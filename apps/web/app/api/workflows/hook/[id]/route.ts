import { NextRequest, NextResponse } from "next/server"

/**
 * Public webhook trigger for a workflow — NO Supabase session required (external
 * systems call this). Runs in the workflow's own tenant (resolved server-side by
 * the orchestrator). Optionally gated by X-Webhook-Key == WORKFLOW_WEBHOOK_KEY.
 */
const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL || "http://agent-orchestrator:8021"
const WEBHOOK_KEY = process.env.WORKFLOW_WEBHOOK_KEY || ""

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  if (WEBHOOK_KEY && request.headers.get("x-webhook-key") !== WEBHOOK_KEY) {
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
