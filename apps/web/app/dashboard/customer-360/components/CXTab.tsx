"use client"

import { useEffect, useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ScrollArea } from "@/components/ui/scroll-area"
import { NumberTicker } from "@/components/ui/number-ticker"
import {
  ShoppingCart,
  Truck,
  Wrench,
  Headphones,
  Activity,
  Star,
  Clock,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Loader2,
  RefreshCw,
  Package,
  MapPin,
  Calendar,
  MessageSquare,
  TrendingUp,
  FileText,
  ChevronRight,
  Hash,
  Timer,
  ThumbsUp,
  ThumbsDown,
  Minus,
} from "lucide-react"
import { cn } from "@/lib/utils"

// ─── Types ───────────────────────────────────────────────────────────────────

interface Order {
  id: string
  orderNumber: string
  date: string
  items: string[]
  total: number
  status: "pending" | "processing" | "shipped" | "delivered" | "cancelled" | "returned"
}

interface Delivery {
  id: string
  orderId: string
  trackingNumber: string
  carrier: string
  status: "pending" | "in_transit" | "out_for_delivery" | "delivered" | "failed" | "returned"
  estimatedDelivery: string
  actualDelivery?: string
  address: string
}

interface TechnicianVisit {
  id: string
  date: string
  technicianName: string
  serviceType: string
  rating: number
  notes?: string
  status: "scheduled" | "in_progress" | "completed" | "cancelled"
}

interface SupportTicket {
  id: string
  ticketNumber: string
  subject: string
  priority: "low" | "medium" | "high" | "critical"
  status: "open" | "in_progress" | "resolved" | "closed" | "escalated"
  createdAt: string
  updatedAt: string
  assignee?: string
}

interface ActivityEvent {
  id: string
  type: "order" | "delivery" | "ticket" | "visit" | "note" | "nps" | "payment"
  title: string
  description: string
  timestamp: string
  icon?: string
}

interface NpsRecord {
  id: string
  score: number
  feedback?: string
  date: string
  channel: "email" | "sms" | "phone" | "in_app"
}

interface CXSummary {
  totalOrders: number
  openTickets: number
  avgTechnicianRating: number
  lastInteraction: string
  npsScore: number
  totalDeliveries: number
  completedVisits: number
}

interface CXData {
  summary: CXSummary
  orders: Order[]
  deliveries: Delivery[]
  technicianVisits: TechnicianVisit[]
  supportTickets: SupportTicket[]
  activityTimeline: ActivityEvent[]
  npsHistory: NpsRecord[]
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

function timeAgo(dateStr: string): string {
  if (!dateStr) return "—"
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  const now = new Date()
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (seconds < 60) return "just now"
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}mo ago`
  const years = Math.floor(months / 12)
  return `${years}y ago`
}

// ─── Status Badges ───────────────────────────────────────────────────────────

function OrderStatusBadge({ status }: { status: Order["status"] }) {
  switch (status) {
    case "delivered":
      return (
        <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
          <CheckCircle2 className="mr-1 h-3 w-3" />
          Delivered
        </Badge>
      )
    case "shipped":
      return (
        <Badge className="bg-blue-500/15 text-blue-400 border-blue-500/30">
          <Truck className="mr-1 h-3 w-3" />
          Shipped
        </Badge>
      )
    case "processing":
      return (
        <Badge className="bg-cyan-500/15 text-cyan-400 border-cyan-500/30">
          <Package className="mr-1 h-3 w-3" />
          Processing
        </Badge>
      )
    case "pending":
      return (
        <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30">
          <Clock className="mr-1 h-3 w-3" />
          Pending
        </Badge>
      )
    case "cancelled":
      return (
        <Badge className="bg-red-500/15 text-red-400 border-red-500/30">
          <XCircle className="mr-1 h-3 w-3" />
          Cancelled
        </Badge>
      )
    case "returned":
      return (
        <Badge className="bg-orange-500/15 text-orange-400 border-orange-500/30">
          <RefreshCw className="mr-1 h-3 w-3" />
          Returned
        </Badge>
      )
    default:
      return <Badge variant="secondary">{status}</Badge>
  }
}

function DeliveryStatusBadge({ status }: { status: Delivery["status"] }) {
  switch (status) {
    case "delivered":
      return (
        <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
          <CheckCircle2 className="mr-1 h-3 w-3" />
          Delivered
        </Badge>
      )
    case "in_transit":
      return (
        <Badge className="bg-blue-500/15 text-blue-400 border-blue-500/30">
          <Truck className="mr-1 h-3 w-3" />
          In Transit
        </Badge>
      )
    case "out_for_delivery":
      return (
        <Badge className="bg-cyan-500/15 text-cyan-400 border-cyan-500/30">
          <MapPin className="mr-1 h-3 w-3" />
          Out for Delivery
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
    case "returned":
      return (
        <Badge className="bg-orange-500/15 text-orange-400 border-orange-500/30">
          <RefreshCw className="mr-1 h-3 w-3" />
          Returned
        </Badge>
      )
    default:
      return <Badge variant="secondary">{status.replace("_", " ")}</Badge>
  }
}

function PriorityBadge({ priority }: { priority: SupportTicket["priority"] }) {
  switch (priority) {
    case "critical":
      return (
        <Badge className="bg-red-500/15 text-red-400 border-red-500/30">
          <AlertCircle className="mr-1 h-3 w-3" />
          Critical
        </Badge>
      )
    case "high":
      return (
        <Badge className="bg-orange-500/15 text-orange-400 border-orange-500/30">
          <AlertCircle className="mr-1 h-3 w-3" />
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

function TicketStatusBadge({ status }: { status: SupportTicket["status"] }) {
  switch (status) {
    case "open":
      return (
        <Badge className="bg-blue-500/15 text-blue-400 border-blue-500/30">
          <MessageSquare className="mr-1 h-3 w-3" />
          Open
        </Badge>
      )
    case "in_progress":
      return (
        <Badge className="bg-cyan-500/15 text-cyan-400 border-cyan-500/30">
          <Loader2 className="mr-1 h-3 w-3" />
          In Progress
        </Badge>
      )
    case "resolved":
      return (
        <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
          <CheckCircle2 className="mr-1 h-3 w-3" />
          Resolved
        </Badge>
      )
    case "closed":
      return (
        <Badge className="bg-slate-500/15 text-slate-400 border-slate-500/30">
          <XCircle className="mr-1 h-3 w-3" />
          Closed
        </Badge>
      )
    case "escalated":
      return (
        <Badge className="bg-red-500/15 text-red-400 border-red-500/30">
          <AlertCircle className="mr-1 h-3 w-3" />
          Escalated
        </Badge>
      )
    default:
      return <Badge variant="secondary">{status.replace("_", " ")}</Badge>
  }
}

function VisitStatusBadge({ status }: { status: TechnicianVisit["status"] }) {
  switch (status) {
    case "completed":
      return (
        <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
          <CheckCircle2 className="mr-1 h-3 w-3" />
          Completed
        </Badge>
      )
    case "in_progress":
      return (
        <Badge className="bg-cyan-500/15 text-cyan-400 border-cyan-500/30">
          <Loader2 className="mr-1 h-3 w-3" />
          In Progress
        </Badge>
      )
    case "scheduled":
      return (
        <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30">
          <Clock className="mr-1 h-3 w-3" />
          Scheduled
        </Badge>
      )
    case "cancelled":
      return (
        <Badge className="bg-red-500/15 text-red-400 border-red-500/30">
          <XCircle className="mr-1 h-3 w-3" />
          Cancelled
        </Badge>
      )
    default:
      return <Badge variant="secondary">{status}</Badge>
  }
}

// ─── Star Rating ─────────────────────────────────────────────────────────────

function StarRating({ rating, max = 5 }: { rating: number; max?: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: max }, (_, i) => (
        <Star
          key={i}
          className={cn(
            "h-3.5 w-3.5",
            i < Math.round(rating)
              ? "fill-amber-400 text-amber-400"
              : "fill-muted/30 text-muted/30"
          )}
        />
      ))}
      <span className="ml-1.5 text-xs font-medium text-foreground">{rating.toFixed(1)}</span>
    </div>
  )
}

// ─── NPS Gauge ───────────────────────────────────────────────────────────────

function NpsGauge({ score }: { score: number }) {
  const getColor = (s: number) => {
    if (s >= 7) return "text-emerald-400"
    if (s >= 4) return "text-amber-400"
    return "text-red-400"
  }

  const getLabel = (s: number) => {
    if (s >= 9) return "Excellent"
    if (s >= 7) return "Good"
    if (s >= 4) return "Average"
    return "Poor"
  }

  const getIcon = (s: number) => {
    if (s >= 7) return <ThumbsUp className="h-5 w-5" />
    if (s >= 4) return <Minus className="h-5 w-5" />
    return <ThumbsDown className="h-5 w-5" />
  }

  return (
    <div className="flex flex-col items-center gap-2">
      <div className={cn("flex items-center gap-2", getColor(score))}>
        {getIcon(score)}
        <span className="text-3xl font-bold">
          <NumberTicker value={score} decimalPlaces={1} />
        </span>
        <span className="text-sm text-muted-foreground">/10</span>
      </div>
      <Badge className={cn(
        "border",
        score >= 7
          ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
          : score >= 4
            ? "bg-amber-500/15 text-amber-400 border-amber-500/30"
            : "bg-red-500/15 text-red-400 border-red-500/30"
      )}>
        {getLabel(score)}
      </Badge>
      {/* NPS Bar */}
      <div className="w-full max-w-[200px] mt-1">
        <div className="h-2 w-full rounded-full bg-muted/30 overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all",
              score >= 7
                ? "bg-emerald-500"
                : score >= 4
                  ? "bg-amber-500"
                  : "bg-red-500"
            )}
            style={{ width: `${(score / 10) * 100}%` }}
          />
        </div>
        <div className="flex justify-between mt-1">
          <span className="text-[10px] text-muted-foreground">0</span>
          <span className="text-[10px] text-muted-foreground">10</span>
        </div>
      </div>
    </div>
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
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-28 rounded-xl border border-border bg-card" />
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="h-64 rounded-xl border border-border bg-card" />
        <div className="h-64 rounded-xl border border-border bg-card" />
      </div>
      <div className="h-48 rounded-xl border border-border bg-card" />
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

// ─── Activity Timeline Item ──────────────────────────────────────────────────

function TimelineItem({ event }: { event: ActivityEvent }) {
  const getIcon = () => {
    switch (event.type) {
      case "order":
        return <ShoppingCart className="h-4 w-4" />
      case "delivery":
        return <Truck className="h-4 w-4" />
      case "ticket":
        return <Headphones className="h-4 w-4" />
      case "visit":
        return <Wrench className="h-4 w-4" />
      case "nps":
        return <Star className="h-4 w-4" />
      case "payment":
        return <TrendingUp className="h-4 w-4" />
      default:
        return <Activity className="h-4 w-4" />
    }
  }

  const getIconColor = () => {
    switch (event.type) {
      case "order":
        return "bg-blue-500/15 text-blue-400"
      case "delivery":
        return "bg-cyan-500/15 text-cyan-400"
      case "ticket":
        return "bg-amber-500/15 text-amber-400"
      case "visit":
        return "bg-emerald-500/15 text-emerald-400"
      case "nps":
        return "bg-purple-500/15 text-purple-400"
      case "payment":
        return "bg-green-500/15 text-green-400"
      default:
        return "bg-muted text-muted-foreground"
    }
  }

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className={cn("rounded-full p-1.5", getIconColor())}>
          {getIcon()}
        </div>
        <div className="w-px flex-1 bg-border/50 mt-1" />
      </div>
      <div className="pb-6 min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">{event.title}</p>
        <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{event.description}</p>
        <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
          <Timer className="h-3 w-3" />
          {timeAgo(event.timestamp)}
        </p>
      </div>
    </div>
  )
}

// ─── Main Component ──────────────────────────────────────────────────────────

interface CXTabProps {
  customerId: string
}

export function CXTab({ customerId }: CXTabProps) {
  const [data, setData] = useState<CXData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchCX = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`/svc/crm/customers/${encodeURIComponent(customerId)}/360/cx`, {
        cache: "no-store",
      })
      if (!response.ok) {
        throw new Error(`Failed to fetch CX data: ${response.status}`)
      }
      const json = await response.json()
      setData(json.data ?? json)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load CX data")
    } finally {
      setLoading(false)
    }
  }, [customerId])

  useEffect(() => {
    fetchCX()
  }, [fetchCX])

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">Loading customer experience data…</span>
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
        <h3 className="text-lg font-semibold text-foreground mb-1">Failed to load CX data</h3>
        <p className="text-sm text-muted-foreground mb-4 max-w-md">{error}</p>
        <button
          onClick={fetchCX}
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
          <Headphones className="h-6 w-6 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold text-foreground mb-1">No CX data</h3>
        <p className="text-sm text-muted-foreground">No customer experience data found.</p>
      </div>
    )
  }

  const { summary, orders, deliveries, technicianVisits, supportTickets, activityTimeline, npsHistory } = data

  return (
    <div className="space-y-6">
      {/* ── CX Summary Cards ─────────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="border-border bg-card">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Total Orders</p>
                <p className="text-2xl font-bold text-foreground mt-1">
                  <NumberTicker value={summary.totalOrders} />
                </p>
              </div>
              <div className="rounded-xl bg-blue-500/10 p-2.5">
                <ShoppingCart className="h-5 w-5 text-blue-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Open Tickets</p>
                <p className="text-2xl font-bold text-foreground mt-1">
                  <NumberTicker value={summary.openTickets} />
                </p>
              </div>
              <div className="rounded-xl bg-amber-500/10 p-2.5">
                <Headphones className="h-5 w-5 text-amber-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Avg Tech Rating</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-2xl font-bold text-foreground">
                    <NumberTicker value={summary.avgTechnicianRating} decimalPlaces={1} />
                  </span>
                  <Star className="h-4 w-4 fill-amber-400 text-amber-400" />
                </div>
              </div>
              <div className="rounded-xl bg-emerald-500/10 p-2.5">
                <Wrench className="h-5 w-5 text-emerald-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Last Interaction</p>
                <p className="text-sm font-semibold text-foreground mt-2">
                  {timeAgo(summary.lastInteraction)}
                </p>
              </div>
              <div className="rounded-xl bg-purple-500/10 p-2.5">
                <Clock className="h-5 w-5 text-purple-400" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── NPS Score + Activity Timeline ────────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* NPS Score Card */}
        <SectionCard title="NPS Score" icon={TrendingUp}>
          <div className="flex flex-col items-center py-4">
            <NpsGauge score={summary.npsScore} />
            {npsHistory.length > 0 && (
              <div className="w-full mt-6 pt-4 border-t border-border/50">
                <p className="text-xs text-muted-foreground mb-3">Recent Surveys</p>
                <div className="space-y-2">
                  {npsHistory.slice(0, 3).map((record) => (
                    <div key={record.id} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={cn(
                          "text-xs font-semibold",
                          record.score >= 7
                            ? "text-emerald-400"
                            : record.score >= 4
                              ? "text-amber-400"
                              : "text-red-400"
                        )}>
                          {record.score}/10
                        </span>
                        <Badge variant="outline" className="text-[10px] capitalize">
                          {record.channel}
                        </Badge>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {timeAgo(record.date)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </SectionCard>

        {/* Activity Timeline */}
        <div className="lg:col-span-2">
          <SectionCard title="Activity Timeline" icon={Activity}>
            {activityTimeline.length === 0 ? (
              <EmptyState message="No activity recorded" />
            ) : (
              <ScrollArea className="max-h-80 pr-4">
                <div className="space-y-0">
                  {activityTimeline.map((event) => (
                    <TimelineItem key={event.id} event={event} />
                  ))}
                </div>
              </ScrollArea>
            )}
          </SectionCard>
        </div>
      </div>

      {/* ── Orders Table ─────────────────────────────────────────────────── */}
      <SectionCard title="Orders" icon={ShoppingCart}>
        {orders.length === 0 ? (
          <EmptyState message="No orders on record" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Order #</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Items</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead className="text-right">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {orders.map((order) => (
                <TableRow key={order.id}>
                  <TableCell className="font-mono text-sm">
                    <div className="flex items-center gap-1.5">
                      <Hash className="h-3 w-3 text-muted-foreground" />
                      {order.orderNumber}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <Calendar className="h-3 w-3 text-muted-foreground" />
                      <span className="text-sm">{formatDate(order.date)}</span>
                      <span className="text-xs text-muted-foreground">({timeAgo(order.date)})</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {order.items.slice(0, 2).map((item, i) => (
                        <Badge key={i} variant="outline" className="text-xs">
                          {item}
                        </Badge>
                      ))}
                      {order.items.length > 2 && (
                        <Badge variant="outline" className="text-xs">
                          +{order.items.length - 2} more
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right font-medium">
                    {formatCurrency(order.total)}
                  </TableCell>
                  <TableCell className="text-right">
                    <OrderStatusBadge status={order.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>

      {/* ── Deliveries + Technician Visits ───────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Deliveries */}
        <SectionCard title="Deliveries" icon={Truck}>
          {deliveries.length === 0 ? (
            <EmptyState message="No deliveries on record" />
          ) : (
            <ScrollArea className="max-h-80">
              <div className="space-y-3">
                {deliveries.map((delivery) => (
                  <div
                    key={delivery.id}
                    className="rounded-lg border border-border bg-secondary/20 p-3 transition-colors hover:border-primary/30"
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-foreground font-mono">
                            {delivery.trackingNumber}
                          </p>
                          <Badge variant="outline" className="text-xs">
                            {delivery.carrier}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                          <MapPin className="h-3 w-3 shrink-0" />
                          <span className="truncate">{delivery.address}</span>
                        </p>
                      </div>
                      <DeliveryStatusBadge status={delivery.status} />
                    </div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>ETA: {formatDate(delivery.estimatedDelivery)}</span>
                      {delivery.actualDelivery && (
                        <span className="text-emerald-400">
                          Delivered {timeAgo(delivery.actualDelivery)}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </SectionCard>

        {/* Technician Visits */}
        <SectionCard title="Technician Visits" icon={Wrench}>
          {technicianVisits.length === 0 ? (
            <EmptyState message="No technician visits on record" />
          ) : (
            <ScrollArea className="max-h-80">
              <div className="space-y-3">
                {technicianVisits.map((visit) => (
                  <div
                    key={visit.id}
                    className="rounded-lg border border-border bg-secondary/20 p-3 transition-colors hover:border-primary/30"
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-foreground">{visit.technicianName}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">{visit.serviceType}</p>
                      </div>
                      <VisitStatusBadge status={visit.status} />
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Calendar className="h-3 w-3" />
                        {formatDate(visit.date)}
                        <span>({timeAgo(visit.date)})</span>
                      </div>
                      {visit.status === "completed" && (
                        <StarRating rating={visit.rating} />
                      )}
                    </div>
                    {visit.notes && (
                      <p className="text-xs text-muted-foreground mt-2 italic border-t border-border/30 pt-2">
                        &ldquo;{visit.notes}&rdquo;
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </SectionCard>
      </div>

      {/* ── Support Tickets ───────────────────────────────────────────────── */}
      <SectionCard title="Support Tickets" icon={Headphones}>
        {supportTickets.length === 0 ? (
          <EmptyState message="No support tickets on record" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ticket #</TableHead>
                <TableHead>Subject</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Assignee</TableHead>
                <TableHead className="text-right">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {supportTickets.map((ticket) => (
                <TableRow key={ticket.id}>
                  <TableCell className="font-mono text-sm">
                    <div className="flex items-center gap-1.5">
                      <Hash className="h-3 w-3 text-muted-foreground" />
                      {ticket.ticketNumber}
                    </div>
                  </TableCell>
                  <TableCell className="max-w-[200px]">
                    <p className="text-sm text-foreground truncate">{ticket.subject}</p>
                  </TableCell>
                  <TableCell>
                    <PriorityBadge priority={ticket.priority} />
                  </TableCell>
                  <TableCell>
                    <TicketStatusBadge status={ticket.status} />
                  </TableCell>
                  <TableCell>
                    <span className="text-sm text-muted-foreground">
                      {ticket.assignee ?? "—"}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1.5 text-xs text-muted-foreground">
                      <Timer className="h-3 w-3" />
                      {timeAgo(ticket.updatedAt)}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>
    </div>
  )
}
