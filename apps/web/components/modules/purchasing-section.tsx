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
import {
  type PurchaseOrder as BasePurchaseOrder,
  type Supplier,
  type PurchaseOrderItemInput,
  listPurchaseOrders,
  listSuppliers,
  createSupplier,
  createPurchaseOrder,
} from "@/lib/inventory-api"

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
  product_id: string
  quantity_ordered: string
  unit_cost_zar: string
}

const emptyLine = (): LineDraft => ({ product_id: "", quantity_ordered: "1", unit_cost_zar: "0.00" })

/**
 * Live procure-to-receive UI against the inventory service's purchasing
 * routes — Supplier -> PurchaseOrder (draft -> submit -> approve) ->
 * GoodsReceipt, with the same three-way-match and approval-threshold rules
 * enforced server-side. Unlike the rest of this dashboard, this section
 * reads/writes real backend state rather than canned demo data.
 */
export function PurchasingSection() {
  const [pos, setPos] = useState<PurchaseOrder[]>([])
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [newSupplierOpen, setNewSupplierOpen] = useState(false)
  const [receiveTarget, setReceiveTarget] = useState<PurchaseOrder | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState("")
  const [decisionTarget, setDecisionTarget] = useState<PurchaseOrder | null>(null)
  const [signature, setSignature] = useState("")
  const [signerName, setSignerName] = useState("")
  const [comment, setComment] = useState("")
  const [receiptRef, setReceiptRef] = useState("")
  const [autoApproveLimit, setAutoApproveLimit] = useState("")

  const [supplierId, setSupplierId] = useState("")
  const [warehouseId, setWarehouseId] = useState("")
  const [lines, setLines] = useState<LineDraft[]>([emptyLine()])

  const [newSupplierCode, setNewSupplierCode] = useState("")
  const [newSupplierName, setNewSupplierName] = useState("")

  const [receiveQty, setReceiveQty] = useState<Record<string, string>>({})

  async function refresh() {
    setLoading(true)
    const [poList, supplierList] = await Promise.all([listPurchaseOrders(), listSuppliers()])
    setPos(poList)
    setSuppliers(supplierList)
    setLoading(false)
  }

  useEffect(() => {
    refresh()
    purchasingRequest<{ auto_approve_limit: string }>("/purchasing/settings")
      .then((settings) => setAutoApproveLimit(settings.auto_approve_limit))
      .catch((cause) => setError(String(cause.message || cause)))
  }, [])

  async function handleCreatePo() {
    if (!supplierId || !warehouseId) return
    const items: PurchaseOrderItemInput[] = lines
      .filter((l) => l.product_id)
      .map((l) => ({
        product_id: l.product_id,
        quantity_ordered: Number(l.quantity_ordered) || 0,
        unit_cost_zar: l.unit_cost_zar || "0",
      }))
    if (items.length === 0) return
    const created = await createPurchaseOrder({ supplier_id: supplierId, warehouse_id: warehouseId, items })
    if (created) {
      setCreateOpen(false)
      setLines([emptyLine()])
      setSupplierId("")
      setWarehouseId("")
      await refresh()
    }
  }

  async function handleCreateSupplier() {
    if (!newSupplierCode || !newSupplierName) return
    const created = await createSupplier({ code: newSupplierCode, name: newSupplierName })
    if (created) {
      setNewSupplierOpen(false)
      setNewSupplierCode("")
      setNewSupplierName("")
      await refresh()
    }
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
      .filter((i) => Number(receiveQty[i.id] || 0) > 0)
      .map((i) => ({ po_item_id: i.id, quantity_received: Number(receiveQty[i.id]) }))
    if (items.length === 0) return
    setBusyId(receiveTarget.id)
    setError("")
    try {
      await purchasingRequest(`/purchase-orders/${receiveTarget.id}/goods-receipts`, "POST", { receipt_ref: receiptRef, items })
      setReceiveTarget(null)
      setReceiveQty({})
      setReceiptRef("")
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
      <p className="text-sm text-muted-foreground mb-3">PO email is unavailable: Communication does not yet support PDF attachments.</p>
      <div className="flex items-end gap-2 mb-4">
        <div><Label htmlFor="po-autoapprove">Autoapproval limit (ZAR including VAT; 0 disables)</Label>
          <Input id="po-autoapprove" type="number" min="0" step="0.01" value={autoApproveLimit} onChange={(event) => setAutoApproveLimit(event.target.value)} />
        </div>
        <Button variant="outline" onClick={saveSettings}>Save limit</Button>
      </div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h4 className="card-title">Purchase Orders</h4>
          <p className="text-sm text-muted-foreground">
            Live procure-to-receive — draft → submit → approve → receive, three-way-matched against the PO.
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setNewSupplierOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" /> Supplier
          </Button>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" /> New Purchase Order
          </Button>
        </div>
      </div>

      <DataTable
        columns={columns}
        rows={pos}
        loading={loading}
        emptyTitle="No purchase orders yet"
        emptyDescription="Create one to start the procure-to-receive flow."
      />

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
              <Label>Warehouse ID</Label>
              <Input value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)} placeholder="warehouse UUID" />
            </div>
            <div className="space-y-2">
              <Label>Line items</Label>
              {lines.map((line, i) => (
                <div key={i} className="grid grid-cols-3 gap-2">
                  <Input
                    placeholder="Product UUID"
                    value={line.product_id}
                    onChange={(e) => {
                      const next = [...lines]; next[i] = { ...line, product_id: e.target.value }; setLines(next)
                    }}
                  />
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

      {/* New supplier */}
      <Dialog open={newSupplierOpen} onOpenChange={setNewSupplierOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>New Supplier</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Code</Label>
              <Input value={newSupplierCode} onChange={(e) => setNewSupplierCode(e.target.value)} placeholder="e.g. huawei" />
            </div>
            <div>
              <Label>Name</Label>
              <Input value={newSupplierName} onChange={(e) => setNewSupplierName(e.target.value)} placeholder="Supplier name" />
            </div>
          </div>
          <DialogFooter>
            <Button onClick={handleCreateSupplier}>Create</Button>
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
                <div key={item.id} className="flex items-center justify-between gap-3">
                  <div className="text-sm">
                    <div className="font-medium">{item.product_id.slice(0, 8)}…</div>
                    <div className="text-muted-foreground">
                      {item.quantity_received}/{item.quantity_ordered} received — {remaining} outstanding
                    </div>
                  </div>
                  <Input
                    type="number"
                    className="w-28"
                    placeholder="0"
                    max={remaining}
                    value={receiveQty[item.id] ?? ""}
                    onChange={(e) => setReceiveQty({ ...receiveQty, [item.id]: e.target.value })}
                  />
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
