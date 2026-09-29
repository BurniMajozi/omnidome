"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import {
  MarketApiError,
  acknowledgeSignal,
  createWatch,
  deleteWatch,
  getCompare,
  listSignals,
  listWatches,
  scanAll,
  scanWatch,
  updateWatch,
  type CompareRow,
  type MarketSignal,
  type MarketWatch,
  type WatchCategory,
} from "@/lib/market-api"
import type { Plan } from "@/lib/products-api"

const formatCurrency = (value: number | null | undefined) =>
  value == null ? "-" : `R ${value.toLocaleString("en-ZA")}`

const CATEGORIES: WatchCategory[] = ["fibre", "lte", "wireless", "other"]

const SIGNAL_LABEL: Record<string, string> = {
  price_change: "Price change",
  new_plan: "New plan",
  removed_plan: "Plan removed",
  speed_change: "Speed change",
}

function describeSignal(s: MarketSignal): string {
  const b = s.before as Record<string, number | null> | null
  const a = s.after as Record<string, number | null> | null
  if (s.type === "price_change") return `${formatCurrency(b?.price_zar)} → ${formatCurrency(a?.price_zar)}`
  if (s.type === "speed_change")
    return `${b?.speed_down_mbps ?? "?"}/${b?.speed_up_mbps ?? "?"} → ${a?.speed_down_mbps ?? "?"}/${a?.speed_up_mbps ?? "?"} Mbps`
  const p = (s.type === "new_plan" ? a : b) as Record<string, number | null> | null
  return p?.price_zar != null ? formatCurrency(p.price_zar) : ""
}

function errMsg(e: unknown): string {
  return e instanceof MarketApiError || e instanceof Error ? e.message : "Something went wrong"
}

export function MarketWatchView({ plans }: { plans: Plan[] }) {
  const [watches, setWatches] = useState<MarketWatch[]>([])
  const [signals, setSignals] = useState<MarketSignal[]>([])
  const [compare, setCompare] = useState<CompareRow[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [form, setForm] = useState<{ competitor_name: string; url: string; category: WatchCategory }>({
    competitor_name: "",
    url: "",
    category: "fibre",
  })

  const refresh = useCallback(async () => {
    try {
      const [w, s, c] = await Promise.all([listWatches(), listSignals(), getCompare()])
      setWatches(w)
      setSignals(s)
      setCompare(c)
      setLoadError(null)
    } catch (e) {
      setLoadError(errMsg(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key)
    setActionError(null)
    try {
      await fn()
    } catch (e) {
      setActionError(errMsg(e))
    } finally {
      await refresh()
      setBusy(null)
    }
  }

  const submit = () =>
    run("save", async () => {
      if (editing) await updateWatch(editing, form)
      else await createWatch(form)
      setEditing(null)
      setForm({ competitor_name: "", url: "", category: "fibre" })
    })

  const startEdit = (w: MarketWatch) => {
    setEditing(w.id)
    setForm({ competitor_name: w.competitor_name, url: w.url, category: w.category })
  }

  // Our cheapest active plan per category (billing catalog) for the price delta.
  const ourCheapest = useMemo(() => {
    const map: Record<string, number> = {}
    for (const p of plans) {
      if (!p.is_active || !p.category) continue
      const k = p.category.toLowerCase()
      map[k] = Math.min(map[k] ?? Infinity, p.price)
    }
    return map
  }, [plans])

  const unacked = signals.filter((s) => !s.acknowledged)

  if (loading) return <p className="py-12 text-center text-sm text-muted-foreground">Loading market watch...</p>

  return (
    <div className="space-y-4">
      {loadError && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          Market watch is unavailable: {loadError}
        </div>
      )}
      {actionError && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {actionError}
        </div>
      )}

      <Card className="border-border bg-card">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Watched competitor pages</CardTitle>
          <Button
            size="sm"
            variant="outline"
            disabled={busy !== null || watches.length === 0}
            onClick={() => run("all", scanAll)}
          >
            {busy === "all" ? "Scanning..." : "Scan all"}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2 md:grid-cols-[1fr_2fr_auto_auto]">
            <Input
              placeholder="Competitor name"
              value={form.competitor_name}
              onChange={(e) => setForm({ ...form, competitor_name: e.target.value })}
            />
            <Input
              placeholder="https://competitor.co.za/pricing"
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
            />
            <select
              className="rounded-md border border-border bg-background px-2 text-sm"
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value as WatchCategory })}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={busy !== null || !form.competitor_name.trim() || !/^https?:\/\//.test(form.url)}
                onClick={submit}
              >
                {editing ? "Save" : "Add watch"}
              </Button>
              {editing && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setEditing(null)
                    setForm({ competitor_name: "", url: "", category: "fibre" })
                  }}
                >
                  Cancel
                </Button>
              )}
            </div>
          </div>

          {watches.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No competitor pages are being watched yet. Add a pricing page above to start tracking price changes.
            </p>
          ) : (
            <div className="space-y-2">
              {watches.map((w) => (
                <div
                  key={w.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      {w.competitor_name} <Badge variant="secondary">{w.category}</Badge>
                      {!w.active && <Badge variant="outline">paused</Badge>}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">{w.url}</p>
                    <p className={`text-xs ${w.last_status === "failed" ? "text-destructive" : "text-muted-foreground"}`}>
                      {w.last_status === "never"
                        ? "Not scanned yet"
                        : `${w.last_status.replace("_", " ")}${
                            w.last_scraped_at ? ` · ${new Date(w.last_scraped_at).toLocaleString("en-ZA")}` : ""
                          }`}
                      {w.last_error ? ` · ${w.last_error}` : ""}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" disabled={busy !== null} onClick={() => run(`scan-${w.id}`, () => scanWatch(w.id))}>
                      {busy === `scan-${w.id}` ? "Scanning..." : "Scan now"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy !== null}
                      onClick={() => run(`tog-${w.id}`, () => updateWatch(w.id, { active: !w.active }))}
                    >
                      {w.active ? "Pause" : "Resume"}
                    </Button>
                    <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => startEdit(w)}>
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={busy !== null}
                      onClick={() => {
                        if (window.confirm(`Delete watch for ${w.competitor_name}? Its history is removed too.`))
                          void run(`del-${w.id}`, () => deleteWatch(w.id))
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Signals ({unacked.length} unacknowledged)</CardTitle>
        </CardHeader>
        <CardContent>
          {signals.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No changes detected yet. Signals appear after a watch has been scanned at least twice and something changed.
            </p>
          ) : (
            <div className="space-y-2">
              {signals.map((s) => (
                <div
                  key={s.id}
                  className={`flex items-center justify-between gap-2 rounded-md border border-border p-3 ${
                    s.acknowledged ? "opacity-60" : ""
                  }`}
                >
                  <div className="text-sm">
                    <Badge variant={s.type === "price_change" ? "default" : "secondary"}>
                      {SIGNAL_LABEL[s.type] ?? s.type}
                    </Badge>{" "}
                    <span className="font-medium">{s.competitor_name}</span> · {s.plan_name}{" "}
                    <span className="text-muted-foreground">{describeSignal(s)}</span>
                    <p className="text-xs text-muted-foreground">
                      {s.detected_at ? new Date(s.detected_at).toLocaleString("en-ZA") : ""}
                    </p>
                  </div>
                  {!s.acknowledged && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy !== null}
                      onClick={() => run(`ack-${s.id}`, () => acknowledgeSignal(s.id))}
                    >
                      Acknowledge
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Competitor vs us</CardTitle>
        </CardHeader>
        <CardContent>
          {compare.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No competitor prices captured yet. Scan a watch to populate this table.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="py-2 pr-3">Competitor</th>
                    <th className="pr-3">Plan</th>
                    <th className="pr-3">Speed (down/up)</th>
                    <th className="pr-3">Price</th>
                    <th className="pr-3">Our cheapest (same category)</th>
                    <th>Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {compare.map((r, i) => {
                    const ours = ourCheapest[r.category]
                    const delta = ours != null && r.price_zar != null ? r.price_zar - ours : null
                    return (
                      <tr key={`${r.watch_id}-${r.plan_name}-${i}`} className="border-b border-border/50">
                        <td className="py-2 pr-3">{r.competitor_name}</td>
                        <td className="pr-3">{r.plan_name}</td>
                        <td className="pr-3">
                          {r.speed_down_mbps ?? "?"}/{r.speed_up_mbps ?? "?"} Mbps
                        </td>
                        <td className="pr-3">{formatCurrency(r.price_zar)}</td>
                        <td className="pr-3">{ours != null ? formatCurrency(ours) : "-"}</td>
                        <td
                          className={
                            delta == null
                              ? "text-muted-foreground"
                              : delta < 0
                                ? "font-medium text-red-500"
                                : delta > 0
                                  ? "font-medium text-emerald-500"
                                  : ""
                          }
                        >
                          {delta == null ? "-" : `${delta > 0 ? "+" : ""}${formatCurrency(delta)}`}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <p className="mt-2 text-xs text-muted-foreground">
                Red: competitor is cheaper than our cheapest active plan in that category. Green: we are cheaper.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
