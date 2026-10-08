"use client"

import { useEffect, useRef, useState } from "react"
import { ExternalLink, Globe, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import {
  connectWordPress, disconnectWordPress, exportWordPressDraft, loadWordPressConnections,
  loadWordPressPublication, publishWordPressDraft, refreshWordPressPublication, testWordPressConnection,
  type WordPressConnection, type WordPressPublication,
} from "@/lib/portal-api"

const field = "mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
const labels: Record<WordPressPublication["status"], string> = {
  not_exported: "Not exported", draft_exported: "Draft exported", published: "Live on WordPress",
  external_changes: "Changed in WordPress", running: "Request in progress", uncertain: "Needs status check", failed: "Request failed",
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  pageId: string | null
  pageTitle: string
  dirty: boolean
  saving: boolean
  save: () => Promise<boolean>
}

export function WordPressPublisher({ open, onOpenChange, pageId, pageTitle, dirty, saving, save }: Props) {
  const [connections, setConnections] = useState<WordPressConnection[]>([])
  const [selected, setSelected] = useState("")
  const [publication, setPublication] = useState<WordPressPublication | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [showConnect, setShowConnect] = useState(false)
  const [siteUrl, setSiteUrl] = useState("")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [reviewed, setReviewed] = useState(false)
  const operationLock = useRef(false)
  const current = connections.find((c) => c.id === selected)
  const disabled = busy !== null || saving || loading
  const pending = publication?.status === "running" || publication?.status === "uncertain"
  const conflict = publication?.status === "external_changes"

  useEffect(() => {
    if (!open) { setPassword(""); return }
    let cancelled = false
    setLoading(true); setError(null); setReviewed(false)
    void loadWordPressConnections().then((result) => {
      if (cancelled) return
      setLoading(false)
      if (result.state !== "ready") { setError("WordPress connections could not be loaded. Close and reopen to retry."); return }
      setConnections(result.data.items)
      setSelected((old) => result.data.items.some((c) => c.id === old && c.active) ? old : result.data.items.find((c) => c.active)?.id || "")
      setShowConnect(!result.data.items.some((c) => c.active))
    })
    return () => { cancelled = true }
  }, [open])

  useEffect(() => {
    setPublication(null); setReviewed(false); setNotice(null)
    if (!open || !pageId || !selected) return
    let cancelled = false
    setLoading(true)
    void loadWordPressPublication(selected, pageId).then((result) => {
      if (cancelled) return
      setLoading(false)
      if (result.state === "ready") setPublication(result.data)
      else setError("Publication status could not be loaded. Refresh status before exporting.")
    })
    return () => { cancelled = true }
  }, [open, pageId, selected])

  useEffect(() => { if (dirty) setReviewed(false) }, [dirty])

  async function action(kind: "connect" | "test" | "disconnect" | "export" | "refresh" | "publish") {
    if (operationLock.current || saving) return
    operationLock.current = true; setBusy(kind); setError(null); setNotice(null)
    try {
      if (kind === "connect") {
        const result = await connectWordPress({ site_url: siteUrl, username, application_password: password })
        setPassword("")
        if (!result.ok) { setError(result.message); return }
        setConnections((old) => [result.data, ...old.filter((c) => c.id !== result.data.id)])
        setSelected(result.data.id); setShowConnect(false); setNotice("WordPress connected and required capabilities verified.")
      } else if (kind === "test") {
        const result = await testWordPressConnection(selected)
        if (!result.ok) { setError(result.message); return }
        setConnections((old) => old.map((c) => c.id === selected ? result.data : c)); setNotice("Connection and publishing capabilities verified.")
      } else if (kind === "disconnect") {
        const result = await disconnectWordPress(selected)
        if (!result.ok) { setError(result.message); return }
        setConnections((old) => old.map((c) => c.id === selected ? { ...c, active: false } : c))
        setSelected(""); setPublication(null); setShowConnect(true); setNotice("Disconnected. Existing WordPress pages remain available.")
      } else if (pageId) {
        const result = kind === "export" ? await exportWordPressDraft(selected, pageId)
          : kind === "publish" ? await publishWordPressDraft(selected, pageId, publication?.exported_hash || "")
          : await refreshWordPressPublication(selected, pageId)
        setReviewed(false)
        if (!result.ok) {
          setError(result.message)
          // A timeout can occur after the remote write. Require a status check.
          if (kind !== "refresh") setPublication((old) => ({ ...old, status: "uncertain", local_changes: old?.local_changes ?? false }))
          return
        }
        setPublication(result.data)
        if (result.data.error) setError(result.data.error)
        else if (kind === "export") setNotice("WordPress draft ready. Open its preview and review it before publishing.")
        else if (kind === "publish" && result.data.status === "published") setNotice("The reviewed page is live on WordPress.")
      }
    } finally { operationLock.current = false; setBusy(null) }
  }

  const canPublish = !!publication?.exported_hash && publication.status === "draft_exported" &&
    !publication.local_changes && !dirty && reviewed && !disabled && !!current?.active

  return <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next) }}>
    <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
      <DialogHeader><DialogTitle className="flex items-center gap-2"><Globe className="h-5 w-5" />WordPress publishing</DialogTitle>
        <DialogDescription>Connect your site, send a draft, then publish the version you reviewed.</DialogDescription></DialogHeader>
      {error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
      {notice && <p role="status" className="text-sm text-emerald-600 dark:text-emerald-400">{notice}</p>}
      {loading && <p role="status" className="text-sm text-muted-foreground">Loading WordPress status…</p>}
      <div className="space-y-3">
        <label className="block text-sm">Connected site<select className={field} disabled={disabled} value={selected} onChange={(e) => { setSelected(e.target.value); setError(null) }}>
          <option value="">Choose a WordPress site</option>{connections.filter((c) => c.active).map((c) => <option key={c.id} value={c.id}>{c.site_name} · {c.site_url}</option>)}</select></label>
        <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" disabled={disabled} onClick={() => setShowConnect(!showConnect)}>{showConnect ? "Hide connection form" : "Add or reconnect site"}</Button>
          {current?.active && <><Button size="sm" variant="ghost" disabled={disabled} onClick={() => void action("test")}>Test connection</Button>
            <Button size="sm" variant="ghost" disabled={disabled || pending} onClick={() => { if (window.confirm("Disconnect this site? WordPress pages will remain live. Revoke the Application Password in WordPress if it is no longer needed.")) void action("disconnect") }}>Disconnect</Button></>}
        </div>
      </div>
      {showConnect && <form className="space-y-3 rounded-lg border border-border p-4" onSubmit={(e) => { e.preventDefault(); void action("connect") }}>
        <p className="text-sm text-muted-foreground">Install MCP Adapter and the OmniDome Website Builder plugin on WordPress, then use a dedicated integration user and its Application Password. Connecting requires a portal manager role.</p>
        <fieldset disabled={disabled} className="space-y-3">
          <label className="block text-sm">WordPress site URL<input required type="url" placeholder="https://your-site.com" className={field} value={siteUrl} maxLength={1000} onChange={(e) => setSiteUrl(e.target.value)} /></label>
          <label className="block text-sm">Integration username<input required autoComplete="off" className={field} value={username} maxLength={200} onChange={(e) => setUsername(e.target.value)} /></label>
          <label className="block text-sm">Application Password<input required type="password" autoComplete="new-password" className={field} value={password} maxLength={200} onChange={(e) => setPassword(e.target.value)} /></label>
          <Button type="submit">{busy === "connect" ? "Connecting…" : "Connect and verify"}</Button>
        </fieldset>
      </form>}
      {current?.active && <section className="space-y-4 border-t border-border pt-4">
        <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-medium">{pageTitle || "Your landing page"}</h3>{publication && <Badge variant="outline">{labels[publication.status]}</Badge>}</div>
        {(!pageId || dirty) && <div className="space-y-2"><p className="text-sm text-muted-foreground">Save this draft before sending it to WordPress.</p><Button size="sm" variant="outline" disabled={disabled || !pageTitle} onClick={async () => { if (!await save()) setError("Local draft could not be saved. Close this panel and check the builder's save message.") }}>{saving ? "Saving…" : "Save local draft"}</Button></div>}
        <p className="text-sm text-muted-foreground">WordPress theme styles apply. Images stay at their source URLs. Set a working enquiry button URL; the OmniDome enquiry form and SEO plugin fields are not exported.</p>
        {publication?.local_changes && <p className="text-sm text-amber-700 dark:text-amber-300">Local changes need a new WordPress draft export and review.</p>}
        {pending && <p className="text-sm text-amber-700 dark:text-amber-300">Refresh status before retrying. A request may have completed on WordPress even if its response was lost.</p>}
        {conflict && <p className="text-sm text-amber-700 dark:text-amber-300">A managed page changed in WordPress. Resolve that change there before exporting or publishing.</p>}
        <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={disabled || !pageId || dirty || pending || conflict || !publication} onClick={() => void action("export")}>{busy === "export" ? "Sending draft…" : "Send draft to WordPress"}</Button>
          <Button variant="ghost" disabled={disabled || !pageId} onClick={() => void action("refresh")}><RefreshCw className="mr-2 h-4 w-4" />Refresh WordPress status</Button></div>
        {publication?.warnings?.map((warning) => <p key={warning} className="text-xs text-muted-foreground">{warning}</p>)}
        {publication?.preview_url && <a className="inline-flex items-center gap-2 text-sm font-medium text-cyan-600 dark:text-cyan-400" href={publication.preview_url} target="_blank" rel="noopener noreferrer"><ExternalLink className="h-4 w-4" />Open WordPress preview (WordPress login required)</a>}
        {publication?.live_url && <a className="flex items-center gap-2 break-all text-sm text-emerald-600 dark:text-emerald-400" href={publication.live_url} target="_blank" rel="noopener noreferrer"><ExternalLink className="h-4 w-4 shrink-0" />{publication.live_url}</a>}
        {publication?.status === "draft_exported" && <div className="space-y-3 rounded-lg border border-border p-4">
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={reviewed} disabled={disabled || dirty || publication.local_changes} onChange={(e) => setReviewed(e.target.checked)} /><span>I reviewed the WordPress preview, prices, coverage, offer details, and links.</span></label>
          <Button disabled={!canPublish} onClick={() => void action("publish")}>{busy === "publish" ? "Publishing…" : "Publish reviewed draft"}</Button><p className="text-xs text-muted-foreground">Publication requires a portal manager role.</p>
        </div>}
      </section>}
    </DialogContent>
  </Dialog>
}
