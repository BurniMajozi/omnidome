"use client"
import { useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { TenantUsage } from "@/lib/platform-pricing"
import { workApi, usd, type WorkAgent, type WorkBudget } from "@/lib/agent-work-api"

export function AgentWorkBudgets({ credits, creditError, budget, agents, refresh }: {
  credits: TenantUsage | null; creditError: string; budget: WorkBudget & { can_edit?: boolean }; agents: WorkAgent[]; refresh: () => Promise<void>
}) {
  const [caps, setCaps] = useState<Record<string, string>>({})
  const [tenantCap, setTenantCap] = useState<string | null>(null)
  const [busy, setBusy] = useState("")
  const [error, setError] = useState("")
  const [readiness, setReadiness] = useState<Record<string, any>>({})
  async function save(id: string) {
    setBusy(id); setError("")
    try {
      if (id === "tenant") await workApi("/budgets/tenant", { monthly_budget_usd: (tenantCap ?? String(budget.monthly_budget_usd ?? "")).trim() ? Number(tenantCap ?? budget.monthly_budget_usd) : null }, "PUT")
      else { const agent = agents.find(a => a.id === id)!; await workApi(`/registered/${agent.employee_id}/budget`, { monthly_budget_usd: Number(caps[id] ?? agent.monthly_budget_usd) }, "PUT") }
      await refresh()
    } catch (e) { setError(e instanceof Error ? e.message : "Budget update failed") }
    finally { setBusy("") }
  }
  async function check(agent: WorkAgent) {
    setBusy(agent.id); setError("")
    try { const result = await workApi(`/registered/${agent.employee_id}/readiness`); setReadiness(r => ({ ...r, [agent.id]: result })) }
    catch (e) { setError(e instanceof Error ? e.message : "Context check failed") }
    finally { setBusy("") }
  }
  return <section className="rounded-xl border bg-card p-4 space-y-5" aria-label="Credits and agent budgets">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-base font-semibold">Credits & budgets</h3><Link href="/platform-billing" className="text-sm text-primary">Billing, usage & top-ups →</Link></div>
    {credits ? <div className="space-y-2">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[["Included credits", credits.policy.monthly_credits], ["Used this period", credits.used], ["Prepaid remaining", credits.credit_wallet?.purchased_remaining ?? 0], [credits.charges_enabled ? "Available credits" : "Illustrated remaining", credits.credit_wallet?.available ?? credits.remaining]].map(([label, value]) => <div key={String(label)} className="rounded-lg bg-muted p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-xl font-semibold">{Number(value).toLocaleString("en-ZA")}</p></div>)}</div>
      <progress className="w-full h-2" aria-label="Included AI credit usage" max={Math.max(1, credits.policy.monthly_credits)} value={Math.min(credits.used, credits.policy.monthly_credits)} />
      <p className="text-xs text-muted-foreground">{credits.credit_wallet?.reserved ?? 0} credits reserved for running work · allowance resets {new Date(credits.period_end).toLocaleDateString("en-ZA")}. {credits.charges_enabled ? "This is the shared tenant billing wallet." : "Shadow metering is active; this illustrates usage and is not a published selling price."}</p>
      {!credits.credit_wallet?.topup_policy?.enabled && <p className="text-xs text-muted-foreground">Credit purchases open when the Platform Owner publishes pricing. The minimum top-up is R{credits.credit_wallet?.topup_policy?.minimum_zar ?? "50"}.</p>}
      {Boolean(credits.by_panel?.length) && <details className="text-sm"><summary className="cursor-pointer">Usage by panel</summary><div className="mt-2 grid gap-2 sm:grid-cols-2">{credits.by_panel?.map(p => <p key={p.panel} className="rounded border p-2 text-xs">{p.panel.replaceAll("_", " ")} · {p.credits.toLocaleString()} credits · {p.operations} operations · {p.running} running</p>)}</div></details>}
    </div> : <p role="status" className="text-sm text-muted-foreground">{creditError || "Loading billing credit balance…"} <Button size="sm" variant="link" onClick={() => void refresh()}>Refresh</Button></p>}
    <div className="border-t pt-4 space-y-3">
      <h4 className="text-sm font-medium">Spend ceilings</h4><p className="text-xs text-muted-foreground">Provider spend is measured in USD; billing credits are a separate allowance. These controls are not a credit-to-dollar exchange rate. Run ceilings are checked between turns.</p>
      <div className="flex flex-wrap items-end gap-3"><div><p className="text-xs">Tenant month: {usd(budget.month_spend_usd)} / {budget.monthly_budget_usd === null ? "no monthly cap" : usd(budget.monthly_budget_usd)}</p><p className="text-xs text-muted-foreground">Today: {usd(budget.day_spend_usd ?? 0)}{budget.daily_budget_usd ? ` / ${usd(budget.daily_budget_usd)}` : ""}</p></div>
        {budget.can_edit ? <><label className="text-xs">Tenant monthly ceiling (USD)<Input className="mt-1 w-40" type="number" min="0" max="100000" step="0.01" value={tenantCap ?? String(budget.monthly_budget_usd ?? "")} onChange={e => setTenantCap(e.target.value)} placeholder="No cap" /></label><Button size="sm" variant="outline" disabled={busy !== ""} onClick={() => void save("tenant")}>Save</Button></> : <span className="text-xs text-muted-foreground">Tenant ceiling is set by the Platform Owner.</span>}
      </div>
      {agents.map(agent => <div key={agent.id} className="rounded-lg border p-3 space-y-2"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-medium">{agent.name}</p><p className="text-xs text-muted-foreground">{agent.role} · {usd(agent.month_spend_usd)} this month</p></div><div className="flex flex-wrap items-end gap-2"><Button size="sm" variant="outline" disabled={busy !== ""} onClick={() => void check(agent)}>Check context</Button><label className="text-xs">Agent monthly ceiling (USD)<Input className="mt-1 w-28" type="number" min="0" max="10000" step="0.01" value={caps[agent.id] ?? String(agent.monthly_budget_usd)} onChange={e => setCaps(c => ({ ...c, [agent.id]: e.target.value }))} /></label><Button size="sm" variant="outline" disabled={busy !== ""} onClick={() => void save(agent.id)}>Save</Button></div></div>
        {readiness[agent.id] && <p className="text-xs text-muted-foreground">Memory: {readiness[agent.id].memory_status} · Skills: {readiness[agent.id].skills?.join(", ") || "none"} · KPI: {readiness[agent.id].kpi_status} · {readiness[agent.id].read_only_tools?.length || 0} read-only tools.</p>}
      </div>)}
    </div>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
  </section>
}
