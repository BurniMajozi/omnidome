"use client";

/**
 * Support — Unified conversational support page.
 *
 * Replaces the old split between support/page.tsx (form + ticket list)
 * and assistant/page.tsx (AI chat). Both concerns live here:
 *
 *  - The AI handles the conversation first — it can diagnose issues,
 *    answer billing questions, and create tickets on behalf of the customer.
 *  - A "Tickets" tab surfaces existing tickets and any created in this session.
 *  - No context-switching required.
 */

import { useState, useCallback } from "react";
import {
  MessageSquare, Ticket, Clock, CheckCircle, AlertCircle,
  ChevronRight, Plus, Phone, Mail,
} from "lucide-react";
import { AgentChat } from "@/components/chat/AgentChat";
import { useAuthStore } from "@/lib/stores/auth-store";
import brandConfig from "@/config/brand.json";

interface SupportTicket {
  id: string;
  subject: string;
  status: "open" | "pending" | "resolved";
  priority: "low" | "medium" | "high";
  created_at: string;
  last_reply?: string;
  source?: "ai" | "form";
}

const STATUS_CONFIG: Record<SupportTicket["status"], { label: string; color: string; icon: typeof Clock }> = {
  open: { label: "Open", color: "bg-blue-50 text-blue-700", icon: Clock },
  pending: { label: "Pending", color: "bg-amber-50 text-amber-700", icon: AlertCircle },
  resolved: { label: "Resolved", color: "bg-green-50 text-green-700", icon: CheckCircle },
};

// Seed with realistic mock data — replace with api.getTickets() when ready
const INITIAL_TICKETS: SupportTicket[] = [
  {
    id: "TKT-1001",
    subject: "Intermittent connection drops",
    status: "open",
    priority: "high",
    created_at: "2026-06-03",
    last_reply: "2026-06-04",
  },
  {
    id: "TKT-1000",
    subject: "Router replacement request",
    status: "resolved",
    priority: "medium",
    created_at: "2026-05-28",
    last_reply: "2026-05-30",
  },
];

type Tab = "chat" | "tickets";

export default function SupportPage() {
  const customer = useAuthStore((s) => s.customer);
  const [tab, setTab] = useState<Tab>("chat");
  const [tickets, setTickets] = useState<SupportTicket[]>(INITIAL_TICKETS);
  const [newTicketBadge, setNewTicketBadge] = useState(false);

  // Fired by AgentChat when the AI creates a ticket via the create_support_ticket tool
  const handleTicketCreated = useCallback(
    (ticket: { ticketId: string; subject: string; status: string }) => {
      setTickets((prev) => [
        {
          id: ticket.ticketId,
          subject: ticket.subject,
          status: (ticket.status as SupportTicket["status"]) || "open",
          priority: "medium",
          created_at: new Date().toISOString().split("T")[0],
          source: "ai",
        },
        ...prev,
      ]);
      // Flash badge on the tickets tab so the customer knows a ticket was created
      setNewTicketBadge(true);
    },
    [],
  );

  const openCount = tickets.filter((t) => t.status === "open" || t.status === "pending").length;

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Tab bar */}
      <div className="flex items-center gap-0 border-b border-gray-200 bg-white shrink-0 px-4">
        <button
          onClick={() => setTab("chat")}
          className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
            tab === "chat"
              ? "border-current text-current"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
          style={tab === "chat" ? { color: brandConfig.colors.primary, borderColor: brandConfig.colors.primary } : undefined}
        >
          <MessageSquare size={15} />
          Chat with AI
        </button>

        <button
          onClick={() => { setTab("tickets"); setNewTicketBadge(false); }}
          className={`relative flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
            tab === "tickets"
              ? "border-current text-current"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
          style={tab === "tickets" ? { color: brandConfig.colors.primary, borderColor: brandConfig.colors.primary } : undefined}
        >
          <Ticket size={15} />
          My Tickets
          {openCount > 0 && (
            <span
              className={`ml-0.5 min-w-[18px] h-[18px] rounded-full text-white text-[10px] font-bold flex items-center justify-center px-1 ${
                newTicketBadge ? "animate-bounce" : ""
              }`}
              style={{ backgroundColor: brandConfig.colors.primary }}
            >
              {openCount}
            </span>
          )}
        </button>
      </div>

      {/* Chat tab */}
      {tab === "chat" && (
        <div className="flex-1 min-h-0">
          <AgentChat
            initialAgent="customer_facing"
            theme="light"
            context={{
              customer_id: customer?.id ?? "",
              account_number: (customer as Record<string, unknown>)?.accountNumber ?? "",
              ui_context: "support_page",
            }}
            onTicketCreated={handleTicketCreated}
          />
        </div>
      )}

      {/* Tickets tab */}
      {tab === "tickets" && (
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Contact options */}
          <div className="flex gap-3">
            {brandConfig.contact?.phone && (
              <a
                href={`tel:${brandConfig.contact.phone}`}
                className="flex-1 bg-white rounded-xl border border-gray-200 p-3 text-center hover:bg-gray-50 transition-colors"
              >
                <Phone size={14} className="mx-auto mb-1 text-gray-400" />
                <p className="text-[10px] text-gray-400">Call us</p>
                <p className="text-xs font-semibold text-gray-800">{brandConfig.contact.phone}</p>
              </a>
            )}
            {brandConfig.contact?.email && (
              <a
                href={`mailto:${brandConfig.contact.email}`}
                className="flex-1 bg-white rounded-xl border border-gray-200 p-3 text-center hover:bg-gray-50 transition-colors"
              >
                <Mail size={14} className="mx-auto mb-1 text-gray-400" />
                <p className="text-[10px] text-gray-400">Email us</p>
                <p className="text-xs font-semibold text-gray-800 truncate">{brandConfig.contact.email}</p>
              </a>
            )}
          </div>

          {/* Tip to use AI */}
          <div
            className="rounded-xl p-3 flex items-start gap-3"
            style={{ backgroundColor: brandConfig.colors.primary + "12" }}
          >
            <MessageSquare size={16} style={{ color: brandConfig.colors.primary }} className="mt-0.5 shrink-0" />
            <div>
              <p className="text-xs font-semibold" style={{ color: brandConfig.colors.primary }}>
                Need help fast?
              </p>
              <p className="text-xs text-gray-600 mt-0.5">
                Our AI can diagnose issues and open a ticket for you instantly — no form required.
              </p>
              <button
                onClick={() => setTab("chat")}
                className="mt-1.5 text-xs font-semibold underline"
                style={{ color: brandConfig.colors.primary }}
              >
                Chat with AI →
              </button>
            </div>
          </div>

          {/* Ticket list */}
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Your tickets
            </p>
            <div className="space-y-2">
              {tickets.length === 0 ? (
                <div className="bg-white rounded-xl border border-gray-200 p-6 text-center">
                  <p className="text-sm text-gray-500">No tickets yet.</p>
                  <button
                    onClick={() => setTab("chat")}
                    className="mt-2 text-xs font-medium underline"
                    style={{ color: brandConfig.colors.primary }}
                  >
                    Ask our AI for help
                  </button>
                </div>
              ) : (
                tickets.map((ticket) => {
                  const cfg = STATUS_CONFIG[ticket.status];
                  const Icon = cfg.icon;
                  return (
                    <div
                      key={ticket.id}
                      className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-3"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <p className="text-sm font-medium text-gray-900 truncate">
                            {ticket.subject}
                          </p>
                          {ticket.source === "ai" && (
                            <span className="shrink-0 text-[9px] font-semibold px-1.5 py-0.5 rounded-full bg-indigo-50 text-indigo-600">
                              AI
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-gray-400">
                          {ticket.id} · {ticket.created_at}
                          {ticket.last_reply ? ` · Updated ${ticket.last_reply}` : ""}
                        </p>
                      </div>
                      <span className={`shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${cfg.color}`}>
                        <Icon size={9} />
                        {cfg.label}
                      </span>
                      <ChevronRight size={14} className="text-gray-300 shrink-0" />
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
