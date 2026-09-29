export interface AgentMailPod {
  id: string
  name: string
  tenantId: string
  isDefault: boolean
  description?: string
  inboxCount: number
  createdAt: string
}

export type AgentPersonaType =
  | "sales"
  | "smart_label"
  | "auto_reply"
  | "finance"
  | "support"
  | "human"

export interface AgentMailbox {
  id: string
  podId: string
  emailAddress: string
  displayName: string
  agentType: AgentPersonaType
  isHuman: boolean
  domain: string
  autoReplyEnabled: boolean
  smartLabelEnabled: boolean
  inboundChannelId?: string
  assignedUser?: string
  unreadCount: number
  totalCount: number
  isActive: boolean
  createdAt: string
}

export interface AgentMailAttachment {
  id: string
  filename: string
  sizeBytes: number
  mimeType: string
  url?: string
}

export interface AgentMailMessage {
  id: string
  threadId: string
  direction: "inbound" | "outbound"
  sender: string
  senderEmail: string
  recipient: string
  recipientEmail: string
  subject: string
  bodyText: string
  bodyHtml?: string
  status: "received" | "processed" | "auto_replied" | "sent" | "draft" | "failed"
  agentResponse?: string
  agentSuggestedReply?: string
  smartLabelConfidence?: number
  attachments?: AgentMailAttachment[]
  createdAt: string
}

export interface AgentMailThread {
  id: string
  podId: string
  mailboxId: string
  sender: string
  senderEmail: string
  recipientEmail: string
  subject: string
  snippet: string
  unread: boolean
  isStarred: boolean
  folder: "inbox" | "sent" | "drafts" | "scheduled" | "trash" | "other"
  labels: string[]
  assignedAgent?: AgentPersonaType
  messagesCount: number
  hasAttachments: boolean
  dateGroup: string // e.g. "Sep 7", "Today"
  timestamp: string
  aiAnalysis?: {
    sentiment: "positive" | "neutral" | "negative" | "urgent"
    category: string
    confidence: number
    suggestedAction: "auto_reply" | "create_task" | "request_approval" | "escalate" | "none"
    leadScore?: number
    quoteAmount?: string
    notes?: string
  }
  messages: AgentMailMessage[]
}

export interface AgentMailLabel {
  id: string
  name: string
  color: string
  count: number
}

export interface AgentMailListRule {
  id: string
  podId: string
  type: "allow" | "block"
  pattern: string
  target: "email" | "domain" | "ip"
  reason: string
  createdAt: string
}

export interface AgentMailDomain {
  id: string
  podId: string
  domain: string
  status: "verified" | "pending" | "failed"
  mxValid: boolean
  spfValid: boolean
  dkimValid: boolean
  dmarcValid: boolean
  dnsRecords: {
    type: "MX" | "TXT" | "CNAME"
    host: string
    value: string
    status: "valid" | "pending"
  }[]
  createdAt: string
}

export interface AgentMailMetrics {
  totalInbound: number
  totalOutbound: number
  automatedRepliesSent: number
  avgResponseSeconds: number
  smartLabelAccuracy: number
  pendingApprovals: number
  escalatedToHuman: number
  activeAgents: number
  deliveryRate: number
  volumeByHour: { hour: string; inbound: number; outbound: number }[]
  categoryDistribution: { category: string; count: number; percentage: number }[]
}

export interface AgentMailPermission {
  id: string
  role: "admin" | "operator" | "viewer"
  userEmail: string
  userName: string
  inboxAccess: "all" | string[]
  canSend: boolean
  canConfigureAgents: boolean
  canApproveQuotes: boolean
}

export interface SharedMailboxMember {
  userId: string
  name: string
  email: string
  role: "admin" | "operator" | "member" | "viewer"
  avatar: string
  addedAt: string
}

export interface SharedMailboxGroup {
  id: string
  mailboxId: string
  name: string
  emailAddress: string
  description: string
  members: SharedMailboxMember[]
  assignedAgents: AgentPersonaType[]
  sharedFolders: string[]
  inboundChannelId?: string
  autoReplyApprovalRequired: boolean
  escalationChannel?: string
  unreadCount: number
  totalCount: number
}

export interface SharedMailFolder {
  id: string
  name: string
  mailboxId: string
  icon?: string
  threadCount: number
  members: string[]
}

