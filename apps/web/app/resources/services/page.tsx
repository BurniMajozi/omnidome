"use client"

import Link from "next/link"
import { ArrowLeft, ArrowRight, Check, Sparkles, Users, Zap, Shield, Clock, Wifi } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const services = [
    {
        id: "onboarding",
        name: "Onboarding",
        description: "Get up and running with OmniDome quickly and efficiently with our expert-led onboarding programs.",
        heroText: "Maximize the Power of OmniDome",
        heroSubtext: "With OmniDome Services, you grow with the guidance that fits your needs and safeguard against blind spots. We align our product, technical, and strategic expertise to your goals so that you get the most out of OmniDome.",
        tiers: [
            {
                name: "Professional",
                price: "R 15,000",
                setting: "Remote",
                features: [
                    { name: "How your data lives in OmniDome", included: true },
                    { name: "Lead capture and conversion paths", included: true },
                    { name: "Segmenting your data", included: true },
                    { name: "Network monitoring setup", included: true },
                    { name: "Baseline reporting setup and review", included: true },
                    { name: "Onboarding your team (invite, permissions, and resources)", included: true },
                    { name: "Standard automation setup", included: true },
                    { name: "Turning on standard integrations", included: true },
                    { name: "Consulting to migrate/import data from your CRM", included: false },
                    { name: "Routing and managing multiple teams", included: false },
                ]
            },
            {
                name: "Enterprise",
                price: "R 35,000",
                setting: "Remote",
                features: [
                    { name: "How your data lives in OmniDome", included: true },
                    { name: "Lead capture and conversion paths", included: true },
                    { name: "Segmenting your data", included: true },
                    { name: "Network monitoring setup", included: true },
                    { name: "Baseline reporting setup and review", included: true, note: "Custom report setup and review" },
                    { name: "Onboarding your team (invite, permissions, and resources)", included: true },
                    { name: "Standard automation setup", included: true },
                    { name: "Turning on standard integrations", included: true },
                    { name: "Consulting to migrate/import data from your CRM", included: true },
                    { name: "Routing and managing multiple teams", included: true },
                ]
            }
        ]
    },
    {
        id: "training",
        name: "Customer Training",
        description: "Comprehensive training programs to ensure your team masters OmniDome's full capabilities.",
        heroText: "Empower Your Team with Expert Training",
        heroSubtext: "Our certified trainers will guide your team through every module, ensuring they can leverage OmniDome to its full potential.",
        tiers: [
            {
                name: "Standard",
                price: "R 8,000",
                setting: "Remote",
                features: [
                    { name: "Core platform navigation", included: true },
                    { name: "Module-specific training (up to 3 modules)", included: true },
                    { name: "Best practices workshops", included: true },
                    { name: "Q&A sessions", included: true },
                    { name: "Recorded sessions for replay", included: true },
                    { name: "Advanced automation training", included: false },
                    { name: "Custom workflow development", included: false },
                    { name: "On-site training", included: false },
                ]
            },
            {
                name: "Premium",
                price: "R 18,000",
                setting: "On-site/Remote",
                features: [
                    { name: "Core platform navigation", included: true },
                    { name: "Module-specific training (all modules)", included: true },
                    { name: "Best practices workshops", included: true },
                    { name: "Q&A sessions", included: true },
                    { name: "Recorded sessions for replay", included: true },
                    { name: "Advanced automation training", included: true },
                    { name: "Custom workflow development", included: true },
                    { name: "On-site training (2 days)", included: true },
                ]
            }
        ]
    },
    {
        id: "migration",
        name: "Migration Services",
        description: "Seamless data migration from your existing systems to OmniDome with zero downtime.",
        heroText: "Migrate Without Missing a Beat",
        heroSubtext: "Our migration experts handle the heavy lifting, ensuring your data, workflows, and integrations transfer smoothly to OmniDome.",
        tiers: [
            {
                name: "Standard",
                price: "R 12,000",
                setting: "Remote",
                features: [
                    { name: "Data audit and mapping", included: true },
                    { name: "Customer data migration", included: true },
                    { name: "Basic workflow recreation", included: true },
                    { name: "Post-migration validation", included: true },
                    { name: "2 weeks of support", included: true },
                    { name: "Historical ticket migration", included: false },
                    { name: "Complex automation migration", included: false },
                    { name: "Custom integration setup", included: false },
                ]
            },
            {
                name: "Complete",
                price: "R 28,000",
                setting: "Remote + On-site",
                features: [
                    { name: "Data audit and mapping", included: true },
                    { name: "Customer data migration", included: true },
                    { name: "Basic workflow recreation", included: true },
                    { name: "Post-migration validation", included: true },
                    { name: "4 weeks of support", included: true },
                    { name: "Historical ticket migration", included: true },
                    { name: "Complex automation migration", included: true },
                    { name: "Custom integration setup", included: true },
                ]
            }
        ]
    }
]

export default function ServicesPage() {
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
                                    Request more information
                                </Button>
                            </Link>
                        </div>
                    </div>
                </div>
            </nav>

            {/* Hero */}
            <section className="relative bg-gradient-to-br from-emerald-900 via-teal-900 to-cyan-900 text-white py-24 px-4 overflow-hidden">
                <div className="absolute inset-0 bg-[url('data:image/svg+xml,...')] opacity-10" />
                <div className="max-w-4xl mx-auto text-center relative z-10">
                    <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold mb-6">OmniDome Services</h1>
                    <p className="text-xl text-white/80 mb-10">Helping you grow better, together.</p>
                    <Link href="#services">
                        <Button size="lg" className="bg-emerald-500 hover:bg-emerald-600 text-white text-lg px-8">
                            Request more information
                        </Button>
                    </Link>
                </div>
            </section>

            {/* Tabs */}
            <div className="border-b border-border sticky top-16 bg-background z-40">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex gap-8">
                        <span className="py-4 text-sm font-medium border-b-2 border-emerald-500 text-emerald-500">
                            OmniDome Services
                        </span>
                        {services.map(s => (
                            <a key={s.id} href={`#${s.id}`} className="py-4 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
                                {s.name}
                            </a>
                        ))}
                    </div>
                </div>
            </div>

            {/* Intro */}
            <section className="py-20 px-4" id="services">
                <div className="max-w-4xl mx-auto text-center">
                    <h2 className="text-3xl sm:text-4xl font-bold mb-6">Maximize the Power of OmniDome</h2>
                    <p className="text-lg text-muted-foreground">
                        With OmniDome Services, you grow with the guidance that fits your needs and safeguard against blind spots.
                        We align our product, technical, and strategic expertise to your goals so that you get the most out of OmniDome.
                    </p>
                </div>
            </section>

            {/* Services */}
            {services.map((service, idx) => (
                <section key={service.id} id={service.id} className={cn("py-20 px-4", idx % 2 === 1 && "bg-card/50")}>
                    <div className="max-w-6xl mx-auto">
                        <div className="text-center mb-12">
                            <h2 className="text-3xl font-bold mb-4">{service.name}</h2>
                            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">{service.description}</p>
                        </div>

                        <div className="mb-8">
                            <h3 className="text-xl font-semibold text-center mb-8">
                                During {service.name}, you may receive guidance on the following:
                            </h3>
                        </div>

                        {/* Comparison Table */}
                        <div className="border border-border rounded-xl overflow-hidden bg-card">
                            <table className="w-full">
                                <thead>
                                    <tr className="border-b border-border">
                                        <th className="text-left p-4 font-medium text-muted-foreground w-1/2"></th>
                                        {service.tiers.map(tier => (
                                            <th key={tier.name} className="p-4 text-center font-semibold uppercase tracking-wider text-sm">
                                                {tier.name}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {service.tiers[0].features.map((feat, fIdx) => (
                                        <tr key={fIdx} className="border-b border-border last:border-0">
                                            <td className="p-4 text-sm">{feat.name}</td>
                                            {service.tiers.map(tier => {
                                                const tierFeat = tier.features[fIdx]
                                                return (
                                                    <td key={tier.name} className="p-4 text-center">
                                                        {tierFeat.included ? (
                                                            <div className="flex flex-col items-center">
                                                                <Check className="h-5 w-5 text-emerald-500" />
                                                                {tierFeat.note && <span className="text-xs text-muted-foreground mt-1">{tierFeat.note}</span>}
                                                            </div>
                                                        ) : (
                                                            <span className="text-muted-foreground">—</span>
                                                        )}
                                                    </td>
                                                )
                                            })}
                                        </tr>
                                    ))}
                                    <tr className="bg-secondary/50">
                                        <td className="p-4 font-semibold">Key Details</td>
                                        {service.tiers.map(tier => (
                                            <td key={tier.name} className="p-4 text-center">
                                                <div className="font-bold text-lg">{tier.price}</div>
                                                <div className="text-sm text-muted-foreground">Setting: {tier.setting}</div>
                                                <a href="#" className="text-xs text-emerald-500 underline">Legal Description</a>
                                            </td>
                                        ))}
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </section>
            ))}

            {/* CTA */}
            <section className="py-24 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 text-white">
                <div className="max-w-4xl mx-auto text-center">
                    <h2 className="text-3xl sm:text-4xl font-bold mb-6">Ready to get started?</h2>
                    <p className="text-xl mb-10 opacity-90">Let our experts help you maximize your OmniDome investment.</p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Button size="lg" className="bg-white text-emerald-600 hover:bg-white/90 text-lg px-8 font-semibold">
                            Contact Sales
                        </Button>
                        <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10 text-lg px-8">
                            View Pricing
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
