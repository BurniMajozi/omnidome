import { AUTH_DISABLED } from "@/lib/flags"

/**
 * Dev-tenant fallback for /api route handlers. FAIL CLOSED: only when the explicit local
 * NEXT_PUBLIC_DISABLE_AUTH flag is on. proxy.ts always supplies verified identity for
 * authenticated requests, so a missing identity here means "unauthenticated" -> 401.
 */
export const DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"
export const DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
export const devFallbackAllowed = (): boolean => AUTH_DISABLED
