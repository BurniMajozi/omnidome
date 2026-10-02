"use client"

import { useEffect, useState } from "react"
import { createTtlCache } from "@/lib/request-cache"

/**
 * Roles the edge gate resolved for this session (/api/whoami). null = could not be
 * read: admin-only controls stay hidden and the server still enforces everything.
 * One shared request per minute however many components ask.
 */
const cache = createTtlCache(60_000)

export function fetchRoles(): Promise<string[] | null> {
  return cache.get<string[] | null>(
    "whoami-roles",
    async () => {
      try {
        const res = await fetch("/api/whoami", { cache: "no-store", signal: AbortSignal.timeout(10_000) })
        if (!res.ok) return null
        const j = (await res.json()) as { roles?: unknown }
        return Array.isArray(j.roles) ? j.roles.filter((r): r is string => typeof r === "string") : null
      } catch {
        return null
      }
    },
    (r) => r !== null,
  )
}

/** `roles` is undefined while loading, null when unreadable, else the role list. */
export function useRoles(): { roles: string[] | null | undefined } {
  const [roles, setRoles] = useState<string[] | null | undefined>(undefined)
  useEffect(() => {
    let cancelled = false
    fetchRoles().then((r) => {
      if (!cancelled) setRoles(r)
    })
    return () => {
      cancelled = true
    }
  }, [])
  return { roles }
}
