"use client"

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react"
import { AlertTriangle, Gauge } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { AnalyticsApiError, getUsage, setUsageLimits, type Usage } from "@/lib/analytics-ai-api"

export const inputCls =
  "h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"

export const NO_RUN_TIP = "Your role does not allow running analyses. Ask an admin for the analyst role."

/** Roles are enforced by the server. Once a write answers 403 we disable run buttons for the session. */
const PermCtx = createContext<{ denied: boolean; markDenied: () => void }>({ denied: false, markDenied: () => {} })
export function PermissionProvider({ children }: { children: ReactNode }) {
  const [denied, setDenied] = useState(false)
  const markDenied = useCallback(() => setDenied(true), [])
  return <PermCtx.Provider value={{ denied, markDenied }}>{children}</PermCtx.Provider>
}
export const usePermission = () => useContext(PermCtx)

export function errText(e: unknown): string {
  if (e instanceof AnalyticsApiError) return e.message
  return e instanceof Error ? e.message : "Something went wrong"
}

export function ErrorNote({ message, className }: { message: string | null; className?: string }) {
  if (!message) return null
  return (
    <div role="alert" className={cn("flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300", className)}>
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span className="break-words">{message}</span>
    </div>
  )
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  return d.toLocaleString("en-ZA", { dateStyle: "medium", timeStyle: "short" })
}
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  return d.toLocaleDateString("en-ZA", { dateStyle: "medium" })
}

/** Runs `fn` immediately and then every `ms` while `active`; stops when fn returns true. */
export function usePoll(active: boolean, fn: () => Promise<boolean>, ms = 3000) {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    if (!active) return
    let stop = false
    let timer: ReturnType<typeof setTimeout>
    const tick = async () => {
      let done = false
      try {
        done = await ref.current()
      } catch {
        done = false
      }
      if (!stop && !done) timer = setTimeout(tick, ms)
    }
    timer = setTimeout(tick, ms)
    return () => {
      stop = true
      clearTimeout(timer)
    }
  }, [active, ms])
}

export function Pill({ children, tone = "muted" }: { children: ReactNode; tone?: "muted" | "good" | "bad" | "warn" | "info" }) {
  const t = {
    muted: "border-border text-muted-foreground",
    good: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
    bad: "border-red-500/40 bg-red-500/10 text-red-300",
    warn: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    info: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  }[tone]
  return <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium", t)}>{children}</span>
}

export function ExternalLink({ href, children }: { href: string | null; children: ReactNode }) {
  if (!href) return <span>{children}</span>
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="break-all text-primary underline-offset-2 hover:underline">
      {children}
    </a>
  )
}

/** Firecrawl credits indicator, with an admin control that the server authorises. */
export function UsageIndicator({ refreshKey }: { refreshKey?: number }) {
  const [usage, setUsage] = useState<Usage | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [monthly, setMonthly] = useState("")
  const [daily, setDaily] = useState("")
  const [saveErr, setSaveErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setUsage(await getUsage())
      setErr(null)
    } catch (e) {
      setErr(errText(e))
    }
  }, [])
  useEffect(() => {
    void load()
  }, [load, refreshKey])

  async function save() {
    setSaveErr(null)
    const num = (s: string) => (s.trim() === "" ? null : Number(s))
    const m = num(monthly)
    const d = num(daily)
    if ((m !== null && (!Number.isInteger(m) || m < 0)) || (d !== null && (!Number.isInteger(d) || d < 0))) {
      setSaveErr("Limits must be whole numbers, or empty for the platform default.")
      return
    }
    try {
      setUsage(await setUsageLimits({ monthly_cap: m, daily_cap: d }))
      setEditing(false)
    } catch (e) {
      setSaveErr(errText(e))
    }
  }

  const pct = usage && usage.month.cap > 0 ? Math.min(100, (usage.month.used / usage.month.cap) * 100) : 0
  return (
    <div className="rounded-md border border-border bg-secondary/20 px-3 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Gauge className="h-3.5 w-3.5 text-muted-foreground" />
        {usage ? (
          <>
            <span className="font-medium text-foreground">
              Firecrawl credits this month: {usage.month.used} / {usage.month.cap}
            </span>
            <span className="text-muted-foreground">
              today {usage.day.used} / {usage.day.cap}
            </span>
            <div className="h-1.5 w-24 overflow-hidden rounded bg-muted" aria-hidden>
              <div className={cn("h-full", pct >= 90 ? "bg-red-400" : "bg-primary")} style={{ width: `${pct}%` }} />
            </div>
            <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => setEditing((v) => !v)}>
              Limits
            </Button>
          </>
        ) : (
          <span className="text-muted-foreground">{err ?? "Loading credit usage…"}</span>
        )}
      </div>
      {usage?.note && <p className="mt-1 text-muted-foreground">{usage.note}</p>}
      {editing && (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <label className="text-muted-foreground">
            Monthly cap
            <input className={cn(inputCls, "mt-1 w-28")} inputMode="numeric" value={monthly} onChange={(e) => setMonthly(e.target.value)} placeholder="default" />
          </label>
          <label className="text-muted-foreground">
            Daily cap
            <input className={cn(inputCls, "mt-1 w-28")} inputMode="numeric" value={daily} onChange={(e) => setDaily(e.target.value)} placeholder="default" />
          </label>
          <Button size="sm" className="h-9" onClick={save}>
            Save (admin)
          </Button>
          <p className="basis-full text-muted-foreground">Admins can only lower caps below the platform default.</p>
          <ErrorNote message={saveErr} className="basis-full" />
        </div>
      )}
    </div>
  )
}
