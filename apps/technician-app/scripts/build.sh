#!/bin/bash
# OmniDome Technician App — EAS Build Script
# Usage: ./scripts/build.sh [development|preview|production|huawei]

set -euo pipefail

PROFILE="${1:-preview}"
APP_NAME="omni-technician-app"

echo "🔧 Building ${APP_NAME} — profile: ${PROFILE}"

# Validate profile
case "$PROFILE" in
  development|preview|production|huawei)
    echo "✅ Valid profile: ${PROFILE}"
    ;;
  *)
    echo "❌ Unknown profile: ${PROFILE}"
    echo "   Valid profiles: development, preview, production, huawei"
    exit 1
    ;;
esac

# Check for EAS CLI
if ! command -v eas &> /dev/null; then
  echo "📦 Installing EAS CLI..."
  npm install -g eas-cli
fi

# Install dependencies
echo "📦 Installing dependencies..."
npm install

# Run EAS build
echo "🏗️  Starting EAS build..."
eas build --platform all --profile "${PROFILE}" --non-interactive

echo "✅ Build complete!"
echo ""
echo "📱 To run locally:"
echo "   npm run dev          # Next.js dev server"
echo "   npm run expo:start   # Expo dev client"
