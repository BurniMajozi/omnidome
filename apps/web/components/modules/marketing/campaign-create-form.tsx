"use client"

import { useState } from "react"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useMarketingLoad } from "@/lib/use-marketing-load"
import type { AudienceSegment } from "@/lib/marketing-api"
import { createCampaignBody, resultMessage } from "@/lib/marketing-zernio-api"

const CHANNELS: Array<[string, string]> = [
  ["email", "Email"],
  ["social", "Social"],
  ["search", "Search"],
  ["display", "Display"],
  ["sms", "SMS"],
]

const startOfDayIso = (d: string) => new Date(`${d}T00:00:00`).toISOString()
const endOfDayIso = (d: string) => new Date(`${d}T23:59:59`).toISOString()

export function CampaignCreateForm({
  onCreated,
  onCancel,
  onOpenAudiences,
}: {
  onCreated: () => void
  onCancel: () => void
  onOpenAudiences?: () => void
}) {
  const audiences = useMarketingLoad<AudienceSegment[]>("/segments")
  const list = audiences.value.state === "ready" && Array.isArray(audiences.value.data) ? audiences.value.data : []
  const [name, setName] = useState("")
  const [channel, setChannel] = useState("email")
  const [description, setDescription] = useState("")
  const [budget, setBudget] = useState("")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [audienceId, setAudienceId] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const budgetNum = budget.trim() === "" ? null : Number(budget)
  const budgetBad = budgetNum !== null && (!Number.isFinite(budgetNum) || budgetNum < 0)
  const datesBad = Boolean(startDate && endDate && endDate < startDate)
  const canSubmit = name.trim().length > 0 && !budgetBad && !datesBad && !busy

  const submit = async () => {
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    // Blank optional fields are sent as null, never as "" (the server rejects empty dates).
    const r = await createCampaignBody({
      name: name.trim(),
      channel,
      description: description.trim() || null,
      budget_zar: budgetNum,
      start_date: startDate ? startOfDayIso(startDate) : null,
      end_date: endDate ? endOfDayIso(endDate) : null,
      audience_id: audienceId || null,
    })
    setBusy(false)
    if (!r.ok) {
      setError(resultMessage(r))
      return
    }
    onCreated()
  }

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="text-sm">Create Campaign</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <label htmlFor="camp-name" className="mb-1 block text-xs font-medium text-muted-foreground">Name</label>
          <Input id="camp-name" placeholder="Campaign name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="camp-channel" className="mb-1 block text-xs font-medium text-muted-foreground">Channel</label>
            <select id="camp-channel" value={channel} onChange={(e) => setChannel(e.target.value)} className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
              {CHANNELS.map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="camp-budget" className="mb-1 block text-xs font-medium text-muted-foreground">Budget (ZAR, optional)</label>
            <Input id="camp-budget" type="number" min="0" step="0.01" placeholder="0" value={budget} onChange={(e) => setBudget(e.target.value)} />
            {budgetBad && <p className="mt-1 text-[11px] text-red-400">Enter zero or a positive amount.</p>}
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="camp-start" className="mb-1 block text-xs font-medium text-muted-foreground">Start date (optional)</label>
            <Input id="camp-start" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </div>
          <div>
            <label htmlFor="camp-end" className="mb-1 block text-xs font-medium text-muted-foreground">End date (optional)</label>
            <Input id="camp-end" type="date" min={startDate || undefined} value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            {datesBad && <p className="mt-1 text-[11px] text-red-400">The end date is before the start date.</p>}
          </div>
        </div>
        <div>
          <label htmlFor="camp-aud" className="mb-1 block text-xs font-medium text-muted-foreground">Audience (optional)</label>
          {audiences.value.state === "loading" ? (
            <p className="text-xs text-muted-foreground">Loading audiences…</p>
          ) : audiences.value.state !== "ready" ? (
            <p className="text-xs text-amber-500">
              Audiences could not be loaded.{" "}
              <button type="button" className="underline" onClick={audiences.reload}>Retry</button>
            </p>
          ) : list.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No audiences yet.{" "}
              {onOpenAudiences ? (
                <button type="button" onClick={onOpenAudiences} className="text-primary underline-offset-2 hover:underline">
                  Create one under Ad Campaigns, Audiences
                </button>
              ) : (
                "Create one under Ad Campaigns, Audiences."
              )}
            </p>
          ) : (
            <>
              <select id="camp-aud" value={audienceId} onChange={(e) => setAudienceId(e.target.value)} className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
                <option value="">No audience</option>
                {list.map((a) => (
                  <option key={a.id} value={a.id}>{a.name} ({a.type}, {a.member_count ?? 0} members)</option>
                ))}
              </select>
              {audienceId && channel !== "email" && (
                <p className="mt-1 text-[11px] text-amber-500">The audience is saved on the campaign, but only email sends use audience members today.</p>
              )}
            </>
          )}
        </div>
        <div>
          <label htmlFor="camp-desc" className="mb-1 block text-xs font-medium text-muted-foreground">Description (optional)</label>
          <Textarea id="camp-desc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} className="resize-none text-sm" />
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={submit} disabled={!canSubmit}>
            {busy && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
            {busy ? "Creating…" : "Create"}
          </Button>
          <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
        </div>
        {error && <p className="text-sm text-red-400" role="alert">{error}</p>}
      </CardContent>
    </Card>
  )
}
