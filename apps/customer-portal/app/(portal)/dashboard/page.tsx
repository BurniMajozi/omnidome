"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  CreditCard, ShoppingBag, HeadphonesIcon, Wifi,
  TrendingUp, AlertTriangle, CheckCircle, Clock,
  ArrowUpRight, Zap, Bell,
} from "lucide-react";
import brandConfig from "@/config/brand.json";

interface DashboardData {
  serviceStatus: "active" | "suspended" | "pending";
  currentPlan: string;
  speedMbps: number;
  usageGb: number;
  usageTotal: number;
  nextInvoice: { amount: number; dueDate: string };
  openTickets: number;
  recentActivity: Array<{ icon: string; text: string; time: string; type: string }>;
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    // In production: fetch from API
    // const api = new ApiClient();
    // const res = await api.getDashboard(authStore.customerId);
    setData({
      serviceStatus: "active",
      currentPlan: "FTTH Unlimited",
      speedMbps: 100,
      usageGb: 847,
      usageTotal: 1000,
      nextInvoice: { amount: 999, dueDate: "2026-07-01" },
      openTickets: 1,
      recentActivity: [
        { icon: "credit", text: "Invoice INV-2026-006 generated — R999.00", time: "2 hours ago", type: "billing" },
        { icon: "usage", text: "Usage at 85% of fair use policy", time: "1 day ago", type: "warning" },
        { icon: "rica", text: "RICA verification completed", time: "3 days ago", type: "success" },
        { icon: "wifi", text: "Service activated — 100 Mbps", time: "5 days ago", type: "success" },
      ],
    });
  }, []);

  if (!data) return <div className="p-6 text-center text-gray-500">Loading...</div>;

  const usagePercent = Math.round((data.usageGb / data.usageTotal) * 100);

  return (
    <div className="p-4 lg:p-6 max-w-5xl mx-auto space-y-6">
      {/* Welcome */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Welcome back 👋</h1>
        <p className="text-gray-500 mt-1">Your {brandConfig.appName} account overview.</p>
      </div>

      {/* Service status */}
      <div className={`rounded-xl p-4 flex items-center gap-3 border ${
        data.serviceStatus === "active" ? "bg-green-50 border-green-200" :
        data.serviceStatus === "suspended" ? "bg-red-50 border-red-200" :
        "bg-yellow-50 border-yellow-200"
      }`}>
        {data.serviceStatus === "active" ? <CheckCircle size={20} className="text-green-600" /> :
         data.serviceStatus === "suspended" ? <AlertTriangle size={20} className="text-red-600" /> :
         <Clock size={20} className="text-yellow-600" />}
        <div>
          <p className={`text-sm font-medium ${
            data.serviceStatus === "active" ? "text-green-800" :
            data.serviceStatus === "suspended" ? "text-red-800" : "text-yellow-800"
          }`}>
            Service {data.serviceStatus === "active" ? "Active" : data.serviceStatus === "suspended" ? "Suspended" : "Pending Activation"}
          </p>
          <p className="text-xs text-gray-500">
            {data.currentPlan} · {data.speedMbps} Mbps · Last checked: just now
          </p>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {/* Usage */}
        <div className="bg-white rounded-xl p-4 border border-gray-200">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-1.5 rounded-lg" style={{ backgroundColor: `${brandConfig.colors.primary}15` }}>
              <TrendingUp size={14} style={{ color: brandConfig.colors.primary }} />
            </div>
            <span className="text-xs text-gray-500">Usage</span>
          </div>
          <p className="text-xl font-bold text-gray-900">{data.usageGb} GB</p>
          <div className="mt-2 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${usagePercent}%`, backgroundColor: usagePercent > 80 ? brandConfig.colors.warning : brandConfig.colors.primary }} />
          </div>
          <p className="text-xs text-gray-500 mt-1">{usagePercent}% of {data.usageTotal} GB</p>
        </div>

        {/* Next invoice */}
        <div className="bg-white rounded-xl p-4 border border-gray-200">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-1.5 rounded-lg bg-yellow-50">
              <CreditCard size={14} className="text-yellow-600" />
            </div>
            <span className="text-xs text-gray-500">Next Bill</span>
          </div>
          <p className="text-xl font-bold text-gray-900">R{data.nextInvoice.amount.toFixed(0)}</p>
          <p className="text-xs text-gray-500 mt-1">Due {data.nextInvoice.dueDate}</p>
        </div>

        {/* Tickets */}
        <div className="bg-white rounded-xl p-4 border border-gray-200">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-1.5 rounded-lg bg-gray-100">
              <HeadphonesIcon size={14} className="text-gray-600" />
            </div>
            <span className="text-xs text-gray-500">Tickets</span>
          </div>
          <p className="text-xl font-bold text-gray-900">{data.openTickets}</p>
          <p className="text-xs text-gray-500 mt-1">Open support ticket{data.openTickets !== 1 ? "s" : ""}</p>
        </div>

        {/* Plan */}
        <div className="bg-white rounded-xl p-4 border border-gray-200">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-1.5 rounded-lg bg-green-50">
              <Wifi size={14} className="text-green-600" />
            </div>
            <span className="text-xs text-gray-500">Plan</span>
          </div>
          <p className="text-xl font-bold text-gray-900">{data.speedMbps} Mbps</p>
          <p className="text-xs text-gray-500 mt-1">{data.currentPlan}</p>
        </div>
      </div>

      {/* Quick actions */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Quick Actions</h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { href: "/billing", label: "Pay Bill", icon: CreditCard, color: brandConfig.colors.primary },
            { href: "/store", label: "Shop", icon: ShoppingBag, color: brandConfig.colors.accent },
            { href: "/support", label: "Get Help", icon: HeadphonesIcon, color: brandConfig.colors.secondary },
            { href: "/settings", label: "Settings", icon: Zap, color: brandConfig.colors.success },
          ].map((action) => (
            <Link key={action.href} href={action.href}
              className="flex items-center gap-3 p-3 rounded-xl bg-white border border-gray-200 hover:shadow-sm transition-shadow">
              <div className="p-2 rounded-lg" style={{ backgroundColor: `${action.color}15` }}>
                <action.icon size={16} style={{ color: action.color }} />
              </div>
              <span className="text-sm font-medium text-gray-700">{action.label}</span>
            </Link>
          ))}
        </div>
      </div>

      {/* Recent activity */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Recent Activity</h2>
        <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
          {data.recentActivity.map((item, i) => (
            <div key={i} className="flex items-center gap-3 p-3.5">
              <div className={`p-1.5 rounded-lg ${
                item.type === "success" ? "bg-green-50" :
                item.type === "warning" ? "bg-yellow-50" :
                item.type === "billing" ? "bg-blue-50" : "bg-gray-50"
              }`}>
                {item.type === "success" ? <CheckCircle size={14} className="text-green-600" /> :
                 item.type === "warning" ? <AlertTriangle size={14} className="text-yellow-600" /> :
                 item.type === "billing" ? <CreditCard size={14} className="text-blue-600" /> :
                 <Wifi size={14} className="text-gray-500" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-700 truncate">{item.text}</p>
                <p className="text-xs text-gray-400">{item.time}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
