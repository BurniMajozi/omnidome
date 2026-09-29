"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Sparkles,
  Music,
  Laugh,
  Radio,
  PhoneCall,
  Volume2,
  Mic,
  RotateCcw,
  Tag,
  CheckCircle2,
  Sliders,
  Play,
  Settings2,
  Layers,
  ArrowRight,
} from "lucide-react"
import type { SmartIvrNode } from "@/app/api/call-center/ivr/route"

export function SmartIvrStudio() {
  const [ivrNodes, setIvrNodes] = useState<SmartIvrNode[]>([])
  const [stats, setStats] = useState<any>(null)
  const [selectedNode, setSelectedNode] = useState<SmartIvrNode | null>(null)
  const [loading, setLoading] = useState(true)
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Edit State
  const [promptText, setPromptText] = useState("")
  const [voiceEngine, setVoiceEngine] = useState<SmartIvrNode["voice_engine"]>("VOICEBOX_CLONED_SA")
  const [voicePersona, setVoicePersona] = useState("")
  const [campaignEnabled, setCampaignEnabled] = useState(true)
  const [campaignTitle, setCampaignTitle] = useState("")
  const [campaignPitch, setCampaignPitch] = useState("")
  const [humorEnabled, setHumorEnabled] = useState(true)
  const [humorStyle, setHumorStyle] = useState<SmartIvrNode["hold_entertainment"]["humor_style"]>("South African Standup Comedy")
  const [defaultGenre, setDefaultGenre] = useState("Amapiano Grooves")
  const [callbackEnabled, setCallbackEnabled] = useState(true)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 4000)
  }

  const fetchIvr = async () => {
    try {
      setLoading(true)
      const res = await fetch("/api/call-center/ivr")
      if (res.ok) {
        const data = await res.json()
        setIvrNodes(data.ivr_nodes || [])
        setStats(data.stats || null)
        if (data.ivr_nodes && data.ivr_nodes.length > 0) {
          const first = data.ivr_nodes[0]
          setSelectedNode(first)
          setPromptText(first.prompt_text)
          setVoiceEngine(first.voice_engine)
          setVoicePersona(first.voice_persona)
          setCampaignEnabled(first.marketing_campaign_push.enabled)
          setCampaignTitle(first.marketing_campaign_push.campaign_title)
          setCampaignPitch(first.marketing_campaign_push.promo_audio_pitch)
          setHumorEnabled(first.hold_entertainment.humor_mode_enabled)
          setHumorStyle(first.hold_entertainment.humor_style)
          setDefaultGenre(first.hold_entertainment.default_genre)
          setCallbackEnabled(first.call_back_enabled)
        }
      }
    } catch (err) {
      console.error("Failed to load IVR nodes", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchIvr()
  }, [])

  const handleSelectNode = (node: SmartIvrNode) => {
    setSelectedNode(node)
    setPromptText(node.prompt_text)
    setVoiceEngine(node.voice_engine)
    setVoicePersona(node.voice_persona)
    setCampaignEnabled(node.marketing_campaign_push.enabled)
    setCampaignTitle(node.marketing_campaign_push.campaign_title)
    setCampaignPitch(node.marketing_campaign_push.promo_audio_pitch)
    setHumorEnabled(node.hold_entertainment.humor_mode_enabled)
    setHumorStyle(node.hold_entertainment.humor_style)
    setDefaultGenre(node.hold_entertainment.default_genre)
    setCallbackEnabled(node.call_back_enabled)
  }

  const handleSaveIvr = async () => {
    if (!selectedNode) return
    try {
      setSaving(true)
      const res = await fetch("/api/call-center/ivr", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "UPDATE_IVR",
          id: selectedNode.id,
          prompt_text: promptText,
          voice_engine: voiceEngine,
          voice_persona: voicePersona,
          marketing_campaign_push: {
            enabled: campaignEnabled,
            campaign_title: campaignTitle,
            promo_audio_pitch: campaignPitch,
          },
          hold_entertainment: {
            allow_genre_selection: true,
            default_genre: defaultGenre,
            humor_mode_enabled: humorEnabled,
            humor_style: humorStyle,
          },
          call_back_enabled: callbackEnabled,
        }),
      })
      if (res.ok) {
        showToast("Smart IVR Flow & Marketing Push Updated!")
        fetchIvr()
      }
    } catch {
      showToast("Failed to save IVR flow")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Toast */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 rounded-lg bg-pink-600 px-4 py-3 text-white shadow-xl flex items-center gap-2 border border-pink-400">
          <CheckCircle2 className="h-5 w-5" />
          <span className="text-sm font-semibold">{toastMessage}</span>
        </div>
      )}

      {/* Header Banner */}
      <div className="rounded-xl border border-pink-500/40 bg-gradient-to-r from-pink-950/40 via-background to-purple-950/30 p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <span className="flex h-3 w-3 rounded-full bg-pink-400 shadow-sm" />
              <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
                Smart IVR Studio: Marketing Push &amp; Interactive Queue Entertainment
              </h2>
              <Badge variant="outline" className="border-pink-500/40 text-pink-400 bg-pink-500/10 text-xs">
                Cloned Voice &amp; Humor Mode
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Turn waiting on hold into a delightful experience. Callers can choose hold music genres (Amapiano, Jazz, Lo-Fi) or laugh with South African standup comedy, while AI injects targeted upgrade campaign promos and guaranteed callbacks.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              onClick={handleSaveIvr}
              disabled={saving}
              className="gap-1.5 text-xs bg-pink-600 hover:bg-pink-500 text-white font-medium"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              {saving ? "Deploying IVR…" : "Deploy to Asterisk Core"}
            </Button>
          </div>
        </div>

        {/* Stats Row */}
        <div className="mt-4 pt-4 border-t border-border/60 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div>
            <span className="text-muted-foreground block text-[11px]">Marketing Campaign Opt-Ins</span>
            <strong className="text-lg font-bold text-foreground">
              {stats?.marketing_campaign_optins_today || 48} upgrades
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Hold Music Engagement</span>
            <strong className="text-lg font-bold text-pink-400">
              {stats?.hold_music_selections?.amapiano || "46%"} Amapiano
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Callbacks Fulfilled</span>
            <strong className="text-lg font-bold text-cyan-400">
              {stats?.callback_requests_fulfilled || 34} saved
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block text-[11px]">Abandonment Prevented</span>
            <strong className="text-lg font-bold text-emerald-400">
              +{stats?.abandonment_prevented_pct || 14.8}% SLA
            </strong>
          </div>
        </div>
      </div>

      {/* Grid: IVR Flow Selector & Live Editor */}
      <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        {/* Left: Flow list */}
        <Card className="border-border bg-card/80">
          <CardHeader className="pb-3 border-b border-border/50">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Layers className="h-4 w-4 text-pink-400" />
              Active IVR Menus
            </CardTitle>
            <CardDescription className="text-xs">Select auto-attendant flow to configure</CardDescription>
          </CardHeader>
          <CardContent className="pt-4 space-y-2">
            {ivrNodes.map((node) => {
              const isSelected = selectedNode?.id === node.id
              return (
                <button
                  key={node.id}
                  onClick={() => handleSelectNode(node)}
                  className={`w-full text-left p-3 rounded-lg border text-xs transition-all ${
                    isSelected
                      ? "border-pink-500/50 bg-pink-500/10 shadow-sm"
                      : "border-border/70 bg-background/50 hover:bg-muted/40"
                  }`}
                >
                  <div className="font-semibold text-foreground">{node.name}</div>
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground mt-1">
                    <span>{node.dtmf_options.length} options</span>
                    <span>•</span>
                    <span className="text-pink-400 font-mono">{node.voice_engine}</span>
                  </div>
                </button>
              )
            })}
          </CardContent>
        </Card>

        {/* Right: Smart Feature Controls */}
        <div className="space-y-6">
          {/* Section 1: Cloned Voice & Prompt */}
          <Card className="border-border bg-card/80">
            <CardHeader className="pb-3 border-b border-border/50">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Volume2 className="h-4 w-4 text-pink-400" />
                Speech Synthesis Engine &amp; Prompt Voice
              </CardTitle>
              <CardDescription className="text-xs">
                Render auto-attendant prompts with Voicebox cloned South African brand voices or Deepgram Aura.
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-4 space-y-4 text-xs">
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Voice Engine</label>
                  <select
                    value={voiceEngine}
                    onChange={(e) => setVoiceEngine(e.target.value as any)}
                    className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value="VOICEBOX_CLONED_SA">Voicebox Cloned SA Accent (Local Offline)</option>
                    <option value="DEEPGRAM_AURA">Deepgram Aura (Cloud Low Latency)</option>
                    <option value="LOCAL_ASTERISK_WAV">Asterisk Standard WAV Prompts</option>
                  </select>
                </div>

                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Voice Persona / Accent</label>
                  <Input
                    value={voicePersona}
                    onChange={(e) => setVoicePersona(e.target.value)}
                    placeholder="e.g. Thandi (Warm SA Vernacular)"
                  />
                </div>
              </div>

              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Welcome Greeting Audio Script</label>
                <textarea
                  rows={3}
                  value={promptText}
                  onChange={(e) => setPromptText(e.target.value)}
                  className="w-full rounded-md border border-border bg-background p-2.5 text-xs text-foreground font-sans focus:outline-none focus:ring-1 focus:ring-pink-500"
                />
              </div>
            </CardContent>
          </Card>

          {/* Section 2: Marketing Campaign Push */}
          <Card className="border-border bg-card/80">
            <CardHeader className="pb-3 border-b border-border/50">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <Tag className="h-4 w-4 text-cyan-400" />
                    In-Queue Marketing Campaign Push
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Deliver high-conversion upgrade promos to waiting callers based on CRM profile.
                  </CardDescription>
                </div>
                <label className="flex items-center gap-2 cursor-pointer text-xs">
                  <span className="text-muted-foreground">Campaign Active</span>
                  <input
                    type="checkbox"
                    checked={campaignEnabled}
                    onChange={(e) => setCampaignEnabled(e.target.checked)}
                    className="h-4 w-4 rounded border-border text-pink-600 focus:ring-pink-500"
                  />
                </label>
              </div>
            </CardHeader>
            <CardContent className="pt-4 space-y-3 text-xs">
              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Campaign Title</label>
                <Input
                  value={campaignTitle}
                  onChange={(e) => setCampaignTitle(e.target.value)}
                  placeholder="e.g. Spring Township & Metro 500Mbps Fiber Burst"
                  disabled={!campaignEnabled}
                />
              </div>

              <div>
                <label className="text-muted-foreground block mb-1 font-medium">Promotional Voice Pitch (Spoken while on hold)</label>
                <textarea
                  rows={2}
                  value={campaignPitch}
                  onChange={(e) => setCampaignPitch(e.target.value)}
                  disabled={!campaignEnabled}
                  className="w-full rounded-md border border-border bg-background p-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-pink-500"
                />
              </div>
            </CardContent>
          </Card>

          {/* Section 3: Interactive Hold Music & Humor Mode */}
          <Card className="border-border bg-card/80">
            <CardHeader className="pb-3 border-b border-border/50">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <Music className="h-4 w-4 text-purple-400" />
                    Interactive Hold Entertainment &amp; Humor Mode
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Give callers control over what they listen to: South African Amapiano, Jazz, or Comedy snippets!
                  </CardDescription>
                </div>
                <label className="flex items-center gap-2 cursor-pointer text-xs">
                  <span className="text-muted-foreground">Enable Humor / Comedy</span>
                  <input
                    type="checkbox"
                    checked={humorEnabled}
                    onChange={(e) => setHumorEnabled(e.target.checked)}
                    className="h-4 w-4 rounded border-border text-pink-600 focus:ring-pink-500"
                  />
                </label>
              </div>
            </CardHeader>
            <CardContent className="pt-4 space-y-4 text-xs">
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Default Music On Hold (MOH) Genre</label>
                  <select
                    value={defaultGenre}
                    onChange={(e) => setDefaultGenre(e.target.value)}
                    className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value="Amapiano Grooves">Amapiano Grooves (High Energy JHB)</option>
                    <option value="Smooth Cape Jazz">Smooth Cape Jazz (Mellow &amp; Relaxing)</option>
                    <option value="Lo-Fi Beats">Lo-Fi Beats (Modern Chillout)</option>
                    <option value="Deep House JHB">Deep House JHB (Soulful Vocal)</option>
                    <option value="Classical">Classical Symphony (Corporate Standard)</option>
                  </select>
                </div>

                <div>
                  <label className="text-muted-foreground block mb-1 font-medium">Humor &amp; Comedy Style</label>
                  <select
                    value={humorStyle}
                    onChange={(e) => setHumorStyle(e.target.value as any)}
                    disabled={!humorEnabled}
                    className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value="South African Standup Comedy">South African Standup Comedy (Clean &amp; Hilarious)</option>
                    <option value="Tech Support Bloopers & Jokes">Tech Support Bloopers &amp; IT Jokes</option>
                    <option value="Geek Trivia">Telecom &amp; Geek Trivia</option>
                  </select>
                </div>
              </div>

              {/* Callback Option */}
              <div className="rounded-lg border border-border bg-background/50 p-3.5 flex items-center justify-between">
                <div>
                  <h4 className="font-semibold text-foreground flex items-center gap-2">
                    <RotateCcw className="h-4 w-4 text-emerald-400" />
                    Automated Queue Callback Service
                  </h4>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    Callers can press 9 to hang up without losing their queue position. Asterisk calls them back once an agent answers.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={callbackEnabled}
                  onChange={(e) => setCallbackEnabled(e.target.checked)}
                  className="h-4 w-4 rounded border-border text-emerald-600 focus:ring-emerald-500"
                />
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
