"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { ArrowLeft, ChevronLeft, ChevronRight, Save, Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  blankDefinition, createProduct, launchProduct, previewProduct, updateProduct,
  type Definition, type Lists, type Product,
} from "@/lib/catalogue-api"
import { StepDefinition } from "./step-definition"
import { StepIncluded, StepPricing } from "./steps-commercial"
import { StepSourcing } from "./step-sourcing"
import { StepMedia, StepResearch } from "./steps-content"
import { StepLaunch, StepReview } from "./steps-launch"
import { fromProduct, toInput, type Form, type Preview } from "./wizard-types"

const STEPS = ["Definition", "Suppliers & costs", "Included products", "Selling price & fees", "Media & documents", "Research & KPIs", "Testing & ICASA", "Review"]

const blankForm = (): Form => ({
  status: "draft", product_number: "", custom_number: "", name: "", category: "", range: "", family: "",
  nature: "Digital service", usage: "Customer-facing", owner: "", definition: blankDefinition(),
})

interface Props {
  open: boolean
  product: Product | null
  products: Product[]
  lists: Lists
  reloadLists: () => Promise<void>
  onClose: () => void
  /** Refetch products after any save/launch. */
  onChanged: () => Promise<void>
  onView: (id: string) => void
}

export function ProductWizard({ open, product, products, lists, reloadLists, onClose, onChanged, onView }: Props) {
  const [form, setForm] = useState<Form>(blankForm)
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const [launching, setLaunching] = useState(false)
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [previewTick, setPreviewTick] = useState(0)
  const [dirty, setDirty] = useState(false)
  const formRef = useRef(form)
  formRef.current = form
  const top = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    setForm(product ? fromProduct(product) : blankForm())
    setStep(0)
    setDirty(false)
    setMessage(null)
    setPreview(null)
    setPreviewError(null)
  }, [open, product])

  // The server's launch checks and economics for the current (possibly unsaved) draft.
  useEffect(() => {
    if (!open) return
    let live = true
    const t = setTimeout(() => {
      previewProduct(toInput(form), form.id)
        .then((p) => { if (live) { setPreview(p); setPreviewError(null) } })
        // Keep the last good verdict on screen and say the check failed, instead of a spinner that never ends.
        .catch((e) => { if (live) setPreviewError(e instanceof Error ? e.message : "Could not check the launch requirements.") })
    }, 450)
    return () => { live = false; clearTimeout(t) }
  }, [open, form, previewTick])

  useEffect(() => { top.current?.scrollIntoView({ block: "start", behavior: "smooth" }); setMessage((m) => (m?.error ? null : m)) }, [step])

  const set = useCallback((patch: Partial<Form>) => { setDirty(true); setForm((f) => ({ ...f, ...patch })) }, [])
  const setDef = useCallback((patch: Partial<Definition>) => { setDirty(true); setForm((f) => ({ ...f, definition: { ...f.definition, ...patch } })) }, [])
  const notify = useCallback((m: string) => setMessage({ text: m }), [])
  const fail = useCallback((m: string) => setMessage({ text: m, error: true }), [])

  const save = useCallback(async (submitForReview = false): Promise<Product> => {
    const f = formRef.current
    if (!f.name.trim()) throw new Error("Enter a product name first.")
    const input = toInput(f)
    const saved = f.id
      ? await updateProduct(f.id, { ...input, product_number: f.custom_number || undefined, expected_revision: f.revision ?? 1, submit_for_review: submitForReview })
      : await createProduct(input)
    setForm(fromProduct(saved))
    setDirty(false)
    await onChanged()
    return saved
  }, [onChanged])

  const ensureSaved = useCallback(async () => {
    if (formRef.current.id) return formRef.current.id
    const p = await save()
    setMessage({ text: `Draft saved as ${p.product_number}.` })
    return p.id
  }, [save])

  async function onSave(submit = false) {
    setBusy(true)
    try {
      const p = await save(submit)
      setMessage({ text: submit ? `${p.product_number} submitted for review.` : `Draft ${p.product_number} saved.` })
      if (submit) onClose()
    } catch (e) {
      fail(e instanceof Error ? e.message : "Could not save.")
    } finally {
      setBusy(false)
    }
  }

  async function onLaunch() {
    setLaunching(true)
    try {
      const p = await save()
      const launched = await launchProduct(p.id, p.revision)
      await onChanged()
      setForm(fromProduct(launched))
      setMessage({ text: `${launched.product_number} launched.` })
      onClose()
    } catch (e) {
      fail(e instanceof Error ? e.message : "Launch failed.")
    } finally {
      setLaunching(false)
    }
  }

  function requestClose() {
    if (dirty && !window.confirm("Discard unsaved changes to this product?")) return
    onClose()
  }

  const props = { form, set, setDef, products, lists, reloadLists, preview, ensureSaved, notify, locked: form.status === "active", onView }
  const title = form.id ? `Edit ${form.name || "product"}` : "Develop a product"

  if (!open) return null
  return (
    <section ref={top} className="scroll-mt-4 space-y-4" aria-label="Product journey">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Button type="button" variant="ghost" size="sm" className="-ml-2 mb-1 h-7 gap-1.5 px-2 text-xs text-muted-foreground" onClick={requestClose}>
            <ArrowLeft className="h-3.5 w-3.5" /> Product Directory
          </Button>
          <div className="text-[11px] font-medium uppercase tracking-wider text-primary">{form.id ? `${form.product_number} · ${form.status.replace("_", " ")}` : "New catalogue entry"}</div>
          <h2 className="text-xl font-bold tracking-tight text-foreground">{title}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void onSave(false)} className="gap-1.5"><Save className="h-3.5 w-3.5" /> Save draft</Button>
          {dirty && <span className="text-[11px] text-amber-400">Unsaved changes</span>}
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card/60">
        <div className="flex gap-1.5 overflow-x-auto border-b border-border px-4 py-3" role="tablist" aria-label="Product journey steps">
          {STEPS.map((s, i) => (
            <button
              key={s} type="button" role="tab" aria-selected={step === i}
              onClick={() => setStep(i)}
              className={`whitespace-nowrap rounded-md border px-3 py-1.5 text-xs transition-colors ${step === i ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:text-foreground"}`}
            >
              {i + 1}. {s}
            </button>
          ))}
        </div>

        {message && (
          <div className={`border-b px-5 py-2 text-xs ${message.error ? "border-red-500/40 bg-red-500/10 text-red-300" : "border-border bg-primary/5 text-foreground"}`} role={message.error ? "alert" : "status"} aria-live="polite">
            {message.text} <button type="button" className="ml-2 text-muted-foreground underline" onClick={() => setMessage(null)}>dismiss</button>
          </div>
        )}

        <div className="px-5 py-5">
          {step === 0 && <StepDefinition {...props} />}
          {step === 1 && <StepSourcing {...props} />}
          {step === 2 && <StepIncluded {...props} />}
          {step === 3 && <StepPricing {...props} />}
          {step === 4 && <StepMedia {...props} />}
          {step === 5 && <StepResearch {...props} />}
          {step === 6 && <StepLaunch {...props} />}
          {step === 7 && <StepReview {...props} onLaunch={onLaunch} launching={launching} previewError={previewError} onRetry={() => setPreviewTick((n) => n + 1)} goto={setStep} />}
        </div>

        <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-2 rounded-b-xl border-t border-border bg-background/95 px-5 py-3 backdrop-blur">
          <Button type="button" variant="ghost" size="sm" onClick={requestClose}>Back to directory</Button>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" disabled={step === 0} onClick={() => setStep(step - 1)} className="gap-1"><ChevronLeft className="h-3.5 w-3.5" /> Previous</Button>
            {step < STEPS.length - 1 ? (
              <Button type="button" size="sm" onClick={() => setStep(step + 1)} className="gap-1">Continue <ChevronRight className="h-3.5 w-3.5" /></Button>
            ) : (
              <Button type="button" size="sm" variant="secondary" disabled={busy || form.status === "active"} onClick={() => void onSave(true)} className="gap-1.5"><Send className="h-3.5 w-3.5" /> Submit for review</Button>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
