"use client"

import { useCallback, useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { PageHeader } from "@/components/ui/page-header"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Globe,
  Smartphone,
  Bot,
  Layout,
  Wrench,
  Users,
  Settings,
  Eye,
  TrendingUp,
  Activity,
  MapPin,
  Plus,
  MoreVertical,
  Play,
  Pause,
  Sparkles,
  Monitor,
  Search,
} from "lucide-react"
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { WebAnalyticsDashboard } from "./web-analytics/web-analytics-dashboard"
import { JourneyBuilderDashboard } from "./journey-builder/journey-builder-dashboard"
import { WebAnalyticsCustomDashboard } from "@/modules/web-analytics-custom"
import { CancelFlowModal } from "./cancel-flow-modal"
import { JourneyABTesting } from "./journey-ab-testing"
import { AB_TESTING_ENABLED } from "@/lib/flags"
import { CommissionTiers } from "./commission-tiers"
import { FieldSalesApp } from "./field-sales-app"
import { TechnicianApp } from "./technician-app"
import { DomeStudioLiveDualView } from "./portal/domestudio-workspace"
import { DomeDesignStudio } from "./portal/domedesign-studio"
import { DomeSeoStudio } from "./portal/domeseo-studio"
import { PortalOperations } from "./portal/portal-operations"
import { NotConnected } from "@/components/ui/not-connected"
import {
  loadPortalPages,
  loadPortalAnalytics,
  type PortalAnalyticsSummary,
  type PortalPageSummary,
} from "@/lib/portal-api"
import type { Loadable } from "@/lib/service-state"

export function PortalModule({ activeTabOverride }: { activeTabOverride?: string }) {
  const [pages, setPages] = useState<Loadable<PortalPageSummary[]>>({ state: "loading" })
  const [analytics, setAnalytics] = useState<Loadable<PortalAnalyticsSummary>>({ state: "loading" })
  const [newPageSignal, setNewPageSignal] = useState(0)

  const reload = useCallback(async () => {
    const [p, a] = await Promise.all([loadPortalPages({ pageSize: 100 }), loadPortalAnalytics(30)])
    setPages(p.state === "ready" ? { state: "ready", data: p.data.items } : p)
    setAnalytics(a)
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const startNewPage = () => {
    setActiveTab("website")
    setNewPageSignal((n) => n + 1)
  }

  const [activeTab, setActiveTab] = useState("overview")
  const [cancelFlowOpen, setCancelFlowOpen] = useState(false)

  useEffect(() => {
    if (!activeTabOverride) return
    setActiveTab(activeTabOverride)
  }, [activeTabOverride])

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Globe className="h-5 w-5" />}
        title={activeTab === "website" ? "Website Builder" : "Customer Portal"}
        subtitle={activeTab === "website" ? "Create a landing page in chat, refine the design, then publish." : "Self-service portal, journey management, and customer engagement"}
        actions={
          <Button size="sm" onClick={startNewPage} className="bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold text-xs">
            <Plus className="h-3.5 w-3.5 mr-1" />
            New Page
          </Button>
        }
      />

      {/* KPI Cards (last 30 days, from Portal Builder analytics) */}
      <div className={`grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4 ${activeTab === "website" ? "hidden" : ""}`}>
        {analytics.state !== "ready" ? (
          <div className="md:col-span-2 lg:col-span-4">
            <NotConnected loadable={analytics} service="Portal Builder analytics" onRetry={() => void reload()} />
          </div>
        ) : (
          [
            { label: "Page views", value: analytics.data.views.toLocaleString(), sub: `${analytics.data.unique_visitors.toLocaleString()} unique visitors`, Icon: Eye, tile: "bg-emerald-500/20", icon: "text-emerald-400" },
            { label: "Form submissions", value: analytics.data.submissions.toLocaleString(), sub: `${analytics.data.conversion_rate}% conversion`, Icon: Activity, tile: "bg-blue-500/20", icon: "text-blue-400" },
            { label: "Published pages", value: String(analytics.data.pages.published), sub: `${analytics.data.pages.draft} drafts, ${analytics.data.pages.archived} archived`, Icon: Layout, tile: "bg-amber-500/20", icon: "text-amber-400" },
            { label: "Campaigns running", value: String(analytics.data.campaigns.running), sub: `${analytics.data.campaigns.total} total`, Icon: TrendingUp, tile: "bg-purple-500/20", icon: "text-purple-400" },
          ].map(({ label, value, sub, Icon, tile, icon }) => (
            <Card key={label} className="border-border bg-card">
              <CardContent className="p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">{label}</p>
                    <p className="mt-1 text-2xl font-bold text-foreground">{value}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{sub}</p>
                  </div>
                  <div className={`rounded-lg ${tile} p-2`}>
                    <Icon className={`h-5 w-5 ${icon}`} />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Main Content */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="h-auto w-full flex-wrap justify-start gap-1 overflow-visible bg-secondary sm:w-full sm:justify-start [&>button]:h-9 [&>button]:flex-none">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="website">Website Builder</TabsTrigger>
          <TabsTrigger value="analytics-custom" className="flex items-center gap-1.5">
            <Monitor className="h-3.5 w-3.5" />
            Live Dual-View
          </TabsTrigger>
          <TabsTrigger value="domeseo" className="flex items-center gap-1.5">
            <Search className="h-3.5 w-3.5 text-cyan-400" />
            DomeSEO
          </TabsTrigger>
          <TabsTrigger value="web-analytics">Website Analytics</TabsTrigger>
          <TabsTrigger value="journeys">Retention Journeys</TabsTrigger>
          <TabsTrigger value="ai-apps">AI Apps</TabsTrigger>
          {AB_TESTING_ENABLED && <TabsTrigger value="ab-testing">A/B Testing</TabsTrigger>}
          <TabsTrigger value="field-sales">Field Sales App</TabsTrigger>
          <TabsTrigger value="technician">Technician App</TabsTrigger>
          <TabsTrigger value="commissions">Commissions</TabsTrigger>
          <TabsTrigger value="operations">Campaigns & records</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <div id="portal-overview" />
          {analytics.state !== "ready" ? (
            <NotConnected loadable={analytics} service="Portal Builder analytics" onRetry={() => void reload()} />
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <Card className="border-border bg-card">
                <CardHeader>
                  <CardTitle className="text-base">Views and submissions, last {analytics.data.period_days} days</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={analytics.data.daily}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis dataKey="date" stroke="#9ca3af" fontSize={12} />
                        <YAxis stroke="#9ca3af" fontSize={12} allowDecimals={false} />
                        <Tooltip contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }} />
                        <Area type="monotone" dataKey="views" stroke="#10b981" fill="#10b981" fillOpacity={0.3} name="Views" />
                        <Area type="monotone" dataKey="submissions" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} name="Submissions" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-border bg-card">
                <CardHeader>
                  <CardTitle className="text-base">Top pages and sources</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4 text-sm">
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Top pages</p>
                    {analytics.data.top_pages.length === 0 ? (
                      <p className="text-xs text-muted-foreground">No views recorded yet.</p>
                    ) : (
                      <ul className="space-y-1.5">
                        {analytics.data.top_pages.map((p) => (
                          <li key={p.page_id} className="flex justify-between gap-2">
                            <span className="truncate text-foreground">{p.title}</span>
                            <span className="text-muted-foreground">{p.views.toLocaleString()}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Top sources</p>
                    {analytics.data.top_sources.length === 0 ? (
                      <p className="text-xs text-muted-foreground">No traffic sources recorded yet.</p>
                    ) : (
                      <ul className="space-y-1.5">
                        {analytics.data.top_sources.map((src) => (
                          <li key={src.source} className="flex justify-between gap-2">
                            <span className="truncate text-foreground">{src.source}</span>
                            <span className="text-muted-foreground">{src.views.toLocaleString()}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        <TabsContent forceMount value="website" className="mt-4 space-y-5 data-[state=inactive]:hidden">
          <div id="portal-landing" />
          <DomeDesignStudio pages={pages} onChanged={() => void reload()} onReload={() => void reload()} newPageSignal={newPageSignal} />
        </TabsContent>

        <TabsContent value="analytics-custom" className="mt-4">
          <DomeStudioLiveDualView pages={pages} onReload={() => void reload()} />
        </TabsContent>

        <TabsContent value="domeseo" className="mt-4">
          <DomeSeoStudio />
        </TabsContent>

        <TabsContent value="web-analytics" className="mt-4">
          <WebAnalyticsDashboard />
        </TabsContent>

        <TabsContent value="journeys" className="mt-4">
          <JourneyBuilderDashboard />
        </TabsContent>

        <TabsContent value="ai-apps" className="mt-4 space-y-4">
          <div id="portal-ai-apps" />
          <div
            role="status"
            className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-secondary/20 p-8 text-center"
          >
            <Bot className="h-6 w-6 text-muted-foreground" />
            <p className="text-sm font-medium text-foreground">Portal AI agents are not connected</p>
            <p className="max-w-md text-xs text-muted-foreground">
              Portal Builder has no AI agent or chatbot endpoint, so no agents, conversation counts or resolution rates are shown here.
            </p>
          </div>
        </TabsContent>

        {/* A/B Testing is mock-only (no backend) — feature-flagged off for v1. */}
        {AB_TESTING_ENABLED && (
          <TabsContent value="ab-testing" className="mt-4">
            <JourneyABTesting />
          </TabsContent>
        )}

        <TabsContent value="field-sales" className="mt-4">
          <FieldSalesApp />
        </TabsContent>

        <TabsContent value="technician" className="mt-4">
          <TechnicianApp />
        </TabsContent>

        <TabsContent value="commissions" className="mt-4">
          <CommissionTiers />
        </TabsContent>
        <TabsContent value="operations" className="mt-4"><PortalOperations /></TabsContent>
      </Tabs>

      {/* Cancel Flow Modal */}
      <CancelFlowModal
        open={cancelFlowOpen}
        onOpenChange={setCancelFlowOpen}
      />

    </div>
  )
}
