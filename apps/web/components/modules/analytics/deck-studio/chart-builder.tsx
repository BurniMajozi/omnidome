"use client"

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import {
  Activity,
  BarChart3,
  BarChartHorizontal,
  ChartColumnStacked,
  CircleDot,
  GripVertical,
  Hash,
  LineChart,
  Loader2,
  PieChart,
  ScatterChart,
  Search,
  Sparkles,
  Table2,
  TrendingUp,
  X,
  AreaChart,
  BarChartBig,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  runQuery,
  suggestCharts,
  type Block,
  type ChartBlock,
  type ChartSuggestion,
  type ChartType,
  type DatasetDef,
  type DeckDoc,
  type Grain,
  type KpiBlock,
  type QueryFilter,
  type QueryResult,
  type QuerySpec,
  type TableBlock,
} from "@/lib/bi-studio-api"
import { cn } from "@/lib/utils"
import { ErrorNote, errText } from "../shared"
import { Field, Modal, fieldCls, useStudio } from "./ui"
import { newId } from "./doc-ops"
import {
  emptyModel,
  fitToType,
  GRAINS,
  modelFrom,
  modelToSeries,
  modelToSpec,
  opsForType,
  presetRange,
  validateModel,
  type BuilderModel,
} from "./builder-model"
import { ChartView, KpiView, TableView } from "./slide-renderer"
import type { Theme } from "./theme"
import { STATS } from "./data-picker"

export type BuilderKind = "chart" | "kpi" | "table"
export type BuilderResult =
  | { kind: "chart"; block: ChartBlock }
  | { kind: "table"; block: TableBlock }
  | { kind: "kpi"; block: KpiBlock; alias: string; spec: QuerySpec }

type TypeKey = ChartType | "table" | "kpi"
const TYPES: { id: ChartType | "table"; label: string; icon: ReactNode }[] = [
  { id: "column", label: "Column", icon: <BarChart3 className="h-5 w-5" /> },
  { id: "bar", label: "Bar", icon: <BarChartHorizontal className="h-5 w-5" /> },
  { id: "stacked_column", label: "Stacked", icon: <ChartColumnStacked className="h-5 w-5" /> },
  { id: "line", label: "Line", icon: <LineChart className="h-5 w-5" /> },
  { id: "area", label: "Area", icon: <AreaChart className="h-5 w-5" /> },
  { id: "combo", label: "Combo", icon: <Activity className="h-5 w-5" /> },
  { id: "pie", label: "Pie", icon: <PieChart className="h-5 w-5" /> },
  { id: "donut", label: "Donut", icon: <CircleDot className="h-5 w-5" /> },
  { id: "scatter", label: "Scatter", icon: <ScatterChart className="h-5 w-5" /> },
  { id: "waterfall", label: "Waterfall", icon: <BarChartBig className="h-5 w-5" /> },
  { id: "table", label: "Table", icon: <Table2 className="h-5 w-5" /> },
]

const KPI_STATS = STATS.filter((s) => ["total", "last", "prev", "first", "max", "min", "avg", "top1.value", "rows"].includes(s.id))

function parseRef(ref: string | null | undefined, measures: string[]): { alias: string; measure: string; stat: string } {
  const seg = (ref ?? "").split(".")
  const alias = seg[0] ?? ""
  let i = 1
  let measure = ""
  if (seg[i] && measures.includes(seg[i])) {
    measure = seg[i]
    i++
  }
  return { alias, measure, stat: seg.slice(i).join(".") || "total" }
}

export function ChartBuilder({
  kind,
  block,
  doc,
  theme,
  onApply,
  onClose,
}: {
  kind: BuilderKind
  block: Block | null
  doc: DeckDoc
  theme: Theme
  onApply: (r: BuilderResult) => void
  onClose: () => void
}) {
  const { catalog, datasets } = useStudio()

  // ── initial state from the block ────────────────────────────────────
  const init = useMemo(() => {
    if (block?.type === "chart") {
      const spec = block.query ?? (block.query_ref ? doc.queries[block.query_ref] : null)
      return { type: block.chart_type as TypeKey, model: modelFrom(spec, block.series, block.chart_type, datasets.get(spec?.dataset ?? "")), block }
    }
    if (block?.type === "table") {
      const spec = block.query ?? (block.query_ref ? doc.queries[block.query_ref] : null)
      return { type: "table" as TypeKey, model: modelFrom(spec, null, "table", datasets.get(spec?.dataset ?? "")), block }
    }
    if (block?.type === "kpi") {
      const alias = block.value_ref.split(".")[0]
      const spec = doc.queries[alias]
      return { type: "kpi" as TypeKey, model: modelFrom(spec, null, "kpi", datasets.get(spec?.dataset ?? "")), block }
    }
    return { type: (kind === "chart" ? "column" : kind) as TypeKey, model: null as BuilderModel | null, block: null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const [type, setType] = useState<TypeKey>(init.type)
  const [model, setModel] = useState<BuilderModel | null>(init.model)
  const [notes, setNotes] = useState<string[]>([])
  const [search, setSearch] = useState("")
  const ds: DatasetDef | undefined = model ? datasets.get(model.dataset) : undefined

  // formatting state
  const cb = init.block?.type === "chart" ? init.block : null
  const tb = init.block?.type === "table" ? init.block : null
  const kb = init.block?.type === "kpi" ? init.block : null
  const [title, setTitle] = useState(cb?.title ?? tb?.title ?? "")
  const [labels, setLabels] = useState(cb?.labels ?? false)
  const [legend, setLegend] = useState<NonNullable<ChartBlock["legend"]>>(cb?.legend ?? "bottom")
  const [axis, setAxis] = useState(cb?.axis ?? { sort: "data" as const })
  const [custom, setCustom] = useState<string[]>(cb?.colors ?? [])
  const [maxRows, setMaxRows] = useState(tb?.max_rows ?? 10)
  // kpi
  const kRef = parseRef(kb?.value_ref, init.model?.y ?? [])
  const [kLabel, setKLabel] = useState(kb?.label ?? "")
  const [kStat, setKStat] = useState(kRef.stat === "total" || KPI_STATS.some((s) => s.id === kRef.stat) ? kRef.stat : "total")
  const [kDelta, setKDelta] = useState<string>(kb?.delta_ref ? parseRef(kb.delta_ref, init.model?.y ?? []).stat : "")
  const [kFormat, setKFormat] = useState(kb?.format ?? "")
  const [kCaption, setKCaption] = useState(kb?.caption ?? "")
  const [kGood, setKGood] = useState<"up" | "down">(kb?.good_direction ?? "up")

  const isKpi = type === "kpi"
  const isTable = type === "table"
  const chartType: ChartType | null = isKpi || isTable ? null : (type as ChartType)

  const err = model ? validateModel(model, type) : "Pick a dataset to start"
  const spec = useMemo(() => (model && !err ? modelToSpec(kpiModel(model, isKpi, kStat, kDelta), type) : null), [model, err, type, isKpi, kStat, kDelta])
  const specKey = JSON.stringify(spec)

  // live preview
  const [preview, setPreview] = useState<{ res?: QueryResult; error?: string; loading: boolean }>({ loading: false })
  useEffect(() => {
    if (!spec) {
      setPreview({ loading: false })
      return
    }
    const ctl = new AbortController()
    setPreview((p) => ({ ...p, loading: true, error: undefined }))
    const t = setTimeout(() => {
      runQuery(spec, ctl.signal)
        .then((res) => setPreview({ res, loading: false }))
        .catch((e) => !ctl.signal.aborted && setPreview({ loading: false, error: errText(e) }))
    }, 450)
    return () => {
      clearTimeout(t)
      ctl.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specKey])

  // ── field operations ────────────────────────────────────────────────
  function patch(fn: (m: BuilderModel) => BuilderModel) {
    setModel((m) => (m ? fn(m) : m))
  }
  function chooseDataset(id: string) {
    setModel(emptyModel(id))
    setNotes([])
  }
  function changeType(t: TypeKey) {
    if (!model) {
      setType(t)
      return
    }
    const { model: fitted, notes: n } = fitToType(model, t)
    setModel(fitted)
    setNotes(n)
    setType(t)
  }
  function addField(kindOf: "measure" | "dimension" | "time", id: string, well?: string) {
    if (!model) return
    patch((m) => {
      const n = { ...m, y: [...m.y], y2: [...m.y2], extraDims: [...m.extraDims] }
      if (kindOf === "measure") {
        if (isKpi) return { ...n, y: [id] }
        if (well === "y2" || (type === "combo" && n.y.length > 0 && well !== "y" && !n.y2.length && false)) {
          if (!n.y2.includes(id) && !n.y.includes(id)) n.y2.push(id)
          return n
        }
        if (type === "scatter" && !n.xMeasure && well === "x") return { ...n, xMeasure: id }
        if (n.y.includes(id) || n.y2.includes(id)) return n
        if (type === "pie" || type === "donut" || type === "waterfall") return { ...n, y: [id] }
        if (type === "scatter" && !n.xMeasure && n.y.length >= 1) return { ...n, xMeasure: n.y[0], y: [id] }
        n.y.push(id)
        return n
      }
      if (isKpi) return n
      if (isTable) {
        if (kindOf === "time") return n.extraDims.includes(id) ? n : { ...n, xTime: { dim: id, grain: n.xTime?.grain ?? "month" } }
        if (!n.extraDims.includes(id)) n.extraDims.push(id)
        return n
      }
      if (kindOf === "time") {
        const mv = n.xDim && !n.series ? { series: n.xDim } : {}
        return { ...n, ...mv, xDim: null, xTime: { dim: id, grain: n.xTime?.grain ?? "month" } }
      }
      if (well === "series" || (n.xDim && (!n.series || well === "series") && well !== "x") || ((n.xTime || n.xDim) && !n.series && well !== "x")) {
        if (n.xDim === id) return n
        return { ...n, series: id }
      }
      return { ...n, xDim: id, series: n.series === id ? null : n.series }
    })
  }
  function onDropWell(well: string, e: React.DragEvent) {
    e.preventDefault()
    const raw = e.dataTransfer.getData("text/plain")
    const m = /^bi-field:(measure|dimension|time):(.+)$/.exec(raw)
    if (m) addField(m[1] as "measure" | "dimension" | "time", m[2], well)
  }

  // suggestions
  const [sugg, setSugg] = useState<ChartSuggestion[] | null>(null)
  const [suggErr, setSuggErr] = useState<string | null>(null)
  async function suggest() {
    if (!model) return
    setSuggErr(null)
    try {
      const meas = [...model.y, ...model.y2, ...(model.xMeasure ? [model.xMeasure] : [])]
      const r = await suggestCharts({
        dataset: model.dataset,
        measures: meas,
        dimensions: [model.xDim, model.series, ...model.extraDims].filter((x): x is string => !!x),
        time: model.xTime ? { dimension: model.xTime.dim, grain: model.xTime.grain } : null,
        row_count: preview.res?.meta.row_count,
      })
      setSugg(r.suggestions)
    } catch (e) {
      setSuggErr(errText(e))
    }
  }
  function applySuggestion(s: ChartSuggestion) {
    if (!model) return
    const t = s.type as TypeKey
    let n: BuilderModel = { ...model }
    const sm = s.series_mapping
    if (sm && t !== "kpi" && t !== "table") {
      const dimsOf = (id: string | null | undefined) => (id ? ds?.dimensions.find((d) => d.id === id) : undefined)
      const x = dimsOf(sm.x)
      if (sm.y?.length) n.y = sm.y
      if (x?.type === "time") {
        n = { ...n, xTime: { dim: x.id, grain: n.xTime?.grain ?? "month" }, xDim: null }
      } else if (x) n = { ...n, xDim: x.id, xTime: null }
      n.series = sm.series ?? null
    }
    const f = fitToType(n, t)
    setModel(f.model)
    setNotes(f.notes)
    setType(t)
  }

  // ── apply ───────────────────────────────────────────────────────────
  function apply() {
    if (!model || !spec) return
    if (type === "kpi") {
      const measure = model.y[0]
      const alias = kb ? kb.value_ref.split(".")[0] : `${init.block?.id ?? newId(doc, "k")}_q`
      const id = init.block?.id ?? alias.replace(/_q$/, "")
      const block: KpiBlock = {
        ...(kb ?? { slot: null, frame: null }),
        type: "kpi",
        id,
        label: kLabel || ds?.measures.find((m) => m.id === measure)?.label || measure,
        value_ref: `${alias}.${measure}${kStat === "total" ? "" : `.${kStat}`}`,
        delta_ref: kDelta ? `${alias}.${measure}.${kDelta}` : null,
        format: kFormat || null,
        caption: kCaption,
        good_direction: kGood,
      }
      return onApply({ kind: "kpi", block, alias, spec })
    }
    if (type === "table") {
      const cols = [...model.extraDims, ...(model.xTime ? [model.xTime.dim] : []), ...model.y]
      const block: TableBlock = {
        ...(tb ?? { slot: null, frame: null }),
        type: "table",
        id: tb?.id ?? newId(doc, "t"),
        title,
        query: spec,
        query_ref: null,
        columns: cols.map((field) => ({ field })),
        max_rows: maxRows,
      }
      return onApply({ kind: "table", block })
    }
    const ct = type as ChartType
    const series = modelToSeries(model, ct)
    const block: ChartBlock = {
      ...(cb ?? { slot: null, frame: null }),
      type: "chart",
      id: cb?.id ?? newId(doc, "c"),
      chart_type: ct,
      title,
      query: spec,
      query_ref: null,
      series,
      axis: { ...axis },
      labels,
      legend,
      colors: custom,
    }
    onApply({ kind: "chart", block })
  }

  // preview block
  const previewBlock = useMemo<ChartBlock | null>(() => {
    if (!model || !spec || !chartType) return null
    return { type: "chart", id: "preview", chart_type: chartType, title, query: spec, series: modelToSeries(model, chartType), axis, labels, legend, colors: custom }
  }, [model, spec, chartType, title, axis, labels, legend, custom])
  const previewTable: TableBlock | null = isTable && spec && model ? { type: "table", id: "preview", title, query: spec, columns: [...model.extraDims, ...(model.xTime ? [model.xTime.dim] : []), ...model.y].map((field) => ({ field })), max_rows: maxRows } : null
  const previewKpi: KpiBlock | null =
    isKpi && model?.y[0]
      ? { type: "kpi", id: "preview", label: kLabel || model.y[0], value_ref: `pv.${model.y[0]}${kStat === "total" ? "" : `.${kStat}`}`, delta_ref: kDelta ? `pv.${model.y[0]}.${kDelta}` : null, format: kFormat || null, caption: kCaption, good_direction: kGood }
      : null

  // ── field pane ──────────────────────────────────────────────────────
  const q = search.trim().toLowerCase()
  const dims = (ds?.dimensions ?? []).filter((d) => !q || d.label.toLowerCase().includes(q) || d.id.includes(q))
  const meas = (ds?.measures ?? []).filter((m) => !q || m.label.toLowerCase().includes(q) || m.id.includes(q))
  const grouped = useMemo(() => {
    const m = new Map<string, DatasetDef[]>()
    for (const d of catalog?.datasets ?? []) m.set(d.category ?? "Other", [...(m.get(d.category ?? "Other") ?? []), d])
    return [...m]
  }, [catalog])

  const label = (id: string) => ds?.measures.find((m) => m.id === id)?.label ?? ds?.dimensions.find((d) => d.id === id)?.label ?? id
  const showSeries = !isKpi && !isTable
  const selectableFilter = ds?.dimensions ?? []

  return (
    <Modal
      full
      title={kind === "kpi" ? "KPI builder" : kind === "table" ? "Table builder" : "Chart builder"}
      onClose={onClose}
      footer={
        <>
          {err && <span className="mr-auto text-xs text-amber-300">{err}</span>}
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" disabled={!spec} onClick={apply}>
            {init.block ? "Apply changes" : kind === "kpi" ? "Add KPI to slide" : kind === "table" ? "Add table to slide" : "Add chart to slide"}
          </Button>
        </>
      }
    >
      <div className="grid h-full min-h-[520px] gap-3 lg:grid-cols-[230px_minmax(0,1fr)_minmax(0,1.15fr)]">
        {/* DATA PANE */}
        <div className="flex min-h-0 flex-col rounded-md border border-border">
          <div className="space-y-2 border-b border-border p-2">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Data</div>
            <select aria-label="Dataset" className={fieldCls} value={model?.dataset ?? ""} onChange={(e) => chooseDataset(e.target.value)}>
              <option value="" disabled>
                Choose a dataset…
              </option>
              {grouped.map(([cat, list]) => (
                <optgroup key={cat} label={cat}>
                  {list.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            {ds && (
              <div className="relative">
                <Search className="pointer-events-none absolute left-2 top-2 h-3.5 w-3.5 text-muted-foreground" />
                <input aria-label="Search fields" className={`${fieldCls} pl-7`} placeholder="Search fields" value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>
            )}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2 text-xs">
            {!ds && <p className="text-muted-foreground">Pick a dataset to see its fields. Click or drag a field into the wells.</p>}
            {ds && (
              <>
                <FieldGroup title="Dimensions">
                  {dims.map((d) => (
                    <FieldItem key={d.id} id={d.id} label={d.label} sub={d.type === "time" ? "date" : d.type} kind={d.type === "time" ? "time" : "dimension"} onAdd={() => addField(d.type === "time" ? "time" : "dimension", d.id)} />
                  ))}
                </FieldGroup>
                <FieldGroup title="Measures">
                  {meas.map((m) => (
                    <FieldItem key={m.id} id={m.id} label={m.label} sub={m.format.replace("currency_zar", "R")} kind="measure" onAdd={() => addField("measure", m.id)} title={m.description} />
                  ))}
                </FieldGroup>
              </>
            )}
          </div>
        </div>

        {/* WELLS */}
        <div className="min-h-0 space-y-3 overflow-y-auto pr-1">
          {!isKpi && !isTable && (
            <div>
              <div className="mb-1 flex items-center justify-between">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Visual</div>
                <Button size="sm" variant="ghost" className="h-6 text-xs" disabled={!model || (model.y.length === 0 && !model.xDim && !model.xTime)} onClick={suggest}>
                  <Sparkles className="h-3.5 w-3.5" /> Suggest a chart
                </Button>
              </div>
              <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-6 lg:grid-cols-4 xl:grid-cols-6" role="radiogroup" aria-label="Chart type">
                {TYPES.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    role="radio"
                    aria-checked={type === t.id}
                    title={t.label}
                    onClick={() => changeType(t.id)}
                    className={cn("flex flex-col items-center gap-0.5 rounded-md border px-1 py-1.5 text-[10px] transition-colors", type === t.id ? "border-primary bg-primary/15 text-primary" : "border-border text-muted-foreground hover:border-primary/50")}
                  >
                    {t.icon}
                    {t.label}
                  </button>
                ))}
              </div>
              {notes.map((n, i) => (
                <p key={i} className="mt-1 text-[11px] text-amber-300">
                  {n}
                </p>
              ))}
              {suggErr && <ErrorNote message={suggErr} className="mt-2" />}
              {sugg && (
                <ul className="mt-2 space-y-1 rounded-md border border-border p-2">
                  {sugg.slice(0, 5).map((s) => (
                    <li key={s.type} className="flex items-start gap-2 text-xs">
                      <button type="button" className="rounded border border-primary/40 px-1.5 py-0.5 font-medium text-primary hover:bg-primary/10" onClick={() => applySuggestion(s)}>
                        {s.type}
                      </button>
                      <span className="text-muted-foreground">{s.reason}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {model ? (
            <div className="space-y-2">
              {isTable ? (
                <Well name="Columns" hint="Drop dimensions and measures" onDrop={(e) => onDropWell("y", e)}>
                  {model.extraDims.map((d) => (
                    <Chip key={d} label={label(d)} onRemove={() => patch((m) => ({ ...m, extraDims: m.extraDims.filter((x) => x !== d) }))} />
                  ))}
                  {model.xTime && <Chip label={`${label(model.xTime.dim)} (${model.xTime.grain})`} onRemove={() => patch((m) => ({ ...m, xTime: null }))} />}
                  {model.y.map((d) => (
                    <Chip key={d} label={label(d)} tone="measure" onRemove={() => patch((m) => ({ ...m, y: m.y.filter((x) => x !== d) }))} />
                  ))}
                </Well>
              ) : (
                <>
                  {!isKpi && (
                    <Well name={type === "scatter" ? "X value (measure)" : "Category / Axis"} hint={type === "scatter" ? "Drop a measure" : "Drop a dimension or date"} onDrop={(e) => onDropWell("x", e)}>
                      {type === "scatter" ? (
                        model.xMeasure && <Chip label={label(model.xMeasure)} tone="measure" onRemove={() => patch((m) => ({ ...m, xMeasure: null }))} />
                      ) : (
                        <>
                          {model.xDim && <Chip label={label(model.xDim)} onRemove={() => patch((m) => ({ ...m, xDim: null }))} />}
                          {model.xTime && <Chip label={`${label(model.xTime.dim)}`} onRemove={() => patch((m) => ({ ...m, xTime: null }))} />}
                        </>
                      )}
                    </Well>
                  )}
                  <Well name={isKpi ? "Measure" : type === "scatter" ? "Y value (measure)" : "Values"} hint="Drop measures" onDrop={(e) => onDropWell("y", e)}>
                    {model.y.map((d) => (
                      <Chip key={d} label={label(d)} tone="measure" onRemove={() => patch((m) => ({ ...m, y: m.y.filter((x) => x !== d) }))} />
                    ))}
                  </Well>
                  {type === "combo" && (
                    <Well name="Line values (second axis)" hint="Drop a measure" onDrop={(e) => onDropWell("y2", e)}>
                      {model.y2.map((d) => (
                        <Chip key={d} label={label(d)} tone="measure" onRemove={() => patch((m) => ({ ...m, y2: m.y2.filter((x) => x !== d) }))} />
                      ))}
                    </Well>
                  )}
                  {showSeries && type !== "pie" && type !== "donut" && type !== "waterfall" && (
                    <Well name="Series / Legend" hint="Drop a dimension to split by" onDrop={(e) => onDropWell("series", e)}>
                      {model.series && <Chip label={label(model.series)} onRemove={() => patch((m) => ({ ...m, series: null }))} />}
                    </Well>
                  )}
                </>
              )}

              <Well name="Time" hint="Range and grouping">
                <div className="flex w-full flex-wrap items-center gap-1.5">
                  <select aria-label="Time grain" className={`${fieldCls} !w-auto`} value={model.xTime?.grain ?? ""} disabled={isKpi ? false : !model.xTime && !(ds?.dimensions.some((d) => d.type === "time"))} onChange={(e) => {
                    const g = e.target.value as Grain | ""
                    const td = ds?.default_time_dimension ?? ds?.dimensions.find((d) => d.type === "time")?.id
                    patch((m) => (g === "" ? { ...m, xTime: null } : { ...m, xTime: { dim: m.xTime?.dim ?? (td as string), grain: g }, ...(m.xDim && !isKpi && !isTable && !m.series && type !== "scatter" ? { series: m.xDim, xDim: null } : {}) }))
                  }}>
                    <option value="">{isKpi ? "Single total" : "No time grouping"}</option>
                    {GRAINS.map((g) => (
                      <option key={g} value={g}>
                        By {g}
                      </option>
                    ))}
                  </select>
                  <input type="date" aria-label="From date" className={`${fieldCls} !w-[8.5rem]`} value={model.range.from} onChange={(e) => patch((m) => ({ ...m, range: { ...m.range, from: e.target.value } }))} />
                  <span className="text-xs text-muted-foreground">to</span>
                  <input type="date" aria-label="To date" className={`${fieldCls} !w-[8.5rem]`} value={model.range.to} onChange={(e) => patch((m) => ({ ...m, range: { ...m.range, to: e.target.value } }))} />
                </div>
                <div className="flex flex-wrap gap-1">
                  {(["3m", "6m", "12m", "ytd", "all"] as const).map((p) => (
                    <button key={p} type="button" className="rounded border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground hover:border-primary/50" onClick={() => patch((m) => ({ ...m, range: presetRange(p), rangeDim: m.rangeDim ?? ds?.default_time_dimension ?? null }))}>
                      {p === "all" ? "All time" : p === "ytd" ? "Year to date" : `Last ${p.replace("m", " months")}`}
                    </button>
                  ))}
                </div>
                {model.xTime && (ds?.dimensions.filter((d) => d.type === "time").length ?? 0) > 1 && (
                  <select aria-label="Date field" className={fieldCls} value={model.xTime.dim} onChange={(e) => patch((m) => ({ ...m, xTime: m.xTime ? { ...m.xTime, dim: e.target.value } : null }))}>
                    {ds?.dimensions.filter((d) => d.type === "time").map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.label}
                      </option>
                    ))}
                  </select>
                )}
              </Well>

              <Well name="Filters" hint="Narrow the data">
                <div className="w-full space-y-1.5">
                  {model.filters.map((f, i) => (
                    <FilterRow key={i} f={f} fields={selectableFilter} onChange={(nf) => patch((m) => ({ ...m, filters: m.filters.map((x, j) => (j === i ? nf : x)) }))} onRemove={() => patch((m) => ({ ...m, filters: m.filters.filter((_, j) => j !== i) }))} />
                  ))}
                  <Button size="sm" variant="outline" className="h-7 text-xs" disabled={!selectableFilter.length || model.filters.length >= 20} onClick={() => patch((m) => ({ ...m, filters: [...m.filters, { field: (selectableFilter.find((d) => d.type === "category") ?? selectableFilter[0]).id, op: "eq", value: "" }] }))}>
                    + Add filter
                  </Button>
                </div>
              </Well>

              {!isKpi && (
                <Well name="Sort and limit" hint="">
                  <select aria-label="Sort field" className={`${fieldCls} !w-auto`} value={model.sort?.field ?? ""} onChange={(e) => patch((m) => ({ ...m, sort: e.target.value ? { field: e.target.value, dir: m.sort?.dir ?? "desc" } : null }))}>
                    <option value="">Default order</option>
                    {[...model.y, ...model.y2, ...(model.xDim ? [model.xDim] : []), ...(model.series ? [model.series] : []), ...model.extraDims].map((f) => (
                      <option key={f} value={f}>
                        {label(f)}
                      </option>
                    ))}
                  </select>
                  <select aria-label="Sort direction" className={`${fieldCls} !w-auto`} disabled={!model.sort} value={model.sort?.dir ?? "desc"} onChange={(e) => patch((m) => (m.sort ? { ...m, sort: { ...m.sort, dir: e.target.value as "asc" | "desc" } } : m))}>
                    <option value="desc">Descending</option>
                    <option value="asc">Ascending</option>
                  </select>
                  <label className="flex items-center gap-1 text-xs text-muted-foreground">
                    Top
                    <input type="number" min={1} max={1000} aria-label="Row limit" className={`${fieldCls} !w-20`} value={model.limit} onChange={(e) => patch((m) => ({ ...m, limit: Number(e.target.value) || 500 }))} />
                  </label>
                </Well>
              )}
            </div>
          ) : (
            <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">Choose a dataset on the left to begin.</p>
          )}
        </div>

        {/* PREVIEW + FORMAT */}
        <div className="min-h-0 space-y-3 overflow-y-auto pr-1">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Preview (live data)</div>
          <div className="relative h-72 rounded-md border border-border p-3" style={{ background: theme.palette.background, color: theme.palette.text }}>
            {preview.loading && <Loader2 className="absolute right-2 top-2 h-4 w-4 animate-spin text-slate-400" />}
            {preview.error ? (
              <div className="flex h-full items-center justify-center p-4 text-center text-sm text-red-600">{preview.error}</div>
            ) : !spec ? (
              <div className="flex h-full items-center justify-center p-4 text-center text-sm text-slate-500">{err ?? "Configure the wells to see a preview"}</div>
            ) : preview.res && preview.res.rows.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-slate-500">No data yet for this selection</div>
            ) : preview.res ? (
              previewBlock ? (
                <ChartView block={previewBlock} res={preview.res} theme={theme} thumb={false} />
              ) : previewTable ? (
                <div className="h-full overflow-auto">
                  <TableView block={previewTable} res={preview.res} theme={theme} thumb={false} />
                </div>
              ) : previewKpi ? (
                <div className="mx-auto h-40 max-w-xs">
                  <KpiView block={previewKpi} data={{ pv: preview.res }} theme={theme} cover={false} />
                </div>
              ) : null
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-slate-500">Loading…</div>
            )}
          </div>
          {preview.res && (
            <p className="text-[11px] text-muted-foreground">
              {preview.res.meta.row_count} row(s){preview.res.meta.truncated ? " (truncated by limit)" : ""} · {ds?.label} · as of {new Date(preview.res.meta.generated_at).toLocaleString("en-ZA")}
            </p>
          )}

          <div className="space-y-3 rounded-md border border-border p-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Format</div>
            {isKpi ? (
              <>
                <Field label="Label" htmlFor="kb-label">
                  <input id="kb-label" className={fieldCls} value={kLabel} onChange={(e) => setKLabel(e.target.value)} placeholder={model?.y[0] ? label(model.y[0]) : "KPI label"} />
                </Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Show" htmlFor="kb-stat" hint={kStat !== "total" && !model?.xTime ? "Needs a time grain above to have periods" : undefined}>
                    <select id="kb-stat" className={fieldCls} value={kStat} onChange={(e) => setKStat(e.target.value)}>
                      {KPI_STATS.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Comparison" htmlFor="kb-delta">
                    <select id="kb-delta" className={fieldCls} value={kDelta} onChange={(e) => setKDelta(e.target.value)}>
                      <option value="">None</option>
                      <option value="delta_pct">% change vs previous period</option>
                      <option value="delta">Change vs previous period</option>
                    </select>
                  </Field>
                  <Field label="Number format" htmlFor="kb-fmt">
                    <select id="kb-fmt" className={fieldCls} value={kFormat} onChange={(e) => setKFormat(e.target.value)}>
                      <option value="">Automatic</option>
                      <option value="currency">Currency</option>
                      <option value="currency_compact">Currency (compact)</option>
                      <option value="number">Number</option>
                      <option value="number_compact">Number (compact)</option>
                      <option value="percent">Percent</option>
                      <option value="duration">Duration</option>
                    </select>
                  </Field>
                  <Field label="Good direction" htmlFor="kb-good">
                    <select id="kb-good" className={fieldCls} value={kGood} onChange={(e) => setKGood(e.target.value as "up" | "down")}>
                      <option value="up">Up is good</option>
                      <option value="down">Down is good</option>
                    </select>
                  </Field>
                </div>
                <Field label="Caption" htmlFor="kb-cap">
                  <input id="kb-cap" className={fieldCls} value={kCaption} maxLength={200} onChange={(e) => setKCaption(e.target.value)} />
                </Field>
              </>
            ) : (
              <>
                <Field label="Title" htmlFor="cb-title">
                  <input id="cb-title" className={fieldCls} value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
                </Field>
                {isTable ? (
                  <Field label="Rows shown" htmlFor="tb-rows">
                    <input id="tb-rows" type="number" min={1} max={50} className={fieldCls} value={maxRows} onChange={(e) => setMaxRows(Math.max(1, Math.min(50, Number(e.target.value) || 10)))} />
                  </Field>
                ) : (
                  <>
                    <div className="grid grid-cols-2 gap-2">
                      <Field label="X axis title" htmlFor="cb-xt">
                        <input id="cb-xt" className={fieldCls} value={axis.x_title ?? ""} onChange={(e) => setAxis({ ...axis, x_title: e.target.value })} />
                      </Field>
                      <Field label="Y axis title" htmlFor="cb-yt">
                        <input id="cb-yt" className={fieldCls} value={axis.y_title ?? ""} onChange={(e) => setAxis({ ...axis, y_title: e.target.value })} />
                      </Field>
                      <Field label="Y format" htmlFor="cb-yf">
                        <select id="cb-yf" className={fieldCls} value={axis.y_format ?? ""} onChange={(e) => setAxis({ ...axis, y_format: (e.target.value || null) as never })}>
                          <option value="">From measure</option>
                          <option value="currency_zar">Currency (R)</option>
                          <option value="number">Number</option>
                          <option value="percent">Percent</option>
                          <option value="duration">Duration</option>
                        </select>
                      </Field>
                      <Field label="Category order" htmlFor="cb-sort">
                        <select id="cb-sort" className={fieldCls} value={axis.sort ?? "data"} onChange={(e) => setAxis({ ...axis, sort: e.target.value as never })}>
                          <option value="data">As returned</option>
                          <option value="value_desc">Largest first</option>
                          <option value="value_asc">Smallest first</option>
                        </select>
                      </Field>
                      <Field label="Y min" htmlFor="cb-ymin">
                        <input id="cb-ymin" type="number" className={fieldCls} value={axis.y_min ?? ""} onChange={(e) => setAxis({ ...axis, y_min: e.target.value === "" ? null : Number(e.target.value) })} />
                      </Field>
                      <Field label="Y max" htmlFor="cb-ymax">
                        <input id="cb-ymax" type="number" className={fieldCls} value={axis.y_max ?? ""} onChange={(e) => setAxis({ ...axis, y_max: e.target.value === "" ? null : Number(e.target.value) })} />
                      </Field>
                      <Field label="Legend" htmlFor="cb-leg">
                        <select id="cb-leg" className={fieldCls} value={legend} onChange={(e) => setLegend(e.target.value as never)}>
                          <option value="bottom">Bottom</option>
                          <option value="top">Top</option>
                          <option value="right">Right</option>
                          <option value="none">Hidden</option>
                        </select>
                      </Field>
                      <label className="flex items-end gap-2 pb-1 text-xs">
                        <input type="checkbox" checked={labels} onChange={(e) => setLabels(e.target.checked)} /> Data labels
                      </label>
                    </div>
                    <div>
                      <div className="mb-1 flex items-center justify-between text-xs">
                        <span className="font-medium text-muted-foreground">Colours</span>
                        <label className="flex items-center gap-1.5">
                          <input type="checkbox" checked={custom.length > 0} onChange={(e) => setCustom(e.target.checked ? [...theme.palette.chart] : [])} /> Override brand palette
                        </label>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {(custom.length ? custom : theme.palette.chart).map((c, i) =>
                          custom.length ? (
                            <input key={i} type="color" aria-label={`Series colour ${i + 1}`} value={c} onChange={(e) => setCustom(custom.map((x, j) => (j === i ? e.target.value.toUpperCase() : x)))} className="h-7 w-8 cursor-pointer rounded border border-border bg-transparent p-0.5" />
                          ) : (
                            <span key={i} className="h-6 w-6 rounded border border-border" style={{ background: c }} title={`Brand chart colour ${i + 1}`} />
                          ),
                        )}
                      </div>
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </Modal>
  )
}

/** KPI specs need grain only when a period statistic is shown; the time well decides, nothing to rewrite here. */
function kpiModel(m: BuilderModel, _isKpi: boolean, _stat: string, _delta: string): BuilderModel {
  return m
}

function FieldGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-3">
      <div className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {title === "Measures" ? <TrendingUp className="h-3 w-3" /> : <Hash className="h-3 w-3" />} {title}
      </div>
      <div className="space-y-0.5">{children}</div>
    </div>
  )
}

function FieldItem({ id, label, sub, kind, onAdd, title }: { id: string; label: string; sub: string; kind: "measure" | "dimension" | "time"; onAdd: () => void; title?: string }) {
  return (
    <div
      draggable
      onDragStart={(e) => e.dataTransfer.setData("text/plain", `bi-field:${kind}:${id}`)}
      className="group flex items-center gap-1 rounded px-1 py-1 hover:bg-muted/60"
      title={title}
    >
      <GripVertical className="h-3.5 w-3.5 shrink-0 cursor-grab text-muted-foreground/60" aria-hidden />
      <button type="button" onClick={onAdd} className="min-w-0 flex-1 truncate text-left text-foreground" aria-label={`Add ${label}`}>
        {label}
      </button>
      <span className="shrink-0 text-[10px] text-muted-foreground">{sub}</span>
    </div>
  )
}

function Well({ name, hint, children, onDrop }: { name: string; hint: string; children: ReactNode; onDrop?: (e: React.DragEvent) => void }) {
  const [over, setOver] = useState(false)
  const empty = !Array.isArray(children) ? !children : (children as ReactNode[]).every((c) => !c)
  return (
    <div
      onDragOver={(e) => {
        if (onDrop) {
          e.preventDefault()
          setOver(true)
        }
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        setOver(false)
        onDrop?.(e)
      }}
      className={cn("rounded-md border border-dashed p-2 transition-colors", over ? "border-primary bg-primary/10" : "border-border")}
    >
      <div className="mb-1 text-[11px] font-semibold text-muted-foreground">{name}</div>
      <div className="flex min-h-7 flex-wrap items-center gap-1.5">
        {children}
        {empty && hint && <span className="text-[11px] text-muted-foreground/70">{hint}</span>}
      </div>
    </div>
  )
}

function Chip({ label, onRemove, tone }: { label: string; onRemove: () => void; tone?: "measure" }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs", tone === "measure" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : "border-sky-500/40 bg-sky-500/10 text-sky-300")}>
      {label}
      <button type="button" aria-label={`Remove ${label}`} onClick={onRemove} className="rounded-full hover:bg-white/10">
        <X className="h-3 w-3" />
      </button>
    </span>
  )
}

function FilterRow({ f, fields, onChange, onRemove }: { f: QueryFilter; fields: DatasetDef["dimensions"]; onChange: (f: QueryFilter) => void; onRemove: () => void }) {
  const dim = fields.find((d) => d.id === f.field) ?? fields[0]
  const ops = opsForType(dim?.type ?? "category")
  const type = dim?.type ?? "category"
  const nullary = f.op === "is_null" || f.op === "not_null"
  const multi = f.op === "in" || f.op === "not_in"
  const between = f.op === "between"
  const parse = (s: string): unknown => (type === "number" ? (s.trim() === "" || Number.isNaN(Number(s)) ? s : Number(s)) : s)
  const arr = Array.isArray(f.value) ? (f.value as unknown[]) : []
  const inputType = type === "time" ? "date" : type === "number" ? "number" : "text"
  const valueEl = nullary ? null : between ? (
    <>
      <input aria-label="From" type={inputType} className={`${fieldCls} !w-24`} value={String(arr[0] ?? "")} onChange={(e) => onChange({ ...f, value: [parse(e.target.value), arr[1] ?? ""] })} />
      <input aria-label="To" type={inputType} className={`${fieldCls} !w-24`} value={String(arr[1] ?? "")} onChange={(e) => onChange({ ...f, value: [arr[0] ?? "", parse(e.target.value)] })} />
    </>
  ) : multi ? (
    <input aria-label="Values, comma separated" placeholder="a, b, c" className={`${fieldCls} min-w-24 flex-1`} value={arr.join(", ")} onChange={(e) => onChange({ ...f, value: e.target.value.split(",").map((s) => parse(s.trim())).filter((v) => v !== "") })} />
  ) : (
    <input aria-label="Value" type={inputType} className={`${fieldCls} min-w-24 flex-1`} value={String(f.value ?? "")} onChange={(e) => onChange({ ...f, value: parse(e.target.value) })} />
  )
  return (
    <div className="flex flex-wrap items-center gap-1">
      <select aria-label="Filter field" className={`${fieldCls} !w-auto max-w-[9rem]`} value={f.field} onChange={(e) => onChange({ field: e.target.value, op: "eq", value: "" })}>
        {fields.map((d) => (
          <option key={d.id} value={d.id}>
            {d.label}
          </option>
        ))}
      </select>
      <select
        aria-label="Filter operator"
        className={`${fieldCls} !w-auto`}
        value={f.op}
        onChange={(e) => {
          const op = e.target.value
          const v = op === "between" ? ["", ""] : op === "in" || op === "not_in" ? [] : op === "is_null" || op === "not_null" ? undefined : ""
          onChange({ field: f.field, op, ...(v === undefined ? {} : { value: v }) })
        }}
      >
        {ops.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>
      {valueEl}
      <button type="button" aria-label="Remove filter" onClick={onRemove} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-red-400">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}
