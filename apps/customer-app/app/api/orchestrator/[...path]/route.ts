import { NextRequest, NextResponse } from "next/server";

const platform = (process.env.PLATFORM_WEB_URL || "http://127.0.0.1:3000").replace(/\/$/, "");
async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const route = path.join("/");
  if (!((request.method === "POST" && ["agents/invoke", "agents/invoke/stream"].includes(route)) || (request.method === "GET" && route === "agents"))) {
    return NextResponse.json({ detail: "Support route not found" }, { status: 404 });
  }
  const bearer = request.headers.get("authorization");
  if (!bearer?.startsWith("Bearer ")) return NextResponse.json({ detail: "Sign in for customer support" }, { status: 401 });
  const headers = { authorization: bearer, "content-type": "application/json" };
  try {
    // The verified customer association supplies scope; discard browser customer IDs.
    const profileResponse = await fetch(platform + "/api/home-dome/profile", { headers, cache: "no-store", signal: AbortSignal.timeout(30000) });
    if (!profileResponse.ok) return NextResponse.json({ detail: "Your customer account could not be verified" }, { status: profileResponse.status });
    const profile = await profileResponse.json();
    let body: string | undefined;
    if (request.method === "POST") {
      const input = await request.json();
      if (input.agent_type !== "customer_facing") return NextResponse.json({ detail: "Only the customer support agent is available here" }, { status: 403 });
      body = JSON.stringify({ agent_type: "customer_facing", message: input.message,
        conversation_id: input.conversation_id, stream_tokens: input.stream_tokens,
        context: { customer_id: profile.id, account_number: profile.accountNumber, ui_context: "customer_support" } });
    }
    const upstream = await fetch(platform + "/api/orchestrator/" + route, { method: request.method, headers, body, cache: "no-store", signal: request.signal });
    if (request.method === "GET" && upstream.ok) {
      const data = await upstream.json();
      const available = (rows: Array<{ agent_type?: string; type?: string; id?: string }>) => rows.filter(row => [row.agent_type, row.type, row.id].includes("customer_facing"));
      return NextResponse.json(Array.isArray(data) ? available(data) : { ...data, agents: available(data.agents || []) }, { headers: { "Cache-Control": "no-store, private" } });
    }
    // Stream SSE without buffering the agent's response.
    return new NextResponse(upstream.body, { status: upstream.status, headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-store, private", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff" } });
  } catch {
    return NextResponse.json({ detail: "Customer support is temporarily unavailable. Please retry." }, { status: 502 });
  }
}
export const GET = proxy;
export const POST = proxy;
