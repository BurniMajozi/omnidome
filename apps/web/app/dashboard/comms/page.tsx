"use client"

/**
 * Communication Hub — /dashboard/comms
 *
 * Standalone full-page route for the team communication hub.
 *
 * Replaces hub_ux.py (Python-served vanilla HTML SPA) with the existing
 * React CommunicationModule, properly integrated into the web admin app.
 *
 * Accessible from the sidebar "Communication" nav item.
 * Also exposes a direct URL that agents and Hermes can deep-link into.
 */

import { CommunicationModule } from "@/components/modules/communication-module"

export default function CommsPage() {
  return (
    // Full-bleed layout — CommunicationModule manages its own internal layout
    <div className="h-screen w-full overflow-hidden">
      <CommunicationModule />
    </div>
  )
}
