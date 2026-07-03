# Building the OmniDome Android APKs (Android Studio / laptop)

Three Expo apps live under `apps/`:

| App | Package | Native stack |
| --- | --- | --- |
| `apps/customer-app` | `com.omnidome.customer` | Expo shell around the Next.js customer portal |
| `apps/technician-app` | `com.omnidome.technician` | Expo Router native screens |
| `apps/field-sales-app` | `com.omnidome.fieldsales` | Expo Router native screens |

All three now ship with generated galactic-dome icons/splash in `assets/`,
an optional `google-services.json` (builds work without FCM), and the
galactic dome background rendered globally (2026-07-03).

## Prerequisites (on the laptop)

- Node.js 20+, npm 10+
- JDK 17 (Android Studio bundles one)
- Android Studio with SDK Platform 34+ and NDK installed
- `ANDROID_HOME` set (Android Studio usually handles this)

## Build steps (per app)

```bash
cd apps/technician-app        # or field-sales-app / customer-app
npm install

# Generate the android/ native project from app.config.ts
npx expo prebuild --platform android --clean

# Option A — Android Studio (what you asked for):
#   Open the generated apps/<app>/android folder in Android Studio,
#   let Gradle sync, then Build > Build App Bundles / APKs > Build APK(s).

# Option B — command line:
cd android && ./gradlew assembleDebug
# APK lands in android/app/build/outputs/apk/debug/app-debug.apk
```

Install on a phone with `adb install app-debug.apk` or by copying the file.

## Pointing the apps at the backend

The apps call the backend via `NEXT_PUBLIC_API_URL` / the API client in
`lib/api/client.ts`. For a phone on your Wi-Fi, set it to your dev machine's
LAN address (e.g. `http://192.168.x.x:3000`) in each app's `.env` before
building, or the app will try `localhost` (which is the phone itself).

## Known state / honest caveats (as of 2026-07-03)

These apps are scaffolding that had **never been built** before this pass.
Fixed statically in this pass:

- Missing `assets/` (icon, splash, adaptive-icon, favicon) — generated.
- `googleServicesFile` referenced a file that doesn't exist — now optional.
- Expo Router layouts were named `layout.tsx` — renamed to `_layout.tsx`
  (Expo Router requirement) in technician + field-sales apps.
- customer-app had no root layout / tsconfig paths that matched its
  folder layout / no global CSS — added.

Still expected to need attention on first real build:

- **Styling on native**: technician/field-sales screens use Tailwind
  `className` strings. On native these need NativeWind (not installed) —
  screens will render unstyled but functional until that pass is done.
- **Icons on native**: screens import `lucide-react` (web). Native builds
  want `lucide-react-native`. Metro may tree-shake or fail here — if the
  build errors on lucide, swap the import per screen.
- **customer-app native shell** (`expo/index.tsx`) wraps the Next.js PWA;
  it needs the portal deployed (or reachable dev server) to show content.

If Gradle fails on the first run, do `npx expo prebuild --clean` again after
fixing config — stale `android/` folders cause confusing errors.
