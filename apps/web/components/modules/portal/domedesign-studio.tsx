"use client"

import { useEffect, useRef, useState } from "react"
import { ArrowLeft, Download, ExternalLink, FolderOpen, Globe, MessageSquare, Monitor, Plus, RotateCcw, Save, Settings2, Share2, Smartphone, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NotConnected } from "@/components/ui/not-connected"
import type { PortalPageSummary } from "@/lib/portal-api"
import type { Loadable } from "@/lib/service-state"
import { ExistingSiteImporterModal } from "./existing-site-importer-modal"
import { DomeStudioShareModal } from "./domestudio-share-modal"
import { BuilderPrompt, BuilderChat, starterPrompts } from "./builder-chat"
import { BuilderCanvas } from "./builder-canvas"
import { AddSection, BuilderSettings, sectionTemplates } from "./builder-settings"
import { useDesignStudio } from "./use-design-studio"
import { BuilderPageActions } from "./builder-page-actions"

interface Props { pages: Loadable<PortalPageSummary[]>; onChanged: () => void; onReload: () => void; newPageSignal?: number }
export function DomeDesignStudio({ pages, onChanged, onReload, newPageSignal = 0 }: Props) {
  const studio = useDesignStudio(onChanged)
  const [view, setView] = useState<"start" | "editor" | "pages">("start")
  const [panel, setPanel] = useState<"chat" | "settings">("chat")
  const [mobile, setMobile] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)
  const [example, setExample] = useState("")
  const [importOpen, setImportOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const [publishOpen, setPublishOpen] = useState(false)
  const previousSignal = useRef(0)
  const busy = studio.busy !== null
  const canLeave = () => !studio.dirty || window.confirm("Discard the unsaved changes to this draft?")
  const newPage = () => { if (busy || !canLeave()) return; studio.reset(); setSelected(null); setExample(""); setView("start"); setPanel("chat") }
  useEffect(() => {
    if (newPageSignal && previousSignal.current !== newPageSignal) { previousSignal.current = newPageSignal; newPage() }
  }, [newPageSignal]) // The signal is an explicit user request, not a background reset.

  const generate = async (prompt: string) => { const ok = await studio.suggest(prompt, selected ?? undefined); if (ok) { setView("editor"); setPanel("chat") }; return ok }
  const openPage = async (id: string) => { if (!canLeave()) return; if (await studio.open(id)) { setView("editor"); setSelected(null); setPanel("chat") } }
  const updateField = (index: number, field: string, value: string) => {
    const blocks = structuredClone(studio.draft.blocks)
    const parts = field.split(".")
    if (parts[0] === "items") { const items = blocks[index].items as Array<Record<string, string>>; if (items?.[Number(parts[1])]) items[Number(parts[1])][parts[2]] = value }
    else blocks[index][field] = value
    studio.change({ ...studio.draft, blocks })
  }
  const feedback = <>{studio.error && <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{studio.error}</div>}{studio.notice && <p role="status" className="text-sm text-emerald-600 dark:text-emerald-400">{studio.notice}</p>}</>
  const importer = <ExistingSiteImporterModal open={importOpen} onOpenChange={setImportOpen} onApplySiteStructure={(result) => { studio.applyImport(result); setView("editor"); setSelected(null); setPanel("chat") }} />

  if (view === "pages") return <section className="space-y-4 rounded-xl border border-border bg-card p-4 sm:p-6">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">My pages</h2><p className="text-sm text-muted-foreground">Continue a draft or make a new version of a live page.</p></div><Button disabled={busy} onClick={newPage}><Plus className="mr-2 h-4 w-4" />New landing page</Button></div>{feedback}
    {pages.state !== "ready" ? <NotConnected loadable={pages} service="Portal Builder" onRetry={onReload} /> : !pages.data.length ? <p className="py-8 text-center text-sm text-muted-foreground">Your saved pages will appear here. Start by describing your first page.</p> : <div className="divide-y divide-border rounded-lg border border-border">{pages.data.map((page) => <div key={page.id} className="flex flex-wrap items-center justify-between gap-3 p-4"><div className="min-w-0 flex-1"><p className="break-words font-medium">{page.title}</p><p className="break-all text-xs text-muted-foreground">/portal/{page.slug}</p></div><Badge variant="outline">{page.status}</Badge><Button size="sm" variant="outline" disabled={busy} onClick={() => void openPage(page.id)}>Edit page</Button>{page.status === "published" && <a aria-label={`Open ${page.title} live page`} href={`/portal/${encodeURIComponent(page.slug)}`} target="_blank" rel="noopener noreferrer" className="rounded p-2 text-muted-foreground"><ExternalLink className="h-4 w-4" /></a>}<BuilderPageActions page={page} onChanged={onChanged} /></div>)}</div>}
    <Button variant="ghost" onClick={() => setView(studio.draft.blocks.length ? "editor" : "start")}><ArrowLeft className="mr-2 h-4 w-4" />Back to builder</Button>
  </section>

  if (view === "start") return <section className="rounded-xl border border-border bg-card">
    <div className="flex justify-end border-b border-border p-3"><Button variant="ghost" size="sm" disabled={busy} onClick={() => { onReload(); setView("pages") }}><FolderOpen className="mr-2 h-4 w-4" />My pages</Button></div>
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10 sm:px-8 sm:py-16">
      <div className="space-y-3"><p className="flex items-center gap-2 text-sm font-medium text-cyan-600 dark:text-cyan-400"><Sparkles className="h-4 w-4" />DomeDesign</p><h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">What would you like to build?</h2><p className="max-w-xl text-sm leading-relaxed text-muted-foreground">Describe your landing page. We’ll turn your brief into a draft you can refine in chat or edit directly in the preview.</p></div>
      {feedback}<BuilderPrompt large initial={example} busy={busy} onSubmit={generate} />
      <div className="space-y-3"><p className="text-xs text-muted-foreground">Need a starting point?</p><div className="flex flex-wrap gap-2">{starterPrompts.map((item) => <Button key={item.title} variant="outline" size="sm" disabled={busy} onClick={() => setExample(item.prompt)}>{item.title}</Button>)}</div></div>
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-5"><Button variant="ghost" size="sm" disabled={busy} onClick={() => { studio.change({ title: "Untitled landing page", description: "", theme: { appearance: "light", accent: "cyan" }, blocks: [structuredClone(sectionTemplates.hero)] }); setView("editor"); setPanel("settings"); setSelected(0) }}><Plus className="mr-2 h-4 w-4" />Start with a blank page</Button><Button variant="ghost" size="sm" disabled={busy} onClick={() => setImportOpen(true)}><Download className="mr-2 h-4 w-4" />Use content from a website</Button></div>
    </div>{importer}
  </section>

  return <section className="min-w-0 overflow-hidden rounded-xl border border-border bg-card text-foreground">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-3 sm:p-4">
      <div className="flex min-w-0 flex-wrap items-center gap-2"><Button variant="ghost" size="sm" disabled={busy} onClick={() => { onReload(); setView("pages") }}><FolderOpen className="mr-2 h-4 w-4" />My pages</Button><h2 className="max-w-xs truncate text-sm font-semibold">{studio.draft.title || "Untitled landing page"}</h2><Badge variant="outline">{studio.status === "published" ? "Live page" : "Draft"}</Badge><span className="text-xs text-muted-foreground">{!studio.pageId ? "Not saved yet" : studio.dirty ? "Unsaved changes" : "Saved"}</span></div>
      <div className="flex flex-wrap gap-2"><Button variant="ghost" size="sm" disabled={busy || !studio.canUndo} onClick={() => { studio.undo(); setSelected(null) }}><RotateCcw className="mr-2 h-3.5 w-3.5" />Undo</Button><Button variant="outline" size="sm" title={studio.dirty || !studio.pageId ? "Save your draft before sharing" : "Share a saved preview"} disabled={busy || !studio.pageId || studio.dirty} onClick={() => setShareOpen(true)}><Share2 className="mr-2 h-3.5 w-3.5" />Share</Button><Button variant="outline" size="sm" disabled={busy} onClick={() => void studio.save()}><Save className="mr-2 h-3.5 w-3.5" />{studio.busy === "save" ? "Saving…" : "Save draft"}</Button><Button size="sm" disabled={busy || !studio.draft.blocks.length} className="bg-cyan-500 text-cyan-950 hover:bg-cyan-400" onClick={() => setPublishOpen(true)}><Globe className="mr-2 h-3.5 w-3.5" />Publish</Button></div>
    </header>
    <div className="space-y-2 px-4 py-3">{feedback}{studio.status === "published" && <p className="text-xs text-muted-foreground">You’re editing a draft of your live page. Save keeps these changes private; Publish updates the live version. <a href={`/portal/${studio.slug}`} target="_blank" rel="noopener noreferrer" className="font-medium text-cyan-600 dark:text-cyan-400">View live page ↗</a></p>}</div>
    <div className="grid min-w-0 lg:grid-cols-[340px_minmax(0,1fr)]">
      <aside className="min-w-0 border-b border-border lg:border-b-0 lg:border-r">
        <div className="flex gap-2 border-b border-border p-3"><Button variant={panel === "chat" ? "secondary" : "ghost"} size="sm" aria-pressed={panel === "chat"} onClick={() => setPanel("chat")}><MessageSquare className="mr-2 h-4 w-4" />Chat</Button><Button variant={panel === "settings" ? "secondary" : "ghost"} size="sm" aria-pressed={panel === "settings"} onClick={() => setPanel("settings")}><Settings2 className="mr-2 h-4 w-4" />Edit & settings</Button></div>
        <div className="max-h-[620px] overflow-y-auto lg:h-[620px]">{panel === "chat" ? <BuilderChat messages={studio.messages} busy={busy} selected={selected === null ? null : `${selected + 1}. ${studio.draft.blocks[selected]?.type || ""}`} onSubmit={generate} /> : <BuilderSettings draft={studio.draft} slug={studio.slug} fixedSlug={!!studio.pageId} selected={selected} onChange={studio.change} onSlug={studio.setSlug} disabled={busy} />}</div>
      </aside>
      <div className="min-w-0 bg-secondary/20 p-3 sm:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><p className="text-sm font-medium">Your landing page</p><div className="flex items-center gap-1 rounded-md border border-border bg-background p-1"><Button variant={!mobile ? "secondary" : "ghost"} size="sm" aria-pressed={!mobile} onClick={() => setMobile(false)}><Monitor className="mr-2 h-3.5 w-3.5" />Desktop</Button><Button variant={mobile ? "secondary" : "ghost"} size="sm" aria-pressed={mobile} onClick={() => setMobile(true)}><Smartphone className="mr-2 h-3.5 w-3.5" />Mobile</Button></div></div>
        <div className="max-h-[620px] overflow-y-auto p-1"><BuilderCanvas blocks={studio.draft.blocks} theme={studio.draft.theme} selected={selected} onSelect={setSelected} onField={updateField} mobile={mobile} disabled={busy}
          onMove={(i, dir) => { const blocks = [...studio.draft.blocks]; const j = i + dir; [blocks[i], blocks[j]] = [blocks[j], blocks[i]]; studio.change({ ...studio.draft, blocks }); setSelected(j) }}
          onRemove={(i) => { studio.change({ ...studio.draft, blocks: studio.draft.blocks.filter((_, index) => index !== i) }); setSelected(null) }} /></div>
        <div className="mt-4"><AddSection disabled={busy || studio.draft.blocks.length >= 24} onAdd={(block) => { studio.change({ ...studio.draft, blocks: [...studio.draft.blocks, block] }); setSelected(studio.draft.blocks.length) }} /></div>
      </div>
    </div>
    <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-3"><Button variant="ghost" size="sm" disabled={busy} onClick={newPage}><Plus className="mr-2 h-3.5 w-3.5" />New page</Button><Button variant="ghost" size="sm" disabled={busy} onClick={() => { if (canLeave()) setImportOpen(true) }}><Download className="mr-2 h-3.5 w-3.5" />Import content</Button></footer>
    {publishOpen && <div role="region" aria-label="Review publication" className="space-y-3 border-t border-border bg-secondary/40 p-5"><h3 className="font-semibold">Ready to publish?</h3><p className="break-all text-sm text-muted-foreground">{studio.status === "published" ? "This replaces the live version at" : "Your page will be available at"} /portal/{studio.slug || "your-page-address"}. Check the copy, offer details and links before publishing.</p><div className="flex gap-2"><Button disabled={busy} onClick={async () => { if (await studio.save(true)) setPublishOpen(false) }}>{studio.busy === "publish" ? "Publishing…" : "Save and publish"}</Button><Button variant="outline" disabled={busy} onClick={() => setPublishOpen(false)}>Keep editing</Button></div></div>}
    <DomeStudioShareModal open={shareOpen} onOpenChange={setShareOpen} pageId={studio.pageId} pageTitle={studio.draft.title} />{importer}
  </section>
}
