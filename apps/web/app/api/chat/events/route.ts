import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

async function proxyPost(request: NextRequest) {
  const body = await request.json().catch(() => null)
  const channelId = body?.channel_id
  const eventType = body?.event_type
  if (!channelId) {
    return NextResponse.json({ error: "channel_id is required" }, { status: 400 })
  }
  if (!eventType) {
    return NextResponse.json({ error: "event_type is required" }, { status: 400 })
  }

  const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/events`)
  const { headers, identity } = await identityHeaders(request)
  if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })

  const response = await fetch(url.toString(), {
    method: "POST",
    headers,
    body: JSON.stringify({
      channel_id: channelId,
      event_type: eventType,
      payload: body?.payload ?? {},
    }),
  })

  const payload = await response.json()
  return NextResponse.json({ data: [payload] }, { status: response.status })
}

export function POST(request: NextRequest) {
  return proxyPost(request)
}
