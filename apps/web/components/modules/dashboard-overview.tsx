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
  Bot,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { tileLabel, type Loadable } from "@/lib/service-state"
import { loadCrmInsights, loadCrmSummary, loadEscalations, loadNetworkDevices } from "@/lib/ops-api"
import {
  CAMPAIGNS_URL,
  CC_QUEUES_URL,
  CC_SESSIONS_URL,
  CRM_INSIGHTS_KEY,
  CRM_SUMMARY_KEY,
  CRM_TOTAL_URL,
  DEALS_URL,
  DEAL_SUMMARY_URL,
  EMPLOYEES_URL,
  ESCALATIONS_KEY,
  NETWORK_DEVICES_KEY,
  STAGES_URL,
  loadCcQueues,
  loadCcSessions,
  loadCrmCustomerTotal,
  loadOverviewCampaigns,
  loadOverviewDealSummary,
  loadOverviewDeals,
  loadOverviewEmployees,
  loadOverviewStageOrder,
  useSharedOps,
} from "@/lib/overview-api"
import {
  OPEN_ESCALATIONS_LABEL,
  buildBriefing,
  buildInsights,
  countStatus,
  customerTotalOf,
  fmtZar,
  listOf,
  lowerBound,
  mapLoadable,
  openEscalationCount,
  resolveDealTotals,
  topDeals,
  type DealRow,
} from "@/lib/overview-derive"
import {
  countText,
  escalationStats,
  fmtInt,
  networkTile,
  partialNote,
  statusCountsFromSummary,
  totalText,
  type EscalationRow,
  type NetworkDeviceRow,
} from "@/lib/ops-derive"
import { avgWaitSeconds, callsToday, formatDuration, unwrapList, type CcQueue, type CcSession } from "@/lib/call-center-metrics"

/** Text for a tile value slot: the figure when ready, an honest state label otherwise. */
function tileText<T>(l: Loadable<T>, fmt: (d: T) => string): string {
  return l.state === "ready" ? fmt(l.data) : (tileLabel(l) ?? "—")
}

const STATIC_MODULES = [
  { title: "Sales", description: "Track deals, manage pipeline and forecast revenue", iconKey: "sales", features: ["Lead tracking", "Quote generation", "Commission reports"] },
  { title: "CRM", description: "Manage customer relationships and interactions", iconKey: "crm", features: ["Contact management", "Customer timeline", "Segmentation"] },
  { title: "Service", description: "Handle support tickets and service requests", iconKey: "service", features: ["Ticket queue", "SLA tracking", "Knowledge base"] },
  { title: "Network", description: "Monitor infrastructure and network performance", iconKey: "network", features: ["Real-time monitoring", "Outage alerts", "Capacity planning"] },
  { title: "Call Center", description: "Manage inbound and outbound call operations", iconKey: "call-center", features: ["Call routing", "Agent performance", "Call recording"] },
  { title: "Marketing", description: "Run campaigns and track marketing performance", iconKey: "marketing", features: ["Email campaigns", "Analytics", "A/B testing"] },
  { title: "Compliance", description: "Ensure regulatory compliance and data security", iconKey: "compliance", features: ["Audit trails", "Policy management", "Risk assessment"] },
  { title: "Talent", description: "Manage HR, recruitment and employee performance", iconKey: "talent", features: ["Recruitment", "Performance reviews", "Training"] },
  { title: "Finance", description: "GAAP reporting, revenue recognition, and FP&A", iconKey: "finance", features: ["Statements", "Scenario planning", "Expense controls"] },
] as const

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
  // Every hook runs unconditionally, in the same order, on every render.
  // useSharedOps: each URL is requested once per page (escalations are also read by
  // TicketsTable, CRM activities by ActivityFeed) and reused for 30s.
  const deals = useSharedOps(DEALS_URL, loadOverviewDeals)
  const dealSummary = useSharedOps(DEAL_SUMMARY_URL, loadOverviewDealSummary)
  const stageOrder = useSharedOps(STAGES_URL, loadOverviewStageOrder)
  const crmTotal = useSharedOps(CRM_TOTAL_URL, loadCrmCustomerTotal)
  const crmSummary = useSharedOps(CRM_SUMMARY_KEY, loadCrmSummary)
  const crmInsights = useSharedOps(CRM_INSIGHTS_KEY, loadCrmInsights)
  const escalations = useSharedOps(ESCALATIONS_KEY, loadEscalations)
  const netDevices = useSharedOps(NETWORK_DEVICES_KEY, loadNetworkDevices)
  const ccSessions = useSharedOps(CC_SESSIONS_URL, loadCcSessions)
  const ccQueues = useSharedOps(CC_QUEUES_URL, loadCcQueues)
  const campaigns = useSharedOps(CAMPAIGNS_URL, loadOverviewCampaigns)
  const employees = useSharedOps(EMPLOYEES_URL, loadOverviewEmployees)

  const dealRows: DealRow[] | null = deals.value.state === "ready" ? deals.value.data.rows : null
  const dealRowsTotal = deals.value.state === "ready" ? deals.value.data.total : null
  const summaryData = dealSummary.value.state === "ready" ? dealSummary.value.data : null
  // Headline deal figures: the server summary when it answers (exact), else the real rows.
  const totals = resolveDealTotals(dealRows, summaryData, dealRowsTotal)
  // Tiles are "ready" as soon as either source answered; otherwise they show the list's state.
  const dealsTile: Loadable<unknown> = totals ? { state: "ready", data: null } : deals.value
  const dealsCut = dealRows !== null && dealRowsTotal !== null && dealRowsTotal > dealRows.length
  const customerTotal: number | null = crmTotal.value.state === "ready" ? customerTotalOf(crmTotal.value.data) : null
  const crmRecs = crmInsights.value.state === "ready" ? (crmInsights.value.data?.aiRecommendations ?? []) : null

  const briefing = buildBriefing(dealRows, customerTotal)
  const suggestions = buildInsights(dealRows, crmRecs)
  const topDealRows = dealRows ? topDeals(dealRows, 4) : []
  const briefingLoading = deals.value.state === "loading" || crmTotal.value.state === "loading"

  const escMeta = escalations.value.state === "ready" ? escalations.value.data : null
  const escStats = escMeta ? escalationStats(escMeta.rows as EscalationRow[]) : null
  const netMeta = netDevices.value.state === "ready" ? netDevices.value.data : null
  const netTile = netMeta ? networkTile(netMeta.rows as NetworkDeviceRow[], netMeta) : null
  const ccNow = new Date()

  const retryDeals = () => {
    deals.reload()
    dealSummary.reload()
  }

  /** Deal figure for a tile: exact from the summary, else from rows with "+" when the list was cut off. */
  const dealsTileText = (fmt: (t: NonNullable<typeof totals>) => string) =>
    tileText(dealsTile, () => (totals ? lowerBound(fmt(totals), totals.partial) : "—"))

  const modules = STATIC_MODULES.map((m) => {
    let stats: { label: string; value: string }[]
    switch (m.iconKey) {
      case "sales":
        stats = [
          { label: "Won Revenue", value: dealsTileText((t) => fmtZar(t.wonValue)) },
          { label: "Open Deals", value: dealsTileText((t) => fmtInt(t.open)) },
        ]
        break
      case "crm":
        stats = [
          { label: "Total Customers", value: tileText(crmTotal.value, (d) => fmtInt(customerTotalOf(d) ?? 0)) },
          {
            label: "Active Customers",
            value: tileText(crmSummary.value, (d) => {
              const c = statusCountsFromSummary(d?.flashcardKPIs)
              return c ? fmtInt(c.active) : "No data yet"
            }),
          },
        ]
        break
      case "service":
        stats = [
          {
            // Same definition as the KPI strip (open + in progress), one helper.
            label: OPEN_ESCALATIONS_LABEL,
            value: tileText(escalations.value, (d) =>
              countText(openEscalationCount(escalationStats(d.rows as EscalationRow[])), d),
            ),
          },
          {
            label: "Avg Resolution",
            value: tileText(escalations.value, (d) => {
              const h = escalationStats(d.rows as EscalationRow[]).avgResolutionHours
              if (h === null) return "No data yet"
              return `${h.toFixed(1)}h${d.loaded < d.total || d.truncated || d.failedPages.length ? " (sample)" : ""}`
            }),
          },
        ]
        break
      case "network":
        stats = [
          {
            label: "Active Devices",
            value: tileText(netDevices.value, (d) => networkTile(d.rows as NetworkDeviceRow[], d).active),
          },
          { label: "Registered Devices", value: tileText(netDevices.value, (d) => totalText(d)) },
        ]
        break
      case "call-center":
        stats = [
          {
            label: "Calls Today",
            value: tileText(ccSessions.value, (d) => fmtInt(callsToday(unwrapList<CcSession>(d, "sessions"), ccNow))),
          },
          {
            label: "Avg Wait Time",
            value: tileText(ccQueues.value, (d) => {
              const w = avgWaitSeconds(unwrapList<CcQueue>(d, "queues"))
              return w === null ? "No data yet" : formatDuration(w)
            }),
          },
        ]
        break
      case "marketing":
        stats = [
          {
            label: "Active Campaigns",
            value: tileText(campaigns.value, (d) => fmtInt(countStatus(listOf<{ status?: string }>(d) ?? [], "active"))),
          },
          { label: "Total Campaigns", value: tileText(campaigns.value, (d) => fmtInt((listOf(d) ?? []).length)) },
        ]
        break
      case "talent":
        stats = [
          { label: "Total Employees", value: tileText(employees.value, (d) => fmtInt((listOf(d) ?? []).length)) },
          {
            label: "Active Employees",
            value: tileText(employees.value, (d) => fmtInt(countStatus(listOf<{ status?: string }>(d) ?? [], "active"))),
          },
        ]
        break
      default:
        // Compliance / Finance: live figures are shown inside their modules.
        stats = [{ label: "Live figures", value: "In module" }]
    }
    return {
      ...m,
      features: [...m.features],
      stats,
      icon: dashboardModuleIconMap[m.iconKey as keyof typeof dashboardModuleIconMap] ?? DollarSign,
    }
  })

  // KPI strip: real values or an honest state. Trend chips are omitted (no history is read).
  const kpis = [
    {
      id: "revenue",
      title: "Won Revenue",
      loadable: dealsTile,
      value: totals ? lowerBound(fmtZar(totals.wonValue), totals.partial) : "",
      description: totals
        ? `${totals.won} won of ${lowerBound(String(totals.count), totals.partial)} deals${totals.partial ? " (first " + fmtInt(dealRows?.length ?? 0) + " loaded)" : ""}`
        : "",
      icon: TrendingUp,
      note: null as string | null,
    },
    {
      id: "subscribers",
      title: "Customers",
      loadable: crmTotal.value as Loadable<unknown>,
      value: customerTotal !== null ? fmtInt(customerTotal) : "",
      description: "from CRM",
      note: null as string | null,
      icon: Users,
    },
    {
      id: "tickets",
      title: `Escalations (${OPEN_ESCALATIONS_LABEL})`,
      loadable: escalations.value as Loadable<unknown>,
      value: escStats && escMeta ? countText(openEscalationCount(escStats), escMeta) : "",
      description: escMeta ? `${totalText(escMeta)} total${partialNote(escMeta) ? " · partial" : ""}` : "",
      note: escMeta ? partialNote(escMeta) : null,
      icon: Ticket,
    },
    {
      id: "uptime",
      title: "Active Network Devices",
      loadable: netDevices.value as Loadable<unknown>,
      value: netTile ? netTile.activeOfRegistered : "",
      description: netTile?.note ? "partial: first page(s) only" : "network service",
      note: netTile ? netTile.note : null,
      icon: Activity,
    },
  ]

  return (
    <div className="space-y-6">
      {/* ── 1. Top KPI Command Strip ─────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((k) => {
          const st = k.loadable.state
          return (
            <StatCard
              key={k.id}
              title={k.title}
              value={st === "ready" ? k.value : (tileLabel(k.loadable) ?? "")}
              change=""
              changeType="neutral"
              icon={k.icon}
              description={st === "ready" ? k.description : undefined}
              note={st === "ready" ? (k.note ?? undefined) : undefined}
              loading={st === "loading"}
              muted={st !== "ready"}
            />
          )
        })}
      </div>

      {/* ── 2. Executive briefing + suggested actions (real data only) ── */}
      <div className="rounded-xl border border-primary/30 bg-gradient-to-r from-primary/10 via-background to-secondary/30 p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl space-y-1.5">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/20 text-primary">
                <Sparkles className="h-4 w-4" />
              </div>
              <h2 className="text-base font-bold text-foreground">Executive Briefing</h2>
              {briefing && (
                <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-emerald-400">
                  From live sales and CRM data
                </span>
              )}
            </div>
            {briefingLoading && !briefing ? (
              <div className="h-4 w-80 max-w-full animate-pulse rounded bg-muted" aria-label="Loading" />
            ) : briefing ? (
              <p className="text-xs font-medium leading-relaxed text-muted-foreground">{briefing}</p>
            ) : (
              <div className="flex items-center gap-3">
                <p className="text-xs font-medium text-muted-foreground">
                  Not connected. The sales and CRM services are not reachable, so no briefing can be produced.
                </p>
                <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => { deals.reload(); crmTotal.reload() }}>
                  Retry
                </Button>
              </div>
            )}
          </div>
          <Button
            size="sm"
            onClick={() => {
              window.dispatchEvent(
                new CustomEvent("open-agent-chat", {
                  detail: {
                    agent: "executive",
                    prompt: "Provide an executive briefing on revenue, deal pipeline stages, and strategic recommendations for this month.",
                  },
                }),
              )
            }}
            className="h-8 shrink-0 gap-1.5 bg-primary text-xs font-semibold text-primary-foreground shadow-xs hover:bg-primary/90"
          >
            <Bot className="h-3.5 w-3.5" />
            Chat with InsightDome
          </Button>
        </div>

        {/* Suggested actions, generated only from real deals / CRM rows */}
        {suggestions.length > 0 && (
          <div className="mt-4 border-t border-border/60 pt-4">
            <div className="mb-2.5 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-foreground">
                <Zap className="h-3.5 w-3.5 text-amber-400" />
                Suggested Actions
              </span>
              <span className="text-[11px] text-muted-foreground">Click to review with an agent</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {suggestions.map((sug) => (
                <button
                  key={sug.id}
                  type="button"
                  onClick={() => {
                    window.dispatchEvent(
                      new CustomEvent("open-agent-chat", {
                        detail: { agent: sug.agentType || "executive", prompt: sug.actionPrompt || sug.description },
                      }),
                    )
                  }}
                  className="group flex cursor-pointer flex-col justify-between rounded-lg border border-border/80 bg-background/60 p-3 text-left shadow-xs transition-all hover:border-primary/50 hover:bg-secondary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  <span className="block space-y-1">
                    <span className="flex items-center justify-between">
                      <span className="text-[10px] font-semibold uppercase text-primary">{sug.category}</span>
                      <span
                        className={`rounded border px-1.5 py-0.5 text-[9px] font-bold ${sug.impact === "high" ? "border-red-500/20 bg-red-500/10 text-red-400" : "border-blue-500/20 bg-blue-500/10 text-blue-400"}`}
                      >
                        {sug.impact} impact
                      </span>
                    </span>
                    <span className="line-clamp-2 block text-xs font-semibold text-foreground transition-colors group-hover:text-primary">
                      {sug.title}
                    </span>
                    <span className="line-clamp-2 block text-[11px] text-muted-foreground">{sug.description}</span>
                  </span>
                  <span className="mt-2.5 flex items-center justify-between border-t border-border/40 pt-2 text-[11px] font-medium text-primary">
                    <span>Review with agent</span>
                    <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── 3. Executive Approval Queue ('Needs You' Review Inbox) ──── */}
      <ExecutiveApprovalQueue />

      {/* ── 4. Sales chart + deals, activity & quick actions ─────────── */}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <QuickStats
            deals={mapLoadable(deals.value, (d) => d.rows)}
            totals={totals}
            rowsTotal={dealRowsTotal}
            stageOrder={stageOrder.value.state === "ready" ? stageOrder.value.data : []}
            onRetry={retryDeals}
          />

          {/* Top deals by value (real sales rows) */}
          <div className="rounded-xl border border-border bg-card p-5 shadow-xs">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400">
                  <Briefcase className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-foreground">Top Deals by Value</h3>
                  <p className="text-xs text-muted-foreground">Largest deals in the sales database</p>
                </div>
              </div>
              {dealRows && (
                <span className="text-xs font-semibold text-emerald-400">
                  {dealsCut ? `Latest ${fmtInt(dealRows.length)} of ${fmtInt(dealRowsTotal ?? 0)} deals` : `Deals (${fmtInt(dealRows.length)})`}
                </span>
              )}
            </div>

            {deals.value.state !== "ready" ? (
              <NotConnected loadable={deals.value} service="The sales service" onRetry={retryDeals} />
            ) : topDealRows.length === 0 ? (
              <NoDataYet message="No deals yet" />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {topDealRows.map((deal, i) => (
                  <div
                    key={`${deal.client}-${i}`}
                    className="group relative flex flex-col justify-between rounded-lg border border-border/80 bg-secondary/20 p-3.5 transition-all hover:border-primary/40 hover:bg-secondary/35"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="space-y-0.5">
                        <span className="text-sm font-semibold text-foreground transition-colors group-hover:text-primary">
                          {deal.client}
                        </span>
                        <p className="line-clamp-1 text-xs text-muted-foreground">{deal.type}</p>
                      </div>
                      <span className="shrink-0 text-sm font-bold text-foreground">{deal.amount}</span>
                    </div>
                    <div className="mt-3 flex items-center justify-between border-t border-border/50 pt-2 text-xs">
                      <span
                        className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                          deal.won
                            ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                            : "border-blue-500/20 bg-blue-500/10 text-blue-400"
                        }`}
                      >
                        {deal.stage}
                      </span>
                      {deal.rep && <span className="text-muted-foreground">Rep: {deal.rep}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right 1 Col: Activity Feed & Executive Quick Actions */}
        <div className="space-y-6">
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
                className="flex cursor-pointer items-center justify-between rounded-lg border border-border/70 bg-secondary/30 px-3.5 py-2.5 text-left text-xs font-medium text-foreground transition hover:border-primary/50 hover:bg-secondary/60"
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

          <ActivityFeed />
        </div>
      </div>

      {/* ── 5. Recent escalations ────────────────────────────────────── */}
      <div className="rounded-xl">
        <TicketsTable />
      </div>

      {/* ── 6. Platform Modules Directory ────────────────────────────── */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-foreground">Platform Modules</h2>
            <p className="text-xs text-muted-foreground">Jump directly into specialized telecom operational modules</p>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {modules.map((module) => (
            <ModuleCard key={module.title} {...module} />
          ))}
        </div>
      </div>
    </div>
  )
}
