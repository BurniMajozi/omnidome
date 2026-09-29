import { NextRequest, NextResponse } from "next/server"

export interface SmartIvrNode {
  id: string
  name: string
  prompt_text: string
  voice_engine: "VOICEBOX_CLONED_SA" | "DEEPGRAM_AURA" | "LOCAL_ASTERISK_WAV"
  voice_persona: string
  marketing_campaign_push: {
    enabled: boolean
    campaign_title: string
    promo_audio_pitch: string
    target_segments: string[]
    discount_offer: string
  }
  hold_entertainment: {
    allow_genre_selection: boolean
    available_genres: Array<"Amapiano Grooves" | "Smooth Cape Jazz" | "Lo-Fi Beats" | "Deep House JHB" | "Classical">
    default_genre: string
    humor_mode_enabled: boolean
    humor_style: "South African Standup Comedy" | "Tech Support Bloopers & Jokes" | "Geek Trivia"
  }
  call_back_enabled: boolean
  call_back_trigger_after_wait_sec: number
  dtmf_options: Array<{
    digit: string
    label: string
    action: "ROUTE_QUEUE" | "AI_ORCHESTRATOR_BOT" | "PLAY_SUBMENU" | "CALL_SEEKER_HUNT" | "INSTANT_CALLBACK"
    target: string
  }>
  active_calls_in_ivr: number
}

let ivrNodes: SmartIvrNode[] = [
  {
    id: "ivr-main",
    name: "OmniDome Smart Telco Auto-Attendant",
    prompt_text: "Welcome to OmniDome Hyper-Reliable Broadband and Enterprise Corridors. Siya ya kuthokoza ngokubiza. Press 1 for Fibre Technical Support, Press 2 for Month-End Billing and Accounts, Press 3 for New 1Gbps Fibre Orders, or Press 0 to speak directly to an Operator.",
    voice_engine: "VOICEBOX_CLONED_SA",
    voice_persona: "Thandi (Warm South African Vernacular / English Accent)",
    marketing_campaign_push: {
      enabled: true,
      campaign_title: "Spring Township & Metro 500Mbps Fiber Burst",
      promo_audio_pitch: "Quick tip while we connect you: Upgrade to our uncapped 500Mbps symmetrical fibre today and receive your first 2 months at 40% off with free Wi-Fi 6 router installation.",
      target_segments: ["Residential FTTH", "Standard 100Mbps Subscribers", "Prepaid Fiber"],
      discount_offer: "SAVE40_FIBRE",
    },
    hold_entertainment: {
      allow_genre_selection: true,
      available_genres: ["Amapiano Grooves", "Smooth Cape Jazz", "Lo-Fi Beats", "Deep House JHB", "Classical"],
      default_genre: "Amapiano Grooves",
      humor_mode_enabled: true,
      humor_style: "South African Standup Comedy",
    },
    call_back_enabled: true,
    call_back_trigger_after_wait_sec: 45,
    dtmf_options: [
      { digit: "1", label: "Fibre Technical Support", action: "CALL_SEEKER_HUNT", target: "seeker-001 (Zero-Lost-Call Seeker)" },
      { digit: "2", label: "Billing & Accounts", action: "ROUTE_QUEUE", target: "queue_billing" },
      { digit: "3", label: "New Sales & Upgrades", action: "AI_ORCHESTRATOR_BOT", target: "Hermes Outbound Sales Agent" },
      { digit: "4", label: "Choose Hold Music / Comedy", action: "PLAY_SUBMENU", target: "ivr-music-humor-menu" },
      { digit: "9", label: "Request Automated Callback", action: "INSTANT_CALLBACK", target: "Auto-Callback Service" },
      { digit: "0", label: "Operator Hunt", action: "CALL_SEEKER_HUNT", target: "seeker-002" },
    ],
    active_calls_in_ivr: 4,
  },
  {
    id: "ivr-after-hours",
    name: "After-Hours & Load-Shedding Emergency IVR",
    prompt_text: "You have reached OmniDome after standard business hours. Our core NOC is actively monitoring all metro POPs. For severe area outages or live Eskom grid drops, press 1 for our AI Network Incident Assistant.",
    voice_engine: "DEEPGRAM_AURA",
    voice_persona: "Aura Asteria (Conversational Neutral)",
    marketing_campaign_push: {
      enabled: false,
      campaign_title: "",
      promo_audio_pitch: "",
      target_segments: [],
      discount_offer: "",
    },
    hold_entertainment: {
      allow_genre_selection: false,
      available_genres: ["Lo-Fi Beats"],
      default_genre: "Lo-Fi Beats",
      humor_mode_enabled: false,
      humor_style: "Tech Support Bloopers & Jokes",
    },
    call_back_enabled: true,
    call_back_trigger_after_wait_sec: 20,
    dtmf_options: [
      { digit: "1", label: "Report Area Fiber Break", action: "AI_ORCHESTRATOR_BOT", target: "Hermes NOC Emergency Bot" },
      { digit: "2", label: "Leave Voicemail-to-AI-Ticket", action: "ROUTE_QUEUE", target: "queue_voicemail_ai" },
      { digit: "9", label: "Urgent Callback at 08:00 AM", action: "INSTANT_CALLBACK", target: "Morning-Priority-Queue" },
    ],
    active_calls_in_ivr: 1,
  },
]

export async function GET() {
  return NextResponse.json({
    ivr_nodes: ivrNodes,
    stats: {
      total_ivr_flows: ivrNodes.length,
      active_callers_in_ivr: ivrNodes.reduce((acc, n) => acc + n.active_calls_in_ivr, 0),
      marketing_campaign_optins_today: 48,
      hold_music_selections: {
        amapiano: "46%",
        smooth_jazz: "28%",
        tech_humor: "18%",
        lo_fi: "8%",
      },
      callback_requests_fulfilled: 34,
      abandonment_prevented_pct: 14.8,
    },
  })
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { action } = body

    if (action === "UPDATE_IVR") {
      const { id, marketing_campaign_push, hold_entertainment, prompt_text, voice_engine, voice_persona } = body
      const node = ivrNodes.find((n) => n.id === id)
      if (!node) return NextResponse.json({ error: "IVR node not found" }, { status: 404 })

      if (marketing_campaign_push) node.marketing_campaign_push = { ...node.marketing_campaign_push, ...marketing_campaign_push }
      if (hold_entertainment) node.hold_entertainment = { ...node.hold_entertainment, ...hold_entertainment }
      if (prompt_text) node.prompt_text = prompt_text
      if (voice_engine) node.voice_engine = voice_engine
      if (voice_persona) node.voice_persona = voice_persona

      return NextResponse.json({ success: true, node })
    }

    if (action === "TOGGLE_CAMPAIGN") {
      const { id, enabled } = body
      const node = ivrNodes.find((n) => n.id === id)
      if (!node) return NextResponse.json({ error: "IVR node not found" }, { status: 404 })
      node.marketing_campaign_push.enabled = enabled
      return NextResponse.json({ success: true, enabled: node.marketing_campaign_push.enabled })
    }

    return NextResponse.json({ error: "Unknown action" }, { status: 400 })
  } catch (err: any) {
    return NextResponse.json({ error: err.message || "Failed to update IVR" }, { status: 500 })
  }
}
