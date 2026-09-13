"use client"

import { useEffect, useMemo, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/ui/page-header"
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
  Upload, Sparkles,
} from "lucide-react"
import {
  listCampaigns, createCampaign, listSocialAccounts, listSocialPosts, listInboxMessages,
  getInboxUnreadCount, listWhatsAppContacts, listWhatsAppBroadcasts,
  listAdCampaigns, listCommentAutomations,
  createSocialPost, publishSocialPost, crossPost, deleteSocialPost, createWhatsAppBroadcast,
  sendWhatsAppBroadcast, createCommentAutomation, replyToInboxMessage,
  archiveInboxMessage, markInboxRead, createAdCampaign, updateAdCampaign,
  listTraditionalCampaigns, type TraditionalCampaign,
  listConnectors, connectSocialAccount, type MarketingConnector,
  getAccountsHealth, type AccountHealth,
  getSocialUsage, createScopedKey, offboardProfile,
  listQueues, createQueue, updateQueue, deleteQueue, enqueuePost, type MarketingQueue,
  listEmailTemplates, createEmailTemplate, sendEmailBatch, type EmailTemplate,
  getAnalyticsOverview, getAnalyticsDaily, getAnalyticsPosts,
  type AnalyticsOverview, type DailyMetricPoint, type AnalyticsPostRow,
  listWhatsAppSenders, connectWhatsAppNumber, listWhatsAppTemplates, createWhatsAppTemplate,
  listWhatsAppFlows, createWhatsAppFlow, listWhatsAppGroups, createWhatsAppGroup, listWhatsAppConversions,
  type WhatsAppSender, type WhatsAppTemplate, type WhatsAppFlow, type WhatsAppGroup, type WhatsAppConversion,
} from "@/lib/marketing-api"
import { salesApi } from "@/lib/sales-api"

const channelColors = ["#4ade80", "#60a5fa", "#f59e0b", "#a78bfa", "#f472b6"]

// ═══════════════════════════════════════════════════════════════════════════════
// ICON MAPS
// ═══════════════════════════════════════════════════════════════════════════════

const platformIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  twitter: Twitter, instagram: Instagram, facebook: Facebook, linkedin: Linkedin,
  tiktok: Video, whatsapp: MessageCircle,
  youtube: Youtube, pinterest: Image, threads: AtSign, bluesky: Globe, telegram: Send,
  snapchat: Image, googlebusiness: Globe, other: Globe,
}

const platformColors: Record<string, string> = {
  twitter: "#1DA1F2", instagram: "#E4405F", facebook: "#1877F2",
  linkedin: "#0A66C2", tiktok: "#000000", whatsapp: "#25D366",
  youtube: "#FF0000", pinterest: "#BD081C", threads: "#000000",
  bluesky: "#0085FF", telegram: "#0088CC", snapchat: "#FFFC00",
  googlebusiness: "#4285F4",
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
  | "campaigns" | "social-composer" | "social-scheduled" | "social-queues"
  | "inbox-messages" | "inbox-comments" | "inbox-reviews" | "inbox-contacts"
  | "analytics"
  | "whatsapp-overview" | "whatsapp-templates" | "whatsapp-flows" | "whatsapp-groups" | "whatsapp-conversions" | "whatsapp-broadcasts" | "whatsapp-contacts"
  | "email-templates" | "email-compose"
  | "ads" | "automations" | "traditional"
  | "platform-usage" | "platform-keys" | "platform-offboard"

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
    id: "social", label: "Social", icon: Share2, children: [
      { key: "social-composer", label: "Composer", icon: Send },
      { key: "social-scheduled", label: "Scheduled", icon: Calendar },
      { key: "social-queues", label: "Queues", icon: Clock },
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
      { key: "email-templates", label: "Templates", icon: FileText },
      { key: "email-compose", label: "Compose", icon: Send },
    ],
  },
  { key: "automations", label: "Automations", icon: Zap },
  {
    id: "platform", label: "Platform", icon: Settings, children: [
      { key: "platform-usage", label: "Usage & Cost", icon: DollarSign },
      { key: "platform-keys", label: "API Keys", icon: Hash },
      { key: "platform-offboard", label: "Offboarding", icon: Trash2 },
    ],
  },
]

export function MarketingModule() {
  const [activeTab, setActiveTab] = useState<MarketingTab>("campaigns")
  // Track which nav groups are open; auto-open the group holding the active tab.
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {}
    for (const entry of MARKETING_NAV) {
      if (isGroup(entry)) init[entry.id] = entry.children.some((c) => c.key === "campaigns")
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
        actions={
          <Button variant="cta" size="sm"><Plus className="h-3.5 w-3.5" />New Campaign</Button>
        }
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
          {activeTab === "connections" && <ConnectionsTab />}
          {activeTab === "campaigns" && <CampaignsTab />}
          {activeTab === "social-composer" && <SocialComposerTab />}
          {activeTab === "social-scheduled" && <ScheduledPostsTab />}
          {activeTab === "social-queues" && <QueuesTab />}
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
          {activeTab === "whatsapp-contacts" && <WhatsAppTab view="contacts" />}
          {activeTab === "email-templates" && <EmailTemplatesTab />}
          {activeTab === "email-compose" && <EmailComposeTab />}
          {activeTab === "ads" && <AdsTab />}
          {activeTab === "automations" && <AutomationsTab />}
          {activeTab === "platform-usage" && <UsageTab />}
          {activeTab === "platform-keys" && <ApiKeysTab />}
          {activeTab === "platform-offboard" && <OffboardTab />}
          {activeTab === "traditional" && <TraditionalTab />}
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

function ConnectionsTab() {
  const [data, setData] = useState<{ connectable: boolean; configured: boolean; profile_ready: boolean; connectors: MarketingConnector[] } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [connectingId, setConnectingId] = useState<string | null>(null)
  const [health, setHealth] = useState<AccountHealth | null>(null)
  const [checkingHealth, setCheckingHealth] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await listConnectors()
      setData(res)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load connectors")
    } finally {
      setLoading(false)
    }
  }

  const checkHealth = async () => {
    setCheckingHealth(true)
    try {
      setHealth(await getAccountsHealth())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Health check failed")
    } finally {
      setCheckingHealth(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleConnect = async (id: string) => {
    setConnectingId(id)
    setError(null)
    try {
      const res = await connectSocialAccount(id)
      if (res?.auth_url) {
        window.open(res.auth_url, "_blank", "noopener,noreferrer")
      } else {
        setError("Zernio returned no connect URL for this platform.")
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start connection")
    } finally {
      setConnectingId(null)
    }
  }

  const connectors = data?.connectors ?? []
  const connectedCount = connectors.filter((c) => c.connected).length
  const categories = ["Social", "Messaging", "Commerce"]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-foreground">Connections</h3>
          <p className="text-sm text-muted-foreground">
            {loading ? "Loading…" : `${connectedCount} connected · ${connectors.length} platforms available via Zernio`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={checkHealth} disabled={checkingHealth}>
            <Radio className={`mr-2 h-4 w-4 ${checkingHealth ? "animate-spin" : ""}`} /> Check health
          </Button>
          <Button size="sm" variant="ghost" onClick={load} disabled={loading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </div>
      </div>

      {health && (
        <div className={`rounded-lg border p-3 ${health.summary.needsReconnect > 0 ? "border-amber-500/30 bg-amber-500/5" : "border-emerald-500/30 bg-emerald-500/5"}`}>
          {health.summary.needsReconnect > 0 ? (
            <div className="space-y-2">
              <p className="flex items-center gap-2 text-sm font-medium text-amber-500">
                <AlertTriangle className="h-4 w-4" /> {health.summary.needsReconnect} account(s) need reconnection
              </p>
              {health.accounts.filter((a) => a.needsReconnect).map((a) => (
                <div key={a.accountId} className="flex items-center justify-between gap-2 text-sm">
                  <span className="flex items-center gap-2 text-foreground">
                    <BrandChip id={a.platform} size={24} />
                    {a.username || a.platform}
                    <span className="text-xs text-muted-foreground">{(a.issues || []).join(", ")}</span>
                  </span>
                  <Button size="sm" variant="outline" className="shrink-0" onClick={() => handleConnect(a.platform)}>
                    <RefreshCw className="mr-1 h-3.5 w-3.5" /> Reconnect
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <p className="flex items-center gap-2 text-sm text-emerald-500">
              <CheckCircle className="h-4 w-4" /> All {health.summary.total} account(s) healthy
            </p>
          )}
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {data && !data.connectable && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
          <div className="text-sm text-amber-500">
            <p className="font-medium">Connecting is disabled</p>
            <p className="text-amber-500/80">
              {!data.configured
                ? "Set ZERNIO_API_KEY to enable Zernio connectors."
                : "Set ZERNIO_PROFILE_ID so new accounts attach to your Zernio profile."}
              {" "}You can still browse the catalogue below.
            </p>
          </div>
        </div>
      )}

      {categories.map((cat) => {
        const items = connectors.filter((c) => c.category === cat)
        if (items.length === 0) return null
        return (
          <div key={cat} className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{cat}</p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((c) => (
                <Card key={c.id} className="border-border bg-card">
                  <CardContent className="flex items-center gap-3 p-4">
                    <BrandChip id={c.id} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium leading-tight text-foreground">{c.label}</p>
                      {c.connected ? (
                        <p className="truncate text-xs text-emerald-500">
                          {c.accounts[0]?.name || c.accounts[0]?.username || "Connected"}
                        </p>
                      ) : (
                        <p className="text-xs text-muted-foreground">Not connected</p>
                      )}
                    </div>
                    {c.coming_soon ? (
                      <Badge variant="outline" className="shrink-0 border-amber-500/40 text-amber-500">Soon</Badge>
                    ) : c.connected ? (
                      <Badge variant="outline" className="shrink-0 border-emerald-500/40 text-emerald-500">
                        <CheckCircle className="mr-1 h-3 w-3" /> Connected
                      </Badge>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        className="shrink-0"
                        disabled={!data?.connectable || connectingId === c.id}
                        onClick={() => handleConnect(c.id)}
                      >
                        {connectingId === c.id ? (
                          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <><Link2 className="mr-1 h-3.5 w-3.5" /> Connect</>
                        )}
                      </Button>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// EMAIL TABS (templates + compose/send over the marketing email backend)
// ═══════════════════════════════════════════════════════════════════════════════

function EmailTemplatesTab() {
  const [templates, setTemplates] = useState<EmailTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState({ name: "", subject: "", body_html: "", category: "" })

  const load = async () => {
    setLoading(true)
    try {
      setTemplates((await listEmailTemplates()) || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load templates")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    if (!draft.name || !draft.subject) return
    setError(null)
    try {
      await createEmailTemplate(draft)
      setShowCreate(false)
      setDraft({ name: "", subject: "", body_html: "", category: "" })
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create template")
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{templates.length} email templates</p>
        <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
          <Plus className="mr-2 h-4 w-4" /> New Template
        </Button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3">
          <AlertTriangle className="h-4 w-4 shrink-0 text-red-400" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {showCreate && (
        <Card className="border-border bg-card">
          <CardHeader><CardTitle className="text-sm">Create Email Template</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Input placeholder="Template name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            <Input placeholder="Subject line" value={draft.subject} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} />
            <Input placeholder="Category (optional)" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })} />
            <Textarea placeholder="HTML body…" value={draft.body_html} onChange={(e) => setDraft({ ...draft, body_html: e.target.value })} rows={6} className="resize-none font-mono text-xs" />
            <div className="flex gap-2">
              <Button size="sm" onClick={handleCreate}>Save Template</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="py-12 text-center text-muted-foreground">Loading…</div>
      ) : templates.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground">No email templates yet</div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {templates.map((t) => (
            <Card key={t.id} className="border-border bg-card">
              <CardContent className="p-4">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <p className="truncate font-medium text-foreground">{t.name}</p>
                  {t.category && <Badge variant="outline" className="border-border text-muted-foreground">{t.category}</Badge>}
                </div>
                <p className="truncate text-sm text-muted-foreground">{t.subject}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function EmailComposeTab() {
  const [campaigns, setCampaigns] = useState<any[]>([])
  const [templates, setTemplates] = useState<EmailTemplate[]>([])
  const [campaignId, setCampaignId] = useState("")
  const [subject, setSubject] = useState("")
  const [bodyHtml, setBodyHtml] = useState("")
  const [recipientsRaw, setRecipientsRaw] = useState("")
  const [fromName, setFromName] = useState("")
  const [fromEmail, setFromEmail] = useState("")
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listCampaigns().then((c) => setCampaigns((c || []).filter((x: any) => (x.channel || "").toLowerCase() === "email" || true))).catch(() => {})
    listEmailTemplates().then((t) => setTemplates(t || [])).catch(() => {})
  }, [])

  const recipients = useMemo(
    () => recipientsRaw.split(/[\s,;]+/).map((r) => r.trim()).filter((r) => r.includes("@")),
    [recipientsRaw],
  )

  const applyTemplate = (id: string) => {
    const t = templates.find((x) => x.id === id)
    if (t) { setSubject(t.subject); setBodyHtml(t.body_html) }
  }

  const handleSend = async () => {
    if (!campaignId || !subject || recipients.length === 0) return
    setSending(true)
    setResult(null)
    setError(null)
    try {
      const res = await sendEmailBatch({
        campaign_id: campaignId,
        subject,
        body_html: bodyHtml,
        recipients,
        from_name: fromName || undefined,
        from_email: fromEmail || undefined,
      })
      setResult(`Queued ${res?.sent ?? recipients.length} email(s).`)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to queue email")
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h3 className="text-base font-semibold text-foreground">Compose Email</h3>
        <p className="text-sm text-muted-foreground">Send a batch to a recipient list, tied to a campaign for tracking.</p>
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-border bg-card/40 p-3">
        <Bell className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <p className="text-xs text-muted-foreground">
          Sends are queued and tracked (delivered / opened / clicked via the email webhook). Actual delivery
          requires an email provider worker to be wired to the queue.
        </p>
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

      <div className="space-y-3">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-foreground">Campaign</label>
          <select value={campaignId} onChange={(e) => setCampaignId(e.target.value)} className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
            <option value="">Select a campaign…</option>
            {campaigns.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>

        {templates.length > 0 && (
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Start from template (optional)</label>
            <select onChange={(e) => applyTemplate(e.target.value)} className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
              <option value="">None</option>
              {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
        )}

        <Input placeholder="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
        <div className="grid grid-cols-2 gap-3">
          <Input placeholder="From name (optional)" value={fromName} onChange={(e) => setFromName(e.target.value)} />
          <Input placeholder="From email (optional)" value={fromEmail} onChange={(e) => setFromEmail(e.target.value)} />
        </div>
        <Textarea placeholder="HTML body…" value={bodyHtml} onChange={(e) => setBodyHtml(e.target.value)} rows={6} className="resize-none font-mono text-xs" />
        <div>
          <label className="mb-1.5 block text-sm font-medium text-foreground">Recipients</label>
          <Textarea placeholder="Comma, space or newline separated email addresses" value={recipientsRaw} onChange={(e) => setRecipientsRaw(e.target.value)} rows={3} className="resize-none" />
          <p className="mt-1 text-xs text-muted-foreground">{recipients.length} valid recipient(s)</p>
        </div>
        <Button onClick={handleSend} disabled={sending || !campaignId || !subject || recipients.length === 0}>
          {sending ? <><RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Queuing…</> : <><Send className="mr-2 h-4 w-4" /> Send Email</>}
        </Button>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// PLATFORM TABS — usage/cost, scoped API keys, offboarding
// ═══════════════════════════════════════════════════════════════════════════════

const RESOURCE_GROUPS = [
  "publishing", "engagement", "messages", "contacts", "analytics",
  "ads", "telephony", "accounts", "billing", "webhooks",
]

function UsageTab() {
  const [data, setData] = useState<{ profile_id: string | null; usage: Record<string, unknown> | null; restricted: boolean } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    ;(async () => {
      try { setData(await getSocialUsage()) }
      catch (e) { setError(e instanceof Error ? e.message : "Failed to load usage") }
      finally { setLoading(false) }
    })()
  }, [])

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h3 className="text-base font-semibold text-foreground">Usage &amp; Cost</h3>
        <p className="text-sm text-muted-foreground">This customer&apos;s share of your Zernio bill for the current cycle, by profile.</p>
      </div>
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3">
          <AlertTriangle className="h-4 w-4 shrink-0 text-red-400" /><p className="text-sm text-red-400">{error}</p>
        </div>
      )}
      {loading ? (
        <div className="py-12 text-center text-muted-foreground">Loading…</div>
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
    try {
      const res = await createScopedKey({
        name,
        permission: readOnly ? "read" : undefined,
        disabled_resource_groups: disabled.length ? disabled : undefined,
        expires_in: expiresIn ? Number(expiresIn) : undefined,
      })
      setCreated(res as Record<string, any>)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create key")
    } finally {
      setCreating(false)
    }
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
    try {
      const res = await offboardProfile()
      setResult(res?.status === "offboarded"
        ? `Offboarded — disconnected ${res.disconnected_accounts ?? 0} account(s) and deleted the profile.`
        : "Nothing to offboard.")
      setAck(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Offboarding failed")
    } finally {
      setRunning(false)
    }
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

function CampaignsTab() {
  const [campaigns, setCampaigns] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [channel, setChannel] = useState<string>("all")
  const [showCreate, setShowCreate] = useState(false)
  const [newCampaign, setNewCampaign] = useState({ name: "", channel: "email", budget_zar: "", start_date: "", end_date: "" })

  useEffect(() => {
    loadCampaigns()
  }, [channel])

  const loadCampaigns = async () => {
    setLoading(true)
    try {
      const data = await listCampaigns(channel !== "all" ? { channel } : undefined)
      setCampaigns(data || [])
    } catch (e) {
      console.error("Failed to load campaigns:", e)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!newCampaign.name) return
    try {
      await createCampaign({
        ...newCampaign,
        budget_zar: newCampaign.budget_zar ? Number(newCampaign.budget_zar) : undefined,
      })
      await loadCampaigns()
      setShowCreate(false)
      setNewCampaign({ name: "", channel: "email", budget_zar: "", start_date: "", end_date: "" })
    } catch (e) {
      console.error("Failed to create campaign:", e)
    }
  }

  const activeCount = campaigns.filter((c: any) => c.status === "active").length
  const totalSent = campaigns.reduce((sum: number, c: any) => sum + (c.total_sent || 0), 0)
  const totalConversions = campaigns.reduce((sum: number, c: any) => sum + (c.total_conversions || 0), 0)
  const avgROI = campaigns.length > 0 ? (campaigns.reduce((sum: number, c: any) => sum + (c.total_conversions > 0 ? c.total_conversions / Math.max(c.total_sent, 1) * 100 : 0), 0) / campaigns.length).toFixed(1) : "0"

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
                <p className="text-2xl font-semibold text-foreground">{activeCount}</p>
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
                <p className="text-2xl font-semibold text-foreground">{totalSent.toLocaleString()}</p>
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
                <p className="text-2xl font-semibold text-foreground">{totalConversions.toLocaleString()}</p>
              </div>
              <div className="rounded-lg bg-purple-500/10 p-2"><UserCheck className="h-5 w-5 text-purple-500" /></div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border bg-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Avg ROI</p>
                <p className="text-2xl font-semibold text-foreground">{avgROI}%</p>
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
        <Card className="border-border bg-card">
          <CardHeader><CardTitle className="text-sm">Create Campaign</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Input placeholder="Campaign name" value={newCampaign.name} onChange={(e) => setNewCampaign({ ...newCampaign, name: e.target.value })} />
            <div className="grid gap-3 sm:grid-cols-2">
              <select value={newCampaign.channel} onChange={(e) => setNewCampaign({ ...newCampaign, channel: e.target.value })} className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
                <option value="email">Email</option><option value="social">Social</option>
                <option value="search">Search</option><option value="display">Display</option>
                <option value="sms">SMS</option>
              </select>
              <Input placeholder="Budget (ZAR)" value={newCampaign.budget_zar} onChange={(e) => setNewCampaign({ ...newCampaign, budget_zar: e.target.value })} />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={handleCreate}>Create</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Campaign Table */}
      <Card className="border-border bg-card">
        <CardHeader><CardTitle>Campaigns</CardTitle></CardHeader>
        <CardContent>
          {loading ? (
            <div className="py-12 text-center text-muted-foreground">Loading campaigns...</div>
          ) : campaigns.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">No campaigns found. Create your first campaign.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[800px]">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Name</th>
                    <th className="py-2 pr-4 font-medium">Channel</th>
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
                      <td className="py-3 pr-4"><Badge variant="outline" className={statusColor[c.status] || "border-muted text-muted-foreground"}>{c.status}</Badge></td>
                      <td className="py-3 pr-4 text-muted-foreground">R {(c.budget_zar || 0).toLocaleString()}</td>
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
          <CardContent><div className="h-64"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={channelDistribution} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>{channelDistribution.map((e, i) => <Cell key={i} fill={channelColors[i % channelColors.length]} />)}</Pie><Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} /></PieChart></ResponsiveContainer></div></CardContent>
        </Card>
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Budget by Campaign</CardTitle></CardHeader>
          <CardContent><div className="h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={campaignBudgets}><CartesianGrid strokeDasharray="3 3" stroke="#404040" /><XAxis dataKey="campaign" tick={{ fill: "#737373", fontSize: 10 }} /><YAxis tick={{ fill: "#737373", fontSize: 12 }} /><Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} /><Bar dataKey="budget" fill="#4ade80" name="Budget (R)" /></BarChart></ResponsiveContainer></div></CardContent>
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
  const [queues, setQueues] = useState<MarketingQueue[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [tz, setTz] = useState(() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone } catch { return "UTC" } })
  const [days, setDays] = useState<number[]>([])
  const [time, setTime] = useState("09:00")
  const [slots, setSlots] = useState<{ day: number; time: string }[]>([])
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    try { setQueues((await listQueues())?.queues ?? []) }
    catch (e) { setError(e instanceof Error ? e.message : "Failed to load queues") }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

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
    try {
      await createQueue({ name, description: description || undefined, timezone: tz, slots })
      setShowCreate(false); resetForm(); load()
    } catch (e) { setError(e instanceof Error ? e.message : "Failed to create queue") }
    finally { setSaving(false) }
  }

  const toggleStatus = async (q: MarketingQueue) => {
    await updateQueue(q.id, { status: q.status === "active" ? "paused" : "active" }).catch(() => {})
    load()
  }
  const remove = async (id: string) => { await deleteQueue(id).catch(() => {}); load() }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-foreground">Queues</h3>
          <p className="text-sm text-muted-foreground">Recurring posting schedules — posts drop into the next open slot.</p>
        </div>
        <Button size="sm" onClick={() => setShowCreate((v) => !v)}><Plus className="mr-2 h-4 w-4" /> New queue</Button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3">
          <AlertTriangle className="h-4 w-4 shrink-0 text-red-400" /><p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {showCreate && (
        <Card className="border-border bg-card">
          <CardHeader><CardTitle className="text-sm">Create queue</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Input placeholder="Queue name (e.g. Morning Posts)" value={name} onChange={(e) => setName(e.target.value)} />
            <Input placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Timezone</label>
              <Input value={tz} onChange={(e) => setTz(e.target.value)} className="w-full sm:w-72" />
            </div>
            <div className="rounded-lg border border-border p-3">
              <p className="mb-2 text-sm font-medium text-foreground">Add slots</p>
              <div className="mb-2 flex flex-wrap gap-1.5">
                {WEEKDAYS.map((w, d) => (
                  <button key={w} onClick={() => toggleDay(d)}
                    className={`rounded-lg border px-3 py-1 text-xs transition-colors ${days.includes(d) ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:text-foreground"}`}>
                    {w}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} className="w-32" />
                <Button size="sm" variant="outline" onClick={addSlots} disabled={days.length === 0}>Add slots</Button>
              </div>
              {slots.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {slots.map((s, i) => (
                    <span key={i} className="inline-flex items-center gap-1 rounded-full border border-border bg-background/40 px-2 py-0.5 text-xs text-foreground">
                      {WEEKDAYS[s.day]} {s.time}
                      <button onClick={() => removeSlot(i)} className="text-muted-foreground hover:text-red-400"><X className="h-3 w-3" /></button>
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={save} disabled={saving || !name || slots.length === 0}>
                {saving ? <><RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Creating…</> : "Create queue"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => { setShowCreate(false); resetForm() }}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="py-12 text-center text-muted-foreground">Loading…</div>
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

function ScheduledPostsTab() {
  const [posts, setPosts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [cancelling, setCancelling] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await listSocialPosts({ status: "scheduled" }).catch(() => [])
      const list = (data || []).slice().sort(
        (a: any, b: any) => new Date(a.scheduled_for || 0).getTime() - new Date(b.scheduled_for || 0).getTime(),
      )
      setPosts(list)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const cancel = async (id: string) => {
    setCancelling(id)
    try { await deleteSocialPost(id); await load() }
    catch (e) { console.error(e) }
    finally { setCancelling(null) }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-foreground">Scheduled posts</h3>
          <p className="text-sm text-muted-foreground">{loading ? "Loading…" : `${posts.length} upcoming`}</p>
        </div>
        <Button size="sm" variant="ghost" onClick={load} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      {loading ? (
        <div className="py-12 text-center text-muted-foreground">Loading…</div>
      ) : posts.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-card/40 p-10 text-center">
          <Calendar className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <p className="font-medium text-foreground">Nothing scheduled</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            In the <span className="text-foreground">Composer</span>, pick &ldquo;Schedule for later&rdquo; and choose a date/time — queued posts appear here.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {posts.map((post: any) => (
            <Card key={post.id} className="border-border bg-card">
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="mb-1.5 flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="border-cyan-500/40 text-cyan-400">
                        <Clock className="mr-1 h-3 w-3" />
                        {post.scheduled_for ? new Date(post.scheduled_for).toLocaleString() : "—"}
                      </Badge>
                      {(post.platforms || []).map((p: string) => (
                        <span key={p} className="rounded-full border px-2 py-0.5 text-xs" style={{ borderColor: (platformColors[p] || "#666") + "40", color: platformColors[p] || "#999" }}>{p}</span>
                      ))}
                    </div>
                    <p className="line-clamp-2 text-sm text-foreground">{post.content}</p>
                  </div>
                  <Button
                    size="sm" variant="ghost"
                    className="shrink-0 text-red-400 hover:text-red-300"
                    disabled={cancelling === post.id}
                    onClick={() => cancel(post.id)}
                  >
                    {cancelling === post.id ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <><Trash2 className="mr-1 h-3.5 w-3.5" /> Cancel</>}
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

function SocialComposerTab() {
  const [accounts, setAccounts] = useState<any[]>([])
  const [posts, setPosts] = useState<any[]>([])
  const [content, setContent] = useState("")
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([])
  // Default the picker to ~1 hour ahead, formatted for <input type="datetime-local">.
  const defaultScheduleAt = () => {
    const d = new Date(Date.now() + 60 * 60000 - new Date().getTimezoneOffset() * 60000)
    return d.toISOString().slice(0, 16)
  }
  const [scheduleAt, setScheduleAt] = useState(defaultScheduleAt)
  const [mode, setMode] = useState<"now" | "schedule" | "queue" | "draft">("schedule")
  const [queues, setQueues] = useState<MarketingQueue[]>([])
  const [queueId, setQueueId] = useState("")
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<string | null>(null)
  const [mediaDropPreview, setMediaDropPreview] = useState<string | null>(null)
  const [selectedTimezone, setSelectedTimezone] = useState("Africa/Johannesburg")
  const [profileSelect, setProfileSelect] = useState("00000000-0000-0000-0000-000000000001")
  const [showReuseModal, setShowReuseModal] = useState(false)

  const TIMEZONE_OPTIONS = [
    { value: "Africa/Johannesburg", label: "Africa/Johannesburg (GMT+2)" },
    { value: "UTC", label: "UTC (GMT+0)" },
    { value: "Europe/London", label: "Europe/London (GMT+1)" },
    { value: "Europe/Paris", label: "Europe/Paris (GMT+2)" },
    { value: "America/New_York", label: "America/New_York (EST)" },
    { value: "America/Los_Angeles", label: "America/Los_Angeles (PST)" },
    { value: "Asia/Dubai", label: "Asia/Dubai (GST+4)" },
    { value: "Asia/Singapore", label: "Asia/Singapore (SGT+8)" },
  ]

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [accData, postData, qData] = await Promise.all([
        listSocialAccounts().catch(() => []),
        listSocialPosts().catch(() => []),
        listQueues().catch(() => null),
      ])
      setAccounts(accData || [])
      setPosts(postData || [])
      setQueues(qData?.queues ?? [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const togglePlatform = (platform: string) => {
    setSelectedPlatforms((prev) =>
      prev.includes(platform) ? prev.filter((p) => p !== platform) : [...prev, platform]
    )
  }

  const scheduledFor = () => new Date(scheduleAt).toISOString()
  const scheduleInvalid = mode === "schedule" && (!scheduleAt || new Date(scheduleAt).getTime() <= Date.now())
  const queueInvalid = mode === "queue" && !queueId
  const canSubmit = content.trim() && selectedPlatforms.length > 0 && !scheduleInvalid && !queueInvalid

  const submitLabel = { now: "Publish Now", schedule: "Schedule Post", queue: "Add to Queue", draft: "Save Draft" }[mode]

  const handlePublish = async () => {
    if (!canSubmit) return
    setNotice(null)
    try {
      const base = { account_id: accounts[0]?.id, content, platforms: selectedPlatforms }
      if (mode === "now") {
        await createSocialPost({ ...base, status: "published" })
      } else if (mode === "schedule") {
        await createSocialPost({ ...base, status: "scheduled", scheduled_for: scheduledFor() })
      } else if (mode === "draft") {
        await createSocialPost({ ...base, status: "draft" })
      } else if (mode === "queue") {
        const res = await enqueuePost(queueId, { ...base, status: "scheduled" })
        if (res?.scheduled_for) setNotice(`Queued for ${new Date(res.scheduled_for).toLocaleString()}`)
      }
      setContent("")
      setSelectedPlatforms([])
      loadData()
    } catch (e) {
      console.error("Failed to publish:", e)
      setNotice(e instanceof Error ? e.message : "Failed to publish")
    }
  }

  const handleCrossPost = async () => {
    if (!content.trim() || selectedPlatforms.length === 0 || scheduleInvalid) return
    try {
      await crossPost({ content, platforms: selectedPlatforms, schedule_minutes: mode === "schedule" ? Math.max(1, Math.round((new Date(scheduleAt).getTime() - Date.now()) / 60000)) : undefined })
      setContent("")
      setSelectedPlatforms([])
      loadData()
    } catch (e) {
      console.error("Failed to cross-post:", e)
    }
  }

  const handleReusePost = (pastPostText: string) => {
    setContent(pastPostText)
    setShowReuseModal(false)
  }

  return (
    <div className="space-y-6">
      {/* Zernio Screenshot 5 Container Layout */}
      <Card className="border-border bg-background shadow-lg overflow-hidden">
        {/* Top Header matching Screenshot 5 */}
        <div className="flex items-center justify-between border-b border-border bg-card/60 px-6 py-4">
          <div>
            <h2 className="text-base font-bold text-foreground">Create Post</h2>
            <p className="text-xs text-muted-foreground">create & publish content</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              className="bg-[#6610f2] hover:bg-[#520dc2] text-white font-medium text-xs h-8 shadow-sm"
              onClick={() => setShowReuseModal(true)}
            >
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Reuse
            </Button>
          </div>
        </div>

        {/* 2-Column Body */}
        <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-border">
          {/* LEFT COLUMN: Content & Media */}
          <div className="p-6 space-y-4">
            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-2">content</label>
              <Textarea
                placeholder="what's on your mind..."
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={7}
                className="resize-none text-sm bg-card border-border focus:border-border/90"
              />
              <div className="text-right mt-1.5">
                <span className="text-xs text-muted-foreground">{content.length} chars</span>
              </div>
            </div>

            {/* Media Dropzone matching Screenshot 5 */}
            <div>
              <div
                onClick={() => setMediaDropPreview(mediaDropPreview ? null : "image_mock.png")}
                className="flex items-center justify-center rounded-xl border-2 border-dashed border-border bg-card/40 p-8 text-center hover:border-border/80 transition-colors cursor-pointer"
              >
                <div className="flex items-center gap-2 text-muted-foreground hover:text-foreground">
                  <Plus className="h-4 w-4" />
                  <span className="text-xs font-medium">{mediaDropPreview ? "1 media attached (click to remove)" : "Add media"}</span>
                </div>
              </div>
            </div>
          </div>

          {/* RIGHT COLUMN: Profiles, Platforms & Publishing */}
          <div className="p-6 space-y-5">
            {/* Profiles */}
            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-1.5">profiles</label>
              <p className="text-[11px] text-muted-foreground mb-2">Select one or more profiles to post to their connected accounts</p>
              <select
                value={profileSelect}
                onChange={(e) => setProfileSelect(e.target.value)}
                className="w-full rounded-md border border-border bg-card px-3 py-2 text-xs font-mono text-foreground focus:outline-none"
              >
                <option value="00000000-0000-0000-0000-000000000001">🟡 00000000-0000-0000-0000-000000000001 (Default)</option>
                <option value="brand-main">🟢 Brand Main OmniDome</option>
              </select>
            </div>

            {/* Platforms matching Screenshot 5 */}
            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-2">platforms (from 1 profile)</label>
              {accounts.length === 0 ? (
                <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card/40 p-8 text-center">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-card text-muted-foreground mb-2">
                    <Plus className="h-5 w-5" />
                  </div>
                  <p className="text-xs font-semibold text-foreground">no connected accounts</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">connect accounts to your selected profile first</p>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {accounts.map((acc: any) => {
                    const isSelected = selectedPlatforms.includes(acc.platform)
                    return (
                      <button
                        key={acc.id}
                        type="button"
                        onClick={() => togglePlatform(acc.platform)}
                        className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                          isSelected ? "border-primary bg-primary/10 text-primary" : "border-border bg-card text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        <div className="h-2 w-2 rounded-full" style={{ backgroundColor: platformColors[acc.platform] || "#666" }} />
                        {acc.account_name || acc.platform}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Publishing Tabs matching Screenshot 5: Schedule | Now | Queue | Draft */}
            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-2">publishing</label>
              <div className="grid grid-cols-4 rounded-lg border border-border bg-card/60 p-1 text-xs">
                {([
                  { m: "schedule", label: "Schedule" },
                  { m: "now", label: "Now" },
                  { m: "queue", label: "Queue" },
                  { m: "draft", label: "Draft" },
                ] as const).map(({ m, label }) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMode(m)}
                    className={`py-1.5 rounded-md font-medium transition-all ${
                      mode === m ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {/* Schedule Sub-form */}
              {mode === "schedule" && (
                <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground block mb-1">date & time</label>
                    <Input
                      type="datetime-local"
                      value={scheduleAt}
                      min={defaultScheduleAt()}
                      onChange={(e) => setScheduleAt(e.target.value)}
                      className="text-xs bg-card border-border"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground block mb-1">timezone</label>
                    <select
                      value={selectedTimezone}
                      onChange={(e) => setSelectedTimezone(e.target.value)}
                      className="w-full rounded-md border border-border bg-card px-2.5 py-2 text-xs text-foreground focus:outline-none"
                    >
                      {TIMEZONE_OPTIONS.map((tz) => (
                        <option key={tz.value} value={tz.value}>{tz.label}</option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {/* Queue Sub-form */}
              {mode === "queue" && (
                <div className="mt-3">
                  <label className="text-[11px] font-medium text-muted-foreground block mb-1">select queue</label>
                  {queues.length === 0 ? (
                    <p className="text-xs text-amber-500">No queues yet — create one under Queues first.</p>
                  ) : (
                    <select
                      value={queueId}
                      onChange={(e) => setQueueId(e.target.value)}
                      className="w-full rounded-md border border-border bg-card px-3 py-2 text-xs text-foreground focus:outline-none"
                    >
                      <option value="">Select a queue…</option>
                      {queues.map((q) => (
                        <option key={q.id} value={q.id}>{q.name} ({q.slots?.length || 0} recurring slots)</option>
                      ))}
                    </select>
                  )}
                </div>
              )}

              {mode === "draft" && (
                <p className="mt-2 text-xs text-muted-foreground">Post will be stored as draft and can be scheduled or modified later.</p>
              )}
              {notice && <p className="mt-2 text-xs text-emerald-500">{notice}</p>}
            </div>
          </div>
        </div>

        {/* Footer actions matching Screenshot 5 */}
        <div className="flex items-center justify-end gap-2 border-t border-border bg-card/30 px-6 py-4">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setContent("")
              setSelectedPlatforms([])
            }}
          >
            cancel
          </Button>
          <Button
            size="sm"
            disabled={!canSubmit}
            onClick={handlePublish}
            className="bg-muted-foreground text-background hover:bg-foreground hover:text-background font-medium"
          >
            {submitLabel.toLowerCase()}
          </Button>
        </div>
      </Card>

      {/* REUSE MODAL */}
      {showReuseModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="relative flex w-full max-w-lg flex-col rounded-xl border border-border bg-background shadow-2xl overflow-hidden max-h-[80vh]">
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <h3 className="text-sm font-bold text-foreground">Reuse Past Post</h3>
              <button onClick={() => setShowReuseModal(false)} className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="overflow-y-auto p-4 space-y-2">
              {posts.length === 0 ? (
                <p className="py-8 text-center text-xs text-muted-foreground">No past posts available to reuse.</p>
              ) : (
                posts.slice(0, 10).map((p) => (
                  <div
                    key={p.id}
                    onClick={() => handleReusePost(p.content)}
                    className="p-3 rounded-lg border border-border bg-card hover:border-primary/50 cursor-pointer transition-colors"
                  >
                    <p className="text-xs text-foreground line-clamp-3">{p.content}</p>
                    <p className="text-[10px] text-muted-foreground mt-1.5">{new Date(p.created_at).toLocaleDateString()} · {p.status}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Recent Posts List */}
      <Card className="border-border bg-card">
        <CardHeader><CardTitle className="text-sm">Recent Posts</CardTitle></CardHeader>
        <CardContent>
          <ScrollArea className="h-64">
            {loading ? (
              <div className="py-8 text-center text-muted-foreground text-xs">Loading...</div>
            ) : posts.length === 0 ? (
              <div className="py-8 text-center text-muted-foreground text-xs">No posts yet</div>
            ) : (
              <div className="space-y-3">
                {posts.map((post: any) => (
                  <div key={post.id} className="rounded-lg border border-border bg-background/40 p-3">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        {(post.platforms || []).map((p: string) => (
                          <span key={p} className="text-[10px] px-2 py-0.5 rounded-full border border-border" style={{ borderColor: platformColors[p] + "40", color: platformColors[p] }}>{p}</span>
                        ))}
                      </div>
                      <Badge variant="outline" className={statusColor[post.status] || "border-muted text-muted-foreground"}>{post.status}</Badge>
                    </div>
                    <p className="text-xs text-foreground line-clamp-2">{post.content}</p>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// SOCIAL INBOX TAB
// ═══════════════════════════════════════════════════════════════════════════════

function InboxContactsTab() {
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    ;(async () => {
      try {
        const msgs = await listInboxMessages().catch(() => [])
        const byKey: Record<string, any> = {}
        for (const m of msgs || []) {
          const key = (m.sender_handle || m.sender_name || "unknown") + "|" + (m.platform || "")
          if (!byKey[key]) byKey[key] = { name: m.sender_name || "Unknown", handle: m.sender_handle || "", platform: m.platform, count: 0 }
          byKey[key].count++
        }
        setRows(Object.values(byKey).sort((a: any, b: any) => b.count - a.count))
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-foreground">Contacts</h3>
        <p className="text-sm text-muted-foreground">{loading ? "Loading…" : `${rows.length} people who've messaged you`}</p>
      </div>
      {loading ? (
        <div className="py-12 text-center text-muted-foreground">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-card/40 p-10 text-center">
          <Users className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <p className="font-medium text-foreground">No contacts yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">People who DM or comment show up here once inbox messages arrive.</p>
        </div>
      ) : (
        <Card className="border-border bg-card">
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Handle</th>
                  <th className="px-4 py-2 font-medium">Platform</th>
                  <th className="px-4 py-2 font-medium">Messages</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-b border-border/60">
                    <td className="px-4 py-2.5 font-medium text-foreground">{r.name}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{r.handle ? "@" + r.handle : "—"}</td>
                    <td className="px-4 py-2.5">
                      <span className="flex items-center gap-2 text-muted-foreground">
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: platformColors[r.platform?.toLowerCase()] || "#666" }} />
                        {r.platform || "—"}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">{r.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

const INBOX_KIND_TYPE: Record<string, string> = { messages: "DM", comments: "COMMENT", reviews: "REVIEW" }

function SocialInboxTab({ kind = "messages" }: { kind?: "messages" | "comments" | "reviews" }) {
  const [messages, setMessages] = useState<any[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [filter, setFilter] = useState<string>("all")
  const [selectedMessage, setSelectedMessage] = useState<any>(null)
  const [replyText, setReplyText] = useState("")
  const [loading, setLoading] = useState(true)
  const messageType = INBOX_KIND_TYPE[kind] || "DM"

  useEffect(() => {
    loadInbox()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, kind])

  const loadInbox = async () => {
    setLoading(true)
    try {
      const [msgData, countData] = await Promise.all([
        listInboxMessages({ message_type: messageType, ...(filter !== "all" ? { status: filter } : {}) }).catch(() => []),
        getInboxUnreadCount().catch(() => ({ unread_count: 0 })),
      ])
      setMessages(msgData || [])
      setUnreadCount(countData?.unread_count || 0)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleReply = async () => {
    if (!selectedMessage || !replyText.trim()) return
    try {
      await replyToInboxMessage(selectedMessage.id, replyText)
      setReplyText("")
      setSelectedMessage(null)
      loadInbox()
    } catch (e) {
      console.error(e)
    }
  }

  const handleArchive = async (id: string) => {
    try {
      await archiveInboxMessage(id)
      loadInbox()
    } catch (e) {
      console.error(e)
    }
  }

  const handleMarkRead = async (id: string) => {
    try {
      await markInboxRead(id)
      loadInbox()
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Bell className="h-5 w-5 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            <span className="font-semibold text-foreground">{unreadCount}</span> unread messages
          </span>
        </div>
        <div className="flex items-center gap-2">
          {["all", "UNREAD", "READ", "REPLIED"].map((f) => (
            <Button key={f} size="sm" variant={filter === f ? "secondary" : "outline"} onClick={() => setFilter(f)}>
              {f === "all" ? "All" : f.charAt(0) + f.slice(1).toLowerCase()}
            </Button>
          ))}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        {/* Message List */}
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Messages</CardTitle></CardHeader>
          <CardContent>
            <ScrollArea className="h-96">
              {loading ? (
                <div className="py-8 text-center text-muted-foreground">Loading...</div>
              ) : messages.length === 0 ? (
                <div className="py-8 text-center text-muted-foreground">No messages</div>
              ) : (
                <div className="space-y-2">
                  {messages.map((msg: any) => (
                    <button
                      key={msg.id}
                      onClick={() => setSelectedMessage(msg)}
                      className={`w-full text-left rounded-lg border p-3 transition-colors ${
                        selectedMessage?.id === msg.id ? "border-cyan-500/40 bg-cyan-500/5" : "border-border bg-background/40 hover:bg-background/60"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-2 rounded-full" style={{ backgroundColor: platformColors[msg.platform] || "#666" }} />
                          <span className="text-sm font-medium text-foreground">{msg.sender_name}</span>
                          <span className="text-xs text-muted-foreground">@{msg.sender_handle}</span>
                        </div>
                        <Badge variant="outline" className={statusColor[msg.status] || "border-muted text-muted-foreground"}>{msg.status}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground line-clamp-2">{msg.content}</p>
                      <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                        <span>{msg.platform}</span>
                        <span>{msg.message_type}</span>
                        {msg.sentiment && <span className={statusColor[msg.sentiment]}>{msg.sentiment}</span>}
                        <span>{msg.created_at ? new Date(msg.created_at).toLocaleString() : ""}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Message Detail + Reply */}
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Message Detail</CardTitle></CardHeader>
          <CardContent>
            {selectedMessage ? (
              <div className="space-y-4">
                <div className="rounded-lg border border-border bg-background/40 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="h-3 w-3 rounded-full" style={{ backgroundColor: platformColors[selectedMessage.platform] || "#666" }} />
                      <span className="font-medium text-foreground">{selectedMessage.sender_name}</span>
                      <span className="text-sm text-muted-foreground">@{selectedMessage.sender_handle}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className={statusColor[selectedMessage.sentiment] || ""}>{selectedMessage.sentiment}</Badge>
                      <Badge variant="outline" className={statusColor[selectedMessage.status] || ""}>{selectedMessage.status}</Badge>
                    </div>
                  </div>
                  <p className="text-sm text-foreground whitespace-pre-wrap">{selectedMessage.content}</p>
                  <p className="text-xs text-muted-foreground mt-2">{selectedMessage.created_at ? new Date(selectedMessage.created_at).toLocaleString() : ""}</p>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => handleMarkRead(selectedMessage.id)}><CheckCircle className="mr-1 h-3 w-3" /> Mark Read</Button>
                  <Button size="sm" variant="outline" onClick={() => handleArchive(selectedMessage.id)}><Archive className="mr-1 h-3 w-3" /> Archive</Button>
                </div>
                <div>
                  <Textarea placeholder="Type your reply..." value={replyText} onChange={(e) => setReplyText(e.target.value)} rows={3} className="resize-none" />
                  <Button size="sm" className="mt-2" onClick={handleReply} disabled={!replyText.trim()}>
                    <Reply className="mr-2 h-4 w-4" /> Reply
                  </Button>
                </div>
              </div>
            ) : (
              <div className="py-12 text-center text-muted-foreground">Select a message to view</div>
            )}
          </CardContent>
        </Card>
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

function SocialAnalyticsTab() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [daily, setDaily] = useState<DailyMetricPoint[]>([])
  const [posts, setPosts] = useState<AnalyticsPostRow[]>([])
  const [attribution, setAttribution] = useState<"publish" | "received">("publish")
  const [metric, setMetric] = useState<keyof DailyMetricPoint["metrics"]>("impressions")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadDaily = async (attr: "publish" | "received") => {
    const d = await getAnalyticsDaily({ attribution: attr, days: 30 }).catch(() => null)
    setDaily(d?.dailyData ?? [])
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const [ov, pg] = await Promise.all([
          getAnalyticsOverview().catch(() => null),
          getAnalyticsPosts({ limit: 20 }).catch(() => null),
        ])
        if (cancelled) return
        setOverview(ov?.overview ?? null)
        setPosts(pg?.posts ?? [])
        await loadDaily(attribution)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load analytics")
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { loadDaily(attribution) }, [attribution])

  const chartData = useMemo(
    () => daily.map((d) => ({ date: d.date.slice(5), value: d.metrics[metric] ?? 0 })),
    [daily, metric],
  )
  const metricDef = DAILY_METRICS.find((m) => m.key === metric) ?? DAILY_METRICS[0]

  const fmt = (n?: number) => (n ?? 0).toLocaleString()
  const asOf = overview?.lastSync
    ? new Date(overview.lastSync).toLocaleString()
    : null

  const stats = [
    { label: "Posts", value: fmt(overview?.totalPosts), icon: FileText, color: "text-blue-400", bg: "bg-blue-500/10" },
    { label: "Impressions", value: fmt(overview?.impressions), icon: Eye, color: "text-purple-400", bg: "bg-purple-500/10" },
    { label: "Reach", value: fmt(overview?.reach), icon: Radio, color: "text-cyan-400", bg: "bg-cyan-500/10" },
    { label: "Likes", value: fmt(overview?.likes), icon: Heart, color: "text-pink-400", bg: "bg-pink-500/10" },
    { label: "Comments", value: fmt(overview?.comments), icon: MessageSquare, color: "text-emerald-400", bg: "bg-emerald-500/10" },
    { label: "Clicks", value: fmt(overview?.clicks), icon: MousePointerClick, color: "text-amber-400", bg: "bg-amber-500/10" },
  ]

  const isEmpty = !loading && (overview?.totalPosts ?? 0) === 0 && daily.length === 0

  return (
    <div className="space-y-6">
      {/* Freshness — dashboards read stored data; the worker keeps it fresh */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-foreground">Social Analytics</h3>
          <p className="text-sm text-muted-foreground">
            {loading ? "Loading…" : asOf ? `Data as of ${asOf}` : "No sync yet"}
            {overview?.dataStaleness?.pendingCount ? ` · ${overview.dataStaleness.pendingCount} still syncing` : ""}
          </p>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3">
          <AlertTriangle className="h-4 w-4 shrink-0 text-red-400" /><p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {isEmpty ? (
        <div className="rounded-lg border border-dashed border-border bg-card/40 p-10 text-center">
          <BarChart3 className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <p className="font-medium text-foreground">No analytics yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            The sync worker fills this from Zernio. Connect an account under <span className="text-foreground">Connections</span>,
            set your Zernio profile, and the worker pulls per-post metrics on its next pass.
          </p>
        </div>
      ) : (
        <>
          {/* Stat cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            {stats.map((s) => (
              <Card key={s.label} className="border-border bg-card">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs text-muted-foreground">{s.label}</p>
                      <p className="text-xl font-semibold text-foreground">{s.value}</p>
                    </div>
                    <div className={`rounded-lg ${s.bg} p-2`}><s.icon className={`h-4 w-4 ${s.color}`} /></div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Daily trend with attribution toggle */}
          <Card className="border-border bg-card">
            <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
              <CardTitle className="text-sm">Daily {metricDef.label}</CardTitle>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={metric}
                  onChange={(e) => setMetric(e.target.value as keyof DailyMetricPoint["metrics"])}
                  className="rounded-lg border border-border bg-card px-2 py-1 text-xs text-foreground"
                >
                  {DAILY_METRICS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
                </select>
                <div className="flex overflow-hidden rounded-lg border border-border text-xs">
                  {(["publish", "received"] as const).map((a) => (
                    <button
                      key={a}
                      onClick={() => setAttribution(a)}
                      className={`px-3 py-1 transition-colors ${attribution === a ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"}`}
                    >
                      {a === "publish" ? "By publish date" : "By day received"}
                    </button>
                  ))}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {chartData.length === 0 ? (
                <div className="py-16 text-center text-sm text-muted-foreground">No daily data in this window yet</div>
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                      <XAxis dataKey="date" tick={{ fill: "#737373", fontSize: 12 }} />
                      <YAxis tick={{ fill: "#737373", fontSize: 12 }} />
                      <Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} />
                      <Line type="monotone" dataKey="value" stroke={metricDef.color} strokeWidth={2} dot={false} name={metricDef.label} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
              <p className="mt-2 text-xs text-muted-foreground">
                {attribution === "publish"
                  ? "Each post's lifetime totals sit on its publish date."
                  : "Engagement bucketed by the day it arrived — moves in weeks you didn't post."}
              </p>
            </CardContent>
          </Card>

          {/* Recent posts */}
          <Card className="border-border bg-card">
            <CardHeader><CardTitle className="text-sm">Recent posts</CardTitle></CardHeader>
            <CardContent>
              {posts.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">No posts synced yet</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Platform</th>
                        <th className="py-2 pr-4 font-medium">Published</th>
                        <th className="py-2 pr-4 font-medium">Likes</th>
                        <th className="py-2 pr-4 font-medium">Comments</th>
                        <th className="py-2 pr-4 font-medium">Impressions</th>
                        <th className="py-2 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {posts.map((p) => (
                        <tr key={`${p.postId}-${p.platform}`} className="border-b border-border/60 text-sm">
                          <td className="py-3 pr-4 font-medium text-foreground">
                            <span className="flex items-center gap-2">
                              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: platformColors[p.platform?.toLowerCase()] || "#666" }} />
                              {p.platform}
                            </span>
                          </td>
                          <td className="py-3 pr-4 text-muted-foreground">{p.publishedAt ? new Date(p.publishedAt).toLocaleDateString() : "—"}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{fmt(p.analytics.likes)}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{fmt(p.analytics.comments)}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{fmt(p.analytics.impressions)}</td>
                          <td className="py-3">
                            {p.syncStatus === "pending" ? (
                              <span className="flex items-center gap-1 text-amber-500"><RefreshCw className="h-3 w-3 animate-spin" /> syncing</span>
                            ) : p.syncStatus === "unavailable" ? (
                              <span className="text-muted-foreground">unavailable</span>
                            ) : (
                              <span className="flex items-center gap-1 text-emerald-500"><CheckCircle className="h-3 w-3" /> synced</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
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
  // Senders / Numbers state
  const [senders, setSenders] = useState<WhatsAppSender[]>([])
  const [templates, setTemplates] = useState<WhatsAppTemplate[]>([])
  const [flows, setFlows] = useState<WhatsAppFlow[]>([])
  const [groups, setGroups] = useState<WhatsAppGroup[]>([])
  const [conversions, setConversions] = useState<WhatsAppConversion[]>([])
  const [contacts, setContacts] = useState<any[]>([])
  const [broadcasts, setBroadcasts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

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

  // Conversions simulator state
  const [showSimulateLead, setShowSimulateLead] = useState(false)
  const [simLead, setSimLead] = useState({
    customer_name: "",
    phone_number: "",
    deal_name: "",
    deal_value_zar: 15000,
    flow_or_template: "Customer Welcome & Quote",
  })
  const [isSyncingLead, setIsSyncingLead] = useState(false)

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

  useEffect(() => {
    loadAll()
  }, [])

  const loadAll = async () => {
    setLoading(true)
    try {
      const [snd, tpl, flw, grp, conv, cnt, bcast] = await Promise.all([
        listWhatsAppSenders().catch(() => []),
        listWhatsAppTemplates().catch(() => []),
        listWhatsAppFlows().catch(() => []),
        listWhatsAppGroups().catch(() => []),
        listWhatsAppConversions().catch(() => []),
        listWhatsAppContacts().catch(() => []),
        listWhatsAppBroadcasts().catch(() => []),
      ])
      setSenders(snd || [])
      setTemplates(tpl || [])
      setFlows(flw || [])
      setGroups(grp || [])
      setConversions(conv || [])
      setContacts(cnt || [])
      setBroadcasts(bcast || [])
    } finally {
      setLoading(false)
    }
  }

  const handleCreateGroup = async () => {
    if (!newGroup.name.trim()) return
    try {
      const activeSender = senders[0]
      await createWhatsAppGroup({
        name: newGroup.name.trim(),
        sender_id: activeSender?.id,
        invite_link: newGroup.invite_link || undefined,
      })
      setShowCreateGroup(false)
      setNewGroup({ name: "", invite_link: "" })
      loadAll()
    } catch (e) {
      console.error(e)
    }
  }

  const handleSimulateWhatsAppLead = async () => {
    if (!simLead.customer_name || !simLead.phone_number) return
    setIsSyncingLead(true)
    try {
      const names = simLead.customer_name.trim().split(" ")
      const firstName = names[0] || "WhatsApp"
      const lastName = names.slice(1).join(" ") || "Lead"

      // 1. Sync to Sales CRM Dome under "MARKETING" channel
      await salesApi.createLead({
        first_name: firstName,
        last_name: lastName,
        phone: simLead.phone_number,
        source: "MARKETING",
        notes: `WhatsApp Lead via ${simLead.flow_or_template}. Projected value: R ${simLead.deal_value_zar.toLocaleString("en-ZA")}`,
      })

      // 2. Add to WhatsApp conversions feed
      const newConv: WhatsAppConversion = {
        id: `conv-${Date.now()}`,
        customer_name: simLead.customer_name,
        phone_number: simLead.phone_number,
        deal_name: simLead.deal_name || "Fiber Service Inquiry",
        deal_value_zar: Number(simLead.deal_value_zar),
        event_type: "LEAD_CAPTURED",
        flow_or_template: simLead.flow_or_template,
        sales_channel: "MARKETING",
        status: "DEAL_CREATED",
        created_at: new Date().toISOString(),
      }
      setConversions((prev) => [newConv, ...prev])
      setShowSimulateLead(false)
      setSimLead({
        customer_name: "",
        phone_number: "",
        deal_name: "",
        deal_value_zar: 15000,
        flow_or_template: "Customer Welcome & Quote",
      })
    } catch (e) {
      console.error("Failed to sync lead to Sales Dome:", e)
    } finally {
      setIsSyncingLead(false)
    }
  }

  const handleConnectNumber = async () => {
    if (!connectMode) return
    setIsConnecting(true)
    try {
      await connectWhatsAppNumber({
        mode: connectMode,
        country_code: selectedCountry,
        phone_number: customPhone || undefined,
        display_name: customDisplayName || undefined,
      })
      setShowConnectModal(false)
      setConnectMode(null)
      setCustomPhone("")
      setCustomDisplayName("")
      loadAll()
    } finally {
      setIsConnecting(false)
    }
  }

  const handleCreateTemplate = async () => {
    if (!newTemplate.name || !newTemplate.body) return
    try {
      await createWhatsAppTemplate({
        ...newTemplate,
        buttons: newTemplate.buttons ? newTemplate.buttons.split(",").map((b) => b.trim()).filter(Boolean) : [],
      })
      setShowCreateTemplate(false)
      setNewTemplate({ name: "", category: "MARKETING", language: "en_US", header: "", body: "", footer: "", buttons: "" })
      loadAll()
    } catch (e) {
      console.error(e)
    }
  }

  const handleCreateFlow = async () => {
    if (!newFlow.name || !newFlow.trigger) return
    try {
      await createWhatsAppFlow({
        name: newFlow.name,
        trigger: newFlow.trigger,
        nodes: [
          { id: "node-1", type: "trigger", label: newFlow.trigger },
          { id: "node-2", type: "menu", label: newFlow.firstStep || "Present Options Menu" },
          { id: "node-3", type: "action", label: newFlow.responseStep || "Execute Automated Action" },
        ],
      })
      setShowCreateFlow(false)
      setNewFlow({ name: "", trigger: "", firstStep: "", responseStep: "" })
      loadAll()
    } catch (e) {
      console.error(e)
    }
  }

  const handleCreateBroadcast = async () => {
    if (!newBroadcast.name || !newBroadcast.content) return
    try {
      await createWhatsAppBroadcast(newBroadcast)
      setShowCreateBroadcast(false)
      setNewBroadcast({ name: "", content: "", template_name: "" })
      loadAll()
    } catch (e) {
      console.error(e)
    }
  }

  const handleSendBroadcast = async (id: string) => {
    try {
      await sendWhatsAppBroadcast(id)
      loadAll()
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="space-y-6">
      {/* 1. OVERVIEW VIEW matching Screenshot 4 */}
      {view === "overview" && (
        <div className="space-y-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-xl font-bold tracking-tight text-foreground">WhatsApp</h2>
              <p className="text-xs text-muted-foreground">{senders.length} live senders</p>
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
                              <p className="text-[11px] text-muted-foreground">Shared test sender</p>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-foreground">{s.number}</td>
                        <td className="py-3 px-4">
                          <span className="inline-flex items-center gap-1 rounded-full border border-border bg-background/50 px-2 py-0.5 text-[11px] text-muted-foreground">
                            {s.type}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-xs text-muted-foreground">{s.name_review || "—"}</td>
                        <td className="py-3 px-4 text-xs text-muted-foreground">{s.business_verification || "—"}</td>
                        <td className="py-3 px-4 text-right">
                          <Badge variant="outline" className="border-emerald-500/40 text-emerald-500 text-[10px]">
                            {s.status}
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

          {loading ? (
            <div className="py-12 text-center text-muted-foreground">Loading...</div>
          ) : broadcasts.length === 0 ? (
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
          {loading ? (
            <div className="py-12 text-center text-muted-foreground">Loading...</div>
          ) : contacts.length === 0 ? (
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
                  {groups.length} Groups Synced
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
                          <span className="text-[11px] text-emerald-500">Live Sync</span>
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
            <Button
              size="sm"
              className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold"
              onClick={() => setShowSimulateLead(true)}
            >
              <Sparkles className="mr-1.5 h-3.5 w-3.5" /> Simulate Customer Lead
            </Button>
          </div>

          {/* Notice banner highlighting feed to Sales Dome under Marketing channel */}
          <div className="flex items-center justify-between rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 text-xs">
            <div className="flex items-center gap-2">
              <Megaphone className="h-4 w-4 text-primary" />
              <span className="text-foreground">
                All WhatsApp CTA inquires and campaign leads feed directly into <strong>Sales Dome</strong> under channel <strong>"Marketing Campaigns" (MARKETING)</strong>.
              </span>
            </div>
            <Badge variant="outline" className="border-primary/40 text-primary text-[10px]">
              CRM Live Bridge
            </Badge>
          </div>

          {/* Quick Metrics */}
          <div className="grid gap-3 sm:grid-cols-4">
            <Card className="border-border bg-card">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">WhatsApp Leads</p>
                <p className="text-2xl font-bold text-foreground mt-1">{conversions.length + 34}</p>
                <span className="text-[10px] text-emerald-500 font-medium">+18% this month</span>
              </CardContent>
            </Card>
            <Card className="border-border bg-card">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">Deals Created in Sales</p>
                <p className="text-2xl font-bold text-foreground mt-1">{conversions.length + 22}</p>
                <span className="text-[10px] text-cyan-400 font-medium">Channel: MARKETING</span>
              </CardContent>
            </Card>
            <Card className="border-border bg-card">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">Attributed Pipeline</p>
                <p className="text-2xl font-bold text-foreground mt-1">
                  R {(conversions.reduce((acc, c) => acc + (c.deal_value_zar || 0), 0) + 480000).toLocaleString("en-ZA")}
                </p>
                <span className="text-[10px] text-muted-foreground">ZAR Closed & In-Flight</span>
              </CardContent>
            </Card>
            <Card className="border-border bg-card">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">Flow Conversion Rate</p>
                <p className="text-2xl font-bold text-foreground mt-1">34.8%</p>
                <span className="text-[10px] text-emerald-500 font-medium">Industry avg 14%</span>
              </CardContent>
            </Card>
          </div>

          {/* Conversions Log Table */}
          <Card className="border-border bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Attributed WhatsApp Deals</CardTitle>
              <CardDescription className="text-xs">
                Real-time deals synchronized with the Sales Pipeline board
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

          {/* Simulate WhatsApp Lead Modal */}
          {showSimulateLead && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
              <div className="relative flex w-full max-w-md flex-col rounded-xl border border-border bg-background shadow-2xl p-6 space-y-4">
                <div className="flex items-start justify-between border-b border-border pb-3">
                  <div>
                    <h3 className="text-base font-bold text-foreground">Simulate Inbound Lead</h3>
                    <p className="text-xs text-muted-foreground">
                      Creates a lead routed to Sales Dome with channel <strong>"MARKETING"</strong>
                    </p>
                  </div>
                  <button onClick={() => setShowSimulateLead(false)} className="text-muted-foreground hover:text-foreground">
                    <X className="h-5 w-5" />
                  </button>
                </div>
                <div className="space-y-3 text-xs">
                  <div>
                    <label className="font-medium text-foreground block mb-1">Customer Full Name</label>
                    <Input
                      placeholder="e.g. Kgomotso Dlamini"
                      value={simLead.customer_name}
                      onChange={(e) => setSimLead({ ...simLead, customer_name: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="font-medium text-foreground block mb-1">Phone Number</label>
                    <Input
                      placeholder="e.g. +27 82 555 1234"
                      value={simLead.phone_number}
                      onChange={(e) => setSimLead({ ...simLead, phone_number: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="font-medium text-foreground block mb-1">Inquired Package</label>
                    <Input
                      placeholder="e.g. 500Mbps MetroFibre Business"
                      value={simLead.deal_name}
                      onChange={(e) => setSimLead({ ...simLead, deal_name: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="font-medium text-foreground block mb-1">Estimated Value (ZAR)</label>
                    <Input
                      type="number"
                      value={simLead.deal_value_zar}
                      onChange={(e) => setSimLead({ ...simLead, deal_value_zar: Number(e.target.value) })}
                    />
                  </div>
                  <div>
                    <label className="font-medium text-foreground block mb-1">Triggering Flow / Template</label>
                    <select
                      value={simLead.flow_or_template}
                      onChange={(e) => setSimLead({ ...simLead, flow_or_template: e.target.value })}
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none"
                    >
                      <option value="Customer Welcome & Quote">Customer Welcome & Quote</option>
                      <option value="fiber_cart_recovery">fiber_cart_recovery</option>
                      <option value="welcome_onboarding">welcome_onboarding</option>
                      <option value="Support Triage">Support Triage</option>
                    </select>
                  </div>
                </div>
                <div className="flex justify-end gap-2 pt-2 border-t border-border">
                  <Button variant="ghost" size="sm" onClick={() => setShowSimulateLead(false)}>Cancel</Button>
                  <Button
                    size="sm"
                    disabled={!simLead.customer_name || !simLead.phone_number || isSyncingLead}
                    onClick={handleSimulateWhatsAppLead}
                  >
                    {isSyncingLead ? "Syncing to Sales…" : "Push to Sales Dome"}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* CONNECT WHATSAPP MODAL matching Screenshot 4 */}
      {showConnectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="relative flex w-full max-w-lg flex-col rounded-xl border border-border bg-background shadow-2xl overflow-hidden">
            {/* Header */}
            <div className="flex items-start justify-between border-b border-border px-6 py-4">
              <div className="flex items-center gap-2">
                <MessageCircle className="h-5 w-5 text-[#25D366]" />
                <div>
                  <h3 className="text-base font-bold text-foreground">Connect WhatsApp</h3>
                  <p className="text-xs text-muted-foreground">Choose how to set up your number</p>
                </div>
              </div>
              <button
                onClick={() => setShowConnectModal(false)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-card hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Content: 2 Cards matching Screenshot 4 */}
            <div className="p-6 space-y-4">
              {/* Option A: Get a number */}
              <div
                onClick={() => setConnectMode("get_number")}
                className={`flex items-start gap-4 rounded-xl border p-4 cursor-pointer transition-all ${
                  connectMode === "get_number"
                    ? "border-primary bg-primary/5 ring-1 ring-primary"
                    : "border-border bg-card hover:border-border/80"
                }`}
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-foreground">
                  <Plus className="h-4 w-4" />
                </div>
                <div className="space-y-1">
                  <p className="font-semibold text-sm text-foreground">Get a number</p>
                  <p className="text-xs text-muted-foreground">From $3/mo. Pick a country, we handle setup.</p>
                  {connectMode === "get_number" && (
                    <div className="pt-3 space-y-2">
                      <label className="text-[11px] font-medium text-foreground block">Select Country</label>
                      <select
                        value={selectedCountry}
                        onChange={(e) => setSelectedCountry(e.target.value)}
                        className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none"
                      >
                        <option value="+27">🇿🇦 South Africa (+27)</option>
                        <option value="+1">🇺🇸 United States (+1)</option>
                        <option value="+44">🇬🇧 United Kingdom (+44)</option>
                      </select>
                      <Input
                        placeholder="Sender display name (e.g. OmniDome Sales)"
                        value={customDisplayName}
                        onChange={(e) => setCustomDisplayName(e.target.value)}
                        className="text-xs bg-background border-border"
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* Option B: Use my own number */}
              <div
                onClick={() => setConnectMode("own_number")}
                className={`flex items-start gap-4 rounded-xl border p-4 cursor-pointer transition-all ${
                  connectMode === "own_number"
                    ? "border-primary bg-primary/5 ring-1 ring-primary"
                    : "border-border bg-card hover:border-border/80"
                }`}
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-foreground">
                  <Hash className="h-4 w-4" />
                </div>
                <div className="space-y-1">
                  <p className="font-semibold text-sm text-foreground">Use my own number</p>
                  <p className="text-xs text-muted-foreground">Bring your existing phone number. Requires verification during setup.</p>
                  {connectMode === "own_number" && (
                    <div className="pt-3 space-y-2">
                      <Input
                        placeholder="Your phone number (+27 82 123 4567)"
                        value={customPhone}
                        onChange={(e) => setCustomPhone(e.target.value)}
                        className="text-xs bg-background border-border"
                      />
                      <Input
                        placeholder="Sender display name"
                        value={customDisplayName}
                        onChange={(e) => setCustomDisplayName(e.target.value)}
                        className="text-xs bg-background border-border"
                      />
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-2 border-t border-border bg-card/30 px-6 py-4">
              <Button variant="outline" size="sm" onClick={() => setShowConnectModal(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={!connectMode || (connectMode === "own_number" && !customPhone.trim()) || isConnecting}
                onClick={handleConnectNumber}
                className="bg-[#25D366] hover:bg-[#1ebd5a] text-black font-semibold"
              >
                {isConnecting ? "Connecting…" : "Proceed Setup"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// ADS TAB (Zernio-style Ads & Boosted Posts)
// ═══════════════════════════════════════════════════════════════════════════════

function AdsTab() {
  const [activeSubTab, setActiveSubTab] = useState<"campaigns" | "audiences" | "lead-forms">("campaigns")
  const [ads, setAds] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [socialAccounts, setSocialAccounts] = useState<any[]>([])

  // Filters matching Screenshot 2: All profiles | All ads | All platforms | All accounts | All statuses | Last 30 days | Newest first
  const [filterProfile, setFilterProfile] = useState("all")
  const [filterType, setFilterType] = useState("all")
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
  const [profileName, setProfileName] = useState("Default")
  const [adName, setAdName] = useState("")
  const [selectedGoal, setSelectedGoal] = useState<"Engagement" | "Traffic" | "Awareness" | "Video Views">("Engagement")
  const [budgetAmount, setBudgetAmount] = useState("5")
  const [budgetType, setBudgetType] = useState<"daily" | "total">("daily")
  const [selectedAudience, setSelectedAudience] = useState("All audiences")
  const [createAsPaused, setCreateAsPaused] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  // Dummy audience / lead forms for secondary tabs
  const [audiences] = useState([
    { id: "aud-1", name: "Broad SA 18-45", size: "4.2M", platform: "meta", updated: "2 days ago" },
    { id: "aud-2", name: "Tech & Telecom Decision Makers", size: "180k", platform: "linkedin", updated: "1 week ago" },
    { id: "aud-3", name: "High-LTV Fiber Churn Targets", size: "45k", platform: "custom", updated: "Yesterday" },
  ])

  const [leadForms, setLeadForms] = useState([
    { id: "lf-1", name: "Home Fiber Instant Quote Form", leads: 142, completionRate: "38.4%", platform: "facebook", status: "ACTIVE" },
    { id: "lf-2", name: "Business Internet Inquiry 2026", leads: 68, completionRate: "29.1%", platform: "linkedin", status: "ACTIVE" },
  ])

  // Lead Form simulation modal
  const [showSimulateLeadForm, setShowSimulateLeadForm] = useState(false)
  const [activeFormForSim, setActiveFormForSim] = useState<any>(null)
  const [leadFormData, setLeadFormData] = useState({
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    address: "",
    notes: "Requested 100Mbps Home Fiber via Instant Lead Form",
  })
  const [isSubmittingLead, setIsSubmittingLead] = useState(false)
  const [leadSubmitSuccess, setLeadSubmitSuccess] = useState(false)

  const handleSimulateLeadSubmit = async () => {
    if (!leadFormData.firstName || !leadFormData.phone) return
    setIsSubmittingLead(true)
    try {
      await salesApi.createLead({
        first_name: leadFormData.firstName,
        last_name: leadFormData.lastName || "Lead",
        email: leadFormData.email || undefined,
        phone: leadFormData.phone,
        address: leadFormData.address || undefined,
        source: "MARKETING", // Directly routes to Sales Dome as Marketing channel
        notes: `Native Lead Form: ${activeFormForSim?.name || "Instant Quote"}. ${leadFormData.notes}`,
      })
      // Increment lead count on the form
      if (activeFormForSim) {
        setLeadForms((prev) =>
          prev.map((lf) => (lf.id === activeFormForSim.id ? { ...lf, leads: lf.leads + 1 } : lf))
        )
      }
      setLeadSubmitSuccess(true)
      setTimeout(() => {
        setLeadSubmitSuccess(false)
        setShowSimulateLeadForm(false)
        setLeadFormData({
          firstName: "",
          lastName: "",
          email: "",
          phone: "",
          address: "",
          notes: "Requested 100Mbps Home Fiber via Instant Lead Form",
        })
      }, 1400)
    } catch (e) {
      console.error("Failed to submit lead to Sales Dome:", e)
    } finally {
      setIsSubmittingLead(false)
    }
  }

  useEffect(() => {
    loadAds()
    listSocialAccounts().then((accs) => setSocialAccounts(accs || [])).catch(() => {})
  }, [])

  const loadAds = async () => {
    setLoading(true)
    try {
      const data = await listAdCampaigns().catch(() => [])
      setAds(data || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleCreateAd = async () => {
    if (!adName.trim()) return
    setSubmitting(true)
    try {
      const budgetNum = parseFloat(budgetAmount) || 0
      await createAdCampaign({
        name: adName,
        platform: "facebook",
        objective: selectedGoal.toUpperCase().replace(/\s+/g, "_"),
        budget_zar: budgetType === "total" ? budgetNum : undefined,
        daily_budget_zar: budgetType === "daily" ? budgetNum : undefined,
        status: createAsPaused ? "PAUSED" : "ACTIVE",
        creative: {
          primary_text: primaryText,
          headline: headline,
          destination_url: destinationUrl,
          media_url: mediaFile,
        },
        targeting: {
          audience: selectedAudience,
          profile: profileName,
        },
      })
      setShowCreateModal(false)
      // Reset
      setPrimaryText("")
      setHeadline("")
      setDestinationUrl("")
      setMediaFile(null)
      setAdName("")
      setBudgetAmount("5")
      setCreateAsPaused(true)
      loadAds()
    } catch (e) {
      console.error(e)
    } finally {
      setSubmitting(false)
    }
  }

  const clearFilters = () => {
    setFilterProfile("all")
    setFilterType("all")
    setFilterPlatform("all")
    setFilterAccount("all")
    setFilterStatus("all")
    setFilterDateRange("30d")
    setFilterSort("newest")
  }

  const filteredAds = ads.filter((ad: any) => {
    if (filterStatus !== "all" && ad.status?.toLowerCase() !== filterStatus.toLowerCase()) return false
    if (filterPlatform !== "all" && ad.platform?.toLowerCase() !== filterPlatform.toLowerCase()) return false
    return true
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
              <Button variant="outline" className="border-border text-foreground hover:bg-card">
                <Sparkles className="mr-1.5 h-4 w-4 text-amber-500" /> Boost Post
              </Button>
            </div>
          </div>

          {/* Zernio Filter Bar matching Screenshot 2 */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <select
              value={filterProfile}
              onChange={(e) => setFilterProfile(e.target.value)}
              className="rounded-md border border-border bg-card px-2.5 py-1.5 text-foreground hover:border-border/80 focus:outline-none"
            >
              <option value="all">All profiles</option>
              <option value="default">Default Profile</option>
            </select>

            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="rounded-md border border-border bg-card px-2.5 py-1.5 text-foreground hover:border-border/80 focus:outline-none"
            >
              <option value="all">All ads</option>
              <option value="standalone">Standalone Ads</option>
              <option value="boosted">Boosted Posts</option>
            </select>

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
          {loading ? (
            <div className="py-20 text-center text-sm text-muted-foreground">Loading ads…</div>
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
                <Button size="sm" variant="outline">
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

      {activeSubTab === "audiences" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-foreground">Target Audiences</h3>
              <p className="text-xs text-muted-foreground">Saved custom audiences and customer segments for ads</p>
            </div>
            <Button size="sm" variant="outline"><Plus className="mr-1.5 h-3.5 w-3.5" /> New Audience</Button>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            {audiences.map((aud) => (
              <Card key={aud.id} className="border-border bg-card">
                <CardContent className="p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="font-semibold text-sm text-foreground">{aud.name}</p>
                    <Badge variant="outline" className="text-[10px]">{aud.platform}</Badge>
                  </div>
                  <p className="text-2xl font-bold text-foreground">{aud.size}</p>
                  <p className="text-xs text-muted-foreground">Updated {aud.updated}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {activeSubTab === "lead-forms" && (
        <div className="space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-base font-semibold text-foreground">Instant Lead Forms</h3>
              <p className="text-xs text-muted-foreground">In-feed native forms syncing customer inquiries into OmniDome CRM</p>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold"
                onClick={() => {
                  setActiveFormForSim(leadForms[0])
                  setShowSimulateLeadForm(true)
                }}
              >
                <Sparkles className="mr-1.5 h-3.5 w-3.5" /> Simulate Lead Submission
              </Button>
              <Button size="sm" variant="outline"><Plus className="mr-1.5 h-3.5 w-3.5" /> New Lead Form</Button>
            </div>
          </div>

          {/* Banner: Automatic routing to Sales Dome under channel MARKETING */}
          <div className="flex items-center justify-between rounded-lg border border-[#e03131]/30 bg-[#e03131]/5 px-4 py-3 text-xs">
            <div className="flex items-center gap-2">
              <Megaphone className="h-4 w-4 text-[#e03131]" />
              <span className="text-foreground">
                All submitted lead forms are automatically ingested into <strong>Sales Dome</strong> under channel <strong>"Marketing Campaigns" (MARKETING)</strong> and queued for sales agent follow-up.
              </span>
            </div>
            <Badge variant="outline" className="border-[#e03131]/40 text-[#e03131] text-[10px]">
              Live CRM Ingestion
            </Badge>
          </div>

          <div className="space-y-3">
            {leadForms.map((lf) => (
              <Card key={lf.id} className="border-border bg-card">
                <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div className="space-y-1">
                    <p className="font-semibold text-sm text-foreground">{lf.name}</p>
                    <p className="text-xs text-muted-foreground">
                      Platform: <span className="capitalize text-foreground font-medium">{lf.platform}</span> · {lf.completionRate} completion
                    </p>
                    <div className="flex items-center gap-2 pt-1 text-[11px] text-muted-foreground">
                      <Badge variant="outline" className="text-[10px] border-[#e03131]/40 text-[#e03131]">
                        Feeds Sales: MARKETING
                      </Badge>
                      <span>Auto-assigns deals to Sales Agent</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 self-end sm:self-center">
                    <div className="text-right">
                      <p className="text-lg font-bold text-foreground">{lf.leads} leads</p>
                      <Badge variant="outline" className="text-[10px] border-emerald-500/40 text-emerald-500">Live</Badge>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-xs"
                      onClick={() => {
                        setActiveFormForSim(lf)
                        setShowSimulateLeadForm(true)
                      }}
                    >
                      Test Submit
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* SIMULATE LEAD SUBMISSION MODAL */}
          {showSimulateLeadForm && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
              <div className="relative flex w-full max-w-md flex-col rounded-xl border border-border bg-background shadow-2xl p-6 space-y-4">
                <div className="flex items-start justify-between border-b border-border pb-3">
                  <div>
                    <h3 className="text-base font-bold text-foreground">Simulate Lead Form Submission</h3>
                    <p className="text-xs text-muted-foreground">
                      Form: <strong>{activeFormForSim?.name}</strong> → Routes to Sales Dome as <strong>"MARKETING"</strong>
                    </p>
                  </div>
                  <button onClick={() => setShowSimulateLeadForm(false)} className="text-muted-foreground hover:text-foreground">
                    <X className="h-5 w-5" />
                  </button>
                </div>

                {leadSubmitSuccess ? (
                  <div className="py-8 text-center space-y-2">
                    <CheckCircle className="h-10 w-10 text-emerald-500 mx-auto animate-bounce" />
                    <p className="font-semibold text-sm text-foreground">Lead Created Successfully!</p>
                    <p className="text-xs text-muted-foreground">
                      Pushed into Sales Dome under channel <strong>Marketing Campaigns</strong>.
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="space-y-3 text-xs">
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="font-medium text-foreground block mb-1">First Name</label>
                          <Input
                            placeholder="John"
                            value={leadFormData.firstName}
                            onChange={(e) => setLeadFormData({ ...leadFormData, firstName: e.target.value })}
                          />
                        </div>
                        <div>
                          <label className="font-medium text-foreground block mb-1">Last Name</label>
                          <Input
                            placeholder="Smith"
                            value={leadFormData.lastName}
                            onChange={(e) => setLeadFormData({ ...leadFormData, lastName: e.target.value })}
                          />
                        </div>
                      </div>
                      <div>
                        <label className="font-medium text-foreground block mb-1">Email Address</label>
                        <Input
                          placeholder="john.smith@example.co.za"
                          value={leadFormData.email}
                          onChange={(e) => setLeadFormData({ ...leadFormData, email: e.target.value })}
                        />
                      </div>
                      <div>
                        <label className="font-medium text-foreground block mb-1">Phone Number</label>
                        <Input
                          placeholder="+27 82 123 4567"
                          value={leadFormData.phone}
                          onChange={(e) => setLeadFormData({ ...leadFormData, phone: e.target.value })}
                        />
                      </div>
                      <div>
                        <label className="font-medium text-foreground block mb-1">Installation Address</label>
                        <Input
                          placeholder="124 Kloof St, Gardens, Cape Town"
                          value={leadFormData.address}
                          onChange={(e) => setLeadFormData({ ...leadFormData, address: e.target.value })}
                        />
                      </div>
                      <div>
                        <label className="font-medium text-foreground block mb-1">Inquiry Details</label>
                        <Input
                          value={leadFormData.notes}
                          onChange={(e) => setLeadFormData({ ...leadFormData, notes: e.target.value })}
                        />
                      </div>
                    </div>
                    <div className="flex justify-end gap-2 pt-2 border-t border-border">
                      <Button variant="ghost" size="sm" onClick={() => setShowSimulateLeadForm(false)}>Cancel</Button>
                      <Button
                        size="sm"
                        disabled={!leadFormData.firstName || !leadFormData.phone || isSubmittingLead}
                        onClick={handleSimulateLeadSubmit}
                        className="bg-[#e03131] hover:bg-[#c92a2a] text-white"
                      >
                        {isSubmittingLead ? "Submitting to Sales…" : "Submit & Sync to Sales"}
                      </Button>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* CREATE AD MODAL — Faithfully matching Screenshot 3 */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="relative flex max-h-[92vh] w-full max-w-5xl flex-col rounded-xl border border-border bg-background shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-border px-6 py-4">
              <div>
                <h3 className="text-lg font-bold text-foreground">Create Ad</h3>
                <p className="text-xs text-muted-foreground">design your ad creative and configure targeting</p>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-card hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Modal Body: 2 Columns */}
            <div className="flex-1 overflow-y-auto p-6">
              <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
                {/* LEFT COLUMN: Creative & Copy */}
                <div className="space-y-5">
                  {/* Primary text */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-xs font-semibold text-foreground">primary text</label>
                    </div>
                    <Textarea
                      placeholder="Write the main text for your ad. This appears above the image."
                      value={primaryText}
                      maxLength={125}
                      onChange={(e) => setPrimaryText(e.target.value)}
                      rows={4}
                      className="resize-none text-sm bg-card border-border"
                    />
                    <div className="text-right mt-1">
                      <span className="text-[11px] text-muted-foreground">{primaryText.length}/125</span>
                    </div>
                  </div>

                  {/* Media Dropzone */}
                  <div>
                    <label className="text-xs font-semibold text-foreground mb-1.5 block">media</label>
                    <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-border bg-card/40 p-8 text-center hover:border-border/80 transition-colors cursor-pointer">
                      <Image className="h-9 w-9 text-muted-foreground/60 mb-2" />
                      <p className="text-xs font-medium text-foreground">Drop an image here or click to browse</p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">JPG or PNG, recommended 1200x628px, max 30MB</p>
                    </div>
                  </div>

                  {/* Headline */}
                  <div>
                    <label className="text-xs font-semibold text-foreground mb-1.5 block">headline</label>
                    <Input
                      placeholder="Your headline"
                      value={headline}
                      maxLength={40}
                      onChange={(e) => setHeadline(e.target.value)}
                      className="text-sm bg-card border-border"
                    />
                    <div className="text-right mt-1">
                      <span className="text-[11px] text-muted-foreground">{headline.length}/40</span>
                    </div>
                  </div>

                  {/* Destination URL */}
                  <div>
                    <label className="text-xs font-semibold text-foreground mb-1.5 block">destination URL</label>
                    <Input
                      placeholder="https://yourwebsite.com/landing-page"
                      value={destinationUrl}
                      onChange={(e) => setDestinationUrl(e.target.value)}
                      className="text-sm bg-card border-border"
                    />
                  </div>
                </div>

                {/* RIGHT COLUMN: Targeting, Budget & Profile */}
                <div className="space-y-5">
                  {/* Profile */}
                  <div>
                    <label className="text-xs font-semibold text-foreground mb-1.5 block">profile</label>
                    <div className="relative">
                      <select
                        value={profileName}
                        onChange={(e) => setProfileName(e.target.value)}
                        className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground focus:outline-none"
                      >
                        <option value="Default">🟡 Default</option>
                        <option value="Brand">🟢 Brand Main</option>
                      </select>
                    </div>
                  </div>

                  {/* Ad name */}
                  <div>
                    <label className="text-xs font-semibold text-foreground mb-1.5 block">ad name</label>
                    <Input
                      placeholder="Summer Sale Campaign"
                      value={adName}
                      onChange={(e) => setAdName(e.target.value)}
                      className="text-sm bg-card border-border"
                    />
                  </div>

                  {/* Platform & account notice / connection */}
                  <div>
                    <label className="text-xs font-semibold text-foreground mb-1 block">platform & account</label>
                    <p className="text-xs text-muted-foreground mb-2">
                      {socialAccounts.length > 0
                        ? `Connected: ${socialAccounts.map((a) => a.platform).join(", ")}`
                        : "No ads accounts connected. Connect an ads platform in Connections to create an ad."}
                    </p>
                    <Button variant="outline" size="sm" className="text-xs">
                      Go to Connections
                    </Button>
                  </div>

                  {/* Goal (4 pills matching Screenshot 3) */}
                  <div>
                    <label className="text-xs font-semibold text-foreground mb-1.5 block">goal</label>
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
                          onClick={() => setSelectedGoal(key)}
                          className={`flex items-center gap-2 rounded-md border p-2.5 text-xs font-medium transition-colors ${
                            selectedGoal === key
                              ? "border-primary bg-primary/10 text-primary"
                              : "border-border bg-card text-foreground hover:bg-card/80"
                          }`}
                        >
                          <Icon className="h-3.5 w-3.5 shrink-0" />
                          <span>{key}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Budget (Input + Per day / Total toggle) */}
                  <div>
                    <label className="text-xs font-semibold text-foreground mb-1.5 block">budget</label>
                    <div className="flex items-center gap-2">
                      <div className="relative flex-1">
                        <span className="absolute left-3 top-2.5 text-xs text-muted-foreground">$</span>
                        <Input
                          type="number"
                          value={budgetAmount}
                          onChange={(e) => setBudgetAmount(e.target.value)}
                          className="pl-6 text-sm bg-card border-border"
                        />
                      </div>
                      <div className="flex rounded-md border border-border p-0.5 text-xs">
                        <button
                          type="button"
                          onClick={() => setBudgetType("daily")}
                          className={`px-3 py-1.5 rounded transition-colors ${
                            budgetType === "daily" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"
                          }`}
                        >
                          Per day
                        </button>
                        <button
                          type="button"
                          onClick={() => setBudgetType("total")}
                          className={`px-3 py-1.5 rounded transition-colors ${
                            budgetType === "total" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"
                          }`}
                        >
                          Total
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Targeting */}
                  <div>
                    <label className="text-xs font-semibold text-foreground mb-1.5 block">targeting</label>
                    <div className="flex items-center justify-between rounded-md border border-border bg-card p-3 text-xs">
                      <span className="text-foreground">{selectedAudience}</span>
                      <button
                        type="button"
                        onClick={() => setSelectedAudience("South Africa 18-50 (Broad)")}
                        className="text-[#e03131] hover:underline font-medium flex items-center gap-1"
                      >
                        <Edit className="h-3 w-3" /> Edit audience
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between border-t border-border bg-card/30 px-6 py-4">
              <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={createAsPaused}
                  onChange={(e) => setCreateAsPaused(e.target.checked)}
                  className="rounded border-border"
                />
                <span>create as paused</span>
              </label>

              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowCreateModal(false)}
                >
                  cancel
                </Button>
                <Button
                  size="sm"
                  disabled={!adName.trim() || submitting}
                  onClick={handleCreateAd}
                  className="bg-muted-foreground text-background hover:bg-foreground hover:text-background"
                >
                  {submitting ? "creating…" : "create Ad"}
                </Button>
              </div>
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
  const [automations, setAutomations] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newAuto, setNewAuto] = useState({ name: "", account_id: "", trigger_type: "KEYWORD", trigger_keywords: "", response_template: "" })

  useEffect(() => {
    loadAutomations()
  }, [])

  const loadAutomations = async () => {
    setLoading(true)
    try {
      const data = await listCommentAutomations().catch(() => [])
      setAutomations(data || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!newAuto.name || !newAuto.response_template) return
    try {
      await createCommentAutomation({
        ...newAuto,
        trigger_keywords: newAuto.trigger_keywords.split(",").map((k) => k.trim()).filter(Boolean),
      })
      setShowCreate(false)
      setNewAuto({ name: "", account_id: "", trigger_type: "KEYWORD", trigger_keywords: "", response_template: "" })
      loadAutomations()
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{automations.length} automations</p>
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
              <Button size="sm" onClick={handleCreate}>Create</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="py-12 text-center text-muted-foreground">Loading...</div>
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
  const [campaigns, setCampaigns] = useState<TraditionalCampaign[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listTraditionalCampaigns().then((data) => {
      setCampaigns(data ?? [])
      setLoading(false)
    })
  }, [])

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

  if (loading) {
    return <div className="py-12 text-center text-sm text-muted-foreground">Loading traditional media data...</div>
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
