"use client"

import { useCallback, useEffect, useState } from "react"
import { Loader2, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { inventoryCall } from "@/lib/catalogue-api"
import { money } from "./catalogue/shared"

interface Batch {
  id: string; product_number: string; name: string; origin: "receipt" | "issue"; reference: string; quantity: number; unit_cost: number
  life_months: number; in_service: string; depreciated_months: number; accumulated: number; net_book_value: number; monthly: number; status: string
}

/** Company assets and equipment given to customers, with what they are still worth and what posts to finance each month. */
export function EquipmentRegister() {
  const [rows, setRows] = useState<Batch[] | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => inventoryCall<Batch[]>("/catalogue/assets").then((r) => { setRows(r); setError("") }).catch((e) => setError(e instanceof Error ? e.message : "Could not load the register")), [])
  useEffect(() => { void load() }, [load])

  async function runNow() {
    setBusy(true)
    try { await inventoryCall("/catalogue/assets/run-depreciation", { method: "POST" }); await load() }
    catch (e) { setError(e instanceof Error ? e.message : "Could not post depreciation") }
    finally { setBusy(false) }
  }
  async function writeOff(b: Batch) {
    const reason = window.prompt(`Why is ${b.name} being written off (lost, stolen, scrapped)?`)
    if (!reason || reason.trim().length < 3) return
    const qty = Number(window.prompt(`How many units? (1 to ${b.quantity})`, "1"))
    if (!Number.isInteger(qty) || qty < 1 || qty > b.quantity) return
    try { await inventoryCall(`/catalogue/assets/${b.id}/dispose`, { method: "POST", json: { quantity: qty, reason: reason.trim() } }); await load() }
    catch (e) { setError(e instanceof Error ? e.message : "Could not write off") }
  }

  const live = (rows ?? []).filter((b) => b.quantity > 0)
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-sm">Equipment register</CardTitle>
        <Button type="button" variant="outline" size="sm" className="h-8 text-xs" disabled={busy} onClick={() => void runNow()}>
          {busy && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />} Post depreciation now
        </Button>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-xs text-muted-foreground">Company assets are carried as equipment from receipt; items given to customers from the day they are issued. Depreciation posts to finance at each month-end; returned units come back to stock at net book value.</p>
        {error && <p className="text-xs text-red-400" role="alert">{error}</p>}
        {rows === null && !error && <p className="text-xs text-muted-foreground">Loading…</p>}
        {rows !== null && live.length === 0 && <p className="text-xs text-muted-foreground">No equipment on the register yet.</p>}
        {live.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead><tr className="text-muted-foreground"><th className="py-1 pr-3 font-normal">Product</th><th className="px-2 font-normal">Qty</th><th className="px-2 font-normal">Cost each</th><th className="px-2 font-normal">Per month</th><th className="px-2 font-normal">Months</th><th className="px-2 font-normal">Net book value</th><th className="px-2 font-normal">Since</th><th /></tr></thead>
              <tbody>
                {live.map((b) => (
                  <tr key={b.id} className="border-t border-border">
                    <td className="py-1.5 pr-3 text-foreground">{b.product_number} · {b.name} <Badge variant="outline" className="ml-1 text-[10px]">{b.origin === "issue" ? "with customer" : "company"}</Badge></td>
                    <td className="px-2">{b.quantity}</td>
                    <td className="px-2">{money(b.unit_cost)}</td>
                    <td className="px-2">{money(b.monthly)}</td>
                    <td className="px-2">{b.depreciated_months}/{b.life_months}</td>
                    <td className="px-2">{money(b.net_book_value)}</td>
                    <td className="px-2">{b.in_service}</td>
                    <td className="px-2"><Button type="button" variant="ghost" size="sm" className="h-7 w-7 p-0 hover:text-red-400" aria-label={`Write off ${b.name}`} onClick={() => void writeOff(b)}><Trash2 className="h-3.5 w-3.5" /></Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
