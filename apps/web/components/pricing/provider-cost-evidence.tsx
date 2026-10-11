"use client"
import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { adminApi, adminErrorMessage } from "@/lib/admin-api"

export type ProviderReceipt = {id:string;provider:string;reference:string;amount:string;currency:string;remaining:string;allocated:string;period_start:string;period_end:string}
export type ProviderAllocation = {id:string;provider:string;reference:string;amount:string;currency:string;quantity:string;unit:string;reason:string;void_reason:string|null}
const units = ["audio minutes","provider credits","account months","inbox months","domain months","email capacity blocks","subscription months","provider requests","storage GB months"]
const input = "mt-1 block w-full rounded border bg-background p-2"

export function ProviderCostEvidence({tenant,onChange}:{tenant:string;onChange:()=>Promise<void>}) {
  const [receipts,setReceipts]=useState<ProviderReceipt[]>([])
  const [rows,setRows]=useState<ProviderAllocation[]>([])
  const [selected,setSelected]=useState("")
  const [error,setError]=useState("")
  const [busy,setBusy]=useState(false)
  const [voidReason,setVoidReason]=useState("")
  const [entry,setEntry]=useState({provider:"AgentMail",reference:"",amount:"",currency:"USD",period_start:"",period_end:""})
  const [share,setShare]=useState({amount:"",quantity:"1",unit:"subscription months",reason:""})
  const retryKey=useRef<string|null>(null)
  const current=useRef(tenant);current.current=tenant
  const load=async()=>{const [invoices,allocations]=await Promise.all([adminApi.getProviderReceipts(),adminApi.getProviderAllocations(tenant)]);if(current.current===tenant){setReceipts(invoices);setRows(allocations)}}
  useEffect(()=>{setReceipts([]);setRows([]);setSelected("");setError("");retryKey.current=null;load().catch(e=>setError(adminErrorMessage(e)))},[tenant]) // eslint-disable-line react-hooks/exhaustive-deps
  const invoice=receipts.find(row=>row.id===selected)
  const act=async(task:()=>Promise<unknown>)=>{setBusy(true);setError("");try{await task();await load();await onChange()}catch(e){setError(adminErrorMessage(e))}finally{setBusy(false)}}
  return <details className="rounded border p-3">
    <summary className="cursor-pointer text-sm font-medium">Supplier invoices & tenant cost allocation</summary>
    <p className="my-3 text-xs text-muted-foreground">Record the supplier invoice once, then allocate its cost across tenants in the supplier currency, excluding supplier tax. These are Platform Owner evidence entries, not automatic provider receipts or customer charges. FX, hosting and support still need reconciliation.</p>
    {error&&<p role="alert" className="mb-3 text-sm text-destructive">{error}</p>}
    <Button size="sm" variant="outline" disabled={busy} onClick={()=>act(async()=>{})}>Refresh evidence</Button>
    <details className="my-4"><summary className="cursor-pointer text-sm">Record a supplier invoice</summary>
      <form className="mt-3 grid gap-3 sm:grid-cols-2" onSubmit={event=>{event.preventDefault();act(async()=>{const result=await adminApi.recordProviderReceipt(entry);setSelected(result.id);setEntry({...entry,reference:"",amount:""})})}}>
        <label className="text-sm">Provider<select className={input} value={entry.provider} onChange={e=>setEntry({...entry,provider:e.target.value})}>{["AgentMail","Deepgram","Firecrawl","Zernio"].map(provider=><option key={provider}>{provider}</option>)}</select></label>
        <label className="text-sm">Supplier reference<input required maxLength={120} className={input} value={entry.reference} onChange={e=>setEntry({...entry,reference:e.target.value})}/></label>
        <label className="text-sm">Net supplier amount<input required type="number" min="0" step="0.01" className={input} value={entry.amount} onChange={e=>setEntry({...entry,amount:e.target.value})}/></label>
        <label className="text-sm">Currency<select className={input} value={entry.currency} onChange={e=>setEntry({...entry,currency:e.target.value})}><option>USD</option><option>ZAR</option></select></label>
        <label className="text-sm">Service period starts<input required type="date" className={input} value={entry.period_start} onChange={e=>setEntry({...entry,period_start:e.target.value})}/></label>
        <label className="text-sm">Service period ends (exclusive)<input required type="date" className={input} value={entry.period_end} onChange={e=>setEntry({...entry,period_end:e.target.value})}/></label>
        <Button type="submit" disabled={busy}>Record supplier invoice</Button>
      </form>
    </details>
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={event=>{event.preventDefault();act(async()=>{retryKey.current??=crypto.randomUUID();await adminApi.allocateProviderCost(tenant,{...share,id:retryKey.current,receipt_id:selected});retryKey.current=null;setShare({...share,amount:"",reason:""})})}}>
      <label className="text-sm sm:col-span-2">Invoice to allocate<select required value={selected} className={input} onChange={e=>setSelected(e.target.value)}><option value="">Choose a supplier invoice</option>{receipts.map(row=><option key={row.id} value={row.id}>{row.provider} · {row.reference} · {row.currency} {row.remaining} remaining</option>)}</select></label>
      {invoice&&<p className="text-xs text-muted-foreground sm:col-span-2">{invoice.period_start} – {invoice.period_end}: {invoice.currency} {invoice.amount} total; {invoice.allocated} allocated. This entry applies to the current tenant.</p>}
      <label className="text-sm">Tenant cost ({invoice?.currency||"supplier currency"})<input required type="number" min="0" step="0.01" max={invoice?.remaining} className={input} value={share.amount} onChange={e=>setShare({...share,amount:e.target.value})}/></label>
      <label className="text-sm">Native capacity unit<select className={input} value={share.unit} onChange={e=>setShare({...share,unit:e.target.value})}>{units.map(unit=><option key={unit}>{unit}</option>)}</select></label>
      <label className="text-sm">Quantity<input required type="number" min="0" step="0.000001" className={input} value={share.quantity} onChange={e=>setShare({...share,quantity:e.target.value})}/></label>
      <label className="text-sm">Allocation basis<input required minLength={5} maxLength={500} className={input} value={share.reason} onChange={e=>setShare({...share,reason:e.target.value})}/></label>
      <Button disabled={busy||!invoice} type="submit">Allocate cost to this tenant</Button>
    </form>
    <div className="mt-5 space-y-3"><h4 className="text-sm font-medium">Allocation history</h4>{!rows.length&&<p className="text-sm text-muted-foreground">No supplier costs allocated yet.</p>}{rows.map(row=><div key={row.id} className="rounded bg-secondary p-3 text-sm"><p>{row.provider} · {row.reference} · {row.currency} {row.amount}</p><p className="text-xs text-muted-foreground">{row.quantity} {row.unit} · {row.reason}</p>{row.void_reason?<p className="mt-2 text-xs">Voided: {row.void_reason}. Original evidence retained.</p>:<Button variant="outline" size="sm" className="mt-2" disabled={busy||voidReason.trim().length<5} onClick={()=>act(()=>adminApi.voidProviderAllocation(tenant,row.id,voidReason))}>Void this allocation</Button>}</div>)}</div>
    <label className="mt-3 block text-sm">Reason for voiding<input minLength={5} maxLength={500} className={input} value={voidReason} onChange={e=>setVoidReason(e.target.value)}/></label>
    <p className="mt-2 text-xs text-muted-foreground">Voiding retains the evidence, frees the amount for reassignment and excludes the allocation from current cost totals. It does not refund a customer. If a request times out, refresh evidence before starting a different allocation.</p>
  </details>
}
