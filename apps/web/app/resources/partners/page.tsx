"use client"

import Link from "next/link"
import { ArrowLeft, ArrowRight, Check, Users, Building2, Zap, Globe, Award, Wifi, Star } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const partnerPrograms = [
    {
        id: "reseller",
        name: "Reseller Partner",
        description: "Resell OmniDome to your customers with attractive margins and full support.",
        icon: Building2,
        price: "R 5,000",
        priceNote: "Annual Partner Fee",
        commission: "20-35%",
        benefits: [
            "Up to 35% revenue share on referred customers",
            "Partner portal access for deal registration",
            "Co-branded marketing materials",
            "Dedicated partner manager",
            "Priority support queue",
            "Quarterly business reviews",
            "Partner certification program"
        ],
        requirements: [
            "Minimum 5 customer referrals per year",
            "Complete partner certification",
            "Maintain customer satisfaction score"
        ]
    },
    {
        id: "integration",
        name: "Integration Partner",
        description: "Build integrations and apps that extend OmniDome's capabilities.",
        icon: Zap,
        price: "R 8,000",
        priceNote: "Annual Partner Fee",
        commission: "15-25%",
        benefits: [
            "API access and sandbox environment",
            "Integration marketplace listing",
            "Co-marketing opportunities",
            "Technical documentation and support",
            "Revenue share on marketplace sales",
            "Early access to new features",
            "Developer community access"
        ],
        requirements: [
            "Publish at least 1 integration annually",
            "Maintain integration quality standards",
            "Provide customer support for integrations"
        ]
    },
    {
        id: "solutions",
        name: "Solutions Partner",
        description: "Deliver implementation, consulting, and custom development services.",
        icon: Globe,
        price: "R 15,000",
        priceNote: "Annual Partner Fee",
        commission: "25-40%",
        benefits: [
            "Highest revenue share tier (up to 40%)",
            "Implementation services referrals",
            "Joint go-to-market programs",
            "Executive sponsorship",
            "Training and certification programs",
            "Annual partner summit invitation",
            "Case study co-creation",
            "Lead sharing program"
        ],
        requirements: [
            "Certified implementation team (min 3 people)",
            "Minimum R500K in annual referred revenue",
            "Complete all certification tracks"
        ]
    }
]

const certifications = [
    {
        name: "OmniDome Core Certification",
        price: "R 2,500",
        duration: "Self-paced (8 hours)",
        description: "Master the fundamentals of OmniDome platform."
    },
    {
        name: "Sales Hub Specialist",
        price: "R 3,500",
        duration: "2-day workshop",
        description: "Deep dive into Sales Hub implementation and optimization."
    },
    {
        name: "Network Ops Expert",
        price: "R 4,500",
        duration: "3-day workshop",
        description: "Advanced training for network monitoring and operations."
    },
    {
        name: "Implementation Architect",
        price: "R 8,000",
        duration: "1-week intensive",
        description: "Full platform implementation and architecture certification."
    }
]

export default function PartnersPage() {
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
                                    Apply to Partner Program
                                </Button>
                            </Link>
                        </div>
                    </div>
                </div>
            </nav>

            {/* Hero */}
            <section className="relative bg-gradient-to-br from-violet-900 via-purple-900 to-indigo-900 text-white py-24 px-4 overflow-hidden">
                <div className="max-w-4xl mx-auto text-center relative z-10">
                    <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-1.5 text-sm mb-6">
                        <Award className="h-4 w-4" />
                        <span>Partner Program</span>
                    </div>
                    <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold mb-6">Grow Together with OmniDome</h1>
                    <p className="text-xl text-white/80 mb-10 max-w-2xl mx-auto">
                        Join our partner ecosystem and unlock new revenue streams while helping ISPs transform their operations.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Button size="lg" className="bg-white text-purple-600 hover:bg-white/90 text-lg px-8 font-semibold">
                            Apply Now
                        </Button>
                        <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10 text-lg px-8">
                            Download Partner Guide
                        </Button>
                    </div>
                </div>
            </section>

            {/* Partner Programs */}
            <section className="py-20 px-4">
                <div className="max-w-7xl mx-auto">
                    <div className="text-center mb-16">
                        <h2 className="text-3xl sm:text-4xl font-bold mb-4">Partner Programs</h2>
                        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                            Choose the partnership model that fits your business.
                        </p>
                    </div>

                    <div className="grid md:grid-cols-3 gap-8">
                        {partnerPrograms.map((program) => (
                            <div key={program.id} className="border border-border rounded-2xl bg-card overflow-hidden hover:border-emerald-500/50 transition-colors">
                                <div className="p-8">
                                    <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-violet-500 to-purple-500 flex items-center justify-center mb-6">
                                        <program.icon className="h-7 w-7 text-white" />
                                    </div>
                                    <h3 className="text-xl font-bold mb-2">{program.name}</h3>
                                    <p className="text-muted-foreground text-sm mb-6">{program.description}</p>

                                    <div className="border-t border-border pt-6 mb-6">
                                        <div className="flex justify-between items-center mb-4">
                                            <span className="text-sm text-muted-foreground">{program.priceNote}</span>
                                            <span className="text-2xl font-bold">{program.price}</span>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-sm text-muted-foreground">Commission Rate</span>
                                            <span className="text-lg font-semibold text-emerald-500">{program.commission}</span>
                                        </div>
                                    </div>

                                    <div className="mb-6">
                                        <h4 className="text-sm font-semibold mb-3">Benefits</h4>
                                        <ul className="space-y-2">
                                            {program.benefits.slice(0, 5).map((benefit, idx) => (
                                                <li key={idx} className="flex items-start gap-2 text-sm">
                                                    <Check className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                                                    <span>{benefit}</span>
                                                </li>
                                            ))}
                                            {program.benefits.length > 5 && (
                                                <li className="text-sm text-emerald-500">+{program.benefits.length - 5} more benefits</li>
                                            )}
                                        </ul>
                                    </div>

                                    <Button className="w-full bg-gradient-to-r from-violet-500 to-purple-500 text-white">
                                        Apply for {program.name}
                                    </Button>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Certifications */}
            <section className="py-20 px-4 bg-card/50">
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-16">
                        <h2 className="text-3xl sm:text-4xl font-bold mb-4">Partner Certifications</h2>
                        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                            Elevate your expertise with our certification programs.
                        </p>
                    </div>

                    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
                        {certifications.map((cert) => (
                            <div key={cert.name} className="border border-border rounded-xl bg-card p-6 hover:border-emerald-500/50 transition-colors">
                                <div className="flex items-center gap-2 mb-4">
                                    <Star className="h-5 w-5 text-amber-500" />
                                    <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Certification</span>
                                </div>
                                <h3 className="font-semibold mb-2">{cert.name}</h3>
                                <p className="text-sm text-muted-foreground mb-4">{cert.description}</p>
                                <div className="space-y-2 text-sm">
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Duration</span>
                                        <span>{cert.duration}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Price</span>
                                        <span className="font-semibold text-emerald-500">{cert.price}</span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section className="py-24 px-4">
                <div className="max-w-4xl mx-auto text-center">
                    <h2 className="text-3xl sm:text-4xl font-bold mb-6">Ready to Partner?</h2>
                    <p className="text-lg text-muted-foreground mb-10">
                        Join 50+ partners already growing with OmniDome.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Button size="lg" className="bg-gradient-to-r from-emerald-500 to-teal-500 text-white text-lg px-8">
                            Apply Now
                            <ArrowRight className="ml-2 h-5 w-5" />
                        </Button>
                        <Button size="lg" variant="outline" className="text-lg px-8">
                            Schedule a Call
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
