import { NextRequest, NextResponse } from "next/server"

const SALES_SERVICE_URL =
  process.env.SALES_SERVICE_URL || "http://sales:8002"

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params
    const apiPath = path.join("/")
    const searchParams = req.nextUrl.searchParams.toString()
    const url = `${SALES_SERVICE_URL}/${apiPath}${searchParams ? `?${searchParams}` : ""}`

    const res = await fetch(url, { cache: "no-store" })
    const data = await res.json()
    return NextResponse.json(data)
  } catch (err) {
    console.error("Sales service proxy error:", err)
    return NextResponse.json({ error: "Sales service unavailable" }, { status: 503 })
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params
    const apiPath = path.join("/")
    const searchParams = req.nextUrl.searchParams.toString()
    const body = await req.text()
    const url = `${SALES_SERVICE_URL}/${apiPath}${searchParams ? `?${searchParams}` : ""}`

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err) {
    console.error("Sales service proxy error:", err)
    return NextResponse.json({ error: "Sales service unavailable" }, { status: 503 })
  }
}

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params
    const apiPath = path.join("/")
    const body = await req.text()
    const url = `${SALES_SERVICE_URL}/${apiPath}`

    const res = await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body,
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err) {
    console.error("Sales service proxy error:", err)
    return NextResponse.json({ error: "Sales service unavailable" }, { status: 503 })
  }
}
