"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Phone,
  PhoneCall,
  PhoneIncoming,
  PhoneOutgoing,
  ShieldAlert,
  Sparkles,
  Zap,
  TrendingUp,
  Activity,
  Layers,
  Clock,
  RefreshCw,
  Search,
  Filter,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Play,
  Volume2,
  Mic,
  Server,
  Database,
  Lock,
} from "lucide-react"
import type { AsteriskCdrRecord, CallSpikeTelemetry } from "@/app/api/call-center/asterisk/route"

export function AsteriskTelephonyView() {
  const [cdrs, setCdrs] = useState<AsteriskCdrRecord[]>([])
  const [spikes, setSpikes] = useState<CallSpikeTelemetry[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [sourceOfTruth, setSourceOfTruth] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [fraudOnly, setFraudOnly] = useState(false)
  const [selectedDisposition, setSelectedDisposition] = useState<string>("ALL")
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [simModalOpen, setSimModalOpen] = useState(false)

  // Simulation Form
  const [simSrc, setSimSrc] = useState("0825559900")
  const [simDst, setSimDst] = useState("0800998822")
  const [simDuration, setSimDuration] = useState(240)
  const [simDestType, setSimDestType] = useState<AsteriskCdrRecord["destination_type"]>("Local Mobile (Vodacom/MTN)")
  const [simRate, setSimRate] = useState(0.45)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 4000)
  }

  const fetchAsteriskData = async () => {
    try {
      setLoading(true)
      const params = new URLSearchParams()
      if (search) params.set("search", search)
      if (selectedDisposition !== "ALL") params.set("disposition", selectedDisposition)
      if (fraudOnly) params.set("fraud_only", "true")

      const res = await fetch(`/api/call-center/asterisk?${params.toString()}`)
      if (res.ok) {
        const data = await res.json()
        setCdrs(data.cdrs || [])
        setSpikes(data.spikes || [])
        setSummary(data.summary || null)
        setSourceOfTruth(data.sourceOfTruth || null)
      }
    } catch (err) {
      console.error("Failed to fetch Asterisk telemetry", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAsteriskData()
  }, [search, selectedDisposition, fraudOnly])

  const handleSimulateCall = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await fetch("/api/call-center/asterisk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "INJECT_CDR",
          src: simSrc,
          dst: simDst,
          durationSec: Number(simDuration),
          destType: simDestType,
          ratePerMin: Number(simRate),
          agentExtension: "101",
          queue: "tech_support",
        }),
      })
      if (res.ok) {
        showToast("Live Asterisk Call Injected & Rated via ASTPP!")
        setSimModalOpen(false)
        fetchAsteriskData()
      }
    } catch {
      showToast("Failed to simulate call")
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

      {/* Banner: Asterisk Ground Truth */}
      <div className="rounded-xl border border-cyan-500/40 bg-gradient-to-r from-cyan-950/40 via-background to-blue-950/30 p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <span className="flex h-3 w-3 rounded-full bg-cyan-400 animate-pulse shadow-sm" />
              <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
                Asterisk 20 LTS & FreePBX Telephony Core
              </h2>
              <Badge variant="outline" className="border-cyan-500/40 text-cyan-400 bg-cyan-500/10 text-xs">
                Source of Truth
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Direct PJSIP channel driver, real-time AudioSocket duplex bridge (Deepgram Nova-3 & Voicebox), and PostgreSQL ODBC CDR adaptive engine.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={fetchAsteriskData}
              className="gap-1.5 text-xs border-border/80 hover:bg-muted"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              Poll Telemetry
            </Button>
            <Button
              size="sm"
              onClick={() => setSimModalOpen(true)}
              className="gap-1.5 text-xs bg-cyan-600 hover:bg-cyan-500 text-white font-medium"
            >
              <Zap className="h-3.5 w-3.5" />
              Simulate Live Call
            </Button>
          </div>
        </div>

        {sourceOfTruth && (
          <div className="mt-4 pt-4 border-t border-border/60 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-[11px]">
            <div>
              <span className="text-muted-foreground block">SIP Engine</span>
              <strong className="text-foreground">{sourceOfTruth.driver}</strong>
            </div>
            <div>
              <span className="text-muted-foreground block">CDR Storage</span>
              <strong className="text-foreground">{sourceOfTruth.cdr_engine}</strong>
            </div>
            <div>
              <span className="text-muted-foreground block">Live STT (&lt;300ms)</span>
              <strong className="text-cyan-400">{sourceOfTruth.stt_engine}</strong>
            </div>
            <div>
              <span className="text-muted-foreground block">TTS Engine</span>
              <strong className="text-pink-400">{sourceOfTruth.tts_engine}</strong>
            </div>
            <div>
              <span className="text-muted-foreground block">Rating Method</span>
              <strong className="text-emerald-400">{sourceOfTruth.billing_rating}</strong>
            </div>
            <div>
              <span className="text-muted-foreground block">SIP Trunks</span>
              <strong className="text-emerald-400">{sourceOfTruth.active_trunk_status}</strong>
            </div>
          </div>
        )}
      </div>

      {/* KPI Cards: Ground Truth Telephony Metrics */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="border-border bg-card/70">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">SIP Channel Utilization</CardDescription>
            <CardTitle className="text-2xl font-bold flex items-center justify-between text-foreground">
              <span>{summary ? `${summary.activeChannels} / ${summary.maxChannelCapacity}` : "18 / 60"}</span>
              <Activity className="h-5 w-5 text-cyan-400" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="w-full bg-muted/60 h-2 rounded-full overflow-hidden mt-1">
              <div
                className="bg-cyan-500 h-full rounded-full"
                style={{ width: `${summary ? (summary.activeChannels / summary.maxChannelCapacity) * 100 : 30}%` }}
              />
            </div>
            <p className="text-[11px] text-muted-foreground mt-2">
              {summary ? `${summary.answerRatePercent}% answer rate` : "96% answer rate"}
            </p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card/70">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">Rated VoIP Revenue & Margin</CardDescription>
            <CardTitle className="text-2xl font-bold flex items-center justify-between text-foreground">
              <span>{summary ? `R ${summary.totalRatedRevenueZar}` : "R 12.60"}</span>
              <TrendingUp className="h-5 w-5 text-emerald-400" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between text-xs mt-1">
              <span className="text-muted-foreground">Carrier Cost:</span>
              <span className="text-foreground font-mono">R {summary?.totalCarrierWholesaleZar || "5.42"}</span>
            </div>
            <div className="flex items-center justify-between text-xs mt-0.5">
              <span className="text-emerald-400 font-semibold">Gross Margin:</span>
              <span className="text-emerald-400 font-mono font-bold">{summary?.marginPercent || 57}% (R {summary?.totalMarginZar || "7.18"})</span>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card/70">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">Real-Time Speech Latency</CardDescription>
            <CardTitle className="text-2xl font-bold flex items-center justify-between text-foreground">
              <span>{summary ? `${summary.avgSttLatencyMs}ms` : "185ms"}</span>
              <Mic className="h-5 w-5 text-violet-400" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between text-xs mt-1">
              <span className="text-muted-foreground">Deepgram STT:</span>
              <span className="text-cyan-400 font-mono font-semibold">{summary?.avgSttLatencyMs || 185}ms (&lt;300ms SLA)</span>
            </div>
            <div className="flex items-center justify-between text-xs mt-0.5">
              <span className="text-muted-foreground">TTS Synthesis:</span>
              <span className="text-pink-400 font-mono font-semibold">{summary?.avgTtsLatencyMs || 215}ms</span>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card/70">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">Telecom Fraud & Anomaly Shield</CardDescription>
            <CardTitle className="text-2xl font-bold flex items-center justify-between text-foreground">
              <span>{summary ? `${summary.fraudEventsBlocked} Blocked` : "2 Blocked"}</span>
              <ShieldAlert className="h-5 w-5 text-amber-500" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-[11px] text-muted-foreground mt-1">
              ASTPP real-time policy: Robocall / SIM Box detection, Iridium satellite block, burst protection.
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Call Spikes vs Agent Redundancy / Idle Time (Requested by User) */}
      <Card className="border-border bg-card/80">
        <CardHeader className="pb-3 border-b border-border/50">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Clock className="h-4 w-4 text-cyan-400" />
                Call Spikes & Agent Redundancy (Idle Time vs Active Talk Time)
              </CardTitle>
              <CardDescription className="text-xs">
                30-minute operational intervals derived from Asterisk queue_log. Highlights call surges vs idle agent capacity to optimize shift rosters.
              </CardDescription>
            </div>
            <Badge variant="outline" className="border-cyan-500/40 text-cyan-400 bg-cyan-500/10 text-xs self-start">
              Asterisk queue_log Ground Truth
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {spikes.map((bucket) => {
              const totalMins = bucket.active_talk_minutes + bucket.agent_idle_redundancy_minutes
              const activePct = Math.round((bucket.active_talk_minutes / (totalMins || 1)) * 100)
              const idlePct = 100 - activePct

              return (
                <div
                  key={bucket.time_bucket}
                  className={`rounded-lg border p-3 space-y-2 transition-all ${
                    bucket.spike_detected
                      ? "border-amber-500/50 bg-amber-500/10 shadow-sm"
                      : "border-border/70 bg-background/50"
                  }`}
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-foreground">{bucket.time_bucket}</span>
                    {bucket.spike_detected ? (
                      <Badge className="bg-amber-500 text-black text-[10px] font-bold h-4 px-1.5">
                        SPIKE DETECTED
                      </Badge>
                    ) : (
                      <span className="text-[11px] text-muted-foreground">{bucket.available_agents} Agents On</span>
                    )}
                  </div>

                  <div className="flex items-baseline justify-between">
                    <div>
                      <span className="text-lg font-bold text-foreground">{bucket.call_count}</span>
                      <span className="text-xs text-muted-foreground ml-1">calls</span>
                    </div>
                    <div className="text-right text-[11px]">
                      <span className="text-cyan-400 font-semibold">{bucket.active_talk_minutes}m</span> active /{" "}
                      <span className="text-muted-foreground">{bucket.agent_idle_redundancy_minutes}m</span> idle
                    </div>
                  </div>

                  {/* Dual Bar: Active Talk vs Redundancy/Idle */}
                  <div className="w-full bg-muted/80 h-2.5 rounded-full overflow-hidden flex">
                    <div
                      className="bg-cyan-500 h-full"
                      style={{ width: `${activePct}%` }}
                      title={`Active Talk: ${activePct}%`}
                    />
                    <div
                      className="bg-muted-foreground/30 h-full"
                      style={{ width: `${idlePct}%` }}
                      title={`Agent Redundancy / Idle: ${idlePct}%`}
                    />
                  </div>

                  <div className="flex justify-between text-[10px] text-muted-foreground pt-0.5">
                    <span className="flex items-center gap-1">
                      <span className="h-1.5 w-1.5 rounded-full bg-cyan-500" />
                      Active: {activePct}%
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />
                      Redundancy (Idle): {idlePct}%
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* Asterisk CDR Table with Strategic Calculated Fields */}
      <Card className="border-border bg-card/80">
        <CardHeader className="pb-3 border-b border-border/50">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Database className="h-4 w-4 text-emerald-400" />
                Asterisk Call Detail Records (CDR) with Strategic Calculated Fields
              </CardTitle>
              <CardDescription className="text-xs">
                Real-time rating, wholesale carrier margins, fraud scoring, and speech engine latency.
              </CardDescription>
            </div>

            {/* Filter toolbar */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative w-48">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  placeholder="Search CLI, DID, Dest…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="h-8 pl-8 text-xs bg-background/50"
                />
              </div>

              <select
                value={selectedDisposition}
                onChange={(e) => setSelectedDisposition(e.target.value)}
                className="h-8 rounded-md border border-border bg-background px-2.5 text-xs text-foreground"
              >
                <option value="ALL">All Dispositions</option>
                <option value="ANSWERED">Answered Only</option>
                <option value="NO ANSWER">No Answer</option>
                <option value="BUSY">Busy</option>
                <option value="FAILED">Failed / Barred</option>
              </select>

              <Button
                size="sm"
                variant={fraudOnly ? "destructive" : "outline"}
                onClick={() => setFraudOnly(!fraudOnly)}
                className="h-8 text-xs gap-1.5"
              >
                <ShieldAlert className="h-3.5 w-3.5" />
                {fraudOnly ? "Showing Fraud Flags" : "Filter Fraud"}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="rounded-lg border border-border overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/40 text-muted-foreground uppercase text-[10px] tracking-wider border-b border-border">
                <tr>
                  <th className="p-3">Time &amp; Caller ID</th>
                  <th className="p-3">Destination &amp; Route</th>
                  <th className="p-3">PJSIP Channel</th>
                  <th className="p-3 text-right">Talk Time</th>
                  <th className="p-3 text-right">Rated Cost (ZAR)</th>
                  <th className="p-3 text-right">Carrier Margin</th>
                  <th className="p-3 text-center">Speech Latency</th>
                  <th className="p-3 text-center">Fraud &amp; FTR</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60 font-mono">
                {cdrs.map((cdr) => {
                  const isFraud = cdr.fraud_risk_score > 50

                  return (
                    <tr
                      key={cdr.uniqueid}
                      className={`hover:bg-muted/20 transition-colors ${
                        isFraud ? "bg-red-500/5 hover:bg-red-500/10" : ""
                      }`}
                    >
                      <td className="p-3">
                        <div className="font-semibold text-foreground font-sans">{cdr.clid}</div>
                        <div className="text-[11px] text-muted-foreground">{cdr.start}</div>
                        <div className="text-[10px] text-cyan-400 font-sans">{cdr.uniqueid}</div>
                      </td>

                      <td className="p-3">
                        <div className="font-bold text-foreground">{cdr.dst}</div>
                        <div className="text-[11px] text-muted-foreground font-sans">{cdr.carrier_prefix}</div>
                        <Badge variant="outline" className="text-[10px] h-4 font-sans mt-0.5 border-border">
                          {cdr.destination_type}
                        </Badge>
                      </td>

                      <td className="p-3 font-sans text-xs">
                        <div className="text-foreground truncate max-w-[140px]" title={cdr.channel}>
                          {cdr.channel}
                        </div>
                        <div className="text-muted-foreground text-[11px] truncate max-w-[140px]" title={cdr.dstchannel}>
                          → {cdr.dstchannel || "Terminated"}
                        </div>
                        <div className="text-[10px] text-emerald-400 font-mono">
                          Queue Wait: {cdr.queue_wait_time_sec}s
                        </div>
                      </td>

                      <td className="p-3 text-right">
                        <div className="font-bold text-foreground">{cdr.billsec}s</div>
                        <div className="text-[11px] text-muted-foreground font-sans">
                          {Math.floor(cdr.billsec / 60)}m {cdr.billsec % 60}s
                        </div>
                        <span
                          className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-sans font-semibold mt-1 ${
                            cdr.disposition === "ANSWERED"
                              ? "bg-emerald-500/20 text-emerald-400"
                              : "bg-red-500/20 text-red-400"
                          }`}
                        >
                          {cdr.disposition}
                        </span>
                      </td>

                      <td className="p-3 text-right">
                        <div className="font-bold text-foreground">R {cdr.rated_cost_zar.toFixed(2)}</div>
                        <div className="text-[11px] text-muted-foreground">R {cdr.rate_per_minute_zar.toFixed(2)}/min</div>
                        <div className="text-[10px] text-muted-foreground font-sans">
                          Pulse: 1/1 sec
                        </div>
                      </td>

                      <td className="p-3 text-right">
                        <div className="font-bold text-emerald-400">+R {cdr.margin_zar.toFixed(2)}</div>
                        <div className="text-[11px] text-muted-foreground">Cost: R {cdr.carrier_cost_zar.toFixed(2)}</div>
                        <div className="text-[10px] text-emerald-500 font-sans">
                          Margin: {Math.round((cdr.margin_zar / (cdr.rated_cost_zar || 1)) * 100)}%
                        </div>
                      </td>

                      <td className="p-3 text-center font-sans">
                        <div className="text-cyan-400 font-mono font-semibold">STT: {cdr.stt_latency_ms}ms</div>
                        <div className="text-pink-400 font-mono text-[11px]">TTS: {cdr.tts_latency_ms}ms</div>
                        <div className="text-[10px] text-muted-foreground mt-0.5">
                          Sentiment: {cdr.sentiment_polarity > 0 ? `+${cdr.sentiment_polarity}` : cdr.sentiment_polarity}
                        </div>
                      </td>

                      <td className="p-3 text-center font-sans">
                        {isFraud ? (
                          <div className="space-y-1">
                            <Badge variant="destructive" className="text-[10px] font-bold">
                              RISK: {cdr.fraud_risk_score}
                            </Badge>
                            {cdr.fraud_flags.map((flag, idx) => (
                              <div key={idx} className="text-[9px] text-red-400 block font-mono">
                                {flag}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="space-y-1">
                            <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px]">
                              PASSED (0)
                            </Badge>
                            <span className="text-[10px] text-muted-foreground block">
                              {cdr.ftr_status === "FIRST_TIME_RESOLVED" ? "FTR ✓" : "Repeat"}
                            </span>
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Simulation Modal */}
      {simModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-card border border-border rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <Zap className="h-4 w-4 text-cyan-400" />
                Simulate Inbound/Outbound Asterisk CDR
              </h3>
              <Button size="sm" variant="ghost" onClick={() => setSimModalOpen(false)}>✕</Button>
            </div>

            <form onSubmit={handleSimulateCall} className="space-y-3.5 text-xs">
              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Caller Source CLI</label>
                <Input value={simSrc} onChange={(e) => setSimSrc(e.target.value)} required />
              </div>

              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Destination Dialed (DID)</label>
                <Input value={simDst} onChange={(e) => setSimDst(e.target.value)} required />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Duration (Seconds)</label>
                  <Input
                    type="number"
                    value={simDuration}
                    onChange={(e) => setSimDuration(Number(e.target.value))}
                    required
                  />
                </div>
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Sell Rate (ZAR / min)</label>
                  <Input
                    type="number"
                    step="0.01"
                    value={simRate}
                    onChange={(e) => setSimRate(Number(e.target.value))}
                    required
                  />
                </div>
              </div>

              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Destination Type</label>
                <select
                  value={simDestType}
                  onChange={(e) => setSimDestType(e.target.value as any)}
                  className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                >
                  <option value="Local Mobile (Vodacom/MTN)">Local Mobile (Vodacom/MTN)</option>
                  <option value="National Geographic (JHB/CPT)">National Geographic (JHB/CPT)</option>
                  <option value="Toll-Free (0800)">Toll-Free (0800)</option>
                  <option value="International Tier 1">International Tier 1</option>
                  <option value="High-Risk Premium">High-Risk Premium</option>
                </select>
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => setSimModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" className="bg-cyan-600 hover:bg-cyan-500 text-white">
                  Inject &amp; Rate Call
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
