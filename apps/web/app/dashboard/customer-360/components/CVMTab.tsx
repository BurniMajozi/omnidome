"use client"

import { useEffect, useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  CreditCard,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  RefreshCw,
  FileText,
  Shield,
  ShieldAlert,
  Activity,
  Zap,
  Award,
  Target,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Receipt,
  Calendar,
  Gauge,
  HeartPulse,
  Lightbulb,
  ChevronRight,
  Banknote,
  BarChart3,
  Users,
  CircleAlert,
} from "lucide-react"
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts"
import { cn } from "@/lib/utils"

// ─── Types ───────────────────────────────────────────────────────────────────

interface FinancialKPIs {
  mrr: number
  arr: number
  ltv: number
  outstandingBalance: number
  paymentReliability: number // 0-100
}

interface InvoiceRecord {
  id: string
  invoiceNumber: string
  date: string
  amount: number
  status: "paid" | "unpaid" | "overdue" | "partially_paid" | "cancelled"
  dueDate: string
}

interface PaymentTimelineEntry {
  id: string
  date: string
  amount: number
  type: "payment" | "refund" | "adjustment"
  description: string
  status: "completed" | "pending" | "failed"
}

interface ChurnRisk {
  score: number // 0-100
  level: "low" | "medium" | "high" | "critical"
  factors: string[]
}

interface HealthFactor {
  name: string
  score: number // 0-100
  weight: number
  trend: "up" | "down" | "stable"
}

interface HealthScore {
  overall: number // 0-100
  factors: HealthFactor[]
}

interface UsageMetric {
  metric: string
  quantity: number
  unit: string
  cost: number
}

interface RecommendedAction {
  id: string
  priority: "low" | "medium" | "high" | "critical"
  action: string
  reason: string
  impact: string
}

interface CVMData {
  financials: FinancialKPIs
  invoices: InvoiceRecord[]
  paymentTimeline: PaymentTimelineEntry[]
  churnRisk: ChurnRisk
  healthScore: HealthScore
  usageSummary: UsageMetric[]
  customerTier: "PLATINUM" | "GOLD" | "SILVER" | "BRONZE"
  valueSegment: "high" | "medium" | "low"
  riskSegment: "low" | "medium" | "high" | "critical"
  recommendedActions: RecommendedAction[]
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

// ─── Status Badges ───────────────────────────────────────────────────────────

function InvoiceStatusBadge({ status }: { status: InvoiceRecord["status"] }) {
  switch (status) {
    case "paid":
      return (
        <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
          <CheckCircle2 className="mr-1 h-3 w-3" />
          Paid
        </Badge>
      )
    case "partially_paid":
      return (
        <Badge className="bg-blue-500/15 text-blue-400 border-blue-500/30">
          <Minus className="mr-1 h-3 w-3" />
          Partial
        </Badge>
      )
    case "unpaid":
      return (
        <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30">
          <Clock className="mr-1 h-3 w-3" />
          Unpaid
        </Badge>
      )
    case "overdue":
      return (
        <Badge className="bg-red-500/15 text-red-400 border-red-500/30">
          <XCircle className="mr-1 h-3 w-3" />
          Overdue
        </Badge>
      )
    case "cancelled":
      return (
        <Badge className="bg-slate-500/15 text-slate-400 border-slate-500/30">
          <XCircle className="mr-1 h-3 w-3" />
          Cancelled
        </Badge>
      )
    default:
      return <Badge variant="secondary">{status}</Badge>
  }
}

function PaymentStatusBadge({ status }: { status: PaymentTimelineEntry["status"] }) {
  switch (status) {
    case "completed":
      return (
        <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
          <CheckCircle2 className="mr-1 h-3 w-3" />
          Completed
        </Badge>
      )
    case "pending":
      return (
        <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30">
          <Clock className="mr-1 h-3 w-3" />
          Pending
        </Badge>
      )
    case "failed":
      return (
        <Badge className="bg-red-500/15 text-red-400 border-red-500/30">
          <XCircle className="mr-1 h-3 w-3" />
          Failed
        </Badge>
      )
    default:
      return <Badge variant="secondary">{status}</Badge>
  }
}

function ActionPriorityBadge({ priority }: { priority: RecommendedAction["priority"] }) {
  switch (priority) {
    case "critical":
      return (
        <Badge className="bg-red-500/15 text-red-400 border-red-500/30">
          <CircleAlert className="mr-1 h-3 w-3" />
          Critical
        </Badge>
      )
    case "high":
      return (
        <Badge className="bg-orange-500/15 text-orange-400 border-orange-500/30">
          <ArrowUpRight className="mr-1 h-3 w-3" />
          High
        </Badge>
      )
    case "medium":
      return (
        <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30">
          <Minus className="mr-1 h-3 w-3" />
          Medium
        </Badge>
      )
    case "low":
      return (
        <Badge className="bg-slate-500/15 text-slate-400 border-slate-500/30">
          <Minus className="mr-1 h-3 w-3" />
          Low
        </Badge>
      )
    default:
      return <Badge variant="secondary">{priority}</Badge>
  }
}

// ─── Tier Badge ──────────────────────────────────────────────────────────────

function TierBadge({ tier }: { tier: CVMData["customerTier"] }) {
  switch (tier) {
    case "PLATINUM":
      return (
        <div className="flex items-center gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-violet-500/20 to-purple-500/20 border border-violet-500/30">
            <Award className="h-5 w-5 text-violet-400" />
          </div>
          <div>
            <Badge className="bg-violet-500/15 text-violet-400 border-violet-500/30 text-sm font-bold">
              PLATINUM
            </Badge>
            <p className="text-[10px] text-muted-foreground mt-0.5">Top tier customer</p>
          </div>
        </div>
      )
    case "GOLD":
      return (
        <div className="flex items-center gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-amber-500/20 to-yellow-500/20 border border-amber-500/30">
            <Award className="h-5 w-5 text-amber-400" />
          </div>
          <div>
            <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30 text-sm font-bold">
              GOLD
            </Badge>
            <p className="text-[10px] text-muted-foreground mt-0.5">High value customer</p>
          </div>
        </div>
      )
    case "SILVER":
      return (
        <div className="flex items-center gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-slate-400/20 to-gray-400/20 border border-slate-400/30">
            <Award className="h-5 w-5 text-slate-300" />
          </div>
          <div>
            <Badge className="bg-slate-400/15 text-slate-300 border-slate-400/30 text-sm font-bold">
              SILVER
            </Badge>
            <p className="text-[10px] text-muted-foreground mt-0.5">Growing customer</p>
          </div>
        </div>
      )
    case "BRONZE":
      return (
        <div className="flex items-center gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-orange-700/20 to-amber-700/20 border border-orange-700/30">
            <Award className="h-5 w-5 text-orange-600" />
          </div>
          <div>
            <Badge className="bg-orange-700/15 text-orange-500 border-orange-700/30 text-sm font-bold">
              BRONZE
            </Badge>
            <p className="text-[10px] text-muted-foreground mt-0.5">Entry tier customer</p>
          </div>
        </div>
      )
  }
}

// ─── Segment Badges ───────────────────────────────────────────────────────────

function SegmentBadge({ label, value }: { label: string; value: string }) {
  const getColor = (v: string) => {
    switch (v) {
      case "high":
      case "low":
        return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
      case "medium":
        return "bg-amber-500/15 text-amber-400 border-amber-500/30"
      case "critical":
        return "bg-red-500/15 text-red-400 border-red-500/30"
      default:
        return "bg-slate-500/15 text-slate-400 border-slate-500/30"
    }
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground">{label}:</span>
      <Badge className={cn("border capitalize", getColor(value))}>
        {value}
      </Badge>
    </div>
  )
}

// ─── Churn Risk Gauge ────────────────────────────────────────────────────────

function ChurnRiskGauge({ churnRisk }: { churnRisk: ChurnRisk }) {
  const getColor = (level: ChurnRisk["level"]) => {
    switch (level) {
      case "low":
        return { fill: "#22c55e", text: "text-emerald-400", bg: "bg-emerald-500/15", border: "border-emerald-500/30" }
      case "medium":
        return { fill: "#f59e0b", text: "text-amber-400", bg: "bg-amber-500/15", border: "border-amber-500/30" }
      case "high":
        return { fill: "#ef4444", text: "text-red-400", bg: "bg-red-500/15", border: "border-red-500/30" }
      case "critical":
        return { fill: "#991b1b", text: "text-red-600", bg: "bg-red-900/20", border: "border-red-800/40" }
    }
  }

  const colors = getColor(churnRisk.level)

  const gaugeData = [
    { name: "risk", value: churnRisk.score },
    { name: "remainder", value: 100 - churnRisk.score },
  ]

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative h-40 w-40">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={gaugeData}
              cx="50%"
              cy="50%"
              startAngle={180}
              endAngle={0}
              innerRadius={60}
              outerRadius={80}
              paddingAngle={0}
              dataKey="value"
              stroke="none"
            >
              <Cell key="risk" fill={colors.fill} />
              <Cell key="remainder" fill="rgba(100,116,139,0.15)" />
            </Pie>
            <Tooltip
              contentStyle={{
                background: "rgba(15,23,42,0.95)",
                border: "1px solid rgba(100,116,139,0.3)",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              formatter={(value: number) => [`${value}%`, "Risk"]}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center" style={{ paddingTop: "20px" }}>
          <span className={cn("text-3xl font-bold", colors.text)}>{churnRisk.score}</span>
          <span className="text-xs text-muted-foreground">/ 100</span>
        </div>
      </div>
      <Badge className={cn("border text-sm font-semibold capitalize", colors.bg, colors.text, colors.border)}>
        {churnRisk.level} Risk
      </Badge>
      {churnRisk.factors.length > 0 && (
        <div className="w-full space-y-1 mt-1">
          <p className="text-xs font-medium text-muted-foreground">Key Factors:</p>
          {churnRisk.factors.slice(0, 3).map((factor, i) => (
            <div key={i} className="flex items-start gap-1.5">
              <AlertTriangle className="h-3 w-3 text-amber-400 mt-0.5 shrink-0" />
              <span className="text-xs text-foreground/80">{factor}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Health Score Card ────────────────────────────────────────────────────────

function HealthScoreCard({ healthScore }: { healthScore: HealthScore }) {
  const getColor = (score: number) => {
    if (score >= 75) return { text: "text-emerald-400", bar: "bg-emerald-500" }
    if (score >= 50) return { text: "text-amber-400", bar: "bg-amber-500" }
    if (score >= 25) return { text: "text-orange-400", bar: "bg-orange-500" }
    return { text: "text-red-400", bar: "bg-red-500" }
  }

  const getTrendIcon = (trend: HealthFactor["trend"]) => {
    switch (trend) {
      case "up":
        return <ArrowUpRight className="h-3 w-3 text-emerald-400" />
      case "down":
        return <ArrowDownRight className="h-3 w-3 text-red-400" />
      case "stable":
        return <Minus className="h-3 w-3 text-muted-foreground" />
    }
  }

  const overallColor = getColor(healthScore.overall)

  return (
    <div className="space-y-4">
      {/* Overall Score */}
      <div className="flex items-center gap-4">
        <div className={cn("flex h-16 w-16 items-center justify-center rounded-full border-4", overallColor.text)}
          style={{ borderColor: "currentColor" }}
        >
          <span className={cn("text-xl font-bold", overallColor.text)}>{healthScore.overall}</span>
        </div>
        <div>
          <p className="text-sm font-semibold text-foreground">Overall Health</p>
          <p className="text-xs text-muted-foreground">Composite score</p>
        </div>
      </div>

      {/* Factor Breakdown */}
      <div className="space-y-3">
        {healthScore.factors.map((factor, i) => {
          const factorColor = getColor(factor.score)
          return (
            <div key={i} className="space-y-1">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-foreground">{factor.name}</span>
                  {getTrendIcon(factor.trend)}
                </div>
                <span className={cn("text-xs font-semibold", factorColor.text)}>{factor.score}%</span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-muted/30 overflow-hidden">
                <div
                  className={cn("h-full rounded-full transition-all", factorColor.bar)}
                  style={{ width: `${factor.score}%` }}
                />
              </div>
              <p className="text-[10px] text-muted-foreground">Weight: {factor.weight}%</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────

function KPICard({
  title,
  value,
  icon: Icon,
  trend,
  trendValue,
  subtitle,
}: {
  title: string
  value: string
  icon: React.ElementType
  trend?: "up" | "down" | "neutral"
  trendValue?: string
  subtitle?: string
}) {
  return (
    <Card className="border-border bg-card">
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{title}</p>
            <p className="text-xl font-bold text-foreground">{value}</p>
            {subtitle && <p className="text-[10px] text-muted-foreground">{subtitle}</p>}
            {trend && trendValue && (
              <div className="flex items-center gap-1 mt-1">
                {trend === "up" && <TrendingUp className="h-3 w-3 text-emerald-400" />}
                {trend === "down" && <TrendingDown className="h-3 w-3 text-red-400" />}
                {trend === "neutral" && <Minus className="h-3 w-3 text-muted-foreground" />}
                <span
                  className={cn(
                    "text-xs font-medium",
                    trend === "up" && "text-emerald-400",
                    trend === "down" && "text-red-400",
                    trend === "neutral" && "text-muted-foreground"
                  )}
                >
                  {trendValue}
                </span>
              </div>
            )}
          </div>
          <div className="rounded-lg bg-primary/10 p-2">
            <Icon className="h-4 w-4 text-primary" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Reusable Section Card ───────────────────────────────────────────────────

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

// ─── Skeleton ────────────────────────────────────────────────────────────────

function SkeletonLoader() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="h-28 rounded-xl border border-border bg-card" />
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="h-64 rounded-xl border border-border bg-card" />
        <div className="h-64 rounded-xl border border-border bg-card" />
        <div className="h-64 rounded-xl border border-border bg-card" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="h-72 rounded-xl border border-border bg-card" />
        <div className="h-72 rounded-xl border border-border bg-card" />
      </div>
    </div>
  )
}

// ─── Empty State ─────────────────────────────────────────────────────────────

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

// ─── Main Component ──────────────────────────────────────────────────────────

interface CVMTabProps {
  customerId: string
}

export function CVMTab({ customerId }: CVMTabProps) {
  const [data, setData] = useState<CVMData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchCVM = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`/api/crm/customers/${encodeURIComponent(customerId)}/360/cvm`, {
        cache: "no-store",
      })
      if (!response.ok) {
        throw new Error(`Failed to fetch CVM data: ${response.status}`)
      }
      const json = await response.json()
      setData(json.data ?? json)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load CVM data")
    } finally {
      setLoading(false)
    }
  }, [customerId])

  useEffect(() => {
    fetchCVM()
  }, [fetchCVM])

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">Loading customer value data…</span>
        </div>
        <SkeletonLoader />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="rounded-full bg-destructive/10 p-4 mb-4">
          <AlertTriangle className="h-6 w-6 text-destructive" />
        </div>
        <h3 className="text-lg font-semibold text-foreground mb-1">Failed to load CVM data</h3>
        <p className="text-sm text-muted-foreground mb-4 max-w-md">{error}</p>
        <button
          onClick={fetchCVM}
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
          <BarChart3 className="h-6 w-6 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold text-foreground mb-1">No CVM data</h3>
        <p className="text-sm text-muted-foreground">No customer value data found for this customer.</p>
      </div>
    )
  }

  const { financials, invoices, paymentTimeline, churnRisk, healthScore, usageSummary, customerTier, valueSegment, riskSegment, recommendedActions } = data

  return (
    <div className="space-y-6">
      {/* ── Tier + Segments Banner ──────────────────────────────────────── */}
      <Card className="border-border bg-card">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <TierBadge tier={customerTier} />
            <div className="flex flex-wrap items-center gap-4">
              <SegmentBadge label="Value" value={valueSegment} />
              <SegmentBadge label="Risk" value={riskSegment} />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Financial KPI Cards ─────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <KPICard
          title="Monthly Recurring"
          value={formatCurrency(financials.mrr)}
          icon={DollarSign}
          subtitle="MRR"
        />
        <KPICard
          title="Annual Recurring"
          value={formatCurrency(financials.arr)}
          icon={Calendar}
          subtitle="ARR"
        />
        <KPICard
          title="Lifetime Value"
          value={formatCurrency(financials.ltv)}
          icon={Target}
          subtitle="LTV"
        />
        <KPICard
          title="Outstanding Balance"
          value={formatCurrency(financials.outstandingBalance)}
          icon={CreditCard}
          subtitle="Current balance"
        />
        <KPICard
          title="Payment Reliability"
          value={`${financials.paymentReliability}%`}
          icon={Shield}
          subtitle="On-time payments"
        />
      </div>

      {/* ── Churn Risk + Health Score ───────────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Churn Risk" icon={Gauge}>
          <ChurnRiskGauge churnRisk={churnRisk} />
        </SectionCard>

        <SectionCard title="Health Score" icon={HeartPulse}>
          <HealthScoreCard healthScore={healthScore} />
        </SectionCard>
      </div>

      {/* ── Invoice History Table ───────────────────────────────────────── */}
      <SectionCard title="Invoice History" icon={Receipt}>
        {invoices.length === 0 ? (
          <EmptyState message="No invoices on record" />
        ) : (
          <ScrollArea className="max-h-80">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Invoice #</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Due Date</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invoices.map((invoice) => (
                  <TableRow key={invoice.id}>
                    <TableCell className="font-medium text-foreground">{invoice.invoiceNumber}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDate(invoice.date)}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDate(invoice.dueDate)}</TableCell>
                    <TableCell className="text-right font-semibold text-foreground">
                      {formatCurrency(invoice.amount)}
                    </TableCell>
                    <TableCell>
                      <InvoiceStatusBadge status={invoice.status} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        )}
      </SectionCard>

      {/* ── Payment Timeline + Usage Summary ────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Payment Timeline" icon={Activity}>
          {paymentTimeline.length === 0 ? (
            <EmptyState message="No payment history" />
          ) : (
            <ScrollArea className="max-h-72">
              <div className="space-y-2">
                {paymentTimeline.map((entry) => (
                  <div
                    key={entry.id}
                    className="flex items-start justify-between gap-3 rounded-lg border border-border bg-secondary/20 p-3 transition-colors hover:border-primary/30"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-foreground truncate">{entry.description}</p>
                        <PaymentStatusBadge status={entry.status} />
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-xs text-muted-foreground">{formatDate(entry.date)}</span>
                        <span className="text-xs text-muted-foreground">•</span>
                        <span className="text-xs capitalize text-muted-foreground">{entry.type}</span>
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p
                        className={cn(
                          "text-sm font-semibold",
                          entry.type === "payment" && "text-emerald-400",
                          entry.type === "refund" && "text-red-400",
                          entry.type === "adjustment" && "text-amber-400"
                        )}
                      >
                        {entry.type === "refund" ? "-" : entry.type === "adjustment" ? "±" : ""}
                        {formatCurrency(entry.amount)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </SectionCard>

        <SectionCard title="Usage Summary" icon={Zap}>
          {usageSummary.length === 0 ? (
            <EmptyState message="No usage data available" />
          ) : (
            <div className="space-y-3">
              {usageSummary.map((usage, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded-lg border border-border bg-secondary/20 p-3"
                >
                  <div className="flex items-center gap-3">
                    <div className="rounded-lg bg-primary/10 p-2">
                      <Activity className="h-4 w-4 text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">{usage.metric}</p>
                      <p className="text-xs text-muted-foreground">
                        {usage.quantity.toLocaleString()} {usage.unit}
                      </p>
                    </div>
                  </div>
                  <p className="text-sm font-semibold text-foreground">{formatCurrency(usage.cost)}</p>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      {/* ── Recommended Actions ─────────────────────────────────────────── */}
      <SectionCard title="Recommended Actions" icon={Lightbulb}>
        {recommendedActions.length === 0 ? (
          <EmptyState message="No recommended actions at this time" />
        ) : (
          <div className="space-y-3">
            {recommendedActions.map((action) => (
              <div
                key={action.id}
                className="rounded-lg border border-border bg-secondary/20 p-4 transition-colors hover:border-primary/30"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <ActionPriorityBadge priority={action.priority} />
                    </div>
                    <p className="text-sm font-semibold text-foreground mt-2">{action.action}</p>
                    <p className="text-xs text-muted-foreground mt-1">{action.reason}</p>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0 mt-1" />
                </div>
                <div className="mt-2 flex items-center gap-1.5">
                  <TrendingUp className="h-3 w-3 text-emerald-400" />
                  <span className="text-xs text-emerald-400">{action.impact}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  )
}
