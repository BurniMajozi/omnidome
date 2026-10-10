"use client"

import { AlertTriangle, BookOpen } from "lucide-react"
import type { KnowledgeCardRef, KnowledgeMeta } from "@/lib/bi-studio-api"

function when(iso?: string | null): string {
  return iso ? iso.slice(0, 10) : "no date"
}

/** "Based on: ..." chips. Only cited cards count as "based on"; supplied-but-uncited cards are listed separately. */
export function KnowledgeChips({ meta, showUnused = false }: { meta: KnowledgeMeta; showUnused?: boolean }) {
  if (meta.use_knowledge === false) return null
  const used = meta.knowledge_used ?? []
  const cited = new Set(meta.knowledge_cited ?? [])
  const basedOn = used.filter((c) => cited.has(c.card_id))
  const rest = used.filter((c) => !cited.has(c.card_id))
  return (
    <div className="space-y-1 text-[11px]" data-testid="knowledge-chips">
      {meta.degraded && (
        <p className="flex gap-1 text-amber-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {meta.degraded}
        </p>
      )}
      {!meta.degraded && used.length === 0 && <p className="text-muted-foreground">Company knowledge: no relevant cards were found.</p>}
      {basedOn.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="font-semibold text-foreground">Based on:</span>
          {basedOn.map((c) => (
            <Chip key={c.card_id} card={c} />
          ))}
        </div>
      )}
      {used.length > 0 && basedOn.length === 0 && <p className="text-muted-foreground">{used.length} memory card(s) were given to the AI as background; it cited none of them.</p>}
      {showUnused && rest.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-muted-foreground">Also available:</span>
          {rest.map((c) => (
            <Chip key={c.card_id} card={c} muted />
          ))}
        </div>
      )}
    </div>
  )
}

function Chip({ card, muted }: { card: KnowledgeCardRef; muted?: boolean }) {
  return (
    <span title={`${card.card_id}${card.stale ? " (may be out of date)" : ""}`} className={`inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 ${muted ? "border-border text-muted-foreground" : "border-primary/40 bg-primary/10 text-foreground"}`}>
      <BookOpen className="h-3 w-3 shrink-0" />
      <span className="truncate">{card.title || card.card_id}</span>
      <span className="shrink-0 text-muted-foreground">
        {card.module ? `${card.module} · ` : ""}
        {when(card.as_of)}
        {card.stale ? " · stale" : ""}
      </span>
    </span>
  )
}

export function KnowledgeToggle({ id, checked, onChange, disabled }: { id: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <div className="rounded-md border border-border p-2">
      <label htmlFor={id} className="flex cursor-pointer items-start gap-2 text-xs">
        <input id={id} type="checkbox" className="mt-0.5" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
        <span>
          <span className="font-medium text-foreground">Use company knowledge (memory)</span>
          <span className="block text-muted-foreground">
            The AI gets a few relevant notes from your company memory (past customers, deals, campaigns, research) as background for the story. Numbers never come from memory: they still come only from queries on your data. Cards it relies on are cited in the speaker notes.
          </span>
        </span>
      </label>
    </div>
  )
}
