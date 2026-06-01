import { NextRequest, NextResponse } from "next/server"

const ANALYTICS_SERVICE_URL =
  process.env.WEB_ANALYTICS_SERVICE_URL || "http://web_analytics:8016"

const geoHeaders = [
  "cf-ipcountry", "x-vercel-ip-country", "x-vercel-ip-city",
  "x-vercel-ip-country-region", "x-vercel-ip-latitude", "x-vercel-ip-longitude",
  "x-geo-country", "x-geo-city", "x-geo-region", "x-geo-lat", "x-geo-lon",
]

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params
    const trackPath = path.join("/")
    const body = await req.text()

    const headers: Record<string, string> = { "Content-Type": "application/json" }
    for (const h of geoHeaders) {
      const val = req.headers.get(h)
      if (val) headers[h] = val
    }
    const ua = req.headers.get("user-agent")
    if (ua) headers["user-agent"] = ua

    const res = await fetch(`${ANALYTICS_SERVICE_URL}/track/${trackPath}`, {
      method: "POST",
      headers,
      body,
    })
    const data = await res.json()
    return NextResponse.json(data)
  } catch (err) {
    console.error("Analytics proxy error:", err)
    return NextResponse.json({ status: "ok" })
  }
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  })
}
