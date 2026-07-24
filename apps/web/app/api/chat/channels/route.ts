import { NextRequest, NextResponse } from "next/server"

const COMMUNICATION_SERVICE_URL = process.env.COMMUNICATION_SERVICE_URL || "http://communication:8020"

async function proxy(request: NextRequest) {
  try {
    const url = new URL(`${COMMUNICATION_SERVICE_URL}/api/v1/channels`)
    request.nextUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value))

    const headers = new Headers()
    for (const header of ["authorization", "x-tenant-id", "x-user-id", "x-roles", "x-permissions", "content-type"]) {
      const value = request.headers.get(header)
      if (value) headers.set(header, value)
    }

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
