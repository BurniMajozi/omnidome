"use client"

import { ExternalLink, FileText } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { kindLabel, openAppPath, type ArtifactLinkItem } from "@/lib/artifact-links"

function formatUpdated(value?: string): string | null {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value.slice(0, 10) : d.toISOString().slice(0, 10)
}

/** Compact cards for existing work product found by the agent. Open navigates inside the app, same tab. */
export function ArtifactLinkCards({ items }: { items: ArtifactLinkItem[] }) {
  if (items.length === 0) return null
  return (
    <div className="my-1.5 space-y-1.5" data-testid="artifact-link-cards">
      {items.map((it) => {
        const meta = [
          it.status,
          it.version ? `v${it.version}` : null,
          formatUpdated(it.updatedAt) ? `updated ${formatUpdated(it.updatedAt)}` : null,
          it.owner ? `owner ${it.owner}` : null,
        ].filter(Boolean)
        return (
          <div key={it.href} className="flex items-center gap-2 rounded-md border border-border bg-card/80 px-3 py-2">
            <FileText className="h-4 w-4 shrink-0 text-cyan-400" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="truncate text-xs font-semibold text-foreground">{it.title}</span>
                <Badge variant="outline" className="shrink-0 px-1 py-0 text-[10px] uppercase">
                  {kindLabel(it.kind)}
                </Badge>
              </div>
              {meta.length > 0 && <p className="truncate text-[11px] text-muted-foreground">{meta.join(" · ")}</p>}
            </div>
            <Button type="button" size="sm" variant="outline" className="h-7 gap-1 px-2 text-xs" onClick={() => openAppPath(it.href)}>
              Open <ExternalLink className="h-3 w-3" />
            </Button>
          </div>
        )
      })}
    </div>
  )
}
