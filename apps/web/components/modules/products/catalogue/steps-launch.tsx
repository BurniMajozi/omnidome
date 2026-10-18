"use client"

import { Plus, Rocket, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { Definition, IcasaItem, Nature, TestResult } from "@/lib/catalogue-api"
import { Field, STANDARD_TESTS, areaCls, kpiSet, money, selectCls } from "./shared"
import type { StepProps } from "./wizard-types"

const iconDanger = "h-8 w-8 p-0 hover:border-red-500/60 hover:text-red-400"

export const icasaRequired = (nature: Nature, usage: string, d: Definition) =>
  d.readiness.icasa.required ?? (nature === "Digital service" && usage === "Customer-facing")

function addBusinessDays(iso: string, n: number) {
  const d = new Date(`${iso}T12:00:00`)
  let k = 0
  while (k < n) {
    d.setDate(d.getDate() + 1)
    if (d.getDay() !== 0 && d.getDay() !== 6) k++
  }
  return d.toISOString().slice(0, 10)
}

function lodgmentText(name: string, number: string, d: Definition, it: IcasaItem) {
  return [
    "To: tariffs@icasa.org.za",
    `Subject: ${it.kind === "Product" ? "Notification of new product" : "Notification of promotion"} - ${name} (${number})`,
    "",
    "Licensee: [licensee name and licence number]",
    `Product: ${name} (${number})`,
    `Tariff: ${money(d.price)} ${d.recurring ? "per month" : "once-off"}, excluding tax`,
    `Objectives: ${it.objectives || "[required]"}`,
    `Reason(s): ${it.reasons || "[required]"}`,
    `Effective date: ${it.effective || "[required]"}`,
    ...(it.kind === "Promotion" ? [`Promotion period: ${it.promo_start || "[start]"} to ${it.promo_end || "[end]"}`] : []),
    "",
    "Regards,",
    "[name, title, contact]",
  ].join("\n")
}

const newItem = (kind: IcasaItem["kind"], date: string | null): IcasaItem => ({
  id: crypto.randomUUID(), kind, objectives: "", reasons: "", effective: date ?? "", promo_start: date ?? "", promo_end: "", lodged: "", ref: "", ack: false,
})

// ── Step 7: launch route, internal testing, ICASA ────────────────────────────

export function StepLaunch({ form, setDef, preview, notify }: StepProps) {
  const d = form.definition
  const r = d.readiness
  const ic = r.icasa
  const need = icasaRequired(form.nature, form.usage, d)
  const route = r.tests_required && need ? "full" : r.tests_required ? "noicasa" : "direct"
  const patch = (p: Partial<Definition["readiness"]>) => setDef({ readiness: { ...r, ...p } })
  const patchIc = (p: Partial<typeof ic>) => patch({ icasa: { ...ic, ...p } })
  const setRoute = (v: string) => patch({ tests_required: v !== "direct", icasa: { ...ic, required: v === "full" } })
  const today = new Date().toISOString().slice(0, 10)
  const standard = new Set(STANDARD_TESTS[form.nature].map((n) => n.trim().toLowerCase()))
  const isStandard = (name: string) => standard.has(name.trim().toLowerCase())
  const updTest = (i: number, p: Partial<TestResult>) =>
    patch({ tests: r.tests.map((t, k) => (k === i ? { ...t, ...p, date: p.result && p.result !== "Pending" && !t.date ? today : (p.date ?? t.date) } : t)) })
  const updItem = (i: number, p: Partial<IcasaItem>) => patchIc({ items: ic.items.map((t, k) => (k === i ? { ...t, ...p } : t)) })
  const failing = (key: string) => preview?.checks.filter((c) => c.key === key && !c.ok) ?? []

  const routes = [
    ["full", "Full route", "Internal testing and ICASA lodgment"],
    ["noicasa", "No ICASA", "Test internally; nothing to lodge (e.g. equipment, non-telecoms)"],
    ["direct", "Direct to market", "No testing and no lodgment; reasons are recorded"],
  ]
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Launch route, testing and ICASA lodgment</h3>
        <p className="mt-1 text-xs text-muted-foreground">Choose how this product goes to market. Anything you skip needs a recorded reason; anything you keep becomes a gate on the Launch button, enforced by the server.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-3" role="radiogroup" aria-label="Launch route">
        {routes.map(([v, t, s]) => (
          <label key={v} className={`cursor-pointer rounded-lg border p-3 text-xs ${route === v ? "border-primary bg-primary/10" : "border-border"}`}>
            <input type="radio" name="route" className="mr-2" checked={route === v} onChange={() => setRoute(v)} />
            <strong className="text-foreground">{t}</strong>
            <div className="mt-1 text-muted-foreground">{s}</div>
          </label>
        ))}
      </div>

      {r.tests_required ? (
        <div className="space-y-3 rounded-lg border border-border p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-xs font-semibold text-foreground">Internal test results</h4>
            <Button type="button" variant="outline" size="sm" className="text-xs" onClick={() => patch({ tests: [...r.tests, ...STANDARD_TESTS[form.nature].filter((n) => !r.tests.some((t) => t.name === n)).map((name) => ({ name, result: "Pending" as const, tester: "", date: "", notes: "", evidence: "" }))] })}>Add standard test plan</Button>
          </div>
          {r.tests.length === 0 && <p className="text-xs text-amber-400">No test results recorded.</p>}
          {r.tests.map((t, i) => (
            <div key={i} className="rounded-lg border border-border bg-card/60 p-3">
              <div className="grid gap-3 sm:grid-cols-4">
                <Field label={isStandard(t.name) ? "Test (standard plan)" : "Test"} className="sm:col-span-2"><Input value={t.name} readOnly={isStandard(t.name)} onChange={(e) => updTest(i, { name: e.target.value })} className="h-9 text-xs" /></Field>
                <Field label="Result"><select value={t.result} className={selectCls} onChange={(e) => updTest(i, { result: e.target.value as TestResult["result"] })}><option>Pending</option><option>Pass</option><option>Fail</option><option>Waived</option></select></Field>
                <Field label="Date" hint={t.date > today ? "A test date cannot be in the future." : undefined}><Input type="date" max={today} value={t.date} onChange={(e) => updTest(i, { date: e.target.value })} className="h-9 text-xs" /></Field>
                <Field label="Tested by"><Input value={t.tester} onChange={(e) => updTest(i, { tester: e.target.value })} className="h-9 text-xs" /></Field>
                <Field label="Evidence (file name or link)" className="sm:col-span-2"><Input value={t.evidence} onChange={(e) => updTest(i, { evidence: e.target.value })} className="h-9 text-xs" /></Field>
                <div className="flex items-end justify-end"><Button type="button" variant="outline" size="sm" className={iconDanger} aria-label="Remove test" onClick={() => patch({ tests: r.tests.filter((_, k) => k !== i) })}><Trash2 className="h-3.5 w-3.5" /></Button></div>
                <Field label={t.result === "Waived" || t.result === "Fail" ? "Notes (required for a waived or failed test)" : "Notes"} className="sm:col-span-4"><textarea rows={2} value={t.notes} onChange={(e) => updTest(i, { notes: e.target.value })} className={areaCls} /></Field>
              </div>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" className="gap-1.5 text-xs" onClick={() => patch({ tests: [...r.tests, { name: "", result: "Pending", tester: "", date: "", notes: "", evidence: "" }] })}><Plus className="h-3.5 w-3.5" /> Add test</Button>
          {failing("testing")[0]?.detail && <p className="text-xs text-amber-400">{failing("testing")[0].detail}</p>}
        </div>
      ) : (
        <div className="rounded-lg border border-border p-4">
          <Field label="Reason internal testing is not needed (recorded for audit)"><textarea rows={2} value={r.tests_exempt_reason} onChange={(e) => patch({ tests_exempt_reason: e.target.value })} className={areaCls} /></Field>
        </div>
      )}

      <div className="space-y-3 rounded-lg border border-border p-4">
        {need ? (
          <>
            <h4 className="text-xs font-semibold text-foreground">ICASA lodgment</h4>
            <p className="text-[11px] text-muted-foreground">Notifications are emailed to tariffs@icasa.org.za. OmniDome drafts the text; nothing is sent from here. No official ICASA form was found: the filing is an email with objectives, reasons, effective date and, for promotions, the promotion period.</p>
            <Field label="Minimum notice (business days)" hint="Sources differ (5 or 7 days; an amendment shortens promotions to 5). Confirm against the regulation in force.">
              <select value={ic.notice} className={`${selectCls} w-32`} onChange={(e) => patchIc({ notice: Number(e.target.value) })}>{[5, 7, 10].map((n) => <option key={n}>{n}</option>)}</select>
            </Field>
            {ic.items.map((it, i) => {
              const earliest = it.lodged ? addBusinessDays(it.lodged, ic.notice) : ""
              return (
                <div key={it.id || i} className="rounded-lg border border-border bg-card/60 p-3">
                  <div className="flex items-center justify-between">
                    <strong className="text-xs text-foreground">{it.kind === "Product" ? "New product tariff" : "Promotion"} notification</strong>
                    <Badge variant="outline" className={`text-[10px] ${it.lodged ? "border-emerald-500/40 text-emerald-400" : "border-amber-500/40 text-amber-400"}`}>{!it.lodged ? "Not lodged" : it.ack ? "Acknowledged" : "Lodged"}</Badge>
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <Field label={`Objectives of the ${it.kind === "Product" ? "product" : "promotion"}`} className="sm:col-span-2"><textarea rows={2} value={it.objectives} onChange={(e) => updItem(i, { objectives: e.target.value })} className={areaCls} /></Field>
                    <Field label="Reason(s)" className="sm:col-span-2"><textarea rows={2} value={it.reasons} onChange={(e) => updItem(i, { reasons: e.target.value })} className={areaCls} /></Field>
                    <Field label="Effective date"><Input type="date" value={it.effective} onChange={(e) => updItem(i, { effective: e.target.value })} className="h-9 text-xs" /></Field>
                    {it.kind === "Promotion" && (
                      <>
                        <Field label="Promotion starts"><Input type="date" value={it.promo_start} onChange={(e) => updItem(i, { promo_start: e.target.value })} className="h-9 text-xs" /></Field>
                        <Field label="Promotion ends"><Input type="date" value={it.promo_end} onChange={(e) => updItem(i, { promo_end: e.target.value })} className="h-9 text-xs" /></Field>
                      </>
                    )}
                    <Field label="Date lodged with ICASA" hint={it.lodged > today ? "Lodged dates are in the past or today. Enter the date you actually sent it." : undefined}><Input type="date" max={today} value={it.lodged} onChange={(e) => updItem(i, { lodged: e.target.value })} className="h-9 text-xs" /></Field>
                    <Field label="Reference / email proof"><Input value={it.ref} placeholder="e.g. sent-mail message ID" onChange={(e) => updItem(i, { ref: e.target.value })} className="h-9 text-xs" /></Field>
                    <label className="flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={it.ack} disabled={!it.lodged} onChange={(e) => updItem(i, { ack: e.target.checked })} /> ICASA acknowledgement received</label>
                  </div>
                  {earliest && (
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                      <span>Earliest permitted go-live at {ic.notice} business days: <strong className="text-foreground">{earliest}</strong> (weekends excluded; public holidays not modelled).</span>
                      {it.effective !== earliest && <Button type="button" variant="outline" size="sm" className="h-7 text-[11px]" onClick={() => updItem(i, { effective: earliest })}>Use this as the effective date</Button>}
                      {it.effective && it.effective < earliest && <span className="text-amber-400">The effective date is before the notice period ends. Edit either date to continue; nothing is locked.</span>}
                    </div>
                  )}
                  <details className="mt-2 text-xs">
                    <summary className="cursor-pointer text-primary">Lodgment email draft</summary>
                    <textarea readOnly rows={9} value={lodgmentText(form.name, form.product_number || "[number assigned on save]", d, it)} className={`${areaCls} mt-2 font-mono`} />
                    <Button type="button" variant="outline" size="sm" className="mt-2 text-xs" onClick={() => navigator.clipboard?.writeText(lodgmentText(form.name, form.product_number, d, it)).then(() => notify("Draft copied. Nothing was sent to ICASA."), () => notify("Copy unavailable. Select the text and copy it."))}>Copy draft</Button>
                  </details>
                  <div className="mt-2 flex justify-end"><Button type="button" variant="outline" size="sm" className={iconDanger} aria-label="Remove notification" onClick={() => patchIc({ items: ic.items.filter((_, k) => k !== i) })}><Trash2 className="h-3.5 w-3.5" /></Button></div>
                </div>
              )
            })}
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" className="gap-1.5 text-xs" disabled={ic.items.some((x) => x.kind === "Product")} onClick={() => patchIc({ items: [...ic.items, newItem("Product", d.launch_date)] })}><Plus className="h-3.5 w-3.5" /> Product lodgment</Button>
              <Button type="button" variant="outline" size="sm" className="gap-1.5 text-xs" onClick={() => patchIc({ items: [...ic.items, newItem("Promotion", d.launch_date)] })}><Plus className="h-3.5 w-3.5" /> Promotion lodgment</Button>
            </div>
            {preview?.checks.filter((c) => c.key.startsWith("icasa") && !c.ok).map((c, i) => <p key={i} className="text-xs text-amber-400">{c.label}: {c.detail}</p>)}
          </>
        ) : (
          <Field label="Reason no ICASA lodgment is needed (recorded for audit)"><textarea rows={2} value={ic.exempt_reason} onChange={(e) => patchIc({ exempt_reason: e.target.value })} className={areaCls} /></Field>
        )}
      </div>
    </div>
  )
}

// ── Step 8: review and launch ────────────────────────────────────────────────

/** Which wizard step fixes each launch check. */
const FIX_STEP: Record<string, number> = { definition: 0, classification: 0, costs: 1, sourcing: 1, components: 2, price: 3, testing: 6, icasa: 6, icasa_product: 6, icasa_promotion: 6 }

export function StepReview({ form, preview, products, onLaunch, launching, previewError, onRetry, goto }: StepProps & {
  onLaunch: () => void; launching: boolean; previewError: string | null; onRetry: () => void; goto: (step: number) => void
}) {
  const d = form.definition
  const checks = preview?.checks ?? []
  const ok = preview?.ready_to_launch ?? false
  const active = form.status === "active"
  const kpis = kpiSet(form.nature).filter((k) => d.research.kpis.includes(k.key))
  const e = preview?.economics
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Review and launch</h3>
        <p className="mt-1 text-xs text-muted-foreground">The server checks every requirement below before it allows launch.</p>
      </div>
      <div className="rounded-lg border border-border bg-card/60 p-4">
        <div className="font-mono text-[11px] text-primary">{form.custom_number || form.product_number || "Number assigned on save"}</div>
        <h2 className="text-base font-semibold text-foreground">{d.customer_name || form.name || "Unnamed product"}</h2>
        <p className="text-xs text-muted-foreground">{[form.category, form.range].filter(Boolean).join(" › ") || "Unclassified"} · {form.nature} · {form.usage}</p>
        <p className="mt-2 text-xs text-muted-foreground">{d.description || "Description required"}</p>
        <div className="mt-3 grid gap-2 text-xs sm:grid-cols-3">
          <div><span className="text-muted-foreground">Price</span><div className="font-medium text-foreground">{Number(d.price) > 0 ? `${money(d.price)}${d.recurring ? " /mo" : ""}` : "Not set"}</div></div>
          <div><span className="text-muted-foreground">Costs / inclusions</span><div className="font-medium text-foreground">{d.costs.length} lines · {d.components.length} included</div></div>
          <div><span className="text-muted-foreground">Enabled fees</span><div className="font-medium text-foreground">{d.fees.filter((f) => f.enabled).length}</div></div>
        </div>
        {d.components.length > 0 && <p className="mt-2 text-[11px] text-muted-foreground">Includes: {d.components.map((c) => `${c.qty} × ${products.find((p) => p.id === c.product_id)?.name ?? "unavailable product"}`).join(", ")}</p>}
        {preview?.margin_matrix && preview.margin_matrix.suppliers.length > 0 && (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-[11px]">
              <thead><tr className="text-muted-foreground"><th className="py-1 pr-3 font-normal">Supplier</th><th className="px-2 font-normal">Unit cost</th><th className="px-2 font-normal">Margin</th>{preview.margin_matrix.channels.map((c) => <th key={c.channel} className="px-2 font-normal">{c.channel}</th>)}</tr></thead>
              <tbody>
                {preview.margin_matrix.suppliers.map((s) => (
                  <tr key={s.supplier_id ?? "none"} className="border-t border-border">
                    <td className="py-1 pr-3 text-foreground">{s.name ?? "No supplier"}{s.preferred ? " ★" : ""}</td>
                    <td className="px-2">{s.unit_cost === null ? "—" : money(s.unit_cost)}</td>
                    <td className="px-2">{s.complete && s.margin_pct !== null ? `${s.margin_pct.toFixed(1)}%` : "—"}</td>
                    {preview.margin_matrix!.channels.map((c) => { const x = s.channels[c.channel]; return <td key={c.channel} className="px-2">{s.complete && x && x.margin_pct !== null ? `${x.margin_pct.toFixed(1)}%` : "—"}</td> })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {(d.barcode.value || d.identifiers.length > 0 || d.provisioning.protocol !== "None") && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            {[d.barcode.value && `Barcode ${d.barcode.value}`, d.identifiers.length > 0 && `Captures ${d.identifiers.join(" and ").toLowerCase()} per unit`, d.provisioning.protocol !== "None" && `Provisioned by ${d.provisioning.protocol}${d.provisioning.profile ? ` (${d.provisioning.profile})` : ""}`].filter(Boolean).join(" · ")}
          </p>
        )}
        {e && <p className="mt-2 text-[11px] text-muted-foreground">{e.complete ? `${e.horizon}-month contribution ${money(e.profit)} (${e.margin_pct == null ? "N/A" : `${e.margin_pct}%`} margin)` : "Margin not shown: the cost sheet is incomplete."}</p>}
      </div>

      <div className="rounded-lg border border-border p-4">
        <h4 className="text-xs font-semibold text-foreground">Product performance</h4>
        <div className="mt-2 grid gap-2 sm:grid-cols-3">
          {kpis.length === 0 && <p className="text-xs text-muted-foreground">No KPIs selected. Choose them in the Research step.</p>}
          {kpis.map((k) => (
            <div key={k.key} className="rounded-md border border-border p-2.5">
              <div className="text-lg font-semibold text-muted-foreground">—</div>
              <div className="text-xs text-foreground">{k.label}</div>
              <div className="text-[11px] text-muted-foreground">{k.source} · {active ? "feed not connected yet" : "available after launch"}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-border p-4" id="launch-card">
        <h4 className="text-xs font-semibold text-foreground">Launch requirements</h4>
        <ul className="mt-2 space-y-1">
          {checks.length === 0 && !previewError && <li className="text-xs text-muted-foreground">Checking…</li>}
          {previewError && (
            <li className="flex flex-wrap items-center gap-2 text-xs text-red-400" role="alert">
              Could not check the launch requirements ({previewError}).{checks.length > 0 ? " The list below may be out of date." : ""}
              <Button type="button" variant="outline" size="sm" className="h-7 text-[11px]" onClick={onRetry}>Retry</Button>
            </li>
          )}
          {checks.map((c, i) => (
            <li key={i} className={`flex flex-wrap items-center gap-2 text-xs ${c.ok ? "text-emerald-400" : "text-amber-400"}`}>
              <span>{c.ok ? "✓" : "○"} {c.label}{c.detail && <span className="text-muted-foreground"> · {c.detail}</span>}</span>
              {!c.ok && FIX_STEP[c.key] !== undefined && (
                <button type="button" className="text-[11px] font-medium text-primary underline" onClick={() => goto(FIX_STEP[c.key])}>Fix in step {FIX_STEP[c.key] + 1} →</button>
              )}
            </li>
          ))}
        </ul>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground">{active ? "This product is already active." : ok ? "All requirements met." : "Complete the open items to unlock launch."}</span>
          <Button type="button" className="gap-1.5" disabled={!ok || active || launching || !!previewError} onClick={onLaunch}><Rocket className="h-4 w-4" /> {launching ? "Launching…" : "Launch product"}</Button>
        </div>
      </div>
    </div>
  )
}
