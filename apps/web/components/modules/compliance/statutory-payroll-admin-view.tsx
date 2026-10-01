"use client"

import React, { useCallback, useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Landmark,
  FileText,
  CheckCircle2,
  RefreshCw,
  Search,
  Users,
  Scale,
  FileCheck,
  ExternalLink,
  Info,
} from "lucide-react"
import {
  getPayrollStatutorySummary,
  prepareEmp201,
  markEmp201Filed,
  getUifDeclarations,
  getLaborComplianceAudit,
  type StatutoryPayrollSummaryResponse,
  type UifDeclarationsResponse,
  type LaborComplianceAuditResponse,
  type Emp201ReturnItem,
  type PrepareEmp201Result,
} from "@/lib/compliance-api"
import type { Loadable } from "@/lib/service-state"
import {
  SARS_EFILING_URL,
  isFiledStatus,
  loadableFromError,
  scoreView,
  validateFiledDate,
  validatePeriod,
  validatePrn,
  zarOrNA,
} from "@/lib/compliance-state"
import { RatesNotVerifiedChip, SectionStateNotice } from "./section-state"

async function load<T>(fn: () => Promise<T>): Promise<Loadable<T>> {
  try {
    return { state: "ready", data: await fn() }
  } catch (e) {
    return loadableFromError(e) as unknown as Loadable<T>
  }
}

const NA = "Not available"
const val = (v: string | number | null | undefined): string => (v === null || v === undefined || v === "" ? NA : String(v))

/** YYYY-MM of the previous calendar month: the EMP201 period normally due next. */
function previousPeriod(now = new Date()): string {
  const d = new Date(now.getFullYear(), now.getMonth() - 1, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
}

function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

function ManualFilingNote() {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-blue-500/30 bg-blue-500/5 p-3 text-xs text-blue-300">
      <Info className="mt-0.5 h-4 w-4 flex-shrink-0" />
      <p>
        Filing is done manually on SARS eFiling. OmniDome prepares a working paper from paid payslips and records the
        receipt you paste back; it never submits anything to SARS.{" "}
        <a
          href={SARS_EFILING_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 font-medium underline"
        >
          Open SARS eFiling <ExternalLink className="h-3 w-3" />
        </a>
      </p>
    </div>
  )
}

export function StatutoryPayrollAdminView() {
  const [activeTab, setActiveTab] = useState<"emp201" | "uif" | "labor" | "emp501">("emp201")
  const [summary, setSummary] = useState<Loadable<StatutoryPayrollSummaryResponse>>({ state: "loading" })
  const [uif, setUif] = useState<Loadable<UifDeclarationsResponse>>({ state: "loading" })
  const [labor, setLabor] = useState<Loadable<LaborComplianceAuditResponse>>({ state: "loading" })
  const [uifSearch, setUifSearch] = useState("")

  // Prepare working paper
  const [period, setPeriod] = useState(previousPeriod())
  const [preparing, setPreparing] = useState(false)
  const [prepared, setPrepared] = useState<PrepareEmp201Result | null>(null)
  const [prepareError, setPrepareError] = useState<string | null>(null)

  // Mark as filed
  const [markTarget, setMarkTarget] = useState<{ id: number; period: string } | null>(null)
  const [prnInput, setPrnInput] = useState("")
  const [filedDate, setFiledDate] = useState(today())
  const [marking, setMarking] = useState(false)
  const [markError, setMarkError] = useState<string | null>(null)
  const [markedMsg, setMarkedMsg] = useState<string | null>(null)

  const loadAll = useCallback(async () => {
    setSummary({ state: "loading" })
    setUif({ state: "loading" })
    setLabor({ state: "loading" })
    const [s, u, l] = await Promise.all([
      load(() => getPayrollStatutorySummary()),
      load(() => getUifDeclarations()),
      load(() => getLaborComplianceAudit()),
    ])
    setSummary(s)
    setUif(u)
    setLabor(l)
  }, [])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  const reloadSummary = async () => setSummary(await load(() => getPayrollStatutorySummary()))

  const handlePrepare = async (e: React.FormEvent) => {
    e.preventDefault()
    setPrepareError(null)
    if (!validatePeriod(period)) {
      setPrepareError("Enter the tax period as YYYY-MM.")
      return
    }
    setPreparing(true)
    try {
      const res = await prepareEmp201({ period: period.trim() })
      setPrepared(res)
      await reloadSummary()
    } catch (err) {
      // Server message verbatim (403 role, 404/409 no paid payslips, etc.)
      setPrepareError(err instanceof Error ? err.message : "Could not prepare the working paper")
    } finally {
      setPreparing(false)
    }
  }

  const handleMarkFiled = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!markTarget) return
    setMarkError(null)
    const prn = validatePrn(prnInput)
    if (!prn.ok) return setMarkError(prn.error)
    const date = validateFiledDate(filedDate)
    if (!date.ok) return setMarkError(date.error)
    setMarking(true)
    try {
      await markEmp201Filed(markTarget.id, { prn: prn.prn, filed_at: date.date })
      setMarkedMsg(`Recorded: EMP201 for ${markTarget.period} marked as filed with PRN ${prn.prn} on ${date.date}.`)
      setMarkTarget(null)
      setPrnInput("")
      await reloadSummary()
    } catch (err) {
      setMarkError(err instanceof Error ? err.message : "Could not record the filing")
    } finally {
      setMarking(false)
    }
  }

  const tabBtn = (key: typeof activeTab, icon: React.ReactNode, label: string) => (
    <Button size="sm" variant={activeTab === key ? "secondary" : "ghost"} onClick={() => setActiveTab(key)} className="gap-1.5">
      {icon} {label}
    </Button>
  )

  if (summary.state !== "ready") {
    return <SectionStateNotice state={summary} onRetry={loadAll} />
  }
  const sum = summary.data
  const ratesUnverified = sum.rates_verified !== true
  const hasFigures =
    typeof sum.total_emp201_liability_zar === "number" ||
    typeof sum.paye_withheld_zar === "number" ||
    typeof sum.sdl_zar === "number"
  const uifTotal =
    typeof sum.uif_employee_zar === "number" && typeof sum.uif_employer_zar === "number"
      ? sum.uif_employee_zar + sum.uif_employer_zar
      : null
  const laborScore = labor.state === "ready" ? scoreView(labor.data.overall_labor_score) : null
  const returns: Emp201ReturnItem[] = sum.recent_emp201_returns ?? []

  const filteredEmployees = (uif.state === "ready" ? uif.data.employees ?? [] : []).filter((emp) => {
    const q = uifSearch.toLowerCase()
    return (
      (emp.full_name ?? "").toLowerCase().includes(q) ||
      (emp.department ?? "").toLowerCase().includes(q) ||
      (emp.id_number ?? "").includes(q) ||
      (emp.employee_code ?? "").toLowerCase().includes(q)
    )
  })

  return (
    <div className="space-y-6">
      {markedMsg && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3.5 text-sm text-emerald-400 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
            <span>{markedMsg}</span>
          </div>
          <Button size="sm" variant="ghost" onClick={() => setMarkedMsg(null)}>Dismiss</Button>
        </div>
      )}

      <ManualFilingNote />

      {/* Top metric cards: real values only */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <Card className="p-3.5">
          <p className="text-xs text-muted-foreground flex items-center justify-between gap-2">
            <span>EMP201 liability ({sum.period ?? "no period"})</span>
            {ratesUnverified && hasFigures && <RatesNotVerifiedChip />}
          </p>
          <p className="text-2xl font-bold text-foreground mt-1.5">{zarOrNA(sum.total_emp201_liability_zar)}</p>
          <p className="text-[11px] text-muted-foreground mt-1">PAYE {zarOrNA(sum.paye_withheld_zar)} + UIF + SDL</p>
        </Card>
        <Card className="p-3.5">
          <p className="text-xs text-muted-foreground">SARS tax clearance (TCC)</p>
          <p className="text-2xl font-bold text-foreground mt-1.5">{sum.sars_tcc_pin ? "TCC on file" : NA}</p>
          <p className="text-[11px] text-muted-foreground mt-1">{val(sum.sars_tcc_status)}</p>
        </Card>
        <Card className="p-3.5">
          <p className="text-xs text-muted-foreground">UIF contributors</p>
          <p className="text-2xl font-bold text-foreground mt-1.5">
            {uif.state === "ready" && typeof uif.data.total_contributors === "number" ? uif.data.total_contributors : NA}
          </p>
          <p className="text-[11px] text-muted-foreground mt-1">
            {uif.state === "ready" ? "From the payroll register" : uif.state === "loading" ? "Loading" : "Register not loaded"}
          </p>
        </Card>
        <Card className="p-3.5">
          <p className="text-xs text-muted-foreground">Labour standards score</p>
          <p className="text-2xl font-bold text-foreground mt-1.5">{laborScore ? laborScore.label : NA}</p>
          <p className="text-[11px] text-muted-foreground mt-1">
            {laborScore && !laborScore.assessed ? "Not assessed" : labor.state === "ready" ? val(labor.data.bcea_readiness_status) : "Audit not loaded"}
          </p>
        </Card>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
        <div className="flex flex-wrap gap-2">
          {tabBtn("emp201", <Landmark className="h-4 w-4" />, "EMP201 working papers")}
          {tabBtn("uif", <Users className="h-4 w-4" />, "UIF register")}
          {tabBtn("labor", <Scale className="h-4 w-4" />, "BCEA & PSIRA audit")}
          {tabBtn("emp501", <FileCheck className="h-4 w-4" />, "EMP501 reconciliation")}
        </div>
        <Button size="sm" variant="outline" onClick={loadAll} className="gap-1">
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </Button>
      </div>

      {/* ── EMP201 ── */}
      {activeTab === "emp201" && (
        <div className="space-y-6">
          <Card className="border-border/80 bg-background/50">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Landmark className="h-4 w-4 text-emerald-400" />
                Prepare EMP201 working paper
              </CardTitle>
              <CardDescription className="text-xs">
                Built from PAID payslips for the chosen period. The result is saved as PREPARED_NOT_FILED until you file
                on SARS eFiling and record the receipt.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={handlePrepare} className="flex flex-wrap items-end gap-3">
                <div>
                  <label className="text-xs font-medium text-foreground">Tax period (YYYY-MM)</label>
                  <Input
                    value={period}
                    onChange={(e) => setPeriod(e.target.value)}
                    className="mt-1 w-36 font-mono text-xs"
                    aria-label="Tax period"
                  />
                </div>
                <Button type="submit" size="sm" variant="cta" disabled={preparing} className="gap-1">
                  <FileText className="h-3.5 w-3.5" />
                  {preparing ? "Preparing…" : "Prepare EMP201 working paper"}
                </Button>
              </form>
              {prepareError && <p role="alert" className="text-xs text-red-400">{prepareError}</p>}

              {prepared && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3.5 space-y-2 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="border-amber-500/40 text-amber-400">{prepared.status}</Badge>
                    <span className="font-medium text-foreground">Period {prepared.period}</span>
                    {prepared.rates_verified !== true && <RatesNotVerifiedChip />}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-4">
                    <div><p className="text-muted-foreground">PAYE</p><p className="font-mono text-foreground">{zarOrNA(prepared.paye_zar)}</p></div>
                    <div><p className="text-muted-foreground">UIF</p><p className="font-mono text-foreground">{zarOrNA(prepared.uif_zar)}</p></div>
                    <div><p className="text-muted-foreground">SDL</p><p className="font-mono text-foreground">{zarOrNA(prepared.sdl_zar)}</p></div>
                    <div><p className="text-muted-foreground">Total</p><p className="font-mono font-semibold text-foreground">{zarOrNA(prepared.total_payable_zar)}</p></div>
                  </div>
                  <p className="text-muted-foreground">
                    {prepared.note || "File manually on SARS eFiling"}. Then use Mark as filed below with the PRN SARS gives you.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/80 bg-background/50">
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-base">Latest payroll figures ({sum.period ?? "no period"})</CardTitle>
                  <CardDescription className="text-xs">From PAID payslips only. Nothing is estimated.</CardDescription>
                </div>
                {ratesUnverified && hasFigures && <RatesNotVerifiedChip />}
              </div>
            </CardHeader>
            <CardContent>
              {!hasFigures ? (
                <p className="rounded-lg border border-dashed border-border bg-secondary/20 p-6 text-center text-sm text-muted-foreground">
                  No payroll data yet: there are no PAID payslips to prepare an EMP201 from.
                </p>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-lg border border-border/60 bg-muted/20 p-3 space-y-1">
                    <p className="text-xs font-semibold text-foreground">PAYE withheld</p>
                    <p className="text-lg font-bold text-foreground">{zarOrNA(sum.paye_withheld_zar)}</p>
                  </div>
                  <div className="rounded-lg border border-border/60 bg-muted/20 p-3 space-y-1">
                    <p className="text-xs font-semibold text-foreground">Skills Development Levy</p>
                    <p className="text-lg font-bold text-foreground">{zarOrNA(sum.sdl_zar)}</p>
                  </div>
                  <div className="rounded-lg border border-border/60 bg-muted/20 p-3 space-y-1">
                    <p className="text-xs font-semibold text-foreground">UIF (employee + employer)</p>
                    <p className="text-lg font-bold text-foreground">{zarOrNA(uifTotal)}</p>
                  </div>
                  <div className="rounded-lg border border-border/60 bg-muted/20 p-3 space-y-1">
                    <p className="text-xs font-semibold text-foreground">Total EMP201</p>
                    <p className="text-lg font-bold text-foreground">{zarOrNA(sum.total_emp201_liability_zar)}</p>
                  </div>
                </div>
              )}
              <div className="mt-4 pt-3 border-t border-border/60 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
                <span>Gross remuneration: <strong className="text-foreground">{zarOrNA(sum.gross_remuneration_zar)}</strong></span>
                <span>Net salaries: <strong className="text-foreground">{zarOrNA(sum.net_salaries_disbursed_zar)}</strong></span>
                <span>Employees: <strong className="text-foreground">{val(sum.total_employees)}</strong></span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">EMP201 register</CardTitle>
              <CardDescription className="text-xs">
                A return counts as filed only after you record the eFiling PRN/receipt. Until then it stays prepared, not filed.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {markTarget && (
                <form onSubmit={handleMarkFiled} className="rounded-lg border border-border bg-secondary/20 p-3.5 space-y-3 text-xs">
                  <p className="font-medium text-foreground">
                    Mark EMP201 for {markTarget.period} as filed
                  </p>
                  <p className="text-muted-foreground">
                    Record this only after you have filed on SARS eFiling. This stores the reference you paste; it does
                    not file anything.
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <label className="font-medium text-foreground">PRN / receipt reference (16 to 19 letters or digits)</label>
                      <Input
                        value={prnInput}
                        onChange={(e) => setPrnInput(e.target.value)}
                        className="mt-1 font-mono text-xs"
                        aria-label="PRN or receipt reference"
                        autoComplete="off"
                      />
                    </div>
                    <div>
                      <label className="font-medium text-foreground">Date filed</label>
                      <Input
                        type="date"
                        value={filedDate}
                        max={today()}
                        onChange={(e) => setFiledDate(e.target.value)}
                        className="mt-1 text-xs"
                        aria-label="Date filed"
                      />
                    </div>
                  </div>
                  {markError && <p role="alert" className="text-red-400">{markError}</p>}
                  <div className="flex gap-2">
                    <Button type="submit" size="sm" variant="cta" disabled={marking}>
                      {marking ? "Saving…" : "Mark as filed"}
                    </Button>
                    <Button type="button" size="sm" variant="outline" onClick={() => { setMarkTarget(null); setMarkError(null) }}>
                      Cancel
                    </Button>
                  </div>
                </form>
              )}

              {returns.length === 0 ? (
                <p className="rounded-lg border border-dashed border-border bg-secondary/20 p-6 text-center text-sm text-muted-foreground">
                  No EMP201 working papers yet. Prepare one above.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[820px] text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2.5 pr-4 font-medium">Period</th>
                        <th className="py-2.5 pr-4 font-medium">PAYE</th>
                        <th className="py-2.5 pr-4 font-medium">UIF</th>
                        <th className="py-2.5 pr-4 font-medium">SDL</th>
                        <th className="py-2.5 pr-4 font-medium">Total</th>
                        <th className="py-2.5 pr-4 font-medium">Status</th>
                        <th className="py-2.5 pr-4 font-medium">PRN / receipt</th>
                        <th className="py-2.5 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {returns.map((ret) => {
                        const filed = isFiledStatus(ret.status)
                        return (
                          <tr key={ret.id ?? ret.period} className="border-b border-border/50 align-top">
                            <td className="py-3 pr-4 font-semibold text-foreground">{ret.period}</td>
                            <td className="py-3 pr-4 font-mono text-xs">{zarOrNA(ret.paye_zar)}</td>
                            <td className="py-3 pr-4 font-mono text-xs">{zarOrNA(ret.uif_zar)}</td>
                            <td className="py-3 pr-4 font-mono text-xs">{zarOrNA(ret.sdl_zar)}</td>
                            <td className="py-3 pr-4 font-mono text-xs font-semibold">{zarOrNA(ret.total_payable_zar)}</td>
                            <td className="py-3 pr-4">
                              <Badge
                                variant="outline"
                                className={filed ? "border-emerald-500/40 text-emerald-400" : "border-amber-500/40 text-amber-400"}
                              >
                                {filed ? "Filed (receipt recorded)" : ret.status || "PREPARED_NOT_FILED"}
                              </Badge>
                            </td>
                            <td className="py-3 pr-4">
                              {filed ? (
                                <div className="flex flex-col text-xs">
                                  <span className="font-mono text-primary">{val(ret.prn)}</span>
                                  <span className="text-muted-foreground">
                                    Filed {val(ret.filed_at)}
                                    {ret.filed_by ? ` by ${ret.filed_by}` : ""}
                                    {ret.marked_filed_at ? ` (recorded ${ret.marked_filed_at.slice(0, 10)})` : ""}
                                  </span>
                                </div>
                              ) : (
                                <span className="text-xs text-muted-foreground">Not filed</span>
                              )}
                            </td>
                            <td className="py-3">
                              {!filed && typeof ret.id === "number" && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-7 text-xs"
                                  onClick={() => {
                                    setMarkError(null)
                                    setMarkTarget({ id: ret.id as number, period: ret.period })
                                  }}
                                >
                                  Mark as filed
                                </Button>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── UIF ── */}
      {activeTab === "uif" && (
        <div className="space-y-6">
          {uif.state !== "ready" ? (
            <SectionStateNotice state={uif} onRetry={loadAll} />
          ) : (
            <Card className="border-border/80 bg-background/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Users className="h-4 w-4 text-blue-400" />
                  UIF contributor register
                </CardTitle>
                <CardDescription className="text-xs">
                  A working register built from payroll. UIF declarations are made manually on the Department of
                  Employment and Labour uFiling; nothing is lodged from here.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                  <div className="relative w-full sm:max-w-xs">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Search by name or department"
                      value={uifSearch}
                      onChange={(e) => setUifSearch(e.target.value)}
                      className="pl-9 h-9 text-xs"
                    />
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                    <span>Monthly UIF: <strong className="text-foreground">{zarOrNA(uif.data.total_monthly_remittance_zar)}</strong></span>
                    {ratesUnverified && <RatesNotVerifiedChip />}
                  </div>
                </div>
                {filteredEmployees.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-border bg-secondary/20 p-6 text-center text-sm text-muted-foreground">
                    {(uif.data.employees ?? []).length === 0
                      ? "No contributors yet: there is no payroll data to list."
                      : "No contributors match your search."}
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[760px] text-sm">
                      <thead>
                        <tr className="border-b border-border text-left text-xs text-muted-foreground">
                          <th className="py-2.5 pr-4 font-medium">Employee</th>
                          <th className="py-2.5 pr-4 font-medium">Department</th>
                          <th className="py-2.5 pr-4 font-medium">Gross</th>
                          <th className="py-2.5 pr-4 font-medium">UIF remuneration</th>
                          <th className="py-2.5 pr-4 font-medium">Employee UIF</th>
                          <th className="py-2.5 font-medium">Employer UIF</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredEmployees.map((emp) => (
                          <tr key={emp.employee_id} className="border-b border-border/50">
                            <td className="py-3 pr-4">
                              <p className="font-semibold text-foreground">{val(emp.full_name)}</p>
                              <p className="text-xs text-muted-foreground font-mono">{val(emp.employee_code)} · {val(emp.job_title)}</p>
                            </td>
                            <td className="py-3 pr-4 text-xs text-muted-foreground">{val(emp.department)}</td>
                            <td className="py-3 pr-4 font-mono text-xs">{zarOrNA(emp.gross_remuneration_zar)}</td>
                            <td className="py-3 pr-4 font-mono text-xs text-muted-foreground">{zarOrNA(emp.uif_remuneration_zar)}</td>
                            <td className="py-3 pr-4 font-mono text-xs">{zarOrNA(emp.employee_uif_zar)}</td>
                            <td className="py-3 font-mono text-xs">{zarOrNA(emp.employer_uif_zar)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ── Labour audit ── */}
      {activeTab === "labor" && (
        <div className="space-y-6">
          {labor.state !== "ready" ? (
            <SectionStateNotice state={labor} onRetry={loadAll} />
          ) : (
            <Card className="border-border/80 bg-background/50">
              <CardHeader className="pb-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div>
                    <CardTitle className="text-base flex items-center gap-2">
                      <Scale className="h-4 w-4 text-emerald-400" />
                      Labour standards audit
                    </CardTitle>
                    <CardDescription className="text-xs">
                      BCEA, COIDA and PSIRA checks computed from the records the service holds.
                    </CardDescription>
                  </div>
                  <Badge variant="outline" className="text-muted-foreground text-xs">
                    Score: {scoreView(labor.data.overall_labor_score).label}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                {(labor.data.audit_findings ?? []).length === 0 ? (
                  <p className="rounded-lg border border-dashed border-border bg-secondary/20 p-6 text-center text-sm text-muted-foreground">
                    No audit findings available: there is not enough data to assess.
                  </p>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2">
                    {(labor.data.audit_findings ?? []).map((finding, idx) => (
                      <div key={idx} className="rounded-lg border border-border/60 bg-muted/20 p-4 space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold text-foreground text-sm">{finding.standard}</span>
                          <Badge
                            variant="outline"
                            className={finding.compliant ? "border-emerald-500/40 text-emerald-400 text-xs" : "border-amber-500/40 text-amber-400 text-xs"}
                          >
                            {finding.status_label}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed">{finding.details}</p>
                        {finding.remediation && <p className="text-xs text-amber-300">Remediation: {finding.remediation}</p>}
                        <p className="pt-2 text-[11px] text-muted-foreground border-t border-border/40">
                          Category: <strong className="text-foreground">{(finding.category ?? "").replace(/_/g, " ")}</strong>
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ── EMP501 ── */}
      {activeTab === "emp501" && (
        <Card className="border-border/80 bg-background/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <FileCheck className="h-4 w-4 text-purple-400" />
              EMP501 reconciliation
            </CardTitle>
            <CardDescription className="text-xs">
              EMP501 and employee tax certificates (IRP5/IT3(a)) are reconciled and submitted on SARS eFiling. OmniDome
              does not generate or submit them.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-border/60 bg-muted/20 p-3.5 space-y-1">
                <p className="text-xs text-muted-foreground">Reconciliation status</p>
                <p className="text-lg font-bold text-foreground">{val(sum.emp501_reconciliation_status)}</p>
              </div>
              <div className="rounded-lg border border-border/60 bg-muted/20 p-3.5 space-y-1">
                <p className="text-xs text-muted-foreground">Variance</p>
                <p className="text-lg font-bold text-foreground">{zarOrNA(sum.emp501_variance_zar)}</p>
              </div>
              <div className="rounded-lg border border-border/60 bg-muted/20 p-3.5 space-y-1">
                <p className="text-xs text-muted-foreground">Tax certificates (IRP5)</p>
                <p className="text-lg font-bold text-foreground">{NA}</p>
              </div>
            </div>
            <ManualFilingNote />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
