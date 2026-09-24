"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { ChevronDown, ChevronRight, FileSpreadsheet, Layers, Loader2, MapPin, Target, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DWELLING_LABELS,
  EMPTY_FILTERS,
  fnoApi,
  type DwellingType,
  type GeoArea,
  type GeoSegment,
  type GeoSegmentFilterOptions,
  type GeoSegmentFilters,
  type GeoSegmentPreview,
  type PassedHomeImport,
} from "@/lib/fno-api"

const EXCLUSION_LABELS: Record<keyof GeoSegmentPreview["excluded"], string> = {
  suppressed_customer: "existing customers",
  duplicate: "duplicates",
  invalid: "invalid",
  raw: "not processed",
  not_geocoded: "not on the map yet",
}

function omitKey<V>(record: Record<string, V>, key: string): Record<string, V> {
  const next = { ...record }
  delete next[key]
  return next
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
}

function formatDate(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" }) : "—"
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
        active
          ? "border-primary/60 bg-primary/15 text-primary"
          : "border-border bg-background text-muted-foreground hover:text-foreground"
      }`}
    >
      {children}
    </button>
  )
}

function AreaTable({ areas }: { areas: GeoArea[] }) {
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="border-b border-border text-left text-muted-foreground">
          <th className="py-1.5 pr-2 font-medium">Area</th>
          <th className="py-1.5 pr-2 text-right font-medium">Homes</th>
          <th className="py-1.5 text-right font-medium">Ad radius</th>
        </tr>
      </thead>
      <tbody>
        {areas.map((a) => (
          <tr key={`${a.suburb}|${a.city}|${a.postal_code}`} className="border-b border-border/40">
            <td className="py-1.5 pr-2">
              <div className="flex items-center gap-1 text-foreground">
                <MapPin className="h-3 w-3 shrink-0 text-muted-foreground" />
                {a.suburb ?? "Unknown suburb"}
              </div>
              <div className="pl-4 text-[10px] text-muted-foreground">
                {[a.city, a.postal_code].filter(Boolean).join(" · ")}
              </div>
            </td>
            <td className="py-1.5 pr-2 text-right">{a.homes}</td>
            <td className="py-1.5 text-right text-muted-foreground">
              {a.centroid_lat === null ? "No location" : `${a.suggested_radius_km} km`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
      {children}
    </div>
  )
}

export function SalesLeadSources() {
  const [imports, setImports] = useState<PassedHomeImport[] | null>(null)
  const [options, setOptions] = useState<GeoSegmentFilterOptions | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [filters, setFilters] = useState<GeoSegmentFilters>(EMPTY_FILTERS)
  const [preview, setPreview] = useState<GeoSegmentPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const previewAbort = useRef<AbortController | null>(null)

  const [segments, setSegments] = useState<GeoSegment[] | null>(null)
  const [segmentName, setSegmentName] = useState("")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Record<string, GeoArea[] | "loading">>({})
  const [rowError, setRowError] = useState<Record<string, string>>({})

  useEffect(() => {
    Promise.all([fnoApi.listPassedHomeImports(), fnoApi.getGeoSegmentFilterOptions(), fnoApi.listGeoSegments()])
      .then(([imp, opts, segs]) => {
        setImports(imp)
        setOptions(opts)
        setSegments(segs)
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Couldn't load passed homes"))
  }, [])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    const name = segmentName.trim()
    if (!name) {
      setSaveError("Enter a segment name")
      return
    }
    setSaving(true)
    setSaveError(null)
    try {
      const created = await fnoApi.createGeoSegment(name, filters)
      setSegments((prev) => [created, ...(prev ?? [])])
      setExpanded((prev) => ({ ...prev, [created.id]: created.areas ?? [] }))
      setSegmentName("")
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Couldn't save the segment")
    } finally {
      setSaving(false)
    }
  }

  const toggleAreas = async (seg: GeoSegment) => {
    if (expanded[seg.id]) {
      setExpanded((prev) => omitKey(prev, seg.id))
      return
    }
    setExpanded((prev) => ({ ...prev, [seg.id]: "loading" }))
    try {
      const detail = await fnoApi.getGeoSegment(seg.id)
      setExpanded((prev) => ({ ...prev, [seg.id]: detail.areas ?? [] }))
    } catch (err) {
      setExpanded((prev) => omitKey(prev, seg.id))
      setRowError((prev) => ({ ...prev, [seg.id]: err instanceof Error ? err.message : "Couldn't load areas" }))
    }
  }

  const handleDelete = async (seg: GeoSegment) => {
    if (!window.confirm(`Delete the segment "${seg.name}"? The homes themselves aren't affected.`)) return
    try {
      await fnoApi.deleteGeoSegment(seg.id)
      setSegments((prev) => (prev ?? []).filter((s) => s.id !== seg.id))
    } catch (err) {
      setRowError((prev) => ({ ...prev, [seg.id]: err instanceof Error ? err.message : "Couldn't delete" }))
    }
  }

  // Debounced live count. The previous result stays on screen while the next
  // one loads, so the builder never flashes back to a spinner.
  useEffect(() => {
    const timer = setTimeout(() => {
      previewAbort.current?.abort()
      const controller = new AbortController()
      previewAbort.current = controller
      setPreviewing(true)
      setPreviewError(null)
      fnoApi
        .previewGeoSegment(filters, controller.signal)
        .then((p) => setPreview(p))
        .catch((err) => {
          if (controller.signal.aborted) return
          setPreviewError(err instanceof Error ? err.message : "Couldn't count homes")
        })
        .finally(() => {
          if (previewAbort.current === controller) setPreviewing(false)
        })
    }, 400)
    return () => clearTimeout(timer)
  }, [filters])

  const visibleSuburbs = useMemo(() => {
    if (!options) return []
    return filters.cities.length
      ? options.suburbs.filter((s) => s.city && filters.cities.includes(s.city))
      : options.suburbs
  }, [options, filters.cities])

  const excludedParts = preview
    ? (Object.keys(EXCLUSION_LABELS) as (keyof typeof EXCLUSION_LABELS)[])
        .filter((k) => preview.excluded[k] > 0)
        .map((k) => `${preview.excluded[k]} ${EXCLUSION_LABELS[k]}`)
    : []

  if (loadError) {
    return (
      <div className="surface-card p-5 text-sm text-red-400">
        Couldn&apos;t load FNO passed homes: {loadError}
      </div>
    )
  }

  if (!imports || !options || !segments) {
    return (
      <div className="surface-card flex items-center gap-2 p-5 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading FNO passed homes…
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Past imports */}
      <div className="surface-card p-5 space-y-4">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
            <FileSpreadsheet className="h-4 w-4 text-cyan-400" />
            FNO homes-passed imports
          </h4>
          <p className="text-xs text-muted-foreground">
            Address lists from FNOs, cleaned, deduplicated and checked against existing customers
          </p>
        </div>
        {imports.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground">
            No FNO files imported yet. Imported homes-passed lists appear here with their cleaning results.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">File</th>
                  <th className="py-2 pr-3 font-medium">FNO</th>
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
                {imports.map((i) => (
                  <tr key={i.id} className="border-b border-border/50">
                    <td className="py-2 pr-3 font-medium text-foreground max-w-[220px] truncate" title={i.file_name}>
                      {i.file_name}
                    </td>
                    <td className="py-2 pr-3 capitalize">{i.fno_name}</td>
                    <td className="py-2 pr-3">{formatDate(i.created_at)}</td>
                    <td className="py-2 pr-3 text-right">{i.total_rows}</td>
                    <td className="py-2 pr-3 text-right text-emerald-400">{i.inserted_rows}</td>
                    <td className="py-2 pr-3 text-right">{i.duplicate_rows}</td>
                    <td className="py-2 pr-3 text-right">{i.invalid_rows}</td>
                    <td className="py-2 pr-3 text-right">{i.suppressed_rows}</td>
                    <td className="py-2">
                      <Badge variant="outline" className="text-[10px] capitalize">{i.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Segment builder */}
      <div className="surface-card p-5 space-y-4">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
            <Target className="h-4 w-4 text-purple-400" />
            Target segment
          </h4>
          <p className="text-xs text-muted-foreground">
            Pick the homes to target. Existing customers are always left out.
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <div className="space-y-4">
            {options.fno_names.length > 1 && (
              <FilterGroup label="FNO">
                <div className="flex flex-wrap gap-1.5">
                  {options.fno_names.map((f) => (
                    <Chip key={f} active={filters.fno_names.includes(f)}
                      onClick={() => setFilters((s) => ({ ...s, fno_names: toggle(s.fno_names, f) }))}>
                      {f}
                    </Chip>
                  ))}
                </div>
              </FilterGroup>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <FilterGroup label="Import">
                <select
                  value={filters.import_ids[0] ?? ""}
                  onChange={(e) => setFilters((s) => ({ ...s, import_ids: e.target.value ? [e.target.value] : [] }))}
                  className="w-full rounded-lg border border-border bg-background px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="">All imports</option>
                  {options.imports.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.file_name} · {formatDate(i.created_at)}
                    </option>
                  ))}
                </select>
              </FilterGroup>
              <FilterGroup label="Passed between">
                <div className="flex items-center gap-1.5">
                  <input
                    type="date"
                    aria-label="Passed from"
                    value={filters.date_passed_from ?? ""}
                    onChange={(e) => setFilters((s) => ({ ...s, date_passed_from: e.target.value || null }))}
                    className="w-full rounded-lg border border-border bg-background px-2 py-1.5 text-xs"
                  />
                  <span className="text-xs text-muted-foreground">to</span>
                  <input
                    type="date"
                    aria-label="Passed to"
                    value={filters.date_passed_to ?? ""}
                    onChange={(e) => setFilters((s) => ({ ...s, date_passed_to: e.target.value || null }))}
                    className="w-full rounded-lg border border-border bg-background px-2 py-1.5 text-xs"
                  />
                </div>
              </FilterGroup>
            </div>

            {options.cities.length > 0 && (
              <FilterGroup label="City">
                <div className="flex flex-wrap gap-1.5">
                  {options.cities.map((c) => (
                    <Chip key={c} active={filters.cities.includes(c)}
                      onClick={() => setFilters((s) => ({ ...s, cities: toggle(s.cities, c), suburbs: [] }))}>
                      {c}
                    </Chip>
                  ))}
                </div>
              </FilterGroup>
            )}

            {visibleSuburbs.length > 0 && (
              <FilterGroup label="Suburbs">
                <div className="flex flex-wrap gap-1.5">
                  {visibleSuburbs.map((s) => (
                    <Chip key={`${s.suburb}|${s.city}`} active={filters.suburbs.includes(s.suburb)}
                      onClick={() => setFilters((f) => ({ ...f, suburbs: toggle(f.suburbs, s.suburb) }))}>
                      {s.suburb} <span className="opacity-60">{s.homes}</span>
                    </Chip>
                  ))}
                </div>
              </FilterGroup>
            )}

            {options.dwelling_types.length > 0 && (
              <FilterGroup label="Dwelling type">
                <div className="flex flex-wrap gap-1.5">
                  {options.dwelling_types.map((d: DwellingType) => (
                    <Chip key={d} active={filters.dwelling_types.includes(d)}
                      onClick={() => setFilters((s) => ({ ...s, dwelling_types: toggle(s.dwelling_types, d) }))}>
                      {DWELLING_LABELS[d] ?? d}
                    </Chip>
                  ))}
                </div>
              </FilterGroup>
            )}

            <label className="flex items-center gap-2 text-xs text-foreground">
              <input
                type="checkbox"
                checked={filters.geocoded_only}
                onChange={(e) => setFilters((s) => ({ ...s, geocoded_only: e.target.checked }))}
                className="h-3.5 w-3.5 accent-primary"
              />
              Only homes placed on the map (needed for location-based ads)
            </label>
          </div>

          {/* Live result */}
          <div className="rounded-xl border border-border bg-card p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground">Homes in this segment</span>
              {previewing && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" aria-label="Updating" />}
            </div>
            {previewError ? (
              <p className="text-xs text-red-400">{previewError}</p>
            ) : preview ? (
              <>
                <div className="text-3xl font-bold text-foreground">{preview.home_count.toLocaleString("en-ZA")}</div>
                <p className="text-[11px] text-muted-foreground">
                  {excludedParts.length ? `Left out: ${excludedParts.join(", ")}` : "Nothing left out"}
                </p>
                {preview.areas.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">
                    No homes match these filters. Try widening the suburbs or dates.
                  </p>
                ) : (
                  <div className="max-h-64 overflow-y-auto">
                    <AreaTable areas={preview.areas} />
                  </div>
                )}
              </>
            ) : (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Counting homes…
              </div>
            )}

            <form onSubmit={handleSave} className="space-y-1.5 border-t border-border pt-3">
              <label htmlFor="segment-name" className="text-[11px] font-semibold text-muted-foreground">
                Save this segment
              </label>
              <div className="flex gap-2">
                <input
                  id="segment-name"
                  type="text"
                  maxLength={120}
                  placeholder="Brackenfell fibre launch"
                  value={segmentName}
                  onChange={(e) => {
                    setSegmentName(e.target.value)
                    setSaveError(null)
                  }}
                  className="min-w-0 flex-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <Button type="submit" size="sm" className="h-8 text-xs" disabled={saving}>
                  {saving ? "Saving…" : "Save segment"}
                </Button>
              </div>
              {saveError && <p className="text-[11px] text-red-400">{saveError}</p>}
            </form>
          </div>
        </div>
      </div>

      {/* Saved segments */}
      <div className="surface-card p-5 space-y-4">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
            <Layers className="h-4 w-4 text-emerald-400" />
            Saved segments
          </h4>
          <p className="text-xs text-muted-foreground">
            Counts are a snapshot from when the segment was saved or last refreshed
          </p>
        </div>
        {segments.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground">
            No saved segments yet. Build one above and save it to reuse it for campaigns and field sales.
          </p>
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {segments.map((s) => {
              const areas = expanded[s.id]
              return (
                <li key={s.id} className="p-3 space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => toggleAreas(s)}
                      aria-expanded={Boolean(areas)}
                      className="flex items-center gap-1.5 text-left"
                    >
                      {areas ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                      <span className="text-sm font-semibold text-foreground">{s.name}</span>
                    </button>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>
                        <span className="font-semibold text-foreground">{s.home_count.toLocaleString("en-ZA")}</span> homes
                        {" · "}
                        {s.area_count} {s.area_count === 1 ? "area" : "areas"}
                      </span>
                      <span>Updated {formatDate(s.refreshed_at)}</span>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-red-400"
                        onClick={() => handleDelete(s)}
                        aria-label={`Delete ${s.name}`}
                        title="Delete segment"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                  {rowError[s.id] && <p className="text-[11px] text-red-400">{rowError[s.id]}</p>}
                  {areas === "loading" && (
                    <div className="flex items-center gap-2 pl-5 text-xs text-muted-foreground">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading areas…
                    </div>
                  )}
                  {Array.isArray(areas) && (
                    <div className="pl-5">
                      {areas.length ? <AreaTable areas={areas} /> : (
                        <p className="text-xs text-muted-foreground">No homes in this segment.</p>
                      )}
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
