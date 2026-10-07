"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { createPortalPage, loadPortalPage, loadPortalDesignContext, savePortalDesignContext, publishPortalPage, slugify, suggestPortalDesign, updatePortalPage, type PortalDesignDraft, type PortalImportResult, type PortalPage, type PortalPageContent, type PortalPageStatus } from "@/lib/portal-api"
import { blocksOf, plainText } from "./portal-blocks"

export type StudioMessage = { role: "user" | "assistant"; text: string }
const blank = (): PortalDesignDraft => ({ title: "", description: "", blocks: [], theme: { accent: "cyan", appearance: "light" } })
export function useDesignStudio(onChanged: () => void) {
  const [draft, setDraft] = useState(blank)
  const draftRef = useRef(draft)
  const [pageId, setPageId] = useState<string | null>(null)
  const [slug, setSlug] = useState("")
  const [status, setStatus] = useState<PortalPageStatus>("draft")
  const [sourceContent, setSourceContent] = useState<PortalPageContent>({})
  const [baseline, setBaseline] = useState(JSON.stringify(blank()))
  const [busy, setBusy] = useState<string | null>(null)
  const lock = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [messages, setMessages] = useState<StudioMessage[]>([])
  const [brief, setBrief] = useState("")
  const [generated, setGenerated] = useState(false)
  const context = { brief, messages: messages.slice(-20).map((m) => ({ ...m, text: m.text.slice(0, 4000) })), generated }
  const [contextBaseline, setContextBaseline] = useState(JSON.stringify(context))
  const [history, setHistory] = useState<PortalDesignDraft[]>([])
  const dirty = JSON.stringify(draft) !== baseline || JSON.stringify(context) !== contextBaseline
  const put = useCallback((next: PortalDesignDraft) => { draftRef.current = next; setDraft(next) }, [])
  const change = (next: PortalDesignDraft) => {
    if (JSON.stringify(next) === JSON.stringify(draftRef.current)) return
    setHistory((prev) => [...prev.slice(-24), draftRef.current]); put(next); setNotice(null)
  }
  const undo = () => { const previous = history.at(-1); if (!previous) return; put(previous); setHistory((h) => h.slice(0, -1)); setNotice("Last edit undone.") }
  const acceptPage = (page: PortalPage) => {
    const next = { title: page.title, description: page.description || "", blocks: blocksOf(page.content), theme: page.theme || { accent: "cyan", appearance: "light" } }
    put(next); setPageId(page.id); setSlug(page.slug); setStatus(page.status); setSourceContent(page.content); setBaseline(JSON.stringify(next))
  }
  const reset = () => { put(blank()); setPageId(null); setSlug(""); setStatus("draft"); setSourceContent({}); setBaseline(JSON.stringify(blank())); setHistory([]); setMessages([]); setBrief(""); setGenerated(false); setContextBaseline(JSON.stringify({ brief: "", messages: [], generated: false })); setError(null); setNotice(null) }
  const open = async (id: string) => {
    if (lock.current) return false
    lock.current = true; setBusy("open"); setError(null)
    try {
      const result = await loadPortalPage(id)
      if (result.state !== "ready") { setError(result.state === "denied" ? "You do not have access to this page." : "This page could not be loaded. Please retry."); return false }
      const saved = await loadPortalDesignContext(id)
      if (saved.state !== "ready") { setError("The page's conversation could not be loaded. Retry before editing to preserve its history."); return false }
      acceptPage(result.data); setHistory([]); setNotice(null)
      setMessages(saved.data.messages); setBrief(saved.data.brief); setGenerated(saved.data.generated)
      setContextBaseline(JSON.stringify(saved.data))
      return true
    } finally { lock.current = false; setBusy(null) }
  }
  const suggest = async (prompt: string, selected?: number) => {
    if (lock.current) return false
    lock.current = true; setBusy("design"); setError(null); setNotice(null)
    setMessages((prev) => [...prev, { role: "user", text: prompt }])
    if (!brief) setBrief(prompt)
    try {
      const current = draftRef.current
      const result = await suggestPortalDesign(prompt, current.blocks.length ? current : undefined, selected, { ...context, brief: brief || prompt })
      if (!result.ok) { setError(result.message); return false }
      change(result.data.draft)
      setGenerated(true)
      if (result.data.warnings?.length > 1) setNotice(result.data.warnings.slice(1).join("\n"))
      if (!pageId && !slug) setSlug(slugify(result.data.draft.title))
      setMessages((prev) => [...prev.slice(-18), { role: "assistant", text: plainText(result.data.message) }])
      return true
    } finally { lock.current = false; setBusy(null) }
  }
  const save = async (publish = false) => {
    if (lock.current) return false
    const current = draftRef.current
    const pageSlug = slug || slugify(current.title)
    if (!current.title.trim() || !current.blocks.length || !/^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$/.test(pageSlug)) { setError("Add a page title, at least one section, and a valid page address in Page settings."); return false }
    lock.current = true; setBusy(publish ? "publish" : "save"); setError(null); setNotice(null)
    try {
      const content = { ...sourceContent, blocks: current.blocks }
      const payload = { title: current.title.trim(), description: current.description, content, theme: current.theme }
      const result = pageId ? await updatePortalPage(pageId, payload) : await createPortalPage({ ...payload, slug: pageSlug, page_type: "landing" })
      if (!result.ok) { setError(result.status === 409 ? "That page address is already used. Choose another in Page settings." : result.message); return false }
      acceptPage(result.data); onChanged()
      const savedContext = await savePortalDesignContext(result.data.id, context)
      if (!savedContext.ok) { setContextBaseline(""); setError(`Page saved, but its conversation could not be saved: ${savedContext.message}. Retry Save draft before leaving.`); return false }
      setContextBaseline(JSON.stringify(context))
      if (!publish) { setNotice(status === "published" ? "Draft saved. Your live page has not changed; publish when ready." : "Draft saved. You can return to it from My pages."); return true }
      const publication = await publishPortalPage(result.data.id)
      if (!publication.ok) { setError(`Draft saved, but publishing failed: ${publication.message}`); return false }
      setStatus("published"); setNotice("Published. Your landing page is live."); onChanged(); return true
    } finally { lock.current = false; setBusy(null) }
  }
  const applyImport = (result: PortalImportResult) => {
    change({ ...draftRef.current, title: result.suggested_page.title.slice(0, 200), description: result.suggested_page.description.slice(0, 500), blocks: blocksOf(result.suggested_page.content) })
    if (!pageId) setSlug(slugify(result.suggested_page.title))
    setMessages((m) => [...m, { role: "assistant", text: "Imported text and images are in the preview. This is a starting draft, rather than a copy of the original site's design. Tell me how to reshape it, or edit the sections directly." }])
  }
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = "" }
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn)
  }, [dirty])
  return { draft, pageId, slug, setSlug, status, busy, error, setError, notice, messages, generated, dirty, change, undo, canUndo: history.length > 0, reset, open, suggest, save, applyImport }
}
