import catalog from "./platform-pricing.json"
export { catalog }
export type PricingTier = "starter" | "professional" | "enterprise"
export type PricingSelection = { bundle?: string | null; modules: Record<string, PricingTier>; period: "monthly" | "annually"; seats?: number }
export type PlatformQuote = { selection: PricingSelection; name: string; seats: number; period: string; entitlements: string[]; manual_panels?: string[]; net_zar: string; vat_zar: string; total_zar: string; monthly_net_zar: string; amount_cents: number; currency: string; lines: { description: string; quantity: number; net_zar: string }[] }
export type PlatformOrder = { id: string; reference: string; tenant_id: string; status: string; intent: string; quote: PlatformQuote; created_at: string }
export type PlatformPricingState = { pricing: { selection?: PricingSelection; quote?: PlatformQuote; provisioned?: boolean }; orders: PlatformOrder[]; subscription?: { status: string; order_id: string } | null }
export const defaultSelection: PricingSelection = { bundle: "professional", modules: {}, period: "monthly", seats: 6 }
export const canonicalModule = (id: string) => catalog.modules.find(m => m.page_id === id || m.id === id)?.id || id
export function bundleSelection(id: string, period: "monthly" | "annually"): PricingSelection {
  const bundle = catalog.bundles[id as keyof typeof catalog.bundles]
  return { bundle: id, modules: {}, period, seats: bundle?.seats || 1 }
}
export function selectedPanels(selection: PricingSelection): Record<string, PricingTier> {
  const bundle = catalog.bundles[selection.bundle as keyof typeof catalog.bundles]
  return { ...(bundle ? Object.fromEntries(bundle.modules.map(m => [m, bundle.tier as PricingTier])) : {}), ...selection.modules }
}
export function startCheckout(selection: PricingSelection) {
  localStorage.setItem("omnidome.pricing.selection", JSON.stringify(selection))
  window.location.assign("/checkout")
}
