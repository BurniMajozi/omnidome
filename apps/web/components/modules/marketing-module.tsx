"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/ui/page-header"
import { InsightsCard } from "@/components/dashboard/insights-card"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from "recharts"
import {
  Megaphone, Mail, TrendingUp, Users, Target, Zap, Radio, Tv, Monitor,
  Send, Plus, Eye, MousePointerClick, DollarSign, UserCheck, Award,
  MessageSquare, Heart, Share2, Bell, Settings, BarChart3, Globe,
  Image, Calendar, Clock, CheckCircle, AlertTriangle, XCircle,
  ArrowUpRight, ArrowDownRight, Minus, Search, Filter, Download, RefreshCw, ChevronRight,
  Link2, Unlink, Play, Pause, Trash2, Edit, Reply, Archive, ExternalLink,
  Hash, AtSign, Mail as MailIcon, Phone, Star, ThumbsUp, MessageCircle,
  Instagram, Twitter, Facebook, Linkedin, Youtube, Video, FileText, Copy, ShoppingBag, X,
  Upload, Sparkles, LayoutGrid, List, Check, MoreVertical, Paperclip, ChevronDown, ShieldCheck,
  Shield, CreditCard, ArrowUpDown, Layers, Workflow,
} from "lucide-react"
import { EmailTemplatesTab } from "./marketing/email-templates-tab"
import { EmailComposeTab } from "./marketing/email-compose-tab"
import { EmailJourneyTab } from "./marketing/email-journey-tab"
import { AgentMailTab } from "./marketing/agentmail-tab"
import {
  sendWhatsAppBroadcast,
  type TraditionalCampaign,
  type MarketingConnector,
  type AccountHealth,
  type MarketingQueue,
  type AnalyticsOverview,
  type DailyMetricPoint,
  type AnalyticsPostRow,
  type WhatsAppSender,
  type WhatsAppTemplate,
  type WhatsAppFlow,
  type WhatsAppGroup,
  type WhatsAppConversion,
  type SmsSenderId,
} from "@/lib/marketing-api"
import {
  adminApi, adminErrorMessage, AdminApiError, grantableRoles, ROLE_LABELS,
  type Whoami, type TenantMember, type TenantInvite,
} from "@/lib/admin-api"
import { scheduledPostsPath } from "@/lib/marketing-zernio-api"
import { ConnectionsPanel, ConnectPlatformDialog } from "./marketing/connect-flow"
import { SocialComposer } from "./marketing/post-composer"
import { CreateAdModal } from "./marketing/create-ad-modal"
import { LeadFormsPanel } from "./marketing/lead-forms-panel"
import { CampaignCreateForm } from "./marketing/campaign-create-form"
import {
  loadMarketing, writeMarketing, campaignsPath, socialAccountsPath, socialPostsPath,
  inboxMessagesPath, analyticsDailyPath, analyticsPostsPath, adCampaignsPath, commentAutomationsPath, whatsAppContactsPath, whatsAppBroadcastsPath,
} from "@/lib/marketing-api"
import { useMarketingLoad } from "@/lib/use-marketing-load"
import { describeMutationError } from "@/lib/marketing-state"
import { NotConnected, NoDataYet, StatValue } from "@/components/ui/not-connected"
import type { Loadable } from "@/lib/service-state"
import { MarketingAudiences } from "./marketing-audiences"
import { StaffAttributionTab } from "./marketing/staff-attribution-tab"

/** One-line message for a failed Loadable (server detail verbatim where given). */
function describeLoadableError(l: Loadable<unknown>, fallback: string): string {
  if (l.state === "unreachable") return "Service not running. Try again once it is connected."
  if (l.state === "denied") return `Not permitted (HTTP ${l.status}).`
  if (l.state === "error") return l.message || `${fallback} (HTTP ${l.status ?? "?"})`
  return fallback
}

const channelColors = ["#4ade80", "#60a5fa", "#f59e0b", "#a78bfa", "#f472b6"]

// ═══════════════════════════════════════════════════════════════════════════════
// ICON MAPS
// ═══════════════════════════════════════════════════════════════════════════════

const platformIcons: Record<string, React.ComponentType<{ className?: string; style?: React.CSSProperties }>> = {
  twitter: Twitter, instagram: Instagram, facebook: Facebook, linkedin: Linkedin,
  tiktok: Video, whatsapp: MessageCircle,
  youtube: Youtube, pinterest: Image, threads: AtSign, bluesky: Globe, telegram: Send,
  snapchat: Image, googlebusiness: Globe, reddit: MessageCircle, sms: Phone, slack: Hash, other: Globe,
}

const platformColors: Record<string, string> = {
  twitter: "#1DA1F2", instagram: "#E4405F", facebook: "#1877F2",
  linkedin: "#0A66C2", tiktok: "#000000", whatsapp: "#25D366",
  youtube: "#FF0000", pinterest: "#BD081C", threads: "#000000",
  bluesky: "#0085FF", telegram: "#0088CC", snapchat: "#FFFC00",
  googlebusiness: "#4285F4", reddit: "#FF4500", sms: "#10B981", slack: "#4A154B",
}

const statusColor: Record<string, string> = {
  draft: "border-gray-500/40 text-gray-400",
  active: "border-emerald-500/40 text-emerald-500",
  paused: "border-amber-500/40 text-amber-500",
  completed: "border-blue-500/40 text-blue-400",
  scheduled: "border-cyan-500/40 text-cyan-400",
  published: "border-emerald-500/40 text-emerald-500",
  failed: "border-red-500/40 text-red-400",
  DRAFT: "border-gray-500/40 text-gray-400",
  ACTIVE: "border-emerald-500/40 text-emerald-500",
  PAUSED: "border-amber-500/40 text-amber-500",
  COMPLETED: "border-blue-500/40 text-blue-400",
  SENT: "border-emerald-500/40 text-emerald-500",
  QUEUED: "border-cyan-500/40 text-cyan-400",
  SENDING: "border-amber-500/40 text-amber-500",
  UNREAD: "border-red-500/40 text-red-400",
  READ: "border-gray-500/40 text-gray-400",
  REPLIED: "border-emerald-500/40 text-emerald-500",
  ARCHIVED: "border-gray-500/40 text-gray-400",
  POSITIVE: "border-emerald-500/40 text-emerald-500",
  NEUTRAL: "border-gray-500/40 text-gray-400",
  NEGATIVE: "border-red-500/40 text-red-400",
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN MODULE
// ═══════════════════════════════════════════════════════════════════════════════

type MarketingTab =
  | "connections"
  | "campaigns" | "social-overview" | "social-composer" | "social-queues" | "social-scheduled"
  | "inbox-messages" | "inbox-comments" | "inbox-reviews" | "inbox-contacts"
  | "analytics"
  | "whatsapp-overview" | "whatsapp-templates" | "whatsapp-flows" | "whatsapp-groups" | "whatsapp-conversions" | "whatsapp-broadcasts" | "whatsapp-contacts"
  | "email-templates" | "email-compose" | "email-journeys" | "email-agentmail"
  | "sms-senders"
  | "team-users"
  | "ads" | "automations" | "traditional"
  | "platform-usage" | "platform-keys" | "platform-offboard"
  | "staff-attribution"

type IconType = React.ComponentType<{ className?: string }>
type NavLeaf = { key: MarketingTab; label: string; icon: IconType }
type NavGroup = { id: string; label: string; icon: IconType; children: NavLeaf[] }
type NavEntry = NavLeaf | NavGroup

const isGroup = (e: NavEntry): e is NavGroup => "children" in e

// Zernio-style grouped navigation: expandable sections + flat items, each
// icon-led, so the eye follows a vertical rail instead of scanning a row of
// look-alike horizontal buttons.
const MARKETING_NAV: NavEntry[] = [
  { key: "connections", label: "Connections", icon: Link2 },
  {
    id: "campaigns", label: "Campaigns", icon: Megaphone, children: [
      { key: "campaigns", label: "Overview", icon: BarChart3 },
      { key: "ads", label: "Ad Campaigns", icon: Target },
      { key: "traditional", label: "Traditional", icon: Radio },
    ],
  },
  {
    id: "social", label: "Posts", icon: Share2, children: [
      { key: "social-overview", label: "Overview", icon: LayoutGrid },
      { key: "social-composer", label: "Composer", icon: Send },
      { key: "social-queues", label: "Queues", icon: Clock },
      { key: "social-scheduled", label: "Scheduled", icon: Calendar },
    ],
  },
  {
    id: "inbox", label: "Inbox", icon: MessageSquare, children: [
      { key: "inbox-messages", label: "Messages", icon: MessageSquare },
      { key: "inbox-comments", label: "Comments", icon: MessageCircle },
      { key: "inbox-reviews", label: "Reviews", icon: Star },
      { key: "inbox-contacts", label: "Contacts", icon: Users },
    ],
  },
  { key: "analytics", label: "Analytics", icon: BarChart3 },
  {
    id: "whatsapp", label: "WhatsApp", icon: MessageCircle, children: [
      { key: "whatsapp-overview", label: "Overview", icon: Phone },
      { key: "whatsapp-templates", label: "Templates", icon: FileText },
      { key: "whatsapp-flows", label: "Flows", icon: RefreshCw },
      { key: "whatsapp-groups", label: "Groups", icon: Users },
      { key: "whatsapp-conversions", label: "Conversions", icon: Target },
      { key: "whatsapp-broadcasts", label: "Broadcasts", icon: Send },
      { key: "whatsapp-contacts", label: "Contacts", icon: UserCheck },
    ],
  },
  {
    id: "email", label: "Email", icon: Mail, children: [
      { key: "email-templates", label: "Templates & Builder", icon: FileText },
      { key: "email-compose", label: "Campaigns", icon: Send },
      { key: "email-journeys", label: "Templates Journey", icon: Workflow },
      { key: "email-agentmail", label: "AgentMail Integration", icon: Sparkles },
    ],
  },
  {
    id: "sms", label: "SMS", icon: Phone, children: [
      { key: "sms-senders", label: "Sender IDs", icon: MessageSquare },
    ],
  },
  { key: "team-users", label: "Users", icon: Users },
  { key: "automations", label: "Automations", icon: Zap },
  {
    id: "platform", label: "Platform", icon: Settings, children: [
      { key: "platform-usage", label: "Usage & Cost", icon: DollarSign },
      { key: "platform-keys", label: "API Keys", icon: Hash },
      { key: "platform-offboard", label: "Offboarding", icon: Trash2 },
    ],
  },
  { key: "staff-attribution", label: "Staff Attribution", icon: Layers },
]

const VALID_TABS = new Set<string>([
  "connections", "campaigns", "social-overview", "social-composer", "social-queues", "social-scheduled",
  "inbox-messages", "inbox-comments", "inbox-reviews", "inbox-contacts", "analytics",
  "whatsapp-overview", "whatsapp-templates", "whatsapp-flows", "whatsapp-groups", "whatsapp-conversions", "whatsapp-broadcasts", "whatsapp-contacts",
  "email-templates", "email-compose", "email-journeys", "email-agentmail", "sms-senders", "team-users", "ads", "automations", "traditional",
  "platform-usage", "platform-keys", "platform-offboard", "staff-attribution",
])

/** Tab and connect-result banner handed back by the in-app connect callback (?marketing_tab=...&connect=success|error). */
function readReturnParams(): { tab: MarketingTab | null; banner: { kind: "success" | "error"; message: string } | null } {
  if (typeof window === "undefined") return { tab: null, banner: null }
  const q = new URLSearchParams(window.location.search)
  const t = q.get("marketing_tab")
  const kind = q.get("connect")
  const msg = q.get("connect_msg")
  return {
    tab: t && VALID_TABS.has(t) ? (t as MarketingTab) : null,
    banner: (kind === "success" || kind === "error") && msg ? { kind, message: msg } : null,
  }
}

export function MarketingModule() {
  const [returnParams] = useState(readReturnParams)
  const [activeTab, setActiveTab] = useState<MarketingTab>(returnParams.tab ?? "campaigns")
  const [adsSubTab, setAdsSubTab] = useState<"campaigns" | "audiences" | "lead-forms">("campaigns")
  useEffect(() => {
    // Strip the one-shot banner params so a refresh does not replay them.
    if (typeof window === "undefined") return
    const u = new URL(window.location.href)
    if (u.searchParams.has("connect") || u.searchParams.has("connect_msg") || u.searchParams.has("marketing_tab")) {
      u.searchParams.delete("connect"); u.searchParams.delete("connect_msg"); u.searchParams.delete("marketing_tab")
      window.history.replaceState(null, "", `${u.pathname}${u.search}${u.hash}`)
    }
  }, [])
  // Track which nav groups are open; auto-open the group holding the active tab.
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {}
    for (const entry of MARKETING_NAV) {
      if (isGroup(entry)) init[entry.id] = entry.children.some((c) => c.key === (returnParams.tab ?? "campaigns"))
    }
    return init
  })

  const toggleGroup = (id: string) =>
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))

  const renderLeaf = (leaf: NavLeaf, nested: boolean) => {
    const Icon = leaf.icon
    const isActive = leaf.key === activeTab
    return (
      <button
        key={leaf.key}
        onClick={() => setActiveTab(leaf.key)}
        aria-current={isActive ? "page" : undefined}
        className={`group flex w-full items-center gap-2.5 rounded-lg py-2 pr-3 text-sm font-medium transition-colors ${nested ? "pl-9" : "pl-3"} ${
          isActive
            ? "bg-primary/10 text-primary"
            : "text-muted-foreground hover:bg-card hover:text-foreground"
        }`}
      >
        <Icon
          className={`h-4 w-4 shrink-0 transition-colors ${
            isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
          }`}
        />
        <span className="truncate">{leaf.label}</span>
        {isActive && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
      </button>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Megaphone className="h-5 w-5" />}
        title="Marketing"
        subtitle="Campaigns, social media, ads, and automation"
      />

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        {/* Left sub-nav — Zernio-style collapsible groups */}
        <nav className="w-full shrink-0 space-y-1 lg:sticky lg:top-4 lg:w-56">
          {MARKETING_NAV.map((entry) => {
            if (!isGroup(entry)) return renderLeaf(entry, false)
            const Icon = entry.icon
            const isOpen = expanded[entry.id]
            const hasActive = entry.children.some((c) => c.key === activeTab)
            return (
              <div key={entry.id}>
                <button
                  onClick={() => toggleGroup(entry.id)}
                  aria-expanded={isOpen}
                  className={`group flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
                    hasActive ? "text-foreground" : "text-muted-foreground hover:bg-card hover:text-foreground"
                  }`}
                >
                  <Icon
                    className={`h-4 w-4 shrink-0 ${
                      hasActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                    }`}
                  />
                  <span className="truncate">{entry.label}</span>
                  <ChevronRight
                    className={`ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform ${isOpen ? "rotate-90" : ""}`}
                  />
                </button>
                {isOpen && (
                  <div className="mt-0.5 space-y-0.5">
                    {entry.children.map((c) => renderLeaf(c, true))}
                  </div>
                )}
              </div>
            )
          })}
        </nav>

        {/* Content */}
        <div className="min-w-0 flex-1">
          {activeTab === "connections" && <ConnectionsPanel banner={returnParams.banner} />}
          {activeTab === "campaigns" && <InsightsCard module="marketing" title="Marketing briefing" className="mb-4" />}
          {activeTab === "campaigns" && <CampaignsTab onOpenAudiences={() => { setAdsSubTab("audiences"); setActiveTab("ads") }} />}
          {activeTab === "social-overview" && <PostsOverviewTab onOpenComposer={() => setActiveTab("social-composer")} />}
          {activeTab === "social-composer" && <SocialComposer onBackToOverview={() => setActiveTab("social-overview")} />}
          {activeTab === "social-queues" && <QueuesTab />}
          {activeTab === "social-scheduled" && <ScheduledPostsTab onOpenComposer={() => setActiveTab("social-composer")} />}
          {activeTab === "inbox-messages" && <SocialInboxTab kind="messages" />}
          {activeTab === "inbox-comments" && <SocialInboxTab kind="comments" />}
          {activeTab === "inbox-reviews" && <SocialInboxTab kind="reviews" />}
          {activeTab === "inbox-contacts" && <InboxContactsTab />}
          {activeTab === "analytics" && <SocialAnalyticsTab />}
          {activeTab === "whatsapp-overview" && <WhatsAppTab view="overview" />}
          {activeTab === "whatsapp-templates" && <WhatsAppTab view="templates" />}
          {activeTab === "whatsapp-flows" && <WhatsAppTab view="flows" />}
          {activeTab === "whatsapp-groups" && <WhatsAppTab view="groups" />}
          {activeTab === "whatsapp-conversions" && <WhatsAppTab view="conversions" />}
          {activeTab === "whatsapp-broadcasts" && <WhatsAppTab view="broadcasts" />}
          {activeTab === "email-templates" && (
            <EmailTemplatesTab
              onOpenComposerWithTemplate={() => setActiveTab("email-compose")}
            />
          )}
          {activeTab === "email-compose" && <EmailComposeTab />}
          {activeTab === "email-journeys" && (
            <EmailJourneyTab
              onOpenTemplateInBuilder={() => setActiveTab("email-templates")}
            />
          )}
          {activeTab === "email-agentmail" && <AgentMailTab />}
          {activeTab === "sms-senders" && <SmsSenderIdsTab />}
          {activeTab === "team-users" && <TeamUsersTab />}
          {activeTab === "ads" && <AdsTab initialSubTab={adsSubTab} />}
          {activeTab === "automations" && <AutomationsTab />}
          {activeTab === "platform-usage" && <UsageTab />}
          {activeTab === "platform-keys" && <ApiKeysTab />}
          {activeTab === "platform-offboard" && <OffboardTab />}
          {activeTab === "traditional" && <TraditionalTab />}
          {activeTab === "staff-attribution" && <StaffAttributionTab />}
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONNECTIONS TAB (brand connectors via Zernio)
// ═══════════════════════════════════════════════════════════════════════════════

// Brand color + glyph per connector. Recognizable brand chips without pulling
// in a brand-icon dependency; swap in exact logos later if desired.
const connectorVisual: Record<string, { color: string; icon: IconType }> = {
  tiktok: { color: "#111827", icon: Video },
  instagram: { color: "#E4405F", icon: Instagram },
  facebook: { color: "#1877F2", icon: Facebook },
  youtube: { color: "#FF0000", icon: Youtube },
  linkedin: { color: "#0A66C2", icon: Linkedin },
  twitter: { color: "#111827", icon: Twitter },
  threads: { color: "#111827", icon: AtSign },
  bluesky: { color: "#0085FF", icon: Globe },
  pinterest: { color: "#BD081C", icon: Image },
  reddit: { color: "#FF4500", icon: MessageSquare },
  googlebusiness: { color: "#4285F4", icon: Globe },
  snapchat: { color: "#FFFC00", icon: Image },
  telegram: { color: "#26A5E4", icon: Send },
  whatsapp: { color: "#25D366", icon: MessageCircle },
  shopify: { color: "#7AB55C", icon: ShoppingBag },
}

const LIGHT_BG_BRANDS = new Set(["snapchat"])

function BrandChip({ id, size = 40 }: { id: string; size?: number }) {
  const v = connectorVisual[id] ?? { color: "#6366f1", icon: Globe }
  const Icon = v.icon
  const dark = LIGHT_BG_BRANDS.has(id)
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-lg"
      style={{ width: size, height: size, backgroundColor: v.color }}
    >
      <Icon className={`h-5 w-5 ${dark ? "text-black" : "text-white"}`} />
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// PLATFORMS DROPDOWN WITH BRANDS (Zernio media_1789297905856.png)
// ═══════════════════════════════════════════════════════════════════════════════

const ALL_BRAND_PLATFORMS: Array<{
  id: string
  label: string
  renderIcon?: () => React.ReactNode
}> = [
  {
    id: "all",
    label: "All platforms",
  },
  {
    id: "tiktok",
    label: "TikTok",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded bg-black text-white">
        <svg className="h-3 w-3 fill-current" viewBox="0 0 24 24">
          <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-5.2 1.74 2.89 2.89 0 0 1 2.31-4.64c.298-.002.595.042.88.13V9.4a6.33 6.33 0 0 0-1-.08A6.34 6.34 0 0 0 3 15.66a6.34 6.34 0 0 0 10.82 4.46V12.1a8.16 8.16 0 0 0 5.77 2.3V10.9a4.85 4.85 0 0 1-3.77-4.21h3.77z"/>
        </svg>
      </span>
    ),
  },
  {
    id: "instagram",
    label: "Instagram",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded bg-gradient-to-tr from-[#f09433] via-[#dc2743] to-[#bc1888] text-white">
        <Instagram className="h-3.5 w-3.5" />
      </span>
    ),
  },
  {
    id: "facebook",
    label: "Facebook",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#1877F2] text-white">
        <Facebook className="h-3.5 w-3.5" />
      </span>
    ),
  },
  {
    id: "youtube",
    label: "YouTube",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded bg-[#FF0000] text-white">
        <Youtube className="h-3 w-3" />
      </span>
    ),
  },
  {
    id: "linkedin",
    label: "LinkedIn",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded bg-[#0A66C2] text-white">
        <Linkedin className="h-3 w-3" />
      </span>
    ),
  },
  {
    id: "twitter",
    label: "Twitter/X",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded bg-black text-white">
        <svg className="h-3 w-3 fill-current" viewBox="0 0 24 24">
          <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
        </svg>
      </span>
    ),
  },
  {
    id: "threads",
    label: "Threads",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-black text-white">
        <AtSign className="h-3.5 w-3.5" />
      </span>
    ),
  },
  {
    id: "pinterest",
    label: "Pinterest",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#BD081C] text-white font-serif font-bold text-[11px] leading-none">
        P
      </span>
    ),
  },
  {
    id: "reddit",
    label: "Reddit",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#FF4500] text-white">
        <MessageCircle className="h-3 w-3" />
      </span>
    ),
  },
  {
    id: "bluesky",
    label: "Bluesky",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center text-[#0085FF]">
        <svg className="h-4 w-4 fill-current" viewBox="0 0 24 24">
          <path d="M12 10.8c-1.087-2.114-4.046-6.053-6.798-7.995C2.566 1.01 0 1.956 0 5.4c0 3.444 1.343 11.233 2.143 13.067.8 1.834 3.085 2.133 4.857.733 1.772-1.4 3.2-4.267 5-7.4 1.8 3.133 3.228 6 5 7.4 1.772 1.4 4.057 1.1 4.857-.733.8-1.834 2.143-9.623 2.143-13.067 0-3.444-2.566-4.39-5.202-2.595C16.046 4.747 13.087 8.686 12 10.8z"/>
        </svg>
      </span>
    ),
  },
  {
    id: "googlebusiness",
    label: "GBP",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded bg-[#4285F4] text-white text-[9px] font-bold">
        G
      </span>
    ),
  },
  {
    id: "telegram",
    label: "Telegram",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#0088CC] text-white">
        <Send className="h-2.5 w-2.5" />
      </span>
    ),
  },
  {
    id: "snapchat",
    label: "Snapchat",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded bg-[#FFFC00] text-black text-xs">
        👻
      </span>
    ),
  },
]

type PlatformOption = {
  id: string
  label: string
  renderIcon?: () => React.ReactNode
}

function PlatformBrandDropdown({
  value,
  onChange,
  className = "",
  options = ALL_BRAND_PLATFORMS,
}: {
  value: string
  onChange: (val: string) => void
  className?: string
  options?: PlatformOption[]
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const selected =
    options.find((p) => p.id.toLowerCase() === (value || "all").toLowerCase()) ||
    options[0]

  return (
    <div className={`relative inline-block text-left ${className}`} ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="inline-flex items-center justify-between gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-accent focus:outline-none min-w-[130px]"
      >
        <span className="flex items-center gap-2 truncate">
          {selected.renderIcon ? selected.renderIcon() : null}
          <span className="truncate">{selected.label}</span>
        </span>
        <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute left-0 z-50 mt-1 w-56 rounded-lg border border-border bg-popover shadow-xl p-1 max-h-80 overflow-y-auto">
          {options.map((plat) => {
            const isSelected = plat.id.toLowerCase() === (value || "all").toLowerCase()
            return (
              <button
                key={plat.id}
                type="button"
                onClick={() => {
                  onChange(plat.id)
                  setOpen(false)
                }}
                className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-xs transition-colors ${
                  isSelected
                    ? "bg-accent text-foreground font-semibold"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <div className="flex h-5 w-5 shrink-0 items-center justify-center">
                    {plat.renderIcon ? plat.renderIcon() : null}
                  </div>
                  <span>{plat.label}</span>
                </div>
                {isSelected && <Check className="h-3.5 w-3.5 text-foreground shrink-0" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// Review-specific platform list (only platforms that support reviews)
const REVIEW_PLATFORMS: PlatformOption[] = [
  {
    id: "all",
    label: "All review platforms",
    renderIcon: () => <Globe className="h-3.5 w-3.5 text-muted-foreground" />,
  },
  {
    id: "googlebusiness",
    label: "Google Business (GBP)",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded bg-[#4285F4] text-white text-[9px] font-bold">
        G
      </span>
    ),
  },
  {
    id: "facebook",
    label: "Facebook Reviews",
    renderIcon: () => (
      <span className="flex h-5 w-5 items-center justify-center rounded bg-[#1877F2] text-white">
        <Facebook className="h-3 w-3" />
      </span>
    ),
  },
]

type ScheduleSortOption = {
  id: string
  label: string
  shortLabel?: string
  isMetric?: boolean
}

const SCHEDULE_SORT_TOP_OPTIONS: ScheduleSortOption[] = [
  { id: "scheduled-newest", label: "Scheduled (newest first)", shortLabel: "Scheduled (new)" },
  { id: "scheduled-oldest", label: "Scheduled (oldest first)", shortLabel: "Scheduled (old)" },
  { id: "created-newest", label: "Created (newest first)", shortLabel: "Created (new)" },
  { id: "created-oldest", label: "Created (oldest first)", shortLabel: "Created (old)" },
  { id: "status", label: "Status", shortLabel: "Status" },
  { id: "platform", label: "Platform", shortLabel: "Platform" },
]

const SCHEDULE_SORT_METRIC_OPTIONS: ScheduleSortOption[] = [
  { id: "engagement", label: "Most engagement (likes+comments+shares+saves)", shortLabel: "Most engagement", isMetric: true },
  { id: "likes", label: "Most likes", shortLabel: "Most likes", isMetric: true },
  { id: "comments", label: "Most comments", shortLabel: "Most comments", isMetric: true },
  { id: "shares", label: "Most shares", shortLabel: "Most shares", isMetric: true },
  { id: "views", label: "Most views", shortLabel: "Most views", isMetric: true },
  { id: "impressions", label: "Most impressions", shortLabel: "Most impressions", isMetric: true },
  { id: "reach", label: "Most reach", shortLabel: "Most reach", isMetric: true },
  { id: "saves", label: "Most saves", shortLabel: "Most saves", isMetric: true },
  { id: "clicks", label: "Most clicks", shortLabel: "Most clicks", isMetric: true },
]

function ScheduleSortDropdown({
  value,
  onChange,
  className = "",
}: {
  value: string
  onChange: (val: string) => void
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const allOpts = [...SCHEDULE_SORT_TOP_OPTIONS, ...SCHEDULE_SORT_METRIC_OPTIONS]
  const current = allOpts.find((o) => o.id === value) || SCHEDULE_SORT_TOP_OPTIONS[0]
  const displayLabel = current.shortLabel || current.label

  return (
    <div className={`relative inline-block text-left ${className}`} ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="inline-flex items-center justify-between gap-1.5 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-accent focus:outline-none min-w-[140px] shadow-2xs"
      >
        <span className="flex items-center gap-1.5 truncate">
          <ArrowUpDown className="h-3 w-3 shrink-0 text-muted-foreground" />
          <span className="truncate">{displayLabel}</span>
        </span>
        <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-1 w-64 rounded-lg border border-border bg-popover shadow-xl py-1 text-left">
          <div className="space-y-0.5 px-1">
            {SCHEDULE_SORT_TOP_OPTIONS.map((opt) => {
              const isSelected = opt.id === value
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => {
                    onChange(opt.id)
                    setOpen(false)
                  }}
                  className={`w-full text-left rounded-md px-3 py-1.5 text-xs transition-colors ${
                    isSelected
                      ? "bg-accent text-foreground font-semibold"
                      : "text-foreground hover:bg-accent/60"
                  }`}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>

          <div className="my-1.5 border-t border-border/80 px-3 pt-2 pb-1">
            <span className="text-[10px] font-semibold text-muted-foreground tracking-wider uppercase">
              BY METRIC · PUBLISHED ONLY
            </span>
          </div>

          <div className="space-y-0.5 px-1 max-h-56 overflow-y-auto">
            {SCHEDULE_SORT_METRIC_OPTIONS.map((opt) => {
              const isSelected = opt.id === value
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => {
                    onChange(opt.id)
                    setOpen(false)
                  }}
                  className={`w-full text-left rounded-md px-3 py-1.5 text-xs transition-colors ${
                    isSelected
                      ? "bg-accent text-foreground font-semibold"
                      : "text-foreground hover:bg-accent/60"
                  }`}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// EMAIL TABS & JOURNEYS (Modularized in ./marketing/email-templates-tab, etc.)
// ═══════════════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════════════
// PLATFORM TABS — usage/cost, scoped API keys, offboarding
// ═══════════════════════════════════════════════════════════════════════════════

const RESOURCE_GROUPS = [
  "publishing", "engagement", "messages", "contacts", "analytics",
  "ads", "telephony", "accounts", "billing", "webhooks",
]

function UsageTab() {
  const { value: usage, reload } = useMarketingLoad<{ profile_id: string | null; usage: Record<string, unknown> | null; restricted: boolean }>("/social/usage")
  const data = usage.state === "ready" ? usage.data : null

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h3 className="text-base font-semibold text-foreground">Usage &amp; Cost</h3>
        <p className="text-sm text-muted-foreground">This customer&apos;s share of your Zernio bill for the current cycle, by profile.</p>
      </div>
      {usage.state !== "ready" ? (
        <NotConnected loadable={usage} service="The marketing service" onRetry={reload} />
      ) : !data?.usage ? (
        <div className="rounded-lg border border-dashed border-border bg-card/40 p-10 text-center">
          <DollarSign className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <p className="font-medium text-foreground">No usage data</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Spend shows here once this tenant&apos;s profile has metered, connected accounts and Zernio is configured with a live API key.
          </p>
        </div>
      ) : (
        <Card className="border-border bg-card">
          <CardContent className="space-y-2 p-4">
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">Profile {data.profile_id}</p>
              {data.restricted && <Badge variant="outline" className="border-amber-500/40 text-amber-500">restricted key</Badge>}
            </div>
            {Object.entries(data.usage).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between border-b border-border/50 py-1.5 text-sm">
                <span className="text-muted-foreground">{k}</span>
                <span className="font-medium text-foreground">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function ApiKeysTab() {
  const [name, setName] = useState("")
  const [readOnly, setReadOnly] = useState(false)
  const [expiresIn, setExpiresIn] = useState("")
  const [disabled, setDisabled] = useState<string[]>([])
  const [creating, setCreating] = useState(false)
  const [created, setCreated] = useState<Record<string, any> | null>(null)
  const [error, setError] = useState<string | null>(null)

  const toggle = (g: string) => setDisabled((d) => (d.includes(g) ? d.filter((x) => x !== g) : [...d, g]))

  const submit = async () => {
    if (!name) return
    setCreating(true); setError(null); setCreated(null)
    const res = await writeMarketing<Record<string, any>>("POST", "/social/api-keys", {
      name,
      permission: readOnly ? "read" : undefined,
      disabled_resource_groups: disabled.length ? disabled : undefined,
      expires_in: expiresIn ? Number(expiresIn) : undefined,
    })
    if (res.ok && res.data) setCreated(res.data)
    else setError(describeMutationError(res.status, res.error))
    setCreating(false)
  }

  const keyStr = created ? String(created.apiKey?.key ?? created.key ?? "") : ""

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h3 className="text-base font-semibold text-foreground">Scoped API Keys</h3>
        <p className="text-sm text-muted-foreground">Mint a Zernio key limited to this customer&apos;s profile (access control — the rate limit stays with the team).</p>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3">
          <AlertTriangle className="h-4 w-4 shrink-0 text-red-400" /><p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {created ? (
        <Card className="border-emerald-500/30 bg-emerald-500/5">
          <CardHeader><CardTitle className="text-sm text-emerald-500">Key created — copy it now</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs text-muted-foreground">Zernio shows a key once. Store it securely; you can&apos;t retrieve it again.</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 truncate rounded-lg border border-border bg-card px-3 py-2 text-xs text-foreground">{keyStr || "(no key returned)"}</code>
              <Button size="sm" variant="outline" onClick={() => keyStr && navigator.clipboard.writeText(keyStr)}>
                <Copy className="mr-1 h-3.5 w-3.5" /> Copy
              </Button>
            </div>
            <Button size="sm" variant="ghost" onClick={() => { setCreated(null); setName("") }}>Create another</Button>
          </CardContent>
        </Card>
      ) : (
        <Card className="border-border bg-card">
          <CardContent className="space-y-4 p-4">
            <Input placeholder="Key name (e.g. acme-readonly)" value={name} onChange={(e) => setName(e.target.value)} />
            <div className="flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-2 text-sm text-foreground">
                <input type="checkbox" checked={readOnly} onChange={(e) => setReadOnly(e.target.checked)} /> Read-only
              </label>
              <label className="flex items-center gap-2 text-sm text-foreground">
                Expires in
                <Input type="number" value={expiresIn} onChange={(e) => setExpiresIn(e.target.value)} placeholder="days" className="w-24" />
              </label>
            </div>
            <div>
              <p className="mb-1.5 text-sm font-medium text-foreground">Disable resource groups (denylist)</p>
              <div className="flex flex-wrap gap-2">
                {RESOURCE_GROUPS.map((g) => (
                  <button
                    key={g}
                    onClick={() => toggle(g)}
                    className={`rounded-full border px-3 py-1 text-xs transition-colors ${disabled.includes(g) ? "border-red-500/40 bg-red-500/10 text-red-400" : "border-border text-muted-foreground hover:text-foreground"}`}
                  >
                    {g}
                  </button>
                ))}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">Any group disabled mints a <code>zrk_</code> key that 403s those calls; otherwise <code>sk_</code>.</p>
            </div>
            <Button onClick={submit} disabled={creating || !name}>
              {creating ? <><RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Creating…</> : <><Hash className="mr-2 h-4 w-4" /> Create key</>}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function OffboardTab() {
  const [ack, setAck] = useState(false)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setRunning(true); setError(null); setResult(null)
    const r = await writeMarketing<{ status: string; disconnected_accounts?: number }>("POST", "/social/profile/offboard")
    if (!r.ok) {
      setError(describeMutationError(r.status, r.error))
    } else {
      const res = r.data
      setResult(res?.status === "offboarded"
        ? `Offboarded — disconnected ${res.disconnected_accounts ?? 0} account(s) and deleted the profile.`
        : `Server response: ${res?.status ?? "no status returned"}`)
      setAck(false)
    }
    setRunning(false)
  }

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h3 className="text-base font-semibold text-foreground">Offboarding</h3>
        <p className="text-sm text-muted-foreground">Disconnect this customer&apos;s accounts and delete their Zernio profile.</p>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3">
          <AlertTriangle className="h-4 w-4 shrink-0 text-red-400" /><p className="text-sm text-red-400">{error}</p>
        </div>
      )}
      {result && (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3">
          <CheckCircle className="h-4 w-4 shrink-0 text-emerald-500" /><p className="text-sm text-emerald-500">{result}</p>
        </div>
      )}

      <Card className="border-red-500/30 bg-red-500/5">
        <CardHeader><CardTitle className="text-sm text-red-400">Danger zone</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            This disconnects every connected account for this tenant, then deletes its Zernio profile and clears the local map.
            Active accounts are disconnected first (Zernio blocks profile deletion otherwise). This cannot be undone.
          </p>
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            I understand this permanently offboards this customer.
          </label>
          <Button variant="destructive" disabled={!ack || running} onClick={run}>
            {running ? <><RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Offboarding…</> : <><Trash2 className="mr-2 h-4 w-4" /> Disconnect &amp; delete profile</>}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// CAMPAIGNS TAB
// ═══════════════════════════════════════════════════════════════════════════════

function CampaignsTab({ onOpenAudiences }: { onOpenAudiences?: () => void } = {}) {
  const [channel, setChannel] = useState<string>("all")
  const [showCreate, setShowCreate] = useState(false)
  const { value: camp, reload } = useMarketingLoad<any[]>(campaignsPath(channel !== "all" ? { channel } : undefined))
  const loading = camp.state === "loading"
  const campaigns: any[] = camp.state === "ready" ? camp.data : []

  const activeCount = campaigns.filter((c: any) => c.status === "active").length
  const totalSent = campaigns.reduce((sum: number, c: any) => sum + (c.total_sent || 0), 0)
  const totalConversions = campaigns.reduce((sum: number, c: any) => sum + (c.total_conversions || 0), 0)
  // Real conversion rate across all campaigns' sends; "No sends yet" when nothing has been sent.
  const conversionRate = totalSent > 0 ? `${((totalConversions / totalSent) * 100).toFixed(1)}%` : "No sends yet"

  const channelDistribution = Object.entries(
    campaigns.reduce((acc: Record<string, number>, c: any) => {
      acc[c.channel] = (acc[c.channel] ?? 0) + 1
      return acc
    }, {})
  ).map(([name, value]) => ({ name, value }))

  const campaignBudgets = campaigns
    .filter((c: any) => c.budget_zar > 0)
    .slice(0, 8)
    .map((c: any) => ({ campaign: c.name, budget: Number(c.budget_zar) }))

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="border-border bg-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Active Campaigns</p>
                <p className="text-2xl font-semibold text-foreground"><StatValue loadable={camp}>{() => activeCount}</StatValue></p>
              </div>
              <div className="rounded-lg bg-emerald-500/10 p-2"><Megaphone className="h-5 w-5 text-emerald-500" /></div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border bg-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Total Sent</p>
                <p className="text-2xl font-semibold text-foreground"><StatValue loadable={camp}>{() => totalSent.toLocaleString()}</StatValue></p>
              </div>
              <div className="rounded-lg bg-blue-500/10 p-2"><Send className="h-5 w-5 text-blue-500" /></div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border bg-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Conversions</p>
                <p className="text-2xl font-semibold text-foreground"><StatValue loadable={camp}>{() => totalConversions.toLocaleString()}</StatValue></p>
              </div>
              <div className="rounded-lg bg-purple-500/10 p-2"><UserCheck className="h-5 w-5 text-purple-500" /></div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border bg-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Conversion rate</p>
                <p className="text-2xl font-semibold text-foreground"><StatValue loadable={camp}>{() => conversionRate}</StatValue></p>
              </div>
              <div className="rounded-lg bg-amber-500/10 p-2"><TrendingUp className="h-5 w-5 text-amber-500" /></div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Channel Filter + Create */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          {["all", "email", "social", "search", "display", "sms"].map((ch) => (
            <Button key={ch} size="sm" variant={channel === ch ? "secondary" : "outline"} onClick={() => setChannel(ch)}>
              {ch.charAt(0).toUpperCase() + ch.slice(1)}
            </Button>
          ))}
        </div>
        <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
          <Plus className="mr-2 h-4 w-4" /> New Campaign
        </Button>
      </div>

      {/* Create Form */}
      {showCreate && (
        <CampaignCreateForm
          onCancel={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); reload() }}
          onOpenAudiences={onOpenAudiences}
        />
      )}

      {/* Campaign Table */}
      <Card className="border-border bg-card">
        <CardHeader><CardTitle>Campaigns</CardTitle></CardHeader>
        <CardContent>
          {camp.state !== "ready" ? (
            <NotConnected loadable={camp} service="The marketing service" onRetry={reload} />
          ) : campaigns.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">No campaigns yet. Use New Campaign to create one.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px]">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Name</th>
                    <th className="py-2 pr-4 font-medium">Channel</th>
                    <th className="py-2 pr-4 font-medium">Audience</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 pr-4 font-medium">Budget</th>
                    <th className="py-2 pr-4 font-medium">Sent</th>
                    <th className="py-2 pr-4 font-medium">Conversions</th>
                    <th className="py-2 font-medium">Dates</th>
                  </tr>
                </thead>
                <tbody>
                  {campaigns.map((c: any) => (
                    <tr key={c.id} className="border-b border-border/60 text-sm">
                      <td className="py-3 pr-4 text-foreground font-medium">{c.name}</td>
                      <td className="py-3 pr-4 text-muted-foreground">{c.channel}</td>
                      <td className="py-3 pr-4 text-muted-foreground">{c.audience_name ? `${c.audience_name}${typeof c.audience_size === "number" ? ` (${c.audience_size})` : ""}` : "—"}</td>
                      <td className="py-3 pr-4"><Badge variant="outline" className={statusColor[c.status] || "border-muted text-muted-foreground"}>{c.status}</Badge></td>
                      <td className="py-3 pr-4 text-muted-foreground">{c.budget_zar ? `R ${Number(c.budget_zar).toLocaleString()}` : "—"}</td>
                      <td className="py-3 pr-4 text-muted-foreground">{c.total_sent || 0}</td>
                      <td className="py-3 pr-4 text-muted-foreground">{c.total_conversions || 0}</td>
                      <td className="py-3 text-muted-foreground text-xs">{c.start_date ? new Date(c.start_date).toLocaleDateString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Channel Distribution + Budget */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Channel Distribution</CardTitle></CardHeader>
          <CardContent>{channelDistribution.length === 0 ? <NoDataYet message={camp.state === "ready" ? "No campaigns yet" : "No data to chart"} /> : <div className="h-64"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={channelDistribution} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>{channelDistribution.map((e, i) => <Cell key={i} fill={channelColors[i % channelColors.length]} />)}</Pie><Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} /></PieChart></ResponsiveContainer></div>}</CardContent>
        </Card>
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Budget by Campaign</CardTitle></CardHeader>
          <CardContent>{campaignBudgets.length === 0 ? <NoDataYet message={camp.state === "ready" ? "No campaign has a budget set" : "No data to chart"} /> : <div className="h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={campaignBudgets}><CartesianGrid strokeDasharray="3 3" stroke="#404040" /><XAxis dataKey="campaign" tick={{ fill: "#737373", fontSize: 10 }} /><YAxis tick={{ fill: "#737373", fontSize: 12 }} /><Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} /><Bar dataKey="budget" fill="#4ade80" name="Budget (R)" /></BarChart></ResponsiveContainer></div>}</CardContent>
        </Card>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// SOCIAL COMPOSER TAB
// ═══════════════════════════════════════════════════════════════════════════════

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

function QueuesTab() {
  const { value: qLoad, reload: load } = useMarketingLoad<{ queues: MarketingQueue[] }>("/social/queues")
  const queues: MarketingQueue[] = qLoad.state === "ready" ? (qLoad.data?.queues ?? []) : []
  const [showCreate, setShowCreate] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [tz, setTz] = useState(() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone } catch { return "UTC" } })
  const [days, setDays] = useState<number[]>([])
  const [time, setTime] = useState("09:00")
  const [slots, setSlots] = useState<{ day: number; time: string }[]>([])
  const [saving, setSaving] = useState(false)

  const toggleDay = (d: number) => setDays((ds) => (ds.includes(d) ? ds.filter((x) => x !== d) : [...ds, d]))
  const addSlots = () => {
    if (days.length === 0 || !time) return
    setSlots((s) => {
      const next = [...s]
      for (const d of days) if (!next.some((x) => x.day === d && x.time === time)) next.push({ day: d, time })
      return next.sort((a, b) => a.day - b.day || a.time.localeCompare(b.time))
    })
    setDays([])
  }
  const removeSlot = (i: number) => setSlots((s) => s.filter((_, idx) => idx !== i))

  const resetForm = () => { setName(""); setDescription(""); setDays([]); setTime("09:00"); setSlots([]) }

  const save = async () => {
    if (!name || slots.length === 0) return
    setSaving(true); setError(null)
    const r = await writeMarketing("POST", "/social/queues", { name, description: description || undefined, timezone: tz, slots })
    if (r.ok) { setShowCreate(false); resetForm(); load() }
    else setError(describeMutationError(r.status, r.error))
    setSaving(false)
  }

  const toggleStatus = async (q: MarketingQueue) => {
    setError(null)
    const r = await writeMarketing("PATCH", `/social/queues/${q.id}`, { status: q.status === "active" ? "paused" : "active" })
    if (!r.ok) setError(describeMutationError(r.status, r.error))
    else load()
  }
  const remove = async (id: string) => {
    setError(null)
    const r = await writeMarketing("DELETE", `/social/queues/${id}`)
    if (!r.ok) setError(describeMutationError(r.status, r.error))
    else load()
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-foreground">Queues</h3>
          <p className="text-sm text-muted-foreground">Recurring posting schedules — posts drop into the next open slot.</p>
        </div>
        <Button
          size="sm"
          onClick={() => setShowCreate((v) => !v)}
          className="bg-[#EA3829] hover:bg-[#d02e20] text-white font-medium text-xs shadow-sm"
        >
          <Plus className="mr-1.5 h-4 w-4" /> New queue
        </Button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3">
          <AlertTriangle className="h-4 w-4 shrink-0 text-red-400" /><p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {showCreate && (
        <Card className="border-border bg-card shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Create queue</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input
              placeholder="Queue name (e.g. Morning Posts)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="text-xs bg-background border-border"
            />
            <Input
              placeholder="Description (optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="text-xs bg-background border-border"
            />
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Timezone</label>
              <select
                value={tz}
                onChange={(e) => setTz(e.target.value)}
                className="w-full sm:w-80 rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none"
              >
                <option value="Africa/Johannesburg">Africa/Johannesburg (SAST, UTC+2)</option>
                <option value="UTC">UTC (Universal Coordinated Time)</option>
                <option value="Africa/Nairobi">Africa/Nairobi (EAT, UTC+3)</option>
                <option value="Africa/Lagos">Africa/Lagos (WAT, UTC+1)</option>
                <option value="Africa/Cairo">Africa/Cairo (EEST, UTC+2)</option>
                <option value="Europe/London">Europe/London (GMT/BST)</option>
                <option value="America/New_York">America/New_York (EST/EDT)</option>
              </select>
            </div>
            <div className="rounded-lg border border-border bg-background/50 p-4">
              <p className="mb-2.5 text-xs font-medium text-foreground">Add slots</p>
              <div className="mb-3 flex flex-wrap gap-1.5">
                {WEEKDAYS.map((w, d) => {
                  const isSelected = days.includes(d)
                  return (
                    <button
                      key={w}
                      type="button"
                      onClick={() => toggleDay(d)}
                      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                        isSelected
                          ? "border-[#EA3829] bg-[#EA3829] text-white shadow-xs"
                          : "border-border bg-background text-muted-foreground hover:border-foreground/30 hover:text-foreground"
                      }`}
                    >
                      {w}
                    </button>
                  )
                })}
              </div>
              <div className="flex items-center gap-2">
                <Input
                  type="time"
                  value={time}
                  onChange={(e) => setTime(e.target.value)}
                  className="w-32 text-xs bg-background border-border"
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={addSlots}
                  disabled={days.length === 0}
                  className="text-xs border-border bg-background"
                >
                  Add slots
                </Button>
              </div>
              {slots.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5 pt-2 border-t border-border/60">
                  {slots.map((s, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-2.5 py-0.5 text-xs text-foreground shadow-2xs"
                    >
                      {WEEKDAYS[s.day]} {s.time}
                      <button onClick={() => removeSlot(i)} className="text-muted-foreground hover:text-red-400">
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 pt-1">
              <Button
                size="sm"
                onClick={save}
                disabled={saving || !name || slots.length === 0}
                className="bg-[#EA3829] hover:bg-[#d02e20] text-white font-medium text-xs px-4 h-9 shadow-sm"
              >
                {saving ? <><RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" /> Creating…</> : "Create queue"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-xs text-muted-foreground hover:text-foreground h-9 px-3"
                onClick={() => { setShowCreate(false); resetForm() }}
              >
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {qLoad.state !== "ready" ? (
        <NotConnected loadable={qLoad} service="The marketing service" onRetry={load} />
      ) : queues.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-card/40 p-10 text-center">
          <Clock className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <p className="font-medium text-foreground">No queues yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">Create a queue with weekly time slots, then choose &ldquo;Queue&rdquo; in the Composer to drop posts into the next open slot.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {queues.map((q) => (
            <Card key={q.id} className="border-border bg-card">
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex items-center gap-2">
                      <p className="font-medium text-foreground">{q.name}</p>
                      <Badge variant="outline" className={q.status === "active" ? "border-emerald-500/40 text-emerald-500" : "border-amber-500/40 text-amber-500"}>{q.status}</Badge>
                    </div>
                    {q.description && <p className="mb-1 text-xs text-muted-foreground">{q.description}</p>}
                    <div className="flex flex-wrap gap-1.5">
                      {(q.slots || []).map((s, i) => (
                        <span key={i} className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">{WEEKDAYS[s.day]} {s.time}</span>
                      ))}
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">
                      {q.timezone} · {q.next_slot ? `next slot ${new Date(q.next_slot).toLocaleString()}` : "no upcoming slot"}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button size="sm" variant="ghost" onClick={() => toggleStatus(q)}>{q.status === "active" ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}</Button>
                    <Button size="sm" variant="ghost" className="text-red-400 hover:text-red-300" onClick={() => remove(q.id)}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function ScheduledPostsTab({ onOpenComposer }: { onOpenComposer?: () => void } = {}) {
  const [listView, setListView] = useState<"scheduled" | "draft" | "failed">("scheduled")
  // Scheduled view reads the dedicated endpoint (scheduled + queued, soonest first); drafts/failed use the filtered list.
  const listPath = listView === "scheduled" ? scheduledPostsPath() : `/social/posts?status=${listView}&sort=created_desc&limit=200`
  const { value: postsLoad, reload: load } = useMarketingLoad<{ posts?: any[]; provider_error?: string | null } | any[]>(listPath)
  const loading = postsLoad.state === "loading"
  const [removed, setRemoved] = useState<string[]>([])
  const rawPosts: any[] = postsLoad.state === "ready" ? (Array.isArray(postsLoad.data) ? postsLoad.data : postsLoad.data?.posts ?? []) : []
  const posts: any[] = rawPosts.filter((p: any) => !removed.includes(p.id))
  const [cancelling, setCancelling] = useState<string | null>(null)
  const [cancelError, setCancelError] = useState<string | null>(null)
  const [platformFilter, setPlatformFilter] = useState("all")
  const [dateFilter, setDateFilter] = useState("all")
  const [sortBy, setSortBy] = useState("scheduled-newest")
  const [viewMode, setViewMode] = useState<"grid" | "list" | "calendar">("grid")
  const [zoomScale, setZoomScale] = useState(4)

  const cancel = async (id: string) => {
    setCancelling(id)
    setCancelError(null)
    const r = await writeMarketing("DELETE", `/social/posts/${id}`)
    if (r.ok) setRemoved((prev) => [...prev, id])
    else setCancelError(describeMutationError(r.status, r.error))
    setCancelling(null)
  }

  const filteredPosts = useMemo(() => {
    const result = posts.filter((p) => {
      if (platformFilter !== "all" && !p.platforms?.some((plat: string) => plat.toLowerCase() === platformFilter.toLowerCase())) return false
      if (dateFilter !== "all") {
        const t = p.scheduled_for ? new Date(p.scheduled_for).getTime() : NaN
        if (!Number.isFinite(t)) return false
        const now = new Date()
        const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
        const day = 86_400_000
        if (dateFilter === "today" && !(t >= startOfDay && t < startOfDay + day)) return false
        if (dateFilter === "this-week" && !(t >= startOfDay && t < startOfDay + 7 * day)) return false
        if (dateFilter === "this-month" && !(t >= startOfDay && t < startOfDay + 31 * day)) return false
      }
      return true
    })

    result.sort((a, b) => {
      if (sortBy === "scheduled-newest") {
        return new Date(b.scheduled_for || 0).getTime() - new Date(a.scheduled_for || 0).getTime()
      }
      if (sortBy === "scheduled-oldest") {
        return new Date(a.scheduled_for || 0).getTime() - new Date(b.scheduled_for || 0).getTime()
      }
      if (sortBy === "created-newest") {
        return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
      }
      if (sortBy === "created-oldest") {
        return new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime()
      }
      if (sortBy === "status") {
        return (a.status || "").localeCompare(b.status || "")
      }
      if (sortBy === "platform") {
        return (a.platforms?.[0] || "").localeCompare(b.platforms?.[0] || "")
      }
      return 0
    })

    return result
  }, [posts, platformFilter, dateFilter, sortBy])

  const gridColsClass =
    zoomScale === 1
      ? "grid-cols-1"
      : zoomScale === 2
      ? "grid-cols-1 sm:grid-cols-2"
      : zoomScale === 3
      ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
      : zoomScale === 4
      ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4"
      : zoomScale === 5
      ? "grid-cols-1 sm:grid-cols-3 lg:grid-cols-5"
      : "grid-cols-1 sm:grid-cols-3 lg:grid-cols-6"

  return (
    <div className="space-y-5">
      {/* Top Header matching Zernio Posts journey */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-foreground">Scheduled posts</h2>
          <p className="text-xs text-muted-foreground">Manage your upcoming scheduled social posts and queue calendar</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={onOpenComposer}
            className="bg-[#EA3829] hover:bg-[#d02e20] text-white font-medium text-xs px-4 h-9 shadow-sm"
          >
            <Plus className="mr-1.5 h-4 w-4" /> Create post
          </Button>
          <Button size="sm" variant="outline" className="text-xs h-9 border-border bg-card" disabled title="CSV import is not available yet: there is no backend endpoint for it">
            <Upload className="mr-1.5 h-3.5 w-3.5" /> Import CSV
          </Button>
          <Button size="sm" variant="ghost" onClick={load} disabled={loading} className="h-9 px-2.5 text-muted-foreground hover:text-foreground">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {/* Filters Bar matching Zernio screenshot */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        <div className="flex flex-wrap items-center gap-2">
          {/* Platform */}
          <PlatformBrandDropdown
            value={platformFilter}
            onChange={setPlatformFilter}
          />

          {/* Dates */}
          <select
            value={dateFilter}
            onChange={(e) => setDateFilter(e.target.value)}
            className="rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-foreground focus:outline-none"
          >
            <option value="all">All dates</option>
            <option value="today">Today</option>
            <option value="this-week">This week</option>
            <option value="this-month">This month</option>
          </select>
        </div>

        {/* Right Controls: Sort & Views (media_1789300191753.png) */}
        <div className="flex items-center gap-2">
          <ScheduleSortDropdown
            value={sortBy}
            onChange={setSortBy}
          />

          {/* View Mode Buttons */}
          <div className="flex items-center rounded-md border border-border bg-card p-0.5">
            <button
              onClick={() => setViewMode("grid")}
              className={`rounded p-1.5 transition-colors ${viewMode === "grid" ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              title="Grid view"
            >
              <LayoutGrid className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={`rounded p-1.5 transition-colors ${viewMode === "list" ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              title="List view"
            >
              <List className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setViewMode("calendar")}
              className={`rounded p-1.5 transition-colors ${viewMode === "calendar" ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              title="Calendar view"
            >
              <Calendar className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Zoom scale indicator matching screenshot */}
          <div className="hidden sm:flex items-center gap-1 text-xs text-muted-foreground border border-border bg-card rounded-md px-2 py-1">
            <button onClick={() => setZoomScale((z) => Math.max(1, z - 1))} className="hover:text-foreground p-0.5">-</button>
            <span className="font-mono text-[11px] px-1">{zoomScale}</span>
            <button onClick={() => setZoomScale((z) => Math.min(6, z + 1))} className="hover:text-foreground p-0.5">+</button>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1 rounded-lg border border-border bg-card/60 p-1 text-xs w-fit">
        {([["scheduled", "Scheduled and queued"], ["draft", "Drafts"], ["failed", "Failed"]] as const).map(([k, label]) => (
          <button key={k} type="button" onClick={() => setListView(k)} className={`rounded-md px-3 py-1.5 font-medium ${listView === k ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>{label}</button>
        ))}
      </div>
      {cancelError && <p className="text-sm text-red-400" role="alert">{cancelError}</p>}
      {postsLoad.state === "ready" && !Array.isArray(postsLoad.data) && postsLoad.data?.provider_error && (
        <p className="text-xs text-amber-500" role="status">Provider status could not be checked: {postsLoad.data.provider_error}</p>
      )}
      {postsLoad.state !== "ready" ? (
        <NotConnected loadable={postsLoad} service="The marketing service" onRetry={load} />
      ) : filteredPosts.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card/30 py-16 px-6 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-muted/60 text-muted-foreground">
            <Calendar className="h-6 w-6" />
          </div>
          <h3 className="text-base font-bold text-foreground">{listView === "scheduled" ? "Nothing scheduled" : listView === "draft" ? "No drafts" : "No failed posts"}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{listView === "scheduled" ? "Create a scheduled post in the composer or add a slot in your queue" : listView === "draft" ? "Drafts saved from the composer appear here" : "Posts the provider rejected appear here with the reason"}</p>
          <Button
            onClick={onOpenComposer}
            className="mt-5 bg-[#EA3829] hover:bg-[#d02e20] text-white font-medium text-xs px-5 h-9 shadow-sm"
          >
            <Plus className="mr-1.5 h-4 w-4" /> Create post
          </Button>
        </div>
      ) : viewMode === "list" ? (
        <Card className="border-border bg-card shadow-sm">
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full min-w-[650px] text-xs">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground bg-muted/30">
                  <th className="px-4 py-3 font-semibold">Scheduled Time</th>
                  <th className="px-4 py-3 font-semibold">Platforms</th>
                  <th className="px-4 py-3 font-semibold">Post Content</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredPosts.map((p) => (
                  <tr key={p.id} className="hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3 whitespace-nowrap">
                      <Badge variant="outline" className="border-cyan-500/40 text-cyan-400 text-[11px] font-mono">
                        <Clock className="mr-1 h-3 w-3" />
                        {p.scheduled_for ? new Date(p.scheduled_for).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        {p.platforms?.map((plat: string) => {
                          const Icon = platformIcons[plat.toLowerCase()] || Globe
                          return (
                            <span
                              key={plat}
                              className="flex h-5 w-5 items-center justify-center rounded-full border text-[10px]"
                              style={{
                                borderColor: (platformColors[plat.toLowerCase()] || "#888") + "40",
                                color: platformColors[plat.toLowerCase()] || "#888",
                                backgroundColor: (platformColors[plat.toLowerCase()] || "#888") + "15",
                              }}
                              title={plat}
                            >
                              <Icon className="h-3 w-3" />
                            </span>
                          )
                        })}
                      </div>
                    </td>
                    <td className="px-4 py-3 max-w-sm">
                      <p className="line-clamp-2 text-foreground font-medium">{p.content}</p>
                      {p.publish_error && <p className="mt-0.5 text-[11px] text-red-400">{p.publish_error}</p>}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-[11px]">
                      <Badge variant="outline" className={statusColor[String(p.status).toLowerCase()] || "border-muted text-muted-foreground"}>{p.queue_id ? "queued" : p.status}</Badge>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-red-400 hover:text-red-300 text-xs"
                        disabled={cancelling === p.id}
                        onClick={() => cancel(p.id)}
                      >
                        {cancelling === p.id ? <RefreshCw className="h-3 w-3 animate-spin" /> : <><Trash2 className="mr-1 h-3 w-3" /> Cancel</>}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : viewMode === "calendar" ? (
        <Card className="border-border bg-card p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground">Upcoming Schedule Calendar</span>
            <Badge variant="outline" className="border-cyan-500/30 text-cyan-400 text-[10px]">
              {filteredPosts.length} posts scheduled
            </Badge>
          </div>
          <div className="grid grid-cols-7 gap-2">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => (
              <div key={day} className="text-center text-[11px] font-semibold text-muted-foreground pb-1">
                {day}
              </div>
            ))}
            {Array.from({ length: new Date().getDay() }).map((_, i) => <div key={`pad-${i}`} />)}
            {Array.from({ length: 28 }).map((_, idx) => {
              const cellDate = new Date(Date.now() + idx * 86400 * 1000)
              const cellPosts = filteredPosts.filter((p) => {
                if (!p.scheduled_for) return false
                const d = new Date(p.scheduled_for)
                return d.getFullYear() === cellDate.getFullYear() && d.getDate() === cellDate.getDate() && d.getMonth() === cellDate.getMonth()
              })
              return (
                <div
                  key={idx}
                  className="min-h-[90px] rounded-lg border border-border/70 bg-background/50 p-1.5 flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                    <span>{cellDate.toLocaleDateString([], { month: "short", day: "numeric" })}</span>
                    {cellPosts.length > 0 && (
                      <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
                    )}
                  </div>
                  <div className="space-y-1 mt-1 flex-1">
                    {cellPosts.map((p) => (
                      <div
                        key={p.id}
                        className="rounded border border-border/80 bg-card p-1 text-[10px] leading-tight text-foreground shadow-2xs hover:border-primary/50 transition-colors"
                      >
                        <div className="flex items-center gap-1 font-mono text-[9px] text-cyan-400">
                          <Clock className="h-2.5 w-2.5" />
                          {new Date(p.scheduled_for).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </div>
                        <p className="line-clamp-1 mt-0.5 text-muted-foreground">{p.content}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      ) : (
        /* Grid View */
        <div className={`grid gap-4 ${gridColsClass}`}>
          {filteredPosts.map((post: any) => (
            <Card key={post.id} className="border-border bg-card shadow-xs flex flex-col justify-between">
              <CardContent className="p-4 flex-1 flex flex-col justify-between">
                <div>
                  <div className="mb-2.5 flex items-center justify-between gap-2">
                    <Badge variant="outline" className="border-cyan-500/40 text-cyan-400 text-[11px] font-mono">
                      <Clock className="mr-1 h-3 w-3" />
                      {post.scheduled_for ? new Date(post.scheduled_for).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                    </Badge>
                    <div className="flex items-center gap-1">
                      {(post.platforms || []).map((plat: string) => {
                        const Icon = platformIcons[plat.toLowerCase()] || Globe
                        return (
                          <span
                            key={plat}
                            className="flex h-5 w-5 items-center justify-center rounded-full border text-[10px]"
                            style={{
                              borderColor: (platformColors[plat.toLowerCase()] || "#888") + "40",
                              color: platformColors[plat.toLowerCase()] || "#888",
                              backgroundColor: (platformColors[plat.toLowerCase()] || "#888") + "15",
                            }}
                            title={plat}
                          >
                            <Icon className="h-3 w-3" />
                          </span>
                        )
                      })}
                    </div>
                  </div>
                  <p className="line-clamp-3 text-xs text-foreground font-medium leading-relaxed">{post.content}</p>
                </div>
                <div className="mt-4 pt-3 border-t border-border/60 flex items-center justify-between text-xs">
                  <span className="text-[11px] text-muted-foreground truncate max-w-[160px]">
                    {post.publish_error ? <span className="text-red-400" title={post.publish_error}>{post.publish_error}</span> : (post.queue_id ? "queued" : post.status)}
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-red-400 hover:text-red-300 text-xs"
                    disabled={cancelling === post.id}
                    onClick={() => cancel(post.id)}
                  >
                    {cancelling === post.id ? <RefreshCw className="h-3 w-3 animate-spin" /> : <><Trash2 className="mr-1 h-3 w-3" /> Cancel</>}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// POSTS OVERVIEW TAB (Zernio Screenshot & Brand Safety)
// ═══════════════════════════════════════════════════════════════════════════════

function PostsOverviewTab({ onOpenComposer }: { onOpenComposer: () => void }) {
  const { value: postsLoad, reload } = useMarketingLoad<any[]>(socialPostsPath())
  const { value: accountsLoad } = useMarketingLoad<any[]>(socialAccountsPath())
  const posts: any[] = postsLoad.state === "ready" ? postsLoad.data : []
  const [postStatusFilter, setPostStatusFilter] = useState("all")
  const [platformFilter, setPlatformFilter] = useState("all")
  const [dateFilter, setDateFilter] = useState("all")
  const [sortBy, setSortBy] = useState("scheduled-newest")
  const [viewMode, setViewMode] = useState<"grid" | "list" | "calendar">("grid")
  const [zoomScale, setZoomScale] = useState(4)

  const filteredPosts = useMemo(() => {
    const result = posts.filter((p) => {
      if (postStatusFilter !== "all" && p.status?.toLowerCase() !== postStatusFilter.toLowerCase()) return false
      if (platformFilter !== "all" && !p.platforms?.some((plat: string) => plat.toLowerCase() === platformFilter.toLowerCase())) return false
      if (dateFilter !== "all") {
        const t = new Date(p.scheduled_for || p.published_at || p.created_at || 0).getTime()
        if (!Number.isFinite(t) || t === 0) return false
        const now = new Date()
        const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
        const day = 86_400_000
        if (dateFilter === "today" && !(t >= startOfDay && t < startOfDay + day)) return false
        if (dateFilter === "this-week" && !(t >= startOfDay - 6 * day && t < startOfDay + day)) return false
        if (dateFilter === "this-month" && !(t >= startOfDay - 30 * day && t < startOfDay + day)) return false
      }
      return true
    })

    result.sort((a, b) => {
      if (sortBy === "scheduled-newest") {
        return new Date(b.scheduled_for || 0).getTime() - new Date(a.scheduled_for || 0).getTime()
      }
      if (sortBy === "scheduled-oldest") {
        return new Date(a.scheduled_for || 0).getTime() - new Date(b.scheduled_for || 0).getTime()
      }
      if (sortBy === "created-newest") {
        return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
      }
      if (sortBy === "created-oldest") {
        return new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime()
      }
      if (sortBy === "status") {
        return (a.status || "").localeCompare(b.status || "")
      }
      if (sortBy === "platform") {
        return (a.platforms?.[0] || "").localeCompare(b.platforms?.[0] || "")
      }
      if (sortBy === "engagement") {
        const engA = (a.likes || 0) + (a.comments || 0) + (a.shares || 0)
        const engB = (b.likes || 0) + (b.comments || 0) + (b.shares || 0)
        return engB - engA
      }
      if (sortBy === "likes") return (b.likes || 0) - (a.likes || 0)
      if (sortBy === "comments") return (b.comments || 0) - (a.comments || 0)
      if (sortBy === "shares") return (b.shares || 0) - (a.shares || 0)
      if (sortBy === "views") return (b.views || 0) - (a.views || 0)
      if (sortBy === "impressions") return (b.impressions || 0) - (a.impressions || 0)
      if (sortBy === "reach") return (b.reach || 0) - (a.reach || 0)
      if (sortBy === "saves") return (b.saves || 0) - (a.saves || 0)
      if (sortBy === "clicks") return (b.clicks || 0) - (a.clicks || 0)
      return 0
    })

    return result
  }, [posts, postStatusFilter, platformFilter, sortBy])

  const gridColsClass =
    zoomScale === 1
      ? "grid-cols-1"
      : zoomScale === 2
      ? "grid-cols-1 sm:grid-cols-2"
      : zoomScale === 3
      ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
      : zoomScale === 4
      ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4"
      : zoomScale === 5
      ? "grid-cols-1 sm:grid-cols-3 lg:grid-cols-5"
      : "grid-cols-1 sm:grid-cols-3 lg:grid-cols-6"

  return (
    <div className="space-y-5">
      {/* Top Header matching media_1789288661301.png */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-foreground">Posts</h2>
          <p className="text-xs text-muted-foreground">Manage your scheduled and published content</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={onOpenComposer}
            className="bg-[#EA3829] hover:bg-[#d02e20] text-white font-medium text-xs px-4 h-9 shadow-sm"
          >
            <Plus className="mr-1.5 h-4 w-4" /> Create post
          </Button>
          <Button size="sm" variant="outline" className="text-xs h-9 border-border bg-card">
            <Upload className="mr-1.5 h-3.5 w-3.5" /> Import CSV
          </Button>
        </div>
      </div>

      {/* Connected accounts (real, from /social/accounts) */}
      <div className="rounded-lg border border-border bg-card/60 p-3.5 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-muted-foreground shrink-0" />
            <span className="text-xs font-semibold text-foreground">Connected accounts</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {accountsLoad.state === "loading" ? (
              <span className="h-6 w-40 animate-pulse rounded-full bg-muted" aria-label="Loading" />
            ) : accountsLoad.state !== "ready" ? (
              <span className="text-[11px] text-muted-foreground">{accountsLoad.state === "unreachable" ? "Service not running" : "Could not load accounts"}</span>
            ) : accountsLoad.data.length === 0 ? (
              <span className="text-[11px] text-muted-foreground">No accounts connected. Connect one under Connections.</span>
            ) : (
              accountsLoad.data.map((a: any) => (
                <span key={a.id} className="inline-flex items-center gap-1.5 rounded-full border border-border/70 bg-background/80 px-2.5 py-1 text-[11px] text-muted-foreground font-mono">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: platformColors[String(a.platform).toLowerCase()] || "#737373" }} />
                  {a.account_handle || a.account_name || a.platform}
                </span>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Filters Bar matching media_1789288661301.png & media_1789297905856.png */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        {/* Left Filter Dropdowns */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Status */}
          <select
            value={postStatusFilter}
            onChange={(e) => setPostStatusFilter(e.target.value)}
            className="rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-foreground focus:outline-none"
          >
            <option value="all">All posts</option>
            <option value="published">Published</option>
            <option value="scheduled">Scheduled</option>
            <option value="draft">Drafts</option>
            <option value="queued">Queued</option>
          </select>

          {/* Platform with authentic Brand Icons (media_1789297905856.png) */}
          <PlatformBrandDropdown
            value={platformFilter}
            onChange={setPlatformFilter}
          />

          {/* Dates */}
          <select
            value={dateFilter}
            onChange={(e) => setDateFilter(e.target.value)}
            className="rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-foreground focus:outline-none"
          >
            <option value="all">All dates</option>
            <option value="today">Today</option>
            <option value="this-week">This week</option>
            <option value="this-month">This month</option>
          </select>
        </div>

        {/* Right Controls: Sort & Views (media_1789298044544.png) */}
        <div className="flex items-center gap-2">
          {/* Sort Dropdown with exact popover matching media_1789300191753.png */}
          <ScheduleSortDropdown
            value={sortBy}
            onChange={setSortBy}
          />

          {/* View Mode Buttons */}
          <div className="flex items-center rounded-md border border-border bg-card p-0.5">
            <button
              onClick={() => setViewMode("grid")}
              className={`rounded p-1.5 transition-colors ${viewMode === "grid" ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              title="Grid view"
            >
              <LayoutGrid className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={`rounded p-1.5 transition-colors ${viewMode === "list" ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              title="List view"
            >
              <List className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setViewMode("calendar")}
              className={`rounded p-1.5 transition-colors ${viewMode === "calendar" ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              title="Calendar view"
            >
              <Calendar className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Zoom scale indicator matching screenshot */}
          <div className="hidden sm:flex items-center gap-1 text-xs text-muted-foreground border border-border bg-card rounded-md px-2 py-1">
            <button onClick={() => setZoomScale((z) => Math.max(1, z - 1))} className="hover:text-foreground p-0.5">-</button>
            <span className="font-mono text-[11px] px-1">{zoomScale}</span>
            <button onClick={() => setZoomScale((z) => Math.min(6, z + 1))} className="hover:text-foreground p-0.5">+</button>
          </div>
        </div>
      </div>

      {/* Main Content: Empty State OR Populated Grid/List/Calendar */}
      {postsLoad.state !== "ready" ? (
        <NotConnected loadable={postsLoad} service="The marketing service" onRetry={reload} />
      ) : filteredPosts.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card/30 py-20 px-6 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-muted/60 text-muted-foreground">
            <Edit className="h-6 w-6" />
          </div>
          <h3 className="text-lg font-bold text-foreground">No posts yet</h3>
          <p className="mt-1 text-xs text-muted-foreground">Create your first social media post</p>
          <Button
            onClick={onOpenComposer}
            className="mt-6 bg-[#EA3829] hover:bg-[#d02e20] text-white font-semibold text-xs px-6 h-10 shadow-md"
          >
            <Plus className="mr-1.5 h-4 w-4" /> Create post
          </Button>
        </div>
      ) : viewMode === "list" ? (
        <Card className="border-border bg-card">
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full min-w-[650px] text-xs">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground bg-muted/30">
                  <th className="px-4 py-3 font-semibold">Post Content</th>
                  <th className="px-4 py-3 font-semibold">Platforms</th>
                  <th className="px-4 py-3 font-semibold">Timing</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Engagement</th>
                  <th className="px-4 py-3 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredPosts.map((p) => (
                  <tr key={p.id} className="hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3 max-w-sm">
                      <p className="font-medium text-foreground line-clamp-2">{p.content}</p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">{p.brand_handle || "—"}</p>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        {p.platforms?.map((plat: string) => {
                          const Icon = platformIcons[plat.toLowerCase()] || Globe
                          return (
                            <span key={plat} className="p-1 rounded bg-background border border-border" title={plat}>
                              <Icon className="h-3 w-3" style={{ color: platformColors[plat.toLowerCase()] }} />
                            </span>
                          )
                        })}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                      {p.scheduled_for ? new Date(p.scheduled_for).toLocaleString() : "Immediate"}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant="outline" className={`text-[10px] capitalize ${statusColor[p.status] || "border-muted"}`}>
                        {p.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {p.likes || p.comments ? `${p.likes ?? 0} likes · ${p.comments ?? 0} comments` : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground">
                        <MoreVertical className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : viewMode === "calendar" ? (
        <Card className="border-border bg-card">
          <CardHeader className="pb-3 border-b border-border">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold text-foreground">Content Schedule Calendar</CardTitle>
              <Badge variant="outline" className="text-xs font-mono">{filteredPosts.length} posts scheduled</Badge>
            </div>
          </CardHeader>
          <CardContent className="p-4">
            <div className="grid grid-cols-7 gap-2 text-center text-xs">
              {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => (
                <div key={day} className="font-semibold text-muted-foreground py-1 bg-muted/20 rounded">
                  {day}
                </div>
              ))}
              {Array.from({ length: 14 }).map((_, idx) => {
                const date = new Date(Date.now() + (idx - 2) * 86400000)
                const dayStr = date.toISOString().slice(0, 10)
                const dayPosts = filteredPosts.filter((p) => p.scheduled_for && p.scheduled_for.slice(0, 10) === dayStr)
                return (
                  <div key={idx} className="min-h-[90px] rounded-lg border border-border/70 p-1.5 text-left bg-card/40 flex flex-col justify-between">
                    <div className="flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                      <span>{date.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
                      {dayPosts.length > 0 && (
                        <span className="rounded-full bg-primary/20 px-1 text-primary font-bold">{dayPosts.length}</span>
                      )}
                    </div>
                    <div className="space-y-1 mt-1">
                      {dayPosts.slice(0, 2).map((dp) => (
                        <div key={dp.id} className="rounded bg-accent/60 p-1 text-[10px] truncate" title={dp.content}>
                          <span className="font-semibold">{dp.brand_handle?.split("@")[1] || "Post"}:</span> {dp.content}
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className={`grid gap-4 ${gridColsClass}`}>
          {filteredPosts.map((p) => (
            <Card key={p.id} className="border-border bg-card shadow-xs hover:border-border/80 transition-colors flex flex-col justify-between">
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center font-bold text-xs text-primary">
                      O
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-foreground">{p.brand_handle || "—"}</p>
                      <div className="flex items-center gap-1 mt-0.5">
                        {p.platforms?.map((plat: string) => (
                          <span key={plat} className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: platformColors[plat.toLowerCase()] || "#666" }} title={plat} />
                        ))}
                      </div>
                    </div>
                  </div>
                  <Badge variant="outline" className={`text-[10px] capitalize ${statusColor[p.status] || "border-muted"}`}>
                    {p.status}
                  </Badge>
                </div>
                <p className="text-xs text-foreground/90 leading-relaxed line-clamp-4">{p.content}</p>
                <div className="flex items-center justify-between pt-2 border-t border-border/60 text-[11px] text-muted-foreground">
                  <span>{p.scheduled_for ? `Scheduled: ${new Date(p.scheduled_for).toLocaleDateString()}` : "Published"}</span>
                  <span className="flex items-center gap-2">
                    {p.likes ? <span>❤️ {p.likes}</span> : null}
                    {p.comments ? <span>💬 {p.comments}</span> : null}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// SOCIAL INBOX TAB
// ═══════════════════════════════════════════════════════════════════════════════

function InboxContactsTab() {
  // Real sources only: saved WhatsApp contacts + people who have messaged an
  // inbox-connected account. Nothing is seeded.
  const { value: waLoad, reload: reloadWa } = useMarketingLoad<any[]>(whatsAppContactsPath())
  const { value: inboxLoad, reload: reloadInbox } = useMarketingLoad<any[]>(inboxMessagesPath())
  const contacts = useMemo(() => {
    const out: any[] = []
    const seen = new Set<string>()
    if (waLoad.state === "ready") {
      for (const c of waLoad.data) {
        seen.add("wa|" + String(c.phone_number || "").replace(/\s+/g, ""))
        out.push({
          id: `wa-${c.id}`,
          name: c.name,
          identifier: c.phone_number,
          platform: "whatsapp",
          email: c.email || "",
          company: "",
          tags: c.tags || [],
          status: c.opt_in_status || "",
          lastActive: c.created_at ? new Date(c.created_at).toLocaleDateString() : "",
        })
      }
    }
    if (inboxLoad.state === "ready") {
      for (const m of inboxLoad.data) {
        const key = (m.sender_handle || m.sender_name || "unknown") + "|" + (m.platform || "")
        if (seen.has(key)) continue
        seen.add(key)
        out.push({
          id: `msg-cnt-${m.id}`,
          name: m.sender_name || m.sender_handle || "Unknown sender",
          identifier: m.sender_handle ? `@${m.sender_handle}` : (m.sender_name || "Unknown"),
          platform: m.platform?.toLowerCase() || "other",
          email: "",
          company: "",
          tags: ["inbox"],
          status: "",
          lastActive: m.created_at ? new Date(m.created_at).toLocaleDateString() : "",
        })
      }
    }
    return out
  }, [waLoad, inboxLoad])
  const loadState: Loadable<unknown> =
    waLoad.state === "ready" || inboxLoad.state === "ready" ? { state: "ready", data: null }
    : waLoad.state === "loading" || inboxLoad.state === "loading" ? { state: "loading" }
    : waLoad
  const reloadAll = () => { reloadWa(); reloadInbox() }
  const [searchQuery, setSearchQuery] = useState("")
  const [platformFilter, setPlatformFilter] = useState("all")
  const [showDrawer, setShowDrawer] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [creatingContact, setCreatingContact] = useState(false)

  // New contact drawer (persisted as a WhatsApp contact: name + phone are required by the API)
  const [formName, setFormName] = useState("")
  const [formPhone, setFormPhone] = useState("")
  const [formEmail, setFormEmail] = useState("")
  const [formTags, setFormTags] = useState("")

  const filtered = useMemo(() => {
    return contacts.filter((c) => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const matchesName = c.name?.toLowerCase().includes(q)
        const matchesIdent = c.identifier?.toLowerCase().includes(q)
        const matchesEmail = c.email?.toLowerCase().includes(q)
        const matchesCompany = c.company?.toLowerCase().includes(q)
        if (!matchesName && !matchesIdent && !matchesEmail && !matchesCompany) return false
      }
      if (platformFilter !== "all" && c.platform?.toLowerCase() !== platformFilter.toLowerCase()) {
        return false
      }
      return true
    })
  }, [contacts, searchQuery, platformFilter])

  const handleCreateContact = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formName.trim() || !formPhone.trim()) return
    setCreatingContact(true)
    setCreateError(null)
    const tags = formTags.split(",").map((t) => t.trim()).filter(Boolean)
    const r = await writeMarketing("POST", "/whatsapp/contacts", {
      name: formName.trim(),
      phone_number: formPhone.trim(),
      email: formEmail.trim() || undefined,
      tags: tags.length ? tags : undefined,
    })
    setCreatingContact(false)
    if (!r.ok) {
      setCreateError(describeMutationError(r.status, r.error))
      return
    }
    reloadAll()
    setShowDrawer(false)
    setFormName(""); setFormPhone(""); setFormEmail(""); setFormTags("")
  }

  return (
    <div className="space-y-4">
      {/* Top Header matching media_1789288816985.png */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-foreground">Contacts</h2>
          <p className="text-xs text-muted-foreground">Manage contacts across all platforms</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => { setCreateError(null); setShowDrawer(true) }}
            className="bg-[#EA3829] hover:bg-[#d02e20] text-white font-medium text-xs px-4 h-9 shadow-sm"
          >
            <Plus className="mr-1.5 h-4 w-4" /> Add Contact
          </Button>
        </div>
      </div>

      {/* Filter Row matching media_1789288816985.png */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        {/* Search Bar */}
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="Search contacts..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 text-xs h-9 bg-card border-border"
          />
        </div>

        {/* Dropdowns on Right */}
        <div className="flex items-center gap-2">
          <select
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value)}
            className="rounded-md border border-border bg-card px-3 py-1.5 text-xs text-foreground focus:outline-none"
          >
            <option value="all">All platforms</option>
            <option value="telegram">Telegram</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="facebook">Facebook</option>
            <option value="instagram">Instagram</option>
            <option value="twitter">X / Twitter</option>
            <option value="sms">SMS</option>
            <option value="slack">Slack</option>
            <option value="tiktok">TikTok</option>
          </select>
        </div>
      </div>

      {/* Table matching media_1789288816985.png */}
      {loadState.state !== "ready" ? (
        <NotConnected loadable={loadState} service="The marketing service" onRetry={reloadAll} />
      ) : (
      <Card className="border-border bg-card overflow-hidden">
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full min-w-[650px] text-xs">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground bg-muted/20">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Identifier</th>
                <th className="px-4 py-3 font-medium">Tags</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Last Active</th>
                <th className="px-4 py-3 font-medium text-right"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((c) => {
                const initial = (c.name || "C").charAt(0).toUpperCase()
                const PlatformIcon = platformIcons[c.platform?.toLowerCase()] || Globe
                const iconColor = platformColors[c.platform?.toLowerCase()] || "#666"

                return (
                  <tr key={c.id} className="hover:bg-muted/15 transition-colors">
                    {/* Name with Avatar */}
                    <td className="px-4 py-3 font-medium text-foreground">
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-muted-foreground font-semibold text-xs border border-border/70">
                          {initial}
                        </div>
                        <div>
                          <span className="font-semibold text-foreground text-xs">{c.name}</span>
                          {c.company && (
                            <p className="text-[11px] text-muted-foreground font-normal">{c.company}</p>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Identifier with Platform Icon */}
                    <td className="px-4 py-3 text-muted-foreground">
                      <div className="flex items-center gap-2">
                        <PlatformIcon className="h-3.5 w-3.5 shrink-0" style={{ color: iconColor }} />
                        <span className="font-mono text-[11px] truncate max-w-[200px]">{c.identifier}</span>
                      </div>
                    </td>

                    {/* Tags */}
                    <td className="px-4 py-3">
                      {c.tags && c.tags.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {c.tags.map((tag: string) => (
                            <span
                              key={tag}
                              className="rounded-md border border-border/80 bg-muted/50 px-2 py-0.5 text-[10px] text-muted-foreground"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>

                    {/* Status badge: subscribed (soft green) */}
                    <td className="px-4 py-3">
                      {!c.status ? <span className="text-muted-foreground">—</span> : <span className="inline-flex items-center rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                        {c.status}
                      </span>}
                    </td>

                    {/* Last Active */}
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                      {c.lastActive || "—"}
                    </td>

                    {/* 3-dots action */}
                    <td className="px-4 py-3 text-right">
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground">
                        <MoreVertical className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {/* Footer count matching screenshot */}
          <div className="border-t border-border px-4 py-3 text-center text-xs text-muted-foreground">
            {filtered.length === 0 ? "No contacts yet. Add one, or they appear here when someone messages a connected account." : `${filtered.length} ${filtered.length === 1 ? "contact" : "contacts"}`}
          </div>
        </CardContent>
      </Card>
      )}

      {/* Flyout Drawer matching media_1789290179411.png */}
      {showDrawer && (
        <div className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/60 backdrop-blur-xs">
          <div className="w-full max-w-md bg-card border-l border-border h-full flex flex-col p-6 shadow-2xl overflow-y-auto animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="flex items-center justify-between pb-4 border-b border-border">
              <h3 className="text-base font-bold text-foreground">New Contact</h3>
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground" onClick={() => setShowDrawer(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>

            {/* Form */}
            <form onSubmit={handleCreateContact} className="flex-1 space-y-4 pt-4">
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1.5">
                  Name <span className="text-red-500">*</span>
                </label>
                <Input
                  required
                  placeholder="Contact name"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="text-xs h-9 bg-background border-border"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground block mb-1.5">Email</label>
                <Input
                  type="email"
                  placeholder="email@example.com"
                  value={formEmail}
                  onChange={(e) => setFormEmail(e.target.value)}
                  className="text-xs h-9 bg-background border-border"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground block mb-1.5">
                  Phone number (WhatsApp) <span className="text-red-500">*</span>
                </label>
                <Input
                  required
                  placeholder="+country code and number"
                  value={formPhone}
                  onChange={(e) => setFormPhone(e.target.value)}
                  className="text-xs h-9 bg-background border-border"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground block mb-1.5">Tags (comma separated)</label>
                <Input
                  placeholder="customer, vip, lead"
                  value={formTags}
                  onChange={(e) => setFormTags(e.target.value)}
                  className="text-xs h-9 bg-background border-border"
                />
              </div>

              {createError && <p role="alert" className="text-xs text-red-400">{createError}</p>}

              {/* Drawer Actions at Bottom */}
              <div className="flex items-center justify-end gap-3 pt-6 border-t border-border mt-auto">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowDrawer(false)}
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={!formName.trim() || !formPhone.trim() || creatingContact}
                  className="bg-[#EA3829] hover:bg-[#d02e20] text-white font-medium text-xs px-5 h-9"
                >
                  {creatingContact ? "Creating…" : "Create"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

const INBOX_KIND_TYPE: Record<string, string> = { messages: "DM", comments: "COMMENT", reviews: "REVIEW" }

const INBOX_PLATFORMS = [
  { id: "all", label: "All platforms", icon: null, color: "" },
  { id: "facebook", label: "Facebook", icon: Facebook, color: "#1877F2" },
  { id: "instagram", label: "Instagram", icon: Instagram, color: "#E4405F" },
  { id: "twitter", label: "Twitter", icon: Twitter, color: "#1DA1F2" },
  { id: "bluesky", label: "Bluesky", icon: Globe, color: "#0085FF" },
  { id: "reddit", label: "Reddit", icon: MessageCircle, color: "#FF4500" },
  { id: "telegram", label: "Telegram", icon: Send, color: "#0088CC" },
  { id: "whatsapp", label: "WhatsApp", icon: MessageCircle, color: "#25D366" },
  { id: "sms", label: "SMS", icon: Phone, color: "#10B981" },
  { id: "slack", label: "Slack", icon: Hash, color: "#4A154B" },
  { id: "tiktok", label: "TikTok", icon: Video, color: "#000000" },
]

/** "5m ago", "3h ago", "2d ago" from a real timestamp; empty when unknown. */
function timeAgo(iso?: string | null): string {
  if (!iso) return ""
  const t = new Date(iso).getTime()
  if (!Number.isFinite(t)) return ""
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000))
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 48) return `${hrs}h ago`
  return `${Math.round(hrs / 24)}d ago`
}

function SocialInboxTab({ kind = "messages" }: { kind?: "messages" | "comments" | "reviews" }) {
  const messageType = INBOX_KIND_TYPE[kind] || "DM"
  const { value: inboxLoad, reload: loadInbox } = useMarketingLoad<any[]>(inboxMessagesPath({ message_type: messageType }))
  const { value: accountsLoad } = useMarketingLoad<any[]>(socialAccountsPath())
  const messages: any[] = inboxLoad.state === "ready" ? inboxLoad.data : []
  const accountName = (id?: string) => {
    if (accountsLoad.state !== "ready") return ""
    const a = accountsLoad.data.find((x: any) => x.id === id)
    return a ? (a.account_handle || a.account_name || "") : ""
  }
  const [selectedPlatform, setSelectedPlatform] = useState<string>("all")
  const [selectedAccount, setSelectedAccount] = useState("all")
  const [searchQuery, setSearchQuery] = useState("")
  const [sortBy, setSortBy] = useState("newest")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [replyText, setReplyText] = useState("")
  // Replies the server accepted this session, keyed by message id.
  const [sentReplies, setSentReplies] = useState<Record<string, { text: string; time: string }[]>>({})
  const [actionError, setActionError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  // Title based on kind
  const titleLabel = kind === "comments" ? "Comments" : kind === "reviews" ? "Reviews" : "Messages"

  const selectedMessage = messages.find((m) => m.id === selectedId) ?? messages[0] ?? null
  const chatHistory: any[] = selectedMessage
    ? [
        { sender: selectedMessage.sender_name || selectedMessage.sender_handle || "Sender", role: "customer", text: selectedMessage.content, rating: typeof selectedMessage.rating === "number" ? selectedMessage.rating : undefined, time: timeAgo(selectedMessage.created_at) },
        ...(sentReplies[selectedMessage.id] ?? []).map((r) => ({ sender: "You", role: "agent", text: r.text, time: r.time })),
      ]
    : []

  const handleMarkRead = async (id: string) => {
    setActionError(null)
    const r = await writeMarketing("PUT", `/social/inbox/${id}/read`)
    if (!r.ok) setActionError(describeMutationError(r.status, r.error))
    else loadInbox()
  }

  const handleArchive = async (id: string) => {
    setActionError(null)
    const r = await writeMarketing("PUT", `/social/inbox/${id}/archive`)
    if (!r.ok) setActionError(describeMutationError(r.status, r.error))
    else loadInbox()
  }

  const filteredMessages = useMemo(() => {
    const ts = (m: any) => new Date(m.created_at || 0).getTime()
    const ordered = [...messages].sort((a, b) =>
      sortBy === "oldest" ? ts(a) - ts(b)
      : sortBy === "unread" ? ((b.status === "UNREAD" ? 1 : 0) - (a.status === "UNREAD" ? 1 : 0)) || ts(b) - ts(a)
      : ts(b) - ts(a))
    return ordered.filter((m) => {
      // Reviews must only come from review platforms (Google Business & Facebook)
      if (kind === "reviews") {
        const isReviewPlatform = m.platform === "googlebusiness" || m.platform === "facebook"
        if (!isReviewPlatform) return false
      }
      if (selectedPlatform !== "all" && m.platform?.toLowerCase() !== selectedPlatform.toLowerCase()) return false
      if (selectedAccount !== "all" && m.account_id !== selectedAccount) return false
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        if (!m.sender_name?.toLowerCase().includes(q) && !m.content?.toLowerCase().includes(q)) return false
      }
      return true
    })
  }, [messages, selectedPlatform, selectedAccount, searchQuery, kind, sortBy])

  const handleSendReply = async () => {
    if (!selectedMessage || !replyText.trim() || sending) return
    const textToSend = replyText.trim()
    setSending(true)
    setActionError(null)
    const r = await writeMarketing("POST", `/social/inbox/${selectedMessage.id}/reply`, { content: textToSend })
    setSending(false)
    if (!r.ok) {
      setActionError(describeMutationError(r.status, r.error))
      return
    }
    setReplyText("")
    setSentReplies((prev) => ({
      ...prev,
      [selectedMessage.id]: [...(prev[selectedMessage.id] ?? []), { text: textToSend, time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) }],
    }))
  }

  return (
    <div className="space-y-4">
      {/* Top Header matching media_1789290079115.png */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-foreground">{titleLabel}</h2>
          {kind === "reviews" && (
            <p className="text-xs text-muted-foreground">Customer reviews and ratings from verified Google Business and Facebook pages</p>
          )}
        </div>
        <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground">
          <Edit className="h-4 w-4" />
        </Button>
      </div>

      {/* Row 1: Filter Dropdowns */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Multi-Platform Dropdown Button & Menu */}
        <PlatformBrandDropdown
          value={selectedPlatform}
          onChange={setSelectedPlatform}
          options={kind === "reviews" ? REVIEW_PLATFORMS : ALL_BRAND_PLATFORMS}
        />

        {/* Accounts Dropdown */}
        <select
          value={selectedAccount}
          onChange={(e) => setSelectedAccount(e.target.value)}
          className="rounded-md border border-border bg-card px-3 py-1.5 text-xs text-foreground focus:outline-none"
        >
          <option value="all">All accounts</option>
          {accountsLoad.state === "ready" && accountsLoad.data.map((a: any) => (
            <option key={a.id} value={a.id}>{a.account_handle || a.account_name || a.platform}</option>
          ))}
        </select>
      </div>

      {/* Row 2: Search + Sort */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder={kind === "reviews" ? "Search customer reviews..." : "Search messages..."}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 text-xs h-9 bg-card border-border"
          />
        </div>

        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="rounded-md border border-border bg-card px-3 py-1.5 text-xs text-foreground focus:outline-none"
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="unread">Unread first</option>
        </select>
      </div>

      {/* Main 2-Column Chat Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] border border-border rounded-xl bg-card overflow-hidden min-h-[560px]">
        {/* Left Column: Conversation / Review List */}
        <div className="border-r border-border divide-y divide-border/60 overflow-y-auto max-h-[640px]">
          {inboxLoad.state !== "ready" ? (
            <NotConnected loadable={inboxLoad} service="The marketing service" onRetry={loadInbox} className="m-3" />
          ) : filteredMessages.length === 0 ? (
            <div className="py-12 text-center text-xs text-muted-foreground">{messages.length === 0 ? `No ${titleLabel.toLowerCase()} yet` : `No ${titleLabel.toLowerCase()} match the filters`}</div>
          ) : (
            filteredMessages.map((m) => {
              const isSelected = selectedMessage?.id === m.id
              const initial = (m.sender_name || "U").charAt(0).toUpperCase()
              const PlatformIcon = platformIcons[m.platform?.toLowerCase()] || Globe
              const iconColor = platformColors[m.platform?.toLowerCase()] || "#666"

              return (
                <button
                  key={m.id}
                  onClick={() => setSelectedId(m.id)}
                  className={`w-full text-left p-3.5 transition-colors flex items-start gap-3 ${
                    isSelected ? "bg-accent/70 border-l-2 border-l-[#EA3829]" : "hover:bg-muted/20"
                  }`}
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground font-semibold text-xs border border-border">
                    {initial}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="font-semibold text-xs text-foreground truncate">{m.sender_name}</span>
                      <span className="text-[10px] text-muted-foreground shrink-0">
                        {timeAgo(m.created_at)}
                      </span>
                    </div>

                    {/* Star ratings for reviews */}
                    {kind === "reviews" && typeof m.rating === "number" && (
                      <div className="flex items-center gap-0.5 mb-1">
                        {Array.from({ length: 5 }).map((_, si) => (
                          <Star
                            key={si}
                            className={`h-3 w-3 ${si < m.rating ? "fill-amber-400 text-amber-400" : "text-muted-foreground/30"}`}
                          />
                        ))}
                        <span className="ml-1 text-[10px] font-bold text-foreground">{m.rating}.0</span>
                      </div>
                    )}

                    <p className="text-xs text-muted-foreground truncate mb-1">{m.content}</p>
                    <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                      <PlatformIcon className="h-3 w-3 shrink-0" style={{ color: iconColor }} />
                      <span>
                        {kind === "reviews"
                          ? m.platform === "googlebusiness" ? "Google Review" : "Facebook Review"
                          : (accountName(m.account_id) ? `via ${accountName(m.account_id)}` : (m.platform || ""))}
                      </span>
                    </div>
                  </div>
                </button>
              )
            })
          )}
        </div>

        {/* Right Column: Review / Chat History & Composer */}
        <div className="flex flex-col h-full justify-between bg-background/50">
          {selectedMessage ? (
            <>
              {/* Header */}
              <div className="flex items-center justify-between border-b border-border bg-card/60 px-5 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-muted text-muted-foreground font-semibold text-xs border border-border">
                    {(selectedMessage.sender_name || "U").charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5">
                      <h4 className="text-xs font-bold text-foreground">{selectedMessage.sender_name}</h4>
                      {(() => {
                        const Icon = platformIcons[selectedMessage.platform?.toLowerCase()] || Globe
                        return <Icon className="h-3 w-3" style={{ color: platformColors[selectedMessage.platform?.toLowerCase()] || "#666" }} />
                      })()}
                      {kind === "reviews" && typeof selectedMessage.rating === "number" && (
                        <span className="flex items-center gap-0.5 ml-1">
                          {Array.from({ length: 5 }).map((_, si) => (
                            <Star
                              key={si}
                              className={`h-3 w-3 ${si < selectedMessage.rating ? "fill-amber-400 text-amber-400" : "text-muted-foreground/30"}`}
                            />
                          ))}
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      {kind === "reviews"
                        ? `Public review on ${selectedMessage.platform === "googlebusiness" ? "Google Business Profile" : "Facebook Pages"}`
                        : `${accountName(selectedMessage.account_id) ? `Replying as ${accountName(selectedMessage.account_id)} · ` : ""}Received ${timeAgo(selectedMessage.created_at)}`}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" className="text-[11px] h-7" onClick={() => handleMarkRead(selectedMessage.id)}>
                    Mark Read
                  </Button>
                  <Button size="sm" variant="outline" className="text-[11px] h-7" onClick={() => handleArchive(selectedMessage.id)}>
                    Archive
                  </Button>
                </div>
              </div>

              {/* Chat / Review Bubble Stream */}
              <div className="flex-1 p-5 space-y-3 overflow-y-auto max-h-[460px]">
                {chatHistory.map((bubble, i) => {
                  const isAgent = bubble.role === "agent"
                  return (
                    <div key={i} className={`flex flex-col ${isAgent ? "items-end" : "items-start"}`}>
                      <div
                        className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-xs shadow-2xs ${
                          isAgent
                            ? "bg-[#EA3829] text-white rounded-br-none"
                            : "bg-card border border-border text-foreground rounded-bl-none"
                        }`}
                      >
                        {!isAgent && (
                          <div className="flex items-center justify-between gap-2 text-[10px] font-semibold text-muted-foreground mb-1">
                            <span>{bubble.sender}</span>
                            {bubble.rating && (
                              <span className="flex items-center gap-0.5">
                                {Array.from({ length: 5 }).map((_, si) => (
                                  <Star
                                    key={si}
                                    className={`h-2.5 w-2.5 ${si < bubble.rating ? "fill-amber-400 text-amber-400" : "text-muted-foreground/30"}`}
                                  />
                                ))}
                              </span>
                            )}
                          </div>
                        )}
                        {isAgent && (
                          <div className="text-[10px] font-semibold text-white/90 mb-0.5">
                            {kind === "reviews" ? "Your response (public)" : "You"}
                          </div>
                        )}
                        <p className="leading-relaxed whitespace-pre-wrap">{bubble.text}</p>
                        <div
                          className={`text-[9px] mt-1 text-right ${
                            isAgent ? "text-white/80" : "text-muted-foreground"
                          }`}
                        >
                          {bubble.time}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Bottom Reply Composer */}
              <div className="p-4 border-t border-border bg-card/60">
                {actionError && <p role="alert" className="mb-2 text-xs text-red-400">{actionError}</p>}
                <div className="flex items-center gap-2 rounded-xl border border-border bg-background px-3 py-1.5 shadow-xs focus-within:border-primary/60">
                  <Input
                    placeholder={kind === "reviews" ? "Reply publicly to this customer review as OmniDome..." : "Type a message..."}
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault()
                        handleSendReply()
                      }
                    }}
                    className="border-0 shadow-none focus-visible:ring-0 text-xs px-1 h-9 bg-transparent"
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground shrink-0"
                    title="Attach media"
                  >
                    <Paperclip className="h-4 w-4" />
                  </Button>
                  <button
                    onClick={handleSendReply}
                    disabled={!replyText.trim() || sending}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#EA3829] text-white hover:bg-[#d02e20] transition-colors disabled:opacity-40"
                    title={kind === "reviews" ? "Post public reply" : "Send"}
                  >
                    <Send className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="flex h-full items-center justify-center p-10 text-center text-xs text-muted-foreground">
              Select a {kind === "reviews" ? "review" : "conversation"} to inspect and reply
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// SOCIAL ANALYTICS TAB
// ═══════════════════════════════════════════════════════════════════════════════

const DAILY_METRICS: { key: keyof DailyMetricPoint["metrics"]; label: string; color: string }[] = [
  { key: "impressions", label: "Impressions", color: "#60a5fa" },
  { key: "reach", label: "Reach", color: "#a78bfa" },
  { key: "likes", label: "Likes", color: "#f472b6" },
  { key: "comments", label: "Comments", color: "#4ade80" },
  { key: "clicks", label: "Clicks", color: "#f59e0b" },
  { key: "views", label: "Views", color: "#22d3ee" },
]

const WINDOW_DAYS: Record<string, number> = { "7d": 7, "30d": 30, "90d": 90, "1y": 365 }

function SocialAnalyticsTab() {
  const [subTab, setSubTab] = useState<"posting" | "inbox">("posting")
  const [platformFilter, setPlatformFilter] = useState("all")
  const [timeWindow, setTimeWindow] = useState("30d")
  const [likesMetric, setLikesMetric] = useState("likes")
  const [attribution] = useState<"publish" | "received">("publish")
  const days = WINDOW_DAYS[timeWindow] ?? 30

  // One loader per data set; the marketing read cache shares results with other tabs.
  const { value: overviewLoad, reload: reloadOverview } = useMarketingLoad<{ overview: AnalyticsOverview }>("/social/analytics/overview")
  const { value: postsLoad } = useMarketingLoad<{ posts: AnalyticsPostRow[] }>(analyticsPostsPath({ limit: 20 }))
  const { value: dailyLoad } = useMarketingLoad<{ dailyData: DailyMetricPoint[] }>(analyticsDailyPath({ attribution, days }))
  const { value: inboxLoad, reload: reloadInbox } = useMarketingLoad<any[]>(subTab === "inbox" ? inboxMessagesPath() : null)

  const overview = overviewLoad.state === "ready" ? overviewLoad.data?.overview ?? null : null
  const allPosts: AnalyticsPostRow[] = postsLoad.state === "ready" ? postsLoad.data?.posts ?? [] : []
  const posts = platformFilter === "all" ? allPosts : allPosts.filter((p) => p.platform?.toLowerCase() === platformFilter.toLowerCase())
  const daily: DailyMetricPoint[] = dailyLoad.state === "ready" ? dailyLoad.data?.dailyData ?? [] : []

  // Real aggregates derived from synced posts / daily rows
  const postsPerPlatform = Object.entries(
    posts.reduce((acc: Record<string, number>, p) => { acc[p.platform] = (acc[p.platform] ?? 0) + 1; return acc }, {}),
  ).map(([platform, count]) => ({ platform, count }))
  const metricPerPlatform = Object.entries(
    posts.reduce((acc: Record<string, number>, p) => { acc[p.platform] = (acc[p.platform] ?? 0) + (Number(p.analytics?.[likesMetric]) || 0); return acc }, {}),
  ).map(([platform, value]) => ({ platform, value }))
  const dailySeries = daily.map((d) => ({
    date: d.date,
    posts: d.postCount,
    interactions: likesMetric in d.metrics ? (d.metrics as Record<string, number>)[likesMetric] : 0,
  }))

  // Inbox analytics from real messages
  const inboxMsgs: any[] = inboxLoad.state === "ready" ? inboxLoad.data : []
  const inboxTotal = inboxMsgs.length
  const inboxReplied = inboxMsgs.filter((m) => m.status === "REPLIED").length
  const inboxUnread = inboxMsgs.filter((m) => m.status === "UNREAD").length
  const inboxContacts = new Set(inboxMsgs.map((m) => `${m.sender_handle || m.sender_name || "?"}|${m.platform}`)).size
  const inboxByPlatform = Object.entries(
    inboxMsgs.reduce((acc: Record<string, number>, m) => { const k = m.platform || "other"; acc[k] = (acc[k] ?? 0) + 1; return acc }, {}),
  ).map(([platform, messages]) => ({ platform, messages }))
  const inboxByDay = Object.entries(
    inboxMsgs.reduce((acc: Record<string, number>, m) => {
      const d = m.created_at ? new Date(m.created_at).toISOString().slice(0, 10) : null
      if (d) acc[d] = (acc[d] ?? 0) + 1
      return acc
    }, {}),
  ).sort(([a], [b]) => a.localeCompare(b)).map(([date, inbound]) => ({ date, inbound }))

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight text-foreground">Analytics</h2>
        <p className="text-xs text-muted-foreground">
          {subTab === "posting" ? "View post performance metrics" : "View customer response and inbox metrics"}
        </p>
      </div>

      <div className="flex border-b border-border text-xs font-semibold">
        <button
          onClick={() => setSubTab("posting")}
          className={`pb-2.5 px-3 transition-colors border-b-2 ${
            subTab === "posting" ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Posting analytics
        </button>
        <button
          onClick={() => setSubTab("inbox")}
          className={`pb-2.5 px-3 transition-colors border-b-2 ${
            subTab === "inbox" ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Inbox analytics
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <PlatformBrandDropdown value={platformFilter} onChange={setPlatformFilter} />
        <select
          value={timeWindow}
          onChange={(e) => setTimeWindow(e.target.value)}
          className="rounded-md border border-border bg-card px-3 py-1.5 text-xs text-foreground focus:outline-none"
        >
          <option value="30d">Last 30 days</option>
          <option value="7d">Last 7 days</option>
          <option value="90d">Last 90 days</option>
          <option value="1y">Last year</option>
        </select>
      </div>

      {subTab === "posting" ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-0 rounded-lg border border-border bg-card divide-y md:divide-y-0 md:divide-x divide-border overflow-hidden">
            <div className="p-4">
              <p className="text-xs text-muted-foreground mb-1">Engagement rate</p>
              <p className="text-xl font-bold text-foreground">
                <StatValue loadable={overviewLoad}>{(d) => `${(d?.overview?.engagementRate ?? 0).toFixed(1)}%`}</StatValue>
              </p>
            </div>
            <div className="p-4">
              <p className="text-xs text-muted-foreground mb-1">Total reach</p>
              <div className="flex items-center gap-1.5">
                <Eye className="h-4 w-4 text-muted-foreground" />
                <span className="text-xl font-bold text-foreground">
                  <StatValue loadable={overviewLoad}>{(d) => (d?.overview?.reach ?? 0).toLocaleString()}</StatValue>
                </span>
              </div>
            </div>
            <div className="p-4">
              <p className="text-xs text-muted-foreground mb-1">Total followers</p>
              <div className="flex items-center gap-1.5">
                <Users className="h-4 w-4 text-muted-foreground" />
                <span className="text-xl font-bold text-foreground">
                  <StatValue loadable={overviewLoad}>{(d) => (d?.overview?.followers ?? 0).toLocaleString()}</StatValue>
                </span>
              </div>
            </div>
            <div className="p-4">
              <p className="text-xs text-muted-foreground mb-1">Posts this period</p>
              <div className="flex items-center gap-1.5">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <span className="text-xl font-bold text-foreground">
                  <StatValue loadable={overviewLoad}>{(d) => (d?.overview?.totalPosts ?? 0).toLocaleString()}</StatValue>
                </span>
              </div>
            </div>
            <div className="p-4">
              <p className="text-xs text-muted-foreground mb-1">Best post</p>
              <p className="text-base font-semibold text-muted-foreground truncate">
                <StatValue loadable={overviewLoad} className="text-base">{(d) => d?.overview?.bestPost || "No data yet"}</StatValue>
              </p>
            </div>
          </div>
          {overview && (overview.lastSync || overview.lastError) && (
            <p className="text-[11px] text-muted-foreground">
              {overview.lastSync ? `Last synced ${new Date(overview.lastSync).toLocaleString()}` : "Not synced yet"}
              {overview.lastError ? ` · last sync error: ${overview.lastError}` : ""}
            </p>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="border-border bg-card">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">Posts per platform</CardTitle>
                <CardDescription className="text-xs">From the latest synced posts</CardDescription>
              </CardHeader>
              <CardContent className="h-56">
                {postsLoad.state !== "ready" ? (
                  <NotConnected loadable={postsLoad} service="The marketing service" className="h-56" />
                ) : postsPerPlatform.length === 0 ? (
                  <NoDataYet message="No posts yet" className="h-56 flex items-center justify-center" />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={postsPerPlatform}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                      <XAxis dataKey="platform" tick={{ fill: "#888", fontSize: 11 }} />
                      <YAxis tick={{ fill: "#888", fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ backgroundColor: "#1f1f1f", borderColor: "#444", fontSize: "11px" }} />
                      <Bar dataKey="count" fill="#60a5fa" name="Posts" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card className="border-border bg-card">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">Posts over time</CardTitle>
                <CardDescription className="text-xs">Posts per day · last {days} days</CardDescription>
              </CardHeader>
              <CardContent className="h-56">
                {dailyLoad.state !== "ready" ? (
                  <NotConnected loadable={dailyLoad} service="The marketing service" className="h-56" />
                ) : dailySeries.length === 0 ? (
                  <NoDataYet message="No synced activity in this window" className="h-56 flex items-center justify-center" />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={dailySeries}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#333333" />
                      <XAxis dataKey="date" tick={{ fill: "#888888", fontSize: 11 }} />
                      <YAxis tick={{ fill: "#888888", fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ backgroundColor: "#1f1f1f", borderColor: "#444", fontSize: "11px" }} />
                      <Line type="monotone" dataKey="posts" stroke="#60a5fa" strokeWidth={2} dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card className="border-border bg-card">
              <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                <div className="flex items-center gap-1.5">
                  <Heart className="h-4 w-4 text-muted-foreground" />
                  <CardTitle className="text-sm font-semibold">{likesMetric.charAt(0).toUpperCase() + likesMetric.slice(1)} per platform</CardTitle>
                </div>
                <select
                  value={likesMetric}
                  onChange={(e) => setLikesMetric(e.target.value)}
                  className="rounded-md border border-border bg-background px-2.5 py-1 text-xs text-foreground focus:outline-none"
                >
                  <option value="likes">Likes</option>
                  <option value="comments">Comments</option>
                  <option value="shares">Shares</option>
                  <option value="clicks">Clicks</option>
                </select>
              </CardHeader>
              <CardContent className="h-56">
                {postsLoad.state !== "ready" ? (
                  <NotConnected loadable={postsLoad} service="The marketing service" className="h-56" />
                ) : metricPerPlatform.every((r) => r.value === 0) ? (
                  <NoDataYet message={`No ${likesMetric} recorded yet`} className="h-56 flex items-center justify-center" />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={metricPerPlatform}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                      <XAxis dataKey="platform" tick={{ fill: "#888", fontSize: 11 }} />
                      <YAxis tick={{ fill: "#888", fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ backgroundColor: "#1f1f1f", borderColor: "#444", fontSize: "11px" }} />
                      <Bar dataKey="value" fill="#f472b6" name={likesMetric} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card className="border-border bg-card">
              <CardHeader className="pb-2">
                <div className="flex items-center gap-1.5">
                  <Heart className="h-4 w-4 text-muted-foreground" />
                  <CardTitle className="text-sm font-semibold">{likesMetric.charAt(0).toUpperCase() + likesMetric.slice(1)} over time</CardTitle>
                </div>
                <CardDescription className="text-xs">Daily · last {days} days</CardDescription>
              </CardHeader>
              <CardContent className="h-56">
                {dailyLoad.state !== "ready" ? (
                  <NotConnected loadable={dailyLoad} service="The marketing service" className="h-56" />
                ) : dailySeries.length === 0 ? (
                  <NoDataYet message="No synced activity in this window" className="h-56 flex items-center justify-center" />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={dailySeries}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#333333" />
                      <XAxis dataKey="date" tick={{ fill: "#888888", fontSize: 11 }} />
                      <YAxis tick={{ fill: "#888888", fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ backgroundColor: "#1f1f1f", borderColor: "#444", fontSize: "11px" }} />
                      <Line type="monotone" dataKey="interactions" stroke="#f472b6" strokeWidth={2} dot={{ r: 3 }} name={likesMetric} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>

          {posts.length > 0 && (
            <Card className="border-border bg-card">
              <CardHeader><CardTitle className="text-sm">Recent Posts Performance</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px] text-xs">
                    <thead>
                      <tr className="border-b border-border text-left text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Platform</th>
                        <th className="py-2 pr-4 font-medium">Published</th>
                        <th className="py-2 pr-4 font-medium">Likes</th>
                        <th className="py-2 pr-4 font-medium">Comments</th>
                        <th className="py-2 pr-4 font-medium">Impressions</th>
                        <th className="py-2 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {posts.map((p) => (
                        <tr key={`${p.postId}-${p.platform}`}>
                          <td className="py-3 pr-4 font-medium text-foreground">
                            <span className="flex items-center gap-2">
                              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: platformColors[p.platform?.toLowerCase()] || "#666" }} />
                              {p.platform}
                            </span>
                          </td>
                          <td className="py-3 pr-4 text-muted-foreground">{p.publishedAt ? new Date(p.publishedAt).toLocaleDateString() : "—"}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{p.analytics.likes ?? 0}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{p.analytics.comments ?? 0}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{p.analytics.impressions ?? 0}</td>
                          <td className="py-3">
                            <Badge variant="outline" className="text-[10px] border-emerald-500/30 text-emerald-500">
                              {p.syncStatus || "synced"}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      ) : inboxLoad.state !== "ready" ? (
        <NotConnected loadable={inboxLoad} service="The marketing service" onRetry={reloadInbox} />
      ) : (
        <>
          {/* Inbox analytics: every figure is derived from real inbox messages */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-0 rounded-lg border border-border bg-card divide-y md:divide-y-0 md:divide-x divide-border overflow-hidden">
            <div className="p-4">
              <p className="text-xs text-muted-foreground mb-1">Response rate</p>
              <p className="text-xl font-bold text-foreground">{inboxTotal > 0 ? `${((inboxReplied / inboxTotal) * 100).toFixed(1)}%` : "No messages yet"}</p>
            </div>
            <div className="p-4">
              <p className="text-xs text-muted-foreground mb-1">Unread</p>
              <div className="flex items-center gap-1.5">
                <Eye className="h-4 w-4 text-muted-foreground" />
                <span className="text-xl font-bold text-foreground">{inboxUnread.toLocaleString()}</span>
              </div>
            </div>
            <div className="p-4">
              <p className="text-xs text-muted-foreground mb-1">Total contacts</p>
              <div className="flex items-center gap-1.5">
                <Users className="h-4 w-4 text-muted-foreground" />
                <span className="text-xl font-bold text-foreground">{inboxContacts.toLocaleString()}</span>
              </div>
            </div>
            <div className="p-4">
              <p className="text-xs text-muted-foreground mb-1">Messages</p>
              <div className="flex items-center gap-1.5">
                <MessageSquare className="h-4 w-4 text-muted-foreground" />
                <span className="text-xl font-bold text-foreground">{inboxTotal.toLocaleString()}</span>
              </div>
            </div>
            <div className="p-4">
              <p className="text-xs text-muted-foreground mb-1">Avg response time</p>
              <p className="text-base font-semibold text-muted-foreground">Not tracked</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="border-border bg-card">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">Messages per platform</CardTitle>
                <CardDescription className="text-xs">Inbound channel distribution</CardDescription>
              </CardHeader>
              <CardContent className="h-56">
                {inboxByPlatform.length === 0 ? (
                  <NoDataYet message="No messages yet" className="h-56 flex items-center justify-center" />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={inboxByPlatform}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                      <XAxis dataKey="platform" tick={{ fill: "#888", fontSize: 11 }} />
                      <YAxis tick={{ fill: "#888", fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ backgroundColor: "#1f1f1f", borderColor: "#444", fontSize: "11px" }} />
                      <Bar dataKey="messages" radius={[4, 4, 0, 0]}>
                        {inboxByPlatform.map((r) => (
                          <Cell key={r.platform} fill={platformColors[r.platform.toLowerCase()] || "#737373"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card className="border-border bg-card">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">Messages over time</CardTitle>
                <CardDescription className="text-xs">Inbound messages per day</CardDescription>
              </CardHeader>
              <CardContent className="h-56">
                {inboxByDay.length === 0 ? (
                  <NoDataYet message="No messages yet" className="h-56 flex items-center justify-center" />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={inboxByDay}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                      <XAxis dataKey="date" tick={{ fill: "#888", fontSize: 11 }} />
                      <YAxis tick={{ fill: "#888", fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ backgroundColor: "#1f1f1f", borderColor: "#444", fontSize: "11px" }} />
                      <Line type="monotone" dataKey="inbound" stroke="#60a5fa" strokeWidth={2} name="Inbound" dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// WHATSAPP TAB
// ═══════════════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════════════
// WHATSAPP TAB (Zernio-style Overview, Senders, Templates, Flows & Connect Modal)
// ═══════════════════════════════════════════════════════════════════════════════

function WhatsAppTab({ view }: { view: "overview" | "templates" | "flows" | "groups" | "conversions" | "broadcasts" | "contacts" }) {
  // Each view fetches only what it shows, through the shared marketing read cache.
  const needSenders = view === "overview" || view === "groups"
  const { value: sendersLoad, reload: reloadSenders } = useMarketingLoad<WhatsAppSender[]>(needSenders ? "/whatsapp/senders" : null)
  const { value: templatesLoad, reload: reloadTemplates } = useMarketingLoad<WhatsAppTemplate[]>(view === "templates" ? "/whatsapp/templates" : null)
  const { value: flowsLoad, reload: reloadFlows } = useMarketingLoad<WhatsAppFlow[]>(view === "flows" ? "/whatsapp/flows" : null)
  const { value: groupsLoad, reload: reloadGroups } = useMarketingLoad<WhatsAppGroup[]>(view === "groups" ? "/whatsapp/groups" : null)
  const { value: conversionsLoad, reload: reloadConversions } = useMarketingLoad<WhatsAppConversion[]>(view === "conversions" ? "/whatsapp/conversions" : null)
  const { value: contactsLoad, reload: reloadContacts } = useMarketingLoad<any[]>(view === "contacts" ? whatsAppContactsPath() : null)
  const { value: broadcastsLoad, reload: reloadBroadcasts } = useMarketingLoad<any[]>(view === "broadcasts" ? whatsAppBroadcastsPath() : null)
  const senders: WhatsAppSender[] = sendersLoad.state === "ready" ? sendersLoad.data : []
  const templates: WhatsAppTemplate[] = templatesLoad.state === "ready" ? templatesLoad.data : []
  const flows: WhatsAppFlow[] = flowsLoad.state === "ready" ? flowsLoad.data : []
  const groups: WhatsAppGroup[] = groupsLoad.state === "ready" ? groupsLoad.data : []
  const conversions: WhatsAppConversion[] = conversionsLoad.state === "ready" ? conversionsLoad.data : []
  const contacts: any[] = contactsLoad.state === "ready" ? contactsLoad.data : []
  const broadcasts: any[] = broadcastsLoad.state === "ready" ? broadcastsLoad.data : []
  const primaryLoad: Loadable<unknown> =
    view === "overview" ? sendersLoad
    : view === "templates" ? templatesLoad
    : view === "flows" ? flowsLoad
    : view === "groups" ? (sendersLoad.state !== "ready" ? sendersLoad : groupsLoad)
    : view === "conversions" ? conversionsLoad
    : view === "contacts" ? contactsLoad
    : broadcastsLoad
  const loadAll = () => { reloadSenders(); reloadTemplates(); reloadFlows(); reloadGroups(); reloadConversions(); reloadContacts(); reloadBroadcasts() }
  const [actionError, setActionError] = useState<string | null>(null)
  const runWrite = async (method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, body: unknown): Promise<boolean> => {
    setActionError(null)
    const r = await writeMarketing(method, path, body)
    if (!r.ok) { setActionError(describeMutationError(r.status, r.error)); return false }
    return true
  }

  // Modals
  const [showConnectModal, setShowConnectModal] = useState(false)
  const [connectMode, setConnectMode] = useState<"get_number" | "own_number" | null>(null)
  const [selectedCountry, setSelectedCountry] = useState("+27")
  const [customPhone, setCustomPhone] = useState("")
  const [customDisplayName, setCustomDisplayName] = useState("")
  const [isConnecting, setIsConnecting] = useState(false)

  // Groups create state
  const [showCreateGroup, setShowCreateGroup] = useState(false)
  const [newGroup, setNewGroup] = useState({ name: "", invite_link: "" })

  // Templates create state
  const [showCreateTemplate, setShowCreateTemplate] = useState(false)
  const [newTemplate, setNewTemplate] = useState({
    name: "",
    category: "MARKETING",
    language: "en_US",
    header: "",
    body: "",
    footer: "",
    buttons: "",
  })

  // Flows create state
  const [showCreateFlow, setShowCreateFlow] = useState(false)
  const [newFlow, setNewFlow] = useState({
    name: "",
    trigger: "",
    firstStep: "",
    responseStep: "",
  })

  // Broadcasts create state
  const [showCreateBroadcast, setShowCreateBroadcast] = useState(false)
  const [newBroadcast, setNewBroadcast] = useState({ name: "", content: "", template_name: "" })
  const [sendNotice, setSendNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null)

  const handleCreateGroup = async () => {
    if (!newGroup.name.trim()) return
    const ok = await runWrite("POST", "/whatsapp/groups", {
      name: newGroup.name.trim(),
      sender_id: senders[0]?.id,
      invite_link: newGroup.invite_link || undefined,
    })
    if (ok) {
      setShowCreateGroup(false)
      setNewGroup({ name: "", invite_link: "" })
      reloadGroups()
    }
  }

  const handleCreateTemplate = async () => {
    if (!newTemplate.name || !newTemplate.body) return
    const ok = await runWrite("POST", "/whatsapp/templates", {
      ...newTemplate,
      buttons: newTemplate.buttons ? newTemplate.buttons.split(",").map((b) => b.trim()).filter(Boolean) : [],
    })
    if (ok) {
      setShowCreateTemplate(false)
      setNewTemplate({ name: "", category: "MARKETING", language: "en_US", header: "", body: "", footer: "", buttons: "" })
      reloadTemplates()
    }
  }

  const handleCreateFlow = async () => {
    if (!newFlow.name || !newFlow.trigger) return
    const ok = await runWrite("POST", "/whatsapp/flows", {
      name: newFlow.name,
      trigger: newFlow.trigger,
      nodes: [
        { id: "node-1", type: "trigger", label: newFlow.trigger },
        { id: "node-2", type: "menu", label: newFlow.firstStep || "Present Options Menu" },
        { id: "node-3", type: "action", label: newFlow.responseStep || "Execute Automated Action" },
      ],
    })
    if (ok) {
      setShowCreateFlow(false)
      setNewFlow({ name: "", trigger: "", firstStep: "", responseStep: "" })
      reloadFlows()
    }
  }

  const handleCreateBroadcast = async () => {
    if (!newBroadcast.name || !newBroadcast.content) return
    const ok = await runWrite("POST", "/whatsapp/broadcasts", newBroadcast)
    if (ok) {
      setShowCreateBroadcast(false)
      setNewBroadcast({ name: "", content: "", template_name: "" })
      reloadBroadcasts()
    }
  }

  const handleSendBroadcast = async (id: string) => {
    setSendNotice(null)
    const res = await sendWhatsAppBroadcast(id)
    if (!res.ok) {
      setSendNotice({ kind: "error", text: describeMutationError(res.status, res.error) })
    } else if (res.data?.status === "FAILED") {
      setSendNotice({ kind: "error", text: "Broadcast failed for all recipients — check the WhatsApp connection and template." })
    } else if (res.data?.status === "PARTIAL") {
      setSendNotice({ kind: "error", text: "Broadcast sent with some failures. See recipient statuses." })
    } else if (res.data?.status === "SENDING") {
      setSendNotice({ kind: "ok", text: "Broadcast submitted to WhatsApp — delivery is tracked per recipient." })
    } else {
      setSendNotice({ kind: "ok", text: `Server reports broadcast status: ${res.data?.status ?? "unknown"}.` })
    }
    reloadBroadcasts()
  }

  if (primaryLoad.state !== "ready") {
    return (
      <div className="space-y-4">
        <h2 className="text-xl font-bold tracking-tight text-foreground">WhatsApp</h2>
        <NotConnected loadable={primaryLoad} service="The marketing service" onRetry={loadAll} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {actionError && (
        <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
          <p className="text-sm text-red-400">{actionError}</p>
        </div>
      )}
      {/* 1. OVERVIEW VIEW matching Screenshot 4 */}
      {view === "overview" && (
        <div className="space-y-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-xl font-bold tracking-tight text-foreground">WhatsApp</h2>
              <p className="text-xs text-muted-foreground">{senders.length} {senders.length === 1 ? "sender" : "senders"}</p>
            </div>
            <Button
              className="bg-[#25D366] hover:bg-[#1ebd5a] text-black font-semibold shadow-sm"
              onClick={() => {
                setConnectMode(null)
                setShowConnectModal(true)
              }}
            >
              <MessageCircle className="mr-1.5 h-4 w-4" /> Connect WhatsApp
            </Button>
          </div>

          {/* Senders Table matching Screenshot 4 */}
          <Card className="border-border bg-card">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div className="flex items-center gap-2">
                <Input placeholder="Search senders…" className="w-56 text-xs h-8 bg-background/50 border-border" />
                <select className="rounded-md border border-border bg-background/50 px-2.5 py-1 text-xs text-foreground focus:outline-none">
                  <option value="all">All types</option>
                  <option value="sandbox">Sandbox</option>
                  <option value="business">Business</option>
                </select>
                <select className="rounded-md border border-border bg-background/50 px-2.5 py-1 text-xs text-foreground focus:outline-none">
                  <option value="all">Any status</option>
                  <option value="live">Live</option>
                </select>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="py-3 px-4 font-medium">Sender</th>
                      <th className="py-3 px-4 font-medium">Number</th>
                      <th className="py-3 px-4 font-medium">Type</th>
                      <th className="py-3 px-4 font-medium">Name review</th>
                      <th className="py-3 px-4 font-medium">Business verification</th>
                      <th className="py-3 px-4 font-medium text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {senders.map((s) => (
                      <tr key={s.id} className="border-b border-border/60 hover:bg-card/60 transition-colors">
                        <td className="py-3 px-4 font-medium text-foreground">
                          <div className="flex items-center gap-2">
                            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#25D366]/10 text-[#25D366]">
                              <MessageCircle className="h-4 w-4" />
                            </div>
                            <div>
                              <p className="font-semibold text-xs text-foreground">{s.name}</p>
                              <p className="text-[11px] text-muted-foreground">{s.type}</p>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-foreground">{s.number}</td>
                        <td className="py-3 px-4">
                          <span className="inline-flex items-center gap-1 rounded-full border border-border bg-background/50 px-2 py-0.5 text-[11px] text-muted-foreground">
                            {s.type}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-xs text-muted-foreground" title={s.status_error ?? undefined}>{s.name_review ?? "Not reported"}</td>
                        <td className="py-3 px-4 text-xs text-muted-foreground" title={s.status_error ?? undefined}>{s.business_verification ?? "Not reported"}</td>
                        <td className="py-3 px-4 text-right">
                          <Badge variant="outline" className={`text-[10px] ${s.status ? "border-emerald-500/40 text-emerald-500" : "border-muted text-muted-foreground"}`} title={s.status_error ?? undefined}>
                            {s.status ?? "Not reported"}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* 2. TEMPLATES VIEW */}
      {view === "templates" && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-foreground">Message Templates</h3>
              <p className="text-xs text-muted-foreground">Pre-approved Meta templates for outbound marketing & automated alerts</p>
            </div>
            <Button size="sm" onClick={() => setShowCreateTemplate(!showCreateTemplate)}>
              <Plus className="mr-1.5 h-3.5 w-3.5" /> New Template
            </Button>
          </div>

          {showCreateTemplate && (
            <Card className="border-border bg-card">
              <CardHeader><CardTitle className="text-sm">Create WhatsApp Template</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-3">
                  <Input
                    placeholder="Template name (e.g. order_update)"
                    value={newTemplate.name}
                    onChange={(e) => setNewTemplate({ ...newTemplate, name: e.target.value })}
                  />
                  <select
                    value={newTemplate.category}
                    onChange={(e) => setNewTemplate({ ...newTemplate, category: e.target.value })}
                    className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
                  >
                    <option value="MARKETING">Marketing</option>
                    <option value="UTILITY">Utility</option>
                    <option value="AUTHENTICATION">Authentication</option>
                  </select>
                  <Input
                    placeholder="Language (e.g. en_US)"
                    value={newTemplate.language}
                    onChange={(e) => setNewTemplate({ ...newTemplate, language: e.target.value })}
                  />
                </div>
                <Input
                  placeholder="Header text (optional)"
                  value={newTemplate.header}
                  onChange={(e) => setNewTemplate({ ...newTemplate, header: e.target.value })}
                />
                <Textarea
                  placeholder="Body text. Use {{1}}, {{2}} for dynamic customer parameters..."
                  value={newTemplate.body}
                  onChange={(e) => setNewTemplate({ ...newTemplate, body: e.target.value })}
                  rows={4}
                  className="resize-none"
                />
                <Input
                  placeholder="Buttons (comma-separated, e.g. View Quote, Chat Agent)"
                  value={newTemplate.buttons}
                  onChange={(e) => setNewTemplate({ ...newTemplate, buttons: e.target.value })}
                />
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleCreateTemplate}>Submit Template</Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowCreateTemplate(false)}>Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {templates.length === 0 && <NoDataYet message="No templates yet. Create one to get started." />}
          <div className="grid gap-4 sm:grid-cols-2">
            {templates.map((tpl) => (
              <Card key={tpl.id} className="border-border bg-card">
                <CardContent className="p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-semibold text-sm text-foreground font-mono">{tpl.name}</p>
                      <p className="text-[11px] text-muted-foreground">{tpl.category} · {tpl.language}</p>
                    </div>
                    <Badge variant="outline" className="border-emerald-500/40 text-emerald-500 text-[10px]">
                      {tpl.status}
                    </Badge>
                  </div>
                  {tpl.header && <p className="font-semibold text-xs text-foreground">{tpl.header}</p>}
                  <p className="text-xs text-muted-foreground whitespace-pre-line rounded-md bg-background/50 p-3 border border-border">
                    {tpl.body}
                  </p>
                  {tpl.buttons && tpl.buttons.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {tpl.buttons.map((b) => (
                        <span key={b} className="rounded border border-border bg-card px-2 py-0.5 text-[10px] text-foreground">
                          🔘 {b}
                        </span>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* 3. FLOWS VIEW */}
      {view === "flows" && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-foreground">WhatsApp Conversation Flows</h3>
              <p className="text-xs text-muted-foreground">Automated multi-step branching dialogs and lead capture journeys</p>
            </div>
            <Button size="sm" onClick={() => setShowCreateFlow(!showCreateFlow)}>
              <Plus className="mr-1.5 h-3.5 w-3.5" /> New Flow
            </Button>
          </div>

          {showCreateFlow && (
            <Card className="border-border bg-card">
              <CardHeader><CardTitle className="text-sm">Create Conversational Flow</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <Input
                  placeholder="Flow Name (e.g. Abandoned Cart Recovery)"
                  value={newFlow.name}
                  onChange={(e) => setNewFlow({ ...newFlow, name: e.target.value })}
                />
                <Input
                  placeholder="Trigger (e.g. Inbound message containing 'PROMO')"
                  value={newFlow.trigger}
                  onChange={(e) => setNewFlow({ ...newFlow, trigger: e.target.value })}
                />
                <Input
                  placeholder="Step 1: First interactive menu prompt"
                  value={newFlow.firstStep}
                  onChange={(e) => setNewFlow({ ...newFlow, firstStep: e.target.value })}
                />
                <Input
                  placeholder="Step 2: Automated response or CRM sync action"
                  value={newFlow.responseStep}
                  onChange={(e) => setNewFlow({ ...newFlow, responseStep: e.target.value })}
                />
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleCreateFlow}>Create Flow</Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowCreateFlow(false)}>Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {flows.length === 0 && <NoDataYet message="No flows yet. Create one to get started." />}
          <div className="space-y-4">
            {flows.map((flow) => (
              <Card key={flow.id} className="border-border bg-card">
                <CardContent className="p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-semibold text-sm text-foreground">{flow.name}</p>
                      <p className="text-xs text-muted-foreground">Trigger: {flow.trigger}</p>
                    </div>
                    <Badge variant="outline" className="border-emerald-500/40 text-emerald-500 text-[10px]">
                      {flow.status}
                    </Badge>
                  </div>
                  {/* Flow Node Progression preview */}
                  <div className="flex flex-wrap items-center gap-2 pt-2">
                    {flow.nodes.map((node, i) => (
                      <div key={node.id} className="flex items-center gap-2">
                        <div className="rounded-lg border border-border bg-background/50 px-3 py-1.5 text-xs text-foreground shadow-sm">
                          <span className="font-semibold text-primary mr-1.5">{i + 1}.</span>
                          {node.label}
                        </div>
                        {i < flow.nodes.length - 1 && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* 4. BROADCASTS VIEW */}
      {view === "broadcasts" && (
        <div className="space-y-4">
          {sendNotice && (
            <div className={`rounded-lg border p-3 text-sm ${sendNotice.kind === "ok" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-600" : "border-red-500/40 bg-red-500/10 text-red-600"}`}>
              {sendNotice.text}
            </div>
          )}
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">{broadcasts.length} broadcasts</p>
            <Button size="sm" onClick={() => setShowCreateBroadcast(!showCreateBroadcast)}>
              <Plus className="mr-2 h-4 w-4" /> New Broadcast
            </Button>
          </div>

          {showCreateBroadcast && (
            <Card className="border-border bg-card">
              <CardHeader><CardTitle className="text-sm">Create Broadcast</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <Input placeholder="Broadcast name" value={newBroadcast.name} onChange={(e) => setNewBroadcast({ ...newBroadcast, name: e.target.value })} />
                <Input placeholder="Template name (optional)" value={newBroadcast.template_name} onChange={(e) => setNewBroadcast({ ...newBroadcast, template_name: e.target.value })} />
                <Textarea placeholder="Message content..." value={newBroadcast.content} onChange={(e) => setNewBroadcast({ ...newBroadcast, content: e.target.value })} rows={4} className="resize-none" />
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleCreateBroadcast}>Create</Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowCreateBroadcast(false)}>Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {broadcasts.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">No broadcasts yet</div>
          ) : (
            <div className="space-y-3">
              {broadcasts.map((b: any) => (
                <Card key={b.id} className="border-border bg-card">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <p className="font-medium text-foreground">{b.name}</p>
                        <p className="text-xs text-muted-foreground">{b.template_name || "No template"}</p>
                      </div>
                      <Badge variant="outline" className={statusColor[b.status] || "border-muted text-muted-foreground"}>{b.status}</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground line-clamp-2 mb-3">{b.content}</p>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4 text-xs text-muted-foreground">
                        <span>Recipients: {b.recipient_count || 0}</span>
                        <span>Sent: {b.sent_count || 0}</span>
                        <span>Delivered: {b.delivered_count || 0}</span>
                        <span>Read: {b.read_count || 0}</span>
                      </div>
                      {b.status === "DRAFT" && (
                        <Button size="sm" onClick={() => handleSendBroadcast(b.id)}><Send className="mr-1 h-3 w-3" /> Send</Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 5. CONTACTS VIEW */}
      {view === "contacts" && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">{contacts.length} contacts</p>
          {contacts.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">No contacts yet</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[600px]">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Name</th>
                    <th className="py-2 pr-4 font-medium">Phone</th>
                    <th className="py-2 pr-4 font-medium">Tags</th>
                    <th className="py-2 font-medium">Opt-in</th>
                  </tr>
                </thead>
                <tbody>
                  {contacts.map((c: any) => (
                    <tr key={c.id} className="border-b border-border/60 text-sm">
                      <td className="py-3 pr-4 text-foreground">{c.name}</td>
                      <td className="py-3 pr-4 text-muted-foreground">{c.phone_number}</td>
                      <td className="py-3 pr-4 text-muted-foreground">{(c.tags || []).join(", ")}</td>
                      <td className="py-3"><Badge variant="outline" className={c.opt_in_status === "OPTED_IN" ? "border-emerald-500/40 text-emerald-500" : "border-red-500/40 text-red-400"}>{c.opt_in_status}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* 4. GROUPS VIEW — Faithfully matching Screenshot 6 (zernio.com/dashboard/whatsapp_groups) */}
      {view === "groups" && (
        <div className="space-y-6">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-xl font-bold tracking-tight text-foreground">Groups</h2>
              <p className="text-xs text-muted-foreground">
                Manage the WhatsApp groups this sender belongs to
              </p>
            </div>
            {senders.length > 0 && (
              <Button size="sm" onClick={() => setShowCreateGroup(!showCreateGroup)}>
                <Plus className="mr-1.5 h-3.5 w-3.5" /> Add Group
              </Button>
            )}
          </div>

          {showCreateGroup && (
            <Card className="border-border bg-card">
              <CardHeader><CardTitle className="text-sm">Register WhatsApp Group</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <Input
                  placeholder="Group Name (e.g. Cape Town MetroFibre Expansion Leads)"
                  value={newGroup.name}
                  onChange={(e) => setNewGroup({ ...newGroup, name: e.target.value })}
                />
                <Input
                  placeholder="Invite Link (e.g. https://chat.whatsapp.com/invite/...)"
                  value={newGroup.invite_link}
                  onChange={(e) => setNewGroup({ ...newGroup, invite_link: e.target.value })}
                />
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleCreateGroup}>Save Group</Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowCreateGroup(false)}>Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* If no sender is connected, display EXACT card from Screenshot 6 */}
          {senders.length === 0 ? (
            <div className="rounded-xl border border-border bg-card/60 p-16 text-center space-y-4 shadow-sm">
              <p className="text-sm text-muted-foreground">
                Connect a WhatsApp sender first, then manage its groups here.
              </p>
              <div>
                <Button
                  className="bg-[#ea384c] hover:bg-[#d92b3f] text-white font-semibold px-5 shadow-sm"
                  onClick={() => {
                    setConnectMode(null)
                    setShowConnectModal(true)
                  }}
                >
                  <Plus className="mr-1.5 h-4 w-4" /> Connect WhatsApp
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between rounded-lg border border-border bg-background/60 px-4 py-3 text-xs">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="font-semibold text-foreground">Active Sender:</span>
                  <span className="text-muted-foreground">{senders[0]?.name} ({senders[0]?.number})</span>
                </div>
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-500 text-[10px]">
                  {groups.length} {groups.length === 1 ? "group" : "groups"}
                </Badge>
              </div>

              {groups.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border p-12 text-center text-muted-foreground text-sm">
                  No groups linked to this sender yet.
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {groups.map((g) => (
                    <Card key={g.id} className="border-border bg-card hover:border-border/80 transition-colors">
                      <CardContent className="p-4 space-y-3">
                        <div className="flex items-start justify-between">
                          <div className="space-y-1">
                            <p className="font-semibold text-sm text-foreground">{g.name}</p>
                            <p className="text-[11px] text-muted-foreground">
                              Sender: {g.sender_name || senders[0]?.name}
                            </p>
                          </div>
                          <Badge variant="outline" className="text-[10px] border-border text-foreground">
                            {g.role}
                          </Badge>
                        </div>
                        <div className="flex items-center justify-between pt-2 border-t border-border/60 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <Users className="h-3.5 w-3.5 text-primary" /> {g.participant_count} participants
                          </span>
                        </div>
                        {g.invite_link && (
                          <a
                            href={g.invite_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[11px] text-primary hover:underline block truncate"
                          >
                            {g.invite_link}
                          </a>
                        )}
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 5. CONVERSIONS VIEW — WhatsApp Lead & Sales CRM Attributions */}
      {view === "conversions" && (
        <div className="space-y-6">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-xl font-bold tracking-tight text-foreground">WhatsApp Conversions</h2>
              <p className="text-xs text-muted-foreground">
                Automated deal creation and sales revenue attributed to WhatsApp flows and lead captures
              </p>
            </div>
          </div>

          {/* Notice banner highlighting feed to Sales Dome under Marketing channel */}
          <div className="flex items-center justify-between rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 text-xs">
            <div className="flex items-center gap-2">
              <Megaphone className="h-4 w-4 text-primary" />
              <span className="text-foreground">
                All WhatsApp CTA inquires and campaign leads feed directly into <strong>Sales Dome</strong> under channel <strong>"Marketing Campaigns" (MARKETING)</strong>.
              </span>
            </div>
          </div>

          {/* Quick Metrics */}
          <div className="grid gap-3 sm:grid-cols-4">
            <Card className="border-border bg-card">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">WhatsApp Leads</p>
                <p className="text-2xl font-bold text-foreground mt-1">{conversions.length}</p>
              </CardContent>
            </Card>
            <Card className="border-border bg-card">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">Deals Created in Sales</p>
                <p className="text-2xl font-bold text-foreground mt-1">{conversions.filter((c) => c.status === "DEAL_CREATED" || c.status === "CONVERTED").length}</p>
                <span className="text-[10px] text-cyan-400 font-medium">Channel: MARKETING</span>
              </CardContent>
            </Card>
            <Card className="border-border bg-card">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">Attributed Pipeline</p>
                <p className="text-2xl font-bold text-foreground mt-1">
                  R {conversions.reduce((acc, c) => acc + (c.deal_value_zar || 0), 0).toLocaleString("en-ZA")}
                </p>
                <span className="text-[10px] text-muted-foreground">ZAR Closed & In-Flight</span>
              </CardContent>
            </Card>
            <Card className="border-border bg-card">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">Flow Conversion Rate</p>
                <p className="text-2xl font-bold text-foreground mt-1">
                  {conversions.length > 0 ? `${((conversions.filter((c) => c.status === "CONVERTED").length / conversions.length) * 100).toFixed(1)}%` : "No leads yet"}
                </p>
                <span className="text-[10px] text-muted-foreground">Converted / all leads</span>
              </CardContent>
            </Card>
          </div>

          {/* Conversions Log Table */}
          <Card className="border-border bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Attributed WhatsApp Deals</CardTitle>
              <CardDescription className="text-xs">
                Deals attributed to WhatsApp
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px] text-left text-xs">
                  <thead className="border-b border-border bg-muted/20 text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2.5 font-medium">Customer</th>
                      <th className="px-4 py-2.5 font-medium">Phone</th>
                      <th className="px-4 py-2.5 font-medium">Deal Package</th>
                      <th className="px-4 py-2.5 font-medium">Value (ZAR)</th>
                      <th className="px-4 py-2.5 font-medium">Trigger / Flow</th>
                      <th className="px-4 py-2.5 font-medium">Sales Channel</th>
                      <th className="px-4 py-2.5 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {conversions.length === 0 && (
                      <tr><td colSpan={7} className="px-4 py-10 text-center text-muted-foreground">No WhatsApp conversions yet.</td></tr>
                    )}
                    {conversions.map((conv) => (
                      <tr key={conv.id} className="hover:bg-muted/10 transition-colors">
                        <td className="px-4 py-3 font-medium text-foreground">{conv.customer_name}</td>
                        <td className="px-4 py-3 text-muted-foreground">{conv.phone_number}</td>
                        <td className="px-4 py-3 text-foreground">{conv.deal_name}</td>
                        <td className="px-4 py-3 font-semibold text-foreground">
                          R {conv.deal_value_zar.toLocaleString("en-ZA")}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          <span className="rounded bg-background/80 px-2 py-0.5 border border-border font-mono text-[10px]">
                            {conv.flow_or_template}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="outline" className="border-red-500/40 text-red-400 text-[10px]">
                            {conv.sales_channel}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">
                          <Badge
                            variant="outline"
                            className={
                              conv.status === "CONVERTED"
                                ? "border-emerald-500/40 text-emerald-500 text-[10px]"
                                : "border-blue-500/40 text-blue-400 text-[10px]"
                            }
                          >
                            {conv.status}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Connect WhatsApp: Meta Embedded Signup inside OmniDome */}
      {showConnectModal && (
        <ConnectPlatformDialog
          platform={{ id: "whatsapp", label: "WhatsApp", flow: "embedded_signup", category: "social" }}
          category="social"
          returnTo="/dashboard?section=marketing&marketing_tab=whatsapp-overview"
          onClose={() => setShowConnectModal(false)}
          onConnected={() => { setShowConnectModal(false); reloadSenders() }}
        />
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// ADS TAB (Zernio-style Ads & Boosted Posts)
// ═══════════════════════════════════════════════════════════════════════════════

function AdsTab({ initialSubTab = "campaigns" }: { initialSubTab?: "campaigns" | "audiences" | "lead-forms" } = {}) {
  const [activeSubTab, setActiveSubTab] = useState<"campaigns" | "audiences" | "lead-forms">(initialSubTab)
  const { value: adsLoad, reload: loadAds } = useMarketingLoad<any[]>(adCampaignsPath())
  const { value: accountsLoad } = useMarketingLoad<any[]>(socialAccountsPath())
  const ads: any[] = adsLoad.state === "ready" ? adsLoad.data : []
  const socialAccounts: any[] = accountsLoad.state === "ready" ? accountsLoad.data : []
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [adError, setAdError] = useState<string | null>(null)

  // Filters matching Screenshot 2: All profiles | All ads | All platforms | All accounts | All statuses | Last 30 days | Newest first
  const [filterPlatform, setFilterPlatform] = useState("all")
  const [filterAccount, setFilterAccount] = useState("all")
  const [filterStatus, setFilterStatus] = useState("all")
  const [filterDateRange, setFilterDateRange] = useState("30d")
  const [filterSort, setFilterSort] = useState("newest")

  // Create Ad Modal state matching Screenshot 3
  const [primaryText, setPrimaryText] = useState("")
  const [headline, setHeadline] = useState("")
  const [destinationUrl, setDestinationUrl] = useState("")
  const [mediaFile, setMediaFile] = useState<string | null>(null)
  const [adName, setAdName] = useState("")
  const [selectedGoal, setSelectedGoal] = useState<"Engagement" | "Traffic" | "Awareness" | "Video Views">("Engagement")
  const [budgetAmount, setBudgetAmount] = useState("5")
  const [budgetType, setBudgetType] = useState<"daily" | "total">("daily")
  const [selectedAudience, setSelectedAudience] = useState("")
  const [createAsPaused, setCreateAsPaused] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  // Boost Post Modal state matching media_1789288184604.png
  const [showBoostModal, setShowBoostModal] = useState(false)
  const [boostAdName, setBoostAdName] = useState("My Boosted Post")
  const [boostGoal, setBoostGoal] = useState<"Engagement" | "Traffic" | "Awareness" | "Video Views">("Engagement")
  const [boostBudget, setBoostBudget] = useState("5")
  const [boostBudgetType, setBoostBudgetType] = useState<"daily" | "total">("daily")
  const [boostCountries, setBoostCountries] = useState("")
  const [boostAgeMin, setBoostAgeMin] = useState("")
  const [boostAgeMax, setBoostAgeMax] = useState("")
  const [boostGender, setBoostGender] = useState("All")
  const [isBoosting, setIsBoosting] = useState(false)

  const clearFilters = () => {
    setFilterPlatform("all")
    setFilterAccount("all")
    setFilterStatus("all")
    setFilterDateRange("30d")
    setFilterSort("newest")
  }

  const filteredAds = ads
    .filter((ad: any) => {
      if (filterStatus !== "all" && ad.status?.toLowerCase() !== filterStatus.toLowerCase()) return false
      if (filterPlatform !== "all" && ad.platform?.toLowerCase() !== filterPlatform.toLowerCase()) return false
      if (filterAccount !== "all" && ad.account_id && ad.account_id !== filterAccount) return false
      if (filterDateRange !== "all") {
        const days = filterDateRange === "7d" ? 7 : filterDateRange === "90d" ? 90 : 30
        const t = new Date(ad.created_at || 0).getTime()
        if (Number.isFinite(t) && t > 0 && Date.now() - t > days * 86_400_000) return false
      }
      return true
    })
    .sort((a: any, b: any) => {
      const ts = (x: any) => new Date(x.created_at || 0).getTime()
      if (filterSort === "oldest") return ts(a) - ts(b)
      if (filterSort === "spend_high") return (b.spend_zar || 0) - (a.spend_zar || 0)
      if (filterSort === "roas_high") return (b.roas || 0) - (a.roas || 0)
      return ts(b) - ts(a)
    })

  return (
    <div className="space-y-6">
      {/* Top Tab Strip matching Screenshot 2: Campaigns | Audiences | Lead Forms */}
      <div className="flex border-b border-border text-sm font-medium">
        <button
          onClick={() => setActiveSubTab("campaigns")}
          className={`border-b-2 px-4 py-2.5 transition-colors ${
            activeSubTab === "campaigns"
              ? "border-primary text-foreground font-semibold"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Campaigns
        </button>
        <button
          onClick={() => setActiveSubTab("audiences")}
          className={`border-b-2 px-4 py-2.5 transition-colors ${
            activeSubTab === "audiences"
              ? "border-primary text-foreground font-semibold"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Audiences
        </button>
        <button
          onClick={() => setActiveSubTab("lead-forms")}
          className={`border-b-2 px-4 py-2.5 transition-colors ${
            activeSubTab === "lead-forms"
              ? "border-primary text-foreground font-semibold"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Lead Forms
        </button>
      </div>

      {activeSubTab === "campaigns" && (
        <div className="space-y-6">
          {/* Header Row: Title & description on left, + Create Ad (Coral Red) & Boost Post on right */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-xl font-bold tracking-tight text-foreground">Ads</h2>
              <p className="text-xs text-muted-foreground">Manage boosted post ads</p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                className="bg-[#e03131] hover:bg-[#c92a2a] text-white font-medium shadow-sm"
                onClick={() => setShowCreateModal(true)}
              >
                <Plus className="mr-1.5 h-4 w-4" /> Create Ad
              </Button>
              <Button
                variant="outline"
                className="border-border text-foreground hover:bg-card"
                onClick={() => setShowBoostModal(true)}
              >
                <Sparkles className="mr-1.5 h-4 w-4 text-amber-500" /> Boost Post
              </Button>
            </div>
          </div>

          {/* Zernio Filter Bar matching Screenshot 2 */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <select
              value={filterPlatform}
              onChange={(e) => setFilterPlatform(e.target.value)}
              className="rounded-md border border-border bg-card px-2.5 py-1.5 text-foreground hover:border-border/80 focus:outline-none"
            >
              <option value="all">All platforms</option>
              <option value="facebook">Facebook</option>
              <option value="instagram">Instagram</option>
              <option value="google">Google</option>
              <option value="linkedin">LinkedIn</option>
              <option value="tiktok">TikTok</option>
            </select>

            <select
              value={filterAccount}
              onChange={(e) => setFilterAccount(e.target.value)}
              className="rounded-md border border-border bg-card px-2.5 py-1.5 text-foreground hover:border-border/80 focus:outline-none"
            >
              <option value="all">All accounts</option>
              {socialAccounts.map((a) => (
                <option key={a.id} value={a.id}>{a.account_name || a.platform}</option>
              ))}
            </select>

            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="rounded-md border border-border bg-card px-2.5 py-1.5 text-foreground hover:border-border/80 focus:outline-none"
            >
              <option value="all">All statuses</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="draft">Draft</option>
              <option value="completed">Completed</option>
            </select>

            <select
              value={filterDateRange}
              onChange={(e) => setFilterDateRange(e.target.value)}
              className="rounded-md border border-border bg-card px-2.5 py-1.5 text-foreground hover:border-border/80 focus:outline-none"
            >
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
              <option value="90d">Last 90 days</option>
              <option value="all">All time</option>
            </select>

            <select
              value={filterSort}
              onChange={(e) => setFilterSort(e.target.value)}
              className="rounded-md border border-border bg-card px-2.5 py-1.5 text-foreground hover:border-border/80 focus:outline-none"
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="spend_high">Highest spend</option>
              <option value="roas_high">Highest ROAS</option>
            </select>

            <button
              onClick={clearFilters}
              className="flex items-center gap-1 text-muted-foreground hover:text-foreground px-2 py-1.5 transition-colors"
            >
              <X className="h-3 w-3" /> Clear filters
            </button>
          </div>

          {/* Ads List or Empty State matching Screenshot 2 */}
          {adsLoad.state !== "ready" ? (
            <NotConnected loadable={adsLoad} service="The marketing service" onRetry={loadAds} />
          ) : filteredAds.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/40 py-20 text-center">
              <Megaphone className="h-10 w-10 text-muted-foreground/50 mb-3" />
              <p className="font-semibold text-foreground">No ads yet</p>
              <p className="mt-1 max-w-sm text-xs text-muted-foreground">
                Boost a published post or create a standalone ad to get started
              </p>
              <div className="mt-5 flex gap-2">
                <Button
                  size="sm"
                  className="bg-[#e03131] hover:bg-[#c92a2a] text-white"
                  onClick={() => setShowCreateModal(true)}
                >
                  <Plus className="mr-1.5 h-3.5 w-3.5" /> Create Ad
                </Button>
                <Button size="sm" variant="outline" onClick={() => setShowBoostModal(true)}>
                  <Sparkles className="mr-1.5 h-3.5 w-3.5 text-amber-500" /> Boost Post
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredAds.map((ad: any) => (
                <Card key={ad.id} className="border-border bg-card">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <p className="font-medium text-foreground">{ad.name}</p>
                        <p className="text-xs text-muted-foreground">{ad.platform} · {ad.objective}</p>
                      </div>
                      <Badge variant="outline" className={statusColor[ad.status] || "border-muted text-muted-foreground"}>
                        {ad.status}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mt-3 text-sm">
                      <div><p className="text-xs text-muted-foreground">Budget</p><p className="text-foreground">R {(ad.budget_zar || ad.daily_budget_zar || 0).toLocaleString()}</p></div>
                      <div><p className="text-xs text-muted-foreground">Spend</p><p className="text-foreground">R {(ad.spend_zar || 0).toLocaleString()}</p></div>
                      <div><p className="text-xs text-muted-foreground">Impressions</p><p className="text-foreground">{(ad.impressions || 0).toLocaleString()}</p></div>
                      <div><p className="text-xs text-muted-foreground">Clicks</p><p className="text-foreground">{(ad.clicks || 0).toLocaleString()}</p></div>
                      <div><p className="text-xs text-muted-foreground">ROAS</p><p className="text-foreground">{ad.roas ? `${ad.roas}x` : "—"}</p></div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {activeSubTab === "audiences" && <MarketingAudiences />}

      {activeSubTab === "lead-forms" && <LeadFormsPanel />}

      {showCreateModal && <CreateAdModal onClose={() => setShowCreateModal(false)} onCreated={loadAds} />}

      {/* BOOST POST MODAL — Faithfully matching Screenshot 2 (media_1789288184604.png) */}
      {showBoostModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/70 backdrop-blur-sm">
          <div className="relative flex h-full w-full max-w-xl flex-col border-l border-border bg-background shadow-2xl overflow-hidden animate-in slide-in-from-right duration-200">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-border px-6 py-5">
              <div>
                <h3 className="text-lg font-bold text-foreground">Boost Post</h3>
                <p className="text-xs text-muted-foreground">Turn an existing post into a paid ad</p>
              </div>
              <button
                onClick={() => setShowBoostModal(false)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-card hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Account warning with Go to Connections button */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground block mb-1">account</label>
                <p className="text-xs text-muted-foreground mb-3">
                  No ads accounts connected. Connect an ads platform in Connections to start boosting.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-xs border-border text-foreground hover:bg-card"
                  onClick={() => setShowBoostModal(false)}
                >
                  Go to Connections
                </Button>
              </div>

              {/* Ad Name */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground block mb-1.5">ad name</label>
                <Input
                  placeholder="My Boosted Post"
                  value={boostAdName}
                  onChange={(e) => setBoostAdName(e.target.value)}
                  className="bg-card border-border text-sm"
                />
              </div>

              {/* Goal: 4 cards matching Screenshot 2 */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground block mb-1.5">goal</label>
                <div className="grid grid-cols-2 gap-2">
                  {([
                    { key: "Engagement", icon: MessageSquare },
                    { key: "Traffic", icon: Link2 },
                    { key: "Awareness", icon: Eye },
                    { key: "Video Views", icon: Play },
                  ] as const).map(({ key, icon: Icon }) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setBoostGoal(key)}
                      className={`flex items-center gap-2 rounded-md border p-3 text-xs font-medium transition-colors ${
                        boostGoal === key
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border bg-card text-foreground hover:bg-card/80"
                      }`}
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      <span>{key}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Budget */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground block mb-1.5">budget</label>
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <span className="absolute left-3 top-2.5 text-xs text-muted-foreground">R</span>
                    <Input
                      type="number"
                      value={boostBudget}
                      onChange={(e) => setBoostBudget(e.target.value)}
                      className="pl-6 bg-card border-border text-sm"
                    />
                  </div>
                  <div className="flex rounded-md border border-border p-0.5 text-xs bg-card">
                    <button
                      type="button"
                      onClick={() => setBoostBudgetType("daily")}
                      className={`px-3 py-1.5 rounded transition-colors ${
                        boostBudgetType === "daily" ? "bg-background text-foreground shadow-sm font-medium" : "text-muted-foreground"
                      }`}
                    >
                      Per day
                    </button>
                    <button
                      type="button"
                      onClick={() => setBoostBudgetType("total")}
                      className={`px-3 py-1.5 rounded transition-colors ${
                        boostBudgetType === "total" ? "bg-background text-foreground shadow-sm font-medium" : "text-muted-foreground"
                      }`}
                    >
                      Total
                    </button>
                  </div>
                </div>
              </div>

              {/* Targeting (Countries, Age Min, Age Max, Gender) */}
              <div className="space-y-3">
                <label className="text-xs font-semibold text-muted-foreground block">targeting</label>
                <div>
                  <label className="text-[11px] font-medium text-muted-foreground block mb-1 uppercase tracking-wider">Countries</label>
                  <Input
                    placeholder="Countries, e.g. ZA, GB"
                    value={boostCountries}
                    onChange={(e) => setBoostCountries(e.target.value)}
                    className="bg-card border-border text-xs"
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground block mb-1 uppercase tracking-wider">Age Min</label>
                    <Input
                      type="number"
                      value={boostAgeMin}
                      onChange={(e) => setBoostAgeMin(e.target.value)}
                      className="bg-card border-border text-xs"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground block mb-1 uppercase tracking-wider">Age Max</label>
                    <Input
                      type="number"
                      value={boostAgeMax}
                      onChange={(e) => setBoostAgeMax(e.target.value)}
                      className="bg-card border-border text-xs"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground block mb-1 uppercase tracking-wider">Gender</label>
                    <select
                      value={boostGender}
                      onChange={(e) => setBoostGender(e.target.value)}
                      className="w-full rounded-md border border-border bg-card px-2.5 py-2 text-xs text-foreground focus:outline-none"
                    >
                      <option value="All">All</option>
                      <option value="Male">Male</option>
                      <option value="Female">Female</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>

            {adError && <p role="alert" className="border-t border-border bg-red-500/5 px-6 py-2 text-xs text-red-400">{adError}</p>}
            {/* Modal Footer */}
            <div className="flex items-center justify-end gap-2 border-t border-border bg-card/30 px-6 py-4">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowBoostModal(false)}
              >
                cancel
              </Button>
              <Button
                size="sm"
                disabled={!boostAdName.trim() || isBoosting}
                onClick={async () => {
                  setIsBoosting(true)
                  setAdError(null)
                  const r = await writeMarketing("POST", "/ads/campaigns", {
                    name: boostAdName,
                    platform: "facebook",
                    objective: boostGoal.toUpperCase(),
                    ...(boostBudgetType === "total" ? { budget_zar: Number(boostBudget) } : { daily_budget_zar: Number(boostBudget) }),
                    targeting: { countries: boostCountries, age_min: boostAgeMin, age_max: boostAgeMax, gender: boostGender },
                  })
                  setIsBoosting(false)
                  if (!r.ok) {
                    setAdError(describeMutationError(r.status, r.error))
                    return
                  }
                  setShowBoostModal(false)
                  loadAds()
                }}
                className="bg-muted-foreground text-background hover:bg-foreground hover:text-background font-medium"
              >
                {isBoosting ? "Boosting…" : "Boost Post"}
              </Button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// AUTOMATIONS TAB
// ═══════════════════════════════════════════════════════════════════════════════

function AutomationsTab() {
  const { value: autoLoad, reload: loadAutomations } = useMarketingLoad<any[]>(commentAutomationsPath())
  const automations: any[] = autoLoad.state === "ready" ? autoLoad.data : []
  const [showCreate, setShowCreate] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [newAuto, setNewAuto] = useState({ name: "", account_id: "", trigger_type: "KEYWORD", trigger_keywords: "", response_template: "" })

  const handleCreate = async () => {
    if (!newAuto.name || !newAuto.response_template) return
    setCreating(true)
    setCreateError(null)
    const r = await writeMarketing("POST", "/social/automations", {
      ...newAuto,
      trigger_keywords: newAuto.trigger_keywords.split(",").map((k) => k.trim()).filter(Boolean),
    })
    setCreating(false)
    if (!r.ok) {
      setCreateError(describeMutationError(r.status, r.error))
      return
    }
    setShowCreate(false)
    setNewAuto({ name: "", account_id: "", trigger_type: "KEYWORD", trigger_keywords: "", response_template: "" })
    loadAutomations()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{autoLoad.state === "ready" ? `${automations.length} automations` : ""}</p>
        <Button size="sm" onClick={() => setShowCreate(!showCreate)}><Plus className="mr-2 h-4 w-4" /> New Automation</Button>
      </div>

      {showCreate && (
        <Card className="border-border bg-card">
          <CardHeader><CardTitle className="text-sm">Create Comment Automation</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Input placeholder="Automation name" value={newAuto.name} onChange={(e) => setNewAuto({ ...newAuto, name: e.target.value })} />
            <select value={newAuto.trigger_type} onChange={(e) => setNewAuto({ ...newAuto, trigger_type: e.target.value })} className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
              <option value="KEYWORD">Keyword</option>
              <option value="ALL_COMMENTS">All Comments</option>
              <option value="FIRST_COMMENT">First Comment</option>
            </select>
            {newAuto.trigger_type === "KEYWORD" && (
              <Input placeholder="Keywords (comma-separated)" value={newAuto.trigger_keywords} onChange={(e) => setNewAuto({ ...newAuto, trigger_keywords: e.target.value })} />
            )}
            <Textarea placeholder="Response template..." value={newAuto.response_template} onChange={(e) => setNewAuto({ ...newAuto, response_template: e.target.value })} rows={3} className="resize-none" />
            <div className="flex gap-2">
              <Button size="sm" onClick={handleCreate} disabled={creating}>{creating ? "Creating…" : "Create"}</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            </div>
            {createError && <p role="alert" className="text-sm text-red-400">{createError}</p>}
          </CardContent>
        </Card>
      )}

      {autoLoad.state !== "ready" ? (
        <NotConnected loadable={autoLoad} service="The marketing service" onRetry={loadAutomations} />
      ) : automations.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground">No automations yet</div>
      ) : (
        <div className="space-y-3">
          {automations.map((a: any) => (
            <Card key={a.id} className="border-border bg-card">
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="font-medium text-foreground">{a.name}</p>
                    <p className="text-xs text-muted-foreground">Trigger: {a.trigger_type}</p>
                  </div>
                  <Badge variant="outline" className={a.is_active ? "border-emerald-500/40 text-emerald-500" : "border-gray-500/40 text-gray-400"}>{a.is_active ? "Active" : "Inactive"}</Badge>
                </div>
                <p className="text-sm text-muted-foreground line-clamp-2 mb-2">{a.response_template}</p>
                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                  <span>Triggered: {a.total_triggered || 0}</span>
                  <span>Replied: {a.total_replied || 0}</span>
                  {(a.trigger_keywords || []).length > 0 && <span>Keywords: {(a.trigger_keywords || []).join(", ")}</span>}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TRADITIONAL TAB (existing marketing — radio, billboards, OOH)
// ═══════════════════════════════════════════════════════════════════════════════

const radioTypeColors: Record<string, string> = {
  National: "#4ade80",
  Regional: "#60a5fa",
  Community: "#f59e0b",
}

function TraditionalTab() {
  const { value: tradLoad, reload: reloadTrad } = useMarketingLoad<TraditionalCampaign[]>("/traditional-campaigns")
  const campaigns: TraditionalCampaign[] = tradLoad.state === "ready" ? tradLoad.data : []

  const radioCampaigns = campaigns.filter((c) => c.medium === "radio")
  const oohCampaigns = campaigns.filter((c) => c.medium === "billboard" || c.medium === "ooh_screen")

  const totalSpend = campaigns.reduce((sum, c) => sum + Number(c.spend_zar || 0), 0)
  const totalImpressions = campaigns.reduce((sum, c) => sum + (c.impressions || 0), 0)
  const activeMediums = new Set(campaigns.map((c) => c.medium)).size

  const radioPerformance = Object.values(
    radioCampaigns.reduce((acc: Record<string, { month: string; spots: number; leads: number }>, c) => {
      const key = c.period_month?.slice(0, 7) ?? "Unscheduled"
      acc[key] = acc[key] ?? { month: key, spots: 0, leads: 0 }
      acc[key].spots += c.spots_booked || 0
      acc[key].leads += c.leads_generated || 0
      return acc
    }, {})
  )

  const radioByType = Object.entries(
    radioCampaigns.reduce((acc: Record<string, number>, c) => {
      const key = c.category ?? "Uncategorized"
      acc[key] = (acc[key] ?? 0) + 1
      return acc
    }, {})
  ).map(([name, value]) => ({ name, value, fill: radioTypeColors[name] ?? "#a78bfa" }))

  const kpis = [
    { label: "Campaigns Recorded", value: String(campaigns.length), icon: BarChart3, color: "text-blue-400", bg: "bg-blue-500/10" },
    { label: "Total Impressions", value: totalImpressions.toLocaleString(), icon: Users, color: "text-emerald-400", bg: "bg-emerald-500/10" },
    { label: "Total Spend", value: `R ${totalSpend.toLocaleString()}`, icon: TrendingUp, color: "text-amber-400", bg: "bg-amber-500/10" },
    { label: "Active Mediums", value: String(activeMediums), icon: Radio, color: "text-purple-400", bg: "bg-purple-500/10" },
  ]

  if (tradLoad.state !== "ready") {
    return <NotConnected loadable={tradLoad} service="The marketing service" onRetry={reloadTrad} />
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((kpi) => (
          <Card key={kpi.label} className="border-border bg-card">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div><p className="text-xs text-muted-foreground">{kpi.label}</p><p className="text-2xl font-semibold text-foreground">{kpi.value}</p></div>
                <div className={`rounded-lg ${kpi.bg} p-2`}><kpi.icon className={`h-5 w-5 ${kpi.color}`} /></div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {campaigns.length === 0 && (
        <Card className="border-border bg-card">
          <CardContent className="p-8 text-center text-sm text-muted-foreground">
            No traditional media campaigns recorded yet. Use{" "}
            <code className="rounded bg-secondary px-1.5 py-0.5">POST /traditional-campaigns</code> on the marketing
            service to log radio, billboard, or OOH screen buys.
          </CardContent>
        </Card>
      )}

      {/* Radio + Billboard */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Radio Performance</CardTitle><CardDescription>Spots and leads by month</CardDescription></CardHeader>
          <CardContent><div className="h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={radioPerformance}><CartesianGrid strokeDasharray="3 3" stroke="#404040" /><XAxis dataKey="month" tick={{ fill: "#737373", fontSize: 12 }} /><YAxis tick={{ fill: "#737373", fontSize: 12 }} /><Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} /><Legend /><Bar dataKey="spots" fill="#4ade80" name="Spots" /><Bar dataKey="leads" fill="#60a5fa" name="Leads" /></BarChart></ResponsiveContainer></div></CardContent>
        </Card>
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Radio by Type</CardTitle></CardHeader>
          <CardContent><div className="h-64"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={radioByType} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>{radioByType.map((e, i) => <Cell key={i} fill={e.fill} />)}</Pie><Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} /></PieChart></ResponsiveContainer></div></CardContent>
        </Card>
      </div>

      {/* Radio Stations Table */}
      <Card className="border-border bg-card">
        <CardHeader><CardTitle>Radio Campaigns</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px]">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Station</th><th className="py-2 pr-4 font-medium">Type</th>
                  <th className="py-2 pr-4 font-medium">Reach</th><th className="py-2 pr-4 font-medium">Spots</th>
                  <th className="py-2 pr-4 font-medium">Spend</th><th className="py-2 font-medium">Leads</th>
                </tr>
              </thead>
              <tbody>
                {radioCampaigns.map((row) => (
                  <tr key={row.id} className="border-b border-border/60 text-sm">
                    <td className="py-3 pr-4 text-foreground font-medium">{row.name}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.category ?? "—"}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.reach ?? "—"}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.spots_booked}</td>
                    <td className="py-3 pr-4 text-muted-foreground">R {Number(row.spend_zar).toLocaleString()}</td>
                    <td className="py-3 text-muted-foreground">{row.leads_generated}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* OOH Metrics */}
      <Card className="border-border bg-card">
        <CardHeader><CardTitle>Out-of-Home Advertising</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px]">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Medium</th><th className="py-2 pr-4 font-medium">Name</th>
                  <th className="py-2 pr-4 font-medium">Category</th><th className="py-2 pr-4 font-medium">Impressions</th>
                  <th className="py-2 pr-4 font-medium">Spend</th><th className="py-2 font-medium">Leads</th>
                </tr>
              </thead>
              <tbody>
                {oohCampaigns.map((row) => (
                  <tr key={row.id} className="border-b border-border/60 text-sm">
                    <td className="py-3 pr-4 text-foreground font-medium">{row.medium}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.name}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.category ?? "—"}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.impressions.toLocaleString()}</td>
                    <td className="py-3 pr-4 text-muted-foreground">R {Number(row.spend_zar).toLocaleString()}</td>
                    <td className="py-3 text-muted-foreground">{row.leads_generated}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// SMS SENDER IDS TAB (Zernio media_1789297416997.png & media_1789297828199.png)
// ═══════════════════════════════════════════════════════════════════════════════

function SmsSenderIdsTab() {
  const { value: sendersLoad, reload: load } = useMarketingLoad<SmsSenderId[]>("/sms/senders")
  const senders: SmsSenderId[] = sendersLoad.state === "ready" ? sendersLoad.data : []
  const loading = sendersLoad.state === "loading"
  const [isDrawerOpen, setIsDrawerOpen] = useState(false)
  const [senderInput, setSenderInput] = useState("")
  const [creating, setCreating] = useState(false)
  const [smsError, setSmsError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [testModalOpen, setTestModalOpen] = useState(false)
  const [selectedSenderForTest, setSelectedSenderForTest] = useState<SmsSenderId | null>(null)
  const [testRecipient, setTestRecipient] = useState("")
  const [testMessage, setTestMessage] = useState("")
  const [sendingTest, setSendingTest] = useState(false)
  const [testNotice, setTestNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null)

  const handleCreateSender = async () => {
    const clean = senderInput.trim().replace(/[^a-zA-Z0-9]/g, "")
    if (!clean) return
    setCreating(true)
    setSmsError(null)
    const r = await writeMarketing("POST", "/sms/senders", { sender_id: clean })
    setCreating(false)
    if (!r.ok) {
      setSmsError(describeMutationError(r.status, r.error))
      return
    }
    setSenderInput("")
    setIsDrawerOpen(false)
    load()
  }

  const handleDelete = async (id: string) => {
    setDeletingId(id)
    setSmsError(null)
    const r = await writeMarketing("DELETE", `/sms/senders/${encodeURIComponent(id)}`)
    setDeletingId(null)
    if (!r.ok) {
      setSmsError(describeMutationError(r.status, r.error))
      return
    }
    load()
  }

  const handleSendTestSms = async () => {
    if (!selectedSenderForTest || !testRecipient.trim() || !testMessage.trim()) return
    setSendingTest(true)
    setTestNotice(null)
    const r = await writeMarketing<{ status: string; message_id?: string; provider?: string }>("POST", "/sms/send", {
      sender_id: selectedSenderForTest.sender_id,
      to: testRecipient.trim(),
      message: testMessage.trim(),
    })
    setSendingTest(false)
    if (!r.ok) {
      setTestNotice({ kind: "error", text: describeMutationError(r.status, r.error) })
      return
    }
    setTestNotice({
      kind: "ok",
      text: `Server accepted the SMS (status: ${r.data?.status ?? "unknown"}${r.data?.provider ? `, provider: ${r.data.provider}` : ""}${r.data?.message_id ? `, id: ${r.data.message_id}` : ""}).`,
    })
  }

  return (
    <div className="space-y-6">
      {/* Header matching media_1789297416997.png */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-foreground">Sender IDs</h2>
          <p className="text-xs text-muted-foreground max-w-2xl mt-1 leading-relaxed">
            Branded names shown as the sender of your international SMS, no phone number needed. Text only, no replies, can&apos;t reach the US or Canada.
          </p>
        </div>
        <Button
          onClick={() => {
            setSenderInput("")
            setIsDrawerOpen(true)
          }}
          className="bg-[#EA3829] hover:bg-[#d02e20] text-white font-medium text-xs px-4 h-9 shadow-sm"
        >
          <Plus className="mr-1.5 h-4 w-4" /> New sender ID
        </Button>
      </div>

      {/* Main Container: Empty state or Table */}
      {smsError && <p role="alert" className="text-sm text-red-400">{smsError}</p>}
      {sendersLoad.state !== "ready" ? (
        <NotConnected loadable={sendersLoad} service="The marketing service" onRetry={load} />
      ) : senders.length === 0 ? (
        /* Empty state matching media_1789297416997.png */
        <div className="rounded-xl border border-border bg-card/40 py-24 px-6 text-center shadow-xs">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-lg bg-muted/40 text-muted-foreground/70 border border-border/40">
            <span className="font-serif text-3xl font-normal leading-none select-none text-muted-foreground">T</span>
          </div>
          <h3 className="text-base font-semibold text-foreground">No sender IDs yet</h3>
          <p className="mx-auto mt-1 max-w-md text-xs text-muted-foreground">
            Send SMS as your brand name (e.g. ZERNIO) instead of a phone number.
          </p>
          <div className="mt-5">
            <Button
              variant="outline"
              onClick={() => {
                setSenderInput("")
                setIsDrawerOpen(true)
              }}
              className="text-xs h-9 border-border bg-card hover:bg-accent text-foreground"
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" /> New sender ID
            </Button>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-card shadow-xs overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[600px] text-xs">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground bg-muted/30">
                  <th className="px-5 py-3 font-semibold">Sender ID</th>
                  <th className="px-5 py-3 font-semibold">Type</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold">Created</th>
                  <th className="px-5 py-3 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {senders.map((s) => (
                  <tr key={s.id} className="hover:bg-muted/10 transition-colors">
                    <td className="px-5 py-3.5 font-semibold text-foreground flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-emerald-500" />
                      <span>{s.sender_id}</span>
                    </td>
                    <td className="px-5 py-3.5 text-muted-foreground">
                      {s.type || "Alphanumeric (International)"}
                    </td>
                    <td className="px-5 py-3.5">
                      <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px]">
                        Active
                      </Badge>
                    </td>
                    <td className="px-5 py-3.5 text-muted-foreground">
                      {s.created_at ? new Date(s.created_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-5 py-3.5 text-right space-x-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setSelectedSenderForTest(s)
                          setTestNotice(null)
                          setTestModalOpen(true)
                        }}
                        className="text-[11px] h-7 px-2.5"
                      >
                        <Send className="mr-1 h-3 w-3" /> Test SMS
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={deletingId === s.id}
                        onClick={() => handleDelete(s.id)}
                        className="text-[11px] h-7 px-2 text-red-400 hover:text-red-300"
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Slide-over Drawer New sender ID (media_1789297828199.png) */}
      {isDrawerOpen && (
        <div className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/70 backdrop-blur-xs">
          <div className="w-full max-w-md bg-card border-l border-border h-full flex flex-col p-6 shadow-2xl overflow-y-auto animate-in slide-in-from-right duration-200">
            {/* Header */}
            <div className="flex items-start justify-between gap-3 mb-2">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-5 w-5 text-foreground shrink-0" />
                <h3 className="text-lg font-bold text-foreground">New sender ID</h3>
              </div>
              <button
                onClick={() => setIsDrawerOpen(false)}
                className="rounded p-1 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="text-xs text-muted-foreground mb-6 leading-relaxed">
              A branded name shown as the sender of your international SMS, no phone number needed. Use it as from when sending.
            </p>

            {/* Input with Counter */}
            <div className="space-y-1.5 mb-2">
              <div className="flex items-center justify-between text-xs">
                <label className="font-semibold text-foreground">Sender ID</label>
                <span className="text-muted-foreground font-mono">{senderInput.length}/11</span>
              </div>
              <Input
                value={senderInput}
                maxLength={11}
                onChange={(e) => setSenderInput(e.target.value.replace(/[^a-zA-Z0-9]/g, ""))}
                placeholder="OmniDome"
                className="h-10 text-sm font-medium"
              />
            </div>

            {/* Red Notice */}
            <p className="text-xs text-[#EA3829] font-medium mb-6">
              SMS features incur carrier fees. Add a payment method to continue.
            </p>

            {/* Bullet Points Info Card */}
            <div className="rounded-xl border border-border bg-accent/20 p-4 space-y-2.5 text-xs text-muted-foreground mb-8">
              <div className="flex items-start gap-2">
                <span className="text-foreground leading-tight">•</span>
                <span>One-way only: recipients can&apos;t reply</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-foreground leading-tight">•</span>
                <span>Can&apos;t reach the US, Canada, or Puerto Rico</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-foreground leading-tight">•</span>
                <span>Text only, no picture (MMS) messages</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-foreground leading-tight">•</span>
                <span>Names impersonating known brands are rejected</span>
              </div>
            </div>

            {/* Actions */}
            <div className="mt-auto pt-6 border-t border-border flex items-center gap-3">
              <Button
                onClick={handleCreateSender}
                disabled={!senderInput.trim() || creating}
                className="bg-[#EA3829] hover:bg-[#d02e20] text-white font-medium text-xs px-5 h-9"
              >
                {creating ? "Creating..." : "Create sender ID"}
              </Button>
              <Button
                variant="outline"
                onClick={() => setIsDrawerOpen(false)}
                className="text-xs h-9 border-border bg-card hover:bg-accent"
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Test SMS Modal */}
      {testModalOpen && selectedSenderForTest && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                <Send className="h-4 w-4 text-[#EA3829]" />
                Test SMS Dispatch
              </h3>
              <button onClick={() => setTestModalOpen(false)} className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="font-semibold text-muted-foreground">From (Sender ID)</label>
                <div className="mt-1 font-mono font-bold text-foreground bg-accent/30 rounded px-2.5 py-1.5 border border-border">
                  {selectedSenderForTest.sender_id}
                </div>
              </div>

              <div>
                <label className="font-semibold text-muted-foreground">Recipient Number (E.164)</label>
                <Input
                  value={testRecipient}
                  onChange={(e) => setTestRecipient(e.target.value)}
                  placeholder="+country code and number"
                  className="mt-1 h-9 text-xs"
                />
              </div>

              <div>
                <label className="font-semibold text-muted-foreground">Message</label>
                <Textarea
                  value={testMessage}
                  onChange={(e) => setTestMessage(e.target.value)}
                  rows={3}
                  className="mt-1 text-xs resize-none"
                />
              </div>

              {testNotice && (
                <div role={testNotice.kind === "error" ? "alert" : "status"} className={testNotice.kind === "error" ? "rounded-lg bg-red-500/10 border border-red-500/30 p-2.5 text-red-400 text-xs" : "rounded-lg bg-emerald-500/10 border border-emerald-500/30 p-2.5 text-emerald-600 dark:text-emerald-400 text-xs"}>
                  {testNotice.text}
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
              <Button variant="ghost" size="sm" onClick={() => setTestModalOpen(false)} className="text-xs">
                Close
              </Button>
              <Button
                size="sm"
                onClick={handleSendTestSms}
                disabled={sendingTest || !testRecipient.trim()}
                className="bg-[#EA3829] hover:bg-[#d02e20] text-white text-xs font-medium px-4"
              >
                {sendingTest ? "Sending..." : "Dispatch SMS"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TEAM & USERS TAB (Zernio media_1789298463219.png)
// ═══════════════════════════════════════════════════════════════════════════════

function TeamUsersTab() {
  // Real members and invites come from the admin service (the same source as
  // Admin > Team). Nothing here is seeded, and an invite link is shown only
  // when the server returned one.
  const [identity, setIdentity] = useState<Whoami | null>(null)
  const [members, setMembers] = useState<Loadable<TenantMember[]>>({ state: "loading" })
  const [invites, setInvites] = useState<TenantInvite[]>([])
  const [tick, setTick] = useState(0)
  const [searchQuery, setSearchQuery] = useState("")
  const [roleFilter, setRoleFilter] = useState("all")

  // Invite drawer state
  const [isInviteOpen, setIsInviteOpen] = useState(false)
  const [inviteEmails, setInviteEmails] = useState("")
  const [selectedRole, setSelectedRole] = useState("org_user")
  const [sending, setSending] = useState(false)
  const [inviteResults, setInviteResults] = useState<{ email: string; ok: boolean; text: string; link?: string }[]>([])
  const [copiedLink, setCopiedLink] = useState<string | null>(null)
  const [rowError, setRowError] = useState<string | null>(null)

  const tenantId = identity?.tenant_id ?? ""
  const grantable = useMemo(() => grantableRoles(identity?.roles ?? []), [identity])
  const canInvite = grantable.length > 0

  useEffect(() => {
    let alive = true
    setMembers({ state: "loading" })
    ;(async () => {
      try {
        const who = await adminApi.whoami()
        if (!alive) return
        setIdentity(who)
        const [m, i] = await Promise.allSettled([adminApi.listMembers(who.tenant_id), adminApi.listInvites(who.tenant_id)])
        if (!alive) return
        if (m.status === "fulfilled") setMembers({ state: "ready", data: m.value })
        else setMembers(adminFailureToLoadable(m.reason))
        setInvites(i.status === "fulfilled" ? i.value.filter((x) => x.status === "pending") : [])
      } catch (e) {
        if (alive) setMembers(adminFailureToLoadable(e))
      }
    })()
    return () => { alive = false }
  }, [tick])

  const reload = () => setTick((t) => t + 1)

  const rows = useMemo(() => {
    const out: { key: string; name: string; email: string; role: string; state: "active" | "inactive" | "invited"; isOwner: boolean; inviteId?: string }[] = []
    if (members.state === "ready") {
      for (const m of members.data) {
        out.push({
          key: m.id,
          name: m.name || m.email.split("@")[0],
          email: m.email,
          role: m.roles.map((r) => ROLE_LABELS[r] || r).join(", ") || "No role",
          state: m.is_active ? "active" : "inactive",
          isOwner: !!m.is_owner || m.roles.includes("owner"),
        })
      }
    }
    for (const inv of invites) {
      out.push({
        key: `inv-${inv.id}`,
        name: inv.email.split("@")[0],
        email: inv.email,
        role: inv.roles.map((r) => ROLE_LABELS[r] || r).join(", "),
        state: "invited",
        isOwner: false,
        inviteId: inv.id,
      })
    }
    return out
  }, [members, invites])

  const filteredRows = useMemo(() => {
    return rows.filter((r) => {
      if (roleFilter !== "all" && !r.role.toLowerCase().includes((ROLE_LABELS[roleFilter] || roleFilter).toLowerCase())) return false
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        if (!r.name.toLowerCase().includes(q) && !r.email.toLowerCase().includes(q)) return false
      }
      return true
    })
  }, [rows, roleFilter, searchQuery])

  const handleSendInvites = async () => {
    const emails = inviteEmails.split(/[,\s;]+/).map((e) => e.trim()).filter(Boolean)
    if (emails.length === 0 || !tenantId) return
    setSending(true)
    setInviteResults([])
    const results: { email: string; ok: boolean; text: string; link?: string }[] = []
    for (const email of emails) {
      try {
        const res = await adminApi.createInvite(tenantId, { email, roles: [selectedRole], send_email: true })
        results.push({
          email,
          ok: true,
          text: res.email_requested
            ? res.email_error ? `Invite created; email not sent: ${res.email_error}` : "Invite created and email requested."
            : "Invite created.",
          link: res.accept_link,
        })
      } catch (e) {
        results.push({ email, ok: false, text: adminErrorMessage(e) })
      }
    }
    setInviteResults(results)
    setSending(false)
    if (results.some((r) => r.ok)) {
      setInviteEmails("")
      reload()
    }
  }

  const handleCopyLink = (link: string) => {
    void navigator.clipboard.writeText(link)
    setCopiedLink(link)
    setTimeout(() => setCopiedLink(null), 2500)
  }

  const handleRevoke = async (inviteId: string) => {
    setRowError(null)
    try {
      await adminApi.revokeInvite(inviteId)
      reload()
    } catch (e) {
      setRowError(adminErrorMessage(e))
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-foreground">Team</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {members.state === "ready" ? `${rows.length} ${rows.length === 1 ? "member or invite" : "members and invites"}` : "Team members come from the admin service"}
          </p>
        </div>
        <Button
          onClick={() => {
            setInviteEmails("")
            setSelectedRole(grantable.includes("org_user") ? "org_user" : grantable[0] ?? "org_user")
            setInviteResults([])
            setIsInviteOpen(true)
          }}
          disabled={!canInvite}
          title={canInvite ? undefined : "Your role cannot invite members"}
          className="bg-[#EA3829] hover:bg-[#d02e20] text-white font-medium text-xs px-4 h-9 shadow-sm"
        >
          <Plus className="mr-1.5 h-4 w-4" /> Invite member
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[240px] flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search members..."
            className="pl-9 h-9 text-xs"
          />
        </div>
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className="rounded-md border border-border bg-card px-3 py-1.5 text-xs text-foreground focus:outline-none"
        >
          <option value="all">All roles</option>
          {Object.keys(ROLE_LABELS).map((r) => (
            <option key={r} value={r}>{ROLE_LABELS[r]}</option>
          ))}
        </select>
      </div>

      {rowError && <p role="alert" className="text-sm text-red-400">{rowError}</p>}

      {members.state !== "ready" ? (
        <NotConnected loadable={members} service="The admin service" onRetry={reload} />
      ) : (
        <div className="rounded-xl border border-border bg-card shadow-xs overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[650px] text-xs">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground bg-muted/20">
                  <th className="px-5 py-3 font-semibold">Member</th>
                  <th className="px-5 py-3 font-semibold">Email</th>
                  <th className="px-5 py-3 font-semibold">Role</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredRows.length === 0 && (
                  <tr><td colSpan={5} className="px-5 py-10 text-center text-muted-foreground">{rows.length === 0 ? "No team members yet." : "No members match the filters."}</td></tr>
                )}
                {filteredRows.map((r) => {
                  const initial = (r.name || r.email || "U")[0].toUpperCase()
                  const isYou = identity?.user_id && r.key === identity.user_id
                  return (
                    <tr key={r.key} className="hover:bg-muted/10 transition-colors">
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-3">
                          <div className="h-8 w-8 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center shrink-0">{initial}</div>
                          <p className="font-semibold text-foreground flex items-center gap-1.5">
                            {r.name}
                            {isYou && <span className="text-[10px] text-muted-foreground font-normal">(You)</span>}
                          </p>
                        </div>
                      </td>
                      <td className="px-5 py-3.5 text-muted-foreground font-mono text-[11px]">{r.email}</td>
                      <td className="px-5 py-3.5">
                        <span className="inline-flex items-center rounded-md border border-border bg-muted/40 px-2 py-0.5 text-[11px] font-semibold text-foreground">{r.role}</span>
                      </td>
                      <td className="px-5 py-3.5 text-muted-foreground">
                        {r.state === "invited" ? "Invite pending" : r.state === "active" ? "Active" : "Deactivated"}
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        {r.inviteId && canInvite && (
                          <Button size="sm" variant="ghost" onClick={() => handleRevoke(r.inviteId!)} className="h-7 px-2 text-red-400 hover:text-red-300 text-xs">
                            <Trash2 className="mr-1 h-3 w-3" /> Revoke
                          </Button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="border-t border-border px-5 py-2.5 text-[11px] text-muted-foreground">
            To change roles or deactivate a member, use Admin &gt; Team.
          </p>
        </div>
      )}

      {isInviteOpen && (
        <div className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/70 backdrop-blur-xs">
          <div className="w-full max-w-md bg-card border-l border-border h-full flex flex-col p-6 shadow-2xl overflow-y-auto animate-in slide-in-from-right duration-200">
            <div className="flex items-start justify-between gap-3 mb-2">
              <h3 className="text-lg font-bold text-foreground">Invite team member</h3>
              <button onClick={() => setIsInviteOpen(false)} className="rounded p-1 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
                <X className="h-5 w-5" />
              </button>
            </div>
            <p className="text-xs text-muted-foreground mb-6 leading-relaxed">
              Each email gets a real invitation from the admin service. An invite holds a seat until it is accepted or revoked.
            </p>

            <div className="space-y-1 mb-6">
              <label className="text-xs font-semibold text-foreground">Email</label>
              <Input
                value={inviteEmails}
                onChange={(e) => setInviteEmails(e.target.value)}
                placeholder="teammate@company.com, another@company.com"
                className="h-10 text-xs"
              />
              <p className="text-[11px] text-muted-foreground pt-0.5">One or more emails, comma-separated.</p>
            </div>

            <div className="space-y-2.5 mb-6">
              <label className="text-xs font-semibold text-foreground">Role</label>
              {grantable.map((role) => (
                <div
                  key={role}
                  onClick={() => setSelectedRole(role)}
                  className={`cursor-pointer rounded-xl border p-3.5 transition-colors ${
                    selectedRole === role ? "border-primary bg-primary/5 ring-1 ring-primary/30" : "border-border bg-card hover:bg-accent/40"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Users className="h-4 w-4 text-primary shrink-0" />
                      <span className="text-xs font-bold text-foreground">{ROLE_LABELS[role] || role}</span>
                    </div>
                    {selectedRole === role && <Check className="h-3.5 w-3.5 text-primary" />}
                  </div>
                </div>
              ))}
            </div>

            {inviteResults.length > 0 && (
              <div className="mb-6 rounded-xl border border-border bg-accent/20 p-4 space-y-3">
                {inviteResults.map((r) => (
                  <div key={r.email} className="space-y-1.5">
                    <p className={`text-xs font-semibold ${r.ok ? "text-foreground" : "text-red-400"}`}>{r.email}</p>
                    <p role={r.ok ? "status" : "alert"} className={`text-[11px] ${r.ok ? "text-muted-foreground" : "text-red-400"}`}>{r.text}</p>
                    {r.link && (
                      <div className="flex items-center gap-2">
                        <Input readOnly value={r.link} className="h-8 text-xs font-mono select-all bg-card" />
                        <Button size="sm" onClick={() => handleCopyLink(r.link!)} className="h-8 text-xs bg-primary text-primary-foreground shrink-0">
                          {copiedLink === r.link ? "Copied!" : <><Copy className="mr-1 h-3 w-3" /> Copy</>}
                        </Button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="mt-auto pt-6 border-t border-border">
              <Button
                onClick={handleSendInvites}
                disabled={sending || !inviteEmails.trim() || !selectedRole}
                className="w-full bg-[#EA3829] hover:bg-[#d02e20] text-white font-medium text-xs h-10 shadow-sm"
              >
                <Mail className="mr-2 h-4 w-4" />
                {sending ? "Sending…" : "Send invitation"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/** Admin-service failure (thrown AdminApiError / network error) -> honest Loadable state. */
function adminFailureToLoadable(err: unknown): Loadable<never> {
  const status = err instanceof AdminApiError ? err.status : null
  if (status === null && !(err instanceof AdminApiError)) {
    // timeout / network failure
    return { state: "unreachable", status: null }
  }
  if (status === 502 || status === 503 || status === 504) return { state: "unreachable", status }
  if (status === 401 || status === 403) return { state: "denied", status: status as number }
  return { state: "error", status, message: adminErrorMessage(err) }
}
