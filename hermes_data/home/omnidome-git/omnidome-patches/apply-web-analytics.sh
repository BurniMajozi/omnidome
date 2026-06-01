#!/bin/bash
# OmniDome Web Analytics — Apply Patches
# Run from the project root: bash apply-web-analytics.sh

set -e

OMNIDOME_DIR="/opt/data/workspace/omnidome"
PATCHES_DIR="/opt/data/home/omnidome-patches"

echo "🔧 Applying Web Analytics patches..."

# --- Backend Service ---
echo "📦 Creating web_analytics service..."
mkdir -p "$OMNIDOME_DIR/services/web_analytics"
cp "$PATCHES_DIR/services/web_analytics/models.py" "$OMNIDOME_DIR/services/web_analytics/"
cp "$PATCHES_DIR/services/web_analytics/database.py" "$OMNIDOME_DIR/services/web_analytics/"
cp "$PATCHES_DIR/services/web_analytics/main.py" "$OMNIDOME_DIR/services/web_analytics/"
cp "$PATCHES_DIR/services/web_analytics/requirements.txt" "$OMNIDOME_DIR/services/web_analytics/"
cp "$PATCHES_DIR/services/web_analytics/Dockerfile" "$OMNIDOME_DIR/services/web_analytics/"

# --- Frontend: API routes ---
echo "📡 Creating API routes..."
mkdir -p "$OMNIDOME_DIR/apps/web/app/api/analytics/track/[...path]"
cp "$PATCHES_DIR/apps/web/app/api/analytics/track/[...path]/route.ts" "$OMNIDOME_DIR/apps/web/app/api/analytics/track/[...path]/route.ts"

mkdir -p "$OMNIDOME_DIR/apps/web/app/api/analytics/service/[...path]"
cp "$PATCHES_DIR/apps/web/app/api/analytics/service/[...path]/route.ts" "$OMNIDOME_DIR/apps/web/app/api/analytics/service/[...path]/route.ts"

# --- Frontend: Lib ---
echo "📚 Creating analytics library..."
mkdir -p "$OMNIDOME_DIR/apps/web/lib/analytics"
cp "$PATCHES_DIR/apps/web/lib/analytics/api.ts" "$OMNIDOME_DIR/apps/web/lib/analytics/api.ts"
cp "$PATCHES_DIR/web_analytics_sdk.ts" "$OMNIDOME_DIR/apps/web/lib/analytics/tracker.ts"

# --- Frontend: Components ---
echo "🧩 Creating analytics components..."
mkdir -p "$OMNIDOME_DIR/apps/web/components/modules/web-analytics"
cp "$PATCHES_DIR/apps/web/components/modules/web-analytics/web-analytics-dashboard.tsx" "$OMNIDOME_DIR/apps/web/components/modules/web-analytics/web-analytics-dashboard.tsx"
cp "$PATCHES_DIR/apps/web/components/analytics-provider.tsx" "$OMNIDOME_DIR/apps/web/components/analytics-provider.tsx"

# --- Frontend: Updated layout ---
echo "🏗️  Updating layout.tsx..."
cp "$PATCHES_DIR/apps/web/app/layout.tsx" "$OMNIDOME_DIR/apps/web/app/layout.tsx"

# --- Frontend: Updated sidebar ---
echo "📋 Updating sidebar..."
cp "$PATCHES_DIR/apps/web/components/dashboard/sidebar.tsx" "$OMNIDOME_DIR/apps/web/components/dashboard/sidebar.tsx"

# --- Frontend: Portal module patch ---
echo "🌐 Patching portal module..."
# Add the import line for WebAnalyticsDashboard (after the existing imports)
# and add the web-analytics tab
PORTAL_FILE="$OMNIDOME_DIR/apps/web/components/modules/portal-module.tsx"
PORTAL_BACKUP="$PORTAL_FILE.bak.$(date +%s)"
cp "$PORTAL_FILE" "$PORTAL_BACKUP"
echo "  Backed up portal-module.tsx to $PORTAL_BACKUP"

# Use python to do the targeted insertion
python3 << 'PYEOF'
import re

portal_path = "/opt/data/workspace/omnidome/apps/web/components/modules/portal-module.tsx"

with open(portal_path, "r") as f:
    content = f.read()

# 1. Add import for WebAnalyticsDashboard after existing imports
import_line = 'import { WebAnalyticsDashboard } from "./web-analytics/web-analytics-dashboard"\n'
if "WebAnalyticsDashboard" not in content:
    # Find the last import line
    last_import = content.rfind("import ")
    if last_import >= 0:
        # Find end of that import
        end_of_import = content.find("\n", last_import)
        if end_of_import >= 0:
            content = content[:end_of_import+1] + import_line + content[end_of_import+1:]

# 2. Add web-analytics tab trigger after the "website" tab trigger
if 'value="web-analytics"' not in content:
    # Find the website tab trigger and add after it
    website_tab = '<TabsTrigger value="website">Website Builder</TabsTrigger>'
    web_analytics_tab = '<TabsTrigger value="web-analytics">Website Analytics</TabsTrigger>'
    content = content.replace(
        website_tab,
        website_tab + "\n          " + web_analytics_tab,
    )

# 3. Add TabsContent for web-analytics after the website TabsContent
if '<TabsContent value="web-analytics">' not in content:
    # Find the end of the website TabsContent (before journeys tab)
    website_close = '</TabsContent>\n\n        <TabsContent value="journeys">'
    web_analytics_content = '''</TabsContent>

        <TabsContent value="web-analytics" className="mt-4">
          <WebAnalyticsDashboard />
        </TabsContent>

        <TabsContent value="journeys">'''
    content = content.replace(website_close, web_analytics_content)

with open(portal_path, "w") as f:
    f.write(content)

print("  ✅ Portal module patched successfully")
PYEOF

# --- Docker Compose additions ---
echo "🐳 Appending docker-compose additions..."
if ! grep -q "web_analytics:" "$OMNIDOME_DIR/docker-compose.yaml"; then
  cat "$PATCHES_DIR/docker-compose-web-analytics.yaml" >> "$OMNIDOME_DIR/docker-compose.yaml"
fi

# --- Environment variables ---
echo "🌍 Adding environment variables..."
if ! grep -q "WEB_ANALYTICS_SERVICE_URL" "$OMNIDOME_DIR/.env"; then
  echo "" >> "$OMNIDOME_DIR/.env"
  echo "# Web Analytics Service" >> "$OMNIDOME_DIR/.env"
  echo "WEB_ANALYTICS_SERVICE_URL=http://web_analytics:8016" >> "$OMNIDOME_DIR/.env"
  echo "NEXT_PUBLIC_ANALYTICS_ENDPOINT=/api/analytics" >> "$OMNIDOME_DIR/.env"
fi

echo ""
echo "✅ Web Analytics patches applied successfully!"
echo ""
echo "Summary:"
echo "  • Backend: services/web_analytics/ (FastAPI tracking + dashboard API)"
echo "  • Frontend: Tracking SDK auto-captures page views, clicks, forms, devices"
echo "  • Frontend: Analytics dashboard with traffic, devices, locations, forms tabs"
echo "  • Frontend: Website Analytics tab added to Portal Management sidebar"
echo "  • Frontend: AnalyticsProvider integrated into layout.tsx"
echo "  • Docker: web_analytics service on port 8016"
echo ""
echo "To rebuild & deploy:"
echo "  cd /opt/data/workspace/omnidome && docker compose up -d --build web_analytics"
echo ""
echo "Note: If you already have Vercel Analytics enabled, the tracker runs alongside it."
echo "The web_analytics service gives you first-party, privacy-compliant analytics."
