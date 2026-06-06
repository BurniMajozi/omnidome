# Customer Portal — Expo Build Guide

## Prerequisites
```bash
npm install -g eas-cli
eas login
eas build:configure
```

## Build Profiles

### Android (Google Play)
```bash
# Development APK
eas build --platform android --profile development

# Production AAB (for Google Play Store)
eas build --platform android --profile production
```

### iOS (App Store)
```bash
# Development (simulator)
eas build --platform ios --profile development

# Production (App Store)
eas build --platform ios --profile production
```

### Huawei (AppGallery)
```bash
# Build AAB for Huawei AppGallery
eas build --platform android --profile huawei
```

## White-Label Configuration

Before building, update these files:

1. **config/brand.json** — ISP name, colors, logo paths, contact info
2. **app.json** — bundle ID, app name, splash screen
3. **expo/huawei/appgallery-config.json** — Huawei-specific config

### Environment Variables per Build

```bash
# Set brand per build
eas build --platform android --profile production \
  --env BRAND_NAME="MyISP" \
  --env BRAND_PRIMARY_COLOR="#2563eb" \
  --env API_BASE_URL="https://api.myisp.co.za"
```

## App Icons & Splash

Required assets in `assets/`:
- `icon.png` (1024x1024) — App icon
- `adaptive-icon.png` (432x432) — Android adaptive icon
- `splash.png` (1284x2778) — Splash screen
- `favicon.png` (48x48) — Web favicon
- `notification-icon.png` (96x96) — Push notification icon

## Push Notifications

### FCM (Android / Huawei)
1. Create project in Firebase Console
2. Download `google-services.json` → place in project root
3. For Huawei: also configure in Huawei AppGallery Connect

### APNs (iOS)
1. Create APNs key in Apple Developer Portal
2. Upload to App Store Connect
3. Configure in EAS: `eas credentials`

## Permissions

The app declares these native permissions:

| Permission | Purpose | Platform |
|---|---|---|
| CAMERA | RICA document capture | Android, iOS |
| PHOTO_LIBRARY | RICA document upload | iOS |
| READ_EXTERNAL_STORAGE | RICA document upload | Android |
| LOCATION | Coverage check | Android, iOS |
| NOTIFICATIONS | Push notifications | Android, iOS |
| FACE ID | Secure credential storage | iOS |

## Offline Support

The PWA service worker caches:
- Static assets (JS, CSS, images, fonts)
- API responses (NetworkFirst strategy)
- App shell for offline access

When offline:
- Dashboard shows cached data
- Store browsing works (cached catalog)
- Support ticket creation is queued
- Cart changes sync when back online

## Bundle Size Targets

| Platform | Target |
|---|---|
| Android APK (dev) | < 50 MB |
| Android AAB (prod) | < 30 MB |
| iOS IPA (prod) | < 40 MB |
| PWA (gzipped) | < 500 KB initial |
