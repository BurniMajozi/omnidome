"use client"

import { useState } from "react"
import { Eye, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { Fee, Product } from "@/lib/catalogue-api"
import { AuthImage, Field, FEE_NAMES, money, primaryImage, selectCls } from "./shared"
import type { StepProps } from "./wizard-types"

const iconBtn = "h-9 w-9 shrink-0 p-0"

// ── Step 3: included products (from the catalogue) ───────────────────────────

function reaches(from: string, target: string, byId: Map<string, Product>, seen = new Set<string>()): boolean {
  if (from === target) return true
  if (seen.has(from)) return false
  seen.add(from)
  return (byId.get(from)?.definition.components ?? []).some((c) => reaches(c.product_id, target, byId, seen))
}

export function StepIncluded({ form, setDef, products, onView }: StepProps) {
  const d = form.definition
  const byId = new Map(products.map((p) => [p.id, p]))
  const candidates = products.filter((p) => p.id !== form.id && p.status === "active" && !(form.id && reaches(p.id, form.id, byId)))
  const free = candidates.filter((p) => !d.components.some((c) => c.product_id === p.id))

  const upd = (i: number, patch: Partial<(typeof d.components)[number]>) => setDef({ components: d.components.map((c, k) => (k === i ? { ...c, ...patch } : c)) })
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Does this product include something else?</h3>
        <p className="mt-1 text-xs text-muted-foreground">Pick from products already developed and launched in the catalogue. Pictures, costs, fees and documents come from that product, so edit them there. Included does not mean cost-free.</p>
      </div>
      {d.components.length === 0 && <p className="text-xs text-muted-foreground">Nothing included yet.</p>}
      {d.components.map((c, i) => {
        const x = byId.get(c.product_id)
        const opts = candidates.filter((p) => p.id === c.product_id || !d.components.some((k) => k.product_id === p.id))
        const fees = x?.definition.fees.filter((f) => f.enabled).map((f) => f.name).join(", ")
        return (
          <div key={`${c.product_id}-${i}`} className="grid items-center gap-3 rounded-lg border border-border bg-card/60 p-3 sm:grid-cols-[72px_1fr_90px_auto]">
            <AuthImage asset={x ? primaryImage(x.definition) : undefined} alt={x?.name} className="h-14 w-[72px] rounded-md ring-1 ring-border" />
            <div className="grid gap-1.5">
              <label className="text-xs text-muted-foreground" htmlFor={`inc-${i}`}>Product from the catalogue</label>
              <select id={`inc-${i}`} value={c.product_id} className={selectCls} onChange={(e) => upd(i, { product_id: e.target.value })}>
                {!x && <option value={c.product_id}>Unavailable product</option>}
                {opts.map((p) => <option key={p.id} value={p.id}>{p.product_number} · {p.name}</option>)}
              </select>
              {x && <small className="text-[11px] text-muted-foreground">{x.nature} · included at R0 to the customer{fees ? ` · fees on this item: ${fees}` : ""} · {x.definition.documents.length} documents</small>}
            </div>
            <Field label="Qty"><Input type="number" min={1} step={1} value={c.qty} onChange={(e) => upd(i, { qty: Math.max(1, Math.floor(Number(e.target.value)) || 1) })} className="h-9 text-xs" /></Field>
            <div className="flex gap-1.5">
              {x && <Button type="button" variant="outline" size="sm" className={iconBtn} title="View product details" aria-label={`View ${x.name}`} onClick={() => onView(x.id)}><Eye className="h-3.5 w-3.5" /></Button>}
              <Button type="button" variant="outline" size="sm" className={`${iconBtn} hover:border-red-500/60 hover:text-red-400`} title="Remove" aria-label="Remove included product" onClick={() => setDef({ components: d.components.filter((_, k) => k !== i) })}><Trash2 className="h-3.5 w-3.5" /></Button>
            </div>
          </div>
        )
      })}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="outline" size="sm" className="gap-1.5 text-xs" disabled={free.length === 0} onClick={() => setDef({ components: [...d.components, { product_id: free[0].id, qty: 1 }] })}><Plus className="h-3.5 w-3.5" /> Add included product</Button>
        {free.length === 0 && <span className="text-[11px] text-muted-foreground">No further launched products are available. Develop and launch the item first, then include it here.</span>}
      </div>
      <p className="text-[11px] text-muted-foreground">A product cannot include itself or anything that includes it. Only launched products can be included. Production also supports optional extras, rental/loan ownership and per-period quantities.</p>
    </div>
  )
}

// ── Step 4: price and customer fees ──────────────────────────────────────────

export function StepPricing({ form, setDef, preview }: StepProps) {
  const d = form.definition
  const [pick, setPick] = useState("")
  const [custom, setCustom] = useState("")
  const used = new Set(d.fees.map((f) => f.name.toLowerCase()))
  const available = FEE_NAMES.filter((n) => !used.has(n.toLowerCase()))
  const upd = (i: number, patch: Partial<Fee>) => setDef({ fees: d.fees.map((f, k) => (k === i ? { ...f, ...patch } : f)) })

  function addFee() {
    const name = (pick === "__other" ? custom : pick).trim()
    if (!name || used.has(name.toLowerCase())) return
    const cadence = ["Maintenance", "Equipment rental"].includes(name) ? "Monthly" : ["Callout", "Reconnection", "Relocation", "Support visit"].includes(name) ? "On event" : "Once-off"
    setDef({ fees: [...d.fees, { id: crypto.randomUUID(), name, enabled: true, amount: 0, cadence, mode: "Charge", invoice_label: `${name} fee` }] })
    setPick("")
    setCustom("")
  }
  const e = preview?.economics
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-foreground">How will customers pay?</h3>
        <p className="mt-1 text-xs text-muted-foreground">Use a consistent price and cost basis. Amounts are in ZAR excluding tax.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Selling price (R, ex tax)"><Input type="number" min={0} step="0.01" value={d.price} onChange={(ev) => setDef({ price: ev.target.value })} className="h-9 text-xs" /></Field>
        <Field label="Charge basis">
          <select value={d.recurring ? "m" : "o"} className={selectCls} onChange={(ev) => setDef({ recurring: ev.target.value === "m" })}><option value="m">Monthly recurring</option><option value="o">Once-off</option></select>
        </Field>
        {d.recurring && <Field label="Contract / forecast horizon (months)"><Input type="number" min={1} max={120} value={d.term} onChange={(ev) => setDef({ term: Math.max(1, Math.floor(Number(ev.target.value)) || 1) })} className="h-9 text-xs" /></Field>}
        <Field label="Proposed effective date"><Input type="date" value={d.launch_date ?? ""} onChange={(ev) => setDef({ launch_date: ev.target.value || null })} className="h-9 text-xs" /></Field>
      </div>

      <div className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Which fees may the customer pay?</h3>
          <p className="mt-1 text-xs text-muted-foreground">A customer charge is revenue; its delivery cost belongs in Sourcing &amp; costs. “Included” and “Waived” bill R0 but are still disclosed.</p>
        </div>
        {d.fees.length === 0 && <p className="text-xs text-muted-foreground">No customer fees yet. Add delivery, setup, callout, installation and so on below.</p>}
        {d.fees.map((f, i) => (
          <div key={f.id || i} className="rounded-lg border border-border bg-card/60 p-3">
            <div className="flex items-center justify-between gap-2">
              <label className="flex items-center gap-2 text-xs font-medium text-foreground">
                <input type="checkbox" role="switch" checked={f.enabled} onChange={(ev) => upd(i, { enabled: ev.target.checked })} aria-label={`Enable ${f.name} fee`} />
                {f.name} fee
              </label>
              <Button type="button" variant="ghost" size="sm" className="h-7 w-7 p-0 hover:text-red-400" aria-label={`Remove ${f.name} fee`} onClick={() => setDef({ fees: d.fees.filter((_, k) => k !== i) })}><Trash2 className="h-3.5 w-3.5" /></Button>
            </div>
            {f.enabled && (
              <div className="mt-3 grid gap-3 sm:grid-cols-4">
                <Field label="Treatment"><select value={f.mode} className={selectCls} onChange={(ev) => upd(i, { mode: ev.target.value as Fee["mode"] })}><option>Charge</option><option>Included</option><option>Waived</option></select></Field>
                <Field label="Trigger / cadence"><select value={f.cadence} className={selectCls} onChange={(ev) => upd(i, { cadence: ev.target.value as Fee["cadence"] })}><option>Once-off</option><option>Monthly</option><option>On event</option></select></Field>
                <Field label="Amount (R)"><Input type="number" min={0} step="0.01" disabled={f.mode !== "Charge"} value={f.mode === "Charge" ? f.amount : 0} onChange={(ev) => upd(i, { amount: ev.target.value })} className="h-9 text-xs" /></Field>
                <Field label="Invoice line description"><Input value={f.invoice_label} onChange={(ev) => upd(i, { invoice_label: ev.target.value })} className="h-9 text-xs" /></Field>
              </div>
            )}
          </div>
        ))}
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Add a fee">
            <select value={pick} className={`${selectCls} w-56`} onChange={(ev) => setPick(ev.target.value)}>
              <option value="">Choose a fee…</option>
              {available.map((n) => <option key={n}>{n}</option>)}
              <option value="__other">Other (custom name)…</option>
            </select>
          </Field>
          {pick === "__other" && <Field label="Fee name"><Input value={custom} onChange={(ev) => setCustom(ev.target.value)} className="h-9 w-48 text-xs" /></Field>}
          <Button type="button" variant="outline" size="sm" className="h-9 gap-1.5 text-xs" disabled={!pick || (pick === "__other" && !custom.trim())} onClick={addFee}><Plus className="h-3.5 w-3.5" /> Add fee</Button>
        </div>
      </div>

      {e && e.margin_pct !== undefined && (
        <div className="rounded-lg border border-border bg-card/60 p-3 text-xs">
          <div className="flex justify-between"><span className="text-muted-foreground">{e.horizon}-month contribution (price + enabled fees − direct cost)</span><strong className={Number(e.profit) < 0 ? "text-red-400" : ""}>{e.complete ? money(e.profit) : "Cost sheet incomplete"}</strong></div>
          <div className="mt-1 flex justify-between"><span className="text-muted-foreground">Margin</span><strong>{e.complete ? (e.margin_pct == null ? "N/A" : `${e.margin_pct}%`) : "N/A until costs are complete"}</strong></div>
        </div>
      )}
    </div>
  )
}
