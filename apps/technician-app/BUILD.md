# OmniDome Technician App — Build Instructions

## Overview

A standalone Next.js 16 + Expo 52 + PWA app for field technicians. This app is
**separate** from the customer portal and has its own package.json, Expo config,
and build pipeline.

## Tech Stack

| Layer          | Technology                          |
| -------------- | ----------------------------------- |
| Framework      | Next.js 16 + React 19               |
| Mobile         | Expo 52 (React Native 0.76)         |
| Styling        | Tailwind CSS 4 (inline, no shadcn)  |
| State          | Zustand 5 (with expo-secure-store)  |
| Icons          | lucide-react                        |
| API            | REST + SSE (EventSource)            |
| Auth           | JWT tokens in SecureStore/localStorage |
| PWA            | @ducanh2912/next-pwa                |
| OTA Updates    | expo-updates                        |

## Prerequisites

- Node.js 20+
- npm 10+
- EAS CLI (`npm install -g eas-cli`)
- Expo account (for native builds)

## Quick Start

```bash
cd apps/technician-app

# Install dependencies
npm install

# Run as Next.js web app (PWA)
npm run dev
# → http://localhost:3000

# Run with Expo dev client
npm run expo:start
```

## Project Structure

```
apps/technician-app/
├── app/
│   ├── layout.tsx              # Root layout (Expo Router)
│   └── (tabs)/
│       ├── layout.tsx          # Bottom tab navigation
│       ├── index.tsx           # Job queue (main page)
│       ├── job/
│       │   └── [id].tsx        # Job detail / work panel
│       ├── stats.tsx           # Technician stats
│       └── profile.tsx         # Profile & settings
├── lib/
│   ├── api/
│   │   ├── client.ts           # API client (all endpoints)
│   │   └── types.ts            # TypeScript types
│   └── stores/
│       └── auth-store.ts       # Zustand auth store
├── config/
│   └── brand.json              # White-label brand config
├── scripts/
│   └── build.sh                # EAS build script
├── package.json
├── app.config.ts               # Expo dynamic config
├── eas.json                    # EAS build profiles
├── next.config.js              # Next.js + PWA config
├── tsconfig.json
└── BUILD.md                    # This file
```

## API Endpoints

All endpoints are relative to `NEXT_PUBLIC_API_URL` (default: `http://localhost:8000`).

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/support/tickets` | Get my job queue |
| GET | `/api/support/tickets/:id` | Get job details |
| POST | `/api/support/tickets/:id/accept` | Accept a job |
| POST | `/api/support/tickets/:id/start` | Start working a job |
| POST | `/api/support/tickets/:id/resolve` | Complete a job |
| POST | `/api/support/tickets/:id/escalate-fno` | Escalate to FNO |
| GET | `/api/iot/devices?contact_id=` | Get customer devices |
| GET | `/api/iot/devices/:id/signal` | Get device signal data |
| POST | `/api/iot/devices/:id/reboot` | Reboot a device |
| GET | `/api/network/radius-accounts?contact_id=` | Get RADIUS account |
| GET | `/api/inventory/stock?sku=` | Check parts availability |
| POST | `/api/inventory/stock/checkout` | Checkout parts |
| POST | `/api/network/speed-test` | Run speed test |
| GET | `/api/support/technicians/me/stats` | Get my stats |
| SSE | `/api/support/technicians/me/stream` | Real-time job dispatch |

## Building for Production

### Web (PWA)

```bash
npm run build
npm run start
```

### Native (Android / iOS)

```bash
# Using the build script
./scripts/build.sh production

# Or directly with EAS
eas build --platform android --profile production
eas build --platform ios --profile production
```

### EAS Build Profiles

| Profile | Use Case | Output |
| ------- | -------- | ------ |
| `development` | Local dev with Expo dev client | APK (debug) |
| `preview` | Internal testing | APK |
| `production` | App store release | AAB (Android), IPA (iOS) |
| `huawei` | Huawei AppGallery | AAB |

### OTA Updates

After publishing a native build, you can push OTA updates:

```bash
eas update --branch production --message "Bug fixes"
```

## White-Label Configuration

Edit `config/brand.json` to customize:

- App name, logo, favicon
- Color scheme (primary, secondary, accent, etc.)
- Fonts
- Contact info

Environment variables for build-time config:

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `BRAND_NAME` | `OmniDome` | App display name |
| `BRAND_PRIMARY_COLOR` | `#6366f1` | Primary brand color (indigo) |
| `BRAND_ACCENT_COLOR` | `#f59e0b` | Accent color (amber) |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | API base URL |

## Authentication

The app uses a Zustand store with platform-aware persistence:

- **Native (Expo):** `expo-secure-store` for secure token storage
- **Web/PWA:** `localStorage` fallback

The auth store persists: `technician`, `isAuthenticated`, `accessToken`, `refreshToken`.

## Real-Time Job Dispatch

The app subscribes to an SSE stream at `/api/support/technicians/me/stream`
for real-time job dispatch. Events:

- `connected` — Stream established
- `initial_state` — Initial job list
- `new_ticket` — New job dispatched to technician
- `ticket_update` — Existing job updated
- `ping` — Keep-alive (ignored)

## Dependencies

**No shadcn/ui** — all UI is built with inline Tailwind CSS classes for minimal
dependency footprint. The dark theme uses a slate color palette matching the
OmniDome brand.
