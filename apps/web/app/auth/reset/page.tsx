"use client"

import { useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import Link from "next/link"
import { supabase } from "@/lib/supabase/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function ResetPasswordPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const code = searchParams.get("code")

  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [isReady, setIsReady] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const initialize = async () => {
      try {
        if (code) {
          const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code)
          if (exchangeError) {
            throw new Error(exchangeError.message)
          }
        }

        const { data, error: sessionError } = await supabase.auth.getSession()
        if (cancelled) return

        if (sessionError) {
          setError(sessionError.message)
          return
        }

        if (!data.session) {
          setError("This reset link is invalid or expired. Please request a new one.")
          return
        }

        setIsReady(true)
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : "Unable to start password reset.")
      }
    }

    initialize()

    return () => {
      cancelled = true
    }
  }, [code])

  const handleReset = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (password.length < 8) {
      setError("Use at least 8 characters for your new password.")
      return
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.")
      return
    }

    setIsLoading(true)
    setError(null)
    setNotice(null)

    const { error: updateError } = await supabase.auth.updateUser({ password })
    if (updateError) {
      setError(updateError.message)
      setIsLoading(false)
      return
    }

    setNotice("Password updated. Redirecting to your dashboard...")
    setIsLoading(false)
    router.replace("/dashboard")
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted/40 flex items-center justify-center px-4 py-16">
      <div className="relative z-10 w-full max-w-md">
        <Card className="border-border/60 bg-card/90 shadow-xl backdrop-blur">
          <CardHeader className="space-y-2">
            <CardTitle className="text-2xl font-semibold">Reset your password</CardTitle>
            <CardDescription>
              Choose a new password to regain access to your OmniDome account.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!isReady && !error && (
              <p className="text-sm text-muted-foreground">Preparing your reset link…</p>
            )}

            {error && (
              <div className="space-y-3">
                <p className="text-sm text-destructive">{error}</p>
                <Button asChild variant="outline" className="w-full">
                  <Link href="/auth">Return to sign in</Link>
                </Button>
              </div>
            )}

            {isReady && !error && (
              <form onSubmit={handleReset} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="password">New password</Label>
                  <Input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete="new-password"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm-password">Confirm new password</Label>
                  <Input
                    id="confirm-password"
                    type="password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    autoComplete="new-password"
                    required
                  />
                </div>
                <Button type="submit" className="w-full" disabled={isLoading}>
                  Update password
                </Button>
              </form>
            )}

            {notice && (
              <p className="text-sm text-emerald-600">{notice}</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
