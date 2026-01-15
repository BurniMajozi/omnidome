"use client"

import { useState } from "react"
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
    ArrowRight,
    Sparkles,
    Menu,
    X,
    ChevronDown,
    Star,
    Zap,
    Shield,
    BarChart3,
    Brain,
    BookOpen,
    Building2,
    GraduationCap,
    Handshake,
    FileText,
    HelpCircle,
    Rocket
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

// All 13 modules (excluding Dashboard Overview)
const modules = [
    {
        id: "communication",
        icon: MessageSquare,
        name: "Communication Hub",
        description: "Team collaboration, internal messaging, and unified communications.",
        category: "Core",
        color: "from-blue-600 via-indigo-500 to-violet-500",
        slug: "communication"
    },
    {
        id: "sales",
        icon: DollarSign,
        name: "Sales Hub",
        description: "Deal pipeline, revenue tracking, quote generation.",
        category: "Revenue",
        color: "from-emerald-500 via-teal-400 to-cyan-500",
        slug: "sales"
    },
    {
        id: "crm",
        icon: Users,
        name: "CRM Hub",
        description: "Customer relationship management and journey analytics.",
        category: "Customer",
        color: "from-indigo-600 via-violet-500 to-purple-500",
        slug: "crm"
    },
    {
        id: "service",
        icon: Headset,
        name: "Service Hub",
        description: "Ticket management, SLA tracking, knowledge base.",
        category: "Customer",
        color: "from-orange-500 via-amber-400 to-yellow-500",
        slug: "support"
    },
    {
        id: "retention",
        icon: HeartHandshake,
        name: "Retention Hub",
        description: "AI-powered churn prediction and CLV analysis.",
        category: "Analytics",
        color: "from-rose-500 via-pink-500 to-fuchsia-500",
        slug: "retention"
    },
    {
        id: "network",
        icon: Wifi,
        name: "Network Ops Hub",
        description: "Real-time monitoring, outage alerts, capacity planning.",
        category: "Operations",
        color: "from-cyan-500 via-blue-500 to-indigo-500",
        slug: "network"
    },
    {
        id: "call-center",
        icon: Phone,
        name: "Call Center Hub",
        description: "Inbound/outbound call management and agent performance.",
        category: "Customer",
        color: "from-blue-600 via-indigo-600 to-violet-600",
        slug: "call-center"
    },
    {
        id: "marketing",
        icon: Megaphone,
        name: "Marketing Hub",
        description: "Campaign management, email marketing, analytics.",
        category: "Revenue",
        color: "from-fuchsia-600 via-purple-600 to-indigo-600",
        slug: "marketing"
    },
    {
        id: "compliance",
        icon: ShieldCheck,
        name: "Compliance Hub",
        description: "RICA verification, POPIA compliance, audit trails.",
        category: "Operations",
        color: "from-slate-400 via-slate-500 to-slate-600",
        slug: "compliance"
    },
    {
        id: "talent",
        icon: UserCog,
        name: "Talent Hub",
        description: "HR management, recruitment, performance reviews.",
        category: "Operations",
        color: "from-yellow-500 via-amber-500 to-orange-500",
        slug: "talent"
    },
    {
        id: "billing",
        icon: Receipt,
        name: "Billing Hub",
        description: "Invoice management, payment processing, collections.",
        category: "Revenue",
        color: "from-teal-500 via-emerald-500 to-green-500",
        slug: "billing"
    },
    {
        id: "products",
        icon: Package,
        name: "Product Hub",
        description: "Product catalog, pricing management, bundling.",
        category: "Operations",
        color: "from-violet-600 via-purple-600 to-fuchsia-600",
        slug: "products"
    },
    {
        id: "portal",
        icon: Globe,
        name: "Portal Hub",
        description: "Customer self-service portal and white-label configurations.",
        category: "Core",
        color: "from-sky-400 via-blue-500 to-indigo-600",
        slug: "portal"
    },
]

// Solutions grouped by category with colors
const solutionsByCategory: Record<string, { title: string; description: string; slug: string; icon: any; color: string }[]> = {
    Core: [
        { title: "Unified Communications", description: "Bring all team communications into one platform", slug: "communication", icon: MessageSquare, color: "from-blue-500 to-cyan-500" },
        { title: "Self-Service Portal", description: "White-label customer portal with your branding", slug: "portal", icon: Globe, color: "from-sky-500 to-blue-500" },
    ],
    Revenue: [
        { title: "Accelerate Sales", description: "Close deals faster with AI-powered insights", slug: "sales", icon: DollarSign, color: "from-green-500 to-emerald-500" },
        { title: "Marketing Automation", description: "Generate and nurture leads at scale", slug: "marketing", icon: Megaphone, color: "from-fuchsia-500 to-pink-500" },
        { title: "Automated Billing", description: "Streamline invoicing and collections", slug: "billing", icon: Receipt, color: "from-teal-500 to-green-500" },
    ],
    Customer: [
        { title: "360° Customer View", description: "Complete visibility into customer relationships", slug: "crm", icon: Users, color: "from-violet-500 to-purple-500" },
        { title: "Omnichannel Support", description: "Deliver exceptional service across all channels", slug: "support", icon: Headset, color: "from-orange-500 to-amber-500" },
        { title: "Call Center Excellence", description: "Empower agents with intelligent tools", slug: "call-center", icon: Phone, color: "from-indigo-500 to-violet-500" },
    ],
    Operations: [
        { title: "Network Monitoring", description: "Real-time visibility into infrastructure health", slug: "network", icon: Wifi, color: "from-cyan-500 to-blue-500" },
        { title: "SA Compliance", description: "RICA and POPIA compliance built-in", slug: "compliance", icon: ShieldCheck, color: "from-slate-500 to-zinc-500" },
        { title: "Team Management", description: "HR, recruitment, and performance tracking", slug: "talent", icon: UserCog, color: "from-amber-500 to-yellow-500" },
        { title: "Product Catalog", description: "Manage packages, pricing, and bundles", slug: "products", icon: Package, color: "from-purple-500 to-indigo-500" },
    ],
    Analytics: [
        { title: "Churn Prevention", description: "87% accurate AI prediction to stop churn", slug: "retention", icon: HeartHandshake, color: "from-rose-500 to-pink-500" },
    ]
}

// Resources
const resourceItems = {
    featured: [
        { icon: Sparkles, title: "Why OmniDome", description: "See what makes us different", href: "/resources/why-omnidome" },
        { icon: BookOpen, title: "Blog", description: "Latest insights and updates", href: "#" },
        { icon: FileText, title: "Documentation", description: "Technical guides and API docs", href: "#" },
    ],
    services: [
        { icon: Rocket, title: "Onboarding", description: "Get up and running quickly", href: "/resources/services", price: "From R15,000" },
        { icon: GraduationCap, title: "Customer Training", description: "Master every module", href: "/resources/services", price: "From R8,000" },
        { icon: Zap, title: "Migration", description: "Seamless data transfer", href: "/resources/services", price: "From R12,000" },
    ],
    partners: [
        { icon: Handshake, title: "Reseller Program", description: "Earn up to 35% commission", href: "/resources/partners", price: "R5,000/year" },
        { icon: Building2, title: "Solutions Partner", description: "Implementation & consulting", href: "/resources/partners", price: "R15,000/year" },
        { icon: Zap, title: "Integration Partner", description: "Build apps and integrations", href: "/resources/partners", price: "R8,000/year" },
    ]
}

export default function LandingPage() {
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
    const [productMenuOpen, setProductMenuOpen] = useState(false)
    const [solutionMenuOpen, setSolutionMenuOpen] = useState(false)
    const [resourceMenuOpen, setResourceMenuOpen] = useState(false)

    return (
        <div className="min-h-screen bg-[#020617] text-slate-100 selection:bg-indigo-500/30 overflow-x-hidden">
            {/* Grid Pattern Background */}
            <div className="fixed inset-0 z-0 pointer-events-none opacity-20 grid-pattern" />
            {/* Top Bar */}
            <div className="relative z-10 bg-slate-900/50 backdrop-blur-md border-b border-slate-800/50 py-2 px-4 text-xs text-center sm:text-right">
                <div className="max-w-7xl mx-auto flex justify-center sm:justify-end gap-6">
                    <a href="#" className="text-slate-400 hover:text-indigo-400 transition-colors">Documentation</a>
                    <a href="#" className="text-slate-400 hover:text-indigo-400 transition-colors">Developer Portal</a>
                    <a href="#" className="text-slate-400 hover:text-indigo-400 transition-colors">Support</a>
                </div>
            </div>

            {/* Navigation */}
            <nav className="sticky top-0 z-50 border-b border-slate-800/50 bg-[#020617]/80 backdrop-blur-xl">
                <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
                    <div className="flex h-16 items-center justify-between">
                        <div className="flex items-center gap-10">
                            <Link href="/" className="flex items-center gap-2 group">
                                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-blue-500 to-cyan-400 shadow-[0_0_20px_rgba(79,70,229,0.4)] group-hover:shadow-[0_0_30px_rgba(79,70,229,0.6)] transition-all duration-300">
                                    <Wifi className="h-5 w-5 text-white" />
                                </div>
                                <span className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
                                    OmniDome
                                </span>
                            </Link>

                            {/* Desktop Nav */}
                            <div className="hidden lg:flex items-center gap-1">
                                {/* Product - Mega Menu */}
                                <div
                                    className="relative"
                                    onMouseEnter={() => setProductMenuOpen(true)}
                                    onMouseLeave={() => setProductMenuOpen(false)}
                                >
                                    <button className="flex items-center gap-1 text-sm font-medium text-slate-300 hover:text-white transition-all px-4 py-5">
                                        Product <ChevronDown className={cn("h-4 w-4 transition-transform", productMenuOpen && "rotate-180")} />
                                    </button>

                                    {/* Product Mega Menu */}
                                    <div className={cn(
                                        "fixed left-0 right-0 bg-slate-950/95 backdrop-blur-2xl border-b border-slate-800 shadow-[0_20px_50px_rgba(0,0,0,0.5)] transition-all duration-300 ease-out mega-menu-top",
                                        productMenuOpen ? "opacity-100 translate-y-0 visible" : "opacity-0 -translate-y-2 invisible pointer-events-none"
                                    )}>
                                        <div className="max-w-7xl mx-auto px-8 py-10">
                                            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                                                {modules.map(mod => (
                                                    <Link
                                                        key={mod.id}
                                                        href={`/products/${mod.slug}`}
                                                        className="group flex items-start gap-4 p-4 rounded-xl hover:bg-white/5 transition-all outline-none focus:ring-2 focus:ring-indigo-500/50"
                                                    >
                                                        <div className={cn(
                                                            "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br shadow-[0_4px_12px_rgba(0,0,0,0.1)] group-hover:scale-110 group-hover:shadow-[0_4px_20px_rgba(0,0,0,0.2)] transition-all duration-300",
                                                            mod.color
                                                        )}>
                                                            <mod.icon className="h-5.5 w-5.5 text-white" />
                                                        </div>
                                                        <div className="min-w-0">
                                                            <div className="font-bold text-sm text-slate-100 group-hover:text-indigo-400 transition-colors">
                                                                {mod.name}
                                                            </div>
                                                            <p className="text-[11px] text-slate-500 line-clamp-2 mt-1 leading-relaxed group-hover:text-slate-400 transition-colors">
                                                                {mod.description}
                                                            </p>
                                                        </div>
                                                    </Link>
                                                ))}
                                            </div>

                                            <div className="mt-8 pt-6 border-t border-border flex items-center justify-between">
                                                <div className="text-sm text-muted-foreground">
                                                    <span className="font-semibold text-foreground">13 integrated modules</span> designed for ISP operations
                                                </div>
                                                <Link href="/pricing">
                                                    <Button size="sm" className="bg-gradient-to-r from-indigo-600 to-blue-500 font-bold shadow-[0_0_20px_rgba(79,70,229,0.3)] text-white hover:shadow-[0_0_30px_rgba(79,70,229,0.5)] transition-all">
                                                        View Pricing <ArrowRight className="ml-2 h-4 w-4" />
                                                    </Button>
                                                </Link>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Solution - Mega Menu */}
                                <div
                                    className="relative"
                                    onMouseEnter={() => setSolutionMenuOpen(true)}
                                    onMouseLeave={() => setSolutionMenuOpen(false)}
                                >
                                    <button className="flex items-center gap-1 text-sm font-medium text-slate-300 hover:text-white transition-all px-4 py-5">
                                        Solution <ChevronDown className={cn("h-4 w-4 transition-transform", solutionMenuOpen && "rotate-180")} />
                                    </button>

                                    {/* Solution Mega Menu */}
                                    <div className={cn(
                                        "fixed left-0 right-0 bg-slate-950/95 backdrop-blur-2xl border-b border-slate-800 shadow-[0_20px_50px_rgba(0,0,0,0.5)] transition-all duration-300 ease-out mega-menu-top",
                                        solutionMenuOpen ? "opacity-100 translate-y-0 visible" : "opacity-0 -translate-y-2 invisible pointer-events-none"
                                    )}>
                                        <div className="max-w-7xl mx-auto px-8 py-10">
                                            <div className="grid grid-cols-5 gap-8">
                                                {Object.entries(solutionsByCategory).map(([category, solutions]) => (
                                                    <div key={category}>
                                                        <h3 className="text-[10px] font-bold text-indigo-400 uppercase tracking-[2px] mb-6">
                                                            {category}
                                                        </h3>
                                                        <div className="space-y-5">
                                                            {solutions.map(sol => (
                                                                <Link
                                                                    key={sol.slug}
                                                                    href={`/solutions/${sol.slug}`}
                                                                    className="flex items-start gap-4 group"
                                                                >
                                                                    <div className={cn(
                                                                        "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br shadow-inner group-hover:scale-105 transition-all duration-300",
                                                                        sol.color
                                                                    )}>
                                                                        <sol.icon className="h-4.5 w-4.5 text-white" />
                                                                    </div>
                                                                    <div>
                                                                        <div className="font-bold text-sm text-slate-100 group-hover:text-indigo-400 transition-colors">
                                                                            {sol.title}
                                                                        </div>
                                                                        <p className="text-[11px] text-slate-500 mt-1 leading-snug group-hover:text-slate-400 transition-colors">
                                                                            {sol.description}
                                                                        </p>
                                                                    </div>
                                                                </Link>
                                                            ))}
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>

                                            <div className="mt-8 pt-6 border-t border-border">
                                                <Link href="/resources/why-omnidome" className="inline-flex items-center gap-2 text-sm font-medium text-indigo-400 hover:text-indigo-300 hover:underline transition-colors">
                                                    Learn why ISPs choose OmniDome <ArrowRight className="h-4 w-4" />
                                                </Link>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Price */}
                                <Link href="/pricing" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors px-4 py-5">
                                    Price
                                </Link>

                                {/* Resources - Mega Menu */}
                                <div
                                    className="relative"
                                    onMouseEnter={() => setResourceMenuOpen(true)}
                                    onMouseLeave={() => setResourceMenuOpen(false)}
                                >
                                    <button className="flex items-center gap-1 text-sm font-medium text-slate-300 hover:text-white transition-all px-4 py-5 font-bold">
                                        Resources <ChevronDown className={cn("h-4 w-4 transition-transform", resourceMenuOpen && "rotate-180")} />
                                    </button>

                                    {/* Resources Mega Menu */}
                                    <div className={cn(
                                        "fixed left-0 right-0 bg-slate-950/95 backdrop-blur-2xl border-b border-slate-800 shadow-[0_20px_50px_rgba(0,0,0,0.5)] transition-all duration-300 ease-out mega-menu-top",
                                        resourceMenuOpen ? "opacity-100 translate-y-0 visible" : "opacity-0 -translate-y-2 invisible pointer-events-none"
                                    )}>
                                        <div className="max-w-7xl mx-auto px-8 py-10">
                                            <div className="grid grid-cols-3 gap-12">
                                                {/* Featured Links */}
                                                <div>
                                                    <h3 className="text-xs font-bold text-indigo-400 uppercase tracking-[2px] mb-4">
                                                        Featured
                                                    </h3>
                                                    <div className="space-y-4">
                                                        {resourceItems.featured.map(item => (
                                                            <Link
                                                                key={item.title}
                                                                href={item.href}
                                                                className="flex items-start gap-3 group"
                                                            >
                                                                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-secondary group-hover:bg-indigo-500/10">
                                                                    <item.icon className="h-5 w-5 text-muted-foreground group-hover:text-indigo-400" />
                                                                </div>
                                                                <div>
                                                                    <div className="font-medium text-sm group-hover:text-indigo-400 transition-colors">
                                                                        {item.title}
                                                                    </div>
                                                                    <p className="text-xs text-muted-foreground">
                                                                        {item.description}
                                                                    </p>
                                                                </div>
                                                            </Link>
                                                        ))}
                                                    </div>
                                                </div>

                                                {/* Services */}
                                                <div>
                                                    <h3 className="text-xs font-semibold text-indigo-400 uppercase tracking-[2px] font-bold">
                                                        Services
                                                    </h3>
                                                    <div className="space-y-4">
                                                        {resourceItems.services.map(item => (
                                                            <Link
                                                                key={item.title}
                                                                href={item.href}
                                                                className="flex items-start gap-3 group"
                                                            >
                                                                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-secondary group-hover:bg-indigo-500/10">
                                                                    <item.icon className="h-5 w-5 text-muted-foreground group-hover:text-indigo-400" />
                                                                </div>
                                                                <div>
                                                                    <div className="font-medium text-sm group-hover:text-indigo-400 transition-colors">
                                                                        {item.title}
                                                                    </div>
                                                                    <p className="text-xs text-muted-foreground">
                                                                        {item.description}
                                                                    </p>
                                                                    <span className="text-xs font-medium text-indigo-400 font-bold mt-1 inline-block">
                                                                        {item.price}
                                                                    </span>
                                                                </div>
                                                            </Link>
                                                        ))}
                                                    </div>
                                                </div>

                                                {/* Partners */}
                                                <div>
                                                    <h3 className="text-xs font-semibold text-indigo-400 uppercase tracking-[2px] font-bold">
                                                        Partners
                                                    </h3>
                                                    <div className="space-y-4">
                                                        {resourceItems.partners.map(item => (
                                                            <Link
                                                                key={item.title}
                                                                href={item.href}
                                                                className="flex items-start gap-3 group"
                                                            >
                                                                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-secondary group-hover:bg-indigo-500/10">
                                                                    <item.icon className="h-5 w-5 text-muted-foreground group-hover:text-indigo-400" />
                                                                </div>
                                                                <div>
                                                                    <div className="font-medium text-sm group-hover:text-indigo-400 transition-colors">
                                                                        {item.title}
                                                                    </div>
                                                                    <p className="text-xs text-muted-foreground">
                                                                        {item.description}
                                                                    </p>
                                                                    <span className="text-xs font-medium text-indigo-400 font-bold mt-1 inline-block">
                                                                        {item.price}
                                                                    </span>
                                                                </div>
                                                            </Link>
                                                        ))}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className="flex items-center gap-4">
                            <Link href="/dashboard" className="hidden sm:block text-sm font-bold text-slate-300 hover:text-white transition-colors">
                                Log in
                            </Link>
                            <Link href="/dashboard">
                                <Button size="sm" className="bg-indigo-600 hover:bg-indigo-500 text-white font-bold px-6 shadow-[0_0_20px_rgba(79,70,229,0.3)] hover:shadow-[0_0_25px_rgba(79,70,229,0.5)] transition-all">
                                    Get Started
                                </Button>
                            </Link>
                            <button className="lg:hidden p-2 text-slate-300 transition-colors hover:text-white" onClick={() => setMobileMenuOpen(!mobileMenuOpen)} title="Toggle menu">
                                {mobileMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
                            </button>
                        </div>
                    </div>
                </div>

                {/* Mobile menu */}
                {mobileMenuOpen && (
                    <div className="lg:hidden border-t border-border bg-card p-6 space-y-4">
                        <Link href="/pricing" className="block font-medium py-2">Pricing</Link>
                        <Link href="/resources/services" className="block font-medium py-2">Services</Link>
                        <Link href="/resources/partners" className="block font-medium py-2">Partners</Link>
                        <div className="border-t border-border pt-4 mt-4">
                            <Link href="/dashboard" className="block text-center mb-4 font-medium">Sign In</Link>
                            <Button className="w-full bg-gradient-to-r from-indigo-600 to-blue-500 shadow-[0_0_25px_rgba(79,70,229,0.3)] hover:shadow-[0_0_35px_rgba(79,70,229,0.5)] transition-all">Get Started</Button>
                        </div>
                    </div>
                )}
            </nav>

            {/* Hero Section */}
            <section className="relative pt-32 pb-24 lg:pt-48 lg:pb-32 overflow-hidden">
                {/* Background Glows */}
                <div className="absolute top-0 right-[-10%] w-[600px] h-[600px] bg-indigo-600/20 blur-[130px] rounded-full pointer-events-none animate-pulse" />
                <div className="absolute bottom-[-10%] left-[-10%] w-[600px] h-[600px] bg-blue-600/10 blur-[130px] rounded-full pointer-events-none" />

                <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 text-center relative z-10">
                    <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-black tracking-[2px] uppercase mb-10 overflow-hidden group">
                        <Sparkles className="h-3.5 w-3.5 animate-bounce" />
                        <span>Next-Gen ISP Operating System</span>
                        <div className="absolute inset-x-0 bottom-0 h-[1px] bg-gradient-to-r from-transparent via-indigo-500 to-transparent" />
                    </div>

                    <h1 className="text-5xl lg:text-8xl font-black tracking-tight text-white mb-8 leading-[1]">
                        Unify Your Entire ISP <br />
                        <span className="bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 via-blue-400 to-cyan-400 animate-gradient-x">
                            On One Powerful Platform
                        </span>
                    </h1>

                    <p className="mx-auto max-w-2xl text-lg lg:text-xl text-slate-400 mb-12 leading-relaxed font-medium">
                        Stop juggling disconnected tools. Manage sales, fiber networks, billing, and support with an integrated OS built specifically for the South African ISP market.
                    </p>

                    <div className="flex flex-col sm:flex-row items-center justify-center gap-6 mb-24">
                        <Link href="/dashboard">
                            <Button size="lg" className="h-16 px-10 text-xl font-black bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_40px_rgba(79,70,229,0.4)] transition-all duration-300 group overflow-hidden relative active:scale-95">
                                <span className="relative z-10 flex items-center gap-3">
                                    Start Your Free Trial <ArrowRight className="h-6 w-6 group-hover:translate-x-1.5 transition-transform" />
                                </span>
                                <div className="absolute inset-0 bg-gradient-to-r from-indigo-500 to-blue-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                            </Button>
                        </Link>
                        <Button size="lg" variant="outline" className="h-16 px-10 text-xl font-bold border-slate-700 bg-slate-900/50 hover:bg-slate-800 text-white backdrop-blur-md transition-all active:scale-95">
                            Schedule a Demo
                        </Button>
                    </div>

                    {/* Stats */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-12 max-w-5xl mx-auto border-t border-slate-800/50 pt-16">
                        <div className="group">
                            <div className="text-4xl lg:text-5xl font-black text-white mb-2 group-hover:text-indigo-400 transition-colors">13</div>
                            <div className="text-[10px] text-slate-500 uppercase tracking-[3px] font-black">Native Modules</div>
                        </div>
                        <div className="group">
                            <div className="text-4xl lg:text-5xl font-black text-white mb-2 group-hover:text-blue-400 transition-colors">87%</div>
                            <div className="text-[10px] text-slate-500 uppercase tracking-[3px] font-black">Churn Prediction</div>
                        </div>
                        <div className="group">
                            <div className="text-4xl lg:text-5xl font-black text-white mb-2 group-hover:text-cyan-400 transition-colors">2.4x</div>
                            <div className="text-[10px] text-slate-500 uppercase tracking-[3px] font-black">Sales Velocity</div>
                        </div>
                        <div className="group">
                            <div className="text-4xl lg:text-5xl font-black text-white mb-2 group-hover:text-indigo-400 transition-colors">100%</div>
                            <div className="text-[10px] text-slate-500 uppercase tracking-[3px] font-black">SA Compliant</div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Features/Why Section */}
            <section id="features" className="py-20 px-4 sm:px-6 lg:px-8 bg-card/50">
                <div className="mx-auto max-w-7xl">
                    <div className="text-center mb-16">
                        <h2 className="text-3xl sm:text-4xl font-bold mb-4">Why Choose OmniDome?</h2>
                        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                            Purpose-built for ISPs with everything you need to scale your operations
                        </p>
                    </div>

                    <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
                        <div className="rounded-2xl border border-border bg-card p-6 hover:border-indigo-500/50 hover:shadow-indigo-500/5 transition-all outline-none focus:ring-2 focus:ring-indigo-500/30">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 via-blue-500 to-cyan-400 shadow-[0_0_15px_rgba(79,70,229,0.2)]">
                                <Brain className="h-6 w-6 text-white" />
                            </div>
                            <h3 className="text-xl font-semibold mb-2">AI-Powered Insights</h3>
                            <p className="text-muted-foreground">
                                Predictive churn analytics, automated recommendations, and intelligent task creation.
                            </p>
                        </div>

                        <div className="rounded-2xl border border-border bg-card p-6 hover:border-indigo-500/50 hover:shadow-indigo-500/5 transition-all outline-none focus:ring-2 focus:ring-indigo-500/30">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center mb-4">
                                <Zap className="h-6 w-6 text-white" />
                            </div>
                            <h3 className="text-xl font-semibold mb-2">Real-Time Operations</h3>
                            <p className="text-muted-foreground">
                                Monitor network health, customer activity, and business metrics with live dashboards.
                            </p>
                        </div>

                        <div className="rounded-2xl border border-border bg-card p-6 hover:border-indigo-500/50 hover:shadow-indigo-500/5 transition-all outline-none focus:ring-2 focus:ring-indigo-500/30">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500 to-violet-500 flex items-center justify-center mb-4">
                                <BarChart3 className="h-6 w-6 text-white" />
                            </div>
                            <h3 className="text-xl font-semibold mb-2">Unified Analytics</h3>
                            <p className="text-muted-foreground">
                                Cross-module reporting, executive dashboards, and data-driven decision tools.
                            </p>
                        </div>

                        <div className="rounded-2xl border border-border bg-card p-6 hover:border-indigo-500/50 hover:shadow-indigo-500/5 transition-all outline-none focus:ring-2 focus:ring-indigo-500/30">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-rose-500 to-pink-500 flex items-center justify-center mb-4">
                                <HeartHandshake className="h-6 w-6 text-white" />
                            </div>
                            <h3 className="text-xl font-semibold mb-2">Retention Focus</h3>
                            <p className="text-muted-foreground">
                                Proactive churn prevention with AI risk scoring and automated retention campaigns.
                            </p>
                        </div>

                        <div className="rounded-2xl border border-border bg-card p-6 hover:border-indigo-500/50 hover:shadow-indigo-500/5 transition-all outline-none focus:ring-2 focus:ring-indigo-500/30">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center mb-4">
                                <Shield className="h-6 w-6 text-white" />
                            </div>
                            <h3 className="text-xl font-semibold mb-2">SA Compliance Ready</h3>
                            <p className="text-muted-foreground">
                                Built-in RICA verification, POPIA compliance, and South African regulatory requirements.
                            </p>
                        </div>

                        <div className="rounded-2xl border border-border bg-card p-6 hover:border-indigo-500/50 hover:shadow-indigo-500/5 transition-all outline-none focus:ring-2 focus:ring-indigo-500/30">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-blue-500 flex items-center justify-center mb-4">
                                <Globe className="h-6 w-6 text-white" />
                            </div>
                            <h3 className="text-xl font-semibold mb-2">White-Label Portal</h3>
                            <p className="text-muted-foreground">
                                Customizable customer portal with your branding for self-service and account management.
                            </p>
                        </div>
                    </div>
                </div>
            </section>

            {/* Modules Preview */}
            <section id="modules" className="py-20 px-4 sm:px-6 lg:px-8">
                <div className="mx-auto max-w-7xl">
                    <div className="text-center mb-12">
                        <h2 className="text-3xl sm:text-4xl font-bold mb-4">Platform Modules</h2>
                        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                            13 integrated modules designed to cover every aspect of ISP operations
                        </p>
                    </div>

                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                        {modules.slice(0, 8).map((module) => (
                            <Link
                                key={module.id}
                                href={`/products/${module.slug}`}
                                className="group rounded-2xl border border-border bg-card p-6 hover:border-emerald-500/50 hover:shadow-lg hover:shadow-emerald-500/5 transition-all"
                            >
                                <div className={cn(
                                    "w-12 h-12 rounded-xl bg-gradient-to-br flex items-center justify-center mb-4",
                                    module.color
                                )}>
                                    <module.icon className="h-6 w-6 text-white" />
                                </div>
                                <h3 className="text-lg font-semibold mb-2 group-hover:text-indigo-400 transition-colors uppercase font-bold tracking-tight">
                                    {module.name}
                                </h3>
                                <p className="text-sm text-muted-foreground">
                                    {module.description}
                                </p>
                            </Link>
                        ))}
                    </div>

                    <div className="text-center mt-10">
                        <Link href="/pricing">
                            <Button size="lg" variant="outline" className="gap-2">
                                View All Modules & Pricing
                                <ArrowRight className="h-5 w-5" />
                            </Button>
                        </Link>
                    </div>
                </div>
            </section>

            {/* CTA Section */}
            <section className="py-24 px-4 sm:px-6 lg:px-8 bg-gradient-to-br from-[#020617] via-[#0f172a] to-indigo-950 border-y border-white/5 relative overflow-hidden">
                <div className="absolute inset-0 grid-pattern opacity-10" />
                <div className="mx-auto max-w-4xl text-center relative z-10">
                    <h2 className="text-4xl sm:text-6xl font-black mb-6 text-white leading-tight">
                        Ready to Transform Your <br />
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-cyan-400">ISP Operations?</span>
                    </h2>
                    <p className="text-xl text-slate-400 mb-10 max-w-2xl mx-auto">
                        Join leading South African ISPs using OmniDome to streamline operations and grow revenue.
                    </p>
                    <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
                        <Link href="/dashboard">
                            <Button size="lg" className="bg-indigo-600 hover:bg-indigo-500 text-white text-xl font-black h-16 px-10 shadow-[0_0_30px_rgba(79,70,229,0.4)] transition-all">
                                Start Your Free Trial
                                <ArrowRight className="ml-3 h-6 w-6" />
                            </Button>
                        </Link>
                        <Button size="lg" variant="outline" className="border-slate-800 bg-white/5 text-white hover:bg-white/10 text-xl font-bold h-16 px-10 backdrop-blur-md">
                            Schedule a Demo
                        </Button>
                    </div>
                </div>
            </section>

            {/* Footer */}
            <footer className="border-t border-border py-12 px-4 sm:px-6 lg:px-8">
                <div className="mx-auto max-w-7xl">
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-8 mb-12">
                        <div className="col-span-2">
                            <div className="flex items-center gap-2 mb-4">
                                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-blue-500 shadow-[0_0_15px_rgba(79,70,229,0.3)]">
                                    <Wifi className="h-4 w-4 text-white" />
                                </div>
                                <span className="text-lg font-bold text-white">OmniDome</span>
                            </div>
                            <p className="text-sm text-muted-foreground max-w-xs">
                                The complete ISP operating system for South African service providers.
                            </p>
                        </div>
                        <div>
                            <h4 className="font-semibold mb-4">Product</h4>
                            <ul className="space-y-2 text-sm text-muted-foreground">
                                <li><Link href="/products/sales" className="hover:text-foreground">Sales Hub</Link></li>
                                <li><Link href="/products/crm" className="hover:text-foreground">CRM Hub</Link></li>
                                <li><Link href="/products/network" className="hover:text-foreground">Network Ops</Link></li>
                                <li><Link href="/pricing" className="hover:text-foreground">Pricing</Link></li>
                            </ul>
                        </div>
                        <div>
                            <h4 className="font-semibold mb-4">Resources</h4>
                            <ul className="space-y-2 text-sm text-muted-foreground">
                                <li><Link href="/resources/why-omnidome" className="hover:text-foreground">Why OmniDome</Link></li>
                                <li><Link href="/resources/services" className="hover:text-foreground">Services</Link></li>
                                <li><Link href="/resources/partners" className="hover:text-foreground">Partners</Link></li>
                                <li><a href="#" className="hover:text-foreground">Documentation</a></li>
                            </ul>
                        </div>
                        <div>
                            <h4 className="font-semibold mb-4">Company</h4>
                            <ul className="space-y-2 text-sm text-muted-foreground">
                                <li><a href="#" className="hover:text-foreground">About</a></li>
                                <li><a href="#" className="hover:text-foreground">Careers</a></li>
                                <li><a href="#" className="hover:text-foreground">Contact</a></li>
                                <li><a href="#" className="hover:text-foreground">Legal</a></li>
                            </ul>
                        </div>
                    </div>
                    <div className="border-t border-border pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
                        <p className="text-sm text-muted-foreground">
                            © 2026 OmniDome. All rights reserved.
                        </p>
                        <div className="flex gap-6 text-sm text-muted-foreground">
                            <a href="#" className="hover:text-foreground">Privacy Policy</a>
                            <a href="#" className="hover:text-foreground">Terms of Service</a>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    )
}
