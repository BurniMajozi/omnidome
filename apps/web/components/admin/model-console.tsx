"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

type Slot = "basic" | "balanced" | "premium"
type Profile = { model: string; fallbacks: string[]; enabled: boolean }
type Routing = { enabled: boolean; profiles: Record<Slot, Profile>; tiers: Record<string, Slot> }
type Configuration = { config: Routing; keys: { provider: string; configured: boolean; management: string }[] }
async function api<T>(path = "", body?: unknown, method = "POST"): Promise<T> {
  const response = await fetch(`/api/orchestrator/llm-console${path}`, { cache: "no-store", ...(body === undefined ? {} : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }) })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`)
  return data
}
const slots: Slot[] = ["basic", "balanced", "premium"]
export function ModelConsole() {
  const [data, setData] = useState<Configuration | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [slot, setSlot] = useState<Slot>("basic")
  const [prompt, setPrompt] = useState("Explain what you can help an ISP operations team with in two sentences.")
  const [answer, setAnswer] = useState<{ content: string; served_model: string; latency_ms: number; verified: boolean } | null>(null)
  const [analytics, setAnalytics] = useState<{ model: string; calls: number; tokens: number; failures: number; latency_ms: number }[]>([])
  const [notice, setNotice] = useState("")
  useEffect(() => { api<Configuration>().then(setData).catch(e => setError(e.message)); api<{ models: typeof analytics }>("/analytics").then(d => setAnalytics(d.models)).catch(e => setError(e.message)) }, [])
  async function action(fn: () => Promise<void>) { setBusy(true); setError(""); setNotice(""); try { await fn() } catch (e) { setError(e instanceof Error ? e.message : "Request failed") } finally { setBusy(false) } }
  function profile(name: Slot, patch: Partial<Profile>) { if (data) setData({ ...data, config: { ...data.config, profiles: { ...data.config.profiles, [name]: { ...data.config.profiles[name], ...patch } } } }) }
  if (!data) return <p role="status">{error || "Loading platform models…"}</p>
  return <Card><CardHeader><CardTitle>Models & Routing</CardTitle><p className="text-sm text-muted-foreground">Platform Owner controls · All organisations inherit their active plan’s model access. Paid tests can incur provider costs.</p></CardHeader><CardContent className="space-y-4">
    {error && <p role="alert" className="text-destructive">{error}</p>}{notice && <p role="status">{notice}</p>}
    <Tabs defaultValue="models"><TabsList className="flex flex-wrap h-auto">{["models", "routing", "playground", "keys", "analytics"].map(tab => <TabsTrigger value={tab} key={tab} className="capitalize">{tab}</TabsTrigger>)}</TabsList>
      <TabsContent value="models" className="space-y-4"><p className="text-sm text-muted-foreground">Enter model IDs, test each slot in Playground, then save and enable it. Basic accepts local Ollama models or OpenRouter IDs ending in :free.</p>
        <div className="grid gap-4 lg:grid-cols-3">{slots.map(name => <div key={name} className="rounded-xl border p-4 space-y-3"><h3 className="font-semibold capitalize">{name === "basic" ? "Free / Basic" : name}</h3>
          <label className="block text-sm">Model ID<input className="block w-full rounded border bg-background p-2 mt-1" value={data.config.profiles[name].model} onChange={e => profile(name, { model: e.target.value })} placeholder={name === "basic" ? "provider/model:free" : "provider/model"} /></label>
          <label className="block text-sm">Fallback IDs (up to two, comma separated)<input className="block w-full rounded border bg-background p-2 mt-1" value={data.config.profiles[name].fallbacks.join(",")} onChange={e => profile(name, { fallbacks: e.target.value.split(",").map(v => v.trim()).filter(Boolean) })} /></label>
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={data.config.profiles[name].enabled} onChange={e => profile(name, { enabled: e.target.checked })} />Enable tested slot</label></div>)}</div>
      </TabsContent>
      <TabsContent value="routing" className="space-y-4"><label className="flex gap-2"><input type="checkbox" checked={data.config.enabled} onChange={e => setData({ ...data, config: { ...data.config, enabled: e.target.checked } })} />Apply plan routing</label>
        <p className="text-sm text-muted-foreground">Free is always Basic. An unavailable or disabled paid slot uses Basic. Exhausted Basic capacity returns unavailable; it cannot charge a paid fallback.</p>
        {Object.entries(data.config.tiers).map(([tier, choice]) => <label key={tier} className="flex items-center gap-4"><span className="w-36">{tier}</span><select aria-label={`${tier} model slot`} className="rounded border bg-background p-2" disabled={tier === "FREE"} value={choice} onChange={e => setData({ ...data, config: { ...data.config, tiers: { ...data.config.tiers, [tier]: e.target.value as Slot } } })}>{slots.map(s => <option value={s} key={s}>{s}</option>)}</select></label>)}
      </TabsContent>
      <TabsContent value="playground" className="space-y-3"><p className="text-sm text-muted-foreground">Tests the model IDs currently in the form, including every fallback. No tools or company memory are sent. Testing does not change the active route.</p><label className="block">Model slot<select className="block rounded border bg-background p-2" value={slot} onChange={e => setSlot(e.target.value as Slot)}>{slots.map(s => <option key={s} value={s}>{s}</option>)}</select></label>
        <label className="block">Test message<textarea className="block w-full min-h-24 rounded border bg-background p-3" maxLength={4000} value={prompt} onChange={e => setPrompt(e.target.value)} /></label>
        <Button disabled={busy || !prompt.trim()} onClick={() => void action(async () => { setAnswer(await api("/playground", { slot, prompt, profile: data.config.profiles[slot] })); setNotice("Slot and fallbacks verified. You can now save and enable this configuration.") })}>{busy ? "Testing…" : "Test slot"}</Button>
        {answer && <div className="rounded border p-4 space-y-2"><p className="text-xs text-muted-foreground">{answer.served_model} · {answer.latency_ms} ms</p><p className="whitespace-pre-wrap">{answer.content}</p></div>}
      </TabsContent>
      <TabsContent value="keys" className="space-y-3">{data.keys.map(key => <div key={key.provider} className="rounded border p-4"><p>{key.provider} · {key.configured ? "Key configured" : "Key missing"}</p><p className="text-sm text-muted-foreground">{key.management}. Credentials remain on the server. Tenant key entry is disabled.</p></div>)}<p className="text-sm">Key changes currently use deployment settings. This console never displays the saved key.</p></TabsContent>
      <TabsContent value="analytics"><p className="text-sm text-muted-foreground mb-3">All organisations · Last 7 days · Recorded calls, including owner tests</p><div className="overflow-auto"><table className="w-full text-sm"><thead><tr>{["Model", "Calls", "Tokens", "Failures", "Latency (ms)"].map(h => <th key={h} className="text-left p-2">{h}</th>)}</tr></thead><tbody>{analytics.map((a, i) => <tr key={i}><td className="p-2">{a.model || "Unavailable"}</td><td>{a.calls}</td><td>{a.tokens}</td><td>{a.failures}</td><td>{a.latency_ms}</td></tr>)}</tbody></table></div></TabsContent>
    </Tabs><Button disabled={busy} onClick={() => void action(async () => { await api("", { config: data.config }, "PUT"); setNotice("Configuration saved.") })}>{busy ? "Working…" : "Save model and routing settings"}</Button>
  </CardContent></Card>
}
