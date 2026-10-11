"use client"

/**
 * Card disputes (chargebacks). Unanswered disputes are lost automatically, so the deadline is the
 * main thing shown. The respond drawer prefills the evidence pack from the billing service; accepting
 * or declining a dispute cannot be undone and always goes through a confirm dialog.
 */

import { useCallback, useEffect, useState } from "react"
import { AlertTriangle, RefreshCcw } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import {
  getDispute,
  listDisputes,
  resolveDispute,
  submitDisputeEvidence,
  useBillingTier,
  type DisputeDetail,
  type DisputeList,
} from "@/lib/billing-api"
import { fmtMoney } from "@/lib/money"
import type { Loadable } from "@/lib/service-state"
import type { ActionResult } from "@/lib/api-result"
import { ConfirmModal } from "./confirm-modal"
import { InvoiceDrawer } from "./invoicing/invoice-drawer"
import { Field, Note, SidePanel, fmtDate, fmtDateTime, humanise, inputClass, textareaClass, tierTip, useActionState } from "./shared"

const HOUR = 3_600_000

/** 404/501 from the not-yet-deployed dispute endpoints read as "Not available yet" instead of an error. */
const unavailable = <T,>(r: ActionResult<T>): ActionResult<T> =>
  !r.ok && (r.status === 404 || r.status === 501) ? { ...r, message: "Not available yet. This action has not been enabled on the server." } : r

function deadline(dueAt: string | null, open: boolean): { text: string; tone: "danger" | "warning" | "muted" } {
  if (!dueAt) return { text: "—", tone: "muted" }
  const ms = new Date(dueAt).getTime() - Date.now()
  if (Number.isNaN(ms)) return { text: "—", tone: "muted" }
  if (!open) return { text: fmtDate(dueAt), tone: "muted" }
  if (ms < 0) return { text: "Overdue", tone: "danger" }
  const h = Math.floor(ms / HOUR)
  const text = h >= 48 ? `${Math.floor(h / 24)} days left` : h >= 1 ? `${h} hour${h === 1 ? "" : "s"} left` : "Less than 1 hour left"
  return { text, tone: ms < 48 * HOUR ? "danger" : "muted" }
}

function OutcomeBadge({ outcome }: { outcome?: string | null }) {
  if (outcome === "lost") return <Badge className="badge-danger ml-1">Lost</Badge>
  if (outcome === "won") return <Badge className="badge-success ml-1">Won</Badge>
  return null
}

function statusTone(status: string, open: boolean) {
  if (!open) return /won|resolved|accepted/i.test(status) ? "badge-success" : "bg-secondary text-muted-foreground"
  return /evidence|pending/i.test(status) ? "badge-warning" : "badge-danger"
}

export function DisputesTab() {
  const { isAdmin } = useBillingTier()
  const [data, setData] = useState<Loadable<DisputeList>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const [respondId, setRespondId] = useState<string | null>(null)
  const [openInvoice, setOpenInvoice] = useState<string | null>(null)
  const reload = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    let off = false
    setData({ state: "loading" })
    listDisputes().then((l) => !off && setData(l))
    return () => {
      off = true
    }
  }, [tick])

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">Card disputes</CardTitle>
          <Button size="sm" variant="ghost" onClick={reload}>
            <RefreshCcw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {data.state !== "ready" ? (
          <NotConnected loadable={data} service="Billing" onRetry={reload} />
        ) : (
          <>
            {data.data.open > 0 && (
              <Note tone="error">
                <span className="font-medium">
                  {data.data.open} open dispute{data.data.open === 1 ? "" : "s"}.
                </span>{" "}
                Unanswered disputes are lost automatically; respond before {data.data.next_due_at ? fmtDateTime(data.data.next_due_at) : "the deadline"}.
              </Note>
            )}
            {(data.data.disputes ?? []).length === 0 ? (
              <NoDataYet message="No card disputes. Disputes raised by customers' banks will appear here." />
            ) : (
              <div className="overflow-x-auto rounded-md border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-secondary/40 text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2">Respond by</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2">Category</th>
                      <th className="px-3 py-2 text-right">Amount</th>
                      <th className="px-3 py-2">Invoice</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {data.data.disputes.map((d) => {
                      const dl = deadline(d.due_at, d.open)
                      return (
                        <tr key={d.id} className="border-t border-border">
                          <td className={`px-3 py-2 ${dl.tone === "danger" ? "font-medium text-red-400" : "text-muted-foreground"}`}>
                            {dl.tone === "danger" && <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />}
                            {dl.text}
                            {d.open && d.due_at && <span className="block text-[11px] font-normal text-muted-foreground">{fmtDateTime(d.due_at)}</span>}
                          </td>
                          <td className="px-3 py-2">
                            <Badge className={statusTone(d.status, d.open)}>{humanise(d.status)}</Badge>
                            {!d.open && <OutcomeBadge outcome={d.outcome} />}
                            {d.resolution && <span className="ml-1 text-[11px] text-muted-foreground">{humanise(d.resolution)}</span>}
                          </td>
                          <td className="px-3 py-2">{humanise(d.category)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(d.amount_zar)}</td>
                          <td className="px-3 py-2">
                            {d.invoice_id ? (
                              <button type="button" className="text-primary underline-offset-2 hover:underline" onClick={() => setOpenInvoice(d.invoice_id as string)}>
                                {d.invoice_id.slice(0, 8)}
                              </button>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="px-3 py-2 text-right">
                            <Button size="sm" variant={d.open ? "default" : "outline"} onClick={() => setRespondId(d.id)}>
                              {d.open ? "Respond" : "View"}
                            </Button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </CardContent>
      <RespondDrawer id={respondId} isAdmin={isAdmin} onClose={() => setRespondId(null)} onChanged={reload} />
      <InvoiceDrawer invoiceId={openInvoice} customerName={undefined} onClose={() => setOpenInvoice(null)} onChanged={reload} />
    </Card>
  )
}

interface FormState {
  customer_name: string
  customer_email: string
  customer_phone: string
  service_details: string
  delivery_address: string
  delivery_date: string
}
const EMPTY: FormState = { customer_name: "", customer_email: "", customer_phone: "", service_details: "", delivery_address: "", delivery_date: "" }

function RespondDrawer({ id, isAdmin, onClose, onChanged }: { id: string | null; isAdmin: boolean; onClose: () => void; onChanged: () => void }) {
  const [detail, setDetail] = useState<Loadable<DisputeDetail>>({ state: "loading" })
  const [form, setForm] = useState<FormState>(EMPTY)
  const [tick, setTick] = useState(0)
  const [confirm, setConfirm] = useState<"accept" | "decline" | null>(null)
  const [message, setMessage] = useState("")
  const [refund, setRefund] = useState("")
  const act = useActionState()

  useEffect(() => {
    if (!id) return
    let off = false
    setDetail({ state: "loading" })
    setConfirm(null)
    setMessage("")
    setRefund("")
    act.clear()
    getDispute(id).then((l) => {
      if (off) return
      setDetail(l)
      if (l.state === "ready") {
        const p = l.data.evidence_pack ?? {}
        setForm({
          customer_name: p.customer_name ?? "",
          customer_email: p.customer_email ?? "",
          customer_phone: p.customer_phone ?? "",
          service_details: p.service_details ?? "",
          delivery_address: p.delivery_address ?? "",
          delivery_date: p.delivery_date ? String(p.delivery_date).slice(0, 10) : "",
        })
      }
    })
    return () => {
      off = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, tick])

  const d = detail.state === "ready" ? detail.data : null
  const pack = d?.evidence_pack ?? null
  const editable = !!d?.open && isAdmin
  const set = (k: keyof FormState) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submitEvidence = async () => {
    if (!id) return
    const r = await act.run(
      "evidence",
      async () =>
        unavailable(
          await submitDisputeEvidence(id, {
            customer_email: form.customer_email.trim(),
            customer_name: form.customer_name.trim(),
            customer_phone: form.customer_phone.trim(),
            service_details: form.service_details.trim(),
            delivery_address: form.delivery_address.trim(),
            delivery_date: form.delivery_date || null,
          }),
        ),
      "Evidence submitted.",
    )
    if (r !== undefined) onChanged()
  }

  const resolve = async () => {
    if (!id || !confirm) return
    const text = message.trim()
    if (confirm === "decline" && !text) {
      act.setMsg({ tone: "error", text: "Enter a message explaining why the dispute is declined." })
      return
    }
    const body: { resolution: "merchant-accepted" | "declined"; message: string; refund_amount_zar?: number } = {
      resolution: confirm === "accept" ? "merchant-accepted" : "declined",
      message: text || "Dispute accepted by merchant",
    }
    if (confirm === "accept" && refund.trim()) {
      const n = Number(refund)
      if (!Number.isFinite(n) || n <= 0) {
        act.setMsg({ tone: "error", text: "Enter a valid refund amount." })
        return
      }
      body.refund_amount_zar = n
    }
    const kind = confirm
    const r = await act.run("resolve", async () => unavailable(await resolveDispute(id, body)), kind === "accept" ? "Dispute accepted." : "Dispute declined.")
    if (r !== undefined) {
      setConfirm(null)
      onChanged()
      setTick((t) => t + 1)
    }
  }

  const needAdmin = !isAdmin

  return (
    <SidePanel open={!!id} onOpenChange={(o) => !o && onClose()} title={d ? `Dispute ${d.dispute_id}` : "Dispute"} description={d ? `${fmtMoney(d.amount_zar)} · ${humanise(d.category)}` : undefined}>
      {detail.state !== "ready" ? (
        <NotConnected loadable={detail} service="Billing" onRetry={() => setTick((t) => t + 1)} />
      ) : (
        <div className="space-y-5 pb-8">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge className={statusTone(detail.data.status, detail.data.open)}>{humanise(detail.data.status)}</Badge>
            {detail.data.open && <span className="text-xs text-muted-foreground">Respond by {fmtDateTime(detail.data.due_at)}</span>}
            {!detail.data.open && <OutcomeBadge outcome={detail.data.outcome} />}
            {detail.data.resolution && <span className="text-xs text-muted-foreground">Resolution: {humanise(detail.data.resolution)}</span>}
          </div>
          {!detail.data.open && <Note tone="info">This dispute is closed and can no longer be answered.</Note>}
          {detail.data.open && !isAdmin && <Note tone="info">You can view this dispute. A finance admin must respond.</Note>}

          {pack && (
            <section className="space-y-2">
              <h4 className="text-sm font-semibold text-foreground">What we know</h4>
              <dl className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <dt className="text-muted-foreground">Invoices</dt>
                  <dd className="text-foreground">{(pack.invoice_numbers ?? []).join(", ") || "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Reference</dt>
                  <dd className="text-foreground">{detail.data.reference || "—"}</dd>
                </div>
              </dl>
              {(pack.payments ?? []).length > 0 && (
                <ul className="divide-y divide-border rounded-md border border-border text-xs">
                  {(pack.payments ?? []).map((p, i) => (
                    <li key={`${p.reference}-${i}`} className="flex justify-between gap-2 px-3 py-1.5">
                      <span>
                        {p.reference} <span className="text-muted-foreground">{fmtDateTime(p.paid_at)}</span>
                      </span>
                      <span className="tabular-nums">{fmtMoney(p.amount_zar)}</span>
                    </li>
                  ))}
                </ul>
              )}
              {(pack.activity ?? []).length > 0 && (
                <ol className="space-y-1 border-l border-border pl-4 text-xs">
                  {(pack.activity ?? []).map((a, i) => (
                    <li key={i}>
                      <span className="text-muted-foreground">{fmtDateTime(a.at)}</span> {a.text}
                    </li>
                  ))}
                </ol>
              )}
            </section>
          )}

          <section className="space-y-3">
            <h4 className="text-sm font-semibold text-foreground">Evidence</h4>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Customer name">
                <input className={inputClass} value={form.customer_name} disabled={!editable} onChange={set("customer_name")} />
              </Field>
              <Field label="Customer email">
                <input type="email" className={inputClass} value={form.customer_email} disabled={!editable} onChange={set("customer_email")} />
              </Field>
              <Field label="Customer phone">
                <input className={inputClass} value={form.customer_phone} disabled={!editable} onChange={set("customer_phone")} />
              </Field>
              <Field label="Delivery date">
                <input type="date" className={inputClass} value={form.delivery_date} disabled={!editable} onChange={set("delivery_date")} />
              </Field>
            </div>
            <Field label="Service details">
              <textarea className={textareaClass} value={form.service_details} disabled={!editable} onChange={set("service_details")} />
            </Field>
            <Field label="Delivery address">
              <textarea className={textareaClass} value={form.delivery_address} disabled={!editable} onChange={set("delivery_address")} />
            </Field>
            {act.msg && !confirm && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
            {editable && (
              <div className="flex flex-wrap gap-2">
                <Button size="sm" disabled={!!act.busy} onClick={submitEvidence}>
                  {act.busy === "evidence" ? "Submitting…" : "Submit evidence"}
                </Button>
                <Button size="sm" variant="outline" disabled={!!act.busy || needAdmin} title={needAdmin ? tierTip("admin") : undefined} onClick={() => { act.clear(); setConfirm("accept") }}>
                  Accept dispute
                </Button>
                <Button size="sm" variant="outline" disabled={!!act.busy || needAdmin} title={needAdmin ? tierTip("admin") : undefined} onClick={() => { act.clear(); setConfirm("decline") }}>
                  Decline
                </Button>
              </div>
            )}
          </section>
        </div>
      )}

      <ConfirmModal
        open={!!confirm}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm === "accept" ? "Accept this dispute" : "Decline this dispute"}
        confirmLabel={confirm === "accept" ? "Accept dispute" : "Decline dispute"}
        destructive
        busy={act.busy === "resolve"}
        error={act.msg?.tone === "error" ? act.msg.text : null}
        onConfirm={resolve}
      >
        <p>
          {confirm === "accept"
            ? "Accepting means the customer's bank keeps the money and the dispute is closed. This cannot be undone."
            : "Declining tells the customer's bank you contest the dispute. This cannot be undone."}
        </p>
        <Field label={confirm === "decline" ? "Message (required)" : "Message (optional)"}>
          <textarea className={textareaClass} value={message} maxLength={1000} onChange={(e) => setMessage(e.target.value)} />
        </Field>
        {confirm === "accept" && (
          <Field label="Refund amount in ZAR (optional)">
            <input className={inputClass} inputMode="decimal" value={refund} onChange={(e) => setRefund(e.target.value)} />
          </Field>
        )}
      </ConfirmModal>
    </SidePanel>
  )
}
