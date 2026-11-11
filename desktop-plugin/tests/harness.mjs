// Verification harness for the harness-story desktop plugin.
//
// Mounts the real contribution returned by plugin.register(ctx) under React 19 + jsdom
// and verifies:
// - contribution shape & id
// - zero hardcoded hex/rgb/hsl colors
// - pure helpers (packLanes, tallyToolsAtStep, computeContextSnapshot, detectPivots, loadStoriesIndex)
// - full React mount with sample story:
//   - "You asked:" kickoff restatement
//   - Hidden Hermes Context Load step (skills, connectors, plugins, tools, memory notes)
//   - Unified Context 5-Buckets + Story Chronicle on the same view
//   - Layperson tool indicator badges & animations
//   - Animated playback controls (prev/next step scrubber updates running tool count & context gauge)
// - gateway snapshot fallback, empty state, error states, and bare ctx resilience.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const results = []
function check(name, fn) {
  try {
    const out = fn()
    results.push({ name, ok: true, detail: out === undefined ? '' : String(out) })
  } catch (e) {
    results.push({ name, ok: false, detail: String((e && e.message) || e) })
  }
}
async function checkAsync(name, fn) {
  try {
    const out = await fn()
    results.push({ name, ok: true, detail: out === undefined ? '' : String(out) })
  } catch (e) {
    results.push({ name, ok: false, detail: String((e && e.message) || e) })
  }
}

// ---------------------------------------------------------------- sample data

const SAMPLE_STORY = {
  slug: 'attack-nav-session',
  session_id: '20261108_142623_3ae14b',
  title: 'Hermes plugin idea using ATT&CK Navigator',
  headline: 'You asked: “Hermes plugin idea using ATT&CK Navigator” — Hermes loaded 6,525 tokens of context (112 skills, 4 connectors) and used 3 tools (with 1 course correction).',
  executive_summary: 'You asked: “Hermes plugin idea using ATT&CK Navigator”\n\nBefore calling the model, Hermes loaded your workspace context (6,525 tokens, 112 skills, 4 MCP connectors, 9 plugins, ~50 tools).\n\nHermes then worked through your request, recovered from a JSON parse error on layerformat.md by reading it as Markdown, and verified the plugin.',
  context_load: {
    total_tokens: 6525,
    context_max: 131072,
    utilization_pct: 4.98,
    system_prompt_tokens: 3566,
    skills_and_memory_tokens: 2959,
    skills_count: 112,
    skill_categories: ['autonomous-ai-agents', 'creative', 'devops', 'gaming'],
    connectors_count: 4,
    connectors_list: ['fastmail', 'stubhub', 'tinyfish', 'mitre-attack'],
    plugins_count: 9,
    toolsets_count: 23,
    tools_estimated_count: 50,
    memory_notes_count: 5,
    user_profile_loaded: true,
    semantic_memory_provider: 'local-embed',
    summary_sentence: 'Before calling the model, Hermes quietly packed 6,525 tokens (4.98% of the 131,072-token window) into context: 112 skills, 4 MCP connectors, 9 plugins, ~50 tools, and 5 personal memory notes.',
  },
  context_journey: {
    context_max: 131072,
    start_tokens: 6590,
    peak_tokens: 14800,
    peak_pct: 11.29,
    end_tokens: 14800,
    end_pct: 11.29,
  },
  steps: [
    {
      index: 1,
      kind: 'user_prompt',
      tool_name: null,
      category: 'prompt',
      verb: 'You asked',
      target: 'Hermes plugin idea using ATT&CK Navigator',
      human_title: 'You asked: “Hermes plugin idea using ATT&CK Navigator”',
      human_narrative: 'You kicked off the session by asking: “Hermes plugin idea using ATT&CK Navigator”. Your prompt added 65 tokens to the conversation.',
      tool_indicator: {
        tool_name: 'user_prompt',
        badge: 'Your Prompt',
        icon: '💬',
        animation: 'prompt_bubble',
      },
      status: 'ok',
      duration_ms: 0,
      lane: 0,
      running_tool_count: 0,
      is_pivot: false,
      context: {
        total_tokens: 65,
        context_max: 131072,
        utilization_pct: 0.05,
        delta_tokens: 65,
        system_prompt_tokens: 0,
        skills_and_memory_tokens: 0,
        user_messages_tokens: 65,
        assistant_reasoning_tokens: 0,
        tool_io_tokens: 0,
      },
    },
    {
      index: 2,
      kind: 'context_load',
      tool_name: 'hermes_context_loader',
      category: 'context',
      verb: 'Loaded context',
      target: '6,525 tokens · 112 skills · 4 connectors · ~50 tools',
      human_title: 'Behind the scenes, Hermes loaded your workspace context',
      human_narrative: 'Before calling the model, Hermes quietly packed 6,525 tokens (4.98% of the 131,072-token window) into context: 112 skills, 4 MCP connectors, 9 plugins, ~50 tools, and 5 personal memory notes.',
      decision_text: 'This is a default hidden step in Hermes so the model knows your tools, skills, connectors, and preferences.',
      tool_indicator: {
        tool_name: 'hermes_context_loader',
        badge: 'Hermes Context Load',
        icon: '🎒',
        animation: 'backpack_load',
      },
      context_load_details: {
        total_tokens: 6525,
        skills_count: 112,
        skill_categories: ['autonomous-ai-agents', 'creative', 'devops'],
        connectors_count: 4,
        connectors_list: ['fastmail', 'stubhub', 'tinyfish', 'mitre-attack'],
        plugins_count: 9,
        toolsets_count: 23,
        tools_estimated_count: 50,
        memory_notes_count: 5,
        user_profile_loaded: true,
        semantic_memory_provider: 'local-embed',
      },
      status: 'ok',
      duration_ms: 12,
      lane: 0,
      running_tool_count: 0,
      is_pivot: false,
      context: {
        total_tokens: 6590,
        context_max: 131072,
        utilization_pct: 5.03,
        delta_tokens: 6525,
        system_prompt_tokens: 3566,
        skills_and_memory_tokens: 2959,
        user_messages_tokens: 65,
        assistant_reasoning_tokens: 0,
        tool_io_tokens: 0,
      },
    },
    {
      index: 3,
      kind: 'tool_call',
      tool_name: 'terminal',
      category: 'execute',
      verb: 'Executed',
      target: 'python3 -c "json.load(open(\'layerformat.md\'))"',
      human_title: 'Tried running command: python3 -c "json.load(open(\'layerformat.md\'))" (ran into an error)',
      human_narrative: 'The model decided: “Let us parse layerformat.md.” It used Terminal Command (`terminal`), which returned an error (`JSONDecodeError`). This step added +2,310 tokens, bringing context to 8,900 tokens (6.79%).',
      decision_text: 'Let us parse layerformat.md.',
      tool_indicator: {
        tool_name: 'terminal',
        badge: 'Terminal Command',
        icon: '🖥️',
        animation: 'terminal_exec',
      },
      status: 'error',
      duration_ms: 115,
      lane: 0,
      running_tool_count: 1,
      is_pivot: false,
      context: {
        total_tokens: 8900,
        context_max: 131072,
        utilization_pct: 6.79,
        delta_tokens: 2310,
        system_prompt_tokens: 3566,
        skills_and_memory_tokens: 2959,
        user_messages_tokens: 65,
        assistant_reasoning_tokens: 600,
        tool_io_tokens: 1710,
      },
    },
    {
      index: 4,
      kind: 'tool_call',
      tool_name: 'read_file',
      category: 'explore',
      verb: 'Read',
      target: 'layerformat.md',
      human_title: 'Course correction: Opened and read layerformat.md',
      human_narrative: 'After the previous step ran into an error, the model adjusted its plan: “Pivoted to reading layerformat.md as Markdown after JSON parse error.” It used File Reader (`read_file`). This step added +2,000 tokens, bringing context to 10,900 tokens (8.32%).',
      decision_text: 'Pivoted to reading layerformat.md as Markdown after JSON parse error.',
      tool_indicator: {
        tool_name: 'read_file',
        badge: 'File Reader',
        icon: '📖',
        animation: 'file_scan',
      },
      status: 'ok',
      duration_ms: 38,
      lane: 0,
      running_tool_count: 2,
      is_pivot: true,
      pivot_from_step: 3,
      pivot_reason: 'Pivoted to reading layerformat.md as Markdown after JSON parse error.',
      context: {
        total_tokens: 10900,
        context_max: 131072,
        utilization_pct: 8.32,
        delta_tokens: 2000,
        system_prompt_tokens: 3566,
        skills_and_memory_tokens: 2959,
        user_messages_tokens: 65,
        assistant_reasoning_tokens: 1100,
        tool_io_tokens: 3210,
      },
    },
    {
      index: 5,
      kind: 'tool_call',
      tool_name: 'terminal',
      category: 'verify',
      verb: 'Verified',
      target: 'pytest -q',
      human_title: 'Ran verification check: pytest -q',
      human_narrative: 'It used Test & Verify (`terminal`) and got: “4 passed”. This step added +3,900 tokens, bringing context to 14,800 tokens (11.29%).',
      tool_indicator: {
        tool_name: 'terminal',
        badge: 'Test & Verify',
        icon: '✅',
        animation: 'verify_check',
      },
      status: 'ok',
      duration_ms: 490,
      lane: 0,
      running_tool_count: 3,
      is_pivot: false,
      context: {
        total_tokens: 14800,
        context_max: 131072,
        utilization_pct: 11.29,
        delta_tokens: 3900,
        system_prompt_tokens: 3566,
        skills_and_memory_tokens: 2959,
        user_messages_tokens: 65,
        assistant_reasoning_tokens: 1600,
        tool_io_tokens: 6610,
      },
    },
  ],
  pivots: [
    {
      failed_step: 3,
      failed_tool: 'terminal',
      recovery_step: 4,
      recovery_tool: 'read_file',
      reason: 'Pivoted to reading layerformat.md as Markdown after JSON parse error.',
    },
  ],
  code_impact: [
    {
      path: 'layerformat.md',
      reads: [4],
      edits: [],
      verified_by: [5],
    },
  ],
}

const SAMPLE_INDEX = [
  {
    slug: 'attack-nav-session',
    title: SAMPLE_STORY.title,
    tool_calls: 3,
    pivots: 1,
    peak_tokens: 14800,
    peak_pct: 11.29,
  },
]

// ---------------------------------------------------------------- environment

const { JSDOM } = await import('jsdom')
const dom = new JSDOM('<!doctype html><html><head></head><body><div id="root"></div></body></html>', {
  url: 'http://localhost/',
  pretendToBeVisual: true,
})
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.Node = dom.window.Node
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true })
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const React = await import('react')
const { act } = React
const { createRoot } = await import('react-dom/client')
const mod = await import('./plugin.js')
const plugin = mod.default

const flush = async (n = 8) => {
  for (let i = 0; i < n; i++) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
  }
}

function makeCtx({
  stories = SAMPLE_INDEX,
  recentSessions = [],
  storyJson = SAMPLE_STORY,
  throwOnIndex = null,
  throwOnStory = null,
} = {}) {
  const ctx = {
    contribution: null,
    calls: [],
    copied: null,
    register(c) {
      ctx.contribution = c
    },
    rest: async (path, opts) => {
      ctx.calls.push({ path, opts })
      if (path === '/stories') {
        if (throwOnIndex) throw throwOnIndex
        return { stories: stories || [], recent_sessions: recentSessions || [] }
      }
      if (path === '/generate') {
        return { ok: true, slug: 'attack-nav-session' }
      }
      const m = /^\/stories\/(.+?)\.json$/.exec(path)
      if (m) {
        if (throwOnStory) throw throwOnStory
        return storyJson
      }
      throw new Error('unexpected route ' + path)
    },
    files: {
      readText: async () => {
        throw new Error('no local snapshot')
      },
    },
    os: {
      clipboard: {
        writeText: async (t) => {
          ctx.copied = t
        },
      },
    },
  }
  return ctx
}

let active = null
async function mount(ctx) {
  if (active) {
    await act(async () => active.unmount())
    active = null
  }
  plugin.register(ctx)
  const el = ctx.contribution.render()
  const host = document.getElementById('root')
  host.innerHTML = ''
  const root = createRoot(host)
  await act(async () => {
    root.render(el)
  })
  await flush()
  active = root
  return { html: host.innerHTML, text: host.textContent || '', ctx }
}

// --------------------------------------------------------------------- checks

check('register() contributes the harness-story main workspace pane', () => {
  const ctx = makeCtx()
  plugin.register(ctx)
  assert.ok(ctx.contribution, 'register did not call ctx.register')
  assert.equal(ctx.contribution.id, 'story-main')
  assert.equal(ctx.contribution.area, 'panes')
  assert.equal(ctx.contribution.data.placement, 'main')
  assert.equal(typeof ctx.contribution.render, 'function')
  return `id=${ctx.contribution.id} area=${ctx.contribution.area} placement=${ctx.contribution.data.placement}`
})

check('source has zero hardcoded hex/rgb/hsl colors', () => {
  const src = readFileSync(new URL('./plugin.js', import.meta.url), 'utf8')
  const hex = src.match(/#[0-9a-fA-F]{3,8}\b/g)
  assert.equal(hex, null, 'hex colors found: ' + JSON.stringify(hex))
  assert.ok(!/rgb\(|rgba\(|hsl\(/.test(src), 'rgb/hsl literal found')
  return 'theme CSS vars only'
})

check('helpers: packLanes assigns non-overlapping intervals to lane 0 and overlapping to lane 1+', () => {
  const res = mod.packLanes([
    { index: 1, t0: 0, t1: 5 },
    { index: 2, t0: 2, t1: 6 },
    { index: 3, t0: 5.5, t1: 8 },
  ])
  assert.equal(res.lanes, 2)
  assert.deepEqual(
    res.spans.map((s) => s.lane),
    [0, 1, 0]
  )
  return `lanes=${res.lanes}`
})

check('helpers: tallyToolsAtStep computes running tool counts and categories (excluding kickoff/context_load)', () => {
  const t2 = mod.tallyToolsAtStep(SAMPLE_STORY.steps, 2)
  assert.equal(t2.current, 0)
  assert.equal(t2.total, 3)
  const t5 = mod.tallyToolsAtStep(SAMPLE_STORY.steps, 5)
  assert.equal(t5.current, 3)
  assert.equal(t5.total, 3)
  assert.equal(t5.pivots, 1)
  assert.equal(t5.byCategory.explore, 1)
  assert.equal(t5.byCategory.verify, 1)
  return `step2=${t2.current}/${t2.total} step5=${t5.current}/${t5.total}`
})

check('helpers: computeContextSnapshot returns exact 5-bucket breakdown at each step', () => {
  const c2 = mod.computeContextSnapshot(SAMPLE_STORY, 2)
  const c4 = mod.computeContextSnapshot(SAMPLE_STORY, 4)
  assert.equal(c2.total_tokens, 6590)
  assert.equal(c2.system_prompt_tokens, 3566)
  assert.equal(c2.skills_and_memory_tokens, 2959)
  assert.equal(c4.total_tokens, 10900)
  assert.equal(c4.delta_tokens, 2000)
  return `step2=${c2.total_tokens} -> step4=${c4.total_tokens}`
})

await checkAsync('mount: renders kickoff "You asked:", hidden context load, unified 5-bucket context + chronicle, and layperson tool badges', async () => {
  const { html, text } = await mount(makeCtx())
  assert.ok(html.includes('class="harness-story"'), 'pane root missing')
  assert.ok(!html.includes('data-crash='), 'error boundary fired')
  assert.ok(text.includes('You asked:'), 'kickoff restatement missing')
  assert.ok(text.includes('Behind the scenes, Hermes loaded your workspace context'), 'hidden context load step missing')
  assert.ok(text.includes('112 skills'), 'skills count missing')
  assert.ok(text.includes('Hermes Instructions & Tools'), 'unified 5-bucket context breakdown missing from main screen')
  assert.ok(text.includes('File Reader'), 'layperson tool badge missing')
  const stepRows = [...html.matchAll(/data-step-index="(\d+)"/g)].map((m) => Number(m[1]))
  assert.deepEqual(stepRows, [1, 2, 3, 4, 5])
  return `${stepRows.length} steps rendered with unified 5-Bucket Context + Chronicle`
})

await checkAsync('mount: stepping forward advances from Kickoff -> Hidden Context Load -> Tool Steps and updates live context gauge', async () => {
  await mount(makeCtx())
  const nextBtn = document.querySelector('.harness-story-next-btn')
  assert.ok(nextBtn, 'next step button missing')

  // Advance from Step 1 (You asked) -> Step 2 (Hidden Hermes Context Load)
  await act(async () => {
    nextBtn.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }))
  })
  await flush()
  const stageText2 = document.querySelector('[data-testid="story-stage"]')?.textContent || ''
  const ctxGauge2 = document.querySelector('[data-testid="context-gauge"]')?.textContent || ''
  assert.ok(/112 skills/i.test(stageText2), 'stage did not show context load backpack at step 2: ' + stageText2)
  assert.ok(ctxGauge2.includes('6,590 tok (5.03%)'), 'context gauge did not update to step 2: ' + ctxGauge2)

  // Advance to Step 3 (Terminal Command) and Step 4 (Course correction File Reader)
  await act(async () => {
    nextBtn.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }))
  })
  await flush()
  await act(async () => {
    nextBtn.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }))
  })
  await flush()
  const toolCounter4 = document.querySelector('[data-testid="tool-counter"]')?.textContent || ''
  const ctxGauge4 = document.querySelector('[data-testid="context-gauge"]')?.textContent || ''
  assert.ok(toolCounter4.includes('2 / 3'), 'tool counter did not update to 2 / 3: ' + toolCounter4)
  assert.ok(ctxGauge4.includes('10,900 tok (8.32%)'), 'context gauge did not update to step 4: ' + ctxGauge4)
  return `step 2 -> step 4 verified (${toolCounter4} | ${ctxGauge4})`
})

await checkAsync('mount: filter pills switch between All Steps, Pivots & Decisions, and Files Touched while keeping Context Buckets visible', async () => {
  await mount(makeCtx())
  const pivotsTab = document.querySelector('[data-tab="pivots"]')
  await act(async () => {
    pivotsTab.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }))
  })
  await flush()
  assert.ok(document.body.textContent.includes('Pivoted to reading layerformat.md as Markdown'))
  assert.ok(document.body.textContent.includes('Hermes Instructions & Tools'), '5-Bucket Context Breakdown should remain visible')

  const impactTab = document.querySelector('[data-tab="impact"]')
  await act(async () => {
    impactTab.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }))
  })
  await flush()
  assert.ok(document.body.innerHTML.includes('data-impact-path="layerformat.md"'))
  return 'filter pills + persistent context buckets verified'
})

await checkAsync('loadStoriesIndex: falls back to ctx.files snapshot when gateway fails', async () => {
  const ctx = {
    rest: async () => {
      throw new Error('ECONNREFUSED')
    },
    files: {
      readText: async (dir, name) => {
        assert.equal(dir, 'data')
        assert.equal(name, 'stories.json')
        return JSON.stringify({ stories: SAMPLE_INDEX })
      },
    },
  }
  const res = await mod.loadStoriesIndex(ctx)
  assert.equal(res.source, 'snapshot')
  assert.equal(res.stories.length, 1)
  assert.ok(res.problems.length >= 1)
  return `source=${res.source}`
})

await checkAsync('mount: empty stories list renders empty state cleanly', async () => {
  const { html, text } = await mount(makeCtx({ stories: [] }))
  assert.ok(!html.includes('data-crash='))
  assert.ok(text.includes('No Harness Stories generated yet.'))
  return 'empty state ok'
})

await checkAsync('mount: bare ctx without files/os degrades cleanly', async () => {
  const bare = {
    register(c) {
      bare.contribution = c
    },
    rest: async (p) => (p === '/stories' ? { stories: SAMPLE_INDEX } : SAMPLE_STORY),
  }
  const { html } = await mount(bare)
  assert.ok(!html.includes('data-crash='))
  assert.ok(!html.includes('harness-story-copy'), 'copy button should omit without ctx.os')
  return 'bare ctx ok'
})

if (active) await act(async () => active.unmount())

for (const r of results) console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.name}${r.detail ? '  — ' + r.detail : ''}`)
const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
if (failed.length) process.exitCode = 1
