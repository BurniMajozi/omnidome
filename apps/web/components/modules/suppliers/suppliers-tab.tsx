"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ArrowLeft, Building2, Mail, Pencil, Phone, Plus, Search, Trash2, UserRound } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { listProducts, type Product } from "@/lib/catalogue-api"
import {
  createSupplier, deleteSupplier, getScorecards, getSupplierDetail, listSuppliers, updateSupplier,
  type ScorecardRow, type SupplierDetail, type SupplierInput, type SupplierRecord,
} from "@/lib/supplier-api"
import { Field, areaCls, money, selectCls } from "../products/catalogue/shared"
import { MetricTiles, RejectionReasons, ScoreBadge } from "./scorecard"

type View = { kind: "list" } | { kind: "form"; supplier: SupplierRecord | null } | { kind: "detail"; supplier: SupplierRecord }

const BLANK: SupplierInput = {
  code: "", name: "", contact_person: "", email: "", phone: "", address: "", tax_id: "", account_number: "",
  payment_terms: "Net 30", lead_time_days: 7, spend_limit: "", notes: "", is_active: true,
}

export function SuppliersTab() {
  const [view, setView] = useState<View>({ kind: "list" })
  const [suppliers, setSuppliers] = useState<SupplierRecord[]>([])
  const [scores, setScores] = useState<Record<string, ScorecardRow>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [s, sc] = await Promise.all([listSuppliers(false), getScorecards(12).catch(() => null)])
      setSuppliers(s)
      setScores(Object.fromEntries((sc?.suppliers ?? []).map((r) => [r.id, r])))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load suppliers")
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { void load() }, [load])

  if (view.kind === "form") {
    return <SupplierForm supplier={view.supplier} onCancel={() => setView(view.supplier ? { kind: "detail", supplier: view.supplier } : { kind: "list" })}
      onSaved={async (s) => { await load(); setView({ kind: "detail", supplier: s }) }} />
  }
  if (view.kind === "detail") {
    const current = suppliers.find((s) => s.id === view.supplier.id) ?? view.supplier
    return <SupplierDetailView supplier={current} onBack={() => setView({ kind: "list" })} onEdit={() => setView({ kind: "form", supplier: current })}
      onChanged={load} onDeleted={async () => { await load(); setView({ kind: "list" }) }} />
  }
  return <SupplierList suppliers={suppliers} scores={scores} loading={loading} error={error} onNew={() => setView({ kind: "form", supplier: null })} onOpen={(s) => setView({ kind: "detail", supplier: s })} />
}

// ── directory ────────────────────────────────────────────────────────────────

function SupplierList({ suppliers, scores, loading, error, onNew, onOpen }: {
  suppliers: SupplierRecord[]; scores: Record<string, ScorecardRow>; loading: boolean; error: string | null; onNew: () => void; onOpen: (s: SupplierRecord) => void
}) {
  const [q, setQ] = useState("")
  const [status, setStatus] = useState("active")
  const rows = useMemo(() => {
    const t = q.trim().toLowerCase()
    return suppliers.filter((s) => (status === "all" || (status === "active") === s.is_active) &&
      (!t || [s.name, s.code, s.contact_person, s.email, s.phone, s.tax_id, s.account_number].join(" ").toLowerCase().includes(t)))
  }, [suppliers, q, status])
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-xl font-bold tracking-tight text-foreground">Suppliers</h2>
            <Badge variant="outline" className="border-primary/30 bg-primary/10 text-xs text-primary">{suppliers.filter((s) => s.is_active).length} active</Badge>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">One supplier list for the whole platform. Stock buys from these suppliers and rates every delivery; their performance shows here and on each product.</p>
        </div>
        <Button size="sm" className="h-8 gap-1.5 text-xs" onClick={onNew}><Plus className="h-3.5 w-3.5" /> New supplier</Button>
      </div>
      <Card className="border-border"><CardContent className="grid gap-3 p-3 sm:grid-cols-12 sm:p-4">
        <div className="relative sm:col-span-8">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name, code, contact, VAT or account number…" className="h-9 pl-8 text-xs" aria-label="Search suppliers" />
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className={`${selectCls} sm:col-span-4`} aria-label="Filter by status">
          <option value="active">Active</option><option value="inactive">Inactive</option><option value="all">All</option>
        </select>
      </CardContent></Card>
      {loading ? <p className="py-12 text-center text-sm text-muted-foreground">Loading suppliers…</p>
        : error ? <p className="py-8 text-center text-sm text-red-400" role="alert">Could not load suppliers: {error}</p>
        : suppliers.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border py-14 text-center">
            <p className="text-sm text-muted-foreground">No suppliers yet.</p>
            <Button size="sm" className="mt-3 gap-1.5 text-xs" onClick={onNew}><Plus className="h-3.5 w-3.5" /> Add your first supplier</Button>
          </div>
        ) : rows.length === 0 ? <p className="py-12 text-center text-sm text-muted-foreground">No suppliers match.</p>
        : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {rows.map((s) => (
              <div key={s.id} role="button" tabIndex={0} onClick={() => onOpen(s)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(s) } }}
                className="group cursor-pointer rounded-xl border border-border bg-card/80 p-4 shadow-sm transition-all hover:border-primary/50 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-primary">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary"><Building2 className="h-5 w-5" /></span>
                    <div>
                      <h3 className="text-sm font-semibold text-foreground group-hover:text-primary">{s.name}</h3>
                      <p className="font-mono text-[11px] text-primary">{s.code}</p>
                    </div>
                  </div>
                  {!s.is_active && <Badge variant="outline" className="border-border text-[10px] text-muted-foreground">Inactive</Badge>}
                </div>
                <div className="mt-3 space-y-1 border-t border-border/50 pt-2.5 text-xs text-muted-foreground">
                  <div className="flex items-center gap-1.5"><UserRound className="h-3 w-3 shrink-0" />{s.contact_person || "No contact person"}</div>
                  <div className="flex items-center gap-1.5"><Phone className="h-3 w-3 shrink-0" />{s.phone || "No phone"}</div>
                  <div className="flex items-center gap-1.5 truncate"><Mail className="h-3 w-3 shrink-0" /><span className="truncate">{s.email || "No email"}</span></div>
                </div>
                <div className="mt-3 flex items-center justify-between border-t border-border/40 pt-2.5 text-[11px]">
                  <span className="text-muted-foreground">{s.payment_terms || "No terms"} · {s.lead_time_days}d lead</span>
                  {scores[s.id] ? <ScoreBadge m={scores[s.id].metrics} /> : <span className="text-muted-foreground">No score yet</span>}
                </div>
              </div>
            ))}
          </div>
        )}
    </div>
  )
}

// ── add / edit ───────────────────────────────────────────────────────────────

function SupplierForm({ supplier, onCancel, onSaved }: { supplier: SupplierRecord | null; onCancel: () => void; onSaved: (s: SupplierRecord) => Promise<void> }) {
  const [f, setF] = useState<SupplierInput>(supplier ? {
    code: supplier.code, name: supplier.name, contact_person: supplier.contact_person ?? "", email: supplier.email ?? "", phone: supplier.phone ?? "",
    address: supplier.address ?? "", tax_id: supplier.tax_id ?? "", account_number: supplier.account_number ?? "", payment_terms: supplier.payment_terms ?? "",
    lead_time_days: supplier.lead_time_days, spend_limit: supplier.spend_limit ?? "", notes: supplier.notes ?? "", is_active: supplier.is_active,
  } : BLANK)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const set = (p: Partial<SupplierInput>) => setF((x) => ({ ...x, ...p }))
  const text = (k: keyof SupplierInput) => ({ value: String(f[k] ?? ""), onChange: (e: React.ChangeEvent<HTMLInputElement>) => set({ [k]: e.target.value } as Partial<SupplierInput>), className: "h-9 text-xs" })

  async function save() {
    if (!f.name.trim() || !f.code.trim()) return setErr("Name and code are required.")
    setBusy(true)
    setErr(null)
    try {
      const body = { ...f, lead_time_days: Number(f.lead_time_days) || 0, spend_limit: f.spend_limit === "" ? null : f.spend_limit }
      const saved = supplier ? await updateSupplier(supplier.id, body) : await createSupplier(body)
      await onSaved(saved)
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save the supplier")
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="space-y-4" aria-label="Supplier form">
      <div>
        <Button type="button" variant="ghost" size="sm" className="-ml-2 mb-1 h-7 gap-1.5 px-2 text-xs text-muted-foreground" onClick={onCancel}><ArrowLeft className="h-3.5 w-3.5" /> {supplier ? supplier.name : "Suppliers"}</Button>
        <h2 className="text-xl font-bold tracking-tight text-foreground">{supplier ? `Edit ${supplier.name}` : "New supplier"}</h2>
      </div>
      <div className="rounded-xl border border-border bg-card/60 p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Supplier name *"><Input {...text("name")} /></Field>
          <Field label="Supplier code *" hint="Short and unique, e.g. metro"><Input {...text("code")} /></Field>
          <Field label="Contact person"><Input {...text("contact_person")} /></Field>
          <Field label="Phone number"><Input {...text("phone")} placeholder="+27 …" /></Field>
          <Field label="Email address"><Input {...text("email")} type="email" /></Field>
          <Field label="VAT number"><Input {...text("tax_id")} /></Field>
          <Field label="Our account number with them" hint="The account or customer number they know us by"><Input {...text("account_number")} /></Field>
          <Field label="Payment terms"><Input {...text("payment_terms")} placeholder="Net 30" /></Field>
          <Field label="Typical lead time (days)"><Input {...text("lead_time_days")} type="number" min={0} max={365} /></Field>
          <Field label="Per-order spend limit (R, optional)" hint="Orders above this need extra approval"><Input {...text("spend_limit")} type="number" min={0} /></Field>
          <Field label="Address" className="sm:col-span-2"><textarea rows={2} value={f.address ?? ""} onChange={(e) => set({ address: e.target.value })} className={areaCls} /></Field>
          <Field label="Notes" className="sm:col-span-2"><textarea rows={2} value={f.notes ?? ""} onChange={(e) => set({ notes: e.target.value })} className={areaCls} /></Field>
          {supplier && <label className="flex items-center gap-2 text-xs text-foreground"><input type="checkbox" checked={f.is_active !== false} onChange={(e) => set({ is_active: e.target.checked })} /> Active (can be selected on new purchase orders)</label>}
        </div>
        <p className="mt-3 text-[11px] text-muted-foreground">Bank details are kept separately under Stock → Supplier bank details, with their own access control.</p>
        {err && <p className="mt-3 text-xs text-red-400" role="alert">{err}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
          <Button size="sm" disabled={busy} onClick={() => void save()}>{busy ? "Saving…" : "Save supplier"}</Button>
        </div>
      </div>
    </section>
  )
}

// ── detail with performance ─────────────────────────────────────────────────

function SupplierDetailView({ supplier, onBack, onEdit, onChanged, onDeleted }: {
  supplier: SupplierRecord; onBack: () => void; onEdit: () => void; onChanged: () => Promise<void>; onDeleted: () => Promise<void>
}) {
  const [detail, setDetail] = useState<SupplierDetail | null>(null)
  const [products, setProducts] = useState<Product[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setDetail(null)
    getSupplierDetail(supplier.id).then(setDetail).catch((e) => setError(e instanceof Error ? e.message : "Could not load performance"))
    listProducts().then(setProducts).catch(() => setProducts([]))
  }, [supplier.id])

  const supplied = products.filter((p) => p.definition.sources?.some((s) => s.supplier_id === supplier.id))
  const perf = new Map((detail?.by_product ?? []).map((b) => [b.catalogue_product_id, b.metrics]))

  async function toggleActive() {
    setBusy(true)
    try { await updateSupplier(supplier.id, { is_active: !supplier.is_active }); await onChanged() } catch (e) { setError(e instanceof Error ? e.message : "Failed") } finally { setBusy(false) }
  }
  async function remove() {
    if (!window.confirm(`Delete ${supplier.name}? Existing purchase orders and history are kept; it can no longer be selected.`)) return
    setBusy(true)
    try { await deleteSupplier(supplier.id); await onDeleted() } catch (e) { setError(e instanceof Error ? e.message : "Failed"); setBusy(false) }
  }
  return (
    <section className="space-y-5" aria-label="Supplier detail">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Button type="button" variant="ghost" size="sm" className="-ml-2 mb-1 h-7 gap-1.5 px-2 text-xs text-muted-foreground" onClick={onBack}><ArrowLeft className="h-3.5 w-3.5" /> Suppliers</Button>
          <div className="font-mono text-[11px] text-primary">{supplier.code}</div>
          <div className="flex items-center gap-2"><h2 className="text-xl font-bold tracking-tight text-foreground">{supplier.name}</h2>{!supplier.is_active && <Badge variant="outline" className="text-[10px]">Inactive</Badge>}{detail && <ScoreBadge m={detail.metrics} />}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" className="gap-1.5" onClick={onEdit}><Pencil className="h-3.5 w-3.5" /> Edit</Button>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => void toggleActive()}>{supplier.is_active ? "Deactivate" : "Activate"}</Button>
          <Button variant="outline" size="sm" disabled={busy} className="gap-1.5 hover:border-red-500/60 hover:text-red-400" onClick={() => void remove()}><Trash2 className="h-3.5 w-3.5" /> Delete</Button>
        </div>
      </div>
      {error && <p className="text-xs text-red-400" role="alert">{error}</p>}

      <div className="grid gap-4 rounded-xl border border-border bg-card/60 p-5 text-xs sm:grid-cols-2 lg:grid-cols-3">
        {([["Contact person", supplier.contact_person], ["Phone", supplier.phone], ["Email", supplier.email], ["VAT number", supplier.tax_id], ["Our account number", supplier.account_number],
          ["Payment terms", supplier.payment_terms], ["Typical lead time", `${supplier.lead_time_days} days`], ["Spend limit", supplier.spend_limit ? money(supplier.spend_limit) : null], ["Address", supplier.address]] as const).map(([k, v]) => (
          <div key={k}><div className="text-muted-foreground">{k}</div><div className="mt-0.5 whitespace-pre-line font-medium text-foreground">{v || "—"}</div></div>
        ))}
      </div>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-foreground">Performance (last 12 months)</h3>
        <p className="text-[11px] text-muted-foreground">Measured from stock: purchase orders against what was received, rejected and returned. Receivers rate each delivery in Stock.</p>
        {detail ? <><MetricTiles m={detail.metrics} /><RejectionReasons m={detail.metrics} /></> : <p className="text-xs text-muted-foreground">{error ? "" : "Loading performance…"}</p>}
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-foreground">Products this supplier provides</h3>
        {supplied.length === 0 ? <p className="text-xs text-muted-foreground">No product lists this supplier yet. Add it under a product's Sourcing &amp; costs step.</p> : (
          <div className="overflow-x-auto rounded-lg border border-border"><table className="w-full min-w-[640px] text-xs">
            <thead><tr className="border-b border-border bg-muted/20 text-left text-muted-foreground"><th className="px-3 py-2 font-medium">Product</th><th className="px-3 py-2 font-medium">Their SKU</th><th className="px-3 py-2 text-right font-medium">Unit cost</th><th className="px-3 py-2 text-right font-medium">Lead</th><th className="px-3 py-2 font-medium">Preferred</th><th className="px-3 py-2 font-medium">Performance on it</th></tr></thead>
            <tbody className="divide-y divide-border/60">{supplied.map((p) => {
              const s = p.definition.sources.find((x) => x.supplier_id === supplier.id)!
              const m = perf.get(p.id)
              return <tr key={p.id}><td className="px-3 py-2"><span className="font-mono text-primary">{p.product_number}</span> {p.name}</td><td className="px-3 py-2">{s.supplier_sku || "—"}</td>
                <td className="px-3 py-2 text-right">{money(s.unit_cost)}{s.cadence === "Monthly" ? " /mo" : ""}</td><td className="px-3 py-2 text-right">{s.lead_time_days ?? supplier.lead_time_days}d</td>
                <td className="px-3 py-2">{s.preferred ? "Yes" : "—"}</td><td className="px-3 py-2">{m ? <ScoreBadge m={m} /> : <span className="text-muted-foreground">No deliveries yet</span>}</td></tr>
            })}</tbody></table></div>
        )}
      </div>

      {detail && detail.deliveries.length > 0 && (
        <div className="space-y-2"><h3 className="text-sm font-semibold text-foreground">Recent deliveries</h3>
          <div className="overflow-x-auto rounded-lg border border-border"><table className="w-full min-w-[560px] text-xs">
            <thead><tr className="border-b border-border bg-muted/20 text-left text-muted-foreground"><th className="px-3 py-2 font-medium">Order</th><th className="px-3 py-2 font-medium">Due</th><th className="px-3 py-2 font-medium">First received</th><th className="px-3 py-2 font-medium">Days late</th></tr></thead>
            <tbody className="divide-y divide-border/60">{detail.deliveries.map((d) => <tr key={d.po_number}><td className="px-3 py-2 font-mono">{d.po_number}</td><td className="px-3 py-2">{d.expected_delivery ?? "—"}</td><td className="px-3 py-2">{d.first_received ?? "Not yet"}</td>
              <td className={`px-3 py-2 ${d.days_late ? "text-amber-400" : ""}`}>{d.days_late === null ? "—" : d.days_late}</td></tr>)}</tbody></table></div></div>
      )}
    </section>
  )
}
