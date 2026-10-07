/**
 * Client-side totals for the line editor. PREVIEW ONLY: the server recomputes every
 * figure (qty*price, discount amount|percent, per-line half-up VAT) and its numbers
 * are authoritative. Integer cents internally to avoid float drift.
 */
import type { LineInput } from "@/lib/invoicing-api"

export interface EditableLine {
  key: string
  description: string
  quantity: string
  unit_price: string
  discount: string
  discount_type: "amount" | "percent"
  tax_rate: string
  catalog_item_id: string | null
}

/** The server's default VAT is configurable; the preview assumes this when a line leaves VAT blank. */
export const ASSUMED_DEFAULT_VAT = 15

let seq = 0
export const newKey = () => `l${Date.now().toString(36)}${(seq++).toString(36)}`

export const blankLine = (): EditableLine => ({
  key: newKey(),
  description: "",
  quantity: "1",
  unit_price: "",
  discount: "",
  discount_type: "amount",
  tax_rate: "",
  catalog_item_id: null,
})

const n = (v: string): number => {
  const x = Number(String(v ?? "").trim().replace(",", "."))
  return Number.isFinite(x) ? x : 0
}
const cents = (x: number) => Math.round(x * 100)

export interface LineCalc {
  gross: number
  discount: number
  net: number
  vat: number
  total: number
}
/** All values in cents. */
export function calcLine(l: EditableLine): LineCalc {
  const gross = cents(n(l.quantity) * n(l.unit_price))
  const rawDisc = l.discount_type === "percent" ? Math.round((gross * n(l.discount)) / 100) : cents(n(l.discount))
  const discount = Math.max(0, Math.min(gross, rawDisc))
  const net = gross - discount
  const rate = l.tax_rate.trim() === "" ? ASSUMED_DEFAULT_VAT : n(l.tax_rate)
  const vat = Math.round((net * rate) / 100)
  return { gross, discount, net, vat, total: net + vat }
}

export function calcTotals(lines: EditableLine[]) {
  let subtotal = 0
  let discount = 0
  let vat = 0
  for (const l of lines) {
    const c = calcLine(l)
    subtotal += c.net
    discount += c.discount
    vat += c.vat
  }
  return { subtotal, discount, vat, total: subtotal + vat }
}

export const centsToMoney = (c: number) => (c / 100).toFixed(2)

/** Lines the server would accept: blank rows are dropped. */
export function toLineInputs(lines: EditableLine[]): LineInput[] {
  return lines
    .filter((l) => l.description.trim() !== "" || n(l.unit_price) !== 0)
    .map((l) => ({
      description: l.description.trim(),
      quantity: l.quantity.trim() || "1",
      unit_price: l.unit_price.trim() || "0",
      ...(l.discount.trim() ? { discount: l.discount.trim(), discount_type: l.discount_type } : {}),
      ...(l.tax_rate.trim() ? { tax_rate: l.tax_rate.trim() } : {}),
      ...(l.catalog_item_id ? { catalog_item_id: l.catalog_item_id } : {}),
    }))
}

/** Server stored lines -> editable rows. Percent discounts are stored as amounts, so they come back as amounts. */
export function fromServerLines(
  lines: Array<{ description: string; quantity: string | number; unit_price_zar?: string | number; discount_zar?: string; tax_rate?: string | number; catalog_item_id?: string | null }> | undefined,
): EditableLine[] {
  if (!lines || lines.length === 0) return []
  return lines.map((l) => ({
    key: newKey(),
    description: l.description ?? "",
    quantity: String(l.quantity ?? "1"),
    unit_price: String(l.unit_price_zar ?? ""),
    discount: l.discount_zar && Number(l.discount_zar) !== 0 ? String(l.discount_zar) : "",
    discount_type: "amount",
    tax_rate: l.tax_rate === undefined || l.tax_rate === null ? "" : String(l.tax_rate),
    catalog_item_id: l.catalog_item_id ?? null,
  }))
}
