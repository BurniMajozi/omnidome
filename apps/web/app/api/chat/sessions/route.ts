import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

async function proxyGet(request: NextRequest) {
  const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/sessions`)
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value))

  const { headers, identity } = await identityHeaders(request)
  if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })

  const response = await fetch(url.toString(), {
    method: "GET",
    headers,
    cache: "no-store",
  })
  const payload = await response.json()
  const data = Array.isArray(payload?.items) ? payload.items : Array.isArray(payload) ? payload : []
  return NextResponse.json({ data }, { status: response.status })
}

async function proxyPost(request: NextRequest) {
  const body = await request.json().catch(() => null)
  const channelId = body?.channel_id
  const sessionType = body?.session_type
  if (!channelId) {
    return NextResponse.json({ error: "channel_id is required" }, { status: 400 })
  }
  if (!sessionType) {
    return NextResponse.json({ error: "session_type is required" }, { status: 400 })
  }

  const { headers, identity } = await identityHeaders(request)
  if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })

  const response = await fetch(`${COMMUNICATION_SERVICE_URL}/api/v1/sessions`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      channel_id: channelId,
      session_type: sessionType,
      participants: body?.participants ?? [],
      metadata: body?.metadata ?? {},
      provider_name: body?.provider_name ?? null,
    }),
  })
  const payload = await response.json()
  return NextResponse.json({ data: [payload] }, { status: response.status })
}

export function GET(request: NextRequest) {
  return proxyGet(request)
}

export function POST(request: NextRequest) {
  return proxyPost(request)
}
