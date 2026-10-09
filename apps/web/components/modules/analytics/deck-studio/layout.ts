import type { Block, Frame, Layout, Slide } from "@/lib/bi-studio-api"

/** Layout-based zones in percent of a 16:9 slide. Shared by the on-screen renderer and the PPTX exporter. */

export const LAYOUT_LABELS: Record<Layout, string> = {
  title: "Title",
  section: "Section",
  content: "Content",
  two_column: "Two columns",
  chart_full: "Full chart",
  chart_plus_text: "Chart + text",
  kpi_strip: "KPI strip",
  table: "Table",
  comparison: "Comparison",
  closing: "Closing",
}
export const LAYOUT_ORDER = Object.keys(LAYOUT_LABELS) as Layout[]

const F = (x: number, y: number, w: number, h: number): Frame => ({ x, y, w, h })
const BODY_Y = 21
const BODY_H = 67

type ZoneDef = Record<string, Frame>
const ZONES: Record<Layout, ZoneDef> = {
  title: { main: F(8, 66, 84, 22) },
  section: { main: F(8, 64, 84, 24) },
  closing: { main: F(8, 66, 84, 22) },
  content: { main: F(5, BODY_Y, 90, BODY_H) },
  two_column: { left: F(5, BODY_Y, 43.5, BODY_H), right: F(51.5, BODY_Y, 43.5, BODY_H) },
  comparison: { left: F(5, BODY_Y, 43.5, BODY_H), right: F(51.5, BODY_Y, 43.5, BODY_H) },
  chart_full: { main: F(5, BODY_Y, 90, 57), bottom: F(5, 80, 90, 9) },
  chart_plus_text: { left: F(5, BODY_Y, 58, BODY_H), right: F(66, BODY_Y, 29, BODY_H) },
  kpi_strip: { top: F(5, BODY_Y, 90, 25), main: F(5, 49, 90, 39) },
  table: { main: F(5, BODY_Y, 90, 60), bottom: F(5, 83, 90, 6) },
}

export const TITLE_FRAME: Frame = F(5, 5.5, 78, 12)
export const COVER_TITLE_FRAME: Frame = F(8, 26, 84, 24)
export const COVER_SUBTITLE_FRAME: Frame = F(8, 51, 84, 10)
export const SUBTITLE_FRAME: Frame = F(5, 15, 78, 5)
export const FOOTER_FRAME: Frame = F(5, 93, 70, 4)
export const SLIDE_NUM_FRAME: Frame = F(90, 93, 5, 4)
export const LOGO_FRAME: Frame = F(86, 4, 9, 9)

export const isCoverLayout = (l: Layout) => l === "title" || l === "section" || l === "closing"
export const zonesFor = (l: Layout): string[] => Object.keys(ZONES[l])

function isDataBlock(b: Block) {
  return b.type === "chart" || b.type === "table"
}

function autoZone(layout: Layout, b: Block, i: number, all: Block[]): string {
  const zones = ZONES[layout]
  const flowing: Block[] = all.filter((x) => x.type !== "shape" && x.type !== "image")
  const fi = flowing.indexOf(b)
  switch (layout) {
    case "two_column":
    case "comparison":
      return fi >= 0 && fi >= Math.ceil(flowing.length / 2) ? "right" : "left"
    case "chart_full":
    case "table": {
      const first = all.find(isDataBlock)
      return isDataBlock(b) && b === first ? "main" : "bottom"
    }
    case "chart_plus_text": {
      const first = all.find(isDataBlock)
      return b === first ? "left" : "right"
    }
    case "kpi_strip":
      return b.type === "kpi" ? "top" : "main"
    default:
      return "main" in zones ? "main" : Object.keys(zones)[0]
  }
}

function weight(b: Block): number {
  switch (b.type) {
    case "chart":
    case "table":
      return 4
    case "kpi":
      return 2
    case "text":
      return Math.min(4, 0.9 + 0.4 * Math.max(1, b.items.length))
    case "image":
      return 2
    case "shape":
      return 0.15
  }
}

export interface SlideFrames {
  cover: boolean
  title: Frame
  subtitle: Frame
  blocks: Record<string, Frame>
  zoneOf: Record<string, string>
  zones: ZoneDef
}

export function computeFrames(slide: Slide): SlideFrames {
  const zones = ZONES[slide.layout] ?? ZONES.content
  const zoneOf: Record<string, string> = {}
  const grouped: Record<string, Block[]> = {}
  slide.blocks.forEach((b, i) => {
    const z = b.slot && b.slot in zones ? b.slot : autoZone(slide.layout, b, i, slide.blocks)
    zoneOf[b.id] = z
    ;(grouped[z] ??= []).push(b)
  })
  const blocks: Record<string, Frame> = {}
  for (const [z, list] of Object.entries(grouped)) {
    const zf = zones[z] ?? Object.values(zones)[0]
    const gap = 1.6
    const horizontal = list.length > 1 && list.every((b) => b.type === "kpi")
    const auto = list.filter((b) => !b.frame)
    if (horizontal) {
      const w = (zf.w - gap * (auto.length - 1)) / auto.length
      auto.forEach((b, i) => (blocks[b.id] = F(zf.x + i * (w + gap), zf.y, w, zf.h)))
    } else {
      const total = auto.reduce((a, b) => a + weight(b), 0) || 1
      const avail = zf.h - gap * Math.max(0, auto.length - 1)
      let y = zf.y
      for (const b of auto) {
        const h = (avail * weight(b)) / total
        blocks[b.id] = F(zf.x, y, zf.w, h)
        y += h + gap
      }
    }
  }
  for (const b of slide.blocks) if (b.frame) blocks[b.id] = b.frame
  const cover = isCoverLayout(slide.layout)
  return {
    cover,
    title: cover ? COVER_TITLE_FRAME : TITLE_FRAME,
    subtitle: cover ? COVER_SUBTITLE_FRAME : SUBTITLE_FRAME,
    blocks,
    zoneOf,
    zones,
  }
}

export const ZONE_LABELS: Record<string, string> = {
  main: "Main",
  left: "Left",
  right: "Right",
  top: "Top",
  bottom: "Bottom",
}
