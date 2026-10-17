"use client"

import { useRef, useState } from "react"
import { Download, FileText, Plus, Star, Trash2, Upload } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { deleteAsset, downloadAsset, uploadAsset, type Asset, type Competitor } from "@/lib/catalogue-api"
import { AuthImage, Field, kpiSet, money, selectCls } from "./shared"
import type { StepProps } from "./wizard-types"

const IMAGE_EXT = ["png", "jpg", "jpeg", "webp", "avif", "gif"]
const MODEL_EXT = ["glb", "gltf", "usdz"]
const DOC_EXT = ["pdf", "docx", "txt"]
const DOC_CATEGORIES = ["Terms & conditions", "Fee schedule", "Instructions", "Manual", "Warranty", "Installation guide", "Other"]
const ext = (name: string) => (name.includes(".") ? name.split(".").pop()!.toLowerCase() : "")
const iconDanger = "h-8 w-8 p-0 hover:border-red-500/60 hover:text-red-400"

// ── Step 5: media, documents and policies ────────────────────────────────────

export function StepMedia({ form, setDef, ensureSaved, notify }: StepProps) {
  const d = form.definition
  const mediaInput = useRef<HTMLInputElement>(null)
  const docInput = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [policy, setPolicy] = useState("")

  async function add(files: FileList | null, group: "media" | "documents") {
    if (!files?.length) return
    setBusy(true)
    try {
      const id = await ensureSaved()
      const added: Asset[] = []
      for (const file of Array.from(files)) {
        const e = ext(file.name)
        const okExt = group === "media" ? [...IMAGE_EXT, ...MODEL_EXT] : DOC_EXT
        if (!okExt.includes(e)) { notify(`Unsupported file type: ${file.name}`); continue }
        if (file.size > 15 * 1024 * 1024) { notify(`${file.name} exceeds 15 MB.`); continue }
        try {
          const r = await uploadAsset(id, file)
          added.push({
            id: r.id, name: r.name, kind: r.kind, extension: r.extension, size: r.size, url: r.url, alt: form.name || r.name,
            visibility: "Internal only", primary: group === "media" && d.media.length === 0 && added.length === 0,
            category: group === "documents" ? "Manual" : "Other", version: "1", effective: new Date().toISOString().slice(0, 10), acceptance: false,
          })
        } catch (err) {
          notify(err instanceof Error ? err.message : `Could not upload ${file.name}`)
        }
      }
      if (added.length) {
        setDef(group === "media" ? { media: [...d.media, ...added] } : { documents: [...d.documents, ...added] })
        notify(`${added.length} file(s) uploaded. Choose what customers can see, then save the draft.`)
      }
    } catch (err) {
      notify(err instanceof Error ? err.message : "Save the draft first.")
    } finally {
      setBusy(false)
      if (mediaInput.current) mediaInput.current.value = ""
      if (docInput.current) docInput.current.value = ""
    }
  }

  async function remove(group: "media" | "documents", a: Asset) {
    try { await deleteAsset(a.id) } catch { /* already gone */ }
    const rest = d[group].filter((x) => x.id !== a.id)
    if (group === "media" && a.primary && rest[0]) rest[0] = { ...rest[0], primary: true }
    setDef({ [group]: rest } as never)
  }
  const patchAsset = (group: "media" | "documents", id: string, patch: Partial<Asset>) =>
    setDef({ [group]: d[group].map((x) => (x.id === id ? { ...x, ...patch } : x)) } as never)
  const setPrimary = (id: string) => setDef({ media: d.media.map((m) => ({ ...m, primary: m.id === id })) })

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Media, policies &amp; product documents</h3>
        <p className="mt-1 text-xs text-muted-foreground">Keep the material that explains the product with its definition. New files are internal until you choose Customer portal.</p>
      </div>

      {form.nature === "Physical item" ? (
        <div className="space-y-3 rounded-lg border border-border p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div><h4 className="text-xs font-semibold text-foreground">Product gallery</h4><p className="text-[11px] text-muted-foreground">Photos, GIFs and 3D models: PNG, JPEG, WebP, AVIF, GIF, GLB, glTF, USDZ, up to 15 MB.</p></div>
            <Button type="button" variant="outline" size="sm" className="gap-1.5 text-xs" disabled={busy} onClick={() => mediaInput.current?.click()}><Upload className="h-3.5 w-3.5" /> Add pictures</Button>
            <input ref={mediaInput} type="file" multiple hidden accept={[...IMAGE_EXT, ...MODEL_EXT].map((e) => `.${e}`).join(",")} onChange={(e) => void add(e.target.files, "media")} />
          </div>
          {d.media.length === 0 && <p className="text-xs text-muted-foreground">No pictures yet. The product directory shows a placeholder until you add one.</p>}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {d.media.map((m) => (
              <div key={m.id} className="rounded-lg border border-border bg-card/60 p-2.5">
                <div className="relative">
                  {m.kind === "3D" ? <div className="flex aspect-[4/3] items-center justify-center rounded-md bg-muted/30 text-xs text-muted-foreground">3D model · {m.extension.toUpperCase()}</div> : <AuthImage asset={m} alt={m.alt} className="aspect-[4/3] w-full rounded-md" />}
                  {m.primary && <Badge className="absolute left-1.5 top-1.5 gap-1 text-[10px]"><Star className="h-3 w-3" /> Primary</Badge>}
                </div>
                <div className="mt-2 space-y-2">
                  <Field label="Alt text"><Input value={m.alt} onChange={(e) => patchAsset("media", m.id, { alt: e.target.value })} className="h-8 text-xs" /></Field>
                  <Field label="Visibility"><select value={m.visibility} className={selectCls} onChange={(e) => patchAsset("media", m.id, { visibility: e.target.value as Asset["visibility"] })}><option>Internal only</option><option>Customer portal</option></select></Field>
                  <div className="flex items-center justify-between">
                    <Button type="button" variant="ghost" size="sm" className="h-7 text-[11px]" disabled={m.primary || m.kind === "3D"} onClick={() => setPrimary(m.id)}>Make primary</Button>
                    <Button type="button" variant="outline" size="sm" className={iconDanger} aria-label={`Remove ${m.name}`} onClick={() => void remove("media", m)}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">The picture gallery appears when Nature is set to Physical item. Digital and professional services can still attach documents below.</p>
      )}

      <div className="space-y-3 rounded-lg border border-border p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div><h4 className="text-xs font-semibold text-foreground">Documents</h4><p className="text-[11px] text-muted-foreground">T&amp;C documents, fee schedules, instructions, manuals, warranties. PDF, DOCX or TXT, up to 15 MB.</p></div>
          <Button type="button" variant="outline" size="sm" className="gap-1.5 text-xs" disabled={busy} onClick={() => docInput.current?.click()}><Upload className="h-3.5 w-3.5" /> Add documents</Button>
          <input ref={docInput} type="file" multiple hidden accept={DOC_EXT.map((e) => `.${e}`).join(",")} onChange={(e) => void add(e.target.files, "documents")} />
        </div>
        {d.documents.length === 0 && <p className="text-xs text-muted-foreground">No documents attached yet.</p>}
        {d.documents.map((a) => (
          <div key={a.id} className="rounded-lg border border-border bg-card/60 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-xs font-medium text-foreground"><FileText className="h-4 w-4 text-primary" />{a.name}</span>
              <span className="flex gap-1.5">
                <Button type="button" variant="outline" size="sm" className="h-8 w-8 p-0" aria-label={`Download ${a.name}`} onClick={() => void downloadAsset(a)}><Download className="h-3.5 w-3.5" /></Button>
                <Button type="button" variant="outline" size="sm" className={iconDanger} aria-label={`Remove ${a.name}`} onClick={() => void remove("documents", a)}><Trash2 className="h-3.5 w-3.5" /></Button>
              </span>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-4">
              <Field label="Document type"><select value={a.category} className={selectCls} onChange={(e) => patchAsset("documents", a.id, { category: e.target.value })}>{DOC_CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
              <Field label="Visibility"><select value={a.visibility} className={selectCls} onChange={(e) => patchAsset("documents", a.id, { visibility: e.target.value as Asset["visibility"] })}><option>Internal only</option><option>Customer portal</option></select></Field>
              <Field label="Version"><Input value={a.version} onChange={(e) => patchAsset("documents", a.id, { version: e.target.value })} className="h-9 text-xs" /></Field>
              <Field label="Effective"><Input type="date" value={a.effective} onChange={(e) => patchAsset("documents", a.id, { effective: e.target.value })} className="h-9 text-xs" /></Field>
            </div>
            <label className="mt-2 flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={a.acceptance} onChange={(e) => patchAsset("documents", a.id, { acceptance: e.target.checked })} /> Customer must accept this version at order</label>
          </div>
        ))}
      </div>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <div><h4 className="text-xs font-semibold text-foreground">Fee policy and T&amp;C references</h4><p className="text-[11px] text-muted-foreground">Reference the approved invoice fee policy or terms by name and version. Customers see these on quotes, invoices and the portal.</p></div>
        {d.policy_refs.map((r, i) => (
          <div key={i} className="flex items-center justify-between rounded-md border border-border px-3 py-1.5 text-xs">
            <span>{r}</span>
            <Button type="button" variant="ghost" size="sm" className="h-7 w-7 p-0 hover:text-red-400" aria-label={`Remove ${r}`} onClick={() => setDef({ policy_refs: d.policy_refs.filter((_, k) => k !== i) })}><Trash2 className="h-3.5 w-3.5" /></Button>
          </div>
        ))}
        <div className="flex gap-2">
          <Input value={policy} placeholder="e.g. Early-termination policy v2" onChange={(e) => setPolicy(e.target.value)} className="h-9 text-xs" aria-label="Policy reference"
            onKeyDown={(e) => { if (e.key === "Enter" && policy.trim()) { e.preventDefault(); setDef({ policy_refs: [...d.policy_refs, policy.trim()] }); setPolicy("") } }} />
          <Button type="button" variant="outline" size="sm" className="h-9 gap-1.5 text-xs" disabled={!policy.trim()} onClick={() => { setDef({ policy_refs: [...d.policy_refs, policy.trim()] }); setPolicy("") }}><Plus className="h-3.5 w-3.5" /> Add</Button>
        </div>
      </div>
    </div>
  )
}

// ── Step 6: competitor research and KPIs ─────────────────────────────────────

export function StepResearch({ form, setDef, notify }: StepProps) {
  const d = form.definition
  const rows = d.research.rows
  const kpis = d.research.kpis
  const setRows = (r: Competitor[]) => setDef({ research: { ...d.research, rows: r } })
  const upd = (i: number, patch: Partial<Competitor>) => setRows(rows.map((c, k) => (k === i ? { ...c, ...patch } : c)))
  const prices = rows.map((r) => Number(r.price)).filter((n) => n > 0).sort((a, b) => a - b)
  const median = prices.length ? (prices.length % 2 ? prices[(prices.length - 1) / 2] : (prices[prices.length / 2 - 1] + prices[prices.length / 2]) / 2) : 0
  const mine = Number(d.price)
  const catalog = kpiSet(form.nature)
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Research and performance tracking</h3>
        <p className="mt-1 text-xs text-muted-foreground">Compare this SKU with the market before you commit, then choose the KPIs it will be tracked on once live.</p>
      </div>
      <div className="space-y-3 rounded-lg border border-border p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-xs font-semibold text-foreground">Competitor analysis</h4>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" className="gap-1.5 text-xs" onClick={() => setRows([...rows, { name: "", offer: "", price: "", spec: "", term: "", date: new Date().toISOString().slice(0, 10), source: "" }])}><Plus className="h-3.5 w-3.5" /> Add competitor</Button>
            <Button type="button" variant="outline" size="sm" className="text-xs" onClick={() => notify("Automated research needs a web-research connector, which is not connected. Add competitors manually for now.")}>✦ Research with AI</Button>
          </div>
        </div>
        {rows.length === 0 && <p className="text-xs text-muted-foreground">No competitors recorded.</p>}
        {rows.map((c, i) => (
          <div key={i} className="rounded-lg border border-border bg-card/60 p-3">
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Competitor"><Input value={c.name} onChange={(e) => upd(i, { name: e.target.value })} className="h-9 text-xs" /></Field>
              <Field label="Offer / plan"><Input value={c.offer} onChange={(e) => upd(i, { offer: e.target.value })} className="h-9 text-xs" /></Field>
              <Field label="Price (R, ex tax)"><Input type="number" min={0} step="0.01" value={c.price ?? ""} onChange={(e) => upd(i, { price: e.target.value })} className="h-9 text-xs" /></Field>
              <Field label="Speed / spec"><Input value={c.spec} onChange={(e) => upd(i, { spec: e.target.value })} className="h-9 text-xs" /></Field>
              <Field label="Contract term"><Input value={c.term} onChange={(e) => upd(i, { term: e.target.value })} className="h-9 text-xs" /></Field>
              <Field label="Date checked"><Input type="date" value={c.date} onChange={(e) => upd(i, { date: e.target.value })} className="h-9 text-xs" /></Field>
              <Field label="Source URL or note" className="sm:col-span-3"><Input value={c.source} onChange={(e) => upd(i, { source: e.target.value })} className="h-9 text-xs" /></Field>
            </div>
            <div className="mt-2 flex justify-end"><Button type="button" variant="outline" size="sm" className={iconDanger} aria-label="Remove competitor" onClick={() => setRows(rows.filter((_, k) => k !== i))}><Trash2 className="h-3.5 w-3.5" /></Button></div>
          </div>
        ))}
        <p className="text-xs text-muted-foreground">
          {prices.length && mine > 0
            ? `Your price ${money(mine)} is ${mine > median ? "above" : mine < median ? "below" : "at"} the competitor median ${money(median)} (range ${money(prices[0])} to ${money(prices[prices.length - 1])}; ${prices.filter((x) => x < mine).length} of ${prices.length} are cheaper).`
            : "Add competitor prices and set your price to see positioning."}
        </p>
      </div>
      <div className="space-y-2 rounded-lg border border-border p-4">
        <h4 className="text-xs font-semibold text-foreground">KPIs this product is tracked on</h4>
        <p className="text-[11px] text-muted-foreground">Read from the owning module after launch. The choices depend on the product nature.</p>
        {catalog.map((k) => (
          <label key={k.key} className="flex items-center gap-2 py-1 text-xs text-foreground">
            <input type="checkbox" checked={kpis.includes(k.key)} onChange={(e) => setDef({ research: { ...d.research, kpis: e.target.checked ? [...new Set([...kpis, k.key])] : kpis.filter((x) => x !== k.key) } })} />
            {k.label} <span className="text-muted-foreground">· {k.source}</span>
          </label>
        ))}
      </div>
    </div>
  )
}
