// Run: node --test lib/internal-identity.test.mjs   (Node >= 22.6 strips TS types natively)
// The vector below is duplicated in services/common/tests/test_internal_auth.py - keep in sync.
import test from "node:test"
import assert from "node:assert/strict"
import {
  canonicalString, signIdentity, signHeaders, backendPathForSvc, decodedPath, TS_HEADER, SIG_HEADER,
} from "./internal-identity.ts"

const SECRET = "test-secret-0123456789abcdef0123456789abcdef"
const FIELDS = {
  method: "POST",
  path: "/customers/list",
  ts: 1760000000,
  userId: "11111111-2222-3333-4444-555555555555",
  tenantId: "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
  roles: "org_admin, crm_user,org_admin",
  permissions: "crm.write,crm.read",
  modules: "crm,billing",
  orgId: "",
}
const VECTOR_SIG = "3cd5503774bc86f8754ac1d8aa1bac567b65573495c787cda266c38bd36f6a9e"
const VECTOR_CANONICAL =
  "v1\nPOST\n/customers/list\n1760000000\n11111111-2222-3333-4444-555555555555\n" +
  "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\ncrm_user,org_admin\ncrm.read,crm.write\nbilling,crm\n"

test("canonical string + signature match the Python verifier vector", async () => {
  assert.equal(canonicalString(FIELDS), VECTOR_CANONICAL)
  assert.equal(await signIdentity(SECRET, FIELDS), VECTOR_SIG)
})

test("signHeaders signs the final headers and clears stale signatures", async () => {
  process.env.INTERNAL_AUTH_SECRET = SECRET
  const h = new Headers({
    "x-user-id": FIELDS.userId, "x-tenant-id": FIELDS.tenantId, "x-roles": FIELDS.roles,
    "x-permissions": FIELDS.permissions, "x-modules": FIELDS.modules,
    [SIG_HEADER]: "stale", [TS_HEADER]: "1",
  })
  await signHeaders(h, "post", FIELDS.path, FIELDS.ts)
  assert.equal(h.get(SIG_HEADER), VECTOR_SIG)
  assert.equal(h.get(TS_HEADER), "1760000000")
})

test("no identity or no secret -> no signature", async () => {
  process.env.INTERNAL_AUTH_SECRET = SECRET
  const none = await signHeaders(new Headers({ [SIG_HEADER]: "stale" }), "GET", "/x")
  assert.equal(none.get(SIG_HEADER), null)
  delete process.env.INTERNAL_AUTH_SECRET
  const h = await signHeaders(new Headers({ "x-user-id": "u", "x-tenant-id": "t" }), "GET", "/x")
  assert.equal(h.get(SIG_HEADER), null)
})

test("rewrite path mapping strips /svc/<service> and decodes", () => {
  assert.equal(backendPathForSvc("/svc/communication/api/v1/channels"), "/api/v1/channels")
  assert.equal(backendPathForSvc("/svc/admin"), "/")
  assert.equal(backendPathForSvc("/svc/sales/deals/a%20b"), "/deals/a b")
  assert.equal(decodedPath("/a%zz"), "/a%zz")
})

test("tampering any field changes the signature", async () => {
  for (const patch of [{ roles: "platform_admin" }, { tenantId: "x" }, { path: "/other" }, { method: "GET" }, { ts: FIELDS.ts + 1 }]) {
    assert.notEqual(await signIdentity(SECRET, { ...FIELDS, ...patch }), VECTOR_SIG)
  }
})
