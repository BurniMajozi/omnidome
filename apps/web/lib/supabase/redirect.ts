const fallbackBase = "http://localhost:3000"

const envBase =
  process.env.NEXT_PUBLIC_SITE_URL ||
  process.env.NEXT_PUBLIC_AUTH_REDIRECT_URL ||
  fallbackBase

export const getAuthRedirectBase = () => {
  if (typeof window !== "undefined") {
    const browserBase = window.location.origin
    return browserBase || envBase
  }
  return envBase
}

export const getAuthRedirectUrl = (path: string) => {
  const base = getAuthRedirectBase().replace(/\/$/, "")
  const normalized = path.startsWith("/") ? path : `/${path}`
  return `${base}${normalized}`
}

/**
 * Validates and sanitizes a `?next=` redirect parameter to prevent open redirect vulnerabilities.
 * Strictly allows only safe, relative same-site paths (e.g. `/dashboard`, `/dashboard/sales?tab=1`).
 * Rejects absolute URLs, protocol-relative (`//evil.com`), backslashes (`/\`), CRLF injections,
 * and dangerous protocols (`javascript:`, `data:`).
 */
export function sanitizeNextUrl(
  next: string | null | undefined,
  fallback = "/dashboard",
): string {
  if (!next || typeof next !== "string") {
    return fallback
  }

  const trimmed = next.trim()
  if (!trimmed) {
    return fallback
  }

  // Must begin with a single forward slash and cannot start with '//'
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) {
    return fallback
  }

  // Reject any backslashes, percent-encoded backslashes, CRLF, or control characters
  if (/[\\\r\n\t\0]/.test(trimmed) || /%5[cC]/i.test(trimmed)) {
    return fallback
  }

  try {
    const dummyOrigin = "http://localhost"
    const parsed = new URL(trimmed, dummyOrigin)

    // The origin must match the dummy origin (guarantees no domain spoofing)
    if (parsed.origin !== dummyOrigin) {
      return fallback
    }

    // Pathname must start with '/' and not contain '//' or backslashes
    if (
      !parsed.pathname.startsWith("/") ||
      parsed.pathname.startsWith("//") ||
      parsed.pathname.includes("\\")
    ) {
      return fallback
    }

    // Must be standard http scheme on the dummy origin
    if (parsed.protocol !== "http:") {
      return fallback
    }

    return `${parsed.pathname}${parsed.search}${parsed.hash}`
  } catch {
    return fallback
  }
}

