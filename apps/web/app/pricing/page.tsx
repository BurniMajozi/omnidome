"use client"

import { useState, useMemo, useEffect } from "react"
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
    Package,
    Globe,
    HeartHandshake,
    Check,
    ArrowLeft,
    ChevronDown,
    Sparkles,
    ArrowRight,
    X
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

// All 13 modules (excluding Dashboard Overview)
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
        name: "Talent Hub",
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
type ViewType = "customer-platform" | "create-bundle" | "individual" | string

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
    const [mounted, setMounted] = useState(false)

    useEffect(() => {
        setMounted(true)
    }, [])

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

    const getPrice = (module: typeof modules[0], tier: TierType) => {
        const price = tier === "starter" ? module.starterPrice
            : tier === "professional" ? module.professionalPrice
                : module.enterprisePrice
        return billingPeriod === "annually" ? Math.round(price * 0.8) : price
    }

    const selectedProducts = useMemo(() => {
        return Object.entries(selectedModules)
            .filter(([_, tier]) => tier !== null)
            .map(([id, tier]) => {
                const mod = modules.find(m => m.id === id)!
                return { ...mod, selectedTier: tier! }
            })
    }, [selectedModules])

    const totalMonthly = useMemo(() => {
        return selectedProducts.reduce((acc, prod) => {
            return acc + getPrice(prod, prod.selectedTier)
        }, 0)
    }, [selectedProducts, billingPeriod])

    const sidebarItems = [
        { id: "customer-platform", label: "Customer Platform", type: "platform" },
        { id: "create-bundle", label: "Create a Bundle", type: "platform" },
        { id: "individual", label: "Individual & Start-Up", type: "platform" },
        ...modules.map(m => ({ id: m.id, label: m.name, type: "product" })),
        { id: "api-access", label: "API Access", type: "enhancement" },
        { id: "premium-support", label: "Premium Support", type: "enhancement" }
    ]

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
                                            <span className="text-3xl font-bold">R{!mounted ? "--" : (billingPeriod === "annually" ? bundle.annualPrice.toLocaleString() : bundle.basePrice.toLocaleString())}</span>
                                            <span className="text-muted-foreground">/mo</span>
                                        </div>
                                        {billingPeriod === "annually" && mounted && (
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

                                    <p className="text-xs text-muted-foreground mb-6">{!mounted ? "--" : bundle.credits.toLocaleString()} OmniDome Credits</p>

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
                                                Includes {!mounted ? "--" : mod.customers.toLocaleString()} customers. Additional customers sold in increments of 1,000 from R50/month.
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
                                                <div className="text-2xl font-bold">R{!mounted ? "0" : totalMonthly.toLocaleString()}</div>
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
                                                {plan.basePrice === 0 ? "Free" : `R${!mounted ? "--" : plan.basePrice.toLocaleString()}`}
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
        <div className="min-h-screen bg-background">
            {/* Top Nav */}
            <nav className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur-xl">
                <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
                    <div className="flex h-16 items-center justify-between">
                        <Link href="/" className="flex items-center gap-2">
                            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-500">
                                <Wifi className="h-4 w-4 text-white" />
                            </div>
                            <span className="font-bold">OmniDome</span>
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
                            <Link href="/dashboard">
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
