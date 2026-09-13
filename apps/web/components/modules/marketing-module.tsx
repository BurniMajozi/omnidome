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
  Instagram, Twitter, Facebook, Linkedin, Youtube, Video, FileText, Copy, ShoppingBag,
} from "lucide-react"
import {
  listCampaigns, createCampaign, listSocialAccounts, listSocialPosts, listInboxMessages,
  getInboxUnreadCount, listWhatsAppContacts, listWhatsAppBroadcasts,
  listAdCampaigns, listCommentAutomations,
  createSocialPost, publishSocialPost, crossPost, createWhatsAppBroadcast,
  sendWhatsAppBroadcast, createCommentAutomation, replyToInboxMessage,
  archiveInboxMessage, markInboxRead, createAdCampaign, updateAdCampaign,
  listTraditionalCampaigns, type TraditionalCampaign,
  listConnectors, connectSocialAccount, type MarketingConnector,
  getAccountsHealth, type AccountHealth,
  getSocialUsage, createScopedKey, offboardProfile,
  listEmailTemplates, createEmailTemplate, sendEmailBatch, type EmailTemplate,
  getAnalyticsOverview, getAnalyticsDaily, getAnalyticsPosts,
  type AnalyticsOverview, type DailyMetricPoint, type AnalyticsPostRow,
} from "@/lib/marketing-api"

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
  | "campaigns" | "social-composer" | "social-inbox" | "social-analytics"
  | "whatsapp-broadcasts" | "whatsapp-contacts" | "whatsapp-templates" | "whatsapp-flows" | "whatsapp-groups"
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
      { key: "social-inbox", label: "Inbox", icon: MessageSquare },
      { key: "social-analytics", label: "Analytics", icon: BarChart3 },
    ],
  },
  {
    id: "whatsapp", label: "WhatsApp", icon: MessageCircle, children: [
      { key: "whatsapp-broadcasts", label: "Broadcasts", icon: Send },
      { key: "whatsapp-contacts", label: "Contacts", icon: UserCheck },
      { key: "whatsapp-templates", label: "Templates", icon: FileText },
      { key: "whatsapp-flows", label: "Flows", icon: RefreshCw },
      { key: "whatsapp-groups", label: "Groups", icon: Users },
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
          {activeTab === "social-inbox" && <SocialInboxTab />}
          {activeTab === "social-analytics" && <SocialAnalyticsTab />}
          {activeTab === "whatsapp-broadcasts" && <WhatsAppTab view="broadcasts" />}
          {activeTab === "whatsapp-contacts" && <WhatsAppTab view="contacts" />}
          {activeTab === "whatsapp-templates" && (
            <WhatsAppComingSoon
              icon={FileText}
              title="WhatsApp Message Templates"
              description="Create and manage reusable, pre-approved WhatsApp message templates for broadcasts and automated replies. Backend support is not wired up yet."
            />
          )}
          {activeTab === "whatsapp-flows" && (
            <WhatsAppComingSoon
              icon={RefreshCw}
              title="WhatsApp Flows"
              description="Build interactive, multi-step WhatsApp conversation flows (menus, forms, guided journeys). Backend support is not wired up yet."
            />
          )}
          {activeTab === "whatsapp-groups" && (
            <WhatsAppComingSoon
              icon={Users}
              title="WhatsApp Groups"
              description="Organize contacts into targetable groups for segmented broadcasts. Backend support is not wired up yet."
            />
          )}
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

function SocialComposerTab() {
  const [accounts, setAccounts] = useState<any[]>([])
  const [posts, setPosts] = useState<any[]>([])
  const [content, setContent] = useState("")
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([])
  const [scheduleMinutes, setScheduleMinutes] = useState(60)
  const [publishNow, setPublishNow] = useState(true)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [accData, postData] = await Promise.all([
        listSocialAccounts().catch(() => []),
        listSocialPosts().catch(() => []),
      ])
      setAccounts(accData || [])
      setPosts(postData || [])
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

  const handlePublish = async () => {
    if (!content.trim() || selectedPlatforms.length === 0) return
    try {
      if (publishNow) {
        await createSocialPost({ account_id: accounts[0]?.id, content, platforms: selectedPlatforms, status: "published" })
      } else {
        await createSocialPost({ account_id: accounts[0]?.id, content, platforms: selectedPlatforms, status: "scheduled", scheduled_for: new Date(Date.now() + scheduleMinutes * 60000).toISOString() })
      }
      setContent("")
      setSelectedPlatforms([])
      loadData()
    } catch (e) {
      console.error("Failed to publish:", e)
    }
  }

  const handleCrossPost = async () => {
    if (!content.trim() || selectedPlatforms.length === 0) return
    try {
      await crossPost({ content, platforms: selectedPlatforms, schedule_minutes: publishNow ? undefined : scheduleMinutes })
      setContent("")
      setSelectedPlatforms([])
      loadData()
    } catch (e) {
      console.error("Failed to cross-post:", e)
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        {/* Composer */}
        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle>Compose Post</CardTitle>
            <CardDescription>Create and publish to multiple platforms</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              placeholder="What's on your mind?"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={5}
              className="resize-none"
            />
            <div>
              <p className="text-xs text-muted-foreground mb-2">Select Platforms</p>
              <div className="flex flex-wrap gap-2">
                {accounts.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No accounts connected. Connect accounts first.</p>
                ) : (
                  accounts.map((acc: any) => {
                    const isSelected = selectedPlatforms.includes(acc.platform)
                    return (
                      <button
                        key={acc.id}
                        onClick={() => togglePlatform(acc.platform)}
                        className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors ${
                          isSelected ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-400" : "border-border text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        <div className="h-2 w-2 rounded-full" style={{ backgroundColor: platformColors[acc.platform] || "#666" }} />
                        {acc.account_name || acc.platform}
                      </button>
                    )
                  })
                )}
              </div>
            </div>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" checked={publishNow} onChange={() => setPublishNow(true)} className="accent-cyan-500" />
                Publish Now
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" checked={!publishNow} onChange={() => setPublishNow(false)} className="accent-cyan-500" />
                Schedule
              </label>
              {!publishNow && (
                <Input type="number" value={scheduleMinutes} onChange={(e) => setScheduleMinutes(Number(e.target.value))} className="w-24" placeholder="min" />
              )}
            </div>
            <div className="flex gap-2">
              <Button onClick={handlePublish} disabled={!content.trim() || selectedPlatforms.length === 0}>
                <Send className="mr-2 h-4 w-4" /> {publishNow ? "Publish" : "Schedule"}
              </Button>
              <Button variant="outline" onClick={handleCrossPost} disabled={!content.trim() || selectedPlatforms.length === 0}>
                <Copy className="mr-2 h-4 w-4" /> Cross-Post
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Recent Posts */}
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Recent Posts</CardTitle></CardHeader>
          <CardContent>
            <ScrollArea className="h-80">
              {loading ? (
                <div className="py-8 text-center text-muted-foreground">Loading...</div>
              ) : posts.length === 0 ? (
                <div className="py-8 text-center text-muted-foreground">No posts yet</div>
              ) : (
                <div className="space-y-3">
                  {posts.map((post: any) => (
                    <div key={post.id} className="rounded-lg border border-border bg-background/40 p-3">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          {(post.platforms || []).map((p: string) => (
                            <span key={p} className="text-xs px-2 py-0.5 rounded-full border border-border" style={{ borderColor: platformColors[p] + "40", color: platformColors[p] }}>{p}</span>
                          ))}
                        </div>
                        <Badge variant="outline" className={statusColor[post.status] || "border-muted text-muted-foreground"}>{post.status}</Badge>
                      </div>
                      <p className="text-sm text-foreground line-clamp-2">{post.content}</p>
                      {post.engagement_data && (
                        <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1"><Heart className="h-3 w-3" /> {post.engagement_data.likes || 0}</span>
                          <span className="flex items-center gap-1"><MessageCircle className="h-3 w-3" /> {post.engagement_data.comments || 0}</span>
                          <span className="flex items-center gap-1"><Share2 className="h-3 w-3" /> {post.engagement_data.shares || 0}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// SOCIAL INBOX TAB
// ═══════════════════════════════════════════════════════════════════════════════

function SocialInboxTab() {
  const [messages, setMessages] = useState<any[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [filter, setFilter] = useState<string>("all")
  const [selectedMessage, setSelectedMessage] = useState<any>(null)
  const [replyText, setReplyText] = useState("")
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadInbox()
  }, [filter])

  const loadInbox = async () => {
    setLoading(true)
    try {
      const [msgData, countData] = await Promise.all([
        listInboxMessages(filter !== "all" ? { status: filter } : undefined).catch(() => []),
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

function WhatsAppTab({ view }: { view: "broadcasts" | "contacts" }) {
  const [contacts, setContacts] = useState<any[]>([])
  const [broadcasts, setBroadcasts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateBroadcast, setShowCreateBroadcast] = useState(false)
  const [newBroadcast, setNewBroadcast] = useState({ name: "", content: "", template_name: "" })

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [contactData, broadcastData] = await Promise.all([
        listWhatsAppContacts().catch(() => []),
        listWhatsAppBroadcasts().catch(() => []),
      ])
      setContacts(contactData || [])
      setBroadcasts(broadcastData || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleCreateBroadcast = async () => {
    if (!newBroadcast.name || !newBroadcast.content) return
    try {
      await createWhatsAppBroadcast(newBroadcast)
      setShowCreateBroadcast(false)
      setNewBroadcast({ name: "", content: "", template_name: "" })
      loadData()
    } catch (e) {
      console.error(e)
    }
  }

  const handleSend = async (id: string) => {
    try {
      await sendWhatsAppBroadcast(id)
      loadData()
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="space-y-6">
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
                        <Button size="sm" onClick={() => handleSend(b.id)}><Send className="mr-1 h-3 w-3" /> Send</Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

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
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// WHATSAPP PLACEHOLDER (Templates / Flows / Groups — not yet backed)
// ═══════════════════════════════════════════════════════════════════════════════

function WhatsAppComingSoon({
  title,
  description,
  icon: Icon,
}: {
  title: string
  description: string
  icon: IconType
}) {
  return (
    <Card className="border-dashed border-border bg-card/40">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
          <Icon className="h-6 w-6 text-primary" />
        </div>
        <div className="space-y-1">
          <p className="text-base font-semibold text-foreground">{title}</p>
          <Badge variant="outline" className="border-amber-500/40 text-amber-500">Coming soon</Badge>
        </div>
        <p className="max-w-md text-sm text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// ADS TAB
// ═══════════════════════════════════════════════════════════════════════════════

function AdsTab() {
  const [ads, setAds] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newAd, setNewAd] = useState({ name: "", platform: "facebook", objective: "AWARENESS", budget_zar: "", daily_budget_zar: "" })

  useEffect(() => {
    loadAds()
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

  const handleCreate = async () => {
    if (!newAd.name) return
    try {
      await createAdCampaign({ ...newAd, budget_zar: Number(newAd.budget_zar) || undefined, daily_budget_zar: Number(newAd.daily_budget_zar) || undefined })
      setShowCreate(false)
      setNewAd({ name: "", platform: "facebook", objective: "AWARENESS", budget_zar: "", daily_budget_zar: "" })
      loadAds()
    } catch (e) {
      console.error(e)
    }
  }

  const totalSpend = ads.reduce((s: number, a: any) => s + (a.spend_zar || 0), 0)
  const totalImpressions = ads.reduce((s: number, a: any) => s + (a.impressions || 0), 0)
  const totalClicks = ads.reduce((s: number, a: any) => s + (a.clicks || 0), 0)
  const avgROAS = ads.length > 0 ? (ads.reduce((s: number, a: any) => s + (a.roas || 0), 0) / ads.length).toFixed(1) : "0"

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "Active Ads", value: ads.filter((a: any) => a.status === "ACTIVE").length, icon: Play, color: "text-emerald-400", bg: "bg-emerald-500/10" },
          { label: "Total Spend", value: `R ${totalSpend.toLocaleString()}`, icon: DollarSign, color: "text-amber-400", bg: "bg-amber-500/10" },
          { label: "Impressions", value: totalImpressions.toLocaleString(), icon: Eye, color: "text-blue-400", bg: "bg-blue-500/10" },
          { label: "Avg ROAS", value: avgROAS + "x", icon: TrendingUp, color: "text-purple-400", bg: "bg-purple-500/10" },
        ].map((kpi: any) => (
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

      {/* Create + Table */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{ads.length} ad campaigns</p>
        <Button size="sm" onClick={() => setShowCreate(!showCreate)}><Plus className="mr-2 h-4 w-4" /> New Ad Campaign</Button>
      </div>

      {showCreate && (
        <Card className="border-border bg-card">
          <CardHeader><CardTitle className="text-sm">Create Ad Campaign</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Input placeholder="Campaign name" value={newAd.name} onChange={(e) => setNewAd({ ...newAd, name: e.target.value })} />
            <div className="grid gap-3 sm:grid-cols-3">
              <select value={newAd.platform} onChange={(e) => setNewAd({ ...newAd, platform: e.target.value })} className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
                <option value="facebook">Facebook</option><option value="instagram">Instagram</option>
                <option value="google">Google</option><option value="linkedin">LinkedIn</option>
                <option value="tiktok">TikTok</option>
              </select>
              <select value={newAd.objective} onChange={(e) => setNewAd({ ...newAd, objective: e.target.value })} className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
                <option value="AWARENESS">Awareness</option><option value="TRAFFIC">Traffic</option>
                <option value="CONVERSIONS">Conversions</option><option value="LEADS">Leads</option>
              </select>
              <Input placeholder="Budget (ZAR)" value={newAd.budget_zar} onChange={(e) => setNewAd({ ...newAd, budget_zar: e.target.value })} />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={handleCreate}>Create</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="py-12 text-center text-muted-foreground">Loading...</div>
      ) : ads.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground">No ad campaigns yet</div>
      ) : (
        <div className="space-y-3">
          {ads.map((ad: any) => (
            <Card key={ad.id} className="border-border bg-card">
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="font-medium text-foreground">{ad.name}</p>
                    <p className="text-xs text-muted-foreground">{ad.platform} · {ad.objective}</p>
                  </div>
                  <Badge variant="outline" className={statusColor[ad.status] || "border-muted text-muted-foreground"}>{ad.status}</Badge>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mt-3 text-sm">
                  <div><p className="text-xs text-muted-foreground">Budget</p><p className="text-foreground">R {(ad.budget_zar || 0).toLocaleString()}</p></div>
                  <div><p className="text-xs text-muted-foreground">Spend</p><p className="text-foreground">R {(ad.spend_zar || 0).toLocaleString()}</p></div>
                  <div><p className="text-xs text-muted-foreground">Impressions</p><p className="text-foreground">{(ad.impressions || 0).toLocaleString()}</p></div>
                  <div><p className="text-xs text-muted-foreground">Clicks</p><p className="text-foreground">{(ad.clicks || 0).toLocaleString()}</p></div>
                  <div><p className="text-xs text-muted-foreground">ROAS</p><p className="text-foreground">{ad.roas || 0}x</p></div>
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
