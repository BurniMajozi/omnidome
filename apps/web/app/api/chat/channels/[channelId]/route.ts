import { signedFetch } from "@/lib/internal-identity"
import { identityHeaders } from "@/lib/api-auth"
import { NextRequest, NextResponse } from "next/server"

const service = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

async function forward(request: NextRequest, params: Promise<{ channelId: string }>, method: "PUT" | "DELETE") {
  try {
    const { headers, identity } = await identityHeaders(request)
    if (!identity) return NextResponse.json({ error: "unauthenticated" }, { status: 401 })
    const { channelId } = await params
    const response = await signedFetch(`${service}/api/v1/channels/${encodeURIComponent(channelId)}`, {
      method, headers, cache: "no-store", ...(method === "PUT" ? { body: await request.text() } : {}),
    })
    if (response.status === 204) return new NextResponse(null, { status: 204 })
    return NextResponse.json(await response.json().catch(() => ({})), { status: response.status })
  } catch {
    return NextResponse.json({ error: "service_unreachable" }, { status: 503 })
  }
}

export function PUT(request: NextRequest, { params }: { params: Promise<{ channelId: string }> }) {
  return forward(request, params, "PUT")
}
export function DELETE(request: NextRequest, { params }: { params: Promise<{ channelId: string }> }) {
  return forward(request, params, "DELETE")
}
