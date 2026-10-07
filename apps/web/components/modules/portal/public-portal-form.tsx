"use client"
import { useState, type FormEvent } from "react"
import { Button } from "@/components/ui/button"

const consentText = "I agree that the service provider may use these details to respond to my enquiry."
export function PublicPortalForm({ slug, theme }: { slug: string; theme?: Record<string, unknown> | null }) {
  const dark = theme?.appearance === "dark"
  const inputClass = `mt-1 block w-full rounded-md border px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-cyan-500 ${dark ? "border-slate-700 bg-slate-900 text-slate-100" : "border-slate-300 bg-white text-slate-900"}`
  const textareaClass = `${inputClass} min-h-24 resize-y`
  const accents: Record<string, string> = { cyan: "bg-cyan-600 hover:bg-cyan-700", blue: "bg-blue-600 hover:bg-blue-700", emerald: "bg-emerald-600 hover:bg-emerald-700", orange: "bg-orange-600 hover:bg-orange-700" }
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")
  const [sent, setSent] = useState(false)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const form = new FormData(event.currentTarget)
    if (form.get("consent") !== "on") { setMessage("Please agree to the use of your details before sending."); return }
    setBusy(true); setMessage("")
    const query = new URLSearchParams(window.location.search)
    try {
      const response = await fetch("/svc/portal_builder/api/v1/portal/submissions", {
        method: "POST", credentials: "omit", headers: { "Content-Type": "application/json" }, signal: AbortSignal.timeout(20_000),
        body: JSON.stringify({ slug, consent: true, consent_text: consentText, website: String(form.get("website") || ""),
          form_data: { name: form.get("name"), email: form.get("email"), phone: form.get("phone"), message: form.get("message") },
          utm_source: query.get("utm_source")?.slice(0, 100), utm_medium: query.get("utm_medium")?.slice(0, 100), utm_campaign: query.get("utm_campaign")?.slice(0, 200),
          referrer: document.referrer ? new URL(document.referrer).origin : null }),
      })
      const result = await response.json().catch(() => null)
      if (!response.ok) { setMessage(response.status === 429 ? "Too many enquiries. Please wait a few minutes and try again." : typeof result?.detail === "string" ? result.detail : "Your enquiry could not be sent. Please try again."); return }
      setSent(true)
    } catch { setMessage("The service is unavailable. Your enquiry has not been sent. Please retry.") }
    finally { setBusy(false) }
  }
  return <section id="enquiry" className={`rounded-lg border p-5 sm:p-7 ${dark ? "border-slate-700 bg-slate-950 text-slate-100" : "border-slate-200 bg-white text-slate-900"}`}>
    <h2 className="mb-4 text-xl font-semibold">Send an enquiry</h2>
    {sent ? <p role="status">Thank you. Your enquiry has been received.</p> : <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="space-y-1 text-sm">Name<input name="name" autoComplete="name" required maxLength={200} className={inputClass} /></label>
        <label className="space-y-1 text-sm">Email<input name="email" type="email" autoComplete="email" required maxLength={254} className={inputClass} /></label>
      </div>
      <label className="block space-y-1 text-sm">Phone (optional)<input name="phone" type="tel" autoComplete="tel" maxLength={40} className={inputClass} /></label>
      <label className="block space-y-1 text-sm">How can we help?<textarea name="message" required maxLength={2000} className={textareaClass} /></label>
      <div hidden aria-hidden="true"><label>Website<input name="website" tabIndex={-1} autoComplete="off" /></label></div>
      <label className="flex items-start gap-2 text-sm"><input name="consent" type="checkbox" required className="mt-1" /><span>{consentText}</span></label>
      {message && <p role="alert" className="text-sm text-destructive">{message}</p>}
      <Button type="submit" disabled={busy} className={`text-white ${accents[String(theme?.accent)] || accents.cyan}`}>{busy ? "Sending…" : "Send enquiry"}</Button>
    </form>}
  </section>
}
