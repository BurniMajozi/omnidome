import type { Metadata } from "next"
import type { ReactNode } from "react"

// Share links carry a secret token: never index, never leak it through the Referer header.
export const metadata: Metadata = {
  title: "Your invoice",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
}

export default function PublicInvoiceLayout({ children }: { children: ReactNode }) {
  return <>{children}</>
}
