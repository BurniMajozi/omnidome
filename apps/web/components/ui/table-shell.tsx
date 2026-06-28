"use client"

import { useState, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Plus, Download, RefreshCw, Trash2, MoreVertical, Search, X } from "lucide-react"
import { cn } from "@/lib/utils"

// ── Column definition ─────────────────────────────────────────────────────────

export interface TableColumn<T = Record<string, unknown>> {
  key: string
  label: string
  /** How to render a cell value. Defaults to String(value). */
  render?: (value: unknown, row: T) => ReactNode
  /**
   * Input type for the Add/Edit form.
   * Omit (or set calculated:true) to skip this field in the form.
   */
  inputType?: "text" | "number" | "date" | "select" | "email" | "tel" | "range"
  /** Skip this column in the form (auto-calculated values). */
  calculated?: boolean
  /** Options for select inputs */
  options?: string[]
  /** Default value shown in the form */
  defaultValue?: string | number
  /** Min / max / step for range or number inputs */
  min?: number
  max?: number
  step?: number
}

// ── CSV export ────────────────────────────────────────────────────────────────

function exportCSV<T extends { id: string | number }>(
  title: string,
  columns: TableColumn<T>[],
  data: T[],
) {
  const headers = columns.map((c) => c.label).join(",")
  const rows = data.map((row) =>
    columns.map((c) => {
      const val = (row as Record<string, unknown>)[c.key]
      const str = val == null ? "" : String(val)
      return str.includes(",") || str.includes('"') ? `"${str.replace(/"/g, '""')}"`  : str
    }).join(",")
  ).join("\n")
  const blob = new Blob([`${headers}\n${rows}`], { type: "text/csv" })
  const url = URL.createObjectURL(blob)
  const a = Object.assign(document.createElement("a"), {
    href: url,
    download: `${title.toLowerCase().replace(/\s+/g, "-")}.csv`,
  })
  a.click()
  URL.revokeObjectURL(url)
}

// ── Add/Edit form modal ───────────────────────────────────────────────────────

interface RecordFormProps<T extends { id: string | number }> {
  title: string
  columns: TableColumn<T>[]
  initial?: Partial<Record<string, unknown>>
  onSubmit: (record: Record<string, unknown>) => void
  onCancel: () => void
}

function RecordForm<T extends { id: string | number }>({
  title,
  columns,
  initial = {},
  onSubmit,
  onCancel,
}: RecordFormProps<T>) {
  // Exclude calculated and non-form columns
  const formCols = columns.filter((c) => c.inputType && !c.calculated)

  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    formCols.forEach((c) => {
      const v = initial[c.key] ?? c.defaultValue ?? ""
      init[c.key] = String(v)
    })
    return init
  })

  const set = (key: string, val: string) => setValues((p) => ({ ...p, [key]: val }))

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const record: Record<string, unknown> = { ...initial, id: initial.id ?? `rec-${Date.now()}` }
    formCols.forEach((c) => {
      record[c.key] = (c.inputType === "number" || c.inputType === "range")
        ? Number(values[c.key])
        : values[c.key]
    })
    onSubmit(record)
  }

  return (
    /* Backdrop */
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl border border-border bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-base font-semibold text-foreground">{title}</h2>
          <button onClick={onCancel} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-5">
          <div className="grid gap-4" style={{ gridTemplateColumns: formCols.length > 4 ? "1fr 1fr" : "1fr" }}>
            {formCols.map((col) => (
              <div key={col.key} className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {col.label}
                  {col.inputType === "range" && (
                    <span className="ml-2 normal-case text-primary font-semibold">{values[col.key]}</span>
                  )}
                </label>

                {/* SELECT — dropdown */}
                {col.inputType === "select" && (
                  <select
                    value={values[col.key]}
                    onChange={(e) => set(col.key, e.target.value)}
                    className="h-9 rounded-md border border-border bg-secondary/50 px-3 text-sm text-foreground focus:border-primary/60 focus:outline-none"
                  >
                    {(col.options ?? []).map((opt) => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                )}

                {/* RANGE — slider with live value */}
                {col.inputType === "range" && (
                  <input
                    type="range"
                    min={col.min ?? 0}
                    max={col.max ?? 100}
                    step={col.step ?? 1}
                    value={values[col.key] || String(col.min ?? 0)}
                    onChange={(e) => set(col.key, e.target.value)}
                    className="h-2 w-full cursor-pointer accent-primary"
                  />
                )}

                {/* DATE — native calendar picker */}
                {col.inputType === "date" && (
                  <input
                    type="date"
                    value={values[col.key]}
                    onChange={(e) => set(col.key, e.target.value)}
                    className="h-9 rounded-md border border-border bg-secondary/50 px-3 text-sm text-foreground focus:border-primary/60 focus:outline-none [color-scheme:dark]"
                  />
                )}

                {/* All other text-like inputs */}
                {col.inputType !== "select" && col.inputType !== "range" && col.inputType !== "date" && (
                  <Input
                    type={col.inputType}
                    value={values[col.key]}
                    onChange={(e) => set(col.key, e.target.value)}
                    className="h-9 bg-secondary/50 border-border text-sm"
                    placeholder={col.label}
                    min={col.min}
                    max={col.max}
                    step={col.step}
                  />
                )}
              </div>
            ))}
          </div>

          <div className="mt-6 flex items-center justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" variant="cta" size="sm">
              {initial.id ? "Save Changes" : "Add Record"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main TableShell ───────────────────────────────────────────────────────────

interface TableShellProps<T extends { id: string | number }> {
  title: string
  columns: TableColumn<T>[]
  data: T[]
  onAdd?: (record: T) => void
  addLabel?: string
  onDelete?: (id: string | number) => void
  onEdit?: (record: T) => void
  onRefresh?: () => void
  extraActions?: ReactNode
  searchable?: boolean
  searchPlaceholder?: string
  rowCount?: number
  className?: string
}

export function TableShell<T extends { id: string | number }>({
  title,
  columns,
  data,
  onAdd,
  addLabel = "Add Record",
  onDelete,
  onEdit,
  onRefresh,
  extraActions,
  searchable = true,
  searchPlaceholder = "Search...",
  rowCount = 50,
  className,
}: TableShellProps<T>) {
  const [search, setSearch] = useState("")
  const [selected, setSelected] = useState<Set<string | number>>(new Set())
  const [showForm, setShowForm] = useState(false)
  const [editRow, setEditRow] = useState<T | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | number | null>(null)

  const filtered = search
    ? data.filter((row) =>
        columns.some((col) => {
          const v = (row as Record<string, unknown>)[col.key]
          return v != null && String(v).toLowerCase().includes(search.toLowerCase())
        })
      )
    : data

  const visible = filtered.slice(0, rowCount)
  const allSelected = visible.length > 0 && selected.size === visible.length

  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set(visible.map((r) => r.id)))

  const toggleRow = (id: string | number) =>
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const handleBulkDelete = () => {
    selected.forEach((id) => onDelete?.(id))
    setSelected(new Set())
  }

  const handleFormSubmit = (record: Record<string, unknown>) => {
    if (editRow) {
      onEdit?.(record as T)
    } else {
      onAdd?.(record as T)
    }
    setShowForm(false)
    setEditRow(null)
  }

  const openEdit = (row: T) => {
    setEditRow(row)
    setShowForm(true)
  }

  const hasFormCols = columns.some((c) => c.inputType && !c.calculated)

  return (
    <>
      {/* Add / Edit modal */}
      {showForm && (
        <RecordForm
          title={editRow ? `Edit ${title.replace(/s$/, "")}` : `Add ${title.replace(/s$/, "")}`}
          columns={columns}
          initial={editRow ? (editRow as Record<string, unknown>) : {}}
          onSubmit={handleFormSubmit}
          onCancel={() => { setShowForm(false); setEditRow(null) }}
        />
      )}

      <Card className={cn("border-border bg-card", className)}>
        <CardHeader className="pb-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            {/* Left: title + counters */}
            <div className="flex flex-wrap items-center gap-2 min-w-0">
              <h3 className="card-title shrink-0">{title}</h3>
              <span className="text-xs text-muted-foreground">
                {filtered.length} {filtered.length === 1 ? "record" : "records"}
              </span>
              {selected.size > 0 && (
                <span className="flex items-center gap-1 rounded-md bg-destructive/10 px-2 py-0.5 text-xs text-destructive">
                  {selected.size} selected
                  <button onClick={() => setSelected(new Set())} className="ml-0.5 hover:opacity-70">
                    <X className="h-3 w-3" />
                  </button>
                </span>
              )}
            </div>

            {/* Right: actions */}
            <div className="flex flex-wrap items-center gap-2 shrink-0">
              {selected.size > 0 && onDelete && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleBulkDelete}
                  className="border-destructive/50 text-destructive hover:bg-destructive/10"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete {selected.size}
                </Button>
              )}

              {searchable && (
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={searchPlaceholder}
                    className="h-8 w-40 pl-8 text-xs bg-secondary/50 transition-[width] focus:w-52"
                  />
                </div>
              )}

              {extraActions}

              {onRefresh && (
                <Button variant="outline" size="sm" onClick={onRefresh}>
                  <RefreshCw className="h-3.5 w-3.5" />
                  Refresh
                </Button>
              )}

              <Button variant="outline" size="sm" onClick={() => exportCSV(title, columns, filtered)}>
                <Download className="h-3.5 w-3.5" />
                Export CSV
              </Button>

              {onAdd && (
                <Button
                  variant="cta"
                  size="sm"
                  onClick={() => {
                    setEditRow(null)
                    if (hasFormCols) {
                      setShowForm(true)
                    } else {
                      const blank: Record<string, unknown> = { id: `rec-${Date.now()}` }
                      columns.forEach((c) => { blank[c.key] = c.defaultValue ?? "" })
                      onAdd(blank as T)
                    }
                  }}
                >
                  <Plus className="h-3.5 w-3.5" />
                  {addLabel}
                </Button>
              )}
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          {/* Inline delete confirm */}
          {confirmDeleteId !== null && (
            <div className="flex items-center justify-between gap-3 border-y border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm">
              <span className="text-destructive font-medium">Delete this record? This cannot be undone.</span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setConfirmDeleteId(null)}>Cancel</Button>
                <Button
                  size="sm"
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  onClick={() => { onDelete?.(confirmDeleteId); setConfirmDeleteId(null) }}
                >
                  Delete
                </Button>
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  {onDelete && (
                    <th className="w-10">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 rounded border-border accent-primary"
                        checked={allSelected}
                        onChange={toggleAll}
                      />
                    </th>
                  )}
                  {columns.map((col) => <th key={col.key}>{col.label}</th>)}
                  {(onEdit || onDelete) && <th className="w-10" />}
                </tr>
              </thead>
              <tbody>
                {visible.length === 0 ? (
                  <tr>
                    <td
                      colSpan={columns.length + (onDelete ? 1 : 0) + (onEdit || onDelete ? 1 : 0)}
                      className="py-10 text-center text-sm text-muted-foreground"
                    >
                      {search ? "No records match your search." : "No records found."}
                    </td>
                  </tr>
                ) : (
                  visible.map((row) => (
                    <tr key={row.id} className={cn(selected.has(row.id) && "bg-primary/5")}>
                      {onDelete && (
                        <td>
                          <input
                            type="checkbox"
                            className="h-3.5 w-3.5 rounded border-border accent-primary"
                            checked={selected.has(row.id)}
                            onChange={() => toggleRow(row.id)}
                          />
                        </td>
                      )}
                      {columns.map((col) => (
                        <td key={col.key}>
                          {col.render
                            ? col.render((row as Record<string, unknown>)[col.key], row)
                            : String((row as Record<string, unknown>)[col.key] ?? "")}
                        </td>
                      ))}
                      {(onEdit || onDelete) && (
                        <td className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon-sm">
                                <MoreVertical className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-40">
                              {onEdit && (
                                <DropdownMenuItem onClick={() => openEdit(row)}>
                                  Edit
                                </DropdownMenuItem>
                              )}
                              <DropdownMenuItem onClick={() => openEdit(row)}>
                                View Details
                              </DropdownMenuItem>
                              {onDelete && (
                                <DropdownMenuItem
                                  className="text-destructive focus:text-destructive focus:bg-destructive/10"
                                  onClick={() => setConfirmDeleteId(row.id)}
                                >
                                  <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                                  Delete
                                </DropdownMenuItem>
                              )}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </td>
                      )}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {filtered.length > rowCount && (
            <div className="border-t border-border px-4 py-2.5 text-xs text-muted-foreground text-right">
              Showing {rowCount} of {filtered.length} records
            </div>
          )}
        </CardContent>
      </Card>
    </>
  )
}
