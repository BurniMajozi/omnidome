"use client"

import { useEffect, useRef, useState } from "react"
import { Copy, Plus, Trash2 } from "lucide-react"
import type { DeckDoc, Layout, Slide } from "@/lib/bi-studio-api"
import { cn } from "@/lib/utils"
import { SlideRenderer } from "./slide-renderer"
import { computeFrames, LAYOUT_LABELS, LAYOUT_ORDER } from "./layout"
import type { Theme } from "./theme"
import type { QState } from "./use-deck-data"
import type { DataMap } from "./tokens"

/** Mini schematic of a layout's zones. */
export function LayoutGlyph({ layout, active }: { layout: Layout; active?: boolean }) {
  const f = computeFrames({ id: "g", layout, title: "", blocks: [] })
  return (
    <div className={cn("relative aspect-video w-full rounded-sm border bg-background", active ? "border-primary" : "border-border")} aria-hidden>
      <div className="absolute rounded-[1px] bg-muted-foreground/50" style={{ left: `${f.title.x}%`, top: `${f.title.y}%`, width: `${f.title.w * (f.cover ? 0.7 : 0.6)}%`, height: "6%" }} />
      {Object.entries(f.zones).map(([k, z]) => (
        <div key={k} className="absolute rounded-[1px] border border-primary/60 bg-primary/15" style={{ left: `${z.x}%`, top: `${z.y}%`, width: `${z.w}%`, height: `${z.h}%` }} />
      ))}
    </div>
  )
}

export function LayoutGallery({ current, onPick }: { current?: Layout; onPick: (l: Layout) => void }) {
  return (
    <div className="grid grid-cols-3 gap-2" role="listbox" aria-label="Slide layouts">
      {LAYOUT_ORDER.map((l) => (
        <button key={l} type="button" role="option" aria-selected={current === l} onClick={() => onPick(l)} className={cn("rounded-md border p-1.5 text-center text-[11px] transition-colors hover:border-primary/60", current === l ? "border-primary bg-primary/10" : "border-border")}>
          <LayoutGlyph layout={l} active={current === l} />
          <span className="mt-1 block text-foreground">{LAYOUT_LABELS[l]}</span>
        </button>
      ))}
    </div>
  )
}

function LazyThumb({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === "undefined") return setShown(true)
    const io = new IntersectionObserver((es) => es.forEach((e) => setShown(e.isIntersecting)), { rootMargin: "300px" })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <div ref={ref} className="aspect-video w-full overflow-hidden rounded-sm bg-muted/40">
      {shown ? children : null}
    </div>
  )
}

export function SlideRail({
  doc,
  theme,
  states,
  data,
  currentId,
  readOnly,
  onSelect,
  onMove,
  onDuplicate,
  onDelete,
  onAdd,
}: {
  doc: DeckDoc
  theme: Theme
  states: Record<string, QState>
  data: DataMap
  currentId: string
  readOnly: boolean
  onSelect: (id: string) => void
  onMove: (from: number, to: number) => void
  onDuplicate: (id: string) => void
  onDelete: (id: string) => void
  onAdd: (layout: Layout) => void
}) {
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [overIdx, setOverIdx] = useState<number | null>(null)
  const [gallery, setGallery] = useState(false)
  const listRef = useRef<HTMLOListElement>(null)

  function onKey(e: React.KeyboardEvent, i: number, s: Slide) {
    if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown") && !readOnly) {
      e.preventDefault()
      const to = e.key === "ArrowUp" ? i - 1 : i + 1
      onMove(i, to)
      requestAnimationFrame(() => listRef.current?.querySelector<HTMLElement>(`[data-rail-id="${s.id}"]`)?.focus())
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault()
      const n = doc.slides[i + (e.key === "ArrowDown" ? 1 : -1)]
      if (n) {
        onSelect(n.id)
        requestAnimationFrame(() => listRef.current?.querySelector<HTMLElement>(`[data-rail-id="${n.id}"]`)?.focus())
      }
    } else if ((e.key === "Delete" || e.key === "Backspace") && !readOnly && doc.slides.length > 1) {
      e.preventDefault()
      onDelete(s.id)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ol ref={listRef} className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2" aria-label="Slides">
        {doc.slides.map((s, i) => (
          <li
            key={s.id}
            draggable={!readOnly}
            onDragStart={(e) => {
              setDragIdx(i)
              e.dataTransfer.effectAllowed = "move"
              e.dataTransfer.setData("text/plain", `slide:${i}`)
            }}
            onDragOver={(e) => {
              if (dragIdx !== null) {
                e.preventDefault()
                setOverIdx(i)
              }
            }}
            onDragEnd={() => {
              setDragIdx(null)
              setOverIdx(null)
            }}
            onDrop={(e) => {
              e.preventDefault()
              if (dragIdx !== null && dragIdx !== i) onMove(dragIdx, i)
              setDragIdx(null)
              setOverIdx(null)
            }}
            className={cn("group relative", overIdx === i && dragIdx !== null && dragIdx !== i && "before:absolute before:-top-1.5 before:left-0 before:right-0 before:h-0.5 before:bg-primary")}
          >
            <button
              type="button"
              data-rail-id={s.id}
              onClick={() => onSelect(s.id)}
              onKeyDown={(e) => onKey(e, i, s)}
              aria-current={s.id === currentId}
              aria-label={`Slide ${i + 1}: ${s.title || "Untitled"}. Alt plus arrow keys to reorder.`}
              className={cn("flex w-full items-start gap-1.5 rounded-md border p-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-primary/60", s.id === currentId ? "border-primary bg-primary/10" : "border-transparent hover:border-border")}
            >
              <span className="w-4 pt-1 text-right text-[10px] text-muted-foreground">{i + 1}</span>
              <div className="min-w-0 flex-1 overflow-hidden rounded border border-border/70">
                <LazyThumb>
                  <SlideRenderer slide={s} index={i} total={doc.slides.length} theme={theme} states={states} data={data} mode="thumb" />
                </LazyThumb>
              </div>
            </button>
            {!readOnly && (
              <div className="absolute right-1.5 top-1 hidden gap-0.5 rounded bg-card/90 p-0.5 shadow group-focus-within:flex group-hover:flex">
                <button type="button" aria-label={`Duplicate slide ${i + 1}`} title="Duplicate" onClick={() => onDuplicate(s.id)} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground">
                  <Copy className="h-3 w-3" />
                </button>
                <button type="button" aria-label={`Delete slide ${i + 1}`} title="Delete" disabled={doc.slides.length <= 1} onClick={() => onDelete(s.id)} className="rounded p-1 text-muted-foreground hover:bg-red-500/10 hover:text-red-400 disabled:opacity-30">
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            )}
          </li>
        ))}
      </ol>
      {!readOnly && (
        <div className="relative border-t border-border p-2">
          <button type="button" onClick={() => setGallery((g) => !g)} aria-expanded={gallery} className="flex w-full items-center justify-center gap-1.5 rounded-md border border-dashed border-border py-1.5 text-xs text-muted-foreground hover:border-primary/60 hover:text-foreground">
            <Plus className="h-3.5 w-3.5" /> Add slide
          </button>
          {gallery && (
            <div className="absolute bottom-full left-2 z-30 mb-1 w-[300px] rounded-lg border border-border bg-card p-3 shadow-2xl">
              <div className="mb-2 text-xs font-semibold text-foreground">Choose a layout</div>
              <LayoutGallery
                onPick={(l) => {
                  setGallery(false)
                  onAdd(l)
                }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
