"use client"

import { useState, useEffect, useCallback } from "react"
import {
  Wrench, MapPin, Phone, Clock, CheckCircle, AlertTriangle, Zap,
  Wifi, Thermometer, ArrowLeft, Play, Square, Package, Camera,
  ChevronRight, Signal, RotateCcw, Star, Timer, TrendingUp, Plus,
  Radio,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { technicianApi } from "@/lib/mobile-technician-api"
import type { TechJob, TechDevice, SpeedTestResult } from "@/lib/mobile-technician-api"

// ── Priority badge ────────────────────────────────────────────────────

function PriorityBadge({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    URGENT: "bg-red-500/20 text-red-400 border-red-500/30",
    HIGH: "bg-orange-500/20 text-orange-400 border-orange-500/30",
    NORMAL: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    LOW: "bg-secondary text-muted-foreground",
  }
  return <Badge className={`text-[10px] ${colors[priority] || colors.NORMAL}`}>{priority}</Badge>
}

// ── Job Card ──────────────────────────────────────────────────────────

function JobCard({ job, onSelect }: { job: TechJob; onSelect: (j: TechJob) => void }) {
  return (
    <Card className="border-border bg-card cursor-pointer hover:border-primary/50" onClick={() => onSelect(job)}>
      <CardContent className="p-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <PriorityBadge priority={job.priority} />
              <Badge className="text-[10px] bg-secondary">{job.category}</Badge>
            </div>
            <p className="font-medium text-sm truncate">{job.subject}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{job.customer_name || job.customer_id}</p>
            <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
              <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{job.customer_phone || "N/A"}</span>
              <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{new Date(job.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1 truncate flex items-center gap-1"><MapPin className="h-3 w-3 shrink-0" />{job.customer_address || "N/A"}</p>
          </div>
          <ChevronRight className="h-4 w-4 text-muted-foreground self-center ml-2" />
        </div>
      </CardContent>
    </Card>
  )
}

// ── Device Status Card ────────────────────────────────────────────────

function DeviceCard({ device }: { device: TechDevice }) {
  const signalColor = device.rx_power_dbm != null
    ? device.rx_power_dbm >= -20 ? "text-emerald-400" : device.rx_power_dbm >= -25 ? "text-amber-400" : "text-red-400"
    : "text-muted-foreground"

  return (
    <Card className="border-border bg-card">
      <CardContent className="p-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">{device.device_name}</p>
            <p className="text-xs text-muted-foreground">{device.device_type} • {device.serial_number || device.mac_address || "No serial"}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge className={`text-[10px] ${device.status === "ONLINE" ? "bg-emerald-500/20 text-emerald-400" : device.status === "OFFLINE" ? "bg-red-500/20 text-red-400" : "bg-amber-500/20 text-amber-400"}`}>
              {device.status}
            </Badge>
          </div>
        </div>
        {device.rx_power_dbm != null && (
          <div className="grid grid-cols-3 gap-2 mt-2">
            <div className="text-center bg-secondary/30 rounded p-1.5">
              <Signal className={`h-3 w-3 mx-auto mb-0.5 ${signalColor}`} />
              <p className={`text-xs font-mono font-bold ${signalColor}`}>{device.rx_power_dbm} dBm</p>
              <p className="text-[9px] text-muted-foreground">RX</p>
            </div>
            <div className="text-center bg-secondary/30 rounded p-1.5">
              <Thermometer className="h-3 w-3 mx-auto mb-0.5 text-blue-400" />
              <p className="text-xs font-mono font-bold text-blue-400">{device.temperature_c}°C</p>
              <p className="text-[9px] text-muted-foreground">Temp</p>
            </div>
            <div className="text-center bg-secondary/30 rounded p-1.5">
              <Wifi className="h-3 w-3 mx-auto mb-0.5 text-violet-400" />
              <p className="text-xs font-mono font-bold text-violet-400">{device.tx_power_dbm} dBm</p>
              <p className="text-[9px] text-muted-foreground">TX</p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Job Detail / Work Panel ───────────────────────────────────────────

function JobWorkPanel({ job, onBack, onComplete }: { job: TechJob; onBack: () => void; onComplete: () => void }) {
  const [devices, setDevices] = useState<TechDevice[]>([])
  const [notes, setNotes] = useState("")
  const [speedTest, setSpeedTest] = useState<SpeedTestResult | null>(null)
  const [runningSpeed, setRunningSpeed] = useState(false)
  const [partsUsed, setPartsUsed] = useState<Array<{ product_id: string; quantity: number }>>([])
  const [partSku, setPartSku] = useState("")
  const [partQty, setPartQty] = useState("1")
  const [status, setStatus] = useState(job.status)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    technicianApi.getCustomerDevices(job.customer_id).then(setDevices).catch(() => {})
  }, [job.customer_id])

  const handleStart = async () => {
    await technicianApi.startJob(job.id)
    setStatus("IN_PROGRESS")
  }

  const handleSpeedTest = async () => {
    setRunningSpeed(true)
    try { const r = await technicianApi.runSpeedTest(); setSpeedTest(r) }
    catch { setSpeedTest({ download_mbps: 0, upload_mbps: 0, latency_ms: 0, jitter_ms: 0, timestamp: new Date().toISOString() }) }
    finally { setRunningSpeed(false) }
  }

  const handleAddPart = () => {
    if (!partSku) return
    setPartsUsed([...partsUsed, { product_id: partSku, quantity: parseInt(partQty) || 1 }])
    setPartSku(""); setPartQty("1")
  }

  const handleComplete = async () => {
    setSaving(true)
    try {
      await technicianApi.completeJob({
        job_id: job.id,
        resolution_notes: notes,
        parts_used: partsUsed,
        speed_test: speedTest || undefined,
        fcr: true,
      })
      onComplete()
    } catch (e) { alert("Complete failed: " + (e as Error).message) }
    finally { setSaving(false) }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={onBack}><ArrowLeft className="h-4 w-4" /></Button>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <PriorityBadge priority={job.priority} />
            <Badge className="text-[10px] bg-secondary">{status}</Badge>
          </div>
          <h3 className="font-semibold text-foreground mt-1">{job.subject}</h3>
        </div>
      </div>

      {/* Customer info */}
      <Card className="border-border bg-card">
        <CardContent className="p-3 space-y-1">
          <p className="font-medium text-sm">{job.customer_name || job.customer_id}</p>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{job.customer_phone || "N/A"}</span>
          </div>
          <p className="text-xs text-muted-foreground flex items-center gap-1"><MapPin className="h-3 w-3 shrink-0" />{job.customer_address || "N/A"}</p>
          {job.external_fno_ref && <p className="text-xs text-muted-foreground">FNO Ref: {job.external_fno_ref}</p>}
        </CardContent>
      </Card>

      {/* Description */}
      {job.description && (
        <Card className="border-border bg-card">
          <CardContent className="p-3">
            <p className="text-xs font-medium text-muted-foreground mb-1">DESCRIPTION</p>
            <p className="text-sm">{job.description}</p>
          </CardContent>
        </Card>
      )}

      {/* Action buttons */}
      {status === "OPEN" && (
        <Button className="w-full" onClick={handleStart}><Play className="mr-2 h-4 w-4" /> Start Job</Button>
      )}
      {status === "IN_PROGRESS" && (
        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" onClick={handleSpeedTest} disabled={runningSpeed}>
            <Zap className="mr-2 h-4 w-4" /> {runningSpeed ? "Testing..." : "Speed Test"}
          </Button>
          <Button variant="outline" onClick={() => technicianApi.escalateJob(job.id, "Escalated from mobile")}>
            <AlertTriangle className="mr-2 h-4 w-4" /> Escalate
          </Button>
        </div>
      )}

      {/* Speed test results */}
      {speedTest && speedTest.download_mbps > 0 && (
        <Card className="border-border bg-card">
          <CardContent className="p-3">
            <p className="text-xs font-medium text-muted-foreground mb-2">SPEED TEST RESULTS</p>
            <div className="grid grid-cols-2 gap-2">
              <div className="text-center bg-secondary/30 rounded p-2">
                <p className="text-lg font-bold text-emerald-400">{speedTest.download_mbps}</p>
                <p className="text-[10px] text-muted-foreground">Download Mbps</p>
              </div>
              <div className="text-center bg-secondary/30 rounded p-2">
                <p className="text-lg font-bold text-blue-400">{speedTest.upload_mbps}</p>
                <p className="text-[10px] text-muted-foreground">Upload Mbps</p>
              </div>
              <div className="text-center bg-secondary/30 rounded p-2">
                <p className="text-lg font-bold text-violet-400">{speedTest.latency_ms}</p>
                <p className="text-[10px] text-muted-foreground">Latency ms</p>
              </div>
              <div className="text-center bg-secondary/30 rounded p-2">
                <p className="text-lg font-bold text-amber-400">{speedTest.jitter_ms}</p>
                <p className="text-[10px] text-muted-foreground">Jitter ms</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Devices at site */}
      {devices.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">DEVICES AT SITE ({devices.length})</p>
          <div className="space-y-2">
            {devices.map(d => (
              <div key={d.id} className="relative">
                <DeviceCard device={d} />
                {d.status === "ONLINE" && (
                  <Button variant="ghost" size="icon" className="absolute top-2 right-2 h-6 w-6" onClick={() => technicianApi.rebootDevice(d.id)}>
                    <RotateCcw className="h-3 w-3" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Parts checkout */}
      {status === "IN_PROGRESS" && (
        <Card className="border-border bg-card">
          <CardContent className="p-3">
            <p className="text-xs font-medium text-muted-foreground mb-2">PARTS USED</p>
            <div className="flex gap-2 mb-2">
              <Input placeholder="SKU or product ID" value={partSku} onChange={e => setPartSku(e.target.value)} className="flex-1" />
              <Input type="number" min={1} value={partQty} onChange={e => setPartQty(e.target.value)} className="w-16" />
              <Button size="sm" onClick={handleAddPart}><Plus className="h-3 w-3" /></Button>
            </div>
            {partsUsed.map((p, i) => (
              <div key={i} className="flex items-center justify-between bg-secondary/30 rounded p-2 mb-1">
                <span className="text-xs">{p.product_id} × {p.quantity}</span>
                <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => setPartsUsed(partsUsed.filter((_, j) => j !== i))}>×</Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Resolution notes */}
      {status === "IN_PROGRESS" && (
        <div>
          <Label className="text-xs text-muted-foreground">Resolution Notes</Label>
          <textarea value={notes} onChange={e => setNotes(e.target.value)} placeholder="Describe what was done..." className="mt-1 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" rows={3} />
        </div>
      )}

      {/* Complete button */}
      {status === "IN_PROGRESS" && (
        <Button className="w-full bg-emerald-600 hover:bg-emerald-700" onClick={handleComplete} disabled={saving || !notes}>
          <CheckCircle className="mr-2 h-4 w-4" /> {saving ? "Completing..." : "Complete Job"}
        </Button>
      )}
    </div>
  )
}

// ── Main Technician App ───────────────────────────────────────────────

export function TechnicianApp() {
  const [tab, setTab] = useState("queue")
  const [jobs, setJobs] = useState<TechJob[]>([])
  const [selectedJob, setSelectedJob] = useState<TechJob | null>(null)
  const [stats, setStats] = useState({ jobs_today: 0, jobs_week: 0, avg_resolution_min: 0, fcr_rate: 0, customer_rating: 0, revenue_generated: 0 })
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<"ALL" | "OPEN" | "IN_PROGRESS">("ALL")

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const [j, s] = await Promise.all([
        technicianApi.getMyJobs(),
        technicianApi.getMyStats(),
      ])
      setJobs(j)
      if (s) setStats(s)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  // Real-time SSE subscription for job dispatch
  useEffect(() => {
    const unsubscribe = technicianApi.streamJobEvents((evt) => {
      if (evt.event === "new_ticket") {
        const newJob = evt.data as TechJob
        setJobs((prev) => {
          // Avoid duplicates
          if (prev.find((j) => j.id === newJob.id)) return prev
          return [newJob, ...prev]
        })
      } else if (evt.event === "ticket_update") {
        const updatedJob = evt.data as TechJob
        setJobs((prev) =>
          prev.map((j) => (j.id === updatedJob.id ? updatedJob : j))
        )
      }
    })
    return unsubscribe
  }, [])

  const filteredJobs = jobs.filter(j => filter === "ALL" || j.status === filter)

  if (selectedJob) {
    return <JobWorkPanel job={selectedJob} onBack={() => setSelectedJob(null)} onComplete={() => { setSelectedJob(null); load() }} />
  }

  return (
    <div className="space-y-4">
      {/* Stats header */}
      <div className="grid grid-cols-3 gap-2">
        <Card className="border-border bg-card"><CardContent className="p-3 text-center">
          <Wrench className="h-4 w-4 text-violet-400 mx-auto mb-1" />
          <p className="text-lg font-bold">{stats.jobs_today}</p><p className="text-[10px] text-muted-foreground">Today</p>
        </CardContent></Card>
        <Card className="border-border bg-card"><CardContent className="p-3 text-center">
          <Timer className="h-4 w-4 text-blue-400 mx-auto mb-1" />
          <p className="text-lg font-bold">{stats.avg_resolution_min}m</p><p className="text-[10px] text-muted-foreground">Avg Time</p>
        </CardContent></Card>
        <Card className="border-border bg-card"><CardContent className="p-3 text-center">
          <Star className="h-4 w-4 text-amber-400 mx-auto mb-1" />
          <p className="text-lg font-bold">{stats.customer_rating}</p><p className="text-[10px] text-muted-foreground">Rating</p>
        </CardContent></Card>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-secondary w-full">
          <TabsTrigger value="queue" className="flex-1">Job Queue</TabsTrigger>
          <TabsTrigger value="stats" className="flex-1">My Stats</TabsTrigger>
        </TabsList>

        <TabsContent value="queue" className="mt-3 space-y-2">
          <div className="flex gap-1">
            {(["ALL", "OPEN", "IN_PROGRESS"] as const).map(f => (
              <button key={f} onClick={() => setFilter(f)} className={`px-3 py-1 text-xs rounded-md transition-colors ${filter === f ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground hover:text-foreground"}`}>
                {f === "ALL" ? "All" : f === "OPEN" ? "Open" : "In Progress"} ({jobs.filter(j => f === "ALL" || j.status === f).length})
              </button>
            ))}
          </div>
          {loading ? <p className="text-xs text-muted-foreground text-center py-8">Loading jobs...</p> : filteredJobs.map(j => (
            <JobCard key={j.id} job={j} onSelect={setSelectedJob} />
          ))}
          {!loading && filteredJobs.length === 0 && <p className="text-xs text-muted-foreground text-center py-8">No jobs in queue</p>}
        </TabsContent>

        <TabsContent value="stats" className="mt-3 space-y-3">
          <Card className="border-border bg-card">
            <CardHeader><CardTitle className="text-sm">This Week</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-2 gap-3">
              <div className="text-center bg-secondary/30 rounded-lg p-3">
                <p className="text-2xl font-bold text-emerald-400">{stats.jobs_week}</p>
                <p className="text-xs text-muted-foreground">Jobs Completed</p>
              </div>
              <div className="text-center bg-secondary/30 rounded-lg p-3">
                <p className="text-2xl font-bold text-violet-400">{stats.fcr_rate}%</p>
                <p className="text-xs text-muted-foreground">FCR Rate</p>
              </div>
              <div className="text-center bg-secondary/30 rounded-lg p-3">
                <p className="text-2xl font-bold text-amber-400">R{stats.revenue_generated.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Revenue Generated</p>
              </div>
              <div className="text-center bg-secondary/30 rounded-lg p-3">
                <div className="flex items-center justify-center gap-1">
                  <p className="text-2xl font-bold text-amber-400">{stats.customer_rating}</p>
                  <span className="text-amber-400">★</span>
                </div>
                <p className="text-xs text-muted-foreground">Customer Rating</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
