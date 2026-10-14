const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const { NextRequest } = require('next/server');
const file = path.resolve(__dirname, '../app/api/orchestrator/[...path]/route.ts');
const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const routeModule = new Module(file, module);
routeModule.filename = file;
routeModule.paths = Module._nodeModulePaths(path.dirname(file));
routeModule._compile(compiled, file);
const routes = routeModule.exports;
const profile = { id: 'verified-customer', accountNumber: 'TEST-1' };
const context = parts => ({ params: Promise.resolve({ path: parts }) });
function request(method, parts, body, authenticated = true) {
  return new NextRequest('http://localhost/api/orchestrator/' + parts.join('/'), { method,
    headers: { 'content-type': 'application/json', ...(authenticated ? { authorization: 'Bearer unit-test-session' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}) });
}
async function withFetch(fake, work) {
  const original = global.fetch;
  global.fetch = fake;
  try { await work(); } finally { global.fetch = original; }
}
test('unauthenticated support requests never contact services', async () => {
  await withFetch(() => { throw Error('Unexpected service call'); }, async () => {
    const parts = ['agents', 'invoke'];
    assert.equal((await routes.POST(request('POST', parts, { agent_type: 'customer_facing' }, false), context(parts))).status, 401);
  });
});
test('administration routes are unavailable through customer support', async () => {
  const parts = ['workflows'];
  assert.equal((await routes.GET(request('GET', parts), context(parts))).status, 404);
});
test('customers cannot invoke staff agents', async () => {
  let calls = 0;
  await withFetch(async () => { calls++; return Response.json(profile); }, async () => {
    const parts = ['agents', 'invoke'];
    assert.equal((await routes.POST(request('POST', parts, { agent_type: 'finance' }), context(parts))).status, 403);
    assert.equal(calls, 1);
  });
});
test('streaming uses verified customer context and strips caller tenant and identity', async () => {
  let submitted;
  await withFetch(async (url, init) => {
    if (url.endsWith('/profile')) return Response.json(profile);
    submitted = JSON.parse(init.body);
    return new Response('data: hello\n\n', { headers: { 'content-type': 'text/event-stream' } });
  }, async () => {
    const parts = ['agents', 'invoke', 'stream'];
    const response = await routes.POST(request('POST', parts, { agent_type: 'customer_facing', message: 'Help',
      tenant_id: 'another-tenant', user_id: 'another-user', context: { customer_id: 'another-customer', permissions: ['admin'] } }), context(parts));
    assert.equal(response.status, 200);
    assert.equal(await response.text(), 'data: hello\n\n');
    assert.deepEqual(submitted.context, { customer_id: profile.id, account_number: profile.accountNumber, ui_context: 'customer_support' });
    assert.equal(submitted.tenant_id, undefined);
    assert.equal(submitted.user_id, undefined);
    assert.equal(response.headers.get('cache-control'), 'no-store, private');
  });
});
test('the support catalogue exposes only the customer agent', async () => {
  await withFetch(async url => url.endsWith('/profile') ? Response.json(profile) : Response.json([
    { agent_type: 'customer_facing' }, { agent_type: 'finance' }]), async () => {
    const parts = ['agents'];
    const response = await routes.GET(request('GET', parts), context(parts));
    assert.deepEqual(await response.json(), [{ agent_type: 'customer_facing' }]);
  });
});
test('an unlinked account cannot reach the agent service', async () => {
  let calls = 0;
  await withFetch(async () => { calls++; return new Response(null, { status: 403 }); }, async () => {
    const parts = ['agents', 'invoke'];
    assert.equal((await routes.POST(request('POST', parts, { agent_type: 'customer_facing' }), context(parts))).status, 403);
    assert.equal(calls, 1);
  });
});
