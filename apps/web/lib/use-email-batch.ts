"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { getEmailBatch, sendEmailBatch, type MarketingResult } from "@/lib/marketing-api"
import {
  describeMutationError,
  nextPollDelay,
  parseEmailBatch,
  summarizeEmailBatch,
  type EmailBatchInfo,
} from "@/lib/marketing-state"

type EmailBatchSendInput = Parameters<typeof sendEmailBatch>[0]

export interface EmailBatchView {
  /** idle -> sending (request in flight) -> tracking (202 accepted, polling) -> done | error */
  phase: "idle" | "sending" | "tracking" | "done" | "error"
  batchId: string | null
  info: EmailBatchInfo | null
  /** Real server error or poll failure; never a synthesized success. */
  error: string | null
  /** One-line human status: "Sending…", or the real counts once known. */
  message: string | null
}

const IDLE: EmailBatchView = { phase: "idle", batchId: null, info: null, error: null, message: null }

/**
 * Sends an email batch and follows it to completion. A 202 means "accepted":
 * we show Sending… and poll GET /email/batches/{id} no faster than every 5s
 * (backing off), pausing while the tab is hidden, until a terminal status.
 * Suppressed / sent / failed counts are shown only if the API returns them.
 */
export function useEmailBatch() {
  const [view, setView] = useState<EmailBatchView>(IDLE)
  const alive = useRef(true)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pollRef = useRef<(batchId: string, attempt: number) => void>(() => {})

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      if (timer.current) clearTimeout(timer.current)
    }
  }, [])

  const poll = useCallback((batchId: string, attempt: number) => {
    const again = (id: string, n: number) => pollRef.current(id, n)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      if (!alive.current) return
      if (typeof document !== "undefined" && document.hidden) {
        again(batchId, attempt) // paused while hidden; re-check later at the same pace
        return
      }
      const res = await getEmailBatch(batchId)
      if (!alive.current) return
      if (!res.ok) {
        // Transient poll failure: keep the last known state, surface the reason, try again (bounded).
        if (attempt >= 12) {
          setView((v) => ({ ...v, phase: "error", error: describeMutationError(res.status, res.error), message: null }))
        } else {
          setView((v) => ({ ...v, error: describeMutationError(res.status, res.error) }))
          again(batchId, attempt + 1)
        }
        return
      }
      const info = parseEmailBatch(res.data)
      if (info.done) {
        setView({ phase: "done", batchId, info, error: null, message: `${labelFor(info)}: ${summarizeEmailBatch(info)}` })
      } else {
        setView({ phase: "tracking", batchId, info, error: null, message: "Sending… " + summarizeEmailBatch(info) })
        again(batchId, attempt + 1)
      }
    }, nextPollDelay(attempt))
  }, [])

  useEffect(() => {
    pollRef.current = poll
  }, [poll])

  const send = useCallback(
    async (input: EmailBatchSendInput): Promise<MarketingResult<{ status: string; total_queued: number; batch_id: string }>> => {
      if (timer.current) clearTimeout(timer.current)
      setView({ phase: "sending", batchId: null, info: null, error: null, message: "Sending…" })
      const res = await sendEmailBatch(input)
      if (!alive.current) return res
      if (!res.ok) {
        setView({ phase: "error", batchId: null, info: null, error: describeMutationError(res.status, res.error), message: null })
        return res
      }
      const batchId = res.data?.batch_id ?? null
      const info = parseEmailBatch(res.data)
      if (!batchId) {
        // Accepted but the server gave us nothing to track: say exactly that.
        setView({ phase: "done", batchId: null, info, error: null, message: `Server accepted the request (status: ${info.status}); no batch id was returned to track it.` })
      } else if (info.done) {
        setView({ phase: "done", batchId, info, error: null, message: `${labelFor(info)}: ${summarizeEmailBatch(info)}` })
      } else {
        setView({ phase: "tracking", batchId, info, error: null, message: "Sending… " + summarizeEmailBatch(info) })
        poll(batchId, 1)
      }
      return res
    },
    [poll],
  )

  const reset = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    setView(IDLE)
  }, [])

  return { view, send, reset }
}

function labelFor(info: EmailBatchInfo): string {
  if (info.status === "failed") return "Failed"
  if (info.status === "partial") return "Partly sent"
  if (info.status === "cancelled" || info.status === "canceled") return "Cancelled"
  return "Sent"
}
