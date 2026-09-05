import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

async function forward(request: NextRequest, method: "GET" | "POST" | "PATCH") {
  const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/escalations`)
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value))

  const { headers, identity } = await identityHeaders(request)
  if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })

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

export function PATCH(request: NextRequest) {
  return forward(request, "PATCH")
}
