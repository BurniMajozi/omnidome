"use client"

import { useState, useRef, useCallback, useEffect } from "react"
import { supabase } from "@/lib/supabase/client"
import { listVoices, speak as voiceboxSpeak, type VoiceProfile } from "@/lib/voicebox-api"
import { toWavWithStats, SILENCE_RMS_THRESHOLD } from "@/lib/audio-utils"
import {
  MIC_STORAGE_KEY,
  DEFAULT_MIC_ID,
  isBrowserPseudoMic,
  findPreferredPhysicalMic,
  stripMicAliasPrefix,
  resolvePreferredMicId,
  micAudioConstraints,
  saveMicId,
} from "@/lib/mic-device"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  Mic,
  MicOff,
  Upload,
  Play,
  Square,
  Volume2,
  Copy,
  Download,
  Bot,
  Brain,
  FileAudio,
  Loader2,
  Sparkles,
  MessageSquare,
  Target,
  Hash,
  TrendingUp,
  TrendingDown,
  Minus,
  ChevronRight,
  AlertCircle,
  PhoneCall,
  PhoneOff,
  PhoneIncoming,
  PhoneOutgoing,
  CheckCircle2,
  X,
  Radio,
  RefreshCw,
} from "lucide-react"
import { deployVoiceAgent, stopVoiceAgent, listVoiceAgentDeployments } from "@/lib/call-center-api"

const API_BASE = "/svc/call-center"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const FALLBACK_USER_ID = "00000000-0000-0000-0000-000000000002"

async function getTenantId(): Promise<string> {
  const { data } = await supabase.auth.getSession()
  return (
    data.session?.user?.user_metadata?.tenant_id ??
    data.session?.user?.app_metadata?.tenant_id ??
    FALLBACK_TENANT_ID
  )
}

async function getUserId(): Promise<string> {
  const { data } = await supabase.auth.getSession()
  return data.session?.user?.id ?? FALLBACK_USER_ID
}

async function getAuthHeaders(): Promise<Record<string, string>> {
  const [tenantId, userId] = await Promise.all([getTenantId(), getUserId()])
  return { "x-tenant-id": tenantId, "x-user-id": userId }
}

// ─── Helpers ───────────────────────────────────────────────────────────
function cn(...classes: (string | false | undefined)[]) {
  return classes.filter(Boolean).join(" ")
}

function getSentimentColor(sentiment: string) {
  switch (sentiment) {
    case "positive": return "text-emerald-400"
    case "negative": return "text-red-400"
    default: return "text-neutral-400"
  }
}

function getSentimentIcon(sentiment: string) {
  switch (sentiment) {
    case "positive": return TrendingUp
    case "negative": return TrendingDown
    default: return Minus
  }
}

// ─── Types ─────────────────────────────────────────────────────────────
interface TranscriptResult {
  transcript: string
  confidence: number
  words?: Array<{ word: string; start: number; end: number; confidence: number }>
}

interface AudioIntelResult {
  transcript: string
  confidence: number
  summary: string
  sentiments: {
    average: { sentiment?: string; sentiment_score?: number }
    segments: Array<{ text: string; sentiment: string; sentiment_score: number }>
  }
  intents: {
    segments: Array<{ text: string; intents: Array<{ intent: string; confidence_score: number }> }>
  }
  topics: {
    segments: Array<{ text: string; topics: Array<{ topic: string; confidence_score: number }> }>
  }
}

// ═══════════════════════════════════════════════════════════════════════
// Speech-to-Text Tab
// ═══════════════════════════════════════════════════════════════════════
function SpeechToTextPanel() {
  const [isRecording, setIsRecording] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [processingSeconds, setProcessingSeconds] = useState(0)

  useEffect(() => {
    if (!isProcessing) {
      setProcessingSeconds(0)
      return
    }
    const t = setInterval(() => setProcessingSeconds((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [isProcessing])
  const [result, setResult] = useState<TranscriptResult | null>(null)
  const [language, setLanguage] = useState("en")
  const [error, setError] = useState<string | null>(null)
  const [audioInputs, setAudioInputs] = useState<MediaDeviceInfo[]>([])
  const [selectedMicId, setSelectedMicId] = useState(DEFAULT_MIC_ID)
  const [activeMicLabel, setActiveMicLabel] = useState<string | null>(null)
  const [micListError, setMicListError] = useState<string | null>(null)
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const refreshAudioInputs = useCallback(async (requestPermission = false) => {
    if (!navigator.mediaDevices?.enumerateDevices) {
      setMicListError("Microphone device listing is not available in this browser.")
      return
    }

    let permissionStream: MediaStream | null = null
    setMicListError(null)

    try {
      if (requestPermission) {
        permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true })
      }

      const devices = await navigator.mediaDevices.enumerateDevices()
      const inputs = devices.filter((device) => device.kind === "audioinput")
      const preferredMic = findPreferredPhysicalMic(inputs)
      setAudioInputs(inputs)
      setSelectedMicId((current) =>
        current && !isBrowserPseudoMic(current) && inputs.some((device) => device.deviceId === current)
          ? current
          : preferredMic?.deviceId ?? DEFAULT_MIC_ID,
      )
    } catch (err) {
      console.error("Could not list microphone devices", err)
      setMicListError(err instanceof Error ? err.message : "Could not list microphone devices.")
    } finally {
      permissionStream?.getTracks().forEach((track) => track.stop())
    }
  }, [])

  useEffect(() => {
    try {
      const savedMicId = window.localStorage.getItem(MIC_STORAGE_KEY)
      if (savedMicId) setSelectedMicId(savedMicId)
    } catch {
      // Ignore private browsing / blocked storage.
    }

    refreshAudioInputs(false)

    const handleDeviceChange = () => refreshAudioInputs(false)
    navigator.mediaDevices?.addEventListener?.("devicechange", handleDeviceChange)
    return () => {
      navigator.mediaDevices?.removeEventListener?.("devicechange", handleDeviceChange)
    }
  }, [refreshAudioInputs])

  const selectableAudioInputs = audioInputs.filter(
    (device) => device.deviceId && !isBrowserPseudoMic(device.deviceId),
  )
  const defaultMicLabel =
    audioInputs.find((device) => device.deviceId === DEFAULT_MIC_ID)?.label || "System default microphone"
  const defaultMicOptionLabel =
    defaultMicLabel === "System default microphone"
      ? "Browser default microphone"
      : `Browser default (${stripMicAliasPrefix(defaultMicLabel)})`
  const selectedMicLabel =
    selectedMicId === DEFAULT_MIC_ID
      ? defaultMicOptionLabel
      : audioInputs.find((device) => device.deviceId === selectedMicId)?.label || "Selected microphone"

  const handleMicChange = useCallback((deviceId: string) => {
    setSelectedMicId(deviceId)
    setActiveMicLabel(null)
    saveMicId(deviceId)
  }, [])

  const sendAudioForTranscription = useCallback(async (blob: Blob) => {
    setIsProcessing(true)
    setResult(null)
    setError(null)
    try {
      const form = new FormData()
      form.append("file", blob, blob.type === "audio/wav" ? "recording.wav" : "recording.webm")
      form.append("language", language)

      const res = await fetch(`${API_BASE}/ai/speech-to-text`, {
        method: "POST",
        headers: await getAuthHeaders(),
        body: form,
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setResult(data)
    } catch (err) {
      console.error(err)
      setError(err instanceof Error ? err.message : "Transcription failed")
    } finally {
      setIsProcessing(false)
    }
  }, [language])

  const startRecording = useCallback(async () => {
    setError(null)
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Microphone recording is not available in this browser.")
      }

      const resolvedMicId = await resolvePreferredMicId(selectedMicId)
      if (resolvedMicId !== selectedMicId) {
        setSelectedMicId(resolvedMicId)
        saveMicId(resolvedMicId)
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: micAudioConstraints(resolvedMicId) })
      const recordingMicLabel = stream.getAudioTracks()[0]?.label || selectedMicLabel
      setActiveMicLabel(recordingMicLabel)
      refreshAudioInputs(false)

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : ""
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
      chunks.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.current.push(e.data)
      }

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const rawBlob = new Blob(chunks.current, { type: mimeType || "audio/webm" })
        if (rawBlob.size < 100) {
          setError("No audio captured — hold the button while speaking, then release.")
          return
        }
        // Convert to 16kHz WAV so the server doesn't have to rely on
        // librosa's deprecated audioread opus/webm fallback (which causes
        // Whisper to hallucinate instead of transcribing real speech).
        const stats = await toWavWithStats(rawBlob).catch(() => null)
        if (stats && stats.rms < SILENCE_RMS_THRESHOLD) {
          setError(
            `The recording from "${recordingMicLabel}" contains no sound. Select the Senary Audio microphone here and try again.`,
          )
          return
        }
        await sendAudioForTranscription(stats ? stats.wav : rawBlob)
      }

      recorder.start(250) // timeslice ensures ondataavailable fires even for short recordings
      mediaRecorder.current = recorder
      setIsRecording(true)
    } catch (err) {
      console.error("Microphone access denied", err)
      setError(
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone access was denied. Allow microphone access for this site in your browser's address-bar permissions, then try again."
          : err instanceof DOMException && err.name === "NotFoundError"
            ? "No microphone was found on this device."
            : `Could not start recording: ${err instanceof Error ? err.message : String(err)}`,
      )
    }
  }, [refreshAudioInputs, selectedMicId, selectedMicLabel, sendAudioForTranscription])

  const stopRecording = useCallback(() => {
    mediaRecorder.current?.stop()
    setIsRecording(false)
  }, [])

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    await sendAudioForTranscription(file)
  }

  const copyTranscript = () => {
    if (result?.transcript) navigator.clipboard.writeText(result.transcript)
  }

  const downloadTranscript = () => {
    if (!result?.transcript) return
    const blob = new Blob([result.transcript], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "transcript.txt"
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      {/* Sub-tabs */}
      <div className="flex items-center gap-6 border-b border-border pb-2">
        <span className="text-sm text-muted-foreground">Whisper: Transcription</span>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.5fr]">
        {/* Left — controls */}
        <div className="space-y-6">
          {/* Language select */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Language</label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
            >
              <option value="en">English</option>
              <option value="es">Spanish</option>
              <option value="fr">French</option>
              <option value="de">German</option>
              <option value="pt">Portuguese</option>
              <option value="zu">Zulu</option>
              <option value="af">Afrikaans</option>
            </select>
          </div>

          <div>
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <label className="block text-sm font-medium text-foreground">Microphone</label>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={() => refreshAudioInputs(true)}
                disabled={isRecording || isProcessing}
                title="Refresh microphones"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
            <Select
              value={selectedMicId}
              onValueChange={handleMicChange}
              disabled={isRecording || isProcessing}
            >
              <SelectTrigger className="w-full rounded-lg border-border bg-card text-sm text-foreground">
                <SelectValue placeholder="System default microphone" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DEFAULT_MIC_ID}>{defaultMicOptionLabel}</SelectItem>
                {selectableAudioInputs.map((device, index) => (
                  <SelectItem key={`${device.deviceId}-${index}`} value={device.deviceId}>
                    {device.label || `Microphone ${index + 1}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="mt-1.5 text-xs text-muted-foreground">
              Active: {activeMicLabel || selectedMicLabel}
            </p>
            {micListError ? (
              <p className="mt-1 text-xs text-red-400">{micListError}</p>
            ) : null}
          </div>

          {/* Mic button */}
          <div className="flex flex-col items-center gap-4">
            <button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isProcessing}
              className={cn(
                "relative flex h-28 w-28 items-center justify-center rounded-full border-4 transition-all",
                isRecording
                  ? "border-red-500 bg-red-500/10 shadow-[0_0_30px_rgba(239,68,68,0.3)]"
                  : "border-cyan-400 bg-cyan-400/5 hover:bg-cyan-400/10 shadow-[0_0_30px_rgba(34,211,238,0.15)]",
                isProcessing && "opacity-50 cursor-not-allowed"
              )}
            >
              {isProcessing ? (
                <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
              ) : isRecording ? (
                <MicOff className="h-8 w-8 text-red-400" />
              ) : (
                <Mic className="h-8 w-8 text-cyan-400" />
              )}
            </button>
            <span className="text-sm text-muted-foreground">
              {isProcessing
                ? `Transcribing… ${processingSeconds}s (takes ~20s on this server — don't navigate away)`
                : isRecording
                  ? "Recording — click to stop"
                  : "Speak"}
            </span>
          </div>

          {/* Divider */}
          <div className="flex items-center gap-3">
            <div className="h-px flex-1 bg-border" />
            <span className="text-xs text-muted-foreground">OR</span>
            <div className="h-px flex-1 bg-border" />
          </div>

          {/* File upload */}
          <input ref={fileInputRef} type="file" accept="audio/*" onChange={handleFileUpload} className="hidden" />
          <Button
            variant="outline"
            className="w-full"
            onClick={() => fileInputRef.current?.click()}
            disabled={isProcessing}
          >
            <Upload className="mr-2 h-4 w-4" />
            Use Your Own File
          </Button>
        </div>

        {/* Right — results */}
        <Card className="border-border bg-card/50">
          <CardContent className="p-5">
            {error ? (
              <div className="flex flex-col items-center gap-2 py-20 text-center">
                <AlertCircle className="h-8 w-8 text-red-400" />
                <p className="max-w-xs text-sm text-red-400">{error}</p>
              </div>
            ) : result ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Badge variant="outline" className="text-xs">
                    Confidence: {(result.confidence * 100).toFixed(1)}%
                  </Badge>
                </div>
                <ScrollArea className="h-60">
                  <p className="whitespace-pre-wrap text-sm text-foreground leading-relaxed">
                    {result.transcript}
                  </p>
                </ScrollArea>
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="ghost" onClick={copyTranscript}>
                    <Copy className="mr-1 h-3.5 w-3.5" /> Copy
                  </Button>
                  <Button size="sm" variant="ghost" onClick={downloadTranscript}>
                    <Download className="mr-1 h-3.5 w-3.5" /> Download
                  </Button>
                </div>
              </div>
            ) : (
              <p className="py-24 text-center text-sm text-muted-foreground">
                Your transcriptions will show here.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// Text-to-Speech Tab
// ═══════════════════════════════════════════════════════════════════════
function TextToSpeechPanel() {
  const [text, setText] = useState("")
  const [voices, setVoices] = useState<VoiceProfile[]>([])
  const [voiceId, setVoiceId] = useState<string>("")
  const [isGenerating, setIsGenerating] = useState(false)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement>(null)

  useEffect(() => {
    listVoices()
      .then((all) => {
        const ready = all.filter((v) => v.status === "ready")
        setVoices(ready)
        if (ready.length > 0) setVoiceId(ready[0].id)
      })
      .catch((err) => {
        console.error("Failed to load voices", err)
        setError(err instanceof Error ? `Could not load voices: ${err.message}` : "Could not load voices")
      })
  }, [])

  const handleGenerate = async () => {
    if (!text.trim() || !voiceId) return
    setIsGenerating(true)
    setAudioUrl(null)
    setError(null)
    try {
      const blob = await voiceboxSpeak({ text, voice_profile_id: voiceId, requested_by_service: "call_center_ui" })
      const url = URL.createObjectURL(blob)
      setAudioUrl(url)
    } catch (err: any) {
      console.error(err)
      setError(err?.message ?? "Speech generation failed")
    } finally {
      setIsGenerating(false)
    }
  }

  const downloadAudio = () => {
    if (!audioUrl) return
    const a = document.createElement("a")
    a.href = audioUrl
    a.download = "speech.mp3"
    a.click()
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-6 border-b border-border pb-2">
        <span className="text-sm text-muted-foreground">Voicebox: Voice Synthesis</span>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Input */}
        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Voice</label>
            {voices.length > 0 ? (
              <select
                value={voiceId}
                onChange={(e) => setVoiceId(e.target.value)}
                title="Voice"
                aria-label="Voice"
                className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
              >
                {voices.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name} {v.voice_type === "cloned" ? "(cloned)" : "(preset)"}
                  </option>
                ))}
              </select>
            ) : (
              <p className="rounded-lg border border-dashed border-border bg-card/50 px-3 py-2 text-xs text-muted-foreground">
                No voices yet — clone or add one in the Voice Studio tab below.
              </p>
            )}
          </div>

          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={8}
            placeholder="Type or paste the text you want to convert to speech…"
            className="w-full rounded-lg border border-border bg-card p-3 text-sm text-foreground placeholder-muted-foreground resize-none focus:outline-none focus:ring-1 focus:ring-cyan-500"
          />

          <Button onClick={handleGenerate} disabled={isGenerating || !text.trim() || !voiceId} className="w-full">
            {isGenerating ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Volume2 className="mr-2 h-4 w-4" />
            )}
            {isGenerating ? "Generating…" : "Generate Speech"}
          </Button>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>

        {/* Output */}
        <Card className="border-border bg-card/50">
          <CardContent className="flex flex-col items-center justify-center p-8">
            {audioUrl ? (
              <div className="w-full space-y-4">
                <div className="flex items-center justify-center">
                  <div className="flex h-20 w-20 items-center justify-center rounded-full bg-cyan-500/10 border-2 border-cyan-400">
                    <Volume2 className="h-8 w-8 text-cyan-400" />
                  </div>
                </div>
                <audio ref={audioRef} controls src={audioUrl} className="w-full" />
                <Button size="sm" variant="outline" className="w-full" onClick={downloadAudio}>
                  <Download className="mr-2 h-4 w-4" /> Download
                </Button>
              </div>
            ) : (
              <div className="py-12 text-center">
                <Volume2 className="mx-auto mb-3 h-12 w-12 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">
                  Generated audio will play here.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// Voice Agent Tab
// ═══════════════════════════════════════════════════════════════════════

interface DeploymentRecord {
  id: string
  agent_name: string
  mode: "inbound" | "outbound"
  phone_number: string
  stt_model: string
  tts_voice: string
  llm_provider: string
  status: "active" | "stopped"
  deployed_at: string
}

function VoiceAgentPanel() {
  // ── Config form state ──────────────────────────────────────────────────
  const [agentName, setAgentName] = useState("Customer Support Agent")
  const [systemPrompt, setSystemPrompt] = useState(
    "You are a helpful customer support agent for a telecommunications company. Be friendly, professional, and help customers resolve their issues."
  )
  const [sttModel, setSttModel] = useState("whisper-large-v3")
  const [ttsVoice, setTtsVoice] = useState("voicebox-nova")
  const [llmProvider, setLlmProvider] = useState("anthropic")

  // ── Deploy modal state ─────────────────────────────────────────────────
  const [modalOpen, setModalOpen] = useState(false)
  const [deployMode, setDeployMode] = useState<"inbound" | "outbound">("inbound")
  const [phoneNumber, setPhoneNumber] = useState("")
  const [deploying, setDeploying] = useState(false)
  const [deployError, setDeployError] = useState<string | null>(null)

  // ── Active deployments ─────────────────────────────────────────────────
  const [deployments, setDeployments] = useState<DeploymentRecord[]>([])
  const [loadingDeps, setLoadingDeps] = useState(true)
  const [undeploying, setUndeploying] = useState<string | null>(null)

  const activeDeployments = deployments.filter((d) => d.status === "active")

  // Load existing deployments on mount
  useEffect(() => {
    listVoiceAgentDeployments()
      .then((data) => setDeployments(Array.isArray(data) ? data : []))
      .catch(() => {/* backend may be unavailable */})
      .finally(() => setLoadingDeps(false))
  }, [])

  // ── Deploy ─────────────────────────────────────────────────────────────
  const handleDeploy = async () => {
    if (!phoneNumber.trim()) return
    setDeploying(true)
    setDeployError(null)
    try {
      const result = await deployVoiceAgent({
        agent_name: agentName,
        system_prompt: systemPrompt,
        stt_model: sttModel,
        tts_voice: ttsVoice,
        llm_provider: llmProvider,
        mode: deployMode,
        phone_number: phoneNumber.trim(),
      })
      setDeployments((prev) => [result, ...prev])
      setModalOpen(false)
      setPhoneNumber("")
    } catch (err) {
      setDeployError(err instanceof Error ? err.message : "Deployment failed")
    } finally {
      setDeploying(false)
    }
  }

  // ── Undeploy ───────────────────────────────────────────────────────────
  const handleUndeploy = async (id: string) => {
    setUndeploying(id)
    try {
      const result = await stopVoiceAgent(id)
      setDeployments((prev) => prev.map((d) => (d.id === id ? { ...d, ...result } : d)))
    } catch {
      /* show nothing — stale state is fine */
    } finally {
      setUndeploying(null)
    }
  }

  return (
    <>
      {/* ── Deploy Modal ─────────────────────────────────────────────── */}
      {modalOpen && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-border bg-card shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-violet-400" />
                <h2 className="text-base font-semibold text-foreground">Deploy Voice Agent</h2>
              </div>
              <button
                onClick={() => { setModalOpen(false); setDeployError(null) }}
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-5 space-y-5">
              {/* Mode toggle */}
              <div>
                <label className="mb-2 block text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Call Direction
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {(["inbound", "outbound"] as const).map((m) => (
                    <button
                      key={m}
                      onClick={() => setDeployMode(m)}
                      className={cn(
                        "flex items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-medium transition-all",
                        deployMode === m
                          ? "border-violet-500/50 bg-violet-500/10 text-violet-300"
                          : "border-border bg-card/50 text-muted-foreground hover:bg-secondary"
                      )}
                    >
                      {m === "inbound"
                        ? <PhoneIncoming className="h-4 w-4" />
                        : <PhoneOutgoing className="h-4 w-4" />}
                      {m.charAt(0).toUpperCase() + m.slice(1)}
                    </button>
                  ))}
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {deployMode === "inbound"
                    ? "Agent monitors the queue and answers incoming calls from this number."
                    : "Agent dials out to the specified number and handles the call."}
                </p>
              </div>

              {/* Phone number */}
              <div>
                <label className="mb-1.5 block text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {deployMode === "inbound" ? "Queue / DID Number" : "Dial-out Number"}
                </label>
                <div className="relative">
                  <PhoneCall className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="tel"
                    value={phoneNumber}
                    onChange={(e) => setPhoneNumber(e.target.value)}
                    placeholder="+27 11 555 0100"
                    className="h-10 w-full rounded-lg border border-border bg-secondary/50 pl-9 pr-3 text-sm text-foreground placeholder-muted-foreground focus:border-violet-500/60 focus:outline-none"
                  />
                </div>
              </div>

              {/* Summary */}
              <div className="rounded-lg border border-border/40 bg-background/40 p-3 text-xs text-muted-foreground space-y-1">
                <p><span className="text-foreground font-medium">Agent:</span> {agentName}</p>
                <p><span className="text-foreground font-medium">STT:</span> {sttModel}</p>
                <p><span className="text-foreground font-medium">TTS:</span> {ttsVoice}</p>
                <p><span className="text-foreground font-medium">LLM:</span> {llmProvider}</p>
              </div>

              {deployError && (
                <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  {deployError}
                </div>
              )}

              {/* Actions */}
              <div className="flex items-center justify-end gap-2 pt-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { setModalOpen(false); setDeployError(null) }}
                  disabled={deploying}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleDeploy}
                  disabled={deploying || !phoneNumber.trim()}
                  className="bg-violet-600 hover:bg-violet-500 text-white"
                >
                  {deploying ? (
                    <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  ) : (
                    <Bot className="mr-1.5 h-4 w-4" />
                  )}
                  {deploying ? "Deploying…" : "Deploy"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-4">
        <div className="flex items-center gap-6 border-b border-border pb-2">
          <span className="text-sm text-muted-foreground">Flux: Voice Agents</span>
        </div>

        {/* Active deployment status cards */}
        {activeDeployments.length > 0 && (
          <div className="space-y-2">
            {activeDeployments.map((dep) => (
              <div
                key={dep.id}
                className="flex items-center justify-between rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-4 py-3"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500/15">
                    {dep.mode === "inbound"
                      ? <PhoneIncoming className="h-4 w-4 text-emerald-400" />
                      : <PhoneOutgoing className="h-4 w-4 text-emerald-400" />}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-foreground">{dep.agent_name}</span>
                      <span className="flex items-center gap-1 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        LIVE
                      </span>
                      <Badge
                        variant="outline"
                        className="text-[10px] border-emerald-500/30 text-emerald-400 capitalize"
                      >
                        {dep.mode}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      <Radio className="mr-1 inline h-3 w-3" />
                      {dep.phone_number} · {dep.stt_model} · {dep.tts_voice}
                    </p>
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="border-destructive/40 text-destructive hover:bg-destructive/10"
                  onClick={() => handleUndeploy(dep.id)}
                  disabled={undeploying === dep.id}
                >
                  {undeploying === dep.id
                    ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    : <PhoneOff className="mr-1.5 h-3.5 w-3.5" />}
                  Undeploy
                </Button>
              </div>
            ))}
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Configuration */}
          <div className="space-y-4">
            <Card className="border-border bg-card/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium">Agent Configuration</CardTitle>
                <CardDescription>Configure your AI voice agent for call center automation</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Agent Name</label>
                  <input
                    type="text"
                    value={agentName}
                    onChange={(e) => setAgentName(e.target.value)}
                    placeholder="Customer Support Agent"
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-violet-500/60 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">System Prompt</label>
                  <textarea
                    rows={4}
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                    className="w-full rounded-lg border border-border bg-card p-3 text-sm text-foreground placeholder-muted-foreground resize-none focus:border-violet-500/60 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">STT Model</label>
                  <select
                    value={sttModel}
                    onChange={(e) => setSttModel(e.target.value)}
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
                  >
                    <option value="whisper-large-v3">Whisper Large v3 (Recommended)</option>
                    <option value="whisper-medium">Whisper Medium</option>
                    <option value="whisper-base">Whisper Base (Fastest)</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">TTS Voice</label>
                  <select
                    value={ttsVoice}
                    onChange={(e) => setTtsVoice(e.target.value)}
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
                  >
                    <option value="voicebox-nova">Nova (Female, Neutral)</option>
                    <option value="voicebox-orion">Orion (Male, Neutral)</option>
                    <option value="voicebox-luna">Luna (Female, Warm)</option>
                    <option value="voicebox-atlas">Atlas (Male, Deep)</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">LLM Provider</label>
                  <select
                    value={llmProvider}
                    onChange={(e) => setLlmProvider(e.target.value)}
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
                  >
                    <option value="anthropic">Anthropic Claude</option>
                    <option value="openai">OpenAI GPT-4o</option>
                    <option value="groq">Groq Llama</option>
                  </select>
                </div>
              </CardContent>
            </Card>

            <Button
              className="w-full bg-violet-600 hover:bg-violet-500 text-white"
              onClick={() => { setDeployError(null); setModalOpen(true) }}
            >
              <Bot className="mr-2 h-4 w-4" />
              {activeDeployments.length > 0 ? "Deploy Another Agent" : "Deploy Agent"}
            </Button>
          </div>

          {/* Capabilities */}
          <Card className="border-border bg-card/50">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Voice Agent Capabilities</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {[
                { icon: Mic, title: "Real-time STT", desc: "Whisper Large v3 streaming transcription via WebSocket — 3s latency" },
                { icon: Volume2, title: "Natural TTS", desc: "Voicebox voices optimized for conversational phone speech" },
                { icon: Brain, title: "LLM Reasoning", desc: "Plug in any LLM for agent reasoning and response generation" },
                { icon: MessageSquare, title: "Turn-taking", desc: "Intelligent barge-in and end-of-turn detection via VAD" },
                { icon: Target, title: "Intent Routing", desc: "Auto-detect caller intent and route to the right department" },
                { icon: Sparkles, title: "Live Sentiment", desc: "Real-time sentiment monitoring from Whisper transcripts" },
              ].map((item) => (
                <div key={item.title} className="flex items-start gap-3 rounded-lg border border-border/50 bg-background/50 p-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-violet-500/10">
                    <item.icon className="h-4 w-4 text-violet-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-foreground">{item.title}</p>
                    <p className="text-xs text-muted-foreground">{item.desc}</p>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// Audio Intelligence Tab
// ═══════════════════════════════════════════════════════════════════════
function AudioIntelligencePanel() {
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [result, setResult] = useState<AudioIntelResult | null>(null)
  const [activeInsight, setActiveInsight] = useState<"summary" | "sentiment" | "intents" | "topics">("summary")
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const analyzeFile = async (file: Blob) => {
    setIsAnalyzing(true)
    setResult(null)
    try {
      const form = new FormData()
      form.append("file", file, "call.webm")
      form.append("language", "en")
      form.append("summarize", "true")
      form.append("sentiment", "true")
      form.append("intents", "true")
      form.append("topics", "true")

      const res = await fetch(`${API_BASE}/ai/audio-intelligence`, {
        method: "POST",
        headers: await getAuthHeaders(),
        body: form,
      })
      if (!res.ok) throw new Error(await res.text())
      setResult(await res.json())
    } catch (err) {
      console.error(err)
    } finally {
      setIsAnalyzing(false)
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const url = URL.createObjectURL(file)
    setAudioUrl(url)
    await analyzeFile(file)
  }

  const insightTabs = [
    { key: "summary" as const, label: "Summarization", icon: MessageSquare },
    { key: "sentiment" as const, label: "Sentiment Analysis", icon: TrendingUp },
    { key: "intents" as const, label: "Intent Detection", icon: Target },
    { key: "topics" as const, label: "Topic Detection", icon: Hash },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-6 border-b border-border pb-2">
        <span className="text-sm text-muted-foreground">Audio Intelligence</span>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.5fr]">
        {/* Left — upload + audio player + insight buttons */}
        <div className="space-y-4">
          {/* Audio info */}
          {audioUrl && (
            <Card className="border-border bg-card/50">
              <CardContent className="p-4">
                <p className="mb-2 text-xs font-medium text-muted-foreground">Call Center: Customer Support:</p>
                <audio controls src={audioUrl} className="w-full" />
              </CardContent>
            </Card>
          )}

          {/* Insight buttons */}
          <div className="space-y-2">
            {insightTabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveInsight(tab.key)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-lg border px-4 py-3 text-sm font-medium transition-all",
                  activeInsight === tab.key
                    ? "border-cyan-500/50 bg-cyan-500/5 text-cyan-400"
                    : "border-border bg-card text-foreground hover:bg-accent"
                )}
              >
                <tab.icon className="h-4 w-4" />
                {tab.label}
                <ChevronRight className="ml-auto h-4 w-4 opacity-50" />
              </button>
            ))}
          </div>

          {/* Upload */}
          <input ref={fileInputRef} type="file" accept="audio/*" onChange={handleFileUpload} className="hidden" />
          <Button
            variant="outline"
            className="w-full"
            onClick={() => fileInputRef.current?.click()}
            disabled={isAnalyzing}
          >
            {isAnalyzing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
            {isAnalyzing ? "Analyzing…" : "Upload Call Recording"}
          </Button>
        </div>

        {/* Right — results */}
        <Card className="border-border bg-card/50">
          <CardContent className="p-5">
            {isAnalyzing && (
              <div className="flex flex-col items-center justify-center py-20">
                <Loader2 className="mb-3 h-8 w-8 animate-spin text-cyan-400" />
                <p className="text-sm text-muted-foreground">Running audio intelligence analysis…</p>
              </div>
            )}

            {!isAnalyzing && !result && (
              <div className="flex flex-col items-center justify-center py-20">
                <Brain className="mb-3 h-12 w-12 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">Upload a call recording to analyze</p>
              </div>
            )}

            {!isAnalyzing && result && (
              <div className="space-y-4">
                <h3 className="text-base font-semibold text-foreground capitalize">{activeInsight.replace("_", " ")}</h3>

                {/* Summary */}
                {activeInsight === "summary" && (
                  <div className="space-y-3">
                    <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-4">
                      <p className="mb-1 text-xs font-semibold text-cyan-400">Summary:</p>
                      <p className="text-sm text-foreground leading-relaxed">
                        {result.summary || "No summary available."}
                      </p>
                    </div>
                    <div>
                      <p className="mb-1 text-xs font-semibold text-muted-foreground">Transcript</p>
                      <ScrollArea className="h-40">
                        <p className="text-sm text-muted-foreground leading-relaxed">
                          {result.transcript}
                        </p>
                      </ScrollArea>
                    </div>
                  </div>
                )}

                {/* Sentiment */}
                {activeInsight === "sentiment" && (
                  <div className="space-y-3">
                    {result.sentiments.average?.sentiment && (
                      <div className="flex items-center gap-3 rounded-lg border border-border bg-background/50 p-4">
                        <div className="text-sm font-medium text-muted-foreground">Overall:</div>
                        <Badge
                          className={cn(
                            "capitalize",
                            result.sentiments.average.sentiment === "positive" && "bg-emerald-500/20 text-emerald-400",
                            result.sentiments.average.sentiment === "negative" && "bg-red-500/20 text-red-400",
                            result.sentiments.average.sentiment === "neutral" && "bg-neutral-500/20 text-neutral-400"
                          )}
                        >
                          {result.sentiments.average.sentiment}
                        </Badge>
                        <span className="text-sm text-muted-foreground">
                          Score: {result.sentiments.average.sentiment_score?.toFixed(2)}
                        </span>
                      </div>
                    )}
                    <ScrollArea className="h-56">
                      <div className="space-y-2">
                        {result.sentiments.segments.map((seg, i) => {
                          const Icon = getSentimentIcon(seg.sentiment)
                          return (
                            <div key={i} className="flex items-start gap-2 rounded border border-border/50 bg-background/30 p-3">
                              <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", getSentimentColor(seg.sentiment))} />
                              <div>
                                <p className="text-xs text-foreground">{seg.text}</p>
                                <p className={cn("text-[10px] capitalize", getSentimentColor(seg.sentiment))}>
                                  {seg.sentiment} ({seg.sentiment_score?.toFixed(2)})
                                </p>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </ScrollArea>
                  </div>
                )}

                {/* Intents */}
                {activeInsight === "intents" && (
                  <ScrollArea className="h-72">
                    <div className="space-y-2">
                      {result.intents.segments.length === 0 && (
                        <p className="text-sm text-muted-foreground">No intents detected.</p>
                      )}
                      {result.intents.segments.map((seg, i) => (
                        <div key={i} className="rounded-lg border border-border/50 bg-background/30 p-3">
                          <p className="mb-1.5 text-xs text-muted-foreground">{seg.text}</p>
                          <div className="flex flex-wrap gap-1.5">
                            {seg.intents.map((intent, j) => (
                              <Badge key={j} variant="secondary" className="text-[10px]">
                                <Target className="mr-1 h-3 w-3" />
                                {intent.intent} ({(intent.confidence_score * 100).toFixed(0)}%)
                              </Badge>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                )}

                {/* Topics */}
                {activeInsight === "topics" && (
                  <ScrollArea className="h-72">
                    <div className="space-y-2">
                      {result.topics.segments.length === 0 && (
                        <p className="text-sm text-muted-foreground">No topics detected.</p>
                      )}
                      {result.topics.segments.map((seg, i) => (
                        <div key={i} className="rounded-lg border border-border/50 bg-background/30 p-3">
                          <p className="mb-1.5 text-xs text-muted-foreground">{seg.text}</p>
                          <div className="flex flex-wrap gap-1.5">
                            {seg.topics.map((topic, j) => (
                              <Badge key={j} variant="outline" className="text-[10px]">
                                <Hash className="mr-1 h-3 w-3" />
                                {topic.topic} ({(topic.confidence_score * 100).toFixed(0)}%)
                              </Badge>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// Main Export — Voice AI Tabs
// ═══════════════════════════════════════════════════════════════════════
export function VoiceAIPanel() {
  return (
    <div className="surface-card p-5">
      <Tabs defaultValue="stt">
        <TabsList className="mb-4 grid w-full grid-cols-4 bg-muted/30">
          <TabsTrigger value="stt" className="gap-1.5 text-xs data-[state=active]:text-cyan-400">
            <Mic className="h-3.5 w-3.5" />
            Speech to Text
          </TabsTrigger>
          <TabsTrigger value="tts" className="gap-1.5 text-xs data-[state=active]:text-pink-400">
            <Volume2 className="h-3.5 w-3.5" />
            Text to Speech
          </TabsTrigger>
          <TabsTrigger value="agent" className="gap-1.5 text-xs data-[state=active]:text-violet-400">
            <Bot className="h-3.5 w-3.5" />
            Voice Agent
          </TabsTrigger>
          <TabsTrigger value="intel" className="gap-1.5 text-xs data-[state=active]:text-amber-400">
            <Brain className="h-3.5 w-3.5" />
            Audio Intelligence
          </TabsTrigger>
        </TabsList>

        <TabsContent value="stt"><SpeechToTextPanel /></TabsContent>
        <TabsContent value="tts"><TextToSpeechPanel /></TabsContent>
        <TabsContent value="agent"><VoiceAgentPanel /></TabsContent>
        <TabsContent value="intel"><AudioIntelligencePanel /></TabsContent>
      </Tabs>
    </div>
  )
}
