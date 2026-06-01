# Portal Module Patch — Add Website Analytics Tab
# This is a sed-style patch guide for portal-module.tsx
#
# The portal-module.tsx needs these changes:
#
# 1. Add import for WebAnalyticsDashboard:
#    import { WebAnalyticsDashboard } from "./web-analytics/web-analytics-dashboard"
#
# 2. Add "web-analytics" tab trigger to the TabsList (after the "website" tab trigger):
#    <TabsTrigger value="web-analytics">Website Analytics</TabsTrigger>
#
# 3. Add TabsContent for web-analytics (after the website TabsContent, before journeys):
#    <TabsContent value="web-analytics" className="mt-4">
#      <WebAnalyticsDashboard />
#    </TabsContent>
#
# Apply these changes to: apps/web/components/modules/portal-module.tsx
