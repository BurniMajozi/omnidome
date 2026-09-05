import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

async function forward(request: NextRequest, channelId: string) {
  const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/channels/${channelId}/preferences`)
  const { headers, identity } = await identityHeaders(request)
  if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })
  const response = await fetch(url.toString(), {
    method: request.method,
    headers,
    body: request.method === "PATCH" ? await request.text() : undefined,
    cache: "no-store",
  })
  const payload = await response.json()
  return NextResponse.json(payload, { status: response.status })
}

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ channelId: string }> }) {
  const { channelId } = await params
  return forward(request, channelId)
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ channelId: string }> }) {
  const { channelId } = await params
  return forward(request, channelId)
}
