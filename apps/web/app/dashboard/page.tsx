"use client"

import { useEffect, useMemo, useState } from "react"
import { Sidebar } from "@/components/dashboard/sidebar"
import { Header } from "@/components/dashboard/header"
import { AITaskChat } from "@/components/chat/ai-task-chat"
import { DashboardOverview } from "@/components/modules/dashboard-overview"
import { SalesModule } from "@/components/modules/sales-module"
import { CrmModule } from "@/components/modules/crm-module"
import { ServiceModule } from "@/components/modules/service-module"
import { RetentionModule } from "@/components/modules/retention-module"
import { NetworkModule } from "@/components/modules/network-module"
import { CallCenterModule } from "@/components/modules/call-center-module"
import { MarketingModule } from "@/components/modules/marketing-module"
import { ComplianceModule } from "@/components/modules/compliance-module"
import { TalentModule } from "@/components/modules/talent-module"
import { CommunicationModule } from "@/components/modules/communication-module"
import { BillingModule } from "@/components/modules/billing-module"
import { FinanceModule } from "@/components/modules/finance-module"
import { ProductsModule } from "@/components/modules/products-module"
import { PortalModule } from "@/components/modules/portal-module"
import { AnalyticsModule } from "@/components/modules/analytics-module"
import { InventoryModule } from "@/components/modules/inventory-module"
import { IoTModule } from "@/components/modules/iot-module"
import { FlickeringGrid } from "@/components/ui/flickering-grid"
import { DEFAULT_ENTITLEMENTS, fetchEntitlements, isModuleEnabled, moduleBySection } from "@/lib/entitlements"
import { supabase } from "@/lib/supabase/client"

const sectionTitles: Record<string, string> = {
  overview: "Dashboard Overview",
  communication: "Team Communication",
  sales: "Sales Management",
  crm: "Customer Relationship Management",
  service: "Service & Support",
  retention: "Retention & Churn Analytics",
  network: "Network Operations",
  "call-center": "Call Center Operations",
  marketing: "Marketing Hub",
  compliance: "Compliance & Security",
  talent: "Staff Dome",
  billing: "Billing & Collection",
  finance: "Finance & FP&A",
  products: "Product Management",
  portal: "Portal Management",
  analytics: "Analytics & AI Insights",
  inventory: "Inventory & Stock Management",
  iot: "IoT & Device Management",
}

export default function Dashboard() {
  const [activeSection, setActiveSection] = useState("overview")
  const [chatOpen, setChatOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [retentionTab, setRetentionTab] = useState<string | null>(null)
  const [portalTab, setPortalTab] = useState<string | null>(null)
  const [entitlements, setEntitlements] = useState(DEFAULT_ENTITLEMENTS)

  useEffect(() => {
    let cancelled = false

    const ensureAuthenticated = async () => {
      const { data, error } = await supabase.auth.getSession()
      if (cancelled) return

      if (error || !data.session) {
        router.replace("/auth")
      }
    }

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!session) {
        router.replace("/auth")
      }
    })

    ensureAuthenticated()

    return () => {
      cancelled = true
      subscription.unsubscribe()
    }
  }, [])

  useEffect(() => {
    let mounted = true
    fetchEntitlements()
      .then((data) => {
        if (mounted) setEntitlements(data)
      })
      .catch(() => {
        if (mounted) setEntitlements(DEFAULT_ENTITLEMENTS)
      })
    return () => {
      mounted = false
    }
  }, [])

  const allowedSections = useMemo(() => {
    const sections = Object.keys(sectionTitles).filter((section) =>
      isModuleEnabled(entitlements.modules, moduleBySection[section] || section),
    )
    if (!sections.includes("overview")) {
      sections.unshift("overview")
    }
    return sections
  }, [entitlements.modules])

  const resolvedSection = allowedSections.includes(activeSection) ? activeSection : "overview"

  useEffect(() => {
    if (activeSection !== "retention") setRetentionTab(null)
    if (activeSection !== "portal") setPortalTab(null)
  }, [activeSection])

  const renderModule = () => {
    try {
      switch (resolvedSection) {
        case "communication":
          return <CommunicationModule />
        case "sales":
          return <SalesModule />
        case "crm":
          return <CrmModule />
        case "service":
          return <ServiceModule />
        case "network":
          return <NetworkModule />
        case "call-center":
          return <CallCenterModule />
        case "marketing":
          return <MarketingModule />
        case "compliance":
          return <ComplianceModule />
        case "talent":
          return <TalentModule />
        case "billing":
          return <BillingModule />
        case "finance":
          return <FinanceModule />
        case "products":
          return <ProductsModule />
        case "portal":
          return <PortalModule activeTabOverride={portalTab ?? undefined} />
        case "analytics":
          return <AnalyticsModule />
        case "inventory":
          return <InventoryModule />
        case "iot":
          return <IoTModule />
        case "retention":
          return <RetentionModule activeTabOverride={retentionTab ?? undefined} />
        default:
          return <DashboardOverview />
      }
    } catch (error) {
      console.log("[v0] Error rendering module:", error)
      return <div className="p-4 text-red-500">Error loading module</div>
    }
  }

  const handleSubSectionSelect = (section: string, target: string) => {
    setActiveSection(section)
    if (section === "retention") {
      setRetentionTab(target)
      setPortalTab(null)
    } else if (section === "portal") {
      setPortalTab(target)
      setRetentionTab(null)
    }
    setSidebarOpen(false)
  }

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background relative">
      {/* Mobile sidebar backdrop */}
      {sidebarOpen && (
        <button
          type="button"
          aria-label="Close sidebar"
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      {/* Flickering Grid Background */}
      <div className="fixed top-0 left-0 z-0 w-full h-full [mask-image:linear-gradient(to_bottom,black_0%,transparent_30%)] pointer-events-none opacity-50">
        <FlickeringGrid
          className="absolute top-0 left-0 size-full"
          squareSize={4}
          gridGap={6}
          color="#6B7280"
          maxOpacity={0.1}
          flickerChance={0.03}
        />
      </div>

      {/* Sidebar */}
      <Sidebar
        activeSection={resolvedSection}
        allowedSections={allowedSections}
        onSectionChange={setActiveSection}
        mobileOpen={sidebarOpen}
        onMobileClose={() => setSidebarOpen(false)}
        onSubSectionSelect={handleSubSectionSelect}
        activeSubSections={{
          retention: retentionTab ?? undefined,
          portal: portalTab ?? undefined,
        }}
      />

      {/* Main Content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header
          title={sectionTitles[resolvedSection] || "Dashboard"}
          onNewTask={() => setChatOpen(true)}
          onMenuToggle={() => setSidebarOpen((prev) => !prev)}
        />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6">{renderModule()}</main>
      </div>

      {/* Chat Sidebar */}
      {chatOpen && <AITaskChat isOpen={chatOpen} onClose={() => setChatOpen(false)} />}
    </div>
  )
}
