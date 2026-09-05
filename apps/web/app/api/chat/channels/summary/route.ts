import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

// Per-channel message counts for unread badges. The client compares these
// against a locally-stored last-seen count to compute unread.
export async function GET(request: NextRequest) {
  try {
    const { headers, identity } = await identityHeaders(request)
    if (!identity) return NextResponse.json({ data: [] }, { status: 401 })

    const response = await fetch(`${COMMUNICATION_SERVICE_URL}/api/v1/channels/summary`, {
      method: "GET",
      headers,
      cache: "no-store",
    })
    if (!response.ok) return NextResponse.json({ data: [] }, { status: 200 })
    const payload = await response.json()
    const data = Array.isArray(payload?.items) ? payload.items : []
    return NextResponse.json({ data }, { status: 200 })
  } catch (error) {
    console.error("Error fetching channel summary:", error)
    return NextResponse.json({ data: [] }, { status: 200 })
  }
}
