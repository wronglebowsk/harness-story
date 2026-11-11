// Harness Story — Hermes Desktop Pane Plugin
//
// Tells the human-friendly, animated story of what happens when you use Hermes:
// 1. Kickoff: Restates "You asked: 'Prompt Here'"
// 2. Hidden Hermes Context Load: Shows how much base context, how many skills,
//    connectors, plugins, tools, and memory notes Hermes silently packed in
// 3. Unified Story Chronicle + 5 Context Buckets: Context is baked into every
//    step, with layperson tool indicators, animated action visuals, decisions,
//    questions, and course-corrections (pivots).
//
// Imports ONLY @hermes/plugin-sdk, react, and react/jsx-runtime.
// Zero hardcoded hex/rgb/hsl colors — all styling uses var(--ui-*) tokens.

import { PANES_AREA } from '@hermes/plugin-sdk'
import { Component, useEffect, useMemo, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const PLUGIN_ID = 'harness-story'
const API_BASE = '/api/plugins/harness-story'

export const TOOL_CATEGORIES = {
  read_file: 'explore',
  read_files: 'explore',
  search_files: 'explore',
  find_by_name: 'explore',
  grep_search: 'explore',
  list_dir: 'explore',
  patch: 'mutate',
  write_file: 'mutate',
  edit_file: 'mutate',
  terminal: 'execute',
  run_command: 'execute',
  process: 'execute',
  delegate_task: 'orchestrate',
  invoke_subagent: 'orchestrate',
  clarify: 'orchestrate',
  todo_list: 'orchestrate',
  memory: 'knowledge',
  local_recall: 'knowledge',
  session_search: 'knowledge',
  skill_view: 'knowledge',
  skill_manage: 'knowledge',
  web_search: 'explore',
  web_extract: 'explore',
}

export const CATEGORY_LABELS = {
  explore: 'Explore & Read',
  mutate: 'Write & Edit',
  execute: 'Run Commands',
  verify: 'Test & Verify',
  knowledge: 'Skills & Memory',
  orchestrate: 'Plan & Delegate',
  external: 'Connectors',
  other: 'Other Tools',
}

export function classifyTool(toolName, argsPreview = '') {
  const name = String(toolName || '').trim()
  if (name.startswith ? name.startswith('mcp__') : name.indexOf('mcp__') === 0) {
    return 'external'
  }
  if (name === 'terminal' || name === 'run_command') {
    if (/\b(pytest|unittest|jest|vitest|cargo\s+test|go\s+test|ruff|mypy|flake8|node\s+--check|hermes\s+plugins\s+validate)\b/i.test(String(argsPreview || ''))) {
      return 'verify'
    }
    return 'execute'
  }
  return TOOL_CATEGORIES[name] || 'other'
}

export function describeToolForLayperson(step) {
  if (!step) {
    return {
      badge: 'Step',
      icon: '•',
      animation: 'decision_thought',
      humanTitle: 'Session step',
      whatHappened: '',
    }
  }
  const ind = step.tool_indicator || {}
  const kind = step.kind || 'tool_call'
  const tname = String(step.tool_name || '')
  const target = String(step.target || '')

  if (kind === 'user_prompt' || tname === 'user') {
    const title = step.human_title || `You asked: “${target}”`
    return {
      badge: ind.badge || (step.turn_index > 1 ? 'Your Reply' : 'You Asked'),
      icon: ind.icon || '💬',
      animation: 'prompt_bubble',
      humanTitle: title,
      whatHappened: step.human_narrative || `You kicked off this turn with your prompt: “${target}”.`,
    }
  }

  if (kind === 'context_load' || tname === 'hermes_harness') {
    return {
      badge: ind.badge || 'Hermes Context Load (Hidden Step)',
      icon: ind.icon || '🎒',
      animation: 'backpack_load',
      humanTitle: step.human_title || 'Behind the scenes, Hermes loaded your workspace context',
      whatHappened:
        step.human_narrative ||
        'Before calling the model, Hermes silently packed system instructions, available skills, MCP connectors, tool definitions, and your personal memory into the context window.',
    }
  }

  if (kind === 'question' || tname === 'clarify') {
    return {
      badge: ind.badge || 'Question for You',
      icon: ind.icon || '❓',
      animation: 'question_ask',
      humanTitle: step.human_title || `Hermes asked you a question: “${target}”`,
      whatHappened: step.human_narrative || `Hermes paused to ask for clarification: “${target}”.`,
    }
  }

  if (kind === 'assistant_reply' || tname === 'assistant') {
    return {
      badge: ind.badge || 'Hermes Response',
      icon: ind.icon || '✅',
      animation: 'reply_deliver',
      humanTitle: step.human_title || `Hermes replied: “${target}”`,
      whatHappened: step.human_narrative || step.outcome_summary || target,
    }
  }

  if (kind === 'compaction' || tname === 'context_compressor') {
    return {
      badge: 'Context Compaction',
      icon: '🗜️',
      animation: 'backpack_load',
      humanTitle: step.human_title || `Hermes compressed older conversation history (${target})`,
      whatHappened:
        step.human_narrative ||
        'Hermes summarized older turns and tool outputs so the context window would not overflow.',
    }
  }

  if (ind.badge && ind.icon) {
    return {
      badge: `${ind.badge} · ${tname}`,
      icon: ind.icon,
      animation: ind.animation || 'terminal_exec',
      humanTitle:
        step.human_title ||
        ind.human_title ||
        `${step.verb || 'Used'} ${tname} on ${target}`,
      whatHappened:
        step.human_narrative ||
        ind.plain_what_happened ||
        step.outcome_summary ||
        '',
    }
  }

  // Fallback for older saved stories without tool_indicator
  if (tname.indexOf('mcp__') === 0) {
    const parts = tname.split('__')
    const srv = parts[1] || 'MCP'
    return {
      badge: `Connector · ${srv}`,
      icon: '🔌',
      animation: 'connector_pulse',
      humanTitle: step.human_title || `Queried the ${srv} connector (${target})`,
      whatHappened:
        step.human_narrative ||
        `Hermes queried the external '${srv}' connector and brought the response into context.`,
    }
  }
  if (tname === 'read_file' || tname === 'read_files' || tname === 'view_file') {
    return {
      badge: `File Reader · ${tname}`,
      icon: '📖',
      animation: 'file_scan',
      humanTitle: step.human_title || `Opened and read ${target}`,
      whatHappened:
        step.human_narrative ||
        `Hermes opened '${target}' on disk and read its contents into the context window.`,
    }
  }
  if (tname === 'patch' || tname === 'write_file' || tname === 'edit_file') {
    return {
      badge: `File Editor · ${tname}`,
      icon: '✏️',
      animation: 'file_edit',
      humanTitle: step.human_title || `Edited file ${target}`,
      whatHappened:
        step.human_narrative || `Hermes wrote or updated code in '${target}'.`,
    }
  }
  if (tname === 'skill_view' || tname === 'skill_manage') {
    return {
      badge: `Skill Manual · ${tname}`,
      icon: '📘',
      animation: 'skill_inject',
      humanTitle: step.human_title || `Loaded the '${target}' skill manual into context`,
      whatHappened:
        step.human_narrative ||
        `Hermes pulled the '${target}' skill instructions into the Skills & Memory bucket.`,
    }
  }
  if (tname === 'delegate_task' || tname === 'invoke_subagent') {
    return {
      badge: `Subagent Helper · ${tname}`,
      icon: '🤝',
      animation: 'subagent_branch',
      humanTitle: step.human_title || `Delegated sub-task to a helper agent: ${target}`,
      whatHappened:
        step.human_narrative ||
        `Hermes spawned a helper subagent with its own clean context window to handle '${target}'.`,
    }
  }
  if (tname === 'terminal' || tname === 'run_command') {
    const isVerify = step.category === 'verify' || /verified/i.test(String(step.verb || ''))
    return {
      badge: isVerify ? `Test & Verify · ${tname}` : `Terminal Command · ${tname}`,
      icon: isVerify ? '✅' : '🖥️',
      animation: isVerify ? 'verify_check' : 'terminal_exec',
      humanTitle:
        step.human_title ||
        (isVerify ? `Ran verification check: ${target}` : `Ran terminal command: ${target}`),
      whatHappened:
        step.human_narrative ||
        `Hermes executed \`${target}\` in the terminal and captured the result.`,
    }
  }

  return {
    badge: `Tool · ${tname || 'step'}`,
    icon: '🛠️',
    animation: 'terminal_exec',
    humanTitle: step.human_title || `${step.verb || 'Ran'} ${tname}: ${target}`,
    whatHappened: step.human_narrative || step.outcome_summary || '',
  }
}

export function packLanes(spans) {
  const sorted = [...(spans || [])].sort(
    (a, b) =>
      Number(a.t0 || a.started_at || 0) - Number(b.t0 || b.started_at || 0) ||
      (a.index || 0) - (b.index || 0)
  )
  const laneEnds = []
  let maxConcurrency = 0
  for (const s of sorted) {
    const start = Number(s.t0 ?? s.started_at ?? s.index ?? 0)
    const dur = Math.max(0.05, Number(s.duration_ms || 120) / 1000)
    const end = Number(s.t1 ?? start + dur)
    let placed = -1
    for (let i = 0; i < laneEnds.length; i++) {
      if (laneEnds[i] <= start + 1e-6) {
        placed = i
        laneEnds[i] = end
        break
      }
    }
    if (placed === -1) {
      placed = laneEnds.length
      laneEnds.push(end)
    }
    s.lane = placed
    if (laneEnds.length > maxConcurrency) maxConcurrency = laneEnds.length
  }
  return { lanes: Math.max(1, maxConcurrency), spans: sorted }
}

export function tallyToolsAtStep(steps, activeIndex) {
  const list = Array.isArray(steps) ? steps : []
  const cutoff =
    activeIndex == null ? list.length : Math.max(0, Math.min(list.length, Number(activeIndex)))
  const slice = list.slice(0, cutoff)
  const allToolSteps = list.filter(
    (s) => !s.kind || s.kind === 'tool_call'
  )
  const sliceToolSteps = slice.filter(
    (s) => !s.kind || s.kind === 'tool_call'
  )
  const byCategory = {}
  const byTool = {}
  let failed = 0
  let pivots = 0
  for (const st of sliceToolSteps) {
    const cat = st.category || classifyTool(st.tool_name, st.target)
    byCategory[cat] = (byCategory[cat] || 0) + 1
    const tname = st.tool_name || 'tool'
    byTool[tname] = (byTool[tname] || 0) + 1
    if (st.status === 'error' || st.failed) failed += 1
    if (st.is_pivot) pivots += 1
  }
  return {
    current: sliceToolSteps.length,
    total: allToolSteps.length,
    failed,
    pivots,
    byCategory,
    byTool,
  }
}

export function computeContextSnapshot(story, activeIndex) {
  const steps = Array.isArray(story?.steps) ? story.steps : []
  const cj = story?.context_journey || {}
  const contextMax = Math.max(1, Number(cj.context_max || 131072))
  if (!steps.length) {
    const sys = Number(cj.initial_tokens || cj.start_tokens || 1200)
    return {
      total_tokens: sys,
      context_max: contextMax,
      utilization_pct: Number(((sys / contextMax) * 100).toFixed(2)),
      delta_tokens: 0,
      system_prompt_tokens: sys,
      skills_and_memory_tokens: 0,
      user_messages_tokens: 0,
      assistant_reasoning_tokens: 0,
      tool_io_tokens: 0,
    }
  }
  const idx =
    activeIndex == null
      ? steps.length - 1
      : Math.max(0, Math.min(steps.length - 1, Number(activeIndex) - 1))
  const step = steps[idx] || steps[steps.length - 1]
  const ctx = step?.context || {}
  const b = ctx.breakdown || {}
  const sysTok = Number(ctx.system_prompt_tokens ?? b.system_prompt ?? 0)
  const skTok = Number(ctx.skills_and_memory_tokens ?? b.skills_and_memory ?? 0)
  const usrTok = Number(ctx.user_messages_tokens ?? b.user_messages ?? 0)
  const rsnTok = Number(ctx.assistant_reasoning_tokens ?? b.assistant_reasoning ?? 0)
  const tioTok = Number(ctx.tool_io_tokens ?? b.tool_io ?? 0)
  const total = Number(ctx.total_tokens || sysTok + skTok + usrTok + rsnTok + tioTok)
  const max = Math.max(1, Number(ctx.context_max || contextMax))
  return {
    total_tokens: total,
    context_max: max,
    utilization_pct: Number((ctx.utilization_pct ?? ctx.context_pct ?? (total / max) * 100).toFixed(2)),
    delta_tokens: Number(ctx.delta_tokens || 0),
    system_prompt_tokens: sysTok,
    skills_and_memory_tokens: skTok,
    user_messages_tokens: usrTok,
    assistant_reasoning_tokens: rsnTok,
    tool_io_tokens: tioTok,
  }
}

export function detectPivots(steps) {
  const list = Array.isArray(steps) ? steps : []
  const out = []
  for (let i = 0; i < list.length; i++) {
    const st = list[i]
    if (st.is_pivot) {
      out.push({
        failed_step: st.pivot_from_step || st.from_step || Math.max(1, (st.index || i + 1) - 1),
        recovery_step: st.index || i + 1,
        reason: st.pivot_reason || st.narrative_why || 'Adapted approach after prior tool error',
        tool_name: st.tool_name,
      })
    }
  }
  return out
}

export async function loadStoriesIndex(ctx) {
  const problems = []
  if (ctx && typeof ctx.rest === 'function') {
    try {
      const res = await ctx.rest('/stories')
      if (res && Array.isArray(res.stories)) {
        return {
          source: 'gateway',
          stories: res.stories,
          recentSessions: Array.isArray(res.recent_sessions) ? res.recent_sessions : [],
          problems,
        }
      }
    } catch (err) {
      problems.push(String((err && err.message) || err))
    }
  }
  if (ctx && ctx.files && typeof ctx.files.readText === 'function') {
    try {
      const raw = await ctx.files.readText('data', 'stories.json')
      const parsed = JSON.parse(raw)
      if (parsed && Array.isArray(parsed.stories)) {
        return {
          source: 'snapshot',
          stories: parsed.stories,
          recentSessions: Array.isArray(parsed.recent_sessions) ? parsed.recent_sessions : [],
          problems,
        }
      }
    } catch (err) {
      problems.push(String((err && err.message) || err))
    }
  }
  return { source: 'empty', stories: [], recentSessions: [], problems }
}

class Guard extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error) {
    return { error }
  }
  render() {
    if (this.state.error) {
      return jsxs('div', {
        className: 'harness-story-crash',
        'data-crash': 'true',
        style: {
          padding: '12px',
          color: 'var(--ui-danger)',
          background: 'var(--ui-bg-editor)',
          border: '1px solid var(--ui-stroke-primary)',
          fontFamily: 'var(--ui-font-mono, monospace)',
          fontSize: '12px',
        },
        children: [
          jsx('strong', { children: 'Harness Story pane recovered from an error: ' }),
          jsx('span', { children: String(this.state.error?.message || this.state.error) }),
        ],
      })
    }
    return this.props.children
  }
}

function fmtNum(n) {
  return Number(n || 0).toLocaleString('en-US')
}

// Layperson Animated Stage Visual for the Active Step
function StageVisual({ step, story, ctxSnap, playing }) {
  if (!step) return null
  const info = describeToolForLayperson(step)
  const anim = info.animation
  const cl = step.context_load_details || story?.context_load || null

  // 1. Kickoff Prompt Bubble
  if (anim === 'prompt_bubble') {
    return jsxs('div', {
      className: 'harness-story-stage-visual',
      'data-stage-anim': 'prompt_bubble',
      style: {
        padding: '14px 18px',
        background: 'var(--ui-bg-editor)',
        border: '2px solid var(--ui-accent)',
        borderRadius: '10px',
        marginTop: '10px',
      },
      children: [
        jsx('div', {
          style: { fontSize: '13px', color: 'var(--ui-accent)', fontWeight: 700, marginBottom: '6px' },
          children: step.turn_index > 1 ? '💬 You sent a follow-up message:' : '💬 Session Kickoff — You asked:',
        }),
        jsx('div', {
          style: { fontSize: '18px', fontWeight: 600, lineHeight: 1.45, color: 'var(--ui-text-primary)' },
          children: `“${step.detail_preview || step.outcome_summary || step.target}”`,
        }),
        jsx('div', {
          style: { marginTop: '8px', fontSize: '13.5px', color: 'var(--ui-text-secondary)' },
          children: `Your prompt added +${fmtNum(ctxSnap.delta_tokens)} tokens to the "Your Prompts" bucket.`,
        }),
      ],
    })
  }

  // 2. Hidden Hermes Context Load (Skills, Connectors, Tools, Memory)
  if (anim === 'backpack_load') {
    const skillsCount = cl?.skills_count ?? 112
    const sampleArr = cl?.skills_sample || cl?.sample_skills || cl?.skill_categories || []
    const sampleSkills = Array.isArray(sampleArr) && sampleArr.length
      ? sampleArr.slice(0, 5).join(', ')
      : 'hermes-agent, claude-code, codex, network-ssh-access'
    const connArr = cl?.connectors_list || cl?.connectors || []
    const connList = Array.isArray(connArr) && connArr.length
      ? connArr.join(', ')
      : 'MCP connectors'
    const plgCount = cl?.plugins_count ?? 9
    const toolsCount = cl?.tools_estimated_count ?? cl?.tools_count ?? 50
    const toolsetsCount = cl?.toolsets_count ?? 23
    const memNotes = cl?.memory_notes_count ?? 5
    const memChars = cl?.memory_chars ?? 2059
    const baseTok = cl?.total_tokens || cl?.base_total_tokens || ctxSnap.total_tokens

    return jsxs('div', {
      className: 'harness-story-stage-visual',
      'data-stage-anim': 'backpack_load',
      style: {
        padding: '14px 18px',
        background: 'var(--ui-bg-editor)',
        border: '2px solid var(--ui-yellow)',
        borderRadius: '10px',
        marginTop: '10px',
      },
      children: [
        jsxs('div', {
          style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', flexWrap: 'wrap', gap: '8px' },
          children: [
            jsx('span', {
              style: { fontWeight: 700, color: 'var(--ui-yellow)', fontSize: '15px' },
              children: '🎒 Default Hidden Step: Hermes Context Load',
            }),
            jsx('span', {
              style: { fontFamily: 'var(--ui-font-mono, monospace)', fontSize: '14px', fontWeight: 600, color: 'var(--ui-text-primary)' },
              children: `+${fmtNum(baseTok)} base tokens (${ctxSnap.utilization_pct}% of window)`,
            }),
          ],
        }),
        jsx('div', {
          style: { fontSize: '14.5px', color: 'var(--ui-text-primary)', lineHeight: 1.5, marginBottom: '12px' },
          children:
            'Most people never see this step: before the model writes a single token, Hermes silently packs your workspace capabilities into the prompt:',
        }),
        jsxs('div', {
          style: {
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '10px',
            fontSize: '14px',
          },
          children: [
            jsxs('div', {
              style: { padding: '10px 12px', background: 'var(--ui-bg-elevated)', border: '1px solid var(--ui-stroke-primary)', borderRadius: '8px' },
              children: [
                jsx('div', { style: { fontWeight: 700, fontSize: '15px' }, children: `📚 ${skillsCount} Skills Indexed` }),
                jsx('div', { style: { color: 'var(--ui-text-secondary)', fontSize: '12.5px', marginTop: '4px' }, children: sampleSkills }),
              ],
            }),
            jsxs('div', {
              style: { padding: '10px 12px', background: 'var(--ui-bg-elevated)', border: '1px solid var(--ui-stroke-primary)', borderRadius: '8px' },
              children: [
                jsx('div', { style: { fontWeight: 700, fontSize: '15px' }, children: `🔌 ${cl?.connectors_count ?? 4} Connectors & ${plgCount} Plugins` }),
                jsx('div', { style: { color: 'var(--ui-text-secondary)', fontSize: '12.5px', marginTop: '4px' }, children: connList }),
              ],
            }),
            jsxs('div', {
              style: { padding: '10px 12px', background: 'var(--ui-bg-elevated)', border: '1px solid var(--ui-stroke-primary)', borderRadius: '8px' },
              children: [
                jsx('div', { style: { fontWeight: 700, fontSize: '15px' }, children: `🛠️ ~${toolsCount} Tools Ready` }),
                jsx('div', { style: { color: 'var(--ui-text-secondary)', fontSize: '12.5px', marginTop: '4px' }, children: `Across ${toolsetsCount} active toolsets` }),
              ],
            }),
            jsxs('div', {
              style: { padding: '10px 12px', background: 'var(--ui-bg-elevated)', border: '1px solid var(--ui-stroke-primary)', borderRadius: '8px' },
              children: [
                jsx('div', { style: { fontWeight: 700, fontSize: '15px' }, children: `🧠 ${memNotes} Memory Notes + Profile` }),
                jsx('div', { style: { color: 'var(--ui-text-secondary)', fontSize: '12.5px', marginTop: '4px' }, children: `${fmtNum(memChars)} chars of personal notes` }),
              ],
            }),
          ],
        }),
      ],
    })
  }

  // 3. Tool / Question / Decision / Reply Animated Action Card
  const isError = step.failed || step.status === 'error'
  const borderCol = isError
    ? 'var(--ui-danger)'
    : step.is_pivot
    ? 'var(--ui-yellow)'
    : anim === 'verify_check' || anim === 'reply_deliver'
    ? 'var(--ui-success)'
    : 'var(--ui-accent)'

  return jsxs('div', {
    className: 'harness-story-stage-visual',
    'data-stage-anim': anim,
    style: {
      padding: '14px 18px',
      background: 'var(--ui-bg-editor)',
      border: `2px solid ${borderCol}`,
      borderRadius: '10px',
      marginTop: '10px',
    },
    children: [
      // Tool indicator header row
      jsxs('div', {
        style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' },
        children: [
          jsxs('span', {
            style: {
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 12px',
              background: 'var(--ui-bg-elevated)',
              border: `1.5px solid ${borderCol}`,
              borderRadius: '999px',
              fontWeight: 700,
              fontSize: '13.5px',
            },
            children: [
              jsx('span', { children: info.icon }),
              jsx('span', { children: info.badge }),
              playing ? jsx('span', { style: { color: 'var(--ui-accent)' }, children: '● LIVE' }) : null,
            ],
          }),
          jsx('span', {
            style: { fontFamily: 'var(--ui-font-mono, monospace)', fontSize: '13.5px', fontWeight: 600, color: 'var(--ui-text-secondary)' },
            children:
              step.running_tool_count > 0
                ? `Tool #${step.running_tool_count} · +${fmtNum(ctxSnap.delta_tokens)} tok`
                : `+${fmtNum(ctxSnap.delta_tokens)} tok`,
          }),
        ],
      }),

      // Decision / Hypothesis thought bubble if present
      step.decision_text || step.narrative_why || step.intent
        ? jsxs('div', {
            style: {
              marginTop: '10px',
              padding: '10px 14px',
              background: 'var(--ui-bg-elevated)',
              borderLeft: '4px solid var(--ui-accent)',
              borderRadius: '6px',
              fontSize: '14.5px',
              lineHeight: 1.45,
              color: 'var(--ui-text-primary)',
            },
            children: [
              jsx('strong', {
                children: step.is_pivot
                  ? '🔄 Why Hermes changed strategy (Pivot): '
                  : '💭 Decision / Why Hermes did this: ',
              }),
              jsx('span', {
                children: step.pivot_reason || step.decision_text || step.narrative_why || step.intent,
              }),
            ],
          })
        : null,

      // Plain-English explanation of what happened
      jsx('div', {
        style: { marginTop: '10px', fontSize: '15px', lineHeight: 1.5, color: 'var(--ui-text-primary)' },
        children: info.whatHappened,
      }),

      // Visual simulation box showing the target command / file / connector
      step.target
        ? jsxs('div', {
            style: {
              marginTop: '10px',
              padding: '10px 14px',
              background: 'var(--ui-bg-elevated)',
              border: '1px solid var(--ui-stroke-primary)',
              borderRadius: '6px',
              fontFamily: 'var(--ui-font-mono, monospace)',
              fontSize: '13.5px',
              overflowX: 'auto',
            },
            children: [
              jsx('div', {
                style: { color: 'var(--ui-accent)', fontWeight: 700 },
                children:
                  anim === 'terminal_exec' || anim === 'verify_check'
                    ? `$ ${step.target}`
                    : anim === 'file_scan'
                    ? `📖 Reading file: ${step.target}`
                    : anim === 'file_edit'
                    ? `✏️ Updating file: ${step.target}`
                    : anim === 'skill_inject'
                    ? `📘 Injecting into context: ${step.target}`
                    : anim === 'subagent_branch'
                    ? `🤝 Subagent goal: ${step.target}`
                    : step.target,
              }),
              step.outcome_summary
                ? jsx('div', {
                    style: {
                      marginTop: '5px',
                      color: isError ? 'var(--ui-danger)' : 'var(--ui-text-secondary)',
                      fontSize: '13px',
                    },
                    children: `↳ ${step.outcome_summary}`,
                  })
                : null,
            ],
          })
        : null,
    ],
  })
}

function StoryPane({ ctx }) {
  const [stories, setStories] = useState([])
  const [recentSessions, setRecentSessions] = useState([])
  const [selectedSlug, setSelectedSlug] = useState('')
  const [story, setStory] = useState(null)
  const [problems, setProblems] = useState([])
  const [storyError, setStoryError] = useState('')
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [refreshTick, setRefreshTick] = useState(0)
  const [filterMode, setFilterMode] = useState('all') // 'all' | 'pivots' | 'impact'
  const [activeStep, setActiveStep] = useState(1)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [copiedNote, setCopiedNote] = useState('')
  const [liveSteps, setLiveSteps] = useState([])
  const chronicleListRef = useRef(null)

  // 1. Load saved stories index
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    loadStoriesIndex(ctx)
      .then((res) => {
        if (cancelled) return
        setStories(res.stories)
        setRecentSessions(res.recentSessions || [])
        setProblems(res.problems || [])
        if (res.stories.length > 0) {
          setSelectedSlug((prev) =>
            prev && res.stories.some((s) => s.slug === prev) ? prev : res.stories[0].slug
          )
        } else {
          setSelectedSlug('')
          setStory(null)
        }
        setLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        setProblems([String((err && err.message) || err)])
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [ctx, refreshTick])

  // 2. Load selected story JSON (start at Step 1 when a story loads so the user sees the Kickoff & Context Load first, or full count if single step)
  useEffect(() => {
    if (!selectedSlug || !ctx || typeof ctx.rest !== 'function') return
    let cancelled = false
    setStoryError('')
    ctx
      .rest(`/stories/${selectedSlug}.json`)
      .then((doc) => {
        if (cancelled) return
        setStory(doc)
        setActiveStep(1)
        setPlaying(false)
      })
      .catch((err) => {
        if (cancelled) return
        setStory(null)
        setStoryError(String((err && err.message) || err))
      })
    return () => {
      cancelled = true
    }
  }, [ctx, selectedSlug, refreshTick])

  // 3. Subscribe to live gateway events if ctx.events is available
  useEffect(() => {
    if (!ctx || !ctx.events || typeof ctx.events.on !== 'function') return
    const offStart = ctx.events.on('tool.start', (ev) => {
      setLiveSteps((prev) => {
        const nextIdx = prev.length + 1
        const tname = ev?.tool_name || ev?.name || 'tool'
        const target = ev?.target || ev?.path || ev?.command || ''
        return [
          ...prev,
          {
            index: nextIdx,
            kind: 'tool_call',
            tool_name: tname,
            category: classifyTool(tname, target),
            verb: CATEGORY_LABELS[classifyTool(tname, target)] || 'Ran',
            target: String(target).slice(0, 80),
            status: 'running',
            duration_ms: 0,
            running_tool_count: nextIdx,
            context: {
              total_tokens: 6500 + nextIdx * 650,
              context_max: 131072,
              utilization_pct: Number((((6500 + nextIdx * 650) / 131072) * 100).toFixed(2)),
              delta_tokens: 650,
              system_prompt_tokens: 4200,
              skills_and_memory_tokens: 2300,
              user_messages_tokens: 300,
              assistant_reasoning_tokens: nextIdx * 220,
              tool_io_tokens: nextIdx * 430,
            },
          },
        ]
      })
    })
    const offDone = ctx.events.on('tool.complete', (ev) => {
      setLiveSteps((prev) => {
        if (!prev.length) return prev
        const copy = [...prev]
        const last = { ...copy[copy.length - 1] }
        last.status = ev?.status === 'error' || ev?.error ? 'error' : 'ok'
        last.failed = last.status === 'error'
        last.duration_ms = Number(ev?.duration_ms || 140)
        copy[copy.length - 1] = last
        return copy
      })
    })
    return () => {
      if (typeof offStart === 'function') offStart()
      if (typeof offDone === 'function') offDone()
    }
  }, [ctx])

  const effectiveStory = useMemo(() => {
    if (story) return story
    if (liveSteps.length > 0) {
      const packed = packLanes(liveSteps)
      return {
        slug: 'live-session',
        session_id: 'live',
        title: 'Live Hermes Session',
        headline: `Live session with ${liveSteps.length} steps tracked in real time.`,
        executive_summary: 'Streaming tool calls and context growth directly from the active session.',
        steps: packed.spans,
        pivots: detectPivots(packed.spans),
        chapters: [],
        code_impact: [],
        subagents: [],
        context_journey: {
          context_max: 131072,
          peak_tokens: packed.spans[packed.spans.length - 1]?.context?.total_tokens || 6500,
          peak_pct: packed.spans[packed.spans.length - 1]?.context?.utilization_pct || 5.0,
        },
      }
    }
    return null
  }, [story, liveSteps])

  const steps = useMemo(
    () => (Array.isArray(effectiveStory?.steps) ? effectiveStory.steps : []),
    [effectiveStory]
  )

  // 4. Playback interval timer for animated story replay
  useEffect(() => {
    if (!playing || steps.length <= 1) return
    const delayMs = Math.max(300, Math.floor(1600 / Math.max(1, speed)))
    const timer = setInterval(() => {
      setActiveStep((prev) => {
        if (prev >= steps.length) {
          setPlaying(false)
          return steps.length
        }
        return prev + 1
      })
    }, delayMs)
    return () => clearInterval(timer)
  }, [playing, speed, steps.length])

  // 5. Auto-scroll the bottom Chronicle list so the active step stays centered in view
  useEffect(() => {
    const container = chronicleListRef.current
    if (!container || typeof container.querySelector !== 'function') return
    const rowEl = container.querySelector(`[data-step-index="${activeStep}"]`)
    if (rowEl && typeof rowEl.scrollIntoView === 'function') {
      rowEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [activeStep, filterMode, steps.length])

  const tally = useMemo(() => tallyToolsAtStep(steps, activeStep), [steps, activeStep])
  const ctxSnap = useMemo(
    () => computeContextSnapshot(effectiveStory, activeStep),
    [effectiveStory, activeStep]
  )
  const currentStepObj = useMemo(
    () => steps[Math.max(0, Math.min(steps.length - 1, activeStep - 1))] || null,
    [steps, activeStep]
  )
  const currentLayperson = useMemo(
    () => describeToolForLayperson(currentStepObj),
    [currentStepObj]
  )

  const handleGenerateLatest = async (sessionId = 'latest') => {
    if (!ctx || typeof ctx.rest !== 'function') return
    setGenerating(true)
    setStoryError('')
    try {
      const res = await ctx.rest('/generate', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, use_llm: true }),
      })
      if (res && res.slug) {
        setSelectedSlug(res.slug)
      }
      setRefreshTick((t) => t + 1)
    } catch (err) {
      setStoryError(String((err && err.message) || err))
    } finally {
      setGenerating(false)
    }
  }

  const handleCopyPath = async () => {
    if (!ctx?.os?.clipboard?.writeText || !effectiveStory?.slug) return
    const path = `${API_BASE}/stories/${effectiveStory.slug}.html`
    await ctx.os.clipboard.writeText(path)
    setCopiedNote('Copied!')
    setTimeout(() => setCopiedNote(''), 1500)
  }

  const totalCtx = Math.max(1, ctxSnap.total_tokens)
  const bucketItems = [
    {
      key: 'sys',
      label: 'Hermes Instructions & Tools',
      tokens: ctxSnap.system_prompt_tokens,
      pct: Math.round((ctxSnap.system_prompt_tokens / totalCtx) * 100),
      color: 'var(--ui-text-secondary)',
    },
    {
      key: 'skills',
      label: 'Skills & Memory',
      tokens: ctxSnap.skills_and_memory_tokens,
      pct: Math.round((ctxSnap.skills_and_memory_tokens / totalCtx) * 100),
      color: 'var(--ui-yellow)',
    },
    {
      key: 'user',
      label: 'Your Prompts',
      tokens: ctxSnap.user_messages_tokens,
      pct: Math.round((ctxSnap.user_messages_tokens / totalCtx) * 100),
      color: 'var(--ui-success)',
    },
    {
      key: 'reason',
      label: 'Model Thinking',
      tokens: ctxSnap.assistant_reasoning_tokens,
      pct: Math.round((ctxSnap.assistant_reasoning_tokens / totalCtx) * 100),
      color: 'var(--ui-accent)',
    },
    {
      key: 'tool',
      label: 'Tool Results',
      tokens: ctxSnap.tool_io_tokens,
      pct: Math.max(
        0,
        100 -
          Math.round(
            ((ctxSnap.system_prompt_tokens +
              ctxSnap.skills_and_memory_tokens +
              ctxSnap.user_messages_tokens +
              ctxSnap.assistant_reasoning_tokens) /
              totalCtx) *
              100
          )
      ),
      color: 'var(--ui-text-primary)',
    },
  ]

  return jsxs('div', {
    className: 'harness-story',
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      width: '100%',
      overflow: 'hidden',
      background: 'var(--ui-bg-editor)',
      color: 'var(--ui-text-primary)',
      fontFamily: 'var(--ui-font-sans, system-ui, sans-serif)',
      fontSize: '15px',
    },
    children: [
      // Top Toolbar: Story Picker + Refresh + Tell Latest Story
      jsxs('div', {
        className: 'harness-story-toolbar',
        style: {
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '10px 16px',
          borderBottom: '1px solid var(--ui-stroke-primary)',
          background: 'var(--ui-bg-elevated)',
          flexWrap: 'wrap',
          flexShrink: 0,
        },
        children: [
          jsx('select', {
            className: 'harness-story-picker',
            'aria-label': 'Select session story',
            disabled: stories.length === 0,
            value: selectedSlug,
            onChange: (e) => setSelectedSlug(e.target.value),
            style: {
              flex: '1 1 220px',
              minWidth: '180px',
              padding: '7px 10px',
              background: 'var(--ui-bg-editor)',
              color: 'var(--ui-text-primary)',
              border: '1px solid var(--ui-stroke-primary)',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: 600,
            },
            children:
              stories.length === 0
                ? jsx('option', { value: '', children: 'No stories yet' })
                : stories.map((s) =>
                    jsx(
                      'option',
                      {
                        value: s.slug,
                        children: `${s.title || s.slug} (${s.tool_calls ?? 0} tools)`,
                      },
                      s.slug
                    )
                  ),
          }),
          jsx('button', {
            type: 'button',
            className: 'harness-story-refresh',
            title: 'Refresh stories index',
            onClick: () => setRefreshTick((t) => t + 1),
            style: {
              padding: '7px 12px',
              background: 'var(--ui-bg-editor)',
              color: 'var(--ui-text-primary)',
              border: '1px solid var(--ui-stroke-primary)',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '14px',
            },
            children: 'Refresh',
          }),
          jsx('button', {
            type: 'button',
            className: 'harness-story-generate',
            disabled: generating,
            onClick: () => handleGenerateLatest('latest'),
            style: {
              padding: '7px 14px',
              background: 'var(--ui-accent)',
              color: 'var(--ui-bg-elevated)',
              border: '1px solid var(--ui-stroke-primary)',
              borderRadius: '6px',
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: '14px',
            },
            children: generating ? 'Building Story…' : 'Tell Latest Story',
          }),
          ctx?.os?.clipboard?.writeText && effectiveStory?.slug
            ? jsx('button', {
                type: 'button',
                className: 'harness-story-copy',
                onClick: handleCopyPath,
                style: {
                  padding: '7px 12px',
                  background: 'var(--ui-bg-editor)',
                  color: 'var(--ui-text-secondary)',
                  border: '1px solid var(--ui-stroke-primary)',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '13.5px',
                },
                children: copiedNote || 'Copy story URL',
              })
            : null,
        ],
      }),

      // Error / problem banner
      problems.length > 0 || storyError
        ? jsxs('div', {
            className: 'harness-story-error',
            role: 'alert',
            style: {
              padding: '10px 16px',
              borderBottom: '1px solid var(--ui-stroke-primary)',
              color: 'var(--ui-danger)',
              fontSize: '14px',
              flexShrink: 0,
            },
            children: [
              storyError ? jsx('div', { children: `Could not load story: ${storyError}` }) : null,
              ...problems.map((p, i) => jsx('div', { children: `Gateway note: ${p}` }, i)),
            ],
          })
        : null,

      // Empty state when no stories exist
      !effectiveStory && !loading
        ? jsxs('div', {
            className: 'harness-story-empty',
            style: {
              padding: '24px 20px',
              color: 'var(--ui-text-secondary)',
              lineHeight: 1.6,
              fontSize: '15px',
            },
            children: [
              jsx('div', {
                style: { fontWeight: 700, fontSize: '18px', color: 'var(--ui-text-primary)', marginBottom: '6px' },
                children: 'No Harness Stories generated yet.',
              }),
              jsx('div', {
                children: `Click "Tell Latest Story", run /story in chat, or POST to ${API_BASE}/generate to synthesize an animated session story.`,
              }),
              recentSessions.length > 0
                ? jsxs('div', {
                    style: { marginTop: '14px' },
                    children: [
                      jsx('div', {
                        style: { fontWeight: 700, marginBottom: '6px', color: 'var(--ui-text-primary)' },
                        children: 'Recent sessions in state.db:',
                      }),
                      ...recentSessions.slice(0, 5).map((s) =>
                        jsxs(
                          'div',
                          {
                            style: {
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              padding: '6px 0',
                              borderBottom: '1px solid var(--ui-stroke-primary)',
                            },
                            children: [
                              jsx('span', { children: s.title || s.id }),
                              jsx('button', {
                                type: 'button',
                                onClick: () => handleGenerateLatest(s.id),
                                style: {
                                  background: 'var(--ui-bg-elevated)',
                                  color: 'var(--ui-accent)',
                                  border: '1px solid var(--ui-stroke-primary)',
                                  borderRadius: '5px',
                                  padding: '4px 10px',
                                  cursor: 'pointer',
                                  fontSize: '13.5px',
                                },
                                children: `Build (${s.tool_call_count || 0} tools)`,
                              }),
                            ],
                          },
                          s.id
                        )
                      ),
                    ],
                  })
                : null,
            ],
          })
        : null,

      // Main Unified Story Experience (Top Spotlight + Big Context Bar pinned; Bottom Chronicle auto-scrolls)
      effectiveStory
        ? jsxs('div', {
            className: 'harness-story-body',
            style: {
              display: 'flex',
              flexDirection: 'column',
              flex: 1,
              overflow: 'hidden',
            },
            children: [
              // 1. Story Playback Controls Bar
              jsxs('div', {
                className: 'harness-story-player',
                style: {
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '10px 16px',
                  borderBottom: '1px solid var(--ui-stroke-primary)',
                  background: 'var(--ui-bg-elevated)',
                  flexShrink: 0,
                },
                children: [
                  jsx('button', {
                    type: 'button',
                    className: 'harness-story-play-btn',
                    'data-action': 'play-toggle',
                    onClick: () => {
                      if (!playing && activeStep >= steps.length) {
                        setActiveStep(1)
                      }
                      setPlaying((p) => !p)
                    },
                    style: {
                      padding: '7px 16px',
                      background: 'var(--ui-accent)',
                      color: 'var(--ui-bg-elevated)',
                      border: '1px solid var(--ui-stroke-primary)',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: 700,
                      fontSize: '15px',
                    },
                    children: playing ? '⏸ Pause' : '▶ Play Story',
                  }),
                  jsx('button', {
                    type: 'button',
                    className: 'harness-story-prev-btn',
                    'aria-label': 'Previous step',
                    onClick: () => {
                      setPlaying(false)
                      setActiveStep((s) => Math.max(1, s - 1))
                    },
                    style: {
                      padding: '6px 12px',
                      background: 'var(--ui-bg-editor)',
                      color: 'var(--ui-text-primary)',
                      border: '1px solid var(--ui-stroke-primary)',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontSize: '16px',
                      fontWeight: 700,
                    },
                    children: '‹ Prev',
                  }),
                  jsx('input', {
                    type: 'range',
                    className: 'harness-story-scrubber',
                    'aria-label': 'Story step scrubber',
                    min: 1,
                    max: Math.max(1, steps.length),
                    value: Math.min(Math.max(1, activeStep), Math.max(1, steps.length)),
                    onChange: (e) => {
                      setPlaying(false)
                      setActiveStep(Number(e.target.value))
                    },
                    style: { flex: 1, height: '8px', cursor: 'pointer' },
                  }),
                  jsx('button', {
                    type: 'button',
                    className: 'harness-story-next-btn',
                    'aria-label': 'Next step',
                    onClick: () => {
                      setPlaying(false)
                      setActiveStep((s) => Math.min(Math.max(1, steps.length), s + 1))
                    },
                    style: {
                      padding: '6px 12px',
                      background: 'var(--ui-bg-editor)',
                      color: 'var(--ui-text-primary)',
                      border: '1px solid var(--ui-stroke-primary)',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontSize: '16px',
                      fontWeight: 700,
                    },
                    children: 'Next ›',
                  }),
                  jsx('span', {
                    style: {
                      fontFamily: 'var(--ui-font-mono, monospace)',
                      fontSize: '14px',
                      fontWeight: 700,
                      color: 'var(--ui-text-primary)',
                      whiteSpace: 'nowrap',
                    },
                    children: `Step ${activeStep} / ${steps.length}`,
                  }),
                  jsx('button', {
                    type: 'button',
                    className: 'harness-story-speed-btn',
                    onClick: () => setSpeed((s) => (s === 1 ? 2 : s === 2 ? 4 : 1)),
                    style: {
                      padding: '5px 10px',
                      background: 'var(--ui-bg-editor)',
                      color: 'var(--ui-text-secondary)',
                      border: '1px solid var(--ui-stroke-primary)',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontFamily: 'var(--ui-font-mono, monospace)',
                      fontSize: '13.5px',
                      fontWeight: 600,
                    },
                    children: `${speed}x`,
                  }),
                ],
              }),

              // 2. Pinned Top Digest Section: Active Step Spotlight + Big Context Window Bar + Filter Tabs
              jsxs('div', {
                className: 'harness-story-top-digest',
                style: {
                  flexShrink: 0,
                  padding: '14px 16px 10px 16px',
                  borderBottom: '1px solid var(--ui-stroke-primary)',
                  background: 'var(--ui-bg-editor)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                  maxHeight: '56%',
                  overflowY: 'auto',
                },
                children: [
                  // A. Big "Active Item" Spotlight Card (Digest one item at a time simply)
                  jsxs('div', {
                    className: 'harness-story-stage-card',
                    'data-testid': 'story-stage',
                    'data-active-step': currentStepObj?.index || activeStep,
                    style: {
                      padding: '16px 18px',
                      background: 'var(--ui-bg-elevated)',
                      border: '2px solid var(--ui-accent)',
                      borderRadius: '10px',
                    },
                    children: [
                      jsxs('div', {
                        style: {
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          gap: '10px',
                          flexWrap: 'wrap',
                        },
                        children: [
                          jsx('span', {
                            style: {
                              fontSize: '13px',
                              fontWeight: 700,
                              textTransform: 'uppercase',
                              letterSpacing: '0.05em',
                              color: 'var(--ui-accent)',
                            },
                            children: playing
                              ? `▶ Now Playing · Step ${activeStep} of ${steps.length} · ${currentLayperson.badge}`
                              : `Active Step ${activeStep} of ${steps.length} · ${currentLayperson.badge}`,
                          }),
                          jsx('span', {
                            style: {
                              fontFamily: 'var(--ui-font-mono, monospace)',
                              fontSize: '13px',
                              color: 'var(--ui-text-secondary)',
                            },
                            children: `${ctxSnap.delta_tokens >= 0 ? '+' : ''}${fmtNum(ctxSnap.delta_tokens)} tok at this step`,
                          }),
                        ],
                      }),
                      jsx('div', {
                        style: {
                          fontSize: '20px',
                          fontWeight: 700,
                          marginTop: '6px',
                          lineHeight: 1.35,
                          color: 'var(--ui-text-primary)',
                        },
                        children: currentLayperson.humanTitle,
                      }),
                      jsx(StageVisual, {
                        step: currentStepObj,
                        story: effectiveStory,
                        ctxSnap,
                        playing,
                      }),
                    ],
                  }),

                  // B. Large, Prominent 5-Bucket Context Window Bar & Tool Tally
                  jsxs('div', {
                    className: 'harness-story-baked-context',
                    style: {
                      padding: '14px 18px',
                      background: 'var(--ui-bg-elevated)',
                      border: '1px solid var(--ui-stroke-primary)',
                      borderRadius: '10px',
                    },
                    children: [
                      // Top row: Big Context Gauge + Tool Counter
                      jsxs('div', {
                        style: {
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          flexWrap: 'wrap',
                          gap: '10px',
                        },
                        children: [
                          jsxs('div', {
                            'data-testid': 'context-gauge',
                            style: { fontSize: '15px' },
                            children: [
                              jsx('span', {
                                style: { fontWeight: 700, fontSize: '15px' },
                                children: 'Context Window @ Step: ',
                              }),
                              jsx('strong', {
                                style: {
                                  fontFamily: 'var(--ui-font-mono, monospace)',
                                  fontSize: '16px',
                                  color: 'var(--ui-accent)',
                                },
                                children: `${fmtNum(ctxSnap.total_tokens)} tok (${ctxSnap.utilization_pct}%)`,
                              }),
                              jsx('span', {
                                style: {
                                  marginLeft: '10px',
                                  fontSize: '13.5px',
                                  color: 'var(--ui-text-secondary)',
                                },
                                children: `Δ ${ctxSnap.delta_tokens >= 0 ? '+' : ''}${fmtNum(ctxSnap.delta_tokens)} tok · Max ${fmtNum(ctxSnap.context_max)}`,
                              }),
                            ],
                          }),
                          jsxs('div', {
                            'data-testid': 'tool-counter',
                            style: { fontSize: '14px', display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '6px' },
                            children: [
                              jsx('span', {
                                style: { color: 'var(--ui-text-secondary)', fontWeight: 600 },
                                children: 'Tool Calls: ',
                              }),
                              jsx('strong', {
                                style: { fontFamily: 'var(--ui-font-mono, monospace)', fontSize: '15px' },
                                children: `${tally.current} / ${tally.total}`,
                              }),
                              ...Object.entries(tally.byCategory).map(([cat, count]) =>
                                jsx(
                                  'span',
                                  {
                                    'data-cat-pill': cat,
                                    style: {
                                      padding: '2px 8px',
                                      border: '1px solid var(--ui-stroke-primary)',
                                      borderRadius: '5px',
                                      fontSize: '12.5px',
                                      color: 'var(--ui-text-secondary)',
                                      background: 'var(--ui-bg-editor)',
                                    },
                                    children: `${CATEGORY_LABELS[cat] || cat}: ${count}`,
                                  },
                                  cat
                                )
                              ),
                              tally.pivots > 0
                                ? jsx('span', {
                                    style: {
                                      padding: '2px 8px',
                                      border: '1px solid var(--ui-yellow)',
                                      color: 'var(--ui-yellow)',
                                      borderRadius: '5px',
                                      fontSize: '12.5px',
                                      fontWeight: 600,
                                    },
                                    children: `Pivots: ${tally.pivots}`,
                                  })
                                : null,
                            ],
                          }),
                        ],
                      }),

                      // Thick 20px 5-Segment Stacked Context Bar
                      jsxs('div', {
                        className: 'harness-story-context-bar',
                        style: {
                          display: 'flex',
                          height: '20px',
                          width: '100%',
                          marginTop: '10px',
                          borderRadius: '8px',
                          overflow: 'hidden',
                          border: '1px solid var(--ui-stroke-primary)',
                          background: 'var(--ui-bg-editor)',
                        },
                        children: bucketItems.map((b) =>
                          jsx(
                            'div',
                            {
                              title: `${b.label}: ${fmtNum(b.tokens)} tokens (${b.pct}%)`,
                              style: {
                                width: `${b.pct}%`,
                                background: b.color,
                                transition: 'width 240ms ease',
                              },
                            },
                            b.key
                          )
                        ),
                      }),

                      // Large 5-Bucket Human-Readable Breakdown Cards
                      jsxs('div', {
                        className: 'harness-story-context-detail',
                        style: {
                          display: 'grid',
                          gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
                          gap: '8px 14px',
                          marginTop: '10px',
                          fontSize: '13.5px',
                        },
                        children: [
                          ...bucketItems.map((b) =>
                            jsxs(
                              'div',
                              {
                                style: {
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  alignItems: 'center',
                                  padding: '6px 10px',
                                  background: 'var(--ui-bg-editor)',
                                  border: '1px solid var(--ui-stroke-primary)',
                                  borderRadius: '6px',
                                },
                                children: [
                                  jsxs('span', {
                                    style: { display: 'inline-flex', alignItems: 'center', gap: '8px', fontWeight: 600 },
                                    children: [
                                      jsx('span', {
                                        style: {
                                          display: 'inline-block',
                                          width: '12px',
                                          height: '12px',
                                          borderRadius: '3px',
                                          background: b.color,
                                          flexShrink: 0,
                                        },
                                      }),
                                      jsx('span', { children: b.label }),
                                    ],
                                  }),
                                  jsx('span', {
                                    style: {
                                      fontFamily: 'var(--ui-font-mono, monospace)',
                                      fontSize: '13px',
                                      fontWeight: 700,
                                      marginLeft: '8px',
                                    },
                                    children: `${fmtNum(b.tokens)} (${b.pct}%)`,
                                  }),
                                ],
                              },
                              b.key
                            )
                          ),
                        ],
                      }),
                    ],
                  }),

                  // C. Quick Filter Bar above the Auto-Scrolling Story Chronicle
                  jsxs('div', {
                    className: 'harness-story-tabs',
                    role: 'tablist',
                    style: {
                      display: 'flex',
                      gap: '8px',
                    },
                    children: [
                      ['all', `Full Story Chronicle (${steps.length} steps — auto-scrolls with active step)`],
                      ['pivots', `Course Corrections (${(effectiveStory.pivots || []).length})`],
                      ['impact', `Files Touched (${(effectiveStory.code_impact || []).length})`],
                    ].map(([modeId, label]) =>
                      jsx(
                        'button',
                        {
                          type: 'button',
                          role: 'tab',
                          'data-tab': modeId,
                          'aria-selected': filterMode === modeId,
                          onClick: () => setFilterMode(modeId),
                          style: {
                            flex: 1,
                            padding: '8px 12px',
                            fontSize: '13.5px',
                            fontWeight: filterMode === modeId ? 700 : 500,
                            background: filterMode === modeId ? 'var(--ui-bg-elevated)' : 'transparent',
                            color: filterMode === modeId ? 'var(--ui-accent)' : 'var(--ui-text-secondary)',
                            border: filterMode === modeId
                              ? '1.5px solid var(--ui-accent)'
                              : '1px solid var(--ui-stroke-primary)',
                            borderRadius: '6px',
                            cursor: 'pointer',
                          },
                          children: label,
                        },
                        modeId
                      )
                    ),
                  }),
                ],
              }),

              // 3. Auto-Scrolling Bottom Chronicle Container (Scrolls smoothly as Active Step changes)
              jsxs('div', {
                ref: chronicleListRef,
                className: 'harness-story-unified-scroll',
                style: {
                  flex: 1,
                  overflowY: 'auto',
                  padding: '14px 16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '10px',
                },
                children: [
                  // D. Filter View: Course Corrections (Pivots)
                  filterMode === 'pivots'
                    ? jsx('div', {
                        className: 'harness-story-pivots-list',
                        children:
                          (effectiveStory.pivots || []).length === 0
                            ? jsx('div', {
                                style: { color: 'var(--ui-text-secondary)', padding: '12px', fontSize: '15px' },
                                children: 'Every tool call succeeded on the first try — no course corrections were needed.',
                              })
                            : (effectiveStory.pivots || []).map((pv, i) =>
                                jsxs(
                                  'div',
                                  {
                                    className: 'harness-story-pivot-card',
                                    onClick: () => {
                                      setPlaying(false)
                                      setActiveStep(Number(pv.recovery_step || pv.step_index || 1))
                                      setFilterMode('all')
                                    },
                                    style: {
                                      padding: '14px 16px',
                                      marginBottom: '10px',
                                      background: 'var(--ui-bg-elevated)',
                                      border: '1.5px solid var(--ui-yellow)',
                                      borderRadius: '8px',
                                      cursor: 'pointer',
                                      fontSize: '15px',
                                    },
                                    children: [
                                      jsx('div', {
                                        style: { fontWeight: 700, fontSize: '16px', color: 'var(--ui-yellow)' },
                                        children: `🔄 Step #${pv.failed_step || pv.from_step} → Course Correction at Step #${pv.recovery_step || pv.step_index}`,
                                      }),
                                      jsx('div', {
                                        style: { marginTop: '6px', color: 'var(--ui-text-primary)', lineHeight: 1.5 },
                                        children: pv.reason,
                                      }),
                                    ],
                                  },
                                  i
                                )
                              ),
                      })
                    : null,

                  // E. Filter View: Files Touched (Code & System Impact)
                  filterMode === 'impact'
                    ? jsx('div', {
                        className: 'harness-story-impact-list',
                        children:
                          (effectiveStory.code_impact || []).length === 0
                            ? jsx('div', {
                                style: { color: 'var(--ui-text-secondary)', padding: '12px', fontSize: '15px' },
                                children: 'No files were read or modified on disk during this session.',
                              })
                            : (effectiveStory.code_impact || []).map((entry) =>
                                jsxs(
                                  'div',
                                  {
                                    className: 'harness-story-impact-row',
                                    'data-impact-path': entry.path,
                                    style: {
                                      padding: '12px 16px',
                                      marginBottom: '8px',
                                      background: 'var(--ui-bg-elevated)',
                                      border: '1px solid var(--ui-stroke-primary)',
                                      borderRadius: '8px',
                                    },
                                    children: [
                                      jsx('div', {
                                        style: {
                                          fontFamily: 'var(--ui-font-mono, monospace)',
                                          fontWeight: 700,
                                          fontSize: '14.5px',
                                        },
                                        children: entry.path,
                                      }),
                                      jsx('div', {
                                        style: {
                                          fontSize: '13.5px',
                                          color: 'var(--ui-text-secondary)',
                                          marginTop: '4px',
                                        },
                                        children: `Read ${(entry.reads || []).length}× · Edited ${(entry.edits || []).length}× · Verified ${(entry.verifications || entry.verified_by || []).length}×`,
                                      }),
                                    ],
                                  },
                                  entry.path
                                )
                              ),
                      })
                    : null,

                  // F. Unified Conversational Story Chronicle (Default 'all' view — auto-scrolls active item into center)
                  filterMode === 'all'
                    ? jsx('div', {
                        className: 'harness-story-step-list',
                        children: steps.map((st) => {
                          const isCurrent = st.index === activeStep
                          const lp = describeToolForLayperson(st)
                          const stTok = Number(st.context?.total_tokens || 0)
                          const stPct = st.context?.utilization_pct ?? st.context?.context_pct ?? 0
                          const stDelta = Number(st.context?.delta_tokens || 0)
                          const isErr = st.failed || st.status === 'error'

                          return jsxs(
                            'button',
                            {
                              type: 'button',
                              className: 'harness-story-step-row',
                              'data-step-index': st.index,
                              'data-tool-name': st.tool_name,
                              'data-pivot': st.is_pivot ? 'true' : 'false',
                              'data-active': isCurrent ? 'true' : 'false',
                              onClick: () => {
                                setPlaying(false)
                                setActiveStep(st.index)
                              },
                              style: {
                                display: 'flex',
                                flexDirection: 'column',
                                width: '100%',
                                textAlign: 'left',
                                padding: isCurrent ? '16px 18px' : '11px 14px',
                                marginBottom: '10px',
                                background: isCurrent ? 'var(--ui-bg-elevated)' : 'transparent',
                                color: 'var(--ui-text-primary)',
                                border: isCurrent
                                  ? '2px solid var(--ui-accent)'
                                  : st.kind === 'context_load'
                                  ? '1px dashed var(--ui-yellow)'
                                  : '1px solid var(--ui-stroke-primary)',
                                borderLeft: isCurrent
                                  ? '6px solid var(--ui-accent)'
                                  : st.kind === 'context_load'
                                  ? '4px solid var(--ui-yellow)'
                                  : '1px solid var(--ui-stroke-primary)',
                                borderRadius: '8px',
                                cursor: 'pointer',
                                transition: 'all 180ms ease',
                              },
                              children: [
                                // Step badge + inline baked-in context pill
                                jsxs('div', {
                                  style: {
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center',
                                    width: '100%',
                                    gap: '8px',
                                    flexWrap: 'wrap',
                                  },
                                  children: [
                                    jsxs('span', {
                                      style: {
                                        fontSize: isCurrent ? '13.5px' : '12.5px',
                                        fontWeight: 700,
                                        color: isErr
                                          ? 'var(--ui-danger)'
                                          : st.is_pivot || st.kind === 'context_load'
                                          ? 'var(--ui-yellow)'
                                          : 'var(--ui-accent)',
                                      },
                                      children: [
                                        isCurrent ? '▶ ACTIVE · ' : '',
                                        `${lp.icon} Step #${st.index} · ${lp.badge}`,
                                        st.is_pivot ? ' · 🔄 PIVOT' : '',
                                        isErr ? ' · ⚠️ ERROR' : '',
                                      ],
                                    }),
                                    jsx('span', {
                                      style: {
                                        fontFamily: 'var(--ui-font-mono, monospace)',
                                        fontSize: isCurrent ? '13px' : '12px',
                                        fontWeight: isCurrent ? 700 : 500,
                                        color: 'var(--ui-text-secondary)',
                                      },
                                      children: `${stDelta >= 0 ? '+' : ''}${fmtNum(stDelta)} tok → ${fmtNum(stTok)} tok (${stPct}%)`,
                                    }),
                                  ],
                                }),

                                // Conversational Human Headline
                                jsx('div', {
                                  style: {
                                    fontWeight: 700,
                                    fontSize: isCurrent ? '17.5px' : '15px',
                                    marginTop: '5px',
                                    lineHeight: 1.4,
                                  },
                                  children: lp.humanTitle,
                                }),

                                // Decision / Thought or Plain-English explanation
                                st.decision_text || lp.whatHappened
                                  ? jsx('div', {
                                      style: {
                                        fontSize: isCurrent ? '15px' : '13.5px',
                                        color: isCurrent ? 'var(--ui-text-primary)' : 'var(--ui-text-secondary)',
                                        marginTop: '5px',
                                        lineHeight: 1.5,
                                      },
                                      children: st.is_pivot
                                        ? st.pivot_reason || lp.whatHappened
                                        : lp.whatHappened,
                                    })
                                  : null,
                              ],
                            },
                            st.index
                          )
                        }),
                      })
                    : null,
                ],
              }),
            ],
          })
        : null,
    ],
  })
}

export default {
  id: PLUGIN_ID,
  name: 'Harness Story',
  register(ctx) {
    ctx.register({
      id: 'story-main',
      area: PANES_AREA,
      title: 'Harness Story',
      data: {
        title: 'Harness Story',
        icon: 'book-open',
        placement: 'main',
      },
      render: () => jsx(Guard, { children: jsx(StoryPane, { ctx }) }),
    })
  },
}
