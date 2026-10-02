import { joinSafePath, badPathResponse } from "@/lib/safe-path"
import { signedFetch } from "@/lib/internal-identity"
import { NextRequest, NextResponse } from "next/server"
import { verifiedRoleHeaders } from "@/lib/proxy-roles"

const BILLING_SERVICE_URL = process.env.BILLING_SERVICE_URL || "http://billing:8003"
const DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
const ALLOW_DEV_HEADERS = process.env.NODE_ENV !== "production" && process.env.BILLING_PROXY_ALLOW_DEV_HEADERS === "true"

async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const pathStr = joinSafePath(path)
  if (pathStr === null) return badPathResponse()
  const url = new URL(`${BILLING_SERVICE_URL}/${pathStr}`)

  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.set(key, value)
  })

  // Public, signature-authenticated callback. Forward exact bytes to the verified
  // backend path; never inject tenant identity into a Paystack event.
  if (pathStr === "payments/paystack/webhook") {
    if (request.method !== "POST") return NextResponse.json({ error: "Method not allowed" }, { status: 405 })
    const signature = request.headers.get("x-paystack-signature")
    if (!signature) return NextResponse.json({ error: "Missing Paystack signature" }, { status: 401 })
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "content-type": request.headers.get("content-type") || "application/json", "x-paystack-signature": signature },
        body: await request.arrayBuffer(),
        redirect: "manual",
        signal: AbortSignal.timeout(15_000),
      })
      return new NextResponse([204, 205, 304].includes(res.status) ? null : await res.text(), {
        status: res.status, headers: { "Content-Type": res.headers.get("content-type") || "application/json" },
      })
    } catch {
      return NextResponse.json({ error: "Billing service unreachable" }, { status: 502 })
    }
  }

  const headers = new Headers()
  for (const header of ["authorization", "x-tenant-id", "x-user-id", "x-roles", "x-permissions", "content-type", "idempotency-key"]) {
    const value = request.headers.get(header)
    if (value) headers.set(header, value)
  }

  // Fail closed: proxy.ts always injects verified identity; a request without it is unauthenticated.
  if (!headers.has("x-tenant-id") || !headers.has("x-user-id")) {
    if (!ALLOW_DEV_HEADERS) return NextResponse.json({ error: "unauthorized" }, { status: 401 })
    if (!headers.has("x-tenant-id")) headers.set("x-tenant-id", DEV_TENANT_ID)
    if (!headers.has("x-user-id")) headers.set("x-user-id", DEV_USER_ID)
  }
  // Least privilege: only the proxy.ts-verified roles; minimal role otherwise (never org_admin).
  const rp = verifiedRoleHeaders(request.headers, ["billing.read", "billing.write", "billing.admin"])
  headers.set("x-roles", rp.roles)
  if (rp.permissions) headers.set("x-permissions", rp.permissions)
  else headers.delete("x-permissions")

  try {
    const body = request.method !== "GET" && request.method !== "HEAD" ? await request.text() : undefined
    const res = await signedFetch(url.toString(), {
      method: request.method,
      headers,
      body,
    })
    const contentType = res.headers.get("content-type") || "application/json"
    const data = await res.text()
    // 204/205/304 must not carry a body: passing "" makes NextResponse throw,
    // which the catch below turned into a 502 for every successful DELETE.
    const noBody = res.status === 204 || res.status === 205 || res.status === 304
    return new NextResponse(noBody ? null : data, {
      status: res.status,
      headers: { "Content-Type": contentType },
    })
  } catch (err) {
    return NextResponse.json({ error: "Billing service unreachable", details: String(err) }, { status: 502 })
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
