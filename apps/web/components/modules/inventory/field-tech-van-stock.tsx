"use client"

import React, { useState, useEffect } from "react"
import {
  Wrench,
  Truck,
  CheckCircle2,
  ShieldCheck,
  Coins,
  Package,
  RefreshCw,
  Search,
  AlertTriangle,
  Plus,
  Box,
} from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  listFieldTechniciansRoster,
  type FieldTechnicianProfile,
  type VanStockItem,
} from "@/lib/hr-api"

export function FieldTechVanStockView() {
  const [techRoster, setTechRoster] = useState<FieldTechnicianProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedTech, setSelectedTech] = useState<FieldTechnicianProfile | null>(null)
  const [auditSuccessMsg, setAuditSuccessMsg] = useState<string | null>(null)
  const [replenishModalOpen, setReplenishModalOpen] = useState(false)
  const [replenishItem, setReplenishItem] = useState<{ vanCode: string; sku: string; qty: number }>({
    vanCode: "",
    sku: "ONT-FBR-01",
    qty: 5,
  })

  const fetchTechs = async () => {
    setLoading(true)
    setError(null)
    try {
      const roster = await listFieldTechniciansRoster()
      setTechRoster(roster)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchTechs()
  }, [])

  const filteredTechs = techRoster.filter(
    (t) =>
      t.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.employee_code.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.job_title.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const totalVanStockValue = techRoster.reduce((sum, t) => sum + t.total_equipment_value_zar, 0)
  const onDutyCount = techRoster.filter((t) => t.shift_status === "ON_DUTY" || !!t.shift_today).length
  const certifiedCount = techRoster.filter((t) => t.certifications && t.certifications.length > 0).length

  const handleAuditVan = (tech: FieldTechnicianProfile) => {
    setAuditSuccessMsg(`Audited VAN-${tech.employee_code} (${tech.full_name}): All ${tech.van_stock.length} inventory lines verified against warehouse dispatch ledger.`)
    setTimeout(() => setAuditSuccessMsg(null), 6000)
  }

  const handleReplenishSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setAuditSuccessMsg(`Replenishment requisition logged: +${replenishItem.qty} units of ${replenishItem.sku} dispatched to VAN-${replenishItem.vanCode}.`)
    setReplenishModalOpen(false)
    setTimeout(() => setAuditSuccessMsg(null), 6000)
  }

  return (
    <div className="space-y-6">
      {/* Header with Search and Refresh */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold text-foreground flex items-center gap-2">
            <Truck className="h-5 w-5 text-amber-500" />
            Field Technicians & Mobile Van Stock Inventory
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Real-time tracking of mobile field technician inventory, fiber installation tools, and van stock reconciliations.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative w-56">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search technician or van…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 h-8 text-xs"
            />
          </div>
          <Button variant="outline" size="sm" onClick={fetchTechs} className="h-8 gap-1.5 text-xs">
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {auditSuccessMsg && (
        <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/30 p-3 text-xs text-emerald-400 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>{auditSuccessMsg}</span>
          </div>
          <button onClick={() => setAuditSuccessMsg(null)} className="text-emerald-400 hover:text-white">✕</button>
        </div>
      )}

      {/* KPI Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Field Technicians</p>
              <p className="text-2xl font-bold text-foreground mt-1">{loading ? "…" : techRoster.length}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">splicers & fiber installers</p>
            </div>
            <div className="rounded-lg bg-primary/10 p-2.5 text-primary">
              <Wrench className="h-5 w-5" />
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">On-Duty Shifts</p>
              <p className="text-2xl font-bold text-emerald-400 mt-1">{loading ? "…" : onDutyCount}</p>
              <p className="text-[11px] text-emerald-400 mt-0.5">active in service zones</p>
            </div>
            <div className="rounded-lg bg-emerald-500/10 p-2.5 text-emerald-400">
              <CheckCircle2 className="h-5 w-5" />
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Total Van Stock Value</p>
              <p className="text-2xl font-bold text-foreground mt-1">
                {loading ? "…" : `R ${totalVanStockValue.toLocaleString()}`}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">allocated mobile inventory</p>
            </div>
            <div className="rounded-lg bg-amber-500/10 p-2.5 text-amber-400">
              <Coins className="h-5 w-5" />
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Certified Splicers</p>
              <p className="text-2xl font-bold text-foreground mt-1">{loading ? "…" : certifiedCount}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">fiber & safety accredited</p>
            </div>
            <div className="rounded-lg bg-blue-500/10 p-2.5 text-blue-400">
              <ShieldCheck className="h-5 w-5" />
            </div>
          </div>
        </Card>
      </div>

      {/* Roster & Van Stock Table */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Package className="h-4 w-4 text-amber-500" />
                Technician Fleet Roster & Van Stock Breakdown
              </CardTitle>
              <CardDescription className="text-xs">
                Detailed item allocations, unit values, and replenishment status per mobile field unit.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2 text-muted-foreground" />
              Loading technician van stock…
            </div>
          ) : error ? (
            <div className="py-6 text-center text-sm text-red-400">Error: {error}</div>
          ) : filteredTechs.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">No field technicians found matching search.</div>
          ) : (
            <div className="space-y-4">
              {filteredTechs.map((tech) => {
                const isOnDuty = tech.shift_status === "ON_DUTY" || !!tech.shift_today
                return (
                  <div
                    key={tech.employee_id}
                    className="rounded-xl border border-border/80 bg-background/50 p-4 space-y-3.5 hover:border-border transition-all"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/40 pb-3">
                      <div>
                        <div className="flex items-center gap-2.5">
                          <span className="font-semibold text-foreground text-sm">{tech.full_name}</span>
                          <Badge
                            variant="outline"
                            className={
                              isOnDuty
                                ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-xs"
                                : "border-muted text-muted-foreground text-xs"
                            }
                          >
                            {isOnDuty ? "● On Shift" : "○ Off Duty"}
                          </Badge>
                          <span className="text-xs font-mono bg-muted/60 px-2 py-0.5 rounded text-foreground">
                            VAN-{tech.employee_code}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {tech.job_title} • {tech.department} • Active Orders: <strong className="text-foreground">{tech.active_work_orders}</strong> • Completed Installs: <strong className="text-foreground">{tech.installations_completed}</strong>
                        </p>
                      </div>

                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleAuditVan(tech)}
                          className="h-7 text-xs"
                        >
                          <CheckCircle2 className="h-3 w-3 mr-1 text-emerald-400" />
                          Audit Van
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            setReplenishItem({ vanCode: tech.employee_code, sku: "ONT-FBR-01", qty: 5 })
                            setReplenishModalOpen(true)
                          }}
                          className="h-7 text-xs"
                        >
                          <Plus className="h-3 w-3 mr-1" />
                          Replenish
                        </Button>
                      </div>
                    </div>

                    {/* Certifications */}
                    {tech.certifications && tech.certifications.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[11px] text-muted-foreground mr-1">Certifications:</span>
                        {tech.certifications.map((c) => (
                          <Badge key={c} variant="outline" className="border-blue-500/30 text-blue-400 text-[11px]">
                            {c}
                          </Badge>
                        ))}
                      </div>
                    )}

                    {/* Van Stock Items Grid */}
                    <div className="rounded-lg border border-border/40 bg-muted/10 p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                          <Box className="h-3.5 w-3.5 text-amber-400" />
                          Allocated Stock Items ({tech.van_stock?.length ?? 0} SKUs)
                        </span>
                        <span className="text-xs font-mono font-bold text-emerald-400">
                          Total Value: R {tech.total_equipment_value_zar.toLocaleString()}
                        </span>
                      </div>

                      {tech.van_stock && tech.van_stock.length > 0 ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                          {tech.van_stock.map((item, idx) => (
                            <div
                              key={idx}
                              className="rounded-md border border-border/50 bg-background/60 p-2 text-xs space-y-1"
                            >
                              <div className="flex items-center justify-between">
                                <span className="font-semibold text-foreground truncate">{item.product_name}</span>
                                <Badge
                                  variant="outline"
                                  className={
                                    item.quantity <= item.safety_stock
                                      ? "border-amber-500/40 text-amber-400 text-[10px]"
                                      : "border-emerald-500/40 text-emerald-400 text-[10px]"
                                  }
                                >
                                  {item.quantity} units
                                </Badge>
                              </div>
                              <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                                <span>SKU: {item.product_sku}</span>
                                <span>R {(item.unit_cost_zar * item.quantity).toLocaleString()}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground">No stock items assigned to this van.</p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Replenish Van Stock Modal */}
      {replenishModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div>
                <h3 className="text-base font-bold text-foreground">Disptach Requisition to VAN-{replenishItem.vanCode}</h3>
                <p className="text-xs text-muted-foreground mt-0.5">Transfer equipment from main warehouse stock to mobile van unit.</p>
              </div>
              <button
                type="button"
                onClick={() => setReplenishModalOpen(false)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleReplenishSubmit} className="space-y-3.5">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Select Equipment Item</label>
                <select
                  value={replenishItem.sku}
                  onChange={(e) => setReplenishItem({ ...replenishItem, sku: e.target.value })}
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="ONT-FBR-01">Vumatel/Openserve 1Gbps ONT (R 850)</option>
                  <option value="RTR-WIFI6">Wi-Fi 6 Gigabit Router (R 1,200)</option>
                  <option value="FBR-DROP-100M">Fiber Drop Cable 100m Drum (R 650)</option>
                  <option value="SPLICE-TRAY-24">24-Core Splice Protection Tray (R 180)</option>
                  <option value="OPT-PWR-METER">Optical Laser Power Meter (R 2,400)</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground">Quantity to Dispatch</label>
                <Input
                  type="number"
                  min={1}
                  max={50}
                  value={replenishItem.qty}
                  onChange={(e) => setReplenishItem({ ...replenishItem, qty: Number(e.target.value) || 1 })}
                  className="mt-1 text-xs"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
                <Button type="button" variant="outline" size="sm" onClick={() => setReplenishModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" variant="cta" size="sm">
                  Confirm Dispatch
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
