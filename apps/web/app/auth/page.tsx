"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { supabase } from "@/lib/supabase/client"
import { getAuthRedirectUrl, sanitizeNextUrl } from "@/lib/supabase/redirect"
import type { Provider } from "@supabase/supabase-js"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Loader2 } from "lucide-react"

function GoogleIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" {...props}>
      <path
        fill="#4285F4"
        d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.8-2.4 3.65v3.03h3.88c2.27-2.09 3.665-5.17 3.665-9.12z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.03c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.13C3.27 21.36 7.33 24 12 24z"
      />
      <path
        fill="#FBBC05"
        d="M5.28 14.29c-.25-.72-.38-1.49-.38-2.29s.13-1.57.38-2.29V6.57H1.25C.45 8.16 0 9.98 0 12c0 2.02.45 3.84 1.25 5.43l4.03-3.14z"
      />
      <path
        fill="#EA4335"
        d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.27 2.64 1.25 6.57l4.03 3.14c.95-2.83 3.6-4.96 6.72-4.96z"
      />
    </svg>
  )
}

function GitHubIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" {...props}>
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
      />
    </svg>
  )
}

const allProviders: { id: Provider; label: string; icon: (props: React.SVGProps<SVGSVGElement>) => React.JSX.Element }[] = [
  { id: "google", label: "Continue with Google", icon: GoogleIcon },
]

const enabledProviders = (process.env.NEXT_PUBLIC_SUPABASE_OAUTH_PROVIDERS ?? "google")
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
  const [loadingProvider, setLoadingProvider] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const getNextDestination = () => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      return sanitizeNextUrl(params.get("next"))
    }
    return "/dashboard"
  }

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      const errorParam = params.get("error_description") || params.get("error")
      if (errorParam) {
        setError(decodeURIComponent(errorParam))
      }
    }

    supabase.auth.getSession().then(({ data }) => {
      if (data.session) router.replace(getNextDestination())
    })
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

    try {
      const nextTarget = getNextDestination()
      const { error: signInError } = await supabase.auth.signInWithOtp({
        email,
        options: {
          emailRedirectTo: getAuthRedirectUrl(`/auth/callback?next=${encodeURIComponent(nextTarget)}`),
        },
      })

      if (signInError) {
        setError(signInError.message)
        return
      }

      setNotice("Check your inbox for a sign-in link.")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.")
    } finally {
      setIsLoading(false)
    }
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

    try {
      const nextTarget = getNextDestination()
      if (isSignUp) {
        const { error: signUpError } = await supabase.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: getAuthRedirectUrl(`/auth/callback?next=${encodeURIComponent(nextTarget)}`),
          },
        })

        if (signUpError) {
          setError(signUpError.message)
          return
        }

        setNotice("Account created. Check your email to confirm and sign in.")
        return
      }

      const { error: signInError } = await supabase.auth.signInWithPassword({
        email,
        password,
      })

      if (signInError) {
        setError(signInError.message)
        return
      }

      router.replace(nextTarget)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.")
    } finally {
      setIsLoading(false)
    }
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
    setLoadingProvider(provider)
    setError(null)
    setNotice(null)

    try {
      const nextTarget = getNextDestination()
      const { error: signInError } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: getAuthRedirectUrl(`/auth/callback?next=${encodeURIComponent(nextTarget)}`),
          queryParams: {
            access_type: "offline",
            prompt: "consent",
          },
        },
      })

      if (signInError) {
        setError(signInError.message)
        setIsLoading(false)
        setLoadingProvider(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong initiating Google sign-in.")
      setIsLoading(false)
      setLoadingProvider(null)
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
              Sign in with your Google account or work email to access your dashboard.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-3">
              {oauthProviders.map((provider) => {
                const IconComponent = provider.icon
                const isThisLoading = loadingProvider === provider.id
                return (
                  <Button
                    key={provider.id}
                    type="button"
                    variant="outline"
                    className="w-full flex items-center justify-center gap-3 h-11 text-sm font-medium hover:bg-muted/60 transition-colors shadow-sm"
                    onClick={() => handleOAuthSignIn(provider.id)}
                    disabled={isLoading}
                  >
                    {isThisLoading ? (
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    ) : (
                      <IconComponent className="h-4 w-4 shrink-0" />
                    )}
                    <span>{provider.label}</span>
                  </Button>
                )
              })}
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
