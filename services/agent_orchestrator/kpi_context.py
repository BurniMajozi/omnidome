"""Fetch an approved HR KPI sheet for a hired agent without inventing targets."""

from __future__ import annotations

import json
import os
import uuid

import httpx


async def approved_kpi_briefing(tenant_id: uuid.UUID, employee_id: uuid.UUID,
                                 actor_id: str | None) -> tuple[str, str]:
    if not actor_id:
        return "", "identity_unavailable"
    url = os.getenv("HR_SERVICE_URL", "http://hr:8009").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                f"{url}/employees/{employee_id}/kpi-sheet",
                headers={"X-Tenant-Id": str(tenant_id), "X-User-Id": actor_id},
            )
        if response.status_code == 403:
            return "", "not_permitted"
        response.raise_for_status()
        sheet = response.json()
    except (httpx.HTTPError, ValueError):
        return "", "unavailable"
    if sheet.get("is_template") or not sheet.get("kpis"):
        return "", "not_configured"
    if sheet.get("status") != "APPROVED":
        return "", "not_approved"
    items = [item for item in sheet["kpis"] if isinstance(item, dict)][:10]
    excerpt = json.dumps(items, ensure_ascii=False, default=str)[:3000]
    return (f"Approved HR KPI sheet for this agent (fiscal year {sheet.get('fiscal_year') or 'unspecified'}). "
            f"Use as targets, not live actuals: {excerpt}", "approved")
