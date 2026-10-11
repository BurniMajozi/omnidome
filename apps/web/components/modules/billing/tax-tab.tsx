"use client"

/**
 * VAT & tax: whether this business charges VAT, the details printed on its invoices, and where it stands
 * against the South African registration thresholds. Guidance only; the server enforces what is issued.
 */

import { useCallback, useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NotConnected } from "@/components/ui/not-connected"
import {
  getTaxCountries,
  getTaxProfile,
  getTaxStatus,
  invalidateTaxProfile,
  saveTaxProfile,
  useBillingTier,
  type TaxCountry,
  type TaxProfile,
  type TaxStatus,
} from "@/lib/billing-api"
import { fmtMoney } from "@/lib/money"
import type { Loadable } from "@/lib/service-state"
import { ConfirmModal } from "./confirm-modal"
import { Field, Note, inputClass, textareaClass, tierTip, useActionState } from "./shared"

export function TaxTab() {
  const [profile, setProfile] = useState<Loadable<TaxProfile>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((t) => t + 1), [])
  useEffect(() => {
    let off = false
    getTaxProfile().then((l) => !off && setProfile(l))
    return () => {
      off = true
    }
  }, [tick])

  return (
    <div className="space-y-4">
      {profile.state === "ready" && !profile.data.configured && (
        <Note tone="error" className="border-amber-500/40 bg-amber-500/10 text-amber-300">
          <span className="font-medium">Confirm your VAT status.</span> Until you do, invoices add 15% VAT on top of your prices.
        </Note>
      )}
      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Do you charge VAT?</CardTitle>
        </CardHeader>
        <CardContent>
          {profile.state !== "ready" ? (
            <NotConnected loadable={profile} service="Billing" onRetry={reload} />
          ) : (
            <ProfileForm profile={profile.data} onSaved={(p) => { invalidateTaxProfile(); setProfile({ state: "ready", data: p }); setTick((t) => t + 1) }} />
          )}
        </CardContent>
      </Card>
      <StatusCard />
      <RulesCard />
    </div>
  )
}

// ------------------------------------------------------------------ form

function ProfileForm({ profile, onSaved }: { profile: TaxProfile; onSaved: (p: TaxProfile) => void }) {
  const { isAdmin } = useBillingTier()
  const [countries, setCountries] = useState<TaxCountry[]>([])
  const [registered, setRegistered] = useState<boolean | null>(profile.configured ? profile.vat_registered : null)
  const [country, setCountry] = useState(profile.country === "ZA" || !profile.country ? "ZA" : "OTHER")
  const [countryCode, setCountryCode] = useState(profile.country && profile.country !== "ZA" ? profile.country : "")
  const [rate, setRate] = useState(profile.rate_percent !== null && profile.country !== "ZA" ? String(profile.rate_percent) : "")
  const [vatNumber, setVatNumber] = useState(profile.vat_number ?? "")
  const [legalName, setLegalName] = useState(profile.legal_name ?? "")
  const [address, setAddress] = useState(profile.address ?? "")
  const [since, setSince] = useState(profile.registered_since ?? "")
  const [include, setInclude] = useState(profile.configured ? profile.prices_include_vat : true)
  const [confirming, setConfirming] = useState(false)
  const act = useActionState()

  useEffect(() => {
    let off = false
    getTaxCountries().then((l) => !off && l.state === "ready" && setCountries(l.data.countries ?? []))
    return () => {
      off = true
    }
  }, [])

  const za = country === "ZA"
  const zaRate = countries.find((c) => c.code === "ZA")?.default_rate_percent
  const valid =
    registered !== null &&
    (registered === false ||
      (legalName.trim() !== "" &&
        address.trim() !== "" &&
        vatNumber.trim() !== "" &&
        (!za || /^4\d{9}$/.test(vatNumber.trim())) &&
        (za || (/^[A-Za-z]{2}$/.test(countryCode.trim()) && Number(rate) >= 0 && rate.trim() !== ""))))

  const save = async () => {
    if (registered === null) return
    const body = {
      country: registered ? (za ? "ZA" : countryCode.trim().toUpperCase()) : "ZA",
      vat_registered: registered,
      vat_number: registered ? vatNumber.trim() : null,
      ...(registered && !za ? { rate_percent: Number(rate) } : {}),
      prices_include_vat: registered ? include : false,
      legal_name: registered ? legalName.trim() : legalName.trim() || null,
      address: registered ? address.trim() : address.trim() || null,
      registered_since: registered && since ? since : null,
    }
    const r = await act.run("save", () => saveTaxProfile(body), "VAT settings saved.")
    if (r) {
      setConfirming(false)
      onSaved(r)
    }
  }

  const choice = (value: boolean, label: string) => (
    <label className={`flex cursor-pointer items-start gap-2 rounded-md border p-3 text-sm ${registered === value ? "border-primary bg-primary/5" : "border-border"}`}>
      <input type="radio" name="vat-registered" className="mt-1" checked={registered === value} disabled={!isAdmin} onChange={() => setRegistered(value)} />
      <span className="text-foreground">{label}</span>
    </label>
  )

  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-2">
        {choice(true, "Yes, we are a registered VAT vendor")}
        {choice(false, "No, we are not registered for VAT")}
      </div>

      {registered === false && (
        <Note tone="info">You will issue plain invoices with no VAT. You must register if your taxable supplies pass R2.3 million in 12 months.</Note>
      )}

      {registered === true && (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Country">
              <select className={inputClass} value={country} disabled={!isAdmin} onChange={(e) => setCountry(e.target.value)}>
                <option value="ZA">South Africa{zaRate !== undefined ? ` (VAT ${zaRate}%)` : ""}</option>
                <option value="OTHER">Another country</option>
              </select>
            </Field>
            {!za && (
              <>
                <Field label="Country code (2 letters)">
                  <input className={inputClass} maxLength={2} value={countryCode} disabled={!isAdmin} onChange={(e) => setCountryCode(e.target.value.toUpperCase())} />
                </Field>
                <Field label="VAT rate (%)">
                  <input className={inputClass} inputMode="decimal" value={rate} disabled={!isAdmin} onChange={(e) => setRate(e.target.value)} />
                </Field>
              </>
            )}
            <Field label="VAT registration number" hint={za ? "10 digits, starting with 4." : undefined}>
              <input className={inputClass} inputMode={za ? "numeric" : "text"} maxLength={za ? 10 : 30} value={vatNumber} disabled={!isAdmin} onChange={(e) => setVatNumber(za ? e.target.value.replace(/\D/g, "") : e.target.value)} />
            </Field>
            <Field label="Registered name">
              <input className={inputClass} maxLength={150} value={legalName} disabled={!isAdmin} onChange={(e) => setLegalName(e.target.value)} />
            </Field>
            <Field label="VAT registration date">
              <input type="date" className={inputClass} value={since} disabled={!isAdmin} onChange={(e) => setSince(e.target.value)} />
            </Field>
          </div>
          <Field label="Registered address">
            <textarea className={textareaClass} value={address} disabled={!isAdmin} onChange={(e) => setAddress(e.target.value)} />
          </Field>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className={`flex cursor-pointer items-start gap-2 rounded-md border p-3 text-sm ${include ? "border-primary bg-primary/5" : "border-border"}`}>
              <input type="radio" name="vat-include" className="mt-1" checked={include} disabled={!isAdmin} onChange={() => setInclude(true)} />
              <span>Our prices include VAT</span>
            </label>
            <label className={`flex cursor-pointer items-start gap-2 rounded-md border p-3 text-sm ${!include ? "border-primary bg-primary/5" : "border-border"}`}>
              <input type="radio" name="vat-include" className="mt-1" checked={!include} disabled={!isAdmin} onChange={() => setInclude(false)} />
              <span>VAT is added on top</span>
            </label>
          </div>
        </div>
      )}

      {act.msg && !confirming && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
      <Button size="sm" disabled={!isAdmin || !valid || !!act.busy} title={isAdmin ? undefined : tierTip("admin")} onClick={() => { act.clear(); setConfirming(true) }}>
        Save VAT settings
      </Button>

      <ConfirmModal open={confirming} onOpenChange={setConfirming} title="Save VAT settings" confirmLabel="Save" busy={act.busy === "save"} error={act.msg?.tone === "error" ? act.msg.text : null} onConfirm={save}>
        <p>
          {registered ? "From now on your documents will charge VAT as set here." : "From now on your documents will be plain invoices with no VAT."} This applies to documents issued from now on. Invoices already issued are unchanged.
        </p>
      </ConfirmModal>
    </div>
  )
}

// ------------------------------------------------------------------ status

const STATUS_VIEW: Record<string, { label: string; tone: string }> = {
  registered: { label: "Registered", tone: "badge-success" },
  must_register: { label: "Must register", tone: "badge-danger" },
  will_exceed: { label: "Will exceed threshold", tone: "badge-warning" },
  approaching: { label: "Approaching threshold", tone: "badge-warning" },
  may_register: { label: "May register", tone: "badge-info" },
  below_threshold: { label: "Below threshold", tone: "bg-secondary text-muted-foreground" },
  not_applicable: { label: "Not applicable", tone: "bg-secondary text-muted-foreground" },
}

function StatusCard() {
  const [data, setData] = useState<Loadable<TaxStatus>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let off = false
    getTaxStatus().then((l) => !off && setData(l))
    return () => {
      off = true
    }
  }, [tick])

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="text-base">Registration status</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {data.state !== "ready" ? (
          <NotConnected loadable={data} service="Billing" onRetry={() => setTick((t) => t + 1)} />
        ) : !data.data.applicable ? (
          <p className="text-sm text-muted-foreground">{data.data.message}</p>
        ) : (
          <StatusBody s={data.data} />
        )}
      </CardContent>
    </Card>
  )
}

function StatusBody({ s }: { s: TaxStatus }) {
  const view = STATUS_VIEW[s.status] ?? { label: s.status, tone: "bg-secondary text-muted-foreground" }
  const max = s.compulsory_threshold_zar || 1
  const pct = (v: number) => Math.min(100, Math.max(0, (v / max) * 100))
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Badge className={view.tone}>{view.label}</Badge>
        <span className="text-sm text-foreground">{fmtMoney(s.turnover_12m_zar)} invoiced in the last 12 months (excluding VAT)</span>
      </div>
      <div className="space-y-1">
        <div className="relative h-3 w-full overflow-hidden rounded-full bg-secondary">
          <div className="h-full rounded-full bg-primary" style={{ width: `${pct(s.turnover_12m_zar)}%` }} />
          <div className="absolute top-0 h-full w-px bg-foreground/60" style={{ left: `${pct(s.voluntary_threshold_zar)}%` }} />
        </div>
        <div className="relative h-4 text-[11px] text-muted-foreground">
          <span className="absolute -translate-x-1/2" style={{ left: `${Math.min(pct(s.voluntary_threshold_zar), 90)}%` }}>
            Voluntary {fmtMoney(s.voluntary_threshold_zar)}
          </span>
          <span className="absolute right-0">Compulsory {fmtMoney(s.compulsory_threshold_zar)}</span>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">{s.message}</p>
    </>
  )
}

// ------------------------------------------------------------------ rules

function RulesCard() {
  return (
    <Card className="border-border bg-card">
      <CardContent className="pt-6">
        <details>
          <summary className="cursor-pointer text-sm font-semibold text-foreground">VAT rules in short</summary>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-muted-foreground">
            <li>You must register for VAT, and charge it, once your taxable supplies pass R2.3 million in any 12 months. You may register voluntarily above R120,000.</li>
            <li>Apply to SARS within 21 business days of passing the threshold.</li>
            <li>Registered vendors issue tax invoices showing their name, address and VAT number, an invoice number and date, a description, the quantity, the value, the VAT and the total.</li>
            <li>Above R5,000 the invoice must also show the customer&apos;s name and address, and their VAT number if they are a vendor. Up to R5,000 an abridged tax invoice is allowed.</li>
            <li>Businesses that are not registered must not charge VAT. They issue a plain invoice.</li>
            <li>Prices quoted by VAT vendors should include VAT.</li>
          </ul>
          <p className="mt-3 text-sm">
            <a className="text-primary underline-offset-2 hover:underline" href="https://www.sars.gov.za/types-of-tax/value-added-tax/" target="_blank" rel="noopener noreferrer">
              SARS: Register for VAT
            </a>
          </p>
          <p className="mt-2 text-xs text-muted-foreground">General guidance, not tax advice. Thresholds in force from 1 April 2026.</p>
        </details>
      </CardContent>
    </Card>
  )
}
