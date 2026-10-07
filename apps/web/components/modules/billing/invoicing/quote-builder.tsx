"use client"

/**
 * <QuoteBuilder/> - editor for quotes (customers or field-sales prospects).
 *
 * Props (all optional except `mode`)
 *   mode           "create" | "edit". Only DRAFT quotes are editable.
 *   initial        QuoteDoc (edit) or pre-filled values (create).
 *   customer       { id, label, email? } pre-selected CRM customer. With `lockCustomer` the picker is hidden.
 *   lockCustomer   true when the host already knows the customer.
 *   allowProspect  default true: lets the user quote a prospect (name/email/phone/address) instead of a CRM
 *                  customer. Prospect quotes need a customer_id before they can be converted to an invoice.
 *   source         "billing" (default; stored as "other") | "field_sales" | "technician".
 *   createdBy      free text stored as created_by (agent / technician).
 *   onSaved        (quote, action) => void   action = saved | sent | accepted | declined | converted
 *   onConverted    (invoice) => void          called with the new DRAFT invoice after "Convert to invoice"
 *   onCancel       renders a Close button when given.
 *   hidePreview    skip the live document column (small screens).
 *
 * Totals typed here are a client-side estimate; the server's figures replace them on every save.
 * Quotes never touch the ledger. Accept / decline here record a decision on behalf of the customer
 * (internal, with a note); the customer's own decision arrives through the public share link.
 */

import { useMemo, useState } from "react"
import { Check, FileOutput, Save, Send, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useBillingTier } from "@/lib/billing-api"
import {
  acceptQuote,
  convertQuote,
  createQuote,
  declineQuote,
  getQuote,
  markQuoteSent,
  updateQuote,
  type InvoiceDetail,
  type QuoteDoc,
  type QuoteInput,
  type QuoteSource,
} from "@/lib/invoicing-api"
import { fmtMoney } from "@/lib/money"
import { Field, Note, StatusBadge, addDaysIso, inputClass, textareaClass, tierAtLeast, tierTip, todayIso, useActionState } from "../shared"
import { CustomerPicker, DocumentPreview, LinesGrid, TemplatePicker, useCatalog, useTemplates, type PickedCustomer } from "./doc-editor"
import { DocumentActions } from "./document-actions"
import { blankLine, fromServerLines, toLineInputs, type EditableLine } from "./doc-math"
import type { BuilderSource } from "./invoice-builder"

export type QuoteSavedAction = "saved" | "sent" | "accepted" | "declined" | "converted"

export interface QuoteBuilderProps {
  mode: "create" | "edit"
  initial?: Partial<QuoteDoc>
  customer?: PickedCustomer | null
  lockCustomer?: boolean
  allowProspect?: boolean
  source?: BuilderSource
  createdBy?: string
  onSaved?: (quote: QuoteDoc, action: QuoteSavedAction) => void
  onConverted?: (invoice: InvoiceDetail) => void
  onCancel?: () => void
  hidePreview?: boolean
}

const SOURCE: Record<BuilderSource, QuoteSource> = { billing: "other", field_sales: "field_sales", technician: "technician" }

export function QuoteBuilder({ mode, initial, customer, lockCustomer, allowProspect = true, source = "billing", createdBy, onSaved, onConverted, onCancel, hidePreview }: QuoteBuilderProps) {
  const { tier } = useBillingTier()
  const canWrite = tierAtLeast(tier, "clerk")
  const isAdmin = tier === "admin"
  const act = useActionState()
  const catalog = useCatalog()
  const tpl = useTemplates()

  const [saved, setSaved] = useState<Partial<QuoteDoc> | undefined>(mode === "edit" ? initial : undefined)
  const [cust, setCust] = useState<PickedCustomer | null>(
    customer ?? (initial?.customer_id ? { id: initial.customer_id, label: initial.prospect?.name || "Customer", email: initial.prospect?.email } : null),
  )
  const [useProspect, setUseProspect] = useState<boolean>(!customer && !initial?.customer_id && !!initial?.prospect?.name)
  const [prospect, setProspect] = useState({
    name: initial?.prospect?.name ?? "",
    email: initial?.prospect?.email ?? "",
    phone: initial?.prospect?.phone ?? "",
    address: initial?.prospect?.address ?? "",
  })
  const [lines, setLines] = useState<EditableLine[]>(() => {
    const l = fromServerLines(initial?.lines)
    return l.length ? l : [blankLine()]
  })
  const [issueDate, setIssueDate] = useState(initial?.issue_date ?? todayIso())
  const [validUntil, setValidUntil] = useState(initial?.valid_until ?? addDaysIso(todayIso(), 30))
  const [po, setPo] = useState(initial?.po_number ?? "")
  const [notes, setNotes] = useState(initial?.notes ?? "")
  const [terms, setTerms] = useState(initial?.terms ?? "")
  const [templateId, setTemplateId] = useState(initial?.template_id ?? "")
  const [previewKey, setPreviewKey] = useState(0)
  const [note, setNote] = useState("")
  const [dueDate, setDueDate] = useState("")
  const [force, setForce] = useState(false)

  const id = saved?.id ?? null
  const status = saved?.status ?? "draft"
  const editable = (!id || status === "draft") && canWrite
  const locked = !editable || !!act.busy
  const customerLocked = !!lockCustomer || !!id

  const body = useMemo((): QuoteInput => {
    const b: QuoteInput = {
      lines: toLineInputs(lines),
      notes,
      terms,
      po_number: po,
      template_id: templateId || undefined,
      issue_date: issueDate || undefined,
      valid_until: validUntil || undefined,
    }
    return b
  }, [lines, notes, terms, po, templateId, issueDate, validUntil])

  const validate = (): string | null => {
    if (!id) {
      if (useProspect) {
        if (!prospect.name.trim()) return "Enter the prospect's name."
      } else if (!cust) return "Choose a customer or switch to a prospect."
    }
    if (toLineInputs(lines).length === 0) return "Add at least one line with a description and price."
    if (toLineInputs(lines).some((l) => !l.description)) return "Every line needs a description."
    return null
  }

  const persist = async (): Promise<QuoteDoc | null> => {
    const bad = validate()
    if (bad) {
      act.setMsg({ tone: "error", text: bad })
      return null
    }
    const r = await act.run("save", () =>
      id
        ? updateQuote(id, body)
        : createQuote({
            ...body,
            source: SOURCE[source],
            ...(createdBy ? { created_by: createdBy } : {}),
            ...(useProspect
              ? { prospect_name: prospect.name.trim(), prospect_email: prospect.email.trim(), prospect_phone: prospect.phone.trim(), prospect_address: prospect.address.trim() }
              : { customer_id: cust?.id }),
          }),
    )
    if (!r) return null
    setSaved(r)
    const sv = fromServerLines(r.lines)
    if (sv.length) setLines(sv)
    setPreviewKey((k) => k + 1)
    return r
  }

  const saveDraft = async () => {
    const r = await persist()
    if (r) {
      act.setMsg({ tone: "success", text: `Quote ${r.number} saved. Server total ${fmtMoney(r.total_zar)} (authoritative).` })
      onSaved?.(r, "saved")
    }
  }

  const transition = async (key: "sent" | "accepted" | "declined") => {
    if (!id) return
    const fn = key === "sent" ? () => markQuoteSent(id) : key === "accepted" ? () => acceptQuote(id, note.trim() || undefined) : () => declineQuote(id, note.trim() || undefined)
    const r = await act.run(key, fn, key === "sent" ? "Marked as sent (nothing was emailed; use Email below to send it)." : key === "accepted" ? "Recorded as accepted." : "Recorded as declined.")
    if (r) {
      setSaved(r)
      setPreviewKey((k) => k + 1)
      onSaved?.(r, key)
    }
  }

  const convert = async () => {
    if (!id) return
    const r = await act.run(
      "convert",
      () => convertQuote(id, { ...(dueDate ? { due_date: dueDate } : {}), ...(cust ? { customer_id: cust.id } : {}), ...(force ? { force: true } : {}) }),
      (d) => (d?.created ? `Draft invoice ${d.invoice.number} created. Issue it from the Invoices tab.` : `Already converted: invoice ${d?.invoice.number} (no duplicate created).`),
    )
    if (r) {
      setSaved(r.quote)
      onSaved?.(r.quote, "converted")
      onConverted?.(r.invoice)
    }
  }

  const prospectOnly = !saved?.customer_id && !cust

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-foreground">{id ? saved?.number ?? "Quote" : "New quote"}</h3>
        {id && <StatusBadge status={status} />}
        {source !== "billing" && <span className="rounded bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">source: {source.replace("_", " ")}</span>}
      </div>

      {!canWrite && <Note>{tier === "none" ? "Your role could not be verified, so editing is disabled." : tierTip("clerk")}. You can still view.</Note>}
      {id && status !== "draft" && <Note>Only drafts are editable.</Note>}
      {act.msg && <Note tone={act.msg.tone}>{act.msg.text}</Note>}

      <div className={hidePreview ? "space-y-5" : "grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]"}>
        <div className="min-w-0 space-y-4">
          <div className="space-y-2">
            {allowProspect && !customerLocked && (
              <div className="flex gap-3 text-xs">
                <label className="flex items-center gap-1">
                  <input type="radio" checked={!useProspect} disabled={locked} onChange={() => setUseProspect(false)} />
                  CRM customer
                </label>
                <label className="flex items-center gap-1">
                  <input type="radio" checked={useProspect} disabled={locked} onChange={() => setUseProspect(true)} />
                  Prospect (not in CRM)
                </label>
              </div>
            )}
            {useProspect && !customerLocked ? (
              <div className="grid gap-2 sm:grid-cols-2">
                <Field label="Prospect name">
                  <input className={inputClass} value={prospect.name} disabled={locked} onChange={(e) => setProspect({ ...prospect, name: e.target.value })} />
                </Field>
                <Field label="Email">
                  <input className={inputClass} value={prospect.email} disabled={locked} onChange={(e) => setProspect({ ...prospect, email: e.target.value })} />
                </Field>
                <Field label="Phone">
                  <input className={inputClass} value={prospect.phone} disabled={locked} onChange={(e) => setProspect({ ...prospect, phone: e.target.value })} />
                </Field>
                <Field label="Address">
                  <input className={inputClass} value={prospect.address} disabled={locked} onChange={(e) => setProspect({ ...prospect, address: e.target.value })} />
                </Field>
              </div>
            ) : customerLocked && (cust || saved?.prospect?.name) ? (
              <div className="rounded-md border border-border bg-secondary/30 px-3 py-2 text-sm text-foreground">
                {cust?.label ?? saved?.prospect?.name}
                {(cust?.email ?? saved?.prospect?.email) && <span className="ml-2 text-xs text-muted-foreground">{cust?.email ?? saved?.prospect?.email}</span>}
              </div>
            ) : (
              <Field label="Customer">
                <CustomerPicker value={cust} onChange={setCust} disabled={locked} />
              </Field>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Issue date">
              <input type="date" className={inputClass} value={issueDate} disabled={locked} onChange={(e) => setIssueDate(e.target.value)} />
            </Field>
            <Field label="Valid until">
              <input type="date" className={inputClass} value={validUntil} disabled={locked} onChange={(e) => setValidUntil(e.target.value)} />
            </Field>
            <Field label="PO / reference">
              <input className={inputClass} value={po} disabled={locked} maxLength={80} onChange={(e) => setPo(e.target.value)} />
            </Field>
          </div>

          <LinesGrid lines={lines} onChange={setLines} catalog={catalog.items} catalogState={catalog.state} disabled={locked} />

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Notes">
              <textarea className={textareaClass} value={notes} disabled={locked} onChange={(e) => setNotes(e.target.value)} />
            </Field>
            <Field label="Terms" hint="Empty = the template's default terms">
              <textarea className={textareaClass} value={terms} disabled={locked} onChange={(e) => setTerms(e.target.value)} />
            </Field>
          </div>
        </div>

        {!hidePreview && (
          <div className="min-w-0 space-y-3">
            <Field label="Template">
              <TemplatePicker templates={tpl.templates} state={tpl.state} value={templateId} onChange={setTemplateId} disabled={locked} />
            </Field>
            <DocumentPreview kind="quotes" id={id} refreshKey={previewKey} />
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
        {editable && (
          <Button size="sm" disabled={!!act.busy} onClick={saveDraft}>
            <Save className="h-3.5 w-3.5" />
            {act.busy === "save" ? "Saving…" : id ? "Save changes" : "Save draft"}
          </Button>
        )}
        {id && status === "draft" && (
          <Button size="sm" variant="outline" disabled={!!act.busy || !canWrite} title={!canWrite ? tierTip("clerk") : "Marks the quote sent without emailing it"} onClick={() => transition("sent")}>
            <Send className="h-3.5 w-3.5" />
            Mark sent
          </Button>
        )}
        {onCancel && (
          <Button size="sm" variant="ghost" className="ml-auto" onClick={onCancel}>
            Close
          </Button>
        )}
      </div>

      {id && ["sent", "viewed"].includes(status) && (
        <div className="flex flex-wrap items-end gap-2 rounded-md border border-border p-3">
          <Field label="Decision note (optional, internal)" className="min-w-[14rem] flex-1">
            <input className={inputClass} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <Button size="sm" variant="outline" disabled={!!act.busy || !canWrite} title={!canWrite ? tierTip("clerk") : undefined} onClick={() => transition("accepted")}>
            <Check className="h-3.5 w-3.5" />
            Record accepted
          </Button>
          <Button size="sm" variant="outline" disabled={!!act.busy || !canWrite} title={!canWrite ? tierTip("clerk") : undefined} onClick={() => transition("declined")}>
            <X className="h-3.5 w-3.5" />
            Record declined
          </Button>
        </div>
      )}

      {id && (status === "accepted" || status === "converted" || (isAdmin && ["sent", "viewed", "expired"].includes(status))) && (
        <div className="space-y-2 rounded-md border border-border p-3">
          <p className="text-xs font-semibold text-foreground">Convert to invoice</p>
          {status === "converted" && <Note tone="success">Converted{saved?.converted_invoice_id ? ` (invoice ${saved.converted_invoice_id.slice(0, 8)})` : ""}. Converting again returns the same invoice.</Note>}
          {prospectOnly && status !== "converted" && <Note tone="info">This is a prospect quote: pick a CRM customer first (search above after reloading as a customer) before converting.</Note>}
          {!saved?.customer_id && !customerLocked && (
            <Field label="Customer for the invoice">
              <CustomerPicker value={cust} onChange={setCust} disabled={!!act.busy} />
            </Field>
          )}
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Invoice due date" hint="Empty = template default">
              <input type="date" className={inputClass} value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
            </Field>
            {isAdmin && status !== "accepted" && status !== "converted" && (
              <label className="flex items-center gap-1 pb-2 text-xs text-muted-foreground">
                <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
                Force (admin; quote was not accepted)
              </label>
            )}
            <Button size="sm" disabled={!!act.busy || !canWrite || (status !== "accepted" && status !== "converted" && !force)} title={!canWrite ? tierTip("clerk") : undefined} onClick={convert}>
              <FileOutput className="h-3.5 w-3.5" />
              {act.busy === "convert" ? "Converting…" : "Convert to invoice"}
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">The result is a draft invoice; nothing posts to finance until it is issued.</p>
        </div>
      )}

      {id && (
        <div className="border-t border-border pt-4">
          <DocumentActions kind="quote" id={id} number={saved?.number} status={status} defaultEmail={cust?.email ?? saved?.prospect?.email} onChanged={() => { getQuote(id).then((l) => { if (l.state === "ready") { setSaved(l.data); setPreviewKey((k) => k + 1) } }) }} />
        </div>
      )}
    </div>
  )
}
