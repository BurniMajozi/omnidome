import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

async function forward(request: NextRequest, method: "GET" | "POST") {
  const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/tasks`)
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value))

  // Resolve identity server-side from the verified Supabase bearer and inject
  // x-user-id / x-tenant-id (the backend authorizes on those). 401 if absent.
  const { headers, identity } = await identityHeaders(request)
  if (!identity) {
    return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })
  }

  const init: RequestInit = { method, headers, cache: "no-store" }
  if (method !== "GET") {
    init.body = await request.text()
  }

  const response = await fetch(url.toString(), init)
  const payload = await response.json().catch(() => null)
  const data = payload?.items ?? (payload ? [payload] : [])
  return NextResponse.json({ data }, { status: response.status })
}

export function GET(request: NextRequest) {
  return forward(request, "GET")
}

export function POST(request: NextRequest) {
  return forward(request, "POST")
}

// Update a task's status. Body: { id, status }. The backend exposes this at
// PATCH /api/v1/tasks/{id}/status, so route the id from the body into the path.
export async function PATCH(request: NextRequest) {
  const { headers, identity } = await identityHeaders(request)
  if (!identity) {
    return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })
  }
  const body = await request.json().catch(() => null)
  const id = body?.id
  if (!id) return NextResponse.json({ error: "id required" }, { status: 400 })

  const response = await fetch(`${COMMUNICATION_SERVICE_URL}/api/v1/tasks/${id}/status`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({ status: body.status }),
    cache: "no-store",
  })
  const payload = await response.json().catch(() => null)
  const data = payload?.items ?? (payload ? [payload] : [])
  return NextResponse.json({ data }, { status: response.status })
}
