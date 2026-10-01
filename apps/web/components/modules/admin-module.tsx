"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
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
  ThumbsUp,
  ThumbsDown,
  UserPlus,
  Plus,
  Trash2,
  Edit3,
  ExternalLink,
  Settings2,
  CheckSquare,
  Square,
  AlertCircle,
  Info,
  Lock,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { PageHeader } from "@/components/ui/page-header"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { NotConnected, StatValue } from "@/components/ui/not-connected"
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
  type UCPCheckoutSession,
  type IntentMandate,
  type PaymentMandate,
  type AgentActionAuditItem,
} from "@/lib/orchestrator-api"
import {
  adminApi,
  adminErrorMessage,
  invalidateAdminCache,
  type AdminRole,
  type AdminUser,
  type AuditLogEntry,
  type CommissionTier,
  type CommissionTierCreate,
  type ModuleCatalogItem,
  type SeatUsage,
  type PlatformSeatRow,
  type Tenant,
  type Whoami,
} from "@/lib/admin-api"
import {
  adminVisibility,
  canRequestSection,
  deniedState,
  isSystemRole,
  loadableFromError,
  readyData,
  requiredRoleLabel,
  validateTier,
  type AdminSection,
} from "@/lib/admin-state"
import type { Loadable } from "@/lib/service-state"
import { CreateTenantCard, SeatsBillingTab, TeamTab, TenantSeatControls } from "@/components/modules/admin-team"
import { cn } from "@/lib/utils"

const LOADING: Loadable<never> = { state: "loading" }

const fmtDate = (value?: string) => {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "-"
  return date.toLocaleString()
}

/** Run `fn` and store the outcome as a Loadable. Never swallows: failures become a real state. */
async function runInto<T>(setter: (l: Loadable<T>) => void, fn: () => Promise<T>): Promise<void> {
  try {
    setter({ state: "ready", data: await fn() })
  } catch (e) {
    setter(loadableFromError<T>(e, adminErrorMessage))
  }
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

/** Non-ready section state: loading skeleton, Service not running, Error + Retry, Not permitted (naming the role). */
function SectionState({
  state,
  service,
  section,
  onRetry,
}: {
  state: Loadable<unknown>
  service: string
  section: AdminSection
  onRetry?: () => void
}) {
  if (state.state === "ready") return null
  return (
    <div className="space-y-1.5">
      <NotConnected loadable={state} service={service} onRetry={state.state === "denied" ? undefined : onRetry} />
      {state.state === "denied" && (
        <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
          <Lock className="h-3 w-3" /> Requires the {requiredRoleLabel(section)} role.
        </p>
      )}
    </div>
  )
}

/** Small confirm dialog for destructive actions. */
function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  open: boolean
  title: string
  description: string
  confirmLabel: string
  busy: boolean
  error?: string | null
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {error && (
          <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
            {error}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={busy}>
            {busy ? "Working..." : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const LAZY_SECTIONS = { audit: "audit", commission: "commission", protocols: "protocols", users: "users" } as const

export function AdminModule() {
  const router = useRouter()

  // Identity (one /api/whoami per mount; roles decide what is requested at all)
  const [identity, setIdentity] = useState<Whoami | null>(null)
  const [identityState, setIdentityState] = useState<Loadable<Whoami>>(LOADING)

  // Per-section request state. `loading` -> `ready | unreachable | denied | error`; never an empty fallback.
  const [tenants, setTenants] = useState<Loadable<Tenant[]>>(LOADING)
  const [catalog, setCatalog] = useState<Loadable<ModuleCatalogItem[]>>(LOADING)
  const [tenantModules, setTenantModules] = useState<Loadable<ModuleCatalogItem[]>>(LOADING)
  const [seatRows, setSeatRows] = useState<Loadable<PlatformSeatRow[]>>(LOADING)
  const [ownSeats, setOwnSeats] = useState<Loadable<SeatUsage>>(LOADING)
  const [users, setUsers] = useState<Loadable<AdminUser[]>>(LOADING)
  const [auditLog, setAuditLog] = useState<Loadable<AuditLogEntry[]>>(LOADING)
  const [tiers, setTiers] = useState<Loadable<CommissionTier[]>>(LOADING)
  const [ucpSessions, setUcpSessions] = useState<Loadable<UCPCheckoutSession[]>>(LOADING)
  const [intentMandates, setIntentMandates] = useState<Loadable<IntentMandate[]>>(LOADING)
  const [paymentMandates, setPaymentMandates] = useState<Loadable<PaymentMandate[]>>(LOADING)
  const [agentActions, setAgentActions] = useState<Loadable<AgentActionAuditItem[]>>(LOADING)

  const [selectedTenantId, setSelectedTenantId] = useState<string>("")
  const [error, setError] = useState<string | null>(null)
  const [successBanner, setSuccessBanner] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<string | null>(null)
  const [teamFocusTenant, setTeamFocusTenant] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [moduleBusy, setModuleBusy] = useState<string | null>(null)

  const [auditSubTab, setAuditSubTab] = useState<"agents" | "system">("agents")
  const [agentFilter, setAgentFilter] = useState<string>("all")

  // Role grant dialog (real roles from GET /roles; ids are the server's)
  const [roleGrantOpen, setRoleGrantOpen] = useState(false)
  const [roleGrantUser, setRoleGrantUser] = useState<AdminUser | null>(null)
  const [roleOptions, setRoleOptions] = useState<Loadable<AdminRole[]>>(LOADING)
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([])
  const [roleSaving, setRoleSaving] = useState(false)
  const [roleErr, setRoleErr] = useState<string | null>(null)

  // Commission tier dialog + delete confirm
  const [commissionOpen, setCommissionOpen] = useState(false)
  const [editingTier, setEditingTier] = useState<CommissionTier | null>(null)
  const [tierName, setTierName] = useState("")
  const [tierMinDeals, setTierMinDeals] = useState<string>("0")
  const [tierMaxDeals, setTierMaxDeals] = useState<string>("")
  const [tierRate, setTierRate] = useState<string>("")
  const [tierActive, setTierActive] = useState(true)
  const [commissionSaving, setCommissionSaving] = useState(false)
  const [tierErr, setTierErr] = useState<string | null>(null)
  const [deleteTier, setDeleteTier] = useState<CommissionTier | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteErr, setDeleteErr] = useState<string | null>(null)

  // Refs: the initial load runs once; tenant switches only reload tenant-scoped data.
  const booted = useRef(false)
  const identityRef = useRef<Whoami | null>(null)
  const selectedTenantRef = useRef("")
  const tenantSeq = useRef(0)
  const loadedSections = useRef<Set<string>>(new Set())

  const tenantList = readyData(tenants)
  const selectedTenant = useMemo(
    () => tenantList.find((tenant) => tenant.id === selectedTenantId) || tenantList[0],
    [selectedTenantId, tenantList],
  )

  // UI gating only; services/admin enforces every action. Roles come from the verified edge identity.
  const vis = adminVisibility(identity?.roles)
  const isPlatformAdmin = vis.platform
  const canManageTeam = vis.tenantAdmin
  const currentTab = activeTab ?? (isPlatformAdmin ? "tenants" : canManageTeam ? "team" : "modules")

  const filteredAgentActions = useMemo(() => {
    const items = readyData(agentActions)
    if (agentFilter === "all") return items
    return items.filter((a) => a.agent_type === agentFilter)
  }, [agentActions, agentFilter])

  const loadTenantModules = useCallback(async (tenantId: string) => {
    const seq = ++tenantSeq.current
    if (!tenantId) {
      setTenantModules({ state: "ready", data: [] })
      return
    }
    setTenantModules(LOADING)
    let next: Loadable<ModuleCatalogItem[]>
    try {
      next = { state: "ready", data: await adminApi.listTenantModules(tenantId) }
    } catch (e) {
      next = loadableFromError<ModuleCatalogItem[]>(e, adminErrorMessage)
    }
    if (seq === tenantSeq.current) setTenantModules(next)
  }, [])

  /** (Re)load one lazily-fetched section. Not requested at all when the role cannot read it. */
  const loadSection = useCallback((section: keyof typeof LAZY_SECTIONS): Promise<unknown> => {
    const roles = identityRef.current?.roles
    if (!canRequestSection(roles, section)) {
      const d = deniedState()
      if (section === "users") setUsers(d)
      if (section === "audit") {
        setAuditLog(d)
        setAgentActions(d)
      }
      if (section === "commission") setTiers(d)
      if (section === "protocols") {
        setUcpSessions(d)
        setIntentMandates(d)
        setPaymentMandates(d)
      }
      return Promise.resolve()
    }
    switch (section) {
      case "users":
        setUsers(LOADING)
        return runInto(setUsers, () => adminApi.listUsers())
      case "audit":
        setAuditLog(LOADING)
        setAgentActions(LOADING)
        return Promise.all([
          runInto(setAuditLog, () => adminApi.listAuditLog({ limit: 50 })),
          runInto(setAgentActions, async () => (await listAgentActions({ limit: 100 })).items ?? []),
        ])
      case "commission":
        setTiers(LOADING)
        return runInto(setTiers, () => adminApi.listCommissionTiers())
      case "protocols":
        setUcpSessions(LOADING)
        setIntentMandates(LOADING)
        setPaymentMandates(LOADING)
        return Promise.all([
          runInto(setUcpSessions, () => listUCPSessions(20)),
          runInto(setIntentMandates, () => listIntentMandates(20)),
          runInto(setPaymentMandates, () => listPaymentMandates(20)),
        ])
    }
  }, [])

  const retrySection = useCallback(
    (section: keyof typeof LAZY_SECTIONS) => {
      invalidateAdminCache()
      void loadSection(section)
    },
    [loadSection],
  )

  /**
   * Identity first, then only what this role may read. Platform-only lists are never requested for tenant
   * admins; users load eagerly (KPI), audit/commission/protocols load when their tab is first opened.
   */
  const bootstrap = useCallback(async () => {
    invalidateAdminCache()
    loadedSections.current.clear()
    setIdentityState(LOADING)
    let who: Whoami
    try {
      who = await adminApi.whoami()
    } catch (e) {
      setIdentityState(loadableFromError<Whoami>(e, adminErrorMessage))
      return
    }
    identityRef.current = who
    setIdentity(who)
    setIdentityState({ state: "ready", data: who })

    const v = adminVisibility(who.roles)
    const own = who.tenant_id || ""
    const jobs: Promise<unknown>[] = []

    if (v.platform) {
      setOwnSeats(deniedState())
      jobs.push(
        (async () => {
          try {
            const list = await adminApi.listTenants()
            setTenants({ state: "ready", data: list })
            const keep = selectedTenantRef.current && list.some((t) => t.id === selectedTenantRef.current)
            const id = keep ? selectedTenantRef.current : list[0]?.id || ""
            selectedTenantRef.current = id
            setSelectedTenantId(id)
            await loadTenantModules(id)
          } catch (e) {
            const l = loadableFromError<Tenant[]>(e, adminErrorMessage)
            setTenants(l)
            setTenantModules(l as Loadable<ModuleCatalogItem[]>)
          }
        })(),
        runInto(setCatalog, () => adminApi.listModules()),
        runInto(setSeatRows, async () => (await adminApi.platformSeatUsage()).tenants ?? []),
      )
    } else {
      setCatalog(deniedState())
      setSeatRows(deniedState())
      selectedTenantRef.current = own
      setSelectedTenantId(own)
      if (v.tenantAdmin && own) {
        jobs.push(
          runInto(setTenants, async () => [await adminApi.getTenant(own)]),
          runInto(setOwnSeats, () => adminApi.getSeats(own)),
        )
      } else {
        setTenants(deniedState())
        setOwnSeats(deniedState())
      }
      jobs.push(loadTenantModules(own))
    }

    if (v.tenantAdmin) {
      loadedSections.current.add("users")
      jobs.push(loadSection("users"))
    } else {
      setUsers(deniedState())
    }
    await Promise.all(jobs)
  }, [loadTenantModules, loadSection])

  // Exactly one initial load (ref guard survives StrictMode's double effect).
  useEffect(() => {
    if (booted.current) return
    booted.current = true
    void bootstrap()
  }, [bootstrap])

  // Lazy tabs: fetched the first time they are shown (and never for roles that cannot read them).
  useEffect(() => {
    if (!identity) return
    if (currentTab === "audit" || currentTab === "commission" || currentTab === "protocols") {
      if (loadedSections.current.has(currentTab)) return
      loadedSections.current.add(currentTab)
      void loadSection(currentTab)
    }
  }, [currentTab, identity, loadSection])

  const refreshAll = async () => {
    setRefreshing(true)
    setError(null)
    try {
      await bootstrap()
      // Lazy sections already shown reload too.
      const shown = ["audit", "commission", "protocols"].filter((s) => s === currentTab)
      await Promise.all(shown.map((s) => (loadedSections.current.add(s), loadSection(s as keyof typeof LAZY_SECTIONS))))
    } finally {
      setRefreshing(false)
    }
  }

  const selectTenant = (tenantId: string) => {
    selectedTenantRef.current = tenantId
    setSelectedTenantId(tenantId)
    void loadTenantModules(tenantId)
  }

  const flash = (message: string) => {
    setSuccessBanner(message)
    setTimeout(() => setSuccessBanner(null), 5000)
  }

  const toggleTenantModule = async (moduleItem: ModuleCatalogItem) => {
    if (!selectedTenant || !isPlatformAdmin || moduleBusy) return // entitlements are platform-admin only
    const moduleName = moduleItem.module_name || moduleItem.key || moduleItem.name
    setModuleBusy(moduleName)
    setError(null)
    try {
      await adminApi.updateTenantModules(selectedTenant.id, [
        { name: moduleName, enabled: !moduleItem.enabled, config: moduleItem.config },
      ])
      await loadTenantModules(selectedTenant.id)
    } catch (e) {
      setError(adminErrorMessage(e))
    } finally {
      setModuleBusy(null)
    }
  }

  /** Invitations go through Team -> Invite (seat-aware, role-ranked, hashed token); the direct create-user path is gone. */
  const goInvite = (tenantId?: string) => {
    setTeamFocusTenant(tenantId ?? null)
    setActiveTab("team")
  }

  // ── Role grant ──
  const openRoleGrant = (user: AdminUser) => {
    setRoleGrantUser(user)
    setSelectedRoleIds([])
    setRoleErr(null)
    setRoleGrantOpen(true)
    setRoleOptions(LOADING)
    void runInto(setRoleOptions, () => adminApi.listRoles())
  }

  const toggleRoleSelection = (roleId: string) => {
    setSelectedRoleIds((prev) => (prev.includes(roleId) ? prev.filter((r) => r !== roleId) : [...prev, roleId]))
  }

  const handleSaveRoleGrant = async () => {
    if (!roleGrantUser || roleSaving || selectedRoleIds.length === 0) return
    setRoleSaving(true)
    setRoleErr(null)
    const roles = readyData(roleOptions)
    const failures: string[] = []
    const granted: string[] = []
    for (const rId of selectedRoleIds) {
      const name = roles.find((r) => r.id === rId)?.name ?? rId
      try {
        await adminApi.assignUserRole(roleGrantUser.id, rId)
        granted.push(name)
      } catch (e) {
        failures.push(`${name}: ${adminErrorMessage(e)}`)
      }
    }
    setRoleSaving(false)
    if (failures.length) {
      setRoleErr(failures.join(" | "))
      setSelectedRoleIds((prev) => prev.filter((id) => !granted.includes(roles.find((r) => r.id === id)?.name ?? id)))
      if (granted.length) flash(`Granted ${granted.join(", ")} to ${roleGrantUser.name || roleGrantUser.email}. Some roles failed, see the dialog.`)
      return
    }
    flash(`Granted ${granted.join(", ")} to ${roleGrantUser.name || roleGrantUser.email}.`)
    setRoleGrantOpen(false)
  }

  // ── Commission tiers ──
  const openCommissionModal = (tier?: CommissionTier) => {
    setTierErr(null)
    if (tier) {
      setEditingTier(tier)
      setTierName(tier.tier_name)
      setTierMinDeals(String(tier.min_deals))
      setTierMaxDeals(tier.max_deals !== null ? String(tier.max_deals) : "")
      setTierRate(String(tier.rate_percent))
      setTierActive(tier.is_active)
    } else {
      setEditingTier(null)
      setTierName("")
      setTierMinDeals("0")
      setTierMaxDeals("")
      setTierRate("")
      setTierActive(true)
    }
    setCommissionOpen(true)
  }

  const refreshTiers = () => runInto(setTiers, () => adminApi.listCommissionTiers())

  const handleSaveCommissionTier = async (e: React.FormEvent) => {
    e.preventDefault()
    if (commissionSaving) return
    const invalid = validateTier({ name: tierName, minDeals: tierMinDeals, maxDeals: tierMaxDeals, rate: tierRate })
    if (invalid) {
      setTierErr(invalid)
      return
    }
    setCommissionSaving(true)
    setTierErr(null)
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
        flash(`Commission tier "${tierName.trim()}" updated.`)
      } else {
        await adminApi.createCommissionTier(payload)
        flash(`Commission tier "${tierName.trim()}" created.`)
      }
      setCommissionOpen(false)
      await refreshTiers()
    } catch (err) {
      setTierErr(adminErrorMessage(err))
    } finally {
      setCommissionSaving(false)
    }
  }

  const handleDeleteCommissionTier = async () => {
    if (!deleteTier || deleteBusy) return
    setDeleteBusy(true)
    setDeleteErr(null)
    try {
      await adminApi.deleteCommissionTier(deleteTier.id)
      flash(`Commission tier "${deleteTier.tier_name}" deleted.`)
      setDeleteTier(null)
      await refreshTiers()
    } catch (err) {
      setDeleteErr(adminErrorMessage(err))
    } finally {
      setDeleteBusy(false)
    }
  }

  const modulesList = readyData(tenantModules)
  const enabledModules = modulesList.filter((item) => item.enabled).length
  const activeTenants = tenantList.filter((tenant) => tenant.active || tenant.status === "ACTIVE").length

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
            {canManageTeam && (
              <Button variant="default" size="sm" onClick={() => goInvite()} className="gap-1.5 bg-primary text-primary-foreground">
                <UserPlus className="h-3.5 w-3.5" />
                Invite Member
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={() => void refreshAll()} disabled={refreshing || identityState.state === "loading"}>
              <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", (refreshing || identityState.state === "loading") && "animate-spin")} />
              Refresh
            </Button>
          </div>
        }
      />

      {error && (
        <Card role="alert" className="border-red-500/30 bg-red-500/10">
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
        <Card role="status" className="border-emerald-500/30 bg-emerald-500/10">
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

      {identityState.state !== "ready" ? (
        <NotConnected loadable={identityState} service="Admin" onRetry={() => void bootstrap()} />
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {isPlatformAdmin ? (
              <>
                <Card>
                  <CardContent className="flex items-center justify-between p-4">
                    <div>
                      <p className="text-sm text-muted-foreground">Tenants</p>
                      <p className="text-2xl font-semibold">
                        <StatValue loadable={tenants}>{(d) => d.length}</StatValue>
                      </p>
                    </div>
                    <Building2 className="h-5 w-5 text-cyan-400" />
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="flex items-center justify-between p-4">
                    <div>
                      <p className="text-sm text-muted-foreground">Active Tenants</p>
                      <p className="text-2xl font-semibold">
                        <StatValue loadable={tenants}>{() => activeTenants}</StatValue>
                      </p>
                    </div>
                    <ShieldCheck className="h-5 w-5 text-emerald-400" />
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="flex items-center justify-between p-4">
                    <div>
                      <p className="text-sm text-muted-foreground">Catalog Modules</p>
                      <p className="text-2xl font-semibold">
                        <StatValue loadable={catalog}>{(d) => d.length}</StatValue>
                      </p>
                    </div>
                    <SlidersHorizontal className="h-5 w-5 text-amber-400" />
                  </CardContent>
                </Card>
              </>
            ) : (
              <>
                <Card>
                  <CardContent className="flex items-center justify-between p-4">
                    <div>
                      <p className="text-sm text-muted-foreground">Modules Enabled</p>
                      <p className="text-2xl font-semibold">
                        <StatValue loadable={tenantModules}>{() => enabledModules}</StatValue>
                      </p>
                    </div>
                    <SlidersHorizontal className="h-5 w-5 text-amber-400" />
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="flex items-center justify-between p-4">
                    <div>
                      <p className="text-sm text-muted-foreground">Modules Available</p>
                      <p className="text-2xl font-semibold">
                        <StatValue loadable={tenantModules}>{(d) => d.length}</StatValue>
                      </p>
                    </div>
                    <Building2 className="h-5 w-5 text-cyan-400" />
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="flex items-center justify-between p-4">
                    <div>
                      <p className="text-sm text-muted-foreground">Seats Used</p>
                      <p className="text-2xl font-semibold">
                        <StatValue loadable={ownSeats}>{(s) => `${s.seats_used} / ${s.seat_limit ?? "unlimited"}`}</StatValue>
                      </p>
                    </div>
                    <ShieldCheck className="h-5 w-5 text-emerald-400" />
                  </CardContent>
                </Card>
              </>
            )}
            <Card>
              <CardContent className="flex items-center justify-between p-4">
                <div>
                  <p className="text-sm text-muted-foreground">Users</p>
                  <p className="text-2xl font-semibold">
                    <StatValue loadable={users}>{(d) => d.length}</StatValue>
                  </p>
                </div>
                <Users className="h-5 w-5 text-violet-400" />
              </CardContent>
            </Card>
          </div>

          <Tabs value={currentTab} onValueChange={setActiveTab} className="space-y-4">
            <TabsList className="flex w-full justify-start overflow-x-auto" aria-label="Administration sections">
              {isPlatformAdmin && <TabsTrigger value="tenants">Tenants</TabsTrigger>}
              {canManageTeam && <TabsTrigger value="team">Team</TabsTrigger>}
              {isPlatformAdmin && <TabsTrigger value="seats">Seats &amp; Billing</TabsTrigger>}
              <TabsTrigger value="modules">Modules</TabsTrigger>
              <TabsTrigger value="users">Users</TabsTrigger>
              <TabsTrigger value="audit">Audit</TabsTrigger>
              <TabsTrigger value="commission">Commission</TabsTrigger>
              <TabsTrigger value="protocols">Protocols</TabsTrigger>
            </TabsList>

            {canManageTeam && (
              <TabsContent value="team" className="space-y-4">
                <TeamTab identity={identity} tenants={tenantList} focusTenantId={teamFocusTenant} />
              </TabsContent>
            )}

            {isPlatformAdmin && (
              <TabsContent value="seats" className="space-y-4">
                <SeatsBillingTab tenants={tenantList} />
              </TabsContent>
            )}

            {isPlatformAdmin && (
              <TabsContent value="tenants" className="space-y-4">
                <CreateTenantCard onCreated={() => void bootstrap()} />
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h3 className="text-base font-semibold text-foreground">Registered Organizations</h3>
                    <p className="text-xs text-muted-foreground">Manage organization scopes, domains, and team members</p>
                  </div>
                  <Button size="sm" onClick={() => goInvite(selectedTenant?.id)} className="gap-1.5">
                    <UserPlus className="h-3.5 w-3.5" />
                    Invite Member to Tenant
                  </Button>
                </div>

                {tenants.state !== "ready" ? (
                  <SectionState state={tenants} service="Admin" section="tenants" onRetry={() => void bootstrap()} />
                ) : tenantList.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">No tenants exist yet. Create one above.</p>
                ) : (
                  <div className="grid gap-4 lg:grid-cols-2">
                    {tenantList.map((tenant) => (
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
                          <DataRow label="Domain" value={tenant.domain || tenant.subdomain || "-"} />
                          <DataRow label="Tier" value={tenant.tier || "-"} />
                          <DataRow label="Org Code" value={tenant.org_code || "-"} />
                          <DataRow label="Created" value={fmtDate(tenant.created_at)} />
                          <TenantSeatControls
                            tenant={tenant}
                            usage={readyData(seatRows).find((r) => r.tenant_id === tenant.id)}
                            onChanged={() => void bootstrap()}
                          />

                          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/60">
                            <Button size="sm" variant="outline" className="text-xs h-8 gap-1.5" onClick={() => goInvite(tenant.id)}>
                              <UserPlus className="h-3.5 w-3.5 text-cyan-400" />
                              Invite Member
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-xs h-8 gap-1.5 text-muted-foreground hover:text-foreground"
                              onClick={() => {
                                selectTenant(tenant.id)
                                setActiveTab("modules")
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
                )}
              </TabsContent>
            )}

            <TabsContent value="modules">
              <Card>
                <CardHeader>
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <CardTitle className="text-base">Tenant Module Entitlements</CardTitle>
                      <CardDescription>
                        {isPlatformAdmin
                          ? "Grant or revoke functional platform modules per organization"
                          : "Modules enabled for your organization. Only the platform team can change these."}
                      </CardDescription>
                    </div>
                    {isPlatformAdmin && (
                      <select
                        aria-label="Tenant"
                        className="h-9 rounded-md border border-border bg-background px-3 text-sm font-medium"
                        value={selectedTenant?.id || ""}
                        onChange={(event) => selectTenant(event.target.value)}
                      >
                        {tenantList.map((tenant) => (
                          <option key={tenant.id} value={tenant.id}>{tenant.name}</option>
                        ))}
                      </select>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  {tenantModules.state !== "ready" ? (
                    <SectionState
                      state={tenantModules}
                      service="Admin"
                      section="modules"
                      onRetry={() => {
                        invalidateAdminCache()
                        void loadTenantModules(selectedTenant?.id || identity?.tenant_id || "")
                      }}
                    />
                  ) : (
                    <>
                      <div className="mb-4 text-sm text-muted-foreground">
                        <span className="font-semibold text-foreground">{enabledModules}</span> modules active for{" "}
                        <span className="font-medium text-foreground">{selectedTenant?.name || "your organization"}</span>
                      </div>
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        {modulesList.map((item) => {
                          const key = item.module_name || item.key || item.name
                          const Wrapper: React.ElementType = isPlatformAdmin ? "button" : "div"
                          return (
                            <Wrapper
                              key={key}
                              {...(isPlatformAdmin
                                ? {
                                    type: "button" as const,
                                    onClick: () => void toggleTenantModule(item),
                                    disabled: moduleBusy !== null,
                                    "aria-pressed": !!item.enabled,
                                  }
                                : {})}
                              className={`rounded-lg border border-border bg-card p-4 text-left transition-colors group ${isPlatformAdmin ? "hover:border-primary/50 disabled:opacity-60" : ""}`}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <p className="font-medium text-foreground group-hover:text-primary transition-colors">{item.name || key}</p>
                                  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.description || key}</p>
                                </div>
                                {item.enabled ? <ToggleRight className="h-6 w-6 text-emerald-400 shrink-0" /> : <ToggleLeft className="h-6 w-6 text-muted-foreground shrink-0" />}
                              </div>
                            </Wrapper>
                          )
                        })}
                        {modulesList.length === 0 && <p className="col-span-full text-sm text-muted-foreground">No modules returned for this organization.</p>}
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="users">
              <Card>
                <CardHeader>
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <KeyRound className="h-4 w-4 text-cyan-400" /> Tenant Users
                      </CardTitle>
                      <CardDescription>Assign functional access roles to the users of your organization</CardDescription>
                    </div>
                    {canManageTeam && (
                      <Button size="sm" onClick={() => goInvite()} className="gap-1.5">
                        <UserPlus className="h-3.5 w-3.5" />
                        Add user (Team invite)
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  {users.state !== "ready" ? (
                    <SectionState state={users} service="Admin" section="users" onRetry={() => retrySection("users")} />
                  ) : (
                    <div className="space-y-3">
                      {users.data.map((user) => (
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
                      {users.data.length === 0 && (
                        <div className="py-12 text-center text-muted-foreground space-y-2">
                          <Users className="h-8 w-8 mx-auto text-muted-foreground/40" />
                          <p className="text-sm font-medium">No users in this organization yet.</p>
                          <p className="text-xs">Use the Team tab to invite people.</p>
                        </div>
                      )}
                    </div>
                  )}
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
                      aria-pressed={auditSubTab === "agents"}
                      onClick={() => setAuditSubTab("agents")}
                      className="gap-2 text-xs"
                    >
                      <Bot className="h-4 w-4 text-primary" />
                      <span>Agent Actions & AI Audits</span>
                      <Badge variant="outline" className="text-[10px] ml-1 bg-background font-mono">
                        {agentActions.state === "ready" ? agentActions.data.length : "-"}
                      </Badge>
                    </Button>
                    <Button
                      variant={auditSubTab === "system" ? "secondary" : "ghost"}
                      size="sm"
                      aria-pressed={auditSubTab === "system"}
                      onClick={() => setAuditSubTab("system")}
                      className="gap-2 text-xs"
                    >
                      <Activity className="h-4 w-4 text-muted-foreground" />
                      <span>Platform System Events</span>
                      <Badge variant="outline" className="text-[10px] ml-1 bg-background font-mono">
                        {auditLog.state === "ready" ? auditLog.data.length : "-"}
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
                          aria-pressed={agentFilter === ag}
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
                        {agentActions.state === "ready" && (
                          <Badge variant="outline" className="font-mono text-xs">
                            {filteredAgentActions.length} actions
                          </Badge>
                        )}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {agentActions.state !== "ready" ? (
                        <SectionState state={agentActions} service="Agent orchestrator" section="audit" onRetry={() => retrySection("audit")} />
                      ) : filteredAgentActions.length === 0 ? (
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
                      {auditLog.state !== "ready" ? (
                        <SectionState state={auditLog} service="Admin" section="audit" onRetry={() => retrySection("audit")} />
                      ) : (
                        <div className="space-y-2">
                          {auditLog.data.map((event) => (
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
                          {auditLog.data.length === 0 && <p className="text-sm text-muted-foreground">No audit events recorded.</p>}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}
              </div>
            </TabsContent>

            {/* ── COMMISSION TIERS TAB ────────── */}
            <TabsContent value="commission" className="space-y-4">
              <div className="rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-4 text-xs text-foreground flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-start gap-2.5">
                  <Info className="h-4 w-4 text-cyan-400 shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-sm">Commission tiers</p>
                    <p className="text-muted-foreground mt-0.5">
                      Tiers you define here belong to your organization. Review statements and payouts in <strong>Finance & Billing</strong>.
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
                    {tiers.state === "ready" && (
                      <Button size="sm" onClick={() => openCommissionModal()} className="gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white">
                        <Plus className="h-3.5 w-3.5" />
                        Add Commission Tier
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  {tiers.state !== "ready" ? (
                    <SectionState state={tiers} service="Admin" section="commission" onRetry={() => retrySection("commission")} />
                  ) : (
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      {tiers.data.map((tier) => (
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
                                aria-label={`Edit tier ${tier.tier_name}`}
                              >
                                <Edit3 className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-7 w-7 text-muted-foreground hover:text-red-400"
                                onClick={() => {
                                  setDeleteErr(null)
                                  setDeleteTier(tier)
                                }}
                                title="Delete Tier"
                                aria-label={`Delete tier ${tier.tier_name}`}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          </div>
                        </div>
                      ))}
                      {tiers.data.length === 0 && (
                        <div className="col-span-full py-10 text-center text-sm text-muted-foreground">
                          No commission tiers configured. Click Add Commission Tier to configure sales structures.
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* ── PROTOCOLS & MANDATES TAB (read-only; no simulation, no invented policy values) ── */}
            <TabsContent value="protocols">
              <div className="space-y-6">
                <Card className="border-border bg-card">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Settings2 className="h-4 w-4 text-cyan-400" /> Protocol Policy
                    </CardTitle>
                    <CardDescription>
                      UCP (Universal Commerce Protocol) and AP2 (Agent Payments Protocol) records created by agents for your organization.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="rounded-lg border border-border p-3.5 space-y-2 bg-secondary/20">
                        <span className="font-semibold text-sm flex items-center gap-1.5">
                          <LinkIcon className="h-4 w-4 text-cyan-400" />
                          Universal Commerce Protocol (UCP)
                        </span>
                        <div className="flex justify-between text-xs text-muted-foreground">
                          <span>Auto-approve cart limit</span>
                          <span className="font-medium text-foreground">Not configured here</span>
                        </div>
                      </div>
                      <div className="rounded-lg border border-border p-3.5 space-y-2 bg-secondary/20">
                        <span className="font-semibold text-sm flex items-center gap-1.5">
                          <ShieldCheck className="h-4 w-4 text-purple-400" />
                          Agent Payments Protocol (AP2)
                        </span>
                        <div className="flex justify-between text-xs text-muted-foreground">
                          <span>Dual-signature threshold</span>
                          <span className="font-medium text-foreground">Not configured here</span>
                        </div>
                      </div>
                    </div>
                    <p className="mt-3 text-xs text-muted-foreground">
                      The services expose no endpoint to read or change policy thresholds, so none are shown. Limits are set in the orchestrator service configuration.
                    </p>
                  </CardContent>
                </Card>

                {/* Summary counts only for lists that actually loaded */}
                <div className="grid gap-4 md:grid-cols-3">
                  <Card>
                    <CardContent className="flex items-center justify-between p-4">
                      <div>
                        <p className="text-sm text-muted-foreground">UCP Sessions</p>
                        <p className="text-2xl font-semibold"><StatValue loadable={ucpSessions}>{(d) => d.length}</StatValue></p>
                      </div>
                      <LinkIcon className="h-5 w-5 text-cyan-400" />
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="flex items-center justify-between p-4">
                      <div>
                        <p className="text-sm text-muted-foreground">Intent Mandates</p>
                        <p className="text-2xl font-semibold"><StatValue loadable={intentMandates}>{(d) => d.length}</StatValue></p>
                      </div>
                      <ShieldCheck className="h-5 w-5 text-amber-400" />
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="flex items-center justify-between p-4">
                      <div>
                        <p className="text-sm text-muted-foreground">Payment Mandates</p>
                        <p className="text-2xl font-semibold"><StatValue loadable={paymentMandates}>{(d) => d.length}</StatValue></p>
                      </div>
                      <CircleDollarSign className="h-5 w-5 text-emerald-400" />
                    </CardContent>
                  </Card>
                </div>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base"><LinkIcon className="h-4 w-4 text-cyan-400" /> UCP Checkout Sessions</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {ucpSessions.state !== "ready" ? (
                      <SectionState state={ucpSessions} service="Agent orchestrator" section="protocols" onRetry={() => retrySection("protocols")} />
                    ) : (
                      <div className="space-y-2">
                        {ucpSessions.data.map((session) => (
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
                        {ucpSessions.data.length === 0 && <p className="text-sm text-muted-foreground">No UCP checkout sessions recorded.</p>}
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="h-4 w-4 text-purple-400" /> AP2 Intent Mandates</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {intentMandates.state !== "ready" ? (
                      <SectionState state={intentMandates} service="Agent orchestrator" section="protocols" onRetry={() => retrySection("protocols")} />
                    ) : (
                      <div className="space-y-2">
                        {intentMandates.data.map((mandate) => (
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
                        {intentMandates.data.length === 0 && <p className="text-sm text-muted-foreground">No AP2 intent mandates recorded.</p>}
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base"><CircleDollarSign className="h-4 w-4" /> AP2 Payment Mandates</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {paymentMandates.state !== "ready" ? (
                      <SectionState state={paymentMandates} service="Agent orchestrator" section="protocols" onRetry={() => retrySection("protocols")} />
                    ) : (
                      <div className="space-y-2">
                        {paymentMandates.data.map((mandate) => (
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
                        {paymentMandates.data.length === 0 && <p className="text-sm text-muted-foreground">No AP2 payment mandates recorded.</p>}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </TabsContent>
          </Tabs>
        </>
      )}

      {/* ── DIALOG: ROLE ACCESS (real roles from the server) ───────────────── */}
      <Dialog open={roleGrantOpen} onOpenChange={(o) => !o && !roleSaving && setRoleGrantOpen(false)}>
        <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-cyan-400" />
              Grant role access
            </DialogTitle>
            <DialogDescription>
              Roles of your organization for <strong>{roleGrantUser?.name || roleGrantUser?.email}</strong>. The server checks that you may grant each one.
              For rank-aware role editing use the Team tab.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2 py-2">
            {roleOptions.state !== "ready" ? (
              <SectionState
                state={roleOptions}
                service="Admin"
                section="users"
                onRetry={() => void runInto(setRoleOptions, () => adminApi.listRoles())}
              />
            ) : roleOptions.data.length === 0 ? (
              <p className="text-sm text-muted-foreground">No roles are defined for this organization.</p>
            ) : (
              roleOptions.data.map((role) => {
                const isSelected = selectedRoleIds.includes(role.id)
                return (
                  <button
                    key={role.id}
                    type="button"
                    role="checkbox"
                    aria-checked={isSelected}
                    onClick={() => toggleRoleSelection(role.id)}
                    className={cn(
                      "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-all",
                      isSelected ? "border-primary bg-primary/5 shadow-sm" : "border-border bg-card hover:bg-secondary/20",
                    )}
                  >
                    <span className="mt-0.5 text-primary">
                      {isSelected ? <CheckSquare className="h-4 w-4" /> : <Square className="h-4 w-4 text-muted-foreground" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-foreground">{role.name}</span>
                        {isSystemRole(role) && (
                          <Badge variant="outline" className="text-[10px] uppercase" title="System roles are immutable">
                            System
                          </Badge>
                        )}
                      </span>
                      {role.description && <span className="mt-0.5 block text-xs text-muted-foreground">{role.description}</span>}
                      {role.permissions && role.permissions.length > 0 && (
                        <span className="mt-2 flex flex-wrap gap-1">
                          {role.permissions.map((p) => (
                            <span key={p} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{p}</span>
                          ))}
                        </span>
                      )}
                    </span>
                  </button>
                )
              })
            )}
            {roleErr && (
              <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
                {roleErr}
              </div>
            )}
          </div>

          <DialogFooter className="pt-2">
            <Button type="button" variant="ghost" onClick={() => setRoleGrantOpen(false)} disabled={roleSaving}>
              Cancel
            </Button>
            <Button onClick={() => void handleSaveRoleGrant()} disabled={roleSaving || selectedRoleIds.length === 0} className="gap-1.5">
              {roleSaving ? "Applying..." : "Grant selected roles"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── DIALOG: COMMISSION TIER (ADD / EDIT) ───────────────────────────── */}
      <Dialog open={commissionOpen} onOpenChange={(o) => !o && !commissionSaving && setCommissionOpen(false)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CircleDollarSign className="h-5 w-5 text-emerald-400" />
              {editingTier ? "Edit Commission Tier" : "Add Commission Tier"}
            </DialogTitle>
            <DialogDescription>Configure milestone thresholds and payout percentages</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSaveCommissionTier} className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="tier-name">Tier Name *</Label>
              <Input id="tier-name" placeholder="e.g. Bronze, Silver, Gold, Platinum" value={tierName} onChange={(e) => setTierName(e.target.value)} required />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="tier-min">Min Deals *</Label>
                <Input id="tier-min" type="number" min={0} value={tierMinDeals} onChange={(e) => setTierMinDeals(e.target.value)} required />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tier-max">Max Deals (optional)</Label>
                <Input id="tier-max" type="number" placeholder="Uncapped" value={tierMaxDeals} onChange={(e) => setTierMaxDeals(e.target.value)} />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="tier-rate">Commission Rate (%) *</Label>
              <Input id="tier-rate" inputMode="decimal" placeholder="Enter a rate between 0 and 100" value={tierRate} onChange={(e) => setTierRate(e.target.value)} required />
            </div>

            <div className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <p className="font-medium text-sm" id="tier-active-label">Tier Active</p>
                <p className="text-xs text-muted-foreground">Inactive tiers are not listed on this page</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={tierActive}
                aria-labelledby="tier-active-label"
                onClick={() => setTierActive((p) => !p)}
                className="text-primary"
              >
                {tierActive ? <ToggleRight className="h-6 w-6 text-emerald-400" /> : <ToggleLeft className="h-6 w-6 text-muted-foreground" />}
              </button>
            </div>

            {tierErr && (
              <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
                {tierErr}
              </div>
            )}

            <DialogFooter className="pt-2">
              <Button type="button" variant="ghost" onClick={() => setCommissionOpen(false)} disabled={commissionSaving}>
                Cancel
              </Button>
              <Button type="submit" disabled={commissionSaving} className="gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white">
                {commissionSaving ? "Saving..." : editingTier ? "Update Tier" : "Create Tier"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleteTier}
        title="Delete commission tier?"
        description={`Tier "${deleteTier?.tier_name ?? ""}" will be removed. This cannot be undone.`}
        confirmLabel="Delete tier"
        busy={deleteBusy}
        error={deleteErr}
        onConfirm={() => void handleDeleteCommissionTier()}
        onClose={() => setDeleteTier(null)}
      />
    </div>
  )
}
