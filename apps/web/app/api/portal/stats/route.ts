import { NextResponse, type NextRequest } from "next/server"

export async function GET(_request: NextRequest) {
  try {
    const stats = {
      websiteVisitors: 16700,
      visitorsGrowth: "+12.5% this week",
      aiConversations: 9300,
      aiResolutionRate: "75% resolution rate",
      fieldAgentsActive: 45,
      leadsToday: 34,
      dealsWonToday: 12,
      techniciansActive: 38,
      jobsCompletedToday: 86,
      averageJobTime: "42 min",
      customerRating: 4.8,
      visitorTraffic: [
        { day: "Mon", website: 2400, customerPortal: 1800, fieldApp: 450, techApp: 320 },
        { day: "Tue", website: 2100, customerPortal: 1650, fieldApp: 480, techApp: 340 },
        { day: "Wed", website: 2800, customerPortal: 2100, fieldApp: 520, techApp: 380 },
        { day: "Thu", website: 3200, customerPortal: 2400, fieldApp: 490, techApp: 350 },
        { day: "Fri", website: 2900, customerPortal: 2200, fieldApp: 510, techApp: 370 },
        { day: "Sat", website: 1800, customerPortal: 1400, fieldApp: 280, techApp: 150 },
        { day: "Sun", website: 1500, customerPortal: 1100, fieldApp: 220, techApp: 120 },
      ],
      systemStatus: {
        mainWebsite: { url: "omnidome.co.za", status: "online" },
        aiChatSystem: { activeBots: 4, status: "running" },
        fieldSalesApp: { version: "v2.4.1", status: "live" },
        technicianApp: { version: "v3.1.0", status: "live" },
      },
    }

    return NextResponse.json({ success: true, data: stats }, { status: 200 })
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "Failed to load portal stats" },
      { status: 500 }
    )
  }
}
