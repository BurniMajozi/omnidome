"use client"

import { Fragment, useCallback, useEffect, useState } from "react"
import { ChevronDown, ChevronRight, Undo2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { inventoryCall } from "@/lib/catalogue-api"
import {
  getPurchasable, getScorecards, getSupplierDetail, pct, returnToSupplier,
  type PurchasableProduct, type ScorecardRow, type SupplierDetail,
} from "@/lib/supplier-api"
import { MetricTiles, RejectionReasons, ScoreBadge } from "./scorecard"

const selectCls = "h-9 w-full rounded-md border border-border bg-background px-3 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"

/**
 * Supplier evaluation, in Stock: where deliveries are received, rated and returned. The same numbers feed each
 * product's supplier comparison in Product Management.
 */
export function StockSupplierPerformance() {
  const [rows, setRows] = useState<ScorecardRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [detail, setDetail] = useState<SupplierDetail | null>(null)
  const [returnOpen, setReturnOpen] = useState(false)

  const load = useCallback(async () => {
    try { setRows((await getScorecards(12)).suppliers); setError(null) }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load supplier performance") }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void load() }, [load])

  async function toggle(id: string) {
    if (open === id) return setOpen(null)
    setOpen(id)
    setDetail(null)
    try { setDetail(await getSupplierDetail(id, 12)) } catch { setDetail(null) }
  }

  return (
    <div className="surface-card p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 className="card-title">Supplier performance</h4>
          <p className="text-sm text-muted-foreground">Late deliveries, short deliveries, rejected and returned stock, and receiver ratings over the last 12 months. Needs 3 deliveries before a score is shown.</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => setReturnOpen(true)}><Undo2 className="mr-1 h-3.5 w-3.5" /> Return stock to supplier</Button>
      </div>
      {loading ? <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
        : error ? <p className="py-6 text-center text-sm text-red-400" role="alert">{error}</p>
        : rows.length === 0 ? <p className="py-8 text-center text-sm text-muted-foreground">No suppliers yet. Suppliers are created in Product Management.</p>
        : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="w-6 py-2" /><th className="py-2 pr-3">Supplier</th><th className="py-2 pr-3">Score</th><th className="py-2 pr-3 text-right">Deliveries</th><th className="py-2 pr-3 text-right">On time</th>
                <th className="py-2 pr-3 text-right">Avg days late</th><th className="py-2 pr-3 text-right">Fill rate</th><th className="py-2 pr-3 text-right">Accepted</th><th className="py-2 pr-3 text-right">Returned</th><th className="py-2 text-right">Rating</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <Fragment key={r.id}>
                    <tr className="cursor-pointer border-b border-border/50 hover:bg-muted/20" onClick={() => void toggle(r.id)}>
                      <td className="py-2">{open === r.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</td>
                      <td className="py-2 pr-3 font-medium">{r.name}{!r.is_active && <span className="ml-2 text-xs text-muted-foreground">inactive</span>}</td>
                      <td className="py-2 pr-3"><ScoreBadge m={r.metrics} /></td>
                      <td className="py-2 pr-3 text-right">{r.metrics.deliveries}</td>
                      <td className="py-2 pr-3 text-right">{pct(r.metrics.on_time_rate)}</td>
                      <td className="py-2 pr-3 text-right">{r.metrics.avg_days_late === null ? "—" : r.metrics.avg_days_late.toFixed(1)}</td>
                      <td className="py-2 pr-3 text-right">{pct(r.metrics.fill_rate)}</td>
                      <td className="py-2 pr-3 text-right">{r.metrics.rejection_rate === null ? "—" : pct(1 - r.metrics.rejection_rate)}</td>
                      <td className="py-2 pr-3 text-right">{r.metrics.units_returned}</td>
                      <td className="py-2 text-right">{r.metrics.avg_rating === null ? "—" : `${r.metrics.avg_rating.toFixed(1)}/5`}</td>
                    </tr>
                    {open === r.id && (
                      <tr className="border-b border-border/50 bg-muted/10"><td colSpan={10} className="space-y-3 p-4">
                        {!detail ? <p className="text-xs text-muted-foreground">Loading…</p> : (
                          <>
                            <MetricTiles m={detail.metrics} />
                            <RejectionReasons m={detail.metrics} />
                            {detail.by_product.length > 0 && (
                              <table className="w-full text-xs"><thead><tr className="text-left text-muted-foreground"><th className="py-1 font-medium">Product</th><th className="py-1 font-medium">Score</th><th className="py-1 text-right font-medium">On time</th><th className="py-1 text-right font-medium">Fill</th><th className="py-1 text-right font-medium">Accepted</th><th className="py-1 text-right font-medium">Returned</th></tr></thead>
                                <tbody>{detail.by_product.map((p) => (
                                  <tr key={p.product_id} className="border-t border-border/40"><td className="py-1.5"><span className="font-mono text-primary">{p.product_number}</span> {p.name}</td><td><ScoreBadge m={p.metrics} /></td>
                                    <td className="text-right">{pct(p.metrics.on_time_rate)}</td><td className="text-right">{pct(p.metrics.fill_rate)}</td><td className="text-right">{p.metrics.rejection_rate === null ? "—" : pct(1 - p.metrics.rejection_rate)}</td><td className="text-right">{p.metrics.units_returned}</td></tr>))}</tbody></table>
                            )}
                          </>
                        )}
                      </td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      <ReturnDialog open={returnOpen} onClose={() => setReturnOpen(false)} suppliers={rows} onDone={load} />
    </div>
  )
}

function ReturnDialog({ open, onClose, suppliers, onDone }: { open: boolean; onClose: () => void; suppliers: ScorecardRow[]; onDone: () => Promise<void> }) {
  const [products, setProducts] = useState<PurchasableProduct[]>([])
  const [warehouses, setWarehouses] = useState<{ id: string; name: string }[]>([])
  const [f, setF] = useState({ supplier_id: "", product_id: "", quantity: "1", reason: "", warehouse_id: "", credit_note_ref: "", adjust_stock: true })
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!open) return
    setErr(null)
    getPurchasable().then(setProducts).catch(() => setProducts([]))
    inventoryCall<{ id: string; name: string }[]>("/warehouses").then(setWarehouses).catch(() => setWarehouses([]))
  }, [open])
  const set = (p: Partial<typeof f>) => setF((x) => ({ ...x, ...p }))

  async function submit() {
    if (!f.supplier_id || !f.product_id || !f.reason.trim()) return setErr("Choose the supplier and product and give a reason.")
    setBusy(true)
    setErr(null)
    try {
      await returnToSupplier({ supplier_id: f.supplier_id, product_id: f.product_id, quantity: Number(f.quantity) || 0, reason: f.reason, warehouse_id: f.adjust_stock ? f.warehouse_id || null : f.warehouse_id || null, credit_note_ref: f.credit_note_ref || null, adjust_stock: f.adjust_stock })
      await onDone()
      onClose()
      setF({ supplier_id: "", product_id: "", quantity: "1", reason: "", warehouse_id: "", credit_note_ref: "", adjust_stock: true })
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not record the return") } finally { setBusy(false) }
  }
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Return stock to supplier</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Supplier</Label><select className={selectCls} value={f.supplier_id} onChange={(e) => set({ supplier_id: e.target.value })}><option value="">Select supplier</option>{suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
          <div><Label>Product</Label><select className={selectCls} value={f.product_id} onChange={(e) => set({ product_id: e.target.value })}><option value="">Select product</option>{products.map((p) => <option key={p.inventory_product_id} value={p.inventory_product_id}>{p.product_number} · {p.name}</option>)}</select></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Quantity</Label><Input type="number" min={1} value={f.quantity} onChange={(e) => set({ quantity: e.target.value })} /></div>
            <div><Label>Warehouse</Label><select className={selectCls} value={f.warehouse_id} onChange={(e) => set({ warehouse_id: e.target.value })}><option value="">Select</option>{warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select></div>
          </div>
          <div><Label>Reason</Label><Input value={f.reason} onChange={(e) => set({ reason: e.target.value })} placeholder="Dead on arrival, wrong model, damaged…" /></div>
          <div><Label>Supplier credit note (optional)</Label><Input value={f.credit_note_ref} onChange={(e) => set({ credit_note_ref: e.target.value })} /></div>
          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={f.adjust_stock} onChange={(e) => set({ adjust_stock: e.target.checked })} /> Take these units out of the warehouse now (needs the warehouse)</label>
          {err && <p className="text-xs text-red-400" role="alert">{err}</p>}
        </div>
        <DialogFooter><Button variant="ghost" onClick={onClose}>Cancel</Button><Button disabled={busy} onClick={() => void submit()}>{busy ? "Saving…" : "Record return"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
