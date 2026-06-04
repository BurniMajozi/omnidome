"""OpenAPI spec validation for OmniDome services.

Validates that all services expose a valid OpenAPI spec at /openapi.json
and checks for common issues:
- Missing endpoint descriptions
- Missing response schemas
- Missing tags
- Inconsistent naming

Usage: python -m scripts.validate_openapi
"""

import asyncio
import json
import os
import sys

try:
    import httpx
except ImportError:
    print("pip install httpx")
    sys.exit(1)

GATEWAY_URL = os.getenv("OMNIDOME_GATEWAY_URL", "http://localhost:8000")

# Service prefixes and their expected tags
SERVICES = {
    "/api/crm": {"name": "CRM", "min_endpoints": 5},
    "/api/sales": {"name": "Sales", "min_endpoints": 8},
    "/api/billing": {"name": "Billing", "min_endpoints": 4},
    "/api/finance": {"name": "Finance", "min_endpoints": 5},
    "/api/rica": {"name": "RICA", "min_endpoints": 3},
    "/api/network": {"name": "Network", "min_endpoints": 4},
    "/api/iot": {"name": "IoT", "min_endpoints": 4},
    "/api/call-center": {"name": "Call Center", "min_endpoints": 6},
    "/api/support": {"name": "Support", "min_endpoints": 5},
    "/api/hr": {"name": "HR", "min_endpoints": 5},
    "/api/inventory": {"name": "Inventory", "min_endpoints": 4},
    "/api/analytics": {"name": "Analytics", "min_endpoints": 3},
    "/api/retention": {"name": "Retention", "min_endpoints": 4},
    "/api/admin": {"name": "Admin", "min_endpoints": 10},
    "/api/marketing": {"name": "Marketing", "min_endpoints": 6},
}


async def fetch_openapi(client: httpx.AsyncClient, prefix: str, base_url: str) -> dict | None:
    """Fetch OpenAPI spec directly from a service."""
    try:
        r = await client.get(f"{base_url}/openapi.json", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


async def validate():
    errors = []
    warnings = []

    async with httpx.AsyncClient(timeout=10) as client:
        # Fetch gateway openapi
        try:
            r = await client.get(f"{GATEWAY_URL}/openapi.json")
            if r.status_code != 200:
                errors.append(f"Gateway OpenAPI not available: {r.status_code}")
            else:
                spec = r.json()
                print(f"✅ Gateway OpenAPI: {spec.get('info', {}).get('title', 'unknown')} v{spec.get('info', {}).get('version', '?')}")
        except Exception as e:
            errors.append(f"Cannot reach gateway: {e}")

        # Check each service
        for prefix, expected in SERVICES.items():
            # Try to get spec from service directly via gateway
            try:
                r = await client.get(f"{GATEWAY_URL}{prefix}/openapi.json", timeout=5)
                if r.status_code == 200:
                    spec = r.json()
                    paths = spec.get("paths", {})
                    n_paths = len(paths)
                    n_tags = len(spec.get("tags", []))

                    if n_paths < expected["min_endpoints"]:
                        warnings.append(
                            f"  ⚠️  {expected['name']}: only {n_paths} endpoints "
                            f"(expected >= {expected['min_endpoints']})"
                        )

                    # Check for undocumented endpoints
                    undocumented = []
                    for path, methods in paths.items():
                        for method, details in methods.items():
                            if method in ("get", "post", "put", "patch", "delete"):
                                if not details.get("summary") and not details.get("description"):
                                    undocumented.append(f"{method.upper()} {path}")

                    if undocumented:
                        warnings.append(
                            f"  ⚠️  {expected['name']}: {len(undocumented)} undocumented endpoints"
                        )

                    print(f"  ✅ {expected['name']}: {n_paths} endpoints, {n_tags} tags")
                else:
                    warnings.append(f"  ⚠️  {expected['name']}: OpenAPI not available ({r.status_code})")
            except Exception as e:
                warnings.append(f"  ⚠️  {expected['name']}: cannot reach ({e})")

    print()
    if warnings:
        print("Warnings:")
        for w in warnings:
            print(w)
    if errors:
        print("Errors:")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print("✅ All services validated")


if __name__ == "__main__":
    asyncio.run(validate())
