"use client"

/**
 * <InsightsCard module="sales" /> : the one AI briefing widget for every panel (docs/insights-and-jev.md).
 *
 * Summary + recommendations come from the orchestrator's insights engine: personalised to the signed-in person, grounded
 * in cited company knowledge and governed metric facts. Numbers are never typed by a model. A recommendation only ever
 * DRAFTS an action (a link into the panel, a prompt for an agent, or a task the person confirms).
 *
 * <InsightsSummary> and <InsightsRecommendations> render the two halves separately for panels that already have a
 * "Summary" tab and a "Recommendations" column; they share one request through the hook's store.
 */

import Link from "next/link"
import { useState, type ReactNode } from "react"
import {
  AlertTriangle, Bot, Check, ChevronDown, ClipboardList, ExternalLink, Info, RefreshCw, ShieldCheck, Sparkles,
  ThumbsDown, ThumbsUp, X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  useInsights, type InsightEvidence, type InsightRecommendation, type InsightVerdict, type PanelInsights, type UseInsights,
} from "@/lib/insights-api"

const AGENT_FOR: Record<string, string> = {
  retention: "retention", support: "support", billing: "billing", sales: "sales", hr: "talent",
  call_center: "call_center", analytics: "analytics", products: "products",
}

function fmtDate(iso?: string | null): string {
  if (!iso) return "unknown date"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? "unknown date" : d.toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" })
}

const LEVEL_STYLE: Record<string, string> = {
  high: "border-red-500/30 bg-red-500/10 text-red-400",
  medium: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  low: "border-border bg-secondary/40 text-muted-foreground",
}

function Pill({ children, className, title }: { children: ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold", className)}>
      {children}
    </span>
  )
}

export function InsightsSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Preparing your briefing">
      <div className="h-4 w-4/5 animate-pulse rounded bg-muted" />
      <div className="h-4 w-3/5 animate-pulse rounded bg-muted" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-16 animate-pulse rounded-lg bg-muted/60" />
      ))}
    </div>
  )
}

function Notice({ tone, children }: { tone: "amber" | "muted"; children: ReactNode }) {
  return (
    <p
      className={cn(
        "flex items-start gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] leading-snug",
        tone === "amber" ? "border-amber-500/30 bg-amber-500/10 text-amber-300" : "border-border bg-secondary/30 text-muted-foreground",
      )}
    >
      <Info className="mt-0.5 h-3 w-3 shrink-0" />
      <span>{children}</span>
    </p>
  )
}

function VerifiedBadge({ doc }: { doc: PanelInsights }) {
  if (doc.source !== "llm") return <Pill className="border-border bg-secondary/40 text-muted-foreground" title="Built from rules over your data, no AI model">Rules-based</Pill>
  if (doc.verified) {
    const p = doc.verification.probability
    return (
      <Pill className="border-emerald-500/30 bg-emerald-500/10 text-emerald-400" title={p ? `Independent check agreed with your data (${Math.round(p * 100)}%)` : undefined}>
        <ShieldCheck className="mr-1 h-3 w-3" />Checked against your data
      </Pill>
    )
  }
  return (
    <Pill className="border-border bg-secondary/40 text-muted-foreground" title="The independent check was not available, so this was only validated by built-in rules">
      Not independently checked
    </Pill>
  )
}

function Header({ title, doc, api, extra }: { title: string; doc: PanelInsights | null; api: UseInsights; extra?: ReactNode }) {
  const { state, refresh } = api
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/20 text-primary"><Sparkles className="h-4 w-4" /></div>
      <h3 className="text-sm font-bold text-foreground">{title}</h3>
      {doc && !doc.empty && <VerifiedBadge doc={doc} />}
      <span className="ml-auto flex items-center gap-2">
        {doc && !doc.empty && <span className="text-[11px] text-muted-foreground">Data as of {fmtDate(doc.as_of ?? doc.generated_at)}</span>}
        {extra}
        <Button variant="ghost" size="icon-sm" onClick={refresh} disabled={state.status === "loading" || state.refreshing} aria-label="Refresh briefing" title="Refresh briefing">
          <RefreshCw className={cn("h-3.5 w-3.5", (state.status === "loading" || state.refreshing) && "animate-spin")} />
        </Button>
      </span>
    </div>
  )
}

function Notices({ doc, error }: { doc: PanelInsights; error: string | null }) {
  return (
    <div className="space-y-1.5">
      {doc.degraded && <Notice tone="amber">Showing a simpler, rules-based briefing: {doc.degraded}.</Notice>}
      {doc.stale && !doc.degraded && <Notice tone="amber">Some of the data behind this briefing may be out of date{doc.refreshing ? "; refreshing now" : ""}.</Notice>}
      {doc.notice && <Notice tone="muted">{doc.notice}</Notice>}
      {error && <Notice tone="muted">Could not refresh just now ({error}). Showing the last briefing.</Notice>}
    </div>
  )
}

function EvidenceChip({ e }: { e: InsightEvidence }) {
  const label = e.kind === "fact" ? `${e.title}` : e.kind === "personal" ? e.title : e.title
  const inner = (
    <>
      <span className="max-w-[16rem] truncate">{label}</span>
      <span className="text-muted-foreground/70">· {fmtDate(e.as_of)}</span>
      {e.stale && <span className="text-amber-400">· older</span>}
      {e.deep_link && <ExternalLink className="h-3 w-3 shrink-0" />}
    </>
  )
  const cls = "inline-flex items-center gap-1 rounded-md border border-border bg-background/60 px-1.5 py-0.5 text-[10px] text-muted-foreground"
  return e.deep_link ? (
    <Link href={e.deep_link} className={cn(cls, "hover:border-primary/50 hover:text-foreground")} title={`${e.kind}: open the source`}>{inner}</Link>
  ) : (
    <span className={cls} title={e.kind}>{inner}</span>
  )
}

function RecItem({ rec, doc, api }: { rec: InsightRecommendation; doc: PanelInsights; api: UseInsights }) {
  const [why, setWhy] = useState(false)
  const [confirmTask, setConfirmTask] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [voted, setVoted] = useState<InsightVerdict | null>(null)
  const act = rec.suggested_action

  const vote = async (v: InsightVerdict) => {
    setVoted(v)
    const ok = await api.feedback(v, rec.id)
    if (!ok) { setVoted(null); setMsg("Your feedback could not be saved. Try again.") }
  }
  const askAgent = () => {
    const prompt =
      `Help me act on this recommendation from the ${doc.label} panel: "${rec.title}". Why: ${rec.why} ` +
      `Evidence: ${rec.evidence.map((e) => e.title).join("; ")}. Draft a plan for me to review; do not change anything until I confirm.`
    window.dispatchEvent(new CustomEvent("open-agent-chat", { detail: { agent: AGENT_FOR[doc.module] ?? "executive", prompt, draft: prompt } }))
    void api.feedback("acted", rec.id)
  }
  const createTask = async () => {
    setConfirmTask(false)
    setMsg("Creating task…")
    try {
      const res = await fetch("/api/chat/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: `[AI Action] ${act.draft ?? rec.title}`, description: rec.why, priority: rec.priority === "high" ? "high" : "normal", status: "todo" }),
      })
      setMsg(res.ok ? "Task created." : `Could not create the task (${res.status}).`)
      if (res.ok) void api.feedback("acted", rec.id)
    } catch {
      setMsg("Could not reach the task service.")
    }
  }

  return (
    <li className="rounded-lg border border-border bg-secondary/20 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 flex-1 text-sm font-semibold text-foreground">{rec.title}</p>
        <div className="flex shrink-0 items-center gap-1">
          <Pill className={LEVEL_STYLE[rec.priority]}>{rec.priority} priority</Pill>
          <Pill
            className={rec.impact === "high" ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
              : rec.impact === "medium" ? "border-blue-500/30 bg-blue-500/10 text-blue-400" : LEVEL_STYLE.low}
            title="Expected impact"
          >{rec.impact} impact</Pill>
          <Pill className="border-border bg-secondary/40 text-muted-foreground" title="Effort to act on this">{rec.effort} effort</Pill>
        </div>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{rec.why}</p>
      {rec.owner_hint && <p className="mt-1 text-[11px] text-muted-foreground">Suggested owner: {rec.owner_hint}</p>}

      <button type="button" onClick={() => setWhy((v) => !v)} aria-expanded={why}
        className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline">
        <ChevronDown className={cn("h-3 w-3 transition-transform", why && "rotate-180")} />
        Why this? {rec.evidence.length} source{rec.evidence.length === 1 ? "" : "s"}
      </button>
      {why && (
        <div className="mt-2 space-y-1.5 rounded-md border border-border bg-background/50 p-2">
          <p className="text-[11px] text-muted-foreground">Built from these records. Figures are the platform's own values; open a source to check it.</p>
          <div className="flex flex-wrap gap-1.5">{rec.evidence.map((e) => <EvidenceChip key={e.id} e={e} />)}</div>
          <p className="text-[10px] text-muted-foreground">Confidence {Math.round(rec.confidence * 100)}%. This is a suggestion; nothing has been changed.</p>
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {act.link && (
          <Button asChild size="sm" variant="outline" className="h-7 gap-1 text-[11px]"><Link href={act.link}><ExternalLink className="h-3 w-3" />{act.label || "Open"}</Link></Button>
        )}
        <Button size="sm" variant="outline" className="h-7 gap-1 text-[11px]" onClick={askAgent}><Bot className="h-3 w-3" />Ask an agent</Button>
        {act.kind === "draft_task" && !confirmTask && (
          <Button size="sm" variant="outline" className="h-7 gap-1 text-[11px]" onClick={() => setConfirmTask(true)}><ClipboardList className="h-3 w-3" />Draft task</Button>
        )}
        {confirmTask && (
          <span className="flex items-center gap-1 rounded-md border border-primary/40 bg-primary/5 px-2 py-1 text-[11px]">
            Create task "{(act.draft ?? rec.title).slice(0, 50)}"?
            <Button size="sm" className="h-6 px-2 text-[11px]" onClick={createTask}>Create</Button>
            <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={() => setConfirmTask(false)}>Cancel</Button>
          </span>
        )}
        <span className="ml-auto flex items-center gap-0.5">
          <Button size="icon-sm" variant="ghost" aria-label="Helpful" title="Helpful" disabled={!!voted} onClick={() => vote("helpful")}>
            <ThumbsUp className={cn("h-3.5 w-3.5", voted === "helpful" && "text-emerald-400")} />
          </Button>
          <Button size="icon-sm" variant="ghost" aria-label="Not helpful" title="Not helpful (hides it)" disabled={!!voted} onClick={() => vote("not_helpful")}>
            <ThumbsDown className="h-3.5 w-3.5" />
          </Button>
          <Button size="icon-sm" variant="ghost" aria-label="Dismiss" title="Dismiss" disabled={!!voted} onClick={() => vote("dismissed")}>
            <X className="h-3.5 w-3.5" />
          </Button>
          <Button size="icon-sm" variant="ghost" aria-label="I did this" title="I acted on this" disabled={!!voted} onClick={() => vote("acted")}>
            <Check className={cn("h-3.5 w-3.5", voted === "acted" && "text-emerald-400")} />
          </Button>
        </span>
      </div>
      {msg && <p className="mt-1.5 text-[11px] text-muted-foreground" role="status">{msg}</p>}
    </li>
  )
}

function Kpis({ doc }: { doc: PanelInsights }) {
  if (!doc.kpis.length) return null
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {doc.kpis.slice(0, 6).map((k) => (
        <div key={k.id} className="rounded-lg border border-border bg-background/50 px-2.5 py-2">
          <p className="truncate text-[10px] uppercase tracking-wide text-muted-foreground" title={k.label}>{k.label}</p>
          <p className="text-sm font-bold text-foreground">{k.value}{k.kind === "forecast" && <span className="ml-1 text-[10px] font-normal text-muted-foreground">forecast</span>}</p>
          {k.delta && <p className="text-[10px] text-muted-foreground">{k.delta}</p>}
        </div>
      ))}
    </div>
  )
}

function StateBody({ api, module, label, fallback, children }: {
  api: UseInsights; module: string; label: string; fallback?: ReactNode; children: (doc: PanelInsights) => ReactNode
}) {
  const { state } = api
  if (state.status === "idle" || (state.status === "loading" && !state.data)) return <InsightsSkeleton />
  if (state.status === "denied") {
    return (
      <p className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
        You do not have access to the {label} panel, so there is no briefing for it.
        {state.allowed.length > 0 && ` You can open: ${state.allowed.join(", ")}.`}
      </p>
    )
  }
  if (state.status === "error" || !state.data) {
    return (
      <div className="space-y-2">
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
          <span>The AI briefing is unavailable right now{state.error ? ` (${state.error})` : ""}.</span>
          <Button variant="outline" size="sm" className="ml-auto h-6 text-[11px]" onClick={api.refresh}>Retry</Button>
        </p>
        {fallback}
      </div>
    )
  }
  if (state.data.empty) {
    return (
      <div className="space-y-2">
        <p className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">{state.data.empty_reason ?? "Not enough data yet."}</p>
        {fallback}
      </div>
    )
  }
  return <>{children(state.data)}</>
}

function visible(doc: PanelInsights, hidden: string[]) {
  return doc.recommendations.filter((r) => !hidden.includes(r.id))
}

export function InsightsSummary({ module, scope, title, fallback }: { module: string; scope?: string; title?: string; fallback?: ReactNode }) {
  const api = useInsights(module, { scope })
  return (
    <div className="space-y-3">
      <StateBody api={api} module={module} label={title ?? module} fallback={fallback}>
        {(doc) => (
          <>
            <div className="flex flex-wrap items-center gap-2"><VerifiedBadge doc={doc} /><span className="text-[11px] text-muted-foreground">Data as of {fmtDate(doc.as_of ?? doc.generated_at)}</span></div>
            <Notices doc={doc} error={api.state.error} />
            <p className="text-sm leading-relaxed text-muted-foreground">{doc.summary}</p>
            <Kpis doc={doc} />
            {doc.risks.length > 0 && (
              <ul className="space-y-1">
                {doc.risks.map((r, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-xs text-muted-foreground"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-400" />{r.text}</li>
                ))}
              </ul>
            )}
          </>
        )}
      </StateBody>
    </div>
  )
}

export function InsightsRecommendations({ module, scope, title, fallback }: { module: string; scope?: string; title?: string; fallback?: ReactNode }) {
  const api = useInsights(module, { scope })
  return (
    <div className="space-y-3">
      <StateBody api={api} module={module} label={title ?? module} fallback={fallback}>
        {(doc) => {
          const recs = visible(doc, api.state.hidden)
          return (
            <>
              <Notices doc={doc} error={api.state.error} />
              {recs.length === 0 ? (
                <p className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
                  Nothing to recommend right now. That is not an error: the data does not call for action.
                </p>
              ) : (
                <ul className="space-y-2.5">{recs.map((r) => <RecItem key={r.id} rec={r} doc={doc} api={api} />)}</ul>
              )}
            </>
          )
        }}
      </StateBody>
    </div>
  )
}

export function InsightsCard({ module, title, scope, className, fallback }: {
  module: string; title?: string; scope?: string; className?: string; fallback?: ReactNode
}) {
  const api = useInsights(module, { scope })
  const heading = title ?? (module === "overview" ? "Executive overview" : "AI briefing")
  return (
    <section className={cn("space-y-3 rounded-xl border border-primary/30 bg-gradient-to-r from-primary/10 via-background to-secondary/30 p-4 shadow-sm", className)}
      aria-label={heading}>
      <Header title={heading} doc={api.state.data} api={api} />
      <StateBody api={api} module={module} label={title ?? module} fallback={fallback}>
        {(doc) => {
          const recs = visible(doc, api.state.hidden)
          return (
            <>
              <Notices doc={doc} error={api.state.error} />
              <p className="text-xs font-medium leading-relaxed text-foreground/90">{doc.summary}</p>
              <Kpis doc={doc} />
              {recs.length > 0 && (
                <div className="space-y-2 border-t border-border/60 pt-3">
                  <p className="text-xs font-semibold uppercase tracking-wider text-foreground">Recommended for you</p>
                  <ul className="space-y-2.5">{recs.map((r) => <RecItem key={r.id} rec={r} doc={doc} api={api} />)}</ul>
                </div>
              )}
              {doc.used_skills.length > 0 && <p className="text-[10px] text-muted-foreground">Playbooks used: {doc.used_skills.join(", ")}</p>}
            </>
          )
        }}
      </StateBody>
    </section>
  )
}
