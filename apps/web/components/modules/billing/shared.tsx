"use client"

/**
 * Small shared UI pieces for the billing invoicing workspace. Native form
 * controls are used on purpose (compact grids); styling follows the design tokens.
 */

import { useState, type ReactNode } from "react"
import { AlertTriangle, CheckCircle2, Info } from "lucide-react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { BillingTier } from "@/lib/billing-derive"

export const inputClass =
  "h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
export const textareaClass = cn(inputClass, "h-auto min-h-[72px] py-2")

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cn("flex flex-col gap-1 text-xs font-medium text-muted-foreground", className)}>
      <span>{label}</span>
      {children}
      {hint && <span className="text-[11px] font-normal">{hint}</span>}
    </label>
  )
}

export type NoteTone = "error" | "success" | "info"
export function Note({ tone = "info", children, className }: { tone?: NoteTone; children: ReactNode; className?: string }) {
  const Icon = tone === "error" ? AlertTriangle : tone === "success" ? CheckCircle2 : Info
  const color =
    tone === "error"
      ? "border-red-500/40 bg-red-500/10 text-red-300"
      : tone === "success"
        ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
        : "border-border bg-secondary/40 text-muted-foreground"
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cn("flex items-start gap-2 rounded-md border px-3 py-2 text-xs", color, className)}>
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div className="min-w-0 break-words">{children}</div>
    </div>
  )
}

/** Tracks a single in-flight action plus its last outcome message. */
export function useActionState() {
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ tone: NoteTone; text: string } | null>(null)
  return {
    busy,
    msg,
    clear: () => setMsg(null),
    setMsg,
    async run<T>(key: string, fn: () => Promise<{ ok: boolean; message: string | null; data: T | null }>, okText?: string | ((d: T | null) => string)): Promise<T | null | undefined> {
      if (busy) return undefined
      setBusy(key)
      setMsg(null)
      try {
        const r = await fn()
        if (!r.ok) {
          setMsg({ tone: "error", text: r.message ?? "Request failed" })
          return undefined
        }
        if (okText) setMsg({ tone: "success", text: typeof okText === "function" ? okText(r.data) : okText })
        return r.data
      } finally {
        setBusy(null)
      }
    },
  }
}

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  wide,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  description?: string
  children: ReactNode
  wide?: boolean
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn("max-h-[90vh] overflow-y-auto", wide ? "max-w-5xl" : "max-w-xl")}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  )
}

/** Right-hand slide-over built on the dialog primitive (focus trap + escape handled by Radix). */
export function SidePanel({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="left-auto right-0 top-0 h-full max-h-screen w-full max-w-2xl translate-x-0 translate-y-0 content-start overflow-y-auto rounded-none border-l data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right sm:rounded-none">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  )
}

// ------------------------------------------------------------------ formatting

export function fmtDate(v: string | null | undefined): string {
  if (!v) return "—"
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return String(v)
  return d.toLocaleDateString("en-ZA", { year: "numeric", month: "short", day: "2-digit" })
}
export function fmtDateTime(v: string | null | undefined): string {
  if (!v) return "—"
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return String(v)
  return d.toLocaleString("en-ZA", { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" })
}
export const todayIso = () => new Date().toISOString().slice(0, 10)
export const addDaysIso = (iso: string, days: number) => {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export function humanise(s: string | null | undefined): string {
  if (!s) return "—"
  const t = s.replace(/[_-]+/g, " ").trim()
  return t.charAt(0).toUpperCase() + t.slice(1)
}

// ------------------------------------------------------------------ status badges

const TONE: Record<string, string> = {
  draft: "bg-secondary text-muted-foreground",
  sent: "badge-info",
  viewed: "badge-info",
  partially_paid: "badge-warning",
  paid: "badge-success",
  accepted: "badge-success",
  converted: "badge-success",
  overdue: "badge-danger",
  declined: "badge-danger",
  voided: "bg-secondary text-muted-foreground line-through",
  void: "bg-secondary text-muted-foreground line-through",
  expired: "badge-warning",
  superseded: "bg-secondary text-muted-foreground",
  calculated: "badge-info",
  waived: "badge-warning",
  invoiced: "badge-success",
  delivered: "badge-success",
  bounced: "badge-danger",
  complained: "badge-danger",
  failed: "badge-danger",
  suppressed: "badge-warning",
  queued: "badge-warning",
  opened: "badge-info",
  replied: "badge-info",
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <Badge variant="secondary">—</Badge>
  return <Badge className={TONE[status] ?? "bg-secondary text-muted-foreground"}>{humanise(status)}</Badge>
}

// ------------------------------------------------------------------ tier gating

const RANK: Record<BillingTier, number> = { none: 0, reader: 1, clerk: 2, admin: 3 }
export const tierAtLeast = (have: BillingTier, need: "reader" | "clerk" | "admin") => RANK[have] >= RANK[need]
export const tierTip = (need: "clerk" | "admin") => (need === "admin" ? "Finance admin only" : "Billing clerk or admin only")

/** Triggers a browser download of text content. */
export function downloadText(filename: string, text: string, mime: string) {
  if (typeof document === "undefined") return
  const blob = new Blob([text], { type: mime })
  const u = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = u
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(u), 1000)
}

export const num = (v: unknown): number => {
  const n = typeof v === "number" ? v : Number(String(v ?? "").replace(/\s/g, ""))
  return Number.isFinite(n) ? n : 0
}
