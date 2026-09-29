"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  CreditCard,
  DollarSign,
  TrendingUp,
  ShieldAlert,
  Plus,
  Trash2,
  RefreshCw,
  Search,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  FileText,
  Send,
  Building2,
  Wallet,
  Layers,
} from "lucide-react"
import type { AstppRateCard } from "@/app/api/call-center/rates/route"
import type { VoipInvoiceItem } from "@/app/api/call-center/billing-sync/route"

export function AstppBillingView() {
  const [rates, setRates] = useState<AstppRateCard[]>([])
  const [invoices, setInvoices] = useState<VoipInvoiceItem[]>([])
  const [rateStats, setRateStats] = useState<any>(null)
  const [invoiceStats, setInvoiceStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [syncingFinance, setSyncingFinance] = useState(false)

  // Modals
  const [addRateModal, setAddRateModal] = useState(false)
  const [addInvoiceModal, setAddInvoiceModal] = useState(false)

  // Add Rate Form
  const [formDest, setFormDest] = useState("")
  const [formPrefix, setFormPrefix] = useState("")
  const [formBuyRate, setFormBuyRate] = useState(0.20)
  const [formSellRate, setFormSellRate] = useState(0.45)
  const [formPulse, setFormPulse] = useState<AstppRateCard["pulse"]>("1/1 (Per Second)")
  const [formCarrier, setFormCarrier] = useState<AstppRateCard["carrier"]>("Liquid Telecom")

  // Add Invoice Form
  const [invAccount, setInvAccount] = useState("CUST-NEW-01")
  const [invName, setInvName] = useState("Cape Town Metro Enterprises")
  const [invMinutes, setInvMinutes] = useState(1400)
  const [invSubtotal, setInvSubtotal] = useState(650)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 4000)
  }

  const fetchData = async () => {
    try {
      setLoading(true)
      const [rateRes, invRes] = await Promise.all([
        fetch(`/api/call-center/rates${search ? `?search=${encodeURIComponent(search)}` : ""}`),
        fetch("/api/call-center/billing-sync"),
      ])

      if (rateRes.ok) {
        const rateData = await rateRes.json()
        setRates(rateData.rate_cards || [])
        setRateStats(rateData.stats || null)
      }

      if (invRes.ok) {
        const invData = await invRes.json()
        setInvoices(invData.invoices || [])
        setInvoiceStats(invData.stats || null)
      }
    } catch (err) {
      console.error("Failed to fetch ASTPP billing data", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [search])

  const handleCreateRate = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await fetch("/api/call-center/rates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          destination: formDest,
          prefix: formPrefix,
          buy_rate_zar: Number(formBuyRate),
          sell_rate_zar: Number(formSellRate),
          pulse: formPulse,
          carrier: formCarrier,
        }),
      })
      if (res.ok) {
        showToast("ASTPP Rate Card Created!")
        setAddRateModal(false)
        setFormDest("")
        setFormPrefix("")
        fetchData()
      }
    } catch {
      showToast("Failed to create rate card")
    }
  }

  const handleDeleteRate = async (id: string) => {
    if (!confirm("Remove this rate card?")) return
    try {
      const res = await fetch(`/api/call-center/rates?id=${id}`, { method: "DELETE" })
      if (res.ok) {
        showToast("Rate Card Removed")
        fetchData()
      }
    } catch {
      showToast("Failed to remove rate card")
    }
  }

  const handleSyncFinance = async () => {
    try {
      setSyncingFinance(true)
      const res = await fetch("/api/call-center/billing-sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "SYNC_TO_FINANCE" }),
      })
      if (res.ok) {
        const data = await res.json()
        showToast(data.message || "VoIP Invoices successfully synced to General Ledger!")
      }
    } catch {
      showToast("Sync failed")
    } finally {
      setSyncingFinance(false)
    }
  }

  const handleCreateInvoice = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await fetch("/api/call-center/billing-sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "GENERATE_CUSTOMER_INVOICE",
          account_code: invAccount,
          customer_name: invName,
          minutes: Number(invMinutes),
          subtotal: Number(invSubtotal),
        }),
      })
      if (res.ok) {
        showToast("Itemized Customer VoIP Invoice Generated!")
        setAddInvoiceModal(false)
        fetchData()
      }
    } catch {
      showToast("Failed to generate invoice")
    }
  }

  return (
    <div className="space-y-6">
      {/* Toast */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 rounded-lg bg-emerald-600 px-4 py-3 text-white shadow-xl flex items-center gap-2 border border-emerald-400">
          <CheckCircle2 className="h-5 w-5" />
          <span className="text-sm font-semibold">{toastMessage}</span>
        </div>
      )}

      {/* Header Banner */}
      <div className="rounded-xl border border-emerald-500/40 bg-gradient-to-r from-emerald-950/40 via-background to-teal-950/30 p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <span className="flex h-3 w-3 rounded-full bg-emerald-400 shadow-sm" />
              <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
                ASTPP VoIP Billing, Rating &amp; Fraud Shield
              </h2>
              <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-xs">
                Open-Source Telecom Billing
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Real-time per-second pulse rating, multi-carrier wholesale rate cards (Vodacom, MTN, Telkom, Liquid), automated SARS 15% VAT invoicing, and Finance GL ledger integration.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleSyncFinance}
              disabled={syncingFinance}
              className="gap-1.5 text-xs border-emerald-500/50 text-emerald-400 hover:bg-emerald-500/10 font-semibold"
            >
              <Send className={`h-3.5 w-3.5 ${syncingFinance ? "animate-spin" : ""}`} />
              {syncingFinance ? "Posting to GL…" : "Sync to Finance & Billing"}
            </Button>
            <Button
              size="sm"
              onClick={() => setAddRateModal(true)}
              className="gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 text-white font-medium"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Rate Card
            </Button>
          </div>
        </div>

        {/* Stats Row */}
        <div className="mt-4 pt-4 border-t border-border/60 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div>
            <span className="text-muted-foreground block text-[11px]">Total VoIP Billed (Sep)</span>
            <strong className="text-lg font-bold text-foreground">
              R {invoiceStats?.total_billed_zar?.toFixed(2) || "2,864.57"}
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Net Margin (ZAR)</span>
            <strong className="text-lg font-bold text-emerald-400">
              R {invoiceStats?.total_net_margin_zar?.toFixed(2) || "1,438.43"}
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Rated Minutes</span>
            <strong className="text-lg font-bold text-cyan-400">
              {invoiceStats?.total_rated_minutes || "6,110.7"} min
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Tax &amp; VAT Rate</span>
            <strong className="text-lg font-bold text-purple-400">15% SA VAT</strong>
          </div>
        </div>
      </div>

      {/* ASTPP Rate Cards Table */}
      <Card className="border-border bg-card/80">
        <CardHeader className="pb-3 border-b border-border/50">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <CreditCard className="h-4 w-4 text-emerald-400" />
                South African &amp; International Telecom Rate Tables
              </CardTitle>
              <CardDescription className="text-xs">
                Least Cost Routing (LCR) buy/sell tariffs with custom per-second (1/1) pulse increments and wholesale carrier allocation.
              </CardDescription>
            </div>
            <div className="relative w-56">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Filter destination, prefix…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-8 pl-8 text-xs bg-background/50"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="rounded-lg border border-border overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/40 text-muted-foreground uppercase text-[10px] tracking-wider border-b border-border">
                <tr>
                  <th className="p-3">Destination &amp; Route</th>
                  <th className="p-3">Dial Prefix</th>
                  <th className="p-3">Wholesale Carrier</th>
                  <th className="p-3 text-right">Buy Rate (ZAR)</th>
                  <th className="p-3 text-right">Sell Rate (ZAR)</th>
                  <th className="p-3 text-right">Gross Margin</th>
                  <th className="p-3 text-center">Pulse</th>
                  <th className="p-3 text-center">Status</th>
                  <th className="p-3 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {rates.map((rate) => (
                  <tr key={rate.id} className="hover:bg-muted/20 transition-colors">
                    <td className="p-3">
                      <div className="font-semibold text-foreground">{rate.destination}</div>
                      <Badge variant="outline" className="text-[10px] mt-0.5 border-border">
                        {rate.destination_type}
                      </Badge>
                    </td>

                    <td className="p-3 font-mono text-muted-foreground font-semibold text-xs">
                      {rate.prefix}
                    </td>

                    <td className="p-3 text-muted-foreground font-medium text-xs">
                      {rate.carrier}
                    </td>

                    <td className="p-3 text-right font-mono text-foreground">
                      R {rate.buy_rate_zar.toFixed(2)}/m
                    </td>

                    <td className="p-3 text-right font-mono font-bold text-foreground">
                      R {rate.sell_rate_zar.toFixed(2)}/m
                    </td>

                    <td className="p-3 text-right font-mono font-bold text-emerald-400">
                      {rate.margin_percent}%
                    </td>

                    <td className="p-3 text-center text-[11px] text-muted-foreground font-mono">
                      {rate.pulse}
                    </td>

                    <td className="p-3 text-center">
                      <Badge
                        variant="outline"
                        className={
                          rate.active
                            ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-[10px]"
                            : "border-red-500/40 text-red-400 bg-red-500/10 text-[10px]"
                        }
                      >
                        {rate.active ? "ACTIVE" : "BARRED"}
                      </Badge>
                    </td>

                    <td className="p-3 text-center">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDeleteRate(rate.id)}
                        className="h-7 w-7 p-0 text-muted-foreground hover:text-red-400"
                        title="Remove Rate"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Invoicing & Finance Integration Panel */}
      <Card className="border-border bg-card/80">
        <CardHeader className="pb-3 border-b border-border/50">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <FileText className="h-4 w-4 text-cyan-400" />
                Customer VoIP Invoicing &amp; General Ledger Integration
              </CardTitle>
              <CardDescription className="text-xs">
                Automated monthly call usage invoices with SARS 15% VAT and direct balance reconciliation into services/finance GL-4010.
              </CardDescription>
            </div>
            <Button
              size="sm"
              onClick={() => setAddInvoiceModal(true)}
              className="gap-1.5 text-xs bg-cyan-600 hover:bg-cyan-500 text-white font-medium"
            >
              <Plus className="h-3.5 w-3.5" />
              Generate Customer Invoice
            </Button>
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="rounded-lg border border-border overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/40 text-muted-foreground uppercase text-[10px] tracking-wider border-b border-border">
                <tr>
                  <th className="p-3">Invoice &amp; Customer</th>
                  <th className="p-3">Billing Period</th>
                  <th className="p-3 text-center">Calls &amp; Minutes</th>
                  <th className="p-3 text-right">Subtotal (ZAR)</th>
                  <th className="p-3 text-right">15% VAT</th>
                  <th className="p-3 text-right">Total Invoiced</th>
                  <th className="p-3 text-right">Net Margin</th>
                  <th className="p-3 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {invoices.map((inv) => (
                  <tr key={inv.id} className="hover:bg-muted/20 transition-colors">
                    <td className="p-3">
                      <div className="font-bold text-foreground font-mono">{inv.invoice_number}</div>
                      <div className="font-semibold text-foreground text-xs">{inv.customer_name}</div>
                      <div className="text-[11px] text-muted-foreground font-mono">{inv.account_code}</div>
                    </td>

                    <td className="p-3 text-muted-foreground font-medium">
                      {inv.billing_period}
                      <div className="text-[10px] text-cyan-400 font-mono">{inv.finance_ledger_ref}</div>
                    </td>

                    <td className="p-3 text-center font-mono">
                      <div className="font-semibold text-foreground">{inv.total_calls} calls</div>
                      <div className="text-[11px] text-muted-foreground">{inv.total_billable_minutes} min</div>
                    </td>

                    <td className="p-3 text-right font-mono text-foreground">
                      R {inv.subtotal_zar.toFixed(2)}
                    </td>

                    <td className="p-3 text-right font-mono text-muted-foreground">
                      R {inv.vat_zar.toFixed(2)}
                    </td>

                    <td className="p-3 text-right font-mono font-bold text-foreground text-sm">
                      R {inv.total_amount_zar.toFixed(2)}
                    </td>

                    <td className="p-3 text-right font-mono text-emerald-400 font-bold">
                      +R {inv.net_margin_zar.toFixed(2)} ({inv.margin_percent}%)
                    </td>

                    <td className="p-3 text-center">
                      <Badge
                        variant="outline"
                        className={
                          inv.payment_status === "PAID"
                            ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-[10px]"
                            : "border-amber-500/40 text-amber-400 bg-amber-500/10 text-[10px]"
                        }
                      >
                        {inv.payment_status.replace(/_/g, " ")}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Add Rate Modal */}
      {addRateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-card border border-border rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <Plus className="h-4 w-4 text-emerald-400" />
                Add ASTPP VoIP Rate Card
              </h3>
              <Button size="sm" variant="ghost" onClick={() => setAddRateModal(false)}>✕</Button>
            </div>

            <form onSubmit={handleCreateRate} className="space-y-3.5 text-xs">
              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Destination Name</label>
                <Input
                  placeholder="e.g. South Africa - MTN Fixed LTE"
                  value={formDest}
                  onChange={(e) => setFormDest(e.target.value)}
                  required
                />
              </div>

              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Dial Prefixes (Comma-separated)</label>
                <Input
                  placeholder="e.g. 2783, 2773, 2778"
                  value={formPrefix}
                  onChange={(e) => setFormPrefix(e.target.value)}
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Buy Rate (ZAR / min)</label>
                  <Input
                    type="number"
                    step="0.01"
                    value={formBuyRate}
                    onChange={(e) => setFormBuyRate(Number(e.target.value))}
                    required
                  />
                </div>
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Sell Rate (ZAR / min)</label>
                  <Input
                    type="number"
                    step="0.01"
                    value={formSellRate}
                    onChange={(e) => setFormSellRate(Number(e.target.value))}
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Pulse Increment</label>
                  <select
                    value={formPulse}
                    onChange={(e) => setFormPulse(e.target.value as any)}
                    className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value="1/1 (Per Second)">1/1 (Per Second)</option>
                    <option value="60/60 (Per Minute)">60/60 (Per Minute)</option>
                    <option value="60/1 (First Minute then Second)">60/1 (First Minute then Second)</option>
                  </select>
                </div>
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Wholesale Carrier</label>
                  <select
                    value={formCarrier}
                    onChange={(e) => setFormCarrier(e.target.value as any)}
                    className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value="Liquid Telecom">Liquid Telecom</option>
                    <option value="Telkom Wholesale">Telkom Wholesale</option>
                    <option value="Vodacom Business">Vodacom Business</option>
                    <option value="MTN Wholesale">MTN Wholesale</option>
                    <option value="Twilio Global">Twilio Global</option>
                  </select>
                </div>
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => setAddRateModal(false)}>
                  Cancel
                </Button>
                <Button type="submit" className="bg-emerald-600 hover:bg-emerald-500 text-white">
                  Save Rate Card
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Customer Invoice Modal */}
      {addInvoiceModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-card border border-border rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <FileText className="h-4 w-4 text-cyan-400" />
                Generate Customer VoIP Invoice
              </h3>
              <Button size="sm" variant="ghost" onClick={() => setAddInvoiceModal(false)}>✕</Button>
            </div>

            <form onSubmit={handleCreateInvoice} className="space-y-3.5 text-xs">
              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Account Code</label>
                <Input value={invAccount} onChange={(e) => setInvAccount(e.target.value)} required />
              </div>

              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Customer / Company Name</label>
                <Input value={invName} onChange={(e) => setInvName(e.target.value)} required />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Total Billable Minutes</label>
                  <Input
                    type="number"
                    value={invMinutes}
                    onChange={(e) => setInvMinutes(Number(e.target.value))}
                    required
                  />
                </div>
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Usage Subtotal (ZAR)</label>
                  <Input
                    type="number"
                    step="0.01"
                    value={invSubtotal}
                    onChange={(e) => setInvSubtotal(Number(e.target.value))}
                    required
                  />
                </div>
              </div>

              <p className="text-[11px] text-muted-foreground bg-muted/40 p-2.5 rounded-lg border border-border">
                💡 15% South African VAT (R {(invSubtotal * 0.15).toFixed(2)}) will automatically be calculated and appended to the invoice total (R {(invSubtotal * 1.15).toFixed(2)}).
              </p>

              <div className="pt-2 flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => setAddInvoiceModal(false)}>
                  Cancel
                </Button>
                <Button type="submit" className="bg-cyan-600 hover:bg-cyan-500 text-white">
                  Generate &amp; Register Invoice
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
