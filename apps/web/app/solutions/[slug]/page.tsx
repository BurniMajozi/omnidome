"use client"

import { use } from "react"
import Link from "next/link"
import {
    ArrowLeft,
    Check,
    PlayCircle,
    Users,
    ShieldCheck,
    Wifi,
    MessageSquare,
    DollarSign,
    HeartHandshake,
    Phone,
    Megaphone,
    Receipt,
    FileText,
    Package,
    Globe,
    UserCog,
    Headset,
    BarChart3,
    Boxes,
    Radio,
    type LucideIcon
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { ThemeToggleCompact } from "@/components/ui/theme-toggle"
import { FlickeringGrid } from "@/components/ui/flickering-grid"
import { NumberTicker } from "@/components/ui/number-ticker"
import { ShineBorder } from "@/components/ui/shine-border"

type MainPoint = {
    title: string
    description: string
    features: string[]
    image: string
}

type ModuleDetail = {
    name: string
    icon: LucideIcon
    color: string
    title: string
    description: string
    heroImage: string
    mainPoints: MainPoint[]
}

type HeroStat = {
    value: number
    label: string
    prefix?: string
    suffix?: string
    decimalPlaces?: number
}

type SolutionTheme = {
    accent: string
    accentAlt: string
    accentSoft: string
    washPrimary: string
    washSecondary: string
    gradient: string
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

// Comprehensive module details with correct content for each
const moduleDetails: Record<string, ModuleDetail> = {
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
        name: "Marketing & Media Hub",
        icon: Megaphone,
        color: "from-fuchsia-500 to-pink-500",
        title: "Digital Campaigns, Radio, Billboards & SightLive™ Analytics — All in One Platform",
        description: "Plan omnichannel digital campaigns, book SA radio airtime across Metro FM, Jacaranda FM, and 20+ stations, manage airport & billboard OOH inventory, and measure everything with SightLive™ — our proprietary post-campaign analytics engine, the first of its kind in the media industry.",
        heroImage: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?q=80&w=2426&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Attract leads across every digital channel with one command center.",
                description: "Centralize social publishing, paid ads, SEO, and content marketing in a single calendar view. AI suggests optimal posting times and budget allocation based on channel performance.",
                features: ["Content Calendar", "Social Publishing", "Ad Management", "SEO Tools", "AI Budget Optimizer"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Deliver emails at scale with enterprise-grade reliability.",
                description: "Built-in transactional and bulk email engine with SMTP and REST API, drag-and-drop template builder, DKIM/SPF/DMARC alignment, dedicated IP management, and real-time delivery analytics — inspired by best-in-class email platforms.",
                features: ["Email API & SMTP", "Template Builder", "Deliverability Monitor", "Abandoned Cart Flows", "Audience Segmentation"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Book South African radio airtime across 20+ national & regional stations.",
                description: "Access Metro FM, Ukhozi FM, Jacaranda FM, 947, East Coast Radio, Kaya FM, KFM, 5FM, Hot 102.7, Gagasi FM, and more — all from one booking panel. Track spots aired, listener reach, and lead conversions per station with real-time dashboards.",
                features: ["National & Regional Stations", "Spot Booking & Scheduling", "Listener Reach Analytics", "Radio Lead Attribution", "Campaign-to-Station ROI"],
                image: "https://images.unsplash.com/photo-1478737270239-2f02b77fc618?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Manage airport, digital & static billboard inventory across South Africa.",
                description: "Book and track outdoor & OOH media including OR Tambo and Cape Town International airport screens, N1 and M1 digital billboards, street pole ads, and mall displays. See live impression estimates, site status, and spend-per-site in one dashboard.",
                features: ["Airport Advertising", "Digital Billboards", "Static Billboards", "Street Pole & Mall", "OOH Spend Tracker"],
                image: "https://images.unsplash.com/photo-1504868584819-f8e8b4b6d7e3?q=80&w=2076&auto=format&fit=crop"
            },
            {
                title: "SightLive™ — the first proprietary post-campaign analytics for outdoor & indoor media.",
                description: "SightLive™ is our groundbreaking analytics engine that delivers verified impression counts, real-time dwell-time measurement, attention rate scoring, foot-traffic lift analysis, and brand recall benchmarks for every billboard, airport screen, mall display, and indoor sign — something no other platform in the media industry offers.",
                features: ["Verified Impressions", "Dwell-Time Measurement", "Attention Rate Scoring", "Foot-Traffic Lift", "Brand Recall Benchmarks"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Capture, score, and convert with intelligent automation.",
                description: "Build responsive landing pages, deploy smart forms and CTAs, auto-score leads based on engagement signals, and trigger personalized nurture sequences — all while tracking full-funnel attribution across digital, radio, and OOH channels.",
                features: ["Landing Pages", "Lead Scoring", "Marketing Automation", "A/B Testing", "Full-Funnel Attribution"],
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
        name: "Staff Dome",
        icon: UserCog,
        color: "from-amber-500 to-yellow-500",
        title: "A Compact HR Operating System For Your Team",
        description: "Staff Dome brings onboarding, HR knowledge, org charts, ATS, payroll via Paystack, leave and scheduling, KPI management, surveys, recognition, and attrition prediction into one governed workspace — with role-based access and asset allocation.",
        heroImage: "https://images.unsplash.com/photo-1521737711867-e3b97375f902?q=80&w=2070&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Onboarding, knowledge base, and a living org view.",
                description: "Standardize Employee Onboarding with checklists and tasks, publish an HR Knowledge Base, and keep a Company Org Chart with Pictures so everyone finds the right team fast.",
                features: ["Employee Onboarding", "HR Knowledge Base", "Company Org Chart", "Pictures"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Recruiting, payroll, and day-to-day people ops.",
                description: "Run an Applicant Tracker (ATS), handle Pay Role (Salaries and Wages using Paystack), manage Leave Management, and do Staff Scheduling based on demand — without spreadsheet handoffs.",
                features: [
                    "Applicant Tracker",
                    "Pay Role (Salaries & Wages using Paystack)",
                    "Leave Management",
                    "Staff Scheduling (Based on Demand)"
                ],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Engagement, retention, and governance — built in.",
                description: "Measure with KPI Management and Surveys, reward with Kudos (recognition programme) plus Birthdays and milestones, and reduce risk with Attrition prediction, Access control, systems role base access, and Asset allocation (laptop, company car) — including Retirement and Retrenchment flows and Employee benefit management.",
                features: [
                    "KPI Management",
                    "Surveys",
                    "Kudos (Recognition Programme)",
                    "Birthdays & Milestones",
                    "Attrition Prediction",
                    "Access Control",
                    "Systems Role Base Access",
                    "Asset Allocation (Laptop, Company Car)",
                    "Retirement",
                    "Retrenchment",
                    "Employee Benefit Management"
                ],
                image: "https://images.unsplash.com/photo-1553877522-43269d4ea984?q=80&w=2070&auto=format&fit=crop"
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
    "finance": {
        name: "Finance & FP&A Hub",
        icon: FileText,
        color: "from-emerald-500 to-cyan-500",
        title: "GAAP-Ready Finance With Scenario Planning",
        description: "Revenue recognition, expense controls, financial close, and forecasting in one finance command center.",
        heroImage: "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?q=80&w=2070&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Close the books faster with automated recognition.",
                description: "Synchronize billing, contracts, and deferred revenue schedules so GAAP reporting is always current.",
                features: ["Revenue Recognition", "Deferred Revenue", "Contract Schedules"],
                image: "https://images.unsplash.com/photo-1520607162513-77705c0f0d4a?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Control spend with automated approvals and POs.",
                description: "Route expense approvals based on delegation of authority, track assets, and enforce recurring payment policies.",
                features: ["Receipt OCR", "Approval Workflows", "Asset Register"],
                image: "https://images.unsplash.com/photo-1521791055366-0d553872125f?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Run scenario planning for EBITA and EBIT.",
                description: "Model revenue, opex, and capex changes with sliders tied to sales, billing, and network inputs.",
                features: ["Scenario Sliders", "Budget vs Reforecast", "EBITA/EBIT Views"],
                image: "https://images.unsplash.com/photo-1487014679447-9f8336841d58?q=80&w=2070&auto=format&fit=crop"
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
    },
    "analytics": {
        name: "Analytics Hub",
        icon: BarChart3,
        color: "from-indigo-500 to-cyan-500",
        title: "AI-Powered Intelligence Across Your Entire Business",
        description: "Executive summaries, revenue analytics, usage-to-billing sync, and cross-module AI insights.",
        heroImage: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Get AI-generated executive summaries on demand.",
                description: "Our AI engine analyzes data across every module to deliver actionable insights. Know your revenue trends, churn risks, and growth opportunities at a glance.",
                features: ["Executive Dashboard", "Revenue Analytics", "Trend Detection"],
                image: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?q=80&w=2426&auto=format&fit=crop"
            },
            {
                title: "Sync usage data to billing for perfect accuracy.",
                description: "Automatically correlate RADIUS usage with subscription plans. Detect orphaned accounts and billing variances before they impact revenue.",
                features: ["Usage-Billing Sync", "Variance Detection", "Orphaned Account Alerts"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Turn data into proactive business decisions.",
                description: "From upsell opportunities to proactive maintenance, our AI identifies the actions that matter most and prioritizes them by impact.",
                features: ["Upsell Signals", "Churn Predictions", "Anomaly Detection"],
                image: "https://images.unsplash.com/photo-1553877522-43269d4ea984?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "inventory": {
        name: "Inventory Hub",
        icon: Boxes,
        color: "from-amber-500 to-orange-500",
        title: "Master Your Supply Chain & Stock Management",
        description: "Multi-warehouse inventory control, global shipment tracking, auto-replenishment, and sell-through analytics.",
        heroImage: "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=2070&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Track stock across multiple warehouses in real-time.",
                description: "Monitor stock levels, reservations, and movements across your entire warehouse network. Get instant visibility into what's available and where.",
                features: ["Multi-Warehouse", "Real-Time SOH", "Stock Reservations"],
                image: "https://images.unsplash.com/photo-1553877522-43269d4ea984?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Never run out of stock with auto-replenishment.",
                description: "Set minimum thresholds for every SKU. When stock falls below the line, purchase orders are generated automatically and sent to procurement.",
                features: ["Threshold Alerts", "Auto-PO Generation", "Vendor Management"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Track global shipments from factory to warehouse.",
                description: "Monitor international shipments with ETA tracking, customs status, and automated receiving workflows.",
                features: ["Global Tracking", "ETA Monitoring", "Customs Management"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    },
    "iot": {
        name: "IoT Hub",
        icon: Radio,
        color: "from-green-500 to-teal-500",
        title: "Proactive Device Management & Fiber Signal Intelligence",
        description: "Real-time device telemetry, fiber signal monitoring, proactive maintenance, and remote command execution.",
        heroImage: "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?q=80&w=2034&auto=format&fit=crop",
        mainPoints: [
            {
                title: "Monitor every ONT, router, and smart device in real-time.",
                description: "Ingest telemetry from thousands of devices simultaneously. Track signal strength, temperature, and device health from a single dashboard.",
                features: ["Real-Time Telemetry", "Signal Monitoring", "Device Health"],
                image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Detect fiber signal degradation before customers complain.",
                description: "AI analyzes RX power trends to identify degrading connections. When thresholds are breached, maintenance tickets are auto-created and dispatched.",
                features: ["Proactive Alerts", "Auto-Ticketing", "Threshold Engine"],
                image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
            },
            {
                title: "Execute remote commands to reduce truck rolls.",
                description: "Reboot devices, run diagnostics, and toggle power remotely. Save time and money by resolving issues without dispatching a technician.",
                features: ["Remote Reboot", "Remote Diagnostics", "Power Management"],
                image: "https://images.unsplash.com/photo-1553877522-43269d4ea984?q=80&w=2070&auto=format&fit=crop"
            }
        ]
    }
}

const solutionOrder = [
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

const palettePresets: Record<string, SolutionTheme> = {
    coral: {
        accent: "#FF7A59",
        accentAlt: "#FF9F68",
        accentSoft: "#FFD166",
        washPrimary: "rgba(255, 122, 89, 0.2)",
        washSecondary: "rgba(255, 209, 102, 0.16)",
        gradient: "from-[#FF7A59] via-[#FF9F68] to-[#FFD166]"
    },
    sky: {
        accent: "#3B82F6",
        accentAlt: "#22D3EE",
        accentSoft: "#A5B4FC",
        washPrimary: "rgba(59, 130, 246, 0.2)",
        washSecondary: "rgba(34, 211, 238, 0.16)",
        gradient: "from-[#3B82F6] via-[#22D3EE] to-[#A5B4FC]"
    },
    teal: {
        accent: "#14B8A6",
        accentAlt: "#34D399",
        accentSoft: "#99F6E4",
        washPrimary: "rgba(20, 184, 166, 0.2)",
        washSecondary: "rgba(52, 211, 153, 0.16)",
        gradient: "from-[#14B8A6] via-[#34D399] to-[#99F6E4]"
    },
    indigo: {
        accent: "#6366F1",
        accentAlt: "#A855F7",
        accentSoft: "#C4B5FD",
        washPrimary: "rgba(99, 102, 241, 0.2)",
        washSecondary: "rgba(168, 85, 247, 0.16)",
        gradient: "from-[#6366F1] via-[#8B5CF6] to-[#C4B5FD]"
    },
    amber: {
        accent: "#F59E0B",
        accentAlt: "#F97316",
        accentSoft: "#FDE68A",
        washPrimary: "rgba(245, 158, 11, 0.2)",
        washSecondary: "rgba(249, 115, 22, 0.16)",
        gradient: "from-[#F59E0B] via-[#F97316] to-[#FDE68A]"
    },
    rose: {
        accent: "#F43F5E",
        accentAlt: "#FB7185",
        accentSoft: "#FBCFE8",
        washPrimary: "rgba(244, 63, 94, 0.2)",
        washSecondary: "rgba(251, 113, 133, 0.16)",
        gradient: "from-[#F43F5E] via-[#FB7185] to-[#FBCFE8]"
    },
    slate: {
        accent: "#64748B",
        accentAlt: "#94A3B8",
        accentSoft: "#E2E8F0",
        washPrimary: "rgba(100, 116, 139, 0.2)",
        washSecondary: "rgba(148, 163, 184, 0.16)",
        gradient: "from-[#64748B] via-[#94A3B8] to-[#E2E8F0]"
    }
}

const solutionThemes: Record<string, SolutionTheme> = {
    communication: palettePresets.indigo,
    sales: palettePresets.amber,
    crm: palettePresets.indigo,
    support: palettePresets.coral,
    retention: palettePresets.rose,
    network: palettePresets.teal,
    "call-center": palettePresets.indigo,
    marketing: palettePresets.coral,
    compliance: palettePresets.slate,
    talent: palettePresets.sky,
    billing: palettePresets.amber,
    finance: palettePresets.teal,
    products: palettePresets.indigo,
    portal: palettePresets.sky,
    analytics: palettePresets.indigo,
    inventory: palettePresets.amber,
    iot: palettePresets.teal,
    default: palettePresets.coral
}

const heroStatsBySlug: Record<string, HeroStat[]> = {
    communication: [
        { value: 42, suffix: "%", label: "Faster response" },
        { value: 30, suffix: "%", label: "Fewer escalations" },
        { value: 1, suffix: " inbox", label: "Unified channels" }
    ],
    sales: [
        { value: 28, suffix: "%", label: "Shorter cycles" },
        { value: 1.8, decimalPlaces: 1, suffix: "x", label: "Forecast accuracy" },
        { value: 35, suffix: "%", label: "Higher win rate" }
    ],
    crm: [
        { value: 1, suffix: " view", label: "Customer context" },
        { value: 27, suffix: "%", label: "Faster resolution" },
        { value: 22, suffix: "%", label: "Higher renewal" }
    ],
    support: [
        { value: 55, suffix: "%", label: "Faster response" },
        { value: 92, suffix: "%", label: "SLA compliance" },
        { value: 30, suffix: "%", label: "Fewer reopens" }
    ],
    retention: [
        { value: 18, suffix: "%", label: "Lower churn" },
        { value: 2.4, decimalPlaces: 1, suffix: "x", label: "Win-back lift" },
        { value: 12, suffix: " days", label: "Earlier signal" }
    ],
    network: [
        { value: 99.95, decimalPlaces: 2, suffix: "%", label: "Uptime" },
        { value: 38, suffix: "%", label: "Faster resolution" },
        { value: 25, suffix: "%", label: "Fewer outages" }
    ],
    "call-center": [
        { value: 28, suffix: "%", label: "Lower handle time" },
        { value: 2, suffix: "x", label: "QA coverage" },
        { value: 15, suffix: "%", label: "Higher CSAT" }
    ],
    marketing: [
        { value: 3, suffix: "x", label: "Faster launches" },
        { value: 24, suffix: "%", label: "Higher lead quality" },
        { value: 40, suffix: "%", label: "Fewer approval loops" }
    ],
    compliance: [
        { value: 100, suffix: "%", label: "Audit readiness" },
        { value: 50, suffix: "%", label: "Faster approvals" },
        { value: 0, suffix: "", label: "Missed deadlines" }
    ],
    talent: [
        { value: 60, suffix: "%", label: "Faster onboarding" },
        { value: 2, suffix: "x", label: "Review completion" },
        { value: 75, suffix: "%", label: "Fewer requests" }
    ],
    billing: [
        { value: 35, suffix: "%", label: "Faster collections" },
        { value: 28, suffix: "%", label: "Fewer overdue" },
        { value: 2, suffix: "x", label: "Invoice accuracy" }
    ],
    finance: [
        { value: 58, suffix: "%", label: "Faster close" },
        { value: 30, suffix: "%", label: "Fewer recon issues" },
        { value: 24, suffix: " hrs", label: "Time to forecast" }
    ],
    products: [
        { value: 4, suffix: "x", label: "Faster launches" },
        { value: 38, suffix: "%", label: "Fewer pricing errors" },
        { value: 2.1, decimalPlaces: 1, suffix: "x", label: "Upsell lift" }
    ],
    portal: [
        { value: 60, suffix: "%", label: "Self-serve deflection" },
        { value: 4, suffix: "x", label: "Portal adoption" },
        { value: 25, suffix: "%", label: "Fewer tickets" }
    ],
    analytics: [
        { value: 5, suffix: "x", label: "Faster insights" },
        { value: 1, suffix: " dashboard", label: "Unified view" },
        { value: 20, suffix: "%", label: "Fewer data requests" }
    ],
    inventory: [
        { value: 50, suffix: "%", label: "Fewer stockouts" },
        { value: 2, suffix: "x", label: "Faster replenishment" },
        { value: 18, suffix: "%", label: "Lower carry cost" }
    ],
    iot: [
        { value: 33, suffix: "%", label: "Fewer truck rolls" },
        { value: 2, suffix: "x", label: "Faster detection" },
        { value: 15, suffix: "%", label: "Higher uptime" }
    ],
    default: [
        { value: 3, suffix: "x", label: "Faster execution" },
        { value: 25, suffix: "%", label: "Lower overhead" },
        { value: 2, suffix: "x", label: "Clearer visibility" }
    ]
}

const solutionCaseStudies: Record<string, CaseStudy> = {
    communication: {
        label: "Communication",
        title: "Team conversations consolidated into one operating layer",
        summary:
            "Service teams unified internal chat, customer updates, and escalations in one workspace so requests no longer lived in silos.",
        challenge:
            "Messages were split across inboxes and tools, slowing handoffs and hiding priority work.",
        approach:
            "A unified inbox with routing rules, ownership visibility, and shared response templates.",
        image: "https://images.unsplash.com/photo-1553877522-43269d4ea984?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "42%", label: "Faster response time" },
            { value: "30%", label: "Fewer escalations" },
            { value: "1 inbox", label: "Unified channels" },
            { value: "2x", label: "Better visibility" }
        ],
        highlights: [
            "Shared inbox with ownership and priorities.",
            "Templates and escalation paths baked in.",
            "Unified timeline across teams.",
            "Real-time visibility for leaders."
        ],
        steps: [
            { title: "Week 1 - Channel audit", description: "Consolidated channels and defined routing paths." },
            { title: "Week 2 - Routing rules", description: "Automated triage and escalation workflows." },
            { title: "Week 3 - Insights", description: "Rolled out dashboards and weekly review cadences." }
        ],
        quote: {
            body: "We see every request in one place and respond faster.",
            name: "Operations Lead",
            role: "Service team"
        }
    },
    sales: {
        label: "Sales",
        title: "Pipeline execution standardized from lead to close",
        summary:
            "Sales operations aligned stages, approvals, and pricing to improve forecast accuracy and deal velocity.",
        challenge:
            "Deal data lived in spreadsheets and notes, creating inconsistent stages and missed follow-ups.",
        approach:
            "A single pipeline with automated stage rules, quote approvals, and live reporting.",
        image: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "35%", label: "Shorter sales cycle" },
            { value: "1.8x", label: "Forecast accuracy" },
            { value: "28%", label: "Higher win rate" },
            { value: "2 days", label: "Faster approvals" }
        ],
        highlights: [
            "Single source of truth for deal stages.",
            "Quote automation with approval controls.",
            "Sales enablement assets linked to stages.",
            "Clear handoffs to onboarding."
        ],
        steps: [
            { title: "Week 1 - Stage definitions", description: "Standardized pipeline stages and criteria." },
            { title: "Week 2 - Quote automation", description: "Built pricing rules and approval flows." },
            { title: "Week 3 - Forecasting", description: "Delivered real-time forecasting dashboards." }
        ],
        quote: {
            body: "Forecasts finally match reality and deals move faster.",
            name: "Head of Sales Ops",
            role: "Revenue team"
        }
    },
    crm: {
        label: "CRM",
        title: "Customer context unified across teams",
        summary:
            "Customer success teams consolidated profiles, interactions, and lifecycle data into one view for faster decisions.",
        challenge:
            "Teams lacked shared context, leading to duplicated outreach and slow issue resolution.",
        approach:
            "A 360 view with activity timelines, segmentation, and shared notes.",
        image: "https://images.unsplash.com/photo-1552664730-d307ca884978?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "1 view", label: "Customer context" },
            { value: "27%", label: "Faster resolution" },
            { value: "22%", label: "Higher renewal" },
            { value: "3x", label: "Segmentation speed" }
        ],
        highlights: [
            "Unified profiles with full interaction history.",
            "Segment-based playbooks for outreach.",
            "Shared notes and ownership tracking.",
            "Lifecycle dashboards for leadership."
        ],
        steps: [
            { title: "Week 1 - Data consolidation", description: "Unified customer data across modules." },
            { title: "Week 2 - Segment rules", description: "Built dynamic segmentation and alerts." },
            { title: "Week 3 - Lifecycle playbooks", description: "Rolled out outreach templates and tracking." }
        ],
        quote: {
            body: "Every team now works from the same customer story.",
            name: "Customer Success Lead",
            role: "Account management"
        }
    },
    support: {
        label: "Support",
        title: "Support queues shifted from reactive to proactive",
        summary:
            "Support teams centralized tickets and knowledge to reduce response time and reopens.",
        challenge:
            "Tickets were scattered across channels and lacked consistent priority handling.",
        approach:
            "Unified ticketing with SLA rules, smart routing, and self-serve content.",
        image: "https://images.unsplash.com/photo-1556745757-8d76bdb6984b?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "55%", label: "Faster first response" },
            { value: "92%", label: "SLA compliance" },
            { value: "30%", label: "Fewer reopens" },
            { value: "3 channels", label: "Unified intake" }
        ],
        highlights: [
            "Smart routing with priority rules.",
            "Self-serve knowledge base.",
            "Real-time queue visibility.",
            "Customer feedback loops."
        ],
        steps: [
            { title: "Week 1 - Channel consolidation", description: "Unified intake from email and chat." },
            { title: "Week 2 - SLA automation", description: "Configured SLA timers and escalations." },
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
        summary:
            "Retention teams consolidated risk signals and offers into one system to trigger timely interventions.",
        challenge:
            "Risk signals were delayed and retention offers were inconsistent.",
        approach:
            "Automated risk scoring with playbooks and win-back workflows.",
        image: "https://images.unsplash.com/photo-1551434678-e076c223a692?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "18%", label: "Lower churn" },
            { value: "2.4x", label: "Win-back lift" },
            { value: "12 days", label: "Earlier signals" },
            { value: "85%", label: "Coverage" }
        ],
        highlights: [
            "Automated churn scoring and alerts.",
            "Retention offer playbooks by segment.",
            "Save desk workflows with context.",
            "Campaign ROI tracking."
        ],
        steps: [
            { title: "Week 1 - Risk model setup", description: "Connected signals and calibrated thresholds." },
            { title: "Week 2 - Playbook automation", description: "Launched offer workflows and triggers." },
            { title: "Week 3 - Save desk dashboards", description: "Rolled out performance reporting." }
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
        summary:
            "Network teams moved monitoring, incidents, and capacity planning into a shared command center.",
        challenge:
            "Alerts were noisy and incident response lacked clear ownership.",
        approach:
            "Unified dashboards with automated incident workflows and capacity insights.",
        image: "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "38%", label: "Faster resolution" },
            { value: "25%", label: "Fewer outages" },
            { value: "99.95%", label: "Uptime" },
            { value: "1 hub", label: "Command center" }
        ],
        highlights: [
            "Real-time topology with health signals.",
            "Automated incident routing and escalation.",
            "Capacity planning tied to growth.",
            "Post-incident reviews and learning."
        ],
        steps: [
            { title: "Week 1 - Telemetry ingest", description: "Connected monitoring and alert sources." },
            { title: "Week 2 - Alert tuning", description: "Reduced noise and set ownership." },
            { title: "Week 3 - Incident playbooks", description: "Standardized response workflows." }
        ],
        quote: {
            body: "We see issues sooner and respond with confidence.",
            name: "Network Operations Lead",
            role: "Infrastructure team"
        }
    },
    "call-center": {
        label: "Call Center",
        title: "Agent workflows streamlined for faster resolutions",
        summary:
            "Call center leaders unified routing, coaching, and QA to improve handling time and satisfaction.",
        challenge:
            "Agents lacked context and QA coverage was inconsistent across shifts.",
        approach:
            "Skills-based routing, live coaching cues, and performance dashboards.",
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
        summary:
            "A mid-market marketing team replaced spreadsheets and inbox approvals with a unified campaign workspace, speeding up launches while keeping brand standards tight.",
        challenge:
            "Campaign requests, assets, and approvals lived in different tools, which created delays, duplicated work, and inconsistent reporting.",
        approach:
            "A single workflow for intake, approvals, and performance tracking with automated handoffs to stakeholders.",
        image: "https://images.unsplash.com/photo-1487014679447-9f8336841d58?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "3x", label: "Faster campaign launches" },
            { value: "24%", label: "Higher lead quality" },
            { value: "40%", label: "Fewer approval loops" },
            { value: "1 week", label: "Time to go live" }
        ],
        highlights: [
            "Unified campaign intake with clear briefs and owners.",
            "Automated brand checks and approvals.",
            "Regional rollouts with shared templates.",
            "Live performance dashboards for stakeholders."
        ],
        steps: [
            {
                title: "Week 1 - Intake and taxonomy",
                description: "Standardized campaign briefs, assets, and ownership across teams."
            },
            {
                title: "Week 2 - Approvals and automation",
                description: "Built automated review stages and notifications for every launch."
            },
            {
                title: "Week 3 - Reporting and ROI",
                description: "Connected performance data and executive-ready dashboards."
            }
        ],
        quote: {
            body: "We finally launch on time without losing quality or visibility.",
            name: "Marketing Operations Lead",
            role: "Growth team"
        }
    },
    compliance: {
        label: "Compliance",
        title: "Compliance workflows standardized across teams",
        summary:
            "Compliance leaders centralized policy, evidence, and approvals to stay audit-ready.",
        challenge:
            "Evidence lived in folders and approvals were manual and inconsistent.",
        approach:
            "A governed compliance hub with automated checklists and audit trails.",
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
            "Real-time compliance dashboards."
        ],
        steps: [
            { title: "Week 1 - Policy mapping", description: "Centralized policies and ownership." },
            { title: "Week 2 - Evidence workflows", description: "Automated evidence collection." },
            { title: "Week 3 - Audit reporting", description: "Delivered audit-ready dashboards." }
        ],
        quote: {
            body: "Audits are now routine, not stressful.",
            name: "Compliance Officer",
            role: "Risk team"
        }
    },
    talent: {
        label: "Human Resources",
        title: "People operations standardized from hire to review",
        summary:
            "A people team consolidated onboarding, employee records, and review cycles into a single system that reduced admin work and improved the employee experience.",
        challenge:
            "Employee data, onboarding steps, and review timelines were fragmented across documents, making compliance and reporting slow.",
        approach:
            "A governed HR workspace with automated onboarding, review reminders, and policy acknowledgements.",
        image: "https://images.unsplash.com/photo-1521737711867-e3b97375f902?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "60%", label: "Faster onboarding" },
            { value: "2x", label: "Review completion" },
            { value: "75%", label: "Fewer ad hoc requests" },
            { value: "10 days", label: "Time to fill roles" }
        ],
        highlights: [
            "Single source of truth for employee records.",
            "Automated onboarding checklists and task handoffs.",
            "Review cycles with structured templates and reminders.",
            "Policy acknowledgements with audit trails."
        ],
        steps: [
            {
                title: "Week 1 - Data cleanup",
                description: "Centralized employee records and normalized core fields."
            },
            {
                title: "Week 2 - Workflow build",
                description: "Automated onboarding, reviews, and approvals in one hub."
            },
            {
                title: "Week 3 - Insights and surveys",
                description: "Rolled out dashboards and pulse surveys for leadership."
            }
        ],
        quote: {
            body: "We spend less time chasing tasks and more time supporting people.",
            name: "People Operations Manager",
            role: "HR team"
        }
    },
    billing: {
        label: "Billing",
        title: "Billing operations moved to automated collections",
        summary:
            "Billing teams centralized invoicing, payments, and dunning to improve cash flow and visibility.",
        challenge:
            "Manual invoicing and reminders created delays and revenue leakage.",
        approach:
            "Automated billing schedules with payment workflows and collection triggers.",
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
        title: "Close cycle shortened with automated controls",
        summary:
            "A finance team connected billing, expenses, and approvals in one place, cutting the close cycle and improving forecast accuracy.",
        challenge:
            "Reconciliations and approvals were manual, causing late closes and inconsistent reporting.",
        approach:
            "Automated reconciliations with standardized approvals and real-time reporting.",
        image: "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "58%", label: "Faster close" },
            { value: "30%", label: "Fewer recon issues" },
            { value: "2x", label: "Faster approvals" },
            { value: "24 hrs", label: "Time to forecast" }
        ],
        highlights: [
            "Automated reconciliations and exceptions.",
            "Approval workflows with clear ownership.",
            "Live dashboards for leadership reporting.",
            "Scenario planning tied to operational inputs."
        ],
        steps: [
            {
                title: "Week 1 - Data mapping",
                description: "Connected billing, expenses, and chart of accounts."
            },
            {
                title: "Week 2 - Controls and approvals",
                description: "Implemented approval policies with audit-ready trails."
            },
            {
                title: "Week 3 - Reporting and scenarios",
                description: "Delivered real-time reporting and forecasting models."
            }
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
        summary:
            "Product teams centralized catalogs, pricing rules, and approvals to launch faster with fewer errors.",
        challenge:
            "Catalog updates were manual and pricing logic was inconsistent across regions.",
        approach:
            "A governed product catalog with pricing rules, approvals, and automated handoffs.",
        image: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "4x", label: "Faster launches" },
            { value: "38%", label: "Fewer pricing errors" },
            { value: "2.1x", label: "Upsell lift" },
            { value: "14 days", label: "Time to new bundle" }
        ],
        highlights: [
            "Single catalog for packages and add-ons.",
            "Dynamic pricing rules by segment.",
            "Approval workflows with audit trails.",
            "One-click rollout to billing and portal."
        ],
        steps: [
            { title: "Week 1 - Catalog cleanup", description: "Normalized plans and pricing tiers." },
            { title: "Week 2 - Pricing rules", description: "Built rules and promotional logic." },
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
        summary:
            "Portal adoption grew with branded self-service and guided workflows that reduced support demand.",
        challenge:
            "Customers lacked visibility and opened tickets for routine tasks.",
        approach:
            "A white-label portal with guided actions, payments, and support deflection.",
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
            { title: "Week 1 - Portal design", description: "Defined branded layouts and content." },
            { title: "Week 2 - Self-serve flows", description: "Implemented payments and service changes." },
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
        summary:
            "Teams consolidated metrics across modules into a single dashboard for faster decisions.",
        challenge:
            "Executives spent days pulling data from multiple systems.",
        approach:
            "Unified analytics with automated KPI snapshots and insight alerts.",
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
            "Self-serve reporting for teams."
        ],
        steps: [
            { title: "Week 1 - KPI definitions", description: "Aligned metrics across teams." },
            { title: "Week 2 - Data pipelines", description: "Connected operational data sources." },
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
        summary:
            "Operations teams connected inventory, procurement, and fulfillment with real-time tracking.",
        challenge:
            "Stockouts and manual updates slowed installations and repairs.",
        approach:
            "Centralized inventory with auto-replenishment and shipment tracking.",
        image: "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=2200&auto=format&fit=crop",
        stats: [
            { value: "50%", label: "Fewer stockouts" },
            { value: "2x", label: "Faster replenishment" },
            { value: "18%", label: "Lower carry cost" },
            { value: "1 view", label: "Stock visibility" }
        ],
        highlights: [
            "Multi-warehouse tracking in one hub.",
            "Auto-PO generation and approvals.",
            "Reservation controls for installs.",
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
        summary:
            "IoT telemetry centralized to detect issues early and trigger remote fixes.",
        challenge:
            "Device issues were discovered only after customer complaints.",
        approach:
            "Telemetry monitoring with automated alerts and remote actions.",
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

export default function SolutionPage({ params }: { params: Promise<{ slug: string }> }) {
    const { slug } = use(params)
    const detail = moduleDetails[slug] || moduleDetails["marketing"]
    const theme = solutionThemes[slug] || solutionThemes.default
    const heroStats = heroStatsBySlug[slug] || heroStatsBySlug.default
    const caseStudy = solutionCaseStudies[slug]
    const orderIndex = Math.max(0, solutionOrder.indexOf(slug))
    const flipLayout = orderIndex % 2 === 1
    const flipCaseStudy = orderIndex % 2 === 0

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

            {/* Nav */}
            <nav className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur-xl">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex h-16 items-center justify-between">
                        <Link href="/" className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-emerald-500 transition-colors">
                            <ArrowLeft className="h-4 w-4" /> Back to Home
                        </Link>
                        <div className="flex gap-4 items-center">
                            <ThemeToggleCompact />
                            <Button variant="outline" size="sm">Get a demo</Button>
                            <Link href="/auth">
                                <Button size="sm" className="bg-gradient-to-r from-emerald-500 to-teal-500 text-white">
                                    Get started free
                                </Button>
                            </Link>
                        </div>
                    </div>
                </div>
            </nav>

            {/* Hero Section */}
            <section className="py-24 px-4 sm:px-6 lg:px-8 relative overflow-hidden bg-[#F8F5F2]">
                <div
                    className="absolute inset-0"
                    style={{
                        backgroundImage: `radial-gradient(circle at 20% 20%, ${theme.washPrimary}, transparent 55%), radial-gradient(circle at 80% 70%, ${theme.washSecondary}, transparent 60%)`
                    }}
                />
                <div className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-12 items-center relative">
                    <div className={cn("space-y-6", flipLayout ? "lg:order-2" : "lg:order-1")}>
                        <div className="inline-flex items-center gap-2 rounded-full border border-black/5 bg-white/80 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-[0.3em] text-slate-600 shadow-sm">
                            Solution
                            <span className="text-slate-900">{detail.name}</span>
                        </div>
                        <h1 className="text-4xl lg:text-5xl font-semibold tracking-tight text-slate-950">
                            {detail.title}
                        </h1>
                        <p className="text-lg text-slate-600 leading-relaxed">
                            {detail.description}
                        </p>
                        <div className="flex flex-col sm:flex-row gap-4">
                            <Button size="lg" className={cn("bg-gradient-to-r text-white shadow-lg shadow-black/10", theme.gradient)}>
                                Get a demo
                            </Button>
                            <Link href="/auth">
                                <Button size="lg" variant="outline" className="border-black/10 text-slate-700">
                                    Get started free
                                </Button>
                            </Link>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pt-4">
                            {heroStats.map((stat) => (
                                <div key={stat.label} className="rounded-2xl border border-black/5 bg-white/80 px-4 py-3 shadow-sm">
                                    <NumberTicker
                                        value={stat.value}
                                        prefix={stat.prefix}
                                        suffix={stat.suffix}
                                        decimalPlaces={stat.decimalPlaces ?? 0}
                                        className="text-2xl font-semibold text-slate-900"
                                    />
                                    <p className="text-[11px] uppercase tracking-[0.25em] text-slate-500 mt-1">
                                        {stat.label}
                                    </p>
                                </div>
                            ))}
                        </div>
                    </div>
                    <div className={cn("relative group", flipLayout ? "lg:order-1" : "lg:order-2")}>
                        <ShineBorder
                            borderRadius={28}
                            borderWidth={1.5}
                            color={[theme.accent, theme.accentAlt, theme.accentSoft]}
                            className="rounded-[28px]"
                        >
                            <div className="rounded-[26px] overflow-hidden border border-black/10 bg-white shadow-2xl">
                                <img
                                    src={detail.heroImage}
                                    alt={detail.name}
                                    className="w-full aspect-video object-cover transition-transform duration-500 group-hover:scale-[1.02]"
                                />
                            </div>
                        </ShineBorder>
                        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                            <div className="w-20 h-20 bg-white/80 backdrop-blur-md rounded-full flex items-center justify-center shadow-lg">
                                <PlayCircle className="h-10 w-10" style={{ color: theme.accent }} />
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Intro section */}
            <section className="py-20 px-4 bg-white">
                <div className="max-w-3xl mx-auto text-center">
                    <h2 className="text-3xl lg:text-4xl font-semibold mb-6 text-slate-900">
                        Build repeatable execution without losing speed.
                    </h2>
                    <p className="text-lg text-slate-600 mb-12">
                        Replace manual handoffs with guided workflows, shared context, and measurable outcomes across every team.
                    </p>
                    <ol className="text-left max-w-xl mx-auto space-y-4">
                        {detail.mainPoints.map((point, idx) => (
                            <li key={idx} className="flex gap-4 items-start">
                                <span className="font-semibold text-xl" style={{ color: theme.accent }}>{idx + 1}.</span>
                                <span className="text-lg font-medium text-slate-800">{point.title}</span>
                            </li>
                        ))}
                    </ol>
                </div>
            </section>

            {/* Main Points alternating */}
            {detail.mainPoints.map((point, idx) => (
                <section key={idx} className={cn("py-20 px-4 sm:px-6 lg:px-8", idx % 2 === 1 ? "bg-[#F8F5F2]" : "bg-white")}>
                    <div className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-16 items-center">
                        <div className={idx % 2 === 1 ? "lg:order-last" : ""}>
                            <ShineBorder
                                borderRadius={24}
                                borderWidth={1}
                                color={[theme.accent, theme.accentAlt, theme.accentSoft]}
                                className="rounded-[24px]"
                            >
                                <div className="rounded-[22px] overflow-hidden border border-black/10 bg-white">
                                    <img src={point.image} alt={point.title} className="w-full aspect-video object-cover" />
                                </div>
                            </ShineBorder>
                        </div>
                        <div>
                            <div className="text-[11px] uppercase tracking-[0.3em] text-slate-500 mb-4">
                                Feature {idx + 1}
                            </div>
                            <h3 className="text-3xl font-semibold mb-6 leading-tight text-slate-900">
                                {point.title}
                            </h3>
                            <p className="text-lg text-slate-600 mb-8 leading-relaxed">
                                {point.description}
                            </p>
                            <ul className="space-y-3">
                                {point.features.map((feat: string) => (
                                    <li key={feat} className="flex items-center gap-3">
                                        <Check className="h-5 w-5" style={{ color: theme.accent }} />
                                        <span className="font-medium text-slate-800">{feat}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </section>
            ))}

            {/* Case Study */}
            {caseStudy && (
                <section className="py-24 px-4 sm:px-6 lg:px-8 relative overflow-hidden bg-[#F8F5F2]">
                    <div
                        className="absolute inset-0"
                        style={{
                            backgroundImage: `radial-gradient(circle at 20% 20%, ${theme.washPrimary}, transparent 55%), radial-gradient(circle at 80% 70%, ${theme.washSecondary}, transparent 60%)`
                        }}
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
                                    borderRadius={20}
                                    borderWidth={1}
                                    color={[theme.accent, theme.accentAlt, theme.accentSoft]}
                                    className="rounded-[20px]"
                                >
                                    <div className="rounded-[18px] overflow-hidden border border-black/10 bg-white">
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
                                    <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500 mb-4">Launch Playbook</p>
                                    <div className="space-y-4">
                                        {caseStudy.steps.map((step, idx) => {
                                            const stepNumber = step.title.match(/\d+/)?.[0] ?? `${idx + 1}`
                                            return (
                                                <div key={step.title} className="flex gap-4 items-start">
                                                    <div className={cn("h-10 w-10 rounded-xl bg-gradient-to-br flex items-center justify-center text-white text-sm font-bold shadow-sm", theme.gradient)}>
                                                        {stepNumber}
                                                    </div>
                                                    <div>
                                                        <p className="font-semibold text-slate-900">{step.title}</p>
                                                        <p className="text-sm text-slate-600 leading-relaxed">{step.description}</p>
                                                    </div>
                                                </div>
                                            )
                                        })}
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
                                    <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500 mb-4">Results</p>
                                    <div className="space-y-3">
                                        {caseStudy.highlights.map((item) => (
                                            <div key={item} className="flex items-start gap-3">
                                                <Check className="h-5 w-5 mt-0.5" style={{ color: theme.accent }} />
                                                <p className="text-sm text-slate-900">{item}</p>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                <div className="rounded-2xl border border-black/5 bg-white p-6">
                                    <p className="text-lg font-semibold mb-4 text-slate-900">&ldquo;{caseStudy.quote.body}&rdquo;</p>
                                    <div className="text-sm text-slate-500">
                                        <span className="font-semibold text-slate-900">{caseStudy.quote.name}</span> - {caseStudy.quote.role}
                                    </div>
                                </div>

                                <div className="rounded-2xl border border-black/5 bg-white p-6">
                                    <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500 mb-3">Ready to replicate this?</p>
                                    <p className="text-sm text-slate-600 mb-5 leading-relaxed">
                                        {detail.name} gives your team the same launch workflow and governance, tailored for this solution.
                                    </p>
                                    <div className="flex flex-col sm:flex-row gap-3">
                                        <Link href="/auth">
                                            <Button className={cn("bg-gradient-to-r text-white", theme.gradient)}>
                                                Get a demo
                                            </Button>
                                        </Link>
                                        <Link href="/auth">
                                            <Button variant="outline">
                                                Talk to our team
                                            </Button>
                                        </Link>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>
            )}

            {/* CTA */}
            <section className="py-20 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 text-white">
                <div className="max-w-3xl mx-auto text-center">
                    <h2 className="text-3xl lg:text-4xl font-bold mb-6">Ready to grow your ISP?</h2>
                    <p className="text-lg opacity-90 mb-10">Start your 14-day free trial today. No credit card required.</p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Button size="lg" className="bg-white text-emerald-600 hover:bg-white/90 font-semibold">
                            Get a demo
                        </Button>
                        <Link href="/auth">
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
                        <img src="/logo-new.svg" alt="OmniDome" className="h-10 w-10" />
                        <span className="text-sm font-semibold">OmniDome</span>
                    </div>
                    <p className="text-sm text-muted-foreground">© 2026 OmniDome. All rights reserved.</p>
                </div>
            </footer>
        </div>
    )
}

