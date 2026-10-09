import type { ChartType, DatasetDef, Grain, QueryFilter, QuerySpec, SeriesMap } from "@/lib/bi-studio-api"

/** The Power-BI-style "field wells" model, convertible to/from a query spec + series mapping. */
export interface BuilderModel {
  dataset: string
  xTime: { dim: string; grain: Grain } | null
  xDim: string | null
  xMeasure: string | null // scatter x
  y: string[]
  y2: string[]
  series: string | null
  extraDims: string[] // table columns
  range: { from: string; to: string }
  /** time range filter without grouping (when xTime is null) */
  rangeDim: string | null
  filters: QueryFilter[]
  sort: { field: string; dir: "asc" | "desc" } | null
  limit: number
}

export const GRAINS: Grain[] = ["day", "week", "month", "quarter", "year"]

export function emptyModel(dataset: string): BuilderModel {
  return { dataset, xTime: null, xDim: null, xMeasure: null, y: [], y2: [], series: null, extraDims: [], range: { from: "", to: "" }, rangeDim: null, filters: [], sort: null, limit: 500 }
}

export function modelFrom(spec: QuerySpec | null | undefined, sm: SeriesMap | null | undefined, type: ChartType | "table" | "kpi", ds?: DatasetDef): BuilderModel | null {
  if (!spec) return null
  const m = emptyModel(spec.dataset)
  const timeDim = spec.time?.dimension ?? ds?.default_time_dimension ?? null
  if (spec.time?.grain && timeDim) m.xTime = { dim: timeDim, grain: spec.time.grain }
  else if (spec.time && (spec.time.from || spec.time.to)) m.rangeDim = timeDim
  m.range = { from: spec.time?.from ?? "", to: spec.time?.to ?? "" }
  const dims = spec.dimensions ?? []
  if (type === "table") {
    m.extraDims = [...dims]
    m.y = [...spec.measures]
  } else if (type === "kpi") {
    m.y = spec.measures.slice(0, 1)
  } else {
    const series = sm?.series && dims.includes(sm.series) ? sm.series : null
    m.series = series
    m.xDim = dims.find((d) => d !== series) ?? null
    const y2 = (sm?.y2 ?? []).filter((x) => spec.measures.includes(x))
    m.y2 = y2
    if (type === "scatter" && sm?.x && spec.measures.includes(sm.x)) {
      m.xMeasure = sm.x
      m.y = spec.measures.filter((x) => x !== sm.x)
    } else m.y = (sm?.y?.length ? sm.y : spec.measures).filter((x) => spec.measures.includes(x) && !y2.includes(x))
  }
  m.filters = spec.filters ? [...spec.filters] : []
  m.sort = spec.order_by?.[0] ? { field: spec.order_by[0].field, dir: spec.order_by[0].dir } : null
  m.limit = spec.limit ?? 500
  return m
}

export function modelToSpec(m: BuilderModel, type: ChartType | "table" | "kpi"): QuerySpec {
  const measures = [...new Set([...(m.xMeasure && type === "scatter" ? [m.xMeasure] : []), ...m.y, ...(type === "combo" ? m.y2 : [])])]
  const dimensions = type === "table" ? [...m.extraDims] : type === "kpi" ? [] : [m.xDim, m.series].filter((x): x is string => !!x)
  const spec: QuerySpec = { dataset: m.dataset, measures, dimensions }
  const hasRange = !!(m.range.from || m.range.to)
  if (m.xTime && type !== "scatter") {
    spec.time = { dimension: m.xTime.dim, grain: m.xTime.grain, ...(m.range.from ? { from: m.range.from } : {}), ...(m.range.to ? { to: m.range.to } : {}) }
  } else if (hasRange) {
    spec.time = { ...(m.rangeDim ?? m.xTime?.dim ? { dimension: (m.rangeDim ?? m.xTime?.dim) as string } : {}), ...(m.range.from ? { from: m.range.from } : {}), ...(m.range.to ? { to: m.range.to } : {}) }
  }
  if (m.filters.length) spec.filters = m.filters
  const selected = new Set<string>([...measures, ...dimensions, ...(spec.time?.grain ? [spec.time.dimension ?? ""] : [])])
  if (m.sort && selected.has(m.sort.field)) spec.order_by = [m.sort]
  spec.limit = Math.max(1, Math.min(1000, m.limit || 500))
  return spec
}

export function modelToSeries(m: BuilderModel, type: ChartType): SeriesMap {
  const x = type === "scatter" ? m.xMeasure : (m.xTime ? m.xTime.dim : m.xDim)
  return { x: x ?? null, y: m.y, y2: type === "combo" ? m.y2 : [], series: m.series }
}

/** Adjust a model so it satisfies a chart type's constraints; reports what was changed. */
export function fitToType(m: BuilderModel, type: ChartType | "table" | "kpi"): { model: BuilderModel; notes: string[] } {
  const notes: string[] = []
  const n = { ...m, y: [...m.y], y2: [...m.y2] }
  if (type === "pie" || type === "donut" || type === "waterfall") {
    if (n.y.length + n.y2.length > 1) {
      n.y = [...n.y, ...n.y2].slice(0, 1)
      n.y2 = []
      notes.push("Kept only the first value (this chart takes one measure).")
    }
    if (n.xTime && (type === "pie" || type === "donut")) {
      notes.push("Time grouping is used as categories.")
    }
  }
  if (type === "combo" && n.y2.length === 0 && n.y.length >= 2) {
    n.y2 = [n.y.pop() as string]
    notes.push(`Moved the last value to the second axis (line).`)
  }
  if (type !== "combo" && n.y2.length) {
    n.y = [...n.y, ...n.y2]
    n.y2 = []
  }
  if (type === "scatter") {
    if (!n.xMeasure && n.y.length >= 2) {
      n.xMeasure = n.y[0]
      n.y = n.y.slice(1)
    }
  } else if (n.xMeasure) {
    n.y = [n.xMeasure, ...n.y]
    n.xMeasure = null
  }
  return { model: n, notes }
}

/** Why the current wells cannot form a valid chart of this type (null = fine). */
export function validateModel(m: BuilderModel, type: ChartType | "table" | "kpi"): string | null {
  const meas = m.y.length + m.y2.length + (m.xMeasure ? 1 : 0)
  if (!m.dataset) return "Choose a dataset"
  if (type === "table") return m.y.length + m.extraDims.length === 0 ? "Add at least one column" : null
  if (type === "kpi") return m.y.length === 0 ? "Choose a measure for the KPI" : null
  if (m.y.length + m.y2.length === 0) return "Add a measure to Values"
  if ((type === "pie" || type === "donut" || type === "waterfall") && m.y.length !== 1) return "This chart type needs exactly one measure"
  if (type === "scatter" && meas < 2) return "Scatter needs two measures (X value and Y value)"
  if (type === "combo" && m.y2.length === 0) return "Combo needs a second measure for the line"
  if (type === "combo" && m.y.length === 0) return "Combo needs a measure for the columns"
  if (type !== "scatter" && !m.xTime && !m.xDim) return "Add a Category/Axis (a dimension or a date)"
  return null
}

export function opsForType(t: string): { id: string; label: string }[] {
  const all = {
    eq: "equals",
    neq: "not equal",
    in: "is one of",
    not_in: "is not one of",
    contains: "contains",
    gt: "greater than",
    gte: "at least",
    lt: "less than",
    lte: "at most",
    between: "between",
    is_null: "is empty",
    not_null: "is not empty",
  }
  const ids = t === "category" ? ["eq", "neq", "in", "not_in", "contains", "is_null", "not_null"] : t === "number" ? ["eq", "neq", "gt", "gte", "lt", "lte", "between", "in", "is_null", "not_null"] : ["eq", "gt", "gte", "lt", "lte", "between", "is_null", "not_null"]
  return ids.map((id) => ({ id, label: all[id as keyof typeof all] }))
}

export function presetRange(kind: "ytd" | "3m" | "6m" | "12m" | "all"): { from: string; to: string } {
  const now = new Date()
  const iso = (d: Date) => d.toISOString().slice(0, 10)
  const back = (m: number) => {
    const d = new Date(now.getFullYear(), now.getMonth() - m + 1, 1)
    return iso(d)
  }
  if (kind === "all") return { from: "", to: "" }
  if (kind === "ytd") return { from: `${now.getFullYear()}-01-01`, to: iso(now) }
  return { from: back(kind === "3m" ? 3 : kind === "6m" ? 6 : 12), to: iso(now) }
}
