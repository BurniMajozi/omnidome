"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Pencil, Plus, RefreshCcw, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { useBillingTier } from "@/lib/billing-api"
import { fmtMoney } from "@/lib/money"
import {
  asList,
  createItem,
  createTemplate,
  deleteItem,
  deleteTemplate,
  listItems,
  listTemplates,
  updateItem,
  updateTemplate,
  type CatalogItem,
  type InvoiceTemplate,
  type Loadable,
  type ShowColumns,
} from "@/lib/invoicing-api"
import { Field, Modal, Note, inputClass, textareaClass, tierAtLeast, tierTip, useActionState } from "../shared"

export function ItemsTemplatesTab() {
  return (
    <div className="space-y-8">
      <ItemsSection />
      <TemplatesSection />
    </div>
  )
}

// ------------------------------------------------------------------ items

interface ItemForm {
  name: string
  description: string
  unit_price_zar: string
  tax_rate: string
  category: string
  active: boolean
}
const blankItem: ItemForm = { name: "", description: "", unit_price_zar: "", tax_rate: "", category: "", active: true }

function ItemsSection() {
  const { tier } = useBillingTier()
  const canWrite = tierAtLeast(tier, "clerk")
  const isAdmin = tier === "admin"
  const [q, setQ] = useState("")
  const [data, setData] = useState<Loadable<CatalogItem[]>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const [edit, setEdit] = useState<{ id: string | null; form: ItemForm } | null>(null)
  const [confirmDel, setConfirmDel] = useState<string | null>(null)
  const act = useActionState()

  useEffect(() => {
    let off = false
    setData({ state: "loading" })
    listItems({ limit: 200 }).then((l) => {
      if (off) return
      setData(l.state === "ready" ? { state: "ready", data: asList(l.data) } : (l as Loadable<CatalogItem[]>))
    })
    return () => {
      off = true
    }
  }, [tick])
  const reload = useCallback(() => setTick((t) => t + 1), [])

  const rows = useMemo(() => {
    if (data.state !== "ready") return []
    const n = q.trim().toLowerCase()
    return data.data.filter((i) => !n || i.name.toLowerCase().includes(n) || (i.category ?? "").toLowerCase().includes(n))
  }, [data, q])

  const save = async () => {
    if (!edit) return
    const f = edit.form
    if (!f.name.trim()) return act.setMsg({ tone: "error", text: "Name is required." })
    if (f.unit_price_zar.trim() === "" || Number.isNaN(Number(f.unit_price_zar))) return act.setMsg({ tone: "error", text: "Enter a valid unit price." })
    const payload: Partial<CatalogItem> = {
      name: f.name.trim(),
      description: f.description.trim() || null,
      unit_price_zar: f.unit_price_zar.trim(),
      ...(f.tax_rate.trim() !== "" ? { tax_rate: f.tax_rate.trim() } : {}),
      category: f.category.trim() || null,
      active: f.active,
    }
    const r = await act.run("save", () => (edit.id ? updateItem(edit.id, payload) : createItem(payload)))
    if (r) {
      setEdit(null)
      act.clear()
      reload()
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-foreground">Item catalogue</h3>
        <input className={`${inputClass} max-w-xs`} placeholder="Search items…" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button size="sm" variant="ghost" onClick={reload}>
          <RefreshCcw className="h-3.5 w-3.5" />
          Refresh
        </Button>
        <Button size="sm" className="ml-auto" disabled={!canWrite} title={!canWrite ? tierTip("clerk") : undefined} onClick={() => { act.clear(); setEdit({ id: null, form: blankItem }) }}>
          <Plus className="h-3.5 w-3.5" />
          New item
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">Picking a catalogue item copies its price onto the line; later price changes or deletions never alter issued documents.</p>
      {act.msg && !edit && <Note tone={act.msg.tone}>{act.msg.text}</Note>}

      {data.state !== "ready" ? (
        <NotConnected loadable={data} service="Billing" onRetry={reload} />
      ) : data.data.length === 0 ? (
        <NoDataYet message="The catalogue is empty. Add the products and services you invoice for." />
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Category</th>
                <th className="px-3 py-2 text-right">Unit price</th>
                <th className="px-3 py-2 text-right">VAT %</th>
                <th className="px-3 py-2">Active</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.id} className="border-t border-border">
                  <td className="px-3 py-2">
                    <p className="font-medium text-foreground">{i.name}</p>
                    {i.description && <p className="text-xs text-muted-foreground">{i.description}</p>}
                  </td>
                  <td className="px-3 py-2 text-xs">{i.category ?? "—"}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(i.unit_price_zar)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{i.tax_rate ?? "default"}</td>
                  <td className="px-3 py-2">{i.active ? <Badge className="badge-success">Active</Badge> : <Badge variant="secondary">Inactive</Badge>}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex justify-end gap-1">
                      <Button size="icon-sm" variant="ghost" aria-label={`Edit ${i.name}`} disabled={!canWrite} onClick={() => { act.clear(); setEdit({ id: i.id, form: { name: i.name, description: i.description ?? "", unit_price_zar: String(i.unit_price_zar), tax_rate: i.tax_rate === null || i.tax_rate === undefined ? "" : String(i.tax_rate), category: i.category ?? "", active: i.active } }) }}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      {confirmDel === i.id ? (
                        <>
                          <Button size="sm" variant="destructive" disabled={!!act.busy} onClick={async () => { const r = await act.run("del", () => deleteItem(i.id), "Item deleted."); setConfirmDel(null); if (r !== undefined) reload() }}>
                            Delete
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setConfirmDel(null)}>
                            Cancel
                          </Button>
                        </>
                      ) : (
                        <Button size="icon-sm" variant="ghost-destructive" aria-label={`Delete ${i.name}`} disabled={!isAdmin} title={!isAdmin ? tierTip("admin") : undefined} onClick={() => setConfirmDel(i.id)}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={!!edit} onOpenChange={(o) => !o && setEdit(null)} title={edit?.id ? "Edit item" : "New item"}>
        {edit && (
          <div className="space-y-3">
            {act.msg && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
            <Field label="Name">
              <input className={inputClass} value={edit.form.name} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, name: e.target.value } })} />
            </Field>
            <Field label="Description">
              <textarea className={textareaClass} value={edit.form.description} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, description: e.target.value } })} />
            </Field>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Unit price (R)">
                <input className={inputClass} inputMode="decimal" value={edit.form.unit_price_zar} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, unit_price_zar: e.target.value } })} />
              </Field>
              <Field label="VAT %" hint="Empty = default">
                <input className={inputClass} inputMode="decimal" value={edit.form.tax_rate} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, tax_rate: e.target.value } })} />
              </Field>
              <Field label="Category">
                <input className={inputClass} value={edit.form.category} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, category: e.target.value } })} />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={edit.form.active} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, active: e.target.checked } })} />
              Active (available in the invoice builder)
            </label>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setEdit(null)}>
                Cancel
              </Button>
              <Button size="sm" disabled={!!act.busy} onClick={save}>
                {act.busy === "save" ? "Saving…" : "Save item"}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </section>
  )
}

// ------------------------------------------------------------------ templates

const COLS: Array<[keyof ShowColumns, string]> = [
  ["description", "Description"],
  ["quantity", "Qty"],
  ["unit_price", "Unit price"],
  ["discount", "Discount"],
  ["tax", "VAT"],
  ["line_total", "Line total"],
]

const blankTemplate = (): InvoiceTemplate => ({
  name: "",
  is_default: false,
  company_name: "",
  company_address: "",
  vat_number: "",
  logo_url: "",
  accent_colour: "#2563eb",
  footer: "",
  payment_details: "",
  default_terms: "",
  default_due_days: 30,
  show_columns: { description: true, quantity: true, unit_price: true, discount: true, tax: true, line_total: true },
  show_payment_details: true,
  show_terms: true,
})

const HEX = /^#[0-9a-fA-F]{6}$/

function TemplatesSection() {
  const { tier } = useBillingTier()
  const isAdmin = tier === "admin"
  const [data, setData] = useState<Loadable<InvoiceTemplate[]>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const [edit, setEdit] = useState<InvoiceTemplate | null>(null)
  const [confirmDel, setConfirmDel] = useState<string | null>(null)
  const act = useActionState()

  useEffect(() => {
    let off = false
    setData({ state: "loading" })
    listTemplates().then((l) => {
      if (off) return
      setData(l.state === "ready" ? { state: "ready", data: asList(l.data) } : (l as Loadable<InvoiceTemplate[]>))
    })
    return () => {
      off = true
    }
  }, [tick])
  const reload = useCallback(() => setTick((t) => t + 1), [])

  const save = async () => {
    if (!edit) return
    if (!edit.name.trim()) return act.setMsg({ tone: "error", text: "Template name is required." })
    if (edit.accent_colour && !HEX.test(edit.accent_colour)) return act.setMsg({ tone: "error", text: "Accent colour must be #rrggbb." })
    if (edit.logo_url && !/^https?:\/\//i.test(edit.logo_url)) return act.setMsg({ tone: "error", text: "Logo URL must start with http:// or https://." })
    const body: InvoiceTemplate = { ...edit, name: edit.name.trim(), logo_url: edit.logo_url?.trim() || null, default_due_days: Number(edit.default_due_days) || 30 }
    delete (body as { id?: string }).id
    delete (body as { builtin?: boolean }).builtin
    const r = await act.run("save", () => (edit.id ? updateTemplate(edit.id, body) : createTemplate(body)), "Template saved.")
    if (r) {
      setEdit(null)
      reload()
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-foreground">Document templates</h3>
        <Button size="sm" variant="ghost" onClick={reload}>
          <RefreshCcw className="h-3.5 w-3.5" />
          Refresh
        </Button>
        <Button size="sm" className="ml-auto" disabled={!isAdmin} title={!isAdmin ? tierTip("admin") : undefined} onClick={() => { act.clear(); setEdit(blankTemplate()) }}>
          <Plus className="h-3.5 w-3.5" />
          New template
        </Button>
      </div>
      {act.msg && !edit && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
      {data.state !== "ready" ? (
        <NotConnected loadable={data} service="Billing" onRetry={reload} />
      ) : data.data.length === 0 ? (
        <NoDataYet message="No templates." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {data.data.map((t, i) => (
            <div key={t.id ?? `builtin-${i}`} className="space-y-2 rounded-md border border-border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium text-foreground">{t.name || "Built-in default"}</p>
                {t.is_default && <Badge className="badge-info">Default</Badge>}
                {t.builtin && <Badge variant="secondary">Built-in</Badge>}
                {t.id && (
                  <div className="ml-auto flex gap-1">
                    <Button size="icon-sm" variant="ghost" aria-label={`Edit ${t.name}`} disabled={!isAdmin} title={!isAdmin ? tierTip("admin") : undefined} onClick={() => { act.clear(); setEdit({ ...blankTemplate(), ...t, show_columns: { ...blankTemplate().show_columns, ...(t.show_columns ?? {}) }, company_name: t.company_name ?? "", company_address: t.company_address ?? "", vat_number: t.vat_number ?? "", logo_url: t.logo_url ?? "", footer: t.footer ?? "", payment_details: t.payment_details ?? "", default_terms: t.default_terms ?? "", accent_colour: t.accent_colour ?? "#2563eb" }) }}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    {confirmDel === t.id ? (
                      <>
                        <Button size="sm" variant="destructive" disabled={!!act.busy} onClick={async () => { const r = await act.run("del", () => deleteTemplate(t.id as string), "Template deleted."); setConfirmDel(null); if (r !== undefined) reload() }}>
                          Delete
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setConfirmDel(null)}>
                          Cancel
                        </Button>
                      </>
                    ) : (
                      <Button size="icon-sm" variant="ghost-destructive" aria-label={`Delete ${t.name}`} disabled={!isAdmin} title={!isAdmin ? tierTip("admin") : undefined} onClick={() => setConfirmDel(t.id as string)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                )}
              </div>
              <TemplatePreview t={t} />
            </div>
          ))}
        </div>
      )}

      <Modal open={!!edit} onOpenChange={(o) => !o && setEdit(null)} title={edit?.id ? "Edit template" : "New template"} description="The first template becomes the default; making another the default clears the old one." wide>
        {edit && (
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
            <div className="space-y-3">
              {act.msg && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Template name">
                  <input className={inputClass} value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
                </Field>
                <Field label="Default due days">
                  <input className={inputClass} inputMode="numeric" value={edit.default_due_days ?? ""} onChange={(e) => setEdit({ ...edit, default_due_days: e.target.value === "" ? null : Number(e.target.value) })} />
                </Field>
                <Field label="Company name">
                  <input className={inputClass} value={edit.company_name ?? ""} onChange={(e) => setEdit({ ...edit, company_name: e.target.value })} />
                </Field>
                <Field label="VAT number">
                  <input className={inputClass} value={edit.vat_number ?? ""} onChange={(e) => setEdit({ ...edit, vat_number: e.target.value })} />
                </Field>
                <Field label="Logo URL (http/https)" className="sm:col-span-2">
                  <input className={inputClass} value={edit.logo_url ?? ""} onChange={(e) => setEdit({ ...edit, logo_url: e.target.value })} placeholder="https://…/logo.png" />
                </Field>
                <Field label="Accent colour">
                  <div className="flex gap-2">
                    <input type="color" aria-label="Accent colour picker" className="h-9 w-12 rounded border border-border bg-background" value={HEX.test(edit.accent_colour ?? "") ? (edit.accent_colour as string) : "#2563eb"} onChange={(e) => setEdit({ ...edit, accent_colour: e.target.value })} />
                    <input className={inputClass} value={edit.accent_colour ?? ""} onChange={(e) => setEdit({ ...edit, accent_colour: e.target.value })} placeholder="#2563eb" />
                  </div>
                </Field>
                <label className="flex items-center gap-2 self-end pb-2 text-sm">
                  <input type="checkbox" checked={edit.is_default} onChange={(e) => setEdit({ ...edit, is_default: e.target.checked })} />
                  Default template
                </label>
                <Field label="Company address" className="sm:col-span-2">
                  <textarea className={textareaClass} value={edit.company_address ?? ""} onChange={(e) => setEdit({ ...edit, company_address: e.target.value })} />
                </Field>
                <Field label="Payment details (bank, reference)" className="sm:col-span-2">
                  <textarea className={textareaClass} value={edit.payment_details ?? ""} onChange={(e) => setEdit({ ...edit, payment_details: e.target.value })} />
                </Field>
                <Field label="Default terms" className="sm:col-span-2">
                  <textarea className={textareaClass} value={edit.default_terms ?? ""} onChange={(e) => setEdit({ ...edit, default_terms: e.target.value })} />
                </Field>
                <Field label="Footer" className="sm:col-span-2">
                  <textarea className={textareaClass} value={edit.footer ?? ""} onChange={(e) => setEdit({ ...edit, footer: e.target.value })} />
                </Field>
              </div>
              <fieldset className="rounded-md border border-border p-3">
                <legend className="px-1 text-xs text-muted-foreground">Columns and sections shown</legend>
                <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
                  {COLS.map(([k, label]) => (
                    <label key={k} className="flex items-center gap-1.5">
                      <input type="checkbox" checked={edit.show_columns[k]} onChange={(e) => setEdit({ ...edit, show_columns: { ...edit.show_columns, [k]: e.target.checked } })} />
                      {label}
                    </label>
                  ))}
                  <label className="flex items-center gap-1.5">
                    <input type="checkbox" checked={edit.show_payment_details} onChange={(e) => setEdit({ ...edit, show_payment_details: e.target.checked })} />
                    Payment details
                  </label>
                  <label className="flex items-center gap-1.5">
                    <input type="checkbox" checked={edit.show_terms} onChange={(e) => setEdit({ ...edit, show_terms: e.target.checked })} />
                    Terms
                  </label>
                </div>
              </fieldset>
              <div className="flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={() => setEdit(null)}>
                  Cancel
                </Button>
                <Button size="sm" disabled={!!act.busy} onClick={save}>
                  {act.busy === "save" ? "Saving…" : "Save template"}
                </Button>
              </div>
            </div>
            <div>
              <p className="mb-2 text-xs text-muted-foreground">Layout preview</p>
              <TemplatePreview t={edit} />
            </div>
          </div>
        )}
      </Modal>
    </section>
  )
}

/** Schematic layout preview driven by the template fields. Uses no real invoice data. */
function TemplatePreview({ t }: { t: InvoiceTemplate }) {
  const accent = HEX.test(t.accent_colour ?? "") ? (t.accent_colour as string) : "#2563eb"
  const cols = COLS.filter(([k]) => t.show_columns?.[k] !== false)
  const safeLogo = t.logo_url && /^https?:\/\//i.test(t.logo_url) ? t.logo_url : null
  return (
    <div className="space-y-2 rounded-md border border-border bg-white p-3 text-[11px] text-neutral-700">
      <div className="flex items-start justify-between gap-2 border-b-2 pb-2" style={{ borderColor: accent }}>
        <div className="min-w-0">
          {safeLogo ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={safeLogo} alt="Logo" referrerPolicy="no-referrer" className="mb-1 max-h-10 max-w-[8rem] object-contain" />
          ) : null}
          <p className="font-semibold text-neutral-900">{t.company_name || "Company name"}</p>
          {t.company_address && <p className="whitespace-pre-line">{t.company_address}</p>}
          {t.vat_number && <p>VAT {t.vat_number}</p>}
        </div>
        <p className="text-base font-bold" style={{ color: accent }}>
          INVOICE
        </p>
      </div>
      <div className="overflow-hidden rounded border border-neutral-200">
        <div className="flex text-white" style={{ background: accent }}>
          {cols.map(([k, label]) => (
            <span key={k} className={`px-1.5 py-1 ${k === "description" ? "flex-[3]" : "flex-1 text-right"}`}>
              {label}
            </span>
          ))}
        </div>
        <div className="flex text-neutral-400">
          {cols.map(([k]) => (
            <span key={k} className={`px-1.5 py-1 ${k === "description" ? "flex-[3]" : "flex-1 text-right"}`}>
              {k === "description" ? "Line items appear here" : "…"}
            </span>
          ))}
        </div>
      </div>
      {t.show_payment_details && t.payment_details && <p className="whitespace-pre-line"><span className="font-semibold">Payment details: </span>{t.payment_details}</p>}
      {t.show_terms && t.default_terms && <p className="whitespace-pre-line"><span className="font-semibold">Terms: </span>{t.default_terms}</p>}
      {t.footer && <p className="border-t border-neutral-200 pt-1 text-center text-neutral-500">{t.footer}</p>}
      <p className="text-center text-[10px] text-neutral-400">Layout preview only. No invoice data is shown.</p>
    </div>
  )
}
