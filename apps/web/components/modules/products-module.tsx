"use client"
import { TableShell } from "@/components/ui/table-shell"

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
import { listPlans, createPlan, listBundles, createBundle, type Plan, type Bundle } from "@/lib/products-api"

const formatCurrency = (value: number) => `R ${value.toLocaleString("en-ZA")}`

const categoryColors: Record<string, string> = {
  Fibre: "#10b981",
  LTE: "#3b82f6",
  VoIP: "#f59e0b",
  TV: "#8b5cf6",
}

export function ProductsModule() {
  const [plans, setPlans] = useState<Plan[]>([])
  const [bundles, setBundles] = useState<Bundle[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState("overview")
  const [showAddBundle, setShowAddBundle] = useState(false)
  const [newBundle, setNewBundle] = useState({ name: "", discount_pct: "5", plan_ids: [] as string[] })
  const isClient = useIsClient()

  async function refresh() {
    setLoading(true)
    const [p, b] = await Promise.all([listPlans(), listBundles()])
    setPlans(p)
    setBundles(b)
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

  async function handleAddPlan(rec: Plan) {
    await createPlan({
      name: rec.name ?? "",
      category: rec.category ?? undefined,
      price: Number(rec.price) || 0,
    })
    await refresh()
  }

  async function handleAddBundle() {
    if (!newBundle.name || newBundle.plan_ids.length === 0) return
    await createBundle({
      name: newBundle.name,
      discount_pct: Number(newBundle.discount_pct) || 0,
      plan_ids: newBundle.plan_ids,
    })
    setShowAddBundle(false)
    setNewBundle({ name: "", discount_pct: "5", plan_ids: [] })
    await refresh()
  }

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
                <p className="text-sm text-muted-foreground">Bundles</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{bundles.length}</p>
                <p className="mt-1 text-xs text-muted-foreground">Multi-plan packages</p>
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
            <TabsTrigger value="products">Products</TabsTrigger>
            <TabsTrigger value="bundles">Bundles</TabsTrigger>
            <TabsTrigger value="pricing">Pricing</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base">Product Mix</CardTitle>
            </CardHeader>
            <CardContent>
              {plans.length === 0 ? (
                <p className="py-12 text-center text-sm text-muted-foreground">
                  No products yet. Add one from the Products tab.
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

        <TabsContent value="products" className="mt-4">
          <TableShell
            title="Product Catalog"
            columns={[
              { key: "name", label: "Product Name", inputType: "text" },
              { key: "category", label: "Category", inputType: "select", options: ["Fibre", "LTE", "VoIP", "TV"] },
              { key: "price", label: "Price/mo (R)", inputType: "number", render: (v) => `R ${Number(v).toLocaleString()}` },
              { key: "subscribers", label: "Subscribers", inputType: "number", render: (v) => Number(v).toLocaleString() },
              { key: "mrr", label: "MRR (R)", inputType: "number", render: (v) => `R ${Number(v).toLocaleString()}` },
              { key: "is_active", label: "Status", render: (v) => (
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${v ? "bg-emerald-500/20 text-emerald-400" : "bg-amber-500/20 text-amber-400"}`}>
                  {v ? "Active" : "Inactive"}
                </span>
              )},
            ]}
            data={plans}
            addLabel="New Product"
            onAdd={handleAddPlan}
            searchPlaceholder="Search products..."
          />
        </TabsContent>

        <TabsContent value="bundles" className="mt-4 space-y-4">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowAddBundle(true)}>
              <Plus className="mr-2 h-4 w-4" /> New Bundle
            </Button>
          </div>

          {showAddBundle && (
            <Card className="border-border bg-card">
              <CardHeader><CardTitle className="text-sm">Create Bundle</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <Input placeholder="Bundle name" value={newBundle.name} onChange={(e) => setNewBundle({ ...newBundle, name: e.target.value })} />
                <Input placeholder="Discount %" type="number" value={newBundle.discount_pct} onChange={(e) => setNewBundle({ ...newBundle, discount_pct: e.target.value })} />
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">Select plans to include:</p>
                  {plans.map((p) => (
                    <label key={p.id} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={newBundle.plan_ids.includes(p.id)}
                        onChange={(e) => {
                          setNewBundle((prev) => ({
                            ...prev,
                            plan_ids: e.target.checked ? [...prev.plan_ids, p.id] : prev.plan_ids.filter((id) => id !== p.id),
                          }))
                        }}
                      />
                      {p.name} ({formatCurrency(p.price)})
                    </label>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleAddBundle}>Create</Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowAddBundle(false)}>Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {bundles.length === 0 ? (
            <Card className="border-border bg-card">
              <CardContent className="py-12 text-center text-sm text-muted-foreground">No bundles yet.</CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {bundles.map((bundle) => (
                <Card key={bundle.id} className="border-border bg-card">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="font-semibold text-foreground">{bundle.name}</h3>
                        <p className="mt-1 text-sm text-muted-foreground">{bundle.products.join(" + ")}</p>
                      </div>
                      <Badge className="badge-success">{bundle.discount_pct}% off</Badge>
                    </div>
                    <div className="mt-4 flex items-center justify-between">
                      <div>
                        <p className="text-2xl font-bold text-foreground">{!isClient ? "R --" : formatCurrency(bundle.price)}</p>
                        <p className="text-xs text-muted-foreground">per month</p>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold text-foreground">{!isClient ? "--" : bundle.subscribers.toLocaleString()}</p>
                        <p className="text-xs text-muted-foreground">subscribers</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="pricing" className="mt-4">
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
      </Tabs>
    </div>
  )
}
