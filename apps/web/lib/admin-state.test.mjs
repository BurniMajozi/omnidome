// Run: node --test lib/admin-state.test.mjs   (Node >= 22.6 strips TS types natively)
import test from "node:test"
import assert from "node:assert/strict"
import {
  adminVisibility,
  canRequestSection,
  requiredRoleLabel,
  deniedState,
  statusFromError,
  loadableFromError,
  syncBadge,
  deactivateNotice,
  isSystemRole,
  canEditRole,
  resolveUserId,
  validateTier,
  readyData,
} from "./admin-state.ts"

test("visibility by role", () => {
  assert.deepEqual(adminVisibility(["platform_admin"]), { platform: true, tenantAdmin: true })
  assert.deepEqual(adminVisibility(["org_admin"]), { platform: false, tenantAdmin: true })
  assert.deepEqual(adminVisibility(["owner"]), { platform: false, tenantAdmin: true })
  assert.deepEqual(adminVisibility(["manager", "org_user"]), { platform: false, tenantAdmin: false })
  assert.deepEqual(adminVisibility(undefined), { platform: false, tenantAdmin: false })
})

test("platform-only sections are never requested for tenant admins", () => {
  for (const s of ["tenants", "seats"]) {
    assert.equal(canRequestSection(["platform_admin"], s), true)
    assert.equal(canRequestSection(["org_admin"], s), false)
    assert.equal(canRequestSection(["owner"], s), false)
  }
})

test("tenant-admin sections: admins yes, plain members no", () => {
  for (const s of ["team", "users", "audit", "commission", "protocols"]) {
    assert.equal(canRequestSection(["org_admin"], s), true)
    assert.equal(canRequestSection(["platform_admin"], s), true)
    assert.equal(canRequestSection(["org_user"], s), false)
    assert.equal(canRequestSection([], s), false)
  }
  assert.equal(canRequestSection(["org_user"], "modules"), true)
})

test("required role label and denied state", () => {
  assert.equal(requiredRoleLabel("tenants"), "platform_admin")
  assert.equal(requiredRoleLabel("users"), "org_admin or owner")
  assert.deepEqual(deniedState(), { state: "denied", status: 403 })
})

test("statusFromError reads status, message, and network failures", () => {
  assert.equal(statusFromError({ status: 403 }), 403)
  assert.equal(statusFromError(new Error("UCP list failed: 502")), 502)
  assert.equal(statusFromError(new Error("Admin API error 500: {\"x\":1}")), 500)
  assert.equal(statusFromError(new TypeError("fetch failed")), null)
  const t = new Error("timed out")
  t.name = "TimeoutError"
  assert.equal(statusFromError(t), null)
  assert.equal(statusFromError(new Error("boom")), null)
})

test("loadableFromError maps to honest states", () => {
  assert.equal(loadableFromError({ status: 403 }).state, "denied")
  assert.equal(loadableFromError({ status: 401 }).state, "denied")
  assert.equal(loadableFromError({ status: 502 }).state, "unreachable")
  assert.equal(loadableFromError(new TypeError("fetch failed")).state, "unreachable")
  const e = loadableFromError({ status: 500 }, () => "raw body")
  assert.equal(e.state, "error")
  assert.equal(e.message, undefined) // never surface raw 5xx text
  const c = loadableFromError({ status: 409 }, () => "Roles are immutable")
  assert.equal(c.state, "error")
  assert.equal(c.message, "Roles are immutable")
})

test("sync badge from status code", () => {
  assert.deepEqual(syncBadge("pending"), { label: "Sync pending", tone: "pending" })
  assert.deepEqual(syncBadge("failed"), { label: "Sync failed - retry", tone: "failed" })
  assert.equal(syncBadge("synced"), null)
  assert.equal(syncBadge(undefined), null)
  assert.equal(syncBadge(null), null)
})

test("deactivate notice only when sessions_revoked is exactly false", () => {
  assert.match(deactivateNotice({ sessions_revoked: false }), /within about an hour/)
  assert.equal(deactivateNotice({ sessions_revoked: true }), null)
  assert.equal(deactivateNotice({}), null)
  assert.equal(deactivateNotice(null), null)
})

test("system roles are immutable", () => {
  assert.equal(isSystemRole({ name: "org_admin" }), true)
  assert.equal(isSystemRole({ name: "custom_x", is_system: true }), true)
  assert.equal(isSystemRole({ name: "custom_x", is_system: false }), false)
  assert.equal(canEditRole({ name: "owner" }), false)
  assert.equal(canEditRole({ name: "field_tech" }), true)
  assert.equal(canEditRole(null), false)
})

test("resolveUserId accepts uuid or a known email only", () => {
  const users = [{ id: "11111111-2222-3333-4444-555555555555", email: "a@example.test" }]
  assert.equal(resolveUserId("11111111-2222-3333-4444-555555555555", users), "11111111-2222-3333-4444-555555555555")
  assert.equal(resolveUserId("A@Example.test", users), "11111111-2222-3333-4444-555555555555")
  assert.equal(resolveUserId("b@example.test", users), null)
  assert.equal(resolveUserId("not-an-id", users), null)
  assert.equal(resolveUserId("  ", users), null)
})

test("validateTier", () => {
  const ok = { name: "Gold", minDeals: 5, maxDeals: "", rate: "7.5" }
  assert.equal(validateTier(ok), null)
  assert.match(validateTier({ ...ok, name: " " }), /name/i)
  assert.match(validateTier({ ...ok, minDeals: -1 }), /Min deals/)
  assert.match(validateTier({ ...ok, maxDeals: "2" }), /Max deals/)
  assert.match(validateTier({ ...ok, rate: "" }), /required/)
  assert.match(validateTier({ ...ok, rate: "101" }), /between 0 and 100/)
  assert.match(validateTier({ ...ok, rate: "abc" }), /between 0 and 100/)
})

test("readyData is empty unless ready", () => {
  assert.deepEqual(readyData({ state: "loading" }), [])
  assert.deepEqual(readyData({ state: "denied", status: 403 }), [])
  assert.deepEqual(readyData({ state: "ready", data: [1, 2] }), [1, 2])
})
