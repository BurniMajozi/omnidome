"use client"

import React, { useCallback, useEffect, useState } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { NotConnected } from "@/components/ui/not-connected"
import { Share2, Copy, Check, Users, Mail, Globe, AlertTriangle } from "lucide-react"
import {
  loadPortalShares,
  revokePortalShare,
  sharePortalPage,
  type PortalShare,
  type PortalShareCreated,
  type ShareEmailStatus,
} from "@/lib/portal-api"
import type { Loadable } from "@/lib/service-state"

interface DomeStudioShareModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Saved page id; null when the page has not been saved yet. */
  pageId: string | null
  pageTitle: string
}

const EMAIL_STATUS_COPY: Record<ShareEmailStatus, { label: string; tone: string; detail: string }> = {
  sent: { label: "Email sent", tone: "text-emerald-400", detail: "The recipient was emailed the review link." },
  suppressed: { label: "Not emailed", tone: "text-amber-400", detail: "This address is on the suppression list, so no email was sent. Share the link yourself." },
  no_mailbox: { label: "Not emailed", tone: "text-amber-400", detail: "No single active mailbox is configured in Communication, so no email was sent. Share the link yourself." },
  failed: { label: "Email failed", tone: "text-red-400", detail: "The email could not be sent. The link was still created; share it yourself." },
}

export function DomeStudioShareModal({ open, onOpenChange, pageId, pageTitle }: DomeStudioShareModalProps) {
  const [email, setEmail] = useState("")
  const [hours, setHours] = useState(168)
  const [message, setMessage] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<PortalShareCreated | null>(null)
  const [copied, setCopied] = useState(false)
  const [shares, setShares] = useState<Loadable<{ items: PortalShare[] }>>({ state: "loading" })

  const refresh = useCallback(async () => {
    if (!pageId) return
    setShares(await loadPortalShares(pageId))
  }, [pageId])

  useEffect(() => {
    if (open && pageId) {
      setShares({ state: "loading" })
      void refresh()
    }
    if (!open) {
      setCreated(null)
      setError(null)
    }
  }, [open, pageId, refresh])

  const handleShare = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!pageId || !email.trim()) return
    setBusy(true)
    setError(null)
    const res = await sharePortalPage(pageId, {
      recipient_email: email.trim(),
      expires_in_hours: hours,
      message: message.trim() || undefined,
    })
    setBusy(false)
    if (!res.ok) {
      setError(res.message)
      return
    }
    setCreated(res.data)
    setEmail("")
    setMessage("")
    void refresh()
  }

  const handleCopy = async () => {
    if (!created || typeof navigator === "undefined" || !navigator.clipboard) return
    try {
      await navigator.clipboard.writeText(created.share_url)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setError("Copy failed. Select the link and copy it manually.")
    }
  }

  const handleRevoke = async (id: string) => {
    setError(null)
    const res = await revokePortalShare(id)
    if (!res.ok) setError(res.message)
    void refresh()
  }

  const status = created ? EMAIL_STATUS_COPY[created.email_status] : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md border-border bg-card sm:max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="rounded-lg bg-cyan-500/20 p-2 text-cyan-400">
              <Share2 className="h-5 w-5" />
            </div>
            <div>
              <DialogTitle className="text-base font-semibold text-foreground">Share for review</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                Creates an expiring private preview link for <span className="font-medium text-foreground">{pageTitle || "this page"}</span>. Works for drafts.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {!pageId ? (
          <div className="rounded-lg border border-dashed border-border bg-secondary/20 p-5 text-center text-xs text-muted-foreground">
            Save the page first. Only saved pages can be shared.
          </div>
        ) : (
          <div className="space-y-4 py-2">
            <form onSubmit={handleShare} className="space-y-2 rounded-lg border border-border bg-secondary/20 p-3">
              <Label className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                <Mail className="h-3.5 w-3.5 text-cyan-400" />
                Recipient
              </Label>
              <Input type="email" required placeholder="name@example.com" value={email} onChange={(e) => setEmail(e.target.value)} className="h-9 bg-background text-xs" />
              <div className="flex gap-2">
                <div className="flex-1">
                  <Label className="text-[11px] text-muted-foreground">Expires after (hours, 1 to 720)</Label>
                  <Input
                    type="number"
                    min={1}
                    max={720}
                    value={hours}
                    onChange={(e) => setHours(Math.min(720, Math.max(1, Number(e.target.value) || 1)))}
                    className="h-9 bg-background text-xs"
                  />
                </div>
              </div>
              <Input placeholder="Optional message" value={message} onChange={(e) => setMessage(e.target.value)} className="h-9 bg-background text-xs" maxLength={500} />
              <Button type="submit" size="sm" disabled={busy || !email.trim()} className="h-9 w-full bg-cyan-500 text-xs font-semibold text-cyan-950 hover:bg-cyan-400">
                {busy ? "Creating link..." : "Create link and email recipient"}
              </Button>
            </form>

            {error && (
              <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {created && status && (
              <div className="space-y-2 rounded-lg border border-border bg-secondary/20 p-3">
                <p className={`text-xs font-semibold ${status.tone}`}>
                  {status.label} ({created.recipient_email})
                </p>
                <p className="text-[11px] text-muted-foreground">{status.detail}</p>
                <Label className="text-[11px] text-muted-foreground">Review link (shown only now; it cannot be retrieved later)</Label>
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <Globe className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                    <Input readOnly value={created.share_url} onFocus={(e) => e.currentTarget.select()} className="bg-secondary/40 pl-8 font-mono text-xs text-muted-foreground" />
                  </div>
                  <Button size="sm" variant="outline" onClick={handleCopy} className="h-9 text-xs font-medium">
                    {copied ? (
                      <>
                        <Check className="mr-1.5 h-3.5 w-3.5 text-emerald-400" />
                        Copied
                      </>
                    ) : (
                      <>
                        <Copy className="mr-1.5 h-3.5 w-3.5" />
                        Copy
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}

            <div className="space-y-2">
              <Label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Users className="h-3.5 w-3.5" />
                Existing links
              </Label>
              {shares.state !== "ready" ? (
                <NotConnected loadable={shares} service="Portal Builder" onRetry={() => void refresh()} />
              ) : shares.data.items.length === 0 ? (
                <p className="text-[11px] text-muted-foreground">No review links created for this page yet.</p>
              ) : (
                <div className="max-h-48 space-y-2 divide-y divide-border/40 overflow-y-auto">
                  {shares.data.items.map((s) => (
                    <div key={s.id} className="flex items-center justify-between gap-2 pt-2 text-xs first:pt-0">
                      <div className="min-w-0">
                        <p className="truncate font-medium text-foreground">{s.recipient_email}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {s.view_count} view{s.view_count === 1 ? "" : "s"} · expires {new Date(s.expires_at).toLocaleString()}
                          {s.email_status ? ` · email ${s.email_status}` : ""}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <Badge variant="secondary" className={`px-2 py-0.5 text-[10px] ${s.active ? "bg-emerald-500/20 text-emerald-300" : "text-muted-foreground"}`}>
                          {s.revoked_at ? "Revoked" : s.active ? "Active" : "Expired"}
                        </Badge>
                        {s.active && (
                          <Button variant="outline" size="sm" className="h-6 px-2 text-[11px]" onClick={() => void handleRevoke(s.id)}>
                            Revoke
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        <DialogFooter className="border-t border-border pt-3">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} className="text-xs">
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
