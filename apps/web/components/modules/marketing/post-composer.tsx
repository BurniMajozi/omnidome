"use client"

import { useRef, useState } from "react"
import { Loader2, Plus, RefreshCw, X, Film } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { ScrollArea } from "@/components/ui/scroll-area"
import { NotConnected } from "@/components/ui/not-connected"
import { useMarketingLoad } from "@/lib/use-marketing-load"
import { invalidateMarketingCache, type MarketingQueue } from "@/lib/marketing-api"
import {
  createPost,
  enqueueNewPost,
  MEDIA_ACCEPT,
  resultMessage,
  uploadMedia,
  type CreatePostBody,
  type PostRow,
  type UploadedMedia,
} from "@/lib/marketing-zernio-api"
import { ConnectAccountsDialog, type ConnectedRow } from "./connect-flow"

const platformColors: Record<string, string> = {
  twitter: "#1DA1F2", instagram: "#E4405F", facebook: "#1877F2", linkedin: "#0A66C2", tiktok: "#111827",
  whatsapp: "#25D366", youtube: "#FF0000", pinterest: "#BD081C", threads: "#111827", bluesky: "#0085FF",
  telegram: "#0088CC", snapchat: "#C9C400", googlebusiness: "#4285F4", reddit: "#FF4500",
}

export const POST_STATUS_STYLE: Record<string, string> = {
  draft: "border-gray-500/40 text-gray-400",
  scheduled: "border-cyan-500/40 text-cyan-400",
  queued: "border-cyan-500/40 text-cyan-400",
  publishing: "border-amber-500/40 text-amber-500",
  published: "border-emerald-500/40 text-emerald-500",
  partial: "border-amber-500/40 text-amber-500",
  failed: "border-red-500/40 text-red-400",
  cancelled: "border-gray-500/40 text-gray-400",
}

type Mode = "now" | "schedule" | "queue" | "draft"

const isAdsPlatform = (p: string) => /ads$/i.test(p)

function defaultScheduleAt() {
  const d = new Date(Date.now() + 60 * 60000 - new Date().getTimezoneOffset() * 60000)
  return d.toISOString().slice(0, 16)
}

interface PlatformResult {
  platform?: string
  status?: string
  error?: string
  message?: string
}

function describePostOutcome(mode: Mode, post: PostRow): { ok: boolean; text: string } {
  const per = ((post.platform_post_ids as { platforms?: PlatformResult[] } | undefined)?.platforms ?? []).filter((p) => p.error || p.message)
  const perText = per.length ? ` ${per.map((p) => `${p.platform ?? "platform"}: ${p.error || p.message}`).join("; ")}` : ""
  if (post.status === "failed") return { ok: false, text: `Not ${mode === "draft" ? "saved" : "published"}: ${post.publish_error || "the provider rejected it."}${perText}` }
  if (post.status === "partial") return { ok: false, text: `Published to some platforms only. ${post.publish_error || ""}${perText}`.trim() }
  if (post.publish_error) return { ok: false, text: `${post.publish_error}${perText}` }
  if (mode === "draft") return { ok: true, text: "Draft saved." }
  if (mode === "now") return { ok: true, text: post.status === "published" ? "Published." : `Sent to the provider (status: ${post.status}).` }
  if (post.scheduled_for) return { ok: true, text: `${mode === "queue" ? "Queued" : "Scheduled"} for ${new Date(post.scheduled_for).toLocaleString()}.` }
  return { ok: true, text: `Saved (status: ${post.status}).` }
}

export function SocialComposer({ onBackToOverview, onPosted }: { onBackToOverview?: () => void; onPosted?: () => void }) {
  const accountsLoad = useMarketingLoad<{ accounts: ConnectedRow[] }>("/social/connected-accounts")
  const recent = useMarketingLoad<PostRow[]>("/social/posts?sort=created_desc&limit=20")
  const queuesLoad = useMarketingLoad<{ queues: MarketingQueue[] }>("/social/queues")
  const accounts = (accountsLoad.value.state === "ready" ? accountsLoad.value.data.accounts ?? [] : []).filter((a) => !isAdsPlatform(a.platform))
  const posts = recent.value.state === "ready" && Array.isArray(recent.value.data) ? recent.value.data : []
  const queues = queuesLoad.value.state === "ready" ? queuesLoad.value.data?.queues ?? [] : []

  const [content, setContent] = useState("")
  const [selected, setSelected] = useState<string[]>([])
  const [media, setMedia] = useState<UploadedMedia[]>([])
  const [uploading, setUploading] = useState(0)
  const [uploadErrors, setUploadErrors] = useState<string[]>([])
  const [scheduleAt, setScheduleAt] = useState(defaultScheduleAt)
  const [mode, setMode] = useState<Mode>("schedule")
  const [queueId, setQueueId] = useState("")
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [showConnect, setShowConnect] = useState(false)
  const [showReuse, setShowReuse] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const tz = (() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone
    } catch {
      return "UTC"
    }
  })()

  const toggle = (id: string) => setSelected((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))

  const scheduleInvalid = mode === "schedule" && (!scheduleAt || new Date(scheduleAt).getTime() < Date.now() + 60_000)
  const queueInvalid = mode === "queue" && !queueId
  const hasBody = content.trim().length > 0 || media.length > 0
  const canSubmit = hasBody && selected.length > 0 && !scheduleInvalid && !queueInvalid && uploading === 0

  const addFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploadErrors([])
    const list = Array.from(files)
    setUploading((n) => n + list.length)
    await Promise.all(
      list.map(async (f) => {
        try {
          const m = await uploadMedia(f)
          setMedia((prev) => [...prev, m])
        } catch (e) {
          setUploadErrors((prev) => [...prev, `${f.name}: ${e instanceof Error ? e.message : "upload failed"}`])
        } finally {
          setUploading((n) => n - 1)
        }
      }),
    )
    if (fileRef.current) fileRef.current.value = ""
  }

  const submit = async () => {
    if (!canSubmit || submitting) return
    setNotice(null)
    setSubmitting(true)
    const body: CreatePostBody = {
      content: content.trim(),
      account_ids: selected,
      media_urls: media.map((m) => m.public_url),
      status: mode === "now" ? "published" : mode === "draft" ? "draft" : "scheduled",
      timezone: tz,
    }
    if (mode === "schedule") body.scheduled_for = new Date(scheduleAt).toISOString()
    const r = mode === "queue" ? await enqueueNewPost(queueId, body) : await createPost(body)
    setSubmitting(false)
    if (!r.ok || !r.data) {
      setNotice({ ok: false, text: resultMessage(r) })
      return
    }
    const outcome = describePostOutcome(mode, r.data)
    setNotice(outcome)
    if (outcome.ok) {
      setContent("")
      setMedia([])
      setSelected([])
    }
    invalidateMarketingCache()
    recent.reload()
    onPosted?.()
  }

  const submitLabel = { now: "Publish now", schedule: "Schedule post", queue: "Add to queue", draft: "Save draft" }[mode]

  return (
    <div className="space-y-6">
      <Card className="overflow-hidden border-border bg-background shadow-lg">
        <div className="flex items-center justify-between border-b border-border bg-card/60 px-6 py-4">
          <div>
            <h2 className="text-base font-bold text-foreground">Create Post</h2>
            <p className="text-xs text-muted-foreground">create and publish content</p>
          </div>
          <div className="flex items-center gap-2">
            {onBackToOverview && (
              <Button size="sm" variant="outline" className="h-8 text-xs" onClick={onBackToOverview}>
                ← Back to Posts
              </Button>
            )}
            <Button size="sm" className="h-8 bg-[#6610f2] text-xs font-medium text-white shadow-sm hover:bg-[#520dc2]" onClick={() => setShowReuse(true)}>
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Reuse
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 divide-y divide-border lg:grid-cols-2 lg:divide-x lg:divide-y-0">
          <div className="space-y-4 p-6">
            <div>
              <label htmlFor="composer-content" className="mb-2 block text-xs font-semibold text-muted-foreground">content</label>
              <Textarea
                id="composer-content"
                placeholder="what's on your mind..."
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={7}
                className="resize-none border-border bg-card text-sm"
              />
              <div className="mt-1.5 text-right">
                <span className="text-xs text-muted-foreground">{content.length} chars</span>
              </div>
            </div>

            <div className="space-y-2">
              <input ref={fileRef} type="file" multiple accept={MEDIA_ACCEPT} className="hidden" onChange={(e) => void addFiles(e.target.files)} />
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  void addFiles(e.dataTransfer.files)
                }}
                className="flex w-full items-center justify-center rounded-xl border-2 border-dashed border-border bg-card/40 p-6 text-center transition-colors hover:border-primary/50"
              >
                <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  {uploading > 0 ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                  {uploading > 0 ? `Uploading ${uploading} file(s)…` : "Add images or video (click or drop files)"}
                </span>
              </button>
              {uploadErrors.map((m, i) => (
                <p key={i} role="alert" className="text-xs text-red-400">{m}</p>
              ))}
              {media.length > 0 && (
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                  {media.map((m) => (
                    <div key={m.public_url} className="group relative aspect-square overflow-hidden rounded-lg border border-border bg-card">
                      {m.type === "image" ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={m.public_url} alt={m.filename} className="h-full w-full object-cover" />
                      ) : m.type === "video" ? (
                        <video src={m.public_url} className="h-full w-full object-cover" muted preload="metadata" />
                      ) : (
                        <div className="flex h-full flex-col items-center justify-center gap-1 p-1 text-center text-[10px] text-muted-foreground">
                          <Film className="h-5 w-5" />
                          {m.filename}
                        </div>
                      )}
                      <button
                        type="button"
                        aria-label={`Remove ${m.filename}`}
                        onClick={() => setMedia((prev) => prev.filter((x) => x.public_url !== m.public_url))}
                        className="absolute right-1 top-1 rounded-full bg-black/70 p-1 text-white"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="space-y-5 p-6">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-xs font-semibold text-muted-foreground">platforms (connected accounts)</label>
                {accounts.length > 0 && (
                  <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => setShowConnect(true)} aria-label="Connect another account">
                    <Plus className="mr-1 h-3 w-3" /> Connect
                  </Button>
                )}
              </div>
              {accountsLoad.value.state !== "ready" && accountsLoad.value.state !== "loading" ? (
                <NotConnected loadable={accountsLoad.value} service="The marketing service" onRetry={accountsLoad.reload} />
              ) : accountsLoad.value.state === "loading" ? (
                <p className="text-xs text-muted-foreground">loading accounts…</p>
              ) : accounts.length === 0 ? (
                <button
                  type="button"
                  onClick={() => setShowConnect(true)}
                  className="flex w-full flex-col items-center justify-center rounded-xl border border-border bg-card/40 p-8 text-center hover:bg-card"
                >
                  <span className="mb-2 flex h-10 w-10 items-center justify-center rounded-full border border-border bg-card text-muted-foreground">
                    <Plus className="h-5 w-5" />
                  </span>
                  <span className="text-xs font-semibold text-foreground">no connected accounts</span>
                  <span className="mt-0.5 text-[11px] text-muted-foreground">click to connect an account inside OmniDome</span>
                </button>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  {accounts.map((a) => {
                    const on = selected.includes(a.account_id)
                    const bad = a.status === "error"
                    return (
                      <button
                        key={a.account_id}
                        type="button"
                        onClick={() => toggle(a.account_id)}
                        aria-pressed={on}
                        title={bad ? "This account needs reconnecting; posting may fail." : undefined}
                        className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${on ? "border-primary bg-primary/10 text-primary" : "border-border bg-card text-muted-foreground hover:text-foreground"}`}
                      >
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: platformColors[a.platform] || "#666" }} />
                        {a.username ? `${a.platform} · ${a.username}` : a.platform}
                        {bad && <span className="text-amber-500">!</span>}
                      </button>
                    )
                  })}
                  <button
                    type="button"
                    onClick={() => setShowConnect(true)}
                    aria-label="Connect an account"
                    className="flex h-8 w-8 items-center justify-center rounded-lg border border-dashed border-border text-muted-foreground hover:text-foreground"
                  >
                    <Plus className="h-4 w-4" />
                  </button>
                </div>
              )}
            </div>

            <div>
              <label className="mb-2 block text-xs font-semibold text-muted-foreground">publishing</label>
              <div className="grid grid-cols-4 rounded-lg border border-border bg-card/60 p-1 text-xs">
                {([
                  { m: "schedule", label: "Schedule" },
                  { m: "now", label: "Now" },
                  { m: "queue", label: "Queue" },
                  { m: "draft", label: "Draft" },
                ] as const).map(({ m, label }) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMode(m)}
                    className={`rounded-md py-1.5 font-medium transition-all ${mode === m ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {mode === "schedule" && (
                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-muted-foreground">date and time</label>
                    <Input type="datetime-local" value={scheduleAt} min={defaultScheduleAt()} onChange={(e) => setScheduleAt(e.target.value)} className="border-border bg-card text-xs" />
                    {scheduleInvalid && <p className="mt-1 text-[11px] text-amber-500">Pick a time at least a minute from now.</p>}
                  </div>
                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-muted-foreground">timezone</label>
                    <p className="rounded-md border border-border bg-card px-2.5 py-2 text-xs text-muted-foreground">{tz} (your browser)</p>
                  </div>
                </div>
              )}

              {mode === "queue" && (
                <div className="mt-3">
                  <label className="mb-1 block text-[11px] font-medium text-muted-foreground">select queue</label>
                  {queuesLoad.value.state !== "ready" ? (
                    <p className="text-xs text-amber-500">{queuesLoad.value.state === "loading" ? "Loading queues…" : "Queues could not be loaded."}</p>
                  ) : queues.length === 0 ? (
                    <p className="text-xs text-amber-500">No queues yet. Create one under Queues first.</p>
                  ) : (
                    <select value={queueId} onChange={(e) => setQueueId(e.target.value)} className="w-full rounded-md border border-border bg-card px-3 py-2 text-xs text-foreground focus:outline-none">
                      <option value="">Select a queue…</option>
                      {queues.map((q) => (
                        <option key={q.id} value={q.id}>{q.name} ({q.slots?.length || 0} recurring slots)</option>
                      ))}
                    </select>
                  )}
                </div>
              )}
              {mode === "now" && <p className="mt-2 text-xs text-muted-foreground">Publishes immediately to every selected account.</p>}
              {mode === "draft" && <p className="mt-2 text-xs text-muted-foreground">Stored in OmniDome as a draft. Nothing is sent to the platforms.</p>}
              {notice && (
                <p role={notice.ok ? "status" : "alert"} className={`mt-2 text-xs ${notice.ok ? "text-emerald-500" : "text-red-400"}`}>
                  {notice.text}
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border bg-card/30 px-6 py-4">
          <Button variant="outline" size="sm" onClick={() => { setContent(""); setSelected([]); setMedia([]); setNotice(null) }}>
            clear
          </Button>
          <Button size="sm" disabled={!canSubmit || submitting} onClick={submit}>
            {submitting && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
            {submitLabel.toLowerCase()}
          </Button>
        </div>
      </Card>

      {showConnect && (
        <ConnectAccountsDialog
          category="social"
          returnTo="/dashboard?section=marketing&marketing_tab=social-composer"
          onClose={() => setShowConnect(false)}
          onConnected={() => {
            setShowConnect(false)
            accountsLoad.reload()
          }}
        />
      )}

      {showReuse && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="relative flex max-h-[80vh] w-full max-w-lg flex-col overflow-hidden rounded-xl border border-border bg-background shadow-2xl">
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <h3 className="text-sm font-bold text-foreground">Reuse Past Post</h3>
              <button aria-label="Close" onClick={() => setShowReuse(false)} className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-2 overflow-y-auto p-4">
              {posts.length === 0 ? (
                <p className="py-8 text-center text-xs text-muted-foreground">No past posts available to reuse.</p>
              ) : (
                posts.slice(0, 10).map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => { setContent(p.content ?? ""); setShowReuse(false) }}
                    className="w-full cursor-pointer rounded-lg border border-border bg-card p-3 text-left transition-colors hover:border-primary/50"
                  >
                    <p className="line-clamp-3 text-xs text-foreground">{p.content}</p>
                    <p className="mt-1.5 text-[10px] text-muted-foreground">{p.created_at ? new Date(p.created_at).toLocaleDateString() : ""} · {p.status}</p>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      <Card className="border-border bg-card">
        <CardHeader><CardTitle className="text-sm">Recent Posts</CardTitle></CardHeader>
        <CardContent>
          <ScrollArea className="h-64">
            {recent.value.state !== "ready" ? (
              <NotConnected loadable={recent.value} service="The marketing service" onRetry={recent.reload} />
            ) : posts.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted-foreground">No posts yet</div>
            ) : (
              <div className="space-y-3">
                {posts.map((post) => (
                  <div key={post.id} className="rounded-lg border border-border bg-background/40 p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {(post.platforms || []).map((p) => (
                          <span key={p} className="rounded-full border px-2 py-0.5 text-[10px]" style={{ borderColor: `${platformColors[p] ?? "#666"}66`, color: platformColors[p] }}>{p}</span>
                        ))}
                      </div>
                      <Badge variant="outline" className={POST_STATUS_STYLE[String(post.status).toLowerCase()] || "border-muted text-muted-foreground"}>{post.status}</Badge>
                    </div>
                    <p className="line-clamp-2 text-xs text-foreground">{post.content}</p>
                    {post.publish_error && <p className="mt-1 text-[11px] text-red-400">{post.publish_error}</p>}
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  )
}
