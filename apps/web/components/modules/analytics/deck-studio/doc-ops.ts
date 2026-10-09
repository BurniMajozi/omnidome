import type {
  Block,
  BlockType,
  ChartBlock,
  ChartType,
  DeckDoc,
  KpiBlock,
  Layout,
  QuerySpec,
  Slide,
  TableBlock,
  TextBlock,
} from "@/lib/bi-studio-api"

/** Pure document operations (immutable). Ids obey ^[A-Za-z0-9_-]{1,40}$ and are unique per deck. */

export function allIds(doc: DeckDoc): Set<string> {
  const s = new Set<string>(Object.keys(doc.queries ?? {}))
  for (const sl of doc.slides) {
    s.add(sl.id)
    for (const b of sl.blocks) s.add(b.id)
  }
  return s
}
export function newId(doc: DeckDoc, prefix: string, extra?: Set<string>): string {
  const used = allIds(doc)
  extra?.forEach((x) => used.add(x))
  for (let i = 0; i < 1000; i++) {
    const id = `${prefix}${Math.random().toString(36).slice(2, 8)}`
    if (!used.has(id)) return id
  }
  return `${prefix}${Date.now().toString(36)}`
}

export const blockAlias = (b: Block): string | null =>
  b.type === "chart" || b.type === "table" ? (b.query ? b.id : (b.query_ref ?? null)) : null

/** All query specs the deck needs, keyed by alias (deck-level queries + inline block queries). */
export function collectQueries(doc: DeckDoc): Record<string, QuerySpec> {
  const out: Record<string, QuerySpec> = { ...(doc.queries ?? {}) }
  for (const s of doc.slides)
    for (const b of s.blocks) if ((b.type === "chart" || b.type === "table") && b.query) out[b.id] = b.query
  return out
}

export function emptyDoc(title: string): DeckDoc {
  return {
    schema_version: 1,
    title,
    queries: {},
    slides: [
      {
        id: "s1",
        layout: "title",
        title,
        subtitle: "",
        notes: "",
        blocks: [],
      },
    ],
  }
}

function textBlock(id: string, text: string, role: TextBlock["role"] = "body", bullet = true): TextBlock {
  return { type: "text", id, role, align: "left", items: [{ text, bullet }] }
}

export function starterBlocks(doc: DeckDoc, layout: Layout): Block[] {
  const used = new Set<string>()
  const id = () => {
    const v = newId(doc, "b", used)
    used.add(v)
    return v
  }
  switch (layout) {
    case "content":
    case "two_column":
      return [textBlock(id(), "Add your key point")]
    case "comparison":
      return [textBlock(id(), "First option", "body"), textBlock(id(), "Second option", "body")]
    case "closing":
      return [textBlock(id(), "Thank you", "callout", false)]
    case "chart_full":
    case "chart_plus_text":
    case "kpi_strip":
    case "table":
      return [textBlock(id(), "Add a takeaway", "caption", false)]
    default:
      return []
  }
}

export function makeSlide(doc: DeckDoc, layout: Layout): Slide {
  const used = new Set<string>()
  const sid = newId(doc, "s")
  used.add(sid)
  const d2: DeckDoc = { ...doc, slides: [...doc.slides] }
  return { id: sid, layout, title: layout === "title" ? "Title" : "New slide", subtitle: "", notes: "", blocks: starterBlocks(d2, layout).map((b) => ({ ...b })) }
}

export function insertSlide(doc: DeckDoc, slide: Slide, index: number): DeckDoc {
  const slides = [...doc.slides]
  slides.splice(Math.max(0, Math.min(index, slides.length)), 0, slide)
  return { ...doc, slides }
}
export function removeSlide(doc: DeckDoc, id: string): DeckDoc {
  if (doc.slides.length <= 1) return doc
  return { ...doc, slides: doc.slides.filter((s) => s.id !== id) }
}
export function moveSlide(doc: DeckDoc, from: number, to: number): DeckDoc {
  if (from === to || from < 0 || to < 0 || from >= doc.slides.length || to >= doc.slides.length) return doc
  const slides = [...doc.slides]
  const [s] = slides.splice(from, 1)
  slides.splice(to, 0, s)
  return { ...doc, slides }
}
export function updateSlide(doc: DeckDoc, id: string, patch: Partial<Slide>): DeckDoc {
  return { ...doc, slides: doc.slides.map((s) => (s.id === id ? { ...s, ...patch } : s)) }
}
export function replaceSlide(doc: DeckDoc, slide: Slide): DeckDoc {
  return { ...doc, slides: doc.slides.map((s) => (s.id === slide.id ? slide : s)) }
}

/** Duplicate with fresh slide/block ids; inline queries move with their (renamed) blocks. */
export function duplicateSlide(doc: DeckDoc, id: string): DeckDoc {
  const i = doc.slides.findIndex((s) => s.id === id)
  if (i < 0) return doc
  const src = doc.slides[i]
  const used = new Set<string>()
  const take = (p: string) => {
    const v = newId(doc, p, used)
    used.add(v)
    return v
  }
  const copy: Slide = JSON.parse(JSON.stringify(src))
  copy.id = take("s")
  copy.blocks = copy.blocks.map((b) => ({ ...b, id: take("b") }))
  return insertSlide(doc, copy, i + 1)
}

export function updateBlock(doc: DeckDoc, slideId: string, blockId: string, next: Block | ((b: Block) => Block)): DeckDoc {
  return {
    ...doc,
    slides: doc.slides.map((s) =>
      s.id !== slideId ? s : { ...s, blocks: s.blocks.map((b) => (b.id === blockId ? (typeof next === "function" ? next(b) : next) : b)) },
    ),
  }
}
export function addBlock(doc: DeckDoc, slideId: string, block: Block, index?: number): DeckDoc {
  return {
    ...doc,
    slides: doc.slides.map((s) => {
      if (s.id !== slideId) return s
      const blocks = [...s.blocks]
      blocks.splice(index ?? blocks.length, 0, block)
      return { ...s, blocks }
    }),
  }
}
export function removeBlock(doc: DeckDoc, slideId: string, blockId: string): DeckDoc {
  return { ...doc, slides: doc.slides.map((s) => (s.id !== slideId ? s : { ...s, blocks: s.blocks.filter((b) => b.id !== blockId) })) }
}
export function moveBlock(doc: DeckDoc, slideId: string, blockId: string, delta: number): DeckDoc {
  return {
    ...doc,
    slides: doc.slides.map((s) => {
      if (s.id !== slideId) return s
      const i = s.blocks.findIndex((b) => b.id === blockId)
      const j = i + delta
      if (i < 0 || j < 0 || j >= s.blocks.length) return s
      const blocks = [...s.blocks]
      const [b] = blocks.splice(i, 1)
      blocks.splice(j, 0, b)
      return { ...s, blocks }
    }),
  }
}
export function duplicateBlock(doc: DeckDoc, slideId: string, blockId: string): { doc: DeckDoc; id: string | null } {
  const s = doc.slides.find((x) => x.id === slideId)
  const b = s?.blocks.find((x) => x.id === blockId)
  if (!s || !b) return { doc, id: null }
  const id = newId(doc, "b")
  const copy = { ...JSON.parse(JSON.stringify(b)), id } as Block
  return { doc: addBlock(doc, slideId, copy, s.blocks.indexOf(b) + 1), id }
}

/** Query specs no block, token or kpi references any more. */
export function pruneQueries(doc: DeckDoc): DeckDoc {
  const refs = new Set<string>()
  const text: string[] = []
  for (const s of doc.slides) {
    text.push(s.notes ?? "")
    for (const b of s.blocks) {
      if ((b.type === "chart" || b.type === "table") && b.query_ref) refs.add(b.query_ref)
      if (b.type === "kpi") {
        refs.add(b.value_ref.split(".")[0])
        if (b.delta_ref) refs.add(b.delta_ref.split(".")[0])
      }
      if (b.type === "text") b.items.forEach((i) => text.push(i.text))
    }
  }
  const body = text.join("\n")
  const queries: Record<string, QuerySpec> = {}
  for (const [k, v] of Object.entries(doc.queries ?? {})) {
    if (refs.has(k) || new RegExp(`\\{\\{\\s*${k.replace(/[-]/g, "\\-")}[.|\\s}]`).test(body)) queries[k] = v
  }
  return { ...doc, queries }
}

export function newChartBlock(doc: DeckDoc, spec: QuerySpec, type: ChartType, series: ChartBlock["series"], title = ""): ChartBlock {
  return {
    type: "chart",
    id: newId(doc, "c"),
    chart_type: type,
    title,
    query: spec,
    series,
    axis: { sort: "data" },
    labels: false,
    legend: "bottom",
    colors: [],
  }
}
export function newTableBlock(doc: DeckDoc, spec: QuerySpec): TableBlock {
  return { type: "table", id: newId(doc, "t"), title: "", query: spec, columns: [], max_rows: 10 }
}
export function newKpiBlock(doc: DeckDoc, alias: string, measure: string, label: string): KpiBlock {
  return { type: "kpi", id: newId(doc, "k"), label, value_ref: `${alias}.${measure}`, delta_ref: null, format: null, caption: "", good_direction: "up" }
}
export function newBlockOfType(doc: DeckDoc, type: Exclude<BlockType, "chart" | "table" | "kpi">): Block {
  const id = newId(doc, type === "text" ? "b" : type === "image" ? "i" : "h")
  if (type === "text") return textBlock(id, "New text")
  if (type === "image") return { type: "image", id, source: { kind: "brand_logo" }, alt: "Logo", fit: "contain" }
  return { type: "shape", id, shape: "divider", color: "accent" }
}

export function docStats(doc: DeckDoc) {
  const blocks = doc.slides.reduce((a, s) => a + s.blocks.length, 0)
  return { slides: doc.slides.length, blocks, queries: Object.keys(collectQueries(doc)).length }
}

/** Text block items <-> editable plain text. Lines starting with "- " or a bullet are bullets; two leading spaces per indent level. */
export function itemsToText(items: { text: string; bullet?: boolean; level?: number }[]): string {
  return items.map((i) => `${"  ".repeat(i.level ?? 0)}${i.bullet ? "- " : ""}${i.text}`).join("\n")
}
export function textToItems(text: string, prev: { text: string; bullet?: boolean; level?: number; bold?: boolean }[] = []) {
  return text
    .split("\n")
    .slice(0, 30)
    .map((line, idx) => {
      const lead = /^(\s*)/.exec(line)?.[1].length ?? 0
      const level = Math.min(2, Math.floor(lead / 2))
      let rest = line.slice(lead)
      let bullet = false
      const m = /^([-*•])\s+/.exec(rest)
      if (m) {
        bullet = true
        rest = rest.slice(m[0].length)
      }
      return { text: rest.slice(0, 1200), bullet, level, bold: prev[idx]?.bold ?? false }
    })
}
