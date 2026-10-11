import catalog from "./platform-pricing.json"
export { catalog }
export type PricingTier = "starter" | "professional" | "enterprise"
export type UsagePolicy = {version:number;mode:string;status:string;monthly_credits:number;rates:Record<string,number>;token_block:number;hosting:Record<string,number|null>;communications:string;legacy?:boolean}
export type TenantUsage = {policy:UsagePolicy;period_start:string;period_end:string;used:number;remaining:number;running:number;source:string;charges_enabled:boolean;sync:{status:string;error_code?:string;attempts:number}|null;recent:{id:string;kind:string;credits:number;status:string;started_at:string}[]}
export type ProviderRateCard = {status:string;reviewed_at:string;limitation:string;assumptions:{usd_zar:number;fx_buffer:number;target_margin:number};rates:{id:string;name:string;provider:string;unit:string;price_zar:number;minimum_net_zar:string;scenario_margin_percent:string;meets_target:boolean;source:string;note:string}[]}
export type TenantCosts = {window_days:number;margin_available:boolean;margin_reason:string;draft_rate_card?:ProviderRateCard;costs:{category:string;provider:string;currency:string;source:string;events:number;quantity:string;unit:string;amount:string|null}[]}
export type PricingSelection = { bundle?: string | null; modules: Record<string, PricingTier>; period: "monthly" | "annually"; seats?: number }
export type PlatformQuote = { selection: PricingSelection; name: string; seats: number; period: string; entitlements: string[]; manual_panels?: string[]; usage_policy?: UsagePolicy; net_zar: string; vat_zar: string; total_zar: string; monthly_net_zar: string; amount_cents: number; currency: string; lines: { description: string; quantity: number; net_zar: string }[] }
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
