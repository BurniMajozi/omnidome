# OmniDome Field Sales App — Build Instructions

## Overview

A standalone Next.js 16 + Expo 52 + PWA app for field sales agents. This app is
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
| API            | REST                                |
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
cd apps/field-sales-app

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
apps/field-sales-app/
├── app/
│   ├── layout.tsx              # Root layout (Expo Router)
│   └── (tabs)/
│       ├── layout.tsx          # Bottom tab navigation
│       ├── index.tsx           # Leads tab (main page)
│       ├── customers.tsx       # Customers/contacts tab
│       ├── deals.tsx           # Deals tab
│       └── commissions.tsx     # Commissions tab
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
| GET | `/sales/leads` | List leads |
| POST | `/sales/leads` | Create lead |
| PUT | `/sales/leads/:id` | Update lead |
| POST | `/sales/leads/:id/convert` | Convert lead to deal |
| GET | `/crm/customers` | List contacts |
| GET | `/crm/customers/:id` | Get contact / 360 view |
| GET | `/sales/deals` | List deals |
| POST | `/sales/deals` | Create deal |
| GET | `/sales/quotes` | List quotes |
| POST | `/sales/quotes` | Create quote |
| GET | `/sales/commissions` | Get my commissions |
| GET | `/inventory/products` | List products |
| GET | `/billing/invoices?customer_id=` | Get customer invoices |

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
| `BRAND_PRIMARY_COLOR` | `#10b981` | Primary brand color (emerald) |
| `BRAND_ACCENT_COLOR` | `#f59e0b` | Accent color (amber) |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | API base URL |

## Authentication

The app uses a Zustand store with platform-aware persistence:

- **Native (Expo):** `expo-secure-store` for secure token storage
- **Web/PWA:** `localStorage` fallback

The auth store persists: `agent`, `isAuthenticated`, `accessToken`, `refreshToken`.

## Dependencies

**No shadcn/ui** — all UI is built with inline Tailwind CSS classes for minimal
dependency footprint. The dark theme uses a slate color palette with emerald
accents matching the OmniDome brand.
