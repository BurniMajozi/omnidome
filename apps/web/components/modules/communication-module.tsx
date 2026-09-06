"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import { cn } from "@/lib/utils"
import { useChannelSocket } from "@/lib/useChannelSocket"
import { supabase } from "@/lib/supabase/client"
import { transcribe as voiceboxTranscribe, speak as voiceboxSpeak } from "@/lib/voicebox-api"
import { AgentArtifactChat } from "@/components/chat/agent-artifact-chat"
import { toWavWithStats, SILENCE_RMS_THRESHOLD } from "@/lib/audio-utils"
import {
  Mic,
  MicOff,
  Volume2,
  Loader2,
  Hash,
  Lock,
  ChevronDown,
  ChevronRight,
  Plus,
  Search,
  Bell,
  Pin,
  MoreHorizontal,
  Edit3,
  Smile,
  Paperclip,
  Send,
  AtSign,
  Video,
  Phone,
  Users,
  Circle,
  CheckCircle2,
  Clock,
  AlertCircle,
  ArrowUpRight,
  MessageSquare,
  ListTodo,
  Flag,
  Bot,
  Server,
  Calendar,
  CalendarDays,
  LayoutGrid,
  GanttChart,
  List,
  CheckSquare,
  PhoneCall,
  Reply,
  CalendarPlus,
  ClipboardList,
  Zap,
  Settings,
  MonitorSpeaker,
  PanelLeft,
  PanelLeftClose,
  PanelRightClose,
  X,
  Sparkles,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent } from "@/components/ui/tabs"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

interface Channel {
  id: string
  name: string
  isPrivate?: boolean
  is_private?: boolean
  unread?: number
}

interface DirectMessage {
  id: string
  name: string
  avatar: string
  status: "online" | "away" | "offline"
  unread?: number
}

interface SystemMessage {
  id: string
  type: "alert" | "notification" | "update" | "warning"
  title: string
  content: string
  time: string
  read?: boolean
}

interface AgentApproval {
  id: string
  agent: string
  avatar: string
  type: "discount" | "refund" | "credit" | "override"
  customer: string
  amount: string
  reason: string
  status: "pending" | "approved" | "rejected"
  time: string
}

interface ScheduleEvent {
  id: string
  title: string
  type: "meeting" | "task" | "reminder" | "deadline"
  date: string
  time: string
  assignee?: string
  avatar?: string
  status: "upcoming" | "in-progress" | "completed"
}

interface ActivityItem {
  id: string
  type: "chat" | "task" | "approval" | "escalation" | "schedule"
  title: string
  actor: string
  time: string
  meta?: string
}

interface Message {
  id: string
  channel_id?: string | null
  author_name?: string | null
  author_avatar?: string | null
  content: string
  created_at?: string | null
  reactions?: { emoji: string; count: number }[]
  thread?: number
  isPinned?: boolean
}

interface Task {
  id: string
  title: string
  assignee: string
  avatar: string
  status: "todo" | "in-progress" | "done"
  priority: "low" | "medium" | "high"
  dueDate: string
}

interface Lead {
  id: string
  name: string
  company: string
  value: string
  assignee: string
  avatar: string
  status: "new" | "contacted" | "qualified"
}

interface Escalation {
  id: string
  title: string
  customer: string
  severity: "low" | "medium" | "high" | "critical"
  assignee: string
  avatar: string
  time: string
  status?: "open" | "resolved"
}

const seedChannels: Channel[] = [
  { id: "1", name: "general", unread: 3 },
  { id: "2", name: "sales-team", unread: 12 },
  { id: "3", name: "support-tickets" },
  { id: "4", name: "network-alerts", unread: 5 },
  { id: "5", name: "marketing", isPrivate: true },
  { id: "6", name: "leadership", isPrivate: true },
]

const directMessages: DirectMessage[] = [
  { id: "1", name: "Sarah Chen", avatar: "SC", status: "online", unread: 2 },
  { id: "2", name: "Mike Johnson", avatar: "MJ", status: "online" },
  { id: "3", name: "Emily Davis", avatar: "ED", status: "away" },
  { id: "4", name: "James Wilson", avatar: "JW", status: "offline" },
  { id: "5", name: "Lisa Park", avatar: "LP", status: "online", unread: 1 },
]

const systemMessages: SystemMessage[] = [
  {
    id: "1",
    type: "alert",
    title: "Network Alert",
    content: "High latency detected in Johannesburg region",
    time: "2 min ago",
    read: false,
  },
  {
    id: "2",
    type: "notification",
    title: "New Lead Assigned",
    content: "TechCorp Enterprise lead assigned to you",
    time: "15 min ago",
    read: false,
  },
  {
    id: "3",
    type: "update",
    title: "System Update",
    content: "CRM sync completed successfully",
    time: "1 hour ago",
    read: true,
  },
  {
    id: "4",
    type: "warning",
    title: "SLA Warning",
    content: "Ticket #4521 approaching SLA breach",
    time: "30 min ago",
    read: false,
  },
]

const seedApprovals: AgentApproval[] = [
  {
    id: "1",
    agent: "Sarah Chen",
    avatar: "SC",
    type: "discount",
    customer: "Meridian Corp",
    amount: "R15,000",
    reason: "Loyalty discount for 3-year renewal",
    status: "pending",
    time: "10 min ago",
  },
  {
    id: "2",
    agent: "Mike Johnson",
    avatar: "MJ",
    type: "refund",
    customer: "TechStart Ltd",
    amount: "R8,500",
    reason: "Service downtime compensation",
    status: "pending",
    time: "25 min ago",
  },
  {
    id: "3",
    agent: "Emily Davis",
    avatar: "ED",
    type: "credit",
    customer: "RetailMax",
    amount: "R3,200",
    reason: "Billing adjustment for incorrect charges",
    status: "approved",
    time: "1 hour ago",
  },
  {
    id: "4",
    agent: "James Wilson",
    avatar: "JW",
    type: "override",
    customer: "MediaGroup",
    amount: "R22,000",
    reason: "Special pricing for enterprise upgrade",
    status: "pending",
    time: "2 hours ago",
  },
]

const seedScheduleEvents: ScheduleEvent[] = [
  {
    id: "1",
    title: "Q4 Pipeline Review",
    type: "meeting",
    date: "Today",
    time: "14:00",
    assignee: "Sales Team",
    status: "upcoming",
  },
  {
    id: "2",
    title: "Follow up Meridian",
    type: "task",
    date: "Today",
    time: "16:00",
    assignee: "Sarah Chen",
    avatar: "SC",
    status: "in-progress",
  },
  {
    id: "3",
    title: "Network Maintenance",
    type: "reminder",
    date: "Tomorrow",
    time: "02:00",
    assignee: "Network Ops",
    status: "upcoming",
  },
  {
    id: "4",
    title: "Contract Deadline",
    type: "deadline",
    date: "Friday",
    time: "17:00",
    assignee: "Legal",
    status: "upcoming",
  },
  {
    id: "5",
    title: "Client Presentation",
    type: "meeting",
    date: "Thursday",
    time: "10:00",
    assignee: "Mike Johnson",
    avatar: "MJ",
    status: "upcoming",
  },
  {
    id: "6",
    title: "Update CRM Records",
    type: "task",
    date: "Today",
    time: "12:00",
    assignee: "Emily Davis",
    avatar: "ED",
    status: "completed",
  },
]

const seedMessages: Message[] = [
  {
    id: "1",
    author_name: "Sarah Chen",
    author_avatar: "SC",
    content: "Hey team! Just closed the Meridian account - R450K MRR! 🎉",
    created_at: new Date().toISOString(),
    reactions: [
      { emoji: "🎉", count: 8 },
      { emoji: "🔥", count: 5 },
    ],
    thread: 4,
    isPinned: true,
  },
  {
    id: "2",
    author_name: "Mike Johnson",
    author_avatar: "MJ",
    content: "Amazing work Sarah! That's our biggest deal this quarter.",
    created_at: new Date().toISOString(),
    reactions: [{ emoji: "👏", count: 3 }],
  },
  {
    id: "3",
    author_name: "Emily Davis",
    author_avatar: "ED",
    content:
      "@channel Quick reminder: All Q4 pipeline reviews due by EOD Friday. Please update your opportunities in the CRM.",
    created_at: new Date().toISOString(),
    reactions: [{ emoji: "👍", count: 12 }],
  },
  {
    id: "4",
    author_name: "James Wilson",
    author_avatar: "JW",
    content: "Network team heads up: We're seeing increased latency in the Johannesburg region. Investigating now.",
    created_at: new Date().toISOString(),
    thread: 7,
  },
  {
    id: "5",
    author_name: "Lisa Park",
    author_avatar: "LP",
    content:
      "Customer escalation from TechCorp - they need bandwidth upgrade urgently. Can someone from provisioning assist?",
    created_at: new Date().toISOString(),
    reactions: [{ emoji: "👀", count: 2 }],
  },
]

const seedTasks: Task[] = [
  {
    id: "1",
    title: "Follow up with Meridian contract",
    assignee: "Sarah Chen",
    avatar: "SC",
    status: "in-progress",
    priority: "high",
    dueDate: "Today",
  },
  {
    id: "2",
    title: "Prepare Q4 sales presentation",
    assignee: "Mike Johnson",
    avatar: "MJ",
    status: "todo",
    priority: "medium",
    dueDate: "Tomorrow",
  },
  {
    id: "3",
    title: "Review support ticket backlog",
    assignee: "Emily Davis",
    avatar: "ED",
    status: "done",
    priority: "low",
    dueDate: "Completed",
  },
  {
    id: "4",
    title: "Network capacity planning",
    assignee: "James Wilson",
    avatar: "JW",
    status: "in-progress",
    priority: "high",
    dueDate: "Friday",
  },
  {
    id: "5",
    title: "Update customer onboarding docs",
    assignee: "Lisa Park",
    avatar: "LP",
    status: "todo",
    priority: "medium",
    dueDate: "Next Week",
  },
]

const leads: Lead[] = [
  {
    id: "1",
    name: "David Smith",
    company: "Acme Corp",
    value: "R280,000",
    assignee: "Sarah Chen",
    avatar: "SC",
    status: "qualified",
  },
  {
    id: "2",
    name: "Jennifer Brown",
    company: "GlobalTech",
    value: "R150,000",
    assignee: "Mike Johnson",
    avatar: "MJ",
    status: "contacted",
  },
  {
    id: "3",
    name: "Robert Taylor",
    company: "Innovate Inc",
    value: "R95,000",
    assignee: "Sarah Chen",
    avatar: "SC",
    status: "new",
  },
  {
    id: "4",
    name: "Amanda White",
    company: "Enterprise Co",
    value: "R420,000",
    assignee: "Lisa Park",
    avatar: "LP",
    status: "contacted",
  },
]

const seedEscalations: Escalation[] = [
  {
    id: "1",
    title: "Service outage - Cape Town",
    customer: "TechCorp",
    severity: "critical",
    assignee: "James Wilson",
    avatar: "JW",
    time: "15 min ago",
  },
  {
    id: "2",
    title: "Billing dispute",
    customer: "RetailMax",
    severity: "high",
    assignee: "Emily Davis",
    avatar: "ED",
    time: "1 hour ago",
  },
  {
    id: "3",
    title: "Speed degradation",
    customer: "MediaGroup",
    severity: "medium",
    assignee: "Mike Johnson",
    avatar: "MJ",
    time: "2 hours ago",
  },
]

const REACTION_EMOJIS = ["👍", "❤️", "🎉", "🔥", "👀", "✅", "🙏", "😂"]

// Platform components referenced with "/" in chat.
const PLATFORM_COMPONENTS = [
  "sales", "marketing", "crm", "finance", "network", "support",
  "retention", "inventory", "billing", "analytics", "provisioning",
  "compliance", "portal", "call-center", "hr",
]

const DEFAULT_TEAM_USERS = [
  { id: "u-1", name: "Sarah Chen", email: "sarah.chen@omnidome.co.za" },
  { id: "u-2", name: "Mike Johnson", email: "mike.johnson@omnidome.co.za" },
  { id: "u-3", name: "Emily Davis", email: "emily.davis@omnidome.co.za" },
  { id: "u-4", name: "James Wilson", email: "james.wilson@omnidome.co.za" },
  { id: "u-5", name: "Lisa Park", email: "lisa.park@omnidome.co.za" },
]

export function CommunicationModule() {
  const [channelsExpanded, setChannelsExpanded] = useState(true)
  const [dmExpanded, setDmExpanded] = useState(true)
  const [systemMsgExpanded, setSystemMsgExpanded] = useState(true)
  const [agentMsgExpanded, setAgentMsgExpanded] = useState(true)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true)
  const [selectedChannel, setSelectedChannel] = useState("sales-team")
  const [messageInput, setMessageInput] = useState("")
  const [activeTab, setActiveTab] = useState("chat")
  const [scheduleView, setScheduleView] = useState<"kanban" | "timeline" | "todo" | "activity">("kanban")
  const [scheduleFilter, setScheduleFilter] = useState<"hour" | "day" | "week" | "month">("week")
  const [channels, setChannels] = useState<Channel[]>(seedChannels)
  const [messages, setMessages] = useState<Message[]>(seedMessages)
  const [mutedChannels, setMutedChannels] = useState<string[]>([])
  const [pinnedChannels, setPinnedChannels] = useState<string[]>([])
  const [loadingChannels, setLoadingChannels] = useState(true)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [tasks, setTasks] = useState<Task[]>(seedTasks)
  const [approvals, setApprovals] = useState<AgentApproval[]>(seedApprovals)
  const [escalations, setEscalations] = useState<Escalation[]>(seedEscalations)
  const [scheduleEvents, setScheduleEvents] = useState<ScheduleEvent[]>(seedScheduleEvents)
  const [activityItems, setActivityItems] = useState<ActivityItem[]>([
    {
      id: "activity-1",
      type: "schedule",
      title: "Q4 Pipeline Review scheduled",
      actor: "Sarah Chen",
      time: "2 min ago",
      meta: "Today at 14:00",
    },
    {
      id: "activity-2",
      type: "approval",
      title: "Discount approval requested",
      actor: "Mike Johnson",
      time: "10 min ago",
      meta: "Meridian Corp",
    },
  ])
  const [panelOpen, setPanelOpen] = useState(false)
  const [panelType, setPanelType] = useState<
    "start-chat" | "add-event" | "add-task" | "add-approval" | "add-escalation" | null
  >(null)
  const [startChatMode, setStartChatMode] = useState<"channel" | "dm">("channel")
  const [startChatSubject, setStartChatSubject] = useState("")
  const [startChatParticipants, setStartChatParticipants] = useState("")
  const [startChatNotes, setStartChatNotes] = useState("")
  const [eventTitle, setEventTitle] = useState("")
  const [eventType, setEventType] = useState<ScheduleEvent["type"]>("meeting")
  const [eventDate, setEventDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [eventTime, setEventTime] = useState(() => new Date().toTimeString().slice(0, 5))
  const [eventAssignee, setEventAssignee] = useState("")
  const [eventNotes, setEventNotes] = useState("")
  const [taskTitle, setTaskTitle] = useState("")
  const [taskAssignee, setTaskAssignee] = useState("")
  const [taskPriority, setTaskPriority] = useState<Task["priority"]>("medium")
  const [taskDueDate, setTaskDueDate] = useState("")
  const [taskNotes, setTaskNotes] = useState("")
  const [contextMessageId, setContextMessageId] = useState<string | null>(null)
  const [approvalSubject, setApprovalSubject] = useState("")
  const [approvalApprover, setApprovalApprover] = useState("")
  const [approvalTimeline, setApprovalTimeline] = useState("")
  const [approvalNotes, setApprovalNotes] = useState("")
  const [escalationTitle, setEscalationTitle] = useState("")
  const [escalationSeverity, setEscalationSeverity] = useState<Escalation["severity"]>("medium")
  const [escalationNotes, setEscalationNotes] = useState("")
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [channelMenuId, setChannelMenuId] = useState<string | null>(null)
  const [channelDialogOpen, setChannelDialogOpen] = useState(false)
  const [newChannelName, setNewChannelName] = useState("")
  const [newChannelPrivate, setNewChannelPrivate] = useState(false)
  const [creatingChannel, setCreatingChannel] = useState(false)
  const [teamUsers, setTeamUsers] = useState<{ id: string; name: string; email?: string }[]>(DEFAULT_TEAM_USERS)
  const [selectedInvites, setSelectedInvites] = useState<Set<string>>(new Set())
  const [replyTo, setReplyTo] = useState<Message | null>(null)
  const messageInputRef = useRef<HTMLInputElement>(null)

  const currentUserName = "You"
  const currentUserAvatar = "ME"
  const activeChannel = channels.find((channel) => channel.name === selectedChannel) ?? channels[0]
  const activeChannelId = activeChannel?.id
  const isUuid = (value?: string | null) =>
    !!value &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)

  // ── Real-time auth token ─────────────────────────────────────────────
  const [wsToken, setWsToken] = useState<string | null>(null)
  const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set())
  const typingClearTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setWsToken(data.session?.access_token ?? null)
    })
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setWsToken(session?.access_token ?? null)
    })
    return () => listener.subscription.unsubscribe()
  }, [])

  // ── WebSocket — live message delivery ────────────────────────────────
  const handleIncomingMessage = useCallback((data: { id: string; user_id: string; content: string; created_at: string; [key: string]: unknown }) => {
    setMessages((prev) => {
      // Deduplicate — optimistic messages sent by us are already in state
      if (prev.some((m) => m.id === data.id)) return prev
      return [
        ...prev,
        {
          id: data.id,
          user: data.user_id === "me" ? currentUserName : data.user_id,
          avatar: data.user_id.slice(0, 2).toUpperCase(),
          content: data.content,
          time: new Date(data.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          reactions: [],
          isPinned: false,
        },
      ]
    })
  }, [currentUserName])

  const handleTyping = useCallback(({ user_id }: { user_id: string }) => {
    setTypingUsers((prev) => new Set(prev).add(user_id))
    // Clear indicator after 3 s of silence
    const existing = typingClearTimers.current.get(user_id)
    if (existing) clearTimeout(existing)
    const timer = setTimeout(() => {
      setTypingUsers((prev) => {
        const next = new Set(prev)
        next.delete(user_id)
        return next
      })
    }, 3_000)
    typingClearTimers.current.set(user_id, timer)
  }, [])

  const { connected: wsConnected, sendTyping } = useChannelSocket(
    isUuid(activeChannelId) ? activeChannelId : null,
    wsToken,
    { onMessage: handleIncomingMessage, onTyping: handleTyping },
  )

  useEffect(() => {
    let isMounted = true
    const loadChannels = async () => {
      setLoadingChannels(true)
      try {
        const response = await fetch("/api/chat/channels")
        const payload = await response.json()
        if (!isMounted) return
        if (Array.isArray(payload.data) && payload.data.length > 0) {
          setChannels(payload.data)
          setSelectedChannel((prev) =>
            payload.data.some((channel: Channel) => channel.name === prev) ? prev : payload.data[0].name,
          )
        }
      } catch (error) {
        console.error("Failed to load channels", error)
      } finally {
        if (isMounted) setLoadingChannels(false)
      }
    }

    loadChannels()
    return () => {
      isMounted = false
    }
  }, [])

  useEffect(() => {
    let isMounted = true
    if (!activeChannelId) {
      setMessages(seedMessages)
      return () => {
        isMounted = false
      }
    }
    if (!isUuid(activeChannelId)) {
      setMessages(seedMessages)
      return () => {
        isMounted = false
      }
    }

    const loadMessages = async () => {
      setLoadingMessages(true)
      try {
        const response = await fetch(`/api/chat/messages?channel_id=${activeChannelId}`)
        const payload = await response.json()
        if (!isMounted) return
        if (Array.isArray(payload.data)) {
          setMessages(payload.data)
        }
      } catch (error) {
        console.error("Failed to load messages", error)
      } finally {
        if (isMounted) setLoadingMessages(false)
      }
    }

    loadMessages()
    return () => {
      isMounted = false
    }
  }, [activeChannelId])

  // ── Load tasks + schedule from the backend (kanban/list/to-do live data) ──
  useEffect(() => {
    let isMounted = true
    const loadTasks = async () => {
      try {
        const r = await fetch("/api/tasks")
        const b = await r.json()
        if (!isMounted || !Array.isArray(b.data) || b.data.length === 0) return
        const normalizeTaskStatus = (s?: string): Task["status"] => {
          const v = (s || "").toLowerCase()
          if (["in-progress", "in_progress", "doing", "active"].includes(v)) return "in-progress"
          if (["done", "completed", "complete", "closed"].includes(v)) return "done"
          return "todo" // pending / open / new / unknown → to-do
        }
        setTasks(
          b.data.map((t: any) => ({
            id: t.id,
            title: t.title,
            assignee: t.assignee_name ?? "Unassigned",
            avatar: formatInitials(t.assignee_name) || "NA",
            status: normalizeTaskStatus(t.status),
            priority: (t.priority as Task["priority"]) ?? "medium",
            dueDate: t.due_date ? friendlyDate(t.due_date) : "No due date",
          })),
        )
      } catch (e) {
        console.error("Failed to load tasks", e)
      }
    }
    const loadSchedule = async () => {
      try {
        const r = await fetch("/api/schedule")
        const b = await r.json()
        if (!isMounted || !Array.isArray(b.data) || b.data.length === 0) return
        setScheduleEvents(
          b.data.map((e: any) => ({
            id: e.id,
            title: e.title,
            type: (e.type as ScheduleEvent["type"]) ?? "meeting",
            date: e.date_label || friendlyDate(e.start_time),
            time: e.time_label || formatTime(e.start_time),
            assignee: e.assignee_name || undefined,
            avatar: e.assignee_name ? formatInitials(e.assignee_name) : undefined,
            status: (e.status as ScheduleEvent["status"]) ?? "upcoming",
          })),
        )
      } catch (e) {
        console.error("Failed to load schedule", e)
      }
    }
    void loadTasks()
    void loadSchedule()
    return () => {
      isMounted = false
    }
  }, [])

  // ── Per-channel unread counts (message_count − locally-stored last-seen) ──
  const [channelUnread, setChannelUnread] = useState<Record<string, number>>({})
  const channelCounts = useRef<Record<string, number>>({})

  const refreshUnread = useCallback(async () => {
    try {
      const r = await fetch("/api/chat/channels/summary")
      const b = await r.json()
      if (!Array.isArray(b.data)) return
      let seen: Record<string, number> = {}
      try {
        seen = JSON.parse(localStorage.getItem("comm:lastSeen") || "{}")
      } catch {
        seen = {}
      }
      const counts: Record<string, number> = {}
      const unread: Record<string, number> = {}
      for (const row of b.data) {
        const id = row.channel_id
        const count = Number(row.message_count || 0)
        counts[id] = count
        unread[id] = Math.max(0, count - (seen[id] ?? 0))
      }
      channelCounts.current = counts
      setChannelUnread(unread)
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    void refreshUnread()
    const t = setInterval(() => void refreshUnread(), 30_000)
    return () => clearInterval(t)
  }, [refreshUnread])

  // Opening a channel marks it read: store its current count as last-seen.
  useEffect(() => {
    if (!isUuid(activeChannelId)) return
    const id = activeChannelId as string
    const markRead = () => {
      try {
        const seen = JSON.parse(localStorage.getItem("comm:lastSeen") || "{}")
        seen[id] = channelCounts.current[id] ?? seen[id] ?? 0
        localStorage.setItem("comm:lastSeen", JSON.stringify(seen))
      } catch {
        /* ignore */
      }
      setChannelUnread((prev) => ({ ...prev, [id]: 0 }))
    }
    // small delay so a freshly-loaded count is available
    const t = setTimeout(markRead, 800)
    return () => clearTimeout(t)
  }, [activeChannelId, messages.length])

  const formatTime = (value?: string | null) => {
    if (!value) return ""
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ""
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  }

  const formatInitials = (name?: string | null) => {
    if (!name) return "??"
    return name
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("")
  }

  // Friendly relative label from an ISO datetime, using the real system date.
  const friendlyDate = (iso?: string | null) => {
    if (!iso) return ""
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso || ""
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const target = new Date(d)
    target.setHours(0, 0, 0, 0)
    const diff = Math.round((target.getTime() - today.getTime()) / 86_400_000)
    if (diff === 0) return "Today"
    if (diff === 1) return "Tomorrow"
    if (diff === -1) return "Yesterday"
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
  }

  // Digest of upcoming schedule + open tasks, handed to the agent chat so the
  // agent is aware of what the team has planned.
  const agentScheduleContext = (() => {
    const up = scheduleEvents.filter((e) => e.status !== "completed").slice(0, 8)
    const td = tasks.filter((t) => t.status !== "done").slice(0, 8)
    const parts: string[] = []
    if (up.length)
      parts.push(
        "Upcoming schedule:\n" +
          up.map((e) => `- ${e.title} (${e.date} ${e.time}${e.assignee ? `, ${e.assignee}` : ""})`).join("\n"),
      )
    if (td.length)
      parts.push(
        "Open tasks:\n" +
          td.map((t) => `- ${t.title} [${t.status}, ${t.priority}${t.dueDate ? `, due ${t.dueDate}` : ""}]`).join("\n"),
      )
    return parts.join("\n\n")
  })()

  const openPanel = (
    type: "start-chat" | "add-event" | "add-task" | "add-approval" | "add-escalation",
    message?: Message,
  ) => {
    if (message?.content) {
      if (type === "add-task") {
        setTaskTitle(message.content.slice(0, 120))
      }
      if (type === "add-approval") {
        setApprovalSubject(message.content.slice(0, 120))
      }
      if (type === "add-escalation") {
        setEscalationTitle(message.content.slice(0, 120))
      }
      if (type === "add-event") {
        setEventTitle(message.content.slice(0, 120))
      }
      setApprovalNotes(message.content)
      setTaskNotes(message.content)
      setEscalationNotes(message.content)
      setEventNotes(message.content)
    }
    setContextMessageId(message?.id ?? null)
    setPanelType(type)
    setPanelOpen(true)
  }

  const postJson = async (url: string, payload: Record<string, unknown>) => {
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      return await response.json()
    } catch (error) {
      console.error(`Failed POST ${url}`, error)
      return null
    }
  }

  const patchJson = async (url: string, payload: Record<string, unknown>) => {
    try {
      const response = await fetch(url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      return await response.json()
    } catch (error) {
      console.error(`Failed PATCH ${url}`, error)
      return null
    }
  }

  const closePanel = () => {
    setPanelOpen(false)
    setPanelType(null)
  }

  const persistChannelPreference = async (channelName: string, nextMuted: boolean, nextPinned: boolean) => {
    const channel = channels.find((item) => item.name === channelName)
    if (!channel) return
    await fetch(`/api/chat/channels/${channel.id}/preferences`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ muted: nextMuted, pinned: nextPinned }),
    })
  }

  const addActivity = (item: ActivityItem) => {
    setActivityItems((prev) => [item, ...prev])
  }

  const filteredScheduleEvents = (() => {
    if (scheduleFilter === "month") return scheduleEvents
    if (scheduleFilter === "week") {
      return scheduleEvents.filter((event) =>
        ["Today", "Tomorrow", "Thursday", "Friday"].includes(event.date),
      )
    }
    return scheduleEvents.filter((event) => event.date === "Today")
  })()

  const priorityColors = {
    low: "bg-blue-500/20 text-blue-400",
    medium: "bg-yellow-500/20 text-yellow-400",
    high: "bg-red-500/20 text-red-400",
  }

  const eventTypeColors = {
    meeting: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    task: "bg-green-500/20 text-green-400 border-green-500/30",
    reminder: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    deadline: "bg-red-500/20 text-red-400 border-red-500/30",
  }

  const approvalTypeColors = {
    discount: "bg-purple-500/20 text-purple-400",
    refund: "bg-red-500/20 text-red-400",
    credit: "bg-blue-500/20 text-blue-400",
    override: "bg-orange-500/20 text-orange-400",
  }

  const severityColors = {
    low: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    medium: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    high: "bg-orange-500/20 text-orange-400 border-orange-500/30",
    critical: "bg-red-500/20 text-red-400 border-red-500/30",
  }

  const kanbanItems = [
    ...filteredScheduleEvents.map((event) => ({
      id: event.id,
      type: "schedule" as const,
      title: event.title,
      status: event.status,
      meta: `${event.date} at ${event.time}`,
      assignee: event.assignee,
      avatar: event.avatar,
      colorClass: eventTypeColors[event.type],
    })),
    ...tasks.map((task) => ({
      id: task.id,
      type: "task" as const,
      title: task.title,
      status: task.status === "done" ? "completed" : task.status === "in-progress" ? "in-progress" : "upcoming",
      meta: `Task • ${task.dueDate}`,
      assignee: task.assignee,
      avatar: task.avatar,
      colorClass: priorityColors[task.priority],
    })),
    ...approvals.map((approval) => ({
      id: approval.id,
      type: "approval" as const,
      title: approval.customer,
      status: approval.status === "approved" ? "completed" : "upcoming",
      meta: `Approval • ${approval.amount}`,
      assignee: approval.agent,
      avatar: approval.avatar,
      colorClass: approvalTypeColors[approval.type],
    })),
    ...escalations.map((esc) => ({
      id: esc.id,
      type: "escalation" as const,
      title: esc.title,
      status: esc.status === "resolved" ? "completed" : "in-progress",
      meta: `Escalation • ${esc.severity}`,
      assignee: esc.assignee,
      avatar: esc.avatar,
      colorClass: severityColors[esc.severity],
    })),
  ]

  const [isRecordingVoice, setIsRecordingVoice] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [speakingMessageId, setSpeakingMessageId] = useState<string | null>(null)
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const voiceRecorder = useRef<MediaRecorder | null>(null)
  const voiceChunks = useRef<Blob[]>([])

  const startVoiceRecording = useCallback(async () => {
    setVoiceError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : ""
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
      voiceChunks.current = []
      recorder.ondataavailable = (e) => e.data.size > 0 && voiceChunks.current.push(e.data)
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const rawBlob = new Blob(voiceChunks.current, { type: mimeType || "audio/webm" })
        if (rawBlob.size < 100) {
          setVoiceError("No audio captured — hold the button while speaking, then release.")
          return
        }
        const stats = await toWavWithStats(rawBlob).catch(() => null)
        if (stats && stats.rms < SILENCE_RMS_THRESHOLD) {
          setVoiceError(
            "The recording contains no sound — Windows is likely capturing the wrong microphone. Check Settings → System → Sound → Input.",
          )
          return
        }
        const wavBlob = stats ? stats.wav : rawBlob
        setIsTranscribing(true)
        try {
          const result = await voiceboxTranscribe(wavBlob)
          if (result.text?.trim()) {
            setMessageInput((prev) => (prev ? `${prev} ${result.text}` : result.text).trim())
          }
        } catch (err) {
          console.error("Voice transcription failed", err)
          setVoiceError(err instanceof Error ? err.message : "Transcription failed")
        } finally {
          setIsTranscribing(false)
        }
      }
      recorder.start(250)
      voiceRecorder.current = recorder
      setIsRecordingVoice(true)
    } catch (err) {
      console.error("Microphone access denied", err)
      setVoiceError(
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone access denied — allow it in your browser's site permissions."
          : "Could not access microphone",
      )
    }
  }, [])

  const stopVoiceRecording = useCallback(() => {
    voiceRecorder.current?.stop()
    setIsRecordingVoice(false)
  }, [])

  const handleSpeakMessage = async (msg: { id: string; content: string }) => {
    if (!msg.content?.trim()) return
    setSpeakingMessageId(msg.id)
    setVoiceError(null)
    try {
      const blob = await voiceboxSpeak({
        text: msg.content,
        scope: "webchat_bot",
        scope_ref: "default",
        requested_by_service: "webchat",
      })
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audio.onended = () => setSpeakingMessageId(null)
      audio.onerror = () => setSpeakingMessageId(null)
      await audio.play()
    } catch (err) {
      console.error("Speak failed", err)
      setVoiceError(
        err instanceof Error
          ? `${err.message} — bind a voice to the webchat bot in Call Center → Voice Studio first.`
          : "Speech playback failed",
      )
      setSpeakingMessageId(null)
    }
  }

  const handleSend = async () => {
    const trimmed = messageInput.trim()
    if (!trimmed || !activeChannelId) return
    // Prepend a quote line when replying so the thread context is visible.
    const content = replyTo
      ? `↳ @${(replyTo.author_name ?? "user").replace(/\s+/g, "")}: ${(replyTo.content ?? "").slice(0, 80)}\n${trimmed}`
      : trimmed
    const payload = {
      channel_id: activeChannelId,
      content,
      author_name: currentUserName,
      author_avatar: currentUserAvatar,
    }

    try {
      const response = await fetch("/api/chat/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      const result = await response.json()
      const created = Array.isArray(result.data) ? result.data[0] : null
      if (created) {
        setMessages((prev) => [...prev, created])
        setMessageInput("")
        setReplyTo(null)
      }
    } catch (error) {
      console.error("Failed to send message", error)
    }
  }

  const handleStartChat = () => {
    const channelId = activeChannelId
    if (!channelId) return
    void postJson("/api/chat/sessions", {
      channel_id: channelId,
      session_type: "chat",
      provider_name: "chat",
      participants: startChatParticipants
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
        .map((name) => ({ name })),
      metadata: {
        mode: startChatMode,
        subject: startChatSubject,
        notes: startChatNotes,
      },
    })
    addActivity({
      id: `activity-${Date.now()}`,
      type: "chat",
      title: startChatSubject ? `Chat started: ${startChatSubject}` : "Chat started",
      actor: currentUserName,
      time: "just now",
      meta: startChatMode === "dm" ? "Direct message" : `#${activeChannel?.name ?? selectedChannel}`,
    })
    setActiveTab("chat")
    setStartChatSubject("")
    setStartChatParticipants("")
    setStartChatNotes("")
    closePanel()
  }

  const handleStartCall = (mode: "voice" | "video") => {
    if (!activeChannelId) return
    void postJson("/api/chat/sessions", {
      channel_id: activeChannelId,
      session_type: mode,
      provider_name: mode === "voice" ? "call-provider" : "video-provider",
      participants: [],
      metadata: {
        channel_name: activeChannel?.name ?? selectedChannel,
        channel_id: activeChannelId,
      },
    })
    addActivity({
      id: `activity-${Date.now()}`,
      type: "chat",
      title: mode === "voice" ? "Voice call started" : "Video call started",
      actor: currentUserName,
      time: "just now",
      meta: `#${activeChannel?.name ?? selectedChannel}`,
    })
  }

  // Load the team directory on mount (for @mentions + the invite picker).
  useEffect(() => {
    let cancelled = false
    fetch("/api/chat/users")
      .then((r) => r.json())
      .then((b) => {
        if (!cancelled && Array.isArray(b.data) && b.data.length > 0) setTeamUsers(b.data)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  // Dismiss open panels, dialogs, and replies with Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        closePanel()
        setReplyTo(null)
        setChannelDialogOpen(false)
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  const toggleInvite = (id: string) =>
    setSelectedInvites((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const handleCreateChannel = async () => {
    const name = newChannelName.trim().toLowerCase().replace(/\s+/g, "-")
    if (!name || creatingChannel) return
    setCreatingChannel(true)
    try {
      const r = await fetch("/api/chat/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, is_private: newChannelPrivate }),
      })
      const created = await r.json()
      if (r.ok && created?.id) {
        // Invite selected members.
        const invites = Array.from(selectedInvites)
        if (invites.length > 0) {
          try {
            await fetch(`/api/chat/channels/${created.id}/members`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ user_ids: invites }),
            })
          } catch (e) {
            console.error("Failed to invite members", e)
          }
        }
        setChannels((prev) => [
          { id: created.id, name: created.name, isPrivate: created.is_private },
          ...prev.filter((c) => c.id !== created.id),
        ])
        setSelectedChannel(created.name)
        addActivity({
          id: `activity-${Date.now()}-channel`,
          type: "chat",
          title: `Channel created: #${created.name}`,
          actor: currentUserName,
          time: "just now",
          meta: `${created.is_private ? "Private" : "Public"}${invites.length ? ` · ${invites.length} invited` : ""}`,
        })
        setChannelDialogOpen(false)
        setNewChannelName("")
        setNewChannelPrivate(false)
        setSelectedInvites(new Set())
      }
    } catch (e) {
      console.error("Failed to create channel", e)
    } finally {
      setCreatingChannel(false)
    }
  }

  const addReaction = (msgId: string, emoji: string) => {
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== msgId) return m
        const rx = m.reactions ? [...m.reactions] : []
        const i = rx.findIndex((r) => r.emoji === emoji)
        if (i >= 0) rx[i] = { ...rx[i], count: rx[i].count + 1 }
        else rx.push({ emoji, count: 1 })
        return { ...m, reactions: rx }
      }),
    )
  }

  const startReply = (msg: Message) => {
    setReplyTo(msg)
    setActiveTab("chat")
    setTimeout(() => messageInputRef.current?.focus(), 50)
  }

  // ── @mention / /component autocomplete (computed from the current input) ──
  const lastToken = messageInput.split(/\s/).pop() ?? ""
  const mentionActive = lastToken.startsWith("@") && lastToken.length >= 1
  const slashActive = lastToken.startsWith("/") && lastToken.length >= 1
  const mentionMatches = mentionActive
    ? teamUsers.filter((u) => u.name.toLowerCase().includes(lastToken.slice(1).toLowerCase())).slice(0, 6)
    : []
  const slashMatches = slashActive
    ? PLATFORM_COMPONENTS.filter((c) => c.startsWith(lastToken.slice(1).toLowerCase())).slice(0, 8)
    : []
  const autocompleteOpen = (mentionActive && mentionMatches.length > 0) || (slashActive && slashMatches.length > 0)

  const applyAutocomplete = (prefix: "@" | "/", value: string) => {
    const idx = messageInput.lastIndexOf(lastToken)
    const next = messageInput.slice(0, idx) + prefix + value + " "
    setMessageInput(next)
    setTimeout(() => messageInputRef.current?.focus(), 20)
  }

  const handleAddEvent = () => {
    if (!eventTitle.trim()) return
    const contextId = contextMessageId && isUuid(contextMessageId) ? contextMessageId : null
    // Build real start/end datetimes from the picked date + time (system tz).
    const start = new Date(`${eventDate}T${eventTime || "09:00"}`)
    const validStart = Number.isNaN(start.getTime()) ? new Date() : start
    const end = new Date(validStart.getTime() + 60 * 60 * 1000)
    const timeLabel = validStart.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    const newEvent: ScheduleEvent = {
      id: `event-${Date.now()}`,
      title: eventTitle.trim(),
      type: eventType,
      date: friendlyDate(validStart.toISOString()),
      time: timeLabel,
      assignee: eventAssignee || undefined,
      avatar: eventAssignee ? formatInitials(eventAssignee) : undefined,
      status: "upcoming",
    }
    setScheduleEvents((prev) => [newEvent, ...prev])
    void (async () => {
      if (!isUuid(activeChannelId)) return
      const result = await postJson("/api/schedule", {
        channel_id: activeChannelId,
        title: newEvent.title,
        type: newEvent.type,
        start_time: validStart.toISOString(),
        end_time: end.toISOString(),
        date_label: newEvent.date,
        time_label: timeLabel,
        notes: eventNotes,
        source_message_id: contextId,
        status: newEvent.status,
      })
      const created = result?.data
      const createdId = Array.isArray(created) ? created[0]?.id : created?.id
      if (createdId) {
        setScheduleEvents((prev) => prev.map((event) => (event.id === newEvent.id ? { ...event, id: createdId } : event)))
      }
    })()
    addActivity({
      id: `activity-${Date.now()}-event`,
      type: "schedule",
      title: `Event added: ${newEvent.title}`,
      actor: currentUserName,
      time: "just now",
      meta: `${newEvent.date} at ${newEvent.time}`,
    })
    setEventTitle("")
    setEventAssignee("")
    setEventNotes("")
    closePanel()
  }

  const handleAddTask = () => {
    if (!taskTitle.trim()) return
    const contextId = contextMessageId && isUuid(contextMessageId) ? contextMessageId : null
    const newTask: Task = {
      id: `task-${Date.now()}`,
      title: taskTitle.trim(),
      assignee: taskAssignee || "Unassigned",
      avatar: taskAssignee
        ? taskAssignee
            .split(" ")
            .filter(Boolean)
            .slice(0, 2)
            .map((part) => part[0]?.toUpperCase())
            .join("")
        : "NA",
      status: "todo",
      priority: taskPriority,
      dueDate: taskDueDate || "No due date",
    }
    setTasks((prev) => [newTask, ...prev])
    void (async () => {
      if (!isUuid(activeChannelId)) return
      const result = await postJson("/api/tasks", {
        channel_id: activeChannelId,
        title: newTask.title,
        description: taskNotes || null,
        message_id: contextId,
      })
      const created = result?.data?.[0] ?? result?.data
      if (created?.id) {
        setTasks((prev) => prev.map((task) => (task.id === newTask.id ? { ...task, id: created.id } : task)))
      }
    })()
    addActivity({
      id: `activity-${Date.now()}-task`,
      type: "task",
      title: `Task created: ${newTask.title}`,
      actor: currentUserName,
      time: "just now",
      meta: newTask.assignee,
    })
    setTaskTitle("")
    setTaskAssignee("")
    setTaskDueDate("")
    setTaskNotes("")
    closePanel()
  }

  const handleAddApproval = () => {
    if (!approvalSubject.trim()) return
    const contextId = contextMessageId && isUuid(contextMessageId) ? contextMessageId : null
    const newApproval: AgentApproval = {
      id: `approval-${Date.now()}`,
      agent: currentUserName,
      avatar: currentUserAvatar,
      type: "override",
      customer: approvalSubject.trim(),
      amount: "Pending",
      reason: approvalNotes || "Approval requested",
      status: "pending",
      time: "just now",
    }
    setApprovals((prev) => [newApproval, ...prev])
    void (async () => {
      const result = await postJson("/api/approvals", {
        subject: approvalSubject.trim(),
        type: newApproval.type,
        status: newApproval.status,
        amount: newApproval.amount,
        reason: newApproval.reason,
        timeline: approvalTimeline,
        notes: approvalNotes,
        source_message_id: contextId,
      })
      const created = result?.data?.[0]
      if (created?.id) {
        setApprovals((prev) =>
          prev.map((approval) => (approval.id === newApproval.id ? { ...approval, id: created.id } : approval)),
        )
      }
    })()
    addActivity({
      id: `activity-${Date.now()}-approval`,
      type: "approval",
      title: `Approval requested: ${approvalSubject.trim()}`,
      actor: currentUserName,
      time: "just now",
      meta: approvalApprover || "Approver TBD",
    })
    setApprovalSubject("")
    setApprovalApprover("")
    setApprovalTimeline("")
    setApprovalNotes("")
    closePanel()
  }

  const handleAddEscalation = () => {
    if (!escalationTitle.trim()) return
    const contextId = contextMessageId && isUuid(contextMessageId) ? contextMessageId : null
    const newEscalation: Escalation = {
      id: `escalation-${Date.now()}`,
      title: escalationTitle.trim(),
      customer: "Customer",
      severity: escalationSeverity,
      assignee: currentUserName,
      avatar: currentUserAvatar,
      time: "just now",
      status: "open",
    }
    setEscalations((prev) => [newEscalation, ...prev])
    void (async () => {
      const result = await postJson("/api/escalations", {
        title: newEscalation.title,
        customer: newEscalation.customer,
        severity: newEscalation.severity,
        status: newEscalation.status,
        notes: escalationNotes,
        source_message_id: contextId,
      })
      const created = result?.data?.[0]
      if (created?.id) {
        setEscalations((prev) =>
          prev.map((esc) => (esc.id === newEscalation.id ? { ...esc, id: created.id } : esc)),
        )
      }
    })()
    addActivity({
      id: `activity-${Date.now()}-escalation`,
      type: "escalation",
      title: `Escalation created: ${escalationTitle.trim()}`,
      actor: currentUserName,
      time: "just now",
      meta: escalationSeverity,
    })
    setEscalationTitle("")
    setEscalationNotes("")
    closePanel()
  }

  const handleApprovalAction = async (approvalId: string, action: "approve" | "reject") => {
    const newStatus = action === "approve" ? "approved" : "rejected"
    setApprovals((prev) =>
      prev.map((a) => (a.id === approvalId ? { ...a, status: newStatus } : a)),
    )
    if (isUuid(approvalId)) {
      await patchJson("/api/approvals", { id: approvalId, status: newStatus })
    }
    addActivity({
      id: `activity-${Date.now()}-approval-${action}`,
      type: "approval",
      title: `Approval ${action}d`,
      actor: currentUserName,
      time: "just now",
      meta: approvalId,
    })
  }

  const handleKanbanDrop = (column: "upcoming" | "in-progress" | "completed", payload?: string) => {
    if (!payload) return
    const [type, id] = payload.split(":")
    if (!type || !id) return

    if (type === "schedule") {
      setScheduleEvents((prev) =>
        prev.map((event) => (event.id === id ? { ...event, status: column } : event)),
      )
      if (isUuid(id)) {
        void patchJson("/api/schedule", { id, status: column })
      }
      addActivity({
        id: `activity-${Date.now()}-schedule-move`,
        type: "schedule",
        title: `Schedule moved to ${column}`,
        actor: currentUserName,
        time: "just now",
        meta: id,
      })
      return
    }

    if (type === "task") {
      const statusMap = {
        "upcoming": "todo",
        "in-progress": "in-progress",
        "completed": "done",
      } as const
      setTasks((prev) => prev.map((task) => (task.id === id ? { ...task, status: statusMap[column] } : task)))
      if (isUuid(id)) {
        void patchJson("/api/tasks", { id, status: statusMap[column] })
      }
      addActivity({
        id: `activity-${Date.now()}-task-move`,
        type: "task",
        title: `Task moved to ${column}`,
        actor: currentUserName,
        time: "just now",
        meta: id,
      })
      return
    }

    if (type === "approval") {
      const statusMap = {
        "upcoming": "pending",
        "in-progress": "pending",
        "completed": "approved",
      } as const
      setApprovals((prev) =>
        prev.map((approval) => (approval.id === id ? { ...approval, status: statusMap[column] } : approval)),
      )
      if (isUuid(id)) {
        void patchJson("/api/approvals", { id, status: statusMap[column] })
      }
      addActivity({
        id: `activity-${Date.now()}-approval-move`,
        type: "approval",
        title: `Approval moved to ${column}`,
        actor: currentUserName,
        time: "just now",
        meta: id,
      })
      return
    }

    if (type === "escalation") {
      const status = column === "completed" ? "resolved" : "open"
      setEscalations((prev) =>
        prev.map((esc) => (esc.id === id ? { ...esc, status } : esc)),
      )
      if (isUuid(id)) {
        void patchJson("/api/escalations", { id, status })
      }
      addActivity({
        id: `activity-${Date.now()}-escalation-move`,
        type: "escalation",
        title: `Escalation moved to ${column}`,
        actor: currentUserName,
        time: "just now",
        meta: id,
      })
    }
  }

  const statusColors = {
    online: "bg-green-500",
    away: "bg-yellow-500",
    offline: "bg-muted-foreground/50",
  }

  const leadStatusColors = {
    new: "bg-purple-500/20 text-purple-400",
    contacted: "bg-blue-500/20 text-blue-400",
    qualified: "bg-green-500/20 text-green-400",
  }

  const taskStatusIcons = {
    todo: <Circle className="h-4 w-4 text-muted-foreground" />,
    "in-progress": <Clock className="h-4 w-4 text-yellow-400" />,
    done: <CheckCircle2 className="h-4 w-4 text-green-400" />,
  }

  const systemMsgIcons = {
    alert: <AlertCircle className="h-4 w-4 text-red-400" />,
    notification: <Bell className="h-4 w-4 text-blue-400" />,
    update: <Zap className="h-4 w-4 text-green-400" />,
    warning: <AlertCircle className="h-4 w-4 text-yellow-400" />,
  }

  return (
    <div className="flex h-full w-full min-h-0 flex-1 flex-col gap-0 rounded-xl border border-border bg-card lg:flex-row lg:overflow-hidden">
      {mobileSidebarOpen && (
        <button
          type="button"
          aria-label="Close channels"
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}
      {/* Sidebar - Channels & DMs */}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-shrink-0 flex-col border-r border-border bg-sidebar transition-all duration-300 lg:static lg:z-auto lg:translate-x-0",
          sidebarCollapsed ? "w-16" : "w-72",
          mobileSidebarOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="p-3 border-b border-border">
          <div className={cn("flex items-center mb-2", sidebarCollapsed ? "justify-center" : "justify-between")}>
            {!sidebarCollapsed && (
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Channels</span>
            )}
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground"
                onClick={() => setSidebarCollapsed((prev) => !prev)}
                title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              >
                {sidebarCollapsed ? <PanelRightClose className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground lg:hidden"
                onClick={() => setMobileSidebarOpen(false)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
          {!sidebarCollapsed && (
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="Search messages..." className="h-9 bg-secondary pl-9 text-sm" />
            </div>
          )}
        </div>
        <ScrollArea className="flex-1">
          <div className="p-2">
            <div className={cn("mb-3 grid gap-1", sidebarCollapsed ? "grid-cols-1" : "grid-cols-3")}>
              {[
                { value: "chat", icon: MessageSquare, label: "Chat" },
                { value: "agents", icon: Bot, label: "Agent" },
                { value: "tasks", icon: ListTodo, label: "Tasks" },
                { value: "approvals", icon: CheckSquare, label: "Approvals" },
                { value: "escalations", icon: Flag, label: "Escalations" },
                { value: "schedule", icon: Calendar, label: "Schedule" },
              ].map((item) => {
                const Icon = item.icon
                return (
                  <Button
                    key={item.value}
                    variant={activeTab === item.value ? "secondary" : "ghost"}
                    size="sm"
                    className={cn("h-9 justify-start gap-2", sidebarCollapsed && "justify-center px-0")}
                    onClick={() => setActiveTab(item.value)}
                  >
                    <Icon className="h-4 w-4" />
                    {!sidebarCollapsed && <span className="text-xs">{item.label}</span>}
                  </Button>
                )
              })}
            </div>
            {!sidebarCollapsed && <div className="mb-2 border-t border-border" />}
            {/* Channels Section */}
            {!sidebarCollapsed && (
              <button
                onClick={() => setChannelsExpanded(!channelsExpanded)}
                className="flex w-full items-center gap-1 px-2 py-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground"
              >
                {channelsExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                Channels
              </button>
            )}
            {sidebarCollapsed ? (
              <div className="space-y-1">
                {channels.map((channel) => {
                  const isActive = selectedChannel === channel.name
                  const isPrivate = channel.isPrivate ?? (channel as any).is_private
                  const unread = channelUnread[channel.id] ?? channel.unread ?? 0
                  return (
                    <button
                      key={channel.id}
                      onClick={() => {
                        setSelectedChannel(channel.name)
                        setMobileSidebarOpen(false)
                      }}
                      title={`#${channel.name}${unread > 0 ? ` (${unread} unread)` : ""}`}
                      className={cn(
                        "relative flex h-9 w-9 mx-auto items-center justify-center rounded-lg transition-colors",
                        isActive
                          ? "bg-primary/10 text-primary font-bold"
                          : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                      )}
                    >
                      {isPrivate ? <Lock className="h-4 w-4" /> : <Hash className="h-4 w-4" />}
                      {unread > 0 && (
                        <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-primary" />
                      )}
                    </button>
                  )
                })}
              </div>
            ) : channelsExpanded ? (
              <div className="space-y-0.5">
                {loadingChannels && (
                  <div className="px-2 py-1 text-xs text-muted-foreground">Loading channels...</div>
                )}
                {channels.map((channel) => {
                  const isActive = selectedChannel === channel.name
                  const isPrivate = channel.isPrivate ?? (channel as any).is_private
                  const unread = channelUnread[channel.id] ?? channel.unread ?? 0
                  return (
                    <div key={channel.id} className="relative">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => {
                            setSelectedChannel(channel.name)
                            setMobileSidebarOpen(false)
                            setChannelMenuId(null)
                          }}
                          className={cn(
                            "flex flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                            isActive
                              ? "bg-primary/10 text-primary"
                              : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                          )}
                        >
                          {isPrivate ? <Lock className="h-4 w-4" /> : <Hash className="h-4 w-4" />}
                          <span className="flex-1 truncate text-left">{channel.name}</span>
                          {unread > 0 && (
                            <Badge variant="secondary" className="h-5 min-w-5 bg-primary text-primary-foreground text-xs">
                              {unread}
                            </Badge>
                          )}
                        </button>
                        <DropdownMenu open={channelMenuId === channel.id} onOpenChange={(open) => setChannelMenuId(open ? channel.id : null)}>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-muted-foreground hover:text-foreground"
                              onClick={(event) => {
                                event.stopPropagation()
                                setChannelMenuId(channelMenuId === channel.id ? null : channel.id)
                              }}
                            >
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-44">
                            <DropdownMenuItem
                              className="gap-2"
                              onClick={() => {
                                const nextPinned = !pinnedChannels.includes(channel.name)
                                const nextMuted = mutedChannels.includes(channel.name)
                                setPinnedChannels((prev) =>
                                   nextPinned ? [channel.name, ...prev.filter((item) => item !== channel.name)] : prev.filter((item) => item !== channel.name),
                                )
                                void persistChannelPreference(channel.name, nextMuted, nextPinned)
                              }}
                            >
                              <Edit3 className="h-4 w-4" />
                              {pinnedChannels.includes(channel.name) ? "Unpin" : "Pin"}
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="gap-2"
                              onClick={() => {
                                const nextMuted = !mutedChannels.includes(channel.name)
                                const nextPinned = pinnedChannels.includes(channel.name)
                                setMutedChannels((prev) =>
                                  nextMuted ? [channel.name, ...prev.filter((item) => item !== channel.name)] : prev.filter((item) => item !== channel.name),
                                )
                                void persistChannelPreference(channel.name, nextMuted, nextPinned)
                              }}
                            >
                              <Bell className="h-4 w-4" />
                              {mutedChannels.includes(channel.name) ? "Unmute" : "Mute"}
                            </DropdownMenuItem>
                            <DropdownMenuItem className="gap-2" onClick={() => setSelectedChannel(channel.name)}>
                              <MessageSquare className="h-4 w-4" />
                              Focus
                            </DropdownMenuItem>
                            <DropdownMenuItem className="gap-2">
                              <Pin className="h-4 w-4" />
                              Details
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                      {(mutedChannels.includes(channel.name) || pinnedChannels.includes(channel.name)) && (
                        <div className="mt-1 flex items-center gap-2 px-2">
                          {pinnedChannels.includes(channel.name) && (
                            <Badge variant="secondary" className="h-5 bg-amber-500/15 text-[10px] text-amber-400">
                              Pinned
                            </Badge>
                          )}
                          {mutedChannels.includes(channel.name) && (
                            <Badge variant="secondary" className="h-5 bg-muted text-[10px] text-muted-foreground">
                              Muted
                            </Badge>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
                <button
                  onClick={() => setChannelDialogOpen(true)}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground"
                >
                  <Plus className="h-4 w-4" />
                  <span>Add Channel</span>
                </button>
              </div>
            ) : null}

            {/* Direct Messages Section */}
            {sidebarCollapsed ? (
              <div className="mt-3 space-y-1 border-t border-border pt-2">
                {directMessages.map((dm) => (
                  <button
                    key={dm.id}
                    onClick={() => setMobileSidebarOpen(false)}
                    title={dm.name}
                    className="relative flex h-9 w-9 mx-auto items-center justify-center rounded-lg hover:bg-secondary transition-colors"
                  >
                    <Avatar className="h-7 w-7">
                      <AvatarFallback className="text-[10px] bg-primary/20 text-primary">{dm.avatar}</AvatarFallback>
                    </Avatar>
                    <span
                      className={cn(
                        "absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-sidebar",
                        statusColors[dm.status],
                      )}
                    />
                  </button>
                ))}
              </div>
            ) : (
              <>
                <button
                  onClick={() => setDmExpanded(!dmExpanded)}
                  className="flex w-full items-center gap-1 px-2 py-1.5 mt-4 text-xs font-semibold text-muted-foreground hover:text-foreground"
                >
                  {dmExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  Direct Messages
                </button>
                {dmExpanded && (
                  <div className="space-y-0.5">
                    {directMessages.map((dm) => (
                      <button
                        key={dm.id}
                        onClick={() => setMobileSidebarOpen(false)}
                        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground"
                      >
                        <div className="relative">
                          <Avatar className="h-6 w-6">
                            <AvatarFallback className="text-xs bg-primary/20 text-primary">{dm.avatar}</AvatarFallback>
                          </Avatar>
                          <span
                            className={cn(
                              "absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-sidebar",
                              statusColors[dm.status],
                            )}
                          />
                        </div>
                        <span className="flex-1 text-left truncate">{dm.name}</span>
                        {dm.unread && (
                          <Badge variant="secondary" className="h-5 min-w-5 bg-primary text-primary-foreground text-xs">
                            {dm.unread}
                          </Badge>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}

            {!sidebarCollapsed && (
              <button
                onClick={() => setSystemMsgExpanded(!systemMsgExpanded)}
                className="flex w-full items-center gap-1 px-2 py-1.5 mt-4 text-xs font-semibold text-muted-foreground hover:text-foreground"
              >
                {systemMsgExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                <Server className="h-3 w-3 mr-1" />
                System Messages
                <Badge variant="secondary" className="ml-auto h-4 min-w-4 bg-red-500/20 text-red-400 text-[10px]">
                  {systemMessages.filter((m) => !m.read).length}
                </Badge>
              </button>
            )}
            {!sidebarCollapsed && systemMsgExpanded && (
              <div className="space-y-0.5">
                {systemMessages.map((msg) => (
                  <button
                    key={msg.id}
                    onClick={() => setMobileSidebarOpen(false)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                      !msg.read
                        ? "bg-secondary/50 text-foreground"
                        : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                    )}
                  >
                    {systemMsgIcons[msg.type]}
                    <div className="flex-1 text-left truncate">
                      <span className="text-xs">{msg.title}</span>
                    </div>
                    {!msg.read && <span className="h-2 w-2 rounded-full bg-primary" />}
                  </button>
                ))}
              </div>
            )}

            {!sidebarCollapsed && (
              <>
                <button
                  onClick={() => setAgentMsgExpanded(!agentMsgExpanded)}
                  className="flex w-full items-center gap-1 px-2 py-1.5 mt-4 text-xs font-semibold text-muted-foreground hover:text-foreground"
                >
                  {agentMsgExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  <Bot className="h-3 w-3 mr-1" />
                  Agent Approvals
                  <Badge variant="secondary" className="ml-auto h-4 min-w-4 bg-orange-500/20 text-orange-400 text-[10px]">
                    {approvals.filter((a) => a.status === "pending").length}
                  </Badge>
                </button>
                {agentMsgExpanded && (
                  <div className="space-y-0.5">
                    {approvals
                      .filter((a) => a.status === "pending")
                      .slice(0, 4)
                      .map((approval) => (
                        <button
                          key={approval.id}
                          onClick={() => setActiveTab("approvals")}
                          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground"
                        >
                          <Avatar className="h-5 w-5">
                            <AvatarFallback className="text-[10px] bg-primary/20 text-primary">
                              {approval.avatar}
                            </AvatarFallback>
                          </Avatar>
                          <div className="flex-1 text-left truncate">
                            <span className="text-xs">
                              {approval.type} - {approval.amount}
                            </span>
                          </div>
                          <Clock className="h-3 w-3 text-orange-400" />
                        </button>
                      ))}
                    <button
                      onClick={() => setActiveTab("approvals")}
                      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-primary hover:bg-secondary"
                    >
                      <span className="text-xs">View all approvals</span>
                      <ArrowUpRight className="h-3 w-3" />
                    </button>
                  </div>
                )}

                <button
                  onClick={() => setActiveTab("schedule")}
                  className="flex w-full items-center gap-1 px-2 py-1.5 mt-4 text-xs font-semibold text-muted-foreground hover:text-foreground"
                >
                  <Calendar className="h-3 w-3 mr-1" />
                  Schedule
                  <Badge variant="secondary" className="ml-auto h-4 min-w-4 bg-blue-500/20 text-blue-400 text-[10px]">
                    {scheduleEvents.filter((e) => e.date === "Today").length}
                  </Badge>
                </button>
                <div className="space-y-0.5 mt-1">
                  {scheduleEvents
                    .filter((e) => e.date === "Today")
                    .slice(0, 3)
                    .map((event) => (
                      <button
                        key={event.id}
                        onClick={() => setActiveTab("schedule")}
                        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground"
                      >
                        <CalendarDays className="h-4 w-4 text-blue-400" />
                        <div className="flex-1 text-left truncate">
                          <span className="text-xs">{event.title}</span>
                        </div>
                        <span className="text-[10px] text-muted-foreground">{event.time}</span>
                      </button>
                    ))}
                </div>
              </>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex min-h-0 flex-col lg:ml-0">
        {/* Channel Header */}
        <div className="flex flex-col gap-3 border-b border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <Hash className="h-5 w-5 text-muted-foreground" />
              <h2 className="font-semibold text-foreground">{selectedChannel}</h2>
              {/* Real-time connection indicator */}
              <span
                title={wsConnected ? "Live — real-time updates on" : "Connecting…"}
                className={cn(
                  "inline-block h-2 w-2 rounded-full transition-colors",
                  wsConnected ? "bg-emerald-500 shadow-[0_0_6px_#22c55e]" : "bg-amber-400 animate-pulse",
                )}
              />
            </div>
            <Badge variant="outline" className="text-xs">
              <Users className="h-3 w-3 mr-1" />
              24 members
            </Badge>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              className="h-8 lg:hidden"
              onClick={() => setMobileSidebarOpen(true)}
            >
              <PanelLeft className="h-4 w-4 mr-2" />
              Channels
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleStartCall("voice")}>
              <Phone className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleStartCall("video")}>
              <Video className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <MonitorSpeaker className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <Settings className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <Server className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="uppercase tracking-wide">Providers</span>
          </div>
          <Badge variant="secondary" className="text-xs">
            Voice: Voicebox
          </Badge>
          <Badge variant="secondary" className="text-xs">
            Email: Unione
          </Badge>
          <Badge variant="secondary" className="text-xs">
            SMS: Twilio
          </Badge>
          <Badge variant="secondary" className="text-xs">
            Chat: Beeper
          </Badge>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0 overflow-hidden">
          {/* Chat Tab - Added context menu to messages */}
          <TabsContent value="chat" className="flex-1 flex flex-col min-h-0 m-0 overflow-hidden data-[state=inactive]:hidden">
            <ScrollArea className="flex-1 min-h-0 p-4">
              <div className="space-y-4">
                {loadingMessages && (
                  <div className="text-xs text-muted-foreground">Loading messages...</div>
                )}
                {!loadingMessages && messages.length === 0 && (
                  <div className="text-xs text-muted-foreground">No messages yet.</div>
                )}
                {messages.map((msg) => (
                  <DropdownMenu key={msg.id}>
                    <div
                      className={cn(
                        "group flex gap-3 rounded-lg p-2 -mx-2 hover:bg-secondary/50",
                        msg.isPinned && "bg-yellow-500/5 border-l-2 border-yellow-500",
                      )}
                      onContextMenu={(e) => {
                        e.preventDefault()
                        const trigger = e.currentTarget.querySelector("[data-context-trigger]") as HTMLElement
                        trigger?.click()
                      }}
                    >
                      <Avatar className="h-9 w-9 flex-shrink-0">
                        <AvatarFallback className="bg-primary/20 text-primary text-sm">
                          {msg.author_avatar ?? formatInitials(msg.author_name)}
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground text-sm">
                            {msg.author_name ?? "Unknown"}
                          </span>
                          <span className="text-xs text-muted-foreground">{formatTime(msg.created_at)}</span>
                          {msg.isPinned && <Pin className="h-3 w-3 text-yellow-500" />}
                        </div>
                        {msg.content.startsWith("↳ @") ? (() => {
                          const newlineIdx = msg.content.indexOf("\n")
                          if (newlineIdx !== -1) {
                            const quote = msg.content.slice(0, newlineIdx)
                            const body = msg.content.slice(newlineIdx + 1)
                            return (
                              <>
                                <div className="mb-1.5 flex items-center gap-1.5 rounded border-l-2 border-primary bg-secondary/50 px-2 py-1 text-xs text-muted-foreground">
                                  <Reply className="h-3 w-3 text-primary shrink-0" />
                                  <span className="truncate italic">{quote}</span>
                                </div>
                                <p className="text-sm text-foreground/90">{body}</p>
                              </>
                            )
                          }
                          return <p className="text-sm text-foreground/90 mt-0.5">{msg.content}</p>
                        })() : (
                          <p className="text-sm text-foreground/90 mt-0.5">{msg.content}</p>
                        )}
                        {(msg.reactions || msg.thread) && (
                          <div className="flex items-center gap-2 mt-2">
                            {msg.reactions?.map((reaction, i) => (
                              <button
                                key={i}
                                onClick={() => addReaction(msg.id, reaction.emoji)}
                                className="flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-xs hover:bg-secondary/80"
                              >
                                <span>{reaction.emoji}</span>
                                <span className="text-muted-foreground">{reaction.count}</span>
                              </button>
                            ))}
                            {msg.thread && (
                              <button className="flex items-center gap-1 text-xs text-primary hover:underline">
                                <MessageSquare className="h-3 w-3" />
                                {msg.thread} replies
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                      <div className="opacity-0 group-hover:opacity-100 flex items-start gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => handleSpeakMessage(msg)}
                          disabled={speakingMessageId === msg.id}
                          title="Speak message"
                        >
                          {speakingMessageId === msg.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Volume2 className="h-4 w-4" />
                          )}
                        </Button>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-7 w-7" title="React">
                              <Smile className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="flex gap-1 p-1">
                            {REACTION_EMOJIS.map((e) => (
                              <button
                                key={e}
                                onClick={() => addReaction(msg.id, e)}
                                className="rounded p-1 text-lg leading-none hover:bg-secondary"
                              >
                                {e}
                              </button>
                            ))}
                          </DropdownMenuContent>
                        </DropdownMenu>
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => startReply(msg)} title="Reply">
                          <Reply className="h-4 w-4" />
                        </Button>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-7 w-7" data-context-trigger>
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                      </div>
                    </div>
                    <DropdownMenuContent align="end" className="w-52">
                      <div className="flex items-center justify-between px-2 py-1.5 border-b border-border mb-1">
                        {REACTION_EMOJIS.slice(0, 6).map((e) => (
                          <button
                            key={e}
                            type="button"
                            onClick={(ev) => {
                              ev.stopPropagation()
                              addReaction(msg.id, e)
                            }}
                            className="rounded p-1 text-base leading-none hover:bg-secondary transition-transform hover:scale-125"
                            title={`React with ${e}`}
                          >
                            {e}
                          </button>
                        ))}
                      </div>
                      <DropdownMenuItem className="gap-2" onClick={() => startReply(msg)}>
                        <Reply className="h-4 w-4" />
                        Reply
                      </DropdownMenuItem>
                      <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-task", msg)}>
                        <ClipboardList className="h-4 w-4" />
                        Create Task
                      </DropdownMenuItem>
                      <DropdownMenuItem className="gap-2" onClick={() => setMessageInput((v) => `${v}@${msg.author_name ?? "user"} `)}>
                        <AtSign className="h-4 w-4" />
                        Mention
                      </DropdownMenuItem>
                      <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-event", msg)}>
                        <CalendarPlus className="h-4 w-4" />
                        Schedule
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-escalation", msg)}>
                        <Flag className="h-4 w-4" />
                        Escalate
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        className="gap-2"
                        onClick={() =>
                          {
                            const nextPinned = !msg.isPinned
                            setMessages((prev) =>
                              prev.map((item) => (item.id === msg.id ? { ...item, isPinned: nextPinned } : item)),
                            )
                            void fetch(`/api/chat/messages/${msg.id}/pin`, {
                              method: "PATCH",
                              headers: { "Content-Type": "application/json" },
                              body: JSON.stringify({ is_pinned: nextPinned }),
                            })
                          }
                        }
                      >
                        <Pin className="h-4 w-4" />
                        {msg.isPinned ? "Unpin Message" : "Pin Message"}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                ))}
              </div>
            </ScrollArea>

            {/* Typing indicator */}
            {typingUsers.size > 0 && (
              <div className="px-4 pb-1 flex items-center gap-1.5">
                <span className="flex gap-0.5 items-end h-3">
                  <span className="w-1 h-1 rounded-full bg-muted-foreground animate-bounce [animation-delay:0ms]" />
                  <span className="w-1 h-1 rounded-full bg-muted-foreground animate-bounce [animation-delay:150ms]" />
                  <span className="w-1 h-1 rounded-full bg-muted-foreground animate-bounce [animation-delay:300ms]" />
                </span>
                <span className="text-xs text-muted-foreground">
                  {typingUsers.size === 1
                    ? `${[...typingUsers][0].slice(0, 8)}… is typing`
                    : `${typingUsers.size} people are typing`}
                </span>
              </div>
            )}

            {/* Message Input */}
            <div className="p-4 border-t border-border">
              {voiceError && (
                <div className="mb-2 flex items-center justify-between rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs text-red-400">
                  <span>{voiceError}</span>
                  <button type="button" onClick={() => setVoiceError(null)} className="ml-2 shrink-0 hover:text-red-300">×</button>
                </div>
              )}
              {replyTo && (
                <div className="mb-2 flex items-center gap-2 rounded-lg border-l-2 border-primary bg-secondary/40 px-3 py-1.5 text-xs">
                  <Reply className="h-3.5 w-3.5 text-primary" />
                  <span className="text-muted-foreground">
                    Replying to <span className="font-medium text-foreground">{replyTo.author_name ?? "message"}</span>:{" "}
                    <span className="italic">{(replyTo.content ?? "").slice(0, 60)}</span>
                  </span>
                  <button type="button" onClick={() => setReplyTo(null)} className="ml-auto shrink-0 hover:text-foreground">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
              <div className="relative rounded-lg border border-border bg-secondary/50 p-2">
                {autocompleteOpen && (
                  <div className="absolute bottom-full left-0 z-20 mb-2 w-64 overflow-hidden rounded-lg border border-border bg-popover shadow-xl">
                    {mentionActive
                      ? mentionMatches.map((u) => (
                          <button
                            key={u.id}
                            onClick={() => applyAutocomplete("@", u.name.replace(/\s+/g, ""))}
                            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-secondary"
                          >
                            <Avatar className="h-6 w-6">
                              <AvatarFallback className="bg-primary/20 text-primary text-[10px]">
                                {formatInitials(u.name)}
                              </AvatarFallback>
                            </Avatar>
                            <span className="truncate">{u.name}</span>
                          </button>
                        ))
                      : slashMatches.map((c) => (
                          <button
                            key={c}
                            onClick={() => applyAutocomplete("/", c)}
                            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm capitalize hover:bg-secondary"
                          >
                            <Hash className="h-4 w-4 text-muted-foreground" />
                            {c}
                          </button>
                        ))}
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <Button variant="ghost" size="icon" className="h-8 w-8">
                    <Plus className="h-4 w-4" />
                  </Button>
                  <Input
                    ref={messageInputRef}
                    value={messageInput}
                    onChange={(e) => { setMessageInput(e.target.value); sendTyping() }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault()
                        if (autocompleteOpen) {
                          if (mentionActive && mentionMatches[0]) applyAutocomplete("@", mentionMatches[0].name.replace(/\s+/g, ""))
                          else if (slashActive && slashMatches[0]) applyAutocomplete("/", slashMatches[0])
                        } else {
                          handleSend()
                        }
                      } else if (e.key === "Escape" && replyTo) {
                        setReplyTo(null)
                      }
                    }}
                    placeholder={`Message #${activeChannel?.name ?? selectedChannel}`}
                    className="flex-1 border-0 bg-transparent focus-visible:ring-0 px-0"
                  />
                  <Button variant="ghost" size="icon" className="h-8 w-8">
                    <AtSign className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8">
                    <Smile className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8">
                    <Paperclip className="h-4 w-4" />
                  </Button>
                  <Button
                    variant={isRecordingVoice ? "destructive" : "ghost"}
                    size="icon"
                    className="h-8 w-8"
                    onClick={isRecordingVoice ? stopVoiceRecording : startVoiceRecording}
                    disabled={isTranscribing}
                    title={isRecordingVoice ? "Stop recording" : "Voice input"}
                  >
                    {isTranscribing ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : isRecordingVoice ? (
                      <MicOff className="h-4 w-4" />
                    ) : (
                      <Mic className="h-4 w-4" />
                    )}
                  </Button>
                  <Button
                    size="icon"
                    className="h-8 w-8 bg-primary hover:bg-primary/90"
                    onClick={handleSend}
                    disabled={!messageInput.trim() || !activeChannelId}
                  >
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          </TabsContent>

          {/* Agent Channel Tab — AI agents with full OmniDome context */}
          <TabsContent value="agents" className="flex-1 min-h-0 h-full m-0 flex flex-col overflow-hidden data-[state=inactive]:hidden">
            <AgentArtifactChat
              channelId={activeChannelId}
              channelName={activeChannel?.name}
              extraContext={agentScheduleContext}
              teamUsers={teamUsers}
            />
          </TabsContent>

          {/* Tasks Tab — with agent assistance */}
          <TabsContent value="tasks" className="flex-1 m-0 overflow-hidden">
            <div className="flex h-full">
              {/* Task list */}
              <div className="flex-1 flex flex-col min-w-0">
                <ScrollArea className="flex-1">
                  <div className="p-4">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-semibold text-foreground">Team Tasks</h3>
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 gap-1"
                          onClick={() => setActiveTab("agents")}
                        >
                          <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
                          Ask Agent
                        </Button>
                        <Button size="sm" className="h-8" onClick={() => openPanel("add-task")}>
                          <Plus className="h-4 w-4 mr-1" />
                          New Task
                        </Button>
                      </div>
                    </div>

                    {/* Agent suggestion banner */}
                    <div className="mb-4 rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-3">
                      <div className="flex items-start gap-2">
                        <Bot className="h-4 w-4 text-cyan-400 mt-0.5" />
                        <div className="flex-1">
                          <p className="text-xs font-medium text-cyan-400">Agent Assistance Available</p>
                          <p className="mt-0.5 text-[11px] text-muted-foreground">
                            Agents can help with tasks using full OmniDome context — customer data, network status, billing info, and more.
                            Go to the <strong>Agent Channel</strong> tab or click &quot;Ask Agent&quot; to get started.
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-2">
                      {tasks.map((task) => (
                        <div
                          key={task.id}
                          className="flex items-center gap-3 rounded-lg border border-border bg-secondary/30 p-3 hover:bg-secondary/50 transition-colors"
                        >
                          {taskStatusIcons[task.status]}
                          <div className="flex-1 min-w-0">
                            <p
                              className={cn(
                                "text-sm font-medium",
                                task.status === "done" && "line-through text-muted-foreground",
                              )}
                            >
                              {task.title}
                            </p>
                            <div className="flex items-center gap-2 mt-1">
                              <Avatar className="h-5 w-5">
                                <AvatarFallback className="text-[10px] bg-primary/20 text-primary">
                                  {task.avatar}
                                </AvatarFallback>
                              </Avatar>
                              <span className="text-xs text-muted-foreground">{task.assignee}</span>
                            </div>
                          </div>
                          <Badge className={cn("text-xs", priorityColors[task.priority])}>{task.priority}</Badge>
                          <span className="text-xs text-muted-foreground">{task.dueDate}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </ScrollArea>
              </div>
            </div>
          </TabsContent>

          {/* Leads Tab */}
          <TabsContent value="leads" className="flex-1 m-0 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="p-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-foreground">Active Leads</h3>
                  <Button size="sm" className="h-8">
                    <Plus className="h-4 w-4 mr-1" />
                    Add Lead
                  </Button>
                </div>
                <div className="space-y-2">
                  {leads.map((lead) => (
                    <div
                      key={lead.id}
                      className="flex items-center gap-3 rounded-lg border border-border bg-secondary/30 p-3 hover:bg-secondary/50 transition-colors cursor-pointer"
                    >
                      <Avatar className="h-10 w-10">
                        <AvatarFallback className="bg-primary/20 text-primary">
                          {lead.name
                            .split(" ")
                            .map((n) => n[0])
                            .join("")}
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground">{lead.name}</p>
                        <p className="text-xs text-muted-foreground">{lead.company}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-semibold text-primary">{lead.value}</p>
                        <Badge className={cn("text-xs mt-1", leadStatusColors[lead.status])}>{lead.status}</Badge>
                      </div>
                      <div className="flex items-center gap-2">
                        <Avatar className="h-6 w-6">
                          <AvatarFallback className="text-[10px] bg-muted">{lead.avatar}</AvatarFallback>
                        </Avatar>
                        <ArrowUpRight className="h-4 w-4 text-muted-foreground" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="approvals" className="flex-1 m-0 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="p-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-foreground">Agent Approvals</h3>
                  <div className="flex gap-2">
                    <Badge variant="outline" className="text-xs">
                      Pending: {approvals.filter((a) => a.status === "pending").length}
                    </Badge>
                    <Button size="sm" className="h-8" onClick={() => openPanel("add-approval")}>
                      <Plus className="h-4 w-4 mr-1" />
                      Add Approval
                    </Button>
                  </div>
                </div>
                <div className="space-y-3">
                  {approvals.map((approval) => (
                    <div
                      key={approval.id}
                      className={cn(
                        "rounded-lg border p-4 transition-colors",
                        approval.status === "pending"
                          ? "border-orange-500/30 bg-orange-500/5"
                          : approval.status === "approved"
                            ? "border-green-500/30 bg-green-500/5"
                            : "border-red-500/30 bg-red-500/5",
                      )}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3">
                          <Avatar className="h-10 w-10">
                            <AvatarFallback className="bg-primary/20 text-primary">{approval.avatar}</AvatarFallback>
                          </Avatar>
                          <div>
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-medium text-foreground">{approval.agent}</p>
                              <Badge className={cn("text-xs capitalize", approvalTypeColors[approval.type])}>
                                {approval.type}
                              </Badge>
                            </div>
                            <p className="text-xs text-muted-foreground mt-0.5">Customer: {approval.customer}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-lg font-bold text-foreground">{approval.amount}</p>
                          <p className="text-xs text-muted-foreground">{approval.time}</p>
                        </div>
                      </div>
                      <p className="text-sm text-muted-foreground mt-3 p-2 bg-secondary/50 rounded">
                        {approval.reason}
                      </p>
                      {approval.status === "pending" && (
                        <div className="flex gap-2 mt-3">
                          <Button
                            size="sm"
                            className="flex-1 bg-green-600 hover:bg-green-700"
                            onClick={() => handleApprovalAction(approval.id, "approve")}
                          >
                            <CheckCircle2 className="h-4 w-4 mr-1" />
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            className="flex-1"
                            onClick={() => handleApprovalAction(approval.id, "reject")}
                          >
                            <AlertCircle className="h-4 w-4 mr-1" />
                            Reject
                          </Button>
                        </div>
                      )}
                      {approval.status !== "pending" && (
                        <div className="flex items-center gap-2 mt-3">
                          <Badge
                            variant="outline"
                            className={cn(
                              "text-xs",
                              approval.status === "approved"
                                ? "text-green-400 border-green-500/30"
                                : "text-red-400 border-red-500/30",
                            )}
                          >
                            {approval.status === "approved" ? (
                              <CheckCircle2 className="h-3 w-3 mr-1" />
                            ) : (
                              <AlertCircle className="h-3 w-3 mr-1" />
                            )}
                            {approval.status.charAt(0).toUpperCase() + approval.status.slice(1)}
                          </Badge>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </ScrollArea>
          </TabsContent>

          {/* Escalations Tab */}
          <TabsContent value="escalations" className="flex-1 m-0 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="p-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-foreground">Active Escalations</h3>
                  <Button size="sm" variant="destructive" className="h-8" onClick={() => openPanel("add-escalation")}>
                    <AlertCircle className="h-4 w-4 mr-1" />
                    Report Issue
                  </Button>
                </div>
                <div className="space-y-2">
                  {escalations.map((esc) => (
                    <div
                      key={esc.id}
                      className={cn(
                        "flex items-center gap-3 rounded-lg border p-3 transition-colors cursor-pointer",
                        severityColors[esc.severity],
                      )}
                    >
                      <div
                        className={cn(
                          "flex h-10 w-10 items-center justify-center rounded-full",
                          esc.severity === "critical" ? "bg-red-500/20" : "bg-secondary",
                        )}
                      >
                        <AlertCircle
                          className={cn(
                            "h-5 w-5",
                            esc.severity === "critical" ? "text-red-400" : "text-muted-foreground",
                          )}
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground">{esc.title}</p>
                        <p className="text-xs text-muted-foreground">{esc.customer}</p>
                      </div>
                      <Badge variant="outline" className={cn("text-xs uppercase", severityColors[esc.severity])}>
                        {esc.severity}
                      </Badge>
                      <div className="flex items-center gap-2">
                        <Avatar className="h-6 w-6">
                          <AvatarFallback className="text-[10px] bg-muted">{esc.avatar}</AvatarFallback>
                        </Avatar>
                        <span className="text-xs text-muted-foreground">{esc.time}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="schedule" className="flex-1 m-0 overflow-hidden">
            <div className="h-full flex flex-col">
              {/* Schedule View Toggle */}
              <div className="flex items-center justify-between p-4 border-b border-border">
                <h3 className="font-semibold text-foreground">My Schedule</h3>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1 bg-secondary rounded-lg p-1">
                    <Button
                      size="sm"
                      variant={scheduleView === "kanban" ? "default" : "ghost"}
                      className="h-7 px-3 text-xs"
                      onClick={() => setScheduleView("kanban")}
                    >
                      <LayoutGrid className="h-3 w-3 mr-1" />
                      Kanban
                    </Button>
                    <Button
                      size="sm"
                      variant={scheduleView === "timeline" ? "default" : "ghost"}
                      className="h-7 px-3 text-xs"
                      onClick={() => setScheduleView("timeline")}
                    >
                      <GanttChart className="h-3 w-3 mr-1" />
                      Timeline
                    </Button>
                    <Button
                      size="sm"
                      variant={scheduleView === "todo" ? "default" : "ghost"}
                      className="h-7 px-3 text-xs"
                      onClick={() => setScheduleView("todo")}
                    >
                      <List className="h-3 w-3 mr-1" />
                      To-do
                    </Button>
                    <Button
                      size="sm"
                      variant={scheduleView === "activity" ? "default" : "ghost"}
                      className="h-7 px-3 text-xs"
                      onClick={() => setScheduleView("activity")}
                    >
                      <ClipboardList className="h-3 w-3 mr-1" />
                      Activity
                    </Button>
                  </div>
                  <div className="flex items-center gap-1 bg-secondary rounded-lg p-1">
                    {(["hour", "day", "week", "month"] as const).map((range) => (
                      <Button
                        key={range}
                        size="sm"
                        variant={scheduleFilter === range ? "default" : "ghost"}
                        className="h-7 px-3 text-xs capitalize"
                        onClick={() => setScheduleFilter(range)}
                      >
                        {range}
                      </Button>
                    ))}
                  </div>
                  <Button size="sm" className="h-8" onClick={() => openPanel("add-event")}>
                    <Plus className="h-4 w-4 mr-1" />
                    Add Event
                  </Button>
                </div>
              </div>

              <ScrollArea className="flex-1">
                {/* Kanban View */}
                {scheduleView === "kanban" && (
                  <div className="p-4">
                    <div className="grid grid-cols-3 gap-4">
                      {/* Upcoming Column */}
                      <div
                        className="bg-secondary/30 rounded-lg p-3"
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => {
                          e.preventDefault()
                          handleKanbanDrop("upcoming", e.dataTransfer.getData("text/plain"))
                        }}
                      >
                        <div className="flex items-center gap-2 mb-3">
                          <Clock className="h-4 w-4 text-blue-400" />
                          <h4 className="font-medium text-sm">Upcoming</h4>
                          <Badge variant="secondary" className="ml-auto text-xs">
                            {kanbanItems.filter((item) => item.status === "upcoming").length}
                          </Badge>
                        </div>
                        <div className="space-y-2">
                          {kanbanItems
                            .filter((item) => item.status === "upcoming")
                            .map((item) => (
                              <DropdownMenu key={`${item.type}-${item.id}`}>
                                <div
                                  draggable
                                  onDragStart={(e) => {
                                    e.dataTransfer.setData("text/plain", `${item.type}:${item.id}`)
                                  }}
                                  onContextMenu={(e) => {
                                    e.preventDefault()
                                    const trigger = e.currentTarget.querySelector("[data-context-trigger]") as HTMLElement
                                    trigger?.click()
                                  }}
                                  className={cn("group rounded-lg border p-3 cursor-move", item.colorClass)}
                                >
                                  <div className="flex items-center justify-between">
                                    <p className="text-sm font-medium">{item.title}</p>
                                    <DropdownMenuTrigger asChild>
                                      <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-7 w-7 opacity-0 group-hover:opacity-100"
                                        data-context-trigger
                                      >
                                        <MoreHorizontal className="h-4 w-4" />
                                      </Button>
                                    </DropdownMenuTrigger>
                                  </div>
                                  <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
                                    <CalendarDays className="h-3 w-3" />
                                    {item.meta}
                                  </div>
                                  {item.assignee && (
                                    <div className="flex items-center gap-1 mt-2">
                                      {item.avatar && (
                                        <Avatar className="h-5 w-5">
                                          <AvatarFallback className="text-[10px] bg-primary/20 text-primary">
                                            {item.avatar}
                                          </AvatarFallback>
                                        </Avatar>
                                      )}
                                      <span className="text-xs text-muted-foreground">{item.assignee}</span>
                                    </div>
                                  )}
                                </div>
                                <DropdownMenuContent align="end" className="w-48">
                                  <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-task")}>
                                    <ClipboardList className="h-4 w-4" />
                                    Create Task
                                  </DropdownMenuItem>
                                  <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-approval")}>
                                    <CheckSquare className="h-4 w-4" />
                                    Create Approval
                                  </DropdownMenuItem>
                                  <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-event")}>
                                    <CalendarPlus className="h-4 w-4" />
                                    Schedule
                                  </DropdownMenuItem>
                                  <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-escalation")}>
                                    <Flag className="h-4 w-4" />
                                    Escalate
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            ))}
                        </div>
                      </div>

                      {/* In Progress Column */}
                      <div
                        className="bg-secondary/30 rounded-lg p-3"
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => {
                          e.preventDefault()
                          handleKanbanDrop("in-progress", e.dataTransfer.getData("text/plain"))
                        }}
                      >
                        <div className="flex items-center gap-2 mb-3">
                          <Zap className="h-4 w-4 text-yellow-400" />
                          <h4 className="font-medium text-sm">In Progress</h4>
                          <Badge variant="secondary" className="ml-auto text-xs">
                            {kanbanItems.filter((item) => item.status === "in-progress").length}
                          </Badge>
                        </div>
                        <div className="space-y-2">
                          {kanbanItems
                            .filter((item) => item.status === "in-progress")
                            .map((item) => (
                              <DropdownMenu key={`${item.type}-${item.id}`}>
                                <div
                                  draggable
                                  onDragStart={(e) => {
                                    e.dataTransfer.setData("text/plain", `${item.type}:${item.id}`)
                                  }}
                                  onContextMenu={(e) => {
                                    e.preventDefault()
                                    const trigger = e.currentTarget.querySelector("[data-context-trigger]") as HTMLElement
                                    trigger?.click()
                                  }}
                                  className={cn("group rounded-lg border p-3 cursor-move", item.colorClass)}
                                >
                                  <div className="flex items-center justify-between">
                                    <p className="text-sm font-medium">{item.title}</p>
                                    <DropdownMenuTrigger asChild>
                                      <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-7 w-7 opacity-0 group-hover:opacity-100"
                                        data-context-trigger
                                      >
                                        <MoreHorizontal className="h-4 w-4" />
                                      </Button>
                                    </DropdownMenuTrigger>
                                  </div>
                                  <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
                                    <CalendarDays className="h-3 w-3" />
                                    {item.meta}
                                  </div>
                                  {item.assignee && (
                                    <div className="flex items-center gap-1 mt-2">
                                      {item.avatar && (
                                        <Avatar className="h-5 w-5">
                                          <AvatarFallback className="text-[10px] bg-primary/20 text-primary">
                                            {item.avatar}
                                          </AvatarFallback>
                                        </Avatar>
                                      )}
                                      <span className="text-xs text-muted-foreground">{item.assignee}</span>
                                    </div>
                                  )}
                                </div>
                                <DropdownMenuContent align="end" className="w-48">
                                  <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-task")}>
                                    <ClipboardList className="h-4 w-4" />
                                    Create Task
                                  </DropdownMenuItem>
                                  <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-approval")}>
                                    <CheckSquare className="h-4 w-4" />
                                    Create Approval
                                  </DropdownMenuItem>
                                  <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-event")}>
                                    <CalendarPlus className="h-4 w-4" />
                                    Schedule
                                  </DropdownMenuItem>
                                  <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-escalation")}>
                                    <Flag className="h-4 w-4" />
                                    Escalate
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            ))}
                        </div>
                      </div>

                      {/* Completed Column */}
                      <div
                        className="bg-secondary/30 rounded-lg p-3"
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => {
                          e.preventDefault()
                          handleKanbanDrop("completed", e.dataTransfer.getData("text/plain"))
                        }}
                      >
                        <div className="flex items-center gap-2 mb-3">
                          <CheckCircle2 className="h-4 w-4 text-green-400" />
                          <h4 className="font-medium text-sm">Completed</h4>
                          <Badge variant="secondary" className="ml-auto text-xs">
                            {kanbanItems.filter((item) => item.status === "completed").length}
                          </Badge>
                        </div>
                        <div className="space-y-2">
                          {kanbanItems
                            .filter((item) => item.status === "completed")
                            .map((item) => (
                              <DropdownMenu key={`${item.type}-${item.id}`}>
                                <div
                                  draggable
                                  onDragStart={(e) => {
                                    e.dataTransfer.setData("text/plain", `${item.type}:${item.id}`)
                                  }}
                                  onContextMenu={(e) => {
                                    e.preventDefault()
                                    const trigger = e.currentTarget.querySelector("[data-context-trigger]") as HTMLElement
                                    trigger?.click()
                                  }}
                                  className={cn("group rounded-lg border p-3 cursor-move", item.colorClass)}
                                >
                                  <div className="flex items-center justify-between">
                                    <p className="text-sm font-medium line-through text-muted-foreground">
                                      {item.title}
                                    </p>
                                    <DropdownMenuTrigger asChild>
                                      <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-7 w-7 opacity-0 group-hover:opacity-100"
                                        data-context-trigger
                                      >
                                        <MoreHorizontal className="h-4 w-4" />
                                      </Button>
                                    </DropdownMenuTrigger>
                                  </div>
                                  <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
                                    <CalendarDays className="h-3 w-3" />
                                    {item.meta}
                                  </div>
                                  {item.assignee && (
                                    <div className="flex items-center gap-1 mt-2">
                                      {item.avatar && (
                                        <Avatar className="h-5 w-5">
                                          <AvatarFallback className="text-[10px] bg-primary/20 text-primary">
                                            {item.avatar}
                                          </AvatarFallback>
                                        </Avatar>
                                      )}
                                      <span className="text-xs text-muted-foreground">{item.assignee}</span>
                                    </div>
                                  )}
                                </div>
                                <DropdownMenuContent align="end" className="w-48">
                                  <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-task")}>
                                    <ClipboardList className="h-4 w-4" />
                                    Create Task
                                  </DropdownMenuItem>
                                  <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-approval")}>
                                    <CheckSquare className="h-4 w-4" />
                                    Create Approval
                                  </DropdownMenuItem>
                                  <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-event")}>
                                    <CalendarPlus className="h-4 w-4" />
                                    Schedule
                                  </DropdownMenuItem>
                                  <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-escalation")}>
                                    <Flag className="h-4 w-4" />
                                    Escalate
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Timeline View */}
                {scheduleView === "timeline" && (
                  <div className="p-4">
                    <div className="relative">
                      {/* Timeline line */}
                      <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-border" />

                      <div className="space-y-4">
                        {["Today", "Tomorrow", "Thursday", "Friday"].map((day) => {
                          const dayEvents = filteredScheduleEvents.filter((e) => e.date === day)
                          if (dayEvents.length === 0) return null
                          return (
                            <div key={day}>
                              <div className="flex items-center gap-3 mb-2">
                                <div className="h-3 w-3 rounded-full bg-primary relative z-10" />
                                <h4 className="font-semibold text-sm">{day}</h4>
                              </div>
                              <div className="ml-8 space-y-2">
                                {dayEvents.map((event) => (
                                  <div
                                    key={event.id}
                                    className={cn(
                                      "rounded-lg border p-3 flex items-center gap-3",
                                      eventTypeColors[event.type],
                                    )}
                                  >
                                    <span className="text-sm font-mono text-muted-foreground w-12">{event.time}</span>
                                    <div className="flex-1">
                                      <p className="text-sm font-medium">{event.title}</p>
                                      {event.assignee && (
                                        <p className="text-xs text-muted-foreground">{event.assignee}</p>
                                      )}
                                    </div>
                                    <Badge variant="outline" className="text-xs capitalize">
                                      {event.type}
                                    </Badge>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  </div>
                )}

                {/* To-do List View */}
                {scheduleView === "todo" && (
                  <div className="p-4">
                    <div className="space-y-2">
                      {filteredScheduleEvents.map((event) => (
                        <div
                          key={event.id}
                          className={cn(
                            "flex items-center gap-3 rounded-lg border border-border bg-secondary/30 p-3 hover:bg-secondary/50 transition-colors",
                            event.status === "completed" && "opacity-60",
                          )}
                        >
                          <button
                            className={cn(
                              "h-5 w-5 rounded-full border-2 flex items-center justify-center transition-colors",
                              event.status === "completed"
                                ? "bg-green-500 border-green-500"
                                : "border-muted-foreground hover:border-primary",
                            )}
                          >
                            {event.status === "completed" && <CheckCircle2 className="h-3 w-3 text-white" />}
                          </button>
                          <div className="flex-1">
                            <p
                              className={cn(
                                "text-sm font-medium",
                                event.status === "completed" && "line-through text-muted-foreground",
                              )}
                            >
                              {event.title}
                            </p>
                            <div className="flex items-center gap-3 mt-1">
                              <span className="text-xs text-muted-foreground">
                                {event.date} at {event.time}
                              </span>
                              {event.assignee && (
                                <span className="text-xs text-muted-foreground">• {event.assignee}</span>
                              )}
                            </div>
                          </div>
                          <Badge variant="outline" className={cn("text-xs capitalize", eventTypeColors[event.type])}>
                            {event.type}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {scheduleView === "activity" && (
                  <div className="p-4">
                    <div className="space-y-3">
                      {activityItems.map((activity) => (
                        <div
                          key={activity.id}
                          className="flex items-start gap-3 rounded-lg border border-border bg-secondary/30 p-3"
                        >
                          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary">
                            {activity.type === "chat" && <MessageSquare className="h-4 w-4" />}
                            {activity.type === "task" && <ListTodo className="h-4 w-4" />}
                            {activity.type === "approval" && <CheckSquare className="h-4 w-4" />}
                            {activity.type === "escalation" && <Flag className="h-4 w-4" />}
                            {activity.type === "schedule" && <CalendarDays className="h-4 w-4" />}
                          </div>
                          <div className="flex-1">
                            <p className="text-sm font-medium text-foreground">{activity.title}</p>
                            <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                              <span>{activity.actor}</span>
                              <span>•</span>
                              <span>{activity.time}</span>
                              {activity.meta && (
                                <>
                                  <span>•</span>
                                  <span>{activity.meta}</span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </ScrollArea>
            </div>
          </TabsContent>
        </Tabs>
      </div>

      {channelDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={() => setChannelDialogOpen(false)} />
          <div className="relative w-full max-w-sm rounded-xl border border-border bg-background p-5 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="font-semibold">Create a channel</h3>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setChannelDialogOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <label className="text-xs text-muted-foreground">Channel name</label>
            <Input
              autoFocus
              value={newChannelName}
              onChange={(e) => setNewChannelName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleCreateChannel()
              }}
              placeholder="e.g. product-launch"
              className="mt-1.5"
            />
            <div className="mt-4 space-y-2">
              <p className="text-xs text-muted-foreground">Visibility</p>
              <button
                type="button"
                onClick={() => setNewChannelPrivate(false)}
                className={cn(
                  "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors",
                  !newChannelPrivate ? "border-primary bg-primary/10" : "border-border hover:bg-secondary/50",
                )}
              >
                <Hash className="mt-0.5 h-4 w-4 text-muted-foreground" />
                <div>
                  <div className="text-sm font-medium">Public</div>
                  <div className="text-xs text-muted-foreground">Anyone on the team can find and join.</div>
                </div>
              </button>
              <button
                type="button"
                onClick={() => setNewChannelPrivate(true)}
                className={cn(
                  "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors",
                  newChannelPrivate ? "border-primary bg-primary/10" : "border-border hover:bg-secondary/50",
                )}
              >
                <Lock className="mt-0.5 h-4 w-4 text-muted-foreground" />
                <div>
                  <div className="text-sm font-medium">Private</div>
                  <div className="text-xs text-muted-foreground">Only invited people can see it.</div>
                </div>
              </button>
            </div>
            <div className="mt-4">
              <p className="text-xs text-muted-foreground">
                Invite people {selectedInvites.size > 0 && <span className="text-primary">· {selectedInvites.size} selected</span>}
              </p>
              <div className="mt-2 max-h-40 space-y-1 overflow-y-auto rounded-lg border border-border p-1">
                {teamUsers.length === 0 && (
                  <p className="px-2 py-1.5 text-xs text-muted-foreground">No teammates found.</p>
                )}
                {teamUsers.map((u) => (
                  <label
                    key={u.id}
                    className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-secondary/50"
                  >
                    <input
                      type="checkbox"
                      checked={selectedInvites.has(u.id)}
                      onChange={() => toggleInvite(u.id)}
                    />
                    <Avatar className="h-6 w-6">
                      <AvatarFallback className="bg-primary/20 text-primary text-[10px]">
                        {formatInitials(u.name)}
                      </AvatarFallback>
                    </Avatar>
                    <span className="flex-1 truncate">{u.name}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setChannelDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={() => void handleCreateChannel()} disabled={creatingChannel || !newChannelName.trim()}>
                {creatingChannel ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create channel"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {panelOpen && (
        <div className="fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={(e) => {
              e.stopPropagation()
              closePanel()
            }}
          />
          <div className="absolute right-0 top-0 h-full w-full max-w-md bg-background border-l border-border flex flex-col shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <div>
                <p className="text-sm text-muted-foreground">
                  {panelType === "start-chat" && "Start Chat"}
                  {panelType === "add-event" && "Add Event"}
                  {panelType === "add-task" && "Add Task"}
                  {panelType === "add-approval" && "Add Approval"}
                  {panelType === "add-escalation" && "Escalate"}
                </p>
                <h3 className="section-title">
                  {panelType === "start-chat" && "Start a conversation"}
                  {panelType === "add-event" && "Schedule an event"}
                  {panelType === "add-task" && "Create a new task"}
                  {panelType === "add-approval" && "Request approval"}
                  {panelType === "add-escalation" && "Create an escalation"}
                </h3>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={(e) => {
                  e.stopPropagation()
                  closePanel()
                }}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
              {panelType === "start-chat" && (
                <>
                  <div className="flex items-center gap-2 bg-secondary rounded-lg p-1 w-fit">
                    <Button
                      size="sm"
                      variant={startChatMode === "channel" ? "default" : "ghost"}
                      className="h-8 px-3 text-xs"
                      onClick={() => setStartChatMode("channel")}
                    >
                      Channel
                    </Button>
                    <Button
                      size="sm"
                      variant={startChatMode === "dm" ? "default" : "ghost"}
                      className="h-8 px-3 text-xs"
                      onClick={() => setStartChatMode("dm")}
                    >
                      DM
                    </Button>
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Subject</label>
                    <Input
                      value={startChatSubject}
                      onChange={(e) => setStartChatSubject(e.target.value)}
                      placeholder="What's this chat about?"
                      className="mt-2"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Participants</label>
                    <Input
                      value={startChatParticipants}
                      onChange={(e) => setStartChatParticipants(e.target.value)}
                      placeholder="Add people or teams"
                      className="mt-2"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Notes</label>
                    <textarea
                      value={startChatNotes}
                      onChange={(e) => setStartChatNotes(e.target.value)}
                      placeholder="Share context or expectations..."
                      className="mt-2 min-h-[120px] w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                    />
                  </div>
                </>
              )}

              {panelType === "add-event" && (
                <>
                  <div>
                    <label className="text-xs text-muted-foreground">Title</label>
                    <Input
                      value={eventTitle}
                      onChange={(e) => setEventTitle(e.target.value)}
                      placeholder="Event title"
                      className="mt-2"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Type</label>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {(["meeting", "task", "reminder", "deadline"] as const).map((type) => (
                        <Button
                          key={type}
                          size="sm"
                          variant={eventType === type ? "default" : "secondary"}
                          className="h-8 px-3 text-xs capitalize"
                          onClick={() => setEventType(type)}
                        >
                          {type}
                        </Button>
                      ))}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-muted-foreground">Date</label>
                      <Input
                        type="date"
                        value={eventDate}
                        onChange={(e) => setEventDate(e.target.value)}
                        className="mt-2"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">Time</label>
                      <Input
                        type="time"
                        value={eventTime}
                        onChange={(e) => setEventTime(e.target.value)}
                        className="mt-2"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Assignee</label>
                    <Input
                      value={eventAssignee}
                      onChange={(e) => setEventAssignee(e.target.value)}
                      placeholder="Assign to"
                      className="mt-2"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Notes</label>
                    <textarea
                      value={eventNotes}
                      onChange={(e) => setEventNotes(e.target.value)}
                      placeholder="Add agenda or details..."
                      className="mt-2 min-h-[120px] w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                    />
                  </div>
                </>
              )}

              {panelType === "add-task" && (
                <>
                  <div>
                    <label className="text-xs text-muted-foreground">Task Title</label>
                    <Input
                      value={taskTitle}
                      onChange={(e) => setTaskTitle(e.target.value)}
                      placeholder="What needs to be done?"
                      className="mt-2"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Assignee</label>
                    <Input
                      value={taskAssignee}
                      onChange={(e) => setTaskAssignee(e.target.value)}
                      placeholder="Assign to"
                      className="mt-2"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-muted-foreground">Due Date</label>
                      <Input
                        value={taskDueDate}
                        onChange={(e) => setTaskDueDate(e.target.value)}
                        placeholder="Tomorrow"
                        className="mt-2"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">Priority</label>
                      <div className="mt-2 flex gap-2">
                        {(["low", "medium", "high"] as const).map((level) => (
                          <Button
                            key={level}
                            size="sm"
                            variant={taskPriority === level ? "default" : "secondary"}
                            className="h-8 px-3 text-xs capitalize"
                            onClick={() => setTaskPriority(level)}
                          >
                            {level}
                          </Button>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Notes</label>
                    <textarea
                      value={taskNotes}
                      onChange={(e) => setTaskNotes(e.target.value)}
                      placeholder="Add context or requirements..."
                      className="mt-2 min-h-[120px] w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                    />
                  </div>
                </>
              )}

              {panelType === "add-approval" && (
                <>
                  <div>
                    <label className="text-xs text-muted-foreground">Subject</label>
                    <Input
                      value={approvalSubject}
                      onChange={(e) => setApprovalSubject(e.target.value)}
                      placeholder="Approval subject"
                      className="mt-2"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Approver</label>
                    <Input
                      value={approvalApprover}
                      onChange={(e) => setApprovalApprover(e.target.value)}
                      placeholder="Who should approve?"
                      className="mt-2"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Timeline</label>
                    <Input
                      value={approvalTimeline}
                      onChange={(e) => setApprovalTimeline(e.target.value)}
                      placeholder="e.g. Today, EOD Friday"
                      className="mt-2"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Notes</label>
                    <textarea
                      value={approvalNotes}
                      onChange={(e) => setApprovalNotes(e.target.value)}
                      placeholder="Why is this approval needed?"
                      className="mt-2 min-h-[120px] w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                    />
                  </div>
                </>
              )}

              {panelType === "add-escalation" && (
                <>
                  <div>
                    <label className="text-xs text-muted-foreground">Escalation Title</label>
                    <Input
                      value={escalationTitle}
                      onChange={(e) => setEscalationTitle(e.target.value)}
                      placeholder="What needs escalation?"
                      className="mt-2"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Severity</label>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {(["low", "medium", "high", "critical"] as const).map((level) => (
                        <Button
                          key={level}
                          size="sm"
                          variant={escalationSeverity === level ? "default" : "secondary"}
                          className="h-8 px-3 text-xs capitalize"
                          onClick={() => setEscalationSeverity(level)}
                        >
                          {level}
                        </Button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Notes</label>
                    <textarea
                      value={escalationNotes}
                      onChange={(e) => setEscalationNotes(e.target.value)}
                      placeholder="Add escalation details..."
                      className="mt-2 min-h-[120px] w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                    />
                  </div>
                </>
              )}
            </div>

            <div className="border-t border-border p-4 flex gap-2">
              <Button variant="outline" className="flex-1" onClick={closePanel}>
                Cancel
              </Button>
              {panelType === "start-chat" && (
                <Button className="flex-1" onClick={handleStartChat}>
                  Start Chat
                </Button>
              )}
              {panelType === "add-event" && (
                <Button className="flex-1" onClick={handleAddEvent} disabled={!eventTitle.trim()}>
                  Create Event
                </Button>
              )}
              {panelType === "add-task" && (
                <Button className="flex-1" onClick={handleAddTask} disabled={!taskTitle.trim()}>
                  Create Task
                </Button>
              )}
              {panelType === "add-approval" && (
                <Button className="flex-1" onClick={handleAddApproval} disabled={!approvalSubject.trim()}>
                  Request Approval
                </Button>
              )}
              {panelType === "add-escalation" && (
                <Button className="flex-1" onClick={handleAddEscalation} disabled={!escalationTitle.trim()}>
                  Escalate
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
