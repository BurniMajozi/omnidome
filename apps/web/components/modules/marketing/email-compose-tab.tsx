"use client"

import React, { useState, useEffect, useMemo } from "react"
import { SandboxedEmailPreview } from "./email-html-preview"
import {
  Send, Mail, Sparkles, AlertTriangle, CheckCircle2, Eye,
  FileText, Users, Sliders, Edit3, ArrowRight, RefreshCw
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { type EmailTemplate, type AgentMailStatus } from "@/lib/marketing-api"
import { useMarketingLoad } from "@/lib/use-marketing-load"
import { useEmailBatch } from "@/lib/use-email-batch"
import { NotConnected } from "@/components/ui/not-connected"
import { EmailBuilder } from "./email-builder"

interface EmailComposeTabProps {
  initialTemplate?: EmailTemplate | null
}

export function EmailComposeTab({ initialTemplate }: EmailComposeTabProps) {
  // One fetch per data set, shared with the other email tabs through the marketing read cache.
  const { value: templatesLoad, reload: reloadTemplates } = useMarketingLoad<EmailTemplate[]>("/templates")
  const { value: mailStatusLoad } = useMarketingLoad<AgentMailStatus>("/email/agentmail/status")
  const templates: EmailTemplate[] = templatesLoad.state === "ready" ? templatesLoad.data : []
  const agentInbox = mailStatusLoad.state === "ready" && mailStatusLoad.data.configured ? mailStatusLoad.data.inbox_id : ""
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>(initialTemplate?.id || "")

  // Fields
  const [campaignId] = useState("")
  const [subject, setSubject] = useState(initialTemplate?.subject || "")
  const [bodyHtml, setBodyHtml] = useState(initialTemplate?.body_html || "")
  const [recipientsRaw, setRecipientsRaw] = useState("")
  const [fromName, setFromName] = useState("")
  const [fromEmailEdit, setFromEmailEdit] = useState<string | null>(null)
  const fromEmail = fromEmailEdit ?? agentInbox
  const setFromEmail = (v: string) => setFromEmailEdit(v)

  // State: each send is tracked to completion (202 -> poll batch status)
  const { view: campaignView, send: sendCampaign } = useEmailBatch()
  const { view: testView, send: sendTest } = useEmailBatch()
  const sending = campaignView.phase === "sending" || campaignView.phase === "tracking"
  const testSending = testView.phase === "sending" || testView.phase === "tracking"
  const [testEmail, setTestEmail] = useState("")

  // Builder switch
  const [isBuilderOpen, setIsBuilderOpen] = useState(false)
  const [showPreviewModal, setShowPreviewModal] = useState(false)

  useEffect(() => {
    // Preselect the first real template once, only when nothing was chosen.
    if (!selectedTemplateId && templates.length > 0) {
      const first = templates[0]
      setSelectedTemplateId(first.id)
      setSubject(first.subject)
      setBodyHtml(first.body_html)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templatesLoad.state])

  const recipients = useMemo(
    () =>
      recipientsRaw
        .split(/[\s,;]+/)
        .map((r) => r.trim())
        .filter((r) => r.includes("@")),
    [recipientsRaw],
  )

  const handleSelectTemplate = (id: string) => {
    setSelectedTemplateId(id)
    const t = templates.find((x) => x.id === id)
    if (t) {
      setSubject(t.subject)
      setBodyHtml(t.body_html)
    }
  }

  const handleSendTest = async () => {
    if (!testEmail || !subject) return
    await sendTest({
      subject: `[TEST] ${subject}`,
      body_html: bodyHtml,
      recipients: [testEmail],
      from_name: fromName || undefined,
      from_email: fromEmail || undefined,
    })
  }

  const handleSendCampaign = async () => {
    if (!subject || recipients.length === 0) return
    await sendCampaign({
      campaign_id: campaignId || undefined,
      subject,
      body_html: bodyHtml,
      recipients,
      from_name: fromName || undefined,
      from_email: fromEmail || undefined,
    })
  }

  if (isBuilderOpen) {
    const currentTpl = templates.find((t) => t.id === selectedTemplateId)
    return (
      <div className="space-y-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setIsBuilderOpen(false)}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          ← Back to Campaign Dispatcher
        </Button>
        <EmailBuilder
          initialTemplate={currentTpl}
          onSave={(data) => {
            setSubject(data.subject)
            setBodyHtml(data.body_html)
            setIsBuilderOpen(false)
          }}
          onStartCampaign={(data) => {
            setSubject(data.subject)
            setBodyHtml(data.body_html)
            setIsBuilderOpen(false)
          }}
          onBack={() => setIsBuilderOpen(false)}
        />
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Mail className="h-5 w-5 text-blue-600" /> Send Email Campaign
            </h2>
            <Badge variant="outline" className="text-[11px] font-mono gap-1">
              {agentInbox ? <><CheckCircle2 className="h-3 w-3" /> AgentMail: {agentInbox}</> : mailStatusLoad.state === "loading" ? "AgentMail: checking…" : mailStatusLoad.state === "ready" ? "AgentMail: not configured" : "AgentMail: status unavailable"}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Launch email broadcasts powered by AgentMail inboxes and visual templates.
          </p>
        </div>

        <Button
          size="sm"
          onClick={() => setIsBuilderOpen(true)}
          className="bg-[#0066cc] hover:bg-[#0052a3] text-white gap-2 font-medium"
        >
          <Edit3 className="h-4 w-4" /> Open in Visual Builder
        </Button>
      </div>

      {campaignView.message && (
        <div role="status" className={`flex items-center gap-2 rounded-lg border p-4 text-sm ${campaignView.phase === "done" ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-600" : "border-blue-500/30 bg-blue-500/5 text-blue-500"}`}>
          {campaignView.phase === "done" ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <RefreshCw className="h-4 w-4 shrink-0 animate-spin" />}
          <p>{campaignView.message}</p>
        </div>
      )}
      {campaignView.error && (
        <div role="alert" className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-500">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <p>{campaignView.error}</p>
        </div>
      )}
      {templatesLoad.state !== "ready" && templatesLoad.state !== "loading" && (
        <NotConnected loadable={templatesLoad} service="The marketing service" onRetry={reloadTemplates} />
      )}

      <div className="grid gap-6 md:grid-cols-3">
        {/* Left 2 Cols: Form */}
        <div className="md:col-span-2 space-y-4">
          <Card className="border-border bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold">Message & Template</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Select Visual Template</label>
                <div className="flex gap-2">
                  <select
                    value={selectedTemplateId}
                    onChange={(e) => handleSelectTemplate(e.target.value)}
                    className="flex-1 rounded-md border bg-background px-3 py-2 text-sm"
                  >
                    <option value="">Blank / Custom HTML</option>
                    {templates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                  <Button variant="outline" size="sm" onClick={() => setIsBuilderOpen(true)} className="gap-1.5">
                    <Edit3 className="h-3.5 w-3.5" /> Edit
                  </Button>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Subject Line</label>
                <Input
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="e.g. Own your newsletter — seasonal updates"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">From Name</label>
                  <Input value={fromName} onChange={(e) => setFromName(e.target.value)} placeholder="Sender name" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">From Email</label>
                  <Input value={fromEmail} onChange={(e) => setFromEmail(e.target.value)} placeholder={agentInbox ? "" : "Connect an AgentMail inbox first"} />
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex justify-between items-center">
                  <label className="text-xs font-medium text-muted-foreground">HTML Body</label>
                  <button
                    onClick={() => setShowPreviewModal(true)}
                    className="text-xs text-blue-600 hover:underline flex items-center gap-1 font-medium"
                  >
                    <Eye className="h-3.5 w-3.5" /> Preview render
                  </button>
                </div>
                <Textarea
                  value={bodyHtml}
                  onChange={(e) => setBodyHtml(e.target.value)}
                  rows={6}
                  className="font-mono text-xs leading-relaxed"
                />
              </div>
            </CardContent>
          </Card>

          {/* Recipients Card */}
          <Card className="border-border bg-card">
            <CardHeader className="pb-3">
              <div className="flex justify-between items-center">
                <CardTitle className="text-base font-semibold">Recipients</CardTitle>
                <Badge variant="secondary" className="font-mono text-xs">
                  {recipients.length} valid recipient(s)
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <Textarea
                placeholder="Paste emails separated by commas or newlines..."
                value={recipientsRaw}
                onChange={(e) => setRecipientsRaw(e.target.value)}
                rows={3}
                className="font-mono text-xs"
              />
            </CardContent>
          </Card>
        </div>

        {/* Right Col: Dispatch Actions */}
        <div className="space-y-4">
          <Card className="border-border bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold">Dispatch</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Button
                onClick={handleSendCampaign}
                disabled={sending || recipients.length === 0 || !subject}
                className="w-full bg-[#0066cc] hover:bg-[#0052a3] text-white font-medium gap-2 h-10 shadow-sm"
              >
                {sending ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" /> Sending…
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4" /> Start Campaign ({recipients.length})
                  </>
                )}
              </Button>

              <div className="pt-3 border-t space-y-3">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block">
                  Send Test Email
                </label>
                <Input
                  value={testEmail}
                  onChange={(e) => setTestEmail(e.target.value)}
                  placeholder="test@example.com"
                  className="h-8 text-xs"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSendTest}
                  disabled={testSending || !testEmail || !subject}
                  className="w-full text-xs gap-1.5"
                >
                  {testSending ? "Sending…" : "Send Test"}
                </Button>
                {testView.message && (
                  <p role="status" className="text-xs text-muted-foreground">{testView.message}</p>
                )}
                {testView.error && (
                  <p role="alert" className="text-xs text-red-400">{testView.error}</p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/60 text-xs text-muted-foreground p-4 space-y-2">
            <h4 className="font-semibold text-foreground text-sm flex items-center gap-1.5">
              <Sparkles className="h-4 w-4 text-blue-500" /> Powered by AgentMail
            </h4>
            <p>
              High-throughput two-way AI agent email infrastructure. Sent directly from your verified AgentMail inbox with native thread parsing, allowlists, and event streams.
            </p>
          </Card>
        </div>
      </div>

      {/* Preview Dialog */}
      <Dialog open={showPreviewModal} onOpenChange={setShowPreviewModal}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Email Render Preview</DialogTitle>
            <DialogDescription>Subject: {subject}</DialogDescription>
          </DialogHeader>
          <div className="border rounded-md bg-muted/10 p-4 max-h-[60vh] overflow-y-auto">
            <SandboxedEmailPreview html={bodyHtml} className="w-full h-[50vh] max-w-[600px] mx-auto block bg-white rounded border-0" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPreviewModal(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
