"use client"

import { fetchOps } from "@/lib/ops-api"
import type { Loadable } from "@/lib/service-state"
import type { DealRow } from "@/lib/overview-derive"

/**
 * Status-aware loaders for the Overview page. Every loader returns a
 * Loadable so the UI can tell loading / ready (real zeros OK) / service not
 * running / error apart. Reuse `useOps` from ops-api to run them.
 * Identity is attached to /api/* and /svc/* by AuthFetchInit.
 */

export const loadOverviewDeals = () => fetchOps<DealRow[]>("/api/sales/deals", { timeoutMs: 12_000 })

/** page_size=1: only `total` is needed. */
export const loadCrmCustomerTotal = () =>
  fetchOps<{ total?: number; items?: unknown[] } | unknown[]>("/svc/crm/customers?page=1&page_size=1")

export const loadOverviewCampaigns = () => fetchOps<Array<{ status?: string }>>("/svc/marketing/campaigns?limit=200")

export const loadOverviewEmployees = () => fetchOps<Array<{ status?: string }>>("/svc/hr/employees")

export const loadCcSessions = () =>
  fetchOps<unknown>("/svc/call-center/sessions", { rewriteProxy: true })

export const loadCcQueues = () =>
  fetchOps<unknown>("/svc/call-center/queues", { rewriteProxy: true })
