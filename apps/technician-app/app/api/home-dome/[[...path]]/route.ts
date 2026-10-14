import { NextRequest, NextResponse } from "next/server";
// Only bearer tokens cross this app boundary; platform web resolves verified identity.
const platform = (process.env.PLATFORM_WEB_URL || "http://127.0.0.1:3000").replace(/\/$/, "");
async function proxy(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await params;
  if (path.some(part => part === "." || part === ".." || /[\\/\x00-\x1f]/.test(part))) return NextResponse.json({ detail: "Invalid path" }, { status: 400 });
  const bearer = request.headers.get("authorization");
  if (!bearer?.startsWith("Bearer ")) return NextResponse.json({ detail: "Sign in to HomeDome" }, { status: 401 });
  const target = new URL(platform + "/api/home-dome" + (path.length ? "/" + path.map(encodeURIComponent).join("/") : ""));
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.set(key, value));
  try {
    const upstream = await fetch(target, { method: request.method, cache: "no-store", signal: AbortSignal.timeout(60000),
      headers: { authorization: bearer, "content-type": request.headers.get("content-type") || "application/json" },
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.text() });
    return new NextResponse(upstream.status === 204 ? null : await upstream.arrayBuffer(), { status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff" } });
  } catch {
    return NextResponse.json({ detail: "HomeDome service is unavailable" }, { status: 502 });
  }
}
export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
