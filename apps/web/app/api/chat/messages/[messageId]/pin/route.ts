import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ messageId: string }> }) {
  const { messageId } = await params
  const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/messages/${messageId}/pin`)
  const { headers, identity } = await identityHeaders(request)
  if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })
  const response = await fetch(url.toString(), {
    method: "PATCH",
    headers,
    body: await request.text(),
    cache: "no-store",
  })
  const payload = await response.json()
  return NextResponse.json(payload, { status: response.status })
}
