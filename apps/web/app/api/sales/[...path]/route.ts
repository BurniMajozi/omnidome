import { NextRequest, NextResponse } from "next/server"
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

async function proxy(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  try {
    const { path } = await params
    const apiPath = path.join("/")
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
        headers.set("x-roles", "platform_admin,org_admin")
        headers.set("x-permissions", "sales.read,sales.write,crm.read,crm.write")
      }
    }

    if (!headers.has("x-tenant-id")) headers.set("x-tenant-id", DEV_TENANT_ID)
    if (!headers.has("x-user-id")) headers.set("x-user-id", DEV_USER_ID)
    if (!headers.has("x-roles")) headers.set("x-roles", "platform_admin,org_admin")

    const body = req.method !== "GET" && req.method !== "HEAD" ? await req.text() : undefined

    const res = await fetch(url, {
      method: req.method,
      headers,
      body,
      cache: "no-store",
    })

    const contentType = res.headers.get("content-type") || "application/json"
    const data = await res.text()
    return new NextResponse(data, {
      status: res.status,
      headers: { "Content-Type": contentType },
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
