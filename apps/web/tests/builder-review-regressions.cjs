// Focused state-transition checks; no browser, provider or customer data required.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const jsx = require('react/jsx-runtime')
const root = path.resolve(__dirname, '..')

function harness(file, external = {}, globals = {}) {
  const slots = [], effects = []
  let cursor = 0
  const react = {
    useState(initial) { const i = cursor++; if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial; return [slots[i], v => { slots[i] = typeof v === 'function' ? v(slots[i]) : v }] },
    useRef(initial) { const i = cursor++; return slots[i] ||= { current: initial } },
    useMemo(fn) { cursor++; return fn() }, useCallback(fn) { cursor++; return fn },
    useEffect(fn, deps) { const i = cursor++; const prev = slots[i]; if (!prev || deps.some((d, n) => !Object.is(d, prev.deps[n]))) { effects.push(() => { prev?.cleanup?.(); slots[i] = { deps, cleanup: fn() } }) } },
  }
  const output = { exports: {} }
  const stub = new Proxy({}, { get: (_, name) => name })
  const context = { exports: output.exports, module: output, console, Intl, Set, Error, structuredClone, ...globals,
    require(name) { if (name === 'react') return react; if (name === 'react/jsx-runtime') return jsx; return external[name] || stub },
  }
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText, context)
  return { exports: output.exports, render(fn) { cursor = 0; const tree = fn(); effects.splice(0).forEach(f => f()); return tree } }
}
function nodes(tree) { if (tree == null || typeof tree !== 'object') return []; if (Array.isArray(tree)) return tree.flatMap(nodes); return [tree, ...nodes(tree.props?.children)] }
function text(tree) { if (tree == null || typeof tree === 'boolean') return ''; if (typeof tree !== 'object') return String(tree); if (Array.isArray(tree)) return tree.map(text).join(''); return text(tree.props?.children) }
const tick = async () => { for (let i = 0; i < 12; i++) await Promise.resolve() }

async function agentChecks() {
  const fullObjective = 'Original long objective '.repeat(25)
  let summary = { id: 'job', objective: fullObjective.slice(0, 200), status: 'queued', total_steps: 0, total_tokens: 0, max_cost_usd: 2, estimated_cost_usd: 0, actual_cost_usd: 0 }
  let resolveDetail, rejectDetail, poll
  const calls = []
  const h = harness('components/admin/agent-work-view.tsx', {}, {
    window: { setInterval(fn) { poll = fn; return 1 }, clearInterval() {} }, document: { visibilityState: 'visible' },
    fetch: async (url, init) => {
      calls.push({ url, init })
      const route = url.replace('/api/orchestrator/agents', '')
      if (route === '/jobs/job') return new Promise((resolve, reject) => { resolveDetail = full => resolve({ ok: true, json: async () => full }); rejectDetail = reject })
      return { ok: true, json: async () => route === '/jobs' ? [summary] : route === '/registered' ? [] : { monthly_budget_usd: null, month_spend_usd: 0 } }
    },
  })
  const render = () => h.render(() => h.exports.AgentWorkView({ agents: [] }))
  render(); await tick()
  let tree = render()
  const select = nodes(tree).find(n => n.props?.onClick && text(n).includes(summary.objective))
  assert.ok(select, 'Job selection control exists')
  select.props.onClick(); tree = render()
  let edit = nodes(tree).find(n => n.type === 'Button' && text(n) === 'Edit prompt')
  assert.equal(edit.props.disabled, true, 'Summary objective cannot be edited before full detail arrives')
  resolveDetail({ ...summary, objective: fullObjective, iteration_history: [] }); await tick(); tree = render()
  edit = nodes(tree).find(n => n.type === 'Button' && text(n) === 'Edit prompt')
  assert.equal(edit.props.disabled, false)
  edit.props.onClick(); tree = render()
  assert.equal(nodes(tree).find(n => n.type === 'Textarea' && n.props.value === fullObjective)?.props.value, fullObjective)
  summary = { ...summary, status: 'running', total_steps: 1, total_tokens: 10 }
  poll(); await tick(); tree = render()
  resolveDetail({ ...summary, objective: fullObjective, iteration_history: [{ iteration: 1, steps: 1, tokens: 10, content_preview: 'First iteration' }] }); await tick(); render()
  summary = { ...summary, total_steps: 7, total_tokens: 70 }
  const before = calls.filter(c => c.url.endsWith('/jobs/job')).length
  poll(); await tick(); tree = render()
  assert.equal(calls.filter(c => c.url.endsWith('/jobs/job')).length, before + 1, 'Same-status polling refreshes full detail')
  assert.ok(text(tree).includes('Steps: 7'), 'New summary counters are not overwritten by stale detail')
  resolveDetail({ ...summary, objective: fullObjective, iteration_history: [{ iteration: 2, steps: 7, tokens: 70, content_preview: 'New iteration' }] }); await tick(); tree = render()
  assert.ok(text(tree).includes('New iteration'))
  poll(); await tick(); render(); rejectDetail(new Error('Detail unavailable')); await tick(); tree = render()
  assert.ok(text(tree).includes('Detail unavailable'))
  assert.ok(nodes(tree).some(n => n.type === 'Button' && text(n) === 'Retry full detail'))
}

async function studioChecks() {
  let stored, requestContext, failSave = false
  const page = { id: 'page', slug: 'draft', status: 'draft', title: 'Draft', description: '', content: { blocks: [{ type: 'hero', heading: 'Draft' }] }, theme: { accent: 'cyan', appearance: 'light' } }
  const api = {
    slugify: s => s.toLowerCase(),
    suggestPortalDesign: async (prompt, current, selected, context) => { requestContext = context; return { ok: true, data: { draft: { title: page.title, description: '', blocks: page.content.blocks, theme: page.theme }, message: 'Review the draft', warnings: [] } } },
    createPortalPage: async () => ({ ok: true, data: page }), updatePortalPage: async () => ({ ok: true, data: page }),
    savePortalDesignContext: async (id, context) => { if (failSave) return { ok: false, message: 'Unavailable' }; stored = structuredClone(context); return { ok: true, data: context } },
    loadPortalPage: async () => ({ state: 'ready', data: page }), loadPortalDesignContext: async () => ({ state: 'ready', data: stored }),
  }
  const h = harness('components/modules/portal/use-design-studio.ts', { '@/lib/portal-api': api, './portal-blocks': { blocksOf: c => c.blocks || [], plainText: s => s } }, { window: { addEventListener() {}, removeEventListener() {} } })
  const render = () => h.render(() => h.exports.useDesignStudio(() => {}))
  let studio = render(); await studio.suggest('Original brief'); studio = render()
  await studio.suggest('Use my first instruction'); studio = render()
  assert.equal(requestContext.brief, 'Original brief')
  assert.ok(requestContext.messages.some(m => m.text === 'Original brief'))
  await studio.save(); studio = render(); assert.equal(studio.dirty, false)
  studio.reset(); studio = render(); await studio.open('page'); studio = render()
  assert.ok(studio.messages.some(m => m.text === 'Use my first instruction'), 'Saved conversation survives reopening')
  assert.equal(studio.generated, true)
  assert.equal(studio.dirty, false)
  failSave = true
  studio.change({ ...studio.draft, description: 'Edited directly' }); studio = render()
  assert.equal(await studio.save(), false)
  studio = render()
  assert.equal(studio.dirty, true, 'Partial save still prompts the user to retry before leaving')
}

async function main() {
  const blocks = harness('components/modules/portal/portal-blocks.tsx').exports
  assert.equal(blocks.plainText('First paragraph.\r\n\r\nSecond paragraph.'), 'First paragraph.\n\nSecond paragraph.')
  const tree = blocks.PortalBlockView({ block: { type: 'hero', subheading: 'One\n\nTwo' } })
  assert.ok(nodes(tree).some(n => n.type === 'span' && text(n) === 'One\n\nTwo' && n.props.className.includes('whitespace-pre-wrap')))
  await agentChecks(); await studioChecks()
  console.log('PASS: pending detail guard, full objective, same-status polling, error retry, private chat save/reopen, paragraph rendering')
}
main().catch(err => { console.error(err); process.exitCode = 1 })
