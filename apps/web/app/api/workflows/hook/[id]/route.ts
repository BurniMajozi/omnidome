import { NextRequest, NextResponse } from "next/server"
import { timingSafeEqual } from "crypto"

/**
 * Public webhook trigger for a workflow — NO Supabase session required (external
 * systems call this). Runs in the workflow's own tenant (resolved server-side by
 * the orchestrator). Requires X-Webhook-Key == WORKFLOW_WEBHOOK_KEY; fails closed (503) when that
 * env var is unset. Compared in constant time.
 */
const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL || "http://agent-orchestrator:8021"
const WEBHOOK_KEY = process.env.WORKFLOW_WEBHOOK_KEY || ""

function keyMatches(provided: string): boolean {
  const a = Buffer.from(provided)
  const b = Buffer.from(WEBHOOK_KEY)
  // timingSafeEqual needs equal lengths; compare against self on mismatch to keep timing flat.
  if (a.length !== b.length) {
    timingSafeEqual(b, b)
    return false
  }
  return timingSafeEqual(a, b)
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  if (!WEBHOOK_KEY) {
    return NextResponse.json(
      { error: "webhook_disabled", message: "WORKFLOW_WEBHOOK_KEY is not configured on this server; workflow webhooks are disabled." },
      { status: 503 },
    )
  }
  if (!keyMatches(request.headers.get("x-webhook-key") || "")) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 })
  }
  const body = await request.text()
  const res = await fetch(`${ORCHESTRATOR_URL}/api/workflows/hooks/${id}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body || "{}",
    cache: "no-store",
  })
  const data = await res.json().catch(() => null)
  return NextResponse.json(data, { status: res.status })
}
