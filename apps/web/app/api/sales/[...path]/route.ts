import { devFallbackAllowed } from "@/lib/dev-identity"
import { joinSafePath, badPathResponse } from "@/lib/safe-path"
import { signedFetch } from "@/lib/internal-identity"
import { NextRequest, NextResponse } from "next/server"
import { verifiedRoleHeaders } from "@/lib/proxy-roles"
import { getSupabaseServer } from "@/lib/supabase/server"

const SALES_SERVICE_URL =
  process.env.SALES_SERVICE_URL || "http://sales:8002"
const ADMIN_SERVICE_URL = process.env.ADMIN_SERVICE_URL || "http://admin:8013"
const INTERNAL_SERVICE_KEY = process.env.INTERNAL_SERVICE_KEY || ""
const DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const DEV_USER_ID = "00000000-0000-0000-0000-000000000001"

async function resolveIdentity(bearerToken: string): Promise<{ userId: string; tenantId: string } | null> {
  const { client } = getSupabaseServer()
  if (!client) return null

  const { data, error } = await client.auth.getUser(bearerToken)
  if (error || !data.user?.email) return null

  try {
    const res = await signedFetch(
      `${ADMIN_SERVICE_URL}/internal/users/by-email?email=${encodeURIComponent(data.user.email)}`,
      { headers: { "x-internal-key": INTERNAL_SERVICE_KEY } },
    )
    if (!res.ok) return null
    const body = await res.json()
    return { userId: body.user_id, tenantId: body.tenant_id }
  } catch {
    return null
  }
}

async function proxy(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  try {
    const { path } = await params
    const apiPath = joinSafePath(path)
    if (apiPath === null) return badPathResponse()
    const searchParams = req.nextUrl.searchParams.toString()
    const url = `${SALES_SERVICE_URL}/${apiPath}${searchParams ? `?${searchParams}` : ""}`

    const headers = new Headers()
    for (const h of ["authorization", "x-tenant-id", "x-user-id", "x-roles", "x-permissions", "content-type"]) {
      const val = req.headers.get(h)
      if (val) headers.set(h, val)
    }

    const authHeader = req.headers.get("authorization")
    if (authHeader?.startsWith("Bearer ")) {
      const token = authHeader.slice(7).trim()
      const identity = await resolveIdentity(token)
      if (identity) {
        headers.set("x-user-id", identity.userId)
        headers.set("x-tenant-id", identity.tenantId)
      }
    }

    if (!headers.has("x-tenant-id") || !headers.has("x-user-id")) {
      if (!devFallbackAllowed()) return NextResponse.json({ error: "unauthorized" }, { status: 401 })
      if (!headers.has("x-tenant-id")) headers.set("x-tenant-id", DEV_TENANT_ID)
      if (!headers.has("x-user-id")) headers.set("x-user-id", DEV_USER_ID)
    }
    // Least privilege: only the proxy.ts-verified roles; minimal role otherwise (never platform_admin/org_admin).
    const rp = verifiedRoleHeaders(req.headers, ["sales.read", "sales.write", "crm.read", "crm.write"])
    headers.set("x-roles", rp.roles)
    if (rp.permissions) headers.set("x-permissions", rp.permissions)
    else headers.delete("x-permissions")

    const body = req.method !== "GET" && req.method !== "HEAD" ? await req.text() : undefined

    const res = await signedFetch(url, {
      method: req.method,
      headers,
      body,
      cache: "no-store",
    })

    const contentType = res.headers.get("content-type") || "application/json"
    const data = await res.text()
    // 204/205/304 must not carry a body: passing "" makes NextResponse throw,
    // which the catch below turned into a 502 for every successful DELETE.
    const noBody = res.status === 204 || res.status === 205 || res.status === 304
    const outHeaders: Record<string, string> = { "Content-Type": contentType }
    // Pagination metadata from list endpoints (GET /deals): "showing N of total".
    for (const h of ["x-total-count", "x-limit", "x-offset"]) {
      const v = res.headers.get(h)
      if (v !== null) outHeaders[h] = v
    }
    return new NextResponse(noBody ? null : data, {
      status: res.status,
      headers: outHeaders,
    })
  } catch (err) {
    console.error("Sales service proxy error:", err)
    return NextResponse.json({ error: "Sales service unavailable", details: String(err) }, { status: 503 })
  }
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx)
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx)
}

export async function PUT(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx)
}

export async function PATCH(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx)
}

export async function DELETE(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx)
}
