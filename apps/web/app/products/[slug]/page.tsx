"use client"

import { use } from "react"
import Link from "next/link"
import {
    ArrowLeft,
    Check,
    PlayCircle,
    Sparkles,
    Zap,
    BarChart3,
    Target,
    Users,
    Wifi,
    LayoutDashboard,
    DollarSign,
    Headset,
    Phone,
    Megaphone,
    ShieldCheck,
    UserCog,
    MessageSquare,
    Receipt,
    Package,
    Globe,
    HeartHandshake,
    ArrowRight
} from "lucide-react"
import { Button } from "@/components/ui/button"

// All modules data
const allModules: Record<string, any> = {
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
                title: "360° Customer View",
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
        name: "Talent Management Hub",
        icon: UserCog,
        tagline: "Build & Retain A High-Performance Team",
        description: "HR management, recruitment, performance reviews, and employee engagement.",
        heroImage: "https://images.unsplash.com/photo-1521737711867-e3b97375f902?q=80&w=2070&auto=format&fit=crop",
        color: "amber",
        features: [
            {
                title: "Employee Management",
                description: "Centralized HR system for your entire workforce.",
                capabilities: ["Employee Profiles", "Leave Management", "Onboarding"]
            },
            {
                title: "Performance Reviews",
                description: "Goal setting and performance tracking for growth.",
                capabilities: ["Goal Tracking", "360 Reviews", "Development Plans"]
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
    }
}

const colorClasses: Record<string, string> = {
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

export default function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
    const { slug } = use(params)
    const product = allModules[slug] || allModules["overview"]
    const IconComponent = product.icon

    return (
        <div className="min-h-screen bg-background text-foreground">
            {/* Sticky Nav */}
            <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/95 backdrop-blur-xl">
                <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
                    <div className="flex h-16 items-center justify-between">
                        <div className="flex items-center gap-4">
                            <Link href="/" className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-emerald-500 transition-colors">
                                <ArrowLeft className="h-4 w-4" /> Back
                            </Link>
                            <span className="text-muted-foreground">/</span>
                            <span className="text-sm font-semibold text-foreground">{product.name}</span>
                        </div>
                        <div className="flex items-center gap-4">
                            <Link href="/dashboard">
                                <Button variant="outline" size="sm">Sign In</Button>
                            </Link>
                            <Link href="/dashboard">
                                <Button size="sm" className="bg-gradient-to-r from-emerald-500 to-teal-500 text-white">
                                    Get Started Free
                                </Button>
                            </Link>
                        </div>
                    </div>
                </div>
            </nav>

            {/* Hero Section */}
            <section className="pt-32 pb-20 px-4 sm:px-6 lg:px-8">
                <div className="mx-auto max-w-7xl grid lg:grid-cols-2 gap-16 items-center">
                    <div>
                        <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-1.5 text-xs font-medium mb-6">
                            <Sparkles className="h-3.5 w-3.5 text-emerald-500" />
                            <span>Product</span>
                        </div>

                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight mb-6">
                            {product.tagline.split(' ').slice(0, -2).join(' ')}{' '}
                            <span className={`bg-gradient-to-r ${colorClasses[product.color]} bg-clip-text text-transparent`}>
                                {product.tagline.split(' ').slice(-2).join(' ')}
                            </span>
                        </h1>

                        <p className="text-lg text-muted-foreground mb-10 max-w-xl">
                            {product.description}
                        </p>

                        <div className="flex flex-col sm:flex-row gap-4">
                            <Link href="/dashboard">
                                <Button size="lg" className={`bg-gradient-to-r ${colorClasses[product.color]} text-white text-lg px-8`}>
                                    Get a demo
                                </Button>
                            </Link>
                            <Link href="/dashboard">
                                <Button size="lg" variant="outline" className="text-lg px-8">
                                    Get started free
                                </Button>
                            </Link>
                        </div>
                    </div>

                    <div className="relative">
                        <div className="rounded-2xl overflow-hidden border border-border bg-card p-2 shadow-2xl">
                            <img
                                src={product.heroImage}
                                alt={product.name}
                                className="rounded-xl w-full aspect-video object-cover"
                            />
                            <div className="absolute inset-0 flex items-center justify-center bg-black/20 opacity-0 hover:opacity-100 transition-opacity rounded-2xl">
                                <div className="p-4 bg-white/10 backdrop-blur-md rounded-full">
                                    <PlayCircle className="h-16 w-16 text-white" />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Features Section */}
            <section className="py-20 px-4 sm:px-6 lg:px-8 bg-card/50">
                <div className="mx-auto max-w-7xl">
                    <div className="text-center mb-16">
                        <h2 className="text-3xl sm:text-4xl font-bold mb-4">
                            Everything you need in {product.name}
                        </h2>
                        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                            Powerful features designed specifically for ISP operations.
                        </p>
                    </div>

                    <div className="space-y-24">
                        {product.features.map((feature: any, idx: number) => (
                            <div key={idx} className={`grid lg:grid-cols-2 gap-16 items-center ${idx % 2 === 1 ? 'lg:flex-row-reverse' : ''}`}>
                                <div className={idx % 2 === 1 ? 'lg:order-last' : ''}>
                                    <div className="rounded-2xl bg-gradient-to-br from-card to-background border border-border p-8 aspect-video flex items-center justify-center">
                                        <div className={`w-24 h-24 rounded-2xl bg-gradient-to-br ${colorClasses[product.color]} flex items-center justify-center`}>
                                            <IconComponent className="h-12 w-12 text-white" />
                                        </div>
                                    </div>
                                </div>
                                <div>
                                    <div className="text-xs font-medium text-emerald-500 uppercase tracking-wider mb-4">
                                        Feature {idx + 1}
                                    </div>
                                    <h3 className="text-3xl font-bold mb-4">{feature.title}</h3>
                                    <p className="text-lg text-muted-foreground mb-8">
                                        {feature.description}
                                    </p>
                                    <div className="space-y-3">
                                        {feature.capabilities.map((cap: string) => (
                                            <div key={cap} className="flex items-center gap-3">
                                                <Check className="h-5 w-5 text-emerald-500" />
                                                <span className="font-medium">{cap}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section className="py-24 px-4 sm:px-6 lg:px-8">
                <div className="mx-auto max-w-4xl text-center">
                    <h2 className="text-3xl sm:text-4xl font-bold mb-6">
                        Ready to get started with {product.name}?
                    </h2>
                    <p className="text-lg text-muted-foreground mb-10">
                        Start your 14-day free trial today. No credit card required.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Link href="/dashboard">
                            <Button size="lg" className={`bg-gradient-to-r ${colorClasses[product.color]} text-white text-lg px-10`}>
                                Start Free Trial
                                <ArrowRight className="ml-2 h-5 w-5" />
                            </Button>
                        </Link>
                        <Button size="lg" variant="outline" className="text-lg px-10">
                            Schedule a Demo
                        </Button>
                    </div>
                </div>
            </section>

            {/* Footer */}
            <footer className="border-t border-border py-12 px-4 sm:px-6 lg:px-8">
                <div className="mx-auto max-w-7xl flex flex-col md:flex-row items-center justify-between gap-8">
                    <div className="flex items-center gap-2">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-500">
                            <Wifi className="h-4 w-4 text-white" />
                        </div>
                        <span className="text-lg font-bold">OmniDome</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                        © 2026 OmniDome. All rights reserved.
                    </p>
                </div>
            </footer>
        </div>
    )
}
