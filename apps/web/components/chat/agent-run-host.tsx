"use client"

// App-wide listener for agent runs. Mounted once in the dashboard layout so it outlives every page, panel and
// chat component: it re-attaches to runs the orchestrator is still executing after a reload, and when any run
// ends it shows a toast (click: jump back to that chat) plus a browser Notification when the tab is in the background.
import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { Toaster, toast } from "sonner"
import { isChatVisible, onRunFinished, reattachRuns, requestOpenConversation, type RunFinishedInfo } from "@/lib/agent-chat-store"
import { showBrowserNotification } from "@/lib/agent-run-notify"

export function AgentRunHost() {
  const router = useRouter()

  useEffect(() => {
    const open = (info: Pick<RunFinishedInfo, "key" | "conversationId">) => {
      if (info.key !== "floating") { // other chats (e.g. the communication agent) live on their own page
        router.push("/dashboard/comms")
        return
      }
      if (window.location.pathname === "/dashboard") {
        requestOpenConversation(info.conversationId)
      } else {
        router.push(`/dashboard?agentChat=${encodeURIComponent(info.conversationId ?? "")}`)
      }
    }

    const stop = onRunFinished((info) => {
      const watching = isChatVisible(info.key) && document.visibilityState === "visible" && document.hasFocus()
      if (watching) return
      const ok = info.status === "finished"
      const title = ok ? `${info.agentName} finished` : `${info.agentName} stopped`
      const show = ok ? toast.success : toast.error
      show(title, { description: info.summary, duration: 12000, action: { label: "Open chat", onClick: () => open(info) } })
      if (document.visibilityState !== "visible" || !document.hasFocus()) {
        showBrowserNotification(title, info.summary, `agent-run-${info.runId}`, () => open(info))
      }
    })

    void reattachRuns()
    return stop
  }, [router])

  return <Toaster position="bottom-right" richColors closeButton theme="system" />
}
