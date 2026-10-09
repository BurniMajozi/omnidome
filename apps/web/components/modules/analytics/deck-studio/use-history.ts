"use client"

import { useCallback, useRef, useState } from "react"
import type { DeckDoc } from "@/lib/bi-studio-api"

interface H {
  doc: DeckDoc | null
  past: DeckDoc[]
  future: DeckDoc[]
}
const MAX = 100

/** Undo/redo stack. Edits that share a coalesce key within 900 ms (typing, dragging a slider) become one undo step. */
export function useHistory() {
  const [h, setH] = useState<H>({ doc: null, past: [], future: [] })
  const last = useRef<{ key: string; at: number } | null>(null)

  const set = useCallback((next: DeckDoc, key?: string) => {
    const now = Date.now()
    setH((cur) => {
      if (cur.doc === next) return cur
      const merge = key && last.current && last.current.key === key && now - last.current.at < 900 && cur.past.length > 0
      last.current = key ? { key, at: now } : null
      if (merge || !cur.doc) return { doc: next, past: cur.past, future: [] }
      return { doc: next, past: [...cur.past.slice(-(MAX - 1)), cur.doc], future: [] }
    })
  }, [])
  const reset = useCallback((doc: DeckDoc | null) => {
    last.current = null
    setH({ doc, past: [], future: [] })
  }, [])
  const undo = useCallback(() => {
    last.current = null
    setH((cur) => (cur.past.length && cur.doc ? { doc: cur.past[cur.past.length - 1], past: cur.past.slice(0, -1), future: [cur.doc, ...cur.future] } : cur))
  }, [])
  const redo = useCallback(() => {
    last.current = null
    setH((cur) => (cur.future.length && cur.doc ? { doc: cur.future[0], past: [...cur.past, cur.doc], future: cur.future.slice(1) } : cur))
  }, [])
  return { doc: h.doc, set, reset, undo, redo, canUndo: h.past.length > 0, canRedo: h.future.length > 0 }
}
