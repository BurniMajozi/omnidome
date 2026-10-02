"use client"

import { fetchLoadable } from "@/lib/service-fetch"
import { sendJson } from "@/lib/api-result"
import type { JournalEntry, JournalEntryLineInput } from "@/lib/finance-api"

export interface AccountingPeriod { period: string; status: string }
export const readJournals = (offset = 0) => fetchLoadable<JournalEntry[]>(`/svc/finance/journal-entries?limit=100&offset=${offset}`)
export const readPeriods = () => fetchLoadable<AccountingPeriod[]>("/svc/finance/periods")
export const writeJournal = (body: { description: string; entry_date: string; source: string; lines: JournalEntryLineInput[] }) => sendJson("/svc/finance/journal-entries", "POST", body)
export const journalAction = (id: string, action: "post" | "reverse" | "delete") => sendJson(`/svc/finance/journal-entries/${encodeURIComponent(id)}${action === "delete" ? "" : `/${action}`}`, action === "delete" ? "DELETE" : "POST")
export const setAccountingPeriod = (period: string, action: "close" | "reopen") => sendJson(`/svc/finance/periods/${encodeURIComponent(period)}/${action}`, "POST")
