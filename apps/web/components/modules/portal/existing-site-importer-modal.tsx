"use client"

import React, { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Globe, Sparkles, CheckCircle2, RefreshCw, Search, AlertTriangle } from "lucide-react"
import { importPortalSite, type PortalImportResult } from "@/lib/portal-api"
import { plainText } from "./portal-blocks"

interface ExistingSiteImporterModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Receives the real import result; the caller loads `suggested_page.content.blocks` into the editor. */
  onApplySiteStructure: (result: PortalImportResult) => void
}

export function ExistingSiteImporterModal({ open, onOpenChange, onApplySiteStructure }: ExistingSiteImporterModalProps) {
  const [targetUrl, setTargetUrl] = useState("")
  const [isCrawling, setIsCrawling] = useState(false)
  const [result, setResult] = useState<PortalImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleCrawl = async () => {
    const url = targetUrl.trim()
    if (!url) return
    setIsCrawling(true)
    setError(null)
    setResult(null)
    const res = await importPortalSite(url)
    setIsCrawling(false)
    if (res.ok) setResult(res.data)
    else setError(res.message)
  }

  const handleImport = () => {
    if (!result) return
    onApplySiteStructure(result)
    onOpenChange(false)
  }

  const blocks = result?.suggested_page.content.blocks ?? []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md border-border bg-card sm:max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="rounded-lg bg-cyan-500/20 p-2 text-cyan-400">
              <Globe className="h-5 w-5" />
            </div>
            <div>
              <DialogTitle className="text-base font-semibold text-foreground">Import an existing website</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                Fetches a public https page and extracts its headings, text and images into editable blocks. Nothing is saved until you save the page.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-muted-foreground">Website URL (https only)</Label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Globe className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  value={targetUrl}
                  onChange={(e) => setTargetUrl(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void handleCrawl()
                  }}
                  placeholder="https://example.com/page"
                  className="bg-background pl-8 font-mono text-xs"
                />
              </div>
              <Button onClick={handleCrawl} disabled={isCrawling || !targetUrl.trim()} className="h-9 bg-cyan-500 text-xs font-semibold text-cyan-950 hover:bg-cyan-400">
                {isCrawling ? (
                  <>
                    <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    Fetching...
                  </>
                ) : (
                  <>
                    <Search className="mr-1.5 h-3.5 w-3.5" />
                    Fetch
                  </>
                )}
              </Button>
            </div>
          </div>

          {error && (
            <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {result && (
            <div className="space-y-3 rounded-lg border border-border bg-secondary/20 p-3.5">
              <div className="flex items-center justify-between border-b border-border/50 pb-2">
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  <span className="text-xs font-semibold text-foreground">Fetched {plainText(result.final_url)}</span>
                </div>
                <Badge className="bg-secondary text-[10px] text-muted-foreground">
                  {result.content.stats.words} words, {result.content.stats.images} images
                </Badge>
              </div>
              <div className="space-y-1">
                <p className="text-[11px] font-medium text-muted-foreground">Title</p>
                <p className="text-xs font-semibold text-foreground">{plainText(result.suggested_page.title) || "(none found)"}</p>
                {result.suggested_page.description ? (
                  <p className="line-clamp-2 text-[11px] text-muted-foreground">{plainText(result.suggested_page.description)}</p>
                ) : null}
              </div>
              <p className="text-[11px] text-muted-foreground">
                {blocks.length} content block{blocks.length === 1 ? "" : "s"} will be loaded into the editor.
                {result.fetch.truncated ? " The page was larger than the fetch limit, so content was truncated." : ""}
              </p>
            </div>
          )}
        </div>

        <DialogFooter className="border-t border-border pt-3">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} className="text-xs">
            Cancel
          </Button>
          <Button size="sm" disabled={!result || blocks.length === 0} onClick={handleImport} className="bg-cyan-500 text-xs font-semibold text-cyan-950 hover:bg-cyan-400">
            <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            Load into editor
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
