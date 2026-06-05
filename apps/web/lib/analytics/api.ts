"use client"

/**
 * Analytics data fetching helpers.
 * Pulls from the web_analytics service through the Next.js API proxy.
 */

const ANALYTICS_API = "/api/analytics/service"

async function fetchAnalytics<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${ANALYTICS_API}${path}`, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  }
  const res = await fetch(url.toString(), { cache: "no-store" })
  if (!res.ok) throw new Error(`Analytics API error: ${res.status}`)
  return res.json()
}

export interface OverviewData {
  total_pageviews: number
  unique_visitors: number
  unique_sessions: number
  avg_session_duration: number
  bounce_rate: number
}

export interface TrafficPoint {
  date: string
  pageviews: number
  unique_visitors: number
  sessions: number
}

export interface PageStat {
  path: string
  title: string
  pageviews: number
  unique_visitors: number
  avg_time_on_page: number
}

export interface DeviceData {
  devices: { device: string; count: number }[]
  browsers: { browser: string; count: number }[]
  os: { os: string; count: number }[]
  screens: { resolution: string; count: number }[]
}

export interface LocationData {
  countries: { country_code: string; country: string; pageviews: number; unique_visitors: number }[]
  cities: { city: string; region: string | null; country: string | null; pageviews: number }[]
}

export interface FormStat {
  form_id: string | null
  form_name: string
  path: string
  views: number
  starts: number
  submits: number
  abandons: number
  errors: number
  avg_time_to_complete: number
  conversion_rate: number
}

export interface FormsData {
  forms: FormStat[]
}

export interface ReferrerData {
  referrer: string
  sessions: number
}

export interface UTMData {
  source: string
  medium: string | null
  campaign: string | null
  sessions: number
}

export interface RealtimeData {
  active_visitors: number
  pageviews_last_5min: number
  top_pages: { path: string; visitors: number }[]
}

export interface ClickPoint {
  date: string
  clicks: number
  sessions_with_clicks: number
}

export interface PageLoadPoint {
  date: string
  pageviews: number
  avg_load_seconds: number
  median_load_seconds: number
}

export const analyticsApi = {
  getOverview: (days = 30) => fetchAnalytics<OverviewData>("/overview", { days: String(days) }),
  getTraffic: (days = 30) => fetchAnalytics<TrafficPoint[]>("/traffic", { days: String(days) }),
  getPages: (days = 30, limit = 20) => fetchAnalytics<PageStat[]>("/pages", { days: String(days), limit: String(limit) }),
  getDevices: (days = 30) => fetchAnalytics<DeviceData>("/devices", { days: String(days) }),
  getLocations: (days = 30, limit = 50) => fetchAnalytics<LocationData>("/locations", { days: String(days), limit: String(limit) }),
  getForms: (days = 30) => fetchAnalytics<FormsData>("/forms", { days: String(days) }),
  getReferrers: (days = 30, limit = 20) => fetchAnalytics<ReferrerData[]>("/referrers", { days: String(days), limit: String(limit) }),
  getUTM: (days = 30) => fetchAnalytics<UTMData[]>("/utm", { days: String(days) }),
  getRealtime: () => fetchAnalytics<RealtimeData>("/realtime"),
  getClicks: (days = 30) => fetchAnalytics<ClickPoint[]>("/clicks", { days: String(days) }),
  getPageLoad: (days = 30) => fetchAnalytics<PageLoadPoint[]>("/page-load", { days: String(days) }),
}
