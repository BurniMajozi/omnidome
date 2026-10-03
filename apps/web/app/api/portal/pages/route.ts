import { NextResponse, type NextRequest } from "next/server"
import { createClient } from "@supabase/supabase-js"

export interface PortalLandingPage {
  id: string | number
  name: string
  url: string
  status: "published" | "draft"
  views: number
  conversions: number
  rate: string
  intent?: "promo" | "business" | "coverage" | "referral"
  designDirection?: "craft" | "bolder" | "quieter" | "delight"
  marketingCampaign?: string
  utmSource?: string
  utmMedium?: string
  crmQueue?: string
  metaPixelId?: string
  gtmContainerId?: string
  updatedAt?: string
}

// Durable initial dataset
let portalPagesStore: PortalLandingPage[] = [
  {
    id: "page-1",
    name: "Fibre Promo Q1 Summer Sprint",
    url: "/promo/fibre-summer-sprint",
    status: "published",
    views: 12450,
    conversions: 342,
    rate: "2.7%",
    intent: "promo",
    designDirection: "craft",
    marketingCampaign: "summer_fibre_flash",
    utmSource: "google_cpc",
    utmMedium: "paid_search",
    crmQueue: "Cape Town Inbound Feasibility",
    updatedAt: new Date().toISOString(),
  },
  {
    id: "page-2",
    name: "Business Solutions Dedicated 1Gbps",
    url: "/business/direct-1g",
    status: "published",
    views: 8920,
    conversions: 156,
    rate: "1.7%",
    intent: "business",
    designDirection: "bolder",
    marketingCampaign: "enterprise_cape_switch",
    utmSource: "linkedin_ads",
    utmMedium: "cpc",
    crmQueue: "Enterprise Commercial Sales",
    updatedAt: new Date().toISOString(),
  },
  {
    id: "page-3",
    name: "Instant FTTH Feasibility Qualifier",
    url: "/coverage/instant-check",
    status: "draft",
    views: 0,
    conversions: 0,
    rate: "-",
    intent: "coverage",
    designDirection: "quieter",
    marketingCampaign: "coverage_qualifier_kwazulu",
    utmSource: "meta_ads",
    utmMedium: "social_paid",
    crmQueue: "Durban Residential Queue",
    updatedAt: new Date().toISOString(),
  },
  {
    id: "page-4",
    name: "Refer a Neighbour Loop",
    url: "/refer/friends",
    status: "published",
    views: 5640,
    conversions: 89,
    rate: "1.6%",
    intent: "referral",
    designDirection: "delight",
    marketingCampaign: "customer_referrals_march",
    utmSource: "whatsapp_broadcast",
    utmMedium: "direct",
    crmQueue: "Customer Care Loyalty",
    updatedAt: new Date().toISOString(),
  },
]

function getSupabaseClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || process.env.INTERNAL_SERVICE_KEY
  if (!url || !key) return null
  return createClient(url, key)
}

export async function GET(request: NextRequest) {
  try {
    const supabase = getSupabaseClient()
    if (supabase) {
      const { data, error } = await supabase
        .from("portal_landing_pages")
        .select("*")
        .order("created_at", { ascending: false })

      if (!error && data && data.length > 0) {
        return NextResponse.json({ success: true, data }, { status: 200 })
      }
    }

    return NextResponse.json({ success: true, data: portalPagesStore }, { status: 200 })
  } catch (error) {
    console.warn("[Portal API] Returning fallback in-memory store due to error:", error)
    return NextResponse.json({ success: true, data: portalPagesStore }, { status: 200 })
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    if (!body || !body.name) {
      return NextResponse.json({ success: false, error: "Page name is required" }, { status: 400 })
    }

    const newPage: PortalLandingPage = {
      id: body.id || `page-${Date.now()}`,
      name: body.name,
      url: body.url || `/promo/${body.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
      status: body.status || "draft",
      views: Number(body.views) || 0,
      conversions: Number(body.conversions) || 0,
      rate: body.rate || (body.views ? `${((body.conversions / body.views) * 100).toFixed(1)}%` : "-"),
      intent: body.intent || "promo",
      designDirection: body.designDirection || "craft",
      marketingCampaign: body.marketingCampaign || "default_campaign",
      utmSource: body.utmSource || "direct",
      utmMedium: body.utmMedium || "organic",
      crmQueue: body.crmQueue || "General Sales Queue",
      metaPixelId: body.metaPixelId || "",
      gtmContainerId: body.gtmContainerId || "",
      updatedAt: new Date().toISOString(),
    }

    portalPagesStore = [newPage, ...portalPagesStore]

    const supabase = getSupabaseClient()
    if (supabase) {
      try {
        await supabase.from("portal_landing_pages").upsert([newPage])
      } catch (dbErr) {
        console.warn("[Portal API] Supabase sync deferred:", dbErr)
      }
    }

    return NextResponse.json({ success: true, data: newPage }, { status: 201 })
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "Failed to create page" },
      { status: 500 }
    )
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json()
    if (!body || !body.id) {
      return NextResponse.json({ success: false, error: "Page ID is required for update" }, { status: 400 })
    }

    const existingIndex = portalPagesStore.findIndex((p) => String(p.id) === String(body.id))
    if (existingIndex >= 0) {
      portalPagesStore[existingIndex] = {
        ...portalPagesStore[existingIndex],
        ...body,
        updatedAt: new Date().toISOString(),
      }
    } else {
      portalPagesStore = [{ ...body, updatedAt: new Date().toISOString() }, ...portalPagesStore]
    }

    const updated = portalPagesStore.find((p) => String(p.id) === String(body.id)) || body

    const supabase = getSupabaseClient()
    if (supabase) {
      try {
        await supabase.from("portal_landing_pages").upsert([updated])
      } catch (dbErr) {
        console.warn("[Portal API] Supabase sync deferred:", dbErr)
      }
    }

    return NextResponse.json({ success: true, data: updated }, { status: 200 })
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "Failed to update page" },
      { status: 500 }
    )
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const id = searchParams.get("id")
    if (!id) {
      return NextResponse.json({ success: false, error: "Missing page ID" }, { status: 400 })
    }

    portalPagesStore = portalPagesStore.filter((p) => String(p.id) !== String(id))

    const supabase = getSupabaseClient()
    if (supabase) {
      try {
        await supabase.from("portal_landing_pages").delete().eq("id", id)
      } catch (dbErr) {
        console.warn("[Portal API] Supabase sync deferred:", dbErr)
      }
    }

    return NextResponse.json({ success: true, message: `Page ${id} deleted` }, { status: 200 })
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "Failed to delete page" },
      { status: 500 }
    )
  }
}
