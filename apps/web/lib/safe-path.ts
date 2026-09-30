/**
 * Path-traversal guards shared by proxy.ts (edge gate) and every catch-all route
 * handler that joins user-supplied path segments into an upstream URL.
 *
 * Self-contained, erasable TS only, so it also runs under `node --test`.
 */

const ENCODED_SEPARATOR = /%(?:2e|2f|5c|00)/i
const BACKSLASH = String.fromCharCode(92)

function normalize(s: string): string {
  return s.normalize("NFKC").replace(/[․‥﹒．。｡]/g, ".")
}

/** Decode up to 3 layers so double/triple-encoded payloads are exposed. */
function decodeLayers(s: string): string[] {
  const out = [s]
  let cur = s
  for (let i = 0; i < 3; i++) {
    let next: string
    try {
      next = decodeURIComponent(cur)
    } catch {
      break
    }
    if (next === cur) break
    out.push(next)
    cur = next
  }
  return out
}

function unsafeText(s: string): boolean {
  if (ENCODED_SEPARATOR.test(s)) return true
  const n = normalize(s)
  for (const t of [s, n]) {
    if (t.includes(BACKSLASH) || t.includes("\u0000") || t.includes("//")) return true
  }
  return n.includes("..")
}

/** True when a request pathname (raw, and every decoded layer) could escape its prefix. */
export function hasUnsafePath(pathname: string): boolean {
  return decodeLayers(pathname).some(unsafeText)
}

/** True when a single (already router-decoded) path segment is unsafe to join into a URL. */
export function isUnsafeSegment(segment: string): boolean {
  if (typeof segment !== "string" || segment.length === 0) return true
  for (const layer of decodeLayers(segment)) {
    const n = normalize(layer)
    if (n === "." || n === "..") return true
    for (const t of [layer, n]) {
      if (t.includes("/") || t.includes(BACKSLASH)) return true
    }
    // control characters (includes NUL)
    if (/[\u0000-\u001f\u007f]/.test(layer)) return true
    if (ENCODED_SEPARATOR.test(layer)) return true
  }
  return false
}

/** Join catch-all segments for an upstream URL, or null when any segment is unsafe. */
export function joinSafePath(segments: string[] | undefined | null): string | null {
  if (!Array.isArray(segments)) return null
  for (const s of segments) if (isUnsafeSegment(s)) return null
  return segments.join("/")
}

export function badPathResponse(): Response {
  return Response.json({ error: "invalid_path" }, { status: 400, headers: { "cache-control": "no-store" } })
}
