import type { PlatformQuote } from "@/lib/platform-pricing"

const zar = (v: string | number) => Number(v).toLocaleString("en-ZA", { style: "currency", currency: "ZAR" })

/** Subtotal / VAT / total block for an OmniDome quote or invoice. Amounts come straight from the quote. */
export function QuoteSummation({ quote }: { quote: Pick<PlatformQuote, "net_zar" | "vat_zar" | "total_zar" | "vat_registered" | "prices_include_vat" | "vat_rate"> }) {
  if (!quote.vat_registered) return <div className="text-sm"><div className="flex justify-between gap-6 font-semibold"><span>Total</span><span>{zar(quote.total_zar)}</span></div></div>
  const pct = quote.vat_rate !== undefined && quote.vat_rate !== null ? Number((Number(quote.vat_rate) * 100).toFixed(2)) : 15
  if (quote.prices_include_vat) return <div className="text-sm"><div className="flex justify-between gap-6 font-semibold"><span>Total</span><span>{zar(quote.total_zar)}</span></div><p className="text-xs text-muted-foreground">Includes VAT {zar(quote.vat_zar)}</p></div>
  return <div className="space-y-0.5 text-sm" aria-label="Invoice summation">
    <div className="flex justify-between gap-6"><span>Subtotal (excl. VAT)</span><span>{zar(quote.net_zar)}</span></div>
    <div className="flex justify-between gap-6"><span>VAT {pct}%</span><span>{zar(quote.vat_zar)}</span></div>
    <div className="flex justify-between gap-6 border-t pt-0.5 font-semibold"><span>Total (incl. VAT)</span><span>{zar(quote.total_zar)}</span></div>
  </div>
}
