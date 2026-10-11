"use client"

/**
 * Supplier payments for purchase orders: a Payments dialog per PO (paid from the tenant's funded payout
 * wallet) and a supplier Bank details dialog. The bank account number is typed once, sent once and never
 * shown again; only "ending 1234" is displayed. The server enforces roles; its messages are shown as returned.
 */

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Note } from "@/components/modules/billing/shared"
import { listGatewayBanks, type GatewayBank } from "@/lib/billing-api"
import {
  getPoPayments,
  getSupplierBankDetails,
  payPurchaseOrder,
  saveSupplierBankDetails,
  syncPoPayments,
  type PoPayment,
  type PoPayments,
  type PoWalletShortfall,
  type SupplierBankDetails,
} from "@/lib/inventory-api"
import { fmtMoney } from "@/lib/money"
import type { Loadable } from "@/lib/service-state"

const PAYABLE = new Set(["approved", "sent", "partially_received", "received"])
const payTone = (s: string) => (s === "paid" ? "badge-success" : s === "failed" ? "badge-danger" : "badge-warning")
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

interface PoLite {
  id: string
  po_number: string
  status: string
  supplier_id: string
}

export function PoPaymentsDialog({ po, supplierName, open, onClose }: { po: PoLite | null; supplierName: string; open: boolean; onClose: () => void }) {
  const [data, setData] = useState<Loadable<PoPayments>>({ state: "loading" })
  const [bank, setBank] = useState<Loadable<SupplierBankDetails>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const [payOpen, setPayOpen] = useState(false)
  const [bankOpen, setBankOpen] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [msg, setMsg] = useState<{ tone: "error" | "success" | "info"; text: string } | null>(null)
  const reload = useCallback(() => setTick((t) => t + 1), [])

  const poId = po?.id
  const payable = !!po && PAYABLE.has(po.status)

  useEffect(() => {
    if (!open || !poId || !po) return
    let off = false
    setData({ state: "loading" })
    setBank({ state: "loading" })
    getPoPayments(poId).then((l) => !off && setData(l))
    getSupplierBankDetails(po.supplier_id).then((l) => !off && setBank(l))
    return () => {
      off = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, poId, tick])

  useEffect(() => {
    if (open) setMsg(null)
  }, [open, poId])

  const rows = data.state === "ready" ? (data.data.payments ?? []) : []
  const inFlight = rows.some((p) => p.status === "pending" || p.status === "processing")

  const sync = async () => {
    if (!poId) return
    setSyncing(true)
    setMsg(null)
    const r = await syncPoPayments(poId)
    setSyncing(false)
    if (r.ok) reload()
    else setMsg({ tone: "error", text: r.message ?? "Could not refresh the payment status." })
  }

  return (
    <>
      <Dialog open={open && !payOpen && !bankOpen} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Payments — {po?.po_number}</DialogTitle>
            <DialogDescription>{supplierName}</DialogDescription>
          </DialogHeader>

          {!payable && <Note tone="info">Approve the purchase order before paying. Payments are read-only until then.</Note>}
          {msg && <Note tone={msg.tone}>{msg.text}</Note>}

          {data.state === "loading" ? (
            <div className="h-24 animate-pulse rounded-lg bg-muted/50" aria-label="Loading" />
          ) : data.state !== "ready" ? (
            <div className="space-y-2 rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
              <p>{data.state === "denied" ? "Not permitted: payments are visible to purchasing managers only." : "Payments could not be loaded."}</p>
              <Button size="sm" variant="outline" onClick={reload}>
                Retry
              </Button>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-2 text-sm">
                <Tile k="Order total" v={fmtMoney(data.data.po_total_zar)} />
                <Tile k="Paid" v={fmtMoney(data.data.paid_zar)} />
                <Tile k="Outstanding" v={fmtMoney(data.data.outstanding_zar)} />
              </div>
              {rows.length === 0 ? (
                <p className="rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted-foreground">No payments made yet.</p>
              ) : (
                <div className="overflow-x-auto rounded-md border border-border">
                  <table className="w-full text-sm">
                    <thead className="bg-secondary/40 text-left text-xs text-muted-foreground">
                      <tr>
                        <th className="px-3 py-2">Date</th>
                        <th className="px-3 py-2">Invoice ref</th>
                        <th className="px-3 py-2">Status</th>
                        <th className="px-3 py-2 text-right">Amount</th>
                        <th className="px-3 py-2 text-right">Fee</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((p: PoPayment) => (
                        <tr key={p.id} className="border-t border-border">
                          <td className="px-3 py-2">{new Date(p.created_at).toLocaleDateString("en-ZA")}</td>
                          <td className="px-3 py-2 text-muted-foreground">{p.supplier_invoice_ref || "—"}</td>
                          <td className="px-3 py-2">
                            <Badge className={payTone(p.status)}>{cap(p.status)}</Badge>
                            {p.status === "failed" && p.message && <span className="mt-1 block text-[11px] text-red-400">{p.message}</span>}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(p.amount_zar)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(p.fee_zar)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-secondary/20 px-3 py-2 text-sm">
            <span className="text-muted-foreground">
              Supplier bank account:{" "}
              <span className="text-foreground">
                {bank.state === "ready" && bank.data.configured ? `ending ${bank.data.account_last4} (${bank.data.account_name})` : bank.state === "loading" ? "…" : bank.state === "ready" ? "Not set" : "Unknown"}
              </span>
            </span>
            <Button size="sm" variant="outline" onClick={() => setBankOpen(true)}>
              {bank.state === "ready" && bank.data.configured ? "Replace" : "Set"}
            </Button>
          </div>

          <DialogFooter className="gap-2">
            {inFlight && (
              <Button variant="outline" disabled={syncing} onClick={sync}>
                {syncing ? "Refreshing…" : "Refresh status"}
              </Button>
            )}
            <Button disabled={!payable || data.state !== "ready" || data.data.outstanding_zar <= 0} onClick={() => setPayOpen(true)}>
              Pay supplier
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {po && data.state === "ready" && (
        <PayDialog
          poId={po.id}
          open={open && payOpen}
          outstanding={data.data.outstanding_zar}
          supplierName={supplierName}
          onClose={() => setPayOpen(false)}
          onDone={(m) => {
            setMsg(m)
            reload()
          }}
        />
      )}
      {po && (
        <SupplierBankDialog
          supplierId={po.supplier_id}
          supplierName={supplierName}
          open={open && bankOpen}
          onClose={() => setBankOpen(false)}
          onSaved={(b) => setBank({ state: "ready", data: b })}
        />
      )}
    </>
  )
}

function Tile({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-md border border-border bg-secondary/20 p-2.5">
      <p className="text-[11px] text-muted-foreground">{k}</p>
      <p className="font-semibold tabular-nums text-foreground">{v}</p>
    </div>
  )
}

function PayDialog({ poId, open, outstanding, supplierName, onClose, onDone }: { poId: string; open: boolean; outstanding: number; supplierName: string; onClose: () => void; onDone: (m: { tone: "error" | "success" | "info"; text: string }) => void }) {
  const [amount, setAmount] = useState("")
  const [ref, setRef] = useState("")
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [shortfall, setShortfall] = useState<PoWalletShortfall | null>(null)

  useEffect(() => {
    if (!open) return
    setAmount(outstanding.toFixed(2))
    setRef("")
    setConfirming(false)
    setError(null)
    setShortfall(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const n = Number(amount)
  const valid = amount.trim() !== "" && Number.isFinite(n) && n > 0 && n <= outstanding + 0.0001

  const submit = async () => {
    setBusy(true)
    setError(null)
    setShortfall(null)
    const r = await payPurchaseOrder(poId, { amount_zar: Number(n.toFixed(2)), ...(ref.trim() ? { supplier_invoice_ref: ref.trim() } : {}) })
    setBusy(false)
    if (r.ok) {
      onDone({ tone: "success", text: "Payment submitted. Use Refresh status to see when the supplier has been paid." })
      onClose()
      return
    }
    setConfirming(false)
    if (r.shortfall) setShortfall(r.shortfall)
    else if (r.status === 502 || r.status === 0) {
      setError(`${r.message ?? "The outcome is unknown."} The payment was recorded as pending: use Refresh status before paying again.`)
      onDone({ tone: "info", text: "A payment may be in progress. Use Refresh status before paying again." })
    } else setError(r.message)
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{confirming ? "Confirm payment" : "Pay supplier"}</DialogTitle>
          <DialogDescription>{supplierName}</DialogDescription>
        </DialogHeader>
        {confirming ? (
          <p className="text-sm text-muted-foreground">
            Pay {fmtMoney(n)} to {supplierName}. The money is taken from your payout wallet, plus OmniDome&apos;s fee. This cannot be undone.
          </p>
        ) : (
          <div className="space-y-3">
            <div>
              <Label htmlFor="po-pay-amount">Amount in ZAR (outstanding {fmtMoney(outstanding)})</Label>
              <Input id="po-pay-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="po-pay-ref">Supplier invoice reference (optional)</Label>
              <Input id="po-pay-ref" maxLength={100} value={ref} onChange={(e) => setRef(e.target.value)} />
            </div>
          </div>
        )}
        {shortfall && (
          <div role="alert" className="space-y-2 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm">
            <p className="font-medium text-red-300">{shortfall.message}</p>
            <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
              <span>Needed incl. fee <b className="text-foreground">{fmtMoney(shortfall.required_zar)}</b></span>
              <span>In wallet <b className="text-foreground">{fmtMoney(shortfall.balance_zar)}</b></span>
              <span>Short by <b className="text-foreground">{fmtMoney(shortfall.shortfall_zar)}</b></span>
              <span>Fee <b className="text-foreground">{fmtMoney(shortfall.fee_zar)}</b></span>
            </div>
            <Button asChild size="sm">
              <Link href="/dashboard?section=billing&sub=payout-wallet">Fund the payout wallet</Link>
            </Button>
          </div>
        )}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={() => (confirming ? setConfirming(false) : onClose())}>
            {confirming ? "Back" : "Cancel"}
          </Button>
          {confirming ? (
            <Button disabled={busy} onClick={submit}>
              {busy ? "Paying…" : `Pay ${fmtMoney(n)}`}
            </Button>
          ) : (
            <Button disabled={!valid} onClick={() => setConfirming(true)}>
              Continue
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function SupplierBankDialog({ supplierId, supplierName, open, onClose, onSaved }: { supplierId: string | null; supplierName: string; open: boolean; onClose: () => void; onSaved?: (b: SupplierBankDetails) => void }) {
  const [current, setCurrent] = useState<Loadable<SupplierBankDetails>>({ state: "loading" })
  const [banks, setBanks] = useState<GatewayBank[] | null>(null)
  const [code, setCode] = useState("")
  const [name, setName] = useState("")
  const [account, setAccount] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!open || !supplierId) return
    let off = false
    setCurrent({ state: "loading" })
    setCode("")
    setName("")
    setAccount("")
    setError(null)
    setSaved(false)
    getSupplierBankDetails(supplierId).then((l) => !off && setCurrent(l))
    // The bank list is admin-tier in billing; on a 403 we fall back to a free-text bank code.
    listGatewayBanks().then((l) => !off && setBanks(l.state === "ready" ? (l.data.banks ?? []) : null))
    return () => {
      off = true
    }
  }, [open, supplierId])

  const valid = code.trim() !== "" && name.trim() !== "" && /^\d{6,17}$/.test(account)

  const submit = async () => {
    if (!supplierId) return
    setBusy(true)
    setError(null)
    const r = await saveSupplierBankDetails(supplierId, { bank_code: code.trim(), account_name: name.trim(), account_number: account })
    setBusy(false)
    // The account number is not kept once sent.
    setAccount("")
    if (r.ok && r.data) {
      setCurrent({ state: "ready", data: r.data })
      setSaved(true)
      onSaved?.(r.data)
    } else if (r.status === 409) setError(r.message ?? "This supplier has a payment in progress. Try again once it completes.")
    else setError(r.message)
  }

  const cur = current.state === "ready" ? current.data : null
  return (
    <Dialog open={open} onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Bank details — {supplierName}</DialogTitle>
          <DialogDescription>Where this supplier is paid.</DialogDescription>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Current: <span className="text-foreground">{current.state === "loading" ? "…" : cur?.configured ? `Account ending ${cur.account_last4} (${cur.account_name})` : cur ? "Not set" : "Unavailable"}</span>
        </p>
        {saved ? (
          <Note tone="success">Bank details saved.</Note>
        ) : (
          <div className="space-y-3">
            <Note tone="info">The account number is sent securely and is not stored. Only the last 4 digits are kept for display.</Note>
            <div>
              <Label htmlFor="sup-bank">Bank</Label>
              {banks && banks.length > 0 ? (
                <select id="sup-bank" className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm" value={code} onChange={(e) => setCode(e.target.value)}>
                  <option value="">Select a bank</option>
                  {banks.map((b) => (
                    <option key={b.code} value={b.code}>
                      {b.name}
                    </option>
                  ))}
                </select>
              ) : (
                <>
                  <Input id="sup-bank" value={code} onChange={(e) => setCode(e.target.value)} placeholder="Bank code" />
                  <p className="mt-1 text-[11px] text-muted-foreground">The bank list is not available to you, so enter the bank code (for example 632005).</p>
                </>
              )}
            </div>
            <div>
              <Label htmlFor="sup-acc-name">Account name</Label>
              <Input id="sup-acc-name" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="sup-acc-no">Account number (digits only)</Label>
              <Input id="sup-acc-no" inputMode="numeric" autoComplete="off" maxLength={17} value={account} onChange={(e) => setAccount(e.target.value.replace(/\D/g, ""))} />
            </div>
          </div>
        )}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={onClose}>
            {saved ? "Done" : "Cancel"}
          </Button>
          {!saved && (
            <Button disabled={!valid || busy} onClick={submit}>
              {busy ? "Saving…" : "Save"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
