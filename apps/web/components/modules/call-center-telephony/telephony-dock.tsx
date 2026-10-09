"use client"

import { useEffect, useMemo, useState } from "react"
import { Delete, Mic, MicOff, Pause, Phone, PhoneForwarded, PhoneIncoming, PhoneOff, Play, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { listAgents } from "@/lib/call-center-api"
import { useSoftphone, type Phase } from "./use-softphone"

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"]

const PHASE_COPY: Record<Phase, { label: string; tone: "ok" | "warn" | "bad" | "idle" }> = {
  loading: { label: "Checking telephony…", tone: "idle" },
  service_down: { label: "Call-center service not reachable", tone: "bad" },
  no_trunk: { label: "No SIP trunk configured", tone: "warn" },
  disabled: { label: "Telephony is switched off", tone: "warn" },
  pbx_down: { label: "Telephony server not connected", tone: "bad" },
  registering: { label: "Softphone connecting…", tone: "idle" },
  ready: { label: "Ready", tone: "ok" },
  error: { label: "Softphone error", tone: "bad" },
}

const TONE: Record<string, string> = {
  ok: "bg-emerald-500", warn: "bg-amber-500", bad: "bg-red-500", idle: "bg-muted-foreground/50",
}

function useTimer(startedAt: number | null) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!startedAt) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [startedAt])
  if (!startedAt) return "00:00"
  const s = Math.max(0, Math.floor((now - startedAt) / 1000))
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`
}

export function TelephonyDock() {
  const sp = useSoftphone(true)
  const [open, setOpen] = useState(false)
  const [number, setNumber] = useState("")
  const [xferOpen, setXferOpen] = useState(false)
  const [xferNumber, setXferNumber] = useState("")
  const [agents, setAgents] = useState<{ id: string; name: string; status: string }[]>([])
  const timer = useTimer(sp.call?.startedAt ?? null)
  const copy = PHASE_COPY[sp.phase]
  const ringing = sp.call?.direction === "inbound" && sp.call.state === "ringing"

  // a ringing call must be seen even when the dock is collapsed
  const shown = open || ringing

  useEffect(() => {
    if (!xferOpen) return
    let alive = true
    listAgents({ status: "IDLE" })
      .then((rows: any) => alive && setAgents(Array.isArray(rows) ? rows : [])) // eslint-disable-line @typescript-eslint/no-explicit-any
      .catch(() => alive && setAgents([]))
    return () => { alive = false }
  }, [xferOpen])

  const headline = useMemo(() => {
    if (sp.phase === "ready" && sp.status && !sp.status.registered) {
      return `Trunk not registered: ${sp.status.last_error || sp.status.state}`
    }
    if (sp.phase === "error" && sp.reason) return sp.reason
    if (sp.phase === "ready") return copy.label
    return sp.reason ?? copy.label
  }, [copy.label, sp.phase, sp.reason, sp.status])

  const canDial = sp.phase === "ready" && !!sp.status?.registered && !sp.call
  const press = (k: string) => (sp.call?.state === "active" ? void sp.dtmf(k) : setNumber((n) => (n + k).slice(0, 24)))

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end gap-2" data-testid="telephony-dock">
      {shown && (
        <div className="w-80 rounded-xl border border-border bg-card p-4 shadow-xl" role="dialog" aria-label="Softphone">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <span className={cn("h-2.5 w-2.5 rounded-full", TONE[copy.tone])} aria-hidden />
              Softphone
            </div>
            <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground" aria-label="Close softphone">
              <X className="h-4 w-4" />
            </button>
          </div>
          <p className="mb-3 text-xs text-muted-foreground" role="status">{headline}</p>

          {sp.call ? (
            <div className="space-y-3">
              <div className="rounded-lg bg-secondary/40 p-3 text-center">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">
                  {sp.call.direction === "inbound" ? "Incoming call" : "Outbound call"}
                  {sp.call.serverCall?.recording && <Badge variant="outline" className="ml-2 text-[10px]">Recording</Badge>}
                </div>
                <div className="mt-1 text-lg font-semibold">{sp.call.serverCall?.number || sp.call.number}</div>
                <div className="text-xs text-muted-foreground">
                  {sp.call.state === "ringing" ? "Ringing…" : sp.call.state === "connecting" ? "Connecting…" : sp.call.held ? `On hold · ${timer}` : timer}
                </div>
              </div>

              {ringing ? (
                <div className="grid grid-cols-2 gap-2">
                  <Button onClick={() => void sp.answer()} className="bg-emerald-600 hover:bg-emerald-700"><PhoneIncoming className="h-4 w-4" />Answer</Button>
                  <Button variant="destructive" onClick={sp.reject}><PhoneOff className="h-4 w-4" />Decline</Button>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-4 gap-2">
                    <Button variant="outline" size="sm" onClick={sp.toggleMute} aria-pressed={sp.call.muted} title="Mute microphone">
                      {sp.call.muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => void sp.toggleHold()} disabled={!sp.call.serverCall || sp.call.state !== "active"} aria-pressed={sp.call.held} title="Hold">
                      {sp.call.held ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => setXferOpen((v) => !v)} disabled={sp.call.state !== "active"} title="Transfer">
                      <PhoneForwarded className="h-4 w-4" />
                    </Button>
                    <Button variant="destructive" size="sm" onClick={() => void sp.hangup()} title="Hang up"><PhoneOff className="h-4 w-4" /></Button>
                  </div>
                  {xferOpen && (
                    <div className="space-y-2 rounded-lg border border-border p-2">
                      <div className="text-xs font-medium">Transfer to an agent</div>
                      {agents.length === 0 ? <div className="text-xs text-muted-foreground">No other idle agents.</div> : (
                        <div className="flex flex-wrap gap-1">
                          {agents.map((a) => (
                            <Button key={a.id} size="sm" variant="outline" className="h-7 text-xs"
                              onClick={() => { void sp.transfer({ to_agent_id: a.id }); setXferOpen(false) }}>{a.name}</Button>
                          ))}
                        </div>
                      )}
                      <div className="text-xs font-medium">…or to a number</div>
                      <div className="flex gap-2">
                        <Input value={xferNumber} onChange={(e) => setXferNumber(e.target.value)} placeholder="082 123 4567" className="h-8 text-sm" />
                        <Button size="sm" disabled={!xferNumber.trim()} onClick={() => { void sp.transfer({ to_number: xferNumber }); setXferNumber(""); setXferOpen(false) }}>Go</Button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Input
                  value={number}
                  onChange={(e) => setNumber(e.target.value.replace(/[^0-9+()\-\s]/g, "").slice(0, 24))}
                  placeholder="Number to call"
                  inputMode="tel"
                  aria-label="Number to call"
                  onKeyDown={(e) => { if (e.key === "Enter" && canDial && number.trim()) void sp.dial(number) }}
                />
                <Button variant="ghost" size="icon" onClick={() => setNumber((n) => n.slice(0, -1))} aria-label="Delete last digit"><Delete className="h-4 w-4" /></Button>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {KEYS.map((k) => (
                  <Button key={k} variant="outline" className="h-10 text-base" onClick={() => press(k)}>{k}</Button>
                ))}
              </div>
              <Button className="w-full bg-emerald-600 hover:bg-emerald-700" disabled={!canDial || !number.trim()} onClick={() => void sp.dial(number)}>
                <Phone className="h-4 w-4" />Call
              </Button>
              {sp.status && sp.status.allowed_prefixes.length > 0 && (
                <p className="text-[11px] text-muted-foreground">Allowed destinations: {sp.status.allowed_prefixes.join(", ")}</p>
              )}
            </div>
          )}

          {sp.call?.state === "active" && !ringing && (
            <div className="mt-3 grid grid-cols-6 gap-1">
              {KEYS.map((k) => (
                <Button key={k} variant="ghost" size="sm" className="h-7 px-0 text-xs" onClick={() => void sp.dtmf(k)}>{k}</Button>
              ))}
            </div>
          )}
          {sp.actionError && <p className="mt-2 text-xs text-red-500" role="alert">{sp.actionError}</p>}
        </div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "relative flex h-12 w-12 items-center justify-center rounded-full border border-border bg-card shadow-lg hover:bg-secondary",
          ringing && "animate-pulse ring-2 ring-emerald-500",
        )}
        aria-label={`Softphone: ${headline}`}
        title={headline}
      >
        <Phone className="h-5 w-5" />
        <span className={cn("absolute right-0.5 top-0.5 h-3 w-3 rounded-full border-2 border-card", TONE[copy.tone])} />
      </button>
    </div>
  )
}
