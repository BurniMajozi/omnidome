"use client";

import { ReactNode, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, CreditCard, ShoppingBag, HeadphonesIcon,
  Settings, LogOut, Wifi, Bell, Menu, X, User,
  BarChart3,
} from "lucide-react";
import brandConfig from "@/config/brand.json";

// "AI Assistant" is now embedded inside the Support page — no separate nav item needed.
const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/billing", label: "Billing", icon: CreditCard },
  { href: "/store", label: "Store", icon: ShoppingBag },
  { href: "/support", label: "Support", icon: HeadphonesIcon },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function PortalLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col bg-gray-50/70">
      {/* Top bar */}
      <header className="sticky top-0 z-50 bg-white/85 backdrop-blur border-b border-gray-200 px-4 h-14 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button className="lg:hidden p-2 -ml-2 rounded-lg hover:bg-gray-100" onClick={() => setSidebarOpen(!sidebarOpen)} aria-label="Toggle menu">
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <Link href="/dashboard" className="flex items-center gap-2">
            <Wifi size={24} style={{ color: brandConfig.colors.primary }} />
            <span className="font-bold text-lg text-gray-900">{brandConfig.appName}</span>
          </Link>
        </div>
        <div className="flex items-center gap-2">
          <button className="p-2 rounded-lg hover:bg-gray-100 relative" aria-label="Notifications">
            <Bell size={20} className="text-gray-600" />
            <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full" />
          </button>
          <button className="p-2 rounded-lg hover:bg-gray-100" aria-label="Profile">
            <User size={20} className="text-gray-600" />
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Desktop sidebar */}
        <nav className="hidden lg:flex flex-col w-56 bg-white/85 backdrop-blur border-r border-gray-200 shrink-0">
          <div className="flex-1 py-4 px-3 space-y-1">
            {navItems.map((item) => {
              const active = pathname === item.href || pathname.startsWith(item.href + "/");
              const Icon = item.icon;
              return (
                <Link key={item.href} href={item.href}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${active ? "text-white" : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"}`}
                  style={active ? { backgroundColor: brandConfig.colors.primary } : undefined}>
                  <Icon size={18} />
                  {item.label}
                </Link>
              );
            })}
          </div>
          <div className="p-3 border-t border-gray-200">
            <button className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-gray-500 hover:bg-gray-100 w-full">
              <LogOut size={18} />
              Sign out
            </button>
          </div>
        </nav>

        {/* Mobile sidebar */}
        {sidebarOpen && (
          <div className="lg:hidden fixed inset-0 z-40 flex">
            <div className="fixed inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
            <nav className="relative w-64 bg-white h-full flex flex-col shadow-xl">
              <div className="flex-1 py-4 px-3 space-y-1">
                {navItems.map((item) => {
                  const active = pathname === item.href;
                  const Icon = item.icon;
                  return (
                    <Link key={item.href} href={item.href} onClick={() => setSidebarOpen(false)}
                      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium ${active ? "text-white" : "text-gray-600 hover:bg-gray-100"}`}
                      style={active ? { backgroundColor: brandConfig.colors.primary } : undefined}>
                      <Icon size={18} />
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </nav>
          </div>
        )}

        {/* Main content */}
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>

      {/* Mobile bottom nav */}
      <nav className="lg:hidden sticky bottom-0 z-50 bg-white/85 backdrop-blur border-t border-gray-200 h-16 flex items-center justify-around shrink-0">
        {navItems.map((item) => {
          const active = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link key={item.href} href={item.href}
              className={`flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg ${active ? "" : "text-gray-500"}`}
              style={active ? { color: brandConfig.colors.primary } : undefined}>
              <Icon size={20} />
              <span className="text-[10px] font-medium">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
