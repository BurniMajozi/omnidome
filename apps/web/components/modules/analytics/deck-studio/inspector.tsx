"use client"

import { AlertTriangle, ArrowDown, ArrowUp, Copy, Database, Pencil, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { Block, ChartBlock, ChartType, DeckDoc, ImageBlock, KpiBlock, Layout, ShapeBlock, Slide, TableBlock, TextBlock } from "@/lib/bi-studio-api"
import { Field, Section, fieldCls, textareaCls, useStudio } from "./ui"
import { LayoutGallery } from "./slide-rail"
import { computeFrames, ZONE_LABELS } from "./layout"
import { fitToType, modelFrom, modelToSeries, modelToSpec, validateModel } from "./builder-model"
import { safeImageUrl } from "./theme"
import type { QState } from "./use-deck-data"
import { itemsToText } from "./doc-ops"

export interface InspectorProps {
  doc: DeckDoc
  slide: Slide
  block: Block | null
  readOnly: boolean
  states: Record<string, QState>
  setDoc: (d: DeckDoc, key?: string) => void
  onSelectBlock: (id: string | null) => void
  onUpdateBlock: (id: string, fn: (b: Block) => Block, key?: string) => void
  onUpdateSlide: (patch: Partial<Slide>, key?: string) => void
  onChangeLayout: (l: Layout) => void
  onEditData: (b: Block) => void
  onAddBlock: (t: "chart" | "kpi" | "table" | "text" | "image" | "shape") => void
  onDeleteBlock: (id: string) => void
  onDuplicateBlock: (id: string) => void
  onMoveBlock: (id: string, delta: number) => void
  onEditText: (id: string) => void
  onInsertValue: (target: "notes" | "block") => void
  onRetry: (alias: string) => void
  kits: { id: string; name: string }[]
  onKit: (id: string | null) => void
  onTheme: (patch: { footer_text?: string; slide_numbers?: boolean }) => void
  onStrict: (v: boolean) => void
  registerNotes: (el: HTMLTextAreaElement | null) => void
  warnings: Record<string, { literal: string }[]>
}

const ROLES: TextBlock["role"][] = ["body", "callout", "quote", "caption"]

export function Inspector(p: InspectorProps) {
  return p.block ? <BlockInspector {...p} block={p.block} /> : <SlideInspector {...p} />
}

function BlockList({ p }: { p: InspectorProps }) {
  const { slide } = p
  return (
    <ul className="space-y-1">
      {slide.blocks.map((b, i) => (
        <li key={b.id} className="flex items-center gap-1 rounded border border-border px-2 py-1 text-xs">
          <button type="button" className="min-w-0 flex-1 truncate text-left" onClick={() => p.onSelectBlock(b.id)}>
            <span className="text-muted-foreground">{b.type}</span> {blockTitle(b)}
          </button>
          <button type="button" aria-label="Move up" disabled={p.readOnly || i === 0} onClick={() => p.onMoveBlock(b.id, -1)} className="rounded p-0.5 hover:bg-muted disabled:opacity-30">
            <ArrowUp className="h-3 w-3" />
          </button>
          <button type="button" aria-label="Move down" disabled={p.readOnly || i === slide.blocks.length - 1} onClick={() => p.onMoveBlock(b.id, 1)} className="rounded p-0.5 hover:bg-muted disabled:opacity-30">
            <ArrowDown className="h-3 w-3" />
          </button>
        </li>
      ))}
      {slide.blocks.length === 0 && <li className="text-xs text-muted-foreground">No blocks on this slide.</li>}
    </ul>
  )
}

function blockTitle(b: Block): string {
  switch (b.type) {
    case "text":
      return (b.items[0]?.text ?? "").slice(0, 30)
    case "kpi":
      return b.label
    case "chart":
    case "table":
      return b.title || b.id
    default:
      return b.id
  }
}

function SlideInspector(p: InspectorProps) {
  const { slide, readOnly } = p
  const { datasets } = useStudio()
  void datasets
  return (
    <div>
      <Section title="Slide">
        <Field label="Title" htmlFor="si-title">
          <input id="si-title" className={fieldCls} value={slide.title} maxLength={200} disabled={readOnly} onChange={(e) => p.onUpdateSlide({ title: e.target.value }, `title:${slide.id}`)} />
        </Field>
        <Field label="Subtitle" htmlFor="si-sub">
          <input id="si-sub" className={fieldCls} value={slide.subtitle ?? ""} maxLength={200} disabled={readOnly} onChange={(e) => p.onUpdateSlide({ subtitle: e.target.value }, `sub:${slide.id}`)} />
        </Field>
      </Section>
      <Section title="Layout">
        <fieldset disabled={readOnly} className="disabled:opacity-60">
          <LayoutGallery current={slide.layout} onPick={p.onChangeLayout} />
        </fieldset>
      </Section>
      <Section
        title="Add to slide"
        action={slide.blocks.length >= 12 ? <span className="text-[10px] text-amber-300">12 block limit</span> : undefined}
      >
        <div className="grid grid-cols-3 gap-1.5">
          {(["chart", "kpi", "table", "text", "image", "shape"] as const).map((t) => (
            <Button key={t} size="sm" variant="outline" className="h-7 text-xs capitalize" disabled={readOnly || slide.blocks.length >= 12} onClick={() => p.onAddBlock(t)}>
              <Plus className="h-3 w-3" /> {t === "kpi" ? "KPI" : t}
            </Button>
          ))}
        </div>
      </Section>
      <Section title="Blocks">
        <BlockList p={p} />
      </Section>
      <Section
        title="Speaker notes"
        action={
          <button type="button" disabled={readOnly} onClick={() => p.onInsertValue("notes")} className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline disabled:opacity-40">
            <Database className="h-3 w-3" /> Insert data value
          </button>
        }
      >
        <textarea ref={p.registerNotes} aria-label="Speaker notes" className={textareaCls} rows={5} maxLength={4000} disabled={readOnly} value={slide.notes ?? ""} onChange={(e) => p.onUpdateSlide({ notes: e.target.value }, `notes:${slide.id}`)} placeholder="Notes can reference data: {{alias.measure.last|currency}}" />
      </Section>
      <DeckSettings {...p} />
    </div>
  )
}

function DeckSettings(p: InspectorProps) {
  const th = p.doc.theme ?? {}
  return (
    <Section title="Deck settings">
      <Field label="Brand kit" htmlFor="ds-kit">
        <select id="ds-kit" className={fieldCls} disabled={p.readOnly} value={p.doc.brand_kit_id ?? ""} onChange={(e) => p.onKit(e.target.value || null)}>
          <option value="">Default</option>
          {p.kits.map((k) => (
            <option key={k.id} value={k.id}>
              {k.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Footer text override" htmlFor="ds-foot">
        <input id="ds-foot" className={fieldCls} disabled={p.readOnly} value={th.footer_text ?? ""} maxLength={160} onChange={(e) => p.onTheme({ footer_text: e.target.value })} placeholder="From brand kit" />
      </Field>
      <label className="flex items-center gap-2 text-xs">
        <input type="checkbox" disabled={p.readOnly} checked={th.slide_numbers ?? true} onChange={(e) => p.onTheme({ slide_numbers: e.target.checked })} /> Slide numbers
      </label>
      <label className="flex items-start gap-2 text-xs">
        <input type="checkbox" className="mt-0.5" disabled={p.readOnly} checked={p.doc.settings?.strict_numbers ?? false} onChange={(e) => p.onStrict(e.target.checked)} />
        <span>
          Strict numbers
          <span className="block text-[11px] text-muted-foreground">Reject saving and block export while any figure is typed outside a data reference.</span>
        </span>
      </label>
    </Section>
  )
}

function SourceInfo({ p, alias }: { p: InspectorProps; alias: string }) {
  const { datasetLabel } = useStudio()
  const st = p.states[alias]
  return (
    <div className="space-y-1 rounded-md border border-border bg-secondary/20 p-2 text-[11px] text-muted-foreground">
      {st?.result ? (
        <>
          <div>
            Dataset: <span className="text-foreground">{datasetLabel(st.result.meta.dataset)}</span>
          </div>
          <div>
            {st.result.meta.row_count} row(s) · as of {new Date(st.result.meta.generated_at).toLocaleString("en-ZA")}
          </div>
        </>
      ) : st?.status === "error" ? (
        <div className="space-y-1 text-red-300">
          <div className="flex items-start gap-1">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> {st.error}
          </div>
          <Button size="sm" variant="outline" className="h-6 text-xs" onClick={() => p.onRetry(alias)}>
            Retry
          </Button>
        </div>
      ) : (
        <div>Loading data…</div>
      )}
    </div>
  )
}

function BlockInspector(p: InspectorProps & { block: Block }) {
  const { block: b, readOnly, slide } = p
  const { datasets } = useStudio()
  const upd = (fn: (b: Block) => Block, key?: string) => p.onUpdateBlock(b.id, fn, key ?? `blk:${b.id}`)
  const zones = Object.keys(computeFrames(slide).zones)
  const warn = p.warnings[b.id]

  function retype(t: ChartType) {
    const cb = b as ChartBlock
    const spec = cb.query ?? (cb.query_ref ? p.doc.queries[cb.query_ref] : null)
    const model = modelFrom(spec, cb.series, cb.chart_type, datasets.get(spec?.dataset ?? ""))
    if (!model) return
    const { model: fitted } = fitToType(model, t)
    const bad = validateModel(fitted, t)
    if (bad) {
      p.onEditData({ ...cb, chart_type: t })
      return
    }
    upd((x) => ({ ...(x as ChartBlock), chart_type: t, query: modelToSpec(fitted, t), query_ref: null, series: modelToSeries(fitted, t) }), `type:${b.id}`)
  }

  const alias = b.type === "chart" || b.type === "table" ? (b.query ? b.id : (b.query_ref ?? "")) : b.type === "kpi" ? b.value_ref.split(".")[0] : ""

  return (
    <div>
      <Section
        title={`${b.type === "kpi" ? "KPI" : b.type} block`}
        action={
          <button type="button" className="text-[11px] text-primary hover:underline" onClick={() => p.onSelectBlock(null)}>
            Slide settings
          </button>
        }
      >
        <div className="flex flex-wrap gap-1">
          <Button size="sm" variant="outline" className="h-7 text-xs" disabled={readOnly} onClick={() => p.onDuplicateBlock(b.id)}>
            <Copy className="h-3 w-3" /> Duplicate
          </Button>
          <Button size="sm" variant="outline" className="h-7 text-xs" disabled={readOnly} onClick={() => p.onMoveBlock(b.id, -1)}>
            <ArrowUp className="h-3 w-3" /> Back
          </Button>
          <Button size="sm" variant="outline" className="h-7 text-xs" disabled={readOnly} onClick={() => p.onMoveBlock(b.id, 1)}>
            <ArrowDown className="h-3 w-3" /> Forward
          </Button>
          <Button size="sm" variant="ghost-destructive" className="ml-auto h-7 text-xs" disabled={readOnly} onClick={() => p.onDeleteBlock(b.id)}>
            <Trash2 className="h-3 w-3" /> Delete
          </Button>
        </div>
        {warn && warn.length > 0 && (
          <div className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-[11px] text-amber-200">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              Typed figure(s) not linked to data: {warn.map((w) => `“${w.literal}”`).join(", ")}. Replace with “Insert data value”.
            </span>
          </div>
        )}
      </Section>

      {b.type === "text" && (
        <Section title="Text">
          <Button size="sm" className="h-7 w-full text-xs" disabled={readOnly} onClick={() => p.onEditText(b.id)}>
            <Pencil className="h-3 w-3" /> Edit text
          </Button>
          <Button size="sm" variant="outline" className="h-7 w-full text-xs" disabled={readOnly} onClick={() => p.onInsertValue("block")}>
            <Database className="h-3 w-3" /> Insert data value
          </Button>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Style" htmlFor="tx-role">
              <select id="tx-role" className={fieldCls} disabled={readOnly} value={b.role ?? "body"} onChange={(e) => upd((x) => ({ ...(x as TextBlock), role: e.target.value as TextBlock["role"] }))}>
                {ROLES.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </Field>
            <Field label="Align" htmlFor="tx-al">
              <select id="tx-al" className={fieldCls} disabled={readOnly} value={b.align ?? "left"} onChange={(e) => upd((x) => ({ ...(x as TextBlock), align: e.target.value as TextBlock["align"] }))}>
                <option>left</option>
                <option>center</option>
                <option>right</option>
              </select>
            </Field>
          </div>
          <p className="text-[11px] text-muted-foreground">Double-click the text on the slide to edit inline. One line per item; start a line with “- ” for a bullet, indent two spaces per level.</p>
          <details className="text-[11px] text-muted-foreground">
            <summary className="cursor-pointer">Raw text</summary>
            <pre className="mt-1 whitespace-pre-wrap break-words rounded bg-secondary/30 p-2">{itemsToText(b.items)}</pre>
          </details>
        </Section>
      )}

      {b.type === "kpi" && (
        <Section title="KPI">
          <Field label="Label" htmlFor="kp-l">
            <input id="kp-l" className={fieldCls} disabled={readOnly} value={b.label} maxLength={80} onChange={(e) => upd((x) => ({ ...(x as KpiBlock), label: e.target.value }))} />
          </Field>
          <Field label="Caption" htmlFor="kp-c">
            <input id="kp-c" className={fieldCls} disabled={readOnly} value={b.caption ?? ""} maxLength={200} onChange={(e) => upd((x) => ({ ...(x as KpiBlock), caption: e.target.value }))} />
          </Field>
          <Button size="sm" className="h-7 w-full text-xs" disabled={readOnly} onClick={() => p.onEditData(b)}>
            <Database className="h-3 w-3" /> Edit data
          </Button>
          <SourceInfo p={p} alias={alias} />
        </Section>
      )}

      {b.type === "chart" && (
        <Section title="Chart">
          <Field label="Title" htmlFor="ch-t">
            <input id="ch-t" className={fieldCls} disabled={readOnly} value={b.title ?? ""} maxLength={200} onChange={(e) => upd((x) => ({ ...(x as ChartBlock), title: e.target.value }))} />
          </Field>
          <Field label="Chart type" htmlFor="ch-type">
            <select id="ch-type" className={fieldCls} disabled={readOnly} value={b.chart_type} onChange={(e) => retype(e.target.value as ChartType)}>
              {["column", "bar", "stacked_column", "line", "area", "combo", "pie", "donut", "scatter", "waterfall"].map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </Field>
          <Button size="sm" className="h-7 w-full text-xs" disabled={readOnly} onClick={() => p.onEditData(b)}>
            <Database className="h-3 w-3" /> Edit data and format
          </Button>
          <SourceInfo p={p} alias={alias} />
        </Section>
      )}

      {b.type === "table" && (
        <Section title="Table">
          <Field label="Title" htmlFor="tb-t">
            <input id="tb-t" className={fieldCls} disabled={readOnly} value={b.title ?? ""} maxLength={200} onChange={(e) => upd((x) => ({ ...(x as TableBlock), title: e.target.value }))} />
          </Field>
          <Button size="sm" className="h-7 w-full text-xs" disabled={readOnly} onClick={() => p.onEditData(b)}>
            <Database className="h-3 w-3" /> Edit data and columns
          </Button>
          <SourceInfo p={p} alias={alias} />
        </Section>
      )}

      {b.type === "image" && <ImageInspector b={b} readOnly={readOnly} upd={upd} />}

      {b.type === "shape" && (
        <Section title="Shape">
          <Field label="Shape" htmlFor="sh-s">
            <select id="sh-s" className={fieldCls} disabled={readOnly} value={b.shape} onChange={(e) => upd((x) => ({ ...(x as ShapeBlock), shape: e.target.value as ShapeBlock["shape"] }))}>
              <option value="divider">Divider line</option>
              <option value="rect">Rectangle</option>
              <option value="accent_bar">Accent bar</option>
            </select>
          </Field>
          <Field label="Colour" htmlFor="sh-c">
            <select id="sh-c" className={fieldCls} disabled={readOnly} value={b.color ?? "accent"} onChange={(e) => upd((x) => ({ ...(x as ShapeBlock), color: e.target.value }))}>
              {["primary", "secondary", "accent", "text", "background"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </Field>
        </Section>
      )}

      <Section title="Position">
        <Field label="Layout zone" htmlFor="pos-zone" hint="Blocks sit in the layout's zones; several blocks in a zone stack automatically.">
          <select id="pos-zone" className={fieldCls} disabled={readOnly} value={b.slot && zones.includes(b.slot) ? b.slot : ""} onChange={(e) => upd((x) => ({ ...x, slot: e.target.value || null }) as Block, `slot:${b.id}`)}>
            <option value="">Automatic</option>
            {zones.map((z) => (
              <option key={z} value={z}>
                {ZONE_LABELS[z] ?? z}
              </option>
            ))}
          </select>
        </Field>
        {b.frame && (
          <Button size="sm" variant="outline" className="h-7 text-xs" disabled={readOnly} onClick={() => upd((x) => ({ ...x, frame: null }) as Block)}>
            Reset to layout position
          </Button>
        )}
      </Section>
    </div>
  )
}

function ImageInspector({ b, readOnly, upd }: { b: ImageBlock; readOnly: boolean; upd: (fn: (b: Block) => Block, key?: string) => void }) {
  const url = b.source.kind === "url" ? b.source.url : ""
  const bad = b.source.kind === "url" && !!url && !safeImageUrl(url)
  return (
    <Section title="Image">
      <Field label="Source" htmlFor="im-s">
        <select id="im-s" className={fieldCls} disabled={readOnly} value={b.source.kind} onChange={(e) => upd((x) => ({ ...(x as ImageBlock), source: e.target.value === "brand_logo" ? { kind: "brand_logo" } : { kind: "url", url: "" } }))}>
          <option value="brand_logo">Brand logo</option>
          <option value="url">Web address (https)</option>
        </select>
      </Field>
      {b.source.kind === "url" && (
        <Field label="Image URL" htmlFor="im-u" hint={bad ? "Only https:// image links are allowed." : "The server never downloads it; your browser loads it directly."}>
          <input id="im-u" className={fieldCls} aria-invalid={bad} disabled={readOnly} value={url ?? ""} maxLength={500} onChange={(e) => upd((x) => ({ ...(x as ImageBlock), source: { kind: "url", url: e.target.value } }), `img:${b.id}`)} placeholder="https://…" />
        </Field>
      )}
      <Field label="Alt text" htmlFor="im-a">
        <input id="im-a" className={fieldCls} disabled={readOnly} value={b.alt ?? ""} maxLength={200} onChange={(e) => upd((x) => ({ ...(x as ImageBlock), alt: e.target.value }), `alt:${b.id}`)} />
      </Field>
      <Field label="Fit" htmlFor="im-f">
        <select id="im-f" className={fieldCls} disabled={readOnly} value={b.fit ?? "contain"} onChange={(e) => upd((x) => ({ ...(x as ImageBlock), fit: e.target.value as ImageBlock["fit"] }))}>
          <option>contain</option>
          <option>cover</option>
        </select>
      </Field>
    </Section>
  )
}
