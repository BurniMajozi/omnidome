"use client"

import { useEffect, useState, useRef, useCallback } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Mic,
  MicOff,
  Upload,
  Sparkles,
  Trash2,
  Loader2,
  Wand2,
  Link2,
  AlertCircle,
} from "lucide-react"
import { listAgents } from "@/lib/call-center-api"
import {
  listVoices,
  cloneVoice,
  deleteVoice,
  listPersonalities,
  createPersonality,
  deletePersonality,
  setBinding,
  listBindings,
  type VoiceProfile,
  type VoicePersonality,
  type AgentVoiceBinding,
  type BindingScope,
} from "@/lib/voicebox-api"

const ORCHESTRATOR_AGENT_TYPES = ["customer_facing", "retention", "provisioning", "executive", "support"]

function cn(...classes: (string | false | undefined)[]) {
  return classes.filter(Boolean).join(" ")
}

// ═══════════════════════════════════════════════════════════════════════
// Voice cloning
// ═══════════════════════════════════════════════════════════════════════
function CloneVoiceCard({ onCloned }: { onCloned: () => void }) {
  const [name, setName] = useState("")
  const [referenceText, setReferenceText] = useState("")
  const [language, setLanguage] = useState("en")
  const [isRecording, setIsRecording] = useState(false)
  const [sample, setSample] = useState<Blob | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" })
      chunks.current = []
      recorder.ondataavailable = (e) => e.data.size > 0 && chunks.current.push(e.data)
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        setSample(new Blob(chunks.current, { type: "audio/webm" }))
      }
      recorder.start()
      mediaRecorder.current = recorder
      setIsRecording(true)
    } catch (err) {
      console.error("Microphone access denied", err)
    }
  }, [])

  const stopRecording = useCallback(() => {
    mediaRecorder.current?.stop()
    setIsRecording(false)
  }, [])

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) setSample(file)
  }

  const handleSubmit = async () => {
    if (!name.trim() || !referenceText.trim() || !sample) return
    setIsSubmitting(true)
    setError(null)
    try {
      await cloneVoice({ name, reference_text: referenceText, language, sample })
      setName("")
      setReferenceText("")
      setSample(null)
      onCloned()
    } catch (err: any) {
      setError(err?.message ?? "Cloning failed")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card className="border-border bg-card/50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Sparkles className="h-4 w-4 text-cyan-400" />
          Clone a Voice
        </CardTitle>
        <CardDescription>Record or upload a sample, then transcribe what's said in it.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Input placeholder="Voice name (e.g. Sipho — Sales)" value={name} onChange={(e) => setName(e.target.value)} />
        <textarea
          value={referenceText}
          onChange={(e) => setReferenceText(e.target.value)}
          rows={3}
          placeholder="Exact text spoken in the sample (improves cloning quality)…"
          className="w-full rounded-lg border border-border bg-card p-3 text-sm text-foreground placeholder-muted-foreground resize-none"
        />
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          title="Language"
          aria-label="Language"
          className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
        >
          <option value="en">English</option>
          <option value="es">Spanish</option>
          <option value="fr">French</option>
          <option value="de">German</option>
          <option value="pt">Portuguese</option>
        </select>

        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant={isRecording ? "destructive" : "outline"}
            size="sm"
            onClick={isRecording ? stopRecording : startRecording}
            className="flex-1"
          >
            {isRecording ? <MicOff className="mr-2 h-4 w-4" /> : <Mic className="mr-2 h-4 w-4" />}
            {isRecording ? "Stop" : "Record sample"}
          </Button>
          <input ref={fileInputRef} type="file" accept="audio/*" onChange={handleFileUpload} className="hidden" />
          <Button type="button" variant="outline" size="sm" onClick={() => fileInputRef.current?.click()} className="flex-1">
            <Upload className="mr-2 h-4 w-4" /> Upload
          </Button>
        </div>
        {sample && <p className="text-xs text-emerald-400">Sample ready ({Math.round(sample.size / 1024)} KB)</p>}
        {error && (
          <p className="flex items-start gap-1.5 text-xs text-red-400">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {error}
          </p>
        )}

        <Button
          className="w-full"
          disabled={isSubmitting || !name.trim() || !referenceText.trim() || !sample}
          onClick={handleSubmit}
        >
          {isSubmitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
          {isSubmitting ? "Cloning…" : "Clone Voice"}
        </Button>
      </CardContent>
    </Card>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// Voice list
// ═══════════════════════════════════════════════════════════════════════
function VoiceListCard({ voices, onDeleted }: { voices: VoiceProfile[]; onDeleted: () => void }) {
  return (
    <Card className="border-border bg-card/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Voices</CardTitle>
        <CardDescription>{voices.length} voice{voices.length === 1 ? "" : "s"} for this tenant</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {voices.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">No voices yet.</p>}
        {voices.map((v) => (
          <div key={v.id} className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 p-3">
            <div>
              <p className="text-sm font-medium text-foreground">{v.name}</p>
              <div className="mt-1 flex items-center gap-1.5">
                <Badge variant="outline" className="text-[10px] capitalize">{v.voice_type}</Badge>
                <Badge
                  className={cn(
                    "text-[10px] capitalize",
                    v.status === "ready" && "bg-emerald-500/20 text-emerald-400",
                    v.status === "pending" && "bg-amber-500/20 text-amber-400",
                    v.status === "failed" && "bg-red-500/20 text-red-400"
                  )}
                >
                  {v.status}
                </Badge>
              </div>
              {v.status === "failed" && v.error && (
                <p className="mt-1 text-[10px] text-red-400">{v.error}</p>
              )}
            </div>
            <Button
              size="icon"
              variant="ghost"
              onClick={async () => {
                await deleteVoice(v.id)
                onDeleted()
              }}
            >
              <Trash2 className="h-4 w-4 text-muted-foreground" />
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// Personalities
// ═══════════════════════════════════════════════════════════════════════
function PersonalitiesCard({
  personalities,
  voices,
  onChanged,
}: {
  personalities: VoicePersonality[]
  voices: VoiceProfile[]
  onChanged: () => void
}) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [stylePrompt, setStylePrompt] = useState("")
  const [defaultVoiceId, setDefaultVoiceId] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleCreate = async () => {
    if (!name.trim()) return
    setIsSubmitting(true)
    try {
      await createPersonality({
        name,
        description: description || undefined,
        style_prompt: stylePrompt || undefined,
        default_voice_profile_id: defaultVoiceId || undefined,
      })
      setName("")
      setDescription("")
      setStylePrompt("")
      setDefaultVoiceId("")
      onChanged()
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card className="border-border bg-card/50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Wand2 className="h-4 w-4 text-violet-400" />
          Voice Personalities
        </CardTitle>
        <CardDescription>Reusable personas — a style prompt that drives in-character rewriting before synthesis.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          {personalities.length === 0 && <p className="text-sm text-muted-foreground">No personalities yet.</p>}
          {personalities.map((p) => (
            <div key={p.id} className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 p-3">
              <div>
                <p className="text-sm font-medium text-foreground">{p.name}</p>
                {p.description && <p className="text-xs text-muted-foreground">{p.description}</p>}
              </div>
              <Button
                size="icon"
                variant="ghost"
                onClick={async () => {
                  await deletePersonality(p.id)
                  onChanged()
                }}
              >
                <Trash2 className="h-4 w-4 text-muted-foreground" />
              </Button>
            </div>
          ))}
        </div>

        <div className="space-y-2 border-t border-border pt-3">
          <Input placeholder="Personality name (e.g. Friendly & Concise)" value={name} onChange={(e) => setName(e.target.value)} />
          <Input placeholder="Short description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />
          <textarea
            value={stylePrompt}
            onChange={(e) => setStylePrompt(e.target.value)}
            rows={2}
            placeholder="Style prompt — e.g. 'Warm, upbeat, uses short sentences, never sounds scripted.'"
            className="w-full rounded-lg border border-border bg-card p-3 text-sm text-foreground placeholder-muted-foreground resize-none"
          />
          <select
            value={defaultVoiceId}
            onChange={(e) => setDefaultVoiceId(e.target.value)}
            title="Default voice"
            aria-label="Default voice"
            className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
          >
            <option value="">No default voice</option>
            {voices.map((v) => (
              <option key={v.id} value={v.id}>{v.name}</option>
            ))}
          </select>
          <Button size="sm" className="w-full" disabled={isSubmitting || !name.trim()} onClick={handleCreate}>
            {isSubmitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Add Personality
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// Bindings — assign a voice to a call-center agent, orchestrator agent
// type, or the webchat bot
// ═══════════════════════════════════════════════════════════════════════
function BindingsCard({ voices, personalities }: { voices: VoiceProfile[]; personalities: VoicePersonality[] }) {
  const [scope, setScope] = useState<BindingScope>("call_center_agent")
  const [callCenterAgents, setCallCenterAgents] = useState<Array<{ id: string; name: string }>>([])
  const [scopeRef, setScopeRef] = useState("")
  const [voiceId, setVoiceId] = useState("")
  const [personalityId, setPersonalityId] = useState("")
  const [bindings, setBindings] = useState<AgentVoiceBinding[]>([])
  const [isSaving, setIsSaving] = useState(false)

  const refreshBindings = useCallback(() => {
    listBindings().then(setBindings).catch(() => {})
  }, [])

  useEffect(() => {
    listAgents().then((agents: any[]) => setCallCenterAgents(agents.map((a) => ({ id: a.id, name: a.name })))).catch(() => {})
    refreshBindings()
  }, [refreshBindings])

  const scopeRefOptions =
    scope === "call_center_agent"
      ? callCenterAgents.map((a) => ({ value: a.id, label: a.name }))
      : scope === "orchestrator_agent_type"
        ? ORCHESTRATOR_AGENT_TYPES.map((t) => ({ value: t, label: t }))
        : [{ value: "default", label: "Webchat bot (default)" }]

  const handleSave = async () => {
    if (!scopeRef || !voiceId) return
    setIsSaving(true)
    try {
      await setBinding({ scope, scope_ref: scopeRef, voice_profile_id: voiceId, personality_id: personalityId || undefined })
      refreshBindings()
    } finally {
      setIsSaving(false)
    }
  }

  const labelFor = (b: AgentVoiceBinding) => {
    if (b.scope === "call_center_agent") return callCenterAgents.find((a) => a.id === b.scope_ref)?.name ?? b.scope_ref
    return b.scope_ref
  }

  return (
    <Card className="border-border bg-card/50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Link2 className="h-4 w-4 text-amber-400" />
          Voice Bindings
        </CardTitle>
        <CardDescription>Assign a voice (+ optional personality) to a call-center agent, an orchestrator agent, or the webchat bot.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          {bindings.length === 0 && <p className="text-sm text-muted-foreground">No bindings yet.</p>}
          {bindings.map((b) => (
            <div key={b.id} className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 p-3 text-sm">
              <div>
                <span className="font-medium text-foreground">{labelFor(b)}</span>
                <span className="ml-2 text-xs text-muted-foreground">({b.scope.replace(/_/g, " ")})</span>
              </div>
              <span className="text-xs text-muted-foreground">{voices.find((v) => v.id === b.voice_profile_id)?.name ?? b.voice_profile_id}</span>
            </div>
          ))}
        </div>

        <div className="space-y-2 border-t border-border pt-3">
          <select
            value={scope}
            onChange={(e) => { setScope(e.target.value as BindingScope); setScopeRef("") }}
            title="Scope"
            aria-label="Scope"
            className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
          >
            <option value="call_center_agent">Call Center Agent</option>
            <option value="orchestrator_agent_type">Orchestrator Agent</option>
            <option value="webchat_bot">Webchat Bot</option>
          </select>
          <select
            value={scopeRef}
            onChange={(e) => setScopeRef(e.target.value)}
            title="Target"
            aria-label="Target"
            className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
          >
            <option value="">Select target…</option>
            {scopeRefOptions.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <select
            value={voiceId}
            onChange={(e) => setVoiceId(e.target.value)}
            title="Voice"
            aria-label="Voice"
            className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
          >
            <option value="">Select voice…</option>
            {voices.map((v) => (
              <option key={v.id} value={v.id}>{v.name}</option>
            ))}
          </select>
          <select
            value={personalityId}
            onChange={(e) => setPersonalityId(e.target.value)}
            title="Personality"
            aria-label="Personality"
            className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
          >
            <option value="">No personality</option>
            {personalities.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <Button size="sm" className="w-full" disabled={isSaving || !scopeRef || !voiceId} onClick={handleSave}>
            {isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Save Binding
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// Main export
// ═══════════════════════════════════════════════════════════════════════
export function VoiceStudioTab() {
  const [voices, setVoices] = useState<VoiceProfile[]>([])
  const [personalities, setPersonalities] = useState<VoicePersonality[]>([])
  const [isLoading, setIsLoading] = useState(true)

  const refresh = useCallback(() => {
    Promise.all([listVoices(), listPersonalities()])
      .then(([v, p]) => {
        setVoices(v)
        setPersonalities(p)
      })
      .catch((err) => console.error("Failed to load voice studio data", err))
      .finally(() => setIsLoading(false))
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-cyan-400" />
      </div>
    )
  }

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4">
        <CloneVoiceCard onCloned={refresh} />
      </div>
      <div className="space-y-4">
        <VoiceListCard voices={voices} onDeleted={refresh} />
        <PersonalitiesCard personalities={personalities} voices={voices} onChanged={refresh} />
      </div>
      <div className="space-y-4">
        <BindingsCard voices={voices} personalities={personalities} />
      </div>
    </div>
  )
}
