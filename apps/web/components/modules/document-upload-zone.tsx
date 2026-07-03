"use client"

import { useCallback, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { DocumentResultCard, UrlFetchResultCard } from "./document-result-cards"
import {
  Upload, Link, Globe, FileText, FileCheck, AlertTriangle,
  CheckCircle, XCircle, Loader2, ChevronDown, ChevronUp,
  Building2, Gavel, Shield, Heart, Users, Landmark, Coins,
  ExternalLink, RefreshCw, Trash2, Eye,
} from "lucide-react"
import {
  uploadDocument, fetchUrlDocument, linkDocumentToContract,
  type DocumentUploadResult, type UrlFetchResult,
} from "@/lib/compliance-api"

// ═══════════════════════════════════════════════════════════════════════════════
// DOCUMENT TYPE ICON MAP
// ═══════════════════════════════════════════════════════════════════════════════

const DOC_TYPE_ICON: Record<string, React.ReactNode> = {
  contract: <FileText className="h-4 w-4 text-blue-400" />,
  tax_return: <Gavel className="h-4 w-4 text-red-400" />,
  hs_report: <Heart className="h-4 w-4 text-rose-400" />,
  cipc_filing: <Building2 className="h-4 w-4 text-purple-400" />,
  bbbee_certificate: <Shield className="h-4 w-4 text-emerald-400" />,
  permit: <Users className="h-4 w-4 text-amber-400" />,
  dr_plan: <Shield className="h-4 w-4 text-indigo-400" />,
  bcp_plan: <Shield className="h-4 w-4 text-indigo-400" />,
  financial_statement: <Coins className="h-4 w-4 text-green-400" />,
  invoice: <FileText className="h-4 w-4 text-gray-400" />,
  policy: <FileCheck className="h-4 w-4 text-cyan-400" />,
  regulation: <Landmark className="h-4 w-4 text-blue-400" />,
  breach_report: <AlertTriangle className="h-4 w-4 text-red-400" />,
  dsar: <Users className="h-4 w-4 text-orange-400" />,
  icasa_submission: <Landmark className="h-4 w-4 text-blue-400" />,
}

const ENTITY_LABELS: Record<string, string> = {
  contract_number: "Contract No.",
  company_registration: "Reg. No.",
  vat_number: "VAT",
  tax_reference: "Tax Ref",
  phone: "Phone",
  email: "Email",
  monetary_amount: "Amount",
  percentage: "Percent",
  date: "Date",
  regulation_ref: "Regulation",
  icasa_ref: "ICASA",
  sars_ref: "SARS",
  government_gazette: "Gazette",
  bbbee_ref: "BBBEE",
  popi_ref: "POPI",
  rica_ref: "RICA",
  cipc_ref: "CIPC",
  coida_ref: "COIDA",
  case_number: "Case No.",
  sla_metric: "SLA",
  url: "Link",
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN UPLOAD COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

interface DocumentUploadZoneProps {
  contractId?: number
  onUploadComplete?: (result: DocumentUploadResult) => void
  onUrlFetchComplete?: (result: UrlFetchResult) => void
  compact?: boolean
}

export default function DocumentUploadZone({
  contractId,
  onUploadComplete,
  onUrlFetchComplete,
  compact = false,
}: DocumentUploadZoneProps) {
  const [mode, setMode] = useState<"upload" | "url" | "crawl">("upload")
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [fetching, setFetching] = useState(false)
  const [url, setUrl] = useState("")
  const [crawlDepth, setCrawlDepth] = useState(2)
  const [docTypeHint, setDocTypeHint] = useState("")
  const [result, setResult] = useState<DocumentUploadResult | null>(null)
  const [urlResult, setUrlResult] = useState<UrlFetchResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showDetails, setShowDetails] = useState(true)

  // ── File Upload Handler ─────────────────────────────────────────────

  const handleFile = useCallback(async (file: File) => {
    setUploading(true)
    setError(null)
    setResult(null)
    try {
      const res = await uploadDocument(file, {
        docTypeHint: docTypeHint || undefined,
        contractId,
        process: true,
      })
      setResult(res)
      onUploadComplete?.(res)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed")
    } finally {
      setUploading(false)
    }
  }, [docTypeHint, contractId, onUploadComplete])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }, [handleFile])

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }, [handleFile])

  // ── URL Fetch Handler ────────────────────────────────────────────────

  const handleUrlFetch = useCallback(async () => {
    if (!url.trim()) return
    setFetching(true)
    setError(null)
    setUrlResult(null)
    try {
      const res = await fetchUrlDocument(url.trim(), {
        docTypeHint: docTypeHint || undefined,
        crawl: mode === "crawl",
        maxDepth: crawlDepth,
      })
      setUrlResult(res)
      onUrlFetchComplete?.(res)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "URL fetch failed")
    } finally {
      setFetching(false)
    }
  }, [url, mode, crawlDepth, docTypeHint, onUrlFetchComplete])

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <Card className="border-border/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm flex items-center gap-2">
          <Upload className="h-4 w-4 text-primary" />
          Document Upload & Understanding
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Mode Tabs */}
        <div className="flex gap-1 p-1 rounded-lg bg-muted/30">
          {([
            { key: "upload", icon: <Upload className="h-3.5 w-3.5" />, label: "File Upload" },
            { key: "url", icon: <Link className="h-3.5 w-3.5" />, label: "URL Fetch" },
            { key: "crawl", icon: <Globe className="h-3.5 w-3.5" />, label: "Website Crawl" },
          ] as const).map((m) => (
            <button key={m.key} onClick={() => setMode(m.key)}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                mode === m.key ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
              }`}>
              {m.icon} {m.label}
            </button>
          ))}
        </div>

        {/* Document Type Hint */}
        <div className="flex items-center gap-2">
          <Label className="text-xs text-muted-foreground whitespace-nowrap">Type hint:</Label>
          <select value={docTypeHint} onChange={(e) => setDocTypeHint(e.target.value)}
            className="flex h-8 rounded-md border border-border bg-background px-2 text-xs">
            <option value="">Auto-detect</option>
            <option value="contract">Contract</option>
            <option value="tax_return">Tax Return</option>
            <option value="hs_report">H&S Report</option>
            <option value="cipc_filing">CIPC Filing</option>
            <option value="bbbee_certificate">BBBEE Certificate</option>
            <option value="permit">Permit</option>
            <option value="dr_plan">DR Plan</option>
            <option value="bcp_plan">BCP Plan</option>
            <option value="financial_statement">Financial Statement</option>
            <option value="invoice">Invoice</option>
            <option value="policy">Policy</option>
            <option value="regulation">Regulation</option>
            <option value="breach_report">Breach Report</option>
            <option value="dsar">POPI DSAR</option>
            <option value="icasa_submission">ICASA Submission</option>
          </select>
          {contractId && (
            <Badge variant="outline" className="text-[10px] border-blue-500/40 text-blue-400">
              Linked to Contract #{contractId}
            </Badge>
          )}
        </div>

        {/* Upload Zone */}
        {mode === "upload" && (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={`relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 transition-colors ${
              dragOver ? "border-primary bg-primary/5" : "border-border/50 hover:border-border"
            }`}>
            <input type="file" onChange={handleFileInput} className="absolute inset-0 opacity-0 cursor-pointer"
              accept=".pdf,.docx,.pptx,.xlsx,.xls,.txt,.md,.html,.htm,.csv" />
            {uploading ? (
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            ) : (
              <Upload className="h-8 w-8 text-muted-foreground" />
            )}
            <p className="mt-2 text-sm text-muted-foreground">
              {uploading ? "Processing..." : "Drop file here or click to browse"}
            </p>
            <p className="mt-1 text-[10px] text-muted-foreground">
              PDF · DOCX · PPTX · XLSX · TXT · MD · HTML · CSV
            </p>
          </div>
        )}

        {/* URL / Crawl Zone */}
        {(mode === "url" || mode === "crawl") && (
          <div className="space-y-3">
            <div className="flex gap-2">
              <Input value={url} onChange={(e) => setUrl(e.target.value)}
                placeholder={mode === "crawl" ? "https://www.icasa.org.za/legislation" : "https://example.com/document.pdf"}
                className="h-9" />
              <Button size="sm" onClick={handleUrlFetch} disabled={fetching || !url.trim()}>
                {fetching ? <Loader2 className="h-4 w-4 animate-spin" /> : mode === "crawl" ? <Globe className="h-4 w-4" /> : <Link className="h-4 w-4" />}
                <span className="ml-1">{mode === "crawl" ? "Crawl" : "Fetch"}</span>
              </Button>
            </div>
            {mode === "crawl" && (
              <div className="flex items-center gap-2">
                <Label className="text-xs text-muted-foreground">Depth:</Label>
                <select value={crawlDepth} onChange={(e) => setCrawlDepth(Number(e.target.value))}
                  className="h-7 rounded border border-border bg-background px-2 text-xs">
                  <option value={1}>1 level</option>
                  <option value={2}>2 levels</option>
                  <option value={3}>3 levels</option>
                </select>
                <span className="text-[10px] text-muted-foreground">Max 20 pages</span>
              </div>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/5 p-3">
            <XCircle className="h-4 w-4 text-red-400 shrink-0" />
            <p className="text-xs text-red-400">{error}</p>
          </div>
        )}

        {/* Upload Result */}
        {result && (
          <DocumentResultCard result={result} showDetails={showDetails} onToggleDetails={() => setShowDetails(!showDetails)} />
        )}

        {/* URL Fetch Result */}
        {urlResult && (
          <UrlFetchResultCard result={urlResult} />
        )}
      </CardContent>
    </Card>
  )
}
