"use client";

import { useState, useEffect, useCallback } from "react";
import { Wrench, Clock, CheckCircle2, DollarSign, Star, TrendingUp } from "lucide-react";
import { technicianApi } from "@/lib/api/client";
import type { TechStats } from "@/lib/api/types";

// ── Stat Card Component ───────────────────────────────────────────────

function StatCard({
  icon,
  label,
  value,
  sublabel,
  accentColor,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sublabel?: string;
  accentColor: string;
}) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 text-center">
      <div className="flex justify-center mb-2">{icon}</div>
      <p className="text-2xl font-bold text-slate-100">{value}</p>
      <p className="text-xs text-slate-400 mt-1">{label}</p>
      {sublabel && <p className="text-[10px] text-slate-500 mt-0.5">{sublabel}</p>}
    </div>
  );
}

// ── Stats Page ────────────────────────────────────────────────────────

export default function StatsPage() {
  const [stats, setStats] = useState<TechStats>({
    jobs_today: 0,
    jobs_week: 0,
    avg_resolution_min: 0,
    fcr_rate: 0,
    customer_rating: 0,
    revenue_generated: 0,
  });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const s = await technicianApi.getMyStats();
      if (s) setStats(s);
    } catch (e) {
      console.error("Failed to load stats:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-slate-900 px-4 pt-12 pb-3 border-b border-slate-700">
        <h1 className="text-xl font-bold text-slate-100">My Stats</h1>
        <p className="text-xs text-slate-400 mt-0.5">Your performance overview</p>
      </div>

      <div className="px-4 py-4 space-y-6 pb-24">
        {/* Today Summary */}
        <div>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Today</h2>
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-center">
              <Wrench className="h-4 w-4 text-violet-400 mx-auto mb-1" />
              <p className="text-lg font-bold text-slate-100">{stats.jobs_today}</p>
              <p className="text-[10px] text-slate-400">Completed</p>
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-center">
              <Clock className="h-4 w-4 text-blue-400 mx-auto mb-1" />
              <p className="text-lg font-bold text-slate-100">{stats.avg_resolution_min}m</p>
              <p className="text-[10px] text-slate-400">Avg Time</p>
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-center">
              <Star className="h-4 w-4 text-amber-400 mx-auto mb-1" />
              <p className="text-lg font-bold text-slate-100">{stats.customer_rating}</p>
              <p className="text-[10px] text-slate-400">Rating</p>
            </div>
          </div>
        </div>

        {/* Weekly Stats */}
        <div>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">This Week</h2>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 text-center">
              <CheckCircle2 className="h-5 w-5 text-emerald-400 mx-auto mb-1" />
              <p className="text-2xl font-bold text-emerald-400">{stats.jobs_week}</p>
              <p className="text-xs text-slate-400">Jobs Completed</p>
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 text-center">
              <TrendingUp className="h-5 w-5 text-violet-400 mx-auto mb-1" />
              <p className="text-2xl font-bold text-violet-400">{stats.fcr_rate}%</p>
              <p className="text-xs text-slate-400">FCR Rate</p>
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 text-center">
              <DollarSign className="h-5 w-5 text-amber-400 mx-auto mb-1" />
              <p className="text-2xl font-bold text-amber-400">R{stats.revenue_generated.toLocaleString()}</p>
              <p className="text-xs text-slate-400">Revenue Generated</p>
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 text-center">
              <Star className="h-5 w-5 text-amber-400 mx-auto mb-1" />
              <div className="flex items-center justify-center gap-1">
                <p className="text-2xl font-bold text-amber-400">{stats.customer_rating}</p>
                <span className="text-amber-400 text-lg">★</span>
              </div>
              <p className="text-xs text-slate-400">Customer Rating</p>
            </div>
          </div>
        </div>

        {/* Performance Tip */}
        <div className="bg-slate-800 border border-indigo-500/30 rounded-lg p-4">
          <p className="text-xs font-semibold text-indigo-400 mb-1">💡 Tips</p>
          <p className="text-sm text-slate-300">
            {loading
              ? "Loading stats..."
              : stats.fcr_rate >= 80
                ? "Great FCR rate! Keep up the excellent first-call resolution work."
                : stats.fcr_rate >= 60
                  ? "Solid performance. Focus on resolving issues on first contact to boost your FCR rate."
                  : "Review common escalation patterns and check knowledge base for faster resolutions."}
          </p>
        </div>
      </div>
    </div>
  );
}
