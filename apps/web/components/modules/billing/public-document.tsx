"use client"

/**
 * Customer-facing invoice / quote view used by app/pay/[token] and app/quote/[token].
 * Fetches ONLY the public billing endpoints (token in the path is the credential) and renders the
 * sanitised JSON as escaped React text. Nothing from the server is injected as HTML.
 */

import { useCallback, useEffect, useState } from "react"
import { CheckCircle2, CircleAlert, Loader2 } from "lucide-react"
import { fmtMoney } from "@/lib/money"

const BASE = "/svc/billing/public"

interface PubLine {
  description?: string
  quantity?: string
  unit_price?: string
  discount?: string
  tax_rate?: string | null
  net?: string
  vat?: string | null
  total?: string
}
interface PubDoc {
  number: string
  status: string
  title?: string
  issue_date?: string | null
  due_date?: string | null
  valid_until?: string | null
  po_number?: string | null
  bill_to?: { name?: string | null; address?: string | null }
  lines: PubLine[]
  subtotal: string
  discount_total?: string
  vat: string
  total: string
  paid?: string
  balance?: string
  notes?: string | null
  terms?: string | null
  currency?: string
  branding?: { company_name?: string | null; logo_url?: string | null; accent_colour?: string | null; footer?: string | null; payment_details?: string | null }
  payable?: boolean
  actionable?: boolean
}

const HEX = /^#[0-9a-fA-F]{6}$/
const label = (s: string) => s.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())

async function call(path: string, method: "GET" | "POST", body?: unknown): Promise<{ ok: boolean; status: number; data: unknown }> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      method,
      cache: "no-store",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(20_000),
    })
    let data: unknown = null
    try {
      data = await res.json()
    } catch {
      data = null
    }
    return { ok: res.ok, status: res.status, data }
  } catch {
    return { ok: false, status: 0, data: null }
  }
}

const errText = (status: number, data: unknown): string => {
  if (status === 404) return "This link is not valid. It may have expired or been revoked. Please contact the sender for a new one."
  if (status === 429) return "Too many requests. Please wait a few minutes and try again."
  if (status === 0) return "We could not reach the server. Check your connection and try again."
  const d = (data as { detail?: unknown } | null)?.detail
  if (typeof d === "string") return d
  return "Something went wrong. Please try again shortly."
}

export function PublicDocument({ kind, token }: { kind: "invoice" | "quote"; token: string }) {
  const seg = kind === "invoice" ? "invoices" : "quotes"
  const [doc, setDoc] = useState<PubDoc | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null)
  const [amount, setAmount] = useState("")
  const [note, setNote] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    const r = await call(`/${seg}/${encodeURIComponent(token)}`, "GET")
    if (r.ok && r.data) {
      setDoc(r.data as PubDoc)
      setError(null)
    } else {
      setDoc(null)
      setError(errText(r.status, r.data))
    }
    setLoading(false)
  }, [seg, token])
  useEffect(() => {
    void load()
  }, [load])

  const pay = async () => {
    if (!doc || busy) return
    setMsg(null)
    const body: Record<string, string> = {}
    if (amount.trim()) {
      const n = Number(amount)
      if (!Number.isFinite(n) || n <= 0) return setMsg({ tone: "err", text: "Enter a valid amount." })
      if (doc.balance && n > Number(doc.balance)) return setMsg({ tone: "err", text: "The amount cannot be more than the balance due." })
      body.amount_zar = n.toFixed(2)
    }
    setBusy("pay")
    const r = await call(`/invoices/${encodeURIComponent(token)}/pay`, "POST", body)
    const url = (r.data as { authorization_url?: unknown } | null)?.authorization_url
    if (r.ok && typeof url === "string") {
      let ok = false
      try {
        const u = new URL(url)
        ok = u.protocol === "https:" && /(^|\.)paystack\.(com|co)$/i.test(u.hostname)
      } catch {
        ok = false
      }
      if (ok) {
        window.location.assign(url)
        return
      }
      setMsg({ tone: "err", text: "The payment page address was not recognised, so you were not redirected. Please contact the sender." })
    } else {
      setMsg({ tone: "err", text: errText(r.status, r.data) })
    }
    setBusy(null)
  }

  const decide = async (decision: "accept" | "decline") => {
    if (busy) return
    setMsg(null)
    setBusy(decision)
    const r = await call(`/quotes/${encodeURIComponent(token)}/${decision}`, "POST", note.trim() ? { note: note.trim() } : {})
    setBusy(null)
    if (r.ok) {
      setMsg({ tone: "ok", text: decision === "accept" ? "Thank you. The quote has been accepted." : "The quote has been declined. Thank you for letting us know." })
      void load()
    } else setMsg({ tone: "err", text: errText(r.status, r.data) })
  }

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-sm text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading…
      </div>
    )
  }
  if (error || !doc) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-lg border border-border bg-card p-6 text-center">
        <CircleAlert className="mx-auto mb-2 h-6 w-6 text-muted-foreground" />
        <p className="text-sm text-foreground">{error ?? "Not found"}</p>
        <button type="button" onClick={() => void load()} className="mt-4 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-secondary">
          Try again
        </button>
      </div>
    )
  }

  const accent = HEX.test(doc.branding?.accent_colour ?? "") ? (doc.branding?.accent_colour as string) : "#2563eb"
  const logo = doc.branding?.logo_url && /^https?:\/\//i.test(doc.branding.logo_url) ? doc.branding.logo_url : null
  const isInvoice = kind === "invoice"
  const hasDiscount = doc.lines.some((l) => l.discount && Number(l.discount) !== 0)

  return (
    <div className="mx-auto max-w-3xl space-y-4 px-4 py-8">
      <div className="rounded-lg border border-border bg-card p-5 shadow-sm sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b-2 pb-4" style={{ borderColor: accent }}>
          <div className="min-w-0">
            {logo && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={logo} alt="" referrerPolicy="no-referrer" className="mb-2 max-h-12 max-w-[10rem] object-contain" />
            )}
            <p className="text-base font-semibold text-foreground">{doc.branding?.company_name || (isInvoice ? "Invoice" : "Quote")}</p>
          </div>
          <div className="text-right">
            <p className="text-xl font-bold" style={{ color: accent }}>
              {doc.title || (isInvoice ? "Invoice" : "Quote")}
            </p>
            <p className="text-sm text-foreground">{doc.number}</p>
            <p className="text-xs text-muted-foreground">{label(doc.status)}</p>
          </div>
        </div>

        <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Billed to</dt>
            <dd className="text-foreground">{doc.bill_to?.name || "—"}</dd>
            {doc.bill_to?.address && <dd className="whitespace-pre-line text-muted-foreground">{doc.bill_to.address}</dd>}
          </div>
          <div className="space-y-0.5 sm:text-right">
            {doc.issue_date && (
              <p>
                <span className="text-muted-foreground">Issued: </span>
                {doc.issue_date}
              </p>
            )}
            {doc.due_date && (
              <p>
                <span className="text-muted-foreground">Due: </span>
                {doc.due_date}
              </p>
            )}
            {doc.valid_until && (
              <p>
                <span className="text-muted-foreground">Valid until: </span>
                {doc.valid_until}
              </p>
            )}
            {doc.po_number && (
              <p>
                <span className="text-muted-foreground">PO / ref: </span>
                {doc.po_number}
              </p>
            )}
          </div>
        </dl>

        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[480px] text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="py-2 pr-2">Description</th>
                <th className="px-2 py-2 text-right">Qty</th>
                <th className="px-2 py-2 text-right">Unit</th>
                {hasDiscount && <th className="px-2 py-2 text-right">Discount</th>}
                <th className="py-2 pl-2 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {doc.lines.map((l, i) => (
                <tr key={i} className="border-t border-border">
                  <td className="py-2 pr-2 text-foreground">{l.description}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{l.quantity}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{fmtMoney(l.unit_price)}</td>
                  {hasDiscount && <td className="px-2 py-2 text-right tabular-nums">{Number(l.discount) ? fmtMoney(l.discount) : "—"}</td>}
                  <td className="py-2 pl-2 text-right tabular-nums text-foreground">{fmtMoney(l.total ?? l.net)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="ml-auto mt-4 w-full max-w-xs space-y-1 text-sm">
          <Row k="Subtotal" v={fmtMoney(doc.subtotal)} />
          {doc.discount_total && Number(doc.discount_total) !== 0 && <Row k="Discounts" v={fmtMoney(doc.discount_total)} />}
          <Row k="VAT" v={fmtMoney(doc.vat)} />
          <Row k="Total" v={fmtMoney(doc.total)} bold />
          {isInvoice && doc.paid !== undefined && Number(doc.paid) !== 0 && <Row k="Paid" v={fmtMoney(doc.paid)} />}
          {isInvoice && doc.balance !== undefined && <Row k="Balance due" v={fmtMoney(doc.balance)} bold accent={accent} />}
        </div>

        {doc.notes && <p className="mt-5 whitespace-pre-line text-sm text-muted-foreground">{doc.notes}</p>}
        {doc.terms && (
          <div className="mt-4 text-xs text-muted-foreground">
            <p className="font-semibold text-foreground">Terms</p>
            <p className="whitespace-pre-line">{doc.terms}</p>
          </div>
        )}
        {doc.branding?.payment_details && (
          <div className="mt-4 text-xs text-muted-foreground">
            <p className="font-semibold text-foreground">Payment details</p>
            <p className="whitespace-pre-line">{doc.branding.payment_details}</p>
          </div>
        )}
        {doc.branding?.footer && <p className="mt-6 border-t border-border pt-3 text-center text-xs text-muted-foreground">{doc.branding.footer}</p>}
      </div>

      {msg && (
        <div role="status" className={`flex items-start gap-2 rounded-md border px-3 py-2 text-sm ${msg.tone === "ok" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : "border-red-500/40 bg-red-500/10 text-red-300"}`}>
          {msg.tone === "ok" ? <CheckCircle2 className="mt-0.5 h-4 w-4" /> : <CircleAlert className="mt-0.5 h-4 w-4" />}
          {msg.text}
        </div>
      )}

      {isInvoice && (
        <div className="rounded-lg border border-border bg-card p-5">
          {doc.payable ? (
            <div className="space-y-3">
              <p className="text-sm text-foreground">You will be taken to our secure payment provider (Paystack) to complete the payment.</p>
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Amount to pay (optional, defaults to the full balance)
                  <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={doc.balance ? Number(doc.balance).toFixed(2) : ""} className="h-9 w-48 rounded-md border border-border bg-background px-3 text-sm text-foreground" />
                </label>
                <button type="button" disabled={!!busy} onClick={pay} className="inline-flex h-9 items-center gap-2 rounded-md px-5 text-sm font-semibold text-white disabled:opacity-60" style={{ background: accent }}>
                  {busy === "pay" && <Loader2 className="h-4 w-4 animate-spin" />}
                  Pay {doc.balance && !amount.trim() ? fmtMoney(doc.balance) : "now"}
                </button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {doc.status === "paid" ? "This invoice has been paid. Thank you." : doc.status === "voided" ? "This invoice has been cancelled." : "This invoice cannot be paid online right now."}
            </p>
          )}
        </div>
      )}

      {!isInvoice && (
        <div className="rounded-lg border border-border bg-card p-5">
          {doc.actionable ? (
            <div className="space-y-3">
              <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                Note (optional)
                <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} className="min-h-[64px] rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground" />
              </label>
              <div className="flex flex-wrap gap-3">
                <button type="button" disabled={!!busy} onClick={() => decide("accept")} className="inline-flex h-9 items-center gap-2 rounded-md px-5 text-sm font-semibold text-white disabled:opacity-60" style={{ background: accent }}>
                  {busy === "accept" && <Loader2 className="h-4 w-4 animate-spin" />}
                  Accept quote
                </button>
                <button type="button" disabled={!!busy} onClick={() => decide("decline")} className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-5 text-sm hover:bg-secondary disabled:opacity-60">
                  {busy === "decline" && <Loader2 className="h-4 w-4 animate-spin" />}
                  Decline
                </button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {doc.status === "accepted" || doc.status === "converted" ? "This quote has been accepted." : doc.status === "declined" ? "This quote was declined." : doc.status === "expired" ? "This quote has expired. Please ask for an updated one." : "This quote cannot be actioned right now."}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function Row({ k, v, bold, accent }: { k: string; v: string; bold?: boolean; accent?: string }) {
  return (
    <div className={`flex justify-between tabular-nums ${bold ? "border-t border-border pt-1 font-semibold text-foreground" : "text-muted-foreground"}`} style={bold && accent ? { color: accent } : undefined}>
      <span>{k}</span>
      <span>{v}</span>
    </div>
  )
}
