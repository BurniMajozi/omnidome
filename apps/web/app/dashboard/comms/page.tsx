"use client"

/**
 * Communication Hub — /dashboard/comms
 *
 * Standalone full-page route for the team communication hub.
 * Accessible from the sidebar "Communication" and "AgentMail" nav items.
 * Supports ?tab=mail, ?tab=chat, ?tab=tasks, etc.
 */

import { Suspense } from "react"
import { useSearchParams } from "next/navigation"
import { CommunicationModule } from "@/components/modules/communication-module"

function CommsContent() {
  const searchParams = useSearchParams()
  const tab = searchParams.get("tab") || undefined

  return (
    <div className="h-screen w-full flex flex-col min-h-0 overflow-hidden bg-background">
      <CommunicationModule initialTab={tab} />
    </div>
  )
}

export default function CommsPage() {
  return (
    <Suspense
      fallback={
        <div className="h-screen w-full flex items-center justify-center bg-background text-sm text-muted-foreground">
          Loading Communication Hub...
        </div>
      }
    >
      <CommsContent />
    </Suspense>
  )
}
