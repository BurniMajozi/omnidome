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
  Play,
  Pencil,
  X,
  Check,
  ChevronDown,
  ChevronUp,
  History,
  Volume2,
  Library,
} from "lucide-react"
import { listAgents } from "@/lib/call-center-api"
import {
  listVoices,
  cloneVoice,
  speak,
  deleteVoice,
  clearFailedVoices,
  listPresetVoices,
  createPresetVoice,
  listPersonalities,
  createPersonality,
  updatePersonality,
  deletePersonality,
  setBinding,
  listBindings,
  deleteBinding,
  listGenerations,
  type VoiceProfile,
  type VoicePersonality,
  type AgentVoiceBinding,
  type BindingScope,
  type PresetVoice,
  type GenerationRecord,
} from "@/lib/voicebox-api"

const ORCHESTRATOR_AGENT_TYPES = ["customer_facing", "retention", "provisioning", "executive", "support"]

function cn(...classes: (string | false | undefined)[]) {
  return classes.filter(Boolean).join(" ")
}

// =========================================================================
// Clone Voice Card
// =========================================================================
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
          placeholder="Exact text spoken in the sample (improves cloning quality)..."
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
          {isSubmitting ? "Submitting..." : "Clone Voice"}
        </Button>
      </CardContent>
    </Card>
  )
}

// =========================================================================
// Preset Voice Browser Card
// =========================================================================
function PresetVoiceBrowserCard({ onAdded }: { onAdded: () => void }) {
  const [engine, setEngine] = useState("kokoro")
  const [presets, setPresets] = useState<PresetVoice[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [addingId, setAddingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Stale-closure guard: if the engine changes before the fetch resolves,
    // discard the result from the previous fetch.
    let stale = false
    setIsLoading(true)
    setError(null)
    listPresetVoices(engine)
      .then((r) => { if (!stale) setPresets(r.voices ?? []) })
      .catch((e: any) => { if (!stale) setError(e?.message ?? "Failed to load presets") })
      .finally(() => { if (!stale) setIsLoading(false) })
    return () => { stale = true }
  }, [engine])

  const handleAdd = async (p: PresetVoice) => {
    setAddingId(p.voice_id)
    try {
      await createPresetVoice({
        name: p.name,
        preset_engine: engine,
        preset_voice_id: p.voice_id,
        language: p.language ?? "en",
      })
      onAdded()
    } catch (err: any) {
      setError(err?.message ?? "Failed to add preset")
    } finally {
      setAddingId(null)
    }
  }

  return (
    <Card className="border-border bg-card/50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Library className="h-4 w-4 text-indigo-400" />
          Preset Voices
        </CardTitle>
        <CardDescription>Browse stock voices and add them to your library.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <select
          value={engine}
          onChange={(e) => setEngine(e.target.value)}
          title="Engine"
          aria-label="Engine"
          className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
        >
          <option value="kokoro">Kokoro</option>
          <option value="chatterbox">Chatterbox</option>
        </select>

        {isLoading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-cyan-400" />
          </div>
        ) : error ? (
          <p className="text-xs text-red-400 py-2">{error}</p>
        ) : presets.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">No presets available.</p>
        ) : (
          <div className="space-y-1 max-h-52 overflow-y-auto custom-scrollbar pr-1">
            {presets.map((p) => (
              <div
                key={p.voice_id}
                className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 p-2.5"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{p.name}</p>
                  <p className="text-[10px] text-muted-foreground">{p.gender} · {p.language}</p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-2 shrink-0 h-7 px-2 text-xs"
                  disabled={addingId === p.voice_id}
                  onClick={() => handleAdd(p)}
                >
                  {addingId === p.voice_id ? <Loader2 className="h-3 w-3 animate-spin" /> : "Add"}
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// =========================================================================
// Voice List Card
// Item 1  — preview button with AbortController (cancels previous on new click)
// Item 14 — grey non-active preview buttons instead of disabling them
// =========================================================================
function VoiceListCard({
  voices,
  onDeleted,
}: {
  voices: VoiceProfile[]
  onDeleted: () => void
}) {
  const [previewingId, setPreviewingId] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const [isClearingFailed, setIsClearingFailed] = useState(false)

  // Cleanup on unmount — stop any playing audio
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.src = ""
      }
    }
  }, [])

  const handlePreview = async (v: VoiceProfile) => {
    if (v.status !== "ready") return

    // Cancel any in-flight preview request and stop current playback
    abortRef.current?.abort()
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.src = ""
    }

    const controller = new AbortController()
    abortRef.current = controller
    setPreviewingId(v.id)

    try {
      const blob = await speak(
        { text: "Hello, this is a preview of my voice.", voice_profile_id: v.id },
        controller.signal
      )
      if (controller.signal.aborted) return

      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onended = () => URL.revokeObjectURL(url)
      await audio.play()
    } catch (err: any) {
      if (err?.name === "AbortError") return // cancelled by user clicking another preview
      console.error("Preview failed", err)
    } finally {
      setPreviewingId((cur) => (cur === v.id ? null : cur))
    }
  }

  const failedCount = voices.filter((v) => v.status === "failed").length

  const handleClearFailed = async () => {
    setIsClearingFailed(true)
    try {
      await clearFailedVoices()
      onDeleted()
    } finally {
      setIsClearingFailed(false)
    }
  }

  return (
    <Card className="border-border bg-card/50">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Voices</CardTitle>
          {failedCount > 0 && (
            <Button
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-[10px] text-red-400 hover:text-red-300"
              disabled={isClearingFailed}
              onClick={handleClearFailed}
            >
              {isClearingFailed ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
              Clear {failedCount} failed
            </Button>
          )}
        </div>
        <CardDescription>
          {voices.length} voice{voices.length === 1 ? "" : "s"} for this tenant
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {voices.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">No voices yet.</p>
        )}
        {voices.map((v) => (
          <div
            key={v.id}
            className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 p-3"
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground truncate">{v.name}</p>
              <div className="mt-1 flex items-center gap-1.5 flex-wrap">
                <Badge variant="outline" className="text-[10px] capitalize">{v.voice_type}</Badge>
                <Badge
                  className={cn(
                    "text-[10px] capitalize",
                    v.status === "ready" && "bg-emerald-500/20 text-emerald-400",
                    v.status === "pending" && "bg-amber-500/20 text-amber-400 animate-pulse",
                    v.status === "failed" && "bg-red-500/20 text-red-400",
                  )}
                >
                  {v.status === "pending" ? "Processing..." : v.status}
                </Badge>
              </div>
              {v.status === "failed" && v.error && (
                <p className="mt-1 text-[10px] text-red-400 truncate">{v.error}</p>
              )}
            </div>
            <div className="flex items-center gap-1 ml-2 shrink-0">
              {/* Preview: only disabled when voice not ready; grey (not disabled) when another is loading */}
              <Button
                size="icon"
                variant="ghost"
                disabled={v.status !== "ready"}
                onClick={() => handlePreview(v)}
                title={previewingId === v.id ? "Playing..." : "Preview voice"}
                className={cn(
                  "transition-opacity",
                  previewingId !== null && previewingId !== v.id && "opacity-40",
                )}
              >
                {previewingId === v.id ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Volume2
                    className={cn(
                      "h-4 w-4",
                      v.status === "ready" ? "text-cyan-400" : "text-muted-foreground/40",
                    )}
                  />
                )}
              </Button>
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
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

// =========================================================================
// Personalities Card
// =========================================================================
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

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState("")
  const [editDescription, setEditDescription] = useState("")
  const [editStylePrompt, setEditStylePrompt] = useState("")
  const [editVoiceId, setEditVoiceId] = useState("")
  const [isSavingEdit, setIsSavingEdit] = useState(false)

  const startEdit = (p: VoicePersonality) => {
    setEditingId(p.id)
    setEditName(p.name)
    setEditDescription(p.description ?? "")
    setEditStylePrompt(p.style_prompt ?? "")
    setEditVoiceId(p.default_voice_profile_id ?? "")
  }

  const cancelEdit = () => setEditingId(null)

  const saveEdit = async () => {
    if (!editingId) return
    setIsSavingEdit(true)
    try {
      await updatePersonality(editingId, {
        name: editName,
        description: editDescription || undefined,
        style_prompt: editStylePrompt || undefined,
        default_voice_profile_id: editVoiceId || undefined,
      })
      setEditingId(null)
      onChanged()
    } finally {
      setIsSavingEdit(false)
    }
  }

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

  const readyVoices = voices.filter((v) => v.status === "ready")

  return (
    <Card className="border-border bg-card/50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Wand2 className="h-4 w-4 text-violet-400" />
          Voice Personalities
        </CardTitle>
        <CardDescription>
          Reusable personas — a style prompt that drives in-character rewriting before synthesis.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          {personalities.length === 0 && (
            <p className="text-sm text-muted-foreground">No personalities yet.</p>
          )}
          {personalities.map((p) =>
            editingId === p.id ? (
              <div key={p.id} className="rounded-lg border border-border bg-background/50 p-3 space-y-2">
                <Input value={editName} onChange={(e) => setEditName(e.target.value)} placeholder="Name" className="h-8 text-sm" />
                <Input value={editDescription} onChange={(e) => setEditDescription(e.target.value)} placeholder="Description (optional)" className="h-8 text-sm" />
                <textarea
                  value={editStylePrompt}
                  onChange={(e) => setEditStylePrompt(e.target.value)}
                  rows={2}
                  placeholder="Style prompt"
                  className="w-full rounded-lg border border-border bg-card p-2.5 text-sm text-foreground placeholder-muted-foreground resize-none"
                />
                <select
                  value={editVoiceId}
                  onChange={(e) => setEditVoiceId(e.target.value)}
                  title="Default voice"
                  aria-label="Default voice"
                  className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
                >
                  <option value="">No default voice</option>
                  {readyVoices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                </select>
                <div className="flex gap-2">
                  <Button size="sm" className="flex-1" disabled={isSavingEdit || !editName.trim()} onClick={saveEdit}>
                    {isSavingEdit ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Check className="mr-1.5 h-3.5 w-3.5" />}
                    Save
                  </Button>
                  <Button size="sm" variant="ghost" onClick={cancelEdit}>
                    <X className="mr-1.5 h-3.5 w-3.5" /> Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div key={p.id} className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 p-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-foreground">{p.name}</p>
                  {p.description && <p className="text-xs text-muted-foreground truncate">{p.description}</p>}
                </div>
                <div className="flex items-center gap-1 ml-2 shrink-0">
                  <Button size="icon" variant="ghost" onClick={() => startEdit(p)} title="Edit personality">
                    <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
                  </Button>
                  <Button size="icon" variant="ghost" onClick={async () => { await deletePersonality(p.id); onChanged() }}>
                    <Trash2 className="h-4 w-4 text-muted-foreground" />
                  </Button>
                </div>
              </div>
            )
          )}
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
            {readyVoices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
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

// =========================================================================
// Bindings Card
// =========================================================================
function BindingsCard({
  voices,
  personalities,
}: {
  voices: VoiceProfile[]
  personalities: VoicePersonality[]
}) {
  const [scope, setScope] = useState<BindingScope>("call_center_agent")
  const [callCenterAgents, setCallCenterAgents] = useState<Array<{ id: string; name: string }>>([])
  const [scopeRef, setScopeRef] = useState("")
  const [voiceId, setVoiceId] = useState("")
  const [personalityId, setPersonalityId] = useState("")
  const [bindings, setBindings] = useState<AgentVoiceBinding[]>([])
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const refreshBindings = useCallback(() => {
    listBindings().then(setBindings).catch(() => {})
  }, [])

  useEffect(() => {
    listAgents()
      .then((agents: any[]) => setCallCenterAgents(agents.map((a) => ({ id: a.id, name: a.name }))))
      .catch(() => {})
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
    setSaveError(null)
    try {
      await setBinding({ scope, scope_ref: scopeRef, voice_profile_id: voiceId, personality_id: personalityId || undefined })
      refreshBindings()
    } catch (err: any) {
      setSaveError(err?.message ?? "Failed to save binding")
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async (b: AgentVoiceBinding) => {
    setDeletingId(b.id)
    try {
      await deleteBinding(b.scope, b.scope_ref)
      refreshBindings()
    } catch (err) {
      console.error("Failed to delete binding", err)
    } finally {
      setDeletingId(null)
    }
  }

  const labelFor = (b: AgentVoiceBinding) => {
    if (b.scope === "call_center_agent")
      return callCenterAgents.find((a) => a.id === b.scope_ref)?.name ?? b.scope_ref
    return b.scope_ref
  }

  const readyVoices = voices.filter((v) => v.status === "ready")

  return (
    <Card className="border-border bg-card/50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Link2 className="h-4 w-4 text-amber-400" />
          Voice Bindings
        </CardTitle>
        <CardDescription>
          Assign a voice (+ optional personality) to a call-center agent, an orchestrator agent, or the webchat bot.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          {bindings.length === 0 && <p className="text-sm text-muted-foreground">No bindings yet.</p>}
          {bindings.map((b) => (
            <div key={b.id} className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 p-3 text-sm">
              <div className="min-w-0 flex-1">
                <span className="font-medium text-foreground">{labelFor(b)}</span>
                <span className="ml-2 text-xs text-muted-foreground">({b.scope.replace(/_/g, " ")})</span>
                <p className="text-[10px] text-muted-foreground mt-0.5 truncate">
                  {readyVoices.find((v) => v.id === b.voice_profile_id)?.name ?? b.voice_profile_id}
                </p>
              </div>
              <Button
                size="icon"
                variant="ghost"
                className="ml-2 shrink-0"
                disabled={deletingId === b.id}
                onClick={() => handleDelete(b)}
                title="Remove binding"
              >
                {deletingId === b.id
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />}
              </Button>
            </div>
          ))}
        </div>

        <div className="space-y-2 border-t border-border pt-3">
          <select value={scope} onChange={(e) => { setScope(e.target.value as BindingScope); setScopeRef("") }}
            title="Scope" aria-label="Scope"
            className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
            <option value="call_center_agent">Call Center Agent</option>
            <option value="orchestrator_agent_type">Orchestrator Agent</option>
            <option value="webchat_bot">Webchat Bot</option>
          </select>
          <select value={scopeRef} onChange={(e) => setScopeRef(e.target.value)}
            title="Target" aria-label="Target"
            className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
            <option value="">Select target...</option>
            {scopeRefOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select value={voiceId} onChange={(e) => setVoiceId(e.target.value)}
            title="Voice" aria-label="Voice"
            className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
            <option value="">Select voice...</option>
            {readyVoices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
          <select value={personalityId} onChange={(e) => setPersonalityId(e.target.value)}
            title="Personality" aria-label="Personality"
            className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
            <option value="">No personality</option>
            {personalities.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <Button size="sm" className="w-full" disabled={isSaving || !scopeRef || !voiceId} onClick={handleSave}>
            {isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Save Binding
          </Button>
          {saveError && (
            <p className="flex items-center gap-1.5 text-xs text-red-400">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" /> {saveError}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// =========================================================================
// Generation History Card
// =========================================================================
function GenerationHistoryCard({ voices }: { voices: VoiceProfile[] }) {
  const [isOpen, setIsOpen] = useState(false)
  const [generations, setGenerations] = useState<GenerationRecord[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [replayingId, setReplayingId] = useState<string | null>(null)
  const [replayError, setReplayError] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.src = ""
      }
    }
  }, [])

  const refresh = useCallback(() => {
    setIsLoading(true)
    listGenerations()
      .then(setGenerations)
      .catch(() => {})
      .finally(() => setIsLoading(false))
  }, [])

  useEffect(() => {
    if (isOpen) refresh()
  }, [isOpen, refresh])

  const handleReplay = async (g: GenerationRecord) => {
    abortRef.current?.abort()
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.src = ""
    }

    const controller = new AbortController()
    abortRef.current = controller
    setReplayingId(g.id)
    setReplayError(null)

    try {
      const blob = await speak(
        { text: g.source_text, voice_profile_id: g.voice_profile_id },
        controller.signal
      )
      if (controller.signal.aborted) return

      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onended = () => URL.revokeObjectURL(url)
      await audio.play()
    } catch (err: any) {
      if (err?.name === "AbortError") return
      setReplayError(err?.message ?? "Replay failed")
    } finally {
      setReplayingId((cur) => (cur === g.id ? null : cur))
    }
  }

  return (
    <Card className="border-border bg-card/50">
      <CardHeader
        className="pb-3 cursor-pointer select-none"
        onClick={() => setIsOpen((o) => !o)}
      >
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <History className="h-4 w-4 text-muted-foreground" />
            Generation History
          </CardTitle>
          {isOpen
            ? <ChevronUp className="h-4 w-4 text-muted-foreground" />
            : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </div>
        {isOpen && <CardDescription>Recent TTS generations for this tenant</CardDescription>}
      </CardHeader>
      {isOpen && (
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-cyan-400" />
            </div>
          ) : generations.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No generations yet.</p>
          ) : (
            <div className="space-y-1.5 max-h-72 overflow-y-auto custom-scrollbar pr-1">
              {generations.map((g) => (
                <div
                  key={g.id}
                  className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 p-2.5 gap-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-foreground truncate">{g.source_text}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      {g.voice_name ?? "Unknown voice"} · {g.created_at ? new Date(g.created_at).toLocaleString() : "—"}
                    </p>
                  </div>
                  <Button
                    size="icon"
                    variant="ghost"
                    className={cn("shrink-0 h-7 w-7", replayingId !== null && replayingId !== g.id && "opacity-40")}
                    onClick={() => handleReplay(g)}
                    title="Replay"
                  >
                    {replayingId === g.id
                      ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      : <Play className="h-3.5 w-3.5 text-cyan-400" />}
                  </Button>
                </div>
              ))}
            </div>
          )}
          {replayError && (
            <p className="flex items-center gap-1.5 text-xs text-red-400 mt-2">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" /> {replayError}
            </p>
          )}
        </CardContent>
      )}
    </Card>
  )
}

// =========================================================================
// Main export — pending voice polling
// =========================================================================
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

  // Poll every 3 s while any voice is pending
  const statusKey = voices.map((v) => v.status).join(",")
  useEffect(() => {
    if (!voices.some((v) => v.status === "pending")) return
    const t = setInterval(() => {
      listVoices()
        .then((fresh) => setVoices(fresh))
        .catch(() => {})
    }, 3000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusKey])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-cyan-400" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4">
          <CloneVoiceCard onCloned={refresh} />
          <PresetVoiceBrowserCard onAdded={refresh} />
        </div>
        <div className="space-y-4">
          <VoiceListCard voices={voices} onDeleted={refresh} />
          <PersonalitiesCard personalities={personalities} voices={voices} onChanged={refresh} />
        </div>
        <div className="space-y-4">
          <BindingsCard voices={voices} personalities={personalities} />
        </div>
      </div>
      <GenerationHistoryCard voices={voices} />
    </div>
  )
}
