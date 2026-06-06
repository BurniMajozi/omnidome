# OmniDome Customer Portal — Build Guide

This guide covers building the OmniDome customer portal as a native mobile app using Expo and EAS Build.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Initial Setup](#initial-setup)
- [Environment Variables](#environment-variables)
- [Build Profiles](#build-profiles)
- [Step-by-Step Build Instructions](#step-by-step-build-instructions)
- [OTA Updates with expo-updates](#ota-updates-with-expo-updates)
- [App Icons & Splash Screens](#app-icons--splash-screens)
- [Push Notifications](#push-notifications)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Accounts & Tools

| Requirement | Purpose | Link |
|---|---|---|
| **EAS CLI** | Build orchestration | `npm install -g eas-cli` |
| **Apple Developer Account** | iOS builds & App Store submission | [developer.apple.com](https://developer.apple.com) |
| **Google Play Console** | Android builds & Play Store submission | [play.google.com/console](https://play.google.com/console) |
| **Expo Account** | EAS project management | [expo.dev](https://expo.dev) |
| **Node.js 20+** | Build environment | — |
| **Firebase Project** | FCM push notifications (Android) | [console.firebase.google.com](https://console.firebase.google.com) |

### Install EAS CLI

```bash
npm install -g eas-cli
eas login
```

### Verify Setup

```bash
# Check EAS CLI version (must be >= 14.0.0)
eas --version

# Verify login
eas whoami
```

---

## Initial Setup

### 1. Configure EAS Project

```bash
cd apps/customer-portal
eas project:init
```

This creates/updates the `projectId` in `app.config.ts` under `extra.eas.projectId`.

### 2. Configure Native Credentials

```bash
# Android — FCM push notifications
# Place google-services.json in the project root

# iOS — APNs & code signing
eas credentials
# Follow prompts to configure:
#   - Apple Distribution Certificate
#   - Apple Provisioning Profile
#   - APNs key (for push notifications)
```

### 3. Configure Android Signing

```bash
eas credentials --platform android
# Select "Google Play Store" → "Let EAS manage your keystore"
# Or provide your own upload key
```

---

## Environment Variables

The app uses environment variables for API endpoints and branding. These are injected at build time.

### Required Variables

| Variable | Description | Example |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Backend API base URL | `https://api.omnidome.app` |
| `BRAND_NAME` | ISP brand name | `OmniDome` |
| `BRAND_PRIMARY_COLOR` | Primary brand color (hex) | `#2563eb` |
| `BRAND_ACCENT_COLOR` | Accent brand color (hex) | `#f59e0b` |

### Setting Variables in EAS

**Option A: In `eas.json` build profiles (recommended)**

The production profile in `eas.json` already sets default values:

```json
{
  "build": {
    "production": {
      "env": {
        "NEXT_PUBLIC_API_BASE_URL": "https://api.omnidome.app",
        "BRAND_NAME": "OmniDome",
        "BRAND_PRIMARY_COLOR": "#2563eb",
        "BRAND_ACCENT_COLOR": "#f59e0b"
      }
    }
  }
}
```

**Option B: Per-build overrides via CLI**

```bash
eas build --platform android --profile production \
  --env NEXT_PUBLIC_API_BASE_URL="https://api.staging.omnidome.app" \
  --env BRAND_NAME="OmniDome Staging"
```

**Option C: EAS Secrets (for sensitive values)**

```bash
eas secret:create --name SUPABASE_ANON_KEY --value "your-key-here"
```

### API Client Configuration

The API client (`lib/api-client.ts`) reads the base URL from environment variables:

```typescript
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'http://localhost:8000';
```

This ensures the same code works in:
- **Web/PWA**: Uses `NEXT_PUBLIC_API_BASE_URL` from `next.config.js`
- **Native (Expo)**: Uses `NEXT_PUBLIC_API_BASE_URL` from EAS build profile env vars
- **Development**: Falls back to `http://localhost:8000`

---

## Build Profiles

### Development

- **Purpose**: Internal testing with debug tools
- **Android**: Debug APK (not for store distribution)
- **iOS**: Simulator build (requires Xcode)
- **Distribution**: Internal only

```bash
./scripts/build.sh development android
./scripts/build.sh development ios
```

### Preview

- **Purpose**: QA testing on real devices
- **Android**: Release APK (can be sideloaded)
- **iOS**: Release build (requires ad-hoc provisioning)
- **Distribution**: Internal testing

```bash
./scripts/build.sh preview android
./scripts/build.sh preview ios
```

### Production

- **Purpose**: Store release
- **Android**: AAB (Android App Bundle) for Google Play
- **iOS**: IPA for App Store Connect
- **Node**: 20
- **Resource Class**: Large (for faster builds)
- **Distribution**: Store

```bash
./scripts/build.sh production android
./scripts/build.sh production ios
./scripts/build.sh production all
```

### Huawei (AppGallery)

- **Purpose**: Huawei AppGallery release
- **Android**: AAB format
- **Distribution**: AppGallery

```bash
eas build --platform android --profile huawei
```

---

## Step-by-Step Build Instructions

### Android (Google Play Store)

1. **Prepare assets**: Ensure `assets/icon.png`, `assets/adaptive-icon.png`, `assets/splash.png` exist
2. **Configure FCM**: Place `google-services.json` in project root
3. **Build production AAB**:

   ```bash
   cd apps/customer-portal
   ./scripts/build.sh production android
   ```

4. **Submit to Play Store**:

   ```bash
   eas submit --platform android --profile production
   ```

   Or manually upload the AAB from the EAS build dashboard.

### iOS (App Store)

1. **Prepare assets**: Ensure `assets/icon.png`, `assets/splash.png` exist
2. **Configure APNs**: Set up push notification key in Apple Developer Portal
3. **Build production IPA**:

   ```bash
   cd apps/customer-portal
   ./scripts/build.sh production ios
   ```

4. **Submit to App Store**:

   ```bash
   eas submit --platform ios --profile production
   ```

### All Platforms (Full Release)

```bash
cd apps/customer-portal
./scripts/build.sh production all
```

---

## OTA Updates with expo-updates

The app is configured for Over-The-Air (OTA) updates using `expo-updates`. This allows pushing bug fixes and minor updates without going through the app store review process.

### Configuration

OTA updates are configured in `app.config.ts`:

```typescript
runtimeVersion: {
  policy: 'appVersion',  // Ties OTA updates to app version
},
updates: {
  url: 'https://u.expo.dev/your-eas-project-id',
  checkAutomatically: 'ON_LOAD',
  fallbackToCacheTimeout: 0,
},
```

### Publishing OTA Updates

1. **Make your code changes** and commit them
2. **Publish the update**:

   ```bash
   eas update --branch production --message "Fix: billing page crash"
   ```

3. **Users receive the update** automatically on next app launch

### Update Channels

| Channel | Use Case |
|---|---|
| `production` | Live users |
| `preview` | QA / beta testers |
| `development` | Internal dev builds |

### Best Practices

- **Only push JS/asset changes via OTA** — native code changes require a new build
- **Always test OTA updates** on the preview branch before pushing to production
- **Use semantic versioning** — the `runtimeVersion.policy: 'appVersion'` ensures updates only apply to matching app versions
- **Set fallbackToCacheTimeout: 0** — ensures the app loads immediately even if the update check fails

---

## App Icons & Splash Screens

Required assets in `assets/` directory:

| File | Size | Purpose |
|---|---|---|
| `icon.png` | 1024×1024 | App icon (all platforms) |
| `adaptive-icon.png` | 432×432 | Android adaptive icon |
| `splash.png` | 1284×2778 | Splash screen |
| `favicon.png` | 48×48 | Web/PWA favicon |
| `notification-icon.png` | 96×96 | Push notification icon (Android) |
| `notification-sound.wav` | — | Custom notification sound |

---

## Push Notifications

### Android (FCM)

1. Create a project in [Firebase Console](https://console.firebase.google.com)
2. Add an Android app with package `com.omnidome.customer`
3. Download `google-services.json` and place it in the project root
4. The `expo-notifications` plugin handles the rest

### iOS (APNs)

1. Create an APNs key in the [Apple Developer Portal](https://developer.apple.com)
2. Upload the key to EAS:

   ```bash
   eas credentials --platform ios
   # Select "Push Notifications" → "APNs key"
   ```

3. The `expo-notifications` plugin configures the entitlements

### Huawei (HMS Push)

For Huawei devices without Google Play Services:
1. Configure in Huawei AppGallery Connect
2. The `expo-notifications` plugin handles HMS integration

---

## Troubleshooting

### Build fails with "projectId not found"

```bash
eas project:init
# Then update app.config.ts with the new projectId
```

### iOS build fails with "No provisioning profile"

```bash
eas credentials --platform ios
# Select "Production" → "Let EAS manage your credentials"
```

### Android build fails with "google-services.json not found"

Ensure `google-services.json` is in the project root (`apps/customer-portal/`).

### API calls fail in native build

Check that `NEXT_PUBLIC_API_BASE_URL` is set correctly in the EAS build profile. The API client reads this at build time.

### OTA updates not applying

1. Verify the `runtimeVersion` matches between the build and the update
2. Check that the `updates.url` in `app.config.ts` matches your EAS project ID
3. Ensure `checkAutomatically` is set to `ON_LOAD`

### Bundle size too large

- Run `npx expo-doctor` to check for issues
- Enable ProGuard/R8 for Android: add `"enableProguardInReleaseBuilds": true` to `android` config in `eas.json`
- Use `expo-asset` for optimized image loading
