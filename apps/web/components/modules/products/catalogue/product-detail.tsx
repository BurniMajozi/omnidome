"use client"

import { useEffect, useState } from "react"
import { Archive, Download, Pencil, Rocket, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { archiveProduct, deleteProduct, downloadAsset, launchProduct, productHistory, type HistoryEvent, type Product } from "@/lib/catalogue-api"
import { getProductSupplierPerformance, pct, type ProductSupplierPerformance } from "@/lib/supplier-api"
import { ScoreBadge } from "../../suppliers/scorecard"
import { AuthImage, StatusBadge, kpiSet, money, primaryImage, productSummary } from "./shared"

interface Props {
  product: Product | null
  products: Product[]
  onClose: () => void
  onEdit: (p: Product) => void
  onChanged: () => Promise<void>
  onOpen: (p: Product) => void
  /** False while the product editor is open, so a stacked detail view cannot replace the draft being edited. */
  canEdit?: boolean
}

export function ProductDetail({ product, products, onClose, onEdit, onChanged, onOpen, canEdit = true }: Props) {
  const [history, setHistory] = useState<HistoryEvent[]>([])
  const [supplierPerf, setSupplierPerf] = useState<ProductSupplierPerformance | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setError(null)
    setHistory([])
    setSupplierPerf(null)
    if (product) {
      productHistory(product.id).then(setHistory).catch(() => setHistory([]))
      if ((product.definition.sources ?? []).length) getProductSupplierPerformance(product.id).then(setSupplierPerf).catch(() => setSupplierPerf(null))
    }
  }, [product])

  async function act(fn: () => Promise<unknown>, done: string) {
    setBusy(true)
    setError(null)
    try {
      await fn()
      await onChanged()
      onClose()
      void done
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed")
    } finally {
      setBusy(false)
    }
  }

  const p = product
  const d = p?.definition
  const fees = d?.fees.filter((f) => f.enabled) ?? []
  const customerDocs = d?.documents ?? []
  const includes = (d?.components ?? []).map((c) => ({ c, x: products.find((x) => x.id === c.product_id) }))
  const kpis = p ? kpiSet(p.nature).filter((k) => d!.research.kpis.includes(k.key)) : []
  const e = p?.economics

  return (
    <Dialog open={!!p} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="flex max-h-[92vh] w-[96vw] max-w-4xl flex-col gap-0 overflow-hidden p-0">
        {p && d && (
          <>
            <DialogHeader className="border-b border-border px-6 py-4 text-left">
              <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-primary">
                <span className="font-mono">{p.product_number}</span><span>·</span><span>{productSummary(p)}</span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <DialogTitle className="text-lg">{d.customer_name || p.name}</DialogTitle>
                <StatusBadge status={p.status} />
                <Badge variant="outline" className="text-[10px]">{p.nature}</Badge>
              </div>
              <DialogDescription className="sr-only">Product details, launch requirements and history.</DialogDescription>
            </DialogHeader>

            <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5 text-xs">
              <div className="grid gap-5 md:grid-cols-[220px_1fr]">
                <AuthImage asset={primaryImage(d)} alt={p.name} className="aspect-[4/3] w-full rounded-lg ring-1 ring-border" />
                <div className="space-y-2">
                  <p className="text-sm text-foreground">{d.description || <span className="text-muted-foreground">No description yet.</span>}</p>
                  <div className="grid gap-2 sm:grid-cols-3">
                    <div><span className="text-muted-foreground">Price</span><div className="font-medium text-foreground">{Number(d.price) > 0 ? `${money(d.price)}${d.recurring ? " /mo" : ""}` : "Not set"}</div></div>
                    <div><span className="text-muted-foreground">Owner</span><div className="font-medium text-foreground">{p.owner || "Unassigned"}</div></div>
                    <div><span className="text-muted-foreground">Family</span><div className="font-medium text-foreground">{p.family || "Unclassified"}</div></div>
                  </div>
                  {e && (
                    <div className="rounded-md border border-border bg-card/60 p-2.5">
                      <div className="flex justify-between"><span className="text-muted-foreground">Direct cost</span><span>{money(e.monthly)}/mo · {money(e.upfront)} upfront</span></div>
                      <div className="mt-1 flex justify-between"><span className="text-muted-foreground">{e.horizon}-month contribution</span><strong>{e.complete ? `${money(e.profit)} (${e.margin_pct == null ? "N/A" : `${e.margin_pct}%`})` : "Cost sheet incomplete"}</strong></div>
                    </div>
                  )}
                </div>
              </div>

              {includes.length > 0 && (
                <section><h4 className="mb-1.5 font-semibold text-foreground">Includes</h4>
                  <div className="flex flex-wrap gap-2">
                    {includes.map(({ c, x }) => (
                      <button key={c.product_id} type="button" disabled={!x} onClick={() => x && onOpen(x)} className="flex items-center gap-2 rounded-lg border border-border bg-card/60 p-1.5 pr-3 text-left hover:border-primary/50">
                        <AuthImage asset={x ? primaryImage(x.definition) : undefined} alt={x?.name} className="h-10 w-12 rounded" />
                        <span><span className="block font-medium text-foreground">{c.qty} × {x?.name ?? "Unavailable product"}</span><span className="block font-mono text-[10px] text-primary">{x?.product_number}</span></span>
                      </button>
                    ))}
                  </div>
                </section>
              )}

              {supplierPerf && supplierPerf.suppliers.length > 0 && (
                <section><h4 className="mb-1.5 font-semibold text-foreground">Suppliers and how they perform on this product</h4>
                  <div className="overflow-x-auto rounded-lg border border-border"><table className="w-full min-w-[640px]">
                    <thead><tr className="border-b border-border bg-muted/20 text-left text-muted-foreground"><th className="px-3 py-2 font-medium">Supplier</th><th className="px-3 py-2 text-right font-medium">Unit cost</th><th className="px-3 py-2 text-right font-medium">Lead</th><th className="px-3 py-2 font-medium">Score</th><th className="px-3 py-2 text-right font-medium">On time</th><th className="px-3 py-2 text-right font-medium">Accepted</th><th className="px-3 py-2 text-right font-medium">Returned</th></tr></thead>
                    <tbody className="divide-y divide-border/60">{supplierPerf.suppliers.map((s) => (
                      <tr key={s.supplier_id}>
                        <td className="px-3 py-2">{s.name}{s.preferred && <span className="ml-1.5 rounded bg-primary/15 px-1.5 py-0.5 text-[10px] text-primary">preferred</span>}{supplierPerf.best_supplier_id === s.supplier_id && <span className="ml-1.5 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] text-emerald-400">best</span>}</td>
                        <td className="px-3 py-2 text-right">{money(s.unit_cost)}{s.cadence === "Monthly" ? " /mo" : ""}</td>
                        <td className="px-3 py-2 text-right">{s.quoted_lead_days ?? "—"}{s.quoted_lead_days != null ? "d" : ""}{s.metrics.avg_lead_days != null ? <span className="text-muted-foreground"> (actual {s.metrics.avg_lead_days.toFixed(0)}d)</span> : null}</td>
                        <td className="px-3 py-2"><ScoreBadge m={s.metrics} /></td>
                        <td className="px-3 py-2 text-right">{pct(s.metrics.on_time_rate)}</td>
                        <td className="px-3 py-2 text-right">{s.metrics.rejection_rate === null ? "—" : pct(1 - s.metrics.rejection_rate)}</td>
                        <td className="px-3 py-2 text-right">{s.metrics.units_returned}</td>
                      </tr>))}</tbody></table></div>
                  {supplierPerf.best_reason && supplierPerf.suppliers.length > 1 && <p className="mt-1 text-[11px] text-muted-foreground">Best supplier for this product: {supplierPerf.best_reason.toLowerCase()}. Performance comes from receiving in Stock.</p>}
                </section>
              )}

              {fees.length > 0 && (
                <section><h4 className="mb-1.5 font-semibold text-foreground">Customer fees</h4>
                  <table className="w-full"><tbody className="divide-y divide-border/60">
                    {fees.map((f) => <tr key={f.id}><td className="py-1.5">{f.name}</td><td className="text-muted-foreground">{f.cadence}</td><td className="text-right font-medium">{f.mode === "Charge" ? money(f.amount) : f.mode}</td></tr>)}
                  </tbody></table>
                </section>
              )}

              {(customerDocs.length > 0 || d.policy_refs.length > 0) && (
                <section><h4 className="mb-1.5 font-semibold text-foreground">Documents and policies</h4>
                  <ul className="space-y-1">
                    {customerDocs.map((a) => (
                      <li key={a.id} className="flex items-center justify-between rounded-md border border-border px-3 py-1.5">
                        <span>{a.category}: {a.name} <span className="text-muted-foreground">· v{a.version} · {a.visibility}</span></span>
                        <Button type="button" variant="ghost" size="sm" className="h-7 w-7 p-0" aria-label={`Download ${a.name}`} onClick={() => void downloadAsset(a)}><Download className="h-3.5 w-3.5" /></Button>
                      </li>
                    ))}
                    {d.policy_refs.map((r) => <li key={r} className="rounded-md border border-border px-3 py-1.5">Policy: {r}</li>)}
                  </ul>
                </section>
              )}

              {d.research.rows.length > 0 && (
                <section><h4 className="mb-1.5 font-semibold text-foreground">Competitor research</h4>
                  <table className="w-full"><thead><tr className="text-left text-muted-foreground"><th className="py-1 font-medium">Competitor</th><th className="font-medium">Offer</th><th className="text-right font-medium">Price</th><th className="font-medium pl-3">Checked</th></tr></thead>
                    <tbody className="divide-y divide-border/60">{d.research.rows.map((r, i) => <tr key={i}><td className="py-1.5">{r.name || "—"}</td><td>{r.offer}</td><td className="text-right">{r.price ? money(r.price) : "—"}</td><td className="pl-3 text-muted-foreground">{r.date}</td></tr>)}</tbody></table>
                </section>
              )}

              <section><h4 className="mb-1.5 font-semibold text-foreground">Product performance</h4>
                <div className="grid gap-2 sm:grid-cols-3">
                  {kpis.length === 0 && <p className="text-muted-foreground">No KPIs selected.</p>}
                  {kpis.map((k) => (
                    <div key={k.key} className="rounded-md border border-border p-2.5">
                      <div className="text-lg font-semibold text-muted-foreground">—</div>
                      <div className="text-foreground">{k.label}</div>
                      <div className="text-[11px] text-muted-foreground">{k.source} · {p.status === "active" ? "feed not connected yet" : "available after launch"}</div>
                    </div>
                  ))}
                </div>
              </section>

              {p.status !== "active" && p.status !== "archived" && (
                <section><h4 className="mb-1.5 font-semibold text-foreground">Launch requirements</h4>
                  <ul className="space-y-1">{p.checks.map((c, i) => <li key={i} className={c.ok ? "text-emerald-400" : "text-amber-400"}>{c.ok ? "✓" : "○"} {c.label}{c.detail && <span className="text-muted-foreground"> · {c.detail}</span>}</li>)}</ul>
                </section>
              )}

              <section><h4 className="mb-1.5 font-semibold text-foreground">History</h4>
                <ul className="space-y-1 text-muted-foreground">
                  {history.length === 0 && <li>No history yet.</li>}
                  {history.slice(0, 12).map((h) => <li key={h.id}>{new Date(h.at).toLocaleString("en-ZA")} · <span className="text-foreground">{h.kind.replace("_", " ")}</span></li>)}
                </ul>
              </section>
              {error && <p className="text-red-400" role="alert">{error}</p>}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-6 py-3">
              <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
              <div className="flex flex-wrap gap-2">
                {canEdit && p.status !== "archived" && <Button variant="outline" size="sm" className="gap-1.5" onClick={() => { onClose(); onEdit(p) }}><Pencil className="h-3.5 w-3.5" /> Edit</Button>}
                {(p.status === "draft" || p.status === "in_review") && (
                  <>
                    <Button variant="outline" size="sm" className="gap-1.5 hover:border-red-500/60 hover:text-red-400" disabled={busy}
                      onClick={() => { if (window.confirm(`Delete draft ${p.product_number}? Its number will never be reused.`)) void act(() => deleteProduct(p.id), "deleted") }}><Trash2 className="h-3.5 w-3.5" /> Delete</Button>
                    <Button size="sm" className="gap-1.5" disabled={busy || !p.ready_to_launch} title={p.ready_to_launch ? "" : "Complete the launch requirements first"}
                      onClick={() => void act(() => launchProduct(p.id, p.revision), "launched")}><Rocket className="h-3.5 w-3.5" /> Launch</Button>
                  </>
                )}
                {p.status === "active" && (
                  <Button variant="outline" size="sm" className="gap-1.5" disabled={busy}
                    onClick={() => { if (window.confirm(`Archive ${p.product_number}? It is retired from new sales; history is kept.`)) void act(() => archiveProduct(p.id, p.revision), "archived") }}><Archive className="h-3.5 w-3.5" /> Archive</Button>
                )}
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
