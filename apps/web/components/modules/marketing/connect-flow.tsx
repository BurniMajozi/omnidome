"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { AlertTriangle, CheckCircle, Link2, Loader2, RefreshCw, Trash2, Unlink, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { NotConnected } from "@/components/ui/not-connected"
import { useMarketingLoad } from "@/lib/use-marketing-load"
import { invalidateMarketingCache, loadMarketing } from "@/lib/marketing-api"
import {
  connectBluesky,
  connectWhatsAppCredentials,
  completeWhatsAppSignup,
  disconnectAccount,
  getWhatsAppSdkConfig,
  rememberConnectReturn,
  resultMessage,
  startConnect,
  startTelegram,
  telegramStatus,
  type ConnectPlatform,
  type ConnectPlatformsResponse,
  type SelectionOption,
  type TelegramStart,
} from "@/lib/marketing-zernio-api"

export const CONNECTIONS_RETURN = "/dashboard?section=marketing&marketing_tab=connections"

export interface ConnectedRow {
  account_id: string
  platform: string
  username?: string | null
  status?: string | null
  issues?: unknown
}

/** Ads accounts are stored with the provider id (metaads) while the catalog uses meta_ads. */
const norm = (id: string) => id.toLowerCase().replace(/[_-]/g, "")

const FLOW_COPY: Record<string, string> = {
  oauth: "You will be sent to the platform to approve access, then brought straight back here.",
  oauth_select: "You will approve access on the platform, then choose the page, organisation or location to use here in OmniDome.",
  credentials: "Enter your credentials below. They are sent once to connect the account and are not stored by OmniDome.",
  telegram_code: "Link your Telegram bot or channel with a one-time code.",
  embedded_signup: "Connect a WhatsApp Business number with Meta's sign-up window, without leaving OmniDome.",
}

// ── Shared picker (also used by the callback page) ──────────────────────────

export function optionTitle(o: SelectionOption): string {
  return o.name || o.username || o.instagram_username || o.phone_number || o.id
}

export function optionSubtitle(step: string, o: SelectionOption): string {
  const bits: string[] = []
  if (step === "select_page") {
    if (o.username) bits.push(`@${o.username}`)
    if (o.category) bits.push(String(o.category))
  } else if (step === "select_account") {
    if (o.instagram_username) bits.push(`@${o.instagram_username}`)
  } else if (step === "select_organization") {
    bits.push(o.account_type === "personal" ? "Personal profile" : "Organisation")
    if (o.vanity_name) bits.push(String(o.vanity_name))
  } else if (step === "select_location") {
    if (o.address) bits.push(String(o.address))
  } else if (step === "select_phone_number") {
    if (o.phone_number) bits.push(String(o.phone_number))
    if (o.name_status) bits.push(`Name: ${String(o.name_status).toLowerCase().replace(/_/g, " ")}`)
    if (o.quality_rating) bits.push(`Quality: ${String(o.quality_rating).toLowerCase()}`)
  } else if (o.username) bits.push(`@${o.username}`)
  return bits.join(" · ")
}

export const STEP_TITLES: Record<string, string> = {
  select_page: "Choose the Facebook Page to connect",
  select_account: "Choose the Instagram account to connect",
  select_organization: "Choose the LinkedIn profile or organisation",
  select_board: "Choose the Pinterest board",
  select_location: "Choose the Google Business location",
  select_public_profile: "Choose the public profile",
  select_phone_number: "Choose the WhatsApp number",
}

export function SelectionPicker({
  step,
  options,
  multiple,
  busy,
  error,
  onSubmit,
  onCancel,
}: {
  step: string
  options: SelectionOption[]
  multiple: boolean
  busy: boolean
  error: string | null
  onSubmit: (ids: string[], accountType?: string | null) => void
  onCancel: () => void
}) {
  const [picked, setPicked] = useState<string[]>([])
  const toggle = (id: string) =>
    setPicked((p) => (multiple ? (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]) : [id]))
  const submit = () => {
    const first = options.find((o) => o.id === picked[0])
    onSubmit(picked, step === "select_organization" ? first?.account_type ?? null : null)
  }
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-foreground">{STEP_TITLES[step] ?? "Choose what to connect"}</h3>
        <p className="text-sm text-muted-foreground">
          {multiple ? "You can pick more than one." : "Pick one."} Nothing is connected until you confirm.
        </p>
      </div>
      {options.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
          The platform returned nothing to choose from. Check that the account you approved owns a page, organisation or number, then try again.
        </p>
      ) : (
        <ul className="max-h-80 space-y-2 overflow-y-auto">
          {options.map((o) => {
            const on = picked.includes(o.id)
            return (
              <li key={o.id}>
                <button
                  type="button"
                  onClick={() => toggle(o.id)}
                  aria-pressed={on}
                  className={`flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors ${on ? "border-primary bg-primary/10" : "border-border bg-card hover:bg-accent/50"}`}
                >
                  <span className={`flex h-5 w-5 shrink-0 items-center justify-center ${multiple ? "rounded" : "rounded-full"} border ${on ? "border-primary bg-primary text-primary-foreground" : "border-border"}`}>
                    {on && <CheckCircle className="h-3.5 w-3.5" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-foreground">{optionTitle(o)}</span>
                    <span className="block truncate text-xs text-muted-foreground">{optionSubtitle(step, o) || o.id}</span>
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-400">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button onClick={submit} disabled={busy || picked.length === 0}>
          {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          Connect {picked.length > 1 ? `${picked.length} selected` : "selected"}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

// ── Per-platform dialog ─────────────────────────────────────────────────────

declare global {
  interface Window {
    FB?: {
      init: (o: Record<string, unknown>) => void
      login: (cb: (r: { authResponse?: { code?: string } | null }) => void, o: Record<string, unknown>) => void
    }
    fbAsyncInit?: () => void
  }
}

function loadFacebookSdk(appId: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const init = () => {
      try {
        window.FB?.init({ appId, autoLogAppEvents: true, xfbml: false, version: "v21.0" })
        resolve()
      } catch (e) {
        reject(e)
      }
    }
    if (window.FB) return init()
    window.fbAsyncInit = init
    const existing = document.getElementById("facebook-jssdk")
    if (existing) return
    const s = document.createElement("script")
    s.id = "facebook-jssdk"
    s.async = true
    s.src = "https://connect.facebook.net/en_US/sdk.js"
    s.onerror = () => reject(new Error("Meta's sign-up script could not be loaded. A browser extension or the site's content security policy may be blocking connect.facebook.net."))
    document.body.appendChild(s)
  })
}

function WhatsAppSignupPanel({ onDone }: { onDone: (msg: string) => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [adv, setAdv] = useState({ access_token: "", waba_id: "", phone_number_id: "", pin: "" })
  const sessionRef = useRef<{ code?: string; waba?: string; phone?: string; coexistence?: boolean; state?: string; submitted?: boolean }>({})

  useEffect(() => {
    const onMessage = (ev: MessageEvent) => {
      if (typeof ev.origin !== "string" || !/(^|\.)facebook\.com$/.test(new URL(ev.origin).hostname)) return
      let data: unknown = ev.data
      if (typeof data === "string") {
        try {
          data = JSON.parse(data)
        } catch {
          return
        }
      }
      const d = data as { type?: string; event?: string; data?: Record<string, unknown> } | null
      if (!d || d.type !== "WA_EMBEDDED_SIGNUP") return
      if (d.event === "FINISH" || d.event === "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING") {
        sessionRef.current.waba = String(d.data?.waba_id ?? "")
        sessionRef.current.phone = String(d.data?.phone_number_id ?? "")
        sessionRef.current.coexistence = d.event !== "FINISH"
        void trySubmit()
      } else if (d.event === "CANCEL") {
        setBusy(false)
        setError("Sign-up was cancelled before it finished. Nothing was connected.")
      }
    }
    window.addEventListener("message", onMessage)
    return () => window.removeEventListener("message", onMessage)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const trySubmit = async () => {
    const s = sessionRef.current
    if (s.submitted || !s.code || !s.state || (!s.waba && !s.phone)) return
    s.submitted = true
    const r = await completeWhatsAppSignup({
      state: s.state,
      code: s.code,
      waba_id: s.waba || undefined,
      phone_number_id: s.phone || undefined,
      is_coexistence: Boolean(s.coexistence),
    })
    setBusy(false)
    if (!r.ok) {
      s.submitted = false
      setError(resultMessage(r))
      return
    }
    invalidateMarketingCache()
    onDone("WhatsApp number connected.")
  }

  const start = async () => {
    setBusy(true)
    setError(null)
    sessionRef.current = {}
    const cfg = await getWhatsAppSdkConfig()
    if (cfg.state !== "ready") {
      setBusy(false)
      setError(cfg.state === "error" ? cfg.message || "WhatsApp sign-up is not configured." : "The marketing service is not reachable.")
      return
    }
    try {
      await loadFacebookSdk(cfg.data.app_id)
    } catch (e) {
      setBusy(false)
      setError(e instanceof Error ? e.message : "Could not load Meta's sign-up script.")
      return
    }
    sessionRef.current.state = cfg.data.state
    window.FB?.login(
      (resp) => {
        const code = resp.authResponse?.code
        if (!code) {
          setBusy(false)
          setError("Meta did not return an authorisation code. The window was closed or access was declined.")
          return
        }
        sessionRef.current.code = code
        void trySubmit()
      },
      {
        config_id: cfg.data.config_id,
        response_type: "code",
        override_default_response_type: true,
        extras: { setup: {}, sessionInfoVersion: 3 },
      },
    )
  }

  const submitAdvanced = async () => {
    setBusy(true)
    setError(null)
    const r = await connectWhatsAppCredentials({
      access_token: adv.access_token.trim(),
      waba_id: adv.waba_id.trim(),
      phone_number_id: adv.phone_number_id.trim(),
      pin: adv.pin.trim() || undefined,
    })
    setBusy(false)
    setAdv((a) => ({ ...a, access_token: "" }))
    if (!r.ok) return setError(resultMessage(r))
    invalidateMarketingCache()
    onDone(r.data?.warning ? `WhatsApp number connected. ${r.data.warning}` : "WhatsApp number connected.")
  }

  return (
    <div className="space-y-3">
      <Button onClick={start} disabled={busy}>
        {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Link2 className="mr-2 h-4 w-4" />}
        Start WhatsApp sign-up
      </Button>
      <p className="text-xs text-muted-foreground">
        Opens Meta&apos;s sign-up window. Requires the WhatsApp app credentials to be configured on the server.
      </p>
      <button type="button" className="text-xs text-primary underline-offset-2 hover:underline" onClick={() => setShowAdvanced((v) => !v)}>
        {showAdvanced ? "Hide" : "Use a system-user access token instead"}
      </button>
      {showAdvanced && (
        <div className="space-y-2 rounded-lg border border-border p-3">
          <Input type="password" autoComplete="off" placeholder="System user access token" value={adv.access_token} onChange={(e) => setAdv({ ...adv, access_token: e.target.value })} />
          <Input placeholder="WhatsApp Business Account ID" value={adv.waba_id} onChange={(e) => setAdv({ ...adv, waba_id: e.target.value })} />
          <Input placeholder="Phone number ID" value={adv.phone_number_id} onChange={(e) => setAdv({ ...adv, phone_number_id: e.target.value })} />
          <Input placeholder="6-digit registration PIN (optional)" inputMode="numeric" maxLength={6} value={adv.pin} onChange={(e) => setAdv({ ...adv, pin: e.target.value })} />
          <Button size="sm" onClick={submitAdvanced} disabled={busy || !adv.access_token || !adv.waba_id || !adv.phone_number_id}>
            Connect with token
          </Button>
          <p className="text-xs text-muted-foreground">The token is forwarded once to connect the number and is not stored by OmniDome. Connecting re-points that account&apos;s WhatsApp webhook.</p>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-400">
          {error}
        </p>
      )}
    </div>
  )
}

function TelegramPanel({ onDone }: { onDone: (msg: string) => void }) {
  const [info, setInfo] = useState<TelegramStart | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const start = async () => {
    setBusy(true)
    setError(null)
    const r = await startTelegram()
    setBusy(false)
    if (!r.ok || !r.data) return setError(resultMessage(r))
    setInfo(r.data)
  }

  useEffect(() => {
    if (!info) return
    let alive = true
    const t = setInterval(async () => {
      const s = await telegramStatus(info.state)
      if (!alive || s.state !== "ready") return
      if (s.data.status === "connected") {
        alive = false
        clearInterval(t)
        invalidateMarketingCache()
        onDone("Telegram connected.")
      } else if (s.data.status === "expired") {
        alive = false
        clearInterval(t)
        setInfo(null)
        setError("That code expired. Start again to get a new one.")
      }
    }, 3000)
    return () => {
      alive = false
      clearInterval(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info])

  return (
    <div className="space-y-3">
      {!info ? (
        <Button onClick={start} disabled={busy}>
          {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          Get a connection code
        </Button>
      ) : (
        <div className="space-y-2 rounded-lg border border-border p-3">
          <p className="text-sm text-muted-foreground">Send this code to {info.bot_username ? `@${info.bot_username}` : "the bot"} on Telegram:</p>
          <p className="select-all font-mono text-2xl font-semibold tracking-widest text-foreground">{info.code}</p>
          {info.instructions?.map((line, i) => (
            <p key={i} className="text-xs text-muted-foreground">
              {line}
            </p>
          ))}
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Waiting for the code to arrive. This page updates by itself.
          </p>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-400">
          {error}
        </p>
      )}
    </div>
  )
}

function BlueskyPanel({ onDone }: { onDone: (msg: string) => void }) {
  const [identifier, setIdentifier] = useState("")
  const [pw, setPw] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submit = async () => {
    setBusy(true)
    setError(null)
    const r = await connectBluesky(identifier.trim(), pw.trim())
    setBusy(false)
    setPw("")
    if (!r.ok) return setError(resultMessage(r))
    invalidateMarketingCache()
    onDone("Bluesky connected.")
  }
  return (
    <div className="space-y-2">
      <Input placeholder="Handle, e.g. acme.bsky.social" autoComplete="off" value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
      <Input type="password" autoComplete="off" placeholder="App password (xxxx-xxxx-xxxx-xxxx)" value={pw} onChange={(e) => setPw(e.target.value)} />
      <p className="text-xs text-muted-foreground">Create an app password in Bluesky under Settings, Privacy and security, App passwords. Do not use your main password.</p>
      <Button onClick={submit} disabled={busy || !identifier.trim() || !pw.trim()}>
        {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
        Connect Bluesky
      </Button>
      {error && (
        <p role="alert" className="text-sm text-red-400">
          {error}
        </p>
      )}
    </div>
  )
}

export function ConnectPlatformDialog({
  platform,
  category,
  returnTo = CONNECTIONS_RETURN,
  reconnectAccountId,
  onClose,
  onConnected,
}: {
  platform: ConnectPlatform | null
  category: "social" | "ads"
  returnTo?: string
  reconnectAccountId?: string
  onClose: () => void
  onConnected: (message: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loginMethod, setLoginMethod] = useState("instagram_login")
  const [loginMode, setLoginMode] = useState("classic")

  useEffect(() => {
    setError(null)
    setBusy(false)
  }, [platform?.id])

  if (!platform) return null
  const flow = platform.flow
  const redirectFlow = flow === "oauth" || flow === "oauth_select"

  const go = async () => {
    setBusy(true)
    setError(null)
    const r = await startConnect({
      platform: platform.id,
      category,
      return_to: returnTo,
      reconnect_account_id: reconnectAccountId,
      login_method: platform.id === "instagram" ? loginMethod : undefined,
      login_mode: platform.id === "meta_ads" ? loginMode : undefined,
    })
    if (!r.ok || !r.data) {
      setBusy(false)
      return setError(resultMessage(r))
    }
    if (r.data.status === "already_connected") {
      setBusy(false)
      invalidateMarketingCache()
      onConnected(`${platform.label} is already connected and valid.`)
      return
    }
    if (!r.data.auth_url) {
      setBusy(false)
      return setError("The provider did not return an authorisation address. Nothing was connected.")
    }
    rememberConnectReturn(returnTo)
    window.location.assign(r.data.auth_url)
  }

  const done = (msg: string) => {
    onConnected(msg)
  }

  return (
    <Dialog open onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{reconnectAccountId ? "Reconnect" : "Connect"} {platform.label}</DialogTitle>
          <DialogDescription>{FLOW_COPY[flow] ?? "Connect this account."}</DialogDescription>
        </DialogHeader>
        {platform.id === "instagram" && redirectFlow && (
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">Sign in with</span>
            <select value={loginMethod} onChange={(e) => setLoginMethod(e.target.value)} className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
              <option value="instagram_login">Instagram login (professional account)</option>
              <option value="facebook_login">Facebook login (via a Facebook Page)</option>
            </select>
          </label>
        )}
        {platform.id === "meta_ads" && (
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">Meta login type</span>
            <select value={loginMode} onChange={(e) => setLoginMode(e.target.value)} className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
              <option value="classic">Classic (personal Facebook login)</option>
              <option value="business">Business login</option>
            </select>
          </label>
        )}
        {redirectFlow && (
          <>
            <Button onClick={go} disabled={busy}>
              {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Link2 className="mr-2 h-4 w-4" />}
              Continue to {platform.label}
            </Button>
            {error && (
              <p role="alert" className="text-sm text-red-400">
                {error}
              </p>
            )}
          </>
        )}
        {flow === "credentials" && platform.id === "bluesky" && <BlueskyPanel onDone={done} />}
        {flow === "credentials" && platform.id !== "bluesky" && <p className="text-sm text-muted-foreground">This platform has no in-app credentials form yet.</p>}
        {flow === "telegram_code" && <TelegramPanel onDone={done} />}
        {flow === "embedded_signup" && <WhatsAppSignupPanel onDone={done} />}
      </DialogContent>
    </Dialog>
  )
}

// ── Hook: platform catalogue + connected accounts ───────────────────────────

export function useConnectCatalog() {
  const cat = useMarketingLoad<ConnectPlatformsResponse & { configured?: boolean }>("/social/connect/platforms")
  const acc = useMarketingLoad<{ accounts: ConnectedRow[] }>("/social/connected-accounts")
  const reload = useCallback(() => {
    cat.reload()
    acc.reload()
  }, [cat, acc])
  const rows = acc.value.state === "ready" ? acc.value.data.accounts ?? [] : []
  return { cat: cat.value, acc: acc.value, rows, reload }
}

export function accountsForPlatform(rows: ConnectedRow[], platformId: string): ConnectedRow[] {
  const n = norm(platformId)
  return rows.filter((r) => norm(r.platform) === n)
}

// ── Connect picker used by other tabs (composer "+", create-ad modal) ───────

export function ConnectAccountsDialog({
  category,
  returnTo,
  onClose,
  onConnected,
}: {
  category: "social" | "ads"
  returnTo: string
  onClose: () => void
  onConnected: () => void
}) {
  const { cat, acc, rows, reload } = useConnectCatalog()
  const [target, setTarget] = useState<ConnectPlatform | null>(null)
  const list = cat.state === "ready" ? (category === "ads" ? cat.data.ads : cat.data.social) ?? [] : []
  return (
    <>
      <Dialog open={!target} onOpenChange={(o) => (!o ? onClose() : undefined)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{category === "ads" ? "Connect an ads account" : "Connect a social account"}</DialogTitle>
            <DialogDescription>Accounts are connected inside OmniDome. You will never be asked to sign in to a third-party dashboard.</DialogDescription>
          </DialogHeader>
          {cat.state !== "ready" ? (
            <NotConnected loadable={cat} service="The marketing service" onRetry={reload} />
          ) : (
            <div className="grid max-h-[60vh] gap-2 overflow-y-auto sm:grid-cols-2">
              {list.map((p) => {
                const n = accountsForPlatform(rows, p.id).length
                return (
                  <button
                    key={p.id}
                    type="button"
                    disabled={Boolean(p.coming_soon)}
                    onClick={() => setTarget(p)}
                    className="flex items-center justify-between gap-2 rounded-lg border border-border bg-card p-3 text-left hover:bg-accent/50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <span className="text-sm font-medium text-foreground">{p.label}</span>
                    {p.coming_soon ? <Badge variant="outline">Soon</Badge> : n > 0 ? <Badge variant="outline" className="border-emerald-500/40 text-emerald-500">{n} connected</Badge> : <Link2 className="h-4 w-4 text-muted-foreground" />}
                  </button>
                )
              })}
            </div>
          )}
          {acc.state !== "ready" && acc.state !== "loading" && <p className="text-xs text-amber-500">Connected-account status could not be loaded.</p>}
          <DialogFooter>
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConnectPlatformDialog
        platform={target}
        category={category}
        returnTo={returnTo}
        onClose={() => setTarget(null)}
        onConnected={() => {
          setTarget(null)
          reload()
          onConnected()
        }}
      />
    </>
  )
}

// ── Connections tab ─────────────────────────────────────────────────────────

export function ConnectionsPanel({ banner }: { banner?: { kind: "success" | "error"; message: string } | null }) {
  const { cat, acc, rows, reload } = useConnectCatalog()
  const [target, setTarget] = useState<{ platform: ConnectPlatform; category: "social" | "ads"; reconnect?: string } | null>(null)
  const [confirmDisconnect, setConfirmDisconnect] = useState<ConnectedRow | null>(null)
  const [disconnecting, setDisconnecting] = useState(false)
  const [notice, setNotice] = useState<{ kind: "success" | "error"; message: string } | null>(banner ?? null)
  const [health, setHealth] = useState<Record<string, { needsReconnect?: boolean; issues?: string[] }>>({})
  const [checking, setChecking] = useState(false)

  const configured = cat.state === "ready" ? cat.data.configured !== false : true

  const checkHealth = async () => {
    setChecking(true)
    const r = await loadMarketing<{ accounts: Array<{ accountId: string; needsReconnect?: boolean; issues?: string[] }> }>("/social/accounts-health", { force: true })
    setChecking(false)
    if (r.state !== "ready") return setNotice({ kind: "error", message: r.state === "error" ? r.message || "Health check failed." : "Health check is unavailable right now." })
    const m: Record<string, { needsReconnect?: boolean; issues?: string[] }> = {}
    for (const a of r.data.accounts ?? []) m[a.accountId] = { needsReconnect: a.needsReconnect, issues: a.issues }
    setHealth(m)
    reload()
  }

  const doDisconnect = async () => {
    if (!confirmDisconnect) return
    setDisconnecting(true)
    const r = await disconnectAccount(confirmDisconnect.account_id)
    setDisconnecting(false)
    if (!r.ok) {
      setNotice({ kind: "error", message: resultMessage(r) })
    } else {
      setNotice({ kind: "success", message: `Disconnected ${confirmDisconnect.username || confirmDisconnect.platform}.` })
      reload()
    }
    setConfirmDisconnect(null)
  }

  const section = (title: string, category: "social" | "ads", list: ConnectPlatform[]) => (
    <div key={category} className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {list.map((p) => {
          const mine = accountsForPlatform(rows, p.id)
          return (
            <Card key={p.id} className="border-border bg-card">
              <CardContent className="space-y-3 p-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground">{p.label}</p>
                    <p className="text-xs text-muted-foreground">{mine.length > 0 ? `${mine.length} connected` : "Not connected"}</p>
                  </div>
                  {p.coming_soon ? (
                    <Badge variant="outline" className="border-amber-500/40 text-amber-500">Soon</Badge>
                  ) : (
                    <Button size="sm" variant="outline" disabled={!configured} onClick={() => setTarget({ platform: p, category })}>
                      <Link2 className="mr-1 h-3.5 w-3.5" /> {mine.length > 0 ? "Add another" : "Connect"}
                    </Button>
                  )}
                </div>
                {mine.map((a) => {
                  const h = health[a.account_id]
                  const bad = h?.needsReconnect || a.status === "error"
                  return (
                    <div key={a.account_id} className="flex items-center justify-between gap-2 rounded-md border border-border/60 px-2 py-1.5">
                      <div className="min-w-0">
                        <p className="truncate text-xs font-medium text-foreground">{a.username || a.account_id}</p>
                        <p className={`text-[11px] ${bad ? "text-amber-500" : "text-emerald-500"}`}>
                          {bad ? `Needs reconnecting${h?.issues?.length ? `: ${h.issues.join(", ")}` : ""}` : "Connected"}
                        </p>
                      </div>
                      <div className="flex shrink-0 gap-1">
                        {bad && !p.coming_soon && (
                          <Button size="sm" variant="outline" className="h-7 px-2" onClick={() => setTarget({ platform: p, category, reconnect: a.account_id })}>
                            <RefreshCw className="h-3 w-3" />
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" className="h-7 px-2 text-red-400 hover:text-red-300" aria-label={`Disconnect ${a.username || p.label}`} onClick={() => setConfirmDisconnect(a)}>
                          <Unlink className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  )
                })}
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-foreground">Connections</h3>
          <p className="text-sm text-muted-foreground">
            {cat.state === "loading" ? "Loading…" : cat.state === "ready" ? `${rows.length} account(s) connected` : "Connection status unavailable"}. Accounts connect inside OmniDome.
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={checkHealth} disabled={checking || rows.length === 0}>
            <CheckCircle className={`mr-2 h-4 w-4 ${checking ? "animate-pulse" : ""}`} /> Check health
          </Button>
          <Button size="sm" variant="ghost" onClick={reload}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
        </div>
      </div>

      {notice && (
        <div
          role="status"
          className={`flex items-start gap-2 rounded-lg border p-3 ${notice.kind === "success" ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-500" : "border-red-500/30 bg-red-500/5 text-red-400"}`}
        >
          {notice.kind === "success" ? <CheckCircle className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
          <p className="flex-1 text-sm">{notice.message}</p>
          <button aria-label="Dismiss" onClick={() => setNotice(null)}>
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {cat.state !== "ready" && <NotConnected loadable={cat} service="The marketing service" onRetry={reload} />}
      {cat.state === "ready" && !configured && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-500">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>Connecting is disabled: the social provider key is not configured on the server (operator action: set ZERNIO_API_KEY).</p>
        </div>
      )}
      {acc.state !== "ready" && acc.state !== "loading" && cat.state === "ready" && (
        <p className="text-xs text-amber-500">Your connected accounts could not be loaded, so connection badges may be missing.</p>
      )}
      {cat.state === "ready" && section("Social and messaging", "social", cat.data.social ?? [])}
      {cat.state === "ready" && (cat.data.ads?.length ?? 0) > 0 && section("Ads accounts", "ads", cat.data.ads)}

      <ConnectPlatformDialog
        platform={target?.platform ?? null}
        category={target?.category ?? "social"}
        reconnectAccountId={target?.reconnect}
        onClose={() => setTarget(null)}
        onConnected={(msg) => {
          setTarget(null)
          setNotice({ kind: "success", message: msg })
          reload()
        }}
      />

      <Dialog open={Boolean(confirmDisconnect)} onOpenChange={(o) => (!o && !disconnecting ? setConfirmDisconnect(null) : undefined)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Disconnect this account?</DialogTitle>
            <DialogDescription>
              {confirmDisconnect?.username || confirmDisconnect?.platform} will stop publishing, receiving messages and syncing analytics. Scheduled posts for it will fail until it is reconnected.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmDisconnect(null)} disabled={disconnecting}>
              Keep connected
            </Button>
            <Button variant="destructive" onClick={doDisconnect} disabled={disconnecting}>
              {disconnecting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
              Disconnect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
