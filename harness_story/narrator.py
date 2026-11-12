"""Hybrid LLM narrative synthesizer and session comparator for harness-story.

Combines deterministic causal/context telemetry with an optional LLM pass (via any
OpenAI-compatible endpoint or Hermes's ``ctx.llm``) to weave a human-readable story
of what the model tried, why it pivoted, and how the harness managed context.
Always degrades cleanly to deterministic prose if the LLM endpoint is offline or skipped.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .models import clip_text


class LocalOpenAI:
    """Zero-dependency OpenAI-compatible chat completion client (stdlib urllib only)."""

    def __init__(self, base_url: str = "", model: str = "qwen3.8-flash-next-iq3_xxs",
                 api_key: str = "local", timeout: float = 25.0) -> None:
        clean = (base_url or "").strip().rstrip("/")
        if clean.endswith("/v1"):
            clean = clean[:-3]
        self.base_url = clean
        self.model = model or "qwen3.8-flash-next-iq3_xxs"
        self.api_key = api_key or "local"
        self.timeout = timeout

    def chat_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 900) -> Optional[Dict[str, Any]]:
        if not self.base_url:
            return None
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
        choices = body.get("choices") or []
        if not choices:
            return None
        msg = choices[0].get("message") or {}
        content = str(msg.get("content") or "").strip()
        return _extract_json_object(content)


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Extract a JSON object from an LLM response (stripping any <think> or markdown fences)."""
    if not text:
        return None
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE).strip()
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except ValueError:
            return None
    return None


def build_deterministic_insights(story: Dict[str, Any]) -> List[str]:
    """Generate plain-English insights about the kickoff, hidden context load, tool steps, and pivots."""
    tally = story.get("tool_tally") or {}
    ctx = story.get("context_journey") or {}
    ctx_load = story.get("context_load") or {}
    mech = story.get("harness_mechanics") or {}
    pivots = story.get("pivots") or []
    impact = story.get("code_impact") or []
    subagents = story.get("subagents") or []

    insights: List[str] = []
    if ctx_load:
        insights.append(
            f"Hidden Hermes Context Load: Before the model took its first step, Hermes loaded "
            f"{ctx_load.get('total_tokens', 0):,} tokens ({ctx_load.get('utilization_pct', 0)}%) of workspace context — "
            f"{ctx_load.get('skills_count', 0)} skills, {ctx_load.get('connectors_count', 0)} MCP connectors, "
            f"{ctx_load.get('plugins_count', 0)} plugins, ~{ctx_load.get('tools_estimated_count', 0)} tools, and "
            f"{ctx_load.get('memory_notes_count', 0)} personal memory notes."
        )

    total_calls = int(tally.get("total_calls") or 0)
    failed = int(tally.get("failed") or 0)
    by_tool = tally.get("by_tool") or {}
    top_tool_str = ", ".join(f"{k} ({v}×)" for k, v in list(by_tool.items())[:4]) or "none"

    insights.append(
        f"Tools Used: Hermes used {total_calls} tool call{'s' if total_calls != 1 else ''} "
        f"({tally.get('succeeded', 0)} succeeded, {failed} ran into an error; most used: {top_tool_str})."
    )

    start_tok = int(ctx.get("start_tokens") or 0)
    peak_tok = int(ctx.get("peak_tokens") or 0)
    max_tok = int(ctx.get("context_max") or 131072)
    peak_pct = ctx.get("peak_pct") or 0.0
    fb = ctx.get("final_breakdown") or {}
    tool_io_tok = int(fb.get("tool_io") or 0)
    insights.append(
        f"Context Window Growth: Started at {start_tok:,} tokens and grew to "
        f"{peak_tok:,} / {max_tok:,} tokens ({peak_pct}%), with tool outputs adding {tool_io_tok:,} tokens."
    )

    cache_read = int(mech.get("cache_read_tokens") or 0)
    if cache_read > 0:
        insights.append(
            f"Prompt Cache Speedup: Hermes reused {cache_read:,} cached tokens across "
            f"{mech.get('api_calls', 1)} model turns so it didn't have to re-read your workspace context from scratch."
        )

    if pivots:
        insights.append(
            f"Course Corrections (Pivots): Hermes adjusted its approach {len(pivots)} time(s) after a tool error "
            f"(first at Step #{pivots[0].get('step_index')}: {clip_text(pivots[0].get('reason'), 130)})."
        )

    verified = [c["path"] for c in impact if c.get("status") == "verified"]
    modified = [c["path"] for c in impact if c.get("status") == "modified"]
    if verified or modified:
        insights.append(
            f"Files & Verification: {len(verified)} edited file(s) were verified by a test or check command; "
            f"{len(modified)} edited file(s) had no separate test command."
        )

    if subagents:
        insights.append(
            f"Subagent Helpers: Hermes delegated {len(subagents)} side-task(s) to helper agents, keeping "
            f"{sum(int(s.get('tool_call_count') or 0) for s in subagents)} tool calls out of your main context window."
        )

    return insights


def synthesize_narrative(
    story: Dict[str, Any],
    *,
    use_llm: bool = True,
    base_url: str = "",
    model: str = "qwen3.8-flash-next-iq3_xxs",
    llm_client: Optional[Any] = None,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    """Enrich *story* in-place with deterministic insights and optional LLM-synthesized narrative."""
    story["harness_insights"] = build_deterministic_insights(story)
    if not use_llm or (llm_client is None and not (base_url or "").strip()):
        return story

    # Build a compact, high-signal digest for the LLM narrator
    digest = {
        "title": story.get("title"),
        "kickoff_prompt": ((story.get("steps") or [{}])[0].get("target") if story.get("steps") else story.get("title")),
        "context_load": story.get("context_load"),
        "model": story.get("model"),
        "duration_seconds": round(float(story.get("duration_ms") or 0) / 1000.0, 1),
        "tool_tally": story.get("tool_tally"),
        "context_journey": {
            k: (story.get("context_journey") or {}).get(k)
            for k in ("start_tokens", "peak_tokens", "peak_pct", "end_tokens", "context_max", "final_breakdown")
        },
        "pivots": (story.get("pivots") or [])[:5],
        "code_impact": (story.get("code_impact") or [])[:8],
        "subagents": [
            {"title": s.get("title"), "goal": s.get("goal"), "tools": s.get("tool_call_count"), "summary": s.get("summary")}
            for s in (story.get("subagents") or [])[:5]
        ],
        "chapters": [
            {
                "chapter_index": c.get("chapter_index"),
                "title": c.get("title"),
                "steps": f"{c.get('start_step')}-{c.get('end_step')}",
                "tools": c.get("tool_call_count"),
                "context_delta": c.get("context_delta_tokens"),
                "draft_narrative": c.get("narrative"),
                "key_decisions": c.get("key_decisions"),
            }
            for c in (story.get("chapters") or [])[:8]
        ],
    }

    sys_prompt = (
        "You are the Hermes Agent Storyteller. Given a session digest, write a warm, clear, natural-language story "
        "for a human reader explaining:\n"
        "1) What the user asked (`You asked: \"...\"`),\n"
        "2) What Hermes loaded behind the scenes before the first model call (how much context in tokens/%, how many skills, "
        "connectors, plugins, and tools were packed),\n"
        "3) The actual steps Hermes and the model took together — which tools were used, what decisions or questions happened, "
        "how it adjusted after any errors (pivots), and how the context window grew.\n"
        "Respond ONLY with a valid JSON object matching this schema:\n"
        "{\n"
        '  "headline": "One natural-language sentence starting with You asked: \\"...\\" and summarizing the outcome",\n'
        '  "executive_summary": "2-3 warm, clear paragraphs starting with You asked: \\"...\\", then explaining the hidden Hermes context load, and then walking through the steps and context growth",\n'
        '  "chapter_narratives": {"1": "Polished plain-English narrative for chapter 1...", "2": "..."}\n'
        "}"
    )
    user_prompt = json.dumps(digest, ensure_ascii=False, indent=2)

    try:
        client = llm_client or LocalOpenAI(base_url=base_url, model=model, timeout=timeout)
        result = client.chat_json(sys_prompt, user_prompt)
        if isinstance(result, dict):
            if isinstance(result.get("headline"), str) and result["headline"].strip():
                story["headline"] = clip_text(result["headline"].strip(), 220)
            if isinstance(result.get("executive_summary"), str) and result["executive_summary"].strip():
                story["executive_summary"] = result["executive_summary"].strip()
            ch_map = result.get("chapter_narratives")
            if isinstance(ch_map, dict):
                for ch in story.get("chapters") or []:
                    cidx = str(ch.get("chapter_index"))
                    if isinstance(ch_map.get(cidx), str) and ch_map[cidx].strip():
                        ch["narrative"] = ch_map[cidx].strip()
            story["narrative_source"] = f"hybrid_llm ({model})"
    except Exception as exc:
        story["narrative_source"] = "deterministic"
        story["narrative_llm_note"] = f"Used deterministic narrative ({type(exc).__name__})"

    return story


def compare_stories(story_a: Dict[str, Any], story_b: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two session stories across tool usage, context efficiency, pivots, and code impact."""
    ta = story_a.get("tool_tally") or {}
    tb = story_b.get("tool_tally") or {}
    ca = story_a.get("context_journey") or {}
    cb = story_b.get("context_journey") or {}

    calls_a = int(ta.get("total_calls") or 0)
    calls_b = int(tb.get("total_calls") or 0)
    peak_a = int(ca.get("peak_tokens") or 0)
    peak_b = int(cb.get("peak_tokens") or 0)
    fail_a = int(ta.get("failed") or 0)
    fail_b = int(tb.get("failed") or 0)
    piv_a = int(ta.get("pivots") or 0)
    piv_b = int(tb.get("pivots") or 0)
    dur_a = int(story_a.get("duration_ms") or 0)
    dur_b = int(story_b.get("duration_ms") or 0)

    cat_deltas: Dict[str, Dict[str, int]] = {}
    cats_a = ta.get("by_category") or {}
    cats_b = tb.get("by_category") or {}
    for k in set(cats_a) | set(cats_b):
        va = int(cats_a.get(k) or 0)
        vb = int(cats_b.get(k) or 0)
        cat_deltas[k] = {"a": va, "b": vb, "delta": vb - va}

    md_lines = [
        f"# Harness Story Comparison: `{story_a.get('title')}` vs `{story_b.get('title')}`",
        "",
        "| Metric | Baseline (A) | Comparison (B) | Delta (B - A) |",
        "|---|---:|---:|---:|",
        f"| **Tool Calls** | {calls_a} | {calls_b} | {calls_b - calls_a:+d} |",
        f"| **Failed Calls** | {fail_a} | {fail_b} | {fail_b - fail_a:+d} |",
        f"| **Recovery Pivots** | {piv_a} | {piv_b} | {piv_b - piv_a:+d} |",
        f"| **Peak Context Tokens** | {peak_a:,} ({ca.get('peak_pct', 0)}%) | {peak_b:,} ({cb.get('peak_pct', 0)}%) | {peak_b - peak_a:+,d} |",
        f"| **Duration** | {dur_a / 1000:.1f}s | {dur_b / 1000:.1f}s | {(dur_b - dur_a) / 1000:+.1f}s |",
        f"| **Subagents Spawned** | {len(story_a.get('subagents') or [])} | {len(story_b.get('subagents') or [])} | {len(story_b.get('subagents') or []) - len(story_a.get('subagents') or []):+d} |",
    ]

    return {
        "a": {"session_id": story_a.get("session_id"), "title": story_a.get("title")},
        "b": {"session_id": story_b.get("session_id"), "title": story_b.get("title")},
        "deltas": {
            "tool_calls": calls_b - calls_a,
            "failed_calls": fail_b - fail_a,
            "pivots": piv_b - piv_a,
            "peak_context_tokens": peak_b - peak_a,
            "duration_ms": dur_b - dur_a,
            "categories": cat_deltas,
        },
        "markdown": "\n".join(md_lines),
    }
