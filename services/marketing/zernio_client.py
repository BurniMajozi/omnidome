"""
Zernio API Client for OmniDome Marketing Service
-------------------------------------------------
Handles all Zernio API v1 calls: social messaging, conversations,
accounts, inbox, and webhooks across 7 platforms.

API Base: https://zernio.com/api/v1
Docs: https://docs.zernio.com

Usage:
    from services.marketing.zernio_client import ZernioClient
    client = ZernioClient(api_key=os.getenv("ZERNIO_API_KEY"))
    accounts = await client.list_accounts()
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

ZERNIO_BASE_URL = "https://zernio.com/api/v1"


class ZernioError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"Zernio API error {status}: {message}")


class ZernioRateLimitError(ZernioError):
    """Raised on HTTP 429. Carries seconds until the limit resets so a worker
    can sleep exactly that long and retry the same page."""

    def __init__(self, message: str, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        super().__init__(429, message)

    def seconds_until_reset(self, default: int = 5) -> int:
        return self.retry_after if self.retry_after and self.retry_after > 0 else default


class ZernioClient:
    """Async REST client for Zernio API v1."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = ZERNIO_BASE_URL,
        webhook_secret: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("ZERNIO_API_KEY", "")
        if not self.api_key:
            raise ValueError("ZERNIO_API_KEY environment variable is required")
        self.base_url = base_url.rstrip("/")
        self.webhook_secret = webhook_secret or os.getenv("ZERNIO_WEBHOOK_SECRET")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # ── Internal ──────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout,
            )
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
    ) -> Any:
        client = await self._get_client()
        resp = await client.request(method, path, params=params, json=json_data)
        if resp.status_code == 429:
            # Prefer Retry-After; fall back to X-RateLimit-Reset (epoch seconds).
            retry_after: Optional[int] = None
            ra = resp.headers.get("Retry-After")
            if ra and ra.isdigit():
                retry_after = int(ra)
            else:
                reset = resp.headers.get("X-RateLimit-Reset")
                if reset and reset.isdigit():
                    import time
                    retry_after = max(1, int(reset) - int(time.time()))
            raise ZernioRateLimitError(resp.text, retry_after=retry_after)
        if resp.status_code >= 400:
            raise ZernioError(resp.status_code, resp.text)
        return resp.json()

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Accounts ───────────────────────────────────────────────────────

    async def list_accounts(
        self, platform: Optional[str] = None, status: Optional[str] = None
    ) -> List[Dict]:
        """List all connected social media accounts."""
        params: Dict[str, Any] = {}
        if platform:
            params["platform"] = platform
        if status:
            params["status"] = status
        result = await self._request("GET", "/accounts", params=params)
        if isinstance(result, dict):
            return result.get("data", result.get("accounts", []))
        return result if isinstance(result, list) else []

    async def get_account(self, account_id: str) -> Dict:
        """Get a specific account by ID.

        Spec note: /v1/accounts/{accountId} has no GET — filter the
        list endpoint instead (verified against zernio.com/openapi.json).
        """
        accounts = await self.list_accounts()
        for acct in accounts:
            if acct.get("_id") == account_id or acct.get("id") == account_id:
                return acct
        return {}

    # ── Conversations / Inbox ──────────────────────────────────────────

    async def list_conversations(
        self,
        platform: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        cursor: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List inbox conversations across platforms.

        Path verified: GET /v1/inbox/conversations (spec: platform, status,
        limit, cursor, accountId query params).
        """
        params: Dict[str, Any] = {"limit": limit}
        if platform:
            params["platform"] = platform
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        if account_id:
            params["accountId"] = account_id
        return await self._request("GET", "/inbox/conversations", params=params)

    async def get_conversation(
        self, conversation_id: str, account_id: Optional[str] = None
    ) -> Dict:
        """Get a specific conversation (spec requires accountId query)."""
        params: Dict[str, Any] = {}
        if account_id:
            params["accountId"] = account_id
        result = await self._request(
            "GET", f"/inbox/conversations/{conversation_id}", params=params
        )
        return result.get("data", result) if isinstance(result, dict) else result

    async def fetch_messages(
        self,
        conversation_id: str,
        account_id: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
        sort_order: str = "asc",
    ) -> Dict[str, Any]:
        """Fetch messages from a conversation (spec requires accountId query)."""
        params: Dict[str, Any] = {"limit": limit, "sortOrder": sort_order}
        if account_id:
            params["accountId"] = account_id
        if cursor:
            params["cursor"] = cursor
        return await self._request(
            "GET", f"/inbox/conversations/{conversation_id}/messages", params=params
        )

    # ── Messages (Send) ───────────────────────────────────────────────

    async def send_message(
        self,
        conversation_id: str,
        message: str,
        account_id: Optional[str] = None,
        attachment_url: Optional[str] = None,
    ) -> Dict:
        """Send a message in a conversation.

        Path verified: POST /v1/inbox/conversations/{id}/messages with
        { accountId?, message, attachmentUrl? } (spec body schema).
        """
        payload: Dict[str, Any] = {"message": message}
        if account_id:
            payload["accountId"] = account_id
        if attachment_url:
            payload["attachmentUrl"] = attachment_url
        result = await self._request(
            "POST", f"/inbox/conversations/{conversation_id}/messages", json_data=payload
        )
        return result.get("data", result) if isinstance(result, dict) else result

    async def send_inbox_message(
        self,
        conversation_id: str,
        content: str,
        account_id: Optional[str] = None,
    ) -> Dict:
        """Send a reply to an inbox message (alias for send_message)."""
        return await self.send_message(conversation_id, content, account_id=account_id)

    # ── Posts ─────────────────────────────────────────────────────────

    async def create_post(
        self,
        content: str,
        platforms: List[str],
        account_ids: Optional[List[str]] = None,
        profile_id: Optional[str] = None,
        is_draft: bool = False,
        publish_now: bool = False,
        schedule_minutes: int = 60,
        media_urls: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Dict:
        """Create a social media post."""
        payload: Dict[str, Any] = {
            "content": content,
            "platforms": platforms,
            "is_draft": is_draft,
            "publish_now": publish_now,
            "schedule_minutes": schedule_minutes,
        }
        if account_ids:
            payload["account_ids"] = account_ids
        if profile_id:
            payload["profile_id"] = profile_id
        if media_urls:
            payload["media_urls"] = media_urls
        if title:
            payload["title"] = title
        result = await self._request("POST", "/posts", json_data=payload)
        return result.get("data", result) if isinstance(result, dict) else result

    async def list_posts(
        self,
        status: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict]:
        """List posts."""
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        result = await self._request("GET", "/posts", params=params)
        return result.get("data", result) if isinstance(result, dict) else result

    # ── Webhook Verification ──────────────────────────────────────────

    def verify_webhook(self, payload_body: bytes, signature: str) -> bool:
        """Verify Zernio webhook HMAC-SHA256 signature."""
        if not self.webhook_secret:
            logger.warning("ZERNIO_WEBHOOK_SECRET not set — skipping verification")
            return True
        expected = hmac.new(
            self.webhook_secret.encode(),
            payload_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    # ── Profiles (one per customer/tenant) ─────────────────────────────

    async def create_profile(self, name: str, description: Optional[str] = None) -> Dict:
        """POST /v1/profiles — one profile per customer. Names are unique per
        team; a duplicate name returns 409 (ZernioError.status == 409) with
        details.existingProfileId, which the caller reuses."""
        payload: Dict[str, Any] = {"name": name}
        if description:
            payload["description"] = description
        return await self._request("POST", "/profiles", json_data=payload)

    async def list_profiles(self) -> List[Dict]:
        result = await self._request("GET", "/profiles")
        if isinstance(result, dict):
            return result.get("profiles", result.get("data", []))
        return result if isinstance(result, list) else []

    async def delete_profile(self, profile_id: str) -> Dict:
        """DELETE /v1/profiles/{id}. Active connected accounts block deletion
        with a 400 — disconnect them first."""
        return await self._request("DELETE", f"/profiles/{profile_id}")

    # ── Social Account Connection ──────────────────────────────────────

    async def get_connect_url(
        self,
        platform: str,
        profile_id: Optional[str] = None,
        redirect_url: Optional[str] = None,
    ) -> str:
        """Get OAuth connect URL so the account lands in `profile_id` (defaults
        to ZERNIO_PROFILE_ID). Returns "" when no profile id is available so
        callers degrade gracefully."""
        pid = profile_id or os.getenv("ZERNIO_PROFILE_ID", "")
        if not pid:
            logger.warning("no profileId available — connect URL unavailable")
            return ""
        params: Dict[str, Any] = {"profileId": pid}
        if redirect_url:
            params["redirect_url"] = redirect_url
        result = await self._request("GET", f"/connect/{platform}", params=params)
        if isinstance(result, dict):
            return result.get("authUrl", result.get("connect_url", result.get("url", "")))
        return str(result)

    async def disconnect_account(self, account_id: str) -> Dict:
        """Disconnect a social media account."""
        return await self._request("DELETE", f"/accounts/{account_id}")

    async def get_accounts_health(
        self, profile_id: str, status: Optional[str] = None
    ) -> Dict:
        """GET /v1/accounts/health — per-account token health + a summary with
        needsReconnect. `status` (e.g. 'error') filters the list."""
        params: Dict[str, Any] = {"profileId": profile_id}
        if status:
            params["status"] = status
        return await self._request("GET", "/accounts/health", params=params)

    # ── Billing / usage + API keys (platform admin) ─────────────────────

    async def get_usage(self, range_: str = "cycle", group_by: str = "profile") -> Dict:
        """GET /v1/usage — spend for the period, split per profile when
        group_by='profile' (attribution.groups[])."""
        return await self._request("GET", "/usage", params={"range": range_, "groupBy": group_by})

    async def create_api_key(
        self,
        name: str,
        scope: Optional[str] = None,
        profile_ids: Optional[List[str]] = None,
        permission: Optional[str] = None,
        disabled_resource_groups: Optional[List[str]] = None,
        expires_in: Optional[int] = None,
    ) -> Dict:
        """POST /v1/api-keys — mint a (optionally profile-scoped, read-only,
        or group-restricted) key. There is no update endpoint."""
        payload: Dict[str, Any] = {"name": name}
        if scope:
            payload["scope"] = scope
        if profile_ids:
            payload["profileIds"] = profile_ids
        if permission:
            payload["permission"] = permission
        if disabled_resource_groups:
            payload["disabledResourceGroups"] = disabled_resource_groups
        if expires_in is not None:
            payload["expiresIn"] = expires_in
        return await self._request("POST", "/api-keys", json_data=payload)

    # ── Analytics ──────────────────────────────────────────────────────

    async def get_analytics(
        self,
        platform: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict:
        """Legacy overview call (platform + from/to). Kept for back-compat."""
        params: Dict[str, Any] = {}
        if platform:
            params["platform"] = platform
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return await self._request("GET", "/analytics", params=params)

    # ── Analytics: profile-scoped (what the sync worker uses) ──────────────

    async def get_post_analytics(
        self,
        profile_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
        source: str = "all",
    ) -> Dict[str, Any]:
        """GET /v1/analytics — per-post metrics + overview, paginated, for one
        customer's profile. `source`: late | external | all."""
        params: Dict[str, Any] = {"profileId": profile_id, "page": page, "limit": limit, "source": source}
        if from_date:
            params["fromDate"] = from_date
        if to_date:
            params["toDate"] = to_date
        return await self._request("GET", "/analytics", params=params)

    async def get_daily_metrics(
        self,
        profile_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        attribution: str = "publish",
        source: str = "all",
    ) -> Dict[str, Any]:
        """GET /v1/analytics/daily-metrics — day-by-day sums + platform
        breakdown. `attribution`: publish (default) | received."""
        params: Dict[str, Any] = {"profileId": profile_id, "attribution": attribution, "source": source}
        if from_date:
            params["fromDate"] = from_date
        if to_date:
            params["toDate"] = to_date
        return await self._request("GET", "/analytics/daily-metrics", params=params)

    async def get_follower_stats(
        self,
        profile_id: str,
        granularity: str = "daily",
    ) -> Dict[str, Any]:
        """GET /v1/accounts/follower-stats — follower counts + growth.
        `granularity`: daily | weekly | monthly."""
        return await self._request(
            "GET", "/accounts/follower-stats",
            params={"profileId": profile_id, "granularity": granularity},
        )
