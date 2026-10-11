"use client"
import Link from "next/link"
import {useEffect,useState} from "react"
import {adminApi,adminErrorMessage} from "@/lib/admin-api"
import {PlatformBilling} from "@/components/pricing/platform-billing"

export default function PlatformBillingPage() {
  const [tenant,setTenant]=useState<string|null>(null)
  const [platform,setPlatform]=useState(false)
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState("")
  useEffect(()=>{let alive=true;adminApi.whoami().then(who=>{
    if(!alive)return
    if(!who.roles.some(role=>["owner","org_admin","platform_admin"].includes(role)))throw new Error("Your Organisation Admin manages platform billing.")
    setTenant(who.tenant_id);setPlatform(who.roles.includes("platform_admin"))
  }).catch(e=>{if(alive)setError(adminErrorMessage(e))}).finally(()=>{if(alive)setLoading(false)});return()=>{alive=false}},[])
  return <main className="mx-auto max-w-6xl space-y-6 p-4 sm:p-8"><nav className="flex flex-wrap gap-4 text-sm"><Link href="/" className="underline">Back to OmniDome</Link><Link href="/pricing" className="underline">View plans</Link></nav>{loading?<p>Checking your organisation…</p>:error?<div className="space-y-3"><p role="alert">{error}</p><Link href="/auth?next=%2Fplatform-billing" className="underline">Sign in as your Organisation Admin</Link></div>:tenant&&<PlatformBilling key={tenant} tenant={tenant} platformOwner={platform}/>}</main>
}
