"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams } from "next/navigation"
import {
  User,
  CreditCard,
  Headphones,
  TrendingUp,
  Loader2,
  AlertCircle,
  ArrowLeft,
} from "lucide-react"
import Link from "next/link"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { loadCustomer360, loadCustomer360Section } from "@/lib/crm-api"
import { formatTier, read360Meta, formatReliability, formatRecommendation } from "@/lib/crm-derive"
import { describeLoadable } from "@/lib/service-state"

// ─── Types ───────────────────────────────────────────────────────────────────

interface CustomerBasicInfo {
  id: string
  first_name: string
  last_name: string
  email: string | null
  phone?: string | null
  status: string
  account_number?: string | null
  tier?: string
}

type TabId = "details" | "cx" | "crm" | "cvm"

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getStatusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  const s = status.toLowerCase()
  if (s === "active") return "default"
  if (s === "inactive" || s === "suspended") return "secondary"
  if (s === "churned" || s === "cancelled") return "destructive"
  return "outline"
}

function getTierVariant(tier: string | undefined): "default" | "secondary" | "destructive" | "outline" {
  const t = (tier ?? "").toUpperCase()
  if (t === "PLATINUM") return "default"
  if (t === "GOLD") return "secondary"
  if (t === "SILVER") return "outline"
  return "outline"
}

// ─── Tab placeholder panels ─────────────────────────────────────────────────

function SectionTab({ customerId, section }: { customerId: string; section: TabId }) {
  const [data, setData] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setData(null)
    setError(null)
    loadCustomer360Section(customerId, section).then((result) => {
      if (cancelled) return
      if (result.state === "ready") setData(result.data)
      else setError(describeLoadable(result, `CRM ${section}`)?.detail ?? "Section unavailable")
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [customerId, section, attempt])
  if (loading) return <TabLoader />
  if (error) return <div><TabError message={error} /><button className="mt-3 text-sm text-primary" onClick={() => setAttempt((n) => n + 1)}>Retry section</button></div>
  const meta = read360Meta(data)
  const cvm = data as { churn_prediction?: unknown; financial_summary?: { payment_reliability_pct?: number | null }; cvm_summary?: { customer_tier?: string; recommended_action?: string } } | null
  return <Card className="border-border bg-card"><CardContent className="pt-6">
    {meta.partial && <div role="alert" className="mb-3 text-sm text-destructive">Some sections are unavailable: {Object.entries(meta.sectionErrors).map(([name, message]) => `${name}: ${message}`).join("; ")}</div>}
    {section === "cvm" && <div className="mb-3 text-sm text-muted-foreground">
      <p>Tier: {formatTier(cvm?.cvm_summary?.customer_tier)}</p>
      <p>Payment reliability: {formatReliability(cvm?.financial_summary?.payment_reliability_pct)}</p>
      <p>Recommendation: {formatRecommendation(cvm?.cvm_summary?.recommended_action)}</p>
      {!cvm?.churn_prediction && <p>Churn prediction: Not assessed</p>}
    </div>}
    <pre className="max-h-96 overflow-auto rounded-lg bg-secondary/50 p-4 text-xs text-foreground">{JSON.stringify(data, null, 2)}</pre>
  </CardContent></Card>
}

function TabLoader() {
  return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      <span className="ml-2 text-sm text-muted-foreground">Loading…</span>
    </div>
  )
}

function TabError({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
      <AlertCircle className="h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

// ─── Customer Header ─────────────────────────────────────────────────────────

function CustomerHeader({ customer }: { customer: CustomerBasicInfo }) {
  const fullName = `${customer.first_name} ${customer.last_name}`.trim()
  const tier = formatTier(customer.tier)

  return (
    <Card className="border-border bg-card">
      <CardContent className="pt-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          {/* Left: identity */}
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-secondary">
              <User className="h-6 w-6 text-muted-foreground" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-foreground">{fullName}</h2>
              <p className="text-sm text-muted-foreground">{customer.email}</p>
            </div>
          </div>

          {/* Right: badges */}
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={getStatusVariant(customer.status)}>
              {customer.status}
            </Badge>
            <Badge variant={getTierVariant(customer.tier)}>
              {tier}
            </Badge>
            <Badge variant="outline" className="font-mono text-xs">
              #{customer.account_number}
            </Badge>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function Customer360Page() {
  const params = useParams()
  const customerId = params.customer_id as string

  const [customer, setCustomer] = useState<CustomerBasicInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Track which tabs have been activated (lazy-load gate)
  const [activeTab, setActiveTab] = useState<TabId>("details")
  const [headerAttempt, setHeaderAttempt] = useState(0)
  const [activatedTabs, setActivatedTabs] = useState<Set<TabId>>(new Set(["details"]))

  const handleTabChange = useCallback((value: string) => {
    setActiveTab(value as TabId)
    setActivatedTabs((prev) => {
      const next = new Set(prev)
      next.add(value as TabId)
      return next
    })
  }, [])

  // CRM enforces tenant scope and redaction for the header.
  useEffect(() => {
    let cancelled = false

    async function loadCustomer() {
      setLoading(true)
      setError(null)
      setCustomer(null)
      try {
        const result = await loadCustomer360(customerId)
        if (!cancelled) {
          if (result.state === "ready") setCustomer(result.data)
          else setError(describeLoadable(result, "CRM customer")?.detail ?? "Customer unavailable")
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load customer")
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    if (customerId) loadCustomer()
    return () => { cancelled = true }
  }, [customerId, headerAttempt])

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">Loading customer…</span>
      </div>
    )
  }

  if (error || !customer) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">
          {error ?? "Customer not found"}
        </p>
        <button className="text-sm text-primary" onClick={() => setHeaderAttempt((n) => n + 1)}>Retry customer</button>
        <Link
          href="/dashboard"
          className="mt-2 inline-flex items-center gap-1 text-sm text-primary hover:underline"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-4 sm:p-6">
      {/* Back link */}
      <Link
        href="/dashboard"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Dashboard
      </Link>

      {/* Customer header */}
      <CustomerHeader customer={customer} />

      {/* Tab bar */}
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="details" className="gap-2">
            <User className="h-4 w-4" />
            <span className="hidden sm:inline">Customer Details</span>
            <span className="sm:hidden">Details</span>
          </TabsTrigger>
          <TabsTrigger value="cx" className="gap-2">
            <Headphones className="h-4 w-4" />
            <span className="hidden sm:inline">CX</span>
            <span className="sm:hidden">CX</span>
          </TabsTrigger>
          <TabsTrigger value="crm" className="gap-2">
            <CreditCard className="h-4 w-4" />
            <span className="hidden sm:inline">CRM</span>
            <span className="sm:hidden">CRM</span>
          </TabsTrigger>
          <TabsTrigger value="cvm" className="gap-2">
            <TrendingUp className="h-4 w-4" />
            <span className="hidden sm:inline">CVM</span>
            <span className="sm:hidden">CVM</span>
          </TabsTrigger>
        </TabsList>

        <div className="mt-4">
          {activatedTabs.has("details") && (
            <TabsContent value="details">
              <SectionTab key={customerId} customerId={customerId} section="details" />
            </TabsContent>
          )}
          {activatedTabs.has("cx") && (
            <TabsContent value="cx">
              <SectionTab key={customerId} customerId={customerId} section="cx" />
            </TabsContent>
          )}
          {activatedTabs.has("crm") && (
            <TabsContent value="crm">
              <SectionTab key={customerId} customerId={customerId} section="crm" />
            </TabsContent>
          )}
          {activatedTabs.has("cvm") && (
            <TabsContent value="cvm">
              <SectionTab key={customerId} customerId={customerId} section="cvm" />
            </TabsContent>
          )}
        </div>
      </Tabs>
    </div>
  )
}
