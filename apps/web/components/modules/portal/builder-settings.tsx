"use client"

import { useState } from "react"
import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { PortalBlock, PortalDesignDraft } from "@/lib/portal-api"

const input = "mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-cyan-500"
export const sectionTemplates: Record<string, PortalBlock> = {
  hero: { type: "hero", heading: "Your headline", subheading: "Tell visitors about your offer.", cta_label: "Enquire now", cta_url: "#enquiry" },
  text: { type: "text", heading: "About your offer", body: "Add your copy here." },
  features: { type: "features", heading: "Why choose us", items: [{ title: "Your first benefit", body: "Explain what makes your offer useful." }] },
  pricing: { type: "pricing", heading: "Choose your plan", items: [{ title: "Plan name", price: "", body: "Add your actual plan details and price." }] },
  faq: { type: "faq", heading: "Your questions, answered", items: [{ title: "Add a question", body: "Add your answer." }] },
  cta: { type: "cta", heading: "Ready to get started?", body: "Get in touch to find out more.", cta_label: "Send an enquiry", cta_url: "#enquiry" },
  gallery: { type: "gallery", images: [] },
}
export function AddSection({ onAdd, disabled }: { onAdd: (block: PortalBlock) => void; disabled: boolean }) {
  const [type, setType] = useState("text")
  return <div className="flex flex-wrap items-center gap-2"><label className="sr-only" htmlFor="new-section-type">Section type</label>
    <select id="new-section-type" value={type} disabled={disabled} onChange={(e) => setType(e.target.value)} className="h-9 rounded-md border border-border bg-background px-3 text-sm">{Object.keys(sectionTemplates).map((key) => <option key={key} value={key}>{key.charAt(0).toUpperCase() + key.slice(1)}</option>)}</select>
    <Button variant="outline" size="sm" disabled={disabled} onClick={() => onAdd(structuredClone(sectionTemplates[type]))}><Plus className="mr-2 h-3.5 w-3.5" />Add section</Button></div>
}
export function BuilderSettings({ draft, slug, fixedSlug, selected, onChange, onSlug, disabled }: {
  draft: PortalDesignDraft; slug: string; fixedSlug: boolean; selected: number | null; onChange: (draft: PortalDesignDraft) => void; onSlug: (slug: string) => void; disabled: boolean
}) {
  const block = selected === null ? null : draft.blocks[selected]
  const patchBlock = (patch: Partial<PortalBlock>) => onChange({ ...draft, blocks: draft.blocks.map((b, i) => i === selected ? { ...b, ...patch } : b) })
  return <fieldset disabled={disabled} className="space-y-5 p-4 disabled:opacity-60">
    {block && <div className="space-y-4 border-b border-border pb-5">
      <h4 className="text-sm font-semibold">Section {selected! + 1}: {block.type}</h4>
      <p className="text-xs text-muted-foreground">Edit copy directly in the preview. Use these controls for images, links and cards.</p>
      {block.type !== "gallery" && <label className="block text-xs text-muted-foreground">Heading<input className={input} value={String(block.heading || "")} maxLength={500} onChange={(e) => patchBlock({ heading: e.target.value })} /></label>}
      {block.type === "hero" && <label className="block text-xs text-muted-foreground">Hero image URL<input type="url" className={input} value={String(block.image || "")} placeholder="https://…" onChange={(e) => patchBlock({ image: e.target.value })} /></label>}
      {block.type === "gallery" && <label className="block text-xs text-muted-foreground">Images (one URL per line)<textarea rows={5} className={input} value={(block.images || []).map((i) => i.src).join("\n")} onChange={(e) => patchBlock({ images: e.target.value.split("\n").filter(Boolean).slice(0, 12).map((src, i) => ({ src, alt: block.images?.[i]?.alt || "" })) })} /></label>}
      {["hero", "cta", "features", "pricing"].includes(block.type) && <><label className="block text-xs text-muted-foreground">Button text<input className={input} value={String(block.cta_label || "")} maxLength={100} onChange={(e) => patchBlock({ cta_label: e.target.value })} /></label><label className="block text-xs text-muted-foreground">Button destination<input className={input} value={String(block.cta_url || "#enquiry")} placeholder="#enquiry or https://…" onChange={(e) => patchBlock({ cta_url: e.target.value })} /></label></>}
      {["features", "pricing", "faq"].includes(block.type) && <div className="space-y-2">
        <Button variant="outline" size="sm" disabled={(Array.isArray(block.items) ? block.items.length : 0) >= 12} onClick={() => patchBlock({ items: [...(Array.isArray(block.items) ? block.items : []), { title: "New item", body: "Add details.", price: "" }] })}>Add {block.type === "faq" ? "question" : "card"}</Button>
        {(Array.isArray(block.items) ? block.items : []).map((item, i) => <div key={i} className="flex items-center justify-between gap-2 text-xs"><span className="truncate">{String(item.title || `Item ${i + 1}`)}</span><Button variant="ghost" size="sm" onClick={() => patchBlock({ items: (block.items as unknown[]).filter((_, j) => i !== j) })}>Remove</Button></div>)}
      </div>}
    </div>}
    <h4 className="text-sm font-semibold">Page settings</h4>
    <label className="block text-xs text-muted-foreground">Page title<input className={input} value={draft.title} maxLength={200} onChange={(e) => onChange({ ...draft, title: e.target.value })} /></label>
    <label className="block text-xs text-muted-foreground">Page address<input className={input} value={slug} disabled={fixedSlug || disabled} maxLength={100} placeholder="your-landing-page" onChange={(e) => onSlug(e.target.value.toLowerCase())} /><span className="mt-1 block break-all text-xs">/portal/{slug || "your-landing-page"}{fixedSlug && " · Fixed after the first save"}</span></label>
    <label className="block text-xs text-muted-foreground">Search description<textarea rows={3} className={input} value={draft.description} maxLength={500} onChange={(e) => onChange({ ...draft, description: e.target.value })} /></label>
    <div className="grid grid-cols-2 gap-3">
      <label className="block text-xs text-muted-foreground">Appearance<select className={input} value={String(draft.theme.appearance || "light")} onChange={(e) => onChange({ ...draft, theme: { ...draft.theme, appearance: e.target.value } })}><option value="light">Light</option><option value="dark">Dark</option></select></label>
      <label className="block text-xs text-muted-foreground">Accent<select className={input} value={String(draft.theme.accent || "cyan")} onChange={(e) => onChange({ ...draft, theme: { ...draft.theme, accent: e.target.value } })}>{["cyan", "blue", "emerald", "orange"].map((accent) => <option value={accent} key={accent}>{accent}</option>)}</select></label>
    </div>
  </fieldset>
}
