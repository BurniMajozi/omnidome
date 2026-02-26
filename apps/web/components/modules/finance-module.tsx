"use client"

import { useMemo, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ModuleLayout } from "./module-layout"
import { useModuleData } from "@/lib/module-data"
import { RevenueRecognitionPanel } from "./finance/revenue-recognition-panel"
import { ExpenseTrackingPanel } from "./finance/expense-tracking-panel"
import { JournalsTrialBalancePanel } from "./finance/journals-trial-balance-panel"
import { BankReconciliationPanel } from "./finance/bank-reconciliation-panel"
import { StatementsPanel } from "./finance/statements-panel"
import { ScenarioPlanningPanel } from "./finance/scenario-planning-panel"
import { formatCurrency } from "./finance/utils"
import { BarChart3, Clock, DollarSign, TrendingUp } from "lucide-react"

const defaultRecognitionSeries = [
  { period: "Jul", recognized: 3400000, deferred: 6200000, billed: 3900000 },
  { period: "Aug", recognized: 3600000, deferred: 6100000, billed: 4100000 },
  { period: "Sep", recognized: 3850000, deferred: 6000000, billed: 4300000 },
  { period: "Oct", recognized: 4100000, deferred: 5850000, billed: 4550000 },
  { period: "Nov", recognized: 4250000, deferred: 5700000, billed: 4700000 },
  { period: "Dec", recognized: 4480000, deferred: 5520000, billed: 4980000 },
]

const defaultContracts = [
  { contract: "ENT-1008", customer: "Vodacom SA", method: "Straight-line", start: "2025-07-01", end: "2026-06-30", recognized: 5200000, deferred: 1400000 },
  { contract: "ENT-1014", customer: "MTN Group", method: "Milestone", start: "2025-09-01", end: "2026-08-31", recognized: 3200000, deferred: 1800000 },
  { contract: "BUS-2042", customer: "Dimension Data", method: "Straight-line", start: "2025-10-01", end: "2026-09-30", recognized: 2100000, deferred: 900000 },
  { contract: "RES-4501", customer: "Premium Fibre", method: "Straight-line", start: "2025-07-01", end: "2026-06-30", recognized: 1850000, deferred: 650000 },
]

const defaultReceipts = [
  { id: "R-101", vendor: "Hilton Travel", amount: 18250, category: "Travel", status: "processed" as const, ocrConfidence: 97, submittedBy: "T. Molefe", date: "2026-02-02" },
  { id: "R-102", vendor: "Vodacom Roaming", amount: 6940, category: "Travel", status: "flagged" as const, ocrConfidence: 82, submittedBy: "S. Dlamini", date: "2026-02-03" },
  { id: "R-103", vendor: "Office Depot", amount: 4280, category: "Office", status: "processed" as const, ocrConfidence: 95, submittedBy: "L. Naidoo", date: "2026-02-04" },
]

const defaultApprovals = [
  { id: "A-201", request: "Cape Town field visit", amount: 12400, owner: "M. Nkosi", status: "pending" as const, policy: "Travel-DOA-2" },
  { id: "A-202", request: "Network spares procurement", amount: 98000, owner: "K. Zulu", status: "approved" as const, policy: "Capex-DOA-3" },
  { id: "A-203", request: "Executive offsite", amount: 42000, owner: "R. Patel", status: "rejected" as const, policy: "Travel-DOA-4" },
]

const defaultPurchaseOrders = [
  { id: "PO-3301", vendor: "FibreTech", amount: 240000, status: "review" as const, approver: "Finance Ops", dueDate: "2026-02-15" },
  { id: "PO-3302", vendor: "MetroNet", amount: 87000, status: "approved" as const, approver: "CFO", dueDate: "2026-02-10" },
  { id: "PO-3303", vendor: "SignalCore", amount: 54000, status: "draft" as const, approver: "Ops Lead", dueDate: "2026-02-20" },
]

const defaultAssets = [
  { id: "AS-18", asset: "OLT Chassis", location: "Johannesburg", status: "active" as const, cost: 860000, depreciation: 172000, remainingLife: "3.5 years" },
  { id: "AS-19", asset: "Vehicle Fleet", location: "Cape Town", status: "maintenance" as const, cost: 420000, depreciation: 84000, remainingLife: "2.0 years" },
  { id: "AS-20", asset: "Core Router", location: "Durban", status: "active" as const, cost: 360000, depreciation: 72000, remainingLife: "4.0 years" },
]

const defaultRecurringPayments = [
  { id: "RP-1", vendor: "Tower Lease", amount: 68000, frequency: "Monthly", nextRun: "2026-02-28", status: "active" as const },
  { id: "RP-2", vendor: "Transit IP", amount: 42000, frequency: "Monthly", nextRun: "2026-02-26", status: "active" as const },
  { id: "RP-3", vendor: "Insurance", amount: 15500, frequency: "Quarterly", nextRun: "2026-03-31", status: "paused" as const },
]

const defaultJournals = [
  { id: "J-9001", date: "2026-02-01", account: "Accounts Receivable", description: "January invoicing run", debit: 3200000, credit: 0, source: "Billing" },
  { id: "J-9002", date: "2026-02-01", account: "Deferred Revenue", description: "Subscription billing deferral", debit: 0, credit: 3200000, source: "Revenue Recognition" },
  { id: "J-9003", date: "2026-02-03", account: "Travel Expense", description: "Field ops travel", debit: 18500, credit: 0, source: "Expense" },
  { id: "J-9004", date: "2026-02-03", account: "Cash", description: "Travel reimbursement", debit: 0, credit: 18500, source: "Treasury" },
  { id: "J-9005", date: "2026-02-05", account: "Network Capex", description: "OLT chassis purchase", debit: 860000, credit: 0, source: "PO" },
  { id: "J-9006", date: "2026-02-05", account: "Accounts Payable", description: "OLT chassis invoice", debit: 0, credit: 860000, source: "PO" },
]

const defaultTrialBalance = [
  { id: "TB-1", account: "Cash", debit: 8200000, credit: 0 },
  { id: "TB-2", account: "Accounts Receivable", debit: 6400000, credit: 0 },
  { id: "TB-3", account: "Deferred Revenue", debit: 0, credit: 5520000 },
  { id: "TB-4", account: "Network Capex", debit: 41200000, credit: 0 },
  { id: "TB-5", account: "Accounts Payable", debit: 0, credit: 5400000 },
  { id: "TB-6", account: "Long-Term Debt", debit: 0, credit: 18000000 },
  { id: "TB-7", account: "Equity", debit: 0, credit: 20000000 },
  { id: "TB-8", account: "Retained Earnings", debit: 0, credit: 6880000 },
]

const defaultBankItems = [
  { id: "B-101", date: "2026-02-03", description: "Debit order settlements", amount: 2450000, status: "matched" as const, source: "Billing" },
  { id: "B-102", date: "2026-02-03", description: "Vendor payment - FibreTech", amount: -240000, status: "matched" as const, source: "AP" },
  { id: "B-103", date: "2026-02-04", description: "Bank fees", amount: -8200, status: "review" as const, source: "Treasury" },
  { id: "B-104", date: "2026-02-04", description: "Unidentified deposit", amount: 65000, status: "unmatched" as const, source: "Bank" },
]

const defaultAuditTrail = [
  { id: "AT-1", user: "Thandi Molefe", action: "approved", target: "PO-3302", time: "45 minutes ago" },
  { id: "AT-2", user: "Finance Bot", action: "matched", target: "Bank settlement B-101", time: "1 hour ago" },
  { id: "AT-3", user: "Sipho Dlamini", action: "posted", target: "Journal J-9006", time: "2 hours ago" },
  { id: "AT-4", user: "Audit Bot", action: "flagged", target: "Unidentified deposit B-104", time: "Today" },
]

const balanceSheetLines = [
  { label: "Assets", amount: 0, style: "section" as const },
  { label: "Cash", amount: 8200000, indent: true },
  { label: "Accounts Receivable", amount: 6400000, indent: true },
  { label: "Network Capex (PP&E)", amount: 41200000, indent: true },
  { label: "Total Assets", amount: 55800000, style: "total" as const },
  { label: "Liabilities", amount: 0, style: "section" as const },
  { label: "Accounts Payable", amount: 5400000, indent: true },
  { label: "Deferred Revenue", amount: 5520000, indent: true },
  { label: "Long-Term Debt", amount: 18000000, indent: true },
  { label: "Total Liabilities", amount: 28920000, style: "subtotal" as const },
  { label: "Equity", amount: 0, style: "section" as const },
  { label: "Equity", amount: 20000000, indent: true },
  { label: "Retained Earnings", amount: 6880000, indent: true },
  { label: "Total Equity", amount: 26880000, style: "subtotal" as const },
  { label: "Total Liabilities & Equity", amount: 55800000, style: "total" as const },
]

const incomeStatementLines = [
  { label: "Revenue", amount: 48000000, style: "section" as const },
  { label: "Cost of Service", amount: -14000000, indent: true },
  { label: "Gross Profit", amount: 34000000, style: "subtotal" as const },
  { label: "Operating Expenses", amount: -16000000, indent: true },
  { label: "EBITA", amount: 18000000, style: "subtotal" as const },
  { label: "Depreciation & Amortization", amount: -6000000, indent: true },
  { label: "EBIT", amount: 12000000, style: "subtotal" as const },
  { label: "Interest", amount: -1800000, indent: true },
  { label: "Taxes", amount: -2856000, indent: true },
  { label: "Net Income", amount: 9344000, style: "total" as const },
]

const cashFlowLines = [
  { label: "Operating Cash Flow", amount: 15600000, style: "section" as const },
  { label: "Investing Cash Flow", amount: -9000000, style: "section" as const },
  { label: "Financing Cash Flow", amount: -2100000, style: "section" as const },
  { label: "Net Change in Cash", amount: 3600000, style: "total" as const },
]

const defaultFlashcardKPIs = [
  {
    id: "1",
    title: "EBITA Margin",
    value: "38.5%",
    change: "+1.2%",
    changeType: "positive" as const,
    iconKey: "ebitda",
    backTitle: "EBITA Drivers",
    backDetails: [
      { label: "Network Opex", value: "-3.1%" },
      { label: "Scale Impact", value: "+2.4%" },
      { label: "Price Uplifts", value: "+1.8%" },
    ],
    backInsight: "Telecom EBITA trending above plan",
  },
  {
    id: "2",
    title: "EBIT",
    value: formatCurrency(12000000),
    change: "+0.8%",
    changeType: "positive" as const,
    iconKey: "ebit",
    backTitle: "EBIT Bridge",
    backDetails: [
      { label: "EBITA", value: formatCurrency(18000000) },
      { label: "D&A", value: formatCurrency(-6000000) },
      { label: "Net", value: formatCurrency(12000000) },
    ],
    backInsight: "Capex depreciation aligns with plan",
  },
  {
    id: "3",
    title: "Free Cash Flow",
    value: formatCurrency(7800000),
    change: "-2.6%",
    changeType: "negative" as const,
    iconKey: "cash",
    backTitle: "Cash Flow Detail",
    backDetails: [
      { label: "Operating", value: formatCurrency(15600000) },
      { label: "Capex", value: formatCurrency(-9000000) },
      { label: "Financing", value: formatCurrency(-2100000) },
    ],
    backInsight: "Capex spike from network expansion",
  },
  {
    id: "4",
    title: "DSO",
    value: "31 days",
    change: "-4 days",
    changeType: "positive" as const,
    iconKey: "dso",
    backTitle: "Receivables Health",
    backDetails: [
      { label: "Current", value: "84%" },
      { label: "30-60", value: "12%" },
      { label: "60+", value: "4%" },
    ],
    backInsight: "Collections improved after outreach",
  },
]

const financeKpiIconMap: Record<string, React.ReactNode> = {
  ebitda: <TrendingUp className="h-5 w-5 text-emerald-400" />,
  ebita: <TrendingUp className="h-5 w-5 text-emerald-400" />,
  ebit: <BarChart3 className="h-5 w-5 text-blue-400" />,
  cash: <DollarSign className="h-5 w-5 text-amber-400" />,
  dso: <Clock className="h-5 w-5 text-violet-400" />,
}

const defaultActivities = [
  { id: "1", user: "Finance Bot", action: "posted journal", target: "J-9006", time: "10 minutes ago", type: "create" as const },
  { id: "2", user: "Thandi Molefe", action: "approved", target: "PO-3302", time: "45 minutes ago", type: "update" as const },
  { id: "3", user: "Sipho Dlamini", action: "closed period", target: "Jan 2026", time: "2 hours ago", type: "update" as const },
  { id: "4", user: "Audit Bot", action: "flagged", target: "Bank item B-104", time: "Today", type: "assign" as const },
]

const defaultIssues = [
  { id: "1", title: "Bank recon variance of R65,000", severity: "high" as const, status: "open" as const, assignee: "Finance Ops", time: "Active" },
  { id: "2", title: "Unapproved travel request exceeds policy", severity: "medium" as const, status: "in-progress" as const, assignee: "CFO", time: "4 hours ago" },
  { id: "3", title: "Deferred revenue schedule mismatch", severity: "low" as const, status: "resolved" as const, assignee: "Revenue Team", time: "Yesterday" },
]

const defaultTasks = [
  { id: "1", title: "Reforecast Q2 revenue", priority: "urgent" as const, status: "in-progress" as const, dueDate: "Today", assignee: "FP&A" },
  { id: "2", title: "Finalize bank reconciliation", priority: "high" as const, status: "todo" as const, dueDate: "Tomorrow", assignee: "Treasury" },
  { id: "3", title: "Review PO delegation matrix", priority: "normal" as const, status: "todo" as const, dueDate: "This week", assignee: "Finance Ops" },
  { id: "4", title: "Close Feb accruals", priority: "normal" as const, status: "done" as const, dueDate: "Completed", assignee: "Accounting" },
]

const defaultAIRecommendations = [
  { id: "1", title: "Adjust capex schedule", description: "Delay 12% of Q2 network capex to improve free cash flow by R1.4M.", impact: "high" as const, category: "Cash" },
  { id: "2", title: "Optimize travel spend", description: "Apply remote site audit for 9 routes to cut travel expense by 6%.", impact: "medium" as const, category: "Opex" },
  { id: "3", title: "Increase enterprise price uplift", description: "EBITA upside of R2.1M from 1.5% uplift on enterprise contracts.", impact: "high" as const, category: "Revenue" },
]

const defaultTableData = [
  { id: "1", account: "Cash", debit: formatCurrency(8200000), credit: formatCurrency(0), balance: formatCurrency(8200000) },
  { id: "2", account: "Accounts Receivable", debit: formatCurrency(6400000), credit: formatCurrency(0), balance: formatCurrency(6400000) },
  { id: "3", account: "Deferred Revenue", debit: formatCurrency(0), credit: formatCurrency(5520000), balance: formatCurrency(-5520000) },
  { id: "4", account: "Accounts Payable", debit: formatCurrency(0), credit: formatCurrency(5400000), balance: formatCurrency(-5400000) },
  { id: "5", account: "Retained Earnings", debit: formatCurrency(0), credit: formatCurrency(6880000), balance: formatCurrency(-6880000) },
]

const tableColumns = [
  { key: "account", label: "Account" },
  { key: "debit", label: "Debit" },
  { key: "credit", label: "Credit" },
  { key: "balance", label: "Balance" },
]

const defaultFinanceData = {
  recognitionSeries: defaultRecognitionSeries,
  contracts: defaultContracts,
  receipts: defaultReceipts,
  approvals: defaultApprovals,
  purchaseOrders: defaultPurchaseOrders,
  assets: defaultAssets,
  recurringPayments: defaultRecurringPayments,
  journals: defaultJournals,
  trialBalance: defaultTrialBalance,
  bankItems: defaultBankItems,
  auditTrail: defaultAuditTrail,
  balanceSheet: balanceSheetLines,
  incomeStatement: incomeStatementLines,
  cashFlow: cashFlowLines,
  flashcardKPIs: defaultFlashcardKPIs,
  activities: defaultActivities,
  issues: defaultIssues,
  tasks: defaultTasks,
  aiRecommendations: defaultAIRecommendations,
  tableData: defaultTableData,
}

export function FinanceModule() {
  const { data } = useModuleData("finance", defaultFinanceData)
  const [activeTab, setActiveTab] = useState("overview")

  const flashcardKPIs = useMemo(() => {
    const source = (data.flashcardKPIs ?? defaultFlashcardKPIs) as typeof defaultFlashcardKPIs
    return source.map((kpi) => ({
      ...kpi,
      icon: financeKpiIconMap[kpi.iconKey] ?? <BarChart3 className="h-5 w-5 text-primary" />,
    }))
  }, [data.flashcardKPIs])

  const dataSources = ["Sales", "CRM", "Billing", "Network", "Inventory", "HR", "Marketing"]

  return (
    <ModuleLayout
      title="Finance & FP&A"
      flashcardKPIs={flashcardKPIs}
      activities={data.activities ?? defaultActivities}
      issues={data.issues ?? defaultIssues}
      summary="Finance Dome consolidates GAAP-aligned statements with revenue recognition, expense governance, bank reconciliation, and FP&A reforecasting. EBITA and EBIT are tracked for telecoms performance, with scenario planning tied to live module inputs."
      tasks={data.tasks ?? defaultTasks}
      aiRecommendations={data.aiRecommendations ?? defaultAIRecommendations}
      tableData={data.tableData ?? defaultTableData}
      tableColumns={tableColumns}
    >
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
              <Badge className="bg-emerald-500/20 text-emerald-400">Adjustments Enabled</Badge>
            </CardContent>
          </Card>
          <RevenueRecognitionPanel
            recognitionSeries={data.recognitionSeries ?? defaultRecognitionSeries}
            contracts={data.contracts ?? defaultContracts}
          />
        </TabsContent>

        <TabsContent value="expenses" className="mt-4">
          <ExpenseTrackingPanel
            receipts={data.receipts ?? defaultReceipts}
            approvals={data.approvals ?? defaultApprovals}
            purchaseOrders={data.purchaseOrders ?? defaultPurchaseOrders}
            assets={data.assets ?? defaultAssets}
            recurringPayments={data.recurringPayments ?? defaultRecurringPayments}
          />
        </TabsContent>

        <TabsContent value="journals" className="mt-4">
          <JournalsTrialBalancePanel
            journals={data.journals ?? defaultJournals}
            trialBalance={data.trialBalance ?? defaultTrialBalance}
          />
        </TabsContent>

        <TabsContent value="bank" className="mt-4">
          <BankReconciliationPanel
            bankItems={data.bankItems ?? defaultBankItems}
            auditTrail={data.auditTrail ?? defaultAuditTrail}
          />
        </TabsContent>

        <TabsContent value="statements" className="mt-4">
          <StatementsPanel
            balanceSheet={data.balanceSheet ?? balanceSheetLines}
            incomeStatement={data.incomeStatement ?? incomeStatementLines}
            cashFlow={data.cashFlow ?? cashFlowLines}
          />
        </TabsContent>

        <TabsContent value="scenario" className="mt-4">
          <ScenarioPlanningPanel
            baseRevenue={48000000}
            baseOpex={30000000}
            baseCapex={9000000}
            baseDepreciation={6000000}
            baseInterest={1800000}
            taxRate={0.28}
          />
        </TabsContent>
      </Tabs>
    </ModuleLayout>
  )
}
