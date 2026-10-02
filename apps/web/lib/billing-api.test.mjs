import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
const require = createRequire(new URL('../package.json', import.meta.url))
const ts = require('typescript')

function load(relative, mocks) {
  const source = readFileSync(new URL(relative, import.meta.url), 'utf8')
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', output)(id => {
    if (!(id in mocks)) throw new Error(`Unexpected dependency: ${id}`)
    return mocks[id]
  }, module, module.exports)
  return module.exports
}
function billing(fetchLoadable) {
  return load('./billing-api.ts', {
    react: {}, '@/lib/request-cache': { createTtlCache: () => ({ get: (_key, fn) => fn() }) },
    '@/lib/service-fetch': { fetchLoadable }, '@/lib/api-result': {},
    '@/lib/billing-derive': { customerNameMap: rows => Object.fromEntries(rows.map(r => [r.id, `${r.first_name} ${r.last_name}`])) },
  })
}

test('billing fetches successive pages and preserves query filters', async () => {
  const urls = []
  const client = billing(async url => {
    urls.push(url)
    return { state: 'ready', data: { total: 3, items: urls.length === 1 ? [1, 2] : [3] } }
  })
  assert.deepEqual(await client.fetchPages('/payments?status=completed', { pageSize: 2 }), { state: 'ready', data: { items: [1, 2, 3], total: 3, truncated: false } })
  assert.equal(urls[1], '/svc/billing/payments?status=completed&page=2&page_size=2')
})
test('billing cap and later failure label partial data without inventing a total', async () => {
  let count = 0
  const client = billing(async () => ++count === 1 ? { state: 'ready', data: { total: 5, items: [1, 2] } } : { state: 'forbidden', status: 403 })
  assert.deepEqual((await client.fetchPages('/payments', { pageSize: 2 })).data, { items: [1, 2], total: 5, truncated: true })
  count = 0
  assert.deepEqual((await client.fetchPages('/payments', { pageSize: 2, maxPages: 1 })).data, { items: [1, 2], total: 5, truncated: true })
  const denied = billing(async () => ({ state: 'forbidden', status: 403 }))
  assert.deepEqual(await denied.fetchPages('/payments'), { state: 'forbidden', status: 403 })
})
test('customer directory goes beyond the first page and marks later failures partial', async () => {
  let count = 0
  const client = billing(async () => ({ state: 'ready', data: { total: 101, items: ++count === 1 ? Array.from({ length: 100 }, (_, i) => ({ id: String(i), first_name: 'First', last_name: String(i) })) : [{ id: 'last', first_name: 'Last', last_name: 'Customer' }] } }))
  assert.equal((await client.fetchCustomerNames()).names.last, 'Last Customer')
  assert.equal(count, 2)
  count = 0
  const partial = billing(async () => ++count === 1 ? { state: 'ready', data: { total: 101, items: Array.from({ length: 100 }, (_, i) => ({ id: String(i) })) } } : { state: 'error', status: 502 })
  assert.equal((await partial.fetchCustomerNames()).partial, true)
})

test('public webhook forwards exact bytes and signature to the backend route with no tenant headers', async () => {
  const originalFetch = globalThis.fetch
  let call
  globalThis.fetch = async (url, init) => { call = { url: String(url), init }; return new Response('{"ok":true}', { status: 200 }) }
  try {
    const route = load('../app/svc/billing/[...path]/route.ts', {
      '@/lib/safe-path': { joinSafePath: p => p.join('/'), badPathResponse: () => new Response(null, { status: 400 }) },
      '@/lib/internal-identity': { signedFetch: () => { throw new Error('Webhook must not use signed identity') } },
      '@/lib/proxy-roles': { verifiedRoleHeaders: () => { throw new Error('Webhook must not resolve roles') } },
      'next/server': { NextResponse: class extends Response { static json(body, init) { return new Response(JSON.stringify(body), init) } } },
    })
    const raw = new TextEncoder().encode('{ "event": "charge.success", "data": {"reference":"test-only"} }')
    const request = { method: 'POST', nextUrl: new URL('http://local/svc/billing/payments/paystack/webhook'), headers: new Headers({ 'x-paystack-signature': 'test-signature' }), arrayBuffer: async () => raw.buffer }
    const result = await route.POST(request, { params: Promise.resolve({ path: ['payments', 'paystack', 'webhook'] }) })
    assert.equal(result.status, 200)
    assert.equal(new URL(call.url).pathname, '/payments/paystack/webhook')
    assert.deepEqual(new Uint8Array(call.init.body), raw)
    assert.equal(call.init.headers['x-paystack-signature'], 'test-signature')
    assert.equal(call.init.headers['x-tenant-id'], undefined)
    assert.equal(call.init.redirect, 'manual')
    const backend = readFileSync(new URL('../../../services/billing/routes/paystack.py', import.meta.url), 'utf8')
    assert.match(backend, /prefix="\/payments\/paystack"/)
    assert.match(backend, /@router.post\("\/webhook"/)
    call = undefined
    const denied = await route.POST({ ...request, headers: new Headers() }, { params: Promise.resolve({ path: ['payments', 'paystack', 'webhook'] }) })
    assert.equal(denied.status, 401)
    assert.equal(call, undefined)
  } finally { globalThis.fetch = originalFetch }
})

test('journal client uses exact backend actions and preserves failures', async () => {
  const calls = []
  const failure = { ok: false, status: 409, message: 'Period closed', data: null }
  const client = load('../components/modules/finance/journal-api.ts', {
    '@/lib/service-fetch': { fetchLoadable: url => { calls.push(url); return { state: 'ready', data: [] } } },
    '@/lib/api-result': { sendJson: (...args) => { calls.push(args); return failure } },
  })
  assert.equal(await client.journalAction('id', 'reverse'), failure)
  assert.deepEqual(calls.pop(), ['/svc/finance/journal-entries/id/reverse', 'POST'])
  await client.journalAction('id', 'delete')
  assert.deepEqual(calls.pop(), ['/svc/finance/journal-entries/id', 'DELETE'])
  await client.setAccountingPeriod('2026-09', 'close')
  assert.deepEqual(calls.pop(), ['/svc/finance/periods/2026-09/close', 'POST'])
  await client.readJournals(100)
  assert.equal(calls.pop(), '/svc/finance/journal-entries?limit=100&offset=100')
})
