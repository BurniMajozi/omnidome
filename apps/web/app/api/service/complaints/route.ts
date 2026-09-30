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

// No complaint ingestion backend exists yet (no crawler, no HelloPeter / social /
// regulatory feed), so the feed is EMPTY by design: nothing is fabricated. The only
// state kept here is the list of sources a user asked to monitor, which is real
// input, but "crawled" is never claimed because nothing crawls it.
const complaintsFeed: CustomerComplaintEvent[] = []

export interface TrackedSource {
  url: string
  label: string
  platform: string
  lastCrawled: string | null
  status: "NOT_CRAWLED"
}

let trackedUrls: TrackedSource[] = []

export async function GET() {
  return NextResponse.json({
    connected: false,
    complaints: complaintsFeed,
    trackedUrls,
    stats: null,
  })
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { action } = body

    if (action === "ADD_URL") {
      const { url, label, platform } = body
      if (!url || typeof url !== "string") return NextResponse.json({ error: "URL is required" }, { status: 400 })
      if (trackedUrls.some((t) => t.url === url)) {
        return NextResponse.json({ error: "Source already added" }, { status: 409 })
      }

      const newSource: TrackedSource = {
        url,
        label: label || url,
        platform: platform || "Custom Web Source",
        lastCrawled: null,
        status: "NOT_CRAWLED",
      }
      trackedUrls = [newSource, ...trackedUrls]
      return NextResponse.json({ success: true, source: newSource, crawled: false })
    }

    if (action === "RESOLVE_COMPLAINT") {
      return NextResponse.json({ error: "Complaint not found" }, { status: 404 })
    }

    return NextResponse.json({ error: "Unsupported action" }, { status: 400 })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Failed to process complaint request"
    return NextResponse.json({ error: msg }, { status: 400 })
  }
}
