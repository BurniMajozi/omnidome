"use client"

import { useEffect, useState } from "react"
import { Plus, Send, CheckCircle2, PackageCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { DataTable, type DataColumn } from "@/components/ui/data-table"
import { PurchasingSignature } from "./purchasing-signature"
import { PoPaymentsDialog, SupplierBankDialog } from "./purchasing-payments"
import {
  type PurchaseOrder as BasePurchaseOrder,
  type Supplier,
  listSuppliers,
} from "@/lib/inventory-api"
import { inventoryCall } from "@/lib/catalogue-api"
import { evaluateDelivery, getPurchasable, type PurchasableProduct } from "@/lib/supplier-api"

type PurchaseOrder = Omit<BasePurchaseOrder, "status"> & {
  status: BasePurchaseOrder["status"] | "pending_approval" | "rejected" | "sent"
}

async function purchasingRequest<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`/svc/inventory${path}`, {
    method, cache: "no-store", headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const payload = await response.json()
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : payload.error || "Purchasing request failed")
  return payload as T
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "outline" | "destructive"> = {
  draft: "outline",
  submitted: "secondary",
  pending_approval: "secondary",
  rejected: "destructive",
  sent: "default",
  approved: "default",
  partially_received: "secondary",
  received: "default",
  cancelled: "destructive",
}

function formatZar(value: string) {
  return `R ${Number(value).toLocaleString("en-ZA", { minimumFractionDigits: 2 })}`
}

interface LineDraft {
  product_id: string        // stock item id, chosen from the products created in Product Management
  quantity_ordered: string
  unit_cost_zar: string
}

const emptyLine = (): LineDraft => ({ product_id: "", quantity_ordered: "1", unit_cost_zar: "0.00" })

interface WarehouseLite { id: string; name: string }
interface RateTarget { grId: string; poNumber: string; supplier: string; expected: string | null }

/**
 * Live procure-to-receive UI against the inventory service's purchasing
 * routes — Supplier -> PurchaseOrder (draft -> submit -> approve) ->
 * GoodsReceipt, with the same three-way-match and approval-threshold rules
 * enforced server-side. Unlike the rest of this dashboard, this section
 * reads/writes real backend state rather than canned demo data.
 */
export function PurchasingSection({approvalOnly = false}: {approvalOnly?: boolean} = {}) {
  const [pos, setPos] = useState<PurchaseOrder[]>([])
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [catalogue, setCatalogue] = useState<PurchasableProduct[]>([])        // everything stock can buy (names for receiving)
  const [offers, setOffers] = useState<PurchasableProduct[]>([])              // the same list priced for the chosen supplier
  const [warehouses, setWarehouses] = useState<WarehouseLite[]>([])
  const [expectedDelivery, setExpectedDelivery] = useState("")
  const [rateTarget, setRateTarget] = useState<RateTarget | null>(null)
  const [rating, setRating] = useState(0)
  const [ratingLate, setRatingLate] = useState("")
  const [ratingComment, setRatingComment] = useState("")
  const [receiveTarget, setReceiveTarget] = useState<PurchaseOrder | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState("")
  const [paymentsTarget, setPaymentsTarget] = useState<PurchaseOrder | null>(null)
  const [bankOpen, setBankOpen] = useState(false)
  const [bankSupplierId, setBankSupplierId] = useState("")
  const [decisionTarget, setDecisionTarget] = useState<PurchaseOrder | null>(null)
  const [signature, setSignature] = useState("")
  const [signerName, setSignerName] = useState("")
  const [comment, setComment] = useState("")
  const [receiptRef, setReceiptRef] = useState("")
  const [autoApproveLimit, setAutoApproveLimit] = useState("")

  const [supplierId, setSupplierId] = useState("")
  const [warehouseId, setWarehouseId] = useState("")
  const [lines, setLines] = useState<LineDraft[]>([emptyLine()])

  const [receiveQty, setReceiveQty] = useState<Record<string, string>>({})
  const [rejectQty, setRejectQty] = useState<Record<string, string>>({})
  const [rejectReason, setRejectReason] = useState<Record<string, string>>({})

  async function refresh() {
    setLoading(true)
  const [unitText, setUnitText] = useState<Record<string, string>>({})
    setError("")
    try {
      if (approvalOnly) await purchasingRequest("/approvals/inbox")
      const [poList, supplierList] = await Promise.all([purchasingRequest<PurchaseOrder[]>("/purchase-orders"), listSuppliers()])
      setPos(approvalOnly ? poList.filter(p => ["submitted", "pending_approval"].includes(p.status)) : poList)
      setSuppliers(supplierList)
      getPurchasable().then(setCatalogue).catch(() => setCatalogue([]))
      inventoryCall<WarehouseLite[]>("/warehouses").then(setWarehouses).catch(() => setWarehouses([]))
    } catch(cause) {setError(cause instanceof Error ? cause.message : "Purchase orders could not be loaded"); setPos([])}
    finally {setLoading(false)}
  }

  useEffect(() => {
    refresh()
    purchasingRequest<{ auto_approve_limit: string }>("/purchasing/settings")
      .then((settings) => setAutoApproveLimit(settings.auto_approve_limit))
      .catch((cause) => setError(String(cause.message || cause)))
  }, [approvalOnly])

  useEffect(() => {
    setOffers([])
    if (supplierId) getPurchasable(supplierId).then(setOffers).catch(() => setOffers([]))
  }, [supplierId])

  function pickProduct(i: number, productId: string) {
    const p = offers.find((x) => x.inventory_product_id === productId)
    const cost = p?.offer?.unit_cost ?? p?.preferred?.unit_cost ?? "0.00"
    const next = [...lines]
    next[i] = { ...next[i], product_id: productId, unit_cost_zar: String(cost), quantity_ordered: next[i].quantity_ordered === "1" && p?.offer?.moq ? String(p.offer.moq) : next[i].quantity_ordered }
    setLines(next)
    const lead = p?.offer?.lead_time_days ?? suppliers.find((s) => s.id === supplierId)?.lead_time_days
    if (!expectedDelivery && lead != null) setExpectedDelivery(new Date(Date.now() + lead * 86400000).toISOString().slice(0, 10))
  }

  async function handleCreatePo() {
    if (!supplierId || !warehouseId) return
    const items = lines
      .filter((l) => l.product_id)
      .map((l) => ({
        product_id: l.product_id,
        quantity_ordered: Number(l.quantity_ordered) || 0,
        unit_cost_zar: l.unit_cost_zar || "0",
      }))
    if (items.length === 0) return
    setError("")
    try {
      await purchasingRequest("/purchase-orders", "POST", { supplier_id: supplierId, warehouse_id: warehouseId, expected_delivery: expectedDelivery || null, items })
      setCreateOpen(false)
      setLines([emptyLine()])
      setSupplierId("")
      setWarehouseId("")
      setExpectedDelivery("")
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not create the purchase order") }
  }

  async function handleSubmit(po: PurchaseOrder) {
    setBusyId(po.id)
    setError("")
    try {
      await purchasingRequest(`/purchase-orders/${po.id}/submit`, "POST")
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Submit failed") }
    finally { setBusyId(null) }
  }

  async function handleDecision(decision: "approve" | "reject") {
    if (!decisionTarget) return
    setBusyId(decisionTarget.id)
    setError("")
    try {
      await purchasingRequest(`/purchase-orders/${decisionTarget.id}/${decision}`, "POST", {
        signer_name: signerName, signature_data: signature, comment: comment || null,
      })
      setDecisionTarget(null)
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Decision failed") }
    finally { setBusyId(null) }
  }

  async function handleCancel(po: PurchaseOrder) {
    setBusyId(po.id)
    setError("")
    try {
      await purchasingRequest(`/purchase-orders/${po.id}/cancel`, "POST")
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Cancel failed") }
    finally { setBusyId(null) }
  }

  async function saveSettings() {
    setError("")
    try {
      const settings = await purchasingRequest<{ auto_approve_limit: string }>("/purchasing/settings", "PUT", { auto_approve_limit: autoApproveLimit })
      setAutoApproveLimit(settings.auto_approve_limit)
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Settings update failed") }
  }

  async function handleReceive() {
    if (!receiveTarget) return
    const items = receiveTarget.items
  const identifiersFor = (productId: string) => catalogue.find((c) => c.inventory_product_id === productId)?.identifiers ?? []
  /** One line per accepted unit: a serial number, a MAC address, or both separated by a space or comma. */
  function parseUnits(text: string) {
    return text.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
      const parts = l.split(/[\s,;]+/).filter(Boolean)
      const mac = parts.find((x) => /^([0-9a-f]{2}[:-]?){5}[0-9a-f]{2}$/i.test(x))
      const serial = parts.find((x) => x !== mac)
      return { serial: serial ?? null, mac: mac ?? null }
    })
  }

      .filter((i) => Number(receiveQty[i.id] || 0) > 0)
      .map((i) => {
        const accepted = Number(receiveQty[i.id]) - Math.min(Number(rejectQty[i.id] || 0), Number(receiveQty[i.id]))
        const ids = identifiersFor(i.product_id)
        return {
          po_item_id: i.id, quantity_received: Number(receiveQty[i.id]),
          quantity_rejected: Math.min(Number(rejectQty[i.id] || 0), Number(receiveQty[i.id])),
          rejection_reason: Number(rejectQty[i.id] || 0) > 0 ? (rejectReason[i.id] || "").trim() || null : null,
          units: ids.length ? parseUnits(unitText[i.id] || "") : undefined,
          _accepted: accepted, _ids: ids,
        }
      })
    if (items.length === 0) return
    if (items.some((i) => i.quantity_rejected > 0 && !i.rejection_reason)) { setError("Give a reason for every rejected quantity."); return }
    setBusyId(receiveTarget.id)
    setError("")
    try {
    const short = items.find((i) => i._ids.length && (i.units?.length ?? 0) !== i._accepted)
    if (short) { setError(`Enter ${short._accepted} unit line${short._accepted === 1 ? "" : "s"} (${short._ids.join(" and ").toLowerCase()}), one per accepted unit. You have ${short.units?.length ?? 0}.`); return }
      const receipt = await purchasingRequest<{ id: string }>(`/purchase-orders/${receiveTarget.id}/goods-receipts`, "POST", { receipt_ref: receiptRef, items: items.map(({ _accepted, _ids, ...rest }) => rest) })
      const target = receiveTarget
      setReceiveTarget(null)
      setReceiveQty({})
      setRejectQty({})
      setRejectReason({})
      setReceiptRef("")
      setRating(0); setRatingLate(""); setRatingComment("")
      setRateTarget({ grId: receipt.id, poNumber: target.po_number, supplier: supplierName(target.supplier_id), expected: target.expected_delivery ?? null })
      setUnitText({})
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Receipt failed") }
    finally { setBusyId(null) }
  }

  const supplierName = (id: string) => suppliers.find((s) => s.id === id)?.name ?? id.slice(0, 8)

  const columns: DataColumn<PurchaseOrder>[] = [
    { key: "po_number", label: "PO Number" },
    { key: "supplier_id", label: "Supplier", render: (row) => supplierName(row.supplier_id) },
    {
      key: "status",
      label: "Status",
      render: (row) => (
        <Badge variant={STATUS_VARIANT[row.status] ?? "outline"}>{row.status.replace("_", " ")}</Badge>
      ),
    },
    { key: "total_zar", label: "Total", align: "right", render: (row) => formatZar(row.total_zar) },
    {
      key: "actions",
      label: "",
      render: (row) => (
        <div className="flex gap-1 justify-end">
          {row.status === "draft" && (
            <Button size="sm" variant="outline" disabled={busyId === row.id} onClick={() => handleSubmit(row)}>
              <Send className="h-3.5 w-3.5 mr-1" /> Submit
            </Button>
          )}
          {(row.status === "submitted" || row.status === "pending_approval") && (
            <Button size="sm" variant="outline" disabled={busyId === row.id} onClick={() => { setSignature(""); setComment(""); setDecisionTarget(row) }}>
              <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Review
            </Button>
          )}
          {(row.status === "approved" || row.status === "sent" || row.status === "partially_received") && (
            <Button size="sm" variant="outline" onClick={() => { setReceiveQty({}); setReceiptRef(crypto.randomUUID()); setReceiveTarget(row) }}>
              <PackageCheck className="h-3.5 w-3.5 mr-1" /> Receive
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => setPaymentsTarget(row)}>Payments</Button>
          {["draft", "submitted", "pending_approval", "approved", "rejected", "sent"].includes(row.status) && (
            <Button size="sm" variant="ghost" disabled={busyId === row.id} onClick={() => handleCancel(row)}>Cancel</Button>
          )}
        </div>
      ),
    },
  ]

  return (
    <div className="surface-card p-6">
      {error && <p role="alert" className="text-sm text-destructive mb-3">{error}</p>}
      <p className="text-sm text-muted-foreground mb-3">Review submitted orders with a signed approval before supplier dispatch.</p>
      {!approvalOnly && <div className="flex items-end gap-2 mb-4">
        <div><Label htmlFor="po-autoapprove">Autoapproval limit (ZAR including VAT; 0 disables)</Label>
          <Input id="po-autoapprove" type="number" min="0" step="0.01" value={autoApproveLimit} onChange={(event) => setAutoApproveLimit(event.target.value)} />
        </div>
        <Button variant="outline" onClick={saveSettings}>Save limit</Button>
      </div>}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h4 className="card-title">{approvalOnly ? "Pending purchase approvals" : "Purchase Orders"}</h4>
          <p className="text-sm text-muted-foreground">
            Live procure-to-receive — draft → submit → approve → receive, three-way-matched against the PO.
            Suppliers and the products you can buy are created in Product Management; stock only orders and receives them.
          </p>
        </div>
        {!approvalOnly && <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setBankOpen(true)}>Supplier bank details</Button>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" /> New Purchase Order
          </Button>
        </div>}
      </div>

      <DataTable
        columns={columns}
        rows={pos}
        loading={loading}
        emptyTitle={error ? "Purchase orders unavailable" : approvalOnly ? "No pending approvals" : "No purchase orders yet"}
        emptyDescription={error || (approvalOnly ? "Submitted orders will appear here for signed review." : "Create one to start the procure-to-receive flow.")}
      />

      <PoPaymentsDialog po={paymentsTarget} supplierName={paymentsTarget ? supplierName(paymentsTarget.supplier_id) : ""} open={!!paymentsTarget} onClose={() => setPaymentsTarget(null)} />

      {/* Supplier bank details (pick a supplier first) */}
      <Dialog open={bankOpen && !bankSupplierId} onOpenChange={(o) => !o && setBankOpen(false)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Supplier bank details</DialogTitle></DialogHeader>
          {suppliers.length === 0 ? (
            <p className="text-sm text-muted-foreground">No suppliers yet. Add a supplier first.</p>
          ) : (
            <Select value={bankSupplierId} onValueChange={setBankSupplierId}>
              <SelectTrigger><SelectValue placeholder="Select supplier" /></SelectTrigger>
              <SelectContent>{suppliers.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
            </Select>
          )}
        </DialogContent>
      </Dialog>
      <SupplierBankDialog supplierId={bankSupplierId || null} supplierName={bankSupplierId ? supplierName(bankSupplierId) : ""} open={bankOpen && !!bankSupplierId} onClose={() => { setBankOpen(false); setBankSupplierId("") }} />

      {/* Create PO */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>New Purchase Order</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Supplier</Label>
              <Select value={supplierId} onValueChange={setSupplierId}>
                <SelectTrigger><SelectValue placeholder="Select supplier" /></SelectTrigger>
                <SelectContent>
                  {suppliers.map((s) => (
                    <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Warehouse</Label>
              <Select value={warehouseId} onValueChange={setWarehouseId}>
                <SelectTrigger><SelectValue placeholder={warehouses.length ? "Select warehouse" : "No warehouses yet"} /></SelectTrigger>
                <SelectContent>{warehouses.map((w) => <SelectItem key={w.id} value={w.id}>{w.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="po-expected">Expected delivery (used to measure on-time delivery)</Label>
              <Input id="po-expected" type="date" value={expectedDelivery} onChange={(e) => setExpectedDelivery(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Line items</Label>
              {lines.map((line, i) => (
                <div key={i} className="grid grid-cols-3 gap-2">
                  <div>
                    <Select value={line.product_id} onValueChange={(v) => pickProduct(i, v)} disabled={!supplierId}>
                      <SelectTrigger><SelectValue placeholder={!supplierId ? "Choose a supplier first" : offers.length ? "Select product" : "No stock products yet"} /></SelectTrigger>
                      <SelectContent>
                        {offers.map((p) => (
                          <SelectItem key={p.inventory_product_id} value={p.inventory_product_id}>{p.product_number} · {p.name}{p.offer ? "" : " (not sourced from this supplier)"}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {(() => { const p = offers.find((x) => x.inventory_product_id === line.product_id); return p && !p.offer ? <p className="mt-1 text-[11px] text-amber-500">This supplier is not listed for the product. Add them in Product Management first.</p> : p?.offer ? <p className="mt-1 text-[11px] text-muted-foreground">{p.offer.moq ? `Minimum order ${p.offer.moq}. ` : ""}{(() => { const m = p.sources.find((s) => s.supplier_id === p.offer!.supplier_id); const alt = p.sources.filter((s) => s.supplier_id !== p.offer!.supplier_id && s.margin_pct != null).map((s) => `${s.supplier_name} ${s.margin_pct}%`); return m?.margin_pct != null ? `Margin from this supplier ${m.margin_pct}%${alt.length ? ` (others: ${alt.join(", ")})` : ""}.` : "" })()}</p> : null })()}
                  </div>
                  <Input
                    type="number" placeholder="Qty"
                    value={line.quantity_ordered}
                    onChange={(e) => {
                      const next = [...lines]; next[i] = { ...line, quantity_ordered: e.target.value }; setLines(next)
                    }}
                  />
                  <Input
                    type="number" placeholder="Unit cost (ZAR)"
                    value={line.unit_cost_zar}
                    onChange={(e) => {
                      const next = [...lines]; next[i] = { ...line, unit_cost_zar: e.target.value }; setLines(next)
                    }}
                  />
                </div>
              ))}
              <Button size="sm" variant="ghost" onClick={() => setLines([...lines, emptyLine()])}>
                <Plus className="h-3.5 w-3.5 mr-1" /> Add line
              </Button>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={handleCreatePo}>Create Draft</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Receive goods */}
      <Dialog open={!!receiveTarget} onOpenChange={(open) => !open && setReceiveTarget(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Receive Goods — {receiveTarget?.po_number}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="receipt-reference">Delivery reference (keep the same reference when retrying)</Label>
            <Input id="receipt-reference" value={receiptRef} maxLength={128} onChange={(event) => setReceiptRef(event.target.value)} />
            {receiveTarget?.items.map((item) => {
              const remaining = item.quantity_ordered - item.quantity_received
              return (
                <div key={item.id} className="space-y-1.5 rounded-md border border-border/60 p-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm">
                      <div className="font-medium">{(() => { const p = catalogue.find((c) => c.inventory_product_id === item.product_id); return p ? `${p.product_number} · ${p.name}` : `${item.product_id.slice(0, 8)}…` })()}</div>
                      <div className="text-muted-foreground">
                        {item.quantity_received}/{item.quantity_ordered} received — {remaining} outstanding
                      </div>
                    </div>
                    <Input
                      type="number"
                      className="w-24"
                      placeholder="Received"
                      aria-label="Quantity received"
                      max={remaining}
                      value={receiveQty[item.id] ?? ""}
                      onChange={(e) => setReceiveQty({ ...receiveQty, [item.id]: e.target.value })}
                    />
                  </div>
                  {Number(receiveQty[item.id] || 0) > 0 && (
                    <div className="grid grid-cols-[96px_1fr] gap-2">
                      <Input type="number" min="0" max={receiveQty[item.id]} placeholder="Rejected" aria-label="Quantity rejected" value={rejectQty[item.id] ?? ""}
                        onChange={(e) => setRejectQty({ ...rejectQty, [item.id]: e.target.value })} />
                      <Input placeholder="Reason for rejection (damaged, wrong model…)" aria-label="Rejection reason" disabled={!Number(rejectQty[item.id] || 0)}
                  {Number(receiveQty[item.id] || 0) > 0 && identifiersFor(item.product_id).length > 0 && (
                    <div className="space-y-1">
                      <Label htmlFor={`units-${item.id}`} className="text-xs text-muted-foreground">
                        {identifiersFor(item.product_id).join(" and ")} per accepted unit, one unit per line (e.g. “SN12345 AA:BB:CC:DD:EE:FF”)
                      </Label>
                      <textarea id={`units-${item.id}`} rows={3} value={unitText[item.id] ?? ""} onChange={(e) => setUnitText({ ...unitText, [item.id]: e.target.value })}
                        className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs" />
                      <div className="text-[11px] text-muted-foreground">{parseUnits(unitText[item.id] || "").length} of {Number(receiveQty[item.id]) - Math.min(Number(rejectQty[item.id] || 0), Number(receiveQty[item.id]))} units entered</div>
                    </div>
                  )}
                        value={rejectReason[item.id] ?? ""} onChange={(e) => setRejectReason({ ...rejectReason, [item.id]: e.target.value })} />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          <DialogFooter>
            <Button disabled={!receiptRef.trim() || busyId === receiveTarget?.id} onClick={handleReceive}>Record Receipt</Button>
          </DialogFooter>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        </DialogContent>
      </Dialog>

      {/* Rate the delivery: feeds the supplier scorecard in Stock and in Product Management */}
      <Dialog open={!!rateTarget} onOpenChange={(open) => !open && setRateTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Rate this delivery — {rateTarget?.supplier}</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Receipt recorded for {rateTarget?.poNumber}. How did {rateTarget?.supplier} do on packaging, accuracy, paperwork and timeliness?</p>
          <div className="flex gap-1" role="radiogroup" aria-label="Delivery rating">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} type="button" role="radio" aria-checked={rating === n} aria-label={`${n} out of 5`} onClick={() => setRating(n)}
                className={`h-10 w-10 rounded-md border text-sm font-medium ${rating === n ? "border-primary bg-primary/15 text-primary" : "border-border text-muted-foreground hover:text-foreground"}`}>{n}</button>
            ))}
          </div>
          <div className="space-y-2">
            <Input placeholder="If it was late, why? (optional)" value={ratingLate} onChange={(e) => setRatingLate(e.target.value)} aria-label="Reason it was late" />
            <Input placeholder="Comment (optional)" value={ratingComment} onChange={(e) => setRatingComment(e.target.value)} aria-label="Comment" />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRateTarget(null)}>Skip</Button>
            <Button disabled={!rating} onClick={async () => {
              if (!rateTarget) return
              try { await evaluateDelivery(rateTarget.grId, { rating, late_reason: ratingLate, comment: ratingComment }); setRateTarget(null) }
              catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save the rating") }
            }}>Save rating</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!decisionTarget} onOpenChange={(open) => !open && setDecisionTarget(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Review {decisionTarget?.po_number}</DialogTitle></DialogHeader>
          <p>{decisionTarget && formatZar(decisionTarget.total_zar)} including VAT</p>
          <Label htmlFor="po-signer">Signer name</Label>
          <Input id="po-signer" value={signerName} onChange={(event) => setSignerName(event.target.value)} />
          <Label>Draw signature</Label>
          <PurchasingSignature onChange={setSignature} />
          <Label htmlFor="po-decision-comment">Comment (required for rejection)</Label>
          <Input id="po-decision-comment" value={comment} onChange={(event) => setComment(event.target.value)} />
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button variant="destructive" disabled={!signature || !signerName.trim() || !comment.trim() || busyId === decisionTarget?.id} onClick={() => handleDecision("reject")}>Reject</Button>
            <Button disabled={!signature || !signerName.trim() || busyId === decisionTarget?.id} onClick={() => handleDecision("approve")}>Approve</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
