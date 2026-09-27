import { NextRequest, NextResponse } from "next/server"

export interface CustomerComplaintEvent {
  id: string
  source: "HelloPeter" | "DownDetector" | "X / Twitter" | "Facebook" | "Regulatory Inbox (ICASA)" | "Refund Request" | "Post-Call Survey"
  sourceUrl?: string
  author: string
  location?: string
  sentimentScore: number // -1.0 to 1.0
  sentimentPolarity: "Extremely Negative" | "Negative" | "Neutral" | "Positive"
  category: "Billing / Refund" | "Fibre Outage / Physical" | "Latency / Gaming" | "Technician No-Show" | "Regulatory Breach"
  urgency: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
  title: string
  content: string
  timestamp: string
  status: "INVESTIGATING" | "TICKET_CREATED" | "REFUND_PENDING" | "RESOLVED"
  correlatedTicketId?: string
  assignedTeam: string
  suggestedAction: string
}

let complaintsFeed: CustomerComplaintEvent[] = [
  {
    id: "comp-1",
    source: "HelloPeter",
    sourceUrl: "https://www.hellopeter.com/omnidome/reviews/unresolved-rosebank-fibre-break",
    author: "Grant Van Der Merwe",
    location: "Rosebank, Johannesburg",
    sentimentScore: -0.88,
    sentimentPolarity: "Extremely Negative",
    category: "Fibre Outage / Physical",
    urgency: "CRITICAL",
    title: "Day 3 without internet in Rosebank - Zero technician update!",
    content: "Our uncapped business 500Mbps fiber has been down since Wednesday. Call center keeps saying 'dispatch in progress' but no van arrived. We are losing business revenue. Fix this immediately or I am taking this to ICASA!",
    timestamp: "12 minutes ago",
    status: "INVESTIGATING",
    correlatedTicketId: "TKT-8821",
    assignedTeam: "Field Operations (Van #4)",
    suggestedAction: "Re-prioritize Splicing Van #4 to Oxford Rd corridor; dispatch proactive WhatsApp SMS credit note.",
  },
  {
    id: "comp-2",
    source: "DownDetector",
    sourceUrl: "https://downdetector.co.za/status/omnidome-telecoms",
    author: "DownDetector Automated Telemetry",
    location: "Pretoria East / Menlyn",
    sentimentScore: -0.72,
    sentimentPolarity: "Negative",
    category: "Fibre Outage / Physical",
    urgency: "HIGH",
    title: "Spike Detected: 48 User Reports in Menlyn Corridor",
    content: "Sudden spike in user reports indicating 'Total Blackout / Red LOS' on OmniDome GPON network in Menlyn & Faerie Glen. Correlation with Eskom Stage 2 load shedding feeder trip.",
    timestamp: "28 minutes ago",
    status: "TICKET_CREATED",
    correlatedTicketId: "INC-9904",
    assignedTeam: "NOC & Core Infra",
    suggestedAction: "Activate generator at Menlyn POP 2; damp BGP route flapping to Teraco.",
  },
  {
    id: "comp-3",
    source: "Regulatory Inbox (ICASA)",
    sourceUrl: "mailto:complaints@icasa.org.za",
    author: "ICASA Consumer Protection Unit (Ref: CAS-2026-9921)",
    location: "Sandton, Gauteng",
    sentimentScore: -0.92,
    sentimentPolarity: "Extremely Negative",
    category: "Regulatory Breach",
    urgency: "CRITICAL",
    title: "Formal Section 69 Complaint: Failure to Refund Unutilized Days Post-Cancellation",
    content: "Consumer Mr. David Khoza has lodged an escalated formal dispute alleging failure by OmniDome to process refund of R 1,840 after service was cancelled with 30-day notice. Response required within 5 working days.",
    timestamp: "1 hour ago",
    status: "REFUND_PENDING",
    correlatedTicketId: "REF-4412",
    assignedTeam: "Finance & Billing",
    suggestedAction: "Finance Lead to authorize R 1,840 Netcash refund immediately; submit formal ICASA compliance response.",
  },
  {
    id: "comp-4",
    source: "Refund Request",
    sourceUrl: "https://portal.omnidome.co.za/billing/refunds/REF-5021",
    author: "Ayesha Patel",
    location: "Durban Central",
    sentimentScore: -0.65,
    sentimentPolarity: "Negative",
    category: "Billing / Refund",
    urgency: "HIGH",
    title: "Double Debit Order Deduction on 25th September",
    content: "My account was debited twice: R 899.00 at 04:00 AM and again R 899.00 at 06:15 AM via Capitec debit order. I need the second debit reversed today please.",
    timestamp: "2 hours ago",
    status: "REFUND_PENDING",
    correlatedTicketId: "REF-5021",
    assignedTeam: "Finance & Billing",
    suggestedAction: "Execute single-click EFT reversal via Netcash API batch #992.",
  },
  {
    id: "comp-5",
    source: "X / Twitter",
    sourceUrl: "https://x.com/Sipho_TechGuru/status/18920199218",
    author: "@Sipho_TechGuru",
    location: "Soweto, Gauteng",
    sentimentScore: -0.58,
    sentimentPolarity: "Negative",
    category: "Latency / Gaming",
    urgency: "MEDIUM",
    title: "@OmniDomeZA high jitter on Valorant and Warzone servers tonight",
    content: "Ping jumping between 15ms and 190ms every 30 seconds on JHB servers. What is going on with the transit link @ Teraco? Anyone else in Soweto experiencing this? #OmniDome",
    timestamp: "3 hours ago",
    status: "RESOLVED",
    correlatedTicketId: "TKT-8790",
    assignedTeam: "NOC & Core Infra",
    suggestedAction: "Advise customer that Teraco IX link re-balanced; send direct link to latency telemetry graph.",
  },
  {
    id: "comp-6",
    source: "Post-Call Survey",
    sourceUrl: "https://callcenter.omnidome.internal/surveys/SUR-8841",
    author: "Anonymous Caller (082 *** 4491)",
    location: "Cape Town",
    sentimentScore: -0.80,
    sentimentPolarity: "Extremely Negative",
    category: "Technician No-Show",
    urgency: "HIGH",
    title: "Rating: 1/5 Stars - 'Technician promised to arrive between 10:00 and 12:00, never called'",
    content: "I took half a day off work to wait for the installation technician. No call, no SMS, no van. Customer service agent had no visibility on where the driver was.",
    timestamp: "4 hours ago",
    status: "TICKET_CREATED",
    correlatedTicketId: "TKT-8841",
    assignedTeam: "Field Operations (Dispatch)",
    suggestedAction: "Dispatch manager to contact customer with R200 courtesy credit voucher; reschedule priority Saturday slot.",
  }
]

let trackedUrls = [
  { url: "https://www.hellopeter.com/omnidome-telecoms", label: "HelloPeter Consumer Portal", platform: "HelloPeter", lastCrawled: "10 mins ago", status: "ACTIVE" },
  { url: "https://downdetector.co.za/status/omnidome", label: "DownDetector South Africa", platform: "DownDetector", lastCrawled: "15 mins ago", status: "ACTIVE" },
  { url: "https://x.com/search?q=%40OmniDomeZA", label: "X / Twitter Brand Mentions", platform: "X / Twitter", lastCrawled: "25 mins ago", status: "ACTIVE" },
  { url: "mailto:disputes@ispa.org.za", label: "ISPA Regulatory Ombudsman", platform: "Regulatory Inbox", lastCrawled: "1 hour ago", status: "ACTIVE" }
]

export async function GET() {
  const totalComplaints = complaintsFeed.length
  const criticalCount = complaintsFeed.filter((c) => c.urgency === "CRITICAL").length
  const unresolvedCount = complaintsFeed.filter((c) => c.status !== "RESOLVED").length
  const averageSentiment = (complaintsFeed.reduce((sum, c) => sum + c.sentimentScore, 0) / totalComplaints).toFixed(2)

  return NextResponse.json({
    complaints: complaintsFeed,
    trackedUrls,
    stats: {
      totalTracked: totalComplaints,
      criticalUrgent: criticalCount,
      unresolvedEscalations: unresolvedCount,
      averageSentimentScore: Number(averageSentiment),
      sentimentDistribution: {
        extremelyNegative: complaintsFeed.filter((c) => c.sentimentPolarity === "Extremely Negative").length,
        negative: complaintsFeed.filter((c) => c.sentimentPolarity === "Negative").length,
        neutral: complaintsFeed.filter((c) => c.sentimentPolarity === "Neutral").length,
        positive: complaintsFeed.filter((c) => c.sentimentPolarity === "Positive").length,
      }
    }
  })
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { action } = body

    if (action === "ADD_URL") {
      const { url, label, platform } = body
      if (!url) return NextResponse.json({ error: "URL is required" }, { status: 400 })

      const newSource = {
        url,
        label: label || url,
        platform: platform || "Custom Web Source",
        lastCrawled: "Just now",
        status: "ACTIVE",
      }
      trackedUrls = [newSource, ...trackedUrls]

      // Simulate crawler scraping new feedback from the added URL
      const crawledComplaint: CustomerComplaintEvent = {
        id: `comp-${Date.now()}`,
        source: (platform as CustomerComplaintEvent["source"]) || "HelloPeter",
        sourceUrl: url,
        author: "Crawled Consumer Feedback",
        location: "South Africa (Web Scrape)",
        sentimentScore: -0.74,
        sentimentPolarity: "Negative",
        category: "Billing / Refund",
        urgency: "HIGH",
        title: `Extracted Complaint from ${label || url}`,
        content: `Firecrawl extracted live feedback: Customer reported difficulty contacting technical support during peak load shedding hours. Service credit requested.`,
        timestamp: "Just now",
        status: "INVESTIGATING",
        correlatedTicketId: `TKT-${Math.floor(1000 + Math.random() * 9000)}`,
        assignedTeam: "Customer Support",
        suggestedAction: "Proactively send SMS update and offer R100 service goodwill credit.",
      }

      complaintsFeed = [crawledComplaint, ...complaintsFeed]
      return NextResponse.json({ success: true, source: newSource, newComplaint: crawledComplaint })
    }

    if (action === "RESOLVE_COMPLAINT") {
      const { id } = body
      const index = complaintsFeed.findIndex((c) => c.id === id)
      if (index !== -1) {
        complaintsFeed[index].status = "RESOLVED"
        return NextResponse.json({ success: true, complaint: complaintsFeed[index] })
      }
      return NextResponse.json({ error: "Complaint not found" }, { status: 404 })
    }

    return NextResponse.json({ error: "Unsupported action" }, { status: 400 })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Failed to process complaint request"
    return NextResponse.json({ error: msg }, { status: 400 })
  }
}
