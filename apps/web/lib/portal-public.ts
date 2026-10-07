import "server-only"
import { cache } from "react"
import { headers } from "next/headers"
import { notFound } from "next/navigation"
import type { PortalPageContent } from "./portal-api"

export interface PublicPortalPage {
  id: string
  slug: string
  title: string
  description: string | null
  content: PortalPageContent
  theme: Record<string, unknown> | null
  seo_meta: Record<string, unknown> | null
  custom_css: string | null
  preview: boolean
  expires_at?: string
}

// Request-scoped caching prevents metadata + rendering from counting two views.
export const loadPublicPortalPage = cache(async (kind: "public" | "shared", key: string, query = ""): Promise<PublicPortalPage> => {
  if (!(kind === "public" ? /^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$/ : /^[A-Za-z0-9_-]{16,200}$/).test(key)) notFound()
  const incoming = await headers()
  const outgoing = new Headers()
  const ip = incoming.get("x-forwarded-for")?.split(",").at(-1)?.trim()
  if (ip) outgoing.set("x-forwarded-for", ip)
  // Shared preview tokens never leave this route as a referrer.
  if (kind === "public") {
    const referrer = incoming.get("referer")
    if (referrer) { try { outgoing.set("referer", new URL(referrer).origin) } catch {} }
  }
  const service = process.env.PORTAL_BUILDER_SERVICE_URL || "http://portal-builder:8026"
  const response = await fetch(`${service}/api/v1/portal/${kind}/${encodeURIComponent(key)}${query ? `?${query}` : ""}`, {
    headers: outgoing, cache: "no-store", signal: AbortSignal.timeout(20_000),
  })
  if (response.status === 404) notFound()
  if (!response.ok) throw new Error("The portal page is temporarily unavailable.")
  return response.json()
})

export function portalTrackingQuery(search: Record<string, string | string[] | undefined>) {
  const query = new URLSearchParams()
  for (const key of ["utm_source", "utm_medium", "utm_campaign"]) {
    const value = search[key]
    if (typeof value === "string") query.set(key, value.slice(0, key === "utm_campaign" ? 200 : 100))
  }
  return query.toString()
}
