"use client"

import { useState, useMemo, useEffect, useCallback } from "react"
import {
  Inbox,
  Send,
  FileText,
  Clock,
  Layers,
  Trash2,
  Folder,
  Shield,
  LayoutGrid,
  BarChart3,
  Globe,
  Settings,
  Search,
  RotateCw,
  Copy,
  Check,
  ChevronDown,
  ChevronsUpDown,
  ChevronRight,
  Plus,
  Star,
  Paperclip,
  ArrowLeft,
  ArrowRight,
  Bot,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  FileUp,
  Tag,
  Users,
  Building,
  KeyRound,
  Filter,
  ExternalLink,
  HelpCircle,
  X,
  Code2,
  ArrowUpRight,
  TrendingUp,
  Flame,
  UserPlus,
  MoreVertical,
  Sliders,
  Mail,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ThemeToggleCompact } from "@/components/ui/theme-toggle"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import {
  listMailboxes,
  listEmails,
  sendEmail,
  replyToEmail,
  approveAgentReply,
  updateEmail,
  deleteEmail,
  type MailboxRow,
  type AgentEmailRow,
} from "@/lib/mail-api"
import {
  AgentMailPod,
  AgentMailbox,
  AgentMailThread,
  AgentMailMessage,
  AgentPersonaType,
  AgentMailLabel,
  AgentMailListRule,
  AgentMailDomain,
  SharedMailboxGroup,
  SharedMailFolder,
  SharedMailboxMember,
} from "./types"
import {
  INITIAL_PODS,
  INITIAL_MAILBOXES,
  INITIAL_THREADS,
  INITIAL_LABELS,
  INITIAL_LIST_RULES,
  INITIAL_DOMAINS,
  INITIAL_METRICS,
  INITIAL_SHARED_GROUPS,
  INITIAL_SHARED_FOLDERS,
} from "./mock-data"


// ── Live data wiring ────────────────────────────────────────────────────────
const LIVE_POD: AgentMailPod = {
  id: "pod-live",
  name: "Live workspace",
  tenantId: "current",
  isDefault: true,
  description: "Real mailboxes from the communication service",
  inboxCount: 0,
  createdAt: new Date(0).toISOString(),
}

const EMPTY_MAILBOX: AgentMailbox = {
  id: "",
  podId: LIVE_POD.id,
  emailAddress: "no mailbox configured",
  displayName: "No mailbox",
  agentType: "auto_reply",
  isHuman: false,
  domain: "",
  autoReplyEnabled: false,
  smartLabelEnabled: false,
  unreadCount: 0,
  totalCount: 0,
  isActive: false,
  createdAt: new Date(0).toISOString(),
}

const EMPTY_METRICS: typeof INITIAL_METRICS = {
  totalInbound: 0,
  totalOutbound: 0,
  automatedRepliesSent: 0,
  avgResponseSeconds: 0,
  smartLabelAccuracy: 0,
  pendingApprovals: 0,
  escalatedToHuman: 0,
  activeAgents: 0,
  deliveryRate: 0,
  volumeByHour: [],
  categoryDistribution: [],
  sentCount: 0,
  receivedCount: 0,
  bouncedCount: 0,
  rejectedCount: 0,
  complainedCount: 0,
  bounceRate: 0,
  complaintRate: 0,
  streakDays: 0,
  messages30Days: 0,
  activityMatrix: [],
}

const PERSONAS: AgentPersonaType[] = ["sales", "smart_label", "auto_reply", "finance", "support", "human"]
const MESSAGE_STATUSES = ["received", "processed", "auto_replied", "sent", "draft", "failed"]

function mapMailbox(row: MailboxRow, emails: AgentEmailRow[]): AgentMailbox {
  const mine = emails.filter((e) => e.mailbox_id === row.id)
  const persona = PERSONAS.includes(row.agent_type as AgentPersonaType)
    ? (row.agent_type as AgentPersonaType)
    : "auto_reply"
  return {
    id: row.id,
    podId: LIVE_POD.id,
    emailAddress: row.email_address,
    displayName: row.display_name,
    agentType: persona,
    isHuman: persona === "human",
    domain: row.email_address.split("@")[1] ?? "",
    autoReplyEnabled: row.auto_reply_enabled,
    smartLabelEnabled: false,
    inboundChannelId: row.inbound_channel_id ?? undefined,
    unreadCount: mine.filter((e) => e.direction === "inbound" && e.status === "received").length,
    totalCount: mine.length,
    isActive: row.is_active,
    createdAt: row.created_at,
  }
}

function parseSender(raw: string): { name: string; email: string } {
  const m = raw.match(/^\s*"?([^"<]*?)"?\s*<([^>]+)>\s*$/)
  if (m) return { name: m[1].trim() || m[2], email: m[2] }
  return { name: raw, email: raw }
}

function mapEmailsToThreads(emails: AgentEmailRow[]): AgentMailThread[] {
  const groups = new Map<string, AgentEmailRow[]>()
  for (const e of emails) {
    const key = `${e.mailbox_id}::${(e.subject || "").replace(/^(re|fwd?):\s*/gi, "").trim().toLowerCase()}`
    const list = groups.get(key)
    if (list) list.push(e)
    else groups.set(key, [e])
  }
  const threads: AgentMailThread[] = []
  groups.forEach((rows, key) => {
    rows.sort((a, b) => a.created_at.localeCompare(b.created_at))
    const last = rows[rows.length - 1]
    const first = rows[0]
    const from = parseSender(first.sender)
    const messages: AgentMailMessage[] = rows.map((r) => {
      const s = parseSender(r.sender)
      const rc = parseSender(r.recipient)
      return {
        id: r.id,
        threadId: key,
        direction: r.direction === "outbound" ? "outbound" : "inbound",
        sender: s.name,
        senderEmail: s.email,
        recipient: rc.name,
        recipientEmail: rc.email,
        subject: r.subject,
        bodyText: r.body_text,
        bodyHtml: r.body_html ?? undefined,
        status: (r.status === "replied"
          ? "auto_replied"
          : MESSAGE_STATUSES.includes(r.status)
            ? r.status
            : "received") as AgentMailMessage["status"],
        agentResponse: r.agent_response ?? undefined,
        createdAt: r.created_at,
      }
    })
    const d = new Date(last.created_at)
    threads.push({
      id: key,
      podId: LIVE_POD.id,
      mailboxId: first.mailbox_id,
      sender: from.name,
      senderEmail: from.email,
      recipientEmail: parseSender(first.recipient).email,
      subject: first.subject,
      snippet: last.body_text.slice(0, 140),
      unread: rows.some((r) => r.direction === "inbound" && r.headers?.is_read !== true),
      isStarred: rows.some((r) => r.headers?.is_starred === true),
      folder: last.direction === "outbound" ? "sent" : "inbox",
      labels: [],
      messagesCount: rows.length,
      hasAttachments: false,
      dateGroup: d.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      timestamp: last.created_at,
      messages,
    })
  })
  return threads.sort((a, b) => b.timestamp.localeCompare(a.timestamp))
}

export interface AgentMailViewProps {
  onCreateTask?: (task: { title: string; assignee: string; priority: "low" | "medium" | "high"; notes?: string }) => void
  onCreateApproval?: (approval: { subject: string; agent: string; amount: string; reason: string }) => void
  onCreateEscalation?: (escalation: { title: string; severity: "low" | "medium" | "high" | "critical"; notes?: string }) => void
}

export function AgentMailView({
  onCreateTask,
  onCreateApproval,
  onCreateEscalation,
}: AgentMailViewProps) {
  // ── Navigation & Views ──
  const [activeSideNav, setActiveSideNav] = useState<
    "overview" | "inboxes" | "metrics" | "domains" | "lists" | "settings"
  >("overview")
  const [activeFolder, setActiveFolder] = useState<
    "inbox" | "sent" | "drafts" | "scheduled" | "all" | "trash" | "other"
  >("inbox")

  // Overview time range
  const [overviewTimeRange, setOverviewTimeRange] = useState<"24h" | "7d" | "30d" | "custom">("30d")

  // ── Multi-Tenant Pod State ──
  const [pods, setPods] = useState<AgentMailPod[]>([LIVE_POD])
  const [selectedPodId, setSelectedPodId] = useState<string>(LIVE_POD.id)
  const [createPodOpen, setCreatePodOpen] = useState(false)
  const [newPodName, setNewPodName] = useState("")

  // ── Mailboxes & Inboxes State ──
  const [mailboxes, setMailboxes] = useState<AgentMailbox[]>([])
  const [selectedMailboxId, setSelectedMailboxId] = useState<string>("")
  const [createInboxOpen, setCreateInboxOpen] = useState(false)
  const [newInboxUsername, setNewInboxUsername] = useState("")
  const [newInboxDomain, setNewInboxDomain] = useState("agentmail.to")
  const [newInboxPersona, setNewInboxPersona] = useState<AgentPersonaType>("auto_reply")
  const [newInboxDisplayName, setNewInboxDisplayName] = useState("")

  // ── Shared Groups & Team Mailboxes State ──
  const [sharedGroups, setSharedGroups] = useState<SharedMailboxGroup[]>([])
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null)
  const [manageGroupModalOpen, setManageGroupModalOpen] = useState(false)
  const [capabilitiesDrawerOpen, setCapabilitiesDrawerOpen] = useState(false)
  const [newMemberEmail, setNewMemberEmail] = useState("")
  const [newMemberRole, setNewMemberRole] = useState<"admin" | "operator" | "member" | "viewer">("member")
  const [createGroupOpen, setCreateGroupOpen] = useState(false)
  const [newGroupName, setNewGroupName] = useState("")
  const [newGroupEmail, setNewGroupEmail] = useState("")

  // ── Threads & Messaging State ──
  const [threads, setThreads] = useState<AgentMailThread[]>([])
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedLabelFilter, setSelectedLabelFilter] = useState<string | null>(null)
  const [selectedThreadIds, setSelectedThreadIds] = useState<Set<string>>(new Set())
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [copiedEmail, setCopiedEmail] = useState(false)

  // ── Allow/Block Lists & Domains ──
  const [listRules, setListRules] = useState<AgentMailListRule[]>([])
  const [domains, setDomains] = useState<AgentMailDomain[]>([])
  const [labels, setLabels] = useState<AgentMailLabel[]>([])
  const [addRuleOpen, setAddRuleOpen] = useState(false)
  const [newRuleScope, setNewRuleScope] = useState<"receive" | "send" | "reply">("receive")
  const [newRuleType, setNewRuleType] = useState<"allow" | "block">("allow")
  const [newRulePattern, setNewRulePattern] = useState("")
  const [newRuleReason, setNewRuleReason] = useState("")
  const [apiDocsOpen, setApiDocsOpen] = useState(false)

  // ── Compose Dialog State ──
  const [composeOpen, setComposeOpen] = useState(false)
  const [composeTo, setComposeTo] = useState("")
  const [composeSubject, setComposeSubject] = useState("")
  const [composeBody, setComposeBody] = useState("")
  const [composeFromMailboxId, setComposeFromMailboxId] = useState<string>("")
  const [aiPrompt, setAiPrompt] = useState("")
  const [isGeneratingAi, setIsGeneratingAi] = useState(false)
  const [notificationMsg, setNotificationMsg] = useState<string | null>(null)
  const [sendingCompose, setSendingCompose] = useState(false)
  const [composeError, setComposeError] = useState<string | null>(null)
  const [replyText, setReplyText] = useState("")
  const [replyBusy, setReplyBusy] = useState(false)
  const [replyError, setReplyError] = useState<string | null>(null)


  // ── Live data vs explicit demo data ──
  const [demoMode, setDemoMode] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const metrics = demoMode ? INITIAL_METRICS : EMPTY_METRICS

  const loadLive = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    const [mbRes, emRes] = await Promise.all([listMailboxes(), listEmails()])
    if (!mbRes.ok || !emRes.ok) {
      setLoadError(mbRes.error || emRes.error || "Mail service unavailable")
      setLoading(false)
      return
    }
    const rows = emRes.data ?? []
    const mbs = (mbRes.data ?? []).map((r) => mapMailbox(r, rows))
    setPods([{ ...LIVE_POD, inboxCount: mbs.length }])
    setSelectedPodId(LIVE_POD.id)
    setMailboxes(mbs)
    setSelectedMailboxId((prev) => (mbs.some((m) => m.id === prev) ? prev : mbs[0]?.id ?? ""))
    setComposeFromMailboxId((prev) => (mbs.some((m) => m.id === prev) ? prev : mbs[0]?.id ?? ""))
    setThreads(mapEmailsToThreads(rows))
    setSharedGroups([])
    setListRules([])
    setDomains([])
    setLabels([])
    setLoading(false)
  }, [])

  useEffect(() => {
    if (demoMode) {
      setPods(INITIAL_PODS)
      setSelectedPodId("pod-default")
      setMailboxes(INITIAL_MAILBOXES)
      setSelectedMailboxId("mb-burnibraa")
      setComposeFromMailboxId("mb-burnibraa")
      setThreads(INITIAL_THREADS)
      setSharedGroups(INITIAL_SHARED_GROUPS)
      setListRules(INITIAL_LIST_RULES)
      setDomains(INITIAL_DOMAINS)
      setLabels(INITIAL_LABELS)
      setLoading(false)
      setLoadError(null)
    } else {
      void loadLive()
    }
  }, [demoMode, loadLive])

  const liveEmpty = !demoMode && !loading && !loadError && mailboxes.length === 0 && threads.length === 0

  // Current active pod
  const currentPod = useMemo(
    () => pods.find((p) => p.id === selectedPodId) || pods[0],
    [pods, selectedPodId]
  )

  // Current active mailbox
  const currentMailbox = useMemo(
    () => mailboxes.find((m) => m.id === selectedMailboxId) || mailboxes[0] || EMPTY_MAILBOX,
    [mailboxes, selectedMailboxId]
  )

  // Current active shared group (if selected)
  const currentSharedGroup = useMemo(
    () => sharedGroups.find((g) => g.id === selectedGroupId || g.mailboxId === selectedMailboxId) || null,
    [sharedGroups, selectedGroupId, selectedMailboxId]
  )

  // Filtered threads for current mailbox and folder
  const currentThreads = useMemo(() => {
    return threads.filter((t) => {
      // Must match pod
      if (t.podId !== currentPod.id) return false
      // Filter by selected mailbox if not all mail
      if (activeFolder !== "all" && t.mailboxId !== currentMailbox?.id) return false
      // Filter by folder
      if (activeFolder === "inbox" && t.folder !== "inbox") return false
      if (activeFolder === "sent" && t.folder !== "sent") return false
      if (activeFolder === "drafts" && t.folder !== "drafts") return false
      if (activeFolder === "trash" && t.folder !== "trash") return false

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const matches =
          t.subject.toLowerCase().includes(q) ||
          t.snippet.toLowerCase().includes(q) ||
          t.sender.toLowerCase().includes(q) ||
          t.senderEmail.toLowerCase().includes(q)
        if (!matches) return false
      }

      // Label filter
      if (selectedLabelFilter && !t.labels.includes(selectedLabelFilter)) {
        return false
      }

      return true
    })
  }, [threads, currentPod, currentMailbox, activeFolder, searchQuery, selectedLabelFilter])

  // Active selected thread details
  const activeThread = useMemo(
    () => threads.find((t) => t.id === selectedThreadId) || null,
    [threads, selectedThreadId]
  )

  // Handlers
  const handleCopyEmail = (email?: string) => {
    const target = email || currentMailbox?.emailAddress
    if (target) {
      navigator.clipboard.writeText(target)
      setCopiedEmail(true)
      setTimeout(() => setCopiedEmail(false), 2000)
    }
  }

  const handleRefresh = () => {
    setIsRefreshing(true)
    setTimeout(() => {
      setIsRefreshing(false)
      showNotification("Mailbox refreshed from AgentMail API")
    }, 600)
  }

  const showNotification = (msg: string) => {
    setNotificationMsg(msg)
    setTimeout(() => setNotificationMsg(null), 3500)
  }

  const toggleSelectThread = (id: string) => {
    setSelectedThreadIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedThreadIds.size === currentThreads.length) {
      setSelectedThreadIds(new Set())
    } else {
      setSelectedThreadIds(new Set(currentThreads.map((t) => t.id)))
    }
  }

  const handleCreatePod = () => {
    if (!newPodName.trim()) return
    const newPod: AgentMailPod = {
      id: `pod-${Date.now()}`,
      name: newPodName.trim(),
      tenantId: "tenant-custom",
      isDefault: false,
      inboxCount: 0,
      createdAt: new Date().toISOString(),
    }
    setPods((prev) => [...prev, newPod])
    setSelectedPodId(newPod.id)
    setNewPodName("")
    setCreatePodOpen(false)
    showNotification(`Pod "${newPod.name}" initialized`)
  }

  const handleCreateInbox = () => {
    if (!newInboxUsername.trim()) return
    const emailAddress = `${newInboxUsername.trim()}@${newInboxDomain}`
    const newMb: AgentMailbox = {
      id: `mb-${Date.now()}`,
      podId: selectedPodId,
      emailAddress,
      displayName: newInboxDisplayName || newInboxUsername,
      agentType: newInboxPersona,
      isHuman: newInboxPersona === "human",
      domain: newInboxDomain,
      autoReplyEnabled: true,
      smartLabelEnabled: true,
      unreadCount: 0,
      totalCount: 0,
      isActive: true,
      createdAt: new Date().toISOString(),
    }
    setMailboxes((prev) => [...prev, newMb])
    setSelectedMailboxId(newMb.id)
    setCreateInboxOpen(false)
    setNewInboxUsername("")
    setNewInboxDisplayName("")
    showNotification(`Inbox "${emailAddress}" provisioned with AgentMail`)
  }

  const handleAddMemberToGroup = () => {
    if (!newMemberEmail.trim() || !currentSharedGroup) return
    const newMember: SharedMailboxMember = {
      userId: `usr-${Date.now()}`,
      name: newMemberEmail.split("@")[0].replace(".", " "),
      email: newMemberEmail.trim(),
      role: newMemberRole,
      avatar: newMemberEmail.slice(0, 2).toUpperCase(),
      addedAt: new Date().toISOString(),
    }
    setSharedGroups((prev) =>
      prev.map((g) =>
        g.id === currentSharedGroup.id
          ? { ...g, members: [...g.members, newMember] }
          : g
      )
    )
    setNewMemberEmail("")
    showNotification(`Added ${newMember.email} as ${newMember.role} to ${currentSharedGroup.name}`)
  }

  const handleRemoveMemberFromGroup = (memberEmail: string) => {
    if (!currentSharedGroup) return
    setSharedGroups((prev) =>
      prev.map((g) =>
        g.id === currentSharedGroup.id
          ? { ...g, members: g.members.filter((m) => m.email !== memberEmail) }
          : g
      )
    )
    showNotification(`Removed ${memberEmail} from ${currentSharedGroup.name}`)
  }

  const handleAskOrchestratorAi = (preset?: string) => {
    setIsGeneratingAi(true)
    setTimeout(() => {
      setIsGeneratingAi(false)
      if (preset?.includes("sales") || aiPrompt.includes("quote") || aiPrompt.includes("sales")) {
        setComposeSubject("OmniDome Enterprise Telemetry & SLA Agreement (Proposal)")
        setComposeBody(
          `Dear Client,\n\nFollowing our review of your deployment specifications, OmniDome is pleased to propose our Enterprise Edge Tier.\n\nIncluded Capabilities:\n• Sub-50ms Telemetry Stream\n• Real-time Automated Driver Alerting\n• Dedicated Pod Isolation & AgentMail Integration\n• 99.99% Availability SLA\n\nAnnual Retainer: R 245,000.00\nPayment Terms: Net 30 with 15% inaugural incentive applied.\n\nPlease let us know if you require any adjustments prior to signature.\n\nWarm regards,\nOmniDome AI Sales Assistant`
        )
      } else {
        setComposeSubject("Regarding your technical support inquiry")
        setComposeBody(
          `Hello,\n\nThank you for reaching out to OmniDome support. We have investigated the telemetry latency on gateway node #OM-9102.\n\nThe edge firmware patch has been scheduled for 23:00 SAST with zero anticipated downtime.\n\nBest regards,\nOmniDome Support Team`
        )
      }
      showNotification("Draft generated by OmniDome Orchestrator AI")
    }, 800)
  }

  const handleSendCompose = async () => {
    if (!composeTo.trim() || !composeSubject.trim()) return
    if (!demoMode) {
      const mbId = composeFromMailboxId || currentMailbox?.id
      if (!mbId) {
        setComposeError("Select a mailbox to send from")
        return
      }
      const split = (v: string) => v.split(/[,;\s]+/).map((x) => x.trim()).filter(Boolean)
      setSendingCompose(true)
      setComposeError(null)
      const res = await sendEmail({
        mailbox_id: mbId,
        to: split(composeTo),
        subject: composeSubject,
        body_text: composeBody,
      })
      setSendingCompose(false)
      if (!res.ok || res.data?.status === "failed") {
        setComposeError(res.error || (res.data?.headers?.error as string) || "Send failed")
        return
      }
      setComposeOpen(false)
      setComposeTo("")
      setComposeSubject("")
      setComposeBody("")
      showNotification(`Email sent to ${res.data?.recipient ?? "recipient"}`)
      void loadLive()
      return
    }
    const senderMb = mailboxes.find((m) => m.id === composeFromMailboxId) || currentMailbox
    const newMsg: AgentMailMessage = {
      id: `msg-${Date.now()}`,
      threadId: `thread-outbound-${Date.now()}`,
      direction: "outbound",
      sender: senderMb.displayName,
      senderEmail: senderMb.emailAddress,
      recipient: composeTo,
      recipientEmail: composeTo,
      subject: composeSubject,
      bodyText: composeBody,
      status: "sent",
      createdAt: new Date().toISOString(),
    }
    const newThread: AgentMailThread = {
      id: newMsg.threadId,
      podId: selectedPodId,
      mailboxId: senderMb.id,
      sender: senderMb.displayName,
      senderEmail: senderMb.emailAddress,
      recipientEmail: composeTo,
      subject: composeSubject,
      snippet: composeBody.slice(0, 90),
      unread: false,
      isStarred: false,
      folder: "sent",
      labels: ["Outbound"],
      messagesCount: 1,
      hasAttachments: false,
      dateGroup: "Today",
      timestamp: "Just now",
      messages: [newMsg],
    }
    setThreads((prev) => [newThread, ...prev])
    setComposeOpen(false)
    setComposeTo("")
    setComposeSubject("")
    setComposeBody("")
    showNotification(`Email dispatched to ${composeTo} via AgentMail`)
  }

  const liveMessageIds = (thread: AgentMailThread) => thread.messages.map((m) => m.id)

  const openThreadLive = (thread: AgentMailThread) => {
    setSelectedThreadId(thread.id)
    setReplyText("")
    setReplyError(null)
    if (demoMode || !thread.unread) return
    setThreads((prev) => prev.map((t) => (t.id === thread.id ? { ...t, unread: false } : t)))
    void Promise.all(
      thread.messages.filter((m) => m.direction === "inbound").map((m) => updateEmail(m.id, { is_read: true }))
    )
  }

  const toggleStarLive = async (thread: AgentMailThread) => {
    const next = !thread.isStarred
    setThreads((prev) => prev.map((t) => (t.id === thread.id ? { ...t, isStarred: next } : t)))
    if (demoMode) return
    const results = await Promise.all(liveMessageIds(thread).map((id) => updateEmail(id, { is_starred: next })))
    if (results.some((r) => !r.ok)) {
      setThreads((prev) => prev.map((t) => (t.id === thread.id ? { ...t, isStarred: !next } : t)))
      showNotification("Could not update star: " + (results.find((r) => !r.ok)?.error ?? "error"))
    }
  }

  const deleteSelectedLive = async () => {
    const ids = new Set(selectedThreadIds)
    if (demoMode) {
      setThreads((prev) => prev.filter((t) => !ids.has(t.id)))
      setSelectedThreadIds(new Set())
      showNotification("Selected threads moved to trash")
      return
    }
    const targets = threads.filter((t) => ids.has(t.id)).flatMap(liveMessageIds)
    const results = await Promise.all(targets.map((id) => deleteEmail(id)))
    setSelectedThreadIds(new Set())
    const failed = results.find((r) => !r.ok)
    showNotification(failed ? `Delete failed: ${failed.error}` : "Selected threads deleted")
    void loadLive()
  }

  const handleSendReplyLive = async (thread: AgentMailThread) => {
    const inbound = [...thread.messages].reverse().find((m) => m.direction === "inbound")
    if (!inbound || !replyText.trim()) return
    setReplyBusy(true)
    setReplyError(null)
    const res = await replyToEmail(inbound.id, replyText)
    setReplyBusy(false)
    if (!res.ok || res.data?.status === "failed") {
      setReplyError(res.error || (res.data?.headers?.error as string) || "Reply failed")
      return
    }
    setReplyText("")
    showNotification("Reply sent")
    void loadLive()
  }

  const handleApproveAgentReply = async (thread: AgentMailThread) => {
    const target = [...thread.messages]
      .reverse()
      .find((m) => m.direction === "inbound" && m.agentResponse && m.status !== "auto_replied")
    if (!target) return
    setReplyBusy(true)
    setReplyError(null)
    const res = await approveAgentReply(target.id)
    setReplyBusy(false)
    if (!res.ok || res.data?.status === "failed") {
      setReplyError(res.error || (res.data?.headers?.error as string) || "Approve and send failed")
      return
    }
    showNotification("Agent reply approved and sent")
    void loadLive()
  }

  const handleAutoReply = (thread: AgentMailThread) => {
    const msg = thread.messages[0]
    if (!msg) return
    const replyBody =
      msg.agentSuggestedReply ||
      `Hello,\n\nThank you for contacting OmniDome. We have logged your request regarding "${thread.subject}" and our team is actively addressing it.\n\nRegards,\nOmniDome AI Assistant`

    const replyMsg: AgentMailMessage = {
      id: `reply-${Date.now()}`,
      threadId: thread.id,
      direction: "outbound",
      sender: currentMailbox.displayName,
      senderEmail: currentMailbox.emailAddress,
      recipient: thread.sender,
      recipientEmail: thread.senderEmail,
      subject: `Re: ${thread.subject}`,
      bodyText: replyBody,
      status: "auto_replied",
      createdAt: new Date().toISOString(),
    }

    setThreads((prev) =>
      prev.map((t) =>
        t.id === thread.id
          ? {
              ...t,
              messagesCount: t.messagesCount + 1,
              labels: Array.from(new Set([...t.labels, "Auto-Replied"])),
              messages: [...t.messages, replyMsg],
            }
          : t
      )
    )
    showNotification(`Auto Reply sent to ${thread.senderEmail} via AgentMail`)
  }

  const handleCreateTaskFromEmail = (thread: AgentMailThread) => {
    onCreateTask?.({
      title: `Follow-up: ${thread.subject} (${thread.sender})`,
      assignee: currentMailbox.assignedUser || "Sales Agent",
      priority: thread.aiAnalysis?.sentiment === "urgent" ? "high" : "medium",
      notes: `Generated from AgentMail thread ${thread.id}.\nSender: ${thread.senderEmail}\nSnippet: ${thread.snippet}`,
    })
    showNotification("Task created in Communication Tasks board")
  }

  const handleCreateApprovalFromEmail = (thread: AgentMailThread) => {
    onCreateApproval?.({
      subject: `Quote Approval: ${thread.subject}`,
      agent: "Sales Agent",
      amount: thread.aiAnalysis?.quoteAmount || "R 245,000",
      reason: thread.aiAnalysis?.notes || "Enterprise discount requested for lead",
    })
    showNotification("Approval request created in Communication Approvals")
  }

  const handleEscalateFromEmail = (thread: AgentMailThread) => {
    onCreateEscalation?.({
      title: `Email Escalation: ${thread.subject}`,
      severity: thread.aiAnalysis?.sentiment === "urgent" ? "high" : "medium",
      notes: `Escalated from AgentMail inbox ${currentMailbox.emailAddress}.\nFrom: ${thread.senderEmail}\nDetails: ${thread.snippet}`,
    })
    showNotification("Escalation logged in Communication Escalations")
  }

  return (
    <div className="flex h-full w-full bg-background text-foreground overflow-hidden select-none relative">
      {/* ── LIVE / DEMO STATUS ── */}
      <div className="absolute top-2 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 rounded-full border border-border bg-card/95 px-3 py-1 text-[11px] shadow">
        {demoMode ? (
          <Badge variant="outline" className="border-amber-500/50 text-amber-400">Demo data - not real email</Badge>
        ) : loading ? (
          <span className="text-muted-foreground">Loading mailboxes...</span>
        ) : loadError ? (
          <span className="text-red-400">Mail service error: {loadError}</span>
        ) : liveEmpty ? (
          <span className="text-muted-foreground">No mailboxes or emails yet. Configure the mail service or use Demo data.</span>
        ) : (
          <span className="text-emerald-400">Live</span>
        )}
        {!demoMode && !loading && (
          <button type="button" className="underline text-muted-foreground hover:text-foreground" onClick={() => void loadLive()}>
            Retry
          </button>
        )}
        <button
          type="button"
          className="underline text-muted-foreground hover:text-foreground"
          onClick={() => setDemoMode((v) => !v)}
        >
          {demoMode ? "Back to live" : "Demo data"}
        </button>
      </div>

      {/* ── NOTIFICATION TOAST ── */}
      {notificationMsg && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-2 rounded-lg bg-muted/50 border border-emerald-500/40 px-4 py-2.5 shadow-2xl text-emerald-300 text-xs font-medium animate-in fade-in slide-in-from-top-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          <span>{notificationMsg}</span>
        </div>
      )}

      {/* ── 1. PRIMARY NAVIGATION RAIL (Far Left - Matches Screenshot media_1790515130371.png) ── */}
      <div className="w-[210px] shrink-0 border-r border-border bg-card flex flex-col justify-between py-3 px-2">
        <div className="space-y-3">
          {/* Logo */}
          <div className="flex items-center gap-2.5 px-2 py-1">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-muted text-foreground shadow">
              <Bot className="h-4 w-4 text-foreground" />
            </div>
            <span className="font-semibold text-sm tracking-tight text-foreground">AgentMail</span>
          </div>

          {/* Org Card */}
          <div className="flex items-center gap-2.5 rounded-lg bg-muted/50 p-2 border border-border/60">
            <Avatar className="h-8 w-8 rounded-md bg-muted text-foreground font-bold text-xs">
              <AvatarFallback>B</AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-foreground truncate">Burni&apos;s Organization</p>
              <p className="text-[10px] text-muted-foreground">Free Tier</p>
            </div>
          </div>

          {/* Search or jump to... (Cmd+K) */}
          <button
            onClick={() => setActiveSideNav("inboxes")}
            className="flex w-full items-center justify-between rounded-lg bg-muted/50 hover:bg-muted/50 px-2.5 py-1.5 text-xs text-muted-foreground border border-border transition-colors"
          >
            <div className="flex items-center gap-2 truncate">
              <Search className="h-3.5 w-3.5 text-muted-foreground/75" />
              <span className="text-[11px]">Search or jump to...</span>
            </div>
            <kbd className="text-[9px] font-mono bg-muted px-1 py-0.5 rounded text-muted-foreground border border-border">
              ⌘K
            </kbd>
          </button>

          {/* Pod Selector (Multi-Tenant Architecture) */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex w-full items-center justify-between rounded-lg bg-muted/30 hover:bg-muted/50 px-2.5 py-1.5 text-xs text-foreground/80 border border-border transition-colors">
                <div className="flex items-center gap-2 truncate">
                  <Building className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                  <span className="truncate font-medium">{currentPod.name}</span>
                </div>
                <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-56 bg-muted/50 border-border text-foreground">
              <DropdownMenuLabel className="text-[11px] text-muted-foreground">Multi-Tenant Pods</DropdownMenuLabel>
              {pods.map((pod) => (
                <DropdownMenuItem
                  key={pod.id}
                  onClick={() => setSelectedPodId(pod.id)}
                  className={cn(
                    "flex items-center justify-between text-xs cursor-pointer",
                    pod.id === selectedPodId && "bg-muted font-semibold text-foreground"
                  )}
                >
                  <div className="flex items-center gap-2 truncate">
                    <Building className="h-3.5 w-3.5 text-muted-foreground" />
                    <span>{pod.name}</span>
                  </div>
                  {pod.isDefault && (
                    <Badge variant="outline" className="text-[9px] h-4 text-muted-foreground border-border">
                      Default
                    </Badge>
                  )}
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator className="bg-muted" />
              <DropdownMenuItem
                onClick={() => setCreatePodOpen(true)}
                className="text-xs text-emerald-400 cursor-pointer gap-2"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Create New Pod</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Primary Nav Options (Exact match: Overview, Inboxes, Metrics, Domains, Lists, Settings) */}
          <nav className="space-y-1 pt-1">
            {[
              { id: "overview", label: "Overview", icon: LayoutGrid },
              { id: "inboxes", label: "Inboxes", icon: Inbox },
              { id: "metrics", label: "Metrics", icon: BarChart3 },
              { id: "domains", label: "Domains", icon: Globe },
              { id: "lists", label: "Lists", icon: Shield },
              { id: "settings", label: "Settings", icon: Settings },
            ].map((item) => {
              const Icon = item.icon
              const isActive = activeSideNav === item.id
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    setActiveSideNav(item.id as any)
                    if (item.id === "inboxes") setSelectedThreadId(null)
                  }}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors",
                    isActive
                      ? "bg-primary/10 text-primary font-semibold shadow-xs"
                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                  )}
                >
                  <Icon className={cn("h-4 w-4", isActive ? "text-primary" : "text-muted-foreground")} />
                  <span>{item.label}</span>
                </button>
              )
            })}
          </nav>
        </div>

        {/* Bottom Section: Upgrade Pill, Help, and User Profile Footer (Exact match to screenshots) */}
        <div className="space-y-3 pt-2 border-t border-border/60">
          {/* Upgrade Pill Button */}
          <Button
            size="sm"
            className="w-full h-8 rounded-full bg-primary text-primary-foreground hover:bg-primary/90 font-semibold text-xs shadow-sm"
          >
            Upgrade
          </Button>

          {/* Help Link */}
          <button
            onClick={() => setApiDocsOpen(true)}
            className="flex w-full items-center gap-2 px-2 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <HelpCircle className="h-4 w-4 text-muted-foreground" />
            <span>Help & Docs</span>
          </button>

          {/* User Profile Footer (Burni Braai / burnibraa@gmail.com) */}
          <div className="flex items-center justify-between rounded-lg bg-muted/30 p-2 border border-border/60">
            <div className="flex items-center gap-2 min-w-0">
              <Avatar className="h-7 w-7 rounded-full bg-muted text-foreground font-bold text-xs">
                <AvatarFallback>B</AvatarFallback>
              </Avatar>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-foreground truncate leading-tight">Burni Braai</p>
                <p className="text-[10px] text-muted-foreground truncate leading-tight">burnibraa@gmail.com</p>
              </div>
            </div>
            <MoreVertical className="h-3.5 w-3.5 text-muted-foreground/75 shrink-0" />
          </div>
        </div>
      </div>

      {/* ── 2. SECONDARY INBOXES SIDEBAR (When Inboxes is active) ── */}
      {activeSideNav === "inboxes" && (
        <div className="w-[220px] shrink-0 border-r border-border bg-card flex flex-col justify-between py-3 px-2 overflow-y-auto">
          <div className="space-y-3">
            {/* Compose Button */}
            <Button
              onClick={() => setComposeOpen(true)}
              className="w-full h-9 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 font-medium text-xs flex items-center justify-start gap-2 px-3 shadow-xs"
            >
              <Plus className="h-3.5 w-3.5 stroke-[2.5]" />
              <span>Compose</span>
            </Button>

            {/* Inboxes Selector Dropdown */}
            <div className="px-1">
              <div className="flex items-center justify-between">
                <label className="text-[10px] font-semibold uppercase text-muted-foreground/75 tracking-wider">
                  Active Inbox
                </label>
                <button
                  onClick={() => setCreateInboxOpen(true)}
                  className="text-[10px] text-muted-foreground hover:text-foreground"
                  title="Create Inbox"
                >
                  <Plus className="h-3 w-3" />
                </button>
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="mt-1 flex w-full items-center justify-between rounded-md bg-muted/50 hover:bg-muted/60 px-2 py-1.5 text-xs text-foreground border border-border transition-colors">
                    <span className="truncate text-left font-mono text-[11px]">
                      {currentMailbox.emailAddress}
                    </span>
                    <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0 ml-1" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-64 bg-muted/50 border-border text-foreground">
                  <DropdownMenuLabel className="text-[11px] text-muted-foreground">
                    Inboxes in {currentPod.name}
                  </DropdownMenuLabel>
                  {mailboxes.map((mb) => (
                    <DropdownMenuItem
                      key={mb.id}
                      onClick={() => {
                        setSelectedMailboxId(mb.id)
                        setSelectedGroupId(null)
                        setSelectedThreadId(null)
                      }}
                      className={cn(
                        "flex flex-col items-start py-1.5 text-xs cursor-pointer",
                        mb.id === selectedMailboxId && "bg-muted text-foreground"
                      )}
                    >
                      <div className="flex items-center justify-between w-full">
                        <span className="font-medium truncate">{mb.displayName}</span>
                        {mb.isHuman ? (
                          <Badge variant="outline" className="text-[9px] h-3.5 text-muted-foreground border-border">
                            Human
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="text-[9px] h-3.5 bg-cyan-950 text-cyan-300">
                            AI Agent
                          </Badge>
                        )}
                      </div>
                      <span className="font-mono text-[10px] text-muted-foreground truncate w-full">
                        {mb.emailAddress}
                      </span>
                    </DropdownMenuItem>
                  ))}
                  <DropdownMenuSeparator className="bg-muted" />
                  <DropdownMenuItem
                    onClick={() => setCreateInboxOpen(true)}
                    className="text-xs text-emerald-400 cursor-pointer gap-2"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Create New Inbox</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            {/* Folders (Matching screenshot: Inbox, Sent, Drafts, Scheduled, All Mail, Trash, Other) */}
            <div className="space-y-0.5">
              {[
                { id: "inbox", label: "Inbox", icon: Inbox, badge: currentMailbox.unreadCount },
                { id: "sent", label: "Sent", icon: Send },
                { id: "drafts", label: "Drafts", icon: FileText },
                { id: "scheduled", label: "Scheduled", icon: Clock },
                { id: "all", label: "All Mail", icon: Layers },
                { id: "trash", label: "Trash", icon: Trash2 },
                { id: "other", label: "Other", icon: Folder, hasChevron: true },
              ].map((folder) => {
                const Icon = folder.icon
                const isActive = activeFolder === folder.id
                return (
                  <button
                    key={folder.id}
                    onClick={() => {
                      setActiveFolder(folder.id as any)
                      setSelectedThreadId(null)
                    }}
                    className={cn(
                      "flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-xs transition-colors",
                      isActive
                        ? "bg-muted/50 text-foreground font-medium"
                        : "text-muted-foreground hover:bg-muted/40 hover:text-foreground"
                    )}
                  >
                    <div className="flex items-center gap-2.5 truncate">
                      <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                      <span>{folder.label}</span>
                    </div>
                    {folder.badge && folder.badge > 0 ? (
                      <Badge className="h-4 min-w-4 rounded-full bg-muted px-1 text-[10px] text-foreground/80">
                        {folder.badge}
                      </Badge>
                    ) : folder.hasChevron ? (
                      <ChevronRight className="h-3 w-3 text-muted-foreground/75" />
                    ) : null}
                  </button>
                )
              })}
            </div>

            {/* SHARED MAILBOXES & GROUPS (Requirement: Visibility of shared groups & mailboxes added to) */}
            <div className="border-t border-border/80 pt-2 space-y-1">
              <div className="flex items-center justify-between px-2 py-1">
                <span className="text-[10px] font-semibold uppercase text-muted-foreground/75 tracking-wider">
                  Shared Groups & Mailboxes
                </span>
                <button
                  onClick={() => setCreateGroupOpen(true)}
                  className="text-muted-foreground/75 hover:text-foreground"
                  title="Add to new shared group"
                >
                  <Plus className="h-3 w-3" />
                </button>
              </div>

              <div className="space-y-0.5">
                {sharedGroups.map((group) => {
                  const isSelected = selectedGroupId === group.id || selectedMailboxId === group.mailboxId
                  return (
                    <button
                      key={group.id}
                      onClick={() => {
                        setSelectedGroupId(group.id)
                        setSelectedMailboxId(group.mailboxId)
                        setSelectedThreadId(null)
                      }}
                      className={cn(
                        "flex w-full flex-col rounded-md px-2.5 py-1.5 text-xs transition-colors text-left",
                        isSelected
                          ? "bg-muted/50 text-foreground font-medium border border-border"
                          : "text-muted-foreground hover:bg-muted/40 hover:text-foreground"
                      )}
                    >
                      <div className="flex items-center justify-between w-full">
                        <div className="flex items-center gap-1.5 truncate">
                          <Users className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
                          <span className="truncate">{group.name}</span>
                        </div>
                        {group.unreadCount > 0 && (
                          <Badge className="h-4 min-w-4 rounded-full bg-cyan-950 text-cyan-300 px-1 text-[9px]">
                            {group.unreadCount}
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-muted-foreground/75 mt-0.5 pl-5">
                        <span className="font-mono truncate">{group.emailAddress}</span>
                        <span className="shrink-0 text-muted-foreground">👥 {group.members.length}</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="border-t border-border/80 pt-2">
              <button
                onClick={() => setActiveSideNav("lists")}
                className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-muted/40 hover:text-foreground"
              >
                <Shield className="h-3.5 w-3.5 text-muted-foreground" />
                <span>Allow/Block Lists</span>
              </button>
            </div>
          </div>

          {/* Group / Agent Capabilities Button */}
          <div className="pt-2 border-t border-border/60">
            <button
              onClick={() => setCapabilitiesDrawerOpen(true)}
              className="w-full flex items-center justify-between rounded-lg bg-muted/60 hover:bg-muted/50 p-2 border border-border/80 text-left transition-colors"
            >
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-cyan-400 shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-foreground">Group Capabilities</p>
                  <p className="text-[10px] text-muted-foreground">Pods, Drafts & Orchestrator</p>
                </div>
              </div>
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/75" />
            </button>
          </div>
        </div>
      )}

      {/* ── 3. MAIN WORKSPACE / INBOX / THREAD READER ── */}
      <div className="flex-1 flex flex-col min-w-0 bg-background overflow-hidden">
        {/* VIEW 1: INBOXES VIEW */}
        {activeSideNav === "inboxes" && !selectedThreadId && (
          <div className="flex-1 flex flex-col min-h-0">
            {/* Top Header Bar with Theme Toggle */}
            <div className="h-12 border-b border-border/80 px-4 flex items-center justify-between shrink-0 bg-background">
              {/* Breadcrumbs */}
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <button onClick={() => setActiveSideNav("overview")} className="hover:text-foreground">
                  Dashboard
                </button>
                <span>&gt;</span>
                <span className="hover:text-foreground">Inboxes</span>
                <span>&gt;</span>
                <div className="flex items-center gap-1.5 text-foreground font-mono font-medium">
                  <span>{currentMailbox.emailAddress}</span>
                  <button
                    onClick={() => handleCopyEmail()}
                    className="p-1 text-muted-foreground hover:text-foreground transition-colors"
                    title="Copy address"
                  >
                    {copiedEmail ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                  </button>
                </div>
                {currentSharedGroup && (
                  <Badge variant="outline" className="text-[10px] h-4 bg-cyan-950/40 text-cyan-300 border-cyan-800">
                    Shared Group
                  </Badge>
                )}
              </div>

              {/* Top Right: Search, Capabilities, Theme Toggle */}
              <div className="flex items-center gap-2.5">
                <div className="relative w-64">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/75" />
                  <Input
                    placeholder="Search mail"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="h-8 pl-8 bg-muted/50 border-border text-xs text-foreground placeholder:text-muted-foreground/75 focus-visible:ring-neutral-700"
                  />
                  {searchQuery && (
                    <button
                      onClick={() => setSearchQuery("")}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground/75 hover:text-foreground"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}
                </div>

                {currentSharedGroup && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setManageGroupModalOpen(true)}
                    className="h-8 text-xs border-border text-foreground hover:bg-muted/50 gap-1.5"
                  >
                    <UserPlus className="h-3.5 w-3.5 text-cyan-400" />
                    <span>Members ({currentSharedGroup.members.length})</span>
                  </Button>
                )}

                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setCapabilitiesDrawerOpen(true)}
                  className="h-8 text-xs border-border text-foreground hover:bg-muted/50 gap-1.5"
                >
                  <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
                  <span>Capabilities</span>
                </Button>

                {/* Page Dark Mode / Theme Toggle (RESTORED) */}
                <div className="border-l border-border pl-2">
                  <ThemeToggleCompact />
                </div>
              </div>
            </div>

            {/* Action Bar (Checkbox, Refresh, Labels, Threads count, Pagination) */}
            <div className="h-10 border-b border-border/80 px-4 flex items-center justify-between shrink-0 bg-background">
              <div className="flex items-center gap-3">
                {/* Select All */}
                <input
                  type="checkbox"
                  checked={
                    currentThreads.length > 0 && selectedThreadIds.size === currentThreads.length
                  }
                  onChange={toggleSelectAll}
                  className="rounded border-border bg-muted/50 text-primary focus:ring-0 cursor-pointer"
                />

                {/* Refresh */}
                <button
                  onClick={handleRefresh}
                  className="text-muted-foreground hover:text-foreground transition-colors"
                  title="Refresh"
                >
                  <RotateCw className={cn("h-3.5 w-3.5", isRefreshing && "animate-spin text-cyan-400")} />
                </button>

                {/* Labels Dropdown */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button className="flex items-center gap-1 text-xs text-foreground/80 hover:text-foreground">
                      <span>{selectedLabelFilter || "Labels"}</span>
                      <ChevronDown className="h-3 w-3 text-muted-foreground/75" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="bg-muted/50 border-border text-foreground">
                    <DropdownMenuItem
                      onClick={() => setSelectedLabelFilter(null)}
                      className="text-xs cursor-pointer"
                    >
                      All Labels
                    </DropdownMenuItem>
                    <DropdownMenuSeparator className="bg-muted" />
                    {labels.map((l) => (
                      <DropdownMenuItem
                        key={l.id}
                        onClick={() => setSelectedLabelFilter(l.name)}
                        className="text-xs cursor-pointer flex items-center justify-between"
                      >
                        <span>{l.name}</span>
                        <Badge variant="outline" className="text-[9px] h-3.5 text-muted-foreground border-border">
                          {l.count}
                        </Badge>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>

                {selectedThreadIds.size > 0 && (
                  <div className="flex items-center gap-2 pl-2 border-l border-border">
                    <button
                      onClick={() => void deleteSelectedLive()}
                      className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      <span>Delete ({selectedThreadIds.size})</span>
                    </button>
                  </div>
                )}
              </div>

              {/* Right side stats: 1–N of N */}
              <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
                <span>
                  {currentThreads.length > 0 ? `1–${currentThreads.length} of ${currentThreads.length}` : "0 threads"}
                </span>
              </div>
            </div>

            {/* Thread Rows */}
            <ScrollArea className="flex-1 min-h-0 bg-background">
              {currentThreads.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-12 text-center text-muted-foreground/75">
                  <Inbox className="h-10 w-10 stroke-[1.2] text-neutral-600 mb-2" />
                  <p className="text-sm font-medium text-muted-foreground">No emails found in this mailbox</p>
                  <p className="text-xs text-muted-foreground/75 mt-1">
                    Send an email to <span className="font-mono text-foreground/80">{currentMailbox.emailAddress}</span>
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-border">
                  {currentThreads.map((thread) => {
                    const isSelected = selectedThreadIds.has(thread.id)
                    const isBounce = thread.labels.includes("Bounced") || thread.labels.includes("System Bounce")
                    return (
                      <div
                        key={thread.id}
                        onClick={() => openThreadLive(thread)}
                        className={cn(
                          "group flex items-center gap-3 px-4 py-2.5 hover:bg-muted/50 cursor-pointer transition-colors text-xs",
                          thread.unread ? "font-semibold text-foreground bg-card/40" : "text-foreground/80",
                          isSelected && "bg-muted/50/90"
                        )}
                      >
                        {/* Checkbox */}
                        <div
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleSelectThread(thread.id)
                          }}
                          className="shrink-0"
                        >
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => {}}
                            className="rounded border-border bg-muted/50 text-primary focus:ring-0 cursor-pointer"
                          />
                        </div>

                        {/* Star */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            void toggleStarLive(thread)
                          }}
                          className="text-neutral-600 hover:text-amber-400 transition-colors shrink-0"
                        >
                          <Star className={cn("h-3.5 w-3.5", thread.isStarred && "fill-amber-400 text-amber-400")} />
                        </button>

                        {/* Sender */}
                        <div className="w-48 shrink-0 truncate flex items-center gap-2">
                          {isBounce ? (
                            <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                          ) : (
                            <Avatar className="h-5 w-5 rounded-full bg-muted text-[10px] text-foreground/80 font-semibold shrink-0">
                              <AvatarFallback>{thread.sender.slice(0, 1)}</AvatarFallback>
                            </Avatar>
                          )}
                          <span className="truncate">{thread.sender}</span>
                        </div>

                        {/* Subject + Snippet + Labels */}
                        <div className="flex-1 min-w-0 flex items-center gap-2 truncate">
                          <span className="text-foreground truncate font-medium">{thread.subject}</span>
                          <span className="text-muted-foreground/75 shrink-0">-</span>
                          <span className="text-muted-foreground truncate font-normal">{thread.snippet}</span>
                          {thread.labels.slice(0, 2).map((label) => (
                            <Badge
                              key={label}
                              variant="outline"
                              className="text-[9px] h-4 shrink-0 bg-muted/70 text-foreground/80 border-border"
                            >
                              {label}
                            </Badge>
                          ))}
                        </div>

                        {/* Attachments Icon */}
                        {thread.hasAttachments && (
                          <Paperclip className="h-3.5 w-3.5 text-muted-foreground/75 shrink-0" />
                        )}

                        {/* Date / Timestamp */}
                        <div className="w-20 shrink-0 text-right text-muted-foreground font-mono text-[11px]">
                          {thread.timestamp}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </ScrollArea>
          </div>
        )}

        {/* VIEW 2: THREAD DETAIL / CONVERSATION INSPECTOR */}
        {activeSideNav === "inboxes" && activeThread && (
          <div className="flex-1 flex flex-col min-h-0 bg-background">
            {/* Thread Header Bar */}
            <div className="h-12 border-b border-border/80 px-4 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setSelectedThreadId(null)}
                  className="h-8 text-muted-foreground hover:text-foreground gap-1 px-2"
                >
                  <ArrowLeft className="h-4 w-4" />
                  <span>Back to Inboxes</span>
                </Button>
                <div className="h-4 w-[1px] bg-muted" />
                <h2 className="text-sm font-semibold text-foreground truncate max-w-md">
                  {activeThread.subject}
                </h2>
              </div>

              <div className="flex items-center gap-2">
                <ThemeToggleCompact />
                {demoMode ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleAutoReply(activeThread)}
                    className="h-8 text-xs border-border text-foreground hover:bg-muted/50 gap-1.5"
                  >
                    <Bot className="h-3.5 w-3.5 text-cyan-400" />
                    <span>Agent Auto-Reply</span>
                  </Button>
                ) : (
                  activeThread.messages.some(
                    (m) => m.direction === "inbound" && m.agentResponse && m.status !== "auto_replied"
                  ) && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={replyBusy}
                      onClick={() => void handleApproveAgentReply(activeThread)}
                      className="h-8 text-xs border-border text-foreground hover:bg-muted/50 gap-1.5"
                    >
                      <Bot className="h-3.5 w-3.5 text-cyan-400" />
                      <span>{replyBusy ? "Sending..." : "Approve & send agent reply"}</span>
                    </Button>
                  )
                )}
              </div>
            </div>

            {!demoMode && activeThread.messages.some((m) => m.direction === "inbound") && (
              <div className="flex items-center gap-2 border-b border-border px-4 py-2">
                <input
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault()
                      void handleSendReplyLive(activeThread)
                    }
                  }}
                  placeholder="Write a reply to the sender..."
                  className="h-8 flex-1 rounded border border-border bg-background px-2 text-xs"
                />
                <Button
                  size="sm"
                  disabled={replyBusy || !replyText.trim()}
                  onClick={() => void handleSendReplyLive(activeThread)}
                  className="h-8 text-xs"
                >
                  <Send className="h-3.5 w-3.5 mr-1" />
                  {replyBusy ? "Sending..." : "Reply"}
                </Button>
                {replyError && <span className="text-xs text-red-400">{replyError}</span>}
              </div>
            )}

            {/* Thread Content */}
            <div className="flex-1 flex min-h-0">
              <ScrollArea className="flex-1 min-h-0 p-6 space-y-6">
                <div className="max-w-3xl mx-auto space-y-6">
                  {activeThread.messages.map((message) => {
                    const isInbound = message.direction === "inbound"
                    return (
                      <div
                        key={message.id}
                        className={cn(
                          "rounded-xl border p-5 space-y-4",
                          isInbound
                            ? "bg-card border-border"
                            : "bg-muted/50 border-border/80"
                        )}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <Avatar className="h-8 w-8 rounded-full bg-muted text-xs font-bold text-foreground">
                              <AvatarFallback>{message.sender.slice(0, 2).toUpperCase()}</AvatarFallback>
                            </Avatar>
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-semibold text-xs text-foreground">{message.sender}</span>
                                <span className="text-[11px] font-mono text-muted-foreground/75">
                                  &lt;{message.senderEmail}&gt;
                                </span>
                              </div>
                              <p className="text-[11px] text-muted-foreground">
                                To: {message.recipientEmail} &bull; {message.createdAt.slice(0, 16).replace("T", " ")}
                              </p>
                            </div>
                          </div>
                          <Badge
                            variant="outline"
                            className={cn(
                              "text-[10px] h-4 capitalize",
                              isInbound ? "border-cyan-800 text-cyan-300" : "border-emerald-800 text-emerald-300"
                            )}
                          >
                            {message.direction}
                          </Badge>
                        </div>

                        <div className="text-xs text-foreground font-sans leading-relaxed whitespace-pre-wrap">
                          {message.bodyText}
                        </div>

                        {/* Attachments */}
                        {message.attachments && message.attachments.length > 0 && (
                          <div className="pt-2 border-t border-border/80 space-y-2">
                            <span className="text-[10px] font-semibold uppercase text-muted-foreground/75">Attachments</span>
                            <div className="flex flex-wrap gap-2">
                              {message.attachments.map((att) => (
                                <div
                                  key={att.id}
                                  className="flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-1.5 border border-border text-xs"
                                >
                                  <FileText className="h-3.5 w-3.5 text-cyan-400" />
                                  <span className="text-foreground font-medium">{att.filename}</span>
                                  <span className="text-[10px] text-muted-foreground/75 font-mono">
                                    ({Math.round(att.sizeBytes / 1024)} KB)
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </ScrollArea>

              {/* Right Side: Orchestrator AI Insights & Actions Panel */}
              <div className="w-80 shrink-0 border-l border-border/80 bg-card p-4 space-y-5 overflow-y-auto">
                <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                  <Sparkles className="h-4 w-4 text-cyan-400" />
                  <span>Orchestrator AI Analysis</span>
                </div>

                {activeThread.aiAnalysis && (
                  <div className="space-y-3 text-xs">
                    <div className="rounded-lg bg-muted/50 border border-border p-3 space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">Category</span>
                        <Badge variant="outline" className="text-[10px] border-cyan-800 text-cyan-300">
                          {activeThread.aiAnalysis.category}
                        </Badge>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">Sentiment</span>
                        <span className="capitalize font-medium text-foreground">
                          {activeThread.aiAnalysis.sentiment}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">Confidence</span>
                        <span className="font-mono text-emerald-400">
                          {Math.round(activeThread.aiAnalysis.confidence * 100)}%
                        </span>
                      </div>
                      {activeThread.aiAnalysis.quoteAmount && (
                        <div className="flex justify-between items-center pt-1 border-t border-border">
                          <span className="text-muted-foreground">Estimated Value</span>
                          <span className="font-mono font-bold text-emerald-400">
                            {activeThread.aiAnalysis.quoteAmount}
                          </span>
                        </div>
                      )}
                    </div>

                    {activeThread.aiAnalysis.notes && (
                      <p className="text-[11px] text-muted-foreground bg-muted/30 p-2.5 rounded-lg border border-border/60 leading-relaxed">
                        {activeThread.aiAnalysis.notes}
                      </p>
                    )}
                  </div>
                )}

                {/* Orchestrator Quick Actions */}
                <div className="space-y-2 pt-2 border-t border-border/80">
                  <span className="text-[10px] font-semibold uppercase text-muted-foreground/75 tracking-wider">
                    Orchestrator Pipeline Actions
                  </span>

                  <div className="space-y-1.5">
                    <button
                      onClick={() => handleCreateTaskFromEmail(activeThread)}
                      className="w-full flex items-center justify-between rounded-lg bg-muted/50 hover:bg-muted/60 p-2.5 border border-border text-xs text-left transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                        <div>
                          <p className="font-medium text-foreground">Convert to Task</p>
                          <p className="text-[10px] text-muted-foreground/75">Assigns to Communication board</p>
                        </div>
                      </div>
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/75" />
                    </button>

                    <button
                      onClick={() => handleCreateApprovalFromEmail(activeThread)}
                      className="w-full flex items-center justify-between rounded-lg bg-muted/50 hover:bg-muted/60 p-2.5 border border-border text-xs text-left transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <Shield className="h-4 w-4 text-amber-400" />
                        <div>
                          <p className="font-medium text-foreground">Request Quote Approval</p>
                          <p className="text-[10px] text-muted-foreground/75">Syncs to Approvals board</p>
                        </div>
                      </div>
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/75" />
                    </button>

                    <button
                      onClick={() => handleEscalateFromEmail(activeThread)}
                      className="w-full flex items-center justify-between rounded-lg bg-muted/50 hover:bg-muted/60 p-2.5 border border-border text-xs text-left transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <AlertCircle className="h-4 w-4 text-red-400" />
                        <div>
                          <p className="font-medium text-foreground">Escalate to Supervisor</p>
                          <p className="text-[10px] text-muted-foreground/75">Triggers incident SLA alert</p>
                        </div>
                      </div>
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/75" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* VIEW 3: OVERVIEW VIEW (EXACT MATCH TO media_1790515130371.png) */}
        {activeSideNav === "overview" && (
          <ScrollArea className="flex-1 min-h-0 bg-background">
            <div className="max-w-6xl mx-auto p-6 space-y-6">
              {/* Header Bar with Theme Toggle */}
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-xl font-bold text-foreground tracking-tight">Overview</h1>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Platform status, deliverability metrics, and recent conversations
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <ThemeToggleCompact />
                  <Button
                    size="sm"
                    onClick={() => setActiveSideNav("inboxes")}
                    className="h-8 text-xs bg-primary text-primary-foreground hover:bg-foreground/80 font-semibold"
                  >
                    Open Inboxes
                  </Button>
                </div>
              </div>

              {/* Top 3 Action Banner Cards (Exact Match to screenshot media_1790515130371.png) */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {/* Banner 1: AgentID beta */}
                <div className="rounded-xl border border-border bg-card p-4 flex flex-col justify-between space-y-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-xs text-foreground">Sign in with AgentID</span>
                      <Badge className="text-[9px] h-3.5 bg-muted text-foreground/80">beta</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      AgentID lets your agents sign into websites like Domecrawl, Keenetic, and Turso. Let them build without giving up your password.
                    </p>
                  </div>
                  <button
                    onClick={() => showNotification("AgentID beta credentials active for Domecrawl MCP")}
                    className="text-xs text-foreground hover:underline flex items-center gap-1 font-medium"
                  >
                    <span>Explore AgentID</span>
                    <ArrowRight className="h-3 w-3" />
                  </button>
                </div>

                {/* Banner 2: Send and receive emails */}
                <div className="rounded-xl border border-border bg-card p-4 flex flex-col justify-between space-y-3">
                  <div>
                    <span className="font-semibold text-xs text-foreground">Send and receive emails</span>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      Use webhooks to receive incoming emails and our API to send. Check out the docs to get started.
                    </p>
                  </div>
                  <button
                    onClick={() => setApiDocsOpen(true)}
                    className="text-xs text-foreground hover:underline flex items-center gap-1 font-medium"
                  >
                    <span>Read the docs</span>
                    <ArrowRight className="h-3 w-3" />
                  </button>
                </div>

                {/* Banner 3: Use your own domain */}
                <div className="rounded-xl border border-border bg-card p-4 flex flex-col justify-between space-y-3">
                  <div>
                    <span className="font-semibold text-xs text-foreground">Use your own domain</span>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      Send and receive emails from your own domain like info@omnidome.co.za or sales@omnidome.co.za.
                    </p>
                  </div>
                  <button
                    onClick={() => setActiveSideNav("domains")}
                    className="text-xs text-foreground hover:underline flex items-center gap-1 font-medium"
                  >
                    <span>Set up a domain</span>
                    <ArrowRight className="h-3 w-3" />
                  </button>
                </div>
              </div>

              {/* Greeting & Time Range Bar (Exact match to screenshot) */}
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pt-2">
                <h2 className="text-lg font-bold text-foreground tracking-tight">Back for another look, Burni?</h2>
                <div className="flex items-center gap-1 bg-muted/50 rounded-lg p-1 border border-border text-xs">
                  {(["24 hours", "7 days", "30 days", "Custom"] as const).map((r) => {
                    const val = r === "24 hours" ? "24h" : r === "7 days" ? "7d" : r === "30 days" ? "30d" : "custom"
                    const isSelected = overviewTimeRange === val
                    return (
                      <button
                        key={r}
                        onClick={() => setOverviewTimeRange(val)}
                        className={cn(
                          "px-3 py-1 rounded-md text-xs font-medium transition-colors",
                          isSelected
                            ? "bg-primary text-primary-foreground shadow font-semibold"
                            : "text-muted-foreground hover:text-foreground"
                        )}
                      >
                        {r}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* 5 Stats Cards Row (Sent: 22, Received: 33, Bounced: 3, Rejected: 0, Complained: 0) */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <div className="rounded-xl border border-border bg-card p-4">
                  <p className="text-xs text-muted-foreground">Sent</p>
                  <p className="text-2xl font-bold text-foreground mt-1">{metrics.sentCount}</p>
                </div>
                <div className="rounded-xl border border-border bg-card p-4">
                  <p className="text-xs text-muted-foreground">Received</p>
                  <p className="text-2xl font-bold text-foreground mt-1">{metrics.receivedCount}</p>
                </div>
                <div className="rounded-xl border border-border bg-card p-4">
                  <p className="text-xs text-muted-foreground">Bounced</p>
                  <p className="text-2xl font-bold text-foreground mt-1">{metrics.bouncedCount}</p>
                </div>
                <div className="rounded-xl border border-border bg-card p-4">
                  <p className="text-xs text-muted-foreground">Rejected</p>
                  <p className="text-2xl font-bold text-foreground mt-1">{metrics.rejectedCount}</p>
                </div>
                <div className="rounded-xl border border-border bg-card p-4">
                  <p className="text-xs text-muted-foreground">Complained</p>
                  <p className="text-2xl font-bold text-foreground mt-1">{metrics.complainedCount}</p>
                </div>
              </div>

              {/* Line Chart Card (Sent vs Received from Aug 29 to Sep 27) */}
              <div className="rounded-xl border border-border bg-card p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4 text-xs">
                    <div className="flex items-center gap-1.5">
                      <span className="h-2.5 w-2.5 rounded-full bg-purple-500" />
                      <span className="text-foreground/80">Sent</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="h-2.5 w-2.5 rounded-full bg-blue-500" />
                      <span className="text-foreground/80">Received</span>
                    </div>
                  </div>
                  <span className="text-[11px] text-muted-foreground/75 font-mono">Aug 29 – Sep 27, 2026</span>
                </div>

                {/* Visual Chart representation */}
                <div className="h-44 w-full flex items-end gap-2 pt-4 px-2 border-b border-border">
                  {metrics.activityMatrix.map((item, idx) => {
                    const h1 = Math.min(100, item.count * 12 + 6)
                    const h2 = Math.min(100, Math.floor(item.count * 8 + 4))
                    return (
                      <div key={idx} className="flex-1 flex flex-col items-center gap-1 group relative">
                        <div className="w-full flex items-end justify-center gap-0.5 h-32">
                          <div
                            className="w-1.5 bg-purple-500/80 rounded-t group-hover:bg-purple-400 transition-colors"
                            style={{ height: `${h1}%` }}
                            title={`${item.date} - Sent: ${item.count}`}
                          />
                          <div
                            className="w-1.5 bg-blue-500/80 rounded-t group-hover:bg-blue-400 transition-colors"
                            style={{ height: `${h2}%` }}
                            title={`${item.date} - Received: ${item.count}`}
                          />
                        </div>
                        {idx % 5 === 0 && (
                          <span className="text-[9px] text-muted-foreground/75 font-mono whitespace-nowrap">
                            {item.date}
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Bottom 2-Column Section (Left: Latest Conversations, Right: Delivery Health, Resources, Needs Attention) */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left 2 Cols: Latest Conversations (Exact match to screenshot) */}
                <div className="lg:col-span-2 rounded-xl border border-border bg-card p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-foreground">Latest Conversations</h3>
                    <button
                      onClick={() => setActiveSideNav("inboxes")}
                      className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                    >
                      <span>View all</span>
                      <ArrowRight className="h-3 w-3" />
                    </button>
                  </div>

                  <div className="divide-y divide-border text-xs">
                    {/* Row 1: Alex Nurzi */}
                    <div
                      onClick={() => {
                        setActiveSideNav("inboxes")
                        setSelectedThreadId("thread-alex-nurzi")
                      }}
                      className="py-3 flex items-center justify-between hover:bg-muted/40 px-2 rounded-lg cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <Avatar className="h-7 w-7 rounded-full bg-muted text-xs text-foreground">
                          <AvatarFallback>AN</AvatarFallback>
                        </Avatar>
                        <div className="min-w-0">
                          <p className="font-semibold text-foreground truncate">Alex Nurzi</p>
                          <p className="text-muted-foreground truncate">Get the most out of Domecrawl</p>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-[11px] font-mono text-muted-foreground">burnibraa@agentmail.to</p>
                        <p className="text-[10px] text-muted-foreground/75">Sep 27, 2:56 AM</p>
                      </div>
                    </div>

                    {/* Row 2: Benedict Majozi */}
                    <div
                      onClick={() => {
                        setActiveSideNav("inboxes")
                        setSelectedThreadId("thread-benedict-test")
                      }}
                      className="py-3 flex items-center justify-between hover:bg-muted/40 px-2 rounded-lg cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <Avatar className="h-7 w-7 rounded-full bg-muted text-xs text-foreground">
                          <AvatarFallback>BM</AvatarFallback>
                        </Avatar>
                        <div className="min-w-0">
                          <p className="font-semibold text-foreground truncate">Benedict Majozi</p>
                          <p className="text-muted-foreground truncate">Test</p>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-[11px] font-mono text-muted-foreground">burnibraa@agentmail.to</p>
                        <p className="text-[10px] text-muted-foreground/75">Sep 7, 7:39 AM</p>
                      </div>
                    </div>

                    {/* Row 3: mailer-daemon failure 1 */}
                    <div
                      onClick={() => {
                        setActiveSideNav("inboxes")
                        setSelectedThreadId("thread-bounce-1")
                      }}
                      className="py-3 flex items-center justify-between hover:bg-muted/40 px-2 rounded-lg cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="h-7 w-7 rounded-full bg-amber-500/10 text-amber-400 flex items-center justify-center shrink-0">
                          <AlertTriangle className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <p className="font-semibold text-foreground truncate">mailer-daemon@agentmail.to</p>
                          <p className="text-muted-foreground truncate">Delivery Status Notification (Failure)</p>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-[11px] font-mono text-muted-foreground">burnibraa@agentmail.to</p>
                        <p className="text-[10px] text-muted-foreground/75">Aug 29, 7:16 PM</p>
                      </div>
                    </div>

                    {/* Row 4: mailer-daemon failure 2 */}
                    <div
                      onClick={() => {
                        setActiveSideNav("inboxes")
                        setSelectedThreadId("thread-bounce-2")
                      }}
                      className="py-3 flex items-center justify-between hover:bg-muted/40 px-2 rounded-lg cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="h-7 w-7 rounded-full bg-amber-500/10 text-amber-400 flex items-center justify-center shrink-0">
                          <AlertTriangle className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <p className="font-semibold text-foreground truncate">mailer-daemon@agentmail.to</p>
                          <p className="text-muted-foreground truncate">Delivery Status Notification (Failure)</p>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-[11px] font-mono text-muted-foreground">burnibraa@agentmail.to</p>
                        <p className="text-[10px] text-muted-foreground/75">Aug 29, 7:15 PM</p>
                      </div>
                    </div>

                    {/* Row 5: mailer-daemon failure 3 */}
                    <div
                      onClick={() => {
                        setActiveSideNav("inboxes")
                        setSelectedThreadId("thread-bounce-3")
                      }}
                      className="py-3 flex items-center justify-between hover:bg-muted/40 px-2 rounded-lg cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="h-7 w-7 rounded-full bg-amber-500/10 text-amber-400 flex items-center justify-center shrink-0">
                          <AlertTriangle className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <p className="font-semibold text-foreground truncate">mailer-daemon@agentmail.to</p>
                          <p className="text-muted-foreground truncate">Delivery Status Notification (Failure)</p>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-[11px] font-mono text-muted-foreground">burnibraa@agentmail.to</p>
                        <p className="text-[10px] text-muted-foreground/75">Aug 29, 7:15 PM</p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right 1 Col: Delivery Health, Resources, Needs Attention */}
                <div className="space-y-4">
                  {/* Delivery Health Card */}
                  <div className="rounded-xl border border-border bg-card p-5 space-y-4">
                    <h3 className="text-sm font-semibold text-foreground">Delivery Health</h3>
                    <div className="space-y-3 text-xs">
                      <div>
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">Bounce Rate</span>
                          <span className="font-bold text-amber-400">12%</span>
                        </div>
                        <div className="h-1.5 w-full bg-muted rounded-full mt-1.5 overflow-hidden">
                          <div className="h-full bg-amber-500 rounded-full" style={{ width: "12%" }} />
                        </div>
                      </div>
                      <div>
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">Complaint Rate</span>
                          <span className="font-bold text-emerald-400">0%</span>
                        </div>
                        <div className="h-1.5 w-full bg-muted rounded-full mt-1.5 overflow-hidden">
                          <div className="h-full bg-emerald-500 rounded-full" style={{ width: "0%" }} />
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Resources Card */}
                  <div className="rounded-xl border border-border bg-card p-5 space-y-4">
                    <h3 className="text-sm font-semibold text-foreground">Resources</h3>
                    <div className="space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Inboxes</span>
                        <span className="font-mono text-foreground font-medium">3 / 4</span>
                      </div>
                      <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                        <div className="h-full bg-white rounded-full" style={{ width: "75%" }} />
                      </div>
                    </div>
                  </div>

                  {/* Needs Attention Card */}
                  <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 space-y-2">
                    <div className="flex items-center gap-2 text-amber-400 text-xs font-semibold">
                      <AlertTriangle className="h-4 w-4" />
                      <span>Needs Attention</span>
                    </div>
                    <p className="text-xs text-foreground/80 leading-relaxed">
                      High bounce rate detected (12%) from previous outbound attempts. Address <span className="font-mono text-foreground">majozippe@gmail.com</span> has been isolated in the Block List.
                    </p>
                    <button
                      onClick={() => setActiveSideNav("lists")}
                      className="text-xs text-amber-400 hover:underline font-medium inline-block pt-1"
                    >
                      Review Send Block List &rarr;
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </ScrollArea>
        )}

        {/* VIEW 4: METRICS (MATRIX) VIEW (EXACT MATCH TO media_1790515187100.png) */}
        {activeSideNav === "metrics" && (
          <ScrollArea className="flex-1 min-h-0 bg-background">
            <div className="max-w-5xl mx-auto p-6 space-y-6">
              {/* Header with Platform Tag, Title, USE API, Theme Toggle */}
              <div className="flex items-center justify-between">
                <div>
                  <Badge variant="outline" className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground border-border mb-1">
                    Platform
                  </Badge>
                  <h1 className="text-2xl font-bold text-foreground tracking-tight">Metrics</h1>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Activity metrics and deliverability across all inboxes in this pod.
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <ThemeToggleCompact />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setApiDocsOpen(true)}
                    className="h-8 text-xs font-mono font-semibold border-border bg-muted/50 text-foreground hover:bg-muted gap-1.5"
                  >
                    <Code2 className="h-3.5 w-3.5" />
                    <span>USE API</span>
                  </Button>
                </div>
              </div>

              {/* Top Stats: Total messages in 30 days & Streak */}
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                <div className="rounded-xl border border-border bg-card p-5">
                  <span className="text-xs text-muted-foreground">Total messages (30 days)</span>
                  <p className="text-3xl font-bold text-foreground mt-1.5 font-mono">{metrics.messages30Days}</p>
                  <p className="text-[10px] text-muted-foreground/75 mt-1">Sent &amp; received combined</p>
                </div>
                <div className="rounded-xl border border-border bg-card p-5">
                  <span className="text-xs text-muted-foreground">Streak</span>
                  <div className="flex items-center gap-2 mt-1.5">
                    <Flame className="h-6 w-6 text-amber-400" />
                    <p className="text-3xl font-bold text-foreground font-mono">{metrics.streakDays} days</p>
                  </div>
                  <p className="text-[10px] text-muted-foreground/75 mt-1">Consecutive activity</p>
                </div>
                <div className="rounded-xl border border-border bg-card p-5">
                  <span className="text-xs text-muted-foreground">Bounce Rate</span>
                  <p className="text-3xl font-bold text-amber-400 mt-1.5 font-mono">{metrics.bounceRate}%</p>
                  <p className="text-[10px] text-amber-400/80 mt-1">Above recommended 5%</p>
                </div>
                <div className="rounded-xl border border-border bg-card p-5">
                  <span className="text-xs text-muted-foreground">Complaint Rate</span>
                  <p className="text-3xl font-bold text-emerald-400 mt-1.5 font-mono">{metrics.complaintRate}%</p>
                  <p className="text-[10px] text-emerald-400 mt-1">Excellent reputation</p>
                </div>
              </div>

              {/* 30-Day Message Activity Heatmap Matrix (Purple Tiles) */}
              <div className="rounded-xl border border-border bg-card p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-foreground">30-Day Message Activity Matrix</h3>
                  <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/75 font-mono">
                    <span>Less</span>
                    <span className="h-3 w-3 rounded-sm bg-muted/50 border border-border" />
                    <span className="h-3 w-3 rounded-sm bg-purple-100 dark:bg-purple-950/70 border border-purple-200 dark:border-purple-800/40" />
                    <span className="h-3 w-3 rounded-sm bg-purple-500" />
                    <span className="h-3 w-3 rounded-sm bg-purple-600 dark:bg-purple-500" />
                    <span>More</span>
                  </div>
                </div>

                {/* Heatmap Grid */}
                <div className="grid grid-cols-6 sm:grid-cols-10 gap-2 pt-2">
                  {metrics.activityMatrix.map((cell, idx) => {
                    const bg =
                      cell.level === 0
                        ? "bg-muted/40 border border-border text-muted-foreground"
                        : cell.level === 1
                          ? "bg-purple-100 dark:bg-purple-950/70 border border-purple-200 dark:border-purple-800/40 text-purple-700 dark:text-purple-300"
                          : cell.level === 2
                            ? "bg-purple-500 text-white font-bold shadow-xs"
                            : "bg-purple-600 dark:bg-purple-500 text-white font-bold shadow-sm"
                    return (
                      <div
                        key={idx}
                        className={cn(
                          "h-14 rounded-lg flex flex-col justify-between p-1.5 transition-transform hover:scale-105 cursor-pointer",
                          bg
                        )}
                        title={`${cell.date}: ${cell.count} messages`}
                      >
                        <span className="text-[9px] opacity-75 font-mono">{cell.date.slice(4)}</span>
                        <span className="text-xs font-mono self-end">{cell.count}</span>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Deliverability Section & Diagnostics */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-xl border border-border bg-card p-5 space-y-3">
                  <h3 className="text-sm font-semibold text-foreground">Deliverability Breakdown</h3>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Total Outbound Attempted</span>
                      <span className="font-mono text-foreground font-bold">25</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Successful Dispatches</span>
                      <span className="font-mono text-emerald-400 font-bold">22 (88%)</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Bounced Addresses</span>
                      <span className="font-mono text-amber-400 font-bold">3 (12%)</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Spam Complaints</span>
                      <span className="font-mono text-foreground font-bold">0 (0%)</span>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-card p-5 space-y-3">
                  <h3 className="text-sm font-semibold text-foreground">Diagnostics & Quarantine</h3>
                  <div className="p-3 rounded-lg bg-muted/50 border border-border text-xs space-y-1.5">
                    <p className="font-medium text-foreground">Mail Held Outside Inbox</p>
                    <p className="text-[11px] text-muted-foreground">
                      0 messages held by quarantine or threat detection filters in the last 30 days.
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/50 border border-border text-xs space-y-1.5">
                    <p className="font-medium text-foreground">DKIM & SPF Alignment</p>
                    <p className="text-[11px] text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      100% compliant across omnidome.co.za and agentmail.to
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </ScrollArea>
        )}

        {/* VIEW 5: DOMAINS VIEW (EXACT MATCH TO media_1790515223063.png) */}
        {activeSideNav === "domains" && (
          <ScrollArea className="flex-1 min-h-0 bg-background">
            <div className="max-w-5xl mx-auto p-6 space-y-6">
              {/* Header with Platform Tag, Title, USE API, and + Create Domain */}
              <div className="flex items-center justify-between">
                <div>
                  <Badge variant="outline" className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground border-border mb-1">
                    Platform
                  </Badge>
                  <h1 className="text-2xl font-bold text-foreground tracking-tight">Domains</h1>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Configure custom domains to send and receive directly from your AI agents.
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <ThemeToggleCompact />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setApiDocsOpen(true)}
                    className="h-8 text-xs font-mono font-semibold border-border bg-muted/50 text-foreground hover:bg-muted gap-1.5"
                  >
                    <Code2 className="h-3.5 w-3.5" />
                    <span>USE API</span>
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => showNotification("Custom domain provision wizard ready")}
                    className="h-8 text-xs bg-primary text-primary-foreground hover:bg-foreground/80 font-semibold gap-1.5"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Create Domain</span>
                  </Button>
                </div>
              </div>

              {/* Upgrade Banner (Exact match to screenshot media_1790515223063.png) */}
              <div className="rounded-xl border border-border bg-muted/60 p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center text-foreground shrink-0">
                    <Sparkles className="h-4 w-4 text-cyan-400" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-foreground">
                      Upgrade to Developer or Startup plan to use custom domains
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      Send and receive emails with info@omnidome.co.za and sales@omnidome.co.za.
                    </p>
                  </div>
                </div>
                <Button size="sm" className="h-8 text-xs bg-primary text-primary-foreground hover:bg-foreground/80 font-semibold">
                  Upgrade Now
                </Button>
              </div>

              {/* Empty state / Domain configuration card (Exact match to screenshot) */}
              <div className="rounded-xl border border-border bg-card p-12 flex flex-col items-center justify-center text-center space-y-4">
                <div className="h-12 w-12 rounded-full bg-muted/50 flex items-center justify-center border border-border">
                  <Globe className="h-6 w-6 text-muted-foreground" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-foreground">No custom domains yet</h3>
                  <p className="text-xs text-muted-foreground mt-1 max-w-md">
                    Send and receive emails using your own custom domain (e.g. info@omnidome.co.za, sales@omnidome.co.za).
                  </p>
                </div>
                <Button
                  size="sm"
                  onClick={() => showNotification("Add domain DNS setup opened")}
                  className="h-8 text-xs bg-primary text-primary-foreground hover:bg-foreground/80 font-semibold gap-1.5 px-4"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>Add Domain</span>
                </Button>
              </div>

              {/* Active Verified Domains Table */}
              <div className="space-y-4 pt-4 border-t border-border/80">
                <h3 className="text-sm font-semibold text-foreground">Active Verified Domains</h3>
                {domains.map((dom) => (
                  <div key={dom.id} className="rounded-xl border border-border bg-card p-5 space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        <Globe className="h-4 w-4 text-cyan-400" />
                        <span className="font-semibold text-sm text-foreground font-mono">{dom.domain}</span>
                        <Badge className="text-[10px] h-4 bg-emerald-950 text-emerald-300 border-emerald-800">
                          Verified &bull; Active
                        </Badge>
                      </div>
                      <span className="text-xs text-muted-foreground/75">Added {dom.createdAt.slice(0, 10)}</span>
                    </div>

                    <div className="rounded-lg bg-muted/50 border border-border overflow-hidden text-xs">
                      <table className="w-full text-left">
                        <thead className="bg-card text-muted-foreground border-b border-border">
                          <tr>
                            <th className="py-2 px-3 font-semibold">Type</th>
                            <th className="py-2 px-3 font-semibold">Host</th>
                            <th className="py-2 px-3 font-semibold">Target Value</th>
                            <th className="py-2 px-3 font-semibold">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border font-mono text-[11px]">
                          {dom.dnsRecords.map((rec, i) => (
                            <tr key={i} className="hover:bg-muted/40">
                              <td className="py-2 px-3 text-foreground/80 font-bold">{rec.type}</td>
                              <td className="py-2 px-3 text-muted-foreground">{rec.host}</td>
                              <td className="py-2 px-3 text-foreground">{rec.value}</td>
                              <td className="py-2 px-3 text-emerald-400 font-sans text-xs">Valid</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </ScrollArea>
        )}

        {/* VIEW 6: LISTS (ALLOW & BLOCK LISTS) VIEW (EXACT MATCH TO media_1790515336340.png) */}
        {activeSideNav === "lists" && (
          <ScrollArea className="flex-1 min-h-0 bg-background">
            <div className="max-w-5xl mx-auto p-6 space-y-6">
              {/* Header with Platform Tag, Title, USE API, and Theme Toggle */}
              <div className="flex items-center justify-between">
                <div>
                  <Badge variant="outline" className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground border-border mb-1">
                    Platform
                  </Badge>
                  <h1 className="text-2xl font-bold text-foreground tracking-tight">Allow &amp; Block Lists</h1>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Control who can email your inboxes and who your agents are permitted to contact.
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <ThemeToggleCompact />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setApiDocsOpen(true)}
                    className="h-8 text-xs font-mono font-semibold border-border bg-muted/50 text-foreground hover:bg-muted gap-1.5"
                  >
                    <Code2 className="h-3.5 w-3.5" />
                    <span>USE API</span>
                  </Button>
                </div>
              </div>

              {/* 3 SECTIONS: Receive, Send, Reply (Matching screenshot media_1790515336340.png) */}

              {/* SECTION 1: RECEIVE */}
              <div className="space-y-3">
                <h3 className="text-sm font-bold text-foreground">Receive</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Allow List */}
                  <div className="rounded-xl border border-border bg-card p-5 space-y-3 flex flex-col justify-between">
                    <div>
                      <span className="font-semibold text-xs text-foreground">Allow List</span>
                      <p className="text-xs text-muted-foreground mt-1">
                        Incoming emails matching these rules will always be delivered to your inbox.
                      </p>
                      <div className="mt-3 p-3 rounded-lg bg-muted/50 border border-border font-mono text-xs text-foreground/80">
                        *@omnidome.co.za &bull; benemajozl@gmail.com
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setNewRuleScope("receive")
                        setNewRuleType("allow")
                        setAddRuleOpen(true)
                      }}
                      className="h-8 text-xs border-border text-foreground hover:bg-muted/50 mt-2 gap-1"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      <span>Add Rule</span>
                    </Button>
                  </div>

                  {/* Block List */}
                  <div className="rounded-xl border border-border bg-card p-5 space-y-3 flex flex-col justify-between">
                    <div>
                      <span className="font-semibold text-xs text-foreground">Block List</span>
                      <p className="text-xs text-muted-foreground mt-1">
                        Incoming emails matching these rules will be rejected or held outside your inbox.
                      </p>
                      <div className="mt-3 p-3 rounded-lg bg-muted/50 border border-border font-mono text-xs text-muted-foreground italic">
                        *@marketing-spammers-bot.net
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setNewRuleScope("receive")
                        setNewRuleType("block")
                        setAddRuleOpen(true)
                      }}
                      className="h-8 text-xs border-border text-foreground hover:bg-muted/50 mt-2 gap-1"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      <span>Add Rule</span>
                    </Button>
                  </div>
                </div>
              </div>

              {/* SECTION 2: SEND (Contains majozippe@gmail.com Bounced matching screenshot) */}
              <div className="space-y-3">
                <h3 className="text-sm font-bold text-foreground">Send</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Allow List */}
                  <div className="rounded-xl border border-border bg-card p-5 space-y-3 flex flex-col justify-between">
                    <div>
                      <span className="font-semibold text-xs text-foreground">Allow List</span>
                      <p className="text-xs text-muted-foreground mt-1">
                        Outbound emails matching these rules will bypass outbound reputation checks.
                      </p>
                      <p className="text-xs text-muted-foreground/75 italic mt-3">No active rules</p>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setNewRuleScope("send")
                        setNewRuleType("allow")
                        setAddRuleOpen(true)
                      }}
                      className="h-8 text-xs border-border text-foreground hover:bg-muted/50 mt-2 gap-1"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      <span>Add Rule</span>
                    </Button>
                  </div>

                  {/* Block List (With majozippe@gmail.com Bounced row) */}
                  <div className="rounded-xl border border-border bg-card p-5 space-y-3 flex flex-col justify-between">
                    <div>
                      <span className="font-semibold text-xs text-foreground">Block List</span>
                      <p className="text-xs text-muted-foreground mt-1">
                        Outbound emails matching these rules cannot be sent from your inboxes.
                      </p>
                      {/* Exact row from screenshot media_1790515336340.png */}
                      <div className="mt-3 flex items-center justify-between p-2.5 rounded-lg bg-muted/50 border border-border text-xs">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="font-mono text-foreground truncate">majozippe@gmail.com</span>
                          <Badge variant="outline" className="text-[10px] h-4 text-muted-foreground border-border">
                            Bounced
                          </Badge>
                        </div>
                        <button
                          onClick={() => {
                            setListRules((prev) => prev.filter((r) => r.pattern !== "majozippe@gmail.com"))
                            showNotification("Removed majozippe@gmail.com from Send Block List")
                          }}
                          className="text-muted-foreground/75 hover:text-red-400 transition-colors p-1"
                          title="Delete rule"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setNewRuleScope("send")
                        setNewRuleType("block")
                        setAddRuleOpen(true)
                      }}
                      className="h-8 text-xs border-border text-foreground hover:bg-muted/50 mt-2 gap-1"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      <span>Add Rule</span>
                    </Button>
                  </div>
                </div>
              </div>

              {/* SECTION 3: REPLY */}
              <div className="space-y-3">
                <h3 className="text-sm font-bold text-foreground">Reply</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Allow List */}
                  <div className="rounded-xl border border-border bg-card p-5 space-y-3 flex flex-col justify-between">
                    <div>
                      <span className="font-semibold text-xs text-foreground">Allow List</span>
                      <p className="text-xs text-muted-foreground mt-1">
                        Auto-reply agents are permitted to respond to these senders automatically.
                      </p>
                      <p className="text-xs text-muted-foreground/75 italic mt-3">All verified inbound senders permitted</p>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setNewRuleScope("reply")
                        setNewRuleType("allow")
                        setAddRuleOpen(true)
                      }}
                      className="h-8 text-xs border-border text-foreground hover:bg-muted/50 mt-2 gap-1"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      <span>Add Rule</span>
                    </Button>
                  </div>

                  {/* Block List */}
                  <div className="rounded-xl border border-border bg-card p-5 space-y-3 flex flex-col justify-between">
                    <div>
                      <span className="font-semibold text-xs text-foreground">Block List</span>
                      <p className="text-xs text-muted-foreground mt-1">
                        Auto-reply agents will NEVER trigger or send automatic replies to these addresses.
                      </p>
                      <div className="mt-3 p-3 rounded-lg bg-muted/50 border border-border font-mono text-xs text-muted-foreground italic">
                        *@noreply.* &bull; mailer-daemon@*
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setNewRuleScope("reply")
                        setNewRuleType("block")
                        setAddRuleOpen(true)
                      }}
                      className="h-8 text-xs border-border text-foreground hover:bg-muted/50 mt-2 gap-1"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      <span>Add Rule</span>
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </ScrollArea>
        )}

        {/* VIEW 7: SETTINGS VIEW */}
        {activeSideNav === "settings" && (
          <ScrollArea className="flex-1 min-h-0 bg-background">
            <div className="max-w-3xl mx-auto p-6 space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-2xl font-bold text-foreground tracking-tight">AgentMail Settings</h1>
                  <p className="text-xs text-muted-foreground mt-1">
                    Multi-tenant pod boundaries, webhook dispatch endpoints, and Orchestrator AI routing.
                  </p>
                </div>
                <ThemeToggleCompact />
              </div>

              <div className="rounded-xl border border-border bg-card p-5 space-y-4">
                <h3 className="text-sm font-semibold text-foreground">Current Pod Profile</h3>
                <div className="space-y-3 text-xs">
                  <div>
                    <label className="text-muted-foreground block mb-1">Pod Name</label>
                    <Input
                      defaultValue={currentPod.name}
                      className="bg-muted/50 border-border text-foreground text-xs h-8"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground block mb-1">Tenant ID</label>
                    <Input
                      disabled
                      defaultValue={currentPod.tenantId}
                      className="bg-muted/40 border-border text-muted-foreground text-xs font-mono h-8"
                    />
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-border bg-card p-5 space-y-4">
                <h3 className="text-sm font-semibold text-foreground">Orchestrator AI Automation Policies</h3>
                <div className="space-y-3 text-xs">
                  <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50 border border-border">
                    <div>
                      <p className="font-medium text-foreground">Auto-Reply Confidence Threshold</p>
                      <p className="text-[11px] text-muted-foreground">Only auto-send if AI certainty exceeds 85%</p>
                    </div>
                    <Badge variant="outline" className="text-xs text-cyan-400 border-cyan-500/40">
                      85%
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50 border border-border">
                    <div>
                      <p className="font-medium text-foreground">Sales Quote Escalation</p>
                      <p className="text-[11px] text-muted-foreground">Require supervisor approval before sending quotes &gt; R50,000</p>
                    </div>
                    <Badge variant="outline" className="text-xs text-emerald-400 border-emerald-500/40">
                      Enabled
                    </Badge>
                  </div>
                </div>
              </div>
            </div>
          </ScrollArea>
        )}
      </div>

      {/* ── GROUP CAPABILITIES & ORCHESTRATOR DRAWER ── */}
      <Dialog open={capabilitiesDrawerOpen} onOpenChange={setCapabilitiesDrawerOpen}>
        <DialogContent className="max-w-2xl bg-card border-border text-foreground p-6">
          <DialogHeader>
            <div className="flex items-center gap-2 text-cyan-400">
              <Sparkles className="h-5 w-5" />
              <DialogTitle className="text-lg font-bold text-foreground">
                AgentMail Core Capabilities &amp; Orchestrator
              </DialogTitle>
            </div>
            <DialogDescription className="text-xs text-muted-foreground">
              Core concepts linking multi-tenant pods, collaborative shared mailboxes, and automated AI agents.
            </DialogDescription>
          </DialogHeader>

          <ScrollArea className="max-h-[65vh] pr-2 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div className="rounded-lg bg-muted/60 border border-border p-3 space-y-1.5">
                <div className="flex items-center gap-2 text-foreground font-semibold">
                  <Inbox className="h-4 w-4 text-cyan-400" />
                  <span>Inboxes &amp; Shared Groups</span>
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  Provision personal inboxes and team shared mailboxes (<span className="font-mono text-foreground">sales@omnidome.co.za</span>, <span className="font-mono text-foreground">info@omnidome.co.za</span>). Members receive assigned visibility with live unread indicators.
                </p>
              </div>

              <div className="rounded-lg bg-muted/60 border border-border p-3 space-y-1.5">
                <div className="flex items-center gap-2 text-foreground font-semibold">
                  <Building className="h-4 w-4 text-purple-400" />
                  <span>Multi-Tenant Pods</span>
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  Pod architecture provides cryptographic isolation between tenants, departments, or companies. All inboxes, list rules, and metrics operate inside tenant boundaries.
                </p>
              </div>

              <div className="rounded-lg bg-muted/60 border border-border p-3 space-y-1.5">
                <div className="flex items-center gap-2 text-foreground font-semibold">
                  <FileText className="h-4 w-4 text-amber-400" />
                  <span>Collaborative Drafts</span>
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  Agents synthesize customer proposals and responses into shared drafts. Team members review, edit, and co-author before human-in-the-loop dispatch.
                </p>
              </div>

              <div className="rounded-lg bg-muted/60 border border-border p-3 space-y-1.5">
                <div className="flex items-center gap-2 text-foreground font-semibold">
                  <Tag className="h-4 w-4 text-emerald-400" />
                  <span>Smart Labels</span>
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  Inbound emails are automatically tagged by the Smart Label Agent (e.g. Sales Inquiry, High Intent, Support Incident, Billing) with confidence scoring.
                </p>
              </div>

              <div className="rounded-lg bg-muted/60 border border-border p-3 space-y-1.5">
                <div className="flex items-center gap-2 text-foreground font-semibold">
                  <Shield className="h-4 w-4 text-red-400" />
                  <span>Allow &amp; Block Lists</span>
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  Scoped rules across Receive, Send, and Reply. Automatically isolates bounces (e.g. <span className="font-mono text-foreground">majozippe@gmail.com</span>) to protect domain reputation.
                </p>
              </div>

              <div className="rounded-lg bg-muted/60 border border-border p-3 space-y-1.5">
                <div className="flex items-center gap-2 text-foreground font-semibold">
                  <Bot className="h-4 w-4 text-cyan-400" />
                  <span>Orchestrator AI Linking</span>
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  Direct pipeline linking to Sales Agent (telemetry pricing &amp; quote approvals), Auto Reply Agent (instant SLA verification), and supervisor escalation thresholds.
                </p>
              </div>
            </div>
          </ScrollArea>

          <DialogFooter className="pt-3 border-t border-border">
            <Button
              size="sm"
              onClick={() => setCapabilitiesDrawerOpen(false)}
              className="h-8 text-xs bg-primary text-primary-foreground hover:bg-foreground/80 font-semibold"
            >
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── MANAGE MEMBERS & SHARED FOLDERS MODAL ── */}
      <Dialog open={manageGroupModalOpen} onOpenChange={setManageGroupModalOpen}>
        <DialogContent className="max-w-xl bg-card border-border text-foreground p-6">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold text-foreground flex items-center gap-2">
              <Users className="h-4 w-4 text-cyan-400" />
              <span>Manage Shared Group: {currentSharedGroup?.name}</span>
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Add team members, assign permission roles, and view shared mail folders.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 pt-2 text-xs">
            {/* Add Member Form */}
            <div className="p-3 rounded-lg bg-muted/50 border border-border space-y-2.5">
              <span className="font-semibold text-foreground">Add User to Shared Mailbox</span>
              <div className="flex gap-2">
                <Input
                  placeholder="colleague@omnidome.co.za"
                  value={newMemberEmail}
                  onChange={(e) => setNewMemberEmail(e.target.value)}
                  className="flex-1 bg-muted/50 border-border text-xs h-8 text-foreground"
                />
                <select
                  value={newMemberRole}
                  onChange={(e) => setNewMemberRole(e.target.value as any)}
                  className="h-8 rounded-md bg-muted/50 border border-border px-2 text-foreground text-xs"
                >
                  <option value="admin">Admin</option>
                  <option value="operator">Operator</option>
                  <option value="member">Member</option>
                  <option value="viewer">Viewer</option>
                </select>
                <Button
                  size="sm"
                  onClick={handleAddMemberToGroup}
                  className="h-8 text-xs bg-primary text-primary-foreground hover:bg-foreground/80 font-semibold"
                >
                  Add
                </Button>
              </div>
            </div>

            {/* Current Members List */}
            <div className="space-y-2">
              <span className="font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">
                Current Members ({currentSharedGroup?.members.length})
              </span>
              <div className="divide-y divide-border/80 rounded-lg border border-border bg-muted/30">
                {currentSharedGroup?.members.map((member) => (
                  <div key={member.email} className="p-2.5 flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <Avatar className="h-7 w-7 rounded-full bg-muted text-foreground font-bold text-xs">
                        <AvatarFallback>{member.avatar}</AvatarFallback>
                      </Avatar>
                      <div>
                        <p className="font-medium text-foreground">{member.name}</p>
                        <p className="text-[10px] text-muted-foreground font-mono">{member.email}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[9px] capitalize border-border text-foreground/80">
                        {member.role}
                      </Badge>
                      <button
                        onClick={() => handleRemoveMemberFromGroup(member.email)}
                        className="text-muted-foreground/75 hover:text-red-400 p-1"
                        title="Remove member"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Shared Folders in this group */}
            <div className="space-y-2">
              <span className="font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">
                Shared Folders in this Mailbox
              </span>
              <div className="flex flex-wrap gap-2">
                {currentSharedGroup?.sharedFolders.map((folder) => (
                  <Badge key={folder} variant="secondary" className="text-xs bg-muted/50 text-foreground/80 border-border py-1 px-2.5">
                    <Folder className="h-3 w-3 mr-1 text-cyan-400" />
                    {folder}
                  </Badge>
                ))}
              </div>
            </div>
          </div>

          <DialogFooter className="pt-3 border-t border-border">
            <Button
              size="sm"
              onClick={() => setManageGroupModalOpen(false)}
              className="h-8 text-xs bg-primary text-primary-foreground hover:bg-foreground/80 font-semibold"
            >
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── CREATE NEW SHARED GROUP MODAL ── */}
      <Dialog open={createGroupOpen} onOpenChange={setCreateGroupOpen}>
        <DialogContent className="max-w-md bg-card border-border text-foreground p-6">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold text-foreground">Create Shared Mailbox Group</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Provision a collaborative team mailbox with multi-user access and AI agent automation.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 pt-2 text-xs">
            <div>
              <label className="text-muted-foreground block mb-1">Group Name</label>
              <Input
                placeholder="e.g. VIP Support Desk, Regional Sales"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                className="bg-muted/50 border-border text-foreground h-8"
              />
            </div>
            <div>
              <label className="text-muted-foreground block mb-1">Email Address</label>
              <Input
                placeholder="e.g. vip-support@omnidome.co.za"
                value={newGroupEmail}
                onChange={(e) => setNewGroupEmail(e.target.value)}
                className="bg-muted/50 border-border text-foreground h-8 font-mono"
              />
            </div>
          </div>

          <DialogFooter className="pt-3 border-t border-border">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCreateGroupOpen(false)}
              className="h-8 text-xs border-border"
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => {
                if (!newGroupName.trim() || !newGroupEmail.trim()) return
                const newGroup: SharedMailboxGroup = {
                  id: `grp-${Date.now()}`,
                  mailboxId: `mb-${Date.now()}`,
                  name: newGroupName.trim(),
                  emailAddress: newGroupEmail.trim(),
                  description: "Custom collaborative shared mailbox.",
                  members: [
                    {
                      userId: "usr-burni",
                      name: "Burni Braai",
                      email: "burnibraa@gmail.com",
                      role: "admin",
                      avatar: "B",
                      addedAt: new Date().toISOString(),
                    },
                  ],
                  assignedAgents: ["sales", "auto_reply"],
                  sharedFolders: ["Inbound Queue", "Collaborative Drafts"],
                  autoReplyApprovalRequired: true,
                  unreadCount: 0,
                  totalCount: 0,
                }
                setSharedGroups((prev) => [...prev, newGroup])
                setCreateGroupOpen(false)
                setNewGroupName("")
                setNewGroupEmail("")
                showNotification(`Shared group "${newGroup.name}" created`)
              }}
              className="h-8 text-xs bg-primary text-primary-foreground hover:bg-foreground/80 font-semibold"
            >
              Create Group
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── COMPOSE MODAL (With Orchestrator AI Copilot) ── */}
      <Dialog open={composeOpen} onOpenChange={setComposeOpen}>
        <DialogContent className="max-w-2xl bg-card border-border text-foreground p-6">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold text-foreground">New Email Transmission</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Send via AgentMail with automated DKIM/SPF compliance.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 pt-2">
            {/* From selector */}
            <div className="flex items-center gap-2 text-xs">
              <span className="w-12 text-muted-foreground">From:</span>
              <select
                value={composeFromMailboxId}
                onChange={(e) => setComposeFromMailboxId(e.target.value)}
                className="flex-1 h-8 rounded-md bg-muted/50 border border-border px-2 text-foreground text-xs font-mono"
              >
                {mailboxes.map((mb) => (
                  <option key={mb.id} value={mb.id}>
                    {mb.displayName} &lt;{mb.emailAddress}&gt;
                  </option>
                ))}
              </select>
            </div>

            {/* To */}
            <div className="flex items-center gap-2 text-xs">
              <span className="w-12 text-muted-foreground">To:</span>
              <Input
                placeholder="recipient@example.com"
                value={composeTo}
                onChange={(e) => setComposeTo(e.target.value)}
                className="flex-1 h-8 bg-muted/50 border-border text-xs text-foreground"
              />
            </div>

            {/* Subject */}
            <div className="flex items-center gap-2 text-xs">
              <span className="w-12 text-muted-foreground">Subject:</span>
              <Input
                placeholder="Subject line"
                value={composeSubject}
                onChange={(e) => setComposeSubject(e.target.value)}
                className="flex-1 h-8 bg-muted/50 border-border text-xs text-foreground"
              />
            </div>

            {/* Orchestrator Prompt Bar */}
            <div className="rounded-lg bg-muted/70 border border-border p-2.5 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5 text-cyan-400 font-medium">
                  <Bot className="h-3.5 w-3.5" />
                  <span>Draft with Orchestrator AI</span>
                </div>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => handleAskOrchestratorAi("sales proposal for fleet telemetry")}
                    className="text-[10px] px-2 py-0.5 rounded bg-muted hover:bg-muted text-foreground/80"
                  >
                    Sales Quote
                  </button>
                  <button
                    type="button"
                    onClick={() => handleAskOrchestratorAi("technical support resolution")}
                    className="text-[10px] px-2 py-0.5 rounded bg-muted hover:bg-muted text-foreground/80"
                  >
                    Support Reply
                  </button>
                </div>
              </div>
              <div className="flex gap-2">
                <Input
                  placeholder="e.g. Write a friendly follow-up email confirming our meeting tomorrow..."
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  className="h-7 bg-card border-border text-xs text-foreground"
                />
                <Button
                  size="sm"
                  type="button"
                  onClick={() => handleAskOrchestratorAi()}
                  disabled={isGeneratingAi}
                  className="h-7 px-3 text-xs bg-cyan-600 hover:bg-cyan-500 text-foreground"
                >
                  {isGeneratingAi ? "Generating..." : "Generate"}
                </Button>
              </div>
            </div>

            {/* Message Body */}
            <Textarea
              placeholder="Write your email here..."
              rows={8}
              value={composeBody}
              onChange={(e) => setComposeBody(e.target.value)}
              className="bg-muted/50 border-border text-xs text-foreground font-sans leading-relaxed"
            />
          </div>

          <DialogFooter className="flex justify-between items-center pt-3 border-t border-border">
            <div className="flex items-center gap-2">
              <Button size="sm" variant="ghost" className="h-8 text-muted-foreground text-xs">
                <Paperclip className="h-3.5 w-3.5 mr-1" />
                Attach
              </Button>
            </div>
            <div className="flex items-center gap-2">
              {composeError && <span className="text-xs text-red-400">{composeError}</span>}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setComposeOpen(false)}
                className="h-8 text-xs border-border"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => void handleSendCompose()}
                disabled={sendingCompose}
                className="h-8 text-xs bg-primary text-primary-foreground hover:bg-foreground/80 font-medium"
              >
                <Send className="h-3.5 w-3.5 mr-1" />
                {sendingCompose ? "Sending..." : "Send Email"}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── CREATE INBOX MODAL ── */}
      <Dialog open={createInboxOpen} onOpenChange={setCreateInboxOpen}>
        <DialogContent className="max-w-md bg-card border-border text-foreground p-6">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold text-foreground">Create Automated Inbox</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Provision an on-the-fly email address for an AI Agent or team member.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 pt-2 text-xs">
            <div>
              <label className="text-muted-foreground block mb-1">Username / Prefix</label>
              <div className="flex items-center gap-2">
                <Input
                  placeholder="e.g. sales, support, info"
                  value={newInboxUsername}
                  onChange={(e) => setNewInboxUsername(e.target.value)}
                  className="bg-muted/50 border-border text-foreground h-8"
                />
                <span className="text-muted-foreground/75 font-mono">@</span>
                <select
                  value={newInboxDomain}
                  onChange={(e) => setNewInboxDomain(e.target.value)}
                  className="h-8 rounded-md bg-muted/50 border border-border px-2 text-foreground text-xs font-mono"
                >
                  <option value="agentmail.to">agentmail.to</option>
                  <option value="omnidome.co.za">omnidome.co.za</option>
                </select>
              </div>
            </div>

            <div>
              <label className="text-muted-foreground block mb-1">Display Name</label>
              <Input
                placeholder="e.g. OmniDome Enterprise Sales"
                value={newInboxDisplayName}
                onChange={(e) => setNewInboxDisplayName(e.target.value)}
                className="bg-muted/50 border-border text-foreground h-8"
              />
            </div>

            <div>
              <label className="text-muted-foreground block mb-1">Agent Persona</label>
              <select
                value={newInboxPersona}
                onChange={(e) => setNewInboxPersona(e.target.value as any)}
                className="w-full h-8 rounded-md bg-muted/50 border border-border px-2 text-foreground text-xs"
              >
                <option value="auto_reply">Auto Reply Agent (Instant acknowledgment)</option>
                <option value="sales">Sales Agent (Lead qualification & proposals)</option>
                <option value="smart_label">Smart Label Agent (Automated categorization)</option>
                <option value="finance">Finance Agent (Invoices & settlements)</option>
                <option value="human">Human Team Member (With AI Copilot)</option>
              </select>
            </div>
          </div>

          <DialogFooter className="pt-3 border-t border-border">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCreateInboxOpen(false)}
              className="h-8 text-xs border-border"
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleCreateInbox}
              className="h-8 text-xs bg-primary text-primary-foreground hover:bg-foreground/80"
            >
              Provision Inbox
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── CREATE POD MODAL (Multi-Tenant Architecture) ── */}
      <Dialog open={createPodOpen} onOpenChange={setCreatePodOpen}>
        <DialogContent className="max-w-md bg-card border-border text-foreground p-6">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold text-foreground">Create Multi-Tenant Pod</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Isolate inboxes, custom domains, and rules per tenant or department.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 pt-2 text-xs">
            <div>
              <label className="text-muted-foreground block mb-1">Pod Name</label>
              <Input
                placeholder="e.g. Sales Dept Pod, Tenant Beta Pod"
                value={newPodName}
                onChange={(e) => setNewPodName(e.target.value)}
                className="bg-muted/50 border-border text-foreground h-8"
              />
            </div>
          </div>

          <DialogFooter className="pt-3 border-t border-border">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCreatePodOpen(false)}
              className="h-8 text-xs border-border"
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleCreatePod}
              className="h-8 text-xs bg-primary text-primary-foreground hover:bg-foreground/80"
            >
              Initialize Pod
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── ADD RULE MODAL (Lists) ── */}
      <Dialog open={addRuleOpen} onOpenChange={setAddRuleOpen}>
        <DialogContent className="max-w-md bg-card border-border text-foreground p-6">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold text-foreground">
              Add {newRuleScope.toUpperCase()} {newRuleType.toUpperCase()} Rule
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Configure filtering and reputation rules for incoming and outgoing mail.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 pt-2 text-xs">
            <div>
              <label className="text-muted-foreground block mb-1">Scope</label>
              <select
                value={newRuleScope}
                onChange={(e) => setNewRuleScope(e.target.value as any)}
                className="w-full h-8 rounded-md bg-muted/50 border border-border px-2 text-foreground text-xs"
              >
                <option value="receive">Receive (Incoming mail)</option>
                <option value="send">Send (Outbound dispatches)</option>
                <option value="reply">Reply (Auto-reply triggers)</option>
              </select>
            </div>
            <div>
              <label className="text-muted-foreground block mb-1">Action Type</label>
              <select
                value={newRuleType}
                onChange={(e) => setNewRuleType(e.target.value as any)}
                className="w-full h-8 rounded-md bg-muted/50 border border-border px-2 text-foreground text-xs"
              >
                <option value="allow">Allow</option>
                <option value="block">Block</option>
              </select>
            </div>
            <div>
              <label className="text-muted-foreground block mb-1">Pattern</label>
              <Input
                placeholder="e.g. *@partner.com, user@domain.com"
                value={newRulePattern}
                onChange={(e) => setNewRulePattern(e.target.value)}
                className="bg-muted/50 border-border text-foreground h-8 font-mono"
              />
            </div>
            <div>
              <label className="text-muted-foreground block mb-1">Reason</label>
              <Input
                placeholder="e.g. Strategic client partner, Bounced recipient"
                value={newRuleReason}
                onChange={(e) => setNewRuleReason(e.target.value)}
                className="bg-muted/50 border-border text-foreground h-8"
              />
            </div>
          </div>

          <DialogFooter className="pt-3 border-t border-border">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAddRuleOpen(false)}
              className="h-8 text-xs border-border"
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => {
                if (!newRulePattern) return
                setListRules((prev) => [
                  ...prev,
                  {
                    id: `rule-${Date.now()}`,
                    podId: selectedPodId,
                    type: newRuleType,
                    pattern: newRulePattern,
                    target: newRulePattern.includes("@") ? "email" : "domain",
                    reason: newRuleReason || "Custom rule",
                    createdAt: new Date().toISOString(),
                  },
                ])
                setAddRuleOpen(false)
                setNewRulePattern("")
                setNewRuleReason("")
                showNotification(`Rule added to ${newRuleScope} ${newRuleType} list`)
              }}
              className="h-8 text-xs bg-primary text-primary-foreground hover:bg-foreground/80"
            >
              Save Rule
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── API DOCS / CODE DIALOG ── */}
      <Dialog open={apiDocsOpen} onOpenChange={setApiDocsOpen}>
        <DialogContent className="max-w-2xl bg-card border-border text-foreground p-6">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold text-foreground flex items-center gap-2">
              <Code2 className="h-4 w-4 text-cyan-400" />
              <span>AgentMail Developer API</span>
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Integrate your AI agents directly via Python SDK or TypeScript.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 pt-2 text-xs">
            <div className="rounded-lg bg-muted/50 p-3 border border-border font-mono text-[11px] space-y-2 overflow-x-auto">
              <p className="text-muted-foreground"># Send automated email via AgentMail Python SDK</p>
              <p className="text-cyan-300">from agentmail import AgentMail</p>
              <p className="text-foreground">client = AgentMail(api_key=&quot;am_live_...&quot;)</p>
              <p className="text-emerald-400">
                response = client.inboxes.send(
                <br />
                &nbsp;&nbsp;inbox_id=&quot;sales@omnidome.co.za&quot;,
                <br />
                &nbsp;&nbsp;to=&quot;nkhumalo@apexlogistics.co.za&quot;,
                <br />
                &nbsp;&nbsp;subject=&quot;Enterprise Telemetry Proposal&quot;,
                <br />
                &nbsp;&nbsp;body=&quot;Attached is your customized 500-node quote.&quot;
                <br />)
              </p>
            </div>
          </div>

          <DialogFooter className="pt-3 border-t border-border">
            <Button
              size="sm"
              onClick={() => setApiDocsOpen(false)}
              className="h-8 text-xs bg-primary text-primary-foreground hover:bg-foreground/80"
            >
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
