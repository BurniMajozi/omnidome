"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Globe,
  Radio,
  Plus,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  MessageSquare,
  ShieldAlert,
  Flame,
  TrendingDown,
  ArrowUpRight,
  Check,
  Mail,
  Receipt,
  HeartCrack,
  Sparkles,
} from "lucide-react"
import { NoDataYet } from "@/components/ui/not-connected"
import type { CustomerComplaintEvent } from "@/app/api/service/complaints/route"

export function ServiceComplaintsRadar() {
  const [complaints, setComplaints] = useState<CustomerComplaintEvent[]>([])
  const [trackedUrls, setTrackedUrls] = useState<any[]>([])
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // Add URL Modal
  const [addUrlModalOpen, setAddUrlModalOpen] = useState(false)
  const [newUrl, setNewUrl] = useState("")
  const [newLabel, setNewLabel] = useState("")
  const [newPlatform, setNewPlatform] = useState<CustomerComplaintEvent["source"]>("HelloPeter")
  const [isCrawling, setIsCrawling] = useState(false)

  const fetchComplaints = async () => {
    try {
      setLoading(true)
      const res = await fetch("/api/service/complaints", { cache: "no-store", signal: AbortSignal.timeout(10_000) })
      if (res.ok) {
        const json = await res.json()
        setComplaints(json.complaints || [])
        setTrackedUrls(json.trackedUrls || [])
        setStats(json.stats || null)
      }
    } catch (err) {
      console.error("Failed to fetch complaints radar:", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchComplaints()
  }, [])

  const handleAddUrl = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newUrl) return
    setIsCrawling(true)
    try {
      const res = await fetch("/api/service/complaints", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "ADD_URL",
          url: newUrl,
          label: newLabel || newUrl,
          platform: newPlatform,
        }),
      })
      if (res.ok) {
        setToastMessage(`Source saved: ${newLabel || newUrl}. No crawler is connected yet, so nothing has been ingested.`)
        setAddUrlModalOpen(false)
        setNewUrl("")
        setNewLabel("")
        fetchComplaints()
        setTimeout(() => setToastMessage(null), 4000)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setIsCrawling(false)
    }
  }

  const handleResolve = async (id: string, title: string) => {
    try {
      const res = await fetch("/api/service/complaints", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "RESOLVE_COMPLAINT", id }),
      })
      if (res.ok) {
        setToastMessage(`Marked escalation as resolved: "${title.slice(0, 32)}..."`)
        fetchComplaints()
        setTimeout(() => setToastMessage(null), 3000)
      }
    } catch (err) {
      console.error(err)
    }
  }

  const getSourceIcon = (source: CustomerComplaintEvent["source"]) => {
    switch (source) {
      case "HelloPeter":
        return <Flame className="h-4 w-4 text-orange-400" />
      case "DownDetector":
        return <Radio className="h-4 w-4 text-red-400" />
      case "X / Twitter":
      case "Facebook":
        return <MessageSquare className="h-4 w-4 text-blue-400" />
      case "Regulatory Inbox (ICASA)":
        return <ShieldAlert className="h-4 w-4 text-amber-400" />
      case "Refund Request":
        return <Receipt className="h-4 w-4 text-emerald-400" />
      case "Post-Call Survey":
        return <HeartCrack className="h-4 w-4 text-pink-400" />
      default:
        return <Globe className="h-4 w-4 text-cyan-400" />
    }
  }

  return (
    <div className="space-y-6">
      {/* Toast Alert */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-950/95 px-4 py-3 text-sm text-emerald-200 shadow-2xl backdrop-blur animate-in fade-in">
          <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Banner Header */}
      <div className="rounded-xl border border-border bg-gradient-to-r from-card/90 via-card/70 to-red-950/20 p-5 shadow-sm">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-red-500/40 bg-red-500/10 text-red-400 shadow-sm">
              <Radio className="h-6 w-6 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-xl font-bold text-foreground">External Complaints & Sentiment Radar</h2>
                <Badge variant="outline" className="border-red-500/40 text-red-400 bg-red-500/10 text-[10px] font-semibold">
                  Crawler not connected
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5 max-w-2xl">
                Customer friction points from HelloPeter ZA, DownDetector, X/Twitter, Facebook, and ICASA regulatory inboxes. No crawler or feed is connected yet, so no complaints, sentiment scores or counts are shown; sources you add are saved for when one is.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <Button
              size="sm"
              variant="default"
              className="gap-1.5 text-xs font-semibold h-9 bg-red-600 hover:bg-red-500 text-white"
              onClick={() => setAddUrlModalOpen(true)}
            >
              <Plus className="h-4 w-4" />
              Add Source to Monitor
            </Button>

            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs h-9"
              onClick={fetchComplaints}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh Radar
            </Button>
          </div>
        </div>
      </div>

      {/* KPI Stats Bar */}
      {stats && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Card className="border-border bg-card/60">
            <CardContent className="p-4">
              <span className="text-xs font-medium text-muted-foreground">Tracked Escalations</span>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-foreground font-mono">{stats.totalTracked}</span>
                <span className="text-[11px] text-muted-foreground font-semibold">Across 4 Channels</span>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">Web, Social, Regulatory, Voice</p>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/60">
            <CardContent className="p-4">
              <span className="text-xs font-medium text-muted-foreground">Critical Urgency Alerts</span>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-red-400 font-mono">{stats.criticalUrgent}</span>
                <span className="text-[11px] text-red-400 font-semibold">SLA Breaches</span>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">Immediate manager action required</p>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/60">
            <CardContent className="p-4">
              <span className="text-xs font-medium text-muted-foreground">Average Sentiment Index</span>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-amber-400 font-mono">{stats.averageSentimentScore}</span>
                <span className="text-[11px] text-muted-foreground">(-1.0 to +1.0)</span>
              </div>
              <p className="mt-1 text-[11px] text-amber-400">Moderately negative friction</p>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/60">
            <CardContent className="p-4">
              <span className="text-xs font-medium text-muted-foreground">Unresolved Escalations</span>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-foreground font-mono">{stats.unresolvedEscalations}</span>
                <span className="text-[11px] text-cyan-400 font-semibold">In Progress</span>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">Linked to support tickets</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Monitored URLs Bar */}
      <Card className="border-border">
        <CardHeader className="pb-3 border-b border-border/60">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Globe className="h-4 w-4 text-cyan-400" />
              Monitored Sources
            </CardTitle>
            <Badge variant="outline" className="border-amber-500/40 text-amber-400 text-[10px]">
              Not crawled
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="p-4">
          {trackedUrls.length === 0 && !loading && <NoDataYet message="No sources added yet" />}
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            {trackedUrls.map((feed) => (
              <div key={feed.url} className="rounded-lg border border-border/70 bg-background/50 p-3 text-xs space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-foreground truncate max-w-[140px]">{feed.label}</span>
                  <Badge variant="outline" className="text-[9px] border-amber-500/40 text-amber-400 py-0 px-1">
                    {feed.status === "NOT_CRAWLED" ? "Not crawled" : feed.status}
                  </Badge>
                </div>
                <p className="text-[11px] font-mono text-muted-foreground truncate" title={feed.url}>
                  {feed.url}
                </p>
                <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-1 border-t border-border/40">
                  <span>Crawled: {feed.lastCrawled ?? "Never"}</span>
                  <a href={feed.url} target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline flex items-center gap-0.5">
                    View <ArrowUpRight className="h-2.5 w-2.5" />
                  </a>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* ── LIVE CUSTOMER EXPERIENCE & ESCALATION FEED ────────────────── */}
      <Card className="border-border">
        <CardHeader className="pb-3 border-b border-border/60">
          <CardTitle className="text-base flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-red-400" />
            Customer Escalation & Friction Stream
          </CardTitle>
          <CardDescription className="text-xs">
            Correlated with internal tickets and shift scheduling so managers can dispatch relevant skills immediately.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-4 space-y-3">
          {complaints.length === 0 && !loading && (
            <NoDataYet message="No complaints ingested yet: no complaint feed or crawler is connected." />
          )}
          {complaints.map((item) => (
            <div
              key={item.id}
              className={`rounded-xl border p-4 transition-all ${
                item.status === "RESOLVED"
                  ? "border-border/50 bg-background/30 opacity-60"
                  : item.urgency === "CRITICAL"
                  ? "border-red-500/60 bg-red-950/15 ring-1 ring-red-500/30"
                  : "border-border/80 bg-card/70"
              }`}
            >
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <div className="flex items-center gap-2.5 flex-wrap">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-muted/40">
                    {getSourceIcon(item.source)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-foreground text-sm">{item.source}</span>
                      <span className="text-xs text-muted-foreground">• {item.author}</span>
                      {item.location && (
                        <span className="text-xs text-muted-foreground">({item.location})</span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {/* Urgency */}
                  <Badge
                    variant="outline"
                    className={`text-[10px] font-bold ${
                      item.urgency === "CRITICAL"
                        ? "border-red-500 text-red-400 bg-red-950/40"
                        : item.urgency === "HIGH"
                        ? "border-amber-500 text-amber-400 bg-amber-950/30"
                        : "border-border text-muted-foreground"
                    }`}
                  >
                    {item.urgency}
                  </Badge>

                  {/* Sentiment */}
                  <Badge
                    variant="outline"
                    className={`text-[10px] font-mono font-semibold ${
                      item.sentimentScore < -0.7
                        ? "border-red-500 text-red-400"
                        : "border-amber-500 text-amber-400"
                    }`}
                  >
                    Sentiment: {item.sentimentScore} ({item.sentimentPolarity})
                  </Badge>

                  {/* Correlated Ticket */}
                  {item.correlatedTicketId && (
                    <Badge variant="outline" className="border-cyan-500/40 text-cyan-400 font-mono text-[10px]">
                      Ticket #{item.correlatedTicketId}
                    </Badge>
                  )}
                </div>
              </div>

              {/* Title & Description */}
              <div className="mt-3">
                <h4 className="font-semibold text-foreground text-sm">{item.title}</h4>
                <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{item.content}</p>
              </div>

              {/* Action & Correlation Bar */}
              <div className="mt-3 pt-3 border-t border-border/50 flex flex-col md:flex-row md:items-center md:justify-between gap-3 text-xs">
                <div className="flex items-center gap-2 text-cyan-300">
                  <Sparkles className="h-3.5 w-3.5 shrink-0 text-cyan-400" />
                  <span className="text-[11px]">
                    <strong>AI Recommendation:</strong> {item.suggestedAction}
                  </span>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[11px] text-muted-foreground">Team: <strong className="text-foreground">{item.assignedTeam}</strong></span>
                  {item.status !== "RESOLVED" && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs border-emerald-500/40 text-emerald-400 hover:bg-emerald-950/20"
                      onClick={() => handleResolve(item.id, item.title)}
                    >
                      <Check className="h-3 w-3 mr-1" />
                      Mark Resolved
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* ── MODAL: ADD COMPLAINT / REVIEW URL TO SCRAPE ────────────────── */}
      {addUrlModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm animate-in fade-in">
          <Card className="w-full max-w-lg border-border shadow-2xl">
            <CardHeader className="border-b border-border pb-3">
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <Globe className="h-4 w-4 text-cyan-400" />
                Add External URL to Track Customer Complaints
              </CardTitle>
              <CardDescription className="text-xs">
                Save a HelloPeter company profile, DownDetector URL, Twitter mention feed, or regulatory email inbox. It is stored as a monitored source only; no crawling happens yet.
              </CardDescription>
            </CardHeader>
            <form onSubmit={handleAddUrl}>
              <CardContent className="space-y-3 p-4 text-xs">
                <div className="space-y-1">
                  <label className="font-semibold text-muted-foreground">Platform / Channel *</label>
                  <select
                    value={newPlatform}
                    onChange={(e) => setNewPlatform(e.target.value as any)}
                    className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs"
                  >
                    <option value="HelloPeter">HelloPeter (South Africa Consumer Reviews)</option>
                    <option value="DownDetector">DownDetector ZA (Outage Reports)</option>
                    <option value="X / Twitter">X / Twitter (Brand Mentions & DMs)</option>
                    <option value="Facebook">Facebook Page Reviews & Comments</option>
                    <option value="Regulatory Inbox (ICASA)">Regulatory Inbox (ICASA / ISPA Disputes)</option>
                    <option value="Refund Request">Customer Portal (Refund Requests)</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="font-semibold text-muted-foreground">Target URL / Mailbox *</label>
                  <Input
                    value={newUrl}
                    onChange={(e) => setNewUrl(e.target.value)}
                    required
                    placeholder="e.g. https://www.hellopeter.com/omnidome-telecoms"
                    className="h-8 text-xs font-mono"
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-semibold text-muted-foreground">Display Label</label>
                  <Input
                    value={newLabel}
                    onChange={(e) => setNewLabel(e.target.value)}
                    placeholder="e.g. HelloPeter Primary Profile"
                    className="h-8 text-xs"
                  />
                </div>

                <div className="rounded-lg border border-cyan-500/30 bg-cyan-950/20 p-2.5 text-[11px] text-cyan-300 flex items-start gap-2">
                  <Sparkles className="h-4 w-4 text-cyan-400 shrink-0 mt-0.5" />
                  <span>
                    This only saves the source. Crawling, sentiment scoring and ticket matching are not connected yet.
                  </span>
                </div>
              </CardContent>

              <div className="flex justify-end gap-2 border-t border-border p-3 bg-muted/20">
                <Button type="button" variant="ghost" size="sm" onClick={() => setAddUrlModalOpen(false)}>Cancel</Button>
                <Button type="submit" variant="default" size="sm" disabled={isCrawling} className="font-semibold bg-red-600 hover:bg-red-500 text-white">
                  {isCrawling ? "Saving..." : "Save Source"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
