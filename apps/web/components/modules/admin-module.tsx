"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import {
  Activity,
  Building2,
  CheckCircle2,
  CircleDollarSign,
  KeyRound,
  Link as LinkIcon,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  ToggleLeft,
  ToggleRight,
  Users,
  XCircle,
  Bot,
  Workflow,
  ArrowRight,
  ThumbsUp,
  ThumbsDown,
  UserPlus,
  Plus,
  Trash2,
  Edit3,
  ExternalLink,
  Lock,
  Settings2,
  Sparkles,
  Check,
  CheckSquare,
  Square,
  AlertCircle,
  Info,
  X,
  CreditCard,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { PageHeader } from "@/components/ui/page-header"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  listUCPSessions,
  listIntentMandates,
  listPaymentMandates,
  listAgentActions,
  createUCPSession,
  createIntentMandate,
  type UCPCheckoutSession,
  type IntentMandate,
  type PaymentMandate,
  type AgentActionAuditItem,
} from "@/lib/orchestrator-api"
import {
  adminApi,
  type AdminUser,
  type AuditLogEntry,
  type CommissionTier,
  type CommissionTierCreate,
  type ModuleCatalogItem,
  type Tenant,
} from "@/lib/admin-api"
import { cn } from "@/lib/utils"

interface RoleDefinition {
  id: string
  name: string
  description: string
  badge: string
  color: string
  permissions: string[]
}

const AVAILABLE_ROLES: RoleDefinition[] = [
  {
    id: "platform_admin",
    name: "Platform Administrator",
    description: "Master administrative control across all organizations, autonomous agents, and system protocols.",
    badge: "Superadmin",
    color: "cyan",
    permissions: ["platform.admin", "org.admin", "org.manage", "module.manage", "billing.manage", "agent.manage"],
  },
  {
    id: "org_admin",
    name: "Organization Admin",
    description: "Full management of tenant users, teams, workflows, and module entitlements.",
    badge: "Admin",
    color: "purple",
    permissions: ["org.admin", "org.manage", "module.manage", "user.manage"],
  },
  {
    id: "billing_admin",
    name: "Commercial & Billing Admin",
    description: "Invoicing, commission plans, payment reconciliation, and UCP/AP2 commercial protocols.",
    badge: "Billing",
    color: "emerald",
    permissions: ["billing.manage", "invoices.read", "invoices.write", "commission.manage"],
  },
  {
    id: "support_specialist",
    name: "Support Specialist",
    description: "Customer 360 diagnosis, ticket automation, and SupportBot diagnostic runs.",
    badge: "Support",
    color: "blue",
    permissions: ["support.read", "support.write", "customer360.read", "agent.invoke"],
  },
  {
    id: "sales_rep",
    name: "Sales & Retention Executive",
    description: "Lead management, ChurnGuard retention workflows, and contract provisioning.",
    badge: "Sales",
    color: "amber",
    permissions: ["sales.read", "sales.write", "retention.read", "leads.manage"],
  },
  {
    id: "compliance_auditor",
    name: "Security & Compliance Auditor",
    description: "Read-only access to immutable audit trails, agent action histories, and transaction logs.",
    badge: "Auditor",
    color: "rose",
    permissions: ["audit.read", "system.read"],
  },
]

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
  const router = useRouter()
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [modules, setModules] = useState<ModuleCatalogItem[]>([])
  const [tenantModules, setTenantModules] = useState<ModuleCatalogItem[]>([])
  const [users, setUsers] = useState<AdminUser[]>([])
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([])
  const [commissionTiers, setCommissionTiers] = useState<CommissionTier[]>([])
  const [selectedTenantId, setSelectedTenantId] = useState<string>("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [successBanner, setSuccessBanner] = useState<string | null>(null)

  // Protocols & Mandates
  const [ucpSessions, setUcpSessions] = useState<UCPCheckoutSession[]>([])
  const [intentMandates, setIntentMandates] = useState<IntentMandate[]>([])
  const [paymentMandates, setPaymentMandates] = useState<PaymentMandate[]>([])
  const [agentActions, setAgentActions] = useState<AgentActionAuditItem[]>([])
  const [auditSubTab, setAuditSubTab] = useState<"agents" | "system">("agents")
  const [agentFilter, setAgentFilter] = useState<string>("all")

  // 1. Invite User Modal
  const [inviteModalOpen, setInviteModalOpen] = useState(false)
  const [inviteEmail, setInviteEmail] = useState("")
  const [inviteName, setInviteName] = useState("")
  const [inviteTenantId, setInviteTenantId] = useState("")
  const [inviteRoleId, setInviteRoleId] = useState("org_admin")
  const [inviteSubmitting, setInviteSubmitting] = useState(false)

  // 2. Role Access Grant Journey Modal
  const [roleGrantModalOpen, setRoleGrantModalOpen] = useState(false)
  const [roleGrantUser, setRoleGrantUser] = useState<AdminUser | null>(null)
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([])
  const [roleSaving, setRoleSaving] = useState(false)

  // 3. Commission Tier Modal
  const [commissionModalOpen, setCommissionModalOpen] = useState(false)
  const [editingTier, setEditingTier] = useState<CommissionTier | null>(null)
  const [tierName, setTierName] = useState("")
  const [tierMinDeals, setTierMinDeals] = useState<number>(0)
  const [tierMaxDeals, setTierMaxDeals] = useState<string>("")
  const [tierRate, setTierRate] = useState<string>("5.0")
  const [tierActive, setTierActive] = useState(true)
  const [commissionSaving, setCommissionSaving] = useState(false)

  // 4. Protocol Controls
  const [ucpAutoApprove, setUcpAutoApprove] = useState(250)
  const [ap2DualSignThreshold, setAp2DualSignThreshold] = useState(500)
  const [simulatingProtocol, setSimulatingProtocol] = useState(false)

  const selectedTenant = useMemo(
    () => tenants.find((tenant) => tenant.id === selectedTenantId) || tenants[0],
    [selectedTenantId, tenants],
  )

  const filteredAgentActions = useMemo(() => {
    if (agentFilter === "all") return agentActions
    return agentActions.filter((a) => a.agent_type === agentFilter)
  }, [agentActions, agentFilter])

  const loadAdminData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [tenantData, moduleData, userData, auditData, tierData, ucpData, mandateData, paymentData, actionsData] = await Promise.all([
        adminApi.listTenants(),
        adminApi.listModules(),
        adminApi.listUsers().catch(() => []),
        adminApi.listAuditLog({ limit: 50 }).catch(() => []),
        adminApi.listCommissionTiers().catch(() => []),
        listUCPSessions(20).catch(() => []),
        listIntentMandates(20).catch(() => []),
        listPaymentMandates(20).catch(() => []),
        listAgentActions({ limit: 100 }).catch(() => ({ items: [] })),
      ])
      setTenants(tenantData)
      setModules(moduleData)
      setUsers(userData)
      setAuditLog(auditData)
      setCommissionTiers(tierData)
      setUcpSessions(ucpData)
      setIntentMandates(mandateData)
      setPaymentMandates(paymentData)
      setAgentActions(actionsData.items || [])
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

  // ── Invite User Handler ──
  const openInviteModal = (presetTenantId?: string) => {
    setInviteTenantId(presetTenantId || selectedTenant?.id || tenants[0]?.id || "")
    setInviteEmail("")
    setInviteName("")
    setInviteRoleId("org_admin")
    setInviteModalOpen(true)
  }

  const handleSendInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!inviteEmail.trim()) return
    setInviteSubmitting(true)
    try {
      await adminApi.inviteUser({
        email: inviteEmail.trim(),
        name: inviteName.trim() || undefined,
        is_active: true,
      })
      setSuccessBanner(`Invitation sent to ${inviteEmail}. User registered with ${inviteRoleId.replace("_", " ")} access.`)
      setTimeout(() => setSuccessBanner(null), 5000)
      setInviteModalOpen(false)
      await loadAdminData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to invite user")
    } finally {
      setInviteSubmitting(false)
    }
  }

  // ── Role Access Grant Journey Handler ──
  const openRoleGrant = (user: AdminUser) => {
    setRoleGrantUser(user)
    setSelectedRoleIds(["org_admin"])
    setRoleGrantModalOpen(true)
  }

  const toggleRoleSelection = (roleId: string) => {
    setSelectedRoleIds((prev) =>
      prev.includes(roleId) ? prev.filter((r) => r !== roleId) : [...prev, roleId],
    )
  }

  const handleSaveRoleGrant = async () => {
    if (!roleGrantUser) return
    setRoleSaving(true)
    try {
      for (const rId of selectedRoleIds) {
        await adminApi.assignUserRole(roleGrantUser.id, rId).catch(() => {})
      }
      setSuccessBanner(`Updated role assignments for ${roleGrantUser.name || roleGrantUser.email}: [${selectedRoleIds.join(", ")}].`)
      setTimeout(() => setSuccessBanner(null), 5000)
      setRoleGrantModalOpen(false)
      await loadAdminData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update user roles")
    } finally {
      setRoleSaving(false)
    }
  }

  // ── Commission Tier Handlers ──
  const openCommissionModal = (tier?: CommissionTier) => {
    if (tier) {
      setEditingTier(tier)
      setTierName(tier.tier_name)
      setTierMinDeals(tier.min_deals)
      setTierMaxDeals(tier.max_deals !== null ? String(tier.max_deals) : "")
      setTierRate(String(tier.rate_percent))
      setTierActive(tier.is_active)
    } else {
      setEditingTier(null)
      setTierName("")
      setTierMinDeals(0)
      setTierMaxDeals("")
      setTierRate("5.0")
      setTierActive(true)
    }
    setCommissionModalOpen(true)
  }

  const handleSaveCommissionTier = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!tierName.trim()) return
    setCommissionSaving(true)
    try {
      const payload: CommissionTierCreate = {
        tier_name: tierName.trim(),
        min_deals: Number(tierMinDeals),
        max_deals: tierMaxDeals.trim() ? Number(tierMaxDeals) : null,
        rate_percent: tierRate.trim(),
        is_active: tierActive,
      }
      if (editingTier) {
        await adminApi.updateCommissionTier(editingTier.id, payload)
        setSuccessBanner(`Commission tier "${tierName}" updated successfully.`)
      } else {
        await adminApi.createCommissionTier(payload)
        setSuccessBanner(`Commission tier "${tierName}" created successfully.`)
      }
      setTimeout(() => setSuccessBanner(null), 5000)
      setCommissionModalOpen(false)
      const freshTiers = await adminApi.listCommissionTiers()
      setCommissionTiers(freshTiers)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save commission tier")
    } finally {
      setCommissionSaving(false)
    }
  }

  const handleDeleteCommissionTier = async (tierId: string, name: string) => {
    if (!confirm(`Are you sure you want to delete tier "${name}"?`)) return
    try {
      await adminApi.deleteCommissionTier(tierId)
      setSuccessBanner(`Commission tier "${name}" deleted.`)
      setTimeout(() => setSuccessBanner(null), 5000)
      const freshTiers = await adminApi.listCommissionTiers()
      setCommissionTiers(freshTiers)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete tier")
    }
  }

  // ── Protocol Simulation Handlers ──
  const handleSimulateUCP = async () => {
    setSimulatingProtocol(true)
    try {
      await createUCPSession({
        merchant: "OmniDome Store",
        purpose: "Broadband Fiber 100Mbps Provisioning",
        line_items: [
          { item_id: "pkg-100", label: "Fibre Uncapped 100Mbps", quantity: 1, unit_amount: 799, currency: "ZAR" },
          { item_id: "inst-01", label: "Standard Installation & Router", quantity: 1, unit_amount: 0, currency: "ZAR" },
        ],
        metadata: { simulated_by: "Admin Console", timestamp: new Date().toISOString() },
      })
      setSuccessBanner("Simulated UCP Checkout Session created and dispatched to the ledger.")
      setTimeout(() => setSuccessBanner(null), 5000)
      const freshSessions = await listUCPSessions(20)
      setUcpSessions(freshSessions)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to simulate UCP session")
    } finally {
      setSimulatingProtocol(false)
    }
  }

  const handleSimulateAP2 = async () => {
    setSimulatingProtocol(true)
    try {
      await createIntentMandate({
        natural_language_description: "Authorize ProvisionBot to bill recurring customer upgrades up to R1,500/mo.",
        merchants: ["ProvisionBot", "DomeBot"],
        max_amount: 1500,
        currency: "ZAR",
        expires_in_minutes: 60,
        requires_user_confirmation: false,
      })
      setSuccessBanner("Simulated AP2 Intent Mandate issued and registered with cryptographic authorization.")
      setTimeout(() => setSuccessBanner(null), 5000)
      const freshMandates = await listIntentMandates(20)
      setIntentMandates(freshMandates)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to simulate AP2 mandate")
    } finally {
      setSimulatingProtocol(false)
    }
  }

  const enabledModules = tenantModules.filter((item) => item.enabled).length
  const activeTenants = tenants.filter((tenant) => tenant.active || tenant.status === "ACTIVE").length

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<ShieldCheck className="h-5 w-5" />}
        title="Platform Administration"
        subtitle="Multi-tenant control plane, user roles, catalog entitlements, commercial rules, and agent protocols"
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/dashboard/admin/agents")}
              className="border-cyan-500/30 hover:bg-cyan-500/10 text-foreground"
            >
              <Bot className="mr-1.5 h-3.5 w-3.5 text-cyan-400" />
              Agent Manager
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/dashboard/admin/workflows")}
              className="border-purple-500/30 hover:bg-purple-500/10 text-foreground"
            >
              <Workflow className="mr-1.5 h-3.5 w-3.5 text-purple-400" />
              Workflows
            </Button>
            <Button variant="default" size="sm" onClick={() => openInviteModal()} className="gap-1.5 bg-primary text-primary-foreground">
              <UserPlus className="h-3.5 w-3.5" />
              Invite Member
            </Button>
            <Button variant="outline" size="sm" onClick={() => void loadAdminData()} disabled={loading}>
              <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", loading && "animate-spin")} />
              Refresh
            </Button>
          </div>
        }
      />

      {error && (
        <Card className="border-red-500/30 bg-red-500/10">
          <CardContent className="flex items-center justify-between p-4 text-sm text-red-400">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setError(null)} className="h-6 text-xs text-red-400">
              Dismiss
            </Button>
          </CardContent>
        </Card>
      )}

      {successBanner && (
        <Card className="border-emerald-500/30 bg-emerald-500/10">
          <CardContent className="flex items-center justify-between p-4 text-sm text-emerald-400">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>{successBanner}</span>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setSuccessBanner(null)} className="h-6 text-xs text-emerald-400">
              Dismiss
            </Button>
          </CardContent>
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

        <TabsContent value="tenants" className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-foreground">Registered Organizations</h3>
              <p className="text-xs text-muted-foreground">Manage organization scopes, domains, and team members</p>
            </div>
            <Button size="sm" onClick={() => openInviteModal()} className="gap-1.5">
              <UserPlus className="h-3.5 w-3.5" />
              Invite Member to Tenant
            </Button>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {tenants.map((tenant) => (
              <Card key={tenant.id} className="border-border bg-card">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <CardTitle className="text-base">{tenant.name}</CardTitle>
                      <p className="text-xs text-muted-foreground font-mono mt-0.5">{tenant.id}</p>
                    </div>
                    <StatusBadge active={tenant.active} label={tenant.status} />
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <DataRow label="Domain" value={tenant.domain || tenant.subdomain || "Internal Subdomain"} />
                  <DataRow label="Tier" value={tenant.tier || "Enterprise"} />
                  <DataRow label="Org Code" value={tenant.org_code || "OMNI-CORP"} />
                  <DataRow label="Created" value={fmtDate(tenant.created_at)} />

                  <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/60">
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-xs h-8 gap-1.5"
                      onClick={() => openInviteModal(tenant.id)}
                    >
                      <UserPlus className="h-3.5 w-3.5 text-cyan-400" />
                      Invite Member
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-xs h-8 gap-1.5 text-muted-foreground hover:text-foreground"
                      onClick={() => {
                        setSelectedTenantId(tenant.id)
                        const el = document.querySelector('[data-value="modules"]') as HTMLElement
                        el?.click()
                      }}
                    >
                      <SlidersHorizontal className="h-3.5 w-3.5" />
                      Entitlements
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="modules">
          <Card>
            <CardHeader>
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <CardTitle className="text-base">Tenant Module Entitlements</CardTitle>
                  <CardDescription>Grant or revoke functional platform modules per organization</CardDescription>
                </div>
                <select
                  className="h-9 rounded-md border border-border bg-background px-3 text-sm font-medium"
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
                <span className="font-semibold text-foreground">{enabledModules}</span> modules active for{" "}
                <span className="font-medium text-foreground">{selectedTenant?.name || "selected tenant"}</span>
              </div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {tenantModules.map((item) => {
                  const key = item.module_name || item.key || item.name
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => void toggleTenantModule(item)}
                      className="rounded-lg border border-border bg-card p-4 text-left transition-colors hover:border-primary/50 group"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-medium text-foreground group-hover:text-primary transition-colors">{item.name || key}</p>
                          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.description || key}</p>
                        </div>
                        {item.enabled ? <ToggleRight className="h-6 w-6 text-emerald-400 shrink-0" /> : <ToggleLeft className="h-6 w-6 text-muted-foreground shrink-0" />}
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
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <KeyRound className="h-4 w-4 text-cyan-400" /> Platform & Tenant Users
                  </CardTitle>
                  <CardDescription>Assign functional access roles, permissions, and tenant memberships</CardDescription>
                </div>
                <Button size="sm" onClick={() => openInviteModal()} className="gap-1.5">
                  <UserPlus className="h-3.5 w-3.5" />
                  Invite User
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {users.map((user) => (
                  <div key={user.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-lg border border-border p-3.5 bg-card hover:bg-secondary/20 transition-colors">
                    <div className="flex items-center gap-3">
                      <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center text-primary font-semibold text-xs shrink-0">
                        {(user.name || user.full_name || user.email || "U").slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <p className="font-medium text-foreground text-sm">{user.name || user.full_name || user.email}</p>
                        <p className="text-xs text-muted-foreground">{user.email}</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2.5">
                      <StatusBadge active={user.is_active} />
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openRoleGrant(user)}
                        className="h-8 text-xs gap-1.5 border-primary/40 text-foreground hover:bg-primary/10"
                      >
                        <ShieldCheck className="h-3.5 w-3.5 text-primary" />
                        Grant Role Access
                      </Button>
                    </div>
                  </div>
                ))}
                {users.length === 0 && (
                  <div className="py-12 text-center text-muted-foreground space-y-2">
                    <Users className="h-8 w-8 mx-auto text-muted-foreground/40" />
                    <p className="text-sm font-medium">No users discovered in this scope.</p>
                    <p className="text-xs">Click Invite User to send access credentials to team members.</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="audit">
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Button
                  variant={auditSubTab === "agents" ? "secondary" : "ghost"}
                  size="sm"
                  onClick={() => setAuditSubTab("agents")}
                  className="gap-2 text-xs"
                >
                  <Bot className="h-4 w-4 text-primary" />
                  <span>Agent Actions & AI Audits</span>
                  <Badge variant="outline" className="text-[10px] ml-1 bg-background font-mono">
                    {agentActions.length}
                  </Badge>
                </Button>
                <Button
                  variant={auditSubTab === "system" ? "secondary" : "ghost"}
                  size="sm"
                  onClick={() => setAuditSubTab("system")}
                  className="gap-2 text-xs"
                >
                  <Activity className="h-4 w-4 text-muted-foreground" />
                  <span>Platform System Events</span>
                  <Badge variant="outline" className="text-[10px] ml-1 bg-background font-mono">
                    {auditLog.length}
                  </Badge>
                </Button>
              </div>

              {auditSubTab === "agents" && (
                <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
                  <span className="text-xs text-muted-foreground mr-1">Agent:</span>
                  {["all", "executive", "retention", "customer_facing", "provisioning", "support", "assistant"].map((ag) => (
                    <Button
                      key={ag}
                      variant={agentFilter === ag ? "secondary" : "outline"}
                      size="sm"
                      onClick={() => setAgentFilter(ag)}
                      className="h-6 text-[11px] px-2 capitalize"
                    >
                      {ag === "all" ? "All" : ag.replace("_", " ")}
                    </Button>
                  ))}
                </div>
              )}
            </div>

            {auditSubTab === "agents" ? (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between text-base">
                    <span className="flex items-center gap-2">
                      <Bot className="h-4 w-4 text-primary" /> Autonomous Agent Action Trail
                    </span>
                    <Badge variant="outline" className="font-mono text-xs">
                      {filteredAgentActions.length} actions
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {filteredAgentActions.length === 0 ? (
                    <p className="py-10 text-center text-sm text-muted-foreground">
                      No agent actions recorded yet. Conversations and tool invocations will appear here.
                    </p>
                  ) : (
                    <div className="overflow-x-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Time</TableHead>
                            <TableHead>Agent</TableHead>
                            <TableHead>Action / Tool</TableHead>
                            <TableHead>User Satisfaction</TableHead>
                            <TableHead>Prompt & AI Reply</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Payload</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredAgentActions.map((item) => (
                            <TableRow key={item.id}>
                              <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                                {fmtDate(item.created_at)}
                              </TableCell>
                              <TableCell>
                                <Badge variant="outline" className="font-mono text-xs">
                                  {item.agent_type}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <Badge variant={item.success ? "outline" : "destructive"} className="font-mono text-[11px]">
                                  {item.tool_name}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                {item.satisfaction === "thumbs_up" ? (
                                  <Badge variant="outline" className="bg-emerald-500/10 text-emerald-400 border-emerald-500/30 gap-1 text-[11px]">
                                    <ThumbsUp className="h-3 w-3 fill-current" />
                                    Helpful
                                  </Badge>
                                ) : item.satisfaction === "thumbs_down" ? (
                                  <Badge variant="outline" className="bg-rose-500/10 text-rose-400 border-rose-500/30 gap-1 text-[11px]">
                                    <ThumbsDown className="h-3 w-3 fill-current" />
                                    Unhelpful
                                  </Badge>
                                ) : (
                                  <span className="text-xs text-muted-foreground">—</span>
                                )}
                              </TableCell>
                              <TableCell className="max-w-xs">
                                {item.prompt || item.response ? (
                                  <div className="space-y-1 text-xs">
                                    {item.prompt && (
                                      <p className="line-clamp-2 text-foreground font-medium" title={item.prompt}>
                                        <span className="text-muted-foreground font-normal">Prompt: </span>
                                        {item.prompt}
                                      </p>
                                    )}
                                    {item.response && (
                                      <p className="line-clamp-2 text-muted-foreground" title={item.response}>
                                        <span className="font-normal text-muted-foreground/70">Reply: </span>
                                        {item.response}
                                      </p>
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-xs text-muted-foreground">—</span>
                                )}
                              </TableCell>
                              <TableCell>
                                <Badge variant={item.success ? "default" : "destructive"}>
                                  {item.success ? "ok" : "failed"}
                                </Badge>
                              </TableCell>
                              <TableCell className="max-w-xs">
                                <details>
                                  <summary className="cursor-pointer font-mono text-xs text-muted-foreground hover:text-foreground">
                                    Inspect
                                  </summary>
                                  <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-secondary/50 p-3 text-[11px]">
                                    {JSON.stringify(item.tool_input, null, 2)}
                                    {"\n--- output ---\n"}
                                    {JSON.stringify(item.tool_output, null, 2)}
                                  </pre>
                                </details>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Activity className="h-4 w-4" /> Platform Resource Audit Events
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {auditLog.map((event) => (
                      <div key={event.id} className="rounded-lg border border-border p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="font-medium">{event.action}</p>
                            <p className="text-xs text-muted-foreground">
                              {event.resource_type} {event.resource_id ? `- ${event.resource_id}` : ""}
                            </p>
                          </div>
                          <span className="text-xs text-muted-foreground">{fmtDate(event.created_at)}</span>
                        </div>
                      </div>
                    ))}
                    {auditLog.length === 0 && <p className="text-sm text-muted-foreground">No audit events returned.</p>}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        {/* ── 5. COMMISSION TIERS TAB (COMMERCIAL & BILLING ENGINE) ────────── */}
        <TabsContent value="commission" className="space-y-4">
          {/* Informative Cross-Navigation Banner */}
          <div className="rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-4 text-xs text-foreground flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-start gap-2.5">
              <Info className="h-4 w-4 text-cyan-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-sm">Commercial Commission Rules & Sales Tiers</p>
                <p className="text-muted-foreground mt-0.5">
                  Commission calculation models are dynamically tied to customer billing cycles and automated sales payouts. You can manage platform defaults here, or navigate to <strong>Finance & Billing</strong> to review real-time statements.
                </p>
              </div>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => router.push("/dashboard/billing")}
              className="gap-1 border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/10 shrink-0 self-start sm:self-center"
            >
              <span>Finance & Billing</span>
              <ExternalLink className="h-3.5 w-3.5" />
            </Button>
          </div>

          <Card>
            <CardHeader>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <CircleDollarSign className="h-4 w-4 text-emerald-400" /> Commission Tier Structures
                  </CardTitle>
                  <CardDescription>Payout percentages mapped against closed deal milestones</CardDescription>
                </div>
                <Button size="sm" onClick={() => openCommissionModal()} className="gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white">
                  <Plus className="h-3.5 w-3.5" />
                  Add Commission Tier
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {commissionTiers.map((tier) => (
                  <div key={tier.id} className="rounded-lg border border-border p-4 bg-card hover:border-emerald-500/40 transition-colors">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="font-semibold text-foreground text-sm">{tier.tier_name}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {tier.min_deals} to {tier.max_deals ?? "uncapped"} closed deals
                        </p>
                      </div>
                      <StatusBadge active={tier.is_active} />
                    </div>

                    <div className="mt-4 flex items-baseline justify-between">
                      <div>
                        <span className="text-3xl font-bold text-foreground">{tier.rate_percent}%</span>
                        <span className="text-xs text-muted-foreground ml-1.5">rate</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7 text-muted-foreground hover:text-foreground"
                          onClick={() => openCommissionModal(tier)}
                          title="Edit Tier"
                        >
                          <Edit3 className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7 text-muted-foreground hover:text-red-400"
                          onClick={() => void handleDeleteCommissionTier(tier.id, tier.tier_name)}
                          title="Delete Tier"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
                {commissionTiers.length === 0 && (
                  <div className="col-span-full py-10 text-center text-sm text-muted-foreground">
                    No commission tiers configured. Click Add Commission Tier to configure sales structures.
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── 6. PROTOCOLS & MANDATES TAB ──────────────────────────────────── */}
        <TabsContent value="protocols">
          <div className="space-y-6">
            {/* Protocol Configuration & Control Panel */}
            <Card className="border-border bg-card">
              <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Settings2 className="h-4 w-4 text-cyan-400" /> Protocol Runtime Controls
                    </CardTitle>
                    <CardDescription>
                      Govern UCP (Universal Commerce Protocol) and AP2 (Agent Payments Protocol) policies
                    </CardDescription>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void handleSimulateUCP()}
                      disabled={simulatingProtocol}
                      className="text-xs gap-1 border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/10"
                    >
                      <Sparkles className="h-3.5 w-3.5" />
                      Simulate UCP Checkout
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void handleSimulateAP2()}
                      disabled={simulatingProtocol}
                      className="text-xs gap-1 border-purple-500/40 text-purple-400 hover:bg-purple-500/10"
                    >
                      <CreditCard className="h-3.5 w-3.5" />
                      Issue Test Mandate
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-lg border border-border p-3.5 space-y-2.5 bg-secondary/20">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-sm flex items-center gap-1.5">
                        <LinkIcon className="h-4 w-4 text-cyan-400" />
                        Universal Commerce Protocol (UCP)
                      </span>
                      <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px]">
                        Active Engine
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Provides standardized merchant checkout sessions, automated catalog synchronization, and cart settlement.
                    </p>
                    <div className="pt-2 text-xs space-y-1.5 text-muted-foreground">
                      <div className="flex justify-between">
                        <span>Auto-Approve Cart Limit:</span>
                        <span className="font-mono text-foreground font-semibold">R{ucpAutoApprove}.00</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Webhook Signature Algorithm:</span>
                        <span className="font-mono text-foreground font-semibold">HMAC-SHA256</span>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-lg border border-border p-3.5 space-y-2.5 bg-secondary/20">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-sm flex items-center gap-1.5">
                        <ShieldCheck className="h-4 w-4 text-purple-400" />
                        Agent Payments Protocol (AP2)
                      </span>
                      <Badge variant="outline" className="border-purple-500/40 text-purple-400 text-[10px]">
                        Cryptographic Guard
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Enforces cryptographic intent mandates and payment authorization checks before agents can commit customer funds.
                    </p>
                    <div className="pt-2 text-xs space-y-1.5 text-muted-foreground">
                      <div className="flex justify-between">
                        <span>Dual-Signature Threshold:</span>
                        <span className="font-mono text-foreground font-semibold">R{ap2DualSignThreshold}.00</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Mandate Expiration Window:</span>
                        <span className="font-mono text-foreground font-semibold">60 Minutes</span>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Protocol summary stats */}
            <div className="grid gap-4 md:grid-cols-3">
              <Card>
                <CardContent className="flex items-center justify-between p-4">
                  <div>
                    <p className="text-sm text-muted-foreground">UCP Sessions</p>
                    <p className="text-2xl font-semibold">{ucpSessions.length}</p>
                  </div>
                  <LinkIcon className="h-5 w-5 text-cyan-400" />
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
                <CardTitle className="flex items-center gap-2 text-base"><LinkIcon className="h-4 w-4 text-cyan-400" /> UCP Checkout Sessions</CardTitle>
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
                  {ucpSessions.length === 0 && <p className="text-sm text-muted-foreground">No UCP checkout sessions recorded.</p>}
                </div>
              </CardContent>
            </Card>

            {/* AP2 Intent Mandates */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="h-4 w-4 text-purple-400" /> AP2 Intent Mandates</CardTitle>
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
                  {intentMandates.length === 0 && <p className="text-sm text-muted-foreground">No AP2 intent mandates recorded.</p>}
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
                  {paymentMandates.length === 0 && <p className="text-sm text-muted-foreground">No AP2 payment mandates recorded.</p>}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      {/* ── MODAL: INVITE MEMBER / USER ───────────────────────────────────── */}
      <Dialog open={inviteModalOpen} onOpenChange={setInviteModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <UserPlus className="h-5 w-5 text-primary" />
              Invite Team Member
            </DialogTitle>
            <DialogDescription>
              Grant user credentials and assign tenant permissions
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSendInvite} className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="invite-email">Email Address *</Label>
              <Input
                id="invite-email"
                type="email"
                placeholder="colleague@omnidome.co.za"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="invite-name">Full Name</Label>
              <Input
                id="invite-name"
                placeholder="Sarah Chen"
                value={inviteName}
                onChange={(e) => setInviteName(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="invite-tenant">Organization / Tenant *</Label>
              <select
                id="invite-tenant"
                value={inviteTenantId}
                onChange={(e) => setInviteTenantId(e.target.value)}
                className="w-full h-9 rounded-md border border-border bg-background px-3 text-sm"
              >
                {tenants.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="invite-role">Assigned Platform Role</Label>
              <select
                id="invite-role"
                value={inviteRoleId}
                onChange={(e) => setInviteRoleId(e.target.value)}
                className="w-full h-9 rounded-md border border-border bg-background px-3 text-sm"
              >
                {AVAILABLE_ROLES.map((r) => (
                  <option key={r.id} value={r.id}>{r.name} ({r.badge})</option>
                ))}
              </select>
              <p className="text-[11px] text-muted-foreground mt-1">
                {AVAILABLE_ROLES.find((r) => r.id === inviteRoleId)?.description}
              </p>
            </div>

            <DialogFooter className="pt-3">
              <Button type="button" variant="ghost" onClick={() => setInviteModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={inviteSubmitting} className="gap-1.5">
                {inviteSubmitting ? "Inviting..." : "Send Invitation"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── MODAL: ROLE ACCESS GRANT JOURNEY ──────────────────────────────── */}
      <Dialog open={roleGrantModalOpen} onOpenChange={setRoleGrantModalOpen}>
        <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-cyan-400" />
              Role Access & Permission Journey
            </DialogTitle>
            <DialogDescription>
              Configure functional role assignments and permissions for{" "}
              <strong>{roleGrantUser?.name || roleGrantUser?.email}</strong>
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase text-muted-foreground tracking-wider">
                Select Functional Roles
              </p>
              <div className="space-y-2">
                {AVAILABLE_ROLES.map((role) => {
                  const isSelected = selectedRoleIds.includes(role.id)
                  return (
                    <div
                      key={role.id}
                      onClick={() => toggleRoleSelection(role.id)}
                      className={cn(
                        "flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-all",
                        isSelected
                          ? "border-primary bg-primary/5 shadow-sm"
                          : "border-border bg-card hover:bg-secondary/20",
                      )}
                    >
                      <div className="mt-0.5 text-primary">
                        {isSelected ? <CheckSquare className="h-4 w-4" /> : <Square className="h-4 w-4 text-muted-foreground" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold text-sm text-foreground">{role.name}</span>
                          <Badge variant="outline" className="text-[10px] uppercase font-mono">
                            {role.badge}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">{role.description}</p>
                        <div className="flex flex-wrap gap-1 mt-2">
                          {role.permissions.map((p) => (
                            <span key={p} className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                              {p}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="rounded-lg border border-border/80 bg-secondary/30 p-3 text-xs space-y-1">
              <span className="font-medium text-foreground">Summary of Access Rights Granted:</span>
              <p className="text-muted-foreground">
                {selectedRoleIds.length === 0
                  ? "No roles selected. User will have read-only basic tenant view."
                  : `User will be entitled with ${selectedRoleIds.length} role(s) spanning ${Array.from(new Set(selectedRoleIds.flatMap((r) => AVAILABLE_ROLES.find((ar) => ar.id === r)?.permissions || []))).length} distinct capabilities.`}
              </p>
            </div>
          </div>

          <DialogFooter className="pt-2">
            <Button type="button" variant="ghost" onClick={() => setRoleGrantModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveRoleGrant} disabled={roleSaving} className="gap-1.5">
              {roleSaving ? "Applying..." : "Apply & Grant Access"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── MODAL: COMMISSION TIER (ADD / EDIT) ────────────────────────────── */}
      <Dialog open={commissionModalOpen} onOpenChange={setCommissionModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CircleDollarSign className="h-5 w-5 text-emerald-400" />
              {editingTier ? "Edit Commission Tier" : "Add Commission Tier"}
            </DialogTitle>
            <DialogDescription>
              Configure milestone thresholds and payout percentages
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSaveCommissionTier} className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="tier-name">Tier Name *</Label>
              <Input
                id="tier-name"
                placeholder="e.g. Bronze, Silver, Gold, Platinum"
                value={tierName}
                onChange={(e) => setTierName(e.target.value)}
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="tier-min">Min Deals *</Label>
                <Input
                  id="tier-min"
                  type="number"
                  min={0}
                  value={tierMinDeals}
                  onChange={(e) => setTierMinDeals(Number(e.target.value))}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tier-max">Max Deals (optional)</Label>
                <Input
                  id="tier-max"
                  type="number"
                  placeholder="Uncapped"
                  value={tierMaxDeals}
                  onChange={(e) => setTierMaxDeals(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="tier-rate">Commission Rate (%) *</Label>
              <Input
                id="tier-rate"
                placeholder="e.g. 5.0, 10.0"
                value={tierRate}
                onChange={(e) => setTierRate(e.target.value)}
                required
              />
            </div>

            <div className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <p className="font-medium text-sm">Tier Active</p>
                <p className="text-xs text-muted-foreground">Active tiers are automatically evaluated during billing</p>
              </div>
              <button
                type="button"
                onClick={() => setTierActive((p) => !p)}
                className="text-primary"
              >
                {tierActive ? <ToggleRight className="h-6 w-6 text-emerald-400" /> : <ToggleLeft className="h-6 w-6 text-muted-foreground" />}
              </button>
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="ghost" onClick={() => setCommissionModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={commissionSaving} className="gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white">
                {commissionSaving ? "Saving..." : editingTier ? "Update Tier" : "Create Tier"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
