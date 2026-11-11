"""Pytest configuration for harness-story tests."""
from __future__ import annotations

import json
import site
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent

for p in (str(TESTS_DIR), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# If running under Hermes Agent's isolated (-I) test interpreter, attach the active Hermes venv site-packages.
for facts in sorted((Path.home() / ".hermes" / "installs").glob("*/facts.json")):
    try:
        doc = json.loads(facts.read_text(encoding="utf-8"))
        env_dir = Path(((doc.get("packages") or {}).get("venv") or {}).get("environment") or "")
        for sp in env_dir.glob("lib/python*/site-packages"):
            if sp.is_dir():
                site.addsitedir(str(sp))
    except Exception:
        continue
