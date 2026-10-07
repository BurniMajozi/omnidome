"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { NotConnected } from "@/components/ui/not-connected"
import type { Loadable } from "@/lib/service-state"
import * as api from "@/lib/portal-api"
import { inputClass, textareaClass } from "../billing/shared"

export function PortalOperations() {
  const [pages, setPages] = useState<Loadable<api.PortalPageList>>({state: "loading"})
  const [selected, setSelected] = useState("")
  useEffect(() => { void api.loadPortalPages({pageSize: 100}).then(setPages) }, [])
  return <Tabs defaultValue="campaigns" className="space-y-4">
    <TabsList className="flex h-auto flex-wrap justify-start">
      <TabsTrigger value="campaigns">Campaigns</TabsTrigger><TabsTrigger value="seo">SEO profiles</TabsTrigger>
      <TabsTrigger value="records">Versions & submissions</TabsTrigger>
    </TabsList>
    <TabsContent value="campaigns"><Campaigns pages={pages.state === "ready" ? pages.data.items : []} /></TabsContent>
    <TabsContent value="seo"><Profiles /></TabsContent>
    <TabsContent value="records" className="space-y-4">
      {pages.state !== "ready" ? <NotConnected loadable={pages} service="Portal pages" onRetry={() => void api.loadPortalPages({pageSize: 100}).then(setPages)} /> :
        <label className="block text-sm">Page<select className={inputClass} value={selected} onChange={e => setSelected(e.target.value)}>
          <option value="">Select a page</option>{pages.data.items.map(p => <option key={p.id} value={p.id}>{p.title} ({p.status})</option>)}
        </select></label>}
      {selected && <PageRecords key={selected} id={selected} />}
    </TabsContent>
  </Tabs>
}

function Campaigns({pages}: {pages: api.PortalPageSummary[]}) {
  const [data, setData] = useState<Loadable<{items: api.PortalCampaign[]; total: number; pages: number}>>({state: "loading"})
  const [page, setPage] = useState(1)
  const [name, setName] = useState(""); const [pageId, setPageId] = useState("")
  const [budget, setBudget] = useState("0"); const [content, setContent] = useState("{}")
  const [busy, setBusy] = useState(false); const [error, setError] = useState("")
  const reload = () => api.loadPortalCampaigns(page).then(setData)
  useEffect(() => { void api.loadPortalCampaigns(page).then(setData) }, [page])
  async function run(task: () => Promise<api.PortalResult<unknown>>) {
    setBusy(true); setError("")
    try { const result = await task(); if (!result.ok) setError(result.message); else await reload() }
    catch (e) { setError(e instanceof Error ? e.message : "Campaign request failed") }
    finally { setBusy(false) }
  }
  return <div className="space-y-4">
    <p className="text-sm text-muted-foreground">Track campaign budgets and lifecycle. Launch records a running campaign; delivery is managed separately.</p>
    <form className="grid gap-3 rounded-lg border p-4 sm:grid-cols-2" onSubmit={e => {e.preventDefault(); void run(async () => {
      const parsed = JSON.parse(content)
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Content must be a JSON object")
      const result = await api.createPortalCampaign({name: name.trim(), campaign_type: "email", budget_zar: Number(budget), content: parsed, ...(pageId ? {page_id: pageId} : {})})
      if (result.ok) {setName(""); setContent("{}")}; return result
    })}}>
      <label className="text-sm">Name<input required maxLength={300} className={inputClass} value={name} onChange={e => setName(e.target.value)} /></label>
      <label className="text-sm">Budget (ZAR)<input required type="number" min="0" step="0.01" className={inputClass} value={budget} onChange={e => setBudget(e.target.value)} /></label>
      <label className="text-sm">Linked page<select className={inputClass} value={pageId} onChange={e => setPageId(e.target.value)}><option value="">No linked page</option>{pages.map(p => <option value={p.id} key={p.id}>{p.title}</option>)}</select></label>
      <label className="text-sm">Content (JSON)<textarea className={textareaClass} value={content} onChange={e => setContent(e.target.value)} /></label>
      <Button disabled={busy || !name.trim()} type="submit">Create campaign</Button>
    </form>
    {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
    {data.state !== "ready" ? <NotConnected loadable={data} service="Campaigns" onRetry={() => void reload()} /> : <>
      {data.data.items.length === 0 && <p>No campaigns on this page.</p>}
      {data.data.items.map(c => <article key={c.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4">
        <div><h3 className="font-medium">{c.name}</h3><p className="text-sm text-muted-foreground">{c.status} · Budget R{c.budget_zar.toFixed(2)} · Spent R{c.spent_zar.toFixed(2)}</p></div>
        {(c.status === "draft" || c.status === "running") && <Button disabled={busy} variant="outline" onClick={() => void run(() => api.transitionPortalCampaign(c.id, c.status === "running" ? "complete" : "launch"))}>{c.status === "running" ? "Complete" : "Launch"}</Button>}
      </article>)}
      <div className="flex items-center gap-3"><Button disabled={page === 1 || busy} onClick={() => setPage(page - 1)}>Previous</Button><span>Page {page} · {data.data.total} campaigns</span><Button disabled={page >= data.data.pages || busy} onClick={() => setPage(page + 1)}>Next</Button></div>
    </>}
  </div>
}

function Profiles() {
  const [data, setData] = useState<Loadable<api.PortalSeoProfile[]>>({state: "loading"})
  const [name, setName] = useState(""); const [keywords, setKeywords] = useState("")
  const [robots, setRobots] = useState(""); const [analytics, setAnalytics] = useState("")
  const [structured, setStructured] = useState("{}"); const [sitemap, setSitemap] = useState(true)
  const [busy, setBusy] = useState(false); const [error, setError] = useState("")
  const reload = () => api.loadPortalSeoProfiles().then(setData)
  useEffect(() => { void api.loadPortalSeoProfiles().then(setData) }, [])
  return <div className="space-y-4">
    <form className="grid gap-3 rounded-lg border p-4 sm:grid-cols-2" onSubmit={async e => {
      e.preventDefault(); setBusy(true); setError("")
      try {
        const parsed = JSON.parse(structured)
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Structured data must be a JSON object")
        const result = await api.createPortalSeoProfile({name: name.trim(), target_keywords: keywords.split(",").map(k => k.trim()).filter(Boolean), sitemap_enabled: sitemap, robots_txt: robots || null, analytics_id: analytics || null, structured_data: parsed})
        if (!result.ok) setError(result.message); else {setName(""); await reload()}
      } catch(e) {setError(e instanceof Error ? e.message : "Profile request failed")}
      finally {setBusy(false)}
    }}>
      <label className="text-sm">Profile name<input required className={inputClass} value={name} onChange={e => setName(e.target.value)} /></label>
      <label className="text-sm">Keywords (comma separated)<input className={inputClass} value={keywords} onChange={e => setKeywords(e.target.value)} /></label>
      <label className="text-sm">Analytics ID<input className={inputClass} value={analytics} onChange={e => setAnalytics(e.target.value)} /></label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={sitemap} onChange={e => setSitemap(e.target.checked)} />Enable sitemap</label>
      <label className="text-sm">Robots rules<textarea className={textareaClass} value={robots} onChange={e => setRobots(e.target.value)} /></label>
      <label className="text-sm">Structured data (JSON)<textarea className={textareaClass} value={structured} onChange={e => setStructured(e.target.value)} /></label>
      <Button disabled={busy || !name.trim()}>Create profile</Button>
    </form>
    {error && <p role="alert" className="text-red-400">{error}</p>}
    {data.state !== "ready" ? <NotConnected loadable={data} service="SEO profiles" onRetry={() => void reload()} /> : data.data.length === 0 ? <p>No SEO profiles.</p> : data.data.map(p => <article className="rounded-lg border p-4" key={p.id}><h3 className="font-medium">{p.name}</h3><p className="text-sm">{p.target_keywords.join(", ") || "No keywords"}</p><p className="text-sm text-muted-foreground">Sitemap {p.sitemap_enabled ? "enabled" : "disabled"} · {p.analytics_id || "No analytics ID"}</p>{p.robots_txt && <pre className="whitespace-pre-wrap break-words text-xs">{p.robots_txt}</pre>}</article>)}
  </div>
}

function PageRecords({id}: {id: string}) {
  const [versions, setVersions] = useState<Loadable<{published_version: number | null; items: api.PortalVersion[]}>>({state: "loading"})
  const [submissions, setSubmissions] = useState<Loadable<{items: api.PortalSubmission[]; total: number}>>({state: "loading"})
  const [page, setPage] = useState(1)
  useEffect(() => { void api.loadPortalVersions(id).then(setVersions) }, [id])
  useEffect(() => { setSubmissions({state: "loading"}); void api.loadPortalSubmissions(id, page, 20).then(setSubmissions) }, [id, page])
  return <div className="grid gap-4 lg:grid-cols-2">
    <section className="space-y-3"><h3 className="font-medium">Saved versions</h3>{versions.state !== "ready" ? <NotConnected loadable={versions} service="Versions" onRetry={() => void api.loadPortalVersions(id).then(setVersions)} /> : <>
      <p className="text-sm">Published version: {versions.data.published_version ?? "None"}</p>
      {versions.data.items.length === 0 && <p>No saved versions.</p>}
      {versions.data.items.map(v => <p key={v.id} className="rounded border p-3 text-sm">Version {v.version_number} · {v.reason} · {new Date(v.created_at).toLocaleString()}</p>)}
    </>}</section>
    <section className="space-y-3"><h3 className="font-medium">Submissions</h3>{submissions.state !== "ready" ? <NotConnected loadable={submissions} service="Submissions" onRetry={() => void api.loadPortalSubmissions(id, page, 20).then(setSubmissions)} /> : <>
      {submissions.data.items.length === 0 && <p>No submissions on this page.</p>}
      {submissions.data.items.map(s => <article className="space-y-2 rounded border p-3 text-sm" key={s.id}><p>{new Date(s.created_at).toLocaleString()} · {s.converted ? "Converted" : "New"} · Consent {s.consent_given ? "recorded" : "absent"}</p><dl>{Object.entries(s.form_data).map(([key, value]) => <div className="break-words" key={key}><dt className="font-medium">{key}</dt><dd>{String(value ?? "")}</dd></div>)}</dl></article>)}
      <div className="flex items-center gap-3"><Button disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button><span>{submissions.data.total} submissions</span><Button disabled={page * 20 >= submissions.data.total} onClick={() => setPage(page + 1)}>Next</Button></div>
    </>}</section>
  </div>
}
