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
  allStages,
  onStageChange,
  onMoveNext,
  onMovePrev,
  onWon,
  onLost,
  isFirst,
  isLast,
}: {
  deal: Deal
  stageName: string
  allStages: PipelineOverviewStage[]
  onStageChange: (dealId: string, newStageId: string) => void
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
      <div className="mt-1.5 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <DollarSign className="h-3.5 w-3.5 text-emerald-400" />
          <span className="text-sm font-semibold text-emerald-400">
            {formatCurrency(deal.value_zar)}
          </span>
        </div>
        {deal.status !== "OPEN" && (
          <Badge
            variant="outline"
            className={`text-[9px] px-1 py-0 ${
              deal.status === "WON" ? "border-emerald-500 text-emerald-400" : "border-red-500 text-red-400"
            }`}
          >
            {deal.status}
          </Badge>
        )}
      </div>

      {/* Stage Selector Dropdown (Adjustable Stage) */}
      <div className="mt-2.5 flex items-center justify-between gap-1.5">
        <select
          value={deal.stage_id}
          onChange={(e) => {
            e.stopPropagation()
            onStageChange(deal.id, e.target.value)
          }}
          className="h-6 rounded bg-background/80 border border-border/80 px-1 text-[11px] font-medium text-foreground focus:outline-none focus:ring-1 focus:ring-primary max-w-[130px] truncate"
          title="Adjust lead/deal stage"
        >
          {allStages.map((s) => (
            <option key={s.id} value={s.id} className="bg-popover text-foreground">
              {s.name}
            </option>
          ))}
        </select>

        {deal.agent_id && (
          <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
            <User className="h-3 w-3" />
            <span>Assigned</span>
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div className="mt-2.5 flex items-center justify-between pt-1 border-t border-border/40">
        <div className="flex items-center gap-1">
          {!isFirst && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={(e) => { e.stopPropagation(); onMovePrev(deal.id) }}
              title="Move to previous stage"
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
              title="Move to next stage"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>

        {stageName !== "Closed Won" && stageName !== "Closed Lost" && (
          <div className="flex items-center gap-1">
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
          </div>
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
  allStages,
  onDrop,
  onStageChange,
  onMoveNext,
  onMovePrev,
  onWon,
  onLost,
}: {
  stage: PipelineOverviewStage
  deals: Deal[]
  stageIndex: number
  totalStages: number
  allStages: PipelineOverviewStage[]
  onDrop: (dealId: string, stageId: string) => void
  onStageChange: (dealId: string, newStageId: string) => void
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
            allStages={allStages}
            onStageChange={onStageChange}
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

export function SalesPipelineBoard({
  onDataLoaded,
}: {
  onDataLoaded?: (deals: Deal[], stages: PipelineOverviewStage[]) => void
}) {
  const [stages, setStages] = useState<PipelineOverviewStage[]>([])
  const [deals, setDeals] = useState<Deal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Manual Deal Creation Modal state
  const [newDealOpen, setNewDealOpen] = useState(false)
  const [dealName, setDealName] = useState("")
  const [dealValue, setDealValue] = useState<string>("50000")
  const [dealStageId, setDealStageId] = useState("")
  const [dealNotes, setDealNotes] = useState("")
  const [savingDeal, setSavingDeal] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [overviewData, dealsData, stagesData] = await Promise.all([
        salesApi.getPipelineOverview().catch(() => []),
        salesApi.listDeals().catch(() => []),
        salesApi.getPipelineStages().catch(() => []),
      ])

      // Fallback stages if backend is initializing or empty
      const effectiveStages = stagesData.length > 0 ? stagesData : [
        { id: "stage-1", name: "Prospecting", probability: 10, sort_order: 1 },
        { id: "stage-2", name: "Qualified", probability: 30, sort_order: 2 },
        { id: "stage-3", name: "Proposal", probability: 60, sort_order: 3 },
        { id: "stage-4", name: "Negotiation", probability: 80, sort_order: 4 },
        { id: "stage-5", name: "Closed Won", probability: 100, sort_order: 5 },
        { id: "stage-6", name: "Closed Lost", probability: 0, sort_order: 6 },
      ]

      // Sort stages by sort_order
      const sortedStages = [...effectiveStages].sort((a, b) => a.sort_order - b.sort_order)
      // Merge overview stats into stages
      const stagesWithStats = sortedStages.map((s) => {
        const ov = overviewData.find((o) => o.id === s.id)
        const stageDeals = dealsData.filter((d) => d.stage_id === s.id)
        return {
          ...s,
          deal_count: ov?.deal_count ?? stageDeals.length,
          total_value_zar: ov?.total_value_zar ?? stageDeals.reduce((sum, d) => sum + Number(d.value_zar || 0), 0),
        }
      })

      setStages(stagesWithStats)
      setDeals(dealsData)
      if (sortedStages.length > 0 && !dealStageId) {
        setDealStageId(sortedStages[0].id)
      }
      onDataLoaded?.(dealsData, stagesWithStats)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load pipeline")
    } finally {
      setLoading(false)
    }
  }, [dealStageId, onDataLoaded])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Group deals by stage
  const dealsByStage = stages.reduce<Record<string, Deal[]>>((acc, stage) => {
    acc[stage.id] = deals.filter((d) => d.stage_id === stage.id)
    return acc
  }, {})

  // ── Actions ───────────────────────────────────────────────────────

  const handleStageChange = useCallback(async (dealId: string, targetStageId: string) => {
    const deal = deals.find((d) => d.id === dealId)
    if (!deal || deal.stage_id === targetStageId) return

    // Optimistic update
    setDeals((prev) =>
      prev.map((d) => (d.id === dealId ? { ...d, stage_id: targetStageId } : d))
    )

    try {
      const updated = await salesApi.moveDealStage(dealId, { stage_id: targetStageId })
      setDeals((prev) => prev.map((d) => (d.id === dealId ? updated : d)))
      loadData()
    } catch (err) {
      console.error("Failed to move deal:", err)
      loadData() // Revert
    }
  }, [deals, loadData])

  const handleDrop = useCallback(async (dealId: string, targetStageId: string) => {
    handleStageChange(dealId, targetStageId)
  }, [handleStageChange])

  const handleMoveNext = useCallback(async (dealId: string) => {
    const deal = deals.find((d) => d.id === dealId)
    if (!deal) return
    const currentIdx = stages.findIndex((s) => s.id === deal.stage_id)
    if (currentIdx < 0 || currentIdx >= stages.length - 1) return
    const nextStage = stages[currentIdx + 1]
    handleStageChange(dealId, nextStage.id)
  }, [deals, stages, handleStageChange])

  const handleMovePrev = useCallback(async (dealId: string) => {
    const deal = deals.find((d) => d.id === dealId)
    if (!deal) return
    const currentIdx = stages.findIndex((s) => s.id === deal.stage_id)
    if (currentIdx <= 0) return
    const prevStage = stages[currentIdx - 1]
    handleStageChange(dealId, prevStage.id)
  }, [deals, stages, handleStageChange])

  const handleWon = useCallback(async (dealId: string) => {
    try {
      const updated = await salesApi.closeDealWon(dealId)
      setDeals((prev) => prev.map((d) => (d.id === dealId ? updated : d)))
      loadData()
    } catch (err) {
      console.error("Failed to close deal as won:", err)
    }
  }, [loadData])

  const handleLost = useCallback(async (dealId: string) => {
    const reason = prompt("Reason for losing this deal?")
    if (!reason || reason.length < 3) return
    try {
      const updated = await salesApi.closeDealLost(dealId, reason)
      setDeals((prev) => prev.map((d) => (d.id === dealId ? updated : d)))
      loadData()
    } catch (err) {
      console.error("Failed to close deal as lost:", err)
    }
  }, [loadData])

  const handleCreateManualDeal = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!dealName.trim()) return
    setSavingDeal(true)
    try {
      const stage = stages.find((s) => s.id === dealStageId) || stages[0]
      await salesApi.createDeal({
        name: dealName.trim(),
        customer_id: "00000000-0000-0000-0000-000000000001",
        stage_id: stage?.id,
        stage_name: stage?.name,
        value_zar: Number(dealValue) || 0,
        notes: dealNotes.trim() || undefined,
      })
      setNewDealOpen(false)
      setDealName("")
      setDealValue("50000")
      setDealNotes("")
      loadData()
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to create deal")
    } finally {
      setSavingDeal(false)
    }
  }

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

  if (error && stages.length === 0) {
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
      {/* Pipeline top actions & summary */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <div className="flex items-center gap-4">
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

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => setNewDealOpen(true)}
            className="h-8 gap-1.5 bg-primary text-primary-foreground text-xs shadow-sm"
          >
            + Create Deal Manually
          </Button>
        </div>
      </div>

      {/* Manual Create Deal Dialog */}
      {newDealOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-base font-bold text-foreground">Add Deal to Pipeline</h3>
              <button
                type="button"
                onClick={() => setNewDealOpen(false)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted"
              >
                ✕
              </button>
            </div>
            <form onSubmit={handleCreateManualDeal} className="space-y-3.5">
              <div>
                <label className="text-xs font-semibold text-foreground">Deal Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Acme Corp - Fiber Upgrade"
                  value={dealName}
                  onChange={(e) => setDealName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-foreground">Value (ZAR) *</label>
                  <input
                    type="number"
                    required
                    min="0"
                    step="100"
                    value={dealValue}
                    onChange={(e) => setDealValue(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-foreground">Initial Stage *</label>
                  <select
                    value={dealStageId}
                    onChange={(e) => setDealStageId(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    {stages.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} ({s.probability}%)
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground">Notes / Customer Context</label>
                <textarea
                  rows={3}
                  placeholder="Customer walk-in, agreed pricing, expected signing..."
                  value={dealNotes}
                  onChange={(e) => setDealNotes(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-border">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setNewDealOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={savingDeal || !dealName.trim()}
                  className="bg-primary text-primary-foreground"
                >
                  {savingDeal ? "Creating..." : "Add to Board"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Kanban columns — horizontal scroll */}
      <div className="flex gap-4 overflow-x-auto pb-4 px-1">
        {stages.map((stage, idx) => (
          <PipelineColumn
            key={stage.id}
            stage={stage}
            deals={dealsByStage[stage.id] ?? []}
            stageIndex={idx}
            totalStages={stages.length}
            allStages={stages}
            onDrop={handleDrop}
            onStageChange={handleStageChange}
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
