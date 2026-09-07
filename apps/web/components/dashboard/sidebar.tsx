"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
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
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  X,
  Search,
  Settings,
  MessageSquare,
  Receipt,
  FileText,
  Package,
  Globe,
  HeartHandshake,
  BarChart3,
  Boxes,
  Radio,
  ServerCog,
  Bot,
  Workflow,
  ExternalLink,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"

const navItems = [
  { icon: MessageSquare, label: "Communication", href: "/dashboard/comms", section: "communication", openInNewTab: true },
  { icon: LayoutDashboard, label: "Overview", href: "#overview", section: "overview" },
  { icon: DollarSign, label: "Sales", href: "#sales", section: "sales" },
  { icon: Megaphone, label: "Marketing", href: "#marketing", section: "marketing" },
  { icon: Phone, label: "Call Center", href: "#call-center", section: "call-center" },
  { icon: Users, label: "CRM", href: "#crm", section: "crm" },
  { icon: Headset, label: "Service", href: "#service", section: "service" },
  { icon: HeartHandshake, label: "Retention", href: "#retention", section: "retention" },
  { icon: UserCog, label: "Talent", href: "#talent", section: "talent" },
  { icon: ShieldCheck, label: "Compliance", href: "#compliance", section: "compliance" },
  { icon: FileText, label: "Finance", href: "#finance", section: "finance" },
  { icon: Receipt, label: "Billing & Collection", href: "#billing", section: "billing" },
  { icon: Package, label: "Product Management", href: "#products", section: "products" },
  { icon: Boxes, label: "Inventory & Stock", href: "#inventory", section: "inventory" },
  { icon: Radio, label: "IoT & Devices", href: "#iot", section: "iot" },
  { icon: Wifi, label: "Network", href: "#network", section: "network" },
  { icon: Globe, label: "Portal Management", href: "#portal", section: "portal" },
  {
    icon: ServerCog,
    label: "Admin",
    href: "#admin",
    section: "admin",
    children: [
      { label: "Admin Console", target: "admin-overview" },
      { label: "Agent Manager", href: "/dashboard/admin/agents" },
      { label: "Workflows", href: "/dashboard/admin/workflows" },
    ],
  },
  // Not in the requested order — kept at the bottom so it isn't lost.
  { icon: BarChart3, label: "Analytics & AI", href: "#analytics", section: "analytics" },
]

interface SidebarProps {
  activeSection: string
  allowedSections: string[]
  onSectionChange: (section: string) => void
  mobileOpen: boolean
  onMobileClose: () => void
  onSubSectionSelect?: (section: string, target: string) => void
  activeSubSections?: {
    retention?: string
    portal?: string
  }
}

export function Sidebar({
  activeSection,
  allowedSections,
  onSectionChange,
  mobileOpen,
  onMobileClose,
  onSubSectionSelect,
  activeSubSections,
}: SidebarProps) {
  const router = useRouter()
  const [collapsed, setCollapsed] = useState(false)
  const isCollapsed = collapsed && !mobileOpen
  const [retentionOpen, setRetentionOpen] = useState(true)
  const [portalOpen, setPortalOpen] = useState(true)
  const [adminOpen, setAdminOpen] = useState(true)
  const visibleNavItems = navItems.filter((item) => {
    // Items with real routes (not hash anchors) are always visible
    if (item.href.startsWith("/")) return true
    return allowedSections.includes(item.href.replace("#", ""))
  })

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 flex h-screen flex-shrink-0 flex-col border-r border-border bg-sidebar transition-all duration-300 md:static md:z-auto md:translate-x-0",
        mobileOpen ? "translate-x-0" : "-translate-x-full",
        collapsed ? "md:w-16" : "md:w-64",
        "w-72",
      )}
    >
      <div className="flex h-auto items-center justify-between border-b border-border bg-transparent px-4 py-4">
        {isCollapsed ? (
          <img src="/logo-new.svg" alt="OmniDome Logo" className="h-8 w-8 mx-auto" title="OmniDome" />
        ) : (
          <div className="flex items-center gap-3 group cursor-pointer">
            <img src="/logo-new.svg" alt="OmniDome Logo" className="h-12 w-12 transition-all group-hover:scale-110" />
            <div className="flex flex-col">
              <span className="font-extrabold text-xl tracking-tight text-foreground group-hover:text-primary transition-colors">
                OmniDome
              </span>
              <span className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground">
                Telecom Cloud OS
              </span>
            </div>
          </div>
        )}
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="hidden md:flex h-8 w-8 text-muted-foreground hover:text-foreground"
            onClick={() => setCollapsed(!collapsed)}
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden h-8 w-8 text-muted-foreground hover:text-foreground"
            onClick={onMobileClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {!isCollapsed && (
        <div className="p-3">
          <div className="relative group">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground group-focus-within:text-primary transition-colors" />
            <input
              placeholder="Search..."
              className="flex h-10 w-full rounded-md border border-input bg-secondary/50 px-3 py-2 pl-9 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 transition-all border-border focus:border-primary/50 focus:ring-primary/20"
            />
          </div>
        </div>
      )}

      <nav className={cn("flex-1 space-y-1.5 py-4 custom-scrollbar", isCollapsed ? "overflow-hidden px-2" : "overflow-y-auto px-3")}>
        {visibleNavItems.map((item) => {
          const section = item.section ?? item.href.replace("#", "")
          const isActive = activeSection === section
          const hasChildren = Array.isArray(item.children) && item.children.length > 0
          const isOpen =
            section === "retention" ? retentionOpen : section === "portal" ? portalOpen : section === "admin" ? adminOpen : false
          const activeChild =
            section === "retention"
              ? activeSubSections?.retention
              : section === "portal"
                ? activeSubSections?.portal
                : undefined
          return (
            <div key={item.label} className="space-y-1">
              <div className="flex items-center gap-1">
                <button
                  onClick={() => {
                    // Items marked openInNewTab or comms open in a separate window/tab
                    if ((item as any).openInNewTab || item.href === "/dashboard/comms") {
                      window.open(item.href, "_blank", "noopener,noreferrer")
                      onMobileClose()
                      return
                    }
                    // Items with a real path (starts with "/") navigate to that route
                    if (item.href.startsWith("/")) {
                      router.push(item.href)
                      onMobileClose()
                      return
                    }
                    onSectionChange(section)
                    if (section === "retention") setRetentionOpen(true)
                    if (section === "portal") setPortalOpen(true)
                    if (section === "admin") setAdminOpen(true)
                    onMobileClose()
                  }}
                  title={isCollapsed ? item.label : undefined}
                  className={cn(
                    "group flex flex-1 items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-bold transition-all duration-200 outline-none",
                    isCollapsed && "justify-center px-2",
                    isActive
                      ? "bg-primary/10 text-primary border border-primary/20"
                      : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                  )}
                >
                  <div className={cn(
                    "p-1.5 rounded-lg transition-all",
                    isActive ? "bg-primary text-primary-foreground shadow-[0_0_10px_rgba(var(--primary),0.4)]" : "group-hover:text-primary"
                  )}>
                    <item.icon className="h-[18px] w-[18px] shrink-0" />
                  </div>
                  {!isCollapsed && <span className="tracking-tight">{item.label}</span>}
                  {!isCollapsed && (item as any).openInNewTab && (
                    <ExternalLink className="ml-auto h-3.5 w-3.5 text-muted-foreground opacity-60 group-hover:opacity-100 transition-opacity" />
                  )}
                  {isActive && !isCollapsed && !(item as any).openInNewTab && (
                    <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_10px_rgba(var(--primary),1)]" />
                  )}
                </button>
                {hasChildren && !isCollapsed && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-foreground"
                    onClick={() => {
                      if (section === "retention") setRetentionOpen((prev) => !prev)
                      if (section === "portal") setPortalOpen((prev) => !prev)
                      if (section === "admin") setAdminOpen((prev) => !prev)
                    }}
                    title="Toggle section"
                  >
                    <ChevronDown className={cn("h-4 w-4 transition-transform", isOpen && "rotate-180")} />
                  </Button>
                )}
              </div>
              {hasChildren && !isCollapsed && isOpen && (
                <div className="ml-11 space-y-1">
                  {item.children?.map((child: any) => {
                    const isChildActive = activeChild === child.target
                    return (
                      <button
                        key={child.target || child.href}
                        onClick={() => {
                          if (child.href) {
                            router.push(child.href)
                            onMobileClose()
                            return
                          }
                          if (onSubSectionSelect) {
                            onSubSectionSelect(section, child.target)
                          } else {
                            onSectionChange(section)
                          }
                          onMobileClose()
                        }}
                        className={cn(
                          "flex w-full items-center rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors",
                          isChildActive
                            ? "bg-secondary text-foreground"
                            : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground",
                        )}
                      >
                        {child.label}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      <div className="border-t border-border p-4">
        <div className={cn("flex items-center gap-3", isCollapsed && "flex-col gap-2 justify-center")}>
          <Avatar className="h-9 w-9" title="Profile">
            <AvatarImage src="/diverse-avatars.png" />
            <AvatarFallback>JD</AvatarFallback>
          </Avatar>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground"
            title="Settings"
          >
            <Settings className="h-4 w-4" />
          </Button>
          {!isCollapsed && (
            <span className="text-xs text-muted-foreground flex-1 truncate">Admin</span>
          )}
        </div>
      </div>
    </aside>
  )
}
