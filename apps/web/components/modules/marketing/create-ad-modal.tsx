"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { AlertTriangle, CheckCircle, Eye, Link2, Loader2, MessageSquare, Play, Plus, Target, X, Image as ImageIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { NotConnected } from "@/components/ui/not-connected"
import { useMarketingLoad } from "@/lib/use-marketing-load"
import { invalidateMarketingCache } from "@/lib/marketing-api"
import {
  adsCreate,
  adsPreview,
  adsReach,
  adsValidate,
  friendlyServerMessage,
  MEDIA_ACCEPT,
  searchTargeting,
  uploadMedia,
  type AdAccount,
  type AdsAccountsResponse,
  type AdsAudience,
  type AdsGoalsResponse,
  type AdsOptions,
  type TargetingResult,
  type UploadedMedia,
} from "@/lib/marketing-zernio-api"
import { ConnectAccountsDialog } from "./connect-flow"

const GOAL_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  engagement: MessageSquare,
  traffic: Link2,
  awareness: Eye,
  video_views: Play,
}

type GeoKind = "country" | "region" | "city"
interface Pick {
  id: string
  name: string
}

const isHttps = (u: string) => {
  try {
    return new URL(u).protocol === "https:"
  } catch {
    return false
  }
}

function newKey(): string {
  try {
    return crypto.randomUUID()
  } catch {
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`
  }
}

function toResults(data: unknown): TargetingResult[] {
  if (Array.isArray(data)) return data as TargetingResult[]
  const o = data as { results?: TargetingResult[]; items?: TargetingResult[] } | null
  return o?.results ?? o?.items ?? []
}

function Typeahead({
  label,
  placeholder,
  search,
  onPick,
  disabled,
  disabledReason,
}: {
  label: string
  placeholder: string
  search: (q: string) => Promise<{ items: Pick[]; error?: string }>
  onPick: (p: Pick) => void
  disabled?: boolean
  disabledReason?: string
}) {
  const [q, setQ] = useState("")
  const [items, setItems] = useState<Pick[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    if (disabled || q.trim().length < 2) {
      setItems([])
      setErr(null)
      return
    }
    let alive = true
    const t = setTimeout(async () => {
      setBusy(true)
      const r = await search(q.trim())
      if (!alive) return
      setBusy(false)
      setItems(r.items)
      setErr(r.error ?? null)
    }, 350)
    return () => {
      alive = false
      clearTimeout(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, disabled])
  return (
    <div className="relative">
      <label className="mb-1 block text-[11px] font-medium text-muted-foreground">{label}</label>
      <Input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={disabled ? disabledReason ?? "Unavailable" : placeholder}
        disabled={disabled}
        className="border-border bg-card text-xs"
      />
      {busy && <Loader2 className="absolute right-2 top-7 h-3.5 w-3.5 animate-spin text-muted-foreground" />}
      {err && <p className="mt-1 text-[11px] text-red-400">{err}</p>}
      {items.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-border bg-popover p-1 shadow-lg">
          {items.map((it) => (
            <li key={it.id}>
              <button
                type="button"
                className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-accent"
                onClick={() => {
                  onPick(it)
                  setQ("")
                  setItems([])
                }}
              >
                {it.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Chips({ items, onRemove }: { items: Pick[]; onRemove: (id: string) => void }) {
  if (items.length === 0) return null
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {items.map((i) => (
        <span key={i.id} className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-2 py-0.5 text-[11px] text-foreground">
          {i.name}
          <button type="button" aria-label={`Remove ${i.name}`} onClick={() => onRemove(i.id)}>
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
    </div>
  )
}

interface Issue {
  field?: string
  message?: string
}

function ErrorBlock({ raw, status }: { raw: string | null; status: number }) {
  let issues: Issue[] = []
  let created: unknown = null
  if (raw && raw.trim().startsWith("{")) {
    try {
      const o = JSON.parse(raw) as { errors?: Issue[]; details?: { createdObjects?: unknown } }
      if (Array.isArray(o.errors)) issues = o.errors
      created = o.details?.createdObjects ?? null
    } catch {
      /* fall through to the plain message */
    }
  }
  return (
    <div role="alert" className="space-y-1 rounded-md border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-400">
      {issues.length > 0 ? (
        <ul className="list-disc space-y-0.5 pl-4">
          {issues.map((e, i) => (
            <li key={i}>
              {e.field ? <span className="font-medium">{String(e.field).replace(/_/g, " ")}: </span> : null}
              {e.message}
            </li>
          ))}
        </ul>
      ) : (
        <p>{friendlyServerMessage(raw, status)}</p>
      )}
      {created ? <p className="text-amber-500">The provider created some objects before failing. Check the ad account in the platform before retrying: {JSON.stringify(created)}</p> : null}
    </div>
  )
}

export function CreateAdModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const accountsLoad = useMarketingLoad<AdsAccountsResponse>("/ads/accounts")
  const optionsLoad = useMarketingLoad<AdsOptions>("/ads/options")
  const accountsData = accountsLoad.value.state === "ready" ? accountsLoad.value.data : null
  const connections = accountsData?.connections ?? []
  const adAccounts = accountsData?.ad_accounts ?? []
  const options = optionsLoad.value.state === "ready" ? optionsLoad.value.data : null

  const [accountKey, setAccountKey] = useState("")
  const selected: AdAccount | undefined = adAccounts.find((a) => `${a.account_id}|${a.ad_account_id}` === accountKey)
  const connection = connections.find((c) => c.account_id === selected?.account_id)
  const platform = (connection?.platform || selected?.platform || "").toLowerCase()

  const goalsLoad = useMarketingLoad<AdsGoalsResponse>(platform ? `/ads/goals?platform=${encodeURIComponent(platform)}` : null)
  const goals = useMemo(() => {
    if (goalsLoad.value.state !== "ready") return []
    const g = goalsLoad.value.data?.goals ?? []
    return g.map((x) => (typeof x === "string" ? { id: x, label: x.replace(/_/g, " "), requires: [] as string[] } : { id: String(x.id ?? ""), label: String(x.label ?? x.id ?? ""), requires: (x.requires as string[]) ?? [] })).filter((x) => x.id)
  }, [goalsLoad.value])

  const [goal, setGoal] = useState("")
  const [name, setName] = useState("")
  const [body, setBody] = useState("")
  const [headline, setHeadline] = useState("")
  const [cta, setCta] = useState("")
  const [url, setUrl] = useState("")
  const [media, setMedia] = useState<UploadedMedia | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadErr, setUploadErr] = useState<string | null>(null)
  const [amount, setAmount] = useState("")
  const [budgetType, setBudgetType] = useState<"daily" | "lifetime">("daily")
  const [currency, setCurrency] = useState("")
  const [startAt, setStartAt] = useState("")
  const [endAt, setEndAt] = useState("")
  const [countries, setCountries] = useState<Pick[]>([])
  const [regions, setRegions] = useState<Pick[]>([])
  const [cities, setCities] = useState<Pick[]>([])
  const [interests, setInterests] = useState<Pick[]>([])
  const [geoKind, setGeoKind] = useState<GeoKind>("region")
  const [geoCountry, setGeoCountry] = useState("ZA")
  const [ageMin, setAgeMin] = useState("")
  const [ageMax, setAgeMax] = useState("")
  const [gender, setGender] = useState("all")
  const [audienceId, setAudienceId] = useState("")
  const [paused, setPaused] = useState(true)
  const [showConnect, setShowConnect] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  // Keep dependent selections valid when the ad account changes.
  useEffect(() => {
    if (!accountKey) {
      const first = adAccounts.find((a) => a.selectable !== false)
      if (first) setAccountKey(`${first.account_id}|${first.ad_account_id}`)
    }
  }, [adAccounts, accountKey])
  useEffect(() => {
    if (selected?.currency) setCurrency(selected.currency)
  }, [selected?.currency, accountKey])
  useEffect(() => {
    if (goals.length > 0 && !goals.some((g) => g.id === goal)) setGoal(goals[0].id)
  }, [goals, goal])

  const audLoad = useMarketingLoad<{ audiences?: AdsAudience[] } | AdsAudience[]>(
    selected ? `/ads/audiences?account_id=${encodeURIComponent(selected.account_id)}&ad_account_id=${encodeURIComponent(selected.ad_account_id)}` : null,
  )
  const platformAudiences: AdsAudience[] = audLoad.value.state === "ready" ? (Array.isArray(audLoad.value.data) ? audLoad.value.data : audLoad.value.data?.audiences ?? []) : []

  const limits = (options?.limits ?? {}) as Record<string, unknown>
  const limitFor = (key: "headline_max" | "body_max"): number | undefined => {
    const m = limits[key] as Record<string, number> | number | undefined
    return typeof m === "number" ? m : m?.[platform]
  }
  const headlineMax = limitFor("headline_max")
  const bodyMax = limitFor("body_max")
  const ctaList = (platform === "linkedin" ? (options?.linkedin_call_to_actions as string[] | undefined) : undefined) ?? options?.call_to_actions ?? options?.cta ?? []
  const ageRange = options?.age_range ?? { min: 13, max: 65 }

  const goalInfo = goals.find((g) => g.id === goal)
  const needsLink = goalInfo?.requires.includes("creative.link_url") ?? true

  const pickToTargeting = () => ({
    countries: countries.map((c) => c.id),
    regions: regions.map((r) => ({ key: r.id, name: r.name })),
    cities: cities.map((c) => ({ key: c.id, name: c.name })),
    age_min: ageMin ? Number(ageMin) : null,
    age_max: ageMax ? Number(ageMax) : null,
    gender,
    interests: interests.map((i) => ({ id: i.id, name: i.name })),
    audience_id: audienceId || null,
  })

  const payload = (): Record<string, unknown> => ({
    account_id: selected?.account_id,
    ad_account_id: selected?.ad_account_id,
    name: name.trim(),
    goal,
    budget: { amount: Number(amount), type: budgetType, currency: currency.trim().toUpperCase() || undefined },
    start_date: startAt ? new Date(startAt).toISOString() : null,
    end_date: endAt ? new Date(endAt).toISOString() : null,
    status: paused ? "PAUSED" : "ACTIVE",
    creative: {
      headline: headline.trim() || null,
      body: body.trim() || null,
      call_to_action: cta || null,
      link_url: url.trim() || null,
      image_url: media?.type === "image" ? media.public_url : null,
      video_url: media?.type === "video" ? media.public_url : null,
    },
    targeting: pickToTargeting(),
  })

  // Client-side checks that need no round trip. The server re-checks everything.
  const problems = useMemo(() => {
    const p: string[] = []
    if (!selected) p.push("Choose an ads account.")
    if (!name.trim()) p.push("Name the ad.")
    if (!goal) p.push("Choose a goal.")
    const amt = Number(amount)
    if (!amount || !Number.isFinite(amt) || amt <= 0) p.push("Enter a budget above zero.")
    else if (budgetType === "daily" && selected?.minimum_daily_budget && amt < Number(selected.minimum_daily_budget)) p.push(`The minimum daily budget on this account is ${selected.minimum_daily_budget} ${selected.currency ?? ""}.`)
    if (!/^[A-Za-z]{3}$/.test(currency.trim())) p.push("Currency must be a 3-letter code.")
    if (url.trim() && !isHttps(url.trim())) p.push("The destination URL must start with https://")
    if (needsLink && !url.trim()) p.push("This goal needs a destination URL.")
    if (headlineMax && headline.length > headlineMax) p.push(`Headline is over ${headlineMax} characters.`)
    if (bodyMax && body.length > bodyMax) p.push(`Primary text is over ${bodyMax} characters.`)
    if (ageMin && ageMax && Number(ageMin) > Number(ageMax)) p.push("Minimum age is above maximum age.")
    if (startAt && endAt && new Date(endAt) <= new Date(startAt)) p.push("The end must be after the start.")
    return p
  }, [selected, name, goal, amount, budgetType, currency, url, needsLink, headline, body, headlineMax, bodyMax, ageMin, ageMax, startAt, endAt])

  const [busy, setBusy] = useState<null | "validate" | "preview" | "reach" | "create">(null)
  const [result, setResult] = useState<
    | null
    | { kind: "validate"; valid: boolean; errors: Issue[]; warnings: Issue[]; providerValidated: boolean }
    | { kind: "preview"; local: Record<string, unknown>; note?: string }
    | { kind: "reach"; data: Record<string, unknown> }
    | { kind: "error"; raw: string | null; status: number }
    | { kind: "created"; adId: string; status: string; warnings: Issue[] }
  >(null)
  const keyRef = useRef<{ sig: string; key: string }>({ sig: "", key: newKey() })

  const run = async (kind: "validate" | "preview" | "reach" | "create") => {
    setBusy(kind)
    setResult(null)
    const p = payload()
    if (kind === "validate") {
      const r = await adsValidate(p)
      if (!r.ok || !r.data) setResult({ kind: "error", raw: r.error, status: r.status })
      else setResult({ kind: "validate", valid: r.data.valid, errors: r.data.errors ?? [], warnings: r.data.warnings ?? [], providerValidated: Boolean(r.data.provider_validated) })
    } else if (kind === "preview") {
      const r = await adsPreview({ account_id: p.account_id, ad_account_id: p.ad_account_id, creative: p.creative })
      if (!r.ok || !r.data) setResult({ kind: "error", raw: r.error, status: r.status })
      else setResult({ kind: "preview", local: (r.data.local as Record<string, unknown>) ?? {}, note: r.data.provider_note as string | undefined })
    } else if (kind === "reach") {
      const r = await adsReach({ account_id: String(p.account_id), ad_account_id: String(p.ad_account_id), targeting: p.targeting as Record<string, unknown> })
      if (!r.ok || !r.data) setResult({ kind: "error", raw: r.error, status: r.status })
      else setResult({ kind: "reach", data: r.data })
    } else {
      const sig = JSON.stringify(p)
      if (keyRef.current.sig !== sig) keyRef.current = { sig, key: newKey() }
      const r = await adsCreate(p, keyRef.current.key)
      if (!r.ok || !r.data) setResult({ kind: "error", raw: r.error, status: r.status })
      else {
        invalidateMarketingCache()
        setResult({ kind: "created", adId: String((r.data.ad as { ad_id?: string } | undefined)?.ad_id ?? ""), status: r.data.created_as ?? "paused", warnings: r.data.warnings ?? [] })
      }
    }
    setBusy(null)
  }

  const upload = async (files: FileList | null) => {
    const f = files?.[0]
    if (!f) return
    setUploading(true)
    setUploadErr(null)
    try {
      const m = await uploadMedia(f, "/ads/media/presign")
      if (m.type === "file") throw new Error("Ads accept an image or a video, not a document.")
      setMedia(m)
    } catch (e) {
      setUploadErr(e instanceof Error ? e.message : "Upload failed")
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  const geoSearch = async (q: string) => {
    if (!selected) return { items: [] }
    const r = await searchTargeting({ account_id: selected.account_id, q, dimension: "geo", geo_type: geoKind, country_code: geoKind === "country" ? undefined : geoCountry || undefined })
    if (!r.ok) return { items: [], error: friendlyServerMessage(r.error, r.status) }
    return {
      items: toResults(r.data)
        .map((x) => ({ id: String(geoKind === "country" ? x.country_code ?? x.key ?? x.id ?? "" : x.key ?? x.id ?? ""), name: String(x.name ?? "") }))
        .filter((x) => x.id && x.name),
    }
  }
  const interestSearch = async (q: string) => {
    if (!selected) return { items: [] }
    const r = await searchTargeting({ account_id: selected.account_id, q, dimension: "interest" })
    if (!r.ok) return { items: [], error: friendlyServerMessage(r.error, r.status) }
    return { items: toResults(r.data).map((x) => ({ id: String(x.id ?? x.key ?? ""), name: String(x.name ?? "") })).filter((x) => x.id && x.name) }
  }
  const addGeo = (p: Pick) => {
    const add = (list: Pick[]) => (list.some((x) => x.id === p.id) ? list : [...list, p])
    if (geoKind === "country") setCountries(add)
    else if (geoKind === "region") setRegions(add)
    else setCities(add)
  }

  const closeAndRefresh = () => {
    onCreated()
    onClose()
  }

  const budgetTypes = options?.budget_types?.length ? options.budget_types : ["daily", "lifetime"]
  const noConnection = accountsLoad.value.state === "ready" && connections.length === 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="relative flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-border bg-background shadow-2xl">
        <div className="flex items-start justify-between border-b border-border px-6 py-4">
          <div>
            <h3 className="text-lg font-bold text-foreground">Create Ad</h3>
            <p className="text-xs text-muted-foreground">design your ad creative and configure targeting</p>
          </div>
          <button aria-label="Close" onClick={onClose} className="rounded-lg p-1 text-muted-foreground hover:bg-card hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        {result?.kind === "created" ? (
          <div className="space-y-4 p-8 text-center">
            <CheckCircle className="mx-auto h-10 w-10 text-emerald-500" />
            <p className="text-base font-semibold text-foreground">Ad created {result.status === "paused" ? "as paused" : "and active"}</p>
            {result.adId && <p className="text-xs text-muted-foreground">Provider ad id: {result.adId}</p>}
            {result.status === "paused" && <p className="text-xs text-muted-foreground">It will not spend until you resume it.</p>}
            {result.warnings.length > 0 && (
              <ul className="mx-auto max-w-md list-disc pl-5 text-left text-xs text-amber-500">
                {result.warnings.map((w, i) => (
                  <li key={i}>{w.message}</li>
                ))}
              </ul>
            )}
            <Button onClick={closeAndRefresh}>Done</Button>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto p-6">
              <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
                {/* LEFT: creative */}
                <div className="space-y-5">
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-foreground">primary text</label>
                    <Textarea placeholder="Write the main text for your ad." value={body} onChange={(e) => setBody(e.target.value)} rows={4} className="resize-none border-border bg-card text-sm" />
                    <div className="mt-1 text-right text-[11px] text-muted-foreground">{body.length}{bodyMax ? `/${bodyMax}` : ""}</div>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-foreground">media (optional image or video)</label>
                    <input ref={fileRef} type="file" accept={MEDIA_ACCEPT.split(",").filter((t) => !t.includes("pdf")).join(",")} className="hidden" onChange={(e) => void upload(e.target.files)} />
                    {media ? (
                      <div className="relative overflow-hidden rounded-lg border border-border bg-card">
                        {media.type === "image" ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={media.public_url} alt={media.filename} className="max-h-48 w-full object-contain" />
                        ) : (
                          <video src={media.public_url} controls className="max-h-48 w-full" />
                        )}
                        <button type="button" aria-label="Remove media" onClick={() => setMedia(null)} className="absolute right-2 top-2 rounded-full bg-black/70 p-1 text-white">
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => fileRef.current?.click()}
                        disabled={uploading}
                        className="flex w-full flex-col items-center justify-center rounded-lg border-2 border-dashed border-border bg-card/40 p-8 text-center transition-colors hover:border-primary/50"
                      >
                        {uploading ? <Loader2 className="mb-2 h-8 w-8 animate-spin text-muted-foreground" /> : <ImageIcon className="mb-2 h-8 w-8 text-muted-foreground/60" />}
                        <span className="text-xs font-medium text-foreground">{uploading ? "Uploading…" : "Upload an image or video"}</span>
                      </button>
                    )}
                    {uploadErr && <p role="alert" className="mt-1 text-xs text-red-400">{uploadErr}</p>}
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-foreground">headline</label>
                    <Input placeholder="Your headline" value={headline} onChange={(e) => setHeadline(e.target.value)} className="border-border bg-card text-sm" />
                    <div className="mt-1 text-right text-[11px] text-muted-foreground">{headline.length}{headlineMax ? `/${headlineMax}` : ""}</div>
                  </div>

                  {ctaList.length > 0 && (
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold text-foreground">call to action</label>
                      <select value={cta} onChange={(e) => setCta(e.target.value)} className="w-full rounded-md border border-border bg-card px-3 py-2 text-xs text-foreground">
                        <option value="">Provider default</option>
                        {ctaList.map((c) => (
                          <option key={c} value={c}>{c.replace(/_/g, " ").toLowerCase()}</option>
                        ))}
                      </select>
                    </div>
                  )}

                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-foreground">destination URL{needsLink ? "" : " (optional for this goal)"}</label>
                    <Input placeholder="https://yourwebsite.com/landing-page" value={url} onChange={(e) => setUrl(e.target.value)} className="border-border bg-card text-sm" />
                    {url.trim() && !isHttps(url.trim()) && <p className="mt-1 text-[11px] text-amber-500">Must be a full https:// address.</p>}
                  </div>
                </div>

                {/* RIGHT: account, goal, budget, targeting */}
                <div className="space-y-5">
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-foreground">ad name</label>
                    <Input placeholder="Summer Sale Campaign" value={name} onChange={(e) => setName(e.target.value)} className="border-border bg-card text-sm" />
                  </div>

                  <div>
                    <label className="mb-1 block text-xs font-semibold text-foreground">platform and account</label>
                    {accountsLoad.value.state === "loading" ? (
                      <p className="text-xs text-muted-foreground">Loading ads accounts…</p>
                    ) : accountsLoad.value.state !== "ready" ? (
                      <NotConnected loadable={accountsLoad.value} service="The marketing service" onRetry={accountsLoad.reload} />
                    ) : noConnection ? (
                      <div className="space-y-2">
                        <p className="text-xs text-muted-foreground">{accountsData?.message || "No ads account is connected yet."}</p>
                        <Button size="sm" variant="outline" className="text-xs" onClick={() => setShowConnect(true)}>
                          <Plus className="mr-1 h-3.5 w-3.5" /> Connect an ads account
                        </Button>
                      </div>
                    ) : adAccounts.length === 0 ? (
                      <div className="space-y-2">
                        <p className="text-xs text-amber-500">An ads account is connected but no ad accounts were returned for it.</p>
                        {(accountsData?.errors ?? []).map((e, i) => (
                          <p key={i} className="text-[11px] text-red-400">{typeof e === "string" ? e : friendlyServerMessage(JSON.stringify(e), 0)}</p>
                        ))}
                        <Button size="sm" variant="outline" className="text-xs" onClick={() => setShowConnect(true)}>
                          Connect another ads account
                        </Button>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <select value={accountKey} onChange={(e) => setAccountKey(e.target.value)} className="w-full rounded-md border border-border bg-card px-3 py-2 text-xs text-foreground">
                          {adAccounts.map((a) => (
                            <option key={`${a.account_id}|${a.ad_account_id}`} value={`${a.account_id}|${a.ad_account_id}`} disabled={a.selectable === false}>
                              {a.name || a.ad_account_id} · {a.platform}{a.currency ? ` · ${a.currency}` : ""}{a.selectable === false ? ` (unavailable: ${a.unusable_reason ?? "cannot run ads"})` : ""}
                            </option>
                          ))}
                        </select>
                        {(accountsData?.errors?.length ?? 0) > 0 && <p className="text-[11px] text-amber-500">Some ad accounts could not be listed.</p>}
                        <button type="button" onClick={() => setShowConnect(true)} className="text-[11px] text-primary hover:underline">
                          Connect another ads account
                        </button>
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-foreground">goal</label>
                    {!platform ? (
                      <p className="text-xs text-muted-foreground">Choose an ads account to see its valid goals.</p>
                    ) : goalsLoad.value.state === "loading" ? (
                      <p className="text-xs text-muted-foreground">Loading goals…</p>
                    ) : goalsLoad.value.state !== "ready" ? (
                      <NotConnected loadable={goalsLoad.value} service="The marketing service" onRetry={goalsLoad.reload} />
                    ) : (
                      <>
                        <div className="grid grid-cols-2 gap-2">
                          {goals.map((g) => {
                            const Icon = GOAL_ICONS[g.id] ?? Target
                            return (
                              <button
                                key={g.id}
                                type="button"
                                aria-pressed={goal === g.id}
                                onClick={() => setGoal(g.id)}
                                className={`flex items-center gap-2 rounded-md border p-2.5 text-left text-xs font-medium capitalize transition-colors ${goal === g.id ? "border-primary bg-primary/10 text-primary" : "border-border bg-card text-foreground hover:bg-card/80"}`}
                              >
                                <Icon className="h-3.5 w-3.5 shrink-0" />
                                <span>{g.label}</span>
                              </button>
                            )
                          })}
                        </div>
                        {goalInfo && goalInfo.requires.length > 0 && <p className="mt-1.5 text-[11px] text-muted-foreground">Needs: {goalInfo.requires.map((r) => r.replace("creative.", "").replace("promoted_object.", "").replace(/_/g, " ")).join(", ")}</p>}
                      </>
                    )}
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-foreground">budget</label>
                    <div className="flex flex-wrap items-center gap-2">
                      <Input type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Amount" className="w-28 border-border bg-card text-sm" aria-label="Budget amount" />
                      <Input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase().slice(0, 3))} placeholder="ZAR" className="w-20 border-border bg-card text-sm uppercase" aria-label="Currency" />
                      <div className="flex rounded-md border border-border p-0.5 text-xs">
                        {budgetTypes.map((t) => {
                          const k = t === "daily" ? "daily" : "lifetime"
                          return (
                            <button key={t} type="button" onClick={() => setBudgetType(k)} className={`rounded px-3 py-1.5 transition-colors ${budgetType === k ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"}`}>
                              {k === "daily" ? "Per day" : "Total"}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                    {selected?.minimum_daily_budget ? <p className="mt-1 text-[11px] text-muted-foreground">Minimum daily budget on this account: {selected.minimum_daily_budget} {selected.currency}</p> : null}
                    <p className="mt-1 text-[11px] text-muted-foreground">Whole currency units, not cents.</p>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="mb-1 block text-[11px] font-medium text-muted-foreground">start (optional)</label>
                      <Input type="datetime-local" value={startAt} onChange={(e) => setStartAt(e.target.value)} className="border-border bg-card text-xs" />
                    </div>
                    <div>
                      <label className="mb-1 block text-[11px] font-medium text-muted-foreground">end (optional)</label>
                      <Input type="datetime-local" value={endAt} onChange={(e) => setEndAt(e.target.value)} className="border-border bg-card text-xs" />
                    </div>
                  </div>

                  <div className="space-y-3">
                    <label className="block text-xs font-semibold text-foreground">targeting</label>
                    <div className="grid grid-cols-[110px_70px_1fr] items-end gap-2">
                      <div>
                        <label className="mb-1 block text-[11px] font-medium text-muted-foreground">location type</label>
                        <select value={geoKind} onChange={(e) => setGeoKind(e.target.value as GeoKind)} className="w-full rounded-md border border-border bg-card px-2 py-2 text-xs text-foreground">
                          <option value="country">Country</option>
                          <option value="region">Region</option>
                          <option value="city">City</option>
                        </select>
                      </div>
                      <div>
                        <label className="mb-1 block text-[11px] font-medium text-muted-foreground">in</label>
                        <Input value={geoCountry} disabled={geoKind === "country"} onChange={(e) => setGeoCountry(e.target.value.toUpperCase().slice(0, 2))} className="border-border bg-card text-xs uppercase" aria-label="Country code to search within" />
                      </div>
                      <Typeahead label="search locations" placeholder="e.g. Gauteng" search={geoSearch} onPick={addGeo} disabled={!selected} disabledReason="Choose an ads account first" />
                    </div>
                    <Chips items={countries} onRemove={(id) => setCountries((l) => l.filter((x) => x.id !== id))} />
                    <Chips items={regions} onRemove={(id) => setRegions((l) => l.filter((x) => x.id !== id))} />
                    <Chips items={cities} onRemove={(id) => setCities((l) => l.filter((x) => x.id !== id))} />

                    <div className="grid grid-cols-3 gap-2">
                      <div>
                        <label className="mb-1 block text-[11px] font-medium text-muted-foreground">age min</label>
                        <Input type="number" min={ageRange.min} max={ageRange.max} value={ageMin} onChange={(e) => setAgeMin(e.target.value)} className="border-border bg-card text-xs" />
                      </div>
                      <div>
                        <label className="mb-1 block text-[11px] font-medium text-muted-foreground">age max</label>
                        <Input type="number" min={ageRange.min} max={ageRange.max} value={ageMax} onChange={(e) => setAgeMax(e.target.value)} className="border-border bg-card text-xs" />
                      </div>
                      <div>
                        <label className="mb-1 block text-[11px] font-medium text-muted-foreground">gender</label>
                        <select value={gender} onChange={(e) => setGender(e.target.value)} className="w-full rounded-md border border-border bg-card px-2 py-2 text-xs text-foreground">
                          <option value="all">All</option>
                          <option value="male">Male</option>
                          <option value="female">Female</option>
                        </select>
                      </div>
                    </div>

                    <div>
                      <Typeahead label="interests" placeholder="e.g. Internet" search={interestSearch} onPick={(p) => setInterests((l) => (l.some((x) => x.id === p.id) ? l : [...l, p]))} disabled={!selected} disabledReason="Choose an ads account first" />
                      <Chips items={interests} onRemove={(id) => setInterests((l) => l.filter((x) => x.id !== id))} />
                    </div>

                    <div>
                      <label className="mb-1 block text-[11px] font-medium text-muted-foreground">saved audience (optional)</label>
                      {audLoad.value.state === "ready" && platformAudiences.length === 0 ? (
                        <p className="text-xs text-muted-foreground">No custom or lookalike audiences exist on this ad account.</p>
                      ) : audLoad.value.state === "ready" ? (
                        <select value={audienceId} onChange={(e) => setAudienceId(e.target.value)} className="w-full rounded-md border border-border bg-card px-3 py-2 text-xs text-foreground">
                          <option value="">No audience</option>
                          {platformAudiences.map((a) => (
                            <option key={a.id} value={a.id}>{a.name}{a.type ? ` (${String(a.type).replace(/_/g, " ")})` : ""}{typeof a.size === "number" ? ` · ~${a.size.toLocaleString()}` : ""}</option>
                          ))}
                        </select>
                      ) : audLoad.value.state === "loading" ? (
                        <p className="text-xs text-muted-foreground">Loading audiences…</p>
                      ) : selected ? (
                        <p className="text-xs text-amber-500">Audiences could not be loaded for this account.</p>
                      ) : (
                        <p className="text-xs text-muted-foreground">Choose an ads account first.</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Result area */}
            {result && (
              <div className="max-h-48 overflow-y-auto border-t border-border px-6 py-3 text-xs">
                {result.kind === "error" && <ErrorBlock raw={result.raw} status={result.status} />}
                {result.kind === "validate" && (
                  <div className="space-y-1">
                    <p className={`flex items-center gap-1.5 font-medium ${result.valid ? "text-emerald-500" : "text-red-400"}`}>
                      {result.valid ? <CheckCircle className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
                      {result.valid ? `Valid${result.providerValidated ? " (checked with the provider)" : " (local checks only; the provider validates on create)"}` : "Not valid yet"}
                    </p>
                    {result.errors.map((e, i) => (
                      <p key={`e${i}`} className="text-red-400">{e.field ? `${String(e.field).replace(/_/g, " ")}: ` : ""}{e.message}</p>
                    ))}
                    {result.warnings.map((e, i) => (
                      <p key={`w${i}`} className="text-amber-500">{e.field ? `${String(e.field).replace(/_/g, " ")}: ` : ""}{e.message}</p>
                    ))}
                  </div>
                )}
                {result.kind === "preview" && (
                  <div className="mx-auto max-w-xs overflow-hidden rounded-lg border border-border bg-card">
                    {result.local.image_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={String(result.local.image_url)} alt="" className="max-h-40 w-full object-cover" />
                    ) : result.local.video_url ? (
                      <video src={String(result.local.video_url)} className="max-h-40 w-full" muted />
                    ) : null}
                    <div className="space-y-1 p-3">
                      <p className="text-[11px] text-foreground">{String(result.local.body ?? "")}</p>
                      <p className="text-[10px] uppercase text-muted-foreground">{String(result.local.display_url ?? "")}</p>
                      <p className="text-xs font-semibold text-foreground">{String(result.local.headline ?? "")}</p>
                      {result.local.call_to_action ? <span className="inline-block rounded border border-border px-2 py-0.5 text-[10px] text-foreground">{String(result.local.call_to_action).replace(/_/g, " ").toLowerCase()}</span> : null}
                    </div>
                    <p className="border-t border-border px-3 py-1.5 text-[10px] text-muted-foreground">{result.note ?? "In-app approximation. The platform's own preview appears only for Meta creatives that already exist."}</p>
                  </div>
                )}
                {result.kind === "reach" && <ReachView data={result.data} />}
              </div>
            )}
            {problems.length > 0 && busy === null && (
              <ul className="border-t border-border bg-amber-500/5 px-6 py-2 text-[11px] text-amber-500">
                {problems.slice(0, 3).map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            )}

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-card/30 px-6 py-4">
              <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-muted-foreground">
                <input type="checkbox" checked={paused} onChange={(e) => setPaused(e.target.checked)} className="rounded border-border" />
                <span>create as paused{paused ? "" : " (the ad will start spending immediately)"}</span>
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => run("reach")} disabled={!selected || busy !== null} title="Estimated audience size for the targeting above">
                  {busy === "reach" && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />} Reach estimate
                </Button>
                <Button variant="outline" size="sm" onClick={() => run("preview")} disabled={!selected || busy !== null}>
                  {busy === "preview" && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />} Preview
                </Button>
                <Button variant="outline" size="sm" onClick={() => run("validate")} disabled={problems.length > 0 || busy !== null}>
                  {busy === "validate" && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />} Validate
                </Button>
                <Button variant="outline" size="sm" onClick={onClose}>cancel</Button>
                <Button size="sm" disabled={problems.length > 0 || busy !== null || uploading} onClick={() => run("create")}>
                  {busy === "create" ? "creating…" : "create Ad"}
                </Button>
              </div>
            </div>
          </>
        )}
      </div>

      {showConnect && (
        <ConnectAccountsDialog
          category="ads"
          returnTo="/dashboard?section=marketing&marketing_tab=ads"
          onClose={() => setShowConnect(false)}
          onConnected={() => {
            setShowConnect(false)
            invalidateMarketingCache()
            accountsLoad.reload()
          }}
        />
      )}
    </div>
  )
}

function ReachView({ data }: { data: Record<string, unknown> }) {
  if (data.available === false) {
    return <p className="text-muted-foreground">{String(data.message ?? "This platform does not provide a reach estimate.")}</p>
  }
  const rows = Object.entries(data).filter(([, v]) => typeof v === "number" || typeof v === "string")
  if (rows.length === 0) return <p className="text-muted-foreground">The provider returned no estimate for this targeting.</p>
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{k.replace(/_/g, " ")}</dt>
          <dd className="text-foreground">{typeof v === "number" ? v.toLocaleString() : String(v)}</dd>
        </div>
      ))}
    </dl>
  )
}
