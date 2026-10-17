// Agent chat sessions that live OUTSIDE React. A run used to be a closure inside the chat component, aborted in
// an unmount effect, so closing the panel or navigating away killed it. Here the run, its AbortController and its
// messages belong to a module-level store keyed by session ("floating", "comms:<channel>"); components only
// subscribe. The orchestrator also owns the run (see services/agent_orchestrator/run_registry.py), so after a
// reload the store re-attaches by run id and replays the events it missed.
import { useSyncExternalStore } from "react"
import {
  invokeAgentAGUI, attachAgentRun, listAgentRuns, cancelAgentRun, getConversation,
  type AGUIEvent, type AGUIRunRequest, type ConversationRead,
} from "@/lib/orchestrator-api"
import { emptyActivity, finishActivity } from "@/components/chat/agent-activity"
import { reduceAgentEvent, conversationToMessages, type ChatMessage } from "@/lib/agent-chat-reduce"

export { reduceAgentEvent, conversationToMessages, type ChatMessage }

export interface ChatSession {
  messages: ChatMessage[]
  conversationId: string | null
  runId: string
  isSending: boolean
  error: string | null
}

export interface RunFinishedInfo {
  key: string
  runId: string
  conversationId: string | null
  agentName: string
  status: "finished" | "error" | "stopped"
  summary: string
}

const EMPTY: ChatSession = { messages: [], conversationId: null, runId: "", isSending: false, error: null }
const sessions = new Map<string, ChatSession>()
const controllers = new Map<string, AbortController>()
const listeners = new Set<() => void>()
const finishListeners = new Set<(info: RunFinishedInfo) => void>()
const RUN_MAP_KEY = "omnidome.agentRuns"

function emit() { listeners.forEach((l) => l()) }

export function getSession(key: string): ChatSession { return sessions.get(key) ?? EMPTY }

function patch(key: string, change: Partial<ChatSession> | ((s: ChatSession) => Partial<ChatSession>)) {
  const cur = getSession(key)
  sessions.set(key, { ...cur, ...(typeof change === "function" ? change(cur) : change) })
  emit()
}

export function setMessages(key: string, update: ChatMessage[] | ((m: ChatMessage[]) => ChatMessage[])) {
  patch(key, (s) => ({ messages: typeof update === "function" ? update(s.messages) : update }))
}
export function setConversationId(key: string, id: string | null) { patch(key, { conversationId: id }) }
export function setSessionError(key: string, error: string | null) { patch(key, { error }) }
export function resetSession(key: string) {
  controllers.get(key)?.abort()
  controllers.delete(key)
  sessions.set(key, { ...EMPTY })
  emit()
}

export function subscribeSessions(cb: () => void) { listeners.add(cb); return () => { listeners.delete(cb) } }
export function onRunFinished(cb: (info: RunFinishedInfo) => void) { finishListeners.add(cb); return () => { finishListeners.delete(cb) } }

/** Subscribe a component to one chat session; the snapshot is referentially stable between changes. */
export function useChatSession(key: string): ChatSession {
  return useSyncExternalStore(subscribeSessions, () => getSession(key), () => EMPTY)
}

// ── Runs ────────────────────────────────────────────────────────────────────

function rememberRun(runId: string, key: string) {
  try {
    const map = JSON.parse(sessionStorage.getItem(RUN_MAP_KEY) || "{}")
    map[runId] = { key, at: Date.now() }
    for (const id of Object.keys(map)) if (Date.now() - map[id].at > 2 * 3600_000) delete map[id]
    sessionStorage.setItem(RUN_MAP_KEY, JSON.stringify(map))
  } catch { /* storage unavailable: reattach just falls back to the floating chat */ }
}
function recallRuns(): Record<string, { key: string; at: number }> {
  try { return JSON.parse(sessionStorage.getItem(RUN_MAP_KEY) || "{}") } catch { return {} }
}
function forgetRun(runId: string) {
  try { const m = recallRuns(); delete m[runId]; sessionStorage.setItem(RUN_MAP_KEY, JSON.stringify(m)) } catch { /* ignore */ }
}

function summarise(content: string): string {
  return content.replace(/```[\s\S]*?```/g, "(document)").replace(/[#*_`>|]/g, "").replace(/\s+/g, " ").trim().slice(0, 160)
}

/** Fold one stream event into the session's current assistant message (and session-level fields). */
function applyEvent(key: string, assistantId: string, ev: AGUIEvent, agentNames: (t: string) => string | undefined) {
  if (ev.run_id) {
    if (getSession(key).runId !== ev.run_id) {
      patch(key, { runId: ev.run_id })
      rememberRun(ev.run_id, key)
    }
  }
  if (ev.conversation_id && getSession(key).conversationId !== ev.conversation_id) setConversationId(key, ev.conversation_id)
  setMessages(key, (ms) => ms.map((m) => (m.id === assistantId ? reduceAgentEvent(m, ev, agentNames) : m)))
}

function finish(key: string, assistantId: string, status: RunFinishedInfo["status"], agentName: string) {
  setMessages(key, (ms) => ms.map((m) => (m.id === assistantId
    ? { ...m, isStreaming: false, activity: m.activity ? finishActivity(m.activity, Date.now(), status === "stopped") : undefined } : m)))
  const s = getSession(key)
  const last = s.messages.find((m) => m.id === assistantId)
  patch(key, { isSending: false })
  if (s.runId) forgetRun(s.runId)
  if (status === "stopped") return
  finishListeners.forEach((l) => l({
    key, runId: s.runId, conversationId: s.conversationId, agentName, status,
    summary: status === "error" ? (last?.content || "The run failed").replace(/^⚠️ Error:\s*/, "").slice(0, 160) : summarise(last?.content || "") || "Done",
  }))
}

export interface StartRunOptions {
  agentType: string
  agentName: string
  message: string
  context?: Record<string, unknown>
  agentNames?: (type: string) => string | undefined
}

/** Start a run in session `key`. Resolves when the stream ends; the run keeps going if no component is mounted. */
export async function startRun(key: string, opts: StartRunOptions): Promise<void> {
  const cur = getSession(key)
  if (cur.isSending) return
  const stamp = Date.now()
  const assistantId = String(stamp + 1)
  const names = opts.agentNames ?? (() => undefined)
  const req: AGUIRunRequest = {
    agent_type: opts.agentType,
    message: opts.message,
    context: { ...(opts.context ?? {}), conversation_id: cur.conversationId },
    conversation_id: cur.conversationId || undefined,
    stream_tokens: true,
  }
  setMessages(key, (ms) => [...ms,
    { id: String(stamp), role: "user", content: opts.message },
    { id: assistantId, role: "assistant", content: "", isStreaming: true, toolCalls: [], memoryWrites: [], activity: emptyActivity() }])
  patch(key, { isSending: true, error: null, runId: "" })
  const controller = new AbortController()
  controllers.set(key, controller)
  let outcome: RunFinishedInfo["status"] = "finished"
  try {
    await invokeAgentAGUI(req, (ev) => {
      if (ev.type === "RUN_ERROR") outcome = "error"
      applyEvent(key, assistantId, ev, names)
    }, controller.signal)
  } catch (err) {
    if (controller.signal.aborted) {
      outcome = "stopped"
      setMessages(key, (ms) => ms.map((m) => (m.id === assistantId ? { ...m, content: m.content || "Stopped." } : m)))
    } else {
      outcome = "error"
      const msg = err instanceof Error ? err.message : "Failed to reach agent"
      setMessages(key, (ms) => ms.map((m) => (m.id === assistantId ? { ...m, content: `⚠️ Error: ${msg}` } : m)))
      patch(key, { error: msg })
    }
  } finally {
    if (controllers.get(key) === controller) controllers.delete(key)
    finish(key, assistantId, outcome, opts.agentName)
  }
}

export function stopRun(key: string) {
  const runId = getSession(key).runId
  controllers.get(key)?.abort()
  if (runId) void cancelAgentRun(runId)
}

// ── Conversations and re-attach ─────────────────────────────────────────────

export async function loadConversationInto(key: string, id: string): Promise<ConversationRead> {
  const data = await getConversation(id)
  patch(key, { messages: conversationToMessages(data, id), conversationId: data.id, error: null })
  return data
}

let reattaching = false
/** After a reload: pick up runs this browser tab started that the orchestrator is still running (or just finished). */
export async function reattachRuns(agentNames: (t: string) => string | undefined = () => undefined): Promise<void> {
  if (reattaching) return
  reattaching = true
  try {
    const mine = recallRuns()
    const runs = (await listAgentRuns()).filter((r) => mine[r.run_id] && !controllers.has(mine[r.run_id].key) && getSession(mine[r.run_id].key).runId !== r.run_id)
    for (const run of runs) {
      const key = mine[run.run_id].key
      if (getSession(key).isSending) continue
      if (run.status !== "running") {
        // Finished while we were away: the turn is persisted, show the conversation and announce it.
        await loadConversationInto(key, run.conversation_id).catch(() => undefined)
        forgetRun(run.run_id)
        finishListeners.forEach((l) => l({ key, runId: run.run_id, conversationId: run.conversation_id, agentName: run.agent_name,
          status: run.status === "finished" ? "finished" : "error", summary: summarise(run.preview) || "Done" }))
        continue
      }
      await loadConversationInto(key, run.conversation_id).catch(() => patch(key, { messages: [] }))
      const assistantId = `re-${run.run_id}`
      setMessages(key, (ms) => [...ms,
        { id: `${assistantId}-u`, role: "user", content: run.message },
        { id: assistantId, role: "assistant", content: "", isStreaming: true, toolCalls: [], memoryWrites: [], activity: emptyActivity() }])
      patch(key, { isSending: true, runId: run.run_id, conversationId: run.conversation_id })
      const controller = new AbortController()
      controllers.set(key, controller)
      let outcome: RunFinishedInfo["status"] = "finished"
      void attachAgentRun(run.run_id, (ev) => {
        if (ev.type === "RUN_ERROR") outcome = "error"
        applyEvent(key, assistantId, ev, agentNames)
      }, controller.signal).catch(() => { if (!controller.signal.aborted) outcome = "error" }).finally(() => {
        if (controllers.get(key) === controller) controllers.delete(key)
        finish(key, assistantId, outcome, run.agent_name)
      })
    }
  } finally {
    reattaching = false
  }
}

// ── "Open this run's chat" requests (toast / bell click) ───────────────────

let pendingOpen: string | null = null
/** Ask the floating chat to show a conversation; works whether or not the chat is mounted yet. */
export function requestOpenConversation(conversationId: string | null) {
  pendingOpen = conversationId
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("open-agent-chat", { detail: { conversationId } }))
}
export function takePendingOpen(): string | null { const id = pendingOpen; pendingOpen = null; return id }

// Which chats are on screen right now (so finishing a run in the chat you are reading doesn't pop a toast).
const visible = new Map<string, number>()
export function setChatVisible(key: string, on: boolean) {
  visible.set(key, Math.max(0, (visible.get(key) ?? 0) + (on ? 1 : -1)))
}
export function isChatVisible(key: string): boolean { return (visible.get(key) ?? 0) > 0 }
