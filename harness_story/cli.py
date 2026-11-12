"""CLI interface for harness-story.

Usage:
    python3 -m harness_story.cli list [--limit 15]
    python3 -m harness_story.cli generate [--session <id|latest>] [--no-llm] [--out <dir>]
    python3 -m harness_story.cli inspect <story.json> [--step <n>]
    python3 -m harness_story.cli compare <a.json> <b.json>
    python3 -m harness_story.cli render <story.json> [--html <out.html>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .collector import get_storage_dir
from .narrator import compare_stories, synthesize_narrative
from .reconstruct import list_recent_sessions, reconstruct_story, save_story
from .render import render_story_html


def cmd_list(args: argparse.Namespace) -> int:
    sessions = list_recent_sessions(
        db_path=args.db,
        limit=args.limit,
        include_cron=not args.no_cron,
        min_tool_calls=args.min_tools,
    )
    if args.json:
        print(json.dumps({"sessions": sessions}, indent=2))
        return 0
    print(f"{'SESSION ID':<38}  {'TOOLS':>5}  {'MSGS':>5}  {'IN TOK':>9}  {'SOURCE':<8}  TITLE")
    print("-" * 100)
    for s in sessions:
        sid = str(s.get("id") or "")[:38]
        tools = int(s.get("tool_call_count") or 0)
        msgs = int(s.get("message_count") or 0)
        in_tok = int(s.get("input_tokens") or 0)
        src = str(s.get("source") or "")[:8]
        title = str(s.get("title") or "(untitled)")[:42]
        print(f"{sid:<38}  {tools:>5}  {msgs:>5}  {in_tok:>9,}  {src:<8}  {title}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    story = reconstruct_story(
        session_id=args.session,
        db_path=args.db,
        storage_dir=args.storage_dir,
        context_window=args.context_window,
    )
    if args.slug:
        story["slug"] = args.slug
    synthesize_narrative(
        story,
        use_llm=not args.no_llm,
        base_url=args.base_url,
        model=args.model,
    )
    html_doc = render_story_html(story)
    if args.out_dir:
        out_root = Path(args.out_dir)
        out_root.mkdir(parents=True, exist_ok=True)
        slug = story["slug"]
        jpath = out_root / f"{slug}.json"
        hpath = out_root / f"{slug}.html"
        jpath.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
        hpath.write_text(html_doc, encoding="utf-8")
    else:
        jpath, hpath = save_story(story, html_doc, storage_dir=args.storage_dir)

    print(json.dumps({
        "ok": True,
        "session_id": story["session_id"],
        "slug": story["slug"],
        "title": story["title"],
        "headline": story["headline"],
        "narrative_source": story["narrative_source"],
        "tool_calls": story["tool_tally"]["total_calls"],
        "pivots": len(story["pivots"]),
        "peak_context_tokens": story["context_journey"]["peak_tokens"],
        "peak_context_pct": story["context_journey"]["peak_pct"],
        "story_json": str(jpath),
        "widget_html": str(hpath),
    }, indent=2))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    doc = json.loads(Path(args.story).read_text(encoding="utf-8"))
    if args.step is not None:
        steps = doc.get("steps") or []
        match = next((s for s in steps if s.get("index") == args.step), None)
        if not match:
            print(json.dumps({"ok": False, "error": f"Step {args.step} not found"}, indent=2))
            return 1
        print(json.dumps({"ok": True, "step": match}, indent=2))
        return 0
    print(json.dumps({
        "ok": True,
        "session_id": doc.get("session_id"),
        "title": doc.get("title"),
        "headline": doc.get("headline"),
        "executive_summary": doc.get("executive_summary"),
        "tool_tally": doc.get("tool_tally"),
        "context_journey": {k: v for k, v in (doc.get("context_journey") or {}).items() if k != "timeline"},
        "pivots": doc.get("pivots"),
        "chapters": doc.get("chapters"),
    }, indent=2))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    a = json.loads(Path(args.a).read_text(encoding="utf-8"))
    b = json.loads(Path(args.b).read_text(encoding="utf-8"))
    res = compare_stories(a, b)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(res["markdown"])
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    src = Path(args.story)
    doc = json.loads(src.read_text(encoding="utf-8"))
    html_doc = render_story_html(doc, title=args.title)
    out = Path(args.html) if args.html else src.with_suffix(".html")
    out.write_text(html_doc, encoding="utf-8")
    print(json.dumps({"ok": True, "widget_html": str(out), "steps": len(doc.get("steps") or [])}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="harness-story", description="Hermes Agent Session Storyteller & Causal Telemetry")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List recent sessions from Hermes state.db")
    p_list.add_argument("--db", default=None, help="Path to state.db")
    p_list.add_argument("--limit", type=int, default=15)
    p_list.add_argument("--min-tools", type=int, default=1)
    p_list.add_argument("--no-cron", action="store_true")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_gen = sub.add_parser("generate", help="Generate story JSON + animated HTML viewer for a session")
    p_gen.add_argument("--session", default="latest", help="Session ID or 'latest'")
    p_gen.add_argument("--slug", default=None, help="Custom output slug")
    p_gen.add_argument("--db", default=None, help="Path to state.db")
    p_gen.add_argument("--storage-dir", default=None)
    p_gen.add_argument("--out-dir", default=None)
    p_gen.add_argument("--context-window", type=int, default=131072)
    p_gen.add_argument("--no-llm", action="store_true", help="Skip LLM narrative pass and use deterministic synthesis")
    p_gen.add_argument("--base-url", default="", help="Optional OpenAI-compatible endpoint URL for LLM narrative pass")
    p_gen.add_argument("--model", default="qwen3.8-flash-next-iq3_xxs")
    p_gen.set_defaults(func=cmd_generate)

    p_insp = sub.add_parser("inspect", help="Inspect a generated story JSON or a specific step")
    p_insp.add_argument("story", help="Path to story JSON")
    p_insp.add_argument("--step", type=int, default=None, help="1-based step index to inspect")
    p_insp.set_defaults(func=cmd_inspect)

    p_cmp = sub.add_parser("compare", help="Compare two story JSON files")
    p_cmp.add_argument("a", help="Baseline story JSON")
    p_cmp.add_argument("b", help="Comparison story JSON")
    p_cmp.add_argument("--json", action="store_true")
    p_cmp.set_defaults(func=cmd_compare)

    p_ren = sub.add_parser("render", help="Render a story JSON into a self-contained animated HTML viewer")
    p_ren.add_argument("story", help="Path to story JSON")
    p_ren.add_argument("--html", default=None, help="Output HTML path")
    p_ren.add_argument("--title", default=None)
    p_ren.set_defaults(func=cmd_render)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
