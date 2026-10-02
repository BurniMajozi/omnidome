"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { supabase } from "@/lib/supabase/client"
import { getAuthRedirectUrl, sanitizeNextUrl } from "@/lib/supabase/redirect"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function AuthPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const getNextDestination = () => {
    if (typeof window === "undefined") return "/dashboard"
    return sanitizeNextUrl(new URLSearchParams(window.location.search).get("next"))
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const errorParam = params.get("error_description") || params.get("error")
    if (errorParam) setError(errorParam)
    void supabase.auth.getSession().then(({ data }) => {
      if (data.session) router.replace(getNextDestination())
    })
  }, [router])

  const signIn = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setIsLoading(true)
    setError(null)
    setNotice(null)
    try {
      const { error: signInError } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
      if (signInError) {
        setError(signInError.message)
      } else {
        router.replace(getNextDestination())
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  const resetPassword = async () => {
    if (!email.trim()) {
      setError("Enter your invited email address to reset your password.")
      return
    }
    setIsLoading(true)
    setError(null)
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(email.trim(), {
      redirectTo: getAuthRedirectUrl("/auth/reset"),
    })
    setIsLoading(false)
    if (resetError) setError(resetError.message)
    else setNotice("If this email has an account, check its inbox for password reset instructions.")
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted/40 flex items-center justify-center px-4 py-16">
      <div className="relative z-10 w-full max-w-md">
        <Card className="border-border/60 bg-card/90 shadow-xl backdrop-blur">
          <CardHeader className="space-y-2">
            <CardTitle className="text-2xl font-semibold">Sign in to OmniDome</CardTitle>
            <CardDescription>Access is by email invitation. Sign in with the address and password you set when accepting it.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={signIn} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
              </div>
              <Button type="submit" className="w-full" disabled={isLoading}>Sign in</Button>
            </form>
            <button type="button" className="text-sm text-primary hover:underline" onClick={() => void resetPassword()} disabled={isLoading}>
              Forgot password?
            </button>
            {notice && <p className="text-sm text-emerald-600">{notice}</p>}
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <p className="text-xs text-muted-foreground">No invitation? Ask your organization administrator to invite you.</p>
          </CardContent>
        </Card>
        <div className="mt-6 text-center text-sm text-muted-foreground">
          <Link href="/" className="text-primary hover:underline">Back to home</Link>
        </div>
      </div>
    </div>
  )
}
