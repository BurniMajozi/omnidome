"use client"

import { useState } from "react"
import { Check, HelpCircle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { submitAgentAnswer } from "@/lib/agent-activity-api"
import {
  allAnswered, answerSummary, buildAnswerPayload, formatCountdown, MAX_OTHER, secondsUntil,
  type AgentQuestion, type AnswerDraft,
} from "@/lib/agent-activity"
import { useNow } from "./use-now"

/** Inline "the agent is asking you" card. One Submit for all stacked questions. */
export function QuestionCard({ question, streaming }: { question: AgentQuestion; streaming: boolean }) {
  const [drafts, setDrafts] = useState<AnswerDraft[]>(() => question.questions.map(() => ({ selected: [], other: "" })))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [sent, setSent] = useState(false)

  const secs = secondsUntil(question.expires_at, useNow(!sent && !question.status && streaming))
  const expired = secs !== null && secs <= 0
  const resolved = question.status && question.status !== "answered" ? question.status : ""
  const answered = sent || question.status === "answered"
  const closed = answered || !!resolved || expired || !streaming
  const valid = allAnswered(question, drafts)
  const id = `q-${question.question_id}`

  function update(i: number, fn: (d: AnswerDraft) => AnswerDraft) {
    setDrafts((prev) => prev.map((d, n) => (n === i ? fn(d) : d)))
  }

  async function submit() {
    if (!valid || busy || closed) return
    setBusy(true)
    setError("")
    const res = await submitAgentAnswer(question.run_id, buildAnswerPayload(question, drafts))
    if (res.ok) setSent(true)
    else {
      setError(res.message)
      if (res.status === 409) setSent(true) // already answered elsewhere: stop offering the form
    }
    setBusy(false)
  }

  const closedReason = answered ? "" : resolved === "cancelled" ? "This question was cancelled." : resolved === "expired" || expired ? "This question expired." : !streaming ? "The run ended before this was answered." : ""

  return (
    <section
      aria-labelledby={`${id}-title`}
      data-agent-question
      className={cn("rounded-md border bg-card/80 p-3 text-sm", closed ? "border-border" : "border-primary/40")}
    >
      <div className="mb-2 flex items-center gap-2">
        <HelpCircle className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <h3 id={`${id}-title`} className="flex-1 text-xs font-semibold text-foreground">{answered ? "Answered" : "The agent needs your input"}</h3>
        {!closed && secs !== null && <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">{formatCountdown(secs)}</span>}
      </div>

      {answered ? (
        <ul className="space-y-1 text-xs text-muted-foreground">
          {answerSummary(question, drafts).map((line, i) => (
            <li key={i} className="flex items-start gap-1.5"><Check className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" aria-hidden="true" /><span className="break-words">{line}</span></li>
          ))}
        </ul>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); void submit() }} className="space-y-3">
          {question.questions.map((q, i) => (
            <fieldset key={i} disabled={closed || busy} className="min-w-0 space-y-1.5">
              <legend className="mb-1 flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
                {q.header && <span className="rounded-full border border-border bg-secondary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{q.header}</span>}
                <span className="break-words">{q.question}</span>
              </legend>
              {q.options.map((o) => {
                const checked = drafts[i].selected.includes(o.label)
                return (
                  <label key={o.label} className={cn(
                    "flex cursor-pointer items-start gap-2 rounded-md border p-2 text-xs transition-colors motion-reduce:transition-none focus-within:ring-2 focus-within:ring-primary/60",
                    checked ? "border-primary bg-primary/10" : "border-border hover:bg-secondary/60",
                    (closed || busy) && "cursor-not-allowed opacity-60",
                  )}>
                    <input
                      type={q.multi_select ? "checkbox" : "radio"}
                      name={`${id}-${i}`}
                      checked={checked}
                      onChange={(e) => update(i, (d) => ({
                        ...d,
                        selected: q.multi_select ? (e.target.checked ? [...d.selected, o.label] : d.selected.filter((x) => x !== o.label)) : [o.label],
                      }))}
                      className="mt-0.5 accent-[hsl(var(--primary))]"
                    />
                    <span className="min-w-0">
                      <span className="block break-words font-semibold text-foreground">{o.label}</span>
                      {o.description && <span className="block break-words text-muted-foreground">{o.description}</span>}
                    </span>
                  </label>
                )
              })}
              <label className="block text-xs text-muted-foreground">
                Other
                <input
                  type="text"
                  maxLength={MAX_OTHER}
                  value={drafts[i].other}
                  placeholder="Or type your own answer"
                  onChange={(e) => update(i, (d) => ({ ...d, other: e.target.value }))}
                  className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/60"
                />
              </label>
            </fieldset>
          ))}
          {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
          {closedReason && <p className="text-xs text-muted-foreground">{closedReason}</p>}
          {!closed && (
            <Button type="submit" size="sm" disabled={!valid || busy} className="gap-1.5">
              {busy && <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
              {busy ? "Sending…" : question.questions.length > 1 ? "Submit answers" : "Submit"}
            </Button>
          )}
        </form>
      )}
    </section>
  )
}
