"""Tests for dashboard/plugin_api.py FastAPI routes."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard import plugin_api
from test_core import _create_synthetic_db


def test_dashboard_api_routes(tmp_path: Path, monkeypatch) -> None:
    db_file = _create_synthetic_db(tmp_path)
    storage_root = tmp_path / "plugin_data"
    for sub in ("live", "stories", "out"):
        (storage_root / sub).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(plugin_api, "_storage", lambda: storage_root)
    monkeypatch.setenv("HARNESS_STORY_DB_PATH", str(db_file))

    app = FastAPI()
    app.include_router(plugin_api.router, prefix="/api/plugins/harness-story")
    client = TestClient(app)

    # 1. GET /health
    r_health = client.get("/api/plugins/harness-story/health")
    assert r_health.status_code == 200
    assert r_health.json()["ok"] is True

    # 2. POST /generate
    r_gen = client.post(
        "/api/plugins/harness-story/generate",
        json={
            "session_id": "sess_parent_01",
            "slug": "synth-story",
            "use_llm": False,
            "db_path": str(db_file),
        },
    )
    assert r_gen.status_code == 200
    gen_body = r_gen.json()
    assert gen_body["ok"] is True
    assert gen_body["slug"] == "synth-story"
    assert gen_body["tool_calls"] == 5

    # 3. GET /stories
    r_list = client.get("/api/plugins/harness-story/stories")
    assert r_list.status_code == 200
    stories_list = r_list.json()["stories"]
    assert len(stories_list) == 1
    assert stories_list[0]["slug"] == "synth-story"

    # 4. GET /stories/{slug}.json
    r_json = client.get("/api/plugins/harness-story/stories/synth-story.json")
    assert r_json.status_code == 200
    assert r_json.json()["session_id"] == "sess_parent_01"

    # 5. GET /stories/{slug}.html
    r_html = client.get("/api/plugins/harness-story/stories/synth-story.html")
    assert r_html.status_code == 200
    assert "<!doctype html>" in r_html.text.lower()

    # 6. POST /compare
    r_cmp = client.post(
        "/api/plugins/harness-story/compare",
        json={"a": "synth-story", "b": "synth-story"},
    )
    assert r_cmp.status_code == 200
    assert r_cmp.json()["ok"] is True

    # 7. Path traversal & 404 guards
    r_bad = client.get("/api/plugins/harness-story/stories/..evil.json")
    assert r_bad.status_code == 400
    r_404 = client.get("/api/plugins/harness-story/stories/nonexistent.json")
    assert r_404.status_code == 404
