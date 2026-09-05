import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

async function proxy(request: NextRequest) {
  try {
    const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/channels`)
    request.nextUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value))

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
    console.error("Error fetching channels from communication service:", error)
    return NextResponse.json({ data: [] }, { status: 200 })
  }
}

export function GET(request: NextRequest) {
  return proxy(request)
}

// Create a channel (public or private). Proxies to the communication service.
export async function POST(request: NextRequest) {
  try {
    const { headers, identity } = await identityHeaders(request)
    if (!identity) return NextResponse.json({ error: "unauthenticated" }, { status: 401 })

    const response = await fetch(`${COMMUNICATION_SERVICE_URL}/api/v1/channels`, {
      method: "POST",
      headers,
      body: await request.text(),
      cache: "no-store",
    })
    const payload = await response.json().catch(() => null)
    return NextResponse.json(payload ?? {}, { status: response.status })
  } catch (error) {
    console.error("Error creating channel:", error)
    return NextResponse.json({ error: "failed to create channel" }, { status: 500 })
  }
}
