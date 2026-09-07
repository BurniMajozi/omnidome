"use client"

import { useState } from "react"
import {
  ShieldAlert,
  CheckCircle,
  XCircle,
  MessageSquare,
  Sparkles,
  ArrowRight,
  TrendingDown,
  Mail,
  Zap,
  Check,
  AlertTriangle,
  Clock,
  ExternalLink,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export interface ExecutiveApprovalItem {
  id: string
  title: string
  agent: "executive" | "retention" | "support" | "provisioning" | "customer_facing"
  agentName: string
  agentIcon: string
  impact: "critical" | "high" | "medium"
  category: "Retention Save" | "Pricing Strategy" | "Outage Compensation" | "Network Provisioning" | "Compliance Alert"
  summary: string
  context: string
  estimatedRoi?: string
  targetCount?: number
  timestamp: string
  status: "pending" | "approved" | "dismissed"
}

const DEFAULT_APPROVAL_ITEMS: ExecutiveApprovalItem[] = [
  {
    id: "appr-1",
    title: "Dispatch 45 Proactive Retention Save Offers (Fiber 100/200 Mbps)",
    agent: "retention",
    agentName: "ChurnGuard",
    agentIcon: "🛡️",
    impact: "critical",
    category: "Retention Save",
    summary: "45 high-value subscribers in Sea Point & Umhlanga flagged with >82% churn probability following recent maintenance. Proposes 15% speed upgrade credit for 3 months.",
    context: "Estimated MRR at risk is R48,500/mo. Applying credit preserves an estimated R582,000 annualized revenue.",
    estimatedRoi: "R582,000 Annualized MRR Saved",
    targetCount: 45,
    timestamp: "10 mins ago",
    status: "pending",
  },
  {
    id: "appr-2",
    title: "Approve MetroFibre Bulk Provisioning Batch for Sandton Office Park",
    agent: "provisioning",
    agentName: "ProvisionBot",
    agentIcon: "⚡",
    impact: "high",
    category: "Network Provisioning",
    summary: "12 corporate broadband circuits ready for automated ONT configuration and IP allocation across MetroFibre backbone.",
    context: "Installation SLA expires in 18 hours. Approving triggers automated RADIUS profile provisioning.",
    estimatedRoi: "R96,000/mo New Contracted MRR",
    targetCount: 12,
    timestamp: "25 mins ago",
    status: "pending",
  },
  {
    id: "appr-3",
    title: "Authorize SLA Credit Adjustments for Outage #INC-8921 (Durban Central)",
    agent: "support",
    agentName: "SupportBot",
    agentIcon: "🔧",
    impact: "medium",
    category: "Outage Compensation",
    summary: "28 business clients experienced 3.5h unplanned downtime due to backhaul power failure. Pre-calculated R12,400 pro-rata billing credit.",
    context: "Automatic SLA credits prevent escalation to ICASA/adjudication and restore client trust.",
    estimatedRoi: "SLA Compliance & Goodwill",
    targetCount: 28,
    timestamp: "1 hour ago",
    status: "pending",
  },
  {
    id: "appr-4",
    title: "Executive Strategic Realignment: Cape Town 1Gbps Fiber Price Drop",
    agent: "executive",
    agentName: "InsightDome",
    agentIcon: "📊",
    impact: "high",
    category: "Pricing Strategy",
    summary: "Competitor Vumatel announced R799 500Mbps tier. Recommends repositioning OmniHome 1Gbps to R999 with bundled VoiceBox VoIP.",
    context: "Unit economics model shows gross margin remains above 42% while defending 320 at-risk consumer lines.",
    estimatedRoi: "+18% Target Net Adds in Q4",
    timestamp: "2 hours ago",
    status: "pending",
  },
]

export function ExecutiveApprovalQueue() {
  const [items, setItems] = useState<ExecutiveApprovalItem[]>(DEFAULT_APPROVAL_ITEMS)
  const [actionFeedback, setActionFeedback] = useState<string | null>(null)

  const pendingItems = items.filter((i) => i.status === "pending")

  const handleApprove = (item: ExecutiveApprovalItem) => {
    setItems((prev) =>
      prev.map((i) => (i.id === item.id ? { ...i, status: "approved" as const } : i)),
    )
    setActionFeedback(`Approved & executed: "${item.title}". Action dispatched via ${item.agentName}.`)
    setTimeout(() => setActionFeedback(null), 4000)
  }

  const handleDismiss = (id: string) => {
    setItems((prev) =>
      prev.map((i) => (i.id === id ? { ...i, status: "dismissed" as const } : i)),
    )
    setActionFeedback("Proposal dismissed.")
    setTimeout(() => setActionFeedback(null), 3000)
  }

  const handleDiscussInChat = (item: ExecutiveApprovalItem) => {
    const prompt = `Executive Deliberation on Action Proposal:
Title: ${item.title}
Originating Agent: ${item.agentName} (${item.agent})
Category: ${item.category} | Priority: ${item.impact}
Summary: ${item.summary}
Financial / Operational Context: ${item.context}
${item.estimatedRoi ? `Projected Impact: ${item.estimatedRoi}` : ""}

Please break down:
1. What are the key risks and immediate benefits if approved?
2. What are the specific implementation steps?
3. Draft the required customer communication / executive order as an artifact for review.`

    window.dispatchEvent(
      new CustomEvent("open-agent-chat", {
        detail: {
          agent: item.agent,
          prompt,
          draft: prompt,
        },
      }),
    )

    setActionFeedback(`Opened deliberation with ${item.agentName} in Agent Chat.`)
    setTimeout(() => setActionFeedback(null), 4000)
  }

  if (pendingItems.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card p-5 shadow-xs">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400">
              <CheckCircle className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-foreground">Executive Action Queue</h3>
              <p className="text-xs text-muted-foreground">All autonomous agent proposals have been reviewed and approved</p>
            </div>
          </div>
          <Badge variant="outline" className="border-emerald-500/30 text-emerald-400 text-xs">
            Queue Clear
          </Badge>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-xs space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/15 text-amber-400">
            <ShieldAlert className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-foreground">Executive Approval Queue</h3>
              <Badge variant="secondary" className="bg-amber-500/20 text-amber-300 font-mono text-[11px] px-1.5">
                {pendingItems.length} Needs Review
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              High-stakes autonomous actions staged by specialist agents requiring executive authorization
            </p>
          </div>
        </div>

        <Button
          variant="outline"
          size="sm"
          className="text-xs h-8 border-primary/40 text-primary hover:bg-primary/10 gap-1.5"
          onClick={() => {
            items.forEach((item) => {
              if (item.status === "pending") handleApprove(item)
            })
          }}
        >
          <Check className="h-3.5 w-3.5" />
          <span>Batch Approve All ({pendingItems.length})</span>
        </Button>
      </div>

      {actionFeedback && (
        <div className="rounded-md bg-primary/10 border border-primary/20 px-3 py-1.5 text-xs font-medium text-primary animate-in fade-in flex items-center justify-between">
          <span>{actionFeedback}</span>
          <button onClick={() => setActionFeedback(null)} className="text-primary hover:text-primary/80">×</button>
        </div>
      )}

      <div className="grid gap-3">
        {pendingItems.map((item) => (
          <div
            key={item.id}
            className="group relative flex flex-col justify-between rounded-lg border border-border/80 bg-secondary/15 p-4 transition-all hover:border-primary/40 hover:bg-secondary/25"
          >
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
              <div className="space-y-1.5 flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded-md bg-secondary text-foreground border border-border/60">
                    <span>{item.agentIcon}</span>
                    <span>{item.agentName}</span>
                  </span>

                  <span
                    className={cn(
                      "text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded border",
                      item.impact === "critical" && "bg-red-500/15 text-red-400 border-red-500/30",
                      item.impact === "high" && "bg-amber-500/15 text-amber-400 border-amber-500/30",
                      item.impact === "medium" && "bg-blue-500/15 text-blue-400 border-blue-500/30",
                    )}
                  >
                    {item.impact}
                  </span>

                  <Badge variant="outline" className="text-[10px] text-muted-foreground">
                    {item.category}
                  </Badge>

                  <span className="text-[11px] text-muted-foreground ml-auto sm:ml-0 flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {item.timestamp}
                  </span>
                </div>

                <h4 className="text-sm font-semibold text-foreground pt-0.5">{item.title}</h4>
                <p className="text-xs text-muted-foreground leading-relaxed">{item.summary}</p>
                <div className="rounded-md bg-background/60 border border-border/40 p-2 text-[11px] text-muted-foreground/90 font-mono">
                  {item.context}
                </div>
              </div>

              {item.estimatedRoi && (
                <div className="shrink-0 sm:text-right pt-1 sm:pt-0">
                  <span className="text-[10px] uppercase text-muted-foreground font-semibold block">Projected Value</span>
                  <span className="text-xs font-bold text-emerald-400 font-mono">{item.estimatedRoi}</span>
                </div>
              )}
            </div>

            <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-border/50 text-xs">
              <span className="text-[11px] text-muted-foreground">
                {item.targetCount ? `Affects ${item.targetCount} accounts/lines` : "Strategic executive policy"}
              </span>

              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs text-muted-foreground hover:text-foreground gap-1"
                  onClick={() => handleDismiss(item.id)}
                >
                  <XCircle className="h-3.5 w-3.5" />
                  <span>Dismiss</span>
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs border-primary/40 text-primary hover:bg-primary/10 gap-1"
                  onClick={() => handleDiscussInChat(item)}
                >
                  <MessageSquare className="h-3.5 w-3.5" />
                  <span>Discuss in Chat</span>
                </Button>

                <Button
                  size="sm"
                  className="h-7 text-xs bg-primary hover:bg-primary/90 text-primary-foreground gap-1 font-semibold"
                  onClick={() => handleApprove(item)}
                >
                  <Check className="h-3.5 w-3.5" />
                  <span>Approve & Execute</span>
                </Button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
