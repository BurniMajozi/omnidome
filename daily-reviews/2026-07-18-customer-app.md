# Daily Review — apps/customer-app (2026-07-18)

## 1. Today's plan
Component **1 of 35** in the rotation (5 apps + 29 services + 1 integration). State file was missing, so the cycle restarted at the first app alphabetically: `apps/customer-app` (Next.js portal + Expo native hybrid).

## 2. What was found / achieved

### Critical — broken or fake flows
- **RICA submission never calls the API.** `expo/screens/RicaCapture.tsx` (~line 76-104): `submitRica()` builds the FormData, then just shows a "Success" alert with the comment `// In production: API call`. A compliance-critical flow silently does nothing.
- **Camera capture is stubbed.** Same file, ~line 112: the capture button pushes the literal string `"captured_image_uri"` instead of a real photo (`// Capture logic`).
- **Push token never registered.** Same file, ~line 47: token is `console.log`ged with comment `// Send token to API` — no backend call.
- **LoginForm contract mismatch — likely doesn't compile/work.** `components/auth/LoginForm.tsx` imports `{ ApiClient }` from `lib/api/client.ts`, but that class is **not exported** (only the `api` singleton is). It also reads `res.access_token` / `res.expires_in` (snake_case) while `api.login()` returns `{ accessToken, refreshToken, customer }`. Cookies would be `undefined`. Also stores JWTs in non-httpOnly cookies (security concern).
- **Two competing auth paths.** `lib/stores/auth-store.ts` (Zustand + secure store, camelCase) vs LoginForm's cookie approach — one of these is dead code.
- **home/page.tsx calls a private method.** ~line 626: `api.request<IoTDashboardData>("/portal/iot/dashboard")` — `request()` is `private` in ApiClient; TS error or bypass.

### Mock/stub data
- **home/page.tsx** ~line 526-616: full `getMockData()` fallback (fake scenes, cameras, sensors, rooms) used **silently in production** whenever the IoT API errors — users would see fake devices with no indication.
- **support/page.tsx** ~line 40-57: `INITIAL_TICKETS` hardcoded mock tickets ("replace with api.getTickets() when ready"). Ticket list never loads from backend.
- **analytics/page.tsx** ~line 55-60: hardcoded dashboard template fallback with empty `widget_config`.

### Hardcoded config / TODOs
- **app.config.ts**: `projectId: 'your-eas-project-id'` and `updates.url: 'https://u.expo.dev/your-eas-project-id'` — placeholder EAS IDs; OTA updates and EAS builds can't work.
- **lib/api/client.ts** line 13-15: base URL falls back to `http://localhost:8000` — fine for dev, but no production guard if env vars are missing.
- **client.ts** `triggerCancel()`: hardcoded fallback `account_number: 'ACC-0001'`.
- **src/config/brand.json**: placeholder contact details (`0800 000 000`).
- Empty catch blocks with `/* TODO: toast */` in **analytics/page.tsx** (~74-86) and **ab-testing/page.tsx** (~57-71) — all mutations fail silently.
- **client.ts** 401 retry can loop: on refresh success it re-requests, and a repeated 401 retries again (no retry cap).

### Solid parts
API client surface is comprehensive (billing, store, IoT, journey engine), auth store token refresh sync is well thought out, AgentChat wrapper cleanly delegates to `@omnidome/agent-chat`.

## 3. Critical decisions / flags (need a human)
1. **Which auth path is canonical?** Zustand store (camelCase, secure store) vs LoginForm cookies (snake_case). Backend response shape must be confirmed before fixing — the two disagree.
2. **RICA flow**: should the Expo screen use `api.submitRicaVerification()` (JSON) or a new multipart upload endpoint? The FormData it builds has no matching client method.
3. **Mock IoT fallback**: keep behind a `NEXT_PUBLIC_DEMO_MODE` flag, or remove entirely? Currently ships fake data to real users on API failure.
4. **EAS project ID + FCM `google-services.json`** are missing — needed from the Expo/Firebase accounts before store builds work.

## 4. Tomorrow's component
`apps/field-sales-app` (2 of 35).
