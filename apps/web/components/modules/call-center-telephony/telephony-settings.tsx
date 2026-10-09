"use client"

import { useCallback, useEffect, useState } from "react"
import { CheckCircle2, Loader2, PlugZap, RefreshCcw, ShieldAlert } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { NotConnected } from "@/components/ui/not-connected"
import type { Loadable } from "@/lib/service-state"
import {
  getSipCredentialMeta, getTelephonySettings, getTrunkStatusAdmin, putTelephonySettings, removeSipTrunk,
  saveSipTrunk, testTrunkRegistration, TelephonyApiError,
  type SipCredentialMeta, type SipTrunkForm, type TelephonySettings, type TelephonyStatus,
} from "@/lib/call-center-telephony-api"

const csv = (s: string) => s.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean)

function trunkHeadline(s: TelephonyStatus): { text: string; ok: boolean } {
  if (s.state === "not_configured") return { text: "No SIP trunk configured", ok: false }
  if (s.registered) return { text: s.detail || "Trunk registered", ok: true }
  return { text: s.detail?.startsWith("Trunk not registered") ? s.detail : `Trunk not registered: ${s.last_error || s.state}`, ok: false }
}

export function TelephonySettingsPanel() {
  const [settingsL, setSettingsL] = useState<Loadable<TelephonySettings>>({ state: "loading" })
  const [statusL, setStatusL] = useState<Loadable<TelephonyStatus>>({ state: "loading" })
  const [credL, setCredL] = useState<Loadable<SipCredentialMeta | null>>({ state: "loading" })
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null)

  const [draft, setDraft] = useState<TelephonySettings | null>(null)
  const [prefixes, setPrefixes] = useState("")
  const [blocked, setBlocked] = useState("")
  const [dids, setDids] = useState("")
  const [trunk, setTrunk] = useState<SipTrunkForm>({ host: "", port: "", username: "", password: "", transport: "udp", auth_mode: "registration", caller_id: "" })

  const load = useCallback(async () => {
    const [s, st, c] = await Promise.all([getTelephonySettings(), getTrunkStatusAdmin(), getSipCredentialMeta()])
    setSettingsL(s); setStatusL(st); setCredL(c)
    if (s.state === "ready") {
      setDraft(s.data)
      setPrefixes(s.data.allowed_prefixes.join(", "))
      setBlocked(s.data.blocked_prefixes.join(", "))
      setDids(s.data.dids.join(", "))
    }
  }, [])
  useEffect(() => { void load() }, [load])

  const run = async (key: string, fn: () => Promise<string | void>) => {
    setBusy(key); setMsg(null)
    try {
      const ok = await fn()
      if (ok) setMsg({ kind: "ok", text: ok })
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof TelephonyApiError ? err.message : "Request failed." })
    } finally { setBusy(null) }
  }

  if (settingsL.state !== "ready" || !draft) {
    return (
      <NotConnected
        loadable={settingsL}
        service="Telephony settings"
        onRetry={() => void load()}
        deniedDetail="Telephony settings need a call-center admin role."
        className="py-16"
      />
    )
  }

  const status = statusL.state === "ready" ? statusL.data : null
  const head = status ? trunkHeadline(status) : null
  const sipMeta = credL.state === "ready" ? credL.data : null

  const saveSettings = () => run("settings", async () => {
    const saved = await putTelephonySettings({
      enabled: draft.enabled, dids: csv(dids), allowed_prefixes: csv(prefixes), blocked_prefixes: csv(blocked),
      max_concurrent_calls: draft.max_concurrent_calls, max_call_seconds: draft.max_call_seconds,
      max_calls_per_agent_hour: draft.max_calls_per_agent_hour, recording_enabled: draft.recording_enabled,
      recording_announcement_confirmed: draft.recording_announcement_confirmed,
    })
    setDraft(saved); setSettingsL({ state: "ready", data: saved })
    return "Settings saved."
  })

  const num = (k: "max_concurrent_calls" | "max_call_seconds" | "max_calls_per_agent_hour") => (
    <Input type="number" min={1} value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: Number(e.target.value) })} />
  )

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {msg && (
        <p role="status" className={`lg:col-span-2 rounded-md border px-3 py-2 text-sm ${msg.kind === "ok" ? "border-emerald-500/40 text-emerald-500" : "border-red-500/40 text-red-500"}`}>{msg.text}</p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base"><PlugZap className="h-4 w-4" />Trunk status</CardTitle>
          <CardDescription>Live registration state from the PBX. The test only checks registration; it never places a call.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {statusL.state !== "ready" ? (
            <NotConnected loadable={statusL} service="Trunk status" onRetry={() => void load()} />
          ) : (
            <>
              <div className="flex items-center gap-2">
                <Badge variant={head?.ok ? "default" : "outline"}>{head?.ok ? "Registered" : status?.state === "not_configured" ? "Not configured" : "Not registered"}</Badge>
                <span className="text-sm">{head?.text}</span>
              </div>
              {status?.host && <p className="text-xs text-muted-foreground">{status.host}:{status.port} ({status.transport}, {status.mode === "ip" ? "IP authentication" : "registration"})</p>}
              {!status?.bridge_connected && <p className="text-xs text-amber-500">The call-center service is not connected to the Asterisk server.</p>}
              <div className="flex gap-2">
                <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void load()}><RefreshCcw className="h-3.5 w-3.5" />Refresh</Button>
                <Button size="sm" disabled={busy !== null || !sipMeta}
                  onClick={() => void run("test", async () => {
                    const r = await testTrunkRegistration()
                    setStatusL({ state: "ready", data: r })
                    return trunkHeadline(r).text
                  })}>
                  {busy === "test" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}Test registration
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">SIP trunk credentials</CardTitle>
          <CardDescription>
            From your SIP provider. The password is encrypted at rest and never shown again; re-enter it whenever you save.
            {sipMeta && <> Saved fields: {sipMeta.fields.join(", ")}.</>}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-2"><Label htmlFor="sip-host">Host</Label><Input id="sip-host" value={trunk.host} onChange={(e) => setTrunk({ ...trunk, host: e.target.value })} placeholder="sip.provider.example" /></div>
            <div><Label htmlFor="sip-port">Port</Label><Input id="sip-port" value={trunk.port} onChange={(e) => setTrunk({ ...trunk, port: e.target.value })} placeholder="5060" /></div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label htmlFor="sip-auth">Authentication</Label>
              <select id="sip-auth" className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm" value={trunk.auth_mode}
                onChange={(e) => setTrunk({ ...trunk, auth_mode: e.target.value as SipTrunkForm["auth_mode"] })}>
                <option value="registration">Username + password (registration)</option>
                <option value="ip">IP authentication</option>
              </select>
            </div>
            <div>
              <Label htmlFor="sip-transport">Transport</Label>
              <select id="sip-transport" className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm" value={trunk.transport}
                onChange={(e) => setTrunk({ ...trunk, transport: e.target.value as SipTrunkForm["transport"] })}>
                <option value="udp">UDP</option><option value="tcp">TCP</option><option value="tls">TLS</option>
              </select>
            </div>
          </div>
          {trunk.auth_mode === "registration" && (
            <div className="grid grid-cols-2 gap-2">
              <div><Label htmlFor="sip-user">Username</Label><Input id="sip-user" autoComplete="off" value={trunk.username} onChange={(e) => setTrunk({ ...trunk, username: e.target.value })} /></div>
              <div><Label htmlFor="sip-pass">Password</Label><Input id="sip-pass" type="password" autoComplete="new-password" value={trunk.password} onChange={(e) => setTrunk({ ...trunk, password: e.target.value })} /></div>
            </div>
          )}
          <div><Label htmlFor="sip-cid">Outbound caller ID (your DID)</Label><Input id="sip-cid" value={trunk.caller_id} onChange={(e) => setTrunk({ ...trunk, caller_id: e.target.value })} placeholder="+27211234567" /></div>
          <div className="flex gap-2">
            <Button size="sm" disabled={busy !== null || !trunk.host.trim() || (trunk.auth_mode === "registration" && (!trunk.username?.trim() || !trunk.password))}
              onClick={() => void run("sip", async () => { await saveSipTrunk(trunk); setTrunk({ ...trunk, password: "" }); await load(); return "Trunk saved. Use Test registration to check it." })}>
              {busy === "sip" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Save trunk
            </Button>
            {sipMeta && (
              <Button size="sm" variant="outline" disabled={busy !== null}
                onClick={() => void run("rm", async () => { await removeSipTrunk(); await load(); return "Trunk removed." })}>Remove</Button>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base"><ShieldAlert className="h-4 w-4" />Dialling policy and limits</CardTitle>
          <CardDescription>Toll-fraud controls. Only South Africa (+27) is enabled by default; premium-rate ranges are always blocked.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between rounded-md border border-border p-2">
            <Label htmlFor="tel-enabled">Telephony enabled for this account</Label>
            <Switch id="tel-enabled" checked={draft.enabled} onCheckedChange={(v) => setDraft({ ...draft, enabled: v })} />
          </div>
          <div><Label htmlFor="tel-dids">Inbound numbers (DIDs, E.164)</Label><Input id="tel-dids" value={dids} onChange={(e) => setDids(e.target.value)} placeholder="+27211234567, +27217654321" /></div>
          <div><Label htmlFor="tel-allowed">Allowed destination prefixes</Label><Input id="tel-allowed" value={prefixes} onChange={(e) => setPrefixes(e.target.value)} placeholder="+27, +263" />
            <p className="mt-1 text-[11px] text-muted-foreground">Add a country code (e.g. +263) to enable international calls to it. Leave only +27 to keep calls national.</p></div>
          <div><Label htmlFor="tel-blocked">Extra blocked prefixes</Label><Input id="tel-blocked" value={blocked} onChange={(e) => setBlocked(e.target.value)} placeholder="+2782" /></div>
          <div className="grid grid-cols-3 gap-2">
            <div><Label>Max concurrent calls</Label>{num("max_concurrent_calls")}</div>
            <div><Label>Max call seconds</Label>{num("max_call_seconds")}</div>
            <div><Label>Calls / agent / hour</Label>{num("max_calls_per_agent_hour")}</div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Call recording (POPIA)</CardTitle>
          <CardDescription>Calls are recorded only when both switches are on, and only after the recording announcement has actually played.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between rounded-md border border-border p-2">
            <Label htmlFor="rec-enabled">Record calls</Label>
            <Switch id="rec-enabled" checked={draft.recording_enabled} onCheckedChange={(v) => setDraft({ ...draft, recording_enabled: v })} />
          </div>
          <div className="flex items-center justify-between rounded-md border border-border p-2">
            <Label htmlFor="rec-ack" className="pr-3">I confirm callers hear a &ldquo;this call may be recorded&rdquo; announcement and I have a lawful basis to record</Label>
            <Switch id="rec-ack" checked={draft.recording_announcement_confirmed} onCheckedChange={(v) => setDraft({ ...draft, recording_announcement_confirmed: v })} />
          </div>
          <p className="text-xs text-muted-foreground">
            Recording is currently <strong>{draft.recording_effective ? "active" : "off"}</strong>. Only metadata is stored in the database; audio files are fetchable by admins only.
          </p>
        </CardContent>
      </Card>

      <div className="lg:col-span-2">
        <Button disabled={busy !== null} onClick={() => void saveSettings()}>
          {busy === "settings" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Save dialling policy, limits and recording settings
        </Button>
      </div>
    </div>
  )
}
