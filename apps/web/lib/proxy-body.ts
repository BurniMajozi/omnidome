/**
 * Raw request-body forwarding for server-side proxy routes.
 *
 * `req.text()` decodes the body as UTF-8, which silently corrupts multipart /
 * binary uploads (PDFs, images). These helpers read the exact bytes and keep
 * the original Content-Type (including the multipart boundary). Pure (Web
 * Request/Headers only) so node --test can load it.
 */

/** Default upload ceiling for the compliance proxy (documents). */
export const MAX_PROXY_BODY_BYTES = 15 * 1024 * 1024

export type BodyResult =
  | { ok: true; body: Uint8Array | undefined; contentType: string | undefined }
  | { ok: false; status: 413 | 400; error: string }

/**
 * Read the request body as raw bytes, enforcing `maxBytes`.
 * - GET/HEAD: no body.
 * - A declared Content-Length above the limit is rejected before reading.
 * - Chunked / undeclared bodies are counted while streaming and aborted early.
 * The returned contentType is the original header value, untouched.
 */
export async function readBodyLimited(
  req: Request,
  maxBytes: number = MAX_PROXY_BODY_BYTES,
): Promise<BodyResult> {
  const method = req.method.toUpperCase()
  const contentType = req.headers.get("content-type") ?? undefined
  if (method === "GET" || method === "HEAD") return { ok: true, body: undefined, contentType }

  const declared = req.headers.get("content-length")
  if (declared !== null) {
    const n = Number(declared)
    if (!Number.isFinite(n) || n < 0) return { ok: false, status: 400, error: "invalid content-length" }
    if (n > maxBytes) return { ok: false, status: 413, error: "request body too large" }
  }

  if (!req.body) return { ok: true, body: undefined, contentType }

  const reader = req.body.getReader()
  const chunks: Uint8Array[] = []
  let total = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    total += value.byteLength
    if (total > maxBytes) {
      try {
        await reader.cancel()
      } catch {
        /* ignore */
      }
      return { ok: false, status: 413, error: "request body too large" }
    }
    chunks.push(value)
  }
  if (total === 0) return { ok: true, body: undefined, contentType }
  const out = new Uint8Array(total)
  let off = 0
  for (const c of chunks) {
    out.set(c, off)
    off += c.byteLength
  }
  return { ok: true, body: out, contentType }
}

/** Statuses that must not carry a body (Response constructor throws otherwise). */
export function isNullBodyStatus(status: number): boolean {
  return status === 204 || status === 205 || status === 304 || (status >= 100 && status < 200)
}
