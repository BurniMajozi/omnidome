"use client"

import { useEffect, Suspense } from "react"
import { usePathname, useSearchParams } from "next/navigation"
import { getAnalytics } from "@/lib/analytics/tracker"

/**
 * PageViewTracker performs the actual page view tracking
 * and contains the useSearchParams hook which must be inside a Suspense boundary.
 */
function PageViewTracker() {
  const pathname = usePathname()
  const searchParams = useSearchParams()

  useEffect(() => {
    const tracker = getAnalytics()
    if (tracker) {
      const path = pathname + (searchParams?.toString() ? `?${searchParams.toString()}` : "")
      tracker.trackPageView(path)
    }
  }, [pathname, searchParams])

  return null
}

/**
 * AnalyticsProvider — wraps the app and auto-tracks page views on navigation.
 * Place inside the ThemeProvider in layout.tsx.
 */
export function AnalyticsProvider({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Suspense fallback={null}>
        <PageViewTracker />
      </Suspense>
      {children}
    </>
  )
}
