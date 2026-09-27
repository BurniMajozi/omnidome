"use client"

import React, { useState, useEffect } from "react"
import {
  FileText, Plus, Edit3, Trash2, Copy, Eye, Sparkles, AlertTriangle,
  Layers, ArrowLeft, Download, Check, ExternalLink, Mail
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import {
  listEmailTemplates, createEmailTemplate, updateEmailTemplate, deleteEmailTemplate,
  type EmailTemplate
} from "@/lib/marketing-api"
import { EmailBuilder } from "./email-builder"

const DEFAULT_SEEDED_TEMPLATES: EmailTemplate[] = [
  {
    id: "tpl-1",
    tenant_id: "00000000-0000-0000-0000-000000000001",
    name: "Own your newsletter",
    subject: "Hello world — self-host and manage your newsletter",
    body_html: `<h1>Hello world</h1><p>Self-host and manage your own newsletter system with ease. Manage millions of subscribers on a tiny VPS instance with minimal resources.</p><p>Compose e-mails with the drag-and-drop visual editor, as richtext, raw HTML, plaintext, or markdown.</p>`,
    category: "newsletter",
    created_at: "2026-09-24T10:00:00Z",
  },
  {
    id: "tpl-2",
    tenant_id: "00000000-0000-0000-0000-000000000001",
    name: "Getting Started Quick Guide",
    subject: "Welcome aboard! Here are 3 steps to configure your dome",
    body_html: `<h2>Welcome to OminiDome!</h2><p>Here is everything you need to get your security, monitoring, and communication channels running in less than 5 minutes.</p>`,
    category: "onboarding",
    created_at: "2026-09-23T14:30:00Z",
  },
  {
    id: "tpl-3",
    tenant_id: "00000000-0000-0000-0000-000000000001",
    name: "Commercial Assessment Intro",
    subject: "Request a complimentary security audit for your facility",
    body_html: `<h2>Commercial Guarding & Access Audits</h2><p>Find out where your perimeter security, camera coverage, and gate access protocols can be upgraded.</p>`,
    category: "promotional",
    created_at: "2026-09-22T09:15:00Z",
  },
  {
    id: "tpl-4",
    tenant_id: "00000000-0000-0000-0000-000000000001",
    name: "Re-engagement Promo",
    subject: "We miss you — enjoy 20% off your annual service renewal",
    body_html: `<h2>Special Re-activation Offer</h2><p>It's been a while since we connected. We would love to welcome you back with an exclusive seasonal discount.</p>`,
    category: "retention",
    created_at: "2026-09-21T16:00:00Z",
  },
]

interface EmailTemplatesTabProps {
  initialEditTemplateId?: string | null
  onOpenComposerWithTemplate?: (template: EmailTemplate) => void
}

export function EmailTemplatesTab({
  initialEditTemplateId,
  onOpenComposerWithTemplate,
}: EmailTemplatesTabProps) {
  const [templates, setTemplates] = useState<EmailTemplate[]>(DEFAULT_SEEDED_TEMPLATES)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)

  // Builder mode state
  const [editingTemplate, setEditingTemplate] = useState<EmailTemplate | null>(null)
  const [isBuilderOpen, setIsBuilderOpen] = useState(false)

  // Preview modal
  const [previewingTemplate, setPreviewingTemplate] = useState<EmailTemplate | null>(null)

  const loadTemplates = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listEmailTemplates()
      if (data && data.length > 0) {
        setTemplates(data)
      }
    } catch (e) {
      console.warn("Using local fallback templates", e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTemplates()
  }, [])

  useEffect(() => {
    if (initialEditTemplateId) {
      const found = templates.find((t) => t.id === initialEditTemplateId)
      if (found) {
        setEditingTemplate(found)
        setIsBuilderOpen(true)
      }
    }
  }, [initialEditTemplateId, templates])

  const handleOpenNewBuilder = () => {
    setEditingTemplate(null)
    setIsBuilderOpen(true)
  }

  const handleEditTemplate = (template: EmailTemplate) => {
    setEditingTemplate(template)
    setIsBuilderOpen(true)
  }

  const handleSaveFromBuilder = async (savedData: {
    name: string
    subject: string
    body_html: string
    category?: string
  }) => {
    if (editingTemplate) {
      const updated: EmailTemplate = {
        ...editingTemplate,
        name: savedData.name,
        subject: savedData.subject,
        body_html: savedData.body_html,
        category: savedData.category || editingTemplate.category,
        updated_at: new Date().toISOString(),
      }
      setTemplates(templates.map((t) => (t.id === editingTemplate.id ? updated : t)))
      setEditingTemplate(updated)
      try {
        await updateEmailTemplate(editingTemplate.id, savedData)
      } catch (e) {}
    } else {
      const created: EmailTemplate = {
        id: `tpl-${Date.now()}`,
        tenant_id: "00000000-0000-0000-0000-000000000001",
        name: savedData.name,
        subject: savedData.subject,
        body_html: savedData.body_html,
        category: savedData.category || "newsletter",
        created_at: new Date().toISOString(),
      }
      setTemplates([created, ...templates])
      setEditingTemplate(created)
      try {
        await createEmailTemplate(savedData)
      } catch (e) {}
    }
  }

  const handleDelete = async (id: string) => {
    setTemplates(templates.filter((t) => t.id !== id))
    try {
      await deleteEmailTemplate(id)
    } catch (e) {}
  }

  const handleDuplicate = (template: EmailTemplate) => {
    const copy: EmailTemplate = {
      ...template,
      id: `tpl-${Date.now()}`,
      name: `${template.name} (Copy)`,
      created_at: new Date().toISOString(),
    }
    setTemplates([copy, ...templates])
  }

  const filtered = templates.filter((t) => {
    const matchesSearch =
      t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.subject.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesCat = !categoryFilter || t.category === categoryFilter
    return matchesSearch && matchesCat
  })

  // If in Visual Builder mode, render the listmonk EmailBuilder component
  if (isBuilderOpen) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between pb-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsBuilderOpen(false)}
            className="text-xs text-muted-foreground hover:text-foreground gap-1.5"
          >
            <ArrowLeft className="h-4 w-4" /> Back to Templates Library
          </Button>
          <span className="text-xs text-muted-foreground font-medium">
            Visual Builder Active
          </span>
        </div>

        <EmailBuilder
          initialTemplate={editingTemplate}
          onSave={handleSaveFromBuilder}
          onStartCampaign={(data) => {
            if (onOpenComposerWithTemplate && editingTemplate) {
              onOpenComposerWithTemplate({
                ...editingTemplate,
                ...data,
              })
            }
          }}
          onBack={() => setIsBuilderOpen(false)}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <FileText className="h-5 w-5 text-blue-600" /> Email Templates & Visual Builder
          </h2>
          <p className="text-sm text-muted-foreground">
            Design newsletters and responsive emails with the listmonk drag-and-drop visual builder.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={handleOpenNewBuilder}
            className="bg-[#0066cc] hover:bg-[#0052a3] text-white gap-2 font-medium"
          >
            <Plus className="h-4 w-4" /> Open Visual Builder
          </Button>
        </div>
      </div>

      {/* Filters and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Input
          placeholder="Search templates or subjects..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="max-w-xs h-9 text-sm"
        />

        <div className="flex flex-wrap items-center gap-1.5">
          <button
            onClick={() => setCategoryFilter(null)}
            className={`px-3 py-1 rounded-full text-xs font-medium ${
              !categoryFilter ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/80"
            }`}
          >
            All ({templates.length})
          </button>
          {["newsletter", "onboarding", "promotional", "retention"].map((cat) => (
            <button
              key={cat}
              onClick={() => setCategoryFilter(cat)}
              className={`px-3 py-1 rounded-full text-xs font-medium capitalize ${
                categoryFilter === cat ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Templates Grid */}
      {filtered.length === 0 ? (
        <div className="py-16 text-center border rounded-xl bg-card">
          <Mail className="h-10 w-10 text-muted-foreground/40 mx-auto mb-3" />
          <h3 className="font-semibold text-base">No templates found</h3>
          <p className="text-sm text-muted-foreground mt-1 max-w-sm mx-auto">
            Get started by launching the visual builder to design your first newsletter template.
          </p>
          <Button onClick={handleOpenNewBuilder} className="mt-4 bg-[#0066cc]">
            <Plus className="h-4 w-4 mr-2" /> Launch Visual Builder
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((template) => (
            <Card key={template.id} className="border-border bg-card hover:shadow-md transition-shadow flex flex-col justify-between">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-base font-semibold leading-tight line-clamp-1">
                    {template.name}
                  </CardTitle>
                  <Badge variant="secondary" className="capitalize text-[10px] shrink-0">
                    {template.category || "custom"}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2 mt-1">
                  {template.subject}
                </p>
              </CardHeader>

              <CardContent className="pt-0 space-y-4">
                {/* Mini Preview Box */}
                <div
                  onClick={() => handleEditTemplate(template)}
                  className="h-28 bg-muted/30 border border-border/60 rounded-md p-3 text-[11px] text-muted-foreground overflow-hidden cursor-pointer hover:border-blue-500 transition-colors relative group"
                >
                  <div
                    dangerouslySetInnerHTML={{
                      __html: (template.body_html || "")
                        .replace(/<svg[\s\S]*?<\/svg>/gi, "[Illustration]")
                        .slice(0, 180),
                    }}
                  />
                  <div className="absolute inset-0 bg-blue-600/10 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
                    <span className="bg-background text-foreground text-xs px-2.5 py-1 rounded shadow font-medium flex items-center gap-1.5">
                      <Edit3 className="h-3.5 w-3.5 text-blue-600" /> Edit in Builder
                    </span>
                  </div>
                </div>

                {/* Action buttons */}
                <div className="flex items-center justify-between pt-1 border-t border-border/40 text-xs">
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setPreviewingTemplate(template)}
                      className="h-7 px-2 text-xs"
                      title="Preview"
                    >
                      <Eye className="h-3.5 w-3.5 mr-1" /> Preview
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDuplicate(template)}
                      className="h-7 px-2 text-xs"
                      title="Duplicate"
                    >
                      <Copy className="h-3.5 w-3.5 mr-1" /> Clone
                    </Button>
                  </div>

                  <div className="flex items-center gap-1">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleEditTemplate(template)}
                      className="h-7 px-2 text-xs font-medium text-blue-600 dark:text-blue-400"
                    >
                      <Edit3 className="h-3.5 w-3.5 mr-1" /> Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(template.id)}
                      className="h-7 w-7 p-0 text-destructive hover:bg-destructive/10"
                      title="Delete Template"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Preview Dialog */}
      <Dialog open={!!previewingTemplate} onOpenChange={() => setPreviewingTemplate(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between pr-4">
              <span>{previewingTemplate?.name}</span>
              <Badge variant="outline" className="text-xs font-mono">
                {previewingTemplate?.category}
              </Badge>
            </DialogTitle>
            <DialogDescription>
              Subject: {previewingTemplate?.subject}
            </DialogDescription>
          </DialogHeader>

          <div className="border rounded-md bg-muted/10 p-4 max-h-[60vh] overflow-y-auto">
            <div
              className="bg-white text-zinc-900 rounded p-6 shadow-xs max-w-[560px] mx-auto text-sm leading-relaxed"
              dangerouslySetInnerHTML={{ __html: previewingTemplate?.body_html || "" }}
            />
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setPreviewingTemplate(null)}>
              Close
            </Button>
            <Button
              onClick={() => {
                const t = previewingTemplate
                setPreviewingTemplate(null)
                if (t) handleEditTemplate(t)
              }}
              className="bg-[#0066cc]"
            >
              <Edit3 className="h-4 w-4 mr-2" /> Open in Visual Builder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
