"use client"

import React, { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  Share2,
  Copy,
  Check,
  Users,
  UserPlus,
  Shield,
  Trash2,
  Mail,
  Globe,
  Sparkles,
} from "lucide-react"

interface Collaborator {
  id: string
  email: string
  name: string
  role: "Editor" | "Reviewer" | "Viewer"
  status: "active" | "invited"
}

interface DomeStudioShareModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  pageTitle: string
  pageSlug: string
}

export function DomeStudioShareModal({
  open,
  onOpenChange,
  pageTitle,
  pageSlug,
}: DomeStudioShareModalProps) {
  const [inviteEmail, setInviteEmail] = useState("")
  const [inviteRole, setInviteRole] = useState<"Editor" | "Reviewer" | "Viewer">("Reviewer")
  const [copiedLink, setCopiedLink] = useState(false)
  const [collaborators, setCollaborators] = useState<Collaborator[]>([
    {
      id: "collab-1",
      name: "Sipho Dlamini",
      email: "sipho.marketing@omnidome.io",
      role: "Editor",
      status: "active",
    },
    {
      id: "collab-2",
      name: "Anika Patel",
      email: "anika.commercial@omnidome.io",
      role: "Reviewer",
      status: "active",
    },
    {
      id: "collab-3",
      name: "Bongani Moyo",
      email: "bongani.network@omnidome.io",
      role: "Viewer",
      status: "invited",
    },
  ])

  const shareUrl = `https://connect.omnidome.io/preview/${pageSlug || "fibre-summer-sprint"}?ref=team_share`

  const handleCopy = () => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(shareUrl)
      setCopiedLink(true)
      setTimeout(() => setCopiedLink(false), 2200)
    }
  }

  const handleInvite = (e: React.FormEvent) => {
    e.preventDefault()
    if (!inviteEmail.trim()) return

    const newCollab: Collaborator = {
      id: `collab-${Date.now()}`,
      name: inviteEmail.split("@")[0].replace(".", " "),
      email: inviteEmail.trim(),
      role: inviteRole,
      status: "invited",
    }

    setCollaborators((prev) => [newCollab, ...prev])
    setInviteEmail("")
  }

  const handleRemove = (id: string) => {
    setCollaborators((prev) => prev.filter((c) => c.id !== id))
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md sm:max-w-lg border-border bg-card">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="rounded-lg bg-cyan-500/20 p-2 text-cyan-400">
              <Share2 className="h-5 w-5" />
            </div>
            <div>
              <DialogTitle className="text-base font-semibold text-foreground">
                Share & Collaborate
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                Invite colleagues from Marketing, Sales, and Network Operations to co-design and review{" "}
                <span className="font-medium text-foreground">{pageTitle}</span>.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Shareable Link Bar */}
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Live Review Link</Label>
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Globe className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  readOnly
                  value={shareUrl}
                  className="pl-8 text-xs font-mono bg-secondary/40 text-muted-foreground"
                />
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={handleCopy}
                className="text-xs h-9 font-medium"
              >
                {copiedLink ? (
                  <>
                    <Check className="mr-1.5 h-3.5 w-3.5 text-emerald-400" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="mr-1.5 h-3.5 w-3.5" />
                    Copy Link
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Invite Employee Form */}
          <form onSubmit={handleInvite} className="space-y-2 rounded-lg border border-border bg-secondary/20 p-3">
            <Label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <UserPlus className="h-3.5 w-3.5 text-cyan-400" />
              Invite Team Member
            </Label>
            <div className="flex flex-col sm:flex-row gap-2">
              <div className="relative flex-1">
                <Mail className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  type="email"
                  placeholder="colleague@omnidome.io"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="pl-8 text-xs h-9 bg-background"
                />
              </div>
              <div className="flex gap-2">
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as any)}
                  className="h-9 rounded-md border border-border bg-background px-2.5 text-xs text-foreground focus:outline-none"
                >
                  <option value="Editor">Editor</option>
                  <option value="Reviewer">Reviewer</option>
                  <option value="Viewer">Viewer</option>
                </select>
                <Button
                  type="submit"
                  size="sm"
                  className="h-9 text-xs bg-cyan-500 hover:bg-cyan-400 text-cyan-950 font-semibold"
                >
                  Invite
                </Button>
              </div>
            </div>
          </form>

          {/* Active Collaborators */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs text-muted-foreground font-medium flex items-center gap-1.5">
                <Users className="h-3.5 w-3.5 text-muted-foreground" />
                People with Access ({collaborators.length})
              </Label>
              <Badge variant="outline" className="text-[10px] border-border text-muted-foreground">
                OmniDome Tenant Domain
              </Badge>
            </div>

            <div className="max-h-48 overflow-y-auto space-y-2 divide-y divide-border/40">
              {collaborators.map((c) => (
                <div key={c.id} className="pt-2 first:pt-0 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-cyan-500/20 text-cyan-400 font-semibold text-[11px]">
                      {c.name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <p className="font-medium text-foreground leading-tight">{c.name}</p>
                      <p className="text-[11px] text-muted-foreground">{c.email}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Badge
                      variant="secondary"
                      className={`text-[10px] px-2 py-0.5 ${
                        c.role === "Editor"
                          ? "bg-purple-500/20 text-purple-300"
                          : c.role === "Reviewer"
                          ? "bg-blue-500/20 text-blue-300"
                          : "bg-secondary text-muted-foreground"
                      }`}
                    >
                      {c.role}
                    </Badge>

                    {c.status === "invited" && (
                      <span className="text-[10px] text-amber-400 italic">Pending</span>
                    )}

                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-muted-foreground hover:text-red-400"
                      onClick={() => handleRemove(c.id)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter className="border-t border-border pt-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            className="text-xs"
          >
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
