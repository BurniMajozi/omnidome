import { signedFetch } from "@/lib/internal-identity"
import { identityHeaders } from "@/lib/api-auth"
import { NextRequest, NextResponse } from "next/server"

const service = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ channelId: string; userId: string }> }) {
  try {
    const { headers, identity } = await identityHeaders(request)
    if (!identity) return NextResponse.json({ error: "unauthenticated" }, { status: 401 })
    const { channelId, userId } = await params
    const response = await signedFetch(`${service}/api/v1/channels/${encodeURIComponent(channelId)}/members/${encodeURIComponent(userId)}`, {
      method: "DELETE", headers, cache: "no-store",
    })
    if (response.status === 204) return new NextResponse(null, { status: 204 })
    return NextResponse.json(await response.json().catch(() => ({})), { status: response.status })
  } catch {
    return NextResponse.json({ error: "service_unreachable" }, { status: 503 })
  }
}
