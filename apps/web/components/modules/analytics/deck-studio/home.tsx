"use client"

import { useCallback, useEffect, useState } from "react"
import { Copy, FilePlus2, Loader2, Lock, Palette, Presentation, Search, Sparkles, Trash2, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  BiApiError,
  createDeck,
  deleteDeck,
  duplicateDeck,
  listDecks,
  publishDeck,
  unwrapDecks,
  type Deck,
  type DeckSummary,
} from "@/lib/bi-studio-api"
import { ErrorNote, Pill, errText, fmtDateTime } from "../shared"
import { fieldCls, Field, Modal, useStudio } from "./ui"
import { AiWizard } from "./ai-wizard"

export function DeckHome({ onOpen, onBrandKits }: { onOpen: (id: string) => void; onBrandKits: () => void }) {
  const { kits, markReadOnly } = useStudio()
  const [decks, setDecks] = useState<DeckSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState("")
  const [status, setStatus] = useState("")
  const [wizard, setWizard] = useState(false)
  const [blank, setBlank] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [confirmDel, setConfirmDel] = useState<DeckSummary | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const r = await listDecks({ q: q.trim() || undefined, status: status || undefined, limit: 100 })
      setDecks(unwrapDecks(r))
      setError(null)
    } catch (e) {
      setError(errText(e))
      setDecks((d) => d ?? [])
    }
  }, [q, status])
  useEffect(() => {
    const t = setTimeout(() => void load(), 250)
    return () => clearTimeout(t)
  }, [load])

  async function act(id: string, fn: () => Promise<unknown>, okMsg?: string) {
    setBusy(id)
    setNote(null)
    setError(null)
    try {
      await fn()
      if (okMsg) setNote(okMsg)
      await load()
    } catch (e) {
      if (e instanceof BiApiError && e.forbidden) markReadOnly()
      setError(e instanceof BiApiError && e.forbidden ? "Your role does not allow this action (publishing and deleting need an admin)." : errText(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold text-foreground">
            <Presentation className="h-5 w-5 text-primary" /> Deck Studio
          </h1>
          <p className="text-xs text-muted-foreground">Brand- and data-grounded presentations. Every number is read from your data, never typed in by the AI.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={onBrandKits}>
            <Palette className="h-4 w-4" /> Brand kits {kits.length > 0 && <span className="text-muted-foreground">({kits.length})</span>}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setBlank(true)}>
            <FilePlus2 className="h-4 w-4" /> Blank deck
          </Button>
          <Button size="sm" onClick={() => setWizard(true)}>
            <Sparkles className="h-4 w-4" /> Generate with AI
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2 top-2 h-4 w-4 text-muted-foreground" />
          <input aria-label="Search decks" className={`${fieldCls} pl-8`} placeholder="Search decks" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <select aria-label="Filter by status" className={`${fieldCls} !w-36`} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="published">Published</option>
        </select>
      </div>

      <ErrorNote message={error} />
      {note && <p className="text-xs text-emerald-400">{note}</p>}

      {decks === null && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading decks…
        </p>
      )}
      {decks && decks.length === 0 && !error && (
        <div className="rounded-lg border border-dashed border-border p-10 text-center">
          <Presentation className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">{q || status ? "No decks match" : "No decks yet"}</p>
          <p className="mb-4 text-xs text-muted-foreground">Describe what you need and let the AI draft it from your data, or start blank.</p>
          <div className="flex justify-center gap-2">
            <Button size="sm" onClick={() => setWizard(true)}>
              <Sparkles className="h-4 w-4" /> Generate with AI
            </Button>
            <Button size="sm" variant="outline" onClick={() => setBlank(true)}>
              Blank deck
            </Button>
          </div>
        </div>
      )}

      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {decks?.map((d) => (
          <li key={d.id} className="group flex flex-col rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/50">
            <button type="button" className="mb-3 flex-1 text-left" onClick={() => onOpen(d.id)}>
              <div className="flex items-start justify-between gap-2">
                <span className="line-clamp-2 text-sm font-semibold text-foreground">{d.title || "Untitled"}</span>
                <Pill tone={d.status === "published" ? "good" : "muted"}>
                  {d.status === "published" && <Lock className="mr-1 h-3 w-3" />}
                  {d.status}
                </Pill>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                {d.slide_count} slide{d.slide_count === 1 ? "" : "s"} · v{d.version}
              </p>
              <p className="text-xs text-muted-foreground">Updated {fmtDateTime(d.updated_at)}</p>
            </button>
            <div className="flex items-center gap-1 border-t border-border/60 pt-2">
              <Button size="sm" variant="secondary" className="h-7 text-xs" onClick={() => onOpen(d.id)}>
                Open
              </Button>
              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" disabled={busy === d.id} onClick={() => act(d.id, () => duplicateDeck(d.id), "Deck duplicated.")} aria-label={`Duplicate ${d.title}`}>
                <Copy className="h-3.5 w-3.5" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-xs"
                disabled={busy === d.id}
                onClick={() => act(d.id, () => publishDeck(d.id, d.status !== "published"), d.status === "published" ? "Unpublished." : "Published (read-only for non-admins).")}
                aria-label={d.status === "published" ? `Unpublish ${d.title}` : `Publish ${d.title}`}
              >
                <Upload className="h-3.5 w-3.5" /> {d.status === "published" ? "Unpublish" : "Publish"}
              </Button>
              <Button size="sm" variant="ghost-destructive" className="ml-auto h-7 px-2" disabled={busy === d.id} onClick={() => setConfirmDel(d)} aria-label={`Delete ${d.title}`}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </li>
        ))}
      </ul>

      {wizard && (
        <AiWizard
          onClose={() => setWizard(false)}
          onCreated={(deck: Deck) => {
            setWizard(false)
            onOpen(deck.id)
          }}
        />
      )}
      {blank && (
        <BlankDeck
          onClose={() => setBlank(false)}
          onCreated={(deck) => {
            setBlank(false)
            onOpen(deck.id)
          }}
        />
      )}
      {confirmDel && (
        <Modal
          title="Delete deck?"
          onClose={() => setConfirmDel(null)}
          footer={
            <>
              <Button variant="outline" size="sm" onClick={() => setConfirmDel(null)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => {
                  const d = confirmDel
                  setConfirmDel(null)
                  void act(d.id, () => deleteDeck(d.id), "Deck deleted.")
                }}
              >
                Delete permanently
              </Button>
            </>
          }
        >
          <p className="text-sm text-foreground">
            “{confirmDel.title}” and all {confirmDel.version} saved versions will be removed. This cannot be undone.
          </p>
        </Modal>
      )}
    </div>
  )
}

function BlankDeck({ onClose, onCreated }: { onClose: () => void; onCreated: (d: Deck) => void }) {
  const { kits } = useStudio()
  const [title, setTitle] = useState("")
  const [kit, setKit] = useState("")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  async function go() {
    setBusy(true)
    setErr(null)
    try {
      onCreated(await createDeck({ title: title.trim() || "Untitled deck", brand_kit_id: kit || undefined }))
    } catch (e) {
      setErr(errText(e))
      setBusy(false)
    }
  }
  return (
    <Modal
      title="New blank deck"
      onClose={onClose}
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={go} disabled={busy}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Create
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Title" htmlFor="bd-title">
          <input id="bd-title" autoFocus className={fieldCls} value={title} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void go()} placeholder="Untitled deck" maxLength={200} />
        </Field>
        <Field label="Brand kit" htmlFor="bd-kit" hint="Leave on default to use the tenant default kit.">
          <select id="bd-kit" className={fieldCls} value={kit} onChange={(e) => setKit(e.target.value)}>
            <option value="">Default</option>
            {kits.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name}
              </option>
            ))}
          </select>
        </Field>
        <ErrorNote message={err} />
      </div>
    </Modal>
  )
}
