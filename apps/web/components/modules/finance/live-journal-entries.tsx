"use client"

import { useEffect, useState } from "react"
import { Plus, CheckCircle2, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { DataTable, type DataColumn } from "@/components/ui/data-table"
import {
  type JournalEntry,
  type JournalEntryLineInput,
  listJournalEntries,
  createJournalEntry,
  postJournalEntry,
  deleteJournalEntry,
} from "@/lib/finance-api"

function formatZar(value: number) {
  return `R ${value.toLocaleString("en-ZA", { minimumFractionDigits: 2 })}`
}

const emptyLine = (): JournalEntryLineInput => ({ account_code: "", account_name: "", debit: 0, credit: 0 })

/**
 * Live GL journal entries backed by the finance service — reference numbers
 * are auto-generated server-side (JE-<TENANT4>-<seq>), debits must equal
 * credits, and posted entries become immutable. Appended alongside the
 * existing mock Journals & Trial Balance panel rather than replacing it.
 */
export function LiveJournalEntries() {
  const [entries, setEntries] = useState<JournalEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [description, setDescription] = useState("")
  const [lines, setLines] = useState<JournalEntryLineInput[]>([emptyLine(), emptyLine()])
  const [busyId, setBusyId] = useState<string | null>(null)

  async function refresh() {
    setLoading(true)
    setEntries(await listJournalEntries())
    setLoading(false)
  }

  useEffect(() => {
    refresh()
  }, [])

  const totalDebit = lines.reduce((s, l) => s + (Number(l.debit) || 0), 0)
  const totalCredit = lines.reduce((s, l) => s + (Number(l.credit) || 0), 0)
  const balanced = Math.abs(totalDebit - totalCredit) < 0.01 && totalDebit > 0

  async function handleCreate() {
    if (!balanced) return
    const created = await createJournalEntry({
      description,
      source: "MANUAL",
      lines: lines.filter((l) => l.account_code),
    })
    if (created) {
      setCreateOpen(false)
      setDescription("")
      setLines([emptyLine(), emptyLine()])
      await refresh()
    }
  }

  async function handlePost(entry: JournalEntry) {
    setBusyId(entry.id)
    await postJournalEntry(entry.id)
    await refresh()
    setBusyId(null)
  }

  async function handleDelete(entry: JournalEntry) {
    setBusyId(entry.id)
    await deleteJournalEntry(entry.id)
    await refresh()
    setBusyId(null)
  }

  const columns: DataColumn<JournalEntry>[] = [
    { key: "reference", label: "Reference" },
    { key: "entry_date", label: "Date" },
    { key: "description", label: "Description" },
    { key: "source", label: "Source", render: (row) => row.source ?? "—" },
    { key: "total_debit", label: "Debit", align: "right", render: (row) => formatZar(row.total_debit) },
    { key: "total_credit", label: "Credit", align: "right", render: (row) => formatZar(row.total_credit) },
    {
      key: "is_posted",
      label: "Status",
      render: (row) => <Badge variant={row.is_posted ? "default" : "outline"}>{row.is_posted ? "posted" : "draft"}</Badge>,
    },
    {
      key: "actions",
      label: "",
      render: (row) => (
        <div className="flex gap-1 justify-end">
          {!row.is_posted && (
            <>
              <Button size="sm" variant="outline" disabled={busyId === row.id} onClick={() => handlePost(row)}>
                <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Post
              </Button>
              <Button size="sm" variant="ghost" disabled={busyId === row.id} onClick={() => handleDelete(row)}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </>
          )}
        </div>
      ),
    },
  ]

  return (
    <div className="surface-card p-6 mt-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h4 className="card-title">Journal Entries (live)</h4>
          <p className="text-sm text-muted-foreground">
            References auto-generated server-side. Posted entries are immutable; deleting is a soft-delete.
          </p>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-3.5 w-3.5 mr-1" /> New Entry
        </Button>
      </div>

      <DataTable columns={columns} rows={entries} loading={loading} emptyTitle="No journal entries yet" />

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>New Journal Entry</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Description</Label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Lines (debits must equal credits)</Label>
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
                    type="number" placeholder="Debit"
                    value={line.debit || ""}
                    onChange={(e) => {
                      const next = [...lines]; next[i] = { ...line, debit: Number(e.target.value), credit: 0 }; setLines(next)
                    }}
                  />
                  <Input
                    type="number" placeholder="Credit"
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
                Debit {formatZar(totalDebit)} / Credit {formatZar(totalCredit)} {balanced ? "✓ balanced" : "— must balance"}
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button disabled={!balanced} onClick={handleCreate}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
