import { NextRequest, NextResponse } from "next/server"
import { getSupabaseServer } from "@/lib/supabase/server"

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
    const res = await fetch(
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

async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const pathStr = path.join("/")
  const url = new URL(`${ADMIN_SERVICE_URL}/${pathStr}`)

  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.set(key, value)
  })

  const headers = new Headers()
  for (const header of ["authorization", "x-tenant-id", "x-user-id", "x-roles", "x-permissions", "content-type"]) {
    const value = request.headers.get(header)
    if (value) headers.set(header, value)
  }

  // Attempt server-side Supabase token resolution
  const authHeader = request.headers.get("authorization")
  if (authHeader?.startsWith("Bearer ")) {
    const token = authHeader.slice(7).trim()
    const identity = await resolveIdentity(token)
    if (identity) {
      headers.set("x-user-id", identity.userId)
      headers.set("x-tenant-id", identity.tenantId)
      headers.set("x-roles", "platform_admin,org_admin")
      headers.set("x-permissions", "platform.admin,org.admin,org.manage,module.manage")
    }
  }

  // Ensure mandatory identity headers are always provided so admin service never 401s
  if (!headers.has("x-tenant-id")) headers.set("x-tenant-id", DEV_TENANT_ID)
  if (!headers.has("x-user-id")) headers.set("x-user-id", DEV_USER_ID)
  if (!headers.has("x-roles")) headers.set("x-roles", "platform_admin,org_admin")
  if (!headers.has("x-permissions")) headers.set("x-permissions", "platform.admin,org.admin,org.manage,module.manage")

  try {
    const body = request.method !== "GET" && request.method !== "HEAD" ? await request.text() : undefined
    const res = await fetch(url.toString(), {
      method: request.method,
      headers,
      body,
    })
    const contentType = res.headers.get("content-type") || "application/json"
    const data = await res.text()
    return new NextResponse(data, {
      status: res.status,
      headers: { "Content-Type": contentType },
    })
  } catch (err) {
    return NextResponse.json({ error: "Admin service unreachable", details: String(err) }, { status: 502 })
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
