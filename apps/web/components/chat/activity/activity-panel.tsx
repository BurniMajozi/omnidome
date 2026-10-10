"use client"

import { useState } from "react"
import { AlertCircle, Check, ChevronRight, ExternalLink, Loader2, Minus } from "lucide-react"
import { cn } from "@/lib/utils"
import { openAppPath } from "@/lib/artifact-links"
import {
  citationsFromSteps, elapsedMs, formatDuration, liveStatusText, stepDurationLabel, summaryText,
  type Activity, type ActivityStep,
} from "@/lib/agent-activity"
import { StepKindIcon } from "./step-icon"
import { useNow } from "./use-now"

function StepState({ step, live }: { step: ActivityStep; live: boolean }) {
  if (step.status === "error") return <AlertCircle className="h-3.5 w-3.5 text-destructive" aria-label="Failed" />
  if (step.status === "done") return <Check className="h-3.5 w-3.5 text-emerald-500" aria-label="Done" />
  if (live) return <Loader2 className="h-3.5 w-3.5 animate-spin text-primary motion-reduce:animate-none" aria-label="Running" />
  return <Minus className="h-3.5 w-3.5 text-muted-foreground" aria-label="Stopped" />
}

function StepRow({ step, live, now, hasOpenQuestion }: { step: ActivityStep; live: boolean; now: number; hasOpenQuestion: boolean }) {
  const [showDetails, setShowDetails] = useState(false)
  const dur = stepDurationLabel(step, now)
  const details = step.detail
  const jump = step.kind === "approval" && step.status === "running" && live && hasOpenQuestion
  return (
    <li className="flex items-start gap-2 py-1 text-xs">
      <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center text-muted-foreground"><StepKindIcon kind={step.kind} className="h-3.5 w-3.5" /></span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className={cn("font-medium text-foreground", step.status === "running" && live && "motion-safe:animate-pulse")}>{step.title}</span>
          {dur && <span className="tabular-nums text-muted-foreground">{dur}</span>}
          {jump && (
            <button
              type="button"
              className="rounded text-primary underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
              onClick={() => document.querySelector<HTMLElement>("[data-agent-question]")?.scrollIntoView({ block: "nearest", behavior: "smooth" })}
            >
              Answer below
            </button>
          )}
        </div>
        {step.result_summary && <p className="break-words text-muted-foreground">{step.result_summary}</p>}
        {details && (
          <>
            <button type="button" className="text-[11px] text-muted-foreground underline-offset-2 hover:underline" aria-expanded={showDetails} onClick={() => setShowDetails((v) => !v)}>
              {showDetails ? "Hide details" : "Details"}
            </button>
            {showDetails && <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-words rounded bg-background/60 p-1.5 text-[11px] text-muted-foreground">{details}</pre>}
          </>
        )}
      </div>
      <span className="mt-0.5 shrink-0"><StepState step={step} live={live} /></span>
    </li>
  )
}

/** Claude-Code-style live process: status line + step timeline; collapses to one summary row when the run ends. */
export function ActivityPanel({ activity, streaming }: { activity: Activity; streaming: boolean }) {
  const now = useNow(streaming)
  const [userOpen, setUserOpen] = useState<boolean | null>(null)
  const open = userOpen ?? streaming
  const hasSteps = activity.steps.length > 0
  const citations = streaming ? [] : citationsFromSteps(activity.steps)
  const openQuestion = activity.questions.some((q) => !q.status)

  // Legacy / Hermes run that already finished: nothing to summarise (existing tool chips remain).
  if (!activity.hasCustom && !streaming) return null

  const headline = streaming ? liveStatusText(activity, now) : summaryText(activity)

  const header = (
    <div className="flex w-full items-center gap-2 text-left text-xs">
      {streaming
        ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" />
        : <Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" aria-hidden="true" />}
      <span className="min-w-0 flex-1 truncate font-medium text-foreground" role={streaming ? "status" : undefined}>{headline}</span>
      {streaming && activity.hasCustom && <span className="shrink-0 tabular-nums text-muted-foreground">{formatDuration(elapsedMs(activity, now))}</span>}
      {hasSteps && <ChevronRight className={cn("h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform motion-reduce:transition-none", open && "rotate-90")} aria-hidden="true" />}
    </div>
  )

  return (
    <div className="rounded-md border border-border/70 bg-background/50 px-2.5 py-1.5" data-testid="agent-activity">
      {hasSteps ? (
        <button type="button" className="w-full rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary" aria-expanded={open} aria-controls="agent-activity-steps" onClick={() => setUserOpen(!open)}>
          {header}
        </button>
      ) : header}
      {hasSteps && (
        <div className={cn("grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none", open ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}>
          <div className="overflow-hidden" aria-hidden={!open}>
            <ol id="agent-activity-steps" className="mt-1.5 divide-y divide-border/40 border-t border-border/50 pt-1">
              {activity.steps.map((s) => <StepRow key={s.id} step={s} live={streaming} now={now} hasOpenQuestion={openQuestion} />)}
            </ol>
          </div>
        </div>
      )}
      {citations.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1" aria-label="Sources used">
          {citations.map((c) => (
            <button key={c.href} type="button" onClick={() => openAppPath(c.href)} title={c.title}
              className="inline-flex max-w-[11rem] items-center gap-1 rounded-full border border-border bg-card/80 px-2 py-0.5 text-[11px] text-foreground hover:bg-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
              <span className="truncate">{c.title}</span><ExternalLink className="h-2.5 w-2.5 shrink-0" aria-hidden="true" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
