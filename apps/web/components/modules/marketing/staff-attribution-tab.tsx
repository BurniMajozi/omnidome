"use client"

import React, { useState, useEffect } from "react"
import {
  Layers,
  Target,
  TrendingUp,
  DollarSign,
  Users,
  CheckCircle2,
  RefreshCw,
  Search,
  ExternalLink,
  Plus,
} from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  getMarketingStaffAttribution,
  type MarketingStaffAttribution,
} from "@/lib/hr-api"

export function StaffAttributionTab() {
  const [staffList, setStaffList] = useState<MarketingStaffAttribution[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")

  const fetchAttribution = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getMarketingStaffAttribution()
      setStaffList(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchAttribution()
  }, [])

  const filtered = staffList.filter(
    (s) =>
      s.employee_name.toLowerCase().includes(search.toLowerCase()) ||
      s.job_title.toLowerCase().includes(search.toLowerCase()) ||
      s.campaign_names.some((c) => c.toLowerCase().includes(search.toLowerCase()))
  )

  const totalBudget = staffList.reduce((sum, s) => sum + s.total_budget_managed_zar, 0)
  const totalConversions = staffList.reduce((sum, s) => sum + s.total_conversions_delivered, 0)
  const totalCampaigns = staffList.reduce((sum, s) => sum + s.active_campaigns_count, 0)

  return (
    <div className="space-y-6">
      {/* Header and Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-foreground flex items-center gap-2">
            <Layers className="h-5 w-5 text-primary" />
            Marketing Staff Attribution & Inbound Delivery
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Links campaign managers and creative staff directly to ad performance, spend budgets, and lead acquisition metrics.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative w-60">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search manager or campaign…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-8 text-xs"
            />
          </div>
          <Button variant="outline" size="sm" onClick={fetchAttribution} className="h-8 gap-1.5 text-xs">
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {/* KPI Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Campaign Managers</p>
              <p className="text-2xl font-bold text-foreground mt-1">{loading ? "…" : staffList.length}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{totalCampaigns} active campaigns</p>
            </div>
            <div className="rounded-lg bg-primary/10 p-2.5 text-primary">
              <Users className="h-5 w-5" />
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Managed Budget (ZAR)</p>
              <p className="text-2xl font-bold text-foreground mt-1">
                {loading ? "…" : `R ${totalBudget.toLocaleString()}`}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">monthly ad allocations</p>
            </div>
            <div className="rounded-lg bg-emerald-500/10 p-2.5 text-emerald-400">
              <DollarSign className="h-5 w-5" />
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Delivered Conversions</p>
              <p className="text-2xl font-bold text-emerald-400 mt-1">
                {loading ? "…" : totalConversions.toLocaleString()}
              </p>
              <p className="text-[11px] text-emerald-400 mt-0.5">verified customer leads</p>
            </div>
            <div className="rounded-lg bg-purple-500/10 p-2.5 text-purple-400">
              <Target className="h-5 w-5" />
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Pipeline Inbound Rate</p>
              <p className="text-2xl font-bold text-cyan-400 mt-1">+18.4%</p>
              <p className="text-[11px] text-cyan-400 mt-0.5">ad-to-sales velocity</p>
            </div>
            <div className="rounded-lg bg-cyan-500/10 p-2.5 text-cyan-400">
              <TrendingUp className="h-5 w-5" />
            </div>
          </div>
        </Card>
      </div>

      {/* Attribution Roster Table */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Target className="h-4 w-4 text-primary" />
                Staff Attribution Matrix & Campaign Ownership
              </CardTitle>
              <CardDescription className="text-xs">
                Direct attribution across Digital Ad campaigns, Social Media queues, and WhatsApp conversion funnels.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px]">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2.5 pr-4 font-medium">Campaign Manager</th>
                  <th className="py-2.5 pr-4 font-medium">Role</th>
                  <th className="py-2.5 pr-4 font-medium">Assigned Campaigns</th>
                  <th className="py-2.5 pr-4 font-medium">Budget Managed</th>
                  <th className="py-2.5 pr-4 font-medium">Conversions</th>
                  <th className="py-2.5 pr-4 font-medium">Efficiency</th>
                  <th className="py-2.5 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                      <RefreshCw className="h-4 w-4 animate-spin inline mr-2 text-muted-foreground" />
                      Loading attribution telemetry…
                    </td>
                  </tr>
                ) : error ? (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-sm text-red-400">
                      Error: {error}
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-sm text-muted-foreground">
                      No staff attribution records match query.
                    </td>
                  </tr>
                ) : (
                  filtered.map((staff) => (
                    <tr key={staff.employee_id} className="border-b border-border/60 text-sm hover:bg-muted/30">
                      <td className="py-3 pr-4 font-medium text-foreground">
                        <div className="flex items-center gap-2.5">
                          <div className="h-8 w-8 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold text-xs">
                            {staff.employee_name
                              .split(" ")
                              .map((n) => n[0])
                              .join("")
                              .slice(0, 2)}
                          </div>
                          <div>
                            <span className="font-semibold text-foreground text-sm">{staff.employee_name}</span>
                            <p className="text-[11px] text-muted-foreground">ID: {staff.employee_id.slice(0, 8)}</p>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 pr-4 text-xs text-muted-foreground">{staff.job_title}</td>
                      <td className="py-3 pr-4">
                        <div className="flex flex-wrap gap-1 max-w-xs">
                          {staff.campaign_names.map((c) => (
                            <Badge key={c} variant="outline" className="border-border text-foreground text-[11px]">
                              {c}
                            </Badge>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs font-semibold text-foreground">
                        R {staff.total_budget_managed_zar.toLocaleString()}
                      </td>
                      <td className="py-3 pr-4 font-semibold text-emerald-400 text-xs">
                        {staff.total_conversions_delivered} leads
                      </td>
                      <td className="py-3 pr-4">
                        <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-xs">
                          High Attribution
                        </Badge>
                      </td>
                      <td className="py-3">
                        <Button size="sm" variant="outline" className="h-7 text-xs">
                          Audit ROI
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
