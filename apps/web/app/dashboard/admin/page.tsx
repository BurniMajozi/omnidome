"use client"

/**
 * Admin Console — /dashboard/admin
 *
 * Hub page for the Admin section. Links to Agent Manager, Workflows, and Audit.
 * This page prevents the 404 when navigating to /dashboard/admin directly.
 */

import Link from "next/link"
import { Bot, GitBranch, Shield, ArrowRight } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"

const adminSections = [
  {
    title: "Agent Manager",
    description: "View, configure, and monitor all AI agents — built-in and HR-deployed custom agents.",
    href: "/dashboard/admin/agents",
    icon: Bot,
    color: "text-cyan-400",
    bg: "from-cyan-500/10 to-blue-500/5",
  },
  {
    title: "Workflows",
    description: "Design, edit, and monitor automated multi-step agent workflows and event triggers.",
    href: "/dashboard/admin/workflows",
    icon: GitBranch,
    color: "text-emerald-400",
    bg: "from-emerald-500/10 to-teal-500/5",
  },
  {
    title: "Audit & Compliance",
    description: "Review agent actions, tool usage logs, guardrail verdicts, and approval history.",
    href: "/dashboard/admin/agents",
    icon: Shield,
    color: "text-amber-400",
    bg: "from-amber-500/10 to-orange-500/5",
  },
]

export default function AdminPage() {
  return (
    <div className="min-h-screen bg-background p-6 md:p-10">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-foreground">Admin Console</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage AI agents, workflows, and platform governance.
          </p>
        </div>

        {/* Section Cards */}
        <div className="grid gap-4 md:grid-cols-3">
          {adminSections.map((section) => (
            <Link key={section.title} href={section.href}>
              <Card className={`h-full bg-gradient-to-br ${section.bg} border-border hover:border-primary/40 transition-all cursor-pointer group`}>
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-2">
                    <section.icon className={`h-5 w-5 ${section.color}`} />
                    <CardTitle className="text-base">{section.title}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-xs leading-relaxed">
                    {section.description}
                  </CardDescription>
                  <div className="mt-3 flex items-center gap-1 text-xs text-primary opacity-0 group-hover:opacity-100 transition-opacity">
                    Open <ArrowRight className="h-3 w-3" />
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
