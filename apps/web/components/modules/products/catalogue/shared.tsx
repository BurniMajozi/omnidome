"use client"

import { useEffect, useState, type ReactNode } from "react"
import { ImageIcon } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { assetObjectUrl, type Asset, type Definition, type Fee, type Nature, type Product, type Status } from "@/lib/catalogue-api"

export const selectCls =
  "w-full h-9 rounded-md border border-border bg-background px-3 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
export const areaCls =
  "w-full rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"

export const money = (v: unknown) => `R ${Number(v || 0).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export const FEE_NAMES = [
  "Delivery", "Setup", "Callout", "Maintenance", "Installation", "Activation", "Administration",
  "Equipment rental", "Reconnection", "Relocation", "Support visit",
]
const EVENT_FEES = ["Callout", "Reconnection", "Relocation", "Support visit"]
const MONTHLY_FEES = ["Maintenance", "Equipment rental"]

export function defaultFees(): Fee[] {
  return FEE_NAMES.map((name, i) => ({
    id: `fee-${i}`, name, enabled: false, amount: 0,
    cadence: MONTHLY_FEES.includes(name) ? "Monthly" : EVENT_FEES.includes(name) ? "On event" : "Once-off",
    mode: "Charge", invoice_label: `${name} fee`,
  }))
}

export const STANDARD_TESTS: Record<Nature, string[]> = {
  "Digital service": ["Provisioning & activation", "Speed / throughput", "Billing & invoice line", "Customer portal order journey", "Cancellation & termination"],
  "Physical item": ["Fulfilment & stock reservation", "Serial & warranty record", "Billing & invoice line"],
  "Professional service": ["Scheduling & job completion", "Billing & invoice line"],
}

export const KPI_CATALOG: Record<"digital" | "physical", { key: string; label: string; source: string }[]> = {
  digital: [
    { key: "subs", label: "Active subscribers", source: "Billing" },
    { key: "mrr", label: "Monthly recurring revenue", source: "Billing" },
    { key: "new30", label: "New sales (30 days)", source: "Sales" },
    { key: "churn", label: "Churn (90 days)", source: "Billing" },
    { key: "gp", label: "Realised gross profit", source: "Finance" },
    { key: "tickets", label: "Open tickets", source: "Support" },
  ],
  physical: [
    { key: "stock", label: "Stock on hand", source: "Inventory" },
    { key: "reserved", label: "Reserved for orders", source: "Inventory" },
    { key: "sold30", label: "Units sold (30 days)", source: "Sales" },
    { key: "cust", label: "Customers holding the item", source: "Billing" },
    { key: "returns", label: "Returns / RMAs", source: "Support" },
    { key: "gp", label: "Realised gross profit", source: "Finance" },
  ],
}
export const kpiSet = (n: Nature) => (n === "Digital service" ? KPI_CATALOG.digital : KPI_CATALOG.physical)

export const STATUS_LABEL: Record<Status, string> = { draft: "Draft", in_review: "In review", active: "Active", archived: "Archived" }
export const STATUS_CLS: Record<Status, string> = {
  draft: "border-amber-500/40 text-amber-400",
  in_review: "border-blue-500/40 text-blue-400",
  active: "border-emerald-500/40 text-emerald-400",
  archived: "border-border text-muted-foreground",
}
export function StatusBadge({ status }: { status: Status }) {
  return <Badge variant="outline" className={`text-[10px] py-0 px-1.5 font-medium ${STATUS_CLS[status]}`}>{STATUS_LABEL[status]}</Badge>
}

export function Field({ label, hint, children, className = "" }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`grid gap-1.5 text-xs text-muted-foreground ${className}`}>
      <span>{label}</span>
      {children}
      {hint && <span className="text-[11px] text-muted-foreground/80">{hint}</span>}
    </label>
  )
}

/** Primary picture for a product: the flagged primary image, else the first image (not GIF/3D). */
export function primaryImage(d: Definition): Asset | undefined {
  const imgs = (d.media ?? []).filter((a) => a.kind !== "3D" && a.extension !== "gif")
  return imgs.find((a) => a.primary) ?? imgs[0]
}

/** Loads a stored picture with the tenant headers (a plain <img src> cannot send them). */
export function AuthImage({ asset, className = "", alt }: { asset?: Pick<Asset, "url" | "alt" | "name">; className?: string; alt?: string }) {
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let live = true
    setSrc(null)
    setFailed(false)
    if (asset?.url) {
      assetObjectUrl(asset.url).then((u) => live && setSrc(u)).catch(() => live && setFailed(true))
    }
    return () => { live = false }
  }, [asset?.url])
  if (!asset || failed || !src) {
    return (
      <div className={`flex items-center justify-center bg-muted/30 text-muted-foreground ${className}`} role="img" aria-label={alt ?? "No picture"}>
        <ImageIcon className="h-6 w-6 opacity-50" />
      </div>
    )
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt ?? asset.alt ?? asset.name} className={`object-cover ${className}`} />
}

export function productSummary(p: Pick<Product, "category" | "range">) {
  return [p.category, p.range].filter(Boolean).join(" › ") || "Unclassified"
}

/** Template draft built only from entered facts. No model is called; the UI says so. */
export function draftDescription(
  p: { name: string; family: string; range: string; nature: Nature; definition: Definition },
  style: "Customer-friendly" | "Technical summary" | "Short portal description",
  componentNames: string[],
): string {
  const d = p.definition
  const nm = d.customer_name || p.name
  const speed = p.nature === "Digital service" && d.down && d.up ? `${d.down}/${d.up} Mbps` : ""
  const price = Number(d.price) > 0 ? `R${Number(d.price).toFixed(2).replace(/\.00$/, "")}${d.recurring ? " per month" : ""} excluding tax` : ""
  const term = d.recurring && d.term ? `${d.term}-month term` : ""
  const fees = d.fees.filter((f) => f.enabled && f.mode === "Charge").map((f) => `${f.name.toLowerCase()} fee`)
  const stock = p.nature === "Physical item" && d.stock !== "None" ? `${d.stock.toLowerCase()} tracked` : ""
  if (style === "Short portal description") return `${nm}${speed ? `: ${speed}` : ""}${componentNames.length ? `, includes ${componentNames.join(", ")}` : ""}.`
  if (style === "Technical summary") {
    return [
      `${nm} (${p.family || "unclassified"}, ${p.range || "no range"}).`,
      [speed && `${speed} symmetrical speeds`, stock, term].filter(Boolean).join("; ") + (speed || stock || term ? "." : ""),
      componentNames.length ? `Includes: ${componentNames.join(", ")}.` : "",
      fees.length ? `Customer-chargeable: ${fees.join(", ")}.` : "",
      price ? `Price: ${price}.` : "",
    ].filter(Boolean).join(" ")
  }
  return [
    `${nm}${speed ? ` gives you ${speed} speeds` : ""}.`,
    componentNames.length ? `It comes with ${componentNames.join(" and ")}.` : "",
    term ? `Available on a ${d.term}-month term.` : "",
    price ? `From ${price}.` : "",
    fees.length ? `Some services may carry a ${fees.join(", ")}; see the fee schedule.` : "",
  ].filter(Boolean).join(" ")
}
