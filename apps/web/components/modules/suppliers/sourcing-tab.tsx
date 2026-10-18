"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { ArrowLeft, Check, ExternalLink, Loader2, Mail, Plus, RefreshCw, Search, Send, Sparkles, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { inventoryCall, listProducts, type Product } from "@/lib/catalogue-api"
import {
  awardRequest, compareRequest, convertProspect, createRequest, editRequest, getCandidates, getDiscovery, getReorder, getRequest, listProspects,
  listRequests, parseReply, patchProspect, recordResponse, requestAction, runScan, sendRequest, startDiscovery,
  type Candidates, type Comparison, type Invitee, type ParsedReply, type Prospect, type ReorderItem, type RequestDetail, type RequestStatus, type SourcingRequest,
} from "@/lib/sourcing-api"
import { UsageIndicator } from "@/components/modules/analytics/shared"
import { Field, areaCls, money, selectCls } from "../products/catalogue/shared"

type Section = "reorder" | "find" | "requests"
const STATUS_STYLE: Record<RequestStatus, string> = {
  draft: "border-border text-muted-foreground", pending_approval: "border-amber-500/40 text-amber-400", approved: "border-sky-500/40 text-sky-400",
  sent: "border-primary/40 text-primary", awarded: "border-emerald-500/40 text-emerald-400", closed: "border-border text-muted-foreground", cancelled: "border-red-500/40 text-red-400",
}
const errText = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback)

export function SourcingTab() {
  const [section, setSection] = useState<Section>("reorder")
  const [products, setProducts] = useState<Product[]>([])
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null)
  const [openRequest, setOpenRequest] = useState<string | null>(null)
  const [draft, setDraft] = useState<{ product_id: string; quantity?: number; kind?: "RFI" | "RFQ"; prospect_id?: string } | null>(null)
  useEffect(() => { listProducts().then((p) => setProducts(p.filter((x) => x.status === "active" || x.status === "draft"))).catch(() => setProducts([])) }, [])
  const notify = useCallback((text: string, error = false) => setMessage({ text, error }), [])
  const startRequest = (d: NonNullable<typeof draft>) => { setDraft(d); setSection("requests"); setOpenRequest(null) }
  const tabs: [Section, string][] = [["reorder", "What to buy"], ["find", "Find suppliers"], ["requests", "RFI / RFQ"]]
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Sourcing</h3>
        <p className="mt-1 text-xs text-muted-foreground">Find suppliers from a product&apos;s description, ask them for information or quotations, compare the replies and decide. Everything follows the procurement protocol set by your admin (Admin → Protocols), and the buying agent works inside the same rules.</p>
      </div>
      <div className="flex gap-1.5" role="tablist">
        {tabs.map(([k, label]) => (
          <Button key={k} type="button" size="sm" variant={section === k ? "default" : "outline"} className="h-8 text-xs" role="tab" aria-selected={section === k} onClick={() => { setSection(k); setOpenRequest(null); setDraft(null) }}>{label}</Button>
        ))}
      </div>
      {message && <p className={`rounded-md border px-3 py-2 text-xs ${message.error ? "border-red-500/40 text-red-400" : "border-border text-foreground"}`} role={message.error ? "alert" : "status"}>{message.text}</p>}
      {section === "reorder" && <ReorderView notify={notify} onRequest={(it) => startRequest({ product_id: it.product_id, quantity: it.suggested_qty, kind: "RFQ" })} onOpen={(id) => { setSection("requests"); setOpenRequest(id) }} />}
      {section === "find" && <FindView products={products} notify={notify} onInvite={(pid, prospect) => startRequest({ product_id: pid, kind: "RFI", prospect_id: prospect })} />}
      {section === "requests" && <RequestsView products={products} notify={notify} openId={openRequest} setOpenId={setOpenRequest} draft={draft} clearDraft={() => setDraft(null)} />}
    </div>
  )
}

// ── what to buy ──────────────────────────────────────────────────────────────

function ReorderView({ notify, onRequest, onOpen }: { notify: (t: string, e?: boolean) => void; onRequest: (i: ReorderItem) => void; onOpen: (id: string) => void }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof getReorder>> | null>(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => getReorder().then(setData).catch((e) => notify(errText(e, "Could not load suggestions"), true)), [notify])
  useEffect(() => { void load() }, [load])
  async function scan() {
    setBusy(true)
    try {
      const r = await runScan()
      notify(r.created.length ? `Prepared ${r.created.length} draft request${r.created.length === 1 ? "" : "s"}: ${r.created.map((c) => c.number).join(", ")}. Review and approve them under RFI / RFQ.` : "Nothing new to request." + (r.skipped[0] ? ` ${r.skipped[0].product}: ${r.skipped[0].why}.` : ""))
      await load()
    } catch (e) { notify(errText(e, "The scan failed"), true) } finally { setBusy(false) }
  }
  return (
    <Card><CardContent className="space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{data?.note ?? "Reading stock and sales…"}{data ? ` Target cover: ${data.cover_days} days.` : ""}</p>
        <Button type="button" size="sm" variant="outline" className="h-8 gap-1.5 text-xs" disabled={busy || !data?.items.length} onClick={() => void scan()}>
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Prepare draft RFQs for all
        </Button>
      </div>
      {data && data.items.length === 0 && (
        <p className="text-xs text-muted-foreground">Nothing to reorder from your KPIs yet. This list fills in when a launched stock product has customer dispatches in the last {data.lookback_days} days and its stock cover falls below {data.cover_days} days. You can still ask suppliers about any product under “RFI / RFQ”.</p>
      )}
      {data && data.items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead><tr className="text-muted-foreground"><th className="py-1 pr-3 font-normal">Product</th><th className="px-2 font-normal">Available</th><th className="px-2 font-normal">Sales / day</th><th className="px-2 font-normal">Cover</th><th className="px-2 font-normal">On order</th><th className="px-2 font-normal">Suggested</th><th className="px-2 font-normal">Est. spend</th><th className="px-2 font-normal">Margin</th><th /></tr></thead>
            <tbody>
              {data.items.map((i) => (
                <tr key={i.product_id} className="border-t border-border align-top">
                  <td className="py-1.5 pr-3 text-foreground">{i.product_number} · {i.name}{i.flags.map((f) => <div key={f} className="text-[10px] text-amber-400">{f}</div>)}</td>
                  <td className="px-2">{i.available}</td><td className="px-2">{i.sales_per_day}</td>
                  <td className={`px-2 ${i.days_of_cover !== null && i.days_of_cover < 7 ? "text-red-400" : ""}`}>{i.days_of_cover === null ? "—" : `${i.days_of_cover} d`}</td>
                  <td className="px-2">{i.on_order}</td><td className="px-2 font-medium text-foreground">{i.suggested_qty}</td>
                  <td className="px-2">{i.estimated_spend === null ? "—" : money(i.estimated_spend)}</td>
                  <td className="px-2">{i.margin_pct === null ? "—" : `${i.margin_pct}%`}</td>
                  <td className="px-2"><Button type="button" size="sm" variant="outline" className="h-7 text-[11px]" disabled={i.open_request} onClick={() => onRequest(i)}>{i.open_request ? "Request open" : "Request quotes"}</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </CardContent></Card>
  )
}

// ── find suppliers ───────────────────────────────────────────────────────────

function FindView({ products, notify, onInvite }: { products: Product[]; notify: (t: string, e?: boolean) => void; onInvite: (productId: string, prospectId: string) => void }) {
  const [productId, setProductId] = useState("")
  const [note, setNote] = useState("")
  const [running, setRunning] = useState(false)
  const [prospects, setProspects] = useState<Prospect[]>([])
  const [meterKey, setMeterKey] = useState(0)
  const [loadError, setLoadError] = useState<string | null>(null)
  const alive = useRef(true)
  useEffect(() => () => { alive.current = false }, [])
  const load = useCallback((pid: string) => {
    setLoadError(null)
    return pid ? listProspects(pid).then(setProspects).catch((e) => { setProspects([]); setLoadError(errText(e, "Could not load prospects")) }) : Promise.resolve(setProspects([]))
  }, [])
  useEffect(() => { void load(productId) }, [productId, load])

  async function search() {
    if (!productId) return notify("Choose a product first.", true)
    setRunning(true)
    try {
      const d = await startDiscovery(productId, note)
      const deadline = Date.now() + 4 * 60_000
      let cur = await getDiscovery(d.id)
      while (alive.current && cur.status === "running" && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 4000))
        cur = await getDiscovery(d.id)
      }
      if (cur.status === "failed") throw new Error(cur.error || "The search failed")
      if (cur.status === "running") throw new Error("The search is still running. Check back in a minute.")
      notify(cur.prospects ? `Found ${cur.prospects} possible supplier${cur.prospects === 1 ? "" : "s"}. Check each one before contacting them.` : "The search found no new suppliers.")
      await load(productId)
    } catch (e) { notify(errText(e, "Search failed"), true) } finally { if (alive.current) { setRunning(false); setMeterKey((k) => k + 1) } }
  }
  async function act(fn: () => Promise<unknown>, ok: string) {
    try { await fn(); notify(ok); await load(productId) } catch (e) { notify(errText(e, "That did not work"), true) }
  }
  return (
    <Card><CardContent className="space-y-3 p-4">
      <p className="text-xs text-muted-foreground">Searches the web for suppliers of the product, using its description and specifications. It uses your research credits. Details are only what the pages show; confirm them before you rely on them.</p>
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Product"><select className={`${selectCls} w-64`} value={productId} onChange={(e) => setProductId(e.target.value)}><option value="">Choose a product…</option>{products.map((p) => <option key={p.id} value={p.id}>{p.product_number} · {p.name}</option>)}</select></Field>
        <Field label="Anything specific? (optional)"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. must hold ICASA approval" className="h-9 w-64 text-xs" maxLength={300} /></Field>
        <Button type="button" size="sm" className="h-9 gap-1.5 text-xs" disabled={running || !productId} onClick={() => void search()}>{running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />} {running ? "Searching…" : "Search the web"}</Button>
      </div>
      <UsageIndicator refreshKey={meterKey} />
      {running && <p className="text-xs text-muted-foreground" role="status">Searching the web and reading the top pages. This usually takes under a minute and uses research credits.</p>}
      {loadError && <p className="text-xs text-red-400" role="alert">{loadError} <Button type="button" variant="outline" size="sm" className="ml-2 h-6 text-[11px]" onClick={() => void load(productId)}>Retry</Button></p>}
      {productId && !loadError && prospects.length === 0 && !running && <p className="text-xs text-muted-foreground">No prospects for this product yet. Press “Search the web”.</p>}
      {prospects.map((p) => (
        <div key={p.id} className={`rounded-lg border p-3 text-xs ${p.status === "dismissed" ? "border-border opacity-60" : "border-border bg-card/60"}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="flex items-center gap-2 font-medium text-foreground">{p.name}
              {p.fit !== null && <Badge variant="outline" className="text-[10px]">Fit {p.fit}%</Badge>}
              {p.status !== "new" && <Badge variant="outline" className="text-[10px]">{p.status}</Badge>}
            </span>
            <a href={p.website} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary">{p.domain} <ExternalLink className="h-3 w-3" /></a>
          </div>
          {p.summary && <p className="mt-1 text-muted-foreground">{p.summary}</p>}
          {p.status !== "dismissed" && p.status !== "converted" && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Input defaultValue={p.email ?? ""} placeholder="Email to send requests to" aria-label={`Email for ${p.name}`} className="h-8 w-64 text-xs" onBlur={(e) => { const v = e.target.value.trim(); if (v !== (p.email ?? "")) void act(() => patchProspect(p.id, { email: v }), "Email saved.") }} />
              <Button type="button" size="sm" variant="outline" className="h-8 gap-1 text-[11px]" onClick={() => onInvite(productId, p.id)}><Mail className="h-3.5 w-3.5" /> Ask for information</Button>
              <Button type="button" size="sm" variant="outline" className="h-8 gap-1 text-[11px]" onClick={() => void act(() => convertProspect(p.id), `${p.name} added to your suppliers. Complete their VAT number and account details in Suppliers.`)}><Plus className="h-3.5 w-3.5" /> Add to suppliers</Button>
              <Button type="button" size="sm" variant="ghost" className="h-8 gap-1 text-[11px] hover:text-red-400" onClick={() => void act(() => patchProspect(p.id, { status: "dismissed" }), "Dismissed.")}><X className="h-3.5 w-3.5" /> Dismiss</Button>
            </div>
          )}
        </div>
      ))}
    </CardContent></Card>
  )
}

// ── requests ─────────────────────────────────────────────────────────────────

function RequestsView({ products, notify, openId, setOpenId, draft, clearDraft }: {
  products: Product[]; notify: (t: string, e?: boolean) => void; openId: string | null; setOpenId: (id: string | null) => void
  draft: { product_id: string; quantity?: number; kind?: "RFI" | "RFQ"; prospect_id?: string } | null; clearDraft: () => void
}) {
  const [rows, setRows] = useState<SourcingRequest[] | null>(null)
  const [creating, setCreating] = useState(false)
  const load = useCallback(() => listRequests().then(setRows).catch((e) => notify(errText(e, "Could not load requests"), true)), [notify])
  useEffect(() => { void load() }, [load, openId])
  if (draft || creating) return <NewRequest products={products} preset={draft ?? { product_id: "" }} notify={notify} onCancel={() => { clearDraft(); setCreating(false) }} onCreated={(id) => { clearDraft(); setCreating(false); setOpenId(id); void load() }} />
  if (openId) return <RequestDetailView id={openId} notify={notify} onBack={() => { setOpenId(null); void load() }} />
  return (
    <Card><CardContent className="space-y-3 p-4">
      <div className="flex items-center justify-between"><p className="text-xs text-muted-foreground">Requests for information (RFI) and quotation (RFQ).</p>
        <Button type="button" size="sm" className="h-8 gap-1.5 text-xs" onClick={() => setCreating(true)}><Plus className="h-3.5 w-3.5" /> New request</Button></div>
      {rows === null && <p className="text-xs text-muted-foreground">Loading…</p>}
      {rows?.length === 0 && <p className="text-xs text-muted-foreground">No requests yet.</p>}
      {rows?.map((r) => (
        <button key={r.id} type="button" className="flex w-full flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-card/60 p-3 text-left text-xs hover:border-primary/50" onClick={() => setOpenId(r.id)}>
          <span><strong className="text-foreground">{r.number}</strong> · {r.kind} · {r.product ?? r.title}{r.quantity ? ` × ${r.quantity}` : ""}{r.created_by_agent && <span className="ml-2 text-muted-foreground">prepared by {r.created_by_agent}</span>}</span>
          <span className="flex items-center gap-2 text-muted-foreground">{r.replies ?? 0}/{r.invited ?? 0} replied<Badge variant="outline" className={`text-[10px] ${STATUS_STYLE[r.status]}`}>{r.status.replace("_", " ")}</Badge></span>
        </button>
      ))}
    </CardContent></Card>
  )
}

function NewRequest({ products, preset, notify, onCancel, onCreated }: {
  products: Product[]; preset: { product_id: string; quantity?: number; kind?: "RFI" | "RFQ"; prospect_id?: string }; notify: (t: string, e?: boolean) => void
  onCancel: () => void; onCreated: (id: string) => void
}) {
  const [productId, setProductId] = useState(preset.product_id)
  const [kind, setKind] = useState<"RFI" | "RFQ">(preset.kind ?? "RFQ")
  const [qty, setQty] = useState(preset.quantity ? String(preset.quantity) : "")
  const [needed, setNeeded] = useState("")
  const [target, setTarget] = useState("")
  const [cand, setCand] = useState<Candidates | null>(null)
  const [candError, setCandError] = useState<string | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set(preset.prospect_id ? [`p:${preset.prospect_id}`] : []))
  const [busy, setBusy] = useState(false)
  useEffect(() => { setCand(null); setCandError(null); if (productId) getCandidates(productId).then((c) => { setCand(c); if (!preset.prospect_id) setPicked(new Set(c.suppliers.filter((s) => s.current_source && s.eligible).slice(0, c.protocol.max_suppliers).map((s) => `s:${s.supplier_id}`))) }).catch((e) => setCandError(errText(e, "Could not load suppliers"))) }, [productId]) // eslint-disable-line react-hooks/exhaustive-deps
  const max = cand?.protocol.max_suppliers ?? 5
  const toggle = (key: string) => setPicked((s) => { const n = new Set(s); if (n.has(key)) n.delete(key); else if (n.size < max) n.add(key); else notify(`The protocol allows at most ${max} suppliers per request.`, true); return n })

  async function create() {
    if (!productId) return notify("Choose a product.", true)
    if (picked.size === 0) return notify("Pick at least one supplier to ask.", true)
    setBusy(true)
    try {
      const r = await createRequest({
        kind, product_id: productId, quantity: qty ? Number(qty) : null, needed_by: needed || null, target_price: target ? Number(target) : null, ai: true,
        invitees: [...picked].map((k) => (k.startsWith("s:") ? { supplier_id: k.slice(2) } : { prospect_id: k.slice(2) })),
      })
      notify(`${r.number} drafted${r.drafted_by === "ai" ? " by AI" : ""}. Read the message, then submit it for approval.`)
      onCreated(r.id)
    } catch (e) { notify(errText(e, "Could not create the request"), true) } finally { setBusy(false) }
  }
  return (
    <Card><CardContent className="space-y-4 p-4">
      <Button type="button" variant="ghost" size="sm" className="h-7 gap-1 px-1 text-xs" onClick={onCancel}><ArrowLeft className="h-3.5 w-3.5" /> Back</Button>
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Product"><select className={selectCls} value={productId} onChange={(e) => setProductId(e.target.value)}><option value="">Choose…</option>{products.map((p) => <option key={p.id} value={p.id}>{p.product_number} · {p.name}</option>)}</select></Field>
        <Field label="Type"><select className={selectCls} value={kind} onChange={(e) => setKind(e.target.value as "RFI" | "RFQ")}><option value="RFQ">RFQ: ask for a quotation</option><option value="RFI">RFI: ask for information</option></select></Field>
        <Field label="Quantity"><Input type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} className="h-9 text-xs" /></Field>
        <Field label="Needed by"><Input type="date" value={needed} onChange={(e) => setNeeded(e.target.value)} className="h-9 text-xs" /></Field>
        {kind === "RFQ" && <Field label="Target price (R, internal)" hint="Used for your comparison; only shared with suppliers if the protocol allows."><Input type="number" min={0} step="0.01" value={target} onChange={(e) => setTarget(e.target.value)} className="h-9 text-xs" /></Field>}
      </div>
      <div className="space-y-2">
        <div className="text-xs font-medium text-foreground">Who to ask ({picked.size}/{max})</div>
        {!cand && productId && !candError && <p className="text-xs text-muted-foreground">Loading…</p>}
        {candError && <p className="text-xs text-red-400" role="alert">{candError}</p>}
        {cand?.suppliers.map((s) => (
          <label key={s.supplier_id} className={`flex items-center gap-2 rounded-md border p-2 text-xs ${s.eligible ? "border-border" : "border-border opacity-50"}`}>
            <input type="checkbox" disabled={!s.eligible} checked={picked.has(`s:${s.supplier_id}`)} onChange={() => toggle(`s:${s.supplier_id}`)} />
            <span className="text-foreground">{s.name}</span>
            <Badge variant="outline" className="text-[10px]">{s.kind}</Badge>
            {s.current_source && <Badge variant="outline" className="border-primary/40 text-[10px] text-primary">current supplier</Badge>}
            <span className="text-muted-foreground">{s.score !== null ? `delivery score ${s.score.toFixed(0)}` : "no track record"}{s.kind === "external" && !s.email ? " · no email on file" : ""}{s.reason ? ` · ${s.reason}` : ""}</span>
          </label>
        ))}
        {cand?.prospects.map((p) => (
          <label key={p.id} className="flex items-center gap-2 rounded-md border border-border p-2 text-xs">
            <input type="checkbox" checked={picked.has(`p:${p.id}`)} onChange={() => toggle(`p:${p.id}`)} />
            <span className="text-foreground">{p.name}</span><Badge variant="outline" className="text-[10px]">web prospect</Badge>
            <span className="text-muted-foreground">{p.domain}{p.fit !== null ? ` · fit ${p.fit}%` : ""}{p.email ? "" : " · no email yet"}</span>
          </label>
        ))}
        {cand && cand.suppliers.length === 0 && cand.prospects.length === 0 && <p className="text-xs text-muted-foreground">No suppliers yet. Use “Find suppliers” to search the web.</p>}
      </div>
      <div className="flex justify-end gap-2"><Button type="button" variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
        <Button type="button" size="sm" className="gap-1.5" disabled={busy} onClick={() => void create()}>{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Draft with AI</Button></div>
    </CardContent></Card>
  )
}

function RequestDetailView({ id, notify, onBack }: { id: string; notify: (t: string, e?: boolean) => void; onBack: () => void }) {
  const [r, setR] = useState<RequestDetail | null>(null)
  const [cmp, setCmp] = useState<Comparison | null>(null)
  const [subject, setSubject] = useState("")
  const [body, setBody] = useState("")
  const [busy, setBusy] = useState(false)
  const [reply, setReply] = useState<Invitee | null>(null)
  const load = useCallback(async () => {
    try {
      const d = await getRequest(id)
      setR(d); setSubject(d.subject); setBody(d.body)
      setCmp(d.status === "draft" || d.status === "pending_approval" || d.status === "approved" ? null : await compareRequest(id))
    } catch (e) { notify(errText(e, "Could not load the request"), true) }
  }, [id, notify])
  useEffect(() => { void load() }, [load])
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    try { await fn(); notify(ok); await load() } catch (e) { notify(errText(e, "That did not work"), true) } finally { setBusy(false) }
  }
  if (!r) return <p className="text-xs text-muted-foreground">Loading…</p>
  const editable = r.status === "draft" || r.status === "pending_approval" || r.status === "approved"
  const dirty = subject !== r.subject || body !== r.body
  return (
    <Card><CardContent className="space-y-4 p-4">
      <Button type="button" variant="ghost" size="sm" className="h-7 gap-1 px-1 text-xs" onClick={onBack}><ArrowLeft className="h-3.5 w-3.5" /> All requests</Button>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><strong className="text-sm text-foreground">{r.number}</strong> <span className="text-xs text-muted-foreground">{r.kind} · {r.product ?? r.title}{r.quantity ? ` × ${r.quantity}` : ""}{r.needed_by ? ` · needed by ${r.needed_by}` : ""}</span></div>
        <Badge variant="outline" className={`text-[10px] ${STATUS_STYLE[r.status]}`}>{r.status.replace("_", " ")}</Badge>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between"><span className="text-xs font-medium text-foreground">Message to suppliers {r.drafted_by === "ai" ? "(drafted by AI)" : r.drafted_by === "template" ? "(template)" : "(edited)"}</span>
          {editable && <Button type="button" variant="outline" size="sm" className="h-7 gap-1 text-[11px]" disabled={busy} onClick={() => void run(() => editRequest(id, { regenerate: true }), "Message drafted again.")}><RefreshCw className="h-3 w-3" /> Draft again</Button>}</div>
        <Input value={subject} readOnly={!editable} onChange={(e) => setSubject(e.target.value)} className="h-9 text-xs" aria-label="Subject" />
        <textarea rows={9} value={body} readOnly={!editable} onChange={(e) => setBody(e.target.value)} className={areaCls} aria-label="Message" />
        {editable && dirty && <Button type="button" size="sm" className="h-8 text-xs" disabled={busy} onClick={() => void run(() => editRequest(id, { subject, body }), "Message saved. It needs approving again.")}>Save message</Button>}
        <p className="text-[11px] text-muted-foreground">The message never includes your costs, margins or selling price.</p>
      </div>

      <div className="space-y-1.5">
        <div className="text-xs font-medium text-foreground">Invited</div>
        {r.invitees.map((i) => (
          <div key={i.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border px-3 py-1.5 text-xs">
            <span className="text-foreground">{i.name} <Badge variant="outline" className="ml-1 text-[10px]">{i.kind}</Badge> <span className="text-muted-foreground">{i.email ?? (i.kind === "internal" ? "in-app" : "no email")}</span></span>
            <span className="flex items-center gap-2"><span className={i.status === "failed" ? "text-red-400" : "text-muted-foreground"}>{i.status}{i.error ? `: ${i.error}` : ""}</span>
              {(r.status === "sent" || r.status === "awarded") && <Button type="button" size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => setReply(i)}>{i.status === "replied" || i.status === "declined" ? "Edit reply" : "Record reply"}</Button>}</span>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap justify-end gap-2">
        {r.status === "draft" && <Button type="button" size="sm" disabled={busy || dirty} onClick={() => void run(() => requestAction(id, "submit"), "Submitted.")}>Submit for approval</Button>}
        {r.status === "pending_approval" && <><Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => void run(() => requestAction(id, "reject"), "Sent back to draft.")}>Send back</Button>
          <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => void run(() => requestAction(id, "approve"), "Approved.")}><Check className="mr-1 h-3.5 w-3.5" /> Approve</Button>
          <Button type="button" size="sm" className="gap-1.5" disabled={busy} onClick={() => void run(async () => { const s = await sendRequest(id); notify(s.sent ? `Approved and sent to ${s.sent}${s.failed ? `; ${s.failed} could not be sent` : ""}.` : `Approved, but nothing was sent: ${s.error ?? "see the errors below"}`, !s.sent) }, "")}><Send className="h-3.5 w-3.5" /> Approve and send</Button></>}
        {r.status === "approved" && <Button type="button" size="sm" className="gap-1.5" disabled={busy} onClick={() => void run(async () => { const s = await sendRequest(id); notify(s.sent ? `Sent to ${s.sent}${s.failed ? `; ${s.failed} could not be sent` : ""}.` : `Nothing was sent: ${s.error ?? "see the errors below"}`, !s.sent) }, "")}><Send className="h-3.5 w-3.5" /> Send now</Button>}
        {r.status === "sent" && r.invitees.some((i) => i.status === "failed" || i.status === "invited") && <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => void run(async () => { const s = await sendRequest(id); notify(`Sent to ${s.sent}${s.failed ? `; ${s.failed} still failing` : ""}.`) }, "")}>Send to the rest</Button>}
        {(r.status === "draft" || r.status === "pending_approval" || r.status === "approved" || r.status === "sent") && <Button type="button" size="sm" variant="ghost" className="hover:text-red-400" disabled={busy} onClick={() => void run(() => requestAction(id, "close"), "Closed.")}>Close request</Button>}
      </div>

      {reply && <ReplyForm request={r} invitee={reply} notify={notify} onClose={() => setReply(null)} onSaved={() => { setReply(null); void load() }} existing={r.responses.find((x) => x.invitee_id === reply.id)} />}
      {cmp && <CompareTable cmp={cmp} request={r} notify={notify} onChanged={() => void load()} />}
    </CardContent></Card>
  )
}

function ReplyForm({ request, invitee, existing, notify, onClose, onSaved }: {
  request: RequestDetail; invitee: Invitee; existing?: RequestDetail["responses"][number]; notify: (t: string, e?: boolean) => void; onClose: () => void; onSaved: () => void
}) {
  const [price, setPrice] = useState(existing?.unit_price != null ? String(existing.unit_price) : "")
  const [lead, setLead] = useState(existing?.lead_time_days != null ? String(existing.lead_time_days) : "")
  const [moq, setMoq] = useState(existing?.moq != null ? String(existing.moq) : "")
  const [valid, setValid] = useState(existing?.valid_until ?? "")
  const [notes, setNotes] = useState(existing?.notes ?? "")
  const [declined, setDeclined] = useState(existing?.declined ?? false)
  const [paste, setPaste] = useState("")
  const [read, setRead] = useState<ParsedReply | null>(null)
  const [busy, setBusy] = useState(false)
  async function readIt() {
    setBusy(true)
    try {
      const p = await parseReply(request.id, paste)
      setRead(p); setPrice(p.unit_price != null ? String(p.unit_price) : ""); setLead(p.lead_time_days != null ? String(p.lead_time_days) : ""); setMoq(p.moq != null ? String(p.moq) : "")
      setValid(p.valid_until ?? ""); setNotes(p.notes); setDeclined(p.declined)
    } catch (e) { notify(errText(e, "Could not read the reply"), true) } finally { setBusy(false) }
  }
  async function save() {
    setBusy(true)
    try {
      await recordResponse(request.id, { invitee_id: invitee.id, unit_price: price ? Number(price) : null, lead_time_days: lead ? Number(lead) : null, moq: moq ? Number(moq) : null, valid_until: valid || null, notes, declined, source: read ? "parsed" : "manual" })
      notify(`Reply from ${invitee.name} recorded.`); onSaved()
    } catch (e) { notify(errText(e, "Could not save the reply"), true) } finally { setBusy(false) }
  }
  return (
    <div className="space-y-3 rounded-lg border border-primary/40 bg-primary/5 p-3" role="region" aria-label={`Reply from ${invitee.name}`}>
      <div className="text-xs font-medium text-foreground">Reply from {invitee.name}</div>
      <textarea rows={3} value={paste} onChange={(e) => setPaste(e.target.value)} placeholder="Paste their email here and let AI read the numbers (you confirm them below)" className={areaCls} aria-label="Pasted reply" />
      <Button type="button" size="sm" variant="outline" className="h-8 gap-1.5 text-xs" disabled={busy || paste.trim().length < 5} onClick={() => void readIt()}><Sparkles className="h-3.5 w-3.5" /> Read reply</Button>
      {read && <p className="text-[11px] text-muted-foreground">Read by {read.method === "ai" ? "AI" : "pattern matching"}. Check every number against their email.</p>}
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Unit price (R, ex VAT)"><Input type="number" min={0} step="0.01" value={price} disabled={declined} onChange={(e) => setPrice(e.target.value)} className="h-9 text-xs" /></Field>
        <Field label="Lead time (days)"><Input type="number" min={0} value={lead} disabled={declined} onChange={(e) => setLead(e.target.value)} className="h-9 text-xs" /></Field>
        <Field label="Minimum order"><Input type="number" min={1} value={moq} disabled={declined} onChange={(e) => setMoq(e.target.value)} className="h-9 text-xs" /></Field>
        <Field label="Valid until"><Input type="date" value={valid} disabled={declined} onChange={(e) => setValid(e.target.value)} className="h-9 text-xs" /></Field>
      </div>
      <Field label="Conditions / notes"><Input value={notes} onChange={(e) => setNotes(e.target.value)} className="h-9 text-xs" maxLength={1000} /></Field>
      <label className="flex items-center gap-2 text-xs text-foreground"><input type="checkbox" checked={declined} onChange={(e) => setDeclined(e.target.checked)} /> They declined to quote</label>
      <div className="flex justify-end gap-2"><Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button><Button type="button" size="sm" disabled={busy} onClick={() => void save()}>Save reply</Button></div>
    </div>
  )
}

function CompareTable({ cmp, request, notify, onChanged }: { cmp: Comparison; request: RequestDetail; notify: (t: string, e?: boolean) => void; onChanged: () => void }) {
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Awaited<ReturnType<typeof awardRequest>> | null>(null)
  const [addSource, setAddSource] = useState(true)
  const [preferred, setPreferred] = useState(false)
  const [createPo, setCreatePo] = useState(true)
  const [warehouses, setWarehouses] = useState<{ id: string; name: string }[]>([])
  const [warehouse, setWarehouse] = useState("")
  useEffect(() => { inventoryCall<{ id: string; name: string }[]>("/warehouses").then(setWarehouses).catch(() => setWarehouses([])) }, [])
  const scored = cmp.rows.filter((x) => x.score !== null)
  if (cmp.rows.every((x) => x.score === null && !x.declined)) return <p className="text-xs text-muted-foreground">No replies yet. Record each supplier&apos;s reply to compare them.</p>
  async function award(inviteeId: string) {
    setBusy(true)
    try { const a = await awardRequest(request.id, inviteeId, { reason, add_source: addSource, make_preferred: preferred, create_po: createPo, warehouse_id: warehouse || null }); setResult(a); notify(`${a.name} chosen.`); onChanged() } catch (e) { notify(errText(e, "Could not award"), true) } finally { setBusy(false) }
  }
  return (
    <div className="space-y-2">
      <div className="text-xs font-medium text-foreground">Comparison ({cmp.replies} of the {cmp.needed} quotes the protocol asks for{cmp.ready_to_award ? ": enough to decide" : ""})</div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead><tr className="text-muted-foreground"><th className="py-1 pr-3 font-normal">Supplier</th><th className="px-2 font-normal">Supply score</th><th className="px-2 font-normal">Unit price</th><th className="px-2 font-normal">Lead time</th><th className="px-2 font-normal">MOQ</th><th className="px-2 font-normal">Margin</th><th /></tr></thead>
          <tbody>
            {cmp.rows.map((x) => (
              <tr key={x.invitee_id} className={`border-t border-border align-top ${cmp.best === x.invitee_id ? "bg-emerald-500/5" : ""}`}>
                <td className="py-1.5 pr-3 text-foreground">{x.name} <Badge variant="outline" className="ml-1 text-[10px]">{x.kind}</Badge>{cmp.best === x.invitee_id && <Badge className="ml-1 text-[10px]">Best</Badge>}
                  {x.declined && <div className="text-[10px] text-muted-foreground">Declined to quote</div>}
                  {x.flags.map((f) => <div key={f} className="text-[10px] text-amber-400">{f}</div>)}</td>
                <td className="px-2">{x.score !== null ? <span title={x.breakdown ? `Price ${x.breakdown.price_pts} · lead time ${x.breakdown.lead_pts} · delivery record ${x.breakdown.performance_pts} · completeness ${x.breakdown.completeness_pts}` : ""}>{x.score}</span> : "—"}</td>
                <td className="px-2">{x.unit_price != null ? money(x.unit_price) : "—"}</td>
                <td className="px-2">{x.lead_time_days != null ? `${x.lead_time_days} d` : "—"}</td>
                <td className="px-2">{x.moq ?? "—"}</td>
                <td className="px-2">{x.margin_pct != null ? `${x.margin_pct}%` : "—"}</td>
                <td className="px-2">{x.score !== null && request.status === "sent" && <Button type="button" size="sm" variant="outline" className="h-7 text-[11px]" disabled={busy} onClick={() => void award(x.invitee_id)}>Award</Button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {request.status === "sent" && scored.length > 0 && !cmp.ready_to_award && (
        <Field label="Reason for awarding with fewer quotes than the protocol asks for"><Input value={reason} onChange={(e) => setReason(e.target.value)} className="h-9 text-xs" maxLength={500} /></Field>
      )}
      {request.status === "sent" && scored.length > 0 && (
        <div className="space-y-1.5 rounded-md border border-border p-3 text-xs" aria-label="What awarding does">
          <div className="font-medium text-foreground">When you award a supplier</div>
          <label className="flex items-center gap-2"><input type="checkbox" checked={addSource} onChange={(e) => setAddSource(e.target.checked)} /> Add them to the product as a supplier source at the quoted price and lead time</label>
          <label className={`flex items-center gap-2 pl-6 ${addSource ? "" : "opacity-50"}`}><input type="checkbox" disabled={!addSource} checked={preferred} onChange={(e) => setPreferred(e.target.checked)} /> Make them the preferred supplier (only for a product that is not launched yet)</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={createPo} onChange={(e) => setCreatePo(e.target.checked)} /> Prepare a draft purchase order at the quoted price</label>
          {createPo && warehouses.length > 1 && (
            <div className="pl-6"><select className={`${selectCls} w-56`} value={warehouse} onChange={(e) => setWarehouse(e.target.value)} aria-label="Deliver to"><option value="">Deliver to…</option>{warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select></div>
          )}
        </div>
      )}
      {request.status === "awarded" && <p className="text-xs text-emerald-400">Awarded{request.award_note ? `: ${request.award_note}` : ""}.</p>}
      {result && (
        <div className="space-y-1 rounded-md border border-emerald-500/40 p-3 text-xs" role="status">
          <div className="text-foreground">{result.name} is now one of your suppliers, at {money(result.unit_price)} each.</div>
          {result.source && <div className={result.source.status === "skipped" ? "text-amber-400" : "text-muted-foreground"}>Product: {result.source.status === "skipped" ? "not updated" : result.source.status === "unchanged" ? "already listed on these terms" : `supplier ${result.source.status}${result.source.preferred ? " as preferred" : ""}`}. {result.source.note}</div>}
          {result.purchase_order && <div className={result.purchase_order.status === "skipped" ? "text-amber-400" : "text-muted-foreground"}>Purchase order: {result.purchase_order.status === "drafted" ? `${result.purchase_order.po_number} drafted for ${result.purchase_order.quantity}` : "not created"}. {result.purchase_order.note}</div>}
          {result.flags.map((f) => <div key={f} className="text-amber-400">{f}</div>)}
        </div>
      )}
    </div>
  )
}
