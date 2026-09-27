"use client"

import React from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { X, Printer, ShieldCheck, Building2, CheckCircle2, Download } from "lucide-react"
import { type PayslipRecord } from "@/lib/hr-api"

interface PayslipModalProps {
  payslip: PayslipRecord | null
  onClose: () => void
}

export function PayslipModal({ payslip, onClose }: PayslipModalProps) {
  if (!payslip) return null

  const handlePrint = () => {
    window.print()
  }

  // Format currency ZAR
  const zar = (val?: number) => {
    return `R ${(val || 0).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }

  const isPaid = payslip.payout_status === "PAID"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm overflow-y-auto">
      <div className="bg-background rounded-xl border border-border max-w-3xl w-full p-6 sm:p-8 space-y-6 shadow-2xl my-8 print:border-none print:shadow-none print:p-0 print:m-0">
        {/* Modal actions (hidden on print) */}
        <div className="flex items-center justify-between border-b border-border pb-3 print:hidden">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            <span className="font-semibold text-sm text-foreground">Official South African Statutory Payslip</span>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={handlePrint} className="gap-1.5 h-8">
              <Printer className="h-3.5 w-3.5" />
              Print / PDF
            </Button>
            <Button size="icon" variant="ghost" onClick={onClose} className="h-8 w-8">
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* ── OFFICIAL PAYSLIP SHEET ─────────────────────────────────── */}
        <div className="rounded-lg border border-border/80 bg-background p-6 space-y-6 text-foreground print:border-none">
          {/* Header & Company Details */}
          <div className="flex flex-col sm:flex-row justify-between gap-4 border-b border-border pb-5">
            <div>
              <div className="flex items-center gap-2">
                <Building2 className="h-6 w-6 text-sky-400" />
                <h1 className="text-xl font-bold tracking-tight text-foreground">OmniDome Networks (Pty) Ltd</h1>
              </div>
              <p className="text-xs text-muted-foreground mt-1">High-Speed Fiber Infrastructure & Armed Security Services</p>
              <div className="mt-2 text-[11px] text-muted-foreground space-y-0.5">
                <p>Registration No: 2024/098712/07 | VAT No: 4890281729</p>
                <p>SARS PAYE Ref: 7920194821 | UIF Ref: U19827364 | SDL Ref: L98230192</p>
                <p>Rosebank Link, 187 Oxford Rd, Johannesburg, 2196</p>
              </div>
            </div>

            <div className="sm:text-right flex flex-col justify-between">
              <div>
                <Badge variant="outline" className="text-xs font-semibold uppercase tracking-wider bg-muted/40">
                  Confidential Payslip
                </Badge>
                <p className="text-sm font-bold text-foreground mt-2">Pay Period: September 2026</p>
                <p className="text-xs text-muted-foreground">Pay Date: 2026-09-25</p>
              </div>

              <div className="mt-2">
                <Badge
                  variant="outline"
                  className={
                    isPaid
                      ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-xs"
                      : "border-amber-500/40 text-amber-400 bg-amber-500/10 text-xs"
                  }
                >
                  {isPaid ? "✓ Disbursed (Paystack EFT)" : "Pending Payment Batch"}
                </Badge>
              </div>
            </div>
          </div>

          {/* Employee Information Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs border-b border-border pb-5">
            <div>
              <span className="text-muted-foreground block text-[11px]">Employee Name</span>
              <span className="font-semibold text-sm text-foreground">{payslip.employee_name}</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-[11px]">Staff Code / ID</span>
              <span className="font-medium text-foreground">{payslip.employee_code || "STF-EMP"}</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-[11px]">Job Title</span>
              <span className="font-medium text-foreground">{payslip.job_title}</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-[11px]">Department</span>
              <span className="font-medium text-foreground">{payslip.department}</span>
            </div>

            <div>
              <span className="text-muted-foreground block text-[11px]">SA ID / Passport</span>
              <span className="font-medium text-foreground">{payslip.id_number || "8504125089087"}</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-[11px]">Income Tax Ref (SARS)</span>
              <span className="font-medium text-foreground">{payslip.tax_number || "9823410582"}</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-[11px]">Bank Name & Branch</span>
              <span className="font-medium text-foreground">FNB / RMB (632005)</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-[11px]">Account Number</span>
              <span className="font-medium text-foreground">
                ••••••••{payslip.account_number ? payslip.account_number.slice(-4) : "4892"}
              </span>
            </div>
          </div>

          {/* Earnings & Deductions Two-Column Ledger */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 text-xs">
            {/* Left: Earnings */}
            <div className="space-y-3">
              <div className="border-b border-border pb-1 font-semibold text-foreground flex justify-between">
                <span>EARNINGS & ALLOWANCES</span>
                <span>AMOUNT</span>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-muted-foreground">
                  <span>Basic Monthly Salary</span>
                  <span className="font-medium text-foreground">{zar(payslip.basic_salary)}</span>
                </div>
                {payslip.commission > 0 && (
                  <div className="flex justify-between text-muted-foreground">
                    <span>Attributed Sales Commission</span>
                    <span className="font-medium text-amber-400">{zar(payslip.commission)}</span>
                  </div>
                )}
                {payslip.allowances > 0 && (
                  <div className="flex justify-between text-muted-foreground">
                    <span>Travel / Field Technical Allowance</span>
                    <span className="font-medium text-foreground">{zar(payslip.allowances)}</span>
                  </div>
                )}
              </div>
              <div className="border-t border-border pt-2 flex justify-between font-bold text-foreground">
                <span>GROSS REMUNERATION</span>
                <span>{zar(payslip.gross)}</span>
              </div>
            </div>

            {/* Right: Statutory Deductions */}
            <div className="space-y-3">
              <div className="border-b border-border pb-1 font-semibold text-foreground flex justify-between">
                <span>STATUTORY & OTHER DEDUCTIONS</span>
                <span>AMOUNT</span>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-muted-foreground">
                  <span>SARS PAYE Income Tax</span>
                  <span className="font-medium text-foreground">{zar(payslip.tax)}</span>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <div>
                    <span>UIF Employee Contribution</span>
                    <span className="text-[10px] text-muted-foreground block">(1% capped at R177.12 statutory ceiling)</span>
                  </div>
                  <span className="font-medium text-foreground">{zar(payslip.uif)}</span>
                </div>
                {payslip.other_deductions > 0 && (
                  <div className="flex justify-between text-muted-foreground">
                    <span>Medical Aid / Pension Scheme</span>
                    <span className="font-medium text-foreground">{zar(payslip.other_deductions)}</span>
                  </div>
                )}
              </div>
              <div className="border-t border-border pt-2 flex justify-between font-bold text-foreground">
                <span>TOTAL DEDUCTIONS</span>
                <span className="text-red-400">
                  {zar(payslip.tax + payslip.uif + payslip.other_deductions)}
                </span>
              </div>
            </div>
          </div>

          {/* Employer Statutory Contributions (South African Law) */}
          <div className="rounded-lg border border-border/80 bg-muted/20 p-3 text-xs flex flex-col sm:flex-row justify-between gap-2">
            <div>
              <span className="font-semibold text-foreground block">Employer Statutory Levies & Contributions (Non-deductible):</span>
              <span className="text-muted-foreground text-[11px]">
                Paid directly to SARS by OmniDome Networks under South African labor statutes.
              </span>
            </div>
            <div className="flex gap-4 text-xs font-medium">
              <div>
                <span className="text-muted-foreground">UIF Employer (1%): </span>
                <span className="text-foreground">{zar(payslip.uif_employer || payslip.uif)}</span>
              </div>
              <div>
                <span className="text-muted-foreground">SDL Levy (1%): </span>
                <span className="text-foreground">{zar(payslip.sdl || Math.round(payslip.gross * 0.01))}</span>
              </div>
            </div>
          </div>

          {/* Net Take-Home Pay Box */}
          <div className="rounded-xl border-2 border-emerald-500/50 bg-emerald-500/10 p-5 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div>
              <span className="text-xs uppercase tracking-wider font-semibold text-emerald-400 block">
                Net Take-Home Pay (Bank Credit)
              </span>
              <p className="text-xs text-muted-foreground mt-0.5">
                Calculated strictly under SARS 2024/2025/2026 progressive brackets with annual primary rebate.
              </p>
            </div>
            <div className="text-right">
              <span className="text-3xl font-extrabold text-foreground tracking-tight">
                {zar(payslip.net)}
              </span>
              {payslip.paystack_reference && (
                <span className="text-[10px] text-muted-foreground block font-mono mt-0.5">
                  Ref: {payslip.paystack_reference}
                </span>
              )}
            </div>
          </div>

          {/* Footer certification */}
          <div className="text-[11px] text-muted-foreground text-center border-t border-border pt-4">
            Computer generated document in compliance with Section 33 of the Basic Conditions of Employment Act (BCEA 75 of 1997).
          </div>
        </div>
      </div>
    </div>
  )
}
