"use client"

import React from "react"
import { ModuleLayout } from "./module-layout"
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    PieChart,
    Pie,
    Cell,
    AreaChart,
    Area,
    LineChart,
    Line,
} from "recharts"
import { Package, Warehouse, Truck, AlertTriangle } from "lucide-react"
import { useModuleData } from "@/lib/module-data"

// Stock levels by category
const defaultStockByCategoryData = [
    { category: "ONTs", inStock: 150, reserved: 35, lowThreshold: 50 },
    { category: "Routers", inStock: 89, reserved: 22, lowThreshold: 40 },
    { category: "Patch Leads", inStock: 420, reserved: 60, lowThreshold: 100 },
    { category: "Smart Cameras", inStock: 64, reserved: 18, lowThreshold: 30 },
    { category: "Switches", inStock: 45, reserved: 12, lowThreshold: 20 },
    { category: "SFP Modules", inStock: 210, reserved: 40, lowThreshold: 80 },
]

// Sell-through rates
const defaultSellThruData = [
    { name: "Vumatel ONT", value: 30, fill: "#4ade80" },
    { name: "Netgear Router", value: 42, fill: "#60a5fa" },
    { name: "Smart Camera", value: 58, fill: "#a855f7" },
    { name: "UPS Battery", value: 22, fill: "#f97316" },
    { name: "Patch Lead 5m", value: 67, fill: "#06b6d4" },
]

// Stock movement trends
const defaultMovementTrendData = [
    { month: "Jul", purchases: 340, sales: 280, returns: 12, transfers: 45 },
    { month: "Aug", purchases: 290, sales: 310, returns: 8, transfers: 52 },
    { month: "Sep", purchases: 410, sales: 350, returns: 15, transfers: 38 },
    { month: "Oct", purchases: 380, sales: 320, returns: 10, transfers: 60 },
    { month: "Nov", purchases: 350, sales: 390, returns: 18, transfers: 42 },
    { month: "Dec", purchases: 500, sales: 420, returns: 14, transfers: 55 },
]

// Warehouse stock distribution
const defaultWarehouseData = [
    { name: "Main JHB", value: 1245, fill: "#4ade80" },
    { name: "Cape Town DC", value: 890, fill: "#60a5fa" },
    { name: "Durban Hub", value: 620, fill: "#a855f7" },
    { name: "Partner (External)", value: 345, fill: "#f97316" },
]

// Global shipment tracking
const defaultShipmentData = [
    { shipment: "SHP-001", origin: "Shenzhen, China", destination: "Main JHB", status: "In Transit", eta: "2026-02-15", items: 500 },
    { shipment: "SHP-002", origin: "Main JHB", destination: "Cape Town DC", status: "Delivered", eta: "2026-02-06", items: 120 },
    { shipment: "SHP-003", origin: "Taipei, Taiwan", destination: "Main JHB", status: "Ordered", eta: "2026-03-01", items: 300 },
    { shipment: "SHP-004", origin: "Main JHB", destination: "Durban Hub", status: "In Transit", eta: "2026-02-09", items: 80 },
]

const formatCurrency = (value: number) => `R ${value.toLocaleString("en-ZA")}`

const defaultFlashcardKPIs = [
    {
        id: "1",
        title: "Total Stock on Hand",
        value: "3,100",
        change: "+8.2%",
        changeType: "positive" as const,
        iconKey: "stock",
        backTitle: "Stock by Warehouse",
        backDetails: [
            { label: "Main JHB", value: "1,245" },
            { label: "Cape Town DC", value: "890" },
            { label: "Durban Hub", value: "620" },
        ],
        backInsight: "Stock levels healthy across all regions",
    },
    {
        id: "2",
        title: "Low Stock Alerts",
        value: "4",
        change: "-2",
        changeType: "positive" as const,
        iconKey: "alerts",
        backTitle: "Items Below Threshold",
        backDetails: [
            { label: "RTR-NET-05", value: "12 / 20 min" },
            { label: "CAM-SMT-02", value: "8 / 15 min" },
            { label: "SFP-1G-LR", value: "18 / 25 min" },
        ],
        backInsight: "Auto-replenishment triggered for 2 items",
    },
    {
        id: "3",
        title: "Inventory Value",
        value: formatCurrency(4250000),
        change: "+5.4%",
        changeType: "positive" as const,
        iconKey: "value",
        backTitle: "Value by Category",
        backDetails: [
            { label: "Network Equipment", value: formatCurrency(2180000) },
            { label: "CPE Devices", value: formatCurrency(1420000) },
            { label: "Accessories", value: formatCurrency(650000) },
        ],
        backInsight: "Avg margin at 34% across all SKUs",
    },
    {
        id: "4",
        title: "Active Shipments",
        value: "3",
        change: "+1",
        changeType: "neutral" as const,
        iconKey: "shipments",
        backTitle: "Shipment Status",
        backDetails: [
            { label: "In Transit", value: "2" },
            { label: "Ordered", value: "1" },
            { label: "Avg Lead Time", value: "18 days" },
        ],
        backInsight: "500 ONTs arriving from China Feb 15",
    },
]

const inventoryKpiIconMap: Record<string, React.ReactNode> = {
    stock: <Package className="h-5 w-5 text-emerald-400" />,
    alerts: <AlertTriangle className="h-5 w-5 text-amber-400" />,
    value: <Warehouse className="h-5 w-5 text-blue-400" />,
    shipments: <Truck className="h-5 w-5 text-violet-400" />,
}

const defaultActivities = [
    {
        id: "1",
        user: "Auto-Replenish",
        action: "created purchase order for",
        target: "RTR-NET-05 (50 units)",
        time: "10 minutes ago",
        type: "create" as const,
    },
    {
        id: "2",
        user: "Warehouse JHB",
        action: "received shipment",
        target: "SHP-002 (120 items)",
        time: "2 hours ago",
        type: "update" as const,
    },
    {
        id: "3",
        user: "Mandla Nkosi",
        action: "transferred 40 ONTs to",
        target: "Cape Town DC",
        time: "3 hours ago",
        type: "update" as const,
    },
    {
        id: "4",
        user: "System",
        action: "flagged low stock for",
        target: "CAM-SMT-02 (8 units)",
        time: "4 hours ago",
        type: "assign" as const,
    },
    {
        id: "5",
        user: "Procurement",
        action: "approved PO for",
        target: "500 Vumatel ONTs",
        time: "Yesterday",
        type: "comment" as const,
    },
]

const defaultIssues = [
    {
        id: "1",
        title: "RTR-NET-05 stock at 12 units — below minimum threshold of 20",
        severity: "high" as const,
        status: "in-progress" as const,
        assignee: "Procurement",
        time: "Active",
    },
    {
        id: "2",
        title: "Shipment SHP-001 delayed by 3 days due to customs hold",
        severity: "medium" as const,
        status: "open" as const,
        assignee: "Logistics",
        time: "1 hour ago",
    },
    {
        id: "3",
        title: "3 customer returns pending quality inspection",
        severity: "low" as const,
        status: "open" as const,
        assignee: "Warehouse Team",
        time: "Today",
    },
]

const defaultTasks = [
    {
        id: "1",
        title: "Complete quarterly stock count for JHB warehouse",
        priority: "urgent" as const,
        status: "in-progress" as const,
        dueDate: "Today",
        assignee: "Warehouse Team",
    },
    {
        id: "2",
        title: "Review and approve vendor pricing for Q1 2026",
        priority: "high" as const,
        status: "todo" as const,
        dueDate: "Tomorrow",
        assignee: "Procurement",
    },
    {
        id: "3",
        title: "Set up auto-replenishment for new Smart Camera SKU",
        priority: "normal" as const,
        status: "todo" as const,
        dueDate: "Next Week",
        assignee: "Mandla Nkosi",
    },
    {
        id: "4",
        title: "Reconcile inventory differences from December count",
        priority: "normal" as const,
        status: "done" as const,
        dueDate: "Completed",
        assignee: "Finance",
    },
]

const defaultAIRecommendations = [
    {
        id: "1",
        title: "Increase ONT safety stock to 200 units",
        description: "Installation rate trending up 15%. Current stock may run out in 18 days at current pace.",
        impact: "high" as const,
        category: "Stock Planning",
    },
    {
        id: "2",
        title: "Bundle Smart Camera with Premium package",
        description: "58% sell-through rate suggests high demand. Bundling could increase Premium plan conversions by 12%.",
        impact: "high" as const,
        category: "Product Strategy",
    },
    {
        id: "3",
        title: "Consolidate low-volume SKUs to Main JHB",
        description: "15 SKUs with <5 units across multiple warehouses. Consolidation saves R 8K/month in holding costs.",
        impact: "medium" as const,
        category: "Cost Optimization",
    },
    {
        id: "4",
        title: "Negotiate volume discount with Netgear",
        description: "Router purchases up 30% YoY. Volume commitment of 500/quarter could save 18% on unit cost.",
        impact: "medium" as const,
        category: "Procurement",
    },
]

const defaultTableData = [
    { id: "1", sku: "ONT-V1", name: "Vumatel ONT", warehouse: "Main JHB", soh: "150", reserved: "35", available: "115", reorderPoint: "50" },
    { id: "2", sku: "RTR-NET-05", name: "Netgear Router R6700", warehouse: "Main JHB", soh: "12", reserved: "4", available: "8", reorderPoint: "20" },
    { id: "3", sku: "CAM-SMT-02", name: "Smart Camera v2", warehouse: "Cape Town DC", soh: "8", reserved: "2", available: "6", reorderPoint: "15" },
    { id: "4", sku: "PL-CAT6-5M", name: "Cat6 Patch Lead 5m", warehouse: "Main JHB", soh: "420", reserved: "60", available: "360", reorderPoint: "100" },
    { id: "5", sku: "SFP-1G-LR", name: "SFP 1G LR Module", warehouse: "Durban Hub", soh: "18", reserved: "5", available: "13", reorderPoint: "25" },
    { id: "6", sku: "SW-24P-01", name: "24-Port Managed Switch", warehouse: "Main JHB", soh: "45", reserved: "12", available: "33", reorderPoint: "20" },
    { id: "7", sku: "UPS-650VA", name: "UPS 650VA Mini", warehouse: "Cape Town DC", soh: "92", reserved: "15", available: "77", reorderPoint: "30" },
    { id: "8", sku: "ONT-V2", name: "Vumatel ONT v2", warehouse: "Main JHB", soh: "85", reserved: "20", available: "65", reorderPoint: "40" },
]

const tableColumns = [
    { key: "sku", label: "SKU" },
    { key: "name", label: "Product Name" },
    { key: "warehouse", label: "Warehouse" },
    { key: "soh", label: "Stock on Hand" },
    { key: "reserved", label: "Reserved" },
    { key: "available", label: "Available" },
    { key: "reorderPoint", label: "Reorder Point" },
]

const WAREHOUSE_COLORS = ["#4ade80", "#60a5fa", "#a855f7", "#f97316"]

export function InventoryModule() {
    const { data } = useModuleData("inventory", {
        flashcardKPIs: defaultFlashcardKPIs,
        activities: defaultActivities,
        issues: defaultIssues,
        tasks: defaultTasks,
        aiRecommendations: defaultAIRecommendations,
        tableData: defaultTableData,
    })

    const flashcardKPIs = (data.flashcardKPIs ?? defaultFlashcardKPIs).map(
        (kpi: (typeof defaultFlashcardKPIs)[number]) => ({
            ...kpi,
            icon: inventoryKpiIconMap[kpi.iconKey] || <Package className="h-5 w-5 text-primary" />,
        }),
    )

    return (
        <ModuleLayout
            title="Inventory & Stock Management"
            flashcardKPIs={flashcardKPIs}
            activities={data.activities ?? defaultActivities}
            issues={data.issues ?? defaultIssues}
            summary="Inventory levels are healthy at 3,100 units across 4 warehouses with R 4.25M total value. 4 low-stock alerts active with auto-replenishment triggered for 2 items. Global supply chain tracking shows 3 active shipments including a 500-unit ONT order from China arriving Feb 15. Sell-through rates are strong for Smart Cameras (58%) and Patch Leads (67%), suggesting increased demand for installation bundles."
            tasks={data.tasks ?? defaultTasks}
            aiRecommendations={data.aiRecommendations ?? defaultAIRecommendations}
            tableData={data.tableData ?? defaultTableData}
            tableColumns={tableColumns}
        >
            <div className="grid gap-6 lg:grid-cols-2">
                {/* Stock by Category */}
                <div className="rounded-xl border border-border bg-card p-6">
                    <h4 className="mb-4 text-sm font-semibold text-foreground">Stock Levels by Category</h4>
                    <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={defaultStockByCategoryData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                            <XAxis dataKey="category" stroke="#888" fontSize={11} />
                            <YAxis stroke="#888" fontSize={12} />
                            <Tooltip
                                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                            />
                            <Legend />
                            <Bar dataKey="inStock" fill="#4ade80" name="In Stock" radius={[4, 4, 0, 0]} />
                            <Bar dataKey="reserved" fill="#f97316" name="Reserved" radius={[4, 4, 0, 0]} />
                            <Bar dataKey="lowThreshold" fill="rgba(239,68,68,0.3)" name="Min Threshold" radius={[4, 4, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>

                {/* Warehouse Distribution */}
                <div className="rounded-xl border border-border bg-card p-6">
                    <h4 className="mb-4 text-sm font-semibold text-foreground">Stock by Warehouse</h4>
                    <ResponsiveContainer width="100%" height={300}>
                        <PieChart>
                            <Pie
                                data={defaultWarehouseData}
                                cx="50%"
                                cy="50%"
                                innerRadius={60}
                                outerRadius={100}
                                paddingAngle={5}
                                dataKey="value"
                                label={({ name, value }) => `${name}: ${value}`}
                            >
                                {defaultWarehouseData.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={WAREHOUSE_COLORS[index % WAREHOUSE_COLORS.length]} />
                                ))}
                            </Pie>
                            <Tooltip
                                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                            />
                        </PieChart>
                    </ResponsiveContainer>
                </div>

                {/* Stock Movement Trends */}
                <div className="rounded-xl border border-border bg-card p-6">
                    <h4 className="mb-4 text-sm font-semibold text-foreground">Stock Movement Trends</h4>
                    <ResponsiveContainer width="100%" height={300}>
                        <AreaChart data={defaultMovementTrendData}>
                            <defs>
                                <linearGradient id="colorPurchases" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#4ade80" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#4ade80" stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="colorSales" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                            <XAxis dataKey="month" stroke="#888" fontSize={12} />
                            <YAxis stroke="#888" fontSize={12} />
                            <Tooltip
                                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                            />
                            <Legend />
                            <Area type="monotone" dataKey="purchases" stroke="#4ade80" fillOpacity={1} fill="url(#colorPurchases)" name="Purchases" />
                            <Area type="monotone" dataKey="sales" stroke="#60a5fa" fillOpacity={1} fill="url(#colorSales)" name="Sales/Installs" />
                            <Line type="monotone" dataKey="returns" stroke="#f97316" strokeWidth={2} dot={false} name="Returns" />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>

                {/* Sell-Through Rates */}
                <div className="rounded-xl border border-border bg-card p-6">
                    <h4 className="mb-4 text-sm font-semibold text-foreground">Sell-Through Rate by Product</h4>
                    <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={defaultSellThruData} layout="vertical">
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                            <XAxis type="number" stroke="#888" fontSize={12} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                            <YAxis dataKey="name" type="category" stroke="#888" fontSize={11} width={130} />
                            <Tooltip
                                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                                formatter={(value: number) => [`${value}%`, "Sell-Through"]}
                            />
                            <Bar dataKey="value" name="Sell-Through %" radius={[0, 4, 4, 0]}>
                                {defaultSellThruData.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={entry.fill} />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </ModuleLayout>
    )
}
