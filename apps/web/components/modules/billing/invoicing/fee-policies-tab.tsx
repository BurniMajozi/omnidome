"use client"

import { useCallback, useEffect, useState } from "react"
import { Pencil, Plus, RefreshCcw, Trash2, Wand2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { useBillingTier } from "@/lib/billing-api"
import { fmtMoney } from "@/lib/money"
import {
  asList,
  createDefaultFeeTemplate,
  createFeePolicy,
  deactivateFeePolicy,
  listFeePolicies,
  updateFeePolicy,
  type FeeComponent,
  type FeePolicy,
  type FeePolicyBody,
  type FeeWaiverRule,
  type Loadable,
} from "@/lib/invoicing-api"
import { Field, Modal, Note, humanise, inputClass, textareaClass, tierTip, useActionState } from "../shared"
import { FeeCalculations, FeeSnapshots } from "./fee-calculations"
import { FeeSimulator, TRIGGERS } from "./fee-simulator"

export function FeePoliciesTab({ onOpenInvoice }: { onOpenInvoice?: (invoiceId: string) => void }) {
  return (
    <Tabs defaultValue="policies">
      <TabsList className="bg-secondary">
        <TabsTrigger value="policies">Policies</TabsTrigger>
        <TabsTrigger value="simulator">Simulator</TabsTrigger>
        <TabsTrigger value="calculations">Calculations</TabsTrigger>
        <TabsTrigger value="snapshots">Contract snapshots</TabsTrigger>
      </TabsList>
      <TabsContent value="policies" className="mt-4">
        <PoliciesSection />
      </TabsContent>
      <TabsContent value="simulator" className="mt-4">
        <FeeSimulator />
      </TabsContent>
      <TabsContent value="calculations" className="mt-4">
        <FeeCalculations onOpenInvoice={onOpenInvoice} />
      </TabsContent>
      <TabsContent value="snapshots" className="mt-4">
        <FeeSnapshots />
      </TabsContent>
    </Tabs>
  )
}

// ------------------------------------------------------------------ policies

const blankPolicy = (): FeePolicyBody => ({
  name: "",
  description: null,
  trigger_types: ["cancellation"],
  applies_to_plans: [],
  is_default: false,
  is_active: true,
  effective_from: null,
  effective_to: null,
  term_months: 24,
  components: [
    { code: "router", label: "Router", amount_source: "snapshot", fixed_amount: null, recoverable: true },
    { code: "activation", label: "Activation", amount_source: "snapshot", fixed_amount: null, recoverable: true },
    { code: "installation", label: "Installation", amount_source: "snapshot", fixed_amount: null, recoverable: true },
  ],
  method: "straight_line",
  flat_percent: "100",
  rental_percent: "100",
  month_rule: { mode: "whole_months", remaining_rounding: "up" },
  min_fee_zar: null,
  max_fee_zar: null,
  grace_period_days: 0,
  waivers: [],
  auto_approve_waiver_limit_zar: null,
  allow_self_approval: false,
  router_credit: { enabled: false, mode: "offset_router_component", router_component_code: "router", condition_pct: { new: "100", good: "90", fair: "60", damaged: "25", missing_parts: "0" } },
  vat: { rate: "0.15", treatment: "exclusive" },
  outstanding_balance: "include",
  auto_invoice: false,
  auto_invoice_stage: "proceed",
  invoice_due_days: 14,
})

function toBody(p: FeePolicy): FeePolicyBody {
  const base = blankPolicy()
  const { id: _id, policy_key: _pk, version: _v, superseded_by: _s, created_at: _c, ...rest } = p
  void _id; void _pk; void _v; void _s; void _c
  return { ...base, ...rest, month_rule: { ...base.month_rule, ...(rest.month_rule ?? {}) }, router_credit: { ...base.router_credit, ...(rest.router_credit ?? {}) }, vat: { ...base.vat, ...(rest.vat ?? {}) } }
}

function PoliciesSection() {
  const { isAdmin } = useBillingTier()
  const act = useActionState()
  const [data, setData] = useState<Loadable<FeePolicy[]>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const [edit, setEdit] = useState<{ id: string | null; body: FeePolicyBody } | null>(null)
  const [confirmDel, setConfirmDel] = useState<string | null>(null)

  useEffect(() => {
    let off = false
    setData({ state: "loading" })
    listFeePolicies({ current_only: true }).then((l) => {
      if (off) return
      setData(l.state === "ready" ? { state: "ready", data: asList(l.data) } : (l as Loadable<FeePolicy[]>))
    })
    return () => {
      off = true
    }
  }, [tick])
  const reload = useCallback(() => setTick((t) => t + 1), [])

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-foreground">Early-termination fee policies</h3>
        <Button size="sm" variant="ghost" onClick={reload}>
          <RefreshCcw className="h-3.5 w-3.5" />
          Refresh
        </Button>
        <div className="ml-auto flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!isAdmin || !!act.busy}
            title={!isAdmin ? tierTip("admin") : "Creates the standard 24-month straight-line policy. Component amounts come from each contract snapshot; none are invented."}
            onClick={async () => {
              const r = await act.run("tpl", () => createDefaultFeeTemplate(), "Default 24-month policy created.")
              if (r) reload()
            }}
          >
            <Wand2 className="h-3.5 w-3.5" />
            {act.busy === "tpl" ? "Creating…" : "Create default 24-month template"}
          </Button>
          <Button size="sm" disabled={!isAdmin} title={!isAdmin ? tierTip("admin") : undefined} onClick={() => { act.clear(); setEdit({ id: null, body: blankPolicy() }) }}>
            <Plus className="h-3.5 w-3.5" />
            New policy
          </Button>
        </div>
      </div>
      {act.msg && !edit && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
      <p className="text-xs text-muted-foreground">Editing a policy creates a new version; old calculations keep pointing at the version they used. Without any applicable policy, cancellations fall back to the legacy hard-coded tiers.</p>

      {data.state !== "ready" ? (
        <NotConnected loadable={data} service="Billing" onRetry={reload} />
      ) : data.data.length === 0 ? (
        <NoDataYet message="No fee policies yet. Create the default 24-month template or define your own." />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {data.data.map((p) => (
            <div key={p.id} className="space-y-2 rounded-md border border-border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium text-foreground">{p.name}</p>
                <span className="text-[11px] text-muted-foreground">v{p.version}</span>
                {p.is_default && <Badge className="badge-info">Default</Badge>}
                {p.is_active ? <Badge className="badge-success">Active</Badge> : <Badge variant="secondary">Inactive</Badge>}
                <div className="ml-auto flex gap-1">
                  <Button size="icon-sm" variant="ghost" aria-label={`Edit ${p.name}`} disabled={!isAdmin} title={!isAdmin ? tierTip("admin") : undefined} onClick={() => { act.clear(); setEdit({ id: p.id, body: toBody(p) }) }}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  {confirmDel === p.id ? (
                    <>
                      <Button size="sm" variant="destructive" disabled={!!act.busy} onClick={async () => { const r = await act.run("del", () => deactivateFeePolicy(p.id), "Policy deactivated (all versions)."); setConfirmDel(null); if (r !== undefined) reload() }}>
                        Deactivate
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setConfirmDel(null)}>
                        Cancel
                      </Button>
                    </>
                  ) : (
                    <Button size="icon-sm" variant="ghost-destructive" aria-label={`Deactivate ${p.name}`} disabled={!isAdmin} title={!isAdmin ? tierTip("admin") : "Deactivate"} onClick={() => setConfirmDel(p.id)}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <Dt k="Triggers" v={(p.trigger_types ?? []).map(humanise).join(", ") || "—"} />
                <Dt k="Plans" v={(p.applies_to_plans ?? []).length ? p.applies_to_plans.join(", ") : "Every plan"} />
                <Dt k="Term" v={`${p.term_months} months`} />
                <Dt k="Method" v={humanise(p.method)} />
                <Dt k="Components" v={(p.components ?? []).map((c) => c.label || c.code).join(", ") || "—"} />
                <Dt k="Grace" v={`${p.grace_period_days} days`} />
                <Dt k="Min / max fee" v={`${p.min_fee_zar ? fmtMoney(p.min_fee_zar) : "none"} / ${p.max_fee_zar ? fmtMoney(p.max_fee_zar) : "none"}`} />
                <Dt k="Router credit" v={p.router_credit?.enabled ? humanise(p.router_credit.mode) : "Off"} />
                <Dt k="VAT" v={`${(Number(p.vat?.rate) * 100).toFixed(0)}% ${p.vat?.treatment}`} />
                <Dt k="Auto-invoice" v={p.auto_invoice ? `Yes (${p.auto_invoice_stage})` : "No"} />
                <Dt k="Waivers" v={(p.waivers ?? []).length ? `${p.waivers.length} reason rule(s)` : "none"} />
                <Dt k="Effective" v={`${p.effective_from ?? "—"} to ${p.effective_to ?? "open"}`} />
              </dl>
            </div>
          ))}
        </div>
      )}

      <Modal open={!!edit} onOpenChange={(o) => !o && setEdit(null)} title={edit?.id ? "Edit fee policy (creates a new version)" : "New fee policy"} wide>
        {edit && (
          <PolicyForm
            body={edit.body}
            busy={!!act.busy}
            msg={act.msg}
            onCancel={() => setEdit(null)}
            onSave={async (b) => {
              const r = await act.run("save", () => (edit.id ? updateFeePolicy(edit.id, b) : createFeePolicy(b)), "Policy saved.")
              if (r) {
                setEdit(null)
                reload()
              }
            }}
          />
        )}
      </Modal>
    </div>
  )
}

function Dt({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">{k}</dt>
      <dd className="text-foreground">{v}</dd>
    </div>
  )
}

const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean)
const nullIfEmpty = (s: string | null | undefined) => (s === null || s === undefined || s.trim() === "" ? null : s.trim())

function PolicyForm({ body, busy, msg, onSave, onCancel }: { body: FeePolicyBody; busy: boolean; msg: { tone: "error" | "success" | "info"; text: string } | null; onSave: (b: FeePolicyBody) => void; onCancel: () => void }) {
  const [f, setF] = useState<FeePolicyBody>(body)
  const [triggersText, setTriggersText] = useState((body.trigger_types ?? []).join(", "))
  const [plansText, setPlansText] = useState((body.applies_to_plans ?? []).join(", "))
  const [catalogText, setCatalogText] = useState(body.catalog_amounts && Object.keys(body.catalog_amounts).length ? JSON.stringify(body.catalog_amounts, null, 2) : "")
  const [err, setErr] = useState<string | null>(null)
  const set = <K extends keyof FeePolicyBody>(k: K, v: FeePolicyBody[K]) => setF((cur) => ({ ...cur, [k]: v }))

  const setComp = (i: number, p: Partial<FeeComponent>) => set("components", f.components.map((c, j) => (j === i ? { ...c, ...p } : c)))
  const setWaiver = (i: number, p: Partial<FeeWaiverRule>) => set("waivers", f.waivers.map((c, j) => (j === i ? { ...c, ...p } : c)))

  const submit = () => {
    setErr(null)
    if (!f.name.trim()) return setErr("Policy name is required.")
    if (!Number.isInteger(Number(f.term_months)) || Number(f.term_months) <= 0) return setErr("Term months must be a whole number.")
    if (f.components.length === 0 || f.components.some((c) => !c.code.trim())) return setErr("Every component needs a code (add at least one).")
    if (f.components.some((c) => c.amount_source === "fixed" && !nullIfEmpty(c.fixed_amount))) return setErr("Components with source 'fixed' need a fixed amount.")
    let catalog: Record<string, Record<string, string>> | undefined
    if (catalogText.trim()) {
      try {
        catalog = JSON.parse(catalogText)
      } catch {
        return setErr("Catalogue amounts must be valid JSON, e.g. {\"router\": {\"Fibre 100\": \"800\"}}.")
      }
    }
    const vatRate = Number(f.vat.rate)
    if (!Number.isFinite(vatRate) || vatRate < 0 || vatRate > 1) return setErr("VAT rate is a fraction between 0 and 1 (0.15 = 15%).")
    const out: FeePolicyBody = {
      ...f,
      name: f.name.trim(),
      description: nullIfEmpty(f.description),
      trigger_types: csv(triggersText),
      applies_to_plans: csv(plansText),
      effective_from: nullIfEmpty(f.effective_from),
      effective_to: nullIfEmpty(f.effective_to),
      term_months: Number(f.term_months),
      min_fee_zar: nullIfEmpty(f.min_fee_zar),
      max_fee_zar: nullIfEmpty(f.max_fee_zar),
      auto_approve_waiver_limit_zar: nullIfEmpty(f.auto_approve_waiver_limit_zar),
      grace_period_days: Number(f.grace_period_days) || 0,
      invoice_due_days: Number(f.invoice_due_days) || 14,
      components: f.components.map((c) => ({ ...c, code: c.code.trim(), label: c.label.trim() || c.code.trim(), fixed_amount: c.amount_source === "fixed" ? nullIfEmpty(c.fixed_amount) : null })),
      ...(catalog ? { catalog_amounts: catalog } : {}),
    }
    if (out.trigger_types.length === 0) return setErr("Add at least one trigger.")
    onSave(out)
  }

  const cond = f.router_credit.condition_pct

  return (
    <div className="space-y-5">
      {(err || msg) && <Note tone={err ? "error" : msg!.tone}>{err ?? msg!.text}</Note>}

      <Section title="Basics">
        <Field label="Name">
          <input className={inputClass} value={f.name} onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label="Term (months)">
          <input className={inputClass} inputMode="numeric" value={f.term_months} onChange={(e) => set("term_months", Number(e.target.value) as never)} />
        </Field>
        <Field label="Triggers (comma separated)" hint={`Known: ${TRIGGERS.join(", ")}; any lowercase slug works`}>
          <input className={inputClass} value={triggersText} onChange={(e) => setTriggersText(e.target.value)} />
        </Field>
        <Field label="Applies to plans" hint="Plan ids or names, comma separated. Empty = every plan">
          <input className={inputClass} value={plansText} onChange={(e) => setPlansText(e.target.value)} />
        </Field>
        <Field label="Effective from">
          <input type="date" className={inputClass} value={f.effective_from ?? ""} onChange={(e) => set("effective_from", e.target.value || null)} />
        </Field>
        <Field label="Effective to">
          <input type="date" className={inputClass} value={f.effective_to ?? ""} onChange={(e) => set("effective_to", e.target.value || null)} />
        </Field>
        <Field label="Description" className="sm:col-span-2">
          <textarea className={textareaClass} value={f.description ?? ""} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.is_default} onChange={(e) => set("is_default", e.target.checked)} />
          Default policy
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.is_active} onChange={(e) => set("is_active", e.target.checked)} />
          Active
        </label>
      </Section>

      <section className="space-y-2">
        <h4 className="text-sm font-semibold text-foreground">Recoverable components</h4>
        <p className="text-[11px] text-muted-foreground">The source is only a fallback when a contract has no snapshot: snapshot (flag it), fixed amount, or catalogue by plan. No amounts are invented.</p>
        <div className="space-y-1.5">
          {f.components.map((c, i) => (
            <div key={i} className="flex flex-wrap items-center gap-1.5">
              <input aria-label="Code" className={`${inputClass} w-32`} list="policy-codes" placeholder="code" value={c.code} onChange={(e) => setComp(i, { code: e.target.value })} />
              <input aria-label="Label" className={`${inputClass} w-40`} placeholder="label" value={c.label} onChange={(e) => setComp(i, { label: e.target.value })} />
              <select aria-label="Amount source" className={`${inputClass} w-32`} value={c.amount_source} onChange={(e) => setComp(i, { amount_source: e.target.value as FeeComponent["amount_source"] })}>
                <option value="snapshot">Snapshot</option>
                <option value="fixed">Fixed</option>
                <option value="catalog">Catalogue</option>
              </select>
              {c.amount_source === "fixed" && <input aria-label="Fixed amount" className={`${inputClass} w-28`} inputMode="decimal" placeholder="R" value={c.fixed_amount ?? ""} onChange={(e) => setComp(i, { fixed_amount: e.target.value })} />}
              <label className="flex items-center gap-1 text-xs">
                <input type="checkbox" checked={c.recoverable} onChange={(e) => setComp(i, { recoverable: e.target.checked })} />
                Recoverable
              </label>
              <Button type="button" size="icon-sm" variant="ghost-destructive" aria-label="Remove component" onClick={() => set("components", f.components.filter((_, j) => j !== i))}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
          <datalist id="policy-codes">
            <option value="router" />
            <option value="activation" />
            <option value="installation" />
          </datalist>
          <Button type="button" size="sm" variant="ghost" onClick={() => set("components", [...f.components, { code: "", label: "", amount_source: "snapshot", fixed_amount: null, recoverable: true }])}>
            <Plus className="h-3.5 w-3.5" />
            Add component (router / activation / installation / custom)
          </Button>
        </div>
        {f.components.some((c) => c.amount_source === "catalog") && (
          <Field label="Catalogue amounts (JSON)" hint='{"router": {"Fibre 100": "800", "default": "600"}}'>
            <textarea className={`${textareaClass} font-mono text-xs`} value={catalogText} onChange={(e) => setCatalogText(e.target.value)} />
          </Field>
        )}
      </section>

      <Section title="Amortisation and limits">
        <Field label="Method">
          <select className={inputClass} value={f.method} onChange={(e) => set("method", e.target.value as FeePolicyBody["method"])}>
            <option value="straight_line">Straight line</option>
            <option value="declining">Declining (sum of digits)</option>
            <option value="flat">Flat percent</option>
            <option value="percent_of_remaining_rental">Percent of remaining rental</option>
          </select>
        </Field>
        <Field label="Month rule">
          <select className={inputClass} value={f.month_rule.mode} onChange={(e) => set("month_rule", { ...f.month_rule, mode: e.target.value as "whole_months" | "prorated_days" })}>
            <option value="whole_months">Whole months</option>
            <option value="prorated_days">Prorated by days</option>
          </select>
        </Field>
        {f.month_rule.mode === "whole_months" && (
          <Field label="A started month counts as">
            <select className={inputClass} value={f.month_rule.remaining_rounding ?? "up"} onChange={(e) => set("month_rule", { ...f.month_rule, remaining_rounding: e.target.value as "up" | "down" })}>
              <option value="up">Remaining (up)</option>
              <option value="down">Elapsed (down)</option>
            </select>
          </Field>
        )}
        {f.method === "flat" && (
          <Field label="Flat percent">
            <input className={inputClass} inputMode="decimal" value={f.flat_percent} onChange={(e) => set("flat_percent", e.target.value)} />
          </Field>
        )}
        {f.method === "percent_of_remaining_rental" && (
          <Field label="Rental percent">
            <input className={inputClass} inputMode="decimal" value={f.rental_percent} onChange={(e) => set("rental_percent", e.target.value)} />
          </Field>
        )}
        <Field label="Minimum fee (R)">
          <input className={inputClass} inputMode="decimal" value={f.min_fee_zar ?? ""} onChange={(e) => set("min_fee_zar", e.target.value)} />
        </Field>
        <Field label="Cap / maximum fee (R)">
          <input className={inputClass} inputMode="decimal" value={f.max_fee_zar ?? ""} onChange={(e) => set("max_fee_zar", e.target.value)} />
        </Field>
        <Field label="Grace period (days)" hint="Cooling-off after term start: whole fee waived">
          <input className={inputClass} inputMode="numeric" value={f.grace_period_days} onChange={(e) => set("grace_period_days", Number(e.target.value) as never)} />
        </Field>
      </Section>

      <section className="space-y-2">
        <h4 className="text-sm font-semibold text-foreground">Waivers by reason</h4>
        <div className="space-y-1.5">
          {f.waivers.map((w, i) => (
            <div key={i} className="flex flex-wrap items-center gap-1.5">
              <input aria-label="Reason code" className={`${inputClass} w-40`} placeholder="reason_code" value={w.reason_code} onChange={(e) => setWaiver(i, { reason_code: e.target.value })} />
              <input aria-label="Label" className={`${inputClass} w-44`} placeholder="label" value={w.label} onChange={(e) => setWaiver(i, { label: e.target.value })} />
              <input aria-label="Waive percent" className={`${inputClass} w-20`} inputMode="decimal" placeholder="%" value={w.waive_percent} onChange={(e) => setWaiver(i, { waive_percent: e.target.value })} />
              <select aria-label="Approval tier" className={`${inputClass} w-28`} value={w.required_tier} onChange={(e) => setWaiver(i, { required_tier: e.target.value as FeeWaiverRule["required_tier"] })}>
                <option value="none">Anyone</option>
                <option value="clerk">Clerk</option>
                <option value="admin">Admin</option>
              </select>
              <label className="flex items-center gap-1 text-xs">
                <input type="checkbox" checked={w.evidence_required} onChange={(e) => setWaiver(i, { evidence_required: e.target.checked })} />
                Evidence
              </label>
              <Button type="button" size="icon-sm" variant="ghost-destructive" aria-label="Remove waiver" onClick={() => set("waivers", f.waivers.filter((_, j) => j !== i))}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
          <Button type="button" size="sm" variant="ghost" onClick={() => set("waivers", [...f.waivers, { reason_code: "", label: "", waive_percent: "100", required_tier: "clerk", evidence_required: false }])}>
            <Plus className="h-3.5 w-3.5" />
            Add waiver rule
          </Button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Auto-approve waiver limit (R)" hint="Clerks may waive up to this gross amount for clerk-tier reasons">
            <input className={inputClass} inputMode="decimal" value={f.auto_approve_waiver_limit_zar ?? ""} onChange={(e) => set("auto_approve_waiver_limit_zar", e.target.value)} />
          </Field>
          <label className="flex items-center gap-2 self-end pb-2 text-sm">
            <input type="checkbox" checked={f.allow_self_approval} onChange={(e) => set("allow_self_approval", e.target.checked)} />
            Allow self-approval above the limit
          </label>
        </div>
      </section>

      <section className="space-y-2">
        <h4 className="text-sm font-semibold text-foreground">Router-return credit</h4>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.router_credit.enabled} onChange={(e) => set("router_credit", { ...f.router_credit, enabled: e.target.checked })} />
          Credit the router when it is returned
        </label>
        {f.router_credit.enabled && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Mode">
              <select className={inputClass} value={f.router_credit.mode} onChange={(e) => set("router_credit", { ...f.router_credit, mode: e.target.value as FeePolicyBody["router_credit"]["mode"] })}>
                <option value="offset_router_component">Offset the router component</option>
                <option value="credit_value_by_condition">Credit value by condition</option>
              </select>
            </Field>
            <Field label="Router component code">
              <input className={inputClass} value={f.router_credit.router_component_code} onChange={(e) => set("router_credit", { ...f.router_credit, router_component_code: e.target.value })} />
            </Field>
            {f.router_credit.mode === "credit_value_by_condition" && (
              <div className="grid grid-cols-5 gap-2 sm:col-span-2">
                {Object.keys(cond).map((k) => (
                  <Field key={k} label={`${humanise(k)} %`}>
                    <input className={inputClass} inputMode="decimal" value={cond[k]} onChange={(e) => set("router_credit", { ...f.router_credit, condition_pct: { ...cond, [k]: e.target.value } })} />
                  </Field>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      <Section title="VAT and invoicing">
        <Field label="VAT rate (fraction)" hint="0.15 = 15%">
          <input className={inputClass} inputMode="decimal" value={f.vat.rate} onChange={(e) => set("vat", { ...f.vat, rate: e.target.value })} />
        </Field>
        <Field label="VAT treatment">
          <select className={inputClass} value={f.vat.treatment} onChange={(e) => set("vat", { ...f.vat, treatment: e.target.value as "exclusive" | "inclusive" })}>
            <option value="exclusive">Exclusive</option>
            <option value="inclusive">Inclusive</option>
          </select>
        </Field>
        <Field label="Outstanding balance" hint="Include = shown in total payable; never put on the fee invoice">
          <select className={inputClass} value={f.outstanding_balance} onChange={(e) => set("outstanding_balance", e.target.value as "include" | "exclude")}>
            <option value="include">Include in total payable</option>
            <option value="exclude">Exclude</option>
          </select>
        </Field>
        <Field label="Fee invoice due (days)">
          <input className={inputClass} inputMode="numeric" value={f.invoice_due_days} onChange={(e) => set("invoice_due_days", Number(e.target.value) as never)} />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.auto_invoice} onChange={(e) => set("auto_invoice", e.target.checked)} />
          Auto-invoice (issued immediately)
        </label>
        {f.auto_invoice && (
          <Field label="Auto-invoice stage">
            <select className={inputClass} value={f.auto_invoice_stage} onChange={(e) => set("auto_invoice_stage", e.target.value as "proceed" | "initiate")}>
              <option value="proceed">When the cancellation proceeds</option>
              <option value="initiate">When it is initiated</option>
            </select>
          </Field>
        )}
      </Section>

      <div className="flex justify-end gap-2 border-t border-border pt-3">
        <Button variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" disabled={busy} onClick={submit}>
          {busy ? "Saving…" : "Save policy"}
        </Button>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h4 className="text-sm font-semibold text-foreground">{title}</h4>
      <div className="grid gap-3 sm:grid-cols-2">{children}</div>
    </section>
  )
}
