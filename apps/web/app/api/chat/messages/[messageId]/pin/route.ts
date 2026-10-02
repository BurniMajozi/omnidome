import { signedFetch } from "@/lib/internal-identity"
import { NextRequest, NextResponse } from "next/server"
import { identityHeaders } from "@/lib/api-auth"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ messageId: string }> }) {
  try {
  const { messageId } = await params
  const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/messages/${encodeURIComponent(messageId)}/pin`)
  const { headers, identity } = await identityHeaders(request)
  if (!identity) return NextResponse.json({ data: [], error: "unauthenticated" }, { status: 401 })
  const response = await signedFetch(url.toString(), {
    method: "PATCH",
    headers,
    body: await request.text(),
    cache: "no-store",
  })
  const payload = await response.json().catch(() => null)
  return NextResponse.json(payload, { status: response.status })
  } catch {
    return NextResponse.json({ error: "service_unreachable" }, { status: 503 })
  }
}
