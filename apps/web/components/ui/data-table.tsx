"use client"

import { type ReactNode } from "react"
import { MoreVertical } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { EmptyState } from "@/components/ui/empty-state"
import { cn } from "@/lib/utils"

export interface DataColumn<T = Record<string, unknown>> {
  key: keyof T | string
  label: string
  /** Custom cell renderer */
  render?: (row: T, value: unknown) => ReactNode
  align?: "left" | "right" | "center"
  width?: string
}

export interface RowAction<T = Record<string, unknown>> {
  label: string
  icon?: ReactNode
  onClick: (row: T) => void
  variant?: "default" | "destructive"
}

interface DataTableProps<T extends { id: string | number }> {
  columns: DataColumn<T>[]
  rows: T[]
  rowActions?: RowAction<T>[]
  /** Renders when rows is empty */
  emptyTitle?: string
  emptyDescription?: string
  emptyIcon?: ReactNode
  /** Extra className for the wrapper div */
  className?: string
  loading?: boolean
  /** Max rows before scrolling */
  maxRows?: number
  onRowClick?: (row: T) => void
}

/**
 * Uniform data table with consistent column headers, row hover, and action menu.
 * Replaces ad-hoc <table> implementations across all modules.
 */
export function DataTable<T extends { id: string | number }>({
  columns,
  rows,
  rowActions,
  emptyTitle = "No data",
  emptyDescription,
  emptyIcon,
  className,
  loading,
  onRowClick,
}: DataTableProps<T>) {
  if (loading) {
    return (
      <div className="rounded-xl border border-border overflow-hidden">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={String(c.key)}>{c.label}</th>
              ))}
              {rowActions && <th />}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 5 }).map((_, i) => (
              <tr key={i} className="border-b border-border/50">
                {columns.map((c) => (
                  <td key={String(c.key)}>
                    <div className="h-4 w-24 animate-pulse rounded bg-muted" />
                  </td>
                ))}
                {rowActions && <td />}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <div className={cn("rounded-xl border border-border", className)}>
        <EmptyState
          icon={emptyIcon}
          title={emptyTitle}
          description={emptyDescription}
        />
      </div>
    )
  }

  return (
    <div className={cn("rounded-xl border border-border overflow-hidden", className)}>
      <div className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={String(c.key)}
                  className={cn(
                    c.align === "right" && "text-right",
                    c.align === "center" && "text-center",
                  )}
                  style={c.width ? { width: c.width } : undefined}
                >
                  {c.label}
                </th>
              ))}
              {rowActions && <th className="w-10" />}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={cn(onRowClick && "cursor-pointer")}
              >
                {columns.map((c) => {
                  const val = (row as Record<string, unknown>)[c.key as string]
                  return (
                    <td
                      key={String(c.key)}
                      className={cn(
                        c.align === "right" && "text-right tabular-nums",
                        c.align === "center" && "text-center",
                      )}
                    >
                      {c.render ? c.render(row, val) : String(val ?? "—")}
                    </td>
                  )
                })}
                {rowActions && (
                  <td className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-40">
                        {rowActions.map((action, i) => (
                          <DropdownMenuItem
                            key={i}
                            onClick={(e) => {
                              e.stopPropagation()
                              action.onClick(row)
                            }}
                            className={cn(
                              action.variant === "destructive" &&
                                "text-destructive focus:text-destructive focus:bg-destructive/10",
                            )}
                          >
                            {action.icon && <span className="mr-2">{action.icon}</span>}
                            {action.label}
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
