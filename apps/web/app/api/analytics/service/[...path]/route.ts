import { joinSafePath, badPathResponse } from "@/lib/safe-path"
import { NextRequest, NextResponse } from "next/server"

const ANALYTICS_SERVICE_URL =
  process.env.WEB_ANALYTICS_SERVICE_URL || "http://web_analytics:8016"

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params
    const apiPath = joinSafePath(path)
    if (apiPath === null) return badPathResponse()
    const searchParams = req.nextUrl.searchParams.toString()
    const url = `${ANALYTICS_SERVICE_URL}/analytics/${apiPath}${searchParams ? `?${searchParams}` : ""}`

    const res = await fetch(url, { cache: "no-store" })
    const data = await res.json()
    return NextResponse.json(data)
  } catch (err) {
    console.error("Analytics service proxy error:", err)
    return NextResponse.json({ error: "Analytics service unavailable" }, { status: 503 })
  }
}
