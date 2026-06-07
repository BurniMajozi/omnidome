"use client"

import { useEffect, useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  User,
  Mail,
  Phone,
  MapPin,
  Calendar,
  DollarSign,
  Target,
  FileText,
  Percent,
  Tag,
  MessageSquare,
  TrendingUp,
  TrendingDown,
  Activity,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  RefreshCw,
  Award,
  Layers,
  BarChart3,
  Receipt,
  HandCoins,
  StickyNote,
  CircleDot,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
} from "lucide-react"
import { cn } from "@/lib/utils"

// ─── Types ───────────────────────────────────────────────────────────────────

interface LeadOrigin {
  source: string
  coverageArea: string
  conversionDate: string
}

interface Deal {
  id: string
  name: string
  value: number
  status: "active" | "won" | "lost" | "stalled"
  stage: string
  probability: number
}

interface Quote {
  id: string
  type: "monthly" | "once-off" | "term"
  amount: number
  status: "sent" | "accepted" | "declined" | "expired"
  date: string
}

interface Commission {
  id: string
  dealName: string
  amount: number
  status: "pending" | "paid" | "held"
  date: string
}

interface InternalNote {
  id: string
  content: string
  author: string
  timestamp: string
}

interface LifecycleStage {
  stage: string
  healthScore: number // 0-100
}

interface CRMSummary {
  totalDealsValue: number
  activeDealsCount: number
  wonDealsCount: number
  lostDealsCount: number
  quotesSent: number
  quotesAccepted: number
}

interface CRM360Data {
  leadOrigin: LeadOrigin
  deals: Deal[]
  quotes: Quote[]
  commissions: Commission[]
  segments: string[]
  tags: string[]
  internalNotes: InternalNote[]
  lifecycle: LifecycleStage
  summary: CRMSummary
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatCurrency(value: number): string {
  return `R ${value.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatDate(dateStr: string): string {
  if (!dateStr) return "—"
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString("en-ZA", { year: "numeric", month: "short", day: "numeric" })
}

function formatDateTime(dateStr: string): string {
  if (!dateStr) return "—"
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString("en-ZA", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

// ─── Shared sub-components ───────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "active":
    case "won":
    case "accepted":
    case "paid":
      return (
        <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
          <CheckCircle2 className="mr-1 h-3 w-3" />
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </Badge>
      )
    case "lost":
    case "declined":
    case "expired":
      return (
        <Badge className="bg-red-500/15 text-red-400 border-red-500/30">
          <XCircle className="mr-1 h-3 w-3" />
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </Badge>
      )
    case "stalled":
    case "held":
      return (
        <Badge className="bg-orange-500/15 text-orange-400 border-orange-500/30">
          <AlertCircle className="mr-1 h-3 w-3" />
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </Badge>
      )
    case "pending":
    case "sent":
      return (
        <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30">
          <Clock className="mr-1 h-3 w-3" />
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </Badge>
      )
    default:
      return (
        <Badge variant="secondary">
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </Badge>
      )
  }
}

function SectionCard({
  title,
  icon: Icon,
  children,
  className,
  action,
}: {
  title: string
  icon: React.ElementType
  children: React.ReactNode
  className?: string
  action?: React.ReactNode
}) {
  return (
    <Card className={cn("border-border bg-card", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base font-semibold text-foreground">
            <div className="rounded-lg bg-primary/10 p-1.5">
              <Icon className="h-4 w-4 text-primary" />
            </div>
            {title}
          </CardTitle>
          {action}
        </div>
      </CardHeader>
      <CardContent className="pt-0">{children}</CardContent>
    </Card>
  )
}

function EmptyState({ message = "No records found" }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <div className="rounded-full bg-muted/50 p-3 mb-3">
        <FileText className="h-5 w-5 text-muted-foreground" />
      </div>
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  )
}

function SkeletonLoader() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="h-32 rounded-xl border border-border bg-card" />
        <div className="h-32 rounded-xl border border-border bg-card" />
        <div className="h-32 rounded-xl border border-border bg-card" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="h-64 rounded-xl border border-border bg-card" />
        <div className="h-64 rounded-xl border border-border bg-card" />
      </div>
      <div className="h-48 rounded-xl border border-border bg-card" />
    </div>
  )
}

function HealthScoreRing({ score }: { score: number }) {
  const radius = 32
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (score / 100) * circumference

  const getColor = () => {
    if (score >= 75) return { stroke: "#10b981", text: "text-emerald-400", bg: "bg-emerald-500/15" }
    if (score >= 50) return { stroke: "#f59e0b", text: "text-amber-400", bg: "bg-amber-500/15" }
    return { stroke: "#ef4444", text: "text-red-400", bg: "bg-red-500/15" }
  }

  const color = getColor()

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative">
        <svg width="80" height="80" className="-rotate-90">
          <circle
            cx="40"
            cy="40"
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth="6"
            className="text-border/30"
          />
          <circle
            cx="40"
            cy="40"
            r={radius}
            fill="none"
            stroke={color.stroke}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="transition-all duration-700 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={cn("text-lg font-bold", color.text)}>{score}</span>
        </div>
      </div>
      <span className="text-xs text-muted-foreground">Health Score</span>
    </div>
  )
}

function SummaryCard({
  label,
  value,
  icon: Icon,
  trend,
  color,
}: {
  label: string
  value: string | number
  icon: React.ElementType
  trend?: "up" | "down" | "neutral"
  color?: string
}) {
  return (
    <Card className="border-border bg-card">
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-muted-foreground mb-1">{label}</p>
            <p className={cn("text-2xl font-bold", color ?? "text-foreground")}>{value}</p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <div className="rounded-lg bg-primary/10 p-2">
              <Icon className="h-4 w-4 text-primary" />
            </div>
            {trend && (
              <div className="flex items-center gap-0.5">
                {trend === "up" && <ArrowUpRight className="h-3 w-3 text-emerald-400" />}
                {trend === "down" && <ArrowDownRight className="h-3 w-3 text-red-400" />}
                {trend === "neutral" && <Minus className="h-3 w-3 text-muted-foreground" />}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Main Component ──────────────────────────────────────────────────────────

interface CRMTabProps {
  customerId: string
}

export function CRMTab({ customerId }: CRMTabProps) {
  const [data, setData] = useState<CRM360Data | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchCRMData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`/api/crm/customers/${encodeURIComponent(customerId)}/360/crm`, {
        cache: "no-store",
      })
      if (!response.ok) {
        throw new Error(`Failed to fetch CRM data: ${response.status}`)
      }
      const json = await response.json()
      setData(json.data ?? json)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load CRM data")
    } finally {
      setLoading(false)
    }
  }, [customerId])

  useEffect(() => {
    fetchCRMData()
  }, [fetchCRMData])

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">Loading CRM data…</span>
        </div>
        <SkeletonLoader />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="rounded-full bg-destructive/10 p-4 mb-4">
          <AlertCircle className="h-6 w-6 text-destructive" />
        </div>
        <h3 className="text-lg font-semibold text-foreground mb-1">Failed to load CRM data</h3>
        <p className="text-sm text-muted-foreground mb-4 max-w-md">{error}</p>
        <button
          onClick={fetchCRMData}
          className="inline-flex items-center gap-2 rounded-lg border border-border bg-secondary px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-secondary/80"
        >
          <RefreshCw className="h-4 w-4" />
          Retry
        </button>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="rounded-full bg-muted/50 p-4 mb-4">
          <Target className="h-6 w-6 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold text-foreground mb-1">No CRM data</h3>
        <p className="text-sm text-muted-foreground">No CRM records found for this customer.</p>
      </div>
    )
  }

  const { leadOrigin, deals, quotes, commissions, segments, tags, internalNotes, lifecycle, summary } = data

  return (
    <div className="space-y-6">
      {/* ── Summary Cards ──────────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <SummaryCard
          label="Total Deal Value"
          value={formatCurrency(summary.totalDealsValue)}
          icon={DollarSign}
          trend="up"
          color="text-primary"
        />
        <SummaryCard
          label="Active Deals"
          value={summary.activeDealsCount}
          icon={Activity}
          trend="up"
          color="text-emerald-400"
        />
        <SummaryCard
          label="Won Deals"
          value={summary.wonDealsCount}
          icon={Award}
          trend="up"
          color="text-emerald-400"
        />
        <SummaryCard
          label="Lost Deals"
          value={summary.lostDealsCount}
          icon={TrendingDown}
          trend={summary.lostDealsCount > 0 ? "down" : "neutral"}
          color="text-red-400"
        />
        <SummaryCard
          label="Quotes Sent"
          value={summary.quotesSent}
          icon={FileText}
          trend="neutral"
        />
        <SummaryCard
          label="Quotes Accepted"
          value={summary.quotesAccepted}
          icon={CheckCircle2}
          trend="up"
          color="text-emerald-400"
        />
      </div>

      {/* ── Lead Origin + Lifecycle + Segments & Tags ───────────────────── */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Lead Origin Card */}
        <SectionCard title="Lead Origin" icon={MapPin}>
          <div className="space-y-3">
            <div className="flex items-start gap-3 py-2">
              <div className="mt-0.5 rounded-md bg-primary/10 p-1.5">
                <Target className="h-3.5 w-3.5 text-primary" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs text-muted-foreground">Source</p>
                <p className="text-sm font-medium text-foreground">{leadOrigin.source || "—"}</p>
              </div>
            </div>
            <div className="flex items-start gap-3 py-2">
              <div className="mt-0.5 rounded-md bg-primary/10 p-1.5">
                <MapPin className="h-3.5 w-3.5 text-primary" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs text-muted-foreground">Coverage Area</p>
                <p className="text-sm font-medium text-foreground">{leadOrigin.coverageArea || "—"}</p>
              </div>
            </div>
            <div className="flex items-start gap-3 py-2">
              <div className="mt-0.5 rounded-md bg-primary/10 p-1.5">
                <Calendar className="h-3.5 w-3.5 text-primary" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs text-muted-foreground">Conversion Date</p>
                <p className="text-sm font-medium text-foreground">{formatDate(leadOrigin.conversionDate)}</p>
              </div>
            </div>
          </div>
        </SectionCard>

        {/* Lifecycle Stage Card */}
        <SectionCard title="Lifecycle Stage" icon={Activity}>
          <div className="flex flex-col items-center gap-4 py-2">
            <HealthScoreRing score={lifecycle.healthScore} />
            <div className="text-center">
              <p className="text-sm font-semibold text-foreground">{lifecycle.stage || "—"}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Current Stage</p>
            </div>
          </div>
        </SectionCard>

        {/* Segments & Tags Card */}
        <SectionCard title="Segments & Tags" icon={Tag}>
          <div className="space-y-4">
            <div>
              <p className="text-xs text-muted-foreground mb-2">Segments</p>
              {segments.length === 0 ? (
                <p className="text-sm text-muted-foreground">No segments assigned</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {segments.map((segment, idx) => (
                    <Badge key={idx} variant="outline" className="text-xs">
                      <Layers className="mr-1 h-3 w-3" />
                      {segment}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-2">Tags</p>
              {tags.length === 0 ? (
                <p className="text-sm text-muted-foreground">No tags assigned</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {tags.map((tag, idx) => (
                    <Badge key={idx} className="bg-primary/10 text-primary border-primary/30 text-xs">
                      #{tag}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>
        </SectionCard>
      </div>

      {/* ── Deal Pipeline ──────────────────────────────────────────────── */}
      <SectionCard
        title="Deal Pipeline"
        icon={Target}
        action={
          <Badge variant="outline" className="text-xs">
            {deals.length} deal{deals.length !== 1 ? "s" : ""}
          </Badge>
        }
      >
        {deals.length === 0 ? (
          <EmptyState message="No deals in pipeline" />
        ) : (
          <ScrollArea className="max-h-80">
            <div className="space-y-2">
              {deals.map((deal) => (
                <div
                  key={deal.id}
                  className="rounded-lg border border-border bg-secondary/20 p-4 transition-colors hover:border-primary/30"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <p className="text-sm font-semibold text-foreground truncate">{deal.name}</p>
                        <StatusBadge status={deal.status} />
                      </div>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <CircleDot className="h-3 w-3" />
                          {deal.stage}
                        </span>
                        <span className="flex items-center gap-1">
                          <Percent className="h-3 w-3" />
                          {deal.probability}%
                        </span>
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-sm font-bold text-foreground">{formatCurrency(deal.value)}</p>
                      <div className="mt-1.5 w-20">
                        <div className="h-1.5 rounded-full bg-border/30 overflow-hidden">
                          <div
                            className={cn(
                              "h-full rounded-full transition-all",
                              deal.probability >= 75
                                ? "bg-emerald-500"
                                : deal.probability >= 50
                                  ? "bg-amber-500"
                                  : "bg-red-500"
                            )}
                            style={{ width: `${deal.probability}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </SectionCard>

      {/* ── Quotes Table ───────────────────────────────────────────────── */}
      <SectionCard
        title="Quotes"
        icon={Receipt}
        action={
          <Badge variant="outline" className="text-xs">
            {quotes.length} quote{quotes.length !== 1 ? "s" : ""}
          </Badge>
        }
      >
        {quotes.length === 0 ? (
          <EmptyState message="No quotes on record" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {quotes.map((quote) => (
                <TableRow key={quote.id}>
                  <TableCell>
                    <Badge variant="outline" className="text-xs capitalize">
                      {quote.type}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-medium text-foreground">
                    {formatCurrency(quote.amount)}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={quote.status} />
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground text-xs">
                    {formatDate(quote.date)}
                  </td>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>

      {/* ── Commissions + Internal Notes ────────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Commissions List */}
        <SectionCard
          title="Commissions"
          icon={HandCoins}
          action={
            <Badge variant="outline" className="text-xs">
              {commissions.length}
            </Badge>
          }
        >
          {commissions.length === 0 ? (
            <EmptyState message="No commissions on record" />
          ) : (
            <ScrollArea className="max-h-72">
              <div className="space-y-2">
                {commissions.map((commission) => (
                  <div
                    key={commission.id}
                    className="rounded-lg border border-border bg-secondary/20 p-3 transition-colors hover:border-primary/30"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-foreground truncate">{commission.dealName}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs text-muted-foreground">{formatDate(commission.date)}</span>
                          <StatusBadge status={commission.status} />
                        </div>
                      </div>
                      <p className="text-sm font-semibold text-foreground shrink-0">
                        {formatCurrency(commission.amount)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </SectionCard>

        {/* Internal Notes Thread */}
        <SectionCard
          title="Internal Notes"
          icon={StickyNote}
          action={
            <Badge variant="outline" className="text-xs">
              {internalNotes.length}
            </Badge>
          }
        >
          {internalNotes.length === 0 ? (
            <EmptyState message="No internal notes" />
          ) : (
            <ScrollArea className="max-h-72">
              <div className="space-y-3">
                {internalNotes.map((note) => (
                  <div
                    key={note.id}
                    className="rounded-lg border border-border bg-secondary/20 p-3 transition-colors hover:border-primary/30"
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
                        <MessageSquare className="h-3.5 w-3.5 text-primary" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-foreground">{note.content}</p>
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className="text-xs font-medium text-primary">{note.author}</span>
                          <span className="text-xs text-muted-foreground">•</span>
                          <span className="text-xs text-muted-foreground">{formatDateTime(note.timestamp)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </SectionCard>
      </div>
    </div>
  )
}
