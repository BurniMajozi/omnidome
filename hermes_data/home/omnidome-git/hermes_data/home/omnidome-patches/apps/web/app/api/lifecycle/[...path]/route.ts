import { NextRequest, NextResponse } from "next/server"

const LIFECYCLE_SERVICE_URL =
  process.env.LIFECYCLE_SERVICE_URL || "http://lifecycle:8018"

async function proxy(req: NextRequest, path: string, method: string) {
  try {
    const url = `${LIFECYCLE_SERVICE_URL}/${path}`
    const headers: Record<string, string> = {}
    const authHeader = req.headers.get("authorization")
    if (authHeader) headers["Authorization"] = authHeader

    const init: RequestInit = { method, headers }
    if (method !== "GET" && method !== "HEAD") {
      init.body = await req.text()
      headers["Content-Type"] = "application/json"
    }

    const res = await fetch(url, init)
    const data = await res.json()
    return NextResponse.json(data)
  } catch (err) {
    console.error("Lifecycle proxy error:", err)
    return NextResponse.json({ error: "Lifecycle service unavailable" }, { status: 503 })
  }
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE }
