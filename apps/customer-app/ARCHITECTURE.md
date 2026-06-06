# OmniDome Customer App — Architecture

## Stack
- **Framework**: Next.js 16 (App Router) + React 19
- **Styling**: Tailwind CSS 4, CSS custom properties for white-label theming
- **State**: Zustand (auth store, persisted to localStorage)
- **API**: REST + SSE (Server-Sent Events) for real-time updates
- **PWA**: @ducanh2912/next-pwa — service worker, manifest, offline caching
- **Native**: Expo SDK 52, React Navigation 7, EAS Build
- **Charts**: Recharts
- **UI**: Radix UI primitives + shadcn/ui pattern (CVA, Tailwind merge)

## White-Label System
Branding is controlled via:
1. `config/brand.json` — ISP name, logo, colors, fonts, contact info
2. CSS custom properties — applied at runtime, overridable per-tenant
3. Environment variables — BRAND_NAME, BRAND_PRIMARY_COLOR, etc.

Any ISP can deploy this as their own app by changing the config.

## PWA Features
- Installable on Android, iOS, Desktop
- Offline caching for static assets + API responses
- Service worker with runtime caching strategies
- App shortcuts (Pay Bill, Usage, Support, Store)
- Safe area support for notched devices
- Standalone display mode

## Native Build (Expo)
- **Android**: APK + AAB via EAS Build → Google Play Store
- **iOS**: IPA via EAS Build → App Store
- **Huawei**: AAB via EAS Build → AppGallery (Huawei AppGallery Connect)
- Shared codebase with Next.js via Expo web + React Native
- expo-file-system for offline data
- expo-image-picker for document uploads (RICA)
- expo-notifications for push notifications
- expo-secure-store for token storage

## Route Structure
```
/app
  /(auth)
    /login          — Login page
    /register       — Registration page
  /(portal)
    /dashboard      — Main dashboard (usage, billing, quick actions)
    /billing        — Invoices, payments, debit orders, EFT
    /store          — Product catalog, cart, checkout
    /support        — Ticket list, create, track
    /usage          — Data usage graphs
    /profile        — Account settings, personal info
    /referrals      — Referral program
    /settings       — App settings, notifications, RICA
```

## API Client Architecture
- **ApiClient class** with automatic token refresh
- **SSE connections** for real-time notifications and billing events
- **Offline queue** — requests queued when offline, replayed on reconnect
- **Tenant scoping** via X-Tenant-ID header
- **Error handling** — structured ApiError with status codes

## State Management
- **auth-store.ts** — JWT tokens, customer info, login/logout/refresh
- Persisted to localStorage (web) / SecureStore (native)
- Auto-refresh on 401 responses

## SSE Real-Time Updates
- **Notifications stream** — new tickets, billing events, announcements
- **Billing events stream** — invoice generated, payment received, debit order status
- **Job tracking stream** — delivery tracking, technician GPS

## Security
- JWT access + refresh tokens
- HttpOnly cookies (web) / SecureStore (native)
- Token auto-refresh on expiry
- Tenant-scoped API calls
- RICA document encryption at rest
