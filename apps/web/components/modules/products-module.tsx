"use client"
import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Input } from "@/components/ui/input"
import {
  Package,
  Wifi,
  Tv,
  Phone,
  Shield,
  Plus,
  TrendingUp,
  Users,
  DollarSign,
} from "lucide-react"
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
} from "recharts"
import { useIsClient } from "@/lib/use-is-client"
import { MarketWatchView } from "./products/market-watch-view"
import { listPlans, type Plan } from "@/lib/products-api"
import { listProducts, type Product as CatalogueProduct } from "@/lib/catalogue-api"
import { CatalogueTab } from "./products/catalogue/catalogue-tab"
import { EquipmentRegister } from "./products/equipment-register"
import { ProfitabilityPanel } from "./products/profitability-panel"
import { SuppliersTab } from "./suppliers/suppliers-tab"

const formatCurrency = (value: number) => `R ${value.toLocaleString("en-ZA")}`

const categoryColors: Record<string, string> = {
  Fibre: "#10b981",
  LTE: "#3b82f6",
  VoIP: "#f59e0b",
  TV: "#8b5cf6",
}

export function ProductsModule() {
  const [plans, setPlans] = useState<Plan[]>([])
  const [catalogue, setCatalogue] = useState<CatalogueProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState("overview")
  const [pricingTab, setPricingTab] = useState("plans")
  const isClient = useIsClient()

  async function refresh() {
    setLoading(true)
    setPlans(await listPlans())
    listProducts().then(setCatalogue).catch(() => undefined)
    setLoading(false)
  }

  useEffect(() => {
    refresh()
  }, [])

  const getCategoryIcon = (category: string | null) => {
    switch (category) {
      case "Fibre":
        return <Wifi className="h-4 w-4 text-emerald-400" />
      case "LTE":
        return <Wifi className="h-4 w-4 text-blue-400" />
      case "VoIP":
        return <Phone className="h-4 w-4 text-amber-400" />
      case "TV":
        return <Tv className="h-4 w-4 text-purple-400" />
      default:
        return <Package className="h-4 w-4" />
    }
  }

  const totalMRR = plans.reduce((sum, p) => sum + p.mrr, 0)
  const totalSubscribers = plans.reduce((sum, p) => sum + p.subscribers, 0)
  const activeCount = plans.filter((p) => p.is_active).length

  const productMixData = Object.entries(
    plans.reduce((acc: Record<string, number>, p) => {
      const key = p.category ?? "Uncategorized"
      acc[key] = (acc[key] ?? 0) + (totalSubscribers > 0 ? p.subscribers : 1)
      return acc
    }, {})
  ).map(([name, value]) => ({ name, value, color: categoryColors[name] ?? "#a78bfa" }))

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total Products</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{plans.length}</p>
                <p className="mt-1 text-xs text-emerald-400">{activeCount} Active, {plans.length - activeCount} Inactive</p>
              </div>
              <div className="rounded-lg bg-emerald-500/20 p-2">
                <Package className="h-5 w-5 text-emerald-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total Subscribers</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{!isClient ? "--" : totalSubscribers.toLocaleString()}</p>
                <div className="mt-1 flex items-center gap-1 text-muted-foreground">
                  <Users className="h-3 w-3" />
                  <span className="text-xs">Active subscriptions</span>
                </div>
              </div>
              <div className="rounded-lg bg-blue-500/20 p-2">
                <Users className="h-5 w-5 text-blue-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Monthly Recurring Revenue</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{!isClient ? "R --" : formatCurrency(totalMRR)}</p>
                <div className="mt-1 flex items-center gap-1 text-muted-foreground">
                  <TrendingUp className="h-3 w-3" />
                  <span className="text-xs">From active subscriptions</span>
                </div>
              </div>
              <div className="rounded-lg bg-amber-500/20 p-2">
                <DollarSign className="h-5 w-5 text-amber-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Catalogue SKUs</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{catalogue.length}</p>
                <p className="mt-1 text-xs text-muted-foreground">{catalogue.filter((p) => p.status === "active").length} launched, {catalogue.filter((p) => p.status === "draft" || p.status === "in_review").length} in development</p>
              </div>
              <div className="rounded-lg bg-purple-500/20 p-2">
                <Shield className="h-5 w-5 text-purple-400" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div className="flex items-center justify-between">
          <TabsList className="bg-secondary">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="pricing">Pricing</TabsTrigger>
            <TabsTrigger value="catalogue">Catalogue</TabsTrigger>
            <TabsTrigger value="suppliers">Suppliers</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <ProfitabilityPanel />
          <EquipmentRegister />
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base">Product Mix</CardTitle>
            </CardHeader>
            <CardContent>
              {plans.length === 0 ? (
                <p className="py-12 text-center text-sm text-muted-foreground">
                  No products yet. Develop one in the Catalogue tab.
                </p>
              ) : (
                <>
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={productMixData}
                          cx="50%"
                          cy="50%"
                          innerRadius={60}
                          outerRadius={100}
                          paddingAngle={2}
                          dataKey="value"
                        >
                          {productMixData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="mt-4 flex flex-wrap justify-center gap-4">
                    {productMixData.map((item) => (
                      <div key={item.name} className="flex items-center gap-2">
                        <div className="h-3 w-3 rounded-full" style={{ backgroundColor: item.color }} />
                        <span className="text-sm text-muted-foreground">{item.name}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="pricing" className="mt-4">
          <Tabs value={pricingTab} onValueChange={setPricingTab}>
            <TabsList className="bg-secondary">
              <TabsTrigger value="plans">Plan Pricing</TabsTrigger>
              <TabsTrigger value="market">Market Watch</TabsTrigger>
            </TabsList>
            <TabsContent value="plans" className="mt-4">
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base">Price Comparison by Product</CardTitle>
            </CardHeader>
            <CardContent>
              {plans.length === 0 ? (
                <p className="py-12 text-center text-sm text-muted-foreground">No products yet.</p>
              ) : (
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={plans.filter((p) => p.is_active)} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis type="number" stroke="#9ca3af" fontSize={12} tickFormatter={(v) => `R${v}`} />
                      <YAxis type="category" dataKey="name" stroke="#9ca3af" fontSize={11} width={100} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }}
                        formatter={(value: number) => formatCurrency(value)}
                      />
                      <Bar dataKey="price" fill="#10b981" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>
            </TabsContent>
            <TabsContent value="market" className="mt-4">
              <MarketWatchView plans={plans} />
            </TabsContent>
          </Tabs>
        </TabsContent>

        <TabsContent value="catalogue" className="mt-4">
          <CatalogueTab onCatalogueChanged={setCatalogue} />
        </TabsContent>

        <TabsContent value="suppliers" className="mt-4">
          <SuppliersTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
