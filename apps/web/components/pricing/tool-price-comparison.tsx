import { catalog } from "@/lib/platform-pricing"

const tools = [
  { name: "HubSpot", free: "Free CRM and selected basic tools", paid: "Smart CRM Starter: from US$20 / seat / month", details: "HubSpot’s professional marketing plan starts at US$890 / month with 3 Core Seats. Marketing contacts and onboarding can add costs.", source: "https://legal.hubspot.com/hubspot-product-and-services-catalog" },
  { name: "Zoho Inventory", free: "50 orders, 1 user, 1 location", paid: "Standard: US$29 / organisation / month, billed annually", details: "An inventory product. Additional users, orders and locations are sold separately; local taxes are excluded.", source: "https://www.zoho.com/us/inventory/pricing/" },
  { name: "Shopify", free: "Trial offer; no permanent free Basic plan", paid: "Basic: US$39 / month, or US$29 / month billed annually", details: "An ecommerce storefront and checkout. Payment fees and optional apps can add costs; this is not an ISP operations suite.", source: "https://www.shopify.com/pricing" },
]

export function ToolPriceComparison() {
  return <section aria-labelledby="tool-price-comparison" className="space-y-5">
    <div>
      <h2 id="tool-price-comparison" className="text-2xl font-semibold">Compare prices with other tools</h2>
      <p className="mt-2 text-sm text-muted-foreground">Public list prices checked 11 October 2026. Products cover different needs; these are reference prices, not equivalent feature packages. Competitor prices remain in US dollars so exchange rates do not distort the comparison.</p>
    </div>
    <div className="grid gap-4 md:grid-cols-2">
      <article className="min-w-0 rounded-xl border border-primary/40 bg-card p-5">
        <h3 className="text-lg font-semibold">OmniDome</h3>
        <p className="mt-3 font-medium">Free: R0 software fee for 1 included seat</p>
        <p className="mt-2 text-sm">CRM, Services, Portal, Retention, Product and Stock, plus Overview and Admin.</p>
        <p className="mt-2 text-sm text-muted-foreground">{catalog.tier_limits.free.writes_per_month} successful writes per Free panel per UTC month and {catalog.bundles.starter.credits} shared AI credits per month. Advanced features and provider capacity are separate.</p>
        <p className="mt-3 font-medium">Growth: R{catalog.bundles.growth.monthly_price} / month for {catalog.bundles.growth.seats} included seats</p>
        <p className="mt-2 text-sm text-muted-foreground">Pricing and tax details are shown in the plan cards and checkout. Additional seats and higher panel tiers cost extra.</p>
      </article>
      {tools.map(tool => <article key={tool.name} className="min-w-0 rounded-xl border bg-card p-5">
        <h3 className="text-lg font-semibold">{tool.name}</h3>
        <p className="mt-3 text-sm">{tool.free}</p>
        <p className="mt-3 font-medium">{tool.paid}</p>
        <p className="mt-2 text-sm text-muted-foreground">{tool.details}</p>
        <a className="mt-4 inline-block text-sm text-primary underline underline-offset-4" href={tool.source} target="_blank" rel="noopener noreferrer">Official pricing and terms</a>
      </article>)}
    </div>
    <p className="text-xs text-muted-foreground">Promotions, local currency, taxes, contacts, seats, implementation and usage charges may change the final price. Check each supplier's current quote before buying.</p>
  </section>
}
