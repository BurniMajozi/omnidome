"use client"

import { Fragment, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  XAxis,
  YAxis,
} from "recharts"
import { AlertTriangle, BarChart3, Loader2, Plus, RefreshCw } from "lucide-react"
import type { Block, ChartBlock, KpiBlock, Slide, TableBlock, TextBlock, Ungrounded } from "@/lib/bi-studio-api"
import { cn } from "@/lib/utils"
import { computeFrames, FOOTER_FRAME, LOGO_FRAME, SLIDE_NUM_FRAME, type SlideFrames } from "./layout"
import { fontStack, onColor, safeDataImage, safeImageUrl, shapeColor, type Theme } from "./theme"
import { compactByMeasure, DASH, formatByMeasure, formatNumber, resolveRef, splitTokens, type DataMap, type TokenOutcome } from "./tokens"
import { prepareChart, waterfallBars, type ChartData } from "./chart-data"
import type { QState } from "./use-deck-data"

export const SLIDE_W = 960
export const SLIDE_H = 540

export type RenderMode = "view" | "edit" | "thumb"

export interface SlideRenderProps {
  slide: Slide
  index: number
  total: number
  theme: Theme
  states: Record<string, QState>
  data: DataMap
  mode?: RenderMode
  asOf?: string | null
  datasetLabel?: (id: string) => string
  selectedId?: string | null
  onSelect?: (blockId: string | null) => void
  onRetry?: (alias: string) => void
  editingId?: string | null
  onStartEdit?: (blockId: string) => void
  renderEditor?: (b: TextBlock) => ReactNode
  onAddBlock?: (type: "chart" | "kpi" | "table" | "text") => void
  warnings?: Record<string, Ungrounded[]>
}

const aliasOf = (b: Block) => (b.type === "chart" || b.type === "table" ? (b.query ? b.id : (b.query_ref ?? "")) : "")

/** Scales the fixed 960x540 slide to the width of its container. */
export function SlideFrame({ children, className, style }: { children: ReactNode; className?: string; style?: CSSProperties }) {
  const ref = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0.5)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(() => setScale(el.clientWidth / SLIDE_W))
    ro.observe(el)
    setScale(el.clientWidth / SLIDE_W)
    return () => ro.disconnect()
  }, [])
  return (
    <div ref={ref} className={cn("relative w-full overflow-hidden", className)} style={{ aspectRatio: "16 / 9", ...style }}>
      <div style={{ width: SLIDE_W, height: SLIDE_H, transform: `scale(${scale})`, transformOrigin: "top left", position: "absolute", left: 0, top: 0 }}>
        {children}
      </div>
    </div>
  )
}

const pct = (f: { x: number; y: number; w: number; h: number }): CSSProperties => ({
  position: "absolute",
  left: `${f.x}%`,
  top: `${f.y}%`,
  width: `${f.w}%`,
  height: `${f.h}%`,
})

export function TokenChip({ t, tone }: { t: TokenOutcome; tone: "light" | "dark" }) {
  const ok = t.ok
  return (
    <span
      title={ok ? `Live value from data: {{${t.raw}}}` : (t.reason ?? "Could not resolve")}
      className={cn("rounded px-1 font-semibold", ok ? "bg-black/10" : "bg-amber-400/30 text-amber-700")}
      style={ok && tone === "dark" ? { background: "rgba(255,255,255,0.18)" } : undefined}
      data-token={t.raw}
    >
      {t.display}
    </span>
  )
}

export function RichText({ text, data, tone = "light" }: { text: string; data: DataMap; tone?: "light" | "dark" }) {
  return (
    <>
      {splitTokens(text, data).map((s, i) => (s.kind === "text" ? <Fragment key={i}>{s.text}</Fragment> : <TokenChip key={i} t={s} tone={tone} />))}
    </>
  )
}

// ── block bodies ─────────────────────────────────────────────────────
function Note({ icon, children, tone }: { icon?: ReactNode; children: ReactNode; tone: string }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-center" style={{ color: tone, opacity: 0.75, fontSize: 14 }}>
      {icon}
      {children}
    </div>
  )
}

function stateGate(
  b: ChartBlock | TableBlock,
  st: QState | undefined,
  theme: Theme,
  mode: RenderMode,
  onRetry?: (a: string) => void,
): ReactNode | null {
  const alias = aliasOf(b)
  const tone = theme.palette.text
  if (!st || (st.status === "loading" && !st.result)) {
    return (
      <Note tone={tone} icon={mode === "thumb" ? null : <Loader2 className="animate-spin" size={22} />}>
        {mode === "thumb" ? "" : "Loading data…"}
      </Note>
    )
  }
  if (st.status === "error" && !st.result) {
    return (
      <Note tone="#B42318" icon={<AlertTriangle size={22} />}>
        <span style={{ maxWidth: 360 }}>{st.error ?? "Query failed"}</span>
        {mode !== "thumb" && onRetry && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onRetry(alias)
            }}
            className="inline-flex items-center gap-1 rounded border border-current px-2 py-0.5 text-xs"
          >
            <RefreshCw size={12} /> Retry
          </button>
        )}
      </Note>
    )
  }
  if (st.result && st.result.rows.length === 0) {
    return (
      <Note tone={tone} icon={<BarChart3 size={22} />}>
        No data yet
      </Note>
    )
  }
  return null
}

export function ChartView({ block, res, theme, thumb }: { block: ChartBlock; res: NonNullable<QState["result"]>; theme: Theme; thumb: boolean }) {
  const cd = prepareChart(res, block.chart_type, block.series ?? {}, block.axis)
  if (!cd) return <Note tone={theme.palette.text}>Choose a value to plot</Note>
  const colors = block.colors && block.colors.length ? block.colors : theme.palette.chart
  const color = (i: number) => colors[i % colors.length]
  const txt = theme.palette.text
  const axisStyle = { fontSize: 11, fill: txt }
  const yFmt = (v: number) => compactByMeasure(v, cd.yFormat)
  const legendPos = block.legend ?? "bottom"
  const legend =
    legendPos === "none" || thumb ? null : (
      <Legend
        verticalAlign={legendPos === "top" ? "top" : "bottom"}
        align={legendPos === "right" ? "right" : "center"}
        layout={legendPos === "right" ? "vertical" : "horizontal"}
        wrapperStyle={{ fontSize: 11, color: txt }}
      />
    )
  const common = { margin: { top: 8, right: 12, bottom: 4, left: 0 } }
  const t = block.chart_type

  if (t === "pie" || t === "donut") {
    const s = cd.series[0]
    const rows = cd.categories.map((c, i) => ({ name: c, value: Math.max(0, s?.values[i] ?? 0) })).filter((r) => r.value > 0)
    return (
      <ResponsiveContainer width="100%" height="100%" minWidth={40} minHeight={40}>
        <PieChart>
          <Pie
            data={rows}
            dataKey="value"
            nameKey="name"
            innerRadius={t === "donut" ? "55%" : 0}
            outerRadius="85%"
            isAnimationActive={false}
            label={block.labels && !thumb ? (e) => `${e.name}` : false}
            stroke={theme.palette.background}
          >
            {rows.map((_r, i) => (
              <Cell key={i} fill={color(i)} />
            ))}
          </Pie>
          {legend}
        </PieChart>
      </ResponsiveContainer>
    )
  }

  if (t === "scatter") {
    return (
      <ResponsiveContainer width="100%" height="100%" minWidth={40} minHeight={40}>
        <ScatterChart {...common}>
          <CartesianGrid stroke={txt} strokeOpacity={0.12} />
          <XAxis type="number" dataKey="x" name={cd.measureLabels.__x} tick={axisStyle} tickFormatter={(v) => compactByMeasure(v)} />
          <YAxis type="number" dataKey="y" name={cd.measureLabels.__y} tick={axisStyle} tickFormatter={yFmt} />
          {(cd.points ?? []).map((p, i) => (
            <Scatter key={p.name} name={p.name} data={p.data} fill={color(i)} isAnimationActive={false} />
          ))}
          {(cd.points?.length ?? 0) > 1 ? legend : null}
        </ScatterChart>
      </ResponsiveContainer>
    )
  }

  // category charts → row objects
  const rows = cd.categories.map((c, i) => {
    const o: Record<string, string | number | null> = { __x: c }
    cd.series.forEach((s, si) => (o[`s${si}`] = s.values[i]))
    return o
  })
  const keyOf = (i: number) => `s${i}`
  const labelFmt = block.labels && !thumb ? { position: "top" as const, fontSize: 10, fill: txt, formatter: (v: unknown) => (typeof v === "number" ? compactByMeasure(v, cd.yFormat) : "") } : undefined
  const yAxis = (
    <YAxis
      tick={axisStyle}
      tickFormatter={yFmt}
      width={48}
      domain={[block.axis?.y_min ?? (t === "line" ? "auto" : 0), block.axis?.y_max ?? "auto"]}
      label={block.axis?.y_title && !thumb ? { value: block.axis.y_title, angle: -90, position: "insideLeft", style: { fontSize: 11, fill: txt } } : undefined}
    />
  )
  const xAxis = <XAxis dataKey="__x" tick={axisStyle} interval="preserveStartEnd" label={block.axis?.x_title && !thumb ? { value: block.axis.x_title, position: "insideBottom", offset: -2, style: { fontSize: 11, fill: txt } } : undefined} />
  const grid = <CartesianGrid stroke={txt} strokeOpacity={0.12} vertical={false} />

  if (t === "waterfall") {
    const wf = waterfallBars(cd.series[0]?.values ?? [])
    const wrows = rows.map((r, i) => ({ ...r, ...wf[i] }))
    return (
      <ResponsiveContainer width="100%" height="100%" minWidth={40} minHeight={40}>
        <BarChart data={wrows} {...common}>
          {grid}
          {xAxis}
          {yAxis}
          <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
          <Bar dataKey="up" stackId="w" fill={color(2)} isAnimationActive={false} name="Increase" />
          <Bar dataKey="down" stackId="w" fill={color(3)} isAnimationActive={false} name="Decrease" />
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (t === "bar") {
    return (
      <ResponsiveContainer width="100%" height="100%" minWidth={40} minHeight={40}>
        <BarChart data={rows} layout="vertical" {...common}>
          <CartesianGrid stroke={txt} strokeOpacity={0.12} horizontal={false} />
          <XAxis type="number" tick={axisStyle} tickFormatter={yFmt} domain={[block.axis?.y_min ?? 0, block.axis?.y_max ?? "auto"]} />
          <YAxis type="category" dataKey="__x" tick={axisStyle} width={90} />
          {cd.series.map((s, i) => (
            <Bar key={i} dataKey={keyOf(i)} name={s.name} fill={color(i)} isAnimationActive={false}>
              {labelFmt && <LabelList dataKey={keyOf(i)} {...labelFmt} position="right" />}
            </Bar>
          ))}
          {legend}
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (t === "line") {
    return (
      <ResponsiveContainer width="100%" height="100%" minWidth={40} minHeight={40}>
        <LineChart data={rows} {...common}>
          {grid}
          {xAxis}
          {yAxis}
          {cd.series.map((s, i) => (
            <Line key={i} type="monotone" dataKey={keyOf(i)} name={s.name} stroke={color(i)} strokeWidth={2.5} dot={rows.length < 25} isAnimationActive={false}>
              {labelFmt && <LabelList dataKey={keyOf(i)} {...labelFmt} />}
            </Line>
          ))}
          {legend}
        </LineChart>
      </ResponsiveContainer>
    )
  }

  if (t === "area") {
    return (
      <ResponsiveContainer width="100%" height="100%" minWidth={40} minHeight={40}>
        <AreaChart data={rows} {...common}>
          {grid}
          {xAxis}
          {yAxis}
          {cd.series.map((s, i) => (
            <Area key={i} type="monotone" dataKey={keyOf(i)} name={s.name} stroke={color(i)} fill={color(i)} fillOpacity={0.25} strokeWidth={2} isAnimationActive={false} />
          ))}
          {legend}
        </AreaChart>
      </ResponsiveContainer>
    )
  }

  // column, stacked_column, combo
  const stacked = t === "stacked_column"
  const hasY2 = cd.series.some((s) => s.axis === "y2")
  return (
    <ResponsiveContainer width="100%" height="100%" minWidth={40} minHeight={40}>
      <ComposedChart data={rows} {...common}>
        {grid}
        {xAxis}
        {yAxis}
        {hasY2 && <YAxis yAxisId="y2" orientation="right" tick={axisStyle} width={48} tickFormatter={(v: number) => compactByMeasure(v, cd.y2Format)} />}
        {cd.series.map((s, i) =>
          s.axis === "y2" ? (
            <Line key={i} yAxisId="y2" type="monotone" dataKey={keyOf(i)} name={s.name} stroke={color(i)} strokeWidth={2.5} isAnimationActive={false} />
          ) : (
            <Bar key={i} dataKey={keyOf(i)} name={s.name} fill={color(i)} stackId={stacked ? "a" : undefined} isAnimationActive={false}>
              {labelFmt && !stacked && <LabelList dataKey={keyOf(i)} {...labelFmt} />}
            </Bar>
          ),
        )}
        {legend}
      </ComposedChart>
    </ResponsiveContainer>
  )
}

export function TableView({ block, res, theme, thumb }: { block: TableBlock; res: NonNullable<QState["result"]>; theme: Theme; thumb: boolean }) {
  const cols = (block.columns.length ? block.columns : res.columns.map((c) => ({ field: c.id, label: c.label, format: null }))).filter((c) =>
    res.columns.some((x) => x.id === c.field),
  )
  const max = block.max_rows ?? 10
  const rows = res.rows.slice(0, max)
  return (
    <table className="w-full border-collapse" style={{ fontSize: thumb ? 12 : 13, color: theme.palette.text }}>
      <thead>
        <tr>
          {cols.map((c) => {
            const rc = res.columns.find((x) => x.id === c.field)!
            return (
              <th
                key={c.field}
                className="px-2 py-1 text-left font-semibold"
                style={{ background: theme.palette.secondary, color: onColor(theme.palette.secondary), textAlign: rc.kind === "measure" ? "right" : "left" }}
              >
                {c.label || rc.label}
              </th>
            )
          })}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, ri) => (
          <tr key={ri} style={{ background: ri % 2 ? `${theme.palette.text}0D` : "transparent" }}>
            {cols.map((c) => {
              const ci = res.columns.findIndex((x) => x.id === c.field)
              const rc = res.columns[ci]
              const v = r[ci]
              return (
                <td key={c.field} className="px-2 py-1" style={{ textAlign: rc.kind === "measure" ? "right" : "left", borderBottom: `1px solid ${theme.palette.text}22` }}>
                  {rc.kind === "measure" ? formatByMeasure(v, c.format === "currency" ? "currency_zar" : rc.format) : v === null ? DASH : String(v)}
                </td>
              )
            })}
          </tr>
        ))}
      </tbody>
      {res.rows.length > max && (
        <tfoot>
          <tr>
            <td colSpan={cols.length} className="px-2 py-1 text-right opacity-60" style={{ fontSize: 11 }}>
              Showing {max} of {res.rows.length} rows
            </td>
          </tr>
        </tfoot>
      )}
    </table>
  )
}

export function KpiView({ block, data, theme, cover }: { block: KpiBlock; data: DataMap; theme: Theme; cover: boolean }) {
  const v = resolveRef(block.value_ref, block.format, data)
  const d = block.delta_ref ? resolveRef(block.delta_ref, block.delta_format, data) : null
  const dv = d?.ok ? (d.value ?? 0) : 0
  const dir = !d?.ok ? "flat" : dv > 0 ? "up" : dv < 0 ? "down" : "flat"
  const good = dir === "flat" ? null : dir === (block.good_direction ?? "up")
  const fg = cover ? onColor(theme.palette.secondary) : theme.palette.text
  return (
    <div
      className="flex h-full w-full flex-col justify-center rounded-lg px-4 py-2"
      style={{ background: cover ? "rgba(255,255,255,0.1)" : `${theme.palette.primary}12`, borderLeft: `5px solid ${theme.palette.primary}`, color: fg }}
    >
      <div style={{ fontSize: 13, opacity: 0.75, fontFamily: fontStack(theme.fonts.body) }}>{block.label}</div>
      <div style={{ fontSize: 40, fontWeight: 700, lineHeight: 1.1, fontFamily: fontStack(theme.fonts.heading), color: v.ok ? theme.palette.primary : "#B42318" }} title={v.ok ? undefined : v.reason}>
        {v.display}
      </div>
      {d && (
        <div style={{ fontSize: 14, fontWeight: 600, color: good === null ? fg : good ? "#1A7F4B" : "#B42318" }} title={d.ok ? undefined : d.reason}>
          {dir === "up" ? "▲ " : dir === "down" ? "▼ " : ""}
          {d.display}
        </div>
      )}
      {block.caption && <div style={{ fontSize: 12, opacity: 0.7 }}>{block.caption}</div>}
    </div>
  )
}

function TextView({ block, data, theme, cover }: { block: TextBlock; data: DataMap; theme: Theme; cover: boolean }) {
  const fg = cover ? onColor(theme.palette.secondary) : theme.palette.text
  const role = block.role ?? "body"
  const size = role === "caption" ? 13 : role === "callout" ? 24 : role === "quote" ? 22 : cover ? 22 : 18
  const style: CSSProperties = {
    color: role === "callout" && !cover ? theme.palette.primary : fg,
    fontSize: size,
    fontFamily: fontStack(role === "callout" ? theme.fonts.heading : theme.fonts.body),
    textAlign: block.align ?? "left",
    fontStyle: role === "quote" ? "italic" : undefined,
    opacity: role === "caption" ? 0.8 : 1,
    lineHeight: 1.35,
    borderLeft: role === "quote" ? `4px solid ${theme.palette.accent}` : undefined,
    paddingLeft: role === "quote" ? 12 : undefined,
  }
  return (
    <div style={style} className="h-full w-full overflow-hidden">
      {block.items.map((it, i) => (
        <div key={i} style={{ paddingLeft: (it.level ?? 0) * 22 + (it.bullet ? 18 : 0), position: "relative", fontWeight: it.bold ? 700 : undefined, marginBottom: 4 }}>
          {it.bullet && <span style={{ position: "absolute", left: (it.level ?? 0) * 22, color: theme.palette.accent }}>{"•"}</span>}
          <RichText text={it.text} data={data} tone={cover ? "dark" : "light"} />
        </div>
      ))}
    </div>
  )
}

function BlockBody({ b, p, cover }: { b: Block; p: SlideRenderProps; cover: boolean }) {
  const mode = p.mode ?? "view"
  const thumb = mode === "thumb"
  switch (b.type) {
    case "text":
      if (p.editingId === b.id && p.renderEditor) return <>{p.renderEditor(b)}</>
      return <TextView block={b} data={p.data} theme={p.theme} cover={cover} />
    case "kpi":
      return <KpiView block={b} data={p.data} theme={p.theme} cover={cover} />
    case "chart":
    case "table": {
      const st = p.states[aliasOf(b)]
      const gate = stateGate(b, st, p.theme, mode, p.onRetry)
      const title = b.title
      const ds = st?.result?.meta.dataset
      const hover = ds ? `Dataset: ${p.datasetLabel?.(ds) ?? ds}${st?.result?.meta.generated_at ? ` · data as of ${new Date(st.result.meta.generated_at).toLocaleString("en-ZA")}` : ""}` : undefined
      return (
        <div className="flex h-full w-full flex-col" title={hover}>
          {title && (
            <div style={{ fontSize: 14, fontWeight: 600, color: p.theme.palette.text, fontFamily: fontStack(p.theme.fonts.heading), marginBottom: 2 }}>{title}</div>
          )}
          <div className="min-h-0 flex-1">
            {gate ??
              (st?.result ? (
                b.type === "chart" ? (
                  <ChartView block={b} res={st.result} theme={p.theme} thumb={thumb} />
                ) : (
                  <TableView block={b} res={st.result} theme={p.theme} thumb={thumb} />
                )
              ) : null)}
          </div>
        </div>
      )
    }
    case "image": {
      const src = b.source.kind === "brand_logo" ? safeDataImage(p.theme.logo_data_url) : safeImageUrl(b.source.url)
      if (!src) return <Note tone={p.theme.palette.text}>{b.source.kind === "brand_logo" ? "No brand logo set" : "Invalid image URL"}</Note>
      // eslint-disable-next-line @next/next/no-img-element
      return <img src={src} alt={b.alt ?? ""} style={{ width: "100%", height: "100%", objectFit: b.fit ?? "contain" }} referrerPolicy="no-referrer" />
    }
    case "shape": {
      const c = shapeColor(p.theme, b.color)
      if (b.shape === "divider") return <div style={{ height: 3, background: c, marginTop: "auto", marginBottom: "auto" }} />
      return <div style={{ width: "100%", height: "100%", background: c, borderRadius: b.shape === "accent_bar" ? 2 : 6 }} />
    }
  }
}

function blockLabel(b: Block): string {
  switch (b.type) {
    case "text":
      return "Text block"
    case "kpi":
      return `KPI ${b.label}`
    case "chart":
      return `Chart ${b.title ?? ""}`
    case "table":
      return `Table ${b.title ?? ""}`
    case "image":
      return "Image"
    case "shape":
      return "Shape"
  }
}

export function SlideRenderer(p: SlideRenderProps) {
  const { slide, theme } = p
  const mode = p.mode ?? "view"
  const edit = mode === "edit"
  const frames: SlideFrames = computeFrames(slide)
  const cover = frames.cover
  const bg = cover ? theme.palette.secondary : theme.palette.background
  const fg = cover ? onColor(theme.palette.secondary) : theme.palette.text
  const hasChart = slide.blocks.some((b) => b.type === "chart" || b.type === "table")
  const hasKpi = slide.blocks.some((b) => b.type === "kpi")
  const logo = theme.show_logo ? safeDataImage(theme.logo_data_url) : null
  const showFooter = !cover || slide.layout === "closing"

  return (
    <SlideFrame>
      <div
        style={{ width: SLIDE_W, height: SLIDE_H, background: bg, color: fg, position: "relative", fontFamily: fontStack(theme.fonts.body) }}
        onClick={() => edit && p.onSelect?.(null)}
        data-slide-id={slide.id}
      >
        {cover && <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 14, background: theme.palette.accent }} />}
        {!cover && <div style={{ position: "absolute", left: 0, top: 0, right: 0, height: 6, background: theme.palette.primary }} />}

        <div style={{ ...pct(frames.title), display: "flex", alignItems: cover ? "flex-end" : "center" }}>
          <h2
            style={{
              margin: 0,
              fontFamily: fontStack(theme.fonts.heading),
              fontSize: cover ? 46 : 30,
              fontWeight: 700,
              lineHeight: 1.12,
              color: cover ? fg : theme.palette.secondary,
              textAlign: theme.title_align,
              width: "100%",
            }}
          >
            {slide.title ? <RichText text={slide.title} data={p.data} tone={cover ? "dark" : "light"} /> : edit ? <span style={{ opacity: 0.4 }}>Slide title</span> : null}
          </h2>
        </div>
        {(slide.subtitle || cover) && (slide.subtitle || edit) && (
          <div style={{ ...pct(frames.subtitle), fontSize: cover ? 22 : 15, opacity: 0.8, fontFamily: fontStack(theme.fonts.body) }}>
            {slide.subtitle ? <RichText text={slide.subtitle} data={p.data} tone={cover ? "dark" : "light"} /> : <span style={{ opacity: 0.5 }}>Subtitle</span>}
          </div>
        )}

        {slide.blocks.map((b) => {
          const f = frames.blocks[b.id]
          if (!f) return null
          const selected = edit && p.selectedId === b.id
          const warn = p.warnings?.[b.id]
          return (
            <div
              key={b.id}
              style={{ ...pct(f), outline: selected ? `2px solid ${theme.palette.primary}` : undefined, outlineOffset: 2, cursor: edit ? "pointer" : undefined }}
              className={cn(edit && "[&_svg]:pointer-events-none", edit && !selected && "hover:outline hover:outline-1 hover:outline-dashed hover:outline-offset-2 hover:outline-slate-400")}
              onClick={(e) => {
                if (!edit) return
                e.stopPropagation()
                p.onSelect?.(b.id)
              }}
              onDoubleClick={(e) => {
                if (edit && b.type === "text") {
                  e.stopPropagation()
                  p.onStartEdit?.(b.id)
                }
              }}
              onKeyDown={(e) => {
                if (!edit || (e.target as HTMLElement).tagName === "TEXTAREA") return
                if (e.key === "Enter") {
                  e.preventDefault()
                  p.onSelect?.(b.id)
                  if (b.type === "text") p.onStartEdit?.(b.id)
                }
              }}
              role={edit ? "button" : undefined}
              tabIndex={edit ? 0 : undefined}
              aria-label={edit ? blockLabel(b) : undefined}
              aria-pressed={edit ? selected : undefined}
              data-block-id={b.id}
            >
              <BlockBody b={b} p={p} cover={cover} />
              {edit && warn && warn.length > 0 && (
                <span
                  className="absolute -right-1 -top-3 z-10 inline-flex items-center gap-1 rounded bg-amber-500 px-1.5 py-0.5 text-[11px] font-semibold text-black"
                  title={`Number written outside a data token: ${warn.map((w) => w.literal).join(", ")}`}
                >
                  <AlertTriangle size={11} /> Ungrounded number
                </span>
              )}
            </div>
          )
        })}

        {edit && p.onAddBlock && !hasChart && ["chart_full", "chart_plus_text", "table"].includes(slide.layout) && (
          <PlaceholderButton zone={frames.zones.left ?? frames.zones.main} label={slide.layout === "table" ? "Add table" : "Add chart"} onClick={() => p.onAddBlock?.(slide.layout === "table" ? "table" : "chart")} />
        )}
        {edit && p.onAddBlock && !hasKpi && slide.layout === "kpi_strip" && (
          <PlaceholderButton zone={frames.zones.top} label="Add KPI" onClick={() => p.onAddBlock?.("kpi")} />
        )}

        {logo && !cover && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={logo} alt={theme.company_name || "Logo"} style={{ ...pct(LOGO_FRAME), objectFit: "contain", objectPosition: "right" }} />
        )}
        {logo && cover && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={logo} alt={theme.company_name || "Logo"} style={{ position: "absolute", left: "8%", top: "7%", height: "12%", maxWidth: "20%", objectFit: "contain", background: "rgba(255,255,255,0.92)", padding: 6, borderRadius: 6 }} />
        )}
        {showFooter && (
          <>
            <div style={{ ...pct(FOOTER_FRAME), fontSize: 10, opacity: 0.6, display: "flex", gap: 12, alignItems: "center", overflow: "hidden", whiteSpace: "nowrap" }}>
              {theme.footer_text && <span>{theme.footer_text}</span>}
              {p.asOf && <span>Data as of {new Date(p.asOf).toLocaleString("en-ZA", { dateStyle: "medium", timeStyle: "short" })}</span>}
            </div>
            {theme.slide_numbers && <div style={{ ...pct(SLIDE_NUM_FRAME), fontSize: 11, opacity: 0.6, textAlign: "right" }}>{p.index + 1}</div>}
          </>
        )}
      </div>
    </SlideFrame>
  )
}

function PlaceholderButton({ zone, label, onClick }: { zone: { x: number; y: number; w: number; h: number }; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-slate-400/70 text-slate-500 hover:border-slate-600 hover:text-slate-700"
      style={{ ...pct(zone), fontSize: 15, background: "rgba(0,0,0,0.02)" }}
    >
      <Plus size={26} />
      {label}
    </button>
  )
}

export { formatNumber }
export type { ChartData }
