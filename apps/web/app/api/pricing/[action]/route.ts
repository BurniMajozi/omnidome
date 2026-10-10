import { NextRequest, NextResponse } from "next/server"
const upstream = process.env.ADMIN_SERVICE_URL || "http://admin:8013"
async function handle(request: NextRequest, context: { params: Promise<{ action: string }> }) {
  const { action } = await context.params
  if (!((action === "catalog" && request.method === "GET") || (action === "quote" && request.method === "POST"))) return new NextResponse(null, { status: 404 })
  try {
    const body = request.method === "POST" ? await request.text() : undefined
    if (body && body.length > 10_000) return new NextResponse(null, { status: 413 })
    const result = await fetch(`${upstream}/pricing/${action}`, { method: request.method, body, headers: { "Content-Type": "application/json" }, cache: "no-store", signal: AbortSignal.timeout(10_000) })
    return new NextResponse(await result.text(), { status: result.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } })
  } catch { return NextResponse.json({ detail: "Pricing service unavailable" }, { status: 503 }) }
}
export const GET = handle
export const POST = handle
