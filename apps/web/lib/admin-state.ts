/**
 * Pure helpers for the Admin module: who may see/request which section, how a
 * failed request maps to an honest UI state, and small view-model mappers.
 * No React / browser imports so it can be unit-tested with node.
 *
 * UI gating only: services/admin enforces every action (403 is always possible).
 */

import type { Loadable } from "./service-state"
// .ts extension lets node --test load this file; the bundler resolves it as normal.
// @ts-ignore TS5097: extension imports are not enabled in tsconfig (noEmit, bundler resolution)
import { loadableFromStatus } from "./service-state.ts"

export type AdminSection = "tenants" | "modules" | "seats" | "team" | "users" | "audit" | "commission" | "protocols"

export interface AdminVisibility {
  platform: boolean
  /** platform_admin, owner or org_admin: mirrors services/admin iam.require_tenant_admin. */
  tenantAdmin: boolean
}

export function adminVisibility(roles: readonly string[] | null | undefined): AdminVisibility {
  const r = roles ?? []
  const platform = r.includes("platform_admin")
  return { platform, tenantAdmin: platform || r.includes("owner") || r.includes("org_admin") }
}

/** Whether the actor should even be sent the request(s) behind a section. */
export function canRequestSection(roles: readonly string[] | null | undefined, section: AdminSection): boolean {
  const v = adminVisibility(roles)
  switch (section) {
    case "tenants":
    case "seats":
      return v.platform
    case "modules":
      return true // own-tenant entitlements are read-only for everyone
    default:
      return v.tenantAdmin // team, users, audit, commission, protocols
  }
}

/** Role named in the "Not permitted" state. */
export function requiredRoleLabel(section: AdminSection): string {
  return section === "tenants" || section === "seats" ? "platform_admin" : "org_admin or owner"
}

export function deniedState(): Loadable<never> {
  return { state: "denied", status: 403 }
}

/** HTTP status from an error thrown by the admin / orchestrator clients, or null for network failure / timeout. */
export function statusFromError(err: unknown): number | null {
  const direct = (err as { status?: unknown } | null)?.status
  if (typeof direct === "number" && direct > 0) return direct
  const name = (err as { name?: string } | null)?.name
  if (name === "TimeoutError" || name === "AbortError" || err instanceof TypeError) return null
  const m = /\b([45]\d{2})\b/.exec(String((err as { message?: unknown } | null)?.message ?? ""))
  return m ? Number(m[1]) : null
}

/**
 * Failure -> Loadable. Network failure / 502-504 = "Service not running", 401/403 = "Not permitted",
 * anything else = error. The server's own text is kept only for 4xx (never raw 5xx bodies).
 */
export function loadableFromError<T>(err: unknown, messageOf?: (e: unknown) => string): Loadable<T> {
  const status = statusFromError(err)
  const message = status !== null && status < 500 && messageOf ? messageOf(err) : undefined
  return loadableFromStatus<T>(status, undefined, message)
}

/** Seat-state of a member's Supabase sync, from the server's status code (never raw errors). */
export function syncBadge(status: unknown): { label: string; tone: "pending" | "failed" } | null {
  if (typeof status !== "string") return null
  const s = status.toLowerCase()
  if (s === "pending" || s === "queued" || s === "syncing") return { label: "Sync pending", tone: "pending" }
  if (s === "failed" || s === "error") return { label: "Sync failed - retry", tone: "failed" }
  return null // synced / ok / unknown: nothing to flag
}

/** Info text when the server says active sessions could not be revoked on deactivate. */
export function deactivateNotice(res: { sessions_revoked?: boolean } | null | undefined): string | null {
  return res && res.sessions_revoked === false ? "Access ends within about an hour (token expiry)." : null
}

const SYSTEM_ROLE_NAMES = new Set([
  "owner",
  "org_admin",
  "org_user",
  "manager",
  "hr_manager",
  "platform_admin",
  "admin",
  "tenant_admin",
  "super_admin",
])

/** System roles are immutable via the API (409); the UI must not offer edit/delete on them. */
export function isSystemRole(role: { name?: string; is_system?: boolean | null } | null | undefined): boolean {
  if (!role) return false
  if (role.is_system === true) return true
  return !!role.name && SYSTEM_ROLE_NAMES.has(role.name)
}

export function canEditRole(role: { name?: string; is_system?: boolean | null } | null | undefined): boolean {
  return !!role && !isSystemRole(role)
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** User id or e-mail -> user id, using the users the actor can already see. Null when not resolvable. */
export function resolveUserId(input: string, users: ReadonlyArray<{ id: string; email: string }>): string | null {
  const v = input.trim()
  if (!v) return null
  if (UUID_RE.test(v)) return v.toLowerCase()
  if (v.includes("@")) {
    const hit = users.find((u) => u.email.toLowerCase() === v.toLowerCase())
    return hit ? hit.id : null
  }
  return null
}

export interface TierInput {
  name: string
  minDeals: string | number
  maxDeals: string
  rate: string
}

/** Client-side validation for a commission tier. Returns an error message, or null when valid. */
export function validateTier(t: TierInput): string | null {
  if (!t.name.trim()) return "Tier name is required"
  const min = Number(t.minDeals)
  if (!Number.isInteger(min) || min < 0) return "Min deals must be a whole number of 0 or more"
  if (t.maxDeals.trim()) {
    const max = Number(t.maxDeals)
    if (!Number.isInteger(max) || max < min) return "Max deals must be a whole number not below min deals"
  }
  if (!t.rate.trim()) return "Commission rate is required"
  const rate = Number(t.rate)
  if (!Number.isFinite(rate) || rate < 0 || rate > 100) return "Commission rate must be between 0 and 100"
  return null
}

/** Nothing in the section is "present" unless the request actually succeeded. */
export function readyData<T>(l: Loadable<T[]>): T[] {
  return l.state === "ready" ? l.data : []
}
