import { NextRequest, NextResponse } from "next/server"

export interface CallSeekerGroup {
  id: string
  name: string
  inbound_did: string
  strategy: "TIERED_SPILLOVER" | "SIMULTANEOUS_BLAST" | "LINEAR_HUNT" | "GEO_POP_PROXIMITY"
  primary_tier_extensions: string[]
  secondary_spillover_extensions: string[]
  mobile_divert_numbers: string[] // Cell phone hunt via SIP trunk
  ring_timeout_sec: number
  fallback_action: "VOICEMAIL_TO_AI_TEXT" | "EMERGENCY_DISPATCH_QUEUE" | "AUTOMATED_CALL_BACK"
  deepgram_transcription_enabled: boolean
  auto_ticket_generation: boolean
  active_hunts_count: number
  total_calls_sought: number
  calls_rescued_pct: number // Percent of calls saved by seeker overflow instead of dropped
  status: "ACTIVE" | "PAUSED"
}

let callSeekerGroups: CallSeekerGroup[] = [
  {
    id: "seeker-001",
    name: "Zero-Lost-Call Fibre Tech Support Seeker",
    inbound_did: "0800 998 822 / 011 200 4000",
    strategy: "TIERED_SPILLOVER",
    primary_tier_extensions: ["101 (Sarah Mbeki)", "102 (Thabo Mokoena)", "107 (Nomvula Dlamini)"],
    secondary_spillover_extensions: ["104 (Johan Pretorius - NOC)", "105 (Sipho Khumalo - Field)"],
    mobile_divert_numbers: ["+27829910022 (Standby Field Manager)", "+27834419910 (NOC Lead Mobile)"],
    ring_timeout_sec: 15,
    fallback_action: "VOICEMAIL_TO_AI_TEXT",
    deepgram_transcription_enabled: true,
    auto_ticket_generation: true,
    active_hunts_count: 2,
    total_calls_sought: 1420,
    calls_rescued_pct: 99.4,
    status: "ACTIVE",
  },
  {
    id: "seeker-002",
    name: "VIP Enterprise & BGP Corridors Seeker",
    inbound_did: "010 500 8800 (Enterprise VIP)",
    strategy: "SIMULTANEOUS_BLAST",
    primary_tier_extensions: ["104 (Johan Pretorius)", "108 (Enterprise Desk)"],
    secondary_spillover_extensions: ["101 (Sarah Mbeki)", "Virtual AI Support Agent #1"],
    mobile_divert_numbers: ["+27820001199 (CTO Emergency Line)"],
    ring_timeout_sec: 10,
    fallback_action: "EMERGENCY_DISPATCH_QUEUE",
    deepgram_transcription_enabled: true,
    auto_ticket_generation: true,
    active_hunts_count: 0,
    total_calls_sought: 412,
    calls_rescued_pct: 100.0,
    status: "ACTIVE",
  },
  {
    id: "seeker-003",
    name: "Month-End Billing & Debit Order Seeker",
    inbound_did: "011 200 4002 (Accounts)",
    strategy: "LINEAR_HUNT",
    primary_tier_extensions: ["103 (Rethabile Sekhoto)", "108 (Lerato Molefe)"],
    secondary_spillover_extensions: ["106 (Kagiso Ndlovu)", "Virtual Billing Bot"],
    mobile_divert_numbers: ["+27843329911 (Finance Escalations)"],
    ring_timeout_sec: 18,
    fallback_action: "AUTOMATED_CALL_BACK",
    deepgram_transcription_enabled: true,
    auto_ticket_generation: true,
    active_hunts_count: 1,
    total_calls_sought: 890,
    calls_rescued_pct: 98.8,
    status: "ACTIVE",
  },
]

export async function GET() {
  return NextResponse.json({
    seeker_groups: callSeekerGroups,
    stats: {
      total_seeker_groups: callSeekerGroups.length,
      active_hunts_now: callSeekerGroups.reduce((acc, g) => acc + g.active_hunts_count, 0),
      total_calls_rescued: callSeekerGroups.reduce((acc, g) => acc + g.total_calls_sought, 0),
      avg_rescue_rate_pct: 99.4,
      zero_lost_call_protocol: "ENABLED (Tier 1 -> Tier 2 -> Mobile Cell SIP Divert -> Deepgram Voicemail AI)",
    },
  })
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { action } = body

    if (action === "ADD_SEEKER_GROUP") {
      const newGroup: CallSeekerGroup = {
        id: `seeker-${Date.now()}`,
        name: body.name || "Custom Hunt Group",
        inbound_did: body.inbound_did || "011 200 4099",
        strategy: body.strategy || "TIERED_SPILLOVER",
        primary_tier_extensions: body.primary_tier_extensions || ["101"],
        secondary_spillover_extensions: body.secondary_spillover_extensions || ["104"],
        mobile_divert_numbers: body.mobile_divert_numbers || ["+27820000000"],
        ring_timeout_sec: Number(body.ring_timeout_sec) || 15,
        fallback_action: body.fallback_action || "VOICEMAIL_TO_AI_TEXT",
        deepgram_transcription_enabled: true,
        auto_ticket_generation: true,
        active_hunts_count: 0,
        total_calls_sought: 0,
        calls_rescued_pct: 100.0,
        status: "ACTIVE",
      }
      callSeekerGroups.unshift(newGroup)
      return NextResponse.json({ success: true, seeker_group: newGroup })
    }

    if (action === "TRIGGER_TEST_HUNT") {
      // Simulate real-time hunt sequence
      const groupId = body.groupId || callSeekerGroups[0].id
      const group = callSeekerGroups.find((g) => g.id === groupId) || callSeekerGroups[0]
      group.active_hunts_count += 1
      group.total_calls_sought += 1

      return NextResponse.json({
        success: true,
        simulation: {
          step1: "Inbound call detected on " + group.inbound_did,
          step2: "Ringing Primary Tier (" + group.primary_tier_extensions.join(", ") + ") for " + group.ring_timeout_sec + "s",
          step3: "No answer -> Seeking Secondary Tier (" + group.secondary_spillover_extensions.join(", ") + ")",
          step4: "Answered by Secondary Extension or Mobile Cell via SIP Trunk",
          result: "CALL RESCUED - 0 Dropped Calls",
        },
      })
    }

    return NextResponse.json({ error: "Unknown action" }, { status: 400 })
  } catch (err: any) {
    return NextResponse.json({ error: err.message || "Failed to process Call Seeker" }, { status: 500 })
  }
}
