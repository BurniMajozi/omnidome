"use client"

import { getSessionSafe } from "@/lib/supabase/client"

/**
 * FNO Intelligence API client — passed-home imports and geo segments
 * (SPEC-geo-segments.md). Reaches services/fno_intelligence through the
 * /svc/fno-intelligence rewrite in next.config.mjs.
 */

const API_BASE = "/svc/fno-intelligence/api/fno"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const FALLBACK_USER_ID = "00000000-0000-0000-0000-000000000001"

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await getSessionSafe()
  const tenantId =
    data.session?.user?.user_metadata?.tenant_id ??
    data.session?.user?.app_metadata?.tenant_id ??
    FALLBACK_TENANT_ID
  const userId = data.session?.user?.id ?? FALLBACK_USER_ID
  return { "x-tenant-id": tenantId, "x-user-id": userId }
}

export class FnoApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function fetchFno<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    ...init,
    signal: init?.signal
      ? AbortSignal.any([init.signal, AbortSignal.timeout(15000)])
      : AbortSignal.timeout(15000),
    headers: { ...(await getAuthHeaders()), "Content-Type": "application/json", ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = typeof body?.detail === "string" ? body.detail : `Request failed (${res.status})`
    throw new FnoApiError(res.status, detail)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

// ── Types ─────────────────────────────────────────────────────────────

export type DwellingType = "unknown" | "sdu" | "mdu_unit" | "complex" | "business" | "estate"

export const DWELLING_LABELS: Record<DwellingType, string> = {
  sdu: "Freestanding house",
  mdu_unit: "Flat / apartment unit",
  complex: "Complex / townhouse",
  estate: "Estate",
  business: "Business",
  unknown: "Unknown",
}

export interface GeoSegmentFilters {
  fno_names: string[]
  import_ids: string[]
  cities: string[]
  suburbs: string[]
  postal_codes: string[]
  dwelling_types: DwellingType[]
  date_passed_from: string | null
  date_passed_to: string | null
  geocoded_only: boolean
}

export const EMPTY_FILTERS: GeoSegmentFilters = {
  fno_names: [],
  import_ids: [],
  cities: [],
  suburbs: [],
  postal_codes: [],
  dwelling_types: [],
  date_passed_from: null,
  date_passed_to: null,
  geocoded_only: true,
}

export interface GeoArea {
  suburb: string | null
  city: string | null
  postal_code: string | null
  homes: number
  centroid_lat: number | null
  centroid_lng: number | null
  suggested_radius_km: number
}

export interface ExclusionCounts {
  suppressed_customer: number
  duplicate: number
  invalid: number
  raw: number
  not_geocoded: number
}

export interface GeoSegmentPreview {
  home_count: number
  excluded: ExclusionCounts
  areas: GeoArea[]
}

export interface GeoSegmentFilterOptions {
  fno_names: string[]
  cities: string[]
  suburbs: { suburb: string; city: string | null; homes: number }[]
  postal_codes: string[]
  dwelling_types: DwellingType[]
  imports: { id: string; file_name: string; fno_name: string; created_at: string | null }[]
}

export interface PassedHomeImport {
  id: string
  fno_name: string
  file_name: string
  status: string
  total_rows: number
  inserted_rows: number
  duplicate_rows: number
  invalid_rows: number
  suppressed_rows: number
  created_at: string
}

// ── API ───────────────────────────────────────────────────────────────

export const fnoApi = {
  listPassedHomeImports: () => fetchFno<PassedHomeImport[]>("/passed-home-imports?limit=20"),

  getGeoSegmentFilterOptions: () => fetchFno<GeoSegmentFilterOptions>("/geo-segments/filter-options"),

  previewGeoSegment: (filters: GeoSegmentFilters, signal?: AbortSignal) =>
    fetchFno<GeoSegmentPreview>("/geo-segments/preview", {
      method: "POST",
      body: JSON.stringify(filters),
      signal,
    }),
}
