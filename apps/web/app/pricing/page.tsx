"use client"

import { useState, useMemo, useCallback } from "react"
import Link from "next/link"
import {
    DollarSign,
    Users,
    Headset,
    Wifi,
    Phone,
    Megaphone,
    ShieldCheck,
    UserCog,
    MessageSquare,
    Receipt,
    FileText,
    Package,
    Globe,
    HeartHandshake,
    Check,
    X,
    BarChart3,
    Mail,
    Zap,
    HardDrive,
    Database,
    ArrowRight,
    Info,
    Minus
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { cn } from "@/lib/utils"
import { ThemeToggleCompact } from "@/components/ui/theme-toggle"
import { FlickeringGrid } from "@/components/ui/flickering-grid"
import { useIsClient } from "@/lib/use-is-client"

// All 14 modules (excluding Dashboard Overview)
const modules = [
    {
        id: "communication",
        icon: MessageSquare,
        name: "Communication Hub",
        category: "Core",
        starterPrice: 199,
        professionalPrice: 499,
        enterprisePrice: 1499,
        slug: "communication",
        customers: null,
        color: "from-blue-600 via-indigo-500 to-violet-500"
    },
    {
        id: "sales",
        icon: DollarSign,
        name: "Sales Hub",
        category: "Revenue",
        starterPrice: 299,
        professionalPrice: 899,
        enterprisePrice: 2999,
        slug: "sales",
        customers: 1000,
        color: "from-indigo-600 to-blue-500"
    },
    {
        id: "crm",
        icon: Users,
        name: "CRM Hub",
        category: "Customer",
        starterPrice: 249,
        professionalPrice: 749,
        enterprisePrice: 2499,
        slug: "crm",
        customers: 1000,
        color: "from-violet-600 to-indigo-600"
    },
    {
        id: "service",
        icon: Headset,
        name: "Service Hub",
        category: "Customer",
        starterPrice: 199,
        professionalPrice: 599,
        enterprisePrice: 1999,
        slug: "support",
        customers: 500,
        color: "from-blue-500 to-cyan-500"
    },
    {
        id: "retention",
        icon: HeartHandshake,
        name: "Retention Hub",
        category: "Analytics",
        starterPrice: 399,
        professionalPrice: 1199,
        enterprisePrice: 3999,
        slug: "retention",
        customers: 1000,
        color: "from-indigo-500 via-purple-500 to-pink-500"
    },
    {
        id: "network",
        icon: Wifi,
        name: "Network Ops Hub",
        category: "Operations",
        starterPrice: 499,
        professionalPrice: 1499,
        enterprisePrice: 4999,
        slug: "network",
        customers: null,
        color: "from-cyan-500 to-blue-600"
    },
    {
        id: "call-center",
        icon: Phone,
        name: "Call Center Hub",
        category: "Customer",
        starterPrice: 299,
        professionalPrice: 899,
        enterprisePrice: 2999,
        slug: "call-center",
        customers: null,
        color: "from-blue-600 to-indigo-600"
    },
    {
        id: "marketing",
        icon: Megaphone,
        name: "Marketing Hub",
        category: "Revenue",
        starterPrice: 299,
        professionalPrice: 899,
        enterprisePrice: 2999,
        slug: "marketing",
        customers: 1000,
        color: "from-indigo-400 to-violet-500"
    },
    {
        id: "compliance",
        icon: ShieldCheck,
        name: "Compliance Hub",
        category: "Operations",
        starterPrice: 199,
        professionalPrice: 599,
        enterprisePrice: 1999,
        slug: "compliance",
        customers: null,
        color: "from-slate-600 to-blue-900"
    },
    {
        id: "talent",
        icon: UserCog,
        name: "Staff Dome",
        category: "Operations",
        starterPrice: 149,
        professionalPrice: 449,
        enterprisePrice: 1499,
        slug: "talent",
        customers: null,
        color: "from-indigo-500 to-sky-500"
    },
    {
        id: "billing",
        icon: Receipt,
        name: "Billing Hub",
        category: "Revenue",
        starterPrice: 249,
        professionalPrice: 749,
        enterprisePrice: 2499,
        slug: "billing",
        customers: 1000,
        color: "from-cyan-600 to-indigo-600"
    },
    {
        id: "finance",
        icon: FileText,
        name: "Finance & FP&A Hub",
        category: "Revenue",
        starterPrice: 299,
        professionalPrice: 899,
        enterprisePrice: 2999,
        slug: "finance",
        customers: null,
        color: "from-emerald-500 to-cyan-500"
    },
    {
        id: "products",
        icon: Package,
        name: "Product Hub",
        category: "Operations",
        starterPrice: 149,
        professionalPrice: 449,
        enterprisePrice: 1499,
        slug: "products",
        customers: null,
        color: "from-violet-500 to-indigo-500"
    },
    {
        id: "portal",
        icon: Globe,
        name: "Portal Hub",
        category: "Core",
        starterPrice: 199,
        professionalPrice: 599,
        enterprisePrice: 1999,
        slug: "portal",
        customers: null,
        color: "from-blue-600 to-cyan-500"
    },
]

type TierType = "starter" | "professional" | "enterprise"
type ViewType = "customer-platform" | "create-bundle" | "individual" | "usage-limits" | string

// ───────────────────── Usage Matrix (Airtable-style feature grid) ─────────────────────
// Aligned with backend tenant tiers: FREE → STARTER → PROFESSIONAL → ENTERPRISE
// and tenant_modules entitlement system

interface UsageRow {
    feature: string
    tooltip?: string
    free: string | number | boolean
    starter: string | number | boolean
    professional: string | number | boolean
    enterprise: string | number | boolean
}

interface UsageCategory {
    name: string
    icon: React.ElementType
    rows: UsageRow[]
}

const usageMatrix: UsageCategory[] = [
    {
        name: "Platform",
        icon: Database,
        rows: [
            { feature: "Sub-tenants", tooltip: "Separate white-label environments", free: 1, starter: 1, professional: 3, enterprise: "Unlimited" },
            { feature: "User seats", free: 1, starter: 3, professional: 10, enterprise: "Unlimited" },
            { feature: "Contacts / Customers", tooltip: "Active CRM contacts per tenant", free: 100, starter: "1,000", professional: "25,000", enterprise: "Unlimited" },
            { feature: "Records per module", tooltip: "Rows across deals, tickets, etc.", free: "1,000", starter: "10,000", professional: "100,000", enterprise: "Unlimited" },
            { feature: "Custom fields per module", free: 5, starter: 25, professional: 100, enterprise: "Unlimited" },
            { feature: "File storage", free: "500 MB", starter: "5 GB", professional: "50 GB", enterprise: "500 GB" },
            { feature: "Data retention", free: "90 days", starter: "1 year", professional: "3 years", enterprise: "7 years" },
            { feature: "API access", free: false, starter: true, professional: true, enterprise: true },
            { feature: "API requests / month", free: "-", starter: "10,000", professional: "250,000", enterprise: "Unlimited" },
            { feature: "Webhooks", free: false, starter: 5, professional: 50, enterprise: "Unlimited" },
        ],
    },
    {
        name: "Automations & AI",
        icon: Zap,
        rows: [
            { feature: "Automation runs / month", tooltip: "Workflow triggers across all modules", free: 100, starter: "1,000", professional: "50,000", enterprise: "Unlimited" },
            { feature: "Active automations", free: 5, starter: 25, professional: 250, enterprise: "Unlimited" },
            { feature: "AI credits / month", tooltip: "Used for churn prediction, smart suggestions, AI chat", free: 50, starter: 500, professional: "5,000", enterprise: "10,000" },
            { feature: "Churn prediction (Retention)", free: false, starter: false, professional: true, enterprise: true },
            { feature: "AI deal scoring (Sales)", free: false, starter: true, professional: true, enterprise: true },
            { feature: "Sentiment analysis (Service)", free: false, starter: false, professional: true, enterprise: true },
            { feature: "Revenue forecasting (Finance)", free: false, starter: false, professional: true, enterprise: true },
        ],
    },
    {
        name: "Communication & Marketing",
        icon: Mail,
        rows: [
            { feature: "Email sends / month", tooltip: "Transactional + marketing via UniOne", free: "1,000", starter: "6,000", professional: "50,000", enterprise: "Custom" },
            { feature: "Email templates", free: 5, starter: 25, professional: "200+", enterprise: "Unlimited" },
            { feature: "Drag-and-drop email builder", free: true, starter: true, professional: true, enterprise: true },
            { feature: "SMS sends / month", free: 0, starter: 500, professional: "5,000", enterprise: "Custom" },
            { feature: "Marketing campaigns", free: 2, starter: 10, professional: "Unlimited", enterprise: "Unlimited" },
            { feature: "Lead scoring", free: false, starter: true, professional: true, enterprise: true },
            { feature: "A/B testing", free: false, starter: false, professional: true, enterprise: true },
            { feature: "Custom unsubscribe management", free: false, starter: true, professional: true, enterprise: true },
            { feature: "Dedicated IP (email)", free: false, starter: false, professional: "Add-on", enterprise: "Included" },
            { feature: "SightLive™ post-campaign analytics", tooltip: "Proprietary OOH & radio analytics", free: false, starter: false, professional: true, enterprise: true },
        ],
    },
    {
        name: "Sales & CRM",
        icon: DollarSign,
        rows: [
            { feature: "Deal pipelines", free: 1, starter: 3, professional: 25, enterprise: "Unlimited" },
            { feature: "Deal stages per pipeline", free: 5, starter: 10, professional: 50, enterprise: "Unlimited" },
            { feature: "Quotes / proposals per month", free: 5, starter: 50, professional: "Unlimited", enterprise: "Unlimited" },
            { feature: "Contact timeline & activity log", free: true, starter: true, professional: true, enterprise: true },
            { feature: "Customer journey mapping", free: false, starter: false, professional: true, enterprise: true },
            { feature: "Revenue attribution", free: false, starter: false, professional: true, enterprise: true },
        ],
    },
    {
        name: "Service & Call Center",
        icon: Headset,
        rows: [
            { feature: "Support tickets / month", free: 50, starter: 500, professional: "10,000", enterprise: "Unlimited" },
            { feature: "SLA policies", free: 1, starter: 3, professional: 10, enterprise: "Unlimited" },
            { feature: "Knowledge base articles", free: 10, starter: 50, professional: "Unlimited", enterprise: "Unlimited" },
            { feature: "Live chat widget", free: false, starter: true, professional: true, enterprise: true },
            { feature: "Call recording & transcription", free: false, starter: false, professional: true, enterprise: true },
            { feature: "IVR / auto-attendant", free: false, starter: false, professional: true, enterprise: true },
            { feature: "Call center agent seats", free: "-", starter: 3, professional: 15, enterprise: "Unlimited" },
        ],
    },
    {
        name: "Network & IoT",
        icon: Wifi,
        rows: [
            { feature: "Monitored devices", free: 10, starter: 100, professional: "5,000", enterprise: "Unlimited" },
            { feature: "Alert rules", free: 3, starter: 25, professional: 250, enterprise: "Unlimited" },
            { feature: "Outage notifications", free: true, starter: true, professional: true, enterprise: true },
            { feature: "Capacity planning", free: false, starter: false, professional: true, enterprise: true },
            { feature: "IoT telemetry retention", free: "7 days", starter: "30 days", professional: "1 year", enterprise: "3 years" },
            { feature: "Remote device commands", free: false, starter: false, professional: true, enterprise: true },
        ],
    },
    {
        name: "Billing & Finance",
        icon: Receipt,
        rows: [
            { feature: "Invoices / month", free: 25, starter: 500, professional: "10,000", enterprise: "Unlimited" },
            { feature: "Payment gateways", tooltip: "Paystack, Stripe, manual", free: 1, starter: 2, professional: 5, enterprise: "Unlimited" },
            { feature: "Recurring billing automation", free: false, starter: true, professional: true, enterprise: true },
            { feature: "Collections workflows", free: false, starter: false, professional: true, enterprise: true },
            { feature: "Revenue recognition (GAAP)", free: false, starter: false, professional: true, enterprise: true },
            { feature: "Expense governance", free: false, starter: false, professional: true, enterprise: true },
            { feature: "Scenario planning", free: false, starter: false, professional: false, enterprise: true },
        ],
    },
    {
        name: "Compliance & Operations",
        icon: ShieldCheck,
        rows: [
            { feature: "RICA verifications / month", free: 10, starter: 100, professional: "5,000", enterprise: "Unlimited" },
            { feature: "POPIA consent tracking", free: true, starter: true, professional: true, enterprise: true },
            { feature: "Audit trail retention", free: "30 days", starter: "1 year", professional: "5 years", enterprise: "7 years" },
            { feature: "Product catalog items", free: 10, starter: 100, professional: "1,000", enterprise: "Unlimited" },
            { feature: "Inventory warehouses", free: 1, starter: 3, professional: 10, enterprise: "Unlimited" },
            { feature: "Staff management (HR)", free: false, starter: true, professional: true, enterprise: true },
            { feature: "Payroll integration", tooltip: "Via Paystack", free: false, starter: false, professional: true, enterprise: true },
        ],
    },
    {
        name: "Portal & Analytics",
        icon: Globe,
        rows: [
            { feature: "Customer self-service portal", free: true, starter: true, professional: true, enterprise: true },
            { feature: "White-label portal", free: false, starter: false, professional: true, enterprise: true },
            { feature: "Custom domain for portal", free: false, starter: false, professional: true, enterprise: true },
            { feature: "Executive dashboards", free: 1, starter: 3, professional: 10, enterprise: "Unlimited" },
            { feature: "Scheduled report exports", free: false, starter: true, professional: true, enterprise: true },
            { feature: "Cross-module analytics", free: false, starter: false, professional: true, enterprise: true },
        ],
    },
    {
        name: "Support & Security",
        icon: ShieldCheck,
        rows: [
            { feature: "Support channel", free: "Email", starter: "Email + Chat", professional: "Priority email + chat + phone", enterprise: "Dedicated account manager" },
            { feature: "Uptime SLA", free: "-", starter: "99.5%", professional: "99.9%", enterprise: "99.99%" },
            { feature: "SSO (SAML / OAuth)", free: false, starter: false, professional: true, enterprise: true },
            { feature: "Two-factor authentication", free: true, starter: true, professional: true, enterprise: true },
            { feature: "IP allowlisting", free: false, starter: false, professional: false, enterprise: true },
            { feature: "Custom data residency", free: false, starter: false, professional: false, enterprise: true },
        ],
    },
]

// ───────────────────── Email Volume Pricing (UniOne-based, 60% margin) ─────────────────────
// UniOne base: $4 for 6,000 emails, overage $0.75/1,000
// Margin: 60% markup → cost × 1.6
// USD → ZAR: R18.50 (approximate Feb 2026)
const EMAIL_USD_TO_ZAR = 18.50
const EMAIL_MARGIN = 1.60 // 60% margin
const EMAIL_BASE_USD = 4 // $4 base for first 6,000
const EMAIL_OVERAGE_PER_1000_USD = 0.75

const emailVolumeSteps = [
    1_000, 3_000, 6_000, 10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000,
]

function calculateEmailPriceZAR(emailCount: number): number {
    if (emailCount <= 0) return 0
    // Up to 6,000: flat base
    if (emailCount <= 6_000) {
        const baseCostUSD = EMAIL_BASE_USD
        return Math.round(baseCostUSD * EMAIL_MARGIN * EMAIL_USD_TO_ZAR)
    }
    // Beyond 6,000: base + overage
    const overageEmails = emailCount - 6_000
    const overageBlocks = Math.ceil(overageEmails / 1_000)
    const totalUSD = EMAIL_BASE_USD + overageBlocks * EMAIL_OVERAGE_PER_1000_USD
    return Math.round(totalUSD * EMAIL_MARGIN * EMAIL_USD_TO_ZAR)
}

// Dedicated IP add-on: $40/mo + $20 setup (one-time) → with margin & ZAR
const DEDICATED_IP_MONTHLY_ZAR = Math.round(40 * EMAIL_MARGIN * EMAIL_USD_TO_ZAR)

// Customer Platform bundles
const customerPlatformBundles = {
    professional: {
        name: "Professional",
        description: "Comprehensive ISP management software for growing businesses.",
        basePrice: 3500,
        annualPrice: 2800,
        seats: 6,
        extraSeatPrice: 45,
        credits: 5000,
        includedModules: ["marketing", "sales", "service", "crm", "billing", "portal"]
    },
    enterprise: {
        name: "Enterprise",
        description: "Our most powerful platform with advanced features and unlimited customization.",
        basePrice: 9500,
        annualPrice: 7600,
        seats: 8,
        extraSeatPrice: 75,
        credits: 10000,
        includedModules: ["marketing", "sales", "service", "crm", "billing", "portal", "retention", "network", "compliance"]
    }
}

// Individual/Startup plans
const individualPlans = {
    starter: {
        name: "Starter",
        description: "Essential tools for new ISPs getting started.",
        basePrice: 0,
        features: ["Up to 100 customers", "Basic CRM", "Email support", "1 user seat"],
        limitations: ["Limited reporting", "No API access"]
    },
    growth: {
        name: "Growth",
        description: "Everything you need to scale your first 1,000 customers.",
        basePrice: 999,
        features: ["Up to 1,000 customers", "Full CRM + Sales Hub", "Phone support", "3 user seats", "Basic reporting", "API access"],
        limitations: []
    }
}

export default function PricingPage() {
    const [selectedModules, setSelectedModules] = useState<Record<string, TierType | null>>({})
    const [billingPeriod, setBillingPeriod] = useState<"monthly" | "annually">("monthly")
    const [customerCounts, setCustomerCounts] = useState<Record<string, number>>({})
    const [activeView, setActiveView] = useState<ViewType>("customer-platform")
    const [audienceTab, setAudienceTab] = useState<"business" | "individual">("business")
    const [emailVolume, setEmailVolume] = useState(2) // index into emailVolumeSteps (6,000 default)
    const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>({})
    const isClient = useIsClient()

    const toggleCategory = (name: string) => {
        setExpandedCategories(prev => ({ ...prev, [name]: !prev[name] }))
    }

    const emailCount = emailVolumeSteps[emailVolume] ?? 6_000
    const emailPriceZAR = calculateEmailPriceZAR(emailCount)

    const toggleModule = (id: string, tier: TierType) => {
        setSelectedModules(prev => ({
            ...prev,
            [id]: prev[id] === tier ? null : tier
        }))
    }

    const removeModule = (id: string) => {
        setSelectedModules(prev => {
            const newState = { ...prev }
            delete newState[id]
            return newState
        })
    }

    const getPrice = useCallback((module: typeof modules[0], tier: TierType) => {
        const price = tier === "starter" ? module.starterPrice
            : tier === "professional" ? module.professionalPrice
                : module.enterprisePrice
        return billingPeriod === "annually" ? Math.round(price * 0.8) : price
    }, [billingPeriod])

    const selectedProducts = useMemo(() => {
        return Object.entries(selectedModules)
            .filter(([, tier]) => tier !== null)
            .map(([id, tier]) => {
                const mod = modules.find(m => m.id === id)!
                return { ...mod, selectedTier: tier! }
            })
    }, [selectedModules])

    const totalMonthly = useMemo(() => {
        return selectedProducts.reduce((acc, prod) => {
            return acc + getPrice(prod, prod.selectedTier)
        }, 0)
    }, [selectedProducts, getPrice])

    const renderMainContent = () => {
        switch (activeView) {
            case "customer-platform":
                return (
                    <div>
                        <div className="text-center mb-12">
                            <h1 className="text-4xl font-bold mb-4">Customer Platform</h1>
                            <p className="text-muted-foreground">
                                Everything you need to scale your ISP business, bundled together and discounted.{" "}
                                <Link href="#" className="text-primary underline">Calculate your price</Link>
                            </p>
                        </div>

                        <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
                            {Object.entries(customerPlatformBundles).map(([key, bundle]) => (
                                <div key={key} className="border border-border rounded-2xl bg-card p-8">
                                    <h2 className="text-2xl font-bold mb-2">{bundle.name}</h2>
                                    <p className="text-sm text-muted-foreground mb-6">{bundle.description}</p>

                                    <div className="mb-4">
                                        <span className="text-xs text-muted-foreground">Starts at</span>
                                        <div className="flex items-baseline gap-1">
                                            <span className="text-3xl font-bold">R{!isClient ? "--" : (billingPeriod === "annually" ? bundle.annualPrice.toLocaleString() : bundle.basePrice.toLocaleString())}</span>
                                            <span className="text-muted-foreground">/mo</span>
                                        </div>
                                        {billingPeriod === "annually" && isClient && (
                                            <span className="text-xs text-muted-foreground line-through">R{bundle.basePrice.toLocaleString()}/mo</span>
                                        )}
                                    </div>

                                    <p className="text-sm text-muted-foreground mb-6">
                                        Includes {bundle.seats} Seats. Additional Core Seats start at R{bundle.extraSeatPrice}/mo
                                    </p>

                                    <div className="flex gap-2 mb-6">
                                        <button
                                            onClick={() => setBillingPeriod("monthly")}
                                            className={cn(
                                                "flex-1 py-2 text-xs font-medium rounded-lg border transition-colors",
                                                billingPeriod === "monthly" ? "bg-secondary border-border" : "border-border hover:bg-secondary/50"
                                            )}
                                        >
                                            Pay Monthly
                                        </button>
                                        <button
                                            onClick={() => setBillingPeriod("annually")}
                                            className={cn(
                                                "flex-1 py-2 text-xs font-medium rounded-lg border transition-colors",
                                                billingPeriod === "annually" ? "bg-secondary border-border" : "border-border hover:bg-secondary/50"
                                            )}
                                        >
                                            <div>Pay Annually</div>
                                            <div className="text-primary text-[10px] font-black uppercase tracking-wider">BEST VALUE</div>
                                        </button>
                                    </div>

                                    <Button className="w-full bg-gradient-to-r from-indigo-600 to-blue-500 font-bold shadow-[0_0_20px_rgba(79,70,229,0.3)] text-white hover:shadow-[0_0_30px_rgba(79,70,229,0.5)] transition-all mb-4">
                                        Talk to Sales
                                    </Button>

                                    <p className="text-xs text-muted-foreground mb-6">{!isClient ? "--" : bundle.credits.toLocaleString()} OmniDome Credits</p>

                                    <div className="text-sm text-muted-foreground mb-4">
                                        {key === "professional" ? "Starter" : "Professional"} Customer Platform, plus:
                                    </div>

                                    <ul className="space-y-3">
                                        {bundle.includedModules.slice(0, 6).map(modId => {
                                            const mod = modules.find(m => m.id === modId)
                                            if (!mod) return null
                                            return (
                                                <li key={modId} className="flex items-center gap-3 text-sm">
                                                    <div className={cn("w-5 h-5 rounded flex items-center justify-center bg-gradient-to-br", mod.color)}>
                                                        <mod.icon className="h-3 w-3 text-white" />
                                                    </div>
                                                    <span className="font-medium">{mod.name} {key === "professional" ? "Professional" : "Enterprise"}</span>
                                                </li>
                                            )
                                        })}
                                    </ul>
                                </div>
                            ))}
                        </div>
                    </div>
                )

            case "create-bundle":
                return (
                    <div className="flex gap-12">
                        <div className="flex-1 space-y-6">
                            <div className="text-center mb-8">
                                <h1 className="text-4xl font-bold mb-4">Create a Bundle</h1>
                                <p className="text-muted-foreground">
                                    Grow your business in the areas that matter most with a custom toolkit.
                                </p>
                            </div>

                            <h2 className="text-xl font-semibold">Select products & add-ons</h2>

                            {modules.map(mod => (
                                <div key={mod.id} className="border border-border rounded-xl p-6 bg-card">
                                    <div className="flex items-center gap-3 mb-6">
                                        <div className={cn("h-8 w-8 rounded-lg bg-gradient-to-br flex items-center justify-center", mod.color)}>
                                            <mod.icon className="h-4 w-4 text-white" />
                                        </div>
                                        <h3 className="font-semibold">{mod.name}</h3>
                                    </div>

                                    <div className="grid grid-cols-3 gap-4 mb-4">
                                        {(["starter", "professional", "enterprise"] as TierType[]).map(tier => {
                                            const price = getPrice(mod, tier)
                                            const isSelected = selectedModules[mod.id] === tier
                                            return (
                                                <button
                                                    key={tier}
                                                    onClick={() => toggleModule(mod.id, tier)}
                                                    className={cn(
                                                        "border rounded-lg p-4 text-left transition-all",
                                                        isSelected
                                                            ? "border-emerald-500 bg-emerald-500/5"
                                                            : "border-border hover:border-muted-foreground/50"
                                                    )}
                                                >
                                                    <div className="flex items-center gap-2 mb-2">
                                                        <div className={cn(
                                                            "w-4 h-4 rounded border-2 flex items-center justify-center",
                                                            isSelected ? "border-emerald-500 bg-emerald-500" : "border-muted-foreground"
                                                        )}>
                                                            {isSelected && <Check className="h-3 w-3 text-white" />}
                                                        </div>
                                                        <span className="text-sm font-medium capitalize">{tier}</span>
                                                    </div>
                                                    <div className="text-lg font-bold">R{price}<span className="text-sm font-normal text-muted-foreground">/month</span></div>
                                                </button>
                                            )
                                        })}
                                    </div>

                                    {mod.customers && selectedModules[mod.id] && (
                                        <div className="border-t border-border pt-4">
                                            <div className="flex items-center justify-between">
                                                <div>
                                                    <span className="text-sm">Select number of </span>
                                                    <span className="text-sm text-primary underline cursor-pointer">customers</span>
                                                    <span className="text-sm">:</span>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <label htmlFor={`customers-${mod.id}`} className="sr-only">Number of customers</label>
                                                    <input
                                                        id={`customers-${mod.id}`}
                                                        type="number"
                                                        value={customerCounts[mod.id] || mod.customers}
                                                        onChange={(e) => setCustomerCounts(prev => ({ ...prev, [mod.id]: parseInt(e.target.value) || 0 }))}
                                                        className="w-24 px-3 py-2 border border-border rounded-lg bg-background text-right"
                                                        title="Number of customers"
                                                        aria-label="Number of customers"
                                                        placeholder="0"
                                                    />
                                                </div>
                                            </div>
                                            <p className="text-xs text-muted-foreground mt-2">
                                                Includes {!isClient ? "--" : mod.customers.toLocaleString()} customers. Additional customers sold in increments of 1,000 from R50/month.
                                            </p>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>

                        {/* Summary Sidebar */}
                        <div className="w-80 shrink-0">
                            <div className="sticky top-24 border border-border rounded-xl bg-card overflow-hidden">
                                <div className="flex border-b border-border">
                                    <button
                                        onClick={() => setBillingPeriod("monthly")}
                                        className={cn(
                                            "flex-1 py-3 text-sm font-medium transition-colors",
                                            billingPeriod === "monthly" ? "bg-secondary" : "hover:bg-secondary/50"
                                        )}
                                    >
                                        Pay Monthly
                                    </button>
                                    <button
                                        onClick={() => setBillingPeriod("annually")}
                                        className={cn(
                                            "flex-1 py-3 text-sm font-medium transition-colors",
                                            billingPeriod === "annually" ? "bg-secondary" : "hover:bg-secondary/50"
                                        )}
                                    >
                                        Pay Annually
                                    </button>
                                </div>

                                <div className="p-6">
                                    <h3 className="font-semibold mb-4">Your products</h3>

                                    {selectedProducts.length === 0 ? (
                                        <p className="text-sm text-muted-foreground italic">No products selected...</p>
                                    ) : (
                                        <div className="space-y-4">
                                            {selectedProducts.map(prod => (
                                                <div key={prod.id} className="flex justify-between items-start text-sm">
                                                    <div>
                                                        <div className="font-medium">{prod.name}</div>
                                                        <div className="text-primary capitalize">{prod.selectedTier}</div>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <span>R{getPrice(prod, prod.selectedTier)}/mo</span>
                                                        <button
                                                            onClick={() => removeModule(prod.id)}
                                                            className="text-muted-foreground hover:text-foreground"
                                                            title="Remove module"
                                                            aria-label="Remove module"
                                                        >
                                                            <X className="h-4 w-4" />
                                                        </button>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    <div className="border-t border-border mt-6 pt-6">
                                        <div className="flex justify-between items-center mb-4">
                                            <span className="font-semibold">Estimated Total</span>
                                            <div className="text-right">
                                                <div className="text-2xl font-bold">R{!isClient ? "0" : totalMonthly.toLocaleString()}</div>
                                                <div className="text-xs text-muted-foreground">/month</div>
                                            </div>
                                        </div>
                                        <Button className="w-full bg-gradient-to-r from-indigo-600 to-blue-500 font-bold shadow-[0_0_20px_rgba(79,70,229,0.3)] text-white hover:shadow-[0_0_30px_rgba(79,70,229,0.5)] transition-all">
                                            Buy now
                                        </Button>
                                        <p className="text-xs text-center text-muted-foreground mt-3">
                                            Prices shown are subject to applicable tax.
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )

            case "usage-limits":
                return (
                    <div>
                        <div className="text-center mb-12">
                            <h1 className="text-4xl font-bold mb-4">Usage & Limits</h1>
                            <p className="text-muted-foreground max-w-2xl mx-auto">
                                Compare what each tier includes across every module. Aligned with our multi-tenant entitlement system — upgrade anytime.
                            </p>
                        </div>

                        {/* Email Volume Calculator — Marketing (UniOne-based) */}
                        <div className="border border-border rounded-2xl bg-card p-8 mb-12">
                            <div className="flex items-center gap-3 mb-6">
                                <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-400 to-violet-500 flex items-center justify-center">
                                    <Mail className="h-5 w-5 text-white" />
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold">Email Volume Calculator</h2>
                                    <p className="text-xs text-muted-foreground">Marketing email pricing powered by UniOne delivery infrastructure</p>
                                </div>
                            </div>

                            <div className="grid md:grid-cols-2 gap-8">
                                <div>
                                    <label className="text-sm font-medium text-muted-foreground block mb-2">
                                        How many emails do you need to send monthly?
                                    </label>
                                    <Slider
                                        value={[emailVolume]}
                                        onValueChange={([v]) => setEmailVolume(v)}
                                        min={0}
                                        max={emailVolumeSteps.length - 1}
                                        step={1}
                                        className="mb-4"
                                    />
                                    <div className="flex justify-between text-xs text-muted-foreground">
                                        <span>1K</span>
                                        <span>1M</span>
                                    </div>
                                    <div className="mt-4 text-center">
                                        <span className="text-3xl font-bold">{emailCount.toLocaleString()}</span>
                                        <span className="text-muted-foreground ml-2">emails / month</span>
                                    </div>
                                </div>

                                <div className="border border-border rounded-xl bg-background p-6">
                                    <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Estimated cost</div>
                                    <div className="flex items-baseline gap-1 mb-4">
                                        <span className="text-4xl font-bold">R{isClient ? emailPriceZAR.toLocaleString() : "--"}</span>
                                        <span className="text-muted-foreground">/month</span>
                                    </div>
                                    <ul className="space-y-2 text-sm text-muted-foreground">
                                        <li className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-primary" /> SMTP & Web API included</li>
                                        <li className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-primary" /> SPF, DKIM, DMARC authentication</li>
                                        <li className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-primary" /> Real-time webhooks & analytics</li>
                                        <li className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-primary" /> 200+ email templates</li>
                                        <li className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-primary" /> 99%+ deliverability</li>
                                    </ul>
                                    <div className="mt-4 pt-4 border-t border-border">
                                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                            <Info className="h-3.5 w-3.5" />
                                            <span>Dedicated IP add-on: R{isClient ? DEDICATED_IP_MONTHLY_ZAR.toLocaleString() : "--"}/mo</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Airtable-style Feature Comparison Grid */}
                        <div className="border border-border rounded-2xl bg-card overflow-hidden">
                            {/* Table Header */}
                            <div className="grid grid-cols-[1fr,100px,100px,120px,120px] gap-0 border-b border-border bg-muted/50 sticky top-16 z-10">
                                <div className="px-6 py-4 text-sm font-semibold">Feature</div>
                                <div className="px-3 py-4 text-sm font-semibold text-center">Free</div>
                                <div className="px-3 py-4 text-sm font-semibold text-center">Starter</div>
                                <div className="px-3 py-4 text-sm font-semibold text-center text-indigo-400">Professional</div>
                                <div className="px-3 py-4 text-sm font-semibold text-center text-violet-400">Enterprise</div>
                            </div>

                            {usageMatrix.map((category) => {
                                const isExpanded = expandedCategories[category.name] !== false // default open
                                return (
                                    <div key={category.name}>
                                        {/* Category Header */}
                                        <button
                                            onClick={() => toggleCategory(category.name)}
                                            className="w-full grid grid-cols-[1fr,100px,100px,120px,120px] gap-0 border-b border-border bg-muted/30 hover:bg-muted/50 transition-colors"
                                        >
                                            <div className="px-6 py-3 flex items-center gap-3 text-left">
                                                <category.icon className="h-4 w-4 text-primary" />
                                                <span className="text-sm font-bold">{category.name}</span>
                                                <ArrowRight className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", isExpanded && "rotate-90")} />
                                            </div>
                                            <div /><div /><div /><div />
                                        </button>

                                        {/* Category Rows */}
                                        {isExpanded && category.rows.map((row, rowIdx) => (
                                            <div
                                                key={row.feature}
                                                className={cn(
                                                    "grid grid-cols-[1fr,100px,100px,120px,120px] gap-0 border-b border-border/50 hover:bg-muted/20 transition-colors",
                                                    rowIdx % 2 === 0 ? "bg-transparent" : "bg-muted/10"
                                                )}
                                            >
                                                <div className="px-6 py-3 flex items-center gap-2">
                                                    <span className="text-sm">{row.feature}</span>
                                                    {row.tooltip && (
                                                        <span className="group relative">
                                                            <Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                                                            <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-1.5 text-xs bg-popover border border-border rounded-lg shadow-lg opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-20">
                                                                {row.tooltip}
                                                            </span>
                                                        </span>
                                                    )}
                                                </div>
                                                {(["free", "starter", "professional", "enterprise"] as const).map(tier => {
                                                    const val = row[tier]
                                                    return (
                                                        <div key={tier} className="px-3 py-3 flex items-center justify-center">
                                                            {val === true ? (
                                                                <Check className="h-4 w-4 text-primary" />
                                                            ) : val === false ? (
                                                                <Minus className="h-4 w-4 text-muted-foreground/40" />
                                                            ) : (
                                                                <span className={cn(
                                                                    "text-sm font-medium",
                                                                    val === "Unlimited" ? "text-primary" : "",
                                                                    val === "-" ? "text-muted-foreground/40" : ""
                                                                )}>
                                                                    {typeof val === "number" ? val.toLocaleString() : val}
                                                                </span>
                                                            )}
                                                        </div>
                                                    )
                                                })}
                                            </div>
                                        ))}
                                    </div>
                                )
                            })}
                        </div>

                        {/* CTA */}
                        <div className="text-center mt-12">
                            <p className="text-muted-foreground mb-4">Need higher limits or a custom plan?</p>
                            <Button className="bg-gradient-to-r from-indigo-600 to-blue-500 font-bold shadow-[0_0_20px_rgba(79,70,229,0.3)] text-white hover:shadow-[0_0_30px_rgba(79,70,229,0.5)] transition-all">
                                Talk to Sales <ArrowRight className="ml-2 h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                )

            case "individual":
                return (
                    <div>
                        <div className="text-center mb-12">
                            <h1 className="text-4xl font-bold mb-4">Individual & Start-Up</h1>
                            <p className="text-muted-foreground">
                                Perfect for new ISPs and small teams just getting started.
                            </p>
                        </div>

                        <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
                            {Object.entries(individualPlans).map(([key, plan]) => (
                                <div key={key} className={cn(
                                    "border rounded-2xl p-8",
                                    key === "growth" ? "border-primary bg-primary/5" : "border-border bg-card"
                                )}>
                                    {key === "growth" && (
                                        <div className="text-xs font-bold text-primary uppercase tracking-[2px] mb-2">
                                            Most Popular
                                        </div>
                                    )}
                                    <h2 className="text-2xl font-bold mb-2">{plan.name}</h2>
                                    <p className="text-sm text-muted-foreground mb-6">{plan.description}</p>

                                    <div className="mb-6">
                                        <div className="flex items-baseline gap-1">
                                            <span className="text-4xl font-bold">
                                                {plan.basePrice === 0 ? "Free" : `R${!isClient ? "--" : plan.basePrice.toLocaleString()}`}
                                            </span>
                                            {plan.basePrice > 0 && <span className="text-muted-foreground">/mo</span>}
                                        </div>
                                    </div>

                                    <Button className={cn(
                                        "w-full mb-6",
                                        key === "growth"
                                            ? "bg-gradient-to-r from-indigo-600 to-blue-500 font-bold shadow-[0_0_20px_rgba(79,70,229,0.3)] text-white hover:shadow-[0_0_30px_rgba(79,70,229,0.5)] transition-all"
                                            : "bg-secondary"
                                    )}>
                                        {plan.basePrice === 0 ? "Get started free" : "Start trial"}
                                    </Button>

                                    <ul className="space-y-3">
                                        {plan.features.map((feat, idx) => (
                                            <li key={idx} className="flex items-center gap-3 text-sm">
                                                <Check className="h-4 w-4 text-primary" />
                                                <span>{feat}</span>
                                            </li>
                                        ))}
                                        {plan.limitations.map((limit, idx) => (
                                            <li key={idx} className="flex items-center gap-3 text-sm text-muted-foreground">
                                                <X className="h-4 w-4" />
                                                <span>{limit}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            ))}
                        </div>
                    </div>
                )

            default:
                // Individual product pricing
                const product = modules.find(m => m.id === activeView)
                if (!product) return null

                return (
                    <div>
                        <div className="flex items-center gap-4 mb-8">
                            <div className={cn("h-12 w-12 rounded-xl bg-gradient-to-br flex items-center justify-center", product.color)}>
                                <product.icon className="h-6 w-6 text-white" />
                            </div>
                            <div>
                                <h1 className="text-3xl font-bold">{product.name}</h1>
                                <p className="text-muted-foreground">
                                    Comprehensive tools for {product.category.toLowerCase()} management.
                                </p>
                            </div>
                        </div>

                        <div className="grid md:grid-cols-2 gap-8 max-w-4xl">
                            {(["professional", "enterprise"] as const).map(tier => {
                                const price = tier === "professional" ? product.professionalPrice : product.enterprisePrice
                                const annualPrice = Math.round(price * 0.8)
                                return (
                                    <div key={tier} className="border border-border rounded-2xl bg-card p-8">
                                        <h2 className="text-xl font-bold mb-2 capitalize">{product.name.replace(" Hub", "")} {tier}</h2>
                                        <p className="text-sm text-muted-foreground mb-6">
                                            {tier === "professional"
                                                ? "Essential features for growing teams."
                                                : "Advanced capabilities for scaling operations."}
                                        </p>

                                        <div className="mb-4">
                                            <span className="text-xs text-muted-foreground">Starts at</span>
                                            <div className="flex items-baseline gap-1">
                                                <span className="text-3xl font-bold">
                                                    R{billingPeriod === "annually" ? annualPrice : price}
                                                </span>
                                                <span className="text-muted-foreground">/mo</span>
                                            </div>
                                        </div>

                                        <p className="text-sm text-muted-foreground mb-6">
                                            Includes 1 Core Seat. Additional seats at R{tier === "professional" ? "45" : "75"}/mo
                                        </p>

                                        <div className="flex gap-2 mb-6">
                                            <button
                                                onClick={() => setBillingPeriod("monthly")}
                                                className={cn(
                                                    "flex-1 py-2 text-xs font-medium rounded-lg border transition-colors",
                                                    billingPeriod === "monthly" ? "bg-secondary border-border" : "border-border hover:bg-secondary/50"
                                                )}
                                            >
                                                Pay Monthly
                                            </button>
                                            <button
                                                onClick={() => setBillingPeriod("annually")}
                                                className={cn(
                                                    "flex-1 py-2 text-xs font-medium rounded-lg border transition-colors",
                                                    billingPeriod === "annually" ? "bg-secondary border-border" : "border-border hover:bg-secondary/50"
                                                )}
                                            >
                                                <div>Pay Annually</div>
                                                <div className="text-emerald-500 text-[10px]">BEST VALUE</div>
                                            </button>
                                        </div>

                                        <Button className={cn(
                                            "w-full mb-3",
                                            tier === "enterprise"
                                                ? "bg-gradient-to-r from-indigo-600 to-blue-500 font-bold shadow-[0_0_20px_rgba(79,70,229,0.3)] text-white hover:shadow-[0_0_30px_rgba(79,70,229,0.5)] transition-all"
                                                : "bg-secondary"
                                        )}>
                                            {tier === "enterprise" ? "Talk to Sales" : "Buy now"}
                                        </Button>

                                        {tier === "professional" && (
                                            <Button variant="outline" className="w-full">
                                                Talk to Sales
                                            </Button>
                                        )}
                                    </div>
                                )
                            })}
                        </div>

                        {/* Features comparison could go here */}
                        <div className="mt-16">
                            <h2 className="text-2xl font-bold mb-8">Features</h2>
                            <p className="text-muted-foreground">
                                <Link href={`/products/${product.slug}`} className="text-primary underline">
                                    See full feature comparison →
                                </Link>
                            </p>
                        </div>
                    </div>
                )
        }
    }

    return (
        <div className="min-h-screen bg-background relative">
            {/* Flickering Grid Background */}
            <div className="fixed top-0 left-0 z-0 w-full h-[300px] [mask-image:linear-gradient(to_top,transparent_25%,black_95%)] pointer-events-none">
                <FlickeringGrid
                    className="absolute top-0 left-0 size-full"
                    squareSize={4}
                    gridGap={6}
                    color="#6B7280"
                    maxOpacity={0.15}
                    flickerChance={0.05}
                />
            </div>

            {/* Top Nav */}
            <nav className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur-xl">
                <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
                    <div className="flex h-auto items-center justify-between py-3">
                        <Link href="/" className="flex items-center gap-3 group">
                            <img src="/logo-new.svg" alt="OmniDome" className="h-12 w-12 transition-all group-hover:scale-110" />
                            <div className="flex flex-col">
                              <span className="font-bold text-white">OmniDome</span>
                            </div>
                        </Link>

                        {/* Audience Toggle */}
                        <div className="flex items-center gap-4">
                            <div className="hidden sm:flex items-center border-b-2 border-transparent">
                                <button
                                    onClick={() => setAudienceTab("business")}
                                    className={cn(
                                        "px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-[2px]",
                                        audienceTab === "business"
                                            ? "border-indigo-500 text-indigo-400"
                                            : "border-transparent text-muted-foreground hover:text-foreground"
                                    )}
                                >
                                    For businesses & enterprises
                                </button>
                                <button
                                    onClick={() => {
                                        setAudienceTab("individual")
                                        setActiveView("individual")
                                    }}
                                    className={cn(
                                        "px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-[2px]",
                                        audienceTab === "individual"
                                            ? "border-indigo-500 text-indigo-400"
                                            : "border-transparent text-muted-foreground hover:text-foreground"
                                    )}
                                >
                                    For individuals & small teams
                                </button>
                            </div>
                        </div>

                        <div className="flex items-center gap-4">
                            <ThemeToggleCompact />
                            <Link href="/auth">
                                <Button size="sm" className="bg-gradient-to-r from-indigo-600 to-blue-500 font-bold shadow-[0_0_20px_rgba(79,70,229,0.3)] text-white hover:shadow-[0_0_30px_rgba(79,70,229,0.5)] transition-all">
                                    Start free or get a demo
                                </Button>
                            </Link>
                        </div>
                    </div>
                </div>
            </nav>

            <div className="flex">
                {/* Sidebar */}
                <aside className="hidden lg:block w-64 border-r border-border bg-card min-h-[calc(100vh-64px)] sticky top-16 overflow-y-auto">
                    <div className="p-6 space-y-8">
                        {/* Platform Solutions */}
                        <div>
                            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4">
                                Platform Solutions
                            </h3>
                            <ul className="space-y-1">
                                <li>
                                    <button
                                        onClick={() => setActiveView("customer-platform")}
                                        className={cn(
                                            "w-full text-left px-3 py-2 text-sm rounded-lg transition-colors",
                                            activeView === "customer-platform"
                                                ? "bg-primary/10 text-primary border-primary/20"
                                                : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                                        )}
                                    >
                                        Customer Platform
                                    </button>
                                </li>
                                <li>
                                    <button
                                        onClick={() => setActiveView("create-bundle")}
                                        className={cn(
                                            "w-full text-left px-3 py-2 text-sm rounded-lg transition-colors",
                                            activeView === "create-bundle"
                                                ? "bg-primary/10 text-primary border-primary/20"
                                                : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                                        )}
                                    >
                                        Create a Bundle
                                    </button>
                                </li>
                                <li>
                                    <button
                                        onClick={() => setActiveView("individual")}
                                        className={cn(
                                            "w-full text-left px-3 py-2 text-sm rounded-lg transition-colors",
                                            activeView === "individual"
                                                ? "bg-primary/10 text-primary border-primary/20"
                                                : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                                        )}
                                    >
                                        Individual & Start-Up
                                    </button>
                                </li>
                                <li>
                                    <button
                                        onClick={() => setActiveView("usage-limits")}
                                        className={cn(
                                            "w-full text-left px-3 py-2 text-sm rounded-lg transition-colors flex items-center gap-2",
                                            activeView === "usage-limits"
                                                ? "bg-primary/10 text-primary border-primary/20"
                                                : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                                        )}
                                    >
                                        <BarChart3 className="h-4 w-4" />
                                        Usage & Limits
                                    </button>
                                </li>
                            </ul>
                        </div>

                        {/* Products */}
                        <div>
                            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4">
                                Products
                            </h3>
                            <ul className="space-y-1">
                                {modules.map(mod => (
                                    <li key={mod.id}>
                                        <button
                                            onClick={() => setActiveView(mod.id)}
                                            className={cn(
                                                "w-full text-left px-3 py-2 text-sm rounded-lg transition-colors flex items-center gap-2",
                                                activeView === mod.id
                                                    ? "bg-primary/10 text-primary font-medium border-l-2 border-primary"
                                                    : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                                            )}
                                        >
                                            <mod.icon className="h-4 w-4" />
                                            {mod.name.replace(" Hub", "")}
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        </div>

                        {/* Enhancements */}
                        <div>
                            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4">
                                Enhancements
                            </h3>
                            <ul className="space-y-1">
                                <li>
                                    <button className="w-full text-left px-3 py-2 text-sm rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary/50">
                                        API Access
                                    </button>
                                </li>
                                <li>
                                    <button className="w-full text-left px-3 py-2 text-sm rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary/50">
                                        Premium Support
                                    </button>
                                </li>
                            </ul>
                        </div>
                    </div>
                </aside>

                {/* Main Content */}
                <main className="flex-1 p-8 lg:p-12">
                    <div className="max-w-6xl mx-auto">
                        {renderMainContent()}
                    </div>
                </main>
            </div>
        </div>
    )
}
