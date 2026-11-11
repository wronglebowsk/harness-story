"""Self-contained animated HTML5 Story Viewer renderer for harness-story.

Produces a zero-dependency, offline-capable, theme-aware HTML document that tells
the human-language story of a Hermes session:
1. "Play Story" Animated Stage (replaces abstract graphs with what actually happened):
   - Kickoff restatement: "You asked: “Prompt Here”"
   - Hidden Hermes Context Load: animated summary of what was loaded (tokens, %, skills,
     connectors, plugins, tools/toolsets, and personal memory notes + User Profile)
   - Layperson Tool Use & Decision Animations: animated visual indicator for each tool
     (File Reader, Code Editor, Terminal Command, Test & Verify, Skill Manual, Subagent Helper,
     Connector, or Question for You) + plain-English decision/hypothesis/pivot callouts
2. Unified Context Buckets + Story Chronicle on the same screen:
   - Always-visible 5-Bucket Context Breakdown & Running Tool Counter
   - Conversational step-by-step Chronicle with context deltas baked directly into every step
"""
from __future__ import annotations

import html
import json
from typing import Any, Dict, Optional


def render_story_html(story: Dict[str, Any], title: Optional[str] = None) -> str:
    """Render *story* as a self-contained interactive HTML5 document."""
    doc_title = html.escape(str(title or story.get("title") or "Harness Story"))
    safe_json = json.dumps(story, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{doc_title} — Hermes Harness Story</title>
<style>
:root {{
  --bg: #0f111a;
  --bg-elev: #161926;
  --bg-card: #1b1f30;
  --bg-hover: #23283d;
  --fg: #e6e9f4;
  --fg-2: #a9b1d6;
  --fg-3: #787c99;
  --fg-4: #565f89;
  --border: #292e42;
  --border-hi: #3b4261;
  --accent: #7aa2f7;
  --cyan: #7dcfff;
  --green: #9ece6a;
  --yellow: #e0af68;
  --orange: #ff9e64;
  --red: #f7768e;
  --purple: #bb9af7;
  --indigo: #5a78c8;
  --font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}}
html[data-theme="light"] {{
  --bg: #f6f7fb;
  --bg-elev: #ffffff;
  --bg-card: #ffffff;
  --bg-hover: #eef1f8;
  --fg: #181a24;
  --fg-2: #3b4056;
  --fg-3: #636982;
  --fg-4: #8c92ab;
  --border: #dfe3ef;
  --border-hi: #c4cbe0;
  --accent: #2e59d9;
  --cyan: #0b7ea8;
  --green: #2e8540;
  --yellow: #b57614;
  --orange: #c95616;
  --red: #c92a42;
  --purple: #7c3aed;
  --indigo: #4355b9;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: var(--font-sans);
  font-size: 13.5px;
  line-height: 1.55;
}}
@keyframes stageFadeIn {{
  from {{ opacity: 0; transform: translateY(6px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes pulseRing {{
  0% {{ box-shadow: 0 0 0 0 rgba(122, 162, 247, 0.35); }}
  70% {{ box-shadow: 0 0 0 8px rgba(122, 162, 247, 0); }}
  100% {{ box-shadow: 0 0 0 0 rgba(122, 162, 247, 0); }}
}}
@keyframes scanSlide {{
  0% {{ transform: translateX(-12%); opacity: 0.55; }}
  50% {{ transform: translateX(12%); opacity: 1; }}
  100% {{ transform: translateX(-12%); opacity: 0.55; }}
}}
.app {{
  max-width: 1240px;
  margin: 0 auto;
  padding: 16px 20px 56px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}}
/* Header */
.header {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 14px 18px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 12px;
}}
.header-left {{ display: flex; flex-direction: column; gap: 3px; min-width: 0; }}
.eyebrow {{
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent);
  font-weight: 700;
}}
.title {{
  font-size: 19px;
  font-weight: 750;
  margin: 0;
  color: var(--fg);
}}
.subtitle {{
  font-size: 12.5px;
  color: var(--fg-2);
}}
.header-meta {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}}
.badge {{
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--fg-2);
}}
.badge b {{ color: var(--fg); font-weight: 650; }}
.btn {{
  background: var(--bg-card);
  color: var(--fg);
  border: 1px solid var(--border-hi);
  border-radius: 7px;
  padding: 6px 12px;
  font-size: 12.5px;
  cursor: pointer;
  font-variant-numeric: tabular-nums;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 550;
}}
.btn:hover {{ background: var(--bg-hover); }}
.btn-primary {{
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
  font-weight: 650;
}}
.btn-primary:hover {{ filter: brightness(1.08); background: var(--accent); }}
/* Executive Summary Card */
.exec-card {{
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: 12px;
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}}
.exec-headline {{
  font-size: 15.5px;
  font-weight: 700;
  color: var(--fg);
}}
.exec-body {{
  font-size: 13.5px;
  color: var(--fg-2);
  white-space: pre-line;
}}
/* Player & Animated Story Stage */
.player-card {{
  position: sticky;
  top: 8px;
  z-index: 25;
  background: var(--bg-elev);
  border: 1px solid var(--border-hi);
  border-radius: 12px;
  padding: 12px 16px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.28);
  display: flex;
  flex-direction: column;
  gap: 10px;
}}
.player-controls {{
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}}
.scrubber-wrap {{
  flex: 1;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}}
.scrubber {{
  width: 100%;
  accent-color: var(--accent);
  cursor: pointer;
  margin: 0;
}}
/* Now Happening Stage */
.stage-card {{
  background: var(--bg-card);
  border: 1px solid var(--border-hi);
  border-radius: 12px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  animation: stageFadeIn 0.25s ease-out;
}}
.stage-card[data-playing="true"] {{
  animation: stageFadeIn 0.25s ease-out, pulseRing 1.8s infinite;
}}
.stage-top {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}}
.stage-badges {{
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}}
.tool-pill {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 650;
  background: var(--bg-elev);
  border: 1px solid var(--border-hi);
  color: var(--fg);
}}
.stage-title {{
  font-size: 16.5px;
  font-weight: 750;
  color: var(--fg);
}}
.stage-narrative {{
  font-size: 13.5px;
  color: var(--fg-2);
}}
.decision-box {{
  padding: 9px 12px;
  border-radius: 8px;
  background: var(--bg-elev);
  border-left: 3px solid var(--accent);
  font-size: 12.5px;
  color: var(--fg);
}}
.decision-box[data-pivot="true"] {{
  border-left-color: var(--yellow);
}}
.backpack-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 10px;
  margin-top: 4px;
}}
.backpack-item {{
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}}
.backpack-head {{
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--purple);
}}
.backpack-val {{
  font-size: 15px;
  font-weight: 750;
  color: var(--fg);
}}
.backpack-sub {{
  font-size: 11.5px;
  color: var(--fg-3);
}}
.anim-box {{
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}}
.scan-bar {{
  height: 5px;
  border-radius: 999px;
  background: var(--border);
  overflow: hidden;
}}
.scan-bar-fill {{
  width: 60%;
  height: 100%;
  background: var(--cyan);
  animation: scanSlide 1.5s infinite ease-in-out;
}}
/* Unified Context Buckets & Running Tool Tally */
.buckets-card {{
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}}
.buckets-head {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
}}
.stacked-bar {{
  height: 12px;
  border-radius: 999px;
  background: var(--bg-card);
  overflow: hidden;
  display: flex;
  border: 1px solid var(--border);
}}
.stacked-seg {{
  height: 100%;
  transition: width 0.25s ease;
}}
.buckets-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(195px, 1fr));
  gap: 8px;
}}
.bucket-pill {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}}
.bucket-top {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11.5px;
  font-weight: 650;
}}
.bucket-desc {{
  font-size: 10.5px;
  color: var(--fg-3);
}}
.dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 5px;
}}
/* Unified Chronicle below Context Buckets */
.chronicle-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}}
.filter-pills {{
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}}
.steps-list {{
  display: flex;
  flex-direction: column;
  gap: 9px;
}}
.step-card {{
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: 10px;
  padding: 12px 15px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}}
.step-card:hover {{ background: var(--bg-hover); }}
.step-card[data-current="true"] {{
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
  background: var(--bg-card);
}}
.step-card[data-kind="context_load"] {{ border-left-color: var(--purple); }}
.step-card[data-failed="true"] {{ border-left-color: var(--red); }}
.step-card[data-pivot="true"] {{ border-left-color: var(--yellow); }}
.step-top {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}}
.step-title {{
  font-size: 14.5px;
  font-weight: 700;
  color: var(--fg);
}}
.step-narrative {{
  font-size: 13px;
  color: var(--fg-2);
}}
.step-detail {{
  margin-top: 4px;
  padding: 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 7px;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--fg-2);
  white-space: pre-wrap;
  word-break: break-word;
}}
</style>
</head>
<body>
<div class="app" id="app"></div>
<script id="story-data" type="application/json">{safe_json}</script>
<script>
(function() {{
  const rawEl = document.getElementById('story-data');
  const STORY = JSON.parse(rawEl ? rawEl.textContent : '{{}}');
  const steps = Array.isArray(STORY.steps) ? STORY.steps : [];
  const pivots = Array.isArray(STORY.pivots) ? STORY.pivots : [];
  const codeImpact = Array.isArray(STORY.code_impact) ? STORY.code_impact : [];
  const tally = STORY.tool_tally || {{}};
  const ctxJourney = STORY.context_journey || {{}};

  const state = {{
    currentStepIdx: 0,
    playing: false,
    speed: 1,
    filterMode: 'all',
    expandedSteps: new Set(),
    autoScroll: true,
    theme: 'dark',
  }};

  let playTimer = null;

  function fmtInt(n) {{
    if (typeof n !== 'number' || !Number.isFinite(n)) return '0';
    return Math.round(n).toLocaleString('en-US');
  }}

  function fmtMs(ms) {{
    if (typeof ms !== 'number' || !Number.isFinite(ms) || ms <= 0) return '';
    if (ms >= 60000) return (ms / 60000).toFixed(1) + 'm';
    if (ms >= 1000) return (ms / 1000).toFixed(1) + 's';
    return Math.round(ms) + 'ms';
  }}

  function el(tag, attrs, children) {{
    const node = document.createElement(tag);
    if (attrs) {{
      for (const [k, v] of Object.entries(attrs)) {{
        if (v === undefined || v === null || v === false) continue;
        if (k === 'className') node.className = v;
        else if (k === 'style' && typeof v === 'object') Object.assign(node.style, v);
        else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2).toLowerCase(), v);
        else node.setAttribute(k, String(v));
      }}
    }}
    if (children !== undefined && children !== null) {{
      const list = Array.isArray(children) ? children : [children];
      for (const child of list) {{
        if (child === undefined || child === null || child === false) continue;
        node.appendChild(typeof child === 'object' ? child : document.createTextNode(String(child)));
      }}
    }}
    return node;
  }}

  function stopPlayback() {{
    state.playing = false;
    if (playTimer) {{
      clearInterval(playTimer);
      playTimer = null;
    }}
  }}

  function startPlayback() {{
    stopPlayback();
    if (!steps.length) return;
    if (state.currentStepIdx >= steps.length - 1) state.currentStepIdx = 0;
    state.playing = true;
    const intervalMs = Math.max(400, Math.round(1400 / state.speed));
    playTimer = setInterval(() => {{
      if (state.currentStepIdx < steps.length - 1) {{
        state.currentStepIdx += 1;
        renderApp();
        if (state.autoScroll) scrollCurrentStepIntoView();
      }} else {{
        stopPlayback();
        renderApp();
      }}
    }}, intervalMs);
    renderApp();
  }}

  function jumpToStepIdx(idx) {{
    stopPlayback();
    state.currentStepIdx = Math.max(0, Math.min(steps.length - 1, idx));
    renderApp();
  }}

  function scrollCurrentStepIntoView() {{
    const step = steps[state.currentStepIdx];
    if (!step) return;
    const card = document.getElementById('step-card-' + step.index);
    if (card && typeof card.scrollIntoView === 'function') {{
      card.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
    }}
  }}

  function renderStageCard(step) {{
    if (!step) return null;
    const ind = step.tool_indicator || {{}};
    const ctx = step.context || {{}};
    const cl = step.context_load_details || STORY.context_load || null;
    const kind = step.kind || 'tool_call';

    let bodyVisual = null;
    if (kind === 'user_prompt') {{
      bodyVisual = el('div', {{ className: 'anim-box', style: {{ borderLeft: '4px solid var(--accent)' }} }}, [
        el('div', {{ style: {{ fontSize: '11px', fontWeight: '700', color: 'var(--accent)', textTransform: 'uppercase' }} }}, 'Session Kickoff — Your Prompt'),
        el('div', {{ style: {{ fontSize: '14.5px', fontWeight: '600', color: 'var(--fg)' }} }}, '“' + (step.target || STORY.title || '') + '”'),
        el('div', {{ style: {{ fontSize: '12px', color: 'var(--fg-3)' }} }}, 'Hermes received your prompt and prepared to load your workspace context before calling the model.'),
      ]);
    }} else if (kind === 'context_load' && cl) {{
      bodyVisual = el('div', {{ className: 'backpack-grid' }}, [
        el('div', {{ className: 'backpack-item' }}, [
          el('div', {{ className: 'backpack-head' }}, '📘 Skills Loaded'),
          el('div', {{ className: 'backpack-val' }}, fmtInt(cl.skills_count || 0) + ' skills'),
          el('div', {{ className: 'backpack-sub' }}, 'Categories: ' + ((cl.skill_categories || []).slice(0, 4).join(', ') || 'built-in')),
        ]),
        el('div', {{ className: 'backpack-item' }}, [
          el('div', {{ className: 'backpack-head' }}, '🔌 Connectors & Plugins'),
          el('div', {{ className: 'backpack-val' }}, fmtInt(cl.connectors_count || 0) + ' MCP · ' + fmtInt(cl.plugins_count || 0) + ' plugins'),
          el('div', {{ className: 'backpack-sub' }}, (cl.connectors_list || []).join(', ') || 'Local workspace connectors'),
        ]),
        el('div', {{ className: 'backpack-item' }}, [
          el('div', {{ className: 'backpack-head' }}, '🧰 Tools & Toolsets'),
          el('div', {{ className: 'backpack-val' }}, '~' + fmtInt(cl.tools_estimated_count || 0) + ' tools'),
          el('div', {{ className: 'backpack-sub' }}, fmtInt(cl.toolsets_count || 0) + ' active toolsets ready for the model'),
        ]),
        el('div', {{ className: 'backpack-item' }}, [
          el('div', {{ className: 'backpack-head' }}, '🧠 Memory & Profile'),
          el('div', {{ className: 'backpack-val' }}, fmtInt(cl.memory_notes_count || 0) + ' notes' + (cl.user_profile_loaded ? ' + Profile' : '')),
          el('div', {{ className: 'backpack-sub' }}, cl.semantic_memory_provider ? ('Semantic memory: ' + cl.semantic_memory_provider) : 'Persistent personal notes'),
        ]),
      ]);
    }} else {{
      const anim = ind.animation || 'terminal_exec';
      const rows = [
        el('div', {{ style: {{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }} }}, [
          el('span', {{ style: {{ fontWeight: '700', color: 'var(--fg)' }} }}, (ind.icon || '🔧') + ' ' + (ind.badge || step.tool_name || 'Action') + (step.tool_name ? ' (' + step.tool_name + ')' : '')),
          el('span', {{ style: {{ fontFamily: 'var(--font-mono)', fontSize: '11.5px', color: 'var(--fg-2)' }} }}, String(step.target || '')),
        ]),
      ];
      if (anim === 'file_scan') {{
        rows.push(el('div', {{ className: 'scan-bar' }}, [el('div', {{ className: 'scan-bar-fill' }})]));
      }} else if (anim === 'file_edit') {{
        rows.push(el('div', {{ style: {{ display: 'flex', flexDirection: 'column', gap: '3px', fontFamily: 'var(--font-mono)', fontSize: '11px' }} }}, [
          el('div', {{ style: {{ color: 'var(--red)' }} }}, '- old lines replaced in ' + (step.target || 'file')),
          el('div', {{ style: {{ color: 'var(--green)' }} }}, '+ updated lines written and saved'),
        ]));
      }} else if (anim === 'terminal_exec' || anim === 'verify_check') {{
        rows.push(el('div', {{ style: {{ fontFamily: 'var(--font-mono)', fontSize: '11.5px', padding: '6px 10px', borderRadius: '6px', background: 'var(--bg)', color: step.status === 'error' ? 'var(--red)' : 'var(--green)' }} }}, '$ ' + (step.target || step.tool_name || 'command')));
      }}
      if (step.outcome_summary) {{
        rows.push(el('div', {{ style: {{ fontSize: '12px', color: step.status === 'error' ? 'var(--red)' : 'var(--fg-2)' }} }}, (step.status === 'error' ? '⚠️ Result: ' : '✓ Result: ') + step.outcome_summary));
      }}
      bodyVisual = el('div', {{ className: 'anim-box' }}, rows);
    }}

    const deltaSign = (ctx.delta_tokens || 0) >= 0 ? '+' : '';
    return el('div', {{ className: 'stage-card', 'data-playing': state.playing ? 'true' : 'false' }}, [
      el('div', {{ className: 'stage-top' }}, [
        el('div', {{ className: 'stage-badges' }}, [
          el('span', {{ className: 'badge' }}, [el('b', null, 'Step ' + step.index + ' of ' + steps.length)]),
          el('span', {{ className: 'tool-pill' }}, (ind.icon || '🔹') + ' ' + (ind.badge || step.tool_name || step.kind)),
          step.running_tool_count > 0 ? el('span', {{ className: 'badge' }}, 'Tool #' + step.running_tool_count + ' of ' + (tally.total_calls || 0)) : null,
          step.is_pivot ? el('span', {{ className: 'badge', style: {{ borderColor: 'var(--yellow)', color: 'var(--yellow)' }} }}, '🔄 Course Correction (Pivot)') : null,
          step.status === 'error' ? el('span', {{ className: 'badge', style: {{ borderColor: 'var(--red)', color: 'var(--red)' }} }}, '⚠️ Error') : null,
        ]),
        el('span', {{ className: 'badge' }}, 'Context: ' + deltaSign + fmtInt(ctx.delta_tokens || 0) + ' tok → ' + fmtInt(ctx.total_tokens || 0) + ' tok (' + Number(ctx.utilization_pct || 0).toFixed(1) + '%)'),
      ]),
      el('div', {{ className: 'stage-title' }}, step.human_title || ((step.verb || '') + ' ' + (step.target || ''))),
      el('div', {{ className: 'stage-narrative' }}, step.human_narrative || step.narrative_why || ''),
      (step.decision_text || step.pivot_reason) ? el('div', {{ className: 'decision-box', 'data-pivot': step.is_pivot ? 'true' : 'false' }}, [
        el('b', null, step.is_pivot ? '🔄 Why Hermes changed strategy (Pivot): ' : '💭 Decision / Hypothesis: '),
        document.createTextNode(step.pivot_reason || step.decision_text || ''),
      ]) : null,
      bodyVisual,
    ]);
  }}

  function renderBucketsCard(step) {{
    const ctx = (step && step.context) || {{}};
    const bd = ctx.breakdown || {{}};
    const total = Math.max(1, ctx.total_tokens || 1);
    const maxTok = ctx.context_max || ctxJourney.context_max || 131072;
    const buckets = [
      {{ key: 'system_prompt', label: 'Hermes Instructions & Tools', val: ctx.system_prompt_tokens ?? bd.system_prompt ?? 0, color: 'var(--indigo)', desc: 'Base rules & tool schemas' }},
      {{ key: 'skills_and_memory', label: 'Skills & Memory', val: ctx.skills_and_memory_tokens ?? bd.skills_and_memory ?? 0, color: 'var(--purple)', desc: 'Loaded skills, notes & profile' }},
      {{ key: 'user_messages', label: 'Your Prompts', val: ctx.user_messages_tokens ?? bd.user_messages ?? 0, color: 'var(--cyan)', desc: 'Your messages in the chat' }},
      {{ key: 'assistant_reasoning', label: 'Model Thinking & Replies', val: ctx.assistant_reasoning_tokens ?? bd.assistant_reasoning ?? 0, color: 'var(--green)', desc: 'Hypotheses, decisions & answers' }},
      {{ key: 'tool_io', label: 'Tool Inputs & Results', val: ctx.tool_io_tokens ?? bd.tool_io ?? 0, color: 'var(--yellow)', desc: 'Files read, command outputs & diffs' }},
    ];

    let toolCurr = 0;
    for (let i = 0; i <= state.currentStepIdx && i < steps.length; i++) {{
      if (steps[i].kind === 'tool_call') toolCurr++;
    }}

    return el('div', {{ className: 'buckets-card' }}, [
      el('div', {{ className: 'buckets-head' }}, [
        el('div', null, [
          el('span', {{ style: {{ fontWeight: '750', fontSize: '13.5px' }} }}, '🎒 Live Context Window & 5 Buckets at Step ' + (step ? step.index : 1)),
          el('span', {{ style: {{ marginLeft: '10px', fontSize: '12px', color: 'var(--fg-2)' }} }}, fmtInt(ctx.total_tokens || 0) + ' / ' + fmtInt(maxTok) + ' tokens (' + Number(ctx.utilization_pct || 0).toFixed(2) + '%)'),
        ]),
        el('div', {{ style: {{ fontSize: '12px', color: 'var(--fg-2)', fontWeight: '650' }} }}, '🧰 Tools used so far: ' + toolCurr + ' of ' + (tally.total_calls || 0)),
      ]),
      el('div', {{ className: 'stacked-bar' }}, buckets.map(b => el('div', {{
        className: 'stacked-seg',
        style: {{ width: Math.max(0, Math.min(100, (b.val / total) * 100)).toFixed(2) + '%', background: b.color }},
        title: b.label + ': ' + fmtInt(b.val) + ' tokens',
      }}))),
      el('div', {{ className: 'buckets-grid' }}, buckets.map(b => el('div', {{ className: 'bucket-pill' }}, [
        el('div', {{ className: 'bucket-top' }}, [
          el('span', null, [el('span', {{ className: 'dot', style: {{ background: b.color }} }}), b.label]),
          el('span', {{ style: {{ fontFamily: 'var(--font-mono)' }} }}, fmtInt(b.val) + ' tok'),
        ]),
        el('div', {{ className: 'bucket-desc' }}, b.desc),
      ]))),
    ]);
  }}

  function renderStepCard(step, idx) {{
    const isCurrent = idx === state.currentStepIdx;
    const isExpanded = state.expandedSteps.has(step.index);
    const ind = step.tool_indicator || {{}};
    const ctx = step.context || {{}};
    const cl = step.context_load_details || null;
    const deltaSign = (ctx.delta_tokens || 0) >= 0 ? '+' : '';

    return el('div', {{
      className: 'step-card',
      id: 'step-card-' + step.index,
      'data-current': isCurrent ? 'true' : 'false',
      'data-kind': step.kind || 'tool_call',
      'data-failed': step.status === 'error' ? 'true' : 'false',
      'data-pivot': step.is_pivot ? 'true' : 'false',
      onClick: () => jumpToStepIdx(idx),
    }}, [
      el('div', {{ className: 'step-top' }}, [
        el('div', {{ style: {{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }} }}, [
          el('span', {{ style: {{ fontFamily: 'var(--font-mono)', fontSize: '11.5px', fontWeight: '700', color: 'var(--fg-3)' }} }}, '#' + step.index),
          el('span', {{ className: 'tool-pill', style: {{ padding: '2px 9px', fontSize: '11.5px' }} }}, (ind.icon || '🔹') + ' ' + (ind.badge || step.tool_name || step.kind)),
          step.is_pivot ? el('span', {{ className: 'badge', style: {{ borderColor: 'var(--yellow)', color: 'var(--yellow)' }} }}, '🔄 Pivot from #' + (step.pivot_from_step || (step.index - 1))) : null,
          step.status === 'error' ? el('span', {{ className: 'badge', style: {{ borderColor: 'var(--red)', color: 'var(--red)' }} }}, '⚠️ Failed') : null,
        ]),
        el('div', {{ style: {{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11.5px', fontFamily: 'var(--font-mono)', color: 'var(--fg-2)' }} }}, [
          step.duration_ms ? el('span', null, fmtMs(step.duration_ms)) : null,
          el('span', {{ className: 'badge' }}, deltaSign + fmtInt(ctx.delta_tokens || 0) + ' tok → ' + fmtInt(ctx.total_tokens || 0) + ' tok (' + Number(ctx.utilization_pct || 0).toFixed(1) + '%)'),
          el('button', {{
            className: 'btn',
            style: {{ padding: '2px 7px', fontSize: '11px' }},
            onClick: (e) => {{
              e.stopPropagation();
              if (state.expandedSteps.has(step.index)) state.expandedSteps.delete(step.index);
              else state.expandedSteps.add(step.index);
              renderApp();
            }},
          }}, isExpanded ? 'Hide raw' : 'Raw details'),
        ]),
      ]),
      el('div', {{ className: 'step-title' }}, step.human_title || ((step.verb || '') + ' ' + (step.target || ''))),
      el('div', {{ className: 'step-narrative' }}, step.human_narrative || step.narrative_why || ''),
      (step.decision_text || step.pivot_reason) ? el('div', {{ className: 'decision-box', 'data-pivot': step.is_pivot ? 'true' : 'false' }}, [
        el('b', null, step.is_pivot ? '🔄 Why Hermes pivoted: ' : '💭 Why Hermes did this: '),
        document.createTextNode(step.pivot_reason || step.decision_text || ''),
      ]) : null,
      (step.kind === 'context_load' && cl) ? el('div', {{ style: {{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '2px' }} }}, [
        el('span', {{ className: 'badge' }}, '📘 ' + fmtInt(cl.skills_count || 0) + ' skills'),
        el('span', {{ className: 'badge' }}, '🔌 ' + fmtInt(cl.connectors_count || 0) + ' connectors (' + ((cl.connectors_list || []).join(', ') || 'none') + ')'),
        el('span', {{ className: 'badge' }}, '🧩 ' + fmtInt(cl.plugins_count || 0) + ' plugins'),
        el('span', {{ className: 'badge' }}, '🧰 ~' + fmtInt(cl.tools_estimated_count || 0) + ' tools across ' + fmtInt(cl.toolsets_count || 0) + ' toolsets'),
        el('span', {{ className: 'badge' }}, '🧠 ' + fmtInt(cl.memory_notes_count || 0) + ' memory notes' + (cl.user_profile_loaded ? ' + User Profile' : '')),
      ]) : null,
      isExpanded ? el('div', {{ className: 'step-detail' }}, [
        step.args_preview ? ('Input / Arguments:\n' + step.args_preview + '\n\n') : '',
        step.result_preview ? ('Result / Output:\n' + step.result_preview) : (step.outcome_summary || ''),
      ].join('')) : null,
    ]);
  }}

  function renderApp() {{
    const app = document.getElementById('app');
    if (!app) return;
    app.innerHTML = '';

    const currentStep = steps[state.currentStepIdx] || steps[0] || null;

    // 1. Header
    app.appendChild(el('div', {{ className: 'header' }}, [
      el('div', {{ className: 'header-left' }}, [
        el('div', {{ className: 'eyebrow' }}, 'Hermes Agent · Session Story & Context Walkthrough'),
        el('h1', {{ className: 'title' }}, STORY.title || 'Harness Story'),
        el('div', {{ className: 'subtitle' }}, 'Session ' + (STORY.session_id || '') + ' · Model: ' + (STORY.model || 'unknown')),
      ]),
      el('div', {{ className: 'header-meta' }}, [
        el('span', {{ className: 'badge' }}, [el('b', null, fmtInt(tally.total_calls || 0)), 'tool calls']),
        el('span', {{ className: 'badge' }}, [el('b', null, fmtInt(pivots.length)), 'pivots']),
        el('span', {{ className: 'badge' }}, [el('b', null, fmtInt(ctxJourney.peak_tokens || 0) + ' tok'), '(' + Number(ctxJourney.peak_pct || 0).toFixed(1) + '% peak context)']),
        el('button', {{
          className: 'btn',
          onClick: () => {{
            state.theme = state.theme === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', state.theme);
          }},
        }}, state.theme === 'dark' ? '☀️ Light' : '🌙 Dark'),
      ]),
    ]));

    // 2. Executive Summary Card
    app.appendChild(el('div', {{ className: 'exec-card' }}, [
      el('div', {{ className: 'exec-headline' }}, STORY.headline || STORY.title || ''),
      el('div', {{ className: 'exec-body' }}, STORY.executive_summary || ''),
    ]));

    // 3. Sticky Play Story Bar + Animated Stage
    app.appendChild(el('div', {{ className: 'player-card', id: 'play-btn' }}, [
      el('div', {{ className: 'player-controls' }}, [
        el('button', {{
          className: 'btn btn-primary',
          id: 'btn-play',
          onClick: () => state.playing ? (stopPlayback(), renderApp()) : startPlayback(),
        }}, state.playing ? '⏸ Pause Story' : '▶ Play Story'),
        el('button', {{
          className: 'btn',
          onClick: () => jumpToStepIdx(state.currentStepIdx - 1),
        }}, '⏮ Prev'),
        el('button', {{
          className: 'btn',
          onClick: () => jumpToStepIdx(state.currentStepIdx + 1),
        }}, 'Next ⏭'),
        el('div', {{ className: 'scrubber-wrap' }}, [
          el('input', {{
            type: 'range',
            className: 'scrubber',
            min: 0,
            max: Math.max(0, steps.length - 1),
            value: state.currentStepIdx,
            onInput: (e) => jumpToStepIdx(Number(e.target.value)),
          }}),
        ]),
        el('button', {{
          className: 'btn',
          onClick: () => {{
            const speeds = [0.5, 1, 2, 4];
            state.speed = speeds[(speeds.indexOf(state.speed) + 1) % speeds.length];
            if (state.playing) startPlayback();
            else renderApp();
          }},
        }}, state.speed + 'x'),
      ]),
      renderStageCard(currentStep),
    ]));

    // 4. Unified 5-Bucket Context Breakdown + Chronicle together
    app.appendChild(renderBucketsCard(currentStep));

    app.appendChild(el('div', {{ className: 'chronicle-header' }}, [
      el('div', {{ style: {{ fontWeight: '750', fontSize: '15px' }} }}, '📖 Step-by-Step Story Chronicle (with Context Baked In)'),
      el('div', {{ className: 'filter-pills' }}, [
        el('button', {{
          className: 'btn' + (state.filterMode === 'all' ? ' btn-primary' : ''),
          onClick: () => {{ state.filterMode = 'all'; renderApp(); }},
        }}, 'All Steps (' + steps.length + ')'),
        el('button', {{
          className: 'btn' + (state.filterMode === 'pivots' ? ' btn-primary' : ''),
          onClick: () => {{ state.filterMode = 'pivots'; renderApp(); }},
        }}, 'Pivots & Decisions (' + pivots.length + ')'),
        el('button', {{
          className: 'btn' + (state.filterMode === 'impact' ? ' btn-primary' : ''),
          onClick: () => {{ state.filterMode = 'impact'; renderApp(); }},
        }}, 'Files Touched (' + codeImpact.length + ')'),
      ]),
    ]));

    if (state.filterMode === 'impact') {{
      app.appendChild(el('div', {{ className: 'steps-list' }}, codeImpact.map(f => el('div', {{ className: 'step-card' }}, [
        el('div', {{ className: 'step-top' }}, [
          el('span', {{ style: {{ fontFamily: 'var(--font-mono)', fontWeight: '700' }} }}, f.path),
          el('span', {{ className: 'badge' }}, 'Status: ' + (f.status || 'inspected')),
        ]),
        el('div', {{ className: 'step-narrative' }},
          'Read at steps: ' + ((f.reads || f.read_steps || []).map(n => '#' + n).join(', ') || 'none') +
          ' · Edited at steps: ' + ((f.edits || f.edit_steps || []).map(n => '#' + n).join(', ') || 'none') +
          ' · Verified at steps: ' + ((f.verified_by || f.verify_steps || []).map(n => '#' + n).join(', ') || 'none')
        ),
      ]))));
    }} else {{
      const list = el('div', {{ className: 'steps-list' }});
      steps.forEach((st, idx) => {{
        if (state.filterMode === 'pivots' && !st.is_pivot && st.status !== 'error' && !st.decision_text && st.kind !== 'context_load') return;
        list.appendChild(renderStepCard(st, idx));
      }});
      app.appendChild(list);
    }}
  }}

  window.addEventListener('keydown', (e) => {{
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
    if (e.key === 'ArrowRight') {{ e.preventDefault(); jumpToStepIdx(state.currentStepIdx + 1); }}
    else if (e.key === 'ArrowLeft') {{ e.preventDefault(); jumpToStepIdx(state.currentStepIdx - 1); }}
    else if (e.key === ' ') {{ e.preventDefault(); state.playing ? (stopPlayback(), renderApp()) : startPlayback(); }}
  }});

  renderApp();
}})();
</script>
</body>
</html>
"""
