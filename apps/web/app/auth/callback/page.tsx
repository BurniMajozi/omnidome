"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { supabase } from "@/lib/supabase/client"
import { Button } from "@/components/ui/button"

export default function AuthCallbackPage() {
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const finalize = async () => {
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (cancelled) return

      if (sessionError) {
        setError(sessionError.message)
        return
      }

      if (data.session) {
        router.replace("/dashboard")
        return
      }

      setError("We couldn't complete the sign-in. Please try again.")
    }

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        router.replace("/dashboard")
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
