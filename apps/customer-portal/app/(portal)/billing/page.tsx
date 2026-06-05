"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CreditCard, FileText, Download, ChevronRight, AlertCircle, CheckCircle, Clock, Plus } from "lucide-react";
import brandConfig from "@/config/brand.json";

interface Invoice {
  id: string; number: string; status: string;
  total_zar: number; due_date: string; created_at: string;
}

export default function BillingPage() {
  const [tab, setTab] = useState<"invoices" | "payments" | "methods">("invoices");
  const [invoices, setInvoices] = useState<Invoice[]>([]);

  useEffect(() => {
    setInvoices([
      { id: "1", number: "INV-2026-006", status: "pending", total_zar: 999, due_date: "2026-07-01", created_at: "2026-06-01" },
      { id: "2", number: "INV-2026-005", status: "paid", total_zar: 999, due_date: "2026-06-01", created_at: "2026-05-01" },
      { id: "3", number: "INV-2026-004", status: "paid", total_zar: 999, due_date: "2026-05-01", created_at: "2026-04-01" },
    ]);
  }, []);

  const outstanding = invoices.filter((i) => i.status === "pending" || i.status === "overdue").reduce((s, i) => s + i.total_zar, 0);
  const statusColors: Record<string, string> = { paid: "bg-green-50 text-green-700", pending: "bg-yellow-50 text-yellow-700", overdue: "bg-red-50 text-red-700" };
  const statusIcons: Record<string, React.ElementType> = { paid: CheckCircle, pending: Clock, overdue: AlertCircle };

  return (
    <div className="p-4 lg:p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Billing</h1>
        <p className="text-gray-500 mt-1">Manage your invoices and payments</p>
      </div>

      {outstanding > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <AlertCircle size={20} className="text-yellow-600" />
              <div>
                <p className="text-sm font-medium text-gray-900">Outstanding Balance</p>
                <p className="text-xs text-gray-500">Pay now to avoid service suspension</p>
              </div>
            </div>
            <p className="text-xl font-bold text-yellow-700">R{outstanding.toFixed(0)}</p>
          </div>
          <button className="mt-3 w-full py-2 rounded-lg text-white text-sm font-medium" style={{ backgroundColor: brandConfig.colors.warning }}>
            Pay Now
          </button>
        </div>
      )}

      <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
        {(["invoices", "payments", "methods"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`flex-1 py-2 px-3 rounded-md text-sm font-medium capitalize transition-colors ${tab === t ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>
            {t}
          </button>
        ))}
      </div>

      {tab === "invoices" && (
        <div className="space-y-2">
          {invoices.map((inv) => {
            const Icon = statusIcons[inv.status] || Clock;
            return (
              <div key={inv.id} className="bg-white rounded-xl border border-gray-200 p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <FileText size={16} className="text-gray-400" />
                    <div>
                      <p className="text-sm font-medium text-gray-900">{inv.number}</p>
                      <p className="text-xs text-gray-500">Due {inv.due_date}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[inv.status]}`}>
                      <Icon size={12} />{inv.status}
                    </span>
                    <p className="text-sm font-semibold text-gray-900">R{inv.total_zar}</p>
                    <Download size={14} className="text-gray-400" />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {tab === "payments" && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-3">
          <CheckCircle size={16} className="text-green-600" />
          <div>
            <p className="text-sm font-medium text-gray-900">Debit Order — R999.00</p>
            <p className="text-xs text-gray-500">FNB •••• 0001 · 1 May 2026</p>
          </div>
        </div>
      )}

      {tab === "methods" && (
        <div className="space-y-3">
          <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-3">
            <div className="p-2 rounded-lg" style={{ backgroundColor: `${brandConfig.colors.primary}15` }}>
              <CreditCard size={16} style={{ color: brandConfig.colors.primary }} />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-900">Debit Order</p>
              <p className="text-xs text-gray-500">FNB •••• 0001 · Active</p>
            </div>
            <ChevronRight size={16} className="text-gray-400" />
          </div>
          <button className="w-full py-3 rounded-xl border-2 border-dashed border-gray-300 text-sm text-gray-500" style={{ }}>
            <Plus size={14} className="inline mr-1" /> Add Payment Method
          </button>
        </div>
      )}

      {/* Self-service links */}
      <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
        <Link href="/billing/statement" className="flex items-center justify-between p-4 hover:bg-gray-50">
          <span className="text-sm text-gray-700">Download Statement</span>
          <Download size={16} className="text-gray-400" />
        </Link>
        <Link href="/billing/pop" className="flex items-center justify-between p-4 hover:bg-gray-50">
          <span className="text-sm text-gray-700">Proof of Payment</span>
          <Download size={16} className="text-gray-400" />
        </Link>
        <Link href="/settings/rica" className="flex items-center justify-between p-4 hover:bg-gray-50">
          <div>
            <span className="text-sm text-gray-700">RICA Status</span>
            <p className="text-xs text-gray-400">Registration compliance</p>
          </div>
          <ChevronRight size={16} className="text-gray-400" />
        </Link>
      </div>
    </div>
  );
}
