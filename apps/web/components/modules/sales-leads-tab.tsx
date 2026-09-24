"use client"

/**
 * Sales → Lead Stage Management (SPEC-lead-lifecycle.md).
 *
 * One stage model with the Pipeline Board: before a lead has a deal its own
 * status is the stage (New / Contacted / Qualified / Disqualified); once it has
 * a deal, the board stage is the truth and changing it here moves the card on
 * the board (and vice versa).
 */
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { ChevronRight, Filter, Layers, Loader2, Mail, Phone, Plus, RefreshCw, User, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  LEAD_PHASE_STAGES,
  LEAD_STATUS_LABELS,
  SALES_CHANNELS,
  salesApi,
  salesErrorMessage,
  type PipelineStage,
  type SalesLead,
} from "@/lib/sales-api"

export const SALES_CHANGED_EVENT = "omnidome:sales-changed"

/** Tell other Sales views (board, lead table) that leads/deals changed. */
export function announceSalesChange() {
  window.dispatchEvent(new CustomEvent(SALES_CHANGED_EVENT))
}

const CLOSED_WON = "Closed Won"
const CLOSED_LOST = "Closed Lost"

const STAGE_TONE: Record<string, string> = {
  NEW: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  CONTACTED: "bg-cyan-500/15 text-cyan-400 border-cyan-500/30",
  QUALIFIED: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  DISQUALIFIED: "bg-red-500/15 text-red-400 border-red-500/30",
  [CLOSED_WON]: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  [CLOSED_LOST]: "bg-red-500/15 text-red-400 border-red-500/30",
}
const PIPELINE_TONE = "bg-purple-500/15 text-purple-300 border-purple-500/30"

const PRIORITY_TONE: Record<string, string> = {
  urgent: "bg-red-500/20 text-red-400 border-red-500/40",
  high: "bg-orange-500/20 text-orange-400 border-orange-500/40",
}

const zar = (n: number) =>
  new Intl.NumberFormat("en-ZA", { style: "currency", currency: "ZAR", maximumFractionDigits: 0 }).format(n)

export function formatDate(iso?: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" })
}

export function formatDateTime(iso?: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString("en-ZA", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  })
}

/** Current stage value for the grouped select. */
function stageValue(lead: SalesLead): string {
  return lead.deal_id && lead.deal_stage ? `stage:${lead.deal_stage}` : `status:${lead.status}`
}

export function stageLabel(lead: SalesLead): string {
  if (lead.deal_id && lead.deal_stage) return lead.deal_stage
  return LEAD_STATUS_LABELS[lead.status] ?? lead.status
}

export function stageTone(lead: SalesLead): string {
  if (lead.deal_id && lead.deal_stage) return STAGE_TONE[lead.deal_stage] ?? PIPELINE_TONE
  return STAGE_TONE[lead.status] ?? "bg-muted text-muted-foreground border-border"
}

// ── Stage change dialog (deal value / lost reason / confirm won) ────────────

type PendingChange = {
  lead: SalesLead
  kind: "status" | "stage"
  target: string
  needs: "value" | "reason" | "reason-optional" | "confirm-won"
}

function StageChangeDialog({
  change,
  onCancel,
  onDone,
}: {
  change: PendingChange
  onCancel: () => void
  onDone: (lead: SalesLead) => void
}) {
  const { lead, kind, target, needs } = change
  const name = `${lead.first_name} ${lead.last_name}`.trim()
  const [value, setValue] = useState("0")
  const [dealName, setDealName] = useState(`${name} - ${lead.source?.replace(/_/g, " ") ?? "Lead"}`)
  const [reason, setReason] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reasonRequired = needs === "reason"
  const canSave = !saving && (!reasonRequired || reason.trim().length >= 3) && (needs !== "value" || Number(value) >= 0)

  const submit = async () => {
    setSaving(true)
    setError(null)
    try {
      const updated = await salesApi.changeLeadStage(lead.id, {
        ...(kind === "status" ? { status: target } : { stage_name: target }),
        ...(needs === "value" ? { value_zar: Number(value) || 0, deal_name: dealName.trim() || undefined } : {}),
        ...(reason.trim() ? { reason: reason.trim() } : {}),
      })
      onDone(updated)
    } catch (err) {
      setError(salesErrorMessage(err, "Could not change the stage"))
      setSaving(false)
    }
  }

  const title =
    needs === "value" ? `Add ${name} to the pipeline board`
      : needs === "confirm-won" ? `Close ${name} as won`
        : target === CLOSED_LOST ? `Close ${name} as lost`
          : `Disqualify ${name}`

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" role="dialog" aria-modal="true" aria-label={title}>
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-5 shadow-2xl space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-foreground">{title}</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {needs === "value" && `A deal is created in "${target}". From then on this lead and its board card move together.`}
              {needs === "confirm-won" && "Runs the won process: commission, finance entry and customer lifecycle."}
              {needs === "reason" && "The deal and the lead are closed. A reason is required."}
              {needs === "reason-optional" && "The lead is closed without a deal. You can reopen it later."}
            </p>
          </div>
          <button type="button" onClick={onCancel} className="rounded p-1 text-muted-foreground hover:bg-muted" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>

        {needs === "value" && (
          <div className="grid gap-3">
            <label className="grid gap-1 text-xs font-medium text-foreground">
              Deal name
              <input value={dealName} onChange={(e) => setDealName(e.target.value)}
                className="h-9 rounded-md border border-border bg-background px-2.5 text-sm" />
            </label>
            <label className="grid gap-1 text-xs font-medium text-foreground">
              Estimated value (ZAR)
              <input type="number" min={0} step={100} value={value} onChange={(e) => setValue(e.target.value)}
                className="h-9 rounded-md border border-border bg-background px-2.5 text-sm" />
              <span className="font-normal text-muted-foreground">You can change it later on the deal.</span>
            </label>
          </div>
        )}
        {(needs === "reason" || needs === "reason-optional") && (
          <label className="grid gap-1 text-xs font-medium text-foreground">
            Reason{reasonRequired ? "" : " (optional)"}
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} autoFocus
              placeholder={reasonRequired ? "e.g. Went with a competitor" : "e.g. Outside coverage area"}
              className="rounded-md border border-border bg-background px-2.5 py-2 text-sm" />
          </label>
        )}

        {error && <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onCancel} disabled={saving}>Cancel</Button>
          <Button size="sm" onClick={() => void submit()} disabled={!canSave}>
            {saving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            {needs === "value" ? "Add to pipeline" : needs === "confirm-won" ? "Close as won" : "Confirm"}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── Tab ─────────────────────────────────────────────────────────────────────

export function SalesLeadsTab({
  leads,
  loading,
  onReload,
  onLeadUpdated,
  renderActions,
  onOpenLead,
}: {
  leads: SalesLead[]
  loading: boolean
  onReload: () => void
  onLeadUpdated: (lead: SalesLead) => void
  /** Row action menu (lead-actions). */
  renderActions?: (lead: SalesLead) => ReactNode
  onOpenLead?: (lead: SalesLead) => void
}) {
  const [stages, setStages] = useState<PipelineStage[]>([])
  const [channel, setChannel] = useState("ALL")
  const [pending, setPending] = useState<PendingChange | null>(null)
  const [rowError, setRowError] = useState<{ id: string; message: string } | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    salesApi.getPipelineStages()
      .then((s) => { if (!cancelled) setStages([...s].sort((a, b) => a.sort_order - b.sort_order)) })
      .catch(() => undefined)
    return () => { cancelled = true }
  }, [])

  const filtered = useMemo(
    () => (channel === "ALL" ? leads : leads.filter((l) => l.source === channel)),
    [leads, channel],
  )

  const counts = useMemo(() => {
    const c = { lead: 0, pipeline: 0, closed: 0 }
    for (const l of leads) {
      if (l.closed_at) c.closed++
      else if (l.deal_id) c.pipeline++
      else c.lead++
    }
    return c
  }, [leads])

  const finish = (updated: SalesLead) => {
    onLeadUpdated(updated)
    announceSalesChange()
    setPending(null)
  }

  const onStageSelect = async (lead: SalesLead, value: string) => {
    const cut = value.indexOf(":")
    const kind = value.slice(0, cut) as "status" | "stage"
    const target = value.slice(cut + 1)
    setRowError(null)
    if (kind === "status" && target === "DISQUALIFIED") return setPending({ lead, kind, target, needs: "reason-optional" })
    if (kind === "stage" && target === CLOSED_LOST) return setPending({ lead, kind, target, needs: "reason" })
    if (kind === "stage" && target === CLOSED_WON) return setPending({ lead, kind, target, needs: "confirm-won" })
    if (kind === "stage" && !lead.deal_id) return setPending({ lead, kind, target, needs: "value" })
    setBusyId(lead.id)
    try {
      const updated = await salesApi.changeLeadStage(lead.id, kind === "status" ? { status: target } : { stage_name: target })
      onLeadUpdated(updated)
      announceSalesChange()
    } catch (err) {
      setRowError({ id: lead.id, message: salesErrorMessage(err, "Could not change the stage") })
    } finally {
      setBusyId(null)
    }
  }

  const leadPhase = LEAD_PHASE_STAGES.filter((s) => s.id !== "DISQUALIFIED")

  return (
    <div className="surface-card p-5 space-y-5">
      {/* Journey: lead phase → pipeline board */}
      <div className="rounded-xl border border-border bg-card/60 p-4 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Layers className="h-4 w-4 text-primary" />
            Lead journey
          </span>
          <span className="text-[11px] text-muted-foreground">
            {counts.lead} in lead phase · {counts.pipeline} on the pipeline board · {counts.closed} closed
          </span>
        </div>
        <div className="flex items-center gap-1 overflow-x-auto py-2 text-[11px]">
          <span className="mr-1 shrink-0 text-muted-foreground">Lead</span>
          {leadPhase.map((st) => (
            <span key={st.id} className="flex items-center gap-1 shrink-0">
              <span className={`px-2 py-0.5 rounded-md border font-semibold ${STAGE_TONE[st.id]}`}>{st.label}</span>
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50" />
            </span>
          ))}
          <span className="mx-1 shrink-0 text-muted-foreground">Pipeline board</span>
          {stages.map((st, i) => (
            <span key={st.id} className="flex items-center gap-1 shrink-0">
              <span className={`px-2 py-0.5 rounded-md border font-semibold ${STAGE_TONE[st.name] ?? PIPELINE_TONE}`}>{st.name}</span>
              {i < stages.length - 1 && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50" />}
            </span>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">
          Choosing a board stage puts the lead on the Pipeline Board. From then on the board and this table move together.
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-bold text-foreground">Customer Leads & Acquisition Channels</h3>
          <p className="text-xs text-muted-foreground">
            Reference, owner and dates for every lead. Change the stage here or on the board.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground font-medium flex items-center gap-1">
            <Filter className="h-3 w-3" /> Channel:
          </span>
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            className="h-8 rounded-lg border border-border bg-background px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="ALL">All acquisition channels</option>
            {SALES_CHANNELS.map((ch) => (
              <option key={ch.id} value={ch.id}>{ch.label}</option>
            ))}
          </select>
          <Button variant="ghost" size="sm" onClick={onReload} className="h-8 text-xs text-muted-foreground hover:text-foreground">
            <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </div>
      </div>

      <div className="rounded-xl border border-border overflow-hidden bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-border bg-muted/40 font-medium text-muted-foreground">
              <tr>
                <th className="py-2.5 px-3.5">Lead</th>
                <th className="py-2.5 px-3.5">Channel</th>
                <th className="py-2.5 px-3.5">Owner</th>
                <th className="py-2.5 px-3.5">Stage</th>
                <th className="py-2.5 px-3.5 whitespace-nowrap">Created · Modified · Closed</th>
                <th className="py-2.5 px-3.5">Notes</th>
                <th className="py-2.5 px-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {loading && leads.length === 0 ? (
                <tr><td colSpan={7} className="py-8 text-center text-muted-foreground">
                  <Loader2 className="mx-auto h-4 w-4 animate-spin" />
                </td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={7} className="py-8 text-center text-muted-foreground">
                  No leads for this channel yet. Use + Create Deal / Lead, or add companies and tenders from Lead sources.
                </td></tr>
              ) : filtered.map((lead) => {
                const ch = SALES_CHANNELS.find((c) => c.id === lead.source) ?? { label: lead.source?.replace(/_/g, " "), color: "#9ca3af" }
                const dealClosed = lead.deal_status === "WON" || lead.deal_status === "LOST"
                return (
                  <tr key={lead.id} className="hover:bg-muted/30 transition-colors align-top">
                    <td className="py-3 px-3.5 min-w-[220px]">
                      <div className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground">
                        {lead.reference ?? "—"}
                        {lead.priority && PRIORITY_TONE[lead.priority] && (
                          <span className={`rounded border px-1 py-px font-sans font-semibold uppercase ${PRIORITY_TONE[lead.priority]}`}>
                            {lead.priority}
                          </span>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => onOpenLead?.(lead)}
                        className="mt-0.5 flex items-center gap-1.5 text-left font-semibold text-foreground hover:text-primary"
                      >
                        <User className="h-3.5 w-3.5 text-primary shrink-0" />
                        {`${lead.first_name} ${lead.last_name}`.trim()}
                      </button>
                      <div className="text-[11px] text-muted-foreground flex flex-wrap items-center gap-x-2 mt-0.5">
                        {lead.email && <span className="flex items-center gap-1"><Mail className="h-2.5 w-2.5" />{lead.email}</span>}
                        {lead.phone && <span className="flex items-center gap-1"><Phone className="h-2.5 w-2.5" />{lead.phone}</span>}
                      </div>
                      {lead.address && <div className="text-[10px] text-muted-foreground/70 truncate max-w-xs mt-0.5">{lead.address}</div>}
                    </td>
                    <td className="py-3 px-3.5">
                      <span
                        className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-medium border"
                        style={{ borderColor: `${ch.color}40`, backgroundColor: `${ch.color}15`, color: ch.color }}
                      >
                        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: ch.color }} />
                        {ch.label}
                      </span>
                      <div className="mt-1 font-mono text-amber-400 text-[11px]">{"★".repeat(lead.interest_level || 3)}</div>
                    </td>
                    <td className="py-3 px-3.5 whitespace-nowrap">
                      {lead.owner_name ? <span className="text-foreground">{lead.owner_name}</span> : <span className="text-muted-foreground">Unassigned</span>}
                    </td>
                    <td className="py-3 px-3.5 min-w-[170px]">
                      <div className="flex items-center gap-1.5">
                        <select
                          value={stageValue(lead)}
                          disabled={busyId === lead.id || dealClosed}
                          onChange={(e) => void onStageSelect(lead, e.target.value)}
                          aria-label={`Stage for ${lead.first_name}`}
                          className={`h-7 max-w-[160px] rounded-md border px-2 text-xs font-semibold focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-70 ${stageTone(lead)}`}
                        >
                          <optgroup label="Lead">
                            {LEAD_PHASE_STAGES.map((st) => (
                              <option key={st.id} value={`status:${st.id}`} disabled={!!lead.deal_id}>{st.label}</option>
                            ))}
                          </optgroup>
                          <optgroup label="Pipeline board">
                            {stages.map((st) => (
                              <option key={st.id} value={`stage:${st.name}`}>{st.name}</option>
                            ))}
                          </optgroup>
                          {/* A status that is not in either list (e.g. CONVERTED without a known stage) */}
                          {!lead.deal_id && !LEAD_PHASE_STAGES.some((s) => s.id === lead.status) && (
                            <option value={`status:${lead.status}`}>{LEAD_STATUS_LABELS[lead.status] ?? lead.status}</option>
                          )}
                        </select>
                        {busyId === lead.id && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
                      </div>
                      {lead.deal_id && (
                        <div className="mt-1 text-[10px] text-muted-foreground">
                          On the board{lead.deal_value_zar ? ` · ${zar(Number(lead.deal_value_zar))}` : ""}
                        </div>
                      )}
                      {rowError?.id === lead.id && <div className="mt-1 max-w-[200px] text-[10px] text-red-400">{rowError.message}</div>}
                    </td>
                    <td className="py-3 px-3.5 whitespace-nowrap text-[11px] leading-5">
                      <div><span className="text-muted-foreground">Created </span>{formatDate(lead.created_at)}</div>
                      <div title={formatDateTime(lead.updated_at)}><span className="text-muted-foreground">Modified </span>{formatDate(lead.updated_at)}</div>
                      <div><span className="text-muted-foreground">Closed </span>{formatDate(lead.closed_at)}</div>
                    </td>
                    <td className="py-3 px-3.5 max-w-[220px] text-muted-foreground">
                      <div className="line-clamp-2">{lead.close_reason ? `Closed: ${lead.close_reason}` : lead.notes || "—"}</div>
                    </td>
                    <td className="py-3 px-3.5 text-right whitespace-nowrap">
                      {renderActions ? renderActions(lead) : !lead.deal_id && !lead.closed_at ? (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs gap-1 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10"
                          onClick={() => setPending({ lead, kind: "stage", target: stages[0]?.name ?? "Prospecting", needs: "value" })}
                        >
                          <Plus className="h-3 w-3" /> Add to pipeline
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {pending && <StageChangeDialog change={pending} onCancel={() => setPending(null)} onDone={finish} />}
    </div>
  )
}
