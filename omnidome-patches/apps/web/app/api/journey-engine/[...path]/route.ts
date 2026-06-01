import { NextRequest, NextResponse } from "next/server"

const JOURNEY_ENGINE_URL =
  process.env.JOURNEY_ENGINE_SERVICE_URL || "http://journey_engine:8017"

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params
    const apiPath = path.join("/")
    const searchParams = req.nextUrl.searchParams.toString()
    const url = `${JOURNEY_ENGINE_URL}/${apiPath}${searchParams ? `?${searchParams}` : ""}`

    const res = await fetch(url, { cache: "no-store" })
    const data = await res.json()
    return NextResponse.json(data)
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
    const apiPath = path.join("/")
    const body = await req.text()

    const res = await fetch(`${JOURNEY_ENGINE_URL}/${apiPath}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    })
    const data = await res.json()
    return NextResponse.json(data)
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
    const apiPath = path.join("/")
    const body = await req.text()

    const res = await fetch(`${JOURNEY_ENGINE_URL}/${apiPath}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body,
    })
    const data = await res.json()
    return NextResponse.json(data)
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
    const apiPath = path.join("/")

    const res = await fetch(`${JOURNEY_ENGINE_URL}/${apiPath}`, {
      method: "DELETE",
    })
    const data = await res.json()
    return NextResponse.json(data)
  } catch (err) {
    console.error("Journey engine proxy error:", err)
    return NextResponse.json({ error: "Journey engine unavailable" }, { status: 503 })
  }
}
