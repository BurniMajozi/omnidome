import type { PortalBlock, PortalPageContent } from "@/lib/portal-api"

/**
 * Backend page content is data, never markup. Everything below renders through
 * React text nodes (escaped); tags in imported strings are stripped for display
 * rather than interpreted. No dangerouslySetInnerHTML, no script, no custom_js.
 */

export function plainText(value: unknown): string {
  if (typeof value !== "string") return ""
  return value
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}

/** Only http(s) and same-origin relative image URLs are rendered. */
export function safeImageSrc(value: unknown): string | null {
  if (typeof value !== "string") return null
  const v = value.trim()
  if (/^https?:\/\//i.test(v) || (v.startsWith("/") && !v.startsWith("//"))) return v
  return null
}

export function blocksOf(content: PortalPageContent | null | undefined): PortalBlock[] {
  return Array.isArray(content?.blocks) ? (content!.blocks as PortalBlock[]) : []
}

export function PortalBlocksPreview({ blocks, compact = false }: { blocks: PortalBlock[]; compact?: boolean }) {
  if (blocks.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-secondary/20 p-6 text-center text-xs text-muted-foreground">
        This page has no content blocks yet.
      </div>
    )
  }
  return (
    <div className="space-y-4">
      {blocks.map((b, i) => {
        if (b.type === "hero") {
          const img = safeImageSrc(b.image)
          return (
            <section key={i} className="space-y-2 rounded-lg border border-border/60 bg-gradient-to-b from-cyan-950/20 to-transparent p-5">
              {img && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={img} alt="" loading="lazy" referrerPolicy="no-referrer" className="max-h-48 w-full rounded-md object-cover" />
              )}
              <h2 className={compact ? "text-lg font-bold text-foreground" : "text-2xl font-bold text-foreground"}>{plainText(b.heading)}</h2>
              {b.subheading ? <p className="text-sm text-muted-foreground">{plainText(b.subheading)}</p> : null}
            </section>
          )
        }
        if (b.type === "gallery") {
          const imgs = (Array.isArray(b.images) ? b.images : []).map((im) => ({ src: safeImageSrc(im?.src), alt: plainText(im?.alt) })).filter((im) => im.src)
          return (
            <section key={i} className="grid grid-cols-2 gap-2">
              {imgs.slice(0, 12).map((im, j) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img key={j} src={im.src as string} alt={im.alt} loading="lazy" referrerPolicy="no-referrer" className="h-28 w-full rounded-md border border-border object-cover" />
              ))}
            </section>
          )
        }
        return (
          <section key={i} className="space-y-1.5 px-1">
            {b.heading ? <h3 className="text-base font-semibold text-foreground">{plainText(b.heading)}</h3> : null}
            {b.body ? <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{plainText(b.body)}</p> : null}
          </section>
        )
      })}
    </div>
  )
}
