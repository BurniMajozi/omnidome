"use client"

/**
 * CancelFlowModal — Customer-initiated cancel with retention journey integration.
 *
 * Flow:
 * 1. Customer clicks "Cancel Service"
 * 2. Modal shows churn reason selector
 * 3. On submit, POST to Journey Engine /cancel/trigger
 * 4. Engine evaluates rules → returns best offer
 * 5. Customer sees offer (discount, pause, etc.)
 * 6. Customer accepts or rejects
 * 7. If accepted → lifecycle event + retain
 * 8. If rejected → proceed with cancellation
 */

import { useState, useCallback } from "react"
import {
  X, AlertTriangle, Gift, Clock, TrendingDown, Check, XCircle,
  Loader2, Shield, Zap, Heart,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

const JOURNEY_ENGINE_URL =
  process.env.NEXT_PUBLIC_JOURNEY_ENGINE_URL || "/api/journey-engine"

const LIFECYCLE_URL =
  process.env.NEXT_PUBLIC_LIFECYCLE_URL || "/api/lifecycle"

const CHURN_REASONS = [
  { value: "price", label: "Too expensive", icon: TrendingDown },
  { value: "service", label: "Service issues", icon: AlertTriangle },
  { value: "competitor", label: "Found a better deal", icon: Zap },
  { value: "relocation", label: "Moving location", icon: Clock },
  { value: "no_need", label: "No longer needed", icon: XCircle },
  { value: "other", label: "Other", icon: X },
]

type Offer = {
  id: string
  type: string
  title: string
  description: string
  value?: string
  icon?: string
}

type CancelFlowStep = "reason" | "offer" | "accept" | "reject" | "processing"

type CancelFlowModalProps = {
  customerId: string
  customerName?: string
  accountNumber?: string
  onClose: () => void
  onCancelled?: () => void
  onRetained?: () => void
}

export function CancelFlowModal({
  customerId,
  customerName,
  accountNumber,
  onClose,
  onCancelled,
  onRetained,
}: CancelFlowModalProps) {
  const [step, setStep] = useState<CancelFlowStep>("reason")
  const [reason, setReason] = useState("")
  const [reasonNote, setReasonNote] = useState("")
  const [offer, setOffer] = useState<Offer | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmitReason = useCallback(async () => {
    if (!reason) return
    setLoading(true)
    setError(null)

    try {
      // Step 1: Trigger the journey engine cancel flow
      const triggerRes = await fetch(`${JOURNEY_ENGINE_URL}/cancel/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: customerId,
          account_number: accountNumber || "",
          churn_reason: reason,
          churn_note: reasonNote,
          channel: "portal",
          metadata: {
            source: "customer_portal",
            initiated_at: new Date().toISOString(),
          },
        }),
      })

      if (!triggerRes.ok) {
        throw new Error("Failed to process cancellation request")
      }

      const triggerData = await triggerRes.json()

      if (triggerData.offer) {
        // Show the retention offer
        setOffer(triggerData.offer)
        setStep("offer")
      } else {
        // No offer matched — proceed to cancellation confirmation
        setStep("reject")
      }
    } catch (err: any) {
      setError(err.message || "Something went wrong. Please try again.")
    } finally {
      setLoading(false)
    }
  }, [customerId, accountNumber, reason, reasonNote])

  const handleRespond = useCallback(async (accepted: boolean) => {
    if (!offer) return
    setLoading(true)
    setError(null)

    try {
      // Step 2: Send the customer's response to journey engine
      const respondRes = await fetch(
        `${JOURNEY_ENGINE_URL}/cancel/${offer.cancel_event_id}/respond`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            accepted,
            customer_id: customerId,
          }),
        }
      )

      if (!respondRes.ok) {
        throw new Error("Failed to record your response")
      }

      // Step 3: If accepted, trigger lifecycle retain event
      if (accepted) {
        await fetch(`${LIFECYCLE_URL}/events`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            customer_id: customerId,
            event_type: "retention_saved",
            source: "journey_engine",
            metadata: {
              offer_type: offer.type,
              offer_value: offer.value,
              churn_reason: reason,
            },
          }),
        }).catch(() => {}) // non-blocking

        setStep("accept")
        onRetained?.()
      } else {
        // Proceed to actual cancellation
        await fetch(`${LIFECYCLE_URL}/events`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            customer_id: customerId,
            event_type: "cancel_confirmed",
            source: "portal",
            metadata: {
              churn_reason: reason,
              offer_rejected: offer.id,
            },
          }),
        }).catch(() => {}) // non-blocking

        setStep("reject")
        onCancelled?.()
      }
    } catch (err: any) {
      setError(err.message || "Something went wrong. Please try again.")
    } finally {
      setLoading(false)
    }
  }, [offer, customerId, reason, onRetained, onCancelled])

  const offerIcon = (type: string) => {
    switch (type) {
      case "percentage_discount":
      case "fixed_discount":
        return <Gift className="h-6 w-6 text-emerald-400" />
      case "plan_downgrade":
        return <TrendingDown className="h-6 w-6 text-blue-400" />
      case "service_pause":
        return <Clock className="h-6 w-6 text-amber-400" />
      case "free_months":
        return <Gift className="h-6 w-6 text-purple-400" />
      case "loyalty_reward":
        return <Heart className="h-6 w-6 text-rose-400" />
      case "personal_outreach":
        return <Shield className="h-6 w-6 text-cyan-400" />
      default:
        return <Gift className="h-6 w-6 text-emerald-400" />
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-lg rounded-xl border border-border bg-card shadow-2xl">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-muted-foreground hover:text-foreground transition-colors"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="p-6">
          {/* STEP 1: Churn Reason */}
          {step === "reason" && (
            <>
              <div className="flex items-center gap-3 mb-6">
                <div className="rounded-lg bg-red-500/20 p-2.5">
                  <AlertTriangle className="h-6 w-6 text-red-400" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-foreground">
                    We&apos;re sorry to see you go
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    {customerName ? `${customerName}, h` : "H"}elp us understand why you&apos;re leaving
                  </p>
                </div>
              </div>

              <div className="space-y-3 mb-4">
                {CHURN_REASONS.map((r) => (
                  <button
                    key={r.value}
                    onClick={() => setReason(r.value)}
                    className={`w-full flex items-center gap-3 rounded-lg border px-4 py-3 text-left transition-all ${
                      reason === r.value
                        ? "border-primary bg-primary/10 text-foreground"
                        : "border-border bg-secondary/30 text-muted-foreground hover:border-border hover:bg-secondary/50"
                    }`}
                  >
                    <r.icon className="h-5 w-5 shrink-0" />
                    <span className="text-sm font-medium">{r.label}</span>
                  </button>
                ))}
              </div>

              <textarea
                value={reasonNote}
                onChange={(e) => setReasonNote(e.target.value)}
                placeholder="Tell us more (optional)..."
                className="w-full rounded-lg border border-border bg-secondary/30 px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
                rows={3}
              />

              {error && (
                <p className="mt-3 text-sm text-red-400">{error}</p>
              )}

              <div className="flex items-center justify-end gap-3 mt-6">
                <Button variant="ghost" onClick={onClose} disabled={loading}>
                  Go Back
                </Button>
                <Button
                  onClick={handleSubmitReason}
                  disabled={!reason || loading}
                  className="bg-red-600 hover:bg-red-700"
                >
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : null}
                  Continue
                </Button>
              </div>
            </>
          )}

          {/* STEP 2: Retention Offer */}
          {step === "offer" && offer && (
            <>
              <div className="flex items-center gap-3 mb-6">
                <div className="rounded-lg bg-emerald-500/20 p-2.5">
                  <Gift className="h-6 w-6 text-emerald-400" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-foreground">
                    Before you go...
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    We have a special offer for you
                  </p>
                </div>
              </div>

              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-6 mb-6">
                <div className="flex items-center gap-3 mb-3">
                  {offerIcon(offer.type)}
                  <div>
                    <h3 className="font-semibold text-foreground">{offer.title}</h3>
                    {offer.value && (
                      <Badge className="bg-emerald-500/20 text-emerald-400 mt-1">
                        {offer.value}
                      </Badge>
                    )}
                  </div>
                </div>
                <p className="text-sm text-muted-foreground">{offer.description}</p>
              </div>

              {error && (
                <p className="mb-3 text-sm text-red-400">{error}</p>
              )}

              <div className="flex items-center justify-between">
                <Button
                  variant="ghost"
                  onClick={() => handleRespond(false)}
                  disabled={loading}
                  className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                >
                  No thanks, proceed with cancellation
                </Button>
                <Button
                  onClick={() => handleRespond(true)}
                  disabled={loading}
                  className="bg-emerald-600 hover:bg-emerald-700"
                >
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <Check className="h-4 w-4 mr-2" />
                  )}
                  Accept & Stay
                </Button>
              </div>
            </>
          )}

          {/* STEP 3a: Customer Stayed */}
          {step === "accept" && (
            <div className="text-center py-6">
              <div className="mx-auto w-16 h-16 rounded-full bg-emerald-500/20 flex items-center justify-center mb-4">
                <Heart className="h-8 w-8 text-emerald-400" />
              </div>
              <h2 className="text-xl font-semibold text-foreground mb-2">
                Thank you for staying with us!
              </h2>
              <p className="text-muted-foreground mb-6">
                Your offer has been applied. We&apos;re committed to earning your trust every day.
              </p>
              <Badge className="bg-emerald-500/20 text-emerald-400 mb-6">
                <Check className="h-3 w-3 mr-1" />
                Retention offer activated
              </Badge>
              <div>
                <Button onClick={onClose} className="bg-emerald-600 hover:bg-emerald-700">
                  Back to Portal
                </Button>
              </div>
            </div>
          )}

          {/* STEP 3b: Customer Leaving */}
          {step === "reject" && (
            <div className="text-center py-6">
              <div className="mx-auto w-16 h-16 rounded-full bg-amber-500/20 flex items-center justify-center mb-4">
                <AlertTriangle className="h-8 w-8 text-amber-400" />
              </div>
              <h2 className="text-xl font-semibold text-foreground mb-2">
                We&apos;re sorry to see you go
              </h2>
              <p className="text-muted-foreground mb-6">
                Your feedback helps us improve. You can always come back — our doors are open.
              </p>
              <div className="flex items-center justify-center gap-3">
                <Button variant="ghost" onClick={onClose}>
                  Not yet, go back
                </Button>
                <Button
                  onClick={onClose}
                  className="bg-red-600 hover:bg-red-700"
                >
                  Confirm Cancellation
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default CancelFlowModal
