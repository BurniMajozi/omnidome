"use client"

/**
 * Early-termination fee simulator + the canonical breakdown table.
 * Every number in the breakdown comes from POST /fee-policies/simulate (or a stored calculation);
 * the only static content is the clearly labelled worked example from docs/billing-fee-policies-api.md.
 */

import { useEffect, useState } from "react"
import { Calculator, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { fmtMoney } from "@/lib/money"
import { useBillingTier } from "@/lib/billing-api"
import {
  asList,
  calculateFee,
  listFeePolicies,
  simulateFee,
  type FeeBreakdown,
  type FeePolicy,
  type SimulateInput,
  type SimulateResult,
} from "@/lib/invoicing-api"
import { Field, Note, humanise, inputClass, tierAtLeast, tierTip, todayIso, useActionState } from "../shared"

export const TRIGGERS = ["cancellation", "downgrade", "plan_change", "relocation", "suspension_abuse", "device_buyout"]
export const ROUTER_CONDITIONS = ["new", "good", "fair", "damaged", "missing_parts"]

const pct = (s: string | undefined) => {
  const n = Number(s)
  return Number.isFinite(n) ? `${(n * 100).toFixed(2)}%` : "—"
}

/** The canonical breakdown: one row per component/adjustment, totals, router credit, waiver eligibility and the formula text. */
export function BreakdownView({ breakdown, flags }: { breakdown: FeeBreakdown; flags?: string[] }) {
  const t = breakdown.totals
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
        <span>Term: <b className="text-foreground">{breakdown.term_months} months</b></span>
        <span>Elapsed: <b className="text-foreground">{breakdown.months_elapsed}</b></span>
        <span>Remaining: <b className="text-foreground">{breakdown.months_remaining}</b></span>
        <span>Method: <b className="text-foreground">{humanise(breakdown.method)}</b></span>
      </div>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full min-w-[860px] text-xs">
          <thead className="bg-secondary/40 text-left text-muted-foreground">
            <tr>
              <th className="px-2 py-1.5">Component</th>
              <th className="px-2 py-1.5 text-right">Total</th>
              <th className="px-2 py-1.5 text-right">Per month</th>
              <th className="px-2 py-1.5 text-right">Elapsed</th>
              <th className="px-2 py-1.5 text-right">Remaining</th>
              <th className="px-2 py-1.5 text-right">Unamortised</th>
              <th className="px-2 py-1.5 text-right">Owed (net)</th>
              <th className="px-2 py-1.5 text-right">VAT</th>
              <th className="px-2 py-1.5 text-right">Gross</th>
              <th className="px-2 py-1.5">Formula / source</th>
            </tr>
          </thead>
          <tbody>
            {breakdown.lines.map((l, i) => {
              const adj = l.kind !== "component"
              return (
                <tr key={`${l.code ?? l.kind}-${i}`} className={`border-t border-border ${adj ? "bg-secondary/20" : ""}`}>
                  <td className="px-2 py-1.5">
                    <span className="font-medium text-foreground">{l.label}</span>
                    {adj && <span className="ml-1 rounded bg-secondary px-1 text-[10px] text-muted-foreground">{humanise(l.kind)}</span>}
                    {l.reason_code && <span className="ml-1 text-[10px] text-muted-foreground">({l.reason_code})</span>}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{l.total_amount ? fmtMoney(l.total_amount) : "—"}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{l.monthly_amortisation ? fmtMoney(l.monthly_amortisation) : "—"}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{l.months_elapsed ?? "—"}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{l.months_remaining ?? "—"}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{l.unamortised_fraction ? pct(l.unamortised_fraction) : "—"}</td>
                  <td className="px-2 py-1.5 text-right font-medium tabular-nums">{fmtMoney(l.net ?? l.amount)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{l.vat ? fmtMoney(l.vat) : "—"}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{l.gross ? fmtMoney(l.gross) : "—"}</td>
                  <td className="px-2 py-1.5 text-muted-foreground">
                    {l.formula ?? "—"}
                    {l.source && <span className="ml-1 text-[10px]">[{l.source}]</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="ml-auto grid w-full max-w-sm grid-cols-[1fr_auto] gap-x-6 gap-y-1 rounded-md border border-border bg-secondary/20 p-3 text-sm">
        <span className="text-muted-foreground">Net fee</span>
        <span className="text-right tabular-nums">{fmtMoney(t.fee_net)}</span>
        <span className="text-muted-foreground">VAT</span>
        <span className="text-right tabular-nums">{fmtMoney(t.fee_vat)}</span>
        <span className="font-semibold text-foreground">Fee total</span>
        <span className="text-right font-semibold tabular-nums text-foreground">{fmtMoney(t.fee_total)}</span>
        {Number(t.waived_total) !== 0 && (
          <>
            <span className="text-muted-foreground">Waived</span>
            <span className="text-right tabular-nums">{fmtMoney(t.waived_total)}</span>
          </>
        )}
        {Number(t.outstanding_balance) !== 0 && (
          <>
            <span className="text-muted-foreground">Outstanding balance</span>
            <span className="text-right tabular-nums">{fmtMoney(t.outstanding_balance)}</span>
          </>
        )}
        <span className="border-t border-border pt-1 font-semibold text-foreground">Total payable</span>
        <span className="border-t border-border pt-1 text-right font-semibold tabular-nums text-foreground">{fmtMoney(t.total_payable)}</span>
      </div>

      {breakdown.router_credit && Object.keys(breakdown.router_credit).length > 0 && (
        <details className="rounded-md border border-border px-3 py-2 text-xs">
          <summary className="cursor-pointer font-medium text-foreground">Router credit</summary>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-muted-foreground">{JSON.stringify(breakdown.router_credit, null, 2)}</pre>
        </details>
      )}
      {breakdown.waiver_eligibility && breakdown.waiver_eligibility.length > 0 && (
        <div className="text-xs">
          <p className="mb-1 font-medium text-foreground">Waiver eligibility</p>
          <ul className="space-y-0.5 text-muted-foreground">
            {breakdown.waiver_eligibility.map((w) => (
              <li key={w.reason_code}>
                {humanise(w.reason_code)}: needs {w.required_tier}
                {w.indicative_gross ? `, indicative ${fmtMoney(w.indicative_gross)}` : ""}
                {w.applied ? " (applied)" : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      {breakdown.formula && (
        <p className="rounded-md bg-secondary/30 p-2 font-mono text-[11px] leading-relaxed text-muted-foreground">{breakdown.formula}</p>
      )}
      {flags && flags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {flags.map((f) => (
            <span key={f} className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-300">
              {f}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

interface CompRow {
  code: string
  amount: string
  discount: string
}

const monthsAgo = (m: number) => {
  const d = new Date()
  d.setMonth(d.getMonth() - m)
  return d.toISOString().slice(0, 10)
}

export function FeeSimulator() {
  const { tier } = useBillingTier()
  const canCalc = tierAtLeast(tier, "clerk")
  const act = useActionState()
  const [policies, setPolicies] = useState<FeePolicy[]>([])
  const [policyId, setPolicyId] = useState("")
  const [mode, setMode] = useState<"subscription" | "snapshot">("snapshot")
  const [subscriptionId, setSubscriptionId] = useState("")
  const [trigger, setTrigger] = useState("cancellation")
  const [customTrigger, setCustomTrigger] = useState("")
  const [effective, setEffective] = useState(todayIso())
  const [reason, setReason] = useState("")
  const [routerReturned, setRouterReturned] = useState(false)
  const [routerCond, setRouterCond] = useState("good")
  const [termStart, setTermStart] = useState("")
  const [termMonths, setTermMonths] = useState("24")
  const [rental, setRental] = useState("")
  const [planName, setPlanName] = useState("")
  const [comps, setComps] = useState<CompRow[]>([{ code: "router", amount: "", discount: "" }])
  const [result, setResult] = useState<SimulateResult | null>(null)
  const [saved, setSaved] = useState<string | null>(null)

  useEffect(() => {
    listFeePolicies({ current_only: true }).then((l) => l.state === "ready" && setPolicies(asList(l.data)))
  }, [])

  const loadExample = () => {
    setMode("snapshot")
    setTrigger("cancellation")
    setTermStart(monthsAgo(10))
    setEffective(todayIso())
    setTermMonths("24")
    setComps([
      { code: "router", amount: "1500", discount: "" },
      { code: "activation", amount: "500", discount: "" },
      { code: "installation", amount: "1000", discount: "" },
    ])
    setRental("")
    setResult(null)
  }

  const build = (): SimulateInput | string => {
    const t = trigger === "custom" ? customTrigger.trim().toLowerCase() : trigger
    if (!t) return "Enter a trigger."
    const base: SimulateInput = {
      trigger: t,
      effective_date: effective || undefined,
      reason_code: reason.trim() || undefined,
      router_returned: routerReturned || undefined,
      router_condition: routerReturned ? routerCond : undefined,
      policy_id: policyId || undefined,
    }
    if (mode === "subscription") {
      if (!subscriptionId.trim()) return "Enter a subscription id."
      return { ...base, subscription_id: subscriptionId.trim() }
    }
    if (!termStart) return "Choose the term start date."
    const months = Number(termMonths)
    if (!Number.isInteger(months) || months <= 0) return "Term months must be a whole number."
    const used = comps.filter((c) => c.code.trim() && c.amount.trim() !== "")
    if (used.length === 0) return "Add at least one component with an amount."
    return {
      ...base,
      snapshot: {
        term_start: termStart,
        term_months: months,
        components: used.map((c) => ({ code: c.code.trim(), amount: c.amount.trim(), ...(c.discount.trim() ? { discount: c.discount.trim() } : {}) })),
        ...(rental.trim() ? { monthly_rental_zar: rental.trim() } : {}),
        ...(planName.trim() ? { plan_name: planName.trim() } : {}),
      },
    }
  }

  const simulate = async () => {
    const b = build()
    if (typeof b === "string") return act.setMsg({ tone: "error", text: b })
    setSaved(null)
    const r = await act.run("sim", () => simulateFee(b))
    setResult(r ?? null)
  }

  const persist = async () => {
    const b = build()
    if (typeof b === "string") return act.setMsg({ tone: "error", text: b })
    if (mode !== "subscription") return act.setMsg({ tone: "error", text: "Only a real subscription can be saved as a calculation. Switch to Existing subscription." })
    const r = await act.run("calc", () => calculateFee(b), (d) => (d?.created ? "Calculation stored." : "An identical calculation already exists (idempotent); nothing new was stored."))
    if (r) setSaved(r.id)
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-md border border-border p-0.5 text-xs">
          {(["snapshot", "subscription"] as const).map((m) => (
            <button key={m} type="button" onClick={() => setMode(m)} className={`rounded px-3 py-1 ${mode === m ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              {m === "snapshot" ? "What-if inputs" : "Existing subscription"}
            </button>
          ))}
        </div>
        <Button size="sm" variant="outline" onClick={loadExample} title="Fills the what-if form with the canonical documentation example (R1500 router, R500 activation, R1000 installation, 24 months, cancelled after 10 months)">
          Load documentation example
        </Button>
      </div>

      {act.msg && <Note tone={act.msg.tone}>{act.msg.text}</Note>}

      <div className="grid gap-3 md:grid-cols-3">
        {mode === "subscription" ? (
          <Field label="Subscription ID" className="md:col-span-3">
            <input className={inputClass} value={subscriptionId} onChange={(e) => setSubscriptionId(e.target.value)} placeholder="UUID of the subscription" />
          </Field>
        ) : (
          <>
            <Field label="Term start">
              <input type="date" className={inputClass} value={termStart} onChange={(e) => setTermStart(e.target.value)} />
            </Field>
            <Field label="Term (months)">
              <input className={inputClass} inputMode="numeric" value={termMonths} onChange={(e) => setTermMonths(e.target.value)} />
            </Field>
            <Field label="Monthly rental (R)" hint="Only needed for percent-of-rental methods">
              <input className={inputClass} inputMode="decimal" value={rental} onChange={(e) => setRental(e.target.value)} />
            </Field>
            <Field label="Plan name (optional)" hint="Used for plan-specific policies and catalogue amounts">
              <input className={inputClass} value={planName} onChange={(e) => setPlanName(e.target.value)} />
            </Field>
            <div className="md:col-span-2">
              <p className="mb-1 text-xs font-medium text-muted-foreground">Components (what the contract cost to set up)</p>
              <div className="space-y-1.5">
                {comps.map((c, i) => (
                  <div key={i} className="flex gap-1.5">
                    <input aria-label="Component code" className={inputClass} list="fee-component-codes" placeholder="code, e.g. router" value={c.code} onChange={(e) => setComps(comps.map((x, j) => (j === i ? { ...x, code: e.target.value } : x)))} />
                    <input aria-label="Amount" className={`${inputClass} w-32`} inputMode="decimal" placeholder="amount" value={c.amount} onChange={(e) => setComps(comps.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)))} />
                    <input aria-label="Discount" className={`${inputClass} w-28`} inputMode="decimal" placeholder="discount" value={c.discount} onChange={(e) => setComps(comps.map((x, j) => (j === i ? { ...x, discount: e.target.value } : x)))} />
                    <Button type="button" size="icon-sm" variant="ghost-destructive" aria-label="Remove component" disabled={comps.length === 1} onClick={() => setComps(comps.filter((_, j) => j !== i))}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
                <datalist id="fee-component-codes">
                  <option value="router" />
                  <option value="activation" />
                  <option value="installation" />
                </datalist>
                <Button type="button" size="sm" variant="ghost" onClick={() => setComps([...comps, { code: "", amount: "", discount: "" }])}>
                  <Plus className="h-3.5 w-3.5" />
                  Add component
                </Button>
              </div>
            </div>
          </>
        )}
        <Field label="Trigger">
          <select className={inputClass} value={trigger} onChange={(e) => setTrigger(e.target.value)}>
            {TRIGGERS.map((t) => (
              <option key={t} value={t}>
                {humanise(t)}
              </option>
            ))}
            <option value="custom">Custom…</option>
          </select>
        </Field>
        {trigger === "custom" && (
          <Field label="Custom trigger slug">
            <input className={inputClass} value={customTrigger} onChange={(e) => setCustomTrigger(e.target.value)} placeholder="lowercase_slug" />
          </Field>
        )}
        <Field label="Effective date">
          <input type="date" className={inputClass} value={effective} onChange={(e) => setEffective(e.target.value)} />
        </Field>
        <Field label="Reason code (for waivers)">
          <input className={inputClass} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. fno_fault" />
        </Field>
        <Field label="Policy">
          <select className={inputClass} value={policyId} onChange={(e) => setPolicyId(e.target.value)}>
            <option value="">Applicable policy (automatic)</option>
            {policies.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} v{p.version}
              </option>
            ))}
          </select>
        </Field>
        <div className="flex items-end gap-3 pb-2">
          <label className="flex items-center gap-1.5 text-xs">
            <input type="checkbox" checked={routerReturned} onChange={(e) => setRouterReturned(e.target.checked)} />
            Router returned
          </label>
          {routerReturned && (
            <select aria-label="Router condition" className={`${inputClass} w-36`} value={routerCond} onChange={(e) => setRouterCond(e.target.value)}>
              {ROUTER_CONDITIONS.map((c) => (
                <option key={c} value={c}>
                  {humanise(c)}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={simulate} disabled={!!act.busy}>
          <Calculator className="h-3.5 w-3.5" />
          {act.busy === "sim" ? "Calculating…" : "Simulate"}
        </Button>
        {mode === "subscription" && result && (
          <Button size="sm" variant="outline" disabled={!!act.busy || !canCalc} title={!canCalc ? tierTip("clerk") : "Stores this run as an immutable calculation"} onClick={persist}>
            Save as calculation
          </Button>
        )}
        <span className="self-center text-[11px] text-muted-foreground">Simulation stores nothing.</span>
      </div>
      {saved && <Note tone="success">Stored as calculation {saved.slice(0, 8)}. Waive or invoice it from the Calculations tab.</Note>}

      {result && (
        <div className="space-y-3 rounded-md border border-border p-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span>
              Policy: <b className="text-foreground">{result.policy.name} v{result.policy.version}</b>
            </span>
            {result.snapshot_missing && <span className="text-amber-400">No contract snapshot: policy fallback amounts used</span>}
            <span className="font-mono text-[10px]">inputs {result.inputs_hash.slice(0, 12)}</span>
          </div>
          <BreakdownView breakdown={result.breakdown} flags={result.flags} />
        </div>
      )}
    </div>
  )
}
