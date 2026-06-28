"use client"

import { supabase } from "@/lib/supabase/client"

/**
 * Marketing API client — campaigns, social media, WhatsApp, ads,
 * comment automations, email, and analytics.
 * Proxies through the Next.js API routes to the marketing service.
 */

const API_BASE = "/svc/marketing"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"

async function getTenantId(): Promise<string> {
  const { data } = await supabase.auth.getSession()
  return (
    data.session?.user?.user_metadata?.tenant_id ??
    data.session?.user?.app_metadata?.tenant_id ??
    FALLBACK_TENANT_ID
  )
}

async function fetchMarketing<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers: { "x-tenant-id": await getTenantId(), "Content-Type": "application/json" },
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
  total: number
  by_platform: Record<string, number>
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
    method: "PUT",
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
  return fetchMarketing<SocialAccount[]>(`/social-accounts?${q}`)
}

export const createSocialAccount = (data: SocialAccountCreate) =>
  fetchMarketing<SocialAccount>("/social-accounts", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const getSocialAccount = (id: string) =>
  fetchMarketing<SocialAccount>(`/social-accounts/${id}`)

export const updateSocialAccount = (id: string, data: Partial<SocialAccount>) =>
  fetchMarketing<SocialAccount>(`/social-accounts/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const deleteSocialAccount = (id: string) =>
  fetchMarketing<{ status: string }>(`/social-accounts/${id}`, {
    method: "DELETE",
  })

export const connectSocialAccount = (platform: string) =>
  fetchMarketing<{ oauth_url: string }>(`/social-accounts/connect?platform=${encodeURIComponent(platform)}`)

export const disconnectSocialAccount = (id: string) =>
  fetchMarketing<{ status: string }>(`/social-accounts/${id}/disconnect`, {
    method: "POST",
  })

// ── Social Posts ─────────────────────────────────────────────────────

export const listSocialPosts = (params?: { status?: string; account_id?: string; campaign_id?: string }) => {
  const q = new URLSearchParams()
  if (params?.status) q.set("status", params.status)
  if (params?.account_id) q.set("account_id", params.account_id)
  if (params?.campaign_id) q.set("campaign_id", params.campaign_id)
  return fetchMarketing<SocialPost[]>(`/social-posts?${q}`)
}

export const createSocialPost = (data: SocialPostCreate) =>
  fetchMarketing<SocialPost>("/social-posts", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const updateSocialPost = (id: string, data: Partial<SocialPost>) =>
  fetchMarketing<SocialPost>(`/social-posts/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const deleteSocialPost = (id: string) =>
  fetchMarketing<{ status: string }>(`/social-posts/${id}`, {
    method: "DELETE",
  })

export const publishSocialPost = (id: string) =>
  fetchMarketing<{ status: string; published_at: string }>(`/social-posts/${id}/publish`, {
    method: "POST",
  })

export const crossPost = (data: CrossPostInput) =>
  fetchMarketing<{ status: string; posted_to: string[] }>("/social-posts/cross-post", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const getSocialPostAnalytics = (id: string) =>
  fetchMarketing<Record<string, unknown>>(`/social-posts/${id}/analytics`)

// ── Social Inbox ─────────────────────────────────────────────────────

export const listInboxMessages = (params?: { status?: string; platform?: string; message_type?: string; account_id?: string }) => {
  const q = new URLSearchParams()
  if (params?.status) q.set("status", params.status)
  if (params?.platform) q.set("platform", params.platform)
  if (params?.message_type) q.set("message_type", params.message_type)
  if (params?.account_id) q.set("account_id", params.account_id)
  return fetchMarketing<InboxMessage[]>(`/social-inbox?${q}`)
}

export const getInboxMessage = (id: string) =>
  fetchMarketing<InboxMessage>(`/social-inbox/${id}`)

export const replyToInboxMessage = (id: string, content: string) =>
  fetchMarketing<{ status: string }>(`/social-inbox/${id}/reply`, {
    method: "POST",
    body: JSON.stringify({ content }),
  })

export const archiveInboxMessage = (id: string) =>
  fetchMarketing<{ status: string }>(`/social-inbox/${id}/archive`, {
    method: "POST",
  })

export const markInboxRead = (id: string) =>
  fetchMarketing<{ status: string }>(`/social-inbox/${id}/read`, {
    method: "PUT",
  })

export const getInboxUnreadCount = () =>
  fetchMarketing<InboxUnreadCount>("/social-inbox/unread-count")

// ── Social Analytics ─────────────────────────────────────────────────

export const getAccountAnalytics = (account_id: string, from_date?: string, to_date?: string) => {
  const q = new URLSearchParams()
  q.set("account_id", account_id)
  if (from_date) q.set("from_date", from_date)
  if (to_date) q.set("to_date", to_date)
  return fetchMarketing<AccountAnalytics>(`/analytics/accounts?${q}`)
}

export const getPlatformAnalytics = (platform: string, from_date?: string, to_date?: string) => {
  const q = new URLSearchParams()
  q.set("platform", platform)
  if (from_date) q.set("from_date", from_date)
  if (to_date) q.set("to_date", to_date)
  return fetchMarketing<PlatformAnalytics>(`/analytics/platforms?${q}`)
}

export const getBestTimeToPost = (account_id: string) =>
  fetchMarketing<BestTimeToPost>(`/analytics/best-time?account_id=${encodeURIComponent(account_id)}`)

export const getEngagementSummary = (params?: { from_date?: string; to_date?: string }) => {
  const q = new URLSearchParams()
  if (params?.from_date) q.set("from_date", params.from_date)
  if (params?.to_date) q.set("to_date", params.to_date)
  return fetchMarketing<EngagementSummary>(`/analytics/engagement-summary?${q}`)
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
  fetchMarketing<{ imported: number; contacts: WhatsAppContact[] }>("/whatsapp/contacts/bulk", {
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

// ── Ad Campaigns ─────────────────────────────────────────────────────

export const listAdCampaigns = (params?: { platform?: string; status?: string }) => {
  const q = new URLSearchParams()
  if (params?.platform) q.set("platform", params.platform)
  if (params?.status) q.set("status", params.status)
  return fetchMarketing<AdCampaign[]>(`/ad-campaigns?${q}`)
}

export const createAdCampaign = (data: AdCampaignCreate) =>
  fetchMarketing<AdCampaign>("/ad-campaigns", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const updateAdCampaign = (id: string, data: Partial<AdCampaign>) =>
  fetchMarketing<AdCampaign>(`/ad-campaigns/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const deleteAdCampaign = (id: string) =>
  fetchMarketing<{ status: string }>(`/ad-campaigns/${id}`, {
    method: "DELETE",
  })

export const getAdCampaignAnalytics = (id: string) =>
  fetchMarketing<AdCampaignAnalytics>(`/ad-campaigns/${id}/analytics`)

// ── Comment Automations ──────────────────────────────────────────────

export const listCommentAutomations = (params?: { account_id?: string; is_active?: boolean }) => {
  const q = new URLSearchParams()
  if (params?.account_id) q.set("account_id", params.account_id)
  if (params?.is_active != null) q.set("is_active", String(params.is_active))
  return fetchMarketing<CommentAutomation[]>(`/comment-automations?${q}`)
}

export const createCommentAutomation = (data: CommentAutomationCreate) =>
  fetchMarketing<CommentAutomation>("/comment-automations", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const updateCommentAutomation = (id: string, data: Partial<CommentAutomation>) =>
  fetchMarketing<CommentAutomation>(`/comment-automations/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const deleteCommentAutomation = (id: string) =>
  fetchMarketing<{ status: string }>(`/comment-automations/${id}`, {
    method: "DELETE",
  })

// ── Email ────────────────────────────────────────────────────────────

export const sendEmailBatch = (data: EmailBatchSendInput) =>
  fetchMarketing<{ status: string; sent: number }>("/email/send-batch", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const listEmailTemplates = () =>
  fetchMarketing<EmailTemplate[]>("/email/templates")

export const createEmailTemplate = (data: EmailTemplateCreate) =>
  fetchMarketing<EmailTemplate>("/email/templates", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const listAudienceSegments = () =>
  fetchMarketing<AudienceSegment[]>("/email/segments")

export const createAudienceSegment = (data: AudienceSegmentCreate) =>
  fetchMarketing<AudienceSegment>("/email/segments", {
    method: "POST",
    body: JSON.stringify(data),
  })
