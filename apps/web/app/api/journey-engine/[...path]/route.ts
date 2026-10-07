import { joinSafePath, badPathResponse } from "@/lib/safe-path"
import { NextRequest, NextResponse } from "next/server"
import { signedFetch } from "@/lib/internal-identity"

const JOURNEY_ENGINE_URL =
  process.env.JOURNEY_ENGINE_SERVICE_URL || "http://journey_engine:8017"

function outboundHeaders(req: NextRequest) {
  const headers = new Headers({"Content-Type": "application/json"})
  for (const name of ["authorization", "x-tenant-id", "x-user-id", "x-roles", "x-permissions"]) {
    const value = req.headers.get(name)
    if (value) headers.set(name, value)
  }
  return headers
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params
    const apiPath = joinSafePath(path)
    if (apiPath === null) return badPathResponse()
    const tenant = req.headers.get("x-tenant-id")
    if (!tenant || !req.headers.get("x-user-id")) return NextResponse.json({error: "Unauthorized"}, {status: 401})
    if (apiPath === "context") return NextResponse.json({tenant_id: tenant})
    const query = new URLSearchParams(req.nextUrl.searchParams)
    query.set("tenant_id", tenant)
    const searchParams = query.toString()
    const url = `${JOURNEY_ENGINE_URL}/${apiPath}${searchParams ? `?${searchParams}` : ""}`

    const res = await signedFetch(url, { headers: outboundHeaders(req), cache: "no-store", signal: AbortSignal.timeout(20000) })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err) {
    console.error("Journey engine proxy error:", err)
    return NextResponse.json({ error: "Journey engine unavailable" }, { status: 503 })
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params
    const apiPath = joinSafePath(path)
    if (apiPath === null) return badPathResponse()
    const tenant = req.headers.get("x-tenant-id")
    if (!tenant || !req.headers.get("x-user-id")) return NextResponse.json({error: "Unauthorized"}, {status: 401})
    const payload = await req.json()
    if (payload && typeof payload === "object" && !Array.isArray(payload)) {
      if ("tenant_id" in payload) payload.tenant_id = tenant
      if (payload.customer_snapshot) payload.customer_snapshot.tenant_id = tenant
    }
    const body = JSON.stringify(payload)

    const res = await signedFetch(`${JOURNEY_ENGINE_URL}/${apiPath}`, {
      method: "POST",
      headers: outboundHeaders(req),
      signal: AbortSignal.timeout(20000),
      body,
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err) {
    console.error("Journey engine proxy error:", err)
    return NextResponse.json({ error: "Journey engine unavailable" }, { status: 503 })
  }
}

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params
    const apiPath = joinSafePath(path)
    if (apiPath === null) return badPathResponse()
    const body = await req.text()
    if (!req.headers.get("x-tenant-id") || !req.headers.get("x-user-id")) return NextResponse.json({error: "Unauthorized"}, {status: 401})
    const res = await signedFetch(`${JOURNEY_ENGINE_URL}/${apiPath}`, {
      method: "PUT",
      headers: outboundHeaders(req),
      signal: AbortSignal.timeout(20000),
      body,
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err) {
    console.error("Journey engine proxy error:", err)
    return NextResponse.json({ error: "Journey engine unavailable" }, { status: 503 })
  }
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params
    const apiPath = joinSafePath(path)
    if (apiPath === null) return badPathResponse()

    if (!req.headers.get("x-tenant-id") || !req.headers.get("x-user-id")) return NextResponse.json({error: "Unauthorized"}, {status: 401})
    const res = await signedFetch(`${JOURNEY_ENGINE_URL}/${apiPath}`, {
      method: "DELETE",
      headers: outboundHeaders(req), signal: AbortSignal.timeout(20000),
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err) {
    console.error("Journey engine proxy error:", err)
    return NextResponse.json({ error: "Journey engine unavailable" }, { status: 503 })
  }
}
