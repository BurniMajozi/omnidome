# Module Licensing + Toggle Design

Goal: enable/disable modules per customer in both cloud and on-prem using the same containers and config, with offline-safe enforcement.

## Summary
- Single license artifact per customer controls which modules are enabled.
- API Gateway/BFF enforces module access centrally.
- Each service performs a local entitlement check for defense in depth.
- UI reads entitlements to hide disabled modules.

## License Artifact
Use a signed JSON license (offline-friendly) delivered as a file or env var.

Example JSON (license payload):
{
  "customer_id": "cust-001",
  "issued_at": "2026-02-02T00:00:00Z",
  "expires_at": "2027-02-02T00:00:00Z",
  "plan": "enterprise",
  "modules": ["crm", "sales", "billing", "support", "network"],
  "limits": {
    "seats": 250,
    "tenants": 5
  }
}

Signature:
- Sign the payload with Ed25519.
- Distribute the public key with the software.
- Store signature alongside payload in `license.json` (see `licenses/license.example.json`).

## Where It Lives
Cloud:
- Store license in Secret Manager (and mount into gateway + services).

On-Prem:
- Store as a file mounted into containers (e.g. /etc/coreconnect/license.json).

## Enforcement Points
1) Gateway/BFF (primary)
- Validates license signature + expiry at startup.
- Exposes /entitlements to UI.
- Rejects requests to disabled modules.

2) Service (secondary)
- Each service checks module entitlement on startup.
- Optional runtime check per request.
- If unlicensed, return 403 with module id.

3) UI (tertiary)
- Call /entitlements and hide modules not enabled.

## Env Vars (Standardized)
- LICENSE_PATH=/etc/coreconnect/license.json
- LICENSE_PUBLIC_KEY=... (Ed25519 public key)
- LICENSE_ENFORCEMENT=strict|warn
- MODULE_ID=crm|sales|billing|support|...

## Module Catalog
Maintain a single module registry (code + docs).

Example:
crm: "CRM Connect"
sales: "Sales Connect"
billing: "Billing Connect"
support: "Support Connect"
network: "Network Connect"
iot: "IoT Connect"
retention: "Retention Connect"
call_center: "Call Center Connect"

## Failure Modes
Strict:
- Invalid or expired license -> block all module access.

Warn:
- Log errors, allow access (use only for dev/test).

## Rotation + Revocation
- Include expires_at for scheduled renewals.
- Support key rotation by allowing multiple public keys.
- Cloud can optionally call a licensing service to refresh.

## Minimal Implementation Plan
1) Add gateway /entitlements endpoint.
2) Add shared license verifier library (Python package).
3) Add per-service MODULE_ID + entitlement check.
4) Add UI module gate (hide + route guard).

## Notes for On-Prem
- Provide a CLI tool to validate license (offline).
- Offer a "license refresh" utility for customers with limited connectivity.
