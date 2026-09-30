import { NextRequest, NextResponse } from "next/server"
import { simulatedTelephonyGuard } from "@/lib/call-center-guard"

export interface VoipInvoiceItem {
  id: string
  invoice_number: string
  account_code: string
  customer_name: string
  billing_period: string
  total_calls: number
  total_billable_minutes: number
  subtotal_zar: number
  vat_zar: number // 15% South African VAT
  total_amount_zar: number
  carrier_wholesale_cost_zar: number
  net_margin_zar: number
  margin_percent: number
  payment_status: "PAID" | "PENDING_DEBIT_ORDER" | "OVERDUE"
  finance_ledger_ref: string
  cdr_breakdown: {
    local_mobile_zar: number
    national_geo_zar: number
    international_zar: number
  }
}

let generatedInvoices: VoipInvoiceItem[] = [
  {
    id: "inv-voip-001",
    invoice_number: "INV-VOIP-2026-0901",
    account_code: "CUST-88129",
    customer_name: "Sandton Financial Advisory Partners",
    billing_period: "September 2026",
    total_calls: 312,
    total_billable_minutes: 1840.5,
    subtotal_zar: 828.23,
    vat_zar: 124.23,
    total_amount_zar: 952.46,
    carrier_wholesale_cost_zar: 368.10,
    net_margin_zar: 460.13,
    margin_percent: 55.6,
    payment_status: "PENDING_DEBIT_ORDER",
    finance_ledger_ref: "LEDGER-GL-4010-VOIP-REV",
    cdr_breakdown: {
      local_mobile_zar: 540.20,
      national_geo_zar: 240.10,
      international_zar: 47.93,
    },
  },
  {
    id: "inv-voip-002",
    invoice_number: "INV-VOIP-2026-0902",
    account_code: "CUST-39014",
    customer_name: "Sandton MedClinic Emergency Dispatch",
    billing_period: "September 2026",
    total_calls: 540,
    total_billable_minutes: 3290.0,
    subtotal_zar: 1250.20,
    vat_zar: 187.53,
    total_amount_zar: 1437.73,
    carrier_wholesale_cost_zar: 512.40,
    net_margin_zar: 737.80,
    margin_percent: 59.0,
    payment_status: "PAID",
    finance_ledger_ref: "LEDGER-GL-4010-VOIP-REV",
    cdr_breakdown: {
      local_mobile_zar: 720.00,
      national_geo_zar: 490.20,
      international_zar: 40.00,
    },
  },
  {
    id: "inv-voip-003",
    invoice_number: "INV-VOIP-2026-0903",
    account_code: "CUST-99201",
    customer_name: "Pretoria High School Campus VoIP",
    billing_period: "September 2026",
    total_calls: 180,
    total_billable_minutes: 980.2,
    subtotal_zar: 412.50,
    vat_zar: 61.88,
    total_amount_zar: 474.38,
    carrier_wholesale_cost_zar: 172.00,
    net_margin_zar: 240.50,
    margin_percent: 58.3,
    payment_status: "PENDING_DEBIT_ORDER",
    finance_ledger_ref: "LEDGER-GL-4010-VOIP-REV",
    cdr_breakdown: {
      local_mobile_zar: 290.00,
      national_geo_zar: 122.50,
      international_zar: 0.00,
    },
  },
]

export async function GET(req: NextRequest) {
  const blocked = simulatedTelephonyGuard(req)
  if (blocked) return blocked
  const totalBilled = generatedInvoices.reduce((acc, inv) => acc + inv.total_amount_zar, 0)
  const totalMargin = generatedInvoices.reduce((acc, inv) => acc + inv.net_margin_zar, 0)
  const totalMinutes = generatedInvoices.reduce((acc, inv) => acc + inv.total_billable_minutes, 0)

  return NextResponse.json({
    invoices: generatedInvoices,
    stats: {
      total_invoices_generated: generatedInvoices.length,
      total_billed_zar: +totalBilled.toFixed(2),
      total_net_margin_zar: +totalMargin.toFixed(2),
      total_rated_minutes: +totalMinutes.toFixed(1),
      vat_rate: "15% South African VAT (SARS compliant)",
      finance_sync_status: "SYNCED WITH FINANCE & BILLING SERVICES (services/billing & services/finance)",
    },
  })
}

export async function POST(req: NextRequest) {
  const blocked = simulatedTelephonyGuard(req)
  if (blocked) return blocked
  try {
    const body = await req.json()
    const { action } = body

    if (action === "SYNC_TO_FINANCE") {
      // Simulate pushing invoice batch to services/billing and services/finance
      const totalAmount = generatedInvoices.reduce((acc, inv) => acc + inv.total_amount_zar, 0)
      return NextResponse.json({
        success: true,
        message: `Successfully posted batch of ${generatedInvoices.length} VoIP invoices (R ${totalAmount.toFixed(2)}) to General Ledger GL-4010 (Voice & Interconnect Revenue).`,
        synced_at: new Date().toISOString(),
        target_service: "services/finance (Port 8008) & services/billing (Port 8003)",
        status: "COMMITTED_IN_LEDGER",
      })
    }

    if (action === "GENERATE_CUSTOMER_INVOICE") {
      const { account_code, customer_name, minutes, subtotal } = body
      const sub = Number(subtotal) || 500
      const vat = +(sub * 0.15).toFixed(2)
      const wholesale = +(sub * 0.42).toFixed(2)
      const margin = +(sub - wholesale).toFixed(2)

      const newInv: VoipInvoiceItem = {
        id: `inv-voip-${Date.now()}`,
        invoice_number: `INV-VOIP-2026-090${generatedInvoices.length + 1}`,
        account_code: account_code || "CUST-MANUAL",
        customer_name: customer_name || "Enterprise Customer",
        billing_period: "September 2026",
        total_calls: Math.floor(Math.random() * 80 + 20),
        total_billable_minutes: Number(minutes) || 1200,
        subtotal_zar: sub,
        vat_zar: vat,
        total_amount_zar: +(sub + vat).toFixed(2),
        carrier_wholesale_cost_zar: wholesale,
        net_margin_zar: margin,
        margin_percent: +((margin / sub) * 100).toFixed(1),
        payment_status: "PENDING_DEBIT_ORDER",
        finance_ledger_ref: "LEDGER-GL-4010-VOIP-REV",
        cdr_breakdown: {
          local_mobile_zar: +(sub * 0.65).toFixed(2),
          national_geo_zar: +(sub * 0.30).toFixed(2),
          international_zar: +(sub * 0.05).toFixed(2),
        },
      }

      generatedInvoices.unshift(newInv)
      return NextResponse.json({ success: true, invoice: newInv })
    }

    return NextResponse.json({ error: "Unknown action" }, { status: 400 })
  } catch (err: any) {
    return NextResponse.json({ error: err.message || "Failed to sync billing with finance" }, { status: 500 })
  }
}
