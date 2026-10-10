"use client"

import { useEffect, useMemo, useState } from "react"
import { AlertTriangle, Check, Loader2, Sparkles, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { aiErrorMessage, aiNarrative, aiSlide, getAiUsage, type DeckDoc, type NarrativeResult, type Slide, type SlideAiResult } from "@/lib/bi-studio-api"
import { ErrorNote } from "../shared"
import { KnowledgeChips, KnowledgeToggle } from "./knowledge-ui"
import { Section, textareaCls } from "./ui"
import { replaceSlide } from "./doc-ops"
import { SlideRenderer } from "./slide-renderer"
import { useDeckData, type QState } from "./use-deck-data"
import type { DataMap } from "./tokens"
import type { Theme } from "./theme"

const EXAMPLES = ["Make this a stacked column by month", "Rewrite for a CFO in two bullets", "Add a KPI for the latest period", "Simplify: fewer words, one clear takeaway"]

export function AiPanel({
  deckId,
  doc,
  slide,
  slideIndex,
  readOnly,
  theme,
  states,
  data,
  getVersion,
  saveNow,
  onAcceptDoc,
  onSetNotes,
  onAddTakeaways,
}: {
  deckId: string
  doc: DeckDoc
  slide: Slide
  slideIndex: number
  readOnly: boolean
  theme: Theme
  states: Record<string, QState>
  data: DataMap
  getVersion: () => number
  saveNow: () => Promise<boolean>
  onAcceptDoc: (d: DeckDoc) => void
  onSetNotes: (notes: string) => void
  onAddTakeaways: (items: string[]) => void
}) {
  const [instruction, setInstruction] = useState("")
  const [useKnowledge, setUseKnowledge] = useState(true)
  const [busy, setBusy] = useState<"slide" | "narr" | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<SlideAiResult | null>(null)
  const [narr, setNarr] = useState<NarrativeResult | null>(null)
  const [usage, setUsage] = useState<{ used: number; cap: number; remaining: number } | null>(null)

  useEffect(() => {
    setResult(null)
    setNarr(null)
    setError(null)
  }, [slide.id])
  const loadUsage = () =>
    getAiUsage()
      .then((r) => setUsage(r.ai_calls_today))
      .catch(() => {})
  useEffect(() => {
    void loadUsage()
  }, [])

  async function runSlide() {
    if (!instruction.trim()) return
    setBusy("slide")
    setError(null)
    setResult(null)
    try {
      // The server edits the saved version, so make sure it is current first.
      if (!(await saveNow())) throw new Error("Save your changes first (autosave failed).")
      const r = await aiSlide({ deck_id: deckId, slide_id: slide.id, instruction: instruction.trim(), include_doc: true, use_knowledge: useKnowledge })
      setResult(r)
      void loadUsage()
    } catch (e) {
      setError(aiErrorMessage(e))
    } finally {
      setBusy(null)
    }
  }
  async function runNarrative() {
    setBusy("narr")
    setError(null)
    setNarr(null)
    try {
      if (!(await saveNow())) throw new Error("Save your changes first (autosave failed).")
      setNarr(await aiNarrative({ deck_id: deckId, slide_id: slide.id, use_knowledge: useKnowledge }))
      void loadUsage()
    } catch (e) {
      setError(aiErrorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  const proposedDoc: DeckDoc | null = useMemo(() => {
    if (!result) return null
    return result.doc_after ?? replaceSlide(doc, result.slide)
  }, [result, doc])
  const stale = result ? result.base_version !== getVersion() : false

  return (
    <div>
      <Section title="Edit this slide with AI">
        <label htmlFor="ai-ins" className="sr-only">
          Instruction for this slide
        </label>
        <textarea id="ai-ins" className={textareaCls} rows={3} maxLength={600} disabled={readOnly || busy !== null} placeholder="e.g. make this a stacked column by month" value={instruction} onChange={(e) => setInstruction(e.target.value)} />
        <div className="flex flex-wrap gap-1">
          {EXAMPLES.map((x) => (
            <button key={x} type="button" disabled={readOnly} className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:border-primary/50 hover:text-foreground" onClick={() => setInstruction(x)}>
              {x}
            </button>
          ))}
        </div>
        <KnowledgeToggle id="ai-knowledge" checked={useKnowledge} onChange={setUseKnowledge} disabled={readOnly || busy !== null} />
        <Button size="sm" className="h-8 w-full" disabled={readOnly || busy !== null || !instruction.trim()} onClick={runSlide}>
          {busy === "slide" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {busy === "slide" ? "Thinking (up to a minute)…" : "Propose a change"}
        </Button>
        <p className="text-[11px] text-muted-foreground">Nothing changes until you accept. Numbers are written as data references, never typed by the AI.</p>
        {usage && (
          <p className="text-[11px] text-muted-foreground">
            AI calls today: {usage.used} / {usage.cap}
          </p>
        )}
        <ErrorNote message={error} />
      </Section>

      {result && proposedDoc && (
        <Section title="Proposed change">
          <AiPreview before={slide} beforeIndex={slideIndex} proposedDoc={proposedDoc} slideId={slide.id} theme={theme} states={states} data={data} />
          {stale && (
            <p className="flex gap-1 text-[11px] text-amber-300">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> The deck was saved again after this proposal was made. Accepting could overwrite newer edits; consider regenerating.
            </p>
          )}
          {result.ungrounded_numbers.length > 0 && (
            <p className="flex gap-1 text-[11px] text-amber-300">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> {result.ungrounded_numbers.length} figure(s) written outside a data reference were replaced with “[add figure]”.
            </p>
          )}
          <KnowledgeChips meta={result} />
          {result.dropped.length > 0 && (
            <ul className="list-disc pl-4 text-[11px] text-muted-foreground">
              {result.dropped.map((d, i) => (
                <li key={i}>
                  Left out {String(d.alias ?? d.id ?? "item")}: {String(d.reason ?? "invalid")}
                </li>
              ))}
            </ul>
          )}
          <div className="flex gap-2">
            <Button
              size="sm"
              className="h-8 flex-1"
              onClick={() => {
                onAcceptDoc(proposedDoc)
                setResult(null)
                setInstruction("")
              }}
            >
              <Check className="h-4 w-4" /> Accept
            </Button>
            <Button size="sm" variant="outline" className="h-8 flex-1" onClick={() => setResult(null)}>
              <X className="h-4 w-4" /> Reject
            </Button>
          </div>
        </Section>
      )}

      <Section title="Insights and notes">
        <Button size="sm" variant="outline" className="h-8 w-full" disabled={readOnly || busy !== null} onClick={runNarrative}>
          {busy === "narr" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          Generate insights and notes
        </Button>
        <p className="text-[11px] text-muted-foreground">Period changes, shares and trends are computed from the data; the AI only phrases them.</p>
        {narr && (
          <div className="space-y-2 text-xs">
            {!narr.llm_used && <p className="text-muted-foreground">AI wording was unavailable; these are the plain computed sentences.</p>}
            {narr.insights.length === 0 && <p className="text-muted-foreground">No insights: this slide has no data-backed blocks.</p>}
            <ul className="list-disc space-y-1 pl-4">
              {narr.insights.map((i, k) => (
                <li key={k}>{i.sentence_resolved}</li>
              ))}
            </ul>
            {narr.takeaways_resolved.length > 0 && (
              <div>
                <div className="font-semibold text-foreground">Takeaways</div>
                <ul className="list-disc space-y-1 pl-4">
                  {narr.takeaways_resolved.map((t, k) => (
                    <li key={k}>{t}</li>
                  ))}
                </ul>
              </div>
            )}
            {narr.notes_resolved && (
              <div>
                <div className="font-semibold text-foreground">Speaker notes</div>
                <p className="whitespace-pre-wrap text-muted-foreground">{narr.notes_resolved}</p>
              </div>
            )}
            <KnowledgeChips meta={narr} />
            {narr.ungrounded_numbers.length > 0 && (
              <p className="flex gap-1 text-[11px] text-amber-300">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> Some figures lacked a data reference and were replaced with placeholders.
              </p>
            )}
            <div className="flex flex-wrap gap-1">
              {narr.notes && (
                <Button size="sm" className="h-7 text-xs" disabled={readOnly} onClick={() => onSetNotes(narr.notes)}>
                  Use as speaker notes
                </Button>
              )}
              {narr.takeaways.length > 0 && (
                <Button size="sm" variant="outline" className="h-7 text-xs" disabled={readOnly} onClick={() => onAddTakeaways(narr.takeaways)}>
                  Add takeaways to slide
                </Button>
              )}
            </div>
          </div>
        )}
      </Section>
    </div>
  )
}

function AiPreview({ before, beforeIndex, proposedDoc, slideId, theme, states, data }: { before: Slide; beforeIndex: number; proposedDoc: DeckDoc; slideId: string; theme: Theme; states: Record<string, QState>; data: DataMap }) {
  const after = proposedDoc.slides.find((s) => s.id === slideId) ?? proposedDoc.slides[beforeIndex]
  const d = useDeckData(proposedDoc)
  return (
    <div className="space-y-2">
      <div>
        <div className="mb-0.5 text-[10px] font-semibold uppercase text-muted-foreground">Before</div>
        <div className="overflow-hidden rounded border border-border">
          <SlideRenderer slide={before} index={beforeIndex} total={proposedDoc.slides.length} theme={theme} states={states} data={data} mode="thumb" />
        </div>
      </div>
      <div>
        <div className="mb-0.5 text-[10px] font-semibold uppercase text-primary">After</div>
        <div className="overflow-hidden rounded border border-primary/60">
          {after ? <SlideRenderer slide={after} index={beforeIndex} total={proposedDoc.slides.length} theme={theme} states={d.states} data={d.data} mode="thumb" /> : <p className="p-3 text-xs text-muted-foreground">The slide was removed.</p>}
        </div>
      </div>
    </div>
  )
}
