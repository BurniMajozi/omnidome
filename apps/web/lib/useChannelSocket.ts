"use client"

/**
 * useChannelSocket — real-time WebSocket hook for a communication channel.
 *
 * Connects to: ws://<COMM_SERVICE>/api/v1/ws?channel_id=<id>&token=<jwt>
 *
 * Features:
 *   - Auto-connect when channelId + token are provided
 *   - Auto-reconnect with exponential back-off (max 30 s)
 *   - Ping/pong keepalive (server pings every 25 s)
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

const COMM_WS_BASE =
  process.env.NEXT_PUBLIC_COMM_WS_URL ||
  "ws://localhost:8020"

const MAX_BACKOFF_MS = 30_000
const BASE_BACKOFF_MS = 1_000

// ── Event shapes (mirror realtime.py) ────────────────────────────────────

export interface WsMessageEvent {
  type: "message"
  data: {
    id: string
    channel_id: string
    user_id: string
    content: string
    thread_parent_id?: string
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
  const mountedRef = useRef(true)
  const callbacksRef = useRef(callbacks)

  const [connected, setConnected] = useState(false)

  // Keep callbacks ref current without triggering reconnects
  useEffect(() => {
    callbacksRef.current = callbacks
  })

  const connect = useCallback(() => {
    if (!channelId || !token || !mountedRef.current) return

    const url = `${COMM_WS_BASE}/api/v1/ws?channel_id=${encodeURIComponent(channelId)}&token=${encodeURIComponent(token)}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      attemptRef.current = 0
      if (mountedRef.current) setConnected(true)
    }

    ws.onmessage = (evt) => {
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

    ws.onclose = () => {
      if (mountedRef.current) setConnected(false)
      if (!mountedRef.current) return

      // Exponential back-off reconnect
      const delay = Math.min(BASE_BACKOFF_MS * 2 ** attemptRef.current, MAX_BACKOFF_MS)
      attemptRef.current += 1
      reconnectTimer.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      ws.close() // triggers onclose → reconnect
    }
  }, [channelId, token])

  // Connect / reconnect when channelId or token changes
  useEffect(() => {
    mountedRef.current = true
    attemptRef.current = 0

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
