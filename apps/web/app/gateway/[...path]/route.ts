import { joinSafePath, badPathResponse } from "@/lib/safe-path"
import { signedFetch } from "@/lib/internal-identity"
import { NextRequest, NextResponse } from "next/server"

/**
 * Same-origin, gated path to the API gateway (browser -> /gateway/* -> gateway).
 * proxy.ts has already verified the Supabase session and injected x-user-id /
 * x-tenant-id / x-roles, so the browser never needs (or gets) direct access to the
 * gateway port. Runtime env GATEWAY_SERVICE_URL, default = Docker DNS.
 */
const GATEWAY_SERVICE_URL = (process.env.GATEWAY_SERVICE_URL || "http://gateway:8000").replace(/\/$/, "")

const FORWARD = ["authorization", "x-tenant-id", "x-user-id", "x-roles", "content-type", "accept"]

async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const gatewayPath = joinSafePath(path)
  if (gatewayPath === null) return badPathResponse()
  const url = new URL(`${GATEWAY_SERVICE_URL}/${gatewayPath}`)
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.append(key, value))

  const headers = new Headers()
  for (const h of FORWARD) {
    const v = request.headers.get(h)
    if (v) headers.set(h, v)
  }

  try {
    const body = request.method !== "GET" && request.method !== "HEAD" ? await request.text() : undefined
    const res = await signedFetch(url.toString(), { method: request.method, headers, body, cache: "no-store" })
    const noBody = res.status === 204 || res.status === 205 || res.status === 304
    return new NextResponse(noBody ? null : await res.text(), {
      status: res.status,
      headers: { "Content-Type": res.headers.get("content-type") || "application/json" },
    })
  } catch (err) {
    return NextResponse.json({ error: "Gateway unreachable", details: String(err) }, { status: 502 })
  }
}

export const GET = proxy
export const POST = proxy
export const PUT = proxy
export const PATCH = proxy
export const DELETE = proxy
