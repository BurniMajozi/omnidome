"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Input } from "@/components/ui/input"
import { PageHeader } from "@/components/ui/page-header"
import { TableShell } from "@/components/ui/table-shell"
import { ActionBar } from "@/components/ui/action-bar"
import {
  Receipt,
  CreditCard,
  AlertTriangle,
  CheckCircle,
  Clock,
  TrendingUp,
  TrendingDown,
  Search,
  Download,
  Send,
  Filter,
  MoreVertical,
  Phone,
  Mail,
  Ban,
  RefreshCcw,
  Plus,
} from "lucide-react"
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  Legend,
} from "recharts"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { useModuleData } from "@/lib/module-data"
import { useIsClient } from "@/lib/use-is-client"

const defaultRevenueData = [
  { month: "Jul", collected: 2400000, outstanding: 180000, overdue: 45000 },
  { month: "Aug", collected: 2650000, outstanding: 195000, overdue: 52000 },
  { month: "Sep", collected: 2800000, outstanding: 210000, overdue: 48000 },
  { month: "Oct", collected: 3100000, outstanding: 175000, overdue: 38000 },
  { month: "Nov", collected: 3350000, outstanding: 220000, overdue: 55000 },
  { month: "Dec", collected: 3600000, outstanding: 190000, overdue: 42000 },
]

const defaultPaymentMethodData = [
  { name: "Debit Order", value: 58, color: "#10b981" },
  { name: "EFT", value: 22, color: "#3b82f6" },
  { name: "Card", value: 12, color: "#f59e0b" },
  { name: "Cash", value: 8, color: "#8b5cf6" },
]

const defaultAgingData = [
  { range: "Current", amount: 2850000, customers: 12450 },
  { range: "30 Days", amount: 420000, customers: 1850 },
  { range: "60 Days", amount: 185000, customers: 720 },
  { range: "90 Days", amount: 95000, customers: 380 },
  { range: "120+ Days", amount: 62000, customers: 245 },
]

const defaultInvoices = [
  {
    id: "INV-2024-0012",
    customer: "Thabo Mokoena",
    amount: 899,
    status: "paid",
    date: "2024-01-10",
    method: "Debit Order",
  },
  { id: "INV-2024-0013", customer: "Sipho Ndlovu", amount: 1299, status: "pending", date: "2024-01-11", method: "EFT" },
  {
    id: "INV-2024-0014",
    customer: "Nomvula Dlamini",
    amount: 599,
    status: "overdue",
    date: "2024-01-05",
    method: "Card",
  },
  {
    id: "INV-2024-0015",
    customer: "Johan van der Merwe",
    amount: 1899,
    status: "paid",
    date: "2024-01-12",
    method: "Debit Order",
  },
  { id: "INV-2024-0016", customer: "Lerato Molefe", amount: 799, status: "pending", date: "2024-01-13", method: "EFT" },
  {
    id: "INV-2024-0017",
    customer: "Pieter Botha",
    amount: 2499,
    status: "overdue",
    date: "2024-01-02",
    method: "Card",
  },
]

const defaultCollections = [
  {
    id: 1,
    customer: "Ayanda Zulu",
    amount: 2850,
    daysPastDue: 45,
    lastContact: "2024-01-08",
    status: "in-progress",
    phone: "082 555 1234",
  },
  {
    id: 2,
    customer: "David Smith",
    amount: 1650,
    daysPastDue: 32,
    lastContact: "2024-01-10",
    status: "promise-to-pay",
    phone: "083 666 5678",
  },
  {
    id: 3,
    customer: "Fatima Patel",
    amount: 4200,
    daysPastDue: 68,
    lastContact: "2024-01-05",
    status: "escalated",
    phone: "084 777 9012",
  },
  {
    id: 4,
    customer: "Kagiso Mabaso",
    amount: 980,
    daysPastDue: 21,
    lastContact: "2024-01-12",
    status: "new",
    phone: "085 888 3456",
  },
  {
    id: 5,
    customer: "Linda Nkosi",
    amount: 3500,
    daysPastDue: 95,
    lastContact: "2024-01-01",
    status: "legal",
    phone: "086 999 7890",
  },
]

const formatCurrency = (value: number) => {
  return `R ${value.toLocaleString("en-ZA")}`
}

export function BillingModule() {
  const { data } = useModuleData("billing", {
    revenueData: defaultRevenueData,
    paymentMethodData: defaultPaymentMethodData,
    agingData: defaultAgingData,
    invoices: defaultInvoices,
    collections: defaultCollections,
  })

  const { revenueData, paymentMethodData, agingData, collections } = data
  const [localInvoices, setLocalInvoices] = useState(() => data.invoices)

  const [activeTab, setActiveTab] = useState("overview")
  const [searchTerm, setSearchTerm] = useState("")
  const isClient = useIsClient()

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "paid":
        return <Badge className="badge-success">Paid</Badge>
      case "pending":
        return <Badge className="badge-warning">Pending</Badge>
      case "overdue":
        return <Badge className="badge-danger">Overdue</Badge>
      default:
        return <Badge variant="secondary">{status}</Badge>
    }
  }

  const getCollectionStatus = (status: string) => {
    switch (status) {
      case "new":
        return <Badge className="badge-info">New</Badge>
      case "in-progress":
        return <Badge className="badge-warning">In Progress</Badge>
      case "promise-to-pay":
        return <Badge className="badge-success">Promise to Pay</Badge>
      case "escalated":
        return <Badge className="bg-orange-500/20 text-orange-400">Escalated</Badge>
      case "legal":
        return <Badge className="badge-danger">Legal</Badge>
      default:
        return <Badge variant="secondary">{status}</Badge>
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Receipt className="h-5 w-5" />}
        title="Billing & Collections"
        subtitle="Revenue tracking, invoices, and collections management"
        actions={
          <>
            <Button variant="outline" size="sm"><Download className="h-3.5 w-3.5" />Export</Button>
            <Button variant="cta" size="sm"><Plus className="h-3.5 w-3.5" />New Invoice</Button>
          </>
        }
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Monthly Revenue</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{!isClient ? "R --" : formatCurrency(3600000)}</p>
                <div className="mt-1 flex items-center gap-1 text-emerald-400">
                  <TrendingUp className="h-3 w-3" />
                  <span className="text-xs">+7.5% vs last month</span>
                </div>
              </div>
              <div className="rounded-lg bg-emerald-500/20 p-2">
                <Receipt className="h-5 w-5 text-emerald-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Collection Rate</p>
                <p className="mt-1 text-2xl font-bold text-foreground">94.8%</p>
                <div className="mt-1 flex items-center gap-1 text-emerald-400">
                  <TrendingUp className="h-3 w-3" />
                  <span className="text-xs">+2.1% improvement</span>
                </div>
              </div>
              <div className="rounded-lg bg-blue-500/20 p-2">
                <CheckCircle className="h-5 w-5 text-blue-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Outstanding</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{!isClient ? "R --" : formatCurrency(190000)}</p>
                <div className="mt-1 flex items-center gap-1 text-amber-400">
                  <Clock className="h-3 w-3" />
                  <span className="text-xs">1,245 accounts</span>
                </div>
              </div>
              <div className="rounded-lg bg-amber-500/20 p-2">
                <CreditCard className="h-5 w-5 text-amber-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Overdue Amount</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{!isClient ? "R --" : formatCurrency(42000)}</p>
                <div className="mt-1 flex items-center gap-1 text-red-400">
                  <TrendingDown className="h-3 w-3" />
                  <span className="text-xs">-12% reduced</span>
                </div>
              </div>
              <div className="rounded-lg bg-red-500/20 p-2">
                <AlertTriangle className="h-5 w-5 text-red-400" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-secondary">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="invoices">Invoices</TabsTrigger>
          <TabsTrigger value="collections">Collections</TabsTrigger>
          <TabsTrigger value="aging">Aging Report</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Revenue Chart */}
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base">Revenue Collection Trend</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={revenueData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="month" stroke="#9ca3af" fontSize={12} />
                      <YAxis stroke="#9ca3af" fontSize={12} tickFormatter={(v) => `R${v / 1000000}M`} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }}
                        formatter={(value: number) => formatCurrency(value)}
                      />
                      <Area
                        type="monotone"
                        dataKey="collected"
                        stackId="1"
                        stroke="#10b981"
                        fill="#10b981"
                        fillOpacity={0.3}
                        name="Collected"
                      />
                      <Area
                        type="monotone"
                        dataKey="outstanding"
                        stackId="2"
                        stroke="#f59e0b"
                        fill="#f59e0b"
                        fillOpacity={0.3}
                        name="Outstanding"
                      />
                      <Area
                        type="monotone"
                        dataKey="overdue"
                        stackId="3"
                        stroke="#ef4444"
                        fill="#ef4444"
                        fillOpacity={0.3}
                        name="Overdue"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Payment Methods */}
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base">Payment Methods</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={paymentMethodData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={100}
                        paddingAngle={2}
                        dataKey="value"
                      >
                        {paymentMethodData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }}
                        formatter={(value: number) => `${value}%`}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-4 flex flex-wrap justify-center gap-4">
                  {paymentMethodData.map((item) => (
                    <div key={item.name} className="flex items-center gap-2">
                      <div className="h-3 w-3 rounded-full" style={{ backgroundColor: item.color }} />
                      <span className="text-sm text-muted-foreground">
                        {item.name} ({item.value}%)
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="invoices" className="mt-4">
          <TableShell
            title="Invoices"
            columns={[
              { key: "id", label: "Invoice ID", inputType: "text", defaultValue: `INV-${Date.now()}` },
              { key: "customer", label: "Customer", inputType: "text" },
              { key: "amount", label: "Amount", inputType: "number", render: (v) => formatCurrency(Number(v)) },
              { key: "date", label: "Date", inputType: "date" },
              { key: "method", label: "Method", inputType: "select", options: ["Debit Order", "EFT", "Card", "Cash"] },
              { key: "status", label: "Status", inputType: "select", options: ["paid", "pending", "overdue"], render: (v) => getStatusBadge(String(v)) },
            ]}
            data={localInvoices}
            addLabel="New Invoice"
            onAdd={(rec) => setLocalInvoices((prev) => [rec, ...prev])}
            onDelete={(id) => setLocalInvoices((prev) => prev.filter((r) => r.id !== id))}
            onEdit={(rec) => setLocalInvoices((prev) => prev.map((r) => r.id === rec.id ? rec : r))}
            searchPlaceholder="Search invoices..."
          />
        </TabsContent>

        <TabsContent value="collections" className="mt-4">
          <Card className="border-border bg-card">
            <CardHeader>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <CardTitle className="text-base">Collections Queue</CardTitle>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className="badge-danger">5 Urgent</Badge>
                  <Badge className="badge-warning">12 Follow-up</Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {collections.map((item) => (
                  <div
                    key={item.id}
                    className="flex flex-col gap-4 rounded-lg border border-border bg-secondary/30 p-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="flex items-center gap-4">
                      <div>
                        <p className="font-medium text-foreground">{item.customer}</p>
                        <p className="text-sm text-muted-foreground">{item.phone}</p>
                      </div>
                    </div>
                    <div className="text-left sm:text-center">
                      <p className="font-semibold text-foreground">{!isClient ? "R --" : formatCurrency(item.amount)}</p>
                      <p className="text-xs text-red-400">{item.daysPastDue} days overdue</p>
                    </div>
                    <div className="text-left sm:text-center">
                      <p className="text-sm text-muted-foreground">Last Contact</p>
                      <p className="text-sm text-foreground">{item.lastContact}</p>
                    </div>
                    <div>{getCollectionStatus(item.status)}</div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button variant="outline" size="icon" className="h-8 w-8 bg-transparent">
                        <Phone className="h-4 w-4" />
                      </Button>
                      <Button variant="outline" size="icon" className="h-8 w-8 bg-transparent">
                        <Mail className="h-4 w-4" />
                      </Button>
                      <Button variant="outline" size="icon" className="h-8 w-8 bg-transparent">
                        <Send className="h-4 w-4" />
                      </Button>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem>Log Promise to Pay</DropdownMenuItem>
                          <DropdownMenuItem>Escalate</DropdownMenuItem>
                          <DropdownMenuItem>
                            <Ban className="mr-2 h-4 w-4" />
                            Suspend Service
                          </DropdownMenuItem>
                          <DropdownMenuItem>
                            <RefreshCcw className="mr-2 h-4 w-4" />
                            Payment Arrangement
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="aging" className="mt-4">
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base">Accounts Receivable Aging</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={agingData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="range" stroke="#9ca3af" fontSize={12} />
                    <YAxis stroke="#9ca3af" fontSize={12} tickFormatter={(v) => `R${v / 1000}k`} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }}
                      formatter={(value: number, name: string) => [
                        formatCurrency(value),
                        name === "amount" ? "Amount" : "Customers",
                      ]}
                    />
                    <Legend />
                    <Bar dataKey="amount" name="Outstanding Amount" fill="#10b981" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-6 grid grid-cols-5 gap-4">
                {agingData.map((item) => (
                  <div key={item.range} className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
                    <p className="text-sm text-muted-foreground">{item.range}</p>
                    <p className="mt-1 font-semibold text-foreground">{!isClient ? "R --" : formatCurrency(item.amount)}</p>
                    <p className="text-xs text-muted-foreground">{!isClient ? "--" : item.customers.toLocaleString()} customers</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
