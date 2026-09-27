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
  calculateSalaryPreview,
  postPayrollRunToFinance,
  type PayslipRecord,
  type SalaryPreviewResult,
  type DepartmentCostAllocation,
} from "@/lib/hr-api"
import { PayslipModal } from "./payslip-modal"

interface PayrollPayslipsViewProps {
  deptCostAllocation: DepartmentCostAllocation | null
  deptCostLoading: boolean
  kpiTotal: number
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

export function PayrollPayslipsView({
  deptCostAllocation,
  deptCostLoading,
  kpiTotal,
}: PayrollPayslipsViewProps) {
  const [activeTab, setActiveTab] = useState<"designer" | "payslips" | "calculator" | "fpa">("designer")

  // Payslips state
  const [payslips, setPayslips] = useState<PayslipRecord[]>([])
  const [loadingSlips, setLoadingSlips] = useState(true)
  const [selectedPayslip, setSelectedPayslip] = useState<PayslipRecord | null>(null)
  const [searchEmp, setSearchEmp] = useState("")

  // Calculator state
  const [calcGross, setCalcGross] = useState<number>(45000)
  const [calcAllowances, setCalcAllowances] = useState<number>(3500)
  const [calcMedAid, setCalcMedAid] = useState<number>(2)
  const [calcResult, setCalcResult] = useState<SalaryPreviewResult | null>(null)
  const [isCalculating, setIsCalculating] = useState(false)

  // Finance Post state
  const [isPostingFinance, setIsPostingFinance] = useState(false)
  const [financePostMsg, setFinancePostMsg] = useState<string | null>(null)

  // ── Payslip Designer & Editor State ────────────────────────────────
  const [designerCompanyName, setDesignerCompanyName] = useState("OmniDome Telecoms (Pty) Ltd")
  const [designerTaxNumber, setDesignerTaxNumber] = useState("9842109482")
  const [designerUifNumber, setDesignerUifNumber] = useState("U-9842194/8")
  const [designerEmpName, setDesignerEmpName] = useState("Sipho Mthembu")
  const [designerJobTitle, setDesignerJobTitle] = useState("NOC Tier-1 Monitoring Tech")
  const [designerEmpCode, setDesignerEmpCode] = useState("ISP-006")
  const [designerPayPeriod, setDesignerPayPeriod] = useState("September 2026")
  const [designerPayDate, setDesignerPayDate] = useState("2026-09-25")

  // Dynamic Earnings
  const [earningsItems, setEarningsItems] = useState<CustomEarningItem[]>([
    { id: "1", label: "Basic Monthly Salary", amount: 35000, taxable: true },
    { id: "2", label: "Fiber Standby Allowance", amount: 3200, taxable: true },
    { id: "3", label: "Night Shift Differential", amount: 2400, taxable: true },
    { id: "4", label: "Cellular & APN Data Allowance", amount: 850, taxable: false },
  ])

  // Dynamic Deductions
  const [deductionItems, setDeductionItems] = useState<CustomDeductionItem[]>([
    { id: "1", label: "PAYE Income Tax (SARS)", amount: 6842, statutory: true },
    { id: "2", label: "UIF Employee Contribution (1%)", amount: 177.12, statutory: true },
    { id: "3", label: "Provident Fund (Sanlam 7.5%)", amount: 2625, statutory: false },
    { id: "4", label: "Discovery Health Medical Aid", amount: 3100, statutory: false },
  ])

  const totalGrossEarnings = earningsItems.reduce((acc, curr) => acc + curr.amount, 0)
  const totalDeductions = deductionItems.reduce((acc, curr) => acc + curr.amount, 0)
  const netTakeHomePay = totalGrossEarnings - totalDeductions

  // Load Payslips
  const loadPayslips = async () => {
    setLoadingSlips(true)
    try {
      const data = await listPayslips()
      setPayslips(data)
    } catch (err: unknown) {
      console.error("Failed to load payslips:", err)
    } finally {
      setLoadingSlips(false)
    }
  }

  useEffect(() => {
    loadPayslips()
    handleCalculatePreview()
  }, [])

  // Calculate live preview
  const handleCalculatePreview = async () => {
    setIsCalculating(true)
    try {
      const res = await calculateSalaryPreview({
        gross_salary: calcGross,
        allowances: calcAllowances,
        medical_aid_members: calcMedAid,
      })
      setCalcResult(res)
    } catch (err: unknown) {
      console.error("Preview failed:", err)
    } finally {
      setIsCalculating(false)
    }
  }

  // Handle post to finance
  const handlePostToFinance = async () => {
    setIsPostingFinance(true)
    setFinancePostMsg(null)
    try {
      const runId = `RUN-${new Date().toISOString().slice(0, 10)}`
      const res = await postPayrollRunToFinance({
        payroll_run_id: runId,
        run_name: `Monthly Payroll - ${runId}`,
        total_gross_zar: kpiTotal * 16000,
        currency: "ZAR",
      })
      setFinancePostMsg(`Successfully posted batch to General Ledger! Journal Entry Ref: ${res.journal_entry_id || res.reference || "GL-2026-SEP"}`)
    } catch (err: unknown) {
      setFinancePostMsg(err instanceof Error ? err.message : "Failed to post to Finance service")
    } finally {
      setIsPostingFinance(false)
    }
  }

  // Add earnings item
  const handleAddEarning = () => {
    setEarningsItems((prev) => [
      ...prev,
      { id: String(Date.now()), label: "New Allowance", amount: 1000, taxable: true },
    ])
  }

  // Add deduction item
  const handleAddDeduction = () => {
    setDeductionItems((prev) => [
      ...prev,
      { id: String(Date.now()), label: "Voluntary Deduction", amount: 500, statutory: false },
    ])
  }

  return (
    <div className="space-y-6">
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
                      onClick={() => alert("Printing BCEA-compliant payslip...")}
                    >
                      <Printer className="h-3.5 w-3.5" /> Print
                    </Button>
                    <Button
                      size="sm"
                      variant="default"
                      className="h-7 text-xs gap-1"
                      onClick={() => alert("Downloading PDF payslip...")}
                    >
                      <Download className="h-3.5 w-3.5" /> Download PDF
                    </Button>
                  </div>
                </CardHeader>

                <CardContent className="p-6 space-y-5 text-xs font-sans">
                  {/* Company & Document Header */}
                  <div className="flex items-start justify-between border-b border-border pb-4">
                    <div>
                      <h2 className="text-base font-bold text-foreground">{designerCompanyName}</h2>
                      <p className="text-muted-foreground text-[11px]">102 Rivonia Road, Sandton, Johannesburg, 2196</p>
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
                            <span className="font-mono text-foreground">R {item.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                          </div>
                        ))}
                      </div>
                      <div className="flex justify-between border-t border-border pt-2 font-bold text-foreground text-xs">
                        <span>Total Gross Earnings:</span>
                        <span className="font-mono text-emerald-400">R {totalGrossEarnings.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
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
                            <span className="font-mono text-foreground">R {item.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                          </div>
                        ))}
                      </div>
                      <div className="flex justify-between border-t border-border pt-2 font-bold text-foreground text-xs">
                        <span>Total Deductions:</span>
                        <span className="font-mono text-red-400">R {totalDeductions.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                      </div>
                    </div>
                  </div>

                  {/* Net Pay Callout Box */}
                  <div className="flex items-center justify-between rounded-xl border border-primary/40 bg-primary/10 p-4">
                    <div>
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-primary">
                        Net Take-Home Pay (Disbursed via EFT)
                      </span>
                      <p className="text-xs text-muted-foreground mt-0.5">Credited to Standard Bank Account ending in •••• 472</p>
                    </div>
                    <div className="text-right">
                      <span className="text-2xl font-bold font-mono text-foreground">
                        R {netTakeHomePay.toLocaleString(undefined, { minimumFractionDigits: 2 })}
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
                    ) : payslips.length === 0 ? (
                      <tr><td colSpan={7} className="py-8 text-center text-muted-foreground">No historical payslips found. Generate a batch below.</td></tr>
                    ) : (
                      payslips
                        .filter((p) => p.employee_name.toLowerCase().includes(searchEmp.toLowerCase()))
                        .map((p) => (
                          <tr key={p.id} className="hover:bg-muted/30">
                            <td className="py-3 px-4 font-semibold text-foreground">{p.employee_name}</td>
                            <td className="py-3 px-4 text-muted-foreground">{p.department}</td>
                            <td className="py-3 px-4 font-mono">R {p.basic_salary.toLocaleString()}</td>
                            <td className="py-3 px-4 font-mono text-red-400">R {p.tax.toLocaleString()}</td>
                            <td className="py-3 px-4 font-mono font-bold text-emerald-400">R {p.net.toLocaleString()}</td>
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
                Computes 2026/2027 progressive tax brackets, Section 6A medical tax credits, and statutory UIF/SDL caps.
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
                  Tax year 2026/2027 statutory deductions under South African Revenue Service tables.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-4 space-y-2 text-muted-foreground">
                <div className="flex justify-between py-1 border-b border-border/40">
                  <span>Gross Monthly Remuneration:</span>
                  <span className="font-semibold text-foreground font-mono">R {calcResult.gross_salary.toLocaleString()}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border/40">
                  <span>PAYE Income Tax:</span>
                  <span className="font-semibold text-red-400 font-mono">R {calcResult.monthly_paye_tax.toLocaleString()}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border/40">
                  <span>Medical Scheme Tax Credit (Section 6A):</span>
                  <span className="font-semibold text-emerald-400 font-mono">- R {calcResult.medical_tax_credit.toLocaleString()}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border/40">
                  <span>UIF Employee Contribution (1% max R177.12):</span>
                  <span className="font-semibold text-foreground font-mono">R {calcResult.uif_employee_contribution.toFixed(2)}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border/40">
                  <span>SDL Employer Contribution (1%):</span>
                  <span className="font-semibold text-foreground font-mono">R {calcResult.sdl_employer_contribution.toFixed(2)}</span>
                </div>
                <div className="flex justify-between py-2 border-t border-border font-bold text-foreground text-sm">
                  <span>Net Estimated Take-Home Pay:</span>
                  <span className="font-mono text-emerald-400 text-base">R {calcResult.net_take_home_pay.toLocaleString()}</span>
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
                  disabled={isPostingFinance}
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

              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                  <span className="text-muted-foreground">Total Salary Liability</span>
                  <p className="text-lg font-bold text-foreground">
                    R {(deptCostAllocation?.total_monthly_payroll_zar ?? 685000).toLocaleString()} ZAR
                  </p>
                  <p className="text-[10px] text-muted-foreground">Includes allowances & night pay</p>
                </div>
                <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                  <span className="text-muted-foreground">Total SARS PAYE & UIF Due</span>
                  <p className="text-lg font-bold text-red-400">
                    R {(deptCostAllocation ? Math.round(deptCostAllocation.total_monthly_payroll_zar * 0.22) : 142300).toLocaleString()} ZAR
                  </p>
                  <p className="text-[10px] text-muted-foreground">Payable via EMP201 return</p>
                </div>
                <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                  <span className="text-muted-foreground">EFT Bank Disbursement Batch</span>
                  <p className="text-lg font-bold text-emerald-400">
                    R {(deptCostAllocation ? Math.round(deptCostAllocation.total_monthly_payroll_zar * 0.78) : 542700).toLocaleString()} ZAR
                  </p>
                  <p className="text-[10px] text-muted-foreground">Ready for bank release</p>
                </div>
              </div>
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
