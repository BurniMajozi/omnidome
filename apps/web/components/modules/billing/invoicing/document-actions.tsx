"use client"

/**
 * <DocumentActions/> - export, print, email, share link and delivery history for ONE
 * issued/saved invoice or quote. Reusable by the billing workspace and the Field Sales /
 * Technician apps.
 *
 * Props
 *   kind          "invoice" | "quote"
 *   id            document id (must already be saved)
 *   number        display number, used for file names / subject hints
 *   status        current status; invoices must be issued (not "draft"/"voided") to be emailed or shared
 *   defaultEmail  optional pre-filled recipient (the server falls back to the customer/prospect email when empty)
 *   canWrite      optional override; defaults to the caller's billing tier (clerk+ can email / share)
 *   onChanged     called after an action that changes server state (email, share link, revoke)
 *
 * Honesty rules: delivery status is shown exactly as the server records it (queued / sent /
 * delivered / bounced / suppressed / viewed ...). "sent" means accepted by the mail provider,
 * not delivered. Nothing is inferred.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Check, Copy, Download, Link2, Mail, Printer, RefreshCcw, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useBillingTier } from "@/lib/billing-api"
import {
  createShareLink,
  emailDocument,
  fetchDocText,
  listDeliveryEvents,
  listShareLinks,
  newIdempotencyKey,
  reconcileDelivery,
  revokeShareLink,
  type DeliveryEvent,
  type DocKind,
  type ShareLinkRow,
} from "@/lib/invoicing-api"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import type { Loadable } from "@/lib/service-state"
import { Field, Note, StatusBadge, downloadText, fmtDateTime, inputClass, textareaClass, tierAtLeast, tierTip, useActionState } from "../shared"

export interface DocumentActionsProps {
  kind: "invoice" | "quote"
  id: string
  number?: string
  status?: string
  defaultEmail?: string | null
  canWrite?: boolean
  onChanged?: () => void
}

const splitEmails = (s: string) =>
  s
    .split(/[,;\s]+/)
    .map((x) => x.trim())
    .filter(Boolean)

export function DocumentActions({ kind, id, number, status, defaultEmail, canWrite, onChanged }: DocumentActionsProps) {
  const path: DocKind = kind === "invoice" ? "invoices" : "quotes"
  const { tier } = useBillingTier()
  const write = canWrite ?? tierAtLeast(tier, "clerk")
  const act = useActionState()
  const issued = kind === "quote" ? true : status !== "draft" && status !== "voided" && status !== undefined
  const sendBlockedReason = !write
    ? tierTip("clerk")
    : kind === "invoice" && status === "draft"
      ? "Issue the invoice first"
      : kind === "invoice" && status === "voided"
        ? "Voided invoices cannot be sent"
        : null

  // ---- export / print
  const baseName = (number || id).replace(/[^A-Za-z0-9._-]+/g, "_")
  const doExport = (fmt: "csv" | "json" | "html") =>
    act.run(`export-${fmt}`, async () => {
      const r = await fetchDocText(path, id, fmt)
      if (r.ok && r.data !== null) {
        const mime = fmt === "csv" ? "text/csv;charset=utf-8" : fmt === "json" ? "application/json" : "text/html;charset=utf-8"
        downloadText(`${baseName}.${fmt}`, r.data, mime)
      }
      return r
    })

  const doPrint = () =>
    act.run("print", async () => {
      const r = await fetchDocText(path, id)
      if (!r.ok || r.data === null) return r
      // Script-less sandbox; allow-same-origin + allow-modals ONLY so the parent can call print().
      const f = document.createElement("iframe")
      f.setAttribute("sandbox", "allow-same-origin allow-modals")
      f.setAttribute("aria-hidden", "true")
      f.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden"
      f.onload = () => {
        try {
          f.contentWindow?.focus()
          f.contentWindow?.print()
        } catch {
          const blob = new Blob([r.data as string], { type: "text/html;charset=utf-8" })
          window.open(URL.createObjectURL(blob), "_blank", "noopener")
        }
        setTimeout(() => f.remove(), 60_000)
      }
      f.srcdoc = r.data
      document.body.appendChild(f)
      return r
    })

  return (
    <div className="space-y-5">
      {act.msg && <Note tone={act.msg.tone}>{act.msg.text}</Note>}

      <section className="space-y-2">
        <h4 className="text-sm font-semibold text-foreground">Export and print</h4>
        <div className="flex flex-wrap gap-2">
          {(["csv", "json", "html"] as const).map((f) => (
            <Button key={f} size="sm" variant="outline" disabled={!!act.busy} onClick={() => doExport(f)}>
              <Download className="h-3.5 w-3.5" />
              {f.toUpperCase()}
            </Button>
          ))}
          <Button size="sm" variant="outline" disabled={!!act.busy} onClick={doPrint}>
            <Printer className="h-3.5 w-3.5" />
            Print / Save as PDF
          </Button>
        </div>
        <p className="text-[11px] text-muted-foreground">There is no server-side PDF yet: choose "Save as PDF" in the browser print dialog.</p>
      </section>

      <EmailSection kind={kind} path={path} id={id} number={number} defaultEmail={defaultEmail} disabledReason={sendBlockedReason} isInvoice={kind === "invoice"} onChanged={onChanged} isAdmin={tier === "admin"} />

      <ShareSection kind={kind} path={path} id={id} disabledReason={!write ? tierTip("clerk") : !issued ? "Issue the invoice first" : kind === "invoice" && status === "voided" ? "Voided invoices cannot be shared" : null} onChanged={onChanged} />
    </div>
  )
}

// ------------------------------------------------------------------ email + delivery history

function EmailSection({
  kind,
  path,
  id,
  number,
  defaultEmail,
  disabledReason,
  isInvoice,
  onChanged,
  isAdmin,
}: {
  kind: "invoice" | "quote"
  path: DocKind
  id: string
  number?: string
  defaultEmail?: string | null
  disabledReason: string | null
  isInvoice: boolean
  onChanged?: () => void
  isAdmin: boolean
}) {
  const act = useActionState()
  const [to, setTo] = useState(defaultEmail ?? "")
  const [cc, setCc] = useState("")
  const [subject, setSubject] = useState("")
  const [message, setMessage] = useState("")
  const [asReminder, setAsReminder] = useState(false)
  const [expires, setExpires] = useState("")
  const key = useRef<string | null>(null)
  const [events, setEvents] = useState<Loadable<DeliveryEvent[]>>({ state: "loading" })

  const loadEvents = useCallback(() => {
    listDeliveryEvents(path, id).then(setEvents)
  }, [path, id])
  useEffect(() => {
    setEvents({ state: "loading" })
    loadEvents()
  }, [loadEvents])
  useEffect(() => {
    if (defaultEmail) setTo((cur) => cur || defaultEmail)
  }, [defaultEmail])

  const touched = () => {
    key.current = null // content changed: a new idempotency key for the next send
  }

  const send = async () => {
    if (!key.current) key.current = newIdempotencyKey()
    const exp = Number(expires)
    const r = await act.run(
      "email",
      () =>
        emailDocument(
          path,
          id,
          {
            to: splitEmails(to),
            cc: splitEmails(cc),
            subject: subject.trim() || undefined,
            message: message.trim() || undefined,
            kind: isInvoice && asReminder ? "reminder" : "document",
            link_expires_in_days: Number.isFinite(exp) && exp > 0 ? exp : undefined,
          },
          key.current as string,
        ),
      (d) => {
        const rec = d?.recipients?.to?.join(", ")
        return `${d?.replayed ? "Already sent (replayed): " : "Accepted by the mail provider"}${rec ? ` for ${rec}` : ""}. This means "sent", not yet "delivered"; delivery updates appear below when the provider reports them.`
      },
    )
    if (r) {
      key.current = null
      loadEvents()
      onChanged?.()
    } else {
      loadEvents() // a failed/ambiguous attempt still leaves a delivery row
    }
  }

  const rows = events.state === "ready" ? [...events.data].sort((a, b) => (a.at < b.at ? 1 : -1)) : []
  const ambiguous = rows.filter((e) => e.event_type === "queued" && (e.detail as { ambiguous?: boolean } | null)?.ambiguous)

  // Latest event per recipient: the honest "where is it now" view.
  const latest = useMemo(() => {
    const m = new Map<string, DeliveryEvent>()
    for (const e of rows) {
      const k = e.recipient || "(unknown)"
      if (!m.has(k) && e.event_type !== "viewed" && e.event_type !== "opened") m.set(k, e)
    }
    return [...m.entries()]
  }, [rows])
  const viewed = rows.some((e) => e.event_type === "viewed" || e.event_type === "opened")

  return (
    <section className="space-y-3">
      <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Mail className="h-4 w-4" />
        Email {kind === "invoice" ? "invoice" : "quote"}
      </h4>
      {act.msg && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
      {disabledReason && <Note>{disabledReason}.</Note>}
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="To" hint="Leave empty to use the customer / prospect email on record">
          <input className={inputClass} value={to} onChange={(e) => { setTo(e.target.value); touched() }} placeholder="name@example.com, ..." disabled={!!disabledReason} />
        </Field>
        <Field label="Cc">
          <input className={inputClass} value={cc} onChange={(e) => { setCc(e.target.value); touched() }} disabled={!!disabledReason} />
        </Field>
        <Field label="Subject" className="sm:col-span-2">
          <input className={inputClass} value={subject} onChange={(e) => { setSubject(e.target.value); touched() }} placeholder={`Default subject for ${number ?? kind}`} disabled={!!disabledReason} />
        </Field>
        <Field label="Message" className="sm:col-span-2">
          <textarea className={textareaClass} value={message} onChange={(e) => { setMessage(e.target.value); touched() }} disabled={!!disabledReason} />
        </Field>
        <Field label="Link valid for (days)" hint="Optional; the server applies its default">
          <input className={inputClass} inputMode="numeric" value={expires} onChange={(e) => { setExpires(e.target.value); touched() }} disabled={!!disabledReason} />
        </Field>
        {isInvoice && (
          <label className="flex items-center gap-2 self-end pb-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={asReminder} onChange={(e) => { setAsReminder(e.target.checked); touched() }} disabled={!!disabledReason} />
            Send as payment reminder
          </label>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" disabled={!!disabledReason || !!act.busy} title={disabledReason ?? undefined} onClick={send}>
          <Mail className="h-3.5 w-3.5" />
          {act.busy === "email" ? "Sending…" : asReminder ? "Send reminder" : "Send email"}
        </Button>
        <Button size="sm" variant="ghost" onClick={loadEvents}>
          <RefreshCcw className="h-3.5 w-3.5" />
          Refresh history
        </Button>
      </div>

      {ambiguous.length > 0 && (
        <Note tone="error">
          A previous send could not be confirmed (provider timeout or error). Further sends are blocked until an admin reconciles it.
          {isAdmin ? (
            <span className="mt-1 flex flex-wrap gap-2">
              {ambiguous.map((e) => (
                <span key={e.id} className="flex items-center gap-1">
                  <span>{fmtDateTime(e.at)}:</span>
                  <Button size="sm" variant="outline" disabled={!!act.busy} onClick={async () => { const r = await act.run("rec", () => reconcileDelivery(e.id, "sent", e.message_id ?? undefined), "Marked as sent."); if (r !== undefined) loadEvents() }}>It was sent</Button>
                  <Button size="sm" variant="outline" disabled={!!act.busy} onClick={async () => { const r = await act.run("rec", () => reconcileDelivery(e.id, "not_sent"), "Marked as not sent."); if (r !== undefined) loadEvents() }}>It was not sent</Button>
                </span>
              ))}
            </span>
          ) : (
            <span> Ask a finance admin.</span>
          )}
        </Note>
      )}

      <div className="space-y-2">
        <h5 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Delivery history</h5>
        {events.state !== "ready" ? (
          <NotConnected loadable={events} service="Billing" onRetry={loadEvents} className="p-4" />
        ) : rows.length === 0 ? (
          <NoDataYet message="Nothing has been emailed yet." className="p-4" />
        ) : (
          <>
            <div className="flex flex-wrap gap-2 text-xs">
              {latest.map(([who, e]) => (
                <span key={who} className="flex items-center gap-1 rounded-md border border-border px-2 py-1">
                  <span className="text-muted-foreground">{who}</span>
                  <StatusBadge status={e.event_type} />
                </span>
              ))}
              {viewed && (
                <span className="flex items-center gap-1 rounded-md border border-border px-2 py-1">
                  <span className="text-muted-foreground">Customer</span>
                  <StatusBadge status="viewed" />
                </span>
              )}
            </div>
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-xs">
                <thead className="bg-secondary/40 text-left text-muted-foreground">
                  <tr>
                    <th className="px-2 py-1.5">When</th>
                    <th className="px-2 py-1.5">Event</th>
                    <th className="px-2 py-1.5">Recipient</th>
                    <th className="px-2 py-1.5">Kind</th>
                    <th className="px-2 py-1.5">By</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((e) => (
                    <tr key={e.id} className="border-t border-border">
                      <td className="px-2 py-1.5 whitespace-nowrap">{fmtDateTime(e.at)}</td>
                      <td className="px-2 py-1.5">
                        <StatusBadge status={e.event_type} />
                        {(e.detail as { ambiguous?: boolean } | null)?.ambiguous && <span className="ml-1 text-amber-400">unconfirmed</span>}
                      </td>
                      <td className="px-2 py-1.5">{e.recipient ?? "—"}</td>
                      <td className="px-2 py-1.5">{e.kind ?? "—"}</td>
                      <td className="px-2 py-1.5">{e.actor ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ share links

function ShareSection({ kind, path, id, disabledReason, onChanged }: { kind: "invoice" | "quote"; path: DocKind; id: string; disabledReason: string | null; onChanged?: () => void }) {
  const act = useActionState()
  const [links, setLinks] = useState<Loadable<ShareLinkRow[]>>({ state: "loading" })
  const [days, setDays] = useState("")
  const [fresh, setFresh] = useState<{ url: string; expires: string } | null>(null)
  const [copied, setCopied] = useState(false)

  const load = useCallback(() => {
    listShareLinks(path, id).then(setLinks)
  }, [path, id])
  useEffect(() => {
    setLinks({ state: "loading" })
    setFresh(null)
    load()
  }, [load])

  const create = async () => {
    const d = Number(days)
    const r = await act.run("create", () => createShareLink(path, id, Number.isFinite(d) && d > 0 ? Math.floor(d) : undefined))
    if (r) {
      // The public page lives in this app: /pay/<token> for invoices, /quote/<token> for quotes.
      const page = `${window.location.origin}${kind === "invoice" ? "/pay" : "/quote"}/${encodeURIComponent(r.token)}`
      setFresh({ url: page, expires: r.expires_at })
      load()
      onChanged?.()
    }
  }
  const copy = async () => {
    if (!fresh) return
    try {
      await navigator.clipboard.writeText(fresh.url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      act.setMsg({ tone: "error", text: "Copy was blocked by the browser. Select the link and copy it manually." })
    }
  }

  return (
    <section className="space-y-3">
      <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Link2 className="h-4 w-4" />
        Share link
      </h4>
      {act.msg && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
      {disabledReason && <Note>{disabledReason}.</Note>}
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Expires in (days)" hint="Default 30, max 365">
          <input className={`${inputClass} w-28`} inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} disabled={!!disabledReason} />
        </Field>
        <Button size="sm" disabled={!!disabledReason || !!act.busy} title={disabledReason ?? undefined} onClick={create}>
          <Link2 className="h-3.5 w-3.5" />
          Create link
        </Button>
      </div>
      {fresh && (
        <div className="space-y-1 rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-xs">
          <p className="text-emerald-300">The link is shown once and cannot be retrieved later. Copy it now. Expires {fmtDateTime(fresh.expires)}.</p>
          <div className="flex gap-2">
            <input readOnly className={inputClass} value={fresh.url} onFocus={(e) => e.currentTarget.select()} />
            <Button size="sm" variant="outline" onClick={copy}>
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
        </div>
      )}
      {links.state !== "ready" ? (
        <NotConnected loadable={links} service="Billing" onRetry={load} className="p-4" />
      ) : links.data.length === 0 ? (
        <NoDataYet message="No share links created." className="p-4" />
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-xs">
            <thead className="bg-secondary/40 text-left text-muted-foreground">
              <tr>
                <th className="px-2 py-1.5">Status</th>
                <th className="px-2 py-1.5">Expires</th>
                <th className="px-2 py-1.5">Views</th>
                <th className="px-2 py-1.5">Last viewed</th>
                <th className="px-2 py-1.5" />
              </tr>
            </thead>
            <tbody>
              {links.data.map((l) => (
                <tr key={l.id} className="border-t border-border">
                  <td className="px-2 py-1.5">{l.revoked_at ? <StatusBadge status="void" /> : l.active ? <StatusBadge status="accepted" /> : <StatusBadge status="expired" />}</td>
                  <td className="px-2 py-1.5">{fmtDateTime(l.expires_at)}</td>
                  <td className="px-2 py-1.5">{l.view_count}</td>
                  <td className="px-2 py-1.5">{fmtDateTime(l.last_viewed_at)}</td>
                  <td className="px-2 py-1.5 text-right">
                    {l.active && !l.revoked_at && (
                      <Button size="sm" variant="ghost-destructive" disabled={!!disabledReason || !!act.busy} onClick={async () => { const r = await act.run("revoke", () => revokeShareLink(l.id), "Link revoked."); if (r !== undefined) { load(); onChanged?.() } }}>
                        <Trash2 className="h-3.5 w-3.5" />
                        Revoke
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
