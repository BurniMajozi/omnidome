import { signedFetch } from "@/lib/internal-identity"
import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

async function proxyGet(request: NextRequest) {
  try {
    const channelId = request.nextUrl.searchParams.get("channel_id")
    if (!channelId) {
      return NextResponse.json({ error: "channel_id is required" }, { status: 400 })
    }

    const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/channels/${encodeURIComponent(channelId)}/messages`)
    request.nextUrl.searchParams.forEach((value, key) => {
      if (key !== "channel_id") url.searchParams.set(key, value)
    })

    const { headers, identity } = await identityHeaders(request)
    if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })

    const response = await signedFetch(url.toString(), {
      method: "GET",
      headers,
      cache: "no-store",
    })
    if (!response.ok) {
      // Surface the real status so the UI can show "Service not running" instead of an empty list.
      const payload = await response.json().catch(() => null)
      return NextResponse.json({ data: [], error: "upstream_error", detail: payload?.detail }, { status: response.status })
    }
    const payload = await response.json()
    const data = Array.isArray(payload?.items) ? payload.items : Array.isArray(payload) ? payload : []
    return NextResponse.json({ data, next_before: payload?.next_before ?? null, has_more: payload?.has_more === true }, { status: 200 })
  } catch (error) {
    console.error("Error fetching messages from communication service:", error)
    return NextResponse.json({ data: [], error: "service_unreachable" }, { status: 503 })
  }
}

async function proxyPost(request: NextRequest) {
  try {
    const body = await request.json().catch(() => null)
    const channelId = body?.channel_id
    if (!channelId) {
      return NextResponse.json({ error: "channel_id is required" }, { status: 400 })
    }

    const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/channels/${encodeURIComponent(channelId)}/messages`)
    const { headers, identity } = await identityHeaders(request)
    if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })

    const response = await signedFetch(url.toString(), {
      method: "POST",
      headers,
      body: JSON.stringify({
        content: body?.content ?? "",
        thread_parent_id: body?.thread_parent_id ?? null,
        client_msg_id: body?.client_msg_id ?? null,
      }),
    })

    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      return NextResponse.json({ data: [], error: "upstream_error", detail: payload?.detail }, { status: response.status })
    }

    const payload = await response.json()
    // The current MessageRead schema omits the stored key; preserve it for this caller's reconciliation.
    return NextResponse.json({ data: [{ ...payload, client_msg_id: body?.client_msg_id ?? payload?.client_msg_id }] }, { status: response.status })
  } catch (error) {
    console.error("Error posting message to communication service:", error)
    return NextResponse.json({ data: [], error: "service_unreachable" }, { status: 503 })
  }
}

export function GET(request: NextRequest) {
  return proxyGet(request)
}

export function POST(request: NextRequest) {
  return proxyPost(request)
}
