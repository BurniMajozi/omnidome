"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, X, CheckCircle, Loader2, ArrowLeft } from "lucide-react";
import { api } from "@/lib/api/client";
import brandConfig from "@/config/brand.json";

const CANCEL_REASONS = [
  { value: "price", label: "Too expensive" },
  { value: "service", label: "Service issues / frequent outages" },
  { value: "moving", label: "Moving to a new area" },
  { value: "competitor", label: "Found a better deal elsewhere" },
  { value: "no_longer_needed", label: "No longer need the service" },
  { value: "other", label: "Other" },
];

export default function CancelPage() {
  const router = useRouter();
  const [step, setStep] = useState<"reason" | "offer" | "confirm" | "done">("reason");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cancelEventId, setCancelEventId] = useState<string | null>(null);
  const [offer, setOffer] = useState<any>(null);
  const [customerSnapshot, setCustomerSnapshot] = useState<Record<string, any>>({});

  useEffect(() => {
    // Load customer profile for the cancel snapshot
    api.getProfile().then((profile: any) => {
      setCustomerSnapshot({
        id: profile.id,
        tenant_id: profile.tenantId || profile.tenant_id,
        account_number: profile.accountNumber || profile.account_number,
        monthly_spend_zar: profile.monthlySpend || profile.monthly_spend_zar || 999,
        segment: profile.segment || "standard",
        tenure_months: profile.tenureMonths || profile.tenure_months || 12,
      });
    }).catch(() => {
      // Fallback snapshot
      setCustomerSnapshot({
        id: "current-customer-id",
        tenant_id: "current-tenant-id",
        account_number: "ACC-0001",
        monthly_spend_zar: 999,
        segment: "standard",
        tenure_months: 12,
      });
    });
  }, []);

  const handleTriggerCancel = async () => {
    if (!reason) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.triggerCancel(customerSnapshot, reason);
      setCancelEventId(data.cancel_event_id);
      if (data.offer) {
        setOffer(data.offer);
        setStep("offer");
      } else {
        setStep("confirm");
      }
    } catch (e: any) {
      setError(e.message || "Failed to process cancellation");
    } finally {
      setLoading(false);
    }
  };

  const handleRespond = async (decision: "accept" | "reject") => {
    if (!cancelEventId) return;
    setLoading(true);
    setError(null);
    try {
      await api.respondToCancel(cancelEventId, decision);
      setStep("done");
    } catch (e: any) {
      setError(e.message || "Failed to process response");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4 lg:p-6 max-w-2xl mx-auto space-y-6">
      <button onClick={() => router.back()} className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700">
        <ArrowLeft size={16} /> Back
      </button>

      {step === "reason" && (
        <>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-red-50">
              <AlertTriangle size={24} className="text-red-600" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Cancel Service</h1>
              <p className="text-gray-500 text-sm">We're sorry to see you go. Help us understand why.</p>
            </div>
          </div>

          <div className="space-y-2">
            {CANCEL_REASONS.map((r) => (
              <button
                key={r.value}
                onClick={() => setReason(r.value)}
                className={`w-full text-left p-4 rounded-xl border-2 transition-colors ${
                  reason === r.value
                    ? "border-red-500 bg-red-50"
                    : "border-gray-200 bg-white hover:border-gray-300"
                }`}
              >
                <p className="text-sm font-medium text-gray-900">{r.label}</p>
              </button>
            ))}
          </div>

          {error && <p className="text-sm text-red-600 bg-red-50 p-3 rounded-lg">{error}</p>}

          <button
            onClick={handleTriggerCancel}
            disabled={!reason || loading}
            className="w-full py-3 rounded-xl text-white font-medium disabled:opacity-50"
            style={{ backgroundColor: brandConfig.colors.error || "#dc2626" }}
          >
            {loading ? <Loader2 size={16} className="inline animate-spin mr-2" /> : null}
            Continue
          </button>
        </>
      )}

      {step === "offer" && offer && (
        <>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-green-50">
              <CheckCircle size={24} className="text-green-600" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">We have an offer for you</h1>
              <p className="text-gray-500 text-sm">Before you go, here's something we'd like you to consider</p>
            </div>
          </div>

          <div className="bg-gradient-to-br from-green-50 to-emerald-50 border-2 border-green-200 rounded-2xl p-6 space-y-4">
            <h2 className="text-xl font-bold text-green-800">{offer.name}</h2>
            <p className="text-sm text-green-700">{offer.description}</p>
            {offer.parameters && (
              <div className="bg-white rounded-xl p-4 space-y-2">
                {Object.entries(offer.parameters).map(([key, value]) => (
                  <div key={key} className="flex justify-between text-sm">
                    <span className="text-gray-500 capitalize">{key.replace(/_/g, " ")}</span>
                    <span className="font-medium text-gray-900">{String(value)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {error && <p className="text-sm text-red-600 bg-red-50 p-3 rounded-lg">{error}</p>}

          <div className="flex gap-3">
            <button
              onClick={() => handleRespond("reject")}
              disabled={loading}
              className="flex-1 py-3 rounded-xl border-2 border-gray-200 text-gray-700 font-medium disabled:opacity-50"
            >
              {loading ? <Loader2 size={16} className="inline animate-spin mr-2" /> : null}
              Proceed with Cancel
            </button>
            <button
              onClick={() => handleRespond("accept")}
              disabled={loading}
              className="flex-1 py-3 rounded-xl text-white font-medium disabled:opacity-50"
              style={{ backgroundColor: brandConfig.colors.primary || "#2563eb" }}
            >
              {loading ? <Loader2 size={16} className="inline animate-spin mr-2" /> : null}
              Accept Offer
            </button>
          </div>
        </>
      )}

      {step === "confirm" && (
        <>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-red-50">
              <AlertTriangle size={24} className="text-red-600" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Confirm Cancellation</h1>
              <p className="text-gray-500 text-sm">No retention offers matched your profile.</p>
            </div>
          </div>

          <div className="bg-red-50 border border-red-200 rounded-xl p-4 space-y-2">
            <p className="text-sm text-red-800 font-medium">What happens next:</p>
            <ul className="text-sm text-red-700 space-y-1 list-disc list-inside">
              <li>Your service will be suspended after the current billing cycle</li>
              <li>Outstanding invoices remain payable</li>
              <li>Equipment must be returned within 14 days</li>
            </ul>
          </div>

          {error && <p className="text-sm text-red-600 bg-red-50 p-3 rounded-lg">{error}</p>}

          <div className="flex gap-3">
            <button onClick={() => router.back()} className="flex-1 py-3 rounded-xl border-2 border-gray-200 text-gray-700 font-medium">
              Go Back
            </button>
            <button
              onClick={() => handleRespond("reject")}
              disabled={loading}
              className="flex-1 py-3 rounded-xl text-white font-medium disabled:opacity-50"
              style={{ backgroundColor: brandConfig.colors.error || "#dc2626" }}
            >
              {loading ? <Loader2 size={16} className="inline animate-spin mr-2" /> : null}
              Confirm Cancel
            </button>
          </div>
        </>
      )}

      {step === "done" && (
        <div className="text-center space-y-6 py-8">
          <div className="p-4 rounded-full bg-green-50 w-20 h-20 mx-auto flex items-center justify-center">
            <CheckCircle size={40} className="text-green-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {offer ? "Offer Accepted!" : "Cancellation Confirmed"}
            </h1>
            <p className="text-gray-500 mt-2">
              {offer
                ? "Your retention offer has been applied. Your service continues as normal."
                : "Your cancellation request has been processed. You will receive a confirmation email shortly."}
            </p>
          </div>
          <button
            onClick={() => router.push("/dashboard")}
            className="px-8 py-3 rounded-xl text-white font-medium"
            style={{ backgroundColor: brandConfig.colors.primary || "#2563eb" }}
          >
            Back to Dashboard
          </button>
        </div>
      )}
    </div>
  );
}
