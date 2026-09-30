"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { supabase, getSessionSafe } from "@/lib/supabase/client"
import { sanitizeNextUrl } from "@/lib/supabase/redirect"
import { Button } from "@/components/ui/button"

export default function AuthCallbackPage() {
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const finalize = async () => {
      // 1. Check for URL error parameters from OAuth provider
      const searchParams = new URLSearchParams(window.location.search)
      const errorParam = searchParams.get("error_description") || searchParams.get("error")
      if (errorParam) {
        if (!cancelled) setError(decodeURIComponent(errorParam))
        return
      }

      // 2. Exchange code for session if PKCE code parameter is present
      const code = searchParams.get("code")
      if (code) {
        const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code)
        if (cancelled) return
        if (exchangeError) {
          setError(exchangeError.message)
          return
        }
      }

      // 3. Check session
      const { data, error: sessionError } = await getSessionSafe()
      if (cancelled) return

      if (sessionError) {
        setError(sessionError.message)
        return
      }

      if (data.session) {
        const nextUrl = sanitizeNextUrl(searchParams.get("next"))
        router.replace(nextUrl)
        return
      }

      try {
        Object.keys(window.localStorage)
          .filter((k) => k.startsWith("sb-") && k.endsWith("-auth-token"))
          .forEach((k) => window.localStorage.removeItem(k))
      } catch {}
      setError("We couldn't complete the sign-in. Any stale saved session was cleared. Please try again.")
    }

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        const searchParams = new URLSearchParams(window.location.search)
        const nextUrl = sanitizeNextUrl(searchParams.get("next"))
        router.replace(nextUrl)
      }
    })

    finalize()

    return () => {
      cancelled = true
      subscription.unsubscribe()
    }
  }, [router])

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4 px-6 text-center">
      <div className="text-2xl font-semibold">Finalizing your sign-in</div>
      <p className="text-sm text-muted-foreground max-w-sm">
        Hang tight while we connect your account.
      </p>
      {error && (
        <div className="space-y-4">
          <p className="text-sm text-destructive">{error}</p>
          <Button asChild variant="outline">
            <Link href="/auth">Return to sign in</Link>
          </Button>
        </div>
      )}
    </div>
  )
}
