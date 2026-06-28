"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { X, AlertTriangle, Gift, CheckCircle, XCircle } from "lucide-react"

interface CancelOffer {
  type: string
  label: string
  description: string
  value: string
}

interface CancelFlowModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  customerId?: string
  customerName?: string
}

const CANCEL_REASONS = [
  { value: "price", label: "Too expensive" },
  { value: "service", label: "Service quality issues" },
  { value: "moving", label: "Moving area" },
  { value: "competitor", label: "Switching to competitor" },
  { value: "unused", label: "Not using the service" },
  { value: "other", label: "Other" },
]

export function CancelFlowModal({
  open,
  onOpenChange,
  customerId = "cust-demo-001",
  customerName = "Demo Customer",
}: CancelFlowModalProps) {
  const [step, setStep] = useState<"reason" | "offer" | "result">("reason")
  const [reason, setReason] = useState("")
  const [offer, setOffer] = useState<CancelOffer | null>(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<"accepted" | "rejected" | null>(null)

  const handleTriggerJourney = async () => {
    if (!reason) return
    setLoading(true)
    setStep("offer")

    try {
      const res = await fetch("/api/journey-engine/cancel/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: customerId,
          churn_reason: reason,
        }),
      })
      const data = await res.json()
      setOffer({
        type: data.offer?.type || "discount",
        label: data.offer?.label || "20% Discount",
        description: data.offer?.description || "20% off your next 3 months",
        value: data.offer?.value || "20%",
      })
    } catch {
      // Fallback demo offer
      setOffer({
        type: "discount",
        label: "20% Discount",
        description: "20% off your next 3 months",
        value: "20%",
      })
    }
    setLoading(false)
  }

  const handleRespond = async (accepted: boolean) => {
    setLoading(true)
    try {
      await fetch("/api/journey-engine/cancel/respond", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: customerId,
          accepted,
        }),
      })
    } catch {
      // Demo mode
    }
    setResult(accepted ? "accepted" : "rejected")
    setStep("result")
    setLoading(false)
  }

  const handleClose = () => {
    setStep("reason")
    setReason("")
    setOffer(null)
    setResult(null)
    setLoading(false)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        {/* Step 1: Reason */}
        {step === "reason" && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-amber-500" />
                Cancel Service
              </DialogTitle>
              <DialogDescription>
                We're sorry to see you go, {customerName}. Help us understand why.
              </DialogDescription>
            </DialogHeader>
            <div className="py-4">
              <Select value={reason} onValueChange={setReason}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a reason..." />
                </SelectTrigger>
                <SelectContent>
                  {CANCEL_REASONS.map((r) => (
                    <SelectItem key={r.value} value={r.value}>
                      {r.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <DialogFooter className="gap-2">
              <Button variant="outline" onClick={handleClose}>
                Go Back
              </Button>
              <Button
                onClick={handleTriggerJourney}
                disabled={!reason || loading}
                className="bg-amber-600 hover:bg-amber-700"
              >
                {loading ? "Checking offers..." : "Continue"}
              </Button>
            </DialogFooter>
          </>
        )}

        {/* Step 2: Offer */}
        {step === "offer" && offer && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Gift className="h-5 w-5 text-emerald-500" />
                We have an offer for you
              </DialogTitle>
              <DialogDescription>
                Based on your situation, here's what we can do:
              </DialogDescription>
            </DialogHeader>
            <div className="py-4">
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Badge className="badge-success">
                    {offer.type}
                  </Badge>
                  <span className="font-semibold text-foreground">{offer.label}</span>
                </div>
                <p className="text-sm text-muted-foreground">{offer.description}</p>
              </div>
            </div>
            <DialogFooter className="gap-2">
              <Button
                variant="outline"
                onClick={() => handleRespond(false)}
                disabled={loading}
                className="border-red-500/30 text-red-400 hover:bg-red-500/10"
              >
                <XCircle className="mr-2 h-4 w-4" />
                No thanks, cancel
              </Button>
              <Button
                onClick={() => handleRespond(true)}
                disabled={loading}
                className="bg-emerald-600 hover:bg-emerald-700"
              >
                <CheckCircle className="mr-2 h-4 w-4" />
                Accept offer
              </Button>
            </DialogFooter>
          </>
        )}

        {/* Step 3: Result */}
        {step === "result" && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {result === "accepted" ? (
                  <>
                    <CheckCircle className="h-5 w-5 text-emerald-500" />
                    Offer Accepted!
                  </>
                ) : (
                  <>
                    <XCircle className="h-5 w-5 text-red-500" />
                    Cancellation Confirmed
                  </>
                )}
              </DialogTitle>
              <DialogDescription>
                {result === "accepted"
                  ? "Your offer has been applied. We're glad to keep you!"
                  : "Your cancellation has been processed. We're sorry to see you go."}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button onClick={handleClose}>Close</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
