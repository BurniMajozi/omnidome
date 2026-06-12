"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import {
  Activity,
  Building2,
  CheckCircle2,
  CircleDollarSign,
  KeyRound,
  Link,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  ToggleLeft,
  ToggleRight,
  Users,
  XCircle,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  listUCPSessions,
  listIntentMandates,
  listPaymentMandates,
  type UCPCheckoutSession,
  type IntentMandate,
  type PaymentMandate,
} from "@/lib/orchestrator-api"
import { adminApi, type AdminUser, type AuditLogEntry, type CommissionTier, type ModuleCatalogItem, type Tenant } from "@/lib/admin-api"

const fmtDate = (value?: string) => {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "-"
  return date.toLocaleString()
}

function StatusBadge({ active, label }: { active?: boolean; label?: string }) {
  const enabled = active ?? String(label || "").toUpperCase() === "ACTIVE"
  return (
    <Badge variant="outline" className={enabled ? "border-emerald-500/40 text-emerald-400" : "border-red-500/40 text-red-400"}>
      {enabled ? <CheckCircle2 className="mr-1 h-3 w-3" /> : <XCircle className="mr-1 h-3 w-3" />}
      {label || (enabled ? "Active" : "Disabled")}
    </Badge>
  )
}

function DataRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border/60 py-2 text-sm last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium text-foreground">{value}</span>
    </div>
  )
}

export function AdminModule() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [modules, setModules] = useState<ModuleCatalogItem[]>([])
  const [tenantModules, setTenantModules] = useState<ModuleCatalogItem[]>([])
  const [users, setUsers] = useState<AdminUser[]>([])
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([])
  const [commissionTiers, setCommissionTiers] = useState<CommissionTier[]>([])
  const [selectedTenantId, setSelectedTenantId] = useState<string>("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [ucpSessions, setUcpSessions] = useState<UCPCheckoutSession[]>([])
  const [intentMandates, setIntentMandates] = useState<IntentMandate[]>([])
  const [paymentMandates, setPaymentMandates] = useState<PaymentMandate[]>([])

  const selectedTenant = useMemo(
    () => tenants.find((tenant) => tenant.id === selectedTenantId) || tenants[0],
    [selectedTenantId, tenants],
  )

  const loadAdminData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [tenantData, moduleData, userData, auditData, tierData, ucpData, mandateData, paymentData] = await Promise.all([
        adminApi.listTenants(),
        adminApi.listModules(),
        adminApi.listUsers().catch(() => []),
        adminApi.listAuditLog({ limit: 20 }).catch(() => []),
        adminApi.listCommissionTiers().catch(() => []),
        listUCPSessions(20).catch(() => []),
        listIntentMandates(20).catch(() => []),
        listPaymentMandates(20).catch(() => []),
      ])
      setTenants(tenantData)
      setModules(moduleData)
      setUsers(userData)
      setAuditLog(auditData)
      setCommissionTiers(tierData)
      setUcpSessions(ucpData)
      setIntentMandates(mandateData)
      setPaymentMandates(paymentData)
      const tenantId = selectedTenantId || tenantData[0]?.id || ""
      setSelectedTenantId(tenantId)
      if (tenantId) {
        setTenantModules(await adminApi.listTenantModules(tenantId))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin data")
    } finally {
      setLoading(false)
    }
  }, [selectedTenantId])

  useEffect(() => {
    void loadAdminData()
  }, [loadAdminData])

  const refreshTenantModules = async (tenantId: string) => {
    setSelectedTenantId(tenantId)
    setTenantModules(await adminApi.listTenantModules(tenantId))
  }

  const toggleTenantModule = async (moduleItem: ModuleCatalogItem) => {
    if (!selectedTenant) return
    const moduleName = moduleItem.module_name || moduleItem.key || moduleItem.name
    await adminApi.updateTenantModules(selectedTenant.id, [
      { name: moduleName, enabled: !moduleItem.enabled, config: moduleItem.config },
    ])
    await refreshTenantModules(selectedTenant.id)
  }

  const enabledModules = tenantModules.filter((item) => item.enabled).length
  const activeTenants = tenants.filter((tenant) => tenant.active || tenant.status === "ACTIVE").length

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight text-foreground">Platform Administration</h2>
          <p className="text-sm text-muted-foreground">Tenant, module, user, audit, and commercial control plane.</p>
        </div>
        <Button variant="outline" onClick={() => void loadAdminData()} disabled={loading}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      {error && (
        <Card className="border-red-500/30">
          <CardContent className="p-4 text-sm text-red-400">{error}</CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="text-sm text-muted-foreground">Tenants</p>
              <p className="text-2xl font-semibold">{tenants.length}</p>
            </div>
            <Building2 className="h-5 w-5 text-cyan-400" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="text-sm text-muted-foreground">Active Tenants</p>
              <p className="text-2xl font-semibold">{activeTenants}</p>
            </div>
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="text-sm text-muted-foreground">Catalog Modules</p>
              <p className="text-2xl font-semibold">{modules.length}</p>
            </div>
            <SlidersHorizontal className="h-5 w-5 text-amber-400" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="text-sm text-muted-foreground">Users</p>
              <p className="text-2xl font-semibold">{users.length}</p>
            </div>
            <Users className="h-5 w-5 text-violet-400" />
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="tenants" className="space-y-4">
        <TabsList className="flex w-full justify-start overflow-x-auto">
          <TabsTrigger value="tenants">Tenants</TabsTrigger>
          <TabsTrigger value="modules">Modules</TabsTrigger>
          <TabsTrigger value="users">Users</TabsTrigger>
          <TabsTrigger value="audit">Audit</TabsTrigger>
          <TabsTrigger value="commission">Commission</TabsTrigger>
          <TabsTrigger value="protocols">Protocols</TabsTrigger>
        </TabsList>

        <TabsContent value="tenants">
          <div className="grid gap-4 lg:grid-cols-2">
            {tenants.map((tenant) => (
              <Card key={tenant.id}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <CardTitle className="text-base">{tenant.name}</CardTitle>
                    <StatusBadge active={tenant.active} label={tenant.status} />
                  </div>
                </CardHeader>
                <CardContent>
                  <DataRow label="Domain" value={tenant.domain || tenant.subdomain || "-"} />
                  <DataRow label="Tier" value={tenant.tier || "-"} />
                  <DataRow label="Org code" value={tenant.org_code || "-"} />
                  <DataRow label="Created" value={fmtDate(tenant.created_at)} />
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="modules">
          <Card>
            <CardHeader>
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <CardTitle className="text-base">Tenant Module Entitlements</CardTitle>
                <select
                  className="h-10 rounded-md border border-border bg-background px-3 text-sm"
                  value={selectedTenant?.id || ""}
                  onChange={(event) => void refreshTenantModules(event.target.value)}
                >
                  {tenants.map((tenant) => (
                    <option key={tenant.id} value={tenant.id}>{tenant.name}</option>
                  ))}
                </select>
              </div>
            </CardHeader>
            <CardContent>
              <div className="mb-4 text-sm text-muted-foreground">
                {enabledModules} enabled for {selectedTenant?.name || "selected tenant"}
              </div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {tenantModules.map((item) => {
                  const key = item.module_name || item.key || item.name
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => void toggleTenantModule(item)}
                      className="rounded-lg border border-border bg-card p-4 text-left transition-colors hover:border-primary/50"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-medium">{item.name || key}</p>
                          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.description || key}</p>
                        </div>
                        {item.enabled ? <ToggleRight className="h-5 w-5 text-emerald-400" /> : <ToggleLeft className="h-5 w-5 text-muted-foreground" />}
                      </div>
                    </button>
                  )
                })}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="users">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base"><KeyRound className="h-4 w-4" /> Users</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {users.map((user) => (
                  <div key={user.id} className="flex items-center justify-between rounded-lg border border-border p-3">
                    <div>
                      <p className="font-medium">{user.name || user.full_name || user.email}</p>
                      <p className="text-xs text-muted-foreground">{user.email}</p>
                    </div>
                    <StatusBadge active={user.is_active} />
                  </div>
                ))}
                {users.length === 0 && <p className="text-sm text-muted-foreground">No users returned for this scope.</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="audit">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base"><Activity className="h-4 w-4" /> Recent Audit Events</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {auditLog.map((event) => (
                  <div key={event.id} className="rounded-lg border border-border p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium">{event.action}</p>
                        <p className="text-xs text-muted-foreground">{event.resource_type} {event.resource_id ? `- ${event.resource_id}` : ""}</p>
                      </div>
                      <span className="text-xs text-muted-foreground">{fmtDate(event.created_at)}</span>
                    </div>
                  </div>
                ))}
                {auditLog.length === 0 && <p className="text-sm text-muted-foreground">No audit events returned.</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="commission">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base"><CircleDollarSign className="h-4 w-4" /> Commission Tiers</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {commissionTiers.map((tier) => (
                  <div key={tier.id} className="rounded-lg border border-border p-4">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="font-medium">{tier.tier_name}</p>
                        <p className="text-xs text-muted-foreground">{tier.min_deals} to {tier.max_deals ?? "uncapped"} deals</p>
                      </div>
                      <StatusBadge active={tier.is_active} />
                    </div>
                    <p className="mt-4 text-2xl font-semibold">{tier.rate_percent}%</p>
                  </div>
                ))}
                {commissionTiers.length === 0 && <p className="text-sm text-muted-foreground">No commission tiers configured.</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="protocols">
          <div className="space-y-6">
            {/* Protocol summary stats */}
            <div className="grid gap-4 md:grid-cols-3">
              <Card>
                <CardContent className="flex items-center justify-between p-4">
                  <div>
                    <p className="text-sm text-muted-foreground">UCP Sessions</p>
                    <p className="text-2xl font-semibold">{ucpSessions.length}</p>
                  </div>
                  <Link className="h-5 w-5 text-cyan-400" />
                </CardContent>
              </Card>
              <Card>
                <CardContent className="flex items-center justify-between p-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Intent Mandates</p>
                    <p className="text-2xl font-semibold">{intentMandates.length}</p>
                  </div>
                  <ShieldCheck className="h-5 w-5 text-amber-400" />
                </CardContent>
              </Card>
              <Card>
                <CardContent className="flex items-center justify-between p-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Payment Mandates</p>
                    <p className="text-2xl font-semibold">{paymentMandates.length}</p>
                  </div>
                  <CircleDollarSign className="h-5 w-5 text-emerald-400" />
                </CardContent>
              </Card>
            </div>

            {/* UCP Checkout Sessions */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base"><Link className="h-4 w-4" /> UCP Checkout Sessions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {ucpSessions.map((session) => (
                    <div key={session.id} className="rounded-lg border border-border p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-medium">{session.merchant} — {session.purpose}</p>
                          <p className="text-xs text-muted-foreground">
                            {session.line_items.length} item(s) • {session.currency} {session.total.toFixed(2)}
                          </p>
                        </div>
                        <Badge variant="outline" className={
                          session.status === "completed" ? "border-emerald-500/40 text-emerald-400" :
                          session.status === "requires_approval" ? "border-amber-500/40 text-amber-400" :
                          session.status === "cancelled" ? "border-red-500/40 text-red-400" :
                          "border-border text-muted-foreground"
                        }>
                          {session.status}
                        </Badge>
                      </div>
                      <p className="mt-1 text-[10px] text-muted-foreground font-mono">{session.id}</p>
                    </div>
                  ))}
                  {ucpSessions.length === 0 && <p className="text-sm text-muted-foreground">No UCP checkout sessions.</p>}
                </div>
              </CardContent>
            </Card>

            {/* AP2 Intent Mandates */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="h-4 w-4" /> AP2 Intent Mandates</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {intentMandates.map((mandate) => (
                    <div key={mandate.id} className="rounded-lg border border-border p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-medium">{mandate.natural_language_description}</p>
                          <p className="text-xs text-muted-foreground">
                            Max: {mandate.currency} {mandate.max_amount.toFixed(2)}
                            {mandate.merchants.length > 0 && ` • Merchants: ${mandate.merchants.join(", ")}`}
                          </p>
                          <p className="text-[10px] text-muted-foreground">Expires: {fmtDate(mandate.expires_at)}</p>
                        </div>
                        <StatusBadge active={mandate.signed} label={mandate.signed ? "Signed" : "Pending"} />
                      </div>
                      <p className="mt-1 text-[10px] text-muted-foreground font-mono">{mandate.id}</p>
                    </div>
                  ))}
                  {intentMandates.length === 0 && <p className="text-sm text-muted-foreground">No AP2 intent mandates.</p>}
                </div>
              </CardContent>
            </Card>

            {/* AP2 Payment Mandates */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base"><CircleDollarSign className="h-4 w-4" /> AP2 Payment Mandates</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {paymentMandates.map((mandate) => (
                    <div key={mandate.id} className="rounded-lg border border-border p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-medium">{mandate.label}</p>
                          <p className="text-xs text-muted-foreground">
                            {mandate.merchant_agent} • {mandate.currency} {mandate.amount.toFixed(2)}
                          </p>
                        </div>
                        <Badge variant="outline" className={
                          mandate.status === "signed" ? "border-emerald-500/40 text-emerald-400" :
                          "border-amber-500/40 text-amber-400"
                        }>
                          {mandate.status}
                        </Badge>
                      </div>
                      <p className="mt-1 text-[10px] text-muted-foreground font-mono">{mandate.id}</p>
                    </div>
                  ))}
                  {paymentMandates.length === 0 && <p className="text-sm text-muted-foreground">No AP2 payment mandates.</p>}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}

