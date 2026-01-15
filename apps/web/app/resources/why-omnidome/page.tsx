"use client"

import Link from "next/link"
import { ArrowLeft, ArrowRight, Check, Users, Zap, Shield, BarChart3, Globe, Brain, HeartHandshake, Wifi, Play } from "lucide-react"
import { Button } from "@/components/ui/button"

const reasons = [
    {
        icon: Brain,
        title: "AI-First Platform",
        description: "Unlike legacy ISP systems, OmniDome is built from the ground up with AI at its core. Predictive churn analytics, intelligent task routing, and automated recommendations aren't add-ons—they're fundamental."
    },
    {
        icon: Zap,
        title: "Purpose-Built for ISPs",
        description: "We understand the unique challenges of running an ISP in South Africa. From RICA compliance to load shedding alerts, every feature is designed with your reality in mind."
    },
    {
        icon: BarChart3,
        title: "Unified Data Model",
        description: "No more siloed systems. Customer data, network metrics, billing, and support all live in one unified platform, giving you a true 360° view of your business."
    },
    {
        icon: HeartHandshake,
        title: "Customer Retention Focus",
        description: "With our 87% accurate churn prediction, you'll identify at-risk customers before they leave. Automated win-back campaigns and loyalty programs are built right in."
    },
    {
        icon: Shield,
        title: "SA Compliance Ready",
        description: "RICA, POPIA, and ICASA requirements are baked into the platform. Audit trails, consent management, and regulatory reporting come standard."
    },
    {
        icon: Globe,
        title: "White-Label Everything",
        description: "Your brand, your portal. Give customers a premium self-service experience with your colors, logo, and domain. No OmniDome branding in sight."
    }
]

const stats = [
    { value: "87%", label: "Churn Prediction Accuracy" },
    { value: "14", label: "Integrated Modules" },
    { value: "99.9%", label: "Platform Uptime" },
    { value: "2hr", label: "Avg. Onboarding Time" }
]

const testimonials = [
    {
        quote: "OmniDome transformed how we operate. We reduced churn by 34% in the first quarter alone.",
        author: "Johan van der Merwe",
        role: "CEO, FibreConnect SA",
        avatar: "https://i.pravatar.cc/100?u=1"
    },
    {
        quote: "The network monitoring alone is worth the investment. We catch issues before customers even notice.",
        author: "Thandi Nkosi",
        role: "Operations Director, MetroFibre",
        avatar: "https://i.pravatar.cc/100?u=2"
    },
    {
        quote: "Finally, a platform that understands South African ISPs. RICA compliance used to be a nightmare.",
        author: "David Chen",
        role: "Compliance Officer, SpeedNet",
        avatar: "https://i.pravatar.cc/100?u=3"
    }
]

export default function WhyOmniDomePage() {
    return (
        <div className="min-h-screen bg-background">
            {/* Nav */}
            <nav className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur-xl">
                <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
                    <div className="flex h-16 items-center justify-between">
                        <Link href="/" className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-emerald-500 transition-colors">
                            <ArrowLeft className="h-4 w-4" /> Back to Home
                        </Link>
                        <div className="flex items-center gap-4">
                            <Link href="/dashboard">
                                <Button size="sm" className="bg-gradient-to-r from-emerald-500 to-teal-500 text-white">
                                    Start Free Trial
                                </Button>
                            </Link>
                        </div>
                    </div>
                </div>
            </nav>

            {/* Hero */}
            <section className="relative py-24 px-4 overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/5 via-transparent to-teal-500/5" />
                <div className="max-w-4xl mx-auto text-center relative z-10">
                    <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold mb-6">
                        Why Choose{" "}
                        <span className="bg-gradient-to-r from-emerald-500 to-teal-500 bg-clip-text text-transparent">
                            OmniDome
                        </span>
                        ?
                    </h1>
                    <p className="text-xl text-muted-foreground mb-10 max-w-2xl mx-auto">
                        The complete ISP operating system, built specifically for South African service providers who demand more from their technology.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Button size="lg" className="bg-gradient-to-r from-emerald-500 to-teal-500 text-white text-lg px-8">
                            Get Started Free
                            <ArrowRight className="ml-2 h-5 w-5" />
                        </Button>
                        <Button size="lg" variant="outline" className="text-lg px-8 gap-2">
                            <Play className="h-5 w-5" />
                            Watch Demo
                        </Button>
                    </div>
                </div>
            </section>

            {/* Stats */}
            <section className="py-16 px-4 bg-card border-y border-border">
                <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8">
                    {stats.map((stat) => (
                        <div key={stat.label} className="text-center">
                            <div className="text-4xl sm:text-5xl font-bold text-emerald-500 mb-2">{stat.value}</div>
                            <div className="text-sm text-muted-foreground">{stat.label}</div>
                        </div>
                    ))}
                </div>
            </section>

            {/* Reasons */}
            <section className="py-24 px-4">
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-16">
                        <h2 className="text-3xl sm:text-4xl font-bold mb-4">Built Different. Built Better.</h2>
                        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                            Here's what sets OmniDome apart from generic CRM and network tools.
                        </p>
                    </div>

                    <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
                        {reasons.map((reason) => (
                            <div key={reason.title} className="border border-border rounded-2xl bg-card p-8 hover:border-emerald-500/50 transition-colors">
                                <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500 flex items-center justify-center mb-6">
                                    <reason.icon className="h-7 w-7 text-white" />
                                </div>
                                <h3 className="text-xl font-semibold mb-3">{reason.title}</h3>
                                <p className="text-muted-foreground">{reason.description}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Comparison */}
            <section className="py-24 px-4 bg-card/50">
                <div className="max-w-5xl mx-auto">
                    <div className="text-center mb-16">
                        <h2 className="text-3xl sm:text-4xl font-bold mb-4">OmniDome vs. The Rest</h2>
                        <p className="text-lg text-muted-foreground">See how we stack up against traditional solutions.</p>
                    </div>

                    <div className="border border-border rounded-2xl bg-card overflow-hidden">
                        <table className="w-full">
                            <thead>
                                <tr className="border-b border-border">
                                    <th className="text-left p-5 font-medium text-muted-foreground">Feature</th>
                                    <th className="p-5 text-center font-semibold bg-emerald-500/10">
                                        <span className="text-emerald-500">OmniDome</span>
                                    </th>
                                    <th className="p-5 text-center font-medium text-muted-foreground">Generic CRM</th>
                                    <th className="p-5 text-center font-medium text-muted-foreground">Legacy ISP Tools</th>
                                </tr>
                            </thead>
                            <tbody>
                                {[
                                    { feature: "AI Churn Prediction", omni: true, generic: false, legacy: false },
                                    { feature: "Network Monitoring", omni: true, generic: false, legacy: true },
                                    { feature: "RICA Compliance", omni: true, generic: false, legacy: "Partial" },
                                    { feature: "Unified Platform", omni: true, generic: false, legacy: false },
                                    { feature: "White-Label Portal", omni: true, generic: "Paid Add-on", legacy: false },
                                    { feature: "Real-time Dashboards", omni: true, generic: true, legacy: false },
                                    { feature: "Built for SA Market", omni: true, generic: false, legacy: "Limited" },
                                ].map((row, idx) => (
                                    <tr key={idx} className="border-b border-border last:border-0">
                                        <td className="p-5 font-medium">{row.feature}</td>
                                        <td className="p-5 text-center bg-emerald-500/5">
                                            {row.omni === true ? <Check className="h-5 w-5 text-emerald-500 mx-auto" /> : row.omni}
                                        </td>
                                        <td className="p-5 text-center">
                                            {row.generic === true ? <Check className="h-5 w-5 text-muted-foreground mx-auto" /> :
                                                row.generic === false ? <span className="text-muted-foreground">—</span> :
                                                    <span className="text-xs text-muted-foreground">{row.generic}</span>}
                                        </td>
                                        <td className="p-5 text-center">
                                            {row.legacy === true ? <Check className="h-5 w-5 text-muted-foreground mx-auto" /> :
                                                row.legacy === false ? <span className="text-muted-foreground">—</span> :
                                                    <span className="text-xs text-muted-foreground">{row.legacy}</span>}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </section>

            {/* Testimonials */}
            <section className="py-24 px-4">
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-16">
                        <h2 className="text-3xl sm:text-4xl font-bold mb-4">Trusted by Leading ISPs</h2>
                        <p className="text-lg text-muted-foreground">Hear from operators who made the switch.</p>
                    </div>

                    <div className="grid md:grid-cols-3 gap-8">
                        {testimonials.map((testimonial, idx) => (
                            <div key={idx} className="border border-border rounded-2xl bg-card p-8">
                                <p className="text-lg mb-6 italic">"{testimonial.quote}"</p>
                                <div className="flex items-center gap-4">
                                    <img src={testimonial.avatar} alt={testimonial.author} className="w-12 h-12 rounded-full" />
                                    <div>
                                        <div className="font-semibold">{testimonial.author}</div>
                                        <div className="text-sm text-muted-foreground">{testimonial.role}</div>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section className="py-24 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 text-white">
                <div className="max-w-4xl mx-auto text-center">
                    <h2 className="text-3xl sm:text-4xl font-bold mb-6">Ready to Transform Your ISP?</h2>
                    <p className="text-xl mb-10 opacity-90">Start your 14-day free trial today. No credit card required.</p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Link href="/dashboard">
                            <Button size="lg" className="bg-white text-emerald-600 hover:bg-white/90 text-lg px-8 font-semibold">
                                Start Free Trial
                                <ArrowRight className="ml-2 h-5 w-5" />
                            </Button>
                        </Link>
                        <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10 text-lg px-8">
                            Schedule a Demo
                        </Button>
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
