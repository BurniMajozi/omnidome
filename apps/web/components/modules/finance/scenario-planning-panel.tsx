"use client"

import { useMemo, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { formatCurrency, formatPercent } from "./utils"

type ScenarioPlanningProps = {
  baseRevenue: number
  baseOpex: number
  baseCapex: number
  baseDepreciation: number
  baseInterest: number
  taxRate: number
}

type SliderFieldProps = {
  label: string
  value: number
  min: number
  max: number
  step: number
  suffix?: string
  onChange: (value: number) => void
}

function SliderField({ label, value, min, max, step, suffix, onChange }: SliderFieldProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-foreground">{label}</span>
        <span className="text-sm text-muted-foreground">{value}{suffix}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full accent-emerald-500"
      />
    </div>
  )
}

export function ScenarioPlanningPanel({
  baseRevenue,
  baseOpex,
  baseCapex,
  baseDepreciation,
  baseInterest,
  taxRate,
}: ScenarioPlanningProps) {
  const [revenueGrowth, setRevenueGrowth] = useState(6)
  const [opexChange, setOpexChange] = useState(-3)
  const [capexChange, setCapexChange] = useState(5)
  const [churnDelta, setChurnDelta] = useState(-0.4)

  const scenario = useMemo(() => {
    const revenue = baseRevenue * (1 + revenueGrowth / 100)
    const opex = baseOpex * (1 + opexChange / 100)
    const capex = baseCapex * (1 + capexChange / 100)
    const depreciation = baseDepreciation * (1 + capexChange / 100 * 0.4)
    const ebitda = revenue - opex
    const ebit = ebitda - depreciation
    const taxable = Math.max(0, ebit - baseInterest)
    const tax = taxable * taxRate
    const freeCashFlow = ebitda - capex - baseInterest - tax

    return {
      revenue,
      opex,
      capex,
      ebitda,
      ebit,
      freeCashFlow,
    }
  }, [baseRevenue, baseOpex, baseCapex, baseDepreciation, baseInterest, taxRate, revenueGrowth, opexChange, capexChange])

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="border-border bg-card lg:col-span-2">
        <CardHeader>
          <CardTitle className="text-base">Scenario Planning Sliders</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <SliderField label="Revenue Growth" value={revenueGrowth} min={-10} max={20} step={0.5} suffix="%" onChange={setRevenueGrowth} />
          <SliderField label="Opex Change" value={opexChange} min={-15} max={10} step={0.5} suffix="%" onChange={setOpexChange} />
          <SliderField label="Capex Change" value={capexChange} min={-20} max={20} step={1} suffix="%" onChange={setCapexChange} />
          <SliderField label="Churn Delta" value={churnDelta} min={-2} max={3} step={0.1} suffix=" pts" onChange={setChurnDelta} />
          <div className="rounded-lg border border-border bg-secondary/40 p-3 text-xs text-muted-foreground">
            Scenario uses inputs from Sales, Billing, Network, and CRM. Adjustments are isolated for reforecasting.
          </div>
        </CardContent>
      </Card>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Scenario Output</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">EBITA</span>
            <span className="text-sm font-semibold text-foreground">{formatCurrency(scenario.ebitda)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">EBIT</span>
            <span className="text-sm font-semibold text-foreground">{formatCurrency(scenario.ebit)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Free Cash Flow</span>
            <span className="text-sm font-semibold text-foreground">{formatCurrency(scenario.freeCashFlow)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Churn Impact</span>
            <Badge className={churnDelta <= 0 ? "bg-emerald-500/20 text-emerald-400" : "bg-amber-500/20 text-amber-400"}>
              {churnDelta <= 0 ? "Improving" : "Rising"}
            </Badge>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border bg-card lg:col-span-3">
        <CardHeader>
          <CardTitle className="text-base">Budget vs Reforecast</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[720px]">
              <thead>
                <tr className="border-b border-border bg-secondary/50">
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Metric</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-muted-foreground">Budget</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-muted-foreground">Reforecast</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-muted-foreground">Variance</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { label: "Revenue", budget: baseRevenue, forecast: scenario.revenue },
                  { label: "Opex", budget: baseOpex, forecast: scenario.opex },
                  { label: "EBITA", budget: baseRevenue - baseOpex, forecast: scenario.ebitda },
                  { label: "EBIT", budget: baseRevenue - baseOpex - baseDepreciation, forecast: scenario.ebit },
                  { label: "Free Cash Flow", budget: baseRevenue - baseOpex - baseCapex - baseInterest, forecast: scenario.freeCashFlow },
                ].map((row) => {
                  const variance = row.forecast - row.budget
                  const variancePct = row.budget === 0 ? 0 : (variance / row.budget) * 100
                  return (
                    <tr key={row.label} className="border-b border-border last:border-0">
                      <td className="px-4 py-3 text-sm text-foreground">{row.label}</td>
                      <td className="px-4 py-3 text-right text-sm text-foreground">{formatCurrency(row.budget)}</td>
                      <td className="px-4 py-3 text-right text-sm text-foreground">{formatCurrency(row.forecast)}</td>
                      <td className="px-4 py-3 text-right text-sm text-foreground">{formatPercent(variancePct)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
