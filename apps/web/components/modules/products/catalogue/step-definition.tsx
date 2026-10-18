"use client"

import { useRef, useState } from "react"
import { Check, FileText, Loader2, Lock, Pencil, Sparkles, Trash2, Undo2, Upload, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { deleteAsset, setBarcode, suggestDescription, uploadAsset, type Asset, type Nature, type Usage } from "@/lib/catalogue-api"
import { Field, areaCls, draftDescription, selectCls } from "./shared"
import { BarcodeSvg, PrintLabelButton } from "./barcode"
import { ManagedSelect } from "./managed-select"
import { NUMBER_RE, toInput, type StepProps } from "./wizard-types"

const STYLES = ["Customer-friendly", "Technical summary", "Short portal description"] as const
const PROTOCOLS = ["None", "TR-069", "OMCI", "NETCONF", "SNMP"] as const

export function StepDefinition({ form, set, setDef, products, lists, reloadLists, notify, locked, ensureSaved }: StepProps) {
  const d = form.definition
  const [editingNumber, setEditingNumber] = useState(false)
  const [numberText, setNumberText] = useState("")
  const [style, setStyle] = useState<(typeof STYLES)[number]>("Customer-friendly")
  const [suggestion, setSuggestion] = useState<{ text: string; note: string } | null>(null)
  const [drafting, setDrafting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [manualCode, setManualCode] = useState("")
  const sheetInput = useRef<HTMLInputElement>(null)
  const barcodeBox = useRef<HTMLDivElement>(null)

  const numberLocked = locked
  const shownNumber = form.custom_number || (form.id ? form.product_number : "Assigned on save")
  const sheets = d.documents.filter((x) => x.category === "Fact sheet")
  const physical = form.nature === "Physical item"

  function saveNumber() {
    const v = numberText.trim().toUpperCase()
    if (!NUMBER_RE.test(v)) return notify("Use 3–24 letters, digits or hyphens.")
    if (products.some((p) => p.id !== form.id && p.product_number === v)) return notify(`${v} is already used by another product.`)
    set({ custom_number: v })
    setEditingNumber(false)
  }

  async function draftWithAi() {
    if (!form.name.trim()) return notify("Enter a product name first.")
    setDrafting(true)
    try {
      if (sheets.length && form.id) {
        const r = await suggestDescription(form.id, style, toInput(form))
        setSuggestion({
          text: r.text,
          note: r.method === "ai"
            ? `Drafted by ${r.model ?? "a language model"} from ${r.sheets.join(", ")}.`
            : (r.note ?? `Built from sentences in ${r.sheets.join(", ")}.`),
        })
      } else {
        const names = d.components.map((c) => {
          const x = products.find((p) => p.id === c.product_id)
          return x ? `${c.qty} × ${x.name}` : ""
        }).filter(Boolean)
        setSuggestion({ text: draftDescription(form, style, names), note: "Template draft from the fields you entered. Upload a fact sheet for a richer draft." })
      }
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not draft a description")
    } finally {
      setDrafting(false)
    }
  }

  async function addSheet(files: FileList | null) {
    if (!files?.length) return
    setBusy(true)
    try {
      const id = await ensureSaved()
      const added: Asset[] = []
      for (const file of Array.from(files)) {
        try {
          const r = await uploadAsset(id, file, "fact_sheet")
          added.push({ id: r.id, name: r.name, kind: "Document", extension: r.extension, size: r.size, url: r.url, alt: r.name, visibility: "Internal only",
            primary: false, category: "Fact sheet", version: "1", effective: new Date().toISOString().slice(0, 10), acceptance: false })
          notify(`${r.name} read (${r.text_chars?.toLocaleString("en-ZA")} characters). Use “Draft with AI” to write from it.`)
        } catch (e) {
          notify(e instanceof Error ? e.message : `Could not read ${file.name}`)
        }
      }
      if (added.length) setDef({ documents: [...d.documents, ...added] })
    } catch (e) {
      notify(e instanceof Error ? e.message : "Save the draft first.")
    } finally {
      setBusy(false)
      if (sheetInput.current) sheetInput.current.value = ""
    }
  }

  async function removeSheet(a: Asset) {
    try { await deleteAsset(a.id) } catch { /* already gone */ }
    setDef({ documents: d.documents.filter((x) => x.id !== a.id) })
  }

  async function barcode(mode: "generate" | "manufacturer" | "clear", value?: string) {
    setBusy(true)
    try {
      const id = await ensureSaved()
      const p = await setBarcode(id, { mode, value })
      setDef({ barcode: p.definition.barcode })
      set({ revision: p.revision })
      setManualCode("")
      notify(mode === "clear" ? "Barcode removed." : `Barcode ${p.definition.barcode.value} linked to ${p.product_number}.`)
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not set the barcode")
    } finally {
      setBusy(false)
    }
  }

  const toggleIdentifier = (name: "Serial number" | "MAC address", on: boolean) =>
    setDef({ identifiers: on ? [...new Set([...d.identifiers, name])] : d.identifiers.filter((x) => x !== name) })

  const ranges = lists.categories[form.category] ?? []
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-foreground">What is this product?</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Nothing is preloaded. Category, range and service family are managed lists: pen to rename, plus to add, bin to delete (blocked while a product uses the value).
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-1.5 text-xs text-muted-foreground">
          <span>Product number</span>
          {editingNumber ? (
            <div className="flex items-center gap-1.5">
              <Input autoFocus value={numberText} maxLength={24} onChange={(e) => setNumberText(e.target.value)} className="h-9 font-mono text-xs" aria-label="Product number"
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); saveNumber() } if (e.key === "Escape") setEditingNumber(false) }} />
              <Button type="button" size="sm" className="h-9 w-9 p-0" onClick={saveNumber} aria-label="Save number"><Check className="h-4 w-4" /></Button>
              <Button type="button" size="sm" variant="outline" className="h-9 w-9 p-0" onClick={() => setEditingNumber(false)} aria-label="Cancel"><X className="h-4 w-4" /></Button>
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <Input readOnly value={form.custom_number ? `${shownNumber} (custom)` : shownNumber} className="h-9 font-mono text-xs" aria-label="Product number" />
              {numberLocked ? (
                <span className="flex h-9 w-9 items-center justify-center rounded-md border border-border" title="The number is fixed once a product is launched" aria-label="Number locked"><Lock className="h-3.5 w-3.5" /></span>
              ) : (
                <>
                  <Button type="button" size="sm" variant="outline" className="h-9 w-9 shrink-0 p-0" title="Set a custom number" aria-label="Edit product number"
                    onClick={() => { setNumberText(form.custom_number || (form.id ? form.product_number : "")); setEditingNumber(true) }}><Pencil className="h-3.5 w-3.5" /></Button>
                  {form.custom_number && (
                    <Button type="button" size="sm" variant="outline" className="h-9 w-9 shrink-0 p-0" title="Back to auto-assigned" aria-label="Reset to auto-assigned number" onClick={() => set({ custom_number: "" })}><Undo2 className="h-3.5 w-3.5" /></Button>
                  )}
                </>
              )}
            </div>
          )}
          <span className="text-[11px] text-muted-foreground/80">3–24 letters, digits or hyphens; unique; never reused.</span>
        </div>

        <Field label="Internal product name">
          <Input value={form.name} onChange={(e) => set({ name: e.target.value })} className="h-9 text-xs" />
        </Field>
        <Field label="Customer-facing name" hint="Shown on quotes, invoices and the portal. Optional.">
          <Input value={d.customer_name} onChange={(e) => setDef({ customer_name: e.target.value })} className="h-9 text-xs" />
        </Field>
        <Field label="Product owner">
          <Input value={form.owner} onChange={(e) => set({ owner: e.target.value })} className="h-9 text-xs" />
        </Field>

        <ManagedSelect label="Category" kind="category" value={form.category} options={Object.keys(lists.categories)} lists={lists} disabled={locked}
          onChange={(v) => set({ category: v, range: "" })} onListsChanged={reloadLists} notify={notify} />
        <ManagedSelect label="Range" kind="range" value={form.range} options={ranges} parent={form.category} lists={lists} disabled={locked || !form.category}
          onChange={(v) => set({ range: v })} onListsChanged={reloadLists} notify={notify} />

        <Field label="Product nature" hint="Fixed values: validation, stock and billing rules depend on them.">
          <select value={form.nature} disabled={locked} className={selectCls} onChange={(e) => { const nature = e.target.value as Nature; set({ nature }); setDef({ recurring: nature === "Digital service" }) }}>
            <option>Digital service</option><option>Physical item</option><option>Professional service</option>
          </select>
        </Field>
        <Field label="Primary usage">
          <select value={form.usage} disabled={locked} className={selectCls} onChange={(e) => set({ usage: e.target.value as Usage })}>
            <option>Customer-facing</option><option>Internal consumable</option><option>Company-owned asset</option>
          </select>
        </Field>
        <ManagedSelect label="Service family" kind="family" value={form.family} options={lists.families} lists={lists} disabled={locked}
          onChange={(v) => set({ family: v })} onListsChanged={reloadLists} notify={notify} />
      </div>
      {locked && <p className="text-[11px] text-amber-400">This product is launched. Identity and classification change through a revision, not a direct edit.</p>}

      <div className="space-y-3 rounded-lg border border-border p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h4 className="text-xs font-semibold text-foreground">Product fact sheets</h4>
            <p className="text-[11px] text-muted-foreground">Upload the manufacturer or supplier sheet (PDF, DOCX or TXT). OmniDome reads it so “Draft with AI” can write the description from the real specifications, and it is added to the knowledge base for search.</p>
          </div>
          <Button type="button" variant="outline" size="sm" className="gap-1.5 text-xs" disabled={busy} onClick={() => sheetInput.current?.click()}>
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />} Add fact sheet
          </Button>
          <input ref={sheetInput} type="file" multiple hidden accept=".pdf,.docx,.txt" onChange={(e) => void addSheet(e.target.files)} />
        </div>
        {sheets.length === 0 && <p className="text-xs text-muted-foreground">No fact sheet yet.</p>}
        {sheets.map((a) => (
          <div key={a.id} className="flex items-center justify-between rounded-md border border-border px-3 py-1.5 text-xs">
            <span className="flex items-center gap-2"><FileText className="h-4 w-4 text-primary" />{a.name}</span>
            <Button type="button" variant="ghost" size="sm" className="h-7 w-7 p-0 hover:text-red-400" aria-label={`Remove ${a.name}`} onClick={() => void removeSheet(a)}><Trash2 className="h-3.5 w-3.5" /></Button>
          </div>
        ))}
      </div>

      <div className="grid gap-1.5 text-xs text-muted-foreground">
        <label htmlFor="pd-desc">Product description</label>
        <textarea id="pd-desc" rows={4} value={d.description} onChange={(e) => setDef({ description: e.target.value })} className={areaCls} />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span>{sheets.length ? "Will draft from your fact sheet." : "Need help wording it?"}</span>
          <div className="flex items-center gap-2">
            <select value={style} onChange={(e) => setStyle(e.target.value as (typeof STYLES)[number])} className={`${selectCls} w-auto`} aria-label="Description style">
              {STYLES.map((s) => <option key={s}>{s}</option>)}
            </select>
            <Button type="button" size="sm" variant="outline" className="h-9 gap-1.5 text-xs" disabled={drafting} onClick={() => void draftWithAi()}>
              {drafting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} {drafting ? "Drafting…" : "Draft with AI"}
            </Button>
          </div>
        </div>
        {suggestion && (
          <div className="rounded-lg border border-primary/40 bg-primary/5 p-3.5" role="region" aria-label="Suggested description">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <strong className="text-xs text-foreground">Suggested description</strong>
              <Badge variant="outline" className="border-amber-500/40 text-[10px] text-amber-400">Review before using</Badge>
            </div>
            <textarea rows={4} value={suggestion.text} onChange={(e) => setSuggestion({ ...suggestion, text: e.target.value })} className={`${areaCls} mt-2`} aria-label="Suggested text" />
            <p className="mt-1.5 text-[11px]">{suggestion.note} Your current description is untouched until you apply it.</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button type="button" size="sm" className="h-8 text-xs" onClick={() => { setDef({ description: suggestion.text.trim() }); setSuggestion(null); notify("Description updated. Review it before submitting.") }}>Replace description</Button>
              <Button type="button" size="sm" variant="outline" className="h-8 text-xs" disabled={!d.description} onClick={() => { setDef({ description: `${d.description.trim()} ${suggestion.text.trim()}` }); setSuggestion(null) }}>Append</Button>
              <Button type="button" size="sm" variant="outline" className="h-8 text-xs" disabled={drafting} onClick={() => void draftWithAi()}>Regenerate</Button>
              <Button type="button" size="sm" variant="ghost" className="h-8 text-xs" onClick={() => setSuggestion(null)}>Dismiss</Button>
            </div>
          </div>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold text-foreground">{form.nature === "Digital service" ? "Service definition" : "Fulfilment definition"}</h3>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          {form.nature === "Digital service" ? (
            <>
              <Field label="Download speed (Mbps)"><Input type="number" min={0} value={d.down ?? ""} onChange={(e) => setDef({ down: e.target.value === "" ? null : Number(e.target.value) })} className="h-9 text-xs" /></Field>
              <Field label="Upload speed (Mbps)"><Input type="number" min={0} value={d.up ?? ""} onChange={(e) => setDef({ up: e.target.value === "" ? null : Number(e.target.value) })} className="h-9 text-xs" /></Field>
            </>
          ) : (
            <>
              <Field label="Stock tracking">
                <select value={d.stock} className={selectCls} onChange={(e) => setDef({ stock: e.target.value })}>
                  <option>None</option><option>Quantity</option><option>Serial number</option><option>Batch</option>
                </select>
              </Field>
              <Field label="Unit of measure">
                <select value={d.unit} className={selectCls} onChange={(e) => setDef({ unit: e.target.value })}>
                  <option>Each</option><option>Metre</option><option>Hour</option><option>Visit</option>
                </select>
              </Field>
            </>
          )}
        </div>
      </div>

      {physical && (
        <div className="space-y-4 rounded-lg border border-border p-4">
          <div>
            <h4 className="text-xs font-semibold text-foreground">Identification</h4>
            <p className="text-[11px] text-muted-foreground">A product is a type of item; each unit you receive has its own serial number and, for network devices, a MAC address. Choose what stock must capture on every unit, then give the product a barcode.</p>
          </div>
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground">Captured on every unit received</div>
            <label className="flex items-center gap-2 text-xs text-foreground">
              <input type="checkbox" checked={d.identifiers.includes("Serial number") || d.stock === "Serial number"} disabled={d.stock === "Serial number"} onChange={(e) => toggleIdentifier("Serial number", e.target.checked)} />
              Serial number {d.stock === "Serial number" && <span className="text-muted-foreground">(required by serial stock tracking)</span>}
            </label>
            <label className="flex items-center gap-2 text-xs text-foreground">
              <input type="checkbox" checked={d.identifiers.includes("MAC address")} onChange={(e) => toggleIdentifier("MAC address", e.target.checked)} /> MAC address
            </label>
            {d.stock === "None" && d.identifiers.length > 0 && <p className="text-[11px] text-amber-400">Set stock tracking to “Serial number” so units are tracked individually.</p>}
          </div>

          <div className="space-y-2">
            <div className="text-xs text-muted-foreground">Barcode</div>
            {d.barcode.value ? (
              <div className="flex flex-wrap items-start gap-3">
                <div ref={barcodeBox}><BarcodeSvg value={d.barcode.value} format={d.barcode.format} /></div>
                <div className="space-y-1.5 text-xs">
                  <div className="text-foreground">{d.barcode.format} · {d.barcode.source === "generated" ? "generated by OmniDome" : "manufacturer's code"}</div>
                  <div className="flex flex-wrap gap-2">
                    <PrintLabelButton name={d.customer_name || form.name} number={form.product_number || "New product"} host={() => barcodeBox.current} />
                    <Button type="button" variant="outline" size="sm" className="h-8 text-xs" disabled={busy} onClick={() => void barcode("clear")}>Remove</Button>
                  </div>
                </div>
              </div>
            ) : <p className="text-xs text-muted-foreground">No barcode yet.</p>}
            <div className="flex flex-wrap items-end gap-2">
              <Button type="button" variant="outline" size="sm" className="h-9 gap-1.5 text-xs" disabled={busy} onClick={() => void barcode("generate")}>{d.barcode.value ? "Generate a new barcode" : "Generate barcode"}</Button>
              <Field label="Or use the manufacturer's barcode">
                <div className="flex gap-2">
                  <Input value={manualCode} onChange={(e) => setManualCode(e.target.value)} placeholder="EAN-13 or code from the packaging" className="h-9 w-64 text-xs" />
                  <Button type="button" variant="outline" size="sm" className="h-9 text-xs" disabled={busy || !manualCode.trim()} onClick={() => void barcode("manufacturer", manualCode.trim())}>Use</Button>
                </div>
              </Field>
            </div>
            <p className="text-[11px] text-muted-foreground">Generated codes are internal EAN-13s (prefix 2, for in-store use). The barcode is linked to the stock item so scanners find the product.</p>
          </div>
        </div>
      )}

      {form.nature !== "Professional service" && (
        <div className="space-y-3 rounded-lg border border-border p-4">
          <div>
            <h4 className="text-xs font-semibold text-foreground">Provisioning</h4>
            <p className="text-[11px] text-muted-foreground">{physical ? "How this device is configured and managed on the network once it is installed." : "How the service is activated on the network."}</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Protocol">
              <select value={d.provisioning.protocol} className={selectCls} onChange={(e) => setDef({ provisioning: { ...d.provisioning, protocol: e.target.value as typeof PROTOCOLS[number] } })}>
                {PROTOCOLS.map((p) => <option key={p}>{p}</option>)}
              </select>
            </Field>
            <Field label="Provisioning profile" hint="The profile or template name on the provisioning server">
              <Input value={d.provisioning.profile} disabled={d.provisioning.protocol === "None"} onChange={(e) => setDef({ provisioning: { ...d.provisioning, profile: e.target.value } })} className="h-9 text-xs" />
            </Field>
          </div>
        </div>
      )}
    </div>
  )
}
