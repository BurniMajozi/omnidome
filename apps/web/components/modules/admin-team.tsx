"use client"

/**
 * Seat / invite / member management for the Admin module.
 *
 *  - TenantSeatControls + CreateTenantCard : platform_admin, inside the Tenants tab
 *  - TeamTab                               : org_admin / owner / platform_admin
 *  - SeatsBillingTab                       : platform_admin
 *
 * Authorization is enforced by services/admin; the role checks here only decide what
 * to show. Backend 403/409 messages are surfaced verbatim (adminErrorMessage).
 */

import { useCallback, useEffect, useMemo, useState } from "react"
import { AlertCircle, CheckCircle2, Copy, Crown, Loader2, MailPlus, RefreshCw, RotateCcw, Trash2, UserCog, UserMinus, UserPlus, UserCheck } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { cn } from "@/lib/utils"
import {
  ROLE_LABELS,
  BillingUnavailableError,
  TENANT_ROLE_RANKS,
  actorRank,
  adminApi,
  adminErrorMessage,
  grantableRoles,
  type CreatedInvite,
  type PlatformSeatRow,
  type ReconcileReport,
  type SeatBillingRun,
  type SeatUsage,
  type Tenant,
  type TenantInvite,
  type TenantMember,
  type Whoami,
} from "@/lib/admin-api"

const SMTP_NOTE = "Email delivery depends on SMTP being configured; copy this link to send it yourself."
const NATIVE_SELECT =
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"

const roleLabel = (r: string) => ROLE_LABELS[r] || r
const fmt = (v?: string) => {
  if (!v) return "-"
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString()
}

// ── shared bits ─────────────────────────────────────────────────────────────

function InlineAlert({ message, onDismiss }: { message: string | null; onDismiss?: () => void }) {
  if (!message) return null
  return (
    <div role="alert" className="flex items-start justify-between gap-3 rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
      <span className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{message}</span>
      </span>
      {onDismiss && (
        <Button variant="ghost" size="sm" className="h-6 text-xs text-red-400" onClick={onDismiss}>
          Dismiss
        </Button>
      )}
    </div>
  )
}

function InlineNotice({ message, onDismiss }: { message: string | null; onDismiss?: () => void }) {
  if (!message) return null
  return (
    <div role="status" className="flex items-start justify-between gap-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-400">
      <span className="flex items-start gap-2">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{message}</span>
      </span>
      {onDismiss && (
        <Button variant="ghost" size="sm" className="h-6 text-xs text-emerald-400" onClick={onDismiss}>
          Dismiss
        </Button>
      )}
    </div>
  )
}

export function SeatMeter({ used, limit, pending }: { used: number; limit: number | null; pending: number }) {
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0
  const full = limit != null && used >= limit
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-medium">
          {used} of {limit ?? "unlimited"} seats used
        </span>
        <span className="text-xs text-muted-foreground">{pending} pending invite{pending === 1 ? "" : "s"}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={used} aria-valuemin={0} aria-valuemax={limit ?? used}>
        <div className={cn("h-full rounded-full transition-all", full ? "bg-red-500" : pct > 80 ? "bg-amber-500" : "bg-emerald-500")} style={{ width: `${limit ? pct : 0}%` }} />
      </div>
    </div>
  )
}

export function CopyLinkBox({ link, email }: { link: string; email?: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }
  return (
    <div className="space-y-2 rounded-md border border-cyan-500/30 bg-cyan-500/5 p-3 text-sm">
      <p className="font-medium">Invitation link{email ? ` for ${email}` : ""}</p>
      <div className="flex gap-2">
        <Input readOnly value={link} className="font-mono text-xs" onFocus={(e) => e.currentTarget.select()} aria-label="Invitation accept link" />
        <Button type="button" size="sm" variant="outline" className="shrink-0 gap-1.5" onClick={() => void copy()}>
          <Copy className="h-3.5 w-3.5" />
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{SMTP_NOTE}</p>
      <p className="text-xs text-muted-foreground">This link is shown only now; the server stores just a hash. Resend the invite to get a new one.</p>
    </div>
  )
}

const slug = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)

// ── Tenants tab additions (platform_admin) ──────────────────────────────────

export function CreateTenantCard({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("")
  const [subdomain, setSubdomain] = useState("")
  const [seatLimit, setSeatLimit] = useState("10")
  const [seatPrice, setSeatPrice] = useState("")
  const [ownerEmail, setOwnerEmail] = useState("")
  const [sendEmail, setSendEmail] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [created, setCreated] = useState<{ name: string; link?: string; email?: string; emailError?: string | null } | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr(null)
    const limit = Number(seatLimit)
    if (!name.trim()) return setErr("Organization name is required")
    if (!Number.isInteger(limit) || limit < 1) return setErr("Seat limit must be a whole number of at least 1")
    if (seatPrice && (Number.isNaN(Number(seatPrice)) || Number(seatPrice) < 0)) return setErr("Seat price must be zero or more")
    setBusy(true)
    try {
      const res = await adminApi.createTenant({
        name: name.trim(),
        domain: subdomain.trim() || slug(name),
        seat_limit: limit,
        seat_price: seatPrice ? Number(seatPrice) : undefined,
        owner_email: ownerEmail.trim() || undefined,
        send_owner_invite_email: sendEmail,
      })
      setCreated({ name: res.name, link: res.owner_invite?.accept_link, email: res.owner_invite?.email, emailError: res.owner_invite?.email_error })
      setName("")
      setSubdomain("")
      setOwnerEmail("")
      onCreated()
    } catch (e2) {
      setErr(adminErrorMessage(e2))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Create tenant</CardTitle>
        <CardDescription>Allocate an organization, its seat limit and price per seat, and invite its owner.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <form onSubmit={submit} className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="ct-name">Organization name</Label>
            <Input id="ct-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Networks" required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ct-sub">Subdomain</Label>
            <Input id="ct-sub" value={subdomain} onChange={(e) => setSubdomain(e.target.value)} placeholder={slug(name) || "acme-networks"} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ct-owner">Owner email</Label>
            <Input id="ct-owner" type="email" value={ownerEmail} onChange={(e) => setOwnerEmail(e.target.value)} placeholder="owner@acme.example" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ct-limit">Seat limit</Label>
            <Input id="ct-limit" type="number" min={1} value={seatLimit} onChange={(e) => setSeatLimit(e.target.value)} required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ct-price">Seat price per month</Label>
            <Input id="ct-price" type="number" min={0} step="0.01" value={seatPrice} onChange={(e) => setSeatPrice(e.target.value)} placeholder="0.00" />
          </div>
          <div className="flex items-end gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={sendEmail} onChange={(e) => setSendEmail(e.target.checked)} />
              Email the owner invite
            </label>
            <Button type="submit" disabled={busy} className="ml-auto gap-1.5">
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UserPlus className="h-3.5 w-3.5" />}
              Create tenant
            </Button>
          </div>
        </form>
        <InlineAlert message={err} onDismiss={() => setErr(null)} />
        {created && (
          <div className="space-y-2">
            <InlineNotice message={`Tenant "${created.name}" created.`} onDismiss={() => setCreated(null)} />
            {created.link ? (
              <>
                <CopyLinkBox link={created.link} email={created.email} />
                {created.emailError && <p className="text-xs text-amber-400">Email was not sent: {created.emailError}</p>}
              </>
            ) : (
              <p className="text-xs text-muted-foreground">No owner email was given, so no invite was created. Invite the owner from the Team tab.</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

const TIERS = ["FREE", "STARTER", "PROFESSIONAL", "ENTERPRISE"]

export function TenantSeatControls({ tenant, usage, onChanged }: { tenant: Tenant; usage?: PlatformSeatRow; onChanged: () => void }) {
  const [limit, setLimit] = useState(usage?.seat_limit != null ? String(usage.seat_limit) : "")
  const [tier, setTier] = useState((tenant.tier || "").toUpperCase())
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)

  useEffect(() => {
    setLimit(usage?.seat_limit != null ? String(usage.seat_limit) : "")
  }, [usage?.seat_limit])

  const save = async () => {
    setErr(null)
    setOk(null)
    setBusy(true)
    try {
      const n = Number(limit)
      if (limit !== "" && usage?.seat_limit !== n) {
        if (!Number.isInteger(n) || n < 1) throw new Error("Seat limit must be a whole number of at least 1")
        await adminApi.setSeats(tenant.id, { seat_limit: n })
      }
      if (tier && tier !== (tenant.tier || "").toUpperCase()) await adminApi.updateTenant(tenant.id, { tier })
      setOk("Saved")
      onChanged()
    } catch (e) {
      setErr(adminErrorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3 border-t border-border/60 pt-3">
      {usage ? <SeatMeter used={usage.seats_used} limit={usage.seat_limit} pending={usage.pending_invites} /> : <p className="text-xs text-muted-foreground">Seat usage unavailable.</p>}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor={`sl-${tenant.id}`} className="text-xs">Seat limit</Label>
          <Input id={`sl-${tenant.id}`} type="number" min={1} value={limit} onChange={(e) => setLimit(e.target.value)} className="h-8" />
        </div>
        <div className="space-y-1">
          <Label htmlFor={`tier-${tenant.id}`} className="text-xs">Tier</Label>
          <select id={`tier-${tenant.id}`} className={cn(NATIVE_SELECT, "h-8")} value={tier} onChange={(e) => setTier(e.target.value)}>
            {!TIERS.includes(tier) && <option value={tier}>{tier || "-"}</option>}
            {TIERS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">
          {usage?.seat_price != null ? `Price per seat: ${usage.seat_price}` : "No seat price set"}
        </span>
        <Button size="sm" variant="outline" className="h-8 text-xs" disabled={busy} onClick={() => void save()}>
          {busy ? "Saving..." : "Save seats and tier"}
        </Button>
      </div>
      <InlineAlert message={err} onDismiss={() => setErr(null)} />
      {ok && <p className="text-xs text-emerald-400">{ok}</p>}
    </div>
  )
}

// ── Team tab ────────────────────────────────────────────────────────────────

type ConfirmState = { kind: "deactivate" | "reactivate"; member: TenantMember } | null

export function TeamTab({ identity, tenants }: { identity: Whoami | null; tenants: Tenant[] }) {
  const roles = useMemo(() => identity?.roles ?? [], [identity])
  const isPlatform = roles.includes("platform_admin")
  const isOwner = isPlatform || roles.includes("owner")
  const rank = actorRank(roles)
  const grantable = useMemo(() => grantableRoles(roles), [roles])

  const [pickedTenant, setPickedTenant] = useState("")
  const tenantId = pickedTenant || identity?.tenant_id || ""

  const [seats, setSeats] = useState<SeatUsage | null>(null)
  const [invites, setInvites] = useState<TenantInvite[]>([])
  const [members, setMembers] = useState<TenantMember[]>([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [email, setEmail] = useState("")
  const [inviteRole, setInviteRole] = useState("org_user")
  const [sendEmail, setSendEmail] = useState(true)
  const [inviting, setInviting] = useState(false)
  const [links, setLinks] = useState<Record<string, string>>({})
  const [latest, setLatest] = useState<CreatedInvite | null>(null)

  const [roleTarget, setRoleTarget] = useState<TenantMember | null>(null)
  const [roleDraft, setRoleDraft] = useState<string[]>([])
  const [confirm, setConfirm] = useState<ConfirmState>(null)
  const [transferTarget, setTransferTarget] = useState<TenantMember | null>(null)
  const [typed, setTyped] = useState("")
  const [dialogBusy, setDialogBusy] = useState(false)
  const [dialogErr, setDialogErr] = useState<string | null>(null)
  const [rowBusy, setRowBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!tenantId) return
    setLoading(true)
    const [s, i, m] = await Promise.allSettled([adminApi.getSeats(tenantId), adminApi.listInvites(tenantId), adminApi.listMembers(tenantId)])
    setSeats(s.status === "fulfilled" ? s.value : null)
    setInvites(i.status === "fulfilled" ? i.value : [])
    setMembers(m.status === "fulfilled" ? m.value : [])
    const failed = [s, i, m].find((r) => r.status === "rejected") as PromiseRejectedResult | undefined
    setErr(failed ? adminErrorMessage(failed.reason) : null)
    setLoading(false)
  }, [tenantId])

  useEffect(() => {
    setLinks({})
    setLatest(null)
    void load()
  }, [load])

  const effectiveRole = grantable.includes(inviteRole) ? inviteRole : grantable[0] || ""
  const atLimit = seats?.seat_limit != null && seats.seats_used >= seats.seat_limit
  const canInvite = !!tenantId && !atLimit && !!effectiveRole && !!email.trim()

  const sendInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canInvite) return
    setInviting(true)
    setErr(null)
    setNotice(null)
    try {
      const res = await adminApi.createInvite(tenantId, { email: email.trim(), roles: [effectiveRole], send_email: sendEmail })
      setLatest(res)
      if (res.accept_link) setLinks((p) => ({ ...p, [res.invite_id]: res.accept_link! }))
      setNotice(`Invitation created for ${res.email}. It holds a seat for 7 days.`)
      setEmail("")
      await load()
    } catch (e2) {
      setErr(adminErrorMessage(e2))
    } finally {
      setInviting(false)
    }
  }

  const resend = async (inv: TenantInvite) => {
    setRowBusy(inv.id)
    setErr(null)
    try {
      const res = await adminApi.resendInvite(inv.id, sendEmail)
      setLatest({ ...res, email: inv.email, roles: inv.roles })
      if (res.accept_link) setLinks((p) => ({ ...p, [inv.id]: res.accept_link! }))
      setNotice(`Invitation to ${inv.email} resent with a fresh 7 day expiry.`)
      await load()
    } catch (e) {
      setErr(adminErrorMessage(e))
    } finally {
      setRowBusy(null)
    }
  }

  const revoke = async (inv: TenantInvite) => {
    setRowBusy(inv.id)
    setErr(null)
    try {
      await adminApi.revokeInvite(inv.id)
      setLinks((p) => {
        const { [inv.id]: _drop, ...rest } = p
        return rest
      })
      if (latest?.invite_id === inv.id) setLatest(null)
      setNotice(`Invitation to ${inv.email} revoked; the seat is free again.`)
      await load()
    } catch (e) {
      setErr(adminErrorMessage(e))
    } finally {
      setRowBusy(null)
    }
  }

  const copyInviteLink = async (link: string) => {
    try {
      await navigator.clipboard.writeText(link)
      setNotice("Link copied to clipboard.")
    } catch {
      setErr("Could not copy automatically; select and copy the link shown above.")
    }
  }

  const memberRank = (m: TenantMember) => Math.max(0, ...m.roles.map((r) => TENANT_ROLE_RANKS[r] ?? 0))
  const canManage = (m: TenantMember) => isPlatform || memberRank(m) <= rank
  const memberIsOwner = (m: TenantMember) => !!m.is_owner || m.roles.includes("owner")

  const openRoles = (m: TenantMember) => {
    setDialogErr(null)
    setRoleDraft(m.roles.filter((r) => grantable.includes(r)))
    setRoleTarget(m)
  }

  const saveRoles = async () => {
    if (!roleTarget) return
    // Roles we cannot grant but the member already holds must be sent back unchanged.
    const locked = roleTarget.roles.filter((r) => !grantable.includes(r))
    const next = Array.from(new Set([...roleDraft, ...locked]))
    if (next.length === 0) {
      setDialogErr("A member needs at least one role.")
      return
    }
    setDialogBusy(true)
    setDialogErr(null)
    try {
      await adminApi.setMemberRoles(tenantId, roleTarget.id, next)
      setNotice(`Roles updated for ${roleTarget.email}. They take effect on the member's next sign-in or token refresh.`)
      setRoleTarget(null)
      await load()
    } catch (e) {
      setDialogErr(adminErrorMessage(e))
    } finally {
      setDialogBusy(false)
    }
  }

  const runConfirm = async () => {
    if (!confirm) return
    setDialogBusy(true)
    setDialogErr(null)
    try {
      if (confirm.kind === "deactivate") await adminApi.deactivateMember(tenantId, confirm.member.id)
      else await adminApi.reactivateMember(tenantId, confirm.member.id)
      setNotice(`${confirm.member.email} ${confirm.kind === "deactivate" ? "deactivated; the seat is released" : "reactivated"}.`)
      setConfirm(null)
      await load()
    } catch (e) {
      setDialogErr(adminErrorMessage(e))
    } finally {
      setDialogBusy(false)
    }
  }

  const runTransfer = async () => {
    if (!transferTarget) return
    setDialogBusy(true)
    setDialogErr(null)
    try {
      await adminApi.transferOwnership(tenantId, transferTarget.id)
      setNotice(`Ownership transferred to ${transferTarget.email}. Previous owners are now org admins.`)
      setTransferTarget(null)
      await load()
    } catch (e) {
      setDialogErr(adminErrorMessage(e))
    } finally {
      setDialogBusy(false)
    }
  }

  const openInvites = invites.filter((i) => i.status === "pending" || i.status === "expired")
  const tenantName = tenants.find((t) => t.id === tenantId)?.name

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h3 className="text-base font-semibold">Team{tenantName ? `: ${tenantName}` : ""}</h3>
          <p className="text-xs text-muted-foreground">Invite people and manage their roles within your seat limit. Invites hold a seat for 7 days.</p>
        </div>
        <div className="flex items-end gap-2">
          {isPlatform && (
            <div className="min-w-56 space-y-1">
              <Label htmlFor="team-tenant" className="text-xs">Tenant</Label>
              <select id="team-tenant" className={NATIVE_SELECT} value={tenantId} onChange={(e) => setPickedTenant(e.target.value)}>
                {tenants.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
                {tenantId && !tenants.some((t) => t.id === tenantId) && <option value={tenantId}>Current tenant</option>}
              </select>
            </div>
          )}
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading} className="gap-1.5">
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      <InlineAlert message={err} onDismiss={() => setErr(null)} />
      <InlineNotice message={notice} onDismiss={() => setNotice(null)} />

      {!tenantId && <p className="text-sm text-muted-foreground">No tenant resolved for your account.</p>}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Seats</CardTitle>
          </CardHeader>
          <CardContent>
            {seats ? (
              <SeatMeter used={seats.seats_used} limit={seats.seat_limit} pending={seats.pending_invites} />
            ) : (
              <p className="text-sm text-muted-foreground">{loading ? "Loading..." : "Seat usage unavailable."}</p>
            )}
            {seats && (
              <p className="mt-2 text-xs text-muted-foreground">
                {seats.active_users} active member{seats.active_users === 1 ? "" : "s"} plus {seats.pending_invites} pending invite{seats.pending_invites === 1 ? "" : "s"}.
                {seats.seat_limit != null && ` ${seats.seats_available ?? 0} free.`}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Invite a member</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <form onSubmit={sendInvite} className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-[1fr_11rem]">
                <div className="space-y-1.5">
                  <Label htmlFor="inv-email">Email</Label>
                  <Input id="inv-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.example" disabled={atLimit} required />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="inv-role">Role</Label>
                  <select id="inv-role" className={NATIVE_SELECT} value={effectiveRole} onChange={(e) => setInviteRole(e.target.value)} disabled={atLimit}>
                    {grantable.map((r) => (
                      <option key={r} value={r}>{roleLabel(r)}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="flex items-center justify-between gap-3">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={sendEmail} onChange={(e) => setSendEmail(e.target.checked)} disabled={atLimit} />
                  Email the invitation
                </label>
                <Button type="submit" size="sm" disabled={!canInvite || inviting} className="gap-1.5">
                  {inviting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <MailPlus className="h-3.5 w-3.5" />}
                  Send invite
                </Button>
              </div>
              {atLimit && (
                <p className="text-xs text-amber-400">
                  All {seats?.seat_limit} seats are used (pending invites count). Revoke an invite or deactivate a member, or ask the platform owner to raise the limit.
                </p>
              )}
              <p className="text-xs text-muted-foreground">You can only grant roles at or below your own level.</p>
            </form>
          </CardContent>
        </Card>
      </div>

      {latest?.accept_link && <CopyLinkBox link={latest.accept_link} email={latest.email} />}
      {latest && latest.email_error && <p className="text-xs text-amber-400">Email was not sent: {latest.email_error}</p>}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Pending invitations</CardTitle>
          <CardDescription>The server stores only a hash of each link, so a link can be copied only right after it was created or resent.</CardDescription>
        </CardHeader>
        <CardContent>
          {openInvites.length === 0 ? (
            <p className="text-sm text-muted-foreground">No pending invitations.</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Email</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Expires</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {openInvites.map((inv) => (
                    <TableRow key={inv.id}>
                      <TableCell>{inv.email}</TableCell>
                      <TableCell>{(inv.roles || []).map(roleLabel).join(", ")}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={inv.status === "expired" ? "border-amber-500/40 text-amber-400" : "border-cyan-500/40 text-cyan-400"}>{inv.status}</Badge>
                      </TableCell>
                      <TableCell className="text-xs">{fmt(inv.expires_at)}</TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-1.5">
                          <Button size="sm" variant="outline" className="h-8 gap-1 text-xs" disabled={rowBusy === inv.id} onClick={() => void resend(inv)}>
                            <RotateCcw className="h-3 w-3" /> Resend
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-8 gap-1 text-xs"
                            disabled={!links[inv.id]}
                            title={links[inv.id] ? "Copy the invitation link" : "Only available right after create/resend; the server stores just a hash. Use Resend to get a new link."}
                            onClick={() => void copyInviteLink(links[inv.id])}
                          >
                            <Copy className="h-3 w-3" /> Copy link
                          </Button>
                          <Button size="sm" variant="ghost" className="h-8 gap-1 text-xs text-red-400" disabled={rowBusy === inv.id} onClick={() => void revoke(inv)}>
                            <Trash2 className="h-3 w-3" /> Revoke
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Members</CardTitle>
        </CardHeader>
        <CardContent>
          {members.length === 0 ? (
            <p className="text-sm text-muted-foreground">{loading ? "Loading..." : "No members yet."}</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Member</TableHead>
                    <TableHead>Roles</TableHead>
                    <TableHead>Seat</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {members.map((m) => {
                    const manageable = canManage(m)
                    const self = m.id === identity?.user_id
                    return (
                      <TableRow key={m.id} className={cn(!m.is_active && "opacity-60")}>
                        <TableCell>
                          <div className="font-medium">{m.name || m.email}</div>
                          {m.name && <div className="text-xs text-muted-foreground">{m.email}</div>}
                          {self && <span className="text-xs text-muted-foreground">(you)</span>}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-1">
                            {memberIsOwner(m) && (
                              <Badge className="gap-1 bg-amber-500/20 text-amber-400 hover:bg-amber-500/20"><Crown className="h-3 w-3" />Owner</Badge>
                            )}
                            {m.roles.filter((r) => r !== "owner").map((r) => (
                              <Badge key={r} variant="outline">{roleLabel(r)}</Badge>
                            ))}
                            {m.roles.length === 0 && <span className="text-xs text-muted-foreground">no roles</span>}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className={m.is_active ? "border-emerald-500/40 text-emerald-400" : "border-red-500/40 text-red-400"}>{m.is_active ? "active" : "suspended"}</Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap justify-end gap-1.5">
                            <Button size="sm" variant="outline" className="h-8 gap-1 text-xs" disabled={!manageable} title={manageable ? "Edit roles" : "This member outranks you"} onClick={() => openRoles(m)}>
                              <UserCog className="h-3 w-3" /> Roles
                            </Button>
                            {m.is_active ? (
                              <Button size="sm" variant="ghost" className="h-8 gap-1 text-xs text-red-400" disabled={!manageable} onClick={() => { setDialogErr(null); setConfirm({ kind: "deactivate", member: m }) }}>
                                <UserMinus className="h-3 w-3" /> Deactivate
                              </Button>
                            ) : (
                              <Button size="sm" variant="outline" className="h-8 gap-1 text-xs" disabled={!manageable} onClick={() => { setDialogErr(null); setConfirm({ kind: "reactivate", member: m }) }}>
                                <UserCheck className="h-3 w-3" /> Reactivate
                              </Button>
                            )}
                            {isOwner && m.is_active && !memberIsOwner(m) && (
                              <Button size="sm" variant="outline" className="h-8 gap-1 text-xs" onClick={() => { setDialogErr(null); setTyped(""); setTransferTarget(m) }}>
                                <Crown className="h-3 w-3" /> Transfer ownership
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Role editor */}
      <Dialog open={!!roleTarget} onOpenChange={(o) => !o && setRoleTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Roles for {roleTarget?.email}</DialogTitle>
            <DialogDescription>Only roles you are allowed to grant can be changed.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {Object.keys(TENANT_ROLE_RANKS).map((r) => {
              const can = grantable.includes(r)
              const held = roleTarget?.roles.includes(r)
              const checked = can ? roleDraft.includes(r) : !!held
              return (
                <label key={r} className={cn("flex items-center gap-2 text-sm", !can && "opacity-60")}>
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={!can}
                    onChange={(e) => setRoleDraft((d) => (e.target.checked ? [...d, r] : d.filter((x) => x !== r)))}
                  />
                  {roleLabel(r)}
                  {!can && <span className="text-xs text-muted-foreground">(above your level)</span>}
                </label>
              )
            })}
          </div>
          <InlineAlert message={dialogErr} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRoleTarget(null)}>Cancel</Button>
            <Button onClick={() => void saveRoles()} disabled={dialogBusy}>{dialogBusy ? "Saving..." : "Save roles"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Deactivate / reactivate confirm */}
      <Dialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{confirm?.kind === "deactivate" ? "Deactivate member?" : "Reactivate member?"}</DialogTitle>
            <DialogDescription>
              {confirm?.kind === "deactivate"
                ? `${confirm?.member.email} will lose access immediately and the seat is released. Their data is kept.`
                : `${confirm?.member.email} will regain access and take a seat (a free seat is required).`}
            </DialogDescription>
          </DialogHeader>
          <InlineAlert message={dialogErr} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(null)}>Cancel</Button>
            <Button variant={confirm?.kind === "deactivate" ? "destructive" : "default"} onClick={() => void runConfirm()} disabled={dialogBusy}>
              {dialogBusy ? "Working..." : confirm?.kind === "deactivate" ? "Deactivate" : "Reactivate"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Transfer ownership: typed confirmation */}
      <Dialog open={!!transferTarget} onOpenChange={(o) => !o && setTransferTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Transfer ownership</DialogTitle>
            <DialogDescription>
              {transferTarget?.email} becomes the owner. Current owners are demoted to org admin. Type the new owner&apos;s email to confirm.
            </DialogDescription>
          </DialogHeader>
          <Input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={transferTarget?.email} aria-label="Type the new owner's email to confirm" autoComplete="off" />
          <InlineAlert message={dialogErr} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setTransferTarget(null)}>Cancel</Button>
            <Button onClick={() => void runTransfer()} disabled={dialogBusy || typed.trim().toLowerCase() !== (transferTarget?.email || "").toLowerCase()}>
              {dialogBusy ? "Transferring..." : "Transfer ownership"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Seats & Billing tab (platform_admin) ────────────────────────────────────

export function SeatsBillingTab({ tenants }: { tenants: Tenant[] }) {
  const [rows, setRows] = useState<PlatformSeatRow[]>([])
  const [total, setTotal] = useState(0)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const [runsTenant, setRunsTenant] = useState("")
  const [runs, setRuns] = useState<SeatBillingRun[] | null>(null)
  const [billingDown, setBillingDown] = useState(false)
  const [runsErr, setRunsErr] = useState<string | null>(null)
  const [runsLoading, setRunsLoading] = useState(false)

  const [report, setReport] = useState<ReconcileReport | null>(null)
  const [reconBusy, setReconBusy] = useState(false)
  const [reconErr, setReconErr] = useState<string | null>(null)
  const [applyOpen, setApplyOpen] = useState(false)
  const [applied, setApplied] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await adminApi.platformSeatUsage()
      setRows(res.tenants)
      setTotal(res.total_seats_used)
      setErr(null)
    } catch (e) {
      setErr(adminErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const runsFor = runsTenant || rows[0]?.tenant_id || tenants[0]?.id || ""

  const loadRuns = useCallback(async () => {
    if (!runsFor) return
    setRunsLoading(true)
    setRunsErr(null)
    try {
      setRuns(await adminApi.listSeatRuns(runsFor))
      setBillingDown(false)
    } catch (e) {
      setRuns(null)
      if (e instanceof BillingUnavailableError) setBillingDown(true)
      else {
        setBillingDown(false)
        setRunsErr(adminErrorMessage(e))
      }
    } finally {
      setRunsLoading(false)
    }
  }, [runsFor])

  useEffect(() => {
    void loadRuns()
  }, [loadRuns])

  const reconcile = async (apply: boolean) => {
    setReconBusy(true)
    setReconErr(null)
    setApplied(null)
    try {
      const res = await adminApi.reconcileSupabase(apply)
      setReport(res)
      if (apply) setApplied(`Applied. ${res.drift.filter((d) => d.fixed).length} of ${res.drift.length} drifted users fixed.`)
      setApplyOpen(false)
    } catch (e) {
      setReconErr(adminErrorMessage(e))
      setApplyOpen(false)
    } finally {
      setReconBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">Seat usage by tenant</CardTitle>
              <CardDescription>{total} seats in use across the platform (active members plus pending invites).</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading} className="gap-1.5">
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} /> Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <InlineAlert message={err} onDismiss={() => setErr(null)} />
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tenant</TableHead>
                  <TableHead className="text-right">Used</TableHead>
                  <TableHead className="text-right">Limit</TableHead>
                  <TableHead className="text-right">Pending</TableHead>
                  <TableHead className="text-right">Seat price</TableHead>
                  <TableHead>Billing</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => {
                  const over = r.seat_limit != null && r.seats_used > r.seat_limit
                  const full = r.seat_limit != null && r.seats_used === r.seat_limit
                  return (
                    <TableRow key={r.tenant_id} className={cn(over && "bg-red-500/10")}>
                      <TableCell className="font-medium">{r.name}</TableCell>
                      <TableCell className={cn("text-right", over && "font-semibold text-red-400")}>{r.seats_used}</TableCell>
                      <TableCell className="text-right">{r.seat_limit ?? "unlimited"}</TableCell>
                      <TableCell className="text-right">{r.pending_invites}</TableCell>
                      <TableCell className="text-right">{r.seat_price ?? "-"}</TableCell>
                      <TableCell>
                        {over ? (
                          <Badge variant="outline" className="border-red-500/40 text-red-400">over limit</Badge>
                        ) : full ? (
                          <Badge variant="outline" className="border-amber-500/40 text-amber-400">full</Badge>
                        ) : (
                          <Badge variant="outline">{r.billing_status || "active"}</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
                {rows.length === 0 && !loading && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-sm text-muted-foreground">No tenants.</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle className="text-base">Seat billing runs</CardTitle>
              <CardDescription>Monthly peak-seat invoicing runs from the billing service.</CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <select className={cn(NATIVE_SELECT, "min-w-48")} value={runsFor} onChange={(e) => setRunsTenant(e.target.value)} aria-label="Tenant for billing runs">
                {(rows.length ? rows.map((r) => ({ id: r.tenant_id, name: r.name })) : tenants).map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
              <Button variant="outline" size="sm" onClick={() => void loadRuns()} disabled={runsLoading} className="gap-1.5">
                <RefreshCw className={cn("h-3.5 w-3.5", runsLoading && "animate-spin")} />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {billingDown && (
            <div role="status" className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-400">
              Billing service not connected. Seat usage above is live from the admin service; billing runs will appear here once the billing service is running.
            </div>
          )}
          <InlineAlert message={runsErr} onDismiss={() => setRunsErr(null)} />
          {runs && runs.length === 0 && <p className="text-sm text-muted-foreground">No billing runs for this tenant yet.</p>}
          {runs && runs.length > 0 && (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Period</TableHead>
                    <TableHead className="text-right">Peak seats</TableHead>
                    <TableHead className="text-right">Unit price</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell>{r.period_start} to {r.period_end}</TableCell>
                      <TableCell className="text-right">{r.peak_seats}</TableCell>
                      <TableCell className="text-right">{r.unit_price}</TableCell>
                      <TableCell className="text-right">{r.amount}</TableCell>
                      <TableCell><Badge variant="outline">{r.status}</Badge></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Supabase role sync</CardTitle>
          <CardDescription>The admin database is the source of truth. Compare it with each user&apos;s Supabase app_metadata (roles and tenant).</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => void reconcile(false)} disabled={reconBusy} className="gap-1.5">
              {reconBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              Reconcile Supabase roles (dry run)
            </Button>
            {report && report.dry_run && report.drift.length > 0 && (
              <Button size="sm" variant="destructive" onClick={() => setApplyOpen(true)} disabled={reconBusy}>
                Apply {report.drift.length} fix{report.drift.length === 1 ? "" : "es"}...
              </Button>
            )}
          </div>
          <InlineAlert message={reconErr} onDismiss={() => setReconErr(null)} />
          <InlineNotice message={applied} onDismiss={() => setApplied(null)} />
          {report && (
            <div className="space-y-2 text-sm">
              <p>
                {report.dry_run ? "Dry run: nothing was changed. " : ""}
                {report.db_users} database users, {report.supabase_users} Supabase users, {report.in_sync} in sync, {report.drift.length} drifted, {report.orphans_in_supabase_only.length} only in Supabase.
              </p>
              {report.drift.length > 0 && (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>User</TableHead>
                        <TableHead>Issue</TableHead>
                        <TableHead>Admin DB</TableHead>
                        <TableHead>Supabase</TableHead>
                        <TableHead>Fixed</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {report.drift.map((d) => (
                        <TableRow key={d.user_id}>
                          <TableCell>{d.email}</TableCell>
                          <TableCell className="text-xs">{d.issue || "roles/tenant differ"}</TableCell>
                          <TableCell><code className="text-xs">{JSON.stringify(d.db ?? null)}</code></TableCell>
                          <TableCell><code className="text-xs">{JSON.stringify(d.supabase ?? null)}</code></TableCell>
                          <TableCell>{d.fixed ? "yes" : "no"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
              {report.orphans_in_supabase_only.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Only in Supabase (no admin DB user; left alone, they keep working from app_metadata):</p>
                  <ul className="mt-1 list-disc pl-5 text-xs text-muted-foreground">
                    {report.orphans_in_supabase_only.map((o) => (
                      <li key={o.supabase_id}>{o.email} {o.app_metadata_roles?.length ? `(${o.app_metadata_roles.join(", ")})` : ""}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={applyOpen} onOpenChange={setApplyOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Apply role sync?</DialogTitle>
            <DialogDescription>
              This overwrites Supabase app_metadata (tenant and roles) for {report?.drift.length ?? 0} user(s) with what the admin database holds, and can remove
              roles a user currently has. Affected users are signed out of stale tokens on their next refresh. Review the drift table first.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApplyOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={() => void reconcile(true)} disabled={reconBusy}>{reconBusy ? "Applying..." : "Apply changes"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
