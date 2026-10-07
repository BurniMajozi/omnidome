"use client"

import React, { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { NotConnected } from "@/components/ui/not-connected"
import { Monitor, Smartphone } from "lucide-react"
import { loadPortalPage, type PortalPage, type PortalPageSummary } from "@/lib/portal-api"
import type { Loadable } from "@/lib/service-state"
import { PortalBlocksPreview, blocksOf, plainText } from "./portal-blocks"

/**
 * Side-by-side desktop and mobile rendering of a saved page's real content.
 * Read only: editing happens in the DomeDesign editor.
 */
export function DomeStudioLiveDualView({
  pages,
  onReload,
}: {
  pages: Loadable<PortalPageSummary[]>
  onReload: () => void
}) {
  const [selectedId, setSelectedId] = useState<string>("")
  const [page, setPage] = useState<Loadable<PortalPage>>({ state: "loading" })

  const list = pages.state === "ready" ? pages.data : []
  useEffect(() => {
    if (!selectedId && list.length > 0) setSelectedId(list[0].id)
  }, [list, selectedId])

  useEffect(() => {
    if (!selectedId) return
    let cancelled = false
    setPage({ state: "loading" })
    loadPortalPage(selectedId).then((p) => {
      if (!cancelled) setPage(p)
    })
    return () => {
      cancelled = true
    }
  }, [selectedId])

  if (pages.state !== "ready") return <NotConnected loadable={pages} service="Portal Builder" onRetry={onReload} />
  if (list.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-secondary/20 p-8 text-center text-xs text-muted-foreground">
        No pages to preview. Create a page in the Website Builder first.
      </div>
    )
  }

  const summary = list.find((p) => p.id === selectedId)
  const blocks = page.state === "ready" ? blocksOf(page.data.content) : []

  return (
    <div className="space-y-4 text-foreground">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card p-4">
        <label className="text-xs text-muted-foreground" htmlFor="dual-view-page">
          Page
        </label>
        <select
          id="dual-view-page"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          className="h-9 rounded-md border border-border bg-background px-2.5 text-xs text-foreground focus:outline-none"
        >
          {list.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title} ({p.status})
            </option>
          ))}
        </select>
        {summary && (
          <span className="text-[11px] text-muted-foreground">
            {summary.views} views, {summary.conversions} conversions
          </span>
        )}
        {summary && <Badge variant="outline" className="text-[10px]">{summary.status}</Badge>}
      </div>

      {page.state !== "ready" ? (
        <NotConnected loadable={page} service="Portal Builder" onRetry={() => setSelectedId((id) => id)} />
      ) : (
        <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-12">
          <div className="space-y-2 xl:col-span-7">
            <span className="flex items-center gap-1.5 px-1 text-xs font-semibold text-foreground">
              <Monitor className="h-3.5 w-3.5 text-cyan-500" />
              Desktop
            </span>
            <div className="rounded-xl border border-border bg-background p-5 shadow-md">
              <h1 className="mb-3 text-lg font-bold text-foreground">{plainText(page.data.title)}</h1>
              <PortalBlocksPreview blocks={blocks} theme={page.data.theme} />
            </div>
          </div>
          <div className="space-y-2 xl:col-span-5">
            <span className="flex items-center gap-1.5 px-1 text-xs font-semibold text-foreground">
              <Smartphone className="h-3.5 w-3.5 text-cyan-500" />
              Mobile (375px)
            </span>
            <div className="flex justify-center rounded-xl border border-border bg-card p-4 shadow-md">
              <div className="w-[375px] max-w-full rounded-lg border border-border bg-background p-4">
                <h1 className="mb-3 text-base font-bold text-foreground">{plainText(page.data.title)}</h1>
                <PortalBlocksPreview blocks={blocks} compact theme={page.data.theme} />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
