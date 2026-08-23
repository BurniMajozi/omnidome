"use client"

/**
 * Payroll Management — demo/onboarding surface for the HR payroll backend.
 * Flow: import a spreadsheet -> searchable roster with inline CRUD -> run payroll.
 * Standalone page (no dashboard sidebar) so it reads as a focused product demo.
 */

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import {
  getRoster, importSpreadsheet, deleteEmployee, setPayroll, createRun, payRun,
  type RosterRow, type ImportResult, type PayRun,
} from "@/lib/payroll-api"

const ZAR = (n: number | null | undefined) =>
  n == null ? "—" : "R " + n.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const TEMPLATE = `employee_id,full_name,job_title,department,hire_date,email,phone,base_salary,bank_code,account_number,account_name
SEC-001,Sipho Mthembu,Security Officer,Guarding,2023-03-14,sipho@example.co.za,0721234501,8500,632005,4071234501,Sipho Mthembu
SEC-002,Lerato Molefe,Site Supervisor,Guarding,2022-07-01,lerato@example.co.za,0721234502,16500,250655,6212345602,Lerato Molefe
`

function thisPeriod(): string {
  // Avoids new Date() at module scope; computed on demand in the browser.
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
}

export default function PayrollPage() {
  const [rows, setRows] = useState<RosterRow[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [createRecipients, setCreateRecipients] = useState(false)
  const [period, setPeriod] = useState("")
  const [running, setRunning] = useState(false)
  const [run, setRun] = useState<PayRun | null>(null)
  const [paying, setPaying] = useState(false)
  const [savingId, setSavingId] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => { setPeriod(thisPeriod()) }, [])

  const load = useCallback(async (q?: string) => {
    setLoading(true)
    setError(null)
    try {
      const res = await getRoster(q)
      setRows(res.items)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Debounced search
  useEffect(() => {
    const t = setTimeout(() => load(search || undefined), 300)
    return () => clearTimeout(t)
  }, [search, load])

  const onImport = async (file: File) => {
    setImporting(true)
    setError(null)
    setImportResult(null)
    try {
      const res = await importSpreadsheet(file, createRecipients)
      setImportResult(res)
      await load(search || undefined)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setImporting(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  const onDownloadTemplate = () => {
    const blob = new Blob([TEMPLATE], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "payroll_template.csv"
    a.click()
    URL.revokeObjectURL(url)
  }

  const onSaveSalary = async (row: RosterRow, value: string) => {
    const salary = Number(value)
    if (!Number.isFinite(salary) || salary === row.base_salary) return
    setSavingId(row.id)
    try {
      await setPayroll(row.id, salary)
      setRows((rs) => rs.map((r) => (r.id === row.id ? { ...r, base_salary: salary } : r)))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingId(null)
    }
  }

  const onDelete = async (row: RosterRow) => {
    if (!confirm(`Remove ${row.full_name}? (marks the employee inactive)`)) return
    try {
      await deleteEmployee(row.id)
      setRows((rs) => rs.filter((r) => r.id !== row.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const onRunPayroll = async () => {
    setRunning(true)
    setError(null)
    setRun(null)
    try {
      const r = await createRun(period)
      setRun(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  const onPayRun = async () => {
    if (!run) return
    if (!confirm("Initiate Paystack transfers for this run? This is the only action that moves money.")) return
    setPaying(true)
    try {
      const r = await payRun(run.id)
      setRun(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setPaying(false)
    }
  }

  const withSalary = rows.filter((r) => r.base_salary != null).length
  const monthlyTotal = rows.reduce((s, r) => s + (r.base_salary ?? 0), 0)

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Payroll Management</h1>
            <p className="text-sm text-muted-foreground">
              Onboard staff from a spreadsheet, manage records, and run payroll with Paystack payouts.
            </p>
          </div>
          <Link href="/dashboard" className="text-sm text-primary hover:underline">← Back to dashboard</Link>
        </div>

        {/* Summary tiles */}
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Tile label="Employees" value={String(rows.length)} />
          <Tile label="With salary set" value={`${withSalary}/${rows.length}`} />
          <Tile label="Monthly payroll" value={ZAR(monthlyTotal)} />
          <Tile label="Bank set" value={String(rows.filter((r) => r.bank_code).length)} />
        </div>

        {/* Import */}
        <section className="mb-6 rounded-xl border bg-card p-5">
          <h2 className="mb-1 text-lg font-medium">1 · Import a spreadsheet</h2>
          <p className="mb-4 text-sm text-muted-foreground">
            CSV or XLSX with a header row. Rows upsert by <code>employee_id</code>. Columns:
            employee_id, full_name, job_title, department, hire_date, email, phone, base_salary,
            bank_code, account_number, account_name.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.xlsx"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) onImport(f) }}
            />
            <Button onClick={() => fileRef.current?.click()} disabled={importing}>
              {importing ? "Importing…" : "Choose file & import"}
            </Button>
            <Button variant="outline" onClick={onDownloadTemplate}>Download template</Button>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input type="checkbox" checked={createRecipients} onChange={(e) => setCreateRecipients(e.target.checked)} />
              Create Paystack payout recipients (slower)
            </label>
          </div>
          {importResult && (
            <div className="mt-4 rounded-lg bg-muted/50 p-3 text-sm">
              <span className="font-medium">Imported:</span>{" "}
              {importResult.created} created, {importResult.updated} updated,{" "}
              {importResult.profiles_set} salaries set
              {importResult.recipients_created > 0 && `, ${importResult.recipients_created} recipients`}
              {" "}(of {importResult.total_rows} rows).
              {importResult.errors.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-destructive">
                  {importResult.errors.slice(0, 6).map((er, i) => (
                    <li key={i}>Row {er.row}: {er.message}</li>
                  ))}
                  {importResult.errors.length > 6 && <li>…and {importResult.errors.length - 6} more</li>}
                </ul>
              )}
            </div>
          )}
        </section>

        {/* Roster */}
        <section className="mb-6 rounded-xl border bg-card p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-medium">2 · Staff & salaries</h2>
            <Input
              placeholder="Search name, ID, or department…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full max-w-xs"
            />
          </div>
          {error && <p className="mb-3 rounded bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">Name</th>
                  <th className="py-2 pr-3 font-medium">Employee ID</th>
                  <th className="py-2 pr-3 font-medium">Department</th>
                  <th className="py-2 pr-3 font-medium">Role</th>
                  <th className="py-2 pr-3 font-medium">Monthly salary</th>
                  <th className="py-2 pr-3 font-medium">Bank</th>
                  <th className="py-2 pr-3 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={7} className="py-8 text-center text-muted-foreground">Loading…</td></tr>
                ) : rows.length === 0 ? (
                  <tr><td colSpan={7} className="py-8 text-center text-muted-foreground">
                    No staff yet — import a spreadsheet above to get started.
                  </td></tr>
                ) : rows.map((r) => (
                  <tr key={r.id} className="border-b last:border-0">
                    <td className="py-2 pr-3 font-medium">{r.full_name}</td>
                    <td className="py-2 pr-3 text-muted-foreground">{r.employee_id}</td>
                    <td className="py-2 pr-3">{r.department}</td>
                    <td className="py-2 pr-3 text-muted-foreground">{r.job_title}</td>
                    <td className="py-2 pr-3">
                      <input
                        type="number"
                        defaultValue={r.base_salary ?? ""}
                        placeholder="set…"
                        disabled={savingId === r.id}
                        className="w-28 rounded border bg-background px-2 py-1 text-right"
                        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur() }}
                        onBlur={(e) => onSaveSalary(r, e.target.value)}
                      />
                    </td>
                    <td className="py-2 pr-3">
                      {r.bank_code ? (
                        <Badge variant={r.has_recipient ? "default" : "secondary"}>
                          {r.account_number_masked ?? r.bank_code}{r.has_recipient ? " ✓" : ""}
                        </Badge>
                      ) : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="py-2 pr-3 text-right">
                      <button onClick={() => onDelete(r)} className="text-xs text-destructive hover:underline">Remove</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">Tip: edit a salary inline — press Enter or click away to save.</p>
        </section>

        {/* Run payroll */}
        <section className="rounded-xl border bg-card p-5">
          <h2 className="mb-4 text-lg font-medium">3 · Run payroll</h2>
          <div className="flex flex-wrap items-center gap-3">
            <Input value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="2026-08" className="w-32" />
            <Button onClick={onRunPayroll} disabled={running || !period}>
              {running ? "Calculating…" : "Generate payslips"}
            </Button>
            {run && (
              <Button variant="outline" onClick={onPayRun} disabled={paying}>
                {paying ? "Paying…" : "Pay via Paystack"}
              </Button>
            )}
          </div>

          {run && (
            <div className="mt-4">
              <div className="mb-3 flex flex-wrap gap-4 text-sm">
                <span>Period <b>{run.period}</b></span>
                <span>Status <Badge variant="secondary">{run.status}</Badge></span>
                <span>Employees <b>{run.employee_count}</b></span>
                <span>Gross <b>{ZAR(run.total_gross)}</b></span>
                <span>Deductions <b>{ZAR(run.total_deductions)}</b></span>
                <span>Net <b>{ZAR(run.total_net)}</b></span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 pr-3 font-medium">Gross</th>
                      <th className="py-2 pr-3 font-medium">PAYE</th>
                      <th className="py-2 pr-3 font-medium">UIF</th>
                      <th className="py-2 pr-3 font-medium">Net</th>
                      <th className="py-2 pr-3 font-medium">Payout</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(run.payslips ?? []).map((p) => (
                      <tr key={p.id} className="border-b last:border-0">
                        <td className="py-2 pr-3">{ZAR(p.gross)}</td>
                        <td className="py-2 pr-3">{ZAR(p.tax)}</td>
                        <td className="py-2 pr-3">{ZAR(p.uif)}</td>
                        <td className="py-2 pr-3 font-medium">{ZAR(p.net)}</td>
                        <td className="py-2 pr-3">
                          <Badge variant={p.payout_status === "PAID" ? "default" : p.payout_status === "FAILED" ? "destructive" : "secondary"}>
                            {p.payout_status}
                          </Badge>
                          {p.payout_message && <span className="ml-2 text-xs text-muted-foreground">{p.payout_message}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  )
}
