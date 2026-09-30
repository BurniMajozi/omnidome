/**
 * Tiny in-memory request cache: in-flight dedupe + short TTL. Pure (no React,
 * no browser imports) so it can be unit-tested with node.
 *
 * - Concurrent callers with the same key share ONE promise (one network call).
 * - A settled result is reused for `ttlMs` only when `shouldCache(result)` is
 *   true (failures are never cached, so Retry really retries).
 */

export interface TtlCache {
  get<T>(key: string, loader: () => Promise<T>, shouldCache?: (r: T) => boolean): Promise<T>
  invalidate(key?: string): void
  size(): number
}

interface Entry {
  promise: Promise<unknown>
  /** ms timestamp the promise settled with a cacheable value; null while in flight. */
  settledAt: number | null
}

export function createTtlCache(ttlMs = 30_000, now: () => number = Date.now): TtlCache {
  const entries = new Map<string, Entry>()
  return {
    get<T>(key: string, loader: () => Promise<T>, shouldCache: (r: T) => boolean = () => true): Promise<T> {
      const hit = entries.get(key)
      if (hit && (hit.settledAt === null || now() - hit.settledAt < ttlMs)) return hit.promise as Promise<T>
      const entry: Entry = { promise: undefined as unknown as Promise<unknown>, settledAt: null }
      entry.promise = loader().then(
        (r) => {
          if (shouldCache(r)) entry.settledAt = now()
          else if (entries.get(key) === entry) entries.delete(key)
          return r
        },
        (e) => {
          if (entries.get(key) === entry) entries.delete(key)
          throw e
        },
      )
      entries.set(key, entry)
      return entry.promise as Promise<T>
    },
    invalidate(key?: string) {
      if (key === undefined) entries.clear()
      else entries.delete(key)
    },
    size: () => entries.size,
  }
}
