"use client"

import { useEffect, useMemo, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ModuleLayout } from "./module-layout"
import { useLoadable } from "@/lib/service-fetch"
import { NotConnected } from "@/components/ui/not-connected"
import { RevenueRecognitionPanel } from "./finance/revenue-recognition-panel"
import { ExpenseTrackingPanel } from "./finance/expense-tracking-panel"
import { LiveJournalEntries } from "./finance/live-journal-entries"
import { BankReconciliationPanel } from "./finance/bank-reconciliation-panel"
import { StatementsPanel } from "./finance/statements-panel"
import { ScenarioPlanningPanel } from "./finance/scenario-planning-panel"
import { formatCurrency } from "./finance/utils"
import { BarChart3, Clock, DollarSign, TrendingUp } from "lucide-react"
import {
  getStatements, getCashFlow,
  listRevenueContracts, listExpenseReceipts, listApprovalRequests, listPurchaseOrders,
  listFixedAssets, listRecurringPayments, listBankItems,
  type FinanceOverview, type Statements, type CashFlowStatement, type StatementLineRaw,
  type RevenueContract, type ExpenseReceipt, type ApprovalRequest, type PurchaseOrder,
  type FixedAsset, type RecurringPayment, type BankStatementItem,
} from "@/lib/finance-api"

function toStatementLines(lines: StatementLineRaw[]) {
  return lines
    .filter((l) => l.line !== "")
    .map((l) => ({
      label: l.line,
      amount: typeof l.amount === "number" ? l.amount : 0,
      style: l.section ? ("section" as const) : l.total ? ("total" as const) : l.subtotal ? ("subtotal" as const) : undefined,
      indent: !l.section && !l.total,
    }))
}

const tableColumns = [
  { key: "account", label: "Account" },
  { key: "debit", label: "Debit" },
  { key: "credit", label: "Credit" },
  { key: "balance", label: "Balance" },
]

export function FinanceModule() {
  // Real finance service only. When it is not running the module shows an
  // honest "Service not running" state - no mock KPIs, journals or scenarios.
  const { value: overviewL, reload: reloadOverview } = useLoadable<FinanceOverview>("/svc/finance/overview")
  const overview = overviewL.state === "ready" ? overviewL.data : null
  const serviceReady = overviewL.state === "ready"
  const [activeTab, setActiveTab] = useState("overview")
  const [statements, setStatements] = useState<Statements | null>(null)
  const [cashFlowStmt, setCashFlowStmt] = useState<CashFlowStatement | null>(null)
  const [contracts, setContracts] = useState<RevenueContract[]>([])
  const [receipts, setReceipts] = useState<ExpenseReceipt[]>([])
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([])
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([])
  const [assets, setAssets] = useState<FixedAsset[]>([])
  const [recurringPayments, setRecurringPayments] = useState<RecurringPayment[]>([])
  const [bankItems, setBankItems] = useState<BankStatementItem[]>([])

  useEffect(() => {
    if (!serviceReady) return
    getStatements().then(setStatements)
    getCashFlow().then(setCashFlowStmt)
    listRevenueContracts().then(setContracts)
    listExpenseReceipts().then(setReceipts)
    listApprovalRequests().then(setApprovals)
    listPurchaseOrders().then(setPurchaseOrders)
    listFixedAssets().then(setAssets)
    listRecurringPayments().then(setRecurringPayments)
    listBankItems().then(setBankItems)
  }, [serviceReady])

  const flashcardKPIs = useMemo(() => {
    if (!overview || !cashFlowStmt) return []
    const fcf = cashFlowStmt.operating_activities.total + cashFlowStmt.investing_activities.total
    const ebitMargin = overview.kpis.revenue > 0 ? (overview.kpis.ebit / overview.kpis.revenue) * 100 : 0
    return [
      { id: "1", title: "Revenue (YTD)", value: formatCurrency(overview.kpis.revenue), change: "", changeType: "neutral" as const, icon: <TrendingUp className="h-5 w-5 text-emerald-400" />, backTitle: "Revenue Detail", backDetails: [{ label: "Period", value: overview.period }], backInsight: "Computed from posted GL revenue accounts." },
      { id: "2", title: "EBIT", value: formatCurrency(overview.kpis.ebit), change: `${ebitMargin.toFixed(1)}% margin`, changeType: "neutral" as const, icon: <BarChart3 className="h-5 w-5 text-blue-400" />, backTitle: "EBIT Detail", backDetails: [{ label: "Revenue", value: formatCurrency(overview.kpis.revenue) }, { label: "Expenses", value: formatCurrency(overview.kpis.expenses) }], backInsight: "Revenue minus posted GL expenses." },
      { id: "3", title: "Free Cash Flow", value: formatCurrency(fcf), change: "", changeType: "neutral" as const, icon: <DollarSign className="h-5 w-5 text-amber-400" />, backTitle: "Cash Flow Detail", backDetails: [{ label: "Operating", value: formatCurrency(cashFlowStmt.operating_activities.total) }, { label: "Investing", value: formatCurrency(cashFlowStmt.investing_activities.total) }], backInsight: "Operating cash flow plus investing activities." },
      { id: "4", title: "Cash Position", value: formatCurrency(overview.kpis.cash_position), change: "", changeType: "neutral" as const, icon: <Clock className="h-5 w-5 text-violet-400" />, backTitle: "Cash Detail", backDetails: [{ label: "As of", value: new Date(overview.generated_at).toLocaleDateString() }], backInsight: "GL cash account balance from posted entries." },
    ]
  }, [overview, cashFlowStmt])

  const liveBalanceSheet = useMemo(() => statements ? toStatementLines(statements.balance_sheet) : [], [statements])
  const liveIncomeStatement = useMemo(() => statements ? toStatementLines(statements.income_statement) : [], [statements])
  const liveCashFlowLines = useMemo(() => {
    if (!cashFlowStmt) return []
    return [
      { label: "Operating Cash Flow", amount: cashFlowStmt.operating_activities.total, style: "section" as const },
      { label: "Investing Cash Flow", amount: cashFlowStmt.investing_activities.total, style: "section" as const },
      { label: "Financing Cash Flow", amount: cashFlowStmt.financing_activities.total, style: "section" as const },
      { label: "Net Change in Cash", amount: cashFlowStmt.net_change_in_cash, style: "total" as const },
    ]
  }, [cashFlowStmt])

  const dataSources = ["Sales", "CRM", "Billing", "Network", "Inventory", "HR", "Marketing"]

  return (
    <ModuleLayout
      title="Finance & FP&A"
        icon={<DollarSign className="h-5 w-5" />}
        subtitle="Financial planning, P&L, cash flow, and FP&A reporting"
      flashcardKPIs={flashcardKPIs}
      activities={[]}
      issues={[]}
      summary="Finance Dome consolidates GAAP-aligned statements with revenue recognition, expense governance, bank reconciliation, and FP&A reforecasting. EBITA and EBIT are tracked for telecoms performance, with scenario planning tied to live module inputs."
      tasks={[]}
      aiRecommendations={[]}
      tableData={[]}
      tableColumns={tableColumns}
    >
      {!serviceReady ? (
        <NotConnected loadable={overviewL} service="Finance service" onRetry={reloadOverview} className="py-16" />
      ) : (
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-secondary flex flex-wrap">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="expenses">Expense Tracking</TabsTrigger>
          <TabsTrigger value="journals">Journals & Trial Balance</TabsTrigger>
          <TabsTrigger value="bank">Bank Reconciliation</TabsTrigger>
          <TabsTrigger value="statements">Statements</TabsTrigger>
          <TabsTrigger value="scenario">Scenario Planning</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-6">
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base">Integrated Data Sources</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {dataSources.map((source) => (
                <Badge key={source} variant="outline" className="text-xs">
                  {source}
                </Badge>
              ))}
              <Badge className="badge-success">Adjustments Enabled</Badge>
            </CardContent>
          </Card>
          <RevenueRecognitionPanel
            recognitionSeries={[]}
            contracts={contracts}
          />
        </TabsContent>

        <TabsContent value="expenses" className="mt-4">
          <ExpenseTrackingPanel
            receipts={receipts}
            approvals={approvals}
            purchaseOrders={purchaseOrders}
            assets={assets}
            recurringPayments={recurringPayments}
          />
        </TabsContent>

        <TabsContent value="journals" className="mt-4">
          <LiveJournalEntries />
        </TabsContent>

        <TabsContent value="bank" className="mt-4">
          <BankReconciliationPanel
            bankItems={bankItems}
            auditTrail={[]}
          />
        </TabsContent>

        <TabsContent value="statements" className="mt-4">
          <StatementsPanel
            balanceSheet={liveBalanceSheet}
            incomeStatement={liveIncomeStatement}
            cashFlow={liveCashFlowLines}
          />
        </TabsContent>

        <TabsContent value="scenario" className="mt-4">
          <ScenarioPlanningPanel
            baseRevenue={overview?.kpis.revenue ?? 0}
            baseOpex={overview?.kpis.expenses ?? 0}
            baseCapex={0}
            baseDepreciation={0}
            baseInterest={0}
            taxRate={0.27}
          />
        </TabsContent>
      </Tabs>
      )}
    </ModuleLayout>
  )
}
