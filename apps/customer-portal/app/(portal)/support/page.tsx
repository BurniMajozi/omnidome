"use client";

import { useEffect, useState } from "react";
import { Plus, MessageSquare, Clock, CheckCircle, AlertCircle, ChevronRight, Send } from "lucide-react";
import brandConfig from "@/config/brand.json";

interface Ticket { id: string; subject: string; status: string; priority: string; created_at: string; last_reply?: string; }

export default function SupportPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [creating, setCreating] = useState(false);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [category, setCategory] = useState("technical");

  useEffect(() => {
    setTickets([
      { id: "1", subject: "Intermittent connection drops", status: "open", priority: "high", created_at: "2026-06-03", last_reply: "2026-06-04" },
      { id: "2", subject: "Router replacement request", status: "resolved", priority: "medium", created_at: "2026-05-28", last_reply: "2026-05-30" },
    ]);
  }, []);

  const statusConfig: Record<string, { color: string; icon: React.ElementType }> = {
    open: { color: "bg-blue-50 text-blue-700", icon: Clock },
    pending: { color: "bg-yellow-50 text-yellow-700", icon: AlertCircle },
    resolved: { color: "bg-green-50 text-green-700", icon: CheckCircle },
  };

  const createTicket = async () => {
    if (!subject || !message) return;
    setTickets((prev) => [{
      id: String(prev.length + 1), subject, status: "open", priority: "medium",
      created_at: new Date().toISOString().split("T")[0],
    }, ...prev]);
    setCreating(false);
    setSubject("");
    setMessage("");
  };

  return (
    <div className="p-4 lg:p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Support</h1>
          <p className="text-gray-500 mt-1">Get help with your service</p>
        </div>
        <button onClick={() => setCreating(!creating)}
          className="px-4 py-2 rounded-lg text-white text-sm font-medium flex items-center gap-1.5"
          style={{ backgroundColor: brandConfig.colors.primary }}>
          <Plus size={14} /> New Ticket
        </button>
      </div>

      {/* Contact info */}
      <div className="flex gap-3">
        {brandConfig.contact.phone && (
          <a href={`tel:${brandConfig.contact.phone}`} className="flex-1 bg-white rounded-xl border border-gray-200 p-3 text-center">
            <p className="text-xs text-gray-500">Call</p>
            <p className="text-sm font-medium text-gray-900">{brandConfig.contact.phone}</p>
          </a>
        )}
        {brandConfig.contact.email && (
          <a href={`mailto:${brandConfig.contact.email}`} className="flex-1 bg-white rounded-xl border border-gray-200 p-3 text-center">
            <p className="text-xs text-gray-500">Email</p>
            <p className="text-sm font-medium text-gray-900 truncate">{brandConfig.contact.email}</p>
          </a>
        )}
      </div>

      {/* Create form */}
      {creating && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Category</label>
            <select value={category} onChange={(e) => setCategory(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2" style={{ "--tw-ring-color": brandConfig.colors.primary } as React.CSSProperties}>
              <option value="technical">Technical Issue</option>
              <option value="billing">Billing Query</option>
              <option value="account">Account Management</option>
              <option value="fault">Report Fault</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Subject</label>
            <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Brief description..."
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2" style={{ "--tw-ring-color": brandConfig.colors.primary } as React.CSSProperties} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Message</label>
            <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={4} placeholder="Describe your issue..."
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm resize-none focus:outline-none focus:ring-2" style={{ "--tw-ring-color": brandConfig.colors.primary } as React.CSSProperties} />
          </div>
          <div className="flex gap-2">
            <button onClick={createTicket}
              className="flex-1 py-2 rounded-lg text-white text-sm font-medium flex items-center justify-center gap-1"
              style={{ backgroundColor: brandConfig.colors.primary }}>
              <Send size={14} /> Submit
            </button>
            <button onClick={() => setCreating(false)} className="px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-600">Cancel</button>
          </div>
        </div>
      )}

      {/* Ticket list */}
      <div className="space-y-2">
        {tickets.map((t) => {
          const cfg = statusConfig[t.status] || statusConfig.open;
          const Icon = cfg.icon;
          return (
            <div key={t.id} className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <MessageSquare size={16} className="text-gray-400 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{t.subject}</p>
                    <p className="text-xs text-gray-500">{t.created_at}{t.last_reply ? ` · Last reply: ${t.last_reply}` : ""}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${cfg.color}`}>
                    <Icon size={10} />{t.status}
                  </span>
                  <ChevronRight size={14} className="text-gray-400" />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
