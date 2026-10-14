const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const { NextRequest } = require('next/server');
const file = path.resolve(__dirname, '../app/api/home-dome/[[...path]]/route.ts');
const loaded = new Module(file, module); loaded.filename = file; loaded.paths = Module._nodeModulePaths(path.dirname(file));
loaded._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, file);
const context = parts => ({ params: Promise.resolve({ path: parts }) });
const request = (method, parts) => new NextRequest('http://localhost/api/home-dome/' + parts.join('/'), { method, headers: { authorization: 'Bearer test-session' } });
async function withFetch(fake, work) { const old = global.fetch; global.fetch = fake; try { await work(); } finally { global.fetch = old; } }
test('tenant reporting queue cannot be reached through the customer app', async () => {
  await withFetch(() => { throw Error('Must not contact upstream'); }, async () => {
    for (const method of ['GET', 'PUT', 'POST', 'DELETE']) {
      const parts = ['reporting', 'requests'];
      assert.equal((await loaded.exports[method](request(method, parts), context(parts))).status, 403);
    }
  });
});
test('customer capabilities hide administrative controls even for an admin identity', async () => {
  await withFetch(async () => Response.json({ can_provision: true, can_request_support: true, can_assign_gateway: true, gateway_onboarding_url: 'private-admin-url' }), async () => {
    const response = await loaded.exports.GET(request('GET', ['capabilities']), context(['capabilities']));
    assert.deepEqual(await response.json(), { can_provision: false, can_request_support: false, can_assign_gateway: false, gateway_onboarding_url: null });
    assert.equal(response.headers.get('cache-control'), 'no-store, private');
  });
});
test('customer upgrade requests still reach the verified platform boundary', async () => {
  let target;
  await withFetch(async url => { target = String(url); return Response.json({ status: 'requested' }); }, async () => {
    const parts = ['home', 'reporting', 'upgrade'];
    assert.equal((await loaded.exports.POST(request('POST', parts), context(parts))).status, 200);
    assert.ok(target.endsWith('/api/home-dome/home/reporting/upgrade'));
  });
});
