"use client"

import { useEffect, useState } from "react"
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { getProfitability, type Profitability } from "@/lib/supplier-api"
import { useIsClient } from "@/lib/use-is-client"
import { money } from "./catalogue/shared"

/** Unit economics of the launched product mix, with the preferred and best-performing supplier per product. */
export function ProfitabilityPanel() {
  const isClient = useIsClient()
  const [data, setData] = useState<Profitability | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { getProfitability().then(setData).catch((e) => setError(e instanceof Error ? e.message : "Could not load profitability")) }, [])

  const rows = data?.products ?? []
  const chart = rows.filter((r) => r.cost_complete && r.margin_pct !== null).map((r) => ({ name: r.product_number, label: r.name, margin: r.margin_pct as number })).sort((a, b) => b.margin - a.margin)
  const mix = data?.mix
  return (
    <Card className="border-border bg-card">
      <CardHeader><CardTitle className="text-base">Profitability of the product mix</CardTitle></CardHeader>
      <CardContent className="space-y-5">
        {error ? <p className="text-sm text-red-400" role="alert">{error}</p> : !data ? <p className="text-sm text-muted-foreground">Loading profitability…</p> : rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No launched products yet. Margins appear here once products are launched with their costs.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Launched products" value={String(mix?.products ?? 0)} hint={`${mix?.costed ?? 0} fully costed`} />
              <Stat label="Mix margin (weighted)" value={mix?.weighted_margin_pct == null ? "—" : `${mix.weighted_margin_pct}%`} hint={mix?.weighted_products ? `By units dispatched, ${mix.weighted_products} product(s)` : "No dispatch volumes yet"} />
              <Stat label="Mix margin (unweighted)" value={mix?.unweighted_margin_pct == null ? "—" : `${mix.unweighted_margin_pct}%`} hint="Every costed product counts equally" />
              <Stat label="Products below 20% margin" value={String(rows.filter((r) => r.cost_complete && r.margin_pct !== null && r.margin_pct < 20).length)} hint="Review price or supplier" />
            </div>
            {chart.length > 0 && isClient && (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="name" stroke="#9ca3af" fontSize={11} />
                    <YAxis stroke="#9ca3af" fontSize={11} tickFormatter={(v) => `${v}%`} />
                    <Tooltip contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }} formatter={(v: number) => `${v}%`} labelFormatter={(l, p) => (p?.[0]?.payload?.label ? `${l} · ${p[0].payload.label}` : l)} />
                    <Bar dataKey="margin" radius={[4, 4, 0, 0]}>{chart.map((c) => <Cell key={c.name} fill={c.margin < 0 ? "#ef4444" : c.margin < 20 ? "#f59e0b" : "#10b981"} />)}</Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-xs">
                <thead><tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">Product</th><th className="py-2 pr-3 text-right font-medium">Price</th><th className="py-2 pr-3 text-right font-medium">Direct cost</th>
                  <th className="py-2 pr-3 text-right font-medium">Margin</th><th className="py-2 pr-3 font-medium">Preferred supplier</th><th className="py-2 font-medium">Best performing supplier</th></tr></thead>
                <tbody className="divide-y divide-border/60">
                  {rows.map((r) => {
                    const switchSuggested = r.best_supplier && r.preferred_supplier && r.best_supplier.name !== r.preferred_supplier
                    return (
                      <tr key={r.id}>
                        <td className="py-2 pr-3"><span className="font-mono text-primary">{r.product_number}</span> {r.name}</td>
                        <td className="py-2 pr-3 text-right">{r.price > 0 ? `${money(r.price)}${r.recurring ? " /mo" : ""}` : "—"}</td>
                        <td className="py-2 pr-3 text-right">{r.cost_complete ? `${money(r.recurring_cost)}${r.recurring_cost ? " /mo" : ""}${r.upfront_cost ? ` + ${money(r.upfront_cost)}` : ""}` : <span className="text-amber-400">Incomplete</span>}</td>
                        <td className={`py-2 pr-3 text-right font-medium ${r.margin_pct !== null && r.cost_complete ? (r.margin_pct < 0 ? "text-red-400" : r.margin_pct < 20 ? "text-amber-400" : "text-emerald-400") : ""}`}>{r.cost_complete && r.margin_pct !== null ? `${r.margin_pct}%` : "—"}</td>
                        <td className="py-2 pr-3">{r.preferred_supplier ?? <span className="text-muted-foreground">None</span>}</td>
                        <td className="py-2">{r.best_supplier ? <>{r.best_supplier.name}<span className="text-muted-foreground"> · {money(r.best_supplier.unit_cost)}{r.best_supplier.score !== null ? ` · score ${r.best_supplier.score.toFixed(0)}` : " · lowest cost"}</span>{switchSuggested && <span className="ml-1 text-amber-400">consider switching</span>}</> : <span className="text-muted-foreground">—</span>}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-muted-foreground">{mix?.note} Costs and margins are visible to inventory managers only.</p>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-border bg-card/60 p-3">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-xl font-semibold text-foreground">{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  )
}
