import { NextRequest, NextResponse } from "next/server"

export interface ShiftAssignment {
  id: string
  employeeId: string
  employeeName: string
  department: "Customer Support" | "Finance & Billing" | "NOC & Core Infra" | "Field Operations" | "Outbound Sales"
  shiftType: "Morning (06:00 - 15:00)" | "Peak Support (08:00 - 17:00)" | "Evening Standby (16:00 - 00:00)" | "NOC Night Watch (22:00 - 06:00)"
  startTime: string
  endTime: string
  dayOfWeek: "Monday" | "Tuesday" | "Wednesday" | "Thursday" | "Friday" | "Saturday" | "Sunday"
  date: string
  station: string
  isOutsourced: boolean
  brokerName?: string
  hourlyRateZar: number
  overtimeHours: number
  onLeave: boolean
  leaveReason?: string
  mttrMinutes: number // Mean Time to Resolve
  ftrPercent: number // First Time Resolution %
  skillTags: string[]
  inboundAnswerRatePercent: number
  outboundCallsToday: number
  outboundConversions: number
  commissionEarnedZar: number
  postCallCsat: number
}

export interface DemandTimelineSlot {
  hour: string
  required: number
  scheduled: number
  predictedTickets: number
  ticketMix: {
    fiberHardware: number
    billingFinance: number
    generalSupport: number
    outboundColdCalls: number
  }
}

// In-memory shift database seeded with realistic South African ISP staffing data
let shiftRoster: ShiftAssignment[] = [
  {
    id: "shift-1",
    employeeId: "emp-001",
    employeeName: "Sarah Mbeki",
    department: "Customer Support",
    shiftType: "Morning (06:00 - 15:00)",
    startTime: "06:00",
    endTime: "15:00",
    dayOfWeek: "Friday",
    date: "2026-09-27",
    station: "Tier 1 Fibre Queue & Live Chat",
    isOutsourced: false,
    hourlyRateZar: 115,
    overtimeHours: 2,
    onLeave: false,
    mttrMinutes: 14.5,
    ftrPercent: 94.2,
    skillTags: ["ONT Diagnostic", "PPPoE Setup", "Customer Empathy", "English & Zulu"],
    inboundAnswerRatePercent: 98.1,
    outboundCallsToday: 0,
    outboundConversions: 0,
    commissionEarnedZar: 0,
    postCallCsat: 4.8,
  },
  {
    id: "shift-2",
    employeeId: "emp-002",
    employeeName: "Thabo Mokoena",
    department: "Customer Support",
    shiftType: "Peak Support (08:00 - 17:00)",
    startTime: "08:00",
    endTime: "17:00",
    dayOfWeek: "Friday",
    date: "2026-09-27",
    station: "Inbound Escalations & Voice Queue",
    isOutsourced: true,
    brokerName: "CCI South Africa (HR Broker)",
    hourlyRateZar: 135,
    overtimeHours: 0,
    onLeave: false,
    mttrMinutes: 18.2,
    ftrPercent: 88.5,
    skillTags: ["Wi-Fi 6 Router Troubleshooting", "SLA Escalation", "English & Sotho"],
    inboundAnswerRatePercent: 95.4,
    outboundCallsToday: 0,
    outboundConversions: 0,
    commissionEarnedZar: 0,
    postCallCsat: 4.6,
  },
  {
    id: "shift-3",
    employeeId: "emp-003",
    employeeName: "Rethabile Sekhoto",
    department: "Finance & Billing",
    shiftType: "Peak Support (08:00 - 17:00)",
    startTime: "08:00",
    endTime: "17:00",
    dayOfWeek: "Friday",
    date: "2026-09-27",
    station: "Month-End Billing & Debit Order Queue",
    isOutsourced: false,
    hourlyRateZar: 160,
    overtimeHours: 4,
    onLeave: false,
    mttrMinutes: 11.2,
    ftrPercent: 96.8,
    skillTags: ["Debit Order Reversals", "Invoice Variance", "Pro-Rata Credits", "Netcash Gateway"],
    inboundAnswerRatePercent: 99.0,
    outboundCallsToday: 12,
    outboundConversions: 8,
    commissionEarnedZar: 600,
    postCallCsat: 4.9,
  },
  {
    id: "shift-4",
    employeeId: "emp-004",
    employeeName: "Johan Pretorius",
    department: "NOC & Core Infra",
    shiftType: "NOC Night Watch (22:00 - 06:00)",
    startTime: "22:00",
    endTime: "06:00",
    dayOfWeek: "Friday",
    date: "2026-09-27",
    station: "Core BGP & Teraco Cross-Connect Monitor",
    isOutsourced: false,
    hourlyRateZar: 220,
    overtimeHours: 8,
    onLeave: false,
    mttrMinutes: 8.5,
    ftrPercent: 98.4,
    skillTags: ["BGP Flapping", "DWDM Metro", "MikroTik CCR2216", "NAPAfrica Peering"],
    inboundAnswerRatePercent: 100,
    outboundCallsToday: 0,
    outboundConversions: 0,
    commissionEarnedZar: 0,
    postCallCsat: 5.0,
  },
  {
    id: "shift-5",
    employeeId: "emp-005",
    employeeName: "Sipho Khumalo",
    department: "Field Operations",
    shiftType: "Morning (06:00 - 15:00)",
    startTime: "06:00",
    endTime: "15:00",
    dayOfWeek: "Friday",
    date: "2026-09-27",
    station: "Soweto & Johannesburg South Splicing Van #4",
    isOutsourced: true,
    brokerName: "Merchants BPO / TechStaff",
    hourlyRateZar: 140,
    overtimeHours: 3,
    onLeave: false,
    mttrMinutes: 32.0,
    ftrPercent: 91.2,
    skillTags: ["Fujikura Fusion Splicer", "OTDR Fiber Break Test", "Trench Re-instatement"],
    inboundAnswerRatePercent: 92.0,
    outboundCallsToday: 0,
    outboundConversions: 0,
    commissionEarnedZar: 0,
    postCallCsat: 4.7,
  },
  {
    id: "shift-6",
    employeeId: "emp-006",
    employeeName: "Kagiso Ndlovu",
    department: "Outbound Sales",
    shiftType: "Peak Support (08:00 - 17:00)",
    startTime: "08:00",
    endTime: "17:00",
    dayOfWeek: "Friday",
    date: "2026-09-27",
    station: "Cold Calling & Lead Conversion Desk",
    isOutsourced: false,
    hourlyRateZar: 105,
    overtimeHours: 0,
    onLeave: false,
    mttrMinutes: 16.0,
    ftrPercent: 86.4,
    skillTags: ["Cold Calling", "Fiber Speed Upgrades", "VoIP Bundle Closing", "Objection Handling"],
    inboundAnswerRatePercent: 94.0,
    outboundCallsToday: 142,
    outboundConversions: 18,
    commissionEarnedZar: 2700,
    postCallCsat: 4.5,
  },
  {
    id: "shift-7",
    employeeId: "emp-007",
    employeeName: "Nomvula Dlamini",
    department: "Customer Support",
    shiftType: "Evening Standby (16:00 - 00:00)",
    startTime: "16:00",
    endTime: "00:00",
    dayOfWeek: "Friday",
    date: "2026-09-27",
    station: "Evening Streaming & Gaming Latency Triage",
    isOutsourced: true,
    brokerName: "Teleperformance SA",
    hourlyRateZar: 130,
    overtimeHours: 1,
    onLeave: false,
    mttrMinutes: 19.5,
    ftrPercent: 87.0,
    skillTags: ["MTU/DNS Tuning", "Steam/PlayStation Latency", "Evening Incident Log"],
    inboundAnswerRatePercent: 96.2,
    outboundCallsToday: 0,
    outboundConversions: 0,
    commissionEarnedZar: 0,
    postCallCsat: 4.4,
  },
  {
    id: "shift-8",
    employeeId: "emp-008",
    employeeName: "Lerato Molefe",
    department: "Finance & Billing",
    shiftType: "Morning (06:00 - 15:00)",
    startTime: "06:00",
    endTime: "15:00",
    dayOfWeek: "Friday",
    date: "2026-09-27",
    station: "Unallocated Deposits & EFT Proof Verification",
    isOutsourced: false,
    hourlyRateZar: 150,
    overtimeHours: 0,
    onLeave: true,
    leaveReason: "Approved Annual Leave (25 - 30 Sep)",
    mttrMinutes: 13.0,
    ftrPercent: 95.0,
    skillTags: ["Bank Statement Reconciliation", "FNB Instant EFT", "Capitec Pay Allocation"],
    inboundAnswerRatePercent: 0,
    outboundCallsToday: 0,
    outboundConversions: 0,
    commissionEarnedZar: 0,
    postCallCsat: 0,
  }
]

// Timeline Demand Curves
const TIMELINE_DEMAND_DATA: Record<string, DemandTimelineSlot[]> = {
  realtime: [
    { hour: "00:00", required: 3, scheduled: 3, predictedTickets: 12, ticketMix: { fiberHardware: 2, billingFinance: 1, generalSupport: 9, outboundColdCalls: 0 } },
    { hour: "02:00", required: 3, scheduled: 3, predictedTickets: 8, ticketMix: { fiberHardware: 1, billingFinance: 0, generalSupport: 7, outboundColdCalls: 0 } },
    { hour: "04:00", required: 4, scheduled: 3, predictedTickets: 15, ticketMix: { fiberHardware: 4, billingFinance: 1, generalSupport: 10, outboundColdCalls: 0 } },
    { hour: "06:00", required: 7, scheduled: 6, predictedTickets: 38, ticketMix: { fiberHardware: 8, billingFinance: 12, generalSupport: 18, outboundColdCalls: 0 } },
    { hour: "08:00", required: 16, scheduled: 15, predictedTickets: 86, ticketMix: { fiberHardware: 22, billingFinance: 28, generalSupport: 36, outboundColdCalls: 45 } },
    { hour: "10:00", required: 20, scheduled: 19, predictedTickets: 114, ticketMix: { fiberHardware: 30, billingFinance: 38, generalSupport: 46, outboundColdCalls: 60 } },
    { hour: "12:00", required: 18, scheduled: 18, predictedTickets: 95, ticketMix: { fiberHardware: 24, billingFinance: 32, generalSupport: 39, outboundColdCalls: 50 } },
    { hour: "14:00", required: 22, scheduled: 18, predictedTickets: 128, ticketMix: { fiberHardware: 36, billingFinance: 44, generalSupport: 48, outboundColdCalls: 55 } }, // Gap 4
    { hour: "16:00", required: 18, scheduled: 17, predictedTickets: 92, ticketMix: { fiberHardware: 26, billingFinance: 30, generalSupport: 36, outboundColdCalls: 30 } },
    { hour: "18:00", required: 14, scheduled: 14, predictedTickets: 68, ticketMix: { fiberHardware: 18, billingFinance: 14, generalSupport: 36, outboundColdCalls: 0 } },
    { hour: "20:00", required: 8, scheduled: 8, predictedTickets: 42, ticketMix: { fiberHardware: 10, billingFinance: 6, generalSupport: 26, outboundColdCalls: 0 } },
    { hour: "22:00", required: 4, scheduled: 4, predictedTickets: 19, ticketMix: { fiberHardware: 4, billingFinance: 2, generalSupport: 13, outboundColdCalls: 0 } },
  ],
  month_end_peak: [
    { hour: "00:00", required: 4, scheduled: 3, predictedTickets: 22, ticketMix: { fiberHardware: 2, billingFinance: 14, generalSupport: 6, outboundColdCalls: 0 } },
    { hour: "02:00", required: 3, scheduled: 3, predictedTickets: 14, ticketMix: { fiberHardware: 1, billingFinance: 9, generalSupport: 4, outboundColdCalls: 0 } },
    { hour: "04:00", required: 4, scheduled: 3, predictedTickets: 20, ticketMix: { fiberHardware: 2, billingFinance: 12, generalSupport: 6, outboundColdCalls: 0 } },
    { hour: "06:00", required: 9, scheduled: 7, predictedTickets: 65, ticketMix: { fiberHardware: 6, billingFinance: 42, generalSupport: 17, outboundColdCalls: 0 } },
    { hour: "08:00", required: 24, scheduled: 18, predictedTickets: 165, ticketMix: { fiberHardware: 18, billingFinance: 110, generalSupport: 37, outboundColdCalls: 20 } }, // Finance gap!
    { hour: "10:00", required: 28, scheduled: 21, predictedTickets: 198, ticketMix: { fiberHardware: 22, billingFinance: 135, generalSupport: 41, outboundColdCalls: 25 } },
    { hour: "12:00", required: 26, scheduled: 22, predictedTickets: 175, ticketMix: { fiberHardware: 20, billingFinance: 118, generalSupport: 37, outboundColdCalls: 20 } },
    { hour: "14:00", required: 27, scheduled: 20, predictedTickets: 184, ticketMix: { fiberHardware: 22, billingFinance: 124, generalSupport: 38, outboundColdCalls: 22 } },
    { hour: "16:00", required: 22, scheduled: 18, predictedTickets: 142, ticketMix: { fiberHardware: 18, billingFinance: 92, generalSupport: 32, outboundColdCalls: 15 } },
    { hour: "18:00", required: 16, scheduled: 14, predictedTickets: 96, ticketMix: { fiberHardware: 12, billingFinance: 58, generalSupport: 26, outboundColdCalls: 0 } },
    { hour: "20:00", required: 10, scheduled: 9, predictedTickets: 54, ticketMix: { fiberHardware: 6, billingFinance: 32, generalSupport: 16, outboundColdCalls: 0 } },
    { hour: "22:00", required: 5, scheduled: 4, predictedTickets: 28, ticketMix: { fiberHardware: 3, billingFinance: 16, generalSupport: 9, outboundColdCalls: 0 } },
  ],
  storm_outage: [
    { hour: "00:00", required: 6, scheduled: 3, predictedTickets: 48, ticketMix: { fiberHardware: 38, billingFinance: 1, generalSupport: 9, outboundColdCalls: 0 } },
    { hour: "02:00", required: 6, scheduled: 3, predictedTickets: 42, ticketMix: { fiberHardware: 34, billingFinance: 0, generalSupport: 8, outboundColdCalls: 0 } },
    { hour: "04:00", required: 8, scheduled: 4, predictedTickets: 58, ticketMix: { fiberHardware: 48, billingFinance: 1, generalSupport: 9, outboundColdCalls: 0 } },
    { hour: "06:00", required: 16, scheduled: 8, predictedTickets: 120, ticketMix: { fiberHardware: 98, billingFinance: 4, generalSupport: 18, outboundColdCalls: 0 } },
    { hour: "08:00", required: 32, scheduled: 18, predictedTickets: 260, ticketMix: { fiberHardware: 215, billingFinance: 8, generalSupport: 37, outboundColdCalls: 0 } },
    { hour: "10:00", required: 36, scheduled: 20, predictedTickets: 295, ticketMix: { fiberHardware: 245, billingFinance: 10, generalSupport: 40, outboundColdCalls: 0 } },
    { hour: "12:00", required: 34, scheduled: 22, predictedTickets: 270, ticketMix: { fiberHardware: 220, billingFinance: 12, generalSupport: 38, outboundColdCalls: 0 } },
    { hour: "14:00", required: 32, scheduled: 21, predictedTickets: 250, ticketMix: { fiberHardware: 205, billingFinance: 11, generalSupport: 34, outboundColdCalls: 0 } },
    { hour: "16:00", required: 26, scheduled: 19, predictedTickets: 210, ticketMix: { fiberHardware: 172, billingFinance: 9, generalSupport: 29, outboundColdCalls: 0 } },
    { hour: "18:00", required: 20, scheduled: 15, predictedTickets: 150, ticketMix: { fiberHardware: 122, billingFinance: 6, generalSupport: 22, outboundColdCalls: 0 } },
    { hour: "20:00", required: 14, scheduled: 10, predictedTickets: 98, ticketMix: { fiberHardware: 80, billingFinance: 3, generalSupport: 15, outboundColdCalls: 0 } },
    { hour: "22:00", required: 8, scheduled: 5, predictedTickets: 55, ticketMix: { fiberHardware: 44, billingFinance: 2, generalSupport: 9, outboundColdCalls: 0 } },
  ],
  yesterday: [
    { hour: "00:00", required: 3, scheduled: 3, predictedTickets: 10, ticketMix: { fiberHardware: 1, billingFinance: 1, generalSupport: 8, outboundColdCalls: 0 } },
    { hour: "02:00", required: 3, scheduled: 3, predictedTickets: 7, ticketMix: { fiberHardware: 1, billingFinance: 0, generalSupport: 6, outboundColdCalls: 0 } },
    { hour: "04:00", required: 3, scheduled: 3, predictedTickets: 12, ticketMix: { fiberHardware: 2, billingFinance: 1, generalSupport: 9, outboundColdCalls: 0 } },
    { hour: "06:00", required: 6, scheduled: 6, predictedTickets: 32, ticketMix: { fiberHardware: 6, billingFinance: 8, generalSupport: 18, outboundColdCalls: 0 } },
    { hour: "08:00", required: 15, scheduled: 15, predictedTickets: 78, ticketMix: { fiberHardware: 18, billingFinance: 22, generalSupport: 38, outboundColdCalls: 40 } },
    { hour: "10:00", required: 18, scheduled: 18, predictedTickets: 102, ticketMix: { fiberHardware: 26, billingFinance: 30, generalSupport: 46, outboundColdCalls: 55 } },
    { hour: "12:00", required: 16, scheduled: 16, predictedTickets: 88, ticketMix: { fiberHardware: 20, billingFinance: 28, generalSupport: 40, outboundColdCalls: 48 } },
    { hour: "14:00", required: 19, scheduled: 19, predictedTickets: 110, ticketMix: { fiberHardware: 28, billingFinance: 36, generalSupport: 46, outboundColdCalls: 50 } },
    { hour: "16:00", required: 16, scheduled: 16, predictedTickets: 85, ticketMix: { fiberHardware: 22, billingFinance: 26, generalSupport: 37, outboundColdCalls: 25 } },
    { hour: "18:00", required: 12, scheduled: 12, predictedTickets: 60, ticketMix: { fiberHardware: 14, billingFinance: 12, generalSupport: 34, outboundColdCalls: 0 } },
    { hour: "20:00", required: 7, scheduled: 7, predictedTickets: 36, ticketMix: { fiberHardware: 8, billingFinance: 5, generalSupport: 23, outboundColdCalls: 0 } },
    { hour: "22:00", required: 3, scheduled: 3, predictedTickets: 15, ticketMix: { fiberHardware: 3, billingFinance: 1, generalSupport: 11, outboundColdCalls: 0 } },
  ],
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const timeline = searchParams.get("timeline") || "realtime"
  const department = searchParams.get("department")

  let filteredRoster = shiftRoster
  if (department && department !== "ALL") {
    filteredRoster = filteredRoster.filter((s) => s.department === department)
  }

  const demandTimeline = TIMELINE_DEMAND_DATA[timeline] || TIMELINE_DEMAND_DATA.realtime

  // Calculate high-level summary KPIs
  const totalRostered = filteredRoster.length
  const onLeaveCount = filteredRoster.filter((s) => s.onLeave).length
  const outsourcedCount = filteredRoster.filter((s) => s.isOutsourced).length
  const internalCount = totalRostered - outsourcedCount
  const totalOvertimeHours = filteredRoster.reduce((sum, s) => sum + s.overtimeHours, 0)
  const totalCommissionPoolZar = filteredRoster.reduce((sum, s) => sum + s.commissionEarnedZar, 0)
  const totalOutboundDials = filteredRoster.reduce((sum, s) => sum + s.outboundCallsToday, 0)
  const totalOutboundConversions = filteredRoster.reduce((sum, s) => sum + s.outboundConversions, 0)

  // Weighted average MTTR and FTR
  const activeStaff = filteredRoster.filter((s) => !s.onLeave)
  const avgMttr = activeStaff.length > 0 ? (activeStaff.reduce((sum, s) => sum + s.mttrMinutes, 0) / activeStaff.length).toFixed(1) : "0"
  const avgFtr = activeStaff.length > 0 ? (activeStaff.reduce((sum, s) => sum + s.ftrPercent, 0) / activeStaff.length).toFixed(1) : "0"
  const avgCsat = activeStaff.length > 0 ? (activeStaff.reduce((sum, s) => sum + s.postCallCsat, 0) / activeStaff.length).toFixed(2) : "0"

  // Cost estimates
  const internalCostZar = filteredRoster.filter((s) => !s.isOutsourced).reduce((sum, s) => sum + s.hourlyRateZar * 8, 0)
  const brokerCostZar = filteredRoster.filter((s) => s.isOutsourced).reduce((sum, s) => sum + s.hourlyRateZar * 8, 0)
  const overtimeCostZar = filteredRoster.reduce((sum, s) => sum + s.overtimeHours * (s.hourlyRateZar * 1.5), 0)

  return NextResponse.json({
    roster: filteredRoster,
    demandTimeline,
    summary: {
      totalRostered,
      activeHeadcount: totalRostered - onLeaveCount,
      onLeaveCount,
      outsourcedCount,
      internalCount,
      totalOvertimeHours,
      totalCommissionPoolZar,
      totalOutboundDials,
      totalOutboundConversions,
      avgMttrMinutes: Number(avgMttr),
      avgFtrPercent: Number(avgFtr),
      avgCsatScore: Number(avgCsat),
      costSummary: {
        internalDailyZar: internalCostZar,
        brokerDailyZar: brokerCostZar,
        overtimeDailyZar: overtimeCostZar,
        totalDailyZar: internalCostZar + brokerCostZar + overtimeCostZar,
      },
      inboundCallMetrics: {
        offeredCalls: 1482,
        answeredCalls: 1421,
        answerRatePercent: 95.9,
        abandonmentRatePercent: 4.1,
        averageSpeedOfAnswerSec: 18,
        postCallSurveysReceived: 820,
      }
    }
  })
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const newShift: ShiftAssignment = {
      id: `shift-${Date.now()}`,
      employeeId: body.employeeId || `emp-${Date.now().toString().slice(-4)}`,
      employeeName: body.employeeName,
      department: body.department,
      shiftType: body.shiftType,
      startTime: body.startTime || "08:00",
      endTime: body.endTime || "17:00",
      dayOfWeek: body.dayOfWeek || "Friday",
      date: body.date || new Date().toISOString().split("T")[0],
      station: body.station,
      isOutsourced: Boolean(body.isOutsourced),
      brokerName: body.isOutsourced ? body.brokerName || "CCI South Africa" : undefined,
      hourlyRateZar: Number(body.hourlyRateZar) || 120,
      overtimeHours: Number(body.overtimeHours) || 0,
      onLeave: Boolean(body.onLeave),
      leaveReason: body.leaveReason,
      mttrMinutes: Number(body.mttrMinutes) || 18.0,
      ftrPercent: Number(body.ftrPercent) || 90.0,
      skillTags: body.skillTags || ["General Customer Care"],
      inboundAnswerRatePercent: 96.0,
      outboundCallsToday: Number(body.outboundCallsToday) || 0,
      outboundConversions: Number(body.outboundConversions) || 0,
      commissionEarnedZar: Number(body.commissionEarnedZar) || 0,
      postCallCsat: Number(body.postCallCsat) || 4.7,
    }

    shiftRoster = [newShift, ...shiftRoster]
    return NextResponse.json({ success: true, shift: newShift })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Failed to create shift"
    return NextResponse.json({ error: msg }, { status: 400 })
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json()
    const { id, ...updates } = body
    if (!id) {
      return NextResponse.json({ error: "Missing shift id" }, { status: 400 })
    }

    const index = shiftRoster.findIndex((s) => s.id === id)
    if (index === -1) {
      return NextResponse.json({ error: "Shift not found" }, { status: 404 })
    }

    shiftRoster[index] = {
      ...shiftRoster[index],
      ...updates,
    }

    return NextResponse.json({ success: true, shift: shiftRoster[index] })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Failed to update shift"
    return NextResponse.json({ error: msg }, { status: 400 })
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const id = searchParams.get("id")
    if (!id) {
      return NextResponse.json({ error: "Missing shift id" }, { status: 400 })
    }

    shiftRoster = shiftRoster.filter((s) => s.id !== id)
    return NextResponse.json({ success: true, removedId: id })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Failed to delete shift"
    return NextResponse.json({ error: msg }, { status: 400 })
  }
}
