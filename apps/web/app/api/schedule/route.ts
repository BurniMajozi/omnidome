import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

async function forward(request: NextRequest, method: "GET" | "POST" | "PUT" | "DELETE") {
  const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/schedule`)
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value))

  const { headers, identity } = await identityHeaders(request)
  if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })

  const init: RequestInit = { method, headers, cache: "no-store" }
  if (method !== "GET" && method !== "DELETE") {
    init.body = await request.text()
  }

  const response = await fetch(url.toString(), init)
  const payload = await response.json().catch(() => null)
  const data = payload?.items ?? payload
  return NextResponse.json({ data }, { status: response.status })
}

export function GET(request: NextRequest) {
  return forward(request, "GET")
}

export function POST(request: NextRequest) {
  return forward(request, "POST")
}

export function PUT(request: NextRequest) {
  return forward(request, "PUT")
}

export function DELETE(request: NextRequest) {
  return forward(request, "DELETE")
}

// Update a schedule event (e.g. status from a kanban drag). Body: { id, ...fields }.
// The backend update is PUT /api/v1/schedule/{id}, so route the id into the path.
export async function PATCH(request: NextRequest) {
  const { headers, identity } = await identityHeaders(request)
  if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })

  const body = await request.json().catch(() => null)
  const { id, ...fields } = body ?? {}
  if (!id) return NextResponse.json({ error: "id required" }, { status: 400 })

  const response = await fetch(`${COMMUNICATION_SERVICE_URL}/api/v1/schedule/${id}`, {
    method: "PUT",
    headers,
    body: JSON.stringify(fields),
    cache: "no-store",
  })
  const payload = await response.json().catch(() => null)
  const data = payload?.items ?? payload
  return NextResponse.json({ data }, { status: response.status })
}
