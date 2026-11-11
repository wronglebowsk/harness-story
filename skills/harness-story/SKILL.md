---
name: harness-story
description: Generate, inspect, compare, and render animated causal stories of Hermes Agent sessions — including step-by-step context window progression, running tool call tallies, failure & recovery pivots, code impact trails, and subagent orchestration.
---

# Harness Story (`harness-story`)

Use `harness-story` when the user asks:
- *"What actually happened in that session?"*
- *"Tell me the story of how the model solved this / why it pivoted"*
- *"How much context window was used at each step, and how many tool calls ran?"*
- *"Show me an animated replay of the session"*
- *"Compare two Hermes sessions"*

## Tools Provided (toolset `harness-story`)

1. **`harness_story_list`**
   - Lists recent sessions from `~/.hermes/state.db` (`id`, `title`, `tool_call_count`, `message_count`, `input_tokens`) plus already-generated story artifacts.
   - Run this first when the user refers to a session by topic rather than exact session ID.

2. **`harness_story_generate`**
   - Reconstructs a full `HarnessStory` from `state.db` + live lifecycle hook telemetry (`plugin-data/harness-story/live/<session_id>.jsonl`).
   - Computes:
     - **Step-by-step Context Window progression** across 5 buckets (`system_prompt`, `skills_and_memory`, `user_messages`, `assistant_reasoning`, `tool_io`) with exact `% of ceiling` at every step.
     - **Running Tool Call Tally** (`1..N`) broken down by category (`explore`, `mutate`, `execute`, `verify`, `delegate`, `memory`, `web`, `other`) and tool name.
     - **Causal Edges & Pivots**: links file reads/searches to downstream edits (`triggered_edit`), edits to test runs (`verified`), tool errors to recovery steps (`caused_pivot`), and `delegate_task` calls to child subagent sessions (`spawned_subagent`).
     - **Hybrid LLM Narrative**: synthesizes chapter titles, executive summary, causal takeaways, and step-level why-it-matters via the configured local OpenAI-compatible model, falling back deterministically if offline.
   - Writes both `<slug>.json` and the self-contained animated HTML5 viewer `<slug>.html`.

3. **`harness_story_inspect`**
   - Drill into a story (`section`: `summary`, `pivots`, `context`, `tools`, `code_impact`, `chapters`, `subagents`) or pass `step=<1..N>` to inspect a single step's exact context snapshot, running tool count, reasoning, and causal links.

4. **`harness_story_compare`**
   - Compare two session stories (`story_a`, `story_b`) across tool call counts, failure & pivot rates, peak context tokens/percentage, subagents spawned, and category shifts.

5. **`harness_story_render`**
   - Re-renders the self-contained animated HTML5 viewer from a saved story JSON.

## Recommended Workflow

1. Call `harness_story_generate(session_id="latest")` (or a specific session ID from `harness_story_list`).
2. Present a concise narrative digest:
   - Headline & executive summary
   - Total tool calls & category breakdown
   - Context window start -> peak (% of ceiling) -> end
   - Key causal pivots (what failed and how the model adapted)
   - Subagent branches (if any)
3. Share the path to `widget_html` so the user can open the animated HTML5 story player in their browser or view it in the **Harness Story** Desktop pane.
