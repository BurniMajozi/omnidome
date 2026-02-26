"use client"

import { useState } from "react"
import { ModuleLayout } from "./module-layout"
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  FunnelChart,
  Funnel,
  LabelList,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
} from "recharts"
import {
  Megaphone,
  TrendingUp,
  Target,
  Mail,
  Radio,
  MapPin,
  Eye,
  Plane,
  Monitor,
  Image as ImageIcon,
  BarChart3,
  Sparkles,
  Activity,
  Building2,
  Users,
  Layers,
  ScanEye,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { useModuleData } from "@/lib/module-data"

// ── Default chart data ──────────────────────────────────────────────

const defaultCampaignPerformance = [
  { month: "Jan", impressions: 45000, clicks: 2800, conversions: 280, emailsSent: 84000 },
  { month: "Feb", impressions: 52000, clicks: 3200, conversions: 340, emailsSent: 91000 },
  { month: "Mar", impressions: 48000, clicks: 3100, conversions: 310, emailsSent: 87000 },
  { month: "Apr", impressions: 61000, clicks: 4100, conversions: 450, emailsSent: 102000 },
  { month: "May", impressions: 58000, clicks: 3900, conversions: 420, emailsSent: 96000 },
  { month: "Jun", impressions: 72000, clicks: 5200, conversions: 620, emailsSent: 118000 },
]

const defaultChannelData = [
  { name: "Email", value: 32, fill: "#4ade80" },
  { name: "Social Media", value: 28, fill: "#60a5fa" },
  { name: "Search", value: 22, fill: "#a855f7" },
  { name: "Display", value: 18, fill: "#f59e0b" },
]

const defaultCampaignROI = [
  { campaign: "Summer Promo", roi: 3.2 },
  { campaign: "Back to School", roi: 2.8 },
  { campaign: "Holiday Sale", roi: 4.1 },
  { campaign: "Black Friday", roi: 5.2 },
  { campaign: "New Year", roi: 2.4 },
]

const defaultEmailDelivery = [
  { month: "Jan", delivered: 81200, opened: 28420, bounced: 2800 },
  { month: "Feb", delivered: 88300, opened: 32670, bounced: 2700 },
  { month: "Mar", delivered: 84100, opened: 29430, bounced: 2900 },
  { month: "Apr", delivered: 99200, opened: 38680, bounced: 2800 },
  { month: "May", delivered: 93100, opened: 35780, bounced: 2900 },
  { month: "Jun", delivered: 115400, opened: 48470, bounced: 2600 },
]

const defaultLeadFunnel = [
  { name: "Visitors", value: 72000, fill: "#818cf8" },
  { name: "Leads", value: 18400, fill: "#a78bfa" },
  { name: "MQLs", value: 6200, fill: "#c084fc" },
  { name: "SQLs", value: 2100, fill: "#e879f9" },
  { name: "Customers", value: 620, fill: "#f472b6" },
]

// ── Radio Advertising Data (SA stations) ────────────────────────────

const defaultRadioStations = [
  { station: "Metro FM", type: "National", listeners: "4.2M", spotsBooked: 48, spend: "R 384,000", reach: "Gauteng, National", ctr: "2.1%" },
  { station: "Ukhozi FM", type: "National", listeners: "7.4M", spotsBooked: 36, spend: "R 288,000", reach: "KZN, National", ctr: "1.8%" },
  { station: "Jacaranda FM", type: "Regional", listeners: "3.1M", spotsBooked: 52, spend: "R 312,000", reach: "Gauteng, Limpopo, Mpumalanga", ctr: "2.4%" },
  { station: "947", type: "Regional", listeners: "1.2M", spotsBooked: 44, spend: "R 264,000", reach: "Johannesburg", ctr: "2.8%" },
  { station: "East Coast Radio", type: "Regional", listeners: "2.1M", spotsBooked: 40, spend: "R 240,000", reach: "KwaZulu-Natal", ctr: "2.3%" },
  { station: "Kaya FM", type: "Regional", listeners: "1.5M", spotsBooked: 32, spend: "R 192,000", reach: "Gauteng", ctr: "2.6%" },
  { station: "KFM", type: "Regional", listeners: "1.1M", spotsBooked: 28, spend: "R 168,000", reach: "Western Cape", ctr: "2.5%" },
  { station: "5FM", type: "National", listeners: "1.8M", spotsBooked: 24, spend: "R 144,000", reach: "National (Youth)", ctr: "3.1%" },
  { station: "Hot 102.7 FM", type: "Regional", listeners: "0.8M", spotsBooked: 20, spend: "R 120,000", reach: "Gauteng", ctr: "2.9%" },
  { station: "Gagasi FM", type: "Regional", listeners: "1.4M", spotsBooked: 30, spend: "R 180,000", reach: "KZN", ctr: "2.2%" },
]

const defaultRadioPerformance = [
  { month: "Jan", spots: 120, reach: 8200000, leads: 340, spend: 420000 },
  { month: "Feb", spots: 145, reach: 9400000, leads: 410, spend: 480000 },
  { month: "Mar", spots: 132, reach: 8800000, leads: 380, spend: 450000 },
  { month: "Apr", spots: 168, reach: 11200000, leads: 520, spend: 560000 },
  { month: "May", spots: 155, reach: 10600000, leads: 480, spend: 530000 },
  { month: "Jun", spots: 178, reach: 12400000, leads: 610, spend: 620000 },
]

const defaultRadioByType = [
  { name: "National", value: 40, fill: "#818cf8" },
  { name: "Regional", value: 38, fill: "#c084fc" },
  { name: "Campus", value: 12, fill: "#f472b6" },
  { name: "Local / Community", value: 10, fill: "#fbbf24" },
]

const radioTableColumns = [
  { key: "station", label: "Station" },
  { key: "type", label: "Type" },
  { key: "listeners", label: "Listeners" },
  { key: "spotsBooked", label: "Spots" },
  { key: "spend", label: "Spend" },
  { key: "reach", label: "Reach" },
  { key: "ctr", label: "Response Rate" },
]

// ── Billboard / Outdoor Advertising Data ────────────────────────────

const defaultBillboardSites = [
  { id: "1", site: "OR Tambo Arrivals Hall", type: "Airport", format: "Digital LED Wall", location: "Johannesburg", impressions: "2.4M/mo", status: "Live", spend: "R 85,000", sightliveScore: 92 },
  { id: "2", site: "N1 Buccleuch Interchange", type: "Digital Billboard", format: "Digital Super Sign", location: "Johannesburg", impressions: "1.8M/mo", status: "Live", spend: "R 65,000", sightliveScore: 88 },
  { id: "3", site: "Cape Town Int'l Departures", type: "Airport", format: "Lightbox Network", location: "Cape Town", impressions: "1.6M/mo", status: "Live", spend: "R 72,000", sightliveScore: 85 },
  { id: "4", site: "M1 Sandton CBD", type: "Static Billboard", format: "Freeway Super Sign", location: "Sandton", impressions: "1.2M/mo", status: "Live", spend: "R 55,000", sightliveScore: 81 },
  { id: "5", site: "N2 King Shaka Corridor", type: "Digital Billboard", format: "Urban Gantry", location: "Durban", impressions: "900K/mo", status: "Scheduled", spend: "R 42,000", sightliveScore: 0 },
  { id: "6", site: "Rosebank Mall Entrance", type: "Static Billboard", format: "City Portrait 7x5", location: "Johannesburg", impressions: "480K/mo", status: "Live", spend: "R 18,000", sightliveScore: 76 },
  { id: "7", site: "Lanseria Airport Terminal", type: "Airport", format: "Digital Screen Network", location: "Johannesburg", impressions: "320K/mo", status: "Draft", spend: "R 38,000", sightliveScore: 0 },
  { id: "8", site: "N3 Durban Toll Plaza", type: "Static Billboard", format: "Rural Super 3x12", location: "KZN", impressions: "1.1M/mo", status: "Live", spend: "R 12,000", sightliveScore: 74 },
]

const defaultBillboardByType = [
  { name: "Airport", value: 28, fill: "#38bdf8" },
  { name: "Digital Billboard", value: 35, fill: "#a78bfa" },
  { name: "Static Billboard", value: 22, fill: "#4ade80" },
  { name: "Street Pole", value: 8, fill: "#fbbf24" },
  { name: "Mall / Indoor", value: 7, fill: "#f472b6" },
]

const defaultBillboardPerformance = [
  { month: "Jan", airport: 4200000, digital: 3800000, static_bb: 2100000, spend: 380000 },
  { month: "Feb", airport: 4500000, digital: 4100000, static_bb: 2300000, spend: 410000 },
  { month: "Mar", airport: 4300000, digital: 3900000, static_bb: 2200000, spend: 395000 },
  { month: "Apr", airport: 5100000, digital: 4800000, static_bb: 2600000, spend: 480000 },
  { month: "May", airport: 4800000, digital: 4500000, static_bb: 2400000, spend: 450000 },
  { month: "Jun", airport: 5400000, digital: 5200000, static_bb: 2800000, spend: 520000 },
]

const billboardTableColumns = [
  { key: "site", label: "Site" },
  { key: "type", label: "Type" },
  { key: "format", label: "Format" },
  { key: "location", label: "Location" },
  { key: "impressions", label: "Impressions" },
  { key: "status", label: "Status" },
  { key: "spend", label: "Spend/mo" },
]

// ── SightLive™ Post-Campaign Analytics Data ─────────────────────────

const defaultSightLiveOverview = {
  campaignsAnalyzed: 24,
  totalImpressions: "34.2M",
  avgDwellTime: "4.8s",
  attentionRate: "67%",
  footTrafficLift: "+22%",
  brandRecall: "41%",
  verifiedViews: "12.8M",
}

const defaultSightLiveByMedium = [
  { medium: "Airport Screens", campaigns: 6, impressions: "8.4M", dwellTime: "6.2s", attentionRate: "78%", footTrafficLift: "+31%", brandRecall: "52%" },
  { medium: "Digital Billboards", campaigns: 9, impressions: "14.6M", dwellTime: "3.8s", attentionRate: "62%", footTrafficLift: "+18%", brandRecall: "38%" },
  { medium: "Static Billboards", campaigns: 5, impressions: "6.8M", dwellTime: "2.4s", attentionRate: "54%", footTrafficLift: "+12%", brandRecall: "29%" },
  { medium: "Mall / Indoor", campaigns: 4, impressions: "4.4M", dwellTime: "7.1s", attentionRate: "82%", footTrafficLift: "+28%", brandRecall: "47%" },
]

const defaultSightLiveRadar = [
  { metric: "Verified Views", airport: 92, digital: 78, static_bb: 60, indoor: 85 },
  { metric: "Dwell Time", airport: 85, digital: 65, static_bb: 42, indoor: 95 },
  { metric: "Attention Rate", airport: 78, digital: 62, static_bb: 54, indoor: 82 },
  { metric: "Foot Traffic Lift", airport: 88, digital: 58, static_bb: 48, indoor: 80 },
  { metric: "Brand Recall", airport: 82, digital: 68, static_bb: 52, indoor: 78 },
  { metric: "Conversion Proxy", airport: 72, digital: 60, static_bb: 40, indoor: 70 },
]

const defaultSightLiveTrend = [
  { month: "Jan", verifiedViews: 1600000, attentionRate: 62, brandRecall: 36 },
  { month: "Feb", verifiedViews: 1800000, attentionRate: 64, brandRecall: 38 },
  { month: "Mar", verifiedViews: 1900000, attentionRate: 63, brandRecall: 37 },
  { month: "Apr", verifiedViews: 2400000, attentionRate: 68, brandRecall: 42 },
  { month: "May", verifiedViews: 2200000, attentionRate: 66, brandRecall: 40 },
  { month: "Jun", verifiedViews: 2900000, attentionRate: 71, brandRecall: 44 },
]

const sightLiveTableColumns = [
  { key: "medium", label: "Medium" },
  { key: "campaigns", label: "Campaigns" },
  { key: "impressions", label: "Impressions" },
  { key: "dwellTime", label: "Dwell Time" },
  { key: "attentionRate", label: "Attention Rate" },
  { key: "footTrafficLift", label: "Foot Traffic Lift" },
  { key: "brandRecall", label: "Brand Recall" },
]

// ── Flippable KPI flashcards ────────────────────────────────────────

const defaultFlashcardKPIs = [
  {
    id: "1",
    title: "Active Campaigns",
    value: "18",
    change: "+5",
    changeType: "positive" as const,
    iconKey: "campaigns",
    backTitle: "Campaign Breakdown",
    backDetails: [
      { label: "Email Campaigns", value: "7" },
      { label: "Social Campaigns", value: "5" },
      { label: "Paid Ads", value: "4" },
      { label: "Content / SEO", value: "2" },
    ],
    backInsight: "Email campaigns drive 42% of total conversions",
  },
  {
    id: "2",
    title: "Email Delivery Rate",
    value: "99.2%",
    change: "+0.4%",
    changeType: "positive" as const,
    iconKey: "email",
    backTitle: "Email Health",
    backDetails: [
      { label: "Sent This Month", value: "118,000" },
      { label: "Delivered", value: "115,400" },
      { label: "Bounce Rate", value: "0.8%" },
      { label: "Open Rate", value: "42.0%" },
    ],
    backInsight: "Transactional emails at 99.88% delivery success",
  },
  {
    id: "3",
    title: "Lead Conversion",
    value: "3.4%",
    change: "+0.6%",
    changeType: "positive" as const,
    iconKey: "conversion",
    backTitle: "Conversion Funnel",
    backDetails: [
      { label: "Visitors → Leads", value: "25.6%" },
      { label: "Leads → MQL", value: "33.7%" },
      { label: "MQL → SQL", value: "33.9%" },
      { label: "SQL → Customer", value: "29.5%" },
    ],
    backInsight: "Landing page A/B tests boosted MQL rate by 12%",
  },
  {
    id: "4",
    title: "Marketing ROI",
    value: "4.2x",
    change: "+0.8x",
    changeType: "positive" as const,
    iconKey: "roi",
    backTitle: "ROI by Channel",
    backDetails: [
      { label: "Email Marketing", value: "6.8x" },
      { label: "Search / SEO", value: "4.1x" },
      { label: "Social Media", value: "2.9x" },
      { label: "Display Ads", value: "1.8x" },
    ],
    backInsight: "Email delivers highest ROI; reallocate 15% display → email",
  },
]

const marketingKpiIconMap: Record<string, JSX.Element> = {
  campaigns: <Megaphone className="h-5 w-5 text-fuchsia-400" />,
  email: <Mail className="h-5 w-5 text-emerald-400" />,
  conversion: <Target className="h-5 w-5 text-blue-400" />,
  roi: <TrendingUp className="h-5 w-5 text-amber-400" />,
}

// ── Activity feed ───────────────────────────────────────────────────

const defaultActivities = [
  {
    id: "1",
    user: "Naledi Moroka",
    action: "launched email campaign",
    target: "Winter Fibre Promo",
    time: "5 minutes ago",
    type: "create" as const,
  },
  {
    id: "2",
    user: "Thabo Dlamini",
    action: "published social post for",
    target: "Speed Upgrade Bundle",
    time: "22 minutes ago",
    type: "create" as const,
  },
  {
    id: "3",
    user: "Priya Naidoo",
    action: "updated A/B test on",
    target: "Landing Page v3",
    time: "1 hour ago",
    type: "update" as const,
  },
  {
    id: "4",
    user: "James van Wyk",
    action: "reviewed analytics for",
    target: "Back to School Campaign",
    time: "2 hours ago",
    type: "comment" as const,
  },
  {
    id: "5",
    user: "Aisha Mahlangu",
    action: "created audience segment",
    target: "High-Value Churning Subs",
    time: "3 hours ago",
    type: "create" as const,
  },
]

// ── Issues ──────────────────────────────────────────────────────────

const defaultIssues = [
  {
    id: "1",
    title: "Email bounce rate spike on Telkom domain",
    severity: "high" as const,
    status: "open" as const,
    assignee: "Naledi Moroka",
    time: "30 minutes ago",
  },
  {
    id: "2",
    title: "Google Ads spend exceeded daily cap by 18%",
    severity: "medium" as const,
    status: "in-progress" as const,
    assignee: "Thabo Dlamini",
    time: "2 hours ago",
  },
  {
    id: "3",
    title: "Social scheduler failed for 3 queued posts",
    severity: "high" as const,
    status: "open" as const,
    assignee: "Priya Naidoo",
    time: "4 hours ago",
  },
  {
    id: "4",
    title: "Landing page load time >4s on mobile",
    severity: "medium" as const,
    status: "in-progress" as const,
    assignee: "James van Wyk",
    time: "Yesterday",
  },
  {
    id: "5",
    title: "DKIM alignment failure on promo domain",
    severity: "critical" as const,
    status: "open" as const,
    assignee: "Aisha Mahlangu",
    time: "Yesterday",
  },
]

// ── Summary ─────────────────────────────────────────────────────────

const defaultSummary = `This month the Marketing Hub drove 118,000 emails with a 99.2% delivery rate and 42% open rate, making email the top-performing channel at 6.8x ROI. 18 active campaigns across email, social, paid search, and display generated 18,400 new leads with a 3.4% visitor-to-customer conversion rate. The "Winter Fibre Promo" campaign alone contributed 2,100 qualified leads. A/B testing on the primary landing page lifted MQL conversion by 12%. Focus areas for next month include fixing DKIM alignment for the promo domain, optimizing mobile landing page speed, and reallocating 15% of display budget to email and search channels for higher returns.`

// ── Tasks ───────────────────────────────────────────────────────────

const defaultTasks = [
  {
    id: "1",
    title: "Fix DKIM alignment on promo domain",
    priority: "urgent" as const,
    status: "todo" as const,
    dueDate: "Today",
    assignee: "Aisha Mahlangu",
  },
  {
    id: "2",
    title: "Launch Spring Fibre referral campaign",
    priority: "high" as const,
    status: "in-progress" as const,
    dueDate: "Tomorrow",
    assignee: "Naledi Moroka",
  },
  {
    id: "3",
    title: "Build email template for abandoned cart flow",
    priority: "high" as const,
    status: "todo" as const,
    dueDate: "This week",
    assignee: "James van Wyk",
  },
  {
    id: "4",
    title: "Audit Google Ads budget pacing rules",
    priority: "normal" as const,
    status: "todo" as const,
    dueDate: "This week",
    assignee: "Thabo Dlamini",
  },
  {
    id: "5",
    title: "Create audience segment for upsell targets",
    priority: "normal" as const,
    status: "done" as const,
    dueDate: "Completed",
    assignee: "Priya Naidoo",
  },
]

// ── AI Recommendations ──────────────────────────────────────────────

const defaultAiRecommendations = [
  {
    id: "1",
    title: "Shift Budget to Email",
    description:
      "Email delivers 6.8x ROI vs 1.8x for display. Reallocating 15% of display spend to email could increase monthly conversions by ~90.",
    impact: "high" as const,
    category: "Budget",
  },
  {
    id: "2",
    title: "Abandoned Cart Automation",
    description:
      "Cart abandonment is at 68%. An automated 3-step email flow (1h → 24h → 72h) is projected to recover 12% of lost orders.",
    impact: "high" as const,
    category: "Automation",
  },
  {
    id: "3",
    title: "Optimize Send Times",
    description:
      "Open-rate analysis shows peak engagement Tue–Thu 09:00-11:00. Rescheduling bulk sends could lift open rate by 8%.",
    impact: "medium" as const,
    category: "Email",
  },
  {
    id: "4",
    title: "Dedicated IP Warmup",
    description:
      "Volume growth warrants a dedicated sending IP. Start warmup now to maintain 99%+ deliverability at scale.",
    impact: "medium" as const,
    category: "Deliverability",
  },
  {
    id: "5",
    title: "Content Calendar Gap",
    description:
      "No campaigns scheduled for the first week of next month. Recommend scheduling a product update email and social series.",
    impact: "low" as const,
    category: "Planning",
  },
]

// ── Data table (Campaigns) ──────────────────────────────────────────

const defaultTableData = [
  {
    id: "1",
    campaign: "Winter Fibre Promo",
    channel: "Email",
    status: "Active",
    sent: "42,000",
    openRate: "44.2%",
    ctr: "8.1%",
    conversions: "620",
    roi: "5.2x",
  },
  {
    id: "2",
    campaign: "Speed Upgrade Bundle",
    channel: "Social",
    status: "Active",
    sent: "—",
    openRate: "—",
    ctr: "3.4%",
    conversions: "310",
    roi: "2.9x",
  },
  {
    id: "3",
    campaign: "Back to School",
    channel: "Paid Search",
    status: "Completed",
    sent: "—",
    openRate: "—",
    ctr: "5.6%",
    conversions: "450",
    roi: "4.1x",
  },
  {
    id: "4",
    campaign: "Referral Rewards",
    channel: "Email",
    status: "Active",
    sent: "28,000",
    openRate: "38.7%",
    ctr: "6.9%",
    conversions: "280",
    roi: "6.1x",
  },
  {
    id: "5",
    campaign: "IoT Smart Home Launch",
    channel: "Display",
    status: "Scheduled",
    sent: "—",
    openRate: "—",
    ctr: "—",
    conversions: "—",
    roi: "—",
  },
  {
    id: "6",
    campaign: "Black Friday Early Access",
    channel: "Email + Social",
    status: "Draft",
    sent: "—",
    openRate: "—",
    ctr: "—",
    conversions: "—",
    roi: "—",
  },
]

const defaultTableColumns = [
  { key: "campaign", label: "Campaign" },
  { key: "channel", label: "Channel" },
  { key: "status", label: "Status" },
  { key: "sent", label: "Sent" },
  { key: "openRate", label: "Open Rate" },
  { key: "ctr", label: "CTR" },
  { key: "conversions", label: "Conversions" },
  { key: "roi", label: "ROI" },
]

// ════════════════════════════════════════════════════════════════════
// Sub-panel tab IDs
// ════════════════════════════════════════════════════════════════════
type MarketingSubPanel = "digital" | "radio" | "billboards" | "sightlive"

const subPanelTabs: { id: MarketingSubPanel; label: string; icon: typeof Megaphone }[] = [
  { id: "digital", label: "Digital Marketing", icon: Megaphone },
  { id: "radio", label: "Radio Advertising", icon: Radio },
  { id: "billboards", label: "Billboards & OOH", icon: MapPin },
  { id: "sightlive", label: "SightLive™ Analytics", icon: ScanEye },
]

// Tooltip styles reused everywhere
const tooltipStyle = {
  backgroundColor: "#262626",
  border: "1px solid #404040",
  borderRadius: "8px",
  color: "#fff",
}

// ════════════════════════════════════════════════════════════════════
// Component
// ════════════════════════════════════════════════════════════════════

export function MarketingModule() {
  const [activePanel, setActivePanel] = useState<MarketingSubPanel>("digital")

  const { data } = useModuleData("marketing", {
    campaignPerformance: defaultCampaignPerformance,
    channelData: defaultChannelData,
    campaignROI: defaultCampaignROI,
    emailDelivery: defaultEmailDelivery,
    leadFunnel: defaultLeadFunnel,
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
    campaignPerformance,
    channelData,
    campaignROI,
    emailDelivery,
    leadFunnel,
    flashcardKPIs,
    activities,
    issues,
    summary,
    tasks,
    aiRecommendations,
    tableData,
    tableColumns,
  } = data

  const flashcardKPIsWithIcons = flashcardKPIs.map((kpi: any) => ({
    ...kpi,
    icon: marketingKpiIconMap[kpi.iconKey] ?? null,
  }))

  return (
    <ModuleLayout
      title="Marketing"
      flashcardKPIs={flashcardKPIsWithIcons}
      activities={activities}
      issues={issues}
      summary={summary}
      tasks={tasks}
      aiRecommendations={aiRecommendations}
      tableData={tableData}
      tableColumns={tableColumns}
    >
      {/* ── Sub-Panel Tabs ─────────────────────────────────────── */}
      <div className="flex flex-wrap gap-2 rounded-xl border border-border bg-card p-2">
        {subPanelTabs.map((tab) => {
          const Icon = tab.icon
          const isActive = activePanel === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActivePanel(tab.id)}
              className={`flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-all ${
                isActive
                  ? "bg-primary text-primary-foreground shadow-md"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
              {tab.id === "sightlive" && (
                <Badge variant="outline" className="ml-1 border-fuchsia-500/50 text-fuchsia-400 text-[10px] px-1.5 py-0">
                  Proprietary
                </Badge>
              )}
            </button>
          )
        })}
      </div>

      {/* ══════════════════════════════════════════════════════════
          DIGITAL MARKETING PANEL
         ══════════════════════════════════════════════════════════ */}
      {activePanel === "digital" && (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Campaign Performance Trend */}
            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="mb-4 text-lg font-semibold text-foreground">
                Campaign Performance Trend
              </h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={campaignPerformance}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                    <XAxis dataKey="month" tick={{ fill: "#737373", fontSize: 12 }} />
                    <YAxis tick={{ fill: "#737373", fontSize: 12 }} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Legend />
                    <Line type="monotone" dataKey="impressions" stroke="#818cf8" strokeWidth={2} name="Impressions" />
                    <Line type="monotone" dataKey="clicks" stroke="#4ade80" strokeWidth={2} name="Clicks" />
                    <Line type="monotone" dataKey="conversions" stroke="#f472b6" strokeWidth={2} name="Conversions" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Email Delivery & Engagement */}
            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="mb-4 text-lg font-semibold text-foreground">
                Email Delivery &amp; Engagement
              </h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={emailDelivery}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                    <XAxis dataKey="month" tick={{ fill: "#737373", fontSize: 12 }} />
                    <YAxis tick={{ fill: "#737373", fontSize: 12 }} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Legend />
                    <Area type="monotone" dataKey="delivered" stroke="#4ade80" fill="#4ade8040" strokeWidth={2} name="Delivered" />
                    <Area type="monotone" dataKey="opened" stroke="#60a5fa" fill="#60a5fa40" strokeWidth={2} name="Opened" />
                    <Area type="monotone" dataKey="bounced" stroke="#f87171" fill="#f8717140" strokeWidth={2} name="Bounced" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Lead Conversion Funnel */}
            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="mb-4 text-lg font-semibold text-foreground">Lead Conversion Funnel</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <FunnelChart>
                    <Tooltip contentStyle={tooltipStyle} />
                    <Funnel dataKey="value" data={leadFunnel} isAnimationActive>
                      <LabelList position="right" fill="#a78bfa" stroke="none" dataKey="name" />
                    </Funnel>
                  </FunnelChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Channel Distribution */}
            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="mb-4 text-lg font-semibold text-foreground">Traffic by Channel</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={channelData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, value }: { name: string; value: number }) => `${name}: ${value}%`}
                      outerRadius={80}
                      fill="#4ade80"
                      dataKey="value"
                    >
                      {channelData.map((entry: any, index: number) => (
                        <Cell key={`cell-${index}`} fill={entry.fill} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Campaign ROI Comparison */}
          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="mb-4 text-lg font-semibold text-foreground">Campaign ROI Comparison</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={campaignROI}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                  <XAxis dataKey="campaign" tick={{ fill: "#737373", fontSize: 12 }} />
                  <YAxis
                    label={{ value: "ROI Multiplier", angle: -90, position: "insideLeft", fill: "#737373" }}
                    tick={{ fill: "#737373", fontSize: 12 }}
                  />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="roi" fill="#c084fc" name="ROI Multiplier" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}

      {/* ══════════════════════════════════════════════════════════
          RADIO ADVERTISING PANEL
         ══════════════════════════════════════════════════════════ */}
      {activePanel === "radio" && (
        <>
          {/* Radio KPI Row */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { label: "Total Spots Booked", value: "354", sub: "this month", icon: Radio, color: "text-indigo-400" },
              { label: "Cumulative Reach", value: "12.4M", sub: "listeners / mo", icon: Users, color: "text-emerald-400" },
              { label: "Radio Leads", value: "610", sub: "+27% vs last month", icon: Target, color: "text-amber-400" },
              { label: "Radio Ad Spend", value: "R 2.29M", sub: "month to date", icon: TrendingUp, color: "text-fuchsia-400" },
            ].map((kpi, idx) => {
              const Icon = kpi.icon
              return (
                <div key={idx} className="rounded-xl border border-border bg-card p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="rounded-lg bg-primary/20 p-2"><Icon className={`h-4 w-4 ${kpi.color}`} /></div>
                    <p className="text-xs text-muted-foreground">{kpi.label}</p>
                  </div>
                  <p className="text-2xl font-bold text-foreground">{kpi.value}</p>
                  <p className="text-xs text-muted-foreground mt-1">{kpi.sub}</p>
                </div>
              )
            })}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Radio Performance Trend */}
            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="mb-4 text-lg font-semibold text-foreground">Radio Performance Trend</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={defaultRadioPerformance}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                    <XAxis dataKey="month" tick={{ fill: "#737373", fontSize: 12 }} />
                    <YAxis tick={{ fill: "#737373", fontSize: 12 }} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Legend />
                    <Line type="monotone" dataKey="spots" stroke="#818cf8" strokeWidth={2} name="Spots Aired" />
                    <Line type="monotone" dataKey="leads" stroke="#4ade80" strokeWidth={2} name="Leads Generated" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Radio Spend by Type */}
            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="mb-4 text-lg font-semibold text-foreground">Spend by Station Type</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={defaultRadioByType}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, value }: { name: string; value: number }) => `${name}: ${value}%`}
                      outerRadius={80}
                      dataKey="value"
                    >
                      {defaultRadioByType.map((entry, index) => (
                        <Cell key={`rc-${index}`} fill={entry.fill} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Radio Stations Table */}
          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="mb-4 text-lg font-semibold text-foreground">Active Radio Station Bookings</h3>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    {radioTableColumns.map((col) => (
                      <th key={col.key} className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">{col.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {defaultRadioStations.map((row, idx) => (
                    <tr key={idx} className="border-b border-border last:border-0 hover:bg-muted/50">
                      <td className="px-4 py-3 text-sm font-medium text-foreground">{row.station}</td>
                      <td className="px-4 py-3 text-sm">
                        <Badge variant="outline" className={row.type === "National" ? "border-indigo-500/50 text-indigo-400" : "border-purple-500/50 text-purple-400"}>
                          {row.type}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-sm text-foreground">{row.listeners}</td>
                      <td className="px-4 py-3 text-sm text-foreground">{row.spotsBooked}</td>
                      <td className="px-4 py-3 text-sm text-foreground">{row.spend}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{row.reach}</td>
                      <td className="px-4 py-3 text-sm text-emerald-400">{row.ctr}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ══════════════════════════════════════════════════════════
          BILLBOARDS & OOH PANEL
         ══════════════════════════════════════════════════════════ */}
      {activePanel === "billboards" && (
        <>
          {/* Billboard KPI Row */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { label: "Total OOH Sites", value: "42", sub: "across 6 provinces", icon: MapPin, color: "text-sky-400" },
              { label: "Monthly Impressions", value: "34.2M", sub: "airport + billboard + static", icon: Eye, color: "text-emerald-400" },
              { label: "Airport Sites", value: "8", sub: "OR Tambo, CPT, King Shaka, Lanseria", icon: Plane, color: "text-amber-400" },
              { label: "OOH Ad Spend", value: "R 2.64M", sub: "month to date", icon: TrendingUp, color: "text-fuchsia-400" },
            ].map((kpi, idx) => {
              const Icon = kpi.icon
              return (
                <div key={idx} className="rounded-xl border border-border bg-card p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="rounded-lg bg-primary/20 p-2"><Icon className={`h-4 w-4 ${kpi.color}`} /></div>
                    <p className="text-xs text-muted-foreground">{kpi.label}</p>
                  </div>
                  <p className="text-2xl font-bold text-foreground">{kpi.value}</p>
                  <p className="text-xs text-muted-foreground mt-1">{kpi.sub}</p>
                </div>
              )
            })}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Impressions by Billboard Type */}
            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="mb-4 text-lg font-semibold text-foreground">Impressions by OOH Type</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={defaultBillboardPerformance}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                    <XAxis dataKey="month" tick={{ fill: "#737373", fontSize: 12 }} />
                    <YAxis tick={{ fill: "#737373", fontSize: 12 }} tickFormatter={(v) => `${(v / 1000000).toFixed(1)}M`} />
                    <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => [`${(value / 1000000).toFixed(2)}M`, ""]} />
                    <Legend />
                    <Area type="monotone" dataKey="airport" stroke="#38bdf8" fill="#38bdf840" strokeWidth={2} name="Airport" />
                    <Area type="monotone" dataKey="digital" stroke="#a78bfa" fill="#a78bfa40" strokeWidth={2} name="Digital Billboard" />
                    <Area type="monotone" dataKey="static_bb" stroke="#4ade80" fill="#4ade8040" strokeWidth={2} name="Static Billboard" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Billboard Spend Distribution */}
            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="mb-4 text-lg font-semibold text-foreground">Spend by OOH Type</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={defaultBillboardByType}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, value }: { name: string; value: number }) => `${name}: ${value}%`}
                      outerRadius={80}
                      dataKey="value"
                    >
                      {defaultBillboardByType.map((entry, index) => (
                        <Cell key={`bb-${index}`} fill={entry.fill} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Billboard Sites Table */}
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-foreground">OOH Site Inventory</h3>
              <div className="flex gap-2">
                <Badge variant="outline" className="border-sky-500/50 text-sky-400">Airport</Badge>
                <Badge variant="outline" className="border-purple-500/50 text-purple-400">Digital</Badge>
                <Badge variant="outline" className="border-emerald-500/50 text-emerald-400">Static</Badge>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    {billboardTableColumns.map((col) => (
                      <th key={col.key} className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">{col.label}</th>
                    ))}
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                      <span className="flex items-center gap-1">
                        <ScanEye className="h-3 w-3 text-fuchsia-400" /> SightLive™
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {defaultBillboardSites.map((site) => (
                    <tr key={site.id} className="border-b border-border last:border-0 hover:bg-muted/50">
                      <td className="px-4 py-3 text-sm font-medium text-foreground">{site.site}</td>
                      <td className="px-4 py-3 text-sm">
                        <Badge variant="outline" className={
                          site.type === "Airport" ? "border-sky-500/50 text-sky-400" :
                          site.type === "Digital Billboard" ? "border-purple-500/50 text-purple-400" :
                          "border-emerald-500/50 text-emerald-400"
                        }>
                          {site.type}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{site.format}</td>
                      <td className="px-4 py-3 text-sm text-foreground">{site.location}</td>
                      <td className="px-4 py-3 text-sm text-foreground">{site.impressions}</td>
                      <td className="px-4 py-3 text-sm">
                        <Badge variant="outline" className={
                          site.status === "Live" ? "border-emerald-500/50 text-emerald-400" :
                          site.status === "Scheduled" ? "border-amber-500/50 text-amber-400" :
                          "border-slate-500/50 text-slate-400"
                        }>
                          {site.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-sm text-foreground">{site.spend}</td>
                      <td className="px-4 py-3 text-sm">
                        {site.sightliveScore > 0 ? (
                          <div className="flex items-center gap-2">
                            <div className="h-2 w-16 rounded-full bg-muted overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  site.sightliveScore >= 85 ? "bg-emerald-500" :
                                  site.sightliveScore >= 70 ? "bg-amber-500" : "bg-red-500"
                                }`}
                                style={{ width: `${site.sightliveScore}%` }}
                              />
                            </div>
                            <span className="text-xs text-muted-foreground">{site.sightliveScore}</span>
                          </div>
                        ) : (
                          <span className="text-xs text-slate-500">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ══════════════════════════════════════════════════════════
          SIGHTLIVE™ POST-CAMPAIGN ANALYTICS PANEL
         ══════════════════════════════════════════════════════════ */}
      {activePanel === "sightlive" && (
        <>
          {/* SightLive Hero Banner */}
          <div className="rounded-xl border border-fuchsia-500/30 bg-gradient-to-r from-fuchsia-950/40 via-purple-950/30 to-indigo-950/40 p-6">
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <div className="rounded-lg bg-fuchsia-500/20 p-2.5">
                    <ScanEye className="h-6 w-6 text-fuchsia-400" />
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-foreground flex items-center gap-2">
                      SightLive™
                      <Badge className="bg-fuchsia-500/20 text-fuchsia-300 text-[10px]">First-of-its-Kind</Badge>
                    </h3>
                    <p className="text-sm text-muted-foreground">Proprietary Post-Campaign Analytics for Outdoor &amp; Indoor Media</p>
                  </div>
                </div>
                <p className="text-sm text-muted-foreground max-w-2xl mt-2">
                  SightLive™ is our proprietary analytics platform — the first of its kind in the media industry — delivering
                  verified impression counts, real-time dwell-time measurement, attention rate scoring, foot-traffic lift analysis,
                  and brand recall benchmarks for outdoor billboards, airport screens, mall displays, and indoor signage.
                </p>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 lg:gap-4">
                {[
                  { label: "Campaigns Analyzed", value: defaultSightLiveOverview.campaignsAnalyzed.toString() },
                  { label: "Verified Views", value: defaultSightLiveOverview.verifiedViews },
                  { label: "Avg Dwell Time", value: defaultSightLiveOverview.avgDwellTime },
                  { label: "Brand Recall", value: defaultSightLiveOverview.brandRecall },
                ].map((stat, idx) => (
                  <div key={idx} className="text-center">
                    <p className="text-xl font-bold text-fuchsia-300">{stat.value}</p>
                    <p className="text-[10px] text-muted-foreground">{stat.label}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* SightLive KPI Row */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { label: "Total Impressions", value: defaultSightLiveOverview.totalImpressions, sub: "verified via SightLive™", icon: Eye, color: "text-fuchsia-400" },
              { label: "Attention Rate", value: defaultSightLiveOverview.attentionRate, sub: "avg across all media", icon: Activity, color: "text-indigo-400" },
              { label: "Foot Traffic Lift", value: defaultSightLiveOverview.footTrafficLift, sub: "vs control zones", icon: Users, color: "text-emerald-400" },
              { label: "Brand Recall", value: defaultSightLiveOverview.brandRecall, sub: "survey-validated", icon: Sparkles, color: "text-amber-400" },
            ].map((kpi, idx) => {
              const Icon = kpi.icon
              return (
                <div key={idx} className="rounded-xl border border-fuchsia-500/20 bg-card p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="rounded-lg bg-fuchsia-500/10 p-2"><Icon className={`h-4 w-4 ${kpi.color}`} /></div>
                    <p className="text-xs text-muted-foreground">{kpi.label}</p>
                  </div>
                  <p className="text-2xl font-bold text-foreground">{kpi.value}</p>
                  <p className="text-xs text-muted-foreground mt-1">{kpi.sub}</p>
                </div>
              )
            })}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Radar: Medium Comparison */}
            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="mb-4 text-lg font-semibold text-foreground">SightLive™ Medium Comparison</h3>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={defaultSightLiveRadar}>
                    <PolarGrid stroke="#404040" />
                    <PolarAngleAxis dataKey="metric" tick={{ fill: "#a1a1aa", fontSize: 11 }} />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: "#737373", fontSize: 10 }} />
                    <Radar name="Airport" dataKey="airport" stroke="#38bdf8" fill="#38bdf8" fillOpacity={0.2} strokeWidth={2} />
                    <Radar name="Digital" dataKey="digital" stroke="#a78bfa" fill="#a78bfa" fillOpacity={0.15} strokeWidth={2} />
                    <Radar name="Static" dataKey="static_bb" stroke="#4ade80" fill="#4ade80" fillOpacity={0.1} strokeWidth={2} />
                    <Radar name="Indoor" dataKey="indoor" stroke="#f472b6" fill="#f472b6" fillOpacity={0.15} strokeWidth={2} />
                    <Legend />
                    <Tooltip contentStyle={tooltipStyle} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* SightLive Verified Views Trend */}
            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="mb-4 text-lg font-semibold text-foreground">Verified Views &amp; Brand Recall Trend</h3>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={defaultSightLiveTrend}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                    <XAxis dataKey="month" tick={{ fill: "#737373", fontSize: 12 }} />
                    <YAxis yAxisId="left" tick={{ fill: "#737373", fontSize: 12 }} tickFormatter={(v) => `${(v / 1000000).toFixed(1)}M`} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fill: "#737373", fontSize: 12 }} unit="%" />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Legend />
                    <Line yAxisId="left" type="monotone" dataKey="verifiedViews" stroke="#c084fc" strokeWidth={2} name="Verified Views" />
                    <Line yAxisId="right" type="monotone" dataKey="attentionRate" stroke="#fbbf24" strokeWidth={2} name="Attention Rate %" />
                    <Line yAxisId="right" type="monotone" dataKey="brandRecall" stroke="#4ade80" strokeWidth={2} name="Brand Recall %" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* SightLive by Medium Table */}
          <div className="rounded-xl border border-fuchsia-500/20 bg-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <ScanEye className="h-5 w-5 text-fuchsia-400" />
                Post-Campaign Reports by Medium
              </h3>
              <Badge className="bg-fuchsia-500/20 text-fuchsia-300 text-xs">SightLive™ Verified</Badge>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    {sightLiveTableColumns.map((col) => (
                      <th key={col.key} className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">{col.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {defaultSightLiveByMedium.map((row, idx) => (
                    <tr key={idx} className="border-b border-border last:border-0 hover:bg-muted/50">
                      <td className="px-4 py-3 text-sm font-medium text-foreground">
                        <span className="flex items-center gap-2">
                          {row.medium === "Airport Screens" ? <Plane className="h-4 w-4 text-sky-400" /> :
                           row.medium === "Digital Billboards" ? <Monitor className="h-4 w-4 text-purple-400" /> :
                           row.medium === "Static Billboards" ? <ImageIcon className="h-4 w-4 text-emerald-400" /> :
                           <Building2 className="h-4 w-4 text-pink-400" />}
                          {row.medium}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-foreground">{row.campaigns}</td>
                      <td className="px-4 py-3 text-sm text-foreground">{row.impressions}</td>
                      <td className="px-4 py-3 text-sm text-foreground">{row.dwellTime}</td>
                      <td className="px-4 py-3 text-sm text-foreground">{row.attentionRate}</td>
                      <td className="px-4 py-3 text-sm text-emerald-400">{row.footTrafficLift}</td>
                      <td className="px-4 py-3 text-sm text-amber-400">{row.brandRecall}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </ModuleLayout>
  )
}
