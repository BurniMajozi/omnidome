"use client"

import { useEffect, useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  User,
  Mail,
  Phone,
  CreditCard,
  Building2,
  Home,
  MapPin,
  Receipt,
  Package,
  Clock,
  ShieldCheck,
  ShieldX,
  ShieldAlert,
  Banknote,
  Smartphone,
  Globe,
  Hash,
  Calendar,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Loader2,
  RefreshCw,
  ChevronRight,
  Wallet,
  FileText,
  ArrowRightLeft,
} from "lucide-react"
import { cn } from "@/lib/utils"

// ─── Types ───────────────────────────────────────────────────────────────────

interface CustomerIdentity {
  id: string
  fullName: string
  email: string
  phone: string
  idNumber: string
  ricaStatus: "verified" | "pending" | "expired" | "unverified"
  customerType: "individual" | "corporate"
  avatarUrl?: string
  dateOfBirth?: string
  gender?: string
}

interface CompanyAffiliation {
  companyName: string
  registrationNumber: string
  role: string
  department?: string
  startDate: string
  status: "active" | "inactive"
}

interface PropertyRecord {
  id: string
  address: string
  type: "residential" | "commercial" | "industrial"
  status: "active" | "inactive" | "pending"
  purchasedDate: string
  value: number
}

interface PropertyAccount {
  id: string
  propertyId: string
  accountNumber: string
  serviceType: string
  status: "active" | "suspended" | "pending" | "closed"
  monthlyFee: number
  balance: number
}

interface ServiceAddress {
  id: string
  address: string
  type: "installation" | "billing" | "service"
  status: "active" | "inactive"
  services: string[]
}

interface BillingAccountSummary {
  accountNumber: string
  status: "active" | "suspended" | "overdue" | "closed"
  currentBalance: number
  lastPaymentDate: string
  lastPaymentAmount: number
  nextBillingDate: string
  paymentMethod: string
  autoPayEnabled: boolean
}

interface Subscription {
  id: string
  planName: string
  serviceType: string
  status: "active" | "suspended" | "cancelled" | "pending"
  startDate: string
  endDate?: string
  monthlyRecurring: number
  nextBillingDate: string
}

interface PaymentMethod {
  id: string
  type: "credit_card" | "debit_card" | "bank_account" | "eft"
  displayName: string
  last4: string
  expiryDate?: string
  isDefault: boolean
  status: "active" | "expired" | "pending"
}

interface HandoverRecord {
  id: string
  date: string
  fromAgent: string
  toAgent: string
  reason: string
  status: "completed" | "pending" | "cancelled"
  notes?: string
}

interface Customer360Details {
  identity: CustomerIdentity
  companyAffiliation?: CompanyAffiliation
  properties: PropertyRecord[]
  propertyAccounts: PropertyAccount[]
  serviceAddresses: ServiceAddress[]
  billingAccount: BillingAccountSummary
  subscriptions: Subscription[]
  paymentMethods: PaymentMethod[]
  handoverHistory: HandoverRecord[]
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatCurrency(value: number): string {
  return `R ${value.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatDate(dateStr: string): string {
  if (!dateStr) return "—"
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString("en-ZA", { year: "numeric", month: "short", day: "numeric" })
}

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "active":
    case "verified":
    case "completed":
      return (
        <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
          <CheckCircle2 className="mr-1 h-3 w-3" />
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </Badge>
      )
    case "suspended":
    case "cancelled":
    case "expired":
    case "closed":
      return (
        <Badge className="bg-red-500/15 text-red-400 border-red-500/30">
          <XCircle className="mr-1 h-3 w-3" />
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </Badge>
      )
    case "pending":
    case "unverified":
      return (
        <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30">
          <AlertCircle className="mr-1 h-3 w-3" />
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </Badge>
      )
    case "inactive":
    case "overdue":
      return (
        <Badge className="bg-orange-500/15 text-orange-400 border-orange-500/30">
          <AlertCircle className="mr-1 h-3 w-3" />
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </Badge>
      )
    default:
      return (
        <Badge variant="secondary">
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </Badge>
      )
  }
}

function RicaBadge({ status }: { status: CustomerIdentity["ricaStatus"] }) {
  switch (status) {
    case "verified":
      return (
        <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
          <ShieldCheck className="mr-1 h-3 w-3" />
          RICA Verified
        </Badge>
      )
    case "pending":
      return (
        <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30">
          <ShieldAlert className="mr-1 h-3 w-3" />
          RICA Pending
        </Badge>
      )
    case "expired":
      return (
        <Badge className="bg-red-500/15 text-red-400 border-red-500/30">
          <ShieldX className="mr-1 h-3 w-3" />
          RICA Expired
        </Badge>
      )
    default:
      return (
        <Badge className="bg-slate-500/15 text-slate-400 border-slate-500/30">
          <ShieldX className="mr-1 h-3 w-3" />
          Unverified
        </Badge>
      )
  }
}

function InfoRow({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex items-start gap-3 py-2">
      <div className="mt-0.5 rounded-md bg-primary/10 p-1.5">
        <Icon className="h-3.5 w-3.5 text-primary" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-sm font-medium text-foreground truncate">{value || "—"}</p>
      </div>
    </div>
  )
}

function SectionCard({
  title,
  icon: Icon,
  children,
  className,
  action,
}: {
  title: string
  icon: React.ElementType
  children: React.ReactNode
  className?: string
  action?: React.ReactNode
}) {
  return (
    <Card className={cn("border-border bg-card", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base font-semibold text-foreground">
            <div className="rounded-lg bg-primary/10 p-1.5">
              <Icon className="h-4 w-4 text-primary" />
            </div>
            {title}
          </CardTitle>
          {action}
        </div>
      </CardHeader>
      <CardContent className="pt-0">{children}</CardContent>
    </Card>
  )
}

// ─── Skeleton ────────────────────────────────────────────────────────────────

function SkeletonLoader() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="h-56 rounded-xl border border-border bg-card" />
        <div className="h-56 rounded-xl border border-border bg-card" />
      </div>
      <div className="h-48 rounded-xl border border-border bg-card" />
      <div className="h-64 rounded-xl border border-border bg-card" />
    </div>
  )
}

// ─── Empty State ─────────────────────────────────────────────────────────────

function EmptyState({ message = "No records found" }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <div className="rounded-full bg-muted/50 p-3 mb-3">
        <FileText className="h-5 w-5 text-muted-foreground" />
      </div>
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  )
}

// ─── Main Component ──────────────────────────────────────────────────────────

interface CustomerDetailsTabProps {
  customerId: string
}

export function CustomerDetailsTab({ customerId }: CustomerDetailsTabProps) {
  const [data, setData] = useState<Customer360Details | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchDetails = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`/api/crm/customers/${encodeURIComponent(customerId)}/360/details`, {
        cache: "no-store",
      })
      if (!response.ok) {
        throw new Error(`Failed to fetch customer details: ${response.status}`)
      }
      const json = await response.json()
      setData(json.data ?? json)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load customer details")
    } finally {
      setLoading(false)
    }
  }, [customerId])

  useEffect(() => {
    fetchDetails()
  }, [fetchDetails])

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">Loading customer details…</span>
        </div>
        <SkeletonLoader />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="rounded-full bg-destructive/10 p-4 mb-4">
          <AlertCircle className="h-6 w-6 text-destructive" />
        </div>
        <h3 className="text-lg font-semibold text-foreground mb-1">Failed to load details</h3>
        <p className="text-sm text-muted-foreground mb-4 max-w-md">{error}</p>
        <button
          onClick={fetchDetails}
          className="inline-flex items-center gap-2 rounded-lg border border-border bg-secondary px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-secondary/80"
        >
          <RefreshCw className="h-4 w-4" />
          Retry
        </button>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="rounded-full bg-muted/50 p-4 mb-4">
          <User className="h-6 w-6 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold text-foreground mb-1">No customer data</h3>
        <p className="text-sm text-muted-foreground">No details found for this customer.</p>
      </div>
    )
  }

  const { identity, companyAffiliation, properties, propertyAccounts, serviceAddresses, billingAccount, subscriptions, paymentMethods, handoverHistory } = data

  return (
    <div className="space-y-6">
      {/* ── Identity + Company ─────────────────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Customer Identity Card */}
        <SectionCard title="Customer Identity" icon={User}>
          <div className="flex items-start gap-4 mb-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-primary/10 text-lg font-bold text-primary">
              {identity.fullName
                .split(" ")
                .map((n) => n[0])
                .join("")
                .slice(0, 2)
                .toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="text-lg font-semibold text-foreground truncate">{identity.fullName}</h3>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                <Badge variant="outline" className="text-xs">
                  {identity.customerType === "corporate" ? "Corporate" : "Individual"}
                </Badge>
                <RicaBadge status={identity.ricaStatus} />
              </div>
            </div>
          </div>
          <div className="divide-y divide-border/50">
            <InfoRow icon={Mail} label="Email" value={identity.email} />
            <InfoRow icon={Phone} label="Phone" value={identity.phone} />
            <InfoRow icon={CreditCard} label="ID Number" value={identity.idNumber} />
            <InfoRow icon={Hash} label="Customer ID" value={identity.id} />
            {identity.dateOfBirth && (
              <InfoRow icon={Calendar} label="Date of Birth" value={formatDate(identity.dateOfBirth)} />
            )}
            {identity.gender && (
              <InfoRow icon={User} label="Gender" value={identity.gender} />
            )}
          </div>
        </SectionCard>

        {/* Company Affiliation Card */}
        <SectionCard
          title="Company Affiliation"
          icon={Building2}
          className={cn(!companyAffiliation && "opacity-60")}
        >
          {companyAffiliation ? (
            <>
              <div className="flex items-start gap-3 mb-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                  <Building2 className="h-5 w-5 text-primary" />
                </div>
                <div className="min-w-0 flex-1">
                  <h4 className="font-semibold text-foreground truncate">{companyAffiliation.companyName}</h4>
                  <p className="text-xs text-muted-foreground">Reg: {companyAffiliation.registrationNumber}</p>
                </div>
                <StatusBadge status={companyAffiliation.status} />
              </div>
              <div className="divide-y divide-border/50">
                <InfoRow icon={User} label="Role" value={companyAffiliation.role} />
                {companyAffiliation.department && (
                  <InfoRow icon={Building2} label="Department" value={companyAffiliation.department} />
                )}
                <InfoRow icon={Calendar} label="Start Date" value={formatDate(companyAffiliation.startDate)} />
              </div>
            </>
          ) : (
            <EmptyState message="No company affiliation on record" />
          )}
        </SectionCard>
      </div>

      {/* ── Properties + Property Accounts ────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Properties Table */}
        <SectionCard title="Properties" icon={Home}>
          {properties.length === 0 ? (
            <EmptyState message="No properties on record" />
          ) : (
            <ScrollArea className="max-h-72">
              <div className="space-y-2">
                {properties.map((property) => (
                  <div
                    key={property.id}
                    className="rounded-lg border border-border bg-secondary/20 p-3 transition-colors hover:border-primary/30"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-foreground truncate">{property.address}</p>
                        <div className="flex flex-wrap items-center gap-2 mt-1">
                          <Badge variant="outline" className="text-xs capitalize">
                            {property.type}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            Purchased {formatDate(property.purchasedDate)}
                          </span>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-sm font-semibold text-foreground">{formatCurrency(property.value)}</p>
                        <div className="mt-1">
                          <StatusBadge status={property.status} />
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </SectionCard>

        {/* Property Accounts */}
        <SectionCard title="Property Accounts" icon={Receipt}>
          {propertyAccounts.length === 0 ? (
            <EmptyState message="No property accounts on record" />
          ) : (
            <ScrollArea className="max-h-72">
              <div className="space-y-2">
                {propertyAccounts.map((account) => (
                  <div
                    key={account.id}
                    className="rounded-lg border border-border bg-secondary/20 p-3 transition-colors hover:border-primary/30"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-foreground">{account.serviceType}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">Acc: {account.accountNumber}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-sm font-semibold text-foreground">{formatCurrency(account.monthlyFee)}/mo</p>
                        <p className={cn("text-xs mt-0.5", account.balance > 0 ? "text-amber-400" : "text-emerald-400")}>
                          Bal: {formatCurrency(account.balance)}
                        </p>
                        <div className="mt-1">
                          <StatusBadge status={account.status} />
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </SectionCard>
      </div>

      {/* ── Service Addresses ─────────────────────────────────────────── */}
      <SectionCard title="Service Addresses" icon={MapPin}>
        {serviceAddresses.length === 0 ? (
          <EmptyState message="No service addresses on record" />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {serviceAddresses.map((addr) => (
              <div
                key={addr.id}
                className="rounded-lg border border-border bg-secondary/20 p-3 transition-colors hover:border-primary/30"
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <MapPin className="h-4 w-4 text-primary shrink-0" />
                    <Badge variant="outline" className="text-xs capitalize">
                      {addr.type}
                    </Badge>
                  </div>
                  <StatusBadge status={addr.status} />
                </div>
                <p className="text-sm text-foreground mb-2">{addr.address}</p>
                <div className="flex flex-wrap gap-1">
                  {addr.services.map((svc, idx) => (
                    <Badge key={idx} variant="secondary" className="text-xs">
                      {svc}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      {/* ── Billing Account Summary ───────────────────────────────────── */}
      <SectionCard title="Billing Account Summary" icon={Banknote}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div className="rounded-lg border border-border bg-secondary/20 p-4">
            <p className="text-xs text-muted-foreground mb-1">Account Number</p>
            <p className="text-sm font-semibold text-foreground">{billingAccount.accountNumber}</p>
            <div className="mt-2">
              <StatusBadge status={billingAccount.status} />
            </div>
          </div>
          <div className="rounded-lg border border-border bg-secondary/20 p-4">
            <p className="text-xs text-muted-foreground mb-1">Current Balance</p>
            <p className={cn("text-xl font-bold", billingAccount.currentBalance > 0 ? "text-amber-400" : "text-emerald-400")}>
              {formatCurrency(billingAccount.currentBalance)}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-secondary/20 p-4">
            <p className="text-xs text-muted-foreground mb-1">Last Payment</p>
            <p className="text-sm font-semibold text-foreground">
              {formatCurrency(billingAccount.lastPaymentAmount)}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {formatDate(billingAccount.lastPaymentDate)}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-secondary/20 p-4">
            <p className="text-xs text-muted-foreground mb-1">Next Billing Date</p>
            <p className="text-sm font-semibold text-foreground">
              {formatDate(billingAccount.nextBillingDate)}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-secondary/20 p-4">
            <p className="text-xs text-muted-foreground mb-1">Payment Method</p>
            <p className="text-sm font-semibold text-foreground">{billingAccount.paymentMethod}</p>
          </div>
          <div className="rounded-lg border border-border bg-secondary/20 p-4">
            <p className="text-xs text-muted-foreground mb-1">Auto Pay</p>
            <div className="flex items-center gap-2">
              {billingAccount.autoPayEnabled ? (
                <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
                  <CheckCircle2 className="mr-1 h-3 w-3" />
                  Enabled
                </Badge>
              ) : (
                <Badge className="bg-slate-500/15 text-slate-400 border-slate-500/30">
                  <XCircle className="mr-1 h-3 w-3" />
                  Disabled
                </Badge>
              )}
            </div>
          </div>
        </div>
      </SectionCard>

      {/* ── Subscriptions Table ───────────────────────────────────────── */}
      <SectionCard title="Subscriptions" icon={Package}>
        {subscriptions.length === 0 ? (
          <EmptyState message="No subscriptions on record" />
        ) : (
          <div className="hidden md:block overflow-x-auto rounded-lg border border-border">
            <Table>
              <TableHeader>
                <TableRow className="bg-secondary/50 hover:bg-secondary/50">
                  <TableHead className="text-muted-foreground">Plan</TableHead>
                  <TableHead className="text-muted-foreground">Type</TableHead>
                  <TableHead className="text-muted-foreground">Status</TableHead>
                  <TableHead className="text-muted-foreground text-right">MRR</TableHead>
                  <TableHead className="text-muted-foreground">Start</TableHead>
                  <TableHead className="text-muted-foreground">Next Billing</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {subscriptions.map((sub) => (
                  <TableRow key={sub.id} className="hover:bg-muted/30">
                    <TableCell className="font-medium text-foreground">{sub.planName}</TableCell>
                    <TableCell className="text-muted-foreground">{sub.serviceType}</TableCell>
                    <TableCell>
                      <StatusBadge status={sub.status} />
                    </TableCell>
                    <TableCell className="text-right font-medium text-foreground">
                      {formatCurrency(sub.monthlyRecurring)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{formatDate(sub.startDate)}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDate(sub.nextBillingDate)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {/* Mobile card view */}
        {subscriptions.length > 0 && (
          <div className="md:hidden space-y-2">
            {subscriptions.map((sub) => (
              <div key={sub.id} className="rounded-lg border border-border bg-secondary/20 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-foreground">{sub.planName}</p>
                    <p className="text-xs text-muted-foreground">{sub.serviceType}</p>
                  </div>
                  <StatusBadge status={sub.status} />
                </div>
                <div className="mt-2 flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">MRR</span>
                  <span className="font-semibold text-foreground">{formatCurrency(sub.monthlyRecurring)}</span>
                </div>
                <div className="mt-1 flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Next Billing</span>
                  <span className="text-foreground">{formatDate(sub.nextBillingDate)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      {/* ── Payment Methods + Handover History ────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Payment Methods */}
        <SectionCard title="Payment Methods" icon={Wallet}>
          {paymentMethods.length === 0 ? (
            <EmptyState message="No payment methods on record" />
          ) : (
            <div className="space-y-2">
              {paymentMethods.map((pm) => (
                <div
                  key={pm.id}
                  className="flex items-center gap-3 rounded-lg border border-border bg-secondary/20 p-3 transition-colors hover:border-primary/30"
                >
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                    {pm.type === "bank_account" || pm.type === "eft" ? (
                      <Banknote className="h-5 w-5 text-primary" />
                    ) : (
                      <CreditCard className="h-5 w-5 text-primary" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-foreground">{pm.displayName}</p>
                      {pm.isDefault && (
                        <Badge variant="outline" className="text-xs border-primary/30 text-primary">
                          Default
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      •••• {pm.last4}
                      {pm.expiryDate && ` · Expires ${pm.expiryDate}`}
                    </p>
                  </div>
                  <StatusBadge status={pm.status} />
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        {/* Handover History */}
        <SectionCard title="Handover History" icon={ArrowRightLeft}>
          {handoverHistory.length === 0 ? (
            <EmptyState message="No handover history on record" />
          ) : (
            <ScrollArea className="max-h-80">
              <div className="relative space-y-0">
                {/* Timeline line */}
                <div className="absolute left-[19px] top-2 bottom-2 w-px bg-border" />

                {handoverHistory.map((record, idx) => (
                  <div key={record.id} className="relative flex gap-4 pb-5 last:pb-0">
                    {/* Timeline dot */}
                    <div
                      className={cn(
                        "relative z-10 mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2",
                        record.status === "completed"
                          ? "border-emerald-500 bg-emerald-500/20"
                          : record.status === "pending"
                            ? "border-amber-500 bg-amber-500/20"
                            : "border-slate-500 bg-slate-500/20"
                      )}
                    >
                      <div
                        className={cn(
                          "h-2 w-2 rounded-full",
                          record.status === "completed"
                            ? "bg-emerald-400"
                            : record.status === "pending"
                              ? "bg-amber-400"
                              : "bg-slate-400"
                        )}
                      />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-medium text-foreground">{record.reason}</p>
                        <StatusBadge status={record.status} />
                      </div>
                      <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                        <span>{record.fromAgent}</span>
                        <ChevronRight className="h-3 w-3" />
                        <span className="font-medium text-foreground">{record.toAgent}</span>
                      </div>
                      <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {formatDate(record.date)}
                      </div>
                      {record.notes && (
                        <p className="mt-1 text-xs text-muted-foreground italic">{record.notes}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </SectionCard>
      </div>
    </div>
  )
}

export default CustomerDetailsTab
