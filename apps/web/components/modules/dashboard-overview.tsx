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

const modules = [
  {
    title: "Sales",
    description: "Track deals, manage pipeline and forecast revenue",
    icon: DollarSign,
    stats: [
      { label: "Monthly Revenue", value: "$284K" },
      { label: "New Deals", value: "47" },
    ],
    features: ["Lead tracking", "Quote generation", "Commission reports"],
  },
  {
    title: "CRM",
    description: "Manage customer relationships and interactions",
    icon: Users,
    stats: [
      { label: "Total Customers", value: "12,847" },
      { label: "Active Leads", value: "342" },
    ],
    features: ["Contact management", "Customer timeline", "Segmentation"],
  },
  {
    title: "Service",
    description: "Handle support tickets and service requests",
    icon: Headset,
    stats: [
      { label: "Open Tickets", value: "128" },
      { label: "Avg Resolution", value: "4.2h" },
    ],
    features: ["Ticket queue", "SLA tracking", "Knowledge base"],
  },
  {
    title: "Network",
    description: "Monitor infrastructure and network performance",
    icon: Wifi,
    stats: [
      { label: "Uptime", value: "99.97%" },
      { label: "Active Nodes", value: "1,247" },
    ],
    features: ["Real-time monitoring", "Outage alerts", "Capacity planning"],
  },
  {
    title: "Call Center",
    description: "Manage inbound and outbound call operations",
    icon: Phone,
    stats: [
      { label: "Calls Today", value: "1,847" },
      { label: "Avg Wait Time", value: "42s" },
    ],
    features: ["Call routing", "Agent performance", "Call recording"],
  },
  {
    title: "Marketing",
    description: "Run campaigns and track marketing performance",
    icon: Megaphone,
    stats: [
      { label: "Active Campaigns", value: "12" },
      { label: "Conversion Rate", value: "3.2%" },
    ],
    features: ["Email campaigns", "Analytics", "A/B testing"],
  },
  {
    title: "Compliance",
    description: "Ensure regulatory compliance and data security",
    icon: ShieldCheck,
    stats: [
      { label: "Compliance Score", value: "94%" },
      { label: "Open Issues", value: "7" },
    ],
    features: ["Audit trails", "Policy management", "Risk assessment"],
  },
  {
    title: "Talent",
    description: "Manage HR, recruitment and employee performance",
    icon: UserCog,
    stats: [
      { label: "Total Employees", value: "248" },
      { label: "Open Positions", value: "14" },
    ],
    features: ["Recruitment", "Performance reviews", "Training"],
  },
]

export function DashboardOverview() {
  return (
    <>
      {/* Stats Grid */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Revenue"
          value="$1.24M"
          change="+12.5%"
          changeType="positive"
          icon={TrendingUp}
          description="vs last month"
        />
        <StatCard
          title="Active Subscribers"
          value="24,847"
          change="+8.2%"
          changeType="positive"
          icon={Users}
          description="vs last month"
        />
        <StatCard
          title="Open Tickets"
          value="128"
          change="-24%"
          changeType="positive"
          icon={Ticket}
          description="vs last week"
        />
        <StatCard
          title="Network Uptime"
          value="99.97%"
          change="+0.02%"
          changeType="positive"
          icon={Activity}
          description="this month"
        />
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
          {modules.map((module) => (
            <ModuleCard key={module.title} {...module} />
          ))}
        </div>
      </div>
    </>
  )
}
