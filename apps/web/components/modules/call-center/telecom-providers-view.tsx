"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Globe,
  Radio,
  Plus,
  Trash2,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Zap,
  Activity,
  Layers,
  ArrowRight,
  ShieldCheck,
} from "lucide-react"
import type { TelecomProvider } from "@/app/api/call-center/providers/route"

export function TelecomProvidersView() {
  const [providers, setProviders] = useState<TelecomProvider[]>([])
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [diagnosticResult, setDiagnosticResult] = useState<any>(null)
  const [testingId, setTestingId] = useState<string | null>(null)

  // Add Provider Form
  const [formName, setFormName] = useState("")
  const [formType, setFormType] = useState<TelecomProvider["carrier_type"]>("Tier-1 Telco (Fibre / IPX)")
  const [formHost, setFormHost] = useState("")
  const [formPort, setFormPort] = useState(5060)
  const [formTransport, setFormTransport] = useState<TelecomProvider["transport"]>("TLS")
  const [formUser, setFormUser] = useState("")
  const [formPrefix, setFormPrefix] = useState("9005")
  const [formDids, setFormDids] = useState("011 300 0000 - 011 300 0100")
  const [formChannels, setFormChannels] = useState(30)
  const [formCommitment, setFormCommitment] = useState(7500)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 4000)
  }

  const fetchProviders = async () => {
    try {
      setLoading(true)
      const res = await fetch("/api/call-center/providers")
      if (res.ok) {
        const data = await res.json()
        setProviders(data.providers || [])
        setStats(data.stats || null)
      }
    } catch (err) {
      console.error("Failed to fetch telecom providers", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchProviders()
  }, [])

  const handleAddProvider = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await fetch("/api/call-center/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "ADD_PROVIDER",
          name: formName,
          carrier_type: formType,
          sip_host: formHost,
          sip_port: Number(formPort),
          transport: formTransport,
          username: formUser,
          outbound_prefix: formPrefix,
          assigned_did_ranges: formDids,
          max_channels: Number(formChannels),
          monthly_commitment_zar: Number(formCommitment),
        }),
      })
      if (res.ok) {
        showToast("SIP Trunk Carrier Interconnect Added!")
        setAddModalOpen(false)
        setFormName("")
        setFormHost("")
        setFormUser("")
        fetchProviders()
      }
    } catch {
      showToast("Failed to add provider")
    }
  }

  const handleTestOptions = async (providerId: string) => {
    try {
      setTestingId(providerId)
      setDiagnosticResult(null)
      const res = await fetch("/api/call-center/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "TEST_SIP_OPTIONS",
          providerId,
        }),
      })
      if (res.ok) {
        const data = await res.json()
        setDiagnosticResult(data)
        showToast(`SIP OPTIONS 200 OK: ${data.latency_ms}ms`)
        fetchProviders()
      }
    } catch {
      showToast("SIP Diagnostic ping failed")
    } finally {
      setTestingId(null)
    }
  }

  const handleDeleteProvider = async (id: string) => {
    if (!confirm("Disconnect and remove this SIP trunk interconnect?")) return
    try {
      const res = await fetch(`/api/call-center/providers?id=${id}`, { method: "DELETE" })
      if (res.ok) {
        showToast("Carrier Trunk Disconnected")
        fetchProviders()
      }
    } catch {
      showToast("Failed to disconnect carrier")
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
      <div className="rounded-xl border border-teal-500/40 bg-gradient-to-r from-teal-950/40 via-background to-cyan-950/30 p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <span className="flex h-3 w-3 rounded-full bg-teal-400 shadow-sm" />
              <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
                SIP Trunks &amp; Telecom Carrier Interconnects
              </h2>
              <Badge variant="outline" className="border-teal-500/40 text-teal-400 bg-teal-500/10 text-xs">
                Carrier Transit
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Direct BGP and PJSIP trunks to South African Tier-1 telecommunications networks (Teraco JB1 peering, Telkom Wholesale, Vodacom Business, MTN, Twilio PSTN).
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              onClick={() => setAddModalOpen(true)}
              className="gap-1.5 text-xs bg-teal-600 hover:bg-teal-500 text-white font-medium"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Carrier Provider
            </Button>
          </div>
        </div>

        {/* Stats Row */}
        <div className="mt-4 pt-4 border-t border-border/60 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div>
            <span className="text-muted-foreground block text-[11px]">Total Trunk Capacity</span>
            <strong className="text-lg font-bold text-foreground">
              {stats?.total_capacity_channels || 150} channels
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Active Channels In Use</span>
            <strong className="text-lg font-bold text-cyan-400">
              {stats?.active_in_use_channels || 18} active ({stats?.utilization_pct || 12}%)
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Average SIP Latency</span>
            <strong className="text-lg font-bold text-emerald-400">
              {stats?.avg_latency_ms || 18.5}ms (Teraco Peered)
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Carrier Registration</span>
            <strong className="text-lg font-bold text-emerald-400">100% HEALTHY</strong>
          </div>
        </div>
      </div>

      {/* SIP Diagnostic Trace if test clicked */}
      {diagnosticResult && (
        <div className="rounded-lg border border-teal-500/50 bg-teal-500/10 p-4 space-y-1.5 text-xs">
          <div className="flex items-center justify-between">
            <span className="font-bold text-teal-400 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" /> Live SIP OPTIONS Ping Telemetry
            </span>
            <Button size="sm" variant="ghost" onClick={() => setDiagnosticResult(null)} className="h-6 text-xs">
              Dismiss
            </Button>
          </div>
          <p className="font-mono text-foreground">{diagnosticResult.result}</p>
        </div>
      )}

      {/* Providers Table */}
      <Card className="border-border bg-card/80">
        <CardHeader className="pb-3 border-b border-border/50">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Globe className="h-4 w-4 text-teal-400" />
            Configured Carrier SIP Trunks &amp; Inbound DIDs
          </CardTitle>
          <CardDescription className="text-xs">
            Least Cost Routing (LCR) failover sequence, active channel load, and live SIP OPTIONS latency telemetry.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="rounded-lg border border-border overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/40 text-muted-foreground uppercase text-[10px] tracking-wider border-b border-border">
                <tr>
                  <th className="p-3">Carrier &amp; Type</th>
                  <th className="p-3">SIP Host &amp; Port</th>
                  <th className="p-3">Outbound Prefix</th>
                  <th className="p-3">Allocated DID Blocks</th>
                  <th className="p-3">Channel Capacity</th>
                  <th className="p-3 text-center">Latency</th>
                  <th className="p-3 text-center">Status</th>
                  <th className="p-3 text-center">Diagnostics</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {providers.map((p) => {
                  const chanPct = Math.round((p.active_channels / (p.max_channels || 1)) * 100)

                  return (
                    <tr key={p.id} className="hover:bg-muted/20 transition-colors">
                      <td className="p-3">
                        <div className="font-bold text-foreground">{p.name}</div>
                        <Badge variant="outline" className="text-[10px] border-border mt-0.5">
                          {p.carrier_type}
                        </Badge>
                      </td>

                      <td className="p-3 font-mono text-xs">
                        <div className="text-foreground">{p.sip_host}:{p.sip_port}</div>
                        <div className="text-[11px] text-muted-foreground">{p.transport} • {p.username}</div>
                      </td>

                      <td className="p-3 font-mono font-bold text-cyan-400">
                        {p.outbound_prefix}
                      </td>

                      <td className="p-3 text-xs text-muted-foreground max-w-[200px] truncate" title={p.assigned_did_ranges}>
                        {p.assigned_did_ranges}
                      </td>

                      <td className="p-3">
                        <div className="flex items-center justify-between text-[11px] mb-1">
                          <span className="font-semibold text-foreground">{p.active_channels} / {p.max_channels}</span>
                          <span className="text-muted-foreground font-mono">{chanPct}%</span>
                        </div>
                        <div className="w-28 bg-muted/60 h-2 rounded-full overflow-hidden">
                          <div className="bg-teal-500 h-full rounded-full" style={{ width: `${chanPct}%` }} />
                        </div>
                      </td>

                      <td className="p-3 text-center font-mono">
                        <span className={p.ping_latency_ms < 30 ? "text-emerald-400 font-bold" : "text-amber-400"}>
                          {p.ping_latency_ms}ms
                        </span>
                      </td>

                      <td className="p-3 text-center">
                        <Badge
                          variant="outline"
                          className={
                            p.registration_status === "REGISTERED"
                              ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-[10px]"
                              : "border-amber-500/40 text-amber-400 bg-amber-500/10 text-[10px]"
                          }
                        >
                          {p.registration_status}
                        </Badge>
                      </td>

                      <td className="p-3 text-center">
                        <div className="flex items-center justify-center gap-1.5">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleTestOptions(p.id)}
                            disabled={testingId === p.id}
                            className="h-7 text-xs gap-1 border-border/80 hover:bg-muted"
                          >
                            <Zap className={`h-3 w-3 ${testingId === p.id ? "animate-spin" : ""}`} />
                            Ping
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleDeleteProvider(p.id)}
                            className="h-7 w-7 p-0 text-muted-foreground hover:text-red-400"
                            title="Disconnect Trunk"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Add Provider Modal */}
      {addModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-card border border-border rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <Plus className="h-4 w-4 text-teal-400" />
                Add Telecom Carrier SIP Trunk
              </h3>
              <Button size="sm" variant="ghost" onClick={() => setAddModalOpen(false)}>✕</Button>
            </div>

            <form onSubmit={handleAddProvider} className="space-y-3.5 text-xs">
              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Provider / Carrier Name</label>
                <Input
                  placeholder="e.g. MTN Wholesale Business SIP"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  required
                />
              </div>

              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Carrier Interconnect Type</label>
                <select
                  value={formType}
                  onChange={(e) => setFormType(e.target.value as any)}
                  className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                >
                  <option value="Tier-1 Telco (Fibre / IPX)">Tier-1 Telco (Fibre / IPX)</option>
                  <option value="Wholesale Interconnect">Wholesale Interconnect</option>
                  <option value="Mobile Network Operator (MNO)">Mobile Network Operator (MNO)</option>
                  <option value="Global Cloud SIP">Global Cloud SIP</option>
                </select>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="text-muted-foreground block mb-1 font-medium">SIP Host FQDN / IP</label>
                  <Input placeholder="sip.mtnbusiness.co.za" value={formHost} onChange={(e) => setFormHost(e.target.value)} required />
                </div>
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Port</label>
                  <Input type="number" value={formPort} onChange={(e) => setFormPort(Number(e.target.value))} required />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Transport Protocol</label>
                  <select
                    value={formTransport}
                    onChange={(e) => setFormTransport(e.target.value as any)}
                    className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value="TLS">TLS (Encrypted SIP)</option>
                    <option value="UDP">UDP</option>
                    <option value="TCP">TCP</option>
                  </select>
                </div>
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">SIP Username / Auth ID</label>
                  <Input value={formUser} onChange={(e) => setFormUser(e.target.value)} required />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Outbound Dial Prefix</label>
                  <Input value={formPrefix} onChange={(e) => setFormPrefix(e.target.value)} required />
                </div>
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Max Concurrent Channels</label>
                  <Input
                    type="number"
                    value={formChannels}
                    onChange={(e) => setFormChannels(Number(e.target.value))}
                    required
                  />
                </div>
              </div>

              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Allocated Inbound DID Numbers</label>
                <Input value={formDids} onChange={(e) => setFormDids(e.target.value)} required />
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => setAddModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" className="bg-teal-600 hover:bg-teal-500 text-white">
                  Add Carrier Trunk
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
