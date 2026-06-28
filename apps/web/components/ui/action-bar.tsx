"use client"

import { type ReactNode, type ChangeEvent } from "react"
import { Search } from "lucide-react"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface ActionBarProps {
  /** Rendered on the left — search field, filter chips, etc. */
  left?: ReactNode
  /** Rendered on the right — action buttons */
  right?: ReactNode
  /** Convenience: renders a controlled search input on the left */
  search?: {
    value: string
    onChange: (v: string) => void
    placeholder?: string
  }
  className?: string
}

/**
 * Uniform action toolbar displayed above lists and tables.
 * Z-flow: search/filters LEFT → actions RIGHT (primary CTA rightmost).
 *
 * Usage:
 *   <ActionBar
 *     search={{ value: q, onChange: setQ, placeholder: "Search agents…" }}
 *     right={
 *       <>
 *         <Button variant="outline" size="sm"><Filter />Filter</Button>
 *         <Button variant="cta" size="sm"><Plus />New Agent</Button>
 *       </>
 *     }
 *   />
 */
export function ActionBar({ left, right, search, className }: ActionBarProps) {
  return (
    <div className={cn("action-toolbar", className)}>
      <div className="action-toolbar-left">
        {search && (
          <div className="relative w-full max-w-xs">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search.value}
              onChange={(e: ChangeEvent<HTMLInputElement>) => search.onChange(e.target.value)}
              placeholder={search.placeholder ?? "Search…"}
              className="h-8 pl-8 text-sm"
            />
          </div>
        )}
        {left}
      </div>
      {right && <div className="action-toolbar-right">{right}</div>}
    </div>
  )
}
