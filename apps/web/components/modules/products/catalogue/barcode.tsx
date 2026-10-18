"use client"

import type { ReactElement } from "react"
import { Printer } from "lucide-react"
import { Button } from "@/components/ui/button"

// ── EAN-13 ───────────────────────────────────────────────────────────────────
const L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
const G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
const R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
const PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]

export function ean13Valid(code: string): boolean {
  if (!/^\d{13}$/.test(code)) return false
  const sum = code.slice(0, 12).split("").reduce((s, c, i) => s + Number(c) * (i % 2 ? 3 : 1), 0)
  return (10 - (sum % 10)) % 10 === Number(code[12])
}

function ean13Bits(code: string): string {
  const parity = PARITY[Number(code[0])]
  let bits = "101"
  for (let i = 0; i < 6; i++) bits += (parity[i] === "L" ? L : G)[Number(code[i + 1])]
  bits += "01010"
  for (let i = 0; i < 6; i++) bits += R[Number(code[i + 7])]
  return bits + "101"
}

// ── Code 128 (subset B: printable ASCII) ─────────────────────────────────────
const C128 = [
  "11011001100", "11001101100", "11001100110", "10010011000", "10010001100", "10001001100", "10011001000", "10011000100", "10001100100", "11001001000",
  "11001000100", "11000100100", "10110011100", "10011011100", "10011001110", "10111001100", "10011101100", "10011100110", "11001110010", "11001011100",
  "11001001110", "11011100100", "11001110100", "11101101110", "11101001100", "11100101100", "11100100110", "11101100100", "11100110100", "11100110010",
  "11011011000", "11011000110", "11000110110", "10100011000", "10001011000", "10001000110", "10110001000", "10001101000", "10001100010", "11010001000",
  "11000101000", "11000100010", "10110111000", "10110001110", "10001101110", "10111011000", "10111000110", "10001110110", "11101110110", "11010001110",
  "11000101110", "11011101000", "11011100010", "11011101110", "11101011000", "11101000110", "11100010110", "11101101000", "11101100010", "11100011010",
  "11101111010", "11001000010", "11110001010", "10100110000", "10100001100", "10010110000", "10010000110", "10000101100", "10000100110", "10110010000",
  "10110000100", "10011010000", "10011000010", "10000110100", "10000110010", "11000010010", "11001010000", "11110111010", "11000010100", "10001111010",
  "10100111100", "10010111100", "10010011110", "10111100100", "10011110100", "10011110010", "11110100100", "11110010100", "11110010010", "11011011110",
  "11011110110", "11110110110", "10101111000", "10100011110", "10001011110", "10111101000", "10111100010", "11110101000", "11110100010", "10111011110",
  "10111101110", "11101011110", "11110101110", "11010000100", "11010010000", "11010011100",
]
const STOP = "1100011101011"

function code128Bits(text: string): string | null {
  if (!text || /[^\x20-\x7e]/.test(text)) return null
  const values = [104, ...text.split("").map((c) => c.charCodeAt(0) - 32)]
  const check = values.reduce((s, v, i) => s + v * (i === 0 ? 1 : i), 0) % 103
  return [...values, check].map((v) => C128[v]).join("") + STOP
}

/** Scannable barcode as inline SVG, so it prints crisply at any size. Returns nothing for a value it cannot encode. */
export function BarcodeSvg({ value, format, height = 70 }: { value: string; format: "EAN-13" | "Code 128" | "None"; height?: number }) {
  const bits = format === "EAN-13" && ean13Valid(value) ? ean13Bits(value) : format === "Code 128" ? code128Bits(value) : null
  if (!bits) return <p className="text-xs text-muted-foreground">No barcode yet.</p>
  const quiet = 11
  const width = bits.length + quiet * 2
  const bars: ReactElement[] = []
  let i = 0
  while (i < bits.length) {
    if (bits[i] === "1") {
      let j = i
      while (j < bits.length && bits[j] === "1") j++
      bars.push(<rect key={i} x={i + quiet} y={0} width={j - i} height={height} fill="#000" />)
      i = j
    } else i++
  }
  return (
    <svg viewBox={`0 0 ${width} ${height + 14}`} role="img" aria-label={`Barcode ${value}`} className="h-24 w-auto max-w-full rounded bg-white p-1">
      {bars}
      <text x={width / 2} y={height + 11} textAnchor="middle" fontSize="9" fontFamily="monospace" fill="#000">{value}</text>
    </svg>
  )
}

/** Opens a print dialog with just the label (product number, name, barcode) at a sensible size. */
export function printBarcodeLabel(name: string, number: string, svgHost: HTMLElement | null) {
  const svg = svgHost?.querySelector("svg")
  if (!svg) return
  const w = window.open("", "_blank", "width=420,height=320")
  if (!w) return
  const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string))
  w.document.write(`<!doctype html><title>${esc(number)}</title><body style="font:12px sans-serif;margin:12px;text-align:center"><div style="font-weight:600">${esc(name)}</div><div style="color:#555;margin-bottom:6px">${esc(number)}</div>${svg.outerHTML.replace("h-24", "")}</body>`)
  w.document.close()
  w.focus()
  w.print()
}

export function PrintLabelButton({ name, number, host }: { name: string; number: string; host: () => HTMLElement | null }) {
  return (
    <Button type="button" variant="outline" size="sm" className="h-8 gap-1.5 text-xs" onClick={() => printBarcodeLabel(name, number, host())}>
      <Printer className="h-3.5 w-3.5" /> Print label
    </Button>
  )
}
