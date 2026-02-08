"use client"

import { StatCard } from "@/components/dashboard/stat-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { ActivityFeed } from "@/components/dashboard/activity-feed"
import { QuickStats } from "@/components/dashboard/quick-stats"
import { TicketsTable } from "@/components/dashboard/tickets-table"
import {
  DollarSign,
  Users,
  Headset,
  Wifi,
  Phone,
  Megaphone,
  ShieldCheck,
  UserCog,
  TrendingUp,
  Ticket,
  Activity,
} from "lucide-react"
import { useModuleData } from "@/lib/module-data"

const defaultModuleCards = [
  {
    title: "Sales",
    description: "Track deals, manage pipeline and forecast revenue",
    iconKey: "sales",
    stats: [
      { label: "Monthly Revenue", value: "$284K" },
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
]

const defaultDashboardStats = [
  {
    id: "revenue",
    title: "Total Revenue",
    value: "R22.5M",
    change: "+12.5%",
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
    description: "this month",
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
    <>
      {/* Stats Grid */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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

      {/* Charts and Activity */}
      <div className="mb-6 grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <QuickStats />
        </div>
        <ActivityFeed />
      </div>

      {/* Tickets Table */}
      <div className="mb-6">
        <TicketsTable />
      </div>

      {/* Modules Grid */}
      <div className="mb-6">
        <h2 className="mb-4 text-lg font-semibold text-foreground">Platform Modules</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {modulesWithIcons.map((module) => (
            <ModuleCard key={module.title} {...module} />
          ))}
        </div>
      </div>
    </>
  )
}
