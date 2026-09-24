"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  Building2, ExternalLink, Loader2, MapPin, Phone, RotateCcw, Search, Sparkles, UserPlus, X,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  opportunityApi,
  type CompanyCategory,
  type CompanySearch,
  type OppCompany,
} from "@/lib/fno-api"
import { announceSalesChange } from "./sales-leads-tab"
import { salesApi } from "@/lib/sales-api"
import { pushCompanySearchAudience } from "@/lib/audiences"
import { listAudienceSegments, type AudienceSegment } from "@/lib/marketing-api"
import { AddToAudience } from "./add-to-audience"

const RADII = [1, 2, 5, 10]

// One column template shared by the search form and the results table, so the
// form fields sit over the columns they describe.
const GRID = "grid grid-cols-[minmax(0,30fr)_minmax(0,24fr)_minmax(0,12fr)_minmax(0,14fr)_minmax(0,7fr)_minmax(0,13fr)] gap-3"

function websiteHost(url: string) {
  try {
    return new URL(url.startsWith("http") ? url : `https://${url}`).hostname.replace(/^www\./, "")
  } catch {
    return url
  }
}

function websiteHref(url: string) {
  return url.startsWith("http") ? url : `https://${url}`
}

function addressOf(c: OppCompany) {
  return [c.address_line, c.suburb, c.city].filter(Boolean).join(", ")
}

export function OpportunityCompanies({
  onSearchLoaded,
}: {
  onSearchLoaded?: (search: (CompanySearch & { companies: OppCompany[] }) | null) => void
}) {
  const [categories, setCategories] = useState<CompanyCategory[]>([])
  const [recent, setRecent] = useState<CompanySearch[]>([])
  const [area, setArea] = useState("")
  const [radius, setRadius] = useState(2)
  const [category, setCategory] = useState("all")
  const [formError, setFormError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [active, setActive] = useState<(CompanySearch & { companies: OppCompany[] }) | null>(null)
  const [showDismissed, setShowDismissed] = useState(false)
  const [rowBusy, setRowBusy] = useState<Record<string, string>>({})
  const [rowNote, setRowNote] = useState<Record<string, { text: string; error?: boolean }>>({})
  const onLoadedRef = useRef(onSearchLoaded)
  onLoadedRef.current = onSearchLoaded
  // Marketing audiences already made from these searches, by search id.
  const [audiences, setAudiences] = useState<Record<string, AudienceSegment>>({})
  useEffect(() => {
    listAudienceSegments("businesses").then((r) => {
      if (!r.ok || !r.data) return
      setAudiences(Object.fromEntries(r.data.filter((a) => a.rules.source_id).map((a) => [a.rules.source_id!, a])))
    })
  }, [])

  // One chip per distinct search (area, type, radius), newest first.
  const loadRecent = useCallback(() => {
    opportunityApi.listCompanySearches()
      .then((all) => {
        const seen = new Set<string>()
        setRecent(all.filter((s) => {
          const key = `${s.area_query.toLowerCase()}|${s.category}|${s.radius_km}`
          if (seen.has(key)) return false
          seen.add(key)
          return true
        }))
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    opportunityApi.listCategories().then(setCategories).catch(() => {})
    loadRecent()
  }, [loadRecent])

  const openSearch = useCallback(async (id: string) => {
    try {
      const detail = await opportunityApi.getCompanySearch(id)
      setActive(detail)
      onLoadedRef.current?.(detail)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Couldn't open that search")
    }
  }, [])

  // Poll the active search while OpenStreetMap is working on it.
  const pending = active && (active.status === "queued" || active.status === "running")
  useEffect(() => {
    if (!pending || !active) return
    const timer = setInterval(async () => {
      try {
        const detail = await opportunityApi.getCompanySearch(active.id)
        setActive(detail)
        if (detail.status === "done" || detail.status === "failed") {
          onLoadedRef.current?.(detail)
          loadRecent()
        }
      } catch {
        // keep polling
      }
    }, 3000)
    return () => clearInterval(timer)
  }, [pending, active, loadRecent])

  const startSearch = async (e?: React.FormEvent, retry?: CompanySearch) => {
    e?.preventDefault()
    const q = retry ? retry.area_query : area.trim()
    if (q.length < 2) {
      setFormError("Enter an area, for example \"Rosebank, Johannesburg\"")
      return
    }
    setStarting(true)
    setFormError(null)
    try {
      const created = await opportunityApi.createCompanySearch(q, retry?.category ?? category, retry?.radius_km ?? radius)
      setActive({ ...created, companies: [] })
      onLoadedRef.current?.(null)
      loadRecent()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Couldn't start the search")
    } finally {
      setStarting(false)
    }
  }

  const updateCompany = (updated: OppCompany) =>
    setActive((prev) => prev && { ...prev, companies: prev.companies.map((c) => (c.id === updated.id ? { ...c, ...updated } : c)) })

  const withRow = async (c: OppCompany, label: string, fn: () => Promise<void>) => {
    setRowBusy((p) => ({ ...p, [c.id]: label }))
    setRowNote((p) => { const n = { ...p }; delete n[c.id]; return n })
    try {
      await fn()
    } catch (err) {
      setRowNote((p) => ({ ...p, [c.id]: { text: err instanceof Error ? err.message : `Couldn't ${label}`, error: true } }))
    } finally {
      setRowBusy((p) => { const n = { ...p }; delete n[c.id]; return n })
    }
  }

  const findContacts = (c: OppCompany) =>
    withRow(c, "find contacts", async () => {
      const updated = await opportunityApi.enrichCompany(c.id)
      updateCompany(updated)
      const found = updated.updated_fields ?? []
      setRowNote((p) => ({ ...p, [c.id]: { text: found.length ? `Found ${found.join(", ")}` : "No public contact details found" } }))
    })

  const addAsLead = (c: OppCompany) =>
    withRow(c, "add as lead", async () => {
      const lead = await salesApi.createLead({
        first_name: c.name,
        last_name: "",
        phone: c.phone ?? undefined,
        email: c.email ?? undefined,
        address: addressOf(c) || undefined,
        source: "COMPANY_SEARCH",
        interest_level: 3,
        notes: [
          `Business lead from company search${active ? ` (${active.category_label}, ${active.radius_km} km around ${active.area_query})` : ""}.`,
          c.category_label ? `Category: ${c.category_label}.` : null,
          c.website ? `Website: ${c.website}` : null,
          "Source: OpenStreetMap.",
        ].filter(Boolean).join(" "),
        // Straight onto the Pipeline Board (SPEC-lead-lifecycle.md).
        pipeline: { stage_name: "Prospecting", deal_name: `${c.name} - Company search` },
      })
      updateCompany(await opportunityApi.patchCompany(c.id, { status: "lead_created", sales_lead_id: lead.id }))
      setRowNote((p) => ({ ...p, [c.id]: { text: `${lead.reference ?? "Lead"} is on the Pipeline Board (${lead.deal_stage ?? "Prospecting"})` } }))
      announceSalesChange()
    })

  const setDismissed = (c: OppCompany, dismissed: boolean) =>
    withRow(c, dismissed ? "dismiss" : "restore", async () => {
      updateCompany(await opportunityApi.patchCompany(c.id, { status: dismissed ? "dismissed" : "new" }))
    })

  const visible = useMemo(
    () => (active?.companies ?? []).filter((c) => showDismissed || c.status !== "dismissed"),
    [active, showDismissed],
  )
  const dismissedCount = (active?.companies ?? []).filter((c) => c.status === "dismissed").length

  return (
    <div className="surface-card p-5 space-y-4">
      <div>
        <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
          <Building2 className="h-4 w-4 text-teal-400" />
          Find companies in an area
        </h4>
        <p className="text-xs text-muted-foreground">
          Named businesses from OpenStreetMap around a suburb or town. Look up missing contact details, then add the good ones as leads.
        </p>
      </div>

      {/* Search form: same column grid as the results table below */}
      <form onSubmit={startSearch} className={`${GRID} items-end rounded-xl border border-border bg-muted/10 p-3`}>
        <label className="col-span-2 space-y-1">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Area</span>
          <div className="relative">
            <MapPin className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={area}
              onChange={(e) => { setArea(e.target.value); setFormError(null) }}
              placeholder="Rosebank, Johannesburg"
              maxLength={200}
              className="w-full rounded-lg border border-border bg-background py-2 pl-8 pr-2.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        </label>
        <label className="space-y-1">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Within</span>
          <select value={radius} onChange={(e) => setRadius(Number(e.target.value))}
            className="w-full rounded-lg border border-border bg-background px-2 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary">
            {RADII.map((r) => <option key={r} value={r}>{r} km</option>)}
          </select>
        </label>
        <label className="col-span-2 space-y-1">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Type of business</span>
          <select value={category} onChange={(e) => setCategory(e.target.value)}
            className="w-full rounded-lg border border-border bg-background px-2 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary">
            {(categories.length ? categories : [{ id: "all", label: "All businesses" }]).map((c) => (
              <option key={c.id} value={c.id}>{c.label}</option>
            ))}
          </select>
        </label>
        <Button type="submit" size="sm" className="h-9 gap-1.5 text-xs" disabled={starting || Boolean(pending)}>
          {starting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
          Search
        </Button>
      </form>
      {formError && <p className="text-[11px] text-red-400">{formError}</p>}

      {recent.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="text-muted-foreground">Recent:</span>
          {recent.slice(0, 6).map((s) => (
            <button key={s.id} type="button" onClick={() => openSearch(s.id)}
              className={`rounded-full border px-2.5 py-1 transition-colors ${
                active?.id === s.id ? "border-primary/60 bg-primary/15 text-primary" : "border-border text-muted-foreground hover:text-foreground"
              }`}>
              {s.area_query} · {s.category_label} · {s.radius_km} km
              {s.status === "done" ? ` · ${s.result_count}` : s.status === "failed" ? " · failed" : " · …"}
            </button>
          ))}
        </div>
      )}

      {!active ? (
        <p className="rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground">
          Search an area to see the businesses in it.
        </p>
      ) : pending ? (
        <div className="flex items-center gap-2 rounded-lg border border-border p-4 text-xs text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
          Searching OpenStreetMap around {active.area_label?.split(",").slice(0, 2).join(",") ?? active.area_query}… this can take up to a minute.
        </div>
      ) : active.status === "failed" ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-xs">
          <span className="text-red-400">{active.error_message ?? "The search failed."}</span>
          <Button size="sm" variant="outline" className="h-7 gap-1 text-[11px]" onClick={() => startSearch(undefined, active)}>
            <RotateCcw className="h-3 w-3" /> Try again
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
            <span>
              <span className="font-semibold text-foreground">{active.result_count}</span> businesses within {active.radius_km} km of{" "}
              {active.area_label?.split(",").slice(0, 2).join(",")}
            </span>
            <div className="flex flex-wrap items-center gap-3">
            <AddToAudience
              key={active.id}
              existing={audiences[active.id]}
              defaultName={`${active.category_label} near ${active.area_query}`}
              disabled={visible.length === 0}
              onPush={async (platform, name) => {
                const audience = await pushCompanySearchAudience(active.id, platform, name)
                setAudiences((prev) => ({ ...prev, [active.id]: audience }))
                return audience
              }}
            />
            {dismissedCount > 0 && (
              <label className="flex items-center gap-1.5">
                <input type="checkbox" checked={showDismissed} onChange={(e) => setShowDismissed(e.target.checked)} className="h-3 w-3 accent-primary" />
                Show {dismissedCount} dismissed
              </label>
            )}
            </div>
          </div>
          {visible.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground">
              No named businesses of this type here. Try a bigger radius or another type of business.
            </p>
          ) : (
            <div className="rounded-lg border border-border">
              <div className={`${GRID} border-b border-border px-3 py-2 text-[11px] font-medium text-muted-foreground`}>
                <span>Company</span><span>Address</span><span>Phone</span><span>Website</span>
                <span className="text-right">Distance</span><span className="text-right">Actions</span>
              </div>
              <ul className="max-h-[520px] overflow-y-auto divide-y divide-border/60">
                {visible.map((c) => {
                  const busy = rowBusy[c.id]
                  const note = rowNote[c.id]
                  const missingContact = !c.phone || !c.website || !c.email
                  return (
                    <li key={c.id} className={`px-3 py-2 text-xs ${c.status === "dismissed" ? "opacity-50" : ""}`}>
                      <div className={`${GRID} items-center`}>
                        <div className="min-w-0">
                          <div className="truncate font-medium text-foreground" title={c.name}>{c.name}</div>
                          {c.category_label && <div className="truncate text-[10px] text-muted-foreground">{c.category_label}</div>}
                        </div>
                        <div className="truncate text-muted-foreground" title={addressOf(c)}>{addressOf(c) || "—"}</div>
                        <div className="truncate">
                          {c.phone ? (
                            <a href={`tel:${c.phone}`} className="inline-flex items-center gap-1 text-foreground hover:text-primary">
                              <Phone className="h-3 w-3 shrink-0" />{c.phone}
                            </a>
                          ) : <span className="text-muted-foreground">—</span>}
                        </div>
                        <div className="truncate">
                          {c.website ? (
                            <a href={websiteHref(c.website)} target="_blank" rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-primary hover:underline">
                              {websiteHost(c.website)} <ExternalLink className="h-3 w-3 shrink-0" />
                            </a>
                          ) : <span className="text-muted-foreground">—</span>}
                        </div>
                        <div className="text-right text-muted-foreground">{c.distance_km.toFixed(1)} km</div>
                        <div className="flex items-center justify-end gap-1">
                          {busy ? (
                            <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                              <Loader2 className="h-3 w-3 animate-spin" /> {busy === "find contacts" ? "Searching the web…" : "Saving…"}
                            </span>
                          ) : c.status === "lead_created" ? (
                            <Badge variant="outline" className="border-emerald-500/40 text-[10px] text-emerald-400">Lead added</Badge>
                          ) : c.status === "dismissed" ? (
                            <Button variant="ghost" size="sm" className="h-7 px-2 text-[11px]" onClick={() => setDismissed(c, false)}>Restore</Button>
                          ) : (
                            <>
                              {missingContact && !c.enriched_at && (
                                <Button variant="ghost" size="icon" className="h-7 w-7" title="Find contact details on the web"
                                  aria-label={`Find contact details for ${c.name}`} onClick={() => findContacts(c)}>
                                  <Sparkles className="h-3.5 w-3.5 text-purple-400" />
                                </Button>
                              )}
                              <Button variant="outline" size="sm" className="h-7 gap-1 px-2 text-[11px]" onClick={() => addAsLead(c)}>
                                <UserPlus className="h-3 w-3" /> Add as lead
                              </Button>
                              <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" title="Dismiss"
                                aria-label={`Dismiss ${c.name}`} onClick={() => setDismissed(c, true)}>
                                <X className="h-3.5 w-3.5" />
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                      {note && <p className={`mt-1 text-right text-[10px] ${note.error ? "text-red-400" : "text-muted-foreground"}`}>{note.text}</p>}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}
          <p className="text-[10px] text-muted-foreground">
            Business data ©{" "}
            <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer" className="hover:underline">
              OpenStreetMap contributors
            </a>
          </p>
        </div>
      )}
    </div>
  )
}
