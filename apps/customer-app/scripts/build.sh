#!/usr/bin/env bash
# OmniDome Customer Portal — Expo Build Script
# Usage: ./scripts/build.sh [profile] [platform]
#
# Profiles: development, preview, production
# Platforms: android, ios, all
#
# Examples:
#   ./scripts/build.sh preview android    # Build APK for testing
#   ./scripts/build.sh preview ios        # Build iOS for testing
#   ./scripts/build.sh production android # Build AAB for Google Play
#   ./scripts/build.sh production all     # Build for all platforms (store release)

set -euo pipefail

PROFILE="${1:-preview}"
PLATFORM="${2:-android}"

# Validate profile
case "$PROFILE" in
  development|preview|production) ;;
  *)
    echo "❌ Invalid profile: $PROFILE"
    echo "   Valid profiles: development, preview, production"
    exit 1
    ;;
esac

# Validate platform
case "$PLATFORM" in
  android|ios|all) ;;
  *)
    echo "❌ Invalid platform: $PLATFORM"
    echo "   Valid platforms: android, ios, all"
    exit 1
    ;;
esac

echo "============================================"
echo "  OmniDome Customer Portal — Expo Build"
echo "============================================"
echo "  Profile:  $PROFILE"
echo "  Platform: $PLATFORM"
echo "============================================"
echo ""

# Check EAS CLI is installed
if ! command -v eas &> /dev/null; then
  echo "❌ EAS CLI not found. Install it with:"
  echo "   npm install -g eas-cli"
  exit 1
fi

# Check EAS is logged in
if ! eas whoami &> /dev/null; then
  echo "❌ Not logged in to EAS. Run:"
  echo "   eas login"
  exit 1
fi

echo "🔨 Starting EAS build..."
echo ""

case "$PROFILE" in
  development)
    echo "📦 Building development build (internal distribution, debug APK/simulator)..."
    eas build --platform "$PLATFORM" --profile development
    ;;
  preview)
    if [ "$PLATFORM" = "android" ]; then
      echo "📦 Building preview APK for Android testing..."
      eas build --platform android --profile preview
    elif [ "$PLATFORM" = "ios" ]; then
      echo "📦 Building preview build for iOS testing..."
      eas build --platform ios --profile preview
    else
      echo "📦 Building preview builds for all platforms..."
      eas build --platform android --profile preview
      eas build --platform ios --profile preview
    fi
    ;;
  production)
    if [ "$PLATFORM" = "android" ]; then
      echo "📦 Building production AAB for Google Play..."
      eas build --platform android --profile production
    elif [ "$PLATFORM" = "ios" ]; then
      echo "📦 Building production IPA for App Store..."
      eas build --platform ios --profile production
    else
      echo "📦 Building production releases for all platforms..."
      eas build --platform android --profile production
      eas build --platform ios --profile production
    fi
    ;;
esac

echo ""
echo "✅ Build submitted successfully!"
echo "   Monitor at: https://expo.dev/accounts/[your-account]/projects/omnidome-customer/builds"
