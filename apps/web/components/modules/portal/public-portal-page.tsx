import type { PublicPortalPage } from "@/lib/portal-public"
import { PortalBlocksPreview, blocksOf, plainText } from "./portal-blocks"
import { PublicPortalForm } from "./public-portal-form"

export function PublicPortalPageView({ page }: { page: PublicPortalPage }) {
  return <main className="mx-auto min-h-screen w-full max-w-4xl space-y-8 px-4 py-10 sm:px-8">
    {page.custom_css && <style>{page.custom_css}</style>}
    {page.preview && <aside role="status" className="rounded-md border border-border bg-muted p-4 text-sm">Shared preview. This page may contain unpublished changes. Enquiries are available on the published page.</aside>}
    <header className="space-y-3"><h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{plainText(page.title)}</h1>{page.description && <p className="text-muted-foreground">{plainText(page.description)}</p>}</header>
    <PortalBlocksPreview blocks={blocksOf(page.content)} />
    {!page.preview && <PublicPortalForm slug={page.slug} />}
  </main>
}
