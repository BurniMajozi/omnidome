"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { runQuery, type DeckDoc, type QueryResult, type QuerySpec } from "@/lib/bi-studio-api"
import { collectQueries } from "./doc-ops"
import type { DataMap } from "./tokens"

export interface QState {
  status: "loading" | "ok" | "error"
  result?: QueryResult
  error?: string
  /** HTTP-ish status for the error (429 etc.) */
  code?: number
}

const STALE_MS = 15 * 60 * 1000

/**
 * Runs every query a deck needs (deduplicated by spec) directly against POST /bi/query, so unsaved drafts show live data.
 * Debounced; failed queries are retryable per alias.
 */
export function useDeckData(doc: DeckDoc | null, enabled = true) {
  const cache = useRef(new Map<string, QState>())
  const inflight = useRef(new Set<string>())
  const [ver, setVer] = useState(0)
  const [tick, setTick] = useState(0)
  const bump = useCallback(() => setVer((v) => v + 1), [])

  const specs = useMemo(() => (doc ? collectQueries(doc) : {}), [doc])
  const keys = useMemo(() => {
    const m: Record<string, string> = {}
    for (const [a, s] of Object.entries(specs)) m[a] = JSON.stringify(s)
    return m
  }, [specs])
  const keysSig = JSON.stringify(keys)

  const fetchKey = useCallback(
    async (key: string, spec: QuerySpec) => {
      if (inflight.current.has(key)) return
      inflight.current.add(key)
      const prev = cache.current.get(key)
      cache.current.set(key, { status: "loading", result: prev?.result })
      bump()
      try {
        const result = await runQuery(spec)
        cache.current.set(key, { status: "ok", result })
      } catch (e) {
        const err = e as { message?: string; status?: number }
        cache.current.set(key, { status: "error", error: err.message ?? "Query failed", code: err.status })
      } finally {
        inflight.current.delete(key)
        bump()
      }
    },
    [bump],
  )

  useEffect(() => {
    if (!enabled) return
    const t = setTimeout(() => {
      const todo: [string, QuerySpec][] = []
      const seen = new Set<string>()
      for (const [alias, key] of Object.entries(keys)) {
        if (seen.has(key)) continue
        seen.add(key)
        if (!cache.current.has(key)) todo.push([key, specs[alias]])
      }
      // 3 workers
      const queue = [...todo]
      const worker = async () => {
        while (queue.length) {
          const next = queue.shift()
          if (next) await fetchKey(next[0], next[1])
        }
      }
      void Promise.all([worker(), worker(), worker()])
    }, 500)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keysSig, enabled])

  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 60000)
    return () => clearInterval(t)
  }, [])

  const states = useMemo(() => {
    const out: Record<string, QState> = {}
    for (const [alias, key] of Object.entries(keys)) out[alias] = cache.current.get(key) ?? { status: "loading" }
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keysSig, ver])

  const data: DataMap = useMemo(() => {
    const out: DataMap = {}
    for (const [a, s] of Object.entries(states)) if (s.status === "ok" || s.result) out[a] = s.result
    return out
  }, [states])

  const refreshAll = useCallback(() => {
    for (const key of new Set(Object.values(keys))) cache.current.delete(key)
    const seen = new Set<string>()
    for (const [alias, key] of Object.entries(keys)) {
      if (seen.has(key)) continue
      seen.add(key)
      void fetchKey(key, specs[alias])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keysSig, fetchKey])

  const retry = useCallback(
    (alias: string) => {
      const key = keys[alias]
      if (!key) return
      cache.current.delete(key)
      void fetchKey(key, specs[alias])
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [keysSig, fetchKey],
  )

  const times = Object.values(states)
    .map((s) => (s.result?.meta.generated_at ? Date.parse(s.result.meta.generated_at) : NaN))
    .filter((n) => !Number.isNaN(n))
  const oldest = times.length ? Math.min(...times) : null
  const asOf = oldest ? new Date(oldest).toISOString() : null
  void tick
  const stale = oldest !== null && Date.now() - oldest > STALE_MS
  const loading = Object.values(states).some((s) => s.status === "loading")
  const errors = Object.values(states).filter((s) => s.status === "error").length
  return { states, data, refreshAll, retry, asOf, stale, loading, errors }
}
