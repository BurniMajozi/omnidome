"use client"

import { useEffect, useState } from "react"
import { Plus, Star, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { createSupplier, getProductSupplierPerformance, listSuppliers, pct, type ProductSupplierPerformance, type SupplierRecord } from "@/lib/supplier-api"
import type { Cost, Source } from "@/lib/catalogue-api"
import { ScoreBadge } from "../../suppliers/scorecard"
import { Field, money, selectCls } from "./shared"
import type { StepProps } from "./wizard-types"

const iconBtn = "h-9 w-9 shrink-0 p-0"

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 30)

// ── Step 2: suppliers, sourcing and costs ────────────────────────────────────

export function StepSourcing({ form, setDef, preview, notify }: StepProps) {
  const d = form.definition
  const [suppliers, setSuppliers] = useState<SupplierRecord[]>([])
  const [perf, setPerf] = useState<ProductSupplierPerformance | null>(null)
  const [quick, setQuick] = useState<null | { name: string; phone: string; email: string; contact: string }>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { listSuppliers(true).then(setSuppliers).catch(() => setSuppliers([])) }, [])
  useEffect(() => {
    setPerf(null)
    if (form.id && form.status === "active") getProductSupplierPerformance(form.id).then(setPerf).catch(() => setPerf(null))
  }, [form.id, form.status])

  const names = new Map(suppliers.map((s) => [s.id, s.name]))
  const free = suppliers.filter((s) => !d.sources.some((x) => x.supplier_id === s.id))
  const perfFor = (id: string) => perf?.suppliers.find((x) => x.supplier_id === id)

  const setSources = (sources: Source[]) => {
    // exactly one preferred source (the server enforces it too)
    const hasPref = sources.some((s) => s.preferred)
    setDef({ sources: sources.map((s, i) => ({ ...s, preferred: hasPref ? s.preferred : i === 0 })) })
  }
  const upd = (i: number, patch: Partial<Source>) => setSources(d.sources.map((s, k) => (k === i ? { ...s, ...patch } : s)))
  const prefer = (i: number) => setSources(d.sources.map((s, k) => ({ ...s, preferred: k === i })))
  const add = (supplierId: string) => {
    const sup = suppliers.find((s) => s.id === supplierId)
    setSources([...d.sources, { supplier_id: supplierId, supplier_sku: "", unit_cost: 0, cadence: d.recurring ? "Monthly" : "Once-off", lead_time_days: sup?.lead_time_days ?? null, moq: null, preferred: false, notes: "" }])
  }

  async function quickAdd() {
    if (!quick?.name.trim()) return notify("Enter the supplier's name.")
    setBusy(true)
    try {
      const code = `${slug(quick.name) || "supplier"}-${Math.random().toString(36).slice(2, 5)}`
      const created = await createSupplier({ code, name: quick.name.trim(), phone: quick.phone, email: quick.email, contact_person: quick.contact })
      setSuppliers((s) => [...s, created].sort((a, b) => a.name.localeCompare(b.name)))
      add(created.id)
      setQuick(null)
      notify(`${created.name} added. Complete their VAT number, address and account number in the Suppliers tab.`)
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not add the supplier")
    } finally {
      setBusy(false)
    }
  }

  const costs: { cost: Cost; index: number }[] = d.costs.map((cost, index) => ({ cost, index })).filter((x) => !x.cost.auto)
  const pref = d.sources.find((s) => s.preferred)
  const e = preview?.economics
  const updCost = (i: number, patch: Partial<Cost>) => setDef({ costs: d.costs.map((c, k) => (k === i ? { ...c, ...patch } : c)) })

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Suppliers and costs</h3>
        <p className="mt-1 text-xs text-muted-foreground">The product manager owns the suppliers of each product. Stock can only buy this product from the suppliers listed here, and the preferred supplier's price becomes the product's purchase cost.</p>
      </div>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-xs font-semibold text-foreground">Supplier sources</h4>
          <div className="flex flex-wrap items-center gap-2">
            <select className={`${selectCls} w-56`} value="" aria-label="Add a supplier" onChange={(ev) => { if (ev.target.value) add(ev.target.value) }}>
              <option value="">{free.length ? "Add a supplier…" : suppliers.length ? "All suppliers added" : "No suppliers yet"}</option>
              {free.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <Button type="button" variant="outline" size="sm" className="h-9 gap-1.5 text-xs" onClick={() => setQuick(quick ? null : { name: "", phone: "", email: "", contact: "" })}><Plus className="h-3.5 w-3.5" /> New supplier</Button>
          </div>
        </div>

        {quick && (
          <div className="rounded-lg border border-primary/40 bg-primary/5 p-3">
            <div className="grid gap-3 sm:grid-cols-4">
              <Field label="Supplier name *"><Input value={quick.name} onChange={(ev) => setQuick({ ...quick, name: ev.target.value })} className="h-9 text-xs" /></Field>
              <Field label="Contact person"><Input value={quick.contact} onChange={(ev) => setQuick({ ...quick, contact: ev.target.value })} className="h-9 text-xs" /></Field>
              <Field label="Phone"><Input value={quick.phone} onChange={(ev) => setQuick({ ...quick, phone: ev.target.value })} className="h-9 text-xs" /></Field>
              <Field label="Email"><Input value={quick.email} onChange={(ev) => setQuick({ ...quick, email: ev.target.value })} className="h-9 text-xs" /></Field>
            </div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-[11px] text-muted-foreground">Quick add. VAT number, address and account number go in the Suppliers tab.</span>
              <span className="flex gap-2"><Button type="button" variant="ghost" size="sm" onClick={() => setQuick(null)}>Cancel</Button><Button type="button" size="sm" disabled={busy} onClick={() => void quickAdd()}>Add supplier</Button></span>
            </div>
          </div>
        )}

        {d.sources.length === 0 && <p className="text-xs text-muted-foreground">No suppliers listed. Items bought as stock need at least one.</p>}
        {d.sources.map((s, i) => {
          const p = perfFor(s.supplier_id)
          const best = perf?.best_supplier_id === s.supplier_id
          return (
            <div key={s.supplier_id} className={`rounded-lg border p-3 ${s.preferred ? "border-primary/50 bg-primary/5" : "border-border bg-card/60"}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-foreground">
                  {names.get(s.supplier_id) ?? "Supplier"}
                  {s.preferred && <Badge className="gap-1 text-[10px]"><Star className="h-3 w-3" /> Preferred</Badge>}
                  {best && <Badge variant="outline" className="border-emerald-500/40 text-[10px] text-emerald-400">Best performer</Badge>}
                  {p && <ScoreBadge m={p.metrics} />}
                </div>
                <div className="flex gap-1.5">
                  {!s.preferred && <Button type="button" variant="ghost" size="sm" className="h-8 text-[11px]" onClick={() => prefer(i)}>Make preferred</Button>}
                  <Button type="button" variant="outline" size="sm" className="h-8 w-8 p-0 hover:border-red-500/60 hover:text-red-400" aria-label={`Remove ${names.get(s.supplier_id) ?? "supplier"}`} onClick={() => setSources(d.sources.filter((_, k) => k !== i))}><Trash2 className="h-3.5 w-3.5" /></Button>
                </div>
              </div>
              <div className="mt-3 grid gap-3 sm:grid-cols-5">
                <Field label="Their product code"><Input value={s.supplier_sku} onChange={(ev) => upd(i, { supplier_sku: ev.target.value })} className="h-9 text-xs" /></Field>
                <Field label="Unit cost (R, ex tax)"><Input type="number" min={0} step="0.01" value={s.unit_cost} onChange={(ev) => upd(i, { unit_cost: ev.target.value })} className="h-9 text-xs" /></Field>
                <Field label="Cadence"><select value={s.cadence} className={selectCls} onChange={(ev) => upd(i, { cadence: ev.target.value as Source["cadence"] })}><option>Once-off</option><option>Monthly</option></select></Field>
                <Field label="Lead time (days)"><Input type="number" min={0} max={365} value={s.lead_time_days ?? ""} onChange={(ev) => upd(i, { lead_time_days: ev.target.value === "" ? null : Number(ev.target.value) })} className="h-9 text-xs" /></Field>
                <Field label="Minimum order qty"><Input type="number" min={1} value={s.moq ?? ""} onChange={(ev) => upd(i, { moq: ev.target.value === "" ? null : Number(ev.target.value) })} className="h-9 text-xs" /></Field>
              </div>
              {p && p.metrics.deliveries > 0 && (
                <p className="mt-2 text-[11px] text-muted-foreground">
                  On this product: {pct(p.metrics.on_time_rate)} on time · {pct(p.metrics.fill_rate)} filled · {p.metrics.rejection_rate === null ? "—" : pct(1 - p.metrics.rejection_rate)} accepted · {p.metrics.units_returned} returned · {p.metrics.deliveries} deliver{p.metrics.deliveries === 1 ? "y" : "ies"}
                </p>
              )}
            </div>
          )
        })}
        {perf && perf.best_reason && perf.suppliers.length > 1 && <p className="text-[11px] text-muted-foreground">Suggested supplier: {names.get(perf.best_supplier_id ?? "") ?? "—"} ({perf.best_reason.toLowerCase()}).</p>}
        {!form.id || form.status !== "active" ? <p className="text-[11px] text-muted-foreground">Supplier performance on this product appears here once it is launched and stock has been received against it.</p> : null}
      </div>

      <div className="space-y-3">
        <h4 className="text-xs font-semibold text-foreground">Cost sheet</h4>
        <p className="text-xs text-muted-foreground">Add every other direct cost. The purchase cost comes from the preferred supplier above. Monthly and once-off costs stay separate. A missing cost is never treated as zero.</p>
        {pref && (
          <div className="grid items-end gap-2 rounded-lg border border-dashed border-primary/40 p-3 text-xs sm:grid-cols-[1.4fr_1fr_110px_120px_36px]">
            <div><div className="text-muted-foreground">Cost component</div><div className="mt-1 font-medium text-foreground">Purchase cost (preferred supplier)</div></div>
            <div><div className="text-muted-foreground">Source</div><div className="mt-1 text-foreground">{names.get(pref.supplier_id) ?? "Supplier"}</div></div>
            <div><div className="text-muted-foreground">Amount</div><div className="mt-1 text-foreground">{money(pref.unit_cost)}</div></div>
            <div><div className="text-muted-foreground">Cadence</div><div className="mt-1 text-foreground">{pref.cadence}</div></div>
            <span className="text-[10px] text-muted-foreground">auto</span>
          </div>
        )}
        {costs.length === 0 && !pref && <p className="text-xs text-amber-400">No direct costs captured. Profitability is incomplete.</p>}
        {costs.map(({ cost: c, index }) => (
          <div key={index} className="grid items-end gap-2 sm:grid-cols-[1.4fr_1fr_110px_120px_36px]">
            <Field label="Cost component"><Input value={c.name} onChange={(ev) => updCost(index, { name: ev.target.value })} className="h-9 text-xs" /></Field>
            <Field label="Source"><Input value={c.supplier} onChange={(ev) => updCost(index, { supplier: ev.target.value })} className="h-9 text-xs" /></Field>
            <Field label="Amount (R)"><Input type="number" min={0} step="0.01" value={c.amount} onChange={(ev) => updCost(index, { amount: ev.target.value })} className="h-9 text-xs" /></Field>
            <Field label="Cadence"><select value={c.cadence} className={selectCls} onChange={(ev) => updCost(index, { cadence: ev.target.value as Cost["cadence"] })}><option>Monthly</option><option>Once-off</option></select></Field>
            <Button type="button" variant="outline" size="sm" className={`${iconBtn} hover:border-red-500/60 hover:text-red-400`} aria-label={`Remove cost line ${index + 1}`} onClick={() => setDef({ costs: d.costs.filter((_, k) => k !== index) })}><Trash2 className="h-3.5 w-3.5" /></Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" className="gap-1.5 text-xs" onClick={() => setDef({ costs: [...d.costs, { name: "", supplier: "Internal", amount: 0, cadence: d.recurring ? "Monthly" : "Once-off" }] })}><Plus className="h-3.5 w-3.5" /> Add cost line</Button>
      </div>

      {e && (
        <div className="rounded-lg border border-border bg-card/60 p-3 text-xs">
          <div className="flex justify-between"><span className="text-muted-foreground">Recurring direct cost</span><strong>{money(e.monthly)}/mo</strong></div>
          <div className="mt-1 flex justify-between"><span className="text-muted-foreground">Upfront direct cost (includes inclusions)</span><strong>{money(e.upfront)}</strong></div>
          {!e.complete && <p className="mt-2 text-amber-400">Incomplete cost sheet: margin is not shown until every cost is captured.</p>}
        </div>
      )}
      <p className="text-[11px] text-muted-foreground">Alternative supplier quotes are separate sources, never added together. Cost changes after launch create dated revisions.</p>
    </div>
  )
}
