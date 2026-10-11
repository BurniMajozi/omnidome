"use client"

/**
 * Platform-admin reconciliation: does the Paystack balance cover what tenants' payout wallets hold, did every
 * charge settle as instructed, and does the Paystack ledger add up. Read-only against Paystack. The overview
 * answers 403 for anyone else, in which case nothing is rendered.
 */

import { useCallback, useEffect, useState } from "react"
import { RefreshCcw } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import {
  generateFeeInvoices,
  getReconLedger,
  listFeeInvoices,
  type FeeInvoice,
  getReconOverview,
  listReconMismatches,
  listReconSettlements,
  listReconSnapshots,
  runRecon,
  type ReconLedger,
  type ReconMismatch,
  type ReconOverview,
  type ReconRunResult,
  type ReconSettlement,
  type ReconSnapshot,
} from "@/lib/billing-api"
import { fmtMoney } from "@/lib/money"
import type { Loadable } from "@/lib/service-state"
import { ConfirmModal } from "./confirm-modal"
import { periodLabel, showFeeInvoice } from "./statement-tab"
import { Field, Note, fmtDateTime, humanise, inputClass, useActionState } from "./shared"

const CATEGORIES = ["payout", "payout_reversal", "charge", "refund", "dispute", "settlement", "fee", "topup", "other"]

export function ReconciliationTab() {
  const [overview, setOverview] = useState<Loadable<ReconOverview>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((t) => t + 1), [])
  useEffect(() => {
    let off = false
    getReconOverview().then((l) => !off && setOverview(l))
    return () => {
      off = true
    }
  }, [tick])

  if (overview.state === "denied") return <p className="text-sm text-muted-foreground">Platform admins only.</p>
  if (overview.state !== "ready") return <NotConnected loadable={overview} service="Billing" onRetry={reload} />

  return (
    <div className="space-y-4">
      <OverviewCards o={overview.data} onRan={reload} />
      <Mismatches />
      <LedgerCard />
      <Settlements />
      <Snapshots />
      <FeeTaxInvoices />
    </div>
  )
}

// ------------------------------------------------------------------ overview

function OverviewCards({ o, onRan }: { o: ReconOverview; onRan: () => void }) {
  const snap = o.snapshot
  const unverified = (o.charges_last_30d?.unverified ?? 0) + (o.charges_last_30d?.no_split_data ?? 0)
  return (
    <div className="space-y-3">
      {snap ? (
        snap.status === "ok" ? (
          <Note tone="success">Paystack balance covers all payout wallets (headroom {fmtMoney(snap.headroom_zar)}).</Note>
        ) : (
          <Note tone="error">
            <span className="font-medium">Paystack balance is {fmtMoney(Math.abs(snap.headroom_zar))} BELOW what tenants&apos; payout wallets hold: top up Paystack before payroll or supplier payments run.</span>
          </Note>
        )
      ) : (
        <Note tone="info">No balance check has been taken yet. Run reconciliation to take one.</Note>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile k="Paystack balance" v={snap ? fmtMoney(snap.balance_zar) : "—"} sub={snap ? `at ${fmtDateTime(snap.taken_at)}` : undefined} />
        <Tile k="Held in tenant wallets" v={fmtMoney(o.wallets_now_zar)} />
        <Tile k="Open refund/chargeback liabilities" v={fmtMoney(o.liabilities_open_zar)} />
        <Tile k="Unverified charges (30 days)" v={String(unverified)} sub={`${o.charges_last_30d?.ok ?? 0} verified`} />
        <Tile k="Open mismatches" v={String(o.open_mismatches)} bad={o.open_mismatches > 0} />
        <Tile k="Payouts in flight" v={String(o.payouts_in_flight)} />
        <Tile k="Ledger gaps" v={String(o.ledger_breaks)} bad={o.ledger_breaks > 0} />
        <Tile k="Last run" v={o.last_run ? fmtDateTime(o.last_run.at) : "Never"} sub={o.last_run?.error ? `Error: ${o.last_run.error}` : o.last_run && !o.last_run.finished ? "Did not finish" : undefined} bad={!!o.last_run?.error} />
      </div>
      <RunCard onRan={onRan} />
    </div>
  )
}

function Tile({ k, v, sub, bad }: { k: string; v: string; sub?: string; bad?: boolean }) {
  return (
    <div className={`rounded-md border p-2.5 ${bad ? "border-red-500/40 bg-red-500/10" : "border-border bg-secondary/20"}`}>
      <p className="text-[11px] text-muted-foreground">{k}</p>
      <p className={`text-lg font-semibold tabular-nums ${bad ? "text-red-300" : "text-foreground"}`}>{v}</p>
      {sub && <p className="text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  )
}

function RunCard({ onRan }: { onRan: () => void }) {
  const [confirming, setConfirming] = useState(false)
  const [result, setResult] = useState<ReconRunResult | null>(null)
  const act = useActionState()

  const run = async () => {
    const r = await act.run("run", () => runRecon())
    if (r) {
      setResult(r)
      setConfirming(false)
      onRan()
    }
  }

  return (
    <Card className="border-border bg-card">
      <CardContent className="space-y-3 pt-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">Reads balances, ledger, charges, payouts and settlements from Paystack and compares them with OmniDome&apos;s records.</p>
          <Button size="sm" onClick={() => { act.clear(); setConfirming(true) }}>
            Run reconciliation now
          </Button>
        </div>
        {result &&
          (result.skipped ? (
            <Note tone="info">Skipped: {result.skipped}</Note>
          ) : (
            <dl className="grid gap-2 text-xs sm:grid-cols-2">
              {(["snapshot", "ledger", "charges", "payouts", "settlements", "ledger_breaks"] as const).map((k) => (
                <div key={k} className="rounded-md border border-border bg-secondary/20 p-2">
                  <dt className="text-muted-foreground">{humanise(k)}</dt>
                  <dd className="break-words font-mono text-foreground">{summarise(result[k])}</dd>
                </div>
              ))}
            </dl>
          ))}
      </CardContent>
      <ConfirmModal open={confirming} onOpenChange={setConfirming} title="Run reconciliation" confirmLabel="Run now" busy={act.busy === "run"} error={act.msg?.tone === "error" ? act.msg.text : null} onConfirm={run}>
        <p>This only reads from Paystack and records the findings. It does not move any money. It can take a minute.</p>
      </ConfirmModal>
    </Card>
  )
}

function summarise(v: unknown): string {
  if (v === undefined || v === null) return "—"
  if (typeof v === "object") return JSON.stringify(v)
  return String(v)
}

// ------------------------------------------------------------------ mismatches

function useLoad<T>(fetcher: () => Promise<Loadable<T>>, deps: unknown[]) {
  const [data, setData] = useState<Loadable<T>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let off = false
    setData({ state: "loading" })
    fetcher().then((l) => !off && setData(l))
    return () => {
      off = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return { data, reload: () => setTick((t) => t + 1) }
}

function Section({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">{title}</CardTitle>
          {right}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">{children}</CardContent>
    </Card>
  )
}

const TH = "px-3 py-2"

function Mismatches() {
  const { data, reload } = useLoad<{ mismatches: ReconMismatch[] }>(listReconMismatches, [])
  return (
    <Section title="Charges that did not settle as instructed">
      {data.state !== "ready" ? (
        <NotConnected loadable={data} service="Billing" onRetry={reload} />
      ) : (data.data.mismatches ?? []).length === 0 ? (
        <NoDataYet message="Every verified charge settled as instructed." />
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className={TH}>Checked</th>
                <th className={TH}>Reference</th>
                <th className={TH}>Tenant</th>
                <th className={`${TH} text-right`}>Gross</th>
                <th className={`${TH} text-right`}>Fee</th>
                <th className={`${TH} text-right`}>Tenant received</th>
                <th className={TH}>Note</th>
              </tr>
            </thead>
            <tbody>
              {data.data.mismatches.map((m) => (
                <tr key={m.reference} className="border-t border-border">
                  <td className={TH}>{fmtDateTime(m.checked_at)}</td>
                  <td className={`${TH} font-mono text-xs`}>{m.reference}</td>
                  <td className={`${TH} font-mono text-xs`}>{m.tenant_id.slice(0, 8)}</td>
                  <td className={`${TH} text-right tabular-nums`}>{fmtMoney(m.gross_zar)}</td>
                  <td className={`${TH} text-right tabular-nums`}>{fmtMoney(m.commission_zar)}</td>
                  <td className={`${TH} text-right tabular-nums`}>{m.actual_tenant_zar === null || m.actual_tenant_zar === undefined ? "—" : fmtMoney(m.actual_tenant_zar)}</td>
                  <td className={`${TH} text-muted-foreground`}>{m.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  )
}

// ------------------------------------------------------------------ ledger

function LedgerCard() {
  const [category, setCategory] = useState("")
  const { data, reload } = useLoad<ReconLedger>(() => getReconLedger(category, 100), [category])
  return (
    <Section
      title="Paystack ledger"
      right={
        <Field label="Category" className="w-44">
          <select className={inputClass} value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {humanise(c)}
              </option>
            ))}
          </select>
        </Field>
      }
    >
      {data.state !== "ready" ? (
        <NotConnected loadable={data} service="Billing" onRetry={reload} />
      ) : (
        <>
          {(data.data.breaks ?? []).length > 0 && (
            <div role="alert" className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
              <p className="font-medium">The ledger does not add up in {data.data.breaks.length} place{data.data.breaks.length === 1 ? "" : "s"}.</p>
              <ul className="space-y-0.5">
                {data.data.breaks.map((b, i) => (
                  <li key={i}>
                    Between entries {String(b.after_paystack_id)} and {String(b.paystack_id)}: expected balance {fmtMoney(b.expected_balance_zar)}, actual {fmtMoney(b.actual_balance_zar)}
                    {b.reason ? ` (${b.reason})` : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {(data.data.totals_by_category ?? []).length > 0 && (
            <div className="flex flex-wrap gap-2">
              {data.data.totals_by_category.map((t) => (
                <Badge key={t.category} className="bg-secondary text-muted-foreground">
                  {humanise(t.category)}: {fmtMoney(t.net_zar)} ({t.entries})
                </Badge>
              ))}
            </div>
          )}
          {(data.data.entries ?? []).length === 0 ? (
            <NoDataYet message="No ledger entries." />
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-sm">
                <thead className="bg-secondary/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className={TH}>Date</th>
                    <th className={TH}>Category</th>
                    <th className={TH}>Reason</th>
                    <th className={`${TH} text-right`}>Change</th>
                    <th className={`${TH} text-right`}>Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {data.data.entries.map((e) => (
                    <tr key={String(e.paystack_id)} className="border-t border-border">
                      <td className={TH}>{fmtDateTime(e.occurred_at)}</td>
                      <td className={TH}>{humanise(e.category)}</td>
                      <td className={`${TH} text-muted-foreground`}>{e.reason || "—"}</td>
                      <td className={`${TH} text-right tabular-nums ${e.difference_zar >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {e.difference_zar >= 0 ? "+" : "-"}
                        {fmtMoney(Math.abs(e.difference_zar))}
                      </td>
                      <td className={`${TH} text-right tabular-nums`}>{fmtMoney(e.balance_zar)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Section>
  )
}

// ------------------------------------------------------------------ settlements + snapshots

function Settlements() {
  const { data, reload } = useLoad<{ settlements: ReconSettlement[] }>(listReconSettlements, [])
  return (
    <Section title="Settlements to OmniDome">
      {data.state !== "ready" ? (
        <NotConnected loadable={data} service="Billing" onRetry={reload} />
      ) : (data.data.settlements ?? []).length === 0 ? (
        <NoDataYet message="No settlements recorded yet." />
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className={TH}>Settled on</th>
                <th className={TH}>Status</th>
                <th className={`${TH} text-right`}>Total</th>
                <th className={`${TH} text-right`}>Fees</th>
                <th className={`${TH} text-right`}>Paid</th>
              </tr>
            </thead>
            <tbody>
              {data.data.settlements.map((s) => (
                <tr key={String(s.paystack_id)} className="border-t border-border">
                  <td className={TH}>{s.settled_on ? fmtDateTime(s.settled_on) : "—"}</td>
                  <td className={TH}>
                    <Badge className={s.status === "success" ? "badge-success" : s.status === "failed" ? "badge-danger" : "badge-warning"}>{humanise(s.status)}</Badge>
                  </td>
                  <td className={`${TH} text-right tabular-nums`}>{fmtMoney(s.total_zar)}</td>
                  <td className={`${TH} text-right tabular-nums`}>{fmtMoney(s.fees_zar)}</td>
                  <td className={`${TH} text-right tabular-nums`}>{fmtMoney(s.paid_zar)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  )
}

function Snapshots() {
  const { data, reload } = useLoad<{ snapshots: ReconSnapshot[] }>(() => listReconSnapshots(48), [])
  return (
    <Section
      title="Balance history"
      right={
        <Button size="sm" variant="ghost" onClick={reload}>
          <RefreshCcw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      }
    >
      {data.state !== "ready" ? (
        <NotConnected loadable={data} service="Billing" onRetry={reload} />
      ) : (data.data.snapshots ?? []).length === 0 ? (
        <NoDataYet message="No balance checks yet." />
      ) : (
        <div className="max-h-96 overflow-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-secondary text-left text-xs text-muted-foreground">
              <tr>
                <th className={TH}>Taken</th>
                <th className={`${TH} text-right`}>Paystack balance</th>
                <th className={`${TH} text-right`}>Tenant wallets</th>
                <th className={`${TH} text-right`}>Liabilities</th>
                <th className={`${TH} text-right`}>Headroom</th>
                <th className={TH}>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.data.snapshots.map((s, i) => (
                <tr key={`${s.taken_at}-${i}`} className="border-t border-border">
                  <td className={TH}>{fmtDateTime(s.taken_at)}</td>
                  <td className={`${TH} text-right tabular-nums`}>{fmtMoney(s.balance_zar)}</td>
                  <td className={`${TH} text-right tabular-nums`}>{fmtMoney(s.wallets_zar)}</td>
                  <td className={`${TH} text-right tabular-nums`}>{fmtMoney(s.liabilities_open_zar)}</td>
                  <td className={`${TH} text-right tabular-nums ${s.headroom_zar < 0 ? "text-red-400" : ""}`}>{fmtMoney(s.headroom_zar)}</td>
                  <td className={TH}>
                    <Badge className={s.status === "ok" ? "badge-success" : "badge-danger"}>{s.status === "ok" ? "Covered" : "Short"}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  )
}

// ------------------------------------------------------------------ fee tax invoices

function FeeTaxInvoices() {
  const { data, reload } = useLoad<{ invoices: FeeInvoice[] }>(() => listFeeInvoices(true), [])
  const [confirming, setConfirming] = useState(false)
  const [issued, setIssued] = useState<FeeInvoice[] | null>(null)
  const [viewErr, setViewErr] = useState<string | null>(null)
  const act = useActionState()

  const issue = async () => {
    const r = await act.run("issue", () => generateFeeInvoices({}))
    if (r) {
      setIssued(r.issued ?? [])
      setConfirming(false)
      reload()
    }
  }

  return (
    <Section
      title="Fee tax invoices"
      right={
        <Button size="sm" onClick={() => { act.clear(); setIssued(null); setConfirming(true) }}>
          Issue last month&apos;s invoices
        </Button>
      }
    >
      {issued && (issued.length === 0 ? <Note tone="info">Nothing to issue.</Note> : <Note tone="success">Issued {issued.length} invoice{issued.length === 1 ? "" : "s"}: {issued.map((i) => i.number).join(", ")}.</Note>)}
      {viewErr && <Note tone="error">{viewErr}</Note>}
      {data.state !== "ready" ? (
        <NotConnected loadable={data} service="Billing" onRetry={reload} />
      ) : (data.data.invoices ?? []).length === 0 ? (
        <NoDataYet message="No fee invoices have been issued yet." />
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className={TH}>Tenant</th>
                <th className={TH}>Number</th>
                <th className={TH}>Month</th>
                <th className={TH}>Type</th>
                <th className={`${TH} text-right`}>Total</th>
                <th className={TH} />
              </tr>
            </thead>
            <tbody>
              {data.data.invoices.map((i) => (
                <tr key={i.id} className="border-t border-border">
                  <td className={`${TH} font-mono text-xs`}>{i.tenant_id.slice(0, 8)}</td>
                  <td className={`${TH} font-mono text-xs`}>{i.number}</td>
                  <td className={TH}>{periodLabel(i.period)}</td>
                  <td className={TH}>{i.doc_type}</td>
                  <td className={`${TH} text-right tabular-nums`}>{fmtMoney(i.total_zar)}</td>
                  <td className={`${TH} text-right`}>
                    <Button size="sm" variant="outline" onClick={async () => setViewErr(await showFeeInvoice(i, "view"))}>
                      View
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ConfirmModal open={confirming} onOpenChange={setConfirming} title="Issue fee invoices" confirmLabel="Issue invoices" busy={act.busy === "issue"} error={act.msg?.tone === "error" ? act.msg.text : null} onConfirm={issue}>
        <p>This issues numbered, immutable tax documents to every tenant that was charged fees last month. They cannot be edited or deleted afterwards.</p>
      </ConfirmModal>
    </Section>
  )
}
