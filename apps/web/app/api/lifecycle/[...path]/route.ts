import { NextRequest, NextResponse } from "next/server"

const LIFECYCLE_SERVICE_URL =
  process.env.LIFECYCLE_SERVICE_URL || "http://lifecycle:8018"

type Context = { params: Promise<{ path: string[] }> }

async function proxy(req: NextRequest, { params }: Context): Promise<NextResponse> {
  try {
    const { path } = await params
    const pathStr = path.join("/")
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

    const init: RequestInit = { method: req.method, headers }
    if (req.method !== "GET" && req.method !== "HEAD") {
      init.body = await req.text()
    }

    const res = await fetch(targetUrl.toString(), init)
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
