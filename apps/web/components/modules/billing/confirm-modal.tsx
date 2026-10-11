"use client"

import type { ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { Modal, Note } from "./shared"

/** Small yes/no dialog for irreversible or money-moving actions. `error` shows the server's message inline. */
export function ConfirmModal({
  open,
  onOpenChange,
  title,
  children,
  confirmLabel,
  busy,
  error,
  destructive,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  children: ReactNode
  confirmLabel: string
  busy?: boolean
  error?: string | null
  destructive?: boolean
  onConfirm: () => void
}) {
  return (
    <Modal open={open} onOpenChange={(o) => !busy && onOpenChange(o)} title={title}>
      <div className="space-y-3 text-sm text-muted-foreground">{children}</div>
      {error && <Note tone="error">{error}</Note>}
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" disabled={busy} onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button size="sm" variant={destructive ? "destructive" : "default"} disabled={busy} onClick={onConfirm}>
          {busy ? "Working…" : confirmLabel}
        </Button>
      </div>
    </Modal>
  )
}
