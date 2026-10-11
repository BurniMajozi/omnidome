"use client"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { adminApi, adminErrorMessage, type InvoiceProfile } from "@/lib/admin-api"

function ProfileForm({value,onChange,onSave,busy,supplier=false}:{value:InvoiceProfile;onChange:(v:InvoiceProfile)=>void;onSave:()=>void;busy:boolean;supplier?:boolean}) {
  const valid = value.name.trim() && value.address.trim() && (!value.vat_registered || /^4\d{9}$/.test(value.vat_number || ""))
  return <fieldset disabled={busy} className="space-y-3 rounded border p-3">
    <legend className="text-sm font-medium">{supplier ? "Platform supplier" : "Customer billing details"}</legend>
    <label className="block text-sm">{supplier ? "Supplier legal or trading name" : "Customer legal or trading name"}<input className="mt-1 block w-full rounded border bg-background p-2" value={value.name} maxLength={200} onChange={e=>onChange({...value,name:e.target.value})}/></label>
    <label className="block text-sm">Business address<textarea className="mt-1 block w-full rounded border bg-background p-2" value={value.address} maxLength={500} onChange={e=>onChange({...value,address:e.target.value})}/></label>
    <label className="flex gap-2 text-sm"><input type="checkbox" checked={value.vat_registered} onChange={e=>onChange({...value,vat_registered:e.target.checked,vat_number:e.target.checked ? value.vat_number : null})}/>VAT registered</label>
    {value.vat_registered && <label className="block text-sm">VAT registration number<input className="mt-1 block w-full rounded border bg-background p-2" inputMode="numeric" maxLength={10} value={value.vat_number || ""} onChange={e=>onChange({...value,vat_number:e.target.value})}/><span className="text-xs text-muted-foreground">10 digits, starting with 4.</span></label>}
    {supplier && <><label className="flex gap-2 text-sm"><input type="checkbox" checked={value.prices_include_vat} onChange={e=>onChange({...value,prices_include_vat:e.target.checked})}/>Catalogue prices include VAT when registered</label><p className="text-xs text-muted-foreground">No VAT is charged while unregistered. Changes apply to future quotes; issued invoices keep their original details and amounts.</p></>}
    <Button size="sm" disabled={busy || !valid} onClick={onSave}>Save {supplier ? "supplier and VAT settings" : "billing details"}</Button>
  </fieldset>
}

export function PlatformInvoiceSettings({tenant,platformOwner}:{tenant:string;platformOwner:boolean}) {
  const [customer,setCustomer]=useState<InvoiceProfile|null>(null)
  const [supplier,setSupplier]=useState<InvoiceProfile|null>(null)
  const [busy,setBusy]=useState(false)
  const [message,setMessage]=useState("")
  const [error,setError]=useState("")
  useEffect(()=>{
    let active=true
    setCustomer(null);setSupplier(null);setError("");setMessage("")
    Promise.all([adminApi.invoiceProfile(tenant),platformOwner ? adminApi.invoiceSupplier() : Promise.resolve(null)])
      .then(([c,s])=>{if(active){setCustomer(c);setSupplier(s)}}).catch(e=>{if(active)setError(adminErrorMessage(e))})
    return ()=>{active=false}
  },[tenant,platformOwner])
  const save=async(kind:"customer"|"supplier")=>{
    setBusy(true);setError("");setMessage("")
    try {if(kind==="supplier" && supplier)setSupplier(await adminApi.saveInvoiceSupplier(supplier));else if(customer)setCustomer(await adminApi.saveInvoiceProfile(tenant,customer));setMessage("Saved for future invoices. Issued invoices remain unchanged.")}
    catch(e){setError(adminErrorMessage(e))}finally{setBusy(false)}
  }
  return <details className="rounded border p-3"><summary className="cursor-pointer text-sm font-medium">Invoice details{platformOwner && " and VAT settings"}</summary><div className="mt-3 space-y-3">
    {customer && <ProfileForm value={customer} onChange={setCustomer} onSave={()=>save("customer")} busy={busy}/>}
    {supplier && <ProfileForm value={supplier} onChange={setSupplier} onSave={()=>save("supplier")} busy={busy} supplier/>}
    {message && <p role="status" className="text-sm">{message}</p>}{error && <p role="alert" className="text-sm text-destructive">{error}</p>}
  </div></details>
}
