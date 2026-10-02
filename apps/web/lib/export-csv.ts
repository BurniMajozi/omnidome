/**
 * CSV export for the billing/finance tables. Spreadsheet-safe: a text cell that
 * starts with = + - @ (or tab / CR) is prefixed with a single quote so Excel and
 * Sheets treat it as text, not a formula. Real numbers are left alone (a negative
 * amount stays "-5"). Pure so node --test can load it; downloadCsv is browser-only.
 */

export const EXPORT_BOM = "﻿"

export function exportCell(value: unknown): string {
  if (value === null || value === undefined) return ""
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : ""
  let s = String(value)
  if (/^(?:[\t\r\n]|\s*[=+\-@])/.test(s)) s = `'${s}`
  if (/[",\r\n]/.test(s)) s = `"${s.replace(/"/g, '""')}"`
  return s
}

/** Header row + data rows, CRLF separated, with a BOM so Excel reads UTF-8. */
export function toCsv(headers: string[], rows: Array<Array<unknown>>, withBom = true): string {
  const lines = [headers, ...rows].map((r) => r.map(exportCell).join(","))
  return (withBom ? EXPORT_BOM : "") + lines.join("\r\n") + "\r\n"
}

/** Trigger a browser download. No-op without a DOM. */
export function downloadCsv(filename: string, csv: string): void {
  if (typeof document === "undefined") return
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
