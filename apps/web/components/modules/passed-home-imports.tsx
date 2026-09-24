"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  AlertTriangle, ChevronDown, ChevronRight, Download, FileSpreadsheet, Loader2, Upload, X,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  FNO_PORTALS,
  PASSED_HOME_COLUMNS,
  PASSED_HOME_UPLOAD,
  REJECT_REASON_LABELS,
  fnoApi,
  type PassedHomeImport,
  type PassedHomeImportDetail,
  type PassedHomeRow,
} from "@/lib/fno-api"

type Phase = { kind: "processing" } | { kind: "geocoding"; done: number; total: number }

const STATUS_LABELS: Record<string, { label: string; className: string }> = {
  uploaded: { label: "Processing", className: "border-blue-500/40 text-blue-400" },
  parsing: { label: "Processing", className: "border-blue-500/40 text-blue-400" },
  imported: { label: "Imported", className: "border-emerald-500/40 text-emerald-400" },
  partial: { label: "No new homes", className: "border-amber-500/40 text-amber-400" },
  failed: { label: "Failed", className: "border-red-500/40 text-red-400" },
}

const TERMINAL = new Set(["imported", "partial", "failed"])

function omitKey<V>(record: Record<string, V>, key: string): Record<string, V> {
  const next = { ...record }
  delete next[key]
  return next
}

function formatDate(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" }) : "—"
}

function formatBytes(n: number) {
  return n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`
}

function downloadTemplate() {
  const header = "Site Address,Suburb,Town,Postcode,RFS Date,Units\n"
  const url = URL.createObjectURL(new Blob([header], { type: "text/csv" }))
  const link = document.createElement("a")
  link.href = url
  link.download = "homes-passed-template.csv"
  link.click()
  URL.revokeObjectURL(url)
}

// Column widths shared by the import form and the table below it, so the form
// fields line up with the columns they feed (File, FNO).
const FILE_COL = "min-w-[220px] w-[38%]"
const FNO_COL = "w-[16%]"

export function PassedHomeImports({ onImportFinished }: { onImportFinished: () => void }) {
  const [imports, setImports] = useState<PassedHomeImport[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [phases, setPhases] = useState<Record<string, Phase>>({})
  const [expanded, setExpanded] = useState<string | null>(null)
  const [details, setDetails] = useState<Record<string, { detail?: PassedHomeImportDetail; issues?: PassedHomeRow[]; error?: string }>>({})

  // Import form state
  const [formOpen, setFormOpen] = useState(false)
  const [portal, setPortal] = useState(FNO_PORTALS[0].portal)
  const [otherName, setOtherName] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const onFinishedRef = useRef(onImportFinished)
  onFinishedRef.current = onImportFinished

  useEffect(() => {
    fnoApi.listPassedHomeImports()
      .then((list) => {
        setImports(list)
        // Imports still processing (e.g. sent through the API) are tracked live too.
        const inFlight = list.filter((i) => !TERMINAL.has(i.status))
        if (inFlight.length) {
          setPhases((prev) => ({ ...prev, ...Object.fromEntries(inFlight.map((i) => [i.id, { kind: "processing" } as Phase])) }))
        }
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Couldn't load imports"))
  }, [])

  const pickFile = (f: File | undefined | null) => {
    setFormError(null)
    if (!f) return
    const ext = f.name.split(".").pop()?.toLowerCase() ?? ""
    if (!PASSED_HOME_UPLOAD.extensions.includes(ext)) {
      setFile(null)
      setFormError("Use a .csv, .xlsx or .xls file")
      return
    }
    if (f.size > PASSED_HOME_UPLOAD.maxBytes) {
      setFile(null)
      setFormError(`That file is ${formatBytes(f.size)}. The limit is 25 MB`)
      return
    }
    setFile(f)
  }

  const resetForm = () => {
    setFile(null)
    setOtherName("")
    setFormError(null)
    if (fileInput.current) fileInput.current.value = ""
  }

  const handleImport = async (e: React.FormEvent) => {
    e.preventDefault()
    const selected = FNO_PORTALS.find((p) => p.portal === portal)!
    const fnoName = portal === "other" ? otherName.trim() : selected.name
    if (!fnoName) {
      setFormError("Enter the FNO's name")
      return
    }
    if (!file) {
      setFormError("Choose a file to import")
      return
    }
    setUploading(true)
    setFormError(null)
    try {
      const created = await fnoApi.uploadPassedHomes(fnoName, portal, file)
      setImports((prev) => [created, ...(prev ?? [])])
      setPhases((prev) => ({ ...prev, [created.id]: { kind: "processing" } }))
      resetForm()
      setFormOpen(false)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Upload failed")
    } finally {
      setUploading(false)
    }
  }

  // Poll every in-flight import: first until the import finishes, then until
  // geocoding (started automatically, needed for location-based ads) is done.
  const phasesRef = useRef(phases)
  phasesRef.current = phases
  const ticking = useRef(false)
  const tick = useCallback(async () => {
    // A slow tick must not overlap the next one (it could trigger geocoding twice).
    if (ticking.current) return
    ticking.current = true
    try {
      await pollOnce()
    } finally {
      ticking.current = false
    }
  }, [])

  const pollOnce = async () => {
    const entries = Object.entries(phasesRef.current)
    for (const [id, phase] of entries) {
      try {
        if (phase.kind === "processing") {
          const d = await fnoApi.getPassedHomeImport(id)
          setImports((prev) => (prev ?? []).map((i) => (i.id === id ? { ...i, ...d } : i)))
          setDetails((prev) => ({ ...prev, [id]: { ...prev[id], detail: d } }))
          if (!TERMINAL.has(d.status)) continue
          if (d.status === "imported" && d.inserted_rows > 0) {
            const q = await fnoApi.triggerGeocode(id)
            setPhases((prev) => ({ ...prev, [id]: { kind: "geocoding", done: 0, total: q.queued } }))
            if (q.queued === 0) {
              setPhases((prev) => omitKey(prev, id))
              onFinishedRef.current()
            }
          } else {
            setPhases((prev) => omitKey(prev, id))
            onFinishedRef.current()
          }
        } else {
          const s = await fnoApi.getGeocodeStatus(id)
          const total = Math.max(phase.total, s.pending + s.geocoded + s.failed)
          if (s.pending === 0) {
            setPhases((prev) => omitKey(prev, id))
            onFinishedRef.current()
          } else {
            setPhases((prev) => ({ ...prev, [id]: { kind: "geocoding", done: s.geocoded + s.failed, total } }))
          }
        }
      } catch {
        // Transient: keep polling on the next tick.
      }
    }
  }

  const polling = Object.keys(phases).length > 0
  useEffect(() => {
    if (!polling) return
    const timer = setInterval(tick, 2000)
    return () => clearInterval(timer)
  }, [polling, tick])

  const toggleDetails = async (imp: PassedHomeImport) => {
    if (expanded === imp.id) {
      setExpanded(null)
      return
    }
    setExpanded(imp.id)
    if (details[imp.id]?.detail && (imp.invalid_rows === 0 || details[imp.id]?.issues)) return
    try {
      const [detail, issues] = await Promise.all([
        fnoApi.getPassedHomeImport(imp.id),
        imp.invalid_rows > 0 ? fnoApi.listImportIssues(imp.id) : Promise.resolve([] as PassedHomeRow[]),
      ])
      setDetails((prev) => ({ ...prev, [imp.id]: { detail, issues } }))
    } catch (err) {
      setDetails((prev) => ({ ...prev, [imp.id]: { error: err instanceof Error ? err.message : "Couldn't load details" } }))
    }
  }

  const statusCell = (imp: PassedHomeImport) => {
    const phase = phases[imp.id]
    if (phase?.kind === "processing" || (!phase && !TERMINAL.has(imp.status))) {
      return (
        <span className="inline-flex items-center gap-1.5 text-[11px] text-blue-400">
          <Loader2 className="h-3 w-3 animate-spin" /> Processing…
        </span>
      )
    }
    if (phase?.kind === "geocoding") {
      return (
        <span className="inline-flex items-center gap-1.5 text-[11px] text-blue-400">
          <Loader2 className="h-3 w-3 animate-spin" /> Placing on map {phase.done}/{phase.total}
        </span>
      )
    }
    const s = STATUS_LABELS[imp.status] ?? { label: imp.status, className: "" }
    return <Badge variant="outline" className={`text-[10px] ${s.className}`}>{s.label}</Badge>
  }

  return (
    <div className="surface-card p-5 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
            <FileSpreadsheet className="h-4 w-4 text-cyan-400" />
            FNO homes-passed imports
          </h4>
          <p className="text-xs text-muted-foreground">
            Address lists from FNOs, cleaned, deduplicated and checked against existing customers
          </p>
        </div>
        {!formOpen && (
          <Button size="sm" className="h-8 gap-1.5 text-xs" onClick={() => setFormOpen(true)}>
            <Upload className="h-3.5 w-3.5" /> Import FNO file
          </Button>
        )}
      </div>

      {formOpen && (
        <form onSubmit={handleImport} className="rounded-xl border border-primary/30 bg-primary/5 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground">Import a homes-passed file</span>
            <button type="button" aria-label="Close import form" className="rounded p-1 text-muted-foreground hover:bg-muted"
              onClick={() => { resetForm(); setFormOpen(false) }}>
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="flex flex-wrap items-stretch gap-3">
            <div
              className={`${FILE_COL} flex-1 rounded-lg border border-dashed p-3 text-xs transition-colors cursor-pointer ${
                dragging ? "border-primary bg-primary/10" : "border-border bg-background hover:border-primary/60"
              }`}
              onClick={() => fileInput.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); pickFile(e.dataTransfer.files?.[0]) }}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") fileInput.current?.click() }}
              aria-label="Choose a CSV or Excel file"
            >
              <input ref={fileInput} type="file" accept=".csv,.xlsx,.xls" className="hidden"
                onChange={(e) => pickFile(e.target.files?.[0])} />
              {file ? (
                <div className="flex items-center gap-2 text-foreground">
                  <FileSpreadsheet className="h-4 w-4 text-cyan-400 shrink-0" />
                  <span className="truncate font-medium">{file.name}</span>
                  <span className="text-muted-foreground">{formatBytes(file.size)}</span>
                </div>
              ) : (
                <div className="text-muted-foreground">
                  <span className="font-medium text-foreground">Drop a CSV or Excel file</span> or click to browse · up to 25 MB
                </div>
              )}
            </div>
            <div className={`${FNO_COL} min-w-[160px] space-y-1.5`}>
              <select
                value={portal}
                onChange={(e) => { setPortal(e.target.value); setFormError(null) }}
                aria-label="FNO"
                className="w-full rounded-lg border border-border bg-background px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
              >
                {FNO_PORTALS.map((p) => <option key={p.portal} value={p.portal}>{p.label}</option>)}
              </select>
              {portal === "other" && (
                <input
                  type="text"
                  value={otherName}
                  onChange={(e) => { setOtherName(e.target.value); setFormError(null) }}
                  placeholder="FNO name"
                  aria-label="FNO name"
                  maxLength={100}
                  className="w-full rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                />
              )}
            </div>
            <div className="flex items-start gap-2">
              <Button type="submit" size="sm" className="h-9 gap-1.5 text-xs" disabled={uploading}>
                {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
                {uploading ? "Uploading…" : "Import homes"}
              </Button>
            </div>
          </div>
          {formError && <p className="text-[11px] text-red-400">{formError}</p>}
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/60 pt-2 text-[11px] text-muted-foreground">
            <span>
              Columns we read:{" "}
              {PASSED_HOME_COLUMNS.map((c, i) => (
                <span key={c.field} title={`Accepted headers: ${c.accepts}`}>
                  <span className={c.required ? "font-semibold text-foreground" : ""}>{c.label}{c.required ? " (required)" : ""}</span>
                  {i < PASSED_HOME_COLUMNS.length - 1 ? ", " : ""}
                </span>
              ))}
            </span>
            <button type="button" onClick={downloadTemplate} className="inline-flex items-center gap-1 text-primary hover:underline">
              <Download className="h-3 w-3" /> Download template
            </button>
          </div>
        </form>
      )}

      {loadError ? (
        <p className="text-xs text-red-400">Couldn&apos;t load imports: {loadError}</p>
      ) : !imports ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading imports…
        </div>
      ) : imports.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground flex flex-wrap items-center justify-between gap-2">
          <span>No FNO files imported yet. Import a homes-passed list to start building target segments.</span>
          {!formOpen && (
            <Button size="sm" variant="outline" className="h-7 gap-1 text-[11px]" onClick={() => setFormOpen(true)}>
              <Upload className="h-3 w-3" /> Import FNO file
            </Button>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className={`py-2 pr-3 font-medium ${FILE_COL}`}>File</th>
                <th className={`py-2 pr-3 font-medium ${FNO_COL}`}>FNO</th>
                <th className="py-2 pr-3 font-medium">Imported</th>
                <th className="py-2 pr-3 text-right font-medium">Rows</th>
                <th className="py-2 pr-3 text-right font-medium">New homes</th>
                <th className="py-2 pr-3 text-right font-medium">Duplicates</th>
                <th className="py-2 pr-3 text-right font-medium">Invalid</th>
                <th className="py-2 pr-3 text-right font-medium">Customers</th>
                <th className="py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {imports.map((i) => {
                const open = expanded === i.id
                const d = details[i.id]
                return [
                  <tr key={i.id} className="border-b border-border/50 hover:bg-muted/20 cursor-pointer" onClick={() => toggleDetails(i)}>
                    <td className="py-2 pr-3 font-medium text-foreground">
                      <div className="flex items-center gap-1.5 max-w-[320px]">
                        {open ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />}
                        <span className="truncate" title={i.file_name}>{i.file_name}</span>
                      </div>
                    </td>
                    <td className="py-2 pr-3 capitalize">{i.fno_name}</td>
                    <td className="py-2 pr-3">{formatDate(i.created_at)}</td>
                    <td className="py-2 pr-3 text-right">{i.total_rows}</td>
                    <td className="py-2 pr-3 text-right text-emerald-400">{i.inserted_rows}</td>
                    <td className="py-2 pr-3 text-right">{i.duplicate_rows}</td>
                    <td className="py-2 pr-3 text-right">
                      {i.invalid_rows > 0 ? (
                        <span className="inline-flex items-center gap-1 text-amber-400">
                          <AlertTriangle className="h-3 w-3" /> {i.invalid_rows}
                        </span>
                      ) : 0}
                    </td>
                    <td className="py-2 pr-3 text-right">{i.suppressed_rows}</td>
                    <td className="py-2">{statusCell(i)}</td>
                  </tr>,
                  open && (
                    <tr key={`${i.id}-details`} className="border-b border-border/50 bg-muted/10">
                      <td colSpan={9} className="px-5 py-3">
                        {d?.error ? (
                          <p className="text-[11px] text-red-400">{d.error}</p>
                        ) : !d?.detail ? (
                          <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
                            <Loader2 className="h-3 w-3 animate-spin" /> Loading details…
                          </span>
                        ) : (
                          <div className="grid gap-3 md:grid-cols-2 text-[11px]">
                            <div className="space-y-1">
                              <div className="font-semibold text-foreground">Columns read from the file</div>
                              {d.detail.column_map && Object.keys(d.detail.column_map).length > 0 ? (
                                <ul className="space-y-0.5 text-muted-foreground">
                                  {Object.entries(d.detail.column_map).map(([field, header]) => (
                                    <li key={field}>
                                      &ldquo;{header}&rdquo; → {PASSED_HOME_COLUMNS.find((c) => c.field === field)?.label ?? field}
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="text-muted-foreground">No recognised columns.</p>
                              )}
                              {d.detail.error_message && (
                                <p className="text-red-400">{d.detail.error_message}</p>
                              )}
                            </div>
                            <div className="space-y-1">
                              <div className="font-semibold text-foreground">
                                {i.invalid_rows > 0 ? `Rows we couldn't use (${i.invalid_rows})` : "Issues"}
                              </div>
                              {i.invalid_rows === 0 ? (
                                <p className="text-muted-foreground">Every row had an address.</p>
                              ) : !d.issues ? (
                                <span className="text-muted-foreground">Loading…</span>
                              ) : (
                                <ul className="max-h-40 overflow-y-auto space-y-0.5 text-muted-foreground">
                                  {d.issues.map((r) => (
                                    <li key={r.id}>
                                      <span className="text-foreground">{r.address_raw || "(blank address)"}</span>
                                      {" — "}
                                      {REJECT_REASON_LABELS[r.reject_reason ?? ""] ?? r.reject_reason}
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          </div>
                        )}
                      </td>
                    </tr>
                  ),
                ]
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
