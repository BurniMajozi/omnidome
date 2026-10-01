"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { AlertCircle, CheckCircle2, Loader2, MailWarning } from "lucide-react"
import { supabase, getSessionSafe } from "@/lib/supabase/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

/**
 * Public invite-acceptance page (not gated: the invitee has no tenant yet).
 * The invite is redeemed with the invitee's own Supabase access token; the admin
 * service checks that the token's verified email matches the invite.
 */

type Phase = "checking" | "needs_login" | "accepting" | "done" | "error"

interface Failure {
  title: string
  message: string
  wrongAccount?: boolean
}

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T | undefined> {
  return Promise.race([p, new Promise<undefined>((r) => setTimeout(() => r(undefined), ms))])
}

function describeFailure(status: number, detail: unknown, email: string | null): Failure {
  const text =
    typeof detail === "string"
      ? detail
      : detail && typeof detail === "object"
        ? String((detail as Record<string, unknown>).message ?? (detail as Record<string, unknown>).error ?? "")
        : ""
  const seatObj = detail && typeof detail === "object" && (detail as Record<string, unknown>).error === "seat_limit_reached"
  if (seatObj) {
    return {
      title: "This organization has no free seats",
      message: "The organization has reached its seat limit. Ask your administrator to free a seat or raise the limit, then use this link again.",
    }
  }
  if (status === 403 && /different email/i.test(text)) {
    return {
      title: "Wrong account",
      message: `This invitation was sent to a different email address${email ? `, but you are signed in as ${email}` : ""}. Sign out and sign in with the address the invitation was sent to.`,
      wrongAccount: true,
    }
  }
  if (status === 410 && /expired/i.test(text)) {
    return { title: "Invitation expired", message: "Invitations are valid for 7 days. Ask your administrator to resend it." }
  }
  if (status === 410) {
    return { title: "Invitation no longer valid", message: `${text || "This invitation was revoked or already used."} Ask your administrator for a new one.` }
  }
  if (status === 404) {
    return { title: "Invitation not found", message: "This link is not valid. It may have been replaced by a newer invitation; check for the latest email or ask your administrator to resend it." }
  }
  if (status === 409) {
    return { title: "Cannot join", message: text || "This email is already linked to another organization." }
  }
  if (status === 401) {
    return { title: "Please sign in again", message: "Your session could not be verified. Sign in and reopen this link." }
  }
  // Never show raw 5xx bodies; 4xx server text (e.g. the generic conflict message) is shown verbatim.
  return { title: "Something went wrong", message: status < 500 && text ? text : `The server returned an error (${status}). Try again shortly.` }
}

export default function AcceptInvitePage() {
  const router = useRouter()
  const [token, setToken] = useState<string | null>(null)
  const [phase, setPhase] = useState<Phase>("checking")
  const [email, setEmail] = useState<string | null>(null)
  const [failure, setFailure] = useState<Failure | null>(null)
  const started = useRef(false)

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token")?.trim() || "")
  }, [])

  const accept = useCallback(
    async (accessToken: string, inviteToken: string, userEmail: string | null) => {
      if (started.current) return
      started.current = true
      setPhase("accepting")
      try {
        const res = await fetch("/svc/admin/invites/accept", {
          method: "POST",
          cache: "no-store",
          signal: AbortSignal.timeout(20_000),
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
          body: JSON.stringify({ token: inviteToken }),
        })
        if (!res.ok) {
          const raw = await res.text().catch(() => "")
          let detail: unknown = raw
          try {
            const parsed = JSON.parse(raw)
            detail = parsed?.detail ?? parsed?.error ?? parsed
          } catch {
            /* plain text */
          }
          setFailure(describeFailure(res.status, detail, userEmail))
          setPhase("error")
          started.current = false
          return
        }
        // Roles/tenant now live in app_metadata: refresh so the browser token carries them.
        await withTimeout(supabase.auth.refreshSession(), 8000).catch(() => undefined)
        setPhase("done")
        setTimeout(() => router.replace("/dashboard"), 1500)
      } catch (err) {
        const timedOut = err instanceof DOMException && err.name === "TimeoutError"
        setFailure({
          title: timedOut ? "Timed out" : "Could not reach the server",
          message: "The invitation may or may not have been accepted. Reload this page to check.",
        })
        setPhase("error")
        started.current = false
      }
    },
    [router],
  )

  useEffect(() => {
    if (token === null) return
    if (!token) {
      setFailure({ title: "Missing invitation token", message: "Open the full link from your invitation email." })
      setPhase("error")
      return
    }
    let cancelled = false
    const run = async (accessToken: string | undefined, userEmail: string | null | undefined) => {
      if (cancelled) return
      if (!accessToken) {
        setPhase("needs_login")
        return
      }
      setEmail(userEmail ?? null)
      void accept(accessToken, token, userEmail ?? null)
    }
    void getSessionSafe().then(({ data }) => run(data.session?.access_token, data.session?.user?.email))
    const { data: sub } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_IN" && session) void run(session.access_token, session.user?.email)
    })
    return () => {
      cancelled = true
      sub.subscription.unsubscribe()
    }
  }, [token, accept])

  const signOut = async () => {
    await supabase.auth.signOut().catch(() => undefined)
    started.current = false
    setFailure(null)
    setEmail(null)
    setPhase("needs_login")
  }

  const returnPath = `/auth/accept?token=${encodeURIComponent(token || "")}`

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Join your organization</CardTitle>
          <CardDescription>Accept your OmniDome invitation.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4" aria-live="polite">
          {(phase === "checking" || phase === "accepting") && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {phase === "checking" ? "Checking your session..." : `Accepting invitation${email ? ` as ${email}` : ""}...`}
            </p>
          )}

          {phase === "needs_login" && (
            <div className="space-y-3">
              <p className="flex items-start gap-2 text-sm">
                <MailWarning className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                <span>
                  Sign in or create an account using <strong>the email address this invitation was sent to</strong>. You will come back here
                  automatically.
                </span>
              </p>
              <Button asChild className="w-full">
                <Link href={`/auth?next=${encodeURIComponent(returnPath)}`}>Sign in or sign up</Link>
              </Button>
              <p className="text-xs text-muted-foreground">
                If you are returned to the dashboard instead, sign in and then reopen the link from your invitation.
              </p>
            </div>
          )}

          {phase === "done" && (
            <p className="flex items-center gap-2 text-sm text-emerald-400">
              <CheckCircle2 className="h-4 w-4" />
              Invitation accepted. Taking you to the dashboard...
            </p>
          )}

          {phase === "error" && failure && (
            <div role="alert" className="space-y-3 rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm">
              <p className="flex items-center gap-2 font-medium text-red-400">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {failure.title}
              </p>
              <p className="text-muted-foreground">{failure.message}</p>
              {failure.wrongAccount && (
                <Button variant="outline" size="sm" onClick={() => void signOut()}>
                  Sign out
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
