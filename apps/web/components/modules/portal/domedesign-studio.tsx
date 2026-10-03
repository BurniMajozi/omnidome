"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
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
  ArrowUp,
  Maximize2,
  Minimize2,
  RotateCcw,
  Bot,
  FileCode,
  Image as ImageIcon,
  MousePointer,
  Hand,
  Type,
  Square,
  Search,
  MoreVertical,
  Paperclip,
  CheckCircle,
  HelpCircle,
} from "lucide-react"
import { LM_FIBER_ZONES, lookupLmZone, type LmZoneMarker, type FiberProduct } from "./lm-map-feeder"
import { DomeStudioShareModal } from "./domestudio-share-modal"
import { ExistingSiteImporterModal, type ScrapedSitePayload } from "./existing-site-importer-modal"

export interface DomeDesignPageRecord {
  id: string | number
  name: string
  url: string
  status: "published" | "draft"
  views: number
  conversions: number
  rate: string
  intent?: string
  designDirection?: string
  marketingCampaign?: string
  utmSource?: string
  utmMedium?: string
  crmQueue?: string
  updatedAt?: string
}

interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  toolCall?: string
  timestamp: string
}

interface DomeDesignStudioProps {
  initialPages?: DomeDesignPageRecord[]
  onSavePage?: (page: any) => void
  onDeletePage?: (id: string | number) => void
  defaultMode?: "discovery" | "canvas"
}

export function DomeDesignStudio({
  initialPages = [],
  onSavePage,
  onDeletePage,
  defaultMode = "discovery",
}: DomeDesignStudioProps) {
  // Navigation / View State
  const [activeStudioView, setActiveStudioView] = useState<"discovery" | "canvas">(
    defaultMode === "canvas" ? "canvas" : "discovery"
  )

  // Current Working Landing Page State
  const [currentPageId, setCurrentPageId] = useState<string>("page-1")
  const [pageTitle, setPageTitle] = useState("Fibre Promo Q1 Summer Sprint")
  const [pageSlug, setPageSlug] = useState("fibre-summer-sprint")
  const [heroBadge, setHeroBadge] = useState("⚡ First Month 100% Free • Pure Uncapped FTTH")
  const [heroHeadline, setHeroHeadline] = useState("Lightning Fast Uncapped Fibre For Your Home")
  const [heroSubheadline, setHeroSubheadline] = useState(
    "Stream, game, and work with zero throttling, free Wi-Fi 6 router, and zero installation fees."
  )
  const [ctaButtonText, setCtaButtonText] = useState("Check Address Feasibility")

  // Design System & Accent
  const [designSystem, setDesignSystem] = useState<"Modernist" | "Obsidian Telecom" | "Vibrant Gigabit" | "Enterprise Sleek">("Obsidian Telecom")
  const [colorAccent, setColorAccent] = useState<"cyan" | "emerald" | "amber" | "cobalt">("cyan")

  // Selected Agent / Model
  const [selectedAgent, setSelectedAgent] = useState("Marketing Designer Agent (Claude 3.5)")

  // Maps (LM files) & Geographic Feasibility State
  const [selectedZone, setSelectedZone] = useState<LmZoneMarker>(LM_FIBER_ZONES[0])
  const [customAddressQuery, setCustomAddressQuery] = useState("Cape Town CBD")
  const [showMapBlock, setShowMapBlock] = useState(true)
  const [selectedProduct, setSelectedProduct] = useState<FiberProduct | null>(
    LM_FIBER_ZONES[0].availableProducts[1] || LM_FIBER_ZONES[0].availableProducts[0]
  )

  // Section Visibility Toggles (Canvas editing)
  const [showPricingTable, setShowPricingTable] = useState(true)
  const [showLeadForm, setShowLeadForm] = useState(true)
  const [showTestimonials, setShowTestimonials] = useState(true)

  // Viewport / Zoom Controls
  const [viewportMode, setViewportMode] = useState<"desktop" | "mobile" | "dual">("desktop")
  const [zoomLevel, setZoomLevel] = useState<number>(100)
  const [activeCanvasTool, setActiveCanvasTool] = useState<"select" | "hand" | "text" | "section" | "map">("select")

  // Modals
  const [shareModalOpen, setShareModalOpen] = useState(false)
  const [importerModalOpen, setImporterModalOpen] = useState(false)
  const [copiedLink, setCopiedLink] = useState(false)
  const [publishFeedback, setPublishFeedback] = useState<string | null>(null)

  // Lead Form Submission Testing State
  const [testLeadName, setTestLeadName] = useState("Nandi Khumalo")
  const [testLeadPhone, setTestLeadPhone] = useState("+27 83 555 1290")
  const [testLeadAddress, setTestLeadAddress] = useState("14 Kloof Street, Gardens, Cape Town")
  const [leadSubmitted, setLeadSubmitted] = useState(false)

  // Conversational Assistant State (Left Pane in Canvas mode)
  const [chatPrompt, setChatPrompt] = useState("")
  const [discoveryPrompt, setDiscoveryPrompt] = useState("")
  const [isAgentThinking, setIsAgentThinking] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "msg-1",
      role: "assistant",
      content:
        "Welcome to DomeDesign. I've initialized the Cape Town Gigabit Summer Sprint artboard with the Octotel & Openserve LM fiber routes. Tell me what to modify, or click any element directly on the canvas to edit.",
      timestamp: "10:00 AM",
    },
  ])

  // Template List for Discovery Screen
  const templates = [
    {
      id: "tpl-summer",
      name: "Gigabit Summer Sprint Promo",
      category: "Promo",
      intent: "promo",
      description: "High-conversion seasonal promo with free router countdown and 3-tier speeds.",
      zone: LM_FIBER_ZONES[0],
      badge: "Summer Special",
    },
    {
      id: "tpl-business",
      name: "Business Dedicated 1Gbps SLA",
      category: "Enterprise",
      intent: "business",
      description: "Dedicated uncontended fiber, static IP addressing, and 99.9% uptime SLA.",
      zone: LM_FIBER_ZONES[1],
      badge: "B2B / SLA",
    },
    {
      id: "tpl-map",
      name: "Interactive FTTH Feasibility Map",
      category: "Coverage",
      intent: "coverage",
      description: "LM fiber trench route scanner with instant address search and operator mapping.",
      zone: LM_FIBER_ZONES[4],
      badge: "LM GIS Map",
    },
    {
      id: "tpl-student",
      name: "Township & Student Fast Bundle",
      category: "Consumer",
      intent: "bundle",
      description: "Budget-friendly uncapped tiers from R399/mo with zero credit check.",
      zone: LM_FIBER_ZONES[2],
      badge: "Prepaid / Flex",
    },
    {
      id: "tpl-gaming",
      name: "Low-Latency Gamer Fibre",
      category: "Gaming",
      intent: "gamer",
      description: "Sub-5ms gaming routes to JINX/CINX with dynamic QoS port prioritization.",
      zone: LM_FIBER_ZONES[1],
      badge: "Sub-5ms Ping",
    },
    {
      id: "tpl-referral",
      name: "Refer a Neighbour Loyalty Loop",
      category: "Loyalty",
      intent: "referral",
      description: "Viral referral landing page giving R500 bill credit to both parties.",
      zone: LM_FIBER_ZONES[3],
      badge: "Viral Loop",
    },
  ]

  // Synchronize product when zone changes
  useEffect(() => {
    if (selectedZone.availableProducts.length > 0) {
      setSelectedProduct(selectedZone.availableProducts[0])
    }
  }, [selectedZone])

  // Handle Location Search / LM Zone Change
  const handleLocationSearch = (query: string) => {
    setCustomAddressQuery(query)
    const matched = lookupLmZone(query)
    setSelectedZone(matched)
  }

  // Handle Chat Instruction to AI Agent
  const handleSendChatMessage = async (overridePrompt?: string) => {
    const text = overridePrompt || chatPrompt
    if (!text.trim()) return

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    }

    setMessages((prev) => [...prev, userMsg])
    if (!overridePrompt) setChatPrompt("")
    setIsAgentThinking(true)

    // Simulate Agent Orchestrator invocation
    setTimeout(() => {
      const lower = text.toLowerCase()
      let replyContent = ""
      let toolCall = ""

      if (lower.includes("map") || lower.includes("lm") || lower.includes("cape town") || lower.includes("sandton") || lower.includes("durban") || lower.includes("pretoria")) {
        const found = lookupLmZone(text)
        setSelectedZone(found)
        toolCall = `[Tool: import_lm_fiber_map] -> Attached ${found.operator} trench routes for ${found.name}`
        replyContent = `I updated the interactive LM map to ${found.name} (${found.operator}). The product pricing table below has been synced with their active GPON tariffs.`
      } else if (lower.includes("headline") || lower.includes("hero") || lower.includes("copy")) {
        setHeroHeadline("Pure Uncapped Gigabit Fibre • Zero Contracts")
        setHeroSubheadline("Experience South Africa's most reliable optical network with instant feasibility checks.")
        toolCall = "[Tool: update_artboard_section] -> Updated Hero typography and marketing copy"
        replyContent = "I revised the Hero headline and subheadline with a punchier, conversion-focused message."
      } else if (lower.includes("pricing") || lower.includes("tier") || lower.includes("speed")) {
        setShowPricingTable(true)
        toolCall = "[Tool: set_location_products] -> Generated 3-tier fiber product matrix"
        replyContent = `I refreshed the speed packages for ${selectedZone.city}. The recommended tier is ${selectedZone.availableProducts[1]?.name || "Fibre Boost"}.`
      } else if (lower.includes("modernist") || lower.includes("obsidian") || lower.includes("theme")) {
        setDesignSystem("Obsidian Telecom")
        setColorAccent("cyan")
        toolCall = "[Tool: apply_design_tokens] -> Loaded Obsidian Telecom token sheet"
        replyContent = "Applied Obsidian Telecom design system with deep dark backgrounds and neon cyan optical indicators."
      } else {
        replyContent = `I reviewed your instruction: "${text}". I have applied the changes to your active artboard and updated the preview canvas.`
        toolCall = "[Tool: orchestrator_layout_patch] -> Synced changes to artboard"
      }

      const agentMsg: ChatMessage = {
        id: `agent-${Date.now()}`,
        role: "assistant",
        content: replyContent,
        toolCall,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      }

      setMessages((prev) => [...prev, agentMsg])
      setIsAgentThinking(false)
    }, 900)
  }

  // Handle Starting from Prompt on Discovery Screen
  const handleStartFromDiscovery = () => {
    if (discoveryPrompt.trim()) {
      setHeroHeadline(discoveryPrompt)
      setPageTitle(discoveryPrompt.slice(0, 35))
    }
    setActiveStudioView("canvas")
    if (discoveryPrompt.trim()) {
      handleSendChatMessage(`Design a high-converting landing page: ${discoveryPrompt}`)
    }
  }

  // Apply Scraped Site from Importer Modal
  const handleApplyScrapedSite = (scraped: ScrapedSitePayload) => {
    setPageTitle(scraped.title.slice(0, 40))
    setHeroHeadline(scraped.heroHeadline)
    setHeroSubheadline(scraped.heroSubheadline)
    setCtaButtonText(scraped.ctaText)
    setActiveStudioView("canvas")

    const agentMsg: ChatMessage = {
      id: `agent-${Date.now()}`,
      role: "assistant",
      content: `I scraped the layout from ${scraped.url}. Extracted headline "${scraped.heroHeadline}" and generated matching fiber packages. You can now edit each block directly on the canvas!`,
      toolCall: `[Tool: firecrawl_dom_ingest] -> Recreated structure with ${scraped.detectedPackages.length} packages`,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    }
    setMessages((prev) => [...prev, agentMsg])
  }

  // Save / Publish Page Handler
  const handleSaveCurrentPage = () => {
    const record: DomeDesignPageRecord = {
      id: currentPageId || `page-${Date.now()}`,
      name: pageTitle,
      url: `/promo/${pageSlug}`,
      status: "published",
      views: 120,
      conversions: 8,
      rate: "6.7%",
      intent: "promo",
      designDirection: designSystem,
      marketingCampaign: "summer_sprint_2026",
      utmSource: "domedesign_studio",
      utmMedium: "direct",
      crmQueue: `${selectedZone.city} Inbound Feasibility`,
      updatedAt: new Date().toISOString(),
    }

    if (onSavePage) {
      onSavePage(record)
    }

    setPublishFeedback("Page published live to /promo/" + pageSlug)
    setTimeout(() => setPublishFeedback(null), 3000)
  }

  // =========================================================================
  // VIEW 1: "WHAT SHOULD WE CREATE?" DISCOVERY HUB (Matches Screenshot 5)
  // =========================================================================
  if (activeStudioView === "discovery") {
    return (
      <div className="min-h-[750px] rounded-xl border border-border bg-[#0b0f17] p-6 lg:p-10 space-y-8 text-foreground">
        {/* Top Header */}
        <div className="flex items-center justify-between border-b border-border/40 pb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/20 text-cyan-400">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <span className="text-base font-bold text-foreground tracking-tight">DomeDesign</span>
              <span className="ml-2 rounded bg-cyan-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-cyan-400 uppercase tracking-wider">
                Beta
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setActiveStudioView("canvas")}
              className="text-xs h-8"
            >
              Open Active Canvas
            </Button>
            <Button
              size="sm"
              onClick={() => setShareModalOpen(true)}
              className="text-xs h-8 bg-secondary hover:bg-secondary/80 text-foreground"
            >
              <Share2 className="mr-1.5 h-3.5 w-3.5" />
              Share
            </Button>
          </div>
        </div>

        {/* Hero Title */}
        <div className="text-center max-w-2xl mx-auto pt-4 space-y-2">
          <h1 className="text-3xl sm:text-4xl font-serif tracking-tight text-foreground">
            What should we create?
          </h1>
          <p className="text-sm text-muted-foreground">
            Describe a campaign idea, attach an existing website, or pick a South African FTTH template.
          </p>
        </div>

        {/* Centered Claude Design Prompt Box */}
        <div className="max-w-2xl mx-auto rounded-xl border border-border/80 bg-card p-3 shadow-2xl space-y-3">
          <div className="relative">
            <textarea
              value={discoveryPrompt}
              onChange={(e) => setDiscoveryPrompt(e.target.value)}
              placeholder="Sketch a landing page layout, e.g. 'Gigabit promo for Cape Town with interactive LM fiber map and Vumatel 500M pricing'..."
              className="w-full resize-none bg-transparent p-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none min-h-[90px]"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  handleStartFromDiscovery()
                }
              }}
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/40 pt-2.5">
            <div className="flex items-center gap-1.5">
              {/* Attachment Button (+) */}
              <div className="relative">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-foreground"
                  onClick={() => setImporterModalOpen(true)}
                  title="Import existing site or attach assets"
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </div>

              {/* Design System Selector */}
              <div className="flex items-center rounded-lg border border-border bg-secondary/50 px-2 py-1 text-xs">
                <Palette className="mr-1.5 h-3 w-3 text-cyan-400" />
                <select
                  value={designSystem}
                  onChange={(e) => setDesignSystem(e.target.value as any)}
                  className="bg-transparent text-xs text-foreground focus:outline-none cursor-pointer"
                >
                  <option value="Obsidian Telecom">Obsidian Telecom</option>
                  <option value="Modernist">Modernist Clean</option>
                  <option value="Vibrant Gigabit">Vibrant Gigabit</option>
                  <option value="Enterprise Sleek">Enterprise Sleek</option>
                </select>
              </div>

              {/* Model / Agent Selector */}
              <div className="hidden sm:flex items-center rounded-lg border border-border bg-secondary/50 px-2 py-1 text-xs">
                <Bot className="mr-1.5 h-3 w-3 text-purple-400" />
                <select
                  value={selectedAgent}
                  onChange={(e) => setSelectedAgent(e.target.value)}
                  className="bg-transparent text-xs text-foreground focus:outline-none cursor-pointer"
                >
                  <option value="Marketing Designer Agent (Claude 3.5)">Marketing Agent (Claude 3.5)</option>
                  <option value="Fiber Feasibility Specialist (GPT-4o)">Feasibility Agent (GPT-4o)</option>
                  <option value="Creative Strategist (DeepSeek V3)">Creative Strategist</option>
                </select>
              </div>
            </div>

            <Button
              size="sm"
              onClick={handleStartFromDiscovery}
              className="h-8 w-8 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-cyan-950 p-0 flex items-center justify-center font-bold"
            >
              <ArrowUp className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Quick Context Action Row (Matches Screenshot 3 "Start with context") */}
        <div className="max-w-2xl mx-auto flex flex-wrap items-center justify-center gap-2 pt-1 text-xs">
          <button
            onClick={() => setImporterModalOpen(true)}
            className="flex items-center gap-1.5 rounded-full border border-border bg-secondary/40 px-3 py-1 text-muted-foreground hover:text-cyan-400 hover:border-cyan-500/40 transition-colors"
          >
            <Globe className="h-3 w-3 text-cyan-400" />
            <span>Import Existing Website</span>
          </button>
          <button
            onClick={() => {
              setSelectedZone(LM_FIBER_ZONES[0])
              setActiveStudioView("canvas")
              handleSendChatMessage("Attach Cape Town LM fiber map with Octotel trench lines")
            }}
            className="flex items-center gap-1.5 rounded-full border border-border bg-secondary/40 px-3 py-1 text-muted-foreground hover:text-emerald-400 hover:border-emerald-500/40 transition-colors"
          >
            <MapPin className="h-3 w-3 text-emerald-400" />
            <span>Attach LM Fiber Route Map</span>
          </button>
          <button
            onClick={() => setShareModalOpen(true)}
            className="flex items-center gap-1.5 rounded-full border border-border bg-secondary/40 px-3 py-1 text-muted-foreground hover:text-purple-400 hover:border-purple-500/40 transition-colors"
          >
            <Share2 className="h-3 w-3 text-purple-400" />
            <span>Invite Team to Collaborate</span>
          </button>
        </div>

        {/* Template Section: CHOOSE A TEMPLATE */}
        <div className="max-w-5xl mx-auto space-y-3 pt-6">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Choose a Template
            </span>
            <span className="text-xs text-muted-foreground">South African FTTH/B Optimized</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {templates.map((tpl) => (
              <Card
                key={tpl.id}
                onClick={() => {
                  setPageTitle(tpl.name)
                  setPageSlug(tpl.id.replace("tpl-", ""))
                  setSelectedZone(tpl.zone)
                  setActiveStudioView("canvas")
                }}
                className="cursor-pointer border-border bg-card/60 hover:bg-card hover:border-cyan-500/50 transition-all group"
              >
                <CardContent className="p-4 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="border-cyan-500/30 text-cyan-400 text-[10px]">
                      {tpl.badge}
                    </Badge>
                    <span className="text-[11px] text-muted-foreground">{tpl.category}</span>
                  </div>

                  <div>
                    <h3 className="text-sm font-semibold text-foreground group-hover:text-cyan-400 transition-colors">
                      {tpl.name}
                    </h3>
                    <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
                      {tpl.description}
                    </p>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-border/40 text-[11px] text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <MapPin className="h-3 w-3 text-muted-foreground" />
                      {tpl.zone.city} ({tpl.zone.operator})
                    </span>
                    <span className="text-cyan-400 font-medium group-hover:translate-x-0.5 transition-transform flex items-center gap-0.5">
                      Open <ArrowRight className="h-3 w-3" />
                    </span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        {/* Existing Projects Directory */}
        <div className="max-w-5xl mx-auto space-y-3 pt-6 border-t border-border/40">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">Recent Landing Page Projects</h3>
            <Badge variant="secondary" className="text-xs">
              {initialPages.length || 4} Active Pages
            </Badge>
          </div>

          <div className="divide-y divide-border/40 rounded-lg border border-border bg-card/40">
            {initialPages.map((pg) => (
              <div
                key={pg.id}
                onClick={() => {
                  setCurrentPageId(String(pg.id))
                  setPageTitle(pg.name)
                  setPageSlug(pg.url.replace("/promo/", "").replace("/business/", "").replace("/coverage/", ""))
                  setActiveStudioView("canvas")
                }}
                className="flex items-center justify-between p-3 hover:bg-secondary/30 transition-colors cursor-pointer text-xs"
              >
                <div className="flex items-center gap-3">
                  <div className="rounded-md bg-cyan-500/10 p-2 text-cyan-400">
                    <Globe className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="font-semibold text-foreground">{pg.name}</p>
                    <p className="text-[11px] text-muted-foreground font-mono">{pg.url}</p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Badge
                    className={
                      pg.status === "published"
                        ? "bg-emerald-500/20 text-emerald-400"
                        : "bg-amber-500/20 text-amber-400"
                    }
                  >
                    {pg.status}
                  </Badge>
                  <span className="text-muted-foreground text-[11px]">{pg.views || 0} visits</span>
                  <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Modals */}
        <DomeStudioShareModal
          open={shareModalOpen}
          onOpenChange={setShareModalOpen}
          pageTitle={pageTitle}
          pageSlug={pageSlug}
        />

        <ExistingSiteImporterModal
          open={importerModalOpen}
          onOpenChange={setImporterModalOpen}
          onApplySiteStructure={handleApplyScrapedSite}
        />
      </div>
    )
  }

  // =========================================================================
  // VIEW 2: DUAL-PANE CHAT & LIVE EDITABLE ARTBOARD CANVAS (Matches Screenshot 1 & 3)
  // =========================================================================
  return (
    <div className="flex flex-col h-[850px] rounded-xl border border-border bg-[#090d16] text-foreground overflow-hidden">
      {/* Studio Top Bar */}
      <header className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-[#0d121f]">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setActiveStudioView("discovery")}
            className="text-xs h-8 text-muted-foreground hover:text-foreground"
          >
            ← Hub
          </Button>

          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm text-foreground">{pageTitle}</span>
            <Badge variant="outline" className="border-cyan-500/40 text-cyan-400 text-[10px]">
              {designSystem}
            </Badge>
          </div>
        </div>

        {/* Viewport, Zoom, Share, Publish Controls */}
        <div className="flex items-center gap-2">
          {/* Viewport Mode Switcher */}
          <div className="flex items-center rounded-lg border border-border bg-secondary/40 p-0.5">
            <button
              onClick={() => setViewportMode("desktop")}
              className={`p-1.5 rounded-md text-xs transition-colors ${
                viewportMode === "desktop" ? "bg-cyan-500/20 text-cyan-400 font-medium" : "text-muted-foreground"
              }`}
              title="Desktop View (1280px)"
            >
              <Monitor className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setViewportMode("mobile")}
              className={`p-1.5 rounded-md text-xs transition-colors ${
                viewportMode === "mobile" ? "bg-cyan-500/20 text-cyan-400 font-medium" : "text-muted-foreground"
              }`}
              title="Mobile View (375px)"
            >
              <Smartphone className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setViewportMode("dual")}
              className={`p-1.5 rounded-md text-xs transition-colors ${
                viewportMode === "dual" ? "bg-cyan-500/20 text-cyan-400 font-medium" : "text-muted-foreground"
              }`}
              title="Dual Side-by-Side View"
            >
              <Layers className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Zoom controls */}
          <div className="hidden sm:flex items-center gap-1 text-xs text-muted-foreground border-l border-border pl-2">
            <button
              onClick={() => setZoomLevel((z) => Math.max(50, z - 25))}
              className="px-1 hover:text-foreground"
            >
              -
            </button>
            <span className="text-[11px] font-mono">{zoomLevel}%</span>
            <button
              onClick={() => setZoomLevel((z) => Math.min(125, z + 25))}
              className="px-1 hover:text-foreground"
            >
              +
            </button>
          </div>

          {/* Share Button (Matches Claude Design screenshot) */}
          <Button
            size="sm"
            onClick={() => setShareModalOpen(true)}
            className="text-xs h-8 bg-secondary hover:bg-secondary/80 text-foreground font-medium"
          >
            <Share2 className="mr-1.5 h-3.5 w-3.5" />
            Share
          </Button>

          {/* Publish Live Button */}
          <Button
            size="sm"
            onClick={handleSaveCurrentPage}
            className="text-xs h-8 bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold"
          >
            <Globe className="mr-1.5 h-3.5 w-3.5" />
            Publish Live
          </Button>
        </div>
      </header>

      {/* Main Dual-Pane Workspace */}
      <div className="flex-1 flex overflow-hidden">
        {/* =================================================================== */}
        {/* LEFT PANE: Conversational AI Agent Assistant (Matches Screenshot 1) */}
        {/* =================================================================== */}
        <div className="w-80 lg:w-96 flex flex-col border-r border-border bg-[#0d121f]">
          {/* Agent Persona Header */}
          <div className="p-3 border-b border-border/50 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="h-7 w-7 rounded-full bg-purple-500/20 flex items-center justify-center text-purple-400 font-semibold text-xs">
                <Bot className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-semibold text-foreground leading-tight">
                  {selectedAgent.split(" ")[0]} Designer
                </p>
                <p className="text-[10px] text-emerald-400 flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Orchestrator Linked
                </p>
              </div>
            </div>

            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground"
              onClick={() => setImporterModalOpen(true)}
              title="Import site"
            >
              <Paperclip className="h-3.5 w-3.5" />
            </Button>
          </div>

          {/* Chat Messages Feed */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3 text-xs">
            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex flex-col ${
                  m.role === "user" ? "items-end" : "items-start"
                }`}
              >
                <div
                  className={`max-w-[90%] rounded-lg p-2.5 ${
                    m.role === "user"
                      ? "bg-cyan-500/20 text-cyan-100 border border-cyan-500/30"
                      : "bg-secondary/40 text-foreground border border-border"
                  }`}
                >
                  {m.toolCall && (
                    <div className="mb-1.5 rounded bg-black/40 px-1.5 py-0.5 font-mono text-[10px] text-amber-300">
                      {m.toolCall}
                    </div>
                  )}
                  <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
                </div>
                <span className="text-[9px] text-muted-foreground mt-0.5 px-1">{m.timestamp}</span>
              </div>
            ))}

            {isAgentThinking && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground p-2">
                <RefreshCw className="h-3.5 w-3.5 animate-spin text-cyan-400" />
                <span>Agent analyzing layout & updating canvas...</span>
              </div>
            )}
          </div>

          {/* Quick Action Prompt Chips */}
          <div className="p-2 border-t border-border/40 flex flex-wrap gap-1 bg-[#0b0e17]">
            <button
              onClick={() => handleSendChatMessage("Add Cape Town Northern Suburbs LM fiber map and sync product table")}
              className="rounded bg-secondary/50 px-2 py-0.5 text-[10px] text-muted-foreground hover:text-cyan-400 transition-colors"
            >
              🗺️ Cape Town LM Map
            </button>
            <button
              onClick={() => handleSendChatMessage("Set LM zone to Sandton Vumatel and highlight 500M gaming tier")}
              className="rounded bg-secondary/50 px-2 py-0.5 text-[10px] text-muted-foreground hover:text-cyan-400 transition-colors"
            >
              ⚡ Sandton Vumatel
            </button>
            <button
              onClick={() => handleSendChatMessage("Make the hero headline punchier with uncapped guarantees")}
              className="rounded bg-secondary/50 px-2 py-0.5 text-[10px] text-muted-foreground hover:text-cyan-400 transition-colors"
            >
              ✍️ Punchy Copy
            </button>
          </div>

          {/* Message Input Box */}
          <div className="p-3 border-t border-border bg-[#0a0d16]">
            <form
              onSubmit={(e) => {
                e.preventDefault()
                handleSendChatMessage()
              }}
              className="flex items-center gap-2"
            >
              <Input
                value={chatPrompt}
                onChange={(e) => setChatPrompt(e.target.value)}
                placeholder="Ask agent to modify layout, copy, or map..."
                className="h-9 text-xs bg-secondary/30 text-foreground"
              />
              <Button
                type="submit"
                size="sm"
                disabled={!chatPrompt.trim() || isAgentThinking}
                className="h-9 w-9 p-0 bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-bold"
              >
                <Send className="h-3.5 w-3.5" />
              </Button>
            </form>
          </div>
        </div>

        {/* =================================================================== */}
        {/* RIGHT PANE: Live Interactive Editable Artboard (Matches Screenshot 1 & 4) */}
        {/* =================================================================== */}
        <div className="flex-1 flex flex-col bg-[#06080e] overflow-hidden">
          {/* Canvas Toolbar */}
          <div className="h-10 px-4 border-b border-border/50 flex items-center justify-between bg-[#0b0e17] text-xs">
            {/* Tool selectors */}
            <div className="flex items-center gap-1">
              <button
                onClick={() => setActiveCanvasTool("select")}
                className={`p-1.5 rounded ${
                  activeCanvasTool === "select" ? "bg-cyan-500/20 text-cyan-400" : "text-muted-foreground"
                }`}
                title="Select Tool"
              >
                <MousePointer className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setActiveCanvasTool("hand")}
                className={`p-1.5 rounded ${
                  activeCanvasTool === "hand" ? "bg-cyan-500/20 text-cyan-400" : "text-muted-foreground"
                }`}
                title="Hand Tool"
              >
                <Hand className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setActiveCanvasTool("text")}
                className={`p-1.5 rounded ${
                  activeCanvasTool === "text" ? "bg-cyan-500/20 text-cyan-400" : "text-muted-foreground"
                }`}
                title="Inline Text Edit"
              >
                <Type className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setShowMapBlock(!showMapBlock)}
                className={`p-1.5 rounded flex items-center gap-1 ${
                  showMapBlock ? "bg-emerald-500/20 text-emerald-400" : "text-muted-foreground"
                }`}
                title="Toggle LM Map Block"
              >
                <MapPin className="h-3.5 w-3.5" />
                <span className="text-[10px]">LM Map</span>
              </button>
              <button
                onClick={() => setShowPricingTable(!showPricingTable)}
                className={`p-1.5 rounded flex items-center gap-1 ${
                  showPricingTable ? "bg-blue-500/20 text-blue-400" : "text-muted-foreground"
                }`}
                title="Toggle Pricing Table"
              >
                <Layers className="h-3.5 w-3.5" />
                <span className="text-[10px]">Pricing</span>
              </button>
            </div>

            {/* Quick Status / Feedback */}
            {publishFeedback && (
              <div className="flex items-center gap-1 text-emerald-400 text-xs animate-fade-in font-medium">
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>{publishFeedback}</span>
              </div>
            )}

            <div className="flex items-center gap-2 text-muted-foreground text-[11px]">
              <span>Active Operator: <strong className="text-cyan-400">{selectedZone.operator}</strong></span>
              <span>•</span>
              <span>Latency: <strong className="text-foreground">{selectedZone.averageLatencyMs}ms</strong></span>
            </div>
          </div>

          {/* Canvas Scrollable Area */}
          <div className="flex-1 overflow-auto p-4 sm:p-8 flex justify-center items-start bg-[#05070c]">
            {/* The Actual Rendered Artboard */}
            <div
              style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: "top center" }}
              className={`transition-transform duration-200 bg-[#090d16] rounded-xl border border-border shadow-2xl overflow-hidden ${
                viewportMode === "mobile"
                  ? "w-[375px]"
                  : viewportMode === "dual"
                  ? "w-[1200px] grid grid-cols-1 xl:grid-cols-2 gap-6 p-4"
                  : "w-full max-w-[900px]"
              }`}
            >
              {/* Artboard Section 1: Hero Header */}
              <div className="relative p-6 sm:p-8 border-b border-border/50 bg-gradient-to-b from-cyan-950/20 to-transparent">
                <div className="space-y-4">
                  {/* Badge */}
                  <div className="inline-block">
                    <input
                      value={heroBadge}
                      onChange={(e) => setHeroBadge(e.target.value)}
                      className="rounded-full bg-cyan-500/10 border border-cyan-500/30 px-3 py-1 text-xs font-semibold text-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 cursor-text w-full sm:w-auto"
                    />
                  </div>

                  {/* Headline */}
                  <textarea
                    rows={2}
                    value={heroHeadline}
                    onChange={(e) => setHeroHeadline(e.target.value)}
                    className="w-full text-2xl sm:text-3xl font-bold tracking-tight text-foreground bg-transparent resize-none border-b border-transparent hover:border-border/50 focus:border-cyan-400 focus:outline-none"
                  />

                  {/* Subheadline */}
                  <textarea
                    rows={2}
                    value={heroSubheadline}
                    onChange={(e) => setHeroSubheadline(e.target.value)}
                    className="w-full text-xs sm:text-sm text-muted-foreground bg-transparent resize-none border-b border-transparent hover:border-border/50 focus:border-cyan-400 focus:outline-none"
                  />

                  {/* Address Feasibility Search Bar */}
                  <div className="rounded-lg border border-border bg-card/80 p-2 flex flex-col sm:flex-row gap-2">
                    <div className="relative flex-1">
                      <MapPin className="absolute left-2.5 top-2.5 h-4 w-4 text-cyan-400" />
                      <Input
                        value={customAddressQuery}
                        onChange={(e) => handleLocationSearch(e.target.value)}
                        placeholder="Enter your street or suburb (e.g. Cape Town, Sandton, Umhlanga)..."
                        className="pl-9 text-xs h-9 bg-secondary/30"
                      />
                    </div>
                    <Button
                      size="sm"
                      onClick={() => handleLocationSearch(customAddressQuery)}
                      className="h-9 text-xs bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold"
                    >
                      {ctaButtonText}
                    </Button>
                  </div>
                </div>
              </div>

              {/* Artboard Section 2: Maps (LM files) & Coverage Feasibility */}
              {showMapBlock && (
                <div className="p-6 border-b border-border/50 space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                        <MapPin className="h-4 w-4 text-emerald-400" />
                        Live Fiber Route & Trench Scanner (LM GIS Map)
                      </h4>
                      <p className="text-xs text-muted-foreground">
                        Real-time optical coverage zone: <span className="font-semibold text-foreground">{selectedZone.name}</span>
                      </p>
                    </div>

                    <Badge className="bg-emerald-500/20 text-emerald-400 text-[10px]">
                      {selectedZone.operator} OLT Active
                    </Badge>
                  </div>

                  {/* Interactive Visual Map Simulation */}
                  <div className="relative rounded-lg border border-border bg-[#03060c] p-4 overflow-hidden min-h-[200px] flex flex-col justify-between">
                    {/* SVG Fiber Trench Lines */}
                    <div className="absolute inset-0 pointer-events-none opacity-40">
                      <svg className="w-full h-full">
                        <line x1="20" y1="50" x2="250" y2="120" stroke="#06b6d4" strokeWidth="2" strokeDasharray="4 2" />
                        <line x1="250" y1="120" x2="500" y2="80" stroke="#10b981" strokeWidth="2.5" />
                        <line x1="500" y1="80" x2="800" y2="160" stroke="#06b6d4" strokeWidth="2" />
                        <circle cx="250" cy="120" r="6" fill="#06b6d4" className="animate-ping" />
                        <circle cx="250" cy="120" r="4" fill="#06b6d4" />
                        <circle cx="500" cy="80" r="4" fill="#10b981" />
                      </svg>
                    </div>

                    {/* Zone Selector Chips */}
                    <div className="relative z-10 flex flex-wrap gap-1.5">
                      {LM_FIBER_ZONES.map((zone) => (
                        <button
                          key={zone.id}
                          onClick={() => setSelectedZone(zone)}
                          className={`px-2.5 py-1 rounded text-xs transition-colors ${
                            selectedZone.id === zone.id
                              ? "bg-cyan-500 text-cyan-950 font-semibold shadow"
                              : "bg-secondary/60 text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          {zone.city} ({zone.operator})
                        </button>
                      ))}
                    </div>

                    {/* Coverage Details Card on Map */}
                    <div className="relative z-10 mt-6 grid grid-cols-1 sm:grid-cols-3 gap-2 bg-black/70 backdrop-blur rounded-lg p-2.5 border border-border/50 text-xs">
                      <div>
                        <span className="text-[10px] text-muted-foreground block">Network Splitter</span>
                        <span className="font-semibold text-emerald-400">{selectedZone.splitterCapacity}</span>
                      </div>
                      <div>
                        <span className="text-[10px] text-muted-foreground block">Exchange Gateway</span>
                        <span className="font-mono text-foreground">{selectedZone.oltId}</span>
                      </div>
                      <div>
                        <span className="text-[10px] text-muted-foreground block">Installation SLA</span>
                        <span className="font-semibold text-cyan-400">1 - 3 Business Days</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Artboard Section 3: Dynamic Product Display Based on Location Chosen */}
              {showPricingTable && (
                <div className="p-6 border-b border-border/50 space-y-4">
                  <div className="text-center space-y-1">
                    <h4 className="text-base font-bold text-foreground">
                      Available Packages for {selectedZone.name}
                    </h4>
                    <p className="text-xs text-muted-foreground">
                      Powered by <span className="font-semibold text-cyan-400">{selectedZone.operator}</span> Optical Infrastructure
                    </p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {selectedZone.availableProducts.map((prod) => (
                      <div
                        key={prod.id}
                        onClick={() => setSelectedProduct(prod)}
                        className={`rounded-xl border p-4 cursor-pointer transition-all flex flex-col justify-between ${
                          selectedProduct?.id === prod.id
                            ? "border-cyan-500 bg-cyan-500/10 shadow-lg ring-1 ring-cyan-500"
                            : "border-border bg-card hover:border-border/80"
                        }`}
                      >
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-xs text-foreground">{prod.name}</span>
                            {prod.recommended && (
                              <Badge className="bg-cyan-500 text-cyan-950 text-[9px] font-bold">
                                Popular
                              </Badge>
                            )}
                          </div>

                          <div className="flex items-baseline gap-1">
                            <span className="text-2xl font-bold text-foreground font-mono">
                              R{prod.promoPriceZar || prod.priceZar}
                            </span>
                            <span className="text-xs text-muted-foreground">/mo</span>
                          </div>

                          <p className="text-[11px] text-cyan-400 font-mono">
                            {prod.speedDown} Mbps Down • {prod.speedUp} Mbps Up
                          </p>

                          <ul className="space-y-1 pt-2 border-t border-border/40 text-[11px] text-muted-foreground">
                            {prod.features.map((feat, idx) => (
                              <li key={idx} className="flex items-center gap-1.5">
                                <CheckCircle className="h-3 w-3 text-emerald-400 shrink-0" />
                                <span>{feat}</span>
                              </li>
                            ))}
                          </ul>
                        </div>

                        <Button
                          size="sm"
                          className={`mt-4 w-full text-xs font-semibold ${
                            selectedProduct?.id === prod.id
                              ? "bg-cyan-500 hover:bg-cyan-400 text-cyan-950"
                              : "bg-secondary hover:bg-secondary/80 text-foreground"
                          }`}
                        >
                          Select Package
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Artboard Section 4: Interactive Lead Generation Checkout */}
              {showLeadForm && (
                <div className="p-6 bg-secondary/10 space-y-4">
                  <div className="text-center space-y-1">
                    <h4 className="text-sm font-semibold text-foreground">Order & Feasibility Dispatch</h4>
                    <p className="text-xs text-muted-foreground">
                      Submits directly to CRM queue: <strong className="text-cyan-400">{selectedZone.city} Inbound Feasibility</strong>
                    </p>
                  </div>

                  <form
                    onSubmit={(e) => {
                      e.preventDefault()
                      setLeadSubmitted(true)
                      setTimeout(() => setLeadSubmitted(false), 3500)
                    }}
                    className="max-w-md mx-auto space-y-2.5 rounded-lg border border-border bg-card p-4"
                  >
                    <div>
                      <Label className="text-[11px] text-muted-foreground">Full Name</Label>
                      <Input
                        value={testLeadName}
                        onChange={(e) => setTestLeadName(e.target.value)}
                        className="h-8 text-xs bg-background"
                      />
                    </div>
                    <div>
                      <Label className="text-[11px] text-muted-foreground">Contact Number</Label>
                      <Input
                        value={testLeadPhone}
                        onChange={(e) => setTestLeadPhone(e.target.value)}
                        className="h-8 text-xs bg-background"
                      />
                    </div>
                    <div>
                      <Label className="text-[11px] text-muted-foreground">Selected Package</Label>
                      <div className="rounded border border-border bg-secondary/30 px-2 py-1.5 text-xs text-cyan-400 font-semibold">
                        {selectedProduct?.name} (R{selectedProduct?.promoPriceZar || selectedProduct?.priceZar}/mo)
                      </div>
                    </div>

                    <Button
                      type="submit"
                      size="sm"
                      className="w-full text-xs font-semibold bg-emerald-500 hover:bg-emerald-400 text-emerald-950 mt-2"
                    >
                      {leadSubmitted ? (
                        <>
                          <Check className="mr-1.5 h-3.5 w-3.5" />
                          Lead Dispatched to CRM!
                        </>
                      ) : (
                        "Submit Feasibility Request"
                      )}
                    </Button>
                  </form>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Modals */}
      <DomeStudioShareModal
        open={shareModalOpen}
        onOpenChange={setShareModalOpen}
        pageTitle={pageTitle}
        pageSlug={pageSlug}
      />

      <ExistingSiteImporterModal
        open={importerModalOpen}
        onOpenChange={setImporterModalOpen}
        onApplySiteStructure={handleApplyScrapedSite}
      />
    </div>
  )
}
