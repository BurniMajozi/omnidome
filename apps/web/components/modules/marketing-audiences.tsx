"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Building2, Download, Home, Loader2, MapPin, Plus, Trash2, Users, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { downloadAudienceCsv, pushCompanySearchAudience, pushGeoSegmentAudience } from "@/lib/audiences"
import { fnoApi, opportunityApi, type CompanySearch, type GeoSegment } from "@/lib/fno-api"
import {
  AUDIENCE_PLATFORMS,
  createAudienceSegment,
  deleteAudienceSegment,
  listAudienceSegments,
  type AudiencePlatform,
  type AudienceSegment,
  type AudienceType,
} from "@/lib/marketing-api"

const TYPE_META: Record<AudienceType, { label: string; unit: string; icon: typeof Home; className: string }> = {
  homes: { label: "Homes", unit: "homes", icon: Home, className: "border-cyan-500/40 text-cyan-400" },
  businesses: { label: "Businesses", unit: "businesses", icon: Building2, className: "border-teal-500/40 text-teal-400" },
  custom: { label: "Custom", unit: "regions", icon: Users, className: "border-purple-500/40 text-purple-400" },
}

const REGIONS = [
  "Gauteng & Western Cape (Metro Areas)",
  "Johannesburg / Sandton Central",
  "Cape Town Atlantic Seaboard & Southern Suburbs",
  "Durban / KZN Coastal Belt",
  "National South Africa",
]
const INTERESTS = [
  "High-Speed Fiber (100Mbps+)",
  "Gigabit Enterprise Internet (SLA)",
  "Budget / Prepaid Home Fiber (50Mbps)",
  "LTE / 5G Failover Backup",
]

function platformLabel(p: AudiencePlatform) {
  return AUDIENCE_PLATFORMS.find((x) => x.id === p)?.label.split(" (")[0] ?? p
}

function formatDate(iso?: string | null) {
  return iso ? new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" }) : "—"
}

function sizeOf(a: AudienceSegment) {
  return a.type === "custom" ? (a.rules.regions ?? []).length : a.member_count
}

export function MarketingAudiences() {
  const [audiences, setAudiences] = useState<AudienceSegment[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)

  const applyList = useCallback((r: Awaited<ReturnType<typeof listAudienceSegments>>) => {
    if (r.ok && r.data) {
      setAudiences(r.data)
      setError(null)
    } else {
      setError(r.error ?? "Couldn't load audiences")
      setAudiences((prev) => prev ?? [])
    }
  }, [])

  const load = useCallback(async () => applyList(await listAudienceSegments()), [applyList])

  useEffect(() => {
    let cancelled = false
    listAudienceSegments().then((r) => {
      if (!cancelled) applyList(r)
    })
    return () => {
      cancelled = true
    }
  }, [applyList])

  const selected = useMemo(() => audiences?.find((a) => a.id === selectedId) ?? null, [audiences, selectedId])

  const remove = async (a: AudienceSegment) => {
    if (!window.confirm(`Delete the audience "${a.name}"? The homes, businesses and segments behind it aren't affected.`)) return
    setDeleting(true)
    const r = await deleteAudienceSegment(a.id)
    setDeleting(false)
    if (!r.ok) {
      setError(r.error ?? "Couldn't delete the audience")
      return
    }
    setSelectedId(null)
    setAudiences((prev) => (prev ?? []).filter((x) => x.id !== a.id))
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-foreground">Target Audiences</h3>
          <p className="text-xs text-muted-foreground">
            Homes from FNO segments and businesses from company searches, ready for location-based and B2B ads
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={() => setModalOpen(true)}>
          <Plus className="mr-1.5 h-3.5 w-3.5" /> New Audience
        </Button>
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      {!audiences ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading audiences…</div>
      ) : audiences.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-6 text-center text-xs text-muted-foreground">
          <p className="font-medium text-foreground">No audiences yet</p>
          <p className="mt-1">
            In Sales → Lead sources, use <span className="text-foreground">Add to audience</span> on a saved homes segment or a company search,
            or create one here with New Audience.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {audiences.map((a) => {
            const meta = TYPE_META[a.type] ?? TYPE_META.custom
            const Icon = meta.icon
            const isSelected = a.id === selectedId
            return (
              <button key={a.id} type="button" onClick={() => setSelectedId(isSelected ? null : a.id)} aria-pressed={isSelected} className="text-left">
                <Card className={`h-full border bg-card transition-colors ${isSelected ? "border-primary/60" : "border-border hover:border-primary/30"}`}>
                  <CardContent className="p-4 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-semibold text-sm text-foreground line-clamp-2">{a.name}</p>
                      <Badge variant="outline" className="shrink-0 text-[10px]">{platformLabel(a.platform)}</Badge>
                    </div>
                    <p className="text-2xl font-bold text-foreground">
                      {sizeOf(a).toLocaleString("en-ZA")} <span className="text-xs font-normal text-muted-foreground">{meta.unit}</span>
                    </p>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <Badge variant="outline" className={`gap-1 text-[10px] ${meta.className}`}><Icon className="h-3 w-3" />{meta.label}</Badge>
                      <span>Updated {formatDate(a.updated_at ?? a.created_at)}</span>
                    </div>
                    {a.rules.source_name && <p className="truncate text-[11px] text-muted-foreground">From {a.rules.source_name}</p>}
                  </CardContent>
                </Card>
              </button>
            )
          })}
        </div>
      )}

      {selected && (
        <div className="rounded-xl border border-border bg-card p-4 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="text-sm font-semibold text-foreground">{selected.name}</p>
              {selected.description && <p className="text-xs text-muted-foreground">{selected.description}</p>}
            </div>
            <div className="flex items-center gap-1.5">
              <Button size="sm" variant="outline" className="h-8 gap-1 text-xs" onClick={() => downloadAudienceCsv(selected)}>
                <Download className="h-3.5 w-3.5" /> Export CSV
              </Button>
              <Button size="sm" variant="ghost" className="h-8 gap-1 text-xs text-muted-foreground hover:text-red-400" disabled={deleting} onClick={() => remove(selected)}>
                <Trash2 className="h-3.5 w-3.5" /> Delete
              </Button>
              <Button size="icon" variant="ghost" className="h-8 w-8" aria-label="Close details" onClick={() => setSelectedId(null)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <AudienceDetail audience={selected} />
        </div>
      )}

      {modalOpen && (
        <NewAudienceModal
          onClose={() => setModalOpen(false)}
          onCreated={async (a) => {
            setModalOpen(false)
            await load()
            setSelectedId(a.id)
          }}
        />
      )}
    </div>
  )
}

function AudienceDetail({ audience }: { audience: AudienceSegment }) {
  if (audience.type === "homes") {
    const areas = audience.rules.areas ?? []
    return (
      <div className="max-h-72 overflow-y-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="py-1.5 pr-2 font-medium">Area</th>
              <th className="py-1.5 pr-2 text-right font-medium">Homes</th>
              <th className="py-1.5 pr-2 text-right font-medium">Centre</th>
              <th className="py-1.5 text-right font-medium">Ad radius</th>
            </tr>
          </thead>
          <tbody>
            {areas.map((a) => (
              <tr key={`${a.suburb}|${a.city}|${a.postal_code}`} className="border-b border-border/40">
                <td className="py-1.5 pr-2">
                  <span className="inline-flex items-center gap-1 text-foreground"><MapPin className="h-3 w-3 text-muted-foreground" />{a.suburb ?? "Unknown suburb"}</span>
                  <span className="ml-1 text-[10px] text-muted-foreground">{[a.city, a.postal_code].filter(Boolean).join(" · ")}</span>
                </td>
                <td className="py-1.5 pr-2 text-right">{a.homes}</td>
                <td className="py-1.5 pr-2 text-right text-muted-foreground">
                  {a.centroid_lat === null ? "—" : `${a.centroid_lat.toFixed(4)}, ${a.centroid_lng?.toFixed(4)}`}
                </td>
                <td className="py-1.5 text-right text-muted-foreground">{a.centroid_lat === null ? "—" : `${a.suggested_radius_km} km`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-[10px] text-muted-foreground">Target areas only; individual home addresses never leave OmniDome.</p>
      </div>
    )
  }
  if (audience.type === "businesses") {
    const rows = audience.rules.businesses ?? []
    return (
      <div className="max-h-72 overflow-y-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="py-1.5 pr-2 font-medium">Business</th>
              <th className="py-1.5 pr-2 font-medium">Address</th>
              <th className="py-1.5 pr-2 font-medium">Phone</th>
              <th className="py-1.5 font-medium">Website</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((b, i) => (
              <tr key={`${b.name}-${i}`} className="border-b border-border/40">
                <td className="py-1.5 pr-2">
                  <span className="text-foreground">{b.name}</span>
                  {b.category && <span className="ml-1 text-[10px] text-muted-foreground">{b.category}</span>}
                </td>
                <td className="py-1.5 pr-2 text-muted-foreground">{b.address ?? "—"}</td>
                <td className="py-1.5 pr-2 text-muted-foreground">{b.phone ?? "—"}</td>
                <td className="py-1.5 text-muted-foreground truncate max-w-[180px]">{b.website ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-[10px] text-muted-foreground">Business data © OpenStreetMap contributors.</p>
      </div>
    )
  }
  return (
    <div className="text-xs text-muted-foreground space-y-1">
      <p>Regions: <span className="text-foreground">{(audience.rules.regions ?? []).join(", ") || "—"}</span></p>
      {audience.rules.interest && <p>Interest: <span className="text-foreground">{audience.rules.interest}</span></p>}
    </div>
  )
}

function NewAudienceModal({ onClose, onCreated }: { onClose: () => void; onCreated: (a: AudienceSegment) => void }) {
  const [type, setType] = useState<AudienceType>("homes")
  const [name, setName] = useState("")
  const [platform, setPlatform] = useState<AudiencePlatform>("google_ads")
  const [description, setDescription] = useState("")
  const [sourceId, setSourceId] = useState("")
  const [regions, setRegions] = useState<string[]>([REGIONS[0]])
  const [interest, setInterest] = useState(INTERESTS[0])
  const [segments, setSegments] = useState<GeoSegment[] | null>(null)
  const [searches, setSearches] = useState<CompanySearch[] | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fnoApi.listGeoSegments().then(setSegments).catch(() => setSegments([]))
    opportunityApi.listCompanySearches()
      .then((all) => setSearches(all.filter((s) => s.status === "done" && s.result_count > 0)))
      .catch(() => setSearches([]))
  }, [])

  const sources = type === "homes" ? segments : type === "businesses" ? searches : []
  const sourceLabel = (id: string) =>
    type === "homes"
      ? segments?.find((s) => s.id === id)?.name
      : searches?.find((s) => s.id === id) && `${searches.find((s) => s.id === id)!.category_label} near ${searches.find((s) => s.id === id)!.area_query}`

  const save = async () => {
    setError(null)
    if (type !== "custom" && !sourceId) {
      setError(type === "homes" ? "Choose a saved homes segment" : "Choose a company search")
      return
    }
    if (type === "custom" && !name.trim()) {
      setError("Enter an audience name")
      return
    }
    if (type === "custom" && regions.length === 0) {
      setError("Choose at least one region")
      return
    }
    setSaving(true)
    try {
      let created: AudienceSegment
      if (type === "homes") created = await pushGeoSegmentAudience(sourceId, platform, name, description)
      else if (type === "businesses") created = await pushCompanySearchAudience(sourceId, platform, name, description)
      else {
        const r = await createAudienceSegment({
          name: name.trim(), description: description.trim() || undefined, member_count: 0,
          rules: { type: "custom", platform, source: "manual", regions, interest },
        })
        if (!r.ok || !r.data) throw new Error(r.error ?? "Couldn't save the audience")
        created = r.data
      }
      onCreated(created)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save the audience")
    } finally {
      setSaving(false)
    }
  }

  const TYPES: { id: AudienceType; label: string; hint: string }[] = [
    { id: "homes", label: "Homes", hint: "From an FNO homes-passed segment" },
    { id: "businesses", label: "Businesses", hint: "From a company search" },
    { id: "custom", label: "Custom", hint: "Regions and interests" },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" role="dialog" aria-label="Create target audience">
      <div className="relative flex w-full max-w-lg flex-col rounded-xl border border-border bg-background shadow-2xl p-6 space-y-4">
        <div className="flex items-start justify-between border-b border-border pb-3">
          <div>
            <h3 className="text-base font-bold text-foreground">Create Target Audience</h3>
            <p className="text-xs text-muted-foreground">Build it from your lead sources, or define custom regions</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-3 text-xs">
          <div>
            <span className="font-medium text-foreground block mb-1">Audience type</span>
            <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Audience type">
              {TYPES.map((t) => (
                <button key={t.id} type="button" role="radio" aria-checked={type === t.id}
                  onClick={() => { setType(t.id); setSourceId(""); setError(null) }}
                  className={`rounded-lg border px-2.5 py-2 text-left ${type === t.id ? "border-primary/60 bg-primary/10" : "border-border hover:border-primary/30"}`}>
                  <span className="block font-semibold text-foreground">{t.label}</span>
                  <span className="block text-[10px] text-muted-foreground">{t.hint}</span>
                </button>
              ))}
            </div>
          </div>

          {type !== "custom" && (
            <label className="block">
              <span className="font-medium text-foreground block mb-1">{type === "homes" ? "Saved homes segment" : "Company search"}</span>
              {sources === null ? (
                <span className="inline-flex items-center gap-1 text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" /> Loading…</span>
              ) : sources.length === 0 ? (
                <p className="rounded-md border border-dashed border-border p-2 text-muted-foreground">
                  {type === "homes"
                    ? "No saved segments yet. Build one in Sales → Lead sources → Homes passed."
                    : "No finished company searches yet. Run one in Sales → Lead sources → Companies."}
                </p>
              ) : (
                <select value={sourceId} onChange={(e) => { setSourceId(e.target.value); setError(null) }}
                  className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none">
                  <option value="">Choose…</option>
                  {type === "homes"
                    ? (segments ?? []).map((s) => <option key={s.id} value={s.id}>{s.name} · {s.home_count} homes</option>)
                    : (searches ?? []).map((s) => (
                      <option key={s.id} value={s.id}>{s.category_label} near {s.area_query} · {s.result_count} businesses</option>
                    ))}
                </select>
              )}
            </label>
          )}

          <label className="block">
            <span className="font-medium text-foreground block mb-1">Audience name{type === "custom" ? "" : " (optional)"}</span>
            <input value={name} onChange={(e) => { setName(e.target.value); setError(null) }} maxLength={255}
              placeholder={(sourceId && sourceLabel(sourceId)) || "Western Cape fibre prospects"}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary" />
          </label>

          {type === "custom" && (
            <>
              <div>
                <span className="font-medium text-foreground block mb-1">Target regions</span>
                <div className="flex flex-wrap gap-1.5">
                  {REGIONS.map((r) => (
                    <button key={r} type="button" aria-pressed={regions.includes(r)}
                      onClick={() => setRegions((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]))}
                      className={`rounded-full border px-2.5 py-1 text-[11px] ${regions.includes(r) ? "border-primary/60 bg-primary/15 text-primary" : "border-border text-muted-foreground"}`}>
                      {r}
                    </button>
                  ))}
                </div>
              </div>
              <label className="block">
                <span className="font-medium text-foreground block mb-1">Telco / internet interest</span>
                <select value={interest} onChange={(e) => setInterest(e.target.value)}
                  className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none">
                  {INTERESTS.map((i) => <option key={i} value={i}>{i}</option>)}
                </select>
              </label>
            </>
          )}

          <label className="block">
            <span className="font-medium text-foreground block mb-1">Platform destination</span>
            <select value={platform} onChange={(e) => setPlatform(e.target.value as AudiencePlatform)}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none">
              {AUDIENCE_PLATFORMS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </label>

          <label className="block">
            <span className="font-medium text-foreground block mb-1">Description (optional)</span>
            <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary" />
          </label>
          {error && <p className="text-[11px] text-red-400">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 pt-2 border-t border-border">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={save} disabled={saving}>
            {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}
            Save Audience
          </Button>
        </div>
      </div>
    </div>
  )
}
