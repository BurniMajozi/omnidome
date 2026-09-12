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

    # ── Social Account Connection ──────────────────────────────────────

    async def get_connect_url(self, platform: str) -> str:
        """Get OAuth connect URL for a platform.

        Spec note: GET /v1/connect/{platform} requires profileId query.
        Without a profile id we return "" so callers degrade gracefully.
        """
        profile_id = os.getenv("ZERNIO_PROFILE_ID", "")
        if not profile_id:
            logger.warning("ZERNIO_PROFILE_ID not set — connect URL unavailable")
            return ""
        result = await self._request(
            "GET", f"/connect/{platform}", params={"profileId": profile_id}
        )
        if isinstance(result, dict):
            return result.get("connect_url", result.get("url", ""))
        return str(result)

    async def disconnect_account(self, account_id: str) -> Dict:
        """Disconnect a social media account."""
        return await self._request("DELETE", f"/accounts/{account_id}")

    # ── Analytics ──────────────────────────────────────────────────────

    async def get_analytics(
        self,
        platform: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict:
        """Get analytics data."""
        params: Dict[str, Any] = {}
        if platform:
            params["platform"] = platform
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return await self._request("GET", "/analytics", params=params)
