"use client"

import React, { useState } from "react"
import {
  Mail, Key, CheckCircle2, AlertCircle, ShieldCheck, Zap, Copy,
  ExternalLink, RefreshCw, Send, Sparkles, Inbox, Server, Code,
  ArrowRight, ShieldAlert, Check, LayoutGrid, Sliders
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { AgentMailView } from "../communication/mail/agentmail-view"
import { agentMailSignUpResult, agentMailVerifyResult, agentMailConfigureResult, type AgentMailStatus } from "@/lib/marketing-api"
import { useMarketingLoad } from "@/lib/use-marketing-load"
import { useEmailBatch } from "@/lib/use-email-batch"
import { describeMutationError } from "@/lib/marketing-state"
import { NotConnected } from "@/components/ui/not-connected"

type Notice = { kind: "ok" | "error"; text: string } | null

export function AgentMailTab() {
  // Real provider state only. While it loads, or when the service is down, we
  // show that, never a pretend-configured inbox.
  const { value: statusLoad, reload: reloadStatus } = useMarketingLoad<AgentMailStatus>("/email/agentmail/status")
  const [statusOverride, setStatusOverride] = useState<Partial<AgentMailStatus>>({})
  const baseStatus: AgentMailStatus =
    statusLoad.state === "ready"
      ? statusLoad.data
      : { configured: false, inbox_id: "", is_verified: false, base_url: "", provider: "" }
  const status: AgentMailStatus = { ...baseStatus, ...statusOverride }
  const [copiedMcp, setCopiedMcp] = useState(false)

  // Sign up form
  const [humanEmail, setHumanEmail] = useState("")
  const [username, setUsername] = useState("")
  const [signingUp, setSigningUp] = useState(false)
  const [signUpNotice, setSignUpNotice] = useState<Notice>(null)

  // OTP verification form
  const [otpCode, setOtpCode] = useState("")
  const [verifying, setVerifying] = useState(false)
  const [verifyNotice, setVerifyNotice] = useState<Notice>(null)

  // Manual API Key config
  const [manualKey, setManualKey] = useState("")
  const [manualInbox, setManualInbox] = useState("")
  const [savingConfig, setSavingConfig] = useState(false)
  const [configNotice, setConfigNotice] = useState<Notice>(null)

  // Test email sender
  const [testRecipient, setTestRecipient] = useState("")
  const { view: testView, send: sendTestBatch } = useEmailBatch()
  const [surfaceMode, setSurfaceMode] = useState<"workspace" | "config">("workspace")

  const handleSignUp = async () => {
    if (!humanEmail || !username) return
    setSigningUp(true)
    setSignUpNotice(null)
    setVerifyNotice(null)
    const res = await agentMailSignUpResult({
      human_email: humanEmail,
      username: username.toLowerCase().replace(/[^a-z0-9_-]/g, ""),
    })
    setSigningUp(false)
    if (!res.ok || !res.data) {
      setSignUpNotice({ kind: "error", text: describeMutationError(res.status, res.error) })
      return
    }
    // The API key in the response is never rendered; only the real message.
    setSignUpNotice({ kind: "ok", text: res.data.message || "Sign-up accepted by the provider." })
    setStatusOverride((prev) => ({ ...prev, configured: true, inbox_id: res.data!.inbox_id, is_verified: false }))
    reloadStatus()
  }

  const handleVerify = async () => {
    if (!otpCode || otpCode.length < 4) return
    setVerifying(true)
    setVerifyNotice(null)
    const res = await agentMailVerifyResult({ otp_code: otpCode })
    setVerifying(false)
    if (!res.ok || !res.data) {
      setVerifyNotice({ kind: "error", text: describeMutationError(res.status, res.error) })
      return
    }
    if (res.data.is_verified) {
      setVerifyNotice({ kind: "ok", text: res.data.message || "The provider confirmed the code." })
      setStatusOverride((prev) => ({ ...prev, is_verified: true }))
      reloadStatus()
    } else {
      setVerifyNotice({ kind: "error", text: res.data.message || "The provider did not verify this code." })
    }
  }

  const handleSaveManualConfig = async () => {
    setSavingConfig(true)
    setConfigNotice(null)
    const res = await agentMailConfigureResult({
      api_key: manualKey || undefined,
      inbox_id: manualInbox || undefined,
    })
    setSavingConfig(false)
    if (!res.ok || !res.data) {
      setConfigNotice({ kind: "error", text: describeMutationError(res.status, res.error) })
      return
    }
    setConfigNotice({ kind: "ok", text: `Saved (configured: ${res.data.configured ? "yes" : "no"}).` })
    setManualKey("")
    setStatusOverride({})
    reloadStatus()
  }

  const handleSendTest = async () => {
    if (!testRecipient || !status.inbox_id) return
    await sendTestBatch({
      subject: `[AgentMail] Health check from ${status.inbox_id}`,
      body_html: `<h2>AgentMail health check</h2><p>Test message from the inbox <b>${status.inbox_id}</b>.</p>`,
      recipients: [testRecipient],
      from_name: "OmniDome Agent",
      from_email: status.inbox_id,
    })
  }

  const copyMcpConfig = () => {
    const json = JSON.stringify(
      {
        mcpServers: {
          AgentMail: {
            url: "https://mcp.agentmail.to/mcp",
            headers: {
              "x-api-key": "${AGENTMAIL_API_KEY}",
            },
          },
        },
      },
      null,
      2
    )
    navigator.clipboard.writeText(json)
    setCopiedMcp(true)
    setTimeout(() => setCopiedMcp(false), 2000)
  }

  return (
    <div className="space-y-4 max-w-6xl mx-auto">
      {/* Surface Mode Toggle */}
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={surfaceMode === "workspace" ? "default" : "outline"}
            onClick={() => setSurfaceMode("workspace")}
            className="h-8 text-xs font-semibold gap-1.5"
          >
            <Inbox className="h-3.5 w-3.5" />
            <span>AgentMail Hub</span>
          </Button>
          <Button
            size="sm"
            variant={surfaceMode === "config" ? "default" : "outline"}
            onClick={() => setSurfaceMode("config")}
            className="h-8 text-xs font-semibold gap-1.5"
          >
            <Key className="h-3.5 w-3.5" />
            <span>API Credentials &amp; MCP Setup</span>
          </Button>
        </div>

        <Badge variant="secondary" className="text-xs bg-primary/10 text-primary border-primary/20">
          {statusLoad.state === "loading" ? "Checking…" : statusLoad.state !== "ready" ? "Status unavailable" : status.is_verified ? "AgentMail verified" : status.configured ? "AgentMail configured" : "AgentMail not configured"}
        </Badge>
      </div>

      {surfaceMode === "workspace" ? (
        <div className="h-[800px] w-full rounded-xl overflow-hidden border border-border shadow-2xl">
          <AgentMailView />
        </div>
      ) : (
        <div className="space-y-6">
          {statusLoad.state !== "ready" && statusLoad.state !== "loading" && (
            <NotConnected loadable={statusLoad} service="The marketing service" onRetry={reloadStatus} />
          )}
          {/* Header */}
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-xl font-bold flex items-center gap-2">
                <Mail className="h-5 w-5 text-blue-600" /> AgentMail Integration
              </h2>
              <p className="text-sm text-muted-foreground">
                Dedicated two-way AI agent email infrastructure with native per-agent inboxes, thread tracking, and MCP integration.
              </p>
            </div>

        <div className="flex items-center gap-2">
          {status.is_verified ? (
            <Badge className="bg-emerald-600 text-white gap-1 px-3 py-1 font-medium">
              <CheckCircle2 className="h-3.5 w-3.5" /> AgentMail Verified & Active
            </Badge>
          ) : status.configured ? (
            <Badge variant="outline" className="border-amber-500 text-amber-500 bg-amber-500/10 gap-1 px-3 py-1">
              <AlertCircle className="h-3.5 w-3.5" /> OTP Verification Pending
            </Badge>
          ) : (
            <Badge variant="secondary" className="gap-1 px-3 py-1">
              Setup Required
            </Badge>
          )}
        </div>
      </div>

      {/* Highlights Banner */}
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="p-4 rounded-xl border bg-card">
          <div className="flex items-center justify-between text-xs text-muted-foreground uppercase font-medium">
            <span>Active Agent Inbox</span>
            <Inbox className="h-4 w-4 text-blue-600" />
          </div>
          <div className="mt-2 text-base font-bold font-mono text-foreground truncate">
            {status.inbox_id || "Not configured"}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">Native sending & reply address</p>
        </div>

        <div className="p-4 rounded-xl border bg-card">
          <div className="flex items-center justify-between text-xs text-muted-foreground uppercase font-medium">
            <span>Provider</span>
            <Sparkles className="h-4 w-4 text-amber-500" />
          </div>
          <div className="mt-2 text-base font-bold text-foreground truncate">
            {status.provider || "Not reported"}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1 truncate">{status.base_url || "No provider URL reported"}</p>
        </div>

        <div className="p-4 rounded-xl border bg-card">
          <div className="flex items-center justify-between text-xs text-muted-foreground uppercase font-medium">
            <span>Sending Permission</span>
            <ShieldCheck className="h-4 w-4 text-emerald-500" />
          </div>
          <div className="mt-2 text-base font-bold text-foreground">
            {status.is_verified ? "Full External Sending" : "Restricted (Verify OTP)"}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">
            {status.is_verified ? "Unlocked for all recipients" : "Restricted to signup email"}
          </p>
        </div>
      </div>

      {/* Main Row: Onboarding vs Configuration */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Onboarding Card */}
        <Card className="border-border bg-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Zap className="h-4 w-4 text-blue-600" /> Programmatic Agent Onboarding
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              Sign up programmatically using the Agent API. No browser console access needed.
            </p>
          </CardHeader>

          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Your Human Email</label>
              <Input
                placeholder="you@yourdomain.co.za (not placeholder domain)"
                value={humanEmail}
                onChange={(e) => setHumanEmail(e.target.value)}
              />
              <p className="text-[11px] text-muted-foreground">
                A 6-digit OTP will be sent here to unlock full permissions.
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Agent Username</label>
              <div className="flex items-center gap-2">
                <Input
                  placeholder="my-agent"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
                <span className="text-xs font-mono text-muted-foreground shrink-0">@agentmail.to</span>
              </div>
            </div>

            <Button
              onClick={handleSignUp}
              disabled={signingUp || !humanEmail || !username}
              className="w-full bg-[#0066cc] hover:bg-[#0052a3] text-white font-medium"
            >
              {signingUp ? <RefreshCw className="h-4 w-4 animate-spin mr-2" /> : <Mail className="h-4 w-4 mr-2" />}
              Sign Up AI Agent
            </Button>
            {signUpNotice && (
              <p role={signUpNotice.kind === "error" ? "alert" : "status"} className={`text-xs font-medium ${signUpNotice.kind === "error" ? "text-red-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                {signUpNotice.text}
              </p>
            )}

            {/* OTP Verification Block */}
            <div className="pt-4 border-t space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Verify 6-Digit OTP Code
                </label>
                {status.is_verified && (
                  <Badge variant="outline" className="border-emerald-500 text-emerald-500 text-[10px]">
                    Verified
                  </Badge>
                )}
              </div>
              <div className="flex gap-2">
                <Input
                  placeholder="e.g. 123456"
                  maxLength={6}
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  className="font-mono text-center tracking-widest text-base font-bold"
                />
                <Button
                  onClick={handleVerify}
                  disabled={verifying || otpCode.length < 4}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white shrink-0"
                >
                  {verifying ? "Verifying..." : "Verify OTP"}
                </Button>
              </div>
              {verifyNotice && (
                <p role={verifyNotice.kind === "error" ? "alert" : "status"} className={`text-xs font-medium ${verifyNotice.kind === "error" ? "text-red-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                  {verifyNotice.text}
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Manual Config & Test Dispatch */}
        <div className="space-y-6">
          <Card className="border-border bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Key className="h-4 w-4 text-amber-500" /> Existing Account Configuration
              </CardTitle>
              <p className="text-xs text-muted-foreground">
                Already generated an API key at <a href="https://console.agentmail.to" target="_blank" rel="noreferrer" className="underline text-blue-600">console.agentmail.to</a>?
              </p>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">AgentMail API Key</label>
                <Input
                  type="password"
                  placeholder="am_live_..."
                  value={manualKey}
                  onChange={(e) => setManualKey(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Inbox Address</label>
                <Input
                  placeholder="my-agent@agentmail.to"
                  value={manualInbox}
                  onChange={(e) => setManualInbox(e.target.value)}
                />
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={handleSaveManualConfig}
                disabled={savingConfig || (!manualKey && !manualInbox)}
                className="w-full text-xs"
              >
                {savingConfig ? "Saving…" : "Save Credentials"}
              </Button>
              {configNotice && (
                <p role={configNotice.kind === "error" ? "alert" : "status"} className={`text-xs font-medium ${configNotice.kind === "error" ? "text-red-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                  {configNotice.text}
                </p>
              )}
            </CardContent>
          </Card>

          {/* Test Send */}
          <Card className="border-border bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Send className="h-4 w-4 text-emerald-600" /> Test AgentMail Dispatch
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Send Test Email To</label>
                <div className="flex gap-2">
                  <Input
                    value={testRecipient}
                    onChange={(e) => setTestRecipient(e.target.value)}
                    placeholder="recipient@example.com"
                  />
                  <Button
                    onClick={handleSendTest}
                    disabled={testView.phase === "sending" || testView.phase === "tracking" || !testRecipient || !status.inbox_id}
                    size="sm"
                    className="bg-[#0066cc] text-white shrink-0"
                  >
                    {testView.phase === "sending" || testView.phase === "tracking" ? <RefreshCw className="h-4 w-4 animate-spin" /> : "Send"}
                  </Button>
                </div>
              </div>
              {testView.message && (
                <p role="status" className={`text-xs font-medium ${testView.info && testView.info.failed ? "text-amber-500" : "text-emerald-600 dark:text-emerald-400"}`}>
                  {testView.message}
                </p>
              )}
              {testView.error && (
                <p role="alert" className="text-xs font-medium text-red-400">{testView.error}</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* MCP Server Integration for Coding Assistants */}
      <Card className="border-border bg-card">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Server className="h-4 w-4 text-purple-600" /> AgentMail MCP Server Configuration
            </CardTitle>
            <Button variant="outline" size="sm" onClick={copyMcpConfig} className="text-xs gap-1.5">
              {copiedMcp ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
              {copiedMcp ? "Copied" : "Copy MCP JSON"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Connect Claude Code, Cursor, Codex, or Antigravity to the hosted AgentMail runtime:
          </p>
        </CardHeader>
        <CardContent>
          <pre className="bg-zinc-950 text-zinc-200 rounded-lg p-4 font-mono text-xs overflow-x-auto leading-relaxed">
{`{
  "mcpServers": {
    "AgentMail": {
      "url": "https://mcp.agentmail.to/mcp",
      "headers": {
        "x-api-key": "${status.configured ? "${AGENTMAIL_API_KEY}" : "YOUR_API_KEY"}"
      }
    }
  }
}`}
          </pre>
        </CardContent>
      </Card>
        </div>
      )}
    </div>
  )
}
