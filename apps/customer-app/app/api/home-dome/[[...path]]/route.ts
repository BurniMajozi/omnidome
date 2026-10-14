import { NextRequest, NextResponse } from "next/server";
// The platform web verifies Supabase identity and signs service requests. The
// customer app never holds the internal signing secret or forwards user/tenant headers.
const platform = (process.env.PLATFORM_WEB_URL || "http://127.0.0.1:3000").replace(/\/$/, "");
async function proxy(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await params;
  if (path.some(part => part === "." || part === ".." || /[\\/\x00-\x1f]/.test(part))) return NextResponse.json({ detail: "Invalid path" }, { status: 400 });
  const bearer = request.headers.get("authorization");
  if (!bearer?.startsWith("Bearer ")) return NextResponse.json({ detail: "Sign in to HomeDome" }, { status: 401 });
  // This surface stays a customer app even when a platform administrator signs in.
  if (path[0] === "reporting") return NextResponse.json({ detail: "Manage reporting requests in the tenant platform" }, { status: 403 });
  const target = new URL(platform + "/api/home-dome" + (path.length ? "/" + path.map(encodeURIComponent).join("/") : ""));
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.set(key, value));
  try {
    const upstream = await fetch(target, { method: request.method, cache: "no-store", signal: AbortSignal.timeout(60000),
      headers: { authorization: bearer, "content-type": request.headers.get("content-type") || "application/json" },
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.text() });
    if (upstream.ok && request.method === "GET" && path.length === 1 && path[0] === "capabilities") {
      const capabilities = await upstream.json();
      return NextResponse.json({ ...capabilities, can_provision: false, can_request_support: false,
        can_assign_gateway: false, gateway_onboarding_url: null }, { headers: { "Cache-Control": "no-store, private" } });
    }
    return new NextResponse(upstream.status === 204 ? null : await upstream.arrayBuffer(), {
      status: upstream.status, headers: { "Content-Type": upstream.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff" },
    });
  } catch {
    return NextResponse.json({ detail: "HomeDome service is unavailable" }, { status: 502 });
  }
}
export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
