"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import {
  LayoutDashboard,
  DollarSign,
  Users,
  Headset,
  Wifi,
  Phone,
  Megaphone,
  ShieldCheck,
  UserCog,
  ChevronLeft,
  ChevronRight,
  Search,
  Settings,
  MessageSquare,
  Receipt,
  Package,
  Globe,
  HeartHandshake,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"

const navItems = [
  { icon: LayoutDashboard, label: "Overview", href: "#overview" },
  { icon: MessageSquare, label: "Communication", href: "#communication" },
  { icon: DollarSign, label: "Sales", href: "#sales" },
  { icon: Users, label: "CRM", href: "#crm" },
  { icon: Headset, label: "Service", href: "#service" },
  { icon: HeartHandshake, label: "Retention", href: "#retention" },
  { icon: Wifi, label: "Network", href: "#network" },
  { icon: Phone, label: "Call Center", href: "#call-center" },
  { icon: Megaphone, label: "Marketing", href: "#marketing" },
  { icon: ShieldCheck, label: "Compliance", href: "#compliance" },
  { icon: UserCog, label: "Talent", href: "#talent" },
  { icon: Receipt, label: "Billing & Collection", href: "#billing" },
  { icon: Package, label: "Product Management", href: "#products" },
  { icon: Globe, label: "Portal Management", href: "#portal" },
]

interface SidebarProps {
  activeSection: string
  onSectionChange: (section: string) => void
}

export function Sidebar({ activeSection, onSectionChange }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <aside
      className={cn(
        "flex h-screen flex-shrink-0 flex-col border-r border-border bg-sidebar transition-all duration-300",
        collapsed ? "w-16" : "w-64",
      )}
    >
      <div className="flex h-16 items-center justify-between border-b border-border px-4 bg-sidebar/50">
        {!collapsed && (
          <div className="flex items-center gap-2.5 group cursor-pointer">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-blue-500 to-cyan-400 shadow-[0_0_15px_rgba(79,70,229,0.3)] group-hover:shadow-[0_0_25px_rgba(79,70,229,0.5)] transition-all">
              <Wifi className="h-5 w-5 text-white" />
            </div>
            <span className="font-bold text-lg tracking-tight text-foreground">OmniDome</span>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed(!collapsed)}
          className="h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-secondary"
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>

      {!collapsed && (
        <div className="p-4">
          <div className="relative group">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground group-focus-within:text-primary transition-colors" />
            <input
              placeholder="Search..."
              className="flex h-10 w-full rounded-md border border-input bg-secondary/50 px-3 py-2 pl-9 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 transition-all border-border focus:border-primary/50 focus:ring-primary/20"
            />
          </div>
        </div>
      )}

      <nav className="flex-1 space-y-1.5 overflow-y-auto px-3 py-4 custom-scrollbar">
        {navItems.map((item) => {
          const isActive = activeSection === item.href.replace("#", "");
          return (
            <button
              key={item.label}
              onClick={() => onSectionChange(item.href.replace("#", ""))}
              className={cn(
                "group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-bold transition-all duration-200 outline-none",
                isActive
                  ? "bg-primary/10 text-primary border border-primary/20"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground"
              )}
            >
              <div className={cn(
                "p-1.5 rounded-lg transition-all",
                isActive ? "bg-primary text-primary-foreground shadow-[0_0_10px_rgba(var(--primary),0.4)]" : "group-hover:text-primary"
              )}>
                <item.icon className="h-4.5 w-4.5 shrink-0" />
              </div>
              {!collapsed && <span className="tracking-tight">{item.label}</span>}
              {isActive && !collapsed && (
                <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_10px_rgba(var(--primary),1)]" />
              )}
            </button>
          );
        })}
      </nav>

      <div className="border-t border-border p-4">
        <div className={cn("flex items-center gap-3", collapsed && "justify-center")}>
          <Avatar className="h-9 w-9">
            <AvatarImage src="/diverse-avatars.png" />
            <AvatarFallback>JD</AvatarFallback>
          </Avatar>
          {!collapsed && (
            <div className="flex-1 overflow-hidden">
              <p className="truncate text-sm font-medium text-foreground">John Doe</p>
              <p className="truncate text-xs text-muted-foreground">Admin</p>
            </div>
          )}
          {!collapsed && (
            <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground">
              <Settings className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </aside>
  )
}
