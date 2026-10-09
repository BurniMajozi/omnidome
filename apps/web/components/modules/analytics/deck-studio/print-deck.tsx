"use client"

import { useEffect } from "react"
import { createPortal } from "react-dom"
import type { DeckDoc } from "@/lib/bi-studio-api"
import { SlideRenderer } from "./slide-renderer"
import type { DataMap } from "./tokens"
import type { Theme } from "./theme"
import type { QState } from "./use-deck-data"

const PRINT_CSS = `
#deck-print-root { position: fixed; left: -99999px; top: 0; width: 13.333in; }
@page { size: 13.333in 7.5in; margin: 0; }
@media print {
  body > *:not(#deck-print-root) { display: none !important; }
  #deck-print-root { position: static !important; left: 0 !important; width: 13.333in !important; display: block !important; }
  .deck-print-page { width: 13.333in; height: 7.5in; page-break-after: always; break-after: page; overflow: hidden; }
  .deck-print-page:last-child { page-break-after: auto; break-after: auto; }
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
`

/**
 * Print-optimised view: every slide at 16:9, one per page. Use the browser's Save as PDF.
 * Rendered in a portal so the rest of the app is hidden by @media print.
 */
export function PrintDeck({ doc, theme, states, data, asOf, onDone }: { doc: DeckDoc; theme: Theme; states: Record<string, QState>; data: DataMap; asOf: string | null; onDone: () => void }) {
  useEffect(() => {
    // give recharts a moment to lay out at the page size, then open the print dialog
    const t = setTimeout(() => window.print(), 900)
    const after = () => onDone()
    window.addEventListener("afterprint", after)
    return () => {
      clearTimeout(t)
      window.removeEventListener("afterprint", after)
    }
  }, [onDone])
  return createPortal(
    <div id="deck-print-root" aria-hidden>
      <style>{PRINT_CSS}</style>
      {doc.slides.map((s, i) => (
        <div key={s.id} className="deck-print-page" style={{ width: "13.333in", height: "7.5in" }}>
          <SlideRenderer slide={s} index={i} total={doc.slides.length} theme={theme} states={states} data={data} asOf={asOf} mode="view" />
        </div>
      ))}
    </div>,
    document.body,
  )
}
