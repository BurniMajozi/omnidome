"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  getTelephonyStatus, hangupCall, holdCall, listActiveCalls, placeCall, requestWebrtcCredentials, sendDtmf,
  transferCall, TelephonyApiError, type ActiveCall, type TelephonyStatus, type WebrtcCredentials,
} from "@/lib/call-center-telephony-api"

/**
 * Browser softphone state machine (JsSIP over WSS to Asterisk).
 *
 * Honest states only: every phase below maps to something the PBX/API actually reported.
 * Outbound calls are click-to-call: the API rings THIS softphone first (auto-answered here because the agent
 * just pressed Call), then dials the customer through the tenant trunk.
 */

export type Phase =
  | "loading"          // asking the API for status
  | "service_down"     // call-center service not reachable / not permitted
  | "no_trunk"         // "No SIP trunk configured"
  | "disabled"         // telephony switched off for the account
  | "pbx_down"         // Asterisk not connected to the call-center service
  | "registering"      // fetching credentials / SIP REGISTER in flight
  | "ready"
  | "error"            // credentials / registration / microphone failure (see `reason`)

export interface LiveCall {
  direction: "inbound" | "outbound"
  number: string
  state: "ringing" | "connecting" | "active"
  startedAt: number | null
  muted: boolean
  held: boolean
  serverCall: ActiveCall | null
}

type JsSipSession = any // eslint-disable-line @typescript-eslint/no-explicit-any
const STATUS_POLL_MS = 20_000
const RENEW_MARGIN_S = 60

export function useSoftphone(enabled = true) {
  const [phase, setPhase] = useState<Phase>("loading")
  const [reason, setReason] = useState<string | null>(null)
  const [status, setStatus] = useState<TelephonyStatus | null>(null)
  const [call, setCall] = useState<LiveCall | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const uaRef = useRef<any>(null) // eslint-disable-line @typescript-eslint/no-explicit-any
  const sessionRef = useRef<JsSipSession | null>(null)
  const credsRef = useRef<WebrtcCredentials | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const expectOutboundUntil = useRef(0)
  const renewTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const callRef = useRef<LiveCall | null>(null)
  callRef.current = call

  const attachAudio = useCallback((s: JsSipSession) => {
    const pc: RTCPeerConnection | undefined = s.connection
    if (!pc) return
    const sink = () => {
      if (!audioRef.current) {
        const el = document.createElement("audio")
        el.autoplay = true
        document.body.appendChild(el)
        audioRef.current = el
      }
      const stream = new MediaStream()
      pc.getReceivers().forEach((r) => r.track && stream.addTrack(r.track))
      audioRef.current.srcObject = stream
      void audioRef.current.play().catch(() => undefined)
    }
    pc.addEventListener("track", sink)
    sink()
  }, [])

  const endLocal = useCallback(() => {
    sessionRef.current = null
    setCall(null)
  }, [])

  const bindSession = useCallback((s: JsSipSession, direction: "inbound" | "outbound") => {
    sessionRef.current = s
    const number = String(s.remote_identity?.display_name || s.remote_identity?.uri?.user || "Unknown")
    setCall({ direction, number, state: direction === "inbound" ? "ringing" : "connecting", startedAt: null, muted: false, held: false, serverCall: null })
    s.on("peerconnection", () => attachAudio(s))
    s.on("accepted", () => setCall((c) => (c ? { ...c, state: "active", startedAt: Date.now() } : c)))
    s.on("confirmed", () => attachAudio(s))
    s.on("ended", endLocal)
    s.on("failed", endLocal)
  }, [attachAudio, endLocal])

  const answerSession = useCallback(async (s: JsSipSession, iceServers: RTCIceServer[]) => {
    try {
      s.answer({ mediaConstraints: { audio: true, video: false }, pcConfig: { iceServers } })
    } catch {
      setActionError("Could not answer: microphone blocked or unavailable.")
      s.terminate()
    }
  }, [])

  // ── registration lifecycle ───────────────────────────────────────────
  const stopUa = useCallback(() => {
    if (renewTimer.current) clearTimeout(renewTimer.current)
    try { uaRef.current?.stop() } catch { /* already stopped */ }
    uaRef.current = null
  }, [])

  const startUa = useCallback(async () => {
    setPhase("registering")
    setReason(null)
    try {
      const creds = await requestWebrtcCredentials()
      credsRef.current = creds
      const mod: any = await import("jssip") // eslint-disable-line @typescript-eslint/no-explicit-any
      const JsSIP = mod.default ?? mod
      stopUa()
      const ua = new JsSIP.UA({
        sockets: [new JsSIP.WebSocketInterface(creds.ws_url)],
        uri: creds.sip_uri,
        authorization_user: creds.username,
        password: creds.password,
        realm: creds.realm,
        display_name: creds.display_name,
        register: true,
        register_expires: 120,
        session_timers: false,
      })
      ua.on("registered", () => { setPhase("ready"); setReason(null) })
      ua.on("unregistered", () => setPhase((p) => (p === "ready" ? "registering" : p)))
      ua.on("registrationFailed", (e: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
        setPhase("error")
        setReason(`Softphone registration failed${e?.cause ? `: ${e.cause}` : ""}`)
      })
      ua.on("disconnected", () => setPhase((p) => (p === "ready" ? "registering" : p)))
      ua.on("newRTCSession", (e: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
        const s = e.session
        if (e.originator !== "remote") return
        if (sessionRef.current) { s.terminate({ status_code: 486, reason_phrase: "Busy Here" }); return }
        // The click-to-call agent leg arrives as an incoming call: auto-answer it (agent just pressed Call).
        const auto = Date.now() < expectOutboundUntil.current
        bindSession(s, auto ? "outbound" : "inbound")
        if (auto) { expectOutboundUntil.current = 0; void answerSession(s, creds.ice_servers) }
      })
      ua.start()
      uaRef.current = ua
      renewTimer.current = setTimeout(() => {
        if (callRef.current) { renewTimer.current = setTimeout(() => void startUa(), 30_000); return }
        void startUa()
      }, Math.max(30, creds.expires_in - RENEW_MARGIN_S) * 1000)
    } catch (err) {
      setPhase("error")
      setReason(err instanceof TelephonyApiError ? err.message : "Could not start the softphone.")
    }
  }, [answerSession, bindSession, stopUa])

  // ── status polling decides whether a softphone can exist ─────────────
  const refreshStatus = useCallback(async () => {
    const l = await getTelephonyStatus()
    if (l.state !== "ready") {
      stopUa()
      setStatus(null)
      setPhase("service_down")
      setReason(l.state === "denied" ? "You do not have access to telephony." : "Call-center service is not reachable.")
      return
    }
    const s = l.data
    setStatus(s)
    if (!s.available || !s.bridge_connected) { stopUa(); setPhase("pbx_down"); setReason("Telephony server (Asterisk) is not connected."); return }
    if (!s.configured) { stopUa(); setPhase("no_trunk"); setReason("No SIP trunk configured"); return }
    if (!s.enabled) { stopUa(); setPhase("disabled"); setReason("Telephony is switched off for this account."); return }
    if (!uaRef.current) await startUa()
  }, [startUa, stopUa])

  useEffect(() => {
    if (!enabled) return
    void refreshStatus()
    const t = setInterval(() => void refreshStatus(), STATUS_POLL_MS)
    return () => { clearInterval(t); stopUa(); audioRef.current?.remove(); audioRef.current = null }
  }, [enabled, refreshStatus, stopUa])

  // while a call exists, keep the server-side call (hold/transfer/DTMF target) in sync
  useEffect(() => {
    if (!call) return
    let alive = true
    const tick = async () => {
      try {
        const calls = await listActiveCalls()
        if (!alive) return
        const sc = calls.find((c) => c.state !== "ended") ?? null
        setCall((c) => (c ? { ...c, serverCall: sc, held: sc?.held ?? c.held } : c))
      } catch { /* transient */ }
    }
    void tick()
    const t = setInterval(tick, 2000)
    return () => { alive = false; clearInterval(t) }
  }, [call?.direction, !!call]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── actions ───────────────────────────────────────────────────────────
  const guard = useCallback(async (fn: () => Promise<unknown>) => {
    setActionError(null)
    try { await fn() } catch (err) {
      setActionError(err instanceof TelephonyApiError ? err.message : "Action failed.")
    }
  }, [])

  const dial = useCallback((to: string) => guard(async () => {
    if (phase !== "ready") throw new TelephonyApiError(409, "not_ready", "Softphone is not ready")
    if (status && !status.registered) throw new TelephonyApiError(409, "trunk_not_registered", `Trunk not registered: ${status.state}`)
    expectOutboundUntil.current = Date.now() + 30_000
    try {
      const sc = await placeCall(to)
      setCall((c) => (c ? { ...c, serverCall: sc } : c))
    } catch (err) {
      expectOutboundUntil.current = 0
      throw err
    }
  }), [guard, phase, status])

  const answer = useCallback(() => guard(async () => {
    if (sessionRef.current && credsRef.current) await answerSession(sessionRef.current, credsRef.current.ice_servers)
  }), [answerSession, guard])

  const hangup = useCallback(() => guard(async () => {
    const sc = callRef.current?.serverCall
    if (sc) { try { await hangupCall(sc.id) } catch { /* fall through to local terminate */ } }
    try { sessionRef.current?.terminate() } catch { /* already ended */ }
  }), [guard])

  const reject = useCallback(() => {
    try { sessionRef.current?.terminate({ status_code: 603, reason_phrase: "Decline" }) } catch { /* ended */ }
  }, [])

  const toggleMute = useCallback(() => {
    const s = sessionRef.current
    if (!s || !callRef.current) return
    if (callRef.current.muted) s.unmute({ audio: true }); else s.mute({ audio: true })
    setCall((c) => (c ? { ...c, muted: !c.muted } : c))
  }, [])

  const toggleHold = useCallback(() => guard(async () => {
    const sc = callRef.current?.serverCall
    if (!sc) throw new TelephonyApiError(409, "no_call", "Call is not connected yet")
    const r = await holdCall(sc.id, !callRef.current!.held)
    setCall((c) => (c ? { ...c, held: r.held, serverCall: r } : c))
  }), [guard])

  const dtmf = useCallback((digits: string) => guard(async () => {
    const sc = callRef.current?.serverCall
    if (!sc) throw new TelephonyApiError(409, "no_call", "Call is not connected yet")
    await sendDtmf(sc.id, digits)
  }), [guard])

  const transfer = useCallback((target: { to_agent_id?: string; to_number?: string }) => guard(async () => {
    const sc = callRef.current?.serverCall
    if (!sc) throw new TelephonyApiError(409, "no_call", "Call is not connected yet")
    await transferCall(sc.id, target)
  }), [guard])

  return { phase, reason, status, call, actionError, dial, answer, reject, hangup, toggleMute, toggleHold, dtmf, transfer, refresh: refreshStatus }
}
