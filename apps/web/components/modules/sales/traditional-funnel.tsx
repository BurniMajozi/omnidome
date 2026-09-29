"use client"

import { useState } from "react"
import {
  TrendingDown,
  TrendingUp,
  Users,
  DollarSign,
  ChevronDown,
  ArrowDown,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Layers,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"

export interface FunnelChannelSegment {
  channel: string
  label: string
  count: number
  color: string
  pctOfTier: number
}

export interface FunnelTierData {
  id: string
  name: string
  stageCategory: "top" | "mid" | "closing" | "won"
  count: number
  valueZar: number
  pctOfTotal: number
  conversionFromPrev?: number // Drop-off / conversion from prior tier
  description: string
  channels: FunnelChannelSegment[]
}

interface TraditionalFunnelProps {
  tiers: FunnelTierData[]
  totalLeads: number
  totalPipelineZar: number
  wonLeads: number
  wonRevenueZar: number
  onSelectTier?: (tierId: string) => void
  onSelectChannel?: (channel: string) => void
}

const zar = (n: number) =>
  new Intl.NumberFormat("en-ZA", {
    style: "currency",
    currency: "ZAR",
    maximumFractionDigits: 0,
  }).format(n)

export function TraditionalFunnel({
  tiers,
  totalLeads,
  totalPipelineZar,
  wonLeads,
  wonRevenueZar,
  onSelectTier,
  onSelectChannel,
}: TraditionalFunnelProps) {
  const [hoveredTier, setHoveredTier] = useState<string | null>(null)
  const [selectedTier, setSelectedTier] = useState<string | null>(null)

  // Traditional funnel width scaling (tapers down from 100% to ~38%)
  const TIER_WIDTHS: Record<number, string> = {
    0: "w-full", // Top: 100%
    1: "w-[82%]", // Mid-High: 82%
    2: "w-[64%]", // Mid: 64%
    3: "w-[46%]", // Bottom: 46%
  }

  const TIER_BORDER_COLORS: Record<string, string> = {
    top: "border-blue-500/40 bg-blue-950/20 hover:border-blue-500/80",
    mid: "border-purple-500/40 bg-purple-950/20 hover:border-purple-500/80",
    closing: "border-amber-500/40 bg-amber-950/20 hover:border-amber-500/80",
    won: "border-emerald-500/50 bg-emerald-950/25 hover:border-emerald-500/90",
  }

  const TIER_ACCENT_COLORS: Record<string, string> = {
    top: "#3b82f6",
    mid: "#8b5cf6",
    closing: "#f59e0b",
    won: "#10b981",
  }

  return (
    <div className="space-y-6">
      {/* ── Visual Funnel Diagram ── */}
      <div className="relative flex flex-col items-center gap-3 py-2">
        {tiers.map((tier, idx) => {
          const widthClass = TIER_WIDTHS[idx] || "w-[50%]"
          const colorClass = TIER_BORDER_COLORS[tier.stageCategory] || "border-border bg-card"
          const accentColor = TIER_ACCENT_COLORS[tier.stageCategory] || "#3b82f6"
          const isSelected = selectedTier === tier.id

          return (
            <div
              key={tier.id}
              className={`flex flex-col items-center transition-all duration-300 ${widthClass}`}
              onMouseEnter={() => setHoveredTier(tier.id)}
              onMouseLeave={() => setHoveredTier(null)}
            >
              {/* Funnel Drop-off Indicator between tiers */}
              {idx > 0 && tier.conversionFromPrev !== undefined && (
                <div className="flex items-center gap-1.5 my-0.5 text-[11px] font-mono text-muted-foreground/80">
                  <ArrowDown className="h-3 w-3 text-muted-foreground/60" />
                  <span>
                    {tier.conversionFromPrev}% transition pass-through
                  </span>
                  <span className="text-red-400/80 text-[10px]">
                    ({(100 - tier.conversionFromPrev).toFixed(1)}% drop-off)
                  </span>
                </div>
              )}

              {/* The Funnel Trapezoid Tier Box */}
              <div
                onClick={() => {
                  const newSel = selectedTier === tier.id ? null : tier.id
                  setSelectedTier(newSel)
                  if (onSelectTier) onSelectTier(tier.id)
                }}
                className={`w-full rounded-2xl border p-4 shadow-lg transition-all cursor-pointer relative overflow-hidden backdrop-blur-md ${colorClass} ${
                  isSelected ? "ring-2 ring-primary ring-offset-2 ring-offset-background" : ""
                }`}
                style={{
                  clipPath:
                    idx === 0
                      ? "polygon(0 0, 100% 0, 96% 100%, 4% 100%)"
                      : idx === 1
                      ? "polygon(2% 0, 98% 0, 94% 100%, 6% 100%)"
                      : idx === 2
                      ? "polygon(3% 0, 97% 0, 92% 100%, 8% 100%)"
                      : "polygon(4% 0, 96% 0, 96% 100%, 4% 100%)",
                }}
              >
                {/* Glow accent */}
                <div
                  className="absolute top-0 left-0 right-0 h-1"
                  style={{ backgroundColor: accentColor }}
                />

                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-3 pt-1">
                  <div>
                    <div className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: accentColor }}
                      />
                      <h4 className="text-sm font-bold text-foreground tracking-tight">
                        {tier.name}
                      </h4>
                      <Badge
                        variant="outline"
                        className="text-[10px] font-mono uppercase"
                        style={{ borderColor: `${accentColor}50`, color: accentColor }}
                      >
                        {tier.stageCategory === "top"
                          ? "Top of Funnel"
                          : tier.stageCategory === "mid"
                          ? "In Pipeline"
                          : tier.stageCategory === "closing"
                          ? "Closing Stage"
                          : "Won & Active"}
                      </Badge>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-1">
                      {tier.description}
                    </p>
                  </div>

                  <div className="flex items-center gap-4 text-right">
                    <div>
                      <span className="text-xs text-muted-foreground block">Volume</span>
                      <span
                        className="text-lg font-black font-mono"
                        style={{ color: accentColor }}
                      >
                        {tier.count} <span className="text-xs font-normal text-muted-foreground">({tier.pctOfTotal}%)</span>
                      </span>
                    </div>

                    {tier.valueZar > 0 && (
                      <div className="border-l border-border/50 pl-3">
                        <span className="text-xs text-muted-foreground block">
                          {tier.stageCategory === "won" ? "Realized Value" : "Pipeline Value"}
                        </span>
                        <span className="text-sm font-bold font-mono text-foreground">
                          {zar(tier.valueZar)}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Stacked Colored Channel Distribution Bar */}
                <div className="mt-3 px-3">
                  <div className="h-3 w-full rounded-full overflow-hidden flex bg-muted/40 p-0.5 gap-0.5">
                    {tier.channels.map((ch) => (
                      <div
                        key={ch.channel}
                        style={{
                          width: `${Math.max(ch.pctOfTier, 4)}%`,
                          backgroundColor: ch.color,
                        }}
                        className="h-full rounded-sm transition-all hover:opacity-80"
                        title={`${ch.label}: ${ch.count} leads (${ch.pctOfTier}%)`}
                      />
                    ))}
                  </div>

                  {/* Micro Channel Legend Chips */}
                  <div className="flex items-center flex-wrap gap-x-3 gap-y-1 mt-2 text-[10px] text-muted-foreground">
                    {tier.channels.slice(0, 5).map((ch) => (
                      <button
                        key={ch.channel}
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          if (onSelectChannel) onSelectChannel(ch.channel)
                        }}
                        className="flex items-center gap-1 hover:text-foreground transition-colors"
                      >
                        <span
                          className="h-2 w-2 rounded-full shrink-0"
                          style={{ backgroundColor: ch.color }}
                        />
                        <span>{ch.label}</span>
                        <span className="font-mono font-semibold text-foreground">
                          {ch.count}
                        </span>
                      </button>
                    ))}
                    {tier.channels.length > 5 && (
                      <span className="text-[9px] text-muted-foreground/60">
                        +{tier.channels.length - 5} more channels
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* ── Stage Breakdown Summary ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
        <Card className="border-border bg-card/60">
          <CardContent className="p-3.5 flex items-center justify-between">
            <div>
              <p className="text-[11px] text-muted-foreground">Stuck in Top Leads</p>
              <p className="text-xl font-bold text-blue-400 mt-0.5">
                {tiers[0]?.count ?? 0} leads
              </p>
              <p className="text-[10px] text-muted-foreground">
                Awaiting contact & initial qualification
              </p>
            </div>
            <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-400">
              <Users className="h-5 w-5" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card/60">
          <CardContent className="p-3.5 flex items-center justify-between">
            <div>
              <p className="text-[11px] text-muted-foreground">Active in Progress</p>
              <p className="text-xl font-bold text-purple-400 mt-0.5">
                {(tiers[1]?.count ?? 0) + (tiers[2]?.count ?? 0)} opportunities
              </p>
              <p className="text-[10px] text-muted-foreground">
                {zar((tiers[1]?.valueZar ?? 0) + (tiers[2]?.valueZar ?? 0))} open pipeline
              </p>
            </div>
            <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-400">
              <DollarSign className="h-5 w-5" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card/60">
          <CardContent className="p-3.5 flex items-center justify-between">
            <div>
              <p className="text-[11px] text-muted-foreground">Won & Subscribed</p>
              <p className="text-xl font-bold text-emerald-400 mt-0.5">
                {wonLeads} deals
              </p>
              <p className="text-[10px] text-muted-foreground">
                {zar(wonRevenueZar)} converted revenue
              </p>
            </div>
            <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-400">
              <CheckCircle2 className="h-5 w-5" />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
