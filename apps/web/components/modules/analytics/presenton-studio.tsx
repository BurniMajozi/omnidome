"use client"

import React, { useState, useEffect, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Sparkles,
  Presentation,
  Play,
  Download,
  Copy,
  Check,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Minimize2,
  ExternalLink,
  RefreshCw,
  Plus,
  Trash2,
  FileText,
  Sliders,
  TrendingUp,
  Brain,
  ShieldCheck,
  Activity,
  Layers,
  Edit2,
  CheckCircle,
  Lightbulb,
} from "lucide-react"
import { toast } from "sonner"
import {
  exportToPowerPoint,
  type GeneratedPresentation,
  type PresentationSlide,
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
  // Config state
  const [selectedPreset, setSelectedPreset] = useState("board-review")
  const [customPrompt, setCustomPrompt] = useState("")
  const [slidesCount, setSlidesCount] = useState(6)
  const [theme, setTheme] = useState<GeneratedPresentation["theme"]>("dark-executive")
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
    setGenerationStep("Extracting platform telemetry & metrics...")

    try {
      setTimeout(() => setGenerationStep("Synthesizing deck narrative with Presenton AI..."), 600)
      setTimeout(() => setGenerationStep("Formatting slide layouts & executive notes..."), 1200)

      const res = await fetch("/api/analytics/presentations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: selectedPreset,
          customPrompt: customPrompt.trim(),
          slidesCount,
          theme,
          includeDataSources: selectedDataSources,
        }),
      })

      if (!res.ok) throw new Error("Failed to generate presentation")

      const data = await res.json()
      if (data.presentation) {
        setPresentation(data.presentation)
        setActiveSlideIndex(0)
        toast.success("Presentation generated successfully from platform data!")
      }
    } catch (err) {
      console.error(err)
      toast.error("Generation failed. Please try again.")
    } finally {
      setIsGenerating(false)
      setGenerationStep("")
    }
  }

  const handleExportPptx = async () => {
    if (!presentation) return
    setIsExporting(true)
    try {
      toast.info("Generating PowerPoint (.pptx) file...")
      await exportToPowerPoint(presentation)
      toast.success("PowerPoint presentation downloaded!")
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
        return `## Slide ${idx + 1}: ${s.title}\n*${s.subtitle || ""}*\n\n${kpisText ? kpisText + "\n\n" : ""}${bulletsText}\n\n> **Key Takeaway:** ${s.takeaway || ""}\n\n*Speaker Notes: ${s.speakerNotes || ""}*\n\n---`
      })
      .join("\n\n")

    navigator.clipboard.writeText(`# ${presentation.title}\n\n${md}`)
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
      id: `slide-${Date.now()}`,
      title: "New Strategic Slide",
      subtitle: "Custom operational topic",
      category: "Operations",
      layout: "bullets",
      bullets: [
        "First key insight from platform operations.",
        "Strategic action item for leadership review.",
      ],
      takeaway: "Execution is aligned with platform operational targets.",
      speakerNotes: "Speaker notes for the newly created slide.",
    }
    setPresentation({
      ...presentation,
      slides: [...presentation.slides, newSlide],
    })
    setActiveSlideIndex(presentation.slides.length)
    toast.success("New slide added!")
  }

  const deleteCurrentSlide = () => {
    if (!presentation || presentation.slides.length <= 1) {
      toast.error("A presentation must have at least one slide.")
      return
    }
    const updatedSlides = presentation.slides.filter((_, idx) => idx !== activeSlideIndex)
    setPresentation({ ...presentation, slides: updatedSlides })
    setActiveSlideIndex((prev) => Math.max(0, Math.min(prev, updatedSlides.length - 1)))
    toast.success("Slide removed.")
  }

  return (
    <div className="space-y-6">
      {/* Top Banner & Presenton Engine Status */}
      <div className="relative overflow-hidden rounded-xl border border-violet-500/20 bg-gradient-to-r from-violet-950/40 via-background to-indigo-950/30 p-5 shadow-lg">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-600/20 text-violet-400 border border-violet-500/30">
                <Sparkles className="h-4 w-4" />
              </span>
              <h2 className="text-xl font-bold tracking-tight text-foreground">
                Presenton AI Presentation Studio
              </h2>
              <Badge variant="outline" className="border-violet-500/40 text-violet-300 bg-violet-500/10">
                Powered by Presenton
              </Badge>
            </div>
            <p className="text-xs sm:text-sm text-muted-foreground">
              Generate boardroom-ready presentations on the fly using live OmniDome telemetry, revenue metrics, and AI recommendations.
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {presentonAvailable ? (
              <Badge variant="outline" className="border-emerald-500/40 text-emerald-300 bg-emerald-500/10 gap-1.5 py-1 px-2.5">
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                Presenton Engine: Online
              </Badge>
            ) : (
              <Badge variant="outline" className="border-cyan-500/40 text-cyan-300 bg-cyan-500/10 gap-1.5 py-1 px-2.5">
                <span className="h-2 w-2 rounded-full bg-cyan-400" />
                OmniDome AI Synthesizer Active
              </Badge>
            )}

            <a
              href="https://github.com/presenton/presenton"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors px-2 py-1 rounded-md border border-border/60 hover:bg-secondary/50"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Presenton Repo
            </a>

            {presentonAvailable && (
              <a
                href={presentonUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-violet-400 hover:text-violet-300 font-medium px-2 py-1 rounded-md border border-violet-500/40 hover:bg-violet-950/30"
              >
                Open Presenton Web
              </a>
            )}
          </div>
        </div>
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
                    isSelected ? "border-violet-400 text-violet-300" : "border-border text-muted-foreground"
                  }`}
                >
                  {preset.badge}
                </Badge>
                <span className="text-[10px] text-muted-foreground font-mono">{preset.slides} slides</span>
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
            <div className="md:col-span-6 space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
                <Lightbulb className="h-3.5 w-3.5 text-amber-400" />
                Custom Presentation Focus / Prompt (Optional)
              </label>
              <Input
                placeholder="e.g. Focus on Q4 Johannesburg Fiber expansion & B2B margins..."
                value={customPrompt}
                onChange={(e) => setCustomPrompt(e.target.value)}
                className="h-9 text-xs bg-background/50 border-border"
              />
            </div>

            {/* Slide Count & Visual Theme */}
            <div className="md:col-span-3 space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
                <Layers className="h-3.5 w-3.5 text-blue-400" />
                Deck Theme
              </label>
              <select
                value={theme}
                onChange={(e) => setTheme(e.target.value as any)}
                className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="dark-executive">Midnight Executive (Dark Obsidian)</option>
                <option value="indigo-cyber">Cyber Indigo (Purple & Slate)</option>
                <option value="emerald-clean">Emerald Growth (Mint & Forest)</option>
                <option value="light-corporate">Clean Corporate (Minimalist Light)</option>
              </select>
            </div>

            {/* Slide Count Selector & Generate Button */}
            <div className="md:col-span-3 flex items-end gap-2">
              <div className="w-24 space-y-1.5">
                <label className="text-xs font-semibold text-muted-foreground">Slides</label>
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
                    <span>Generating...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    <span>Generate Deck</span>
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Data Sources Pills */}
          <div className="flex flex-wrap items-center justify-between pt-2 border-t border-border/50 gap-2 text-xs">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-muted-foreground font-medium mr-1">Active Platform Data Feeds:</span>
              {[
                { id: "revenue", label: "MRR & ARPU", icon: TrendingUp },
                { id: "subscribers", label: "Segments & Base", icon: Activity },
                { id: "modules", label: "Health Scores", icon: ShieldCheck },
                { id: "churn", label: "AI Churn & Risk", icon: Brain },
                { id: "sync", label: "Billing-to-RADIUS Sync", icon: CheckCircle },
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
                {isCopied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
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
                        isSelected ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground"
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

            {/* Right Column: 16:9 Slide Canvas */}
            <div className="lg:col-span-9 space-y-4">
              <div
                className={`relative w-full aspect-[16/9] rounded-2xl p-8 sm:p-12 flex flex-col justify-between overflow-hidden shadow-2xl transition-all border ${
                  theme === "dark-executive"
                    ? "bg-[#0d1117] text-[#f0f6fc] border-[#30363d]"
                    : theme === "indigo-cyber"
                    ? "bg-[#0b0f19] text-[#f8fafc] border-[#334155]"
                    : theme === "emerald-clean"
                    ? "bg-[#062016] text-[#ecfdf5] border-[#047857]"
                    : "bg-[#f8fafc] text-[#0f172a] border-[#e2e8f0]"
                }`}
              >
                {/* Background decorative glows */}
                <div className="absolute top-0 right-0 w-96 h-96 bg-primary/10 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20" />
                <div className="absolute bottom-0 left-0 w-80 h-80 bg-violet-500/10 rounded-full blur-3xl pointer-events-none -ml-20 -mb-20" />

                {/* Slide Top Branding Bar */}
                <div className="relative z-10 flex items-center justify-between border-b border-white/10 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-primary shadow-[0_0_8px_rgba(59,130,246,0.8)]" />
                    <span className="text-[11px] font-bold tracking-widest text-primary uppercase">
                      OMNIDOME ANALYTICS & AI PLATFORM
                    </span>
                  </div>
                  {activeSlide.category && (
                    <Badge variant="outline" className="text-[10px] font-mono border-white/20 text-white/80">
                      {activeSlide.category}
                    </Badge>
                  )}
                </div>

                {/* Slide Center Content */}
                <div className="relative z-10 flex-1 my-auto flex flex-col justify-center py-4">
                  {activeSlide.layout === "title" ? (
                    <div className="space-y-4 max-w-3xl">
                      <Badge className="bg-primary/20 text-primary border-primary/40 font-mono text-xs">
                        OmniDome Board Deck
                      </Badge>
                      <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight leading-tight">
                        {activeSlide.title}
                      </h1>
                      {activeSlide.subtitle && (
                        <p className="text-base sm:text-xl text-white/70 font-light">
                          {activeSlide.subtitle}
                        </p>
                      )}
                      <div className="pt-6 flex items-center gap-4 text-xs text-white/50 border-t border-white/10">
                        <span>Generated live from platform telemetry</span>
                        <span>•</span>
                        <span>Executive Intelligence</span>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-6">
                      <div className="space-y-1">
                        <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">
                          {activeSlide.title}
                        </h2>
                        {activeSlide.subtitle && (
                          <p className="text-xs sm:text-sm text-white/70">
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
                              className="rounded-xl p-3.5 bg-white/5 border border-white/10 backdrop-blur-sm space-y-1"
                            >
                              <span className="text-[11px] text-white/60 font-medium block">
                                {kpi.label}
                              </span>
                              <div className="text-xl sm:text-2xl font-extrabold tracking-tight text-white">
                                {kpi.value}
                              </div>
                              {kpi.change && (
                                <span
                                  className={`text-[10px] font-semibold font-mono ${
                                    kpi.isPositive ? "text-emerald-400" : "text-orange-400"
                                  }`}
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
                            <li key={bIdx} className="flex items-start gap-2.5 text-xs sm:text-sm leading-relaxed text-white/90">
                              <span className="h-1.5 w-1.5 rounded-full bg-primary mt-2 shrink-0 shadow-[0_0_6px_rgba(59,130,246,0.6)]" />
                              <span>{bullet}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>

                {/* Slide Bottom Bar */}
                <div className="relative z-10 flex items-center justify-between pt-3 border-t border-white/10 text-[11px] text-white/50">
                  {activeSlide.takeaway ? (
                    <div className="flex items-center gap-2 text-white/90 font-medium">
                      <span className="text-emerald-400 font-bold uppercase text-[10px] tracking-wider">
                        Takeaway:
                      </span>
                      <span className="line-clamp-1">{activeSlide.takeaway}</span>
                    </div>
                  ) : (
                    <span>CONFIDENTIAL — BOARD LEVEL INTELLIGENCE</span>
                  )}

                  <span className="font-mono text-white/60">
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
                      Executive Speaker Notes & Talking Points
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
              <CardTitle className="text-base font-bold">Edit Slide {activeSlideIndex + 1}</CardTitle>
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

      {/* Fullscreen Presentation Mode */}
      {isFullscreen && presentation && activeSlide && (
        <div className="fixed inset-0 z-50 bg-black flex flex-col justify-between p-8 sm:p-12 overflow-hidden select-none">
          {/* Top Bar */}
          <div className="flex items-center justify-between text-white/50 text-xs">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              <span className="font-bold tracking-widest uppercase">
                OMNIDOME PRESENTATION MODE
              </span>
            </div>
            <div className="flex items-center gap-4">
              <span className="font-mono">
                Slide {activeSlideIndex + 1} of {presentation.slides.length}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 text-white hover:bg-white/10"
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
                <Badge className="bg-primary/20 text-primary border-primary/40 text-sm px-3 py-1">
                  Executive Briefing
                </Badge>
                <h1 className="text-5xl sm:text-7xl font-extrabold text-white tracking-tight leading-tight">
                  {activeSlide.title}
                </h1>
                {activeSlide.subtitle && (
                  <p className="text-xl sm:text-2xl text-white/70 max-w-3xl mx-auto font-light">
                    {activeSlide.subtitle}
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-8">
                <div className="space-y-2">
                  <span className="text-xs uppercase tracking-widest text-primary font-mono">
                    {activeSlide.category}
                  </span>
                  <h2 className="text-4xl sm:text-5xl font-extrabold text-white tracking-tight">
                    {activeSlide.title}
                  </h2>
                  {activeSlide.subtitle && (
                    <p className="text-base sm:text-lg text-white/70">{activeSlide.subtitle}</p>
                  )}
                </div>

                {activeSlide.kpis && (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    {activeSlide.kpis.map((kpi, idx) => (
                      <div
                        key={idx}
                        className="rounded-xl p-5 bg-white/10 border border-white/10 space-y-1"
                      >
                        <span className="text-xs text-white/60">{kpi.label}</span>
                        <div className="text-3xl font-black text-white">{kpi.value}</div>
                        {kpi.change && (
                          <span
                            className={`text-xs font-semibold ${
                              kpi.isPositive ? "text-emerald-400" : "text-orange-400"
                            }`}
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
                      <li key={idx} className="flex items-start gap-4 text-lg sm:text-xl text-white/90">
                        <span className="h-2.5 w-2.5 rounded-full bg-primary mt-2 shrink-0" />
                        <span>{bullet}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/* Bottom Bar in Fullscreen */}
          <div className="flex items-center justify-between text-xs text-white/40 border-t border-white/10 pt-4">
            <span>Press Left / Right arrows or Spacebar to advance</span>
            {activeSlide.takeaway && (
              <span className="text-emerald-400 font-semibold">
                KEY TAKEAWAY: {activeSlide.takeaway}
              </span>
            )}
            <div className="flex gap-2">
              <button
                disabled={activeSlideIndex === 0}
                onClick={() => setActiveSlideIndex((prev) => prev - 1)}
                className="px-3 py-1 bg-white/10 rounded hover:bg-white/20 disabled:opacity-30"
              >
                Prev
              </button>
              <button
                disabled={activeSlideIndex === presentation.slides.length - 1}
                onClick={() => setActiveSlideIndex((prev) => prev + 1)}
                className="px-3 py-1 bg-white/10 rounded hover:bg-white/20 disabled:opacity-30"
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
