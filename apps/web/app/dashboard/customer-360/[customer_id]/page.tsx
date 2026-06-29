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
import { supabase } from "@/lib/supabase/client"

// ─── Types ───────────────────────────────────────────────────────────────────

interface CustomerBasicInfo {
  id: string
  first_name: string
  last_name: string
  email: string
  phone: string | null
  status: string
  account_number: string
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

function formatTier(tier: string | undefined): string {
  if (!tier) return "BRONZE"
  return tier.toUpperCase()
}

// ─── Tab placeholder panels ─────────────────────────────────────────────────

function DetailsTab({ customerId }: { customerId: string }) {
  const [data, setData] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetch(`/svc/crm/customers/${customerId}/360/details`, { cache: "no-store" })
        if (!res.ok) throw new Error(`Failed: ${res.status}`)
        const json = await res.json()
        if (!cancelled) setData(json)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load details")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [customerId])

  if (loading) return <TabLoader />
  if (error) return <TabError message={error} />
  return (
    <Card className="border-border bg-card">
      <CardContent className="pt-6">
        <p className="text-sm text-muted-foreground">
          Customer Details data loaded. Raw payload:
        </p>
        <pre className="mt-3 max-h-96 overflow-auto rounded-lg bg-secondary/50 p-4 text-xs text-foreground">
          {JSON.stringify(data, null, 2)}
        </pre>
      </CardContent>
    </Card>
  )
}

function CXTab({ customerId }: { customerId: string }) {
  const [data, setData] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetch(`/svc/crm/customers/${customerId}/360/cx`, { cache: "no-store" })
        if (!res.ok) throw new Error(`Failed: ${res.status}`)
        const json = await res.json()
        if (!cancelled) setData(json)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load CX data")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [customerId])

  if (loading) return <TabLoader />
  if (error) return <TabError message={error} />
  return (
    <Card className="border-border bg-card">
      <CardContent className="pt-6">
        <p className="text-sm text-muted-foreground">Customer Experience data loaded.</p>
        <pre className="mt-3 max-h-96 overflow-auto rounded-lg bg-secondary/50 p-4 text-xs text-foreground">
          {JSON.stringify(data, null, 2)}
        </pre>
      </CardContent>
    </Card>
  )
}

function CRMTab({ customerId }: { customerId: string }) {
  const [data, setData] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetch(`/svc/crm/customers/${customerId}/360/crm`, { cache: "no-store" })
        if (!res.ok) throw new Error(`Failed: ${res.status}`)
        const json = await res.json()
        if (!cancelled) setData(json)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load CRM data")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [customerId])

  if (loading) return <TabLoader />
  if (error) return <TabError message={error} />
  return (
    <Card className="border-border bg-card">
      <CardContent className="pt-6">
        <p className="text-sm text-muted-foreground">CRM / Sales Pipeline data loaded.</p>
        <pre className="mt-3 max-h-96 overflow-auto rounded-lg bg-secondary/50 p-4 text-xs text-foreground">
          {JSON.stringify(data, null, 2)}
        </pre>
      </CardContent>
    </Card>
  )
}

function CVMTab({ customerId }: { customerId: string }) {
  const [data, setData] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetch(`/svc/crm/customers/${customerId}/360/cvm`, { cache: "no-store" })
        if (!res.ok) throw new Error(`Failed: ${res.status}`)
        const json = await res.json()
        if (!cancelled) setData(json)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load CVM data")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [customerId])

  if (loading) return <TabLoader />
  if (error) return <TabError message={error} />
  return (
    <Card className="border-border bg-card">
      <CardContent className="pt-6">
        <p className="text-sm text-muted-foreground">Customer Value Management data loaded.</p>
        <pre className="mt-3 max-h-96 overflow-auto rounded-lg bg-secondary/50 p-4 text-xs text-foreground">
          {JSON.stringify(data, null, 2)}
        </pre>
      </CardContent>
    </Card>
  )
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
  const [activatedTabs, setActivatedTabs] = useState<Set<TabId>>(new Set(["details"]))

  const handleTabChange = useCallback((value: string) => {
    setActivatedTabs((prev) => {
      const next = new Set(prev)
      next.add(value as TabId)
      return next
    })
  }, [])

  // Fetch customer basic info from Supabase
  useEffect(() => {
    let cancelled = false

    async function loadCustomer() {
      try {
        const { data, error: sbError } = await supabase
          .from("customers")
          .select("id, first_name, last_name, email, phone, status, account_number")
          .eq("id", customerId)
          .single()

        if (sbError) throw sbError
        if (!cancelled && data) {
          setCustomer(data as CustomerBasicInfo)
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
  }, [customerId])

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
      <Tabs defaultValue="details" value="details" onValueChange={handleTabChange}>
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
              <DetailsTab customerId={customerId} />
            </TabsContent>
          )}
          {activatedTabs.has("cx") && (
            <TabsContent value="cx">
              <CXTab customerId={customerId} />
            </TabsContent>
          )}
          {activatedTabs.has("crm") && (
            <TabsContent value="crm">
              <CRMTab customerId={customerId} />
            </TabsContent>
          )}
          {activatedTabs.has("cvm") && (
            <TabsContent value="cvm">
              <CVMTab customerId={customerId} />
            </TabsContent>
          )}
        </div>
      </Tabs>
    </div>
  )
}
