"use client"

import { Button } from "@/components/ui/button"
import { catalog, bundleSelection, startCheckout } from "@/lib/platform-pricing"

const descriptions = {
  starter: "Start with CRM for one person.",
  growth: "CRM and sales for a small team.",
  professional: "Run customer, sales and billing operations together.",
  enterprise: "Add retention, network operations and compliance.",
}
const money = (value: number) => `R${value.toLocaleString("en-GB", { minimumFractionDigits: value % 1 ? 2 : 0, maximumFractionDigits: 2 })}`

export function BundlePlans({ period, onPeriodChange, onCustomize }: {
  period: "monthly" | "annually"
  onPeriodChange: (period: "monthly" | "annually") => void
  onCustomize: () => void
}) {
  const annual = period === "annually"
  const periodicPrice = (monthly: number) => Number((monthly * (annual ? 1 - catalog.annual_discount_percent / 100 : 1)).toFixed(2))
  return <section className="space-y-8">
    <div className="space-y-4 text-center">
      <h1 className="text-3xl font-bold sm:text-4xl">Choose your platform bundle</h1>
      <p className="mx-auto max-w-2xl text-muted-foreground">Start small or bring your operations together. Your plan sets the panels and seats available to your organisation.</p>
      <div role="group" aria-label="Billing period" className="inline-flex flex-wrap justify-center gap-2 rounded-xl border p-1">
        <Button variant={annual ? "ghost" : "secondary"} aria-pressed={!annual} onClick={() => onPeriodChange("monthly")}>Pay monthly</Button>
        <Button variant={annual ? "secondary" : "ghost"} aria-pressed={annual} onClick={() => onPeriodChange("annually")}>Pay annually · save {catalog.annual_discount_percent}%</Button>
      </div>
      <p className="text-sm text-muted-foreground">Prices exclude VAT. Annual plans are paid upfront; the monthly equivalent is shown below.</p>
    </div>
    <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
      {(["starter", "growth", "professional", "enterprise"] as const).map(id => {
        const bundle = catalog.bundles[id]
        const price = periodicPrice(bundle.monthly_price)
        return <article key={id} className="flex min-w-0 flex-col rounded-2xl border bg-card p-5 sm:p-6">
          <h2 className="text-2xl font-semibold">{bundle.name}</h2>
          <p className="mt-2 min-h-12 text-sm text-muted-foreground">{descriptions[id]}</p>
          <p className="mt-5 text-3xl font-bold">{price === 0 ? "Free" : money(price)}{price > 0 && <span className="text-sm font-normal text-muted-foreground"> / month</span>}</p>
          <p className="mt-2 text-sm text-muted-foreground">{price === 0 ? "No software fee for the included seat" : annual ? `${money(Number((price * 12).toFixed(2)))} paid yearly, excluding VAT` : "Billed monthly, excluding VAT"}</p>
          <p className="mt-4 text-sm">{bundle.seats} included {bundle.seats === 1 ? "seat" : "seats"} · {bundle.credits.toLocaleString("en-GB")} AI credits / month</p>
          <p className="mt-1 text-xs text-muted-foreground">Additional seats {money(periodicPrice(bundle.extra_seat_price))} / seat / month</p>
          <Button className="my-5 w-full" onClick={() => startCheckout(bundleSelection(id, period))}>Choose {bundle.name}</Button>
          <p className="mb-3 text-sm font-medium">Included panels</p>
          <ul className="space-y-2 text-sm text-muted-foreground">{bundle.modules.map(module => <li key={module}>{catalog.modules.find(row => row.id === module)?.name}</li>)}</ul>
        </article>
      })}
    </div>
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border p-5">
      <div><h2 className="font-semibold">Prefer individual panels?</h2><p className="text-sm text-muted-foreground">Build a modular plan and review its total before checkout.</p></div>
      <Button variant="outline" onClick={onCustomize}>Build a modular plan</Button>
    </div>
    <p className="text-sm text-muted-foreground">AI usage is currently measured in shadow mode with no credit deductions or overage charges. Managed email, social connections, research and voice capacity are separate from software access.</p>
  </section>
}
