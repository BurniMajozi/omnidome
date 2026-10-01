import { devFallbackAllowed } from "@/lib/dev-identity"
import { joinSafePath, badPathResponse } from "@/lib/safe-path"
import { signedFetch } from "@/lib/internal-identity"
import { NextRequest, NextResponse } from "next/server"
import { verifiedRoleHeaders } from "@/lib/proxy-roles"
import { readBodyLimited, isNullBodyStatus } from "@/lib/proxy-body"

const COMPLIANCE_SERVICE_URL =
  process.env.COMPLIANCE_SERVICE_URL || "http://compliance:8019"
const DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const DEV_USER_ID = "00000000-0000-0000-0000-000000000002"

async function proxy(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
  method: string
) {
  try {
    const { path } = await params
    const apiPath = joinSafePath(path)
    if (apiPath === null) return badPathResponse()
    const searchParams = req.nextUrl.searchParams.toString()
    const url = `${COMPLIANCE_SERVICE_URL}/${apiPath}${searchParams ? `?${searchParams}` : ""}`

    const headers: Record<string, string> = {}
    for (const header of ["authorization", "x-tenant-id", "x-user-id", "x-roles", "x-permissions"]) {
      const value = req.headers.get(header)
      if (value) headers[header] = value
    }

    if (!headers["x-tenant-id"] || !headers["x-user-id"]) {
      if (!devFallbackAllowed()) return NextResponse.json({ error: "unauthorized" }, { status: 401 })
      if (!headers["x-tenant-id"]) headers["x-tenant-id"] = DEV_TENANT_ID
      if (!headers["x-user-id"]) headers["x-user-id"] = DEV_USER_ID
    }
    // Least privilege: only the proxy.ts-verified roles; minimal role otherwise (never org_admin).
    const rp = verifiedRoleHeaders(req.headers, ["compliance.read", "compliance.write", "compliance.admin"])
    headers["x-roles"] = rp.roles
    if (rp.permissions) headers["x-permissions"] = rp.permissions
    else delete headers["x-permissions"]

    const init: RequestInit = { method, headers, cache: "no-store" }
    if (method !== "GET" && method !== "HEAD") {
      // Raw bytes + the ORIGINAL Content-Type (multipart boundary included);
      // req.text() would corrupt binary uploads. Content-Length is recomputed
      // by fetch from the exact bytes. Oversize bodies are rejected with 413.
      const read = await readBodyLimited(req)
      if (!read.ok) return NextResponse.json({ error: read.error }, { status: read.status })
      if (read.body) init.body = read.body as unknown as BodyInit
      if (read.contentType) headers["Content-Type"] = read.contentType
      else if (read.body) headers["Content-Type"] = "application/octet-stream"
    }

    const res = await signedFetch(url, init)
    if (isNullBodyStatus(res.status)) return new NextResponse(null, { status: res.status })
    const out = new Headers()
    for (const h of ["content-type", "content-disposition"]) {
      const v = res.headers.get(h)
      if (v) out.set(h, v)
    }
    // Pass bytes through untouched (JSON, text and file downloads alike).
    return new NextResponse(await res.arrayBuffer(), { status: res.status, headers: out })
  } catch (err) {
    console.error("Compliance service proxy error:", err)
    return NextResponse.json({ error: "Compliance service unavailable" }, { status: 503 })
  }
}

export function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx, "GET")
}

export function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx, "POST")
}

export function PUT(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx, "PUT")
}

export function PATCH(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx, "PATCH")
}

export function DELETE(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx, "DELETE")
}
