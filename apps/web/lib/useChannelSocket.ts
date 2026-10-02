"use client"

/**
 * useChannelSocket — real-time WebSocket hook for a communication channel.
 *
 * Connects to: ws://<COMM_SERVICE>/api/v1/ws?channel_id=<id>&token=<jwt>
 *
 * Features:
 *   - Auto-connect when channelId + token are provided
 *   - Auto-reconnect with exponential back-off + jitter (1 s -> 30 s cap); close-code policy lives in
 *     comm-helpers.wsClosePolicy: stop on 1008/1009/4001/4003/4401/4403, >= 30 s back-off on 4429,
 *     one immediate reconnect on 4408 (idle), give up after more than 5 consecutive failed attempts
 *   - Ping/pong keepalive: the server pings every 25 s and closes with 4408 after 75 s without ANY inbound
 *     frame, so we answer each ping and also send an unsolicited pong every 30 s
 *   - Emits strongly typed events: message, typing, presence, ping
 *   - sendTyping() helper for typing indicators
 *   - Clean disconnect on unmount or channelId change
 *
 * Usage:
 *   const { connected, sendTyping } = useChannelSocket(channelId, token, {
 *     onMessage: (msg) => setMessages(prev => [...prev, msg]),
 *     onTyping:  ({ user_id }) => showTypingIndicator(user_id),
 *     onPresence: ({ user_id, online }) => updatePresence(user_id, online),
 *   })
 */

import { useEffect, useRef, useCallback, useState } from "react"
import { wsClosePolicy } from "@/lib/comm-helpers"

// Same-origin only: /svc/communication is rewritten to the communication service
// and gated by proxy.ts (which accepts the token query param for the WS upgrade).
// Never point this at a backend port directly.
function commWsBase(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${proto}//${window.location.host}/svc/communication`
}


// ── Event shapes (mirror realtime.py) ────────────────────────────────────

export interface WsMessageEvent {
  type: "message"
  data: {
    id: string
    channel_id: string
    user_id: string
    content: string
    thread_parent_id?: string
    client_msg_id?: string | null
    author_name?: string | null
    created_at: string
    updated_at: string
  }
}

export interface WsTypingEvent {
  type: "typing"
  data: { user_id: string }
}

export interface WsPresenceEvent {
  type: "presence"
  data: { user_id: string; online: boolean }
}

export interface WsPingEvent {
  type: "ping"
  data: Record<string, never>
}

export type WsEvent = WsMessageEvent | WsTypingEvent | WsPresenceEvent | WsPingEvent

// ── Hook ─────────────────────────────────────────────────────────────────

interface ChannelSocketCallbacks {
  onMessage?: (data: WsMessageEvent["data"]) => void
  onTyping?: (data: WsTypingEvent["data"]) => void
  onPresence?: (data: WsPresenceEvent["data"]) => void
}

interface ChannelSocketReturn {
  connected: boolean
  sendTyping: () => void
}

export function useChannelSocket(
  channelId: string | null | undefined,
  token: string | null | undefined,
  callbacks: ChannelSocketCallbacks,
): ChannelSocketReturn {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptRef = useRef(0)
  const openedRef = useRef(false)
  const immediateUsedRef = useRef(false)
  const keepAliveRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const mountedRef = useRef(true)
  const callbacksRef = useRef(callbacks)

  const [connected, setConnected] = useState(false)

  // Keep callbacks ref current without triggering reconnects
  useEffect(() => {
    callbacksRef.current = callbacks
  })

  const connect = useCallback(function openSocket() {
    if (!channelId || !token || !mountedRef.current) return

    const url = `${commWsBase()}/api/v1/ws?channel_id=${encodeURIComponent(channelId)}&token=${encodeURIComponent(token)}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current || wsRef.current !== ws) return
      attemptRef.current = 0
      openedRef.current = true
      immediateUsedRef.current = false
      if (mountedRef.current) setConnected(true)
      if (keepAliveRef.current) clearInterval(keepAliveRef.current)
      keepAliveRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "pong" }))
      }, 30_000)
    }

    ws.onmessage = (evt) => {
      if (!mountedRef.current || wsRef.current !== ws) return
      let event: WsEvent
      try {
        event = JSON.parse(evt.data)
      } catch {
        return
      }

      switch (event.type) {
        case "message":
          callbacksRef.current.onMessage?.(event.data)
          break
        case "typing":
          callbacksRef.current.onTyping?.(event.data)
          break
        case "presence":
          callbacksRef.current.onPresence?.(event.data)
          break
        case "ping":
          // Reply immediately so the server knows we're alive
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "pong" }))
          }
          break
      }
    }

    ws.onclose = (evt) => {
      if (!mountedRef.current || wsRef.current !== ws) return
      if (keepAliveRef.current) {
        clearInterval(keepAliveRef.current)
        keepAliveRef.current = null
      }
      if (mountedRef.current) setConnected(false)
      if (!mountedRef.current) return

      // A socket that never opened is a failed attempt (e.g. 403 on the upgrade).
      const wasOpen = openedRef.current
      openedRef.current = false
      if (wasOpen) attemptRef.current = 0
      const decision = wsClosePolicy(evt.code, {
        attempt: attemptRef.current,
        wasOpen,
        immediateUsed: immediateUsedRef.current,
      })
      if (decision.action === "stop") return // denied / frame too large / too many failures

      if (decision.immediate) immediateUsedRef.current = true
      attemptRef.current += 1
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      reconnectTimer.current = setTimeout(openSocket, decision.delayMs)
    }

    ws.onerror = () => {
      ws.close() // triggers onclose → reconnect
    }
  }, [channelId, token])

  // Connect / reconnect when channelId or token changes
  useEffect(() => {
    mountedRef.current = true
    attemptRef.current = 0
    openedRef.current = false
    immediateUsedRef.current = false

    // Close any existing connection before opening a new one
    if (wsRef.current) {
      wsRef.current.onclose = null // prevent reconnect loop
      wsRef.current.close()
      wsRef.current = null
      setConnected(false)
    }

    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
    }

    connect()

    return () => {
      mountedRef.current = false
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (keepAliveRef.current) {
        clearInterval(keepAliveRef.current)
        keepAliveRef.current = null
      }
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  const sendTyping = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN && channelId) {
      wsRef.current.send(JSON.stringify({ type: "typing", channel_id: channelId }))
    }
  }, [channelId])

  return { connected, sendTyping }
}
