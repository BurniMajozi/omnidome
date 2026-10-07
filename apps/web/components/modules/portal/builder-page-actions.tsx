"use client"

import { useState } from "react"
import { MoreHorizontal } from "lucide-react"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { deletePortalPage, unpublishPortalPage, type PortalPageSummary } from "@/lib/portal-api"

export function BuilderPageActions({ page, onChanged }: { page: PortalPageSummary; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  async function action(kind: "delete" | "unpublish") {
    if (!window.confirm(kind === "delete" ? `Delete “${page.title}”? This cannot be undone.` : `Take “${page.title}” offline? You can publish it again later.`)) return
    setBusy(true); setError("")
    const result = kind === "delete" ? await deletePortalPage(page.id) : await unpublishPortalPage(page.id)
    setBusy(false)
    if (!result.ok) { setError(result.message); return }
    onChanged()
  }
  return <div className="flex flex-col items-end gap-1"><DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon" disabled={busy} aria-label={`More actions for ${page.title}`}><MoreHorizontal className="h-4 w-4" /></Button></DropdownMenuTrigger><DropdownMenuContent align="end">{page.status === "published" && <DropdownMenuItem onSelect={() => void action("unpublish")}>Unpublish</DropdownMenuItem>}<DropdownMenuItem className="text-destructive" onSelect={() => void action("delete")}>Delete page</DropdownMenuItem></DropdownMenuContent></DropdownMenu>{error && <p role="alert" className="max-w-xs text-xs text-destructive">{error}</p>}</div>
}
