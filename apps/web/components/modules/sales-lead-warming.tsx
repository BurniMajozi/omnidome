"use client"

/**
 * Sales → AI Lead Warming: the three event triggers as real orchestrator
 * workflows (SPEC-lead-automations.md). Shows whether each rule is installed and
 * active, its runs in the last 7 days and the last run; can install, pause and
 * send a clearly-labelled test event.
 */
import { useCallback, useEffect, useState } from "react"
import { FileText, Globe, Loader2, Play, ShoppingCart, Zap } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { formatDateTime } from "./sales-leads-tab"

type RuleStatus = {
  key: "abandoned_basket" | "quote_request" | "registration_inactive"
  name: string
  trigger_event: string
  description: string
  installed: boolean
  workflow_id: string | null
  status: string | null
  runs_7d: number
  succeeded_7d: number
  last_run: { id: string; status: string; error: string | null; started_at: string | null; lead_id: string | null } | null
}

const ORCH = "/api/orchestrator"

async function orch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${ORCH}${path}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => "")
    let detail = text
    try { detail = JSON.parse(text)?.detail ?? text } catch { /* not JSON */ }
    throw new Error(detail || `Orchestrator error ${res.status}`)
  }
  return res.json()
}

const CARD: Record<RuleStatus["key"], {
  title: string; icon: React.ReactNode; tone: string; when: string; stage: string; ai: string
  sample: Record<string, unknown>
}> = {
  abandoned_basket: {
    title: "Abandoned basket",
    icon: <ShoppingCart className="h-4 w-4 text-cyan-400" />,
    tone: "text-cyan-400",
    when: "Customer placed an internet package in the portal basket but left without paying (> 2 hrs).",
    stage: "New → Contacted",
    ai: "DomeBot drafts a recovery message with voucher FIBERWARM15 and a free installation waiver.",
    sample: { cart_summary: "Fibre 100 Mbps Uncapped", cart_total_zar: 899 },
  },
  quote_request: {
    title: "Instant quotation request",
    icon: <FileText className="h-4 w-4 text-purple-400" />,
    tone: "text-purple-400",
    when: "Customer requested pricing on the website calculator or by email.",
    stage: "New → Proposal (on the pipeline board, at the quoted value)",
    ai: "DomeBot drafts the quote cover note and offers a follow-up call.",
    sample: { quote_summary: "Business Fibre 200 Mbps + static IP", quote_total_zar: 2499 },
  },
  registration_inactive: {
    title: "Online registration inactive",
    icon: <Globe className="h-4 w-4 text-amber-400" />,
    tone: "text-amber-400",
    when: "User registered on the self-service portal but took no action (> 24 hrs).",
    stage: "New → Qualified",
    ai: "The concierge drafts a friendly check-in offering an address coverage check.",
    sample: { registered_at: new Date(Date.now() - 86_400_000).toISOString().slice(0, 10) },
  },
}

function RunLine({ rule }: { rule: RuleStatus }) {
  const last = rule.last_run
  if (!rule.installed) return <span className="text-muted-foreground">Not installed</span>
  return (
    <span className="text-muted-foreground">
      {rule.runs_7d} run{rule.runs_7d === 1 ? "" : "s"} in 7 days · {rule.succeeded_7d} succeeded
      {last && (
        <>
          <br />
          Last: <span className={last.status === "succeeded" ? "text-emerald-400" : last.status === "failed" ? "text-red-400" : "text-foreground"}>
            {last.status}
          </span>
          {last.started_at ? ` · ${formatDateTime(last.started_at)}` : ""}
          {last.status === "failed" && last.error ? <><br /><span className="text-red-400/90">{last.error}</span></> : null}
        </>
      )}
    </span>
  )
}

export function LeadWarmingRules() {
  const [rules, setRules] = useState<RuleStatus[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<Record<string, string>>({})
  const [showIntegration, setShowIntegration] = useState(false)

  const load = useCallback(async () => {
    try {
      const body = await orch<{ data: RuleStatus[] }>("/workflows/templates/lead-warming")
      setRules(body.data)
      setError(null)
      return body.data
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the automations")
      return null
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    orch<{ data: RuleStatus[] }>("/workflows/templates/lead-warming")
      .then((b) => { if (!cancelled) setRules(b.data) })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : "Could not load the automations") })
    return () => { cancelled = true }
  }, [])

  const install = async () => {
    setBusy("install")
    try {
      const body = await orch<{ data: RuleStatus[] }>("/workflows/templates/lead-warming", { method: "POST" })
      setRules(body.data)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Install failed")
    } finally {
      setBusy(null)
    }
  }

  const setActive = async (rule: RuleStatus, active: boolean) => {
    if (!rule.workflow_id) return
    setBusy(rule.key)
    try {
      await orch(`/workflows/${rule.workflow_id}`, { method: "PUT", body: JSON.stringify({ status: active ? "active" : "paused" }) })
      await load()
    } catch (err) {
      setMessage((m) => ({ ...m, [rule.key]: err instanceof Error ? err.message : "Could not change the rule" }))
    } finally {
      setBusy(null)
    }
  }

  const sendTest = async (rule: RuleStatus) => {
    setBusy(rule.key)
    setMessage((m) => ({ ...m, [rule.key]: "Event sent — waiting for the run…" }))
    const tag = Math.random().toString(36).slice(2, 8)
    const previous = rule.last_run?.id
    try {
      await orch("/events", {
        method: "POST",
        body: JSON.stringify({
          type: rule.trigger_event,
          idempotency_key: `ui-test-${rule.key}-${tag}`,
          payload: {
            test: true,
            contact: { first_name: "Test", last_name: `${CARD[rule.key].title} (${tag})`, email: `test+${tag}@omnidome.local` },
            ...CARD[rule.key].sample,
          },
        }),
      })
      // The consumer picks the event up within seconds; the AI draft step can take
      // a minute or more on free models (one ran 62 s), so watch for 3 minutes.
      const started = Date.now()
      while (Date.now() - started < 180_000) {
        await new Promise((r) => setTimeout(r, Date.now() - started < 30_000 ? 3000 : 6000))
        const data = await load()
        const now = data?.find((r) => r.key === rule.key)?.last_run
        if (now && now.id !== previous && now.status === "running") {
          setMessage((m) => ({ ...m, [rule.key]: "Running — the AI draft can take a minute on free models…" }))
        }
        if (now && now.id !== previous && now.status !== "running") {
          setMessage((m) => ({
            ...m,
            [rule.key]: now.status === "succeeded"
              ? "Test run succeeded — the test lead and its AI draft are in Lead Stage Management."
              : `Test run ${now.status}${now.error ? `: ${now.error}` : ""}`,
          }))
          return
        }
      }
      setMessage((m) => ({ ...m, [rule.key]: "Still running — check again in a moment." }))
    } catch (err) {
      setMessage((m) => ({ ...m, [rule.key]: err instanceof Error ? err.message : "Could not send the event" }))
    } finally {
      setBusy(null)
    }
  }

  const activeCount = rules?.filter((r) => r.installed && r.status === "active").length ?? 0
  const missing = rules?.some((r) => !r.installed)

  return (
    <div className="surface-card p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
            <Zap className="h-4 w-4 text-amber-400" />
            Event triggers & stage rules
          </h4>
          <p className="text-xs text-muted-foreground">
            Each rule is a workflow in the Agentic Flow Orchestrator, started by a customer event. AI drafts are saved
            on the lead for a person to review and send.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {rules && (
            <Badge variant="outline" className={activeCount ? "border-emerald-500/30 text-emerald-400 text-xs" : "text-xs"}>
              {activeCount} of {rules.length} active
            </Badge>
          )}
          {missing && (
            <Button size="sm" className="h-8 text-xs" onClick={() => void install()} disabled={busy === "install"}>
              {busy === "install" && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              Install automations
            </Button>
          )}
        </div>
      </div>

      {error && <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {!rules && !error && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}

      {rules && (
        <div className="grid gap-3 lg:grid-cols-3">
          {rules.map((rule) => {
            const card = CARD[rule.key]
            const active = rule.installed && rule.status === "active"
            return (
              <div key={rule.key} className="rounded-xl border border-border bg-card p-4 space-y-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    {card.icon}
                    {card.title}
                  </div>
                  <Badge className={`text-[10px] ${active ? "bg-emerald-500/20 text-emerald-400" : rule.installed ? "bg-amber-500/20 text-amber-400" : "bg-muted text-muted-foreground"}`}>
                    {active ? "Active" : rule.installed ? "Paused" : "Not installed"}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">{card.when}</p>
                <div className="rounded bg-muted/40 p-2 text-[11px] space-y-1">
                  <div className="text-muted-foreground">
                    Event: <code className="text-[11px] text-foreground">{rule.trigger_event}</code>
                  </div>
                  <div className="text-muted-foreground">
                    Stage: <span className="font-semibold text-foreground">{card.stage}</span>
                  </div>
                  <div className={`${card.tone} font-medium`}>AI: {card.ai}</div>
                </div>
                <div className="text-[11px] leading-5"><RunLine rule={rule} /></div>
                {rule.last_run?.lead_id && (
                  <button
                    type="button"
                    className="text-[11px] text-primary hover:underline"
                    onClick={() => window.dispatchEvent(new CustomEvent("omnidome:open-lead", { detail: { id: rule.last_run?.lead_id } }))}
                  >
                    Open the lead from the last run
                  </button>
                )}
                {message[rule.key] && <p className="text-[11px] text-muted-foreground">{message[rule.key]}</p>}
                {rule.installed && (
                  <div className="flex flex-wrap gap-2 pt-1">
                    <Button size="sm" variant="outline" className="h-7 text-[11px] gap-1" disabled={!!busy || !active}
                      onClick={() => void sendTest(rule)} title="Creates a lead labelled Test">
                      {busy === rule.key ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
                      Send test event
                    </Button>
                    <Button size="sm" variant="ghost" className="h-7 text-[11px]" disabled={!!busy}
                      onClick={() => void setActive(rule, !active)}>
                      {active ? "Pause" : "Activate"}
                    </Button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <div className="rounded-lg border border-border/70 p-3">
        <button type="button" className="text-xs font-medium text-foreground hover:text-primary" onClick={() => setShowIntegration((v) => !v)}>
          {showIntegration ? "Hide" : "Show"} how the portal and website send these events
        </button>
        {showIntegration && (
          <div className="mt-2 space-y-2 text-[11px] text-muted-foreground">
            <p>
              Post each customer event to the orchestrator. Events are stored and retried, so a busy or restarting
              service never loses one; the same <code>idempotency_key</code> is only processed once.
            </p>
            <pre className="overflow-x-auto rounded bg-muted/50 p-2 text-[11px] text-foreground">{`POST /api/orchestrator/events
{
  "type": "portal.cart.abandoned",
  "idempotency_key": "cart-8841-2026-09-24",
  "payload": {
    "contact": { "first_name": "Thandi", "last_name": "Mokoena",
                 "email": "thandi@example.com", "phone": "+27 82 000 0000" },
    "cart_summary": "Fibre 100 Mbps Uncapped",
    "cart_total_zar": 899
  }
}`}</pre>
            <p>
              Other types: <code>portal.quote.requested</code> (quote_summary, quote_total_zar) and{" "}
              <code>portal.registration.inactive</code> (registered_at).
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
