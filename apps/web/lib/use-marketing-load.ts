"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { loadMarketing } from "@/lib/marketing-api"
import { clampRefreshMs } from "@/lib/marketing-state"
import type { Loadable } from "@/lib/service-state"

/**
 * One loader per tab: fetches when the tab opens (path != null), shares the
 * result with every other caller of the same path through the marketing read
 * cache, ignores a late response after unmount, and never refreshes more often
 * than every 30s (and not at all while the page is hidden).
 *
 * `reload()` forces a fresh request and shows the loading state again; call it
 * after a successful write. `refresh()` refetches quietly (no skeleton flash).
 * Hooks are unconditional: pass `null` to skip fetching.
 */
export function useMarketingLoad<T>(
  path: string | null,
  opts?: { refreshMs?: number },
): { value: Loadable<T>; reload: () => void; refresh: () => void } {
  const [value, setValue] = useState<Loadable<T>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const forceRef = useRef(false)
  const quietRef = useRef(false)
  const refreshMs = clampRefreshMs(opts?.refreshMs)

  useEffect(() => {
    if (path === null) return
    let alive = true
    const run = (quiet: boolean) => {
      const force = forceRef.current
      forceRef.current = false
      if (!quiet) setValue({ state: "loading" })
      void loadMarketing<T>(path, { force }).then((v) => {
        if (alive) setValue(v)
      })
    }
    run(quietRef.current)
    quietRef.current = false
    let timer: ReturnType<typeof setInterval> | undefined
    if (refreshMs > 0) {
      timer = setInterval(() => {
        if (typeof document !== "undefined" && document.hidden) return
        forceRef.current = true
        run(true)
      }, refreshMs)
    }
    return () => {
      alive = false
      if (timer) clearInterval(timer)
    }
  }, [path, tick, refreshMs])

  const reload = useCallback(() => {
    forceRef.current = true
    quietRef.current = false
    setTick((t) => t + 1)
  }, [])
  const refresh = useCallback(() => {
    forceRef.current = true
    quietRef.current = true
    setTick((t) => t + 1)
  }, [])

  return { value, reload, refresh }
}
