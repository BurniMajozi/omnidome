import type { Metadata } from "next"
import { loadPublicPortalPage, portalTrackingQuery } from "@/lib/portal-public"
import { PublicPortalPageView } from "@/components/modules/portal/public-portal-page"
export const dynamic = "force-dynamic"
type Props = { params: Promise<{ slug: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }
export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const { slug } = await params
  const page = await loadPublicPortalPage("public", slug, portalTrackingQuery(await searchParams))
  return { title: typeof page.seo_meta?.title === "string" ? page.seo_meta.title : page.title,
    description: typeof page.seo_meta?.description === "string" ? page.seo_meta.description : page.description || undefined }
}
export default async function PublishedPortalPage({ params, searchParams }: Props) {
  const { slug } = await params
  return <PublicPortalPageView page={await loadPublicPortalPage("public", slug, portalTrackingQuery(await searchParams))} />
}
