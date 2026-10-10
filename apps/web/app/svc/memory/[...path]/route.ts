import { joinSafePath, badPathResponse } from "@/lib/safe-path"
import { signedFetch } from "@/lib/internal-identity"
import { NextRequest, NextResponse } from "next/server"

const TENANT_MEMORY_SERVICE_URL =
  process.env.TENANT_MEMORY_SERVICE_URL || "http://tenant_memory:8025"

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
    const url = `${TENANT_MEMORY_SERVICE_URL}/${apiPath}${searchParams ? `?${searchParams}` : ""}`

    const headers: Record<string, string> = {}
    for (const header of ["authorization", "x-tenant-id", "x-user-id", "x-roles", "x-permissions"]) {
      const value = req.headers.get(header)
      if (value) headers[header] = value
    }

    // Fail closed: proxy.ts always injects the verified identity (and strips any client-supplied x-roles /
    // x-permissions, re-injecting x-roles from the verified user). Roles are forwarded as verified so the
    // knowledge layer can apply its role-aware card filtering and admin checks; none are ever invented here.
    if (!headers["x-tenant-id"] || !headers["x-user-id"]) {
      return NextResponse.json({ error: "unauthorized" }, { status: 401 })
    }

    const init: RequestInit = { method, headers, cache: "no-store", signal: AbortSignal.timeout(30_000) }
    if (method !== "GET" && method !== "HEAD") {
      init.body = await req.text()
      headers["Content-Type"] = req.headers.get("content-type") || "application/json"
    }

    const res = await signedFetch(url, init)
    const contentType = res.headers.get("content-type") || ""
    const body = contentType.includes("application/json") ? await res.json() : await res.text()

    return contentType.includes("application/json")
      ? NextResponse.json(body, { status: res.status })
      : new NextResponse(body, { status: res.status })
  } catch (err) {
    console.error("Tenant memory service proxy error:", err)
    return NextResponse.json({ error: "Tenant memory service unavailable" }, { status: 503 })
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

