"use client"

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  getBrandOptions,
  getDatasets,
  listBrandKits,
  unwrapKits,
  type BrandKit,
  type BrandOptions,
  type DatasetCatalog,
  type DatasetDef,
} from "@/lib/bi-studio-api"

export const fieldCls =
  "h-8 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
export const textareaCls =
  "w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"

export function Modal({ title, onClose, children, wide, full, footer }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean; full?: boolean; footer?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    ref.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("keydown", onKey)
      prev?.focus?.()
    }
  }, [onClose])
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-3" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn("flex max-h-[92vh] w-full flex-col rounded-lg border border-border bg-card shadow-2xl outline-none", full ? "h-[94vh] max-w-[1500px]" : wide ? "max-w-5xl" : "max-w-xl")}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          <button type="button" aria-label="Close" onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
        {footer && <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border px-4 py-3">{footer}</div>}
      </div>
    </div>
  )
}

export function SideDrawer({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose()
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-[80] flex justify-end bg-black/40" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside role="dialog" aria-label={title} className="flex h-full w-full max-w-md flex-col border-l border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          <button type="button" aria-label="Close" onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
      </aside>
    </div>
  )
}

export function Field({ label, children, hint, htmlFor }: { label: string; children: ReactNode; hint?: string; htmlFor?: string }) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  )
}

export function Section({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="space-y-2 border-b border-border/70 px-3 py-3 last:border-b-0">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  )
}

export function IconBtn({
  label,
  onClick,
  children,
  disabled,
  active,
  className,
}: {
  label: string
  onClick?: () => void
  children: ReactNode
  disabled?: boolean
  active?: boolean
  className?: string
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:opacity-40",
        active && "bg-primary/15 text-primary",
        className,
      )}
    >
      {children}
    </button>
  )
}

// ── shared studio data (dataset catalogue, brand kits) ───────────────
interface StudioCtxValue {
  catalog: DatasetCatalog | null
  datasets: Map<string, DatasetDef>
  catalogError: string | null
  kits: BrandKit[]
  kitsLoaded: boolean
  options: BrandOptions | null
  reloadKits: () => Promise<void>
  datasetLabel: (id: string) => string
  /** true once a write answered 403 */
  readOnly: boolean
  markReadOnly: () => void
}
const Ctx = createContext<StudioCtxValue | null>(null)
export const useStudio = () => {
  const v = useContext(Ctx)
  if (!v) throw new Error("StudioProvider missing")
  return v
}

export function StudioProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<DatasetCatalog | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [kits, setKits] = useState<BrandKit[]>([])
  const [kitsLoaded, setKitsLoaded] = useState(false)
  const [options, setOptions] = useState<BrandOptions | null>(null)
  const [readOnly, setReadOnly] = useState(false)

  useEffect(() => {
    getDatasets()
      .then(setCatalog)
      .catch((e) => setCatalogError(e instanceof Error ? e.message : "Could not load datasets"))
    getBrandOptions()
      .then(setOptions)
      .catch(() => setOptions(null))
  }, [])
  const reloadKits = useCallback(async () => {
    try {
      setKits(unwrapKits(await listBrandKits()))
    } catch {
      setKits([])
    } finally {
      setKitsLoaded(true)
    }
  }, [])
  useEffect(() => {
    void reloadKits()
  }, [reloadKits])

  const datasets = useMemo(() => new Map((catalog?.datasets ?? []).map((d) => [d.id, d])), [catalog])
  const value: StudioCtxValue = {
    catalog,
    datasets,
    catalogError,
    kits,
    kitsLoaded,
    options,
    reloadKits,
    datasetLabel: (id) => datasets.get(id)?.label ?? id,
    readOnly,
    markReadOnly: () => setReadOnly(true),
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
