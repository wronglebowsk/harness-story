"""harness_story — Comprehensive animated session storytelling for Hermes Agent."""
from __future__ import annotations

from .collector import HookCollector, append_live_event, get_storage_dir, read_live_events
from .models import (
    CATEGORY_LABELS,
    TOOL_CATEGORIES,
    TOOL_VERBS,
    CodeImpactEntry,
    ContextSnapshot,
    StoryChapter,
    StoryStep,
    SubagentBranch,
    clip_text,
    describe_tool_call,
    estimate_tokens,
)
from .narrator import LocalOpenAI, build_deterministic_insights, compare_stories, synthesize_narrative
from .reconstruct import list_recent_sessions, pack_lanes, reconstruct_story, resolve_state_db, save_story
from .render import render_story_html

__version__ = "0.1.0"

__all__ = [
    "CATEGORY_LABELS",
    "CodeImpactEntry",
    "ContextSnapshot",
    "HookCollector",
    "LocalOpenAI",
    "StoryChapter",
    "StoryStep",
    "SubagentBranch",
    "TOOL_CATEGORIES",
    "TOOL_VERBS",
    "__version__",
    "append_live_event",
    "build_deterministic_insights",
    "clip_text",
    "compare_stories",
    "describe_tool_call",
    "estimate_tokens",
    "get_storage_dir",
    "list_recent_sessions",
    "pack_lanes",
    "read_live_events",
    "reconstruct_story",
    "render_story_html",
    "resolve_state_db",
    "save_story",
    "synthesize_narrative",
]
