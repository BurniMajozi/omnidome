import { joinSafePath, badPathResponse } from "@/lib/safe-path"
import { signedFetch } from "@/lib/internal-identity"
import { NextRequest, NextResponse } from "next/server"
import { verifiedRoleHeaders } from "@/lib/proxy-roles"
import { readBodyLimited, isNullBodyStatus } from "@/lib/proxy-body"

const PORTAL_BUILDER_SERVICE_URL = process.env.PORTAL_BUILDER_SERVICE_URL || "http://portal-builder:8026"
const DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
// Anonymous visitors: published page, shared preview, form submission (same set as proxy.ts PUBLIC_ROUTES).
const PUBLIC_PATH = /^api\/v1\/portal\/(?:public\/[A-Za-z0-9-]{1,100}|shared\/[A-Za-z0-9_-]{16,200}|submissions)$/
const ALLOW_DEV_HEADERS = process.env.NODE_ENV !== "production" && process.env.PORTAL_PROXY_ALLOW_DEV_HEADERS === "true"

async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const pathStr = joinSafePath(path)
  if (pathStr === null) return badPathResponse()
  const url = new URL(`${PORTAL_BUILDER_SERVICE_URL}/${pathStr}`)

  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.set(key, value)
  })

  const isPublic = PUBLIC_PATH.test(pathStr) && (request.method === "GET" || (request.method === "POST" && pathStr.endsWith("/submissions")))
  const headers = new Headers()
  for (const header of ["authorization", "x-tenant-id", "x-user-id", "x-roles", "x-permissions", "content-type", "idempotency-key"]) {
    const value = request.headers.get(header)
    if (value) headers.set(header, value)
  }

  if (isPublic) {
    // Never forward caller-supplied identity on anonymous routes.
    for (const h of ["authorization", "x-tenant-id", "x-user-id", "x-roles", "x-permissions"]) headers.delete(h)
    // The service rate-limits anonymous submissions per client IP (PORTAL_TRUST_PROXY).
    const fwd = request.headers.get("x-forwarded-for")
    if (fwd) headers.set("x-forwarded-for", fwd)
  } else if (!headers.has("x-tenant-id") || !headers.has("x-user-id")) {
    if (!ALLOW_DEV_HEADERS) return NextResponse.json({ error: "unauthorized" }, { status: 401 })
    if (!headers.has("x-tenant-id")) headers.set("x-tenant-id", DEV_TENANT_ID)
    if (!headers.has("x-user-id")) headers.set("x-user-id", DEV_USER_ID)
  }
  if (!isPublic) {
    // Least privilege: only the proxy.ts-verified roles; minimal role otherwise (never org_admin).
    const rp = verifiedRoleHeaders(request.headers, ["portal.write", "portal.publish", "portal.admin"])
    headers.set("x-roles", rp.roles)
    if (rp.permissions) headers.set("x-permissions", rp.permissions)
    else headers.delete("x-permissions")
  }

  try {
    const incoming = await readBodyLimited(request)
    if (!incoming.ok) return NextResponse.json({ error: incoming.error }, { status: incoming.status })
    const res = await signedFetch(url.toString(), {
      method: request.method,
      headers,
      body: incoming.body as BodyInit | undefined,
      signal: AbortSignal.timeout(pathStr === "api/v1/portal/design/suggest" ? 70_000 : 30_000),
    })
    const contentType = res.headers.get("content-type") || "application/json"
    const data = await res.arrayBuffer()
    // 204/205/304 must not carry a body: passing "" makes NextResponse throw,
    // which the catch below turned into a 502 for every successful DELETE.
    const noBody = isNullBodyStatus(res.status)
    const responseHeaders = new Headers({ "Content-Type": contentType })
    const disposition = res.headers.get("content-disposition")
    if (disposition) responseHeaders.set("content-disposition", disposition)
    return new NextResponse(noBody ? null : data, {
      status: res.status,
      headers: responseHeaders,
    })
  } catch (err) {
    return NextResponse.json({ error: "Portal service unreachable" }, { status: 502 })
  }
}

export function GET(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}

export function POST(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}

export function PUT(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}

export function PATCH(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}

export function DELETE(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}
