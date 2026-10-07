"use client"

import React, { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { NotConnected } from "@/components/ui/not-connected"
import { AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, Globe, Plus, Save, Share2, Trash2, Download } from "lucide-react"
import {
  createPortalPage,
  deletePortalPage,
  loadPortalPage,
  publishPortalPage,
  slugify,
  unpublishPortalPage,
  updatePortalPage,
  type PortalBlock,
  type PortalImportResult,
  type PortalPage,
  type PortalPageStatus,
  type PortalPageSummary,
} from "@/lib/portal-api"
import type { Loadable } from "@/lib/service-state"
import { DomeStudioShareModal } from "./domestudio-share-modal"
import { ExistingSiteImporterModal } from "./existing-site-importer-modal"
import { PortalBlocksPreview, blocksOf } from "./portal-blocks"

interface DomeDesignStudioProps {
  pages: Loadable<PortalPageSummary[]>
  /** Called after any create / save / publish / delete so the parent can refetch lists and analytics. */
  onChanged: () => void
  onReload: () => void
  /** Increment to open the editor on a blank new page. */
  newPageSignal?: number
}

const BLOCK_TEMPLATES: Record<string, PortalBlock> = {
  hero: { type: "hero", heading: "", subheading: "", image: "" },
  text: { type: "text", heading: "", body: "" },
}

export function DomeDesignStudio({ pages, onChanged, onReload, newPageSignal = 0 }: DomeDesignStudioProps) {
  const [editing, setEditing] = useState(false)
  const [pageId, setPageId] = useState<string | null>(null)
  const [title, setTitle] = useState("")
  const [slug, setSlug] = useState("")
  const [slugTouched, setSlugTouched] = useState(false)
  const [description, setDescription] = useState("")
  const [status, setStatus] = useState<PortalPageStatus>("draft")
  const [publicPath, setPublicPath] = useState<string | null>(null)
  const [blocks, setBlocks] = useState<PortalBlock[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [shareOpen, setShareOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)

  const resetEditor = useCallback(() => {
    setPageId(null)
    setTitle("")
    setSlug("")
    setSlugTouched(false)
    setDescription("")
    setStatus("draft")
    setPublicPath(null)
    setBlocks([{ ...BLOCK_TEMPLATES.hero }])
    setError(null)
    setNotice(null)
  }, [])

  useEffect(() => {
    if (newPageSignal > 0) {
      resetEditor()
      setEditing(true)
    }
  }, [newPageSignal, resetEditor])

  const applyPage = (p: PortalPage) => {
    setPageId(p.id)
    setTitle(p.title)
    setSlug(p.slug)
    setSlugTouched(true)
    setDescription(p.description ?? "")
    setStatus(p.status)
    setPublicPath(p.status === "published" ? `/portal/${p.slug}` : null)
    setBlocks(blocksOf(p.content))
  }

  const openPage = async (id: string) => {
    setBusy("open")
    setError(null)
    setNotice(null)
    const res = await loadPortalPage(id)
    setBusy(null)
    if (res.state !== "ready") {
      setError(res.state === "denied" ? "You do not have access to this page." : "Could not load the page. Try again.")
      return
    }
    applyPage(res.data)
    setEditing(true)
  }

  /** Create or update; returns the saved page, or null on failure (error already set). */
  const save = async (): Promise<PortalPage | null> => {
    setError(null)
    const content = { blocks }
    if (!pageId) {
      if (!title.trim() || !slug) {
        setError("Enter a title and a valid URL slug.")
        return null
      }
      const res = await createPortalPage({ slug, title: title.trim(), description: description.trim() || undefined, page_type: "landing", content })
      if (!res.ok) {
        setError(res.status === 409 ? "That slug is already used in your workspace. Choose another." : res.message)
        return null
      }
      applyPage(res.data)
      return res.data
    }
    const res = await updatePortalPage(pageId, { title: title.trim(), description: description.trim(), content })
    if (!res.ok) {
      setError(res.message)
      return null
    }
    applyPage(res.data)
    return res.data
  }

  const handleSave = async () => {
    setBusy("save")
    const saved = await save()
    setBusy(null)
    if (saved) {
      setNotice("Saved.")
      onChanged()
    }
  }

  const handlePublish = async () => {
    setBusy("publish")
    const saved = await save()
    if (!saved) {
      setBusy(null)
      return
    }
    const res = await publishPortalPage(saved.id)
    setBusy(null)
    if (!res.ok) {
      setError(res.status === 409 ? "Another published page already uses this slug. Change the slug and try again." : res.message)
      return
    }
    setStatus("published")
    setPublicPath(res.data.public_path || res.data.url)
    setNotice(`Published (version ${res.data.version}) at ${res.data.url}`)
    onChanged()
  }

  const handleUnpublish = async () => {
    if (!pageId) return
    setBusy("unpublish")
    const res = await unpublishPortalPage(pageId)
    setBusy(null)
    if (!res.ok) {
      setError(res.message)
      return
    }
    setStatus("draft")
    setPublicPath(null)
    setNotice("Unpublished. The page is a draft again.")
    onChanged()
  }

  const handleDelete = async () => {
    if (!pageId) return
    if (typeof window !== "undefined" && !window.confirm(`Delete "${title}"? This cannot be undone.`)) return
    setBusy("delete")
    const res = await deletePortalPage(pageId)
    setBusy(null)
    if (!res.ok) {
      setError(res.message)
      return
    }
    setEditing(false)
    resetEditor()
    onChanged()
  }

  const handleImported = (result: PortalImportResult) => {
    const imported = result.suggested_page.content.blocks ?? []
    setBlocks(imported)
    if (!title.trim()) setTitle(result.suggested_page.title.slice(0, 120))
    if (!description.trim()) setDescription(result.suggested_page.description.slice(0, 500))
    if (!pageId && !slugTouched) setSlug(slugify(result.suggested_page.title))
    setNotice("Imported content loaded. Review it, then save.")
    setEditing(true)
  }

  const updateBlock = (i: number, patch: Partial<PortalBlock>) => setBlocks((prev) => prev.map((b, idx) => (idx === i ? { ...b, ...patch } : b)))
  const moveBlock = (i: number, dir: -1 | 1) =>
    setBlocks((prev) => {
      const j = i + dir
      if (j < 0 || j >= prev.length) return prev
      const next = [...prev]
      ;[next[i], next[j]] = [next[j], next[i]]
      return next
    })

  // ---------------------------------------------------------------- hub
  if (!editing) {
    return (
      <div className="space-y-4 rounded-xl border border-border bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-base font-semibold text-foreground">Pages</h3>
            <p className="text-xs text-muted-foreground">Create, edit, share and publish landing pages stored in Portal Builder.</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => setImportOpen(true)}>
              <Download className="mr-1.5 h-3.5 w-3.5" />
              Import from website
            </Button>
            <Button
              size="sm"
              className="h-8 bg-cyan-500 text-xs font-semibold text-cyan-950 hover:bg-cyan-400"
              onClick={() => {
                resetEditor()
                setEditing(true)
              }}
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              New page
            </Button>
          </div>
        </div>

        {error && <p role="alert" className="text-xs text-red-400">{error}</p>}

        {pages.state !== "ready" ? (
          <NotConnected loadable={pages} service="Portal Builder" onRetry={onReload} />
        ) : pages.data.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-secondary/20 p-8 text-center text-xs text-muted-foreground">
            No pages yet. Create one, or import content from an existing website.
          </div>
        ) : (
          <div className="divide-y divide-border/40 rounded-lg border border-border bg-card/40">
            {pages.data.map((pg) => (
              <button
                key={pg.id}
                type="button"
                onClick={() => void openPage(pg.id)}
                disabled={busy === "open"}
                className="flex w-full items-center justify-between gap-3 p-3 text-left text-xs transition-colors hover:bg-secondary/30"
              >
                <div className="min-w-0">
                  <p className="truncate font-semibold text-foreground">{pg.title}</p>
                  <p className="font-mono text-[11px] text-muted-foreground">/portal/{pg.slug}</p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <Badge className={pg.status === "published" ? "bg-emerald-500/20 text-emerald-400" : "bg-amber-500/20 text-amber-400"}>{pg.status}</Badge>
                  <span className="text-[11px] text-muted-foreground">{pg.views} views</span>
                </div>
              </button>
            ))}
          </div>
        )}

        <ExistingSiteImporterModal open={importOpen} onOpenChange={setImportOpen} onApplySiteStructure={handleImported} />
      </div>
    )
  }

  // ------------------------------------------------------------- editor
  const slugValid = /^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$/.test(slug)
  return (
    <div className="space-y-4 rounded-xl border border-border bg-card p-5 text-foreground">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" className="h-8 text-xs text-muted-foreground" onClick={() => { setEditing(false); onReload() }}>
            ← Pages
          </Button>
          <Badge className={status === "published" ? "bg-emerald-500/20 text-emerald-400" : status === "archived" ? "bg-secondary text-muted-foreground" : "bg-amber-500/20 text-amber-400"}>{status}</Badge>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => setImportOpen(true)}>
            <Download className="mr-1.5 h-3.5 w-3.5" />
            Import
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => setShareOpen(true)}>
            <Share2 className="mr-1.5 h-3.5 w-3.5" />
            Share
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs" disabled={busy !== null} onClick={handleSave}>
            <Save className="mr-1.5 h-3.5 w-3.5" />
            {busy === "save" ? "Saving..." : "Save"}
          </Button>
          {status === "published" ? (
            <Button variant="outline" size="sm" className="h-8 text-xs" disabled={busy !== null} onClick={handleUnpublish}>
              {busy === "unpublish" ? "Unpublishing..." : "Unpublish"}
            </Button>
          ) : null}
          <Button size="sm" className="h-8 bg-cyan-500 text-xs font-semibold text-cyan-950 hover:bg-cyan-400" disabled={busy !== null} onClick={handlePublish}>
            <Globe className="mr-1.5 h-3.5 w-3.5" />
            {busy === "publish" ? "Publishing..." : status === "published" ? "Save and republish" : "Publish"}
          </Button>
          {pageId && (
            <Button variant="outline" size="sm" className="h-8 text-xs text-red-400" disabled={busy !== null} onClick={handleDelete}>
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              Delete
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {notice && (
        <div role="status" className="flex items-center gap-2 text-xs font-medium text-emerald-400">
          <CheckCircle2 className="h-3.5 w-3.5" />
          <span>{notice}</span>
        </div>
      )}
      {publicPath && <p className="font-mono text-[11px] text-muted-foreground">Public path: {publicPath}</p>}

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label className="text-xs text-muted-foreground">Title</Label>
              <Input
                value={title}
                maxLength={200}
                onChange={(e) => {
                  setTitle(e.target.value)
                  if (!pageId && !slugTouched) setSlug(slugify(e.target.value))
                }}
                className="h-9 bg-background text-xs"
              />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">URL slug {pageId ? "(fixed after creation)" : ""}</Label>
              <Input
                value={slug}
                disabled={!!pageId}
                onChange={(e) => {
                  setSlug(e.target.value.toLowerCase())
                  setSlugTouched(true)
                }}
                className="h-9 bg-background font-mono text-xs"
              />
              {!pageId && slug && !slugValid && <p className="mt-1 text-[11px] text-amber-400">Use lowercase letters, numbers and hyphens only.</p>}
            </div>
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">Description</Label>
            <Input value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} className="h-9 bg-background text-xs" />
          </div>

          <div className="space-y-3">
            {blocks.map((b, i) => (
              <div key={i} className="space-y-2 rounded-lg border border-border bg-secondary/10 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{b.type}</span>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" className="h-6 w-6" aria-label="Move up" onClick={() => moveBlock(i, -1)} disabled={i === 0}>
                      <ArrowUp className="h-3 w-3" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-6 w-6" aria-label="Move down" onClick={() => moveBlock(i, 1)} disabled={i === blocks.length - 1}>
                      <ArrowDown className="h-3 w-3" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-6 w-6 text-red-400" aria-label="Remove block" onClick={() => setBlocks((prev) => prev.filter((_, idx) => idx !== i))}>
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
                {b.type === "gallery" ? (
                  <p className="text-[11px] text-muted-foreground">{Array.isArray(b.images) ? b.images.length : 0} imported images (kept as is).</p>
                ) : (
                  <>
                    <Input placeholder="Heading" value={(b.heading as string) ?? ""} onChange={(e) => updateBlock(i, { heading: e.target.value })} className="h-8 bg-background text-xs" />
                    {b.type === "hero" ? (
                      <>
                        <Input placeholder="Subheading" value={(b.subheading as string) ?? ""} onChange={(e) => updateBlock(i, { subheading: e.target.value })} className="h-8 bg-background text-xs" />
                        <Input placeholder="Image URL (https)" value={(b.image as string) ?? ""} onChange={(e) => updateBlock(i, { image: e.target.value })} className="h-8 bg-background font-mono text-xs" />
                      </>
                    ) : (
                      <textarea
                        placeholder="Body text"
                        rows={4}
                        value={(b.body as string) ?? ""}
                        onChange={(e) => updateBlock(i, { body: e.target.value })}
                        className="w-full resize-y rounded-md border border-border bg-background p-2 text-xs text-foreground focus:outline-none"
                      />
                    )}
                  </>
                )}
              </div>
            ))}
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => setBlocks((p) => [...p, { ...BLOCK_TEMPLATES.hero }])}>
                <Plus className="mr-1 h-3 w-3" />
                Hero block
              </Button>
              <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => setBlocks((p) => [...p, { ...BLOCK_TEMPLATES.text }])}>
                <Plus className="mr-1 h-3 w-3" />
                Text block
              </Button>
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-semibold text-foreground">Preview</p>
          <div className="rounded-lg border border-border bg-background p-4">
            <PortalBlocksPreview blocks={blocks} />
          </div>
          <p className="text-[11px] text-muted-foreground">Content is sanitised by the server on save; the preview shows plain text only.</p>
        </div>
      </div>

      <DomeStudioShareModal open={shareOpen} onOpenChange={setShareOpen} pageId={pageId} pageTitle={title} />
      <ExistingSiteImporterModal open={importOpen} onOpenChange={setImportOpen} onApplySiteStructure={handleImported} />
    </div>
  )
}
