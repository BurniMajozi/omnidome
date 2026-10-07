"use client"

/**
 * <InvoiceBuilder/> - Invoice-Ninja-style editor for manual / one-off invoices.
 *
 * Props (all optional except `mode`)
 *   mode           "create" | "edit". Edit loads `initial` (an InvoiceDetail, typically from getInvoiceDetail).
 *                  Only DRAFT invoices are editable; any other status renders read-only with lifecycle actions.
 *   initial        InvoiceDetail for edit mode (or pre-filled values for create, e.g. lines from a quote).
 *   customer       { id, label, email? } pre-selected CRM customer. With `lockCustomer` the picker is hidden.
 *   lockCustomer   true when the host app already knows the customer (e.g. technician at a job).
 *   source         "billing" (default, stored as manual) | "field_sales" | "technician": stored as source_type.
 *   createdBy      free text stored as created_by (e.g. the agent / technician name or id).
 *   onSaved        (invoice, action) => void   action = saved | issued | duplicated | voided | credited
 *   onCancel       renders a Cancel/Close button when given.
 *   hidePreview    true on small screens to skip the live document column.
 *
 * Rules: totals shown while typing are a client-side estimate only; the server recomputes everything and its
 * values replace them after each save. Issuing posts revenue to finance (irreversible except by void / credit
 * note), so "Save & issue" asks for confirmation. Role limits are hints; the server enforces and its message
 * is shown verbatim (e.g. discounts above the clerk limit need an admin).
 */

import { useEffect, useMemo, useState } from "react"
import { Ban, Copy, FilePlus2, Save, Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { createCreditNote, useBillingTier, voidInvoice } from "@/lib/billing-api"
import {
  createManualInvoice,
  duplicateInvoice,
  issueInvoice,
  updateInvoice,
  type InvoiceDetail,
  type InvoiceInput,
  type SourceType,
} from "@/lib/invoicing-api"
import { fmtMoney } from "@/lib/money"
import { Field, Note, StatusBadge, inputClass, textareaClass, tierAtLeast, tierTip, todayIso, useActionState } from "../shared"
import { CustomerPicker, DocumentPreview, LinesGrid, TemplatePicker, useCatalog, useTemplates, type PickedCustomer } from "./doc-editor"
import { DocumentActions } from "./document-actions"
import { blankLine, fromServerLines, toLineInputs, type EditableLine } from "./doc-math"

export type BuilderSource = "billing" | "field_sales" | "technician"
export type InvoiceSavedAction = "saved" | "issued" | "duplicated" | "voided" | "credited"

export interface InvoiceBuilderProps {
  mode: "create" | "edit"
  initial?: Partial<InvoiceDetail>
  customer?: PickedCustomer | null
  lockCustomer?: boolean
  source?: BuilderSource
  createdBy?: string
  onSaved?: (invoice: InvoiceDetail, action: InvoiceSavedAction) => void
  onCancel?: () => void
  hidePreview?: boolean
}

const SOURCE_TYPE: Record<BuilderSource, SourceType> = { billing: "manual", field_sales: "field_sales", technician: "technician" }

export function InvoiceBuilder({ mode, initial, customer, lockCustomer, source = "billing", createdBy, onSaved, onCancel, hidePreview }: InvoiceBuilderProps) {
  const { tier } = useBillingTier()
  const canWrite = tierAtLeast(tier, "clerk")
  const isAdmin = tier === "admin"
  const act = useActionState()
  const catalog = useCatalog()
  const tpl = useTemplates()

  const [saved, setSaved] = useState<Partial<InvoiceDetail> | undefined>(mode === "edit" ? initial : undefined)
  const [cust, setCust] = useState<PickedCustomer | null>(
    customer ?? (initial?.customer_id ? { id: initial.customer_id, label: initial.bill_to?.name || "Customer", email: initial.bill_to?.email } : null),
  )
  const [lines, setLines] = useState<EditableLine[]>(() => {
    const l = fromServerLines(initial?.lines)
    return l.length ? l : [blankLine()]
  })
  const [issueDate, setIssueDate] = useState(initial?.issue_date ?? todayIso())
  const [dueDate, setDueDate] = useState(initial?.due_date ?? "")
  const [po, setPo] = useState(initial?.po_number ?? "")
  const [notes, setNotes] = useState(initial?.notes ?? "")
  const [terms, setTerms] = useState(initial?.terms ?? "")
  const [templateId, setTemplateId] = useState(initial?.template_id ?? "")
  const [bt, setBt] = useState({ name: initial?.bill_to?.name ?? "", email: initial?.bill_to?.email ?? "", phone: initial?.bill_to?.phone ?? "", address: initial?.bill_to?.address ?? "" })
  const [previewKey, setPreviewKey] = useState(0)
  const [confirmIssue, setConfirmIssue] = useState(false)
  const [credReason, setCredReason] = useState("")
  const [showCredit, setShowCredit] = useState(false)

  const id = saved?.id ?? null
  const status = saved?.status ?? "draft"
  const editable = (!id || status === "draft") && canWrite && saved?.subscription_id == null && !saved?.credit_note_of
  const isDraft = status === "draft"

  // Reflect external changes of the `initial` prop (e.g. the host reloaded the detail).
  useEffect(() => {
    if (mode === "edit" && initial?.id && initial.id !== saved?.id) {
      setSaved(initial)
      const l = fromServerLines(initial.lines)
      setLines(l.length ? l : [blankLine()])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial?.id])

  const body = useMemo((): InvoiceInput => {
    const b: InvoiceInput = {
      lines: toLineInputs(lines),
      notes,
      terms,
      po_number: po,
      template_id: templateId || undefined,
      issue_date: issueDate || undefined,
      due_date: dueDate || undefined,
    }
    const billTo = Object.fromEntries(Object.entries(bt).filter(([, v]) => v.trim() !== ""))
    if (Object.keys(billTo).length) b.bill_to = billTo
    return b
  }, [lines, notes, terms, po, templateId, issueDate, dueDate, bt])

  const validate = (): string | null => {
    if (!id && !cust) return "Choose a customer first."
    if (toLineInputs(lines).length === 0) return "Add at least one line with a description and price."
    if (toLineInputs(lines).some((l) => !l.description)) return "Every line needs a description."
    return null
  }

  /** Saves; returns the saved invoice or null (error shown). */
  const persist = async (): Promise<InvoiceDetail | null> => {
    const bad = validate()
    if (bad) {
      act.setMsg({ tone: "error", text: bad })
      return null
    }
    const r = await act.run("save", () =>
      id
        ? updateInvoice(id, { ...body, template_id: templateId || undefined })
        : createManualInvoice({ ...body, customer_id: cust?.id, source_type: SOURCE_TYPE[source], ...(createdBy ? { created_by: createdBy } : {}) }),
    )
    if (!r) return null
    setSaved(r)
    setLines((cur) => {
      const sv = fromServerLines(r.lines)
      return sv.length ? sv : cur
    })
    setPreviewKey((k) => k + 1)
    return r
  }

  const saveDraft = async () => {
    const r = await persist()
    if (r) {
      act.setMsg({ tone: "success", text: `Draft ${r.number} saved. Server total ${fmtMoney(r.total_zar)} (authoritative).` })
      onSaved?.(r, "saved")
    }
  }

  const saveAndIssue = async () => {
    setConfirmIssue(false)
    const r = await persist()
    if (!r) return
    const issued = await act.run("issue", () => issueInvoice(r.id))
    if (issued) {
      setSaved(issued)
      setPreviewKey((k) => k + 1)
      act.setMsg({ tone: "success", text: `Invoice ${issued.number} issued. It is now receivable and queued to the ledger.` })
      onSaved?.(issued, "issued")
    } else {
      onSaved?.(r, "saved") // saved as draft even though issuing failed (error is shown)
    }
  }

  const duplicate = async () => {
    if (!id) return
    const r = await act.run("dup", () => duplicateInvoice(id), (d) => `Created draft ${d?.number ?? ""}.`)
    if (r) onSaved?.(r, "duplicated")
  }

  const doVoid = async () => {
    if (!id) return
    const r = await act.run("void", () => voidInvoice(id), "Invoice voided.")
    if (r !== undefined) {
      setSaved((s) => ({ ...(s ?? {}), status: "voided" }))
      setPreviewKey((k) => k + 1)
      onSaved?.({ ...(saved as InvoiceDetail), status: "voided" }, "voided")
    }
  }

  const doCredit = async () => {
    if (!id || !credReason.trim()) {
      act.setMsg({ tone: "error", text: "Give a reason for the credit note." })
      return
    }
    const r = await act.run("credit", () => createCreditNote(id, credReason.trim()), "Credit note created.")
    if (r !== undefined) {
      setShowCredit(false)
      setCredReason("")
      onSaved?.(r as unknown as InvoiceDetail, "credited")
    }
  }

  const locked = !editable || !!act.busy
  const customerLocked = !!lockCustomer || !!id

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-foreground">{id ? saved?.number ?? "Invoice" : "New invoice"}</h3>
        {id && <StatusBadge status={status} />}
        {source !== "billing" && <span className="rounded bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">source: {source.replace("_", " ")}</span>}
      </div>

      {!canWrite && <Note>{tier === "none" ? "Your role could not be verified, so editing is disabled." : tierTip("clerk")}. You can still view.</Note>}
      {id && !isDraft && <Note>Only drafts are editable. {status === "voided" ? "This invoice is void." : "Use duplicate, void or credit note below."}</Note>}
      {act.msg && <Note tone={act.msg.tone}>{act.msg.text}</Note>}

      <div className={hidePreview ? "space-y-5" : "grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]"}>
        <div className="min-w-0 space-y-4">
          <Field label="Customer">
            {customerLocked && cust ? (
              <div className="rounded-md border border-border bg-secondary/30 px-3 py-2 text-sm text-foreground">
                {cust.label}
                {cust.email && <span className="ml-2 text-xs text-muted-foreground">{cust.email}</span>}
              </div>
            ) : (
              <CustomerPicker value={cust} onChange={setCust} disabled={locked} />
            )}
          </Field>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Issue date">
              <input type="date" className={inputClass} value={issueDate} disabled={locked} onChange={(e) => setIssueDate(e.target.value)} />
            </Field>
            <Field label="Due date" hint="Empty = template default">
              <input type="date" className={inputClass} value={dueDate} disabled={locked} onChange={(e) => setDueDate(e.target.value)} />
            </Field>
            <Field label="PO number">
              <input className={inputClass} value={po} disabled={locked} maxLength={80} onChange={(e) => setPo(e.target.value)} />
            </Field>
          </div>

          <LinesGrid lines={lines} onChange={setLines} catalog={catalog.items} catalogState={catalog.state} disabled={locked} />

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Notes (shown on the document)">
              <textarea className={textareaClass} value={notes} disabled={locked} onChange={(e) => setNotes(e.target.value)} />
            </Field>
            <Field label="Terms" hint="Empty = the template's default terms">
              <textarea className={textareaClass} value={terms} disabled={locked} onChange={(e) => setTerms(e.target.value)} />
            </Field>
          </div>

          <details className="rounded-md border border-border px-3 py-2 text-xs">
            <summary className="cursor-pointer font-medium text-muted-foreground">Bill-to override (optional; otherwise copied from CRM)</summary>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {(["name", "email", "phone", "address"] as const).map((k) => (
                <Field key={k} label={k[0].toUpperCase() + k.slice(1)}>
                  <input className={inputClass} value={bt[k]} disabled={locked} onChange={(e) => setBt({ ...bt, [k]: e.target.value })} />
                </Field>
              ))}
            </div>
          </details>
        </div>

        {!hidePreview && (
          <div className="min-w-0 space-y-3">
            <Field label="Template">
              <TemplatePicker templates={tpl.templates} state={tpl.state} value={templateId} onChange={setTemplateId} disabled={locked} />
            </Field>
            <DocumentPreview kind="invoices" id={id} refreshKey={previewKey} />
            {id && templateId !== (saved?.template_id ?? "") && <Note>Save the draft to re-render the preview with the chosen template.</Note>}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
        {editable && (
          <>
            <Button size="sm" variant="outline" disabled={!!act.busy} onClick={saveDraft}>
              <Save className="h-3.5 w-3.5" />
              {act.busy === "save" ? "Saving…" : id ? "Save changes" : "Save draft"}
            </Button>
            {!confirmIssue ? (
              <Button size="sm" disabled={!!act.busy} onClick={() => (validate() ? act.setMsg({ tone: "error", text: validate() as string }) : setConfirmIssue(true))}>
                <Send className="h-3.5 w-3.5" />
                Save &amp; issue
              </Button>
            ) : (
              <span className="flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-xs text-amber-300">
                Issuing posts revenue and starts dunning. Continue?
                <Button size="sm" disabled={!!act.busy} onClick={saveAndIssue}>
                  Yes, issue
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirmIssue(false)}>
                  Cancel
                </Button>
              </span>
            )}
          </>
        )}
        {id && (
          <Button size="sm" variant="outline" disabled={!!act.busy || !canWrite} title={!canWrite ? tierTip("clerk") : undefined} onClick={duplicate}>
            <Copy className="h-3.5 w-3.5" />
            Duplicate
          </Button>
        )}
        {id && !isDraft && status !== "voided" && !saved?.credit_note_of && (
          <>
            <Button size="sm" variant="outline" disabled={!!act.busy || !isAdmin} title={!isAdmin ? tierTip("admin") : undefined} onClick={() => setShowCredit((v) => !v)}>
              <FilePlus2 className="h-3.5 w-3.5" />
              Credit note
            </Button>
            <Button size="sm" variant="ghost-destructive" disabled={!!act.busy || !isAdmin} title={!isAdmin ? tierTip("admin") : "Void (only when nothing has been paid)"} onClick={doVoid}>
              <Ban className="h-3.5 w-3.5" />
              Void
            </Button>
          </>
        )}
        {onCancel && (
          <Button size="sm" variant="ghost" className="ml-auto" onClick={onCancel}>
            Close
          </Button>
        )}
      </div>

      {showCredit && (
        <div className="flex flex-wrap items-end gap-2 rounded-md border border-border p-3">
          <Field label="Credit note reason (required)" className="min-w-[16rem] flex-1">
            <input className={inputClass} value={credReason} maxLength={500} onChange={(e) => setCredReason(e.target.value)} />
          </Field>
          <Button size="sm" disabled={!!act.busy} onClick={doCredit}>
            Create credit note
          </Button>
        </div>
      )}

      {id && (
        <div className="border-t border-border pt-4">
          <DocumentActions kind="invoice" id={id} number={saved?.number} status={status} defaultEmail={cust?.email ?? saved?.bill_to?.email} />
        </div>
      )}
    </div>
  )
}
