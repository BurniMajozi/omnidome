"use client"

import { useEffect, useState } from "react"
import { getBrandKit, getDefaultBrandKit, unwrapKit, type BrandKit } from "@/lib/bi-studio-api"

const cache = new Map<string, Promise<BrandKit | null>>()

export function invalidateKit(id?: string) {
  if (id) {
    cache.delete(id)
    cache.delete("__default")
  } else cache.clear()
}

function load(id: string | null | undefined): Promise<BrandKit | null> {
  const key = id ?? "__default"
  let p = cache.get(key)
  if (!p) {
    p = (id ? getBrandKit(id).then(unwrapKit) : getDefaultBrandKit().then((r) => r.kit ?? null)).catch(() => null)
    cache.set(key, p)
  }
  return p
}

/** Full brand kit (with logo) for a deck's brand_kit_id; null id = tenant default; kit may be null (theme defaults then apply). */
export function useBrandKit(id: string | null | undefined, reloadKey = 0): { kit: BrandKit | null; loading: boolean } {
  const [state, setState] = useState<{ kit: BrandKit | null; loading: boolean }>({ kit: null, loading: true })
  useEffect(() => {
    let live = true
    setState((s) => ({ ...s, loading: true }))
    load(id).then((kit) => live && setState({ kit, loading: false }))
    return () => {
      live = false
    }
  }, [id, reloadKey])
  return state
}
