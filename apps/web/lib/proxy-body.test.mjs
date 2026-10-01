// Run: node --test lib/proxy-body.test.mjs
import test from "node:test"
import assert from "node:assert/strict"
import { readBodyLimited, isNullBodyStatus, MAX_PROXY_BODY_BYTES } from "./proxy-body.ts"

const post = (body, headers = {}) =>
  new Request("http://x/upload", { method: "POST", body, headers, duplex: "half" })

test("binary bytes survive unchanged (text() would corrupt them)", async () => {
  const bytes = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0xff, 0xfe, 0x00, 0x80, 0xc3, 0x28])
  const r = await readBodyLimited(post(bytes, { "content-type": "application/pdf" }))
  assert.equal(r.ok, true)
  assert.deepEqual(Array.from(r.body), Array.from(bytes))
  assert.equal(r.contentType, "application/pdf")
})

test("multipart boundary in Content-Type is preserved verbatim", async () => {
  const fd = new FormData()
  fd.append("file", new Blob([new Uint8Array([0, 255, 1, 254])]), "a.bin")
  const req = post(fd)
  const ct = req.headers.get("content-type")
  assert.match(ct, /^multipart\/form-data; boundary=/)
  const r = await readBodyLimited(req)
  assert.equal(r.contentType, ct)
  assert.ok(r.body.byteLength > 4)
})

test("GET has no body", async () => {
  const r = await readBodyLimited(new Request("http://x/y"))
  assert.deepEqual(r, { ok: true, body: undefined, contentType: undefined })
})

test("declared Content-Length over the limit -> 413 without reading", async () => {
  const r = await readBodyLimited(post("x", { "content-length": String(MAX_PROXY_BODY_BYTES + 1) }))
  assert.equal(r.ok, false)
  assert.equal(r.status, 413)
})

test("undeclared oversize body is cut off while streaming -> 413", async () => {
  const stream = new ReadableStream({
    pull(c) {
      c.enqueue(new Uint8Array(600))
    },
  })
  const req = new Request("http://x/u", { method: "POST", body: stream, duplex: "half" })
  const r = await readBodyLimited(req, 2000)
  assert.equal(r.ok, false)
  assert.equal(r.status, 413)
})

test("exactly at the limit is accepted", async () => {
  const r = await readBodyLimited(post(new Uint8Array(1000)), 1000)
  assert.equal(r.ok, true)
  assert.equal(r.body.byteLength, 1000)
})

test("invalid content-length -> 400", async () => {
  const r = await readBodyLimited(post("x", { "content-length": "abc" }))
  assert.equal(r.ok, false)
  assert.equal(r.status, 400)
})

test("null-body statuses", () => {
  assert.equal(isNullBodyStatus(204), true)
  assert.equal(isNullBodyStatus(304), true)
  assert.equal(isNullBodyStatus(200), false)
  assert.equal(isNullBodyStatus(501), false)
})
