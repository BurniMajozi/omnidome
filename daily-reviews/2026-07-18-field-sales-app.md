# Daily Review — apps/field-sales-app (2026-07-18, manual run)

## 1. Today's plan
Component **2 of 35** in the rotation (manual "run now" — second review today). `apps/field-sales-app`: Expo/Next hybrid for field sales agents (leads, deals, quotes, commissions, customer 360, property IoT survey).

## 2. What was found / achieved

### Bugs
- **customers.tsx ~line 60: `onChange={e}` in `UIInput`** — `e` is not defined in scope; should be `onChange={onChange}`. This breaks typing into the customer search input (compile/runtime error). One-line fix.

### Gaps / incomplete flows
- **No token refresh.** `lib/api/client.ts` login returns only `accessToken`; `auth-store.ts` has a `refreshToken` field but login stores `null` (`setTokens(res.accessToken, null)`) and nothing ever refreshes. Agents get silently logged out / 401 errors mid-shift when the JWT expires.
- **Silent error handling.** `commissions.tsx` (~L37) and similar tabs catch errors with `console.error` only — no user-facing error state, just an empty list.
- **`getCustomer360` is not a 360.** It calls the same `/crm/customers/{id}` endpoint as `getContact` — no aggregation of billing/support/network data yet.

### Hardcoded config
- **`lib/api/client.ts` line 19:** base URL falls back to `http://localhost:8000` — no production guard if `NEXT_PUBLIC_API_URL` is missing at build time.
- All "placeholder" search hits were legitimate HTML input attributes — **no mock data arrays found** in this app.

### Solid parts (notably better than customer-app)
- **app.config.ts is done right:** EAS project ID comes from `EAS_PROJECT_ID` env (fails loudly if unset) instead of a placeholder string. Consider back-porting this pattern to customer-app.
- Single consistent auth path (Zustand + secure store), clean typed API client, no fake data fallbacks.

## 3. Critical decisions / flags
1. **Session length policy:** without refresh tokens, how long should agent JWTs live? Either the backend issues long-lived agent tokens, or `/auth/agent/refresh` needs to exist and the client needs a refresh flow. Field agents work 8+ hour shifts — decide before pilot.
2. **Customer 360 scope:** is the aggregated 360 (billing + support + network per customer) a backend endpoint still to be built, or should the app compose it from existing endpoints? The method name currently over-promises.

## 4. Tomorrow's component
`apps/portal` (3 of 35).
