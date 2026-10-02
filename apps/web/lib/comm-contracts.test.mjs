import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import ts from "typescript"
import { detailText } from "./comm-messages.ts"

// Execute the real proxy/client code with isolated transport and identity dependencies.
// No service, email, agent or other live control is contacted.
function load(path, dependencies) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8")
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  new Function("require", "exports", compiled)((name) => {
    if (!(name in dependencies)) throw new Error(`Unexpected dependency: ${name}`)
    return dependencies[name]
  }, exports)
  return exports
}

class JsonResponse {
  constructor(body, options) { this.body = body; this.status = options?.status ?? 200 }
  static json(body, options) { return new JsonResponse(body, options) }
}

const request = (body, query = "channel_id=channel") => ({
  nextUrl: new URL(`https://local/api/chat/messages?${query}`),
  json: async () => body,
  text: async () => JSON.stringify(body),
})

function proxy(path, transport, identity = {}) {
  return load(path, {
    "@/lib/internal-identity": { signedFetch: transport },
    "@/lib/api-auth": { identityHeaders: async () => ({ headers: {}, identity }) },
    "next/server": { NextResponse: JsonResponse },
  })
}

test("message proxy forwards cursor and send key and preserves upstream statuses", async () => {
  let call
  let status = 200
  let payload = { items: [{ id: "m" }], has_more: true, next_before: "older" }
  const route = proxy("../app/api/chat/messages/route.ts", async (url, init) => {
    call = { url: new URL(url), init }
    return { ok: status < 400, status, json: async () => payload }
  })
  const history = await route.GET(request(null, "channel_id=c&limit=50&before=key"))
  assert.equal(call.url.searchParams.get("before"), "key")
  assert.equal(history.body.next_before, "older")
  assert.equal(history.body.has_more, true)
  status = 201
  payload = { id: "m" } // current backend MessageRead omits the stored client key
  const sent = await route.POST(request({ channel_id: "c", content: "hi", client_msg_id: "stable" }))
  assert.equal(JSON.parse(call.init.body).client_msg_id, "stable")
  assert.equal(sent.status, 201)
  assert.equal(sent.body.data[0].client_msg_id, "stable")
  for (status of [401, 403, 409, 422, 429, 503]) {
    payload = { detail: "specific server reason" }
    assert.equal((await route.POST(request({ channel_id: "c" }))).status, status)
    const failed = await route.GET(request(null))
    assert.equal(failed.status, status)
    assert.equal(failed.body.detail, payload.detail)
  }
})

test("proxy refuses unsigned calls and maps unreachable transport to 503", async () => {
  let calls = 0
  const transport = async () => { calls++; throw new Error("offline") }
  const denied = proxy("../app/api/chat/messages/route.ts", transport, null)
  assert.equal((await denied.GET(request(null))).status, 401)
  assert.equal(calls, 0)
  const unreachable = proxy("../app/api/chat/channels/[channelId]/members/route.ts", transport)
  assert.equal((await unreachable.POST(request({}), { params: Promise.resolve({ channelId: "c" }) })).status, 503)
})

test("approval decisions use POST decide with enum status; no pending reset", async () => {
  let call
  const route = proxy("../app/api/chat/approvals/route.ts", async (url, init) => {
    call = { url: new URL(url), init }
    return { ok: false, status: 409, json: async () => ({ detail: "Already approved" }) }
  })
  const response = await route.PATCH(request({ id: "approval", status: "approved" }, ""))
  assert.ok(call.url.pathname.endsWith("/approvals/approval/decide"))
  assert.equal(call.init.method, "POST")
  assert.deepEqual(JSON.parse(call.init.body), { status: "approved" })
  assert.equal(response.status, 409)
  assert.equal(response.body.detail, "Already approved")
  assert.equal((await route.PATCH(request({ id: "approval", status: "pending" }, ""))).status, 422)
})

test("channel and membership proxies preserve empty deletes and ownership failures", async () => {
  let call
  let status = 204
  const transport = async (url, init) => {
    call = { url: new URL(url), init }
    return { ok: status < 400, status, json: async () => ({ detail: "The channel creator cannot be removed" }) }
  }
  const channels = proxy("../app/api/chat/channels/[channelId]/route.ts", transport)
  const members = proxy("../app/api/chat/channels/[channelId]/members/[userId]/route.ts", transport)
  const context = { params: Promise.resolve({ channelId: "c", userId: "u" }) }
  const deleted = await channels.DELETE(request(null), context)
  assert.equal(deleted.status, 204)
  assert.equal(deleted.body, null)
  assert.equal(call.init.method, "DELETE")
  assert.equal((await members.DELETE(request(null), context)).status, 204)
  for (status of [403, 409]) {
    const response = await members.DELETE(request(null), context)
    assert.equal(response.status, status)
    assert.match(response.body.detail, /creator/)
  }
})

test("commRequest refreshes 401 once and keeps a stable payload; 403 is not retried", async () => {
  const originalFetch = globalThis.fetch
  let refreshes = 0
  const client = load("./comm-api.ts", {
    "@/lib/supabase/client": { supabase: { auth: { refreshSession: async () => { refreshes++ } } } },
    "@/lib/comm-messages": { detailText },
  })
  try {
    const bodies = []
    globalThis.fetch = async (_url, init) => {
      bodies.push(init.body)
      return new Response(JSON.stringify({ detail: "Expired" }), { status: 401 })
    }
    const result = await client.commRequest("POST", "/api/chat/messages", { client_msg_id: "stable" })
    assert.equal(result.status, 401)
    assert.equal(refreshes, 1)
    assert.equal(bodies.length, 2)
    assert.equal(bodies[0], bodies[1])
    let attempts = 0
    globalThis.fetch = async () => { attempts++; return new Response(JSON.stringify({ detail: "Denied" }), { status: 403 }) }
    const denied = await client.commRequest("POST", "/api/chat/messages", {})
    assert.equal(denied.detail, "Denied")
    assert.equal(attempts, 1)
  } finally { globalThis.fetch = originalFetch }
})
