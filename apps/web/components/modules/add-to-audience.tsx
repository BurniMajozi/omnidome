"use client"

import { useState } from "react"
import { Check, Loader2, Megaphone } from "lucide-react"
import { Button } from "@/components/ui/button"
import { AUDIENCE_PLATFORMS, type AudiencePlatform, type AudienceSegment } from "@/lib/marketing-api"

/** Inline "send this to Marketing → Audiences" control used by Sales lead sources. */
export function AddToAudience({
  existing,
  defaultName,
  onPush,
  disabled,
}: {
  existing?: AudienceSegment
  defaultName: string
  onPush: (platform: AudiencePlatform, name: string) => Promise<AudienceSegment>
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [platform, setPlatform] = useState<AudiencePlatform>(existing?.platform ?? "google_ads")
  const [name, setName] = useState(existing?.name ?? defaultName)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError("Enter an audience name")
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onPush(platform, name.trim())
      setOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't send it to Marketing")
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    const platformLabel = AUDIENCE_PLATFORMS.find((p) => p.id === existing?.platform)?.label.split(" (")[0]
    return existing ? (
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-flex items-center gap-1 rounded-md border border-emerald-500/40 px-1.5 py-0.5 text-[10px] text-emerald-400"
          title={`In Marketing → Audiences as "${existing.name}"`}>
          <Check className="h-3 w-3" /> In Marketing · {platformLabel}
        </span>
        <Button variant="ghost" size="sm" className="h-7 px-2 text-[11px]" disabled={disabled}
          onClick={() => { setName(existing.name); setPlatform(existing.platform); setOpen(true) }}>
          Update
        </Button>
      </span>
    ) : (
      <Button variant="outline" size="sm" className="h-7 gap-1 px-2 text-[11px]" disabled={disabled} onClick={() => setOpen(true)}>
        <Megaphone className="h-3 w-3" /> Add to audience
      </Button>
    )
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-1.5 rounded-lg border border-primary/30 bg-primary/5 p-1.5">
      <input value={name} onChange={(e) => { setName(e.target.value); setError(null) }} maxLength={255} aria-label="Audience name"
        className="min-w-[160px] flex-1 rounded-md border border-border bg-background px-2 py-1 text-[11px] focus:outline-none focus:ring-1 focus:ring-primary" />
      <select value={platform} onChange={(e) => setPlatform(e.target.value as AudiencePlatform)} aria-label="Ad platform"
        className="rounded-md border border-border bg-background px-1.5 py-1 text-[11px]">
        {AUDIENCE_PLATFORMS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
      </select>
      <Button type="submit" size="sm" className="h-7 gap-1 px-2 text-[11px]" disabled={saving}>
        {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Megaphone className="h-3 w-3" />}
        {existing ? "Update audience" : "Send to Marketing"}
      </Button>
      <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-[11px]" onClick={() => { setOpen(false); setError(null) }}>
        Cancel
      </Button>
      {error && <p className="w-full text-[10px] text-red-400">{error}</p>}
    </form>
  )
}
