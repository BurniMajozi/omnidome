// Links to platform-made work product (BI decks, research, analyses...) shown in the agent chat.
// Everything here treats model/tool output as untrusted: only same-origin /dashboard paths are ever navigable.

export interface ArtifactLinkItem {
  kind: string
  title: string
  status?: string
  version?: number
  updatedAt?: string
  owner?: string
  summary?: string
  href: string
}

const KIND_LABELS: Record<string, string> = {
  deck: "Deck",
  brand_kit: "Brand kit",
  research: "Research",
  competitor: "Competitor",
  campaign_analysis: "Campaign analysis",
  portal_page: "Portal page",
}

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? (kind ? kind.replace(/[_-]+/g, " ").slice(0, 24) : "Item")
}

/** Same-origin app path (/dashboard...) or null. Rejects schemes, hosts, //, backslashes, control chars. */
export function safeAppPath(raw: unknown): string | null {
  if (typeof raw !== "string") return null
  const s = raw
  if (s.length === 0 || s.length > 400) return null
  // eslint-disable-next-line no-control-regex
  if (/[\u0000- \<>"'`]/.test(s)) return null
  if (!/^\/dashboard(?:[?/#]|$)/.test(s)) return null
  if (s.startsWith("//")) return null
  return s
}

/** http(s) links only, for generic markdown links in chat text. */
export function safeExternalUrl(raw: unknown): string | null {
  if (typeof raw !== "string") return null
  try {
    const u = new URL(raw.trim())
    return u.protocol === "https:" || u.protocol === "http:" ? u.toString() : null
  } catch {
    return null
  }
}

function str(v: unknown, max: number): string | undefined {
  return typeof v === "string" && v.trim() ? v.trim().slice(0, max) : undefined
}

export function sanitizeArtifactItem(raw: unknown): ArtifactLinkItem | null {
  if (!raw || typeof raw !== "object") return null
  const r = raw as Record<string, unknown>
  const href = safeAppPath(r.deep_link)
  const title = str(r.title, 160)
  if (!href || !title) return null
  return {
    kind: str(r.kind, 40) ?? "item",
    title,
    status: str(r.status, 24),
    version: typeof r.version === "number" && Number.isFinite(r.version) ? r.version : undefined,
    updatedAt: str(r.updated_at, 40),
    owner: str(r.owner, 80),
    summary: str(r.summary, 220),
    href,
  }
}

/** Items from finished `artifacts.find` tool calls, de-duplicated by href, capped at `max` (default 3). */
export function artifactItemsFromToolCalls(
  toolCalls: { toolName?: string; result?: unknown }[] | undefined,
  max = 3,
): ArtifactLinkItem[] {
  const out: ArtifactLinkItem[] = []
  const seen = new Set<string>()
  for (const tc of toolCalls ?? []) {
    if (tc.toolName !== "artifacts.find" && tc.toolName !== "artifacts_find") continue
    let res: unknown = tc.result
    if (typeof res === "string") {
      try {
        res = JSON.parse(res)
      } catch {
        continue
      }
    }
    const data = res as { data?: { items?: unknown[]; weak_match?: boolean }; items?: unknown[]; weak_match?: boolean } | undefined
    if (data?.data?.weak_match ?? data?.weak_match) continue // only semantically near, not a title match: no link cards
    const items = data?.data?.items ?? data?.items
    if (!Array.isArray(items)) continue
    for (const raw of items) {
      const it = sanitizeArtifactItem(raw)
      if (it && !seen.has(it.href)) {
        seen.add(it.href)
        out.push(it)
        if (out.length >= max) return out
      }
    }
  }
  return out
}

/** Navigate inside the app (same tab) without a reload when already on the dashboard. */
export function openAppPath(path: string): boolean {
  const safe = safeAppPath(path)
  if (!safe || typeof window === "undefined") return false
  if (window.location.pathname.startsWith("/dashboard")) {
    window.history.pushState({}, "", safe)
    window.dispatchEvent(new PopStateEvent("popstate"))
  } else {
    window.location.assign(safe)
  }
  return true
}
