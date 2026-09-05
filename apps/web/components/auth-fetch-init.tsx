"use client"

/**
 * AuthFetchInit — attaches the Supabase access token as a Bearer header to all
 * same-origin /api/* requests, once, on the client.
 *
 * Many modules call `fetch("/api/...")` directly without auth, so the server
 * proxy routes can't resolve identity and 401. Rather than edit every call site,
 * this wraps window.fetch to inject the token for /api/ requests that don't
 * already carry an Authorization header. Server routes resolve identity from
 * that verified token (see lib/api-auth.ts).
 */
import { useEffect } from "react"
import { supabase } from "@/lib/supabase/client"

export function AuthFetchInit() {
  useEffect(() => {
    const w = window as unknown as { __omnidomeAuthFetch?: boolean }
    if (w.__omnidomeAuthFetch) return
    w.__omnidomeAuthFetch = true

    const orig = window.fetch.bind(window)
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      try {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.toString()
              : input instanceof Request
                ? input.url
                : ""
        const origin = window.location.origin
        const isApi = url.startsWith("/api/") || url.startsWith(`${origin}/api/`)
        // Only string/URL inputs (the common case); leave Request objects alone.
        if (isApi && !(input instanceof Request)) {
          const existing = new Headers(init?.headers)
          if (!existing.has("authorization")) {
            const { data } = await supabase.auth.getSession()
            const token = data.session?.access_token
            if (token) {
              existing.set("Authorization", `Bearer ${token}`)
              init = { ...init, headers: existing }
            }
          }
        }
      } catch {
        /* fall through to the original fetch */
      }
      return orig(input, init)
    }

    return () => {
      window.fetch = orig
      w.__omnidomeAuthFetch = false
    }
  }, [])

  return null
}
