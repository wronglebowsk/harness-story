"""Data models and vocabulary for harness-story.

Defines the structured representation of a Hermes Agent session story:
- Step-by-step context window progression & 5-bucket breakdown
- Natural human-language titles, layperson tool indicators & animation cues
- Explicit "Hidden Hermes Context Load" step (skills, connectors, tools, memory)
- Running and total tool call tallies
- Causal links between reads, searches, edits, verifications, failures, and pivots
- Story chapters, code impact trails, and subagent orchestration trees
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ------------------------------------------------------------------ vocabulary

TOOL_VERBS: Dict[str, str] = {
    "read_file": "read",
    "read_files": "read",
    "view_file": "read",
    "open_file": "read",
    "read": "read",
    "write_file": "wrote",
    "create_file": "wrote",
    "append_file": "wrote",
    "patch": "edited",
    "edit_file": "edited",
    "str_replace": "edited",
    "multi_edit": "edited",
    "terminal": "ran",
    "shell": "ran",
    "bash": "ran",
    "exec": "ran",
    "execute_code": "executed script",
    "web_search": "searched web for",
    "web_extract": "extracted page",
    "skill_view": "loaded skill",
    "skill_manage": "updated skill",
    "delegate_task": "delegated to subagent",
    "todo_list": "updated plan",
    "local_recall": "recalled memory",
    "memory": "updated memory",
    "session_search": "searched past sessions",
    "image_generate": "generated image",
    "vision_analyze": "analyzed image",
    "computer_use": "controlled desktop",
    "clarify": "asked user",
    "cronjob_manage": "scheduled cron",
    "process_manage": "managed process",
    "read_terminal": "read terminal",
    "desktop_preview": "opened preview",
}

TOOL_CATEGORIES: Dict[str, str] = {
    "read_file": "explore",
    "read_files": "explore",
    "view_file": "explore",
    "open_file": "explore",
    "read": "explore",
    "web_search": "explore",
    "web_extract": "explore",
    "vision_analyze": "explore",
    "terminal": "execute",
    "shell": "execute",
    "bash": "execute",
    "exec": "execute",
    "execute_code": "execute",
    "process_manage": "execute",
    "read_terminal": "execute",
    "computer_use": "execute",
    "write_file": "mutate",
    "create_file": "mutate",
    "append_file": "mutate",
    "patch": "mutate",
    "edit_file": "mutate",
    "str_replace": "mutate",
    "multi_edit": "mutate",
    "skill_view": "knowledge",
    "skill_manage": "knowledge",
    "local_recall": "knowledge",
    "memory": "knowledge",
    "session_search": "knowledge",
    "delegate_task": "orchestrate",
    "todo_list": "orchestrate",
    "clarify": "orchestrate",
    "cronjob_manage": "orchestrate",
    "desktop_preview": "orchestrate",
}

CATEGORY_LABELS: Dict[str, str] = {
    "explore": "Explore & Read",
    "execute": "Execute & Test",
    "mutate": "Write & Edit",
    "knowledge": "Skills & Memory",
    "orchestrate": "Orchestrate & Plan",
    "external": "MCP & External",
}

TARGET_KEYS = (
    "path",
    "file_path",
    "file",
    "command",
    "query",
    "url",
    "skill",
    "name",
    "goal",
    "pattern",
    "prompt",
    "action",
    "target",
    "title",
    "question",
)

_TEST_CMD_RE = re.compile(
    r"\b(pytest|unittest|node\s+--check|node\s+\S*test|npm\s+test|pnpm\s+test|cargo\s+test|go\s+test|bash\s+\S*run\.sh|hermes\s+plugins\s+validate|hermes\s+plugins\s+doctor)\b",
    re.IGNORECASE,
)

_SEARCH_CMD_RE = re.compile(
    r"^\s*(grep|rg|find|ls|cat|head|tail|git\s+status|git\s+diff|git\s+log)\b",
    re.IGNORECASE,
)

_FILE_PATH_RE = re.compile(r"(?:[a-zA-Z0-9_.-]+/)+[a-zA-Z0-9_.-]+\.[a-zA-Z0-9]{1,8}\b")


def clip_text(value: Any, max_len: int = 120) -> str:
    """Normalize whitespace and clip string to max_len."""
    if value is None:
        return ""
    raw = re.sub(r"\s+", " ", str(value)).strip()
    if len(raw) <= max_len:
        return raw
    return raw[: max_len - 1].rstrip() + "…"


def estimate_tokens(text_or_obj: Any) -> int:
    """Fast, deterministic token estimate (~3.8 chars per token for code/JSON/English)."""
    if text_or_obj is None:
        return 0
    if isinstance(text_or_obj, str):
        n = len(text_or_obj)
    else:
        n = len(str(text_or_obj))
    if n <= 0:
        return 0
    return max(1, int(round(n / 3.8)))


def _layperson_tool_indicator(
    name: str, category: str, target: str, is_test_cmd: bool, is_search_cmd: bool
) -> Dict[str, str]:
    """Return a layperson-friendly badge, icon, animation cue, and plain-English explanation for a tool."""
    t_short = clip_text(target or name, 72)

    if name.startswith("mcp__"):
        parts = name.split("__")
        server = parts[1] if len(parts) > 1 else "MCP"
        method = ".".join(parts[2:]) if len(parts) > 2 else "call"
        return {
            "tool_name": name,
            "badge": f"Connector · {server}",
            "icon": "🔌",
            "animation": "connector_pulse",
            "human_title": f"Queried the {server} connector ({method})",
            "plain_what_happened": f"Hermes reached out to the external '{server}' connector ({method}) with '{t_short}' and brought the response into the conversation.",
        }

    if name in ("read_file", "read_files", "view_file", "open_file", "read"):
        return {
            "tool_name": name,
            "badge": "File Reader",
            "icon": "📖",
            "animation": "file_scan",
            "human_title": f"Opened and read {t_short}",
            "plain_what_happened": f"Hermes opened '{t_short}' on disk and read its contents into the context window so the model could inspect it.",
        }

    if name in ("write_file", "create_file", "append_file"):
        return {
            "tool_name": name,
            "badge": "File Writer",
            "icon": "📝",
            "animation": "file_edit",
            "human_title": f"Created or wrote file {t_short}",
            "plain_what_happened": f"Hermes wrote new contents to '{t_short}' on disk.",
        }

    if name in ("patch", "edit_file", "str_replace", "multi_edit"):
        return {
            "tool_name": name,
            "badge": "Code Editor",
            "icon": "✏️",
            "animation": "file_edit",
            "human_title": f"Edited {t_short}",
            "plain_what_happened": f"Hermes applied targeted edits to '{t_short}' without rewriting the entire file.",
        }

    if name in ("terminal", "shell", "bash", "exec", "execute_code"):
        if is_test_cmd:
            return {
                "tool_name": name,
                "badge": "Test & Verify",
                "icon": "✅",
                "animation": "verify_check",
                "human_title": f"Ran verification check: {t_short}",
                "plain_what_happened": f"Hermes ran a test or validation command (`{t_short}`) in the terminal to prove the changes actually work.",
            }
        if is_search_cmd:
            return {
                "tool_name": name,
                "badge": "Workspace Search",
                "icon": "🔍",
                "animation": "search_radar",
                "human_title": f"Searched the system via terminal: {t_short}",
                "plain_what_happened": f"Hermes ran a quick lookup command (`{t_short}`) to locate files or inspect system state.",
            }
        return {
            "tool_name": name,
            "badge": "Terminal Command",
            "icon": "🖥️",
            "animation": "terminal_exec",
            "human_title": f"Ran terminal command: {t_short}",
            "plain_what_happened": f"Hermes executed `{t_short}` in a shell on your machine and captured the terminal output.",
        }

    if name in ("skill_view", "skill_manage"):
        return {
            "tool_name": name,
            "badge": "Skill Manual",
            "icon": "📘",
            "animation": "skill_inject",
            "human_title": f"Loaded the '{t_short}' skill into context",
            "plain_what_happened": f"Hermes opened the '{t_short}' skill playbook and injected its instructions into the Skills & Memory bucket.",
        }

    if name in ("local_recall", "memory", "session_search"):
        return {
            "tool_name": name,
            "badge": "Memory & Recall",
            "icon": "🧠",
            "animation": "skill_inject",
            "human_title": f"Searched memory & past sessions for '{t_short}'",
            "plain_what_happened": f"Hermes searched long-term memory and earlier conversations for '{t_short}'.",
        }

    if name == "delegate_task":
        return {
            "tool_name": name,
            "badge": "Subagent Helper",
            "icon": "🤝",
            "animation": "subagent_branch",
            "human_title": f"Delegated a sub-task to a helper agent: {t_short}",
            "plain_what_happened": f"Hermes spun up a separate helper agent with its own clean context window to work on '{t_short}' and report back a summary.",
        }

    if name == "clarify":
        return {
            "tool_name": name,
            "badge": "Question for You",
            "icon": "❓",
            "animation": "question_ask",
            "human_title": f"Asked you a clarifying question: “{t_short}”",
            "plain_what_happened": "Hermes paused to ask you a question before deciding how to proceed.",
        }

    if name == "todo_list":
        return {
            "tool_name": name,
            "badge": "Task Checklist",
            "icon": "📋",
            "animation": "decision_thought",
            "human_title": f"Updated its step-by-step checklist ({t_short})",
            "plain_what_happened": "Hermes updated its internal task checklist to track what is done and what remains.",
        }

    if name in ("web_search", "web_extract"):
        return {
            "tool_name": name,
            "badge": "Web Lookup",
            "icon": "🌐",
            "animation": "search_radar",
            "human_title": f"Looked up on the web: {t_short}",
            "plain_what_happened": f"Hermes fetched external web information for '{t_short}' and added the relevant excerpt to context.",
        }

    return {
        "tool_name": name,
        "badge": f"Tool · {name}",
        "icon": "🛠️",
        "animation": "terminal_exec",
        "human_title": f"Used {name} on {t_short}",
        "plain_what_happened": f"Hermes called the `{name}` tool with `{t_short}`.",
    }


def describe_tool_call(tool_name: str, args: Any) -> Dict[str, Any]:
    """Turn a raw tool name and arguments dict into a human verb, category, target, layperson indicator, and file ops."""
    name = (tool_name or "tool").strip()
    args_dict = args if isinstance(args, dict) else {}

    if name.startswith("mcp__"):
        parts = name.split("__")
        server = parts[1] if len(parts) > 1 else "mcp"
        rest = ".".join(parts[2:]) if len(parts) > 2 else "call"
        verb = f"called {server}.{rest}"
        category = "external"
    else:
        verb = TOOL_VERBS.get(name, f"used {name}")
        category = TOOL_CATEGORIES.get(name, "external")

    target_str = ""
    for k in TARGET_KEYS:
        val = args_dict.get(k)
        if isinstance(val, str) and val.strip():
            target_str = clip_text(val, 96)
            break
        if isinstance(val, list) and val:
            joined = ", ".join(str(x) for x in val[:3] if x is not None)
            if joined:
                target_str = clip_text(joined, 96)
                break

    if not target_str and name == "delegate_task":
        tasks = args_dict.get("tasks")
        if isinstance(tasks, list) and tasks:
            first = tasks[0]
            if isinstance(first, dict):
                target_str = clip_text(first.get("goal") or first.get("prompt") or f"{len(tasks)} subagent task(s)", 96)
            else:
                target_str = f"{len(tasks)} subagent task(s)"

    if not target_str:
        for val in args_dict.values():
            if isinstance(val, str) and val.strip():
                target_str = clip_text(val, 84)
                break

    # Refine terminal commands into explore / test / execute
    is_test_cmd = False
    is_search_cmd = False
    if name in ("terminal", "shell", "bash", "exec"):
        cmd = str(args_dict.get("command") or "")
        if _TEST_CMD_RE.search(cmd):
            verb = "verified with"
            is_test_cmd = True
        elif _SEARCH_CMD_RE.search(cmd):
            verb = "inspected via"
            is_search_cmd = True

    # Identify files touched
    files_touched: List[Dict[str, str]] = []
    for path_key in ("path", "file_path", "file"):
        pval = args_dict.get(path_key)
        if isinstance(pval, str) and pval.strip():
            op = "edit" if category == "mutate" else "read"
            files_touched.append({"path": _normalize_display_path(pval.strip()), "op": op})
    if name in ("terminal", "shell", "bash", "exec", "execute_code"):
        cmd_text = str(args_dict.get("command") or args_dict.get("code") or "")
        for m in _FILE_PATH_RE.finditer(cmd_text):
            candidate = m.group(0)
            if not candidate.startswith(("http", "192.168.", "127.0.")):
                op = "test" if is_test_cmd else "read"
                files_touched.append({"path": _normalize_display_path(candidate), "op": op})

    indicator = _layperson_tool_indicator(name, category, target_str or name, is_test_cmd, is_search_cmd)

    return {
        "tool_name": name,
        "verb": verb,
        "category": category,
        "target": target_str or name,
        "is_test": is_test_cmd,
        "files_touched": files_touched[:6],
        "tool_indicator": indicator,
    }


def _normalize_display_path(raw_path: str) -> str:
    """Keep file paths readable while preserving their last 2-3 segments."""
    clean = raw_path.strip().strip("'\"")
    if not clean:
        return ""
    parts = [p for p in Path(clean).parts if p not in ("/", "")]
    if len(parts) <= 3:
        return "/".join(parts)
    return "/".join(parts[-3:])


# ------------------------------------------------------------------ dataclasses

@dataclass
class ContextSnapshot:
    step_index: int
    total_tokens: int
    context_max: int
    context_pct: float
    delta_tokens: int
    breakdown: Dict[str, int] = field(default_factory=dict)
    cache_read_tokens: int = 0
    compacted: bool = False
    compaction_freed_tokens: int = 0
    estimated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        b = self.breakdown or {}
        d["utilization_pct"] = self.context_pct
        d["system_prompt_tokens"] = int(b.get("system_prompt", 0))
        d["skills_and_memory_tokens"] = int(b.get("skills_and_memory", 0))
        d["user_messages_tokens"] = int(b.get("user_messages", 0))
        d["assistant_reasoning_tokens"] = int(b.get("assistant_reasoning", 0))
        d["tool_io_tokens"] = int(b.get("tool_io", 0))
        return d


@dataclass
class StoryStep:
    index: int
    id: str
    turn_index: int
    kind: str  # "user_prompt" | "context_load" | "decision" | "question" | "tool_call" | "compaction" | "subagent" | "assistant_reply"
    verb: str
    category: str
    tool_name: str
    target: str
    intent: str
    outcome_summary: str
    detail_preview: str
    started_at_ms: int
    ended_at_ms: int
    duration_ms: int
    lane: int = 0
    failed: bool = False
    error_snippet: str = ""
    is_pivot: bool = False
    pivot_reason: str = ""
    files_touched: List[Dict[str, str]] = field(default_factory=list)
    causal_links: List[Dict[str, Any]] = field(default_factory=list)
    running_tool_count: int = 0
    running_category_counts: Dict[str, int] = field(default_factory=dict)
    running_failed_count: int = 0
    context: Optional[ContextSnapshot] = None
    human_title: str = ""
    human_narrative: str = ""
    decision_text: str = ""
    tool_indicator: Dict[str, Any] = field(default_factory=dict)
    context_load_details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.context is not None:
            d["context"] = self.context.to_dict()
        return d


@dataclass
class StoryChapter:
    chapter_index: int
    title: str
    phase_kind: str
    start_step: int
    end_step: int
    tool_call_count: int
    failed_count: int
    pivot_count: int
    duration_ms: int
    context_start_tokens: int
    context_end_tokens: int
    context_delta_tokens: int
    narrative: str
    key_decisions: List[str] = field(default_factory=list)
    categories_used: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CodeImpactEntry:
    path: str
    reads: List[int] = field(default_factory=list)
    edits: List[int] = field(default_factory=list)
    verifications: List[int] = field(default_factory=list)
    status: str = "inspected_only"  # "verified" | "modified" | "inspected_only" | "failed_mutation"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SubagentBranch:
    child_session_id: str
    parent_step_index: int
    title: str
    goal: str
    model: str
    status: str
    tool_call_count: int
    message_count: int
    input_tokens: int
    output_tokens: int
    duration_ms: int
    summary: str
    top_tools: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
