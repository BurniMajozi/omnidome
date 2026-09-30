import { NextRequest, NextResponse } from "next/server"
import { simulatedTelephonyGuard } from "@/lib/call-center-guard"

export interface AstppRateCard {
  id: string
  destination: string
  prefix: string
  destination_type: "Local Mobile" | "National Geographic" | "Toll-Free" | "Special / VoIP" | "International Tier 1" | "High-Risk Satellite"
  buy_rate_zar: number
  sell_rate_zar: number
  pulse: "1/1 (Per Second)" | "60/60 (Per Minute)" | "60/1 (First Minute then Second)"
  connection_fee_zar: number
  margin_percent: number
  effective_date: string
  active: boolean
  carrier: "Telkom Wholesale" | "Liquid Telecom" | "Vodacom Business" | "MTN Wholesale" | "Twilio Global"
}

let rateCards: AstppRateCard[] = [
  {
    id: "rate-001",
    destination: "South Africa - Vodacom Mobile",
    prefix: "2782, 2772, 2776, 2779, 2760",
    destination_type: "Local Mobile",
    buy_rate_zar: 0.20,
    sell_rate_zar: 0.45,
    pulse: "1/1 (Per Second)",
    connection_fee_zar: 0.00,
    margin_percent: 55.6,
    effective_date: "2026-01-01",
    active: true,
    carrier: "Liquid Telecom",
  },
  {
    id: "rate-002",
    destination: "South Africa - MTN Mobile",
    prefix: "2783, 2773, 2778, 2763",
    destination_type: "Local Mobile",
    buy_rate_zar: 0.20,
    sell_rate_zar: 0.45,
    pulse: "1/1 (Per Second)",
    connection_fee_zar: 0.00,
    margin_percent: 55.6,
    effective_date: "2026-01-01",
    active: true,
    carrier: "Liquid Telecom",
  },
  {
    id: "rate-003",
    destination: "South Africa - Telkom Mobile & Fixed",
    prefix: "2781, 2761, 2765",
    destination_type: "Local Mobile",
    buy_rate_zar: 0.18,
    sell_rate_zar: 0.42,
    pulse: "1/1 (Per Second)",
    connection_fee_zar: 0.00,
    margin_percent: 57.1,
    effective_date: "2026-01-01",
    active: true,
    carrier: "Telkom Wholesale",
  },
  {
    id: "rate-004",
    destination: "South Africa - Cell C Mobile",
    prefix: "2784, 2774, 2764",
    destination_type: "Local Mobile",
    buy_rate_zar: 0.22,
    sell_rate_zar: 0.48,
    pulse: "1/1 (Per Second)",
    connection_fee_zar: 0.00,
    margin_percent: 54.2,
    effective_date: "2026-01-01",
    active: true,
    carrier: "Vodacom Business",
  },
  {
    id: "rate-005",
    destination: "South Africa - Gauteng (Johannesburg 011 / 010)",
    prefix: "2711, 2710",
    destination_type: "National Geographic",
    buy_rate_zar: 0.09,
    sell_rate_zar: 0.22,
    pulse: "1/1 (Per Second)",
    connection_fee_zar: 0.00,
    margin_percent: 59.1,
    effective_date: "2026-01-01",
    active: true,
    carrier: "Liquid Telecom",
  },
  {
    id: "rate-006",
    destination: "South Africa - Western Cape (Cape Town 021)",
    prefix: "2721",
    destination_type: "National Geographic",
    buy_rate_zar: 0.09,
    sell_rate_zar: 0.22,
    pulse: "1/1 (Per Second)",
    connection_fee_zar: 0.00,
    margin_percent: 59.1,
    effective_date: "2026-01-01",
    active: true,
    carrier: "Liquid Telecom",
  },
  {
    id: "rate-007",
    destination: "South Africa - Toll Free (0800 Inbound)",
    prefix: "27800",
    destination_type: "Toll-Free",
    buy_rate_zar: 0.28,
    sell_rate_zar: 0.00,
    pulse: "1/1 (Per Second)",
    connection_fee_zar: 0.00,
    margin_percent: 0.0,
    effective_date: "2026-01-01",
    active: true,
    carrier: "Telkom Wholesale",
  },
  {
    id: "rate-008",
    destination: "United Kingdom & United States Tier 1",
    prefix: "44, 1",
    destination_type: "International Tier 1",
    buy_rate_zar: 0.35,
    sell_rate_zar: 0.85,
    pulse: "60/60 (Per Minute)",
    connection_fee_zar: 0.15,
    margin_percent: 58.8,
    effective_date: "2026-01-01",
    active: true,
    carrier: "Twilio Global",
  },
  {
    id: "rate-009",
    destination: "Global Satellite / Inmarsat / Iridium (Barred)",
    prefix: "881, 882, 870",
    destination_type: "High-Risk Satellite",
    buy_rate_zar: 28.50,
    sell_rate_zar: 55.00,
    pulse: "60/60 (Per Minute)",
    connection_fee_zar: 5.00,
    margin_percent: 48.2,
    effective_date: "2026-01-01",
    active: false, // Default barred for fraud prevention
    carrier: "Telkom Wholesale",
  },
]

export async function GET(req: NextRequest) {
  const blocked = simulatedTelephonyGuard(req)
  if (blocked) return blocked
  const url = new URL(req.url)
  const search = url.searchParams.get("search")?.toLowerCase()

  let results = [...rateCards]
  if (search) {
    results = results.filter(
      (r) =>
        r.destination.toLowerCase().includes(search) ||
        r.prefix.includes(search) ||
        r.carrier.toLowerCase().includes(search)
    )
  }

  const activeCount = rateCards.filter((r) => r.active).length
  const avgMargin = +(
    rateCards.reduce((acc, r) => acc + r.margin_percent, 0) / (rateCards.length || 1)
  ).toFixed(1)

  return NextResponse.json({
    rate_cards: results,
    stats: {
      total_rate_cards: rateCards.length,
      active_destinations: activeCount,
      avg_margin_percent: avgMargin,
      pulse_engine: "ASTPP Real-Time 1-second pulse rating with 15% SA VAT",
      barred_prefixes: ["881 (Iridium)", "870 (Inmarsat)", "232 (Sierra Leone Premium)"],
    },
  })
}

export async function POST(req: NextRequest) {
  const blocked = simulatedTelephonyGuard(req)
  if (blocked) return blocked
  try {
    const body = await req.json()
    const { destination, prefix, destination_type, buy_rate_zar, sell_rate_zar, pulse, connection_fee_zar, carrier, active } = body

    if (!destination || !prefix || buy_rate_zar === undefined || sell_rate_zar === undefined) {
      return NextResponse.json({ error: "Missing required fields (destination, prefix, buy/sell rate)" }, { status: 400 })
    }

    const margin_percent = +(((sell_rate_zar - buy_rate_zar) / (sell_rate_zar || 1)) * 100).toFixed(1)

    const newRate: AstppRateCard = {
      id: `rate-${Date.now()}`,
      destination,
      prefix,
      destination_type: destination_type || "Local Mobile",
      buy_rate_zar: Number(buy_rate_zar),
      sell_rate_zar: Number(sell_rate_zar),
      pulse: pulse || "1/1 (Per Second)",
      connection_fee_zar: Number(connection_fee_zar) || 0,
      margin_percent,
      effective_date: new Date().toISOString().split("T")[0],
      active: active !== undefined ? active : true,
      carrier: carrier || "Liquid Telecom",
    }

    rateCards.unshift(newRate)
    return NextResponse.json({ success: true, rate_card: newRate })
  } catch (err: any) {
    return NextResponse.json({ error: err.message || "Failed to create rate card" }, { status: 500 })
  }
}

export async function DELETE(req: NextRequest) {
  const blocked = simulatedTelephonyGuard(req)
  if (blocked) return blocked
  const url = new URL(req.url)
  const id = url.searchParams.get("id")
  if (!id) return NextResponse.json({ error: "Missing rate card id" }, { status: 400 })

  rateCards = rateCards.filter((r) => r.id !== id)
  return NextResponse.json({ success: true, remaining: rateCards.length })
}
