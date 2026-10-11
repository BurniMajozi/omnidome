"use client"

/**
 * Payments gateway tab: settlement bank account setup, this month's card-processing commission
 * (tiers come from the API, nothing is hard-coded) and, for platform admins only, approval of
 * settlement account changes. The bank account number is typed once, sent once and never shown again;
 * only the last 4 digits are ever displayed.
 */

import { useCallback, useEffect, useState } from "react"
import { Landmark, Percent } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import {
  approveGatewayChange,
  getGatewaySettings,
  getGatewayLiabilities,
  getGatewaySummary,
  listGatewayBanks,
  listPendingGatewayChanges,
  previewCommission,
  rejectGatewayChange,
  saveGatewaySettings,
  useBillingTier,
  type CommissionPreview,
  type GatewayBank,
  type GatewayLiability,
  type GatewaySettings,
  type GatewaySummary,
  type PendingGatewayChange,
} from "@/lib/billing-api"
import { fmtMoney } from "@/lib/money"
import type { Loadable } from "@/lib/service-state"
import { ConfirmModal } from "./confirm-modal"
import { Field, Modal, Note, fmtDateTime, inputClass, useActionState } from "./shared"

const pct = (n: number) => `${Number.isFinite(n) ? Number(n.toFixed(2)) : 0}%`

export function GatewayTab() {
  const { isAdmin, canWrite } = useBillingTier()
  const [settings, setSettings] = useState<Loadable<GatewaySettings>>({ state: "loading" })
  const [formOpen, setFormOpen] = useState(false)
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    let off = false
    getGatewaySettings().then((l) => !off && setSettings(l))
    return () => {
      off = true
    }
  }, [tick])

  return (
    <div className="space-y-4">
      <SetupCard settings={settings} isAdmin={isAdmin} onChange={() => setFormOpen(true)} onRetry={reload} />
      <CommissionCard />
      <OwedCard />
      <PendingChanges canAct={canWrite} />
      <SettingsForm
        open={formOpen}
        onOpenChange={setFormOpen}
        current={settings.state === "ready" ? settings.data : null}
        onSaved={(s) => {
          setSettings({ state: "ready", data: s })
          reload()
        }}
      />
    </div>
  )
}

// ------------------------------------------------------------------ setup

function SetupCard({ settings, isAdmin, onChange, onRetry }: { settings: Loadable<GatewaySettings>; isAdmin: boolean; onChange: () => void; onRetry: () => void }) {
  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Landmark className="h-4 w-4" />
          Card payments setup
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {settings.state !== "ready" ? (
          <NotConnected loadable={settings} service="Billing" onRetry={onRetry} />
        ) : !settings.data.configured ? (
          <>
            <Note tone="error">Customer card payments cannot be taken until the settlement bank account is set up. Charges are refused until this is completed.</Note>
            <p className="text-sm text-muted-foreground">Card payments are paid out to this bank account after the processing commission is deducted.</p>
            <Button size="sm" disabled={!isAdmin} title={isAdmin ? undefined : "Finance admin only"} onClick={onChange}>
              Set up settlement account
            </Button>
          </>
        ) : (
          <>
            {settings.data.pending_change && (
              <Note tone="info">
                Change to account ending {settings.data.pending_change.last4} is awaiting approval; payouts continue to the current account until approved.
                {settings.data.pending_change.requested_at ? ` Requested ${fmtDateTime(settings.data.pending_change.requested_at)}.` : ""}
              </Note>
            )}
            <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
              <Item k="Business name" v={settings.data.business_name || "—"} />
              <Item k="Bank" v={settings.data.bank || "—"} />
              <Item k="Settlement account" v={settings.data.account_last4 ? `Account ending ${settings.data.account_last4}` : "—"} />
              <div>
                <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">Status</dt>
                <dd>
                  <Badge className={settings.data.status === "active" ? "badge-success" : "badge-warning"}>{settings.data.status ? settings.data.status.replace(/_/g, " ") : "Unknown"}</Badge>
                </dd>
              </div>
            </dl>
            <Button size="sm" variant="outline" disabled={!isAdmin} title={isAdmin ? undefined : "Finance admin only"} onClick={onChange}>
              Change settlement account
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function Item({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{k}</dt>
      <dd className="font-medium text-foreground">{v}</dd>
    </div>
  )
}

function SettingsForm({ open, onOpenChange, current, onSaved }: { open: boolean; onOpenChange: (o: boolean) => void; current: GatewaySettings | null; onSaved: (s: GatewaySettings) => void }) {
  const act = useActionState()
  const [banks, setBanks] = useState<Loadable<{ banks: GatewayBank[] }>>({ state: "loading" })
  const [name, setName] = useState("")
  const [bank, setBank] = useState("")
  const [account, setAccount] = useState("")
  const [saved, setSaved] = useState<GatewaySettings | null>(null)

  useEffect(() => {
    if (!open) return
    let off = false
    setBanks({ state: "loading" })
    listGatewayBanks().then((l) => !off && setBanks(l))
    setName(current?.business_name ?? "")
    setBank("")
    setAccount("")
    setSaved(null)
    act.clear()
    return () => {
      off = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const valid = name.trim().length > 0 && bank !== "" && /^\d{6,17}$/.test(account)

  const submit = async () => {
    const r = await act.run("save", () => saveGatewaySettings({ business_name: name.trim(), settlement_bank_code: bank, account_number: account }))
    // The account number is not kept in state once it has been sent.
    setAccount("")
    if (r) {
      setSaved(r)
      onSaved(r)
    }
  }

  return (
    <Modal open={open} onOpenChange={onOpenChange} title={current?.configured ? "Change settlement account" : "Set up settlement account"} description="Card payments are paid out to this bank account.">
      {saved ? (
        <div className="space-y-3">
          <Note tone="success">{saved.pending_change ? `Change to account ending ${saved.pending_change.last4} is awaiting approval; payouts continue to the current account until approved.` : "Settlement account saved."}</Note>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <Item k="Business name" v={saved.business_name || "—"} />
            <Item k="Bank" v={saved.bank || "—"} />
            <Item k="Settlement account" v={saved.account_last4 ? `Account ending ${saved.account_last4}` : "—"} />
          </dl>
          <div className="flex justify-end">
            <Button size="sm" onClick={() => onOpenChange(false)}>
              Done
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {!current?.configured && <Note tone="error">Customer card payments cannot be taken until this is completed.</Note>}
          {current?.configured && <Note tone="info">A change to the settlement account must be approved before payouts switch to it. Payouts continue to the current account until then.</Note>}
          <Field label="Business name">
            <input className={inputClass} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Bank">
            {banks.state !== "ready" ? (
              <NotConnected loadable={banks} service="Billing" className="p-3" />
            ) : (banks.data.banks ?? []).length === 0 ? (
              <NoDataYet message="No banks are available right now." className="p-3" />
            ) : (
              <select className={inputClass} value={bank} onChange={(e) => setBank(e.target.value)}>
                <option value="">Select a bank</option>
                {banks.data.banks.map((b) => (
                  <option key={b.code} value={b.code}>
                    {b.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Account number" hint="Digits only. It is sent once and only the last 4 digits are shown afterwards.">
            <input className={inputClass} inputMode="numeric" autoComplete="off" value={account} maxLength={17} onChange={(e) => setAccount(e.target.value.replace(/\D/g, ""))} />
          </Field>
          {act.msg && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="outline" disabled={!!act.busy} onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button size="sm" disabled={!valid || !!act.busy} onClick={submit}>
              {act.busy ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

// ------------------------------------------------------------------ commission

function CommissionCard() {
  const [summary, setSummary] = useState<Loadable<GatewaySummary>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((t) => t + 1), [])
  useEffect(() => {
    let off = false
    setSummary({ state: "loading" })
    getGatewaySummary().then((l) => !off && setSummary(l))
    return () => {
      off = true
    }
  }, [tick])

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Percent className="h-4 w-4" />
          Card processing commission
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {summary.state !== "ready" ? <NotConnected loadable={summary} service="Billing" onRetry={reload} /> : <SummaryBody s={summary.data} />}
        <FeeCalculator />
      </CardContent>
    </Card>
  )
}

function SummaryBody({ s }: { s: GatewaySummary }) {
  const tiers = s.tiers ?? []
  const next = s.next_threshold_zar
  // Progress towards the threshold that ends the current band.
  const progress = next && next > 0 ? Math.min(100, Math.max(0, (s.volume_zar / next) * 100)) : 100
  return (
    <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile k={`Processed (${s.period})`} v={fmtMoney(s.volume_zar)} />
        <Tile k="Card payments" v={String(s.charges)} />
        <Tile k="Commission this month (excl. VAT)" v={fmtMoney(s.commission_zar)} />
        <Tile k="Current rate" v={pct(s.current_rate_percent)} />
      </div>
      <div className="space-y-1">
        <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
          <div className="h-full rounded-full bg-primary" style={{ width: `${progress}%` }} />
        </div>
        <p className="text-xs text-muted-foreground">
          {next !== null && next !== undefined
            ? `${fmtMoney(s.remaining_in_band_zar ?? Math.max(0, next - s.volume_zar))} more at this rate before the next band at ${fmtMoney(next)}.`
            : "You are on the lowest rate band."}
        </p>
      </div>
      <p className="text-xs text-muted-foreground">VAT (15%) is added to OmniDome&apos;s fees.</p>
      {tiers.length === 0 ? (
        <NoDataYet message="No commission bands are configured." />
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Monthly volume</th>
                <th className="px-3 py-2 text-right">Rate (excl. VAT)</th>
              </tr>
            </thead>
            <tbody>
              {tiers.map((t, i) => {
                const active = s.volume_zar >= t.from_zar && (t.to_zar === null || s.volume_zar < t.to_zar)
                return (
                  <tr key={i} className={`border-t border-border ${active ? "bg-primary/10" : ""}`}>
                    <td className="px-3 py-2">
                      {t.to_zar === null ? `Above ${fmtMoney(t.from_zar)}` : `${fmtMoney(t.from_zar)} to ${fmtMoney(t.to_zar)}`}
                      {active && <span className="ml-2 text-xs text-muted-foreground">(current)</span>}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{pct(t.rate_percent)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function Tile({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-md border border-border bg-secondary/20 p-2.5">
      <p className="text-[11px] text-muted-foreground">{k}</p>
      <p className="text-lg font-semibold tabular-nums text-foreground">{v}</p>
    </div>
  )
}

function FeeCalculator() {
  const [amount, setAmount] = useState("")
  const [result, setResult] = useState<Loadable<CommissionPreview> | null>(null)
  const n = Number(amount)
  const valid = amount.trim() !== "" && Number.isFinite(n) && n > 0

  const calc = async () => {
    if (!valid) return
    setResult({ state: "loading" })
    setResult(await previewCommission(n))
  }

  return (
    <div className="space-y-2 border-t border-border pt-4">
      <h4 className="text-sm font-semibold text-foreground">Fee calculator</h4>
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Payment amount (ZAR)" className="w-48">
          <input className={inputClass} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void calc()} />
        </Field>
        <Button size="sm" variant="outline" disabled={!valid || result?.state === "loading"} onClick={calc}>
          Calculate
        </Button>
      </div>
      {result?.state === "loading" && <p className="text-xs text-muted-foreground">Calculating…</p>}
      {result && result.state !== "loading" && result.state !== "ready" && <NotConnected loadable={result} service="Billing" className="p-3" />}
      {result?.state === "ready" && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
          <Tile k="OmniDome fee (excl. VAT)" v={fmtMoney(result.data.commission_zar)} />
          <Tile k="VAT 15%" v={fmtMoney(result.data.commission_vat_zar ?? 0)} />
          <Tile k="Total fee" v={fmtMoney(result.data.commission_total_zar ?? result.data.commission_zar)} />
          <Tile k="You receive" v={fmtMoney(result.data.tenant_receives_zar)} />
          <Tile k="Effective rate" v={pct(result.data.effective_rate_percent)} />
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ platform admin approvals

/** Rendered only for platform admins: the API answers 403 for everyone else, which hides the section. */
function PendingChanges({ canAct }: { canAct: boolean }) {
  const [data, setData] = useState<Loadable<{ changes: PendingGatewayChange[] }>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const [target, setTarget] = useState<{ change: PendingGatewayChange; kind: "approve" | "reject" } | null>(null)
  const act = useActionState()

  useEffect(() => {
    let off = false
    listPendingGatewayChanges().then((l) => !off && setData(l))
    return () => {
      off = true
    }
  }, [tick])

  // Not a platform admin (403) or the list is unavailable: show nothing rather than a broken state.
  if (data.state !== "ready") return null

  const confirm = async () => {
    if (!target) return
    const { change, kind } = target
    const r = await act.run(kind, () => (kind === "approve" ? approveGatewayChange(change.tenant_id) : rejectGatewayChange(change.tenant_id)))
    if (r !== undefined) {
      setTarget(null)
      setTick((t) => t + 1)
    }
  }

  const changes = data.data.changes ?? []
  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="text-base">Settlement account changes awaiting approval</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {changes.length === 0 ? (
          <NoDataYet message="No settlement account changes are waiting for approval." />
        ) : (
          <ul className="divide-y divide-border rounded-md border border-border">
            {changes.map((c) => (
              <li key={c.tenant_id} className="flex flex-col gap-2 px-3 py-2.5 text-sm md:flex-row md:items-center md:justify-between">
                <div className="min-w-0 space-y-0.5">
                  <p className="font-medium text-foreground">{c.business_name}</p>
                  <p className="text-xs text-muted-foreground">
                    From {c.current.bank} ending {c.current.last4} to {c.requested.bank} ending {c.requested.last4}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Requested by {c.requested_by} on {fmtDateTime(c.requested_at)}
                  </p>
                </div>
                <div className="flex gap-1.5">
                  <Button size="sm" disabled={!canAct} onClick={() => { act.clear(); setTarget({ change: c, kind: "approve" }) }}>
                    Approve
                  </Button>
                  <Button size="sm" variant="outline" disabled={!canAct} onClick={() => { act.clear(); setTarget({ change: c, kind: "reject" }) }}>
                    Reject
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
      <ConfirmModal
        open={!!target}
        onOpenChange={(o) => !o && setTarget(null)}
        title={target?.kind === "approve" ? "Approve settlement account change" : "Reject settlement account change"}
        confirmLabel={target?.kind === "approve" ? "Approve change" : "Reject change"}
        destructive={target?.kind === "reject"}
        busy={!!act.busy}
        error={act.msg?.tone === "error" ? act.msg.text : null}
        onConfirm={confirm}
      >
        {target && (
          <>
            <p>
              {target.change.business_name}: current account ending <strong className="text-foreground">{target.change.current.last4}</strong>, requested account ending{" "}
              <strong className="text-foreground">{target.change.requested.last4}</strong> ({target.change.requested.bank}).
            </p>
            <p>{target.kind === "approve" ? "Approving moves all future payouts to the requested account." : "Rejecting keeps payouts going to the current account."}</p>
          </>
        )}
      </ConfirmModal>
    </Card>
  )
}

// ------------------------------------------------------------------ owed to OmniDome

const LIABILITY_KIND: Record<GatewayLiability["kind"], string> = { refund: "Refund", chargeback: "Lost dispute" }
const LIABILITY_STATUS: Record<GatewayLiability["status"], { label: string; tone: string }> = {
  open: { label: "Open", tone: "badge-warning" },
  recovered: { label: "Recovered", tone: "badge-success" },
  written_off: { label: "Written off", tone: "bg-secondary text-muted-foreground" },
}

/** Amounts paid out of OmniDome's balance for payments already settled to the tenant. Hidden when there is nothing to show. */
function OwedCard() {
  const [data, setData] = useState<Loadable<{ owed_zar: number; items: GatewayLiability[] }>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let off = false
    getGatewayLiabilities().then((l) => !off && setData(l))
    return () => {
      off = true
    }
  }, [tick])

  if (data.state === "loading") return null
  if (data.state === "denied") return null
  if (data.state !== "ready") return <NotConnected loadable={data} service="Billing" onRetry={() => setTick((t) => t + 1)} />
  const items = data.data.items ?? []
  if (!data.data.owed_zar && items.length === 0) return null

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="text-base">Owed to OmniDome</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-3xl font-bold tabular-nums text-foreground">{fmtMoney(data.data.owed_zar)}</p>
        <p className="text-xs text-muted-foreground">
          When a refund or lost dispute is paid out of OmniDome&apos;s balance for a payment you have already been settled for, the amount is owed back and is deducted from your future top-ups and funding.
        </p>
        {items.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Note</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2 text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {items.map((i) => {
                  const st = LIABILITY_STATUS[i.status] ?? { label: i.status, tone: "bg-secondary text-muted-foreground" }
                  return (
                    <tr key={i.id} className="border-t border-border">
                      <td className="px-3 py-2">{fmtDateTime(i.created_at)}</td>
                      <td className="px-3 py-2">{LIABILITY_KIND[i.kind] ?? i.kind}</td>
                      <td className="px-3 py-2 text-muted-foreground">{i.note || "—"}</td>
                      <td className="px-3 py-2">
                        <Badge className={st.tone}>{st.label}</Badge>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(i.amount_zar)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
