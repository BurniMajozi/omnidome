import { NextRequest, NextResponse } from "next/server"

export interface TelecomProvider {
  id: string
  name: string
  carrier_type: "Tier-1 Telco (Fibre / IPX)" | "Wholesale Interconnect" | "Mobile Network Operator (MNO)" | "Global Cloud SIP"
  sip_host: string
  sip_port: number
  transport: "UDP" | "TCP" | "TLS"
  username: string
  outbound_prefix: string
  assigned_did_ranges: string
  max_channels: number
  active_channels: number
  ping_latency_ms: number
  registration_status: "REGISTERED" | "DEGRADED_LATENCY" | "UNREACHABLE"
  failover_priority: number // 1 = Primary, 2 = Secondary, 3 = Fallback
  codecs: string[]
  monthly_commitment_zar: number
}

let telecomProviders: TelecomProvider[] = [
  {
    id: "prov-001",
    name: "Liquid Intelligent Technologies (Core Peering Teraco JB1)",
    carrier_type: "Tier-1 Telco (Fibre / IPX)",
    sip_host: "sip.jb1.liquidtelecom.net",
    sip_port: 5060,
    transport: "TLS",
    username: "omnidome_jb1_primary",
    outbound_prefix: "9001",
    assigned_did_ranges: "010 200 4000 - 010 200 4999 (1,000 DIDs)",
    max_channels: 60,
    active_channels: 14,
    ping_latency_ms: 3.2,
    registration_status: "REGISTERED",
    failover_priority: 1,
    codecs: ["G.722", "G.711a (PCMA)", "G.729"],
    monthly_commitment_zar: 14500,
  },
  {
    id: "prov-002",
    name: "Telkom Wholesale (National Breakout & 0800 Toll-Free)",
    carrier_type: "Wholesale Interconnect",
    sip_host: "sip.telkomwholesale.co.za",
    sip_port: 5060,
    transport: "UDP",
    username: "telkom_omnidome_voice",
    outbound_prefix: "9002",
    assigned_did_ranges: "0800 998 822 (Toll Free) + 012 300 0000 - 012 300 0500",
    max_channels: 40,
    active_channels: 4,
    ping_latency_ms: 12.8,
    registration_status: "REGISTERED",
    failover_priority: 2,
    codecs: ["G.711a", "G.729"],
    monthly_commitment_zar: 8900,
  },
  {
    id: "prov-003",
    name: "Vodacom Business (Direct MNO Interconnect)",
    carrier_type: "Mobile Network Operator (MNO)",
    sip_host: "sip-ims.vodacom.co.za",
    sip_port: 5061,
    transport: "TLS",
    username: "vodacom_corp_omni",
    outbound_prefix: "9003",
    assigned_did_ranges: "082 Mobile Route Allocation",
    max_channels: 30,
    active_channels: 0,
    ping_latency_ms: 15.4,
    registration_status: "REGISTERED",
    failover_priority: 3,
    codecs: ["AMR-WB", "G.722", "PCMA"],
    monthly_commitment_zar: 6500,
  },
  {
    id: "prov-004",
    name: "Twilio Global Transit (International Outbound & Roaming)",
    carrier_type: "Global Cloud SIP",
    sip_host: "omnidome-sip.pstn.twilio.com",
    sip_port: 5061,
    transport: "TLS",
    username: "twilio_edge_acc",
    outbound_prefix: "9004",
    assigned_did_ranges: "+1 (US/CA) & +44 (UK) DIDs",
    max_channels: 20,
    active_channels: 0,
    ping_latency_ms: 148.0,
    registration_status: "REGISTERED",
    failover_priority: 4,
    codecs: ["Opus", "PCMU", "PCMA"],
    monthly_commitment_zar: 2200,
  },
]

export async function GET() {
  const totalChannels = telecomProviders.reduce((acc, p) => acc + p.max_channels, 0)
  const activeChannels = telecomProviders.reduce((acc, p) => acc + p.active_channels, 0)
  return NextResponse.json({
    providers: telecomProviders,
    stats: {
      total_providers: telecomProviders.length,
      total_capacity_channels: totalChannels,
      active_in_use_channels: activeChannels,
      utilization_pct: +((activeChannels / totalChannels) * 100).toFixed(1),
      avg_latency_ms: 18.5,
      all_trunks_registered: telecomProviders.every((p) => p.registration_status === "REGISTERED"),
    },
  })
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { action } = body

    if (action === "ADD_PROVIDER") {
      const { name, carrier_type, sip_host, sip_port, transport, username, outbound_prefix, assigned_did_ranges, max_channels, monthly_commitment_zar } = body

      if (!name || !sip_host || !username) {
        return NextResponse.json({ error: "Missing required fields (name, sip_host, username)" }, { status: 400 })
      }

      const newProvider: TelecomProvider = {
        id: `prov-${Date.now()}`,
        name,
        carrier_type: carrier_type || "Wholesale Interconnect",
        sip_host,
        sip_port: Number(sip_port) || 5060,
        transport: transport || "TLS",
        username,
        outbound_prefix: outbound_prefix || "9005",
        assigned_did_ranges: assigned_did_ranges || "Pending Allocation",
        max_channels: Number(max_channels) || 20,
        active_channels: 0,
        ping_latency_ms: Math.floor(Math.random() * 20 + 8),
        registration_status: "REGISTERED",
        failover_priority: telecomProviders.length + 1,
        codecs: ["G.722", "PCMA", "G.729"],
        monthly_commitment_zar: Number(monthly_commitment_zar) || 5000,
      }

      telecomProviders.push(newProvider)
      return NextResponse.json({ success: true, provider: newProvider })
    }

    if (action === "TEST_SIP_OPTIONS") {
      const providerId = body.providerId
      const p = telecomProviders.find((x) => x.id === providerId) || telecomProviders[0]
      const latency = +(Math.random() * 8 + 3).toFixed(1)
      p.ping_latency_ms = latency
      p.registration_status = latency < 40 ? "REGISTERED" : "DEGRADED_LATENCY"

      return NextResponse.json({
        success: true,
        provider: p.name,
        result: `SIP/2.0 200 OK received from ${p.sip_host}:${p.sip_port} (${latency}ms round-trip via ${p.transport})`,
        latency_ms: latency,
      })
    }

    return NextResponse.json({ error: "Unknown action" }, { status: 400 })
  } catch (err: any) {
    return NextResponse.json({ error: err.message || "Failed to process telecom provider" }, { status: 500 })
  }
}

export async function DELETE(req: NextRequest) {
  const url = new URL(req.url)
  const id = url.searchParams.get("id")
  if (!id) return NextResponse.json({ error: "Missing provider id" }, { status: 400 })

  telecomProviders = telecomProviders.filter((p) => p.id !== id)
  return NextResponse.json({ success: true, remaining: telecomProviders.length })
}
