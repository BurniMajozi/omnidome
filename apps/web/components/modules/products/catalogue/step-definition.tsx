"use client"

import { useState } from "react"
import { Check, Lock, Pencil, Sparkles, Undo2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import type { Nature, Usage } from "@/lib/catalogue-api"
import { Field, areaCls, draftDescription, selectCls } from "./shared"
import { ManagedSelect } from "./managed-select"
import { NUMBER_RE, type StepProps } from "./wizard-types"

const STYLES = ["Customer-friendly", "Technical summary", "Short portal description"] as const

export function StepDefinition({ form, set, setDef, products, lists, reloadLists, notify, locked }: StepProps) {
  const d = form.definition
  const [editingNumber, setEditingNumber] = useState(false)
  const [numberText, setNumberText] = useState("")
  const [style, setStyle] = useState<(typeof STYLES)[number]>("Customer-friendly")
  const [suggestion, setSuggestion] = useState("")

  const numberLocked = locked
  const shownNumber = form.custom_number || (form.id ? form.product_number : "Assigned on save")

  function saveNumber() {
    const v = numberText.trim().toUpperCase()
    if (!NUMBER_RE.test(v)) return notify("Use 3–24 letters, digits or hyphens.")
    if (products.some((p) => p.id !== form.id && p.product_number === v)) return notify(`${v} is already used by another product.`)
    set({ custom_number: v })
    setEditingNumber(false)
  }

  function draftWithAi() {
    if (!form.name.trim()) return notify("Enter a product name first.")
    const names = d.components.map((c) => {
      const x = products.find((p) => p.id === c.product_id)
      return x ? `${c.qty} × ${x.name}` : ""
    }).filter(Boolean)
    setSuggestion(draftDescription(form, style, names))
  }

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

      <div className="grid gap-1.5 text-xs text-muted-foreground">
        <label htmlFor="pd-desc">Product description</label>
        <textarea id="pd-desc" rows={4} value={d.description} onChange={(e) => setDef({ description: e.target.value })} className={areaCls} />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span>Need help wording it?</span>
          <div className="flex items-center gap-2">
            <select value={style} onChange={(e) => setStyle(e.target.value as (typeof STYLES)[number])} className={`${selectCls} w-auto`} aria-label="Description style">
              {STYLES.map((s) => <option key={s}>{s}</option>)}
            </select>
            <Button type="button" size="sm" variant="outline" className="h-9 gap-1.5 text-xs" onClick={draftWithAi}><Sparkles className="h-3.5 w-3.5" /> Draft with AI</Button>
          </div>
        </div>
        {suggestion && (
          <div className="rounded-lg border border-primary/40 bg-primary/5 p-3.5" role="region" aria-label="Suggested description">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <strong className="text-xs text-foreground">Suggested description</strong>
              <Badge variant="outline" className="border-amber-500/40 text-[10px] text-amber-400">Template draft · no model connected</Badge>
            </div>
            <textarea rows={4} value={suggestion} onChange={(e) => setSuggestion(e.target.value)} className={`${areaCls} mt-2`} aria-label="Suggested text" />
            <p className="mt-1.5 text-[11px]">Built only from the fields you entered. Your current description is untouched until you apply it.</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button type="button" size="sm" className="h-8 text-xs" onClick={() => { setDef({ description: suggestion.trim() }); setSuggestion(""); notify("Description updated. Review it before submitting.") }}>Replace description</Button>
              <Button type="button" size="sm" variant="outline" className="h-8 text-xs" disabled={!d.description} onClick={() => { setDef({ description: `${d.description.trim()} ${suggestion.trim()}` }); setSuggestion("") }}>Append</Button>
              <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={draftWithAi}>Regenerate</Button>
              <Button type="button" size="sm" variant="ghost" className="h-8 text-xs" onClick={() => setSuggestion("")}>Dismiss</Button>
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
    </div>
  )
}
