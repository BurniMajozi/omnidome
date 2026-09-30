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

// There is no rostering / workforce-demand backend yet. The in-memory roster
// (invented staff, hourly rates, MTTR/FTR/CSAT, inbound call metrics) and the
// hard-coded demand timelines that used to live here were fabricated figures and
// have been removed. Every method answers 501 until a real service is wired in.
const NOT_IMPLEMENTED = () =>
  NextResponse.json(
    { error: "Shift rostering is not connected: no rostering service exists yet.", connected: false },
    { status: 501 },
  )

export async function GET(_request: NextRequest) {
  return NOT_IMPLEMENTED()
}

export async function POST(_request: NextRequest) {
  return NOT_IMPLEMENTED()
}

export async function PUT(_request: NextRequest) {
  return NOT_IMPLEMENTED()
}

export async function DELETE(_request: NextRequest) {
  return NOT_IMPLEMENTED()
}
