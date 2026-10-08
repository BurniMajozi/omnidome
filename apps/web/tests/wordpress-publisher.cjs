// Behavioral checks for review gating, ambiguous writes, and stale site responses.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const jsx = require('react/jsx-runtime')

function harness(api) {
  const slots = [], effects = []
  let cursor = 0
  const react = {
    useState(initial) { const i = cursor++; if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial; return [slots[i], next => { slots[i] = typeof next === 'function' ? next(slots[i]) : next }] },
    useRef(initial) { const i = cursor++; return slots[i] ||= { current: initial } },
    useEffect(fn, deps) { const i = cursor++; const old = slots[i]; if (!old || deps.some((d, n) => !Object.is(d, old.deps[n]))) effects.push(() => { old?.cleanup?.(); slots[i] = { deps, cleanup: fn() } }) },
  }
  const output = { exports: {} }
  const stub = new Proxy({}, { get: (_, name) => name })
  const context = { exports: output.exports, module: output, console,
    window: { confirm: () => true },
    require(name) { return name === 'react' ? react : name === 'react/jsx-runtime' ? jsx : name === '@/lib/portal-api' ? api : stub },
  }
  const source = fs.readFileSync(path.resolve(__dirname, '../components/modules/portal/wordpress-publisher.tsx'), 'utf8')
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText, context)
  return { render(props) { cursor = 0; const tree = output.exports.WordPressPublisher(props); effects.splice(0).forEach(fn => fn()); return tree } }
}
function nodes(tree) { if (!tree || typeof tree !== 'object') return []; if (Array.isArray(tree)) return tree.flatMap(nodes); return [tree, ...nodes(tree.props?.children)] }
function text(tree) { if (tree == null || typeof tree === 'boolean') return ''; if (typeof tree !== 'object') return String(tree); if (Array.isArray(tree)) return tree.map(text).join(''); return text(tree.props?.children) }
const tick = async () => { for (let i = 0; i < 16; i++) await Promise.resolve() }
const button = (tree, label) => nodes(tree).find(n => n.type === 'Button' && text(n) === label)
const connection = id => ({ id, site_name: id, site_url: `https://${id}.example`, active: true })
const draft = { status: 'draft_exported', exported_hash: 'a'.repeat(64), local_changes: false, preview_url: 'https://one.example/preview' }

async function main() {
  let exported = 0, published = 0, timeout = false, resolveStale
  const api = {
    loadWordPressConnections: async () => ({ state: 'ready', data: { items: [connection('one'), connection('two')] } }),
    loadWordPressPublication: async cid => cid === 'two' ? new Promise(resolve => { resolveStale = resolve }) : ({ state: 'ready', data: { status: 'not_exported', local_changes: false } }),
    exportWordPressDraft: async () => { exported++; return timeout ? { ok: false, message: 'Response lost', status: null } : { ok: true, data: draft } },
    publishWordPressDraft: async (cid, pid, hash) => { published++; assert.equal(hash, draft.exported_hash); return { ok: true, data: { ...draft, status: 'published', live_url: 'https://one.example/fibre' } } },
    refreshWordPressPublication: async () => ({ ok: true, data: draft }),
  }
  const h = harness(api)
  const props = { open: true, onOpenChange() {}, pageId: 'page', pageTitle: 'Fibre', dirty: false, saving: false, save: async () => true }
  const render = () => h.render(props)
  render(); await tick(); render(); await tick(); let tree = render()
  assert.equal(button(tree, 'Send draft to WordPress').props.disabled, false)
  await button(tree, 'Send draft to WordPress').props.onClick(); await tick(); tree = render()
  assert.equal(exported, 1)
  assert.equal(button(tree, 'Publish reviewed draft').props.disabled, true, 'Explicit preview review is required')
  nodes(tree).find(n => n.type === 'input' && n.props.type === 'checkbox').props.onChange({ target: { checked: true } })
  tree = render()
  assert.equal(button(tree, 'Publish reviewed draft').props.disabled, false)
  props.dirty = true; render(); tree = render()
  assert.equal(button(tree, 'Publish reviewed draft').props.disabled, true, 'Unsaved edits invalidate review')
  props.dirty = false; render(); tree = render()
  assert.equal(button(tree, 'Publish reviewed draft').props.disabled, true, 'Saving does not restore an old review')
  nodes(tree).find(n => n.type === 'input' && n.props.type === 'checkbox').props.onChange({ target: { checked: true } })
  tree = render(); await button(tree, 'Publish reviewed draft').props.onClick(); await tick(); tree = render()
  assert.equal(published, 1)
  assert.ok(text(tree).includes('Live on WordPress'))
  timeout = true
  await button(tree, 'Send draft to WordPress').props.onClick(); await tick(); tree = render()
  assert.equal(button(tree, 'Send draft to WordPress').props.disabled, true, 'Ambiguous writes cannot be repeated')
  assert.ok(text(tree).includes('Refresh status before retrying'))
  await button(tree, 'Refresh WordPress status').props.onClick(); await tick(); tree = render()
  assert.equal(button(tree, 'Send draft to WordPress').props.disabled, false)
  nodes(tree).find(n => n.type === 'select').props.onChange({ target: { value: 'two' } }); render(); await tick()
  tree = render()
  nodes(tree).find(n => n.type === 'select').props.onChange({ target: { value: 'one' } }); render(); await tick(); tree = render()
  resolveStale({ state: 'ready', data: { ...draft, status: 'external_changes' } }); await tick(); tree = render()
  assert.ok(!text(tree).includes('Changed in WordPress'), 'A late response from another site cannot overwrite the selected site')
  console.log('PASS: draft review, dirty-state invalidation, publication, ambiguous-write guard, reconciliation, stale-site responses')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
