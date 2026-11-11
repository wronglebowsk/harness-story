"""Unit and integration tests for harness_story core modules.

Covers:
- models (token estimation, tool descriptors, file path extraction)
- collector (live JSONL hook telemetry read/write & HookCollector)
- reconstruct (synthetic SQLite state.db + real ~/.hermes/state.db sessions,
  5-bucket context window progression, running tool call counts, causal edges,
  failure -> recovery pivots, subagent branches, concurrency lane packing)
- narrator (deterministic narrative synthesis, mock LLM narrative synthesis, compare_stories)
- render (self-contained animated HTML5 story viewer generation)
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict

import pytest

from harness_story import (
    HookCollector,
    compare_stories,
    describe_tool_call,
    estimate_tokens,
    pack_lanes,
    read_live_events,
    reconstruct_story,
    render_story_html,
    save_story,
    synthesize_narrative,
)


def _create_synthetic_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "state.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            user_id TEXT,
            model TEXT,
            model_config TEXT,
            system_prompt TEXT,
            parent_session_id TEXT,
            started_at REAL NOT NULL,
            ended_at REAL,
            end_reason TEXT,
            message_count INTEGER DEFAULT 0,
            tool_call_count INTEGER DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_read_tokens INTEGER DEFAULT 0,
            cache_write_tokens INTEGER DEFAULT 0,
            reasoning_tokens INTEGER DEFAULT 0,
            billing_provider TEXT,
            billing_Base_url TEXT,
            billing_mode TEXT,
            estimated_cost_usd REAL,
            actual_cost_usd REAL,
            cost_status TEXT,
            cost_source TEXT,
            pricing_version TEXT,
            title TEXT
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            tool_call_id TEXT,
            tool_calls TEXT,
            tool_name TEXT,
            timestamp REAL NOT NULL,
            token_count INTEGER,
            finish_reason TEXT,
            reasoning TEXT,
            reasoning_details TEXT,
            codex_reasoning_items TEXT
        );
        """
    )

    t0 = 1762600000.0
    sys_prompt = (
        "You are Hermes Agent.\n"
        "<available_skills>\n- hermes-desktop-plugins\n- attack-navigator\n</available_skills>\n"
        "MEMORY: Always validate plugins before finishing."
    )
    conn.execute(
        """
        INSERT INTO sessions (
            id, source, model, system_prompt, parent_session_id,
            started_at, ended_at, message_count, tool_call_count,
            input_tokens, output_tokens, cache_read_tokens, reasoning_tokens, title
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "sess_parent_01",
            "cli",
            "qwen3.8-flash-next-iq3_xxs",
            sys_prompt,
            None,
            t0,
            t0 + 45.0,
            11,
            5,
            18400,
            2200,
            12000,
            950,
            "Build & verify sample plugin",
        ),
    )

    # Child subagent session
    conn.execute(
        """
        INSERT INTO sessions (
            id, source, model, system_prompt, parent_session_id,
            started_at, ended_at, message_count, tool_call_count,
            input_tokens, output_tokens, cache_read_tokens, reasoning_tokens, title
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "sess_child_01",
            "delegate",
            "qwen3.8-flash-next-iq3_xxs",
            "Subagent system prompt",
            "sess_parent_01",
            t0 + 20.0,
            t0 + 28.0,
            4,
            2,
            4200,
            600,
            2000,
            200,
            "Audit plugin imports",
        ),
    )

    # Child messages
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, 'user', ?, ?)",
        ("sess_child_01", "Check private imports in plugin/__init__.py", t0 + 20.1),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_calls, timestamp, reasoning) VALUES (?, 'assistant', ?, ?, ?, ?)",
        (
            "sess_child_01",
            "Reading __init__.py",
            json.dumps([{
                "id": "call_c1",
                "function": {"name": "read_file", "arguments": json.dumps({"path": "plugin/__init__.py"})},
            }]),
            t0 + 21.0,
            "Let's inspect the imports.",
        ),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_call_id, tool_name, timestamp) VALUES (?, 'tool', ?, 'call_c1', 'read_file', ?)",
        ("sess_child_01", "from plugins.plugin_storage import plugin_data_dir\n", t0 + 22.0),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, 'assistant', ?, ?)",
        ("sess_child_01", "All imports use public plugins.plugin_storage API.", t0 + 27.5),
    )

    # Parent messages:
    # 1. User request
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, 'user', ?, ?)",
        ("sess_parent_01", "Please inspect config.json, update plugin/__init__.py, delegate an audit, and run pytest.", t0 + 1.0),
    )
    # 2. Assistant calls read_file on config.json -> FAILS (FileNotFoundError)
    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_calls, timestamp, reasoning) VALUES (?, 'assistant', ?, ?, ?, ?)",
        (
            "sess_parent_01",
            "",
            json.dumps([{
                "id": "call_1",
                "function": {"name": "read_file", "arguments": json.dumps({"path": "config.json"})},
            }]),
            t0 + 2.0,
            "First I hypothesize config is stored in config.json.",
        ),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_call_id, tool_name, timestamp) VALUES (?, 'tool', ?, 'call_1', 'read_file', ?)",
        ("sess_parent_01", '{"error": "FileNotFoundError: config.json does not exist"}', t0 + 2.4),
    )
    # 3. Assistant pivots to reading plugin/__init__.py
    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_calls, timestamp, reasoning) VALUES (?, 'assistant', ?, ?, ?, ?)",
        (
            "sess_parent_01",
            "",
            json.dumps([{
                "id": "call_2",
                "function": {"name": "read_file", "arguments": json.dumps({"path": "plugin/__init__.py"})},
            }]),
            t0 + 5.0,
            "config.json was missing; pivoting to inspect plugin/__init__.py directly.",
        ),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_call_id, tool_name, timestamp) VALUES (?, 'tool', ?, 'call_2', 'read_file', ?)",
        ("sess_parent_01", "def register(ctx):\n    pass\n", t0 + 5.3),
    )
    # 4. Assistant patches plugin/__init__.py
    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_calls, timestamp, reasoning) VALUES (?, 'assistant', ?, ?, ?, ?)",
        (
            "sess_parent_01",
            "",
            json.dumps([{
                "id": "call_3",
                "function": {"name": "patch", "arguments": json.dumps({"path": "plugin/__init__.py", "diff": "+ ctx.register_tool(...)"})},
            }]),
            t0 + 10.0,
            "Now patching plugin/__init__.py based on what we read.",
        ),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_call_id, tool_name, timestamp) VALUES (?, 'tool', ?, 'call_3', 'patch', ?)",
        ("sess_parent_01", "Successfully patched plugin/__init__.py", t0 + 10.5),
    )
    # 5. Assistant delegates audit + runs pytest
    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_calls, timestamp, reasoning) VALUES (?, 'assistant', ?, ?, ?, ?)",
        (
            "sess_parent_01",
            "",
            json.dumps([
                {
                    "id": "call_4",
                    "function": {"name": "delegate_task", "arguments": json.dumps({"goal": "Audit plugin imports", "role": "Auditor"})},
                },
                {
                    "id": "call_5",
                    "function": {"name": "terminal", "arguments": json.dumps({"command": "pytest -q"})},
                },
            ]),
            t0 + 19.5,
            "Delegating import audit and running pytest to verify our edit.",
        ),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_call_id, tool_name, timestamp) VALUES (?, 'tool', ?, 'call_4', 'delegate_task', ?)",
        ("sess_parent_01", "Subagent completed: All imports use public API.", t0 + 28.2),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_call_id, tool_name, timestamp) VALUES (?, 'tool', ?, 'call_5', 'terminal', ?)",
        ("sess_parent_01", "4 passed in 0.12s", t0 + 30.0),
    )
    # 6. Final assistant response
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp, finish_reason) VALUES (?, 'assistant', ?, ?, 'stop')",
        ("sess_parent_01", "Plugin updated, audited by subagent, and verified with pytest.", t0 + 32.0),
    )
    conn.commit()
    conn.close()
    return db_file


def test_models_and_descriptors() -> None:
    assert estimate_tokens("hello world") >= 2
    d1 = describe_tool_call("terminal", {"command": "pytest tests/test_core.py"})
    assert d1["verb"] == "verified with"
    assert d1["is_test"] is True
    assert "pytest" in d1["target"]

    d2 = describe_tool_call("patch", {"path": "src/app.py"})
    assert d2["verb"] == "edited"
    assert d2["category"] == "mutate"
    assert d2["files_touched"][0]["path"] == "src/app.py"


def test_hook_collector_records_live_events(tmp_path: Path) -> None:
    ended = []
    collector = HookCollector(storage_dir=str(tmp_path), on_session_end_cb=lambda sid: ended.append(sid))
    collector.on_session_start(session_id="s1", model="qwen", platform="cli")
    collector.on_pre_llm_call(session_id="s1", turn_id=1, user_message="hi", is_first_turn=True)
    collector.on_pre_api_request(session_id="s1", api_request_id="req1", approx_input_tokens=2048, system_prompt="sys")
    collector.on_post_api_request(
        session_id="s1",
        api_request_id="req1",
        started_at=10.0,
        first_chunk_at=10.25,
        context_length=2500,
        usage={"input_tokens": 2048, "output_tokens": 300},
    )
    collector.on_pre_tool_call(session_id="s1", tool_call_id="tc1", tool_name="read_file", args={"path": "README.md"})
    collector.on_post_tool_call(
        session_id="s1",
        tool_call_id="tc1",
        tool_name="read_file",
        duration_ms=55,
        status="ok",
        result="contents",
    )
    collector.on_skill_lifecycle(session_id="s1", action="loaded", skill_name="harness-story")
    collector.on_subagent_start(parent_session_id="s1", child_session_id="c1", goal="check", role="Helper")
    collector.on_subagent_stop(parent_session_id="s1", child_session_id="c1", child_status="ok", duration_ms=400)
    collector.on_post_compaction(session_id="s1", before_tokens=90000, after_tokens=22000, messages_removed=30)
    collector.on_post_llm_call(session_id="s1", turn_id=1, assistant_response="done")
    collector.on_session_end(session_id="s1", reason="completed")

    events = read_live_events("s1", storage_dir=str(tmp_path))
    assert len(events) == 12
    assert ended == ["s1"]
    post_api = next(e for e in events if e["event"] == "post_api_request")
    assert post_api["ttfb_ms"] == 250


def test_reconstruct_narrative_and_html_on_synthetic_session(tmp_path: Path) -> None:
    db_file = _create_synthetic_db(tmp_path)
    story = reconstruct_story(
        session_id="sess_parent_01",
        db_path=str(db_file),
        storage_dir=str(tmp_path),
        context_window=131072,
    )

    # 1. Verify kickoff, hidden context_load step, tool call counts, and running series
    assert story["tool_tally"]["total_calls"] == 5
    assert story["tool_tally"]["failed_calls"] == 1
    assert len(story["steps"]) == 8  # 1 user_prompt + 1 context_load + 5 tool_call + 1 assistant_reply
    assert story["steps"][0]["kind"] == "user_prompt"
    assert story["steps"][0]["human_title"].startswith("You asked:")
    assert story["steps"][1]["kind"] == "context_load"
    assert "Hermes loaded your workspace context" in story["steps"][1]["human_title"]
    assert story["context_load"]["skills_count"] >= 2
    tool_steps = [s for s in story["steps"] if s["kind"] == "tool_call"]
    assert [s["running_tool_count"] for s in tool_steps] == [1, 2, 3, 4, 5]
    assert all(s.get("tool_indicator", {}).get("badge") for s in tool_steps)

    # 2. Verify step-by-step context window progression
    timeline = story["context_journey"]["timeline"]
    assert len(timeline) == 8
    assert story["context_journey"]["peak_tokens"] >= story["context_journey"]["initial_tokens"]
    for st in story["steps"]:
        ctx = st["context"]
        assert ctx["total_tokens"] > 0
        assert ctx["context_max"] == 131072
        assert ctx["utilization_pct"] > 0
        bucket_sum = (
            ctx["system_prompt_tokens"]
            + ctx["skills_and_memory_tokens"]
            + ctx["user_messages_tokens"]
            + ctx["assistant_reasoning_tokens"]
            + ctx["tool_io_tokens"]
        )
        assert bucket_sum == ctx["total_tokens"]

    # 3. Verify failure -> recovery pivot detection
    assert len(story["pivots"]) == 1
    pv = story["pivots"][0]
    assert pv["failed_step"] == 3
    assert pv["recovery_step"] == 4
    assert story["steps"][3]["is_pivot"] is True

    # 4. Verify causal edges (triggered_edit, verified, caused_pivot, spawned_subagent)
    edge_kinds = {e.get("relation") or e.get("kind") for e in story["causal_edges"]}
    assert "caused_pivot" in edge_kinds
    assert "triggered_edit" in edge_kinds
    assert "verified" in edge_kinds
    assert "spawned_subagent" in edge_kinds

    # 5. Verify subagent attachment
    assert len(story["subagents"]) == 1
    assert story["subagents"][0]["child_session_id"] == "sess_child_01"

    # 6. Verify deterministic narrative fallback + mock LLM narrative synthesis
    synthesize_narrative(story, use_llm=False)
    assert story["narrative_source"] == "deterministic"
    assert story["headline"]
    assert story["executive_summary"]

    class _FakeLLM:
        model = "mock-qwen"

        def chat_json(self, system: str, user: str, **_: Any) -> Dict[str, Any]:
            return {
                "headline": "LLM synthesized headline for sess_parent_01",
                "executive_summary": "LLM synthesized summary of the 5-tool workflow.",
                "chapter_narratives": {"1": "Polished narrative for chapter 1."},
            }

    synthesize_narrative(story, use_llm=True, model="mock-qwen", llm_client=_FakeLLM())
    assert "mock-qwen" in story["narrative_source"]
    assert story["headline"] == "LLM synthesized headline for sess_parent_01"
    assert story["chapters"][0]["narrative"] == "Polished narrative for chapter 1."

    # 7. Verify HTML viewer rendering and saving
    html_doc = render_story_html(story)
    assert "<!doctype html>" in html_doc.lower()
    assert "play-btn" in html_doc or "btn-play" in html_doc or "ctx-canvas" in html_doc or "<canvas" in html_doc
    jpath, hpath = save_story(story, html_doc, storage_dir=str(tmp_path))
    assert jpath.is_file()
    assert hpath.is_file()

    # 8. Verify compare_stories
    diff = compare_stories(story, story)
    assert diff["deltas"]["tool_calls"] == 0
    assert "Harness Story Comparison" in diff["markdown"]


@pytest.mark.skipif(not Path("/home/paul/.hermes/state.db").is_file(), reason="Real state.db not present")
def test_reconstruct_real_hermes_session(tmp_path: Path) -> None:
    # Use the Jellyfin ac4 transcoding session (17 tool calls) from real ~/.hermes/state.db
    story = reconstruct_story(
        session_id="20261110_012809_cc4c3f",
        db_path="/home/paul/.hermes/state.db",
        storage_dir=str(tmp_path),
    )
    synthesize_narrative(story, use_llm=False)
    assert story["session_id"] == "20261110_012809_cc4c3f"
    assert story["tool_tally"]["total_calls"] >= 15
    assert story["context_journey"]["peak_tokens"] > 1000
    html_doc = render_story_html(story)
    assert "Jellyfin" in html_doc or "20261110_012809_cc4c3f" in html_doc
