// Run: node --test lib/identity-resolve.test.mjs
import test from "node:test"
import assert from "node:assert/strict"
import { classifyAdminResponse, resolveIdentityDecision, STALE_ON_ERROR_MS } from "./identity-resolve.ts"

const U = "11111111-2222-3333-4444-555555555555"
const T = "00000000-0000-0000-0000-000000000001"
const T2 = "00000000-0000-0000-0000-000000000002"
const ok = (o = {}) => ({ kind: "ok", userId: U, tenantId: T, roles: ["org_admin"], isActive: true, ...o })
const run = (lookup, extra = {}) =>
  resolveIdentityDecision({ lookup, supabaseUserId: "sb-id", appMetadata: undefined, stale: null, now: 1_000_000, ...extra })

test("classify: 2xx ok, 404 not found, everything else unavailable", () => {
  assert.equal(classifyAdminResponse(200, { user_id: U, tenant_id: T, roles: ["a", "bad role!"], is_active: false }).isActive, false)
  assert.deepEqual(classifyAdminResponse(200, { user_id: U, tenant_id: T, roles: ["a", "bad role!"] }).roles, ["a"])
  assert.equal(classifyAdminResponse(404, { detail: "User not found" }).kind, "not_found")
  assert.equal(classifyAdminResponse(404, { detail: "Not Found" }).kind, "unavailable") // wrong route / proxy
  for (const s of [401, 403, 429, 500, 502, 503]) assert.equal(classifyAdminResponse(s, {}).kind, "unavailable")
  assert.equal(classifyAdminResponse(200, { user_id: "x", tenant_id: T }).kind, "unavailable")
  assert.equal(classifyAdminResponse(200, undefined).kind, "unavailable")
})

test("active admin user: DB tenant + roles, platform_admin kept from app_metadata", () => {
  const r = run(ok(), { appMetadata: { tenant_id: T2, roles: ["platform_admin", "org_user"] } })
  assert.equal(r.kind, "identity")
  assert.equal(r.identity.tenantId, T) // DB wins over a stale metadata tenant
  assert.equal(r.identity.roles, "org_admin,platform_admin")
})

test("active user with no DB roles falls back to app_metadata roles", () => {
  const r = run(ok({ roles: [] }), { appMetadata: { roles: ["hr_manager"] } })
  assert.equal(r.identity.roles, "hr_manager")
})

test("definitive is_active=false -> inactive, even with permissive app_metadata and a stale entry", () => {
  const r = run(ok({ isActive: false }), {
    appMetadata: { tenant_id: T, roles: ["org_admin"] },
    stale: { identity: { userId: U, tenantId: T }, at: 999_999 },
  })
  assert.equal(r.kind, "inactive")
})

test("unavailable + no stale entry -> fail closed (503), never app_metadata", () => {
  const r = run({ kind: "unavailable" }, { appMetadata: { tenant_id: T, roles: ["org_admin"] } })
  assert.equal(r.kind, "unavailable")
  assert.ok(r.retryAfter > 0)
})

test("unavailable + stale entry within window -> reuse; beyond window -> 503", () => {
  const identity = { userId: U, tenantId: T, roles: "org_user" }
  const within = run({ kind: "unavailable" }, { stale: { identity, at: 1_000_000 - STALE_ON_ERROR_MS } })
  assert.equal(within.kind, "identity")
  assert.equal(within.fresh, false)
  assert.equal(within.identity, identity)
  const beyond = run({ kind: "unavailable" }, { stale: { identity, at: 1_000_000 - STALE_ON_ERROR_MS - 1 } })
  assert.equal(beyond.kind, "unavailable")
  assert.ok(STALE_ON_ERROR_MS <= 30_000)
})

test("definitive 404 (never known): app_metadata fallback as before", () => {
  const r = run({ kind: "not_found" }, { appMetadata: { tenant_id: T, roles: ["platform_admin"] } })
  assert.equal(r.kind, "identity")
  assert.deepEqual(r.identity, { userId: "sb-id", tenantId: T, roles: "platform_admin" })
  assert.equal(run({ kind: "not_found" }).kind, "no-tenant")
  assert.equal(run({ kind: "not_found" }, { appMetadata: { tenant_id: "not-a-uuid" } }).kind, "no-tenant")
  assert.equal(run({ kind: "not_found" }, { appMetadata: { tenant_id: T, is_active: false } }).kind, "inactive")
})

test("no internal key configured (dev): app_metadata fallback", () => {
  assert.equal(run({ kind: "not_configured" }, { appMetadata: { tenant_id: T } }).kind, "identity")
})
