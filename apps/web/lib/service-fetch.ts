"use client"

import { useCallback, useEffect, useState } from "react"
import { loadableFromStatus, type Loadable } from "@/lib/service-state"

/**
 * Status-aware GET against /svc/<service>/... Unlike the older per-module
 * clients (which collapse every failure to null) this preserves the HTTP
 * status so the UI can tell "service not running" from "empty" from "error".
 * The Bearer token is attached by AuthFetchInit for /svc/* requests.
 */
export async function fetchLoadable<T>(url: string, timeoutMs = 10_000): Promise<Loadable<T>> {
  let res: Response
  try {
    res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(timeoutMs) })
  } catch {
    return loadableFromStatus<T>(null, undefined)
  }
  if (!res.ok) {
    let message: string | undefined
    try {
      const body = await res.json()
      if (typeof body?.detail === "string") message = body.detail
    } catch {
      /* ignore */
    }
    return loadableFromStatus<T>(res.status, undefined, message)
  }
  try {
    return loadableFromStatus<T>(res.status, (res.status === 204 ? null : await res.json()) as T)
  } catch {
    return { state: "error", status: res.status, message: "Invalid response" }
  }
}

/**
 * Hook wrapper: always runs the same hooks in the same order (no conditional
 * hooks). `reload` re-runs the fetch and shows the loading state again.
 */
export function useLoadable<T>(url: string): { value: Loadable<T>; reload: () => void } {
  const [value, setValue] = useState<Loadable<T>>({ state: "loading" })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    fetchLoadable<T>(url).then((v) => {
      if (!cancelled) setValue(v)
    })
    return () => {
      cancelled = true
    }
  }, [url, tick])

  const reload = useCallback(() => {
    setValue({ state: "loading" })
    setTick((t) => t + 1)
  }, [])

  return { value, reload }
}
