/**
 * Anonymous pass-through for the customer-facing invoice / quote pages (app/pay/[token], app/quote/[token]).
 *
 * The generic app/svc/billing/[...path] handler fails closed without a verified identity, which is correct
 * for everything else; the public document endpoints authenticate with the unguessable share token in the
 * path instead (billing stores only its SHA-256, rate-limits per IP, and answers unknown/revoked/expired
 * tokens with an identical 404). This handler therefore forwards ONLY the five documented public calls,
 * with no identity headers, and nothing else:
 *   GET  /public/invoices/<token>            POST /public/invoices/<token>/pay
 *   GET  /public/quotes/<token>              POST /public/quotes/<token>/accept | decline
 * Anything else is a 404 here (it never reaches billing). The client IP is forwarded so billing's per-IP
 * limits apply to the real visitor.
 */
import { NextRequest, NextResponse } from "next/server"

const BILLING_SERVICE_URL = process.env.BILLING_SERVICE_URL || "http://billing:8003"
const TOKEN = "[A-Za-z0-9_-]{16,200}"
const ALLOWED: Array<{ method: "GET" | "POST"; re: RegExp }> = [
  { method: "GET", re: new RegExp(`^invoices/${TOKEN}$`) },
  { method: "POST", re: new RegExp(`^invoices/${TOKEN}/pay$`) },
  { method: "GET", re: new RegExp(`^quotes/${TOKEN}$`) },
  { method: "POST", re: new RegExp(`^quotes/${TOKEN}/(?:accept|decline)$`) },
]
const MAX_BODY = 4096

const notFound = () => NextResponse.json({ detail: "Not found" }, { status: 404, headers: { "cache-control": "no-store" } })

async function handle(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const sub = (path ?? []).join("/")
  const method = request.method.toUpperCase()
  if (!ALLOWED.some((a) => a.method === method && a.re.test(sub))) return notFound()

  const url = new URL(`${BILLING_SERVICE_URL}/public/${sub}`)
  if (method === "GET") url.searchParams.set("format", "json")

  const headers = new Headers()
  const ip = request.headers.get("x-forwarded-for")?.split(",").map((x) => x.trim()).filter(Boolean).pop() || request.headers.get("x-real-ip") || ""
  if (ip) headers.set("x-forwarded-for", ip)

  let body: string | undefined
  if (method === "POST") {
    body = await request.text()
    if (body.length > MAX_BODY) return NextResponse.json({ detail: "Request too large" }, { status: 413 })
    headers.set("content-type", "application/json")
    if (!body) body = "{}"
  }

  try {
    const res = await fetch(url, { method, headers, body, redirect: "manual", cache: "no-store", signal: AbortSignal.timeout(15_000) })
    const text = await res.text()
    return new NextResponse(text, {
      status: res.status,
      headers: { "content-type": res.headers.get("content-type") || "application/json", "cache-control": "no-store", "x-robots-tag": "noindex" },
    })
  } catch {
    return NextResponse.json({ detail: "Billing service unreachable" }, { status: 502, headers: { "cache-control": "no-store" } })
  }
}

export { handle as GET, handle as POST }
