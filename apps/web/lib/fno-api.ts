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

async function fetchFno<T>(path: string, init?: RequestInit, timeoutMs = 15000): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    ...init,
    signal: init?.signal
      ? AbortSignal.any([init.signal, AbortSignal.timeout(timeoutMs)])
      : AbortSignal.timeout(timeoutMs),
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

export interface PassedHomeImportDetail extends PassedHomeImport {
  fno_portal: string
  file_size_bytes: number
  column_map: Record<string, string> | null
  error_message: string | null
  processed_at: string | null
}

export interface GeocodeStatus {
  pending: number
  geocoded: number
  failed: number
}

export interface PassedHomeRow {
  id: string
  import_id: string
  address_raw: string | null
  address_line1: string | null
  suburb: string | null
  city: string | null
  status: string
  reject_reason: string | null
}

/** Mirrors _VALID_FNO_PORTALS in services/fno_intelligence/routes.py. */
export const FNO_PORTALS: { portal: string; name: string; label: string }[] = [
  { portal: "vumatel_active", name: "vumatel", label: "Vumatel (active)" },
  { portal: "vumatel_passive", name: "vumatel", label: "Vumatel (passive)" },
  { portal: "openserve", name: "openserve", label: "Openserve" },
  { portal: "frogfoot", name: "frogfoot", label: "Frogfoot" },
  { portal: "octotel", name: "octotel", label: "Octotel" },
  { portal: "metrofibre", name: "metrofibre", label: "MetroFibre" },
  { portal: "liquid", name: "liquid", label: "Liquid" },
  { portal: "other", name: "", label: "Other FNO" },
]

/** Mirrors the upload limits in routes.py (_PASSED_HOME_MAX_BYTES / _EXTENSIONS). */
export const PASSED_HOME_UPLOAD = {
  maxBytes: 25 * 1024 * 1024,
  extensions: ["csv", "xlsx", "xls"],
}

/** Header names the importer recognises (HEADER_SYNONYMS in passed_homes.py). */
export const PASSED_HOME_COLUMNS: { field: string; label: string; required: boolean; accepts: string }[] = [
  { field: "address", label: "Address", required: true, accepts: "Address, Street Address, Site Address, Stand Address" },
  { field: "suburb", label: "Suburb", required: false, accepts: "Suburb, Area, Township" },
  { field: "city", label: "City", required: false, accepts: "City, Town, Municipality" },
  { field: "postal_code", label: "Postcode", required: false, accepts: "Postal Code, Postcode, Zip" },
  { field: "date_passed", label: "Date passed", required: false, accepts: "Date Passed, Live Date, RFS Date" },
  { field: "unit_count", label: "Units", required: false, accepts: "Units, Unit Count" },
]

export const REJECT_REASON_LABELS: Record<string, string> = {
  missing_address: "No address in this row",
  duplicate_in_db: "Already imported before",
}

export interface GeoSegment {
  id: string
  name: string
  filters: GeoSegmentFilters
  home_count: number
  area_count: number
  excluded: ExclusionCounts
  created_at: string | null
  refreshed_at: string | null
  areas?: GeoArea[]
}

// ── API ───────────────────────────────────────────────────────────────

export const fnoApi = {
  listPassedHomeImports: () => fetchFno<PassedHomeImport[]>("/passed-home-imports?limit=20"),

  getPassedHomeImport: (id: string) => fetchFno<PassedHomeImportDetail>(`/passed-home-imports/${id}`),

  /** Same endpoint the API integration uses; multipart, so no JSON content type. */
  uploadPassedHomes: async (fnoName: string, fnoPortal: string, file: File) => {
    const form = new FormData()
    form.append("fno_name", fnoName)
    form.append("fno_portal", fnoPortal)
    form.append("file", file)
    const res = await fetch(`${API_BASE}/passed-home-imports`, {
      method: "POST",
      cache: "no-store",
      signal: AbortSignal.timeout(120000),
      headers: await getAuthHeaders(),
      body: form,
    })
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      const detail = typeof body?.detail === "string" ? body.detail : `Upload failed (${res.status})`
      throw new FnoApiError(res.status, detail)
    }
    return (await res.json()) as PassedHomeImport
  },

  triggerGeocode: (importId: string) =>
    fetchFno<{ queued: number; status: string }>(`/passed-homes/geocode?import_id=${importId}`, { method: "POST" }),

  getGeocodeStatus: (importId: string) =>
    fetchFno<GeocodeStatus>(`/passed-homes/geocode-status?import_id=${importId}`),

  listImportIssues: (importId: string) =>
    fetchFno<PassedHomeRow[]>(`/passed-homes?import_id=${importId}&status=invalid&limit=200`),

  getGeoSegmentFilterOptions: () => fetchFno<GeoSegmentFilterOptions>("/geo-segments/filter-options"),

  previewGeoSegment: (filters: GeoSegmentFilters, signal?: AbortSignal) =>
    fetchFno<GeoSegmentPreview>("/geo-segments/preview", {
      method: "POST",
      body: JSON.stringify(filters),
      signal,
    }),

  listGeoSegments: () => fetchFno<GeoSegment[]>("/geo-segments"),

  getGeoSegment: (id: string) => fetchFno<GeoSegment>(`/geo-segments/${id}`),

  createGeoSegment: (name: string, filters: GeoSegmentFilters) =>
    fetchFno<GeoSegment>("/geo-segments", {
      method: "POST",
      body: JSON.stringify({ name, filters }),
    }),

  deleteGeoSegment: (id: string) => fetchFno<void>(`/geo-segments/${id}`, { method: "DELETE" }),

  refreshGeoSegment: (id: string) => fetchFno<GeoSegment>(`/geo-segments/${id}/refresh`, { method: "POST" }),

  /** Fetches the export with auth headers and saves it; a plain <a href> can't send them. */
  downloadGeoSegmentExport: async (id: string, format: "csv" | "kml") => {
    const res = await fetch(`${API_BASE}/geo-segments/${id}/export?format=${format}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
      headers: await getAuthHeaders(),
    })
    if (!res.ok) throw new FnoApiError(res.status, `Export failed (${res.status})`)
    const disposition = res.headers.get("content-disposition") ?? ""
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `segment-areas.${format}`
    const url = URL.createObjectURL(await res.blob())
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  },
}

// ── Opportunity finder (SPEC-opportunity-finder.md) ──────────────────────

export interface CompanyCategory {
  id: string
  label: string
}

export type CompanySearchStatus = "queued" | "running" | "done" | "failed"

export interface CompanySearch {
  id: string
  area_query: string
  area_label: string | null
  category: string
  category_label: string
  radius_km: number
  center_lat: number
  center_lng: number
  status: CompanySearchStatus
  error_message: string | null
  result_count: number
  created_at: string | null
  finished_at: string | null
}

export type CompanyStatus = "new" | "lead_created" | "dismissed"

export interface OppCompany {
  id: string
  search_id: string
  name: string
  category_label: string | null
  address_line: string | null
  suburb: string | null
  city: string | null
  postal_code: string | null
  phone: string | null
  email: string | null
  website: string | null
  lat: number
  lng: number
  distance_km: number
  status: CompanyStatus
  sales_lead_id: string | null
  enriched_at: string | null
  updated_fields?: string[]
}

export interface TenderSource {
  id: string
  url: string
  label: string | null
  active: boolean
  scan_interval_hours: 12 | 24 | 168
  last_scanned_at: string | null
  next_scan_at: string | null
  last_status: "queued" | "scanning" | "ok" | "failed"
  last_error: string | null
  last_tender_count: number
  tender_count: number
  latest_snapshot_id: string | null
  created_at: string | null
}

export type TenderStatus = "new" | "reviewing" | "bidding" | "skipped"

export interface Tender {
  id: string
  source_id: string
  source_label: string | null
  snapshot_id: string | null
  title: string
  reference: string | null
  issuer: string | null
  description: string | null
  closing_at: string | null
  closing_text: string | null
  briefing_at: string | null
  briefing_text: string | null
  briefing_location: string | null
  required_documents: string[]
  document_links: { label: string | null; url: string }[]
  detail_url: string | null
  contact: string | null
  status: TenderStatus
  sales_lead_id: string | null
  first_seen_at: string | null
  last_seen_at: string | null
}

const OPP = "/opportunities"

export const opportunityApi = {
  listCategories: () => fetchFno<CompanyCategory[]>(`${OPP}/company-categories`),
  createCompanySearch: (area: string, category: string, radius_km: number) =>
    fetchFno<CompanySearch>(`${OPP}/company-searches`, {
      method: "POST",
      body: JSON.stringify({ area, category, radius_km }),
    }),
  listCompanySearches: () => fetchFno<CompanySearch[]>(`${OPP}/company-searches`),
  getCompanySearch: (id: string) => fetchFno<CompanySearch & { companies: OppCompany[] }>(`${OPP}/company-searches/${id}`),
  enrichCompany: (id: string) =>
    fetchFno<OppCompany>(`${OPP}/companies/${id}/enrich`, { method: "POST" }, 120000),
  patchCompany: (id: string, data: { status?: CompanyStatus; sales_lead_id?: string }) =>
    fetchFno<OppCompany>(`${OPP}/companies/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  listSources: () => fetchFno<TenderSource[]>(`${OPP}/sources`),
  createSource: (url: string, label: string | null, scan_interval_hours: number) =>
    fetchFno<TenderSource>(`${OPP}/sources`, {
      method: "POST",
      body: JSON.stringify({ url, label, scan_interval_hours }),
    }),
  patchSource: (id: string, data: { label?: string; active?: boolean; scan_interval_hours?: number }) =>
    fetchFno<TenderSource>(`${OPP}/sources/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteSource: (id: string) => fetchFno<void>(`${OPP}/sources/${id}`, { method: "DELETE" }),
  scanSource: (id: string) => fetchFno<TenderSource>(`${OPP}/sources/${id}/scan`, { method: "POST" }),
  listTenders: (params: { status?: TenderStatus; source_id?: string; include_closed?: boolean }) => {
    const q = new URLSearchParams()
    if (params.status) q.set("status", params.status)
    if (params.source_id) q.set("source_id", params.source_id)
    if (params.include_closed) q.set("include_closed", "true")
    return fetchFno<Tender[]>(`${OPP}/tenders?${q}`)
  },
  patchTender: (id: string, data: { status?: TenderStatus; sales_lead_id?: string }) =>
    fetchFno<Tender>(`${OPP}/tenders/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  /** Screenshot evidence as an object URL (the endpoint needs auth headers). */
  screenshotUrl: async (snapshotId: string) => {
    const res = await fetch(`${API_BASE}${OPP}/snapshots/${snapshotId}/screenshot`, {
      cache: "no-store",
      signal: AbortSignal.timeout(30000),
      headers: await getAuthHeaders(),
    })
    if (!res.ok) throw new FnoApiError(res.status, "Screenshot not available")
    return URL.createObjectURL(await res.blob())
  },
}
