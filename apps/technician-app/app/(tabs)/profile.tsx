"use client";

import { useState } from "react";
import { LogOut, User, Mail, Phone, MapPin, Shield, Bell, ChevronRight } from "lucide-react";
import { useAuthStore } from "@/lib/stores/auth-store";

export default function ProfilePage() {
  const { technician, logout } = useAuthStore();
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);

  const handleLogout = async () => {
    logout();
  };

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-slate-900 px-4 pt-12 pb-3 border-b border-slate-700">
        <h1 className="text-xl font-bold text-slate-100">Profile</h1>
      </div>

      <div className="px-4 py-4 space-y-4 pb-24">
        {/* Profile Card */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="h-12 w-12 rounded-full bg-indigo-500/20 flex items-center justify-center">
              <User className="h-6 w-6 text-indigo-400" />
            </div>
            <div>
              <p className="font-semibold text-slate-100">
                {technician?.name || "Technician"}
              </p>
              <p className="text-xs text-slate-400">{technician?.role || "Field Technician"}</p>
            </div>
          </div>
          <div className="space-y-2">
            {technician?.email && (
              <div className="flex items-center gap-2 text-sm text-slate-300">
                <Mail className="h-4 w-4 text-slate-400" />
                <span>{technician.email}</span>
              </div>
            )}
            {technician?.phone && (
              <div className="flex items-center gap-2 text-sm text-slate-300">
                <Phone className="h-4 w-4 text-slate-400" />
                <span>{technician.phone}</span>
              </div>
            )}
            {technician?.zone && (
              <div className="flex items-center gap-2 text-sm text-slate-300">
                <MapPin className="h-4 w-4 text-slate-400" />
                <span>Zone: {technician.zone}</span>
              </div>
            )}
            <div className="flex items-center gap-2 text-sm text-slate-300">
              <Shield className="h-4 w-4 text-slate-400" />
              <span>ID: {technician?.id || "N/A"}</span>
            </div>
          </div>
        </div>

        {/* Settings */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg">
          <div className="px-4 py-3 border-b border-slate-700">
            <p className="text-xs font-semibold text-slate-400 uppercase">Settings</p>
          </div>

          {/* Notifications toggle */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
            <div className="flex items-center gap-3">
              <Bell className="h-4 w-4 text-slate-400" />
              <span className="text-sm text-slate-200">Push Notifications</span>
            </div>
            <button
              className={`w-11 h-6 rounded-full transition-colors relative ${
                notificationsEnabled ? "bg-indigo-500" : "bg-slate-600"
              }`}
              onClick={() => setNotificationsEnabled(!notificationsEnabled)}
            >
              <span
                className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                  notificationsEnabled ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
          </div>

          {/* App Info */}
          <div className="px-4 py-3 border-b border-slate-700">
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-200">App Version</span>
              <span className="text-xs text-slate-400 bg-slate-700 px-2 py-1 rounded">v0.1.0</span>
            </div>
          </div>

          {/* Zone */}
          <div className="px-4 py-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-200">Working Zone</span>
              <div className="flex items-center gap-1">
                <span className="text-xs text-slate-400">{technician?.zone || "Unassigned"}</span>
                <ChevronRight className="h-3.5 w-3.5 text-slate-500" />
              </div>
            </div>
          </div>
        </div>

        {/* Logout */}
        <button
          className="w-full bg-red-600/20 border border-red-500/30 text-red-400 font-semibold py-3 rounded-lg flex items-center justify-center gap-2 active:bg-red-600/30"
          onClick={handleLogout}
        >
          <LogOut className="h-4 w-4" /> Sign Out
        </button>
      </div>
    </div>
  );
}
