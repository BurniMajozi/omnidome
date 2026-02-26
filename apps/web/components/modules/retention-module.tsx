"use client"

import { useEffect, useState } from "react"
import { ModuleLayout } from "./module-layout"
import {
    BarChart,
    Bar,
    Line,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useModuleData } from "@/lib/module-data"

// Churn trend data over 6 months
const defaultChurnTrendData = [
    { month: "Jul", churnRate: 3.2, predictions: 3.5, retained: 96.8 },
    { month: "Aug", churnRate: 2.9, predictions: 3.1, retained: 97.1 },
    { month: "Sep", churnRate: 3.1, predictions: 2.9, retained: 96.9 },
    { month: "Oct", churnRate: 2.7, predictions: 2.8, retained: 97.3 },
    { month: "Nov", churnRate: 2.4, predictions: 2.5, retained: 97.6 },
    { month: "Dec", churnRate: 2.1, predictions: 2.2, retained: 97.9 },
]

// Churn risk segments
const defaultChurnRiskSegments = [
    { name: "High Risk", value: 847, fill: "#ef4444" },
    { name: "Medium Risk", value: 2134, fill: "#f97316" },
    { name: "Low Risk", value: 8521, fill: "#eab308" },
    { name: "Loyal", value: 13345, fill: "#4ade80" },
]

// Churn reasons breakdown
const defaultChurnReasons = [
    { reason: "Price Sensitivity", count: 342, percentage: 32 },
    { reason: "Service Issues", count: 267, percentage: 25 },
    { reason: "Competitor Offers", count: 192, percentage: 18 },
    { reason: "Relocation", count: 139, percentage: 13 },
    { reason: "No Longer Needed", count: 128, percentage: 12 },
]

type ChurnReasonPayload = {
    payload: {
        count: number
    }
}

// Customer lifetime value by segment
const defaultClvBySegment = [
    { segment: "Enterprise", clv: 48500, retentionRate: 94.2 },
    { segment: "Business", clv: 24800, retentionRate: 91.5 },
    { segment: "Premium", clv: 12400, retentionRate: 88.7 },
    { segment: "Standard", clv: 6200, retentionRate: 85.3 },
    { segment: "Basic", clv: 2400, retentionRate: 79.8 },
]

// Retention campaigns performance
const defaultCampaignPerformance = [
    { campaign: "Win-Back Email", saved: 142, cost: 2840, roi: 312 },
    { campaign: "Loyalty Discount", saved: 89, cost: 8900, roi: 156 },
    { campaign: "Personal Outreach", saved: 67, cost: 3350, roi: 248 },
    { campaign: "Upgrade Offer", saved: 45, cost: 1800, roi: 412 },
]

const defaultRetentionJourneys = [
    {
        id: "journey-1",
        name: "Cancel Save Journey",
        status: "active",
        audience: "High risk • Tenure > 6 months",
        offer: "Pause or Discount",
        conversion: "18%",
        saved: 142,
        lastUpdated: "Today",
    },
    {
        id: "journey-2",
        name: "Price Sensitivity Journey",
        status: "active",
        audience: "Price-sensitive • Standard tier",
        offer: "Targeted 10% offer",
        conversion: "14%",
        saved: 88,
        lastUpdated: "Yesterday",
    },
    {
        id: "journey-3",
        name: "Win-back Journey",
        status: "draft",
        audience: "Churned < 30 days",
        offer: "Limited-time upgrade",
        conversion: "-",
        saved: 0,
        lastUpdated: "2 days ago",
    },
]

const defaultRetentionEvents = [
    {
        id: "event-1",
        type: "Cancel Initiated",
        account: "ACC-78421",
        customer: "Lerato Mbeki",
        outcome: "Offer Accepted",
        channel: "Portal",
        time: "5 min ago",
    },
    {
        id: "event-2",
        type: "Offer Shown",
        account: "ACC-65892",
        customer: "Johan Pretorius",
        outcome: "Pending",
        channel: "Portal",
        time: "18 min ago",
    },
    {
        id: "event-3",
        type: "Cancel Completed",
        account: "ACC-91234",
        customer: "Nomvula Dlamini",
        outcome: "Churned",
        channel: "Portal",
        time: "1 hour ago",
    },
    {
        id: "event-4",
        type: "Offer Accepted",
        account: "ACC-45678",
        customer: "David Smith",
        outcome: "Saved",
        channel: "Success Team",
        time: "2 hours ago",
    },
]

const defaultWatchlist = [
    {
        id: "watch-1",
        account: "ACC-78421",
        customer: "Lerato Mbeki",
        segment: "Premium",
        riskScore: "94%",
        trigger: "Service issues spike",
        status: "Watching",
    },
    {
        id: "watch-2",
        account: "ACC-65892",
        customer: "Johan Pretorius",
        segment: "Business",
        riskScore: "87%",
        trigger: "Price sensitivity cluster",
        status: "Outreach",
    },
    {
        id: "watch-3",
        account: "ACC-23456",
        customer: "Sipho Nkosi",
        segment: "Premium",
        riskScore: "71%",
        trigger: "Low engagement",
        status: "Scheduled",
    },
]

const formatCurrency = (value: number) => `R ${value.toLocaleString("en-ZA")}`

const defaultFlashcardKPIs = [
    {
        id: "1",
        title: "Monthly Churn Rate",
        value: "2.1%",
        change: "-0.3%",
        changeType: "positive" as const,
        iconKey: "churn",
        backTitle: "Churn Breakdown",
        backDetails: [
            { label: "Voluntary Churn", value: "1.4%" },
            { label: "Involuntary Churn", value: "0.7%" },
            { label: "Target", value: "< 2.5%" },
        ],
        backInsight: "Lowest churn rate in 18 months",
    },
    {
        id: "2",
        title: "At-Risk Customers",
        value: "847",
        change: "-12%",
        changeType: "positive" as const,
        iconKey: "risk",
        backTitle: "Risk Distribution",
        backDetails: [
            { label: "Critical (90%+)", value: "124" },
            { label: "High (70-89%)", value: "298" },
            { label: "Elevated (50-69%)", value: "425" },
        ],
        backInsight: "AI model 87% accurate on predictions",
    },
    {
        id: "3",
        title: "Retention Rate",
        value: "97.9%",
        change: "+0.3%",
        changeType: "positive" as const,
        iconKey: "retention",
        backTitle: "Retention by Tenure",
        backDetails: [
            { label: "0-6 months", value: "92.4%" },
            { label: "6-24 months", value: "96.8%" },
            { label: "24+ months", value: "99.2%" },
        ],
        backInsight: "Long-term customers most stable",
    },
    {
        id: "4",
        title: "Customers Saved",
        value: "343",
        change: "+28%",
        changeType: "positive" as const,
        iconKey: "saved",
        backTitle: "Save Methods",
        backDetails: [
            { label: "Discount Offers", value: "142" },
            { label: "Service Recovery", value: "108" },
            { label: "Personal Outreach", value: "93" },
        ],
        backInsight: "R 2.1M revenue preserved this month",
    },
]

const retentionKpiIconMap: Record<string, JSX.Element> = {
    churn: <TrendingDown className="h-5 w-5 text-emerald-400" />,
    risk: <AlertTriangle className="h-5 w-5 text-amber-400" />,
    retention: <Heart className="h-5 w-5 text-rose-400" />,
    saved: <RefreshCw className="h-5 w-5 text-blue-400" />,
}

const defaultActivities = [
    {
        id: "1",
        user: "AI System",
        action: "flagged high-risk customer",
        target: "ACC-78421",
        time: "5 minutes ago",
        type: "assign" as const,
    },
    {
        id: "2",
        user: "Retention Team",
        action: "saved customer with",
        target: "loyalty discount",
        time: "22 minutes ago",
        type: "update" as const,
    },
    {
        id: "3",
        user: "Win-Back Campaign",
        action: "re-activated",
        target: "12 customers",
        time: "1 hour ago",
        type: "create" as const,
    },
    {
        id: "4",
        user: "Thabo Ndlovu",
        action: "completed outreach for",
        target: "ACC-65892",
        time: "2 hours ago",
        type: "comment" as const,
    },
    {
        id: "5",
        user: "Churn Model",
        action: "updated predictions for",
        target: "2,847 accounts",
        time: "3 hours ago",
        type: "update" as const,
    },
]

const defaultIssues = [
    {
        id: "1",
        title: "124 customers with 90%+ churn probability",
        severity: "critical" as const,
        status: "in-progress" as const,
        assignee: "Retention Team",
        time: "Active",
    },
    {
        id: "2",
        title: "Spike in service-related churn in Cape Town",
        severity: "high" as const,
        status: "open" as const,
        assignee: "Regional Manager",
        time: "2 hours ago",
    },
    {
        id: "3",
        title: "Competitor campaign detected - MTN promo",
        severity: "high" as const,
        status: "in-progress" as const,
        assignee: "Marketing",
        time: "Yesterday",
    },
    {
        id: "4",
        title: "Win-back email campaign below target",
        severity: "medium" as const,
        status: "open" as const,
        assignee: "Campaign Manager",
        time: "2 days ago",
    },
]

const defaultSummary = `Retention performance shows strong improvement with the monthly churn rate dropping to 2.1%, the lowest in 18 months. The AI-powered churn prediction model has identified 847 at-risk customers with 87% prediction accuracy. This month, the retention team saved 343 customers, preserving R 2.1M in annual revenue. Key focus areas: 124 customers are in critical risk zone (90%+ churn probability), a service-related churn spike was detected in Cape Town requiring immediate attention, and competitor MTN is running an aggressive promotional campaign that may impact retention in budget segments.`

const defaultTasks = [
    {
        id: "1",
        title: "Contact 124 critical-risk customers",
        priority: "urgent" as const,
        status: "in-progress" as const,
        dueDate: "Today",
        assignee: "Retention Team",
    },
    {
        id: "2",
        title: "Launch counter-offer for MTN campaign",
        priority: "high" as const,
        status: "todo" as const,
        dueDate: "Tomorrow",
        assignee: "Marketing",
    },
    {
        id: "3",
        title: "Investigate Cape Town service issues",
        priority: "high" as const,
        status: "in-progress" as const,
        dueDate: "Today",
        assignee: "Service Manager",
    },
    {
        id: "4",
        title: "Update churn prediction model",
        priority: "normal" as const,
        status: "todo" as const,
        dueDate: "This week",
        assignee: "Data Science",
    },
]

const defaultAiRecommendations = [
    {
        id: "1",
        title: "Proactive Outreach Required",
        description: "48 customers show declining usage patterns similar to previous churners. Initiate engagement now.",
        impact: "high" as const,
        category: "Prevention",
    },
    {
        id: "2",
        title: "Price Sensitivity Cluster",
        description: "215 customers comparing competitors. Consider targeted retention offer with 15% discount.",
        impact: "high" as const,
        category: "Pricing",
    },
    {
        id: "3",
        title: "Service Recovery Opportunity",
        description: "67 customers had recent negative support experiences. Personal apology call recommended.",
        impact: "medium" as const,
        category: "Recovery",
    },
    {
        id: "4",
        title: "Loyalty Program Gap",
        description: "Long-term customers (3+ years) showing signs of disengagement. Launch appreciation campaign.",
        impact: "medium" as const,
        category: "Loyalty",
    },
]

const defaultTableData = [
    {
        id: "1",
        account: "ACC-78421",
        customer: "Lerato Mbeki",
        segment: "Premium",
        riskScore: "94%",
        tenure: "8 months",
        reason: "Service Issues",
        status: "Contacted",
        lastAction: "Today",
    },
    {
        id: "2",
        account: "ACC-65892",
        customer: "Johan Pretorius",
        segment: "Business",
        riskScore: "87%",
        tenure: "14 months",
        reason: "Price Sensitive",
        status: "Offer Sent",
        lastAction: "Yesterday",
    },
    {
        id: "3",
        account: "ACC-91234",
        customer: "Nomvula Dlamini",
        segment: "Standard",
        riskScore: "82%",
        tenure: "3 months",
        reason: "Competitor Offer",
        status: "Pending",
        lastAction: "2 days ago",
    },
    {
        id: "4",
        account: "ACC-45678",
        customer: "David Smith",
        segment: "Enterprise",
        riskScore: "76%",
        tenure: "26 months",
        reason: "Service Issues",
        status: "Escalated",
        lastAction: "Today",
    },
    {
        id: "5",
        account: "ACC-23456",
        customer: "Sipho Nkosi",
        segment: "Premium",
        riskScore: "71%",
        tenure: "11 months",
        reason: "No Engagement",
        status: "Scheduled",
        lastAction: "Tomorrow",
    },
]

const defaultTableColumns = [
    { key: "account", label: "Account" },
    { key: "customer", label: "Customer" },
    { key: "segment", label: "Segment" },
    { key: "riskScore", label: "Risk Score" },
    { key: "tenure", label: "Tenure" },
    { key: "reason", label: "Risk Reason" },
    { key: "status", label: "Status" },
    { key: "lastAction", label: "Last Action" },
]

export function RetentionModule({ activeTabOverride }: { activeTabOverride?: string }) {
    const { data } = useModuleData("retention", {
        churnTrendData: defaultChurnTrendData,
        churnRiskSegments: defaultChurnRiskSegments,
        churnReasons: defaultChurnReasons,
        clvBySegment: defaultClvBySegment,
        campaignPerformance: defaultCampaignPerformance,
        retentionJourneys: defaultRetentionJourneys,
        retentionEvents: defaultRetentionEvents,
        watchlist: defaultWatchlist,
        flashcardKPIs: defaultFlashcardKPIs,
        activities: defaultActivities,
        issues: defaultIssues,
        summary: defaultSummary,
        tasks: defaultTasks,
        aiRecommendations: defaultAiRecommendations,
        tableData: defaultTableData,
        tableColumns: defaultTableColumns,
    })

    const {
        churnTrendData,
        churnRiskSegments,
        churnReasons,
        clvBySegment,
        retentionJourneys,
        retentionEvents,
        watchlist,
        flashcardKPIs,
        activities,
        issues,
        summary,
        tasks,
        aiRecommendations,
        tableData,
        tableColumns,
    } = data

    const flashcardKPIsWithIcons = flashcardKPIs.map((kpi) => ({
        ...kpi,
        icon: retentionKpiIconMap[kpi.iconKey] ?? null,
    }))

    const journeysSafe = retentionJourneys ?? defaultRetentionJourneys
    const eventsSafe = retentionEvents ?? defaultRetentionEvents
    const watchlistSafe = watchlist ?? defaultWatchlist

    const [activeTab, setActiveTab] = useState("overview")

    useEffect(() => {
        if (!activeTabOverride) return
        setActiveTab(activeTabOverride)
    }, [activeTabOverride])

    return (
        <ModuleLayout
            title="Retention"
            flashcardKPIs={flashcardKPIsWithIcons}
            activities={activities}
            issues={issues}
            summary={summary}
            tasks={tasks}
            aiRecommendations={aiRecommendations}
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
                    {/* Charts */}
                    <div className="grid gap-6 lg:grid-cols-2">
                        {/* Churn Trend & Prediction */}
                        <div className="rounded-xl border border-border bg-card p-5">
                            <h3 className="mb-4 text-lg font-semibold text-foreground">Churn Rate Trend & Prediction</h3>
                            <div className="h-64">
                                <ResponsiveContainer width="100%" height="100%">
                                    <AreaChart data={churnTrendData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                                        <XAxis dataKey="month" tick={{ fill: "#737373", fontSize: 12 }} />
                                        <YAxis
                                            tick={{ fill: "#737373", fontSize: 12 }}
                                            tickFormatter={(v) => `${v}%`}
                                            domain={[0, 5]}
                                        />
                                        <Tooltip
                                            contentStyle={{
                                                backgroundColor: "#262626",
                                                border: "1px solid #404040",
                                                borderRadius: "8px",
                                                color: "#fff",
                                            }}
                                            formatter={(value: number, name: string) => [`${value}%`, name === "churnRate" ? "Actual Churn" : "AI Prediction"]}
                                        />
                                        <Legend />
                                        <Area type="monotone" dataKey="churnRate" stroke="#ef4444" fill="#ef444433" strokeWidth={2} name="Actual Churn" />
                                        <Area type="monotone" dataKey="predictions" stroke="#60a5fa" fill="#60a5fa22" strokeWidth={2} strokeDasharray="5 5" name="AI Prediction" />
                                    </AreaChart>
                                </ResponsiveContainer>
                            </div>
                        </div>

                        {/* Risk Segmentation */}
                        <div className="rounded-xl border border-border bg-card p-5">
                            <h3 className="mb-4 text-lg font-semibold text-foreground">Customer Risk Segmentation</h3>
                            <div className="h-64">
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie
                                            data={churnRiskSegments}
                                            cx="50%"
                                            cy="50%"
                                            labelLine={false}
                                            label={({ name, value }) => `${name}: ${value.toLocaleString()}`}
                                            outerRadius={80}
                                            fill="#4ade80"
                                            dataKey="value"
                                        >
                                            {churnRiskSegments.map((entry, index) => (
                                                <Cell key={`cell-${index}`} fill={entry.fill} />
                                            ))}
                                        </Pie>
                                        <Tooltip
                                            contentStyle={{
                                                backgroundColor: "#262626",
                                                border: "1px solid #404040",
                                                borderRadius: "8px",
                                                color: "#fff",
                                            }}
                                            formatter={(value: number) => [value.toLocaleString(), "Customers"]}
                                        />
                                    </PieChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>

                    {/* Churn Reasons */}
                    <div className="rounded-xl border border-border bg-card p-5">
                        <h3 className="mb-4 text-lg font-semibold text-foreground">Churn Reasons Analysis</h3>
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={churnReasons} layout="vertical">
                                    <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                                    <XAxis type="number" tick={{ fill: "#737373", fontSize: 12 }} tickFormatter={(v) => `${v}%`} />
                                    <YAxis type="category" dataKey="reason" tick={{ fill: "#737373", fontSize: 12 }} width={130} />
                                        <Tooltip
                                            contentStyle={{
                                                backgroundColor: "#262626",
                                                border: "1px solid #404040",
                                                borderRadius: "8px",
                                                color: "#fff",
                                            }}
                                            formatter={(value: number, name: string, props: ChurnReasonPayload) => {
                                                const label = name === "percentage" ? "Churned" : name
                                                return [`${props.payload.count} customers (${value}%)`, label]
                                            }}
                                        />
                                    <Bar dataKey="percentage" fill="#f97316" name="Percentage" />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    {/* CLV by Segment */}
                    <div className="rounded-xl border border-border bg-card p-5">
                        <h3 className="mb-4 text-lg font-semibold text-foreground">Customer Lifetime Value & Retention by Segment</h3>
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={clvBySegment}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                                    <XAxis dataKey="segment" tick={{ fill: "#737373", fontSize: 12 }} />
                                    <YAxis yAxisId="left" tick={{ fill: "#737373", fontSize: 12 }} tickFormatter={(v) => `R${v / 1000}K`} />
                                    <YAxis yAxisId="right" orientation="right" tick={{ fill: "#737373", fontSize: 12 }} tickFormatter={(v) => `${v}%`} domain={[70, 100]} />
                                    <Tooltip
                                        contentStyle={{
                                            backgroundColor: "#262626",
                                            border: "1px solid #404040",
                                            borderRadius: "8px",
                                            color: "#fff",
                                        }}
                                        formatter={(value: number, name: string) => [
                                            name === "clv" ? formatCurrency(value) : `${value}%`,
                                            name === "clv" ? "Lifetime Value" : "Retention Rate"
                                        ]}
                                    />
                                    <Legend />
                                    <Bar yAxisId="left" dataKey="clv" fill="#4ade80" name="Lifetime Value" />
                                    <Line yAxisId="right" type="monotone" dataKey="retentionRate" stroke="#a855f7" strokeWidth={3} name="Retention Rate" />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </TabsContent>

                <TabsContent value="journeys" className="space-y-6">
                    <div className="rounded-xl border border-border bg-card p-5">
                        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                            <h3 className="text-lg font-semibold text-foreground">Retention Journeys</h3>
                            <Badge variant="secondary" className="w-fit bg-primary/10 text-primary">
                                {journeysSafe.length} active journeys
                            </Badge>
                        </div>
                        <div className="space-y-3">
                            {journeysSafe.map((journey) => (
                                <div key={journey.id} className="rounded-lg border border-border bg-secondary/30 p-4">
                                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                        <div>
                                            <div className="flex flex-wrap items-center gap-2">
                                                <h4 className="font-semibold text-foreground">{journey.name}</h4>
                                                <Badge
                                                    className={
                                                        journey.status === "active"
                                                            ? "bg-emerald-500/20 text-emerald-400"
                                                            : "bg-amber-500/20 text-amber-400"
                                                    }
                                                >
                                                    {journey.status}
                                                </Badge>
                                            </div>
                                            <p className="text-sm text-muted-foreground">{journey.audience}</p>
                                            <p className="text-xs text-muted-foreground">Offer: {journey.offer}</p>
                                        </div>
                                        <div className="flex flex-wrap items-center gap-6 text-sm">
                                            <div>
                                                <p className="text-xs text-muted-foreground">Conversion</p>
                                                <p className="font-semibold text-foreground">{journey.conversion}</p>
                                            </div>
                                            <div>
                                                <p className="text-xs text-muted-foreground">Saved</p>
                                                <p className="font-semibold text-foreground">{journey.saved}</p>
                                            </div>
                                            <div>
                                                <p className="text-xs text-muted-foreground">Updated</p>
                                                <p className="font-semibold text-foreground">{journey.lastUpdated}</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </TabsContent>

                <TabsContent value="events" className="space-y-6">
                    <div className="rounded-xl border border-border bg-card p-5">
                        <h3 className="mb-4 text-lg font-semibold text-foreground">Retention Events</h3>
                        <div className="space-y-3">
                            {eventsSafe.map((event) => (
                                <div key={event.id} className="rounded-lg border border-border bg-secondary/30 p-3">
                                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                        <div>
                                            <p className="text-sm font-semibold text-foreground">{event.type}</p>
                                            <p className="text-xs text-muted-foreground">
                                                {event.account} - {event.customer} - {event.channel}
                                            </p>
                                        </div>
                                        <div className="flex items-center gap-3 text-xs text-muted-foreground">
                                            <Badge variant="secondary" className="bg-secondary text-foreground">
                                                {event.outcome}
                                            </Badge>
                                            <span>{event.time}</span>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </TabsContent>

                <TabsContent value="watchlist" className="space-y-6">
                    <div className="rounded-xl border border-border bg-card p-5">
                        <h3 className="mb-4 text-lg font-semibold text-foreground">Watchlist</h3>
                        <div className="space-y-3">
                            {watchlistSafe.map((item) => (
                                <div key={item.id} className="rounded-lg border border-border bg-secondary/30 p-3">
                                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                        <div>
                                            <p className="text-sm font-semibold text-foreground">{item.customer}</p>
                                            <p className="text-xs text-muted-foreground">
                                                {item.account} - {item.segment}
                                            </p>
                                            <p className="text-xs text-muted-foreground">Trigger: {item.trigger}</p>
                                        </div>
                                        <div className="flex items-center gap-3 text-xs">
                                            <Badge className="bg-amber-500/20 text-amber-400">{item.riskScore}</Badge>
                                            <Badge variant="secondary" className="bg-secondary text-foreground">
                                                {item.status}
                                            </Badge>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </TabsContent>
            </Tabs>
</ModuleLayout>
    )
}
