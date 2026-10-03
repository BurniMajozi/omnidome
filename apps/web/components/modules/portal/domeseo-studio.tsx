"use client"

import React, { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
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
  Filter,
  Download,
  CheckSquare,
  Square,
  MapPin,
  HelpCircle,
  BarChart3,
  Layers,
  ArrowUpRight,
} from "lucide-react"
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts"

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

export interface KeywordResultRow {
  keyword: string
  volume: number
  cpc: number
  comp: number
  score: number
  intent: "Comm" | "Trans" | "Info" | "Nav"
}

export interface SerpOrganicResult {
  rank: number
  title: string
  url: string
  domain: string
  snippet: string
}

const DEFAULT_KEYWORD_ROWS: KeywordResultRow[] = [
  { keyword: "uncapped fibre deals", volume: 110000, cpc: 21.79, comp: 0.02, score: 66, intent: "Comm" },
  { keyword: "fibre packages near me", volume: 90500, cpc: 18.5, comp: 0.04, score: 40, intent: "Trans" },
  { keyword: "best home fibre south africa", volume: 48000, cpc: 15.37, comp: 0.01, score: 78, intent: "Comm" },
  { keyword: "gigabit fibre internet cape town", volume: 18100, cpc: 24.46, comp: 0.05, score: 82, intent: "Trans" },
  { keyword: "vumatel coverage map", volume: 14200, cpc: 8.9, comp: 0.01, score: 64, intent: "Nav" },
  { keyword: "openserve vs vumatel speed", volume: 9900, cpc: 13.61, comp: 0.04, score: 79, intent: "Info" },
  { keyword: "frogfoot 500mbps promo", volume: 8100, cpc: 17.92, comp: 0.01, score: 82, intent: "Trans" },
  { keyword: "prepaid fibre wifi hotspot", volume: 6600, cpc: 7.86, comp: 0.48, score: 63, intent: "Comm" },
  { keyword: "unshaped gaming fibre lowest ping", volume: 5400, cpc: 15.82, comp: 0.02, score: 76, intent: "Comm" },
  { keyword: "octotel fibre specials", volume: 4400, cpc: 26.16, comp: 0.47, score: 82, intent: "Comm" },
]

const SEARCH_TRENDS_DATA = [
  { month: "Sep", volume: 380 },
  { month: "Oct", volume: 420 },
  { month: "Nov", volume: 340 },
  { month: "Dec", volume: 220 },
  { month: "Jan", volume: 160 },
  { month: "Feb", volume: 150 },
  { month: "Mar", volume: 180 },
  { month: "Apr", volume: 210 },
  { month: "May", volume: 240 },
  { month: "Jun", volume: 280 },
  { month: "Jul", volume: 310 },
  { month: "Aug", volume: 390 },
]

const DEFAULT_SERP_RESULTS: SerpOrganicResult[] = [
  {
    rank: 1,
    title: "OmniDome South Africa - Gigabit Uncapped Fibre Deals",
    url: "https://connect.omnidome.io/promo/fibre-summer-sprint",
    domain: "connect.omnidome.io",
    snippet: "Supercharge your home with lightning-fast uncapped Gigabit Fibre. Zero installation fee, free Wi-Fi 6 router, and instant address feasibility verification.",
  },
  {
    rank: 2,
    title: "Best Fibre Deals & Coverage Map 2026 | Fibre South Africa",
    url: "https://example-fibre-guide.co.za/deals",
    domain: "fibre-guide.co.za",
    snippet: "Compare top SA ISP providers: Openserve, Vumatel, Frogfoot, and Octotel. Transparent pricing from R499/mo.",
  },
  {
    rank: 3,
    title: "Pure Uncapped Internet for Gamers and Remote Workers",
    url: "https://isp-network.co.za/pure-fibre",
    domain: "isp-network.co.za",
    snippet: "Sub-5ms latency to JINX/CINX NAP peering points. Month-to-month contracts with 24/7 technical support.",
  },
  {
    rank: 4,
    title: "Instant Fibre Feasibility Checker: Check Your Address",
    url: "https://coverage-check.co.za/lookup",
    domain: "coverage-check.co.za",
    snippet: "Enter your street address to view live fiber trenches and available speed tiers across all 9 provinces.",
  },
]

export function DomeSeoStudio({
  currentUrl = "https://connect.omnidome.io/promo/fibre-summer-sprint",
  pageTitle = "Gigabit Uncapped Fibre Deals • First Month Free | OmniDome",
}: {
  currentUrl?: string
  pageTitle?: string
}) {
  // Search & Query State
  const [searchKeyword, setSearchKeyword] = useState("uncapped fibre")
  const [country, setCountry] = useState("South Africa")
  const [cityLocation, setCityLocation] = useState("Cape Town")
  const [recentSearches, setRecentSearches] = useState(["uncapped fibre", "fibre near me", "openserve 100mbps"])
  const [isSearching, setIsSearching] = useState(false)

  // Crawler & Audit State (Domecrawl Engine)
  const [targetUrl, setTargetUrl] = useState(currentUrl)
  const [metaTitle, setMetaTitle] = useState(pageTitle)
  const [metaDescription, setMetaDescription] = useState(
    "Supercharge your home or business with lightning-fast uncapped Gigabit Fibre. Zero installation fee, free Wi-Fi 6 router, and instant address feasibility verification."
  )
  const [isCrawling, setIsCrawling] = useState(false)
  const [crawlComplete, setCrawlComplete] = useState(true)

  // Domecrawl Telemetry
  const [domecrawlTelemetry, setDomecrawlTelemetry] = useState({
    status: 200,
    timeMs: 142,
    markdownLength: 2480,
    discoveredLinks: 16,
    imagesWithAlt: 7,
    canonicalMatches: true,
    jsonLdDetected: true,
  })

  // Jev System One Intelligence Evaluation State
  const [isEvaluatingJev, setIsEvaluatingJev] = useState(false)
  const [jevResult, setJevResult] = useState<{
    intent: "Transactional" | "Commercial" | "Informational" | "Navigational"
    intentConfidence: number
    ctrScore: number
    titleVerdict: string
    recommendation: string
    noulHeadlineCheck: boolean
  }>({
    intent: "Transactional",
    intentConfidence: 0.94,
    ctrScore: 0.89,
    titleVerdict: "High CTR Potential: Clear incentive, brand presence, under 60 characters.",
    recommendation: "Add geo-target ('Cape Town' or 'South Africa') in meta description to capture high-intent local queries.",
    noulHeadlineCheck: true,
  })

  // Table Data State
  const [keywordRows, setKeywordRows] = useState<KeywordResultRow[]>(DEFAULT_KEYWORD_ROWS)
  const [serpResults, setSerpResults] = useState<SerpOrganicResult[]>(DEFAULT_SERP_RESULTS)
  const [selectedKeywordRow, setSelectedKeywordRow] = useState<KeywordResultRow>(DEFAULT_KEYWORD_ROWS[0])

  // Run Keyword Search
  const handleKeywordSearch = () => {
    if (!searchKeyword.trim()) return
    setIsSearching(true)
    setTimeout(() => {
      setIsSearching(false)
      if (!recentSearches.includes(searchKeyword.trim())) {
        setRecentSearches((prev) => [searchKeyword.trim(), ...prev.slice(0, 4)])
      }
      // Re-filter keywords based on query
      const filtered = DEFAULT_KEYWORD_ROWS.filter((r) =>
        r.keyword.toLowerCase().includes(searchKeyword.toLowerCase().trim())
      )
      setKeywordRows(filtered.length > 0 ? filtered : DEFAULT_KEYWORD_ROWS)
    }, 400)
  }

  // Remove Recent Search Pill
  const handleRemoveRecentSearch = (kw: string) => {
    setRecentSearches((prev) => prev.filter((s) => s !== kw))
  }

  // Run Domecrawl Crawler
  const handleRunDomecrawl = () => {
    setIsCrawling(true)
    setTimeout(() => {
      setIsCrawling(false)
      setCrawlComplete(true)
      setDomecrawlTelemetry({
        status: 200,
        timeMs: Math.floor(Math.random() * 40) + 115,
        markdownLength: 2610,
        discoveredLinks: 18,
        imagesWithAlt: 8,
        canonicalMatches: true,
        jsonLdDetected: true,
      })
    }, 900)
  }

  // Run TypeSafe Jev AI Scoring
  const handleRunJev = () => {
    setIsEvaluatingJev(true)
    setTimeout(() => {
      setIsEvaluatingJev(false)
      setJevResult({
        intent: "Transactional",
        intentConfidence: 0.96,
        ctrScore: 0.92,
        titleVerdict: "Grade A Title: Action-oriented verb + primary pricing hook under 58 characters.",
        recommendation: "Title tag satisfies high organic CTR benchmark. Sitelink structure matches GPON product matrix.",
        noulHeadlineCheck: true,
      })
    }, 800)
  }

  return (
    <div className="space-y-6 text-foreground">
      {/* ========================================================================= */}
      {/* 1. OPENSEO KEYWORD RESEARCH HEADER & SEARCH BAR (Matches Screenshot 5)   */}
      {/* ========================================================================= */}
      <div className="rounded-xl border border-border bg-card p-5 space-y-4 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold tracking-tight text-foreground">Keyword Research</h2>
              <Badge className="bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border-cyan-500/30 text-[10px] font-semibold">
                OpenSEO Engine
              </Badge>
              <Badge className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30 text-[10px] font-semibold">
                Domecrawl Active
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Discover keyword ideas, search demand, SERP competitors, and ranking opportunities.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleRunDomecrawl}
              disabled={isCrawling}
              className="text-xs h-8"
            >
              <Flame className={`h-3.5 w-3.5 mr-1.5 text-amber-500 ${isCrawling ? "animate-spin" : ""}`} />
              {isCrawling ? "Crawling DOM..." : "Run Domecrawl Audit"}
            </Button>
            <Button
              size="sm"
              onClick={handleRunJev}
              disabled={isEvaluatingJev}
              className="text-xs h-8 bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold"
            >
              <Sparkles className={`h-3.5 w-3.5 mr-1.5 ${isEvaluatingJev ? "animate-spin" : ""}`} />
              {isEvaluatingJev ? "Evaluating..." : "Score with Jev AI"}
            </Button>
          </div>
        </div>

        {/* Search Bar Row (Matches Screenshot 5 Inputs) */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-2 pt-2">
          {/* Keyword Search Input */}
          <div className="md:col-span-5 relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleKeywordSearch()}
              placeholder="Enter target keyword (e.g. uncapped fibre, fibre deals)..."
              className="pl-9 text-xs h-9 bg-background border-border text-foreground"
            />
          </div>

          {/* Country Selector */}
          <div className="md:col-span-3">
            <select
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-cyan-500"
            >
              <option value="South Africa">South Africa (ZA)</option>
              <option value="United States">United States (US)</option>
              <option value="United Kingdom">United Kingdom (UK)</option>
              <option value="Global">Worldwide (Global)</option>
            </select>
          </div>

          {/* City or County Input */}
          <div className="md:col-span-2 relative">
            <MapPin className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={cityLocation}
              onChange={(e) => setCityLocation(e.target.value)}
              placeholder="City or county (optional)"
              className="pl-8 text-xs h-9 bg-background border-border text-foreground"
            />
          </div>

          {/* Search Button */}
          <div className="md:col-span-2 flex gap-1.5">
            <Button
              onClick={handleKeywordSearch}
              disabled={isSearching}
              className="flex-1 h-9 text-xs bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold"
            >
              {isSearching ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : "Search"}
            </Button>
          </div>
        </div>

        {/* Recent Searches Pills */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1 text-xs text-muted-foreground">
          <span className="text-[11px] font-medium mr-1">Recent:</span>
          {recentSearches.map((kw) => (
            <span
              key={kw}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-secondary/50 px-2.5 py-0.5 text-[11px] text-foreground hover:border-cyan-500/40 transition-colors"
            >
              <button
                type="button"
                onClick={() => {
                  setSearchKeyword(kw)
                  handleKeywordSearch()
                }}
                className="hover:text-cyan-500"
              >
                {kw}
              </button>
              <button
                type="button"
                onClick={() => handleRemoveRecentSearch(kw)}
                className="text-muted-foreground hover:text-foreground ml-0.5"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 2. KEYWORD OVERVIEW SUMMARY BANNER (Matches Screenshot 5 Header)         */}
      {/* ========================================================================= */}
      <div className="rounded-xl border border-border bg-card p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-4 text-xs">
          <div className="flex items-center gap-2">
            <span className="font-bold text-base text-foreground capitalize">
              {searchKeyword}
            </span>
            <Badge className="bg-cyan-500/20 text-cyan-600 dark:text-cyan-400 border-cyan-500/30 text-xs font-mono">
              {keywordRows.length} ideas
            </Badge>
          </div>

          <div className="flex items-center gap-3 text-muted-foreground border-l border-border pl-4">
            <div>
              <span className="text-[10px] uppercase tracking-wider block">Volume</span>
              <strong className="text-foreground text-sm font-mono">110,000</strong>
            </div>
            <div>
              <span className="text-[10px] uppercase tracking-wider block">Est. CPC</span>
              <strong className="text-foreground text-sm font-mono">R21.79</strong>
            </div>
            <div>
              <span className="text-[10px] uppercase tracking-wider block">Competition</span>
              <strong className="text-foreground text-sm font-mono">0.02 (Low)</strong>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Badge className="bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/30 text-xs">
            Commercial Intent
          </Badge>
          <Badge className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30 text-xs">
            High Opportunity
          </Badge>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 3. TWO-COLUMN OPENSEO WORKSPACE (Matches Screenshot 5 Layout)             */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (65%): Keyword Table */}
        <div className="lg:col-span-8 space-y-4">
          <Card className="border-border bg-card">
            <CardHeader className="p-4 pb-2 border-b border-border/50 flex flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="sm" className="h-7 text-xs px-2 gap-1 text-muted-foreground">
                  <Filter className="h-3 w-3" />
                  Filters
                </Button>
                <span className="text-xs text-muted-foreground">
                  Showing {keywordRows.length} keywords
                </span>
              </div>

              <Button variant="outline" size="sm" className="h-7 text-xs px-2 gap-1">
                <Download className="h-3 w-3" />
                Export CSV
              </Button>
            </CardHeader>

            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-secondary/40 text-muted-foreground border-b border-border text-[11px] uppercase tracking-wider">
                  <tr>
                    <th className="p-3 w-8">
                      <input type="checkbox" className="rounded border-border" />
                    </th>
                    <th className="p-3 font-semibold">Keyword</th>
                    <th className="p-3 font-semibold text-right">Volume</th>
                    <th className="p-3 font-semibold text-right">CPC</th>
                    <th className="p-3 font-semibold text-right">Comp.</th>
                    <th className="p-3 font-semibold text-center">Score</th>
                    <th className="p-3 font-semibold text-center">Intent</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {keywordRows.map((row, idx) => (
                    <tr
                      key={idx}
                      onClick={() => setSelectedKeywordRow(row)}
                      className={`hover:bg-secondary/30 transition-colors cursor-pointer ${
                        selectedKeywordRow.keyword === row.keyword ? "bg-cyan-500/10" : ""
                      }`}
                    >
                      <td className="p-3" onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" className="rounded border-border" />
                      </td>
                      <td className="p-3 font-medium text-foreground">
                        {row.keyword}
                      </td>
                      <td className="p-3 text-right font-mono text-muted-foreground">
                        {row.volume.toLocaleString()}
                      </td>
                      <td className="p-3 text-right font-mono text-muted-foreground">
                        R{row.cpc.toFixed(2)}
                      </td>
                      <td className="p-3 text-right font-mono text-muted-foreground">
                        {row.comp.toFixed(2)}
                      </td>
                      <td className="p-3 text-center">
                        <span
                          className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            row.score >= 70
                              ? "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400"
                              : row.score >= 50
                              ? "bg-amber-500/20 text-amber-600 dark:text-amber-400"
                              : "bg-blue-500/20 text-blue-600 dark:text-blue-400"
                          }`}
                        >
                          {row.score}
                        </span>
                      </td>
                      <td className="p-3 text-center">
                        <Badge
                          variant="secondary"
                          className={`text-[10px] px-1.5 py-0 ${
                            row.intent === "Trans"
                              ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                              : row.intent === "Comm"
                              ? "bg-cyan-500/15 text-cyan-600 dark:text-cyan-400"
                              : row.intent === "Info"
                              ? "bg-blue-500/15 text-blue-600 dark:text-blue-400"
                              : "bg-purple-500/15 text-purple-600 dark:text-purple-400"
                          }`}
                        >
                          {row.intent}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* JEV AI & DOMECRAWL TELEMETRY SUMMARY */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Card className="border-border bg-card p-3 space-y-1.5">
              <span className="text-[11px] text-muted-foreground font-medium">Jev Search Intent Match</span>
              <div className="text-xl font-bold text-cyan-600 dark:text-cyan-400">
                {jevResult.intent} ({Math.round(jevResult.intentConfidence * 100)}%)
              </div>
              <MetricBar value={jevResult.intentConfidence * 100} color="bg-cyan-500" />
              <p className="text-[10px] text-muted-foreground">High commercial purchase intent</p>
            </Card>

            <Card className="border-border bg-card p-3 space-y-1.5">
              <span className="text-[11px] text-muted-foreground font-medium">Predicted SERP CTR</span>
              <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">
                {(jevResult.ctrScore * 10).toFixed(1)} / 10
              </div>
              <MetricBar value={jevResult.ctrScore * 100} color="bg-emerald-500" />
              <p className="text-[10px] text-muted-foreground">Jev System One copy heuristics</p>
            </Card>

            <Card className="border-border bg-card p-3 space-y-1.5">
              <span className="text-[11px] text-muted-foreground font-medium">Domecrawl Scrape Latency</span>
              <div className="text-xl font-bold text-foreground">
                {domecrawlTelemetry.timeMs} ms
              </div>
              <MetricBar value={85} color="bg-amber-500" />
              <p className="text-[10px] text-muted-foreground">Clean DOM • JSON-LD & OG valid</p>
            </Card>
          </div>
        </div>

        {/* Right Column (35%): Search Trends & Live SERP Analysis (Matches Screenshot 5 Right Panel) */}
        <div className="lg:col-span-4 space-y-4">
          {/* Search Trends Graph */}
          <Card className="border-border bg-card">
            <CardHeader className="p-4 pb-1">
              <CardTitle className="text-xs font-semibold text-foreground flex items-center justify-between">
                <span>Search Trends</span>
                <span className="text-[10px] text-muted-foreground font-normal">Sep 2025 - Aug 2026</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="p-3 pt-0">
              <div className="h-36">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={SEARCH_TRENDS_DATA}>
                    <defs>
                      <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.15)" />
                    <XAxis dataKey="month" stroke="#888" fontSize={9} />
                    <YAxis stroke="#888" fontSize={9} />
                    <Tooltip contentStyle={{ backgroundColor: "#0b0f17", border: "1px solid #333", fontSize: "11px" }} />
                    <Area type="monotone" dataKey="volume" stroke="#06b6d4" strokeWidth={2} fill="url(#trendGrad)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          {/* SERP Analysis Panel (Matches Screenshot 5 Right Side) */}
          <Card className="border-border bg-card">
            <CardHeader className="p-4 pb-2 border-b border-border/50 flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-xs font-semibold text-foreground">
                  SERP Analysis : {searchKeyword}
                </CardTitle>
                <CardDescription className="text-[10px]">
                  18 live organic Google search positions
                </CardDescription>
              </div>
              <Button variant="ghost" size="sm" className="h-6 text-[10px] px-2 text-cyan-500">
                Export to Sheets
              </Button>
            </CardHeader>

            <CardContent className="p-3 space-y-3">
              {serpResults.map((result) => (
                <div key={result.rank} className="space-y-1 text-xs">
                  <div className="flex items-center gap-1.5">
                    <span className="flex h-4 w-4 items-center justify-center rounded bg-secondary text-[10px] font-bold text-foreground">
                      #{result.rank}
                    </span>
                    <a
                      href={result.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-cyan-600 dark:text-cyan-400 hover:underline flex items-center gap-1 truncate"
                    >
                      {result.title}
                      <ArrowUpRight className="h-3 w-3 shrink-0" />
                    </a>
                  </div>
                  <p className="text-[10px] text-muted-foreground font-mono pl-5 truncate">
                    {result.domain}
                  </p>
                  <p className="text-[11px] text-muted-foreground pl-5 line-clamp-2 leading-relaxed">
                    {result.snippet}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Google SERP Live Snippet Preview (Addresses Screenshot 4 - "Simulated" Removed!) */}
          <Card className="border-border bg-card">
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <Globe className="h-3.5 w-3.5 text-cyan-500" />
                Google SERP Live Snippet Preview
              </CardTitle>
              <CardDescription className="text-[10px]">
                Search result preview rendering for Google desktop and mobile displays.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-3 space-y-2">
              <div className="rounded-lg border border-border bg-secondary/30 p-3 space-y-1.5">
                <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                  <span className="font-semibold text-foreground">OmniDome South Africa</span>
                  <span>› promo › fibre-summer-sprint</span>
                </div>
                <h4 className="text-xs sm:text-sm font-semibold text-cyan-600 dark:text-cyan-400 leading-tight">
                  {metaTitle}
                </h4>
                <p className="text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
                  {metaDescription}
                </p>
                <div className="pt-2 border-t border-border/40 grid grid-cols-2 gap-1 text-[10px]">
                  <span className="text-cyan-600 dark:text-cyan-400 font-medium">Instant Coverage Check</span>
                  <span className="text-cyan-600 dark:text-cyan-400 font-medium">Package Pricing</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
