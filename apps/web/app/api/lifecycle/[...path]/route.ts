import { devFallbackAllowed } from "@/lib/dev-identity"
import { joinSafePath, badPathResponse } from "@/lib/safe-path"
import { signedFetch } from "@/lib/internal-identity"
import { NextRequest, NextResponse } from "next/server"
import { verifiedRoleHeaders } from "@/lib/proxy-roles"

const LIFECYCLE_SERVICE_URL =
  process.env.LIFECYCLE_SERVICE_URL || "http://lifecycle:8018"

const DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const DEV_USER_ID = "00000000-0000-0000-0000-000000000001"

type Context = { params: Promise<{ path: string[] }> }

async function proxy(req: NextRequest, { params }: Context): Promise<NextResponse> {
  try {
    const { path } = await params
    const pathStr = joinSafePath(path)
    if (pathStr === null) return NextResponse.json({ error: "invalid_path" }, { status: 400 })
    const targetUrl = new URL(`${LIFECYCLE_SERVICE_URL}/${pathStr}`)

    // Forward query parameters
    req.nextUrl.searchParams.forEach((value, key) => {
      targetUrl.searchParams.set(key, value)
    })

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    }
    const authHeader = req.headers.get("authorization")
    if (authHeader) headers["Authorization"] = authHeader
    const tenantHeader = req.headers.get("x-tenant-id")
    if (tenantHeader) headers["x-tenant-id"] = tenantHeader
    const userHeader = req.headers.get("x-user-id")
    if (userHeader) headers["x-user-id"] = userHeader
    const rolesHeader = req.headers.get("x-roles")
    if (rolesHeader) headers["x-roles"] = rolesHeader

    if (!headers["x-tenant-id"] || !headers["x-user-id"]) {
      if (!devFallbackAllowed()) return NextResponse.json({ error: "unauthorized" }, { status: 401 })
      if (!headers["x-tenant-id"]) headers["x-tenant-id"] = DEV_TENANT_ID
      if (!headers["x-user-id"]) headers["x-user-id"] = DEV_USER_ID
    }
    // Least privilege: only the proxy.ts-verified roles; minimal role otherwise (never platform_admin/org_admin).
    headers["x-roles"] = verifiedRoleHeaders(req.headers, []).roles

    const init: RequestInit = { method: req.method, headers }
    if (req.method !== "GET" && req.method !== "HEAD") {
      init.body = await req.text()
    }

    const res = await signedFetch(targetUrl.toString(), init)
    const contentType = res.headers.get("content-type") || ""

    if (contentType.includes("application/json")) {
      const data = await res.json()
      return NextResponse.json(data, { status: res.status })
    }

    const text = await res.text()
    return new NextResponse(text, {
      status: res.status,
      headers: { "Content-Type": contentType || "text/plain" },
    })
  } catch (err) {
    console.error("Lifecycle proxy error:", err)
    return NextResponse.json({ error: "Lifecycle service unavailable" }, { status: 503 })
  }
}

export async function GET(req: NextRequest, ctx: Context) { return proxy(req, ctx) }
export async function POST(req: NextRequest, ctx: Context) { return proxy(req, ctx) }
export async function PUT(req: NextRequest, ctx: Context) { return proxy(req, ctx) }
export async function PATCH(req: NextRequest, ctx: Context) { return proxy(req, ctx) }
export async function DELETE(req: NextRequest, ctx: Context) { return proxy(req, ctx) }
