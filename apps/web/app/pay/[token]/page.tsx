"use client"

import { useParams } from "next/navigation"
import { PublicDocument } from "@/components/modules/billing/public-document"

/** Public customer invoice page: the share token in the URL is the credential. No login required. */
export default function PayInvoicePage() {
  const params = useParams<{ token: string }>()
  const token = Array.isArray(params?.token) ? params.token[0] : params?.token
  if (!token) return null
  return (
    <main className="min-h-screen bg-background">
      <PublicDocument kind="invoice" token={token} />
    </main>
  )
}
