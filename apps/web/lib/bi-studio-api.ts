"use client"

import { getSessionSafe } from "@/lib/supabase/client"
import { AnalyticsApiError } from "@/lib/analytics-ai-api"

/**
 * Deck Studio / BI client. Contract: docs/bi-studio-api.md.
 * Reaches services/fno_intelligence /api/fno/bi through the /svc/fno-intelligence rewrite.
 */

const API_BASE = "/svc/fno-intelligence/api/fno/bi"
const FALLBACK_ID = "00000000-0000-0000-0000-000000000001"

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await getSessionSafe()
  const tenantId =
    data.session?.user?.user_metadata?.tenant_id ?? data.session?.user?.app_metadata?.tenant_id ?? FALLBACK_ID
  const userId = data.session?.user?.id ?? FALLBACK_ID
  return { "x-tenant-id": tenantId, "x-user-id": userId }
}

export class BiApiError extends AnalyticsApiError {
  /** Present on 409 version conflicts. */
  currentVersion: number | null
  constructor(status: number, message: string, currentVersion: number | null = null) {
    super(status, message)
    this.currentVersion = currentVersion
  }
  get conflict() {
    return this.status === 409
  }
  get missingPrecondition() {
    return this.status === 428
  }
}

function parseDetail(body: unknown, status: number): { message: string; currentVersion: number | null } {
  const d = (body as { detail?: unknown } | null)?.detail
  if (typeof d === "string") return { message: d, currentVersion: null }
  if (Array.isArray(d)) {
    const parts = d.map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: unknown }).msg) : "")).filter(Boolean)
    if (parts.length) return { message: parts.join("; "), currentVersion: null }
  }
  if (d && typeof d === "object") {
    const o = d as { message?: unknown; current_version?: unknown }
    return {
      message: typeof o.message === "string" ? o.message : `Request failed (${status})`,
      currentVersion: typeof o.current_version === "number" ? o.current_version : null,
    }
  }
  return { message: `Request failed (${status})`, currentVersion: null }
}

async function raw(path: string, init?: RequestInit, timeoutMs = 25000): Promise<Response> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      ...init,
      signal: init?.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(timeoutMs)]) : AbortSignal.timeout(timeoutMs),
      headers: { ...(await getAuthHeaders()), ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    })
  } catch {
    throw new BiApiError(0, "The BI service is not reachable.")
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const { message, currentVersion } = parseDetail(body, res.status)
    throw new BiApiError(res.status, message, currentVersion)
  }
  return res
}

async function call<T>(path: string, init?: RequestInit, timeoutMs?: number): Promise<T> {
  const res = await raw(path, init, timeoutMs)
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

const post = <T>(path: string, body?: unknown, headers?: Record<string, string>, timeoutMs?: number) =>
  call<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body), headers }, timeoutMs)

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") u.set(k, String(v))
  const s = u.toString()
  return s ? `?${s}` : ""
}

// ── Semantic layer ───────────────────────────────────────────────────
export type Grain = "day" | "week" | "month" | "quarter" | "year"
export type MeasureFormat = "currency_zar" | "number" | "percent" | "duration"

export interface DimensionDef {
  id: string
  label: string
  type: "time" | "category" | "number"
  grains?: Grain[]
  filter_ops?: string[]
  cardinality?: "low" | "medium" | "high"
}
export interface MeasureDef {
  id: string
  label: string
  agg?: string
  format: MeasureFormat
  unit?: string | null
  additive?: boolean
  description?: string
}
export interface DatasetDef {
  id: string
  label: string
  description?: string
  category?: string
  source_tables?: string[]
  default_time_dimension?: string | null
  dimensions: DimensionDef[]
  measures: MeasureDef[]
}
export interface DatasetCatalog {
  datasets: DatasetDef[]
  skipped?: { id: string; reason: string }[]
  grains?: Grain[]
  filter_ops?: string[]
  limits?: Record<string, number>
}

export interface QueryFilter {
  field: string
  op: string
  value?: unknown
}
export interface QuerySpec {
  dataset: string
  measures: string[]
  dimensions?: string[]
  filters?: QueryFilter[]
  time?: { dimension?: string; grain?: Grain; from?: string | null; to?: string | null } | null
  order_by?: { field: string; dir: "asc" | "desc" }[]
  limit?: number
}
export interface QueryColumn {
  id: string
  label: string
  kind: "time" | "dimension" | "measure"
  type: string
  grain?: Grain
  format?: MeasureFormat
  agg?: string
  additive?: boolean
}
export interface QueryResult {
  columns: QueryColumn[]
  rows: (string | number | null)[][]
  totals: Record<string, number | null>
  meta: { dataset: string; generated_at: string; row_count: number; truncated: boolean; timezone?: string; query_key?: string }
}

export type ChartType =
  | "column"
  | "bar"
  | "line"
  | "area"
  | "pie"
  | "donut"
  | "stacked_column"
  | "combo"
  | "scatter"
  | "waterfall"
export type SuggestedType = ChartType | "kpi" | "table"

export interface ChartSuggestion {
  type: SuggestedType
  score: number
  reason: string
  series_mapping?: { x?: string | null; y?: string[]; series?: string | null }
}

export const getDatasets = () => call<DatasetCatalog>("/datasets")
export const runQuery = (spec: QuerySpec, signal?: AbortSignal) =>
  call<QueryResult>("/query", { method: "POST", body: JSON.stringify(spec), signal })
export const suggestCharts = (b: {
  dataset: string
  measures: string[]
  dimensions: string[]
  time?: { dimension?: string; grain: Grain } | null
  row_count?: number
}) => post<{ dataset: string; recommended: SuggestedType; suggestions: ChartSuggestion[] }>("/chart-suggestions", b)

// ── Brand kits ───────────────────────────────────────────────────────
export interface BrandPalette {
  primary: string
  secondary: string
  accent: string
  background: string
  text: string
  chart: string[]
}
export interface BrandKit {
  id: string
  name: string
  company_name: string
  tagline: string
  palette: BrandPalette
  fonts: { heading: string; body: string }
  voice: { formality: string; jargon_level: string; banned_words: string[]; notes: string }
  footer_text: string
  slide_numbers: boolean
  layout_prefs: { default_layout: string; title_align: string; density: string; show_logo: boolean; logo_position: string }
  has_logo?: boolean
  logo_data_url?: string | null
  is_default?: boolean
  updated_at?: string
}
export type BrandKitInput = Partial<Omit<BrandKit, "id" | "has_logo" | "is_default" | "updated_at" | "palette" | "fonts" | "voice" | "layout_prefs">> & {
  palette?: Partial<BrandPalette>
  fonts?: Partial<BrandKit["fonts"]>
  voice?: Partial<BrandKit["voice"]>
  layout_prefs?: Partial<BrandKit["layout_prefs"]>
  remove_logo?: boolean
  make_default?: boolean
}
export interface BrandOptions {
  fonts: { name: string; export_fallback: string }[]
  layouts?: string[]
  default_palette?: BrandPalette
  max_logo_bytes?: number
  logo_types?: string[]
  max_kits?: number
}
export interface BrandSuggestion {
  company_name?: string
  tagline?: string
  palette?: Partial<BrandPalette>
  fonts?: { heading?: string; body?: string } | null
  logo_url?: string | null
  source_url: string
  credits_used?: number
  saved: false
}

export const getBrandOptions = () => call<BrandOptions>("/brand-kits/options")
export const listBrandKits = () => call<{ kits?: BrandKit[]; items?: BrandKit[] } | BrandKit[]>("/brand-kits")
export const getBrandKit = (id: string) => call<BrandKit | { kit: BrandKit }>(`/brand-kits/${id}`)
export const getDefaultBrandKit = () => call<{ kit: BrandKit | null }>("/brand-kits/default")
export const createBrandKit = (b: BrandKitInput) => post<BrandKit>("/brand-kits", b)
export const updateBrandKit = (id: string, b: BrandKitInput) => call<BrandKit>(`/brand-kits/${id}`, { method: "PUT", body: JSON.stringify(b) })
export const setDefaultBrandKit = (id: string) => post<BrandKit>(`/brand-kits/${id}/default`)
export const deleteBrandKit = (id: string) => call<void>(`/brand-kits/${id}`, { method: "DELETE" })
export const suggestBrandFromUrl = (url: string) => post<BrandSuggestion>("/brand-kits/suggest-from-url", { url }, undefined, 60000)

/** Brand kit list responses vary slightly in envelope; normalise. */
export function unwrapKits(r: Awaited<ReturnType<typeof listBrandKits>>): BrandKit[] {
  if (Array.isArray(r)) return r
  return r.kits ?? r.items ?? []
}
export function unwrapKit(r: BrandKit | { kit: BrandKit }): BrandKit {
  return "kit" in r && r.kit ? r.kit : (r as BrandKit)
}

// ── Deck document model ──────────────────────────────────────────────
export type Layout =
  | "title"
  | "section"
  | "content"
  | "two_column"
  | "chart_full"
  | "chart_plus_text"
  | "kpi_strip"
  | "table"
  | "comparison"
  | "closing"

export interface Frame {
  x: number
  y: number
  w: number
  h: number
}
interface BlockBase {
  id: string
  slot?: string | null
  frame?: Frame | null
}
export interface TextItem {
  text: string
  bullet?: boolean
  level?: number
  bold?: boolean
}
export interface TextBlock extends BlockBase {
  type: "text"
  role?: "body" | "callout" | "quote" | "caption"
  align?: "left" | "center" | "right"
  items: TextItem[]
}
export interface KpiBlock extends BlockBase {
  type: "kpi"
  label: string
  value_ref: string
  delta_ref?: string | null
  format?: string | null
  delta_format?: string | null
  caption?: string
  good_direction?: "up" | "down"
}
export interface ChartAxis {
  x_title?: string
  y_title?: string
  y_format?: MeasureFormat | null
  y_min?: number | null
  y_max?: number | null
  sort?: "data" | "value_desc" | "value_asc"
}
export interface SeriesMap {
  x?: string | null
  y?: string[]
  y2?: string[]
  series?: string | null
}
export interface ChartBlock extends BlockBase {
  type: "chart"
  chart_type: ChartType
  title?: string
  query?: QuerySpec | null
  query_ref?: string | null
  series: SeriesMap
  axis?: ChartAxis
  labels?: boolean
  legend?: "none" | "top" | "bottom" | "right"
  colors?: string[]
}
export interface TableColumn {
  field: string
  label?: string | null
  format?: string | null
}
export interface TableBlock extends BlockBase {
  type: "table"
  title?: string
  query?: QuerySpec | null
  query_ref?: string | null
  columns: TableColumn[]
  max_rows?: number
}
export interface ImageBlock extends BlockBase {
  type: "image"
  source: { kind: "brand_logo" } | { kind: "url"; url: string }
  alt?: string
  fit?: "contain" | "cover"
}
export interface ShapeBlock extends BlockBase {
  type: "shape"
  shape: "divider" | "rect" | "accent_bar"
  color?: string
}
export type Block = TextBlock | KpiBlock | ChartBlock | TableBlock | ImageBlock | ShapeBlock
export type BlockType = Block["type"]

export interface Slide {
  id: string
  layout: Layout
  title: string
  subtitle?: string
  notes?: string
  blocks: Block[]
}
export interface DeckTheme {
  palette?: Partial<BrandPalette>
  fonts?: Partial<{ heading: string; body: string }>
  footer_text?: string
  slide_numbers?: boolean
}
export interface DeckDoc {
  schema_version: 1
  title: string
  brand_kit_id?: string | null
  theme?: DeckTheme
  settings?: { strict_numbers?: boolean }
  queries: Record<string, QuerySpec>
  slides: Slide[]
}

export interface DeckSummary {
  id: string
  title: string
  status: "draft" | "published" | string
  version: number
  slide_count: number
  brand_kit_id?: string | null
  created_by?: string | null
  updated_by?: string | null
  updated_at: string
  created_at?: string
}
export interface Deck extends DeckSummary {
  doc: DeckDoc
}
export interface Ungrounded {
  where: string
  literal: string
}
export interface SaveWarnings {
  ungrounded_numbers?: Ungrounded[]
  [k: string]: unknown
}
export type SavedDeck = Deck & { warnings?: SaveWarnings }
export interface DeckVersionSummary {
  version: number
  note?: string | null
  created_by?: string | null
  created_at: string
  slide_count?: number
  title?: string
}

export const listDecks = (p: { status?: string; q?: string; limit?: number; offset?: number } = {}) =>
  call<{ items?: DeckSummary[]; decks?: DeckSummary[]; total: number }>(`/decks${qs(p)}`)
export const getDeck = (id: string) => call<Deck>(`/decks/${id}`)
export const createDeck = (b: { title: string; doc?: DeckDoc; brand_kit_id?: string | null }) => post<Deck>("/decks", b)
export const saveDeck = (
  id: string,
  b: { title?: string; doc?: DeckDoc; brand_kit_id?: string | null; clear_brand_kit?: boolean; note?: string },
  version: number,
) => call<SavedDeck>(`/decks/${id}`, { method: "PUT", body: JSON.stringify(b), headers: { "If-Match": String(version) } })
export const deleteDeck = (id: string) => call<void>(`/decks/${id}`, { method: "DELETE" })
export const duplicateDeck = (id: string) => post<Deck>(`/decks/${id}/duplicate`)
export const publishDeck = (id: string, published: boolean) => post<Deck>(`/decks/${id}/publish`, { published })
export const listVersions = (id: string) =>
  call<{ items?: DeckVersionSummary[]; versions?: DeckVersionSummary[] } | DeckVersionSummary[]>(`/decks/${id}/versions`)
export const getVersion = (id: string, n: number) => call<{ version: number; doc: DeckDoc; title?: string }>(`/decks/${id}/versions/${n}`)
export const restoreVersion = (id: string, n: number, currentVersion: number) =>
  call<SavedDeck>(`/decks/${id}/versions/${n}/restore`, { method: "POST", headers: { "If-Match": String(currentVersion) } })

export function unwrapDecks(r: Awaited<ReturnType<typeof listDecks>>): DeckSummary[] {
  return r.items ?? r.decks ?? []
}
export function unwrapVersions(r: Awaited<ReturnType<typeof listVersions>>): DeckVersionSummary[] {
  if (Array.isArray(r)) return r
  return r.items ?? r.versions ?? []
}

// ── Refresh / resolve / export ───────────────────────────────────────
export interface DeckRun {
  run_id: string
  doc_version: number
  as_of: string
  queries?: string[]
  errors: Record<string, string>
  blocks: Record<string, string>
  data: Record<string, QueryResult>
}
export const refreshDeck = (id: string) => post<DeckRun>(`/decks/${id}/refresh`, undefined, undefined, 90000)

export interface ResolvedBlock {
  id: string
  type: BlockType
  slot?: string | null
  frame?: Frame | null
  query_alias?: string
  // text
  items?: TextItem[]
  role?: string
  align?: string
  // kpi
  label?: string
  value?: string
  delta?: string | null
  delta_direction?: "up" | "down" | "flat"
  delta_is_good?: boolean | null
  caption?: string
  // chart / table
  title?: string
  chart_type?: ChartType
  series?: SeriesMap
  axis?: ChartAxis
  labels?: boolean
  legend?: string
  colors?: string[]
  columns?: TableColumn[]
  max_rows?: number
  // image / shape
  source?: { kind: string; url?: string }
  alt?: string
  fit?: string
  shape?: string
  color?: string
}
export interface ResolvedSlide {
  id: string
  layout: Layout
  title: string
  subtitle?: string
  notes?: string
  blocks: ResolvedBlock[]
}
export interface ResolvedTheme {
  palette: BrandPalette
  fonts: { heading: string; body: string }
  footer_text?: string
  slide_numbers?: boolean
  [k: string]: unknown
}
export interface ExportBundle {
  format: "omnidome-deck/1"
  exported_at: string
  deck: { id: string; title: string; version: number; status: string }
  doc: DeckDoc
  brand_kit: BrandKit | null
  theme: ResolvedTheme
  as_of: string | null
  run_id: string | null
  stale_data: boolean
  slides: ResolvedSlide[]
  unresolved: unknown[]
  query_errors: Record<string, string>
  data: Record<string, QueryResult>
}
export const exportDeckJson = (id: string, p: { run_id?: string; refresh?: boolean } = {}) =>
  call<ExportBundle>(`/decks/${id}/export/json${qs(p)}`, undefined, 90000)

// ── AI assist ────────────────────────────────────────────────────────
export interface AiOutlineInput {
  brief: string
  audience?: string
  tone?: string
  slide_count: number
  dataset_ids: string[]
  research_run_ids?: string[]
  competitor_ids?: string[]
  campaign_analysis_ids?: string[]
  brand_kit_id?: string | null
}
export interface Dropped {
  alias?: string
  id?: string
  reason?: string
  [k: string]: unknown
}
export interface OutlineResult {
  deck: DeckDoc
  dropped: { queries?: Dropped[]; blocks?: Dropped[] }
  ungrounded_numbers: Ungrounded[]
  invalid_tokens: unknown[]
  citations: { slide?: string | number; tag?: string; title?: string; url?: string }[]
  queries_tested: number
  queries_kept: number
  model?: string
  ai_calls_today?: { used: number; cap: number; remaining: number }
}
export interface SlideAiResult {
  patch: unknown[]
  slide: Slide
  dropped: Dropped[]
  ungrounded_numbers: Ungrounded[]
  invalid_tokens: unknown[]
  base_version: number
  doc_after?: DeckDoc
  model?: string
}
export interface NarrativeResult {
  insights: { alias: string; kind: string; measure: string; sentence: string; sentence_resolved: string; data?: unknown }[]
  notes: string
  notes_resolved: string
  takeaways: string[]
  takeaways_resolved: string[]
  ungrounded_numbers: Ungrounded[]
  invalid_tokens: unknown[]
  unresolved: unknown[]
  llm_used: boolean
  model?: string
  as_of?: string
}
export const aiOutline = (b: AiOutlineInput) => post<OutlineResult>("/ai/outline", b, undefined, 150000)
export const aiSlide = (b: { deck_id: string; slide_id: string; instruction: string; include_doc?: boolean }) =>
  post<SlideAiResult>("/ai/slide", { include_doc: true, ...b }, undefined, 150000)
export const aiNarrative = (b: { deck_id: string; slide_id: string; refresh?: boolean }) =>
  post<NarrativeResult>("/ai/narrative", b, undefined, 150000)
export const getAiUsage = () => call<{ ai_calls_today: { used: number; cap: number; remaining: number } }>("/ai/usage")

// ── helpers ──────────────────────────────────────────────────────────
export function aiErrorMessage(e: unknown): string {
  if (e instanceof BiApiError) {
    if (e.status === 429) return `AI limit reached: ${e.message}`
    if (e.status === 502 || e.status === 503 || e.status === 504) return `The AI provider is unavailable right now (${e.message}). Try again shortly.`
    return e.message
  }
  return e instanceof Error ? e.message : "Something went wrong"
}
