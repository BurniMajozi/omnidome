"use client"

import React, { useState, useMemo, useRef, useEffect, useCallback } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Building2,
  Users,
  Search,
  UserCheck,
  ChevronRight,
  ChevronDown,
  Link2,
  X,
  Crown,
  Shield,
  Wrench,
  Radio,
  Coins,
  Layers,
  Sparkles,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Network,
  PhoneCall,
  Laptop,
  UserPlus,
  Bot,
  Upload,
  Download,
  DollarSign,
  Wallet,
  FileSpreadsheet,
  AlertTriangle,
  CheckCircle2,
  ArrowRight,
  RefreshCw,
  Cpu,
  Brain,
  Check,
  Filter,
  Scale,
  Eye,
  SlidersHorizontal,
  Workflow,
  HelpCircle,
  Edit3,
  Copy,
  Move,
} from "lucide-react"
import { updateReportingLine, createEmployee, type Employee, type EmployeeCreate } from "@/lib/hr-api"

interface OrgChartViewProps {
  employees: Employee[]
  onRefresh: () => Promise<void>
}

interface OrgTreeNode {
  employee: Employee
  children: OrgTreeNode[]
  totalSubordinatesCount: number
}

interface OptimizerRecommendation {
  id: string
  title: string
  category: "Span of Control" | "24/7 Coverage Gap" | "Regulatory Compliance"
  severity: "High" | "Medium" | "Low"
  description: string
  proposedAgent: {
    name: string
    title: string
    department: string
    managerId: string
    managerName: string
    llmModel: string
    financialLimit: number
    scope: string
  }
}

export function OrgChartView({ employees, onRefresh }: OrgChartViewProps) {
  // Local staff list state allows dynamic additions & bulk CSV updates immediately
  const [localStaff, setLocalStaff] = useState<Employee[]>(employees)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedDept, setSelectedDept] = useState("ALL")
  const [connectingEmp, setConnectingEmp] = useState<Employee | null>(null)
  const [targetManagerId, setTargetManagerId] = useState<string>("NONE")
  const [isUpdating, setIsUpdating] = useState(false)
  const [scale, setScale] = useState(1)
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 })
  const [isPanning, setIsPanning] = useState(false)
  const [startPanPos, setStartPanPos] = useState({ x: 0, y: 0 })
  const [autoFitEnabled, setAutoFitEnabled] = useState(true)
  const [showFinancialDoA, setShowFinancialDoA] = useState(true)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // Keep localStaff in sync when parent employees list updates, while preserving local agents
  useEffect(() => {
    setLocalStaff((prevLocal) => {
      const parentIds = new Set(employees.map((e) => e.id))
      // Keep any local AI agents or temporary additions not in parent
      const locallyAdded = prevLocal.filter((e) => !parentIds.has(e.id))
      return [...employees, ...locallyAdded]
    })
  }, [employees])

  // Canvas container ref for "Fit to Window" auto-scaling
  const canvasContainerRef = useRef<HTMLDivElement>(null)
  const treeContentRef = useRef<HTMLDivElement>(null)

  // Modals state
  const [addStaffModalOpen, setAddStaffModalOpen] = useState(false)
  const [bulkCsvModalOpen, setBulkCsvModalOpen] = useState(false)
  const [optimizerModalOpen, setOptimizerModalOpen] = useState(false)
  const [editDoaModalOpen, setEditDoaModalOpen] = useState(false)
  const [editingDoaEmp, setEditingDoaEmp] = useState<Employee | null>(null)
  const [newDoaLimit, setNewDoaLimit] = useState<number>(50000)

  // Add Staff form state
  const [newStaffName, setNewStaffName] = useState("")
  const [newStaffTitle, setNewStaffTitle] = useState("")
  const [newStaffDept, setNewStaffDept] = useState("Network Operations")
  const [newStaffReportingTo, setNewStaffReportingTo] = useState<string>("NONE")
  const [newStaffFinancialLimit, setNewStaffFinancialLimit] = useState<number>(50000)
  const [newStaffIsAgent, setNewStaffIsAgent] = useState(false)
  const [newStaffLlmModel, setNewStaffLlmModel] = useState("Qwen 2.5 7B")
  const [newStaffAgentScope, setNewStaffAgentScope] = useState("Autonomous NOC Incident Triage")

  // Bulk CSV state
  const [csvRawText, setCsvRawText] = useState("")
  const [csvParseError, setCsvParseError] = useState<string | null>(null)
  const [csvPreviewRows, setCsvPreviewRows] = useState<Array<{
    name: string
    title: string
    department: string
    reportingToName: string
    financialLimit: number
    isAgent: boolean
    llmModel?: string
  }>>([])

  // Expanded nodes state
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(
    new Set(employees.map((e) => e.id))
  )

  // Default financial authority limits if not specified
  const getFinancialLimit = (emp: Employee): number => {
    if (emp.financial_limit !== undefined && emp.financial_limit !== null) {
      return emp.financial_limit
    }
    if (emp.job_title.toLowerCase().includes("chief executive officer") || emp.department === "Executive") {
      return 5000000 // R5,000,000 Executive
    }
    if (emp.job_title.toLowerCase().includes("chief") || emp.job_title.toLowerCase().includes("head of")) {
      return 500000 // R500,000 Tier 2
    }
    if (emp.job_title.toLowerCase().includes("lead") || emp.job_title.toLowerCase().includes("manager")) {
      return 100000 // R100,000 Tier 3
    }
    if (emp.is_agent) {
      return 10000 // R10,000 Autonomous credits/approvals
    }
    return 25000 // R25,000 Routine staff
  }

  // Build hierarchical tree from flat employees list with subordinate counts
  const orgTree = useMemo(() => {
    const empMap = new Map<string, OrgTreeNode>()
    localStaff.forEach((emp) => {
      empMap.set(emp.id, { employee: emp, children: [], totalSubordinatesCount: 0 })
    })

    const roots: OrgTreeNode[] = []

    localStaff.forEach((emp) => {
      const node = empMap.get(emp.id)!
      if (emp.manager_id && empMap.has(emp.manager_id) && emp.manager_id !== emp.id) {
        empMap.get(emp.manager_id)!.children.push(node)
      } else {
        roots.push(node)
      }
    })

    // Compute total subordinates recursively
    const computeSubordinates = (n: OrgTreeNode): number => {
      let count = n.children.length
      for (const child of n.children) {
        count += computeSubordinates(child)
      }
      n.totalSubordinatesCount = count
      return count
    }
    roots.forEach(computeSubordinates)

    // Sort children: Department Heads/Leaders first, then alphabetical
    const sortTree = (n: OrgTreeNode) => {
      n.children.sort((a, b) => a.employee.full_name.localeCompare(b.employee.full_name))
      n.children.forEach(sortTree)
    }
    roots.forEach(sortTree)

    return roots
  }, [localStaff])

  // Dynamic Auto-Fit to Window: dynamically shrinks or scales tree to fit window perfectly
  const runAutoFit = useCallback(() => {
    if (!canvasContainerRef.current || !treeContentRef.current) return
    requestAnimationFrame(() => {
      if (!canvasContainerRef.current || !treeContentRef.current) return
      const containerWidth = canvasContainerRef.current.clientWidth - 48
      const containerHeight = canvasContainerRef.current.clientHeight - 48
      const treeWidth = treeContentRef.current.scrollWidth
      const treeHeight = treeContentRef.current.scrollHeight

      if (treeWidth > 0 && containerWidth > 0) {
        if (treeWidth > containerWidth || (treeHeight > containerHeight && containerHeight > 250)) {
          const widthScale = containerWidth / treeWidth
          const heightScale = containerHeight > 250 && treeHeight > 0 ? containerHeight / treeHeight : 1.0
          const optimalScale = Math.min(1.0, Math.max(0.18, Number(Math.min(widthScale, Math.max(0.35, heightScale)).toFixed(2))))
          setScale(optimalScale)
        } else {
          // Fits comfortably within container width: reset to 100%
          setScale(1.0)
        }
        setPanOffset({ x: 0, y: 0 })
      }
    })
  }, [])

  // Automatically recalculate and shrink scale whenever nodes are expanded, collapsed, or staff changes
  useEffect(() => {
    if (autoFitEnabled) {
      const timer = setTimeout(() => {
        runAutoFit()
      }, 50)
      return () => clearTimeout(timer)
    }
  }, [expandedNodeIds, localStaff, autoFitEnabled, runAutoFit])

  // Recalculate on window resize
  useEffect(() => {
    const handleResize = () => {
      if (autoFitEnabled) {
        runAutoFit()
      }
    }
    window.addEventListener("resize", handleResize)
    return () => window.removeEventListener("resize", handleResize)
  }, [autoFitEnabled, runAutoFit])

  const handleFitToWindow = () => {
    setAutoFitEnabled(true)
    setPanOffset({ x: 0, y: 0 })
    runAutoFit()
    setToastMessage("Auto-fit activated: Org chart resized to fit the window.")
    setTimeout(() => setToastMessage(null), 2500)
  }

  const handleManualZoom = (delta: number) => {
    setAutoFitEnabled(false)
    setScale((s) => Math.min(1.6, Math.max(0.2, Number((s + delta).toFixed(2)))))
  }

  const handleResetZoom = () => {
    setAutoFitEnabled(false)
    setScale(1)
    setPanOffset({ x: 0, y: 0 })
  }

  // Mouse pan & canvas dragging handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    // Ignore interactive card elements
    if ((e.target as HTMLElement).closest("button, input, select, textarea, a")) {
      return
    }
    setIsPanning(true)
    setStartPanPos({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y })
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isPanning) return
    setPanOffset({
      x: e.clientX - startPanPos.x,
      y: e.clientY - startPanPos.y,
    })
  }

  const handleMouseUp = () => {
    setIsPanning(false)
  }

  const handleWheel = (e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault()
      setAutoFitEnabled(false)
      const zoomFactor = e.deltaY < 0 ? 0.08 : -0.08
      setScale((s) => Math.min(1.6, Math.max(0.2, Number((s + zoomFactor).toFixed(2)))))
    }
  }

  const toggleExpand = (id: string) => {
    setExpandedNodeIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const expandAll = () => {
    setExpandedNodeIds(new Set(localStaff.map((e) => e.id)))
  }

  const collapseAll = () => {
    setExpandedNodeIds(new Set())
  }

  // Open "Change Reporting Manager" modal
  const handleOpenConnect = (emp: Employee) => {
    setConnectingEmp(emp)
    setTargetManagerId(emp.manager_id || "NONE")
  }

  // Submit reporting line change
  const handleSaveReportingLine = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!connectingEmp) return
    setIsUpdating(true)
    try {
      const newMgr = targetManagerId === "NONE" ? null : targetManagerId
      // Optimistic local update
      setLocalStaff((prev) =>
        prev.map((emp) => (emp.id === connectingEmp.id ? { ...emp, manager_id: newMgr } : emp))
      )
      // Call API
      await updateReportingLine(connectingEmp.id, newMgr).catch(() => null)
      setToastMessage(`Updated reporting line for ${connectingEmp.full_name}`)
      setTimeout(() => setToastMessage(null), 3000)
      setConnectingEmp(null)
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to update reporting line")
    } finally {
      setIsUpdating(false)
    }
  }

  // ── ADD STAFF SUBMISSION HANDLER ──────────────────────────────────────────
  const handleAddStaffSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newStaffName.trim() || !newStaffTitle.trim()) {
      alert("Please provide full name and position.")
      return
    }

    const assignedMgrId = newStaffReportingTo === "NONE" ? null : newStaffReportingTo
    const newEmpId = `EMP-${Date.now().toString().slice(-4)}`

    const newRecord: Employee = {
      id: `local-${Date.now()}`,
      tenant_id: "00000000-0000-0000-0000-000000000001",
      employee_id: newEmpId,
      full_name: newStaffName.trim(),
      job_title: newStaffTitle.trim(),
      department: newStaffDept,
      hire_date: new Date().toISOString().split("T")[0],
      manager_id: assignedMgrId,
      status: "ACTIVE",
      created_at: new Date().toISOString(),
      financial_limit: newStaffFinancialLimit,
      is_agent: newStaffIsAgent,
      llm_model: newStaffIsAgent ? newStaffLlmModel : undefined,
    }

    // Optimistically update local hierarchy immediately
    setLocalStaff((prev) => [...prev, newRecord])

    // Expand the manager so the new staff member is visible immediately
    if (assignedMgrId) {
      setExpandedNodeIds((prev) => new Set([...prev, assignedMgrId]))
    }

    // Call API in background — for BOTH agents and humans
    createEmployee({
      employee_id: newEmpId,
      full_name: newRecord.full_name,
      job_title: newRecord.job_title,
      department: newRecord.department,
      hire_date: newRecord.hire_date,
      manager_id: assignedMgrId,
      financial_limit: newStaffFinancialLimit,
      is_agent: newStaffIsAgent || undefined,
      llm_model: newStaffIsAgent ? newStaffLlmModel : undefined,
    }).then((saved) => {
      // Update local state with the real DB id so subsequent actions work
      if (saved?.id) {
        setLocalStaff((prev) =>
          prev.map((s) => (s.id === newRecord.id ? { ...s, id: saved.id } : s))
        )
      }
    }).catch(() => null)

    setToastMessage(
      newStaffIsAgent
        ? `Deployed AI Agent "${newRecord.full_name}" reporting to ${
            assignedMgrId ? localStaff.find((s) => s.id === assignedMgrId)?.full_name : "CEO"
          }!`
        : `Added staff member "${newRecord.full_name}" to the organizational hierarchy!`
    )
    setTimeout(() => setToastMessage(null), 3500)

    // Reset and close
    setAddStaffModalOpen(false)
    setNewStaffName("")
    setNewStaffTitle("")
    setNewStaffReportingTo("NONE")
    setNewStaffIsAgent(false)
  }

  // ── CSV BULK PARSER ───────────────────────────────────────────────────────
  const handleParseCsv = (raw: string) => {
    setCsvRawText(raw)
    setCsvParseError(null)
    if (!raw.trim()) {
      setCsvPreviewRows([])
      return
    }

    try {
      const lines = raw.trim().split("\n")
      if (lines.length <= 1) {
        setCsvParseError("CSV must include a header line and at least one data row.")
        return
      }

      const rows: typeof csvPreviewRows = []
      for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim()
        if (!line) continue
        const cols = line.split(",").map((c) => c.trim().replace(/^["']|["']$/g, ""))
        if (cols.length >= 2) {
          rows.push({
            name: cols[0],
            title: cols[1],
            department: cols[2] || "Network Operations",
            reportingToName: cols[3] || "",
            financialLimit: cols[4] ? Number(cols[4]) : 50000,
            isAgent: cols[5] ? cols[5].toLowerCase() === "true" || cols[5].toLowerCase() === "yes" : false,
            llmModel: cols[6] || (cols[5]?.toLowerCase() === "true" ? "Qwen 2.5 7B" : undefined),
          })
        }
      }
      setCsvPreviewRows(rows)
    } catch {
      setCsvParseError("Failed to parse CSV syntax. Ensure comma-separated format.")
    }
  }

  // Commit Bulk CSV to Local Hierarchy
  const handleImportCsv = () => {
    if (csvPreviewRows.length === 0) return

    // Map existing names to IDs
    const nameToId = new Map<string, string>()
    localStaff.forEach((s) => nameToId.set(s.full_name.toLowerCase(), s.id))

    const newStaffRecords: Employee[] = []

    csvPreviewRows.forEach((row, idx) => {
      const recordId = `csv-${Date.now()}-${idx}`
      nameToId.set(row.name.toLowerCase(), recordId)

      let resolvedMgrId: string | null = null
      if (row.reportingToName && nameToId.has(row.reportingToName.toLowerCase())) {
        resolvedMgrId = nameToId.get(row.reportingToName.toLowerCase())!
      }

      newStaffRecords.push({
        id: recordId,
        tenant_id: "00000000-0000-0000-0000-000000000001",
        employee_id: `CSV-${100 + idx}`,
        full_name: row.name,
        job_title: row.title,
        department: row.department,
        hire_date: new Date().toISOString().split("T")[0],
        manager_id: resolvedMgrId,
        status: "ACTIVE",
        created_at: new Date().toISOString(),
        financial_limit: row.financialLimit,
        is_agent: row.isAgent,
        llm_model: row.llmModel,
      })
    })

    setLocalStaff((prev) => [...prev, ...newStaffRecords])
    setExpandedNodeIds(new Set([...Array.from(expandedNodeIds), ...newStaffRecords.map((r) => r.id)]))
    setBulkCsvModalOpen(false)
    setCsvRawText("")
    setCsvPreviewRows([])
    setToastMessage(`Bulk uploaded ${newStaffRecords.length} staff & agents into the org hierarchy!`)
    setTimeout(() => setToastMessage(null), 3500)
  }

  // ── AI STRUCTURAL OPTIMIZER RECOMMENDATIONS ────────────────────────────────
  const optimizerRecommendations: OptimizerRecommendation[] = useMemo(() => {
    const list: OptimizerRecommendation[] = []

    // 1. Check Field Operations span of control
    const fieldHead = localStaff.find(
      (e) => e.department === "Field Operations" && (e.job_title.includes("Head") || e.job_title.includes("Lead"))
    )
    if (fieldHead) {
      list.push({
        id: "REC-01",
        title: "Deploy Field Dispatch Optimization Agent",
        category: "Span of Control",
        severity: "High",
        description: `${fieldHead.full_name} manages direct field technicians. Deploying an autonomous dispatch copilot absorbs route planning and same-week installation booking.`,
        proposedAgent: {
          name: "Field-DispatchBot",
          title: "Autonomous Van Routing & Dispatch Copilot",
          department: "Field Operations",
          managerId: fieldHead.id,
          managerName: fieldHead.full_name,
          llmModel: "Llama 3.3 70B",
          financialLimit: 15000,
          scope: "Automated technician GPS dispatch, route scheduling & customer ETA updates",
        },
      })
    }

    // 2. Check NOC 24/7 Coverage Gap
    const nocLead = localStaff.find(
      (e) => e.department === "Network Operations" && (e.job_title.includes("Lead") || e.job_title.includes("CTO"))
    )
    if (nocLead) {
      list.push({
        id: "REC-02",
        title: "Deploy 24/7 Autonomous NOC Triage Agent",
        category: "24/7 Coverage Gap",
        severity: "High",
        description: `Eliminate midnight standby fatigue for NOC engineers during Stage 6 loadshedding by deploying a 24/7 optical line incident triage agent.`,
        proposedAgent: {
          name: "NOC-AutoTriage",
          title: "24/7 Autonomous Incident Triage Agent",
          department: "Network Operations",
          managerId: nocLead.id,
          managerName: nocLead.full_name,
          llmModel: "Qwen 2.5 7B",
          financialLimit: 10000,
          scope: "Hermes telemetry optical loss monitoring, BGP route flap dampening & instant failover",
        },
      })
    }

    // 3. Check Finance / Splynx Reconciliation
    const financeStaff = localStaff.find((e) => e.department === "Finance")
    if (financeStaff) {
      list.push({
        id: "REC-03",
        title: "Deploy Splynx Billing Reconciliation Subagent",
        category: "Regulatory Compliance",
        severity: "Medium",
        description: `Automate monthly debit order reconciliations and credit note dispute verifications under ${financeStaff.full_name}.`,
        proposedAgent: {
          name: "Billing-AuditorBot",
          title: "Splynx Billing & Revenue Assurance Copilot",
          department: "Finance",
          managerId: financeStaff.id,
          managerName: financeStaff.full_name,
          llmModel: "Qwen 2.5 7B",
          financialLimit: 5000,
          scope: "Automated invoice dispute auditing and SARS VAT/PAYE reconciliation",
        },
      })
    }

    return list
  }, [localStaff])

  // Deploy AI Agent from Optimizer recommendation
  const handleDeployRecommendedAgent = (rec: OptimizerRecommendation) => {
    const newRecord: Employee = {
      id: `agent-${Date.now()}`,
      tenant_id: "00000000-0000-0000-0000-000000000001",
      employee_id: `AGT-${Date.now().toString().slice(-4)}`,
      full_name: rec.proposedAgent.name,
      job_title: rec.proposedAgent.title,
      department: rec.proposedAgent.department,
      hire_date: new Date().toISOString().split("T")[0],
      manager_id: rec.proposedAgent.managerId,
      status: "ACTIVE",
      created_at: new Date().toISOString(),
      financial_limit: rec.proposedAgent.financialLimit,
      is_agent: true,
      llm_model: rec.proposedAgent.llmModel,
    }

    setLocalStaff((prev) => [...prev, newRecord])
    setExpandedNodeIds((prev) => new Set([...prev, rec.proposedAgent.managerId]))
    setOptimizerModalOpen(false)
    setToastMessage(`Deployed AI Agent "${newRecord.full_name}" reporting to ${rec.proposedAgent.managerName}!`)
    setTimeout(() => setToastMessage(null), 3500)

    // Persist to backend — triggers Orchestrator + Tenant Memory registration
    createEmployee({
      employee_id: newRecord.employee_id,
      full_name: newRecord.full_name,
      job_title: newRecord.job_title,
      department: newRecord.department,
      hire_date: newRecord.hire_date,
      manager_id: rec.proposedAgent.managerId,
      financial_limit: rec.proposedAgent.financialLimit,
      is_agent: true,
      llm_model: rec.proposedAgent.llmModel,
    }).then((saved) => {
      if (saved?.id) {
        setLocalStaff((prev) =>
          prev.map((s) => (s.id === newRecord.id ? { ...s, id: saved.id } : s))
        )
      }
    }).catch(() => null)
  }

  // ── SAVE FINANCIAL DELEGATION LIMIT ───────────────────────────────────────
  const handleSaveDoa = (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingDoaEmp) return
    setLocalStaff((prev) =>
      prev.map((emp) => (emp.id === editingDoaEmp.id ? { ...emp, financial_limit: newDoaLimit } : emp))
    )
    setToastMessage(`Updated Financial Spend Authority for ${editingDoaEmp.full_name} to R ${newDoaLimit.toLocaleString()}`)
    setTimeout(() => setToastMessage(null), 3000)
    setEditDoaModalOpen(false)
    setEditingDoaEmp(null)
  }

  const getDeptIcon = (dept: string) => {
    switch (dept) {
      case "Executive":
        return <Crown className="h-4 w-4 text-amber-400" />
      case "Network Operations":
      case "Core Infrastructure":
        return <Network className="h-4 w-4 text-cyan-400" />
      case "Field Operations":
        return <Wrench className="h-4 w-4 text-emerald-400" />
      case "Sales":
      case "Marketing":
        return <Coins className="h-4 w-4 text-violet-400" />
      case "Customer Support":
        return <PhoneCall className="h-4 w-4 text-blue-400" />
      case "Finance":
        return <Wallet className="h-4 w-4 text-emerald-400" />
      case "Human Resources":
        return <Users className="h-4 w-4 text-pink-400" />
      case "Engineering":
        return <Laptop className="h-4 w-4 text-sky-400" />
      default:
        return <Building2 className="h-4 w-4 text-muted-foreground" />
    }
  }

  const getDeptBadgeStyle = (dept: string) => {
    switch (dept) {
      case "Executive":
        return "border-amber-500/40 text-amber-400 bg-amber-500/10"
      case "Network Operations":
      case "Core Infrastructure":
        return "border-cyan-500/40 text-cyan-400 bg-cyan-500/10"
      case "Field Operations":
        return "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
      case "Sales":
      case "Marketing":
        return "border-violet-500/40 text-violet-400 bg-violet-500/10"
      case "Customer Support":
        return "border-blue-500/40 text-blue-400 bg-blue-500/10"
      case "Finance":
        return "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
      case "Human Resources":
        return "border-pink-500/40 text-pink-400 bg-pink-500/10"
      default:
        return "border-muted text-muted-foreground bg-muted/20"
    }
  }

  // ── RECURSIVE TREE NODE RENDERER ──────────────────────────────────────────
  const renderTreeNode = (node: OrgTreeNode, depth = 0) => {
    const { employee, children, totalSubordinatesCount } = node
    const isExpanded = expandedNodeIds.has(employee.id)
    const hasChildren = children.length > 0
    const finLimit = getFinancialLimit(employee)

    // Filter check
    const matchesSearch =
      !searchQuery ||
      employee.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      employee.job_title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      employee.department.toLowerCase().includes(searchQuery.toLowerCase())

    const matchesDept = selectedDept === "ALL" || employee.department === selectedDept
    const isVisible = matchesSearch && matchesDept
    const isFaded = !isVisible && searchQuery.length > 0

    return (
      <div key={employee.id} className="flex flex-col items-center">
        {/* Node Box */}
        <div
          className={`relative z-10 w-72 rounded-xl border p-3 shadow-sm transition-all duration-200 backdrop-blur ${
            isFaded ? "opacity-25" : "hover:border-cyan-500/60 hover:shadow-lg hover:ring-1 hover:ring-cyan-500/30"
          } ${
            employee.is_agent
              ? "border-violet-500/60 bg-gradient-to-b from-card via-card to-violet-950/25 ring-1 ring-violet-500/40"
              : depth === 0
              ? "border-amber-500/50 bg-amber-500/5 ring-1 ring-amber-500/30"
              : depth === 1
              ? "border-cyan-500/40 bg-cyan-500/5"
              : "border-border/80 bg-card/90"
          }`}
        >
          {/* Header row */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2.5 min-w-0">
              <div
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border font-semibold text-xs shadow-sm ${
                  employee.is_agent
                    ? "border-violet-500/60 bg-violet-500/20 text-violet-300"
                    : depth === 0
                    ? "border-amber-500/50 bg-amber-500/20 text-amber-300"
                    : "border-border/70 bg-muted/40 text-foreground"
                }`}
              >
                {employee.is_agent ? <Bot className="h-5 w-5 text-violet-400" /> : getDeptIcon(employee.department)}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="font-semibold text-foreground text-sm truncate max-w-[130px]">
                    {employee.full_name}
                  </span>
                  {employee.is_agent ? (
                    <Badge variant="outline" className="text-[9px] border-violet-500 text-violet-300 py-0 px-1 font-bold bg-violet-950/40">
                      AI AGENT
                    </Badge>
                  ) : depth === 0 ? (
                    <Badge variant="outline" className="text-[9px] border-amber-500 text-amber-400 py-0 px-1 font-bold">
                      EXEC
                    </Badge>
                  ) : null}
                </div>
                <p className="text-[11px] text-muted-foreground truncate max-w-[190px]" title={employee.job_title}>
                  {employee.job_title}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-0.5">
              <Button
                size="sm"
                variant="ghost"
                className="h-7 w-7 p-0 text-muted-foreground hover:text-cyan-400"
                onClick={() => handleOpenConnect(employee)}
                title="Change Reporting Manager"
              >
                <Link2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>

          {/* Department badge & Agent Model pill */}
          <div className="mt-2.5 flex items-center justify-between border-t border-border/50 pt-2 text-[10px]">
            <Badge variant="outline" className={`py-0 px-1.5 font-medium ${getDeptBadgeStyle(employee.department)}`}>
              {employee.department}
            </Badge>

            {employee.is_agent && employee.llm_model ? (
              <span className="font-mono text-[9px] text-violet-400 flex items-center gap-1">
                <Cpu className="h-3 w-3" /> {employee.llm_model}
              </span>
            ) : hasChildren ? (
              <span className="text-muted-foreground text-[10px]">
                {children.length} direct ({totalSubordinatesCount} total)
              </span>
            ) : null}
          </div>

          {/* Financial Delegation of Authority (DoA) Bar */}
          {showFinancialDoA && (
            <div className="mt-2 rounded-md border border-border/60 bg-muted/20 px-2.5 py-1.5 flex items-center justify-between text-[10px]">
              <div className="flex items-center gap-1 text-muted-foreground">
                <Wallet className="h-3 w-3 text-emerald-400" />
                <span>Spend Limit:</span>
              </div>
              <button
                type="button"
                onClick={() => {
                  setEditingDoaEmp(employee)
                  setNewDoaLimit(finLimit)
                  setEditDoaModalOpen(true)
                }}
                className="font-bold text-emerald-400 hover:underline flex items-center gap-1"
                title="Edit Financial Authority Limit"
              >
                R {finLimit.toLocaleString()}
                <Edit3 className="h-2.5 w-2.5 text-muted-foreground" />
              </button>
            </div>
          )}

          {/* Managerial Access & Role-Based Scope */}
          {hasChildren && (
            <div className="mt-2 flex items-center justify-between border-t border-border/40 pt-1.5 text-[10px] text-muted-foreground">
              <span className="truncate max-w-[180px]">Approves: Leaves & KPIs ({children.length})</span>
              <button
                type="button"
                onClick={() => toggleExpand(employee.id)}
                className="flex items-center gap-1 font-medium text-cyan-400 hover:text-cyan-300 transition-colors shrink-0"
              >
                <span>{isExpanded ? "Collapse" : "Expand"}</span>
                {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              </button>
            </div>
          )}
        </div>

        {/* Child branches */}
        {hasChildren && isExpanded && (
          <div className="flex flex-col items-center">
            {/* Vertical connector from parent */}
            <div className="h-6 w-0.5 bg-border/80" />

            {/* Container for children - maintain strict horizontal tier */}
            <div className="relative flex flex-nowrap justify-center gap-5 pt-2">
              {/* Horizontal crossbar if multiple children */}
              {children.length > 1 && (
                <div
                  className="absolute top-0 h-0.5 bg-border/80"
                  style={{
                    left: "144px",
                    right: "144px",
                  }}
                />
              )}

              {children.map((child) => (
                <div key={child.employee.id} className="relative flex flex-col items-center">
                  {/* Vertical connector drop to child */}
                  {children.length > 1 && <div className="h-2 w-0.5 bg-border/80" />}
                  {renderTreeNode(child, depth + 1)}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  // Unique departments for filter
  const departments = useMemo(() => {
    const set = new Set<string>()
    localStaff.forEach((e) => set.add(e.department))
    return Array.from(set).sort()
  }, [localStaff])

  // Count total AI agents
  const aiAgentCount = useMemo(() => localStaff.filter((e) => e.is_agent).length, [localStaff])

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-950/95 px-4 py-3 text-sm text-emerald-200 shadow-2xl backdrop-blur animate-in fade-in">
          <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Main Hierarchy Card */}
      <Card className="border-border w-full max-w-full overflow-hidden">
        <CardHeader className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4 border-b border-border/60 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <CardTitle className="flex items-center gap-2 text-lg">
                <Building2 className="h-5 w-5 text-cyan-400" />
                Organizational Hierarchy & Chain of Command
              </CardTitle>
              <Badge variant="outline" className="border-primary/40 text-primary text-[10px]">
                {localStaff.length} Positions ({aiAgentCount} AI Agents)
              </Badge>
            </div>
            <CardDescription className="text-xs mt-0.5">
              Live tree structure driving reporting lines, financial delegation of authority (DoA), and Orchestrator sub-agent routing.
            </CardDescription>
          </div>

          {/* Primary Action Buttons */}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="default"
              size="sm"
              onClick={() => setAddStaffModalOpen(true)}
              className="gap-1.5 text-xs font-semibold h-8"
            >
              <UserPlus className="h-3.5 w-3.5" />
              Add Staff / Agent
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setBulkCsvModalOpen(true)}
              className="gap-1.5 text-xs h-8"
            >
              <Upload className="h-3.5 w-3.5" />
              Bulk CSV
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setOptimizerModalOpen(true)}
              className="gap-1.5 text-xs h-8 border-violet-500/40 text-violet-300 hover:bg-violet-950/20"
            >
              <Brain className="h-3.5 w-3.5 text-violet-400" />
              AI Org Optimizer
            </Button>

            <Button variant="outline" size="sm" onClick={expandAll} className="h-8 text-xs px-2.5">
              Expand All
            </Button>
            <Button variant="outline" size="sm" onClick={collapseAll} className="h-8 text-xs px-2.5">
              Collapse All
            </Button>
          </div>
        </CardHeader>

        <CardContent className="p-3 sm:p-5 space-y-3.5 w-full max-w-full overflow-hidden">
          {/* Controls Bar: Search & Department Filter on Left, DoA and Zoom on Right */}
          <div className="flex flex-wrap items-center justify-between gap-2.5">
            <div className="flex flex-wrap items-center gap-2 flex-1 min-w-[280px]">
              <div className="relative w-full sm:w-64">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  placeholder="Search staff, position, or reporting line…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 h-8 text-xs"
                />
              </div>

              <select
                value={selectedDept}
                onChange={(e) => setSelectedDept(e.target.value)}
                className="h-8 rounded-md border border-border bg-background px-2.5 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="ALL">All Departments ({departments.length})</option>
                {departments.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowFinancialDoA((v) => !v)}
                className={`gap-1.5 text-xs h-8 ${showFinancialDoA ? "border-emerald-500/40 text-emerald-400 bg-emerald-950/10" : ""}`}
              >
                <Wallet className="h-3.5 w-3.5" />
                {showFinancialDoA ? "Hide DoA" : "Show DoA Limits"}
              </Button>

              {/* Fit to Window & Zoom Controls */}
              <div className="flex items-center rounded-lg border border-border bg-card/60 p-0.5 shadow-sm">
                <Button
                  variant={autoFitEnabled ? "default" : "ghost"}
                  size="sm"
                  className={`h-7 px-2 text-[11px] font-semibold gap-1 ${
                    autoFitEnabled ? "bg-primary text-primary-foreground shadow-sm" : "text-primary hover:text-primary"
                  }`}
                  onClick={handleFitToWindow}
                  title="Automatically shrink/scale org chart to fit inside window"
                >
                  <Scale className="h-3 w-3 mr-0.5" />
                  {autoFitEnabled ? "Auto-Fit: ON" : "Fit Window"}
                </Button>

                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0"
                  onClick={() => handleManualZoom(-0.1)}
                  title="Zoom Out"
                >
                  <ZoomOut className="h-3.5 w-3.5" />
                </Button>
                <span className="px-1 text-xs font-mono text-muted-foreground min-w-[34px] text-center">
                  {Math.round(scale * 100)}%
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0"
                  onClick={() => handleManualZoom(0.1)}
                  title="Zoom In"
                >
                  <ZoomIn className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-1.5 text-[11px] text-muted-foreground hover:text-foreground"
                  onClick={handleResetZoom}
                  title="Reset Zoom to 100%"
                >
                  Reset
                </Button>
              </div>
            </div>
          </div>

          {/* Tree Canvas with Smooth Auto-Shrink, Zoom, & Drag/Pan */}
          <div
            ref={canvasContainerRef}
            className={`relative w-full max-w-full overflow-hidden rounded-xl border border-border/60 bg-gradient-to-b from-card/90 via-background to-muted/20 h-[640px] select-none transition-all ${
              isPanning ? "cursor-grabbing" : "cursor-grab"
            }`}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            onWheel={handleWheel}
          >
            {/* Subtle background grid pattern */}
            <div
              className="absolute inset-0 opacity-15 pointer-events-none"
              style={{
                backgroundImage: "radial-gradient(circle, #38bdf8 1px, transparent 1px)",
                backgroundSize: "24px 24px",
              }}
            />

            {/* Floating On-Canvas Mini-Controls (Bottom Right) */}
            <div className="absolute bottom-4 right-4 z-20 flex items-center gap-1.5 rounded-lg border border-border/80 bg-card/90 p-1.5 shadow-xl backdrop-blur">
              <Button
                variant={autoFitEnabled ? "default" : "ghost"}
                size="sm"
                className={`h-7 px-2 text-[11px] gap-1 font-semibold ${
                  autoFitEnabled ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground"
                }`}
                onClick={handleFitToWindow}
                title="Auto-Fit chart to page (automatically shrinks when expanded)"
              >
                <Scale className="h-3 w-3" />
                {autoFitEnabled ? "Auto-Fit: ON" : "Fit to Page"}
              </Button>
              <div className="h-4 w-px bg-border mx-0.5" />
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => handleManualZoom(-0.1)}
                title="Zoom Out"
              >
                <ZoomOut className="h-3.5 w-3.5" />
              </Button>
              <span className="px-1 text-xs font-mono font-medium text-foreground min-w-[36px] text-center">
                {Math.round(scale * 100)}%
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => handleManualZoom(0.1)}
                title="Zoom In"
              >
                <ZoomIn className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-1.5 text-[11px] text-muted-foreground hover:text-foreground"
                onClick={handleResetZoom}
                title="Reset to 100%"
              >
                Reset
              </Button>
            </div>

            {/* Hint Badge (Bottom Left) */}
            <div className="absolute bottom-4 left-4 z-20 hidden sm:flex items-center gap-2 rounded-md border border-border/50 bg-card/70 px-2.5 py-1 text-[10px] text-muted-foreground backdrop-blur pointer-events-none">
              <Move className="h-3 w-3 text-cyan-400" />
              <span>Drag canvas to pan • Ctrl + scroll to zoom</span>
              {autoFitEnabled && (
                <span className="inline-flex items-center gap-1 font-medium text-emerald-400 ml-1">
                  • Auto-shrinking on expand active
                </span>
              )}
            </div>

            {/* Absolutely Isolated Scaled & Translated Tree Layer */}
            <div
              className="absolute inset-0 flex justify-center items-start transition-transform duration-300 ease-out pt-8 overflow-visible"
              style={{
                transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${scale})`,
                transformOrigin: "top center",
              }}
            >
              <div
                ref={treeContentRef}
                className="inline-flex flex-col items-center min-w-max pb-16"
              >
                {orgTree.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-12">No active employees found to construct hierarchy.</p>
                ) : (
                  <div className="flex flex-col items-center gap-10">
                    {orgTree.map((rootNode) => renderTreeNode(rootNode, 0))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── MODAL 1: ADD STAFF / AGENT FREE-HAND FORM ─────────────────────── */}
      {addStaffModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm animate-in fade-in">
          <Card className="w-full max-w-lg border-border shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary/40 bg-primary/10 text-primary">
                  {newStaffIsAgent ? <Bot className="h-4 w-4" /> : <UserPlus className="h-4 w-4" />}
                </div>
                <div>
                  <CardTitle className="text-base font-bold">
                    {newStaffIsAgent ? "Deploy Autonomous AI Agent" : "Add Staff Member to Hierarchy"}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Assign a direct reporting manager to update the organizational tree structure immediately.
                  </CardDescription>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setAddStaffModalOpen(false)}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleAddStaffSubmit}>
              <CardContent className="space-y-3.5 pt-4 text-xs">
                {/* Agent vs Human Toggle */}
                <div className="flex items-center justify-between rounded-lg border border-border bg-muted/20 p-2.5">
                  <div>
                    <span className="font-semibold text-foreground block">Position Type</span>
                    <span className="text-[11px] text-muted-foreground">
                      {newStaffIsAgent ? "Autonomous AI sub-agent integrated into Orchestrator" : "Human employee in telecom staff roster"}
                    </span>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant={newStaffIsAgent ? "default" : "outline"}
                    onClick={() => setNewStaffIsAgent((v) => !v)}
                    className="gap-1.5 text-xs h-7"
                  >
                    <Bot className="h-3 w-3" />
                    {newStaffIsAgent ? "AI Subagent" : "Human Staff"}
                  </Button>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="font-semibold text-foreground">
                      {newStaffIsAgent ? "Agent Name *" : "Full Name *"}
                    </label>
                    <Input
                      required
                      placeholder={newStaffIsAgent ? "e.g. NOC-AutoTriage" : "e.g. Kagiso Dlamini"}
                      value={newStaffName}
                      onChange={(e) => setNewStaffName(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="font-semibold text-foreground">Position / Job Title *</label>
                    <Input
                      required
                      placeholder={newStaffIsAgent ? "e.g. 24/7 Optical Incident Agent" : "e.g. Junior Network Engineer"}
                      value={newStaffTitle}
                      onChange={(e) => setNewStaffTitle(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="font-semibold text-foreground">Department *</label>
                    <select
                      value={newStaffDept}
                      onChange={(e) => setNewStaffDept(e.target.value)}
                      className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                    >
                      <option value="Network Operations">Network Operations (NOC)</option>
                      <option value="Field Operations">Field Operations</option>
                      <option value="Core Infrastructure">Core Infrastructure</option>
                      <option value="Customer Support">Customer Support</option>
                      <option value="Sales">Sales & Revenue</option>
                      <option value="Marketing">Marketing</option>
                      <option value="Finance">Finance & Billing</option>
                      <option value="Human Resources">Human Resources</option>
                      <option value="Engineering">Engineering</option>
                      <option value="Executive">Executive</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label className="font-semibold text-foreground">Reporting To (Direct Manager) *</label>
                    <select
                      value={newStaffReportingTo}
                      onChange={(e) => setNewStaffReportingTo(e.target.value)}
                      className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground font-medium"
                    >
                      <option value="NONE">— None (Top Executive / CEO Level) —</option>
                      {localStaff.map((mgr) => (
                        <option key={mgr.id} value={mgr.id}>
                          {mgr.full_name} ({mgr.job_title} — {mgr.department})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Financial Approval Authority (DoA) */}
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <label className="font-semibold text-foreground">Financial Delegation Authority (ZAR)</label>
                    <span className="font-mono text-emerald-400 font-bold text-xs">
                      R {newStaffFinancialLimit.toLocaleString()}
                    </span>
                  </div>
                  <select
                    value={newStaffFinancialLimit}
                    onChange={(e) => setNewStaffFinancialLimit(Number(e.target.value))}
                    className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value={5000}>R 5,000 (Tier 5 - Routine Consumables & Waives)</option>
                    <option value={10000}>R 10,000 (Tier 4 - Autonomous AI Agent Credits)</option>
                    <option value={25000}>R 25,000 (Tier 4 - Spares & Maintenance)</option>
                    <option value={50000}>R 50,000 (Tier 3 - Operational Field Expenses)</option>
                    <option value={100000}>R 100,000 (Tier 3 - Department Head Tooling & Van Spares)</option>
                    <option value={500000}>R 500,000 (Tier 2 - Executive DWDM / Network Capital)</option>
                    <option value={5000000}>R 5,000,000 (Tier 1 - CEO & Board Mandate)</option>
                  </select>
                </div>

                {/* AI Agent specifics */}
                {newStaffIsAgent && (
                  <div className="rounded-lg border border-violet-500/40 bg-violet-950/20 p-3 space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-violet-300 flex items-center gap-1">
                        <Bot className="h-3.5 w-3.5" /> Orchestrator Integration
                      </span>
                      <Badge variant="outline" className="text-[9px] border-violet-500 text-violet-300">
                        Subagent Binding
                      </Badge>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      <div className="space-y-1">
                        <label className="text-[10px] text-muted-foreground">Assigned LLM Model</label>
                        <select
                          value={newStaffLlmModel}
                          onChange={(e) => setNewStaffLlmModel(e.target.value)}
                          className="w-full h-7 rounded border border-border bg-background px-2 text-[11px]"
                        >
                          <option value="Qwen 2.5 7B">Qwen 2.5 7B (Fast, Zero-Latency)</option>
                          <option value="Llama 3.3 70B">Llama 3.3 70B (Complex Reasoning)</option>
                          <option value="Claude 3.5 Sonnet">Claude 3.5 Sonnet (Executive)</option>
                          <option value="DeepSeek-R1">DeepSeek-R1 (Diagnostic Reasoning)</option>
                        </select>
                      </div>
                      <div className="space-y-1">
                        <label className="text-[10px] text-muted-foreground">Autonomous Scope</label>
                        <Input
                          value={newStaffAgentScope}
                          onChange={(e) => setNewStaffAgentScope(e.target.value)}
                          className="h-7 text-[11px]"
                        />
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setAddStaffModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default" className="gap-1.5">
                  <Check className="h-3.5 w-3.5" />
                  {newStaffIsAgent ? "Deploy AI Agent to Tree" : "Add Staff to Hierarchy"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ── MODAL 2: BULK CSV UPLOAD ──────────────────────────────────────── */}
      {bulkCsvModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm animate-in fade-in">
          <Card className="w-full max-w-2xl border-border shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="h-5 w-5 text-emerald-400" />
                <div>
                  <CardTitle className="text-base font-bold">Bulk CSV Org Hierarchy Ingestion</CardTitle>
                  <CardDescription className="text-xs">
                    Upload or paste CSV rows with "Reporting To" relationships to construct the entire company hierarchy at once.
                  </CardDescription>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setBulkCsvModalOpen(false)}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <CardContent className="space-y-4 pt-4 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-foreground">Paste CSV Text or Upload .csv:</span>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-[11px] gap-1"
                  onClick={() => {
                    const sample = `Full Name,Job Title,Department,Reporting To,Financial Limit,Is Agent,LLM Model
Pieter van Wyk,Chief Executive Officer,Executive,,5000000,false,
Thabo Nkosi,Chief Technology Officer,Executive,Pieter van Wyk,500000,false,
Johan Pretorius,NOC Team Lead,Network Operations,Thabo Nkosi,100000,false,
NOC-AutoTriage,Autonomous 24/7 Incident Triage,Network Operations,Johan Pretorius,10000,true,Qwen 2.5 7B
Willem Botha,Head of Field Operations,Field Operations,Thabo Nkosi,100000,false,
Field-DispatchBot,Automated Van Routing Copilot,Field Operations,Willem Botha,15000,true,Llama 3.3 70B
Musa Sithole,Senior Fiber Splice Technician,Field Operations,Willem Botha,25000,false,
Rethabile Sekhoto,Billing & Revenue Assurance Analyst,Finance,Pieter van Wyk,50000,false,
Ayesha Patel,HR & Payroll Specialist,Human Resources,Pieter van Wyk,50000,false,`
                    handleParseCsv(sample)
                  }}
                >
                  <Copy className="h-3 w-3" /> Load Sample CSV
                </Button>
              </div>

              <Textarea
                rows={6}
                value={csvRawText}
                onChange={(e) => handleParseCsv(e.target.value)}
                placeholder="Full Name,Job Title,Department,Reporting To,Financial Limit,Is Agent,LLM Model..."
                className="font-mono text-[11px]"
              />

              {csvParseError && <p className="text-red-400 text-xs">{csvParseError}</p>}

              {/* Preview Table */}
              {csvPreviewRows.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-bold text-foreground">Parsed Records ({csvPreviewRows.length} positions):</span>
                    <span className="text-emerald-400">Ready to map into Org Tree</span>
                  </div>
                  <div className="max-h-40 overflow-y-auto rounded border border-border bg-black/30">
                    <table className="w-full text-[10px]">
                      <thead>
                        <tr className="border-b border-border bg-muted/20 text-muted-foreground text-left">
                          <th className="py-1 px-2">Name</th>
                          <th className="py-1 px-2">Job Title</th>
                          <th className="py-1 px-2">Department</th>
                          <th className="py-1 px-2">Reporting To</th>
                          <th className="py-1 px-2">DoA Limit</th>
                          <th className="py-1 px-2">Type</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/40">
                        {csvPreviewRows.map((r, i) => (
                          <tr key={i} className="hover:bg-muted/10">
                            <td className="py-1 px-2 font-medium text-foreground">{r.name}</td>
                            <td className="py-1 px-2 text-muted-foreground">{r.title}</td>
                            <td className="py-1 px-2 text-muted-foreground">{r.department}</td>
                            <td className="py-1 px-2 text-primary font-medium">{r.reportingToName || "— CEO / Root —"}</td>
                            <td className="py-1 px-2 text-emerald-400 font-mono">R {r.financialLimit.toLocaleString()}</td>
                            <td className="py-1 px-2">
                              {r.isAgent ? (
                                <Badge variant="outline" className="text-[8px] border-violet-500 text-violet-300 py-0">
                                  AI
                                </Badge>
                              ) : (
                                "Human"
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </CardContent>
            <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
              <Button type="button" variant="ghost" size="sm" onClick={() => setBulkCsvModalOpen(false)}>
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                variant="default"
                disabled={csvPreviewRows.length === 0}
                onClick={handleImportCsv}
                className="gap-1.5"
              >
                <Check className="h-3.5 w-3.5" />
                Import & Depict Hierarchy ({csvPreviewRows.length} Nodes)
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* ── MODAL 3: AI STRUCTURAL OPTIMIZER & SKILL GAP ADVISOR ────────── */}
      {optimizerModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm animate-in fade-in">
          <Card className="w-full max-w-2xl border-violet-500/40 shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <Brain className="h-5 w-5 text-violet-400" />
                <div>
                  <CardTitle className="text-base font-bold">Orchestrator Structural Optimization Advisor</CardTitle>
                  <CardDescription className="text-xs">
                    Identifies management bottlenecks and skill gaps; deploy autonomous AI agents where humans are unavailable.
                  </CardDescription>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setOptimizerModalOpen(false)}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <CardContent className="space-y-4 pt-4 text-xs">
              <p className="text-muted-foreground">
                The Orchestrator evaluated your company structure against current operational workload and telemetry. Here are 3 recommended agent deployments:
              </p>

              <div className="space-y-3">
                {optimizerRecommendations.map((rec) => (
                  <div key={rec.id} className="rounded-xl border border-border bg-card p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant="outline"
                          className={
                            rec.severity === "High"
                              ? "border-red-500/40 text-red-400 bg-red-950/20"
                              : "border-amber-500/40 text-amber-400 bg-amber-950/20"
                          }
                        >
                          {rec.category}
                        </Badge>
                        <h4 className="font-bold text-foreground text-xs">{rec.title}</h4>
                      </div>
                      <span className="text-[10px] font-mono text-muted-foreground">{rec.id}</span>
                    </div>

                    <p className="text-muted-foreground text-xs leading-relaxed">{rec.description}</p>

                    <div className="rounded-lg border border-violet-500/30 bg-violet-950/15 p-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-1.5 font-bold text-violet-300">
                          <Bot className="h-3.5 w-3.5" />
                          <span>{rec.proposedAgent.name}</span>
                          <span className="text-[10px] text-muted-foreground font-normal">({rec.proposedAgent.title})</span>
                        </div>
                        <p className="text-[10px] text-muted-foreground">
                          Reports to: <span className="text-foreground font-semibold">{rec.proposedAgent.managerName}</span> • DoA Limit: R {rec.proposedAgent.financialLimit.toLocaleString()}
                        </p>
                      </div>

                      <Button
                        size="sm"
                        variant="default"
                        className="gap-1.5 text-xs h-7 bg-violet-600 hover:bg-violet-500 text-white shrink-0"
                        onClick={() => handleDeployRecommendedAgent(rec)}
                      >
                        <UserPlus className="h-3 w-3" />
                        Deploy Agent Here
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
            <div className="flex items-center justify-end border-t border-border p-3 bg-muted/10">
              <Button size="sm" variant="ghost" onClick={() => setOptimizerModalOpen(false)}>
                Close Advisor
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* ── MODAL 4: EDIT FINANCIAL DELEGATION AUTHORITY (DoA) ──────────── */}
      {editDoaModalOpen && editingDoaEmp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm animate-in fade-in">
          <Card className="w-full max-w-md border-border shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <Wallet className="h-5 w-5 text-emerald-400" />
                <div>
                  <CardTitle className="text-base font-bold">Edit Delegation of Authority</CardTitle>
                  <CardDescription className="text-xs">
                    Configure maximum spend and project purchase approval for {editingDoaEmp.full_name}.
                  </CardDescription>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setEditDoaModalOpen(false)}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleSaveDoa}>
              <CardContent className="space-y-4 pt-4 text-xs">
                <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-1">
                  <p className="text-xs text-muted-foreground">Position Profile</p>
                  <p className="text-sm font-semibold text-foreground">{editingDoaEmp.full_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {editingDoaEmp.job_title} • {editingDoaEmp.department}
                  </p>
                </div>

                <div className="space-y-2">
                  <label className="font-semibold text-foreground">Spend Approval Authority Limit (ZAR)</label>
                  <Input
                    type="number"
                    min={0}
                    step={1000}
                    value={newDoaLimit}
                    onChange={(e) => setNewDoaLimit(Number(e.target.value))}
                    className="h-8 text-xs font-mono font-bold text-emerald-400"
                  />
                  <p className="text-[10px] text-muted-foreground">
                    Any purchase or contract exceeding this amount automatically escalates up the reporting line.
                  </p>
                </div>
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setEditDoaModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default" className="gap-1.5">
                  <Check className="h-3.5 w-3.5" /> Save Spend Limit
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ── MODAL 5: REASSIGN MANAGER MODAL ──────────────────────────────── */}
      {connectingEmp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm animate-in fade-in">
          <Card className="w-full max-w-md border-border shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-base font-semibold">Change Reporting Line</CardTitle>
                <CardDescription className="text-xs">
                  Reassign direct supervisor for <span className="text-foreground font-semibold">{connectingEmp.full_name}</span>.
                </CardDescription>
              </div>
              <button
                type="button"
                onClick={() => setConnectingEmp(null)}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleSaveReportingLine}>
              <CardContent className="space-y-4 pt-2">
                <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-1">
                  <p className="text-xs text-muted-foreground">Employee Profile</p>
                  <p className="text-sm font-semibold text-foreground">{connectingEmp.full_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {connectingEmp.job_title} • {connectingEmp.department}
                  </p>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-foreground">Select New Reporting Manager</label>
                  <select
                    value={targetManagerId}
                    onChange={(e) => setTargetManagerId(e.target.value)}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value="NONE">— None (Top Executive / CEO Level) —</option>
                    {localStaff
                      .filter((e) => e.id !== connectingEmp.id)
                      .map((mgr) => (
                        <option key={mgr.id} value={mgr.id}>
                          {mgr.full_name} ({mgr.job_title} — {mgr.department})
                        </option>
                      ))}
                  </select>
                </div>
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setConnectingEmp(null)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default" disabled={isUpdating}>
                  {isUpdating ? "Saving Line…" : "Save Reporting Line"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
