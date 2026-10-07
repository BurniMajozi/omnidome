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


_VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm", ".avi", ".mpeg", ".mpg")


def _guess_media_type(url: str) -> str:
    """Zernio mediaItems need a `type` (image|video|gif|document)."""
    base = (url or "").split("?", 1)[0].lower()
    if base.endswith(".gif"):
        return "gif"
    if base.endswith(".pdf"):
        return "document"
    if base.endswith(_VIDEO_EXT):
        return "video"
    return "image"


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
        base_url: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("ZERNIO_API_KEY", "")
        if not self.api_key:
            raise ValueError("ZERNIO_API_KEY environment variable is required")
        self.base_url = (base_url or os.getenv("ZERNIO_BASE_URL") or ZERNIO_BASE_URL).rstrip("/")
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
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        client = await self._get_client()
        # None-valued params are dropped so callers can pass optional filters blindly.
        clean = {k: v for k, v in (params or {}).items() if v is not None} or None
        resp = await client.request(
            method, path, params=clean, json=json_data, headers=dict(headers or {}) or None,
        )
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
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}

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
        platforms: List[Any],
        account_ids: Optional[List[str]] = None,  # legacy, ignored
        profile_id: Optional[str] = None,
        is_draft: bool = False,
        publish_now: bool = False,
        schedule_minutes: int = 60,  # legacy, ignored (Zernio has no relative scheduling)
        media_urls: Optional[Any] = None,
        title: Optional[str] = None,
    ) -> Dict:
        """Deprecated shim over publish_content(). The previous implementation sent
        snake_case fields (is_draft, schedule_minutes, media_urls) that the API
        does not read, so posts silently became drafts. `platforms` must be the
        documented [{platform, accountId}] list."""
        return await self.publish_content(
            content=content, platforms=platforms, publish_now=publish_now,
            is_draft=is_draft, media_urls=media_urls if isinstance(media_urls, list) else None,
            title=title,
        )

    async def publish_content(
        self,
        content: str,
        platforms: List[Dict[str, Any]],  # [{platform, accountId, customContent?, ...}]
        publish_now: bool = True,
        schedule_date: Optional[str] = None,  # ISO8601; used when publish_now is False
        media_urls: Optional[List[str]] = None,
        title: Optional[str] = None,
        *,
        is_draft: bool = False,
        queued_from_profile: Optional[str] = None,
        queue_id: Optional[str] = None,
        timezone: Optional[str] = None,
        media_items: Optional[List[Dict[str, Any]]] = None,
        idempotency_key: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """POST /v1/posts (docs.zernio.com/posts/create-post).

        Exactly one scheduling intent is sent, in the documented precedence:
          draft (isDraft) > publishNow > scheduledFor > queuedFromProfile(+queueId).
        Field names are the real ones: scheduledFor / mediaItems / isDraft /
        queuedFromProfile / queueId / timezone. (The previous `scheduleDate` and
        `mediaUrls` were not API fields and were silently dropped.)
        Returns the created post ({_id, status, platforms:[{platform, accountId, status}]})."""
        payload: Dict[str, Any] = {"platforms": platforms}
        if content:
            payload["content"] = content
        if is_draft:
            payload["isDraft"] = True
        elif publish_now:
            payload["publishNow"] = True
        elif schedule_date:
            payload["scheduledFor"] = schedule_date
        elif queued_from_profile:
            payload["queuedFromProfile"] = queued_from_profile
            if queue_id:
                payload["queueId"] = queue_id
        else:
            payload["isDraft"] = True
        if timezone:
            payload["timezone"] = timezone
        items = list(media_items or [])
        if not items and media_urls:
            items = [{"type": _guess_media_type(u), "url": u} for u in media_urls if u]
        if items:
            payload["mediaItems"] = items
        if title:
            payload["title"] = title
        if tags:
            payload["tags"] = tags
        if metadata:
            payload["metadata"] = metadata
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        result = await self._request("POST", "/posts", json_data=payload, headers=headers)
        if isinstance(result, dict):
            return result.get("post", result.get("data", result))
        return result

    async def list_posts(
        self,
        status: Optional[str] = None,
        limit: int = 10,
        *,
        profile_id: Optional[str] = None,
        page: Optional[int] = None,
        platform: Optional[str] = None,
        account_id: Optional[str] = None,
        sort_by: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Any:
        """GET /v1/posts. status: draft|scheduled|publishing|published|partial|failed|cancelled.
        Returns the raw `{posts, pagination}` envelope when any new kwarg is used,
        else the legacy bare list."""
        params: Dict[str, Any] = {
            "limit": limit, "status": status, "profileId": profile_id, "page": page,
            "platform": platform, "accountId": account_id, "sortBy": sort_by,
            "fromDate": from_date, "toDate": to_date, "source": source,
        }
        result = await self._request("GET", "/posts", params=params)
        modern = any(v is not None for v in (profile_id, page, platform, account_id, sort_by, from_date, to_date, source))
        if modern:
            return result
        if isinstance(result, dict):
            return result.get("posts", result.get("data", result))
        return result

    async def get_post(self, post_id: str) -> Dict:
        result = await self._request("GET", f"/posts/{post_id}")
        return result.get("post", result) if isinstance(result, dict) else result

    async def delete_post(self, post_id: str) -> Dict:
        return await self._request("DELETE", f"/posts/{post_id}")

    async def retry_post(self, post_id: str) -> Dict:
        return await self._request("POST", f"/posts/{post_id}/retry", json_data={})

    # ── Media ─────────────────────────────────────────────────────────

    async def presign_media(self, filename: str, content_type: str, size: Optional[int] = None) -> Dict:
        """POST /v1/media/presign -> {uploadUrl, publicUrl, key, expiresIn}. PUT the
        bytes to uploadUrl (no auth header), then use publicUrl in posts/ads."""
        payload: Dict[str, Any] = {"filename": filename, "contentType": content_type}
        if size is not None:
            payload["size"] = size
        return await self._request("POST", "/media/presign", json_data=payload)

    async def put_presigned(self, upload_url: str, data: bytes, content_type: str) -> None:
        """PUT bytes to a presigned storage URL. Uses a throwaway client: the URL is
        a third-party bucket and must NOT receive our Authorization header."""
        async with httpx.AsyncClient(timeout=max(self.timeout, 300.0)) as c:
            resp = await c.put(upload_url, content=data, headers={"Content-Type": content_type})
        if resp.status_code >= 400:
            raise ZernioError(resp.status_code, "media storage rejected the upload")

    # ── Broadcasts (WhatsApp / SMS / social) ──────────────────────────

    async def create_broadcast(
        self,
        *,
        profile_id: str,
        account_id: str,
        platform: str,
        name: str,
        description: Optional[str] = None,
        template: Optional[Dict[str, Any]] = None,
        message: Optional[Dict[str, Any]] = None,
        segment_filters: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """Create a broadcast draft. WhatsApp requires a `template` (Meta-approved).

        POST /v1/broadcasts → { success, broadcast: { id, status, ... } }
        """
        payload: Dict[str, Any] = {
            "profileId": profile_id,
            "accountId": account_id,
            "platform": platform,
            "name": name,
        }
        if description:
            payload["description"] = description
        if template:
            payload["template"] = template
        if message:
            payload["message"] = message
        if segment_filters:
            payload["segmentFilters"] = segment_filters
        result = await self._request("POST", "/broadcasts", json_data=payload)
        if isinstance(result, dict):
            return result.get("broadcast", result.get("data", result))
        return result

    async def add_broadcast_recipients(
        self,
        broadcast_id: str,
        *,
        phones: Optional[List[str]] = None,
        contact_ids: Optional[List[str]] = None,
        use_segment: bool = False,
    ) -> Dict:
        """Add recipients to a broadcast draft.

        POST /v1/broadcasts/{id}/recipients → { success, added, skipped }
        """
        payload: Dict[str, Any] = {}
        if phones:
            payload["phones"] = phones
        if contact_ids:
            payload["contactIds"] = contact_ids
        if use_segment:
            payload["useSegment"] = True
        return await self._request(
            "POST", f"/broadcasts/{broadcast_id}/recipients", json_data=payload
        )

    async def send_broadcast(self, broadcast_id: str) -> Dict:
        """Immediately send a draft broadcast.

        POST /v1/broadcasts/{id}/send → { success, status, sent, failed, recipientCount }
        """
        return await self._request("POST", f"/broadcasts/{broadcast_id}/send", json_data={})

    # ── Webhook Verification ──────────────────────────────────────────

    def verify_webhook(self, payload_body: bytes, signature: str) -> bool:
        """Verify Zernio webhook HMAC-SHA256 signature."""
        if not self.webhook_secret:
            # Fail closed (the route enforces the same policy via marketing.security).
            if os.getenv("ZERNIO_WEBHOOK_ALLOW_UNSIGNED", "").strip().lower() in {"1", "true", "yes", "on"}:
                logger.critical("ZERNIO_WEBHOOK_ALLOW_UNSIGNED=true — accepting unsigned webhook")
                return True
            logger.error("ZERNIO_WEBHOOK_SECRET not set — rejecting webhook")
            return False
        expected = hmac.new(
            self.webhook_secret.encode(),
            payload_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected.encode(), (signature or "").encode("utf-8", "ignore"))

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

    # ── Connect flows (headless, OmniDome-hosted UI) ───────────────────────
    # docs.zernio.com/guides/connecting-accounts

    async def start_connect(
        self,
        platform: str,
        profile_id: str,
        redirect_url: str,
        *,
        headless: bool = False,
        ads: bool = False,
        login_method: Optional[str] = None,
        login_mode: Optional[str] = None,
        scopes: Optional[str] = None,
        reconnect_account_id: Optional[str] = None,
        ad_account_ids: Optional[List[str]] = None,
        page_id: Optional[str] = None,
        onboarding: Optional[str] = None,
        permission_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /v1/connect/{platform} (or /v1/connect/{platform}/ads for the dedicated
        ads connection). Returns {authUrl, state?} (or {alreadyConnected, ...} for a
        Meta business-login reconnect). `redirect_url` MUST be ours: without it Zernio
        finishes on its own hosted dashboard, i.e. zernio.com/signin."""
        params: Dict[str, Any] = {
            "profileId": profile_id,
            "redirect_url": redirect_url,
            "headless": "true" if headless else None,
            "loginMethod": login_method,
            "loginMode": login_mode,
            "scopes": scopes,
            "reconnectAccountId": reconnect_account_id,
            "adAccountIds": ",".join(ad_account_ids) if ad_account_ids else None,
            "pageId": page_id,
            "onboarding": onboarding,
            "permissionLevel": permission_level,
        }
        path = f"/connect/{platform}/ads" if ads else f"/connect/{platform}"
        result = await self._request("GET", path, params=params)
        return result if isinstance(result, dict) else {"authUrl": str(result)}

    async def connect_get(
        self, path: str, params: Optional[Dict[str, Any]] = None, connect_token: Optional[str] = None
    ) -> Any:
        """GET a /v1/connect/... selection/list endpoint (path relative to /connect)."""
        headers = {"X-Connect-Token": connect_token} if connect_token else None
        return await self._request("GET", f"/connect/{path.lstrip('/')}", params=params, headers=headers)

    async def connect_post(
        self, path: str, body: Dict[str, Any], connect_token: Optional[str] = None
    ) -> Any:
        """POST a /v1/connect/... selection/credentials endpoint (path relative to /connect)."""
        headers = {"X-Connect-Token": connect_token} if connect_token else None
        return await self._request("POST", f"/connect/{path.lstrip('/')}", json_data=body, headers=headers)

    async def get_pending_connect_data(self, token: str) -> Dict[str, Any]:
        """GET /v1/connect/pending-data?token=<pendingDataToken> (LinkedIn orgs, GBP
        locations, Pinterest boards, Snapchat profiles, Slack channels)."""
        return await self._request("GET", "/connect/pending-data", params={"token": token})

    async def get_current_user_id(self) -> str:
        """GET /v1/users -> currentUserId (needed for Bluesky `state` = {userId}-{profileId})."""
        result = await self._request("GET", "/users")
        return str((result or {}).get("currentUserId") or "")

    async def list_profile_accounts(self, profile_id: str, category: Optional[str] = None) -> List[Dict]:
        """GET /v1/accounts?profileId=... — the ONLY trustworthy source for 'does this
        accountId belong to this tenant's profile'."""
        params: Dict[str, Any] = {"profileId": profile_id, "category": category, "includeOverLimit": "true"}
        result = await self._request("GET", "/accounts", params=params)
        if isinstance(result, dict):
            return result.get("accounts", result.get("data", []))
        return result if isinstance(result, list) else []

    # ── Queue ──────────────────────────────────────────────────────────────

    async def list_queues(self, profile_id: str) -> Dict[str, Any]:
        return await self._request("GET", "/queue/slots", params={"profileId": profile_id, "all": "true"})

    async def next_queue_slot(self, profile_id: str, queue_id: Optional[str] = None) -> Dict[str, Any]:
        return await self._request("GET", "/queue/next-slot", params={"profileId": profile_id, "queueId": queue_id})

    # ── WhatsApp (senders / numbers) ───────────────────────────────────────

    async def whatsapp_number_info(self, account_id: str) -> Dict[str, Any]:
        """GET /v1/whatsapp/number-info — live from Meta: display name + approval
        (name_status), quality, tier, and the WABA's business_verification_status."""
        return await self._request("GET", "/whatsapp/number-info", params={"accountId": account_id})

    async def whatsapp_display_name(self, account_id: str) -> Dict[str, Any]:
        return await self._request("GET", "/whatsapp/business-profile/display-name", params={"accountId": account_id})

    # ── Ads ────────────────────────────────────────────────────────────────

    async def ads_list_ad_accounts(self, account_id: str, limit: Optional[int] = None) -> List[Dict]:
        """GET /v1/ads/accounts?accountId= — platform ad accounts for an ads connection."""
        result = await self._request("GET", "/ads/accounts", params={"accountId": account_id, "limit": limit})
        if isinstance(result, dict):
            return result.get("accounts", [])
        return result if isinstance(result, list) else []

    async def ads_targeting_search(
        self, account_id: str, q: str, *, dimension: Optional[str] = None, geo_type: Optional[str] = None,
        country_code: Optional[str] = None, ad_account_id: Optional[str] = None, limit: Optional[int] = None,
    ) -> List[Dict]:
        result = await self._request("GET", "/ads/targeting/search", params={
            "accountId": account_id, "q": q, "dimension": dimension, "geoType": geo_type,
            "countryCode": country_code, "adAccountId": ad_account_id, "limit": limit,
        })
        return (result or {}).get("results", []) if isinstance(result, dict) else []

    async def ads_reach_estimate(self, account_id: str, ad_account_id: str, spec: Dict[str, Any]) -> Dict:
        return await self._request("POST", "/ads/targeting/reach-estimate", json_data={
            "accountId": account_id, "adAccountId": ad_account_id, "spec": spec,
        })

    async def ads_list_audiences(
        self, account_id: str, ad_account_id: str, *, platform: Optional[str] = None, type_: Optional[str] = None,
    ) -> List[Dict]:
        result = await self._request("GET", "/ads/audiences", params={
            "accountId": account_id, "adAccountId": ad_account_id, "platform": platform, "type": type_,
        })
        return (result or {}).get("audiences", []) if isinstance(result, dict) else []

    async def ads_create_audience(self, body: Dict[str, Any]) -> Dict:
        return await self._request("POST", "/ads/audiences", json_data=body)

    async def ads_add_audience_users(self, audience_id: str, users: List[Dict[str, str]]) -> Dict:
        """POST /v1/ads/audiences/{id}/users — Zernio SHA256-hashes server-side. Max 10k/request."""
        return await self._request("POST", f"/ads/audiences/{audience_id}/users", json_data={"users": users})

    async def ads_create(self, body: Dict[str, Any], idempotency_key: Optional[str] = None) -> Dict:
        """POST /v1/ads/create (standalone ad: campaign + ad set + ad)."""
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return await self._request("POST", "/ads/create", json_data=body, headers=headers)

    async def ads_preview(self, body: Dict[str, Any]) -> Dict:
        """POST /v1/ads/preview (Meta only) — render creative previews before creating."""
        return await self._request("POST", "/ads/preview", json_data=body)

    async def ads_upload_image(self, account_id: str, ad_account_id: str, image_base64: str, filename: Optional[str] = None) -> Dict:
        body: Dict[str, Any] = {"accountId": account_id, "adAccountId": ad_account_id, "imageBase64": image_base64}
        if filename:
            body["filename"] = filename
        return await self._request("POST", "/ads/images", json_data=body)

    async def ads_list_campaigns(self, **filters: Any) -> Dict:
        return await self._request("GET", "/ads/campaigns", params=_camel(filters))

    async def ads_list_ads(self, **filters: Any) -> Dict:
        return await self._request("GET", "/ads", params=_camel(filters))

    async def ads_set_campaign_status(self, campaign_id: str, status: str, platform: str) -> Dict:
        return await self._request("PUT", f"/ads/campaigns/{campaign_id}/status",
                                   json_data={"status": status, "platform": platform})

    async def ads_set_ad_status(self, ad_id: str, status: str) -> Dict:
        return await self._request("PUT", f"/ads/{ad_id}/status", json_data={"status": status})

    # ── Lead forms / leads (Meta Lead Ads, LinkedIn Lead Gen) ──────────────

    async def lead_forms_list(
        self, account_id: str, *, ad_account_id: Optional[str] = None, limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Dict:
        return await self._request("GET", "/ads/lead-forms", params={
            "accountId": account_id, "adAccountId": ad_account_id, "limit": limit, "cursor": cursor,
        })

    async def lead_forms_create(self, body: Dict[str, Any]) -> Dict:
        return await self._request("POST", "/ads/lead-forms", json_data=body)

    async def leads_list(
        self, *, account_id: Optional[str] = None, form_id: Optional[str] = None,
        ad_account_id: Optional[str] = None, limit: Optional[int] = None, since: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Dict:
        """GET /v1/ads/leads — newest-first, keyset pagination on `cursor`."""
        return await self._request("GET", "/ads/leads", params={
            "accountId": account_id, "formId": form_id, "adAccountId": ad_account_id,
            "limit": limit, "since": since, "cursor": cursor,
        })

    # ── Webhook subscription management ────────────────────────────────────

    async def webhook_settings_get(self) -> Dict:
        return await self._request("GET", "/webhooks/settings")


def _camel(d: Dict[str, Any]) -> Dict[str, Any]:
    """snake_case kwargs -> the camelCase query names Zernio expects."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        parts = k.split("_")
        out[parts[0] + "".join(w.title() for w in parts[1:])] = v
    return out
