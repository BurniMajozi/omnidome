# Retention Module Patch — Replace Journeys tab with Journey Builder
#
# In apps/web/components/modules/retention-module.tsx, make these changes:
#
# 1. Add import at top:
#    import { JourneyBuilderDashboard } from "./journey-builder/journey-builder-dashboard"
#
# 2. Replace the entire <TabsContent value="journeys"> section (lines ~665-711)
#    with:
#    <TabsContent value="journeys" className="mt-4">
#      <JourneyBuilderDashboard />
#    </TabsContent>
#
# That's it — the JourneyBuilderDashboard is self-contained with its own
# tabs for Journeys, Offers, Funnel, and ROI.
