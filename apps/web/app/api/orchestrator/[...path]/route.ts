/**
 * Proxy route: Next.js → Agent Orchestrator (port 8021)
 * Forwards all /api/orchestrator/* requests to the orchestrator service.
 */
import { NextRequest, NextResponse } from "next/server"

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL || "http://localhost:8021"

async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const pathStr = path.join("/")
  const url = new URL(`${ORCHESTRATOR_URL}/api/${pathStr}`)

  // Forward query params
  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.set(key, value)
  })

  // Forward headers (auth context)
  const headers = new Headers()
  const forwardHeaders = ["authorization", "x-tenant-id", "x-user-id", "content-type"]
  forwardHeaders.forEach((h) => {
    const val = request.headers.get(h)
    if (val) headers.set(h, val)
  })

  try {
    const body = request.method !== "GET" ? await request.text() : undefined
    const res = await fetch(url.toString(), {
      method: request.method,
      headers,
      body,
    })

    const contentType = res.headers.get("content-type") || ""

    if (contentType.includes("text/event-stream")) {
      // Streaming response — pass through
      return new NextResponse(res.body, {
        status: res.status,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          "Connection": "keep-alive",
        },
      })
    }

    const data = await res.text()
    return new NextResponse(data, {
      status: res.status,
      headers: { "Content-Type": contentType || "application/json" },
    })
  } catch (err) {
    return NextResponse.json(
      { error: "Orchestrator service unreachable", details: String(err) },
      { status: 502 }
    )
  }
}

export async function GET(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}
export async function POST(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}
export async function PATCH(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}
export async function DELETE(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}
