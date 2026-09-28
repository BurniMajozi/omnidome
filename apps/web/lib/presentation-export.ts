export interface PresentationSlide {
  id: string
  title: string
  subtitle?: string
  category?: string
  layout: "title" | "kpi-grid" | "bullets" | "split" | "table" | "conclusion"
  kpis?: Array<{
    label: string
    value: string
    change?: string
    isPositive?: boolean
  }>
  bullets?: string[]
  takeaway?: string
  speakerNotes?: string
  chartData?: {
    type: "bar" | "pie" | "line"
    title: string
    data: Array<{ name: string; value: number }>
  }
}

export interface BrandPalette {
  id: string
  name: string
  description?: string
  background: string
  primary: string
  accent: string
  text: string
  subtext: string
  cardBg: string
  border: string
}

export type BrandVoiceTone =
  | "executive"
  | "commercial"
  | "visionary"
  | "technical"
  | "customer-centric"

export interface BrandKit {
  companyName: string
  tagline: string
  logoUrl?: string // Data URL (base64) or URL
  voiceTone: BrandVoiceTone
  brandGuidelines?: string // Ingested brand description / prompt
  palette: BrandPalette
}

export interface GeneratedPresentation {
  id: string
  title: string
  topic: string
  theme: "dark-executive" | "indigo-cyber" | "emerald-clean" | "light-corporate" | "custom-brand"
  created_at: string
  slides: PresentationSlide[]
  rawDataSummary?: string
  brandKit?: BrandKit
}

export interface ThemeColors {
  background: string
  primary: string
  accent: string
  text: string
  subtext: string
  cardBg: string
  border: string
}

export const BRAND_PALETTES: BrandPalette[] = [
  {
    id: "omnidome-obsidian",
    name: "OmniDome Obsidian",
    description: "Deep obsidian dark with electric cyan & sapphire telemetry highlights",
    background: "0D1117",
    primary: "38BDF8",
    accent: "34D399",
    text: "F0F6FC",
    subtext: "8B949E",
    cardBg: "161B22",
    border: "30363D",
  },
  {
    id: "vodacom-crimson",
    name: "Vodacom Crimson",
    description: "Bold telecommunications red with sleek slate gray cards",
    background: "111827",
    primary: "EF4444",
    accent: "F87171",
    text: "F9FAFB",
    subtext: "9CA3AF",
    cardBg: "1F2937",
    border: "374151",
  },
  {
    id: "mtn-sunrise",
    name: "MTN Sunrise Amber",
    description: "Vibrant yellow-gold accents with deep graphite contrast",
    background: "0F172A",
    primary: "FBBF24",
    accent: "F59E0B",
    text: "FFFFFF",
    subtext: "94A3B8",
    cardBg: "1E293B",
    border: "334155",
  },
  {
    id: "telkom-azure",
    name: "Telkom Royal Azure",
    description: "Classic South African telecommunications blue and cool gray tones",
    background: "0B132B",
    primary: "0284C7",
    accent: "38BDF8",
    text: "F0F9FF",
    subtext: "7DD3FC",
    cardBg: "1C2541",
    border: "3A506B",
  },
  {
    id: "openserve-emerald",
    name: "OpenServe Emerald Fiber",
    description: "High-contrast dark forest canvas with neon mint optical fiber indicators",
    background: "062016",
    primary: "10B981",
    accent: "6EE7B7",
    text: "ECFDF5",
    subtext: "A7F3D0",
    cardBg: "064E3B",
    border: "047857",
  },
  {
    id: "light-boardroom",
    name: "Clean Boardroom (Light)",
    description: "Minimalist crisp white presentation aesthetic for formal investor decks",
    background: "FFFFFF",
    primary: "1D4ED8",
    accent: "059669",
    text: "0F172A",
    subtext: "64748B",
    cardBg: "F8FAFC",
    border: "E2E8F0",
  },
]

export const BRAND_VOICES: Array<{
  id: BrandVoiceTone
  label: string
  badge: string
  description: string
  focusKeywords: string[]
}> = [
  {
    id: "executive",
    label: "Executive & Authoritative",
    badge: "Boardroom",
    description: "High-conviction, objective, metrics-first governance focus on EBITDA, capital efficiency, and strategic execution.",
    focusKeywords: ["EBITDA margin", "Capital allocation", "Unit economics", "Governance", "Risk mitigation"],
  },
  {
    id: "commercial",
    label: "Bold & Commercial Growth",
    badge: "Sales & Rev",
    description: "Aggressive, market-share expanding, sales velocity language focusing on ARPU uplift, conversion, and competitive displacement.",
    focusKeywords: ["ARPU expansion", "Market capture", "VAS attach rate", "Conversion velocity", "Revenue acceleration"],
  },
  {
    id: "visionary",
    label: "Visionary & Transformational",
    badge: "Innovation",
    description: "Forward-looking, inspiring digital evolution tone highlighting cloud integration, AI autonomous workflows, and future ecosystem expansion.",
    focusKeywords: ["Autonomous operations", "Digital transformation", "Next-gen ecosystem", "AI disruption", "Strategic horizon"],
  },
  {
    id: "technical",
    label: "Technical & SLA Rigor",
    badge: "Engineering",
    description: "Ultra-precise, engineering-grounded vocabulary prioritizing 99.999% uptime, latency reduction, MTTR, and proactive packet telemetry.",
    focusKeywords: ["99.999% SLA", "Sub-millisecond latency", "Automated MTTR", "RADIUS resilience", "FNO optical telemetry"],
  },
  {
    id: "customer-centric",
    label: "Customer-Centric & Care-Led",
    badge: "Retention",
    description: "Empathetic, relationship-driven voice emphasizing Net Promoter Score (NPS), subscriber advocacy, seamless onboarding, and churn prevention.",
    focusKeywords: ["Customer lifetime value", "First Contact Resolution", "Subscriber intimacy", "Proactive care", "Zero-friction experience"],
  },
]

export const BRAND_INGEST_TEMPLATES = [
  {
    name: "Tier-1 National Fiber & 5G Operator",
    companyName: "Apex Telecom Africa",
    tagline: "Uncompromising Gigabit Connectivity for Africa's Enterprise & Homes",
    voiceTone: "executive" as BrandVoiceTone,
    paletteId: "omnidome-obsidian",
    brandGuidelines:
      "We are the premier national optical fiber and 5G network operator. Our communication is precise, authoritative, and data-backed. Never use colloquialisms or unsupported superlatives. Emphasize network reliability (99.99% uptime), nationwide metro rings, enterprise SLA commitments, and healthy unit economics.",
  },
  {
    name: "Fast-Growing Regional FNO / ISP",
    companyName: "Velocity Fiber Networks",
    tagline: "Hyper-Fast Local Broadband Powered by Next-Gen FTTH",
    voiceTone: "commercial" as BrandVoiceTone,
    paletteId: "vodacom-crimson",
    brandGuidelines:
      "We are an agile, disruptive fiber-to-the-home and business provider in Gauteng and Western Cape. Our brand tone is bold, punchy, and growth-obsessed. We pride ourselves on zero-buffering streaming, rapid 48-hour customer installations, and high ARPU value bundles.",
  },
  {
    name: "Open-Access Optical Infrastructure",
    companyName: "OpenGrid Connect",
    tagline: "The Neutral Digital Highway Powering Internet Service Providers",
    voiceTone: "technical" as BrandVoiceTone,
    paletteId: "openserve-emerald",
    brandGuidelines:
      "We operate carrier-grade open access dark fiber and lit services. Our tone is deeply technical, objective, and SLA-rigorous. We speak directly to CTOs and Network Architects about low MTTR, automated telemetry, optical line terminations (OLT), and high capacity backhaul.",
  },
  {
    name: "Enterprise Managed Cloud & Telecom",
    companyName: "Aegis Enterprise Cloud",
    tagline: "Mission-Critical Telecom & Multi-Cloud Connectivity",
    voiceTone: "visionary" as BrandVoiceTone,
    paletteId: "telkom-azure",
    brandGuidelines:
      "We provide enterprise SD-WAN, unified communications, and cloud direct-connect. Tone should be forward-looking, enterprise-secure, and transformational. Focus on enabling digital business transformation and operational resilience.",
  },
]

const THEME_CONFIGS: Record<string, ThemeColors> = {
  "dark-executive": {
    background: "0D1117",
    primary: "58A6FF",
    accent: "7EE787",
    text: "F0F6FC",
    subtext: "8B949E",
    cardBg: "161B22",
    border: "30363D",
  },
  "indigo-cyber": {
    background: "0B0F19",
    primary: "818CF8",
    accent: "C084FC",
    text: "F8FAFC",
    subtext: "94A3B8",
    cardBg: "1E293B",
    border: "334155",
  },
  "emerald-clean": {
    background: "062016",
    primary: "34D399",
    accent: "6EE7B7",
    text: "ECFDF5",
    subtext: "A7F3D0",
    cardBg: "064E3B",
    border: "047857",
  },
  "light-corporate": {
    background: "F8FAFC",
    primary: "2563EB",
    accent: "059669",
    text: "0F172A",
    subtext: "64748B",
    cardBg: "FFFFFF",
    border: "E2E8F0",
  },
}

function cleanHex(color: string | undefined, fallback: string): string {
  if (!color) return fallback
  const cleaned = color.replace(/^#/, "").trim()
  return cleaned.length === 6 ? cleaned.toUpperCase() : fallback
}

export async function exportToPowerPoint(presentation: GeneratedPresentation): Promise<void> {
  const pptxgenModule = await import("pptxgenjs")
  const PptxGen = (pptxgenModule.default || pptxgenModule) as any
  const pptx = new PptxGen()
  pptx.layout = "LAYOUT_16x9"
  pptx.title = presentation.title
  pptx.subject = presentation.topic

  const brandKit = presentation.brandKit
  const companyName = brandKit?.companyName || "OmniDome Analytics & AI"
  const companyTagline = brandKit?.tagline || "Autonomous Telecom Cloud OS"
  const logoUrl = brandKit?.logoUrl

  pptx.author = `${companyName} Intelligence`
  pptx.company = companyName

  // Resolve colors from brand palette or theme
  const brandPalette = brandKit?.palette
  const colors: ThemeColors = brandPalette
    ? {
        background: cleanHex(brandPalette.background, "0D1117"),
        primary: cleanHex(brandPalette.primary, "38BDF8"),
        accent: cleanHex(brandPalette.accent, "34D399"),
        text: cleanHex(brandPalette.text, "F0F6FC"),
        subtext: cleanHex(brandPalette.subtext, "8B949E"),
        cardBg: cleanHex(brandPalette.cardBg, "161B22"),
        border: cleanHex(brandPalette.border, "30363D"),
      }
    : THEME_CONFIGS[presentation.theme] || THEME_CONFIGS["dark-executive"]

  for (let i = 0; i < presentation.slides.length; i++) {
    const slideData = presentation.slides[i]
    const slide = pptx.addSlide()
    slide.background = { color: colors.background }

    // Speaker notes
    if (slideData.speakerNotes) {
      slide.addNotes(slideData.speakerNotes)
    }

    // Embed Brand Logo if provided
    let hasLogo = false
    if (logoUrl) {
      try {
        if (logoUrl.startsWith("data:")) {
          slide.addImage({
            data: logoUrl,
            x: 0.8,
            y: 0.32,
            w: 1.4,
            h: 0.45,
            sizing: { type: "contain" },
          })
          hasLogo = true
        } else if (logoUrl.startsWith("http") || logoUrl.startsWith("/")) {
          slide.addImage({
            path: logoUrl,
            x: 0.8,
            y: 0.32,
            w: 1.4,
            h: 0.45,
            sizing: { type: "contain" },
          })
          hasLogo = true
        }
      } catch (err) {
        console.warn("Could not embed brand logo in PPTX:", err)
      }
    }

    // Top branding banner text
    slide.addText(companyName.toUpperCase(), {
      x: hasLogo ? 2.3 : 0.8,
      y: 0.38,
      w: 7.5,
      h: 0.32,
      fontSize: 10,
      bold: true,
      color: colors.primary,
      fontFace: "Calibri",
    })

    if (slideData.category) {
      slide.addText(slideData.category.toUpperCase(), {
        x: 9.8,
        y: 0.38,
        w: 2.7,
        h: 0.32,
        fontSize: 9,
        align: "right",
        color: colors.accent,
        fontFace: "Calibri",
      })
    }

    if (slideData.layout === "title") {
      // Main Cover Slide
      let titleY = 2.0
      if (hasLogo && logoUrl) {
        try {
          slide.addImage({
            data: logoUrl.startsWith("data:") ? logoUrl : undefined,
            path: !logoUrl.startsWith("data:") ? logoUrl : undefined,
            x: 1.0,
            y: 1.2,
            w: 2.4,
            h: 0.7,
            sizing: { type: "contain" },
          })
          titleY = 2.1
        } catch {
          // ignore title logo error
        }
      }

      slide.addText(slideData.title, {
        x: 1.0,
        y: titleY,
        w: 11.3,
        h: 1.8,
        fontSize: 38,
        bold: true,
        color: colors.text,
        fontFace: "Arial",
      })

      if (slideData.subtitle) {
        slide.addText(slideData.subtitle, {
          x: 1.0,
          y: titleY + 1.9,
          w: 11.3,
          h: 0.9,
          fontSize: 18,
          color: colors.subtext,
          fontFace: "Calibri",
        })
      }

      // Metadata card at bottom
      slide.addShape(pptx.ShapeType.rect, {
        x: 1.0,
        y: 5.4,
        w: 11.3,
        h: 0.9,
        fill: { color: colors.cardBg },
        line: { color: colors.border, width: 1 },
      })

      slide.addText(`${companyName.toUpperCase()}${companyTagline ? `  •  ${companyTagline}` : ""}  |  Brand Architecture: ${brandKit?.voiceTone ? brandKit.voiceTone.toUpperCase() : "EXECUTIVE"}`, {
        x: 1.2,
        y: 5.55,
        w: 10.9,
        h: 0.35,
        fontSize: 10,
        bold: true,
        color: colors.primary,
        fontFace: "Calibri",
      })

      slide.addText(`Synthesized live from platform telemetry & active brand guidelines`, {
        x: 1.2,
        y: 5.9,
        w: 10.9,
        h: 0.3,
        fontSize: 9,
        color: colors.accent,
        fontFace: "Calibri",
      })
    } else {
      // Content Slide Header
      slide.addText(slideData.title, {
        x: 0.8,
        y: 0.85,
        w: 11.7,
        h: 0.75,
        fontSize: 24,
        bold: true,
        color: colors.text,
        fontFace: "Arial",
      })

      if (slideData.subtitle) {
        slide.addText(slideData.subtitle, {
          x: 0.8,
          y: 1.55,
          w: 11.7,
          h: 0.4,
          fontSize: 12,
          color: colors.subtext,
          fontFace: "Calibri",
        })
      }

      // Layout specific contents
      if (slideData.layout === "kpi-grid" && slideData.kpis && slideData.kpis.length > 0) {
        const kpis = slideData.kpis.slice(0, 4)
        const colWidth = 2.7
        const gap = 0.3
        const startX = 0.8

        kpis.forEach((kpi, kIdx) => {
          const cardX = startX + kIdx * (colWidth + gap)
          slide.addShape(pptx.ShapeType.roundRect, {
            x: cardX,
            y: 2.15,
            w: colWidth,
            h: 2.15,
            fill: { color: colors.cardBg },
            line: { color: colors.border, width: 1 },
            rectRadius: 0.1,
          })

          slide.addText(kpi.label, {
            x: cardX + 0.2,
            y: 2.3,
            w: colWidth - 0.4,
            h: 0.4,
            fontSize: 11,
            color: colors.subtext,
            fontFace: "Calibri",
          })

          slide.addText(kpi.value, {
            x: cardX + 0.2,
            y: 2.75,
            w: colWidth - 0.4,
            h: 0.7,
            fontSize: 24,
            bold: true,
            color: colors.primary,
            fontFace: "Arial",
          })

          if (kpi.change) {
            slide.addText(kpi.change, {
              x: cardX + 0.2,
              y: 3.55,
              w: colWidth - 0.4,
              h: 0.4,
              fontSize: 11,
              bold: true,
              color: kpi.isPositive ? colors.accent : "EF4444",
              fontFace: "Calibri",
            })
          }
        })

        // Bullets underneath KPIs
        if (slideData.bullets && slideData.bullets.length > 0) {
          const bulletsY = 4.6
          slideData.bullets.forEach((bullet, bIdx) => {
            slide.addText(`•  ${bullet}`, {
              x: 0.9,
              y: bulletsY + bIdx * 0.45,
              w: 11.5,
              h: 0.4,
              fontSize: 12,
              color: colors.text,
              fontFace: "Calibri",
            })
          })
        }
      } else if (slideData.bullets && slideData.bullets.length > 0) {
        // Bullet list layout
        const bulletStartY = 2.15
        slideData.bullets.forEach((bullet, bIdx) => {
          slide.addShape(pptx.ShapeType.roundRect, {
            x: 0.8,
            y: bulletStartY + bIdx * 0.85,
            w: 11.7,
            h: 0.7,
            fill: { color: colors.cardBg },
            line: { color: colors.border, width: 1 },
            rectRadius: 0.08,
          })

          slide.addText(`▸  ${bullet}`, {
            x: 1.1,
            y: bulletStartY + bIdx * 0.85 + 0.12,
            w: 11.1,
            h: 0.45,
            fontSize: 13,
            color: colors.text,
            fontFace: "Calibri",
          })
        })
      }

      // Takeaway Footer Card
      if (slideData.takeaway) {
        slide.addShape(pptx.ShapeType.rect, {
          x: 0.8,
          y: 6.35,
          w: 11.7,
          h: 0.55,
          fill: { color: colors.cardBg },
          line: { color: colors.accent, width: 1.5 },
        })

        slide.addText(`KEY TAKEAWAY: ${slideData.takeaway}`, {
          x: 1.0,
          y: 6.42,
          w: 11.3,
          h: 0.4,
          fontSize: 10,
          bold: true,
          color: colors.accent,
          fontFace: "Calibri",
        })
      }
    }

    // Slide Number & Brand Footer at bottom
    slide.addText(`CONFIDENTIAL  |  ${companyName.toUpperCase()}${companyTagline ? `  •  ${companyTagline}` : ""}`, {
      x: 0.8,
      y: 7.1,
      w: 9.5,
      h: 0.3,
      fontSize: 8,
      color: colors.subtext,
      fontFace: "Calibri",
    })

    slide.addText(`${i + 1} / ${presentation.slides.length}`, {
      x: 11.2,
      y: 7.1,
      w: 1.3,
      h: 0.3,
      fontSize: 9,
      align: "right",
      color: colors.subtext,
      fontFace: "Calibri",
    })
  }

  const filename = `${companyName.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${presentation.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.pptx`
  await pptx.writeFile({ fileName: filename })
}
