"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { supabase } from "@/lib/supabase/client"
import { AUTH_DISABLED } from "@/lib/flags"
import { sanitizeNextUrl } from "@/lib/supabase/redirect"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const [authChecked, setAuthChecked] = useState(false)

  useEffect(() => {
    let mounted = true

    // If local auth-disabled mode is explicitly turned on via env, skip gate.
    if (AUTH_DISABLED) {
      setAuthChecked(true)
      return () => {
        mounted = false
      }
    }

    const redirectToAuth = () => {
      const currentPath =
        typeof window !== "undefined"
          ? `${window.location.pathname}${window.location.search}${window.location.hash}`
          : "/dashboard"
      const safeNext = sanitizeNextUrl(currentPath)
      router.replace(`/auth?next=${encodeURIComponent(safeNext)}`)
    }

    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return
      if (!data.session) {
        redirectToAuth()
        return
      }
      setAuthChecked(true)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!session) {
        redirectToAuth()
      }
    })

    return () => {
      mounted = false
      subscription.unsubscribe()
    }
  }, [router])

  if (!authChecked) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Checking authentication…</p>
      </div>
    )
  }

  return <>{children}</>
}
