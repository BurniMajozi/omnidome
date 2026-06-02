"use client"

import { useState, useCallback, useEffect } from "react"
import {
  DollarSign,
  GripVertical,
  ChevronRight,
  ChevronLeft,
  CheckCircle,
  XCircle,
  Clock,
  User,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  salesApi,
  type Deal,
  type PipelineOverviewStage,
  type PipelineStage,
} from "@/lib/sales-api"

// ── Stage color mapping ──────────────────────────────────────────────

const STAGE_COLORS: Record<string, { bg: string; border: string; text: string; badge: string; dot: string }> = {
  Prospecting:    { bg: "bg-slate-500/10", border: "border-slate-500/30", text: "text-slate-400", badge: "bg-slate-500/20 text-slate-400", dot: "bg-slate-400" },
  Qualified:      { bg: "bg-blue-500/10",  border: "border-blue-500/30",  text: "text-blue-400",  badge: "bg-blue-500/20 text-blue-400",  dot: "bg-blue-400" },
  Proposal:       { bg: "bg-amber-500/10", border: "border-amber-500/30", text: "text-amber-400", badge: "bg-amber-500/20 text-amber-400", dot: "bg-amber-400" },
  Negotiation:    { bg: "bg-orange-500/10",border: "border-orange-500/30",text: "text-orange-400",badge: "bg-orange-500/20 text-orange-400",dot: "bg-orange-400" },
  "Closed Won":   { bg: "bg-emerald-500/10",border: "border-emerald-500/30",text: "text-emerald-400",badge: "bg-emerald-500/20 text-emerald-400",dot: "bg-emerald-400" },
  "Closed Lost":  { bg: "bg-red-500/10",  border: "border-red-500/30",  text: "text-red-400",  badge: "bg-red-500/20 text-red-400",  dot: "bg-red-400" },
}

function getStageColors(name: string) {
  return STAGE_COLORS[name] ?? {
    bg: "bg-violet-500/10", border: "border-violet-500/30",
    text: "text-violet-400", badge: "bg-violet-500/20 text-violet-400",
    dot: "bg-violet-400",
  }
}

function formatCurrency(value: number) {
  return `R ${value.toLocaleString("en-ZA")}`
}

// ── Deal Card ─────────────────────────────────────────────────────────

function DealCard({
  deal,
  stageName,
  onMoveNext,
  onMovePrev,
  onWon,
  onLost,
  isFirst,
  isLast,
}: {
  deal: Deal
  stageName: string
  onMoveNext: (dealId: string) => void
  onMovePrev: (dealId: string) => void
  onWon: (dealId: string) => void
  onLost: (dealId: string) => void
  isFirst: boolean
  isLast: boolean
}) {
  const colors = getStageColors(stageName)

  return (
    <div
      className={`group relative rounded-lg border ${colors.border} ${colors.bg} p-3 transition-all hover:shadow-lg hover:shadow-black/20 cursor-grab active:cursor-grabbing`}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", deal.id)
        e.dataTransfer.effectAllowed = "move"
      }}
    >
      {/* Drag handle */}
      <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-40 transition-opacity">
        <GripVertical className="h-4 w-4 text-muted-foreground" />
      </div>

      {/* Deal name */}
      <h4 className="text-sm font-medium text-foreground pr-6 truncate" title={deal.name}>
        {deal.name}
      </h4>

      {/* Value */}
      <div className="mt-1.5 flex items-center gap-1.5">
        <DollarSign className="h-3.5 w-3.5 text-emerald-400" />
        <span className="text-sm font-semibold text-emerald-400">
          {formatCurrency(deal.value_zar)}
        </span>
      </div>

      {/* Probability */}
      <div className="mt-2 flex items-center justify-between">
        <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${colors.badge}`}>
          {stageName}
        </Badge>
        {deal.agent_id && (
          <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
            <User className="h-3 w-3" />
            <span>Assigned</span>
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div className="mt-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {!isFirst && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={(e) => { e.stopPropagation(); onMovePrev(deal.id) }}
            title="Move back"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>
        )}
        {!isLast && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={(e) => { e.stopPropagation(); onMoveNext(deal.id) }}
            title="Move forward"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        )}
        {!isLast && stageName !== "Closed Won" && stageName !== "Closed Lost" && (
          <>
            <div className="w-px h-4 bg-border mx-0.5" />
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10"
              onClick={(e) => { e.stopPropagation(); onWon(deal.id) }}
              title="Close Won"
            >
              <CheckCircle className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-red-400 hover:text-red-300 hover:bg-red-500/10"
              onClick={(e) => { e.stopPropagation(); onLost(deal.id) }}
              title="Close Lost"
            >
              <XCircle className="h-3.5 w-3.5" />
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

// ── Pipeline Column ───────────────────────────────────────────────────

function PipelineColumn({
  stage,
  deals,
  stageIndex,
  totalStages,
  onDrop,
  onMoveNext,
  onMovePrev,
  onWon,
  onLost,
}: {
  stage: PipelineOverviewStage
  deals: Deal[]
  stageIndex: number
  totalStages: number
  onDrop: (dealId: string, stageId: string) => void
  onMoveNext: (dealId: string) => void
  onMovePrev: (dealId: string) => void
  onWon: (dealId: string) => void
  onLost: (dealId: string) => void
}) {
  const colors = getStageColors(stage.name)
  const [dragOver, setDragOver] = useState(false)

  return (
    <div
      className={`flex flex-col min-w-[260px] max-w-[300px] flex-shrink-0 rounded-xl border transition-colors ${
        dragOver ? `${colors.border} ${colors.bg} shadow-lg` : "border-border bg-card/50"
      }`}
      onDragOver={(e) => {
        e.preventDefault()
        e.dataTransfer.dropEffect = "move"
        setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        const dealId = e.dataTransfer.getData("text/plain")
        if (dealId) onDrop(dealId, stage.id)
      }}
    >
      {/* Column header */}
      <div className={`px-4 py-3 rounded-t-xl ${colors.bg} border-b ${colors.border}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`h-2.5 w-2.5 rounded-full ${colors.dot}`} />
            <h3 className={`text-sm font-semibold ${colors.text}`}>{stage.name}</h3>
          </div>
          <Badge variant="outline" className={`text-xs ${colors.badge}`}>
            {stage.deal_count}
          </Badge>
        </div>
        <div className="mt-1 flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            {formatCurrency(stage.total_value_zar)}
          </span>
          <span className="text-xs text-muted-foreground">
            {stage.probability}% prob.
          </span>
        </div>
      </div>

      {/* Cards */}
      <div className="flex-1 p-2 space-y-2 overflow-y-auto max-h-[520px] min-h-[120px]">
        {deals.length === 0 && (
          <div className="flex flex-col items-center justify-center h-24 text-muted-foreground text-xs">
            <Clock className="h-4 w-4 mb-1 opacity-50" />
            <span>Drop deals here</span>
          </div>
        )}
        {deals.map((deal) => (
          <DealCard
            key={deal.id}
            deal={deal}
            stageName={stage.name}
            onMoveNext={onMoveNext}
            onMovePrev={onMovePrev}
            onWon={onWon}
            onLost={onLost}
            isFirst={stageIndex === 0}
            isLast={stageIndex === totalStages - 1}
          />
        ))}
      </div>
    </div>
  )
}

// ── Main Pipeline Board ───────────────────────────────────────────────

export function SalesPipelineBoard() {
  const [stages, setStages] = useState<PipelineOverviewStage[]>([])
  const [deals, setDeals] = useState<Deal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [overviewData, dealsData, stagesData] = await Promise.all([
        salesApi.getPipelineOverview(),
        salesApi.listDeals(),
        salesApi.getPipelineStages(),
      ])
      // Sort stages by sort_order
      const sortedStages = [...stagesData].sort((a, b) => a.sort_order - b.sort_order)
      // Merge overview stats into stages
      const stagesWithStats = sortedStages.map((s) => {
        const ov = overviewData.find((o) => o.id === s.id)
        return {
          ...s,
          deal_count: ov?.deal_count ?? 0,
          total_value_zar: ov?.total_value_zar ?? 0,
        }
      })
      setStages(stagesWithStats)
      setDeals(dealsData)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load pipeline")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Group deals by stage
  const dealsByStage = stages.reduce<Record<string, Deal[]>>((acc, stage) => {
    acc[stage.id] = deals.filter((d) => d.stage_id === stage.id)
    return acc
  }, {})

  // ── Actions ───────────────────────────────────────────────────────

  const handleDrop = useCallback(async (dealId: string, targetStageId: string) => {
    const deal = deals.find((d) => d.id === dealId)
    if (!deal || deal.stage_id === targetStageId) return

    // Optimistic update
    setDeals((prev) =>
      prev.map((d) => (d.id === dealId ? { ...d, stage_id: targetStageId } : d))
    )

    try {
      const updated = await salesApi.moveDealStage(dealId, { stage_id: targetStageId })
      setDeals((prev) => prev.map((d) => (d.id === dealId ? updated : d)))
    } catch (err) {
      console.error("Failed to move deal:", err)
      loadData() // Revert
    }
  }, [deals, loadData])

  const handleMoveNext = useCallback(async (dealId: string) => {
    const deal = deals.find((d) => d.id === dealId)
    if (!deal) return
    const currentIdx = stages.findIndex((s) => s.id === deal.stage_id)
    if (currentIdx < 0 || currentIdx >= stages.length - 1) return
    const nextStage = stages[currentIdx + 1]
    handleDrop(dealId, nextStage.id)
  }, [deals, stages, handleDrop])

  const handleMovePrev = useCallback(async (dealId: string) => {
    const deal = deals.find((d) => d.id === dealId)
    if (!deal) return
    const currentIdx = stages.findIndex((s) => s.id === deal.stage_id)
    if (currentIdx <= 0) return
    const prevStage = stages[currentIdx - 1]
    handleDrop(dealId, prevStage.id)
  }, [deals, stages, handleDrop])

  const handleWon = useCallback(async (dealId: string) => {
    try {
      const updated = await salesApi.closeDealWon(dealId)
      setDeals((prev) => prev.map((d) => (d.id === dealId ? updated : d)))
    } catch (err) {
      console.error("Failed to close deal as won:", err)
    }
  }, [])

  const handleLost = useCallback(async (dealId: string) => {
    const reason = prompt("Reason for losing this deal?")
    if (!reason || reason.length < 3) return
    try {
      const updated = await salesApi.closeDealLost(dealId, reason)
      setDeals((prev) => prev.map((d) => (d.id === dealId ? updated : d)))
    } catch (err) {
      console.error("Failed to close deal as lost:", err)
    }
  }, [])

  // ── Render ────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-muted-foreground">
          <Clock className="h-5 w-5 animate-spin" />
          <span>Loading pipeline...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-sm text-red-400">{error}</p>
        <Button variant="outline" size="sm" onClick={loadData}>
          Retry
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Pipeline summary bar */}
      <div className="flex items-center gap-4 px-1">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <DollarSign className="h-4 w-4 text-emerald-400" />
          <span>
            Total Pipeline:{" "}
            <span className="font-semibold text-foreground">
              {formatCurrency(
                stages.reduce((sum, s) => sum + s.total_value_zar, 0)
              )}
            </span>
          </span>
        </div>
        <div className="text-sm text-muted-foreground">
          Deals:{" "}
          <span className="font-semibold text-foreground">
            {stages.reduce((sum, s) => sum + s.deal_count, 0)}
          </span>
        </div>
      </div>

      {/* Kanban columns — horizontal scroll */}
      <div className="flex gap-4 overflow-x-auto pb-4 px-1">
        {stages.map((stage, idx) => (
          <PipelineColumn
            key={stage.id}
            stage={stage}
            deals={dealsByStage[stage.id] ?? []}
            stageIndex={idx}
            totalStages={stages.length}
            onDrop={handleDrop}
            onMoveNext={handleMoveNext}
            onMovePrev={handleMovePrev}
            onWon={handleWon}
            onLost={handleLost}
          />
        ))}
      </div>
    </div>
  )
}
