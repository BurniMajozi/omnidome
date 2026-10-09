"use client"

import { useCallback, useEffect, useState } from "react"
import { DeckHome } from "./home"
import { DeckEditor } from "./editor"
import { BrandKitManager } from "./brand-kits"
import { StudioProvider, useStudio } from "./ui"

type Route = { name: "home" } | { name: "brands" } | { name: "deck"; id: string }

const PARAM = "deck"

function readRoute(): Route {
  if (typeof window === "undefined") return { name: "home" }
  const id = new URLSearchParams(window.location.search).get(PARAM)
  return id && /^[0-9a-fA-F-]{8,64}$/.test(id) ? { name: "deck", id } : { name: "home" }
}

function Inner() {
  const [route, setRoute] = useState<Route>({ name: "home" })
  const studio = useStudio()

  useEffect(() => {
    setRoute(readRoute())
    const onPop = () => setRoute(readRoute())
    window.addEventListener("popstate", onPop)
    return () => window.removeEventListener("popstate", onPop)
  }, [])

  const go = useCallback((r: Route) => {
    setRoute(r)
    try {
      const u = new URL(window.location.href)
      if (r.name === "deck") u.searchParams.set(PARAM, r.id)
      else u.searchParams.delete(PARAM)
      window.history.pushState({}, "", u)
    } catch {
      /* URL state is a convenience only */
    }
  }, [])

  return (
    <div>
      {studio.catalogError && route.name !== "brands" && (
        <p className="mb-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">Datasets could not be loaded ({studio.catalogError}). Charts and AI generation need them.</p>
      )}
      {route.name === "home" && <DeckHome onOpen={(id) => go({ name: "deck", id })} onBrandKits={() => go({ name: "brands" })} />}
      {route.name === "brands" && <BrandKitManager onBack={() => go({ name: "home" })} />}
      {route.name === "deck" && <DeckEditor key={route.id} deckId={route.id} onBack={() => go({ name: "home" })} />}
    </div>
  )
}

/** Deck Studio: deck home, brand kits, and the deck editor. */
export function DeckStudio() {
  return (
    <StudioProvider>
      <Inner />
    </StudioProvider>
  )
}
