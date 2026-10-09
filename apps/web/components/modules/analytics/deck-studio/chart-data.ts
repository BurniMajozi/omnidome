import type { ChartAxis, ChartType, QueryColumn, QueryResult, SeriesMap } from "@/lib/bi-studio-api"

/** Turns a query result + series mapping into chart-ready series. Shared by the recharts view and the PPTX exporter. */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

export function formatXLabel(v: unknown, col?: QueryColumn): string {
  if (v === null || v === undefined || v === "") return "(none)"
  const s = String(v)
  if (col?.kind === "time" && /^\d{4}-\d{2}-\d{2}/.test(s)) {
    const y = Number(s.slice(0, 4))
    const m = Number(s.slice(5, 7))
    const d = Number(s.slice(8, 10))
    switch (col.grain) {
      case "year":
        return String(y)
      case "quarter":
        return `Q${Math.floor((m - 1) / 3) + 1} ${y}`
      case "month":
        return `${MONTHS[m - 1]} ${String(y).slice(2)}`
      case "week":
        return `${d} ${MONTHS[m - 1]}`
      default:
        return `${d} ${MONTHS[m - 1]}`
    }
  }
  return s
}

export interface SeriesData {
  name: string
  values: (number | null)[]
  axis?: "y2"
  /** measure id this series came from */
  measure: string
}
export interface ChartData {
  categories: string[]
  series: SeriesData[]
  /** scatter points, series name -> points */
  points?: { name: string; data: { x: number; y: number }[] }[]
  xLabel: string
  yFormat?: string | null
  y2Format?: string | null
  measureLabels: Record<string, string>
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : v === null || v === undefined || v === "" ? null : Number.isFinite(Number(v)) ? Number(v) : null)

export function prepareChart(res: QueryResult, type: ChartType, sm: SeriesMap, axis?: ChartAxis): ChartData | null {
  const cols = res.columns
  const idx = (id?: string | null) => (id ? cols.findIndex((c) => c.id === id) : -1)
  const measures = cols.filter((c) => c.kind === "measure")
  const ys = (sm.y?.length ? sm.y : measures.map((m) => m.id).filter((m) => !(sm.y2 ?? []).includes(m))).filter((m) => idx(m) >= 0)
  const y2s = (sm.y2 ?? []).filter((m) => idx(m) >= 0)
  if (ys.length === 0 && y2s.length === 0) return null
  const firstDim = cols.findIndex((c) => c.kind !== "measure")
  const xi = type === "scatter" && sm.x && cols[idx(sm.x)]?.kind === "measure" ? idx(sm.x) : idx(sm.x) >= 0 ? idx(sm.x) : firstDim
  const xCol = cols[xi]
  const labels: Record<string, string> = Object.fromEntries(measures.map((m) => [m.id, m.label]))
  const yFormat = axis?.y_format ?? cols[idx(ys[0])]?.format ?? null
  const y2Format = cols[idx(y2s[0])]?.format ?? null

  if (type === "scatter") {
    const xm = xCol?.kind === "measure" ? xCol : measures[0]
    const ym = ys.find((y) => y !== xm?.id) ?? measures.find((m) => m.id !== xm?.id)?.id
    if (!xm || !ym) return null
    const xs = idx(xm.id)
    const yi = idx(ym)
    const si = idx(sm.series)
    const groups = new Map<string, { x: number; y: number }[]>()
    for (const r of res.rows) {
      const x = num(r[xs])
      const y = num(r[yi])
      if (x === null || y === null) continue
      const g = si >= 0 ? formatXLabel(r[si], cols[si]) : "All"
      if (!groups.has(g)) groups.set(g, [])
      groups.get(g)!.push({ x, y })
    }
    return {
      categories: [],
      series: [],
      points: [...groups].map(([name, data]) => ({ name, data })),
      xLabel: xm.label,
      yFormat: cols[yi]?.format ?? null,
      measureLabels: { ...labels, __x: xm.label, __y: labels[ym] ?? ym },
    }
  }

  const si = idx(sm.series)
  let categories: string[] = []
  let series: SeriesData[] = []
  if (si >= 0 && xi >= 0 && ys.length >= 1) {
    const y = ys[0]
    const yi = idx(y)
    const catOrder: string[] = []
    const serOrder: string[] = []
    const cell = new Map<string, number | null>()
    for (const r of res.rows) {
      const c = formatXLabel(r[xi], xCol)
      const s = formatXLabel(r[si], cols[si])
      if (!catOrder.includes(c)) catOrder.push(c)
      if (!serOrder.includes(s)) serOrder.push(s)
      cell.set(`${c}\u0000${s}`, (cell.get(`${c}\u0000${s}`) ?? 0) + (num(r[yi]) ?? 0))
    }
    categories = catOrder
    series = serOrder.map((s) => ({ name: s, measure: y, values: catOrder.map((c) => cell.get(`${c}\u0000${s}`) ?? null) }))
  } else {
    categories = res.rows.map((r) => (xi >= 0 ? formatXLabel(r[xi], xCol) : "Total"))
    series = [
      ...ys.map((m) => ({ name: labels[m] ?? m, measure: m, values: res.rows.map((r) => num(r[idx(m)])) })),
      ...y2s.map((m) => ({ name: labels[m] ?? m, measure: m, axis: "y2" as const, values: res.rows.map((r) => num(r[idx(m)])) })),
    ]
  }

  // sorting by first series value
  if ((axis?.sort === "value_desc" || axis?.sort === "value_asc") && series[0]) {
    const order = categories.map((_c, i) => i)
    const k = axis.sort === "value_desc" ? -1 : 1
    order.sort((a, b) => k * ((series[0].values[a] ?? 0) - (series[0].values[b] ?? 0)))
    categories = order.map((i) => categories[i])
    series = series.map((s) => ({ ...s, values: order.map((i) => s.values[i]) }))
  }
  return { categories, series, xLabel: xCol?.label ?? "", yFormat, y2Format, measureLabels: labels }
}

/** Waterfall: running base + signed bars. */
export function waterfallBars(values: (number | null)[]): { base: number; up: number; down: number }[] {
  let run = 0
  return values.map((v) => {
    const d = v ?? 0
    const start = run
    run += d
    return d >= 0 ? { base: start, up: d, down: 0 } : { base: run, up: 0, down: -d }
  })
}
