"use client"

import { useCallback, useEffect, useState } from "react"
import { Plus, RefreshCcw, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { useBillingTier } from "@/lib/billing-api"
import { fmtMoney } from "@/lib/money"
import {
  asList,
  createSnapshot,
  invoiceFeeCalculation,
  listFeeCalculations,
  listSnapshots,
  waiveFeeCalculation,
  type ContractSnapshot,
  type FeeCalculation,
  type Loadable,
} from "@/lib/invoicing-api"
import { Field, Note, StatusBadge, fmtDateTime, humanise, inputClass, textareaClass, tierAtLeast, tierTip, todayIso, useActionState } from "../shared"
import { CustomerPicker, type PickedCustomer } from "./doc-editor"
import { BreakdownView } from "./fee-simulator"

// ------------------------------------------------------------------ calculations

export function FeeCalculations({ onOpenInvoice }: { onOpenInvoice?: (invoiceId: string) => void }) {
  const { tier } = useBillingTier()
  const clerk = tierAtLeast(tier, "clerk")
  const [cust, setCust] = useState<PickedCustomer | null>(null)
  const [sub, setSub] = useState("")
  const [includeSuperseded, setIncludeSuperseded] = useState(false)
  const [data, setData] = useState<Loadable<FeeCalculation[]>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const [open, setOpen] = useState<string | null>(null)

  useEffect(() => {
    let off = false
    setData({ state: "loading" })
    listFeeCalculations({ customer_id: cust?.id, subscription_id: sub.trim() || undefined, include_superseded: includeSuperseded || undefined }).then((l) => {
      if (off) return
      setData(l.state === "ready" ? { state: "ready", data: asList(l.data) } : (l as Loadable<FeeCalculation[]>))
    })
    return () => {
      off = true
    }
  }, [cust, sub, includeSuperseded, tick])
  const reload = useCallback(() => setTick((t) => t + 1), [])

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_auto]">
        <Field label="Customer">
          <CustomerPicker value={cust} onChange={setCust} />
        </Field>
        <Field label="Subscription ID">
          <input className={inputClass} value={sub} onChange={(e) => setSub(e.target.value)} placeholder="Optional filter" />
        </Field>
        <div className="flex items-end gap-3 pb-1">
          <label className="flex items-center gap-1.5 text-xs">
            <input type="checkbox" checked={includeSuperseded} onChange={(e) => setIncludeSuperseded(e.target.checked)} />
            Include superseded
          </label>
          <Button size="sm" variant="ghost" onClick={reload}>
            <RefreshCcw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {data.state !== "ready" ? (
        <NotConnected loadable={data} service="Billing" onRetry={reload} />
      ) : data.data.length === 0 ? (
        <NoDataYet message="No fee calculations match. Calculations are created automatically on cancellation, or from the simulator with Save as calculation." />
      ) : (
        <ul className="space-y-2">
          {data.data.map((c) => (
            <CalcRow key={c.id} c={c} isOpen={open === c.id} onToggle={() => setOpen(open === c.id ? null : c.id)} clerk={clerk} isAdmin={tier === "admin"} onChanged={reload} onOpenInvoice={onOpenInvoice} />
          ))}
        </ul>
      )}
    </div>
  )
}

function CalcRow({ c, isOpen, onToggle, clerk, isAdmin, onChanged, onOpenInvoice }: { c: FeeCalculation; isOpen: boolean; onToggle: () => void; clerk: boolean; isAdmin: boolean; onChanged: () => void; onOpenInvoice?: (id: string) => void }) {
  const act = useActionState()
  const [waive, setWaive] = useState(false)
  const [reasonCode, setReasonCode] = useState("")
  const [reasonText, setReasonText] = useState("")
  const [mode, setMode] = useState<"percent" | "amount">("percent")
  const [val, setVal] = useState("100")
  const [issue, setIssue] = useState(false)
  const open = c.status === "calculated" || c.status === "waived"

  const doWaive = async () => {
    if (!reasonCode.trim() || !reasonText.trim()) return act.setMsg({ tone: "error", text: "A reason code and a written reason are both required." })
    if (!val.trim() || Number.isNaN(Number(val)) || Number(val) <= 0) return act.setMsg({ tone: "error", text: "Enter a valid waiver value." })
    const r = await act.run(
      "waive",
      () => waiveFeeCalculation(c.id, { reason_code: reasonCode.trim(), reason: reasonText.trim(), ...(mode === "percent" ? { percent: val.trim() } : { amount_zar: val.trim() }) }),
      "Waiver recorded.",
    )
    if (r) {
      setWaive(false)
      onChanged()
    }
  }
  const doInvoice = async () => {
    const r = await act.run("invoice", () => invoiceFeeCalculation(c.id, issue), (d) => `${d?.created ? "Created" : "Already invoiced:"} ${d?.invoice_number ?? ""} (${d?.status ?? ""}).`)
    if (r) {
      onChanged()
      if (r.invoice_id) onOpenInvoice?.(r.invoice_id)
    }
  }

  return (
    <li className="rounded-md border border-border">
      <button type="button" className="flex w-full flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-left" onClick={onToggle} aria-expanded={isOpen}>
        <div className="space-y-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={c.status} />
            <span className="text-sm font-medium text-foreground">{humanise(c.trigger)}</span>
            <span className="text-xs text-muted-foreground">effective {c.effective_date ?? "—"}</span>
            {c.policy_version !== undefined && <span className="text-[11px] text-muted-foreground">policy v{c.policy_version}</span>}
            {c.auto_calculated && <span className="rounded bg-secondary px-1.5 text-[10px] text-muted-foreground">auto</span>}
          </div>
          <p className="text-[11px] text-muted-foreground">{fmtDateTime(c.created_at)}{c.invoice_number ? ` · invoice ${c.invoice_number}` : ""}</p>
        </div>
        <div className="text-right text-sm">
          <p className="font-semibold tabular-nums text-foreground">{fmtMoney(c.amount_due_zar)}</p>
          <p className="text-[11px] text-muted-foreground">fee {fmtMoney(c.fee_total_zar)}{Number(c.waived_total_zar) ? ` · waived ${fmtMoney(c.waived_total_zar)}` : ""}</p>
        </div>
      </button>
      {isOpen && (
        <div className="space-y-3 border-t border-border p-3">
          {act.msg && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
          <BreakdownView breakdown={c.breakdown} flags={c.flags} />
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" disabled={!open || !clerk || !!act.busy} title={!clerk ? tierTip("clerk") : !open ? "Only calculated/waived fees can be waived" : undefined} onClick={() => setWaive((v) => !v)}>
              Waive…
            </Button>
            <label className="flex items-center gap-1.5 text-xs">
              <input type="checkbox" checked={issue} onChange={(e) => setIssue(e.target.checked)} />
              Issue immediately (otherwise draft)
            </label>
            <Button size="sm" disabled={!open || !clerk || !!act.busy} title={!clerk ? tierTip("clerk") : !open ? "Already invoiced or superseded" : undefined} onClick={doInvoice}>
              {act.busy === "invoice" ? "Raising…" : "Raise invoice"}
            </Button>
            {c.invoice_id && (
              <Button size="sm" variant="ghost" onClick={() => onOpenInvoice?.(c.invoice_id as string)}>
                Open invoice {c.invoice_number}
              </Button>
            )}
          </div>
          {waive && (
            <div className="space-y-2 rounded-md border border-border p-3">
              <p className="text-xs text-muted-foreground">
                Clerks can waive up to the policy limit for clerk-tier reasons; anything above, admin-tier reasons and unlisted reasons need {isAdmin ? "an admin (you are one)" : "an admin"}. You cannot approve a fee you calculated yourself above the limit unless the policy allows it. The server decides.
              </p>
              <div className="grid gap-2 sm:grid-cols-4">
                <Field label="Reason code">
                  <input className={inputClass} value={reasonCode} onChange={(e) => setReasonCode(e.target.value)} placeholder="e.g. fno_fault" />
                </Field>
                <Field label="Waive by">
                  <select className={inputClass} value={mode} onChange={(e) => setMode(e.target.value as "percent" | "amount")}>
                    <option value="percent">Percent</option>
                    <option value="amount">Amount (gross R)</option>
                  </select>
                </Field>
                <Field label={mode === "percent" ? "Percent" : "Amount (R)"}>
                  <input className={inputClass} inputMode="decimal" value={val} onChange={(e) => setVal(e.target.value)} />
                </Field>
                <Field label="Written reason" className="sm:col-span-4">
                  <textarea className={textareaClass} value={reasonText} onChange={(e) => setReasonText(e.target.value)} />
                </Field>
              </div>
              <div className="flex gap-2">
                <Button size="sm" disabled={!!act.busy} onClick={doWaive}>
                  Apply waiver
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setWaive(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  )
}

// ------------------------------------------------------------------ snapshots

interface Row {
  code: string
  amount: string
  discount: string
}

export function FeeSnapshots() {
  const { tier } = useBillingTier()
  const clerk = tierAtLeast(tier, "clerk")
  const act = useActionState()
  const [sub, setSub] = useState("")
  const [termStart, setTermStart] = useState("")
  const [termMonths, setTermMonths] = useState("")
  const [rental, setRental] = useState("")
  const [policyId, setPolicyId] = useState("")
  const [backfill, setBackfill] = useState(false)
  const [supersede, setSupersede] = useState(false)
  const [notes, setNotes] = useState("")
  const [rows, setRows] = useState<Row[]>([{ code: "router", amount: "", discount: "" }, { code: "activation", amount: "", discount: "" }, { code: "installation", amount: "", discount: "" }])
  const [list, setList] = useState<Loadable<ContractSnapshot[]> | null>(null)
  const [listFor, setListFor] = useState("")

  const loadList = useCallback((id: string) => {
    if (!id.trim()) return
    setListFor(id.trim())
    setList({ state: "loading" })
    listSnapshots(id.trim()).then((l) => setList(l.state === "ready" ? { state: "ready", data: asList(l.data) } : (l as Loadable<ContractSnapshot[]>)))
  }, [])

  const submit = async () => {
    if (!sub.trim()) return act.setMsg({ tone: "error", text: "Subscription ID is required." })
    const comps = rows.filter((r) => r.code.trim() && r.amount.trim() !== "")
    if (comps.length === 0) return act.setMsg({ tone: "error", text: "Enter at least one component amount." })
    if (comps.some((r) => Number.isNaN(Number(r.amount)))) return act.setMsg({ tone: "error", text: "Component amounts must be numbers." })
    const months = termMonths.trim() ? Number(termMonths) : undefined
    if (months !== undefined && (!Number.isInteger(months) || months <= 0)) return act.setMsg({ tone: "error", text: "Term months must be a whole number." })
    const r = await act.run(
      "snap",
      () =>
        createSnapshot({
          subscription_id: sub.trim(),
          ...(termStart ? { term_start: termStart } : {}),
          ...(months !== undefined ? { term_months: months } : {}),
          components: comps.map((c) => ({ code: c.code.trim(), amount: c.amount.trim(), ...(c.discount.trim() ? { discount: c.discount.trim() } : {}) })),
          ...(rental.trim() ? { monthly_rental_zar: rental.trim() } : {}),
          policy_id: policyId.trim() || null,
          backfill: backfill || undefined,
          supersede: supersede || undefined,
          notes: notes.trim() || undefined,
        }),
      "Snapshot recorded. It is immutable; later price changes will not alter it.",
    )
    if (r) loadList(sub)
  }

  return (
    <div className="space-y-5">
      <Note>
        A contract snapshot records what this subscription cost to set up. It always wins over policy amounts, so the claw-back is calculated on what the customer actually got. Creating one when a snapshot already exists needs "supersede" (adds a new version; earlier ones are kept).
      </Note>
      {act.msg && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
      <div className="grid gap-3 md:grid-cols-3">
        <Field label="Subscription ID" className="md:col-span-2">
          <input className={inputClass} value={sub} onChange={(e) => setSub(e.target.value)} />
        </Field>
        <Field label="Policy ID (optional)">
          <input className={inputClass} value={policyId} onChange={(e) => setPolicyId(e.target.value)} />
        </Field>
        <Field label="Term start" hint="Empty = subscription billing anchor">
          <input type="date" className={inputClass} value={termStart} onChange={(e) => setTermStart(e.target.value)} max={todayIso()} />
        </Field>
        <Field label="Term months" hint="Empty = applicable policy term">
          <input className={inputClass} inputMode="numeric" value={termMonths} onChange={(e) => setTermMonths(e.target.value)} />
        </Field>
        <Field label="Monthly rental (R)" hint="Empty = subscription base price">
          <input className={inputClass} inputMode="decimal" value={rental} onChange={(e) => setRental(e.target.value)} />
        </Field>
        <div className="md:col-span-3">
          <p className="mb-1 text-xs font-medium text-muted-foreground">Components</p>
          <div className="space-y-1.5">
            {rows.map((r, i) => (
              <div key={i} className="flex gap-1.5">
                <input aria-label="Component code" className={inputClass} placeholder="code" value={r.code} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, code: e.target.value } : x)))} />
                <input aria-label="Amount" className={`${inputClass} w-36`} inputMode="decimal" placeholder="amount" value={r.amount} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)))} />
                <input aria-label="Discount" className={`${inputClass} w-28`} inputMode="decimal" placeholder="discount" value={r.discount} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, discount: e.target.value } : x)))} />
                <Button type="button" size="icon-sm" variant="ghost-destructive" aria-label="Remove component" disabled={rows.length === 1} onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
            <Button type="button" size="sm" variant="ghost" onClick={() => setRows([...rows, { code: "", amount: "", discount: "" }])}>
              <Plus className="h-3.5 w-3.5" />
              Add component
            </Button>
          </div>
        </div>
        <Field label="Notes" className="md:col-span-3">
          <textarea className={textareaClass} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
        <div className="flex flex-wrap gap-4 md:col-span-3">
          <label className="flex items-center gap-1.5 text-xs">
            <input type="checkbox" checked={backfill} onChange={(e) => setBackfill(e.target.checked)} />
            Backfill (historic contract)
          </label>
          <label className="flex items-center gap-1.5 text-xs">
            <input type="checkbox" checked={supersede} onChange={(e) => setSupersede(e.target.checked)} />
            Supersede the existing snapshot
          </label>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={!clerk || !!act.busy} title={!clerk ? tierTip("clerk") : undefined} onClick={submit}>
          {act.busy === "snap" ? "Saving…" : "Record snapshot"}
        </Button>
        <Button size="sm" variant="outline" disabled={!sub.trim()} onClick={() => loadList(sub)}>
          Show snapshots for this subscription
        </Button>
      </div>

      {list && (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold text-foreground">Snapshots for {listFor.slice(0, 8)}…</h4>
          {list.state !== "ready" ? (
            <NotConnected loadable={list} service="Billing" onRetry={() => loadList(listFor)} className="p-4" />
          ) : list.data.length === 0 ? (
            <NoDataYet message="No snapshot exists for this subscription." className="p-4" />
          ) : (
            <ul className="space-y-2">
              {list.data.map((s) => (
                <li key={s.id} className="rounded-md border border-border p-3 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-foreground">Version {s.version ?? 1}</span>
                    {s.is_current !== false ? <StatusBadge status="accepted" /> : <StatusBadge status="superseded" />}
                    <span className="text-muted-foreground">
                      term start {s.term_start ?? "—"} · {s.term_months ?? "—"} months{s.monthly_rental_zar ? ` · rental ${fmtMoney(s.monthly_rental_zar)}` : ""}
                    </span>
                  </div>
                  {s.components && (
                    <p className="mt-1 text-muted-foreground">
                      {s.components.map((c) => `${humanise(c.code)} ${fmtMoney(c.amount)}${c.discount && Number(c.discount) ? ` (-${fmtMoney(c.discount)})` : ""}`).join(" · ")}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
