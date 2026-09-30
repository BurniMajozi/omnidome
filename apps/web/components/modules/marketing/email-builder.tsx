"use client"

import React, { useState, useEffect, useRef } from "react"
import {
  Sparkles, Send, Eye, Code, Edit3, Download, Upload, Smartphone, Monitor,
  Maximize2, Minimize2, Plus, Trash2, Copy, ArrowUp, ArrowDown, ChevronDown,
  Layers, Check, Settings, Archive as ArchiveIcon, Mail, Palette, Sliders,
  HelpCircle, ExternalLink, RefreshCw, X, FileText, Image as ImageIcon
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { type EmailTemplate } from "@/lib/marketing-api"

export interface EmailBlock {
  id: string
  type: "heading" | "paragraph" | "illustration" | "button" | "divider" | "spacer" | "image"
  content?: string
  fontSize?: number
  textAlign?: "left" | "center" | "right"
  color?: string
  buttonUrl?: string
  buttonText?: string
  buttonColor?: string
  buttonTextColor?: string
  imageUrl?: string
  imageAlt?: string
}

export interface EmailDesignStyles {
  backdropColor: string
  canvasColor: string
  canvasBorderColor: string
  canvasBorderRadius: number
  fontFamily: string
}

const DEFAULT_BLOCKS: EmailBlock[] = [
  {
    id: "block-1",
    type: "heading",
    content: "Hello world",
    fontSize: 24,
    textAlign: "left",
    color: "#18181b",
  },
  {
    id: "block-2",
    type: "paragraph",
    content: "Self-host and manage your own newsletter system with ease. Manage millions of subscribers on a tiny VPS instance with minimal resources.",
    fontSize: 15,
    textAlign: "left",
    color: "#3f3f46",
  },
  {
    id: "block-3",
    type: "paragraph",
    content: "Compose e-mails with the drag-and-drop visual editor, as richtext, raw HTML, plaintext, or markdown.",
    fontSize: 15,
    textAlign: "left",
    color: "#3f3f46",
  },
  {
    id: "block-4",
    type: "illustration",
    textAlign: "center",
  },
]

const DEFAULT_STYLES: EmailDesignStyles = {
  backdropColor: "#f4f4f5",
  canvasColor: "#ffffff",
  canvasBorderColor: "#e4e4e7",
  canvasBorderRadius: 0,
  fontFamily: "Modern sans",
}

interface EmailBuilderProps {
  initialTemplate?: EmailTemplate | null
  onSave?: (template: { name: string; subject: string; body_html: string; category?: string; styles?: EmailDesignStyles }) => Promise<void | boolean> | void | boolean
  onStartCampaign?: (campaignData: { name: string; subject: string; body_html: string; segment?: string }) => Promise<void> | void
  onBack?: () => void
  embedded?: boolean
}

export function EmailBuilder({
  initialTemplate,
  onSave,
  onStartCampaign,
  onBack,
  embedded = false,
}: EmailBuilderProps) {
  // Campaign & Template Metadata
  const [templateName, setTemplateName] = useState(initialTemplate?.name || "Own your newsletter")
  const [subject, setSubject] = useState(initialTemplate?.subject || "Hello world — welcome to our newsletter")
  const [activeSubTab, setActiveSubTab] = useState<"campaign" | "content" | "archive">("content")
  const [format, setFormat] = useState<"visual" | "html" | "markdown" | "plaintext">("visual")
  const [deviceView, setDeviceView] = useState<"desktop" | "mobile">("desktop")
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [sidebarTab, setSidebarTab] = useState<"styles" | "inspect">("styles")

  // Content state
  const [blocks, setBlocks] = useState<EmailBlock[]>(DEFAULT_BLOCKS)
  const [styles, setStyles] = useState<EmailDesignStyles>(DEFAULT_STYLES)
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>("block-1")
  const [rawHtml, setRawHtml] = useState<string>("")
  const [showCodeView, setShowCodeView] = useState(false)

  // Preview dialog & Tags menu
  const [showPreviewModal, setShowPreviewModal] = useState(false)
  const [showTagsMenu, setShowTagsMenu] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [importHtmlInput, setImportHtmlInput] = useState("")
  const [isSaving, setIsSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)

  // Campaign Settings tab state
  const [campaignSegment, setCampaignSegment] = useState("All subscribers")
  const [fromName, setFromName] = useState("OminiDome News")
  const [fromEmail, setFromEmail] = useState("newsletter@omnidome.co.za")
  const [trackOpens, setTrackOpens] = useState(true)
  const [trackClicks, setTrackClicks] = useState(true)

  const selectedBlock = blocks.find((b) => b.id === selectedBlockId) || null

  // F9 Keyboard shortcut for preview
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "F9") {
        e.preventDefault()
        setShowPreviewModal((prev) => !prev)
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  // If initial template loaded with HTML, initialize or generate
  useEffect(() => {
    if (initialTemplate) {
      setTemplateName(initialTemplate.name)
      if (initialTemplate.subject) setSubject(initialTemplate.subject)
      if (initialTemplate.body_html) {
        setRawHtml(initialTemplate.body_html)
      }
    }
  }, [initialTemplate])

  // Helper to serialize blocks to HTML
  const generateHtml = (): string => {
    const fontStack =
      styles.fontFamily === "Modern sans"
        ? "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
        : styles.fontFamily === "Classic serif"
        ? "Georgia, Cambria, 'Times New Roman', Times, serif"
        : styles.fontFamily === "Monospace"
        ? "'SF Mono', Monaco, Menlo, Consolas, monospace"
        : "'Inter', sans-serif"

    const blocksHtml = blocks
      .map((b) => {
        if (b.type === "heading") {
          return `<h1 style="font-size: ${b.fontSize || 24}px; font-weight: 700; color: ${b.color || "#18181b"}; text-align: ${b.textAlign || "left"}; margin: 0 0 16px 0;">${b.content || ""}</h1>`
        }
        if (b.type === "paragraph") {
          return `<p style="font-size: ${b.fontSize || 15}px; line-height: 1.6; color: ${b.color || "#3f3f46"}; text-align: ${b.textAlign || "left"}; margin: 0 0 16px 0;">${b.content || ""}</p>`
        }
        if (b.type === "button") {
          return `<div style="text-align: ${b.textAlign || "center"}; margin: 20px 0;">
            <a href="${b.buttonUrl || "#"}" style="background-color: ${b.buttonColor || "#0066cc"}; color: ${b.buttonTextColor || "#ffffff"}; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; display: inline-block;">${b.buttonText || "Call to Action"}</a>
          </div>`
        }
        if (b.type === "divider") {
          return `<hr style="border: none; border-top: 1px solid #e4e4e7; margin: 24px 0;" />`
        }
        if (b.type === "spacer") {
          return `<div style="height: 24px;"></div>`
        }
        if (b.type === "illustration") {
          return `<div style="text-align: center; margin: 24px 0;">
            <svg viewBox="0 0 400 240" width="340" height="200" style="max-width: 100%; height: auto; display: inline-block;" xmlns="http://www.w3.org/2000/svg">
              <circle cx="280" cy="80" r="32" stroke="#18181b" stroke-width="2.5" fill="none" />
              <path d="M280 36 L280 20 M280 124 L280 140 M236 80 L220 80 M324 80 L340 80 M248 48 L236 36 M312 112 L324 124 M248 112 L236 124 M312 48 L324 36" stroke="#18181b" stroke-width="2.5" stroke-linecap="round" />
              <path d="M190 60 Q205 45 220 60 Q235 45 250 60" stroke="#18181b" stroke-width="2" fill="none" stroke-linecap="round" />
              <path d="M150 90 Q160 78 170 90 Q180 78 190 90" stroke="#18181b" stroke-width="2" fill="none" stroke-linecap="round" />
              <path d="M60 170 Q110 130 160 170 T260 170 T360 170" stroke="#18181b" stroke-width="2.5" fill="none" stroke-linecap="round" />
              <path d="M80 195 Q140 160 200 195 T320 195" stroke="#18181b" stroke-width="2" fill="none" stroke-linecap="round" />
              <path d="M110 140 Q130 110 150 140 Q170 120 190 140 Q210 130 220 150" stroke="#18181b" stroke-width="2" fill="none" stroke-linecap="round" />
            </svg>
          </div>`
        }
        return ""
      })
      .join("\n")

    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${templateName}</title>
</head>
<body style="margin: 0; padding: 40px 10px; background-color: ${styles.backdropColor}; font-family: ${fontStack};">
  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
    <tr>
      <td align="center">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: ${styles.canvasColor}; border: 1px solid ${styles.canvasBorderColor}; border-radius: ${styles.canvasBorderRadius}px; padding: 40px 32px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
          <tr>
            <td>
              ${blocksHtml}
              <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e4e4e7; text-align: center; font-size: 12px; color: #a1a1aa;">
                <p>Sent with listmonk & OminiDome · <a href="{{ .UnsubscribeURL }}" style="color: #71717a; text-decoration: underline;">Unsubscribe</a></p>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>`
  }

  const handleSave = async () => {
    setIsSaving(true)
    try {
      const html = generateHtml()
      let ok: void | boolean = true
      if (onSave) {
        ok = await onSave({
          name: templateName,
          subject,
          body_html: html,
          category: "newsletter",
          styles,
        })
      }
      // The parent returns false when the server rejected the save: show no success flash.
      if (ok !== false) {
        setSaveSuccess(true)
        setTimeout(() => setSaveSuccess(false), 2500)
      }
    } finally {
      setIsSaving(false)
    }
  }

  const handleStartCampaign = () => {
    const html = generateHtml()
    if (onStartCampaign) {
      onStartCampaign({
        name: templateName,
        subject,
        body_html: html,
        segment: campaignSegment,
      })
    }
  }

  const handleAddBlock = (type: EmailBlock["type"]) => {
    const newBlock: EmailBlock = {
      id: `block-${Date.now()}`,
      type,
      content:
        type === "heading"
          ? "New Section Header"
          : type === "paragraph"
          ? "Write your compelling message here. You can customize font size, alignment, and styling in the sidebar."
          : type === "button"
          ? "Click here"
          : undefined,
      fontSize: type === "heading" ? 20 : 15,
      textAlign: "left",
      color: type === "heading" ? "#18181b" : "#3f3f46",
      buttonText: "Learn More",
      buttonUrl: "https://omnidome.co.za",
      buttonColor: "#0066cc",
      buttonTextColor: "#ffffff",
    }
    setBlocks([...blocks, newBlock])
    setSelectedBlockId(newBlock.id)
    setSidebarTab("inspect")
  }

  const updateSelectedBlock = (updates: Partial<EmailBlock>) => {
    if (!selectedBlockId) return
    setBlocks(blocks.map((b) => (b.id === selectedBlockId ? { ...b, ...updates } : b)))
  }

  const handleMoveBlock = (id: string, direction: "up" | "down") => {
    const idx = blocks.findIndex((b) => b.id === id)
    if (idx === -1) return
    const targetIdx = direction === "up" ? idx - 1 : idx + 1
    if (targetIdx < 0 || targetIdx >= blocks.length) return
    const updated = [...blocks]
    const temp = updated[idx]
    updated[idx] = updated[targetIdx]
    updated[targetIdx] = temp
    setBlocks(updated)
  }

  const handleDuplicateBlock = (id: string) => {
    const block = blocks.find((b) => b.id === id)
    if (!block) return
    const copyBlock: EmailBlock = {
      ...block,
      id: `block-${Date.now()}`,
    }
    const idx = blocks.findIndex((b) => b.id === id)
    const updated = [...blocks]
    updated.splice(idx + 1, 0, copyBlock)
    setBlocks(updated)
    setSelectedBlockId(copyBlock.id)
  }

  const handleDeleteBlock = (id: string) => {
    if (blocks.length <= 1) return
    const updated = blocks.filter((b) => b.id !== id)
    setBlocks(updated)
    if (selectedBlockId === id) {
      setSelectedBlockId(updated[0]?.id || null)
    }
  }

  const insertMergeTag = (tag: string) => {
    if (!selectedBlock) return
    if (selectedBlock.content !== undefined) {
      updateSelectedBlock({ content: (selectedBlock.content || "") + " " + tag })
    }
    setShowTagsMenu(false)
  }

  const downloadHtml = () => {
    const html = generateHtml()
    const blob = new Blob([html], { type: "text/html" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${templateName.toLowerCase().replace(/\s+/g, "-")}.html`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className={`flex flex-col bg-background text-foreground border rounded-xl overflow-hidden shadow-sm ${isFullscreen ? "fixed inset-0 z-50 rounded-none" : "min-h-[750px]"}`}>
      {/* Top Header Bar matching listmonk */}
      <div className="flex items-center justify-between px-6 py-3 border-b bg-card">
        <div className="flex items-center gap-3">
          {/* listmonk logo / badge */}
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-full border-2 border-blue-600 flex items-center justify-center">
              <div className="h-2 w-2 rounded-full bg-blue-600" />
            </div>
            <span className="font-semibold text-lg tracking-tight text-foreground">listmonk</span>
          </div>
          <span className="text-muted-foreground/40">|</span>
          <span className="text-xs text-muted-foreground font-medium">OminiDome Campaign Engine</span>
        </div>

        <div className="flex items-center gap-2">
          {onBack && (
            <Button variant="ghost" size="sm" onClick={onBack} className="text-xs">
              Back
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="h-8 w-8 p-0"
            title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
          >
            {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* Campaign Details Header Row */}
      <div className="px-6 py-4 border-b bg-card/60 flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs">
            <span className="bg-muted px-2.5 py-0.5 rounded-full font-mono text-muted-foreground">Draft</span>
            <span className="text-muted-foreground font-mono">ID: 2</span>
            <span className="text-muted-foreground/70 font-mono hidden sm:inline">UUID: bb7d0bf2-7faa-4465-b129-cc8a2ed4a448</span>
          </div>
          <input
            type="text"
            value={templateName}
            onChange={(e) => setTemplateName(e.target.value)}
            className="text-2xl font-bold bg-transparent border-b border-transparent hover:border-border focus:border-primary focus:outline-none transition-colors w-full max-w-md py-0.5"
            placeholder="Own your newsletter"
          />
        </div>

        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={handleSave} disabled={isSaving} className="gap-1.5">
            {saveSuccess ? <Check className="h-4 w-4 text-emerald-500" /> : <Sparkles className="h-4 w-4 text-blue-500" />}
            {saveSuccess ? "Saved!" : isSaving ? "Saving..." : "Save Template"}
          </Button>
          <Button
            size="sm"
            onClick={handleStartCampaign}
            className="bg-[#0066cc] hover:bg-[#0052a3] text-white gap-2 px-4 shadow-sm font-medium"
          >
            <Send className="h-4 w-4" /> Start campaign
          </Button>
        </div>
      </div>

      {/* Tabs Navigation: Campaign, Content, Archive */}
      <div className="border-b px-6 bg-card/40 flex items-center justify-between">
        <div className="flex items-center space-x-6 text-sm">
          <button
            onClick={() => setActiveSubTab("campaign")}
            className={`py-3 flex items-center gap-2 border-b-2 font-medium transition-colors ${
              activeSubTab === "campaign"
                ? "border-blue-600 text-blue-600 dark:text-blue-400"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Mail className="h-4 w-4" /> Campaign
          </button>
          <button
            onClick={() => setActiveSubTab("content")}
            className={`py-3 flex items-center gap-2 border-b-2 font-medium transition-colors ${
              activeSubTab === "content"
                ? "border-blue-600 text-blue-600 dark:text-blue-400"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Layers className="h-4 w-4" /> Content
          </button>
          <button
            onClick={() => setActiveSubTab("archive")}
            className={`py-3 flex items-center gap-2 border-b-2 font-medium transition-colors ${
              activeSubTab === "archive"
                ? "border-blue-600 text-blue-600 dark:text-blue-400"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <ArchiveIcon className="h-4 w-4" /> Archive
          </button>
        </div>
      </div>

      {/* Subtab: Campaign Settings */}
      {activeSubTab === "campaign" && (
        <div className="p-8 max-w-3xl mx-auto space-y-6 flex-1">
          <div className="space-y-4 bg-card border rounded-xl p-6">
            <h3 className="font-semibold text-base">Campaign Details</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5 sm:col-span-2">
                <label className="text-xs font-medium text-muted-foreground">Subject Line</label>
                <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Subject line for email..." />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">From Name</label>
                <Input value={fromName} onChange={(e) => setFromName(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">From Email Address</label>
                <Input value={fromEmail} onChange={(e) => setFromEmail(e.target.value)} />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <label className="text-xs font-medium text-muted-foreground">Target Audience / Segment</label>
                <select
                  value={campaignSegment}
                  onChange={(e) => setCampaignSegment(e.target.value)}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                >
                  <option value="All subscribers">All subscribers (Broadcast)</option>
                  <option value="Residential">Residential Estate HOA</option>
                  <option value="Commercial">Commercial Guarding Clients</option>
                  <option value="High Intent Leads">High Intent Leads</option>
                  <option value="Dormant">Dormant 30+ Days</option>
                </select>
              </div>
            </div>
          </div>

          <div className="space-y-4 bg-card border rounded-xl p-6">
            <h3 className="font-semibold text-base">Tracking & Delivery</h3>
            <div className="flex flex-col gap-3">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={trackOpens} onChange={(e) => setTrackOpens(e.target.checked)} className="rounded" />
                <span>Track email opens with 1px transparent beacon</span>
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={trackClicks} onChange={(e) => setTrackClicks(e.target.checked)} className="rounded" />
                <span>Rewrite and track link click-throughs</span>
              </label>
            </div>
          </div>
        </div>
      )}

      {/* Subtab: Archive */}
      {activeSubTab === "archive" && (
        <div className="p-8 max-w-3xl mx-auto space-y-6 flex-1">
          <div className="bg-card border rounded-xl p-6 space-y-4">
            <h3 className="font-semibold text-base">Public Archive</h3>
            <p className="text-sm text-muted-foreground">
              Make this newsletter publicly viewable on your archive web page at:
            </p>
            <div className="flex items-center gap-2 p-2.5 bg-muted rounded-md font-mono text-xs">
              <span className="text-muted-foreground">https://omnidome.co.za/archive/</span>
              <span className="font-semibold">{templateName.toLowerCase().replace(/\s+/g, "-")}</span>
            </div>
            <Button variant="outline" size="sm" onClick={() => window.open("#", "_blank")}>
              <ExternalLink className="h-4 w-4 mr-2" /> View Archive Page
            </Button>
          </div>
        </div>
      )}

      {/* Subtab: Content (Visual Builder matching image) */}
      {activeSubTab === "content" && (
        <div className="flex flex-col flex-1">
          {/* Format and preview bar matching listmonk */}
          <div className="px-6 py-3 border-b bg-card/20 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              {/* Format dropdown with floating border label */}
              <div className="relative inline-flex items-center">
                <span className="absolute -top-2 left-2 bg-background px-1 text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                  Format
                </span>
                <select
                  value={format}
                  onChange={(e) => setFormat(e.target.value as any)}
                  className="rounded-md border bg-background pl-3 pr-8 py-1.5 text-sm font-medium focus:ring-1 focus:ring-primary focus:outline-none appearance-none cursor-pointer"
                >
                  <option value="visual">Visual</option>
                  <option value="html">Raw HTML</option>
                  <option value="markdown">Markdown</option>
                  <option value="plaintext">Plaintext</option>
                </select>
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground absolute right-2.5 pointer-events-none" />
              </div>

              {/* Import visual template button */}
              <button
                onClick={() => setShowImportModal(true)}
                className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1.5"
              >
                <Upload className="h-3.5 w-3.5" /> Import visual template
              </button>
            </div>

            {/* Preview [F9] Button */}
            <Button
              size="sm"
              onClick={() => setShowPreviewModal(true)}
              className="bg-[#0066cc] hover:bg-[#0052a3] text-white gap-2 font-medium px-4 h-9 shadow-sm"
            >
              <Eye className="h-4 w-4" /> Preview <span className="text-[10px] opacity-80 uppercase border border-white/30 rounded px-1 ml-0.5 font-mono">F9</span>
            </Button>
          </div>

          {/* Builder Workspace: Canvas + Right Sidebar */}
          <div className="flex flex-1 overflow-hidden">
            {/* Main Center Area: Toolbar & Canvas */}
            <div className="flex-1 flex flex-col overflow-y-auto bg-muted/20">
              {/* Toolbar directly above canvas */}
              <div className="max-w-[700px] w-full mx-auto px-4 pt-4">
                <div className="flex items-center justify-between bg-card border rounded-t-lg px-3 py-1.5 shadow-xs">
                  <div className="flex items-center gap-1">
                    <Button
                      variant={!showCodeView ? "secondary" : "ghost"}
                      size="sm"
                      onClick={() => setShowCodeView(false)}
                      className="h-8 w-8 p-0"
                      title="Visual Edit Mode"
                    >
                      <Edit3 className="h-4 w-4" />
                    </Button>
                    <Button
                      variant={showCodeView ? "secondary" : "ghost"}
                      size="sm"
                      onClick={() => {
                        setRawHtml(generateHtml())
                        setShowCodeView(true)
                      }}
                      className="h-8 w-8 p-0"
                      title="Code Editor"
                    >
                      <Code className="h-4 w-4" />
                    </Button>

                    <div className="relative">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowTagsMenu(!showTagsMenu)}
                        className="h-8 px-2 text-xs font-mono"
                        title="Insert Personalization Tag"
                      >
                        {`{ }`}
                      </Button>
                      {showTagsMenu && (
                        <div className="absolute left-0 mt-1 w-56 rounded-md border bg-popover p-1 shadow-lg z-50 text-xs">
                          <div className="px-2 py-1 font-semibold text-muted-foreground text-[10px] uppercase">Personalization Tags</div>
                          {[
                            { label: "Subscriber First Name", tag: "{{ .Subscriber.FirstName }}" },
                            { label: "Subscriber Email", tag: "{{ .Subscriber.Email }}" },
                            { label: "Unsubscribe URL", tag: "{{ .UnsubscribeURL }}" },
                            { label: "Track Link URL", tag: "{{ .TrackLink }}" },
                            { label: "Current Year", tag: "{{ .CurrentYear }}" },
                          ].map((item) => (
                            <button
                              key={item.tag}
                              onClick={() => insertMergeTag(item.tag)}
                              className="w-full text-left px-2 py-1.5 rounded hover:bg-muted font-mono flex flex-col"
                            >
                              <span>{item.label}</span>
                              <span className="text-[10px] text-muted-foreground">{item.tag}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="sm" onClick={downloadHtml} className="h-8 w-8 p-0" title="Export HTML">
                      <Download className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setShowImportModal(true)} className="h-8 w-8 p-0" title="Import HTML">
                      <Upload className="h-4 w-4" />
                    </Button>

                    <div className="h-4 w-px bg-border mx-1" />

                    <Button
                      variant={deviceView === "desktop" ? "secondary" : "ghost"}
                      size="sm"
                      onClick={() => setDeviceView("desktop")}
                      className="h-8 w-8 p-0"
                      title="Desktop View"
                    >
                      <Monitor className="h-4 w-4" />
                    </Button>
                    <Button
                      variant={deviceView === "mobile" ? "secondary" : "ghost"}
                      size="sm"
                      onClick={() => setDeviceView("mobile")}
                      className="h-8 w-8 p-0"
                      title="Mobile View"
                    >
                      <Smartphone className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>

              {/* Canvas Backdrop with rendered newsletter */}
              <div
                className="flex-1 p-6 flex justify-center items-start overflow-y-auto"
                style={{ backgroundColor: styles.backdropColor }}
              >
                {showCodeView ? (
                  <div className="w-full max-w-2xl bg-card border rounded-b-lg p-4 font-mono text-xs">
                    <textarea
                      value={rawHtml}
                      onChange={(e) => setRawHtml(e.target.value)}
                      rows={22}
                      className="w-full h-full bg-transparent border-0 font-mono text-xs focus:outline-none resize-none leading-relaxed"
                    />
                  </div>
                ) : (
                  <div
                    className={`transition-all duration-200 border shadow-md ${
                      deviceView === "mobile" ? "w-[375px]" : "w-full max-w-[620px]"
                    }`}
                    style={{
                      backgroundColor: styles.canvasColor,
                      borderColor: styles.canvasBorderColor,
                      borderRadius: `${styles.canvasBorderRadius}px`,
                      fontFamily:
                        styles.fontFamily === "Modern sans"
                          ? "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
                          : styles.fontFamily === "Classic serif"
                          ? "Georgia, serif"
                          : styles.fontFamily === "Monospace"
                          ? "monospace"
                          : "sans-serif",
                    }}
                  >
                    <div className="p-8 sm:p-10 space-y-6">
                      {blocks.map((block) => (
                        <div
                          key={block.id}
                          onClick={() => {
                            setSelectedBlockId(block.id)
                            setSidebarTab("inspect")
                          }}
                          className={`relative group rounded p-2 transition-all cursor-pointer ${
                            selectedBlockId === block.id
                              ? "ring-2 ring-blue-500 bg-blue-50/20"
                              : "hover:bg-muted/40"
                          }`}
                        >
                          {/* Block action hover pills */}
                          {selectedBlockId === block.id && (
                            <div className="absolute -top-3.5 right-2 bg-blue-600 text-white text-[10px] px-2 py-0.5 rounded shadow flex items-center gap-1 z-10 font-sans">
                              <span>{block.type}</span>
                            </div>
                          )}

                          {block.type === "heading" && (
                            <h1
                              style={{
                                fontSize: `${block.fontSize || 24}px`,
                                color: block.color || "#18181b",
                                textAlign: block.textAlign || "left",
                              }}
                              className="font-bold leading-tight outline-none"
                              contentEditable
                              suppressContentEditableWarning
                              onBlur={(e) => updateSelectedBlock({ content: e.currentTarget.textContent || "" })}
                            >
                              {block.content}
                            </h1>
                          )}

                          {block.type === "paragraph" && (
                            <p
                              style={{
                                fontSize: `${block.fontSize || 15}px`,
                                color: block.color || "#3f3f46",
                                textAlign: block.textAlign || "left",
                              }}
                              className="leading-relaxed outline-none"
                              contentEditable
                              suppressContentEditableWarning
                              onBlur={(e) => updateSelectedBlock({ content: e.currentTarget.textContent || "" })}
                            >
                              {block.content}
                            </p>
                          )}

                          {block.type === "illustration" && (
                            <div className="py-4 flex justify-center items-center">
                              {/* Exact Hand-Drawn Sun & Doodles matching the listmonk screenshot */}
                              <svg
                                viewBox="0 0 420 260"
                                className="w-full max-w-[360px] text-zinc-900 dark:text-zinc-800"
                                fill="none"
                                xmlns="http://www.w3.org/2000/svg"
                              >
                                {/* Concentric circular sun in top right */}
                                <circle cx="310" cy="80" r="30" stroke="currentColor" strokeWidth="2.5" />
                                <circle cx="310" cy="80" r="18" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 3" />
                                
                                {/* Wavy and straight sun rays */}
                                <path d="M310 32 L310 16" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                                <path d="M310 128 L310 144" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                                <path d="M262 80 L246 80" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                                <path d="M358 80 L374 80" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                                
                                <path d="M276 46 Q266 36 260 40" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                                <path d="M344 114 Q354 124 360 120" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                                <path d="M276 114 Q266 124 260 120" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                                <path d="M344 46 Q354 36 360 40" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                                
                                {/* Flying birds */}
                                <path d="M220 70 Q235 55 250 70 Q265 55 280 70" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
                                <path d="M180 95 Q192 82 204 95 Q216 82 228 95" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />

                                {/* Organic doodle swirl waves & clouds */}
                                <path
                                  d="M60 180 Q100 130 140 180 T220 180 T300 180 T380 180"
                                  stroke="currentColor"
                                  strokeWidth="2.5"
                                  strokeLinecap="round"
                                />
                                <path
                                  d="M90 205 Q140 165 190 205 T290 205 T390 205"
                                  stroke="currentColor"
                                  strokeWidth="2"
                                  strokeLinecap="round"
                                />
                                <path
                                  d="M120 140 C140 110 160 130 170 145 C185 120 215 130 220 155"
                                  stroke="currentColor"
                                  strokeWidth="2.2"
                                  strokeLinecap="round"
                                />
                                <path
                                  d="M75 130 Q90 100 115 125"
                                  stroke="currentColor"
                                  strokeWidth="2"
                                  strokeLinecap="round"
                                />
                                <path
                                  d="M140 190 Q170 230 200 190"
                                  stroke="currentColor"
                                  strokeWidth="1.8"
                                  strokeLinecap="round"
                                />
                              </svg>
                            </div>
                          )}

                          {block.type === "button" && (
                            <div style={{ textAlign: block.textAlign || "center" }} className="py-2">
                              <a
                                href={block.buttonUrl || "#"}
                                style={{
                                  backgroundColor: block.buttonColor || "#0066cc",
                                  color: block.buttonTextColor || "#ffffff",
                                }}
                                className="inline-block px-6 py-3 rounded font-semibold text-sm shadow-xs transition-opacity hover:opacity-90"
                              >
                                {block.buttonText || "Call to Action"}
                              </a>
                            </div>
                          )}

                          {block.type === "divider" && (
                            <hr className="border-t border-border my-3" />
                          )}

                          {block.type === "spacer" && <div className="h-6" />}
                        </div>
                      ))}

                      {/* Canvas Unsubscribe Footer */}
                      <div className="pt-8 border-t text-center text-xs text-muted-foreground space-y-1">
                        <p>© 2026 OminiDome. All rights reserved.</p>
                        <p>
                          You received this email because you subscribed to our service.{" "}
                          <a href="#" className="underline hover:text-foreground">Unsubscribe</a>
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Right Sidebar matching listmonk: Styles & Inspect */}
            <div className="w-80 border-l bg-card flex flex-col overflow-y-auto">
              {/* Tab Header: Styles & Inspect */}
              <div className="flex border-b text-sm font-medium">
                <button
                  onClick={() => setSidebarTab("styles")}
                  className={`flex-1 py-3 px-4 text-center transition-colors border-b-2 ${
                    sidebarTab === "styles"
                      ? "border-blue-600 text-blue-600 font-semibold"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Styles
                </button>
                <button
                  onClick={() => setSidebarTab("inspect")}
                  className={`flex-1 py-3 px-4 text-center transition-colors border-b-2 ${
                    sidebarTab === "inspect"
                      ? "border-blue-600 text-blue-600 font-semibold"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Inspect
                </button>
              </div>

              {/* Styles Tab: GLOBAL colors & styling */}
              {sidebarTab === "styles" && (
                <div className="p-5 space-y-6">
                  <div>
                    <h4 className="text-[11px] font-bold text-muted-foreground tracking-wider uppercase mb-4">
                      GLOBAL
                    </h4>

                    {/* Backdrop color */}
                    <div className="space-y-1.5 mb-4">
                      <label className="text-xs text-muted-foreground">Backdrop color</label>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={styles.backdropColor}
                          onChange={(e) => setStyles({ ...styles, backdropColor: e.target.value })}
                          className="h-8 w-8 rounded border border-border cursor-pointer p-0.5 bg-transparent"
                        />
                        <Input
                          type="text"
                          value={styles.backdropColor}
                          onChange={(e) => setStyles({ ...styles, backdropColor: e.target.value })}
                          className="h-8 text-xs font-mono"
                        />
                      </div>
                    </div>

                    {/* Canvas color */}
                    <div className="space-y-1.5 mb-4">
                      <label className="text-xs text-muted-foreground">Canvas color</label>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={styles.canvasColor}
                          onChange={(e) => setStyles({ ...styles, canvasColor: e.target.value })}
                          className="h-8 w-8 rounded border border-border cursor-pointer p-0.5 bg-transparent"
                        />
                        <Input
                          type="text"
                          value={styles.canvasColor}
                          onChange={(e) => setStyles({ ...styles, canvasColor: e.target.value })}
                          className="h-8 text-xs font-mono"
                        />
                      </div>
                    </div>

                    {/* Canvas border color */}
                    <div className="space-y-1.5 mb-4">
                      <label className="text-xs text-muted-foreground">Canvas border color</label>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={styles.canvasBorderColor}
                          onChange={(e) => setStyles({ ...styles, canvasBorderColor: e.target.value })}
                          className="h-8 w-8 rounded border border-border cursor-pointer p-0.5 bg-transparent"
                        />
                        <Input
                          type="text"
                          value={styles.canvasBorderColor}
                          onChange={(e) => setStyles({ ...styles, canvasBorderColor: e.target.value })}
                          className="h-8 text-xs font-mono"
                        />
                      </div>
                    </div>

                    {/* Canvas border radius */}
                    <div className="space-y-1.5 mb-5">
                      <div className="flex justify-between items-center text-xs">
                        <span className="text-muted-foreground">Canvas border radius</span>
                        <span className="font-mono text-muted-foreground">{styles.canvasBorderRadius}px</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="h-4 w-4 border-2 border-dashed border-muted-foreground rounded-xs shrink-0" />
                        <input
                          type="range"
                          min="0"
                          max="32"
                          value={styles.canvasBorderRadius}
                          onChange={(e) => setStyles({ ...styles, canvasBorderRadius: Number(e.target.value) })}
                          className="w-full accent-blue-600"
                        />
                      </div>
                    </div>

                    {/* Font family */}
                    <div className="space-y-1.5">
                      <label className="text-xs text-muted-foreground">Font family</label>
                      <select
                        value={styles.fontFamily}
                        onChange={(e) => setStyles({ ...styles, fontFamily: e.target.value })}
                        className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                      >
                        <option value="Modern sans">Modern sans</option>
                        <option value="Classic serif">Classic serif</option>
                        <option value="Monospace">Monospace</option>
                        <option value="Geometric sans">Geometric sans</option>
                      </select>
                    </div>
                  </div>

                  {/* Add Block Quick Section */}
                  <div className="pt-4 border-t space-y-3">
                    <h4 className="text-[11px] font-bold text-muted-foreground tracking-wider uppercase">
                      INSERT BLOCKS
                    </h4>
                    <div className="grid grid-cols-2 gap-2">
                      <Button variant="outline" size="sm" onClick={() => handleAddBlock("heading")} className="text-xs justify-start h-8">
                        <Plus className="h-3 w-3 mr-1.5" /> Heading
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleAddBlock("paragraph")} className="text-xs justify-start h-8">
                        <Plus className="h-3 w-3 mr-1.5" /> Paragraph
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleAddBlock("button")} className="text-xs justify-start h-8">
                        <Plus className="h-3 w-3 mr-1.5" /> Button
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleAddBlock("illustration")} className="text-xs justify-start h-8">
                        <Plus className="h-3 w-3 mr-1.5" /> Illustration
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleAddBlock("divider")} className="text-xs justify-start h-8">
                        <Plus className="h-3 w-3 mr-1.5" /> Divider
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleAddBlock("spacer")} className="text-xs justify-start h-8">
                        <Plus className="h-3 w-3 mr-1.5" /> Spacer
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {/* Inspect Tab: Edit selected element properties */}
              {sidebarTab === "inspect" && (
                <div className="p-5 space-y-6">
                  {selectedBlock ? (
                    <div className="space-y-5">
                      <div className="flex items-center justify-between">
                        <h4 className="text-[11px] font-bold text-muted-foreground tracking-wider uppercase">
                          INSPECT BLOCK
                        </h4>
                        <Badge variant="outline" className="text-[10px] uppercase font-mono">
                          {selectedBlock.type}
                        </Badge>
                      </div>

                      {/* Content editor */}
                      {selectedBlock.content !== undefined && (
                        <div className="space-y-1.5">
                          <label className="text-xs text-muted-foreground">Text Content</label>
                          <textarea
                            value={selectedBlock.content}
                            onChange={(e) => updateSelectedBlock({ content: e.target.value })}
                            rows={4}
                            className="w-full rounded-md border bg-background px-3 py-2 text-sm leading-relaxed"
                          />
                        </div>
                      )}

                      {/* Font size */}
                      {selectedBlock.fontSize !== undefined && (
                        <div className="space-y-1.5">
                          <div className="flex justify-between text-xs">
                            <span className="text-muted-foreground">Font Size</span>
                            <span className="font-mono">{selectedBlock.fontSize}px</span>
                          </div>
                          <input
                            type="range"
                            min="12"
                            max="40"
                            value={selectedBlock.fontSize}
                            onChange={(e) => updateSelectedBlock({ fontSize: Number(e.target.value) })}
                            className="w-full accent-blue-600"
                          />
                        </div>
                      )}

                      {/* Text alignment */}
                      <div className="space-y-1.5">
                        <label className="text-xs text-muted-foreground">Alignment</label>
                        <div className="flex rounded-md border bg-muted/30 p-0.5">
                          {(["left", "center", "right"] as const).map((align) => (
                            <button
                              key={align}
                              onClick={() => updateSelectedBlock({ textAlign: align })}
                              className={`flex-1 py-1 text-xs capitalize rounded ${
                                selectedBlock.textAlign === align ? "bg-background shadow-xs font-semibold" : "text-muted-foreground"
                              }`}
                            >
                              {align}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Button-specific options */}
                      {selectedBlock.type === "button" && (
                        <>
                          <div className="space-y-1.5">
                            <label className="text-xs text-muted-foreground">Button Text</label>
                            <Input
                              value={selectedBlock.buttonText || ""}
                              onChange={(e) => updateSelectedBlock({ buttonText: e.target.value })}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <label className="text-xs text-muted-foreground">Link URL</label>
                            <Input
                              value={selectedBlock.buttonUrl || ""}
                              onChange={(e) => updateSelectedBlock({ buttonUrl: e.target.value })}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <label className="text-xs text-muted-foreground">Button Color</label>
                            <div className="flex items-center gap-2">
                              <input
                                type="color"
                                value={selectedBlock.buttonColor || "#0066cc"}
                                onChange={(e) => updateSelectedBlock({ buttonColor: e.target.value })}
                                className="h-8 w-8 rounded border border-border cursor-pointer"
                              />
                              <Input
                                value={selectedBlock.buttonColor || "#0066cc"}
                                onChange={(e) => updateSelectedBlock({ buttonColor: e.target.value })}
                                className="h-8 text-xs font-mono"
                              />
                            </div>
                          </div>
                        </>
                      )}

                      {/* Block Ordering & Deletion */}
                      <div className="pt-4 border-t space-y-2">
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleMoveBlock(selectedBlock.id, "up")}
                            className="flex-1 text-xs"
                          >
                            <ArrowUp className="h-3.5 w-3.5 mr-1" /> Move Up
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleMoveBlock(selectedBlock.id, "down")}
                            className="flex-1 text-xs"
                          >
                            <ArrowDown className="h-3.5 w-3.5 mr-1" /> Move Down
                          </Button>
                        </div>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleDuplicateBlock(selectedBlock.id)}
                            className="flex-1 text-xs"
                          >
                            <Copy className="h-3.5 w-3.5 mr-1" /> Duplicate
                          </Button>
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => handleDeleteBlock(selectedBlock.id)}
                            className="flex-1 text-xs"
                          >
                            <Trash2 className="h-3.5 w-3.5 mr-1" /> Delete
                          </Button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="py-12 text-center text-muted-foreground text-sm">
                      <p>Click on any block on the canvas to inspect and edit its properties.</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Preview Modal (F9) */}
      <Dialog open={showPreviewModal} onOpenChange={setShowPreviewModal}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between pr-4">
              <span>Preview — {templateName}</span>
              <Badge variant="outline" className="font-mono text-xs">Subject: {subject}</Badge>
            </DialogTitle>
            <DialogDescription>
              Preview only: merge tags are replaced with placeholder values, no real contact data is used.
            </DialogDescription>
          </DialogHeader>
          <div className="border rounded-lg overflow-hidden my-4 bg-muted/10 p-4 flex justify-center">
            <iframe
              srcDoc={generateHtml()
                .replace(/\{\{\s*\.Subscriber\.FirstName\s*\}\}/g, "Alex")
                .replace(/\{\{\s*\.Subscriber\.Email\s*\}\}/g, "alex@example.com")
                .replace(/\{\{\s*\.UnsubscribeURL\s*\}\}/g, "#unsubscribe")}
              className="w-full max-w-[620px] h-[540px] bg-white rounded shadow-sm border"
              title="Email Preview"
              sandbox=""
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPreviewModal(false)}>Close</Button>
            <Button onClick={() => { setShowPreviewModal(false); handleStartCampaign() }} className="bg-[#0066cc]">
              <Send className="h-4 w-4 mr-2" /> Start Campaign with this Template
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Import Modal */}
      <Dialog open={showImportModal} onOpenChange={setShowImportModal}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Import Visual Template</DialogTitle>
            <DialogDescription>
              Paste HTML email code to import into the visual editor.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <textarea
              placeholder="Paste <html> code here..."
              value={importHtmlInput}
              onChange={(e) => setImportHtmlInput(e.target.value)}
              rows={8}
              className="w-full rounded-md border font-mono text-xs p-3"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowImportModal(false)}>Cancel</Button>
            <Button
              onClick={() => {
                if (importHtmlInput.trim()) {
                  setRawHtml(importHtmlInput)
                  setShowCodeView(true)
                  setShowImportModal(false)
                }
              }}
              className="bg-[#0066cc]"
            >
              Import HTML
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
