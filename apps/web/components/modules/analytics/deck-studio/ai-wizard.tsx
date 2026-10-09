"use client"

import { useEffect, useMemo, useState } from "react"
import { ArrowDown, ArrowUp, Loader2, Sparkles, Trash2, AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  aiErrorMessage,
  aiOutline,
  createDeck,
  type DatasetDef,
  type Deck,
  type DeckDoc,
  type OutlineResult,
} from "@/lib/bi-studio-api"
import { getCompetitorOverview, listCampaignAnalyses, listResearch, type CompetitorOverviewItem, type CampaignAnalysis, type ResearchRun } from "@/lib/analytics-ai-api"
import { ErrorNote, Pill } from "../shared"
import { fieldCls, Field, Modal, textareaCls, useStudio } from "./ui"
import { moveSlide, pruneQueries, removeSlide } from "./doc-ops"
import { SlideRenderer } from "./slide-renderer"
import { mergeTheme } from "./theme"
import { useDeckData } from "./use-deck-data"
import { useBrandKit } from "./use-kit"
import { LAYOUT_LABELS } from "./layout"

const TONES = ["Professional", "Executive and concise", "Persuasive", "Friendly", "Technical", "Analytical"]

function toggle<T>(arr: T[], v: T, max?: number): T[] {
  if (arr.includes(v)) return arr.filter((x) => x !== v)
  if (max && arr.length >= max) return arr
  return [...arr, v]
}

export function AiWizard({ onClose, onCreated }: { onClose: () => void; onCreated: (deck: Deck) => void }) {
  const { catalog, kits, catalogError } = useStudio()
  const [step, setStep] = useState<"brief" | "generating" | "review">("brief")
  const [brief, setBrief] = useState("")
  const [audience, setAudience] = useState("")
  const [tone, setTone] = useState(TONES[0])
  const [count, setCount] = useState(8)
  const [datasetIds, setDatasetIds] = useState<string[]>([])
  const [dsFilter, setDsFilter] = useState("")
  const [kitId, setKitId] = useState<string>("")
  const [research, setResearch] = useState<ResearchRun[]>([])
  const [competitors, setCompetitors] = useState<CompetitorOverviewItem[]>([])
  const [campaigns, setCampaigns] = useState<CampaignAnalysis[]>([])
  const [researchIds, setResearchIds] = useState<string[]>([])
  const [competitorIds, setCompetitorIds] = useState<string[]>([])
  const [campaignIds, setCampaignIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<OutlineResult | null>(null)
  const [doc, setDoc] = useState<DeckDoc | null>(null)
  const [creating, setCreating] = useState(false)
  const [sel, setSel] = useState(0)

  useEffect(() => {
    listResearch(50)
      .then((r) => setResearch(r.items.filter((x) => x.status === "done")))
      .catch(() => {})
    getCompetitorOverview()
      .then((r) => setCompetitors(r.competitors))
      .catch(() => {})
    listCampaignAnalyses(50)
      .then((r) => setCampaigns(r.items))
      .catch(() => {})
  }, [])
  useEffect(() => {
    if (!kitId && kits.length) setKitId(kits.find((k) => k.is_default)?.id ?? kits[0].id)
  }, [kits, kitId])

  const filtered = useMemo(() => {
    const q = dsFilter.trim().toLowerCase()
    return (catalog?.datasets ?? []).filter((d) => !q || d.label.toLowerCase().includes(q) || (d.category ?? "").toLowerCase().includes(q))
  }, [catalog, dsFilter])
  const byCat = useMemo(() => {
    const m = new Map<string, DatasetDef[]>()
    for (const d of filtered) m.set(d.category ?? "Other", [...(m.get(d.category ?? "Other") ?? []), d])
    return [...m]
  }, [filtered])

  const canGo = brief.trim().length >= 10 && datasetIds.length >= 1 && step === "brief"

  async function generate() {
    setError(null)
    setStep("generating")
    try {
      const r = await aiOutline({
        brief: brief.trim(),
        audience: audience.trim() || undefined,
        tone,
        slide_count: count,
        dataset_ids: datasetIds,
        research_run_ids: researchIds.length ? researchIds : undefined,
        competitor_ids: competitorIds.length ? competitorIds : undefined,
        campaign_analysis_ids: campaignIds.length ? campaignIds : undefined,
        brand_kit_id: kitId || undefined,
      })
      setResult(r)
      setDoc(r.deck)
      setSel(0)
      setStep("review")
    } catch (e) {
      setError(aiErrorMessage(e))
      setStep("brief")
    }
  }

  async function create() {
    if (!doc) return
    setCreating(true)
    setError(null)
    try {
      const final = pruneQueries(doc)
      const deck = await createDeck({ title: final.title || "Untitled deck", doc: final, brand_kit_id: kitId || undefined })
      onCreated(deck)
    } catch (e) {
      setError(aiErrorMessage(e))
      setCreating(false)
    }
  }

  if (step === "review" && doc && result) {
    return (
      <Modal
        title="Review the proposed outline"
        wide
        onClose={onClose}
        footer={
          <>
            <Button variant="outline" size="sm" onClick={() => setStep("brief")}>
              Back to brief
            </Button>
            <Button size="sm" disabled={creating || doc.slides.length === 0} onClick={create}>
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Create deck ({doc.slides.length} slides)
            </Button>
          </>
        }
      >
        <Review result={result} doc={doc} setDoc={setDoc} sel={sel} setSel={setSel} kitId={kitId} />
        <ErrorNote message={error} className="mt-3" />
      </Modal>
    )
  }

  return (
    <Modal
      title="Generate a deck with AI"
      wide
      onClose={onClose}
      footer={
        <>
          <span className="mr-auto text-xs text-muted-foreground">Every figure comes from a query on your data; the AI only writes the words around it.</span>
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={generate} disabled={!canGo}>
            {step === "generating" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {step === "generating" ? "Generating (up to a minute)…" : "Propose outline"}
          </Button>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-3">
          <Field label="What is this deck about?" htmlFor="wz-brief" hint="At least 10 characters. Say what decision or story the deck supports.">
            <textarea id="wz-brief" className={textareaCls} rows={5} value={brief} onChange={(e) => setBrief(e.target.value)} placeholder="e.g. Q3 revenue and collections review for the executive team, highlighting overdue accounts" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Audience" htmlFor="wz-aud">
              <input id="wz-aud" className={fieldCls} value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="Board, CFO, sales team…" />
            </Field>
            <Field label="Tone" htmlFor="wz-tone">
              <select id="wz-tone" className={fieldCls} value={tone} onChange={(e) => setTone(e.target.value)}>
                {TONES.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </Field>
            <Field label="Slides (2-20)" htmlFor="wz-count">
              <input id="wz-count" type="number" min={2} max={20} className={fieldCls} value={count} onChange={(e) => setCount(Math.max(2, Math.min(20, Number(e.target.value) || 2)))} />
            </Field>
            <Field label="Brand kit" htmlFor="wz-kit">
              <select id="wz-kit" className={fieldCls} value={kitId} onChange={(e) => setKitId(e.target.value)}>
                <option value="">Theme defaults</option>
                {kits.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.name}
                    {k.is_default ? " (default)" : ""}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <AttachList
            title="Attach earlier research"
            empty="No completed research runs yet."
            items={research.map((r) => ({ id: r.id, label: r.question }))}
            value={researchIds}
            onToggle={(id) => setResearchIds((v) => toggle(v, id, 3))}
            max={3}
          />
          <AttachList
            title="Attach competitors"
            empty="No competitors tracked yet."
            items={competitors.map((c) => ({ id: c.id, label: c.name }))}
            value={competitorIds}
            onToggle={(id) => setCompetitorIds((v) => toggle(v, id, 5))}
            max={5}
          />
          <AttachList
            title="Attach campaign analyses"
            empty="No campaign analyses yet."
            items={campaigns.map((c) => ({ id: c.id, label: c.name || c.subject }))}
            value={campaignIds}
            onToggle={(id) => setCampaignIds((v) => toggle(v, id, 3))}
            max={3}
          />
        </div>
        <div className="space-y-2">
          <Field label={`Datasets to use (${datasetIds.length}/6)`} htmlFor="wz-ds">
            <input id="wz-ds" className={fieldCls} placeholder="Search datasets" value={dsFilter} onChange={(e) => setDsFilter(e.target.value)} />
          </Field>
          {catalogError && <ErrorNote message={catalogError} />}
          {!catalog && !catalogError && <p className="text-xs text-muted-foreground">Loading datasets…</p>}
          <div className="max-h-[360px] space-y-3 overflow-y-auto rounded-md border border-border p-2">
            {byCat.map(([cat, ds]) => (
              <div key={cat}>
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{cat}</div>
                {ds.map((d) => (
                  <label key={d.id} className="flex cursor-pointer items-start gap-2 rounded px-1 py-1 text-xs hover:bg-muted/50">
                    <input type="checkbox" className="mt-0.5" checked={datasetIds.includes(d.id)} disabled={!datasetIds.includes(d.id) && datasetIds.length >= 6} onChange={() => setDatasetIds((v) => toggle(v, d.id, 6))} />
                    <span>
                      <span className="font-medium text-foreground">{d.label}</span>
                      <span className="block text-muted-foreground">{d.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            ))}
            {catalog && byCat.length === 0 && <p className="p-2 text-xs text-muted-foreground">No datasets match.</p>}
          </div>
          {catalog?.skipped && catalog.skipped.length > 0 && <p className="text-[11px] text-muted-foreground">{catalog.skipped.length} dataset(s) are not available yet (no verified source).</p>}
        </div>
      </div>
      <ErrorNote message={error} className="mt-3" />
    </Modal>
  )
}

function AttachList({ title, items, value, onToggle, empty, max }: { title: string; items: { id: string; label: string }[]; value: string[]; onToggle: (id: string) => void; empty: string; max: number }) {
  return (
    <details className="rounded-md border border-border">
      <summary className="cursor-pointer px-2 py-1.5 text-xs font-medium text-foreground">
        {title} {value.length > 0 && <Pill tone="info">{value.length} selected</Pill>}
      </summary>
      <div className="max-h-32 space-y-0.5 overflow-y-auto border-t border-border p-2">
        {items.length === 0 && <p className="text-xs text-muted-foreground">{empty}</p>}
        {items.map((i) => (
          <label key={i.id} className="flex cursor-pointer items-start gap-2 text-xs">
            <input type="checkbox" className="mt-0.5" checked={value.includes(i.id)} disabled={!value.includes(i.id) && value.length >= max} onChange={() => onToggle(i.id)} />
            <span className="line-clamp-2">{i.label}</span>
          </label>
        ))}
      </div>
    </details>
  )
}

function Review({ result, doc, setDoc, sel, setSel, kitId }: { result: OutlineResult; doc: DeckDoc; setDoc: (d: DeckDoc) => void; sel: number; setSel: (n: number) => void; kitId: string }) {
  const { kit } = useBrandKit(kitId || null)
  const theme = useMemo(() => mergeTheme(kit, doc.theme), [kit, doc.theme])
  const { states, data, asOf } = useDeckData(doc)
  const { datasetLabel } = useStudio()
  const slide = doc.slides[Math.min(sel, doc.slides.length - 1)]
  const dropped = [...(result.dropped.queries ?? []), ...(result.dropped.blocks ?? [])]
  return (
    <div className="grid gap-4 md:grid-cols-[260px_1fr]">
      <div>
        <ol className="space-y-1">
          {doc.slides.map((s, i) => (
            <li key={s.id} className={`flex items-center gap-1 rounded border px-2 py-1.5 text-xs ${i === sel ? "border-primary bg-primary/10" : "border-border"}`}>
              <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setSel(i)}>
                <span className="text-muted-foreground">{i + 1}.</span> <span className="font-medium text-foreground">{s.title || "Untitled"}</span>
                <span className="block text-[11px] text-muted-foreground">
                  {LAYOUT_LABELS[s.layout]} · {s.blocks.length} block(s)
                </span>
              </button>
              <button type="button" aria-label={`Move slide ${i + 1} up`} disabled={i === 0} onClick={() => { setDoc(moveSlide(doc, i, i - 1)); setSel(i - 1) }} className="rounded p-1 hover:bg-muted disabled:opacity-30">
                <ArrowUp className="h-3.5 w-3.5" />
              </button>
              <button type="button" aria-label={`Move slide ${i + 1} down`} disabled={i === doc.slides.length - 1} onClick={() => { setDoc(moveSlide(doc, i, i + 1)); setSel(i + 1) }} className="rounded p-1 hover:bg-muted disabled:opacity-30">
                <ArrowDown className="h-3.5 w-3.5" />
              </button>
              <button type="button" aria-label={`Remove slide ${i + 1}`} disabled={doc.slides.length <= 1} onClick={() => { setDoc(removeSlide(doc, s.id)); setSel(Math.max(0, Math.min(sel, doc.slides.length - 2))) }} className="rounded p-1 text-red-400 hover:bg-red-500/10 disabled:opacity-30">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ol>
      </div>
      <div className="min-w-0 space-y-3">
        {slide && (
          <div className="overflow-hidden rounded-md border border-border">
            <SlideRenderer slide={slide} index={doc.slides.indexOf(slide)} total={doc.slides.length} theme={theme} states={states} data={data} asOf={asOf} datasetLabel={datasetLabel} mode="view" />
          </div>
        )}
        <div className="flex flex-wrap gap-2 text-xs">
          <Pill tone="good">{result.queries_kept} queries kept</Pill>
          <Pill tone={result.queries_tested - result.queries_kept > 0 ? "warn" : "muted"}>{Math.max(0, result.queries_tested - result.queries_kept)} dropped</Pill>
          {result.model && <Pill>{result.model}</Pill>}
          {result.ai_calls_today && <Pill>AI calls today {result.ai_calls_today.used}/{result.ai_calls_today.cap}</Pill>}
        </div>
        {dropped.length > 0 && (
          <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
            <div className="mb-1 font-semibold">Left out (failed validation or returned no data)</div>
            <ul className="list-disc space-y-0.5 pl-4">
              {dropped.map((d, i) => (
                <li key={i}>
                  <span className="font-medium">{String(d.alias ?? d.id ?? "item")}</span>: {String(d.reason ?? "dropped")}
                </li>
              ))}
            </ul>
          </div>
        )}
        {result.ungrounded_numbers.length > 0 && (
          <div className="flex gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              {result.ungrounded_numbers.length} figure(s) the AI wrote without a data reference were replaced by “[add figure]” placeholders. Fill them in with “Insert data value” in the editor.
            </span>
          </div>
        )}
        {result.citations.length > 0 && <p className="text-xs text-muted-foreground">{result.citations.length} research citation(s) are included in speaker notes.</p>}
      </div>
    </div>
  )
}
