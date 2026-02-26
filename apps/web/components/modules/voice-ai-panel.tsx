"use client"

import { useState, useRef, useCallback, useEffect } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
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
} from "lucide-react"

const API_BASE = "/svc/call-center"

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
  const [result, setResult] = useState<TranscriptResult | null>(null)
  const [language, setLanguage] = useState("en")
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" })
      chunks.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.current.push(e.data)
      }

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunks.current, { type: "audio/webm" })
        await sendAudioForTranscription(blob)
      }

      recorder.start()
      mediaRecorder.current = recorder
      setIsRecording(true)
    } catch (err) {
      console.error("Microphone access denied", err)
    }
  }, [language])

  const stopRecording = useCallback(() => {
    mediaRecorder.current?.stop()
    setIsRecording(false)
  }, [])

  const sendAudioForTranscription = async (blob: Blob) => {
    setIsProcessing(true)
    setResult(null)
    try {
      const form = new FormData()
      form.append("file", blob, "recording.webm")
      form.append("language", language)
      form.append("model", "nova-2")

      const res = await fetch(`${API_BASE}/ai/speech-to-text`, {
        method: "POST",
        headers: { "x-tenant-id": "00000000-0000-0000-0000-000000000001" },
        body: form,
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setResult(data)
    } catch (err) {
      console.error(err)
    } finally {
      setIsProcessing(false)
    }
  }

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
        <span className="text-sm text-muted-foreground">Nova: Transcription</span>
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
              {isProcessing ? "Processing…" : isRecording ? "Recording — click to stop" : "Speak"}
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
            {result ? (
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
  const [voice, setVoice] = useState("aura-2-en")
  const [isGenerating, setIsGenerating] = useState(false)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement>(null)

  const handleGenerate = async () => {
    if (!text.trim()) return
    setIsGenerating(true)
    setAudioUrl(null)
    try {
      const res = await fetch(`${API_BASE}/ai/text-to-speech`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-tenant-id": "00000000-0000-0000-0000-000000000001",
        },
        body: JSON.stringify({ text, model: voice }),
      })
      if (!res.ok) throw new Error(await res.text())
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      setAudioUrl(url)
    } catch (err) {
      console.error(err)
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
        <span className="text-sm text-muted-foreground">Aura: Voice Synthesis</span>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Input */}
        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Voice Model</label>
            <select
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
              className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
            >
              <option value="aura-2-en">Aura 2 — English</option>
              <option value="aura-2-en-female">Aura 2 — English (Female)</option>
              <option value="aura-asteria-en">Asteria — English</option>
              <option value="aura-luna-en">Luna — English</option>
              <option value="aura-stella-en">Stella — English</option>
              <option value="aura-athena-en">Athena — English</option>
              <option value="aura-hera-en">Hera — English</option>
              <option value="aura-orion-en">Orion — English</option>
              <option value="aura-arcas-en">Arcas — English</option>
              <option value="aura-perseus-en">Perseus — English</option>
              <option value="aura-angus-en">Angus — English</option>
              <option value="aura-orpheus-en">Orpheus — English</option>
              <option value="aura-helios-en">Helios — English</option>
              <option value="aura-zeus-en">Zeus — English</option>
            </select>
          </div>

          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={8}
            placeholder="Type or paste the text you want to convert to speech…"
            className="w-full rounded-lg border border-border bg-card p-3 text-sm text-foreground placeholder-muted-foreground resize-none focus:outline-none focus:ring-1 focus:ring-cyan-500"
          />

          <Button onClick={handleGenerate} disabled={isGenerating || !text.trim()} className="w-full">
            {isGenerating ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Volume2 className="mr-2 h-4 w-4" />
            )}
            {isGenerating ? "Generating…" : "Generate Speech"}
          </Button>
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
                  <Download className="mr-2 h-4 w-4" /> Download MP3
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
function VoiceAgentPanel() {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-6 border-b border-border pb-2">
        <span className="text-sm text-muted-foreground">Flux: Voice Agents</span>
      </div>

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
                  placeholder="Customer Support Agent"
                  className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">System Prompt</label>
                <textarea
                  rows={4}
                  placeholder="You are a helpful customer support agent for a telecommunications company. Be friendly, professional, and help customers resolve their issues."
                  className="w-full rounded-lg border border-border bg-card p-3 text-sm text-foreground placeholder-muted-foreground resize-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">STT Model</label>
                <select className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
                  <option value="nova-2">Nova-2 (Recommended)</option>
                  <option value="nova-2-conversationalai">Nova-2 ConversationalAI</option>
                  <option value="nova-2-phonecall">Nova-2 Phone Call</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">TTS Voice</label>
                <select className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
                  <option value="aura-asteria-en">Asteria (Female)</option>
                  <option value="aura-orion-en">Orion (Male)</option>
                  <option value="aura-luna-en">Luna (Female)</option>
                  <option value="aura-arcas-en">Arcas (Male)</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">LLM Provider</label>
                <select className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
                  <option value="openai">OpenAI GPT-4o</option>
                  <option value="anthropic">Anthropic Claude</option>
                  <option value="groq">Groq Llama</option>
                </select>
              </div>
            </CardContent>
          </Card>

          <Button className="w-full" disabled>
            <Bot className="mr-2 h-4 w-4" /> Deploy Agent
            <Badge variant="outline" className="ml-2 text-[10px]">Coming Soon</Badge>
          </Button>
        </div>

        {/* Preview */}
        <Card className="border-border bg-card/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Voice Agent Capabilities</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              { icon: Mic, title: "Real-time STT", desc: "Nova-2 streaming transcription with <300ms latency" },
              { icon: Volume2, title: "Natural TTS", desc: "Aura voices optimized for conversational speech" },
              { icon: Brain, title: "LLM Reasoning", desc: "Plug in any LLM for agent reasoning and responses" },
              { icon: MessageSquare, title: "Turn-taking", desc: "Intelligent barge-in and end-of-turn detection" },
              { icon: Target, title: "Intent Routing", desc: "Auto-detect caller intent and route to right department" },
              { icon: Sparkles, title: "Live Sentiment", desc: "Real-time sentiment monitoring during calls" },
            ].map((item) => (
              <div key={item.title} className="flex items-start gap-3 rounded-lg border border-border/50 bg-background/50 p-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-cyan-500/10">
                  <item.icon className="h-4 w-4 text-cyan-400" />
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
        headers: { "x-tenant-id": "00000000-0000-0000-0000-000000000001" },
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
    <div className="rounded-xl border border-border bg-card p-5">
      <Tabs defaultValue="stt">
        <TabsList className="mb-4 grid w-full grid-cols-4 bg-background">
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
