"use client"

import { useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import type { DeckDoc } from "@/lib/bi-studio-api"
import { Field, Modal, fieldCls, useStudio } from "./ui"
import { collectQueries } from "./doc-ops"
import { resolveToken, TOKEN_FORMATS, tokenBody, type DataMap } from "./tokens"

export const STATS: { id: string; label: string }[] = [
  { id: "total", label: "Total (whole filter)" },
  { id: "last", label: "Latest period" },
  { id: "prev", label: "Previous period" },
  { id: "first", label: "First row" },
  { id: "delta", label: "Change vs previous (last − prev)" },
  { id: "delta_pct", label: "Change % vs previous" },
  { id: "max", label: "Maximum" },
  { id: "min", label: "Minimum" },
  { id: "avg", label: "Average" },
  { id: "top1.value", label: "Top 1 value" },
  { id: "top1.label", label: "Top 1 name" },
  { id: "top1.share", label: "Top 1 share of total" },
  { id: "last.label", label: "Latest period label" },
  { id: "rows", label: "Row count" },
]

/** "Insert data value" dialog: pick a query, measure, statistic and format; shows the live resolved value. */
export function DataValuePicker({ doc, data, onInsert, onClose }: { doc: DeckDoc; data: DataMap; onInsert: (token: string) => void; onClose: () => void }) {
  const { datasetLabel } = useStudio()
  const specs = useMemo(() => collectQueries(doc), [doc])
  const aliases = Object.keys(specs)
  const [alias, setAlias] = useState(aliases[0] ?? "")
  const res = data[alias]
  const measures = res?.columns.filter((c) => c.kind === "measure") ?? []
  const [measure, setMeasure] = useState("")
  const [stat, setStat] = useState("last")
  const [format, setFormat] = useState("")
  const m = measure || measures[0]?.id || null
  const token = alias ? tokenBody(alias, m, stat, format || undefined) : ""
  const preview = alias ? resolveToken(token.slice(2, -2), data) : null

  const titleFor = (a: string) => {
    for (const s of doc.slides) for (const b of s.blocks) if ((b.type === "chart" || b.type === "table") && (b.query ? b.id : b.query_ref) === a && b.title) return `${b.title} (${datasetLabel(specs[a].dataset)})`
    return `${a} (${datasetLabel(specs[a]?.dataset ?? "")})`
  }

  return (
    <Modal
      title="Insert data value"
      onClose={onClose}
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" disabled={!preview?.ok} onClick={() => onInsert(token)}>
            Insert
          </Button>
        </>
      }
    >
      {aliases.length === 0 ? (
        <p className="text-sm text-muted-foreground">This deck has no data yet. Add a chart or KPI with the data builder first; its query can then be referenced from text.</p>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">Numbers in text are inserted by reference, so they always match your data and update when it is refreshed.</p>
          <Field label="Data source" htmlFor="dv-alias">
            <select id="dv-alias" className={fieldCls} value={alias} onChange={(e) => { setAlias(e.target.value); setMeasure("") }}>
              {aliases.map((a) => (
                <option key={a} value={a}>
                  {titleFor(a)}
                </option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Measure" htmlFor="dv-m">
              <select id="dv-m" className={fieldCls} value={m ?? ""} onChange={(e) => setMeasure(e.target.value)} disabled={!measures.length}>
                {measures.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Value" htmlFor="dv-s">
              <select id="dv-s" className={fieldCls} value={stat} onChange={(e) => setStat(e.target.value)}>
                {STATS.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Format" htmlFor="dv-f">
            <select id="dv-f" className={fieldCls} value={format} onChange={(e) => setFormat(e.target.value)}>
              <option value="">Automatic</option>
              {TOKEN_FORMATS.map((f) => (
                <option key={f}>{f}</option>
              ))}
            </select>
          </Field>
          <div className="rounded-md border border-border bg-secondary/30 p-3 text-sm">
            {!res ? (
              <span className="text-muted-foreground">Data for this source has not loaded.</span>
            ) : preview?.ok ? (
              <>
                <span className="text-muted-foreground">Preview: </span>
                <strong className="text-foreground">{preview.display}</strong>
              </>
            ) : (
              <span className="text-amber-300">{preview?.reason}</span>
            )}
            <div className="mt-1 font-mono text-[11px] text-muted-foreground">{token}</div>
          </div>
        </div>
      )}
    </Modal>
  )
}
