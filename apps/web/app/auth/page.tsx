"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { supabase } from "@/lib/supabase/client"
import { getAuthRedirectUrl } from "@/lib/supabase/redirect"
import type { Provider } from "@supabase/supabase-js"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

const allProviders: { id: Provider; label: string }[] = [
  { id: "google", label: "Continue with Google" },
  { id: "github", label: "Continue with GitHub" },
]

const enabledProviders = (process.env.NEXT_PUBLIC_SUPABASE_OAUTH_PROVIDERS ?? "google,github")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean)

const oauthProviders = allProviders.filter((provider) => enabledProviders.includes(provider.id))

export default function AuthPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [authMethod, setAuthMethod] = useState("magic")
  const [isSignUp, setIsSignUp] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true
    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return
      if (data.session) {
        router.replace("/dashboard")
      }
    })
    return () => {
      mounted = false
    }
  }, [router])

  const handleEmailSignIn = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!email.trim()) {
      setError("Enter your email address to continue.")
      return
    }

    setIsLoading(true)
    setError(null)
    setNotice(null)

    const { error: signInError } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: getAuthRedirectUrl("/auth/callback"),
      },
    })

    if (signInError) {
      setError(signInError.message)
      setIsLoading(false)
      return
    }

    setNotice("Check your inbox for a sign-in link.")
    setIsLoading(false)
  }

  const handlePasswordSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!email.trim()) {
      setError("Enter your email address to continue.")
      return
    }
    if (!password.trim()) {
      setError("Enter your password to continue.")
      return
    }

    setIsLoading(true)
    setError(null)
    setNotice(null)

    if (isSignUp) {
      const { error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: getAuthRedirectUrl("/auth/callback"),
        },
      })

      if (signUpError) {
        setError(signUpError.message)
        setIsLoading(false)
        return
      }

      setNotice("Account created. Check your email to confirm and sign in.")
      setIsLoading(false)
      return
    }

    const { error: signInError } = await supabase.auth.signInWithPassword({
      email,
      password,
    })

    if (signInError) {
      setError(signInError.message)
      setIsLoading(false)
      return
    }

    router.replace("/dashboard")
    setIsLoading(false)
  }

  const handlePasswordReset = async () => {
    if (!email.trim()) {
      setError("Enter your email address to reset your password.")
      return
    }

    setIsLoading(true)
    setError(null)
    setNotice(null)

    const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: getAuthRedirectUrl("/auth/reset"),
    })

    if (resetError) {
      setError(resetError.message)
      setIsLoading(false)
      return
    }

    setNotice("Check your inbox for a password reset link.")
    setIsLoading(false)
  }

  const handleOAuthSignIn = async (provider: Provider) => {
    setIsLoading(true)
    setError(null)
    setNotice(null)

    const { error: signInError } = await supabase.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: getAuthRedirectUrl("/auth/callback"),
      },
    })

    if (signInError) {
      setError(signInError.message)
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted/40 flex items-center justify-center px-4 py-16">
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-24 -right-10 h-72 w-72 rounded-full bg-indigo-500/20 blur-3xl" />
        <div className="absolute bottom-0 left-10 h-72 w-72 rounded-full bg-cyan-500/20 blur-3xl" />
      </div>
      <div className="relative z-10 w-full max-w-md">
        <Card className="border-border/60 bg-card/90 shadow-xl backdrop-blur">
          <CardHeader className="space-y-2">
            <CardTitle className="text-2xl font-semibold">Sign in to OmniDome</CardTitle>
            <CardDescription>
              Use email, password, or a social account to start your demo workspace.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-3">
              {oauthProviders.map((provider) => (
                <Button
                  key={provider.id}
                  type="button"
                  variant="outline"
                  className="w-full"
                  onClick={() => handleOAuthSignIn(provider.id)}
                  disabled={isLoading}
                >
                  {provider.label}
                </Button>
              ))}
            </div>

            <div className="relative flex items-center text-xs uppercase text-muted-foreground">
              <div className="h-px flex-1 bg-border" />
              <span className="px-3">or use email</span>
              <div className="h-px flex-1 bg-border" />
            </div>

            <Tabs value={authMethod} onValueChange={setAuthMethod} className="w-full">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="magic">Magic Link</TabsTrigger>
                <TabsTrigger value="password">Password</TabsTrigger>
              </TabsList>
              <TabsContent value="magic" className="pt-4">
                <form onSubmit={handleEmailSignIn} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="email-magic">Email</Label>
                    <Input
                      id="email-magic"
                      type="email"
                      placeholder="you@company.com"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      autoComplete="email"
                      required
                    />
                  </div>
                  <Button type="submit" className="w-full" disabled={isLoading}>
                    Send magic link
                  </Button>
                </form>
              </TabsContent>
              <TabsContent value="password" className="pt-4">
                <form onSubmit={handlePasswordSubmit} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="email-password">Email</Label>
                    <Input
                      id="email-password"
                      type="email"
                      placeholder="you@company.com"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      autoComplete="email"
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <Input
                      id="password"
                      type="password"
                      placeholder="••••••••"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      autoComplete={isSignUp ? "new-password" : "current-password"}
                      required
                    />
                  </div>
                  <Button type="submit" className="w-full" disabled={isLoading}>
                    {isSignUp ? "Create account" : "Sign in"}
                  </Button>
                </form>
                <div className="mt-3 flex flex-col gap-2 text-sm">
                  {!isSignUp && (
                    <button
                      type="button"
                      className="text-left text-primary hover:underline"
                      onClick={handlePasswordReset}
                      disabled={isLoading}
                    >
                      Forgot password?
                    </button>
                  )}
                  <button
                    type="button"
                    className="text-left text-primary hover:underline"
                    onClick={() => setIsSignUp((prev) => !prev)}
                  >
                    {isSignUp ? "Already have an account? Sign in" : "New here? Create an account"}
                  </button>
                </div>
              </TabsContent>
            </Tabs>

            {notice && (
              <p className="text-sm text-emerald-600">
                {notice}
              </p>
            )}
            {error && (
              <p className="text-sm text-destructive">
                {error}
              </p>
            )}

            <div className="text-xs text-muted-foreground">
              By continuing, you agree to OmniDome&apos;s terms and privacy policy.
            </div>
          </CardContent>
        </Card>

        <div className="mt-6 text-center text-sm text-muted-foreground">
          <Link href="/" className="text-primary hover:underline">
            Back to home
          </Link>
        </div>
      </div>
    </div>
  )
}
