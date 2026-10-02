/**
 * RFC 4180 CSV building with spreadsheet formula-injection protection.
 * Pure (no browser imports) so node --test can load it.
 */

/** Characters that make Excel / Sheets evaluate a cell as a formula. */
const FORMULA_LEAD = /^(?:[\t\r\n]|\s*[=+\-@])/

/**
 * One cell -> CSV text. null/undefined -> empty. Cells starting with = + - @
 * tab or CR are prefixed with a single quote (neutralised), then the cell is
 * quoted when it contains a comma, double quote, CR or LF; embedded quotes are
 * doubled. Negative numbers are real numbers, not formulas: they are left alone.
 */
export function csvCell(value: unknown): string {
  if (value === null || value === undefined) return ""
  let s: string
  if (typeof value === "number") {
    // Numbers are data, not formulas ("-5" must stay "-5").
    return Number.isFinite(value) ? String(value) : ""
  }
  if (value instanceof Date) s = Number.isNaN(value.getTime()) ? "" : value.toISOString()
  else if (typeof value === "object") {
    try {
      s = JSON.stringify(value)
    } catch {
      s = String(value)
    }
  } else s = String(value)
  if (FORMULA_LEAD.test(s)) s = `'${s}`
  if (/[",\r\n]/.test(s)) s = `"${s.replace(/"/g, '""')}"`
  return s
}

/** UTF-8 BOM so Excel reads non-ASCII (R, accents) correctly. */
export const CSV_BOM = "﻿"

/** headers + rows -> CSV text with BOM and CRLF line endings (RFC 4180). */
export function buildCsv(headers: unknown[], rows: unknown[][]): string {
  const lines = [headers.map(csvCell).join(","), ...rows.map((r) => r.map(csvCell).join(","))]
  return CSV_BOM + lines.join("\r\n") + "\r\n"
}
