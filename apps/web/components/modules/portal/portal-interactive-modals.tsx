"use client"

import React, { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  Palette,
  Code,
  ImageIcon,
  Bot,
  CheckCircle2,
  Copy,
  Upload,
  Check,
  Sparkles,
} from "lucide-react"

// ── 1. THEME EDITOR MODAL ───────────────────────────────────────────────────

export function ThemeEditorModal({
  open,
  onOpenChange,
  onApplyTheme,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onApplyTheme?: (theme: { accent: string; radius: string }) => void
}) {
  const [selectedAccent, setSelectedAccent] = useState("cyan")
  const [borderRadius, setBorderRadius] = useState("0.5rem")
  const [applied, setApplied] = useState(false)

  const handleApply = () => {
    onApplyTheme?.({ accent: selectedAccent, radius: borderRadius })
    setApplied(true)
    setTimeout(() => {
      setApplied(false)
      onOpenChange(false)
    }, 1000)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md bg-[#0a0f1d] border-border text-foreground">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-cyan-500/20 text-cyan-400">
              <Palette className="h-4 w-4" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">Portal Theme Editor</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                Customize global visual system tokens across all landing pages.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-3 text-xs">
          <div className="space-y-2">
            <Label className="text-xs">Primary Brand Accent</Label>
            <div className="grid grid-cols-4 gap-2">
              {[
                { id: "cyan", name: "Telecom Cyan", color: "bg-cyan-500" },
                { id: "emerald", name: "Emerald Pro", color: "bg-emerald-500" },
                { id: "amber", name: "Solar Amber", color: "bg-amber-500" },
                { id: "sky", name: "Cobalt Sky", color: "bg-sky-500" },
              ].map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setSelectedAccent(c.id)}
                  className={`p-2 rounded border text-center transition-all ${
                    selectedAccent === c.id
                      ? "border-cyan-400 bg-secondary ring-1 ring-cyan-500"
                      : "border-border/60 hover:border-border"
                  }`}
                >
                  <div className={`w-full h-5 rounded ${c.color} mb-1.5`} />
                  <span className="text-[10px] text-muted-foreground block truncate">{c.name}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs">Border Radius Curvature</Label>
            <div className="grid grid-cols-3 gap-2">
              {[
                { id: "0.25rem", label: "Sharp (4px)" },
                { id: "0.5rem", label: "Standard (8px)" },
                { id: "0.75rem", label: "Smooth (12px)" },
              ].map((r) => (
                <Button
                  key={r.id}
                  type="button"
                  variant={borderRadius === r.id ? "secondary" : "outline"}
                  size="sm"
                  onClick={() => setBorderRadius(r.id)}
                  className={`text-xs h-8 border ${
                    borderRadius === r.id ? "border-cyan-500 text-cyan-400" : "border-border/60"
                  }`}
                >
                  {r.label}
                </Button>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter className="flex items-center justify-between sm:justify-between pt-2 border-t border-border/40">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} className="text-xs">
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleApply}
            className="text-xs bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold"
          >
            {applied ? <CheckCircle2 className="h-3.5 w-3.5 mr-1 text-emerald-950" /> : <Sparkles className="h-3.5 w-3.5 mr-1" />}
            {applied ? "Theme Applied!" : "Apply Theme Tokens"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── 2. CODE SNIPPETS MODAL ──────────────────────────────────────────────────

export function CodeSnippetsModal({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [headerCode, setHeaderCode] = useState(
    "<!-- Google Tag Manager -->\n<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':\nnew Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],\nj=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=\n'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);\n})(window,document,'script','dataLayer','GTM-OMNI991');</script>"
  )
  const [saved, setSaved] = useState(false)

  const handleSave = () => {
    setSaved(true)
    setTimeout(() => {
      setSaved(false)
      onOpenChange(false)
    }, 1000)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg bg-[#0a0f1d] border-border text-foreground">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-blue-500/20 text-blue-400">
              <Code className="h-4 w-4" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">Custom Code Snippets</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                Inject custom analytics, conversion pixels, and scripts across your portal pages.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-3 py-3 text-xs">
          <Label className="text-xs">Header Scripts (&lt;head&gt;)</Label>
          <textarea
            value={headerCode}
            onChange={(e) => setHeaderCode(e.target.value)}
            rows={7}
            className="w-full rounded-md border border-border bg-[#050811] p-3 text-xs font-mono text-cyan-300 focus:border-cyan-500 focus:outline-none resize-none leading-relaxed"
          />
          <p className="text-[11px] text-muted-foreground">
            Scripts automatically sanitize and load asynchronously with zero impact on Core Web Vitals.
          </p>
        </div>

        <DialogFooter className="flex items-center justify-between sm:justify-between pt-2 border-t border-border/40">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} className="text-xs">
            Close
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            className="text-xs bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold"
          >
            {saved ? <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> : <Code className="h-3.5 w-3.5 mr-1" />}
            {saved ? "Scripts Saved!" : "Save Snippets"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── 3. MEDIA LIBRARY MODAL ──────────────────────────────────────────────────

export function MediaLibraryModal({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null)

  const assets = [
    { id: "hero-1", name: "Fibre-Router-Wifi6.webp", size: "142 KB", dimensions: "1200x800" },
    { id: "hero-2", name: "Speed-Sprint-Banner.png", size: "284 KB", dimensions: "1920x1080" },
    { id: "logo-1", name: "OmniDome-Telecom-Logo.svg", size: "18 KB", dimensions: "Vector" },
    { id: "badge-1", name: "Popia-Compliant-Badge.png", size: "34 KB", dimensions: "400x400" },
  ]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl bg-[#0a0f1d] border-border text-foreground">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400">
              <ImageIcon className="h-4 w-4" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">Portal Media Library</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                Manage high-resolution images, brand vectors, and landing page hero graphics.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-3">
          <div className="border-2 border-dashed border-border/80 hover:border-cyan-500/60 rounded-lg p-5 text-center cursor-pointer transition-colors bg-secondary/20">
            <Upload className="h-6 w-6 text-muted-foreground mx-auto mb-2" />
            <p className="text-xs font-medium text-foreground">Click to upload or drag & drop files</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">SVG, PNG, WebP or JPEG up to 10MB</p>
          </div>

          <div className="grid grid-cols-2 gap-3 max-h-60 overflow-y-auto pr-1">
            {assets.map((asset) => (
              <div
                key={asset.id}
                onClick={() => setSelectedAsset(asset.id)}
                className={`p-3 rounded-lg border cursor-pointer transition-all ${
                  selectedAsset === asset.id
                    ? "border-cyan-500 bg-cyan-950/30 ring-1 ring-cyan-500"
                    : "border-border/60 bg-[#0d1322] hover:border-border"
                }`}
              >
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold text-foreground truncate">{asset.name}</p>
                  {selectedAsset === asset.id && <Check className="h-3.5 w-3.5 text-cyan-400" />}
                </div>
                <div className="flex items-center justify-between text-[10px] text-muted-foreground mt-1">
                  <span>{asset.dimensions}</span>
                  <span className="font-mono">{asset.size}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <DialogFooter className="flex items-center justify-between sm:justify-between pt-2 border-t border-border/40">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} className="text-xs">
            Close
          </Button>
          <Button
            size="sm"
            onClick={() => onOpenChange(false)}
            className="text-xs bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold"
          >
            Insert Selected Asset
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── 4. CREATE AI AGENT MODAL ────────────────────────────────────────────────

export function CreateAiAgentModal({
  open,
  onOpenChange,
  onCreateAgent,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreateAgent?: (agent: { name: string; department: string; model: string }) => void
}) {
  const [name, setName] = useState("Fibre Feasibility Bot")
  const [department, setDepartment] = useState("Sales")
  const [model, setModel] = useState("claude-3-5-sonnet")

  const handleCreate = () => {
    onCreateAgent?.({ name, department, model })
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md bg-[#0a0f1d] border-border text-foreground">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-blue-500/20 text-blue-400">
              <Bot className="h-4 w-4" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">Deploy Customer AI Agent</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                Configure autonomous chatbot routing for customer portals and landing pages.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-3 py-3 text-xs">
          <div className="space-y-1.5">
            <Label className="text-xs">Agent Name</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-8 text-xs bg-secondary/50 border-border"
              placeholder="e.g. Sales Concierge Bot"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Assigned Department</Label>
            <div className="grid grid-cols-3 gap-2">
              {["Sales", "Support", "Billing"].map((dept) => (
                <Button
                  key={dept}
                  type="button"
                  variant={department === dept ? "secondary" : "outline"}
                  size="sm"
                  onClick={() => setDepartment(dept)}
                  className={`text-xs h-8 border ${
                    department === dept ? "border-cyan-500 text-cyan-400" : "border-border/60"
                  }`}
                >
                  {dept}
                </Button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Base LLM Engine</Label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { id: "claude-3-5-sonnet", label: "Claude 3.5 Sonnet" },
                { id: "gpt-4o", label: "GPT-4o Omnichannel" },
              ].map((m) => (
                <Button
                  key={m.id}
                  type="button"
                  variant={model === m.id ? "secondary" : "outline"}
                  size="sm"
                  onClick={() => setModel(m.id)}
                  className={`text-xs h-8 border truncate ${
                    model === m.id ? "border-cyan-500 text-cyan-400" : "border-border/60"
                  }`}
                >
                  {m.label}
                </Button>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter className="flex items-center justify-between sm:justify-between pt-2 border-t border-border/40">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} className="text-xs">
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleCreate}
            className="text-xs bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold"
          >
            <Bot className="h-3.5 w-3.5 mr-1" />
            Deploy Agent
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
