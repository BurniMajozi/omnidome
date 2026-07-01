import { NextRequest, NextResponse } from "next/server"

// Uses a route handler (not a rewrite) so long-running STT/TTS generation
// doesn't hit the rewrite proxy's connection limits (ECONNRESET).
const CALL_CENTER_SERVICE_URL = process.env.CALL_CENTER_SERVICE_URL || "http://call_center:8007"
const DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const DEV_USER_ID = "00000000-0000-0000-0000-000000000002"
const ALLOW_DEV_HEADERS =
  process.env.NODE_ENV !== "production" || process.env.CALL_CENTER_PROXY_ALLOW_DEV_HEADERS === "true"

// 10 minutes — covers cold model load + inference on CPU-only hardware.
const TIMEOUT_MS = 600_000

async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const url = new URL(`${CALL_CENTER_SERVICE_URL}/${path.join("/")}`)
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value))

  const headers = new Headers()
  for (const h of ["authorization", "x-tenant-id", "x-user-id", "content-type"]) {
    const v = request.headers.get(h)
    if (v) headers.set(h, v)
  }
  if (ALLOW_DEV_HEADERS) {
    if (!headers.has("x-tenant-id")) headers.set("x-tenant-id", DEV_TENANT_ID)
    if (!headers.has("x-user-id")) headers.set("x-user-id", DEV_USER_ID)
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)

  try {
    const body = request.method !== "GET" && request.method !== "HEAD"
      ? await request.arrayBuffer()
      : undefined
    const res = await fetch(url.toString(), {
      method: request.method,
      headers,
      body,
      signal: controller.signal,
    })
    const data = await res.arrayBuffer()
    return new NextResponse(data, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("content-type") || "application/json" },
    })
  } catch (err: any) {
    if (err?.name === "AbortError") {
      return NextResponse.json({ error: "Call center request timed out — model may still be loading, try again shortly." }, { status: 504 })
    }
    return NextResponse.json({ error: "Call center service unreachable", details: String(err) }, { status: 502 })
  } finally {
    clearTimeout(timer)
  }
}

export function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) { return proxy(req, ctx) }
export function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) { return proxy(req, ctx) }
export function PUT(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) { return proxy(req, ctx) }
export function PATCH(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) { return proxy(req, ctx) }
export function DELETE(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) { return proxy(req, ctx) }
