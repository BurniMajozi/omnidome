"use client"

import { useState, useEffect, useRef } from "react"
import { useTheme } from "next-themes"
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
    ArrowRight,
    Sparkles,
    Menu,
    X,
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
    Rocket,
    type LucideIcon
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { CalendarIcon, FileTextIcon } from "@radix-ui/react-icons"
import { BellIcon, Share2Icon, TrendingUp, Orbit } from "lucide-react"
import { BentoCard, BentoGrid } from "@/components/ui/bento-grid"
import { Marquee } from "@/components/ui/marquee"
import { FAQSection } from "@/components/ui/faq-section"
import { Calendar } from "@/components/ui/calendar"
import { AnimatedListDemo } from "@/components/demo/animated-list-demo"
import { AIChatDemo } from "@/components/demo/ai-chat-demo"
import { AnimatedBeamMultipleOutputDemo } from "@/components/demo/animated-beam-demo"
import { OrbitingCirclesDemo2 } from "@/components/demo/orbiting-circles-demo"
import { GrowthGraphDemo } from "@/components/demo/growth-graph-demo"
import { AIPitchDemo } from "@/components/demo/ai-pitch-demo"
import { ThemeToggle } from "@/components/ui/theme-toggle"
import { AnimatedStats } from "@/components/demo/animated-stats"
import { ShineBorder } from "@/components/ui/shine-border"
import { EmojiPointer } from "@/components/ui/pointer"
import { HowItWorks } from "@/components/demo/how-it-works"
import { TestimonialsMarquee } from "@/components/demo/testimonials-marquee"

// Module emojis for pointer
const moduleEmojis = ["🚀", "💬", "📊", "📞", "📢", "🛡️", "👥", "💰", "📦", "🌐", "❤️", "🎯", "⚡"]

// All 13 modules (excluding Dashboard Overview)
const modules = [
    {
        id: "communication",
        icon: MessageSquare,
        name: "Communication Dome",
        description: "Team collaboration, internal messaging, and unified communications.",
        category: "Core",
        color: "from-blue-600 via-indigo-500 to-violet-500",
        slug: "communication"
    },
    {
        id: "sales",
        icon: DollarSign,
        name: "Sales Dome",
        description: "Deal pipeline, revenue tracking, quote generation.",
        category: "Revenue",
        color: "from-emerald-500 via-teal-400 to-cyan-500",
        slug: "sales"
    },
    {
        id: "crm",
        icon: Users,
        name: "CRM Dome",
        description: "Customer relationship management and journey analytics.",
        category: "Customer",
        color: "from-indigo-600 via-violet-500 to-purple-500",
        slug: "crm"
    },
    {
        id: "service",
        icon: Headset,
        name: "Service Dome",
        description: "Ticket management, SLA tracking, knowledge base.",
        category: "Customer",
        color: "from-orange-500 via-amber-400 to-yellow-500",
        slug: "support"
    },
    {
        id: "retention",
        icon: HeartHandshake,
        name: "Retention Dome",
        description: "AI-powered churn prediction and CLV analysis.",
        category: "Analytics",
        color: "from-rose-500 via-pink-500 to-fuchsia-500",
        slug: "retention"
    },
    {
        id: "network",
        icon: Wifi,
        name: "Network Dome",
        description: "Real-time monitoring, outage alerts, capacity planning.",
        category: "Operations",
        color: "from-cyan-500 via-blue-500 to-indigo-500",
        slug: "network"
    },
    {
        id: "call-center",
        icon: Phone,
        name: "Call Center Dome",
        description: "Inbound/outbound call management and agent performance.",
        category: "Customer",
        color: "from-blue-600 via-indigo-600 to-violet-600",
        slug: "call-center"
    },
    {
        id: "marketing",
        icon: Megaphone,
        name: "Marketing Dome",
        description: "Campaign management, email marketing, analytics.",
        category: "Revenue",
        color: "from-fuchsia-600 via-purple-600 to-indigo-600",
        slug: "marketing"
    },
    {
        id: "compliance",
        icon: ShieldCheck,
        name: "Compliance Dome",
        description: "RICA verification, POPIA compliance, audit trails.",
        category: "Operations",
        color: "from-slate-400 via-slate-500 to-slate-600",
        slug: "compliance"
    },
    {
        id: "talent",
        icon: UserCog,
        name: "Talent Dome",
        description: "HR management, recruitment, performance reviews.",
        category: "Operations",
        color: "from-yellow-500 via-amber-500 to-orange-500",
        slug: "talent"
    },
    {
        id: "billing",
        icon: Receipt,
        name: "Billing Dome",
        description: "Invoice management, payment processing, collections.",
        category: "Revenue",
        color: "from-teal-500 via-emerald-500 to-green-500",
        slug: "billing"
    },
    {
        id: "products",
        icon: Package,
        name: "Product Dome",
        description: "Product catalog, pricing management, bundling.",
        category: "Operations",
        color: "from-violet-600 via-purple-600 to-fuchsia-600",
        slug: "products"
    },
    {
        id: "portal",
        icon: Globe,
        name: "Portal Dome",
        description: "Customer self-service portal and white-label configurations.",
        category: "Core",
        color: "from-sky-400 via-blue-500 to-indigo-600",
        slug: "portal"
    },
]

type SolutionItem = {
    title: string
    description: string
    slug: string
    icon: LucideIcon
    color: string
}

// Solutions grouped by category with colors
const solutionsByCategory: Record<string, SolutionItem[]> = {
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
        { icon: BookOpen, title: "Blog", description: "Latest insights and updates", href: "/blog" },
    ],
    services: [
        { icon: Rocket, title: "Onboarding", description: "Get up and running quickly", href: "/resources/services" },
        { icon: GraduationCap, title: "Customer Training", description: "Master every module", href: "/resources/services" },
        { icon: Zap, title: "Migration", description: "Seamless data transfer", href: "/resources/services" },
    ],
    partners: [
        { icon: Handshake, title: "Reseller Program", description: "Earn up to 35% commission", href: "/resources/partners" },
        { icon: Building2, title: "Solutions Partner", description: "Implementation & consulting", href: "/resources/partners" },
        { icon: Zap, title: "Integration Partner", description: "Build apps and integrations", href: "/resources/partners" },
    ],
    support: [
        { icon: FileText, title: "Documentation", description: "Technical guides and API docs", href: "/docs" },
        { icon: Rocket, title: "Developer Portal", description: "APIs, SDKs and developer tools", href: "/developers" },
        { icon: HelpCircle, title: "Support Center", description: "Get help from our team", href: "/support" },
    ]
}

// AI Features Showcase data
const aiFeatures = [
    {
        id: 0,
        title: "Unified Communication",
        image: "/unified-communication.png",
    },
    {
        id: 1,
        title: "Unified Sales",
        image: "/unified-sales.png",
    },
    {
        id: 2,
        title: "Predict Churn with AI",
        image: "/predict-churn-with-ai.png",
    },
    {
        id: 3,
        title: "Agentic AI Product Management",
        image: "/agentic-ai-product-management.png",
    },
]

const rotatingWords = ["ISP", "Marketing", "Sales", "CRM", "Billing", "Network", "Support", "Call Center", "Retention"]

// AI Features Showcase Component
function AIFeaturesShowcase() {
    const [activeIndex, setActiveIndex] = useState(0)
    const [progress, setProgress] = useState(0)
    const intervalDuration = 5000 // 5 seconds per feature
    
    // Simple timer that cycles through all 4 features
    useEffect(() => {
        const timer = setInterval(() => {
            setActiveIndex((prev) => (prev + 1) % 4)
            setProgress(0)
        }, intervalDuration)
        
        return () => clearInterval(timer)
    }, [])
    
    // Progress bar animation
    useEffect(() => {
        const progressTimer = setInterval(() => {
            setProgress((prev) => Math.min(prev + 1, 100))
        }, intervalDuration / 100)
        
        return () => clearInterval(progressTimer)
    }, [activeIndex])
    
    const handleTabClick = (index: number) => {
        setActiveIndex(index)
        setProgress(0)
    }
    
    const currentFeature = aiFeatures[activeIndex]
    
    return (
        <section className="py-24 px-4 sm:px-6 lg:px-8 bg-gradient-to-b from-background to-muted/30">
            <div className="mx-auto max-w-7xl">
                <div className="text-center mb-6">
                    <span className="text-sm font-medium text-primary tracking-widest uppercase">
                        Add value to every engagement
                    </span>
                </div>
                <div className="text-center mb-12">
                    <h2 className="text-4xl sm:text-5xl font-black mb-4 text-foreground">
                        Your AI-Powered <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-500 to-cyan-500">ISP Assistant</span>
                    </h2>
                </div>
                
                {/* Feature Tabs */}
                <div className="flex flex-wrap justify-center gap-4 mb-10">
                    {aiFeatures.map((feature, index) => (
                        <button
                            key={feature.id}
                            onClick={() => handleTabClick(index)}
                            className={cn(
                                "relative px-6 py-3 text-sm font-bold transition-all rounded-lg",
                                activeIndex === index
                                    ? "text-foreground"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            {feature.title}
                            {/* Progress bar under active tab */}
                            <div className="absolute bottom-0 left-0 right-0 h-1 bg-muted rounded-full overflow-hidden">
                                {activeIndex === index && (
                                    <div
                                        className="h-full bg-gradient-to-r from-red-500 via-orange-500 to-red-500 transition-all duration-50"
                                        style={{ width: `${progress}%` }}
                                    />
                                )}
                            </div>
                        </button>
                    ))}
                </div>
                
                {/* Feature Image */}
                <div className="relative max-w-6xl mx-auto">
                    <div className="absolute -inset-4 bg-gradient-to-r from-indigo-500/20 via-purple-500/20 to-cyan-500/20 blur-3xl opacity-40 -z-10" />
                    <div className="rounded-2xl border border-border bg-card/80 backdrop-blur-xl overflow-hidden shadow-2xl shadow-indigo-500/10">
                        <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-muted/50">
                            <div className="flex gap-1.5">
                                <div className="w-3 h-3 rounded-full bg-red-500/80" />
                                <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
                                <div className="w-3 h-3 rounded-full bg-green-500/80" />
                            </div>
                            <div className="flex-1 text-center">
                                <span className="text-xs text-muted-foreground font-medium">
                                    {currentFeature.title}
                                </span>
                            </div>
                        </div>
                        <div className="relative bg-slate-900/50">
                            {/* Show current image */}
                            <img
                                src={currentFeature.image}
                                alt={currentFeature.title}
                                className="w-full h-auto block"
                                onError={() => {
                                    console.error("Image failed to load:", currentFeature.image)
                                }}
                            />
                        </div>
                    </div>
                </div>
                
                {/* Debug: Show current index */}
                <div className="text-center mt-4 text-sm text-muted-foreground">
                    Showing: {activeIndex + 1} of 4 - {currentFeature.title}
                </div>
            </div>
        </section>
    )
}

export default function LandingPage() {
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
    const [productMenuOpen, setProductMenuOpen] = useState(false)
    const [solutionMenuOpen, setSolutionMenuOpen] = useState(false)
    const [resourceMenuOpen, setResourceMenuOpen] = useState(false)
    const [isScrolled, setIsScrolled] = useState(false)
    const { resolvedTheme } = useTheme()
    
    // Scroll detection
    useEffect(() => {
        const handleScroll = () => {
            setIsScrolled(window.scrollY > 50)
        }
        // Check initial scroll position
        handleScroll()
        window.addEventListener('scroll', handleScroll, { passive: true })
        return () => window.removeEventListener('scroll', handleScroll)
    }, [])
    
    // Hover delay refs
    const productTimeoutRef = useRef<NodeJS.Timeout | null>(null)
    const solutionTimeoutRef = useRef<NodeJS.Timeout | null>(null)
    const resourceTimeoutRef = useRef<NodeJS.Timeout | null>(null)
    const hoverDelay = 150 // milliseconds
    
    const handleProductEnter = () => {
        if (productTimeoutRef.current) clearTimeout(productTimeoutRef.current)
        productTimeoutRef.current = setTimeout(() => setProductMenuOpen(true), hoverDelay)
    }
    const handleProductLeave = () => {
        if (productTimeoutRef.current) clearTimeout(productTimeoutRef.current)
        setProductMenuOpen(false)
    }
    const handleSolutionEnter = () => {
        if (solutionTimeoutRef.current) clearTimeout(solutionTimeoutRef.current)
        solutionTimeoutRef.current = setTimeout(() => setSolutionMenuOpen(true), hoverDelay)
    }
    const handleSolutionLeave = () => {
        if (solutionTimeoutRef.current) clearTimeout(solutionTimeoutRef.current)
        setSolutionMenuOpen(false)
    }
    const handleResourceEnter = () => {
        if (resourceTimeoutRef.current) clearTimeout(resourceTimeoutRef.current)
        resourceTimeoutRef.current = setTimeout(() => setResourceMenuOpen(true), hoverDelay)
    }
    const handleResourceLeave = () => {
        if (resourceTimeoutRef.current) clearTimeout(resourceTimeoutRef.current)
        setResourceMenuOpen(false)
    }
    
    // Interactive galactic dome pattern
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const mouseRef = useRef({ x: 0, y: 0 })
    const starsRef = useRef<{ 
        x: number; y: number; baseX: number; baseY: number; 
        size: number; length: number; angle: number;
        opacity: number; twinkleSpeed: number; twinklePhase: number;
        orbitAngle: number; orbitRadius: number; orbitSpeed: number;
        color: string; connectionIndex: number;
    }[]>([])
    const timeRef = useRef(0)
    
    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas) return
        
        const ctx = canvas.getContext('2d')
        if (!ctx) return
        
        // Use different color intensities based on theme
        const isDark = resolvedTheme === 'dark'
        const colors = isDark ? [
            '79, 70, 229',    // indigo-600
            '99, 102, 241',   // indigo
            '129, 140, 248',  // indigo-400
            '139, 92, 246',   // violet
            '59, 130, 246',   // blue
            '100, 116, 139',  // slate
        ] : [
            '67, 56, 202',    // indigo-700 (darker for light mode)
            '79, 70, 229',    // indigo-600
            '99, 102, 241',   // indigo-500
            '124, 58, 237',   // violet-600
            '37, 99, 235',    // blue-600
            '71, 85, 105',    // slate-600
        ]
        
        // Adjust opacity multiplier for light mode
        const opacityMultiplier = isDark ? 1 : 2.5
        
        const resizeCanvas = () => {
            canvas.width = window.innerWidth
            canvas.height = window.innerHeight
            initStars()
        }
        
        const initStars = () => {
            starsRef.current = []
            const centerX = canvas.width / 2
            const centerY = canvas.height * 0.65
            const domeWidth = canvas.width * 1.2
            const domeHeight = canvas.height * 0.9
            
            // Create full-screen dome galaxy pattern
            for (let i = 0; i < 800; i++) {
                // Dome arc from left to right (PI to 2*PI is bottom half, 0 to PI is top half/dome)
                const angle = Math.random() * Math.PI
                const radiusFactor = Math.pow(Math.random(), 0.5)
                
                const baseX = centerX + Math.cos(angle) * radiusFactor * domeWidth * 0.5
                const baseY = centerY - Math.sin(angle) * radiusFactor * domeHeight * 0.6
                
                // Elongated streak angle pointing toward center
                const streakAngle = Math.atan2(centerY - baseY, centerX - baseX) + (Math.random() - 0.5) * 0.5
                
                starsRef.current.push({
                    x: baseX,
                    y: baseY,
                    baseX,
                    baseY,
                    size: 0.8 + Math.random() * 1.2,
                    length: 4 + Math.random() * 10,
                    angle: streakAngle,
                    opacity: (0.15 + Math.random() * 0.25) * opacityMultiplier,
                    twinkleSpeed: 0.01 + Math.random() * 0.02,
                    twinklePhase: Math.random() * Math.PI * 2,
                    orbitAngle: Math.random() * Math.PI * 2,
                    orbitRadius: 1 + Math.random() * 4,
                    orbitSpeed: 0.002 + Math.random() * 0.006,
                    color: colors[Math.floor(Math.random() * colors.length)],
                    connectionIndex: Math.random() > 0.6 ? Math.floor(Math.random() * 800) : -1
                })
            }
            
            // Add brighter accent points
            for (let i = 0; i < 20; i++) {
                const angle = Math.random() * Math.PI
                const radiusFactor = Math.random() * 0.7
                const baseX = centerX + Math.cos(angle) * radiusFactor * domeWidth * 0.4
                const baseY = centerY - Math.sin(angle) * radiusFactor * domeHeight * 0.5
                
                starsRef.current.push({
                    x: baseX,
                    y: baseY,
                    baseX,
                    baseY,
                    size: 2 + Math.random() * 1.5,
                    length: 0,
                    angle: 0,
                    opacity: (0.35 + Math.random() * 0.25) * opacityMultiplier,
                    twinkleSpeed: 0.015 + Math.random() * 0.02,
                    twinklePhase: Math.random() * Math.PI * 2,
                    orbitAngle: Math.random() * Math.PI * 2,
                    orbitRadius: 2 + Math.random() * 3,
                    orbitSpeed: 0.004 + Math.random() * 0.006,
                    color: '129, 140, 248',
                    connectionIndex: -1
                })
            }
        }
        
        const animate = () => {
            if (!ctx || !canvas) return
            
            timeRef.current += 1
            ctx.clearRect(0, 0, canvas.width, canvas.height)
            
            const mouseX = mouseRef.current.x
            const mouseY = mouseRef.current.y
            const interactionRadius = 150
            
            // First pass: draw connection lines
            ctx.lineWidth = 0.8
            starsRef.current.forEach((star, index) => {
                if (star.connectionIndex >= 0 && star.connectionIndex < starsRef.current.length && star.connectionIndex !== index) {
                    const target = starsRef.current[star.connectionIndex]
                    const dist = Math.sqrt(Math.pow(star.x - target.x, 2) + Math.pow(star.y - target.y, 2))
                    
                    if (dist < 250) {
                        const lineOpacity = (1 - dist / 250) * 0.15
                        ctx.beginPath()
                        ctx.moveTo(star.x, star.y)
                        ctx.lineTo(target.x, target.y)
                        ctx.strokeStyle = `rgba(99, 102, 241, ${lineOpacity})`
                        ctx.stroke()
                    }
                }
            })
            
            // Second pass: draw stars
            starsRef.current.forEach(star => {
                // Orbital movement around base position
                star.orbitAngle += star.orbitSpeed
                const orbitX = Math.cos(star.orbitAngle) * star.orbitRadius
                const orbitY = Math.sin(star.orbitAngle) * star.orbitRadius * 0.5
                
                // Calculate target position with orbit
                let targetX = star.baseX + orbitX
                let targetY = star.baseY + orbitY
                
                // Mouse interaction - push stars away
                const dx = mouseX - targetX
                const dy = mouseY - targetY
                const distance = Math.sqrt(dx * dx + dy * dy)
                
                if (distance < interactionRadius && distance > 0) {
                    const force = (interactionRadius - distance) / interactionRadius
                    const pushAngle = Math.atan2(dy, dx)
                    targetX -= Math.cos(pushAngle) * force * 50
                    targetY -= Math.sin(pushAngle) * force * 50
                }
                
                // Smooth movement to target
                star.x += (targetX - star.x) * 0.06
                star.y += (targetY - star.y) * 0.06
                
                // Twinkle effect
                const twinkle = Math.sin(timeRef.current * star.twinkleSpeed + star.twinklePhase)
                const twinkleOpacity = star.opacity * (0.7 + twinkle * 0.3)
                
                // Glow boost near mouse
                let glowBoost = 0
                if (distance < interactionRadius * 2) {
                    glowBoost = ((interactionRadius * 2 - distance) / (interactionRadius * 2)) * 0.3
                }
                
                const finalOpacity = Math.min(0.8, twinkleOpacity + glowBoost)
                
                // Draw elongated streak or dot
                if (star.length > 0) {
                    // Draw as elongated streak
                    const endX = star.x + Math.cos(star.angle) * star.length
                    const endY = star.y + Math.sin(star.angle) * star.length
                    
                    const gradient = ctx.createLinearGradient(star.x, star.y, endX, endY)
                    gradient.addColorStop(0, `rgba(${star.color}, ${finalOpacity})`)
                    gradient.addColorStop(1, `rgba(${star.color}, 0)`)
                    
                    ctx.beginPath()
                    ctx.moveTo(star.x, star.y)
                    ctx.lineTo(endX, endY)
                    ctx.strokeStyle = gradient
                    ctx.lineWidth = star.size
                    ctx.lineCap = 'round'
                    ctx.stroke()
                } else {
                    // Draw as glowing dot
                    const gradient = ctx.createRadialGradient(star.x, star.y, 0, star.x, star.y, star.size * 5)
                    gradient.addColorStop(0, `rgba(${star.color}, ${finalOpacity})`)
                    gradient.addColorStop(0.4, `rgba(${star.color}, ${finalOpacity * 0.4})`)
                    gradient.addColorStop(1, `rgba(${star.color}, 0)`)
                    ctx.beginPath()
                    ctx.arc(star.x, star.y, star.size * 5, 0, Math.PI * 2)
                    ctx.fillStyle = gradient
                    ctx.fill()
                }
            })
            
            requestAnimationFrame(animate)
        }
        
        const handleMouseMove = (e: MouseEvent) => {
            mouseRef.current = { x: e.clientX, y: e.clientY }
        }
        
        resizeCanvas()
        window.addEventListener('resize', resizeCanvas)
        window.addEventListener('mousemove', handleMouseMove)
        animate()
        
        return () => {
            window.removeEventListener('resize', resizeCanvas)
            window.removeEventListener('mousemove', handleMouseMove)
        }
    }, [resolvedTheme])
    
    // Typewriter effect state
    const [typedText1, setTypedText1] = useState("")
    const [typedText2, setTypedText2] = useState("")
    const [showCursor1, setShowCursor1] = useState(true)
    const [showCursor2, setShowCursor2] = useState(false)
    const [displayedWord, setDisplayedWord] = useState("")
    const [isTypingComplete, setIsTypingComplete] = useState(false)
    const [showRotatingCursor, setShowRotatingCursor] = useState(false)
    
    const baseText = "Unify Your Entire "
    const fullText2 = "On One Powerful Platform"
    
    useEffect(() => {
        let index = 0
        const fullText1 = baseText + "ISP"
        const typeInterval1 = setInterval(() => {
            if (index < fullText1.length) {
                setTypedText1(fullText1.slice(0, index + 1))
                index++
            } else {
                clearInterval(typeInterval1)
                setShowCursor1(false)
                setShowCursor2(true)
                // Start typing line 2
                let index2 = 0
                const typeInterval2 = setInterval(() => {
                    if (index2 < fullText2.length) {
                        setTypedText2(fullText2.slice(0, index2 + 1))
                        index2++
                    } else {
                        clearInterval(typeInterval2)
                        setShowCursor2(false)
                        setIsTypingComplete(true)
                    }
                }, 80)
            }
        }, 80)
        
        return () => clearInterval(typeInterval1)
    }, [])
    
    // Word rotation effect with typing animation after initial typing is complete
    useEffect(() => {
        if (!isTypingComplete) return
        
        // Set initial word when typing completes
        setDisplayedWord("ISP")
        setShowRotatingCursor(false)
        
        let wordIndex = 0
        let currentDisplayedWord = "ISP"
        
        const rotateAndType = () => {
            wordIndex = (wordIndex + 1) % rotatingWords.length
            const newWord = rotatingWords[wordIndex]
            setShowRotatingCursor(true)
            
            // Delete current word first
            let deleteIndex = currentDisplayedWord.length
            const deleteInterval = setInterval(() => {
                if (deleteIndex > 0) {
                    deleteIndex--
                    setDisplayedWord(currentDisplayedWord.slice(0, deleteIndex))
                } else {
                    clearInterval(deleteInterval)
                    // Now type the new word
                    let typeIndex = 0
                    const typeInterval = setInterval(() => {
                        if (typeIndex < newWord.length) {
                            typeIndex++
                            setDisplayedWord(newWord.slice(0, typeIndex))
                        } else {
                            clearInterval(typeInterval)
                            currentDisplayedWord = newWord
                            setShowRotatingCursor(false)
                        }
                    }, 80)
                }
            }, 50)
        }
        
        const rotateInterval = setInterval(rotateAndType, 3000)
        
        return () => clearInterval(rotateInterval)
    }, [isTypingComplete])

    return (
        <div className="min-h-screen bg-background text-foreground selection:bg-indigo-500/30 overflow-x-hidden">
            {/* Interactive Dome Dot Pattern Background */}
            <canvas
                ref={canvasRef}
                className="fixed inset-0 z-0 pointer-events-none"
            />

            {/* Navigation */}
            <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/80 backdrop-blur-xl transition-all duration-300">
                <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
                    <div className="flex h-auto items-center justify-between py-3">
                        <div className="flex items-center gap-10">
                            <Link href="/" className="flex items-center gap-3 group">
                                <img src="/logo-new.svg" alt="OmniDome" className={cn(
                                    "transition-all duration-300 group-hover:scale-110",
                                    isScrolled ? "h-10 w-10" : "h-12 w-12"
                                )} />
                            </Link>

                            {/* Desktop Nav - Hidden when scrolled */}
                            <div className={cn(
                                "hidden lg:flex items-center gap-1 transition-all duration-300",
                                isScrolled ? "opacity-0 pointer-events-none max-w-0 overflow-hidden" : "opacity-100 max-w-none"
                            )}>
                                {/* Product - Mega Menu */}
                                <div
                                    className="relative"
                                    onMouseEnter={handleProductEnter}
                                    onMouseLeave={handleProductLeave}
                                >
                                    <ShineBorder borderRadius={8} color={["#6366f1", "#8b5cf6", "#06b6d4"]} duration={3}>
                                        <button className={cn(
                                            "text-sm font-medium transition-all px-4 py-2 rounded-lg",
                                            productMenuOpen 
                                                ? "text-foreground bg-primary/10" 
                                                : "text-muted-foreground hover:text-foreground"
                                        )}>
                                            Product
                                        </button>
                                    </ShineBorder>

                                    {/* Product Mega Menu */}
                                    <div className={cn(
                                        "fixed left-0 right-0 bg-card/95 backdrop-blur-2xl border border-border rounded-b-2xl shadow-[0_20px_50px_rgba(0,0,0,0.3)] transition-all duration-300 ease-out mega-menu-top",
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
                                                            <div className="font-bold text-sm text-foreground group-hover:text-primary transition-colors">
                                                                {mod.name}
                                                            </div>
                                                            <p className="text-[11px] text-muted-foreground line-clamp-2 mt-1 leading-relaxed group-hover:text-foreground/70 transition-colors">
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
                                                <ShineBorder borderRadius={8} color={["#6366f1", "#8b5cf6", "#06b6d4"]} duration={2}>
                                                    <Link href="/pricing">
                                                        <Button size="sm" className="bg-gradient-to-r from-indigo-600 to-blue-500 font-bold shadow-[0_0_20px_rgba(79,70,229,0.3)] text-white hover:shadow-[0_0_30px_rgba(79,70,229,0.5)] transition-all">
                                                            View Pricing <ArrowRight className="ml-2 h-4 w-4" />
                                                        </Button>
                                                    </Link>
                                                </ShineBorder>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Solution - Mega Menu */}
                                <div
                                    className="relative"
                                    onMouseEnter={handleSolutionEnter}
                                    onMouseLeave={handleSolutionLeave}
                                >
                                    <ShineBorder borderRadius={8} color={["#6366f1", "#8b5cf6", "#06b6d4"]} duration={3}>
                                        <button className={cn(
                                            "text-sm font-medium transition-all px-4 py-2 rounded-lg",
                                            solutionMenuOpen 
                                                ? "text-foreground bg-primary/10" 
                                                : "text-muted-foreground hover:text-foreground"
                                        )}>
                                            Solution
                                        </button>
                                    </ShineBorder>

                                    {/* Solution Mega Menu */}
                                    <div className={cn(
                                        "fixed left-0 right-0 bg-card/95 backdrop-blur-2xl border border-border rounded-b-2xl shadow-[0_20px_50px_rgba(0,0,0,0.3)] transition-all duration-300 ease-out mega-menu-top",
                                        solutionMenuOpen ? "opacity-100 translate-y-0 visible" : "opacity-0 -translate-y-2 invisible pointer-events-none"
                                    )}>
                                        <div className="max-w-7xl mx-auto px-8 py-10">
                                            <div className="grid grid-cols-5 gap-8">
                                                {Object.entries(solutionsByCategory).map(([category, solutions]) => (
                                                    <div key={category}>
                                                        <h3 className="text-[10px] font-bold text-primary uppercase tracking-[2px] mb-6">
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
                                                                        <div className="font-bold text-sm text-foreground group-hover:text-primary transition-colors">
                                                                            {sol.title}
                                                                        </div>
                                                                        <p className="text-[11px] text-muted-foreground mt-1 leading-snug group-hover:text-foreground/70 transition-colors">
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

                                {/* Resources - Mega Menu */}
                                <div
                                    className="relative"
                                    onMouseEnter={handleResourceEnter}
                                    onMouseLeave={handleResourceLeave}
                                >
                                    <ShineBorder borderRadius={8} color={["#6366f1", "#8b5cf6", "#06b6d4"]} duration={3}>
                                        <button className={cn(
                                            "text-sm font-medium transition-all px-4 py-2 rounded-lg",
                                            resourceMenuOpen 
                                                ? "text-foreground bg-primary/10" 
                                                : "text-muted-foreground hover:text-foreground"
                                        )}>
                                            Resources
                                        </button>
                                    </ShineBorder>

                                    {/* Resources Mega Menu */}
                                    <div className={cn(
                                        "fixed left-0 right-0 bg-card/95 backdrop-blur-2xl border border-border rounded-b-2xl shadow-[0_20px_50px_rgba(0,0,0,0.3)] transition-all duration-300 ease-out mega-menu-top",
                                        resourceMenuOpen ? "opacity-100 translate-y-0 visible" : "opacity-0 -translate-y-2 invisible pointer-events-none"
                                    )}>
                                        <div className="max-w-7xl mx-auto px-8 py-10">
                                            <div className="grid grid-cols-4 gap-10">
                                                {/* Featured Links */}
                                                <div>
                                                    <h3 className="text-xs font-bold text-primary uppercase tracking-[2px] mb-4">
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
                                                                    <span className="text-xs font-medium text-indigo-400 mt-1 inline-flex items-center gap-1 group-hover:gap-2 transition-all">
                                                                        Learn more <ArrowRight className="h-3 w-3" />
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
                                                                    <span className="text-xs font-medium text-indigo-400 mt-1 inline-flex items-center gap-1 group-hover:gap-2 transition-all">
                                                                        Learn more <ArrowRight className="h-3 w-3" />
                                                                    </span>
                                                                </div>
                                                            </Link>
                                                        ))}
                                                    </div>
                                                </div>

                                                {/* Support */}
                                                <div>
                                                    <h3 className="text-xs font-semibold text-indigo-400 uppercase tracking-[2px] font-bold">
                                                        Support
                                                    </h3>
                                                    <div className="space-y-4">
                                                        {resourceItems.support.map(item => (
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
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className="flex items-center gap-4">
                            {/* Price - Always visible */}
                            <ShineBorder borderRadius={8} color={["#6366f1", "#8b5cf6", "#06b6d4"]} duration={3} className="hidden lg:block">
                                <Link href="/pricing" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-all px-4 py-2 rounded-lg block">
                                    Price
                                </Link>
                            </ShineBorder>
                            <ThemeToggle className="hidden md:flex" />
                            <ShineBorder borderRadius={8} color={["#6366f1", "#8b5cf6", "#06b6d4"]} duration={3} className="hidden sm:block">
                                <Link href="/auth" className="block text-sm font-bold text-muted-foreground hover:text-foreground transition-colors px-3 py-1.5">
                                    Log in
                                </Link>
                            </ShineBorder>
                            <ShineBorder borderRadius={8} color={["#6366f1", "#8b5cf6", "#06b6d4"]} duration={2}>
                                <Link href="/auth">
                                    <Button size="sm" className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-6 shadow-[0_0_20px_rgba(79,70,229,0.3)] hover:shadow-[0_0_25px_rgba(79,70,229,0.5)] transition-all">
                                        Get Started
                                    </Button>
                                </Link>
                            </ShineBorder>
                            <button className="lg:hidden p-2 text-muted-foreground transition-colors hover:text-foreground" onClick={() => setMobileMenuOpen(!mobileMenuOpen)} title="Toggle menu">
                                {mobileMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
                            </button>
                        </div>
                    </div>
                </div>

                {/* Mobile menu */}
                {mobileMenuOpen && (
                    <div className="lg:hidden border-t border-border bg-card p-6 space-y-4">
                        <div className="flex items-center justify-between pb-4 border-b border-border">
                            <span className="text-sm text-muted-foreground">Theme</span>
                            <ThemeToggle />
                        </div>
                        <Link href="/pricing" className="block font-medium py-2">Pricing</Link>
                        <Link href="/resources/services" className="block font-medium py-2">Services</Link>
                        <Link href="/resources/partners" className="block font-medium py-2">Partners</Link>
                        <div className="border-t border-border pt-4 mt-4">
                            <Link href="/auth" className="block text-center mb-4 font-medium">Sign In</Link>
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
                    <style>{`
                        @keyframes shimmer {
                            0% {
                                background-position: -1000px 0;
                            }
                            100% {
                                background-position: 1000px 0;
                            }
                        }
                        .shimmer-text {
                            background: linear-gradient(90deg, #7d87ff, #a4b3ff, #7d87ff);
                            background-size: 1000px 100%;
                            -webkit-background-clip: text;
                            -webkit-text-fill-color: transparent;
                            background-clip: text;
                            animation: shimmer 3s infinite;
                        }
                        @keyframes blink {
                            0%, 50% { opacity: 1; }
                            51%, 100% { opacity: 0; }
                        }
                        .cursor-blink {
                            animation: blink 1s step-end infinite;
                        }
                        @keyframes fadeInUp {
                            0% { opacity: 0; transform: translateY(10px); }
                            100% { opacity: 1; transform: translateY(0); }
                        }
                        .rotating-word {
                            display: inline-block;
                            animation: fadeInUp 0.5s ease-out;
                            background: linear-gradient(90deg, #7d87ff, #54a2ff, #00d2ef);
                            -webkit-background-clip: text;
                            -webkit-text-fill-color: transparent;
                            background-clip: text;
                        }
                    `}</style>
                    <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-xs font-black tracking-[2px] uppercase mb-10 group">
                        <Sparkles className="h-3.5 w-3.5 animate-bounce text-indigo-400" />
                        <span className="shimmer-text">Next-Gen ISP Operating System</span>
                        <div className="absolute inset-x-0 bottom-0 h-[1px] bg-gradient-to-r from-transparent via-indigo-500 to-transparent" />
                    </div>

                    <h1 className="text-5xl lg:text-8xl font-black tracking-tight text-foreground mb-8 leading-[1]">
                        <span className="inline-block">
                            {isTypingComplete ? (
                                <>
                                    {baseText}
                                    <span className="bg-gradient-to-r from-indigo-500 via-blue-500 to-cyan-500 bg-clip-text text-transparent">{displayedWord}</span>
                                    {showRotatingCursor && <span className="cursor-blink text-cyan-500">|</span>}
                                </>
                            ) : (
                                <>
                                    {typedText1}
                                    {showCursor1 && <span className="cursor-blink text-indigo-500">|</span>}
                                </>
                            )}
                        </span>
                        <br />
                        <span className="inline-block bg-clip-text text-transparent bg-gradient-to-r from-indigo-500 via-blue-500 to-cyan-500">
                            {typedText2}
                            {showCursor2 && <span className="cursor-blink text-cyan-500">|</span>}
                        </span>
                    </h1>

                    <p className="mx-auto max-w-2xl text-lg lg:text-xl text-muted-foreground mb-12 leading-relaxed font-medium">
                        Stop juggling disconnected tools. Manage sales, fiber networks, billing, and support with an integrated OS built specifically for the South African ISP market.
                    </p>

                    <div className="flex flex-col sm:flex-row items-center justify-center gap-6 mb-16">
                        <ShineBorder borderRadius={12} color={["#6366f1", "#8b5cf6", "#06b6d4"]} duration={2}>
                            <Link href="/auth">
                                <Button size="lg" className="h-16 px-10 text-xl font-black bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_40px_rgba(79,70,229,0.4)] transition-all duration-300 group overflow-hidden relative active:scale-95">
                                    <span className="relative z-10 flex items-center gap-3">
                                        Start Your Free Trial <ArrowRight className="h-6 w-6 group-hover:translate-x-1.5 transition-transform" />
                                    </span>
                                    <div className="absolute inset-0 bg-gradient-to-r from-indigo-500 to-blue-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                                </Button>
                            </Link>
                        </ShineBorder>
                        <ShineBorder borderRadius={12} color={["#6366f1", "#8b5cf6", "#06b6d4"]} duration={3}>
                            <Button size="lg" variant="outline" className="h-16 px-10 text-xl font-bold border-border bg-muted/50 hover:bg-muted text-foreground backdrop-blur-md transition-all active:scale-95">
                                Schedule a Demo
                            </Button>
                        </ShineBorder>
                    </div>

                    {/* Dashboard Preview */}
                    <div className="relative max-w-6xl mx-auto mb-24">
                        <div className="absolute inset-0 bg-gradient-to-t from-background via-transparent to-transparent z-10 pointer-events-none" />
                        <div className="absolute -inset-4 bg-gradient-to-r from-indigo-500/20 via-blue-500/20 to-cyan-500/20 blur-3xl opacity-50 -z-10" />
                        <div className="rounded-2xl border border-border bg-card/80 backdrop-blur-xl overflow-hidden shadow-2xl shadow-indigo-500/10">
                            <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-muted/50">
                                <div className="flex gap-1.5">
                                    <div className="w-3 h-3 rounded-full bg-red-500/80" />
                                    <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
                                    <div className="w-3 h-3 rounded-full bg-green-500/80" />
                                </div>
                                <div className="flex-1 text-center">
                                    <span className="text-xs text-muted-foreground font-medium">OmniDome Dashboard</span>
                                </div>
                            </div>
                            <img 
                                src="/dashboard-preview.png" 
                                alt="OmniDome Dashboard Preview" 
                                className="w-full h-auto"
                            />
                        </div>
                    </div>

                    {/* Stats */}
                    <AnimatedStats />

                    {/* Bento Grid Section */}
                    <div className="mt-24 max-w-7xl mx-auto">
                        <div className="text-center mb-12">
                            <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-4">Everything You Need</h2>
                            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">Powerful features designed for South African ISPs</p>
                        </div>
                        <BentoGrid className="lg:grid-rows-4">
                            <BentoCard
                                name="Customer Records"
                                className="col-span-3 lg:col-span-1 lg:row-span-2"
                                background={
                                    <Marquee
                                        pauseOnHover
                                        className="absolute top-14 [mask-image:linear-gradient(to_top,transparent_30%,#000_100%)] [--duration:20s]"
                                    >
                                        {[
                                            { name: "contracts.pdf", body: "Service agreements and SLAs for fibre installations" },
                                            { name: "rica-docs.pdf", body: "RICA verification documents and ID confirmations" },
                                            { name: "invoices.xlsx", body: "Monthly billing records and payment history" },
                                            { name: "network.json", body: "Customer connection details and router configs" },
                                        ].map((f, idx) => (
                                            <figure
                                                key={idx}
                                                className={cn(
                                                    "relative w-32 cursor-pointer overflow-hidden rounded-xl border p-4",
                                                    "border-border bg-muted/50 hover:bg-muted",
                                                    "transform-gpu blur-[1px] transition-all duration-300 ease-out hover:blur-none"
                                                )}
                                            >
                                                <div className="flex flex-col">
                                                    <figcaption className="text-sm font-medium text-foreground">{f.name}</figcaption>
                                                </div>
                                                <blockquote className="mt-2 text-xs text-muted-foreground">{f.body}</blockquote>
                                            </figure>
                                        ))}
                                    </Marquee>
                                }
                                Icon={FileTextIcon}
                                description="Centralized document management with RICA compliance tracking."
                                href="/products/crm"
                                cta="Learn more"
                            />
                            <BentoCard
                                name="Real-Time Alerts"
                                className="col-span-3 lg:col-span-2 lg:row-span-2"
                                background={
                                    <AnimatedListDemo className="absolute inset-x-4 top-4 bottom-32 scale-100 border-none transition-all duration-300 ease-out group-hover:scale-[1.02]" />
                                }
                                Icon={BellIcon}
                                description="Instant notifications for payments, support tickets, and network events."
                                href="/products/overview"
                                cta="Learn more"
                            />
                            <BentoCard
                                name="Unified Integrations"
                                className="col-span-3 lg:col-span-2 lg:row-span-2"
                                background={
                                    <AnimatedBeamMultipleOutputDemo className="absolute inset-0 flex items-center justify-center border-none transition-all duration-300 ease-out group-hover:scale-105" />
                                }
                                Icon={Share2Icon}
                                description="Connect all your modules - CRM, Billing, Network, Support - in one hub."
                                href="/products/overview"
                                cta="Learn more"
                            />
                            <BentoCard
                                name="Smart Scheduling"
                                className="col-span-3 lg:col-span-1 lg:row-span-2"
                                background={
                                    <Calendar
                                        mode="single"
                                        selected={new Date(2026, 0, 24)}
                                        className="absolute top-6 left-1/2 -translate-x-1/2 origin-top scale-110 rounded-md border border-border bg-card transition-all duration-300 ease-out group-hover:scale-[1.15]"
                                    />
                                }
                                Icon={CalendarIcon}
                                description="Schedule installations, maintenance, and follow-ups effortlessly."
                                href="/products/support"
                                cta="Learn more"
                            />
                        </BentoGrid>

                        {/* Real-Time Activity Feed */}
                        <div className="mt-6 relative h-[300px] w-full max-w-2xl mx-auto rounded-2xl border border-border bg-card/50 overflow-hidden">
                            <AnimatedListDemo className="h-full" />
                            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-1/4 bg-gradient-to-t from-card"></div>
                        </div>
                    </div>

                    {/* Features Marquee */}
                    <div className="mt-24 relative flex w-full flex-col items-center justify-center overflow-hidden">
                        <Marquee pauseOnHover className="[--duration:40s]">
                            <Link href="/resources/why-omnidome#ai-insights" className="relative mx-4 w-80 rounded-2xl border border-border bg-card/80 p-6 hover:border-indigo-500/50 hover:scale-[1.02] transition-all cursor-pointer block overflow-hidden">
                                <EmojiPointer emoji="🧠" />
                                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 via-blue-500 to-cyan-400 flex items-center justify-center mb-4 shadow-[0_0_15px_rgba(79,70,229,0.3)]">
                                    <Brain className="h-6 w-6 text-white" />
                                </div>
                                <h3 className="text-xl font-semibold mb-2 text-foreground">AI-Powered Insights</h3>
                                <p className="text-muted-foreground text-sm">
                                    Predictive churn analytics, automated recommendations, and intelligent task creation.
                                </p>
                            </Link>

                            <Link href="/resources/why-omnidome#real-time" className="relative mx-4 w-80 rounded-2xl border border-border bg-card/80 p-6 hover:border-cyan-500/50 hover:scale-[1.02] transition-all cursor-pointer block overflow-hidden">
                                <EmojiPointer emoji="⚡" />
                                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center mb-4 shadow-[0_0_15px_rgba(6,182,212,0.3)]">
                                    <Zap className="h-6 w-6 text-white" />
                                </div>
                                <h3 className="text-xl font-semibold mb-2 text-foreground">Real-Time Operations</h3>
                                <p className="text-muted-foreground text-sm">
                                    Monitor network health, customer activity, and business metrics with live dashboards.
                                </p>
                            </Link>

                            <Link href="/resources/why-omnidome#analytics" className="relative mx-4 w-80 rounded-2xl border border-border bg-card/80 p-6 hover:border-purple-500/50 hover:scale-[1.02] transition-all cursor-pointer block overflow-hidden">
                                <EmojiPointer emoji="📊" />
                                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500 to-violet-500 flex items-center justify-center mb-4 shadow-[0_0_15px_rgba(139,92,246,0.3)]">
                                    <BarChart3 className="h-6 w-6 text-white" />
                                </div>
                                <h3 className="text-xl font-semibold mb-2 text-foreground">Unified Analytics</h3>
                                <p className="text-muted-foreground text-sm">
                                    Cross-module reporting, executive dashboards, and data-driven decision tools.
                                </p>
                            </Link>

                            <Link href="/resources/why-omnidome#retention" className="relative mx-4 w-80 rounded-2xl border border-border bg-card/80 p-6 hover:border-rose-500/50 hover:scale-[1.02] transition-all cursor-pointer block overflow-hidden">
                                <EmojiPointer emoji="❤️" />
                                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-rose-500 to-pink-500 flex items-center justify-center mb-4 shadow-[0_0_15px_rgba(244,63,94,0.3)]">
                                    <HeartHandshake className="h-6 w-6 text-white" />
                                </div>
                                <h3 className="text-xl font-semibold mb-2 text-foreground">Retention Focus</h3>
                                <p className="text-muted-foreground text-sm">
                                    Proactive churn prevention with AI risk scoring and automated retention campaigns.
                                </p>
                            </Link>

                            <Link href="/resources/why-omnidome#compliance" className="relative mx-4 w-80 rounded-2xl border border-border bg-card/80 p-6 hover:border-amber-500/50 hover:scale-[1.02] transition-all cursor-pointer block overflow-hidden">
                                <EmojiPointer emoji="🛡️" />
                                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center mb-4 shadow-[0_0_15px_rgba(245,158,11,0.3)]">
                                    <Shield className="h-6 w-6 text-white" />
                                </div>
                                <h3 className="text-xl font-semibold mb-2 text-foreground">SA Compliance Ready</h3>
                                <p className="text-muted-foreground text-sm">
                                    Built-in RICA verification, POPIA compliance, and South African regulatory requirements.
                                </p>
                            </Link>

                            <Link href="/resources/why-omnidome#portal" className="relative mx-4 w-80 rounded-2xl border border-border bg-card/80 p-6 hover:border-blue-500/50 hover:scale-[1.02] transition-all cursor-pointer block overflow-hidden">
                                <EmojiPointer emoji="🌍" />
                                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-blue-500 flex items-center justify-center mb-4 shadow-[0_0_15px_rgba(99,102,241,0.3)]">
                                    <Globe className="h-6 w-6 text-white" />
                                </div>
                                <h3 className="text-xl font-semibold mb-2 text-foreground">White-Label Portal</h3>
                                <p className="text-muted-foreground text-sm">
                                    Customizable customer portal with your branding for self-service and account management.
                                </p>
                            </Link>
                        </Marquee>
                        <div className="pointer-events-none absolute inset-y-0 left-0 w-1/4 bg-gradient-to-r from-background"></div>
                        <div className="pointer-events-none absolute inset-y-0 right-0 w-1/4 bg-gradient-to-l from-background"></div>
                    </div>

                    {/* Why Choose OmniDome Header */}
                    <div className="mt-24 text-center mb-12">
                        <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-4">Why Choose OmniDome?</h2>
                        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                            Purpose-built for ISPs with everything you need to scale your operations
                        </p>
                    </div>

                    {/* Second Bento Grid Section */}
                    <div className="max-w-7xl mx-auto">
                        <BentoGrid className="lg:grid-rows-2">
                            <BentoCard
                                name="AI Agent Chat"
                                className="col-span-3 lg:col-span-1 lg:row-span-1"
                                background={
                                    <AIChatDemo className="absolute inset-0 scale-100 border-none transition-all duration-300 ease-out group-hover:scale-[1.02]" />
                                }
                                Icon={MessageSquare}
                                description="Chat with Dome Agent to manage schedules, tasks, and customer queries."
                                href="/products/communication"
                                cta="Try AI Chat"
                            />
                            <BentoCard
                                name="AI Sales Pitch"
                                className="col-span-3 lg:col-span-2 lg:row-span-1"
                                background={
                                    <AIPitchDemo className="absolute inset-0" />
                                }
                                Icon={Sparkles}
                                description="Generate targeted sales pitches for every prospect in minutes with AI."
                                href="/products/sales"
                                cta="Generate pitch"
                            />
                            <BentoCard
                                name="Business Growth"
                                className="col-span-3 lg:col-span-2 lg:row-span-1"
                                background={
                                    <GrowthGraphDemo className="absolute inset-0" />
                                }
                                Icon={TrendingUp}
                                description="Track subscriber growth, revenue metrics, and business performance."
                                href="/products/sales"
                                cta="View analytics"
                            />
                            <BentoCard
                                name="Connected Systems"
                                className="col-span-3 lg:col-span-1 lg:row-span-1"
                                background={
                                    <OrbitingCirclesDemo2 className="absolute inset-0" />
                                }
                                Icon={Orbit}
                                description="Seamless integration between all your operational systems."
                                href="/products/network"
                                cta="Learn more"
                            />
                        </BentoGrid>
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
                        {modules.slice(0, 8).map((module, index) => (
                            <Link
                                key={module.id}
                                href={`/products/${module.slug}`}
                                className="group relative rounded-2xl border border-border bg-card p-6 hover:border-emerald-500/50 hover:shadow-lg hover:shadow-emerald-500/5 transition-all overflow-hidden"
                            >
                                <EmojiPointer emoji={moduleEmojis[index % moduleEmojis.length]} />
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

            {/* AI Features Showcase */}
            <AIFeaturesShowcase />

            {/* How It Works */}
            <HowItWorks />

            {/* CTA Section */}
            <section className="py-24 px-4 sm:px-6 lg:px-8 bg-gradient-to-br from-background via-muted to-primary/10 border-y border-border relative overflow-hidden">
                <div className="absolute inset-0 grid-pattern opacity-10" />
                <div className="mx-auto max-w-4xl text-center relative z-10">
                    <h2 className="text-4xl sm:text-6xl font-black mb-6 text-foreground leading-tight">
                        Ready to Transform Your <br />
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-500 to-cyan-500">ISP Operations?</span>
                    </h2>
                    <p className="text-xl text-muted-foreground mb-10 max-w-2xl mx-auto">
                        Join leading South African ISPs using OmniDome to streamline operations and grow revenue.
                    </p>
                    <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
                        <Link href="/auth">
                            <Button size="lg" className="bg-primary hover:bg-primary/90 text-primary-foreground text-xl font-black h-16 px-10 shadow-[0_0_30px_rgba(79,70,229,0.4)] transition-all">
                                Start Your Free Trial
                                <ArrowRight className="ml-3 h-6 w-6" />
                            </Button>
                        </Link>
                        <Button size="lg" variant="outline" className="border-border bg-muted/50 text-foreground hover:bg-muted text-xl font-bold h-16 px-10 backdrop-blur-md">
                            Schedule a Demo
                        </Button>
                    </div>
                </div>
            </section>



                        {/* Testimonials */}
                        <TestimonialsMarquee />


                        {/* FAQ Section */}
                        <FAQSection />

                        {/* Footer */}
            <footer className="border-t border-border py-16 px-4 sm:px-6 lg:px-8">
                <div className="mx-auto max-w-7xl">
                    <div className="grid grid-cols-2 md:grid-cols-6 gap-8 mb-12">
                        {/* Brand */}
                        <div className="col-span-2">
                            <div className="flex items-center gap-3 mb-4">
                                <img src="/logo-new.svg" alt="OmniDome" className="h-10 w-10" />
                                <div>
                                  <span className="font-bold text-foreground text-lg">OmniDome</span>
                                </div>
                            </div>
                            <p className="text-sm text-muted-foreground max-w-xs mb-6">
                                The complete ISP operating system for South African service providers.
                            </p>
                            <div className="flex gap-4">
                                <a href="#" className="text-muted-foreground hover:text-foreground transition-colors">
                                    <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M24 4.557c-.883.392-1.832.656-2.828.775 1.017-.609 1.798-1.574 2.165-2.724-.951.564-2.005.974-3.127 1.195-.897-.957-2.178-1.555-3.594-1.555-3.179 0-5.515 2.966-4.797 6.045-4.091-.205-7.719-2.165-10.148-5.144-1.29 2.213-.669 5.108 1.523 6.574-.806-.026-1.566-.247-2.229-.616-.054 2.281 1.581 4.415 3.949 4.89-.693.188-1.452.232-2.224.084.626 1.956 2.444 3.379 4.6 3.419-2.07 1.623-4.678 2.348-7.29 2.04 2.179 1.397 4.768 2.212 7.548 2.212 9.142 0 14.307-7.721 13.995-14.646.962-.695 1.797-1.562 2.457-2.549z"/></svg>
                                </a>
                                <a href="#" className="text-muted-foreground hover:text-foreground transition-colors">
                                    <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/></svg>
                                </a>
                                <a href="#" className="text-muted-foreground hover:text-foreground transition-colors">
                                    <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
                                </a>
                            </div>
                        </div>

                        {/* Products */}
                        <div>
                            <h4 className="font-semibold mb-4 text-foreground">Products</h4>
                            <ul className="space-y-2 text-sm text-muted-foreground">
                                {modules.map(mod => (
                                    <li key={mod.id}>
                                        <Link href={`/products/${mod.slug}`} className="hover:text-foreground transition-colors">
                                            {mod.name.replace(' Dome', '')}
                                        </Link>
                                    </li>
                                ))}
                                <li><Link href="/pricing" className="hover:text-foreground transition-colors font-medium text-primary">View Pricing</Link></li>
                            </ul>
                        </div>

                        {/* Solutions */}
                        <div>
                            <h4 className="font-semibold mb-4 text-foreground">Solutions</h4>
                            <ul className="space-y-2 text-sm text-muted-foreground">
                                {Object.entries(solutionsByCategory).flatMap(([, solutions]) => 
                                    solutions.map(sol => (
                                        <li key={sol.slug}>
                                            <Link href={`/solutions/${sol.slug}`} className="hover:text-foreground transition-colors">
                                                {sol.title}
                                            </Link>
                                        </li>
                                    ))
                                )}
                            </ul>
                        </div>

                        {/* Resources */}
                        <div>
                            <h4 className="font-semibold mb-4 text-foreground">Resources</h4>
                            <ul className="space-y-2 text-sm text-muted-foreground">
                                <li><Link href="/resources/why-omnidome" className="hover:text-foreground transition-colors">Why OmniDome</Link></li>
                                <li><Link href="/blog" className="hover:text-foreground transition-colors">Blog</Link></li>
                                <li><Link href="/resources/services" className="hover:text-foreground transition-colors">Services</Link></li>
                                <li><Link href="/resources/partners" className="hover:text-foreground transition-colors">Partners</Link></li>
                                <li><Link href="/docs" className="hover:text-foreground transition-colors">Documentation</Link></li>
                                <li><Link href="/developers" className="hover:text-foreground transition-colors">Developer Portal</Link></li>
                                <li><Link href="/support" className="hover:text-foreground transition-colors">Support Center</Link></li>
                            </ul>
                        </div>

                        {/* Company */}
                        <div>
                            <h4 className="font-semibold mb-4 text-foreground">Company</h4>
                            <ul className="space-y-2 text-sm text-muted-foreground">
                                <li><a href="#" className="hover:text-foreground transition-colors">About Us</a></li>
                                <li><a href="#" className="hover:text-foreground transition-colors">Careers</a></li>
                                <li><a href="#" className="hover:text-foreground transition-colors">Contact</a></li>
                                <li><a href="#" className="hover:text-foreground transition-colors">Press</a></li>
                            </ul>
                            <h4 className="font-semibold mb-4 mt-6 text-foreground">Legal</h4>
                            <ul className="space-y-2 text-sm text-muted-foreground">
                                <li><a href="/privacy-policy" className="hover:text-foreground transition-colors">Privacy Policy</a></li>
                                <li><a href="/terms-of-service" className="hover:text-foreground transition-colors">Terms of Service</a></li>
                                <li><a href="/popia-compliance" className="hover:text-foreground transition-colors">POPIA Compliance</a></li>
                            </ul>
                        </div>
                    </div>
                    <div className="border-t border-border pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
                        <p className="text-sm text-muted-foreground">
                            © 2026 OmniDome. All rights reserved. Built for South African ISPs.
                        </p>
                        <div className="flex items-center gap-6 text-sm text-muted-foreground">
                            <span className="flex items-center gap-2">
                                <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                                All systems operational
                            </span>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    )
}
