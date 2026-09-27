"use client"

import React, { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Sparkles,
  Award,
  Gift,
  Plus,
  Heart,
  Send,
  CheckCircle2,
  Calendar,
  MessageSquare,
  Smile,
  Users,
  Search,
  Check,
  X,
  Star,
  Compass,
  Target,
  Shield,
  Zap,
  Bot,
  Brain,
  Cpu,
  Layers,
  Flame,
  Radio,
  Workflow,
  Copy,
  Edit3,
  RefreshCw,
  ExternalLink,
  ArrowRight,
  TrendingUp,
  Sliders,
  CheckCircle,
  Lightbulb,
  Play,
  FileText,
  AlertTriangle,
  Activity,
  Trash2,
  Terminal,
  HelpCircle,
  Wand2,
} from "lucide-react"
import type { Employee } from "@/lib/hr-api"
import { getEmployeeAvatar } from "./pim-directory-view"

interface TalentCultureViewProps {
  employees: Employee[]
}

export type PeerBadge = "#NetworkHero" | "#CustomerObsessed" | "#FiberChampion" | "#SafetyFirst" | "#TeamPlayer"

export interface PeerKudo {
  id: string
  fromName: string
  toName: string
  badge: PeerBadge
  message: string
  date: string
  likes: number
}

interface LongServiceMilestone {
  employeeName: string
  jobTitle: string
  department: string
  hireDate: string
  yearsOfService: number
  tier: "3-Year Bronze" | "5-Year Silver" | "10-Year Gold Sovereign"
  award: string
}

interface PulseSurvey {
  id: string
  title: string
  department: string
  questionsCount: number
  responseRate: string
  status: "Active" | "Closed" | "Draft"
  createdDate: string
}

export interface StrategicObjective {
  id: string
  pillar: string
  title: string
  targetMetric: string
  currentProgress: string
  progressPercent: number
  cascadedDirective: string
  status: "On Track" | "Near Target" | "Accelerating"
}

export interface TechnicalStrategy {
  id: string
  title: string
  focusArea: string
  description: string
  architectureKey: string
}

export interface CoreValue {
  id: string
  number: number
  title: string
  icon: string
  principle: string
  behaviorDirective: string
  linkedBadge: PeerBadge
}

export interface DecisionRule {
  level: number
  name: string
  scope: string
  rule: string
  color: string
}

export interface SubAgentMapping {
  agentName: string
  role: string
  llmModel: string
  inheritedObjective: string
  governingValue: string
  alignmentStatus: "Synchronized & Active" | "Standby"
}

export interface FreeTestResult {
  query: string
  evaluatedAt: string
  matchedObjectives: Array<{ title: string; pillar: string; reason: string }>
  governingValues: Array<{ title: string; icon: string; directive: string }>
  safetyGuards: string[]
  autonomousAction: string
  suggestedKudos: { recipient: string; badge: PeerBadge; message: string }
}

export function TalentCultureView({ employees }: TalentCultureViewProps) {
  // Navigation: Strategy in front of Kudos, Service, and Surveys
  const [activeTab, setActiveTab] = useState<"strategy" | "kudos" | "service" | "surveys">("strategy")
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // ── Strategy State (Fully Dynamic & User-Editable) ─────────────────────────
  const [companyMission, setCompanyMission] = useState(
    "Connecting South African homes, townships, and enterprise corridors with hyper-reliable, uncapped fiber and carrier-grade wireless broadband. We democratize digital access through resilient local infrastructure, high-touch empathy, and world-class network automation."
  )
  const [companyVision, setCompanyVision] = useState(
    "To become Southern Africa's premier autonomous telecommunications network by 2030—powering 1,000,000 premises with 99.999% availability ('five nines'), zero-touch line provisioning, Stage 6 loadshedding immunity, and industry-benchmark customer NPS."
  )

  const [decisionHierarchy, setDecisionHierarchy] = useState<DecisionRule[]>([
    {
      level: 1,
      name: "Safety & Statutory Compliance",
      scope: "OHS Act, RICA subscriber verification, ICASA license rules, POPIA privacy",
      rule: "Absolute veto over speed, installation backlog, or revenue goals. Never bypass safety or statutory validation.",
      color: "border-red-500/40 text-red-400 bg-red-950/20",
    },
    {
      level: 2,
      name: "Radical Infrastructure Integrity & Core SLA",
      scope: "99.995% Network Availability & Teraco/NAPAfrica BGP stability",
      rule: "Core packet transit, DC battery reserves, and optical ring survivability outrank non-critical feature changes.",
      color: "border-amber-500/40 text-amber-400 bg-amber-950/20",
    },
    {
      level: 3,
      name: "Customer Empathy & Radical Transparency",
      scope: "NPS 75+ & First Contact Resolution > 88%",
      rule: "No subscriber is a statistic. Communicate in plain South African English; proactive notice within 90s of any outage.",
      color: "border-cyan-500/40 text-cyan-400 bg-cyan-950/20",
    },
    {
      level: 4,
      name: "Velocity with Uncompromising Precision",
      scope: "FTTH installs < 72h, zero splice loss backlog",
      rule: "Deploy fast, but measure twice. Mandatory OTDR verification (<0.02 dB loss) before technician signs off site.",
      color: "border-blue-500/40 text-blue-400 bg-blue-950/20",
    },
    {
      level: 5,
      name: "Cost Efficiency & Automation",
      scope: "AI Orchestrator & sub-agent self-healing",
      rule: "Automate routine friction to elevate human craft, never to replace human judgment or accountability.",
      color: "border-emerald-500/40 text-emerald-400 bg-emerald-950/20",
    },
  ])

  const [strategicObjectives, setStrategicObjectives] = useState<StrategicObjective[]>([
    {
      id: "OKR-1",
      pillar: "Infrastructure Reliability",
      title: "Radical Core Redundancy & Uptime",
      targetMetric: "99.995% Network Availability across all Metro POPs",
      currentProgress: "99.98% Active SLA",
      progressPercent: 99.8,
      cascadedDirective: "NOC Telemetry & SupportBot trigger automated BGP route flapping dampening and instant failover to Teraco/NAPAfrica transit.",
      status: "On Track",
    },
    {
      id: "OKR-2",
      pillar: "Network Expansion",
      title: "Metro & Township Fiber Penetration",
      targetMetric: "120,000 Live FTTH/B premises connected",
      currentProgress: "94,200 Connected (78.5%)",
      progressPercent: 78.5,
      cascadedDirective: "ProvisionBot streamlines RICA identity verification & same-week field installation dispatch within 72 hours.",
      status: "On Track",
    },
    {
      id: "OKR-3",
      pillar: "Subscriber Experience",
      title: "Unrivaled Customer Trust & NPS",
      targetMetric: "Net Promoter Score 75+ & First Contact Resolution > 88%",
      currentProgress: "NPS 72 (+3 pts needed) | 87.4% FCR",
      progressPercent: 88,
      cascadedDirective: "DomeBot & ChurnGuard detect subscriber sentiment degradation early and issue proactive credits or bandwidth boosts.",
      status: "Near Target",
    },
    {
      id: "OKR-4",
      pillar: "High-Performance Culture",
      title: "Sustainable Team Growth & Retention",
      targetMetric: "Voluntary turnover < 4% & Employee pulse sentiment > 90%",
      currentProgress: "3.8% Turnover | 91% Sentiment Index",
      progressPercent: 92,
      cascadedDirective: "StaffBot monitors shift fatigue, prompts peer kudos distribution, and tracks mandatory FOA/MikroTik certifications.",
      status: "On Track",
    },
  ])

  const [technicalStrategies, setTechnicalStrategies] = useState<TechnicalStrategy[]>([
    {
      id: "TECH-1",
      title: "Zero-Trust Edge & MikroTik Automation",
      focusArea: "Edge Security & Routing",
      description: "Centralized FreeRADIUS AAA enforcement, dynamic RouterOS v7 API automation, client VLAN isolation, and canary firmware deployment pipelines.",
      architectureKey: "MikroTik / FreeRADIUS",
    },
    {
      id: "TECH-2",
      title: "Autonomous Self-Healing NOC",
      focusArea: "Optical Observability",
      description: "Telemetry-driven optical loss anomaly detection, automated DWDM channel protection switching, and instant alarm dispatch via Hermes event bus.",
      architectureKey: "Hermes Bus / Prometheus",
    },
    {
      id: "TECH-3",
      title: "Stage 6 Loadshedding Grid Resilience",
      focusArea: "Power Sovereignty",
      description: "8-hour lithium-iron phosphate (LiFePO4) battery backup + integrated solar MPPT arrays on 100% of distribution POPs with automated depletion alerts.",
      architectureKey: "Solar / LiFePO4 / SNMP",
    },
    {
      id: "TECH-4",
      title: "Single-Pane API Integration Fabric",
      focusArea: "Data & Workflow Mesh",
      description: "Real-time bidirectional event synchronization uniting Splynx billing, FreeRADIUS sessions, Netbox IPAM, and the AI Orchestrator.",
      architectureKey: "Splynx / Netbox API / LLM",
    },
  ])

  const [companyValues, setCompanyValues] = useState<CoreValue[]>([
    {
      id: "VAL-1",
      number: 1,
      title: "Radical Reliability & Integrity",
      icon: "🛡️",
      principle: "Uptime is sacred. We honor our commitments to our subscribers, our teammates, and our regulatory partners. If something breaks, we own it immediately.",
      behaviorDirective: "Own mistakes immediately without finger-pointing. Never ignore a network alert. Keep tickets and post-mortems transparent in real-time.",
      linkedBadge: "#NetworkHero",
    },
    {
      id: "VAL-2",
      number: 2,
      title: "Customer Obsession with Deep Empathy",
      icon: "💙",
      principle: "No ticket is just a metric. Behind every connection is a learner studying, a clinic communicating, or a family-run business transacting.",
      behaviorDirective: "Listen before responding. Explain technical issues in plain, respectful South African terms. Follow up until the customer is truly satisfied.",
      linkedBadge: "#CustomerObsessed",
    },
    {
      id: "VAL-3",
      number: 3,
      title: "Velocity with Uncompromising Precision",
      icon: "⚡",
      principle: "We deploy fast, but we never compromise on safety, RICA compliance, or fiber bend radius. Fast does not mean reckless.",
      behaviorDirective: "Measure twice, splice once. Adhere strictly to OHS Act safety protocols on poles and cherry pickers. Complete OTDR trace verifications before leaving site.",
      linkedBadge: "#FiberChampion",
    },
    {
      id: "VAL-4",
      number: 4,
      title: "Extreme Ownership & One-Team Spirit",
      icon: "🤝",
      principle: "We win and lose together across NOC, field technicians, customer support, and finance. Leave no loose loops.",
      behaviorDirective: "Never say 'that's not my job'. Step up to help colleagues during major fiber cuts or storm restorations. Celebrate peer achievements loudly.",
      linkedBadge: "#TeamPlayer",
    },
    {
      id: "VAL-5",
      number: 5,
      title: "Continuous Innovation & Lifelong Learning",
      icon: "🚀",
      principle: "We don't fear AI or automation—we orchestrate it. Every employee is empowered to upskill and elevate their craft.",
      behaviorDirective: "Complete monthly MikroTik and fiber certifications. Proactively suggest workflow automations. Treat every outage post-mortem as a learning opportunity.",
      linkedBadge: "#NetworkHero",
    },
  ])

  const [subAgentMappings] = useState<SubAgentMapping[]>([
    {
      agentName: "InsightBot (Executive)",
      role: "Executive Intelligence & Cross-Dept Briefings",
      llmModel: "Llama 3.3 70B / Claude 3.5 Sonnet",
      inheritedObjective: "Synthesizes company revenue, network SLA, and headcount against all Strategic OKRs.",
      governingValue: "Radical Reliability & Integrity",
      alignmentStatus: "Synchronized & Active",
    },
    {
      agentName: "StaffBot (Talent Orchestrator)",
      role: "Workforce Health, Scheduling & Sentiment",
      llmModel: "Qwen 2.5 7B / DeepSeek-R1",
      inheritedObjective: "Ensures employee wellness, balances 24/7 on-call shift fatigue, and fosters Kudos recognition.",
      governingValue: "Extreme Ownership & Lifelong Learning",
      alignmentStatus: "Synchronized & Active",
    },
    {
      agentName: "ChurnGuard (Retention)",
      role: "Proactive Churn Mitigation & LTV Defense",
      llmModel: "Llama 3.3 70B",
      inheritedObjective: "Directly drives OKR #3 (NPS 75+) by identifying at-risk subscribers before cancellation.",
      governingValue: "Customer Obsession with Deep Empathy",
      alignmentStatus: "Synchronized & Active",
    },
    {
      agentName: "SupportBot (NOC Diagnostics)",
      role: "Automated Ticket Resolution & Diagnostics",
      llmModel: "Qwen 2.5 7B",
      inheritedObjective: "Drives OKR #1 (99.995% SLA) via instantaneous optical line telemetry and diagnostic routing.",
      governingValue: "Velocity with Uncompromising Precision",
      alignmentStatus: "Synchronized & Active",
    },
    {
      agentName: "DomeBot (Customer Care)",
      role: "Subscriber Self-Service & Billing Assistant",
      llmModel: "Qwen 2.5 7B",
      inheritedObjective: "Provides empathetic, instant resolution for South African subscribers on WhatsApp & Portal.",
      governingValue: "Customer Obsession with Deep Empathy",
      alignmentStatus: "Synchronized & Active",
    },
    {
      agentName: "ProvisionBot (Line Provisioning)",
      role: "Automated Fiber Onboarding & RICA Agent",
      llmModel: "Qwen 2.5 7B",
      inheritedObjective: "Drives OKR #2 (120k FTTH) via automated RICA verification and field install dispatching.",
      governingValue: "Velocity with Uncompromising Precision",
      alignmentStatus: "Synchronized & Active",
    },
  ])

  // ── FREE-TEST PLAYGROUND STATE ─────────────────────────────────────────────
  const [freeTestQuery, setFreeTestQuery] = useState("")
  const [selectedAgentTarget, setSelectedAgentTarget] = useState("all")
  const [isEvaluatingFreeTest, setIsEvaluatingFreeTest] = useState(false)
  const [freeTestResult, setFreeTestResult] = useState<FreeTestResult | null>(null)
  const [activeHighlightCategory, setActiveHighlightCategory] = useState<string | null>(null)

  // ── MODALS STATE (Full CRUD for Objectives, Values, Strategies) ────────────
  const [isSyncing, setIsSyncing] = useState(false)
  const [lastSyncedTime, setLastSyncedTime] = useState("Just now (Active in LLM Context)")
  const [viewPromptModalOpen, setViewPromptModalOpen] = useState(false)
  const [editStrategyModalOpen, setEditStrategyModalOpen] = useState(false)

  // Add / Edit OKR Modal
  const [okrModalOpen, setOkrModalOpen] = useState(false)
  const [editingOkr, setEditingOkr] = useState<StrategicObjective | null>(null)
  const [okrPillar, setOkrPillar] = useState("")
  const [okrTitle, setOkrTitle] = useState("")
  const [okrMetric, setOkrMetric] = useState("")
  const [okrProgress, setOkrProgress] = useState("")
  const [okrPercent, setOkrPercent] = useState<number>(75)
  const [okrDirective, setOkrDirective] = useState("")

  // Add / Edit Value Modal
  const [valueModalOpen, setValueModalOpen] = useState(false)
  const [editingValue, setEditingValue] = useState<CoreValue | null>(null)
  const [valueTitle, setValueTitle] = useState("")
  const [valueIcon, setValueIcon] = useState("⭐")
  const [valuePrinciple, setValuePrinciple] = useState("")
  const [valueDirective, setValueDirective] = useState("")
  const [valueBadge, setValueBadge] = useState<PeerBadge>("#NetworkHero")

  // Edit Mission/Vision State
  const [editMission, setEditMission] = useState(companyMission)
  const [editVision, setEditVision] = useState(companyVision)

  // Kudos State
  const [kudosList, setKudosList] = useState<PeerKudo[]>([
    {
      id: "1",
      fromName: "Thabo Nkosi (CTO)",
      toName: "Lerato Molefe",
      badge: "#NetworkHero",
      message: "Unbelievable diagnostic work during the late night Rosebank OLT power fluctuation. Kept all enterprise uplinks green, upholding our 99.995% uptime objective.",
      date: "Yesterday",
      likes: 8,
    },
    {
      id: "2",
      fromName: "Willem Botha (Head of Field)",
      toName: "Musa Sithole",
      badge: "#FiberChampion",
      message: "Spliced 144 cores in a record 3.5 hours for the Waterfall Estate expansion with zero dB splice loss. Embodiment of 'Velocity with Precision'.",
      date: "2 days ago",
      likes: 12,
    },
    {
      id: "3",
      fromName: "Zanele Khumalo (Support)",
      toName: "Mandla Sithole",
      badge: "#CustomerObsessed",
      message: "Walked an elderly subscriber through their Wi-Fi 6 router setup with extreme patience. Received a glowing 5-star Google review for OmniDome!",
      date: "3 days ago",
      likes: 6,
    },
    {
      id: "4",
      fromName: "Pieter van Wyk (CEO)",
      toName: "Johan Pretorius",
      badge: "#SafetyFirst",
      message: "Safely halted cherry-picker operations during the heavy highveld lightning storm in Midrand. Zero incidents, safety code strictly upheld.",
      date: "4 days ago",
      likes: 15,
    },
  ])

  // Long Service State
  const [milestones] = useState<LongServiceMilestone[]>([
    {
      employeeName: "Pieter van Wyk",
      jobTitle: "Chief Executive Officer",
      department: "Executive",
      hireDate: "2019-02-14",
      yearsOfService: 7,
      tier: "5-Year Silver",
      award: "R 25,000 Travel Voucher + Silver Plaque",
    },
    {
      employeeName: "Ayesha Patel",
      jobTitle: "HR & Payroll Specialist",
      department: "Human Resources",
      hireDate: "2020-09-01",
      yearsOfService: 6,
      tier: "5-Year Silver",
      award: "R 25,000 Travel Voucher + Silver Plaque",
    },
    {
      employeeName: "Johan Pretorius",
      jobTitle: "NOC Team Lead",
      department: "Network Operations",
      hireDate: "2021-11-20",
      yearsOfService: 5,
      tier: "5-Year Silver",
      award: "R 25,000 Travel Voucher + Silver Plaque",
    },
    {
      employeeName: "Thabo Nkosi",
      jobTitle: "Chief Technology Officer",
      department: "Executive",
      hireDate: "2022-05-16",
      yearsOfService: 4,
      tier: "3-Year Bronze",
      award: "R 10,000 Tech Allowance + Bronze Plaque",
    },
  ])

  // Pulse Surveys State
  const [surveys, setSurveys] = useState<PulseSurvey[]>([
    {
      id: "SRV-001",
      title: "Q3 Strategic Alignment & Equipment Dipstick Survey",
      department: "Field Operations",
      questionsCount: 8,
      responseRate: "94%",
      status: "Active",
      createdDate: "2026-09-15",
    },
    {
      id: "SRV-002",
      title: "NOC 24/7 Shift Standby & Fatigue Index Survey",
      department: "Network Operations",
      questionsCount: 6,
      responseRate: "88%",
      status: "Active",
      createdDate: "2026-09-18",
    },
    {
      id: "SRV-003",
      title: "Core Values Pulse: 'Are We Customer Obsessed?'",
      department: "All Departments",
      questionsCount: 5,
      responseRate: "91%",
      status: "Active",
      createdDate: "2026-09-22",
    },
  ])

  // Modals state
  const [kudosModalOpen, setKudosModalOpen] = useState(false)
  const [selectedRecipient, setSelectedRecipient] = useState(employees[0]?.full_name || "Musa Sithole")
  const [kudosBadge, setKudosBadge] = useState<PeerBadge>("#NetworkHero")
  const [kudosText, setKudosText] = useState("")

  const [surveyModalOpen, setSurveyModalOpen] = useState(false)
  const [newSurveyTitle, setNewSurveyTitle] = useState("")
  const [newSurveyDept, setNewSurveyDept] = useState("All Departments")
  const [newQuestion1, setNewQuestion1] = useState("")
  const [newQuestion2, setNewQuestion2] = useState("")

  // ── Sync to Orchestrator ──────────────────────────────────────────────────
  const handleSyncOrchestrator = () => {
    setIsSyncing(true)
    setTimeout(() => {
      setIsSyncing(false)
      const nowStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      setLastSyncedTime(`Today, ${nowStr} (Synced)`)
      setToastMessage("Corporate Strategy, Values & Non-Negotiables synchronized with AI Orchestrator! 7 sub-agents updated.")
      setTimeout(() => setToastMessage(null), 4000)
    }, 900)
  }

  // ── Save Mission/Vision ───────────────────────────────────────────────────
  const handleSaveStrategy = (e: React.FormEvent) => {
    e.preventDefault()
    setCompanyMission(editMission)
    setCompanyVision(editVision)
    setEditStrategyModalOpen(false)
    handleSyncOrchestrator()
  }

  // ── Add/Edit OKR ──────────────────────────────────────────────────────────
  const openNewOkrModal = () => {
    setEditingOkr(null)
    setOkrPillar("Network Engineering")
    setOkrTitle("")
    setOkrMetric("")
    setOkrProgress("")
    setOkrPercent(50)
    setOkrDirective("")
    setOkrModalOpen(true)
  }

  const openEditOkrModal = (okr: StrategicObjective) => {
    setEditingOkr(okr)
    setOkrPillar(okr.pillar)
    setOkrTitle(okr.title)
    setOkrMetric(okr.targetMetric)
    setOkrProgress(okr.currentProgress)
    setOkrPercent(okr.progressPercent)
    setOkrDirective(okr.cascadedDirective)
    setOkrModalOpen(true)
  }

  const handleSaveOkr = (e: React.FormEvent) => {
    e.preventDefault()
    if (editingOkr) {
      setStrategicObjectives((prev) =>
        prev.map((o) =>
          o.id === editingOkr.id
            ? {
                ...o,
                pillar: okrPillar,
                title: okrTitle,
                targetMetric: okrMetric,
                currentProgress: okrProgress,
                progressPercent: okrPercent,
                cascadedDirective: okrDirective,
              }
            : o
        )
      )
      setToastMessage(`Updated objective "${okrTitle}"`)
    } else {
      const newObj: StrategicObjective = {
        id: `OKR-${strategicObjectives.length + 1}`,
        pillar: okrPillar,
        title: okrTitle,
        targetMetric: okrMetric,
        currentProgress: okrProgress || "0% Inception",
        progressPercent: okrPercent,
        cascadedDirective: okrDirective,
        status: okrPercent >= 90 ? "On Track" : okrPercent >= 70 ? "Near Target" : "Accelerating",
      }
      setStrategicObjectives((prev) => [...prev, newObj])
      setToastMessage(`Added new strategic objective "${newObj.title}"!`)
    }
    setOkrModalOpen(false)
    handleSyncOrchestrator()
  }

  const handleDeleteOkr = (id: string) => {
    setStrategicObjectives((prev) => prev.filter((o) => o.id !== id))
    setToastMessage("Strategic objective removed from charter")
    setTimeout(() => setToastMessage(null), 2500)
    handleSyncOrchestrator()
  }

  // ── Add/Edit Value ────────────────────────────────────────────────────────
  const openNewValueModal = () => {
    setEditingValue(null)
    setValueTitle("")
    setValueIcon("🌟")
    setValuePrinciple("")
    setValueDirective("")
    setValueBadge("#NetworkHero")
    setValueModalOpen(true)
  }

  const openEditValueModal = (val: CoreValue) => {
    setEditingValue(val)
    setValueTitle(val.title)
    setValueIcon(val.icon)
    setValuePrinciple(val.principle)
    setValueDirective(val.behaviorDirective)
    setValueBadge(val.linkedBadge)
    setValueModalOpen(true)
  }

  const handleSaveValue = (e: React.FormEvent) => {
    e.preventDefault()
    if (editingValue) {
      setCompanyValues((prev) =>
        prev.map((v) =>
          v.id === editingValue.id
            ? {
                ...v,
                title: valueTitle,
                icon: valueIcon,
                principle: valuePrinciple,
                behaviorDirective: valueDirective,
                linkedBadge: valueBadge,
              }
            : v
        )
      )
      setToastMessage(`Updated Core Value: "${valueTitle}"`)
    } else {
      const newVal: CoreValue = {
        id: `VAL-${companyValues.length + 1}`,
        number: companyValues.length + 1,
        title: valueTitle,
        icon: valueIcon,
        principle: valuePrinciple,
        behaviorDirective: valueDirective,
        linkedBadge: valueBadge,
      }
      setCompanyValues((prev) => [...prev, newVal])
      setToastMessage(`Added Core Value ${newVal.number}: "${newVal.title}"!`)
    }
    setValueModalOpen(false)
    handleSyncOrchestrator()
  }

  const handleDeleteValue = (id: string) => {
    setCompanyValues((prev) => prev.filter((v) => v.id !== id))
    setToastMessage("Core value removed from company charter")
    setTimeout(() => setToastMessage(null), 2500)
    handleSyncOrchestrator()
  }

  // ── FREE-TEST RUNNER (Dynamic Evaluation of ANY Query) ───────────────────
  const handleRunFreeTest = () => {
    if (!freeTestQuery.trim()) {
      setToastMessage("Please enter a question or operational scenario to test!")
      setTimeout(() => setToastMessage(null), 3000)
      return
    }

    setIsEvaluatingFreeTest(true)
    setActiveHighlightCategory("evaluating")

    setTimeout(() => {
      const q = freeTestQuery.toLowerCase()

      // Dynamically match against the user's active strategic objectives
      const matchedObs = strategicObjectives
        .filter((o) => {
          const text = `${o.title} ${o.pillar} ${o.cascadedDirective}`.toLowerCase()
          if (q.includes("outage") || q.includes("sla") || q.includes("down") || q.includes("cut") || q.includes("bgp")) {
            return o.pillar.toLowerCase().includes("reliability") || o.title.toLowerCase().includes("redundancy")
          }
          if (q.includes("install") || q.includes("delay") || q.includes("fiber") || q.includes("expansion") || q.includes("township")) {
            return o.pillar.toLowerCase().includes("expansion") || o.title.toLowerCase().includes("penetration")
          }
          if (q.includes("customer") || q.includes("cancel") || q.includes("slow") || q.includes("nps") || q.includes("billing")) {
            return o.pillar.toLowerCase().includes("subscriber") || o.title.toLowerCase().includes("trust")
          }
          if (q.includes("fatigue") || q.includes("overtime") || q.includes("safety") || q.includes("shift") || q.includes("training")) {
            return o.pillar.toLowerCase().includes("culture") || o.title.toLowerCase().includes("team")
          }
          return false
        })
        .map((o) => ({
          title: o.title,
          pillar: o.pillar,
          reason: `Query intersects with target '${o.targetMetric}'. Orchestrator prioritizes: ${o.cascadedDirective}`,
        }))

      // Fallback if broad
      const finalMatchedObs =
        matchedObs.length > 0
          ? matchedObs
          : [
              {
                title: strategicObjectives[0]?.title || "Radical Core Redundancy",
                pillar: strategicObjectives[0]?.pillar || "Infrastructure",
                reason: "General operational query evaluated under primary SLA and network uptime commitments.",
              },
            ]

      // Dynamically match against active values
      const matchedVals = companyValues.filter((v) => {
        if (q.includes("safety") || q.includes("storm") || q.includes("fast") || q.includes("splice")) {
          return v.title.includes("Velocity") || v.linkedBadge === "#SafetyFirst" || v.linkedBadge === "#FiberChampion"
        }
        if (q.includes("customer") || q.includes("empathy") || q.includes("cancel") || q.includes("angry")) {
          return v.title.includes("Customer") || v.linkedBadge === "#CustomerObsessed"
        }
        if (q.includes("outage") || q.includes("down") || q.includes("fail") || q.includes("break")) {
          return v.title.includes("Reliability") || v.linkedBadge === "#NetworkHero"
        }
        if (q.includes("overtime") || q.includes("team") || q.includes("shift") || q.includes("colleague")) {
          return v.title.includes("Ownership") || v.linkedBadge === "#TeamPlayer"
        }
        return v.title.includes("Learning") || v.title.includes("Innovation")
      })

      const finalMatchedVals = matchedVals.length > 0 ? matchedVals : [companyValues[0] || companyValues[1]]

      // Check Statutory & Safety Guards
      const guards: string[] = []
      if (q.includes("safety") || q.includes("storm") || q.includes("pole") || q.includes("rain") || q.includes("hazard")) {
        guards.push("OHS Act Section 8: Immediate work-stop enforced for electrical storm / lightning hazard on aerial plant.")
      }
      if (q.includes("rica") || q.includes("id") || q.includes("install") || q.includes("address")) {
        guards.push("RICA Statutory Veto: No service activation permitted without verified physical proof of residence.")
      }
      if (q.includes("overtime") || q.includes("standby") || q.includes("hours") || q.includes("night")) {
        guards.push("BCEA Chapter 2: Mandatory 12 consecutive hours daily rest interval. Overtime capped at 10h/week.")
      }
      if (guards.length === 0) {
        guards.push("ICASA Quality of Service: 99.5% minimum core throughput guarantee & POPIA data confidentiality.")
      }

      // Generate Autonomous Agent Response
      let autoAction = ""
      if (q.includes("storm") || q.includes("lightning") || q.includes("hazard")) {
        autoAction =
          "StaffBot triggers emergency stop-work order to technicians' mobile devices via push notification. Dispatches SMS notifications to affected subscribers rescheduling appointment windows with polite highveld weather explanation. Zero safety compromises permitted."
      } else if (q.includes("outage") || q.includes("cut") || q.includes("down") || q.includes("bgp")) {
        autoAction =
          "SupportBot autonomously queries Hermes event bus telemetry, dampens flapping BGP routes, fails over transit to Teraco JB1/CT1 ring, and triggers proactive WhatsApp notices to affected customers within 60 seconds with estimated restoral countdown."
      } else if (q.includes("install") || q.includes("delay") || q.includes("rica")) {
        autoAction =
          "ProvisionBot geocodes customer pin via Google Maps & Splynx API, validates RICA document in real time, and auto-dispatches nearest Field Service Van with an optimized route to satisfy same-week turnaround."
      } else {
        autoAction =
          "Orchestrator synthesizes situation against corporate charter. Evaluates blast radius, applies relevant tool policy, and produces action plan aligned with executive OKRs and 5 Core Values."
      }

      const assignedBadge = finalMatchedVals[0]?.linkedBadge || "#NetworkHero"
      const kudoRecipient = employees[0]?.full_name || "Musa Sithole"

      setFreeTestResult({
        query: freeTestQuery,
        evaluatedAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        matchedObjectives: finalMatchedObs,
        governingValues: finalMatchedVals.map((v) => ({
          title: v.title,
          icon: v.icon,
          directive: v.behaviorDirective,
        })),
        safetyGuards: guards,
        autonomousAction: autoAction,
        suggestedKudos: {
          recipient: kudoRecipient,
          badge: assignedBadge,
          message: `Demonstrated exceptional adherence to "${finalMatchedVals[0]?.title}" during test scenario resolution.`,
        },
      })

      setIsEvaluatingFreeTest(false)
      setActiveHighlightCategory("results")
      setToastMessage("Free-form strategy evaluation complete!")
      setTimeout(() => setToastMessage(null), 3000)
    }, 700)
  }

  // Preset Scenario helper to populate the free-test query
  const handleQuickInsert = (text: string) => {
    setFreeTestQuery(text)
  }

  const handleSendKudos = (e: React.FormEvent) => {
    e.preventDefault()
    const newK: PeerKudo = {
      id: String(Date.now()),
      fromName: "Pieter van Wyk (Executive)",
      toName: selectedRecipient,
      badge: kudosBadge,
      message: kudosText,
      date: "Just now",
      likes: 1,
    }
    setKudosList((prev) => [newK, ...prev])
    setToastMessage(`Kudos sent to ${selectedRecipient} with badge ${kudosBadge}!`)
    setTimeout(() => setToastMessage(null), 3000)
    setKudosModalOpen(false)
    setKudosText("")
  }

  const handleCreateSurvey = (e: React.FormEvent) => {
    e.preventDefault()
    const newS: PulseSurvey = {
      id: `SRV-${String(surveys.length + 1).padStart(3, "0")}`,
      title: newSurveyTitle,
      department: newSurveyDept,
      questionsCount: 5,
      responseRate: "0%",
      status: "Active",
      createdDate: new Date().toISOString().split("T")[0],
    }
    setSurveys((prev) => [newS, ...prev])
    setToastMessage(`Pulse Survey "${newS.title}" published for ${newSurveyDept}!`)
    setTimeout(() => setToastMessage(null), 3000)
    setSurveyModalOpen(false)
    setNewSurveyTitle("")
  }

  // Compile LLM System Prompt Text dynamically from current state
  const compiledSystemPrompt = `[OMNIDOME CORPORATE STRATEGY & ALIGNMENT CHARTER]
COMPANY MISSION:
${companyMission}

COMPANY 2030 VISION:
${companyVision}

DECISION-MAKING HIERARCHY & NON-NEGOTIABLE TRADE-OFFS:
${decisionHierarchy.map((d) => `  ${d.level}. ${d.name} (${d.scope}) — ${d.rule}`).join("\n")}

STRATEGIC OBJECTIVES (OKRs):
${strategicObjectives.map((o) => `  • [${o.pillar}] ${o.title}: ${o.targetMetric} (Current: ${o.currentProgress}) -> Sub-Agent Directive: ${o.cascadedDirective}`).join("\n")}

TECHNICAL STRATEGIES:
${technicalStrategies.map((t) => `  • [${t.focusArea}] ${t.title} (${t.architectureKey}): ${t.description}`).join("\n")}

CORE VALUES & BEHAVIORAL CODE:
${companyValues.map((v) => `  ${v.number}. ${v.title} (${v.icon})\n     Principle: ${v.principle}\n     Code of Conduct: ${v.behaviorDirective}\n     Linked Recognition Badge: ${v.linkedBadge}`).join("\n\n")}

SUB-AGENT OPERATIONAL COGNITIVE PROTOCOL:
Before executing any tool or finalizing any recommendation, you must verify:
1. [STRATEGIC_FIT]: Which of the ${strategicObjectives.length} Strategic OKRs does this action advance?
2. [VALUES_CHECK]: Does this communication or remediation honor our ${companyValues.length} Core Values?
3. [SAFETY_GATE]: Is this fully compliant with RICA, POPIA, ICASA, and OHS Act safety constraints?
4. [EXECUTION]: Proceed with the lowest-blast-radius action, maintaining full audit traceability.`

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-950/95 px-4 py-3 text-sm text-emerald-200 shadow-2xl backdrop-blur">
          <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Banner */}
      <div className="rounded-xl border border-border bg-card/60 p-5 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-primary/40 bg-primary/10 text-primary">
              <Compass className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-foreground">Culture & Strategy Alignment</h2>
                <Badge variant="outline" className="border-primary/40 text-primary bg-primary/10 text-[10px] font-semibold">
                  Modular & Free-Form
                </Badge>
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-950/30 text-[10px] font-medium">
                  Dynamic Prompt Generation
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Every objective, value, and technical strategy is freely editable. Add custom elements or test free-form queries against the AI Orchestrator below.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs"
              onClick={handleSyncOrchestrator}
              disabled={isSyncing}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isSyncing ? "animate-spin text-primary" : ""}`} />
              {isSyncing ? "Syncing to LLM…" : "Sync to Orchestrator"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs"
              onClick={() => setSurveyModalOpen(true)}
            >
              <Plus className="h-3.5 w-3.5" />
              New Pulse Survey
            </Button>
            <Button
              size="sm"
              variant="default"
              className="gap-1.5 text-xs font-semibold"
              onClick={() => setKudosModalOpen(true)}
            >
              <Award className="h-3.5 w-3.5" />
              Send Peer Kudos
            </Button>
          </div>
        </div>
      </div>

      {/* Sub-Tab Navigation: STRATEGY IN FRONT OF KUDOS BOARD */}
      <div className="flex items-center gap-1.5 border-b border-border pb-2 text-xs overflow-x-auto">
        <button
          type="button"
          onClick={() => setActiveTab("strategy")}
          className={`flex items-center gap-1.5 rounded-md px-3.5 py-1.5 font-medium transition-colors ${
            activeTab === "strategy"
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
          }`}
        >
          <Compass className="h-3.5 w-3.5" />
          <span>1. Company Strategy, Vision & Values</span>
          <span className="ml-1 inline-flex items-center rounded-full bg-emerald-500/20 px-1.5 py-0.2 text-[9px] font-semibold text-emerald-400 border border-emerald-500/30">
            LLM Core Feed
          </span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("kudos")}
          className={`flex items-center gap-1.5 rounded-md px-3.5 py-1.5 font-medium transition-colors ${
            activeTab === "kudos"
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
          }`}
        >
          <Award className="h-3.5 w-3.5" />
          <span>2. Peer Kudos Board ({kudosList.length})</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("service")}
          className={`flex items-center gap-1.5 rounded-md px-3.5 py-1.5 font-medium transition-colors ${
            activeTab === "service"
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
          }`}
        >
          <Gift className="h-3.5 w-3.5" />
          <span>3. Long Service Milestones ({milestones.length})</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("surveys")}
          className={`flex items-center gap-1.5 rounded-md px-3.5 py-1.5 font-medium transition-colors ${
            activeTab === "surveys"
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
          }`}
        >
          <Smile className="h-3.5 w-3.5" />
          <span>4. Alignment & Pulse Surveys ({surveys.length})</span>
        </button>
      </div>

      {/* ── TAB 1: STRATEGY & VALUES SECTION ──────────────────────────────── */}
      {activeTab === "strategy" && (
        <div className="space-y-6">
          {/* AI Orchestrator Alignment Feed Card */}
          <Card className="border-border bg-gradient-to-r from-card via-card to-primary/5">
            <CardHeader className="pb-3 border-b border-border/60">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/40 bg-primary/10 text-primary">
                    <Bot className="h-5 w-5" />
                  </div>
                  <div>
                    <CardTitle className="text-sm font-semibold flex items-center gap-2">
                      <span>AI Orchestrator Alignment Feed</span>
                      <span className="flex items-center gap-1 text-[11px] font-normal text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded-full border border-emerald-500/30">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        Active in LLM System Prompt
                      </span>
                    </CardTitle>
                    <CardDescription className="text-xs">
                      All strategic objectives, core values, and non-negotiables compiled dynamically into the foundation prompt for all OmniDome sub-agents.
                    </CardDescription>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 gap-1.5 text-xs"
                    onClick={() => setViewPromptModalOpen(true)}
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Inspect Compiled Prompt
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 gap-1.5 text-xs"
                    onClick={() => setEditStrategyModalOpen(true)}
                  >
                    <Edit3 className="h-3.5 w-3.5" />
                    Edit Mission & Vision
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-4">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5 text-xs">
                <div className="rounded-lg border border-border bg-muted/20 p-2.5">
                  <span className="text-[10px] text-muted-foreground uppercase font-medium">Orchestrator Engine</span>
                  <p className="font-semibold text-foreground mt-0.5">Claude 3.5 Sonnet / Llama 3.3</p>
                  <span className="text-[10px] text-emerald-400">Multi-Model Routing</span>
                </div>
                <div className="rounded-lg border border-border bg-muted/20 p-2.5">
                  <span className="text-[10px] text-muted-foreground uppercase font-medium">Active Sub-Agents</span>
                  <p className="font-semibold text-foreground mt-0.5">7 Sub-Agents Governed</p>
                  <span className="text-[10px] text-primary">Insight, Staff, Churn, Support...</span>
                </div>
                <div className="rounded-lg border border-border bg-muted/20 p-2.5">
                  <span className="text-[10px] text-muted-foreground uppercase font-medium">Charter Token Weight</span>
                  <p className="font-semibold text-foreground mt-0.5">{Math.round(compiledSystemPrompt.length / 4)} Tokens</p>
                  <span className="text-[10px] text-muted-foreground">Injected dynamically</span>
                </div>
                <div className="rounded-lg border border-border bg-muted/20 p-2.5">
                  <span className="text-[10px] text-muted-foreground uppercase font-medium">Active OKRs & Values</span>
                  <p className="font-semibold text-emerald-400 mt-0.5">{strategicObjectives.length} OKRs • {companyValues.length} Values</p>
                  <span className="text-[10px] text-muted-foreground">Fully customizable</span>
                </div>
                <div className="rounded-lg border border-border bg-muted/20 p-2.5">
                  <span className="text-[10px] text-muted-foreground uppercase font-medium">Last Synchronized</span>
                  <p className="font-semibold text-foreground mt-0.5">{lastSyncedTime}</p>
                  <span className="text-[10px] text-emerald-400">Live in Orchestrator</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* ── FREE-TEST PLAYGROUND WORKBENCH ─────────────────────────────── */}
          <Card className="border-primary/40 bg-card/90 shadow-md">
            <CardHeader className="pb-3 border-b border-border/70">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary/40 bg-primary/10 text-primary">
                    <Terminal className="h-4 w-4" />
                  </div>
                  <div>
                    <CardTitle className="text-sm font-bold text-foreground flex items-center gap-2">
                      <span>Free-Form AI Strategy Testing Workbench</span>
                      <Badge variant="outline" className="border-primary/40 text-primary text-[10px]">
                        Free Test Anything
                      </Badge>
                    </CardTitle>
                    <CardDescription className="text-xs">
                      Type any prompt, subscriber situation, field crisis, or strategic question to see how the AI Orchestrator evaluates it against your current elements.
                    </CardDescription>
                  </div>
                </div>

                <div className="flex items-center gap-2 text-xs">
                  <span className="text-muted-foreground">Target Agent:</span>
                  <select
                    value={selectedAgentTarget}
                    onChange={(e) => setSelectedAgentTarget(e.target.value)}
                    className="h-8 rounded-md border border-border bg-background px-2.5 text-xs text-foreground"
                  >
                    <option value="all">Orchestrator Global Consensus (All Agents)</option>
                    <option value="insight">InsightBot (Executive Strategy)</option>
                    <option value="support">SupportBot (NOC SLA & Outages)</option>
                    <option value="churn">ChurnGuard (Retention & NPS)</option>
                    <option value="staff">StaffBot (Wellness & Rosters)</option>
                    <option value="provision">ProvisionBot (RICA & Field Drops)</option>
                  </select>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              {/* Free-Text Prompt Input */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <label className="font-semibold text-foreground flex items-center gap-1.5">
                    <Wand2 className="h-3.5 w-3.5 text-primary" /> Enter Your Custom Query or Scenario:
                  </label>
                  <span className="text-[11px] text-muted-foreground">Free text — no fixed format required</span>
                </div>
                <Textarea
                  value={freeTestQuery}
                  onChange={(e) => setFreeTestQuery(e.target.value)}
                  rows={3}
                  className="text-xs font-sans"
                  placeholder="e.g. A customer in Soweto has had fiber downtime for 3 hours during Stage 6 loadshedding, and our field van is stuck in traffic. How does OmniDome handle this?"
                />

                {/* Quick-Insert Scenario Pills */}
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  <span className="text-[11px] text-muted-foreground font-medium mr-1">Quick Scenarios:</span>
                  <button
                    type="button"
                    onClick={() =>
                      handleQuickInsert(
                        "Midrand POP lost power during loadshedding Stage 6 and third-party cut Route 4 backhaul."
                      )
                    }
                    className="rounded-full border border-border/80 bg-muted/30 px-2.5 py-1 text-[10px] text-muted-foreground hover:text-foreground hover:bg-muted"
                  >
                    ⚡ POP Blackout & Core Fiber Cut
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      handleQuickInsert(
                        "Subscriber in Tembisa has waited 4 days for fiber drop due to unclear RICA address verification."
                      )
                    }
                    className="rounded-full border border-border/80 bg-muted/30 px-2.5 py-1 text-[10px] text-muted-foreground hover:text-foreground hover:bg-muted"
                  >
                    🏠 Tembisa 4-Day Installation Delay
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      handleQuickInsert(
                        "Severe lightning storm with 75 km/h wind gusts starts while technician is in cherry picker."
                      )
                    }
                    className="rounded-full border border-border/80 bg-muted/30 px-2.5 py-1 text-[10px] text-muted-foreground hover:text-foreground hover:bg-muted"
                  >
                    ⛈️ Severe Lightning Storm on Pole
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      handleQuickInsert(
                        "NOC engineer logged 60 consecutive on-call hours this week with 14 night-time alerts."
                      )
                    }
                    className="rounded-full border border-border/80 bg-muted/30 px-2.5 py-1 text-[10px] text-muted-foreground hover:text-foreground hover:bg-muted"
                  >
                    ☕ NOC Standby Shift Fatigue Alert
                  </button>
                </div>
              </div>

              {/* Action Button */}
              <div className="flex items-center justify-between border-t border-border/60 pt-3">
                <span className="text-[11px] text-muted-foreground">
                  Evaluates against {strategicObjectives.length} active OKRs, {companyValues.length} values, and {decisionHierarchy.length} non-negotiable rules.
                </span>
                <Button
                  size="sm"
                  variant="default"
                  onClick={handleRunFreeTest}
                  disabled={isEvaluatingFreeTest}
                  className="gap-2 text-xs font-semibold px-4"
                >
                  <Play className={`h-3.5 w-3.5 fill-current ${isEvaluatingFreeTest ? "animate-spin" : ""}`} />
                  {isEvaluatingFreeTest ? "Evaluating with Orchestrator…" : "Run Alignment Evaluation"}
                </Button>
              </div>

              {/* Free-Test Evaluation Output Display */}
              {freeTestResult && (
                <div className="rounded-xl border border-primary/30 bg-muted/20 p-4 space-y-4 animate-in fade-in duration-300">
                  <div className="flex items-center justify-between border-b border-border/60 pb-2">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                      <span className="text-xs font-bold text-foreground">Orchestrator Deliberation Results</span>
                      <span className="text-[10px] text-muted-foreground font-mono">({freeTestResult.evaluatedAt})</span>
                    </div>
                    <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-950/20 text-[10px]">
                      Policy Compliant
                    </Badge>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-xs">
                    {/* Step 1: OKR Match */}
                    <div className="rounded-lg border border-border bg-card p-3 space-y-1.5">
                      <span className="text-[10px] font-bold uppercase text-primary block flex items-center gap-1">
                        <Target className="h-3 w-3" /> 1. Strategic OKR Alignment
                      </span>
                      {freeTestResult.matchedObjectives.map((m, idx) => (
                        <div key={idx} className="space-y-0.5">
                          <p className="font-semibold text-foreground text-xs">{m.title}</p>
                          <Badge variant="outline" className="text-[9px] border-border text-muted-foreground">
                            {m.pillar}
                          </Badge>
                          <p className="text-[10px] text-muted-foreground leading-tight pt-1">{m.reason}</p>
                        </div>
                      ))}
                    </div>

                    {/* Step 2: Values Check */}
                    <div className="rounded-lg border border-border bg-card p-3 space-y-1.5">
                      <span className="text-[10px] font-bold uppercase text-primary block flex items-center gap-1">
                        <Shield className="h-3 w-3" /> 2. Governing Core Values
                      </span>
                      {freeTestResult.governingValues.map((v, idx) => (
                        <div key={idx} className="space-y-0.5">
                          <p className="font-semibold text-foreground text-xs flex items-center gap-1">
                            <span>{v.icon}</span> {v.title}
                          </p>
                          <p className="text-[10px] text-muted-foreground leading-tight pt-1">"{v.directive}"</p>
                        </div>
                      ))}
                    </div>

                    {/* Step 3: Statutory & Safety Gate */}
                    <div className="rounded-lg border border-border bg-card p-3 space-y-1.5">
                      <span className="text-[10px] font-bold uppercase text-amber-400 block flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3" /> 3. Non-Negotiable Safety Gate
                      </span>
                      {freeTestResult.safetyGuards.map((g, idx) => (
                        <p key={idx} className="text-[11px] text-foreground font-medium leading-tight">
                          • {g}
                        </p>
                      ))}
                    </div>

                    {/* Step 4: Autonomous Agent Action */}
                    <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/10 p-3 space-y-1.5">
                      <span className="text-[10px] font-bold uppercase text-emerald-400 block flex items-center gap-1">
                        <Bot className="h-3 w-3" /> 4. Orchestrator Tool Execution
                      </span>
                      <p className="text-[11px] text-foreground font-medium leading-relaxed">
                        {freeTestResult.autonomousAction}
                      </p>
                    </div>
                  </div>

                  {/* Cultural Reinforcement / Kudos Trigger */}
                  <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                    <div className="flex items-center gap-2">
                      <Award className="h-4 w-4 text-primary shrink-0" />
                      <div>
                        <span className="font-bold text-foreground">Culture Bridge: Automated Recognition Recommendation</span>
                        <p className="text-muted-foreground text-[11px]">
                          Reward for upholding company strategy: <span className="text-primary font-semibold">{freeTestResult.suggestedKudos.badge}</span> to {freeTestResult.suggestedKudos.recipient}
                        </p>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs gap-1 border-primary/40 text-primary shrink-0"
                      onClick={() => {
                        setSelectedRecipient(freeTestResult.suggestedKudos.recipient)
                        setKudosBadge(freeTestResult.suggestedKudos.badge)
                        setKudosText(freeTestResult.suggestedKudos.message)
                        setKudosModalOpen(true)
                      }}
                    >
                      Post This Kudos
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Philosophy Bridge: Strategy & Culture Live Together */}
          <div className="rounded-xl border border-primary/30 bg-primary/5 p-4 sm:p-5 relative overflow-hidden">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="space-y-1.5 max-w-3xl">
                <div className="flex items-center gap-2">
                  <Lightbulb className="h-4 w-4 text-primary" />
                  <span className="text-xs font-bold uppercase tracking-wider text-primary">
                    Core Philosophy: Culture & Strategy Live Together
                  </span>
                </div>
                <p className="text-sm font-medium text-foreground italic leading-relaxed">
                  "They say 'culture eats strategy for breakfast' — but at OmniDome, they live together as an integrated engine.
                  Strategy defines the vector of what the company is trying to achieve; Culture provides the daily human behaviors,
                  empathy, and peer recognition required to get there."
                </p>
                <p className="text-xs text-muted-foreground">
                  Our Kudos Board reinforces our core values, our Long Service awards celebrate dedication to the mission, and
                  our Pulse Surveys serve as our ongoing dipstick to ensure our people and AI sub-agents remain in lockstep.
                </p>
              </div>

              <div className="flex shrink-0 flex-col gap-1.5 rounded-lg border border-border bg-card/90 p-3 text-xs w-full md:w-64">
                <span className="font-semibold text-foreground flex items-center gap-1.5">
                  <Workflow className="h-3.5 w-3.5 text-primary" /> Strategy-to-Culture Loop
                </span>
                <div className="flex items-center justify-between text-muted-foreground text-[11px] pt-1">
                  <span>Strategy & OKRs</span>
                  <ArrowRight className="h-3 w-3 text-primary" />
                  <span className="text-foreground">AI Orchestrator</span>
                </div>
                <div className="flex items-center justify-between text-muted-foreground text-[11px]">
                  <span>AI Sub-Agents</span>
                  <ArrowRight className="h-3 w-3 text-primary" />
                  <span className="text-foreground">Staff Actions</span>
                </div>
                <div className="flex items-center justify-between text-muted-foreground text-[11px]">
                  <span>Peer Kudos & Values</span>
                  <ArrowRight className="h-3 w-3 text-emerald-400" />
                  <span className="text-emerald-400 font-semibold">Goal Attainment</span>
                </div>
              </div>
            </div>
          </div>

          {/* Mission & Vision Cards */}
          <div className="grid gap-4 md:grid-cols-2">
            <Card className="border-border">
              <CardHeader className="pb-3 border-b border-border/60">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Target className="h-4 w-4 text-cyan-400" />
                    <CardTitle className="text-sm font-bold text-foreground uppercase tracking-wide">Company Mission</CardTitle>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-2 text-[10px] text-muted-foreground hover:text-foreground"
                    onClick={() => setEditStrategyModalOpen(true)}
                  >
                    <Edit3 className="h-3 w-3 mr-1" /> Edit
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="p-4 space-y-2 text-xs">
                <p className="text-sm font-medium text-foreground leading-relaxed">
                  "{companyMission}"
                </p>
                <div className="border-t border-border/60 pt-2 flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>Core Focus: Democratizing Digital Access</span>
                  <span className="text-cyan-400 font-medium">Gigabit FTTH + Solar Fixed Wireless</span>
                </div>
              </CardContent>
            </Card>

            <Card className="border-border">
              <CardHeader className="pb-3 border-b border-border/60">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-primary" />
                    <CardTitle className="text-sm font-bold text-foreground uppercase tracking-wide">2030 Corporate Vision</CardTitle>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-2 text-[10px] text-muted-foreground hover:text-foreground"
                    onClick={() => setEditStrategyModalOpen(true)}
                  >
                    <Edit3 className="h-3 w-3 mr-1" /> Edit
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="p-4 space-y-2 text-xs">
                <p className="text-sm font-medium text-foreground leading-relaxed">
                  "{companyVision}"
                </p>
                <div className="border-t border-border/60 pt-2 flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>Target Horizon: 2030</span>
                  <span className="text-primary font-medium">1,000,000 Connected Premises (SADC)</span>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Decision-Making Hierarchy & Non-Negotiable Trade-Offs */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                  <Shield className="h-4 w-4 text-amber-400" /> Decision-Making Hierarchy & Non-Negotiable Trade-Offs
                </h3>
                <p className="text-xs text-muted-foreground">
                  The explicit tie-breaking rules that govern both human staff decisions and AI sub-agent reasoning loops.
                </p>
              </div>
              <Badge variant="outline" className="border-amber-500/40 text-amber-400 text-[10px]">
                5-Tier Priority Rules
              </Badge>
            </div>

            <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-5">
              {decisionHierarchy.map((rule) => (
                <div
                  key={rule.level}
                  className="rounded-lg border border-border bg-card p-3 space-y-1.5 flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-mono text-muted-foreground">Priority {rule.level}</span>
                      <Badge variant="outline" className={`text-[9px] ${rule.color}`}>
                        Tier {rule.level}
                      </Badge>
                    </div>
                    <h4 className="text-xs font-bold text-foreground">{rule.name}</h4>
                    <p className="text-[10px] text-muted-foreground mt-0.5">{rule.scope}</p>
                  </div>
                  <div className="border-t border-border/50 pt-1.5 text-[10px] text-foreground font-medium leading-tight">
                    {rule.rule}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Strategic Objectives (OKRs) Section with Full CRUD */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                  <TrendingUp className="h-4 w-4 text-emerald-400" /> Company Strategic Objectives (OKRs)
                </h3>
                <p className="text-xs text-muted-foreground">
                  Measurable quarterly milestones fed directly to the Orchestrator. Add, edit, or customize any objective freely.
                </p>
              </div>
              <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7" onClick={openNewOkrModal}>
                <Plus className="h-3 w-3" /> Add Custom Objective
              </Button>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {strategicObjectives.map((obj) => (
                <Card key={obj.id} className="border-border flex flex-col justify-between">
                  <CardHeader className="pb-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono text-muted-foreground">{obj.id}</span>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => openEditOkrModal(obj)}
                          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted"
                          title="Edit Objective"
                        >
                          <Edit3 className="h-3 w-3" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteOkr(obj.id)}
                          className="p-1 rounded text-muted-foreground hover:text-red-400 hover:bg-muted"
                          title="Delete Objective"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                        <Badge
                          variant="outline"
                          className={
                            obj.status === "On Track"
                              ? "border-emerald-500/40 text-emerald-400"
                              : "border-amber-500/40 text-amber-400"
                          }
                        >
                          {obj.status}
                        </Badge>
                      </div>
                    </div>
                    <CardTitle className="text-xs font-bold text-foreground mt-1">{obj.title}</CardTitle>
                    <span className="text-[10px] text-primary font-medium">{obj.pillar}</span>
                  </CardHeader>
                  <CardContent className="space-y-3 pt-0 text-xs">
                    <div>
                      <span className="text-[10px] text-muted-foreground block">Key Target</span>
                      <p className="font-semibold text-foreground text-xs mt-0.5">{obj.targetMetric}</p>
                    </div>

                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="text-muted-foreground">Current Progress</span>
                        <span className="font-bold text-foreground">{obj.currentProgress}</span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full bg-emerald-500 rounded-full"
                          style={{ width: `${Math.min(100, obj.progressPercent)}%` }}
                        />
                      </div>
                    </div>

                    <div className="rounded border border-border/60 bg-muted/20 p-2 text-[11px]">
                      <span className="text-[9px] font-semibold text-primary uppercase block">Sub-Agent Cascaded Directive</span>
                      <p className="text-muted-foreground text-[10px] mt-0.5 leading-tight">{obj.cascadedDirective}</p>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>

          {/* Technical Strategies (ISP Architecture & Engineering) */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                  <Cpu className="h-4 w-4 text-cyan-400" /> Technical Strategies & Network Architecture
                </h3>
                <p className="text-xs text-muted-foreground">
                  Underlying engineering paradigms that ensure uptime, scalability, and load-shedding resilience.
                </p>
              </div>
              <Badge variant="outline" className="border-cyan-500/40 text-cyan-400 text-[10px]">
                Engineering Roadmap
              </Badge>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {technicalStrategies.map((tech) => (
                <div
                  key={tech.id}
                  className="rounded-lg border border-border bg-card p-4 space-y-2 flex flex-col justify-between"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono text-cyan-400">{tech.id}</span>
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[9px] font-mono text-muted-foreground">
                        {tech.architectureKey}
                      </span>
                    </div>
                    <h4 className="text-xs font-bold text-foreground">{tech.title}</h4>
                    <p className="text-xs text-muted-foreground leading-relaxed">{tech.description}</p>
                  </div>
                  <div className="border-t border-border/50 pt-2 text-[10px] text-muted-foreground flex items-center justify-between">
                    <span>Focus: {tech.focusArea}</span>
                    <CheckCircle className="h-3 w-3 text-emerald-400" />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* The 5 Core Values & Behavioral Code of Conduct with CRUD */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                  <Shield className="h-4 w-4 text-primary" /> Core Company Values & Behavioral Code
                </h3>
                <p className="text-xs text-muted-foreground">
                  The principles guiding how every OmniDome employee conducts themselves. Add or edit any value.
                </p>
              </div>
              <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7" onClick={openNewValueModal}>
                <Plus className="h-3 w-3" /> Add Custom Value
              </Button>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {companyValues.map((val) => (
                <Card key={val.id} className="border-border flex flex-col justify-between">
                  <CardHeader className="pb-2.5 border-b border-border/50">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-xl">{val.icon}</span>
                        <div>
                          <CardTitle className="text-xs font-bold text-foreground">
                            Value {val.number}: {val.title}
                          </CardTitle>
                          <span className="text-[10px] text-muted-foreground">OmniDome Cultural Pillar</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => openEditValueModal(val)}
                          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted"
                          title="Edit Value"
                        >
                          <Edit3 className="h-3 w-3" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteValue(val.id)}
                          className="p-1 rounded text-muted-foreground hover:text-red-400 hover:bg-muted"
                          title="Delete Value"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                        <Badge variant="outline" className="border-primary/40 text-primary text-[10px]">
                          {val.linkedBadge}
                        </Badge>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="p-4 space-y-3 text-xs">
                    <div>
                      <span className="text-[10px] uppercase font-bold text-primary tracking-wider block">Foundational Principle</span>
                      <p className="text-foreground text-xs mt-0.5 leading-relaxed font-medium">"{val.principle}"</p>
                    </div>

                    <div className="rounded-lg border border-border/80 bg-muted/30 p-2.5 space-y-1">
                      <span className="text-[10px] uppercase font-semibold text-muted-foreground flex items-center gap-1">
                        <Check className="h-3 w-3 text-emerald-400" /> How Employees Handle Themselves
                      </span>
                      <p className="text-muted-foreground text-[11px] leading-relaxed">{val.behaviorDirective}</p>
                    </div>

                    <div className="flex items-center justify-between text-[11px] pt-1 border-t border-border/40">
                      <span className="text-muted-foreground">Recognition Link:</span>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedRecipient(employees[0]?.full_name || "Musa Sithole")
                          setKudosBadge(val.linkedBadge)
                          setKudosModalOpen(true)
                        }}
                        className="text-primary hover:underline font-semibold flex items-center gap-1"
                      >
                        Reward this Value <ArrowRight className="h-3 w-3" />
                      </button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>

          {/* Sub-Agent Cascading Objectives Matrix */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                  <Workflow className="h-4 w-4 text-primary" /> Sub-Agent Objectives Cascading Matrix
                </h3>
                <p className="text-xs text-muted-foreground">
                  How the AI Orchestrator transmits our corporate strategy into operational parameters for each autonomous sub-agent.
                </p>
              </div>
              <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px]">
                Real-Time LLM Binding
              </Badge>
            </div>

            <Card className="border-border">
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                        <th className="py-2.5 px-4 font-medium">Sub-Agent</th>
                        <th className="py-2.5 px-4 font-medium">Assigned Operational Domain</th>
                        <th className="py-2.5 px-4 font-medium">Inherited Corporate OKR</th>
                        <th className="py-2.5 px-4 font-medium">Governing Core Value</th>
                        <th className="py-2.5 px-4 font-medium text-right">Alignment Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {subAgentMappings.map((agent) => (
                        <tr key={agent.agentName} className="hover:bg-muted/30">
                          <td className="py-3 px-4 font-semibold text-foreground flex items-center gap-2">
                            <Bot className="h-3.5 w-3.5 text-primary" />
                            {agent.agentName}
                          </td>
                          <td className="py-3 px-4 text-muted-foreground">{agent.role}</td>
                          <td className="py-3 px-4 text-foreground font-medium">{agent.inheritedObjective}</td>
                          <td className="py-3 px-4">
                            <Badge variant="outline" className="border-border text-foreground">
                              {agent.governingValue}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-950/20">
                              ● {agent.alignmentStatus}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* ── TAB 2: Kudos Board ────────────────────────────────────────── */}
      {activeTab === "kudos" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between bg-muted/20 p-3 rounded-lg border border-border text-xs">
            <span className="text-muted-foreground">
              Peer recognition wall reinforcing our Core Values. Tag a colleague when they champion reliability, precision, or empathy.
            </span>
            <Button size="sm" variant="default" className="text-xs h-7 gap-1" onClick={() => setKudosModalOpen(true)}>
              <Award className="h-3 w-3" /> Post Kudos
            </Button>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {kudosList.map((kudo) => (
              <Card key={kudo.id} className="border-border flex flex-col justify-between">
                <CardHeader className="pb-3 border-b border-border/60">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="border-primary/40 text-primary">
                      {kudo.badge}
                    </Badge>
                    <span className="text-[11px] text-muted-foreground">{kudo.date}</span>
                  </div>
                  <CardTitle className="text-sm font-semibold pt-1">
                    For: <span className="text-foreground">{kudo.toName}</span>
                  </CardTitle>
                  <CardDescription className="text-xs">From: {kudo.fromName}</CardDescription>
                </CardHeader>
                <CardContent className="p-4 space-y-3 text-xs">
                  <p className="text-muted-foreground italic">"{kudo.message}"</p>
                  <div className="flex items-center justify-between border-t border-border/50 pt-2 text-muted-foreground">
                    <span className="flex items-center gap-1 text-primary">
                      <Heart className="h-3.5 w-3.5 fill-primary" /> {kudo.likes} Applauds
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setKudosList((prev) =>
                          prev.map((k) => (k.id === kudo.id ? { ...k, likes: k.likes + 1 } : k))
                        )
                      }}
                      className="text-xs text-primary hover:underline font-medium"
                    >
                      + Applaud
                    </button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* ── TAB 3: Long Service Milestones ────────────────────────────── */}
      {activeTab === "service" && (
        <Card className="border-border">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base flex items-center gap-2">
              <Award className="h-4 w-4 text-amber-400" /> Long Service Awards & Loyalty Recognition
            </CardTitle>
            <CardDescription className="text-xs">
              Celebrating telecom loyalty milestones (3-Year, 5-Year, 10-Year) with official company awards. Sustaining strategy through long-term tenure.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                    <th className="py-2.5 px-4 font-medium">Employee</th>
                    <th className="py-2.5 px-4 font-medium">Department</th>
                    <th className="py-2.5 px-4 font-medium">Hire Date</th>
                    <th className="py-2.5 px-4 font-medium">Tenure</th>
                    <th className="py-2.5 px-4 font-medium">Award Milestone</th>
                    <th className="py-2.5 px-4 font-medium text-right">Recognition Benefit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {milestones.map((m) => (
                    <tr key={m.employeeName} className="hover:bg-muted/30">
                      <td className="py-3 px-4 font-semibold text-foreground">{m.employeeName}</td>
                      <td className="py-3 px-4 text-muted-foreground">{m.department}</td>
                      <td className="py-3 px-4 text-muted-foreground font-mono">{m.hireDate}</td>
                      <td className="py-3 px-4 font-bold text-foreground">{m.yearsOfService} Years</td>
                      <td className="py-3 px-4">
                        <Badge variant="outline" className="border-amber-500/40 text-amber-400">
                          {m.tier}
                        </Badge>
                      </td>
                      <td className="py-3 px-4 text-right font-medium text-emerald-400">
                        {m.award}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── TAB 4: Pulse Surveys ──────────────────────────────────────── */}
      {activeTab === "surveys" && (
        <div className="space-y-4">
          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <CardTitle className="text-base flex items-center gap-2">
                <Smile className="h-4 w-4 text-cyan-400" /> Employee Pulse Surveys (Strategic Alignment Dipstick)
              </CardTitle>
              <CardDescription className="text-xs">
                Continuous operational dipstick measuring whether staff feel supported, aligned with corporate OKRs, and equipped to perform.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                      <th className="py-2.5 px-4 font-medium">Survey Title</th>
                      <th className="py-2.5 px-4 font-medium">Target Department</th>
                      <th className="py-2.5 px-4 font-medium">Questions</th>
                      <th className="py-2.5 px-4 font-medium">Participation Rate</th>
                      <th className="py-2.5 px-4 font-medium">Published Date</th>
                      <th className="py-2.5 px-4 font-medium text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {surveys.map((s) => (
                      <tr key={s.id} className="hover:bg-muted/30">
                        <td className="py-3 px-4 font-semibold text-foreground">{s.title}</td>
                        <td className="py-3 px-4 text-muted-foreground">{s.department}</td>
                        <td className="py-3 px-4 text-muted-foreground font-mono">{s.questionsCount} Items</td>
                        <td className="py-3 px-4 font-bold text-emerald-400">{s.responseRate}</td>
                        <td className="py-3 px-4 text-muted-foreground font-mono">{s.createdDate}</td>
                        <td className="py-3 px-4 text-right">
                          <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
                            {s.status}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── INSPECT LLM SYSTEM PROMPT INJECTION MODAL ────────────────── */}
      {viewPromptModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-2xl border-border shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <Bot className="h-5 w-5 text-primary" />
                <div>
                  <CardTitle className="text-base font-bold">Compiled LLM Orchestrator System Prompt</CardTitle>
                  <CardDescription className="text-xs">
                    This exact strategic charter and cognitive deliberation protocol are dynamically compiled and injected into all 7 sub-agents.
                  </CardDescription>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setViewPromptModalOpen(false)}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <CardContent className="p-4 space-y-3 text-xs">
              <div className="flex items-center justify-between text-[11px] text-muted-foreground border-b border-border/50 pb-2">
                <span>Prompt Identifier: <code className="text-primary font-mono">OMNIDOME_DYNAMIC_CHARTER</code></span>
                <span>Active Tokens: <code className="text-emerald-400 font-mono">~{Math.round(compiledSystemPrompt.length / 4)} tokens</code></span>
              </div>
              <pre className="max-h-96 overflow-y-auto rounded-lg border border-border bg-black/60 p-3 text-[11px] font-mono text-zinc-300 whitespace-pre-wrap leading-relaxed">
                {compiledSystemPrompt}
              </pre>
            </CardContent>
            <div className="flex items-center justify-between border-t border-border p-3 bg-muted/10">
              <span className="text-[11px] text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="h-3.5 w-3.5" /> Synchronized with live orchestrator runtime
              </span>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    navigator.clipboard.writeText(compiledSystemPrompt)
                    setToastMessage("System prompt copied to clipboard!")
                    setTimeout(() => setToastMessage(null), 2500)
                  }}
                  className="gap-1.5 text-xs"
                >
                  <Copy className="h-3.5 w-3.5" /> Copy Prompt
                </Button>
                <Button size="sm" variant="default" onClick={() => setViewPromptModalOpen(false)}>
                  Done
                </Button>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* ── EDIT MISSION & VISION MODAL ──────────────────────────────── */}
      {editStrategyModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-xl border-border shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <Compass className="h-5 w-5 text-primary" />
                <div>
                  <CardTitle className="text-base font-bold">Edit Corporate Mission & Vision</CardTitle>
                  <CardDescription className="text-xs">
                    Edits immediately recompile and re-feed to the AI Orchestrator loop.
                  </CardDescription>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setEditStrategyModalOpen(false)}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleSaveStrategy}>
              <CardContent className="space-y-4 pt-4 text-xs">
                <div className="space-y-1.5">
                  <label className="font-semibold text-foreground">Company Mission</label>
                  <Textarea
                    required
                    value={editMission}
                    onChange={(e) => setEditMission(e.target.value)}
                    rows={3}
                    className="text-xs"
                    placeholder="Enter company mission..."
                  />
                  <p className="text-[10px] text-muted-foreground">What OmniDome solves for South African communities daily.</p>
                </div>

                <div className="space-y-1.5">
                  <label className="font-semibold text-foreground">2030 Corporate Vision</label>
                  <Textarea
                    required
                    value={editVision}
                    onChange={(e) => setEditVision(e.target.value)}
                    rows={3}
                    className="text-xs"
                    placeholder="Enter long-term vision..."
                  />
                  <p className="text-[10px] text-muted-foreground">The 2030 autonomous telecommunications milestone.</p>
                </div>
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setEditStrategyModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default" className="gap-1.5">
                  <RefreshCw className="h-3.5 w-3.5" /> Save & Re-Feed to Orchestrator
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ── ADD / EDIT STRATEGIC OBJECTIVE (OKR) MODAL ────────────────── */}
      {okrModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-lg border-border shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <Target className="h-5 w-5 text-emerald-400" />
                <div>
                  <CardTitle className="text-base font-bold">
                    {editingOkr ? `Edit Objective: ${editingOkr.id}` : "Add New Strategic Objective (OKR)"}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Define measurable targets and specify how AI sub-agents must align their actions.
                  </CardDescription>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setOkrModalOpen(false)}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleSaveOkr}>
              <CardContent className="space-y-3 pt-4 text-xs">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="font-semibold text-foreground">Strategic Pillar *</label>
                    <Input
                      required
                      placeholder="e.g. Infrastructure Reliability"
                      value={okrPillar}
                      onChange={(e) => setOkrPillar(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="font-semibold text-foreground">Objective Title *</label>
                    <Input
                      required
                      placeholder="e.g. 99.995% Uptime SLA"
                      value={okrTitle}
                      onChange={(e) => setOkrTitle(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="font-semibold text-foreground">Target Metric *</label>
                    <Input
                      required
                      placeholder="e.g. 99.995% Availability across Metro POPs"
                      value={okrMetric}
                      onChange={(e) => setOkrMetric(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="font-semibold text-foreground">Current Progress Description</label>
                    <Input
                      placeholder="e.g. 99.98% Active SLA"
                      value={okrProgress}
                      onChange={(e) => setOkrProgress(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <label className="font-semibold text-foreground">Completion Percentage: {okrPercent}%</label>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={100}
                    value={okrPercent}
                    onChange={(e) => setOkrPercent(Number(e.target.value))}
                    className="w-full accent-primary h-1.5 cursor-pointer"
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-semibold text-foreground">Cascaded Sub-Agent Directive *</label>
                  <Textarea
                    required
                    placeholder="Describe how sub-agents (SupportBot, ProvisionBot, StaffBot) must react to advance this goal..."
                    value={okrDirective}
                    onChange={(e) => setOkrDirective(e.target.value)}
                    rows={2}
                    className="text-xs"
                  />
                  <p className="text-[10px] text-muted-foreground">Injected directly into sub-agents' task evaluation loop.</p>
                </div>
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setOkrModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default" className="gap-1.5">
                  <Check className="h-3.5 w-3.5" /> Save Objective
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ── ADD / EDIT CORE VALUE MODAL ──────────────────────────────── */}
      {valueModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-lg border-border shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <Shield className="h-5 w-5 text-primary" />
                <div>
                  <CardTitle className="text-base font-bold">
                    {editingValue ? `Edit Core Value ${editingValue.number}` : "Add New Core Value"}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Define the behavioral standard and link it directly to a peer recognition badge.
                  </CardDescription>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setValueModalOpen(false)}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleSaveValue}>
              <CardContent className="space-y-3 pt-4 text-xs">
                <div className="grid grid-cols-4 gap-3">
                  <div className="col-span-1 space-y-1">
                    <label className="font-semibold text-foreground">Icon/Emoji</label>
                    <Input
                      required
                      value={valueIcon}
                      onChange={(e) => setValueIcon(e.target.value)}
                      className="h-8 text-xs text-center text-lg"
                    />
                  </div>
                  <div className="col-span-3 space-y-1">
                    <label className="font-semibold text-foreground">Value Title *</label>
                    <Input
                      required
                      placeholder="e.g. Radical Reliability & Integrity"
                      value={valueTitle}
                      onChange={(e) => setValueTitle(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="font-semibold text-foreground">Foundational Principle *</label>
                  <Textarea
                    required
                    placeholder="The core belief behind this value (e.g. Uptime is sacred. We honor our commitments to subscribers)..."
                    value={valuePrinciple}
                    onChange={(e) => setValuePrinciple(e.target.value)}
                    rows={2}
                    className="text-xs"
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-semibold text-foreground">How Employees Handle Themselves (Behavioral Code) *</label>
                  <Textarea
                    required
                    placeholder="Specific actionable conduct (e.g. Own mistakes immediately without finger-pointing. Keep tickets updated)..."
                    value={valueDirective}
                    onChange={(e) => setValueDirective(e.target.value)}
                    rows={2}
                    className="text-xs"
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-semibold text-foreground">Linked Recognition Badge</label>
                  <select
                    value={valueBadge}
                    onChange={(e) => setValueBadge(e.target.value as PeerBadge)}
                    className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground font-semibold"
                  >
                    <option value="#NetworkHero">#NetworkHero (Uptime & Architecture)</option>
                    <option value="#CustomerObsessed">#CustomerObsessed (Empathy & Support)</option>
                    <option value="#FiberChampion">#FiberChampion (Precision & Splicing)</option>
                    <option value="#SafetyFirst">#SafetyFirst (Zero Incidents & Protocols)</option>
                    <option value="#TeamPlayer">#TeamPlayer (Extreme Ownership & Support)</option>
                  </select>
                </div>
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setValueModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default" className="gap-1.5">
                  <Check className="h-3.5 w-3.5" /> Save Core Value
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ── SEND KUDOS MODAL ─────────────────────────────────────────── */}
      {kudosModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-md border-border shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div>
                <CardTitle className="text-base font-bold">Send Peer Recognition</CardTitle>
                <CardDescription className="text-xs">Celebrate a teammate embodying our Core Values.</CardDescription>
              </div>
              <button type="button" onClick={() => setKudosModalOpen(false)} className="rounded p-1 text-muted-foreground hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleSendKudos}>
              <CardContent className="space-y-4 pt-4 text-xs">
                <div className="space-y-1">
                  <label className="font-medium text-foreground">Select Recipient *</label>
                  <select
                    value={selectedRecipient}
                    onChange={(e) => setSelectedRecipient(e.target.value)}
                    className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    {employees.map((emp) => (
                      <option key={emp.id} value={emp.full_name}>
                        {emp.full_name} ({emp.department})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-foreground">Recognition Badge (Tied to Core Values)</label>
                  <select
                    value={kudosBadge}
                    onChange={(e) => setKudosBadge(e.target.value as PeerBadge)}
                    className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground font-semibold"
                  >
                    <option value="#NetworkHero">#NetworkHero (Value: Radical Reliability & Uptime)</option>
                    <option value="#CustomerObsessed">#CustomerObsessed (Value: Subscriber Empathy)</option>
                    <option value="#FiberChampion">#FiberChampion (Value: Field Splicing Precision)</option>
                    <option value="#SafetyFirst">#SafetyFirst (Value: Zero-Incident Safety)</option>
                    <option value="#TeamPlayer">#TeamPlayer (Value: Extreme Ownership & Shift Cover)</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-foreground">Kudos Message *</label>
                  <Textarea
                    required
                    placeholder="Describe what your teammate accomplished and how it upheld company values..."
                    value={kudosText}
                    onChange={(e) => setKudosText(e.target.value)}
                    rows={4}
                    className="text-xs"
                  />
                </div>
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setKudosModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default">
                  Post Kudos
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ── CREATE PULSE SURVEY MODAL ─────────────────────────────────── */}
      {surveyModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-lg border-border shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div>
                <CardTitle className="text-base font-bold">Create Employee Pulse Survey</CardTitle>
                <CardDescription className="text-xs">Gather dipstick feedback on strategic alignment and workplace health.</CardDescription>
              </div>
              <button type="button" onClick={() => setSurveyModalOpen(false)} className="rounded p-1 text-muted-foreground hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleCreateSurvey}>
              <CardContent className="space-y-4 pt-4 text-xs">
                <div className="space-y-1">
                  <label className="font-medium text-foreground">Survey Title *</label>
                  <Input
                    required
                    placeholder="e.g. Q4 Strategic Alignment & Tooling Dipstick"
                    value={newSurveyTitle}
                    onChange={(e) => setNewSurveyTitle(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-foreground">Target Audience</label>
                  <select
                    value={newSurveyDept}
                    onChange={(e) => setNewSurveyDept(e.target.value)}
                    className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value="All Departments">All Departments (Company-wide)</option>
                    <option value="Field Operations">Field Operations Only</option>
                    <option value="Network Operations">Network Operations (NOC)</option>
                    <option value="Customer Support">Customer Support Agents</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-foreground">Question 1 (Rating 1 - 5: Alignment Dipstick)</label>
                  <Input
                    placeholder="e.g. Do you feel your daily tasks directly contribute to our 99.995% SLA objective?"
                    value={newQuestion1}
                    onChange={(e) => setNewQuestion1(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-foreground">Question 2 (Open Feedback)</label>
                  <Input
                    placeholder="e.g. What is the single biggest barrier stopping you from delivering on our core values?"
                    value={newQuestion2}
                    onChange={(e) => setNewQuestion2(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setSurveyModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default">
                  Publish Pulse Survey
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
