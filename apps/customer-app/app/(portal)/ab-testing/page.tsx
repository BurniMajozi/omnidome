"use client";

import { useEffect, useState, useCallback } from "react";
import {
  FlaskConical, Play, Square, Trash2, Plus, TrendingUp,
  Users, Target, Award, Clock, Pause, BarChart3,
} from "lucide-react";
import { api } from "@/lib/api/client";
import type { ABTest, ABTestCreate, ABTestResults } from "@/lib/api/types";
import brandConfig from "@/config/brand.json";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-100 text-gray-700",
  running: "bg-green-100 text-green-700",
  paused: "bg-yellow-100 text-yellow-700",
  completed: "bg-blue-100 text-blue-700",
};

const STATUS_ICONS: Record<string, typeof Clock> = {
  draft: Clock,
  running: Play,
  paused: Pause,
  completed: Award,
};

export default function ABTestingPage() {
  const [tests, setTests] = useState<ABTest[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedTest, setSelectedTest] = useState<(ABTest & { results?: ABTestResults }) | null>(null);
  const [form, setForm] = useState<ABTestCreate>({
    name: "",
    journey_a_id: "",
    journey_b_id: "",
    traffic_split: 50,
  });

  const loadTests = useCallback(async () => {
    try {
      const data = await api.getABTests();
      setTests(data);
    } catch {
      // API not available yet — show empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadTests(); }, [loadTests]);

  const handleCreate = async () => {
    if (!form.name || !form.journey_a_id || !form.journey_b_id) return;
    try {
      await api.createABTest(form);
      setShowCreate(false);
      setForm({ name: "", journey_a_id: "", journey_b_id: "", traffic_split: 50 });
      loadTests();
    } catch { /* TODO: toast */ }
  };

  const handleStart = async (id: string) => {
    try { await api.startABTest(id); loadTests(); } catch { /* TODO */ }
  };

  const handleStop = async (id: string) => {
    try { await api.stopABTest(id); loadTests(); } catch { /* TODO */ }
  };

  const handleDelete = async (id: string) => {
    try { await api.deleteABTest(id); loadTests(); } catch { /* TODO */ }
  };

  const viewDetails = async (test: ABTest) => {
    try {
      const details = await api.getABTest(test.id);
      setSelectedTest(details);
    } catch {
      setSelectedTest(test);
    }
  };

  if (loading) return <div className="p-6 text-center text-gray-500">Loading A/B tests...</div>;

  return (
    <div className="p-4 lg:p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <FlaskConical size={24} style={{ color: brandConfig.colors.primary }} />
            A/B Testing
          </h1>
          <p className="text-gray-500 mt-1">Manage retention journey experiments</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-white text-sm font-medium"
          style={{ backgroundColor: brandConfig.colors.primary }}
        >
          <Plus size={16} /> New Test
        </button>
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
            <h2 className="text-lg font-bold text-gray-900">Create A/B Test</h2>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Test Name</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:outline-none"
                style={{ "--tw-ring-color": brandConfig.colors.primary } as any}
                placeholder="e.g. Discount vs Upgrade Offer"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Journey A ID</label>
              <input
                type="text"
                value={form.journey_a_id}
                onChange={(e) => setForm({ ...form, journey_a_id: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:outline-none"
                placeholder="UUID of first journey"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Journey B ID</label>
              <input
                type="text"
                value={form.journey_b_id}
                onChange={(e) => setForm({ ...form, journey_b_id: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:outline-none"
                placeholder="UUID of second journey"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Traffic Split: {form.traffic_split}% to B
              </label>
              <input
                type="range"
                min={0}
                max={100}
                value={form.traffic_split}
                onChange={(e) => setForm({ ...form, traffic_split: Number(e.target.value) })}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-gray-500">
                <span>A: {100 - form.traffic_split}%</span>
                <span>B: {form.traffic_split}%</span>
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setShowCreate(false)}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                className="flex-1 px-4 py-2 rounded-lg text-white text-sm font-medium"
                style={{ backgroundColor: brandConfig.colors.primary }}
              >
                Create Test
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Detail Modal */}
      {selectedTest && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-gray-900">{selectedTest.name}</h2>
              <button onClick={() => setSelectedTest(null)} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
            </div>
            <div className="flex items-center gap-2">
              <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[selectedTest.status]}`}>
                {selectedTest.status}
              </span>
              {selectedTest.winner && (
                <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-700">
                  Winner: {selectedTest.winner.toUpperCase()}
                </span>
              )}
            </div>
            {selectedTest.results && (
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-gray-50 rounded-xl p-4">
                  <div className="text-sm font-medium text-gray-500 mb-2">Variant A</div>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between"><span className="text-gray-500">Assignments</span><span className="font-medium">{selectedTest.results.variant_a.assignments}</span></div>
                    <div className="flex justify-between"><span className="text-gray-500">Outcomes</span><span className="font-medium">{selectedTest.results.variant_a.outcomes}</span></div>
                    <div className="flex justify-between"><span className="text-gray-500">Accept Rate</span><span className="font-medium">{selectedTest.results.variant_a.acceptance_rate.toFixed(1)}%</span></div>
                  </div>
                </div>
                <div className="bg-gray-50 rounded-xl p-4">
                  <div className="text-sm font-medium text-gray-500 mb-2">Variant B</div>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between"><span className="text-gray-500">Assignments</span><span className="font-medium">{selectedTest.results.variant_b.assignments}</span></div>
                    <div className="flex justify-between"><span className="text-gray-500">Outcomes</span><span className="font-medium">{selectedTest.results.variant_b.outcomes}</span></div>
                    <div className="flex justify-between"><span className="text-gray-500">Accept Rate</span><span className="font-medium">{selectedTest.results.variant_b.acceptance_rate.toFixed(1)}%</span></div>
                  </div>
                </div>
              </div>
            )}
            <div className="text-xs text-gray-500 space-y-1">
              <div>Journey A: <span className="font-mono">{selectedTest.journey_a_id}</span></div>
              <div>Journey B: <span className="font-mono">{selectedTest.journey_b_id}</span></div>
              <div>Traffic Split: {selectedTest.traffic_split}% to B</div>
              {selectedTest.started_at && <div>Started: {new Date(selectedTest.started_at).toLocaleString()}</div>}
              {selectedTest.ended_at && <div>Ended: {new Date(selectedTest.ended_at).toLocaleString()}</div>}
            </div>
          </div>
        </div>
      )}

      {/* Test List */}
      {tests.length === 0 ? (
        <div className="text-center py-16">
          <FlaskConical size={48} className="mx-auto text-gray-300 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-1">No A/B tests yet</h3>
          <p className="text-gray-500 text-sm mb-4">Create your first experiment to compare retention journeys</p>
          <button
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-white text-sm font-medium"
            style={{ backgroundColor: brandConfig.colors.primary }}
          >
            <Plus size={16} /> Create Test
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {tests.map((test) => {
            const StatusIcon = STATUS_ICONS[test.status] || Clock;
            return (
              <div
                key={test.id}
                className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md transition-shadow cursor-pointer"
                onClick={() => viewDetails(test)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: brandConfig.colors.primary + "15" }}>
                      <FlaskConical size={20} style={{ color: brandConfig.colors.primary }} />
                    </div>
                    <div>
                      <div className="font-medium text-gray-900">{test.name}</div>
                      <div className="text-xs text-gray-500">
                        {test.traffic_split}% traffic to B &middot; {new Date(test.created_at).toLocaleDateString()}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[test.status]}`}>
                      <StatusIcon size={12} /> {test.status}
                    </span>
                    {test.winner && (
                      <span className="px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-700">
                        {test.winner.toUpperCase()} wins
                      </span>
                    )}
                    {test.status === "draft" && (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleStart(test.id); }}
                        className="p-1.5 rounded-lg hover:bg-green-50 text-green-600"
                        title="Start test"
                      >
                        <Play size={16} />
                      </button>
                    )}
                    {test.status === "running" && (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleStop(test.id); }}
                        className="p-1.5 rounded-lg hover:bg-red-50 text-red-600"
                        title="Stop test"
                      >
                        <Square size={16} />
                      </button>
                    )}
                    {(test.status === "draft" || test.status === "completed") && (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDelete(test.id); }}
                        className="p-1.5 rounded-lg hover:bg-red-50 text-red-400"
                        title="Delete"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
