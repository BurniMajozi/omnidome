"use client"
import {useEffect,useState} from "react"
import {Button} from "@/components/ui/button"
import {adminApi,adminErrorMessage,type TenantMember} from "@/lib/admin-api"

export type PlatformTrial = {status:"pending"|"active"|"expired"|"upgraded";ends_at:string;credits:number;seats:number;free_user_id?:string|null}
export function PlatformTrialCard({tenant,onChange}:{tenant:string;onChange:()=>Promise<void>}) {
  const [trial,setTrial]=useState<PlatformTrial|null>(null)
  const [members,setMembers]=useState<TenantMember[]>([])
  const [loaded,setLoaded]=useState(false)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState("")
  useEffect(()=>{let alive=true;setLoaded(false);setTrial(null);setError("");Promise.all([adminApi.getPlatformTrial(tenant),adminApi.listMembers(tenant)]).then(([t,m])=>{if(alive){setTrial(t);setMembers(m);setLoaded(true)}}).catch(e=>{if(alive)setError(adminErrorMessage(e))});return()=>{alive=false}},[tenant])
  async function run(action:()=>Promise<PlatformTrial>){setBusy(true);setError("");try{setTrial(await action());await onChange()}catch(e){setError(adminErrorMessage(e))}finally{setBusy(false)}}
  return <div className="rounded-xl border p-4 space-y-3">
    <h3 className="font-semibold">Try it For Free</h3>
    {error&&<p role="alert" className="text-sm text-destructive">{error}</p>}
    {!loaded?<p className="text-sm">Loading trial status…</p>:!trial?<><p className="text-sm text-muted-foreground">Try Professional panel features for 14 days, with three seats and 50 total trial AI credits. No card required. Eligible organisations return to Free automatically; existing paid plans cannot be replaced.</p><Button disabled={busy} onClick={()=>run(()=>adminApi.startPlatformTrial(tenant))}>Try it For Free</Button></>:trial.status==="active"?<><p className="text-sm">Trial ends {new Date(trial.ends_at).toLocaleString()}. {trial.credits} total trial credits · {trial.seats} seats.</p><p className="text-sm text-muted-foreground">You return to Free unless you explicitly upgrade. Your records and purchased credits stay available. Extra members keep Admin access so you can choose your included Free seat.</p></>:<><p className="text-sm">{trial.status==="pending"?"Waiting for the owner to accept their verified invitation. The full 14-day trial starts on acceptance.":trial.status==="expired"?"Your trial has ended. Free includes CRM, Services, Portal, Retention, Product and Stock.":"Your organisation has moved off its trial."}</p>{trial.status==="expired"&&<label className="block text-sm">Included Free seat<select disabled={busy} className="mt-2 block w-full rounded border bg-background p-2" value={trial.free_user_id||""} onChange={e=>run(()=>adminApi.selectTrialFreeSeat(tenant,e.target.value))}><option value="" disabled>Choose an active member</option>{members.filter(m=>m.is_active).map(m=><option key={m.id} value={m.id}>{m.email}</option>)}</select></label>}</>}
  </div>
}
