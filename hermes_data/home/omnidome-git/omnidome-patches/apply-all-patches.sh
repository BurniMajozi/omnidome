#!/bin/bash
# OmniDome — Apply Web Analytics + Journey Engine Patches
# Run from project root: omnidome-patches/apply-all-patches.sh

set -e

OMNIDOME_DIR="/opt/data/workspace/omnidome"
PATCHES_DIR="/opt/data/home/omnidome-patches"

echo "============================================"
echo " OmniDome — Apply Analytics + Journey Engine"
echo "============================================"

# ═══════════════════════════════════════════════
# 1. JOURNEY ENGINE (Backend)
# ═══════════════════════════════════════════════
echo ""
echo "🔧 [1/5] Creating Journey Engine service..."
mkdir -p "$OMNIDOME_DIR/services/journey_engine"
cp "$PATCHES_DIR/services/journey_engine/models.py" "$OMNIDOME_DIR/services/journey_engine/models.py"
cp "$PATCHES_DIR/services/journey_engine/database.py" "$OMNIDOME_DIR/services/journey_engine/database.py"
cp "$PATCHES_DIR/services/journey_engine/main.py" "$OMNIDOME_DIR/services/journey_engine/main.py"
cp "$PATCHES_DIR/services/journey_engine/rule_engine.py" "$OMNIDOME_DIR/services/journey_engine/rule_engine.py"
cp "$PATCHES_DIR/services/journey_engine/journey_manager.py" "$OMNIDOME_DIR/services/journey_engine/journey_manager.py"
cp "$PATCHES_DIR/services/journey_engine/__init__.py" "$OMNIDOME_DIR/services/journey_engine/__init__.py"
cp "$PATCHES_DIR/services/journey_engine/requirements.txt" "$OMNIDOME_DIR/services/journey_engine/requirements.txt"
cp "$PATCHES_DIR/services/journey_engine/Dockerfile" "$OMNIDOME_DIR/services/journey_engine/Dockerfile"
echo "  ✅ Journey Engine service files copied"

# ═══════════════════════════════════════════════
# 2. JOURNEY ENGINE (Frontend)
# ═══════════════════════════════════════════════
echo ""
echo "🎨 [2/5] Creating Journey Engine frontend..."
mkdir -p "$OMNIDOME_DIR/apps/web/components/modules/journey-builder"
cp "$PATCHES_DIR/apps/web/components/modules/journey-builder/journey-builder-dashboard.tsx" \
   "$OMNIDOME_DIR/apps/web/components/modules/journey-builder/journey-builder-dashboard.tsx"

mkdir -p "$OMNIDOME_DIR/apps/web/lib"
cp "$PATCHES_DIR/apps/web/lib/journey-api.ts" "$OMNIDOME_DIR/apps/web/lib/journey-api.ts"

mkdir -p "$OMNIDOME_DIR/apps/web/app/api/journey-engine/[...path]"
cp "$PATCHES_DIR/apps/web/app/api/journey-engine/[...path]/route.ts" \
   "$OMNIDOME_DIR/apps/web/app/api/journey-engine/[...path]/route.ts"
echo "  ✅ Journey Engine frontend files copied"

# ═══════════════════════════════════════════════
# 3. RETENTION MODULE PATCH
# ═══════════════════════════════════════════════
echo ""
echo "🔗 [3/5] Patching retention module..."
PORTAL_FILE="$OMNIDOME_DIR/apps/web/components/modules/retention-module.tsx"
if [ -f "$PORTAL_FILE" ]; then
  cp "$PORTAL_FILE" "$PORTAL_FILE.bak.$(date +%s)"
  python3 << 'PYEOF'
import re

path = "/opt/data/workspace/omnidome/apps/web/components/modules/retention-module.tsx"
with open(path, "r") as f:
    content = f.read()

# Add import after existing imports
import_line = 'import { JourneyBuilderDashboard } from "./journey-builder/journey-builder-dashboard"\n'
if "JourneyBuilderDashboard" not in content:
    # Find last import line
    lines = content.split("\n")
    last_import_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("import{"):
            last_import_idx = i
    if last_import_idx >= 0:
        lines.insert(last_import_idx + 1, import_line.rstrip())
        content = "\n".join(lines)

# Replace journeys TabsContent
old_pattern = r'<TabsContent value="journeys" className="space-y-6">.*?</TabsContent>'
new_content = '''<TabsContent value="journeys" className="mt-4">
                    <JourneyBuilderDashboard />
                </TabsContent>'''
content = re.sub(old_pattern, new_content, content, flags=re.DOTALL)

with open(path, "w") as f:
    f.write(content)
print("  ✅ Retention module patched")
PYEOF
else
  echo "  ⚠️  retention-module.tsx not found — skip"
fi

# ═══════════════════════════════════════════════
# 4. DOCKER COMPOSE
# ═══════════════════════════════════════════════
echo ""
echo "🐳 [4/5] Updating docker-compose..."
if ! grep -q "journey_engine:" "$OMNIDOME_DIR/docker-compose.yaml"; then
  cat "$PATCHES_DIR/docker-compose-journey-engine.yaml" >> "$OMNIDOME_DIR/docker-compose.yaml"
  echo "  ✅ Journey Engine added to docker-compose"
else
  echo "  ℹ️  Journey Engine already in docker-compose"
fi

if ! grep -q "web_analytics:" "$OMNIDOME_DIR/docker-compose.yaml"; then
  cat "$PATCHES_DIR/docker-compose-web-analytics.yaml" >> "$OMNIDOME_DIR/docker-compose.yaml"
  echo "  ✅ Web Analytics added to docker-compose"
else
  echo "  ℹ️  Web Analytics already in docker-compose"
fi

# ═══════════════════════════════════════════════
# 5. ENVIRONMENT VARIABLES
# ═══════════════════════════════════════════════
echo ""
echo "🌍 [5/5] Updating .env..."
if ! grep -q "JOURNEY_ENGINE_SERVICE_URL" "$OMNIDOME_DIR/.env"; then
  echo "" >> "$OMNIDOME_DIR/.env"
  echo "# Journey Engine Service" >> "$OMNIDOME_DIR/.env"
  echo "JOURNEY_ENGINE_SERVICE_URL=http://journey_engine:8017" >> "$OMNIDOME_DIR/.env"
  echo "  ✅ Journey Engine env vars added"
else
  echo "  ℹ️  Journey Engine env vars already set"
fi

if ! grep -q "WEB_ANALYTICS_SERVICE_URL" "$OMNIDOME_DIR/.env"; then
  echo "" >> "$OMNIDOME_DIR/.env"
  echo "# Web Analytics Service" >> "$OMNIDOME_DIR/.env"
  echo "WEB_ANALYTICS_SERVICE_URL=http://web_analytics:8016" >> "$OMNIDOME_DIR/.env"
  echo "NEXT_PUBLIC_ANALYTICS_ENDPOINT=/api/analytics" >> "$OMNIDOME_DIR/.env"
  echo "  ✅ Web Analytics env vars added"
else
  echo "  ℹ️  Web Analytics env vars already set"
fi

# Done
echo ""
echo "============================================"
echo " ✅ All patches applied successfully!"
echo "============================================"
echo ""
echo "Services added:"
echo "  • Journey Engine  : port 8017 (cancel → save)"
echo "  • Web Analytics   : port 8016 (traffic tracking)"
echo ""
echo "To rebuild:"
echo "  cd /opt/data/workspace/omnidome"
echo "  docker compose up -d --build journey_engine web_analytics"
echo ""
echo "The Retention module's 'Journeys' tab now shows the"
echo "full Journey Builder with rule engine + offer config."
