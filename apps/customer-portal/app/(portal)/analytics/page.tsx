"use client";

import { useEffect, useState, useCallback } from "react";
import {
  BarChart3, Plus, Trash2, Edit3, Eye, TrendingUp,
  Users, DollarSign, Activity, Layout, Layers,
  LineChart, PieChart, Table, Filter,
} from "lucide-react";
import { api } from "@/lib/api/client";
import type { Dashboard, DashboardCreate, DashboardTemplate, WidgetConfig } from "@/lib/api/types";
import brandConfig from "@/config/brand.json";

const WIDGET_ICONS: Record<string, typeof LineChart> = {
  line_chart: LineChart,
  bar_chart: BarChart3,
  kpi_card: TrendingUp,
  table: Table,
  funnel: Filter,
};

const TEMPLATE_DESCRIPTIONS: Record<string, string> = {
  executive_summary: "High-level KPIs: MRR, active customers, churn rate, revenue",
  sales_pipeline: "Lead conversion funnel, pipeline value, win rates",
  customer_health: "NPS, support tickets, usage patterns, at-risk accounts",
  network_performance: "Uptime, latency, bandwidth utilization, incidents",
  financial_overview: "Revenue, collections, aging, outstanding balances",
};

export default function AnalyticsPage() {
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [templates, setTemplates] = useState<DashboardTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [selectedDashboard, setSelectedDashboard] = useState<(Dashboard & { widget_data?: any[] }) | null>(null);
  const [form, setForm] = useState<DashboardCreate>({ name: "", description: "", widget_config: [] });

  const loadDashboards = useCallback(async () => {
    try {
      const data = await api.getDashboards();
      setDashboards(data);
    } catch {
      // API not available yet
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTemplates = useCallback(async () => {
    try {
      const data = await api.getDashboardTemplates();
      setTemplates(data);
    } catch {
      // Fallback templates
      setTemplates([
        { id: "executive_summary", name: "Executive Summary", description: TEMPLATE_DESCRIPTIONS.executive_summary, widget_config: [] },
        { id: "sales_pipeline", name: "Sales Pipeline", description: TEMPLATE_DESCRIPTIONS.sales_pipeline, widget_config: [] },
        { id: "customer_health", name: "Customer Health", description: TEMPLATE_DESCRIPTIONS.customer_health, widget_config: [] },
        { id: "network_performance", name: "Network Performance", description: TEMPLATE_DESCRIPTIONS.network_performance, widget_config: [] },
        { id: "financial_overview", name: "Financial Overview", description: TEMPLATE_DESCRIPTIONS.financial_overview, widget_config: [] },
      ]);
    }
  }, []);

  useEffect(() => { loadDashboards(); }, [loadDashboards]);

  const handleCreate = async () => {
    if (!form.name) return;
    try {
      await api.createDashboard(form);
      setShowCreate(false);
      setForm({ name: "", description: "", widget_config: [] });
      loadDashboards();
    } catch { /* TODO: toast */ }
  };

  const handleCreateFromTemplate = async (template: DashboardTemplate) => {
    try {
      await api.createDashboardFromTemplate(template.id, template.name);
      setShowTemplates(false);
      loadDashboards();
    } catch { /* TODO: toast */ }
  };

  const handleDelete = async (id: string) => {
    try { await api.deleteDashboard(id); loadDashboards(); } catch { /* TODO */ }
  };

  const viewDashboard = async (dash: Dashboard) => {
    try {
      const details = await api.getDashboard(dash.id);
      setSelectedDashboard(details);
    } catch {
      setSelectedDashboard(dash);
    }
  };

  const addWidget = (type: WidgetConfig["type"]) => {
    const titles: Record<string, string> = {
      line_chart: "Revenue Trend",
      bar_chart: "Plan Distribution",
      kpi_card: "Monthly Recurring Revenue",
      table: "Top Customers",
      funnel: "Conversion Funnel",
    };
    setForm({
      ...form,
      widget_config: [...form.widget_config, { type, title: titles[type] || "Widget", metric: "revenue" }],
    });
  };

  if (loading) return <div className="p-6 text-center text-gray-500">Loading dashboards...</div>;

  return (
    <div className="p-4 lg:p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <BarChart3 size={24} style={{ color: brandConfig.colors.primary }} />
            Analytics
          </h1>
          <p className="text-gray-500 mt-1">Custom dashboards and real-time metrics</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => { setShowTemplates(true); loadTemplates(); }}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <Layers size={16} /> Templates
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-white text-sm font-medium"
            style={{ backgroundColor: brandConfig.colors.primary }}
          >
            <Plus size={16} /> New Dashboard
          </button>
        </div>
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-bold text-gray-900">Create Dashboard</h2>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:outline-none"
                placeholder="e.g. Monthly Overview"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
              <input
                type="text"
                value={form.description || ""}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:outline-none"
                placeholder="Optional description"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Add Widgets</label>
              <div className="grid grid-cols-2 gap-2">
                {(["kpi_card", "line_chart", "bar_chart", "table", "funnel"] as const).map((type) => {
                  const Icon = WIDGET_ICONS[type] || BarChart3;
                  return (
                    <button
                      key={type}
                      onClick={() => addWidget(type)}
                      className="flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg text-sm text-gray-700 hover:bg-gray-50"
                    >
                      <Icon size={16} />
                      {type.replace("_", " ")}
                    </button>
                  );
                })}
              </div>
            </div>
            {form.widget_config.length > 0 && (
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700">Widgets ({form.widget_config.length})</label>
                {form.widget_config.map((w, i) => (
                  <div key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2 text-sm">
                    <span>{w.title}</span>
                    <button
                      onClick={() => setForm({ ...form, widget_config: form.widget_config.filter((_, idx) => idx !== i) })}
                      className="text-red-400 hover:text-red-600"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex gap-3 pt-2">
              <button onClick={() => setShowCreate(false)} className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50">Cancel</button>
              <button onClick={handleCreate} className="flex-1 px-4 py-2 rounded-lg text-white text-sm font-medium" style={{ backgroundColor: brandConfig.colors.primary }}>Create</button>
            </div>
          </div>
        </div>
      )}

      {/* Templates Modal */}
      {showTemplates && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-gray-900">Dashboard Templates</h2>
              <button onClick={() => setShowTemplates(false)} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
            </div>
            <div className="space-y-2">
              {templates.map((t) => (
                <div key={t.id} className="border border-gray-200 rounded-xl p-4 hover:border-gray-300 transition-colors">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium text-gray-900">{t.name}</span>
                    <button
                      onClick={() => handleCreateFromTemplate(t)}
                      className="px-3 py-1 rounded-lg text-white text-xs font-medium"
                      style={{ backgroundColor: brandConfig.colors.primary }}
                    >
                      Use Template
                    </button>
                  </div>
                  <p className="text-xs text-gray-500">{TEMPLATE_DESCRIPTIONS[t.id] || t.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Dashboard Detail Modal */}
      {selectedDashboard && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl p-6 space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-gray-900">{selectedDashboard.name}</h2>
                {selectedDashboard.description && <p className="text-sm text-gray-500">{selectedDashboard.description}</p>}
              </div>
              <button onClick={() => setSelectedDashboard(null)} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
            </div>
            {selectedDashboard.widget_config.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <BarChart3 size={40} className="mx-auto mb-3" />
                <p className="text-sm">No widgets configured</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {selectedDashboard.widget_config.map((w, i) => {
                  const Icon = WIDGET_ICONS[w.type] || BarChart3;
                  return (
                    <div key={i} className="bg-gray-50 rounded-xl p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <Icon size={16} className="text-gray-400" />
                        <span className="text-sm font-medium text-gray-700">{w.title}</span>
                      </div>
                      <div className="text-xs text-gray-400">{w.type.replace("_", " ")} &middot; {w.metric}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Dashboard List */}
      {dashboards.length === 0 ? (
        <div className="text-center py-16">
          <BarChart3 size={48} className="mx-auto text-gray-300 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-1">No dashboards yet</h3>
          <p className="text-gray-500 text-sm mb-4">Create a custom dashboard or start from a template</p>
          <div className="flex justify-center gap-3">
            <button
              onClick={() => { setShowTemplates(true); loadTemplates(); }}
              className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              <Layers size={16} /> Browse Templates
            </button>
            <button
              onClick={() => setShowCreate(true)}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-white text-sm font-medium"
              style={{ backgroundColor: brandConfig.colors.primary }}
            >
              <Plus size={16} /> Create Dashboard
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {dashboards.map((dash) => (
            <div
              key={dash.id}
              className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => viewDashboard(dash)}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: brandConfig.colors.primary + "15" }}>
                    <Layout size={20} style={{ color: brandConfig.colors.primary }} />
                  </div>
                  <div>
                    <div className="font-medium text-gray-900">{dash.name}</div>
                    <div className="text-xs text-gray-500">{dash.widget_config.length} widgets</div>
                  </div>
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={(e) => { e.stopPropagation(); viewDashboard(dash); }}
                    className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400"
                    title="View"
                  >
                    <Eye size={14} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(dash.id); }}
                    className="p-1.5 rounded-lg hover:bg-red-50 text-red-400"
                    title="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              {dash.description && (
                <p className="text-xs text-gray-500 mb-3">{dash.description}</p>
              )}
              <div className="flex flex-wrap gap-1">
                {dash.widget_config.map((w, i) => {
                  const Icon = WIDGET_ICONS[w.type] || BarChart3;
                  return (
                    <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 rounded text-xs text-gray-600">
                      <Icon size={10} /> {w.title}
                    </span>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
