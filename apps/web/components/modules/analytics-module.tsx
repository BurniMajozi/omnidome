"use client"

import { useEffect, useState } from "react"
import { Megaphone, Presentation, Search, Swords } from "lucide-react"
import { Button } from "@/components/ui/button"
import { DeckStudio } from "./analytics/deck-studio"
import { ResearchView } from "./analytics/research-view"
import { CompetitorsView } from "./analytics/competitors-view"
import { CampaignAnalysisView } from "./analytics/campaign-analysis-view"
import { PermissionProvider } from "./analytics/shared"

type View = "decks" | "research" | "competitors" | "campaign-analysis"

function viewFromTarget(target?: string): View | null {
    switch (target) {
        case "presentations":
        case "presenton":
        case "decks":
            return "decks"
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
    const [activeView, setActiveView] = useState<View>(viewFromTarget(activeTabOverride) ?? "decks")

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
                        {tab("decks", "Deck Studio", <Presentation className="h-3.5 w-3.5" />)}
                        {tab("research", "Research", <Search className="h-3.5 w-3.5" />)}
                        {tab("competitors", "Competitor Analysis", <Swords className="h-3.5 w-3.5" />)}
                        {tab("campaign-analysis", "Campaign Analysis", <Megaphone className="h-3.5 w-3.5" />)}
                    </div>
                </div>

                {activeView === "decks" && <DeckStudio />}
                {activeView === "research" && <ResearchView />}
                {activeView === "competitors" && <CompetitorsView />}
                {activeView === "campaign-analysis" && <CampaignAnalysisView />}
            </div>
        </PermissionProvider>
    )
}
