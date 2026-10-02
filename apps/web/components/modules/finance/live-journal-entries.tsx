"use client"

import { useEffect, useRef, useState } from "react"
import { Plus, CheckCircle2, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { DataTable, type DataColumn } from "@/components/ui/data-table"
import type { JournalEntry, JournalEntryLineInput } from "@/lib/finance-api"
import { readJournals, readPeriods, writeJournal, journalAction, setAccountingPeriod, type AccountingPeriod } from "./journal-api"
import { useRoles } from "@/lib/use-roles"
import { isFinanceAdmin, isFinanceClerk, isPeriodClosed, periodOf, journalTotals, validJournalLines, journalSourceLabel } from "@/lib/finance-derive"
import { fmtMoney, fmtCents } from "@/lib/money"
import { NotConnected } from "@/components/ui/not-connected"
import type { Loadable } from "@/lib/service-state"

const emptyLine = (): JournalEntryLineInput => ({ account_code: "", account_name: "", debit: 0, credit: 0 })
const today = () => new Date().toISOString().slice(0, 10)

/** Drafts are editable; posted entries are corrected with a posted reversal. */
export function LiveJournalEntries({ onChanged }: { onChanged?: () => void } = {}) {
  const { roles } = useRoles()
  const admin = isFinanceAdmin(roles), clerk = isFinanceClerk(roles)
  const [readState, setReadState] = useState<Loadable<JournalEntry[]>>({ state: "loading" })
  const [periodState, setPeriodState] = useState<Loadable<AccountingPeriod[]>>({ state: "loading" })
  const [entries, setEntries] = useState<JournalEntry[]>([])
  const [entryDate, setEntryDate] = useState(today)
  const [period, setPeriod] = useState(() => today().slice(0, 7))
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [more, setMore] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [description, setDescription] = useState("")
  const [lines, setLines] = useState<JournalEntryLineInput[]>([emptyLine(), emptyLine()])
  const [busyId, setBusyId] = useState<string | null>(null)
  const pending = useRef(false)

  async function refresh() {
    setLoading(true)
    const [journals, periods] = await Promise.all([readJournals(), readPeriods()])
    setReadState(journals); setPeriodState(periods)
    if (journals.state === "ready") { setEntries(journals.data); setMore(journals.data.length === 100) }
    setLoading(false)
  }
  useEffect(() => { void refresh() }, [])
  const periodRows = periodState.state === "ready" ? periodState.data : null
  const totals = journalTotals(lines)
  const balanced = validJournalLines(lines)
  const locked = (date: string) => isPeriodClosed(periodRows, periodOf(date))
  // The backend uses date.today() on its service host (UTC in the deployment).
  const reversalLocked = !periodRows || locked(today())
  const reversedIds = new Set(entries.filter(e => e.source === "finance.reversal").map(e => e.source_id))

  async function mutate(id: string, action: () => ReturnType<typeof journalAction>) {
    if (pending.current) return
    pending.current = true; setBusyId(id); setMessage(null)
    try {
      const result = await action()
      if (!result.ok) { setMessage(result.message ?? "Action failed"); return }
      const status = (result.data as { status?: string } | null)?.status
      setMessage(status === "duplicate" ? "Already recorded; no duplicate created." : "Saved successfully.")
      if (id === "create") { setCreateOpen(false); setDescription(""); setLines([emptyLine(), emptyLine()]) }
      await refresh(); onChanged?.()
    } finally { pending.current = false; setBusyId(null) }
  }
  async function handleCreate() {
    if (!clerk || !balanced || !entryDate) return
    await mutate("create", () => writeJournal({ description, entry_date: entryDate, source: "MANUAL", lines }))
  }
  async function handlePost(entry: JournalEntry) {
    if (!admin || !periodRows || locked(entry.entry_date)) return
    await mutate(entry.id, () => journalAction(entry.id, "post"))
  }
  async function handleDelete(entry: JournalEntry) {
    if (!clerk || entry.is_posted) return
    await mutate(entry.id, () => journalAction(entry.id, "delete"))
  }
  async function handleReverse(entry: JournalEntry) {
    if (!admin || !entry.is_posted || reversalLocked || reversedIds.has(entry.id)) return
    if (window.confirm(`Post a reversal of ${entry.reference ?? entry.id} dated today? The original remains posted.`))
      await mutate(entry.id, () => journalAction(entry.id, "reverse"))
  }
  async function loadMore() {
    setLoading(true)
    const result = await readJournals(entries.length)
    if (result.state === "ready") { setEntries(old => [...old, ...result.data]); setMore(result.data.length === 100) }
    else setMessage("Could not load more entries. Existing rows are retained.")
    setLoading(false)
  }
  const columns: DataColumn<JournalEntry>[] = [
    { key: "reference", label: "Reference" },
    { key: "entry_date", label: "Date" },
    { key: "description", label: "Description" },
    { key: "source", label: "Source", render: row => journalSourceLabel(row.source) },
    { key: "total_debit", label: "Debit", align: "right", render: row => fmtMoney(row.total_debit) },
    { key: "total_credit", label: "Credit", align: "right", render: row => fmtMoney(row.total_credit) },
    { key: "is_posted", label: "Status", render: row => <Badge variant={row.is_posted ? "default" : "outline"}>{reversedIds.has(row.id) ? "posted / reversed" : row.is_posted ? "posted" : "draft"}</Badge> },
    { key: "actions", label: "", render: row => <div className="flex gap-1 justify-end">
      {!row.is_posted && clerk && <>
        {admin && <Button size="sm" variant="outline" disabled={!!busyId || !periodRows || locked(row.entry_date)} onClick={() => handlePost(row)}><CheckCircle2 className="h-3.5 w-3.5 mr-1" />Post</Button>}
        <Button size="sm" variant="ghost" disabled={!!busyId} aria-label="Delete draft" onClick={() => handleDelete(row)}><Trash2 className="h-3.5 w-3.5" /></Button>
      </>}
      {row.is_posted && admin && <Button size="sm" variant="outline" disabled={!!busyId || reversalLocked || reversedIds.has(row.id)} onClick={() => handleReverse(row)}>Reverse today</Button>}
      {periodRows && locked(row.entry_date) && <Badge variant="outline">Period locked</Badge>}
    </div> },
  ]
  return <div className="surface-card p-6 mt-4">
    <div className="flex items-center justify-between mb-4">
      <div><h4 className="card-title">Journal Entries (live)</h4><p className="text-sm text-muted-foreground">References are generated by the server. Posted entries are immutable.</p></div>
      <Button size="sm" disabled={!clerk || !!busyId} title="Draft creation requires a finance clerk or admin" onClick={() => setCreateOpen(true)}><Plus className="h-3.5 w-3.5 mr-1" />New Entry</Button>
    </div>
    {message && <p role="status" className="text-sm mb-3">{message}</p>}
    {periodState.state !== "ready" ? <NotConnected loadable={periodState} service="Finance period locks" onRetry={refresh} /> : <div className="flex flex-wrap gap-2 items-center mb-4">
      <Label htmlFor="accounting-period">Accounting period</Label>
      <Input id="accounting-period" type="month" className="w-44" value={period} onChange={e => setPeriod(e.target.value)} />
      <Badge variant="outline">{isPeriodClosed(periodRows, period) ? "Closed" : "Open"}</Badge>
      {admin && <Button size="sm" variant="outline" disabled={!!busyId || !periodOf(period)} onClick={() => {
        if (!admin || !periodOf(period)) return
        const action = isPeriodClosed(periodRows, period) ? "reopen" : "close"
        if (window.confirm(`${action === "close" ? "Lock" : "Reopen"} ${period}?`)) void mutate("period", () => setAccountingPeriod(period, action))
      }}>{isPeriodClosed(periodRows, period) ? "Reopen period" : "Close period"}</Button>}
    </div>}
    {readState.state !== "ready" ? <NotConnected loadable={readState} service="Finance journals" onRetry={refresh} /> : <DataTable columns={columns} rows={entries} loading={loading} emptyTitle="No journal entries yet" />}
    {more && <Button variant="outline" disabled={loading || !!busyId} onClick={loadMore}>Load more journals</Button>}
    <p className="text-xs text-muted-foreground mt-2">Showing {entries.length} entries{more ? "; more may be available" : ""}. Reversal status covers loaded entries only. Reversals post today; the server validates its accounting period.</p>
    <Dialog open={createOpen} onOpenChange={open => { if (!busyId) setCreateOpen(open) }}>
      <DialogContent className="max-w-lg"><DialogHeader><DialogTitle>New Journal Entry</DialogTitle></DialogHeader>
        <div className="space-y-3">
          {message && <p role="status">{message}</p>}
          <Label htmlFor="journal-date">Entry date</Label><Input id="journal-date" type="date" value={entryDate} onChange={e => setEntryDate(e.target.value)} />
          {locked(entryDate) && <p className="text-sm text-muted-foreground">Drafts may be created in this closed period; posting is blocked.</p>}
          <div><Label>Description</Label><Input value={description} onChange={e => setDescription(e.target.value)} /></div>
          <div className="space-y-2"><Label>Lines (debits must equal credits)</Label>
              {lines.map((line, i) => (
                <div key={i} className="grid grid-cols-4 gap-2">
                  <Input
                    placeholder="Acct code"
                    value={line.account_code}
                    onChange={(e) => {
                      const next = [...lines]; next[i] = { ...line, account_code: e.target.value }; setLines(next)
                    }}
                  />
                  <Input
                    placeholder="Acct name"
                    value={line.account_name}
                    onChange={(e) => {
                      const next = [...lines]; next[i] = { ...line, account_name: e.target.value }; setLines(next)
                    }}
                  />
                  <Input
                    type="number" min="0" step="0.01" placeholder="Debit"
                    value={line.debit || ""}
                    onChange={(e) => {
                      const next = [...lines]; next[i] = { ...line, debit: Number(e.target.value), credit: 0 }; setLines(next)
                    }}
                  />
                  <Input
                    type="number" min="0" step="0.01" placeholder="Credit"
                    value={line.credit || ""}
                    onChange={(e) => {
                      const next = [...lines]; next[i] = { ...line, credit: Number(e.target.value), debit: 0 }; setLines(next)
                    }}
                  />
                </div>
              ))}
              <Button size="sm" variant="ghost" onClick={() => setLines([...lines, emptyLine()])}>
                <Plus className="h-3.5 w-3.5 mr-1" /> Add line
              </Button>
              <p className={`text-sm ${balanced ? "text-emerald-500" : "text-destructive"}`}>
                Debit {fmtCents(totals.debit)} / Credit {fmtCents(totals.credit)} {balanced ? "✓ balanced" : "— must balance"}
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button disabled={!clerk || !balanced || !entryDate || !!busyId} onClick={handleCreate}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
}
