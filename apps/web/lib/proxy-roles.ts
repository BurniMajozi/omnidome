/**
 * Least-privilege role/permission headers for server-side proxy routes.
 *
 * proxy.ts strips every client-supplied x-roles / x-permissions and re-injects
 * x-roles ONLY from the verified Supabase user's app_metadata.roles (writable
 * with the service role only). So at route-handler level, `x-roles` is either
 * trustworthy or absent. Handlers must never invent an admin role for callers:
 * with no verified role the caller gets the minimal role and read-only
 * permissions.
 */
export const MINIMAL_ROLE = "org_user"

const ROLE_RE = /^[\w.:-]+$/

/** Roles from the verified x-roles header, or [MINIMAL_ROLE] when none. */
export function verifiedRoles(headers: Headers): string[] {
  const roles = (headers.get("x-roles") || "")
    .split(",")
    .map((r) => r.trim())
    .filter((r) => r && ROLE_RE.test(r))
  return roles.length ? roles : [MINIMAL_ROLE]
}

/**
 * Roles + permissions to forward to a backend.
 * @param fullPermissions the permission set an admin of this module holds.
 * org_admin and owner get everything except `platform.*`; platform_admin gets all;
 * anyone else only the `*.read` permissions.
 */
export function verifiedRoleHeaders(
  headers: Headers,
  fullPermissions: string[],
): { roles: string; permissions: string } {
  const roles = verifiedRoles(headers)
  const isPlatform = roles.includes("platform_admin")
  const isAdmin = isPlatform || roles.includes("org_admin") || roles.includes("owner")
  const permissions = fullPermissions.filter((p) =>
    isAdmin ? (p.startsWith("platform.") ? isPlatform : true) : p.endsWith(".read"),
  )
  return { roles: roles.join(","), permissions: permissions.join(",") }
}
