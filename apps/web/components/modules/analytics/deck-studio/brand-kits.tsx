"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { ArrowLeft, Check, Globe, Loader2, Plus, Star, Trash2, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  BiApiError,
  createBrandKit,
  deleteBrandKit,
  getBrandKit,
  setDefaultBrandKit,
  suggestBrandFromUrl,
  unwrapKit,
  updateBrandKit,
  type BrandKit,
  type BrandKitInput,
  type BrandPalette,
  type BrandSuggestion,
  type Slide,
} from "@/lib/bi-studio-api"
import { ErrorNote, Pill, errText } from "../shared"
import { Field, Modal, fieldCls, useStudio } from "./ui"
import { DEFAULT_PALETTE, isHex, mergeTheme, safeDataImage } from "./theme"
import { SlideRenderer } from "./slide-renderer"
import { invalidateKit } from "./use-kit"

const FALLBACK_LOGO_BYTES = 512 * 1024
const FALLBACK_TYPES = ["image/png", "image/jpeg", "image/svg+xml"]

interface Draft {
  name: string
  company_name: string
  tagline: string
  palette: BrandPalette
  fonts: { heading: string; body: string }
  voice: { formality: string; jargon_level: string; banned: string; notes: string }
  footer_text: string
  slide_numbers: boolean
  layout_prefs: { default_layout: string; title_align: string; density: string; show_logo: boolean; logo_position: string }
  logo: string | null
  logoChanged: boolean
}

function draftFrom(k: BrandKit | null): Draft {
  return {
    name: k?.name ?? "",
    company_name: k?.company_name ?? "",
    tagline: k?.tagline ?? "",
    palette: { ...DEFAULT_PALETTE, ...(k?.palette ?? {}), chart: [...(k?.palette?.chart?.length ? k.palette.chart : DEFAULT_PALETTE.chart)] },
    fonts: { heading: k?.fonts?.heading ?? "Calibri", body: k?.fonts?.body ?? "Calibri" },
    voice: {
      formality: k?.voice?.formality ?? "neutral",
      jargon_level: k?.voice?.jargon_level ?? "medium",
      banned: (k?.voice?.banned_words ?? []).join(", "),
      notes: k?.voice?.notes ?? "",
    },
    footer_text: k?.footer_text ?? "",
    slide_numbers: k?.slide_numbers ?? true,
    layout_prefs: {
      default_layout: k?.layout_prefs?.default_layout ?? "content",
      title_align: k?.layout_prefs?.title_align ?? "left",
      density: k?.layout_prefs?.density ?? "comfortable",
      show_logo: k?.layout_prefs?.show_logo ?? true,
      logo_position: k?.layout_prefs?.logo_position ?? "top_right",
    },
    logo: k?.logo_data_url ?? null,
    logoChanged: false,
  }
}

function draftToKit(d: Draft): BrandKit {
  return {
    id: "draft",
    name: d.name,
    company_name: d.company_name,
    tagline: d.tagline,
    palette: d.palette,
    fonts: d.fonts,
    voice: { formality: d.voice.formality, jargon_level: d.voice.jargon_level, banned_words: [], notes: d.voice.notes },
    footer_text: d.footer_text,
    slide_numbers: d.slide_numbers,
    layout_prefs: d.layout_prefs,
    logo_data_url: d.logo,
  }
}

function toInput(d: Draft, makeDefault?: boolean): BrandKitInput {
  const input: BrandKitInput = {
    name: d.name.trim(),
    company_name: d.company_name.trim(),
    tagline: d.tagline.trim(),
    palette: d.palette,
    fonts: d.fonts,
    voice: {
      formality: d.voice.formality,
      jargon_level: d.voice.jargon_level,
      banned_words: d.voice.banned.split(",").map((s) => s.trim()).filter(Boolean),
      notes: d.voice.notes,
    },
    footer_text: d.footer_text,
    slide_numbers: d.slide_numbers,
    layout_prefs: d.layout_prefs,
  }
  if (d.logoChanged) {
    if (d.logo) input.logo_data_url = d.logo
    else input.remove_logo = true
  }
  if (makeDefault) input.make_default = true
  return input
}

export function BrandKitManager({ onBack }: { onBack: () => void }) {
  const { kits, kitsLoaded, reloadKits, markReadOnly } = useStudio()
  const [editing, setEditing] = useState<{ kit: BrandKit | null } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [confirmDel, setConfirmDel] = useState<BrandKit | null>(null)

  async function openKit(k: BrandKit) {
    setError(null)
    try {
      setEditing({ kit: unwrapKit(await getBrandKit(k.id)) })
    } catch (e) {
      setError(errText(e))
    }
  }
  async function act(id: string, fn: () => Promise<unknown>) {
    setBusy(id)
    setError(null)
    try {
      await fn()
      invalidateKit()
      await reloadKits()
    } catch (e) {
      if (e instanceof BiApiError && e.forbidden) {
        markReadOnly()
        setError("Only admins can change brand kits.")
      } else setError(errText(e))
    } finally {
      setBusy(null)
    }
  }

  if (editing)
    return (
      <KitEditor
        kit={editing.kit}
        onBack={() => setEditing(null)}
        onSaved={async () => {
          invalidateKit()
          await reloadKits()
          setEditing(null)
        }}
      />
    )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" /> Decks
          </Button>
          <h1 className="text-lg font-semibold text-foreground">Brand kits</h1>
        </div>
        <Button size="sm" onClick={() => setEditing({ kit: null })}>
          <Plus className="h-4 w-4" /> New brand kit
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">A brand kit drives the colours, fonts, logo and footer of every slide. Admins create and edit kits; everyone can use them.</p>
      <ErrorNote message={error} />
      {!kitsLoaded && <p className="text-sm text-muted-foreground">Loading…</p>}
      {kitsLoaded && kits.length === 0 && (
        <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          No brand kit yet. Decks use neutral theme defaults until you create one.
        </div>
      )}
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {kits.map((k) => (
          <li key={k.id} className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-sm font-semibold text-foreground">{k.name}</div>
                <div className="text-xs text-muted-foreground">{k.company_name || "No company name"}</div>
              </div>
              {k.is_default && <Pill tone="good">Default</Pill>}
            </div>
            <div className="my-3 flex gap-1" aria-label="Palette">
              {[k.palette.primary, k.palette.secondary, k.palette.accent, ...k.palette.chart.slice(0, 4)].map((c, i) => (
                <span key={i} className="h-5 w-5 rounded border border-border" style={{ background: c }} title={c} />
              ))}
            </div>
            <div className="flex flex-wrap gap-1">
              <Button size="sm" variant="secondary" className="h-7 text-xs" onClick={() => openKit(k)}>
                Edit
              </Button>
              {!k.is_default && (
                <Button size="sm" variant="ghost" className="h-7 text-xs" disabled={busy === k.id} onClick={() => act(k.id, () => setDefaultBrandKit(k.id))}>
                  <Star className="h-3.5 w-3.5" /> Make default
                </Button>
              )}
              <Button size="sm" variant="ghost-destructive" className="ml-auto h-7 px-2" aria-label={`Delete ${k.name}`} onClick={() => setConfirmDel(k)}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </li>
        ))}
      </ul>
      {confirmDel && (
        <Modal
          title="Delete brand kit?"
          onClose={() => setConfirmDel(null)}
          footer={
            <>
              <Button variant="outline" size="sm" onClick={() => setConfirmDel(null)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => {
                  const k = confirmDel
                  setConfirmDel(null)
                  void act(k.id, () => deleteBrandKit(k.id))
                }}
              >
                Delete
              </Button>
            </>
          }
        >
          <p className="text-sm">Decks using “{confirmDel.name}” keep working with theme defaults.</p>
        </Modal>
      )}
    </div>
  )
}

// ── editor ───────────────────────────────────────────────────────────
function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const [text, setText] = useState(value)
  useEffect(() => setText(value), [value])
  return (
    <div className="space-y-1">
      <span className="block text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1.5">
        <input type="color" aria-label={`${label} colour picker`} value={isHex(value) ? value : "#000000"} onChange={(e) => onChange(e.target.value.toUpperCase())} className="h-8 w-9 cursor-pointer rounded border border-border bg-transparent p-0.5" />
        <input
          aria-label={`${label} hex`}
          className={`${fieldCls} font-mono`}
          value={text}
          maxLength={7}
          aria-invalid={!isHex(text)}
          onChange={(e) => {
            setText(e.target.value)
            if (isHex(e.target.value)) onChange(e.target.value.toUpperCase())
          }}
        />
      </div>
    </div>
  )
}

function KitEditor({ kit, onBack, onSaved }: { kit: BrandKit | null; onBack: () => void; onSaved: () => Promise<void> }) {
  const { options, markReadOnly } = useStudio()
  const [d, setD] = useState<Draft>(() => draftFrom(kit))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [url, setUrl] = useState("")
  const [suggesting, setSuggesting] = useState(false)
  const [suggestion, setSuggestion] = useState<BrandSuggestion | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const maxBytes = options?.max_logo_bytes ?? FALLBACK_LOGO_BYTES
  const types = options?.logo_types ?? FALLBACK_TYPES
  const fonts = options?.fonts?.length ? options.fonts.map((f) => f.name) : ["Calibri", "Arial", "Georgia", "Inter", "Roboto"]
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }))

  function onLogo(file: File | undefined) {
    setError(null)
    if (!file) return
    if (!types.includes(file.type)) return setError(`Logo must be PNG, JPEG or SVG (got ${file.type || "unknown"}).`)
    if (file.size > maxBytes) return setError(`Logo is ${(file.size / 1024).toFixed(0)} KB; the limit is ${(maxBytes / 1024).toFixed(0)} KB.`)
    const r = new FileReader()
    r.onload = () => {
      const res = String(r.result)
      if (!safeDataImage(res)) return setError("Could not read that image.")
      setD((x) => ({ ...x, logo: res, logoChanged: true }))
    }
    r.onerror = () => setError("Could not read that file.")
    r.readAsDataURL(file)
  }

  async function save(makeDefault?: boolean) {
    setError(null)
    if (!d.name.trim()) return setError("Give the brand kit a name.")
    if (!isHex(d.palette.primary) || d.palette.chart.some((c) => !isHex(c))) return setError("All colours must be #RRGGBB.")
    setSaving(true)
    try {
      if (kit) await updateBrandKit(kit.id, toInput(d, makeDefault))
      else await createBrandKit(toInput(d, makeDefault))
      await onSaved()
    } catch (e) {
      if (e instanceof BiApiError && e.forbidden) {
        markReadOnly()
        setError("Only admins can create or edit brand kits.")
      } else setError(errText(e))
      setSaving(false)
    }
  }

  async function suggest() {
    setError(null)
    setSuggestion(null)
    setSuggesting(true)
    try {
      setSuggestion(await suggestBrandFromUrl(url.trim()))
    } catch (e) {
      setError(e instanceof BiApiError && e.capped ? `Credit limit reached: ${e.message}` : errText(e))
    } finally {
      setSuggesting(false)
    }
  }

  const theme = useMemo(() => mergeTheme(draftToKit(d), null), [d])
  const coverSlide: Slide = { id: "p1", layout: "title", title: d.company_name || "Your company", subtitle: d.tagline || "Quarterly business review", notes: "", blocks: [] }
  const bodySlide: Slide = {
    id: "p2",
    layout: "content",
    title: "Slide title in your heading font",
    notes: "",
    blocks: [
      { type: "text", id: "pt", role: "body", items: [{ text: "Body copy uses the body font and text colour.", bullet: true }, { text: "Charts take the six chart colours in order.", bullet: true }] },
      { type: "shape", id: "psh", shape: "accent_bar", color: "accent" },
    ],
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" /> Brand kits
          </Button>
          <h1 className="text-lg font-semibold text-foreground">{kit ? `Edit “${kit.name}”` : "New brand kit"}</h1>
        </div>
        <div className="flex gap-2">
          {!kit?.is_default && (
            <Button variant="outline" size="sm" disabled={saving} onClick={() => save(true)}>
              <Star className="h-4 w-4" /> Save as default
            </Button>
          )}
          <Button size="sm" disabled={saving} onClick={() => save()}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Save
          </Button>
        </div>
      </div>
      <ErrorNote message={error} />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <fieldset className="space-y-3 rounded-lg border border-border p-3">
            <legend className="px-1 text-xs font-semibold text-muted-foreground">Identity</legend>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Kit name" htmlFor="bk-name">
                <input id="bk-name" className={fieldCls} value={d.name} maxLength={80} onChange={(e) => set("name", e.target.value)} />
              </Field>
              <Field label="Company name" htmlFor="bk-co">
                <input id="bk-co" className={fieldCls} value={d.company_name} maxLength={120} onChange={(e) => set("company_name", e.target.value)} />
              </Field>
            </div>
            <Field label="Tagline" htmlFor="bk-tag">
              <input id="bk-tag" className={fieldCls} value={d.tagline} maxLength={160} onChange={(e) => set("tagline", e.target.value)} />
            </Field>
            <div className="space-y-1">
              <span className="block text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Logo</span>
              <div className="flex items-center gap-3">
                <div className="flex h-14 w-24 items-center justify-center overflow-hidden rounded border border-border bg-white">
                  {safeDataImage(d.logo) ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={d.logo!} alt="Logo preview" className="max-h-full max-w-full object-contain" />
                  ) : (
                    <span className="text-[11px] text-slate-400">No logo</span>
                  )}
                </div>
                <input ref={fileRef} type="file" accept={types.join(",")} className="sr-only" aria-label="Upload logo" onChange={(e) => onLogo(e.target.files?.[0])} />
                <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()}>
                  <Upload className="h-4 w-4" /> Upload
                </Button>
                {d.logo && (
                  <Button size="sm" variant="ghost" onClick={() => setD((x) => ({ ...x, logo: null, logoChanged: true }))}>
                    Remove
                  </Button>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground">PNG, JPEG or SVG, up to {(maxBytes / 1024).toFixed(0)} KB.</p>
            </div>
          </fieldset>

          <fieldset className="space-y-3 rounded-lg border border-border p-3">
            <legend className="px-1 text-xs font-semibold text-muted-foreground">Suggest from my website</legend>
            <div className="flex gap-2">
              <input aria-label="Website URL" className={fieldCls} placeholder="https://www.yourcompany.co.za" value={url} onChange={(e) => setUrl(e.target.value)} />
              <Button size="sm" variant="outline" disabled={!/^https?:\/\//i.test(url.trim()) || suggesting} onClick={suggest}>
                {suggesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4" />} Suggest
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">Reads the public page (uses 5 scrape credits). Nothing is applied until you confirm.</p>
            {suggestion && (
              <div className="space-y-2 rounded-md border border-primary/30 bg-primary/5 p-3 text-xs">
                <div className="font-semibold text-foreground">Suggestions from {suggestion.source_url}</div>
                {suggestion.company_name && <div>Company: {suggestion.company_name}</div>}
                {suggestion.tagline && <div>Tagline: {suggestion.tagline}</div>}
                {suggestion.palette && (
                  <div className="flex items-center gap-1">
                    Colours:
                    {Object.entries(suggestion.palette).map(([k, v]) => (
                      <span key={k} className="inline-flex items-center gap-1">
                        <span className="h-4 w-4 rounded border border-border" style={{ background: isHex(v) ? v : "transparent" }} /> {k}
                      </span>
                    ))}
                  </div>
                )}
                {suggestion.fonts && <div>Fonts: {[suggestion.fonts.heading, suggestion.fonts.body].filter(Boolean).join(" / ")}</div>}
                {suggestion.logo_url && <div className="text-muted-foreground">A logo was found, but images are not downloaded automatically. Please upload your logo file.</div>}
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() => {
                      setD((x) => ({
                        ...x,
                        company_name: suggestion.company_name ?? x.company_name,
                        tagline: suggestion.tagline ?? x.tagline,
                        palette: { ...x.palette, ...Object.fromEntries(Object.entries(suggestion.palette ?? {}).filter(([, v]) => isHex(v))) },
                        fonts: { heading: suggestion.fonts?.heading && fonts.includes(suggestion.fonts.heading) ? suggestion.fonts.heading : x.fonts.heading, body: suggestion.fonts?.body && fonts.includes(suggestion.fonts.body) ? suggestion.fonts.body : x.fonts.body },
                      }))
                      setSuggestion(null)
                    }}
                  >
                    Apply suggestions
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setSuggestion(null)}>
                    Dismiss
                  </Button>
                </div>
              </div>
            )}
          </fieldset>

          <fieldset className="space-y-3 rounded-lg border border-border p-3">
            <legend className="px-1 text-xs font-semibold text-muted-foreground">Colours</legend>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {(["primary", "secondary", "accent", "background", "text"] as const).map((k) => (
                <ColorField key={k} label={k} value={d.palette[k]} onChange={(v) => set("palette", { ...d.palette, [k]: v })} />
              ))}
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {d.palette.chart.map((c, i) => (
                <ColorField key={i} label={`Chart ${i + 1}`} value={c} onChange={(v) => set("palette", { ...d.palette, chart: d.palette.chart.map((x, j) => (j === i ? v : x)) })} />
              ))}
            </div>
          </fieldset>

          <fieldset className="space-y-3 rounded-lg border border-border p-3">
            <legend className="px-1 text-xs font-semibold text-muted-foreground">Typography and layout</legend>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Heading font" htmlFor="bk-fh">
                <select id="bk-fh" className={fieldCls} value={d.fonts.heading} onChange={(e) => set("fonts", { ...d.fonts, heading: e.target.value })}>
                  {fonts.map((f) => (
                    <option key={f}>{f}</option>
                  ))}
                </select>
              </Field>
              <Field label="Body font" htmlFor="bk-fb">
                <select id="bk-fb" className={fieldCls} value={d.fonts.body} onChange={(e) => set("fonts", { ...d.fonts, body: e.target.value })}>
                  {fonts.map((f) => (
                    <option key={f}>{f}</option>
                  ))}
                </select>
              </Field>
              <Field label="Title alignment" htmlFor="bk-ta">
                <select id="bk-ta" className={fieldCls} value={d.layout_prefs.title_align} onChange={(e) => set("layout_prefs", { ...d.layout_prefs, title_align: e.target.value })}>
                  <option value="left">Left</option>
                  <option value="center">Centre</option>
                </select>
              </Field>
              <Field label="Density" htmlFor="bk-den">
                <select id="bk-den" className={fieldCls} value={d.layout_prefs.density} onChange={(e) => set("layout_prefs", { ...d.layout_prefs, density: e.target.value })}>
                  <option value="comfortable">Comfortable</option>
                  <option value="compact">Compact</option>
                </select>
              </Field>
            </div>
            <Field label="Footer text" htmlFor="bk-ft">
              <input id="bk-ft" className={fieldCls} value={d.footer_text} maxLength={160} onChange={(e) => set("footer_text", e.target.value)} placeholder="Confidential" />
            </Field>
            <div className="flex flex-wrap gap-5 text-xs">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={d.slide_numbers} onChange={(e) => set("slide_numbers", e.target.checked)} /> Slide numbers
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={d.layout_prefs.show_logo} onChange={(e) => set("layout_prefs", { ...d.layout_prefs, show_logo: e.target.checked })} /> Show logo on slides
              </label>
            </div>
          </fieldset>

          <fieldset className="space-y-3 rounded-lg border border-border p-3">
            <legend className="px-1 text-xs font-semibold text-muted-foreground">Voice (guides AI writing)</legend>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Formality" htmlFor="bk-form">
                <select id="bk-form" className={fieldCls} value={d.voice.formality} onChange={(e) => set("voice", { ...d.voice, formality: e.target.value })}>
                  <option value="formal">Formal</option>
                  <option value="neutral">Neutral</option>
                  <option value="casual">Casual</option>
                </select>
              </Field>
              <Field label="Jargon level" htmlFor="bk-jar">
                <select id="bk-jar" className={fieldCls} value={d.voice.jargon_level} onChange={(e) => set("voice", { ...d.voice, jargon_level: e.target.value })}>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </Field>
            </div>
            <Field label="Words to avoid (comma separated)" htmlFor="bk-ban">
              <input id="bk-ban" className={fieldCls} value={d.voice.banned} onChange={(e) => set("voice", { ...d.voice, banned: e.target.value })} />
            </Field>
            <Field label="Notes" htmlFor="bk-notes">
              <input id="bk-notes" className={fieldCls} value={d.voice.notes} maxLength={500} onChange={(e) => set("voice", { ...d.voice, notes: e.target.value })} />
            </Field>
          </fieldset>
        </div>

        <div className="space-y-3 lg:sticky lg:top-4 lg:self-start">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Live preview</h2>
          <div className="overflow-hidden rounded-md border border-border shadow">
            <SlideRenderer slide={coverSlide} index={0} total={2} theme={theme} states={{}} data={{}} />
          </div>
          <div className="overflow-hidden rounded-md border border-border shadow">
            <SlideRenderer slide={bodySlide} index={1} total={2} theme={theme} states={{}} data={{}} />
          </div>
          <div className="flex gap-1" aria-label="Chart colour order">
            {d.palette.chart.map((c, i) => (
              <div key={i} className="h-8 flex-1 rounded" style={{ background: c }} title={`Chart colour ${i + 1}: ${c}`} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
