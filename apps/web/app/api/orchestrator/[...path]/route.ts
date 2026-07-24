/**
 * Proxy route: Next.js → Agent Orchestrator (port 8021)
 * Forwards all /api/orchestrator/* requests to the orchestrator service.
 */
import { NextRequest, NextResponse } from "next/server"
import { getSupabaseServer } from "@/lib/supabase/server"

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL || "http://agent-orchestrator:8021"
const ADMIN_SERVICE_URL = process.env.ADMIN_SERVICE_URL || "http://admin:8013"
const INTERNAL_SERVICE_KEY = process.env.INTERNAL_SERVICE_KEY || ""

// Resolves a verified Supabase session into this platform's {user_id, tenant_id}.
// Returns null on any failure -- callers must drop identity headers entirely
// rather than fall back to anything client-supplied (no tenant-spoofing via headers).
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
  const url = new URL(`${ORCHESTRATOR_URL}/api/${pathStr}`)

  // Forward query params
  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.set(key, value)
  })

  // Forward headers (auth context)
  const headers = new Headers()
  const forwardHeaders = ["authorization", "content-type"]
  forwardHeaders.forEach((h) => {
    const val = request.headers.get(h)
    if (val) headers.set(h, val)
  })

  // Identity is always resolved server-side from a verified Supabase token --
  // never trust a client-sent x-user-id/x-tenant-id directly (tenant-spoofing).
  const authHeader = request.headers.get("authorization")
  if (authHeader?.startsWith("Bearer ")) {
    const identity = await resolveIdentity(authHeader.slice(7))
    if (identity) {
      headers.set("x-user-id", identity.userId)
      headers.set("x-tenant-id", identity.tenantId)
    }
  }

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
