"""Hermes Agent plugin entry point for harness-story.

Registers:
- 5 tools (`harness_story_generate`, `harness_story_inspect`, `harness_story_compare`,
  `harness_story_render`, `harness_story_list`) under toolset `harness-story`.
- 12 lifecycle hooks (`on_session_start`, `pre_llm_call`, `pre_api_request`,
  `post_api_request`, `pre_tool_call`, `post_tool_call`, `on_skill_lifecycle`,
  `subagent_start`, `subagent_stop`, `post_compaction`, `post_llm_call`, `on_session_end`).
- `/story` slash command and bundled `harness-story` skill when supported by the host context.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

TOOLSET = "harness-story"
PLUGIN_ID = "harness-story"


def ensure_package(ctx: Any = None) -> None:
    """Ensure the `harness_story` package is importable from the plugin root."""
    try:
        import harness_story  # noqa: F401
        return
    except ImportError:
        pass
    here = Path(__file__).resolve().parent
    candidates = [here]
    plugin_dir = getattr(ctx, "plugin_dir", None) if ctx is not None else None
    if plugin_dir:
        candidates.insert(0, Path(plugin_dir).resolve())
    for candidate in candidates:
        if (candidate / "harness_story").is_dir():
            s = str(candidate)
            if s not in sys.path:
                sys.path.insert(0, s)
            return


def _resolve_config(ctx: Any = None) -> Dict[str, Any]:
    """Read plugin config values via ctx.get_config(...) with env var overrides and defaults."""
    def _from_ctx(key: str, default: Any = None) -> Any:
        if ctx is not None and callable(getattr(ctx, "get_config", None)):
            try:
                val = ctx.get_config(key, default)
                if val is not None:
                    return val
            except Exception:
                pass
        return default

    model = os.environ.get("HARNESS_STORY_MODEL") or _from_ctx("model", "qwen3.8-flash-next-iq3_xxs")
    base_url = os.environ.get("HARNESS_STORY_BASE_URL")
    if base_url is None:
        base_url = _from_ctx("base_url", "")
    cw_raw = os.environ.get("HARNESS_STORY_CONTEXT_WINDOW")
    if cw_raw is None:
        cw_raw = _from_ctx("context_window", 131072)
    auto_gen = _from_ctx("auto_generate_on_session_end", True)
    storage_dir = os.environ.get("HARNESS_STORY_STORAGE_DIR") or _from_ctx("storage_dir", None)
    db_path = os.environ.get("HARNESS_STORY_DB_PATH") or _from_ctx("db_path", None)

    return {
        "model": str(model or "qwen3.8-flash-next-iq3_xxs"),
        "base_url": str(base_url or "").strip(),
        "context_window": int(cw_raw or 131072),
        "auto_generate_on_session_end": bool(auto_gen),
        "storage_dir": storage_dir,
        "db_path": db_path,
    }


def _resolve_story_path(ref: str, storage_dir: Optional[str] = None) -> Path:
    """Resolve a story reference (slug or session_id) strictly inside <storage_dir>/{stories,out}."""
    from harness_story.collector import get_storage_dir

    root = get_storage_dir(storage_dir).resolve()
    raw = (ref or "").strip()
    if not raw or "/" in raw or "\\" in raw or ".." in raw:
        raise FileNotFoundError(f"Story '{ref}' must be a story slug inside {root / 'stories'}")

    clean = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in raw)
    if not clean or clean in (".", ".."):
        raise FileNotFoundError(f"Story '{ref}' not found in {root / 'stories'}")

    stem = clean[:-5] if clean.endswith(".json") else clean
    for sub in ("stories", "out"):
        sub_dir = (root / sub).resolve()
        candidate = (sub_dir / f"{stem}.json").resolve()
        if candidate.is_relative_to(sub_dir) and candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Story '{ref}' not found in {root / 'stories'}")


# ---------------------------------------------------------------------------
# Tool Schemas
# ---------------------------------------------------------------------------

GENERATE_SCHEMA: Dict[str, Any] = {
    "name": "harness_story_generate",
    "description": (
        "Reconstruct and synthesize a comprehensive, animated session story from Hermes state.db "
        "and live hook telemetry. Produces a causal narrative of decisions, hypotheses, failures & "
        "pivots, step-by-step context window progression (5-bucket breakdown), running tool call "
        "tallies, code/system impact trails, subagent orchestration, and a self-contained animated HTML5 viewer."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Session ID from ~/.hermes/state.db, or 'latest' for the most recent active session.",
            },
            "slug": {
                "type": "string",
                "description": "Optional filename slug for saving the story JSON and HTML viewer.",
            },
            "use_llm": {
                "type": "boolean",
                "description": "Whether to run the hybrid LLM narrative pass (falls back to deterministic synthesis if false or offline). Default true.",
            },
            "context_window": {
                "type": "integer",
                "description": "Override the context window token ceiling (default 131072).",
            },
        },
        "required": [],
    },
}

INSPECT_SCHEMA: Dict[str, Any] = {
    "name": "harness_story_inspect",
    "description": (
        "Inspect a generated harness story or drill into a specific step's causal links, "
        "5-bucket context window snapshot, running tool tally, reasoning, and pivot status."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "story": {
                "type": "string",
                "description": "Story slug or session_id in the plugin storage directory.",
            },
            "step": {
                "type": "integer",
                "description": "Optional 1-based step index to inspect in full detail.",
            },
            "section": {
                "type": "string",
                "enum": ["summary", "pivots", "context", "tools", "code_impact", "chapters", "subagents"],
                "description": "Optional section to focus on when step is omitted.",
            },
        },
        "required": ["story"],
    },
}

COMPARE_SCHEMA: Dict[str, Any] = {
    "name": "harness_story_compare",
    "description": (
        "Compare two session stories side-by-side: deltas in tool call counts, error & recovery "
        "pivots, peak context window pressure, subagent fan-out, and per-category tool mix."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "story_a": {
                "type": "string",
                "description": "Baseline story slug or session_id in the plugin storage directory.",
            },
            "story_b": {
                "type": "string",
                "description": "Comparison story slug or session_id in the plugin storage directory.",
            },
        },
        "required": ["story_a", "story_b"],
    },
}

RENDER_SCHEMA: Dict[str, Any] = {
    "name": "harness_story_render",
    "description": (
        "Render or re-render a self-contained animated HTML5 story viewer from an existing story "
        "slug in the plugin storage directory, writing the HTML inside <storage>/out/."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "story": {
                "type": "string",
                "description": "Story slug or session_id in the plugin storage directory.",
            },
            "output_html": {
                "type": "string",
                "description": "Optional filename or relative path inside <storage>/out/ for the rendered HTML file.",
            },
            "title": {
                "type": "string",
                "description": "Optional custom page title for the HTML viewer.",
            },
        },
        "required": ["story"],
    },
}

LIST_SCHEMA: Dict[str, Any] = {
    "name": "harness_story_list",
    "description": (
        "List recent Hermes Agent sessions from state.db alongside already-generated story artifacts, "
        "including tool call counts, message counts, input tokens, and titles."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of sessions to return (default 15).",
            },
            "min_tool_calls": {
                "type": "integer",
                "description": "Minimum tool calls filter (default 1).",
            },
            "include_cron": {
                "type": "boolean",
                "description": "Whether to include automated cron sessions (default false).",
            },
        },
        "required": [],
    },
}


# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------

def _handle_generate(args: Dict[str, Any], ctx: Any = None, **_: Any) -> str:
    try:
        ensure_package(ctx)
        from harness_story.narrator import synthesize_narrative
        from harness_story.reconstruct import reconstruct_story, save_story
        from harness_story.render import render_story_html

        cfg = _resolve_config(ctx)
        session_id = str(args.get("session_id") or "latest").strip() or "latest"
        use_llm = bool(args.get("use_llm", True))
        context_window = int(args.get("context_window") or cfg["context_window"])

        story = reconstruct_story(
            session_id=session_id,
            db_path=cfg["db_path"],
            storage_dir=cfg["storage_dir"],
            context_window=context_window,
        )
        if args.get("slug"):
            story["slug"] = "".join(
                c if (c.isalnum() or c in "-_.") else "_"
                for c in str(args["slug"]).strip()
            )[:90]

        synthesize_narrative(
            story,
            use_llm=use_llm,
            base_url=cfg["base_url"],
            model=cfg["model"],
        )
        html_doc = render_story_html(story)
        json_path, html_path = save_story(story, html_doc, storage_dir=cfg["storage_dir"])

        return json.dumps({
            "ok": True,
            "session_id": story["session_id"],
            "slug": story["slug"],
            "title": story["title"],
            "headline": story["headline"],
            "executive_summary": story["executive_summary"],
            "narrative_source": story["narrative_source"],
            "tool_tally": {
                "total_calls": story["tool_tally"]["total_calls"],
                "failed_calls": story["tool_tally"]["failed_calls"],
                "by_category": story["tool_tally"]["by_category"],
                "by_tool": story["tool_tally"]["by_tool"],
            },
            "context_journey": {
                "context_max": story["context_journey"]["context_max"],
                "peak_tokens": story["context_journey"]["peak_tokens"],
                "peak_pct": story["context_journey"]["peak_pct"],
                "final_tokens": story["context_journey"]["final_tokens"],
                "final_pct": story["context_journey"]["final_pct"],
                "cache_read_tokens": story["context_journey"]["cache_read_tokens"],
            },
            "pivots_count": len(story.get("pivots") or []),
            "subagents_count": len(story.get("subagents") or []),
            "chapters_count": len(story.get("chapters") or []),
            "story_json": str(json_path),
            "widget_html": str(html_path),
        }, ensure_ascii=False)
    except Exception as exc:
        logger.debug("harness_story_generate failed: %s", exc, exc_info=True)
        return json.dumps({"ok": False, "error": str(exc)})


def _handle_inspect(args: Dict[str, Any], ctx: Any = None, **_: Any) -> str:
    try:
        ensure_package(ctx)
        cfg = _resolve_config(ctx)
        ref = str(args.get("story") or "").strip()
        if not ref:
            return json.dumps({"ok": False, "error": "Missing required parameter 'story'"})
        path = _resolve_story_path(ref, storage_dir=cfg["storage_dir"])
        doc = json.loads(path.read_text(encoding="utf-8"))

        step_num = args.get("step")
        if step_num is not None:
            idx = int(step_num)
            steps = doc.get("steps") or []
            match = next((s for s in steps if int(s.get("index") or 0) == idx), None)
            if not match:
                return json.dumps({
                    "ok": False,
                    "error": f"Step {idx} not found in story '{doc.get('slug')}' (1..{len(steps)})",
                })
            return json.dumps({"ok": True, "story": doc.get("slug"), "step": match}, ensure_ascii=False)

        section = str(args.get("section") or "summary").strip()
        if section == "pivots":
            return json.dumps({"ok": True, "slug": doc.get("slug"), "pivots": doc.get("pivots", [])}, ensure_ascii=False)
        if section == "context":
            return json.dumps({"ok": True, "slug": doc.get("slug"), "context_journey": doc.get("context_journey", {})}, ensure_ascii=False)
        if section == "tools":
            return json.dumps({"ok": True, "slug": doc.get("slug"), "tool_tally": doc.get("tool_tally", {})}, ensure_ascii=False)
        if section == "code_impact":
            return json.dumps({"ok": True, "slug": doc.get("slug"), "code_impact": doc.get("code_impact", [])}, ensure_ascii=False)
        if section == "chapters":
            return json.dumps({"ok": True, "slug": doc.get("slug"), "chapters": doc.get("chapters", [])}, ensure_ascii=False)
        if section == "subagents":
            return json.dumps({"ok": True, "slug": doc.get("slug"), "subagents": doc.get("subagents", [])}, ensure_ascii=False)

        cj = dict(doc.get("context_journey") or {})
        cj.pop("timeline", None)
        return json.dumps({
            "ok": True,
            "session_id": doc.get("session_id"),
            "slug": doc.get("slug"),
            "title": doc.get("title"),
            "headline": doc.get("headline"),
            "executive_summary": doc.get("executive_summary"),
            "causal_takeaways": doc.get("causal_takeaways"),
            "context_commentary": doc.get("context_commentary"),
            "tool_tally": {k: v for k, v in (doc.get("tool_tally") or {}).items() if k != "running_series"},
            "context_journey": cj,
            "pivots": doc.get("pivots"),
            "chapters": doc.get("chapters"),
            "subagents": doc.get("subagents"),
        }, ensure_ascii=False)
    except Exception as exc:
        logger.debug("harness_story_inspect failed: %s", exc, exc_info=True)
        return json.dumps({"ok": False, "error": str(exc)})


def _handle_compare(args: Dict[str, Any], ctx: Any = None, **_: Any) -> str:
    try:
        ensure_package(ctx)
        from harness_story.narrator import compare_stories

        cfg = _resolve_config(ctx)
        ref_a = str(args.get("story_a") or "").strip()
        ref_b = str(args.get("story_b") or "").strip()
        if not ref_a or not ref_b:
            return json.dumps({"ok": False, "error": "Both 'story_a' and 'story_b' are required"})

        path_a = _resolve_story_path(ref_a, storage_dir=cfg["storage_dir"])
        path_b = _resolve_story_path(ref_b, storage_dir=cfg["storage_dir"])
        doc_a = json.loads(path_a.read_text(encoding="utf-8"))
        doc_b = json.loads(path_b.read_text(encoding="utf-8"))
        diff = compare_stories(doc_a, doc_b)
        return json.dumps({"ok": True, **diff}, ensure_ascii=False)
    except Exception as exc:
        logger.debug("harness_story_compare failed: %s", exc, exc_info=True)
        return json.dumps({"ok": False, "error": str(exc)})


def _handle_render(args: Dict[str, Any], ctx: Any = None, **_: Any) -> str:
    try:
        ensure_package(ctx)
        from harness_story.collector import get_storage_dir
        from harness_story.render import render_story_html

        cfg = _resolve_config(ctx)
        ref = str(args.get("story") or "").strip()
        if not ref:
            return json.dumps({"ok": False, "error": "Missing required parameter 'story'"})
        path = _resolve_story_path(ref, storage_dir=cfg["storage_dir"])
        doc = json.loads(path.read_text(encoding="utf-8"))
        html_doc = render_story_html(doc, title=args.get("title"))

        root = get_storage_dir(cfg["storage_dir"]).resolve()
        out_dir = (root / "out").resolve()
        out_arg = str(args.get("output_html") or "").strip()
        if out_arg:
            raw_out = Path(out_arg)
            candidate = (raw_out if raw_out.is_absolute() else (out_dir / raw_out)).resolve()
            if not candidate.is_relative_to(out_dir) or candidate == out_dir:
                return json.dumps({
                    "ok": False,
                    "error": f"output_html must resolve inside {out_dir}",
                })
            if candidate.suffix.lower() != ".html":
                candidate = candidate.with_suffix(".html")
            out_path = candidate
        else:
            out_path = (out_dir / f"{doc.get('slug') or path.stem}.html").resolve()

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_doc, encoding="utf-8")

        return json.dumps({
            "ok": True,
            "slug": doc.get("slug"),
            "story_json": str(path),
            "widget_html": str(out_path),
            "steps_count": len(doc.get("steps") or []),
            "tool_calls": (doc.get("tool_tally") or {}).get("total_calls", 0),
        }, ensure_ascii=False)
    except Exception as exc:
        logger.debug("harness_story_render failed: %s", exc, exc_info=True)
        return json.dumps({"ok": False, "error": str(exc)})


def _handle_list(args: Dict[str, Any], ctx: Any = None, **_: Any) -> str:
    try:
        ensure_package(ctx)
        from harness_story.collector import get_storage_dir
        from harness_story.reconstruct import list_recent_sessions

        cfg = _resolve_config(ctx)
        limit = int(args.get("limit") or 15)
        min_tools = int(args.get("min_tool_calls") if args.get("min_tool_calls") is not None else 1)
        include_cron = bool(args.get("include_cron", False))

        sessions = list_recent_sessions(
            db_path=cfg["db_path"],
            limit=limit,
            include_cron=include_cron,
            min_tool_calls=min_tools,
        )
        root = get_storage_dir(cfg["storage_dir"])
        saved_stories = []
        stories_dir = root / "stories"
        if stories_dir.is_dir():
            for jfile in sorted(stories_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
                try:
                    meta = json.loads(jfile.read_text(encoding="utf-8"))
                    saved_stories.append({
                        "slug": meta.get("slug") or jfile.stem,
                        "session_id": meta.get("session_id"),
                        "title": meta.get("title"),
                        "headline": meta.get("headline"),
                        "tool_calls": (meta.get("tool_tally") or {}).get("total_calls", 0),
                        "peak_context_tokens": (meta.get("context_journey") or {}).get("peak_tokens", 0),
                        "story_json": str(jfile),
                        "widget_html": str(jfile.with_suffix(".html")),
                    })
                except Exception:
                    continue

        return json.dumps({
            "ok": True,
            "sessions": sessions,
            "saved_stories": saved_stories,
        }, ensure_ascii=False)
    except Exception as exc:
        logger.debug("harness_story_list failed: %s", exc, exc_info=True)
        return json.dumps({"ok": False, "error": str(exc)})


def _bind(fn: Callable[..., str], ctx: Any) -> Callable[..., str]:
    def _wrapped(args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
        return fn(args or {}, ctx=ctx, **kwargs)
    return _wrapped


def _slash_story_command(raw_args: str = "", ctx: Any = None, **_: Any) -> str:
    """Handler for the `/story` in-session slash command."""
    tokens = (raw_args or "").strip().split()
    session_id = tokens[0] if tokens else "latest"
    use_llm = "--no-llm" not in tokens
    res_raw = _handle_generate({"session_id": session_id, "use_llm": use_llm}, ctx=ctx)
    try:
        res = json.loads(res_raw)
    except ValueError:
        return res_raw
    if not res.get("ok"):
        return f"Harness Story error: {res.get('error')}"
    return (
        f"### {res.get('title')}\n"
        f"**{res.get('headline')}**\n\n"
        f"{res.get('executive_summary')}\n\n"
        f"- **Tool Calls**: {res['tool_tally']['total_calls']} ({res['tool_tally']['failed_calls']} errors, {res['pivots_count']} pivots)\n"
        f"- **Context Peak**: {res['context_journey']['peak_tokens']:,} tokens ({res['context_journey']['peak_pct']}% of {res['context_journey']['context_max']:,})\n"
        f"- **Animated HTML Viewer**: `{res.get('widget_html')}`\n"
        f"- **Story JSON**: `{res.get('story_json')}`"
    )


def register(ctx: Any) -> None:
    """Register harness-story tools, lifecycle hooks, slash command, and skill."""
    ensure_package(ctx)
    from harness_story.collector import HookCollector

    cfg = _resolve_config(ctx)

    # 1. Register the 5 tools declared in plugin.yaml
    tools = [
        ("harness_story_generate", GENERATE_SCHEMA, _handle_generate),
        ("harness_story_inspect", INSPECT_SCHEMA, _handle_inspect),
        ("harness_story_compare", COMPARE_SCHEMA, _handle_compare),
        ("harness_story_render", RENDER_SCHEMA, _handle_render),
        ("harness_story_list", LIST_SCHEMA, _handle_list),
    ]
    for name, schema, fn in tools:
        ctx.register_tool(
            name=name,
            toolset=TOOLSET,
            schema=schema,
            handler=_bind(fn, ctx),
        )

    # 2. Register the 12 lifecycle hooks declared in plugin.yaml
    def _auto_on_end(session_id: str) -> None:
        if not cfg.get("auto_generate_on_session_end", True):
            return
        try:
            _handle_generate({"session_id": session_id, "use_llm": False}, ctx=ctx)
        except Exception:
            pass

    collector = HookCollector(
        ctx=ctx,
        storage_dir=cfg.get("storage_dir"),
        on_session_end_cb=_auto_on_end,
    )
    hooks = [
        ("on_session_start", collector.on_session_start),
        ("pre_llm_call", collector.on_pre_llm_call),
        ("pre_api_request", collector.on_pre_api_request),
        ("post_api_request", collector.on_post_api_request),
        ("pre_tool_call", collector.on_pre_tool_call),
        ("post_tool_call", collector.on_post_tool_call),
        ("on_skill_lifecycle", collector.on_skill_lifecycle),
        ("subagent_start", collector.on_subagent_start),
        ("subagent_stop", collector.on_subagent_stop),
        ("post_compaction", collector.on_post_compaction),
        ("post_llm_call", collector.on_post_llm_call),
        ("on_session_end", collector.on_session_end),
    ]
    for hook_name, callback in hooks:
        ctx.register_hook(hook_name, callback)

    # 3. Optional slash command and bundled skill registration
    if hasattr(ctx, "register_command"):
        try:
            ctx.register_command(
                name="story",
                description="Generate an animated story of a Hermes session (/story [session_id|latest] [--no-llm])",
                handler=lambda raw_args="", **kw: _slash_story_command(raw_args, ctx=ctx, **kw),
            )
        except Exception:
            pass

    if hasattr(ctx, "register_skill"):
        skill_md = Path(__file__).resolve().parent / "skills" / "harness-story" / "SKILL.md"
        if skill_md.is_file():
            try:
                ctx.register_skill("harness-story", str(skill_md))
            except Exception:
                pass
