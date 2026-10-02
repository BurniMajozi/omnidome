import test from "node:test"
import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import ts from "typescript"

// Exercise the actual pager without React, browser auth or service traffic.
const source = await readFile(new URL("./billing-api.ts", import.meta.url), "utf8")
const pager = source.slice(source.indexOf("export async function fetchPages"), source.indexOf("/** One page"))
const compiled = ts.transpileModule(`const BILLING_BASE = "/svc/billing"; const fetchLoadable = globalThis.__billingPageMock; ${pager}`, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText

async function run(responses, opts) {
  const urls = []
  globalThis.__billingPageMock = async url => { urls.push(url); return responses.shift() }
  const { fetchPages } = await import(`data:text/javascript;base64,${Buffer.from(compiled + `\n// ${Math.random()}`).toString("base64")}`)
  try { return { result: await fetchPages("/invoices?status=sent", opts), urls } }
  finally { delete globalThis.__billingPageMock }
}
const ready = (items, total) => ({ state: "ready", data: { items, total } })

test("billing paging reaches all pages and preserves filters", async () => {
  const { result, urls } = await run([ready([1, 2], 3), ready([3], 3)], { pageSize: 2 })
  assert.deepEqual(result.data, { items: [1, 2, 3], total: 3, truncated: false })
  assert.deepEqual(urls, ["/svc/billing/invoices?status=sent&page=1&page_size=2", "/svc/billing/invoices?status=sent&page=2&page_size=2"])
})
test("billing paging keeps partial rows and honest total after a later failure", async () => {
  const { result } = await run([ready([1, 2], 7), { state: "error", status: 403 }], { pageSize: 2 })
  assert.deepEqual(result.data, { items: [1, 2], total: 7, truncated: true })
})
test("billing paging preserves first-page denial and marks page cap", async () => {
  const denied = { state: "error", status: 403, message: "Forbidden" }
  assert.deepEqual((await run([denied])).result, denied)
  assert.equal((await run([ready([1, 2], 7)], { pageSize: 2, maxPages: 1 })).result.data.truncated, true)
})
test("billing paging rejects malformed successful responses", async () => {
  const { result } = await run([ready(null, 3)])
  assert.equal(result.state, "error")
})
