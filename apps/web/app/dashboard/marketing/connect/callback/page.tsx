"use client"

/**
 * Landing page for the in-app account connect flow. The provider redirects here with ?st=<state>
 * plus its own params. We hand every param to the marketing service, render a picker if one is
 * needed, then return to the hub with a success/failure banner. The user never lands on the
 * provider's own dashboard.
 */

import { Suspense, useCallback, useEffect, useRef, useState } from "react"
import { useSearchParams } from "next/navigation"
import { AlertTriangle, CheckCircle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { SelectionPicker } from "@/components/modules/marketing/connect-flow"
import {
  completeConnect,
  resultMessage,
  safeReturnPath,
  selectConnect,
  takeConnectReturn,
  type ConnectCompleteResponse,
} from "@/lib/marketing-zernio-api"
import { invalidateMarketingCache } from "@/lib/marketing-api"

const DEFAULT_RETURN = "/dashboard?section=marketing&marketing_tab=connections"

type View =
  | { kind: "working" }
  | { kind: "pick"; step: string; options: Array<Record<string, unknown> & { id: string }>; multiple: boolean; platform: string }
  | { kind: "done"; message: string }
  | { kind: "failed"; message: string }

function withBanner(path: string, kind: "success" | "error", message: string): string {
  const u = new URL(path, "http://local")
  u.searchParams.set("connect", kind)
  u.searchParams.set("connect_msg", message.slice(0, 200))
  return `${u.pathname}${u.search}${u.hash}`
}

function CallbackInner() {
  const search = useSearchParams()
  const [view, setView] = useState<View>({ kind: "working" })
  const [busy, setBusy] = useState(false)
  const [pickError, setPickError] = useState<string | null>(null)
  const stateRef = useRef<string>("")
  const returnRef = useRef<string>(DEFAULT_RETURN)
  const ranRef = useRef(false)

  const finish = useCallback((kind: "success" | "error", message: string, delayMs = 1800) => {
    invalidateMarketingCache()
    setView(kind === "success" ? { kind: "done", message } : { kind: "failed", message })
    window.setTimeout(() => window.location.replace(withBanner(returnRef.current, kind, message)), delayMs)
  }, [])

  const handle = useCallback(
    (r: { ok: boolean; status: number; data: ConnectCompleteResponse | null; error: string | null }) => {
      if (!r.ok || !r.data) {
        // 409 already_completed usually means a refresh of this page after success.
        finish("error", resultMessage(r), 3500)
        return
      }
      const d = r.data
      if (d.return_to) returnRef.current = safeReturnPath(d.return_to, returnRef.current)
      if (d.status === "connected") {
        const names = d.accounts.map((a) => a.display_name || a.username || a.platform).filter(Boolean)
        const failed = d.failed?.length ? ` ${d.failed.length} could not be connected: ${d.failed.map((f) => f.message).join("; ")}` : ""
        finish(d.failed?.length && d.accounts.length === 0 ? "error" : "success", `${names.length ? names.join(", ") : "Account"} connected.${failed}`)
      } else if (d.status === "selection_required") {
        setView({ kind: "pick", step: d.step, options: d.options as never, multiple: d.multiple, platform: d.platform })
      } else {
        const msg = d.message || (d.reason ? `${d.error}: ${d.reason}` : d.error.replace(/_/g, " "))
        finish("error", `${d.platform ?? "Connection"} was not connected. ${msg}`, 3500)
      }
    },
    [finish],
  )

  useEffect(() => {
    if (ranRef.current) return
    ranRef.current = true
    const st = search.get("st") ?? ""
    const remembered = takeConnectReturn()
    returnRef.current = safeReturnPath(remembered, DEFAULT_RETURN)
    stateRef.current = st
    if (!st) {
      setView({ kind: "failed", message: "This page is only reached from a connect flow, and it has no connection state. Start again from Connections." })
      return
    }
    const params: Record<string, string> = {}
    search.forEach((v, k) => {
      if (k !== "st") params[k] = v
    })
    void completeConnect(st, params).then(handle)
  }, [search, handle])

  const submitPick = async (ids: string[], accountType?: string | null) => {
    setBusy(true)
    setPickError(null)
    const r = await selectConnect(stateRef.current, ids, accountType)
    setBusy(false)
    if (!r.ok) {
      // A bad pick can be retried; an expired/used state cannot.
      setPickError(resultMessage(r))
      return
    }
    handle(r)
  }

  const goBack = () => window.location.replace(returnRef.current)

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-xl flex-col justify-center gap-4 p-6">
      {view.kind === "working" && (
        <div className="flex items-center gap-3 text-foreground" role="status">
          <Loader2 className="h-5 w-5 animate-spin" />
          <p className="text-sm">Finishing your connection…</p>
        </div>
      )}
      {view.kind === "pick" && (
        <SelectionPicker
          step={view.step}
          options={view.options}
          multiple={view.multiple}
          busy={busy}
          error={pickError}
          onSubmit={submitPick}
          onCancel={() => finish("error", "Connection cancelled. Nothing was connected.", 600)}
        />
      )}
      {view.kind === "done" && (
        <div className="flex items-start gap-3 text-emerald-500" role="status">
          <CheckCircle className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <p className="text-sm font-medium">{view.message}</p>
            <p className="text-xs text-muted-foreground">Taking you back…</p>
          </div>
        </div>
      )}
      {view.kind === "failed" && (
        <div className="space-y-3" role="alert">
          <div className="flex items-start gap-3 text-red-400">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
            <p className="text-sm">{view.message}</p>
          </div>
          <Button variant="outline" onClick={goBack}>
            Back to Connections
          </Button>
        </div>
      )}
    </div>
  )
}

export default function MarketingConnectCallbackPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">Loading…</div>}>
      <CallbackInner />
    </Suspense>
  )
}
