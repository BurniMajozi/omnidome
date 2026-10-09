"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ChevronDown,
  CloudOff,
  Download,
  FileJson,
  FileText,
  History,
  Loader2,
  Lock,
  PanelRight,
  Play,
  Presentation,
  Redo2,
  RefreshCw,
  Sparkles,
  Undo2,
  Upload,
  ZoomIn,
  ZoomOut,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  BiApiError,
  createDeck,
  exportDeckJson,
  getDeck,
  listVersions,
  publishDeck,
  restoreVersion,
  saveDeck,
  unwrapVersions,
  type Block,
  type Deck,
  type DeckDoc,
  type DeckVersionSummary,
  type ExportBundle,
  type Layout,
  type Slide,
  type Ungrounded,
} from "@/lib/bi-studio-api"
import { ErrorNote, Pill, errText, fmtDateTime } from "../shared"
import { IconBtn, Modal, SideDrawer, useStudio } from "./ui"
import { useHistory } from "./use-history"
import { useDeckData } from "./use-deck-data"
import { useBrandKit } from "./use-kit"
import { mergeTheme } from "./theme"
import { SlideRenderer } from "./slide-renderer"
import { SlideRail } from "./slide-rail"
import { Inspector } from "./inspector"
import { AiPanel } from "./ai-panel"
import { ChartBuilder, type BuilderKind, type BuilderResult } from "./chart-builder"
import { DataValuePicker } from "./data-picker"
import { PresentMode } from "./present-mode"
import { PrintDeck } from "./print-deck"
import { pptxToBlob, safeFileName } from "./pptx-export"
import {
  addBlock,
  duplicateBlock,
  duplicateSlide,
  insertSlide,
  itemsToText,
  makeSlide,
  moveBlock,
  moveSlide,
  newBlockOfType,
  pruneQueries,
  removeBlock,
  removeSlide,
  replaceSlide,
  textToItems,
  updateBlock,
  updateSlide,
} from "./doc-ops"

type SaveState = "saved" | "dirty" | "saving" | "error" | "conflict" | "locked"

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

async function fetchImageData(url: string): Promise<string | null> {
  try {
    const r = await fetch(url, { referrerPolicy: "no-referrer", signal: AbortSignal.timeout(8000) })
    if (!r.ok) return null
    const b = await r.blob()
    if (!/^image\/(png|jpeg)$/.test(b.type) || b.size > 3_000_000) return null
    return await new Promise((res) => {
      const fr = new FileReader()
      fr.onload = () => res(String(fr.result))
      fr.onerror = () => res(null)
      fr.readAsDataURL(b)
    })
  } catch {
    return null
  }
}

export function DeckEditor({ deckId, onBack }: { deckId: string; onBack: () => void }) {
  const studio = useStudio()
  const hist = useHistory()
  const doc = hist.doc
  const docRef = useRef<DeckDoc | null>(null)
  docRef.current = doc

  const [deck, setDeck] = useState<Deck | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)
  const versionRef = useRef(0)
  const [status, setStatus] = useState("draft")
  const [savedDoc, setSavedDoc] = useState<DeckDoc | null>(null)
  const savedRef = useRef<DeckDoc | null>(null)
  const [saveState, setSaveState] = useState<SaveState>("saved")
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<Ungrounded[]>([])
  const clearKitRef = useRef(false)
  const saving = useRef<Promise<boolean> | null>(null)
  const retriedRef = useRef(false)

  const [slideId, setSlideId] = useState<string>("")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [zoom, setZoom] = useState<"fit" | number>("fit")
  const [tab, setTab] = useState<"design" | "ai">("design")
  const [panelOpen, setPanelOpen] = useState(true)
  const [builder, setBuilder] = useState<{ kind: BuilderKind; block: Block | null } | null>(null)
  const [picker, setPicker] = useState<"notes" | "block" | null>(null)
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [presentAt, setPresentAt] = useState<number | null>(null)
  const [printing, setPrinting] = useState(false)
  const [busyMsg, setBusyMsg] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [narrow, setNarrow] = useState(false)

  const taRef = useRef<HTMLTextAreaElement>(null)
  const selRef = useRef<{ s: number; e: number }>({ s: 0, e: 0 })
  const notesRef = useRef<HTMLTextAreaElement | null>(null)
  const canvasBox = useRef<HTMLDivElement>(null)
  const [avail, setAvail] = useState({ w: 800, h: 500 })

  // ── load ────────────────────────────────────────────────────────────
  useEffect(() => {
    let live = true
    getDeck(deckId)
      .then((d) => {
        if (!live) return
        setDeck(d)
        hist.reset(d.doc)
        savedRef.current = d.doc
        setSavedDoc(d.doc)
        versionRef.current = d.version
        setVersion(d.version)
        setStatus(d.status)
        setSlideId(d.doc.slides[0]?.id ?? "")
      })
      .catch((e) => live && setLoadError(errText(e)))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deckId])

  useEffect(() => {
    const on = () => setNarrow(window.innerWidth < 720)
    on()
    window.addEventListener("resize", on)
    return () => window.removeEventListener("resize", on)
  }, [])
  useEffect(() => {
    const el = canvasBox.current
    if (!el) return
    const ro = new ResizeObserver(() => setAvail({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    setAvail({ w: el.clientWidth, h: el.clientHeight })
    return () => ro.disconnect()
  }, [deck, narrow])
  useEffect(() => {
    setPanelOpen(window.innerWidth >= 1180)
  }, [])

  const { kit } = useBrandKit(doc?.brand_kit_id ?? null)
  const theme = useMemo(() => mergeTheme(kit, doc?.theme), [kit, doc?.theme])
  const dd = useDeckData(doc, !!doc)

  const slideIdx = doc ? Math.max(0, doc.slides.findIndex((s) => s.id === slideId)) : 0
  const slide: Slide | null = doc ? (doc.slides[slideIdx] ?? null) : null
  const block = slide?.blocks.find((b) => b.id === selectedId) ?? null
  const dirty = !!doc && doc !== savedDoc
  const locked = saveState === "locked"
  const readOnly = locked || narrow

  // ── saving ──────────────────────────────────────────────────────────
  const saveOnce = useCallback(async (): Promise<boolean> => {
    const d = docRef.current
    if (!d || d === savedRef.current) return true
    setSaveState("saving")
    setSaveMsg(null)
    try {
      const body: Parameters<typeof saveDeck>[1] = { title: d.title, doc: d }
      if (clearKitRef.current) body.clear_brand_kit = true
      else if (d.brand_kit_id) body.brand_kit_id = d.brand_kit_id
      const r = await saveDeck(deckId, body, versionRef.current)
      versionRef.current = r.version
      setVersion(r.version)
      setStatus(r.status)
      savedRef.current = d
      setSavedDoc(d)
      clearKitRef.current = false
      retriedRef.current = false
      setWarnings(r.warnings?.ungrounded_numbers ?? [])
      setSaveState(docRef.current === d ? "saved" : "dirty")
      return true
    } catch (e) {
      if (e instanceof BiApiError) {
        if (e.status === 409) {
          setSaveState("conflict")
          setSaveMsg(e.currentVersion ? `Saved elsewhere as version ${e.currentVersion}.` : e.message)
          return false
        }
        if (e.status === 428 && !retriedRef.current) {
          retriedRef.current = true
          try {
            const cur = await getDeck(deckId)
            versionRef.current = cur.version
            return await saveOnce()
          } catch {
            /* fallthrough */
          }
        }
        if (e.status === 403) {
          studio.markReadOnly()
          setSaveState("locked")
          setSaveMsg(status === "published" ? "This deck is published; only admins can edit it." : "Your role does not allow editing decks.")
          return false
        }
        setSaveState("error")
        setSaveMsg(e.status === 422 ? `Not saved: ${e.message}` : e.message)
        return false
      }
      setSaveState("error")
      setSaveMsg(errText(e))
      return false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deckId, status])

  const saveNow = useCallback(async (): Promise<boolean> => {
    while (saving.current) await saving.current.catch(() => false)
    if (docRef.current === savedRef.current) return true
    const p = saveOnce()
    saving.current = p
    try {
      return await p
    } finally {
      saving.current = null
    }
  }, [saveOnce])

  useEffect(() => {
    if (!dirty || locked || saveState === "conflict" || saveState === "error") {
      if (dirty && saveState === "saved") setSaveState("dirty")
      return
    }
    setSaveState((s) => (s === "saving" ? s : "dirty"))
    const t = setTimeout(() => void saveNow(), 1600)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc, locked, saveState === "conflict", saveState === "error"])

  useEffect(() => {
    const h = (e: BeforeUnloadEvent) => {
      if (docRef.current !== savedRef.current) {
        e.preventDefault()
        e.returnValue = ""
      }
    }
    window.addEventListener("beforeunload", h)
    return () => window.removeEventListener("beforeunload", h)
  }, [])

  async function goBack() {
    if (docRef.current !== savedRef.current) {
      const ok = await saveNow()
      if (!ok && !window.confirm("Your latest changes could not be saved. Leave anyway and lose them?")) return
    }
    onBack()
  }

  // ── doc mutation helpers ────────────────────────────────────────────
  const commit = useCallback(
    (fn: (d: DeckDoc) => DeckDoc, key?: string) => {
      const d = docRef.current
      if (!d || readOnly) return
      hist.set(fn(d), key)
    },
    [hist, readOnly],
  )
  const setWholeDoc = useCallback((d: DeckDoc, key?: string) => hist.set(d, key), [hist])

  const cur = slide?.id ?? ""
  const selectSlide = (id: string) => {
    setSlideId(id)
    setSelectedId(null)
    setEditingId(null)
  }

  function addSlideOfLayout(layout: Layout) {
    commit((d) => {
      const s = makeSlide(d, layout)
      setTimeout(() => selectSlide(s.id), 0)
      return insertSlide(d, s, slideIdx + 1)
    })
  }
  function deleteSlide(id: string) {
    if (!doc || doc.slides.length <= 1) return
    const i = doc.slides.findIndex((s) => s.id === id)
    const next = doc.slides[i + 1] ?? doc.slides[i - 1]
    commit((d) => removeSlide(d, id))
    if (id === slideId && next) selectSlide(next.id)
  }
  function onAddBlock(t: "chart" | "kpi" | "table" | "text" | "image" | "shape") {
    if (!slide) return
    if (t === "chart" || t === "kpi" || t === "table") return setBuilder({ kind: t, block: null })
    const nb = newBlockOfType(doc!, t)
    commit((d) => addBlock(d, slide.id, nb))
    setSelectedId(nb.id)
    if (t === "text") setEditingId(nb.id)
  }
  function applyBuilder(r: BuilderResult) {
    if (!slide) return
    commit((d) => {
      let next = d
      if (r.kind === "kpi") next = { ...next, queries: { ...next.queries, [r.alias]: r.spec } }
      const exists = slide.blocks.some((b) => b.id === r.block.id)
      next = exists ? updateBlock(next, slide.id, r.block.id, r.block as Block) : addBlock(next, slide.id, r.block as Block)
      return pruneQueries(next)
    })
    setSelectedId(r.block.id)
    setBuilder(null)
  }

  // text insertion
  function insertToken(token: string) {
    const target = picker
    setPicker(null)
    if (!slide) return
    const wrapped = token.startsWith("{{") ? token : `{{${token}}}`
    if (target === "notes") {
      const ta = notesRef.current
      const curNotes = slide.notes ?? ""
      const pos = ta ? ta.selectionStart : curNotes.length
      const end = ta ? ta.selectionEnd : curNotes.length
      commit((d) => updateSlide(d, slide.id, { notes: curNotes.slice(0, pos) + wrapped + curNotes.slice(end) }))
      return
    }
    const b = slide.blocks.find((x) => x.id === (editingId ?? selectedId))
    if (!b || b.type !== "text") return
    const text = itemsToText(b.items)
    const useSel = editingId === b.id
    const s = useSel ? Math.min(selRef.current.s, text.length) : text.length
    const e = useSel ? Math.min(selRef.current.e, text.length) : text.length
    const next = text.slice(0, s) + wrapped + text.slice(e)
    commit((d) => updateBlock(d, slide.id, b.id, { ...b, items: textToItems(next, b.items) }))
  }

  // ── export ──────────────────────────────────────────────────────────
  const strictBlocked = (doc?.settings?.strict_numbers ?? false) && warnings.length > 0
  async function doExport(kind: "pptx" | "pdf" | "json") {
    setExportOpen(false)
    setActionError(null)
    setNotice(null)
    if (!doc) return
    if (strictBlocked) {
      setActionError("Export is blocked: strict numbers is on and some figures are typed outside a data reference. Fix the flagged blocks first.")
      return
    }
    if (kind === "pdf") {
      if (!(await saveNow())) return setActionError("Save failed, so the export was cancelled.")
      setPrinting(true)
      return
    }
    setBusyMsg(kind === "pptx" ? "Building PowerPoint…" : "Preparing JSON…")
    try {
      if (!(await saveNow())) throw new Error("Save failed, so the export was cancelled.")
      let bundle: ExportBundle
      try {
        bundle = await exportDeckJson(deckId, { refresh: true })
      } catch (e) {
        if (e instanceof BiApiError && e.forbidden) bundle = await exportDeckJson(deckId)
        else throw e
      }
      const fontFallback = Object.fromEntries((studio.options?.fonts ?? []).map((f) => [f.name, f.export_fallback]))
      if (kind === "json") download(new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" }), safeFileName(bundle.deck.title, "json"))
      else {
        const blob = await pptxToBlob(bundle, { fontFallback, fetchImage: fetchImageData })
        download(blob, safeFileName(bundle.deck.title, "pptx"))
      }
      const un = bundle.unresolved?.length ?? 0
      const qe = Object.keys(bundle.query_errors ?? {}).length
      setNotice(`Exported with data as of ${bundle.as_of ? fmtDateTime(bundle.as_of) : "now"}.${un ? ` ${un} value(s) could not be resolved and show as “—”.` : ""}${qe ? ` ${qe} query(ies) failed and show as unavailable.` : ""}`)
    } catch (e) {
      setActionError(errText(e))
    } finally {
      setBusyMsg(null)
    }
  }

  async function togglePublish() {
    setActionError(null)
    try {
      if (!(await saveNow())) throw new Error("Save first.")
      const r = await publishDeck(deckId, status !== "published")
      setStatus(r.status)
      versionRef.current = r.version
      setVersion(r.version)
      setNotice(r.status === "published" ? "Published. Only admins can edit it now." : "Unpublished.")
    } catch (e) {
      setActionError(e instanceof BiApiError && e.forbidden ? "Only admins can publish or unpublish decks." : errText(e))
    }
  }

  // conflict resolution
  async function reloadLatest() {
    try {
      const d = await getDeck(deckId)
      hist.reset(d.doc)
      savedRef.current = d.doc
      setSavedDoc(d.doc)
      versionRef.current = d.version
      setVersion(d.version)
      setStatus(d.status)
      setSaveState("saved")
      setSaveMsg(null)
      setWarnings([])
      setSlideId(d.doc.slides[0]?.id ?? "")
    } catch (e) {
      setActionError(errText(e))
    }
  }
  async function overwriteMine() {
    try {
      const d = await getDeck(deckId)
      versionRef.current = d.version
      setSaveState("dirty")
      setSaveMsg(null)
      void saveNow()
    } catch (e) {
      setActionError(errText(e))
    }
  }
  async function saveAsCopy() {
    if (!doc) return
    try {
      const d = await createDeck({ title: `${doc.title} (my edits)`.slice(0, 200), doc, brand_kit_id: doc.brand_kit_id ?? undefined })
      setNotice(`Saved your version as a new deck “${d.title}”.`)
      await reloadLatest()
    } catch (e) {
      setActionError(errText(e))
    }
  }

  // keyboard
  function onKeyDown(e: React.KeyboardEvent) {
    const t = e.target as HTMLElement
    const typing = t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable
    if ((e.ctrlKey || e.metaKey) && !typing) {
      if (e.key.toLowerCase() === "z") {
        e.preventDefault()
        e.shiftKey ? hist.redo() : hist.undo()
      } else if (e.key.toLowerCase() === "y") {
        e.preventDefault()
        hist.redo()
      } else if (e.key.toLowerCase() === "s") {
        e.preventDefault()
        void saveNow()
      }
      return
    }
    if (e.key === "Escape" && !typing) {
      setSelectedId(null)
      setEditingId(null)
    }
    if ((e.key === "Delete" || e.key === "Backspace") && !typing && selectedId && slide && !readOnly && t.closest("[data-block-id]")) {
      e.preventDefault()
      commit((d) => removeBlock(d, slide.id, selectedId))
      setSelectedId(null)
    }
  }

  if (loadError)
    return (
      <div className="space-y-3">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" /> Decks
        </Button>
        <ErrorNote message={loadError} />
      </div>
    )
  if (!deck || !doc || !slide)
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading deck…
      </p>
    )

  // ── warnings by block ───────────────────────────────────────────────
  const warnBy: Record<string, Ungrounded[]> = {}
  for (const w of warnings) {
    let id: string | null = null
    for (const s of doc.slides) {
      for (const b of s.blocks) if (w.where.includes(b.id)) id = b.id
      if (!id && w.where.includes(s.id)) id = s.blocks.find((b) => b.type === "text")?.id ?? null
    }
    if (id) (warnBy[id] ??= []).push(w)
  }

  // ── phone: read-only preview ────────────────────────────────────────
  if (narrow)
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" /> Decks
          </Button>
          <h1 className="truncate text-base font-semibold">{doc.title}</h1>
        </div>
        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">Use a larger screen to edit. This is a read-only preview.</p>
        {doc.slides.map((s, i) => (
          <div key={s.id} className="overflow-hidden rounded-md border border-border">
            <SlideRenderer slide={s} index={i} total={doc.slides.length} theme={theme} states={dd.states} data={dd.data} asOf={dd.asOf} datasetLabel={studio.datasetLabel} mode="view" />
          </div>
        ))}
      </div>
    )

  const fitW = Math.max(240, Math.min(avail.w - 40, (avail.h - 56) * (16 / 9)))
  const canvasW = zoom === "fit" ? fitW : fitW * zoom
  const editingBlock = slide.blocks.find((b) => b.id === editingId)

  const saveBadge = (() => {
    switch (saveState) {
      case "saving":
        return (
          <span className="flex items-center gap-1 text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Saving…
          </span>
        )
      case "saved":
        return (
          <span className="flex items-center gap-1 text-emerald-400">
            <Check className="h-3.5 w-3.5" /> Saved · v{version}
          </span>
        )
      case "dirty":
        return <span className="text-muted-foreground">Unsaved changes…</span>
      case "conflict":
        return (
          <span className="flex items-center gap-1 text-amber-300">
            <AlertTriangle className="h-3.5 w-3.5" /> Conflict
          </span>
        )
      case "locked":
        return (
          <span className="flex items-center gap-1 text-amber-300">
            <Lock className="h-3.5 w-3.5" /> Read-only
          </span>
        )
      default:
        return (
          <button type="button" onClick={() => { setSaveState("dirty"); void saveNow() }} className="flex items-center gap-1 text-red-300 underline">
            <CloudOff className="h-3.5 w-3.5" /> Not saved, retry
          </button>
        )
    }
  })()

  return (
    <div className="flex h-[calc(100vh-8.5rem)] min-h-[560px] flex-col rounded-lg border border-border bg-card/40" onKeyDown={onKeyDown}>
      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-border px-2 py-1.5">
        <IconBtn label="Back to decks" onClick={goBack}>
          <ArrowLeft className="h-4 w-4" />
        </IconBtn>
        <label className="sr-only" htmlFor="deck-title">
          Deck title
        </label>
        <input id="deck-title" className="h-8 min-w-[10rem] max-w-xs flex-1 rounded-md border border-transparent bg-transparent px-2 text-sm font-semibold text-foreground hover:border-border focus:border-primary focus:outline-none" value={doc.title} maxLength={200} disabled={readOnly} onChange={(e) => commit((d) => ({ ...d, title: e.target.value }), "deck-title")} />
        <Pill tone={status === "published" ? "good" : "muted"}>{status === "published" ? "Published" : "Draft"}</Pill>
        <div className="text-xs" aria-live="polite">
          {saveBadge}
        </div>
        <div className="mx-1 hidden h-5 w-px bg-border sm:block" />
        <IconBtn label="Undo (Ctrl+Z)" disabled={!hist.canUndo || readOnly} onClick={hist.undo}>
          <Undo2 className="h-4 w-4" />
        </IconBtn>
        <IconBtn label="Redo (Ctrl+Shift+Z)" disabled={!hist.canRedo || readOnly} onClick={hist.redo}>
          <Redo2 className="h-4 w-4" />
        </IconBtn>
        <div className="mx-1 hidden h-5 w-px bg-border sm:block" />
        <IconBtn label="Zoom out" onClick={() => setZoom((z) => Math.max(0.5, (z === "fit" ? 1 : z) - 0.25))}>
          <ZoomOut className="h-4 w-4" />
        </IconBtn>
        <button type="button" className="h-8 rounded-md px-2 text-xs text-muted-foreground hover:bg-muted" onClick={() => setZoom("fit")} aria-label="Zoom to fit">
          {zoom === "fit" ? "Fit" : `${Math.round(zoom * 100)}%`}
        </button>
        <IconBtn label="Zoom in" onClick={() => setZoom((z) => Math.min(2, (z === "fit" ? 1 : z) + 0.25))}>
          <ZoomIn className="h-4 w-4" />
        </IconBtn>

        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          <span className={`text-xs ${dd.stale ? "text-amber-300" : "text-muted-foreground"}`} title="Oldest query result on this deck">
            {dd.loading ? "Loading data…" : dd.asOf ? `Data as of ${new Date(dd.asOf).toLocaleTimeString("en-ZA", { hour: "2-digit", minute: "2-digit" })}${dd.stale ? " (stale)" : ""}` : "No data yet"}
            {dd.errors > 0 && <span className="ml-1 text-red-300">· {dd.errors} failed</span>}
          </span>
          <Button size="sm" variant="outline" className="h-8" onClick={dd.refreshAll} disabled={dd.loading}>
            <RefreshCw className={`h-3.5 w-3.5 ${dd.loading ? "animate-spin" : ""}`} /> Refresh data
          </Button>
          <IconBtn label="Version history" onClick={() => setVersionsOpen(true)}>
            <History className="h-4 w-4" />
          </IconBtn>
          <Button size="sm" variant="outline" className="h-8" onClick={() => setPresentAt(slideIdx)}>
            <Play className="h-3.5 w-3.5" /> Present
          </Button>
          <div className="relative">
            <Button size="sm" variant="outline" className="h-8" onClick={() => setExportOpen((v) => !v)} aria-haspopup="menu" aria-expanded={exportOpen} disabled={!!busyMsg}>
              {busyMsg ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />} Export <ChevronDown className="h-3 w-3" />
            </Button>
            {exportOpen && (
              <div role="menu" className="absolute right-0 top-full z-40 mt-1 w-60 rounded-md border border-border bg-card p-1 shadow-xl">
                <MenuItem icon={<Presentation className="h-4 w-4" />} label="PowerPoint (.pptx)" sub="Editable charts, tables and notes" onClick={() => doExport("pptx")} />
                <MenuItem icon={<FileText className="h-4 w-4" />} label="PDF" sub="Opens the print dialog; choose Save as PDF" onClick={() => doExport("pdf")} />
                <MenuItem icon={<FileJson className="h-4 w-4" />} label="JSON" sub="Resolved slides and data" onClick={() => doExport("json")} />
              </div>
            )}
          </div>
          <Button size="sm" variant="outline" className="h-8" onClick={togglePublish}>
            <Upload className="h-3.5 w-3.5" /> {status === "published" ? "Unpublish" : "Publish"}
          </Button>
          <IconBtn label={panelOpen ? "Hide side panel" : "Show side panel"} active={panelOpen} onClick={() => setPanelOpen((v) => !v)}>
            <PanelRight className="h-4 w-4" />
          </IconBtn>
        </div>
      </div>

      {/* banners */}
      {(saveState === "conflict" || locked || saveState === "error" || actionError || notice || warnings.length > 0 || strictBlocked) && (
        <div className="space-y-1 border-b border-border px-3 py-2 text-xs">
          {saveState === "conflict" && (
            <div className="flex flex-wrap items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-amber-100">
              <AlertTriangle className="h-4 w-4" />
              <span className="mr-auto">{saveMsg ?? "This deck changed elsewhere."} Your edits were not saved.</span>
              <Button size="sm" variant="outline" className="h-7" onClick={reloadLatest}>
                Reload latest (discard mine)
              </Button>
              <Button size="sm" variant="outline" className="h-7" onClick={overwriteMine}>
                Overwrite with mine
              </Button>
              <Button size="sm" variant="outline" className="h-7" onClick={saveAsCopy}>
                Save mine as a new deck
              </Button>
            </div>
          )}
          {locked && (
            <div className="flex flex-wrap items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-amber-100">
              <Lock className="h-4 w-4" />
              <span className="mr-auto">{saveMsg}</span>
              <Button size="sm" variant="outline" className="h-7" onClick={reloadLatest}>
                Discard my edits and reload
              </Button>
              <Button size="sm" variant="outline" className="h-7" onClick={saveAsCopy}>
                Save mine as a new deck
              </Button>
            </div>
          )}
          {saveState === "error" && saveMsg && <ErrorNote message={saveMsg} />}
          {actionError && <ErrorNote message={actionError} />}
          {notice && (
            <p className="flex items-center gap-2 text-emerald-300">
              <Check className="h-3.5 w-3.5" /> {notice}
              <button type="button" className="ml-auto text-muted-foreground underline" onClick={() => setNotice(null)}>
                Dismiss
              </button>
            </p>
          )}
          {warnings.length > 0 && (
            <p className="flex items-center gap-2 text-amber-300">
              <AlertTriangle className="h-3.5 w-3.5" /> {warnings.length} figure(s) typed outside a data reference (flagged on the slides). {strictBlocked ? "Strict mode blocks export until fixed." : "Replace them with “Insert data value” so they stay accurate."}
            </p>
          )}
        </div>
      )}

      <div className="relative flex min-h-0 flex-1">
        {/* rail */}
        <div className="w-[132px] shrink-0 border-r border-border md:w-[168px]">
          <SlideRail doc={doc} theme={theme} states={dd.states} data={dd.data} currentId={cur} readOnly={readOnly} onSelect={selectSlide} onMove={(f, t) => commit((d) => moveSlide(d, f, t))} onDuplicate={(id) => commit((d) => duplicateSlide(d, id))} onDelete={deleteSlide} onAdd={addSlideOfLayout} />
        </div>

        {/* canvas */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div ref={canvasBox} className="min-h-0 flex-1 overflow-auto bg-muted/20 p-5" onClick={() => { setSelectedId(null); setEditingId(null) }}>
            <div className="mx-auto overflow-hidden rounded shadow-xl ring-1 ring-black/20" style={{ width: canvasW }} onClick={(e) => e.stopPropagation()}>
              <SlideRenderer
                slide={slide}
                index={slideIdx}
                total={doc.slides.length}
                theme={theme}
                states={dd.states}
                data={dd.data}
                asOf={dd.asOf}
                datasetLabel={studio.datasetLabel}
                mode={readOnly ? "view" : "edit"}
                selectedId={selectedId}
                onSelect={(id) => {
                  setSelectedId(id)
                  if (id !== editingId) setEditingId(null)
                }}
                onRetry={dd.retry}
                editingId={editingId}
                onStartEdit={(id) => !readOnly && setEditingId(id)}
                onAddBlock={(t) => onAddBlock(t)}
                warnings={warnBy}
                renderEditor={(b) => (
                  <textarea
                    ref={taRef}
                    autoFocus
                    aria-label="Edit text. One line per item; start a line with a dash for a bullet."
                    value={itemsToText(b.items)}
                    onChange={(e) => {
                      selRef.current = { s: e.target.selectionStart, e: e.target.selectionEnd }
                      commit((d) => updateBlock(d, slide.id, b.id, { ...b, items: textToItems(e.target.value, b.items) }), `text:${b.id}`)
                    }}
                    onSelect={(e) => (selRef.current = { s: e.currentTarget.selectionStart, e: e.currentTarget.selectionEnd })}
                    onBlur={() => !picker && setEditingId(null)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") {
                        e.stopPropagation()
                        setEditingId(null)
                      }
                    }}
                    onClick={(e) => e.stopPropagation()}
                    style={{ width: "100%", height: "100%", resize: "none", fontSize: 15, lineHeight: 1.4, padding: 6, border: `2px solid ${theme.palette.primary}`, background: "rgba(255,255,255,0.97)", color: "#111", fontFamily: "ui-monospace, monospace", borderRadius: 4 }}
                  />
                )}
              />
            </div>
            {readOnly && !locked && <p className="mt-2 text-center text-xs text-muted-foreground">Read-only</p>}
          </div>
          {editingBlock && (
            <div className="flex flex-wrap items-center gap-2 border-t border-border bg-card px-3 py-1.5 text-xs">
              <span className="text-muted-foreground">Editing text. Numbers should be inserted from data, not typed.</span>
              <Button size="sm" variant="outline" className="ml-auto h-7" onMouseDown={(e) => e.preventDefault()} onClick={() => setPicker("block")}>
                Insert data value
              </Button>
              <Button size="sm" className="h-7" onMouseDown={(e) => e.preventDefault()} onClick={() => setEditingId(null)}>
                Done (Esc)
              </Button>
            </div>
          )}
        </div>

        {/* right panel */}
        {panelOpen && (
          <aside className="absolute inset-y-0 right-0 z-20 flex w-[300px] flex-col border-l border-border bg-card shadow-xl lg:static lg:shadow-none" aria-label="Inspector">
            <div className="flex border-b border-border" role="tablist">
              {(
                [
                  ["design", "Design"],
                  ["ai", "AI"],
                ] as const
              ).map(([k, l]) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`flex-1 py-2 text-xs font-semibold ${tab === k ? "border-b-2 border-primary text-primary" : "text-muted-foreground hover:text-foreground"}`}>
                  {k === "ai" && <Sparkles className="mr-1 inline h-3 w-3" />}
                  {l}
                </button>
              ))}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              {tab === "design" ? (
                <Inspector
                  doc={doc}
                  slide={slide}
                  block={block}
                  readOnly={readOnly}
                  states={dd.states}
                  setDoc={setWholeDoc}
                  onSelectBlock={setSelectedId}
                  onUpdateBlock={(id, fn, key) => commit((d) => updateBlock(d, slide.id, id, fn), key)}
                  onUpdateSlide={(patch, key) => commit((d) => updateSlide(d, slide.id, patch), key)}
                  onChangeLayout={(l) => commit((d) => updateSlide(d, slide.id, { layout: l }))}
                  onEditData={(b) => setBuilder({ kind: b.type === "kpi" ? "kpi" : b.type === "table" ? "table" : "chart", block: b })}
                  onAddBlock={onAddBlock}
                  onDeleteBlock={(id) => {
                    commit((d) => removeBlock(d, slide.id, id))
                    setSelectedId(null)
                  }}
                  onDuplicateBlock={(id) => {
                    const r = duplicateBlock(doc, slide.id, id)
                    if (r.id) {
                      commit(() => r.doc)
                      setSelectedId(r.id)
                    }
                  }}
                  onMoveBlock={(id, delta) => commit((d) => moveBlock(d, slide.id, id, delta))}
                  onEditText={(id) => setEditingId(id)}
                  onInsertValue={(t) => setPicker(t)}
                  onRetry={dd.retry}
                  kits={studio.kits}
                  onKit={(id) => {
                    clearKitRef.current = id === null
                    commit((d) => ({ ...d, brand_kit_id: id }))
                  }}
                  onTheme={(patch) => commit((d) => ({ ...d, theme: { ...(d.theme ?? {}), ...patch } }), "theme")}
                  onStrict={(v) => commit((d) => ({ ...d, settings: { ...(d.settings ?? {}), strict_numbers: v } }))}
                  registerNotes={(el) => { notesRef.current = el }}
                  warnings={warnBy}
                />
              ) : (
                <AiPanel
                  deckId={deckId}
                  doc={doc}
                  slide={slide}
                  slideIndex={slideIdx}
                  readOnly={readOnly}
                  theme={theme}
                  states={dd.states}
                  data={dd.data}
                  getVersion={() => versionRef.current}
                  saveNow={saveNow}
                  onAcceptDoc={(nd) => {
                    commit(() => nd)
                    setSelectedId(null)
                  }}
                  onSetNotes={(notes) => commit((d) => updateSlide(d, slide.id, { notes }))}
                  onAddTakeaways={(items) => {
                    const nb = newBlockOfType(doc, "text")
                    if (nb.type === "text") nb.items = items.map((t) => ({ text: t, bullet: true }))
                    commit((d) => addBlock(d, slide.id, nb))
                    setSelectedId(nb.id)
                  }}
                />
              )}
            </div>
          </aside>
        )}
      </div>

      {builder && <ChartBuilder kind={builder.kind} block={builder.block} doc={doc} theme={theme} onApply={applyBuilder} onClose={() => setBuilder(null)} />}
      {picker && <DataValuePicker doc={doc} data={dd.data} onInsert={insertToken} onClose={() => setPicker(null)} />}
      {versionsOpen && (
        <VersionDrawer
          deckId={deckId}
          current={version}
          onClose={() => setVersionsOpen(false)}
          beforeRestore={saveNow}
          onRestored={(d) => {
            hist.reset(d.doc)
            savedRef.current = d.doc
            setSavedDoc(d.doc)
            versionRef.current = d.version
            setVersion(d.version)
            setSaveState("saved")
            setSlideId(d.doc.slides[0]?.id ?? "")
            setVersionsOpen(false)
            setNotice(`Restored; saved as version ${d.version}.`)
          }}
        />
      )}
      {presentAt !== null && <PresentMode doc={doc} theme={theme} states={dd.states} data={dd.data} asOf={dd.asOf} start={presentAt} datasetLabel={studio.datasetLabel} onExit={() => setPresentAt(null)} />}
      {printing && <PrintDeck doc={doc} theme={theme} states={dd.states} data={dd.data} asOf={dd.asOf} onDone={() => setPrinting(false)} />}
    </div>
  )
}

function MenuItem({ icon, label, sub, onClick }: { icon: React.ReactNode; label: string; sub: string; onClick: () => void }) {
  return (
    <button type="button" role="menuitem" onClick={onClick} className="flex w-full items-start gap-2 rounded px-2 py-1.5 text-left hover:bg-muted">
      <span className="mt-0.5 text-muted-foreground">{icon}</span>
      <span>
        <span className="block text-xs font-medium text-foreground">{label}</span>
        <span className="block text-[11px] text-muted-foreground">{sub}</span>
      </span>
    </button>
  )
}

function VersionDrawer({ deckId, current, onClose, beforeRestore, onRestored }: { deckId: string; current: number; onClose: () => void; beforeRestore: () => Promise<boolean>; onRestored: (d: Deck) => void }) {
  const [items, setItems] = useState<DeckVersionSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<number | null>(null)
  const [confirm, setConfirm] = useState<number | null>(null)
  useEffect(() => {
    listVersions(deckId)
      .then((r) => setItems(unwrapVersions(r).sort((a, b) => b.version - a.version)))
      .catch((e) => setError(errText(e)))
  }, [deckId])
  async function restore(n: number) {
    setBusy(n)
    setError(null)
    try {
      if (!(await beforeRestore())) throw new Error("Save your current changes before restoring.")
      const fresh = await getDeck(deckId)
      const r = await restoreVersion(deckId, n, fresh.version)
      onRestored(r)
    } catch (e) {
      setError(e instanceof BiApiError && e.forbidden ? "Your role cannot restore versions of this deck." : errText(e))
      setBusy(null)
    }
  }
  return (
    <SideDrawer title="Version history" onClose={onClose}>
      <p className="mb-3 text-xs text-muted-foreground">Every save is a version. Restoring creates a new version with the old content, so nothing is lost.</p>
      <ErrorNote message={error} />
      {!items && !error && <p className="text-sm text-muted-foreground">Loading…</p>}
      <ul className="space-y-2">
        {items?.map((v) => (
          <li key={v.version} className="rounded-md border border-border p-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-foreground">Version {v.version}</span>
              {v.version === current ? <Pill tone="good">Current</Pill> : null}
            </div>
            <div className="text-muted-foreground">{fmtDateTime(v.created_at)}</div>
            {v.note && <div className="text-muted-foreground">{v.note}</div>}
            {v.version !== current && (
              <div className="mt-1.5">
                {confirm === v.version ? (
                  <div className="flex items-center gap-2">
                    <span>Replace the current content?</span>
                    <Button size="sm" className="h-6 text-xs" disabled={busy !== null} onClick={() => restore(v.version)}>
                      {busy === v.version ? <Loader2 className="h-3 w-3 animate-spin" /> : null} Restore
                    </Button>
                    <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => setConfirm(null)}>
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <Button size="sm" variant="outline" className="h-6 text-xs" onClick={() => setConfirm(v.version)}>
                    Restore this version
                  </Button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </SideDrawer>
  )
}

