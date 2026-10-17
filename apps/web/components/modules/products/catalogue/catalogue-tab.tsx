"use client"

import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { getLists, listProducts, type Lists, type Product } from "@/lib/catalogue-api"
import { ProductDetail } from "./product-detail"
import { ProductDirectory } from "./product-directory"
import { ProductWizard } from "./product-wizard"
import { AuthImage, StatusBadge, primaryImage, productSummary } from "./shared"

const EMPTY_LISTS: Lists = { categories: {}, families: [], items: [] }

interface Props {
  /** Called when the catalogue changed, so the portal's KPI cards can refresh. */
  onCatalogueChanged?: (products: Product[]) => void
}

export function CatalogueTab({ onCatalogueChanged }: Props) {
  const [products, setProducts] = useState<Product[]>([])
  const [lists, setLists] = useState<Lists>(EMPTY_LISTS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<"directory" | "development">("directory")
  const [detail, setDetail] = useState<Product | null>(null)
  const [editor, setEditor] = useState<{ open: boolean; product: Product | null }>({ open: false, product: null })

  const reload = useCallback(async () => {
    try {
      const p = await listProducts()
      setProducts(p)
      setError(null)
      onCatalogueChanged?.(p)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [onCatalogueChanged])

  const reloadLists = useCallback(async () => {
    try { setLists(await getLists()) } catch { /* the editor shows empty lists until the service answers */ }
    await reload()   // a rename updates products server-side
  }, [reload])

  useEffect(() => {
    void reload()
    void getLists().then(setLists).catch(() => undefined)
  }, [reload])

  const open = (p: Product | null) => setEditor({ open: true, product: p })
  const viewById = (id: string) => { const p = products.find((x) => x.id === id); if (p) setDetail(p) }

  return (
    <div className="space-y-5">
      <div className="inline-flex rounded-lg border border-border bg-card/60 p-0.5" role="tablist" aria-label="Catalogue views">
        {(["directory", "development"] as const).map((v) => (
          <Button key={v} role="tab" aria-selected={view === v} variant={view === v ? "secondary" : "ghost"} size="sm" className="h-8 text-xs capitalize" onClick={() => setView(v)}>
            {v === "directory" ? "Directory" : "Development"}
          </Button>
        ))}
      </div>

      {view === "directory" ? (
        <ProductDirectory products={products} loading={loading} error={error} onNew={() => open(null)} onOpen={setDetail} onEdit={(p) => open(p)} />
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold tracking-tight text-foreground">From idea to a launched offer</h2>
              <p className="text-xs text-muted-foreground">Definition, sourcing, testing and regulatory lodgment in one journey.</p>
            </div>
            <Button size="sm" className="text-xs" onClick={() => open(null)}>+ Start a draft</Button>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {([["draft", "Draft", "Definition & sourcing"], ["in_review", "In review", "Commercial review"], ["active", "Active", "Launched catalogue"]] as const).map(([status, title, sub]) => {
              const items = products.filter((p) => p.status === status)
              return (
                <Card key={status} className="border-border">
                  <CardContent className="space-y-3 p-4">
                    <div><div className="text-[11px] font-medium uppercase tracking-wider text-primary">{title}</div><div className="text-sm font-semibold text-foreground">{sub}</div></div>
                    {items.length === 0 && <p className="text-xs text-muted-foreground">No products at this stage.</p>}
                    {items.map((p) => {
                      const passed = p.checks.filter((c) => c.ok).length
                      return (
                        <div key={p.id} className="flex gap-3 rounded-lg border border-border bg-card/60 p-2.5">
                          <AuthImage asset={primaryImage(p.definition)} alt="" className="h-14 w-16 shrink-0 rounded-md" />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2"><span className="font-mono text-[10px] text-primary">{p.product_number}</span><StatusBadge status={p.status} /></div>
                            <div className="truncate text-xs font-semibold text-foreground">{p.name}</div>
                            <div className="truncate text-[11px] text-muted-foreground">{productSummary(p)}</div>
                            {status !== "active" && <div className={`text-[11px] ${passed === p.checks.length ? "text-emerald-400" : "text-amber-400"}`}>Launch checks: {passed} of {p.checks.length}</div>}
                            <button type="button" className="mt-1 text-[11px] font-medium text-primary hover:underline" onClick={() => open(p)}>Open product journey →</button>
                          </div>
                        </div>
                      )
                    })}
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </div>
      )}

      <ProductDetail
        product={detail} products={products} onClose={() => setDetail(null)} onChanged={reload}
        onEdit={(p) => open(p)} onOpen={(p) => setDetail(p)} canEdit={!editor.open}
      />
      <ProductWizard
        open={editor.open} product={editor.product} products={products} lists={lists} reloadLists={reloadLists}
        onClose={() => setEditor({ open: false, product: null })} onChanged={reload} onView={viewById}
      />
    </div>
  )
}
