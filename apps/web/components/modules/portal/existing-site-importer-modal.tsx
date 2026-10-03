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
  Globe,
  Sparkles,
  CheckCircle2,
  RefreshCw,
  Search,
  ExternalLink,
  Layers,
  Palette,
  ArrowRight,
} from "lucide-react"

export interface ScrapedSitePayload {
  url: string
  title: string
  heroHeadline: string
  heroSubheadline: string
  ctaText: string
  brandColors: {
    primary: string
    accent: string
    background: string
  }
  detectedPackages: Array<{
    name: string
    speed: string
    price: string
  }>
  coverageOperators: string[]
}

interface ExistingSiteImporterModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onApplySiteStructure: (scraped: ScrapedSitePayload) => void
}

export function ExistingSiteImporterModal({
  open,
  onOpenChange,
  onApplySiteStructure,
}: ExistingSiteImporterModalProps) {
  const [targetUrl, setTargetUrl] = useState("https://coolideas.co.za/promos/fibre-deals")
  const [isCrawling, setIsCrawling] = useState(false)
  const [scrapedResult, setScrapedResult] = useState<ScrapedSitePayload | null>(null)

  const handleCrawl = async () => {
    if (!targetUrl.trim()) return
    setIsCrawling(true)

    // Simulate headless DOM parsing via Firecrawl
    setTimeout(() => {
      let isCompetitor = targetUrl.toLowerCase().includes("cool") || targetUrl.toLowerCase().includes("afrihost")
      const result: ScrapedSitePayload = {
        url: targetUrl,
        title: isCompetitor
          ? "Uncapped Home Fibre Deals - Zero Shaping, 1Gbps Ready"
          : "OmniDome NextGen Fibre - Gigabit Internet For Home & Business",
        heroHeadline: isCompetitor
          ? "Switch to High-Performance Pure Uncapped Fibre"
          : "Experience Uncapped Gigabit Fibre with Sub-5ms Latency",
        heroSubheadline:
          "Connect to South Africa's premier fibre operators with free standard installation, free Wi-Fi 6 router, and month-to-month contracts.",
        ctaText: "Check Feasibility Now",
        brandColors: {
          primary: isCompetitor ? "#0284c7" : "#06b6d4",
          accent: "#10b981",
          background: "#090d16",
        },
        detectedPackages: [
          { name: "Fast Starter", speed: "100/50 Mbps", price: "R599/mo" },
          { name: "Super Streamer", speed: "250/125 Mbps", price: "R799/mo" },
          { name: "Gigabit Pro", speed: "1000/500 Mbps", price: "R1,299/mo" },
        ],
        coverageOperators: ["Vumatel", "Openserve", "Frogfoot", "Octotel"],
      }

      setScrapedResult(result)
      setIsCrawling(false)
    }, 1400)
  }

  const handleImportToCanvas = () => {
    if (!scrapedResult) return
    onApplySiteStructure(scrapedResult)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md sm:max-w-lg border-border bg-card">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="rounded-lg bg-cyan-500/20 p-2 text-cyan-400">
              <Globe className="h-5 w-5" />
            </div>
            <div>
              <DialogTitle className="text-base font-semibold text-foreground">
                Import & Recreate Existing Website
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                Enter an existing ISP URL or competitor site. Firecrawl extracts layout, color palette,
                and pricing tiers into an editable DomeDesign artboard.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* URL Input Bar */}
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Website URL</Label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Globe className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  value={targetUrl}
                  onChange={(e) => setTargetUrl(e.target.value)}
                  placeholder="https://example.com/fibre-promo"
                  className="pl-8 text-xs font-mono bg-background"
                />
              </div>
              <Button
                onClick={handleCrawl}
                disabled={isCrawling}
                className="text-xs bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold h-9"
              >
                {isCrawling ? (
                  <>
                    <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    Inspecting...
                  </>
                ) : (
                  <>
                    <Search className="mr-1.5 h-3.5 w-3.5" />
                    Inspect Site
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Quick Presets */}
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <span>Try sample:</span>
            <button
              type="button"
              onClick={() => setTargetUrl("https://coolideas.co.za/promos/fibre-deals")}
              className="text-cyan-400 hover:underline"
            >
              Cool Ideas Deals
            </button>
            <span>•</span>
            <button
              type="button"
              onClick={() => setTargetUrl("https://afrihost.com/fibre")}
              className="text-cyan-400 hover:underline"
            >
              Afrihost FTTH
            </button>
          </div>

          {/* Scraped Result Preview */}
          {scrapedResult && (
            <div className="rounded-lg border border-border bg-secondary/20 p-3.5 space-y-3">
              <div className="flex items-center justify-between border-b border-border/50 pb-2">
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  <span className="text-xs font-semibold text-foreground">DOM Inspection Complete</span>
                </div>
                <Badge className="bg-emerald-500/20 text-emerald-400 text-[10px]">
                  Headless Ready
                </Badge>
              </div>

              <div className="space-y-1.5">
                <p className="text-[11px] font-medium text-muted-foreground">Extracted Headline</p>
                <p className="text-xs font-semibold text-foreground">{scrapedResult.heroHeadline}</p>
                <p className="text-[11px] text-muted-foreground line-clamp-2">{scrapedResult.heroSubheadline}</p>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-md border border-border bg-background p-2">
                  <span className="text-[10px] text-muted-foreground block">Call To Action</span>
                  <span className="font-medium text-cyan-400">{scrapedResult.ctaText}</span>
                </div>
                <div className="rounded-md border border-border bg-background p-2">
                  <span className="text-[10px] text-muted-foreground block">Detected Operators</span>
                  <span className="font-medium text-foreground">{scrapedResult.coverageOperators.join(", ")}</span>
                </div>
              </div>

              <div>
                <span className="text-[10px] text-muted-foreground block mb-1.5">Extracted Packages ({scrapedResult.detectedPackages.length})</span>
                <div className="grid grid-cols-3 gap-2">
                  {scrapedResult.detectedPackages.map((pkg, i) => (
                    <div key={i} className="rounded-md border border-border bg-background p-1.5 text-center">
                      <p className="text-[10px] font-medium text-foreground">{pkg.name}</p>
                      <p className="text-[9px] text-cyan-400 font-mono">{pkg.speed}</p>
                      <p className="text-[10px] font-bold text-foreground mt-0.5">{pkg.price}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="border-t border-border pt-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            className="text-xs"
          >
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!scrapedResult}
            onClick={handleImportToCanvas}
            className="text-xs bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold"
          >
            <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            Generate Artboard on Canvas
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
