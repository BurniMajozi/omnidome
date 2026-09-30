"use client"

import type { JSX } from "react"
import { useEffect, useState } from "react"
import { ModuleLayout } from "./module-layout"
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    PieChart,
    Pie,
    Cell,
    AreaChart,
    Area,
} from "recharts"
import { TrendingDown, Heart, AlertTriangle, RefreshCw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { tileLabel, type Loadable } from "@/lib/service-state"
import {
    loadCrmActivities,
    loadCrmCustomers,
    loadCrmInsights,
    loadCrmSummary,
    loadCrmTasks,
    useOps,
} from "@/lib/ops-api"
import {
    allSettled,
    atRiskCustomers,
    dataOr,
    fmtInt,
    healthBuckets,
    mrrBySegment,
    normIssueStatus,
    normPriority,
    normSeverity,
    normTaskStatus,
    pct,
    statusCountsFromSummary,
    type CrmCustomerRow,
} from "@/lib/ops-derive"
import { JourneyBuilderDashboard } from "./journey-builder/journey-builder-dashboard"

/**
 * Retention. Every figure is read from the CRM service (customers, lifecycle
 * health, churn predictions, activity feed, tasks). Nothing is sampled or
 * illustrative: when CRM is down the tiles say so, and sections CRM has no data
 * for (churn reasons) say "No data yet".
 */

const HEALTH_COLORS: Record<string, string> = {
    Excellent: "#4ade80",
    Good: "#60a5fa",
    "At Risk": "#f97316",
    Critical: "#ef4444",
    Unknown: "#737373",
}

const tooltipStyle = {
    backgroundColor: "#262626",
    border: "1px solid #404040",
    borderRadius: "8px",
    color: "#fff",
}

const tableColumns = [
    { key: "account", label: "Account" },
    { key: "customer", label: "Customer" },
    { key: "segment", label: "Segment" },
    { key: "health", label: "Health" },
    { key: "status", label: "Status" },
    { key: "mrr", label: "MRR (R)" },
]

const retentionKpiIconMap: Record<string, JSX.Element> = {
    churn: <TrendingDown className="h-5 w-5 text-emerald-400" />,
    risk: <AlertTriangle className="h-5 w-5 text-amber-400" />,
    retention: <Heart className="h-5 w-5 text-rose-400" />,
    saved: <RefreshCw className="h-5 w-5 text-blue-400" />,
}

const tile = (l: Loadable<unknown>, value: () => string) => (l.state === "ready" ? value() : (tileLabel(l) ?? "—"))

const fullName = (c: CrmCustomerRow) => `${c.first_name ?? ""} ${c.last_name ?? ""}`.trim() || "Unnamed customer"

export function RetentionModule({ activeTabOverride }: { activeTabOverride?: string }) {
    const [activeTab, setActiveTab] = useState("overview")
    const summary = useOps(loadCrmSummary)
    const customers = useOps(loadCrmCustomers)
    const insights = useOps(loadCrmInsights)
    const activities = useOps(loadCrmActivities)
    const tasks = useOps(loadCrmTasks)

    useEffect(() => {
        if (!activeTabOverride) return
        setActiveTab(activeTabOverride)
    }, [activeTabOverride])

    const reloadAll = () => {
        summary.reload()
        customers.reload()
        insights.reload()
        activities.reload()
        tasks.reload()
    }

    // ModuleLayout copies its list props into state on mount, so only mount it
    // once every source has answered.
    if (!allSettled(summary.value, customers.value, insights.value, activities.value, tasks.value)) {
        return (
            <div className="space-y-4" aria-busy="true" aria-label="Loading retention data">
                <div className="h-16 animate-pulse rounded-lg bg-muted/50" />
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    {[0, 1, 2, 3].map((i) => (
                        <div key={i} className="h-28 animate-pulse rounded-lg bg-muted/50" />
                    ))}
                </div>
                <div className="h-64 animate-pulse rounded-lg bg-muted/50" />
            </div>
        )
    }

    const custRows: CrmCustomerRow[] = customers.value.state === "ready" ? customers.value.data.rows : []
    const custTotal = customers.value.state === "ready" ? customers.value.data.total : 0
    const truncated = custRows.length < custTotal
    const watch = atRiskCustomers(custRows)
    const buckets = healthBuckets(custRows)
    const segments = mrrBySegment(custRows)
    const status = summary.value.state === "ready" ? statusCountsFromSummary(summary.value.data?.flashcardKPIs) : null
    const totalCustomers: number | null =
        summary.value.state === "ready" && typeof summary.value.data?.totalCustomers === "number"
            ? summary.value.data.totalCustomers
            : null
    const churnTrend: Array<{ month: string; churn: number }> =
        summary.value.state === "ready" ? (summary.value.data?.customerData ?? []) : []
    const insightData = dataOr(insights.value, { aiRecommendations: [], issues: [] })
    const activityRows: any[] = dataOr(activities.value, [])
    const taskRows: any[] = dataOr(tasks.value, [])
    const sampleNote = truncated ? `Based on the first ${fmtInt(custRows.length)} of ${fmtInt(custTotal)} customers.` : "Based on all customers."

    const flashcardKPIs = [
        {
            id: "1",
            title: "Churned Customers",
            value: tile(summary.value, () => (status ? fmtInt(status.churned) : "—")),
            change: "",
            changeType: "neutral" as const,
            iconKey: "churn",
            backTitle: "Customer Status",
            backDetails: status
                ? [
                      { label: "Active", value: fmtInt(status.active) },
                      { label: "Suspended", value: fmtInt(status.suspended) },
                      { label: "Churned", value: fmtInt(status.churned) },
                  ]
                : [],
            backInsight: status && totalCustomers ? `${pct(status.churned, totalCustomers)} of ${fmtInt(totalCustomers)} customers have churned.` : "No customer status data available.",
        },
        {
            id: "2",
            title: "At-Risk Customers",
            value: tile(customers.value, () => fmtInt(watch.length)),
            change: "",
            changeType: "neutral" as const,
            iconKey: "risk",
            backTitle: "Health Distribution",
            backDetails: buckets.map((b) => ({ label: b.name, value: fmtInt(b.value) })),
            backInsight: `Customers whose CRM health score is below 60. ${sampleNote}`,
        },
        {
            id: "3",
            title: "Retention Rate",
            value: tile(summary.value, () => (status && totalCustomers ? pct(totalCustomers - status.churned, totalCustomers) : "—")),
            change: "",
            changeType: "neutral" as const,
            iconKey: "retention",
            backTitle: "Retained vs Churned",
            backDetails:
                status && totalCustomers
                    ? [
                          { label: "Retained", value: fmtInt(totalCustomers - status.churned) },
                          { label: "Churned", value: fmtInt(status.churned) },
                      ]
                    : [],
            backInsight: "Share of all customers on record that have not churned.",
        },
        {
            id: "4",
            title: "Suspended Accounts",
            value: tile(summary.value, () => (status ? fmtInt(status.suspended) : "—")),
            change: "",
            changeType: "neutral" as const,
            iconKey: "saved",
            backTitle: "Suspended",
            backDetails: status ? [{ label: "Suspended", value: fmtInt(status.suspended) }] : [],
            backInsight: "Accounts currently suspended; the usual precursor to churn.",
        },
    ].map((kpi) => ({ ...kpi, icon: retentionKpiIconMap[kpi.iconKey] ?? null }))

    const summaryText =
        summary.value.state === "ready" && status && totalCustomers !== null
            ? `${fmtInt(totalCustomers)} customers on record: ${fmtInt(status.active)} active, ${fmtInt(status.suspended)} suspended and ${fmtInt(status.churned)} churned (${pct(status.churned, totalCustomers)}). ` +
              (customers.value.state === "ready"
                  ? `CRM health scoring flags ${fmtInt(watch.length)} customers as at risk. ${sampleNote}`
                  : "Per-customer health could not be loaded.")
            : "Retention figures are unavailable because the CRM service could not be read. Nothing is estimated in its place."

    const tableData = [...custRows]
        .sort((a, b) => Number(atRiskCustomers([b]).length) - Number(atRiskCustomers([a]).length))
        .slice(0, 200)
        .map((c) => ({
            id: c.id,
            account: c.account_number ?? "—",
            customer: fullName(c),
            segment: c.customer_type ?? "—",
            health: c.health ?? "Unknown",
            status: c.status ?? "—",
            mrr: Math.round(c.mrr ?? 0),
        }))

    return (
        <ModuleLayout
            title="Retention"
            icon={<Heart className="h-5 w-5" />}
            subtitle="Churn prevention, win-back campaigns, and loyalty management"
            headerActions={
                <Button variant="outline" size="sm" onClick={reloadAll}>
                    <RefreshCw className="h-3.5 w-3.5" />
                    Refresh
                </Button>
            }
            flashcardKPIs={flashcardKPIs}
            activities={activityRows.map((a) => ({
                id: String(a.id),
                user: String(a.user ?? ""),
                action: String(a.action ?? ""),
                target: String(a.target ?? ""),
                time: String(a.time ?? ""),
                type: (["create", "update", "delete", "comment", "assign"].includes(a.type) ? a.type : "update") as "update",
            }))}
            issues={insightData.issues.map((i: any) => ({
                id: String(i.id),
                title: String(i.title ?? ""),
                severity: normSeverity(i.severity),
                status: normIssueStatus(i.status),
                assignee: String(i.assignee ?? ""),
                time: String(i.time ?? ""),
            }))}
            summary={summaryText}
            tasks={taskRows.map((t: any) => ({
                id: String(t.id),
                title: String(t.title ?? ""),
                priority: normPriority(t.priority),
                status: normTaskStatus(t.status),
                dueDate: t.dueDate ? new Date(t.dueDate).toLocaleDateString("en-ZA") : "No date",
                assignee: String(t.assignee ?? ""),
            }))}
            aiRecommendations={insightData.aiRecommendations.map((r: any) => ({
                id: String(r.id),
                title: String(r.title ?? ""),
                description: String(r.description ?? ""),
                impact: (["high", "medium", "low"].includes(r.impact) ? r.impact : "medium") as "medium",
                category: String(r.category ?? ""),
            }))}
            tableData={tableData}
            tableColumns={tableColumns}
        >
            <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
                <TabsList className="bg-secondary">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="journeys">Journeys</TabsTrigger>
                    <TabsTrigger value="events">Events</TabsTrigger>
                    <TabsTrigger value="watchlist">Watchlist</TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="space-y-6">
                    <div className="grid gap-6 lg:grid-cols-2">
                        {/* Churned per month */}
                        <div className="surface-card p-5">
                            <h3 className="section-title mb-4">Customers Churned per Month</h3>
                            {summary.value.state !== "ready" ? (
                                <NotConnected loadable={summary.value} service="CRM" onRetry={summary.reload} />
                            ) : churnTrend.length === 0 ? (
                                <NoDataYet message="No customer history yet" />
                            ) : (
                                <div className="h-64">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <AreaChart data={churnTrend}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                                            <XAxis dataKey="month" tick={{ fill: "#737373", fontSize: 12 }} />
                                            <YAxis allowDecimals={false} tick={{ fill: "#737373", fontSize: 12 }} />
                                            <Tooltip contentStyle={tooltipStyle} />
                                            <Legend />
                                            <Area type="monotone" dataKey="churn" stroke="#ef4444" fill="#ef444433" strokeWidth={2} name="Churned customers" />
                                        </AreaChart>
                                    </ResponsiveContainer>
                                </div>
                            )}
                        </div>

                        {/* Health segmentation */}
                        <div className="surface-card p-5">
                            <h3 className="section-title mb-4">Customer Health Segmentation</h3>
                            {customers.value.state !== "ready" ? (
                                <NotConnected loadable={customers.value} service="CRM" onRetry={customers.reload} />
                            ) : buckets.length === 0 ? (
                                <NoDataYet message="No customers yet" />
                            ) : (
                                <>
                                    <div className="h-64">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <PieChart>
                                                <Pie
                                                    data={buckets}
                                                    cx="50%"
                                                    cy="50%"
                                                    labelLine={false}
                                                    label={({ name, value }) => `${name}: ${Number(value).toLocaleString()}`}
                                                    outerRadius={80}
                                                    dataKey="value"
                                                >
                                                    {buckets.map((entry) => (
                                                        <Cell key={entry.name} fill={HEALTH_COLORS[entry.name] ?? "#737373"} />
                                                    ))}
                                                </Pie>
                                                <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => [value.toLocaleString(), "Customers"]} />
                                            </PieChart>
                                        </ResponsiveContainer>
                                    </div>
                                    <p className="mt-2 text-xs text-muted-foreground">{sampleNote}</p>
                                </>
                            )}
                        </div>
                    </div>

                    {/* Churn reasons: no data source */}
                    <div className="surface-card p-5">
                        <h3 className="section-title mb-4">Churn Reasons Analysis</h3>
                        <NoDataYet message="Not connected: churn reasons come from the Retention prediction service, which is not running." />
                    </div>

                    {/* Revenue by segment */}
                    <div className="surface-card p-5">
                        <h3 className="section-title mb-4">Average Monthly Revenue by Segment</h3>
                        {customers.value.state !== "ready" ? (
                            <NotConnected loadable={customers.value} service="CRM" onRetry={customers.reload} />
                        ) : segments.length === 0 ? (
                            <NoDataYet message="No billing data yet: no customer has a recurring revenue amount" />
                        ) : (
                            <div className="h-64">
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={segments}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                                        <XAxis dataKey="segment" tick={{ fill: "#737373", fontSize: 12 }} />
                                        <YAxis tick={{ fill: "#737373", fontSize: 12 }} tickFormatter={(v) => `R${v}`} />
                                        <Tooltip
                                            contentStyle={tooltipStyle}
                                            formatter={(value: number, _n: string, p: { payload?: { customers?: number } }) => [
                                                `R ${value.toLocaleString("en-ZA")} (${p.payload?.customers ?? 0} customers)`,
                                                "Avg MRR",
                                            ]}
                                        />
                                        <Bar dataKey="avgMrr" fill="#4ade80" name="Avg MRR" />
                                    </BarChart>
                                </ResponsiveContainer>
                            </div>
                        )}
                    </div>
                </TabsContent>

                <TabsContent value="journeys" className="mt-4">
                    <JourneyBuilderDashboard />
                </TabsContent>

                <TabsContent value="events" className="space-y-6">
                    <div className="surface-card p-5">
                        <h3 className="section-title mb-4">Retention Events</h3>
                        {activities.value.state !== "ready" ? (
                            <NotConnected loadable={activities.value} service="CRM" onRetry={activities.reload} />
                        ) : activityRows.length === 0 ? (
                            <NoDataYet message="No customer events recorded yet" />
                        ) : (
                            <div className="space-y-3">
                                {activityRows.map((event: any) => (
                                    <div key={event.id} className="rounded-lg border border-border bg-secondary/30 p-3">
                                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                            <div>
                                                <p className="card-title capitalize">{event.action}</p>
                                                <p className="text-xs text-muted-foreground">
                                                    {event.user} - {event.target}
                                                </p>
                                            </div>
                                            <span className="text-xs text-muted-foreground">{event.time}</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </TabsContent>

                <TabsContent value="watchlist" className="space-y-6">
                    <div className="surface-card p-5">
                        <h3 className="section-title mb-4">Watchlist</h3>
                        {customers.value.state !== "ready" ? (
                            <NotConnected loadable={customers.value} service="CRM" onRetry={customers.reload} />
                        ) : watch.length === 0 ? (
                            <NoDataYet message="No customers are currently flagged at risk" />
                        ) : (
                            <div className="space-y-3">
                                {watch.slice(0, 50).map((c) => (
                                    <div key={c.id} className="rounded-lg border border-border bg-secondary/30 p-3">
                                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                            <div>
                                                <p className="card-title">{fullName(c)}</p>
                                                <p className="text-xs text-muted-foreground">
                                                    {c.account_number ?? "No account number"} - {c.customer_type ?? "Unknown segment"}
                                                </p>
                                                <p className="text-xs text-muted-foreground">Status: {c.status ?? "unknown"}</p>
                                            </div>
                                            <div className="flex items-center gap-3 text-xs">
                                                <Badge className="badge-warning">{c.health}</Badge>
                                                <Badge variant="secondary" className="bg-secondary text-foreground">
                                                    R {Math.round(c.mrr ?? 0).toLocaleString("en-ZA")} / month
                                                </Badge>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                                {watch.length > 50 && (
                                    <p className="text-xs text-muted-foreground">Showing 50 of {fmtInt(watch.length)} at-risk customers.</p>
                                )}
                            </div>
                        )}
                    </div>
                </TabsContent>
            </Tabs>
        </ModuleLayout>
    )
}
