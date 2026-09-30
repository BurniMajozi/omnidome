"use client"

import React, { useState, useEffect } from "react"
import { SandboxedEmailPreview, htmlToExcerpt } from "./email-html-preview"
import {
  FileText, Plus, Edit3, Trash2, Copy, Eye, Sparkles, AlertTriangle,
  Layers, ArrowLeft, Download, Check, ExternalLink, Mail
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { writeMarketing, type EmailTemplate } from "@/lib/marketing-api"
import { useMarketingLoad } from "@/lib/use-marketing-load"
import { describeMutationError } from "@/lib/marketing-state"
import { NotConnected } from "@/components/ui/not-connected"
import { EmailBuilder } from "./email-builder"

interface EmailTemplatesTabProps {
  initialEditTemplateId?: string | null
  onOpenComposerWithTemplate?: (template: EmailTemplate) => void
}

export function EmailTemplatesTab({
  initialEditTemplateId,
  onOpenComposerWithTemplate,
}: EmailTemplatesTabProps) {
  // Real templates only (shared read with the compose tab); no seeded samples.
  const { value: templatesLoad, reload: loadTemplates } = useMarketingLoad<EmailTemplate[]>("/templates")
  const templates: EmailTemplate[] = templatesLoad.state === "ready" ? templatesLoad.data : []
  const [actionError, setActionError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)

  // Builder mode state
  const [editingTemplate, setEditingTemplate] = useState<EmailTemplate | null>(null)
  const [isBuilderOpen, setIsBuilderOpen] = useState(false)

  // Preview modal
  const [previewingTemplate, setPreviewingTemplate] = useState<EmailTemplate | null>(null)

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

  // Returns false when the server rejected the write so the builder does not flash "Saved!".
  const handleSaveFromBuilder = async (savedData: {
    name: string
    subject: string
    body_html: string
    category?: string
  }): Promise<boolean> => {
    setActionError(null)
    if (editingTemplate) {
      const r = await writeMarketing<EmailTemplate>("PUT", `/templates/${editingTemplate.id}`, savedData)
      if (!r.ok) {
        setActionError(describeMutationError(r.status, r.error))
        return false
      }
      setEditingTemplate({ ...editingTemplate, ...savedData, category: savedData.category || editingTemplate.category })
    } else {
      const r = await writeMarketing<EmailTemplate>("POST", "/templates", savedData)
      if (!r.ok || !r.data) {
        setActionError(describeMutationError(r.status, r.error))
        return false
      }
      setEditingTemplate(r.data)
    }
    loadTemplates()
    return true
  }

  const handleDelete = async (id: string) => {
    setActionError(null)
    const r = await writeMarketing("DELETE", `/templates/${id}`)
    if (!r.ok) {
      setActionError(describeMutationError(r.status, r.error))
      return
    }
    loadTemplates()
  }

  const handleDuplicate = async (template: EmailTemplate) => {
    setActionError(null)
    const r = await writeMarketing("POST", "/templates", {
      name: `${template.name} (Copy)`,
      subject: template.subject,
      body_html: template.body_html,
      category: template.category,
    })
    if (!r.ok) {
      setActionError(describeMutationError(r.status, r.error))
      return
    }
    loadTemplates()
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
        {actionError && <p role="alert" className="text-sm text-red-400">{actionError}</p>}
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
            All{templatesLoad.state === "ready" ? ` (${templates.length})` : ""}
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

      {actionError && <p role="alert" className="text-sm text-red-400">{actionError}</p>}

      {/* Templates Grid */}
      {templatesLoad.state !== "ready" ? (
        <NotConnected loadable={templatesLoad} service="The marketing service" onRetry={loadTemplates} />
      ) : filtered.length === 0 ? (
        <div className="py-16 text-center border rounded-xl bg-card">
          <Mail className="h-10 w-10 text-muted-foreground/40 mx-auto mb-3" />
          <h3 className="font-semibold text-base">{templates.length === 0 ? "No templates yet" : "No templates match"}</h3>
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
                  <div>{htmlToExcerpt(template.body_html || "", 180)}</div>
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
            <SandboxedEmailPreview html={previewingTemplate?.body_html || ""} className="w-full h-[50vh] max-w-[600px] mx-auto block bg-white rounded border-0" />
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
