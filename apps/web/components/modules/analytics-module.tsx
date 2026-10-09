"use client"

import { useEffect, useState } from "react"
import { Megaphone, Search, Sparkles, Swords } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { PresentonStudio } from "./analytics/presenton-studio"
import { ResearchView } from "./analytics/research-view"
import { CompetitorsView } from "./analytics/competitors-view"
import { CampaignAnalysisView } from "./analytics/campaign-analysis-view"
import { PermissionProvider } from "./analytics/shared"

type View = "presenton" | "research" | "competitors" | "campaign-analysis"

function viewFromTarget(target?: string): View | null {
    switch (target) {
        case "presentations":
        case "presenton":
            return "presenton"
        case "research":
            return "research"
        case "competitors":
            return "competitors"
        case "campaign-analysis":
            return "campaign-analysis"
        default:
            return null
    }
}

interface AnalyticsModuleProps {
    activeTabOverride?: string
}

export function AnalyticsModule({ activeTabOverride }: AnalyticsModuleProps = {}) {
    const [activeView, setActiveView] = useState<View>(viewFromTarget(activeTabOverride) ?? "presenton")

    useEffect(() => {
        const v = viewFromTarget(activeTabOverride)
        if (v) setActiveView(v)
    }, [activeTabOverride])

    const tab = (v: View, label: string, icon: React.ReactNode) => (
        <Button
            variant={activeView === v ? "default" : "outline"}
            size="sm"
            className="h-8 gap-2 text-xs font-semibold"
            onClick={() => setActiveView(v)}
        >
            {icon}
            {label}
        </Button>
    )

    return (
        <PermissionProvider>
            <div className="space-y-6">
                <div className="flex flex-wrap items-center justify-between border-b border-border/80 pb-3 gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                        <Button
                            variant={activeView === "presenton" ? "default" : "outline"}
                            size="sm"
                            className={`h-8 gap-2 text-xs font-semibold ${
                                activeView === "presenton"
                                    ? "bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white border-0 shadow-md"
                                    : "border-violet-500/40 text-violet-400 hover:bg-violet-950/20"
                            }`}
                            onClick={() => setActiveView("presenton")}
                        >
                            <Sparkles className="h-3.5 w-3.5 text-violet-300 animate-pulse" />
                            Presenton AI Studio
                            <Badge variant="outline" className="text-[9px] py-0 px-1 border-violet-400 text-violet-200 bg-violet-500/20">
                                Slide Generator
                            </Badge>
                        </Button>
                        {tab("research", "Research", <Search className="h-3.5 w-3.5" />)}
                        {tab("competitors", "Competitor Analysis", <Swords className="h-3.5 w-3.5" />)}
                        {tab("campaign-analysis", "Campaign Analysis", <Megaphone className="h-3.5 w-3.5" />)}
                    </div>
                </div>

                {activeView === "presenton" && <PresentonStudio />}
                {activeView === "research" && <ResearchView />}
                {activeView === "competitors" && <CompetitorsView />}
                {activeView === "campaign-analysis" && <CampaignAnalysisView />}
            </div>
        </PermissionProvider>
    )
}
