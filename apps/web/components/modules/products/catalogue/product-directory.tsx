"use client"

import { useMemo, useState } from "react"
import { ChevronRight, Grid, List, Pencil, Plus, Search } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import type { Product } from "@/lib/catalogue-api"
import { AuthImage, StatusBadge, money, primaryImage, productSummary, selectCls } from "./shared"

interface Props {
  products: Product[]
  loading: boolean
  error: string | null
  onNew: () => void
  onOpen: (p: Product) => void
  onEdit: (p: Product) => void
}

function priceLine(p: Product) {
  const price = Number(p.definition.price)
  if (!(price > 0)) return "Price not set"
  return `${money(price)}${p.definition.recurring ? " /mo" : ""}`
}

export function ProductDirectory({ products, loading, error, onNew, onOpen, onEdit }: Props) {
  const [view, setView] = useState<"grid" | "list">("grid")
  const [search, setSearch] = useState("")
  const [category, setCategory] = useState("ALL")
  const [status, setStatus] = useState("ALL")
  const [nature, setNature] = useState("ALL")

  const categories = useMemo(() => Array.from(new Set(products.map((p) => p.category).filter(Boolean))).sort(), [products])
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return products.filter((p) => {
      if (category !== "ALL" && p.category !== category) return false
      if (status !== "ALL" && p.status !== status) return false
      if (nature !== "ALL" && p.nature !== nature) return false
      if (!q) return true
      return [p.name, p.product_number, p.definition.customer_name, p.category, p.range, p.family].join(" ").toLowerCase().includes(q)
    })
  }, [products, search, category, status, nature])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-xl font-bold tracking-tight text-foreground">Product Directory</h2>
            <Badge variant="outline" className="border-primary/30 bg-primary/10 text-xs text-primary">
              {products.filter((p) => p.status === "active").length} Active · {products.length} Total
            </Badge>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Everything we sell, buy, include or hold, with pictures, pricing, fees and launch status in one place.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" className="h-8 gap-1.5 text-xs font-medium" onClick={onNew}>
            <Plus className="h-3.5 w-3.5" /> New product
          </Button>
          <div className="flex items-center rounded-lg border border-border bg-card/60 p-0.5">
            <Button variant={view === "grid" ? "secondary" : "ghost"} size="sm" className="h-7 w-7 p-0" onClick={() => setView("grid")} title="Grid view" aria-label="Grid view">
              <Grid className="h-3.5 w-3.5" />
            </Button>
            <Button variant={view === "list" ? "secondary" : "ghost"} size="sm" className="h-7 w-7 p-0" onClick={() => setView("list")} title="Table view" aria-label="Table view">
              <List className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>

      <Card className="border-border">
        <CardContent className="p-3 sm:p-4">
          <div className="grid gap-3 sm:grid-cols-12">
            <div className="relative sm:col-span-6 lg:col-span-5">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input placeholder="Search by name, product number, category or range…" value={search} onChange={(e) => setSearch(e.target.value)} className="h-9 pl-8 text-xs" aria-label="Search products" />
            </div>
            <div className="sm:col-span-3 lg:col-span-3">
              <select value={category} onChange={(e) => setCategory(e.target.value)} className={selectCls} aria-label="Filter by category">
                <option value="ALL">All categories ({categories.length})</option>
                {categories.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="sm:col-span-3 lg:col-span-2">
              <select value={nature} onChange={(e) => setNature(e.target.value)} className={selectCls} aria-label="Filter by nature">
                <option value="ALL">All natures</option>
                <option>Digital service</option>
                <option>Physical item</option>
                <option>Professional service</option>
              </select>
            </div>
            <div className="sm:col-span-3 lg:col-span-2">
              <select value={status} onChange={(e) => setStatus(e.target.value)} className={selectCls} aria-label="Filter by status">
                <option value="ALL">All statuses</option>
                <option value="active">Active</option>
                <option value="draft">Draft</option>
                <option value="in_review">In review</option>
                <option value="archived">Archived</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <div className="py-12 text-center text-sm text-muted-foreground">Loading products…</div>
      ) : error ? (
        <div className="py-8 text-center text-sm text-red-400" role="alert">Could not load the catalogue: {error}</div>
      ) : products.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border py-14 text-center">
          <p className="text-sm text-muted-foreground">No products yet.</p>
          <Button size="sm" className="mt-3 gap-1.5 text-xs" onClick={onNew}><Plus className="h-3.5 w-3.5" /> Develop your first product</Button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-12 text-center text-sm text-muted-foreground">No products match your filters.</div>
      ) : view === "grid" ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((p) => {
            const fees = p.definition.fees.filter((f) => f.enabled).length
            return (
              <div
                key={p.id}
                role="button"
                tabIndex={0}
                onClick={() => onOpen(p)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(p) } }}
                className="group relative flex cursor-pointer flex-col overflow-hidden rounded-xl border border-border bg-card/80 shadow-sm backdrop-blur transition-all hover:border-primary/50 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <div className="relative">
                  <AuthImage asset={primaryImage(p.definition)} alt={p.name} className="aspect-[4/3] w-full" />
                  <div className="absolute left-2 top-2"><StatusBadge status={p.status} /></div>
                  <Button
                    variant="secondary" size="sm" className="absolute right-2 top-2 h-7 w-7 p-0 opacity-0 transition-opacity focus:opacity-100 group-hover:opacity-100"
                    title="Edit product" aria-label={`Edit ${p.name}`}
                    onClick={(e) => { e.stopPropagation(); onEdit(p) }}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <div className="flex flex-1 flex-col justify-between p-4">
                  <div>
                    <h3 className="text-sm font-semibold text-foreground transition-colors group-hover:text-primary">{p.definition.customer_name || p.name}</h3>
                    <p className="mt-0.5 text-xs text-muted-foreground line-clamp-1">{productSummary(p)}</p>
                    <div className="mt-2.5 flex items-center justify-between text-xs">
                      <span className="font-mono text-[11px] text-primary">{p.product_number}</span>
                      <Badge variant="outline" className="border-border/80 px-1.5 py-0 text-[10px] font-medium">{p.nature}</Badge>
                    </div>
                  </div>
                  <div className="mt-3.5 flex items-center justify-between border-t border-border/40 pt-2.5 text-[11px]">
                    <span className="font-medium text-foreground">{priceLine(p)}{fees ? <span className="ml-1 text-muted-foreground">+ {fees} fee{fees > 1 ? "s" : ""}</span> : null}</span>
                    <span className="flex items-center gap-0.5 font-medium text-primary transition-transform group-hover:translate-x-0.5">View <ChevronRight className="h-3 w-3" /></span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <Card className="border-border">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                    <th className="px-4 py-2.5 font-medium">Product</th>
                    <th className="px-4 py-2.5 font-medium">Number</th>
                    <th className="px-4 py-2.5 font-medium">Category › Range</th>
                    <th className="px-4 py-2.5 font-medium">Nature</th>
                    <th className="px-4 py-2.5 font-medium">Price</th>
                    <th className="px-4 py-2.5 font-medium">Status</th>
                    <th className="px-4 py-2.5 text-right font-medium">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {filtered.map((p) => (
                    <tr key={p.id} className="cursor-pointer transition-colors hover:bg-muted/30" onClick={() => onOpen(p)}>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2.5">
                          <AuthImage asset={primaryImage(p.definition)} alt="" className="h-9 w-9 rounded-md ring-1 ring-border" />
                          <span className="font-semibold text-foreground">{p.definition.customer_name || p.name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-primary">{p.product_number}</td>
                      <td className="px-4 py-2.5 text-muted-foreground">{productSummary(p)}</td>
                      <td className="px-4 py-2.5 text-foreground">{p.nature}</td>
                      <td className="px-4 py-2.5 text-foreground">{priceLine(p)}</td>
                      <td className="px-4 py-2.5"><StatusBadge status={p.status} /></td>
                      <td className="px-4 py-2.5 text-right">
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" title="Edit product" aria-label={`Edit ${p.name}`} onClick={(e) => { e.stopPropagation(); onEdit(p) }}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
