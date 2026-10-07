"""Ads: connected ads accounts, goals, budget, targeting, audiences, media, validation, preview and creation
through the provider (Zernio `/v1/ads/*`). Everything is tenant scoped and honest:

* an ads account / ad account id from the browser is only used after it is proven to belong to the tenant
  (`marketing_connected_accounts` for the connection, the provider's own `/ads/accounts` list for the ad account);
* a provider rejection comes back as HTTP 422 with the provider's message (`provider_rejected`);
  "no ads account connected" is its own 409 `no_ads_account`; success is only reported when the provider
  returned an ad id;
* ads are created PAUSED unless the caller explicitly asks for ACTIVE.

Goals per platform are the documented ones (docs.zernio.com/platforms/*-ads, Oct 2026).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from services.common.auth import AuthContext, get_current_tenant_id
from services.common.db import get_engine
from services.marketing.audience_members import resolve_members
from services.marketing.security import require_marketing_admin, require_marketing_write
from services.marketing.zernio_errors import not_configured, provider_error

logger = logging.getLogger("marketing.ads")
router = APIRouter()

# Zernio account platform -> our short ads platform key
ACCOUNT_PLATFORM_TO_ADS: Dict[str, str] = {
    "metaads": "meta", "googleads": "google", "tiktokads": "tiktok",
    "linkedinads": "linkedin", "pinterestads": "pinterest", "xads": "x",
}
ADS_ACCOUNT_PLATFORMS = tuple(ACCOUNT_PLATFORM_TO_ADS)

GOALS: Dict[str, List[str]] = {
    "meta": ["engagement", "traffic", "awareness", "video_views", "lead_generation", "lead_conversion",
             "conversions", "app_promotion", "catalog_sales", "page_likes", "page_visits"],
    "google": ["engagement", "traffic", "awareness"],  # video_views / conversion goals are rejected (422) at create
    "tiktok": ["engagement", "traffic", "awareness", "video_views", "lead_generation", "conversions", "app_promotion"],
    "linkedin": ["engagement", "traffic", "awareness", "video_views", "lead_generation", "job_applicants"],
    "pinterest": ["engagement", "traffic", "awareness", "video_views"],
    "x": ["engagement", "traffic", "awareness", "video_views", "app_promotion"],
}
GOAL_LABELS = {
    "engagement": "Engagement", "traffic": "Traffic (link clicks)", "awareness": "Awareness / reach",
    "video_views": "Video views", "lead_generation": "Leads (instant form)", "lead_conversion": "Leads (website, pixel)",
    "conversions": "Sales / conversions (pixel)", "app_promotion": "App installs", "catalog_sales": "Catalog sales",
    "page_likes": "Page likes", "page_visits": "Page visits", "job_applicants": "Job applicants",
}
CALL_TO_ACTIONS = [
    "LEARN_MORE", "SHOP_NOW", "SIGN_UP", "BOOK_TRAVEL", "CONTACT_US", "DOWNLOAD", "GET_OFFER", "GET_QUOTE", "SUBSCRIBE",
    "WATCH_MORE", "ADD_TO_CART", "APPLY_NOW", "BOOK_NOW", "BUY_TICKETS", "DONATE", "DONATE_NOW", "GET_DIRECTIONS",
    "GET_SHOWTIMES", "LISTEN_NOW", "ORDER_NOW", "PLAY_GAME", "REQUEST_TIME", "SEE_MENU", "START_ORDER",
    "INSTALL_MOBILE_APP", "USE_APP", "REGISTER", "JOIN", "ATTEND", "REQUEST_DEMO", "VIEW_QUOTE", "APPLY", "SEE_MORE", "BUY_NOW",
]
LINKEDIN_CTAS = {"LEARN_MORE", "SIGN_UP", "DOWNLOAD", "SUBSCRIBE", "REGISTER", "JOIN", "ATTEND", "REQUEST_DEMO",
                 "VIEW_QUOTE", "APPLY", "SEE_MORE", "SHOP_NOW", "BUY_NOW"}
HEADLINE_MAX = {"meta": 255, "google": 30, "pinterest": 100, "linkedin": 400}
BODY_MAX = {"google": 90, "pinterest": 500, "x": 280}
# provider-side dry run (`validateOnly`) exists for Meta (and Google Performance Max) only
PROVIDER_VALIDATE = {"meta"}
# passthrough keys a caller may set in `provider_overrides` (never account/ids/budget/status)
OVERRIDE_WHITELIST = {
    "optimizationGoal", "billingEvent", "buyingType", "bidStrategy", "bidAmount", "roasAverageFloor", "budgetLevel",
    "placements", "campaignType", "keywords", "negativeKeywords", "additionalHeadlines", "additionalDescriptions",
    "tracking", "attributionSpec", "advantageAudience", "dsaBeneficiary", "dsaPayor", "specialAdCategories",
    "specialAdCategoryCountry", "identityType", "identityId", "boardId", "organizationId", "businessName",
    "locationTargetingType", "longHeadline", "images", "creativeFeatures", "multiAdvertiser", "aiDisclosure",
    "campaignName", "adSetName", "adName", "instagramAccountId", "pageId", "languages", "zips", "metros",
    "customLocations", "behaviors", "countryGroups", "incomeTier", "savedTargetingId", "userOs", "userDevice",
}
_ACCT_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_ACCT_TTL = 60.0


def _mk():
    from services.marketing import main as mk
    return mk


def _client():
    c = _mk().get_zernio_client()
    if c is None:
        raise not_configured()
    return c


# ───────────────────────── request models ─────────────────────────


def _blank(v):
    return None if isinstance(v, str) and not v.strip() else v


class Budget(BaseModel):
    amount: float = Field(..., gt=0, description="WHOLE currency units (50 = 50.00), not cents")
    type: str = Field("daily", pattern="^(daily|lifetime)$")
    currency: Optional[str] = Field(None, pattern="^[A-Za-z]{3}$")


class Creative(BaseModel):
    headline: Optional[str] = None
    body: Optional[str] = None
    description: Optional[str] = None
    call_to_action: Optional[str] = None
    link_url: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    video_id: Optional[str] = None
    lead_gen_form_id: Optional[str] = None
    page_id: Optional[str] = None
    instagram_account_id: Optional[str] = None

    @field_validator("*", mode="before")
    @classmethod
    def _b(cls, v):
        return _blank(v)


class Targeting(BaseModel):
    countries: List[str] = Field(default_factory=list, description="ISO 3166-1 alpha-2")
    regions: List[Any] = Field(default_factory=list, description="[{key,name}] from /ads/targeting/search?geo_type=region")
    cities: List[Any] = Field(default_factory=list, description="[{key,name,radius?,distance_unit?}] from search")
    age_min: Optional[int] = Field(None, ge=13, le=65)
    age_max: Optional[int] = Field(None, ge=13, le=65)
    gender: str = Field("all", pattern="^(all|male|female)$")
    interests: List[Dict[str, Any]] = Field(default_factory=list, description="[{id,name}] from /ads/targeting/search?dimension=interest")
    audience_id: Optional[str] = Field(None, description="A custom or lookalike audience id from GET /ads/audiences")
    saved_targeting_id: Optional[str] = None

    @field_validator("age_min", "age_max", "audience_id", "saved_targeting_id", mode="before")
    @classmethod
    def _b(cls, v):
        return _blank(v)


class AdCreateIn(BaseModel):
    account_id: str = Field(..., description="Connected ADS account id (GET /ads/accounts -> connections[].account_id)")
    ad_account_id: str = Field(..., description="Platform ad account id (GET /ads/accounts -> ad_accounts[].ad_account_id)")
    name: str = Field(..., min_length=1, max_length=255)
    goal: str
    budget: Budget
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str = Field("PAUSED", pattern="^(PAUSED|ACTIVE)$", description="Created paused by default")
    creative: Creative = Field(default_factory=Creative)
    targeting: Targeting = Field(default_factory=Targeting)
    promoted_object: Optional[Dict[str, Any]] = Field(None, description="{pixel_id, custom_event_type} for conversions / lead_conversion")
    provider_overrides: Dict[str, Any] = Field(default_factory=dict)
    client_request_id: Optional[str] = Field(None, max_length=120, description="Reuse on retry to avoid duplicate ads")

    @field_validator("start_date", "end_date", "client_request_id", mode="before")
    @classmethod
    def _b(cls, v):
        return _blank(v)

    @field_validator("goal", mode="before")
    @classmethod
    def _goal(cls, v):
        return str(v or "").strip().lower()

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v):
        return str(v or "PAUSED").strip().upper()


# ───────────────────────── pure validation / mapping ─────────────────────────


def _is_url(v: Optional[str]) -> bool:
    return bool(v) and re.match(r"^https?://[^\s/$.?#][^\s]*$", v or "") is not None


def _parse_when(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def validate_ad(ad: AdCreateIn, platform: str, account: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Local, deterministic checks. Returns (errors, warnings), each [{field, code, message}].
    The provider remains the final judge; these catch what we can know without a network call."""
    errs: List[Dict[str, str]] = []
    warns: List[Dict[str, str]] = []

    def e(field, code, msg):
        errs.append({"field": field, "code": code, "message": msg})

    def w(field, code, msg):
        warns.append({"field": field, "code": code, "message": msg})

    c, t, b = ad.creative, ad.targeting, ad.budget
    allowed = GOALS.get(platform, [])
    if ad.goal not in allowed:
        e("goal", "invalid_goal", f"Goal '{ad.goal}' is not available on {platform}. Choose one of: {', '.join(allowed)}")

    # budget
    if b.type == "lifetime" and not ad.end_date:
        e("end_date", "end_date_required", "A lifetime budget needs an end date")
    sd, ed = _parse_when(ad.start_date), _parse_when(ad.end_date)
    if ad.start_date and not sd:
        e("start_date", "invalid_date", "start_date must be an ISO 8601 date/time")
    if ad.end_date and not ed:
        e("end_date", "invalid_date", "end_date must be an ISO 8601 date/time")
    if sd and ed and ed <= sd:
        e("end_date", "end_before_start", "end_date must be after start_date")
    if account:
        minimum = account.get("minimum_daily_budget")
        cur = account.get("currency")
        if b.currency and cur and b.currency.upper() != str(cur).upper():
            e("budget.currency", "currency_mismatch", f"The ad account bills in {cur}, not {b.currency.upper()}")
        if b.type == "daily" and isinstance(minimum, (int, float)) and b.amount < float(minimum):
            e("budget.amount", "below_minimum", f"Daily budget is below this ad account's minimum ({minimum} {cur or ''})".strip())

    # creative (per-platform documented requirements)
    cta = (c.call_to_action or "").upper() or None
    if cta and cta not in CALL_TO_ACTIONS:
        e("creative.call_to_action", "invalid_cta", f"Unknown call to action '{cta}'")
    if c.link_url and not _is_url(c.link_url):
        e("creative.link_url", "invalid_url", "Destination URL must start with http:// or https://")
    elif c.link_url and c.link_url.startswith("http://"):
        w("creative.link_url", "insecure_url", "http:// destinations are often rejected; prefer https://")
    hmax, bmax = HEADLINE_MAX.get(platform), BODY_MAX.get(platform)
    if c.headline and hmax and len(c.headline) > hmax:
        e("creative.headline", "too_long", f"Headline is {len(c.headline)} characters; {platform} allows {hmax}")
    if c.body and bmax and len(c.body) > bmax:
        e("creative.body", "too_long", f"Body is {len(c.body)} characters; {platform} allows {bmax}")
    has_media = bool(c.image_url or c.video_url or c.video_id)
    if c.image_url and c.video_url:
        e("creative.video_url", "image_and_video", "Provide an image or a video, not both")

    if platform == "meta":
        if not c.headline:
            e("creative.headline", "required", "Headline is required")
        if not c.body:
            e("creative.body", "required", "Primary text is required")
        if not cta:
            e("creative.call_to_action", "required", "Call to action is required")
        if ad.goal == "lead_generation":
            if not c.lead_gen_form_id:
                e("creative.lead_gen_form_id", "required", "Pick a lead form for a lead generation ad (create one under Lead forms)")
        elif not c.link_url:
            e("creative.link_url", "required", "Destination URL is required")
        if not has_media:
            e("creative.image_url", "media_required", "Upload an image or a video")
        if ad.goal in ("conversions", "lead_conversion"):
            po = ad.promoted_object or {}
            if not po.get("pixel_id"):
                e("promoted_object.pixel_id", "required", f"A pixel id is required for the '{ad.goal}' goal")
            if not po.get("custom_event_type") and not po.get("custom_conversion_id"):
                e("promoted_object.custom_event_type", "required", "A conversion event (e.g. PURCHASE, LEAD) is required")
    elif platform == "tiktok":
        if not (c.video_url or c.image_url):
            e("creative.video_url", "media_required", "TikTok ads are video only: upload a video")
        if c.image_url and not c.video_url:
            w("creative.image_url", "video_expected", "TikTok expects a video URL; an image URL will be sent as the video")
        if not c.body:
            e("creative.body", "required", "Caption is required")
        if ad.goal in ("traffic", "conversions") and not c.link_url:
            e("creative.link_url", "required", "Destination URL is required for this goal")
        if ad.goal == "conversions" and not (ad.promoted_object or {}).get("pixel_id"):
            e("promoted_object.pixel_id", "required", "A TikTok pixel id is required for conversions")
    elif platform == "linkedin":
        if not c.headline:
            e("creative.headline", "required", "Headline is required")
        if not c.body:
            e("creative.body", "required", "Intro text is required")
        if not has_media:
            e("creative.image_url", "media_required", "Upload an image or a video")
        if ad.goal == "traffic" and not c.link_url:
            e("creative.link_url", "required", "Destination URL is required for traffic ads")
        if ad.goal == "video_views" and not (c.video_url or c.video_id):
            e("creative.video_url", "required", "A video is required for video views")
        if ad.goal == "lead_generation" and not c.lead_gen_form_id:
            e("creative.lead_gen_form_id", "required", "Pick a lead form")
        if cta and cta not in LINKEDIN_CTAS:
            e("creative.call_to_action", "invalid_cta", f"LinkedIn accepts: {', '.join(sorted(LINKEDIN_CTAS))}")
    elif platform == "google":
        if not c.headline:
            e("creative.headline", "required", "Headline is required")
        if not c.body:
            e("creative.body", "required", "Description is required")
        if not c.link_url:
            e("creative.link_url", "required", "Destination URL is required")
        w("creative", "google_assets", "Google Display also needs square + landscape images and a business name (provider_overrides.images / businessName)")
    elif platform == "pinterest":
        for fld, val in (("headline", c.headline), ("body", c.body), ("link_url", c.link_url)):
            if not val:
                e(f"creative.{fld}", "required", f"{fld.replace('_', ' ').capitalize()} is required")
        if not has_media:
            e("creative.image_url", "media_required", "Upload an image")
    elif platform == "x":
        if not c.body:
            e("creative.body", "required", "Tweet text is required")

    # targeting
    if not (t.countries or t.regions or t.cities or t.saved_targeting_id):
        w("targeting.countries", "default_geo", "No location chosen: the provider will target the US by default")
    for cc in t.countries:
        if not re.fullmatch(r"[A-Za-z]{2}", cc or ""):
            e("targeting.countries", "invalid_country", f"'{cc}' is not an ISO 3166-1 alpha-2 country code")
    if t.age_min and t.age_max and t.age_min > t.age_max:
        e("targeting.age_min", "age_range", "age_min cannot be greater than age_max")
    for it in t.interests:
        if not (isinstance(it, dict) and it.get("id") and it.get("name")):
            e("targeting.interests", "invalid_interest", "Each interest needs id and name (use /ads/targeting/search?dimension=interest)")
            break
    for k in ad.provider_overrides:
        if k not in OVERRIDE_WHITELIST:
            e("provider_overrides", "override_not_allowed", f"Override '{k}' is not allowed")
    return errs, warns


def build_provider_body(ad: AdCreateIn, platform: str, currency: Optional[str] = None, validate_only: bool = False) -> Dict[str, Any]:
    """AdCreateIn -> POST /v1/ads/create body (legacy single-creative shape)."""
    c, t, b = ad.creative, ad.targeting, ad.budget
    body: Dict[str, Any] = {
        "accountId": ad.account_id,
        "adAccountId": ad.ad_account_id,
        "name": ad.name,
        "goal": ad.goal,
        "budgetAmount": b.amount,
        "budgetType": b.type,
        "status": ad.status,
    }
    cur = (b.currency or currency)
    if cur and platform == "meta":
        body["currency"] = cur.upper()
    if ad.start_date:
        body["startDate"] = ad.start_date
    if ad.end_date:
        body["endDate"] = ad.end_date
    for src, dst in (("headline", "headline"), ("body", "body"), ("description", "description"),
                     ("link_url", "linkUrl"), ("lead_gen_form_id", "leadGenFormId"), ("page_id", "pageId"),
                     ("instagram_account_id", "instagramAccountId")):
        v = getattr(c, src)
        if v:
            body[dst] = v
    if c.call_to_action:
        body["callToAction"] = c.call_to_action.upper()
    # TikTok's endpoint is video-only and carries the video URL in imageUrl
    if platform == "tiktok":
        url = c.video_url or c.image_url
        if url:
            body["imageUrl"] = url
    else:
        if c.image_url:
            body["imageUrl"] = c.image_url
        if c.video_url:
            body["video"] = {"url": c.video_url}
        elif c.video_id:
            body["video"] = {"id": c.video_id}
    if t.countries:
        body["countries"] = [x.upper() for x in t.countries]
    if t.regions:
        body["regions"] = t.regions
    if t.cities:
        body["cities"] = t.cities
    if t.age_min:
        body["ageMin"] = t.age_min
    if t.age_max:
        body["ageMax"] = t.age_max
    if t.gender and t.gender != "all":
        body["gender"] = t.gender
    if t.interests:
        body["interests"] = [{"id": str(i["id"]), "name": i["name"]} for i in t.interests]
    if t.audience_id:
        body["audienceId"] = t.audience_id
    if t.saved_targeting_id:
        body["savedTargetingId"] = t.saved_targeting_id
    if ad.promoted_object:
        po = ad.promoted_object
        mapped = {"pixelId": po.get("pixel_id"), "customEventType": po.get("custom_event_type"),
                  "customConversionId": po.get("custom_conversion_id"), "customEventStr": po.get("custom_event_str")}
        body["promotedObject"] = {k: v for k, v in mapped.items() if v}
    for k, v in ad.provider_overrides.items():
        if k in OVERRIDE_WHITELIST:
            body[k] = v
    if validate_only:
        body["validateOnly"] = True
    return body


def parse_created_ads(res: Any) -> List[Dict[str, Any]]:
    """201 body is one ad, {ad}, {ads:[...]} or a list of those. Only entries with an id count."""
    items: List[Any] = []
    if isinstance(res, list):
        items = res
    elif isinstance(res, dict):
        if isinstance(res.get("ads"), list):
            items = res["ads"]
        elif isinstance(res.get("ad"), dict):
            items = [res["ad"]]
        else:
            items = [res]
    out = []
    for it in items:
        ad = it.get("ad") if isinstance(it, dict) and isinstance(it.get("ad"), dict) else it
        if isinstance(ad, dict) and (ad.get("_id") or ad.get("id")):
            out.append(ad)
    return out


def normalize_ad(ad: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ad_id": ad.get("_id") or ad.get("id"),
        "name": ad.get("name"),
        "platform": ad.get("platform"),
        "status": ad.get("status"),
        "configured_status": ad.get("configuredStatus"),
        "review_status": ad.get("reviewStatus"),
        "goal": ad.get("goal"),
        "budget": ad.get("budget"),
        "platform_campaign_id": ad.get("platformCampaignId"),
        "platform_ad_set_id": ad.get("platformAdSetId"),
        "platform_ad_id": ad.get("platformAdId"),
        "campaign_id": ad.get("campaignId"),
        "ad_set_id": ad.get("adSetId"),
    }


# ───────────────────────── tenant ownership ─────────────────────────


def tenant_ads_connections(tenant_id: uuid.UUID) -> List[Dict[str, Any]]:
    with get_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT account_id, platform, username, status FROM marketing_connected_accounts
             WHERE tenant_id = :tid AND status <> 'disconnected' AND platform = ANY(:plats)
             ORDER BY connected_at DESC
        """), {"tid": str(tenant_id), "plats": list(ADS_ACCOUNT_PLATFORMS)}).mappings().all()
    return [dict(r) for r in rows]


def _no_ads_account() -> HTTPException:
    return HTTPException(status_code=409, detail={
        "error": "no_ads_account",
        "message": "No ads account is connected. Connect Meta, Google, TikTok, LinkedIn, Pinterest or X Ads under Connections first.",
    })


def owned_connection(tenant_id: uuid.UUID, account_id: str) -> Dict[str, Any]:
    conns = tenant_ads_connections(tenant_id)
    if not conns:
        raise _no_ads_account()
    for c in conns:
        if c["account_id"] == account_id:
            return c
    raise HTTPException(status_code=403, detail={"error": "account_not_in_tenant",
                                                 "message": "That ads account is not connected to this workspace."})


def _ad_account_view(account_id: str, platform_key: str, a: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "account_id": account_id,
        "platform": platform_key,
        "ad_account_id": str(a.get("id")),
        "name": a.get("name"),
        "currency": a.get("currency"),
        "account_status": a.get("accountStatus", a.get("status")),
        "minimum_daily_budget": a.get("minimumDailyBudget"),
        "timezone": a.get("timezoneName"),
        "business_name": a.get("businessName"),
        "balance": a.get("balance"),
        "selectable": a.get("selectable", True),
        "unusable_reason": a.get("unusableReason"),
    }


async def list_ad_accounts_cached(client, tenant_id: uuid.UUID, conn_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    key = f"{tenant_id}:{conn_row['account_id']}"
    hit = _ACCT_CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _ACCT_TTL:
        return hit[1]
    raw = await client.ads_list_ad_accounts(conn_row["account_id"])
    pk = ACCOUNT_PLATFORM_TO_ADS.get(conn_row["platform"], conn_row["platform"])
    views = [_ad_account_view(conn_row["account_id"], pk, a) for a in raw if isinstance(a, dict) and a.get("id")]
    _ACCT_CACHE[key] = (time.monotonic(), views)
    return views


async def owned_ad_account(client, tenant_id: uuid.UUID, conn_row: Dict[str, Any], ad_account_id: str) -> Dict[str, Any]:
    try:
        accounts = await list_ad_accounts_cached(client, tenant_id, conn_row)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("list ad accounts", exc)
    for a in accounts:
        if a["ad_account_id"] == ad_account_id:
            if a.get("selectable") is False:
                raise HTTPException(status_code=422, detail={"error": "ad_account_unusable",
                                                             "message": a.get("unusable_reason") or "This ad account cannot run ads."})
            return a
    raise HTTPException(status_code=403, detail={"error": "ad_account_not_available",
                                                 "message": "That ad account is not available on this connection."})


# ───────────────────────── routes: accounts, goals, options ─────────────────────────


@router.get("/ads/accounts")
async def ads_accounts(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Ads accounts connected for this workspace and the platform ad accounts under each.

    {connections:[{account_id, platform, username, status}], ad_accounts:[{account_id, platform, ad_account_id,
    name, currency, minimum_daily_budget, ...}], errors:[...]} - empty `connections` means "no ads account connected"."""
    conns = tenant_ads_connections(tenant_id)
    out: Dict[str, Any] = {
        "connections": [{"account_id": c["account_id"], "platform": ACCOUNT_PLATFORM_TO_ADS.get(c["platform"], c["platform"]),
                         "account_platform": c["platform"], "username": c["username"], "status": c["status"]} for c in conns],
        "ad_accounts": [], "errors": [],
    }
    if not conns:
        out["message"] = _no_ads_account().detail["message"]
        return out
    client = _client()

    async def one(c):
        try:
            return await list_ad_accounts_cached(client, tenant_id, c), None
        except Exception as exc:  # noqa: BLE001
            err = provider_error("list ad accounts", exc)
            return [], {"account_id": c["account_id"], "error": err.detail}

    for accounts, err in await asyncio.gather(*(one(c) for c in conns)):
        out["ad_accounts"].extend(accounts)
        if err:
            out["errors"].append(err)
    return out


@router.get("/ads/goals")
async def ads_goals(platform: Optional[str] = Query(None, description="meta|google|tiktok|linkedin|pinterest|x")):
    """Objective enum per ads platform (documented values; the provider validates the rest)."""
    def view(pk: str) -> Dict[str, Any]:
        return {"platform": pk, "goals": [{"id": g, "label": GOAL_LABELS.get(g, g),
                                           "requires": _goal_requirements(pk, g)} for g in GOALS[pk]]}
    if platform:
        pk = platform.lower()
        if pk not in GOALS:
            raise HTTPException(status_code=422, detail=f"Unknown ads platform '{platform}'. One of {sorted(GOALS)}")
        return view(pk)
    return {"platforms": [view(pk) for pk in GOALS]}


def _goal_requirements(pk: str, goal: str) -> List[str]:
    req: List[str] = []
    if pk == "meta":
        req = ["creative.headline", "creative.body", "creative.call_to_action", "media"]
        req.append("creative.lead_gen_form_id" if goal == "lead_generation" else "creative.link_url")
        if goal in ("conversions", "lead_conversion"):
            req += ["promoted_object.pixel_id", "promoted_object.custom_event_type"]
    elif pk == "tiktok":
        req = ["creative.video_url", "creative.body"]
        if goal in ("traffic", "conversions"):
            req.append("creative.link_url")
        if goal == "conversions":
            req.append("promoted_object.pixel_id")
    elif pk == "linkedin":
        req = ["creative.headline", "creative.body", "media"]
        if goal == "traffic":
            req.append("creative.link_url")
        if goal == "video_views":
            req.append("creative.video_url")
        if goal == "lead_generation":
            req.append("creative.lead_gen_form_id")
    elif pk == "google":
        req = ["creative.headline", "creative.body", "creative.link_url"]
    elif pk == "pinterest":
        req = ["creative.headline", "creative.body", "creative.link_url", "media"]
    elif pk == "x":
        req = ["creative.body"]
    return req


@router.get("/ads/options")
async def ads_options():
    """Static enums for the Create Ad form."""
    return {
        "budget_types": ["daily", "lifetime"],
        "statuses": ["PAUSED", "ACTIVE"],
        "default_status": "PAUSED",
        "genders": ["all", "male", "female"],
        "call_to_actions": CALL_TO_ACTIONS,
        "linkedin_call_to_actions": sorted(LINKEDIN_CTAS),
        "age_range": {"min": 13, "max": 65},
        "budget_unit": "whole currency units (not cents)",
        "provider_dry_run_platforms": sorted(PROVIDER_VALIDATE),
        "limits": {"headline_max": HEADLINE_MAX, "body_max": BODY_MAX},
    }


# ───────────────────────── routes: targeting + audiences ─────────────────────────


@router.get("/ads/targeting/search")
async def ads_targeting_search(
    account_id: str, q: str = Query(..., min_length=1, max_length=100),
    dimension: str = Query("geo", pattern="^(geo|interest|behavior|income|language|workPosition|workEmployer|workIndustry|industry|jobFunction|seniority|companySize)$"),
    geo_type: Optional[str] = Query(None, pattern="^(all|country|country_group|region|city|subcity|neighborhood|place|zip|metro_area|geo_market)$"),
    country_code: Optional[str] = Query(None, pattern="^[A-Za-z]{2}$"),
    ad_account_id: Optional[str] = None,
    limit: int = Query(25, ge=1, le=100),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Resolve 'Johannesburg' / 'cycling' into the platform's opaque targeting ids (use as regions/cities/interests)."""
    owned_connection(tenant_id, account_id)
    try:
        results = await _client().ads_targeting_search(
            account_id, q, dimension=dimension, geo_type=geo_type, country_code=country_code,
            ad_account_id=ad_account_id, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("targeting search", exc)
    return {"results": results}


class ReachIn(BaseModel):
    account_id: str
    ad_account_id: str
    targeting: Targeting


@router.post("/ads/targeting/reach")
async def ads_reach(body: ReachIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Estimated audience size for a targeting selection (Meta, LinkedIn, X, Pinterest; Google/TikTok report available:false)."""
    conn_row = owned_connection(tenant_id, body.account_id)
    client = _client()
    await owned_ad_account(client, tenant_id, conn_row, body.ad_account_id)
    t = body.targeting
    spec: Dict[str, Any] = {}
    if t.countries:
        spec["countries"] = [x.upper() for x in t.countries]
    if t.regions:
        spec["regions"] = t.regions
    if t.cities:
        spec["cities"] = t.cities
    if t.age_min:
        spec["ageMin"] = t.age_min
    if t.age_max:
        spec["ageMax"] = t.age_max
    if t.interests:
        spec["interests"] = [{"id": str(i["id"]), "name": i["name"]} for i in t.interests if i.get("id") and i.get("name")]
    try:
        return await client.ads_reach_estimate(body.account_id, body.ad_account_id, spec)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("reach estimate", exc)


@router.get("/ads/audiences")
async def ads_audiences(
    account_id: str, ad_account_id: str,
    type: Optional[str] = Query(None, pattern="^(customer_list|company_list|engagement|meta_engagement|website|website_retargeting|lookalike|saved_targeting)$"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Custom / lookalike / saved audiences that exist on the ad account (targetable in Create Ad)."""
    conn_row = owned_connection(tenant_id, account_id)
    client = _client()
    await owned_ad_account(client, tenant_id, conn_row, ad_account_id)
    try:
        auds = await client.ads_list_audiences(account_id, ad_account_id, type_=type)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("list audiences", exc)
    return {"audiences": [{"id": a.get("id"), "platform_audience_id": a.get("platformAudienceId"), "name": a.get("name"),
                           "type": a.get("type"), "description": a.get("description"),
                           "size": a.get("size") or a.get("approximateCount")} for a in auds if isinstance(a, dict)]}


class AudienceCreateIn(BaseModel):
    account_id: str
    ad_account_id: str
    name: str = Field(..., min_length=1, max_length=120)
    type: str = Field(..., pattern="^(customer_list|website|lookalike|meta_engagement)$")
    description: Optional[str] = None
    # website
    pixel_id: Optional[str] = None
    retention_days: Optional[int] = Field(None, ge=1, le=540)
    url_contains: Optional[str] = None
    # lookalike
    source_audience_id: Optional[str] = None
    country: Optional[str] = Field(None, pattern="^[A-Za-z]{2}$")
    ratio: Optional[float] = Field(None, gt=0, le=0.2)
    # meta_engagement
    engagement_source: Optional[str] = Field(None, pattern="^(page|instagram|video)$")
    source_id: Optional[str] = None
    event: Optional[str] = None


@router.post("/ads/audiences", status_code=201, dependencies=[Depends(require_marketing_write)])
async def ads_create_audience(body: AudienceCreateIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Create an empty customer_list, a website (pixel) audience, a lookalike, or a Meta engagement audience."""
    conn_row = owned_connection(tenant_id, body.account_id)
    client = _client()
    await owned_ad_account(client, tenant_id, conn_row, body.ad_account_id)
    if body.type == "website" and not (body.pixel_id and body.retention_days):
        raise HTTPException(status_code=422, detail="website audiences need pixel_id and retention_days")
    if body.type == "lookalike" and not (body.source_audience_id and body.country):
        raise HTTPException(status_code=422, detail="lookalike audiences need source_audience_id and country")
    if body.type == "meta_engagement" and not (body.engagement_source and body.source_id):
        raise HTTPException(status_code=422, detail="engagement audiences need engagement_source and source_id")
    payload: Dict[str, Any] = {"accountId": body.account_id, "adAccountId": body.ad_account_id, "name": body.name,
                               "type": body.type}
    for src, dst in (("description", "description"), ("pixel_id", "pixelId"), ("retention_days", "retentionDays"),
                     ("source_audience_id", "sourceAudienceId"), ("country", "country"), ("ratio", "ratio"),
                     ("engagement_source", "engagementSource"), ("source_id", "sourceId"), ("event", "event")):
        v = getattr(body, src)
        if v is not None:
            payload[dst] = v
    if body.url_contains:
        payload["urlContains"] = body.url_contains
    try:
        res = await client.ads_create_audience(payload)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("create audience", exc)
    return {"audience": (res or {}).get("audience"), "message": (res or {}).get("message")}


class AudienceFromSegmentIn(BaseModel):
    segment_id: uuid.UUID
    account_id: str
    ad_account_id: str
    name: Optional[str] = Field(None, max_length=120)


@router.post("/ads/audiences/from-segment", status_code=201, dependencies=[Depends(require_marketing_write)])
async def ads_audience_from_segment(body: AudienceFromSegmentIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Push an OmniDome audience (businesses / contact list) to the ad platform as a customer-match
    audience. Emails (and phones, Meta only) are SHA-256 hashed by the provider before reaching the platform.
    Homes audiences (areas only) cannot be uploaded: 422."""
    conn_row = owned_connection(tenant_id, body.account_id)
    client = _client()
    await owned_ad_account(client, tenant_id, conn_row, body.ad_account_id)
    with get_engine().connect() as conn:
        seg = conn.execute(text("SELECT id, name, rules FROM marketing_audience_segments WHERE id = :id AND tenant_id = :tid"),
                           {"id": str(body.segment_id), "tid": str(tenant_id)}).mappings().first()
    if not seg:
        raise HTTPException(status_code=404, detail="Audience not found")
    members = resolve_members(seg["rules"] or {})
    users = [{"email": e} for e in members["emails"]]
    if not users:
        raise HTTPException(status_code=422, detail=members["note"] or "This audience has no members with an email address")
    try:
        created = await client.ads_create_audience({
            "accountId": body.account_id, "adAccountId": body.ad_account_id,
            "name": body.name or f"OmniDome - {seg['name']}"[:120], "type": "customer_list",
        })
        aud = (created or {}).get("audience") or {}
        audience_id = aud.get("id")
        if not audience_id:
            raise HTTPException(status_code=502, detail={"error": "provider_no_audience", "message": "The provider did not return an audience id."})
        sent = invalid = 0
        for i in range(0, len(users), 10000):
            r = await client.ads_add_audience_users(audience_id, users[i:i + 10000])
            sent += int(r.get("numReceived") or 0)
            invalid += int(r.get("numInvalid") or 0)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise provider_error("audience upload", exc)
    return {"audience_id": audience_id, "name": aud.get("name"), "members_sent": sent, "members_invalid": invalid,
            "members_without_email": members["skipped"]}


# ───────────────────────── routes: validate / preview / create ─────────────────────────


async def _prepare(ad: AdCreateIn, tenant_id: uuid.UUID, with_account_check: bool) -> Tuple[str, Optional[Dict[str, Any]], Dict[str, Any]]:
    conn_row = owned_connection(tenant_id, ad.account_id)
    platform = ACCOUNT_PLATFORM_TO_ADS[conn_row["platform"]]
    account = None
    if with_account_check:
        account = await owned_ad_account(_client(), tenant_id, conn_row, ad.ad_account_id)
    return platform, account, conn_row


@router.post("/ads/validate")
async def ads_validate(
    ad: AdCreateIn,
    provider: bool = Query(True, description="also run the provider's dry run where one exists (Meta)"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Check an ad before creating it. Returns {valid, errors, warnings, provider_validated, provider}.
    Nothing is created. Local rules always run; the provider dry run (Meta `validateOnly`) runs when
    available and its rejection message is returned verbatim as an error."""
    platform, account, _ = await _prepare(ad, tenant_id, True)
    errors, warnings = validate_ad(ad, platform, account)
    out: Dict[str, Any] = {"platform": platform, "provider_validated": False, "provider": None}
    if provider and not errors and platform in PROVIDER_VALIDATE:
        try:
            res = await _client().ads_create(build_provider_body(ad, platform, (account or {}).get("currency"), validate_only=True))
            out["provider_validated"] = True
            out["provider"] = {"results": (res or {}).get("results"), "message": (res or {}).get("message")}
        except Exception as exc:  # noqa: BLE001
            err = provider_error("ad validate", exc)
            if err.status_code == 422:
                errors.append({"field": "provider", "code": (err.detail or {}).get("provider_code") or "provider_rejected",
                               "message": (err.detail or {}).get("message", "The provider rejected this ad")})
                out["provider_validated"] = True
            else:
                warnings.append({"field": "provider", "code": "provider_unavailable",
                                 "message": "Could not reach the provider for a dry run; only local checks were applied"})
    elif provider and platform not in PROVIDER_VALIDATE:
        warnings.append({"field": "provider", "code": "no_provider_dry_run",
                         "message": f"{platform} has no provider dry run; the provider validates when you create the ad"})
    out.update(valid=not errors, errors=errors, warnings=warnings)
    return out


class AdPreviewIn(BaseModel):
    account_id: str
    ad_account_id: str
    creative: Creative = Field(default_factory=Creative)
    existing_creative_id: Optional[str] = None
    creative_spec: Optional[Dict[str, Any]] = Field(None, description="Meta object_story_spec for the provider render")
    formats: List[str] = Field(default_factory=list, description="Meta placement formats, e.g. DESKTOP_FEED_STANDARD, MOBILE_FEED_STANDARD")


@router.post("/ads/preview")
async def ads_preview(body: AdPreviewIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Preview an ad. `local` is always returned (text/media/CTA as the form has them, for an in-app mock);
    `provider` carries Meta's rendered <iframe> previews when creative_spec or existing_creative_id is given
    (Meta only; other platforms have no pre-create preview)."""
    conn_row = owned_connection(tenant_id, body.account_id)
    platform = ACCOUNT_PLATFORM_TO_ADS[conn_row["platform"]]
    c = body.creative
    out: Dict[str, Any] = {
        "platform": platform,
        "local": {"headline": c.headline, "body": c.body, "description": c.description,
                  "call_to_action": c.call_to_action, "destination": c.link_url,
                  "display_url": re.sub(r"^https?://(www\.)?", "", c.link_url or "").split("/")[0] or None,
                  "image_url": c.image_url, "video_url": c.video_url},
        "provider": None,
    }
    if body.existing_creative_id or body.creative_spec:
        if platform != "meta":
            out["provider_note"] = "Provider previews are available for Meta only."
            return out
        client = _client()
        await owned_ad_account(client, tenant_id, conn_row, body.ad_account_id)
        payload: Dict[str, Any] = {"accountId": body.account_id, "adAccountId": body.ad_account_id}
        if body.formats:
            payload["formats"] = body.formats[:12]
        if body.existing_creative_id:
            payload["existingCreativeId"] = body.existing_creative_id
        else:
            payload["creativeSpec"] = body.creative_spec
        try:
            res = await client.ads_preview(payload)
        except Exception as exc:  # noqa: BLE001
            raise provider_error("ad preview", exc)
        out["provider"] = (res or {}).get("previews") or []
    return out


@router.post("/ads/create", status_code=201, dependencies=[Depends(require_marketing_write)])
async def ads_create(ad: AdCreateIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Create a real ad at the provider (campaign + ad set + ad). PAUSED by default.

    201 {status:'created', ad:{ad_id, platform_campaign_id, ...}, local_campaign_id}
    409 no_ads_account | 403 account_not_in_tenant / ad_account_not_available
    422 validation_failed {errors[]} | provider_rejected {message, provider_status, details}
    Success is reported only if the provider returned an ad id."""
    platform, account, conn_row = await _prepare(ad, tenant_id, True)
    errors, warnings = validate_ad(ad, platform, account)
    if errors:
        raise HTTPException(status_code=422, detail={"error": "validation_failed", "errors": errors, "warnings": warnings})
    body = build_provider_body(ad, platform, (account or {}).get("currency"))
    key = f"omnidome-ad-{tenant_id}-{ad.client_request_id}" if ad.client_request_id else f"omnidome-ad-{uuid.uuid4().hex}"
    try:
        res = await _client().ads_create(body, idempotency_key=key[:255])
    except Exception as exc:  # noqa: BLE001
        raise provider_error("ad create", exc)
    created = parse_created_ads(res)
    if not created:
        logger.error("ads/create returned no ad id for tenant %s", tenant_id)
        raise HTTPException(status_code=502, detail={"error": "provider_no_ad",
                                                     "message": "The provider accepted the request but returned no ad, so nothing is shown as created. Check the ad account in the platform before retrying."})
    views = [normalize_ad(a) for a in created]
    local_id = await asyncio.to_thread(_save_local_campaign, tenant_id, ad, platform, account, views[0])
    return {"status": "created", "created_as": ad.status.lower(), "ads": views, "ad": views[0],
            "local_campaign_id": str(local_id) if local_id else None, "warnings": warnings}


def _save_local_campaign(tenant_id: uuid.UUID, ad: AdCreateIn, platform: str, account: Optional[Dict[str, Any]],
                         view: Dict[str, Any]) -> Optional[uuid.UUID]:
    """Mirror the provider ad into the OmniDome ads table so the existing Ads list shows it."""
    cur = (ad.budget.currency or (account or {}).get("currency") or "").upper()
    in_zar = cur == "ZAR"
    amount = Decimal(str(ad.budget.amount))
    status_ = str(view.get("status") or ad.status).upper()
    creative = {"headline": ad.creative.headline, "body": ad.creative.body, "call_to_action": ad.creative.call_to_action,
                "link_url": ad.creative.link_url, "image_url": ad.creative.image_url, "video_url": ad.creative.video_url,
                "provider": {"account_id": ad.account_id, "ad_account_id": ad.ad_account_id, "currency": cur or None,
                             "budget": {"amount": ad.budget.amount, "type": ad.budget.type}, **{k: v for k, v in view.items() if v is not None}}}
    targeting = ad.targeting.model_dump()
    new_id = uuid.uuid4()
    try:
        with get_engine().begin() as conn:
            conn.execute(text("""
                INSERT INTO ad_campaigns (id, tenant_id, name, platform, objective, status, budget_zar, daily_budget_zar,
                                          start_date, end_date, targeting, creative, impressions, clicks, conversions, spend_zar)
                VALUES (:id, :tid, :name, :platform, :goal, :status, :budget, :daily, :sd, :ed,
                        CAST(:targeting AS jsonb), CAST(:creative AS jsonb), 0, 0, 0, 0)
            """), {
                "id": str(new_id), "tid": str(tenant_id), "name": ad.name[:255], "platform": platform, "goal": ad.goal,
                "status": status_[:20], "budget": amount if (in_zar and ad.budget.type == "lifetime") else Decimal("0"),
                "daily": amount if (in_zar and ad.budget.type == "daily") else None,
                "sd": _parse_when(ad.start_date), "ed": _parse_when(ad.end_date),
                "targeting": json.dumps(targeting, default=str), "creative": json.dumps(creative, default=str),
            })
        return new_id
    except Exception as exc:  # noqa: BLE001 - the ad exists at the provider; a mirror failure must not hide that
        logger.error("could not mirror created ad into ad_campaigns: %s", exc)
        return None


# ───────────────────────── routes: provider lists + status ─────────────────────────


@router.get("/ads/provider/ads")
async def ads_provider_list(
    account_id: Optional[str] = None,
    status: Optional[str] = Query(None, pattern="^(active|paused|pending_review|rejected|completed|cancelled|error)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Live ads for this workspace from the provider (status, review status, spend metrics)."""
    if account_id:
        owned_connection(tenant_id, account_id)
    elif not tenant_ads_connections(tenant_id):
        raise _no_ads_account()
    profile_id = _mk()._get_tenant_profile(tenant_id)
    try:
        res = await _client().ads_list_ads(profile_id=profile_id, account_id=account_id, status=status, page=page, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("list ads", exc)
    return res


class AdStatusIn(BaseModel):
    status: str = Field(..., pattern="^(active|paused)$")


@router.put("/ads/provider/ads/{ad_id}/status", dependencies=[Depends(require_marketing_write)])
async def ads_set_status(ad_id: str, body: AdStatusIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Pause / resume one ad. The ad must appear in this workspace's own provider ad list."""
    if not re.fullmatch(r"[A-Za-z0-9_\-]{6,64}", ad_id):
        raise HTTPException(status_code=422, detail="Invalid ad id")
    if not tenant_ads_connections(tenant_id):
        raise _no_ads_account()
    client = _client()
    profile_id = _mk()._get_tenant_profile(tenant_id)
    try:
        found = await client.ads_list_ads(profile_id=profile_id, limit=100)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("list ads", exc)
    ids = {str(a.get("_id") or a.get("id")) for a in (found or {}).get("ads") or [] if isinstance(a, dict)}
    if ad_id not in ids:
        raise HTTPException(status_code=404, detail="Ad not found in this workspace")
    try:
        return await client.ads_set_ad_status(ad_id, body.status)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("ad status", exc)


# thin aliases so the Create Ad modal can stay under /ads/*
@router.post("/ads/media/presign", dependencies=[Depends(require_marketing_write)])
async def ads_media_presign(body: Dict[str, Any], tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Same as POST /social/media/presign (images, videos). Use the returned public_url as creative.image_url / video_url."""
    mk = _mk()
    return await mk.presign_media(mk.MediaPresignIn(**body), tenant_id)
