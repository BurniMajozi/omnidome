"use client"

import React from "react"
import { ModuleLayout } from "./module-layout"
import { Package, Warehouse, Truck, AlertTriangle } from "lucide-react"
import { PurchasingSection } from "./purchasing-section"
import { FieldTechVanStockView } from "./inventory/field-tech-van-stock"
import { useLoadable } from "@/lib/service-fetch"
import { type Loadable } from "@/lib/service-state"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"

// Real inventory service only (/svc/inventory/...). The service currently
// exposes products, suppliers and purchase orders - it has NO stock-level,
// warehouse, shipment or movement listing endpoints, so every tile/chart that
// needed those shows "Not connected" instead of sample numbers.

interface Product {
    id: string
    sku: string
    name: string
    cost_price: string | number | null
    rrp: string | number | null
    margin_percent: string | number | null
}
interface PurchaseOrderLite {
    id: string
    status: string
}

const formatZar = (v: string | number | null | undefined) =>
    v === null || v === undefined || v === "" ? "—" : `R ${Number(v).toLocaleString("en-ZA", { minimumFractionDigits: 2 })}`

const NO_STOCK_ENDPOINT: Loadable<unknown> = {
    state: "error",
    status: null,
    message: "the inventory service exposes no stock-level, warehouse or shipment endpoint yet",
}

function kpiValue<T>(l: Loadable<T>, fn: (d: T) => string): string {
    if (l.state === "ready") return fn(l.data)
    if (l.state === "loading") return "…"
    return l.state === "unreachable" ? "Service not running" : l.state === "denied" ? "Not permitted" : "Error loading"
}

export function InventoryModule() {
    const products = useLoadable<Product[]>("/svc/inventory/products")
    const suppliers = useLoadable<unknown[]>("/svc/inventory/suppliers")
    const orders = useLoadable<PurchaseOrderLite[]>("/svc/inventory/purchase-orders")

    const serviceDown = products.value.state === "unreachable"
    const reloadAll = () => {
        products.reload()
        suppliers.reload()
        orders.reload()
    }

    const flashcardKPIs = [
        {
            id: "1",
            title: "Products in Catalogue",
            value: kpiValue(products.value, (d) => String(d.length)),
            change: "",
            changeType: "neutral" as const,
            icon: <Package className="h-5 w-5 text-emerald-400" />,
            backTitle: "Catalogue",
            backDetails: [],
            backInsight: "Counted from the inventory service product list.",
        },
        {
            id: "2",
            title: "Suppliers",
            value: kpiValue(suppliers.value, (d) => String(d.length)),
            change: "",
            changeType: "neutral" as const,
            icon: <Truck className="h-5 w-5 text-violet-400" />,
            backTitle: "Suppliers",
            backDetails: [],
            backInsight: "Counted from the inventory service supplier list.",
        },
        {
            id: "3",
            title: "Open Purchase Orders",
            value: kpiValue(orders.value, (d) =>
                String(d.filter((o) => o.status !== "received" && o.status !== "cancelled").length),
            ),
            change: "",
            changeType: "neutral" as const,
            icon: <Warehouse className="h-5 w-5 text-blue-400" />,
            backTitle: "Purchase Orders",
            backDetails: [],
            backInsight: "Draft, submitted, approved or partially received orders.",
        },
        {
            id: "4",
            title: "Stock on Hand / Low Stock",
            value: "Not connected",
            change: "",
            changeType: "neutral" as const,
            icon: <AlertTriangle className="h-5 w-5 text-amber-400" />,
            backTitle: "Stock levels",
            backDetails: [],
            backInsight: "No stock-level endpoint is exposed by the inventory service yet.",
        },
    ]

    const productRows = products.value.state === "ready" ? products.value.data : []

    return (
        <ModuleLayout
            title="Inventory & Stock Management"
            icon={<Package className="h-5 w-5" />}
            subtitle="Stock levels, procurement, warehouse, and asset tracking"
            flashcardKPIs={flashcardKPIs}
            activities={[]}
            issues={[]}
            summary="Figures on this page are read live from the inventory service. Anything the service cannot provide yet is marked Not connected."
            tasks={[]}
            aiRecommendations={[]}
            tableData={[]}
            tableColumns={[]}
            showTable={false}
        >
            {/* Product catalogue - real rows */}
            <div className="surface-card p-6">
                <h4 className="card-title mb-4">Product Catalogue</h4>
                {products.value.state !== "ready" ? (
                    <NotConnected loadable={products.value} service="Inventory service" onRetry={reloadAll} />
                ) : productRows.length === 0 ? (
                    <NoDataYet message="No products yet" />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                                    <th className="py-2 pr-4">SKU</th>
                                    <th className="py-2 pr-4">Product</th>
                                    <th className="py-2 pr-4 text-right">Cost</th>
                                    <th className="py-2 pr-4 text-right">RRP</th>
                                    <th className="py-2 text-right">Margin</th>
                                </tr>
                            </thead>
                            <tbody>
                                {productRows.map((p) => (
                                    <tr key={p.id} className="border-b border-border/50">
                                        <td className="py-2 pr-4 font-mono text-xs">{p.sku}</td>
                                        <td className="py-2 pr-4">{p.name}</td>
                                        <td className="py-2 pr-4 text-right">{formatZar(p.cost_price)}</td>
                                        <td className="py-2 pr-4 text-right">{formatZar(p.rrp)}</td>
                                        <td className="py-2 text-right">
                                            {p.margin_percent === null || p.margin_percent === undefined
                                                ? "—"
                                                : `${Number(p.margin_percent).toFixed(1)}%`}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Stock analytics - no backing endpoint, so no charts */}
            <div className="mt-6 grid gap-6 lg:grid-cols-2">
                {["Stock Levels by Category", "Stock by Warehouse", "Stock Movement Trends", "Sell-Through Rate by Product"].map(
                    (title) => (
                        <div key={title} className="surface-card p-6">
                            <h4 className="card-title mb-4">{title}</h4>
                            <NotConnected
                                loadable={serviceDown ? products.value : NO_STOCK_ENDPOINT}
                                service={serviceDown ? "Inventory service" : "Stock data"}
                                className="h-56"
                            />
                        </div>
                    ),
                )}
            </div>

            <div className="mt-6">
                {serviceDown ? (
                    <NotConnected loadable={products.value} service="Inventory service" onRetry={reloadAll} className="py-12" />
                ) : (
                    <PurchasingSection />
                )}
            </div>

            <div className="mt-8 pt-6 border-t border-border/50">
                <FieldTechVanStockView />
            </div>
        </ModuleLayout>
    )
}
