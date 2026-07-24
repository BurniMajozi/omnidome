import { NextRequest, NextResponse } from "next/server"

const COMPLIANCE_SERVICE_URL =
  process.env.COMPLIANCE_SERVICE_URL || "http://compliance:8019"

async function proxy(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
  method: string
) {
  try {
    const { path } = await params
    const apiPath = path.join("/")
    const searchParams = req.nextUrl.searchParams.toString()
    const url = `${COMPLIANCE_SERVICE_URL}/${apiPath}${searchParams ? `?${searchParams}` : ""}`

    const headers: Record<string, string> = {}
    for (const header of ["authorization", "x-tenant-id", "x-user-id", "x-roles"]) {
      const value = req.headers.get(header)
      if (value) headers[header] = value
    }

    const init: RequestInit = { method, headers, cache: "no-store" }
    if (method !== "GET" && method !== "HEAD") {
      init.body = await req.text()
      headers["Content-Type"] = req.headers.get("content-type") || "application/json"
    }

    const res = await fetch(url, init)
    const contentType = res.headers.get("content-type") || ""
    const body = contentType.includes("application/json") ? await res.json() : await res.text()

    return contentType.includes("application/json")
      ? NextResponse.json(body, { status: res.status })
      : new NextResponse(body, { status: res.status })
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
