"""Lead Gen forms and leads (Meta Lead Ads, LinkedIn Lead Gen) synced from Zernio into OmniDome.

Provider support (verified against zernio.com/openapi.json, Oct 2026):
  * GET  /v1/ads/lead-forms                 list forms (Meta: forms on the connected Page; LinkedIn: org forms)
  * POST /v1/ads/lead-forms                 create a form (NOT idempotent)
  * GET  /v1/ads/lead-forms/{id}/leads      leads of one form
  * GET  /v1/ads/leads                      submitted leads, newest first, keyset `cursor`
                                            (Meta: persisted from the `leadgen` webhook; LinkedIn: live, 90-day retention)
  * Webhook event `lead.received`           real-time Meta lead (payload: lead{id, leadgenId, formId, formName,
                                            adId, adsetId, campaignId, fields, isOrganic, createdAt}, account{accountId, profileId})
Not provided by the API: lead forms for Google/TikTok/Pinterest/X ads, and no webhook for LinkedIn leads
(LinkedIn is pulled by sync only).

Leads land in `marketing_ad_leads` (tenant scoped, PK (tenant_id, lead_id) => replays and webhook+sync overlap
are idempotent). Forms land in `marketing_lead_forms`. Nothing here creates CRM contacts automatically:
`contact_id` is reserved for that link so the CRM team can attach it without a schema change.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from services.common.auth import get_current_tenant_id
from services.common.db import get_engine
from services.marketing.security import require_marketing_write
from services.marketing.zernio_errors import not_configured, provider_error

logger = logging.getLogger("marketing.leads")
router = APIRouter()

LEAD_ACCOUNT_PLATFORMS = ("facebook", "metaads", "linkedinads")
MAX_SYNC_PAGES = 20


def _mk():
    from services.marketing import main as mk
    return mk


def _client():
    c = _mk().get_zernio_client()
    if c is None:
        raise not_configured()
    return c


def _parse_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        s = str(v).replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def normalize_lead(raw: Dict[str, Any], account_id: Optional[str] = None, platform: str = "facebook") -> Optional[Dict[str, Any]]:
    """Provider lead (list shape or webhook `lead` object) -> marketing_ad_leads row (sans tenant)."""
    lead_id = str(raw.get("id") or raw.get("_id") or raw.get("leadgenId") or "")
    if not lead_id:
        return None
    fields = raw.get("fields")
    if not isinstance(fields, dict):
        fields = {}
    if not fields and isinstance(raw.get("fieldData"), list):  # Meta raw shape [{name, values:[...]}]
        for fd in raw["fieldData"]:
            if isinstance(fd, dict) and fd.get("name"):
                vals = fd.get("values")
                fields[str(fd["name"])] = vals[0] if isinstance(vals, list) and len(vals) == 1 else vals
    return {
        "lead_id": lead_id,
        "leadgen_id": str(raw.get("leadgenId") or "") or None,
        "form_id": str(raw.get("formId") or "") or None,
        "form_name": raw.get("formName"),
        "account_id": str(raw.get("accountId") or account_id or "") or None,
        "platform": platform,
        "ad_id": raw.get("adId"),
        "adset_id": raw.get("adsetId"),
        "campaign_id": raw.get("campaignId"),
        "is_organic": bool(raw.get("isOrganic", False)),
        "fields": fields,
        "created_time": _parse_dt(raw.get("createdTime") or raw.get("createdAt")),
    }


def upsert_leads(tenant_id: str, rows: List[Dict[str, Any]], source: str) -> int:
    """Insert new leads; existing (tenant_id, lead_id) rows are left untouched. Returns inserted count."""
    if not rows:
        return 0
    inserted = 0
    with get_engine().begin() as conn:
        for r in rows:
            res = conn.execute(text("""
                INSERT INTO marketing_ad_leads
                  (tenant_id, lead_id, leadgen_id, form_id, form_name, account_id, platform, ad_id, adset_id,
                   campaign_id, is_organic, fields, created_time, source)
                VALUES (:tid, :lead_id, :leadgen_id, :form_id, :form_name, :account_id, :platform, :ad_id, :adset_id,
                        :campaign_id, :is_organic, CAST(:fields AS jsonb), :created_time, :source)
                ON CONFLICT (tenant_id, lead_id) DO NOTHING
            """), {**r, "fields": json.dumps(r["fields"], default=str), "tid": tenant_id, "source": source})
            inserted += res.rowcount or 0
    return inserted


def ingest_lead_event(tenant_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """`lead.received` webhook -> DB (called from the verified, tenant-routed webhook path)."""
    acct = payload.get("account") or {}
    account_id = str(acct.get("accountId") or acct.get("id") or "") or None
    row = normalize_lead(payload.get("lead") or {}, account_id, str(acct.get("platform") or "facebook"))
    if not row:
        return {"stored": 0, "reason": "no lead id"}
    return {"stored": upsert_leads(tenant_id, [row], "webhook"), "lead_id": row["lead_id"]}


def _tenant_lead_accounts(tenant_id: uuid.UUID) -> List[Dict[str, Any]]:
    with get_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT account_id, platform FROM marketing_connected_accounts
             WHERE tenant_id = :tid AND status <> 'disconnected' AND platform = ANY(:plats)
        """), {"tid": str(tenant_id), "plats": list(LEAD_ACCOUNT_PLATFORMS)}).mappings().all()
    return [dict(r) for r in rows]


def _owned_account(tenant_id: uuid.UUID, account_id: str) -> Dict[str, Any]:
    with get_engine().connect() as conn:
        r = conn.execute(text("""
            SELECT account_id, platform FROM marketing_connected_accounts
             WHERE tenant_id = :tid AND account_id = :aid AND status <> 'disconnected'
        """), {"tid": str(tenant_id), "aid": account_id}).mappings().first()
    if not r:
        raise HTTPException(status_code=403, detail="Account does not belong to this workspace")
    return dict(r)


def _upsert_forms(tenant_id: str, account_id: str, platform: str, forms: List[Dict[str, Any]]) -> int:
    n = 0
    with get_engine().begin() as conn:
        for f in forms:
            fid = str(f.get("id") or f.get("_id") or "")
            if not fid:
                continue
            raw_json = json.dumps(f, default=str)
            conn.execute(text("""
                INSERT INTO marketing_lead_forms (tenant_id, form_id, account_id, platform, name, status, questions, raw, synced_at)
                VALUES (:tid, :fid, :aid, :plat, :name, :status, CAST(:q AS jsonb), CAST(:raw AS jsonb), now())
                ON CONFLICT (tenant_id, form_id) DO UPDATE SET
                    account_id = EXCLUDED.account_id, platform = EXCLUDED.platform, name = EXCLUDED.name,
                    status = EXCLUDED.status, questions = EXCLUDED.questions, raw = EXCLUDED.raw, synced_at = now()
            """), {
                "tid": tenant_id, "fid": fid, "aid": account_id, "plat": platform, "name": f.get("name"),
                "status": f.get("status"), "q": json.dumps(f.get("questions") or []),
                "raw": raw_json if len(raw_json) <= 20000 else "{}",
            })
            n += 1
    return n


async def sync_forms(tenant_id: uuid.UUID, account_id: Optional[str] = None, ad_account_id: Optional[str] = None) -> Dict[str, Any]:
    client = _client()
    accounts = [_owned_account(tenant_id, account_id)] if account_id else _tenant_lead_accounts(tenant_id)
    total, errors = 0, []
    for a in accounts:
        cursor, pages = None, 0
        while pages < MAX_SYNC_PAGES:
            try:
                res = await client.lead_forms_list(a["account_id"], ad_account_id=ad_account_id, cursor=cursor, limit=100)
            except Exception as exc:  # noqa: BLE001
                err = provider_error("lead forms list", exc)
                errors.append({"account_id": a["account_id"], "error": err.detail})
                break
            total += _upsert_forms(str(tenant_id), a["account_id"], a["platform"], [f for f in res.get("forms") or [] if isinstance(f, dict)])
            pg = res.get("pagination") or {}
            cursor, pages = pg.get("cursor"), pages + 1
            if not pg.get("hasMore") or not cursor:
                break
    return {"forms_synced": total, "accounts": len(accounts), "errors": errors}


async def sync_leads(tenant_id: uuid.UUID, account_id: Optional[str] = None, form_id: Optional[str] = None,
                     ad_account_id: Optional[str] = None) -> Dict[str, Any]:
    """Pull leads for the tenant's lead-capable accounts into the DB (idempotent)."""
    client = _client()
    accounts = [_owned_account(tenant_id, account_id)] if account_id else _tenant_lead_accounts(tenant_id)
    inserted, seen, errors = 0, 0, []
    for a in accounts:
        if a["platform"] == "linkedinads" and not ad_account_id:
            errors.append({"account_id": a["account_id"], "error": "LinkedIn lead sync needs ad_account_id"})
            continue
        cursor, pages = None, 0
        while pages < MAX_SYNC_PAGES:
            try:
                res = await client.leads_list(account_id=a["account_id"], form_id=form_id, ad_account_id=ad_account_id,
                                              limit=100, cursor=cursor)
            except Exception as exc:  # noqa: BLE001
                err = provider_error("leads list", exc)
                errors.append({"account_id": a["account_id"], "error": err.detail})
                break
            rows = [r for r in (normalize_lead(x, a["account_id"], "linkedin" if a["platform"] == "linkedinads" else "facebook")
                                for x in res.get("leads") or [] if isinstance(x, dict)) if r]
            seen += len(rows)
            inserted += upsert_leads(str(tenant_id), rows, "sync")
            pg = res.get("pagination") or {}
            cursor, pages = pg.get("cursor"), pages + 1
            if not pg.get("hasMore") or not cursor:
                break
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO marketing_lead_sync_state (tenant_id, last_synced_at, last_error, last_count)
            VALUES (:tid, now(), :err, :cnt)
            ON CONFLICT (tenant_id) DO UPDATE SET last_synced_at = now(), last_error = EXCLUDED.last_error,
                                                 last_count = EXCLUDED.last_count
        """), {"tid": str(tenant_id), "err": json.dumps(errors)[:1000] if errors else None, "cnt": inserted})
    return {"leads_seen": seen, "leads_inserted": inserted, "accounts": len(accounts), "errors": errors}


# ───────────────────────── routes ─────────────────────────


@router.get("/ads/lead-forms")
async def list_lead_forms(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Lead forms synced for this workspace, with how many leads each has collected."""
    with get_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT f.form_id, f.account_id, f.platform, f.name, f.status, f.questions, f.synced_at,
                   COALESCE(l.cnt, 0) AS lead_count, l.last_lead_at
              FROM marketing_lead_forms f
              LEFT JOIN (SELECT form_id, count(*) AS cnt, max(created_time) AS last_lead_at
                           FROM marketing_ad_leads WHERE tenant_id = :tid GROUP BY form_id) l ON l.form_id = f.form_id
             WHERE f.tenant_id = :tid
             ORDER BY f.name NULLS LAST
        """), {"tid": str(tenant_id)}).mappings().all()
        st = conn.execute(text("SELECT last_synced_at, last_error, last_count FROM marketing_lead_sync_state WHERE tenant_id = :tid"),
                          {"tid": str(tenant_id)}).mappings().first()
    return {"forms": [dict(r) for r in rows], "sync": dict(st) if st else None,
            "supported_platforms": ["facebook", "instagram (via Meta)", "linkedin"]}


class LeadSyncIn(BaseModel):
    account_id: Optional[str] = Field(None, description="Limit to one connected account")
    ad_account_id: Optional[str] = Field(None, description="Required for LinkedIn")
    form_id: Optional[str] = None


@router.post("/ads/lead-forms/sync", dependencies=[Depends(require_marketing_write)])
async def sync_lead_forms(body: LeadSyncIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return await sync_forms(tenant_id, body.account_id, body.ad_account_id)


class LeadFormCreateIn(BaseModel):
    account_id: str
    name: str = Field(..., min_length=1, max_length=200)
    privacy_policy_url: str = Field(..., pattern=r"^https://")
    questions: List[Dict[str, Any]] = Field(..., min_length=1, max_length=20,
                                            description="[{type: EMAIL|PHONE|FULL_NAME|FIRST_NAME|LAST_NAME|CUSTOM, key?, label?, options?}]")
    platform_specific_data: Optional[Dict[str, Any]] = None


@router.post("/ads/lead-forms", status_code=201, dependencies=[Depends(require_marketing_write)])
async def create_lead_form(body: LeadFormCreateIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Create a Meta/LinkedIn Lead Gen form on the tenant's connected account. NOT idempotent at the
    provider, so a retry creates a second form; the UI should disable the button while in flight."""
    acct = _owned_account(tenant_id, body.account_id)
    payload: Dict[str, Any] = {"accountId": body.account_id, "name": body.name, "privacyPolicyUrl": body.privacy_policy_url}
    if body.platform_specific_data:
        payload["platformSpecificData"] = {**body.platform_specific_data, "questions": body.platform_specific_data.get("questions", body.questions)}
    else:
        payload["questions"] = body.questions
    try:
        res = await _client().lead_forms_create(payload)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("lead form create", exc)
    form = (res or {}).get("form") or {}
    if not form.get("id"):
        raise HTTPException(status_code=502, detail={"error": "provider_no_form", "message": "The provider did not return a form id."})
    _upsert_forms(str(tenant_id), body.account_id, acct["platform"], [{"id": form["id"], "name": form.get("name") or body.name,
                                                                     "status": "ACTIVE", "questions": body.questions}])
    return {"form_id": form["id"], "name": form.get("name") or body.name, "account_id": body.account_id}


@router.get("/ads/leads")
async def list_ad_leads(
    form_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Leads stored for this workspace, newest first."""
    where, params = "tenant_id = :tid", {"tid": str(tenant_id), "lim": limit, "off": offset}
    if form_id:
        where += " AND form_id = :fid"
        params["fid"] = form_id
    if campaign_id:
        where += " AND campaign_id = :cid"
        params["cid"] = campaign_id
    with get_engine().connect() as conn:
        total = conn.execute(text(f"SELECT count(*) FROM marketing_ad_leads WHERE {where}"), params).scalar() or 0
        rows = conn.execute(text(f"""
            SELECT lead_id, leadgen_id, form_id, form_name, account_id, platform, ad_id, adset_id, campaign_id,
                   is_organic, fields, created_time, source, contact_id
              FROM marketing_ad_leads WHERE {where}
             ORDER BY created_time DESC NULLS LAST, ingested_at DESC LIMIT :lim OFFSET :off
        """), params).mappings().all()
    return {"leads": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/ads/leads/sync", dependencies=[Depends(require_marketing_write)])
async def sync_ad_leads(body: LeadSyncIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Pull leads from the provider now (the `lead.received` webhook keeps Meta leads current in real time;
    this backfills and is the only path for LinkedIn)."""
    return await sync_leads(tenant_id, body.account_id, body.form_id, body.ad_account_id)
