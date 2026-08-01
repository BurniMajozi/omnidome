# Daily Production-Readiness Review — technician-app
**Date:** 2026-07-20
**Rotation position:** 4 of 35 (index 3)
**Path:** `omnidome/apps/technician-app`

## 1. Today's plan

Rotation state showed `lastIndex: 2` (portal, 2026-07-19). Today's list was rebuilt
from `apps/` (5) + `services/` (29) + `integrations/` (1) = 35 components.
`todayIndex = 3` → **technician-app**, the Expo/Next hybrid field-technician app
(job queue, job detail, site IoT, stats, profile, AI assistant).

Read-only inspection of 20 source files. No project files were modified.

## 2. What was found

### A. Build-breaking / runtime-breaking

- **`stats.tsx:4` — `CheckCircleStar` is not a lucide-react export.** The import
  `import { ..., CheckCircleStar, ... } from "lucide-react"` resolves to
  `undefined` and React will throw on render (`Element type is invalid`). The
  entire Stats tab is dead. Likely intended `CheckCircle` or `Star`.
- **`app.config.ts:76` — `sounds: ['./assets/notification-sound.wav']`** but
  `assets/` contains only the 5 image files. `expo-notifications` config plugin
  will fail the prebuild/EAS build on a missing asset.
- **`index.tsx:30` — priority key typo `URGRENT`.** `TechJob.priority` is typed
  `"URGENT"` (types.ts:20), so urgent jobs silently fall through to the NORMAL
  blue badge. The same map in `job/[id].tsx:26` spells it correctly — so the two
  screens disagree about the highest-severity state in the app.

### B. Architectural flag — the app cannot build as a native app

Every screen is written against the DOM, not React Native: `<div>`, `onClick`,
`e.target.value`, `<input>`/`<textarea>`, `alert()` (`job/[id].tsx:203`),
`EventSource` (`client.ts:129`), and `lucide-react` (web) rather than
`lucide-react-native`. Meanwhile `app/_layout.tsx` uses `react-native` `View`,
and the repo carries a full Expo/EAS pipeline (`eas.json`, `scripts/build.sh`,
`expo:build:*` scripts, native permissions, `expo-secure-store`).

As written this is a **PWA wearing an Expo costume**. `eas build` will produce an
artifact that crashes on first render. Dependency set confirms the split:
`next 16.0.10` + `react 19.2.0` alongside `expo ~52` + `react-native 0.76.0`
(which expects React 18.3).

### C. Auth and session

- **Insecure token storage on native.** `auth-store.ts:29-32` only reaches for
  `expo-secure-store` when `typeof window === 'undefined'`. In a React Native
  runtime `window` *is* defined, so it falls through to Zustand's default
  localStorage. The condition is inverted relative to its own comment.
- **No refresh-token flow.** `refreshToken` exists in state, but `login.tsx:34`
  always calls `setTokens(res.accessToken, null)` and `fetchJSON` has no 401
  handling. Sessions expire into an opaque `API error 401` in the console.
- **Redirect loop risk / cold-start bounce.** `app/_layout.tsx:14` redirects to
  `/login` whenever unauthenticated, and `login.tsx` sits under that same root
  layout. There's also no rehydration gate — `zustand/persist` restores async, so
  on every cold start `isAuthenticated` is briefly false and the user is kicked
  to login.
- **Logout** (`profile.tsx:12`) clears local state only — no server-side token
  revoke.

### D. Incomplete flows / dead API surface

- `technicianApi.acceptJob` (`client.ts:69`) — **never called**. There is no
  accept-job step anywhere in the UI; job detail goes straight OPEN → start.
- `technicianApi.checkParts` / `checkoutParts` (`client.ts:104-113`) — **never
  called**. Parts entered in `job/[id].tsx` are free-text SKUs with no validation
  and are only attached to the completion payload; **inventory stock is never
  decremented**.
- `technicianApi.getRadiusAccount` (`client.ts:100`) — **never called**. No
  RADIUS check screen exists.
- **Photos and customer signature are never captured.** `JobCompletionData`
  declares `photos?: string[]` and `customer_signature?` (types.ts:71-72),
  camera permission is requested in both configs, `expo-file-system` is a
  dependency — but no capture UI exists and `handleComplete` never sends either.
- **Push notifications are decorative.** `expo-notifications` is installed and
  permissioned, but there is no token registration or handler anywhere. The
  Profile toggle (`profile.tsx:10`) is local `useState` that writes nothing.

### E. Site IoT screen (`site-iot.tsx`) — largely presentational

- **Camera Snapshots (lines ~213-260) is a static placeholder** — a gradient box
  with the words "Live View" and an animated fake red **"REC"** dot. There is no
  snapshot or stream call; `IoTDevice.snapshot` is declared (line 26) and never
  populated. This looks live to a technician and is not.
- **`room: "Site"` is hardcoded** (line 74) for every device, so "Devices by
  Room" is permanently one bucket. `TechDevice` carries no room/location field.
- **`avgBattery` is always `NaN`** (lines 168-171): `TechDevice` has no battery
  field, so the filter yields an empty array and the code divides by zero. Same
  divide-by-zero pattern for `avgSignal` when no device reports RX power. The UI
  renders "NaN%".
- **Installation checklist is hardcoded local state** (`INITIAL_CHECKLIST`,
  lines 96-107). Progress is never persisted or sent anywhere — it resets on tab
  switch and is invisible to the back office.
- **Wrong-site risk:** the screen picks its customer via `jobs[0]?.customer_id`
  from the OPEN queue (line 505) — an arbitrary first job, not the job the
  technician is standing at.

### F. Error handling

- `handleSpeedTest` (`job/[id].tsx:171-180`) swallows the error and **fabricates
  an all-zero `SpeedTestResult`**. The UI then hides it via `download_mbps > 0`,
  so a failed test is indistinguishable from no test — and a zeroed result can
  be attached to job completion.
- Empty catch: `.catch(() => {})` on device load, `job/[id].tsx:159`.
- No try/catch and no user feedback on `handleStart` (which optimistically flips
  status to IN_PROGRESS regardless of the API result), `handleEscalate`, or
  `rebootDevice` (`job/[id].tsx:91`). A failed reboot looks identical to a
  successful one.
- Load failures on the job queue and stats screens only `console.error` — the
  user sees an empty queue or all-zero stats with no error state.
- **No offline queue.** For a field app this is the biggest functional gap: PWA
  runtime caching only covers `GET /api/` (NetworkFirst); completion POSTs in low
  signal are simply lost.

### G. Hardcoded / environment config

- `client.ts:9-12` and `next.config.js:65` fall back to **`http://localhost:8000`**
  — this ships as the default if the env var is unset.
- **SSE stream uses a relative URL** (`client.ts:129`,
  `/api/support/technicians/me/stream`) while every other call uses the `${API}`
  base — broken on native and on any split-origin deploy. `EventSource` also
  can't attach the `Authorization` header, so the dispatch stream is
  unauthenticated.
- `config/brand.json:26` — placeholder support line `0800-000-000`.
- `eas.json:65-67` — `ascApiKeyIssuerId` and `ascApiKeyId` are empty strings;
  `google-play-service-account.json` and `AppStoreConnect-API-Key.p8` are not in
  the tree. Submit is not runnable.
- **Two divergent Expo configs.** `app.json` and `app.config.ts` both exist;
  Expo prefers the `.ts`, so `app.json` is dead but disagrees — it declares
  `ACCESS_BACKGROUND_LOCATION` and `FOREGROUND_SERVICE`, the `.ts` declares
  storage permissions instead. Whichever a reader trusts, one of them is wrong.
- **Version drift:** `package.json` 0.1.0, both Expo configs 1.0.0, UI hardcodes
  the string `"v0.1.0"` in `index.tsx:207` and `profile.tsx:93`.
- `lib/api/orchestrator.ts:16` re-exports from
  `../../../customer-app/lib/api/orchestrator` — a cross-app relative import
  outside this app's root. Breaks Next standalone output and any Docker build
  context scoped to `apps/technician-app`.
- `brand.json` is imported in `login.tsx` and cast `as any`, but `index.tsx:15`
  and `job/[id].tsx:14` each redeclare their own inline `brandConfig` object
  instead — and neither is actually used for styling (colors are Tailwind
  literals). Three sources of brand truth, zero of them wired.

## 3. Critical decisions / flags for a human

1. **Web PWA or native app? This blocks everything else.** The screens are DOM
   code; the build pipeline is Expo/EAS. Either drop Expo/EAS and ship a PWA, or
   port all five screens to React Native primitives. Every native item below is
   moot until this is settled.
2. **Are photos and customer signature in scope for v1?** The backend contract
   (`JobCompletionData`) expects them and the permissions are requested, but no
   capture exists. Decide: build the capture UI, or drop the fields from the
   contract so completion isn't silently under-reporting.
3. **Should parts consumption decrement inventory?** `checkoutParts` exists and
   is unused. Right now parts are advisory free-text. If stock must move, the
   SKU field needs validation against `checkParts` and completion needs to call
   checkout.
4. **Installation checklist needs a backend owner.** There is no endpoint for it.
   Decide whether it persists per-job (needs an API) or stays a local scratchpad
   (then label it as such in the UI).
5. **Camera "Live View" panel — build or remove.** It currently shows a fake REC
   indicator. Showing a technician a simulated live feed is worse than showing
   nothing. Needs either an IoT snapshot/stream endpoint or deletion.
6. **Missing credentials/assets before any build can run:** `EAS_PROJECT_ID`,
   `assets/notification-sound.wav`, `google-services.json`,
   `google-play-service-account.json`, `AppStoreConnect-API-Key.p8`, and the
   two empty `asc*` values in `eas.json`.
7. **Auth-refresh design.** No refresh flow exists. Decide token lifetime and
   whether the app does silent refresh or forces re-login — field techs on long
   shifts will hit this daily.
8. **Which Expo config is canonical**, `app.json` or `app.config.ts`? Delete the
   other. The permission lists genuinely differ.
9. **Offline behaviour.** Field work implies dead zones. Decide whether job
   completion needs a durable local queue before this is usable in production.

## 4. Tomorrow's component

**`web`** — index 4 of 35 (the last entry under `apps/`, before the rotation
moves into `services/`).
