"use client"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { CustomerPicker, type PickedCustomer } from "./billing/invoicing/doc-editor"
import { inputClass } from "./billing/shared"
import { fieldSalesApi } from "@/lib/mobile-field-sales-api"
type Offer = {name?: string; offer_type?: string; description?: string; parameters?: Record<string, unknown>}
type Trigger = {matched: boolean; cancel_event_id?: string; offer?: Offer | null; message?: string}
const reasons = ["price", "service", "moving", "competitor", "unused", "other"]
async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`/api/journey-engine/cancel/${path}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body), signal: AbortSignal.timeout(20000)})
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : data.error || `Request failed (${response.status})`)
  return data
}
export function CancelFlowModal({open, onOpenChange, customerId, customerName}: {open: boolean; onOpenChange: (open: boolean) => void; customerId?: string; customerName?: string}) {
  const [customer, setCustomer] = useState<PickedCustomer | null>(null)
  const [reason, setReason] = useState(""); const [trigger, setTrigger] = useState<Trigger | null>(null)
  const [busy, setBusy] = useState(false); const [error, setError] = useState("")
  const [decision, setDecision] = useState<"accept" | "reject" | null>(null)
  useEffect(() => { if (open) {setCustomer(customerId ? {id: customerId, label: customerName || customerId} : null); setReason(""); setTrigger(null); setDecision(null); setError("")} }, [open, customerId, customerName])
  async function check() {
    if (!customer || !reason) return
    setBusy(true); setError("")
    try {
      const snapshot = await fieldSalesApi.getCustomer360(customer.id)
      if (!snapshot.tenant_id || !snapshot.account_number) throw new Error("The customer record is missing its tenant or account number. Update the record before continuing.")
      setTrigger(await post<Trigger>("trigger", {customer_id: customer.id, account_number: snapshot.account_number, customer_snapshot: snapshot, cancel_reason: reason, source_channel: "staff_portal"}))
    } catch(e) {setError(e instanceof Error ? e.message : "Could not check retention offers")}
    finally {setBusy(false)}
  }
  async function respond(value: "accept" | "reject") {
    if (!trigger?.cancel_event_id) return
    setBusy(true); setError("")
    try {await post("respond", {cancel_event_id: trigger.cancel_event_id, decision: value}); setDecision(value)}
    catch(e) {setError(e instanceof Error ? e.message : "The decision could not be saved")}
    finally {setBusy(false)}
  }
  return <Dialog open={open} onOpenChange={value => {if (!busy) onOpenChange(value)}}><DialogContent className="sm:max-w-md">
    <DialogHeader><DialogTitle>{decision ? "Decision recorded" : "Retention review"}</DialogTitle><DialogDescription>Select the customer and record their response to an available retention offer.</DialogDescription></DialogHeader>
    {error && <p role="alert" className="text-sm text-red-400 break-words">{error}</p>}
    {decision ? <p className="text-sm">{decision === "accept" ? "The customer accepted the offer." : "The customer declined the offer. Continue the cancellation workflow to process the service cancellation."}</p> : !trigger ? <div className="space-y-4">
      <CustomerPicker value={customer} onChange={setCustomer} disabled={busy} />
      <label className="block text-sm">Reason<select className={inputClass} value={reason} disabled={busy} onChange={e => setReason(e.target.value)}><option value="">Select a reason</option>{reasons.map(r => <option key={r} value={r}>{r}</option>)}</select></label>
    </div> : <div className="space-y-3">
      {trigger.offer ? <><h3 className="font-medium">{trigger.offer.name || trigger.offer.offer_type || "Retention offer"}</h3><p className="text-sm">{trigger.offer.description}</p>{trigger.offer.parameters && <dl className="text-sm">{Object.entries(trigger.offer.parameters).map(([key, value]) => <div key={key} className="break-words"><dt>{key}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd></div>)}</dl>}</> : <p>{trigger.message || "No retention offer matched this customer."}</p>}
    </div>}
    <DialogFooter className="gap-2"><Button variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>Close</Button>
      {!trigger && !decision && <Button disabled={busy || !customer || !reason} onClick={() => void check()}>{busy ? "Checking…" : "Check offers"}</Button>}
      {trigger?.cancel_event_id && !decision && <><Button variant="outline" disabled={busy} onClick={() => void respond("reject")}>Decline offer</Button>{trigger.offer && <Button disabled={busy} onClick={() => void respond("accept")}>Accept offer</Button>}</>}
    </DialogFooter>
  </DialogContent></Dialog>
}
