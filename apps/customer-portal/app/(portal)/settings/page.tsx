"use client";

import { useState } from "react";
import {
  Wifi, CreditCard, FileText, MapPin, PauseCircle, ArrowRightLeft,
  TrendingUp, TrendingDown, XCircle, Shield, Bell, ChevronRight, CheckCircle,
} from "lucide-react";
import brandConfig from "@/config/brand.json";

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState<string | null>(null);

  const sections = [
    { id: "rica", label: "RICA Verification", icon: Shield, desc: "Identity verification status", badge: "Verified", badgeColor: "bg-green-50 text-green-700" },
    { id: "pause", label: "Pause Service", icon: PauseCircle, desc: "Temporarily pause your connection" },
    { id: "move", label: "Move House", icon: MapPin, desc: "Transfer service to new address" },
    { id: "upgrade", label: "Upgrade / Downgrade", icon: TrendingUp, desc: "Change your package" },
    { id: "cancel", label: "Cancel Service", icon: XCircle, desc: "Close your account", danger: true },
    { id: "notifications", label: "Notifications", icon: Bell, desc: "Manage notification preferences" },
  ];

  return (
    <div className="p-4 lg:p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-gray-500 mt-1">Manage your account and service</p>
      </div>

      {/* Service info */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex items-center gap-3 mb-3">
          <div className="p-2 rounded-lg" style={{ backgroundColor: `${brandConfig.colors.primary}15` }}>
            <Wifi size={18} style={{ color: brandConfig.colors.primary }} />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900">100 Mbps FTTH Unlimited</p>
            <p className="text-xs text-gray-500">Account: ACC-001 · Active since Jan 2025</p>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 pt-3 border-t border-gray-100">
          <div>
            <p className="text-lg font-bold text-gray-900">847 GB</p>
            <p className="text-xs text-gray-500">Usage this month</p>
          </div>
          <div>
            <p className="text-lg font-bold text-gray-900">R999</p>
            <p className="text-xs text-gray-500">Monthly</p>
          </div>
          <div>
            <p className="text-lg font-bold text-gray-900">12 mo</p>
            <p className="text-xs text-gray-500">Contract remaining</p>
          </div>
        </div>
      </div>

      {/* Service management */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Service Management</h2>
        <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
          {sections.map((s) => (
            <button key={s.id} onClick={() => setActiveSection(activeSection === s.id ? null : s.id)}
              className="w-full flex items-center gap-3 p-4 hover:bg-gray-50 transition-colors text-left">
              <div className={`p-2 rounded-lg ${s.danger ? "bg-red-50" : "bg-gray-50"}`}>
                <s.icon size={16} className={s.danger ? "text-red-500" : "text-gray-500"} />
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${s.danger ? "text-red-700" : "text-gray-900"}`}>{s.label}</p>
                <p className="text-xs text-gray-500">{s.desc}</p>
              </div>
              {s.badge && (
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${s.badgeColor}`}>{s.badge}</span>
              )}
              <ChevronRight size={14} className="text-gray-400" />
            </button>
          ))}
        </div>
      </div>

      {/* Action panels */}
      {activeSection === "pause" && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-900">Pause Your Service</h3>
          <p className="text-xs text-gray-500">Temporarily pause for up to 3 months. R49/month holding fee applies.</p>
          <select className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm">
            <option>1 month</option><option>2 months</option><option>3 months</option>
          </select>
          <button className="w-full py-2 rounded-lg text-white text-sm font-medium" style={{ backgroundColor: brandConfig.colors.warning }}>
            Confirm Pause
          </button>
        </div>
      )}

      {activeSection === "move" && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-900">Move House</h3>
          <p className="text-xs text-gray-500">We'll check coverage at your new address and schedule installation.</p>
          <input placeholder="New address line 1" className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm" />
          <input placeholder="Suburb" className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm" />
          <div className="flex gap-2">
            <input placeholder="City" className="flex-1 px-3 py-2 rounded-lg border border-gray-200 text-sm" />
            <input placeholder="Postal code" className="w-24 px-3 py-2 rounded-lg border border-gray-200 text-sm" />
          </div>
          <button className="w-full py-2 rounded-lg text-white text-sm font-medium" style={{ backgroundColor: brandConfig.colors.primary }}>
            Check Coverage & Schedule
          </button>
        </div>
      )}

      {activeSection === "upgrade" && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-900">Change Package</h3>
          <div className="space-y-2">
            {[
              { speed: "50 Mbps", price: 799, current: false },
              { speed: "100 Mbps", price: 999, current: true },
              { speed: "200 Mbps", price: 1299, current: false },
              { speed: "500 Mbps", price: 1899, current: false },
              { speed: "1 Gbps", price: 2499, current: false },
            ].map((p) => (
              <div key={p.speed} className={`flex items-center justify-between p-3 rounded-lg border ${p.current ? "border-2" : "border-gray-200"}`}
                style={p.current ? { borderColor: brandConfig.colors.primary } : undefined}>
                <div>
                  <p className="text-sm font-medium text-gray-900">{p.speed}</p>
                  <p className="text-xs text-gray-500">R{p.price}/month</p>
                </div>
                {p.current ? (
                  <CheckCircle size={16} style={{ color: brandConfig.colors.primary }} />
                ) : (
                  <button className="px-3 py-1 rounded-lg text-xs font-medium"
                    style={{ backgroundColor: `${brandConfig.colors.primary}15`, color: brandConfig.colors.primary }}>
                    Switch
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {activeSection === "cancel" && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 space-y-3">
          <h3 className="text-sm font-semibold text-red-800">Cancel Service</h3>
          <p className="text-xs text-red-600">This will initiate the cancellation process. ETF may apply based on your contract.</p>
          <select className="w-full px-3 py-2 rounded-lg border border-red-200 text-sm bg-white">
            <option>Select reason...</option>
            <option>Moving to area without coverage</option>
            <option>Dissatisfied with service</option>
            <option>Switching to competitor</option>
            <option>Financial reasons</option>
            <option>Other</option>
          </select>
          <button className="w-full py-2 rounded-lg bg-red-600 text-white text-sm font-medium">
            Begin Cancellation Process
          </button>
        </div>
      )}

      {activeSection === "rica" && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-center gap-3">
          <CheckCircle size={20} className="text-green-600" />
          <div>
            <p className="text-sm font-medium text-green-800">RICA Verified</p>
            <p className="text-xs text-green-600">Your identity was verified on 2026-03-15. Next review: 2027-03-15.</p>
          </div>
        </div>
      )}
    </div>
  );
}
