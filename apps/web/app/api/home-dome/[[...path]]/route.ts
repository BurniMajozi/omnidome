import { NextRequest, NextResponse } from "next/server";
import { identityHeaders } from "@/lib/api-auth";
import { signedFetch } from "@/lib/internal-identity";
import { joinSafePath, badPathResponse } from "@/lib/safe-path";

const base = (process.env.IOT_SERVICE_URL || "http://iot:8006").replace(/\/$/, "");
async function proxy(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await params;
  const suffix = path.length ? joinSafePath(path) : "";
  if (suffix === null) return badPathResponse();
  const { identity, headers } = await identityHeaders(request);
  if (!identity) return NextResponse.json({ detail: "Sign in to HomeDome" }, { status: 401 });
  // These headers are resolved by api-auth / proxy.ts; browser identity is stripped at the edge.
  headers.set("x-roles", identity.roles?.join(",") || request.headers.get("x-roles") || "");
  const target = new URL(base + "/api/iot/homes" + (suffix ? "/" + suffix : ""));
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.set(key, value));
  try {
    const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.text();
    const upstream = await signedFetch(target.toString(), { method: request.method, headers, body, cache: "no-store", signal: AbortSignal.timeout(60000) });
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
