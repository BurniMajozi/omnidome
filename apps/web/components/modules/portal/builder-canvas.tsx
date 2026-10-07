"use client"

import { useEffect, useRef } from "react"
import { ArrowDown, ArrowUp, MousePointer2, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { PortalBlock } from "@/lib/portal-api"
import { PortalBlockView, pageThemeClass } from "./portal-blocks"

function EditableText({ value, field, className, onChange }: { value: string; field: string; className: string; onChange: (value: string) => void }) {
  const ref = useRef<HTMLSpanElement>(null)
  useEffect(() => { if (ref.current && document.activeElement !== ref.current) ref.current.textContent = value }, [value])
  return <span ref={ref} role="textbox" aria-label={`Edit ${field.replaceAll(".", " ")}`} aria-multiline="true" contentEditable suppressContentEditableWarning
    className={`${className} min-h-6 rounded-sm outline-none focus:ring-2 focus:ring-cyan-500 empty:before:content-['Add_text'] empty:before:opacity-40`}
    onBlur={(e) => { const updated = e.currentTarget.textContent || ""; if (updated !== value) onChange(updated) }}
    onPaste={(e) => { e.preventDefault(); const selection = window.getSelection(); if (!selection?.rangeCount) return; const range = selection.getRangeAt(0); range.deleteContents(); const node = document.createTextNode(e.clipboardData.getData("text/plain")); range.insertNode(node); range.setStartAfter(node); range.collapse(true); selection.removeAllRanges(); selection.addRange(range) }} />
}
export function BuilderCanvas({ blocks, theme, selected, onSelect, onField, onMove, onRemove, mobile, disabled }: {
  blocks: PortalBlock[]; theme: Record<string, unknown>; selected: number | null; onSelect: (index: number) => void
  onField: (index: number, field: string, value: string) => void; onMove: (index: number, direction: -1 | 1) => void
  onRemove: (index: number) => void; mobile: boolean; disabled: boolean
}) {
  return <div className="min-w-0 space-y-3">
    <p className="flex items-center gap-2 text-xs text-muted-foreground"><MousePointer2 className="h-3.5 w-3.5" />Select a section, then click its text to edit. Changes stay in your draft.</p>
    <div className={`mx-auto w-full overflow-hidden rounded-lg border border-border shadow-sm ${pageThemeClass(theme)} ${mobile ? "max-w-sm" : ""}`}>
      {blocks.map((block, index) => <div key={index} className={`relative ${selected === index ? "ring-2 ring-inset ring-cyan-500" : "hover:ring-1 hover:ring-inset hover:ring-cyan-500/60"}`}
        onClick={(e) => { if ((e.target as HTMLElement).closest("a")) e.preventDefault(); if (!disabled) onSelect(index) }}>
        <div className={`flex items-center justify-between gap-2 px-3 py-2 ${selected === index ? "bg-cyan-500/10" : ""}`}>
          <button type="button" disabled={disabled} aria-pressed={selected === index} className="rounded px-2 py-1 text-xs font-medium outline-none focus:ring-2 focus:ring-cyan-500" onClick={() => onSelect(index)}>{index + 1}. {block.type === "hero" ? "Hero" : block.type.charAt(0).toUpperCase() + block.type.slice(1)}</button>
          {selected === index && <div className="flex gap-1">
            <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Move section up" disabled={disabled || index === 0} onClick={(e) => { e.stopPropagation(); onMove(index, -1) }}><ArrowUp className="h-3.5 w-3.5" /></Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Move section down" disabled={disabled || index === blocks.length - 1} onClick={(e) => { e.stopPropagation(); onMove(index, 1) }}><ArrowDown className="h-3.5 w-3.5" /></Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Remove section" disabled={disabled} onClick={(e) => { e.stopPropagation(); onRemove(index) }}><Trash2 className="h-3.5 w-3.5" /></Button>
          </div>}
        </div>
        <PortalBlockView block={block} compact={mobile} theme={theme} renderText={selected === index && !disabled ? (field, value, className) => <EditableText field={field} value={value} className={className} onChange={(value) => onField(index, field, value)} /> : undefined} />
      </div>)}
      <section id="enquiry" className="space-y-4 border-t border-slate-400/20 px-6 py-8">
        <h3 className="text-xl font-semibold">Send an enquiry</h3>
        <div className="grid gap-3 sm:grid-cols-2">{["Name", "Email"].map((label) => <div key={label} className="rounded border border-slate-400/30 p-3 text-sm opacity-60">{label}</div>)}</div>
        <div className="rounded border border-slate-400/30 p-3 text-sm opacity-60">How can we help?</div>
        <p className="text-xs opacity-60">Your published page includes the enquiry form and consent checkbox.</p>
      </section>
    </div>
  </div>
}
