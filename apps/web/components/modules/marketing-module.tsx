"use client"

import { useEffect, useMemo, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
  Smartphone, Image, Calendar, Clock, CheckCircle, AlertTriangle, XCircle,
  ArrowUpRight, ArrowDownRight, Minus, Search, Filter, Download, RefreshCw,
  Link2, Unlink, Play, Pause, Trash2, Edit, Reply, Archive, ExternalLink,
  Hash, AtSign, Mail as MailIcon, Phone, Star, ThumbsUp, MessageCircle,
  Instagram, Twitter, Facebook, Linkedin, Youtube, Video, FileText, Copy,
} from "lucide-react"
import { useModuleData } from "@/lib/module-data"
import {
  listCampaigns, listSocialAccounts, listSocialPosts, listInboxMessages,
  getInboxUnreadCount, listWhatsAppContacts, listWhatsAppBroadcasts,
  listAdCampaigns, listCommentAutomations, getEngagementSummary,
  createSocialPost, publishSocialPost, crossPost, createWhatsAppBroadcast,
  sendWhatsAppBroadcast, createCommentAutomation, replyToInboxMessage,
  archiveInboxMessage, markInboxRead, createAdCampaign, updateAdCampaign,
} from "@/lib/marketing-api"

// ═══════════════════════════════════════════════════════════════════════════════
// ICON MAPS
// ═══════════════════════════════════════════════════════════════════════════════

const platformIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  twitter, instagram, facebook, linkedin, tiktok, whatsapp: MessageCircle,
  youtube, pinterest: Pin, threads: AtSign, bluesky: Cloud, telegram: Send,
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
// EXISTING DATA (traditional marketing — kept from original module)
// ═══════════════════════════════════════════════════════════════════════════════

const defaultChannelData = [
  { name: "Email", value: 32, fill: "#4ade80" },
  { name: "Social", value: 28, fill: "#60a5fa" },
  { name: "Search", value: 18, fill: "#f59e0b" },
  { name: "Display", value: 12, fill: "#a78bfa" },
  { name: "SMS", value: 10, fill: "#f472b6" },
]

const defaultROI = [
  { campaign: "Summer Promo", roi: 3.2 },
  { campaign: "Back to School", roi: 2.8 },
  { campaign: "Holiday Sale", roi: 4.1 },
  { campaign: "Black Friday", roi: 5.2 },
  { campaign: "New Year", roi: 2.4 },
]

const defaultLeadFunnel = [
  { name: "Leads", value: 18400, fill: "#a78bfa" },
  { name: "MQL", value: 9200, fill: "#60a5fa" },
  { name: "SQL", value: 4600, fill: "#4ade80" },
  { name: "Customers", value: 1840, fill: "#f59e0b" },
]

const defaultRadioStations = [
  { station: "KFM", type: "Regional", listeners: "1.2M", spotsBooked: 24, spend: "R 180,000", reach: "Western Cape", ctr: "1.8%" },
  { station: "East Coast Radio", type: "Regional", listeners: "2.1M", spotsBooked: 40, spend: "R 240,000", reach: "KwaZulu-Natal", ctr: "2.3%" },
  { station: "Jacaranda FM", type: "National", listeners: "3.8M", spotsBooked: 60, spend: "R 420,000", reach: "National", ctr: "3.1%" },
  { station: "5FM", type: "National", listeners: "4.2M", spotsBooked: 48, spend: "R 380,000", reach: "National", ctr: "2.7%" },
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
  { name: "National", value: 45, fill: "#4ade80" },
  { name: "Regional", value: 35, fill: "#60a5fa" },
  { name: "Community", value: 20, fill: "#f59e0b" },
]

const defaultBillboardData = [
  { name: "High-Traffic Highway", value: 35, fill: "#4ade80" },
  { name: "Urban CBD", value: 28, fill: "#60a5fa" },
  { name: "Suburban Retail", value: 22, fill: "#f59e0b" },
  { name: "Airport", value: 15, fill: "#a78bfa" },
]

const defaultOOHMetrics = [
  { medium: "Airport Screens", campaigns: 6, impressions: "8.4M", dwellTime: "6.2s", attentionRate: "78%", footTrafficLift: "+31%", brandRecall: "52%" },
  { medium: "Digital Billboards", campaigns: 9, impressions: "14.6M", dwellTime: "3.8s", attentionRate: "62%", footTrafficLift: "+18%", brandRecall: "38%" },
  { medium: "Static Billboards", campaigns: 12, impressions: "22.1M", dwellTime: "2.1s", attentionRate: "45%", footTrafficLift: "+12%", brandRecall: "28%" },
]

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN MODULE
// ═══════════════════════════════════════════════════════════════════════════════

type MarketingTab = "campaigns" | "social-composer" | "social-inbox" | "social-analytics" | "whatsapp" | "ads" | "automations" | "traditional"

export function MarketingModule() {
  const [activeTab, setActiveTab] = useState<MarketingTab>("campaigns")

  const tabs: { key: MarketingTab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { key: "campaigns", label: "Campaigns", icon: Megaphone },
    { key: "social-composer", label: "Social Composer", icon: Send },
    { key: "social-inbox", label: "Social Inbox", icon: MessageSquare },
    { key: "social-analytics", label: "Social Analytics", icon: BarChart3 },
    { key: "whatsapp", label: "WhatsApp", icon: Smartphone },
    { key: "ads", label: "Ad Campaigns", icon: Target },
    { key: "automations", label: "Automations", icon: Zap },
    { key: "traditional", label: "Traditional", icon: Radio },
  ]

  return (
    <div className="space-y-6">
      {/* Tab Navigation */}
      <div className="flex items-center gap-1 border-b border-border pb-1 overflow-x-auto">
        {tabs.map((tab) => {
          const Icon = tab.icon
          const isActive = tab.key === activeTab
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap ${
                isActive
                  ? "bg-card text-foreground border border-border border-b-0 -mb-px"
                  : "text-muted-foreground hover:text-foreground hover:bg-card/50"
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab Content */}
      {activeTab === "campaigns" && <CampaignsTab />}
      {activeTab === "social-composer" && <SocialComposerTab />}
      {activeTab === "social-inbox" && <SocialInboxTab />}
      {activeTab === "social-analytics" && <SocialAnalyticsTab />}
      {activeTab === "whatsapp" && <WhatsAppTab />}
      {activeTab === "ads" && <AdsTab />}
      {activeTab === "automations" && <AutomationsTab />}
      {activeTab === "traditional" && <TraditionalTab />}
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
    try {
      await listCampaigns() // refresh
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

      {/* Channel Distribution + ROI */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Channel Distribution</CardTitle></CardHeader>
          <CardContent><div className="h-64"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={defaultChannelData} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, value }) => `${name}: ${value}%`}>{defaultChannelData.map((e, i) => <Cell key={i} fill={e.fill} />)}</Pie><Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} /></PieChart></ResponsiveContainer></div></CardContent>
        </Card>
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Campaign ROI</CardTitle></CardHeader>
          <CardContent><div className="h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={defaultROI}><CartesianGrid strokeDasharray="3 3" stroke="#404040" /><XAxis dataKey="campaign" tick={{ fill: "#737373", fontSize: 10 }} /><YAxis tick={{ fill: "#737373", fontSize: 12 }} /><Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} /><Bar dataKey="roi" fill="#4ade80" name="ROI" /></BarChart></ResponsiveContainer></div></CardContent>
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
        await createSocialPost({ content, platforms: selectedPlatforms, status: "published" })
      } else {
        await createSocialPost({ content, platforms: selectedPlatforms, status: "scheduled", schedule_minutes: scheduleMinutes })
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
      await crossPost({ content, platforms: selectedPlatforms, publish_now: publishNow, schedule_minutes: publishNow ? undefined : scheduleMinutes })
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
        getInboxUnreadCount().catch(() => ({ count: 0 })),
      ])
      setMessages(msgData || [])
      setUnreadCount(countData?.count || 0)
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

function SocialAnalyticsTab() {
  const [summary, setSummary] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadAnalytics()
  }, [])

  const loadAnalytics = async () => {
    setLoading(true)
    try {
      const data = await getEngagementSummary().catch(() => null)
      setSummary(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const engagementData = summary?.by_platform || [
    { platform: "Twitter", followers: 12400, impressions: 450000, engagement: 3.2 },
    { platform: "Instagram", followers: 28100, impressions: 890000, engagement: 4.8 },
    { platform: "Facebook", followers: 18600, impressions: 620000, engagement: 2.9 },
    { platform: "LinkedIn", followers: 8200, impressions: 180000, engagement: 5.1 },
  ]

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "Total Followers", value: engagementData.reduce((s: number, d: any) => s + (d.followers || 0), 0).toLocaleString(), icon: Users, color: "text-blue-400", bg: "bg-blue-500/10" },
          { label: "Total Impressions", value: engagementData.reduce((s: number, d: any) => s + (d.impressions || 0), 0).toLocaleString(), icon: Eye, color: "text-purple-400", bg: "bg-purple-500/10" },
          { label: "Avg Engagement", value: (engagementData.reduce((s: number, d: any) => s + (d.engagement || 0), 0) / Math.max(engagementData.length, 1)).toFixed(1) + "%", icon: Heart, color: "text-pink-400", bg: "bg-pink-500/10" },
          { label: "Platforms", value: engagementData.length, icon: Globe, color: "text-emerald-400", bg: "bg-emerald-500/10" },
        ].map((kpi: any) => (
          <Card key={kpi.label} className="border-border bg-card">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">{kpi.label}</p>
                  <p className="text-2xl font-semibold text-foreground">{kpi.value}</p>
                </div>
                <div className={`rounded-lg ${kpi.bg} p-2`}><kpi.icon className={`h-5 w-5 ${kpi.color}`} /></div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Followers by Platform</CardTitle></CardHeader>
          <CardContent><div className="h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={engagementData}><CartesianGrid strokeDasharray="3 3" stroke="#404040" /><XAxis dataKey="platform" tick={{ fill: "#737373", fontSize: 12 }} /><YAxis tick={{ fill: "#737373", fontSize: 12 }} /><Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} /><Bar dataKey="followers" fill="#60a5fa" name="Followers" /></BarChart></ResponsiveContainer></div></CardContent>
        </Card>
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Engagement Rate by Platform</CardTitle></CardHeader>
          <CardContent><div className="h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={engagementData}><CartesianGrid strokeDasharray="3 3" stroke="#404040" /><XAxis dataKey="platform" tick={{ fill: "#737373", fontSize: 12 }} /><YAxis tick={{ fill: "#737373", fontSize: 12 }} /><Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} /><Bar dataKey="engagement" fill="#4ade80" name="Engagement %" /></BarChart></ResponsiveContainer></div></CardContent>
        </Card>
      </div>

      {/* Platform Breakdown Table */}
      <Card className="border-border bg-card">
        <CardHeader><CardTitle>Platform Breakdown</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[600px]">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Platform</th>
                  <th className="py-2 pr-4 font-medium">Followers</th>
                  <th className="py-2 pr-4 font-medium">Impressions</th>
                  <th className="py-2 font-medium">Engagement Rate</th>
                </tr>
              </thead>
              <tbody>
                {engagementData.map((row: any) => (
                  <tr key={row.platform} className="border-b border-border/60 text-sm">
                    <td className="py-3 pr-4 text-foreground font-medium flex items-center gap-2">
                      <div className="h-2 w-2 rounded-full" style={{ backgroundColor: platformColors[row.platform?.toLowerCase()] || "#666" }} />
                      {row.platform}
                    </td>
                    <td className="py-3 pr-4 text-muted-foreground">{(row.followers || 0).toLocaleString()}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{(row.impressions || 0).toLocaleString()}</td>
                    <td className="py-3 text-muted-foreground">{row.engagement || 0}%</td>
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
// WHATSAPP TAB
// ═══════════════════════════════════════════════════════════════════════════════

function WhatsAppTab() {
  const [contacts, setContacts] = useState<any[]>([])
  const [broadcasts, setBroadcasts] = useState<any[]>([])
  const [activeWhatsappTab, setActiveWhatsappTab] = useState<"contacts" | "broadcasts">("broadcasts")
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
      {/* Sub-tabs */}
      <div className="flex items-center gap-2 border-b border-border pb-2">
        <button onClick={() => setActiveWhatsappTab("broadcasts")} className={`px-4 py-2 text-sm font-medium rounded-t-lg ${activeWhatsappTab === "broadcasts" ? "bg-card text-foreground border border-border border-b-0 -mb-px" : "text-muted-foreground"}`}>
          Broadcasts
        </button>
        <button onClick={() => setActiveWhatsappTab("contacts")} className={`px-4 py-2 text-sm font-medium rounded-t-lg ${activeWhatsappTab === "contacts" ? "bg-card text-foreground border border-border border-b-0 -mb-px" : "text-muted-foreground"}`}>
          Contacts ({contacts.length})
        </button>
      </div>

      {activeWhatsappTab === "broadcasts" && (
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

      {activeWhatsappTab === "contacts" && (
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
      await createAdCampaign(newAd)
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
  const [newAuto, setNewAuto] = useState({ name: "", trigger_type: "KEYWORD", trigger_keywords: "", response_template: "" })

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
      setNewAuto({ name: "", trigger_type: "KEYWORD", trigger_keywords: "", response_template: "" })
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

function TraditionalTab() {
  const { data } = useModuleData("marketing", {
    channelData: defaultChannelData,
    roiData: defaultROI,
    leadFunnel: defaultLeadFunnel,
    radioPerformance: defaultRadioPerformance,
    radioByType: defaultRadioByType,
  })

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "Campaigns Analyzed", value: "24", icon: BarChart3, color: "text-blue-400", bg: "bg-blue-500/10" },
          { label: "Total Reach", value: "68.4M", icon: Users, color: "text-emerald-400", bg: "bg-emerald-500/10" },
          { label: "Avg ROI", value: "3.5x", icon: TrendingUp, color: "text-amber-400", bg: "bg-amber-500/10" },
          { label: "Active Channels", value: "5", icon: Radio, color: "text-purple-400", bg: "bg-purple-500/10" },
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

      {/* Radio + Billboard */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Radio Performance</CardTitle><CardDescription>Spots, reach, and leads over time</CardDescription></CardHeader>
          <CardContent><div className="h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={data.radioPerformance}><CartesianGrid strokeDasharray="3 3" stroke="#404040" /><XAxis dataKey="month" tick={{ fill: "#737373", fontSize: 12 }} /><YAxis tick={{ fill: "#737373", fontSize: 12 }} /><Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} /><Legend /><Bar dataKey="spots" fill="#4ade80" name="Spots" /><Bar dataKey="leads" fill="#60a5fa" name="Leads" /></BarChart></ResponsiveContainer></div></CardContent>
        </Card>
        <Card className="border-border bg-card">
          <CardHeader><CardTitle>Radio by Type</CardTitle></CardHeader>
          <CardContent><div className="h-64"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data.radioByType} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, value }) => `${name}: ${value}%`}>{data.radioByType.map((e: any, i: number) => <Cell key={i} fill={e.fill} />)}</Pie><Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} /></PieChart></ResponsiveContainer></div></CardContent>
        </Card>
      </div>

      {/* Radio Stations Table */}
      <Card className="border-border bg-card">
        <CardHeader><CardTitle>Radio Stations</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px]">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Station</th><th className="py-2 pr-4 font-medium">Type</th>
                  <th className="py-2 pr-4 font-medium">Listeners</th><th className="py-2 pr-4 font-medium">Spots</th>
                  <th className="py-2 pr-4 font-medium">Spend</th><th className="py-2 pr-4 font-medium">Reach</th>
                  <th className="py-2 font-medium">CTR</th>
                </tr>
              </thead>
              <tbody>
                {defaultRadioStations.map((row) => (
                  <tr key={row.station} className="border-b border-border/60 text-sm">
                    <td className="py-3 pr-4 text-foreground font-medium">{row.station}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.type}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.listeners}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.spotsBooked}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.spend}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.reach}</td>
                    <td className="py-3 text-muted-foreground">{row.ctr}</td>
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
                  <th className="py-2 pr-4 font-medium">Medium</th><th className="py-2 pr-4 font-medium">Campaigns</th>
                  <th className="py-2 pr-4 font-medium">Impressions</th><th className="py-2 pr-4 font-medium">Dwell Time</th>
                  <th className="py-2 pr-4 font-medium">Attention</th><th className="py-2 pr-4 font-medium">Traffic Lift</th>
                  <th className="py-2 font-medium">Brand Recall</th>
                </tr>
              </thead>
              <tbody>
                {defaultOOHMetrics.map((row) => (
                  <tr key={row.medium} className="border-b border-border/60 text-sm">
                    <td className="py-3 pr-4 text-foreground font-medium">{row.medium}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.campaigns}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.impressions}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.dwellTime}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.attentionRate}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{row.footTrafficLift}</td>
                    <td className="py-3 text-muted-foreground">{row.brandRecall}</td>
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
