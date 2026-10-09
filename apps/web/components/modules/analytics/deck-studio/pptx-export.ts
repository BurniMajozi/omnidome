/* eslint-disable @typescript-eslint/no-explicit-any */
import type { Block, ExportBundle, QueryResult, ResolvedBlock, ResolvedSlide, Slide } from "@/lib/bi-studio-api"
import { computeFrames, COVER_SUBTITLE_FRAME, COVER_TITLE_FRAME, SUBTITLE_FRAME, TITLE_FRAME, FOOTER_FRAME, LOGO_FRAME, SLIDE_NUM_FRAME } from "./layout"
import { DEFAULT_PALETTE, isHex, onColor, shapeColor, type Theme } from "./theme"
import { prepareChart, waterfallBars } from "./chart-data"
import { compactByMeasure, formatByMeasure } from "./tokens"

/**
 * Native, editable PowerPoint from POST /decks/{id}/export/json (resolved slides + query data).
 * Charts are real PowerPoint charts (editable data), tables are real tables, text is text.
 */

const W = 10 // inches (16:9)
const H = 5.625
const px = (v: number) => (v / 100) * W
const py = (v: number) => (v / 100) * H
const hex = (c: string | undefined, fb = "000000") => (c && isHex(c) ? c.slice(1).toUpperCase() : fb)
const fr = (f: { x: number; y: number; w: number; h: number }) => ({ x: px(f.x), y: py(f.y), w: px(f.w), h: py(f.h) })

export interface PptxOptions {
  /** brand font name -> font to write when the brand font is not a standard Office font */
  fontFallback?: Record<string, string>
  /** images (https) that could be pre-fetched into data URLs by the caller; others are skipped */
  fetchImage?: (url: string) => Promise<string | null>
}

function themeFrom(bundle: ExportBundle): Theme {
  const t: any = bundle.theme ?? {}
  const kit = bundle.brand_kit
  return {
    palette: { ...DEFAULT_PALETTE, ...(t.palette ?? {}), chart: t.palette?.chart?.length ? t.palette.chart : DEFAULT_PALETTE.chart },
    fonts: { heading: t.fonts?.heading ?? "Calibri", body: t.fonts?.body ?? "Calibri" },
    footer_text: t.footer_text ?? "",
    slide_numbers: t.slide_numbers ?? true,
    company_name: kit?.company_name ?? "",
    logo_data_url: kit?.logo_data_url ?? null,
    show_logo: kit?.layout_prefs?.show_logo ?? true,
    logo_position: kit?.layout_prefs?.logo_position ?? "top_right",
    title_align: kit?.layout_prefs?.title_align === "center" ? "center" : "left",
  }
}

const OFFICE_SAFE = new Set(["Calibri", "Arial", "Georgia", "Times New Roman", "Verdana", "Tahoma", "Trebuchet MS", "Segoe UI", "Cambria", "Helvetica"])

function lighten(h: string, amt: number): string {
  const n = parseInt(h, 16)
  const mix = (c: number) => Math.round(c + (255 - c) * amt)
  const r = mix((n >> 16) & 255)
  const g = mix((n >> 8) & 255)
  const b = mix(n & 255)
  return ((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1).toUpperCase()
}

export async function buildPptx(bundle: ExportBundle, opts: PptxOptions = {}): Promise<any> {
  const mod: any = await import("pptxgenjs")
  const Pptx = mod.default ?? mod
  const pptx = new Pptx()
  pptx.layout = "LAYOUT_16x9"
  pptx.title = bundle.deck.title
  pptx.company = bundle.brand_kit?.company_name ?? ""
  pptx.subject = bundle.as_of ? `Data as of ${bundle.as_of}` : ""
  const theme = themeFrom(bundle)
  const font = (name: string) => {
    const f = opts.fontFallback?.[name]
    return OFFICE_SAFE.has(name) ? name : (f ?? name)
  }
  const heading = font(theme.fonts.heading)
  const body = font(theme.fonts.body)
  const P = theme.palette
  const primary = hex(P.primary)
  const secondary = hex(P.secondary)
  const accent = hex(P.accent)
  const bg = hex(P.background, "FFFFFF")
  const text = hex(P.text, "1B1F2A")
  const logo = theme.show_logo && theme.logo_data_url && /^data:image\/(png|jpeg);base64,/.test(theme.logo_data_url) ? theme.logo_data_url : null
  const asOfLabel = bundle.as_of ? `Data as of ${new Date(bundle.as_of).toLocaleString("en-ZA", { dateStyle: "medium", timeStyle: "short" })}` : ""

  const titleStyle = (cover: boolean) => ({
    name: "title",
    type: "title",
    ...fr(cover ? COVER_TITLE_FRAME : TITLE_FRAME),
    fontFace: heading,
    fontSize: cover ? 36 : 24,
    bold: true,
    color: cover ? hex(onColor(P.secondary)) : secondary,
    align: theme.title_align,
    valign: cover ? "bottom" : "middle",
    margin: 0,
  })
  pptx.defineSlideMaster({
    title: "OD_CONTENT",
    background: { color: bg },
    objects: [
      { rect: { x: 0, y: 0, w: W, h: 0.08, fill: { color: primary } } },
      { placeholder: { options: titleStyle(false), text: "" } },
    ],
    slideNumber: theme.slide_numbers ? { ...fr(SLIDE_NUM_FRAME), fontFace: body, fontSize: 9, color: "808080", align: "right" } : undefined,
  })
  pptx.defineSlideMaster({
    title: "OD_COVER",
    background: { color: secondary },
    objects: [
      { rect: { x: 0, y: 0, w: 0.18, h: H, fill: { color: accent } } },
      { placeholder: { options: titleStyle(true), text: "" } },
    ],
  })

  const addBlocks = async (slide: any, rs: ResolvedSlide, cover: boolean) => {
    const frames = computeFrames(rs as unknown as Slide)
    for (const b of rs.blocks) {
      const f = frames.blocks[b.id]
      if (!f) continue
      const box = fr(f)
      await addBlock(slide, b, box, cover)
    }
  }

  const rowsOf = (alias: string | undefined): QueryResult | undefined => (alias ? bundle.data[alias] : undefined)

  const noData = (slide: any, box: any, msg: string) => slide.addText(msg, { ...box, fontFace: body, fontSize: 12, color: "808080", align: "center", valign: "middle", italic: true })

  async function addBlock(slide: any, b: ResolvedBlock, box: { x: number; y: number; w: number; h: number }, cover: boolean) {
    const fg = cover ? hex(onColor(P.secondary)) : text
    switch (b.type) {
      case "text": {
        const role = b.role ?? "body"
        const size = role === "caption" ? 11 : role === "callout" ? 18 : role === "quote" ? 16 : cover ? 16 : 14
        const items = b.items ?? []
        if (!items.length) return
        slide.addText(
          items.map((it) => ({
            text: it.text,
            options: {
              bullet: it.bullet ? { indent: 14 } : false,
              indentLevel: it.level ?? 0,
              bold: !!it.bold,
              italic: role === "quote",
              breakLine: true,
              color: role === "callout" && !cover ? primary : fg,
              fontFace: role === "callout" ? heading : body,
              fontSize: size,
              paraSpaceAfter: 4,
            },
          })),
          { ...box, align: (b.align as any) ?? "left", valign: "top", margin: 2, fit: "shrink" },
        )
        return
      }
      case "kpi": {
        slide.addShape("rect", { ...box, fill: { color: lighten(primary, 0.88) }, line: { color: lighten(primary, 0.88), width: 0 } })
        slide.addShape("rect", { x: box.x, y: box.y, w: 0.06, h: box.h, fill: { color: primary }, line: { color: primary, width: 0 } })
        const dcol = b.delta_is_good === true ? "1A7F4B" : b.delta_is_good === false ? "B42318" : text
        const arrow = b.delta_direction === "up" ? "▲ " : b.delta_direction === "down" ? "▼ " : ""
        const runs: any[] = [
          { text: b.label ?? "", options: { fontSize: 11, color: text, fontFace: body, breakLine: true } },
          { text: b.value ?? "—", options: { fontSize: 28, bold: true, color: primary, fontFace: heading, breakLine: true } },
        ]
        if (b.delta) runs.push({ text: `${arrow}${b.delta}`, options: { fontSize: 12, bold: true, color: dcol, fontFace: body, breakLine: true } })
        if (b.caption) runs.push({ text: b.caption, options: { fontSize: 9, color: "707070", fontFace: body } })
        slide.addText(runs, { x: box.x + 0.14, y: box.y, w: box.w - 0.18, h: box.h, valign: "middle", margin: 2, fit: "shrink" })
        return
      }
      case "chart": {
        const titleH = b.title ? 0.3 : 0
        if (b.title) slide.addText(b.title, { x: box.x, y: box.y, w: box.w, h: titleH, fontFace: heading, fontSize: 12, bold: true, color: text, margin: 0 })
        const cbox = { x: box.x, y: box.y + titleH, w: box.w, h: box.h - titleH }
        const res = rowsOf(b.query_alias)
        if (!res) return noData(slide, cbox, bundle.query_errors?.[b.query_alias ?? ""] ?? "Data unavailable")
        if (res.rows.length === 0) return noData(slide, cbox, "No data yet")
        addChartTo(slide, b, res, cbox)
        return
      }
      case "table": {
        const titleH = b.title ? 0.3 : 0
        if (b.title) slide.addText(b.title, { x: box.x, y: box.y, w: box.w, h: titleH, fontFace: heading, fontSize: 12, bold: true, color: text, margin: 0 })
        const res = rowsOf(b.query_alias)
        const tbox = { x: box.x, y: box.y + titleH, w: box.w, h: box.h - titleH }
        if (!res) return noData(slide, tbox, bundle.query_errors?.[b.query_alias ?? ""] ?? "Data unavailable")
        if (res.rows.length === 0) return noData(slide, tbox, "No data yet")
        const cols = (b.columns?.length ? b.columns : res.columns.map((c) => ({ field: c.id, label: c.label, format: null }))).filter((c) => res.columns.some((x) => x.id === c.field))
        const head = cols.map((c) => {
          const rc = res.columns.find((x) => x.id === c.field)!
          return { text: c.label || rc.label, options: { bold: true, color: hex(onColor(P.secondary)), fill: { color: secondary }, align: rc.kind === "measure" ? "right" : "left", fontFace: body, fontSize: 10 } }
        })
        const rows = res.rows.slice(0, b.max_rows ?? 10).map((r, ri) =>
          cols.map((c) => {
            const ci = res.columns.findIndex((x) => x.id === c.field)
            const rc = res.columns[ci]
            const v = r[ci]
            return {
              text: rc.kind === "measure" ? formatByMeasure(v, c.format === "currency" ? "currency_zar" : rc.format) : v === null ? "—" : String(v),
              options: { align: rc.kind === "measure" ? "right" : "left", color: text, fontFace: body, fontSize: 10, fill: { color: ri % 2 ? lighten(text, 0.93) : bg } },
            }
          }),
        )
        slide.addTable([head, ...rows], { x: tbox.x, y: tbox.y, w: tbox.w, border: { type: "solid", pt: 0.5, color: "D9D9D9" }, margin: 0.04, autoPage: false })
        return
      }
      case "image": {
        let data: string | null = null
        if (b.source?.kind === "brand_logo") data = theme.logo_data_url && /^data:image\/(png|jpeg);base64,/.test(theme.logo_data_url) ? theme.logo_data_url : null
        else if (b.source?.kind === "url" && b.source.url && opts.fetchImage) data = await opts.fetchImage(b.source.url).catch(() => null)
        if (!data) return noData(slide, box, b.source?.kind === "brand_logo" ? "(Add an uploaded PNG/JPEG logo to the brand kit)" : "(Image could not be embedded)")
        slide.addImage({ data, ...box, altText: b.alt ?? "", sizing: { type: b.fit === "cover" ? "cover" : "contain", w: box.w, h: box.h } })
        return
      }
      case "shape": {
        const c = hex(shapeColor(theme, b.color))
        if (b.shape === "divider") slide.addShape("line", { x: box.x, y: box.y + box.h / 2, w: box.w, h: 0, line: { color: c, width: 2 } })
        else slide.addShape("rect", { ...box, fill: { color: c }, line: { color: c, width: 0 } })
        return
      }
    }
  }

  function addChartTo(slide: any, b: ResolvedBlock, res: QueryResult, box: { x: number; y: number; w: number; h: number }) {
    const type = b.chart_type ?? "column"
    const cd = prepareChart(res, type, b.series ?? {}, b.axis)
    if (!cd) return noData(slide, box, "Choose a value to plot")
    const colors = (b.colors?.length ? b.colors : P.chart).map((c) => hex(c)).filter(Boolean)
    const common: any = {
      ...box,
      chartColors: colors,
      showLegend: b.legend !== "none" && (cd.series.length > 1 || type === "pie" || type === "donut" || (cd.points?.length ?? 0) > 1),
      legendPos: b.legend === "top" ? "t" : b.legend === "right" ? "r" : "b",
      legendFontFace: body,
      legendFontSize: 10,
      legendColor: text,
      catAxisLabelFontFace: body,
      catAxisLabelFontSize: 10,
      catAxisLabelColor: text,
      valAxisLabelFontFace: body,
      valAxisLabelFontSize: 10,
      valAxisLabelColor: text,
      valGridLine: { color: "E5E5E5", size: 0.5 },
      showValue: !!b.labels,
      dataLabelFontSize: 9,
      dataLabelColor: text,
      showCatAxisTitle: !!b.axis?.x_title,
      catAxisTitle: b.axis?.x_title ?? "",
      showValAxisTitle: !!b.axis?.y_title,
      valAxisTitle: b.axis?.y_title ?? "",
      valAxisLabelFormatCode: cd.yFormat === "percent" ? "0%" : cd.yFormat === "currency_zar" ? '"R"#,##0' : "#,##0",
      dataLabelFormatCode: cd.yFormat === "percent" ? "0.0%" : cd.yFormat === "currency_zar" ? '"R"#,##0' : "#,##0",
    }
    if (b.axis?.y_min != null) common.valAxisMinVal = b.axis.y_min
    if (b.axis?.y_max != null) common.valAxisMaxVal = b.axis.y_max
    const z = (v: number | null) => (v === null ? 0 : v)
    const data = cd.series.map((s) => ({ name: s.name, labels: cd.categories, values: s.values.map(z) }))
    const C = pptx.charts

    switch (type) {
      case "column":
      case "bar":
      case "stacked_column":
        slide.addChart(C.BAR, data, { ...common, barDir: type === "bar" ? "bar" : "col", barGrouping: type === "stacked_column" ? "stacked" : "clustered", barGapWidthPct: 60 })
        return
      case "line":
        slide.addChart(C.LINE, data, { ...common, lineSize: 2.5, lineDataSymbolSize: 6 })
        return
      case "area":
        slide.addChart(C.AREA, data, common)
        return
      case "pie":
      case "donut": {
        const s = cd.series[0]
        const labels = cd.categories.filter((_c, i) => (s?.values[i] ?? 0) > 0)
        const values = (s?.values ?? []).filter((v) => (v ?? 0) > 0).map(z)
        slide.addChart(type === "pie" ? C.PIE : C.DOUGHNUT, [{ name: s?.name ?? "", labels, values }], { ...common, showLegend: b.legend !== "none", ...(type === "donut" ? { holeSize: 55 } : {}), showPercent: !!b.labels, showValue: false })
        return
      }
      case "scatter": {
        const pts = (cd.points ?? []).flatMap((p) => p.data)
        slide.addChart(C.SCATTER, [{ name: "X-Axis", values: pts.map((p) => p.x) }, { name: cd.measureLabels.__y ?? "Y", values: pts.map((p) => p.y) }], { ...common, showLegend: false, lineSize: 0, lineDataSymbolSize: 8, showCatAxisTitle: true, catAxisTitle: cd.measureLabels.__x ?? "" })
        return
      }
      case "waterfall": {
        const wf = waterfallBars(cd.series[0]?.values ?? [])
        slide.addChart(
          C.BAR,
          [
            { name: "Base", labels: cd.categories, values: wf.map((w) => w.base) },
            { name: "Increase", labels: cd.categories, values: wf.map((w) => w.up) },
            { name: "Decrease", labels: cd.categories, values: wf.map((w) => w.down) },
          ],
          { ...common, barDir: "col", barGrouping: "stacked", chartColors: [bg, "2BB673", "E5484D"], showLegend: false, showValue: false },
        )
        return
      }
      case "combo": {
        const bars = cd.series.filter((s) => s.axis !== "y2")
        const lines = cd.series.filter((s) => s.axis === "y2")
        const mk = (ss: typeof bars) => ss.map((s) => ({ name: s.name, labels: cd.categories, values: s.values.map(z) }))
        slide.addChart(
          [
            { type: C.BAR, data: mk(bars), options: { chartColors: colors.slice(0, bars.length), barDir: "col", barGrouping: "clustered" } },
            { type: C.LINE, data: mk(lines), options: { chartColors: colors.slice(bars.length, bars.length + lines.length).length ? colors.slice(bars.length, bars.length + lines.length) : [accent], secondaryValAxis: true, secondaryCatAxis: true, lineSize: 2.5 } },
          ],
          {
            ...common,
            valAxes: [{ showValAxisTitle: !!b.axis?.y_title, valAxisTitle: b.axis?.y_title ?? "", valAxisLabelFormatCode: common.valAxisLabelFormatCode }, { showValAxisTitle: false, valAxisLabelFormatCode: cd.y2Format === "percent" ? "0%" : cd.y2Format === "currency_zar" ? '"R"#,##0' : "#,##0", valGridLine: { style: "none" } }],
            catAxes: [{ catAxisTitle: "" }, { catAxisHidden: true }],
          },
        )
        return
      }
    }
  }

  const blocksUsingNarrow: Block[] = []
  void blocksUsingNarrow
  void compactByMeasure
  for (const rs of bundle.slides) {
    const cover = ["title", "section", "closing"].includes(rs.layout)
    const slide = pptx.addSlide({ masterName: cover ? "OD_COVER" : "OD_CONTENT" })
    slide.addText(rs.title || " ", { placeholder: "title" })
    if (rs.subtitle) {
      slide.addText(rs.subtitle, { ...fr(cover ? COVER_SUBTITLE_FRAME : SUBTITLE_FRAME), fontFace: body, fontSize: cover ? 16 : 12, color: cover ? hex(onColor(P.secondary)) : "666666", margin: 0, valign: "top" })
    }
    await addBlocks(slide, rs, cover)
    if (logo) {
      if (cover) slide.addImage({ data: logo, x: px(8), y: py(7), w: px(18), h: py(12), sizing: { type: "contain", w: px(18), h: py(12) }, altText: theme.company_name || "Logo" })
      else slide.addImage({ data: logo, ...fr(LOGO_FRAME), sizing: { type: "contain", w: px(LOGO_FRAME.w), h: py(LOGO_FRAME.h) }, altText: theme.company_name || "Logo" })
    }
    if (!cover || rs.layout === "closing") {
      const foot = [theme.footer_text, asOfLabel].filter(Boolean).join("   |   ")
      if (foot) slide.addText(foot, { ...fr(FOOTER_FRAME), fontFace: body, fontSize: 8, color: cover ? hex(onColor(P.secondary)) : "808080", margin: 0, valign: "middle" })
    }
    if (rs.notes) slide.addNotes(rs.notes)
  }
  return pptx
}

export async function pptxToBlob(bundle: ExportBundle, opts?: PptxOptions): Promise<Blob> {
  const pptx = await buildPptx(bundle, opts)
  return (await pptx.write({ outputType: "blob" })) as Blob
}

export function safeFileName(title: string, ext: string): string {
  const base = title.replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "-").slice(0, 60) || "deck"
  return `${base}.${ext}`
}
