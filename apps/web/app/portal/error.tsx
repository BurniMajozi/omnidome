"use client"
import { Button } from "@/components/ui/button"
export default function PortalError({ reset }: { reset: () => void }) {
  return <main className="mx-auto max-w-lg space-y-4 p-8"><h1 className="text-2xl font-semibold">Page temporarily unavailable</h1><p role="alert">We could not load this page. Please try again shortly.</p><Button onClick={reset}>Try again</Button></main>
}
