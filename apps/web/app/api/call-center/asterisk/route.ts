import { NextRequest, NextResponse } from "next/server"

export interface AsteriskCdrRecord {
  uniqueid: string
  linkedid: string
  clid: string
  src: string
  dst: string
  dcontext: string
  channel: string
  dstchannel: string
  lastapp: string
  lastdata: string
  start: string
  answer: string
  end: string
  duration: number
  billsec: number
  disposition: "ANSWERED" | "NO ANSWER" | "BUSY" | "FAILED"
  amaflags: string
  accountcode: string
  userfield: string

  // Strategic Calculated Fields
  carrier_prefix: string
  destination_type: "Local Mobile (Vodacom/MTN)" | "National Geographic (JHB/CPT)" | "Toll-Free (0800)" | "International Tier 1" | "High-Risk Premium"
  rate_per_minute_zar: number
  rated_cost_zar: number
  carrier_cost_zar: number
  margin_zar: number
  fraud_risk_score: number // 0 - 100
  fraud_flags: string[]
  stt_latency_ms: number // Deepgram Nova-3 latency
  tts_latency_ms: number // Deepgram Aura or Voicebox latency
  sentiment_polarity: number // -1.0 to 1.0
  queue_wait_time_sec: number
  agent_redundancy_sec: number // Idle time before call
  ftr_status: "FIRST_TIME_RESOLVED" | "FOLLOW_UP_REQUIRED" | "REPEAT_CALLER"
}

export interface CallSpikeTelemetry {
  time_bucket: string
  call_count: number
  active_talk_minutes: number
  agent_idle_redundancy_minutes: number
  spike_detected: boolean
  available_agents: number
}

// In-memory store of Asterisk Telemetry Ground Truth
let cdrDatabase: AsteriskCdrRecord[] = [
  {
    uniqueid: "ast-1727440001.101",
    linkedid: "ast-1727440001.101",
    clid: '"Bongani Sithole" <0824419921>',
    src: "0824419921",
    dst: "0800998822",
    dcontext: "ext-queues",
    channel: "PJSIP/liquid-trunk-00000a12",
    dstchannel: "PJSIP/101-sarah-mbeki-00000a13",
    lastapp: "Queue",
    lastdata: "tech_support,t,,,120",
    start: "2026-09-27 10:14:02",
    answer: "2026-09-27 10:14:18",
    end: "2026-09-27 10:22:45",
    duration: 523,
    billsec: 507,
    disposition: "ANSWERED",
    amaflags: "DOCUMENTATION",
    accountcode: "CUST-88129",
    userfield: "PROMO_ACCEPTED:UPGRADE_1GBPS",
    carrier_prefix: "+2782 (Vodacom SA)",
    destination_type: "Local Mobile (Vodacom/MTN)",
    rate_per_minute_zar: 0.45,
    rated_cost_zar: 3.80,
    carrier_cost_zar: 1.69,
    margin_zar: 2.11,
    fraud_risk_score: 4,
    fraud_flags: [],
    stt_latency_ms: 185,
    tts_latency_ms: 220,
    sentiment_polarity: 0.72,
    queue_wait_time_sec: 16,
    agent_redundancy_sec: 142,
    ftr_status: "FIRST_TIME_RESOLVED",
  },
  {
    uniqueid: "ast-1727440024.102",
    linkedid: "ast-1727440024.102",
    clid: '"Kagiso Ndlovu" <106>',
    src: "106",
    dst: "0839912041",
    dcontext: "outbound-sales",
    channel: "PJSIP/106-kagiso-ndlovu-00000a14",
    dstchannel: "PJSIP/telkom-trunk-00000a15",
    lastapp: "Dial",
    lastdata: "PJSIP/0839912041@telkom-trunk,60,r",
    start: "2026-09-27 10:20:10",
    answer: "2026-09-27 10:20:25",
    end: "2026-09-27 10:28:30",
    duration: 500,
    billsec: 485,
    disposition: "ANSWERED",
    amaflags: "BILLING",
    accountcode: "LEAD-44910",
    userfield: "OUTBOUND_CONVERSION_WON",
    carrier_prefix: "+2783 (MTN SA)",
    destination_type: "Local Mobile (Vodacom/MTN)",
    rate_per_minute_zar: 0.45,
    rated_cost_zar: 3.64,
    carrier_cost_zar: 1.62,
    margin_zar: 2.02,
    fraud_risk_score: 8,
    fraud_flags: [],
    stt_latency_ms: 210,
    tts_latency_ms: 240,
    sentiment_polarity: 0.85,
    queue_wait_time_sec: 0,
    agent_redundancy_sec: 38,
    ftr_status: "FIRST_TIME_RESOLVED",
  },
  {
    uniqueid: "ast-1727440112.103",
    linkedid: "ast-1727440112.103",
    clid: '"Unknown / AutoDialer" <0100019283>',
    src: "0100019283",
    dst: "0800998822",
    dcontext: "ext-queues",
    channel: "PJSIP/liquid-trunk-00000a16",
    dstchannel: "None",
    lastapp: "Hangup",
    lastdata: "16",
    start: "2026-09-27 10:25:00",
    answer: "2026-09-27 10:25:02",
    end: "2026-09-27 10:25:04",
    duration: 4,
    billsec: 2,
    disposition: "ANSWERED",
    amaflags: "SECURITY",
    accountcode: "SUSPECT_ROBOCALL",
    userfield: "AUTO_BLOCKED_ASTPP_FRAUD",
    carrier_prefix: "+2710 (JHB VoIP Block)",
    destination_type: "National Geographic (JHB/CPT)",
    rate_per_minute_zar: 0.22,
    rated_cost_zar: 0.05,
    carrier_cost_zar: 0.02,
    margin_zar: 0.03,
    fraud_risk_score: 91,
    fraud_flags: ["SHORT_DURATION_CALL (<3s)", "SUSPECTED_CLI_SPOOFING", "BURST_BURST_ATTACK"],
    stt_latency_ms: 95,
    tts_latency_ms: 0,
    sentiment_polarity: -0.90,
    queue_wait_time_sec: 2,
    agent_redundancy_sec: 0,
    ftr_status: "REPEAT_CALLER",
  },
  {
    uniqueid: "ast-1727440210.104",
    linkedid: "ast-1727440210.104",
    clid: '"Sandton MedClinic" <0117849920>',
    src: "0117849920",
    dst: "0800998822",
    dcontext: "ext-queues",
    channel: "PJSIP/vodacom-trunk-00000a18",
    dstchannel: "PJSIP/103-rethabile-00000a19",
    lastapp: "Queue",
    lastdata: "billing_queue,t,,,180",
    start: "2026-09-27 10:32:15",
    answer: "2026-09-27 10:32:28",
    end: "2026-09-27 10:41:40",
    duration: 565,
    billsec: 552,
    disposition: "ANSWERED",
    amaflags: "DOCUMENTATION",
    accountcode: "CUST-39014",
    userfield: "DISPUTE_SETTLED_NETCASH",
    carrier_prefix: "+2711 (Johannesburg)",
    destination_type: "National Geographic (JHB/CPT)",
    rate_per_minute_zar: 0.22,
    rated_cost_zar: 2.02,
    carrier_cost_zar: 0.83,
    margin_zar: 1.19,
    fraud_risk_score: 2,
    fraud_flags: [],
    stt_latency_ms: 172,
    tts_latency_ms: 198,
    sentiment_polarity: 0.68,
    queue_wait_time_sec: 13,
    agent_redundancy_sec: 85,
    ftr_status: "FIRST_TIME_RESOLVED",
  },
  {
    uniqueid: "ast-1727440315.105",
    linkedid: "ast-1727440315.105",
    clid: '"Pretoria High School" <0123440012>',
    src: "0123440012",
    dst: "0800998822",
    dcontext: "ext-queues",
    channel: "PJSIP/liquid-trunk-00000a20",
    dstchannel: "PJSIP/104-johan-pretorius-00000a21",
    lastapp: "Queue",
    lastdata: "noc_escalations,t,,,300",
    start: "2026-09-27 10:45:00",
    answer: "2026-09-27 10:45:12",
    end: "2026-09-27 10:59:15",
    duration: 855,
    billsec: 843,
    disposition: "ANSWERED",
    amaflags: "DOCUMENTATION",
    accountcode: "CUST-99201",
    userfield: "BGP_FLAP_RESOLVED",
    carrier_prefix: "+2712 (Pretoria)",
    destination_type: "National Geographic (JHB/CPT)",
    rate_per_minute_zar: 0.22,
    rated_cost_zar: 3.09,
    carrier_cost_zar: 1.26,
    margin_zar: 1.83,
    fraud_risk_score: 5,
    fraud_flags: [],
    stt_latency_ms: 165,
    tts_latency_ms: 215,
    sentiment_polarity: 0.91,
    queue_wait_time_sec: 12,
    agent_redundancy_sec: 210,
    ftr_status: "FIRST_TIME_RESOLVED",
  },
  {
    uniqueid: "ast-1727440401.106",
    linkedid: "ast-1727440401.106",
    clid: '"Suspicious Outbound" <109>',
    src: "109",
    dst: "008818291004",
    dcontext: "outbound-restricted",
    channel: "PJSIP/109-unauthorized-00000a22",
    dstchannel: "None",
    lastapp: "Congestion",
    lastdata: "3",
    start: "2026-09-27 10:55:00",
    answer: "2026-09-27 10:55:01",
    end: "2026-09-27 10:55:02",
    duration: 2,
    billsec: 0,
    disposition: "FAILED",
    amaflags: "FRAUD_SECURITY",
    accountcode: "BLOCKED_DESTINATION",
    userfield: "IRIDIUM_SATELLITE_TRIP",
    carrier_prefix: "+881 (Iridium Satellite)",
    destination_type: "High-Risk Premium",
    rate_per_minute_zar: 45.00,
    rated_cost_zar: 0.00,
    carrier_cost_zar: 0.00,
    margin_zar: 0.00,
    fraud_risk_score: 98,
    fraud_flags: ["HIGH_RISK_SATELLITE_PREFIX", "ASTPP_RATE_LIMIT_TRIP", "BLOCKED_BY_POLICY"],
    stt_latency_ms: 0,
    tts_latency_ms: 0,
    sentiment_polarity: -1.0,
    queue_wait_time_sec: 0,
    agent_redundancy_sec: 0,
    ftr_status: "FOLLOW_UP_REQUIRED",
  },
]

// 15-minute intervals showing Call Spikes vs Agent Redundancy / Idle time
const callSpikeHistory: CallSpikeTelemetry[] = [
  { time_bucket: "08:00 - 08:30", call_count: 48, active_talk_minutes: 284, agent_idle_redundancy_minutes: 92, spike_detected: false, available_agents: 12 },
  { time_bucket: "08:30 - 09:00", call_count: 64, active_talk_minutes: 412, agent_idle_redundancy_minutes: 48, spike_detected: false, available_agents: 14 },
  { time_bucket: "09:00 - 09:30", call_count: 92, active_talk_minutes: 618, agent_idle_redundancy_minutes: 18, spike_detected: true, available_agents: 15 },
  { time_bucket: "09:30 - 10:00", call_count: 114, active_talk_minutes: 742, agent_idle_redundancy_minutes: 8, spike_detected: true, available_agents: 16 },
  { time_bucket: "10:00 - 10:30", call_count: 88, active_talk_minutes: 580, agent_idle_redundancy_minutes: 24, spike_detected: false, available_agents: 16 },
  { time_bucket: "10:30 - 11:00", call_count: 76, active_talk_minutes: 490, agent_idle_redundancy_minutes: 54, spike_detected: false, available_agents: 15 },
  { time_bucket: "11:00 - 11:30", call_count: 62, active_talk_minutes: 395, agent_idle_redundancy_minutes: 82, spike_detected: false, available_agents: 14 },
  { time_bucket: "11:30 - 12:00", call_count: 55, active_talk_minutes: 340, agent_idle_redundancy_minutes: 104, spike_detected: false, available_agents: 14 },
]

export async function GET(req: NextRequest) {
  const url = new URL(req.url)
  const search = url.searchParams.get("search")?.toLowerCase()
  const filterDisposition = url.searchParams.get("disposition")
  const filterFraud = url.searchParams.get("fraud_only") === "true"

  let results = [...cdrDatabase]

  if (search) {
    results = results.filter(
      (c) =>
        c.src.includes(search) ||
        c.dst.includes(search) ||
        c.clid.toLowerCase().includes(search) ||
        c.carrier_prefix.toLowerCase().includes(search) ||
        c.accountcode.toLowerCase().includes(search)
    )
  }

  if (filterDisposition) {
    results = results.filter((c) => c.disposition === filterDisposition)
  }

  if (filterFraud) {
    results = results.filter((c) => c.fraud_risk_score > 50 || c.fraud_flags.length > 0)
  }

  // Summary Metrics
  const totalCalls = cdrDatabase.length
  const answeredCalls = cdrDatabase.filter((c) => c.disposition === "ANSWERED").length
  const totalBillableSec = cdrDatabase.reduce((acc, c) => acc + c.billsec, 0)
  const totalRatedRevenueZar = cdrDatabase.reduce((acc, c) => acc + c.rated_cost_zar, 0)
  const totalCarrierWholesaleZar = cdrDatabase.reduce((acc, c) => acc + c.carrier_cost_zar, 0)
  const totalMarginZar = totalRatedRevenueZar - totalCarrierWholesaleZar
  const avgSttLatency = Math.round(
    cdrDatabase.filter((c) => c.stt_latency_ms > 0).reduce((acc, c) => acc + c.stt_latency_ms, 0) /
      (cdrDatabase.filter((c) => c.stt_latency_ms > 0).length || 1)
  )
  const avgTtsLatency = Math.round(
    cdrDatabase.filter((c) => c.tts_latency_ms > 0).reduce((acc, c) => acc + c.tts_latency_ms, 0) /
      (cdrDatabase.filter((c) => c.tts_latency_ms > 0).length || 1)
  )
  const avgMttr = +(totalBillableSec / (answeredCalls || 1) / 60).toFixed(1)
  const fraudEventsCount = cdrDatabase.filter((c) => c.fraud_risk_score > 50).length

  return NextResponse.json({
    cdrs: results,
    spikes: callSpikeHistory,
    summary: {
      totalCalls,
      answeredCalls,
      answerRatePercent: +((answeredCalls / (totalCalls || 1)) * 100).toFixed(1),
      totalBillableMinutes: +(totalBillableSec / 60).toFixed(1),
      totalRatedRevenueZar: +totalRatedRevenueZar.toFixed(2),
      totalCarrierWholesaleZar: +totalCarrierWholesaleZar.toFixed(2),
      totalMarginZar: +totalMarginZar.toFixed(2),
      marginPercent: +((totalMarginZar / (totalRatedRevenueZar || 1)) * 100).toFixed(1),
      avgSttLatencyMs: avgSttLatency,
      avgTtsLatencyMs: avgTtsLatency,
      avgMttrMinutes: avgMttr,
      fraudEventsBlocked: fraudEventsCount,
      activeChannels: 18,
      maxChannelCapacity: 60,
    },
    sourceOfTruth: {
      driver: "res_pjsip & app_queue (Asterisk 20 LTS)",
      cdr_engine: "PostgreSQL ODBC cdr_adaptive",
      stt_engine: "Deepgram Nova-3 (AudioSocket Duplex)",
      tts_engine: "Deepgram Aura & Voicebox Cloned SA Voices",
      billing_rating: "ASTPP Real-Time 1-second pulse rating",
      active_trunk_status: "HEALTHY (3 Trunks Online)",
    },
  })
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { action } = body

    if (action === "INJECT_CDR") {
      const newCdr: AsteriskCdrRecord = {
        uniqueid: `ast-${Date.now()}.${Math.floor(Math.random() * 900) + 100}`,
        linkedid: `ast-${Date.now()}.0`,
        clid: body.clid || '"Test Customer" <0821112233>',
        src: body.src || "0821112233",
        dst: body.dst || "0800998822",
        dcontext: "ext-queues",
        channel: `PJSIP/${body.trunk || "liquid-trunk"}-00000a99`,
        dstchannel: `PJSIP/${body.agentExtension || "101"}-00000a99`,
        lastapp: "Queue",
        lastdata: `${body.queue || "tech_support"},t,,,120`,
        start: new Date().toISOString().replace("T", " ").substring(0, 19),
        answer: new Date().toISOString().replace("T", " ").substring(0, 19),
        end: new Date(Date.now() + (body.durationSec || 180) * 1000).toISOString().replace("T", " ").substring(0, 19),
        duration: body.durationSec || 180,
        billsec: (body.durationSec || 180) - 6,
        disposition: "ANSWERED",
        amaflags: "DOCUMENTATION",
        accountcode: body.accountcode || "CUST-MANUAL",
        userfield: body.userfield || "TEST_SIMULATED_CALL",
        carrier_prefix: body.prefix || "+2782 (Vodacom SA)",
        destination_type: body.destType || "Local Mobile (Vodacom/MTN)",
        rate_per_minute_zar: body.ratePerMin || 0.45,
        rated_cost_zar: +(((body.durationSec || 180) / 60) * (body.ratePerMin || 0.45)).toFixed(2),
        carrier_cost_zar: +(((body.durationSec || 180) / 60) * 0.20).toFixed(2),
        margin_zar: +(((body.durationSec || 180) / 60) * (body.ratePerMin || 0.45) - ((body.durationSec || 180) / 60) * 0.20).toFixed(2),
        fraud_risk_score: body.fraudScore || 0,
        fraud_flags: body.fraudFlags || [],
        stt_latency_ms: body.sttLatency || 180,
        tts_latency_ms: body.ttsLatency || 210,
        sentiment_polarity: body.sentiment || 0.5,
        queue_wait_time_sec: 6,
        agent_redundancy_sec: 45,
        ftr_status: "FIRST_TIME_RESOLVED",
      }

      cdrDatabase.unshift(newCdr)
      return NextResponse.json({ success: true, cdr: newCdr })
    }

    return NextResponse.json({ error: "Unknown action" }, { status: 400 })
  } catch (err: any) {
    return NextResponse.json({ error: err.message || "Failed to process Asterisk CDR" }, { status: 500 })
  }
}
