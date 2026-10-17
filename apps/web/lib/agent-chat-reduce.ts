// Pure chat-message logic shared by every agent chat UI (no React, no DOM, no aliased imports) so it runs under
// `node --test lib/agent-chat-reduce.test.mjs`.
import type { AGUIEvent, ToolCallEvent, ConversationRead } from "./orchestrator-api"
// .ts extension lets node --test load these; the bundler resolves them as normal.
// @ts-ignore TS5097: extension imports are not enabled in tsconfig (noEmit, bundler resolution)
import { reduceActivity, emptyActivity, finishActivity, type Activity } from "./agent-activity.ts"

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  isStreaming?: boolean
  activity?: Activity
  toolCalls?: ToolCallEvent[]
  memoryWrites?: { correlationId?: string; status?: string }[]
  routedAgent?: string
  routedAgentName?: string
}

// ── Event → message reducer (shared by every chat UI) ───────────────────────

export function reduceAgentEvent(m: ChatMessage, ev: AGUIEvent, agentNames: (type: string) => string | undefined): ChatMessage {
  const d = (ev.data ?? {}) as Record<string, unknown>
  switch (ev.type) {
    case "CUSTOM":
      return { ...m, activity: reduceActivity(m.activity || emptyActivity(), String(d.name), (d.value as Record<string, unknown>) || {}) }
    case "RUN_STARTED": {
      const routed = d.agent_type as string | undefined
      if (routed && (d.auto_routed || routed === "auto")) {
        return { ...m, routedAgent: routed, routedAgentName: agentNames(routed) ?? routed }
      }
      return m
    }
    case "TEXT_MESSAGE_CONTENT":
      return { ...m, content: m.content + String(d.delta ?? "") }
    case "TOOL_CALL_START": {
      const name = (d.tool_name ?? d.name) as string | undefined
      const id = (d.tool_call_id as string | undefined) ?? `tc-${(m.toolCalls?.length ?? 0)}`
      return { ...m, toolCalls: [...(m.toolCalls ?? []), { runId: ev.run_id, toolCallId: id, toolName: name, arguments: d.arguments as Record<string, unknown>, status: "start" }] }
    }
    case "TOOL_CALL_RESULT": {
      const id = d.tool_call_id as string | undefined
      const name = (d.tool_name ?? d.name) as string | undefined
      const calls = m.toolCalls ?? []
      const hit = calls.some((tc) => tc.toolCallId === id)
      return { ...m, toolCalls: hit
        ? calls.map((tc) => (tc.toolCallId === id ? { ...tc, result: d.result, status: "result" as const } : tc))
        : [...calls, { runId: ev.run_id, toolCallId: id, toolName: name, result: d.result, status: "result" as const }] }
    }
    case "TOOL_CALL_END":
      return { ...m, toolCalls: (m.toolCalls ?? []).map((tc) => (tc.toolCallId === d.tool_call_id ? { ...tc, status: "end" as const } : tc)) }
    case "MEMORY_WRITE":
      return { ...m, memoryWrites: [...(m.memoryWrites ?? []), { correlationId: d.correlation_id as string, status: d.status as string }] }
    case "RUN_FINISHED":
      return { ...m, isStreaming: false, activity: m.activity ? finishActivity(m.activity) : undefined }
    case "RUN_ERROR":
      return { ...m, content: `⚠️ Error: ${d.error}`, isStreaming: false, activity: m.activity ? finishActivity(m.activity) : undefined }
    default:
      return m
  }
}

/** Persisted conversation → chat messages. Tool rows are folded into the assistant reply they belong to, so
 *  tool-derived UI (artifact link cards) survives reopening a conversation. */
export function conversationToMessages(data: ConversationRead, id: string): ChatMessage[] {
  const out: ChatMessage[] = []
  let pending: ToolCallEvent[] = []
  for (const m of data.messages || []) {
    if (m.role === "user") {
      out.push({ id: m.id || `${id}-${out.length}`, role: "user", content: m.content || "" })
    } else if (m.role === "tool") {
      const calls = (m.tool_calls as { id?: string; name?: string; arguments?: Record<string, unknown> }[]) || []
      const results = (m.tool_results as unknown[]) || []
      calls.forEach((tc, i) => pending.push({ runId: id, toolCallId: tc.id || `tc-${out.length}-${i}`, toolName: tc.name || "tool", arguments: tc.arguments || {}, result: results[i], status: "result" }))
    } else if (m.role === "assistant") {
      const own = ((m.tool_calls as { id?: string; name?: string; arguments?: Record<string, unknown> }[]) || []).map((tc, i) => ({
        runId: id, toolCallId: tc.id || `tc-${out.length}-${i}`, toolName: tc.name || "tool", arguments: tc.arguments || {},
        result: ((m.tool_results as unknown[]) || [])[i], status: "result" as const }))
      out.push({ id: m.id || `${id}-${out.length}`, role: "assistant", content: m.content || "", toolCalls: [...pending, ...own] })
      pending = []
    }
  }
  return out
}

