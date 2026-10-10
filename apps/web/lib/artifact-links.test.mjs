// Run: node --test lib/artifact-links.test.mjs   (Node >= 22.6 strips TS types natively)
import test from "node:test"
import assert from "node:assert/strict"
import { artifactItemsFromToolCalls, kindLabel, safeAppPath, safeExternalUrl, sanitizeArtifactItem } from "./artifact-links.ts"

const OK = "/dashboard?section=analytics&sub=presentations&deck=11111111-2222-3333-4444-555555555555"

test("safeAppPath accepts only same-origin dashboard paths", () => {
  assert.equal(safeAppPath(OK), OK)
  assert.equal(safeAppPath("/dashboard"), "/dashboard")
  for (const bad of [
    "javascript:alert(1)", "https://evil.example/dashboard", "//evil.example/dashboard", "/\evil.example",
    "/dashboardx", "/auth", "/dashboard?x=<script>", "/dashboard\n", "data:text/html,x", "", null, undefined, 5,
  ]) assert.equal(safeAppPath(bad), null, String(bad))
})

test("safeExternalUrl allows http(s) only", () => {
  assert.ok(safeExternalUrl("https://example.com/a"))
  assert.equal(safeExternalUrl("javascript:alert(1)"), null)
  assert.equal(safeExternalUrl("not a url"), null)
})

test("sanitizeArtifactItem drops items without a safe link or title and tolerates unknown kinds", () => {
  assert.equal(sanitizeArtifactItem({ title: "x", deep_link: "javascript:1" }), null)
  assert.equal(sanitizeArtifactItem({ deep_link: OK }), null)
  const it = sanitizeArtifactItem({ kind: "weird_kind", title: "T", deep_link: OK, version: 4, status: "draft", extra: "<b>" })
  assert.equal(it.href, OK)
  assert.equal(it.version, 4)
  assert.equal(kindLabel("weird_kind"), "weird kind")
  assert.equal(kindLabel("deck"), "Deck")
})

test("artifactItemsFromToolCalls reads artifacts.find results (object or JSON string), dedupes and caps", () => {
  const item = (n) => ({ kind: "deck", title: `D${n}`, deep_link: OK.replace("5555", String(1000 + n)) })
  const calls = [
    { toolName: "web.search", result: { data: { items: [item(9)] } } },
    { toolName: "artifacts.find", result: { success: true, data: { items: [item(1), item(1), item(2)] } } },
    { toolName: "artifacts.find", result: JSON.stringify({ data: { items: [item(3), item(4), { title: "bad", deep_link: "https://x" }] } }) },
  ]
  const out = artifactItemsFromToolCalls(calls)
  assert.deepEqual(out.map((i) => i.title), ["D1", "D2", "D3"])
  assert.deepEqual(artifactItemsFromToolCalls(undefined), [])
})

test("weak (semantic-only) matches produce no link cards", () => {
  const calls = [{ toolName: "artifacts.find", result: { data: { weak_match: true, items: [{ title: "Q", deep_link: OK }] } } }]
  assert.deepEqual(artifactItemsFromToolCalls(calls), [])
})
