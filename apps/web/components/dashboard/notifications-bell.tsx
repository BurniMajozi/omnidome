"use client"

/**
 * Header bell backed by the event-bus notifications feed (SPEC-event-bus.md),
 * served by the orchestrator at /api/orchestrator/notifications.
 */
import { useCallback, useEffect, useState } from "react"
import { Bell, CheckCheck, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

type Notification = {
  id: string
  category: string
  severity: "info" | "warning" | "critical"
  title: string
  body: string | null
  link: string | null
  subject_type: string | null
  subject_id: string | null
  created_at: string
  read_at: string | null
}

const POLL_MS = 30_000
const API = "/api/orchestrator/notifications"

const SEVERITY_DOT: Record<Notification["severity"], string> = {
  info: "bg-sky-400",
  warning: "bg-amber-400",
  critical: "bg-red-500",
}

function timeAgo(iso: string, now: number): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return "just now"
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return `${Math.round(hours / 24)} d ago`
}

/** Tell the owning module to open the record a notification is about. */
function openSubject(n: Notification) {
  if (n.subject_type === "lead" && n.subject_id) {
    window.dispatchEvent(new CustomEvent("omnidome:open-lead", { detail: { id: n.subject_id } }))
  }
}

export function NotificationsBell() {
  const [items, setItems] = useState<Notification[]>([])
  const [unread, setUnread] = useState(0)
  const [loading, setLoading] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}?limit=30`, { cache: "no-store", signal: AbortSignal.timeout(10000) })
      if (!res.ok) return
      const body = (await res.json()) as { data: Notification[]; unread: number }
      setItems(body.data ?? [])
      setUnread(body.unread ?? 0)
      setNow(Date.now())
    } catch {
      /* feed is best-effort; the bell simply stays as it was */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const tick = () => {
      if (!cancelled && document.visibilityState === "visible") void load()
    }
    const first = setTimeout(tick, 0)
    const timer = setInterval(tick, POLL_MS)
    return () => {
      cancelled = true
      clearTimeout(first)
      clearInterval(timer)
    }
  }, [load])

  const markRead = async (n: Notification) => {
    if (!n.read_at) {
      setItems((prev) => prev.map((i) => (i.id === n.id ? { ...i, read_at: new Date().toISOString() } : i)))
      setUnread((u) => Math.max(0, u - 1))
      void fetch(`${API}/${n.id}/read`, { method: "POST" }).catch(() => undefined)
    }
    openSubject(n)
  }

  const markAllRead = async () => {
    setItems((prev) => prev.map((i) => ({ ...i, read_at: i.read_at ?? new Date().toISOString() })))
    setUnread(0)
    await fetch(`${API}/read-all`, { method: "POST" }).catch(() => undefined)
  }

  return (
    <DropdownMenu onOpenChange={(open) => open && void load()}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          title="Notifications"
          aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        >
          <Bell className="h-5 w-5" />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 min-w-4 h-4 px-1 rounded-full bg-primary text-[10px] font-semibold leading-4 text-primary-foreground text-center">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[22rem] max-w-[calc(100vw-2rem)] p-0">
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <span className="text-sm font-semibold text-foreground">Notifications</span>
          <div className="flex items-center gap-2">
            {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
            <button
              type="button"
              onClick={() => void markAllRead()}
              disabled={unread === 0}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground disabled:opacity-40"
            >
              <CheckCheck className="h-3.5 w-3.5" /> Mark all read
            </button>
          </div>
        </div>
        <div className="max-h-[26rem] overflow-y-auto">
          {items.length === 0 ? (
            <p className="px-3 py-8 text-center text-xs text-muted-foreground">
              Nothing yet. Escalations, assignments, failed deliveries and automation results show up here.
            </p>
          ) : (
            items.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => void markRead(n)}
                className={`flex w-full gap-2.5 border-b border-border/60 px-3 py-2.5 text-left hover:bg-muted/50 ${
                  n.read_at ? "opacity-70" : ""
                }`}
              >
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEVERITY_DOT[n.severity] ?? SEVERITY_DOT.info}`} />
                <span className="min-w-0 flex-1">
                  <span className={`block text-xs ${n.read_at ? "text-foreground" : "font-semibold text-foreground"}`}>
                    {n.title}
                  </span>
                  {n.body && <span className="mt-0.5 block text-[11px] text-muted-foreground line-clamp-2">{n.body}</span>}
                  <span className="mt-0.5 block text-[10px] text-muted-foreground/80">
                    {n.category} · {timeAgo(n.created_at, now)}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
