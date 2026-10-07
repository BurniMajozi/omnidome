"use client"

import React, { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { AlertTriangle, CheckCircle2, CloudOff, RefreshCw, Search, XCircle } from "lucide-react"
import {
  auditPortalSeo,
  lookupPortalKeywords,
  type PortalKeywordResult,
  type PortalSeoAudit,
  type PortalSeoCheck,
} from "@/lib/portal-api"
import { plainText } from "./portal-blocks"

const STATUS_STYLE: Record<PortalSeoCheck["status"], { icon: React.ReactNode; cls: string }> = {
  pass: { icon: <CheckCircle2 className="h-4 w-4 text-emerald-400" />, cls: "text-emerald-400" },
  warn: { icon: <AlertTriangle className="h-4 w-4 text-amber-400" />, cls: "text-amber-400" },
  fail: { icon: <XCircle className="h-4 w-4 text-red-400" />, cls: "text-red-400" },
}

export function DomeSeoStudio({ currentUrl = "" }: { currentUrl?: string }) {
  const [url, setUrl] = useState(currentUrl)
  const [keyword, setKeyword] = useState("")
  const [auditing, setAuditing] = useState(false)
  const [audit, setAudit] = useState<PortalSeoAudit | null>(null)
  const [auditError, setAuditError] = useState<string | null>(null)

  const [kwInput, setKwInput] = useState("")
  const [kwBusy, setKwBusy] = useState(false)
  const [kwResult, setKwResult] = useState<PortalKeywordResult | null>(null)
  const [kwError, setKwError] = useState<string | null>(null)

  const runAudit = async () => {
    if (!url.trim()) return
    setAuditing(true)
    setAuditError(null)
    setAudit(null)
    const res = await auditPortalSeo(url.trim(), keyword.trim() || undefined)
    setAuditing(false)
    if (res.ok) setAudit(res.data)
    else setAuditError(res.message)
  }

  const runKeywords = async () => {
    const list = kwInput
      .split(/[\n,]/)
      .map((k) => k.trim())
      .filter(Boolean)
      .slice(0, 50)
    if (list.length === 0) return
    setKwBusy(true)
    setKwError(null)
    setKwResult(null)
    const res = await lookupPortalKeywords(list)
    setKwBusy(false)
    if (res.ok) setKwResult(res.data)
    else setKwError(res.message)
  }

  return (
    <div className="space-y-6 text-foreground">
      <section className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-sm">
        <div>
          <h2 className="text-xl font-bold tracking-tight">On-page SEO audit</h2>
          <p className="text-xs text-muted-foreground">Fetches the public https page and scores its title, meta, headings, images, links and content. Results come from the live fetch only.</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void runAudit()} placeholder="https://example.com/page" className="h-9 flex-1 bg-background font-mono text-xs" />
          <Input value={keyword} onChange={(e) => setKeyword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void runAudit()} placeholder="Target keyword (optional)" className="h-9 bg-background text-xs sm:w-56" />
          <Button onClick={runAudit} disabled={auditing || !url.trim()} className="h-9 bg-cyan-500 text-xs font-semibold text-cyan-950 hover:bg-cyan-400">
            {auditing ? <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Search className="mr-1.5 h-3.5 w-3.5" />}
            {auditing ? "Auditing..." : "Run audit"}
          </Button>
        </div>

        {auditError && (
          <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{auditError}</span>
          </div>
        )}

        {audit && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-secondary/20 p-4">
              <div className="text-center">
                <p className="text-4xl font-bold">{audit.score}</p>
                <p className="text-[11px] text-muted-foreground">of 100</p>
              </div>
              <Badge variant="outline" className="px-3 py-1 text-lg">{audit.grade}</Badge>
              <div className="text-xs text-muted-foreground">
                <p className="break-all font-mono text-foreground">{plainText(audit.url)}</p>
                <p>
                  {audit.summary.pass} passed, {audit.summary.warn} warnings, {audit.summary.fail} failed
                </p>
              </div>
            </div>

            {audit.keyword && (
              <div className="rounded-lg border border-border bg-secondary/20 p-3 text-xs">
                <p className="mb-1 font-semibold">Keyword: {plainText(audit.keyword.keyword)}</p>
                <p className="text-muted-foreground">
                  In title: {audit.keyword.in_title ? "yes" : "no"} · In H1: {audit.keyword.in_h1 ? "yes" : "no"} · In meta description: {audit.keyword.in_meta_description ? "yes" : "no"} · Occurrences in text: {audit.keyword.occurrences_in_text} · Density: {audit.keyword.density_pct}%
                </p>
              </div>
            )}

            <ul className="divide-y divide-border/40 rounded-lg border border-border">
              {audit.checks.map((c) => (
                <li key={c.id} className="flex items-start gap-3 p-3 text-xs">
                  <span className="mt-0.5">{STATUS_STYLE[c.status].icon}</span>
                  <div className="min-w-0">
                    <p className={`font-medium ${STATUS_STYLE[c.status].cls}`}>{plainText(c.label)}</p>
                    <p className="text-muted-foreground">{plainText(c.detail)}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-sm">
        <div>
          <h2 className="text-xl font-bold tracking-tight">Keyword research</h2>
          <p className="text-xs text-muted-foreground">Volume, CPC and competition come from the configured SEO data provider. Enter one keyword per line or comma separated.</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <textarea
            value={kwInput}
            onChange={(e) => setKwInput(e.target.value)}
            rows={3}
            placeholder="fibre deals cape town"
            className="flex-1 resize-y rounded-md border border-border bg-background p-2 text-xs text-foreground focus:outline-none"
          />
          <Button onClick={runKeywords} disabled={kwBusy || !kwInput.trim()} className="h-9 bg-cyan-500 text-xs font-semibold text-cyan-950 hover:bg-cyan-400">
            {kwBusy ? "Looking up..." : "Look up keywords"}
          </Button>
        </div>

        {kwError && <p role="alert" className="text-xs text-red-400">{kwError}</p>}

        {kwResult && !kwResult.provider_configured && (
          <div role="status" className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-secondary/20 p-6 text-center">
            <CloudOff className="h-5 w-5 text-muted-foreground" />
            <p className="text-sm font-medium text-foreground">Keyword data provider not configured</p>
            <p className="max-w-md text-xs text-muted-foreground">{kwResult.message || "Set SEO_PROVIDER_API_KEY on the Portal Builder service to enable search volume, CPC and competition. No figures are shown until then."}</p>
          </div>
        )}
        {kwResult && kwResult.provider_configured && kwResult.error && <p role="alert" className="text-xs text-red-400">Provider error: {plainText(kwResult.error)}</p>}
        {kwResult && kwResult.provider_configured && !kwResult.error && (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-left text-xs">
              <thead className="bg-secondary/30 text-muted-foreground">
                <tr>
                  <th className="p-2 font-medium">Keyword</th>
                  <th className="p-2 font-medium">Search volume</th>
                  <th className="p-2 font-medium">CPC</th>
                  <th className="p-2 font-medium">Competition</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {kwResult.keywords.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="p-4 text-center text-muted-foreground">The provider returned no data for these keywords.</td>
                  </tr>
                ) : (
                  kwResult.keywords.map((k) => (
                    <tr key={k.keyword}>
                      <td className="p-2 font-medium text-foreground">{plainText(k.keyword)}</td>
                      <td className="p-2">{k.search_volume ?? "n/a"}</td>
                      <td className="p-2">{k.cpc ?? "n/a"}</td>
                      <td className="p-2">{k.competition ?? "n/a"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
