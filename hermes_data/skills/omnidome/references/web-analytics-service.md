# Web Analytics Service — Session 3 Reference

## Overview
First-party, privacy-compliant web analytics service (self-hosted Google Analytics alternative).
Built in Session 3 (2026-06-xx) as a new OmniDome microservice.

## File Locations

### Backend (patches → live)
| Patch path | Live path |
|---|---|
| `/opt/data/home/omnidome-patches/services/web_analytics/models.py` | `services/web_analytics/models.py` |
| `/opt/data/home/omnidome-patches/services/web_analytics/database.py` | `services/web_analytics/database.py` |
| `/opt/data/home/omnidome-patches/services/web_analytics/main.py` | `services/web_analytics/main.py` |
| `/opt/data/home/omnidome-patches/services/web_analytics/requirements.txt` | `services/web_analytics/requirements.txt` |
| `/opt/data/home/omnidome-patches/services/web_analytics/Dockerfile` | `services/web_analytics/Dockerfile` |

### Frontend (patches → live)
| Patch path | Live path |
|---|---|
| `web_analytics_sdk.ts` | `apps/web/lib/analytics/tracker.ts` |
| `apps/web/lib/analytics/api.ts` | (same) |
| `apps/web/app/api/analytics/track/[...path]/route.ts` | (same) |
| `apps/web/app/api/analytics/service/[...path]/route.ts` | (same) |
| `apps/web/components/analytics-provider.tsx` | (same) |
| `apps/web/components/modules/web-analytics/web-analytics-dashboard.tsx` | (same) |
| `apps/web/app/layout.tsx` | (same — patched) |
| `apps/web/components/dashboard/sidebar.tsx` | (same — patched) |

### Infrastructure
| File | Purpose |
|---|---|
| `/opt/data/home/omnidome-patches/docker-compose-web-analytics.yaml` | Appended to docker-compose.yaml |
| `/opt/data/home/omnidome-patches/apply-web-analytics.sh` | One-click apply script |

## DB Schema (4 tables)
1. **page_views** — Every page visit with device, geo, engagement data
2. **click_events** — Every click with element details + position
3. **form_events** — Form interactions (view/start/submit/abandon/error)
4. **session_tracking** — Session lifecycle with UTM params, device snapshot, engagement summary

## API Endpoints
- `POST /track/pageview` — Record page view (auto-creates session tracking)
- `POST /track/click` — Record click event
- `POST /track/form` — Record form event
- `POST /track/session/end` — End session
- `GET /analytics/overview` — KPIs: pageviews, visitors, sessions, avg duration, bounce rate
- `GET /analytics/traffic` — Daily traffic time series
- `GET /analytics/pages` — Top pages with unique visitors + avg time on page
- `GET /analytics/devices` — Device/browser/OS/screen breakdowns
- `GET /analytics/locations` — Country + city breakdowns
- `GET /analytics/forms` — Form funnel stats (views/starts/submits/abandons/conversion rate)
- `GET /analytics/referrers` — Traffic source referrers
- `GET /analytics/utm` — UTM campaign breakdown
- `GET /analytics/realtime` — Active users in last 5 min + top pages

## Environment Variables
- `WEB_ANALYTICS_SERVICE_URL` — Backend URL (default: `http://web_analytics:8016`)
- `NEXT_PUBLIC_ANALYTICS_ENDPOINT` — Frontend endpoint (default: `/api/analytics`)
- `DATABASE_URL` — Shared PostgreSQL connection

## Key Design Decisions
- **Standalone service** (not using common/db.py) — demonstrates the pattern for services that need independent deployment
- **user-agents** library for device detection — more reliable than manual UA parsing
- **Geo from CDN headers** (CF/Vercel) — works behind load balancers without IP lookup
- **SHA256-hashed IPs** with configurable salt — POPIA-friendly
- **No cookies** — uses localStorage for session/visitor IDs (lighter privacy footprint)
- **sendBeacon fallback** — events still sent on page unload
- **Batched sending** — 10 events per flush, 5-second interval

## Integration Points
- Added to Portal Management sidebar as child: `{ label: "Website Analytics", target: "web-analytics" }`
- Added tab to portal module: `<TabsTrigger value="web-analytics">Website Analytics</TabsTrigger>`
- Added import: `import { WebAnalyticsDashboard } from "./web-analytics/web-analytics-dashboard"`
- Added content: `<TabsContent value="web-analytics" className="mt-4"><WebAnalyticsDashboard /></TabsContent>`
- AnalyticsProvider wrapped around children in layout.tsx (inside ThemeProvider, alongside Vercel Analytics)

## Apply Script
Run: `bash /opt/data/home/omnidome-patches/apply-web-analytics.sh`

The script:
1. Copies all backend service files
2. Copies all frontend files (SDK, API, dashboard, provider, API routes, layout, sidebar)
3. Patches portal-module.tsx via Python (adds import + tab trigger + tab content)
4. Appends docker-compose service definition
5. Adds env vars to .env

## Rebuild Command
```bash
cd /opt/data/workspace/omnidome
docker compose up -d --build web_analytics
```
