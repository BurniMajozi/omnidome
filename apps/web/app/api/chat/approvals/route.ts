import { NextRequest, NextResponse } from "next/server"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://localhost:8020"

async function forward(request: NextRequest, method: "GET" | "POST" | "PATCH") {
  const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/approvals`)
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value))

  const headers = new Headers()
  for (const header of ["authorization", "x-tenant-id", "x-user-id", "x-roles", "x-permissions", "content-type"]) {
    const value = request.headers.get(header)
    if (value) headers.set(header, value)
  }

  const init: RequestInit = { method, headers, cache: "no-store" }
  if (method !== "GET") {
    init.body = await request.text()
  }

  const response = await fetch(url.toString(), init)
  const payload = await response.json()
  const data = Array.isArray(payload?.items) ? payload.items : Array.isArray(payload) ? payload : [payload]
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
