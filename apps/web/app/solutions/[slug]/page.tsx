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
    ShieldCheck,
    Wifi,
    MessageSquare,
    DollarSign,
    HeartHandshake,
    Phone,
    Megaphone,
    Receipt,
    Package,
    Globe,
    UserCog,
    Headset,
    ArrowRight
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

// Comprehensive module details with correct content for each
const moduleDetails: Record<string, any> = {
    "communication": {
        name: "Communication Hub",
        icon: MessageSquare,
        color: "from-blue-500 to-cyan-500",
        title: "Unify Your Team Communications",
        description: "Bring all team messaging, collaboration, and internal communications into one powerful platform.",
        heroImage: "https://images.unsplash.com/photo-1553877522-43269d4ea984?q=80&w=2070&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Centralize team messaging across departments.",
                description: "No more scattered conversations across multiple tools. Communication Hub brings all your team chats, channels, and direct messages into one place.",
                features: ["Team Channels", "Direct Messaging", "File Sharing"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Integrate with your existing communication tools.",
                description: "Connect email, SMS, and social media to create a unified inbox that your team can manage from anywhere.",
                features: ["Email Integration", "SMS Gateway", "Social Inbox"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "sales": {
        name: "Sales Hub",
        icon: DollarSign,
        color: "from-green-500 to-emerald-500",
        title: "Accelerate Your Deal Flow With Sales Hub",
        description: "Manage your entire pipeline from prospecting to close with automated workflows and real-time forecasting.",
        heroImage: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?q=80&w=2426&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Visualize your pipeline with advanced funnel views.",
                description: "Track every deal and identify bottlenecks in real-time. Our funnel visualization shows exactly where you're losing momentum.",
                features: ["Funnel Visualization", "Real-time Deal Tracking", "Stage Automation"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Generate professional quotes in seconds.",
                description: "Create customized quotes with your branding, product catalog, and pricing rules. Get e-signatures and close deals faster.",
                features: ["Quote Templates", "E-Signatures", "Approval Workflows"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Forecast revenue with AI-powered predictions.",
                description: "Our machine learning models analyze your pipeline data to provide accurate revenue forecasts and identify at-risk deals.",
                features: ["AI Predictions", "Pipeline Analytics", "Goal Tracking"],
                image: "https://images.unsplash.com/photo-1553877522-43269d4ea984?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "crm": {
        name: "CRM Hub",
        icon: Users,
        color: "from-violet-500 to-purple-500",
        title: "Build Lasting Customer Relationships At Scale",
        description: "Complete customer relationship management with contact tracking, journey analytics, and engagement scoring.",
        heroImage: "https://images.unsplash.com/photo-1552664730-d307ca884978?q=80&w=2070&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Get a complete 360° view of every customer.",
                description: "See every interaction, ticket, payment, and touchpoint in one unified profile. Never miss context again.",
                features: ["Contact Profiles", "Interaction History", "Notes & Tasks"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Map and optimize the complete customer journey.",
                description: "Visualize how customers move through your business. Identify friction points and optimize for retention.",
                features: ["Journey Analytics", "Touchpoint Tracking", "Segmentation"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "support": {
        name: "Service Hub",
        icon: Headset,
        color: "from-orange-500 to-amber-500",
        title: "Deliver World-Class Support That Customers Love",
        description: "Ticket management, SLA tracking, knowledge base, and customer satisfaction scoring in one platform.",
        heroImage: "https://images.unsplash.com/photo-1556745757-8d76bdb6984b?q=80&w=2073&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Route tickets intelligently with AI-powered automation.",
                description: "Our smart routing ensures tickets reach the right agent instantly. Set SLAs, escalation rules, and priority levels.",
                features: ["Auto-Assignment", "SLA Tracking", "Escalation Rules"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Empower customers with self-service.",
                description: "Build a searchable knowledge base that helps customers find answers without creating tickets.",
                features: ["Article Editor", "Search Analytics", "Customer Portal"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "retention": {
        name: "Retention Hub",
        icon: HeartHandshake,
        color: "from-rose-500 to-pink-500",
        title: "Stop Customer Churn Before It Happens",
        description: "AI-powered churn prediction with 87% accuracy, risk scoring, retention campaigns, and CLV analysis.",
        heroImage: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Predict churn with 87% accuracy using AI.",
                description: "Our machine learning models analyze behavioral patterns to flag customers with a high probability of leaving.",
                features: ["AI Risk Scoring", "Behavioral Pattern Detection", "Early Warnings"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Automate recovery with targeted retention campaigns.",
                description: "Instantly trigger win-back emails or loyalty offers when a customer hits a critical risk threshold.",
                features: ["Automated Win-Backs", "Loyalty Programs", "A/B Testing"],
                image: "https://images.unsplash.com/photo-1553877522-43269d4ea984?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Maximize customer lifetime value.",
                description: "Track and optimize CLV with predictive analytics. Identify your most valuable segments and invest accordingly.",
                features: ["CLV Scoring", "Segment Analysis", "Revenue Attribution"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "network": {
        name: "Network Ops Hub",
        icon: Wifi,
        color: "from-cyan-500 to-blue-500",
        title: "Monitor Your Infrastructure In Real-Time",
        description: "Real-time network monitoring, outage alerts, capacity planning, and infrastructure management.",
        heroImage: "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?q=80&w=2034&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Get real-time visibility into your entire network.",
                description: "Monitor every node, link, and device with live dashboards. See topology maps and performance metrics at a glance.",
                features: ["Topology Maps", "Performance Metrics", "Health Checks"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Respond to outages before customers notice.",
                description: "Instant alerts and automated incident workflows help you resolve issues faster and minimize downtime.",
                features: ["Alert Rules", "Incident Tracking", "Root Cause Analysis"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "call-center": {
        name: "Call Center Hub",
        icon: Phone,
        color: "from-indigo-500 to-violet-500",
        title: "Empower Agents With Intelligent Call Management",
        description: "Inbound/outbound call management, agent performance tracking, call routing, and quality monitoring.",
        heroImage: "https://images.unsplash.com/photo-1556745757-8d76bdb6984b?q=80&w=2073&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Route calls intelligently to the right agent.",
                description: "AI-powered routing considers agent skills, availability, and customer history to connect callers with the best match.",
                features: ["Skills-Based Routing", "Queue Management", "IVR Builder"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Track agent performance and coach to excellence.",
                description: "Monitor call metrics, quality scores, and customer satisfaction. Identify coaching opportunities with call recordings.",
                features: ["Call Recording", "Quality Scoring", "Leaderboards"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "marketing": {
        name: "Marketing Hub",
        icon: Megaphone,
        color: "from-fuchsia-500 to-pink-500",
        title: "Generate More Qualified Leads With Marketing Hub",
        description: "Create, publish, and measure omnichannel marketing campaigns to attract and capture high-quality leads.",
        heroImage: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?q=80&w=2426&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Attract more leads by engaging customers where they are.",
                description: "Keep up with all the channels your audience interacts with. Marketing Hub provides a centralized space to create and manage omnichannel campaigns.",
                features: ["Social Publishing", "Ad Management", "SEO Tools"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Capture leads with scalable, targeted campaigns.",
                description: "Create personalized user experiences to build brand loyalty. Use our intuitive form builder to capture leads from every touchpoint.",
                features: ["Landing Pages", "Form Builder", "Pop-ups & CTAs"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Measure and maximize your marketing ROI.",
                description: "Track every campaign and see what's working. Our built-in analytics help you optimize for better conversions.",
                features: ["Campaign Analytics", "A/B Testing", "Attribution"],
                image: "https://images.unsplash.com/photo-1553877522-43269d4ea984?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "compliance": {
        name: "Compliance Hub",
        icon: ShieldCheck,
        color: "from-slate-500 to-zinc-500",
        title: "Stay Compliant With Built-In Regulatory Frameworks",
        description: "RICA verification, POPIA compliance, audit trails, and policy management for South African ISPs.",
        heroImage: "https://images.unsplash.com/photo-1563986768609-322da13575f3?q=80&w=2070&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Handle RICA and POPIA with confidence.",
                description: "Built-in workflows for South African regulatory requirements. Verify customers, manage consent, and handle data requests seamlessly.",
                features: ["RICA Verification", "Consent Management", "Data Requests"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Maintain complete audit trails.",
                description: "Every action is logged and traceable. Generate compliance reports instantly for any audit.",
                features: ["Activity Logs", "Access Control", "Audit Reports"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "talent": {
        name: "Talent Hub",
        icon: UserCog,
        color: "from-amber-500 to-yellow-500",
        title: "Build & Retain A High-Performance Team",
        description: "HR management, recruitment, performance reviews, and employee engagement tools.",
        heroImage: "https://images.unsplash.com/photo-1521737711867-e3b97375f902?q=80&w=2070&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Manage your entire workforce in one place.",
                description: "From onboarding to offboarding, track employee data, manage leave, and handle HR tasks efficiently.",
                features: ["Employee Profiles", "Leave Management", "Onboarding Workflows"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Drive performance with structured reviews.",
                description: "Set goals, conduct 360 reviews, and create development plans that help your team grow.",
                features: ["Goal Tracking", "360 Reviews", "Development Plans"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "billing": {
        name: "Billing Hub",
        icon: Receipt,
        color: "from-teal-500 to-green-500",
        title: "Automate Revenue Collection & Financial Operations",
        description: "Invoice management, payment processing, revenue cycle, and financial reporting.",
        heroImage: "https://images.unsplash.com/photo-1554224155-6726b3ff858f?q=80&w=2011&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Automate invoicing and never miss a payment.",
                description: "Generate and send invoices automatically on schedule. Support for recurring billing, pro-rata calculations, and credits.",
                features: ["Automated Invoicing", "Recurring Billing", "Pro-Rata Support"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Accept payments via any method.",
                description: "Debit orders, EFT, card payments—give customers flexibility while keeping your collections on track.",
                features: ["Debit Orders", "Card Payments", "Payment Portal"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Reduce bad debt with smart collections.",
                description: "Automated dunning, payment reminders, and debt recovery workflows keep revenue flowing.",
                features: ["Dunning Rules", "Payment Reminders", "Debt Recovery"],
                image: "https://images.unsplash.com/photo-1553877522-43269d4ea984?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "products": {
        name: "Product Hub",
        icon: Package,
        color: "from-purple-500 to-indigo-500",
        title: "Manage Your Product Catalog With Ease",
        description: "Product catalog, pricing management, bundling, and inventory tracking.",
        heroImage: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?q=80&w=2426&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Build a comprehensive product catalog.",
                description: "Define packages, add-ons, and services with flexible pricing. Create bundles and manage product versions.",
                features: ["Package Builder", "Add-Ons", "Versioning"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Implement dynamic pricing strategies.",
                description: "Create pricing rules, promotional campaigns, and discounts that drive sales and retention.",
                features: ["Price Rules", "Promotions", "Bundle Discounts"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "portal": {
        name: "Portal Hub",
        icon: Globe,
        color: "from-sky-500 to-blue-500",
        title: "White-Label Self-Service Portal For Your Customers",
        description: "Customer self-service portal, API management, and white-label configurations.",
        heroImage: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Give customers a premium self-service experience.",
                description: "Let customers view usage, pay bills, manage services, and get support—all from your branded portal.",
                features: ["Account Management", "Usage Dashboard", "Online Payments"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Fully white-label with your branding.",
                description: "Custom domain, colors, logo, and theme. Your customers see your brand, not ours.",
                features: ["Custom Domain", "Brand Colors", "Theme Editor"],
                image: "https://images.unsplash.com/photo-1553877522-43269d4ea984?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    }
}

export default function SolutionPage({ params }: { params: Promise<{ slug: string }> }) {
    const { slug } = use(params)
    const detail = moduleDetails[slug] || moduleDetails["marketing"]
    const IconComponent = detail.icon || Megaphone

    return (
        <div className="min-h-screen bg-background text-foreground">
            {/* Nav */}
            <nav className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur-xl">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex h-16 items-center justify-between">
                        <Link href="/" className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-emerald-500 transition-colors">
                            <ArrowLeft className="h-4 w-4" /> Back to Home
                        </Link>
                        <div className="flex gap-4">
                            <Button variant="outline" size="sm">Get a demo</Button>
                            <Link href="/dashboard">
                                <Button size="sm" className="bg-gradient-to-r from-emerald-500 to-teal-500 text-white">
                                    Get started free
                                </Button>
                            </Link>
                        </div>
                    </div>
                </div>
            </nav>

            {/* Hero Section */}
            <section className="py-20 px-4 sm:px-6 lg:px-8">
                <div className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-12 items-center">
                    <div>
                        <div className="flex items-center gap-2 text-xs uppercase tracking-widest font-medium text-muted-foreground mb-4">
                            <span>Product</span>
                            <span>/</span>
                            <span className={cn("bg-gradient-to-r bg-clip-text text-transparent", detail.color)}>
                                {detail.name}
                            </span>
                        </div>
                        <h1 className="text-4xl lg:text-5xl font-bold leading-tight mb-6">
                            {detail.title}
                        </h1>
                        <p className="text-lg text-muted-foreground mb-10 leading-relaxed">
                            {detail.description}
                        </p>
                        <div className="flex flex-col sm:flex-row gap-4">
                            <Button size="lg" className={cn("bg-gradient-to-r text-white", detail.color)}>
                                Get a demo
                            </Button>
                            <Link href="/dashboard">
                                <Button size="lg" variant="outline">
                                    Get started free
                                </Button>
                            </Link>
                        </div>
                    </div>
                    <div className="relative group cursor-pointer">
                        <div className="rounded-2xl overflow-hidden border border-border bg-card">
                            <img
                                src={detail.heroImage}
                                alt={detail.name}
                                className="w-full aspect-video object-cover transition-transform group-hover:scale-[1.02] duration-500"
                            />
                        </div>
                        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                            <div className="w-20 h-20 bg-background/80 backdrop-blur-md rounded-full flex items-center justify-center">
                                <PlayCircle className="h-10 w-10 text-emerald-500" />
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Intro section */}
            <section className="py-20 px-4 bg-card/50">
                <div className="max-w-3xl mx-auto text-center">
                    <h2 className="text-3xl lg:text-4xl font-bold mb-6">
                        Use OmniDome to grow your ISP and deliver tangible ROI.
                    </h2>
                    <p className="text-lg text-muted-foreground mb-12">
                        ISP management is evolving as competition grows. Businesses need new ways to break through with experiences that generate high-quality conversions.
                    </p>
                    <ol className="text-left max-w-xl mx-auto space-y-4">
                        {detail.mainPoints.map((point: any, idx: number) => (
                            <li key={idx} className="flex gap-4 items-start">
                                <span className="font-bold text-emerald-500 text-xl">{idx + 1}.</span>
                                <span className="text-lg font-medium">{point.title}</span>
                            </li>
                        ))}
                    </ol>
                </div>
            </section>

            {/* Main Points alternating */}
            {detail.mainPoints.map((point: any, idx: number) => (
                <section key={idx} className={cn("py-20 px-4 sm:px-6 lg:px-8", idx % 2 === 1 ? "bg-card/50" : "")}>
                    <div className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-16 items-center">
                        <div className={idx % 2 === 1 ? "lg:order-last" : ""}>
                            <div className="rounded-2xl overflow-hidden border border-border">
                                <img src={point.image} alt={point.title} className="w-full aspect-video object-cover" />
                            </div>
                        </div>
                        <div>
                            <h3 className="text-3xl font-bold mb-6 leading-tight">
                                {idx + 1}. {point.title}
                            </h3>
                            <p className="text-lg text-muted-foreground mb-8 leading-relaxed">
                                {point.description}
                            </p>
                            <ul className="space-y-3">
                                {point.features.map((feat: string) => (
                                    <li key={feat} className="flex items-center gap-3">
                                        <Check className="h-5 w-5 text-emerald-500" />
                                        <span className="font-medium">{feat}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </section>
            ))}

            {/* CTA */}
            <section className="py-20 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 text-white">
                <div className="max-w-3xl mx-auto text-center">
                    <h2 className="text-3xl lg:text-4xl font-bold mb-6">Ready to grow your ISP?</h2>
                    <p className="text-lg opacity-90 mb-10">Start your 14-day free trial today. No credit card required.</p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Button size="lg" className="bg-white text-emerald-600 hover:bg-white/90 font-semibold">
                            Get a demo
                        </Button>
                        <Link href="/dashboard">
                            <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10">
                                Get started free
                            </Button>
                        </Link>
                    </div>
                </div>
            </section>

            {/* Footer */}
            <footer className="border-t border-border py-12 px-4">
                <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-8">
                    <div className="flex items-center gap-2">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-500">
                            <Wifi className="h-4 w-4 text-white" />
                        </div>
                        <span className="text-lg font-bold">OmniDome</span>
                    </div>
                    <p className="text-sm text-muted-foreground">© 2026 OmniDome. All rights reserved.</p>
                </div>
            </footer>
        </div>
    )
}
