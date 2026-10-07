"use client"

import { useEffect, useRef, useState } from "react"
import { ArrowUp, Loader2, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { StudioMessage } from "./use-design-studio"

export const starterPrompts = [
  { title: "Home fibre", prompt: "Create a landing page for our home fibre service. Focus on streaming, working from home and a clear enquiry button. Leave out prices and coverage claims until I add them." },
  { title: "Business connectivity", prompt: "Build a professional landing page for business connectivity. Include an introduction, benefits, frequently asked questions and an enquiry button. Do not invent prices or SLA promises." },
  { title: "Launch a campaign", prompt: "Create a simple campaign landing page with a bold introduction, three benefits and a call to action. Ask me to add the actual offer details before publishing." },
]

export function BuilderPrompt({ onSubmit, busy, initial = "", label = "Describe your landing page", placeholder = "Who is this page for, what are you offering, and what should visitors do?", large = false }: {
  onSubmit: (prompt: string) => Promise<boolean>; busy: boolean; initial?: string; label?: string; placeholder?: string; large?: boolean
}) {
  const [prompt, setPrompt] = useState(initial)
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { setPrompt(initial); if (initial) ref.current?.focus() }, [initial])
  async function submit() { if (prompt.trim().length < 3 || busy) return; if (await onSubmit(prompt.trim())) setPrompt("") }
  return <form onSubmit={(e) => { e.preventDefault(); void submit() }} className="space-y-3">
    <label htmlFor={large ? "builder-brief" : "builder-message"} className="sr-only">{label}</label>
    <textarea ref={ref} id={large ? "builder-brief" : "builder-message"} value={prompt} maxLength={4000} disabled={busy} rows={large ? 5 : 3}
      onChange={(e) => setPrompt(e.target.value)} placeholder={placeholder}
      onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); void submit() } }}
      className={`w-full resize-y rounded-lg border border-border bg-background p-4 leading-relaxed outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 ${large ? "text-base" : "text-sm"}`} />
    <div className="flex items-center justify-between gap-3">
      <p className="text-xs text-muted-foreground">{busy ? "Creating your draft…" : "Ctrl / ⌘ + Enter to send"}</p>
      <Button type="submit" disabled={busy || prompt.trim().length < 3} className="bg-cyan-500 text-cyan-950 hover:bg-cyan-400">
        {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : large ? <Sparkles className="mr-2 h-4 w-4" /> : <ArrowUp className="mr-2 h-4 w-4" />}{large ? "Build my page" : "Send"}
      </Button>
    </div>
  </form>
}
export function BuilderChat({ messages, busy, selected, onSubmit }: { messages: StudioMessage[]; busy: boolean; selected: string | null; onSubmit: (prompt: string) => Promise<boolean> }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }) }, [messages, busy])
  return <div className="flex h-full min-h-96 flex-col">
    <div className="flex-1 space-y-4 overflow-y-auto p-4" role="log" aria-label="Design conversation" aria-live="polite">
      {!messages.length && <p className="text-sm leading-relaxed text-muted-foreground">Tell me what to build. You can refine the copy, add sections, change the style, or focus on a selected section.</p>}
      {messages.map((message, i) => <div key={i} className={message.role === "user" ? "ml-6 rounded-lg bg-secondary p-3" : "mr-3 py-2"}><p className="mb-1 text-xs font-medium text-muted-foreground">{message.role === "user" ? "You" : "DomeDesign"}</p><p className="whitespace-pre-wrap text-sm leading-relaxed">{message.text}</p></div>)}
      {busy && <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Updating your design…</p>}<div ref={end} />
    </div>
    <div className="space-y-3 border-t border-border p-4">
      {selected && <p className="rounded-md bg-cyan-500/10 px-3 py-2 text-xs text-cyan-600 dark:text-cyan-300">Editing section: {selected}</p>}
      <BuilderPrompt busy={busy} onSubmit={onSubmit} label="Tell DomeDesign what to change" placeholder={selected ? "What should change in this section?" : "e.g. Shorten the headline and add a benefits section"} />
    </div>
  </div>
}
