"use client"

import { supabase } from "@/lib/supabase/client"

/**
 * Marketing API client — campaigns, social media, WhatsApp, ads,
 * comment automations, email, and analytics.
 * Proxies through the Next.js API routes to the marketing service.
 */

const API_BASE = "/svc/marketing"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const FALLBACK_USER_ID = "00000000-0000-0000-0000-000000000001"

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession()
  const tenantId =
    data.session?.user?.user_metadata?.tenant_id ??
    data.session?.user?.app_metadata?.tenant_id ??
    FALLBACK_TENANT_ID
  const userId = data.session?.user?.id ?? FALLBACK_USER_ID
  return { "x-tenant-id": tenantId, "x-user-id": userId }
}

async function fetchMarketing<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers: { ...(await getAuthHeaders()), "Content-Type": "application/json" },
      ...init,
    })
    if (!res.ok) {
      console.warn(`Marketing API error ${res.status} for ${path}`)
      return null
    }
    return res.json()
  } catch (error) {
    console.warn(`Marketing API unreachable for ${path}`, error)
    return null
  }
}

// ── Types ─────────────────────────────────────────────────────────────

export interface Campaign {
  id: string
  tenant_id: string
  name: string
  channel: string
  description?: string
  budget_zar?: number
  start_date?: string
  end_date?: string
  status: string
  created_at: string
  updated_at?: string
}

export interface CampaignCreate {
  name: string
  channel: string
  description?: string
  budget_zar?: number
  start_date?: string
  end_date?: string
}

export interface SocialAccount {
  id: string
  tenant_id: string
  platform: string
  account_name: string
  account_handle: string
  access_token: string
  refresh_token?: string
  status: string
  created_at: string
  updated_at?: string
}

export interface SocialAccountCreate {
  platform: string
  account_name: string
  account_handle: string
  access_token: string
  refresh_token?: string
}

export interface SocialPost {
  id: string
  tenant_id: string
  account_id: string
  campaign_id?: string
  content: string
  media_urls?: string[]
  platforms: string[]
  status: string
  scheduled_for?: string
  published_at?: string
  created_at: string
  updated_at?: string
}

export interface SocialPostCreate {
  account_id?: string
  content: string
  media_urls?: string[]
  platforms: string[]
  status?: string
  scheduled_for?: string
  campaign_id?: string
}

export interface CrossPostInput {
  content: string
  platforms: string[]
  account_ids?: string[]
  media_urls?: string[]
  schedule_minutes?: number
}

export interface InboxMessage {
  id: string
  tenant_id: string
  account_id: string
  platform: string
  message_type: string
  sender_name?: string
  sender_handle?: string
  content: string
  status: string
  created_at: string
  updated_at?: string
}

export interface InboxUnreadCount {
  unread_count: number
}

export interface AccountAnalytics {
  account_id: string
  platform: string
  followers: number
  impressions: number
  reach: number
  engagements: number
  engagement_rate: number
  from_date?: string
  to_date?: string
}

export interface PlatformAnalytics {
  platform: string
  total_impressions: number
  total_reach: number
  total_engagements: number
  avg_engagement_rate: number
  from_date?: string
  to_date?: string
}

export interface BestTimeToPost {
  account_id: string
  best_days: string[]
  best_hours: number[]
  timezone: string
}

export interface EngagementSummary {
  total_impressions: number
  total_reach: number
  total_engagements: number
  avg_engagement_rate: number
  by_platform: Record<string, {
    impressions: number
    reach: number
    engagements: number
    engagement_rate: number
  }>
  from_date?: string
  to_date?: string
}

export interface WhatsAppContact {
  id: string
  tenant_id: string
  name: string
  phone_number: string
  email?: string
  tags?: string[]
  opt_in_status: string
  created_at: string
  updated_at?: string
}

export interface WhatsAppContactCreate {
  name: string
  phone_number: string
  email?: string
  tags?: string[]
}

export interface WhatsAppBroadcast {
  id: string
  tenant_id: string
  name: string
  template_name: string
  content: string
  media_url?: string
  recipient_ids: string[]
  scheduled_for?: string
  status: string
  created_at: string
  updated_at?: string
}

export interface WhatsAppBroadcastCreate {
  name: string
  template_name: string
  content: string
  media_url?: string
  recipient_ids?: string[]
  scheduled_for?: string
}

export interface WhatsAppBroadcastStats {
  broadcast_id: string
  total_recipients: number
  sent: number
  delivered: number
  read: number
  failed: number
}

export interface WhatsAppSender {
  id: string
  name: string
  number: string
  type: string
  name_review: string
  business_verification: string
  status: string
  created_at?: string
}

export interface WhatsAppTemplate {
  id: string
  name: string
  category: string
  language: string
  status: string
  header?: string
  body: string
  footer?: string
  buttons?: string[]
  created_at?: string
}

export interface WhatsAppFlowNode {
  id: string
  type: string
  label: string
}

export interface WhatsAppFlow {
  id: string
  name: string
  trigger: string
  status: string
  steps_count: number
  nodes: WhatsAppFlowNode[]
  created_at?: string
}

export interface WhatsAppGroup {
  id: string
  sender_id?: string
  sender_name?: string
  sender_number?: string
  name: string
  participant_count: number
  role: "admin" | "member"
  invite_link?: string
  is_active: boolean
  last_message_at?: string
  created_at?: string
}

export interface WhatsAppConversion {
  id: string
  customer_name: string
  phone_number: string
  deal_name: string
  deal_value_zar: number
  event_type: "QUOTE_REQUEST" | "ORDER_PLACED" | "LEAD_CAPTURED" | "CHECKOUT_COMPLETED"
  flow_or_template: string
  sales_channel: "MARKETING"
  status: "DEAL_CREATED" | "CONVERTED" | "PENDING_SALES"
  created_at: string
}

export interface AdCampaign {
  id: string
  tenant_id: string
  name: string
  platform: string
  objective: string
  budget_zar?: number
  daily_budget_zar?: number
  start_date?: string
  end_date?: string
  targeting?: Record<string, unknown>
  creative?: Record<string, unknown>
  status: string
  created_at: string
  updated_at?: string
}

export interface AdCampaignCreate {
  name: string
  platform: string
  objective: string
  budget_zar?: number
  daily_budget_zar?: number
  start_date?: string
  end_date?: string
  targeting?: Record<string, unknown>
  creative?: Record<string, unknown>
  status?: string
}

export interface AdCampaignAnalytics {
  campaign_id: string
  impressions: number
  clicks: number
  spend_zar: number
  conversions: number
  ctr: number
  cpc_zar: number
  roas?: number
}

export interface CommentAutomation {
  id: string
  tenant_id: string
  name: string
  account_id: string
  trigger_type: string
  trigger_keywords?: string[]
  response_template: string
  is_active: boolean
  created_at: string
  updated_at?: string
}

export interface CommentAutomationCreate {
  name: string
  account_id: string
  trigger_type: string
  trigger_keywords?: string[]
  response_template: string
}

export interface EmailBatchSendInput {
  campaign_id: string
  subject: string
  body_html: string
  recipients: string[]
  from_name?: string
  from_email?: string
}

export interface EmailTemplate {
  id: string
  tenant_id: string
  name: string
  subject: string
  body_html: string
  category?: string
  created_at: string
  updated_at?: string
}

export interface EmailTemplateCreate {
  name: string
  subject: string
  body_html: string
  category?: string
}

export interface AudienceSegment {
  id: string
  tenant_id: string
  name: string
  description?: string
  rules?: Record<string, unknown>
  created_at: string
  updated_at?: string
}

export interface AudienceSegmentCreate {
  name: string
  description?: string
  rules?: Record<string, unknown>
}

// ── Campaigns ────────────────────────────────────────────────────────

export const listCampaigns = (params?: { channel?: string; status?: string; limit?: number; offset?: number }) => {
  const q = new URLSearchParams()
  if (params?.channel) q.set("channel", params.channel)
  if (params?.status) q.set("status", params.status)
  if (params?.limit != null) q.set("limit", String(params.limit))
  if (params?.offset != null) q.set("offset", String(params.offset))
  return fetchMarketing<Campaign[]>(`/campaigns?${q}`)
}

export const createCampaign = (data: CampaignCreate) =>
  fetchMarketing<Campaign>("/campaigns", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const getCampaign = (id: string) =>
  fetchMarketing<Campaign>(`/campaigns/${id}`)

export const updateCampaign = (id: string, data: Partial<Campaign>) =>
  fetchMarketing<Campaign>(`/campaigns/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })

export const deleteCampaign = (id: string) =>
  fetchMarketing<{ status: string }>(`/campaigns/${id}`, {
    method: "DELETE",
  })

// ── Social Media Accounts ────────────────────────────────────────────

export const listSocialAccounts = (params?: { platform?: string; status?: string }) => {
  const q = new URLSearchParams()
  if (params?.platform) q.set("platform", params.platform)
  if (params?.status) q.set("status", params.status)
  return fetchMarketing<SocialAccount[]>(`/social/accounts?${q}`)
}

export const createSocialAccount = (data: SocialAccountCreate) =>
  fetchMarketing<SocialAccount>("/social/accounts", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const getSocialAccount = (id: string) =>
  fetchMarketing<SocialAccount>(`/social/accounts/${id}`)

export const updateSocialAccount = (id: string, data: Partial<SocialAccount>) =>
  fetchMarketing<SocialAccount>(`/social/accounts/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const deleteSocialAccount = (id: string) =>
  fetchMarketing<{ status: string }>(`/social/accounts/${id}`, {
    method: "DELETE",
  })

export const connectSocialAccount = (platform: string) =>
  // Backend returns { platform, auth_url } (Zernio hosted connect URL).
  fetchMarketing<{ platform: string; auth_url: string }>(`/social/accounts/connect/${encodeURIComponent(platform)}`)

export const disconnectSocialAccount = (id: string) =>
  fetchMarketing<{ status: string }>(`/social/accounts/${id}`, {
    method: "DELETE",
  })

// ── Social Posts ─────────────────────────────────────────────────────

export const listSocialPosts = (params?: { status?: string; account_id?: string; campaign_id?: string }) => {
  const q = new URLSearchParams()
  if (params?.status) q.set("status", params.status)
  if (params?.account_id) q.set("account_id", params.account_id)
  if (params?.campaign_id) q.set("campaign_id", params.campaign_id)
  return fetchMarketing<SocialPost[]>(`/social/posts?${q}`)
}

export const createSocialPost = (data: SocialPostCreate) =>
  fetchMarketing<SocialPost>("/social/posts", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const updateSocialPost = (id: string, data: Partial<SocialPost>) =>
  fetchMarketing<SocialPost>(`/social/posts/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const deleteSocialPost = (id: string) =>
  fetchMarketing<{ status: string }>(`/social/posts/${id}`, {
    method: "DELETE",
  })

export const publishSocialPost = (id: string) =>
  fetchMarketing<{ status: string; published_at: string }>(`/social/posts/${id}/publish`, {
    method: "POST",
  })

export const crossPost = (data: CrossPostInput) =>
  fetchMarketing<{ status: string; posted_to: string[] }>("/social/posts/cross-post", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const getSocialPostAnalytics = (id: string) =>
  fetchMarketing<Record<string, unknown>>(`/social/posts/${id}/analytics`)

// ── Posting queues (recurring slots) ─────────────────────────────────────

export interface QueueSlot { day: number; time: string }

export interface MarketingQueue {
  id: string
  name: string
  description?: string | null
  status: string
  timezone: string
  slots: QueueSlot[]
  next_slot: string | null
  created_at?: string | null
}

export const listQueues = () =>
  fetchMarketing<{ queues: MarketingQueue[] }>("/social/queues")

export const createQueue = (body: { name: string; description?: string; timezone: string; status?: string; slots: QueueSlot[] }) =>
  fetchMarketing<MarketingQueue>("/social/queues", { method: "POST", body: JSON.stringify(body) })

export const updateQueue = (id: string, body: Partial<{ name: string; description: string; timezone: string; status: string; slots: QueueSlot[] }>) =>
  fetchMarketing<{ id: string; updated: boolean }>(`/social/queues/${id}`, { method: "PATCH", body: JSON.stringify(body) })

export const deleteQueue = (id: string) =>
  fetchMarketing<{ status: string }>(`/social/queues/${id}`, { method: "DELETE" })

export const enqueuePost = (queueId: string, body: SocialPostCreate) =>
  fetchMarketing<{ id: string; status: string; scheduled_for: string; queue_id: string }>(`/social/queues/${queueId}/enqueue`, {
    method: "POST",
    body: JSON.stringify(body),
  })

// ── Social Inbox ─────────────────────────────────────────────────────

export const listInboxMessages = (params?: { status?: string; platform?: string; message_type?: string; account_id?: string }) => {
  const q = new URLSearchParams()
  if (params?.status) q.set("status", params.status)
  if (params?.platform) q.set("platform", params.platform)
  if (params?.message_type) q.set("message_type", params.message_type)
  if (params?.account_id) q.set("account_id", params.account_id)
  return fetchMarketing<InboxMessage[]>(`/social/inbox?${q}`)
}

export const getInboxMessage = (id: string) =>
  fetchMarketing<InboxMessage>(`/social/inbox/${id}`)

export const replyToInboxMessage = (id: string, content: string) =>
  fetchMarketing<{ status: string }>(`/social/inbox/${id}/reply`, {
    method: "POST",
    body: JSON.stringify({ content }),
  })

export const archiveInboxMessage = (id: string) =>
  fetchMarketing<{ status: string }>(`/social/inbox/${id}/archive`, {
    method: "PUT",
  })

export const markInboxRead = (id: string) =>
  fetchMarketing<{ status: string }>(`/social/inbox/${id}/read`, {
    method: "PUT",
  })

export const getInboxUnreadCount = () =>
  fetchMarketing<InboxUnreadCount>("/social/inbox/unread-count")

// ── Social Analytics ─────────────────────────────────────────────────

export const getAccountAnalytics = (account_id: string, from_date?: string, to_date?: string) => {
  const q = new URLSearchParams()
  if (from_date) q.set("from_date", from_date)
  if (to_date) q.set("to_date", to_date)
  return fetchMarketing<AccountAnalytics>(`/social/analytics/account/${encodeURIComponent(account_id)}?${q}`)
}

export const getPlatformAnalytics = (platform: string, from_date?: string, to_date?: string) => {
  const q = new URLSearchParams()
  if (from_date) q.set("from_date", from_date)
  if (to_date) q.set("to_date", to_date)
  return fetchMarketing<PlatformAnalytics>(`/social/analytics/platform/${encodeURIComponent(platform)}?${q}`)
}

export const getBestTimeToPost = (account_id: string) =>
  fetchMarketing<BestTimeToPost>(`/social/analytics/best-time?account_id=${encodeURIComponent(account_id)}`)

export const getEngagementSummary = (params?: { from_date?: string; to_date?: string }) => {
  const q = new URLSearchParams()
  if (params?.from_date) q.set("from_date", params.from_date)
  if (params?.to_date) q.set("to_date", params.to_date)
  return fetchMarketing<EngagementSummary>(`/social/analytics/engagement?${q}`)
}

// ── WhatsApp ─────────────────────────────────────────────────────────

export const listWhatsAppContacts = (params?: { tag?: string; opt_in_status?: string }) => {
  const q = new URLSearchParams()
  if (params?.tag) q.set("tag", params.tag)
  if (params?.opt_in_status) q.set("opt_in_status", params.opt_in_status)
  return fetchMarketing<WhatsAppContact[]>(`/whatsapp/contacts?${q}`)
}

export const createWhatsAppContact = (data: WhatsAppContactCreate) =>
  fetchMarketing<WhatsAppContact>("/whatsapp/contacts", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const bulkImportWhatsAppContacts = (contacts: WhatsAppContactCreate[]) =>
  fetchMarketing<{ imported: number; contacts: WhatsAppContact[] }>("/whatsapp/contacts/bulk-import", {
    method: "POST",
    body: JSON.stringify({ contacts }),
  })

export const listWhatsAppBroadcasts = (params?: { status?: string }) => {
  const q = new URLSearchParams()
  if (params?.status) q.set("status", params.status)
  return fetchMarketing<WhatsAppBroadcast[]>(`/whatsapp/broadcasts?${q}`)
}

export const createWhatsAppBroadcast = (data: WhatsAppBroadcastCreate) =>
  fetchMarketing<WhatsAppBroadcast>("/whatsapp/broadcasts", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const sendWhatsAppBroadcast = (id: string) =>
  fetchMarketing<{ status: string }>(`/whatsapp/broadcasts/${id}/send`, {
    method: "POST",
  })

export const getWhatsAppBroadcastStats = (id: string) =>
  fetchMarketing<WhatsAppBroadcastStats>(`/whatsapp/broadcasts/${id}/stats`)

export const listWhatsAppSenders = () =>
  fetchMarketing<WhatsAppSender[]>("/whatsapp/senders")

export const connectWhatsAppNumber = (data: { mode: "get_number" | "own_number"; country_code?: string; phone_number?: string; display_name?: string }) =>
  fetchMarketing<WhatsAppSender>("/whatsapp/senders/connect", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const listWhatsAppTemplates = () =>
  fetchMarketing<WhatsAppTemplate[]>("/whatsapp/templates")

export const createWhatsAppTemplate = (data: { name: string; category: string; language: string; header?: string; body: string; footer?: string; buttons?: string[] }) =>
  fetchMarketing<WhatsAppTemplate>("/whatsapp/templates", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const listWhatsAppFlows = () =>
  fetchMarketing<WhatsAppFlow[]>("/whatsapp/flows")

export const createWhatsAppFlow = (data: { name: string; trigger: string; nodes: WhatsAppFlowNode[] }) =>
  fetchMarketing<WhatsAppFlow>("/whatsapp/flows", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const listWhatsAppGroups = (senderId?: string) => {
  const q = senderId ? `?sender_id=${encodeURIComponent(senderId)}` : ""
  return fetchMarketing<WhatsAppGroup[]>(`/whatsapp/groups${q}`)
}

export const createWhatsAppGroup = (data: { sender_id?: string; name: string; invite_link?: string }) =>
  fetchMarketing<WhatsAppGroup>("/whatsapp/groups", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const listWhatsAppConversions = () =>
  fetchMarketing<WhatsAppConversion[]>("/whatsapp/conversions")

// ── Ad Campaigns ─────────────────────────────────────────────────────

export const listAdCampaigns = (params?: { platform?: string; status?: string }) => {
  const q = new URLSearchParams()
  if (params?.platform) q.set("platform", params.platform)
  if (params?.status) q.set("status", params.status)
  return fetchMarketing<AdCampaign[]>(`/ads/campaigns?${q}`)
}

export const createAdCampaign = (data: AdCampaignCreate) =>
  fetchMarketing<AdCampaign>("/ads/campaigns", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const updateAdCampaign = (id: string, data: Partial<AdCampaign>) =>
  fetchMarketing<AdCampaign>(`/ads/campaigns/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const deleteAdCampaign = (id: string) =>
  fetchMarketing<{ status: string }>(`/ads/campaigns/${id}`, {
    method: "DELETE",
  })

export const getAdCampaignAnalytics = (id: string) =>
  fetchMarketing<AdCampaignAnalytics>(`/ads/campaigns/${id}/analytics`)

// ── Comment Automations ──────────────────────────────────────────────

export const listCommentAutomations = (params?: { account_id?: string; is_active?: boolean }) => {
  const q = new URLSearchParams()
  if (params?.account_id) q.set("account_id", params.account_id)
  if (params?.is_active != null) q.set("is_active", String(params.is_active))
  return fetchMarketing<CommentAutomation[]>(`/social/automations?${q}`)
}

export const createCommentAutomation = (data: CommentAutomationCreate) =>
  fetchMarketing<CommentAutomation>("/social/automations", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const updateCommentAutomation = (id: string, data: Partial<CommentAutomation>) =>
  fetchMarketing<CommentAutomation>(`/social/automations/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const deleteCommentAutomation = (id: string) =>
  fetchMarketing<{ status: string }>(`/social/automations/${id}`, {
    method: "DELETE",
  })

// ── Email ────────────────────────────────────────────────────────────

export const sendEmailBatch = (data: EmailBatchSendInput) =>
  fetchMarketing<{ status: string; sent: number }>("/email/send", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const listEmailTemplates = () =>
  fetchMarketing<EmailTemplate[]>("/templates")

export const createEmailTemplate = (data: EmailTemplateCreate) =>
  fetchMarketing<EmailTemplate>("/templates", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const listAudienceSegments = () =>
  fetchMarketing<AudienceSegment[]>("/segments")

export const createAudienceSegment = (data: AudienceSegmentCreate) =>
  fetchMarketing<AudienceSegment>("/segments", {
    method: "POST",
    body: JSON.stringify(data),
  })

// ── Traditional Media (Radio / OOH / Billboard) ────────────────────────

export interface TraditionalCampaign {
  id: string
  tenant_id: string
  medium: "radio" | "billboard" | "ooh_screen"
  name: string
  category?: string
  reach?: string
  spots_booked: number
  impressions: number
  spend_zar: number
  leads_generated: number
  metrics?: Record<string, unknown>
  period_month?: string
  created_at: string
}

export const listTraditionalCampaigns = (medium?: string) => {
  const q = medium ? `?medium=${encodeURIComponent(medium)}` : ""
  return fetchMarketing<TraditionalCampaign[]>(`/traditional-campaigns${q}`)
}

// ── Social → Support ticket bridge ───────────────────────────────────

export const createTicketFromSocial = (id: string, data: { subject?: string; priority?: string; assignee_id?: string }) =>
  fetchMarketing<{ ticket_id: string | null; status: string; message: string }>(`/social/inbox/${id}/create-ticket`, {
    method: "POST",
    body: JSON.stringify(data),
  })

// ── Zernio live integration ──────────────────────────────────────────

export interface ZernioStatus {
  configured: boolean
  webhook_secret_set: boolean
  profile_ready?: boolean
  base_url: string
}

export const getZernioStatus = () =>
  fetchMarketing<ZernioStatus>("/social/zernio/status")

export interface MarketingConnector {
  id: string
  label: string
  category: string
  coming_soon?: boolean
  connected: boolean
  accounts: Array<{ id?: string; name?: string; username?: string }>
}

export interface ConnectorsResponse {
  configured: boolean
  profile_ready: boolean
  connectable: boolean
  connectors: MarketingConnector[]
}

export const listConnectors = () =>
  fetchMarketing<ConnectorsResponse>("/social/zernio/connectors")

// ── DB-backed analytics (filled by the sync worker; never calls Zernio live) ──

export interface AnalyticsOverview {
  totalPosts: number
  likes: number
  comments: number
  impressions: number
  reach: number
  shares: number
  clicks: number
  followers?: number
  engagementRate?: number
  bestPost?: string
  lastSync: string | null
  dataStaleness: { pendingCount: number }
  lastError: string | null
}

export interface DailyMetricPoint {
  date: string
  postCount: number
  metrics: {
    impressions: number; reach: number; likes: number; comments: number
    shares: number; saves: number; clicks: number; views: number
  }
}

export interface AnalyticsPostRow {
  postId: string
  platform: string
  publishedAt: string | null
  url: string | null
  syncStatus: string
  lastUpdated: string | null
  analytics: Record<string, number>
}

export interface FollowerPoint {
  date: string
  platform: string | null
  followers: number
  growth: number
}

export const getAnalyticsOverview = () =>
  fetchMarketing<{ overview: AnalyticsOverview }>("/social/analytics/overview")

export const getAnalyticsDaily = (params?: { attribution?: "publish" | "received"; days?: number; platform?: string }) => {
  const q = new URLSearchParams()
  if (params?.attribution) q.set("attribution", params.attribution)
  if (params?.days != null) q.set("days", String(params.days))
  if (params?.platform) q.set("platform", params.platform)
  return fetchMarketing<{ attribution: string; platform: string; dailyData: DailyMetricPoint[] }>(
    `/social/analytics/daily?${q}`,
  )
}

export const getAnalyticsPosts = (params?: { page?: number; limit?: number; platform?: string }) => {
  const q = new URLSearchParams()
  if (params?.page != null) q.set("page", String(params.page))
  if (params?.limit != null) q.set("limit", String(params.limit))
  if (params?.platform) q.set("platform", params.platform)
  return fetchMarketing<{ posts: AnalyticsPostRow[]; pagination: { page: number; limit: number; total: number; pages: number } }>(
    `/social/analytics/posts?${q}`,
  )
}

export const getAnalyticsFollowers = (params?: { granularity?: "daily" | "weekly" | "monthly"; days?: number }) => {
  const q = new URLSearchParams()
  if (params?.granularity) q.set("granularity", params.granularity)
  if (params?.days != null) q.set("days", String(params.days))
  return fetchMarketing<{ granularity: string; series: FollowerPoint[] }>(`/social/analytics/followers?${q}`)
}

export const setTenantProfile = (zernioProfileId: string) =>
  fetchMarketing<{ tenant_id: string; zernio_profile_id: string }>("/social/analytics/profile", {
    method: "PUT",
    body: JSON.stringify({ zernio_profile_id: zernioProfileId }),
  })

// ── Platform: profile-per-tenant, account health, usage, scoped keys ──

export interface AccountHealthEntry {
  accountId: string
  platform: string
  username?: string
  status: string
  canPost?: boolean
  tokenValid?: boolean
  needsReconnect?: boolean
  issues?: string[]
}

export interface AccountHealth {
  summary: { total: number; healthy?: number; warning?: number; error?: number; needsReconnect: number }
  accounts: AccountHealthEntry[]
}

export const ensureTenantProfile = () =>
  fetchMarketing<{ tenant_id: string; zernio_profile_id: string }>("/social/profile/ensure", { method: "POST" })

export const listConnectedAccounts = () =>
  fetchMarketing<{ accounts: Array<Record<string, unknown>> }>("/social/connected-accounts")

export const getAccountsHealth = (status?: "error" | "warning" | "healthy") =>
  fetchMarketing<AccountHealth>(`/social/accounts-health${status ? `?status=${status}` : ""}`)

export const getSocialUsage = () =>
  fetchMarketing<{ profile_id: string | null; usage: Record<string, unknown> | null; restricted: boolean }>("/social/usage")

export const createScopedKey = (body: { name: string; permission?: "read"; disabled_resource_groups?: string[]; expires_in?: number }) =>
  fetchMarketing<Record<string, unknown>>("/social/api-keys", { method: "POST", body: JSON.stringify(body) })

export const offboardProfile = () =>
  fetchMarketing<{ status: string; disconnected_accounts?: number; profile_id?: string }>("/social/profile/offboard", { method: "POST" })

export const listZernioAccounts = (platform?: string) => {
  const q = platform ? `?platform=${encodeURIComponent(platform)}` : ""
  return fetchMarketing<Array<Record<string, unknown>>>(`/social/zernio/accounts${q}`)
}

export const listZernioConversations = (params?: { platform?: string; status?: string; limit?: number; account_id?: string }) => {
  const q = new URLSearchParams()
  if (params?.platform) q.set("platform", params.platform)
  if (params?.status) q.set("status", params.status)
  if (params?.limit != null) q.set("limit", String(params.limit))
  if (params?.account_id) q.set("account_id", params.account_id)
  return fetchMarketing<Record<string, unknown>>(`/social/zernio/conversations?${q}`)
}

// ── SMS Sender IDs & Sending ──────────────────────────────────────────────────

export interface SmsSenderId {
  id: string
  sender_id: string
  status: "active" | "pending" | "rejected"
  type: string
  created_at: string
}

export const listSmsSenderIds = () =>
  fetchMarketing<SmsSenderId[]>("/sms/senders")

export const createSmsSenderId = (sender_id: string) =>
  fetchMarketing<SmsSenderId>("/sms/senders", {
    method: "POST",
    body: JSON.stringify({ sender_id }),
  })

export const deleteSmsSenderId = (sender_id: string) =>
  fetchMarketing<{ status: string; sender_id: string }>(`/sms/senders/${encodeURIComponent(sender_id)}`, {
    method: "DELETE",
  })

export const sendSmsMessage = (data: { sender_id: string; to: string; message: string }) =>
  fetchMarketing<{ status: string; message_id?: string; provider?: string }>("/sms/send", {
    method: "POST",
    body: JSON.stringify(data),
  })

// ── Team & Users Management ───────────────────────────────────────────────────

export interface TeamMember {
  id: string
  name: string
  email: string
  role: "Owner" | "Admin" | "Member" | "Billing Manager" | "Viewer" | string
  access: string
  access_all_profiles: boolean
  profiles?: string[]
  status?: string
  created_at: string
}

export interface TeamMemberInviteRequest {
  emails?: string
  role: string
  access_all_profiles: boolean
  profile_ids?: string[]
}

export interface TeamInviteResult {
  invite_link: string
  token: string
  invited_emails: string[]
  role: string
  access_all_profiles: boolean
}

export const listTeamMembers = () =>
  fetchMarketing<TeamMember[]>("/team/members")

export const inviteTeamMember = (data: TeamMemberInviteRequest) =>
  fetchMarketing<TeamInviteResult>("/team/members/invite", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const deleteTeamMember = (member_id: string) =>
  fetchMarketing<{ status: string; member_id: string }>(`/team/members/${encodeURIComponent(member_id)}`, {
    method: "DELETE",
  })

