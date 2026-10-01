"use client"

import React, { useState, useEffect } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Gift,
  Eye,
  Calculator,
  BarChart3,
  Building2,
  CheckCircle2,
  FileText,
  ShieldCheck,
  Search,
  ArrowRight,
  TrendingUp,
  Sliders,
  Download,
  Printer,
  CreditCard,
  Send,
  Plus,
  Trash2,
  Settings,
  Sparkles,
} from "lucide-react"
import {
  listPayslips,
  listPayrollRuns,
  createPayrollRun,
  calculateSalaryPreview,
  postPayrollRunToFinance,
  loadableFromError,
  type PayslipRecord,
  type PayrollRun,
  type SalaryPreviewResult,
  type DepartmentCostAllocation,
} from "@/lib/hr-api"
import { fmtZar } from "@/lib/format"
import { fmtMoneyOrDash, formatHrError, isUnverifiedTablesError, parseHrError } from "@/lib/talent-derive"
import { NotConnected } from "@/components/ui/not-connected"
import type { Loadable } from "@/lib/service-state"
import { PayslipModal } from "./payslip-modal"

interface PayrollPayslipsViewProps {
  deptCostAllocation: DepartmentCostAllocation | null
  deptCostLoadable?: Loadable<DepartmentCostAllocation>
  isHrAdmin: boolean
}

interface CustomEarningItem {
  id: string
  label: string
  amount: number
  taxable: boolean
}

interface CustomDeductionItem {
  id: string
  label: string
  amount: number
  statutory: boolean
}

export function PayrollPayslipsView({ deptCostAllocation, deptCostLoadable, isHrAdmin }: PayrollPayslipsViewProps) {
  const [activeTab, setActiveTab] = useState<"designer" | "payslips" | "calculator" | "fpa">("designer")

  // Payslips state
  const [payslips, setPayslips] = useState<PayslipRecord[]>([])
  const [loadingSlips, setLoadingSlips] = useState(true)
  const [slipsLoad, setSlipsLoad] = useState<Loadable<null>>({ state: "loading" })
  const [runs, setRuns] = useState<PayrollRun[]>([])
  const [newPeriod, setNewPeriod] = useState("")
  const [creatingRun, setCreatingRun] = useState(false)
  const [runMessage, setRunMessage] = useState<string | null>(null)
  const [tablesUnverified, setTablesUnverified] = useState<string | null>(null)
  const [calcError, setCalcError] = useState<string | null>(null)
  const [selectedPayslip, setSelectedPayslip] = useState<PayslipRecord | null>(null)
  const [searchEmp, setSearchEmp] = useState("")

  // Calculator state
  const [calcGross, setCalcGross] = useState<number>(0)
  const [calcAllowances, setCalcAllowances] = useState<number>(0)
  const [calcMedAid, setCalcMedAid] = useState<number>(0)
  const [calcResult, setCalcResult] = useState<SalaryPreviewResult | null>(null)
  const [isCalculating, setIsCalculating] = useState(false)

  // Finance Post state
  const [isPostingFinance, setIsPostingFinance] = useState(false)
  const [financePostMsg, setFinancePostMsg] = useState<string | null>(null)

  // ── Payslip Designer & Editor State ────────────────────────────────
  // Blank layout designer: nothing here is real data until you type it.
  const [designerCompanyName, setDesignerCompanyName] = useState("")
  const [designerTaxNumber, setDesignerTaxNumber] = useState("")
  const [designerUifNumber, setDesignerUifNumber] = useState("")
  const [designerEmpName, setDesignerEmpName] = useState("")
  const [designerJobTitle, setDesignerJobTitle] = useState("")
  const [designerEmpCode, setDesignerEmpCode] = useState("")
  const [designerPayPeriod, setDesignerPayPeriod] = useState("")
  const [designerPayDate, setDesignerPayDate] = useState("")

  // Dynamic Earnings
  const [earningsItems, setEarningsItems] = useState<CustomEarningItem[]>([])
  const [deductionItems, setDeductionItems] = useState<CustomDeductionItem[]>([])

  const totalGrossEarnings = earningsItems.reduce((acc, curr) => acc + curr.amount, 0)
  const totalDeductions = deductionItems.reduce((acc, curr) => acc + curr.amount, 0)
  const netTakeHomePay = totalGrossEarnings - totalDeductions

  // Load payslips and runs (a 403 is shown as "Not permitted", never as an empty archive)
  const loadPayslips = async () => {
    setLoadingSlips(true)
    try {
      const [data, runList] = await Promise.all([listPayslips(), listPayrollRuns().catch(() => null)])
      setPayslips(data)
      setRuns(runList?.items ?? [])
      setSlipsLoad({ state: "ready", data: null })
    } catch (err: unknown) {
      setSlipsLoad(loadableFromError(err))
    } finally {
      setLoadingSlips(false)
    }
  }

  useEffect(() => {
    void loadPayslips()
  }, [])

  // Calculate live preview (only when asked: never on mount, never with invented inputs)
  const handleCalculatePreview = async () => {
    setIsCalculating(true)
    setCalcError(null)
    try {
      const res = await calculateSalaryPreview({
        gross_salary: calcGross,
        allowances: calcAllowances,
        medical_aid_members: calcMedAid,
      })
      setCalcResult(res)
    } catch (err: unknown) {
      setCalcError(formatHrError(err))
    } finally {
      setIsCalculating(false)
    }
  }

  const latestRun = runs[0] ?? null

  // Post the latest REAL run to the ledger (totals come from the run, never from headcount x a guess)
  const handlePostToFinance = async () => {
    if (!latestRun) return
    setIsPostingFinance(true)
    setFinancePostMsg(null)
    try {
      const res = await postPayrollRunToFinance({
        payroll_run_id: latestRun.id,
        run_name: `Payroll ${latestRun.period}`,
        currency: "ZAR",
      })
      setFinancePostMsg(`Posted to the General Ledger. Journal Entry Ref: ${res.journal_entry_id || res.reference || "—"}`)
      void loadPayslips()
    } catch (err: unknown) {
      setFinancePostMsg(formatHrError(err))
    } finally {
      setIsPostingFinance(false)
    }
  }

  // Create a payroll run; 503 "PAYE tables not verified" is surfaced as an amber banner
  const handleCreateRun = async () => {
    setCreatingRun(true)
    setRunMessage(null)
    setTablesUnverified(null)
    try {
      const run = await createPayrollRun(newPeriod)
      setRunMessage(`Payroll run for ${run.period} created.`)
      void loadPayslips()
    } catch (err) {
      if (isUnverifiedTablesError(err)) setTablesUnverified(parseHrError(err).message)
      else setRunMessage(formatHrError(err))
    } finally {
      setCreatingRun(false)
    }
  }

  // Add earnings item
  const handleAddEarning = () => {
    setEarningsItems((prev) => [
      ...prev,
      { id: String(Date.now()), label: "New earning", amount: 0, taxable: true },
    ])
  }

  // Add deduction item
  const handleAddDeduction = () => {
    setDeductionItems((prev) => [
      ...prev,
      { id: String(Date.now()), label: "New deduction", amount: 0, statutory: false },
    ])
  }

  return (
    <div className="space-y-6">
      {tablesUnverified && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-400" role="alert">
          PAYE tables for the current tax year are not verified: {tablesUnverified}
        </div>
      )}
      {isHrAdmin && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card/60 p-3 text-xs">
          <span className="font-semibold text-foreground">New payroll run</span>
          <Input
            placeholder="YYYY-MM"
            value={newPeriod}
            onChange={(e) => setNewPeriod(e.target.value)}
            className="h-8 w-32 text-xs font-mono"
          />
          <Button size="sm" onClick={handleCreateRun} disabled={creatingRun || !/^\d{4}-\d{2}$/.test(newPeriod)} className="text-xs">
            {creatingRun ? "Creating…" : "Create run"}
          </Button>
          {runMessage && <span className="text-muted-foreground">{runMessage}</span>}
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border pb-2 text-xs">
        {[
          { id: "designer", label: "Payslip Designer & Customizer" },
          { id: "payslips", label: `Staff Payslips Directory (${payslips.length})` },
          { id: "calculator", label: "SARS PAYE & Net Salary Calculator" },
          { id: "fpa", label: "Finance & General Ledger Posting" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
              activeTab === tab.id
                ? "bg-primary/15 text-primary border border-primary/30"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── TAB 1: Payslip Designer & Editor ───────────────────────────── */}
      {activeTab === "designer" && (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-12">
            {/* Editor Sidebar Controls */}
            <div className="space-y-4 lg:col-span-5 text-xs">
              <Card className="border-border">
                <CardHeader className="pb-3 border-b border-border/60">
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <Sliders className="h-4 w-4 text-primary" /> Payslip Layout & Parameters
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Configure company details, statutory numbers, and employee earnings/deductions.
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-4 space-y-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Company Legal Name</label>
                      <Input
                        value={designerCompanyName}
                        onChange={(e) => setDesignerCompanyName(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">SARS Tax Reference</label>
                      <Input
                        value={designerTaxNumber}
                        onChange={(e) => setDesignerTaxNumber(e.target.value)}
                        className="h-8 text-xs font-mono"
                      />
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Employee Name</label>
                      <Input
                        value={designerEmpName}
                        onChange={(e) => setDesignerEmpName(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Employee Code</label>
                      <Input
                        value={designerEmpCode}
                        onChange={(e) => setDesignerEmpCode(e.target.value)}
                        className="h-8 text-xs font-mono"
                      />
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Pay Period</label>
                      <Input
                        value={designerPayPeriod}
                        onChange={(e) => setDesignerPayPeriod(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Pay Date</label>
                      <Input
                        type="date"
                        value={designerPayDate}
                        onChange={(e) => setDesignerPayDate(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>

                  {/* Earnings Editor */}
                  <div className="space-y-2 border-t border-border/60 pt-3">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground">Earnings & Allowances</span>
                      <Button size="sm" variant="outline" className="h-6 text-[10px] px-2" onClick={handleAddEarning}>
                        <Plus className="h-3 w-3 mr-1" /> Add Item
                      </Button>
                    </div>
                    <div className="space-y-1.5">
                      {earningsItems.map((item) => (
                        <div key={item.id} className="flex items-center gap-2">
                          <Input
                            value={item.label}
                            onChange={(e) =>
                              setEarningsItems((prev) =>
                                prev.map((x) => (x.id === item.id ? { ...x, label: e.target.value } : x))
                              )
                            }
                            className="h-7 text-xs flex-1"
                          />
                          <Input
                            type="number"
                            value={item.amount}
                            onChange={(e) =>
                              setEarningsItems((prev) =>
                                prev.map((x) => (x.id === item.id ? { ...x, amount: Number(e.target.value) } : x))
                              )
                            }
                            className="h-7 text-xs w-24 text-right font-mono"
                          />
                          <button
                            type="button"
                            onClick={() => setEarningsItems((prev) => prev.filter((x) => x.id !== item.id))}
                            className="text-muted-foreground hover:text-red-400 p-1"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Deductions Editor */}
                  <div className="space-y-2 border-t border-border/60 pt-3">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground">Statutory & Voluntary Deductions</span>
                      <Button size="sm" variant="outline" className="h-6 text-[10px] px-2" onClick={handleAddDeduction}>
                        <Plus className="h-3 w-3 mr-1" /> Add Item
                      </Button>
                    </div>
                    <div className="space-y-1.5">
                      {deductionItems.map((item) => (
                        <div key={item.id} className="flex items-center gap-2">
                          <Input
                            value={item.label}
                            onChange={(e) =>
                              setDeductionItems((prev) =>
                                prev.map((x) => (x.id === item.id ? { ...x, label: e.target.value } : x))
                              )
                            }
                            className="h-7 text-xs flex-1"
                          />
                          <Input
                            type="number"
                            value={item.amount}
                            onChange={(e) =>
                              setDeductionItems((prev) =>
                                prev.map((x) => (x.id === item.id ? { ...x, amount: Number(e.target.value) } : x))
                              )
                            }
                            className="h-7 text-xs w-24 text-right font-mono"
                          />
                          <button
                            type="button"
                            onClick={() => setDeductionItems((prev) => prev.filter((x) => x.id !== item.id))}
                            className="text-muted-foreground hover:text-red-400 p-1"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Live Interactive Payslip Preview (BCEA / SARS Compliant) */}
            <div className="lg:col-span-7">
              <Card className="border-border bg-card/90 shadow-md">
                <CardHeader className="flex flex-row items-center justify-between border-b border-border/60 pb-3 bg-muted/10">
                  <div>
                    <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
                      <Eye className="h-4 w-4 text-cyan-400" /> Interactive Payslip Live Preview
                    </CardTitle>
                    <CardDescription className="text-xs">
                      Complies with BCEA Section 33 & SARS PAYE statutory reporting.
                    </CardDescription>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs gap-1"
                      onClick={() => window.print()}
                    >
                      <Printer className="h-3.5 w-3.5" /> Print
                    </Button>

                  </div>
                </CardHeader>

                <CardContent className="p-6 space-y-5 text-xs font-sans">
                  {/* Company & Document Header */}
                  <div className="flex items-start justify-between border-b border-border pb-4">
                    <div>
                      <h2 className="text-base font-bold text-foreground">{designerCompanyName}</h2>
                                            <p className="text-muted-foreground text-[11px]">SARS Tax Ref: <span className="font-mono text-foreground">{designerTaxNumber}</span> | UIF: <span className="font-mono text-foreground">{designerUifNumber}</span></p>
                    </div>
                    <div className="text-right">
                      <Badge variant="outline" className="border-primary/40 text-primary font-bold text-xs uppercase px-2 py-0.5">
                        CONFIDENTIAL PAYSLIP
                      </Badge>
                      <p className="text-muted-foreground text-[11px] mt-1">Period: <span className="text-foreground font-semibold">{designerPayPeriod}</span></p>
                      <p className="text-muted-foreground text-[11px]">Pay Date: <span className="text-foreground font-semibold">{designerPayDate}</span></p>
                    </div>
                  </div>

                  {/* Employee Details Strip */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 rounded-lg border border-border bg-muted/20 p-3">
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase font-semibold">Employee Name</p>
                      <p className="font-semibold text-foreground text-xs mt-0.5">{designerEmpName}</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase font-semibold">Employee Code</p>
                      <p className="font-mono font-semibold text-primary text-xs mt-0.5">{designerEmpCode}</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase font-semibold">Position / Role</p>
                      <p className="text-foreground text-xs mt-0.5">{designerJobTitle}</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase font-semibold">Payment Method</p>
                      <p className="text-foreground text-xs mt-0.5">EFT Direct Deposit</p>
                    </div>
                  </div>

                  {/* Earnings vs Deductions 2-Column Table */}
                  <div className="grid gap-6 sm:grid-cols-2">
                    {/* Earnings Table */}
                    <div className="space-y-2">
                      <div className="flex justify-between border-b border-border/80 pb-1.5 font-semibold text-foreground text-xs">
                        <span>Earnings Item</span>
                        <span>Amount (ZAR)</span>
                      </div>
                      <div className="space-y-1.5 min-h-[140px]">
                        {earningsItems.map((item) => (
                          <div key={item.id} className="flex justify-between text-muted-foreground text-xs">
                            <span className="truncate pr-2">{item.label}</span>
                            <span className="font-mono text-foreground">{fmtMoneyOrDash(item.amount)}</span>
                          </div>
                        ))}
                      </div>
                      <div className="flex justify-between border-t border-border pt-2 font-bold text-foreground text-xs">
                        <span>Total Gross Earnings:</span>
                        <span className="font-mono text-emerald-400">{fmtMoneyOrDash(totalGrossEarnings)}</span>
                      </div>
                    </div>

                    {/* Deductions Table */}
                    <div className="space-y-2">
                      <div className="flex justify-between border-b border-border/80 pb-1.5 font-semibold text-foreground text-xs">
                        <span>Deductions Item</span>
                        <span>Amount (ZAR)</span>
                      </div>
                      <div className="space-y-1.5 min-h-[140px]">
                        {deductionItems.map((item) => (
                          <div key={item.id} className="flex justify-between text-muted-foreground text-xs">
                            <span className="truncate pr-2">{item.label}</span>
                            <span className="font-mono text-foreground">{fmtMoneyOrDash(item.amount)}</span>
                          </div>
                        ))}
                      </div>
                      <div className="flex justify-between border-t border-border pt-2 font-bold text-foreground text-xs">
                        <span>Total Deductions:</span>
                        <span className="font-mono text-red-400">{fmtMoneyOrDash(totalDeductions)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Net Pay Callout Box */}
                  <div className="flex items-center justify-between rounded-xl border border-primary/40 bg-primary/10 p-4">
                    <div>
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-primary">
                        Net Take-Home Pay (Disbursed via EFT)
                      </span>
                      <p className="text-xs text-muted-foreground mt-0.5">Layout preview only; amounts are whatever you type above.</p>
                    </div>
                    <div className="text-right">
                      <span className="text-2xl font-bold font-mono text-foreground">
                        {fmtMoneyOrDash(netTakeHomePay)}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 2: Staff Payslips Directory ────────────────────────────── */}
      {activeTab === "payslips" && (
        <div className="space-y-4">
          <Card className="border-border">
            <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3">
              <div>
                <CardTitle className="text-base">Generated Payslips Archive</CardTitle>
                <CardDescription className="text-xs">
                  Review, download, or audit monthly payslips for all active personnel.
                </CardDescription>
              </div>
              <div className="relative w-full sm:w-64">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  placeholder="Filter by employee name..."
                  value={searchEmp}
                  onChange={(e) => setSearchEmp(e.target.value)}
                  className="pl-8 h-8 text-xs"
                />
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                      <th className="py-2.5 px-4 font-medium">Employee</th>
                      <th className="py-2.5 px-4 font-medium">Department</th>
                      <th className="py-2.5 px-4 font-medium">Basic (ZAR)</th>
                      <th className="py-2.5 px-4 font-medium">Tax / PAYE</th>
                      <th className="py-2.5 px-4 font-medium">Net Disbursed</th>
                      <th className="py-2.5 px-4 font-medium">Status</th>
                      <th className="py-2.5 px-4 font-medium text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {loadingSlips ? (
                      <tr><td colSpan={7} className="py-8 text-center text-muted-foreground">Loading payslips…</td></tr>
                    ) : slipsLoad.state !== "ready" ? (
                      <tr><td colSpan={7} className="p-4"><NotConnected loadable={slipsLoad} service="Payslips" onRetry={() => void loadPayslips()} /></td></tr>
                    ) : payslips.length === 0 ? (
                      <tr><td colSpan={7} className="py-8 text-center text-muted-foreground">No payslips yet. Create a payroll run to generate them.</td></tr>
                    ) : (
                      payslips
                        .filter((p) => p.employee_name.toLowerCase().includes(searchEmp.toLowerCase()))
                        .map((p) => (
                          <tr key={p.id} className="hover:bg-muted/30">
                            <td className="py-3 px-4 font-semibold text-foreground">{p.employee_name}</td>
                            <td className="py-3 px-4 text-muted-foreground">{p.department}</td>
                            <td className="py-3 px-4 font-mono">{fmtMoneyOrDash(p.basic_salary)}</td>
                            <td className="py-3 px-4 font-mono text-red-400">{fmtMoneyOrDash(p.tax)}</td>
                            <td className="py-3 px-4 font-mono font-bold text-emerald-400">{fmtMoneyOrDash(p.net)}</td>
                            <td className="py-3 px-4">
                              <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
                                {p.payout_status}
                              </Badge>
                            </td>
                            <td className="py-3 px-4 text-right">
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 text-xs text-primary"
                                onClick={() => setSelectedPayslip(p)}
                              >
                                View Payslip
                              </Button>
                            </td>
                          </tr>
                        ))
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── TAB 3: SARS PAYE & Net Salary Calculator ──────────────────── */}
      {activeTab === "calculator" && (
        <div className="grid gap-6 lg:grid-cols-2 text-xs">
          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <CardTitle className="text-base flex items-center gap-2">
                <Calculator className="h-4 w-4 text-primary" /> SARS Statutory PAYE & Net Calculator
              </CardTitle>
              <CardDescription className="text-xs">
                Server-side PAYE, medical tax credit and UIF/SDL estimate for the inputs you enter.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              <div className="space-y-1.5">
                <label className="font-medium text-foreground">Monthly Basic Salary (ZAR)</label>
                <Input
                  type="number"
                  value={calcGross}
                  onChange={(e) => setCalcGross(Number(e.target.value))}
                  className="h-8 text-xs font-mono"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-medium text-foreground">Taxable Allowances & Standby Pay</label>
                <Input
                  type="number"
                  value={calcAllowances}
                  onChange={(e) => setCalcAllowances(Number(e.target.value))}
                  className="h-8 text-xs font-mono"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-medium text-foreground">Registered Medical Aid Dependents</label>
                <Input
                  type="number"
                  min={0}
                  max={6}
                  value={calcMedAid}
                  onChange={(e) => setCalcMedAid(Number(e.target.value))}
                  className="h-8 text-xs"
                />
              </div>

              {calcError && <p className="text-xs text-red-400" role="alert">{calcError}</p>}
              <Button
                size="sm"
                variant="default"
                className="w-full"
                onClick={handleCalculatePreview}
                disabled={isCalculating}
              >
                {isCalculating ? "Calculating..." : "Compute Net Pay Breakdown"}
              </Button>
            </CardContent>
          </Card>

          {calcResult && (
            <Card className="border-border">
              <CardHeader className="pb-3 border-b border-border/60">
                <CardTitle className="text-base flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-emerald-400" /> SARS Statutory Tax Breakdown
                </CardTitle>
                <CardDescription className="text-xs">
                  Tax year {calcResult.tax_year ?? "—"}, table version {calcResult.tax_table_version ?? "—"}.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-4 space-y-2 text-muted-foreground">
                {calcResult.rates_verified === false && (
                  <p className="rounded border border-amber-500/40 bg-amber-500/10 p-2 text-amber-400" role="alert">
                    PAYE tables for tax year {calcResult.tax_year ?? "?"} are not verified.
                  </p>
                )}
                <div className="flex justify-between py-1 border-b border-border/40">
                  <span>Gross Monthly Remuneration:</span>
                  <span className="font-semibold text-foreground font-mono">{fmtMoneyOrDash(calcResult.gross_salary)}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border/40">
                  <span>PAYE Income Tax:</span>
                  <span className="font-semibold text-red-400 font-mono">{fmtMoneyOrDash(calcResult.monthly_paye_tax)}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border/40">
                  <span>Medical Scheme Tax Credit (Section 6A):</span>
                  <span className="font-semibold text-emerald-400 font-mono">- {fmtMoneyOrDash(calcResult.medical_tax_credit)}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border/40">
                  <span>UIF Employee Contribution:</span>
                  <span className="font-semibold text-foreground font-mono">{fmtMoneyOrDash(calcResult.uif_employee_contribution)}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border/40">
                  <span>SDL Employer Contribution:</span>
                  <span className="font-semibold text-foreground font-mono">{fmtMoneyOrDash(calcResult.sdl_employer_contribution)}</span>
                </div>
                <div className="flex justify-between py-2 border-t border-border font-bold text-foreground text-sm">
                  <span>Net Estimated Take-Home Pay:</span>
                  <span className="font-mono text-emerald-400 text-base">{fmtMoneyOrDash(calcResult.net_take_home_pay)}</span>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ── TAB 4: Finance & General Ledger Posting ────────────────────── */}
      {activeTab === "fpa" && (
        <div className="space-y-4 text-xs">
          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Building2 className="h-4 w-4 text-primary" /> General Ledger Payroll Journal & Cost Allocation
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Reconciles wage liabilities against departmental cost centers and posts journal entries to Finance.
                  </CardDescription>
                </div>
                <Button
                  size="sm"
                  variant="default"
                  disabled={isPostingFinance || !latestRun || !isHrAdmin}
                  title={!isHrAdmin ? "HR admin only" : !latestRun ? "No payroll run to post" : undefined}
                  onClick={handlePostToFinance}
                  className="gap-1.5 text-xs"
                >
                  <Send className="h-3.5 w-3.5" />
                  {isPostingFinance ? "Posting to Finance…" : "Post Run to General Ledger"}
                </Button>
              </div>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              {financePostMsg && (
                <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-emerald-300">
                  {financePostMsg}
                </div>
              )}

              {!latestRun ? (
                <p className="rounded-lg border border-dashed border-border p-4 text-center text-muted-foreground">
                  No payroll run exists yet. Figures appear once a run has been created.
                </p>
              ) : (
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                    <span className="text-muted-foreground">Gross payroll (run {latestRun.period})</span>
                    <p className="text-lg font-bold text-foreground">{fmtMoneyOrDash(latestRun.total_gross)}</p>
                    <p className="text-[10px] text-muted-foreground">{latestRun.employee_count} employees, status {latestRun.status}</p>
                  </div>
                  <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                    <span className="text-muted-foreground">Total deductions</span>
                    <p className="text-lg font-bold text-red-400">{fmtMoneyOrDash(latestRun.total_deductions)}</p>
                    <p className="text-[10px] text-muted-foreground">as recorded on the run</p>
                  </div>
                  <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                    <span className="text-muted-foreground">Net payable</span>
                    <p className="text-lg font-bold text-emerald-400">{fmtMoneyOrDash(latestRun.total_net)}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {latestRun.tax_year ? `Tax year ${latestRun.tax_year}` : "tax year not recorded"}
                    </p>
                  </div>
                </div>
              )}
              {deptCostAllocation && (
                <p className="text-[11px] text-muted-foreground">
                  Monthly payroll cost across departments: <strong className="text-foreground">{fmtZar(deptCostAllocation.total_monthly_payroll_zar)}</strong>
                </p>
              )}
              {deptCostLoadable && deptCostLoadable.state === "denied" && (
                <p className="text-[11px] text-amber-400">Department cost allocation: Not permitted.</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Payslip View Modal */}
      {selectedPayslip && (
        <PayslipModal payslip={selectedPayslip} onClose={() => setSelectedPayslip(null)} />
      )}
    </div>
  )
}
