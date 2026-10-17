"use client"

import { useState } from "react"
import { Check, Pencil, Plus, Trash2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { addListValue, deleteListValue, renameListValue, type Lists } from "@/lib/catalogue-api"
import { selectCls } from "./shared"

interface Props {
  label: string
  kind: "category" | "range" | "family"
  value: string
  options: string[]
  /** For ranges: the category they belong to. */
  parent?: string
  lists: Lists
  disabled?: boolean
  onChange: (value: string) => void
  /** Called after a list mutation so the caller can refetch lists (and products when a rename propagated). */
  onListsChanged: () => Promise<void>
  notify: (message: string) => void
}

/** A select backed by a managed list, with visible rename (pen), add (plus) and delete (bin). */
export function ManagedSelect({ label, kind, value, options, parent = "", lists, disabled, onChange, onListsChanged, notify }: Props) {
  const [mode, setMode] = useState<null | "add" | "rename" | "delete">(null)
  const [text, setText] = useState("")
  const [busy, setBusy] = useState(false)

  const item = lists.items.find((i) => i.kind === kind && i.name === value && (kind !== "range" || i.parent === parent))

  async function run(fn: () => Promise<void>) {
    setBusy(true)
    try {
      await fn()
      await onListsChanged()
      setMode(null)
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not update the list")
    } finally {
      setBusy(false)
    }
  }

  const save = () =>
    run(async () => {
      const name = text.trim()
      if (!name) throw new Error("Enter a name.")
      if (mode === "add") {
        await addListValue(kind, name, kind === "range" ? parent : "")
        onChange(name)
        notify(`Added “${name}”.`)
      } else if (mode === "rename" && item && name !== value) {
        const r = await renameListValue(item.id, name)
        onChange(name)
        notify(`Renamed to “${name}”${r.updated_products ? ` on ${r.updated_products} product(s)` : ""}.`)
      }
    })

  const remove = () =>
    run(async () => {
      if (!item) return
      await deleteListValue(item.id)
      onChange("")
      notify(`Deleted “${value}”.`)
    })

  if (mode === "delete") {
    return (
      <div className="grid gap-1.5 text-xs text-muted-foreground">
        <span>{label}</span>
        <div className="flex items-center gap-2">
          <span className="text-amber-400">Delete “{value}”?{kind === "category" ? " Its empty ranges go too." : ""}</span>
          <Button type="button" size="sm" variant="destructive" className="h-8 text-xs" disabled={busy} onClick={remove}>Delete</Button>
          <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={() => setMode(null)}>Cancel</Button>
        </div>
      </div>
    )
  }
  if (mode) {
    return (
      <div className="grid gap-1.5 text-xs text-muted-foreground">
        <span>{mode === "add" ? `New ${label.toLowerCase()}` : `Rename ${label.toLowerCase()}`}</span>
        <div className="flex items-center gap-1.5">
          <Input
            autoFocus value={text} onChange={(e) => setText(e.target.value)} className="h-9 text-xs" aria-label={`${label} name`}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void save() } if (e.key === "Escape") setMode(null) }}
          />
          <Button type="button" size="sm" className="h-9 w-9 p-0" disabled={busy} onClick={save} aria-label="Save"><Check className="h-4 w-4" /></Button>
          <Button type="button" size="sm" variant="outline" className="h-9 w-9 p-0" onClick={() => setMode(null)} aria-label="Cancel"><X className="h-4 w-4" /></Button>
        </div>
      </div>
    )
  }
  return (
    <div className="grid gap-1.5 text-xs text-muted-foreground">
      <label htmlFor={`ms-${kind}`}>{label}</label>
      <div className="flex items-center gap-1.5">
        <select id={`ms-${kind}`} value={value} disabled={disabled} className={selectCls} onChange={(e) => onChange(e.target.value)}>
          {!value && <option value="" disabled>Select…</option>}
          {options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
        <Button type="button" size="sm" variant="outline" className="h-9 w-9 shrink-0 p-0" disabled={!value || disabled} title={`Rename ${label.toLowerCase()}`} aria-label={`Rename ${label.toLowerCase()}`} onClick={() => { setText(value); setMode("rename") }}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <Button type="button" size="sm" variant="outline" className="h-9 w-9 shrink-0 p-0" disabled={disabled} title={`Add ${label.toLowerCase()}`} aria-label={`Add ${label.toLowerCase()}`} onClick={() => { setText(""); setMode("add") }}>
          <Plus className="h-3.5 w-3.5" />
        </Button>
        <Button type="button" size="sm" variant="outline" className="h-9 w-9 shrink-0 p-0 hover:border-red-500/60 hover:text-red-400" disabled={!value || disabled} title={`Delete ${label.toLowerCase()}`} aria-label={`Delete ${label.toLowerCase()}`} onClick={() => setMode("delete")}>
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  )
}
