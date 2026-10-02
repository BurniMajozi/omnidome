"use client"

import React, { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Switch } from "@/components/ui/switch"
import {
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  Monitor,
  Smartphone,
  Globe,
  Share2,
  TrendingUp,
  Megaphone,
  Layers,
  Palette,
  Zap,
  ShieldCheck,
  Send,
  MapPin,
  Wifi,
  ExternalLink,
  Copy,
  Plus,
  RefreshCw,
  Eye,
  Sliders,
  Check,
  ArrowRight,
} from "lucide-react"

export interface LandingPageRecord {
  id: number | string
  name: string
  url: string
  status: "published" | "draft"
  views: number
  conversions: number
  rate: string
  marketingCampaign?: string
  utmSource?: string
}

export type DomeStudioPage = LandingPageRecord

interface DomeStudioWorkspaceProps {
  initialPages?: LandingPageRecord[]
  onSavePage?: (page: LandingPageRecord) => void
  onPublishAll?: () => void
  defaultMode?: "inline-builder" | "dual-view"
}

export function DomeStudioWorkspace({
  initialPages = [],
  onSavePage,
  onPublishAll,
  defaultMode = "inline-builder",
}: DomeStudioWorkspaceProps) {
  // Active page selection
  const [selectedPageId, setSelectedPageId] = useState<string | number>(
    initialPages[0]?.id || "promo-q1"
  )

  // Page Configuration State
  const [pageName, setPageName] = useState("Uncapped Fibre Summer Sprint")
  const [pageSlug, setPageSlug] = useState("fibre-summer-sprint")
  const [template, setTemplate] = useState<"promo" | "business" | "coverage" | "referral">("promo")
  const [designMode, setDesignMode] = useState<"craft" | "bolder" | "quieter" | "delight">("craft")
  const [colorAccent, setColorAccent] = useState<"cyan" | "emerald" | "amber" | "cobalt">("cyan")
  const [previewViewport, setPreviewViewport] = useState<"desktop" | "mobile" | "dual">("desktop")

  // Marketing Integration State
  const [utmCampaign, setUtmCampaign] = useState("q4_cape_town_rollout")
  const [utmSource, setUtmSource] = useState("google_cpc")
  const [utmMedium, setUtmMedium] = useState("paid_search")
  const [crmQueue, setCrmQueue] = useState("Cape Town Inbound Feasibility")
  const [enableWhatsAppAutomation, setEnableWhatsAppAutomation] = useState(true)
  const [enableLeadCaptureWebhook, setEnableLeadCaptureWebhook] = useState(true)
  const [metaPixelId, setMetaPixelId] = useState("PIX-84920194")
  const [gtmContainerId, setGtmContainerId] = useState("GTM-OMNI991")

  // Interactive Live Preview Simulation State
  const [simulatedAddress, setSimulatedAddress] = useState("14 Kloof Street, Gardens, Cape Town")
  const [selectedSpeed, setSelectedSpeed] = useState("250")
  const [previewFormSubmitted, setPreviewFormSubmitted] = useState(false)
  const [leadName, setLeadName] = useState("Sipho Ndlovu")
  const [leadPhone, setLeadPhone] = useState("+27 82 459 2940")
  const [copiedLink, setCopiedLink] = useState(false)
  const [publishFeedback, setPublishFeedback] = useState<string | null>(null)

  const handleCopyUrl = () => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(
        `https://connect.omnidome.io/promo/${pageSlug}?utm_source=${utmSource}&utm_medium=${utmMedium}&utm_campaign=${utmCampaign}`
      )
      setCopiedLink(true)
      setTimeout(() => setCopiedLink(false), 2000)
    }
  }

  const handlePublish = (status: "published" | "draft") => {
    const updatedPage: LandingPageRecord = {
      id: selectedPageId,
      name: pageName,
      url: `/promo/${pageSlug}`,
      status,
      views: status === "published" ? 1450 : 0,
      conversions: status === "published" ? 42 : 0,
      rate: status === "published" ? "2.9%" : "-",
      marketingCampaign: utmCampaign,
      utmSource,
    }
    onSavePage?.(updatedPage)
    setPublishFeedback(
      status === "published"
        ? `Page "${pageName}" published live to connect.omnidome.io!`
        : `Draft saved for "${pageName}".`
    )
    setTimeout(() => setPublishFeedback(null), 3500)
  }

  const handleSelectTemplate = (type: "promo" | "business" | "coverage" | "referral") => {
    setTemplate(type)
    if (type === "promo") {
      setPageName("Fibre Summer Sprint 2026")
      setPageSlug("fibre-summer-sprint")
      setColorAccent("cyan")
      setUtmCampaign("summer_fibre_flash")
    } else if (type === "business") {
      setPageName("Direct Dedicated 1Gbps Business Fibre")
      setPageSlug("business-direct-1g")
      setColorAccent("emerald")
      setUtmCampaign("enterprise_cape_switch")
    } else if (type === "coverage") {
      setPageName("Instant FTTH Feasibility Check")
      setPageSlug("check-coverage")
      setColorAccent("amber")
      setUtmCampaign("coverage_qualifier_kwazulu")
    } else {
      setPageName("Refer a Neighbour, Get R500 Off")
      setPageSlug("refer-neighbour")
      setColorAccent("cyan")
      setUtmCampaign("customer_referrals_march")
    }
  }

  // Accent styling mapping strictly adhering to DomeStudio DESIGN.md
  const accentClasses = {
    cyan: {
      badge: "border-cyan-500/30 bg-cyan-500/10 text-cyan-400",
      button: "bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold shadow-cyan-500/20 shadow-md",
      highlight: "text-cyan-400",
      border: "border-cyan-500/30",
    },
    emerald: {
      badge: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
      button: "bg-emerald-500 hover:bg-emerald-400 text-emerald-950 font-semibold shadow-emerald-500/20 shadow-md",
      highlight: "text-emerald-400",
      border: "border-emerald-500/30",
    },
    amber: {
      badge: "border-amber-500/30 bg-amber-500/10 text-amber-400",
      button: "bg-amber-500 hover:bg-amber-400 text-amber-950 font-semibold shadow-amber-500/20 shadow-md",
      highlight: "text-amber-400",
      border: "border-amber-500/30",
    },
    cobalt: {
      badge: "border-sky-500/30 bg-sky-500/10 text-sky-400",
      button: "bg-sky-500 hover:bg-sky-400 text-sky-950 font-semibold shadow-sky-500/20 shadow-md",
      highlight: "text-sky-400",
      border: "border-sky-500/30",
    },
  }

  const currentAccent = accentClasses[colorAccent]

  // Render the simulated interactive landing page content
  const renderSimulatedLanding = (viewport: "desktop" | "mobile") => (
    <div
      className={`bg-[#060911] text-foreground rounded-lg border border-border/80 overflow-hidden flex flex-col transition-all duration-300 ${
        viewport === "mobile"
          ? "max-w-[360px] mx-auto min-h-[580px] shadow-2xl ring-1 ring-border"
          : "w-full min-h-[580px] shadow-xl"
      }`}
    >
      {/* Browser / Device Chrome */}
      <div className="bg-[#0b101c] px-3.5 py-2 border-b border-border/60 flex items-center justify-between text-xs text-muted-foreground select-none">
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
        </div>
        <div className="flex items-center gap-1.5 bg-[#121929] px-2.5 py-0.5 rounded text-[11px] font-mono text-cyan-400 truncate max-w-[200px]">
          <Globe className="h-3 w-3 shrink-0" />
          <span>connect.omnidome.io/{pageSlug}</span>
        </div>
        <div className="flex items-center gap-1">
          <Badge variant="outline" className="text-[9px] px-1 py-0 border-emerald-500/40 text-emerald-400">
            SSL Live
          </Badge>
        </div>
      </div>

      {/* Hero Section */}
      <div className="p-5 md:p-7 flex-1 flex flex-col justify-between space-y-6 bg-gradient-to-b from-[#09101e] to-[#05070d]">
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${currentAccent.badge}`}
            >
              <Zap className="h-3 w-3" />
              {template === "promo" && "LIMITED TIME • FIRST MONTH FREE"}
              {template === "business" && "ENTERPRISE GRADE • 99.95% SLA"}
              {template === "coverage" && "LIVE FEASIBILITY CHECKER"}
              {template === "referral" && "REWARD NETWORK • R500 BILL CREDIT"}
            </span>
          </div>

          <h2
            className={`font-extrabold tracking-tight text-white leading-tight ${
              viewport === "mobile" ? "text-xl" : "text-2xl md:text-3xl"
            }`}
          >
            {template === "promo" && (
              <>
                Gigabit Fibre without the Wait.{" "}
                <span className={currentAccent.highlight}>Zero Installation Fee.</span>
              </>
            )}
            {template === "business" && (
              <>
                Symmetrical Business Fibre.{" "}
                <span className={currentAccent.highlight}>Dedicated Uncapped Bandwidth.</span>
              </>
            )}
            {template === "coverage" && (
              <>
                Check Live Fibre Feasibility.{" "}
                <span className={currentAccent.highlight}>Online in 48 Hours.</span>
              </>
            )}
            {template === "referral" && (
              <>
                Share High-Speed Fibre.{" "}
                <span className={currentAccent.highlight}>Earn R500 for Each Sign-up.</span>
              </>
            )}
          </h2>

          <p className="text-xs text-muted-foreground leading-relaxed">
            {template === "promo" &&
              "Ultra-low latency connection powered by OmniDome Telecom Cloud OS. Free Wi-Fi 6 router included."}
            {template === "business" &&
              "Deterministic performance with static IPv4 subnet and dedicated NOC escalation."}
            {template === "coverage" &&
              "Instant address query across Openserve, Vumatel, Frogfoot, and MetroFibre networks."}
            {template === "referral" &&
              "Refer your friends, family, or office neighbours. Credits reflect directly on your monthly invoice."}
          </p>
        </div>

        {/* Speed Selector Pill */}
        <div className="space-y-2">
          <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Select Your Target Speed
          </label>
          <div className="grid grid-cols-3 gap-2">
            {[
              { mbps: "100", price: "R599/pm" },
              { mbps: "250", price: "R799/pm" },
              { mbps: "1000", price: "R1,199/pm" },
            ].map((pkg) => (
              <button
                key={pkg.mbps}
                type="button"
                onClick={() => setSelectedSpeed(pkg.mbps)}
                className={`p-2 rounded border text-left transition-all ${
                  selectedSpeed === pkg.mbps
                    ? `border-cyan-500/70 bg-cyan-950/40 text-white shadow-sm`
                    : "border-border/60 bg-[#0d1424] text-muted-foreground hover:border-border"
                }`}
              >
                <div className="text-xs font-bold text-white">{pkg.mbps} Mbps</div>
                <div className="text-[10px] text-cyan-400 font-mono">{pkg.price}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Interactive Lead / Feasibility Form */}
        <div className="p-4 rounded-lg border border-border/80 bg-[#0c1220]/90 space-y-3">
          <div className="flex items-center justify-between text-xs font-medium text-foreground">
            <span className="flex items-center gap-1.5">
              <MapPin className="h-3.5 w-3.5 text-cyan-400" />
              Check Address Feasibility
            </span>
            <span className="text-[10px] text-emerald-400 font-mono">POPIA Compliant</span>
          </div>

          <div className="space-y-2">
            <Input
              value={simulatedAddress}
              onChange={(e) => setSimulatedAddress(e.target.value)}
              placeholder="Enter Street Address & Suburb"
              className="h-8 text-xs bg-[#12192c] border-border text-foreground"
            />
            <div className="grid grid-cols-2 gap-2">
              <Input
                value={leadName}
                onChange={(e) => setLeadName(e.target.value)}
                placeholder="Full Name"
                className="h-8 text-xs bg-[#12192c] border-border text-foreground"
              />
              <Input
                value={leadPhone}
                onChange={(e) => setLeadPhone(e.target.value)}
                placeholder="Cell Number"
                className="h-8 text-xs bg-[#12192c] border-border text-foreground"
              />
            </div>
          </div>

          {previewFormSubmitted ? (
            <div className="p-2.5 rounded bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xs flex items-center justify-between animate-in fade-in">
              <span className="flex items-center gap-1.5 font-medium">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                Coverage Confirmed! Routing to {crmQueue}...
              </span>
              <button
                type="button"
                onClick={() => setPreviewFormSubmitted(false)}
                className="text-[10px] underline text-emerald-400 ml-2"
              >
                Reset
              </button>
            </div>
          ) : (
            <Button
              type="button"
              onClick={() => setPreviewFormSubmitted(true)}
              className={`w-full h-8 text-xs font-semibold ${currentAccent.button}`}
            >
              Verify Coverage & Claim Deal
              <ArrowRight className="h-3 w-3 ml-1.5" />
            </Button>
          )}

          {/* Marketing Integration Live Tracking Footprint */}
          <div className="pt-2 border-t border-border/40 flex items-center justify-between text-[10px] text-muted-foreground">
            <span className="truncate">Campaign: {utmCampaign}</span>
            <span className="font-mono text-cyan-400">{crmQueue.split(" ")[0]} Queue</span>
          </div>
        </div>
      </div>
    </div>
  )

  return (
    <div className="space-y-5">
      {/* DomeStudio Main Control Header */}
      <div className="rounded-xl border border-cyan-500/30 bg-gradient-to-r from-cyan-950/40 via-[#0c1322] to-[#080d18] p-5 shadow-lg">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="border-cyan-500/40 bg-cyan-950/60 text-cyan-400 text-xs font-mono">
                <Sparkles className="h-3 w-3 mr-1" />
                DOMESTUDIO ENGINE
              </Badge>
              <span className="text-xs text-muted-foreground">Telecom Landing Pages & Lead Attribution</span>
            </div>
            <h3 className="text-lg font-bold text-foreground">High-Converting Fibre Landing Pages</h3>
            <p className="text-xs text-muted-foreground max-w-2xl">
              Create and publish high-performance landing pages with real-time UTM parameter tracking, automated CRM lead
              ingestion, WhatsApp qualification journeys, and zero UI anti-patterns.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleCopyUrl}
              className="text-xs border-border/80 bg-secondary/50"
            >
              {copiedLink ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 mr-1.5" /> : <Copy className="h-3.5 w-3.5 mr-1.5" />}
              {copiedLink ? "Link Copied" : "Copy Live Link"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handlePublish("draft")}
              className="text-xs border-border/80 bg-secondary/50"
            >
              Save Draft
            </Button>
            <Button
              size="sm"
              onClick={() => handlePublish("published")}
              className="text-xs bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold shadow-md shadow-cyan-500/20"
            >
              <Globe className="h-3.5 w-3.5 mr-1.5" />
              Publish Live
            </Button>
          </div>
        </div>

        {publishFeedback && (
          <div className="mt-3 p-2.5 rounded-lg bg-emerald-950/50 border border-emerald-500/40 text-emerald-300 text-xs flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
            <span>{publishFeedback}</span>
          </div>
        )}
      </div>

      {/* Preset Intent Switcher */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          {
            id: "promo" as const,
            title: "Fibre Flash Promo",
            desc: "First month free & router promo",
            accent: "border-cyan-500/40 hover:border-cyan-400",
          },
          {
            id: "business" as const,
            title: "Business Dedicated",
            desc: "Symmetrical 1Gbps with SLA",
            accent: "border-emerald-500/40 hover:border-emerald-400",
          },
          {
            id: "coverage" as const,
            title: "Feasibility Qualifier",
            desc: "Direct multi-FNO address lookup",
            accent: "border-amber-500/40 hover:border-amber-400",
          },
          {
            id: "referral" as const,
            title: "Referral Network",
            desc: "Customer viral loop & credits",
            accent: "border-sky-500/40 hover:border-sky-400",
          },
        ].map((item) => (
          <Card
            key={item.id}
            onClick={() => handleSelectTemplate(item.id)}
            className={`cursor-pointer transition-all duration-200 border bg-card/80 ${
              template === item.id ? "border-cyan-500 bg-cyan-950/20 shadow-md ring-1 ring-cyan-500/50" : item.accent
            }`}
          >
            <CardContent className="p-3.5">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-xs text-foreground">{item.title}</span>
                {template === item.id && <Check className="h-3.5 w-3.5 text-cyan-400" />}
              </div>
              <p className="text-[11px] text-muted-foreground mt-1">{item.desc}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* DomeStudio Two-Column Interactive Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left Column: Configuration & Marketing Engine (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          <Card className="border-border bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Sliders className="h-4 w-4 text-cyan-400" />
                DomeStudio Controls & Marketing Hooks
              </CardTitle>
              <CardDescription className="text-xs">
                Fine-tune design directions, CRM pipelines, and conversion pixels.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-xs">
              <Tabs defaultValue="campaign" className="w-full">
                <TabsList className="w-full grid grid-cols-3 bg-secondary/60">
                  <TabsTrigger value="campaign" className="text-xs">
                    <Megaphone className="h-3.5 w-3.5 mr-1" />
                    Campaign
                  </TabsTrigger>
                  <TabsTrigger value="crm" className="text-xs">
                    <ShieldCheck className="h-3.5 w-3.5 mr-1" />
                    CRM Sync
                  </TabsTrigger>
                  <TabsTrigger value="design" className="text-xs">
                    <Palette className="h-3.5 w-3.5 mr-1" />
                    Design Tone
                  </TabsTrigger>
                </TabsList>

                {/* Tab 1: Campaign & UTM Attribution */}
                <TabsContent value="campaign" className="space-y-3 pt-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Page Name</Label>
                    <Input
                      value={pageName}
                      onChange={(e) => setPageName(e.target.value)}
                      className="h-8 text-xs bg-secondary/50 border-border"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1.5">
                      <Label className="text-xs">URL Slug</Label>
                      <Input
                        value={pageSlug}
                        onChange={(e) => setPageSlug(e.target.value)}
                        className="h-8 text-xs bg-secondary/50 border-border font-mono"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">UTM Campaign</Label>
                      <Input
                        value={utmCampaign}
                        onChange={(e) => setUtmCampaign(e.target.value)}
                        className="h-8 text-xs bg-secondary/50 border-border font-mono"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1.5">
                      <Label className="text-xs">UTM Source</Label>
                      <Input
                        value={utmSource}
                        onChange={(e) => setUtmSource(e.target.value)}
                        className="h-8 text-xs bg-secondary/50 border-border font-mono"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">UTM Medium</Label>
                      <Input
                        value={utmMedium}
                        onChange={(e) => setUtmMedium(e.target.value)}
                        className="h-8 text-xs bg-secondary/50 border-border font-mono"
                      />
                    </div>
                  </div>

                  <div className="space-y-1.5 pt-1">
                    <Label className="text-xs">Ad & Analytics Tracking</Label>
                    <div className="grid grid-cols-2 gap-2">
                      <Input
                        value={metaPixelId}
                        onChange={(e) => setMetaPixelId(e.target.value)}
                        placeholder="Meta Pixel ID"
                        className="h-8 text-xs bg-secondary/50 border-border font-mono"
                      />
                      <Input
                        value={gtmContainerId}
                        onChange={(e) => setGtmContainerId(e.target.value)}
                        placeholder="GTM Container ID"
                        className="h-8 text-xs bg-secondary/50 border-border font-mono"
                      />
                    </div>
                  </div>
                </TabsContent>

                {/* Tab 2: CRM & Webhook Automation */}
                <TabsContent value="crm" className="space-y-3 pt-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Destination CRM Sales Queue</Label>
                    <Input
                      value={crmQueue}
                      onChange={(e) => setCrmQueue(e.target.value)}
                      className="h-8 text-xs bg-secondary/50 border-border"
                    />
                  </div>

                  <div className="p-3 rounded border border-border/70 bg-secondary/30 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-semibold text-xs text-foreground">Lead Webhook Ingestion</p>
                        <p className="text-[11px] text-muted-foreground">POST /api/sales/leads payload</p>
                      </div>
                      <Switch
                        checked={enableLeadCaptureWebhook}
                        onCheckedChange={setEnableLeadCaptureWebhook}
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-semibold text-xs text-foreground">WhatsApp Instant Qualification</p>
                        <p className="text-[11px] text-muted-foreground">Trigger automated onboarding bot</p>
                      </div>
                      <Switch
                        checked={enableWhatsAppAutomation}
                        onCheckedChange={setEnableWhatsAppAutomation}
                      />
                    </div>
                  </div>

                  <div className="rounded p-2.5 bg-cyan-950/30 border border-cyan-500/20 text-cyan-300 text-[11px] flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-cyan-400 shrink-0" />
                    <span>Leads encrypted at rest & mapped directly to Sales Module pipeline.</span>
                  </div>
                </TabsContent>

                {/* Tab 3: Design Tone & Palette */}
                <TabsContent value="design" className="space-y-3 pt-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">DomeStudio Design Direction</Label>
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { id: "craft" as const, label: "/craft", desc: "Balanced elegance" },
                        { id: "bolder" as const, label: "/bolder", desc: "High conversion contrast" },
                        { id: "quieter" as const, label: "/quieter", desc: "Minimalist corporate" },
                        { id: "delight" as const, label: "/delight", desc: "Micro-interactions" },
                      ].map((item) => (
                        <Button
                          key={item.id}
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => setDesignMode(item.id)}
                          className={`h-auto py-2 flex flex-col items-start text-left border ${
                            designMode === item.id
                              ? "border-cyan-500 bg-cyan-950/40 text-cyan-300"
                              : "border-border/60 hover:border-border"
                          }`}
                        >
                          <span className="font-mono text-xs font-bold">{item.label}</span>
                          <span className="text-[10px] text-muted-foreground">{item.desc}</span>
                        </Button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs">Obsidian Accent Color</Label>
                    <div className="grid grid-cols-4 gap-2">
                      {[
                        { id: "cyan" as const, name: "Telecom Cyan", color: "bg-cyan-500" },
                        { id: "emerald" as const, name: "Emerald Pro", color: "bg-emerald-500" },
                        { id: "amber" as const, name: "Solar Amber", color: "bg-amber-500" },
                        { id: "cobalt" as const, name: "Cobalt Blue", color: "bg-sky-500" },
                      ].map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          onClick={() => setColorAccent(c.id)}
                          className={`p-1.5 rounded border text-center transition-all ${
                            colorAccent === c.id
                              ? "border-white/80 bg-secondary"
                              : "border-border/60 hover:border-border"
                          }`}
                        >
                          <div className={`w-full h-4 rounded-sm ${c.color} mx-auto`} />
                          <span className="text-[10px] text-muted-foreground block mt-1 truncate">
                            {c.name.split(" ")[0]}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Live Viewport Preview (7 cols) */}
        <div className="lg:col-span-7 space-y-3">
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <Eye className="h-3.5 w-3.5 text-cyan-400" />
                Live Interactive Preview
              </span>
              <span className="text-[11px] text-muted-foreground font-mono">
                {previewViewport === "desktop" ? "1280px Desktop" : "375px Mobile Viewport"}
              </span>
            </div>

            <div className="flex items-center gap-1 bg-secondary/80 p-0.5 rounded border border-border/70">
              <Button
                variant={previewViewport === "desktop" ? "secondary" : "ghost"}
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={() => setPreviewViewport("desktop")}
              >
                <Monitor className="h-3.5 w-3.5 mr-1" />
                Desktop
              </Button>
              <Button
                variant={previewViewport === "mobile" ? "secondary" : "ghost"}
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={() => setPreviewViewport("mobile")}
              >
                <Smartphone className="h-3.5 w-3.5 mr-1" />
                Mobile
              </Button>
            </div>
          </div>

          {renderSimulatedLanding(previewViewport === "mobile" ? "mobile" : "desktop")}
        </div>
      </div>
    </div>
  )
}

/**
 * Dedicated Live Dual-View Component for the "Live Dual-View" Tab
 */
export function DomeStudioLiveDualView({
  pages = [],
}: {
  pages?: LandingPageRecord[]
}) {
  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-cyan-500/30 bg-gradient-to-r from-cyan-950/40 via-[#0c1322] to-[#080d18] p-5 shadow-lg">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="border-cyan-500/40 bg-cyan-950/60 text-cyan-400 text-xs font-mono">
                <Monitor className="h-3 w-3 mr-1" />
                LIVE DUAL-VIEWPORT STUDIO
              </Badge>
              <span className="text-xs text-muted-foreground">Simultaneous Desktop & Mobile Experience</span>
            </div>
            <h3 className="text-lg font-bold text-foreground mt-1">Live Dual-View Interactive Simulator</h3>
            <p className="text-xs text-muted-foreground max-w-2xl">
              Preview how customers experience your Fibre landing pages on both full-screen desktop displays and mobile
              devices simultaneously with live lead submission and attribution testing.
            </p>
          </div>
          <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 text-xs px-3 py-1">
            <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
            Interactive Test Active
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        {/* Desktop Viewport (7 cols) */}
        <div className="xl:col-span-7 space-y-2">
          <div className="flex items-center justify-between text-xs px-1 text-muted-foreground">
            <span className="font-semibold text-foreground flex items-center gap-1.5">
              <Monitor className="h-3.5 w-3.5 text-cyan-400" />
              Desktop Viewport (1280px)
            </span>
            <span className="font-mono text-[11px] text-cyan-400">100% Symmetrical Scale</span>
          </div>
          <div className="rounded-xl border border-border/80 bg-[#070b14] p-3 shadow-xl">
            <DomeStudioWorkspace initialPages={pages} defaultMode="inline-builder" />
          </div>
        </div>

        {/* Mobile Viewport (5 cols) */}
        <div className="xl:col-span-5 space-y-2">
          <div className="flex items-center justify-between text-xs px-1 text-muted-foreground">
            <span className="font-semibold text-foreground flex items-center gap-1.5">
              <Smartphone className="h-3.5 w-3.5 text-cyan-400" />
              Mobile Device Simulation (375px)
            </span>
            <span className="font-mono text-[11px] text-emerald-400">Touch & WhatsApp Ready</span>
          </div>
          <div className="rounded-xl border border-border/80 bg-[#070b14] p-4 flex justify-center shadow-xl min-h-[640px]">
            <div className="w-full max-w-[360px] my-auto">
              <DomeStudioWorkspace initialPages={pages} defaultMode="dual-view" />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
