"""harness-story dashboard backend, mounted at /api/plugins/harness-story/.

Serves stored session stories, animated HTML5 story viewers, recent sessions from
`~/.hermes/state.db`, and accepts generate / compare requests from the Desktop pane
or web dashboard.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter()

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))


def _fresh_harness_story() -> None:
    """Ensure the long-running plugin host uses the latest harness_story modules on disk."""
    import importlib
    for mod_name in (
        "harness_story.models",
        "harness_story.collector",
        "harness_story.reconstruct",
        "harness_story.narrator",
        "harness_story.render",
        "harness_story",
    ):
        if mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
            except Exception:
                pass


def _storage() -> Path:
    from harness_story.collector import get_storage_dir
    return get_storage_dir()


def _safe(slug: str) -> str:
    if not slug or "/" in slug or "\\" in slug or slug.startswith(".") or ".." in slug:
        raise HTTPException(status_code=400, detail="bad slug")
    return slug


def _plugin_settings() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config_readonly
        cfg = load_config_readonly() or {}
        return (
            (((cfg.get("plugins") or {}).get("entries") or {})
             .get("harness-story") or {}).get("settings")
            or {}
        )
    except Exception:
        return {}


@router.get("/health")
def health() -> Dict[str, Any]:
    root = _storage()
    stories_dir = root / "stories"
    return {
        "ok": True,
        "stories_dir": str(stories_dir),
        "stories": len(list(stories_dir.glob("*.json"))),
    }


@router.get("/stories")
def stories(limit: int = 20) -> Dict[str, Any]:
    from harness_story.reconstruct import list_recent_sessions

    root = _storage()
    out = []
    for path in sorted((root / "stories").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        tally = doc.get("tool_tally") or {}
        cj = doc.get("context_journey") or {}
        out.append({
            "slug": path.stem,
            "session_id": doc.get("session_id"),
            "title": doc.get("title"),
            "headline": doc.get("headline"),
            "model": doc.get("model"),
            "tool_calls": tally.get("total_calls", 0),
            "failed_calls": tally.get("failed_calls", 0),
            "pivots": len(doc.get("pivots") or []),
            "subagents": len(doc.get("subagents") or []),
            "peak_tokens": cj.get("peak_tokens", 0),
            "peak_pct": cj.get("peak_pct", 0.0),
            "context_max": cj.get("context_max", 131072),
            "narrative_source": doc.get("narrative_source", "deterministic"),
            "modified": path.stat().st_mtime,
        })
    recent = list_recent_sessions(limit=limit, include_cron=False, min_tool_calls=1)
    return {"stories": out, "recent_sessions": recent}


@router.get("/stories/{slug}.json")
def story_json(slug: str) -> Dict[str, Any]:
    clean = _safe(slug)
    path = _storage() / "stories" / f"{clean}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no such story")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/stories/{slug}.html", response_class=HTMLResponse)
def story_html(slug: str) -> str:
    clean = _safe(slug)
    root = _storage()
    for candidate in (root / "out" / f"{clean}.html", root / "stories" / f"{clean}.html"):
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    src = root / "stories" / f"{clean}.json"
    if not src.exists():
        raise HTTPException(status_code=404, detail="no such story")
    from harness_story.render import render_story_html
    markup = render_story_html(json.loads(src.read_text(encoding="utf-8")))
    cached = root / "out" / f"{clean}.html"
    cached.write_text(markup, encoding="utf-8")
    return markup


@router.post("/generate")
def generate(body: Dict[str, Any]) -> Dict[str, Any]:
    _fresh_harness_story()
    from harness_story.narrator import synthesize_narrative
    from harness_story.reconstruct import reconstruct_story, save_story
    from harness_story.render import render_story_html

    session_id = str(body.get("session_id") or "latest").strip() or "latest"
    use_llm = bool(body.get("use_llm", True))
    settings = _plugin_settings()
    model = str(body.get("model") or settings.get("model", "qwen3.8-flash-next-iq3_xxs"))
    base_url = str(body.get("base_url") or settings.get("base_url", "")).strip()
    context_window = int(body.get("context_window") or settings.get("context_window", 131072))
    db_path = body.get("db_path")

    try:
        story = reconstruct_story(
            session_id=session_id,
            db_path=db_path,
            storage_dir=str(_storage()),
            context_window=context_window,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if body.get("slug"):
        story["slug"] = _safe(str(body["slug"]).strip())

    synthesize_narrative(
        story,
        use_llm=use_llm,
        base_url=base_url,
        model=model,
    )
    html_doc = render_story_html(story)
    jpath, hpath = save_story(story, html_doc, storage_dir=str(_storage()))
    return {
        "ok": True,
        "slug": story["slug"],
        "session_id": story["session_id"],
        "title": story["title"],
        "headline": story["headline"],
        "narrative_source": story["narrative_source"],
        "tool_calls": story["tool_tally"]["total_calls"],
        "pivots": len(story.get("pivots") or []),
        "peak_tokens": story["context_journey"]["peak_tokens"],
        "peak_pct": story["context_journey"]["peak_pct"],
        "story_json": str(jpath),
        "widget_html": str(hpath),
    }


@router.post("/compare")
def compare(body: Dict[str, Any]) -> Dict[str, Any]:
    from harness_story.narrator import compare_stories

    slug_a = _safe(str(body.get("a") or body.get("story_a") or "").strip())
    slug_b = _safe(str(body.get("b") or body.get("story_b") or "").strip())
    root = _storage()
    pa = root / "stories" / f"{slug_a}.json"
    pb = root / "stories" / f"{slug_b}.json"
    if not pa.exists() or not pb.exists():
        raise HTTPException(status_code=404, detail="one or both stories not found")
    doc_a = json.loads(pa.read_text(encoding="utf-8"))
    doc_b = json.loads(pb.read_text(encoding="utf-8"))
    return {"ok": True, **compare_stories(doc_a, doc_b)}
