import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

// Invite/add members to a channel, and list them.
async function forward(request: NextRequest, channelId: string, method: "GET" | "POST") {
  const { headers, identity } = await identityHeaders(request)
  if (!identity) return NextResponse.json({ error: "unauthenticated" }, { status: 401 })

  const init: RequestInit = { method, headers, cache: "no-store" }
  if (method !== "GET") init.body = await request.text()

  const response = await fetch(
    `${COMMUNICATION_SERVICE_URL}/api/v1/channels/${channelId}/members`,
    init,
  )
  const payload = await response.json().catch(() => null)
  return NextResponse.json(payload ?? {}, { status: response.status })
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ channelId: string }> }) {
  const { channelId } = await params
  return forward(request, channelId, "GET")
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ channelId: string }> }) {
  const { channelId } = await params
  return forward(request, channelId, "POST")
}
