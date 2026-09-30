import { NextRequest, NextResponse } from "next/server"

/**
 * Who the edge gate (proxy.ts) resolved this request to. proxy.ts strips every
 * client-supplied identity header and re-injects x-user-id / x-tenant-id / x-roles
 * from the VERIFIED user (admin DB roles, else app_metadata), so these are
 * trustworthy here. The admin UI uses this to decide which tabs/roles to offer;
 * the backend still enforces every action.
 */
export function GET(request: NextRequest) {
  const roles = (request.headers.get("x-roles") || "")
    .split(",")
    .map((r) => r.trim())
    .filter(Boolean)
  return NextResponse.json(
    {
      user_id: request.headers.get("x-user-id") || "",
      tenant_id: request.headers.get("x-tenant-id") || "",
      roles: roles.length ? roles : ["org_user"],
    },
    { headers: { "cache-control": "no-store" } },
  )
}
