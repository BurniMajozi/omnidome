"use client"

import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import {
  Hash,
  Lock,
  ChevronDown,
  ChevronRight,
  Plus,
  Search,
  Bell,
  Pin,
  MoreHorizontal,
  Smile,
  Paperclip,
  Send,
  AtSign,
  Video,
  Phone,
  Users,
  Star,
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
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
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

export function CommunicationModule() {
  const [channelsExpanded, setChannelsExpanded] = useState(true)
  const [dmExpanded, setDmExpanded] = useState(true)
  const [systemMsgExpanded, setSystemMsgExpanded] = useState(true)
  const [agentMsgExpanded, setAgentMsgExpanded] = useState(true)
  const [selectedChannel, setSelectedChannel] = useState("sales-team")
  const [messageInput, setMessageInput] = useState("")
  const [activeTab, setActiveTab] = useState("chat")
  const [scheduleView, setScheduleView] = useState<"kanban" | "timeline" | "todo" | "activity">("kanban")
  const [scheduleFilter, setScheduleFilter] = useState<"hour" | "day" | "week" | "month">("week")
  const [channels, setChannels] = useState<Channel[]>(seedChannels)
  const [messages, setMessages] = useState<Message[]>(seedMessages)
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
  const [eventDate, setEventDate] = useState("Today")
  const [eventTime, setEventTime] = useState("09:00")
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

  const currentUserName = "You"
  const currentUserAvatar = "ME"
  const activeChannel = channels.find((channel) => channel.name === selectedChannel) ?? channels[0]
  const activeChannelId = activeChannel?.id
  const isUuid = (value?: string | null) =>
    !!value &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)

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

  const handleSend = async () => {
    const trimmed = messageInput.trim()
    if (!trimmed || !activeChannelId) return
    const payload = {
      channel_id: activeChannelId,
      content: trimmed,
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
      }
    } catch (error) {
      console.error("Failed to send message", error)
    }
  }

  const handleStartChat = () => {
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

  const handleAddEvent = () => {
    if (!eventTitle.trim()) return
    const contextId = contextMessageId && isUuid(contextMessageId) ? contextMessageId : null
    const newEvent: ScheduleEvent = {
      id: `event-${Date.now()}`,
      title: eventTitle.trim(),
      type: eventType,
      date: eventDate,
      time: eventTime,
      assignee: eventAssignee || undefined,
      avatar: eventAssignee
        ? eventAssignee
            .split(" ")
            .filter(Boolean)
            .slice(0, 2)
            .map((part) => part[0]?.toUpperCase())
            .join("")
        : undefined,
      status: "upcoming",
    }
    setScheduleEvents((prev) => [newEvent, ...prev])
    void (async () => {
      const result = await postJson("/api/schedule", {
        title: newEvent.title,
        type: newEvent.type,
        start_at: new Date().toISOString(),
        date_label: eventDate,
        time_label: eventTime,
        notes: eventNotes,
        source_message_id: contextId,
        status: newEvent.status,
      })
      const created = result?.data?.[0]
      if (created?.id) {
        setScheduleEvents((prev) => prev.map((event) => (event.id === newEvent.id ? { ...event, id: created.id } : event)))
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
      const result = await postJson("/api/tasks", {
        title: newTask.title,
        status: newTask.status,
        priority: newTask.priority,
        due_date_label: taskDueDate,
        notes: taskNotes,
        source_message_id: contextId,
      })
      const created = result?.data?.[0]
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
    <div className="flex h-[calc(100vh-8rem)] gap-0 rounded-xl border border-border bg-card overflow-hidden">
      {/* Sidebar - Channels & DMs */}
      <div className="w-64 flex-shrink-0 border-r border-border bg-sidebar flex flex-col">
        <div className="p-3 border-b border-border">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="Search messages..." className="h-9 bg-secondary pl-9 text-sm" />
          </div>
        </div>

        <ScrollArea className="flex-1">
          <div className="p-2">
            {/* Channels Section */}
            <button
              onClick={() => setChannelsExpanded(!channelsExpanded)}
              className="flex w-full items-center gap-1 px-2 py-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground"
            >
              {channelsExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              Channels
            </button>
            {channelsExpanded && (
              <div className="space-y-0.5">
                {loadingChannels && (
                  <div className="px-2 py-1 text-xs text-muted-foreground">Loading channels...</div>
                )}
                {channels.map((channel) => (
                  <button
                    key={channel.id}
                    onClick={() => setSelectedChannel(channel.name)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                      selectedChannel === channel.name
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                    )}
                  >
                    {channel.isPrivate ? <Lock className="h-4 w-4" /> : <Hash className="h-4 w-4" />}
                    <span className="flex-1 text-left truncate">{channel.name}</span>
                    {channel.unread && (
                      <Badge variant="secondary" className="h-5 min-w-5 bg-primary text-primary-foreground text-xs">
                        {channel.unread}
                      </Badge>
                    )}
                  </button>
                ))}
                <button className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground">
                  <Plus className="h-4 w-4" />
                  <span>Add Channel</span>
                </button>
              </div>
            )}

            {/* Direct Messages Section */}
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
            {systemMsgExpanded && (
              <div className="space-y-0.5">
                {systemMessages.map((msg) => (
                  <button
                    key={msg.id}
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
          </div>
        </ScrollArea>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col">
        {/* Channel Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <Hash className="h-5 w-5 text-muted-foreground" />
              <h2 className="font-semibold text-foreground">{selectedChannel}</h2>
            </div>
            <Badge variant="outline" className="text-xs">
              <Users className="h-3 w-3 mr-1" />
              24 members
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" className="h-8" onClick={() => openPanel("start-chat")}>
              <MessageSquare className="h-4 w-4 mr-2" />
              Start Chat
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <Phone className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8">
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

        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col">
          <div className="border-b border-border px-4">
            <TabsList className="h-10 bg-transparent gap-4">
              <TabsTrigger
                value="chat"
                className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-1"
              >
                <MessageSquare className="h-4 w-4 mr-2" />
                Chat
              </TabsTrigger>
              <TabsTrigger
                value="tasks"
                className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-1"
              >
                <ListTodo className="h-4 w-4 mr-2" />
                Tasks
                <Badge variant="secondary" className="ml-2 h-5 bg-muted text-xs">
                  {tasks.filter((t) => t.status !== "done").length}
                </Badge>
              </TabsTrigger>
              <TabsTrigger
                value="leads"
                className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-1"
              >
                <Star className="h-4 w-4 mr-2" />
                Leads
                <Badge variant="secondary" className="ml-2 h-5 bg-muted text-xs">
                  {leads.length}
                </Badge>
              </TabsTrigger>
              <TabsTrigger
                value="approvals"
                className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-1"
              >
                <CheckSquare className="h-4 w-4 mr-2" />
                Approvals
                <Badge variant="secondary" className="ml-2 h-5 bg-orange-500/20 text-orange-400 text-xs">
                  {approvals.filter((a) => a.status === "pending").length}
                </Badge>
              </TabsTrigger>
              <TabsTrigger
                value="escalations"
                className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-1"
              >
                <Flag className="h-4 w-4 mr-2" />
                Escalations
                <Badge variant="secondary" className="ml-2 h-5 bg-red-500/20 text-red-400 text-xs">
                  {escalations.length}
                </Badge>
              </TabsTrigger>
              <TabsTrigger
                value="schedule"
                className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-1"
              >
                <Calendar className="h-4 w-4 mr-2" />
                Schedule
              </TabsTrigger>
            </TabsList>
          </div>

          {/* Chat Tab - Added context menu to messages */}
          <TabsContent value="chat" className="flex-1 flex flex-col m-0">
            <ScrollArea className="flex-1 p-4">
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
                        <p className="text-sm text-foreground/90 mt-0.5">{msg.content}</p>
                        {(msg.reactions || msg.thread) && (
                          <div className="flex items-center gap-2 mt-2">
                            {msg.reactions?.map((reaction, i) => (
                              <button
                                key={i}
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
                        <Button variant="ghost" size="icon" className="h-7 w-7">
                          <Smile className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-7 w-7">
                          <MessageSquare className="h-4 w-4" />
                        </Button>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-7 w-7" data-context-trigger>
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                      </div>
                    </div>
                    <DropdownMenuContent align="end" className="w-48">
                      <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-task", msg)}>
                        <ClipboardList className="h-4 w-4" />
                        Create Task
                      </DropdownMenuItem>
                      <DropdownMenuItem className="gap-2">
                        <Reply className="h-4 w-4" />
                        Reply
                      </DropdownMenuItem>
                      <DropdownMenuItem className="gap-2">
                        <PhoneCall className="h-4 w-4" />
                        Call
                      </DropdownMenuItem>
                      <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-event", msg)}>
                        <CalendarPlus className="h-4 w-4" />
                        Schedule
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-approval", msg)}>
                        <CheckSquare className="h-4 w-4" />
                        Create Approval
                      </DropdownMenuItem>
                      <DropdownMenuItem className="gap-2" onClick={() => openPanel("add-escalation", msg)}>
                        <Flag className="h-4 w-4" />
                        Escalate
                      </DropdownMenuItem>
                      <DropdownMenuItem className="gap-2">
                        <Pin className="h-4 w-4" />
                        Pin Message
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                ))}
              </div>
            </ScrollArea>

            {/* Message Input */}
            <div className="p-4 border-t border-border">
              <div className="rounded-lg border border-border bg-secondary/50 p-2">
                <div className="flex items-center gap-2">
                  <Button variant="ghost" size="icon" className="h-8 w-8">
                    <Plus className="h-4 w-4" />
                  </Button>
                  <Input
                    value={messageInput}
                    onChange={(e) => setMessageInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault()
                        handleSend()
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

          {/* Tasks Tab */}
          <TabsContent value="tasks" className="flex-1 m-0 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="p-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-foreground">Team Tasks</h3>
                  <Button size="sm" className="h-8" onClick={() => openPanel("add-task")}>
                    <Plus className="h-4 w-4 mr-1" />
                    New Task
                  </Button>
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
                          <Button size="sm" className="flex-1 bg-green-600 hover:bg-green-700">
                            <CheckCircle2 className="h-4 w-4 mr-1" />
                            Approve
                          </Button>
                          <Button size="sm" variant="destructive" className="flex-1">
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

      {panelOpen && (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/40" onClick={closePanel} />
          <div className="absolute right-0 top-0 h-full w-full max-w-md bg-background border-l border-border flex flex-col">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <div>
                <p className="text-sm text-muted-foreground">
                  {panelType === "start-chat" && "Start Chat"}
                  {panelType === "add-event" && "Add Event"}
                  {panelType === "add-task" && "Add Task"}
                  {panelType === "add-approval" && "Add Approval"}
                  {panelType === "add-escalation" && "Escalate"}
                </p>
                <h3 className="text-lg font-semibold text-foreground">
                  {panelType === "start-chat" && "Start a conversation"}
                  {panelType === "add-event" && "Schedule an event"}
                  {panelType === "add-task" && "Create a new task"}
                  {panelType === "add-approval" && "Request approval"}
                  {panelType === "add-escalation" && "Create an escalation"}
                </h3>
              </div>
              <Button variant="ghost" size="icon" onClick={closePanel}>
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
                        value={eventDate}
                        onChange={(e) => setEventDate(e.target.value)}
                        placeholder="Today"
                        className="mt-2"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">Time</label>
                      <Input
                        value={eventTime}
                        onChange={(e) => setEventTime(e.target.value)}
                        placeholder="09:00"
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
