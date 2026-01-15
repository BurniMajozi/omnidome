"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import {
  Globe,
  Smartphone,
  Bot,
  Layout,
  Wrench,
  Users,
  Settings,
  Eye,
  Edit,
  TrendingUp,
  Activity,
  MapPin,
  Palette,
  Code,
  FileText,
  ImageIcon,
  ExternalLink,
  Plus,
  MoreVertical,
  Play,
  Pause,
} from "lucide-react"
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"

const visitorData = [
  { day: "Mon", website: 2400, customerPortal: 1800, fieldApp: 450, techApp: 320 },
  { day: "Tue", website: 2100, customerPortal: 1650, fieldApp: 480, techApp: 340 },
  { day: "Wed", website: 2800, customerPortal: 2100, fieldApp: 520, techApp: 380 },
  { day: "Thu", website: 3200, customerPortal: 2400, fieldApp: 490, techApp: 350 },
  { day: "Fri", website: 2900, customerPortal: 2200, fieldApp: 510, techApp: 370 },
  { day: "Sat", website: 1800, customerPortal: 1400, fieldApp: 280, techApp: 150 },
  { day: "Sun", website: 1500, customerPortal: 1100, fieldApp: 220, techApp: 120 },
]

const landingPages = [
  {
    id: 1,
    name: "Fibre Promo Q1",
    url: "/promo/fibre-q1",
    status: "published",
    views: 12450,
    conversions: 342,
    rate: "2.7%",
  },
  {
    id: 2,
    name: "Business Solutions",
    url: "/business",
    status: "published",
    views: 8920,
    conversions: 156,
    rate: "1.7%",
  },
  { id: 3, name: "LTE Uncapped Launch", url: "/lte-launch", status: "draft", views: 0, conversions: 0, rate: "-" },
  { id: 4, name: "Referral Program", url: "/refer", status: "published", views: 5640, conversions: 89, rate: "1.6%" },
]

const aiAgents = [
  { id: 1, name: "Customer Support Bot", status: "active", conversations: 4250, resolution: "78%", avgTime: "2.3 min" },
  { id: 2, name: "Sales Assistant", status: "active", conversations: 1820, resolution: "65%", avgTime: "4.1 min" },
  { id: 3, name: "Technical Help Bot", status: "active", conversations: 2340, resolution: "82%", avgTime: "3.5 min" },
  { id: 4, name: "Billing Inquiries", status: "paused", conversations: 890, resolution: "71%", avgTime: "2.8 min" },
]

const fieldSalesStats = {
  activeAgents: 45,
  visitsToday: 128,
  leadsGenerated: 34,
  dealsWon: 12,
}

const technicianStats = {
  activeTechs: 38,
  jobsCompleted: 86,
  avgJobTime: "42 min",
  customerRating: 4.7,
}

export function PortalModule() {
  const [activeTab, setActiveTab] = useState("overview")
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Website Visitors</p>
                <p className="mt-1 text-2xl font-bold text-foreground">16,700</p>
                <div className="mt-1 flex items-center gap-1 text-emerald-400">
                  <TrendingUp className="h-3 w-3" />
                  <span className="text-xs">+12.5% this week</span>
                </div>
              </div>
              <div className="rounded-lg bg-emerald-500/20 p-2">
                <Globe className="h-5 w-5 text-emerald-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">AI Conversations</p>
                <p className="mt-1 text-2xl font-bold text-foreground">9,300</p>
                <div className="mt-1 flex items-center gap-1 text-emerald-400">
                  <Activity className="h-3 w-3" />
                  <span className="text-xs">75% resolution rate</span>
                </div>
              </div>
              <div className="rounded-lg bg-blue-500/20 p-2">
                <Bot className="h-5 w-5 text-blue-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Field Sales Active</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{fieldSalesStats.activeAgents}</p>
                <div className="mt-1 flex items-center gap-1 text-amber-400">
                  <MapPin className="h-3 w-3" />
                  <span className="text-xs">{fieldSalesStats.visitsToday} visits today</span>
                </div>
              </div>
              <div className="rounded-lg bg-amber-500/20 p-2">
                <Users className="h-5 w-5 text-amber-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Technicians Active</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{technicianStats.activeTechs}</p>
                <div className="mt-1 flex items-center gap-1 text-purple-400">
                  <Wrench className="h-3 w-3" />
                  <span className="text-xs">{technicianStats.jobsCompleted} jobs today</span>
                </div>
              </div>
              <div className="rounded-lg bg-purple-500/20 p-2">
                <Wrench className="h-5 w-5 text-purple-400" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-secondary">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="ai-apps">AI Apps</TabsTrigger>
          <TabsTrigger value="website">Website Builder</TabsTrigger>
          <TabsTrigger value="field-sales">Field Sales App</TabsTrigger>
          <TabsTrigger value="technician">Technician App</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Traffic Chart */}
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base">Portal Traffic Overview</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={visitorData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="day" stroke="#9ca3af" fontSize={12} />
                      <YAxis stroke="#9ca3af" fontSize={12} />
                      <Tooltip contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }} />
                      <Area
                        type="monotone"
                        dataKey="website"
                        stroke="#10b981"
                        fill="#10b981"
                        fillOpacity={0.3}
                        name="Website"
                      />
                      <Area
                        type="monotone"
                        dataKey="customerPortal"
                        stroke="#3b82f6"
                        fill="#3b82f6"
                        fillOpacity={0.3}
                        name="Customer Portal"
                      />
                      <Area
                        type="monotone"
                        dataKey="fieldApp"
                        stroke="#f59e0b"
                        fill="#f59e0b"
                        fillOpacity={0.3}
                        name="Field Sales"
                      />
                      <Area
                        type="monotone"
                        dataKey="techApp"
                        stroke="#8b5cf6"
                        fill="#8b5cf6"
                        fillOpacity={0.3}
                        name="Technician"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Quick Stats */}
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base">Platform Status</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-4">
                  <div className="flex items-center gap-3">
                    <div className="rounded-lg bg-emerald-500/20 p-2">
                      <Globe className="h-5 w-5 text-emerald-400" />
                    </div>
                    <div>
                      <p className="font-medium text-foreground">Main Website</p>
                      <p className="text-sm text-muted-foreground">omnidome.co.za</p>
                    </div>
                  </div>
                  <Badge className="bg-emerald-500/20 text-emerald-400">Online</Badge>
                </div>

                <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-4">
                  <div className="flex items-center gap-3">
                    <div className="rounded-lg bg-blue-500/20 p-2">
                      <Bot className="h-5 w-5 text-blue-400" />
                    </div>
                    <div>
                      <p className="font-medium text-foreground">AI Chat System</p>
                      <p className="text-sm text-muted-foreground">4 bots active</p>
                    </div>
                  </div>
                  <Badge className="bg-emerald-500/20 text-emerald-400">Running</Badge>
                </div>

                <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-4">
                  <div className="flex items-center gap-3">
                    <div className="rounded-lg bg-amber-500/20 p-2">
                      <Smartphone className="h-5 w-5 text-amber-400" />
                    </div>
                    <div>
                      <p className="font-medium text-foreground">Field Sales App</p>
                      <p className="text-sm text-muted-foreground">v2.4.1</p>
                    </div>
                  </div>
                  <Badge className="bg-emerald-500/20 text-emerald-400">Live</Badge>
                </div>

                <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-4">
                  <div className="flex items-center gap-3">
                    <div className="rounded-lg bg-purple-500/20 p-2">
                      <Wrench className="h-5 w-5 text-purple-400" />
                    </div>
                    <div>
                      <p className="font-medium text-foreground">Technician App</p>
                      <p className="text-sm text-muted-foreground">v3.1.0</p>
                    </div>
                  </div>
                  <Badge className="bg-emerald-500/20 text-emerald-400">Live</Badge>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="ai-apps" className="mt-4 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-foreground">AI Agents & Chatbots</h3>
            <Button size="sm" className="bg-primary">
              <Plus className="mr-2 h-4 w-4" />
              Create AI Agent
            </Button>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {aiAgents.map((agent) => (
              <Card key={agent.id} className="border-border bg-card">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="rounded-lg bg-blue-500/20 p-2">
                        <Bot className="h-5 w-5 text-blue-400" />
                      </div>
                      <div>
                        <h4 className="font-medium text-foreground">{agent.name}</h4>
                        <Badge
                          className={
                            agent.status === "active"
                              ? "bg-emerald-500/20 text-emerald-400"
                              : "bg-amber-500/20 text-amber-400"
                          }
                        >
                          {agent.status === "active" ? "Active" : "Paused"}
                        </Badge>
                      </div>
                    </div>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem>
                          <Settings className="mr-2 h-4 w-4" />
                          Configure
                        </DropdownMenuItem>
                        <DropdownMenuItem>
                          <Eye className="mr-2 h-4 w-4" />
                          View Logs
                        </DropdownMenuItem>
                        <DropdownMenuItem>
                          {agent.status === "active" ? (
                            <Pause className="mr-2 h-4 w-4" />
                          ) : (
                            <Play className="mr-2 h-4 w-4" />
                          )}
                          {agent.status === "active" ? "Pause" : "Resume"}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                  <div className="mt-4 grid grid-cols-3 gap-4 text-center">
                    <div>
                      <p className="text-lg font-semibold text-foreground">{!mounted ? "--" : agent.conversations.toLocaleString()}</p>
                      <p className="text-xs text-muted-foreground">Conversations</p>
                    </div>
                    <div>
                      <p className="text-lg font-semibold text-foreground">{agent.resolution}</p>
                      <p className="text-xs text-muted-foreground">Resolution</p>
                    </div>
                    <div>
                      <p className="text-lg font-semibold text-foreground">{agent.avgTime}</p>
                      <p className="text-xs text-muted-foreground">Avg Time</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="website" className="mt-4 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-foreground">Landing Pages</h3>
            <Button size="sm" className="bg-primary">
              <Plus className="mr-2 h-4 w-4" />
              Create Page
            </Button>
          </div>

          <Card className="border-border bg-card">
            <CardContent className="p-0">
              <div className="rounded-lg border border-border">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border bg-secondary/50">
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Page Name</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">URL</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Status</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Views</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Conversions</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Rate</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {landingPages.map((page) => (
                      <tr key={page.id} className="border-b border-border last:border-0">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <Layout className="h-4 w-4 text-muted-foreground" />
                            <span className="font-medium text-foreground">{page.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-sm text-muted-foreground">{page.url}</td>
                        <td className="px-4 py-3">
                          <Badge
                            className={
                              page.status === "published"
                                ? "bg-emerald-500/20 text-emerald-400"
                                : "bg-amber-500/20 text-amber-400"
                            }
                          >
                            {page.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-sm text-foreground">{!mounted ? "--" : page.views.toLocaleString()}</td>
                        <td className="px-4 py-3 text-sm text-foreground">{page.conversions}</td>
                        <td className="px-4 py-3 text-sm text-foreground">{page.rate}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1">
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <Eye className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <Edit className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <ExternalLink className="h-4 w-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Website Builder Tools */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
            <Card className="cursor-pointer border-border bg-card transition-colors hover:border-primary/50">
              <CardContent className="flex flex-col items-center p-6 text-center">
                <div className="rounded-lg bg-emerald-500/20 p-3">
                  <Palette className="h-6 w-6 text-emerald-400" />
                </div>
                <h4 className="mt-3 font-medium text-foreground">Theme Editor</h4>
                <p className="mt-1 text-sm text-muted-foreground">Customize colors & fonts</p>
              </CardContent>
            </Card>
            <Card className="cursor-pointer border-border bg-card transition-colors hover:border-primary/50">
              <CardContent className="flex flex-col items-center p-6 text-center">
                <div className="rounded-lg bg-blue-500/20 p-3">
                  <Code className="h-6 w-6 text-blue-400" />
                </div>
                <h4 className="mt-3 font-medium text-foreground">Code Snippets</h4>
                <p className="mt-1 text-sm text-muted-foreground">Add custom scripts</p>
              </CardContent>
            </Card>
            <Card className="cursor-pointer border-border bg-card transition-colors hover:border-primary/50">
              <CardContent className="flex flex-col items-center p-6 text-center">
                <div className="rounded-lg bg-amber-500/20 p-3">
                  <ImageIcon className="h-6 w-6 text-amber-400" />
                </div>
                <h4 className="mt-3 font-medium text-foreground">Media Library</h4>
                <p className="mt-1 text-sm text-muted-foreground">Manage images & files</p>
              </CardContent>
            </Card>
            <Card className="cursor-pointer border-border bg-card transition-colors hover:border-primary/50">
              <CardContent className="flex flex-col items-center p-6 text-center">
                <div className="rounded-lg bg-purple-500/20 p-3">
                  <FileText className="h-6 w-6 text-purple-400" />
                </div>
                <h4 className="mt-3 font-medium text-foreground">SEO Settings</h4>
                <p className="mt-1 text-sm text-muted-foreground">Optimize for search</p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="field-sales" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card className="border-border bg-card lg:col-span-2">
              <CardHeader>
                <CardTitle className="text-base">Field Sales App Settings</CardTitle>
                <CardDescription>Configure mobile app for sales agents</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-foreground">GPS Tracking</Label>
                    <p className="text-sm text-muted-foreground">Track agent location during work hours</p>
                  </div>
                  <Switch defaultChecked />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-foreground">Photo Capture</Label>
                    <p className="text-sm text-muted-foreground">Require photos at customer visits</p>
                  </div>
                  <Switch defaultChecked />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-foreground">Offline Mode</Label>
                    <p className="text-sm text-muted-foreground">Allow data entry without connection</p>
                  </div>
                  <Switch defaultChecked />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-foreground">Lead Assignment</Label>
                    <p className="text-sm text-muted-foreground">Auto-assign leads by territory</p>
                  </div>
                  <Switch defaultChecked />
                </div>
              </CardContent>
            </Card>

            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base">Today's Stats</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
                  <p className="text-2xl font-bold text-foreground">{fieldSalesStats.activeAgents}</p>
                  <p className="text-sm text-muted-foreground">Active Agents</p>
                </div>
                <div className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
                  <p className="text-2xl font-bold text-foreground">{fieldSalesStats.visitsToday}</p>
                  <p className="text-sm text-muted-foreground">Customer Visits</p>
                </div>
                <div className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
                  <p className="text-2xl font-bold text-foreground">{fieldSalesStats.leadsGenerated}</p>
                  <p className="text-sm text-muted-foreground">Leads Generated</p>
                </div>
                <div className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
                  <p className="text-2xl font-bold text-emerald-400">{fieldSalesStats.dealsWon}</p>
                  <p className="text-sm text-muted-foreground">Deals Won</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="technician" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card className="border-border bg-card lg:col-span-2">
              <CardHeader>
                <CardTitle className="text-base">Technician App Settings</CardTitle>
                <CardDescription>Configure mobile app for field technicians</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-foreground">Job Routing</Label>
                    <p className="text-sm text-muted-foreground">Optimize routes automatically</p>
                  </div>
                  <Switch defaultChecked />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-foreground">Inventory Tracking</Label>
                    <p className="text-sm text-muted-foreground">Track parts and equipment</p>
                  </div>
                  <Switch defaultChecked />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-foreground">Customer Signature</Label>
                    <p className="text-sm text-muted-foreground">Require sign-off on completion</p>
                  </div>
                  <Switch defaultChecked />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-foreground">Speed Test Integration</Label>
                    <p className="text-sm text-muted-foreground">Run network tests on-site</p>
                  </div>
                  <Switch defaultChecked />
                </div>
              </CardContent>
            </Card>

            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base">Today's Stats</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
                  <p className="text-2xl font-bold text-foreground">{technicianStats.activeTechs}</p>
                  <p className="text-sm text-muted-foreground">Active Technicians</p>
                </div>
                <div className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
                  <p className="text-2xl font-bold text-foreground">{technicianStats.jobsCompleted}</p>
                  <p className="text-sm text-muted-foreground">Jobs Completed</p>
                </div>
                <div className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
                  <p className="text-2xl font-bold text-foreground">{technicianStats.avgJobTime}</p>
                  <p className="text-sm text-muted-foreground">Avg Job Time</p>
                </div>
                <div className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
                  <div className="flex items-center justify-center gap-1">
                    <p className="text-2xl font-bold text-amber-400">{technicianStats.customerRating}</p>
                    <span className="text-amber-400">★</span>
                  </div>
                  <p className="text-sm text-muted-foreground">Customer Rating</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
