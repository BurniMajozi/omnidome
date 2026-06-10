"use client"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  CheckCircle, ChevronDown, ChevronUp, ExternalLink,
  FileText, Link, DollarSign, Calendar, Hash, AlertTriangle,
} from "lucide-react"
import type { DocumentUploadResult, UrlFetchResult } from "@/lib/compliance-api"

const ENTITY_LABELS: Record<string, string> = {
  contract_number: "Contract No.", company_registration: "Reg. No.", vat_number: "VAT",
  tax_reference: "Tax Ref", phone: "Phone", email: "Email", monetary_amount: "Amount",
  percentage: "Percent", date: "Date", regulation_ref: "Regulation", icasa_ref: "ICASA",
  sars_ref: "SARS", government_gazette: "Gazette", bbbee_ref: "BBBEE", popi_ref: "POPI",
  rica_ref: "RICA", cipc_ref: "CIPC", coida_ref: "COIDA", case_number: "Case No.",
  sla_metric: "SLA", url: "Link",
}

const LINK_TYPE_COLOR: Record<string, string> = {
  government: "border-blue-500/40 text-blue-400",
  regulation: "border-purple-500/40 text-purple-400",
  legal: "border-amber-500/40 text-amber-400",
  external: "border-gray-500/40 text-gray-400",
}

interface DocumentResultCardProps {
  result: DocumentUploadResult
  showDetails: boolean
  onToggleDetails: () => void
}

export function DocumentResultCard({ result, showDetails, onToggleDetails }: DocumentResultCardProps) {
  const u = result.understanding
  if (!u) return null

  return (
    <div className="space-y-3">
      {/* Summary Header */}
      <div className="flex items-center justify-between rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
        <div className="flex items-center gap-2">
          <CheckCircle className="h-4 w-4 text-emerald-400" />
          <span className="text-sm font-medium">Document Processed</span>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px]">
            {u.document_type.replace(/_/g, " ")} ({Math.round(u.confidence * 100)}%)
          </Badge>
          <span className="text-[10px] text-muted-foreground">{u.processing_time_ms.toFixed(0)}ms</span>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-4 gap-2">
        <div className="rounded-lg border border-border/50 p-2 text-center">
          <p className="text-lg font-bold">{u.entities.length}</p>
          <p className="text-[10px] text-muted-foreground">Entities</p>
        </div>
        <div className="rounded-lg border border-border/50 p-2 text-center">
          <p className="text-lg font-bold">{u.financials.length}</p>
          <p className="text-[10px] text-muted-foreground">Financials</p>
        </div>
        <div className="rounded-lg border border-border/50 p-2 text-center">
          <p className="text-lg font-bold">{u.links.length}</p>
          <p className="text-[10px] text-muted-foreground">Links</p>
        </div>
        <div className="rounded-lg border border-border/50 p-2 text-center">
          <p className="text-lg font-bold">{u.references.length}</p>
          <p className="text-[10px] text-muted-foreground">References</p>
        </div>
      </div>

      {/* Toggle Details */}
      <button onClick={onToggleDetails} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        {showDetails ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        {showDetails ? "Hide" : "Show"} extracted details
      </button>

      {showDetails && (
        <div className="space-y-3">
          {/* Entities */}
          {u.entities.length > 0 && (
            <div>
              <p className="text-xs font-medium mb-1.5 flex items-center gap-1">
                <Hash className="h-3 w-3" /> Extracted Entities
              </p>
              <div className="flex flex-wrap gap-1.5">
                {u.entities.map((e, i) => (
                  <div key={i} className="rounded-md border border-border/50 bg-muted/30 px-2 py-1">
                    <span className="text-[10px] text-muted-foreground">{ENTITY_LABELS[e.label] || e.label}:</span>{" "}
                    <span className="text-xs font-medium">{e.value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Financials */}
          {u.financials.length > 0 && (
            <div>
              <p className="text-xs font-medium mb-1.5 flex items-center gap-1">
                <DollarSign className="h-3 w-3" /> Financial Amounts
              </p>
              <div className="space-y-1">
                {u.financials.map((f, i) => (
                  <div key={i} className="flex items-center justify-between rounded-md border border-border/50 bg-muted/30 px-2 py-1.5">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px]">{f.line_item}</Badge>
                      <span className="text-sm font-medium">R{f.amount?.toLocaleString()}</span>
                    </div>
                    {f.context && (
                      <span className="text-[10px] text-muted-foreground truncate max-w-[200px]">{f.context}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Links */}
          {u.links.length > 0 && (
            <div>
              <p className="text-xs font-medium mb-1.5 flex items-center gap-1">
                <Link className="h-3 w-3" /> Extracted Links
              </p>
              <div className="space-y-1">
                {u.links.map((l, i) => (
                  <div key={i} className="flex items-center justify-between rounded-md border border-border/50 bg-muted/30 px-2 py-1.5">
                    <div className="flex items-center gap-2 min-w-0">
                      <Badge variant="outline" className={`text-[10px] ${LINK_TYPE_COLOR[l.link_type] || ""}`}>
                        {l.link_type}
                      </Badge>
                      <span className="text-xs truncate max-w-[300px]">{l.url}</span>
                    </div>
                    <a href={l.url} target="_blank" rel="noopener noreferrer" className="shrink-0">
                      <ExternalLink className="h-3 w-3 text-muted-foreground" />
                    </a>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* References */}
          {u.references.length > 0 && (
            <div>
              <p className="text-xs font-medium mb-1.5 flex items-center gap-1">
                <FileText className="h-3 w-3" /> Regulation / Legal References
              </p>
              <div className="flex flex-wrap gap-1.5">
                {u.references.map((r, i) => (
                  <Badge key={i} variant="outline" className="text-[10px] border-purple-500/40 text-purple-400">
                    {r}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Dates */}
          {u.dates.length > 0 && (
            <div>
              <p className="text-xs font-medium mb-1.5 flex items-center gap-1">
                <Calendar className="h-3 w-3" /> Dates Found
              </p>
              <div className="flex flex-wrap gap-1.5">
                {u.dates.map((d, i) => (
                  <Badge key={i} variant="outline" className="text-[10px]">{d}</Badge>
                ))}
              </div>
            </div>
          )}

          {/* Errors */}
          {u.errors.length > 0 && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2">
              {u.errors.map((err, i) => (
                <p key={i} className="text-[10px] text-amber-400 flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" /> {err}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// URL FETCH RESULT CARD
// ═══════════════════════════════════════════════════════════════════════════════

export function UrlFetchResultCard({ result }: { result: UrlFetchResult }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
        <div className="flex items-center gap-2">
          <CheckCircle className="h-4 w-4 text-emerald-400" />
          <span className="text-sm font-medium">
            {result.documents_found} document{result.documents_found !== 1 ? "s" : ""} found
          </span>
        </div>
        <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px]">
          {result.crawl ? "Crawl" : "Fetch"}
        </Badge>
      </div>

      <div className="space-y-2">
        {result.documents.map((d, i) => (
          <div key={i} className="flex items-center justify-between rounded-md border border-border/50 bg-muted/30 px-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium truncate">{d.source}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <Badge variant="outline" className="text-[10px]">{d.format}</Badge>
                <Badge variant="outline" className="text-[10px] border-blue-500/40 text-blue-400">
                  {d.document_type.replace(/_/g, " ")} ({Math.round(d.confidence * 100)}%)
                </Badge>
              </div>
            </div>
            <div className="text-right shrink-0 ml-3">
              <p className="text-xs">{d.entities_count} entities</p>
              <p className="text-[10px] text-muted-foreground">{d.processing_time_ms.toFixed(0)}ms</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
