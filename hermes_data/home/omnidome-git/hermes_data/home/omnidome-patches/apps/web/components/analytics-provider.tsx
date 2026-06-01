"use client"

import { useEffect } from "react"
import { usePathname, useSearchParams } from "next/navigation"
import { getAnalytics } from "@/lib/analytics/tracker"

/**
 * AnalyticsProvider — wraps the app and auto-tracks page views on navigation.
 * Place inside the ThemeProvider in layout.tsx.
 */
export function AnalyticsProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const searchParams = useSearchParams()

  useEffect(() => {
    const tracker = getAnalytics()
    if (tracker) {
      const path = pathname + (searchParams?.toString() ? `?${searchParams.toString()}` : "")
      tracker.trackPageView(path)
    }
  }, [pathname, searchParams])

  return <>{children}</>
}
