"use client"

/**
 * AgentChannelChat — compact in-panel agent chat for the Communication module's
 * "Agent Channel" tab. Reuses the authenticated AG-UI invoke path
 * (invokeAgentAGUI) that powers the floating agent chat, passing the currently
 * active channel as context so the agent knows where the conversation is.
 */
import { useState, useRef, useEffect, useCallback } from "react"
import { Bot, Send, Loader2 } from "lucide-react"
import { invokeAgentAGUI, type AGUIEvent } from "@/lib/orchestrator-api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface Msg {
  id: string
  role: "user" | "assistant"
  content: string
  streaming?: boolean
}

export function AgentChannelChat({
  channelId,
  channelName,
}: {
  channelId?: string
  channelName?: string
}) {
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || sending) return
    setError(null)
    setInput("")
    setSending(true)

    const aId = `${Date.now() + 1}`
    setMessages((p) => [
      ...p,
      { id: `${Date.now()}`, role: "user", content: text },
      { id: aId, role: "assistant", content: "", streaming: true },
    ])

    try {
      await invokeAgentAGUI(
        {
          agent_type: "customer_facing",
          message: text,
          context: { channel_id: channelId, channel_name: channelName },
          stream_tokens: true,
        },
        (e: AGUIEvent) => {
          if (e.type === "TEXT_MESSAGE_CONTENT") {
            const delta = (e.data?.delta as string) || ""
            if (delta) setMessages((p) => p.map((m) => (m.id === aId ? { ...m, content: m.content + delta } : m)))
          }
        },
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSending(false)
      setMessages((p) => p.map((m) => (m.id === aId ? { ...m, streaming: false } : m)))
    }
  }, [input, sending, channelId, channelName])

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-muted-foreground">
            <Bot className="h-10 w-10 text-cyan-400" />
            <div className="max-w-md">
              Ask an agent about <strong>{channelName ?? "this channel"}</strong> — it has OmniDome context
              (customers, billing, network, tickets). Start typing below.
            </div>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap",
                m.role === "user" ? "bg-primary text-primary-foreground" : "bg-secondary text-foreground",
              )}
            >
              {m.content || (m.streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : "")}
            </div>
          </div>
        ))}
        {error && <div className="text-xs text-red-400">Error: {error}</div>}
        <div ref={endRef} />
      </div>
      <div className="border-t border-border p-3">
        <div className="flex items-center gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                void send()
              }
            }}
            placeholder="Ask the agent…"
            disabled={sending}
          />
          <Button size="icon" onClick={() => void send()} disabled={sending || !input.trim()}>
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </div>
  )
}
