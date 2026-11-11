# Harness Story (`harness-story`)

**Harness Story** is a full-stack **Hermes Agent + Hermes Desktop** plugin (Backend Tools & Lifecycle Hooks + Main-Workspace Desktop Tab + Self-Contained Animated HTML5 Story Player + CLI) that tells the plain-English, causal story of what Hermes and the model did during a session.

Instead of a raw log of tool calls and internal reasoning blocks, `harness-story` reconstructs and narrates:

1. **Conversational Kickoff & Default Hidden Hermes Context Load** — Restates what you asked (*"You asked: '…'"*) followed by an explicit card unpacking Hermes's hidden startup context load: initial tokens, `% of context ceiling`, loaded skills, connectors, active plugins, registered tools, and recalled memory notes.
2. **Causal Decisions, Hypotheses, Failures & Pivots** — Explains in plain human language *why* the model chose each tool, which specific tool ran (with layperson action badges like `💻 Run Command`, `📖 Read File`, `✏️ Edit File`), what broke when a command failed, and how the model pivoted on the next step (`caused_pivot`, `triggered_edit`, `verified`).
3. **Unified 5-Bucket Context Breakdown & Auto-Scrolling Chronicle** — Displays a prominent 5-bucket context window bar right above the auto-scrolling Chronicle so you can digest one step at a time while watching context grow across:
   - `system_prompt` (Hermes instructions & tool schemas)
   - `skills_and_memory` (activated `SKILL.md` injections + recalled memory)
   - `user_messages` (your prompts and steering)
   - `assistant_reasoning` (model thinking & explanations)
   - `tool_io` (tool call inputs & outputs)
4. **System & Code Impact Trail** — File-level ledger linking every read, edit (`patch`, `write_file`), and verification (`pytest`, `node --check`, `hermes plugins validate`).
5. **Subagent Orchestration** — Links `delegate_task` calls to child subagent sessions in `~/.hermes/state.db` (`parent_session_id`), showing delegated goals, child tool counts, and token usage.
6. **Hybrid LLM Narrative + Deterministic Fallback** — Combines deterministic telemetry from `~/.hermes/state.db` and 12 live lifecycle hooks with an optional narrative synthesis pass via a configurable OpenAI-compatible endpoint, falling back cleanly to deterministic synthesis when offline or `--no-llm` is used.

---

## Architecture & Directory Layout

```text
harness-story/
├── plugin.yaml                           # Hermes backend plugin manifest (5 tools, 12 hooks)
├── __init__.py                           # register(ctx): tools, HookCollector, /story command, skill
├── pyproject.toml                        # Python package & `harness-story` CLI entry point
├── harness_story/
│   ├── models.py                         # Dataclasses, 5-bucket ContextSnapshot, tool verb/category vocabulary
│   ├── collector.py                      # Thread-safe fail-open HookCollector -> plugin-data/harness-story/live/
│   ├── reconstruct.py                    # Reconstructs stories from ~/.hermes/state.db + live hook JSONL
│   ├── narrator.py                       # Hybrid OpenAI-compatible narrative synthesizer + deterministic fallback
│   ├── render.py                         # Self-contained animated HTML5 Story Viewer generator
│   └── cli.py                            # CLI: list, generate, inspect, compare, render
├── dashboard/
│   ├── manifest.json                     # Dashboard API manifest
│   └── plugin_api.py                     # FastAPI router mounted at /api/plugins/harness-story/
├── desktop/
│   └── plugin.js                         # Hermes Desktop main-workspace pane (`placement: 'main'`)
├── desktop-plugin/
│   ├── harness-story/
│   │   └── plugin.js                     # Hermes Desktop plugin bundle
│   └── tests/
│       ├── run.sh                        # Standalone React 19 + jsdom verification runner
│       └── harness.mjs                   # 11 assertions covering mount, playback, filters, and theme compliance
├── skills/
│   └── harness-story/
│       └── SKILL.md                      # Bundled skill guiding the agent on storytelling workflows
└── tests/
    ├── test_core.py                      # Core reconstruction, context buckets, pivots, narrator, HTML tests
    ├── test_plugin_tools.py              # Manifest parity & 5 tool handler tests
    └── test_plugin_api.py                # FastAPI route & path-traversal tests
```

---

## Quick Start

### 1. Inside Hermes Desktop
Open the **Harness Story** tab in the main workspace (`placement: 'main'`), pick any saved story from the dropdown, or click **Tell Latest Story** to synthesize the most recent session from `~/.hermes/state.db`. Click **▶ Play Story** or step through with **‹ Prev / Next ›** as the active step spotlight, 20px 5-bucket context bar, and auto-scrolling Chronicle advance together.

### 2. Slash Command & Agent Tools
- `/story [session_id|latest] [--no-llm]` — Generate a session story directly in chat.
- `harness_story_list` — List recent sessions in `state.db` and saved stories.
- `harness_story_generate` — Reconstruct a session story and write `<slug>.json` + `<slug>.html`.
- `harness_story_inspect` — Inspect story sections (`summary`, `pivots`, `context`, `tools`, `code_impact`, `chapters`, `subagents`) or a single `step`.
- `harness_story_compare` — Compare two stories across tool counts, pivots, and context pressure.
- `harness_story_render` — Render or re-render the self-contained animated HTML5 story player.

### 3. Command Line (`harness_story.cli`)
```bash
# List recent Hermes sessions with tool call counts and token usage
python3 -m harness_story.cli list --limit 10

# Generate a story JSON + animated HTML5 viewer for the latest session
python3 -m harness_story.cli generate --session latest

# Generate a story for a specific session (deterministic mode, no LLM call)
python3 -m harness_story.cli generate --session <session_id> --no-llm
```

---

## Disclosures (Catalog Rule 13)

- **Reads outside plugin data (`~/.hermes/state.db` & `~/.hermes/config.yaml`)**: Reads Hermes's SQLite session store (`~/.hermes/state.db`) in **read-only** mode (`?mode=ro`) to reconstruct session messages, tool calls, and subagent trees, and reads non-secret inventory counts (installed skill names, plugin names, and connector names) from `~/.hermes/` to summarize the initial context load. Never reads `.env`, `auth.json`, or any credential store.
- **Filesystem writes (`filesystem:write`)**: Writes live hook event JSONL and generated `<slug>.json` and `<slug>.html` story artifacts exclusively inside `~/.hermes/plugin-data/harness-story/` (or a user-specified `--out-dir`).
- **Network calls**: Makes **zero** external third-party cloud or telemetry requests. When `use_llm` is enabled, `narrator.py` sends an optional `POST /v1/chat/completions` request to the user-configured local OpenAI-compatible endpoint (`config_schema.base_url`, defaulting to a local LAN/localhost server with a 6-second timeout) and falls back deterministically when unreachable or when `--no-llm` is set.
- **Shell commands & background processes**: Spawns **no** shell commands and runs **no** long-running background daemons.
- **Credentials**: Stores and reads **no** credentials or API keys.

---

## Validation & Tests

```bash
# Validate plugin manifest, capability probe, desktop surface, and security scan
hermes plugins validate /path/to/harness-story --install-deps

# Run Python test suite (27 tests)
pytest -v

# Run Desktop plugin React 19 + jsdom test suite (11 checks)
bash desktop-plugin/tests/run.sh
```
