/**
 * Decimal-safe money helpers for the billing and finance screens.
 *
 * The services send money as JSON strings (Decimal) or floats. Summing floats
 * directly drifts (0.1 + 0.2), so values are converted to integer cents first and
 * only formatted at the edge. Pure and dependency-free so node --test can load it.
 *
 *   fmtMoney("1234.5")  -> "R 1 234,50"
 *   fmtMoney(-5)        -> "-R 5,00"
 *   fmtMoney(null)      -> "—"
 */

const DECIMAL_RE = /^(-?)(\d+)(?:\.(\d+))?$/

/** Integer cents for a number or decimal string; null when it is not a finite amount. */
export function toCents(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? toCents(String(v)) : null
  if (typeof v !== "string") return null
  const m = DECIMAL_RE.exec(v.trim())
  if (!m) return null
  const [, sign, whole, frac = ""] = m
  const padded = (frac + "00").slice(0, 3)
  let cents = Number(whole) * 100 + Number(padded.slice(0, 2))
  if (Number(padded[2]) >= 5) cents += 1 // round half up on the third decimal
  return Number.isSafeInteger(cents) ? (sign ? -cents : cents) : null
}

/** Sum of the amounts in integer cents; unparseable values are ignored. */
export function sumCents(values: Array<unknown>): number {
  let t = 0
  for (const v of values) {
    const c = toCents(v)
    if (c !== null) t += c
    if (!Number.isSafeInteger(t)) return NaN
  }
  return t
}

function groupThousands(intStr: string): string {
  return intStr.replace(/\B(?=(\d{3})+(?!\d))/g, " ")
}

export function fmtCents(cents: number | null): string {
  if (cents === null || !Number.isSafeInteger(cents)) return "—"
  const abs = Math.abs(Math.round(cents))
  const rand = Math.floor(abs / 100)
  const rem = String(abs % 100).padStart(2, "0")
  const sign = cents < 0 && abs !== 0 ? "-" : ""
  return `${sign}R ${groupThousands(String(rand))},${rem}`
}

export function fmtMoney(v: unknown): string {
  return fmtCents(toCents(v))
}

/** Two amounts are equal to the cent. */
export function sameCents(a: unknown, b: unknown): boolean {
  const x = toCents(a)
  const y = toCents(b)
  return x !== null && y !== null && x === y
}
