"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ArrowLeft, Loader2, Pencil, Plus, RefreshCcw, Trash2 } from "lucide-react"
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  AnalyticsApiError,
  createCompetitor,
  deleteCompetitor,
  getChanges,
  getCompetitor,
  getCompetitorActivity,
  getCompetitorOverview,
  getPricingHistory,
  getPromotions,
  getSnapshots,
  safeHttpUrl,
  scanCompetitor,
  updateCompetitor,
  type ActivityItem,
  type Competitor,
  type CompetitorInput,
  type CompetitorOverviewItem,
  type PlanChange,
  type PricingHistory,
  type PromotionsView,
  type Snapshot,
} from "@/lib/analytics-ai-api"
import {
  ErrorNote,
  ExternalLink,
  NO_RUN_TIP,
  Pill,
  UsageIndicator,
  errText,
  fmtDate,
  fmtDateTime,
  inputCls,
  usePermission,
  usePoll,
} from "./shared"

const LINE_COLORS = ["#38bdf8", "#4ade80", "#f59e0b", "#f472b6", "#a78bfa", "#fb7185", "#2dd4bf", "#facc15"]

function scanTone(s: Competitor["scan_status"]) {
  return s === "ok" ? "good" : s === "failed" ? "bad" : s === "no_data" ? "warn" : s === "scanning" ? "info" : "muted"
}
const scanLabel: Record<Competitor["scan_status"], string> = {
  never: "Not scanned yet",
  scanning: "Scanning",
  ok: "Scanned",
  no_data: "No pricing found",
  failed: "Scan failed",
}

function money(n: number | null | undefined, cur?: string | null) {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—"
  const prefix = !cur || cur === "ZAR" ? "R " : `${cur} `
  return `${prefix}${n.toLocaleString("en-ZA", { maximumFractionDigits: 2 })}`
}

export function describeChange(c: PlanChange): string {
  switch (c.change_type) {
    case "price_up":
    case "price_down": {
      const pct = typeof c.pct_change === "number" ? ` (${c.pct_change > 0 ? "+" : ""}${c.pct_change.toFixed(1)}%)` : ""
      const abs = typeof c.abs_change === "number" ? `${c.abs_change > 0 ? "+" : "-"}${money(Math.abs(c.abs_change), c.currency)}` : ""
      return `${c.subject}: ${c.old_value ?? "?"} → ${c.new_value ?? "?"} ${abs}${pct}`.replace(/\s+/g, " ")
    }
    case "new_plan":
      return `New plan: ${c.subject}${c.new_value ? ` at ${c.new_value}` : ""}`
    case "removed_plan":
      return `Plan removed: ${c.subject}`
    case "new_promotion":
      return `New promotion: ${c.subject}${c.new_value ? ` (${c.new_value})` : ""}`
    case "ended_promotion":
      return `Promotion ended: ${c.subject}`
    case "promotion_changed":
      return `Promotion changed: ${c.subject}`
    default:
      return `${c.subject}: ${c.old_value ?? "?"} → ${c.new_value ?? "?"}`
  }
}

function changeTone(t: PlanChange["change_type"]) {
  return t === "price_up" ? "bad" : t === "price_down" ? "good" : t === "removed_plan" || t === "ended_promotion" ? "warn" : "info"
}

function ChangeRow({ c, showName }: { c: PlanChange; showName?: boolean }) {
  const href = safeHttpUrl(c.source_url)
  return (
    <li className="flex flex-wrap items-start gap-2 py-2 text-sm">
      <Pill tone={changeTone(c.change_type)}>{c.change_type.replace(/_/g, " ")}</Pill>
      <div className="min-w-0 flex-1">
        <p className="break-words text-foreground">
          {showName && c.competitor_name ? <span className="font-medium">{c.competitor_name}: </span> : null}
          {describeChange(c)}
        </p>
        <p className="text-xs text-muted-foreground">
          {fmtDateTime(c.detected_at)}
          {c.verified === false && " · price not found literally on the page"}
          {href && (
            <>
              {" · "}
              <ExternalLink href={href}>source</ExternalLink>
            </>
          )}
        </p>
      </div>
    </li>
  )
}

// ── Form ────────────────────────────────────────────────────────────
function validateUrl(label: string, v: string, required: boolean): string | null {
  const s = v.trim()
  if (!s) return required ? `${label} is required.` : null
  if (s.length > 2000) return `${label} is too long.`
  try {
    const u = new URL(s)
    if (u.protocol !== "https:") return `${label} must be a public https:// address.`
    if (u.username || u.password) return `${label} must not contain credentials.`
  } catch {
    return `${label} is not a valid URL.`
  }
  return null
}

function CompetitorForm({ initial, onSaved, onCancel }: { initial?: Competitor; onSaved: (c: Competitor) => void; onCancel: () => void }) {
  const { markDenied } = usePermission()
  const [name, setName] = useState(initial?.name ?? "")
  const [website, setWebsite] = useState(initial?.website ?? "")
  const [pricing, setPricing] = useState(initial?.pricing_page_url ?? "")
  const [promo, setPromo] = useState(initial?.promo_page_url ?? "")
  const [active, setActive] = useState(initial?.active ?? true)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function save() {
    setErr(null)
    if (!name.trim() || name.trim().length > 120) return setErr("Enter a name (max 120 characters).")
    const e = validateUrl("Website", website, true) ?? validateUrl("Pricing page", pricing, false) ?? validateUrl("Promotions page", promo, false)
    if (e) return setErr(e)
    setBusy(true)
    try {
      const body: CompetitorInput = {
        name: name.trim(),
        website: website.trim(),
        pricing_page_url: pricing.trim() || null,
        promo_page_url: promo.trim() || null,
      }
      const saved = initial ? await updateCompetitor(initial.id, { ...body, active }) : await createCompetitor(body)
      onSaved(saved)
    } catch (x) {
      if (x instanceof AnalyticsApiError && x.forbidden) markDenied()
      setErr(errText(x))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="surface-card space-y-3 p-4">
      <h3 className="text-sm font-semibold text-foreground">{initial ? `Edit ${initial.name}` : "Add competitor"}</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-xs font-medium text-muted-foreground">
          Name
          <input className={cn(inputCls, "mt-1")} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="text-xs font-medium text-muted-foreground">
          Website (https)
          <input className={cn(inputCls, "mt-1")} value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="https://www.example.co.za" />
        </label>
        <label className="text-xs font-medium text-muted-foreground">
          Pricing page (optional, otherwise discovered)
          <input className={cn(inputCls, "mt-1")} value={pricing} onChange={(e) => setPricing(e.target.value)} />
        </label>
        <label className="text-xs font-medium text-muted-foreground">
          Promotions page (optional)
          <input className={cn(inputCls, "mt-1")} value={promo} onChange={(e) => setPromo(e.target.value)} />
        </label>
      </div>
      {initial && (
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active
        </label>
      )}
      <ErrorNote message={err} />
      <div className="flex gap-2">
        <Button onClick={save} disabled={busy}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}Save
        </Button>
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

// ── Detail ──────────────────────────────────────────────────────────
type Tab = "pricing" | "history" | "promotions" | "changes" | "snapshots"
const TABS: { id: Tab; label: string }[] = [
  { id: "pricing", label: "Pricing" },
  { id: "history", label: "Price history" },
  { id: "promotions", label: "Promotions" },
  { id: "changes", label: "Changes" },
  { id: "snapshots", label: "Snapshots" },
]

function PriceHistoryChart({ data }: { data: PricingHistory }) {
  const { rows, plans } = useMemo(() => {
    const plans = data.plans.filter((p) => p.points.some((pt) => pt.price_amount !== null))
    const byTime = new Map<string, Record<string, number | string>>()
    plans.forEach((p) =>
      p.points.forEach((pt) => {
        if (pt.price_amount === null) return
        const row = byTime.get(pt.scanned_at) ?? { t: pt.scanned_at }
        row[p.plan_key] = pt.price_amount
        byTime.set(pt.scanned_at, row)
      }),
    )
    const rows = [...byTime.values()].sort((a, b) => String(a.t).localeCompare(String(b.t)))
    return { rows, plans }
  }, [data])
  if (plans.length === 0) return <p className="text-sm text-muted-foreground">No priced plans have been recorded yet.</p>
  const single = rows.length < 2
  return (
    <div>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.25)" />
            <XAxis dataKey="t" tickFormatter={(v) => fmtDate(String(v))} fontSize={11} stroke="#888" />
            <YAxis fontSize={11} stroke="#888" width={56} tickFormatter={(v) => `R${v}`} />
            <Tooltip
              labelFormatter={(v) => fmtDateTime(String(v))}
              formatter={(v: number, k: string) => [money(v, plans[0]?.currency), plans.find((p) => p.plan_key === k)?.plan_name ?? k]}
              contentStyle={{ backgroundColor: "var(--card, #1a1a2e)", border: "1px solid rgba(128,128,128,0.4)", borderRadius: 8 }}
            />
            <Legend formatter={(k) => plans.find((p) => p.plan_key === k)?.plan_name ?? k} />
            {plans.map((p, i) => (
              <Line
                key={p.plan_key}
                type="stepAfter"
                dataKey={p.plan_key}
                stroke={LINE_COLORS[i % LINE_COLORS.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      {single && <p className="mt-2 text-xs text-muted-foreground">Only one scan so far, so no trend yet. Each point is a real scan result.</p>}
      <p className="mt-1 text-xs text-muted-foreground">Based on {data.snapshots_considered} scan(s). Gaps mean the plan had no price in that scan.</p>
    </div>
  )
}

function CompetitorDetail({ id, onBack, onChanged }: { id: string; onBack: () => void; onChanged: () => void }) {
  const { denied, markDenied } = usePermission()
  const [comp, setComp] = useState<Competitor | null>(null)
  const [tab, setTab] = useState<Tab>("pricing")
  const [snaps, setSnaps] = useState<Snapshot[] | null>(null)
  const [history, setHistory] = useState<PricingHistory | null>(null)
  const [promos, setPromos] = useState<PromotionsView | null>(null)
  const [changes, setChanges] = useState<PlanChange[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [scanMsg, setScanMsg] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [usageKey, setUsageKey] = useState(0)

  const loadAll = useCallback(async () => {
    try {
      const [c, s, h, p, ch] = await Promise.all([
        getCompetitor(id),
        getSnapshots(id, 20, 0),
        getPricingHistory(id),
        getPromotions(id),
        getChanges(id, 50, 0),
      ])
      setComp(c)
      setSnaps(s.items)
      setHistory(h)
      setPromos(p)
      setChanges(ch.items)
      setErr(null)
    } catch (e) {
      setErr(errText(e))
    }
  }, [id])
  useEffect(() => {
    void loadAll()
  }, [loadAll])

  const scanning = comp?.scan_status === "scanning"
  usePoll(scanning, async () => {
    const c = await getCompetitor(id)
    setComp(c)
    if (c.scan_status !== "scanning") {
      await loadAll()
      onChanged()
      setUsageKey((k) => k + 1)
      return true
    }
    return false
  })

  async function scan() {
    setErr(null)
    setScanMsg(null)
    try {
      const r = await scanCompetitor(id)
      setScanMsg(`${r.message} Estimated ${r.estimated_credits} credits.`)
      setComp((c) => (c ? { ...c, scan_status: r.scan_status } : c))
      setUsageKey((k) => k + 1)
    } catch (e) {
      if (e instanceof AnalyticsApiError && e.forbidden) markDenied()
      setErr(errText(e))
    }
  }

  async function remove() {
    if (!window.confirm("Delete this competitor and all its history?")) return
    try {
      await deleteCompetitor(id)
      onChanged()
      onBack()
    } catch (e) {
      setErr(errText(e))
    }
  }

  const latest = snaps?.[0]
  const pagesRead = latest?.pages ?? []

  if (!comp) return <div>{err ? <ErrorNote message={err} /> : <p className="text-sm text-muted-foreground">Loading…</p>}</div>
  if (editing)
    return (
      <CompetitorForm
        initial={comp}
        onCancel={() => setEditing(false)}
        onSaved={(c) => {
          setComp(c)
          setEditing(false)
          onChanged()
        }}
      />
    )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Button variant="ghost" size="sm" className="-ml-2 mb-1" onClick={onBack}>
            <ArrowLeft className="h-3.5 w-3.5" />
            All competitors
          </Button>
          <h2 className="break-words text-lg font-semibold text-foreground">{comp.name}</h2>
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <ExternalLink href={safeHttpUrl(comp.website)}>{comp.website}</ExternalLink>
            <Pill tone={scanTone(comp.scan_status)}>{scanLabel[comp.scan_status]}</Pill>
            <span>Last scanned: {comp.last_scanned_at ? fmtDateTime(comp.last_scanned_at) : "Not scanned yet"}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={scan} disabled={scanning || denied} title={denied ? NO_RUN_TIP : undefined}>
            {scanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
            {scanning ? "Scanning…" : "Scan now"}
          </Button>
          <Button variant="outline" onClick={() => setEditing(true)} disabled={denied} title={denied ? NO_RUN_TIP : undefined}>
            <Pencil className="h-4 w-4" />
            Edit
          </Button>
          <Button variant="ghost" aria-label="Delete competitor (admin)" title="Delete (admin only)" onClick={remove}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <UsageIndicator refreshKey={usageKey} />
      {scanMsg && <p className="text-xs text-muted-foreground">{scanMsg}</p>}
      {comp.scan_status === "failed" && comp.last_error && <ErrorNote message={comp.last_error} />}
      {comp.scan_status === "no_data" && (
        <p className="text-sm text-amber-300">The last scan could not read any pricing from the pages. Try giving the exact pricing page URL.</p>
      )}
      <ErrorNote message={err} />

      <div className="flex flex-wrap gap-1 border-b border-border" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "border-b-2 px-3 py-2 text-sm font-medium",
              tab === t.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "pricing" &&
        (!latest ? (
          <p className="text-sm text-muted-foreground">Not scanned yet. Press “Scan now” to read this competitor’s pricing page.</p>
        ) : latest.plans.length === 0 ? (
          <p className="text-sm text-muted-foreground">The latest scan ({fmtDateTime(latest.scanned_at)}) found no plans.</p>
        ) : (
          <div className="space-y-2">
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-left text-xs">
                <thead className="bg-secondary/40 text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Plan</th>
                    <th className="px-3 py-2">Price</th>
                    <th className="px-3 py-2">Speed</th>
                    <th className="px-3 py-2">Terms</th>
                    <th className="px-3 py-2">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {latest.plans.map((p) => {
                    const href = safeHttpUrl(p.source_url)
                    return (
                      <tr key={p.plan_key} className="border-t border-border align-top">
                        <td className="px-3 py-2 font-medium">{p.plan_name}</td>
                        <td className="px-3 py-2">
                          {p.price_amount !== null ? money(p.price_amount, p.currency) : p.price_text ?? "—"}
                          {p.billing_period ? <span className="text-muted-foreground"> / {p.billing_period}</span> : null}{" "}
                          {!p.price_verified && <Pill tone="warn">unverified</Pill>}
                        </td>
                        <td className="px-3 py-2">{p.speed_text ?? (p.speed_down_mbps ? `${p.speed_down_mbps} Mbps` : "—")}</td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {[p.data_text, p.contract_term, p.setup_fee_text && `Setup ${p.setup_fee_text}`, p.promo_text].filter(Boolean).join(" · ") || "—"}
                        </td>
                        <td className="px-3 py-2">
                          {href ? <ExternalLink href={href}>Open</ExternalLink> : "—"}
                          <div className="text-muted-foreground">{fmtDateTime(latest.scanned_at)}</div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-muted-foreground">
              “Unverified” means the price was not found literally in the fetched page text; check the source before relying on it.
            </p>
          </div>
        ))}

      {tab === "history" && (history ? <PriceHistoryChart data={history} /> : <p className="text-sm text-muted-foreground">Loading…</p>)}

      {tab === "promotions" &&
        (promos ? (
          <div className="space-y-4 text-sm">
            <section>
              <h4 className="mb-1 font-semibold">Active</h4>
              {promos.active.length === 0 && promos.plan_promos.length === 0 ? (
                <p className="text-muted-foreground">No active promotions in the latest scan.</p>
              ) : (
                <ul className="space-y-2">
                  {promos.active.map((p) => (
                    <li key={p.promo_key} className="rounded-md border border-border bg-secondary/20 p-3">
                      <p className="font-medium">{p.title}</p>
                      {p.discount_text && <p>{p.discount_text}</p>}
                      {p.description && <p className="text-xs text-muted-foreground">{p.description}</p>}
                      <p className="text-xs text-muted-foreground">
                        {p.valid_until ? `Valid until ${p.valid_until}` : "No end date stated"}
                        {safeHttpUrl(p.source_url) && (
                          <>
                            {" · "}
                            <ExternalLink href={safeHttpUrl(p.source_url)}>source</ExternalLink>
                          </>
                        )}
                      </p>
                    </li>
                  ))}
                  {promos.plan_promos.map((p, i) => (
                    <li key={`pp${i}`} className="rounded-md border border-border bg-secondary/20 p-3">
                      <p className="font-medium">{p.plan_name}</p>
                      <p>{p.promo_text}</p>
                      {p.valid_until && <p className="text-xs text-muted-foreground">Valid until {p.valid_until}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section>
              <h4 className="mb-1 font-semibold">Ended</h4>
              {promos.ended.length === 0 ? (
                <p className="text-muted-foreground">No ended promotions detected.</p>
              ) : (
                <ul className="space-y-1">
                  {promos.ended.map((p, i) => (
                    <li key={i} className="text-muted-foreground">
                      <span className="text-foreground">{p.title}</span> ended (detected {fmtDate(p.ended_detected_at)})
                      {p.last_seen_value ? `, last seen: ${p.last_seen_value}` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ))}

      {tab === "changes" &&
        (changes === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : changes.length === 0 ? (
          <p className="text-sm text-muted-foreground">No changes detected yet. Changes appear after at least two scans.</p>
        ) : (
          <ul className="divide-y divide-border">
            {changes.map((c) => (
              <ChangeRow key={c.id} c={c} />
            ))}
          </ul>
        ))}

      {tab === "snapshots" &&
        (snaps === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : snaps.length === 0 ? (
          <p className="text-sm text-muted-foreground">No snapshots yet.</p>
        ) : (
          <ul className="space-y-2">
            {snaps.map((s) => (
              <li key={s.id} className="rounded-md border border-border p-3 text-sm">
                <p className="font-medium">
                  {fmtDateTime(s.scanned_at)} <span className="font-normal text-muted-foreground">· {s.plans_count} plans · {s.promotions_count} promotions · {s.extraction_method}</span>
                </p>
                <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                  {s.pages.map((p, i) => (
                    <li key={i}>
                      {p.kind}: <ExternalLink href={safeHttpUrl(p.url)}>{p.url}</ExternalLink> · {p.status}
                      {p.error ? ` (${p.error})` : ""}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        ))}
      {tab === "pricing" && pagesRead.length > 0 && null}
    </div>
  )
}

// ── Overview ────────────────────────────────────────────────────────
export function CompetitorsView() {
  const { denied } = usePermission()
  const [list, setList] = useState<CompetitorOverviewItem[] | null>(null)
  const [activity, setActivity] = useState<ActivityItem[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  const load = useCallback(async () => {
    try {
      const [o, a] = await Promise.all([getCompetitorOverview(), getCompetitorActivity(30)])
      setList(o.competitors)
      setActivity(a.items)
      setErr(null)
    } catch (e) {
      setErr(errText(e))
    }
  }, [])
  useEffect(() => {
    void load()
  }, [load])

  const scanningAny = !!list?.some((c) => c.scan_status === "scanning")
  usePoll(scanningAny && !selected, async () => {
    await load()
    return false
  }, 5000)

  if (selected) return <CompetitorDetail id={selected} onBack={() => setSelected(null)} onChanged={load} />

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Competitor Analysis</h2>
          <p className="text-sm text-muted-foreground">Public pricing and promotions, scanned from competitors’ own web pages.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <UsageIndicator />
          <Button onClick={() => setAdding(true)} disabled={denied} title={denied ? NO_RUN_TIP : undefined}>
            <Plus className="h-4 w-4" />
            Add competitor
          </Button>
        </div>
      </div>
      <ErrorNote message={err} />
      {adding && (
        <CompetitorForm
          onCancel={() => setAdding(false)}
          onSaved={(c) => {
            setAdding(false)
            void load()
            setSelected(c.id)
          }}
        />
      )}

      {list === null && !err ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : list && list.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-secondary/20 p-6 text-center text-sm text-muted-foreground">
          No competitors tracked yet. Add one to start monitoring their prices.
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {list?.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setSelected(c.id)}
              className="surface-card space-y-2 p-4 text-left transition hover:border-primary/50"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="break-words font-semibold text-foreground">{c.name}</p>
                <Pill tone={scanTone(c.scan_status)}>{scanLabel[c.scan_status]}</Pill>
              </div>
              <p className="text-xs text-muted-foreground">
                Last scanned: {c.last_scanned_at ? fmtDateTime(c.last_scanned_at) : "Not scanned yet"}
              </p>
              {c.last_scanned_at && (
                <p className="text-xs text-foreground/80">
                  {c.plans_count} plans · {c.promotions_count} promotions
                </p>
              )}
              {c.latest_changes.length > 0 && (
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {c.latest_changes.map((ch) => (
                    <li key={ch.id} className="truncate">
                      {describeChange(ch)}
                    </li>
                  ))}
                </ul>
              )}
            </button>
          ))}
        </div>
      )}

      <div className="surface-card p-4">
        <h3 className="mb-1 text-sm font-semibold text-foreground">Activity</h3>
        {activity.length === 0 ? (
          <p className="text-sm text-muted-foreground">No scans or changes recorded yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {activity.map((a, i) =>
              a.kind === "change" ? (
                <ChangeRow key={`c${a.id}`} c={a} showName />
              ) : (
                <li key={`s${i}`} className="py-2 text-sm text-muted-foreground">
                  <span className="font-medium text-foreground">{a.competitor_name}</span> scanned: {a.plans_count} plans, {a.promotions_count} promotions
                  <span className="block text-xs">{fmtDateTime(a.at)}</span>
                </li>
              ),
            )}
          </ul>
        )}
      </div>
    </div>
  )
}
