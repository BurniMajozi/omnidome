"use client"

/**
 * Builds Marketing audiences from Sales lead sources (SPEC-marketing-audiences.md).
 * Shared by Sales ("Add to audience") and Marketing ("New Audience") so both
 * create exactly the same record for the same source.
 */

import { fnoApi, opportunityApi, type OppCompany } from "@/lib/fno-api"
import {
  createAudienceSegment,
  type AudienceBusiness,
  type AudiencePlatform,
  type AudienceSegment,
} from "@/lib/marketing-api"

function unwrap<T>(result: { ok: boolean; data: T | null; error: string | null }): T {
  if (!result.ok || result.data === null) throw new Error(result.error ?? "Marketing didn't accept the audience")
  return result.data
}

/** Homes audience from a saved geo segment: target areas only, never addresses. */
export async function pushGeoSegmentAudience(segmentId: string, platform: AudiencePlatform, name?: string, description?: string) {
  const segment = await fnoApi.getGeoSegment(segmentId)
  const areas = segment.areas ?? []
  return unwrap<AudienceSegment>(await createAudienceSegment({
    name: name?.trim() || segment.name,
    description: description?.trim() || `FNO homes passed: ${segment.home_count} homes in ${areas.length} areas`,
    member_count: segment.home_count,
    rules: {
      type: "homes",
      platform,
      source: "fno_geo_segment",
      source_id: segment.id,
      source_name: segment.name,
      areas,
    },
  }))
}

export function businessFromCompany(c: OppCompany): AudienceBusiness {
  return {
    name: c.name,
    category: c.category_label,
    address: [c.address_line, c.suburb, c.city].filter(Boolean).join(", ") || null,
    phone: c.phone,
    email: c.email,
    website: c.website,
    lat: c.lat,
    lng: c.lng,
  }
}

/** Business audience from a company search: every business not dismissed. */
export async function pushCompanySearchAudience(searchId: string, platform: AudiencePlatform, name?: string, description?: string) {
  const search = await opportunityApi.getCompanySearch(searchId)
  const businesses = search.companies.filter((c) => c.status !== "dismissed").map(businessFromCompany)
  const defaultName = `${search.category_label} near ${search.area_query}`
  return unwrap<AudienceSegment>(await createAudienceSegment({
    name: name?.trim() || defaultName,
    description: description?.trim() || `${businesses.length} businesses within ${search.radius_km} km of ${search.area_query} (OpenStreetMap)`,
    member_count: businesses.length,
    rules: {
      type: "businesses",
      platform,
      source: "company_search",
      source_id: search.id,
      source_name: defaultName,
      businesses,
    },
  }))
}

function csvCell(value: unknown) {
  const s = value === null || value === undefined ? "" : String(value)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/** CSV of an audience's areas (homes) or businesses, for upload to an ad platform. */
export function audienceCsv(audience: AudienceSegment): string {
  if (audience.rules.type === "businesses") {
    const cols = ["name", "category", "address", "phone", "email", "website", "lat", "lng"] as const
    const rows = (audience.rules.businesses ?? []).map((b) => cols.map((c) => csvCell(b[c])).join(","))
    return [cols.join(","), ...rows].join("\n") + "\n"
  }
  if (audience.rules.type === "homes") {
    const cols = ["suburb", "city", "postal_code", "homes", "centroid_lat", "centroid_lng", "suggested_radius_km"] as const
    const rows = (audience.rules.areas ?? []).map((a) => cols.map((c) => csvCell(a[c])).join(","))
    return [cols.join(","), ...rows].join("\n") + "\n"
  }
  const rows = (audience.rules.regions ?? []).map((r) => csvCell(r))
  return ["region", ...rows].join("\n") + "\n"
}

export function downloadAudienceCsv(audience: AudienceSegment) {
  const slug = audience.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "audience"
  const url = URL.createObjectURL(new Blob([audienceCsv(audience)], { type: "text/csv" }))
  const link = document.createElement("a")
  link.href = url
  link.download = `${slug}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
