"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { X } from "lucide-react"
import type { DeckDoc } from "@/lib/bi-studio-api"
import { SlideRenderer } from "./slide-renderer"
import { resolveText, type DataMap } from "./tokens"
import type { Theme } from "./theme"
import type { QState } from "./use-deck-data"

/** Full-screen presentation. Arrow keys / space / click to advance, Home/End, N toggles speaker notes, Esc exits. */
export function PresentMode({
  doc,
  theme,
  states,
  data,
  asOf,
  start,
  datasetLabel,
  onExit,
}: {
  doc: DeckDoc
  theme: Theme
  states: Record<string, QState>
  data: DataMap
  asOf: string | null
  start: number
  datasetLabel: (id: string) => string
  onExit: () => void
}) {
  const [i, setI] = useState(Math.max(0, Math.min(start, doc.slides.length - 1)))
  const [notes, setNotes] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const go = useCallback((n: number) => setI((c) => Math.max(0, Math.min(doc.slides.length - 1, c + n))), [doc.slides.length])

  useEffect(() => {
    const el = root.current
    el?.focus()
    el?.requestFullscreen?.().catch(() => {})
    const onFs = () => {
      if (!document.fullscreenElement) onExit()
    }
    document.addEventListener("fullscreenchange", onFs)
    return () => {
      document.removeEventListener("fullscreenchange", onFs)
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function onKey(e: React.KeyboardEvent) {
    switch (e.key) {
      case "ArrowRight":
      case "ArrowDown":
      case "PageDown":
      case " ":
      case "Enter":
        e.preventDefault()
        go(1)
        break
      case "ArrowLeft":
      case "ArrowUp":
      case "PageUp":
      case "Backspace":
        e.preventDefault()
        go(-1)
        break
      case "Home":
        setI(0)
        break
      case "End":
        setI(doc.slides.length - 1)
        break
      case "n":
      case "N":
        setNotes((v) => !v)
        break
      case "Escape":
        onExit()
        break
    }
  }
  const slide = doc.slides[i]
  const noteText = resolveText(slide.notes ?? "", data)
  return (
    <div ref={root} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Presentation" onKeyDown={onKey} className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-black outline-none">
      <button type="button" aria-label="Exit presentation" onClick={onExit} className="absolute right-3 top-3 z-10 rounded-full bg-white/10 p-2 text-white opacity-0 transition-opacity hover:opacity-100 focus:opacity-100">
        <X className="h-5 w-5" />
      </button>
      <div
        className="relative"
        style={{ width: "min(100vw, calc((100vh - 0px) * 16 / 9))", maxHeight: "100vh" }}
        onClick={(e) => {
          const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
          go(e.clientX - r.left < r.width * 0.25 ? -1 : 1)
        }}
      >
        <SlideRenderer slide={slide} index={i} total={doc.slides.length} theme={theme} states={states} data={data} asOf={asOf} datasetLabel={datasetLabel} mode="view" />
      </div>
      <div className="pointer-events-none absolute bottom-2 right-4 rounded bg-black/60 px-2 py-0.5 text-xs text-white/80" aria-live="polite">
        {i + 1} / {doc.slides.length}
      </div>
      {notes && (
        <div className="absolute bottom-0 left-0 right-0 max-h-[30vh] overflow-y-auto bg-black/85 p-4 text-sm text-white">
          <div className="mb-1 text-xs uppercase tracking-wide text-white/60">Speaker notes (N to hide)</div>
          {noteText ? <p className="whitespace-pre-wrap">{noteText}</p> : <p className="text-white/50">No notes for this slide.</p>}
        </div>
      )}
    </div>
  )
}
