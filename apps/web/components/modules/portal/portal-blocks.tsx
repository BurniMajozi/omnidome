import type { ReactNode } from "react"
import type { PortalBlock, PortalPageContent } from "@/lib/portal-api"

export function plainText(value: unknown): string {
  return typeof value === "string" ? value.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim() : ""
}
export function safeImageSrc(value: unknown): string | null {
  if (typeof value !== "string") return null
  const v = value.trim()
  return /^https?:\/\//i.test(v) || (v.startsWith("/") && !v.startsWith("//") && !v.includes("\\")) ? v : null
}
export function safeLink(value: unknown): string {
  if (typeof value !== "string") return "#enquiry"
  const v = value.trim()
  return /^(https?:\/\/|mailto:|tel:|#)/i.test(v) || (v.startsWith("/") && !v.startsWith("//") && !v.includes("\\")) ? v : "#enquiry"
}
export function blocksOf(content: PortalPageContent | null | undefined): PortalBlock[] {
  return Array.isArray(content?.blocks) ? content.blocks : []
}
export function pageThemeClass(theme?: Record<string, unknown> | null) {
  return theme?.appearance === "dark" ? "bg-slate-950 text-slate-100" : "bg-white text-slate-900"
}
const accents: Record<string, string> = {
  cyan: "bg-cyan-600 text-white", blue: "bg-blue-600 text-white",
  emerald: "bg-emerald-600 text-white", orange: "bg-orange-600 text-white",
}
type TextRenderer = (field: string, text: string, className: string) => ReactNode
export function PortalBlockView({ block: b, compact = false, theme, renderText }: {
  block: PortalBlock; compact?: boolean; theme?: Record<string, unknown> | null; renderText?: TextRenderer
}) {
  const dark = theme?.appearance === "dark"
  const muted = dark ? "text-slate-300" : "text-slate-600"
  const surface = dark ? "border-slate-700 bg-slate-900" : "border-slate-200 bg-slate-50"
  const accent = accents[String(theme?.accent)] || accents.cyan
  const text = (field: string, value: unknown, cls: string) => renderText
    ? renderText(field, plainText(value), cls) : <span className={cls}>{plainText(value)}</span>
  const cta = b.cta_label ? <a href={safeLink(b.cta_url)} className={`inline-flex max-w-full items-center justify-center rounded-md px-5 py-3 text-sm font-semibold ${accent}`}>{text("cta_label", b.cta_label, "break-words")}</a> : null
  const img = safeImageSrc(b.image)
  const padding = compact ? "px-5 py-8" : "px-6 py-10 sm:px-10 sm:py-14"
  const items = (Array.isArray(b.items) ? b.items : []) as Array<{ title?: string; body?: string; price?: string }>
  if (b.type === "gallery") return <section className={`${padding} grid grid-cols-2 gap-3`}>{(b.images || []).slice(0, 12).map((im, i) => safeImageSrc(im.src) &&
    // eslint-disable-next-line @next/next/no-img-element
    <img key={i} src={safeImageSrc(im.src)!} alt={plainText(im.alt)} loading="lazy" referrerPolicy="no-referrer" className="h-40 w-full rounded-lg object-cover" />)}</section>
  if (b.type === "hero") return <section className={`${padding} space-y-6`}>
    {img && <img src={img} alt="" loading="lazy" referrerPolicy="no-referrer" className="max-h-64 w-full rounded-lg object-cover" /> /* eslint-disable-line @next/next/no-img-element */}
    <h2 className={compact ? "text-3xl font-bold tracking-tight" : "text-4xl font-bold tracking-tight sm:text-5xl"}>{text("heading", b.heading, "block break-words")}</h2>
    <p className={`max-w-2xl text-base leading-relaxed ${muted}`}>{text("subheading", b.subheading, "block whitespace-pre-wrap")}</p>{cta}
  </section>
  if (b.type === "features" || b.type === "pricing" || b.type === "faq") return <section className={`${padding} space-y-6`}>
    <h3 className="text-2xl font-semibold tracking-tight">{text("heading", b.heading, "block break-words")}</h3>
    {b.body && <p className={`leading-relaxed ${muted}`}>{text("body", b.body, "block whitespace-pre-wrap")}</p>}
    <div className={b.type === "faq" || compact ? "grid gap-4" : "grid gap-4 sm:grid-cols-2 lg:grid-cols-3"}>
      {items.map((item, i) => <article key={i} className={`space-y-3 rounded-lg border p-5 ${surface}`}>
        <h4 className="font-semibold">{text(`items.${i}.title`, item.title, "block")}</h4>
        {b.type === "pricing" && item.price && <p className="text-2xl font-bold">{text(`items.${i}.price`, item.price, "block")}</p>}
        <p className={`text-sm leading-relaxed ${muted}`}>{text(`items.${i}.body`, item.body, "block whitespace-pre-wrap")}</p>
      </article>)}
    </div>{cta}
  </section>
  return <section className={`${padding} space-y-4 ${b.type === "cta" ? surface : ""}`}>
    <h3 className="text-2xl font-semibold tracking-tight">{text("heading", b.heading, "block break-words")}</h3>
    <p className={`leading-relaxed ${muted}`}>{text("body", b.body || b.subheading, "block whitespace-pre-wrap")}</p>{cta}
  </section>
}
export function PortalBlocksPreview({ blocks, compact = false, theme }: { blocks: PortalBlock[]; compact?: boolean; theme?: Record<string, unknown> | null }) {
  if (!blocks.length) return <div className="p-8 text-center text-sm text-muted-foreground">This page has no sections yet.</div>
  return <div className={`overflow-hidden rounded-lg ${pageThemeClass(theme)}`}>{blocks.map((block, i) => <PortalBlockView key={i} block={block} compact={compact} theme={theme} />)}</div>
}
