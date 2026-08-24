"use client"

/**
 * Marketing Management — demo surface for the marketing backend.
 * Tabs: Prospects & Segments (spreadsheet import), Campaigns (CRUD),
 * WhatsApp broadcasts (create/send/stats), Leads (scores).
 * Standalone page; uses lib/marketing-demo-api.ts.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import {
  listCampaigns, createCampaign, deleteCampaign,
  listContacts, bulkImportContacts, parseProspectCsv,
  listBroadcasts, createBroadcast, sendBroadcast, getBroadcastStats,
  listLeadScores,
  type Campaign, type Contact, type Broadcast, type BroadcastStats, type LeadScore,
} from "@/lib/marketing-demo-api"

const ZAR = (n?: number | null) => (n == null ? "—" : "R " + Number(n).toLocaleString("en-ZA"))
const TABS = ["prospects", "campaigns", "whatsapp", "leads"] as const
type Tab = (typeof TABS)[number]
const TAB_LABEL: Record<Tab, string> = {
  prospects: "Prospects & Segments", campaigns: "Campaigns", whatsapp: "WhatsApp", leads: "Leads",
}

const PROSPECT_TEMPLATE = `name,phone,email,segment
Sandton Estate HOA,+27821112201,ops@sandtonhoa.co.za,Residential
MetroMall Facilities,+27821112202,facilities@metromall.co.za,Commercial
`

export default function MarketingPage() {
  const [tab, setTab] = useState<Tab>("prospects")
  const [error, setError] = useState<string | null>(null)

  // shared data
  const [contacts, setContacts] = useState<Contact[]>([])
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([])
  const [leads, setLeads] = useState<LeadScore[]>([])

  const reloadAll = useCallback(async () => {
    setError(null)
    try {
      const [c, cp, b, l] = await Promise.all([
        listContacts().catch(() => []),
        listCampaigns().catch(() => []),
        listBroadcasts().catch(() => []),
        listLeadScores().catch(() => []),
      ])
      setContacts(c || []); setCampaigns(cp || []); setBroadcasts(b || []); setLeads(l || [])
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }, [])
  useEffect(() => { reloadAll() }, [reloadAll])

  const segments = useMemo(() => {
    const m = new Map<string, number>()
    for (const c of contacts) for (const t of c.tags ?? []) m.set(t, (m.get(t) ?? 0) + 1)
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [contacts])

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Marketing Management</h1>
            <p className="text-sm text-muted-foreground">
              Import prospects, segment them, run campaigns, broadcast on WhatsApp, and score leads.
            </p>
          </div>
          <Link href="/dashboard" className="text-sm text-primary hover:underline">← Back to dashboard</Link>
        </div>

        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Tile label="Prospects" value={String(contacts.length)} />
          <Tile label="Segments" value={String(segments.length)} />
          <Tile label="Campaigns" value={String(campaigns.length)} />
          <Tile label="Broadcasts" value={String(broadcasts.length)} />
        </div>

        <div className="mb-4 flex flex-wrap gap-2">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-lg px-3 py-1.5 text-sm ${tab === t ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/70"}`}
            >
              {TAB_LABEL[t]}
            </button>
          ))}
        </div>

        {error && <p className="mb-4 rounded bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}

        {tab === "prospects" && (
          <ProspectsTab contacts={contacts} segments={segments} reload={reloadAll} setError={setError} />
        )}
        {tab === "campaigns" && (
          <CampaignsTab campaigns={campaigns} segments={segments} reload={reloadAll} setError={setError} />
        )}
        {tab === "whatsapp" && (
          <WhatsAppTab broadcasts={broadcasts} contactCount={contacts.length} reload={reloadAll} setError={setError} />
        )}
        {tab === "leads" && <LeadsTab leads={leads} />}
      </div>
    </div>
  )
}

// ── Prospects & Segments ───────────────────────────────────────────────
function ProspectsTab({ contacts, segments, reload, setError }: {
  contacts: Contact[]; segments: [string, number][]; reload: () => Promise<void>; setError: (s: string | null) => void
}) {
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<{ imported: number; errors: unknown[] } | null>(null)
  const [q, setQ] = useState("")
  const [seg, setSeg] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const onImport = async (file: File) => {
    setImporting(true); setError(null); setResult(null)
    try {
      const rows = parseProspectCsv(await file.text())
      if (rows.length === 0) throw new Error("No valid rows (need name + phone columns)")
      const res = await bulkImportContacts(rows)
      setResult(res); await reload()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setImporting(false); if (fileRef.current) fileRef.current.value = "" }
  }
  const downloadTemplate = () => {
    const url = URL.createObjectURL(new Blob([PROSPECT_TEMPLATE], { type: "text/csv" }))
    const a = document.createElement("a"); a.href = url; a.download = "prospects_template.csv"; a.click(); URL.revokeObjectURL(url)
  }

  const filtered = contacts.filter((c) =>
    (!seg || (c.tags ?? []).includes(seg)) &&
    (!q || c.name.toLowerCase().includes(q.toLowerCase()) || c.phone_number.includes(q))
  )

  return (
    <div className="space-y-6">
      <section className="rounded-xl border bg-card p-5">
        <h2 className="mb-1 text-lg font-medium">Import a prospect list</h2>
        <p className="mb-4 text-sm text-muted-foreground">CSV with columns: name, phone, email, segment (e.g. Residential / Commercial).</p>
        <div className="flex flex-wrap items-center gap-3">
          <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) onImport(f) }} />
          <Button onClick={() => fileRef.current?.click()} disabled={importing}>{importing ? "Importing…" : "Choose file & import"}</Button>
          <Button variant="outline" onClick={downloadTemplate}>Download template</Button>
        </div>
        {result && <p className="mt-3 rounded bg-muted/50 p-2 text-sm"><b>{result.imported}</b> prospects imported{result.errors.length ? `, ${result.errors.length} errors` : ""}.</p>}
      </section>

      <section className="rounded-xl border bg-card p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-medium">Prospects</h2>
          <Input placeholder="Search name or phone…" value={q} onChange={(e) => setQ(e.target.value)} className="w-full max-w-xs" />
        </div>
        <div className="mb-3 flex flex-wrap gap-2">
          <button onClick={() => setSeg(null)} className={`rounded-full px-3 py-1 text-xs ${!seg ? "bg-primary text-primary-foreground" : "bg-muted"}`}>All ({contacts.length})</button>
          {segments.map(([s, n]) => (
            <button key={s} onClick={() => setSeg(s)} className={`rounded-full px-3 py-1 text-xs ${seg === s ? "bg-primary text-primary-foreground" : "bg-muted"}`}>{s} ({n})</button>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead><tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-3 font-medium">Name</th><th className="py-2 pr-3 font-medium">Phone</th>
              <th className="py-2 pr-3 font-medium">Email</th><th className="py-2 pr-3 font-medium">Segment</th>
            </tr></thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={4} className="py-8 text-center text-muted-foreground">No prospects — import a list above.</td></tr>
              ) : filtered.map((c) => (
                <tr key={c.id} className="border-b last:border-0">
                  <td className="py-2 pr-3 font-medium">{c.name}</td>
                  <td className="py-2 pr-3 text-muted-foreground">{c.phone_number}</td>
                  <td className="py-2 pr-3 text-muted-foreground">{c.email ?? "—"}</td>
                  <td className="py-2 pr-3">{(c.tags ?? []).map((t) => <Badge key={t} variant="secondary" className="mr-1">{t}</Badge>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

// ── Campaigns ──────────────────────────────────────────────────────────
function CampaignsTab({ campaigns, segments, reload, setError }: {
  campaigns: Campaign[]; segments: [string, number][]; reload: () => Promise<void>; setError: (s: string | null) => void
}) {
  const [name, setName] = useState("")
  const [channel, setChannel] = useState("email")
  const [budget, setBudget] = useState("")
  const [saving, setSaving] = useState(false)
  const [q, setQ] = useState("")

  const onCreate = async () => {
    if (!name.trim()) return
    setSaving(true); setError(null)
    try {
      await createCampaign({ name, channel, budget_zar: budget ? Number(budget) : undefined })
      setName(""); setBudget(""); await reload()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setSaving(false) }
  }
  const onDelete = async (id: string) => {
    try { await deleteCampaign(id); await reload() } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }
  const filtered = campaigns.filter((c) => !q || c.name.toLowerCase().includes(q.toLowerCase()))

  return (
    <div className="space-y-6">
      <section className="rounded-xl border bg-card p-5">
        <h2 className="mb-3 text-lg font-medium">Create a campaign</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[200px]">
            <label className="mb-1 block text-xs text-muted-foreground">Name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Residential Guarding — Spring" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Channel</label>
            <select value={channel} onChange={(e) => setChannel(e.target.value)} className="rounded-md border bg-background px-3 py-2 text-sm">
              <option value="email">Email</option><option value="sms">SMS</option>
              <option value="whatsapp">WhatsApp</option><option value="social">Social</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Budget (R)</label>
            <Input type="number" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="15000" className="w-32" />
          </div>
          <Button onClick={onCreate} disabled={saving || !name.trim()}>{saving ? "Creating…" : "Create campaign"}</Button>
        </div>
        {segments.length > 0 && <p className="mt-2 text-xs text-muted-foreground">Tip: you have segments {segments.map((s) => s[0]).join(", ")} to target.</p>}
      </section>

      <section className="rounded-xl border bg-card p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-medium">Campaigns</h2>
          <Input placeholder="Search campaigns…" value={q} onChange={(e) => setQ(e.target.value)} className="w-full max-w-xs" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead><tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-3 font-medium">Name</th><th className="py-2 pr-3 font-medium">Channel</th>
              <th className="py-2 pr-3 font-medium">Status</th><th className="py-2 pr-3 font-medium">Budget</th><th></th>
            </tr></thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={5} className="py-8 text-center text-muted-foreground">No campaigns yet — create one above.</td></tr>
              ) : filtered.map((c) => (
                <tr key={c.id} className="border-b last:border-0">
                  <td className="py-2 pr-3 font-medium">{c.name}</td>
                  <td className="py-2 pr-3"><Badge variant="secondary">{c.channel}</Badge></td>
                  <td className="py-2 pr-3">{c.status}</td>
                  <td className="py-2 pr-3">{ZAR(c.budget_zar)}</td>
                  <td className="py-2 pr-3 text-right"><button onClick={() => onDelete(c.id)} className="text-xs text-destructive hover:underline">Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

// ── WhatsApp broadcasts ────────────────────────────────────────────────
function WhatsAppTab({ broadcasts, contactCount, reload, setError }: {
  broadcasts: Broadcast[]; contactCount: number; reload: () => Promise<void>; setError: (s: string | null) => void
}) {
  const [name, setName] = useState("")
  const [content, setContent] = useState("")
  const [saving, setSaving] = useState(false)
  const [stats, setStats] = useState<Record<string, BroadcastStats>>({})

  const onCreate = async () => {
    if (!name.trim() || !content.trim()) return
    setSaving(true); setError(null)
    try { await createBroadcast({ name, template_name: "promo", content }); setName(""); setContent(""); await reload() }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setSaving(false) }
  }
  const onSend = async (id: string) => {
    setError(null)
    try { await sendBroadcast(id); const s = await getBroadcastStats(id); setStats((p) => ({ ...p, [id]: s })); await reload() }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border bg-card p-5">
        <h2 className="mb-1 text-lg font-medium">New WhatsApp broadcast</h2>
        <p className="mb-3 text-sm text-muted-foreground">{contactCount} prospects available as recipients.</p>
        <div className="space-y-3">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Broadcast name — e.g. Armed response promo" />
          <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={3}
            placeholder="24/7 armed response and guarding from R299/mo. Reply YES for a free site assessment."
            className="w-full rounded-md border bg-background px-3 py-2 text-sm" />
          <Button onClick={onCreate} disabled={saving || !name.trim() || !content.trim()}>{saving ? "Creating…" : "Create broadcast"}</Button>
        </div>
      </section>

      <section className="rounded-xl border bg-card p-5">
        <h2 className="mb-3 text-lg font-medium">Broadcasts</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead><tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-3 font-medium">Name</th><th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 pr-3 font-medium">Recipients</th><th className="py-2 pr-3 font-medium">Results</th><th></th>
            </tr></thead>
            <tbody>
              {broadcasts.length === 0 ? (
                <tr><td colSpan={5} className="py-8 text-center text-muted-foreground">No broadcasts yet.</td></tr>
              ) : broadcasts.map((b) => {
                const s = stats[b.id]
                return (
                  <tr key={b.id} className="border-b last:border-0">
                    <td className="py-2 pr-3 font-medium">{b.name}</td>
                    <td className="py-2 pr-3"><Badge variant={b.status === "SENT" ? "default" : "secondary"}>{b.status}</Badge></td>
                    <td className="py-2 pr-3">{b.recipient_count ?? "—"}</td>
                    <td className="py-2 pr-3 text-muted-foreground">{s ? `${s.sent_count} sent · ${s.delivered_count} delivered · ${s.read_count} read` : "—"}</td>
                    <td className="py-2 pr-3 text-right"><Button variant="outline" onClick={() => onSend(b.id)} className="h-7 px-2 text-xs">Send</Button></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

// ── Leads ──────────────────────────────────────────────────────────────
function LeadsTab({ leads }: { leads: LeadScore[] }) {
  return (
    <section className="rounded-xl border bg-card p-5">
      <h2 className="mb-3 text-lg font-medium">Lead scores</h2>
      {leads.length === 0 ? (
        <p className="py-8 text-center text-muted-foreground">
          No scored leads yet. As prospects engage with campaigns and broadcasts, AI lead scores appear here.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] text-sm">
            <thead><tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-3 font-medium">Lead</th><th className="py-2 pr-3 font-medium">Score</th><th className="py-2 pr-3 font-medium">Grade</th>
            </tr></thead>
            <tbody>
              {leads.map((l, i) => (
                <tr key={l.id ?? i} className="border-b last:border-0">
                  <td className="py-2 pr-3 font-medium">{l.name ?? l.email ?? "Lead"}</td>
                  <td className="py-2 pr-3">{l.score ?? "—"}</td>
                  <td className="py-2 pr-3">{l.grade ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  )
}
