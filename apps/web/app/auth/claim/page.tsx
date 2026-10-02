"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { supabase, getSessionSafe } from "@/lib/supabase/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function ClaimInvitePage() {
  const router = useRouter()
  const [inviteId, setInviteId] = useState("")
  const [email, setEmail] = useState("")
  const [code, setCode] = useState("")
  const [password, setPassword] = useState("")
  const [sessionEmail, setSessionEmail] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setInviteId(new URLSearchParams(window.location.search).get("invite") || "")
    void getSessionSafe().then(({ data }) => {
      if (data.session?.user?.email) {
        setSessionEmail(data.session.user.email)
        setEmail(data.session.user.email)
      }
    })
  }, [])

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { data } = await getSessionSafe()
      const token = data.session?.access_token
      const res = await fetch("/svc/admin/invites/claim", {
        method: "POST",
        cache: "no-store",
        signal: AbortSignal.timeout(25_000),
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ invite_id: inviteId, email: email.trim(), code: code.trim(), ...(!token ? { password } : {}) }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        const detail = body?.detail
        setError(typeof detail === "string" && res.status < 500 ? detail : `Could not accept the invitation (HTTP ${res.status}).`)
        return
      }
      if (!token) {
        const { error: signInError } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
        if (signInError) {
          setError("Invitation accepted. Sign in with the password you just set.")
          return
        }
      } else {
        await supabase.auth.refreshSession()
      }
      router.replace("/dashboard")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the invitation service. Try again.")
    } finally {
      setBusy(false)
    }
  }

  const signInPath = `/auth?next=${encodeURIComponent(`/auth/claim?invite=${inviteId}`)}`
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Accept your OmniDome invitation</CardTitle>
          <CardDescription>Enter the code sent to your invited email address. The link alone cannot activate an account.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!inviteId ? (
            <p role="alert" className="text-sm text-destructive">This invitation link is incomplete. Open the link from your email.</p>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              {sessionEmail && (
                <p className="text-sm text-muted-foreground">
                  Signed in as {sessionEmail}. Use the code sent to this address.{" "}
                  <button type="button" className="text-primary hover:underline" onClick={() => void supabase.auth.signOut().then(() => { setSessionEmail(null); setEmail("") })}>Sign out</button>
                </p>
              )}
              <div className="space-y-2">
                <Label htmlFor="invite-email">Invited email</Label>
                <Input id="invite-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" readOnly={!!sessionEmail} required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="invite-code">Eight-digit invitation code</Label>
                <Input id="invite-code" inputMode="numeric" pattern="[0-9]{8}" maxLength={8} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))} autoComplete="one-time-code" required />
              </div>
              {!sessionEmail && (
                <div className="space-y-2">
                  <Label htmlFor="invite-password">Set a password</Label>
                  <Input id="invite-password" type="password" minLength={12} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required />
                  <p className="text-xs text-muted-foreground">At least 12 characters. If you already have an OmniDome account, sign in first.</p>
                </div>
              )}
              {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
              <Button type="submit" className="w-full" disabled={busy}>{busy ? "Accepting…" : "Accept invitation"}</Button>
            </form>
          )}
          {!sessionEmail && inviteId && <Link href={signInPath} className="block text-sm text-primary hover:underline">Already have an account? Sign in</Link>}
        </CardContent>
      </Card>
    </main>
  )
}
