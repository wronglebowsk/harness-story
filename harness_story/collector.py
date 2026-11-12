"""Live lifecycle hook collector for harness-story.

Subscribes to Hermes Agent's lifecycle hooks and records high-resolution telemetry frames
into ``plugin_data_dir("harness-story") / "live" / "<session_id>.jsonl"``.

Design rules:
- Every hook callback accepts ``**kwargs`` for forward compatibility with additive fields.
- Every hook callback is fail-open and never raises or blocks the agent loop.
- Writes only to durable ``plugin_data_dir("harness-story")``, never to the plugin install tree.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .models import clip_text

PLUGIN_ID = "harness-story"
_WRITE_LOCK = threading.Lock()


def get_storage_dir(custom_dir: Optional[str] = None) -> Path:
    """Resolve the durable data directory for harness-story."""
    if custom_dir:
        root = Path(custom_dir)
    else:
        try:
            from plugins.plugin_storage import plugin_data_dir
            root = plugin_data_dir(PLUGIN_ID)
        except Exception:
            from hermes_constants import get_hermes_home
            root = get_hermes_home() / "plugin-data" / PLUGIN_ID
    for sub in ("live", "stories", "out"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def _safe_session_filename(session_id: str) -> str:
    clean = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (session_id or "").strip())
    return clean[:120] or "unknown_session"


def append_live_event(session_id: str, event_kind: str, payload: Dict[str, Any],
                      storage_dir: Optional[str] = None) -> None:
    """Append one JSONL telemetry frame for *session_id* (best-effort, thread-safe)."""
    if not session_id:
        return
    try:
        root = get_storage_dir(storage_dir)
        fname = _safe_session_filename(session_id)
        path = root / "live" / f"{fname}.jsonl"
        record = {
            "ts": time.time(),
            "session_id": session_id,
            "event": event_kind,
            **payload,
        }
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with _WRITE_LOCK:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


def read_live_events(session_id: str, storage_dir: Optional[str] = None) -> list[Dict[str, Any]]:
    """Read recorded live hook frames for *session_id*, or [] if none exist."""
    if not session_id:
        return []
    try:
        root = get_storage_dir(storage_dir)
        fname = _safe_session_filename(session_id)
        path = root / "live" / f"{fname}.jsonl"
        if not path.is_file():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows
    except Exception:
        return []


class HookCollector:
    """Stateful/durable observer for Hermes lifecycle hooks."""

    def __init__(self, ctx: Any = None, storage_dir: Optional[str] = None,
                 on_session_end_cb: Optional[Callable[[str], None]] = None) -> None:
        self.ctx = ctx
        self.storage_dir = storage_dir
        self.on_session_end_cb = on_session_end_cb

    def on_session_start(self, **kwargs: Any) -> None:
        sid = str(kwargs.get("session_id") or "")
        append_live_event(sid, "on_session_start", {
            "model": kwargs.get("model"),
            "platform": kwargs.get("platform"),
        }, self.storage_dir)

    def on_pre_llm_call(self, **kwargs: Any) -> None:
        sid = str(kwargs.get("session_id") or "")
        user_msg = kwargs.get("user_message")
        history = kwargs.get("conversation_history")
        append_live_event(sid, "pre_llm_call", {
            "turn_id": kwargs.get("turn_id"),
            "task_id": kwargs.get("task_id"),
            "model": kwargs.get("model"),
            "platform": kwargs.get("platform"),
            "parent_session_id": kwargs.get("parent_session_id"),
            "is_first_turn": bool(kwargs.get("is_first_turn")),
            "user_message_preview": clip_text(user_msg, 200),
            "history_count": len(history) if isinstance(history, list) else 0,
        }, self.storage_dir)

    def on_pre_api_request(self, **kwargs: Any) -> None:
        sid = str(kwargs.get("session_id") or "")
        sys_prompt = kwargs.get("system_prompt")
        mw_trace = kwargs.get("middleware_trace")
        append_live_event(sid, "pre_api_request", {
            "turn_id": kwargs.get("turn_id"),
            "api_request_id": kwargs.get("api_request_id"),
            "api_call_count": kwargs.get("api_call_count"),
            "retry_count": kwargs.get("retry_count"),
            "model": kwargs.get("model"),
            "provider": kwargs.get("provider"),
            "message_count": kwargs.get("message_count"),
            "tool_count": kwargs.get("tool_count"),
            "approx_input_tokens": kwargs.get("approx_input_tokens"),
            "request_char_count": kwargs.get("request_char_count"),
            "system_prompt_chars": len(sys_prompt) if isinstance(sys_prompt, str) else 0,
            "max_tokens": kwargs.get("max_tokens"),
            "started_at": kwargs.get("started_at"),
            "middleware_trace": list(mw_trace) if isinstance(mw_trace, list) else [],
        }, self.storage_dir)

    def on_post_api_request(self, **kwargs: Any) -> None:
        sid = str(kwargs.get("session_id") or "")
        usage = kwargs.get("usage")
        started_at = kwargs.get("started_at")
        first_chunk_at = kwargs.get("first_chunk_at")
        ttfb_ms = None
        if isinstance(started_at, (int, float)) and isinstance(first_chunk_at, (int, float)) and first_chunk_at >= started_at:
            ttfb_ms = int(round((first_chunk_at - started_at) * 1000))
        append_live_event(sid, "post_api_request", {
            "turn_id": kwargs.get("turn_id"),
            "api_request_id": kwargs.get("api_request_id"),
            "api_call_count": kwargs.get("api_call_count"),
            "api_duration_s": kwargs.get("api_duration"),
            "ttfb_ms": ttfb_ms,
            "finish_reason": kwargs.get("finish_reason"),
            "message_count": kwargs.get("message_count"),
            "context_length": kwargs.get("context_length"),
            "usage": usage if isinstance(usage, dict) else {},
            "assistant_content_chars": kwargs.get("assistant_content_chars"),
            "assistant_tool_call_count": kwargs.get("assistant_tool_call_count"),
        }, self.storage_dir)

    def on_pre_tool_call(self, **kwargs: Any) -> None:
        sid = str(kwargs.get("session_id") or "")
        args = kwargs.get("args")
        append_live_event(sid, "pre_tool_call", {
            "turn_id": kwargs.get("turn_id"),
            "tool_call_id": kwargs.get("tool_call_id"),
            "api_request_id": kwargs.get("api_request_id"),
            "tool_name": kwargs.get("tool_name"),
            "args_preview": clip_text(json.dumps(args, default=str) if isinstance(args, dict) else str(args), 240),
        }, self.storage_dir)

    def on_post_tool_call(self, **kwargs: Any) -> None:
        sid = str(kwargs.get("session_id") or "")
        result = kwargs.get("result")
        res_str = result if isinstance(result, str) else json.dumps(result, default=str)
        append_live_event(sid, "post_tool_call", {
            "turn_id": kwargs.get("turn_id"),
            "tool_call_id": kwargs.get("tool_call_id"),
            "api_request_id": kwargs.get("api_request_id"),
            "tool_name": kwargs.get("tool_name"),
            "duration_ms": kwargs.get("duration_ms"),
            "status": kwargs.get("status"),
            "error_type": kwargs.get("error_type"),
            "error_message": clip_text(kwargs.get("error_message"), 200),
            "result_chars": len(res_str or ""),
            "result_preview": clip_text(res_str, 240),
        }, self.storage_dir)

    def on_skill_lifecycle(self, **kwargs: Any) -> None:
        sid = str(kwargs.get("session_id") or "")
        append_live_event(sid, "on_skill_lifecycle", {
            "action": kwargs.get("action"),
            "skill_name": kwargs.get("skill_name"),
            "provenance": kwargs.get("provenance"),
        }, self.storage_dir)

    def on_subagent_start(self, **kwargs: Any) -> None:
        sid = str(kwargs.get("parent_session_id") or kwargs.get("session_id") or "")
        append_live_event(sid, "subagent_start", {
            "parent_turn_id": kwargs.get("parent_turn_id"),
            "child_session_id": kwargs.get("child_session_id"),
            "goal": clip_text(kwargs.get("goal") or kwargs.get("prompt"), 200),
            "role": kwargs.get("child_role") or kwargs.get("role"),
        }, self.storage_dir)

    def on_subagent_stop(self, **kwargs: Any) -> None:
        sid = str(kwargs.get("parent_session_id") or kwargs.get("session_id") or "")
        history = kwargs.get("tool_call_history")
        append_live_event(sid, "subagent_stop", {
            "parent_turn_id": kwargs.get("parent_turn_id"),
            "child_session_id": kwargs.get("child_session_id"),
            "child_role": kwargs.get("child_role"),
            "child_status": kwargs.get("child_status"),
            "child_summary": clip_text(kwargs.get("child_summary"), 260),
            "duration_ms": kwargs.get("duration_ms"),
            "tool_call_count": len(history) if isinstance(history, list) else 0,
        }, self.storage_dir)

    def on_post_compaction(self, **kwargs: Any) -> None:
        sid = str(kwargs.get("session_id") or "")
        append_live_event(sid, "post_compaction", {
            "old_session_id": kwargs.get("old_session_id"),
            "kind": kwargs.get("kind"),
            "reason": kwargs.get("reason"),
            "before_tokens": kwargs.get("before_tokens"),
            "after_tokens": kwargs.get("after_tokens"),
            "messages_removed": kwargs.get("messages_removed"),
        }, self.storage_dir)

    def on_post_llm_call(self, **kwargs: Any) -> None:
        sid = str(kwargs.get("session_id") or "")
        resp = kwargs.get("assistant_response")
        append_live_event(sid, "post_llm_call", {
            "turn_id": kwargs.get("turn_id"),
            "task_id": kwargs.get("task_id"),
            "model": kwargs.get("model"),
            "response_chars": len(resp) if isinstance(resp, str) else 0,
            "response_preview": clip_text(resp, 200),
        }, self.storage_dir)

    def on_session_end(self, **kwargs: Any) -> None:
        sid = str(kwargs.get("session_id") or "")
        append_live_event(sid, "on_session_end", {
            "reason": kwargs.get("reason"),
            "platform": kwargs.get("platform"),
        }, self.storage_dir)
        if sid and callable(self.on_session_end_cb):
            try:
                self.on_session_end_cb(sid)
            except Exception:
                pass
