"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Server,
  HardDrive,
  Plus,
  Trash2,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Wifi,
  ExternalLink,
  ShieldCheck,
  Cpu,
} from "lucide-react"
import type { VoipHardwareDevice } from "@/app/api/call-center/hardware/route"

export function VoipHardwareView() {
  const [devices, setDevices] = useState<VoipHardwareDevice[]>([])
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // Add Hardware Form
  const [formBrand, setFormBrand] = useState<VoipHardwareDevice["brand"]>("Yealink")
  const [formModel, setFormModel] = useState("SIP-T46U Gigabit Executive")
  const [formMac, setFormMac] = useState("")
  const [formExt, setFormExt] = useState("")
  const [formAgent, setFormAgent] = useState("")
  const [formIp, setFormIp] = useState("192.168.10.")
  const [formTransport, setFormTransport] = useState<VoipHardwareDevice["sip_transport"]>("TLS")

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 4000)
  }

  const fetchHardware = async () => {
    try {
      setLoading(true)
      const res = await fetch("/api/call-center/hardware")
      if (res.ok) {
        const data = await res.json()
        setDevices(data.devices || [])
        setStats(data.stats || null)
      }
    } catch (err) {
      console.error("Failed to load hardware", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchHardware()
  }, [])

  const handleAddDevice = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await fetch("/api/call-center/hardware", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          brand: formBrand,
          model: formModel,
          mac_address: formMac,
          assigned_extension: formExt,
          agent_name: formAgent,
          ip_address: formIp,
          sip_transport: formTransport,
        }),
      })
      if (res.ok) {
        showToast("VoIP Hardware Provisioned & Registered!")
        setAddModalOpen(false)
        setFormMac("")
        setFormExt("")
        setFormAgent("")
        fetchHardware()
      }
    } catch {
      showToast("Failed to add hardware")
    }
  }

  const handleDeleteDevice = async (id: string) => {
    if (!confirm("De-provision this hardware device?")) return
    try {
      const res = await fetch(`/api/call-center/hardware?id=${id}`, { method: "DELETE" })
      if (res.ok) {
        showToast("Device De-provisioned")
        fetchHardware()
      }
    } catch {
      showToast("Failed to delete device")
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
      <div className="rounded-xl border border-indigo-500/40 bg-gradient-to-r from-indigo-950/40 via-background to-blue-950/30 p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <span className="flex h-3 w-3 rounded-full bg-indigo-400 shadow-sm" />
              <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
                VoIP Hardware &amp; Auto-Provisioning Directory
              </h2>
              <Badge variant="outline" className="border-indigo-500/40 text-indigo-400 bg-indigo-500/10 text-xs">
                Zero-Touch Provisioning
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Manage enterprise SIP deskphones, conference phones, paging horns, and analog telephone adapters (ATAs) across all customer service desks and field vehicles.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              onClick={() => setAddModalOpen(true)}
              className="gap-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-medium"
            >
              <Plus className="h-3.5 w-3.5" />
              Add VoIP Device
            </Button>
          </div>
        </div>

        {/* Stats Row */}
        <div className="mt-4 pt-4 border-t border-border/60 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div>
            <span className="text-muted-foreground block text-[11px]">Total Provisioned Units</span>
            <strong className="text-lg font-bold text-foreground">
              {stats?.total_hardware_units || 4} units
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Online &amp; Active</span>
            <strong className="text-lg font-bold text-emerald-400">
              {stats?.online_active || 4} registered
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Auto-Provisioning URL</span>
            <strong className="text-lg font-bold text-cyan-400 font-mono text-[11px]">
              prov.omnidome.internal
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Supported Hardware</span>
            <strong className="text-lg font-bold text-purple-400">
              Yealink • Grandstream • Cisco
            </strong>
          </div>
        </div>
      </div>

      {/* Devices Table */}
      <Card className="border-border bg-card/80">
        <CardHeader className="pb-3 border-b border-border/50">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <HardDrive className="h-4 w-4 text-indigo-400" />
            Registered VoIP Endpoints &amp; MAC Bindings
          </CardTitle>
          <CardDescription className="text-xs">
            PJSIP endpoints, active IP addresses, TLS security transport, and auto-generated provisioning config files.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="rounded-lg border border-border overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/40 text-muted-foreground uppercase text-[10px] tracking-wider border-b border-border">
                <tr>
                  <th className="p-3">Device Brand &amp; Model</th>
                  <th className="p-3">MAC Address</th>
                  <th className="p-3">Extension &amp; Assigned Agent</th>
                  <th className="p-3">IP Address</th>
                  <th className="p-3">Transport</th>
                  <th className="p-3">Provisioning Config</th>
                  <th className="p-3 text-center">Status</th>
                  <th className="p-3 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {devices.map((device) => (
                  <tr key={device.id} className="hover:bg-muted/20 transition-colors">
                    <td className="p-3">
                      <div className="font-semibold text-foreground">{device.brand}</div>
                      <div className="text-[11px] text-muted-foreground">{device.model}</div>
                      <div className="text-[10px] text-muted-foreground font-mono">{device.firmware_version}</div>
                    </td>

                    <td className="p-3 font-mono text-cyan-400 font-bold text-xs">
                      {device.mac_address}
                    </td>

                    <td className="p-3">
                      <div className="font-bold text-foreground">Ext {device.assigned_extension}</div>
                      <div className="text-[11px] text-muted-foreground">{device.agent_name}</div>
                    </td>

                    <td className="p-3 font-mono text-muted-foreground">
                      {device.ip_address}
                    </td>

                    <td className="p-3">
                      <Badge variant="outline" className="border-border text-[10px] font-mono">
                        {device.sip_transport}
                      </Badge>
                    </td>

                    <td className="p-3 font-mono text-[10px] text-muted-foreground truncate max-w-[180px]" title={device.provisioning_url}>
                      {device.provisioning_url}
                    </td>

                    <td className="p-3 text-center">
                      <Badge
                        variant="outline"
                        className={
                          device.status === "REGISTERED"
                            ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-[10px]"
                            : device.status === "IN_CALL"
                            ? "border-blue-500/40 text-blue-400 bg-blue-500/10 text-[10px]"
                            : "border-red-500/40 text-red-400 bg-red-500/10 text-[10px]"
                        }
                      >
                        {device.status.replace(/_/g, " ")}
                      </Badge>
                    </td>

                    <td className="p-3 text-center">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDeleteDevice(device.id)}
                        className="h-7 w-7 p-0 text-muted-foreground hover:text-red-400"
                        title="Remove Device"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Add Hardware Modal */}
      {addModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-card border border-border rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <Plus className="h-4 w-4 text-indigo-400" />
                Add VoIP Hardware Endpoint
              </h3>
              <Button size="sm" variant="ghost" onClick={() => setAddModalOpen(false)}>✕</Button>
            </div>

            <form onSubmit={handleAddDevice} className="space-y-3.5 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Hardware Brand</label>
                  <select
                    value={formBrand}
                    onChange={(e) => setFormBrand(e.target.value as any)}
                    className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value="Yealink">Yealink</option>
                    <option value="Grandstream">Grandstream</option>
                    <option value="Cisco">Cisco MPP</option>
                    <option value="Polycom">Polycom VVX</option>
                    <option value="Fanvil">Fanvil</option>
                    <option value="AudioCodes ATA">AudioCodes FXS ATA</option>
                  </select>
                </div>
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Model</label>
                  <Input value={formModel} onChange={(e) => setFormModel(e.target.value)} required />
                </div>
              </div>

              <div>
                <label className="text-muted-foreground block mb-1 font-medium">MAC Address (e.g. 80:5E:C0:11:A2:40)</label>
                <Input
                  placeholder="80:5E:C0:11:A2:40"
                  value={formMac}
                  onChange={(e) => setFormMac(e.target.value)}
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Assigned Extension</label>
                  <Input placeholder="e.g. 105" value={formExt} onChange={(e) => setFormExt(e.target.value)} required />
                </div>
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Agent Name</label>
                  <Input placeholder="e.g. Sipho Khumalo" value={formAgent} onChange={(e) => setFormAgent(e.target.value)} required />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Assigned Static / DHCP IP</label>
                  <Input value={formIp} onChange={(e) => setFormIp(e.target.value)} required />
                </div>
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">SIP Transport</label>
                  <select
                    value={formTransport}
                    onChange={(e) => setFormTransport(e.target.value as any)}
                    className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value="TLS">TLS (Encrypted SRTP)</option>
                    <option value="UDP">UDP</option>
                    <option value="TCP">TCP</option>
                    <option value="WSS (WebRTC)">WSS (WebRTC In-Browser)</option>
                  </select>
                </div>
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => setAddModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white">
                  Provision Hardware
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
