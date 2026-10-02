/**
 * Pure helpers for the Finance screen: role tiers (UI hints only), journal
 * balance in integer cents, period helpers and the scenario base. No imports.
 */

const FIN_ADMIN = ["platform_admin", "super_admin", "owner", "org_admin", "admin", "tenant_admin", "billing_admin", "finance_admin", "finance_manager"]
const FIN_CLERK = ["finance", "accountant", "bookkeeper", "finance_clerk", "manager"]

export type FinanceTier = "admin" | "clerk" | "reader" | "none"

export function financeTier(roles: string[] | null | undefined): FinanceTier {
  if (!roles || roles.length === 0) return "none"
  const r = roles.map((x) => x.toLowerCase())
  if (r.some((x) => FIN_ADMIN.includes(x))) return "admin"
  if (r.some((x) => FIN_CLERK.includes(x))) return "clerk"
  return "reader"
}
export const isFinanceAdmin = (roles: string[] | null | undefined) => financeTier(roles) === "admin"
export const isFinanceClerk = (roles: string[] | null | undefined) => {
  const t = financeTier(roles)
  return t === "admin" || t === "clerk"
}

/** Debit / credit totals in integer cents (float input is rounded per line). */
export function journalTotals(lines: Array<{ debit?: unknown; credit?: unknown }>): { debit: number; credit: number; balanced: boolean } {
  const c = (v: unknown) => {
    const n = typeof v === "string" && v.trim() ? Number(v) : v === undefined ? 0 : v
    if (typeof n !== "number" || !Number.isFinite(n) || n < 0) return NaN
    const decimal = /^(\d+)(?:\.(\d+))?$/.exec(String(v ?? 0).trim())
    if (!decimal) return Math.round(n * 100)
    const fraction = (decimal[2] ?? "") + "000"
    return Number(decimal[1]) * 100 + Number(fraction.slice(0, 2)) + (Number(fraction[2]) >= 5 ? 1 : 0)
  }
  let debit = 0
  let credit = 0
  let valid = lines.length >= 2
  for (const l of lines) {
    const d = c(l.debit ?? 0), cr = c(l.credit ?? 0)
    const rawD = Number(l.debit ?? 0), rawC = Number(l.credit ?? 0)
    valid &&= Number.isFinite(rawD) && Number.isFinite(rawC) && rawD >= 0 && rawC >= 0 && !(rawD > 0 && rawC > 0) && (d > 0 || cr > 0)
    debit += d
    credit += cr
  }
  return { debit, credit, balanced: valid && Number.isSafeInteger(debit) && Number.isSafeInteger(credit) && debit > 0 && debit === credit }
}

/** "2026-09-14" -> "2026-09" (the finance period key). */
export function periodOf(isoDate: string | null | undefined): string | null {
  const m = /^(\d{4})-(0[1-9]|1[0-2])(?:$|-)/.exec(isoDate ?? "")
  return m ? `${m[1]}-${m[2]}` : null
}

export function isPeriodClosed(periods: Array<{ period: string; status: string }> | null | undefined, period: string | null): boolean {
  if (!period || !periods) return false
  return periods.some((p) => p.period === period && p.status === "closed")
}

export interface OverviewKpis {
  revenue: number
  expenses: number
  ebit: number
  cash_position: number
}

/** No posted ledger activity: every headline figure is zero, so zeros would pretend to be real. */
export function ledgerIsEmpty(kpis: OverviewKpis | null | undefined, netCashChange: number | null | undefined): boolean {
  if (!kpis) return true
  return kpis.revenue === 0 && kpis.expenses === 0 && kpis.ebit === 0 && kpis.cash_position === 0 && !netCashChange
}

export interface ScenarioBase {
  revenue: number
  opex: number
  /** Investing outflow from the cash-flow statement (0 when none recorded). */
  capex: number
}

/**
 * Scenario base from the real ledger (overview KPIs + cash flow), or null when
 * nothing is posted. Depreciation and interest are not derivable from the
 * statements and are NOT invented: the panel treats them as 0 and says so.
 */
export function scenarioBase(
  kpis: OverviewKpis | null | undefined,
  investingTotal: number | null | undefined,
): ScenarioBase | null {
  if (!kpis || (kpis.revenue === 0 && kpis.expenses === 0)) return null
  const inv = typeof investingTotal === "number" && Number.isFinite(investingTotal) ? investingTotal : 0
  return { revenue: kpis.revenue, opex: kpis.expenses, capex: inv < 0 ? Math.abs(inv) : 0 }
}

export function validJournalLines(lines: Array<{ account_code: string; debit?: unknown; credit?: unknown }>): boolean {
  return lines.length >= 2 && lines.every(line => {
    const debit = Number(line.debit ?? 0), credit = Number(line.credit ?? 0)
    return !!line.account_code.trim() && Number.isFinite(debit) && Number.isFinite(credit) && debit >= 0 && credit >= 0 && ((debit > 0) !== (credit > 0))
  }) && journalTotals(lines).balanced
}

/** Source labels describe recorded ledger activity; they do not imply a live integration. */
export function journalSourceLabel(source: string | null | undefined): string {
  const labels: Record<string, string> = { "billing.invoice": "Billing invoice", "billing.payment": "Billing payment", "billing.credit_note": "Billing credit note", "sales.commission": "Sales commission", "finance.reversal": "Reversal", MANUAL: "Manual" }
  return source ? labels[source] ?? source : "Unspecified"
}
