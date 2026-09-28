"use client"

import React, { useState, useEffect, useRef } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Sparkles,
  Play,
  Download,
  Copy,
  Check,
  ChevronLeft,
  ChevronRight,
  Minimize2,
  ExternalLink,
  RefreshCw,
  Plus,
  Trash2,
  FileText,
  TrendingUp,
  Brain,
  ShieldCheck,
  Activity,
  Layers,
  Edit2,
  CheckCircle,
  Lightbulb,
  Palette,
  Upload,
  Image as ImageIcon,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp,
  X,
  Volume2,
} from "lucide-react"
import { toast } from "sonner"
import {
  type GeneratedPresentation,
  type PresentationSlide,
  type BrandKit,
  type BrandPalette,
  type BrandVoiceTone,
  BRAND_PALETTES,
  BRAND_VOICES,
  BRAND_INGEST_TEMPLATES,
} from "@/lib/presentation-export"

interface PresentonStudioProps {
  onBackToOverview?: () => void
}

const PRESET_TOPICS = [
  {
    id: "board-review",
    title: "Executive Board Review",
    badge: "Most Popular",
    desc: "MRR, ARPU, active subscribers, cross-module health & strategic AI roadmap.",
    slides: 7,
  },
  {
    id: "revenue-growth",
    title: "Revenue & Monetization",
    badge: "Financial",
    desc: "Revenue trends, VAS attach rate, segment ARPU & billing reconciliation.",
    slides: 6,
  },
  {
    id: "retention-churn",
    title: "Retention & Churn Defense",
    badge: "AI Risk",
    desc: "Predictive churn scores, high-risk cohorts, saved customers & AI actions.",
    slides: 6,
  },
  {
    id: "network-sla",
    title: "Network Operations & SLA",
    badge: "Ops & Tech",
    desc: "Fiber uptime, RADIUS sessions, ticket resolution times & field maintenance.",
    slides: 5,
  },
  {
    id: "platform-audit",
    title: "360° Platform Audit",
    badge: "Comprehensive",
    desc: "Health radar across all 8 modules with bottleneck discovery & targets.",
    slides: 8,
  },
]

export function PresentonStudio({ onBackToOverview }: PresentonStudioProps) {
  // Brand Architecture State
  const [brandKit, setBrandKit] = useState<BrandKit>({
    companyName: "OmniDome Networks",
    tagline: "Next-Gen Autonomous Telecom Cloud OS",
    logoUrl: "/logo-new.svg",
    voiceTone: "executive",
    brandGuidelines:
      "Authoritative, data-grounded, metrics-first language. Highlight optical uptime, subscriber unit economics, and AI autonomous operations.",
    palette: BRAND_PALETTES[0],
  })

  const [showBrandDrawer, setShowBrandDrawer] = useState(false)
  const [activeBrandTab, setActiveBrandTab] = useState<"identity" | "voice" | "palette">("identity")
  const [isCustomPalette, setIsCustomPalette] = useState(false)
  const [customPrimary, setCustomPrimary] = useState("#38BDF8")
  const [customAccent, setCustomAccent] = useState("#34D399")
  const [customBg, setCustomBg] = useState("#0D1117")
  const [customText, setCustomText] = useState("#F0F6FC")

  const fileInputRef = useRef<HTMLInputElement>(null)

  // Presentation config state
  const [selectedPreset, setSelectedPreset] = useState("board-review")
  const [customPrompt, setCustomPrompt] = useState("")
  const [slidesCount, setSlidesCount] = useState(6)
  const [selectedDataSources, setSelectedDataSources] = useState<string[]>([
    "revenue",
    "subscribers",
    "modules",
    "churn",
    "sync",
  ])

  // Generation state
  const [isGenerating, setIsGenerating] = useState(false)
  const [generationStep, setGenerationStep] = useState("")
  const [presentation, setPresentation] = useState<GeneratedPresentation | null>(null)
  const [activeSlideIndex, setActiveSlideIndex] = useState(0)
  const [showNotes, setShowNotes] = useState(true)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [isCopied, setIsCopied] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [presentonAvailable, setPresentonAvailable] = useState(false)
  const [presentonUrl, setPresentonUrl] = useState("http://localhost:5000")

  // Editing state
  const [isEditingSlide, setIsEditingSlide] = useState(false)
  const [editTitle, setEditTitle] = useState("")
  const [editSubtitle, setEditSubtitle] = useState("")
  const [editTakeaway, setEditTakeaway] = useState("")

  // Check Presenton service status on mount
  useEffect(() => {
    async function checkPresenton() {
      try {
        const res = await fetch("/api/analytics/presentations")
        if (res.ok) {
          const data = await res.json()
          setPresentonAvailable(data.presentonAvailable)
          if (data.presentonUrl) setPresentonUrl(data.presentonUrl)
        }
      } catch {
        setPresentonAvailable(false)
      }
    }
    checkPresenton()
  }, [])

  // Auto-generate initial presentation once on mount
  useEffect(() => {
    handleGeneratePresentation()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleGeneratePresentation = async () => {
    setIsGenerating(true)
    setGenerationStep(`Aligning narrative to ${brandKit.companyName} brand architecture...`)

    try {
      setTimeout(() => setGenerationStep("Extracting platform telemetry & metrics..."), 400)
      setTimeout(
        () =>
          setGenerationStep(
            `Synthesizing slides with ${brandKit.voiceTone.toUpperCase()} voice tone...`
          ),
        900
      )

      const activePalette = isCustomPalette
        ? {
            id: "custom-palette",
            name: "Custom Brand Palette",
            background: customBg.replace("#", ""),
            primary: customPrimary.replace("#", ""),
            accent: customAccent.replace("#", ""),
            text: customText.replace("#", ""),
            subtext: "94A3B8",
            cardBg: "161B22",
            border: "30363D",
          }
        : brandKit.palette

      const res = await fetch("/api/analytics/presentations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: selectedPreset,
          customPrompt: customPrompt.trim(),
          slidesCount,
          theme: "dark-executive",
          includeDataSources: selectedDataSources,
          brandKit: {
            ...brandKit,
            palette: activePalette,
          },
        }),
      })

      if (!res.ok) throw new Error("Failed to generate presentation")

      const data = await res.json()
      if (data.presentation) {
        setPresentation(data.presentation)
        setActiveSlideIndex(0)
        toast.success(
          `Presentation generated with ${brandKit.companyName} branding!`
        )
      }
    } catch (err) {
      console.error(err)
      toast.error("Generation failed. Please try again.")
    } finally {
      setIsGenerating(false)
      setGenerationStep("")
    }
  }

  // Handle Logo Upload
  const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (file.size > 2 * 1024 * 1024) {
      toast.error("Logo file too large. Please use an image under 2MB.")
      return
    }

    const reader = new FileReader()
    reader.onload = (uploadEvent) => {
      const result = uploadEvent.target?.result as string
      setBrandKit((prev) => ({ ...prev, logoUrl: result }))
      // Update active presentation's brand kit live
      if (presentation) {
        setPresentation({
          ...presentation,
          brandKit: { ...presentation.brandKit, ...brandKit, logoUrl: result },
        })
      }
      toast.success("Company logo successfully uploaded & applied!")
    }
    reader.readAsDataURL(file)
  }

  // Handle Ingest Template Click
  const handleApplyTemplate = (tmpl: (typeof BRAND_INGEST_TEMPLATES)[number]) => {
    const matchedPalette =
      BRAND_PALETTES.find((p) => p.id === tmpl.paletteId) || BRAND_PALETTES[0]
    const updatedKit: BrandKit = {
      ...brandKit,
      companyName: tmpl.companyName,
      tagline: tmpl.tagline,
      voiceTone: tmpl.voiceTone,
      brandGuidelines: tmpl.brandGuidelines,
      palette: matchedPalette,
    }
    setBrandKit(updatedKit)
    setIsCustomPalette(false)
    if (presentation) {
      setPresentation({
        ...presentation,
        brandKit: updatedKit,
      })
    }
    toast.success(`Ingested "${tmpl.name}" brand voice & identity!`)
  }

  // Handle Palette Switch
  const handleSelectPalette = (palette: BrandPalette) => {
    setIsCustomPalette(false)
    const updatedKit = { ...brandKit, palette }
    setBrandKit(updatedKit)
    if (presentation) {
      setPresentation({
        ...presentation,
        brandKit: updatedKit,
      })
    }
  }

  // Apply custom color changes
  const applyCustomColor = (key: "primary" | "accent" | "bg" | "text", hex: string) => {
    setIsCustomPalette(true)
    let p = customPrimary
    let a = customAccent
    let bg = customBg
    let t = customText

    if (key === "primary") {
      setCustomPrimary(hex)
      p = hex
    } else if (key === "accent") {
      setCustomAccent(hex)
      a = hex
    } else if (key === "bg") {
      setCustomBg(hex)
      bg = hex
    } else if (key === "text") {
      setCustomText(hex)
      t = hex
    }

    const updatedPalette: BrandPalette = {
      id: "custom-palette",
      name: "Custom Palette",
      primary: p.replace("#", ""),
      accent: a.replace("#", ""),
      background: bg.replace("#", ""),
      text: t.replace("#", ""),
      subtext: "94A3B8",
      cardBg: bg === "#FFFFFF" || bg.toLowerCase() === "#fff" ? "F8FAFC" : "161B22",
      border: bg === "#FFFFFF" || bg.toLowerCase() === "#fff" ? "E2E8F0" : "30363D",
    }

    const updatedKit = { ...brandKit, palette: updatedPalette }
    setBrandKit(updatedKit)
    if (presentation) {
      setPresentation({
        ...presentation,
        brandKit: updatedKit,
      })
    }
  }

  const handleExportPptx = async () => {
    if (!presentation) return
    setIsExporting(true)
    try {
      toast.info(`Exporting ${brandKit.companyName} PowerPoint (.pptx)...`)
      const { exportToPowerPoint } = await import("@/lib/presentation-export")
      await exportToPowerPoint({
        ...presentation,
        brandKit: {
          ...brandKit,
          palette: isCustomPalette
            ? {
                id: "custom-palette",
                name: "Custom Palette",
                primary: customPrimary.replace("#", ""),
                accent: customAccent.replace("#", ""),
                background: customBg.replace("#", ""),
                text: customText.replace("#", ""),
                subtext: "94A3B8",
                cardBg: "161B22",
                border: "30363D",
              }
            : brandKit.palette,
        },
      })
      toast.success("PowerPoint presentation downloaded with custom branding!")
    } catch (err) {
      console.error(err)
      toast.error("Failed to export PowerPoint")
    } finally {
      setIsExporting(false)
    }
  }

  const handleCopyMarkdown = () => {
    if (!presentation) return
    const md = presentation.slides
      .map((s, idx) => {
        const kpisText = s.kpis
          ? s.kpis.map((k) => `* **${k.label}**: ${k.value} (${k.change || ""})`).join("\n")
          : ""
        const bulletsText = s.bullets ? s.bullets.map((b) => `- ${b}`).join("\n") : ""
        return `## Slide ${idx + 1}: ${s.title}\n*${s.subtitle || ""}*\n\n${
          kpisText ? kpisText + "\n\n" : ""
        }${bulletsText}\n\n> **Key Takeaway:** ${s.takeaway || ""}\n\n*Speaker Notes: ${
          s.speakerNotes || ""
        }*\n\n---`
      })
      .join("\n\n")

    navigator.clipboard.writeText(
      `# ${presentation.title}\n**Brand:** ${brandKit.companyName} | ${brandKit.tagline}\n\n${md}`
    )
    setIsCopied(true)
    toast.success("Presentation markdown copied to clipboard!")
    setTimeout(() => setIsCopied(false), 2500)
  }

  const toggleDataSource = (key: string) => {
    setSelectedDataSources((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    )
  }

  // Keyboard navigation for presentation mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!presentation) return
      if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === " ") {
        e.preventDefault()
        setActiveSlideIndex((prev) => Math.min(presentation.slides.length - 1, prev + 1))
      } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault()
        setActiveSlideIndex((prev) => Math.max(0, prev - 1))
      } else if (e.key === "Escape" && isFullscreen) {
        setIsFullscreen(false)
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [presentation, isFullscreen])

  const activeSlide: PresentationSlide | undefined = presentation?.slides[activeSlideIndex]

  // Editing current slide
  const startEditSlide = () => {
    if (!activeSlide) return
    setEditTitle(activeSlide.title)
    setEditSubtitle(activeSlide.subtitle || "")
    setEditTakeaway(activeSlide.takeaway || "")
    setIsEditingSlide(true)
  }

  const saveEditSlide = () => {
    if (!presentation || !activeSlide) return
    const updatedSlides = [...presentation.slides]
    updatedSlides[activeSlideIndex] = {
      ...activeSlide,
      title: editTitle,
      subtitle: editSubtitle,
      takeaway: editTakeaway,
    }
    setPresentation({ ...presentation, slides: updatedSlides })
    setIsEditingSlide(false)
    toast.success("Slide updated!")
  }

  const addNewSlide = () => {
    if (!presentation) return
    const newSlide: PresentationSlide = {
      id: `custom-slide-${Date.now()}`,
      title: `${brandKit.companyName}: Strategic Opportunity`,
      subtitle: "Custom focus area synthesized with executive brand voice",
      category: "Strategy",
      layout: "bullets",
      bullets: [
        "Identified growth lever aligned with corporate mandate.",
        "High-margin expansion potential with favorable payback period.",
        "Cross-functional synergy across sales and engineering.",
      ],
      takeaway: "Execution readiness is confirmed across operations.",
      speakerNotes: "Present the strategic context and immediate action items.",
    }
    const updated = [...presentation.slides, newSlide]
    setPresentation({ ...presentation, slides: updated })
    setActiveSlideIndex(updated.length - 1)
    toast.success("New slide added to deck!")
  }

  const deleteCurrentSlide = () => {
    if (!presentation || presentation.slides.length <= 1) {
      toast.error("Presentations must contain at least 1 slide.")
      return
    }
    const updated = presentation.slides.filter((_, idx) => idx !== activeSlideIndex)
    setPresentation({ ...presentation, slides: updated })
    setActiveSlideIndex((prev) => Math.min(prev, updated.length - 1))
    toast.info("Slide deleted")
  }

  // Active palette styling helpers
  const activePalette = isCustomPalette
    ? {
        name: "Custom Palette",
        primary: customPrimary.replace("#", ""),
        accent: customAccent.replace("#", ""),
        background: customBg.replace("#", ""),
        text: customText.replace("#", ""),
        subtext: "94A3B8",
        cardBg: customBg === "#FFFFFF" ? "F8FAFC" : "161B22",
        border: customBg === "#FFFFFF" ? "E2E8F0" : "30363D",
      }
    : brandKit.palette

  const canvasBg = `#${activePalette.background}`
  const canvasTextColor = `#${activePalette.text}`
  const canvasPrimary = `#${activePalette.primary}`
  const canvasAccent = `#${activePalette.accent}`
  const canvasCardBg = `#${activePalette.cardBg}`
  const canvasBorder = `#${activePalette.border}`

  return (
    <div className="space-y-5">
      {/* Top Banner & Presenton Engine Status */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-border/70 pb-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="p-1.5 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-600 text-white shadow-sm">
              <Sparkles className="h-4 w-4" />
            </span>
            <h2 className="text-xl font-bold tracking-tight text-foreground">
              Presenton AI Presentation Studio
            </h2>
            <Badge variant="outline" className="border-violet-500/40 text-violet-300 bg-violet-500/10">
              Brand Architecture & Telemetry
            </Badge>
          </div>
          <p className="text-xs sm:text-sm text-muted-foreground">
            Generate boardroom-ready presentations infused with your corporate brand identity, custom palette, logo, and voice tone.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {presentonAvailable ? (
            <Badge
              variant="outline"
              className="border-emerald-500/40 text-emerald-300 bg-emerald-500/10 gap-1.5 py-1 px-2.5"
            >
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              Presenton Engine: Online
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="border-cyan-500/40 text-cyan-300 bg-cyan-500/10 gap-1.5 py-1 px-2.5"
            >
              <span className="h-2 w-2 rounded-full bg-cyan-400" />
              OmniDome AI Synthesizer Active
            </Badge>
          )}

          <a
            href="https://github.com/presenton/presenton"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors px-2.5 py-1 rounded-md border border-border/60 hover:bg-secondary/50"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Presenton Repo
          </a>

          {presentonAvailable && (
            <a
              href={presentonUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-violet-400 hover:text-violet-300 font-medium px-2.5 py-1 rounded-md border border-violet-500/40 hover:bg-violet-950/30"
            >
              Open Web UI
            </a>
          )}
        </div>
      </div>

      {/* BRAND ARCHITECTURE STRIP & CUSTOMIZER TRIGGER */}
      <div className="rounded-xl border border-violet-500/30 bg-gradient-to-r from-violet-950/30 via-background to-indigo-950/20 p-3.5 shadow-sm transition-all">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            {/* Logo Preview Avatar */}
            <div className="h-10 w-10 rounded-lg bg-card border border-border flex items-center justify-center overflow-hidden shrink-0 shadow-sm p-1">
              {brandKit.logoUrl ? (
                <img
                  src={brandKit.logoUrl}
                  alt={brandKit.companyName}
                  className="max-h-full max-w-full object-contain"
                />
              ) : (
                <ImageIcon className="h-5 w-5 text-muted-foreground" />
              )}
            </div>

            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-bold text-foreground truncate">
                  {brandKit.companyName}
                </span>
                <Badge
                  variant="outline"
                  className="text-[10px] capitalize border-primary/40 text-primary bg-primary/10 py-0"
                >
                  {brandKit.voiceTone} Tone
                </Badge>
                <div className="flex items-center gap-1 border border-border/80 rounded-full px-1.5 py-0.5 bg-background/60">
                  <span
                    className="h-2.5 w-2.5 rounded-full shadow-sm"
                    style={{ backgroundColor: canvasPrimary }}
                    title={`Primary: ${canvasPrimary}`}
                  />
                  <span
                    className="h-2.5 w-2.5 rounded-full shadow-sm"
                    style={{ backgroundColor: canvasAccent }}
                    title={`Accent: ${canvasAccent}`}
                  />
                  <span
                    className="h-2.5 w-2.5 rounded-full border border-white/20"
                    style={{ backgroundColor: canvasBg }}
                    title={`Background: ${canvasBg}`}
                  />
                  <span className="text-[10px] font-mono text-muted-foreground ml-1">
                    {isCustomPalette ? "Custom" : brandKit.palette.name}
                  </span>
                </div>
              </div>
              <p className="text-xs text-muted-foreground truncate mt-0.5">
                {brandKit.tagline || "Brand guidelines active for all slide decks"}
              </p>
            </div>
          </div>

          <Button
            variant={showBrandDrawer ? "default" : "outline"}
            size="sm"
            onClick={() => setShowBrandDrawer((prev) => !prev)}
            className="h-8 gap-1.5 text-xs font-semibold shrink-0 border-violet-500/40 text-violet-300 hover:text-white hover:bg-violet-600"
          >
            <Palette className="h-3.5 w-3.5" />
            {showBrandDrawer ? "Hide Brand Studio" : "Brand Identity & Colors"}
            {showBrandDrawer ? (
              <ChevronUp className="h-3.5 w-3.5" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>

        {/* EXPANDABLE BRAND ARCHITECTURE STUDIO */}
        {showBrandDrawer && (
          <div className="mt-4 pt-4 border-t border-border/60 space-y-4 animate-in fade-in slide-in-from-top-2 duration-200">
            {/* Tab navigation within brand drawer */}
            <div className="flex items-center gap-2 border-b border-border/40 pb-2">
              <Button
                variant={activeBrandTab === "identity" ? "default" : "ghost"}
                size="sm"
                onClick={() => setActiveBrandTab("identity")}
                className="h-7 text-xs gap-1.5 px-3"
              >
                <ImageIcon className="h-3.5 w-3.5" />
                1. Company & Logo
              </Button>

              <Button
                variant={activeBrandTab === "voice" ? "default" : "ghost"}
                size="sm"
                onClick={() => setActiveBrandTab("voice")}
                className="h-7 text-xs gap-1.5 px-3"
              >
                <Volume2 className="h-3.5 w-3.5" />
                2. Brand Voice & Story Ingestion
              </Button>

              <Button
                variant={activeBrandTab === "palette" ? "default" : "ghost"}
                size="sm"
                onClick={() => setActiveBrandTab("palette")}
                className="h-7 text-xs gap-1.5 px-3"
              >
                <Palette className="h-3.5 w-3.5" />
                3. Color Palette & Look-and-Feel
              </Button>
            </div>

            {/* TAB 1: COMPANY & LOGO */}
            {activeBrandTab === "identity" && (
              <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
                <div className="md:col-span-4 space-y-2">
                  <label className="text-xs font-semibold text-foreground">Company Name</label>
                  <Input
                    value={brandKit.companyName}
                    onChange={(e) => {
                      const updated = { ...brandKit, companyName: e.target.value }
                      setBrandKit(updated)
                      if (presentation) setPresentation({ ...presentation, brandKit: updated })
                    }}
                    placeholder="e.g. Velocity Fiber Networks"
                    className="h-9 text-xs"
                  />
                </div>

                <div className="md:col-span-5 space-y-2">
                  <label className="text-xs font-semibold text-foreground">
                    Company Tagline / Subtitle
                  </label>
                  <Input
                    value={brandKit.tagline}
                    onChange={(e) => {
                      const updated = { ...brandKit, tagline: e.target.value }
                      setBrandKit(updated)
                      if (presentation) setPresentation({ ...presentation, brandKit: updated })
                    }}
                    placeholder="e.g. Next-Gen Gigabit Broadband for South Africa"
                    className="h-9 text-xs"
                  />
                </div>

                <div className="md:col-span-3 space-y-2">
                  <label className="text-xs font-semibold text-foreground flex items-center justify-between">
                    <span>Company Logo</span>
                    {brandKit.logoUrl && (
                      <button
                        onClick={() => {
                          const updated = { ...brandKit, logoUrl: "" }
                          setBrandKit(updated)
                          if (presentation) setPresentation({ ...presentation, brandKit: updated })
                        }}
                        className="text-[10px] text-destructive hover:underline"
                      >
                        Remove
                      </button>
                    )}
                  </label>

                  <div className="flex items-center gap-2">
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={handleLogoUpload}
                      accept="image/png,image/jpeg,image/svg+xml,image/webp"
                      className="hidden"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => fileInputRef.current?.click()}
                      className="w-full h-9 text-xs gap-1.5 justify-center border-dashed border-primary/50 text-primary hover:bg-primary/10"
                    >
                      <Upload className="h-3.5 w-3.5" />
                      Upload Logo (.png, .svg)
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 2: BRAND VOICE & INGESTION */}
            {activeBrandTab === "voice" && (
              <div className="space-y-4">
                {/* Voice Tone Selector */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Volume2 className="h-3.5 w-3.5 text-violet-400" />
                    Select Brand Voice Tone Archetype
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2">
                    {BRAND_VOICES.map((voice) => {
                      const isSelected = brandKit.voiceTone === voice.id
                      return (
                        <button
                          key={voice.id}
                          type="button"
                          onClick={() => {
                            const updated: BrandKit = { ...brandKit, voiceTone: voice.id }
                            setBrandKit(updated)
                            if (presentation)
                              setPresentation({ ...presentation, brandKit: updated })
                          }}
                          className={`text-left p-2.5 rounded-lg border text-xs transition-all ${
                            isSelected
                              ? "border-violet-500 bg-violet-950/30 ring-1 ring-violet-500/50"
                              : "border-border/60 bg-card hover:bg-secondary/40"
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-bold text-foreground truncate">{voice.label}</span>
                            <Badge
                              variant="outline"
                              className={`text-[9px] px-1 py-0 ${
                                isSelected ? "border-violet-400 text-violet-300" : ""
                              }`}
                            >
                              {voice.badge}
                            </Badge>
                          </div>
                          <p className="text-[10px] text-muted-foreground line-clamp-2">
                            {voice.description}
                          </p>
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Brand Guidelines & Backstory Manifesto */}
                <div className="space-y-2">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                    <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      <FileText className="h-3.5 w-3.5 text-amber-400" />
                      Explain the Brand / Ingest Brand Guidelines & Backstory
                    </label>
                    <span className="text-[11px] text-muted-foreground">
                      Quick Ingest Templates:
                    </span>
                  </div>

                  {/* 1-Click Ingest Presets */}
                  <div className="flex flex-wrap gap-1.5">
                    {BRAND_INGEST_TEMPLATES.map((tmpl) => (
                      <button
                        key={tmpl.name}
                        type="button"
                        onClick={() => handleApplyTemplate(tmpl)}
                        className="text-[11px] font-medium px-2.5 py-1 rounded-md bg-secondary/60 hover:bg-secondary border border-border/80 text-foreground transition-colors"
                      >
                        ⚡ {tmpl.name}
                      </button>
                    ))}
                  </div>

                  <Textarea
                    value={brandKit.brandGuidelines}
                    onChange={(e) => {
                      const updated = { ...brandKit, brandGuidelines: e.target.value }
                      setBrandKit(updated)
                      if (presentation) setPresentation({ ...presentation, brandKit: updated })
                    }}
                    placeholder="Explain the company brand voice, market positioning, target audience, key buzzwords to highlight, and corporate values..."
                    className="text-xs h-20 bg-background/80"
                  />
                </div>
              </div>
            )}

            {/* TAB 3: COLOR PALETTE & LOOK AND FEEL */}
            {activeBrandTab === "palette" && (
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-foreground">
                    Choose Pre-Configured Telecom Brand Palettes:
                  </label>
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
                    {BRAND_PALETTES.map((pal) => {
                      const isSelected = !isCustomPalette && brandKit.palette.id === pal.id
                      return (
                        <button
                          key={pal.id}
                          type="button"
                          onClick={() => handleSelectPalette(pal)}
                          className={`p-2.5 rounded-lg border text-left transition-all relative ${
                            isSelected
                              ? "border-primary bg-primary/10 ring-1 ring-primary/50"
                              : "border-border/60 bg-card hover:bg-secondary/40"
                          }`}
                        >
                          <div className="flex items-center gap-1.5 mb-2">
                            <span
                              className="h-4 w-4 rounded-full shadow-sm"
                              style={{ backgroundColor: `#${pal.primary}` }}
                            />
                            <span
                              className="h-4 w-4 rounded-full shadow-sm"
                              style={{ backgroundColor: `#${pal.accent}` }}
                            />
                            <span
                              className="h-4 w-4 rounded-full border border-white/20"
                              style={{ backgroundColor: `#${pal.background}` }}
                            />
                          </div>
                          <span className="text-xs font-bold text-foreground block truncate">
                            {pal.name}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Custom Palette Sliders / Inputs */}
                <div className="rounded-lg border border-border/80 bg-background/50 p-3 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                      <SlidersHorizontal className="h-3.5 w-3.5 text-primary" />
                      Fine-Tune Custom Brand Colors
                    </span>
                    {isCustomPalette && (
                      <Badge variant="outline" className="text-[10px] text-primary border-primary">
                        Custom Palette Active
                      </Badge>
                    )}
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground block">
                        Primary Brand Color
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={customPrimary}
                          onChange={(e) => applyCustomColor("primary", e.target.value)}
                          className="h-8 w-8 rounded cursor-pointer border border-border bg-transparent"
                        />
                        <Input
                          value={customPrimary}
                          onChange={(e) => applyCustomColor("primary", e.target.value)}
                          className="h-8 text-xs font-mono"
                        />
                      </div>
                    </div>

                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground block">
                        Accent / Highlight Color
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={customAccent}
                          onChange={(e) => applyCustomColor("accent", e.target.value)}
                          className="h-8 w-8 rounded cursor-pointer border border-border bg-transparent"
                        />
                        <Input
                          value={customAccent}
                          onChange={(e) => applyCustomColor("accent", e.target.value)}
                          className="h-8 text-xs font-mono"
                        />
                      </div>
                    </div>

                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground block">
                        Slide Background
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={customBg}
                          onChange={(e) => applyCustomColor("bg", e.target.value)}
                          className="h-8 w-8 rounded cursor-pointer border border-border bg-transparent"
                        />
                        <Input
                          value={customBg}
                          onChange={(e) => applyCustomColor("bg", e.target.value)}
                          className="h-8 text-xs font-mono"
                        />
                      </div>
                    </div>

                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground block">
                        Text Color
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={customText}
                          onChange={(e) => applyCustomColor("text", e.target.value)}
                          className="h-8 w-8 rounded cursor-pointer border border-border bg-transparent"
                        />
                        <Input
                          value={customText}
                          onChange={(e) => applyCustomColor("text", e.target.value)}
                          className="h-8 text-xs font-mono"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Preset Topics Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {PRESET_TOPICS.map((preset) => {
          const isSelected = selectedPreset === preset.id
          return (
            <button
              key={preset.id}
              onClick={() => {
                setSelectedPreset(preset.id)
                setSlidesCount(preset.slides)
              }}
              className={`text-left p-3.5 rounded-xl border transition-all relative ${
                isSelected
                  ? "border-violet-500 bg-violet-950/20 shadow-[0_0_15px_rgba(139,92,246,0.15)] ring-1 ring-violet-500/50"
                  : "border-border/60 bg-card/60 hover:bg-secondary/40 hover:border-border"
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <Badge
                  variant="outline"
                  className={`text-[10px] px-1.5 py-0 ${
                    isSelected
                      ? "border-violet-400 text-violet-300"
                      : "border-border text-muted-foreground"
                  }`}
                >
                  {preset.badge}
                </Badge>
                <span className="text-[10px] text-muted-foreground font-mono">
                  {preset.slides} slides
                </span>
              </div>
              <h4 className="text-xs font-bold text-foreground line-clamp-1">{preset.title}</h4>
              <p className="text-[11px] text-muted-foreground mt-1 line-clamp-2 leading-relaxed">
                {preset.desc}
              </p>
            </button>
          )
        })}
      </div>

      {/* Controls Drawer & Generator Trigger */}
      <Card className="border-border/70 bg-card">
        <CardContent className="p-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
            {/* Custom Prompt / Strategic Focus */}
            <div className="md:col-span-7 space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
                <Lightbulb className="h-3.5 w-3.5 text-amber-400" />
                Strategic Focus & Prompt (Optional)
              </label>
              <Input
                placeholder={`e.g. Emphasize ${brandKit.companyName}'s Q4 Enterprise fiber rollout & ARPU...`}
                value={customPrompt}
                onChange={(e) => setCustomPrompt(e.target.value)}
                className="h-9 text-xs bg-background/50 border-border"
              />
            </div>

            {/* Slide Count Selector & Generate Button */}
            <div className="md:col-span-5 flex items-end gap-2">
              <div className="w-28 space-y-1.5">
                <label className="text-xs font-semibold text-muted-foreground">Slide Count</label>
                <select
                  value={slidesCount}
                  onChange={(e) => setSlidesCount(Number(e.target.value))}
                  className="w-full h-9 rounded-md border border-border bg-background px-2 text-xs text-foreground focus:outline-none"
                >
                  <option value={4}>4 Slides</option>
                  <option value={5}>5 Slides</option>
                  <option value={6}>6 Slides</option>
                  <option value={7}>7 Slides</option>
                  <option value={8}>8 Slides</option>
                  <option value={10}>10 Slides</option>
                </select>
              </div>

              <Button
                onClick={handleGeneratePresentation}
                disabled={isGenerating}
                className="flex-1 h-9 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-semibold gap-1.5 shadow-md"
              >
                {isGenerating ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    <span>Synthesizing...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    <span>Generate Branded Deck</span>
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Data Sources Pills */}
          <div className="flex flex-wrap items-center justify-between pt-2 border-t border-border/50 gap-2 text-xs">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-muted-foreground font-medium mr-1">
                Active Telemetry Feeds:
              </span>
              {[
                { id: "revenue", label: "MRR & ARPU", icon: TrendingUp },
                { id: "subscribers", label: "Segments & Base", icon: Activity },
                { id: "modules", label: "Health Scores", icon: ShieldCheck },
                { id: "churn", label: "AI Churn & Risk", icon: Brain },
                { id: "sync", label: "Billing Reconciliation", icon: CheckCircle },
              ].map((src) => {
                const active = selectedDataSources.includes(src.id)
                const Icon = src.icon
                return (
                  <button
                    key={src.id}
                    onClick={() => toggleDataSource(src.id)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors border ${
                      active
                        ? "bg-violet-500/15 border-violet-500/40 text-violet-300"
                        : "bg-secondary/40 border-border/60 text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <Icon className="h-3 w-3" />
                    {src.label}
                  </button>
                )
              })}
            </div>

            {isGenerating && generationStep && (
              <span className="text-xs text-violet-400 font-medium animate-pulse">
                {generationStep}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Main Presentation Viewer */}
      {presentation && activeSlide ? (
        <div className="space-y-4">
          {/* Deck Action Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 bg-secondary/20 p-2.5 rounded-lg border border-border/60">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="font-mono text-xs">
                {activeSlideIndex + 1} / {presentation.slides.length}
              </Badge>
              <h3 className="text-sm font-bold text-foreground line-clamp-1">
                {presentation.title}
              </h3>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 text-xs"
                onClick={() => setShowNotes((prev) => !prev)}
              >
                <FileText className="h-3.5 w-3.5" />
                {showNotes ? "Hide Notes" : "Speaker Notes"}
              </Button>

              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 text-xs"
                onClick={startEditSlide}
              >
                <Edit2 className="h-3.5 w-3.5" />
                Edit Slide
              </Button>

              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 text-xs"
                onClick={handleCopyMarkdown}
              >
                {isCopied ? (
                  <Check className="h-3.5 w-3.5 text-emerald-400" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
                Copy Deck
              </Button>

              <Button
                onClick={handleExportPptx}
                disabled={isExporting}
                size="sm"
                className="h-8 gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 text-white font-semibold shadow-sm"
              >
                <Download className="h-3.5 w-3.5" />
                Export PowerPoint (.pptx)
              </Button>

              <Button
                variant="default"
                size="sm"
                className="h-8 gap-1.5 text-xs bg-primary hover:bg-primary/90 text-primary-foreground font-semibold"
                onClick={() => setIsFullscreen(true)}
              >
                <Play className="h-3.5 w-3.5" />
                Present
              </Button>
            </div>
          </div>

          {/* Split Layout: Slide Thumbnails + Main 16:9 Canvas */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            {/* Left Column: Slide Thumbnails */}
            <div className="lg:col-span-3 space-y-2 max-h-[620px] overflow-y-auto pr-1">
              <div className="flex items-center justify-between pb-1 px-1">
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Slides Overview
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={addNewSlide}
                  className="h-6 px-2 text-[11px] gap-1 text-primary hover:text-primary"
                >
                  <Plus className="h-3 w-3" />
                  Add Slide
                </Button>
              </div>

              {presentation.slides.map((slide, idx) => {
                const isSelected = activeSlideIndex === idx
                return (
                  <button
                    key={slide.id}
                    onClick={() => setActiveSlideIndex(idx)}
                    className={`w-full text-left p-2.5 rounded-lg border transition-all flex items-start gap-2.5 ${
                      isSelected
                        ? "border-primary bg-primary/10 shadow-sm"
                        : "border-border/60 bg-card hover:bg-secondary/40"
                    }`}
                  >
                    <span
                      className={`text-xs font-mono font-bold px-1.5 py-0.5 rounded ${
                        isSelected
                          ? "bg-primary text-primary-foreground"
                          : "bg-secondary text-muted-foreground"
                      }`}
                    >
                      {idx + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
                          {slide.category || "Slide"}
                        </span>
                        <Badge variant="outline" className="text-[9px] py-0 px-1 border-border">
                          {slide.layout}
                        </Badge>
                      </div>
                      <h5 className="text-xs font-semibold text-foreground truncate mt-0.5">
                        {slide.title}
                      </h5>
                    </div>
                  </button>
                )
              })}
            </div>

            {/* Right Column: 16:9 Slide Canvas with Dynamic Brand Palette & Logo */}
            <div className="lg:col-span-9 space-y-4">
              <div
                className="relative w-full aspect-[16/9] rounded-2xl p-8 sm:p-12 flex flex-col justify-between overflow-hidden shadow-2xl transition-all border"
                style={{
                  backgroundColor: canvasBg,
                  color: canvasTextColor,
                  borderColor: canvasBorder,
                }}
              >
                {/* Background decorative glows matching brand colors */}
                <div
                  className="absolute top-0 right-0 w-96 h-96 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20 opacity-20"
                  style={{ backgroundColor: canvasPrimary }}
                />
                <div
                  className="absolute bottom-0 left-0 w-80 h-80 rounded-full blur-3xl pointer-events-none -ml-20 -mb-20 opacity-15"
                  style={{ backgroundColor: canvasAccent }}
                />

                {/* Slide Top Branding Bar */}
                <div
                  className="relative z-10 flex items-center justify-between border-b pb-3"
                  style={{ borderColor: `${canvasTextColor}20` }}
                >
                  <div className="flex items-center gap-2.5">
                    {brandKit.logoUrl ? (
                      <img
                        src={brandKit.logoUrl}
                        alt={brandKit.companyName}
                        className="h-6 max-w-[130px] object-contain"
                      />
                    ) : (
                      <span
                        className="h-2.5 w-2.5 rounded-full shadow-sm"
                        style={{ backgroundColor: canvasPrimary }}
                      />
                    )}
                    <span
                      className="text-[11px] font-bold tracking-widest uppercase"
                      style={{ color: canvasPrimary }}
                    >
                      {brandKit.companyName}
                    </span>
                  </div>

                  {activeSlide.category && (
                    <Badge
                      variant="outline"
                      className="text-[10px] font-mono border-current"
                      style={{ color: canvasAccent }}
                    >
                      {activeSlide.category}
                    </Badge>
                  )}
                </div>

                {/* Slide Center Content */}
                <div className="relative z-10 flex-1 my-auto flex flex-col justify-center py-4">
                  {activeSlide.layout === "title" ? (
                    <div className="space-y-4 max-w-3xl">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge
                          className="font-mono text-xs border"
                          style={{
                            backgroundColor: `${canvasPrimary}20`,
                            color: canvasPrimary,
                            borderColor: `${canvasPrimary}40`,
                          }}
                        >
                          {brandKit.companyName} Board Deck
                        </Badge>
                        <Badge
                          variant="outline"
                          className="text-[10px] capitalize"
                          style={{ color: canvasAccent, borderColor: `${canvasAccent}40` }}
                        >
                          {brandKit.voiceTone} Tone
                        </Badge>
                      </div>

                      <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight leading-tight">
                        {activeSlide.title}
                      </h1>

                      {activeSlide.subtitle && (
                        <p
                          className="text-base sm:text-xl font-light"
                          style={{ color: `${canvasTextColor}B0` }}
                        >
                          {activeSlide.subtitle}
                        </p>
                      )}

                      <div
                        className="pt-6 flex items-center gap-4 text-xs border-t"
                        style={{
                          borderColor: `${canvasTextColor}20`,
                          color: `${canvasTextColor}80`,
                        }}
                      >
                        <span>{brandKit.tagline || "Autonomous Platform Telemetry"}</span>
                        <span>•</span>
                        <span>Brand Architecture: {brandKit.voiceTone.toUpperCase()}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-6">
                      <div className="space-y-1">
                        <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">
                          {activeSlide.title}
                        </h2>
                        {activeSlide.subtitle && (
                          <p className="text-xs sm:text-sm" style={{ color: `${canvasTextColor}90` }}>
                            {activeSlide.subtitle}
                          </p>
                        )}
                      </div>

                      {/* KPI Grid if present */}
                      {activeSlide.kpis && activeSlide.kpis.length > 0 && (
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                          {activeSlide.kpis.map((kpi, kIdx) => (
                            <div
                              key={kIdx}
                              className="rounded-xl p-3.5 backdrop-blur-sm space-y-1 border"
                              style={{
                                backgroundColor: canvasCardBg,
                                borderColor: canvasBorder,
                              }}
                            >
                              <span
                                className="text-[11px] font-medium block"
                                style={{ color: `${canvasTextColor}80` }}
                              >
                                {kpi.label}
                              </span>
                              <div
                                className="text-xl sm:text-2xl font-extrabold tracking-tight"
                                style={{ color: canvasPrimary }}
                              >
                                {kpi.value}
                              </div>
                              {kpi.change && (
                                <span
                                  className="text-[10px] font-semibold font-mono"
                                  style={{
                                    color: kpi.isPositive ? canvasAccent : "#EF4444",
                                  }}
                                >
                                  {kpi.change}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Bullets List */}
                      {activeSlide.bullets && activeSlide.bullets.length > 0 && (
                        <ul className="space-y-2.5">
                          {activeSlide.bullets.map((bullet, bIdx) => (
                            <li
                              key={bIdx}
                              className="flex items-start gap-2.5 text-xs sm:text-sm leading-relaxed"
                              style={{ color: `${canvasTextColor}E0` }}
                            >
                              <span
                                className="h-1.5 w-1.5 rounded-full mt-2 shrink-0 shadow-sm"
                                style={{ backgroundColor: canvasPrimary }}
                              />
                              <span>{bullet}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>

                {/* Slide Bottom Bar */}
                <div
                  className="relative z-10 flex items-center justify-between pt-3 border-t text-[11px]"
                  style={{
                    borderColor: `${canvasTextColor}20`,
                    color: `${canvasTextColor}80`,
                  }}
                >
                  {activeSlide.takeaway ? (
                    <div className="flex items-center gap-2 font-medium">
                      <span
                        className="font-bold uppercase text-[10px] tracking-wider"
                        style={{ color: canvasAccent }}
                      >
                        Takeaway:
                      </span>
                      <span className="line-clamp-1">{activeSlide.takeaway}</span>
                    </div>
                  ) : (
                    <span>
                      CONFIDENTIAL — {brandKit.companyName.toUpperCase()}{" "}
                      {brandKit.tagline ? `• ${brandKit.tagline}` : ""}
                    </span>
                  )}

                  <span className="font-mono">
                    {activeSlideIndex + 1} / {presentation.slides.length}
                  </span>
                </div>
              </div>

              {/* Navigation Controls */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 gap-1"
                    disabled={activeSlideIndex === 0}
                    onClick={() => setActiveSlideIndex((prev) => prev - 1)}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 gap-1"
                    disabled={activeSlideIndex === presentation.slides.length - 1}
                    onClick={() => setActiveSlideIndex((prev) => prev + 1)}
                  >
                    Next
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={deleteCurrentSlide}
                    className="h-8 text-xs text-destructive hover:text-destructive hover:bg-destructive/10 gap-1"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Delete Slide
                  </Button>
                </div>
              </div>

              {/* Speaker Notes Drawer */}
              {showNotes && activeSlide.speakerNotes && (
                <Card className="border-border/60 bg-card">
                  <CardHeader className="py-2.5 px-4 border-b border-border/40">
                    <CardTitle className="text-xs font-semibold flex items-center gap-2 text-muted-foreground uppercase tracking-wider">
                      <FileText className="h-3.5 w-3.5 text-primary" />
                      Executive Speaker Notes ({brandKit.voiceTone.toUpperCase()} Voice)
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-4 text-xs sm:text-sm text-foreground/90 leading-relaxed font-sans">
                    {activeSlide.speakerNotes}
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {/* Edit Slide Modal / Dialog */}
      {isEditingSlide && activeSlide && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-lg border-border bg-card shadow-2xl">
            <CardHeader className="border-b border-border">
              <CardTitle className="text-base font-bold">
                Edit Slide {activeSlideIndex + 1}
              </CardTitle>
              <CardDescription className="text-xs">
                Modify slide title, subtitle, and executive takeaway.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold">Slide Title</label>
                <Input
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  className="text-sm"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold">Subtitle / Context</label>
                <Input
                  value={editSubtitle}
                  onChange={(e) => setEditSubtitle(e.target.value)}
                  className="text-sm"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold">Key Takeaway</label>
                <Textarea
                  value={editTakeaway}
                  onChange={(e) => setEditTakeaway(e.target.value)}
                  className="text-xs h-20"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" size="sm" onClick={() => setIsEditingSlide(false)}>
                  Cancel
                </Button>
                <Button size="sm" onClick={saveEditSlide}>
                  Save Changes
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Fullscreen Presentation Mode with Brand Styling */}
      {isFullscreen && presentation && activeSlide && (
        <div
          className="fixed inset-0 z-50 flex flex-col justify-between p-8 sm:p-12 overflow-hidden select-none"
          style={{ backgroundColor: canvasBg, color: canvasTextColor }}
        >
          {/* Top Bar */}
          <div
            className="flex items-center justify-between text-xs pb-3 border-b"
            style={{ borderColor: `${canvasTextColor}20` }}
          >
            <div className="flex items-center gap-2.5">
              {brandKit.logoUrl && (
                <img
                  src={brandKit.logoUrl}
                  alt={brandKit.companyName}
                  className="h-6 max-w-[120px] object-contain"
                />
              )}
              <span
                className="font-bold tracking-widest uppercase"
                style={{ color: canvasPrimary }}
              >
                {brandKit.companyName}
              </span>
            </div>
            <div className="flex items-center gap-4">
              <span className="font-mono">
                Slide {activeSlideIndex + 1} of {presentation.slides.length}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 hover:bg-white/10"
                style={{ color: canvasTextColor }}
                onClick={() => setIsFullscreen(false)}
              >
                <Minimize2 className="h-4 w-4" />
                Exit
              </Button>
            </div>
          </div>

          {/* Large Slide Center Canvas */}
          <div className="max-w-5xl mx-auto w-full space-y-8 my-auto">
            {activeSlide.layout === "title" ? (
              <div className="space-y-6 text-center">
                <Badge
                  className="border text-sm px-3 py-1 font-mono"
                  style={{
                    backgroundColor: `${canvasPrimary}20`,
                    color: canvasPrimary,
                    borderColor: `${canvasPrimary}40`,
                  }}
                >
                  {brandKit.companyName} Strategic Briefing
                </Badge>
                <h1 className="text-5xl sm:text-7xl font-extrabold tracking-tight leading-tight">
                  {activeSlide.title}
                </h1>
                {activeSlide.subtitle && (
                  <p
                    className="text-xl sm:text-2xl max-w-3xl mx-auto font-light"
                    style={{ color: `${canvasTextColor}B0` }}
                  >
                    {activeSlide.subtitle}
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-8">
                <div className="space-y-2">
                  <span
                    className="text-xs uppercase tracking-widest font-mono"
                    style={{ color: canvasAccent }}
                  >
                    {activeSlide.category}
                  </span>
                  <h2 className="text-4xl sm:text-5xl font-extrabold tracking-tight">
                    {activeSlide.title}
                  </h2>
                  {activeSlide.subtitle && (
                    <p className="text-base sm:text-lg" style={{ color: `${canvasTextColor}90` }}>
                      {activeSlide.subtitle}
                    </p>
                  )}
                </div>

                {activeSlide.kpis && (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    {activeSlide.kpis.map((kpi, idx) => (
                      <div
                        key={idx}
                        className="rounded-xl p-5 border space-y-1"
                        style={{
                          backgroundColor: canvasCardBg,
                          borderColor: canvasBorder,
                        }}
                      >
                        <span className="text-xs" style={{ color: `${canvasTextColor}80` }}>
                          {kpi.label}
                        </span>
                        <div
                          className="text-3xl font-black"
                          style={{ color: canvasPrimary }}
                        >
                          {kpi.value}
                        </div>
                        {kpi.change && (
                          <span
                            className="text-xs font-semibold"
                            style={{
                              color: kpi.isPositive ? canvasAccent : "#EF4444",
                            }}
                          >
                            {kpi.change}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {activeSlide.bullets && (
                  <ul className="space-y-4">
                    {activeSlide.bullets.map((bullet, idx) => (
                      <li
                        key={idx}
                        className="flex items-start gap-4 text-lg sm:text-xl leading-relaxed"
                        style={{ color: `${canvasTextColor}E0` }}
                      >
                        <span
                          className="h-2.5 w-2.5 rounded-full mt-2 shrink-0 shadow-sm"
                          style={{ backgroundColor: canvasPrimary }}
                        />
                        <span>{bullet}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/* Bottom Bar in Fullscreen */}
          <div
            className="flex items-center justify-between text-xs border-t pt-4"
            style={{
              borderColor: `${canvasTextColor}20`,
              color: `${canvasTextColor}80`,
            }}
          >
            <span>
              CONFIDENTIAL — {brandKit.companyName.toUpperCase()}{" "}
              {brandKit.tagline ? `• ${brandKit.tagline}` : ""}
            </span>
            {activeSlide.takeaway && (
              <span className="font-semibold" style={{ color: canvasAccent }}>
                KEY TAKEAWAY: {activeSlide.takeaway}
              </span>
            )}
            <div className="flex gap-2">
              <button
                disabled={activeSlideIndex === 0}
                onClick={() => setActiveSlideIndex((prev) => prev - 1)}
                className="px-3 py-1 rounded border border-white/20 hover:bg-white/10 disabled:opacity-30"
              >
                Prev
              </button>
              <button
                disabled={activeSlideIndex === presentation.slides.length - 1}
                onClick={() => setActiveSlideIndex((prev) => prev + 1)}
                className="px-3 py-1 rounded border border-white/20 hover:bg-white/10 disabled:opacity-30"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
