"use client"

import { use, useEffect, useMemo, useState, type ReactNode } from "react"
import Link from "next/link"
import {
    ArrowLeft,
    Check,
    PlayCircle,
    Sparkles,
    Users,
    Wifi,
    LayoutDashboard,
    BarChart3,
    DollarSign,
    Headset,
    Phone,
    Megaphone,
    ShieldCheck,
    UserCog,
    MessageSquare,
    Receipt,
    FileText,
    Package,
    Boxes,
    Globe,
    HeartHandshake,
    Radio,
    ArrowRight,
    type LucideIcon
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { ThemeToggleCompact } from "@/components/ui/theme-toggle"
import { FlickeringGrid } from "@/components/ui/flickering-grid"
import { ShineBorder } from "@/components/ui/shine-border"
import { BentoGrid, BentoCard } from "@/components/ui/bento-grid"
import { AnimatedListDemo } from "@/components/demo/animated-list-demo"
import { AIChatDemo } from "@/components/demo/ai-chat-demo"
import { AIPitchDemo } from "@/components/demo/ai-pitch-demo"
import { GrowthGraphDemo } from "@/components/demo/growth-graph-demo"
import { AnimatedBeamMultipleOutputDemo } from "@/components/demo/animated-beam-demo"
import { OrbitingCirclesDemo2 } from "@/components/demo/orbiting-circles-demo"

type ModuleColor =
    | "emerald"
    | "blue"
    | "green"
    | "purple"
    | "orange"
    | "rose"
    | "cyan"
    | "indigo"
    | "fuchsia"
    | "slate"
    | "amber"
    | "teal"
    | "sky"

type ModuleFeature = {
    title: string
    description: string
    capabilities: string[]
}

type ModuleData = {
    name: string
    icon: LucideIcon
    tagline: string
    description: string
    heroImage: string
    color: ModuleColor
    features: ModuleFeature[]
}

// All modules data
const allModules: Record<string, ModuleData> = {
    "overview": {
        name: "Dashboard Overview",
        icon: LayoutDashboard,
        tagline: "AI-Powered Command Center That Multiplies Results",
        description: "Unified command center with AI-powered insights, real-time metrics, and executive summaries across all your ISP operations.",
        heroImage: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop",
        color: "emerald",
        features: [
            {
                title: "Real-time Executive Dashboard",
                description: "Get a bird's eye view of your entire ISP operations with live KPIs, revenue metrics, and customer health scores.",
                capabilities: ["Live KPI Tracking", "Revenue Analytics", "Customer Health Scores"]
            },
            {
                title: "AI-Powered Insights",
                description: "Let our AI analyze patterns and surface actionable recommendations before problems occur.",
                capabilities: ["Predictive Alerts", "Smart Recommendations", "Trend Analysis"]
            },
            {
                title: "Cross-Module Analytics",
                description: "Unified reporting across all modules with drill-down capabilities and custom report builder.",
                capabilities: ["Custom Reports", "Data Export", "Scheduled Reports"]
            }
        ]
    },
    "communication": {
        name: "Communication Hub",
        icon: MessageSquare,
        tagline: "Unified Team Collaboration That Drives Productivity",
        description: "Team collaboration, internal messaging, and unified communications platform for seamless coordination.",
        heroImage: "https://images.unsplash.com/photo-1553877522-43269d4ea984?q=80&w=2070&auto=format&fit=crop",
        color: "blue",
        features: [
            {
                title: "Team Messaging",
                description: "Real-time chat with channels, direct messages, and thread conversations.",
                capabilities: ["Channels", "Direct Messages", "File Sharing"]
            },
            {
                title: "Unified Inbox",
                description: "All customer and team communications in one place.",
                capabilities: ["Email Integration", "SMS", "Social Media"]
            }
        ]
    },
    "sales": {
        name: "Sales Hub",
        icon: DollarSign,
        tagline: "Accelerate Revenue With AI-Driven Sales Intelligence",
        description: "Complete sales management with deal pipeline, revenue tracking, quote generation, and commission management.",
        heroImage: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?q=80&w=2426&auto=format&fit=crop",
        color: "green",
        features: [
            {
                title: "Visual Pipeline Management",
                description: "Track every deal through your customizable sales stages with our intuitive funnel view.",
                capabilities: ["Funnel Visualization", "Deal Tracking", "Stage Automation"]
            },
            {
                title: "Quote Generation",
                description: "Create professional quotes in seconds with your branding and product catalog.",
                capabilities: ["Quote Templates", "E-Signatures", "Approval Workflows"]
            },
            {
                title: "Revenue Forecasting",
                description: "AI-powered forecasting helps you predict revenue with confidence.",
                capabilities: ["AI Predictions", "Pipeline Analytics", "Goal Tracking"]
            }
        ]
    },
    "crm": {
        name: "CRM Hub",
        icon: Users,
        tagline: "Build Lasting Customer Relationships At Scale",
        description: "Complete customer relationship management with contact tracking, journey analytics, and engagement scoring.",
        heroImage: "https://images.unsplash.com/photo-1552664730-d307ca884978?q=80&w=2070&auto=format&fit=crop",
        color: "purple",
        features: [
            {
                title: "360-degree Customer View",
                description: "See every interaction, ticket, payment, and touchpoint in one unified profile.",
                capabilities: ["Contact Profiles", "Interaction History", "Notes & Tasks"]
            },
            {
                title: "Customer Journey Mapping",
                description: "Visualize and optimize the complete customer lifecycle.",
                capabilities: ["Journey Analytics", "Touchpoint Tracking", "Segmentation"]
            }
        ]
    },
    "support": {
        name: "Service Hub",
        icon: Headset,
        tagline: "Deliver World-Class Support That Customers Love",
        description: "Ticket management, SLA tracking, knowledge base, and customer satisfaction scoring.",
        heroImage: "https://images.unsplash.com/photo-1556745757-8d76bdb6984b?q=80&w=2073&auto=format&fit=crop",
        color: "orange",
        features: [
            {
                title: "Smart Ticketing",
                description: "AI-powered ticket routing and prioritization for faster resolutions.",
                capabilities: ["Auto-Assignment", "SLA Tracking", "Escalation Rules"]
            },
            {
                title: "Knowledge Base",
                description: "Self-service portal with searchable articles and FAQs.",
                capabilities: ["Article Editor", "Search Analytics", "Customer Portal"]
            }
        ]
    },
    "retention": {
        name: "Retention & Churn Hub",
        icon: HeartHandshake,
        tagline: "Stop Customer Churn Before It Happens",
        description: "AI-powered churn prediction with 87% accuracy, risk scoring, retention campaigns, and CLV analysis.",
        heroImage: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop",
        color: "rose",
        features: [
            {
                title: "AI Churn Prediction",
                description: "Machine learning models analyze behavior patterns to identify at-risk customers.",
                capabilities: ["Risk Scoring", "Behavioral Analysis", "Early Warnings"]
            },
            {
                title: "Automated Win-Back",
                description: "Trigger personalized retention campaigns when customers hit risk thresholds.",
                capabilities: ["Campaign Automation", "Personalization", "A/B Testing"]
            },
            {
                title: "CLV Analytics",
                description: "Track and maximize customer lifetime value with predictive analytics.",
                capabilities: ["CLV Scoring", "Segment Analysis", "Revenue Attribution"]
            }
        ]
    },
    "network": {
        name: "Network Ops Hub",
        icon: Wifi,
        tagline: "Monitor & Manage Your Infrastructure In Real-Time",
        description: "Real-time network monitoring, outage alerts, capacity planning, and infrastructure management.",
        heroImage: "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?q=80&w=2034&auto=format&fit=crop",
        color: "cyan",
        features: [
            {
                title: "Live Network Monitoring",
                description: "Real-time visibility into every node, link, and device on your network.",
                capabilities: ["Topology Maps", "Performance Metrics", "Health Checks"]
            },
            {
                title: "Outage Management",
                description: "Instant alerts and automated incident workflows when issues occur.",
                capabilities: ["Alert Rules", "Incident Tracking", "Root Cause Analysis"]
            }
        ]
    },
    "call-center": {
        name: "Call Center Hub",
        icon: Phone,
        tagline: "Empower Agents With Intelligent Call Management",
        description: "Inbound/outbound call management, agent performance, call routing, and quality monitoring.",
        heroImage: "https://images.unsplash.com/photo-1556745757-8d76bdb6984b?q=80&w=2073&auto=format&fit=crop",
        color: "indigo",
        features: [
            {
                title: "Smart Call Routing",
                description: "AI-powered routing to connect customers with the right agent.",
                capabilities: ["Skills-Based Routing", "Queue Management", "IVR Builder"]
            },
            {
                title: "Agent Performance",
                description: "Track metrics and coach agents to excellence.",
                capabilities: ["Call Recording", "Quality Scoring", "Leaderboards"]
            }
        ]
    },
    "marketing": {
        name: "Marketing Hub",
        icon: Megaphone,
        tagline: "Generate More Qualified Leads With AI-Powered Marketing",
        description: "Campaign management, email marketing, A/B testing, and conversion analytics.",
        heroImage: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?q=80&w=2426&auto=format&fit=crop",
        color: "fuchsia",
        features: [
            {
                title: "Multi-Channel Campaigns",
                description: "Create and manage campaigns across email, SMS, social, and more.",
                capabilities: ["Email Builder", "SMS Campaigns", "Social Publishing"]
            },
            {
                title: "Lead Capture",
                description: "Convert visitors into leads with forms, landing pages, and CTAs.",
                capabilities: ["Form Builder", "Landing Pages", "Pop-ups"]
            },
            {
                title: "Marketing Analytics",
                description: "Measure ROI and optimize every campaign with deep analytics.",
                capabilities: ["Attribution", "A/B Testing", "Conversion Tracking"]
            }
        ]
    },
    "compliance": {
        name: "Compliance & Security Hub",
        icon: ShieldCheck,
        tagline: "Stay Compliant With Built-In Regulatory Frameworks",
        description: "RICA verification, POPIA compliance, audit trails, and policy management.",
        heroImage: "https://images.unsplash.com/photo-1563986768609-322da13575f3?q=80&w=2070&auto=format&fit=crop",
        color: "slate",
        features: [
            {
                title: "RICA & POPIA Compliance",
                description: "Built-in workflows for South African regulatory requirements.",
                capabilities: ["RICA Verification", "Consent Management", "Data Requests"]
            },
            {
                title: "Audit Trails",
                description: "Complete audit logging for compliance and security.",
                capabilities: ["Activity Logs", "Access Control", "Reports"]
            }
        ]
    },
    "talent": {
        name: "Staff Dome",
        icon: UserCog,
        tagline: "From Hiring To Retention - Run HR In One Place",
        description: "A compact HR operating system: onboarding, knowledge base, org chart, ATS, payroll via Paystack, leave and scheduling, performance KPIs, surveys, recognition, and attrition insights - with role-based access and asset tracking.",
        heroImage: "https://images.unsplash.com/photo-1521737711867-e3b97375f902?q=80&w=2070&auto=format&fit=crop",
        color: "amber",
        features: [
            {
                title: "Hire, onboard, and organize",
                description: "Move candidates to employees with a clear handoff, a searchable HR knowledge base, and a live org view for every team.",
                capabilities: ["Applicant Tracker", "Employee Onboarding", "HR Knowledge Base", "Company Org Chart", "Pictures"]
            },
            {
                title: "Run people ops and protect access",
                description: "Keep day-to-day operations tight: time off, demand-based scheduling, equipment allocation, and granular permissions.",
                capabilities: ["Leave Management", "Staff Scheduling (Demand-Based)", "Asset Allocation (Laptop, Company Car)", "Access Control", "Systems Role-Based Access"]
            },
            {
                title: "Pay, engage, and retain",
                description: "Automate payroll via Paystack, manage benefits, track performance KPIs, and use surveys + recognition to reduce attrition.",
                capabilities: ["Pay Role (Salaries & Wages via Paystack)", "Employee Benefit Management", "KPI Management", "Surveys", "Kudos (Recognition Programme)", "Birthdays & Milestones", "Attrition Prediction", "Retirement", "Retrenchment"]
            }
        ]
    },
    "billing": {
        name: "Billing & Collection Hub",
        icon: Receipt,
        tagline: "Automate Revenue Collection & Financial Operations",
        description: "Invoice management, payment processing, revenue cycle, and financial reporting.",
        heroImage: "https://images.unsplash.com/photo-1554224155-6726b3ff858f?q=80&w=2011&auto=format&fit=crop",
        color: "teal",
        features: [
            {
                title: "Automated Invoicing",
                description: "Generate and send invoices automatically on schedule.",
                capabilities: ["Invoice Templates", "Recurring Billing", "Pro-Rata"]
            },
            {
                title: "Payment Processing",
                description: "Accept payments via debit order, EFT, and card.",
                capabilities: ["Debit Order", "Card Payments", "Payment Portal"]
            },
            {
                title: "Collections",
                description: "Automated dunning and collections workflows.",
                capabilities: ["Payment Reminders", "Dunning Rules", "Debt Recovery"]
            }
        ]
    },
    "finance": {
        name: "Finance & FP&A Hub",
        icon: FileText,
        tagline: "GAAP-Ready Finance With Scenario Planning",
        description: "Revenue recognition, expense governance, journals, trial balance, bank recon, and GAAP financial statements with budgeting and reforecasting.",
        heroImage: "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?q=80&w=2070&auto=format&fit=crop",
        color: "emerald",
        features: [
            {
                title: "Revenue Recognition",
                description: "Automate GAAP-aligned recognition schedules across subscription, installation, and enterprise contracts.",
                capabilities: ["Deferred Revenue", "Contract Schedules", "Multi-Element Allocation"]
            },
            {
                title: "Expense Governance",
                description: "Receipt OCR, travel approvals, PO workflows, asset tracking, and recurring payments in one control center.",
                capabilities: ["Receipt OCR", "Delegation of Authority", "Purchase Orders"]
            },
            {
                title: "Scenario Planning",
                description: "Model EBITDA and EBIT outcomes for telecoms with budget vs reforecast sliders and live module inputs.",
                capabilities: ["Scenario Sliders", "Budget vs Actual", "EBITA/EBIT Views"]
            }
        ]
    },
    "products": {
        name: "Product Management Hub",
        icon: Package,
        tagline: "Manage Your Product Catalog & Pricing With Ease",
        description: "Product catalog, pricing management, bundling, and inventory tracking.",
        heroImage: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?q=80&w=2426&auto=format&fit=crop",
        color: "indigo",
        features: [
            {
                title: "Product Catalog",
                description: "Centralized catalog for all your packages and add-ons.",
                capabilities: ["Package Builder", "Add-Ons", "Versioning"]
            },
            {
                title: "Dynamic Pricing",
                description: "Flexible pricing rules and promotional campaigns.",
                capabilities: ["Price Rules", "Discounts", "Bundles"]
            }
        ]
    },
    "portal": {
        name: "Portal Management Hub",
        icon: Globe,
        tagline: "White-Label Self-Service Portal For Your Customers",
        description: "Customer self-service portal, API management, and white-label configurations.",
        heroImage: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop",
        color: "sky",
        features: [
            {
                title: "Customer Self-Service",
                description: "Branded portal for customers to manage their accounts.",
                capabilities: ["Account Management", "Usage Dashboard", "Payments"]
            },
            {
                title: "White-Label Branding",
                description: "Fully customizable with your colors, logo, and domain.",
                capabilities: ["Custom Domain", "Branding", "Theme Editor"]
            }
        ]
    },
    "analytics": {
        name: "Analytics Dome",
        icon: BarChart3,
        tagline: "Executive Intelligence That Connects Every Signal",
        description: "AI-powered executive insights, revenue analytics, and cross-module intelligence.",
        heroImage: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop",
        color: "indigo",
        features: [
            {
                title: "Executive Dashboards",
                description: "Unified KPI dashboards with automated rollups across every team.",
                capabilities: ["KPI Rollups", "Live Metrics", "Board Snapshots"]
            },
            {
                title: "Insight Automation",
                description: "AI-driven summaries and alerts that highlight risks and opportunities.",
                capabilities: ["Insight Alerts", "Weekly Summaries", "Trend Detection"]
            },
            {
                title: "Self-Serve Analytics",
                description: "Build reports without engineering help and share them instantly.",
                capabilities: ["Report Builder", "Scheduled Exports", "Team Sharing"]
            }
        ]
    },
    "inventory": {
        name: "Inventory Dome",
        icon: Boxes,
        tagline: "Real-Time Stock Visibility For Field Operations",
        description: "Warehouse tracking, stock management, and auto-replenishment for install teams.",
        heroImage: "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=2070&auto=format&fit=crop",
        color: "amber",
        features: [
            {
                title: "Multi-Warehouse Tracking",
                description: "Track devices, routers, and fiber kits across locations.",
                capabilities: ["Location Tracking", "Bin Management", "Stock Reservations"]
            },
            {
                title: "Auto-Replenishment",
                description: "Trigger purchase orders and transfers before stockouts hit.",
                capabilities: ["Reorder Alerts", "Supplier Routing", "Lead-Time Forecasting"]
            },
            {
                title: "Field Kit Readiness",
                description: "Ensure technicians have the right equipment every day.",
                capabilities: ["Kit Assembly", "Dispatch Readiness", "Usage Audits"]
            }
        ]
    },
    "iot": {
        name: "IoT Dome",
        icon: Radio,
        tagline: "Always-On Telemetry Without More Truck Rolls",
        description: "Device telemetry, signal monitoring, and remote actions across every install.",
        heroImage: "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?q=80&w=2070&auto=format&fit=crop",
        color: "teal",
        features: [
            {
                title: "Live Telemetry",
                description: "Monitor device health and signal quality in real time.",
                capabilities: ["Signal Health", "Latency Trends", "Device Status"]
            },
            {
                title: "Remote Diagnostics",
                description: "Run checks and reset devices without dispatching a team.",
                capabilities: ["Remote Reset", "Diagnostics Logs", "Auto-Triage"]
            },
            {
                title: "Proactive Maintenance",
                description: "Spot issues early and trigger preventive workflows.",
                capabilities: ["Alert Thresholds", "Maintenance Cadence", "Field Handoffs"]
            }
        ]
    }
}

const colorClasses: Record<ModuleColor, string> = {
    emerald: "from-emerald-500 to-teal-500",
    blue: "from-blue-500 to-cyan-500",
    green: "from-green-500 to-emerald-500",
    purple: "from-violet-500 to-purple-500",
    orange: "from-orange-500 to-amber-500",
    rose: "from-rose-500 to-pink-500",
    cyan: "from-cyan-500 to-blue-500",
    indigo: "from-indigo-500 to-violet-500",
    fuchsia: "from-fuchsia-500 to-pink-500",
    slate: "from-slate-500 to-zinc-500",
    amber: "from-amber-500 to-yellow-500",
    teal: "from-teal-500 to-green-500",
    sky: "from-sky-500 to-blue-500"
}

const accentTextClasses: Record<ModuleColor, string> = {
    emerald: "text-emerald-500",
    blue: "text-blue-500",
    green: "text-green-500",
    purple: "text-purple-500",
    orange: "text-orange-500",
    rose: "text-rose-500",
    cyan: "text-cyan-500",
    indigo: "text-indigo-500",
    fuchsia: "text-fuchsia-500",
    slate: "text-slate-500",
    amber: "text-amber-500",
    teal: "text-teal-500",
    sky: "text-sky-500"
}

const shineColors: Record<ModuleColor, string[]> = {
    emerald: ["#10b981", "#22c55e", "#14b8a6"],
    blue: ["#60a5fa", "#38bdf8", "#22d3ee"],
    green: ["#22c55e", "#4ade80", "#a3e635"],
    purple: ["#a78bfa", "#c084fc", "#f472b6"],
    orange: ["#fb923c", "#f59e0b", "#fdba74"],
    rose: ["#fb7185", "#f472b6", "#fda4af"],
    cyan: ["#22d3ee", "#38bdf8", "#60a5fa"],
    indigo: ["#6366f1", "#8b5cf6", "#38bdf8"],
    fuchsia: ["#e879f9", "#f472b6", "#fb7185"],
    slate: ["#64748b", "#94a3b8", "#cbd5f5"],
    amber: ["#f59e0b", "#fbbf24", "#f97316"],
    teal: ["#2dd4bf", "#14b8a6", "#34d399"],
    sky: ["#38bdf8", "#60a5fa", "#818cf8"]
}

const InfographicVisual = ({
    visual,
    accentGradient,
    accentText
}: {
    visual: InfographicVisualKind
    accentGradient: string
    accentText: string
}) => {
    if (visual === "pills") {
        return (
            <div className="flex flex-col items-start gap-3">
                <span className={cn("inline-flex rounded-full px-4 py-2 text-xs font-semibold text-white bg-gradient-to-r", accentGradient)}>
                    Track performance
                </span>
                <span className="inline-flex rounded-full px-4 py-2 text-xs font-semibold bg-slate-100 text-slate-700">
                    Generate insights
                </span>
                <span className="inline-flex rounded-full px-4 py-2 text-xs font-semibold bg-slate-100 text-slate-700">
                    Plan rollout
                </span>
                <span className="inline-flex rounded-full px-4 py-2 text-xs font-semibold bg-slate-100 text-slate-700">
                    Draft updates
                </span>
            </div>
        )
    }

    if (visual === "bars") {
        return (
            <div className="space-y-3">
                {[72, 48, 86, 60].map((value, index) => (
                    <div key={`bar-${index}`} className="h-2 w-full rounded-full bg-slate-200">
                        <div
                            className={cn("h-2 rounded-full bg-gradient-to-r", accentGradient)}
                            style={{ width: `${value}%` }}
                        />
                    </div>
                ))}
            </div>
        )
    }

    if (visual === "timeline") {
        const steps = ["Intake", "Review", "Launch"]
        return (
            <div className="relative pl-6 space-y-4">
                <div className="absolute left-2 top-2 bottom-2 w-px bg-slate-200" />
                {steps.map((step, index) => (
                    <div key={step} className="flex items-center gap-3">
                        <div className={cn("h-3 w-3 rounded-full bg-gradient-to-r", accentGradient)} />
                        <span className="text-xs font-semibold text-slate-700">{step}</span>
                        <span className="text-xs text-slate-400">Step {index + 1}</span>
                    </div>
                ))}
            </div>
        )
    }

    return (
        <div className="relative h-24 w-full">
            <div className="absolute inset-0 rounded-2xl bg-gradient-to-r from-white via-slate-50 to-white" />
            <svg viewBox="0 0 120 40" className="relative h-full w-full">
                <polyline
                    points="0,30 20,24 35,28 55,16 75,22 95,10 120,18"
                    fill="none"
                    stroke="currentColor"
                    className={cn("stroke-[3]", accentText)}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                />
                <circle cx="95" cy="10" r="3" className={cn("fill-current", accentText)} />
            </svg>
        </div>
    )
}

type CaseStudyStat = {
    value: string
    label: string
}

type CaseStudyStep = {
    title: string
    description: string
}

type CaseStudyQuote = {
    body: string
    name: string
    role: string
}

type CaseStudy = {
    label: string
    title: string
    summary: string
    challenge: string
    approach: string
    image: string
    stats: CaseStudyStat[]
    highlights: string[]
    steps: CaseStudyStep[]
    quote: CaseStudyQuote
}

type ShowcaseCard = {
    name: string
    description: string
    href: string
    cta: string
    className: string
    Icon: LucideIcon
    background: ReactNode
}

type SlideTemplate = {
    label: string
    title: string
    description: string
    bullets: string[]
}

type SlideCategory = SlideTemplate & {
    image: string
}

type InfographicVisualKind = "pills" | "bars" | "timeline" | "sparkline"

type InfographicCard = {
    title: string
    description: string
    visual: InfographicVisualKind
}

type SlideImage = {
    src: string
    label: string
}

const productOrder = [
    "overview",
    "communication",
    "sales",
    "crm",
    "support",
    "retention",
    "network",
    "call-center",
    "marketing",
    "compliance",
    "talent",
    "billing",
    "finance",
    "products",
    "portal",
    "analytics",
    "inventory",
    "iot"
]

const southAfricaImages: SlideImage[] = [
    {
        src: "https://images.unsplash.com/photo-1501594907352-04cda38ebc29?q=80&w=1800&auto=format&fit=crop",
        label: "Cape Town fibre corridors"
    },
    {
        src: "https://images.unsplash.com/photo-1489515217757-5fd1be406fef?q=80&w=1800&auto=format&fit=crop",
        label: "Johannesburg metro rollout"
    }
]

const fiberImage: SlideImage = {
    src: "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?q=80&w=1800&auto=format&fit=crop",
    label: "Fibre backbone signal"
}

const productScreenshots: Record<string, SlideImage[]> = {
    communication: [
        { src: "/unified-communication.png", label: "Unified communication view" },
        { src: "/dashboard-preview.png", label: "Live operations dashboard" }
    ],
    sales: [
        { src: "/unified-sales.png", label: "Sales command center" },
        { src: "/dashboard-preview.png", label: "Revenue overview" }
    ],
    retention: [
        { src: "/predict-churn-with-ai.png", label: "Churn prediction panel" },
        { src: "/dashboard-preview.png", label: "Retention insights" }
    ],
    products: [
        { src: "/agentic-ai-product-management.png", label: "Product launch console" },
        { src: "/dashboard-preview.png", label: "Catalog performance" }
    ],
    analytics: [
        { src: "/dashboard-preview.png", label: "Executive KPI board" }
    ],
    overview: [
        { src: "/dashboard-preview.png", label: "OmniDome dashboard" }
    ],
    default: [
        { src: "/dashboard-preview.png", label: "OmniDome overview" }
    ]
}

const productSlideTemplates: SlideTemplate[] = [
    {
        label: "Voice of the customer",
        title: "Align features to real customer needs",
        description: "Connect feedback streams in one place and highlight the highest value opportunities.",
        bullets: [
            "Unify support, surveys, and call insights",
            "Auto-detect themes and priority signals",
            "Close the loop with release updates"
        ]
    },
    {
        label: "Portfolio management",
        title: "Keep catalog, bundles, and pricing aligned",
        description: "Standardize product data so every team ships against the same plan.",
        bullets: [
            "Normalize plans, tiers, and add-ons",
            "Track margins and bundle health",
            "Govern changes with approvals"
        ]
    },
    {
        label: "Execution alignment",
        title: "Coordinate every team around the launch plan",
        description: "Tie tasks, approvals, and documentation into a single workflow.",
        bullets: [
            "Shared launch checklists",
            "Automated handoffs to billing",
            "Executive readiness tracking"
        ]
    },
    {
        label: "Launch management",
        title: "Move from draft to go-live without delays",
        description: "Standardize launches and reuse the best playbooks.",
        bullets: [
            "Reusable launch templates",
            "Regional rollouts and gates",
            "Risk tracking and rollback plans"
        ]
    },
    {
        label: "Go-to-market visibility",
        title: "Track adoption from the first day",
        description: "Measure uptake, channel impact, and pricing performance in one view.",
        bullets: [
            "Live adoption metrics",
            "Pricing performance dashboards",
            "Feedback-driven iteration loops"
        ]
    }
]

const revenueSlideTemplates: SlideTemplate[] = [
    {
        label: "Pipeline visibility",
        title: "Keep every deal stage moving",
        description: "Visualize pipeline health with shared ownership and clean handoffs.",
        bullets: [
            "Standardized stages and exit criteria",
            "Automated approvals and routing",
            "Live funnel health checks"
        ]
    },
    {
        label: "Pricing control",
        title: "Protect margin with governed pricing",
        description: "Bundle, discount, and launch offers with full transparency.",
        bullets: [
            "Rule-based pricing logic",
            "Quote and proposal automation",
            "Audit-ready approvals"
        ]
    },
    {
        label: "Forecasting",
        title: "See revenue shifts before they happen",
        description: "Combine leading indicators and AI insights to stay ahead.",
        bullets: [
            "Scenario planning built in",
            "Pipeline weighted forecasts",
            "Weekly executive rollups"
        ]
    },
    {
        label: "Revenue hygiene",
        title: "Keep collections and revenue data clean",
        description: "Eliminate manual reconciliation with automated checks.",
        bullets: [
            "Automated dunning workflows",
            "Cash collection visibility",
            "Variance alerts in real time"
        ]
    }
]

const customerSlideTemplates: SlideTemplate[] = [
    {
        label: "Unified conversations",
        title: "Every customer interaction in one place",
        description: "Give teams shared context across tickets, chats, and calls.",
        bullets: [
            "Shared inbox with ownership",
            "Context-rich handoffs",
            "Escalation coverage"
        ]
    },
    {
        label: "Lifecycle signals",
        title: "Spot churn risk before it is visible",
        description: "Combine usage, billing, and service signals to detect risk.",
        bullets: [
            "Automated risk scoring",
            "Segment-based playbooks",
            "Retention offer tracking"
        ]
    },
    {
        label: "Resolution workflows",
        title: "Move issues from open to closed faster",
        description: "Standardize resolution steps and keep teams aligned.",
        bullets: [
            "SLA tracking with alerts",
            "Knowledge base with ownership",
            "Post-resolution follow-up"
        ]
    },
    {
        label: "Quality insights",
        title: "Measure service quality in real time",
        description: "Track CSAT, QA, and re-open rates in one view.",
        bullets: [
            "QA scorecards",
            "Root cause analysis",
            "Customer feedback loops"
        ]
    }
]

const operationsSlideTemplates: SlideTemplate[] = [
    {
        label: "Field readiness",
        title: "Keep crews ready with the right inventory",
        description: "Tie inventory, dispatch, and work orders together.",
        bullets: [
            "Kit assembly checklists",
            "Dispatch readiness views",
            "Live stock visibility"
        ]
    },
    {
        label: "Asset tracking",
        title: "Track devices and equipment across the fleet",
        description: "Monitor assets from warehouse to customer site.",
        bullets: [
            "Multi-site inventory",
            "Asset assignment history",
            "Warranty and lifecycle views"
        ]
    },
    {
        label: "Operational cadence",
        title: "Keep response workflows consistent",
        description: "Standardize incident response and maintenance playbooks.",
        bullets: [
            "Incident routing",
            "Preventive maintenance schedules",
            "Performance reporting"
        ]
    },
    {
        label: "Compliance coverage",
        title: "Stay ready for audits with clear evidence",
        description: "Automate compliance capture and policy tracking.",
        bullets: [
            "Policy and evidence libraries",
            "Audit trails on every change",
            "Regulatory reporting"
        ]
    }
]

const analyticsSlideTemplates: SlideTemplate[] = [
    {
        label: "Executive KPIs",
        title: "Align every team to shared outcomes",
        description: "Roll up metrics from every module into one dashboard.",
        bullets: [
            "Cross-module KPI rollups",
            "Executive summaries",
            "Weekly performance cadence"
        ]
    },
    {
        label: "Signal routing",
        title: "Connect the right data to the right team",
        description: "Automate signal flow across revenue, support, and ops.",
        bullets: [
            "Automated alerts",
            "Priority escalation routing",
            "Ownership visibility"
        ]
    },
    {
        label: "Insight automation",
        title: "Turn analytics into actions",
        description: "Use AI to surface insights and recommended next steps.",
        bullets: [
            "Insight summaries",
            "Trend detection",
            "Opportunity scoring"
        ]
    },
    {
        label: "Board reporting",
        title: "Deliver board-ready insights fast",
        description: "Publish clean summaries without manual spreadsheet work.",
        bullets: [
            "Auto-generated reports",
            "Version control for KPIs",
            "Export-ready dashboards"
        ]
    }
]

const talentSlideTemplates: SlideTemplate[] = [
    {
        label: "Hiring pipeline",
        title: "Move candidates to hires without delays",
        description: "Keep hiring stages and approvals in one workflow.",
        bullets: [
            "Applicant tracking",
            "Interview coordination",
            "Offer approvals"
        ]
    },
    {
        label: "Onboarding",
        title: "Standardize onboarding and knowledge capture",
        description: "Deliver consistent onboarding with checklists and playbooks.",
        bullets: [
            "Onboarding checklists",
            "Role-based access setup",
            "Knowledge base ownership"
        ]
    },
    {
        label: "Payroll and benefits",
        title: "Keep payroll and benefits transparent",
        description: "Manage pay, benefits, and approvals from one place.",
        bullets: [
            "Payroll workflows",
            "Benefits tracking",
            "Approval history"
        ]
    },
    {
        label: "Engagement",
        title: "Spot engagement risks before they grow",
        description: "Track performance, surveys, and retention signals.",
        bullets: [
            "Performance reviews",
            "Survey pulse checks",
            "Attrition signals"
        ]
    }
]

const revenueInfographics: InfographicCard[] = [
    {
        title: "One flexible revenue platform",
        description: "Bring pipeline, pricing, and approvals together in one view.",
        visual: "pills"
    },
    {
        title: "Go to market faster",
        description: "Coordinate offers and approvals without the back-and-forth.",
        visual: "bars"
    },
    {
        title: "AI tuned for forecasting",
        description: "Combine signals to predict revenue outcomes earlier.",
        visual: "sparkline"
    }
]

const customerInfographics: InfographicCard[] = [
    {
        title: "Unified care desk",
        description: "Bring chat, calls, and tickets into a shared workflow.",
        visual: "timeline"
    },
    {
        title: "Faster resolution",
        description: "Reduce handoffs with clear SLAs and ownership.",
        visual: "bars"
    },
    {
        title: "Lifecycle signals",
        description: "Track service quality and churn risks in one place.",
        visual: "sparkline"
    }
]

const operationsInfographics: InfographicCard[] = [
    {
        title: "Field readiness view",
        description: "Ensure crews have the right stock and tasks every day.",
        visual: "pills"
    },
    {
        title: "Signal coverage",
        description: "Monitor uptime and response windows across the network.",
        visual: "sparkline"
    },
    {
        title: "Compliance cadence",
        description: "Keep audit trails and policy checks visible.",
        visual: "timeline"
    }
]

const analyticsInfographics: InfographicCard[] = [
    {
        title: "Executive rollups",
        description: "See KPIs across every module in one dashboard.",
        visual: "bars"
    },
    {
        title: "Insight stream",
        description: "Surface anomalies and opportunities in real time.",
        visual: "timeline"
    },
    {
        title: "Cross-module trends",
        description: "Track signals that drive revenue and retention.",
        visual: "sparkline"
    }
]

const productInfographics: InfographicCard[] = [
    {
        title: "Portfolio clarity",
        description: "Keep bundles, pricing, and owners in sync.",
        visual: "pills"
    },
    {
        title: "Launch flow",
        description: "Coordinate release milestones without delays.",
        visual: "timeline"
    },
    {
        title: "Demand signals",
        description: "Watch adoption and feedback in one place.",
        visual: "bars"
    }
]

const talentInfographics: InfographicCard[] = [
    {
        title: "Onboarding runway",
        description: "Standardize checklists, access, and first-week tasks.",
        visual: "timeline"
    },
    {
        title: "People operations view",
        description: "Connect payroll, benefits, and approvals.",
        visual: "bars"
    },
    {
        title: "Engagement pulse",
        description: "Track surveys, KPIs, and retention signals.",
        visual: "sparkline"
    }
]

const buildSlidesFromFeatures = (product: ModuleData, images: SlideImage[]): SlideCategory[] => {
    if (!product.features.length) {
        return [
            {
                label: product.name,
                title: product.tagline,
                description: product.description,
                bullets: ["Unified workflows", "Real-time visibility", "Automated handoffs"],
                image: images[0]?.src || product.heroImage
            }
        ]
    }

    return product.features.map((feature, index) => ({
        label: feature.title,
        title: feature.title,
        description: feature.description,
        bullets: feature.capabilities.slice(0, 3),
        image: images[index % images.length]?.src || product.heroImage
    }))
}

const getSlideImages = (slug: string, product: ModuleData): SlideImage[] => {
    const baseImages = productScreenshots[slug]
    const coreImages = baseImages && baseImages.length
        ? baseImages
        : [{ src: product.heroImage, label: product.name }]
    const extras = fiberSlugs.includes(slug)
        ? [fiberImage, ...southAfricaImages]
        : southAfricaImages
    return [...coreImages, ...extras, { src: product.heroImage, label: product.name }]
}

const getCategorySlides = (slug: string, product: ModuleData): SlideCategory[] => {
    const images = getSlideImages(slug, product)
    let templates = operationsSlideTemplates

    if (slug === "products") templates = productSlideTemplates
    if (slug === "talent") templates = talentSlideTemplates
    if (revenueSlugs.includes(slug)) templates = revenueSlideTemplates
    if (customerSlugs.includes(slug)) templates = customerSlideTemplates
    if (analyticsSlugs.includes(slug)) templates = analyticsSlideTemplates
    if (operationsSlugs.includes(slug)) templates = operationsSlideTemplates

    if (!templates.length) {
        return buildSlidesFromFeatures(product, images)
    }

    return templates.map((template, index) => ({
        ...template,
        image: images[index % images.length]?.src || product.heroImage
    }))
}

const getInfographicCards = (slug: string): InfographicCard[] => {
    if (slug === "products") return productInfographics
    if (slug === "talent") return talentInfographics
    if (revenueSlugs.includes(slug)) return revenueInfographics
    if (customerSlugs.includes(slug)) return customerInfographics
    if (analyticsSlugs.includes(slug)) return analyticsInfographics
    if (operationsSlugs.includes(slug)) return operationsInfographics
    return operationsInfographics
}

const productCaseStudies: Record<string, CaseStudy> = {
    overview: {
        label: "Dashboard",
        title: "Operations aligned under one command view",
        summary: "Leaders moved from scattered reports to a single executive cockpit that ties every module together.",
        challenge: "Data lived in multiple tools, causing reporting delays and inconsistent decisions.",
        approach: "Unified KPI dashboards with automated updates and shared visibility across teams.",
        image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "5x", label: "Faster reporting" },
            { value: "1 view", label: "Executive cockpit" },
            { value: "25%", label: "Lower overhead" },
            { value: "Daily", label: "Real-time sync" }
        ],
        highlights: [
            "Single KPI source for leadership.",
            "Automated module rollups.",
            "Live operational alerts.",
            "Board-ready exports in minutes."
        ],
        steps: [
            { title: "Week 1 - KPI alignment", description: "Standardized metrics across teams." },
            { title: "Week 2 - Data connections", description: "Connected operational data sources." },
            { title: "Week 3 - Executive cadence", description: "Set review rhythms and alerts." }
        ],
        quote: {
            body: "We finally have one source of truth for the whole business.",
            name: "Executive Sponsor",
            role: "Operations"
        }
    },
    communication: {
        label: "Communication",
        title: "Team collaboration consolidated into one workflow",
        summary: "Internal comms, customer updates, and escalations now live in one coordinated system.",
        challenge: "Messages were fragmented across inboxes and chat tools.",
        approach: "Unified channels with routing rules and shared response templates.",
        image: "https://images.unsplash.com/photo-1553877522-43269d4ea984?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "42%", label: "Faster response" },
            { value: "30%", label: "Fewer escalations" },
            { value: "1 inbox", label: "Unified channels" },
            { value: "2x", label: "Visibility" }
        ],
        highlights: [
            "Shared inbox with ownership.",
            "Priority routing for key accounts.",
            "Templates for consistent replies.",
            "Cross-team visibility on updates."
        ],
        steps: [
            { title: "Week 1 - Channel audit", description: "Mapped every inbound channel." },
            { title: "Week 2 - Routing rules", description: "Automated triage and handoffs." },
            { title: "Week 3 - Knowledge capture", description: "Standardized response templates." }
        ],
        quote: {
            body: "Every message reaches the right team instantly.",
            name: "Customer Experience Lead",
            role: "Support"
        }
    },
    sales: {
        label: "Sales",
        title: "Pipeline execution standardized for faster closes",
        summary: "Sales teams aligned deal stages, approvals, and playbooks to remove friction.",
        challenge: "Deal data lived in spreadsheets and follow-ups were inconsistent.",
        approach: "A unified pipeline with automated stages and quote approvals.",
        image: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "35%", label: "Shorter sales cycle" },
            { value: "1.8x", label: "Forecast accuracy" },
            { value: "28%", label: "Higher win rate" },
            { value: "2 days", label: "Faster approvals" }
        ],
        highlights: [
            "Single pipeline source of truth.",
            "Quote generation with approvals.",
            "Sales enablement embedded.",
            "Forecast dashboards in real time."
        ],
        steps: [
            { title: "Week 1 - Stage alignment", description: "Standardized sales stages." },
            { title: "Week 2 - Quote automation", description: "Built pricing and approval flows." },
            { title: "Week 3 - Forecasting", description: "Delivered live pipeline insights." }
        ],
        quote: {
            body: "We close faster because every deal has a clear path.",
            name: "Sales Operations Lead",
            role: "Revenue"
        }
    },
    crm: {
        label: "CRM",
        title: "Customer context unified across teams",
        summary: "Customer data, interactions, and lifecycle signals now live in one hub.",
        challenge: "Teams lacked shared context, leading to duplicated outreach.",
        approach: "A 360 view with segmentation, notes, and shared timelines.",
        image: "https://images.unsplash.com/photo-1552664730-d307ca884978?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "1 view", label: "Customer context" },
            { value: "27%", label: "Faster resolution" },
            { value: "22%", label: "Higher renewal" },
            { value: "3x", label: "Segment speed" }
        ],
        highlights: [
            "Unified profiles and histories.",
            "Segment-based playbooks.",
            "Shared notes and ownership.",
            "Lifecycle dashboards."
        ],
        steps: [
            { title: "Week 1 - Data consolidation", description: "Unified customer data sources." },
            { title: "Week 2 - Segment rules", description: "Built dynamic segmentation." },
            { title: "Week 3 - Playbooks", description: "Rolled out outreach workflows." }
        ],
        quote: {
            body: "Every team sees the same customer story.",
            name: "Customer Success Lead",
            role: "Account management"
        }
    },
    support: {
        label: "Support",
        title: "Support queues shifted from reactive to proactive",
        summary: "Support teams centralized tickets and knowledge to reduce response time and reopens.",
        challenge: "Tickets were scattered and priorities inconsistent.",
        approach: "Unified ticketing with SLA rules and smart routing.",
        image: "https://images.unsplash.com/photo-1556745757-8d76bdb6984b?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "55%", label: "Faster response" },
            { value: "92%", label: "SLA compliance" },
            { value: "30%", label: "Fewer reopens" },
            { value: "3 channels", label: "Unified intake" }
        ],
        highlights: [
            "Smart routing and escalation.",
            "Self-serve knowledge base.",
            "Queue visibility in real time.",
            "Customer feedback loops."
        ],
        steps: [
            { title: "Week 1 - Channel consolidation", description: "Unified intake from email and chat." },
            { title: "Week 2 - SLA automation", description: "Configured SLA timers." },
            { title: "Week 3 - Knowledge base", description: "Published guided self-service content." }
        ],
        quote: {
            body: "We resolve issues faster and customers notice.",
            name: "Support Manager",
            role: "Customer care"
        }
    },
    retention: {
        label: "Retention",
        title: "Churn signals surfaced before customers cancel",
        summary: "Retention teams consolidated risk signals and offers into one system.",
        challenge: "Risk signals were delayed and offers inconsistent.",
        approach: "Automated risk scoring with retention playbooks.",
        image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "18%", label: "Lower churn" },
            { value: "2.4x", label: "Win-back lift" },
            { value: "12 days", label: "Earlier signal" },
            { value: "85%", label: "Coverage" }
        ],
        highlights: [
            "Automated churn scoring.",
            "Retention playbooks by segment.",
            "Save desk workflows with context.",
            "Campaign ROI tracking."
        ],
        steps: [
            { title: "Week 1 - Risk model setup", description: "Connected churn signals." },
            { title: "Week 2 - Playbook automation", description: "Launched offer workflows." },
            { title: "Week 3 - Performance dashboards", description: "Rolled out retention reporting." }
        ],
        quote: {
            body: "We act before cancellations, not after.",
            name: "Retention Lead",
            role: "Customer success"
        }
    },
    network: {
        label: "Network",
        title: "Network operations centralized with live visibility",
        summary: "Network teams moved monitoring, incidents, and capacity planning into one hub.",
        challenge: "Alerts were noisy and response lacked ownership.",
        approach: "Unified dashboards with automated incident workflows.",
        image: "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "38%", label: "Faster resolution" },
            { value: "25%", label: "Fewer outages" },
            { value: "99.95%", label: "Uptime" },
            { value: "1 hub", label: "Command center" }
        ],
        highlights: [
            "Real-time topology visibility.",
            "Automated incident routing.",
            "Capacity planning tied to growth.",
            "Post-incident learning loops."
        ],
        steps: [
            { title: "Week 1 - Telemetry ingest", description: "Connected monitoring sources." },
            { title: "Week 2 - Alert tuning", description: "Reduced noise and set ownership." },
            { title: "Week 3 - Incident playbooks", description: "Standardized response workflows." }
        ],
        quote: {
            body: "We see issues sooner and respond with confidence.",
            name: "Network Operations Lead",
            role: "Infrastructure"
        }
    },
    "call-center": {
        label: "Call Center",
        title: "Agent workflows streamlined for faster resolutions",
        summary: "Call center leaders unified routing and coaching to improve handling time.",
        challenge: "Agents lacked context and QA coverage was inconsistent.",
        approach: "Skills-based routing with performance dashboards.",
        image: "https://images.unsplash.com/photo-1556745757-8d76bdb6984b?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "28%", label: "Lower handle time" },
            { value: "2x", label: "QA coverage" },
            { value: "15%", label: "Higher CSAT" },
            { value: "1 console", label: "Unified workflow" }
        ],
        highlights: [
            "Skills-based routing by intent.",
            "Live coaching prompts for agents.",
            "QA scorecards with trends.",
            "Outcome reporting by queue."
        ],
        steps: [
            { title: "Week 1 - Routing rules", description: "Matched calls to the right agents." },
            { title: "Week 2 - QA templates", description: "Standardized quality scorecards." },
            { title: "Week 3 - Coaching dashboards", description: "Delivered performance insights." }
        ],
        quote: {
            body: "Agents are faster and coaching is data-driven.",
            name: "Call Center Director",
            role: "Operations"
        }
    },
    marketing: {
        label: "Marketing",
        title: "Campaign operations moved from scattered tools to one launch system",
        summary: "Marketing teams replaced spreadsheets with a unified campaign workspace.",
        challenge: "Approvals and assets lived in different tools.",
        approach: "A single workflow for intake, approvals, and reporting.",
        image: "https://images.unsplash.com/photo-1487014679447-9f8336841d58?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "3x", label: "Faster launches" },
            { value: "24%", label: "Higher lead quality" },
            { value: "40%", label: "Fewer approval loops" },
            { value: "1 week", label: "Time to live" }
        ],
        highlights: [
            "Unified campaign intake.",
            "Automated brand checks.",
            "Regional rollouts with templates.",
            "Live performance dashboards."
        ],
        steps: [
            { title: "Week 1 - Intake design", description: "Standardized campaign briefs." },
            { title: "Week 2 - Approval automation", description: "Built review stages." },
            { title: "Week 3 - ROI reporting", description: "Connected performance dashboards." }
        ],
        quote: {
            body: "We launch on time without losing quality.",
            name: "Marketing Operations Lead",
            role: "Growth"
        }
    },
    compliance: {
        label: "Compliance",
        title: "Compliance workflows standardized across teams",
        summary: "Compliance leaders centralized policy, evidence, and approvals.",
        challenge: "Evidence lived in folders and approvals were manual.",
        approach: "A governed compliance hub with audit trails.",
        image: "https://images.unsplash.com/photo-1563986768609-322da13575f3?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "100%", label: "Audit readiness" },
            { value: "50%", label: "Faster approvals" },
            { value: "0", label: "Missed deadlines" },
            { value: "1 library", label: "Policy source" }
        ],
        highlights: [
            "Policy tracking with ownership.",
            "Evidence capture with audit trails.",
            "Automated reminders and tasks.",
            "Compliance dashboards."
        ],
        steps: [
            { title: "Week 1 - Policy mapping", description: "Centralized policies and owners." },
            { title: "Week 2 - Evidence workflows", description: "Automated evidence capture." },
            { title: "Week 3 - Audit reporting", description: "Delivered audit-ready reports." }
        ],
        quote: {
            body: "Audits are now routine, not stressful.",
            name: "Compliance Officer",
            role: "Risk"
        }
    },
    talent: {
        label: "Talent",
        title: "People operations standardized from hire to review",
        summary: "HR teams consolidated onboarding and review cycles into one system.",
        challenge: "Employee data and review timelines were fragmented.",
        approach: "Automated onboarding and review reminders with audit trails.",
        image: "https://images.unsplash.com/photo-1521737711867-e3b97375f902?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "60%", label: "Faster onboarding" },
            { value: "2x", label: "Review completion" },
            { value: "75%", label: "Fewer requests" },
            { value: "10 days", label: "Time to fill" }
        ],
        highlights: [
            "Single source for employee records.",
            "Automated onboarding checklists.",
            "Review cycles with reminders.",
            "Policy acknowledgements."
        ],
        steps: [
            { title: "Week 1 - Data cleanup", description: "Centralized employee records." },
            { title: "Week 2 - Workflow build", description: "Automated onboarding and reviews." },
            { title: "Week 3 - Insights", description: "Rolled out engagement reporting." }
        ],
        quote: {
            body: "We spend less time chasing tasks and more time supporting people.",
            name: "People Operations Manager",
            role: "HR"
        }
    },
    billing: {
        label: "Billing",
        title: "Billing operations moved to automated collections",
        summary: "Billing teams centralized invoicing and dunning to improve cash flow.",
        challenge: "Manual invoicing caused delays and revenue leakage.",
        approach: "Automated billing schedules with collection triggers.",
        image: "https://images.unsplash.com/photo-1554224155-6726b3ff858f?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "35%", label: "Faster collections" },
            { value: "28%", label: "Fewer overdue" },
            { value: "2x", label: "Invoice accuracy" },
            { value: "15%", label: "Lower churn risk" }
        ],
        highlights: [
            "Automated invoicing and reminders.",
            "Payment reconciliation in one place.",
            "Dunning workflows by segment.",
            "Revenue health dashboards."
        ],
        steps: [
            { title: "Week 1 - Invoice rules", description: "Standardized invoice schedules." },
            { title: "Week 2 - Payment workflows", description: "Automated payment tracking." },
            { title: "Week 3 - Dunning automation", description: "Triggered collection workflows." }
        ],
        quote: {
            body: "Cash flow is predictable again.",
            name: "Billing Manager",
            role: "Finance ops"
        }
    },
    finance: {
        label: "Finance",
        title: "Close cycles shortened with automated controls",
        summary: "Finance teams connected billing, expenses, and approvals in one place.",
        challenge: "Reconciliations and approvals were manual.",
        approach: "Automated reconciliations with standardized approvals.",
        image: "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "58%", label: "Faster close" },
            { value: "30%", label: "Fewer recon issues" },
            { value: "2x", label: "Faster approvals" },
            { value: "24 hrs", label: "Time to forecast" }
        ],
        highlights: [
            "Automated reconciliations.",
            "Approval workflows with ownership.",
            "Live dashboards for leadership.",
            "Scenario planning tied to ops."
        ],
        steps: [
            { title: "Week 1 - Data mapping", description: "Connected billing and expenses." },
            { title: "Week 2 - Controls", description: "Implemented approval policies." },
            { title: "Week 3 - Reporting", description: "Delivered real-time forecasting." }
        ],
        quote: {
            body: "We trust the numbers and move faster without the scramble.",
            name: "Finance Lead",
            role: "Corporate finance"
        }
    },
    products: {
        label: "Product",
        title: "Product launches moved from spreadsheets to governed workflows",
        summary: "Product teams centralized catalogs and pricing rules to launch faster.",
        challenge: "Catalog updates were manual and pricing logic inconsistent.",
        approach: "A governed product catalog with approvals and automation.",
        image: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "4x", label: "Faster launches" },
            { value: "38%", label: "Fewer pricing errors" },
            { value: "2.1x", label: "Upsell lift" },
            { value: "14 days", label: "Time to bundle" }
        ],
        highlights: [
            "Single catalog for packages.",
            "Dynamic pricing rules by segment.",
            "Approval workflows with audit trails.",
            "One-click rollout to billing."
        ],
        steps: [
            { title: "Week 1 - Catalog cleanup", description: "Normalized plans and pricing tiers." },
            { title: "Week 2 - Pricing rules", description: "Built promotional logic." },
            { title: "Week 3 - Launch templates", description: "Standardized launch playbooks." }
        ],
        quote: {
            body: "Launches are repeatable and consistent.",
            name: "Product Operations Lead",
            role: "Product team"
        }
    },
    portal: {
        label: "Portal",
        title: "Customer self-serve shifted tickets away from support",
        summary: "Portal adoption grew with branded self-service workflows.",
        challenge: "Customers lacked visibility and opened tickets for routine tasks.",
        approach: "A white-label portal with guided actions and payments.",
        image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "60%", label: "Self-serve deflection" },
            { value: "4x", label: "Portal adoption" },
            { value: "25%", label: "Fewer tickets" },
            { value: "98%", label: "Payment success" }
        ],
        highlights: [
            "Guided self-service journeys.",
            "Usage and billing dashboards.",
            "Brand controls and custom domains.",
            "Support deflection reporting."
        ],
        steps: [
            { title: "Week 1 - Portal design", description: "Defined branded layouts." },
            { title: "Week 2 - Self-serve flows", description: "Implemented payments and changes." },
            { title: "Week 3 - Adoption metrics", description: "Measured deflection and usage." }
        ],
        quote: {
            body: "Customers solve issues without contacting us.",
            name: "Customer Experience Lead",
            role: "Portal team"
        }
    },
    analytics: {
        label: "Analytics",
        title: "Leadership reporting standardized in one analytics layer",
        summary: "Teams consolidated metrics into a single dashboard for faster decisions.",
        challenge: "Executives spent days pulling data from multiple systems.",
        approach: "Unified analytics with automated KPI snapshots.",
        image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "5x", label: "Faster insights" },
            { value: "1 dashboard", label: "Unified view" },
            { value: "20%", label: "Fewer data requests" },
            { value: "Daily", label: "KPI refresh" }
        ],
        highlights: [
            "Cross-module executive dashboards.",
            "Automated KPI snapshots.",
            "AI summaries and alerts.",
            "Self-serve reporting."
        ],
        steps: [
            { title: "Week 1 - KPI definitions", description: "Aligned metrics across teams." },
            { title: "Week 2 - Data pipelines", description: "Connected operational sources." },
            { title: "Week 3 - Insight automation", description: "Rolled out alerts and summaries." }
        ],
        quote: {
            body: "Decisions happen in hours, not weeks.",
            name: "Analytics Lead",
            role: "Business intelligence"
        }
    },
    inventory: {
        label: "Inventory",
        title: "Stock visibility improved across warehouses",
        summary: "Operations teams connected inventory with real-time tracking.",
        challenge: "Stockouts and manual updates slowed installations.",
        approach: "Centralized inventory with auto-replenishment.",
        image: "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "50%", label: "Fewer stockouts" },
            { value: "2x", label: "Faster replenishment" },
            { value: "18%", label: "Lower carry cost" },
            { value: "1 view", label: "Stock visibility" }
        ],
        highlights: [
            "Multi-warehouse tracking.",
            "Auto-PO generation.",
            "Reservation controls.",
            "Shipment ETA visibility."
        ],
        steps: [
            { title: "Week 1 - SKU normalization", description: "Standardized catalog and units." },
            { title: "Week 2 - Replenishment rules", description: "Configured thresholds and alerts." },
            { title: "Week 3 - Shipment tracking", description: "Connected inbound logistics." }
        ],
        quote: {
            body: "We know exactly what is available and where.",
            name: "Supply Chain Lead",
            role: "Operations"
        }
    },
    iot: {
        label: "IoT",
        title: "Device monitoring scaled without more truck rolls",
        summary: "IoT telemetry centralized to detect issues early and trigger remote fixes.",
        challenge: "Device issues were discovered after customer complaints.",
        approach: "Telemetry monitoring with automated alerts and actions.",
        image: "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "33%", label: "Fewer truck rolls" },
            { value: "2x", label: "Faster detection" },
            { value: "15%", label: "Higher uptime" },
            { value: "24/7", label: "Monitoring" }
        ],
        highlights: [
            "Real-time telemetry streams.",
            "Signal health dashboards.",
            "Automated alerts and actions.",
            "Remote diagnostics and resets."
        ],
        steps: [
            { title: "Week 1 - Device onboarding", description: "Connected telemetry sources." },
            { title: "Week 2 - Alert thresholds", description: "Defined proactive triggers." },
            { title: "Week 3 - Automation rules", description: "Enabled remote actions." }
        ],
        quote: {
            body: "We fix issues before customers notice.",
            name: "IoT Operations Lead",
            role: "Field operations"
        }
    }
}

const revenueSlugs = ["sales", "billing", "finance", "marketing"]
const customerSlugs = ["communication", "crm", "support", "retention", "call-center"]
const operationsSlugs = ["network", "inventory", "iot", "compliance", "talent", "products", "portal"]
const analyticsSlugs = ["analytics", "overview"]
const fiberSlugs = ["network", "iot", "inventory", "billing", "finance"]

const getShowcaseCards = (slug: string, productName: string): ShowcaseCard[] => {
    const baseHref = "/auth"
    const revenueCards: ShowcaseCard[] = [
        {
            name: "Revenue Pulse",
            description: "Track pipeline, pricing, and performance in one live view.",
            href: baseHref,
            cta: "View insights",
            className: "col-span-3 lg:col-span-2 lg:row-span-1",
            Icon: DollarSign,
            background: <GrowthGraphDemo className="absolute inset-0" />
        },
        {
            name: "Pitch Studio",
            description: "Generate tailored offers and proposals with AI assistance.",
            href: baseHref,
            cta: "Generate pitch",
            className: "col-span-3 lg:col-span-1 lg:row-span-1",
            Icon: Sparkles,
            background: <AIPitchDemo className="absolute inset-0" />
        },
        {
            name: "Workflow Queue",
            description: "Coordinate approvals, tasks, and handoffs in real time.",
            href: baseHref,
            cta: "See workflow",
            className: "col-span-3 lg:col-span-3 lg:row-span-1",
            Icon: FileText,
            background: <AnimatedListDemo className="absolute inset-0" />
        }
    ]

    const customerCards: ShowcaseCard[] = [
        {
            name: "Unified Conversations",
            description: "Keep every interaction and decision in one shared thread.",
            href: baseHref,
            cta: "Explore inbox",
            className: "col-span-3 lg:col-span-2 lg:row-span-1",
            Icon: MessageSquare,
            background: <AIChatDemo className="absolute inset-0" />
        },
        {
            name: "Escalation Flow",
            description: "Route urgent issues with ownership and SLA visibility.",
            href: baseHref,
            cta: "View routing",
            className: "col-span-3 lg:col-span-1 lg:row-span-1",
            Icon: Headset,
            background: <AnimatedListDemo className="absolute inset-0" />
        },
        {
            name: "Customer Orbit",
            description: "Connect teams around the customer lifecycle in real time.",
            href: baseHref,
            cta: "See connections",
            className: "col-span-3 lg:col-span-3 lg:row-span-1",
            Icon: HeartHandshake,
            background: <OrbitingCirclesDemo2 className="absolute inset-0" />
        }
    ]

    const operationsCards: ShowcaseCard[] = [
        {
            name: "System Flow",
            description: "See how data moves across teams and automation layers.",
            href: baseHref,
            cta: "Trace signals",
            className: "col-span-3 lg:col-span-2 lg:row-span-1",
            Icon: Wifi,
            background: <AnimatedBeamMultipleOutputDemo className="absolute inset-0" />
        },
        {
            name: "Field Ops Queue",
            description: "Align dispatch, tasks, and readiness in one view.",
            href: baseHref,
            cta: "View queue",
            className: "col-span-3 lg:col-span-1 lg:row-span-1",
            Icon: Package,
            background: <AnimatedListDemo className="absolute inset-0" />
        },
        {
            name: "Connected Assets",
            description: "Link assets, teams, and compliance with shared visibility.",
            href: baseHref,
            cta: "See assets",
            className: "col-span-3 lg:col-span-3 lg:row-span-1",
            Icon: ShieldCheck,
            background: <OrbitingCirclesDemo2 className="absolute inset-0" />
        }
    ]

    const analyticsCards: ShowcaseCard[] = [
        {
            name: "Executive Pulse",
            description: "Live metrics and KPI rollups in one dashboard.",
            href: baseHref,
            cta: "View KPIs",
            className: "col-span-3 lg:col-span-2 lg:row-span-1",
            Icon: LayoutDashboard,
            background: <GrowthGraphDemo className="absolute inset-0" />
        },
        {
            name: "Signal Routing",
            description: "Automated context across every module.",
            href: baseHref,
            cta: "See signals",
            className: "col-span-3 lg:col-span-1 lg:row-span-1",
            Icon: Sparkles,
            background: <AnimatedBeamMultipleOutputDemo className="absolute inset-0" />
        },
        {
            name: "Insight Queue",
            description: "Prioritized insights delivered as actions.",
            href: baseHref,
            cta: "Open queue",
            className: "col-span-3 lg:col-span-3 lg:row-span-1",
            Icon: FileText,
            background: <AnimatedListDemo className="absolute inset-0" />
        }
    ]

    let cards = operationsCards
    if (revenueSlugs.includes(slug)) cards = revenueCards
    if (customerSlugs.includes(slug)) cards = customerCards
    if (analyticsSlugs.includes(slug)) cards = analyticsCards

    if (slug === "products") {
        cards = [
            {
                name: `${productName} Launches`,
                description: "Coordinate catalog updates, approvals, and go-live tasks.",
                href: baseHref,
                cta: "View launch",
                className: "col-span-3 lg:col-span-2 lg:row-span-1",
                Icon: Package,
                background: <AnimatedListDemo className="absolute inset-0" />
            },
            {
                name: "Pricing Studio",
                description: "Model bundles and price rules with confidence.",
                href: baseHref,
                cta: "See pricing",
                className: "col-span-3 lg:col-span-1 lg:row-span-1",
                Icon: DollarSign,
                background: <GrowthGraphDemo className="absolute inset-0" />
            },
            {
                name: "Cross-Module Rollout",
                description: "Publish changes across billing and portal in minutes.",
                href: baseHref,
                cta: "Launch now",
                className: "col-span-3 lg:col-span-3 lg:row-span-1",
                Icon: Sparkles,
                background: <AnimatedBeamMultipleOutputDemo className="absolute inset-0" />
            }
        ]
    }

    return cards
}


export default function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
    const { slug } = use(params)
    const product = allModules[slug] || allModules["overview"]
    const IconComponent = product.icon
    const caseStudy = productCaseStudies[slug] || productCaseStudies.overview
    const showcaseCards = getShowcaseCards(slug, product.name)
    const orderIndex = Math.max(0, productOrder.indexOf(slug))
    const flipHero = orderIndex % 2 === 1
    const flipCaseStudy = orderIndex % 2 === 1
    const useBento = orderIndex % 2 === 0
    const categorySlides = useMemo(() => getCategorySlides(slug, product), [slug, product])
    const infographicCards = useMemo(() => getInfographicCards(slug), [slug])
    const [activeCategory, setActiveCategory] = useState(0)
    const activeSlide = categorySlides[activeCategory] || categorySlides[0]
    const heroStats = caseStudy.stats.slice(0, 3)
    const accentText = accentTextClasses[product.color]
    const accentGradient = colorClasses[product.color]

    useEffect(() => {
        setActiveCategory(0)
    }, [slug])

    useEffect(() => {
        if (categorySlides.length <= 1) return
        const timer = setInterval(() => {
            setActiveCategory((prev) => (prev + 1) % categorySlides.length)
        }, 6500)
        return () => clearInterval(timer)
    }, [categorySlides.length])

    return (
        <div className="min-h-screen bg-background text-foreground relative">
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

            {/* Sticky Nav */}
            <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/95 backdrop-blur-xl">
                <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
                    <div className="flex h-auto items-center justify-between py-3">
                        <div className="flex items-center gap-4">
                            <Link href="/" className="flex items-center gap-2 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors">
                                <ArrowLeft className="h-4 w-4" />
                                Back to Home
                            </Link>
                            <Link href="/" className="flex items-center gap-2 group hover:opacity-80 transition-opacity">
                                <img src="/logo-new.svg" alt="OmniDome" className="h-10 w-10 transition-all group-hover:scale-110" />
                            </Link>
                            <span className="text-muted-foreground">/</span>
                            <span className="text-sm font-semibold text-foreground">{product.name}</span>
                        </div>
                        <div className="flex items-center gap-4">
                            <ThemeToggleCompact />
                            <Link href="/auth">
                                <Button variant="outline" size="sm">Sign In</Button>
                            </Link>
                            <Link href="/auth">
                                <Button size="sm" className={cn("bg-gradient-to-r text-white", accentGradient)}>
                                    Get Started Free
                                </Button>
                            </Link>
                        </div>
                    </div>
                </div>
            </nav>

            {/* Hero Section */}
            <section className="pt-32 pb-20 px-4 sm:px-6 lg:px-8 relative overflow-hidden bg-[#F8F5F2]">
                <div
                    className={cn(
                        "absolute inset-0",
                        flipHero
                            ? "bg-[radial-gradient(circle_at_20%_20%,rgba(59,130,246,0.18),transparent_55%),radial-gradient(circle_at_80%_70%,rgba(16,185,129,0.14),transparent_60%)]"
                            : "bg-[radial-gradient(circle_at_20%_20%,rgba(255,122,89,0.18),transparent_55%),radial-gradient(circle_at_80%_70%,rgba(54,197,232,0.14),transparent_60%)]"
                    )}
                />
                <div className="mx-auto max-w-7xl grid lg:grid-cols-2 gap-16 items-center relative">
                    <div className={cn("space-y-6", flipHero ? "lg:order-2" : "lg:order-1")}>
                        <div className="inline-flex items-center gap-2 rounded-full border border-black/5 bg-white/80 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-[0.3em] text-slate-600 shadow-sm">
                            Product
                            <span className="text-slate-900">{product.name}</span>
                        </div>

                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tight text-slate-950">
                            {product.tagline.split(" ").slice(0, -2).join(" ")}{" "}
                            <span className={cn("bg-gradient-to-r bg-clip-text text-transparent", accentGradient)}>
                                {product.tagline.split(" ").slice(-2).join(" ")}
                            </span>
                        </h1>

                        <p className="text-lg text-slate-600 max-w-xl">
                            {product.description}
                        </p>

                        <div className="flex flex-col sm:flex-row gap-4">
                            <Link href="/auth">
                                <Button size="lg" className={cn("bg-gradient-to-r text-white shadow-lg shadow-black/10", accentGradient)}>
                                    Get a demo
                                </Button>
                            </Link>
                            <Link href="/auth">
                                <Button size="lg" variant="outline" className="border-black/10 text-slate-700">
                                    Get started free
                                </Button>
                            </Link>
                        </div>

                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pt-2">
                            {heroStats.map((stat) => (
                                <div key={stat.label} className="rounded-2xl border border-black/5 bg-white/80 px-4 py-3 shadow-sm">
                                    <p className="text-2xl font-semibold text-slate-900">{stat.value}</p>
                                    <p className="text-[11px] uppercase tracking-[0.25em] text-slate-500 mt-1">
                                        {stat.label}
                                    </p>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className={cn("relative group", flipHero ? "lg:order-1" : "lg:order-2")}>
                        <ShineBorder
                            borderRadius={28}
                            borderWidth={1.5}
                            color={shineColors[product.color]}
                            className="rounded-[28px]"
                        >
                            <div className="rounded-[26px] overflow-hidden border border-black/10 bg-white shadow-2xl">
                                <img
                                    src={product.heroImage}
                                    alt={product.name}
                                    className="w-full aspect-video object-cover transition-transform duration-500 group-hover:scale-[1.02]"
                                />
                            </div>
                        </ShineBorder>
                        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                            <div className="w-20 h-20 bg-white/80 backdrop-blur-md rounded-full flex items-center justify-center shadow-lg">
                                <PlayCircle className={cn("h-10 w-10", accentText)} />
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Category Slider */}
            <section className={cn("py-20 px-4 sm:px-6 lg:px-8", flipHero ? "bg-white" : "bg-[#F8F5F2]")}>
                <div className="mx-auto max-w-7xl">
                    <div className="text-center mb-12">
                        <div className="inline-flex items-center gap-2 rounded-full border border-black/5 bg-white/80 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600">
                            Product Focus Areas
                        </div>
                        <h2 className="text-3xl sm:text-4xl font-semibold mt-5 mb-4 text-slate-950">
                            Categories aligned to {product.name}
                        </h2>
                        <p className="text-lg text-slate-600 max-w-3xl mx-auto">
                            Switch between the core workflows to see how the module supports each stage.
                        </p>
                    </div>

                    <div className="rounded-3xl border border-black/5 bg-white/90 backdrop-blur-sm p-6 sm:p-8 shadow-[0_24px_60px_rgba(15,23,42,0.12)]">
                        <div className="flex flex-wrap gap-2 border-b border-black/10 pb-2">
                            {categorySlides.map((category, idx) => (
                                <button
                                    key={category.label}
                                    type="button"
                                    onClick={() => setActiveCategory(idx)}
                                    className={cn(
                                        "px-4 py-3 text-sm font-semibold transition-colors border-b-2",
                                        idx === activeCategory
                                            ? "border-slate-900 text-slate-900"
                                            : "border-transparent text-slate-500 hover:text-slate-800"
                                    )}
                                >
                                    {category.label}
                                </button>
                            ))}
                        </div>

                        <div className="grid lg:grid-cols-[0.9fr_1.1fr] gap-10 items-center pt-8">
                            <div key={activeSlide?.title} className="space-y-6 animate-in fade-in slide-in-from-left-4 duration-500">
                                <div className="inline-flex items-center gap-2 rounded-full border border-black/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                                    Active Category
                                </div>
                                <h3 className="text-3xl font-semibold text-slate-950">
                                    {activeSlide?.title}
                                </h3>
                                <p className="text-lg text-slate-600">
                                    {activeSlide?.description}
                                </p>
                                <div className="space-y-3">
                                    {activeSlide?.bullets.map((bullet) => (
                                        <div key={bullet} className="flex items-start gap-3">
                                            <Check className={cn("h-5 w-5 mt-0.5", accentText)} />
                                            <p className="text-sm text-slate-900">{bullet}</p>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div key={activeSlide?.image} className="animate-in fade-in slide-in-from-right-4 duration-500">
                                <ShineBorder
                                    borderRadius={22}
                                    borderWidth={1}
                                    color={shineColors[product.color]}
                                    className="rounded-[22px]"
                                >
                                    <div className="rounded-[20px] overflow-hidden border border-black/10 bg-white shadow-lg">
                                        <img
                                            src={activeSlide?.image}
                                            alt={activeSlide?.label}
                                            className="w-full aspect-video object-cover"
                                        />
                                    </div>
                                </ShineBorder>
                            </div>
                        </div>

                        <div className="mt-6 flex items-center gap-2">
                            {categorySlides.map((_, idx) => (
                                <div
                                    key={`dot-${idx}`}
                                    className={cn(
                                        "h-1.5 rounded-full transition-all",
                                        idx === activeCategory ? "w-10 bg-slate-900" : "w-4 bg-slate-200"
                                    )}
                                />
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {/* Module Showcase / Infographics */}
            {useBento ? (
                <section className={cn("py-20 px-4 sm:px-6 lg:px-8", flipHero ? "bg-white" : "bg-[#F8F5F2]")}>
                    <div className="mx-auto max-w-7xl">
                        <div className="text-center mb-12">
                            <div className="inline-flex items-center gap-2 rounded-full border border-black/5 bg-white/80 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600">
                                Live Workspace
                            </div>
                            <h2 className="text-3xl sm:text-4xl font-semibold mt-5 mb-4 text-slate-950">
                                How {product.name} shows up in the real world
                            </h2>
                            <p className="text-lg text-slate-600 max-w-2xl mx-auto">
                                Built with the same component system you see on the OmniDome landing page, tuned to this module.
                            </p>
                        </div>
                        <BentoGrid className="grid-cols-1 lg:grid-cols-3 auto-rows-[20rem]">
                            {showcaseCards.map((card) => (
                                <BentoCard
                                    key={card.name}
                                    name={card.name}
                                    className={card.className}
                                    background={card.background}
                                    Icon={card.Icon}
                                    description={card.description}
                                    href={card.href}
                                    cta={card.cta}
                                />
                            ))}
                        </BentoGrid>
                    </div>
                </section>
            ) : (
                <section className={cn("py-20 px-4 sm:px-6 lg:px-8", flipHero ? "bg-[#F8F5F2]" : "bg-white")}>
                    <div className="mx-auto max-w-7xl">
                        <div className="text-center mb-12">
                            <div className="inline-flex items-center gap-2 rounded-full border border-black/5 bg-white/80 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600">
                                Snapshot Views
                            </div>
                            <h2 className="text-3xl sm:text-4xl font-semibold mt-5 mb-4 text-slate-950">
                                Still infographics that highlight what matters
                            </h2>
                            <p className="text-lg text-slate-600 max-w-2xl mx-auto">
                                Alternate layouts so each product page feels distinct while staying on brand.
                            </p>
                        </div>

                        <div className="grid md:grid-cols-3 gap-6">
                            {infographicCards.map((card) => (
                                <div key={card.title} className="rounded-3xl border border-black/5 bg-white p-6 shadow-sm">
                                    <div className={cn("text-xs font-semibold uppercase tracking-[0.2em] mb-3", accentText)}>
                                        Insight
                                    </div>
                                    <h3 className="text-xl font-semibold text-slate-950 mb-3">{card.title}</h3>
                                    <p className="text-sm text-slate-600 mb-6">{card.description}</p>
                                    <InfographicVisual
                                        visual={card.visual}
                                        accentGradient={accentGradient}
                                        accentText={accentText}
                                    />
                                </div>
                            ))}
                        </div>
                    </div>
                </section>
            )}

            {/* Features Section */}
            <section className={cn("py-20 px-4 sm:px-6 lg:px-8", flipHero ? "bg-white" : "bg-[#F8F5F2]")}>
                <div className="mx-auto max-w-7xl">
                    <div className="text-center mb-16">
                        <h2 className="text-3xl sm:text-4xl font-semibold mb-4 text-slate-950">
                            Everything you need in {product.name}
                        </h2>
                        <p className="text-lg text-slate-600 max-w-2xl mx-auto">
                            Powerful features designed specifically for ISP operations.
                        </p>
                    </div>

                    <div className="space-y-24">
                        {product.features.map((feature, idx) => (
                            <div key={idx} className="grid lg:grid-cols-2 gap-16 items-center">
                                <div className={cn(idx % 2 === 1 ? "lg:order-last" : "")}>
                                    <div className="rounded-3xl bg-white border border-black/5 p-8 aspect-video flex items-center justify-center shadow-sm">
                                        <div className={`w-24 h-24 rounded-2xl bg-gradient-to-br ${colorClasses[product.color]} flex items-center justify-center`}>
                                            <IconComponent className="h-12 w-12 text-white" />
                                        </div>
                                    </div>
                                </div>
                                <div>
                                    <div className={cn("text-xs font-semibold uppercase tracking-[0.2em] mb-4", accentText)}>
                                        Feature {idx + 1}
                                    </div>
                                    <h3 className="text-3xl font-semibold mb-4 text-slate-950">{feature.title}</h3>
                                    <p className="text-lg text-slate-600 mb-8">
                                        {feature.description}
                                    </p>
                                    <div className="space-y-3">
                                        {feature.capabilities.map((cap: string) => (
                                            <div key={cap} className="flex items-center gap-3">
                                                <Check className={cn("h-5 w-5", accentText)} />
                                                <span className="font-medium text-slate-900">{cap}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Case Study */}
            <section className="py-24 px-4 sm:px-6 lg:px-8 relative overflow-hidden bg-[#F8F5F2]">
                <div
                    className={cn(
                        "absolute inset-0",
                        flipCaseStudy
                            ? "bg-[radial-gradient(circle_at_25%_20%,rgba(59,130,246,0.18),transparent_55%),radial-gradient(circle_at_75%_75%,rgba(16,185,129,0.14),transparent_60%)]"
                            : "bg-[radial-gradient(circle_at_20%_20%,rgba(255,122,89,0.18),transparent_55%),radial-gradient(circle_at_80%_70%,rgba(54,197,232,0.14),transparent_60%)]"
                    )}
                />
                <div className="mx-auto max-w-7xl relative">
                    <div className="text-center mb-14">
                        <div className="inline-flex items-center gap-2 rounded-full border border-black/5 bg-white/80 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-[0.3em] text-slate-600 shadow-sm">
                            Case Study
                            <span className="text-slate-900">{caseStudy.label}</span>
                        </div>
                        <h2 className="text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-tight mt-6 mb-4 text-slate-950">
                            {caseStudy.title}
                        </h2>
                        <p className="text-lg text-slate-600 max-w-3xl mx-auto leading-relaxed">
                            {caseStudy.summary}
                        </p>
                    </div>

                    <div className="grid lg:grid-cols-[1.1fr_0.9fr] gap-10 items-start">
                        <div className={cn("rounded-3xl border border-black/5 bg-white/90 backdrop-blur-sm p-8 shadow-[0_20px_60px_rgba(15,23,42,0.12)]", flipCaseStudy ? "lg:order-2" : "lg:order-1")}>
                            <ShineBorder
                                borderRadius={24}
                                borderWidth={1}
                                color={shineColors[product.color]}
                                className="rounded-[24px]"
                            >
                                <div className="rounded-[22px] overflow-hidden border border-black/10 bg-white shadow-lg">
                                    <img
                                        src={caseStudy.image}
                                        alt={caseStudy.label}
                                        className="w-full aspect-video object-cover"
                                    />
                                </div>
                            </ShineBorder>

                            <div className="mt-8 grid md:grid-cols-2 gap-6">
                                <div className="rounded-2xl border border-black/5 bg-white p-6">
                                    <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500 mb-3">Challenge</p>
                                    <p className="text-sm text-slate-900 leading-relaxed">
                                        {caseStudy.challenge}
                                    </p>
                                </div>
                                <div className="rounded-2xl border border-black/5 bg-white p-6">
                                    <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500 mb-3">Approach</p>
                                    <p className="text-sm text-slate-900 leading-relaxed">
                                        {caseStudy.approach}
                                    </p>
                                </div>
                            </div>

                            <div className="mt-8">
                                <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500 mb-4">Execution Path</p>
                                <div className="space-y-4">
                                    {caseStudy.steps.map((step, index) => (
                                        <div key={step.title} className="flex gap-4 items-start">
                                            <div className={cn("h-10 w-10 rounded-xl bg-gradient-to-br text-white flex items-center justify-center text-sm font-bold shadow-sm", accentGradient)}>
                                                {index + 1}
                                            </div>
                                            <div>
                                                <p className="font-semibold text-slate-900">{step.title}</p>
                                                <p className="text-sm text-slate-600 leading-relaxed">{step.description}</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>

                        <div className={cn("space-y-6", flipCaseStudy ? "lg:order-1" : "lg:order-2")}>
                            <div className="grid sm:grid-cols-2 gap-4">
                                {caseStudy.stats.map((stat) => (
                                    <div key={stat.label} className="rounded-2xl border border-black/5 bg-white p-6 shadow-[0_10px_30px_rgba(15,23,42,0.08)]">
                                        <div className="text-3xl font-semibold text-slate-900">
                                            {stat.value}
                                        </div>
                                        <div className="text-sm text-slate-500">{stat.label}</div>
                                    </div>
                                ))}
                            </div>

                            <div className="rounded-2xl border border-black/5 bg-white p-6">
                                <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500 mb-4">Outcomes</p>
                                <div className="space-y-3">
                                    {caseStudy.highlights.map((item) => (
                                        <div key={item} className="flex items-start gap-3">
                                            <Check className={cn("h-5 w-5 mt-0.5", accentText)} />
                                            <p className="text-sm text-slate-900">{item}</p>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div className="rounded-2xl border border-black/5 bg-white p-6">
                                <p className="text-lg font-semibold mb-4 text-slate-900">"{caseStudy.quote.body}"</p>
                                <div className="text-sm text-slate-500">
                                    <span className="font-semibold text-slate-900">{caseStudy.quote.name}</span> - {caseStudy.quote.role}
                                </div>
                            </div>

                            <div className="rounded-2xl border border-black/5 bg-white p-6">
                                <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500 mb-3">Ready to run this playbook?</p>
                                <p className="text-sm text-slate-600 mb-5 leading-relaxed">
                                    Bring the same workflow into {product.name} with governed execution, fast handoffs, and full visibility.
                                </p>
                                <div className="flex flex-col sm:flex-row gap-3">
                                    <Link href="/auth">
                                        <Button className={cn("bg-gradient-to-r text-white", accentGradient)}>
                                            Get a demo
                                        </Button>
                                    </Link>
                                    <Link href="/auth">
                                        <Button variant="outline">
                                            Talk to the team
                                        </Button>
                                    </Link>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>
            {/* CTA */}
            <section className="py-24 px-4 sm:px-6 lg:px-8 bg-white">
                <div className="mx-auto max-w-4xl text-center">
                    <h2 className="text-3xl sm:text-4xl font-semibold mb-6 text-slate-950">
                        Ready to get started with {product.name}?
                    </h2>
                    <p className="text-lg text-slate-600 mb-10">
                        Start your 14-day free trial today. No credit card required.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Link href="/auth">
                            <Button size="lg" className={cn("bg-gradient-to-r text-white text-lg px-10", accentGradient)}>
                                Start Free Trial
                                <ArrowRight className="ml-2 h-5 w-5" />
                            </Button>
                        </Link>
                        <Button size="lg" variant="outline" className="text-lg px-10 border-black/10 text-slate-700">
                            Schedule a Demo
                        </Button>
                    </div>
                </div>
            </section>

            {/* Footer */}
            <footer className="border-t border-border py-12 px-4 sm:px-6 lg:px-8">
                <div className="mx-auto max-w-7xl flex flex-col md:flex-row items-center justify-between gap-8">
                    <div className="flex items-center gap-2">
                        <img src="/logo-new.svg" alt="OmniDome" className="h-10 w-10" />
                        <span className="text-sm font-semibold">OmniDome</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                        (c) 2026 OmniDome. All rights reserved.
                    </p>
                </div>
            </footer>
        </div>
    )
}

