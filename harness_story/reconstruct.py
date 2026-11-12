"""Reconstruct comprehensive causal stories from Hermes state.db + live hook telemetry.

Combines:
1. Durable SQLite session, message, usage, and subagent records from ``state.db``
2. High-resolution live hook frames from ``plugin-data/harness-story/live/<session_id>.jsonl``
3. Causal inference (reads -> edits -> verifications, failures -> pivots)
4. Step-by-step context window token accounting across 5 categories
5. Running tool call tallies and concurrency lane packing
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .collector import get_storage_dir, read_live_events
from .models import (
    CATEGORY_LABELS,
    CodeImpactEntry,
    ContextSnapshot,
    StoryChapter,
    StoryStep,
    SubagentBranch,
    clip_text,
    describe_tool_call,
    estimate_tokens,
)

_ERROR_PATTERNS = re.compile(
    r"(Traceback \(most recent call last\)|^\s*Error:|\"error\"\s*:\s*\"[^\"]+\"|\"ok\"\s*:\s*false|\"success\"\s*:\s*false|Command exited with code [1-9]|Could not find old_string|PermissionError|FileNotFoundError|SyntaxError|JSONDecodeError)",
    re.IGNORECASE | re.MULTILINE,
)


def resolve_state_db(db_path: Optional[str] = None) -> Optional[Path]:
    """Locate Hermes's canonical ``state.db``."""
    if db_path:
        p = Path(db_path)
        return p if p.is_file() else None
    from hermes_constants import get_hermes_home
    candidate = get_hermes_home() / "state.db"
    return candidate if candidate.is_file() else None


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def list_recent_sessions(
    db_path: Optional[str] = None,
    limit: int = 20,
    include_cron: bool = True,
    min_tool_calls: int = 1,
) -> List[Dict[str, Any]]:
    """List recent sessions from state.db with summary telemetry."""
    resolved = resolve_state_db(db_path)
    if not resolved:
        return []
    where = ["tool_call_count >= ?"]
    params: List[Any] = [int(min_tool_calls)]
    if not include_cron:
        where.append("source != 'cron'")
    sql = f"""
        SELECT *
        FROM sessions
        WHERE {' AND '.join(where)}
        ORDER BY started_at DESC
        LIMIT ?
    """
    params.append(int(limit))
    rows: List[Dict[str, Any]] = []
    keep_keys = (
        "id", "title", "model", "source", "message_count", "tool_call_count",
        "input_tokens", "output_tokens", "cache_read_tokens", "reasoning_tokens",
        "api_call_count", "parent_session_id", "started_at", "ended_at", "cwd",
    )
    try:
        with _connect_ro(resolved) as conn:
            for r in conn.execute(sql, params):
                d = dict(r)
                rows.append({k: d.get(k) for k in keep_keys})
    except Exception:
        return []
    return rows


def _epoch_ms(ts: Any, fallback_ms: int) -> int:
    if isinstance(ts, (int, float)) and ts > 0:
        return int(ts) if ts > 1e11 else int(round(ts * 1000))
    return fallback_ms


def _parse_json_safe(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except ValueError:
            return None
    return None


def _detect_tool_failure(content: str, is_error_flag: bool = False) -> Tuple[bool, str]:
    """Detect whether a tool output represents a failure and extract a clean error snippet."""
    if is_error_flag:
        return True, clip_text(content, 160)
    if not content:
        return False, ""
    parsed = _parse_json_safe(content)
    if isinstance(parsed, dict):
        if parsed.get("ok") is False or parsed.get("success") is False or parsed.get("status") == "error":
            err = parsed.get("error") or parsed.get("message") or parsed.get("output") or content
            return True, clip_text(err, 160)
        if isinstance(parsed.get("error"), str) and parsed["error"].strip():
            return True, clip_text(parsed["error"], 160)
        out_str = str(parsed.get("output") or "")
        if "Traceback (most recent call last):" in out_str:
            lines = [ln.strip() for ln in out_str.strip().splitlines() if ln.strip()]
            tail = lines[-1] if lines else out_str
            return True, clip_text(f"Traceback: {tail}", 160)
    m = _ERROR_PATTERNS.search(content[:2000])
    if m:
        lines = [ln.strip() for ln in content.strip().splitlines() if ln.strip()]
        for ln in reversed(lines[-8:]):
            if any(k in ln for k in ("Error", "Exception", "failed", "False", "Could not")):
                return True, clip_text(ln, 160)
        return True, clip_text(m.group(0), 160)
    return False, ""


def _summarize_tool_outcome(tool_name: str, content: str, failed: bool, error_snippet: str) -> str:
    """Create a concise human-readable outcome summary from a tool's raw result."""
    if failed:
        return f"Failed — {error_snippet or 'tool returned an error'}"
    if not content:
        return "Completed with empty output"
    parsed = _parse_json_safe(content)
    if isinstance(parsed, dict):
        if "output" in parsed and isinstance(parsed["output"], str):
            out = parsed["output"].strip()
            lines = out.splitlines()
            if not out:
                return "Command succeeded (no stdout)"
            first = clip_text(lines[0], 100)
            return f"Returned {len(lines)} line(s): {first}"
        if "content" in parsed and isinstance(parsed["content"], str):
            lines = parsed["content"].splitlines()
            return f"Read {len(lines)} line(s) ({len(parsed['content']):,} chars)"
        if "techniques" in parsed:
            return f"Processed {parsed['techniques']} ATT&CK techniques"
        if "results" in parsed and isinstance(parsed["results"], list):
            return f"Found {len(parsed['results'])} result(s)"
        for k in ("summary", "message", "status", "path", "file"):
            if isinstance(parsed.get(k), str) and parsed[k].strip():
                return clip_text(parsed[k], 120)
    lines = [ln.strip() for ln in content.strip().splitlines() if ln.strip()]
    if not lines:
        return "Completed"
    return f"{len(lines)} line(s) — {clip_text(lines[0], 100)}"


def _inspect_harness_context_load(
    system_prompt_text: str,
    session_meta: Dict[str, Any],
    messages: List[Dict[str, Any]],
    context_window: int,
) -> Dict[str, Any]:
    """Parse the hidden Hermes context load (system prompt, skills index, connectors, tools, memory)."""
    sp = system_prompt_text or ""

    # 1. Parse <available_skills>...</available_skills>
    skills_list: List[str] = []
    skills_chars = 0
    m_skills = re.search(r"<available_skills>(.*?)</available_skills>", sp, re.DOTALL)
    if m_skills:
        s_block = m_skills.group(1)
        skills_chars = len(s_block)
        for line in s_block.splitlines():
            s_line = line.strip()
            if s_line.startswith("- "):
                name_part = s_line[2:].split(":", 1)[0].strip()
                if name_part and name_part not in skills_list:
                    skills_list.append(name_part)
        for tag_name in re.findall(r"<name>(.*?)</name>", s_block):
            t_clean = tag_name.strip()
            if t_clean and t_clean not in skills_list:
                skills_list.append(t_clean)

    # 2. Parse MEMORY and USER PROFILE blocks
    memory_notes_count = 0
    memory_chars = 0
    user_profile_chars = 0
    semantic_memory = ""

    m_mem_hdr = re.search(r"MEMORY \(your personal notes\)\s*\[.*?—\s*([\d,]+)/[\d,]+\s*chars\]", sp)
    if m_mem_hdr:
        try:
            memory_chars = int(m_mem_hdr.group(1).replace(",", ""))
        except ValueError:
            memory_chars = 0
    if "MEMORY" in sp:
        m_mem_body = re.search(
            r"MEMORY(?:\s*\(your personal notes\))?.*?\n(?:═+\n)?(.*?)(?=\n═+|\nUSER PROFILE|\n# Hermes runtime|\Z)",
            sp,
            re.DOTALL,
        )
        if m_mem_body:
            body_txt = m_mem_body.group(1).strip()
            if not memory_chars:
                memory_chars = len(body_txt)
            memory_notes_count = max(1, len([p for p in body_txt.split("§") if p.strip()])) if body_txt else 0

    m_user_hdr = re.search(r"USER PROFILE \(who the user is\)\s*\[.*?—\s*([\d,]+)/[\d,]+\s*chars\]", sp)
    if m_user_hdr:
        try:
            user_profile_chars = int(m_user_hdr.group(1).replace(",", ""))
        except ValueError:
            user_profile_chars = 0

    m_sem = re.search(r"Semantic memory \(provider:\s*([^)]+)\)", sp)
    if m_sem:
        semantic_memory = m_sem.group(1).strip()

    # 3. Inspect active Hermes profile config.yaml + session tool calls for MCP connectors, plugins, and toolsets
    connectors: List[str] = []
    plugins_enabled: List[str] = []
    toolsets_active: List[str] = []
    try:
        from hermes_constants import get_hermes_home
        cfg_path: Optional[Path] = get_hermes_home() / "config.yaml"
    except Exception:
        cfg_path = None
    if cfg_path and cfg_path.is_file():
        try:
            cfg_txt = cfg_path.read_text(encoding="utf-8", errors="replace")
            m_mcp = re.search(r"^mcp_servers:\s*\n((?:  [a-zA-Z0-9_-]+:.*\n(?:    .*\n)*)+)", cfg_txt, re.MULTILINE)
            if m_mcp:
                for cm in re.finditer(r"^  ([a-zA-Z0-9_-]+):", m_mcp.group(1), re.MULTILINE):
                    cname = cm.group(1).strip()
                    if cname not in connectors:
                        connectors.append(cname)
            m_plg = re.search(r"^\s+enabled:\s*\n((?:\s+-\s+[a-zA-Z0-9_-]+\s*\n)+)", cfg_txt, re.MULTILINE)
            if m_plg:
                for pm in re.finditer(r"^\s+-\s+([a-zA-Z0-9_-]+)", m_plg.group(1), re.MULTILINE):
                    pname = pm.group(1).strip()
                    if pname not in plugins_enabled:
                        plugins_enabled.append(pname)
            m_ts = re.search(r"^\s+cli:\s*\[([^\]]+)\]", cfg_txt, re.MULTILINE)
            if m_ts:
                toolsets_active = [x.strip() for x in m_ts.group(1).split(",") if x.strip()]
        except Exception:
            pass

    # Also detect any mcp__<server>__ tool calls in the session messages
    distinct_tools_used: List[str] = []
    for m in messages:
        tn = str(m.get("tool_name") or "").strip()
        if tn and tn not in distinct_tools_used:
            distinct_tools_used.append(tn)
        if tn.startswith("mcp__"):
            parts = tn.split("__")
            if len(parts) > 1 and parts[1] not in connectors:
                connectors.append(parts[1])

    toolsets_count = len(toolsets_active) or 18
    estimated_tools_count = max(len(distinct_tools_used), toolsets_count * 2 + len(connectors) * 2)

    # 4. Token split between core system prompt + tool schemas vs skills index + memory
    total_sp_tokens = estimate_tokens(sp) if sp else 3400
    # Tool schema definitions sent alongside the system prompt typically add ~1,800 tokens
    tool_schema_tokens = min(2200, max(600, estimated_tools_count * 38)) if sp else 800
    skills_and_mem_tokens = estimate_tokens("x" * (skills_chars + memory_chars + user_profile_chars))
    if skills_and_mem_tokens == 0 and sp:
        skills_and_mem_tokens = max(120, total_sp_tokens // 4)
    core_sys_tokens = max(400, total_sp_tokens + tool_schema_tokens - skills_and_mem_tokens)
    base_total_tokens = core_sys_tokens + skills_and_mem_tokens
    base_pct = round(min(100.0, (base_total_tokens / max(1, context_window)) * 100.0), 2)

    skills_count = len(skills_list)
    sample_skills = skills_list[:6]
    skills_phrase = (
        f"{skills_count} skill{'s' if skills_count != 1 else ''} "
        f"({', '.join(sample_skills[:4])}{'…' if skills_count > 4 else ''})"
        if skills_count > 0
        else "built-in skill index"
    )
    conn_phrase = (
        f"{len(connectors)} MCP connector{'s' if len(connectors) != 1 else ''} ({', '.join(connectors[:4])})"
        if connectors
        else "local workspace connectors"
    )
    plg_phrase = (
        f"{len(plugins_enabled)} enabled plugin{'s' if len(plugins_enabled) != 1 else ''}"
        if plugins_enabled
        else "active plugins"
    )
    mem_phrase = (
        f"{memory_notes_count} personal memory note{'s' if memory_notes_count != 1 else ''} ({memory_chars:,} chars)"
        if memory_notes_count > 0
        else "workspace memory"
    )
    if user_profile_chars > 0:
        mem_phrase += f" + your User Profile ({user_profile_chars:,} chars)"
    if semantic_memory:
        mem_phrase += f" + semantic recall ({semantic_memory})"

    summary_sentence = (
        f"Before the model generated its first word, Hermes silently packed {base_total_tokens:,} tokens "
        f"({base_pct}% of the {context_window:,}-token context window) into the session: indexing {skills_phrase}, "
        f"wiring up {conn_phrase} and {plg_phrase}, exposing ~{estimated_tools_count} tools across "
        f"{toolsets_count} toolsets, and injecting {mem_phrase}."
    )

    return {
        "base_total_tokens": base_total_tokens,
        "total_tokens": base_total_tokens,
        "base_pct": base_pct,
        "utilization_pct": base_pct,
        "core_system_tokens": core_sys_tokens,
        "system_prompt_tokens": core_sys_tokens,
        "skills_and_memory_tokens": skills_and_mem_tokens,
        "tool_schema_tokens": tool_schema_tokens,
        "skills_count": skills_count,
        "sample_skills": sample_skills,
        "skill_categories": sample_skills,
        "connectors_count": len(connectors),
        "connectors": connectors,
        "connectors_list": connectors,
        "plugins_count": len(plugins_enabled),
        "plugins": plugins_enabled,
        "toolsets_count": toolsets_count,
        "tools_count": estimated_tools_count,
        "tools_estimated_count": estimated_tools_count,
        "memory_notes_count": memory_notes_count,
        "memory_chars": memory_chars,
        "user_profile_chars": user_profile_chars,
        "user_profile_loaded": user_profile_chars > 0,
        "semantic_memory": semantic_memory,
        "semantic_memory_provider": semantic_memory,
        "summary": summary_sentence,
    }


def pack_lanes(steps: List[StoryStep]) -> int:
    """Assign each step a concurrency lane (0..K-1) based on overlapping [started_at_ms, ended_at_ms]."""
    lane_ends: List[int] = []
    tool_steps = [s for s in steps if s.kind == "tool_call"]
    for step in sorted(tool_steps, key=lambda x: (x.started_at_ms, x.index)):
        placed = False
        for lane_idx, end_ms in enumerate(lane_ends):
            if end_ms <= step.started_at_ms:
                step.lane = lane_idx
                lane_ends[lane_idx] = step.ended_at_ms
                placed = True
                break
        if not placed:
            step.lane = len(lane_ends)
            lane_ends.append(step.ended_at_ms)
    return max(1, len(lane_ends))


def _load_subagents(conn: sqlite3.Connection, parent_session_id: str) -> List[SubagentBranch]:
    """Load child subagent sessions spawned by *parent_session_id* from state.db."""
    branches: List[SubagentBranch] = []
    try:
        sql = """
            SELECT id, title, model, message_count, tool_call_count,
                   input_tokens, output_tokens, started_at, ended_at, end_reason
            FROM sessions
            WHERE parent_session_id = ?
            ORDER BY started_at ASC
        """
        for row in conn.execute(sql, (parent_session_id,)):
            cid = row["id"]
            started = _epoch_ms(row["started_at"], 0)
            ended = _epoch_ms(row["ended_at"], started + 1000)
            dur = max(0, ended - started) if started and ended else 0

            # Inspect child messages for goal (first user message), summary (last assistant message), and top tools
            goal = ""
            summary = ""
            top_tools: Dict[str, int] = {}
            for m in conn.execute(
                "SELECT role, tool_name, content FROM messages WHERE session_id = ? ORDER BY id ASC",
                (cid,),
            ):
                role = m["role"]
                c = m["content"] or ""
                tname = m["tool_name"]
                if role == "user" and not goal and c.strip():
                    goal = clip_text(c, 160)
                elif role == "assistant" and c.strip():
                    summary = clip_text(c, 220)
                elif role == "tool" and tname:
                    top_tools[tname] = top_tools.get(tname, 0) + 1

            branches.append(
                SubagentBranch(
                    child_session_id=cid,
                    parent_step_index=0,  # linked during causal pass
                    title=row["title"] or f"Subagent {cid[:12]}",
                    goal=goal or (row["title"] or "Delegated task"),
                    model=row["model"] or "unknown",
                    status=row["end_reason"] or "completed",
                    tool_call_count=int(row["tool_call_count"] or 0),
                    message_count=int(row["message_count"] or 0),
                    input_tokens=int(row["input_tokens"] or 0),
                    output_tokens=int(row["output_tokens"] or 0),
                    duration_ms=dur,
                    summary=summary or "Subagent completed its assigned task.",
                    top_tools=dict(sorted(top_tools.items(), key=lambda kv: -kv[1])[:6]),
                )
            )
    except Exception:
        pass
    return branches


def reconstruct_story(
    session_id: Optional[str] = None,
    *,
    db_path: Optional[str] = None,
    storage_dir: Optional[str] = None,
    context_window: int = 131072,
    max_steps: int = 250,
    raw_session: Optional[Dict[str, Any]] = None,
    raw_messages: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Reconstruct a complete, structured HarnessStory dictionary for *session_id* (or latest session)."""
    session_meta: Dict[str, Any] = {}
    messages: List[Dict[str, Any]] = []
    subagents: List[SubagentBranch] = []
    system_prompt_text = ""

    if raw_messages is not None:
        session_meta = dict(raw_session or {})
        session_id = str(session_meta.get("id") or session_id or "custom-session")
        messages = [dict(m) for m in raw_messages]
        system_prompt_text = str(session_meta.get("system_prompt") or "")
    else:
        resolved_db = resolve_state_db(db_path)
        if not resolved_db:
            raise FileNotFoundError("Could not locate Hermes state.db")
        with _connect_ro(resolved_db) as conn:
            if not session_id or session_id == "latest":
                row = conn.execute(
                    "SELECT * FROM sessions WHERE tool_call_count > 0 ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
                if not row:
                    row = conn.execute("SELECT * FROM sessions ORDER BY started_at DESC LIMIT 1").fetchone()
            else:
                row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
                if not row:
                    row = conn.execute(
                        "SELECT * FROM sessions WHERE id LIKE ? ORDER BY started_at DESC LIMIT 1",
                        (f"%{session_id}%",),
                    ).fetchone()
            if not row:
                raise ValueError(f"Session {session_id!r} not found in state.db")
            session_meta = dict(row)
            session_id = str(session_meta["id"])
            system_prompt_text = str(session_meta.get("system_prompt") or "")
            if not system_prompt_text and session_meta.get("system_prompt_hash"):
                sp_row = conn.execute(
                    "SELECT prompt FROM system_prompts WHERE hash = ?",
                    (session_meta["system_prompt_hash"],),
                ).fetchone()
                if sp_row and sp_row["prompt"]:
                    system_prompt_text = str(sp_row["prompt"])

            msg_rows = conn.execute(
                """
                SELECT *
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
            messages = [dict(r) for r in msg_rows]
            subagents = _load_subagents(conn, session_id)

    live_events = read_live_events(session_id, storage_dir)
    live_tool_durations: Dict[str, int] = {}
    live_compactions: List[Dict[str, Any]] = []
    live_api_requests: List[Dict[str, Any]] = []
    live_skills: List[str] = []

    for ev in live_events:
        kind = ev.get("event")
        if kind == "post_tool_call" and ev.get("tool_call_id") and isinstance(ev.get("duration_ms"), (int, float)):
            live_tool_durations[str(ev["tool_call_id"])] = int(ev["duration_ms"])
        elif kind == "post_compaction":
            live_compactions.append(ev)
        elif kind in ("pre_api_request", "post_api_request"):
            live_api_requests.append(ev)
            if kind == "pre_api_request" and ev.get("max_tokens"):
                pass
            if kind == "post_api_request" and isinstance(ev.get("context_length"), int) and ev["context_length"] > 0:
                context_window = int(ev["context_length"])
        elif kind == "on_skill_lifecycle" and ev.get("skill_name"):
            sk = str(ev["skill_name"])
            if sk not in live_skills:
                live_skills.append(sk)

    # Parse the hidden Hermes context load (system prompt, skills index, connectors, tools, memory)
    ctx_load_info = _inspect_harness_context_load(system_prompt_text, session_meta, messages, context_window)
    sys_tokens = int(ctx_load_info["base_total_tokens"])
    for ev in live_api_requests:
        if ev.get("event") == "pre_api_request" and isinstance(ev.get("system_prompt_chars"), int) and ev["system_prompt_chars"] > 0:
            sys_tokens = max(sys_tokens, int(round(ev["system_prompt_chars"] / 3.8)))
            break

    session_start_ms = _epoch_ms(session_meta.get("started_at"), int(time.time() * 1000) - 60000)
    cursor_ms = session_start_ms

    # Map tool_call_id -> assistant intent/args from assistant messages
    pending_calls: Dict[str, Dict[str, Any]] = {}
    steps: List[StoryStep] = []

    # Running context state across the 5 buckets.
    # Starts at 0 at the very moment the user types their kickoff prompt, then Step 2
    # ("Behind the scenes, Hermes loaded your workspace context") visibly unpacks the
    # system prompt + skills/memory into the buckets!
    ctx_buckets: Dict[str, int] = {
        "system_prompt": 0,
        "skills_and_memory": 0,
        "user_messages": 0,
        "assistant_reasoning": 0,
        "tool_io": 0,
    }
    context_load_emitted = False
    running_tool_count = 0
    running_failed_count = 0
    running_cat_counts: Dict[str, int] = {k: 0 for k in CATEGORY_LABELS}
    turn_index = 0
    last_failed_step: Optional[StoryStep] = None
    last_reasoning_text = ""

    def _snapshot_context(step_idx: int, delta: int, compacted: bool = False, freed: int = 0) -> ContextSnapshot:
        total = sum(ctx_buckets.values())
        pct = round(min(100.0, (total / max(1, context_window)) * 100.0), 2)
        return ContextSnapshot(
            step_index=step_idx,
            total_tokens=total,
            context_max=context_window,
            context_pct=pct,
            delta_tokens=delta,
            breakdown=dict(ctx_buckets),
            cache_read_tokens=int(session_meta.get("cache_read_tokens") or 0),
            compacted=compacted,
            compaction_freed_tokens=freed,
            estimated=True,
        )

    def _emit_context_load_step(ts_ms: int) -> None:
        nonlocal context_load_emitted
        if context_load_emitted:
            return
        context_load_emitted = True
        core_sys = int(ctx_load_info["core_system_tokens"])
        sk_mem = int(ctx_load_info["skills_and_memory_tokens"])
        ctx_buckets["system_prompt"] += core_sys
        ctx_buckets["skills_and_memory"] += sk_mem
        delta_load = core_sys + sk_mem
        s_idx = len(steps) + 1
        snap = _snapshot_context(s_idx, delta_load)
        steps.append(
            StoryStep(
                index=s_idx,
                id=f"context-load-{s_idx}",
                turn_index=max(1, turn_index),
                kind="context_load",
                verb="loaded workspace context",
                category="knowledge",
                tool_name="hermes_harness",
                target=(
                    f"{ctx_load_info['skills_count']} skills · "
                    f"{ctx_load_info['connectors_count']} connectors · "
                    f"~{ctx_load_info['tools_count']} tools · memory"
                ),
                intent="Hermes silently assembled system instructions, skill directory, connectors, tool schemas, and personal memory before calling the model.",
                outcome_summary=f"Loaded {delta_load:,} base tokens ({snap.context_pct}% of context window).",
                detail_preview=ctx_load_info["summary"],
                started_at_ms=ts_ms,
                ended_at_ms=ts_ms + 40,
                duration_ms=40,
                running_tool_count=running_tool_count,
                running_category_counts=dict(running_cat_counts),
                running_failed_count=running_failed_count,
                context=snap,
                human_title="Behind the scenes, Hermes loaded your workspace context",
                human_narrative=ctx_load_info["summary"],
                decision_text="Default hidden step: Hermes prepares the model's instructions, available skills, connectors, tools, and personal memory before every session.",
                tool_indicator={
                    "tool_name": "hermes_harness",
                    "badge": "Hermes Context Load",
                    "icon": "🎒",
                    "animation": "backpack_load",
                    "human_title": "Behind the scenes, Hermes loaded your workspace context",
                    "plain_what_happened": ctx_load_info["summary"],
                },
                context_load_details=dict(ctx_load_info),
            )
        )

    for msg in messages:
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        reasoning = str(msg.get("reasoning") or msg.get("reasoning_content") or "")
        msg_ts_ms = _epoch_ms(msg.get("timestamp"), cursor_ms + 250)
        cursor_ms = max(cursor_ms, msg_ts_ms)

        # Check if this row is a compaction summary
        if msg.get("_compressed_summary") or msg.get("compacted"):
            _emit_context_load_step(msg_ts_ms)
            before_total = sum(ctx_buckets.values())
            summary_tok = msg.get("token_count") or estimate_tokens(content)
            freed = max(0, (ctx_buckets["tool_io"] + ctx_buckets["assistant_reasoning"]) // 2)
            ctx_buckets["tool_io"] = max(200, ctx_buckets["tool_io"] - freed)
            ctx_buckets["assistant_reasoning"] = max(200, summary_tok)
            after_total = sum(ctx_buckets.values())
            delta = after_total - before_total
            step_idx = len(steps) + 1
            snap = _snapshot_context(step_idx, delta, compacted=True, freed=max(0, -delta))
            steps.append(
                StoryStep(
                    index=step_idx,
                    id=f"compact-{step_idx}",
                    turn_index=max(1, turn_index),
                    kind="compaction",
                    verb="compacted context",
                    category="orchestrate",
                    tool_name="context_compressor",
                    target=f"freed ~{max(0, -delta):,} tokens into summary",
                    intent="Context window approached threshold; harness compressed older turns to preserve working memory.",
                    outcome_summary=f"Context compacted from {before_total:,} to {after_total:,} tokens.",
                    detail_preview=clip_text(content, 320),
                    started_at_ms=msg_ts_ms,
                    ended_at_ms=msg_ts_ms + 180,
                    duration_ms=180,
                    running_tool_count=running_tool_count,
                    running_category_counts=dict(running_cat_counts),
                    running_failed_count=running_failed_count,
                    context=snap,
                    human_title=f"Hermes compressed older conversation history (freed ~{max(0, -delta):,} tokens)",
                    human_narrative=(
                        f"To keep the context window from overflowing, Hermes summarized older tool outputs and turns, "
                        f"shrinking context from {before_total:,} down to {after_total:,} tokens ({snap.context_pct}% full)."
                    ),
                    tool_indicator={
                        "tool_name": "context_compressor",
                        "badge": "Context Compaction",
                        "icon": "🗜️",
                        "animation": "backpack_load",
                        "human_title": "Hermes compressed older conversation history",
                        "plain_what_happened": f"Compacted context from {before_total:,} to {after_total:,} tokens.",
                    },
                )
            )
            continue

        if role == "user" and not msg.get("tool_call_id"):
            turn_index += 1
            tok = int(msg.get("token_count") or estimate_tokens(content))
            ctx_buckets["user_messages"] += tok
            step_idx = len(steps) + 1
            prompt_preview = clip_text(content, 130) or "User prompt"
            is_kickoff = turn_index == 1
            h_title = f'You asked: “{prompt_preview}”' if is_kickoff else f'You followed up: “{prompt_preview}”'
            snap = _snapshot_context(step_idx, tok)
            steps.append(
                StoryStep(
                    index=step_idx,
                    id=f"user-{step_idx}",
                    turn_index=turn_index,
                    kind="user_prompt",
                    verb="asked",
                    category="orchestrate",
                    tool_name="user",
                    target=clip_text(content, 100) or "User prompt",
                    intent="User initiated or steered the task.",
                    outcome_summary=clip_text(content, 180),
                    detail_preview=clip_text(content, 480),
                    started_at_ms=msg_ts_ms,
                    ended_at_ms=msg_ts_ms + 50,
                    duration_ms=50,
                    running_tool_count=running_tool_count,
                    running_category_counts=dict(running_cat_counts),
                    running_failed_count=running_failed_count,
                    context=snap,
                    human_title=h_title,
                    human_narrative=(
                        f"You kicked off the session with your prompt (+{tok:,} tokens in Your Prompts)."
                        if is_kickoff
                        else f"You sent a follow-up message (+{tok:,} tokens in Your Prompts → Context is now {snap.total_tokens:,} tokens / {snap.context_pct}% full)."
                    ),
                    tool_indicator={
                        "tool_name": "user",
                        "badge": "You Asked" if is_kickoff else "Your Reply",
                        "icon": "💬",
                        "animation": "prompt_bubble",
                        "human_title": h_title,
                        "plain_what_happened": f"You sent: “{prompt_preview}”",
                    },
                )
            )
            if not context_load_emitted:
                _emit_context_load_step(msg_ts_ms + 25)
            continue

        if role == "assistant":
            _emit_context_load_step(msg_ts_ms)
            if reasoning.strip():
                last_reasoning_text = reasoning.strip()
            tcs = _parse_json_safe(msg.get("tool_calls"))
            r_tok = estimate_tokens(reasoning)
            c_tok = int(msg.get("token_count") or estimate_tokens(content))

            if isinstance(tcs, list) and tcs:
                # Assistant decided to invoke one or more tools; attach reasoning & args to pending_calls
                ctx_buckets["assistant_reasoning"] += r_tok + c_tok
                per_call_arg_tokens = 0
                for tc in tcs:
                    if not isinstance(tc, dict):
                        continue
                    cid = str(tc.get("id") or tc.get("call_id") or tc.get("tool_call_id") or "")
                    fn = tc.get("function") if isinstance(tc.get("function"), dict) else tc
                    tname = str(fn.get("name") or tc.get("name") or "tool")
                    raw_args = fn.get("arguments") if "arguments" in fn else tc.get("args")
                    parsed_args = _parse_json_safe(raw_args)
                    if not isinstance(parsed_args, dict):
                        parsed_args = {"raw": str(raw_args or "")} if raw_args else {}
                    arg_tok = estimate_tokens(raw_args)
                    per_call_arg_tokens += arg_tok
                    pending_calls[cid] = {
                        "tool_name": tname,
                        "args": parsed_args,
                        "raw_args": raw_args,
                        "arg_tokens": arg_tok,
                        "started_at_ms": msg_ts_ms,
                        "reasoning": last_reasoning_text or content.strip(),
                        "assistant_tokens": r_tok + c_tok,
                    }
                    r_tok = 0
                    c_tok = 0
            elif content.strip() or reasoning.strip():
                # Assistant reply step (or question / decision step)
                delta_tok = r_tok + c_tok
                ctx_buckets["assistant_reasoning"] += delta_tok
                step_idx = len(steps) + 1
                snap = _snapshot_context(step_idx, delta_tok)
                clean_c = content.strip()
                is_question = "?" in clean_c[-180:] and len(clean_c) < 900
                if is_question:
                    h_title = f'Hermes asked you a question: “{clip_text(clean_c, 110)}”'
                    badge_info = {
                        "tool_name": "assistant",
                        "badge": "Question for You",
                        "icon": "❓",
                        "animation": "question_ask",
                        "human_title": h_title,
                        "plain_what_happened": f"Hermes asked: “{clip_text(clean_c, 140)}”",
                    }
                else:
                    h_title = f'Hermes replied: “{clip_text(clean_c or reasoning, 110)}”'
                    badge_info = {
                        "tool_name": "assistant",
                        "badge": "Hermes Response",
                        "icon": "✅",
                        "animation": "reply_deliver",
                        "human_title": h_title,
                        "plain_what_happened": f"Hermes formulated its response (+{delta_tok:,} tokens in Model Thinking & Reply).",
                    }
                steps.append(
                    StoryStep(
                        index=step_idx,
                        id=f"reply-{step_idx}",
                        turn_index=max(1, turn_index),
                        kind="question" if is_question else "assistant_reply",
                        verb="asked" if is_question else "replied",
                        category="orchestrate",
                        tool_name="assistant",
                        target=clip_text(content or reasoning, 100),
                        intent=clip_text(reasoning, 220) if reasoning else "Synthesized findings into response.",
                        outcome_summary=clip_text(content, 200) or "Model completed reasoning.",
                        detail_preview=clip_text(content or reasoning, 600),
                        started_at_ms=msg_ts_ms,
                        ended_at_ms=msg_ts_ms + 300,
                        duration_ms=300,
                        running_tool_count=running_tool_count,
                        running_category_counts=dict(running_cat_counts),
                        running_failed_count=running_failed_count,
                        context=snap,
                        human_title=h_title,
                        human_narrative=(
                            f"{clip_text(clean_c or reasoning, 220)} "
                            f"(Added +{delta_tok:,} tokens → Context is now {snap.total_tokens:,} / {context_window:,} tokens, {snap.context_pct}% full)."
                        ),
                        decision_text=clip_text(reasoning, 240) if reasoning else "",
                        tool_indicator=badge_info,
                    )
                )
                last_reasoning_text = ""
            continue

        if role == "tool":
            _emit_context_load_step(msg_ts_ms)
            cid = str(msg.get("tool_call_id") or f"call-{len(steps)+1}")
            call_info = pending_calls.pop(cid, {})
            tname = str(msg.get("tool_name") or call_info.get("tool_name") or "tool")
            args = call_info.get("args") or {}
            started_ms = int(call_info.get("started_at_ms") or max(session_start_ms, msg_ts_ms - 350))
            ended_ms = max(started_ms + 25, msg_ts_ms)
            dur_ms = live_tool_durations.get(cid) or max(25, ended_ms - started_ms)
            ended_ms = started_ms + dur_ms

            desc = describe_tool_call(tname, args)
            cat = desc["category"]
            ind = dict(desc.get("tool_indicator") or {})
            running_tool_count += 1
            running_cat_counts[cat] = running_cat_counts.get(cat, 0) + 1

            failed, err_snip = _detect_tool_failure(content)
            if failed:
                running_failed_count += 1

            # Context accounting for this tool call (args + result + any preceding assistant reasoning)
            res_tok = int(msg.get("token_count") or estimate_tokens(content))
            arg_tok = int(call_info.get("arg_tokens") or estimate_tokens(args))
            asst_tok = int(call_info.get("assistant_tokens") or 0)
            bucket_label = "Skills & Memory" if cat == "knowledge" else "Tool Results"
            if cat == "knowledge":
                ctx_buckets["skills_and_memory"] += res_tok + arg_tok
            else:
                ctx_buckets["tool_io"] += res_tok + arg_tok
            total_step_delta = res_tok + arg_tok + asst_tok

            raw_thought = str(call_info.get("reasoning") or last_reasoning_text or "").strip()
            intent_str = clip_text(raw_thought, 240)
            if not intent_str:
                intent_str = _infer_default_intent(desc["verb"], desc["target"], cat)

            # Check if this step is a pivot recovering from a previous failure!
            is_pivot = False
            pivot_reason = ""
            causal_links: List[Dict[str, Any]] = []
            if last_failed_step is not None and not failed:
                is_pivot = True
                if raw_thought:
                    pivot_reason = (
                        f"After step #{last_failed_step.index} ({last_failed_step.tool_name}) failed "
                        f"({clip_text(last_failed_step.error_snippet, 80)}), the model changed course: "
                        f"“{clip_text(raw_thought, 140)}”"
                    )
                else:
                    pivot_reason = (
                        f"Recovered from failed step #{last_failed_step.index} ({last_failed_step.tool_name}) "
                        f"by switching to {desc['verb']} {desc['target']}."
                    )
                causal_links.append({
                    "from_step": last_failed_step.index,
                    "to_step": len(steps) + 1,
                    "relation": "caused_pivot",
                    "label": "Failed call triggered pivot",
                })
                last_failed_step = None

            step_idx = len(steps) + 1
            snap = _snapshot_context(step_idx, total_step_delta)
            outcome_sum = _summarize_tool_outcome(tname, content, failed, err_snip)
            base_human_title = ind.get("human_title") or f"{desc['verb'].capitalize()} {desc['target']}"
            if is_pivot:
                h_title = f"Course correction: {base_human_title[0].lower() + base_human_title[1:]}"
            elif failed:
                h_title = f"{base_human_title} — hit an error"
            else:
                h_title = base_human_title

            plain_what = ind.get("plain_what_happened") or f"Hermes used `{tname}`."
            if is_pivot:
                h_narr = (
                    f"{pivot_reason} {plain_what} Result: {outcome_sum}. "
                    f"Added +{total_step_delta:,} tokens to {bucket_label} "
                    f"(Context is now {snap.total_tokens:,} / {context_window:,} tokens · {snap.context_pct}% full)."
                )
            elif failed:
                h_narr = (
                    f"{plain_what} However, it returned an error: {err_snip or outcome_sum}. "
                    f"Added +{total_step_delta:,} tokens to {bucket_label} "
                    f"(Context is now {snap.total_tokens:,} / {context_window:,} tokens · {snap.context_pct}% full)."
                )
            else:
                h_narr = (
                    f"{plain_what} Result: {outcome_sum}. "
                    f"Added +{total_step_delta:,} tokens to {bucket_label} "
                    f"(Context is now {snap.total_tokens:,} / {context_window:,} tokens · {snap.context_pct}% full)."
                )

            detail_obj = {
                "tool": tname,
                "args": args,
                "output_preview": clip_text(content, 420),
            }
            step = StoryStep(
                index=step_idx,
                id=cid,
                turn_index=max(1, turn_index),
                kind="tool_call",
                verb=desc["verb"],
                category=cat,
                tool_name=tname,
                target=desc["target"],
                intent=intent_str,
                outcome_summary=outcome_sum,
                detail_preview=json.dumps(detail_obj, ensure_ascii=False, indent=2)[:800],
                started_at_ms=started_ms,
                ended_at_ms=ended_ms,
                duration_ms=dur_ms,
                failed=failed,
                error_snippet=err_snip,
                is_pivot=is_pivot,
                pivot_reason=pivot_reason,
                files_touched=desc["files_touched"],
                causal_links=causal_links,
                running_tool_count=running_tool_count,
                running_category_counts=dict(running_cat_counts),
                running_failed_count=running_failed_count,
                context=snap,
                human_title=h_title,
                human_narrative=h_narr,
                decision_text=clip_text(raw_thought, 260) if raw_thought else intent_str,
                tool_indicator=ind,
            )
            steps.append(step)
            if failed:
                last_failed_step = step
            last_reasoning_text = ""

            if len(steps) >= max_steps:
                break

    # Reconcile final token count with session's reported input_tokens if higher, scaling smoothly
    _calibrate_context_curve(steps, session_meta, context_window)

    # Compute concurrency lanes
    max_lanes = pack_lanes(steps)

    # Build causal links across file reads -> edits -> test verifications, and link subagents
    causal_edges, code_impact = _build_causal_and_impact_graph(steps, subagents)

    # Segment steps into story chapters
    chapters = _build_story_chapters(steps)

    # Compute overall tool tally & harness mechanics summary
    tool_steps = [s for s in steps if s.kind == "tool_call"]
    by_tool: Dict[str, int] = {}
    for s in tool_steps:
        by_tool[s.tool_name] = by_tool.get(s.tool_name, 0) + 1
    by_tool_sorted = dict(sorted(by_tool.items(), key=lambda kv: (-kv[1], kv[0])))

    pivots = [
        {
            "step_index": s.index,
            "recovery_step": s.index,
            "tool_name": s.tool_name,
            "recovery_tool": s.tool_name,
            "target": s.target,
            "reason": s.pivot_reason,
            "from_step": s.causal_links[0]["from_step"] if s.causal_links else None,
            "failed_step": s.causal_links[0]["from_step"] if s.causal_links else None,
        }
        for s in steps
        if s.is_pivot
    ]

    ended_at_ms = steps[-1].ended_at_ms if steps else session_start_ms
    started_at_ms = steps[0].started_at_ms if steps else session_start_ms
    total_duration_ms = max(0, ended_at_ms - started_at_ms)

    peak_ctx = max((s.context.total_tokens for s in steps if s.context), default=sys_tokens)
    peak_pct = round(min(100.0, (peak_ctx / max(1, context_window)) * 100.0), 1)
    start_ctx = sys_tokens
    end_ctx = steps[-1].context.total_tokens if (steps and steps[-1].context) else sys_tokens

    skills_loaded: List[str] = list(live_skills)
    memories_used = 0
    for s in tool_steps:
        if s.tool_name in ("skill_view", "skill_manage") and s.target not in skills_loaded:
            skills_loaded.append(s.target)
        elif s.tool_name in ("local_recall", "memory", "session_search"):
            memories_used += 1

    compaction_steps = [s for s in steps if s.kind == "compaction"]

    slug = _make_slug(session_id, session_meta.get("title"))
    title = str(session_meta.get("title") or f"Session {session_id[:16]}")

    story: Dict[str, Any] = {
        "schema_version": "1.0",
        "session_id": session_id,
        "slug": slug,
        "title": title,
        "model": str(session_meta.get("model") or "unknown"),
        "source": str(session_meta.get("source") or "cli"),
        "cwd": str(session_meta.get("cwd") or ""),
        "started_at_ms": started_at_ms,
        "ended_at_ms": ended_at_ms,
        "duration_ms": total_duration_ms,
        "headline": _build_deterministic_headline(
            title, ctx_load_info, len(tool_steps), len(pivots), len(subagents), peak_pct
        ),
        "executive_summary": _build_deterministic_summary(
            title,
            ctx_load_info,
            steps,
            chapters,
            by_tool_sorted,
            pivots,
            code_impact,
            subagents,
            start_ctx,
            peak_ctx,
            context_window,
        ),
        "narrative_source": "deterministic",
        "context_load": ctx_load_info,
        "tool_tally": {
            "total_calls": len(tool_steps),
            "succeeded": sum(1 for s in tool_steps if not s.failed),
            "failed": sum(1 for s in tool_steps if s.failed),
            "failed_calls": sum(1 for s in tool_steps if s.failed),
            "pivots": len(pivots),
            "max_concurrency_lanes": max_lanes,
            "total_tool_duration_ms": sum(s.duration_ms for s in tool_steps),
            "by_category": {k: running_cat_counts.get(k, 0) for k in CATEGORY_LABELS},
            "category_labels": CATEGORY_LABELS,
            "by_tool": by_tool_sorted,
        },
        "context_journey": {
            "context_max": context_window,
            "start_tokens": start_ctx,
            "initial_tokens": start_ctx,
            "peak_tokens": peak_ctx,
            "peak_pct": peak_pct,
            "end_tokens": end_ctx,
            "final_tokens": end_ctx,
            "end_pct": round(min(100.0, (end_ctx / max(1, context_window)) * 100.0), 1),
            "final_pct": round(min(100.0, (end_ctx / max(1, context_window)) * 100.0), 1),
            "cache_read_tokens": int(session_meta.get("cache_read_tokens") or 0),
            "system_prompt_tokens": sys_tokens,
            "compactions_count": len(compaction_steps) + len(live_compactions),
            "final_breakdown": dict(steps[-1].context.breakdown) if (steps and steps[-1].context) else dict(ctx_buckets),
            "timeline": [
                {
                    "step": s.index,
                    "label": f"{s.verb} {clip_text(s.target, 32)}",
                    "total_tokens": s.context.total_tokens if s.context else 0,
                    "context_pct": s.context.context_pct if s.context else 0.0,
                    "delta_tokens": s.context.delta_tokens if s.context else 0,
                    "breakdown": s.context.breakdown if s.context else {},
                    "compacted": bool(s.context and s.context.compacted),
                    "running_tool_count": s.running_tool_count,
                }
                for s in steps
            ],
        },
        "harness_mechanics": {
            "api_calls": int(session_meta.get("api_call_count") or len(tool_steps) or 1),
            "input_tokens_billed": int(session_meta.get("input_tokens") or peak_ctx),
            "output_tokens_billed": int(session_meta.get("output_tokens") or 0),
            "cache_read_tokens": int(session_meta.get("cache_read_tokens") or 0),
            "reasoning_tokens": int(session_meta.get("reasoning_tokens") or 0),
            "skills_activated": skills_loaded,
            "memory_operations": memories_used,
            "compactions": len(compaction_steps) + len(live_compactions),
            "subagents_spawned": len(subagents),
            "live_hook_events_captured": len(live_events),
        },
        "chapters": [c.to_dict() for c in chapters],
        "steps": [s.to_dict() for s in steps],
        "causal_edges": causal_edges,
        "pivots": pivots,
        "code_impact": [ci.to_dict() for ci in code_impact],
        "subagents": [sb.to_dict() for sb in subagents],
    }
    return story


def _infer_default_intent(verb: str, target: str, category: str) -> str:
    if category == "explore":
        return f"Gather evidence and inspect {target} before making changes."
    if category == "mutate":
        return f"Apply changes to {target} based on prior inspection."
    if category == "execute":
        if "verified" in verb:
            return f"Run verification suite ({target}) to confirm changes work as expected."
        return f"Execute {target} in the workspace environment."
    if category == "knowledge":
        return f"Load domain procedure or recall prior session context ({target})."
    if category == "orchestrate":
        return f"Coordinate workflow step: {verb} {target}."
    return f"Invoke external capability ({verb} {target})."


def _calibrate_context_curve(steps: List[StoryStep], session_meta: Dict[str, Any], context_window: int) -> None:
    """Keep per-step context numbers realistic and aligned with session metadata."""
    if not steps:
        return
    for s in steps:
        if s.context:
            s.context.total_tokens = sum(s.context.breakdown.values())
            s.context.context_pct = round(
                min(100.0, (s.context.total_tokens / max(1, context_window)) * 100.0), 2
            )


def _build_causal_and_impact_graph(
    steps: List[StoryStep], subagents: List[SubagentBranch]
) -> Tuple[List[Dict[str, Any]], List[CodeImpactEntry]]:
    """Link file reads -> edits -> verifications, failure -> pivots, and delegate_task -> subagents."""
    edges: List[Dict[str, Any]] = []
    file_map: Dict[str, CodeImpactEntry] = {}
    last_read_by_file: Dict[str, int] = {}
    last_edit_by_file: Dict[str, int] = {}
    recent_edited_files: List[Tuple[str, int]] = []
    subagent_cursor = 0

    for step in steps:
        for link in step.causal_links:
            edges.append(link)

        if step.tool_name == "delegate_task" and subagent_cursor < len(subagents):
            sb = subagents[subagent_cursor]
            sb.parent_step_index = step.index
            subagent_cursor += 1
            edge = {
                "from_step": step.index,
                "to_step": step.index,
                "relation": "spawned_subagent",
                "label": f"Spawned {sb.title} ({sb.tool_call_count} tools)",
                "child_session_id": sb.child_session_id,
            }
            step.causal_links.append(edge)
            edges.append(edge)

        for ft in step.files_touched:
            fpath = ft["path"]
            op = ft["op"]
            if not fpath:
                continue
            entry = file_map.setdefault(fpath, CodeImpactEntry(path=fpath))
            if op == "read":
                if step.index not in entry.reads:
                    entry.reads.append(step.index)
                last_read_by_file[fpath] = step.index
            elif op == "edit":
                if step.index not in entry.edits:
                    entry.edits.append(step.index)
                if step.failed:
                    entry.status = "failed_mutation"
                elif entry.status != "verified":
                    entry.status = "modified"
                if fpath in last_read_by_file and last_read_by_file[fpath] != step.index:
                    edge = {
                        "from_step": last_read_by_file[fpath],
                        "to_step": step.index,
                        "relation": "triggered_edit",
                        "label": f"Read of {fpath} informed edit",
                    }
                    step.causal_links.append(edge)
                    edges.append(edge)
                last_edit_by_file[fpath] = step.index
                recent_edited_files.append((fpath, step.index))
            elif op == "test":
                if step.index not in entry.verifications:
                    entry.verifications.append(step.index)
                if fpath in last_edit_by_file and not step.failed:
                    entry.status = "verified"

        # If this step is a test verification command, link it to recently edited files
        if step.verb == "verified with" and recent_edited_files:
            for fpath, edit_step_idx in recent_edited_files[-3:]:
                if edit_step_idx < step.index:
                    edge = {
                        "from_step": edit_step_idx,
                        "to_step": step.index,
                        "relation": "verified",
                        "label": f"Verified edit to {fpath}",
                    }
                    if not any(e["from_step"] == edit_step_idx and e["to_step"] == step.index for e in edges):
                        step.causal_links.append(edge)
                        edges.append(edge)
                    if not step.failed and fpath in file_map:
                        file_map[fpath].status = "verified"
                        if step.index not in file_map[fpath].verifications:
                            file_map[fpath].verifications.append(step.index)

    # Sort code impact entries: verified/modified first, then by total interactions
    impact_list = sorted(
        file_map.values(),
        key=lambda e: (
            0 if e.status == "verified" else 1 if e.status == "modified" else 2 if e.status == "failed_mutation" else 3,
            -(len(e.edits) * 3 + len(e.verifications) * 2 + len(e.reads)),
            e.path,
        ),
    )
    return edges, impact_list[:40]


def _build_story_chapters(steps: List[StoryStep]) -> List[StoryChapter]:
    """Segment steps into meaningful story chapters with prose narratives."""
    if not steps:
        return []

    # Group into chunks of ~8-18 steps or turn boundaries / phase shifts
    raw_groups: List[List[StoryStep]] = []
    current: List[StoryStep] = []

    for s in steps:
        if current:
            # Start a new chapter on a new user prompt (if current already has tool work)
            # or when current chapter reaches 14 steps and the category shifts
            has_tools = any(x.kind == "tool_call" for x in current)
            if (s.kind == "user_prompt" and has_tools and len(current) >= 4) or len(current) >= 16:
                raw_groups.append(current)
                current = []
        current.append(s)
    if current:
        raw_groups.append(current)

    chapters: List[StoryChapter] = []
    for idx, grp in enumerate(raw_groups, start=1):
        tool_steps = [s for s in grp if s.kind == "tool_call"]
        cats: Dict[str, int] = {}
        for s in tool_steps:
            cats[s.category] = cats.get(s.category, 0) + 1
        failed_cnt = sum(1 for s in tool_steps if s.failed)
        pivot_cnt = sum(1 for s in grp if s.is_pivot)

        phase_kind, title = _classify_chapter(idx, len(raw_groups), grp, cats, failed_cnt, pivot_cnt)
        start_ctx = grp[0].context.total_tokens if grp[0].context else 0
        end_ctx = grp[-1].context.total_tokens if grp[-1].context else start_ctx
        dur_ms = max(0, grp[-1].ended_at_ms - grp[0].started_at_ms)

        decisions: List[str] = []
        for s in grp:
            if s.is_pivot and s.pivot_reason:
                decisions.append(s.pivot_reason)
            elif s.kind == "tool_call" and s.intent and not s.intent.startswith(("Gather evidence", "Execute ", "Apply changes")):
                decisions.append(f"Step #{s.index} ({s.verb} {clip_text(s.target, 36)}): {clip_text(s.intent, 120)}")
        decisions = decisions[:4]

        narrative = _compose_chapter_narrative(idx, title, grp, tool_steps, cats, failed_cnt, pivot_cnt, start_ctx, end_ctx)

        chapters.append(
            StoryChapter(
                chapter_index=idx,
                title=title,
                phase_kind=phase_kind,
                start_step=grp[0].index,
                end_step=grp[-1].index,
                tool_call_count=len(tool_steps),
                failed_count=failed_cnt,
                pivot_count=pivot_cnt,
                duration_ms=dur_ms,
                context_start_tokens=start_ctx,
                context_end_tokens=end_ctx,
                context_delta_tokens=end_ctx - start_ctx,
                narrative=narrative,
                key_decisions=decisions,
                categories_used=cats,
            )
        )
    return chapters


def _classify_chapter(
    idx: int,
    total_chapters: int,
    grp: List[StoryStep],
    cats: Dict[str, int],
    failed_cnt: int,
    pivot_cnt: int,
) -> Tuple[str, str]:
    if any(s.tool_name == "delegate_task" for s in grp):
        return "orchestrate", f"Chapter {idx}: Parallel Subagent Delegation"
    if pivot_cnt > 0 and failed_cnt > 0:
        return "pivot", f"Chapter {idx}: Hypothesis Test & Recovery Pivot"
    top_cat = max(cats.items(), key=lambda kv: kv[1])[0] if cats else "explore"
    if idx == 1 and (cats.get("knowledge", 0) > 0 or top_cat == "explore"):
        return "recon", f"Chapter {idx}: Reconnaissance & Context Assembly"
    if top_cat == "mutate":
        return "build", f"Chapter {idx}: Implementation & File Mutation"
    if any(s.verb == "verified with" for s in grp):
        return "verify", f"Chapter {idx}: Verification & Quality Gate"
    if idx == total_chapters and any(s.kind == "assistant_reply" for s in grp):
        return "delivery", f"Chapter {idx}: Final Synthesis & Delivery"
    if top_cat == "execute":
        return "execute", f"Chapter {idx}: Command Execution & Probing"
    return "explore", f"Chapter {idx}: Deep Inspection & Analysis"


def _compose_chapter_narrative(
    idx: int,
    title: str,
    grp: List[StoryStep],
    tool_steps: List[StoryStep],
    cats: Dict[str, int],
    failed_cnt: int,
    pivot_cnt: int,
    start_ctx: int,
    end_ctx: int,
) -> str:
    parts: List[str] = []
    user_steps = [s for s in grp if s.kind == "user_prompt"]
    if user_steps:
        parts.append(f"Opened with user goal: “{clip_text(user_steps[0].target, 90)}”.")

    if tool_steps:
        verbs: List[str] = []
        for s in tool_steps[:4]:
            verbs.append(f"{s.verb} `{clip_text(s.target, 36)}`")
        more = f" and {len(tool_steps) - 4} more action(s)" if len(tool_steps) > 4 else ""
        parts.append(f"The agent executed {len(tool_steps)} tool call(s) ({', '.join(verbs)}{more}).")

    if failed_cnt or pivot_cnt:
        piv_steps = [s for s in grp if s.is_pivot]
        if piv_steps:
            parts.append(clip_text(piv_steps[0].pivot_reason, 180))
        elif failed_cnt:
            parts.append(f"Encountered {failed_cnt} failed tool call(s) that required inspection.")

    delta = end_ctx - start_ctx
    sign = "+" if delta >= 0 else ""
    parts.append(f"Context window moved from {start_ctx:,} to {end_ctx:,} tokens ({sign}{delta:,} tok).")
    return " ".join(parts)


def _build_deterministic_headline(
    title: str,
    ctx_load: Dict[str, Any],
    tool_count: int,
    pivot_count: int,
    subagent_count: int,
    peak_pct: float,
) -> str:
    sk = int(ctx_load.get("skills_count") or 0)
    cn = int(ctx_load.get("connectors_count") or 0)
    clauses = [
        f"Hermes loaded {int(ctx_load.get('total_tokens') or 0):,} tokens of context ({sk} skills, {cn} connectors)",
        f"used {tool_count} tool{'s' if tool_count != 1 else ''}",
    ]
    if pivot_count:
        clauses.append(f"made {pivot_count} course correction{'s' if pivot_count != 1 else ''}")
    if subagent_count:
        clauses.append(f"delegated to {subagent_count} helper subagent{'s' if subagent_count != 1 else ''}")
    clauses.append(f"and reached {peak_pct}% of the context window")
    return f"You asked: “{title}” — {', '.join(clauses)}."


def _build_deterministic_summary(
    title: str,
    ctx_load: Dict[str, Any],
    steps: List[StoryStep],
    chapters: List[StoryChapter],
    by_tool: Dict[str, int],
    pivots: List[Dict[str, Any]],
    code_impact: List[CodeImpactEntry],
    subagents: List[SubagentBranch],
    start_ctx: int,
    peak_ctx: int,
    context_window: int,
) -> str:
    kickoff = steps[0].target if (steps and steps[0].kind == "user_prompt") else title
    p1 = f"You asked: “{clip_text(kickoff, 200)}”"

    sk = int(ctx_load.get("skills_count") or 0)
    cn = int(ctx_load.get("connectors_count") or 0)
    cn_names = ", ".join(ctx_load.get("connectors_list") or [])
    plg = int(ctx_load.get("plugins_count") or 0)
    tls = int(ctx_load.get("tools_estimated_count") or 0)
    tsets = int(ctx_load.get("toolsets_count") or 0)
    notes = int(ctx_load.get("memory_notes_count") or 0)
    start_pct = round(start_ctx / max(1, context_window) * 100, 1)
    conn_phrase = f"{cn} MCP connectors ({cn_names})" if cn_names else f"{cn} MCP connectors"
    p2 = (
        f"Behind the scenes (Hermes Context Load): Before calling the model, Hermes automatically packed "
        f"{start_ctx:,} tokens ({start_pct}% of the {context_window:,}-token window) into context — "
        f"{sk} skills, {conn_phrase}, {plg} plugins, ~{tls} tools across {tsets} toolsets, and "
        f"{notes} personal memory notes{' + your User Profile' if ctx_load.get('user_profile_loaded') else ''}."
    )

    tool_steps = [s for s in steps if s.kind == "tool_call"]
    top_tools_str = ", ".join(f"{k} (×{v})" for k, v in list(by_tool.items())[:4]) or "no tools"
    p3_parts: List[str] = [
        f"How Hermes & the Model Worked Together: Across {len(tool_steps)} tool calls ({top_tools_str}), "
        f"the conversation context grew from {start_ctx:,} tokens to {peak_ctx:,} / {context_window:,} tokens "
        f"({round(peak_ctx / max(1, context_window) * 100, 1)}%)."
    ]
    if pivots:
        p3_parts.append(
            f"Along the way, Hermes hit {len(pivots)} obstacle(s) and adjusted its strategy "
            f"(first at step #{pivots[0]['step_index']}: {clip_text(pivots[0]['reason'], 150)})."
        )
    verified = [c.path for c in code_impact if c.status == "verified"]
    modified = [c.path for c in code_impact if c.status == "modified"]
    if verified or modified:
        touched = (verified + modified)[:4]
        p3_parts.append(
            f"It inspected {len(code_impact)} file(s) and edited {len(verified) + len(modified)} "
            f"({', '.join(touched)}), verifying {len(verified)} with test/check commands."
        )
    if subagents:
        p3_parts.append(
            f"It also spawned {len(subagents)} helper subagent(s) that ran "
            f"{sum(s.tool_call_count for s in subagents)} tool calls in their own separate context windows."
        )
    return "\n\n".join([p1, p2, " ".join(p3_parts)])


def _make_slug(session_id: str, title: Optional[str]) -> str:
    base = (session_id or "story").strip()
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", base).strip("-").lower()
    return clean[:64] or "story"


def save_story(story: Dict[str, Any], html_content: str, storage_dir: Optional[str] = None) -> Tuple[Path, Path]:
    """Persist ``<slug>.json`` and ``<slug>.html`` in the plugin's durable data directory."""
    root = get_storage_dir(storage_dir)
    slug = str(story.get("slug") or "story")
    json_path = root / "stories" / f"{slug}.json"
    html_path = root / "out" / f"{slug}.html"
    json_path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(html_content, encoding="utf-8")
    return json_path, html_path
