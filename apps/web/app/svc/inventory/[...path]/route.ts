import { NextRequest, NextResponse } from "next/server"

const INVENTORY_SERVICE_URL = process.env.INVENTORY_SERVICE_URL || "http://inventory:8010"
const DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
const ALLOW_DEV_HEADERS =
  process.env.NODE_ENV !== "production" || process.env.INVENTORY_PROXY_ALLOW_DEV_HEADERS === "true"

async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const pathStr = path.join("/")
  const url = new URL(`${INVENTORY_SERVICE_URL}/${pathStr}`)

  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.set(key, value)
  })

  const headers = new Headers()
  for (const header of ["authorization", "x-tenant-id", "x-user-id", "x-roles", "x-permissions", "content-type"]) {
    const value = request.headers.get(header)
    if (value) headers.set(header, value)
  }

  if (ALLOW_DEV_HEADERS) {
    if (!headers.has("x-tenant-id")) headers.set("x-tenant-id", DEV_TENANT_ID)
    if (!headers.has("x-user-id")) headers.set("x-user-id", DEV_USER_ID)
    if (!headers.has("x-roles")) headers.set("x-roles", "org_admin,org_user")
    if (!headers.has("x-permissions")) headers.set("x-permissions", "inventory.read,inventory.write,inventory.admin")
  }

  try {
    const body = request.method !== "GET" && request.method !== "HEAD" ? await request.text() : undefined
    const res = await fetch(url.toString(), {
      method: request.method,
      headers,
      body,
    })
    const contentType = res.headers.get("content-type") || "application/json"
    const data = await res.text()
    return new NextResponse(data, {
      status: res.status,
      headers: { "Content-Type": contentType },
    })
  } catch (err) {
    return NextResponse.json({ error: "Inventory service unreachable", details: String(err) }, { status: 502 })
  }
}

export function GET(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}

export function POST(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}

export function PUT(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}

export function PATCH(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}

export function DELETE(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(request, ctx)
}
