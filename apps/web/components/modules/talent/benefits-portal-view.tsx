"use client"

import React, { useState } from "react"
import {
  Gift,
  Heart,
  Shield,
  CreditCard,
  Plus,
  Trash2,
  CheckCircle2,
  MessageSquare,
  Phone,
  HelpCircle,
  FileText,
  UserCheck,
  TrendingUp,
  AlertCircle,
  Save,
  Clock,
  Sparkles,
  ExternalLink,
} from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import type { Employee } from "@/lib/hr-api"

interface BenefitsPortalViewProps {
  employees: Employee[]
}

interface Beneficiary {
  id: string
  name: string
  relationship: string
  idNumber: string
  sharePercent: number
}

export function BenefitsPortalView({ employees }: BenefitsPortalViewProps) {
  const [selectedEmpId, setSelectedEmpId] = useState<string>(employees[0]?.id || "")
  const [activeTab, setActiveTab] = useState<"provident" | "medical" | "funeral" | "care_corner">("provident")
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // Provident Fund State
  const [providentRate, setProvidentRate] = useState<string>("7.5")
  const [beneficiaries, setBeneficiaries] = useState<Beneficiary[]>([
    { id: "1", name: "Nandi Sithole", relationship: "Spouse", idNumber: "910514 0293 081", sharePercent: 70 },
    { id: "2", name: "Bandile Sithole", relationship: "Child", idNumber: "150822 5819 084", sharePercent: 30 },
  ])

  // Medical Aid State
  const [medicalScheme, setMedicalScheme] = useState<string>("Discovery Health Classic Comprehensive")
  const [dependentsCount, setDependentsCount] = useState<number>(2)
  const [gapCover, setGapCover] = useState<boolean>(true)

  // Funeral Cover State
  const [funeralTier, setFuneralTier] = useState<string>("Tier 2 - R50,000")
  const [extendedFamilyCover, setExtendedFamilyCover] = useState<boolean>(true)

  // Care Corner Advice Form State
  const [adviceTopic, setAdviceTopic] = useState<string>("Pension Fund Planning")
  const [adviceMessage, setAdviceMessage] = useState<string>("")
  const [adviceSubmitted, setAdviceSubmitted] = useState<boolean>(false)

  const selectedEmp = employees.find((e) => e.id === selectedEmpId) || employees[0]

  const totalSharePercent = beneficiaries.reduce((sum, b) => sum + b.sharePercent, 0)

  const handleAddBeneficiary = () => {
    setBeneficiaries((prev) => [
      ...prev,
      {
        id: String(Date.now()),
        name: "New Beneficiary",
        relationship: "Child",
        idNumber: "",
        sharePercent: 0,
      },
    ])
  }

  const handleRemoveBeneficiary = (id: string) => {
    setBeneficiaries((prev) => prev.filter((b) => b.id !== id))
  }

  const handleUpdateBeneficiary = (id: string, field: keyof Beneficiary, value: string | number) => {
    setBeneficiaries((prev) =>
      prev.map((b) => (b.id === id ? { ...b, [field]: value } : b))
    )
  }

  const handleSaveBenefits = (section: string) => {
    if (section === "Provident Fund" && totalSharePercent !== 100) {
      alert(`Beneficiary allocation must total exactly 100%. Currently at ${totalSharePercent}%.`)
      return
    }
    setToastMessage(`${section} preferences updated successfully for ${selectedEmp?.full_name}!`)
    setTimeout(() => setToastMessage(null), 3500)
  }

  const handleSubmitCareAdvice = (e: React.FormEvent) => {
    e.preventDefault()
    setAdviceSubmitted(true)
    setToastMessage("Confidential request sent to Employee Care Corner. An advisor will contact you within 24 hours.")
    setTimeout(() => {
      setToastMessage(null)
      setAdviceSubmitted(false)
      setAdviceMessage("")
    }, 4000)
  }

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-950/90 px-4 py-3 text-sm text-emerald-200 shadow-xl backdrop-blur">
          <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Banner */}
      <div className="rounded-xl border border-border bg-card/60 p-5 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-primary/40 bg-primary/10 text-primary">
              <Gift className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-foreground">Benefits & Care Corner</h2>
                <Badge variant="outline" className="border-primary/40 text-primary bg-primary/10 text-[10px] font-semibold">
                  Employee Self-Service
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Provident fund management, medical aid scheme options, funeral covers, beneficiaries editing, and confidential care advisory.
              </p>
            </div>
          </div>

          {/* Employee Selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground shrink-0">Managing For:</span>
            <select
              value={selectedEmpId}
              onChange={(e) => setSelectedEmpId(e.target.value)}
              className="h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-medium"
            >
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.full_name} ({emp.department} — {emp.job_title})
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border pb-2 text-xs">
        {[
          { id: "provident", label: "Provident Fund & Beneficiaries" },
          { id: "medical", label: "Medical Aid & Gap Cover" },
          { id: "funeral", label: "Group Life & Funeral Schemes" },
          { id: "care_corner", label: "Employee Care Corner (Advice)" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
              activeTab === tab.id
                ? "bg-primary/15 text-primary border border-primary/30"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── TAB 1: Provident Fund & Beneficiaries ─────────────────────── */}
      {activeTab === "provident" && (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-3">
            {/* Contribution Settings */}
            <Card className="border-border lg:col-span-1">
              <CardHeader className="pb-3 border-b border-border/60">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-emerald-400" /> Provident Fund Contributions
                </CardTitle>
                <CardDescription className="text-xs">
                  Retirement annuity & employer matching tier.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-4 space-y-4 text-xs">
                <div className="space-y-1.5">
                  <label className="font-medium text-foreground">Employee Contribution Rate</label>
                  <select
                    value={providentRate}
                    onChange={(e) => setProvidentRate(e.target.value)}
                    className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value="5.0">5.0% of Basic Salary</option>
                    <option value="7.5">7.5% of Basic Salary (Standard Matching)</option>
                    <option value="10.0">10.0% of Basic Salary</option>
                    <option value="15.0">15.0% of Basic Salary (Maximum Pre-Tax)</option>
                  </select>
                </div>

                <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-1.5">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Employer Match:</span>
                    <span className="font-semibold text-foreground">{providentRate}% Matching</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Fund Administrator:</span>
                    <span className="font-semibold text-foreground">Sanlam Corporate Umbrella</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">SARS Section 10C:</span>
                    <span className="text-emerald-400 font-semibold">Tax-Deductible</span>
                  </div>
                </div>

                <Button
                  size="sm"
                  variant="default"
                  className="w-full text-xs"
                  onClick={() => handleSaveBenefits("Provident Fund")}
                >
                  <Save className="h-3.5 w-3.5 mr-1.5" /> Save Contribution Rate
                </Button>
              </CardContent>
            </Card>

            {/* Beneficiaries Manager */}
            <Card className="border-border lg:col-span-2">
              <CardHeader className="pb-3 border-b border-border/60 flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <Heart className="h-4 w-4 text-primary" /> Pension & Death Benefit Beneficiaries
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Statutory Section 37C Pension Funds Act nomination of dependents. Must equal 100%.
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className={
                      totalSharePercent === 100
                        ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
                        : "border-red-500/40 text-red-400 bg-red-500/10"
                    }
                  >
                    Total: {totalSharePercent}% / 100%
                  </Badge>
                  <Button size="sm" variant="outline" className="h-7 text-xs" onClick={handleAddBeneficiary}>
                    <Plus className="h-3 w-3 mr-1" /> Add
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="p-4 space-y-3 text-xs">
                {beneficiaries.map((b) => (
                  <div
                    key={b.id}
                    className="flex flex-col sm:flex-row items-center gap-3 rounded-lg border border-border/80 bg-background/50 p-3"
                  >
                    <div className="w-full sm:w-1/3 space-y-1">
                      <label className="text-[10px] text-muted-foreground font-medium">Beneficiary Name</label>
                      <Input
                        value={b.name}
                        onChange={(e) => handleUpdateBeneficiary(b.id, "name", e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="w-full sm:w-1/4 space-y-1">
                      <label className="text-[10px] text-muted-foreground font-medium">Relationship</label>
                      <select
                        value={b.relationship}
                        onChange={(e) => handleUpdateBeneficiary(b.id, "relationship", e.target.value)}
                        className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs text-foreground"
                      >
                        <option value="Spouse">Spouse</option>
                        <option value="Child">Child</option>
                        <option value="Parent">Parent</option>
                        <option value="Sibling">Sibling</option>
                        <option value="Trust">Family Trust</option>
                      </select>
                    </div>
                    <div className="w-full sm:w-1/4 space-y-1">
                      <label className="text-[10px] text-muted-foreground font-medium">RSA ID / DOB</label>
                      <Input
                        placeholder="890412..."
                        value={b.idNumber}
                        onChange={(e) => handleUpdateBeneficiary(b.id, "idNumber", e.target.value)}
                        className="h-8 text-xs font-mono"
                      />
                    </div>
                    <div className="w-full sm:w-20 space-y-1">
                      <label className="text-[10px] text-muted-foreground font-medium">Share (%)</label>
                      <Input
                        type="number"
                        min={0}
                        max={100}
                        value={b.sharePercent}
                        onChange={(e) => handleUpdateBeneficiary(b.id, "sharePercent", Number(e.target.value))}
                        className="h-8 text-xs font-bold text-primary"
                      />
                    </div>
                    <div className="sm:pt-4">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 w-8 p-0 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                        onClick={() => handleRemoveBeneficiary(b.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}

                <div className="flex justify-end pt-2">
                  <Button size="sm" variant="default" onClick={() => handleSaveBenefits("Beneficiaries")}>
                    <Save className="h-3.5 w-3.5 mr-1.5" /> Save Beneficiary Allocations
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* ── TAB 2: Medical Aid Schemes ─────────────────────────────────── */}
      {activeTab === "medical" && (
        <div className="grid gap-6 lg:grid-cols-2 text-xs">
          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <CardTitle className="text-base flex items-center gap-2">
                <Shield className="h-4 w-4 text-cyan-400" /> Medical Aid Plan Selection
              </CardTitle>
              <CardDescription className="text-xs">
                Company-subsidized medical health schemes with payroll deduction integration.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              <div className="space-y-1.5">
                <label className="font-medium text-foreground">Select Scheme & Option</label>
                <select
                  value={medicalScheme}
                  onChange={(e) => setMedicalScheme(e.target.value)}
                  className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground font-medium"
                >
                  <option value="Discovery Health Classic Comprehensive">Discovery Health Classic Comprehensive (Top Tier)</option>
                  <option value="Discovery Health Essential Delta">Discovery Health Essential Delta (Network Hospitals)</option>
                  <option value="Discovery Health Coastal Core">Discovery Health Coastal Core (Hospital Plan)</option>
                  <option value="Momentum Custom Option">Momentum Custom Option (Flexible Savings)</option>
                  <option value="Opt-Out">Opt-Out / Private Policy</option>
                </select>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="font-medium text-foreground">Registered Dependents</label>
                  <select
                    value={dependentsCount}
                    onChange={(e) => setDependentsCount(Number(e.target.value))}
                    className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value={0}>Principal Member Only</option>
                    <option value={1}>Principal + 1 Dependent</option>
                    <option value={2}>Principal + 2 Dependents</option>
                    <option value={3}>Principal + 3 Dependents</option>
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="font-medium text-foreground">Gap Cover Policy</label>
                  <select
                    value={gapCover ? "YES" : "NO"}
                    onChange={(e) => setGapCover(e.target.value === "YES")}
                    className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value="YES">Enrolled (500% Tariff Shortfall Cover)</option>
                    <option value="NO">Declined Gap Cover</option>
                  </select>
                </div>
              </div>

              <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-1 text-muted-foreground">
                <p>Company Contribution: <span className="text-foreground font-semibold">50% subsidy up to R 3,500/mo</span></p>
                <p>Medical Tax Credits: <span className="text-emerald-400 font-semibold">Section 6A & 6B applied on Payslip</span></p>
              </div>

              <Button size="sm" variant="default" onClick={() => handleSaveBenefits("Medical Aid Scheme")}>
                <Save className="h-3.5 w-3.5 mr-1.5" /> Update Medical Aid Plan
              </Button>
            </CardContent>
          </Card>

          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <CardTitle className="text-base flex items-center gap-2">
                <FileText className="h-4 w-4 text-primary" /> Scheme Hospital Network & Benefits
              </CardTitle>
              <CardDescription className="text-xs">
                Key coverage limits for {medicalScheme}.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4 space-y-3 text-muted-foreground">
              <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                <p className="font-semibold text-foreground">In-Hospital Treatment</p>
                <p>100% of Discovery Health Rate at private hospitals nationwide. Unlimited overall annual limit.</p>
              </div>
              <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                <p className="font-semibold text-foreground">Chronic Illness Benefit (CIB)</p>
                <p>Covers 27 Prescribed Minimum Benefit (PMB) conditions including asthma, hypertension, and diabetes.</p>
              </div>
              <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                <p className="font-semibold text-foreground">Day-to-Day Medical Savings Account</p>
                <p>Allocated 25% of annual contribution for GP visits, optical, dental, and prescription medicine.</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── TAB 3: Funeral Covers ─────────────────────────────────────── */}
      {activeTab === "funeral" && (
        <div className="grid gap-6 lg:grid-cols-2 text-xs">
          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <CardTitle className="text-base flex items-center gap-2">
                <Shield className="h-4 w-4 text-violet-400" /> Group Life & Funeral Scheme
              </CardTitle>
              <CardDescription className="text-xs">
                Immediate 24-hour claim settlement for employee and family.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              <div className="space-y-1.5">
                <label className="font-medium text-foreground">Select Funeral Benefit Tier</label>
                <select
                  value={funeralTier}
                  onChange={(e) => setFuneralTier(e.target.value)}
                  className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground font-medium"
                >
                  <option value="Tier 1 - R30,000">Tier 1 - R30,000 (Principal + Spouse)</option>
                  <option value="Tier 2 - R50,000">Tier 2 - R50,000 (Comprehensive Family)</option>
                  <option value="Tier 3 - R100,000">Tier 3 - R100,000 (Executive Extended Family)</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="font-medium text-foreground">Extended Family Rider (Parents & In-Laws)</label>
                <select
                  value={extendedFamilyCover ? "YES" : "NO"}
                  onChange={(e) => setExtendedFamilyCover(e.target.value === "YES")}
                  className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                >
                  <option value="YES">Cover Included (Up to 4 Parents Covered at R20,000 each)</option>
                  <option value="NO">No Extended Family Cover</option>
                </select>
              </div>

              <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-1 text-muted-foreground">
                <p>Repatriation Service: <span className="text-emerald-400 font-semibold">Included (SADC region)</span></p>
                <p>Waiting Period: <span className="text-foreground font-semibold">Waived for full-time staff</span></p>
              </div>

              <Button size="sm" variant="default" onClick={() => handleSaveBenefits("Funeral Cover Tier")}>
                <Save className="h-3.5 w-3.5 mr-1.5" /> Save Funeral Preferences
              </Button>
            </CardContent>
          </Card>

          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <CardTitle className="text-base flex items-center gap-2">
                <FileText className="h-4 w-4 text-cyan-400" /> Group Life Assurance (GLA) Policy
              </CardTitle>
              <CardDescription className="text-xs">
                Employer-funded life protection for dependents.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4 space-y-3 text-muted-foreground">
              <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                <p className="font-semibold text-foreground">Lump Sum Death Benefit</p>
                <p>3x Annual Basic Salary paid out to nominated beneficiaries upon death in service.</p>
              </div>
              <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                <p className="font-semibold text-foreground">Total & Permanent Disability (Disability Income)</p>
                <p>75% of monthly salary paid up to retirement age in the event of incapacitation or injury.</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── TAB 4: Employee Care Corner ───────────────────────────────── */}
      {activeTab === "care_corner" && (
        <div className="grid gap-6 lg:grid-cols-2 text-xs">
          {/* Advice Request Form */}
          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <CardTitle className="text-base flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-primary" /> Confidential Benefits Advisory
              </CardTitle>
              <CardDescription className="text-xs">
                Speak directly with an accredited financial planner or HR benefits advisor.
              </CardDescription>
            </CardHeader>
            <form onSubmit={handleSubmitCareAdvice}>
              <CardContent className="p-4 space-y-4">
                <div className="space-y-1.5">
                  <label className="font-medium text-foreground">Consultation Topic</label>
                  <select
                    value={adviceTopic}
                    onChange={(e) => setAdviceTopic(e.target.value)}
                    className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    <option value="Pension Fund Planning">Pension & Retirement Annuity Planning</option>
                    <option value="Medical Scheme Selection">Choosing the Right Medical Aid Scheme</option>
                    <option value="Debt & Financial Wellness">Debt Consolidation & Financial Wellness</option>
                    <option value="Estate & Wills Advice">Will Drafting & Beneficiaries Counseling</option>
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="font-medium text-foreground">Confidential Note / Query</label>
                  <Textarea
                    required
                    placeholder="Tell us what you would like advice on (e.g. adding my new spouse to medical aid, tax implications of increasing my pension)..."
                    value={adviceMessage}
                    onChange={(e) => setAdviceMessage(e.target.value)}
                    rows={4}
                    className="text-xs"
                  />
                </div>

                <div className="flex items-center gap-2 text-muted-foreground text-[11px]">
                  <Shield className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
                  <span>Your enquiry is 100% confidential under POPIA and will not be disclosed to supervisors.</span>
                </div>

                <Button type="submit" size="sm" variant="default" className="w-full">
                  Book Care Consultation
                </Button>
              </CardContent>
            </form>
          </Card>

          {/* Crisis Hotline & Wellness Resources */}
          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <CardTitle className="text-base flex items-center gap-2">
                <Phone className="h-4 w-4 text-emerald-400" /> 24/7 Wellness & ICAS Hotline
              </CardTitle>
              <CardDescription className="text-xs">
                Toll-free mental health, counseling, and legal advice hotlines available to all OmniDome staff.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4 space-y-3">
              <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-foreground">Employee Assistance Programme (ICAS)</p>
                  <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">24/7 Free</Badge>
                </div>
                <p className="text-muted-foreground">Toll-free counseling in 11 official South African languages.</p>
                <p className="font-mono font-bold text-foreground">0800 21 21 21</p>
              </div>

              <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-foreground">SADAG Mental Health Helpline</p>
                  <Badge variant="outline" className="border-primary/40 text-primary">Anonymous</Badge>
                </div>
                <p className="text-muted-foreground">Suicide crisis and high-stress support line.</p>
                <p className="font-mono font-bold text-foreground">0800 567 567</p>
              </div>

              <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-foreground">Legal & Financial Wellness Hotline</p>
                  <Badge variant="outline" className="border-cyan-500/40 text-cyan-400">Accredited</Badge>
                </div>
                <p className="text-muted-foreground">Free telephonic consultation with admitted attorneys and CFPs.</p>
                <p className="font-mono font-bold text-foreground">0800 33 44 55</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
