"use client"

import { useState, useCallback, useEffect } from "react"
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell,
} from "recharts"
import {
  FlaskConical, Play, Pause, Copy, TrendingUp, TrendingDown,
  CheckCircle, XCircle, AlertTriangle, BarChart3, Users, Target,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"

// ── Types ─────────────────────────────────────────────────────────────

interface ABTestVariant {
  id: string
  name: string
  journey_id: string
  journey_name: string
  traffic_percentage: number
  stats: {
    triggered: number
    accepted: number
    rejected: number
    conversion_rate: number
    revenue_preserved: number
  }
}

interface ABTest {
  id: string
  name: string
  status: "running" | "paused" | "completed"
  created_at: string
  variants: ABTestVariant[]
  winner_variant_id: string | null
  confidence_level: number
  min_sample_size: number
  primary_metric: "conversion_rate" | "revenue_preserved"
}

// ── Mock data (replace with API calls when endpoints are live) ────────

const mockABTests: ABTest[] = [
  {
    id: "ab-1",
    name: "Cancel Save — Discount vs Upgrade Offer",
    status: "running",
    created_at: "2026-05-15T10:00:00Z",
    winner_variant_id: null,
    confidence_level: 0,
    min_sample_size: 200,
    primary_metric: "conversion_rate",
    variants: [
      {
        id: "v-a",
        name: "Variant A: 20% Discount",
        journey_id: "j-1",
        journey_name: "Discount Save Journey",
        traffic_percentage: 50,
        stats: {
          triggered: 186,
          accepted: 42,
          rejected: 144,
          conversion_rate: 22.6,
          revenue_preserved: 312400,
        },
      },
      {
        id: "v-b",
        name: "Variant B: Free Upgrade",
        journey_id: "j-2",
        journey_name: "Upgrade Save Journey",
        traffic_percentage: 50,
        stats: {
          triggered: 192,
          accepted: 51,
          rejected: 141,
          conversion_rate: 26.6,
          revenue_preserved: 398700,
        },
      },
    ],
  },
  {
    id: "ab-2",
    name: "Win-back — Email vs SMS Channel",
    status: "completed",
    created_at: "2026-04-01T08:00:00Z",
    winner_variant_id: "v-d",
    confidence_level: 96.2,
    min_sample_size: 500,
    primary_metric: "conversion_rate",
    variants: [
      {
        id: "v-c",
        name: "Variant C: Email Win-back",
        journey_id: "j-3",
        journey_name: "Email Win-back Journey",
        traffic_percentage: 50,
        stats: {
          triggered: 523,
          accepted: 78,
          rejected: 445,
          conversion_rate: 14.9,
          revenue_preserved: 284500,
        },
      },
      {
        id: "v-d",
        name: "Variant D: SMS Win-back",
        journey_id: "j-4",
        journey_name: "SMS Win-back Journey",
        traffic_percentage: 50,
        stats: {
          triggered: 518,
          accepted: 114,
          rejected: 404,
          conversion_rate: 22.0,
          revenue_preserved: 412800,
        },
      },
    ],
  },
]

// ── helpers ───────────────────────────────────────────────────────────

function getStatusBadge(status: string) {
  switch (status) {
    case "running":
      return <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">
        <span className="relative flex h-2 w-2 mr-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
        </span>
        Running
      </Badge>
    case "completed":
      return <Badge className="bg-blue-500/20 text-blue-400">Completed</Badge>
    case "paused":
      return <Badge className="bg-amber-500/20 text-amber-400">Paused</Badge>
    default:
      return <Badge variant="secondary">{status}</Badge>
  }
}

function getConfidenceColor(confidence: number) {
  if (confidence >= 95) return "text-emerald-400"
  if (confidence >= 80) return "text-amber-400"
  return "text-red-400"
}

// ── Variant comparison chart ──────────────────────────────────────────

function VariantComparisonChart({ variants, metric }: { variants: ABTestVariant[]; metric: string }) {
  const data = variants.map((v) => ({
    name: v.name.split(":")[1]?.trim() || v.name,
    conversion_rate: v.stats.conversion_rate,
    revenue_preserved: v.stats.revenue_preserved / 1000,
    accepted: v.stats.accepted,
    rejected: v.stats.rejected,
  }))

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis dataKey="name" stroke="#888" fontSize={11} />
        <YAxis stroke="#888" fontSize={11} />
        <Tooltip contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }} />
        <Legend />
        <Bar dataKey="conversion_rate" fill="#4ade80" name="Conversion Rate %" radius={[4, 4, 0, 0]} />
        <Bar dataKey="revenue_preserved" fill="#60a5fa" name="Revenue Preserved (K)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Funnel chart for a single variant ─────────────────────────────────

function VariantFunnel({ variant }: { variant: ABTestVariant }) {
  const data = [
    { name: "Triggered", value: variant.stats.triggered, fill: "#a855f7" },
    { name: "Accepted", value: variant.stats.accepted, fill: "#4ade80" },
    { name: "Rejected", value: variant.stats.rejected, fill: "#ef4444" },
  ]

  return (
    <div className="space-y-2">
      {data.map((item, i) => {
        const pct = variant.stats.triggered > 0 ? (item.value / variant.stats.triggered * 100).toFixed(1) : "0"
        return (
          <div key={i} className="flex items-center gap-3">
            <div className="w-20 text-xs text-muted-foreground text-right">{item.name}</div>
            <div className="flex-1 h-6 bg-secondary/30 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${Math.min(100, (item.value / variant.stats.triggered) * 100)}%`, backgroundColor: item.fill }}
              />
            </div>
            <div className="w-16 text-xs text-foreground font-mono">{item.value}</div>
            <div className="w-12 text-xs text-muted-foreground">{pct}%</div>
          </div>
        )
      })}
    </div>
  )
}

// ── A/B Test detail dialog ────────────────────────────────────────────

function ABTestDetailDialog({ test }: { test: ABTest }) {
  const [selectedMetric, setSelectedMetric] = useState<"conversion_rate" | "revenue_preserved">(
    test.primary_metric
  )

  return (
    <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <FlaskConical className="h-5 w-5 text-violet-400" />
          {test.name}
        </DialogTitle>
      </DialogHeader>

      <div className="space-y-6">
        {/* Status bar */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {getStatusBadge(test.status)}
            <span className="text-xs text-muted-foreground">
              Started {new Date(test.created_at).toLocaleDateString()}
            </span>
          </div>
          {test.status === "running" && (
            <div className="flex gap-2">
              <Button variant="outline" size="sm">
                <Pause className="mr-1.5 h-3.5 w-3.5" /> Pause
              </Button>
              <Button variant="outline" size="sm">
                <Copy className="mr-1.5 h-3.5 w-3.5" /> Duplicate
              </Button>
            </div>
          )}
        </div>

        {/* Confidence indicator */}
        {test.confidence_level > 0 && (
          <Card className="border-border bg-card">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Target className={`h-4 w-4 ${getConfidenceColor(test.confidence_level)}`} />
                  <span className="text-sm font-medium">Statistical Confidence</span>
                </div>
                <span className={`text-lg font-bold ${getConfidenceColor(test.confidence_level)}`}>
                  {test.confidence_level}%
                </span>
              </div>
              <div className="mt-2 h-2 bg-secondary/30 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full transition-all"
                  style={{ width: `${test.confidence_level}%` }}
                />
              </div>
              {test.winner_variant_id && (
                <p className="mt-2 text-xs text-emerald-400 flex items-center gap-1">
                  <CheckCircle className="h-3 w-3" />
                  Winner: {test.variants.find((v) => v.id === test.winner_variant_id)?.name}
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Metric selector */}
        <div className="flex gap-2">
          <button
            onClick={() => setSelectedMetric("conversion_rate")}
            className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
              selectedMetric === "conversion_rate"
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-muted-foreground hover:text-foreground"
            }`}
          >
            Conversion Rate
          </button>
          <button
            onClick={() => setSelectedMetric("revenue_preserved")}
            className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
              selectedMetric === "revenue_preserved"
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-muted-foreground hover:text-foreground"
            }`}
          >
            Revenue Preserved
          </button>
        </div>

        {/* Comparison chart */}
        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle className="text-sm">Variant Comparison</CardTitle>
          </CardHeader>
          <CardContent>
            <VariantComparisonChart variants={test.variants} metric={selectedMetric} />
          </CardContent>
        </Card>

        {/* Per-variant funnel */}
        <div className="grid gap-4 md:grid-cols-2">
          {test.variants.map((variant) => (
            <Card key={variant.id} className="border-border bg-card">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center justify-between">
                  <span>{variant.name}</span>
                  {test.winner_variant_id === variant.id && (
                    <Badge className="bg-emerald-500/20 text-emerald-400 text-[10px]">
                      <CheckCircle className="mr-1 h-3 w-3" /> Winner
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription className="text-xs">{variant.journey_name} • {variant.traffic_percentage}% traffic</CardDescription>
              </CardHeader>
              <CardContent>
                <VariantFunnel variant={variant} />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </DialogContent>
  )
}

// ── Main A/B Testing component ────────────────────────────────────────

export function JourneyABTesting() {
  const [tests, setTests] = useState<ABTest[]>(mockABTests)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [newTestName, setNewTestName] = useState("")

  const runningTests = tests.filter((t) => t.status === "running")
  const completedTests = tests.filter((t) => t.status === "completed")

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <FlaskConical className="h-5 w-5 text-violet-400" />
            A/B Testing
          </h3>
          <p className="text-sm text-muted-foreground">
            Compare journey variants to find the best retention strategy
          </p>
        </div>
        <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
          <DialogTrigger asChild>
            <Button size="sm" className="bg-primary">
              <FlaskConical className="mr-2 h-4 w-4" />
              New A/B Test
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create A/B Test</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 pt-2">
              <div>
                <Label className="text-xs text-muted-foreground">Test Name</Label>
                <Input
                  placeholder="e.g. Discount vs Upgrade"
                  value={newTestName}
                  onChange={(e) => setNewTestName(e.target.value)}
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Primary Metric</Label>
                <div className="flex gap-2 mt-1">
                  <Button variant="outline" size="sm" className="flex-1">Conversion Rate</Button>
                  <Button variant="outline" size="sm" className="flex-1">Revenue</Button>
                </div>
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Variants</Label>
                <p className="text-xs text-muted-foreground mt-1">Select 2 or more journeys to compare</p>
              </div>
              <Button className="w-full" disabled={!newTestName}>
                Create & Start Test
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Running tests */}
      {runningTests.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Play className="h-3.5 w-3.5 text-emerald-400" />
            Running ({runningTests.length})
          </h4>
          {runningTests.map((test) => (
            <Dialog key={test.id}>
              <DialogTrigger asChild>
                <Card className="border-border bg-card cursor-pointer hover:border-primary/50 transition-colors">
                  <CardContent className="p-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="font-semibold text-foreground text-sm">{test.name}</h4>
                          {getStatusBadge(test.status)}
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <Users className="h-3 w-3" />
                            {test.variants.reduce((s, v) => s + v.stats.triggered, 0)} participants
                          </span>
                          <span className="flex items-center gap-1">
                            <Target className="h-3 w-3" />
                            {test.variants.length} variants
                          </span>
                          {test.confidence_level > 0 && (
                            <span className={`flex items-center gap-1 ${getConfidenceColor(test.confidence_level)}`}>
                              <BarChart3 className="h-3 w-3" />
                              {test.confidence_level}% confidence
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        {test.variants.map((v) => (
                          <div key={v.id} className="text-center">
                            <p className="text-xs text-muted-foreground">{v.name.split(":")[0]}</p>
                            <p className="text-sm font-bold text-foreground">{v.stats.conversion_rate}%</p>
                            <p className="text-[10px] text-muted-foreground">conv.</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </DialogTrigger>
              <ABTestDetailDialog test={test} />
            </Dialog>
          ))}
        </div>
      )}

      {/* Completed tests */}
      {completedTests.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <CheckCircle className="h-3.5 w-3.5 text-blue-400" />
            Completed ({completedTests.length})
          </h4>
          {completedTests.map((test) => (
            <Dialog key={test.id}>
              <DialogTrigger asChild>
                <Card className="border-border bg-card cursor-pointer hover:border-primary/50 transition-colors">
                  <CardContent className="p-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="font-semibold text-foreground text-sm">{test.name}</h4>
                          {getStatusBadge(test.status)}
                        </div>
                        <p className="text-xs text-emerald-400 mt-1 flex items-center gap-1">
                          <CheckCircle className="h-3 w-3" />
                          Winner: {test.variants.find((v) => v.id === test.winner_variant_id)?.name} ({test.confidence_level}% confidence)
                        </p>
                      </div>
                      <div className="flex items-center gap-4">
                        {test.variants.map((v) => (
                          <div
                            key={v.id}
                            className={`text-center ${v.id === test.winner_variant_id ? "opacity-100" : "opacity-50"}`}
                          >
                            <p className="text-xs text-muted-foreground">{v.name.split(":")[0]}</p>
                            <p className={`text-sm font-bold ${v.id === test.winner_variant_id ? "text-emerald-400" : "text-foreground"}`}>
                              {v.stats.conversion_rate}%
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </DialogTrigger>
              <ABTestDetailDialog test={test} />
            </Dialog>
          ))}
        </div>
      )}

      {/* Empty state */}
      {tests.length === 0 && (
        <Card className="border-border bg-card">
          <CardContent className="py-12 text-center">
            <FlaskConical className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">No A/B tests yet</p>
            <p className="text-xs text-muted-foreground mt-1">Create your first test to compare journey variants</p>
          </CardContent>
        </Card>
      )}

      {/* Tips */}
      <Card className="border-border bg-card">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs text-muted-foreground">A/B Testing Best Practices</CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-muted-foreground space-y-1.5">
          <p>• Run tests for at least 2 weeks to account for weekly patterns</p>
          <p>• Aim for 95%+ statistical confidence before declaring a winner</p>
          <p>• Test one variable at a time (offer type, channel, messaging)</p>
          <p>• Ensure equal traffic split between variants for fair comparison</p>
          <p>• Minimum 200 samples per variant recommended</p>
        </CardContent>
      </Card>
    </div>
  )
}
