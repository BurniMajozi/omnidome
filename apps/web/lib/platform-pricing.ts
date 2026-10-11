import catalog from "./platform-pricing.json"
export { catalog }
export function discountedPrice(price:number,annual:boolean) {
  const [whole,fraction=""] = String(price).split(".")
  const cents = Number(whole)*100+Number(fraction.padEnd(2,"0").slice(0,2))
  return Math.floor((cents*(annual ? 100-catalog.annual_discount_percent : 100)+50)/100)/100
}
export type PricingTier = "starter" | "professional" | "enterprise"
export type UsagePolicy = {version:number;mode:string;status:string;monthly_credits:number;rates:Record<string,number>;token_block:number;hosting:Record<string,number|null>;communications:string;legacy?:boolean}
export type CreditPolicy = {enabled:boolean;price_per_credit_zar:string|null;minimum_zar?:string;operation_credit_limit:number}
export type UsageLog = {id:string;panel:string;kind:string;credits:number;measured_credits?:number;reserved_credits?:number;status:string;started_at:string;completed_at?:string|null}
export type UsageLogs = {total:number;limit:number;offset:number;rows:UsageLog[]}
export type DeliveryControl = {mode:"prepaid"|"auto_recharge";recharge_zar:number;monthly_cap_zar:number}
export type DeliveryControls = {preferences:{voice:DeliveryControl;email:DeliveryControl};capabilities:Record<"voice"|"email",{prepaid_enforced:boolean;auto_recharge_active:boolean;reason:string}>}
export type TenantUsage = {policy:UsagePolicy;panel_usage?:{module:string;used:number;config:{pricing_tier:string;writes_per_month:number}}[];period_start:string;period_end:string;used:number;remaining:number;running:number;source:string;charges_enabled:boolean;entitlement_authority:string;autumn_sync_enabled:boolean;sync:{status:string;error_code?:string;attempts:number}|null;recent:UsageLog[];credit_wallet?:{purchased_remaining:number;reserved:number;available:number;topup_policy:CreditPolicy};by_panel?:{panel:string;operations:number;credits:number;running:number}[]}
export type ProviderRateCard = {status:string;reviewed_at:string;limitation:string;assumptions:{usd_zar:number;fx_buffer:number;target_margin:number};rates:{id:string;name:string;provider:string;unit:string;price_zar:number;minimum_net_zar:string;scenario_margin_percent:string;meets_target:boolean;source:string;note:string}[]}
export type TenantCosts = {window_days:number;margin_available:boolean;margin_reason:string;draft_rate_card?:ProviderRateCard;costs:{category:string;provider:string;currency:string;source:string;events:number;quantity:string;unit:string;amount:string|null}[]}
export type PricingSelection = { bundle?: string | null; modules: Record<string, PricingTier>; period: "monthly" | "annually"; seats?: number }
export type PlatformQuote = { selection: PricingSelection; name: string; seats: number; period: string; entitlements: string[]; manual_panels?: string[]; usage_policy?: UsagePolicy; net_zar: string; vat_zar: string; total_zar: string; monthly_net_zar: string; monthly_display_zar?:string; vat_registered?:boolean; prices_include_vat?:boolean; amount_cents: number; currency: string; credit_topup?:{credits:number;expires_at:string|null;unit_total_zar:string}; proration?: {unused_net_credit:string;credit_applied:string;credit_remaining:string;valid_until:string}; lines: { description: string; quantity: number; net_zar: string }[] }
export type CreditTopupQuote = Omit<PlatformQuote,"selection"|"monthly_net_zar"|"usage_policy"|"proration"> & {credit_topup:{credits:number;expires_at:string|null;unit_total_zar:string}}
export type PlatformOrder = { id: string; reference: string; tenant_id: string; status: string; intent: string; quote: PlatformQuote|CreditTopupQuote; created_at: string; subscription_status?:string|null }
export type PlatformInvoices = {total:number;limit:number;offset:number;rows:PlatformOrder[]}
export type PlatformPricingState = { pricing: { selection?: PricingSelection; quote?: PlatformQuote; active_quote?:PlatformQuote;period_end?:string;billing_mode?:string;credit_net_zar?:string;provisioned?: boolean }; orders: PlatformOrder[]; subscription?: { status: string; order_id: string } | null }
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
