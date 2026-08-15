"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "expo-router";
import {
  Wrench, MapPin, Phone, Clock, ChevronRight, Star, Timer,
} from "lucide-react";
import { technicianApi } from "@/lib/api/client";
import type { TechJob, TechStats } from "@/lib/api/types";

// ── Brand Config ──────────────────────────────────────────────────────

const brandConfig = {
  colors: {
    primary: "#6366f1",
    background: "#0f172a",
    surface: "#1e293b",
    surfaceElevated: "#334155",
    text: "#f8fafc",
    textSecondary: "#94a3b8",
    border: "#334155",
  },
};

// ── Priority Badge ────────────────────────────────────────────────────

function PriorityBadge({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    URGENT: "bg-red-500/20 text-red-400 border border-red-500/30",
    HIGH: "bg-orange-500/20 text-orange-400 border border-orange-500/30",
    NORMAL: "bg-blue-500/20 text-blue-400 border border-blue-500/30",
    LOW: "bg-slate-600/60 text-slate-300 border border-slate-500/30",
  };
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${colors[priority] || colors.NORMAL}`}>
      {priority}
    </span>
  );
}

function CategoryBadge({ category }: { category: string | null }) {
  return (
    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-slate-600/60 text-slate-300">
      {category || "UNCATEGORIZED"}
    </span>
  );
}

// ── Job Card ──────────────────────────────────────────────────────────

function JobCard({ job, onSelect }: { job: TechJob; onSelect: (j: TechJob) => void }) {
  return (
    <div
      className="bg-slate-800 border border-slate-700 rounded-lg p-3 cursor-pointer active:border-indigo-500/50"
      onClick={() => onSelect(job)}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <PriorityBadge priority={job.priority} />
            <CategoryBadge category={job.category} />
          </div>
          <p className="font-medium text-sm text-slate-100 truncate">{job.subject}</p>
          <p className="text-xs text-slate-400 mt-0.5">{job.customer_name || job.customer_id}</p>
          <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
            <span className="flex items-center gap-1">
              <Phone className="h-3 w-3" />{job.customer_phone || "N/A"}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {new Date(job.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1 truncate flex items-center gap-1">
            <MapPin className="h-3 w-3 shrink-0" />{job.customer_address || "N/A"}
          </p>
        </div>
        <ChevronRight className="h-4 w-4 text-slate-400 self-center ml-2 shrink-0" />
      </div>
    </div>
  );
}

// ── Stats Header ─────────────────────────────────────────────────────

function StatsHeader({ stats }: { stats: TechStats }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-center">
        <Wrench className="h-4 w-4 text-violet-400 mx-auto mb-1" />
        <p className="text-lg font-bold text-slate-100">{stats.jobs_today}</p>
        <p className="text-[10px] text-slate-400">Today</p>
      </div>
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-center">
        <Timer className="h-4 w-4 text-blue-400 mx-auto mb-1" />
        <p className="text-lg font-bold text-slate-100">{stats.avg_resolution_min}m</p>
        <p className="text-[10px] text-slate-400">Avg Time</p>
      </div>
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-center">
        <Star className="h-4 w-4 text-amber-400 mx-auto mb-1" />
        <p className="text-lg font-bold text-slate-100">{stats.customer_rating}</p>
        <p className="text-[10px] text-slate-400">Rating</p>
      </div>
    </div>
  );
}

// ── Filter Tabs ──────────────────────────────────────────────────────

type FilterType = "ALL" | "OPEN" | "IN_PROGRESS";

function FilterTabs({
  filter,
  setFilter,
  jobCounts,
}: {
  filter: FilterType;
  setFilter: (f: FilterType) => void;
  jobCounts: Record<FilterType, number>;
}) {
  return (
    <div className="flex gap-1">
      {(["ALL", "OPEN", "IN_PROGRESS"] as FilterType[]).map((f) => (
        <button
          key={f}
          onClick={() => setFilter(f)}
          className={`px-3 py-1 text-xs rounded-md transition-colors font-semibold ${
            filter === f
              ? "bg-indigo-500 text-white"
              : "bg-slate-700 text-slate-400 active:text-slate-100"
          }`}
        >
          {f === "ALL" ? "All" : f === "OPEN" ? "Open" : "In Progress"} ({jobCounts[f]})
        </button>
      ))}
    </div>
  );
}

// ── Job Queue Page ────────────────────────────────────────────────────

export default function JobQueuePage() {
  const router = useRouter();
  const [jobs, setJobs] = useState<TechJob[]>([]);
  const [stats, setStats] = useState<TechStats>({
    jobs_today: 0,
    jobs_week: 0,
    avg_resolution_min: 0,
    fcr_rate: 0,
    customer_rating: 0,
    revenue_generated: 0,
  });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterType>("ALL");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [j, s] = await Promise.all([
        technicianApi.getMyJobs(),
        technicianApi.getMyStats(),
      ]);
      setJobs(j);
      if (s) setStats(s);
    } catch (e) {
      console.error("Failed to load jobs:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Real-time SSE subscription for job dispatch
  useEffect(() => {
    const unsubscribe = technicianApi.streamJobEvents((evt) => {
      if (evt.event === "new_ticket") {
        const newJob = evt.data as TechJob;
        setJobs((prev) => {
          if (prev.find((j) => j.id === newJob.id)) return prev;
          return [newJob, ...prev];
        });
      } else if (evt.event === "ticket_update") {
        const updatedJob = evt.data as TechJob;
        setJobs((prev) => prev.map((j) => (j.id === updatedJob.id ? updatedJob : j)));
      }
    });
    return unsubscribe;
  }, []);

  const filteredJobs = jobs.filter((j) => filter === "ALL" || j.status === filter);
  const jobCounts: Record<FilterType, number> = {
    ALL: jobs.length,
    OPEN: jobs.filter((j) => j.status === "OPEN").length,
    IN_PROGRESS: jobs.filter((j) => j.status === "IN_PROGRESS").length,
  };

  const handleSelectJob = (job: TechJob) => {
    router.push(`/job/${job.id}` as any);
  };

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-slate-900 px-4 pt-12 pb-3 border-b border-slate-700">
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-xl font-bold text-slate-100">Technician</h1>
          <span className="text-xs text-slate-400 bg-slate-800 px-2 py-1 rounded">
            v0.1.0
          </span>
        </div>
      </div>

      <div className="px-4 py-4 space-y-4">
        {/* Stats header */}
        <StatsHeader stats={stats} />

        {/* Filter tabs */}
        <FilterTabs filter={filter} setFilter={setFilter} jobCounts={jobCounts} />

        {/* Job list */}
        {loading ? (
          <p className="text-xs text-slate-400 text-center py-8">Loading jobs...</p>
        ) : filteredJobs.length > 0 ? (
          <div className="space-y-2">
            {filteredJobs.map((j) => (
              <JobCard key={j.id} job={j} onSelect={handleSelectJob} />
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-400 text-center py-8">No jobs in queue</p>
        )}
      </div>
    </div>
  );
}
