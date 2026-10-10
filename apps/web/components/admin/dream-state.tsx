"use client"

/**
 * Memory health / Dream state (docs/dream-state.md): last nightly run + health score, trend, findings with apply/dismiss,
 * "Run now (dry run)" and the per-tenant settings. Rendered inside the Agent Management memory panel. Admin only: every
 * call needs an admin role, so a 403 renders as an explanation rather than an error.
 */
import { useCallback, useEffect, useMemo, useState } from "react"
import { AlertTriangle, CheckCircle2, Loader2, Moon, Play, RefreshCw, Save, ShieldAlert } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  DreamApiError,
  getDreamFindings,
  getDreamStatus,
  putDreamSettings,
  resolveDreamFinding,
  runDream,
  type DreamFinding,
  type DreamSettings,
  type DreamSeverity,
  type DreamStatus,
} from "@/lib/dream-api"

const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("en-ZA", { dateStyle: "medium", timeStyle: "short" }) : "never")
const pct = (v?: number | null) => (v == null ? "n/a" : `${Math.round(v * 100)}%`)
const num = (v?: number | null) => new Intl.NumberFormat("en-ZA").format(Number(v ?? 0))

const SEV_STYLE: Record<DreamSeverity, string> = {
  critical: "border-red-500/50 bg-red-500/10 text-red-600 dark:text-red-300",
  high: "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-300",
  medium: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  low: "border-border bg-muted/40 text-muted-foreground",
  info: "border-border bg-muted/30 text-muted-foreground",
}
const APPLICABLE = new Set(["refresh", "tombstone", "clear_stale", "set_importance", "delete_edges"])

type Load = { state: "loading" } | { state: "ok"; data: DreamStatus } | { state: "forbidden" } | { state: "off" } | { state: "error"; message: string }

function Spark({ values, label, max }: { values: (number | null)[]; label: string; max: number }) {
  const real = values.filter((v): v is number => v != null)
  if (real.length === 0) return <p className="text-[11px] text-muted-foreground">{label}: no data yet</p>
  return (
    <div>
      <p className="text-[11px] text-muted-foreground">
        {label}: <span className="text-foreground">{real[real.length - 1]}</span>
      </p>
      <div className="flex h-8 items-end gap-0.5" role="img" aria-label={`${label} over the last ${values.length} runs: ${real.join(", ")}`}>
        {values.map((v, i) => (
          <div key={i} className="w-2 rounded-sm bg-primary/60" style={{ height: `${v == null ? 4 : Math.max(8, (v / Math.max(1, max)) * 100)}%`, opacity: v == null ? 0.2 : 1 }} title={v == null ? "no value" : String(v)} />
        ))}
      </div>
    </div>
  )
}

export function DreamStateSection() {
  const [st, setSt] = useState<Load>({ state: "loading" })
  const [findings, setFindings] = useState<DreamFinding[]>([])
  const [filter, setFilter] = useState<"open" | "auto_applied" | "all">("open")
  const [busy, setBusy] = useState<string | null>(null)
  const [confirmReal, setConfirmReal] = useState(false)
  const [msg, setMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null)
  const [form, setForm] = useState<DreamSettings | null>(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setSt({ state: "loading" })
    try {
      const data = await getDreamStatus()
      setSt({ state: "ok", data })
      setForm((f) => f ?? data.settings)
      const fs = await getDreamFindings({ status: filter === "all" ? undefined : filter === "open" ? "open" : "auto_applied", limit: 60 })
      let rows = fs.findings
      if (filter === "open") rows = [...rows, ...(await getDreamFindings({ status: "proposed", limit: 40 })).findings]
      setFindings(rows)
    } catch (e) {
      if (e instanceof DreamApiError && e.status === 403) setSt({ state: "forbidden" })
      else if (e instanceof DreamApiError && e.status === 503) setSt({ state: "off" })
      else setSt({ state: "error", message: e instanceof Error ? e.message : "Dream state unavailable" })
    }
  }, [filter])
  useEffect(() => {
    void load()
  }, [load])

  async function run(dry: boolean) {
    setBusy(dry ? "dry" : "real")
    setMsg(null)
    try {
      const r = await runDream(dry)
      setMsg({ tone: "ok", text: `${dry ? "Dry run" : "Run"} queued (job ${r.job_id.slice(0, 8)}). The knowledge worker starts it within about a minute; refresh to see the result.${dry ? " A dry run changes nothing except the dream log." : ""}` })
    } catch (e) {
      setMsg({ tone: "err", text: e instanceof Error ? e.message : "Could not queue the run" })
    } finally {
      setBusy(null)
      setConfirmReal(false)
    }
  }

  async function resolve(f: DreamFinding, action: "accept" | "dismiss" | "apply") {
    setBusy(f.id)
    setMsg(null)
    try {
      await resolveDreamFinding(f.id, action)
      setFindings((rows) => rows.filter((x) => x.id !== f.id))
      setMsg({ tone: "ok", text: action === "apply" ? "Fix applied (derived data only; your source records are untouched)." : action === "accept" ? "Finding accepted." : "Finding dismissed." })
    } catch (e) {
      setMsg({ tone: "err", text: e instanceof Error ? e.message : "Could not update the finding" })
    } finally {
      setBusy(null)
    }
  }

  async function save() {
    if (!form) return
    setSaving(true)
    setMsg(null)
    try {
      const r = await putDreamSettings({
        enabled: form.enabled, window_start: form.window_start, window_hours: form.window_hours, timezone: form.timezone,
        jev_enabled: form.jev_enabled, jev_max_calls: form.jev_max_calls, jev_max_cost_usd: form.jev_max_cost_usd,
        canary_alert_drop: form.canary_alert_drop, rotation_days: form.rotation_days,
      })
      setForm(r.settings)
      setMsg({ tone: "ok", text: "Dream settings saved." })
      await load()
    } catch (e) {
      setMsg({ tone: "err", text: e instanceof Error ? e.message : "Could not save settings" })
    } finally {
      setSaving(false)
    }
  }

  const data = st.state === "ok" ? st.data : null
  const last = data?.last_run ?? null
  const rep = last?.report
  const sev = data?.findings.open ?? {}
  const trend = useMemo(() => data?.trend ?? [], [data])

  return (
    <section className="space-y-3" aria-label="Memory health and dream state" data-testid="dream-state">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
          <Moon className="h-3.5 w-3.5 text-primary" />
          Memory health / Dream state
        </h3>
        <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => void load()}>
          <RefreshCw className="h-3 w-3" /> Refresh
        </Button>
      </div>

      {msg && (
        <div role="status" className={`rounded-lg border p-3 text-xs ${msg.tone === "ok" ? "border-primary/30 bg-primary/10 text-primary" : "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-300"}`}>
          {msg.text}
        </div>
      )}

      {st.state === "loading" && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading memory health…
        </p>
      )}
      {st.state === "forbidden" && (
        <p role="status" className="rounded-lg border border-border bg-card p-3 text-xs text-muted-foreground">Memory health and the nightly dream state are for admins.</p>
      )}
      {st.state === "off" && (
        <p role="status" className="rounded-lg border border-border bg-card p-3 text-xs text-muted-foreground">
          The knowledge layer is not enabled, so there is nothing to maintain yet (see docs/knowledge-layer.md).
        </p>
      )}
      {st.state === "error" && (
        <div role="alert" className="flex items-center justify-between gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300">
          <span>Dream state unavailable: {st.message}</span>
          <Button size="sm" variant="outline" onClick={() => void load()}>Retry</Button>
        </div>
      )}

      {data && !data.ready && (
        <p role="status" className="rounded-lg border border-border bg-card p-3 text-xs text-muted-foreground">{data.note ?? "The dream tables do not exist yet."}</p>
      )}

      {data && (
        <>
          {data.kill_switch && (
            <div role="alert" className="flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-600 dark:text-red-300">
              <ShieldAlert className="h-4 w-4" /> The dream kill switch (DREAM_KILL_SWITCH) is on: no run will start.
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-lg border border-border bg-card p-4 space-y-1">
              <p className="text-xs text-muted-foreground">Health score</p>
              {last?.health_score != null ? (
                <>
                  <p className="text-3xl font-bold">{last.health_score}<span className="text-sm font-normal text-muted-foreground">/100</span></p>
                  <p className="text-[11px] text-muted-foreground">{rep?.health_label} · {last.status.replace(/_/g, " ")} · {when(last.finished_at ?? last.started_at)}</p>
                </>
              ) : (
                <p className="text-xs text-muted-foreground">No nightly run has finished yet. {data.settings.enabled ? "The first one starts in its window." : "Nightly runs are switched off for this tenant."}</p>
              )}
              <p className="text-[11px] text-muted-foreground">
                {data.settings.enabled ? `Next window: ${when(data.next_window)} (${data.settings.timezone})` : "Schedule: off"}
              </p>
            </div>
            <div className="rounded-lg border border-border bg-card p-4 space-y-2">
              <Spark label="Health" values={trend.map((t) => t.health_score)} max={100} />
              <Spark label="Canary recall %" values={trend.map((t) => (t.canary_recall == null ? null : Math.round(t.canary_recall * 100)))} max={100} />
              <Spark label="Stale cards" values={trend.map((t) => t.stale)} max={Math.max(1, ...trend.map((t) => t.stale ?? 0))} />
            </div>
            <div className="rounded-lg border border-border bg-card p-4 space-y-2">
              <p className="text-xs text-muted-foreground">Open findings: {num(data.findings.total_open)}</p>
              <div className="flex flex-wrap gap-1.5 text-[11px]">
                {(["critical", "high", "medium", "low", "info"] as DreamSeverity[]).filter((s) => sev[s]).map((s) => (
                  <span key={s} className={`rounded-full border px-2 py-0.5 ${SEV_STYLE[s]}`}>{s}: {sev[s]}</span>
                ))}
                {data.findings.total_open === 0 && <span className="text-muted-foreground">Nothing needs review.</span>}
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                <Button size="sm" variant="outline" className="h-8 text-xs gap-1" disabled={busy !== null || data.kill_switch || !data.ready} onClick={() => void run(true)}>
                  {busy === "dry" ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />} Run now (dry run)
                </Button>
                {!confirmReal ? (
                  <Button size="sm" variant="ghost" className="h-8 text-xs" disabled={busy !== null || data.kill_switch || !data.ready} onClick={() => setConfirmReal(true)}>Run for real…</Button>
                ) : (
                  <Button size="sm" className="h-8 text-xs" disabled={busy !== null} onClick={() => void run(false)}>Confirm: apply changes</Button>
                )}
              </div>
              {data.running && <p className="text-[11px] text-muted-foreground">A run is in progress (started {when(data.running.started_at)}).</p>}
            </div>
          </div>

          {rep && (
            <div className="grid gap-2 text-[11px] sm:grid-cols-2 lg:grid-cols-4" aria-label="Last run summary">
              <Stat title="Cards" lines={[`${num(rep.cards?.live_sources)} indexed, ${num(rep.cards?.stale)} stale`, `verified ${num(rep.drift?.verified)}, refreshed ${num(rep.drift?.refreshed)}, vanished ${num(rep.drift?.vanished)}`]} />
              <Stat title="Embeddings" lines={[`${num(rep.embeddings?.scanned)} scanned, ${num(rep.embeddings?.invalid)} invalid`, `canary recall@3 ${pct(rep.canary?.recall_at_3)}${rep.canary?.previous != null ? ` (was ${pct(rep.canary.previous)})` : ""}`]} />
              <Stat title="Numbers" lines={[`${num(rep.metrics?.drifted)} of ${num(rep.metrics?.checked)} facts drifted${rep.metrics?.refreshed ? "" : " (not re-run)"}`, `forecasts scored ${num(rep.forecast?.series_scored)}, degraded ${num(rep.forecast?.degraded)}`]} />
              <Stat title="Relevance" lines={[`priority up ${num(rep.relevance?.importance_up)}, down ${num(rep.relevance?.importance_down)}, cold ${num(rep.relevance?.cold)}`, `conflicts for review ${num(rep.relevance?.conflicts)}${rep.relevance?.telemetry === false ? " · no retrieval telemetry yet" : ""}`]} />
            </div>
          )}
          {rep?.errors && rep.errors.length > 0 && (
            <details className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
              <summary className="cursor-pointer text-amber-700 dark:text-amber-300"><AlertTriangle className="mr-1 inline h-3 w-3" />{rep.errors.length} error(s) in the last run</summary>
              <ul className="mt-1 space-y-0.5 text-muted-foreground">{rep.errors.slice(0, 8).map((e, i) => <li key={i}>{e}</li>)}</ul>
            </details>
          )}

          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs">
              <span className="font-medium">Findings</span>
              {(["open", "auto_applied", "all"] as const).map((f) => (
                <button key={f} type="button" onClick={() => setFilter(f)} aria-pressed={filter === f}
                  className={`rounded-full border px-2 py-0.5 ${filter === f ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"}`}>
                  {f === "open" ? "Needs review" : f === "auto_applied" ? "Fixed automatically" : "All"}
                </button>
              ))}
            </div>
            {findings.length === 0 ? (
              <p className="rounded-lg border border-border p-4 text-center text-xs text-muted-foreground">
                {last ? "No findings in this view." : "No findings yet: they appear after the first run."}
              </p>
            ) : (
              <ul className="space-y-2">
                {findings.map((f) => (
                  <li key={f.id} className="rounded-lg border border-border bg-card p-3 text-xs space-y-1.5">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0 space-y-0.5">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className={`rounded-full border px-2 py-0.5 text-[10px] ${SEV_STYLE[f.severity]}`}>{f.severity}</span>
                          <span className="font-mono text-[10px] text-muted-foreground">{f.type}</span>
                          {f.status === "proposed" && <span className="rounded-full border border-border px-2 py-0.5 text-[10px]">proposed (dry run)</span>}
                          {f.auto_applied && <span className="rounded-full border border-border px-2 py-0.5 text-[10px] text-muted-foreground">fixed automatically</span>}
                          {f.jev && <span className="rounded-full border border-border px-2 py-0.5 text-[10px]" title="External evaluator">JEV {f.jev.decision} ({Math.round(f.jev.p * 100)}%)</span>}
                          {f.occurrences > 1 && <span className="text-[10px] text-muted-foreground">seen {f.occurrences}x</span>}
                        </div>
                        <p className="font-medium">{f.title}</p>
                      </div>
                      <div className="flex shrink-0 gap-1.5">
                        {f.action?.kind && APPLICABLE.has(f.action.kind) && (
                          <Button size="sm" className="h-7 text-xs" disabled={busy === f.id} onClick={() => void resolve(f, "apply")}>
                            {busy === f.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="mr-1 h-3 w-3" />}
                            {f.auto_applied ? "Re-apply" : "Apply fix"}
                          </Button>
                        )}
                        <Button size="sm" variant="outline" className="h-7 text-xs" disabled={busy === f.id} onClick={() => void resolve(f, "accept")}>Accept</Button>
                        <Button size="sm" variant="ghost" className="h-7 text-xs" disabled={busy === f.id} onClick={() => void resolve(f, "dismiss")}>Dismiss</Button>
                      </div>
                    </div>
                    <details>
                      <summary className="cursor-pointer text-muted-foreground">Details (before / after)</summary>
                      <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted/40 p-2 text-[10px]">{JSON.stringify(f.detail, null, 2)}</pre>
                    </details>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {form && (
            <details className="rounded-lg border border-border bg-card p-3 text-xs">
              <summary className="cursor-pointer font-medium">Settings</summary>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <label className="flex items-center gap-2"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> Run every night</label>
                <label className="space-y-1">Window opens (local time)<Input type="time" value={form.window_start} onChange={(e) => setForm({ ...form, window_start: e.target.value })} /></label>
                <label className="space-y-1">Window length (hours)<Input type="number" min={0.5} max={12} step={0.5} value={form.window_hours} onChange={(e) => setForm({ ...form, window_hours: Number(e.target.value) })} /></label>
                <label className="space-y-1">Time zone<Input value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} /></label>
                <label className="space-y-1">Re-verify each card about every N nights<Input type="number" min={1} max={60} value={form.rotation_days} onChange={(e) => setForm({ ...form, rotation_days: Number(e.target.value) })} /></label>
                <label className="space-y-1">Alert when canary recall drops by<Input type="number" min={0.01} max={1} step={0.01} value={form.canary_alert_drop} onChange={(e) => setForm({ ...form, canary_alert_drop: Number(e.target.value) })} /></label>
                <div className="sm:col-span-2 space-y-2 rounded-md border border-border p-2">
                  <label className="flex items-center gap-2"><input type="checkbox" checked={form.jev_enabled} onChange={(e) => setForm({ ...form, jev_enabled: e.target.checked })} /> Let JEV adjudicate borderline items</label>
                  <p className="text-[11px] text-muted-foreground">
                    JEV is an external evaluator. Only scrubbed excerpts of non-private cards (never HR, finance, billing or compliance cards) are sent, within the cap below. It acts only at 90% or more, or 10% or less; anything in between waits here for you.
                    {data.jev && !data.jev.credentials ? " No JEV credentials are configured on the server, so nothing will be sent." : ""}
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="space-y-1">Max JEV calls per night<Input type="number" min={0} max={200} value={form.jev_max_calls} onChange={(e) => setForm({ ...form, jev_max_calls: Number(e.target.value) })} /></label>
                    <label className="space-y-1">Max JEV cost per night (USD)<Input type="number" min={0} max={20} step={0.05} value={form.jev_max_cost_usd} onChange={(e) => setForm({ ...form, jev_max_cost_usd: Number(e.target.value) })} /></label>
                  </div>
                </div>
              </div>
              <Button size="sm" className="mt-3 h-8 text-xs gap-1" disabled={saving} onClick={() => void save()}>
                {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />} Save settings
              </Button>
            </details>
          )}
        </>
      )}
    </section>
  )
}

function Stat({ title, lines }: { title: string; lines: string[] }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <p className="font-medium text-xs">{title}</p>
      {lines.map((l, i) => <p key={i} className="text-muted-foreground">{l}</p>)}
    </div>
  )
}
