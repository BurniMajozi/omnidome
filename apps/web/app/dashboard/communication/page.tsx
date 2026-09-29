"use client"

/**
 * /dashboard/communication → redirect to /dashboard/comms
 *
 * Several sidebar links and agent routes pointed to /dashboard/communication
 * which returned 404. This page redirects cleanly to the canonical route.
 */

import { useEffect } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense } from "react"

function CommunicationRedirect() {
  const router = useRouter()
  const searchParams = useSearchParams()

  useEffect(() => {
    const params = searchParams.toString()
    router.replace(`/dashboard/comms${params ? `?${params}` : ""}`)
  }, [router, searchParams])

  return (
    <div className="h-screen w-full flex items-center justify-center bg-background text-sm text-muted-foreground">
      Redirecting to Communication Hub...
    </div>
  )
}

export default function CommunicationPage() {
  return (
    <Suspense
      fallback={
        <div className="h-screen w-full flex items-center justify-center bg-background text-sm text-muted-foreground">
          Loading...
        </div>
      }
    >
      <CommunicationRedirect />
    </Suspense>
  )
}
