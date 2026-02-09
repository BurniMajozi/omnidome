"use client"

import React from "react"
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
    LineChart,
    RadarChart,
    Radar,
    PolarGrid,
    PolarAngleAxis,
    PolarRadiusAxis,
} from "recharts"
import { BarChart3, TrendingUp, Brain, Activity } from "lucide-react"
import { useModuleData } from "@/lib/module-data"

// Revenue trend data
const defaultRevenueTrendData = [
    { month: "Jul", revenue: 2840000, arpu: 412, subscribers: 6893 },
    { month: "Aug", revenue: 3010000, arpu: 418, subscribers: 7201 },
    { month: "Sep", revenue: 3180000, arpu: 425, subscribers: 7482 },
    { month: "Oct", revenue: 3350000, arpu: 431, subscribers: 7770 },
    { month: "Nov", revenue: 3520000, arpu: 438, subscribers: 8036 },
    { month: "Dec", revenue: 3690000, arpu: 445, subscribers: 8292 },
]

// Usage-to-billing sync data
const defaultUsageBillingData = [
    { name: "Synced", value: 450, fill: "#4ade80" },
    { name: "Variance Detected", value: 12, fill: "#f97316" },
    { name: "Orphaned Accounts", value: 3, fill: "#ef4444" },
]

// Module performance scores
const defaultModulePerformanceData = [
    { module: "Sales", score: 92, target: 85 },
    { module: "CRM", score: 88, target: 80 },
    { module: "Support", score: 76, target: 80 },
    { module: "Network", score: 95, target: 90 },
    { module: "Billing", score: 91, target: 85 },
    { module: "Retention", score: 84, target: 80 },
]

// Customer segment breakdown
const defaultSegmentData = [
    { segment: "Enterprise", count: 342, revenue: 16600000, arpu: 48538 },
    { segment: "Business", count: 1245, revenue: 30870000, arpu: 24795 },
    { segment: "Premium Residential", count: 2890, revenue: 35838000, arpu: 12401 },
    { segment: "Standard Residential", count: 3815, revenue: 23653000, arpu: 6200 },
]

// AI insight categories
const defaultInsightBreakdown = [
    { category: "Churn Risk", count: 847, actionable: 612 },
    { category: "Upsell Opportunity", count: 1234, actionable: 890 },
    { category: "Network Alert", count: 156, actionable: 142 },
    { category: "Billing Anomaly", count: 89, actionable: 67 },
    { category: "Usage Spike", count: 234, actionable: 198 },
]

// Radar data for module health
const defaultRadarData = [
    { subject: "Sales", A: 92 },
    { subject: "CRM", A: 88 },
    { subject: "Support", A: 76 },
    { subject: "Network", A: 95 },
    { subject: "Billing", A: 91 },
    { subject: "Retention", A: 84 },
    { subject: "Call Center", A: 79 },
    { subject: "Marketing", A: 82 },
]

const formatCurrency = (value: number) => `R ${value.toLocaleString("en-ZA")}`

const defaultFlashcardKPIs = [
    {
        id: "1",
        title: "Monthly Revenue",
        value: formatCurrency(3690000),
        change: "+12.4%",
        changeType: "positive" as const,
        iconKey: "revenue",
        backTitle: "Revenue Breakdown",
        backDetails: [
            { label: "Subscriptions", value: formatCurrency(2890000) },
            { label: "VAS Revenue", value: formatCurrency(540000) },
            { label: "Installation Fees", value: formatCurrency(260000) },
        ],
        backInsight: "Revenue growth trending 18% above forecast",
    },
    {
        id: "2",
        title: "Active Subscribers",
        value: "8,292",
        change: "+3.2%",
        changeType: "positive" as const,
        iconKey: "subscribers",
        backTitle: "Subscriber Mix",
        backDetails: [
            { label: "Enterprise", value: "342" },
            { label: "Business", value: "1,245" },
            { label: "Residential", value: "6,705" },
        ],
        backInsight: "Enterprise segment growing fastest at 8% MoM",
    },
    {
        id: "3",
        title: "AI Insights Generated",
        value: "2,560",
        change: "+24%",
        changeType: "positive" as const,
        iconKey: "insights",
        backTitle: "Insight Categories",
        backDetails: [
            { label: "Churn Predictions", value: "847" },
            { label: "Upsell Signals", value: "1,234" },
            { label: "Anomaly Alerts", value: "479" },
        ],
        backInsight: "74% of insights actioned within 24h",
    },
    {
        id: "4",
        title: "ARPU",
        value: formatCurrency(445),
        change: "+5.1%",
        changeType: "positive" as const,
        iconKey: "arpu",
        backTitle: "ARPU by Segment",
        backDetails: [
            { label: "Enterprise", value: formatCurrency(48538) },
            { label: "Business", value: formatCurrency(24795) },
            { label: "Residential", value: formatCurrency(5289) },
        ],
        backInsight: "VAS attach rate driving ARPU growth",
    },
]

const analyticsKpiIconMap: Record<string, React.ReactNode> = {
    revenue: <TrendingUp className="h-5 w-5 text-emerald-400" />,
    subscribers: <Activity className="h-5 w-5 text-blue-400" />,
    insights: <Brain className="h-5 w-5 text-violet-400" />,
    arpu: <BarChart3 className="h-5 w-5 text-amber-400" />,
}

const defaultActivities = [
    {
        id: "1",
        user: "AI Engine",
        action: "generated executive summary for",
        target: "December 2025",
        time: "5 minutes ago",
        type: "create" as const,
    },
    {
        id: "2",
        user: "System",
        action: "synced usage-to-billing data for",
        target: "450 accounts",
        time: "15 minutes ago",
        type: "update" as const,
    },
    {
        id: "3",
        user: "Thandi Molefe",
        action: "exported revenue report for",
        target: "Q4 2025",
        time: "1 hour ago",
        type: "create" as const,
    },
    {
        id: "4",
        user: "AI Engine",
        action: "detected billing anomaly for",
        target: "ACC-34521",
        time: "2 hours ago",
        type: "assign" as const,
    },
    {
        id: "5",
        user: "Sipho Dlamini",
        action: "scheduled automated report for",
        target: "Board Meeting",
        time: "3 hours ago",
        type: "update" as const,
    },
]

const defaultIssues = [
    {
        id: "1",
        title: "3 orphaned RADIUS accounts with no CRM subscription",
        severity: "high" as const,
        status: "open" as const,
        assignee: "Billing Team",
        time: "Active",
    },
    {
        id: "2",
        title: "Usage variance of 2.5% detected in billing sync",
        severity: "medium" as const,
        status: "in-progress" as const,
        assignee: "Finance Team",
        time: "4 hours ago",
    },
    {
        id: "3",
        title: "Report generation timeout for large datasets",
        severity: "low" as const,
        status: "open" as const,
        assignee: "Engineering",
        time: "1 day ago",
    },
]

const defaultTasks = [
    {
        id: "1",
        title: "Review Q4 executive summary before board presentation",
        priority: "urgent" as const,
        status: "in-progress" as const,
        dueDate: "Today",
        assignee: "Thandi Molefe",
    },
    {
        id: "2",
        title: "Reconcile orphaned RADIUS accounts",
        priority: "high" as const,
        status: "todo" as const,
        dueDate: "Tomorrow",
        assignee: "Billing Team",
    },
    {
        id: "3",
        title: "Configure automated weekly report emails",
        priority: "normal" as const,
        status: "todo" as const,
        dueDate: "Next Week",
        assignee: "Sipho Dlamini",
    },
    {
        id: "4",
        title: "Set up custom dashboards for regional managers",
        priority: "normal" as const,
        status: "done" as const,
        dueDate: "Completed",
        assignee: "Engineering",
    },
]

const defaultAIRecommendations = [
    {
        id: "1",
        title: "Launch 'Power User' upsell campaign",
        description: "Top 5% of users by bandwidth consumption identified. Potential R 180K/month in additional revenue.",
        impact: "high" as const,
        category: "Revenue",
    },
    {
        id: "2",
        title: "Proactive maintenance for Cape Town region",
        description: "Signal degradation patterns detected for 15 ONTs in Site B. Dispatch before customer impact.",
        impact: "high" as const,
        category: "Operations",
    },
    {
        id: "3",
        title: "Optimize billing cycle timing",
        description: "Analysis shows 12% fewer failed debits when billing runs on the 25th vs 1st of month.",
        impact: "medium" as const,
        category: "Billing",
    },
    {
        id: "4",
        title: "Cross-sell security VAS bundle",
        description: "High sell-through for smart cameras suggests opportunity for Security VAS bundle.",
        impact: "medium" as const,
        category: "Product",
    },
]

const defaultTableData = [
    { id: "1", metric: "Monthly Recurring Revenue", current: "R 3,690,000", previous: "R 3,520,000", change: "+4.8%", status: "Above Target" },
    { id: "2", metric: "Average Revenue Per User", current: "R 445", previous: "R 438", change: "+1.6%", status: "On Target" },
    { id: "3", metric: "Customer Acquisition Cost", current: "R 1,240", previous: "R 1,380", change: "-10.1%", status: "Above Target" },
    { id: "4", metric: "Customer Lifetime Value", current: "R 18,400", previous: "R 17,200", change: "+7.0%", status: "Above Target" },
    { id: "5", metric: "Net Promoter Score", current: "72", previous: "68", change: "+5.9%", status: "On Target" },
    { id: "6", metric: "First Call Resolution", current: "84.2%", previous: "81.5%", change: "+3.3%", status: "Above Target" },
    { id: "7", metric: "Network Uptime", current: "99.97%", previous: "99.94%", change: "+0.03%", status: "Above Target" },
    { id: "8", metric: "Churn Rate", current: "2.1%", previous: "2.4%", change: "-12.5%", status: "Above Target" },
]

const tableColumns = [
    { key: "metric", label: "KPI Metric" },
    { key: "current", label: "Current" },
    { key: "previous", label: "Previous" },
    { key: "change", label: "Change" },
    { key: "status", label: "Status" },
]

const COLORS = ["#4ade80", "#f97316", "#ef4444"]

export function AnalyticsModule() {
    const { data } = useModuleData("analytics", {
        flashcardKPIs: defaultFlashcardKPIs,
        activities: defaultActivities,
        issues: defaultIssues,
        tasks: defaultTasks,
        aiRecommendations: defaultAIRecommendations,
        tableData: defaultTableData,
    })

    const flashcardKPIs = (data.flashcardKPIs ?? defaultFlashcardKPIs).map(
        (kpi: (typeof defaultFlashcardKPIs)[number]) => ({
            ...kpi,
            icon: analyticsKpiIconMap[kpi.iconKey] || <BarChart3 className="h-5 w-5 text-primary" />,
        }),
    )

    return (
        <ModuleLayout
            title="Analytics & AI Insights"
            flashcardKPIs={flashcardKPIs}
            activities={data.activities ?? defaultActivities}
            issues={data.issues ?? defaultIssues}
            summary="AI analytics engine processed 2,560 insights this month with 74% actioned within 24 hours. Revenue is trending 18% above forecast driven by VAS attach rate improvements. Usage-to-billing sync shows 97.5% accuracy with 3 orphaned RADIUS accounts flagged for review. Proactive health monitoring has improved FCR by 15% as technicians are dispatched before customers call."
            tasks={data.tasks ?? defaultTasks}
            aiRecommendations={data.aiRecommendations ?? defaultAIRecommendations}
            tableData={data.tableData ?? defaultTableData}
            tableColumns={tableColumns}
        >
            <div className="grid gap-6 lg:grid-cols-2">
                {/* Revenue & Subscriber Trend */}
                <div className="rounded-xl border border-border bg-card p-6">
                    <h4 className="mb-4 text-sm font-semibold text-foreground">Revenue & Subscriber Growth</h4>
                    <ResponsiveContainer width="100%" height={300}>
                        <AreaChart data={defaultRevenueTrendData}>
                            <defs>
                                <linearGradient id="colorRevenue" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#4ade80" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#4ade80" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                            <XAxis dataKey="month" stroke="#888" fontSize={12} />
                            <YAxis stroke="#888" fontSize={12} tickFormatter={(v) => `R${(v / 1000000).toFixed(1)}M`} />
                            <Tooltip
                                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                                formatter={(value: number, name: string) => [
                                    name === "revenue" ? formatCurrency(value) : value.toLocaleString(),
                                    name === "revenue" ? "Revenue" : "Subscribers",
                                ]}
                            />
                            <Legend />
                            <Area type="monotone" dataKey="revenue" stroke="#4ade80" fillOpacity={1} fill="url(#colorRevenue)" name="Revenue" />
                            <Line type="monotone" dataKey="subscribers" stroke="#60a5fa" strokeWidth={2} dot={false} name="Subscribers" />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>

                {/* Module Health Radar */}
                <div className="rounded-xl border border-border bg-card p-6">
                    <h4 className="mb-4 text-sm font-semibold text-foreground">Module Health Scores</h4>
                    <ResponsiveContainer width="100%" height={300}>
                        <RadarChart data={defaultRadarData}>
                            <PolarGrid stroke="rgba(255,255,255,0.1)" />
                            <PolarAngleAxis dataKey="subject" stroke="#888" fontSize={12} />
                            <PolarRadiusAxis stroke="#888" fontSize={10} domain={[0, 100]} />
                            <Radar name="Score" dataKey="A" stroke="#a855f7" fill="#a855f7" fillOpacity={0.3} />
                        </RadarChart>
                    </ResponsiveContainer>
                </div>

                {/* Usage-to-Billing Sync */}
                <div className="rounded-xl border border-border bg-card p-6">
                    <h4 className="mb-4 text-sm font-semibold text-foreground">Usage-to-Billing Sync Status</h4>
                    <ResponsiveContainer width="100%" height={300}>
                        <PieChart>
                            <Pie
                                data={defaultUsageBillingData}
                                cx="50%"
                                cy="50%"
                                innerRadius={60}
                                outerRadius={100}
                                paddingAngle={5}
                                dataKey="value"
                                label={({ name, value }) => `${name}: ${value}`}
                            >
                                {defaultUsageBillingData.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                ))}
                            </Pie>
                            <Tooltip
                                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                            />
                        </PieChart>
                    </ResponsiveContainer>
                </div>

                {/* AI Insight Categories */}
                <div className="rounded-xl border border-border bg-card p-6">
                    <h4 className="mb-4 text-sm font-semibold text-foreground">AI Insight Categories</h4>
                    <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={defaultInsightBreakdown} layout="vertical">
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                            <XAxis type="number" stroke="#888" fontSize={12} />
                            <YAxis dataKey="category" type="category" stroke="#888" fontSize={11} width={120} />
                            <Tooltip
                                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                            />
                            <Legend />
                            <Bar dataKey="count" fill="#60a5fa" name="Total" radius={[0, 4, 4, 0]} />
                            <Bar dataKey="actionable" fill="#4ade80" name="Actioned" radius={[0, 4, 4, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </ModuleLayout>
    )
}
