import { NextResponse, type NextRequest } from "next/server"

export interface PortalAiAgent {
  id: number | string
  name: string
  status: "active" | "paused"
  conversations: number
  resolution: string
  avgTime: string
  department?: string
  model?: string
}

let aiAgentsStore: PortalAiAgent[] = [
  {
    id: 1,
    name: "Customer Support Bot",
    status: "active",
    conversations: 4250,
    resolution: "78%",
    avgTime: "2.3 min",
    department: "Support",
    model: "claude-3-5-sonnet",
  },
  {
    id: 2,
    name: "Sales Assistant Bot",
    status: "active",
    conversations: 1820,
    resolution: "65%",
    avgTime: "4.1 min",
    department: "Sales",
    model: "gpt-4o",
  },
  {
    id: 3,
    name: "Technical Help Bot",
    status: "active",
    conversations: 2340,
    resolution: "82%",
    avgTime: "3.5 min",
    department: "Network",
    model: "claude-3-5-sonnet",
  },
  {
    id: 4,
    name: "Billing Inquiries Bot",
    status: "paused",
    conversations: 890,
    resolution: "71%",
    avgTime: "2.8 min",
    department: "Billing",
    model: "gpt-4o-mini",
  },
]

export async function GET(_request: NextRequest) {
  return NextResponse.json({ success: true, data: aiAgentsStore }, { status: 200 })
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    if (!body || !body.name) {
      return NextResponse.json({ success: false, error: "Bot name is required" }, { status: 400 })
    }

    const newAgent: PortalAiAgent = {
      id: Date.now(),
      name: body.name,
      status: body.status || "active",
      conversations: 0,
      resolution: "90%",
      avgTime: "1.8 min",
      department: body.department || "General",
      model: body.model || "claude-3-5-sonnet",
    }

    aiAgentsStore = [newAgent, ...aiAgentsStore]
    return NextResponse.json({ success: true, data: newAgent }, { status: 201 })
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "Failed to create agent" },
      { status: 500 }
    )
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json()
    if (!body || !body.id) {
      return NextResponse.json({ success: false, error: "Missing agent ID" }, { status: 400 })
    }

    aiAgentsStore = aiAgentsStore.map((agent) =>
      String(agent.id) === String(body.id) ? { ...agent, ...body } : agent
    )

    const updated = aiAgentsStore.find((a) => String(a.id) === String(body.id))
    return NextResponse.json({ success: true, data: updated }, { status: 200 })
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "Failed to update agent" },
      { status: 500 }
    )
  }
}
