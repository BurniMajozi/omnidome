import { signedFetch } from "@/lib/internal-identity"
import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

async function forward(request: NextRequest, method: "GET" | "POST" | "PATCH") {
  try {
  const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/approvals`)
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value))

  const { headers, identity } = await identityHeaders(request)
  if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })

  const init: RequestInit = { method, headers, cache: "no-store" }
  if (method !== "GET") {
    const body = await request.json().catch(() => null)
    if (!body) return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 })
    if (method === "PATCH") {
      if (typeof body.id !== "string" || !["approved", "rejected", "cancelled"].includes(body.status)) {
        return NextResponse.json({ detail: "A request id and approved, rejected or cancelled status are required" }, { status: 422 })
      }
      url.pathname += `/${encodeURIComponent(body.id)}/decide`
      init.method = "POST"
      init.body = JSON.stringify({ status: body.status })
    } else init.body = JSON.stringify(body)
  }

  const response = await signedFetch(url.toString(), init)
  const payload = await response.json().catch(() => null)
  if (!response.ok) return NextResponse.json({ error: "upstream_error", detail: payload?.detail }, { status: response.status })
  const data = Array.isArray(payload?.items) ? payload.items : Array.isArray(payload) ? payload : [payload]
  return NextResponse.json({ data }, { status: response.status })
  } catch {
    return NextResponse.json({ error: "service_unreachable" }, { status: 503 })
  }
}

export function GET(request: NextRequest) {
  return forward(request, "GET")
}

export function POST(request: NextRequest) {
  return forward(request, "POST")
}

export function PATCH(request: NextRequest) {
  return forward(request, "PATCH")
}
