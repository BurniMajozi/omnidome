"use client";

import { useState, useEffect, useCallback } from "react";
import { DollarSign } from "lucide-react";
import { fieldSalesApi } from "@/lib/api/client";
import type { MobileCommission } from "@/lib/api/types";

/* ─── Inline UI primitives ──────────────────────────────────────────── */

function UICard({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`border border-[#334155] bg-[#1e293b] rounded-xl ${className}`}>
      {children}
    </div>
  );
}

function UIBadge({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium ${className}`}>
      {children}
    </span>
  );
}

/* ─── Commissions Tab ───────────────────────────────────────────────── */

export default function CommissionsTab() {
  const [commissions, setCommissions] = useState<MobileCommission[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const c = await fieldSalesApi.getMyCommissions();
      setCommissions(c);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const totalPaid = commissions.filter(c => c.status === "PAID").reduce((s, c) => s + c.amount_zar, 0);
  const totalPending = commissions.filter(c => c.status === "PENDING").reduce((s, c) => s + c.amount_zar, 0);

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid grid-cols-2 gap-2">
        <UICard><div className="p-3 text-center">
          <p className="text-lg font-bold text-emerald-400">R{totalPaid.toLocaleString()}</p>
          <p className="text-[10px] text-slate-400">Paid Out</p>
        </div></UICard>
        <UICard><div className="p-3 text-center">
          <p className="text-lg font-bold text-amber-400">R{totalPending.toLocaleString()}</p>
          <p className="text-[10px] text-slate-400">Pending</p>
        </div></UICard>
      </div>

      <p className="text-xs text-slate-400">Your commissions</p>
      {loading ? (
        <p className="text-xs text-slate-400 text-center py-8">Loading...</p>
      ) : (
        <div className="space-y-2">
          {commissions.map(c => (
            <UICard key={c.id}>
              <div className="p-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-100">R{c.amount_zar.toLocaleString()}</p>
                  <p className="text-xs text-slate-400">{c.rate_percent}% rate</p>
                </div>
                <UIBadge className={`text-[10px] ${c.status === "PAID" ? "bg-emerald-500/20 text-emerald-400" : c.status === "PENDING" ? "bg-amber-500/20 text-amber-400" : "bg-slate-700 text-slate-300"}`}>
                  {c.status}
                </UIBadge>
              </div>
            </UICard>
          ))}
          {commissions.length === 0 && (
            <div className="text-center py-8">
              <DollarSign className="h-8 w-8 text-slate-600 mx-auto mb-2" />
              <p className="text-xs text-slate-400">No commissions yet</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
