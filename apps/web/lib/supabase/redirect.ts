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
