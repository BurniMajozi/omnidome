/**
 * Shared ZAR formatting for the Overview (tiles, tooltips, axes).
 * Pure and dependency-free so node --test can load it. Independent of the
 * machine locale/ICU: grouping is done by hand with a plain space.
 *
 *   fmtZar(135382)        -> "R 135 382"   full value, space thousands
 *   fmtZarCompact(5496)   -> "R5,5k"       only where space is tight (axes)
 *   fmtZarCompact(1234567)-> "R1,2M"
 */

function group(intStr: string): string {
  return intStr.replace(/\B(?=(\d{3})+(?!\d))/g, " ")
}

/** Full rand amount, rounded to whole rand. Non-finite input renders as a dash. */
export function fmtZar(n: number): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—"
  const r = Math.round(Math.abs(n))
  const sign = n < 0 && r !== 0 ? "-" : ""
  return `${sign}R ${group(String(r))}`
}

function oneDecimal(x: number): string {
  // 1 decimal, comma separator, drop a trailing ",0".
  return (Math.round(x * 10) / 10).toFixed(1).replace(/\.0$/, "").replace(".", ",")
}

/**
 * Compact rand amount for tight spaces (chart axes, small tiles). Always keeps
 * one decimal so 5 496 reads "R5,5k" (never "R5k"), and never emits "R1000k":
 * a value that rounds up to 1000k is shown in millions.
 */
export function fmtZarCompact(n: number): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—"
  const abs = Math.abs(n)
  const sign = n < 0 ? "-" : ""
  if (abs < 1_000) return `${sign}R${Math.round(abs)}`
  const k = Math.round((abs / 1_000) * 10) / 10
  if (k < 1_000) return `${sign}R${oneDecimal(k)}k`
  const m = abs / 1_000_000
  if (m < 1_000) return `${sign}R${oneDecimal(m)}M`
  return `${sign}R${group(String(Math.round(m)))}M`
}
