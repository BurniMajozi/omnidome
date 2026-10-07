import type { Metadata } from "next"
import { loadPublicPortalPage } from "@/lib/portal-public"
import { PublicPortalPageView } from "@/components/modules/portal/public-portal-page"
export const dynamic = "force-dynamic"
export const metadata: Metadata = { title: "Shared portal preview", robots: { index: false, follow: false }, referrer: "no-referrer" }
export default async function SharedPortalPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params
  return <PublicPortalPageView page={await loadPublicPortalPage("shared", token)} />
}
