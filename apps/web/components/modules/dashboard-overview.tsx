"use client"

import { StatCard } from "@/components/dashboard/stat-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { ActivityFeed } from "@/components/dashboard/activity-feed"
import { QuickStats } from "@/components/dashboard/quick-stats"
import { TicketsTable } from "@/components/dashboard/tickets-table"
import { ExecutiveApprovalQueue } from "@/components/dashboard/executive-approval-queue"
import {
  DollarSign,
  Users,
  Headset,
  Wifi,
  Phone,
  Megaphone,
  ShieldCheck,
  UserCog,
  FileText,
  TrendingUp,
  Ticket,
  Activity,
  Briefcase,
  ArrowRight,
  Sparkles,
  Zap,
} from "lucide-react"
import { useModuleData } from "@/lib/module-data"

const defaultModuleCards = [
  {
    title: "Sales",
    description: "Track deals, manage pipeline and forecast revenue",
    iconKey: "sales",
    stats: [
      { label: "Monthly Revenue", value: "R2.84M" },
      { label: "New Deals", value: "47" },
    ],
    features: ["Lead tracking", "Quote generation", "Commission reports"],
  },
  {
    title: "CRM",
    description: "Manage customer relationships and interactions",
    iconKey: "crm",
    stats: [
      { label: "Total Customers", value: "12,847" },
      { label: "Active Leads", value: "342" },
    ],
    features: ["Contact management", "Customer timeline", "Segmentation"],
  },
  {
    title: "Service",
    description: "Handle support tickets and service requests",
    iconKey: "service",
    stats: [
      { label: "Open Tickets", value: "128" },
      { label: "Avg Resolution", value: "4.2h" },
    ],
    features: ["Ticket queue", "SLA tracking", "Knowledge base"],
  },
  {
    title: "Network",
    description: "Monitor infrastructure and network performance",
    iconKey: "network",
    stats: [
      { label: "Uptime", value: "99.97%" },
      { label: "Active Nodes", value: "1,247" },
    ],
    features: ["Real-time monitoring", "Outage alerts", "Capacity planning"],
  },
  {
    title: "Call Center",
    description: "Manage inbound and outbound call operations",
    iconKey: "call-center",
    stats: [
      { label: "Calls Today", value: "1,847" },
      { label: "Avg Wait Time", value: "42s" },
    ],
    features: ["Call routing", "Agent performance", "Call recording"],
  },
  {
    title: "Marketing",
    description: "Run campaigns and track marketing performance",
    iconKey: "marketing",
    stats: [
      { label: "Active Campaigns", value: "12" },
      { label: "Conversion Rate", value: "3.2%" },
    ],
    features: ["Email campaigns", "Analytics", "A/B testing"],
  },
  {
    title: "Compliance",
    description: "Ensure regulatory compliance and data security",
    iconKey: "compliance",
    stats: [
      { label: "Compliance Score", value: "94%" },
      { label: "Open Issues", value: "7" },
    ],
    features: ["Audit trails", "Policy management", "Risk assessment"],
  },
  {
    title: "Talent",
    description: "Manage HR, recruitment and employee performance",
    iconKey: "talent",
    stats: [
      { label: "Total Employees", value: "248" },
      { label: "Open Positions", value: "14" },
    ],
    features: ["Recruitment", "Performance reviews", "Training"],
  },
  {
    title: "Finance",
    description: "GAAP reporting, revenue recognition, and FP&A",
    iconKey: "finance",
    stats: [
      { label: "EBITA Margin", value: "38.5%" },
      { label: "Cash Runway", value: "14 months" },
    ],
    features: ["Statements", "Scenario planning", "Expense controls"],
  },
]

const defaultDashboardStats = [
  {
    id: "revenue",
    title: "Total Revenue (ARR/MRR)",
    value: "R22.5M",
    change: "+18.5%",
    changeType: "positive" as const,
    iconKey: "revenue",
    description: "vs last month",
  },
  {
    id: "subscribers",
    title: "Active Subscribers",
    value: "24,847",
    change: "+8.2%",
    changeType: "positive" as const,
    iconKey: "subscribers",
    description: "vs last month",
  },
  {
    id: "tickets",
    title: "Open Tickets",
    value: "128",
    change: "-24%",
    changeType: "positive" as const,
    iconKey: "tickets",
    description: "vs last week",
  },
  {
    id: "uptime",
    title: "Network Uptime",
    value: "99.97%",
    change: "+0.02%",
    changeType: "positive" as const,
    iconKey: "uptime",
    description: "operational",
  },
]

const recentHighValueDeals = [
  {
    client: "Telkom SA",
    type: "Fiber Backbone Expansion",
    amount: "R 850,000",
    stage: "Closed Won",
    stageColor: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    rep: "John Smith",
  },
  {
    client: "MTN Group",
    type: "Enterprise Bundle (50 Sites)",
    amount: "R 1,200,000",
    stage: "Negotiation",
    stageColor: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    rep: "Sarah Jones",
  },
  {
    client: "Vodacom",
    type: "Primary Data Center Link",
    amount: "R 2,400,000",
    stage: "Proposal Sent",
    stageColor: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    rep: "Mike Brown",
  },
  {
    client: "Dimension Data",
    type: "Managed Cloud Connectivity",
    amount: "R 680,000",
    stage: "Closed Won",
    stageColor: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    rep: "Lisa Chen",
  },
]

const dashboardStatIconMap = {
  revenue: TrendingUp,
  subscribers: Users,
  tickets: Ticket,
  uptime: Activity,
}

const dashboardModuleIconMap = {
  sales: DollarSign,
  crm: Users,
  service: Headset,
  network: Wifi,
  "call-center": Phone,
  marketing: Megaphone,
  compliance: ShieldCheck,
  talent: UserCog,
  finance: FileText,
}

export function DashboardOverview() {
  const { data } = useModuleData("dashboard", {
    stats: defaultDashboardStats,
    modules: defaultModuleCards,
  })

  const statsWithIcons = data.stats.map((stat) => ({
    ...stat,
    icon: dashboardStatIconMap[stat.iconKey as keyof typeof dashboardStatIconMap] ?? TrendingUp,
  }))

  const modulesWithIcons = data.modules.map((module) => ({
    ...module,
    icon: dashboardModuleIconMap[module.iconKey as keyof typeof dashboardModuleIconMap] ?? DollarSign,
  }))

  return (
    <div className="space-y-6">
      {/* ── 1. Top KPI Command Strip ─────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statsWithIcons.map((stat) => (
          <StatCard
            key={stat.id}
            title={stat.title}
            value={stat.value}
            change={stat.change}
            changeType={stat.changeType}
            icon={stat.icon}
            description={stat.description}
          />
        ))}
      </div>

      {/* ── 2. Executive Approval Queue ('Needs You' Review Inbox) ──── */}
      <ExecutiveApprovalQueue />

      {/* ── 3. Hero Sales Graph + Live Activity & Quick Actions (CX Core) ─ */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left 2 Cols: Main Sales Chart & Deal Highlights */}
        <div className="space-y-6 lg:col-span-2">
          {/* Main Sales Performance Chart (Live) */}
          <QuickStats />

          {/* High-Value Deals In Flight (Sales Pipeline Spotlight) */}
          <div className="rounded-xl border border-border bg-card p-5 shadow-xs">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400">
                  <Briefcase className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-foreground">High-Value Deals in Pipeline</h3>
                  <p className="text-xs text-muted-foreground">Top active deal proposals with high close probabilities</p>
                </div>
              </div>
              <span className="text-xs font-semibold text-emerald-400">
                Total R5.13M
              </span>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {recentHighValueDeals.map((deal) => (
                <div
                  key={deal.client}
                  className="group relative flex flex-col justify-between rounded-lg border border-border/80 bg-secondary/20 p-3.5 transition-all hover:border-primary/40 hover:bg-secondary/35"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="space-y-0.5">
                      <span className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                        {deal.client}
                      </span>
                      <p className="text-xs text-muted-foreground line-clamp-1">{deal.type}</p>
                    </div>
                    <span className="text-sm font-bold text-foreground shrink-0">{deal.amount}</span>
                  </div>
                  <div className="mt-3 flex items-center justify-between pt-2 border-t border-border/50 text-xs">
                    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${deal.stageColor}`}>
                      {deal.stage}
                    </span>
                    <span className="text-muted-foreground">Rep: {deal.rep}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right 1 Col: Live Activity Feed & Executive Quick Actions */}
        <div className="space-y-6">
          {/* Executive Quick Actions */}
          <div className="rounded-xl border border-border bg-card p-5 shadow-xs">
            <div className="mb-3 flex items-center gap-2">
              <Zap className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-semibold text-foreground">Executive Quick Actions</h3>
            </div>
            <div className="grid grid-cols-1 gap-2">
              <a
                href="/dashboard/comms"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between rounded-lg border border-border/70 bg-secondary/30 px-3.5 py-2.5 text-xs font-medium text-foreground transition hover:border-primary/50 hover:bg-secondary/60"
              >
                <div className="flex items-center gap-2.5">
                  <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <Sparkles className="h-3.5 w-3.5" />
                  </div>
                  <span>Launch Team Comms Portal</span>
                </div>
                <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
              </a>

              <button
                type="button"
                onClick={() => {
                  window.dispatchEvent(new CustomEvent("open-agent-chat", { detail: { prompt: "Provide a quick summary of this month's revenue and sales forecasts." } }))
                }}
                className="flex items-center justify-between rounded-lg border border-border/70 bg-secondary/30 px-3.5 py-2.5 text-xs font-medium text-foreground transition hover:border-primary/50 hover:bg-secondary/60 cursor-pointer text-left"
              >
                <div className="flex items-center gap-2.5">
                  <div className="flex h-6 w-6 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-400">
                    <DollarSign className="h-3.5 w-3.5" />
                  </div>
                  <span>Ask InsightDome: Forecast</span>
                </div>
                <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
              </button>
            </div>
          </div>

          {/* Activity Feed */}
          <ActivityFeed />
        </div>
      </div>

      {/* ── 3. Operational Support Tickets ───────────────────────────── */}
      <div className="rounded-xl">
        <TicketsTable />
      </div>

      {/* ── 4. Platform Modules Directory ────────────────────────────── */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-foreground">Platform Modules</h2>
            <p className="text-xs text-muted-foreground">Jump directly into specialized telecom operational modules</p>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {modulesWithIcons.map((module) => (
            <ModuleCard key={module.title} {...module} />
          ))}
        </div>
      </div>
    </div>
  )
}
