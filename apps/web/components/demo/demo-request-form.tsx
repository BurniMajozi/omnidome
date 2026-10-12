"use client"
import {useState} from "react"
import {Button} from "@/components/ui/button"

export function DemoRequestForm(){
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState("")
  const [notice,setNotice]=useState("")
  async function submit(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);setError("")
    const form=new FormData(event.currentTarget)
    try{
      const response=await fetch("/api/platform-public/demo/request",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(Object.fromEntries(form))})
      const data=await response.json()
      if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:"Please check your details and try again.")
      setNotice(data.message)
    }catch(e){setError(e instanceof Error?e.message:"Your request could not be sent. Please try again.")}
    finally{setBusy(false)}
  }
  return <section className="space-y-4 rounded-xl border p-5">
    <h2 className="text-xl font-semibold">Request your demo</h2>
    <p className="text-sm text-muted-foreground">Tell us a little about your organisation. Our sales team will contact you to arrange a walkthrough.</p>
    {notice?<p role="status">{notice}</p>:<form onSubmit={submit} className="space-y-4">
      {[["name","Your name","text"],["company","Organisation","text"],["email","Work email","email"]].map(([name,label,type])=><label key={name} className="block text-sm">{label}<input name={name} type={type} required minLength={name==="email"?3:2} maxLength={name==="email"?254:name==="name"?100:150} autoComplete={name==="email"?"email":name==="name"?"name":"organization"} className="mt-2 block w-full rounded border bg-background p-3"/></label>)}
      <Button type="submit" disabled={busy}>{busy?"Sending…":"Request a Demo"}</Button>
      {error&&<p role="alert" className="text-sm text-destructive">{error}</p>}
    </form>}
  </section>
}
