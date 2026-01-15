"use client"

import { useState, useEffect } from "react"
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
  Edit,
  Trash2,
  TrendingUp,
  Users,
  DollarSign,
  Search,
  Filter,
  MoreVertical,
  Copy,
  Eye,
  ToggleLeft,
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
} from "recharts"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"

const subscriptionTrend = [
  { month: "Jul", fibre: 8500, lte: 3200, voip: 1800, tv: 2400 },
  { month: "Aug", fibre: 9100, lte: 3400, voip: 1950, tv: 2600 },
  { month: "Sep", fibre: 9800, lte: 3550, voip: 2100, tv: 2850 },
  { month: "Oct", fibre: 10500, lte: 3700, voip: 2250, tv: 3100 },
  { month: "Nov", fibre: 11200, lte: 3900, voip: 2400, tv: 3350 },
  { month: "Dec", fibre: 12000, lte: 4100, voip: 2550, tv: 3600 },
]

const productMixData = [
  { name: "Fibre", value: 54, color: "#10b981" },
  { name: "LTE", value: 18, color: "#3b82f6" },
  { name: "VoIP", value: 12, color: "#f59e0b" },
  { name: "TV", value: 16, color: "#8b5cf6" },
]

const products = [
  { id: 1, name: "Fibre 50Mbps", category: "Fibre", price: 699, subscribers: 4250, status: "active", mrr: 2970750 },
  { id: 2, name: "Fibre 100Mbps", category: "Fibre", price: 899, subscribers: 3850, status: "active", mrr: 3461150 },
  { id: 3, name: "Fibre 200Mbps", category: "Fibre", price: 1199, subscribers: 2100, status: "active", mrr: 2517900 },
  { id: 4, name: "LTE Uncapped", category: "LTE", price: 599, subscribers: 2450, status: "active", mrr: 1467550 },
  { id: 5, name: "LTE 100GB", category: "LTE", price: 399, subscribers: 1650, status: "active", mrr: 658350 },
  { id: 6, name: "VoIP Basic", category: "VoIP", price: 149, subscribers: 1800, status: "active", mrr: 268200 },
  { id: 7, name: "TV Premium", category: "TV", price: 299, subscribers: 2100, status: "active", mrr: 627900 },
  { id: 8, name: "Fibre 500Mbps", category: "Fibre", price: 1599, status: "draft", subscribers: 0, mrr: 0 },
]

const bundles = [
  {
    id: 1,
    name: "Home Essential",
    products: ["Fibre 50Mbps", "VoIP Basic"],
    price: 799,
    subscribers: 1250,
    discount: "6%",
  },
  {
    id: 2,
    name: "Home Premium",
    products: ["Fibre 100Mbps", "TV Premium", "VoIP Basic"],
    price: 1249,
    subscribers: 850,
    discount: "8%",
  },
  {
    id: 3,
    name: "Business Starter",
    products: ["Fibre 100Mbps", "VoIP Basic"],
    price: 999,
    subscribers: 420,
    discount: "5%",
  },
  {
    id: 4,
    name: "Ultimate Bundle",
    products: ["Fibre 200Mbps", "TV Premium", "VoIP Basic"],
    price: 1549,
    subscribers: 380,
    discount: "10%",
  },
]

const formatCurrency = (value: number) => {
  return `R ${value.toLocaleString("en-ZA")}`
}

export function ProductsModule() {
  const [activeTab, setActiveTab] = useState("overview")
  const [searchTerm, setSearchTerm] = useState("")
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const getCategoryIcon = (category: string) => {
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

  const totalMRR = products.reduce((sum, p) => sum + p.mrr, 0)
  const totalSubscribers = products.reduce((sum, p) => sum + p.subscribers, 0)

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total Products</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{products.length}</p>
                <p className="mt-1 text-xs text-emerald-400">7 Active, 1 Draft</p>
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
                <p className="mt-1 text-2xl font-bold text-foreground">{!mounted ? "--" : totalSubscribers.toLocaleString()}</p>
                <div className="mt-1 flex items-center gap-1 text-emerald-400">
                  <TrendingUp className="h-3 w-3" />
                  <span className="text-xs">+842 this month</span>
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
                <p className="mt-1 text-2xl font-bold text-foreground">{!mounted ? "R --" : formatCurrency(totalMRR)}</p>
                <div className="mt-1 flex items-center gap-1 text-emerald-400">
                  <TrendingUp className="h-3 w-3" />
                  <span className="text-xs">+5.2% growth</span>
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
                <p className="text-sm text-muted-foreground">Active Bundles</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{bundles.length}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {!mounted ? "--" : bundles.reduce((s, b) => s + b.subscribers, 0).toLocaleString()} subscribers
                </p>
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
          <Button size="sm" className="bg-primary">
            <Plus className="mr-2 h-4 w-4" />
            Add Product
          </Button>
        </div>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Subscription Trend */}
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base">Subscription Growth by Product</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={subscriptionTrend}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="month" stroke="#9ca3af" fontSize={12} />
                      <YAxis stroke="#9ca3af" fontSize={12} />
                      <Tooltip contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }} />
                      <Area
                        type="monotone"
                        dataKey="fibre"
                        stackId="1"
                        stroke="#10b981"
                        fill="#10b981"
                        fillOpacity={0.4}
                        name="Fibre"
                      />
                      <Area
                        type="monotone"
                        dataKey="lte"
                        stackId="1"
                        stroke="#3b82f6"
                        fill="#3b82f6"
                        fillOpacity={0.4}
                        name="LTE"
                      />
                      <Area
                        type="monotone"
                        dataKey="voip"
                        stackId="1"
                        stroke="#f59e0b"
                        fill="#f59e0b"
                        fillOpacity={0.4}
                        name="VoIP"
                      />
                      <Area
                        type="monotone"
                        dataKey="tv"
                        stackId="1"
                        stroke="#8b5cf6"
                        fill="#8b5cf6"
                        fillOpacity={0.4}
                        name="TV"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Product Mix */}
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base">Product Mix</CardTitle>
              </CardHeader>
              <CardContent>
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
                      <Tooltip
                        contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }}
                        formatter={(value: number) => `${value}%`}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-4 flex flex-wrap justify-center gap-4">
                  {productMixData.map((item) => (
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

        <TabsContent value="products" className="mt-4">
          <Card className="border-border bg-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Product Catalog</CardTitle>
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      placeholder="Search products..."
                      className="h-9 w-64 bg-secondary pl-9"
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                    />
                  </div>
                  <Button variant="outline" size="sm">
                    <Filter className="mr-2 h-4 w-4" />
                    Filter
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="rounded-lg border border-border">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border bg-secondary/50">
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Product</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Category</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Price</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Subscribers</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">MRR</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Status</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {products.map((product) => (
                      <tr key={product.id} className="border-b border-border last:border-0">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            {getCategoryIcon(product.category)}
                            <span className="font-medium text-foreground">{product.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-sm text-muted-foreground">{product.category}</td>
                        <td className="px-4 py-3 text-sm text-foreground">{!mounted ? "R --" : formatCurrency(product.price)}/mo</td>
                        <td className="px-4 py-3 text-sm text-foreground">{!mounted ? "--" : product.subscribers.toLocaleString()}</td>
                        <td className="px-4 py-3 text-sm text-foreground">{!mounted ? "R --" : formatCurrency(product.mrr)}</td>
                        <td className="px-4 py-3">
                          <Badge
                            className={
                              product.status === "active"
                                ? "bg-emerald-500/20 text-emerald-400"
                                : "bg-amber-500/20 text-amber-400"
                            }
                          >
                            {product.status === "active" ? "Active" : "Draft"}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon" className="h-8 w-8">
                                <MoreVertical className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem>
                                <Eye className="mr-2 h-4 w-4" />
                                View
                              </DropdownMenuItem>
                              <DropdownMenuItem>
                                <Edit className="mr-2 h-4 w-4" />
                                Edit
                              </DropdownMenuItem>
                              <DropdownMenuItem>
                                <Copy className="mr-2 h-4 w-4" />
                                Duplicate
                              </DropdownMenuItem>
                              <DropdownMenuItem>
                                <ToggleLeft className="mr-2 h-4 w-4" />
                                Toggle Status
                              </DropdownMenuItem>
                              <DropdownMenuItem className="text-red-400">
                                <Trash2 className="mr-2 h-4 w-4" />
                                Delete
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="bundles" className="mt-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {bundles.map((bundle) => (
              <Card key={bundle.id} className="border-border bg-card">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-semibold text-foreground">{bundle.name}</h3>
                      <p className="mt-1 text-sm text-muted-foreground">{bundle.products.join(" + ")}</p>
                    </div>
                    <Badge className="bg-emerald-500/20 text-emerald-400">{bundle.discount} off</Badge>
                  </div>
                  <div className="mt-4 flex items-center justify-between">
                    <div>
                      <p className="text-2xl font-bold text-foreground">{!mounted ? "R --" : formatCurrency(bundle.price)}</p>
                      <p className="text-xs text-muted-foreground">per month</p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold text-foreground">{!mounted ? "--" : bundle.subscribers.toLocaleString()}</p>
                      <p className="text-xs text-muted-foreground">subscribers</p>
                    </div>
                  </div>
                  <div className="mt-4 flex gap-2">
                    <Button variant="outline" size="sm" className="flex-1 bg-transparent">
                      Edit
                    </Button>
                    <Button variant="outline" size="sm" className="flex-1 bg-transparent">
                      View Details
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="pricing" className="mt-4">
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base">Price Comparison by Category</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={products.filter((p) => p.status === "active")} layout="vertical">
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
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
