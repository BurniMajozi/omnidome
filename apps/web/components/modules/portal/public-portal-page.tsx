import type { PublicPortalPage } from "@/lib/portal-public"
import { PortalBlocksPreview, blocksOf, plainText, pageThemeClass } from "./portal-blocks"
import { PublicPortalForm } from "./public-portal-form"

export function PublicPortalPageView({ page }: { page: PublicPortalPage }) {
  return <main className={`mx-auto min-h-screen w-full max-w-5xl space-y-6 px-4 py-6 sm:px-8 ${pageThemeClass(page.theme)}`}>
    {page.custom_css && <style>{page.custom_css}</style>}
    {page.preview && <aside role="status" className="rounded-md border border-border bg-muted p-4 text-sm">Shared preview. This page may contain unpublished changes. Enquiries are available on the published page.</aside>}
    <header className="sr-only"><h1>{plainText(page.title)}</h1></header>
    <PortalBlocksPreview blocks={blocksOf(page.content)} theme={page.theme} />
    {!page.preview && <PublicPortalForm slug={page.slug} theme={page.theme} />}
  </main>
}
