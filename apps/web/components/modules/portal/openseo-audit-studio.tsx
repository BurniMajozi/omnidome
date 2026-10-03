"use client"

import React, { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

function MetricBar({ value, color = "bg-emerald-500" }: { value: number; color?: string }) {
  return (
    <div className="h-1.5 w-full bg-secondary/80 rounded-full overflow-hidden">
      <div
        className={`h-full ${color} rounded-full transition-all duration-300`}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  )
}
import {
  Search,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Globe,
  Share2,
  Bot,
  RefreshCw,
  ExternalLink,
  Zap,
  TrendingUp,
  FileText,
  Code,
  ShieldCheck,
  Sliders,
  Check,
  ArrowRight,
  Flame,
} from "lucide-react"

interface OpenSeoProps {
  currentUrl?: string
  pageTitle?: string
}

export function OpenSeoAuditStudio({
  currentUrl = "https://connect.omnidome.io/promo/fibre-summer-sprint",
  pageTitle = "Gigabit Uncapped Fibre Deals • First Month Free | OmniDome",
}: OpenSeoProps) {
  const [targetUrl, setTargetUrl] = useState(currentUrl)
  const [metaTitle, setMetaTitle] = useState(pageTitle)
  const [metaDescription, setMetaDescription] = useState(
    "Supercharge your home or business with lightning-fast uncapped Gigabit Fibre. Zero installation fee, free Wi-Fi 6 router, and instant address feasibility verification."
  )
  const [focusKeyword, setFocusKeyword] = useState("uncapped gigabit fibre")
  const [isCrawling, setIsCrawling] = useState(false)
  const [isEvaluatingJev, setIsEvaluatingJev] = useState(false)
  const [crawlComplete, setCrawlComplete] = useState(true)

  // Simulated Jev Evaluation State
  const [jevResult, setJevResult] = useState<{
    intent: "Transactional" | "Informational" | "Navigational"
    intentConfidence: number
    ctrScore: number
    brandScore: number
    titleVerdict: string
    recommendation: string
  }>({
    intent: "Transactional",
    intentConfidence: 0.94,
    ctrScore: 0.89,
    brandScore: 0.85,
    titleVerdict: "High CTR Potential: Clear incentive, brand presence, under 60 characters.",
    recommendation: "Add geo-target ('Cape Town' or 'South Africa') in meta description to capture high-intent local queries.",
  })

  // Domecrawl Scraper Telemetry State
  const [domecrawlTelemetry, setDomecrawlTelemetry] = useState({
    status: 200,
    timeMs: 138,
    markdownLength: 2480,
    discoveredLinks: 14,
    imagesWithAlt: 6,
    imagesWithoutAlt: 0,
    canonicalMatches: true,
    jsonLdDetected: true,
  })

  const handleRunDomecrawl = () => {
    setIsCrawling(true)
    setTimeout(() => {
      setIsCrawling(false)
      setCrawlComplete(true)
      setDomecrawlTelemetry({
        status: 200,
        timeMs: Math.floor(Math.random() * 50) + 120,
        markdownLength: 2540,
        discoveredLinks: 16,
        imagesWithAlt: 7,
        imagesWithoutAlt: 0,
        canonicalMatches: true,
        jsonLdDetected: true,
      })
    }, 1200)
  }

  const handleRunJev = () => {
    setIsEvaluatingJev(true)
    setTimeout(() => {
      setIsEvaluatingJev(false)
      setJevResult({
        intent: "Transactional",
        intentConfidence: 0.96,
        ctrScore: 0.92,
        brandScore: 0.88,
        titleVerdict: "Optimal System One match: Strong commercial urgency with zero keyword stuffing.",
        recommendation: "Title tag length (56 chars) is in the top 5th percentile for SERP pixel rendering.",
      })
    }, 1000)
  }

  const titleChars = metaTitle.length
  const descChars = metaDescription.length

  return (
    <div className="space-y-6">
      {/* DomeSEO Header with Domecrawl & Jev branding */}
      <div className="rounded-xl border border-cyan-500/30 bg-gradient-to-r from-cyan-950/40 via-[#0c1322] to-[#080d18] p-5 shadow-lg">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="border-cyan-500/40 bg-cyan-950/60 text-cyan-400 text-xs font-mono">
                <Search className="h-3 w-3 mr-1" />
                DOMESEO SUITE • DOMECRAWL & JEV
              </Badge>
              <span className="text-xs text-muted-foreground">Autonomous Search Optimization</span>
            </div>
            <h3 className="text-lg font-bold text-foreground">Technical SEO & SERP Intelligence</h3>
            <p className="text-xs text-muted-foreground max-w-2xl">
              Audit DOM structure and schema via Domecrawl headless crawler, then score search intent, click-through potential,
              and CTR copy with Jev System One typed judgments.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleRunDomecrawl}
              disabled={isCrawling}
              className="text-xs border-border/80 bg-secondary/50"
            >
              <Flame className={`h-3.5 w-3.5 mr-1.5 text-amber-400 ${isCrawling ? "animate-spin" : ""}`} />
              {isCrawling ? "Crawling DOM..." : "Run Domecrawl Audit"}
            </Button>
            <Button
              size="sm"
              onClick={handleRunJev}
              disabled={isEvaluatingJev}
              className="text-xs bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold shadow-md shadow-cyan-500/20"
            >
              <Sparkles className={`h-3.5 w-3.5 mr-1.5 ${isEvaluatingJev ? "animate-spin" : ""}`} />
              {isEvaluatingJev ? "Evaluating..." : "Score with Jev AI"}
            </Button>
          </div>
        </div>

        {/* URL Target Bar */}
        <div className="mt-4 pt-3 border-t border-border/50 flex flex-col sm:flex-row items-center gap-2">
          <div className="relative flex-1 w-full">
            <Globe className="absolute left-3 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={targetUrl}
              onChange={(e) => setTargetUrl(e.target.value)}
              className="h-8 pl-8 text-xs font-mono bg-[#0b101c] border-border text-foreground"
              placeholder="https://your-domain.com/landing-page"
            />
          </div>
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <Input
              value={focusKeyword}
              onChange={(e) => setFocusKeyword(e.target.value)}
              className="h-8 text-xs font-mono bg-[#0b101c] border-border text-cyan-400 sm:w-56"
              placeholder="Focus Keyword"
            />
          </div>
        </div>
      </div>

      {/* SEO Key Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-border bg-card">
          <CardContent className="p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground font-medium">Overall SEO Score</span>
              <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 text-xs">
                Grade A
              </Badge>
            </div>
            <div className="text-2xl font-bold text-foreground">96 / 100</div>
            <MetricBar value={96} color="bg-emerald-500" />
            <p className="text-[11px] text-muted-foreground">0 critical issues detected</p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground font-medium">Jev Intent Match</span>
              <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/30 text-xs font-mono">
                {jevResult.intent}
              </Badge>
            </div>
            <div className="text-2xl font-bold text-cyan-400">
              {Math.round(jevResult.intentConfidence * 100)}%
            </div>
            <MetricBar value={jevResult.intentConfidence * 100} color="bg-cyan-500" />
            <p className="text-[11px] text-muted-foreground">High commercial purchase intent</p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground font-medium">Predicted SERP CTR</span>
              <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 text-xs">
                High
              </Badge>
            </div>
            <div className="text-2xl font-bold text-emerald-400">
              {(jevResult.ctrScore * 10).toFixed(1)} / 10
            </div>
            <MetricBar value={jevResult.ctrScore * 100} color="bg-emerald-500" />
            <p className="text-[11px] text-muted-foreground">Calculated by Jev copy heuristics</p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground font-medium">Domecrawl Scrape Speed</span>
              <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30 text-xs font-mono">
                {domecrawlTelemetry.timeMs}ms
              </Badge>
            </div>
            <div className="text-2xl font-bold text-foreground">Clean DOM</div>
            <MetricBar value={88} color="bg-amber-500" />
            <p className="text-[11px] text-muted-foreground">JSON-LD & OpenGraph valid</p>
          </CardContent>
        </Card>
      </div>

      {/* Two Column Layout: Editor & Live SERP Preview */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Meta Editor & Jev Diagnostics (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          <Card className="border-border bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Sliders className="h-4 w-4 text-cyan-400" />
                Meta Tags & Semantic Optimization
              </CardTitle>
              <CardDescription className="text-xs">
                Customize titles and descriptions with real-time length constraints and Jev AI feedback.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-xs">
              {/* Meta Title Field */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-foreground">Page Meta Title</label>
                  <span
                    className={`font-mono text-[11px] ${
                      titleChars <= 60 ? "text-emerald-400" : "text-amber-400"
                    }`}
                  >
                    {titleChars} / 60 characters
                  </span>
                </div>
                <Input
                  value={metaTitle}
                  onChange={(e) => setMetaTitle(e.target.value)}
                  className="h-8 text-xs bg-secondary/50 border-border text-foreground"
                />
              </div>

              {/* Meta Description Field */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-foreground">Meta Description</label>
                  <span
                    className={`font-mono text-[11px] ${
                      descChars <= 160 ? "text-emerald-400" : "text-amber-400"
                    }`}
                  >
                    {descChars} / 160 characters
                  </span>
                </div>
                <textarea
                  value={metaDescription}
                  onChange={(e) => setMetaDescription(e.target.value)}
                  rows={3}
                  className="w-full rounded-md border border-border bg-secondary/50 p-2.5 text-xs text-foreground focus:border-cyan-500 focus:outline-none resize-none"
                />
              </div>

              {/* Jev System One Audit Breakdown */}
              <div className="rounded-lg border border-cyan-500/30 bg-cyan-950/20 p-3.5 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-cyan-400 flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5" />
                    Jev System One Judgment
                  </span>
                  <Badge variant="outline" className="border-cyan-500/40 text-cyan-400 text-[10px]">
                    typesafe/jev-1.13
                  </Badge>
                </div>
                <p className="text-xs text-foreground">{jevResult.titleVerdict}</p>
                <div className="text-[11px] text-muted-foreground flex items-start gap-1.5 pt-1 border-t border-cyan-500/20">
                  <ArrowRight className="h-3 w-3 text-cyan-400 shrink-0 mt-0.5" />
                  <span>
                    <strong className="text-foreground">Recommendation:</strong> {jevResult.recommendation}
                  </span>
                </div>
              </div>

              {/* Domecrawl Crawler Signals */}
              <div className="rounded-lg border border-border bg-secondary/20 p-3.5 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-foreground flex items-center gap-1.5">
                    <Flame className="h-3.5 w-3.5 text-amber-400" />
                    Domecrawl Headless Inspection
                  </span>
                  <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px]">
                    200 OK • {domecrawlTelemetry.timeMs}ms
                  </Badge>
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                    <span>Structured Data (JSON-LD Offer)</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                    <span>Canonical Rel Self-Referencing</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                    <span>OpenGraph Image (1200x630)</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                    <span>Image Alt Tags ({domecrawlTelemetry.imagesWithAlt}/7)</span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Live SERP Simulation (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          <Card className="border-border bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Globe className="h-4 w-4 text-cyan-400" />
                Live Google SERP Snippet Preview
              </CardTitle>
              <CardDescription className="text-xs">
                Simulated search result rendering on Google desktop and mobile displays.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Google Result Box */}
              <div className="rounded-lg border border-border/70 bg-[#0d121f] p-4 space-y-2 shadow-inner">
                {/* SERP URL row */}
                <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  <div className="w-4 h-4 rounded-full bg-cyan-500/20 flex items-center justify-center text-[10px] text-cyan-400 font-bold">
                    OD
                  </div>
                  <span className="text-foreground">OmniDome South Africa</span>
                  <span className="text-muted-foreground">› promo › {targetUrl.split("/").pop()}</span>
                </div>

                {/* SERP Title */}
                <h4 className="text-sm md:text-base font-medium text-cyan-400 hover:underline cursor-pointer leading-tight">
                  {metaTitle}
                </h4>

                {/* SERP Snippet Description */}
                <p className="text-xs text-muted-foreground line-clamp-3 leading-relaxed">
                  {metaDescription}
                </p>

                {/* Google Sitelinks Simulation */}
                <div className="pt-2 border-t border-border/40 grid grid-cols-2 gap-2 text-xs">
                  <div className="text-cyan-400 hover:underline cursor-pointer font-medium">
                    Instant Coverage Check
                  </div>
                  <div className="text-cyan-400 hover:underline cursor-pointer font-medium">
                    Package Pricing
                  </div>
                </div>
              </div>

              {/* Social Card Share Preview (WhatsApp / LinkedIn) */}
              <div className="rounded-lg border border-border/70 bg-[#0d121f] overflow-hidden space-y-2">
                <div className="h-28 bg-gradient-to-r from-cyan-950 via-[#132238] to-[#09111c] flex items-center justify-center relative p-3">
                  <div className="text-center space-y-1">
                    <span className="text-[10px] uppercase tracking-widest text-cyan-400 font-mono">
                      OmniDome Telecom
                    </span>
                    <p className="text-xs font-bold text-white max-w-[240px] truncate">
                      {metaTitle}
                    </p>
                  </div>
                </div>
                <div className="p-3 pt-1 space-y-1">
                  <p className="text-[10px] uppercase text-muted-foreground font-mono">
                    connect.omnidome.io
                  </p>
                  <p className="text-xs font-medium text-foreground line-clamp-1">{metaTitle}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Telecom ISP Keyword Bank & Rank Tracker */}
      <Card className="border-border bg-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold flex items-center justify-between">
            <span className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-emerald-400" />
              Target Keyword Performance & SERP Positions
            </span>
            <Badge variant="outline" className="border-emerald-500/30 text-emerald-400 text-xs">
              4 Keywords Tracked
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="border-b border-border/70 text-muted-foreground">
                  <th className="pb-2 font-medium">Keyword</th>
                  <th className="pb-2 font-medium">Monthly Volume</th>
                  <th className="pb-2 font-medium">Difficulty</th>
                  <th className="pb-2 font-medium">Current SERP</th>
                  <th className="pb-2 font-medium">Search Intent (Jev)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {[
                  {
                    keyword: "fibre deals cape town",
                    vol: "6,400",
                    diff: "Medium (42)",
                    rank: "#2 Google",
                    intent: "Transactional",
                  },
                  {
                    keyword: "1000mbps uncapped ftth",
                    vol: "3,800",
                    diff: "Low (28)",
                    rank: "#1 Google",
                    intent: "Commercial",
                  },
                  {
                    keyword: "vumatel coverage check",
                    vol: "12,200",
                    diff: "High (65)",
                    rank: "#4 Google",
                    intent: "Navigational",
                  },
                  {
                    keyword: "business dedicated fibre",
                    vol: "2,100",
                    diff: "Medium (49)",
                    rank: "#3 Google",
                    intent: "Commercial",
                  },
                ].map((row) => (
                  <tr key={row.keyword} className="hover:bg-secondary/30 transition-colors">
                    <td className="py-2.5 font-medium text-foreground">{row.keyword}</td>
                    <td className="py-2.5 text-muted-foreground">{row.vol}</td>
                    <td className="py-2.5 text-muted-foreground">{row.diff}</td>
                    <td className="py-2.5 font-bold text-emerald-400">{row.rank}</td>
                    <td className="py-2.5">
                      <Badge variant="outline" className="border-cyan-500/30 text-cyan-400 text-[10px]">
                        {row.intent}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
