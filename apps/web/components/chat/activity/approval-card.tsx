"use client"

import { useEffect, useState } from "react"
import { Loader2, ShieldAlert } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { decideApproval } from "@/lib/approvals-api"
import { fetchApprovalDetails, type ApprovalDetails } from "@/lib/agent-activity-api"
import { decisionErrorMessage, humanizeTool, riskTone, type AgentApproval } from "@/lib/agent-activity"

const TONE: Record<string, string> = {
  high: "border-destructive/40 bg-destructive/10 text-destructive",
  medium: "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  low: "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  review: "border-border bg-secondary text-muted-foreground",
}

const DONE_LABEL: Record<string, string> = {
  approved: "Approved. The action is running.",
  rejected: "Rejected. The action will not run.",
  expired: "This approval expired.",
}

/** Inline approval for a held mutating tool. Role gating and self-approval are enforced server-side; we show its message. */
export function ApprovalCard({ approval, streaming }: { approval: AgentApproval; streaming: boolean }) {
  const [status, setStatus] = useState(approval.status)
  const [details, setDetails] = useState<ApprovalDetails | null>(null)
  const [showArgs, setShowArgs] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState<"approve" | "reject" | "">("")
  const [error, setError] = useState("")

  useEffect(() => { setStatus(approval.status) }, [approval.status])
  useEffect(() => {
    let live = true
    void fetchApprovalDetails(approval.approval_id).then((d) => {
      if (!live || !d) return
      setDetails(d)
      setStatus(d.status) // refresh: someone may have decided from the approvals queue
    })
    return () => { live = false }
  }, [approval.approval_id])

  async function decide(action: "approve" | "reject") {
    setBusy(action)
    setError("")
    const res = await decideApproval(approval.approval_id, action, action === "reject" ? { reason: reason.trim() } : {})
    if (res.ok) {
      setStatus(action === "approve" ? "approved" : "rejected")
      setRejecting(false)
      const fresh = await fetchApprovalDetails(approval.approval_id)
      if (fresh) { setDetails(fresh); setStatus(fresh.status) }
    } else {
      setError(decisionErrorMessage(res.status, res.message))
      if (res.status === 409) {
        const fresh = await fetchApprovalDetails(approval.approval_id)
        if (fresh) { setDetails(fresh); setStatus(fresh.status) }
      }
    }
    setBusy("")
  }

  const pending = status === "pending"
  const tone = riskTone(approval.risk, details?.jevScore)
  const tool = details?.tool || approval.tool
  const title = details?.title || (tool ? humanizeTool(tool) : "Action needs approval")
  const summary = details?.summary || approval.summary

  return (
    <section aria-label="Action approval" className={cn("rounded-md border bg-card/80 p-3 text-xs", pending ? "border-amber-500/40" : "border-border")}>
      <div className="mb-1.5 flex items-center gap-2">
        <ShieldAlert className="h-4 w-4 shrink-0 text-amber-500" aria-hidden="true" />
        <h3 className="min-w-0 flex-1 truncate text-xs font-semibold text-foreground">{title}</h3>
        <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide", TONE[tone])}>
          {tone === "review" ? "Needs review" : `${tone} risk`}
        </span>
      </div>
      {summary && <p className="break-words text-muted-foreground">{summary}</p>}
      {approval.reference && <p className="mt-0.5 text-[11px] text-muted-foreground">Ref {approval.reference}</p>}

      {details && (details.jevAction || details.jevReason || details.jevScore !== null) && (
        <p className="mt-1.5 break-words rounded bg-secondary/60 p-1.5 text-muted-foreground">
          <span className="font-medium text-foreground">Safety check</span>
          {details.jevScore !== null ? ` · risk ${details.jevScore.toFixed(1)}/5` : ""}
          {details.jevAction ? ` · ${details.jevAction.replace(/_/g, " ")}` : ""}
          {details.jevReason ? `. ${details.jevReason}` : ""}
        </p>
      )}

      {details?.args && (
        <div className="mt-1.5">
          <button type="button" className="text-[11px] text-muted-foreground underline-offset-2 hover:underline" aria-expanded={showArgs} onClick={() => setShowArgs((v) => !v)}>
            {showArgs ? "Hide details" : "Details"}
          </button>
          {showArgs && <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-background/60 p-1.5 text-[11px] text-muted-foreground">{details.args}</pre>}
        </div>
      )}

      <div className="mt-2">
        {!pending ? (
          <p className="font-medium text-foreground">
            {DONE_LABEL[status] ?? `Status: ${status}`}
            {status === "rejected" && details?.rejectionReason ? <span className="font-normal text-muted-foreground"> Reason: {details.rejectionReason}</span> : null}
          </p>
        ) : approval.requested_by_me ? (
          <p className="text-muted-foreground">
            {streaming ? "Waiting for a manager to approve." : "Waiting for approval."} You cannot approve your own request.
          </p>
        ) : (
          <div className="space-y-2">
            {rejecting && (
              <label className="block text-muted-foreground">
                Reason (optional)
                <textarea
                  value={reason}
                  maxLength={500}
                  rows={2}
                  onChange={(e) => setReason(e.target.value)}
                  className="mt-1 w-full resize-none rounded-md border border-border bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/60"
                />
              </label>
            )}
            <div className="flex flex-wrap gap-2">
              {!rejecting && (
                <Button size="sm" className="h-7 gap-1.5" disabled={!!busy} onClick={() => void decide("approve")}>
                  {busy === "approve" && <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" aria-hidden="true" />}Approve
                </Button>
              )}
              {rejecting ? (
                <>
                  <Button size="sm" variant="destructive" className="h-7 gap-1.5" disabled={!!busy} onClick={() => void decide("reject")}>
                    {busy === "reject" && <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" aria-hidden="true" />}Confirm reject
                  </Button>
                  <Button size="sm" variant="ghost" className="h-7" disabled={!!busy} onClick={() => setRejecting(false)}>Cancel</Button>
                </>
              ) : (
                <Button size="sm" variant="outline" className="h-7" disabled={!!busy} onClick={() => setRejecting(true)}>Reject</Button>
              )}
            </div>
          </div>
        )}
        {error && <p role="alert" className="mt-1.5 text-destructive">{error}</p>}
      </div>
    </section>
  )
}
