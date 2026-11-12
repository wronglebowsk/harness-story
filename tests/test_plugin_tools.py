"""Tests for root plugin __init__.py: register(ctx), all 5 tool handlers, and 12 hooks."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Callable, Dict, List

from test_core import _create_synthetic_db

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _load_manifest() -> Dict[str, Any]:
    text = (PLUGIN_ROOT / "plugin.yaml").read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-untyped]
        return yaml.safe_load(text)
    except ImportError:
        out: Dict[str, List[str]] = {"provides_tools": [], "provides_hooks": []}
        current: str | None = None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("provides_tools:"):
                current = "provides_tools"
            elif stripped.startswith("provides_hooks:"):
                current = "provides_hooks"
            elif stripped and not line.startswith(" ") and not line.startswith("-"):
                current = None
            elif current and stripped.startswith("- "):
                out[current].append(stripped[2:].strip())
        return out


def _load_plugin_module() -> Any:
    spec = importlib.util.spec_from_file_location("harness_story_plugin_root", PLUGIN_ROOT / "__init__.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class StubPluginContext:
    def __init__(self, config: Dict[str, Any]) -> None:
        self._settings = dict(config)
        self.plugin_dir = str(PLUGIN_ROOT)
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.hooks: Dict[str, List[Callable[..., Any]]] = {}
        self.commands: Dict[str, Dict[str, Any]] = {}
        self.skills: Dict[str, str] = {}

    def get_config(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def register_tool(self, name: str, toolset: str, schema: Dict[str, Any], handler: Callable[..., str], **_: Any) -> None:
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}

    def register_hook(self, hook_name: str, callback: Callable[..., Any], **_: Any) -> None:
        self.hooks.setdefault(hook_name, []).append(callback)

    def register_command(self, name: str, description: str, handler: Callable[..., str], **_: Any) -> None:
        self.commands[name] = {"description": description, "handler": handler}

    def register_skill(self, name: str, path: str, **_: Any) -> None:
        self.skills[name] = path


def test_register_matches_manifest_and_invokes_all_tools(tmp_path: Path) -> None:
    db_file = _create_synthetic_db(tmp_path)
    manifest = _load_manifest()
    storage_root = tmp_path / "data"

    ctx = StubPluginContext({
        "db_path": str(db_file),
        "storage_dir": str(storage_root),
        "context_window": 131072,
        "auto_generate_on_session_end": True,
    })
    mod = _load_plugin_module()
    mod.register(ctx)

    # Verify default base_url is empty and ctx.get_config works
    resolved_cfg = mod._resolve_config(ctx)
    assert resolved_cfg["base_url"] == ""
    assert resolved_cfg["context_window"] == 131072

    # 1. Exact match with plugin.yaml provides_tools and provides_hooks
    assert set(ctx.tools.keys()) == set(manifest["provides_tools"])
    assert set(ctx.hooks.keys()) == set(manifest["provides_hooks"])
    assert "story" in ctx.commands
    assert "harness-story" in ctx.skills

    # 2. Test harness_story_list
    list_res = json.loads(ctx.tools["harness_story_list"]["handler"]({"limit": 10}))
    assert list_res["ok"] is True
    assert any(s["id"] == "sess_parent_01" for s in list_res["sessions"])

    # 3. Test harness_story_generate
    gen_res = json.loads(ctx.tools["harness_story_generate"]["handler"]({
        "session_id": "sess_parent_01",
        "slug": "parent_story",
        "use_llm": False,
    }))
    assert gen_res["ok"] is True
    assert gen_res["slug"] == "parent_story"
    assert gen_res["tool_tally"]["total_calls"] == 5
    assert gen_res["pivots_count"] == 1
    assert gen_res["subagents_count"] == 1
    assert Path(gen_res["story_json"]).is_file()
    assert Path(gen_res["widget_html"]).is_file()

    # 4. Test harness_story_inspect (summary, pivots, context, and step-specific)
    insp_summary = json.loads(ctx.tools["harness_story_inspect"]["handler"]({"story": "parent_story"}))
    assert insp_summary["ok"] is True
    assert insp_summary["slug"] == "parent_story"

    insp_pivots = json.loads(ctx.tools["harness_story_inspect"]["handler"]({"story": "parent_story", "section": "pivots"}))
    assert insp_pivots["ok"] is True
    assert len(insp_pivots["pivots"]) == 1

    insp_step = json.loads(ctx.tools["harness_story_inspect"]["handler"]({"story": "parent_story", "step": 4}))
    assert insp_step["ok"] is True
    assert insp_step["step"]["index"] == 4
    assert insp_step["step"]["is_pivot"] is True

    insp_missing = json.loads(ctx.tools["harness_story_inspect"]["handler"]({"story": "parent_story", "step": 99}))
    assert insp_missing["ok"] is False

    # Reject arbitrary file paths outside storage_dir/{stories,out}
    outside_json = tmp_path / "outside.json"
    outside_json.write_text(Path(gen_res["story_json"]).read_text(encoding="utf-8"), encoding="utf-8")
    insp_outside = json.loads(ctx.tools["harness_story_inspect"]["handler"]({"story": str(outside_json)}))
    assert insp_outside["ok"] is False

    # 5. Test harness_story_render (confined to <storage>/out/)
    ren_res = json.loads(ctx.tools["harness_story_render"]["handler"]({
        "story": "parent_story",
        "output_html": "custom_viewer.html",
        "title": "Custom Title",
    }))
    assert ren_res["ok"] is True
    custom_html = storage_root / "out" / "custom_viewer.html"
    assert custom_html.is_file()
    assert "Custom Title" in custom_html.read_text(encoding="utf-8")

    # Reject output_html escaping <storage>/out/
    escape_res = json.loads(ctx.tools["harness_story_render"]["handler"]({
        "story": "parent_story",
        "output_html": str(tmp_path / "escaped.html"),
    }))
    assert escape_res["ok"] is False
    assert not (tmp_path / "escaped.html").exists()

    # 6. Test harness_story_compare
    cmp_res = json.loads(ctx.tools["harness_story_compare"]["handler"]({
        "story_a": "parent_story",
        "story_b": "parent_story",
    }))
    assert cmp_res["ok"] is True
    assert cmp_res["deltas"]["tool_calls"] == 0

    # 7. Test /story slash command handler
    slash_md = ctx.commands["story"]["handler"]("sess_parent_01 --no-llm")
    assert "Tool Calls" in slash_md
    assert "Context Peak" in slash_md
