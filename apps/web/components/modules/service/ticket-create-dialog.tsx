"use client"

import { useEffect, useRef, useState } from "react"
import { Loader2, Search, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { loadCustomers, type CustomerListItem } from "@/lib/crm-api"
import { supportApi, type Assignee, type Ticket, type TicketMeta } from "@/lib/support-api"
import { CATEGORY_LABELS, SOURCE_LABELS, labelOf } from "@/lib/support-derive"

const FIELD = "h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
const CREATABLE_SOURCES = ["manual", "email", "call_center"]

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  meta: TicketMeta | null
  assignees: Assignee[]
  onCreated: (ticket: Ticket) => void
}

/** Create a ticket by hand: subject, description, category, priority, source, queue, customer and assignee. */
export function TicketCreateDialog({ open, onOpenChange, meta, assignees, onCreated }: Props) {
  const [subject, setSubject] = useState("")
  const [description, setDescription] = useState("")
  const [category, setCategory] = useState("GENERAL")
  const [priority, setPriority] = useState("NORMAL")
  const [source, setSource] = useState("manual")
  const [queue, setQueue] = useState("")
  const [assignee, setAssignee] = useState("")
  const [customer, setCustomer] = useState<CustomerListItem | null>(null)
  const [customerQuery, setCustomerQuery] = useState("")
  const [customerHits, setCustomerHits] = useState<CustomerListItem[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const seq = useRef(0)

  useEffect(() => {
    if (open) {
      setSubject("")
      setDescription("")
      setCategory("GENERAL")
      setPriority("NORMAL")
      setSource("manual")
      setQueue("")
      setAssignee("")
      setCustomer(null)
      setCustomerQuery("")
      setCustomerHits(null)
      setError(null)
    }
  }, [open])

  // Debounced customer lookup against the CRM (tenant-scoped by the edge identity).
  useEffect(() => {
    const term = customerQuery.trim()
    if (term.length < 2 || customer) {
      setCustomerHits(null)
      return
    }
    const mine = ++seq.current
    setSearching(true)
    const t = setTimeout(async () => {
      const res = await loadCustomers({ search: term, pageSize: 6 }, true)
      if (mine !== seq.current) return
      setCustomerHits(res.state === "ready" ? res.data.items : [])
      setSearching(false)
    }, 250)
    return () => clearTimeout(t)
  }, [customerQuery, customer])

  const submit = async () => {
    if (!subject.trim()) {
      setError("Give the ticket a subject")
      return
    }
    setBusy(true)
    setError(null)
    try {
      const ticket = await supportApi.create({
        subject: subject.trim(),
        description: description.trim(),
        category,
        priority,
        source,
        queue: queue || null,
        customer_id: customer?.id ?? null,
        assigned_to: assignee || null,
      })
      onCreated(ticket)
      onOpenChange(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the ticket")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New ticket</DialogTitle>
          <DialogDescription>Log a customer issue or internal task. Its SLA clock starts when you create it.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="tk-subject">Subject</Label>
            <Input id="tk-subject" value={subject} maxLength={200} onChange={(e) => setSubject(e.target.value)} placeholder="e.g. Router keeps rebooting at night" autoFocus />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="tk-desc">Description</Label>
            <Textarea id="tk-desc" rows={4} value={description} maxLength={5000} onChange={(e) => setDescription(e.target.value)} placeholder="What happened, what the customer sees, anything already tried" />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="tk-category">Category</Label>
              <select id="tk-category" className={FIELD} value={category} onChange={(e) => setCategory(e.target.value)}>
                {(meta?.categories ?? ["GENERAL"]).map((c) => (
                  <option key={c} value={c}>{labelOf(CATEGORY_LABELS, c)}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tk-priority">Priority</Label>
              <select id="tk-priority" className={FIELD} value={priority} onChange={(e) => setPriority(e.target.value)}>
                {(meta?.priorities ?? ["LOW", "NORMAL", "HIGH", "URGENT"]).map((p) => (
                  <option key={p} value={p}>
                    {labelOf({}, p)}{meta?.sla_hours?.[p] ? ` (${meta.sla_hours[p]}h SLA)` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tk-source">Raised via</Label>
              <select id="tk-source" className={FIELD} value={source} onChange={(e) => setSource(e.target.value)}>
                {CREATABLE_SOURCES.map((s) => (
                  <option key={s} value={s}>{labelOf(SOURCE_LABELS, s)}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tk-queue">Queue</Label>
              <select id="tk-queue" className={FIELD} value={queue} onChange={(e) => setQueue(e.target.value)}>
                <option value="">No queue</option>
                {(meta?.queues ?? []).map((q) => (
                  <option key={q} value={q}>{labelOf({}, q)}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="tk-assignee">Assign to</Label>
              <select id="tk-assignee" className={FIELD} value={assignee} onChange={(e) => setAssignee(e.target.value)}>
                <option value="">Unassigned</option>
                {assignees.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}{a.id === meta?.user_id ? " (me)" : ""}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="tk-customer">Customer / account (optional)</Label>
            {customer ? (
              <div className="flex items-center justify-between rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
                <span>
                  {customer.first_name} {customer.last_name}
                  {customer.account_number ? <span className="ml-2 text-muted-foreground">#{customer.account_number}</span> : null}
                </span>
                <button type="button" aria-label="Remove customer" className="text-muted-foreground hover:text-foreground" onClick={() => setCustomer(null)}>
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input id="tk-customer" className="pl-8" value={customerQuery} onChange={(e) => setCustomerQuery(e.target.value)} placeholder="Search by name, email, phone or account number" />
                {searching && <Loader2 className="absolute right-2.5 top-2.5 h-4 w-4 animate-spin text-muted-foreground" />}
                {customerHits && (
                  <ul className="absolute z-10 mt-1 max-h-56 w-full overflow-auto rounded-md border border-border bg-popover shadow-md">
                    {customerHits.length === 0 ? (
                      <li className="px-3 py-2 text-sm text-muted-foreground">No customers match</li>
                    ) : (
                      customerHits.map((c) => (
                        <li key={c.id}>
                          <button
                            type="button"
                            className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted"
                            onClick={() => {
                              setCustomer(c)
                              setCustomerHits(null)
                            }}
                          >
                            <span>{c.first_name} {c.last_name}</span>
                            <span className="text-xs text-muted-foreground">{c.account_number ?? c.email ?? ""}</span>
                          </button>
                        </li>
                      ))
                    )}
                  </ul>
                )}
              </div>
            )}
          </div>

          {error && <p role="alert" className="text-sm text-red-400">{error}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
            <Button onClick={submit} disabled={busy}>
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create ticket
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
