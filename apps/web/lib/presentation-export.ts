import pptxgen from "pptxgenjs"

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

export interface GeneratedPresentation {
  id: string
  title: string
  topic: string
  theme: "dark-executive" | "indigo-cyber" | "emerald-clean" | "light-corporate"
  created_at: string
  slides: PresentationSlide[]
  rawDataSummary?: string
}

interface ThemeColors {
  background: string
  primary: string
  accent: string
  text: string
  subtext: string
  cardBg: string
  border: string
}

const THEME_CONFIGS: Record<GeneratedPresentation["theme"], ThemeColors> = {
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

export async function exportToPowerPoint(presentation: GeneratedPresentation): Promise<void> {
  const pptx = new pptxgen()
  pptx.layout = "LAYOUT_16x9"
  pptx.title = presentation.title
  pptx.subject = presentation.topic
  pptx.author = "OmniDome Analytics & AI"
  pptx.company = "OmniDome Executive Intelligence"

  const colors = THEME_CONFIGS[presentation.theme] || THEME_CONFIGS["dark-executive"]

  for (let i = 0; i < presentation.slides.length; i++) {
    const slideData = presentation.slides[i]
    const slide = pptx.addSlide()
    slide.background = { color: colors.background }

    // Speaker notes
    if (slideData.speakerNotes) {
      slide.addNotes(slideData.speakerNotes)
    }

    // Top branding badge
    slide.addText("OMNIDOME ANALYTICS & AI PLATFORM", {
      x: 0.8,
      y: 0.4,
      w: 8.0,
      h: 0.3,
      fontSize: 10,
      bold: true,
      color: colors.primary,
      fontFace: "Calibri",
    })

    if (slideData.category) {
      slide.addText(slideData.category.toUpperCase(), {
        x: 10.0,
        y: 0.4,
        w: 2.5,
        h: 0.3,
        fontSize: 9,
        align: "right",
        color: colors.accent,
        fontFace: "Calibri",
      })
    }

    if (slideData.layout === "title") {
      // Main Cover Slide
      slide.addText(slideData.title, {
        x: 1.0,
        y: 2.2,
        w: 11.3,
        h: 1.8,
        fontSize: 40,
        bold: true,
        color: colors.text,
        fontFace: "Arial",
      })

      if (slideData.subtitle) {
        slide.addText(slideData.subtitle, {
          x: 1.0,
          y: 4.1,
          w: 11.3,
          h: 1.0,
          fontSize: 20,
          color: colors.subtext,
          fontFace: "Calibri",
        })
      }

      // Metadata card at bottom
      slide.addShape(pptx.ShapeType.rect, {
        x: 1.0,
        y: 5.5,
        w: 11.3,
        h: 0.8,
        fill: { color: colors.cardBg },
        line: { color: colors.border, width: 1 },
      })

      slide.addText(`Generated on the fly from live OmniDome Platform Telemetry  |  Data Scope: Cross-Module Intelligence`, {
        x: 1.2,
        y: 5.7,
        w: 10.9,
        h: 0.4,
        fontSize: 11,
        color: colors.accent,
        fontFace: "Calibri",
      })
    } else {
      // Content Slide Header
      slide.addText(slideData.title, {
        x: 0.8,
        y: 0.8,
        w: 11.7,
        h: 0.8,
        fontSize: 26,
        bold: true,
        color: colors.text,
        fontFace: "Arial",
      })

      if (slideData.subtitle) {
        slide.addText(slideData.subtitle, {
          x: 0.8,
          y: 1.5,
          w: 11.7,
          h: 0.4,
          fontSize: 13,
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
          // KPI background card
          slide.addShape(pptx.ShapeType.roundRect, {
            x: cardX,
            y: 2.2,
            w: colWidth,
            h: 2.2,
            fill: { color: colors.cardBg },
            line: { color: colors.border, width: 1 },
            rectRadius: 0.1,
          })

          slide.addText(kpi.label, {
            x: cardX + 0.2,
            y: 2.4,
            w: colWidth - 0.4,
            h: 0.4,
            fontSize: 12,
            color: colors.subtext,
            fontFace: "Calibri",
          })

          slide.addText(kpi.value, {
            x: cardX + 0.2,
            y: 2.9,
            w: colWidth - 0.4,
            h: 0.7,
            fontSize: 26,
            bold: true,
            color: colors.primary,
            fontFace: "Arial",
          })

          if (kpi.change) {
            slide.addText(kpi.change, {
              x: cardX + 0.2,
              y: 3.7,
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
          const bulletsY = 4.7
          slideData.bullets.forEach((bullet, bIdx) => {
            slide.addText(`•  ${bullet}`, {
              x: 0.9,
              y: bulletsY + bIdx * 0.45,
              w: 11.5,
              h: 0.4,
              fontSize: 13,
              color: colors.text,
              fontFace: "Calibri",
            })
          })
        }
      } else if (slideData.bullets && slideData.bullets.length > 0) {
        // Bullet list layout
        const bulletStartY = 2.2
        slideData.bullets.forEach((bullet, bIdx) => {
          slide.addShape(pptx.ShapeType.roundRect, {
            x: 0.8,
            y: bulletStartY + bIdx * 0.9,
            w: 11.7,
            h: 0.75,
            fill: { color: colors.cardBg },
            line: { color: colors.border, width: 1 },
            rectRadius: 0.08,
          })

          slide.addText(`▸  ${bullet}`, {
            x: 1.1,
            y: bulletStartY + bIdx * 0.9 + 0.15,
            w: 11.1,
            h: 0.45,
            fontSize: 14,
            color: colors.text,
            fontFace: "Calibri",
          })
        })
      }

      // Takeaway Footer Card
      if (slideData.takeaway) {
        slide.addShape(pptx.ShapeType.rect, {
          x: 0.8,
          y: 6.4,
          w: 11.7,
          h: 0.55,
          fill: { color: colors.cardBg },
          line: { color: colors.accent, width: 1.5 },
        })

        slide.addText(`KEY TAKEAWAY: ${slideData.takeaway}`, {
          x: 1.0,
          y: 6.48,
          w: 11.3,
          h: 0.4,
          fontSize: 11,
          bold: true,
          color: colors.accent,
          fontFace: "Calibri",
        })
      }
    }

    // Slide Number at bottom right
    slide.addText(`${i + 1} / ${presentation.slides.length}`, {
      x: 11.5,
      y: 7.1,
      w: 1.0,
      h: 0.3,
      fontSize: 9,
      align: "right",
      color: colors.subtext,
      fontFace: "Calibri",
    })
  }

  const filename = `${presentation.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.pptx`
  await pptx.writeFile({ fileName: filename })
}
