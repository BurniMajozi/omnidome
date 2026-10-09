import type { BrandKit, BrandPalette, DeckTheme } from "@/lib/bi-studio-api"

export interface Theme {
  palette: BrandPalette
  fonts: { heading: string; body: string }
  footer_text: string
  slide_numbers: boolean
  company_name: string
  logo_data_url: string | null
  show_logo: boolean
  logo_position: string
  title_align: "left" | "center" | "right"
}

export const DEFAULT_PALETTE: BrandPalette = {
  primary: "#0B5FFF",
  secondary: "#1F2A44",
  accent: "#F5A623",
  background: "#FFFFFF",
  text: "#1B1F2A",
  chart: ["#0B5FFF", "#F5A623", "#2BB673", "#E5484D", "#8E4EC6", "#12A594"],
}

const HEX = /^#[0-9a-fA-F]{6}$/
export const isHex = (s: unknown): s is string => typeof s === "string" && HEX.test(s)

export function mergeTheme(kit: BrandKit | null | undefined, over?: DeckTheme | null): Theme {
  const k = kit?.palette
  const o = over?.palette ?? {}
  const pick = (key: Exclude<keyof BrandPalette, "chart">): string => {
    const cand = [o[key], k?.[key], DEFAULT_PALETTE[key]]
    return cand.find(isHex) ?? DEFAULT_PALETTE[key]
  }
  const chartSrc = (o.chart && o.chart.length ? o.chart : k?.chart && k.chart.length ? k.chart : DEFAULT_PALETTE.chart).filter(isHex)
  const lp = kit?.layout_prefs
  return {
    palette: {
      primary: pick("primary"),
      secondary: pick("secondary"),
      accent: pick("accent"),
      background: pick("background"),
      text: pick("text"),
      chart: chartSrc.length ? chartSrc : DEFAULT_PALETTE.chart,
    },
    fonts: {
      heading: over?.fonts?.heading ?? kit?.fonts?.heading ?? "Calibri",
      body: over?.fonts?.body ?? kit?.fonts?.body ?? "Calibri",
    },
    footer_text: over?.footer_text ?? kit?.footer_text ?? "",
    slide_numbers: over?.slide_numbers ?? kit?.slide_numbers ?? true,
    company_name: kit?.company_name ?? "",
    logo_data_url: kit?.logo_data_url ?? null,
    show_logo: lp?.show_logo ?? true,
    logo_position: lp?.logo_position ?? "top_right",
    title_align: (["left", "center", "right"].includes(lp?.title_align ?? "") ? lp?.title_align : "left") as Theme["title_align"],
  }
}

const SERIF = new Set(["Georgia", "Cambria", "Times New Roman"])
/** CSS font stack: the brand font first, then a safe generic family. */
export function fontStack(name: string): string {
  const safe = name.replace(/[^A-Za-z0-9 \-]/g, "")
  return `"${safe}", ${SERIF.has(safe) ? "Georgia, serif" : "system-ui, -apple-system, 'Segoe UI', Arial, sans-serif"}`
}

/** Readable text colour on a solid fill. */
export function onColor(hex: string): string {
  if (!isHex(hex)) return "#FFFFFF"
  const n = parseInt(hex.slice(1), 16)
  const l = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255
  return l > 0.6 ? "#111111" : "#FFFFFF"
}

export function shapeColor(theme: Theme, c: string | undefined): string {
  if (!c) return theme.palette.accent
  if (isHex(c)) return c
  if (c in theme.palette && c !== "chart") return theme.palette[c as Exclude<keyof BrandPalette, "chart">]
  return theme.palette.accent
}

/** Only https image URLs are ever rendered. */
export function safeImageUrl(u: unknown): string | null {
  if (typeof u !== "string") return null
  try {
    const p = new URL(u)
    return p.protocol === "https:" ? p.toString() : null
  } catch {
    return null
  }
}
export function safeDataImage(u: unknown): string | null {
  return typeof u === "string" && /^data:image\/(png|jpeg|svg\+xml);base64,[A-Za-z0-9+/=]+$/.test(u) ? u : null
}
