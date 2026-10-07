"use client"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { NotConnected } from "@/components/ui/not-connected"
import { fetchLoadable } from "@/lib/service-fetch"
import type { Loadable } from "@/lib/service-state"
import { inputClass } from "../billing/shared"
import { PurchasingSection } from "../purchasing-section"

type ReportKind = "valuation" | "reorder" | "spend" | "margin"
type Report = {basis: string; items: Record<string, string | number | null>[]; total: number; page_size: number; totals: Record<string, string>}
const headings: Record<ReportKind, string> = {valuation: "Stock valuation", reorder: "Reorder recommendations", spend: "Purchasing spend", margin: "Catalogue margins"}
const label = (s: string) => s.replaceAll("_", " ")
export function InventoryReports() {
  const [kind, setKind] = useState<ReportKind | "approvals">("valuation")
  const [warehouse, setWarehouse] = useState(""); const [start, setStart] = useState(""); const [end, setEnd] = useState("")
  const [warehouses, setWarehouses] = useState<Loadable<{id: string; name: string}[]>>({state: "loading"})
  useEffect(() => {void fetchLoadable<{id: string; name: string}[]>("/svc/inventory/warehouses", 20000).then(setWarehouses)}, [])
  const [filters, setFilters] = useState(""); const [page, setPage] = useState(1)
  const [data, setData] = useState<Loadable<Report>>({state: "loading"})
  const [tick, setTick] = useState(0); const [exporting, setExporting] = useState(false); const [error, setError] = useState("")
  const url = `/svc/inventory/reports/${kind}?${filters}&page=${page}&page_size=50`
  useEffect(() => {
    if (kind === "approvals") return
    let cancelled = false
    setData({state: "loading"})
    void fetchLoadable<Report>(url, 20000).then(value => {if (!cancelled) setData(value)})
    return () => {cancelled = true}
  }, [url, kind, tick])
  async function download() {
    setExporting(true); setError("")
    try {
      const response = await fetch(`${url}&format=csv`, {cache: "no-store", signal: AbortSignal.timeout(30000)})
      if (!response.ok) {const body = await response.json().catch(() => ({})); throw new Error(body.detail || body.error || `Export failed (${response.status})`)}
      const href = URL.createObjectURL(await response.blob()); const link = document.createElement("a")
      link.href = href; link.download = `inventory-${kind}.csv`; link.click(); URL.revokeObjectURL(href)
    } catch(e) {setError(e instanceof Error ? e.message : "Export failed")}
    finally {setExporting(false)}
  }
  return <section className="space-y-4 rounded-lg border p-4">
    <h3 className="text-lg font-semibold">Inventory reports & approvals</h3>
    <div role="group" aria-label="Inventory report" className="flex flex-wrap gap-2">
      {Object.entries(headings).map(([key, title]) => <Button key={key} variant={kind === key ? "default" : "outline"} onClick={() => {setKind(key as ReportKind); setPage(1); setFilters(""); setError("")}}>{title}</Button>)}
      <Button variant={kind === "approvals" ? "default" : "outline"} onClick={() => setKind("approvals")}>Approval inbox</Button>
    </div>
    {kind === "approvals" ? <PurchasingSection approvalOnly /> : <>
      <form className="flex flex-wrap items-end gap-3" onSubmit={e => {e.preventDefault(); const q = new URLSearchParams(); if (kind !== "margin" && warehouse.trim()) q.set("warehouse_id", warehouse.trim()); if (kind === "spend") {if (start) q.set("start", start); if (end) q.set("end", end)} setPage(1); setFilters(q.toString()); setTick(t => t + 1)}}>
        {kind !== "margin" && <label className="text-sm">Warehouse<select className={inputClass} value={warehouse} onChange={e => setWarehouse(e.target.value)}><option value="">All warehouses</option>{warehouses.state === "ready" && warehouses.data.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>}
        {kind === "spend" && <><label className="text-sm">Order date from<input type="date" className={inputClass} value={start} onChange={e => setStart(e.target.value)} /></label><label className="text-sm">Order date to<input type="date" className={inputClass} value={end} min={start || undefined} onChange={e => setEnd(e.target.value)} /></label></>}
        <Button variant="outline">Apply filters</Button><Button type="button" disabled={exporting || data.state !== "ready"} onClick={() => void download()}>{exporting ? "Exporting…" : "Export all matching rows (CSV)"}</Button>
      </form>
      {error && <p role="alert" className="text-red-400 text-sm">{error}</p>}
      {data.state !== "ready" ? <NotConnected loadable={data} service="Inventory reports" onRetry={() => setTick(t => t + 1)} /> : <>
        <p className="text-sm text-muted-foreground">{data.data.basis}</p>
        <dl className="flex flex-wrap gap-4">{Object.entries(data.data.totals).map(([key, value]) => <div key={key}><dt className="text-xs capitalize text-muted-foreground">{label(key)}</dt><dd className="font-semibold">R{Number(value).toLocaleString("en-ZA", {minimumFractionDigits: 2})}</dd></div>)}</dl>
        {data.data.items.length === 0 ? <p>No matching records.</p> : <div className="overflow-x-auto"><table className="w-full text-sm"><caption className="sr-only">{headings[kind]}</caption><thead><tr>{Object.keys(data.data.items[0]).filter(key => !key.endsWith("_id")).map(key => <th scope="col" className="whitespace-nowrap p-2 text-left capitalize" key={key}>{label(key)}</th>)}</tr></thead><tbody>{data.data.items.map((row, i) => <tr className="border-t" key={String(row.product_id || row.po_id) + String(row.warehouse_id || i)}>{Object.entries(row).filter(([key]) => !key.endsWith("_id")).map(([key, value]) => <td className="p-2 whitespace-nowrap" key={key}>{value === null ? "—" : String(value)}</td>)}</tr>)}</tbody></table></div>}
        <div className="flex items-center gap-3"><Button variant="outline" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button><span className="text-sm">Page {page} · {data.data.total} records</span><Button variant="outline" disabled={page * data.data.page_size >= data.data.total} onClick={() => setPage(page + 1)}>Next</Button></div>
      </>}
    </>}
  </section>
}
