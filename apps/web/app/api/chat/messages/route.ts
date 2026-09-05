import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

async function proxyGet(request: NextRequest) {
  try {
    const channelId = request.nextUrl.searchParams.get("channel_id")
    if (!channelId) {
      return NextResponse.json({ error: "channel_id is required" }, { status: 400 })
    }

    const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/channels/${channelId}/messages`)
    request.nextUrl.searchParams.forEach((value, key) => {
      if (key !== "channel_id") url.searchParams.set(key, value)
    })

    const { headers, identity } = await identityHeaders(request)
    if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })

    const response = await fetch(url.toString(), {
      method: "GET",
      headers,
      cache: "no-store",
    })
    if (!response.ok) {
      return NextResponse.json({ data: [] }, { status: 200 })
    }
    const payload = await response.json()
    const data = Array.isArray(payload?.items) ? payload.items : Array.isArray(payload) ? payload : []
    return NextResponse.json({ data }, { status: 200 })
  } catch (error) {
    console.error("Error fetching messages from communication service:", error)
    return NextResponse.json({ data: [] }, { status: 200 })
  }
}

async function proxyPost(request: NextRequest) {
  try {
    const body = await request.json().catch(() => null)
    const channelId = body?.channel_id
    if (!channelId) {
      return NextResponse.json({ error: "channel_id is required" }, { status: 400 })
    }

    const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/channels/${channelId}/messages`)
    const { headers, identity } = await identityHeaders(request)
    if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })

    const response = await fetch(url.toString(), {
      method: "POST",
      headers,
      body: JSON.stringify({
        content: body?.content ?? "",
        thread_parent_id: body?.thread_parent_id ?? null,
      }),
    })

    if (!response.ok) {
      return NextResponse.json({ data: [] }, { status: 200 })
    }

    const payload = await response.json()
    return NextResponse.json({ data: [payload] }, { status: 200 })
  } catch (error) {
    console.error("Error posting message to communication service:", error)
    return NextResponse.json({ data: [] }, { status: 200 })
  }
}

export function GET(request: NextRequest) {
  return proxyGet(request)
}

export function POST(request: NextRequest) {
  return proxyPost(request)
}
