"use client"

import React, { useState, useEffect } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Coins,
  Plus,
  Trash2,
  Edit,
  CheckCircle2,
  ArrowUpRight,
  Target,
  TrendingUp,
  Users,
  X,
  FileCheck,
  Shield,
  Layers,
} from "lucide-react"
import {
  listCommissionRules,
  createCommissionRule,
  updateCommissionRule,
  deleteCommissionRule,
  listCommissionLedger,
  createCommissionRecord,
  updateCommissionStatus,
  deleteCommissionRecord,
  claimSalesCommission,
  type CommissionRule,
  type CommissionRecord,
  type SalesRepMetric,
  type SalesOverviewResponse,
  type Employee,
} from "@/lib/hr-api"

interface SalesCommissionsViewProps {
  salesOverview: SalesOverviewResponse | null
  salesReps: SalesRepMetric[]
  salesLoading: boolean
  salesError: string | null
  employees: Employee[]
  onRefreshSales: () => Promise<void>
}

const COMMON_PRODUCTS = [
  "Fiber Home (FTTH)",
  "Enterprise Leased Line (1Gbps)",
  "Dark Fiber Metro Ring",
  "VoIP Cloud PBX Seat",
  "Wi-Fi 6 Mesh Hardware",
  "Guarding & SLA Response",
  "All Products",
]

const DEPARTMENTS = ["Sales", "Channel Partners", "Technicians", "Operations", "Guarding"]

export function SalesCommissionsView({
  salesOverview,
  salesReps,
  salesLoading,
  salesError,
  employees,
  onRefreshSales,
}: SalesCommissionsViewProps) {
  const [activeTab, setActiveTab] = useState<"rules" | "ledger" | "reps">("rules")

  // Commission Rules state
  const [rules, setRules] = useState<CommissionRule[]>([])
  const [loadingRules, setLoadingRules] = useState(true)
  const [isRuleModalOpen, setIsRuleModalOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<CommissionRule | null>(null)

  // Rule Form state
  const [ruleTierName, setRuleTierName] = useState("")
  const [ruleProduct, setRuleProduct] = useState(COMMON_PRODUCTS[0])
  const [ruleDept, setRuleDept] = useState("Sales")
  const [ruleRate, setRuleRate] = useState<number>(8.0)
  const [ruleThreshold, setRuleThreshold] = useState<number>(0)
  const [ruleDesc, setRuleDesc] = useState("")
  const [isSubmittingRule, setIsSubmittingRule] = useState(false)

  // Commission Ledger state
  const [ledger, setLedger] = useState<CommissionRecord[]>([])
  const [loadingLedger, setLoadingLedger] = useState(true)
  const [isClaimModalOpen, setIsClaimModalOpen] = useState(false)
  const [claimSuccessMsg, setClaimSuccessMsg] = useState<string | null>(null)

  // Claim Form state
  const [claimEmpId, setClaimEmpId] = useState<string>(employees[0]?.id || "")
  const [claimDealName, setClaimDealName] = useState("")
  const [claimProduct, setClaimProduct] = useState(COMMON_PRODUCTS[0])
  const [claimDealAmount, setClaimDealAmount] = useState<number>(25000)
  const [claimRate, setClaimRate] = useState<number>(8.0)
  const [isSubmittingClaim, setIsSubmittingClaim] = useState(false)

  // Load Rules
  const loadRules = async () => {
    setLoadingRules(true)
    try {
      const data = await listCommissionRules()
      setRules(data)
    } catch (err: unknown) {
      console.error("Failed to load commission rules:", err)
    } finally {
      setLoadingRules(false)
    }
  }

  // Load Ledger
  const loadLedger = async () => {
    setLoadingLedger(true)
    try {
      const data = await listCommissionLedger()
      setLedger(data)
    } catch (err: unknown) {
      console.error("Failed to load commission ledger:", err)
    } finally {
      setLoadingLedger(false)
    }
  }

  useEffect(() => {
    loadRules()
    loadLedger()
  }, [])

  // Auto-set commission rate when product changes in deal form
  useEffect(() => {
    const matchingRule = rules.find(
      (r) => r.product_name.toLowerCase() === claimProduct.toLowerCase()
    )
    if (matchingRule) {
      setClaimRate(matchingRule.rate_percent)
    }
  }, [claimProduct, rules])

  // Open Add Rule
  const handleOpenAddRule = () => {
    setEditingRule(null)
    setRuleTierName("")
    setRuleProduct(COMMON_PRODUCTS[0])
    setRuleDept("Sales")
    setRuleRate(8.0)
    setRuleThreshold(0)
    setRuleDesc("")
    setIsRuleModalOpen(true)
  }

  // Open Edit Rule
  const handleOpenEditRule = (rule: CommissionRule) => {
    setEditingRule(rule)
    setRuleTierName(rule.tier_name)
    setRuleProduct(rule.product_name)
    setRuleDept(rule.department)
    setRuleRate(rule.rate_percent)
    setRuleThreshold(rule.min_threshold_zar)
    setRuleDesc(rule.description || "")
    setIsRuleModalOpen(true)
  }

  // Save Rule
  const handleSaveRule = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmittingRule(true)
    try {
      if (editingRule) {
        await updateCommissionRule(editingRule.id, {
          tier_name: ruleTierName,
          product_name: ruleProduct,
          department: ruleDept,
          rate_percent: Number(ruleRate),
          min_threshold_zar: Number(ruleThreshold),
          description: ruleDesc,
        })
      } else {
        await createCommissionRule({
          tier_name: ruleTierName,
          product_name: ruleProduct,
          department: ruleDept,
          rate_percent: Number(ruleRate),
          min_threshold_zar: Number(ruleThreshold),
          description: ruleDesc,
        })
      }
      setIsRuleModalOpen(false)
      loadRules()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to save rule")
    } finally {
      setIsSubmittingRule(false)
    }
  }

  // Delete Rule
  const handleDeleteRule = async (id: string) => {
    if (!confirm("Are you sure you want to delete this commission rule?")) return
    try {
      await deleteCommissionRule(id)
      setRules((prev) => prev.filter((r) => r.id !== id))
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete rule")
    }
  }

  // Save Commission Record
  const handleSaveClaimRecord = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmittingClaim(true)
    try {
      const commAmount = (Number(claimDealAmount) * Number(claimRate)) / 100
      await createCommissionRecord({
        employee_id: claimEmpId || undefined,
        deal_name: claimDealName || "Closed B2B SLA Contract",
        product_name: claimProduct,
        amount_zar: commAmount,
        rate_percent: Number(claimRate),
        status: "PENDING",
      })
      setIsClaimModalOpen(false)
      setClaimDealName("")
      loadLedger()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to log commission claim")
    } finally {
      setIsSubmittingClaim(false)
    }
  }

  // Update Status in Ledger
  const handleUpdateLedgerStatus = async (id: string, newStatus: string) => {
    try {
      await updateCommissionStatus(id, newStatus)
      setLedger((prev) => prev.map((c) => (c.id === id ? { ...c, status: newStatus } : c)))
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to update status")
    }
  }

  // Delete Ledger Record
  const handleDeleteLedgerRecord = async (id: string) => {
    if (!confirm("Delete this commission transaction?")) return
    try {
      await deleteCommissionRecord(id)
      setLedger((prev) => prev.filter((c) => c.id !== id))
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete transaction")
    }
  }

  // Claim to Payroll
  const handleClaimToPayroll = async (repId: string, amount: number) => {
    try {
      const res = await claimSalesCommission({
        employee_id: repId,
        amount_zar: amount,
      })
      setClaimSuccessMsg(
        `Successfully transferred R ${amount.toLocaleString()} commission bonus to next payroll run (Bonus #${res.bonus_id?.slice(0, 8)}).`
      )
      onRefreshSales()
      loadLedger()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to route commission to payroll")
    }
  }

  return (
    <div className="space-y-6">
      {/* ── KPI STATS CARDS ─────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-border bg-background/50 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground font-medium">Active Sales Reps</span>
            <Users className="h-4 w-4 text-sky-400" />
          </div>
          <p className="text-2xl font-bold text-foreground mt-2">
            {salesLoading ? "…" : salesOverview?.sales_rep_count ?? 0}
          </p>
          <span className="text-xs text-muted-foreground">attributed staff</span>
        </div>

        <div className="rounded-lg border border-border bg-background/50 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground font-medium">Active Pipeline</span>
            <Target className="h-4 w-4 text-amber-400" />
          </div>
          <p className="text-2xl font-bold text-foreground mt-2">
            {salesLoading ? "…" : `R ${((salesOverview?.total_pipeline_zar ?? 0) / 1000).toFixed(0)}k`}
          </p>
          <span className="text-xs text-emerald-400 font-medium">+14% vs last mo</span>
        </div>

        <div className="rounded-lg border border-border bg-background/50 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground font-medium">Closed Won Revenue</span>
            <TrendingUp className="h-4 w-4 text-emerald-400" />
          </div>
          <p className="text-2xl font-bold text-foreground mt-2">
            {salesLoading ? "…" : `R ${((salesOverview?.total_won_zar ?? 0) / 1000).toFixed(0)}k`}
          </p>
          <span className="text-xs text-emerald-400 font-medium">+22% win velocity</span>
        </div>

        <div className="rounded-lg border border-border bg-background/50 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground font-medium">Pending Commissions</span>
            <Coins className="h-4 w-4 text-yellow-400" />
          </div>
          <p className="text-2xl font-bold text-yellow-400 mt-2">
            {salesLoading ? "…" : `R ${(salesOverview?.total_commissions_pending_zar ?? 0).toLocaleString()}`}
          </p>
          <span className="text-xs text-muted-foreground">ready for payroll route</span>
        </div>
      </div>

      {claimSuccessMsg && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-4 text-sm text-emerald-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            <span>{claimSuccessMsg}</span>
          </div>
          <Button size="sm" variant="ghost" onClick={() => setClaimSuccessMsg(null)} className="h-7 text-xs">
            Dismiss
          </Button>
        </div>
      )}

      {/* ── MAIN CARD WITH NAVIGATION TABS ───────────────────────────── */}
      <Card className="border-border">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-4">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Coins className="h-5 w-5 text-amber-400" />
              Sales Incentive & Commission Management Journey
            </CardTitle>
            <CardDescription>
              Configure commission rates per product and department, track deal attribution, and push approved commissions to payroll.
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={handleOpenAddRule}>
              <Plus className="h-4 w-4 mr-1" />
              Configure Rule
            </Button>
            <Button size="sm" variant="cta" onClick={() => setIsClaimModalOpen(true)}>
              <Plus className="h-4 w-4 mr-1" />
              Log Deal Claim
            </Button>
          </div>
        </CardHeader>

        {/* Tab Selection */}
        <div className="flex border-b border-border px-6 pt-3 gap-2">
          <button
            type="button"
            onClick={() => setActiveTab("rules")}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "rules"
                ? "border-amber-500 text-amber-400 font-semibold"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Commission Rules & Tiers ({rules.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("ledger")}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ml-4 ${
              activeTab === "ledger"
                ? "border-amber-500 text-amber-400 font-semibold"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Transactions Ledger ({ledger.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("reps")}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ml-4 ${
              activeTab === "reps"
                ? "border-amber-500 text-amber-400 font-semibold"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Sales Rep Performance ({salesReps.length})
          </button>
        </div>

        <CardContent className="pt-6">
          {/* ── TAB 1: COMMISSION RULES ───────────────────────────────── */}
          {activeTab === "rules" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Rules automatically govern rate calculation for deals logged by sales and technicians.</span>
                <span className="font-semibold text-foreground">{rules.length} active rules configured</span>
              </div>

              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full min-w-[700px] text-sm">
                  <thead className="bg-muted/40 text-xs text-muted-foreground border-b border-border">
                    <tr>
                      <th className="py-2.5 px-3 text-left font-medium">Rule Tier</th>
                      <th className="py-2.5 px-3 text-left font-medium">Product / Service</th>
                      <th className="py-2.5 px-3 text-left font-medium">Department</th>
                      <th className="py-2.5 px-3 text-right font-medium">Commission Rate</th>
                      <th className="py-2.5 px-3 text-right font-medium">Min Threshold (ZAR)</th>
                      <th className="py-2.5 px-3 text-center font-medium">Status</th>
                      <th className="py-2.5 px-3 text-right font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {loadingRules ? (
                      <tr>
                        <td colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                          Loading commission rules…
                        </td>
                      </tr>
                    ) : rules.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                          No rules defined. Click <strong>Configure Rule</strong> to create commission structures.
                        </td>
                      </tr>
                    ) : (
                      rules.map((rule) => (
                        <tr key={rule.id} className="hover:bg-muted/20 transition-colors">
                          <td className="py-3 px-3 font-semibold text-foreground">{rule.tier_name}</td>
                          <td className="py-3 px-3">
                            <Badge variant="outline" className="text-xs bg-muted/40 font-normal">
                              {rule.product_name}
                            </Badge>
                          </td>
                          <td className="py-3 px-3 text-muted-foreground">{rule.department}</td>
                          <td className="py-3 px-3 text-right font-bold text-amber-400">
                            {rule.rate_percent.toFixed(1)}%
                          </td>
                          <td className="py-3 px-3 text-right text-muted-foreground">
                            {rule.min_threshold_zar > 0 ? `R ${rule.min_threshold_zar.toLocaleString()}` : "No minimum"}
                          </td>
                          <td className="py-3 px-3 text-center">
                            <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-xs">
                              Active
                            </Badge>
                          </td>
                          <td className="py-3 px-3 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                                onClick={() => handleOpenEditRule(rule)}
                                title="Edit rule"
                              >
                                <Edit className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 w-7 p-0 text-muted-foreground hover:text-red-400"
                                onClick={() => handleDeleteRule(rule.id)}
                                title="Delete rule"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── TAB 2: TRANSACTIONS LEDGER ────────────────────────────── */}
          {activeTab === "ledger" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>All deal commission transactions logged and their journey to payroll approval.</span>
                <span className="font-semibold text-foreground">{ledger.length} claims recorded</span>
              </div>

              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full min-w-[760px] text-sm">
                  <thead className="bg-muted/40 text-xs text-muted-foreground border-b border-border">
                    <tr>
                      <th className="py-2.5 px-3 text-left font-medium">Rep / Earner</th>
                      <th className="py-2.5 px-3 text-left font-medium">Deal Reference</th>
                      <th className="py-2.5 px-3 text-left font-medium">Product Category</th>
                      <th className="py-2.5 px-3 text-right font-medium">Commission ZAR</th>
                      <th className="py-2.5 px-3 text-center font-medium">Status</th>
                      <th className="py-2.5 px-3 text-right font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {loadingLedger ? (
                      <tr>
                        <td colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                          Loading transactions ledger…
                        </td>
                      </tr>
                    ) : ledger.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                          No commission claims logged yet. Click <strong>Log Deal Claim</strong> to record one.
                        </td>
                      </tr>
                    ) : (
                      ledger.map((item) => {
                        const isPending = item.status === "PENDING"
                        const isApproved = item.status === "APPROVED"
                        const isClaimed = item.status === "CLAIMED_TO_PAYROLL"
                        return (
                          <tr key={item.id} className="hover:bg-muted/20 transition-colors">
                            <td className="py-3 px-3">
                              <p className="font-medium text-foreground">{item.employee_name || "Sales Rep"}</p>
                              {item.employee_code && (
                                <p className="text-xs text-muted-foreground">{item.employee_code}</p>
                              )}
                            </td>
                            <td className="py-3 px-3 font-medium text-foreground">{item.deal_name}</td>
                            <td className="py-3 px-3">
                              <Badge variant="outline" className="text-xs bg-muted/30">
                                {item.product_name}
                              </Badge>
                            </td>
                            <td className="py-3 px-3 text-right font-bold text-amber-400">
                              R {item.amount_zar.toLocaleString()}
                            </td>
                            <td className="py-3 px-3 text-center">
                              <Badge
                                variant="outline"
                                className={`text-xs ${
                                  isClaimed
                                    ? "border-sky-500/40 text-sky-400 bg-sky-500/10"
                                    : isApproved
                                    ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
                                    : "border-amber-500/40 text-amber-400 bg-amber-500/10"
                                }`}
                              >
                                {item.status.replace(/_/g, " ")}
                              </Badge>
                            </td>
                            <td className="py-3 px-3 text-right">
                              <div className="flex items-center justify-end gap-1.5">
                                {isPending && (
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="h-7 text-xs"
                                    onClick={() => handleUpdateLedgerStatus(item.id, "APPROVED")}
                                  >
                                    Approve
                                  </Button>
                                )}
                                {isApproved && item.employee_id && (
                                  <Button
                                    size="sm"
                                    variant="cta"
                                    className="h-7 text-xs"
                                    onClick={() => handleClaimToPayroll(item.employee_id!, item.amount_zar)}
                                  >
                                    Send to Payroll
                                  </Button>
                                )}
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-7 w-7 p-0 text-muted-foreground hover:text-red-400"
                                  onClick={() => handleDeleteLedgerRecord(item.id)}
                                  title="Delete record"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              </div>
                            </td>
                          </tr>
                        )
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── TAB 3: SALES REPS LEADERBOARD ─────────────────────────── */}
          {activeTab === "reps" && (
            <div className="space-y-4">
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full min-w-[760px] text-sm">
                  <thead className="bg-muted/40 text-xs text-muted-foreground border-b border-border">
                    <tr>
                      <th className="py-2.5 px-3 text-left font-medium">Sales Rep</th>
                      <th className="py-2.5 px-3 text-left font-medium">Role & Dept</th>
                      <th className="py-2.5 px-3 text-center font-medium">Deals Won</th>
                      <th className="py-2.5 px-3 text-right font-medium">Pipeline</th>
                      <th className="py-2.5 px-3 text-right font-medium">Won Revenue</th>
                      <th className="py-2.5 px-3 text-right font-medium">Accrued Commission</th>
                      <th className="py-2.5 px-3 text-right font-medium">Payroll Routing</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {salesLoading ? (
                      <tr>
                        <td colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                          Loading sales force metrics…
                        </td>
                      </tr>
                    ) : salesReps.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                          No sales reps with attributed deals.
                        </td>
                      </tr>
                    ) : (
                      salesReps.map((rep) => (
                        <tr key={rep.employee_id} className="hover:bg-muted/20 transition-colors">
                          <td className="py-3 px-3 font-semibold text-foreground">{rep.full_name}</td>
                          <td className="py-3 px-3 text-muted-foreground">
                            {rep.job_title} ({rep.department})
                          </td>
                          <td className="py-3 px-3 text-center">
                            <span className="font-bold text-emerald-400">{rep.deals_won_count}</span>
                            <span className="text-muted-foreground text-xs"> / {rep.deals_count}</span>
                          </td>
                          <td className="py-3 px-3 text-right text-muted-foreground">
                            R {rep.pipeline_zar.toLocaleString()}
                          </td>
                          <td className="py-3 px-3 text-right font-semibold text-emerald-400">
                            R {rep.deals_won_zar.toLocaleString()}
                          </td>
                          <td className="py-3 px-3 text-right font-bold text-amber-400">
                            R {rep.pending_commission_zar.toLocaleString()}
                          </td>
                          <td className="py-3 px-3 text-right">
                            <Button
                              size="sm"
                              variant={rep.pending_commission_zar > 0 ? "cta" : "outline"}
                              disabled={rep.pending_commission_zar <= 0}
                              className="h-7 text-xs"
                              onClick={() => handleClaimToPayroll(rep.employee_id, rep.pending_commission_zar)}
                            >
                              Route to Payroll
                            </Button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── MODAL: CONFIGURE COMMISSION RULE ─────────────────────────── */}
      {isRuleModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="bg-background rounded-lg border border-border max-w-md w-full p-5 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <Coins className="h-4 w-4 text-amber-400" />
                {editingRule ? "Edit Commission Rule" : "Add Commission Rule"}
              </h3>
              <Button size="icon" variant="ghost" onClick={() => setIsRuleModalOpen(false)} className="h-7 w-7">
                <X className="h-4 w-4" />
              </Button>
            </div>

            <form onSubmit={handleSaveRule} className="space-y-3.5 text-sm">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Tier / Rule Name</label>
                <Input
                  value={ruleTierName}
                  onChange={(e) => setRuleTierName(e.target.value)}
                  placeholder="e.g. Fiber FTTH Residential Commission"
                  required
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Product / Offering</label>
                <select
                  value={ruleProduct}
                  onChange={(e) => setRuleProduct(e.target.value)}
                  className="w-full h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-amber-500"
                >
                  {COMMON_PRODUCTS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Department</label>
                <select
                  value={ruleDept}
                  onChange={(e) => setRuleDept(e.target.value)}
                  className="w-full h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-amber-500"
                >
                  {DEPARTMENTS.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Commission Rate (%)</label>
                  <Input
                    type="number"
                    step="0.5"
                    min="0"
                    max="100"
                    value={ruleRate}
                    onChange={(e) => setRuleRate(parseFloat(e.target.value) || 0)}
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Min Deal Threshold (ZAR)</label>
                  <Input
                    type="number"
                    step="1000"
                    min="0"
                    value={ruleThreshold}
                    onChange={(e) => setRuleThreshold(parseFloat(e.target.value) || 0)}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Description / Notes</label>
                <textarea
                  value={ruleDesc}
                  onChange={(e) => setRuleDesc(e.target.value)}
                  placeholder="Optional details on quarterly caps or partner criteria…"
                  rows={2}
                  className="w-full rounded-md border border-border bg-background p-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-amber-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-border">
                <Button type="button" variant="ghost" onClick={() => setIsRuleModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" variant="cta" disabled={isSubmittingRule}>
                  {isSubmittingRule ? "Saving…" : "Save Rule"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: LOG COMMISSION CLAIM / DEAL ───────────────────────── */}
      {isClaimModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="bg-background rounded-lg border border-border max-w-md w-full p-5 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <Plus className="h-4 w-4 text-emerald-400" />
                Log Commission Deal Attribution
              </h3>
              <Button size="icon" variant="ghost" onClick={() => setIsClaimModalOpen(false)} className="h-7 w-7">
                <X className="h-4 w-4" />
              </Button>
            </div>

            <form onSubmit={handleSaveClaimRecord} className="space-y-3.5 text-sm">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Sales Rep / Attributed Staff</label>
                <select
                  value={claimEmpId}
                  onChange={(e) => setClaimEmpId(e.target.value)}
                  className="w-full h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  required
                >
                  {employees.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.full_name} ({e.job_title} - {e.department})
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Deal Reference / Client Name</label>
                <Input
                  value={claimDealName}
                  onChange={(e) => setClaimDealName(e.target.value)}
                  placeholder="e.g. Discovery Health 1Gbps Dedicated Fiber SLA"
                  required
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Product Category</label>
                <select
                  value={claimProduct}
                  onChange={(e) => setClaimProduct(e.target.value)}
                  className="w-full h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-emerald-500"
                >
                  {COMMON_PRODUCTS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Deal Value (ZAR)</label>
                  <Input
                    type="number"
                    step="1000"
                    min="1"
                    value={claimDealAmount}
                    onChange={(e) => setClaimDealAmount(parseFloat(e.target.value) || 0)}
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Applied Rate (%)</label>
                  <Input
                    type="number"
                    step="0.5"
                    min="0"
                    max="100"
                    value={claimRate}
                    onChange={(e) => setClaimRate(parseFloat(e.target.value) || 0)}
                    required
                  />
                </div>
              </div>

              <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
                <p className="text-xs text-muted-foreground">Calculated Commission to be Earned:</p>
                <p className="text-lg font-bold text-amber-400 mt-0.5">
                  R {(((claimDealAmount || 0) * (claimRate || 0)) / 100).toLocaleString()}
                </p>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-border">
                <Button type="button" variant="ghost" onClick={() => setIsClaimModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" variant="cta" disabled={isSubmittingClaim}>
                  {isSubmittingClaim ? "Logging…" : "Log Claim"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
