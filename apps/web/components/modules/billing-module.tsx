"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { PageHeader } from "@/components/ui/page-header"
import { TableShell } from "@/components/ui/table-shell"
import {
  Receipt,
  CreditCard,
  AlertTriangle,
  CheckCircle,
  Clock,
  Download,
  Send,
  MoreVertical,
  Phone,
  Mail,
  Ban,
  RefreshCcw,
  Plus,
} from "lucide-react"
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  Legend,
} from "recharts"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { useIsClient } from "@/lib/use-is-client"
import { useLoadable } from "@/lib/service-fetch"
import { sumMoney, type Loadable } from "@/lib/service-state"
import { NotConnected, NoDataYet, StatValue } from "@/components/ui/not-connected"

// All figures come from the billing service (/svc/billing/...). Nothing is
// hard-coded: when the service is down or returns no rows the UI says so.

const BASE = "/svc/billing"

interface RevenueRow {
  period: string
  total_invoiced_zar: string | number
  total_paid_zar: string | number
  total_outstanding_zar: string | number
}
interface AgingRow {
  bucket: string
  count: number
  total_zar: string | number
}
interface QueueRow {
  customer_id: string
  customer_name?: string | null
  total_overdue_zar: string | number
  oldest_overdue_date: string
  days_overdue: number
  invoice_count: number
  dunning_stage: string
}
interface InvoiceRow {
  id: string
  customer_id: string
  number: string
  status: string
  total_zar: string | number
  amount_paid_zar: string | number
  due_date: string
}
interface PaymentRow {
  method: string
  amount_zar: string | number
  status: string
}
interface Paginated<T> {
  items: T[]
  total: number
}

const AGING_LABELS: Record<string, string> = {
  current: "Current",
  "30_days": "1-30 Days",
  "60_days": "31-60 Days",
  "90_days_plus": "60+ Days",
}
const METHOD_COLORS = ["#10b981", "#3b82f6", "#f59e0b", "#8b5cf6", "#ef4444", "#14b8a6"]

const formatCurrency = (value: number) => `R ${Math.round(value).toLocaleString("en-ZA")}`

function mapLoadable<T, U>(l: Loadable<T>, fn: (d: T) => U): Loadable<U> {
  return l.state === "ready" ? { state: "ready", data: fn(l.data) } : (l as Loadable<U>)
}

export function BillingModule() {
  const revenue = useLoadable<RevenueRow[]>(`${BASE}/reports/revenue?months=6`)
  const aging = useLoadable<AgingRow[]>(`${BASE}/reports/aging`)
  const queue = useLoadable<QueueRow[]>(`${BASE}/collections/queue?min_days=1`)
  const invoices = useLoadable<Paginated<InvoiceRow>>(`${BASE}/invoices?page_size=100`)
  const payments = useLoadable<Paginated<PaymentRow>>(`${BASE}/payments?page_size=100`)

  const [activeTab, setActiveTab] = useState("overview")
  const isClient = useIsClient()

  // Oldest -> newest for the trend chart.
  const revenueSeries = mapLoadable(revenue.value, (rows) =>
    [...rows].reverse().map((r) => ({
      month: r.period,
      collected: Number(r.total_paid_zar),
      outstanding: Number(r.total_outstanding_zar),
    })),
  )
  const revenueHasData =
    revenueSeries.state === "ready" && revenueSeries.data.some((r) => r.collected > 0 || r.outstanding > 0)

  const thisMonth = mapLoadable(revenue.value, (rows) => rows[0] ?? null)
  const agingTotals = mapLoadable(aging.value, (rows) => {
    const overdueRows = rows.filter((r) => r.bucket !== "current")
    return {
      total: sumMoney(rows.map((r) => r.total_zar)),
      overdue: sumMoney(overdueRows.map((r) => r.total_zar)),
      count: rows.reduce((a, r) => a + r.count, 0),
      overdueCount: overdueRows.reduce((a, r) => a + r.count, 0),
    }
  })

  const agingSeries = mapLoadable(aging.value, (rows) =>
    rows.map((r) => ({ range: AGING_LABELS[r.bucket] ?? r.bucket, amount: Number(r.total_zar), customers: r.count })),
  )
  const agingHasData = agingSeries.state === "ready" && agingSeries.data.some((r) => r.amount > 0 || r.customers > 0)

  const methodSeries = mapLoadable(payments.value, (p) => {
    const totals = new Map<string, number>()
    for (const pay of p.items) {
      if (pay.status !== "completed") continue
      totals.set(pay.method, (totals.get(pay.method) ?? 0) + Number(pay.amount_zar))
    }
    const sum = [...totals.values()].reduce((a, b) => a + b, 0)
    return [...totals.entries()].map(([name, amt], i) => ({
      name,
      value: sum > 0 ? Math.round((amt / sum) * 1000) / 10 : 0,
      color: METHOD_COLORS[i % METHOD_COLORS.length],
    }))
  })

  const invoiceRows = mapLoadable(invoices.value, (p) =>
    p.items.map((i) => ({
      id: i.id,
      number: i.number,
      customer: i.customer_id.slice(0, 8),
      amount: Number(i.total_zar),
      date: i.due_date,
      status: i.status,
    })),
  )

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "paid":
        return <Badge className="badge-success">Paid</Badge>
      case "sent":
      case "pending":
      case "draft":
      case "partially_paid":
        return <Badge className="badge-warning">{status.replace("_", " ")}</Badge>
      case "overdue":
        return <Badge className="badge-danger">Overdue</Badge>
      default:
        return <Badge variant="secondary">{status}</Badge>
    }
  }

  const stageBadge = (stage: string) => {
    switch (stage) {
      case "sms_reminder":
        return <Badge className="badge-info">SMS reminder</Badge>
      case "email_warning":
        return <Badge className="badge-warning">Email warning</Badge>
      case "suspended":
        return <Badge className="bg-orange-500/20 text-orange-400">Suspended</Badge>
      case "collections":
        return <Badge className="badge-danger">Collections</Badge>
      default:
        return <Badge variant="secondary">{stage}</Badge>
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Receipt className="h-5 w-5" />}
        title="Billing & Collections"
        subtitle="Revenue tracking, invoices, and collections management"
        actions={
          <>
            <Button variant="outline" size="sm"><Download className="h-3.5 w-3.5" />Export</Button>
            <Button variant="cta" size="sm"><Plus className="h-3.5 w-3.5" />New Invoice</Button>
          </>
        }
      />

      {/* KPI Cards - real report data only */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Collected This Month</p>
                <p className="mt-1 text-2xl font-bold text-foreground">
                  <StatValue loadable={thisMonth}>
                    {(m) => (!isClient ? "R --" : formatCurrency(Number(m?.total_paid_zar ?? 0)))}
                  </StatValue>
                </p>
                <div className="mt-1 text-xs text-muted-foreground">
                  <StatValue loadable={thisMonth} className="text-xs">
                    {(m) => `Invoiced ${formatCurrency(Number(m?.total_invoiced_zar ?? 0))}`}
                  </StatValue>
                </div>
              </div>
              <div className="rounded-lg bg-emerald-500/20 p-2">
                <Receipt className="h-5 w-5 text-emerald-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Collection Rate</p>
                <p className="mt-1 text-2xl font-bold text-foreground">
                  <StatValue loadable={thisMonth}>
                    {(m) => {
                      const inv = Number(m?.total_invoiced_zar ?? 0)
                      return inv > 0 ? `${((Number(m?.total_paid_zar ?? 0) / inv) * 100).toFixed(1)}%` : "No data yet"
                    }}
                  </StatValue>
                </p>
                <p className="mt-1 text-xs text-muted-foreground">Paid / invoiced this month</p>
              </div>
              <div className="rounded-lg bg-blue-500/20 p-2">
                <CheckCircle className="h-5 w-5 text-blue-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Outstanding</p>
                <p className="mt-1 text-2xl font-bold text-foreground">
                  <StatValue loadable={agingTotals}>{(a) => (!isClient ? "R --" : formatCurrency(a.total))}</StatValue>
                </p>
                <div className="mt-1 flex items-center gap-1 text-amber-400">
                  <Clock className="h-3 w-3" />
                  <span className="text-xs">
                    <StatValue loadable={agingTotals} className="text-xs">{(a) => `${a.count} open invoices`}</StatValue>
                  </span>
                </div>
              </div>
              <div className="rounded-lg bg-amber-500/20 p-2">
                <CreditCard className="h-5 w-5 text-amber-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Overdue Amount</p>
                <p className="mt-1 text-2xl font-bold text-foreground">
                  <StatValue loadable={agingTotals}>{(a) => (!isClient ? "R --" : formatCurrency(a.overdue))}</StatValue>
                </p>
                <div className="mt-1 flex items-center gap-1 text-red-400">
                  <AlertTriangle className="h-3 w-3" />
                  <span className="text-xs">
                    <StatValue loadable={agingTotals} className="text-xs">{(a) => `${a.overdueCount} overdue invoices`}</StatValue>
                  </span>
                </div>
              </div>
              <div className="rounded-lg bg-red-500/20 p-2">
                <AlertTriangle className="h-5 w-5 text-red-400" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-secondary">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="invoices">Invoices</TabsTrigger>
          <TabsTrigger value="collections">Collections</TabsTrigger>
          <TabsTrigger value="aging">Aging Report</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Revenue Chart */}
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base">Revenue Collection Trend</CardTitle>
              </CardHeader>
              <CardContent>
                {revenueSeries.state !== "ready" ? (
                  <NotConnected loadable={revenueSeries} service="Billing" onRetry={revenue.reload} className="h-72" />
                ) : !revenueHasData ? (
                  <NoDataYet message="No invoices or payments in the last 6 months" className="flex h-72 items-center justify-center" />
                ) : (
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={revenueSeries.data}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis dataKey="month" stroke="#9ca3af" fontSize={12} />
                        <YAxis stroke="#9ca3af" fontSize={12} tickFormatter={(v) => formatCurrency(Number(v))} width={80} />
                        <Tooltip
                          contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }}
                          formatter={(value: number) => formatCurrency(value)}
                        />
                        <Area type="monotone" dataKey="collected" stackId="1" stroke="#10b981" fill="#10b981" fillOpacity={0.3} name="Collected" />
                        <Area type="monotone" dataKey="outstanding" stackId="2" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.3} name="Outstanding" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Payment Methods */}
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base">Payment Methods</CardTitle>
              </CardHeader>
              <CardContent>
                {methodSeries.state !== "ready" ? (
                  <NotConnected loadable={methodSeries} service="Billing" onRetry={payments.reload} className="h-72" />
                ) : methodSeries.data.length === 0 ? (
                  <NoDataYet message="No completed payments yet" className="flex h-72 items-center justify-center" />
                ) : (
                  <>
                    <div className="h-72">
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie data={methodSeries.data} cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={2} dataKey="value">
                            {methodSeries.data.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={entry.color} />
                            ))}
                          </Pie>
                          <Tooltip
                            contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }}
                            formatter={(value: number) => `${value}%`}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="mt-4 flex flex-wrap justify-center gap-4">
                      {methodSeries.data.map((item) => (
                        <div key={item.name} className="flex items-center gap-2">
                          <div className="h-3 w-3 rounded-full" style={{ backgroundColor: item.color }} />
                          <span className="text-sm text-muted-foreground">
                            {item.name} ({item.value}%)
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="invoices" className="mt-4">
          {invoiceRows.state !== "ready" ? (
            <NotConnected loadable={invoiceRows} service="Billing" onRetry={invoices.reload} />
          ) : (
            <TableShell
              title="Invoices"
              columns={[
                { key: "number", label: "Invoice" },
                { key: "customer", label: "Customer" },
                { key: "amount", label: "Amount", render: (v) => formatCurrency(Number(v)) },
                { key: "date", label: "Due" },
                { key: "status", label: "Status", render: (v) => getStatusBadge(String(v)) },
              ]}
              data={invoiceRows.data}
              searchPlaceholder="Search invoices..."
              onRefresh={invoices.reload}
            />
          )}
        </TabsContent>

        <TabsContent value="collections" className="mt-4">
          <Card className="border-border bg-card">
            <CardHeader>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <CardTitle className="text-base">Collections Queue</CardTitle>
                {queue.value.state === "ready" && (
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge className="badge-danger">{queue.value.data.filter((q) => q.days_overdue >= 30).length} Urgent (30+ days)</Badge>
                    <Badge className="badge-warning">{queue.value.data.filter((q) => q.days_overdue < 30).length} Follow-up</Badge>
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {queue.value.state !== "ready" ? (
                <NotConnected loadable={queue.value} service="Billing" onRetry={queue.reload} />
              ) : queue.value.data.length === 0 ? (
                <NoDataYet message="No overdue accounts" />
              ) : (
                <div className="space-y-3">
                  {queue.value.data.map((item) => (
                    <div
                      key={item.customer_id}
                      className="flex flex-col gap-4 rounded-lg border border-border bg-secondary/30 p-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div>
                        <p className="font-medium text-foreground">{item.customer_name ?? `Customer ${item.customer_id.slice(0, 8)}`}</p>
                        <p className="text-sm text-muted-foreground">{item.invoice_count} overdue invoice{item.invoice_count === 1 ? "" : "s"}</p>
                      </div>
                      <div className="text-left sm:text-center">
                        <p className="font-semibold text-foreground">{!isClient ? "R --" : formatCurrency(Number(item.total_overdue_zar))}</p>
                        <p className="text-xs text-red-400">{item.days_overdue} days overdue</p>
                      </div>
                      <div className="text-left sm:text-center">
                        <p className="text-sm text-muted-foreground">Oldest due</p>
                        <p className="text-sm text-foreground">{item.oldest_overdue_date}</p>
                      </div>
                      <div>{stageBadge(item.dunning_stage)}</div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Button variant="outline" size="icon" className="h-8 w-8 bg-transparent">
                          <Phone className="h-4 w-4" />
                        </Button>
                        <Button variant="outline" size="icon" className="h-8 w-8 bg-transparent">
                          <Mail className="h-4 w-4" />
                        </Button>
                        <Button variant="outline" size="icon" className="h-8 w-8 bg-transparent">
                          <Send className="h-4 w-4" />
                        </Button>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem>Log Promise to Pay</DropdownMenuItem>
                            <DropdownMenuItem>Escalate</DropdownMenuItem>
                            <DropdownMenuItem>
                              <Ban className="mr-2 h-4 w-4" />
                              Suspend Service
                            </DropdownMenuItem>
                            <DropdownMenuItem>
                              <RefreshCcw className="mr-2 h-4 w-4" />
                              Payment Arrangement
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="aging" className="mt-4">
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base">Accounts Receivable Aging</CardTitle>
            </CardHeader>
            <CardContent>
              {agingSeries.state !== "ready" ? (
                <NotConnected loadable={agingSeries} service="Billing" onRetry={aging.reload} />
              ) : !agingHasData ? (
                <NoDataYet message="No unpaid invoices - nothing to age" />
              ) : (
                <>
                  <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={agingSeries.data}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis dataKey="range" stroke="#9ca3af" fontSize={12} />
                        <YAxis stroke="#9ca3af" fontSize={12} tickFormatter={(v) => formatCurrency(Number(v))} width={80} />
                        <Tooltip
                          contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }}
                          formatter={(value: number) => [formatCurrency(value), "Amount"]}
                        />
                        <Legend />
                        <Bar dataKey="amount" name="Outstanding Amount" fill="#10b981" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
                    {agingSeries.data.map((item) => (
                      <div key={item.range} className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
                        <p className="text-sm text-muted-foreground">{item.range}</p>
                        <p className="mt-1 font-semibold text-foreground">{!isClient ? "R --" : formatCurrency(item.amount)}</p>
                        <p className="text-xs text-muted-foreground">{item.customers} invoices</p>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
