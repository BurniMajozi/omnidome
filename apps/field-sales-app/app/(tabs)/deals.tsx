"use client";

import { useState, useEffect, useCallback } from "react";
import { TrendingUp } from "lucide-react";
import { fieldSalesApi } from "@/lib/api/client";
import type { MobileDeal } from "@/lib/api/types";

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

/* ─── Deals Tab ─────────────────────────────────────────────────────── */

export default function DealsTab() {
  const [deals, setDeals] = useState<MobileDeal[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const d = await fieldSalesApi.listDeals({ status: "OPEN" });
      setDeals(d);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Polling fallback — refresh deals every 30s
  useEffect(() => {
    const interval = setInterval(() => {
      fieldSalesApi.listDeals({ status: "OPEN" }).then(setDeals).catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-400">{deals.length} open deals</p>
      {loading ? (
        <p className="text-xs text-slate-400 text-center py-8">Loading...</p>
      ) : (
        <div className="space-y-2">
          {deals.map(d => (
            <UICard key={d.id}>
              <div className="p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-sm text-slate-100">{d.name}</p>
                    <p className="text-xs text-slate-400">{d.stage_name}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-emerald-400">R{d.value_zar.toLocaleString()}</p>
                    <UIBadge className="text-[10px] bg-blue-500/20 text-blue-400">{d.status}</UIBadge>
                  </div>
                </div>
              </div>
            </UICard>
          ))}
          {deals.length === 0 && (
            <div className="text-center py-8">
              <TrendingUp className="h-8 w-8 text-slate-600 mx-auto mb-2" />
              <p className="text-xs text-slate-400">No open deals</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
