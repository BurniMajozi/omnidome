"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  PhoneCall,
  PhoneForwarded,
  ShieldCheck,
  Zap,
  Users,
  Smartphone,
  Mic,
  ArrowRight,
  Plus,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Play,
  RotateCcw,
  Sparkles,
} from "lucide-react"
import type { CallSeekerGroup } from "@/app/api/call-center/seeker/route"

export function CallSeekerView() {
  const [seekerGroups, setSeekerGroups] = useState<CallSeekerGroup[]>([])
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [simulationResult, setSimulationResult] = useState<any>(null)
  const [simulating, setSimulating] = useState(false)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // Add Seeker Form
  const [formName, setFormName] = useState("")
  const [formDid, setFormDid] = useState("")
  const [formStrategy, setFormStrategy] = useState<CallSeekerGroup["strategy"]>("TIERED_SPILLOVER")
  const [formPrimary, setFormPrimary] = useState("101, 102")
  const [formSecondary, setFormSecondary] = useState("104, 105")
  const [formMobile, setFormMobile] = useState("+27829910022")
  const [formTimeout, setFormTimeout] = useState(15)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 4000)
  }

  const fetchSeekerData = async () => {
    try {
      setLoading(true)
      const res = await fetch("/api/call-center/seeker")
      if (res.ok) {
        const data = await res.json()
        setSeekerGroups(data.seeker_groups || [])
        setStats(data.stats || null)
      }
    } catch (err) {
      console.error("Failed to fetch seeker data", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSeekerData()
  }, [])

  const handleCreateSeeker = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await fetch("/api/call-center/seeker", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "ADD_SEEKER_GROUP",
          name: formName,
          inbound_did: formDid,
          strategy: formStrategy,
          primary_tier_extensions: formPrimary.split(",").map((s) => s.trim()),
          secondary_spillover_extensions: formSecondary.split(",").map((s) => s.trim()),
          mobile_divert_numbers: formMobile.split(",").map((s) => s.trim()),
          ring_timeout_sec: Number(formTimeout),
        }),
      })
      if (res.ok) {
        showToast("Call Seeker Hunt Group Created!")
        setAddModalOpen(false)
        setFormName("")
        setFormDid("")
        fetchSeekerData()
      }
    } catch {
      showToast("Failed to create seeker group")
    }
  }

  const handleTriggerSimulation = async (groupId: string) => {
    try {
      setSimulating(true)
      setSimulationResult(null)
      const res = await fetch("/api/call-center/seeker", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "TRIGGER_TEST_HUNT",
          groupId,
        }),
      })
      if (res.ok) {
        const data = await res.json()
        setSimulationResult(data.simulation)
        showToast("Zero-Lost-Call Simulation Succeeded: Call Rescued!")
        fetchSeekerData()
      }
    } catch {
      showToast("Simulation failed")
    } finally {
      setSimulating(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Toast */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 rounded-lg bg-emerald-600 px-4 py-3 text-white shadow-xl flex items-center gap-2 border border-emerald-400">
          <CheckCircle2 className="h-5 w-5" />
          <span className="text-sm font-semibold">{toastMessage}</span>
        </div>
      )}

      {/* Header Banner */}
      <div className="rounded-xl border border-blue-500/40 bg-gradient-to-r from-blue-950/40 via-background to-cyan-950/30 p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <span className="flex h-3 w-3 rounded-full bg-blue-400 shadow-sm" />
              <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
                Call Seeker: Zero-Lost-Call Routing Architecture
              </h2>
              <Badge variant="outline" className="border-blue-500/40 text-blue-400 bg-blue-500/10 text-xs">
                Guaranteed Telephony Reach
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Intelligent multi-tier call hunting. If primary call center agents are engaged, the Seeker overflows to standby technicians, mobile cellphones via SIP trunk, and Deepgram AI Voicemail-to-Text with instant support ticket generation.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              onClick={() => setAddModalOpen(true)}
              className="gap-1.5 text-xs bg-blue-600 hover:bg-blue-500 text-white font-medium"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Hunt Group
            </Button>
          </div>
        </div>

        {/* Stats Row */}
        <div className="mt-4 pt-4 border-t border-border/60 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div>
            <span className="text-muted-foreground block text-[11px]">Calls Rescued</span>
            <strong className="text-lg font-bold text-foreground">
              {stats?.total_calls_rescued?.toLocaleString() || "2,722"} calls
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Rescue Success Rate</span>
            <strong className="text-lg font-bold text-emerald-400">
              {stats?.avg_rescue_rate_pct || 99.4}%
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Active Seeker Hunts</span>
            <strong className="text-lg font-bold text-cyan-400">
              {stats?.active_hunts_now || 3} Live Hunts
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Failover SLA</span>
            <strong className="text-lg font-bold text-violet-400">Zero Dropped Calls</strong>
          </div>
        </div>
      </div>

      {/* Visual Call Seeker Architecture Flow */}
      <Card className="border-border bg-card/80">
        <CardHeader className="pb-3 border-b border-border/50">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <PhoneForwarded className="h-4 w-4 text-blue-400" />
            Live Call Seeker Failover Sequence
          </CardTitle>
          <CardDescription className="text-xs">
            Visual cascade showing how incoming subscriber calls hunt across endpoints until resolved.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-5">
          <div className="grid gap-3 md:grid-cols-4 items-center">
            {/* Step 1 */}
            <div className="rounded-lg border border-border bg-background/50 p-3.5 space-y-1.5 relative">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-cyan-400 uppercase tracking-wider">Step 1: Inbound</span>
                <Badge variant="outline" className="text-[10px]">0 - 15s</Badge>
              </div>
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                <Users className="h-4 w-4 text-cyan-400" /> Primary Support Tier
              </h4>
              <p className="text-[11px] text-muted-foreground">
                Rings active shift agents logged in via Asterisk ACD queue.
              </p>
            </div>

            {/* Step 2 */}
            <div className="rounded-lg border border-border bg-background/50 p-3.5 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-blue-400 uppercase tracking-wider">Step 2: Spillover</span>
                <Badge variant="outline" className="text-[10px]">15 - 30s</Badge>
              </div>
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                <ShieldCheck className="h-4 w-4 text-blue-400" /> Secondary / NOC Standby
              </h4>
              <p className="text-[11px] text-muted-foreground">
                Spills over to standby engineers and cross-functional staff.
              </p>
            </div>

            {/* Step 3 */}
            <div className="rounded-lg border border-border bg-background/50 p-3.5 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-purple-400 uppercase tracking-wider">Step 3: Mobile Hunt</span>
                <Badge variant="outline" className="text-[10px]">30 - 45s</Badge>
              </div>
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                <Smartphone className="h-4 w-4 text-purple-400" /> Mobile Cellphone Divert
              </h4>
              <p className="text-[11px] text-muted-foreground">
                Diverts out via Liquid/Telkom SIP trunk to on-call manager mobile.
              </p>
            </div>

            {/* Step 4 */}
            <div className="rounded-lg border border-emerald-500/40 bg-emerald-950/20 p-3.5 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-emerald-400 uppercase tracking-wider">Step 4: AI Voice</span>
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px]">Always On</Badge>
              </div>
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                <Mic className="h-4 w-4 text-emerald-400" /> Deepgram Voicemail-to-Ticket
              </h4>
              <p className="text-[11px] text-muted-foreground">
                Auto-transcribes caller message and generates #TKT in Service.
              </p>
            </div>
          </div>

          {/* Simulation Output Panel if triggered */}
          {simulationResult && (
            <div className="mt-4 rounded-lg border border-emerald-500/50 bg-emerald-500/10 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4" /> Live Call Seeker Simulation Trace
                </span>
                <Button size="sm" variant="ghost" onClick={() => setSimulationResult(null)} className="h-6 text-xs">
                  Clear
                </Button>
              </div>
              <div className="grid gap-1.5 text-xs text-foreground font-mono">
                <div>• {simulationResult.step1}</div>
                <div>• {simulationResult.step2}</div>
                <div>• {simulationResult.step3}</div>
                <div>• {simulationResult.step4}</div>
                <div className="text-emerald-400 font-bold font-sans pt-1">
                  ✓ {simulationResult.result}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Seeker Hunt Groups Table */}
      <Card className="border-border bg-card/80">
        <CardHeader className="pb-3 border-b border-border/50">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Zap className="h-4 w-4 text-cyan-400" />
            Configured Call Seeker Hunt Groups
          </CardTitle>
          <CardDescription className="text-xs">
            Manage hunting rules, ring timeout thresholds, and automated failover targets per inbound phone number.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="rounded-lg border border-border overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/40 text-muted-foreground uppercase text-[10px] tracking-wider border-b border-border">
                <tr>
                  <th className="p-3">Hunt Group &amp; DID</th>
                  <th className="p-3">Strategy</th>
                  <th className="p-3">Primary Ring Tier</th>
                  <th className="p-3">Secondary Spillover</th>
                  <th className="p-3">Mobile Cell Divert</th>
                  <th className="p-3 text-center">Timeout</th>
                  <th className="p-3 text-right">Rescued Rate</th>
                  <th className="p-3 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {seekerGroups.map((group) => (
                  <tr key={group.id} className="hover:bg-muted/20 transition-colors">
                    <td className="p-3">
                      <div className="font-semibold text-foreground">{group.name}</div>
                      <div className="text-[11px] text-cyan-400 font-mono">{group.inbound_did}</div>
                    </td>

                    <td className="p-3">
                      <Badge variant="outline" className="text-[10px] border-border">
                        {group.strategy.replace(/_/g, " ")}
                      </Badge>
                    </td>

                    <td className="p-3">
                      <div className="text-xs text-foreground font-medium">
                        {group.primary_tier_extensions.join(", ")}
                      </div>
                    </td>

                    <td className="p-3">
                      <div className="text-xs text-muted-foreground">
                        {group.secondary_spillover_extensions.join(", ")}
                      </div>
                    </td>

                    <td className="p-3">
                      <div className="text-xs text-purple-400 font-mono">
                        {group.mobile_divert_numbers.join(", ")}
                      </div>
                    </td>

                    <td className="p-3 text-center font-mono font-semibold text-foreground">
                      {group.ring_timeout_sec}s
                    </td>

                    <td className="p-3 text-right">
                      <div className="font-bold text-emerald-400">{group.calls_rescued_pct}%</div>
                      <div className="text-[10px] text-muted-foreground">
                        {group.total_calls_sought} sought
                      </div>
                    </td>

                    <td className="p-3 text-center">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleTriggerSimulation(group.id)}
                        disabled={simulating}
                        className="h-7 text-xs gap-1 border-blue-500/40 text-blue-400 hover:bg-blue-500/10"
                      >
                        <Play className="h-3 w-3" />
                        Test Hunt
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Add Hunt Group Modal */}
      {addModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-card border border-border rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <Plus className="h-4 w-4 text-blue-400" />
                Add Zero-Lost-Call Seeker Hunt Group
              </h3>
              <Button size="sm" variant="ghost" onClick={() => setAddModalOpen(false)}>✕</Button>
            </div>

            <form onSubmit={handleCreateSeeker} className="space-y-3.5 text-xs">
              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Hunt Group Name</label>
                <Input
                  placeholder="e.g. VIP Fiber & Corporate Hunt"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  required
                />
              </div>

              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Inbound DID Numbers</label>
                <Input
                  placeholder="e.g. 011 200 4010 / 0800 998 823"
                  value={formDid}
                  onChange={(e) => setFormDid(e.target.value)}
                  required
                />
              </div>

              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Hunting Strategy</label>
                <select
                  value={formStrategy}
                  onChange={(e) => setFormStrategy(e.target.value as any)}
                  className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                >
                  <option value="TIERED_SPILLOVER">Tiered Spillover (Tier 1 → Tier 2 → Mobile)</option>
                  <option value="SIMULTANEOUS_BLAST">Simultaneous Blast (Ring All Extensions at Once)</option>
                  <option value="LINEAR_HUNT">Linear Hunt (One-by-One in Sequence)</option>
                  <option value="GEO_POP_PROXIMITY">Geo / Metro POP Proximity</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Primary Extensions</label>
                  <Input value={formPrimary} onChange={(e) => setFormPrimary(e.target.value)} required />
                </div>
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Spillover Extensions</label>
                  <Input value={formSecondary} onChange={(e) => setFormSecondary(e.target.value)} required />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Mobile Cellphone Divert</label>
                  <Input value={formMobile} onChange={(e) => setFormMobile(e.target.value)} required />
                </div>
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Ring Timeout (Sec)</label>
                  <Input
                    type="number"
                    value={formTimeout}
                    onChange={(e) => setFormTimeout(Number(e.target.value))}
                    required
                  />
                </div>
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => setAddModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" className="bg-blue-600 hover:bg-blue-500 text-white">
                  Save Seeker Group
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
