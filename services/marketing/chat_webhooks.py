"""Zernio Webhook Handler + Chat Engine for OmniDome Marketing Service
------------------------------------------------------------------
Handles incoming Zernio webhooks (messages, comments, reactions),
normalizes them into our SocialInboxMessage model, and provides
auto-reply / ticket-creation / routing logic.

Webhook events handled:
  - message.received  → new DM/comment from customer
  - comment.received  → new comment on a post
  - reaction.received → emoji reaction (WhatsApp/Telegram)

Support bridge contract (verified against services/support/main.py):
  POST {SUPPORT_SERVICE_URL}/tickets  (NOT /api/support/tickets)
  body: { customer_id: UUID, subject, description, category, priority }
  tenant: propagated from the caller via X-Tenant-Id header (never hardcoded).
  customer_id: social senders have no CRM record, so the caller passes a
  per-tenant SOCIAL_TICKET_CUSTOMER_ID env UUID (a real contacts row) or the
  bridge is skipped gracefully.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from services.marketing.zernio_client import ZernioClient

logger = logging.getLogger(__name__)


# ── Webhook Normalizer ─────────────────────────────────────────────────

def extract_event_meta(event: Dict[str, Any]) -> tuple[str, str]:
    """Pull (event_type, platform) from a Zernio webhook payload.

    Single source of truth for the real payload shape (Sep 2026): the event
    type is the top-level ``event`` key and the platform is nested at
    ``message.platform``. Legacy flat keys (``event_type``, top-level
    ``platform``) are accepted as fallbacks. The webhook route and the
    normalizer both call this so they can never read the payload differently.
    """
    event_type = event.get("event") or event.get("event_type") or "unknown"
    raw_msg = event.get("message")
    msg = raw_msg if isinstance(raw_msg, dict) else {}
    platform = (msg.get("platform") or event.get("platform") or "unknown")
    return event_type, str(platform).lower()


def normalize_webhook_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a Zernio webhook payload into our SocialInboxMessage schema.

    REAL Zernio webhook payload shape (message.received, Sep 2026):
    {
      "id": "8dafe19b-24b2-4b75-a862-93d9127c882e",
      "event": "message.received",
      "message": {
        "id": "6aa5920dc7f9323ddc0ea8c2",
        "conversationId": "6aa57f8a726ebfe037e0851e",
        "platform": "telegram",
        "platformMessageId": "25393",
        "direction": "incoming",
        "text": "Hey testing again.",
        "attachments": [],
        "sender": {
          "id": "8975916657",
          "name": "Bene Majozi",
          "contactId": "6aa57f8ad6acdc682e22771e"
        },
        "sentAt": "2026-09-12T17:55:24.000Z",
        "isRead": false,
        "sentVia": null
      },
      "conversation": { ... },
      "account": { ... },
      "timestamp": "2026-09-12T17:55:25.157Z"
    }
    """
    # Event type ("event" top-level) and platform ("message.platform") come
    # from the shared extractor so this can never drift from the route.
    event_type, platform = extract_event_meta(event)
    # message/sender may be missing or a non-dict for non-message events.
    raw_msg = event.get("message")
    msg = raw_msg if isinstance(raw_msg, dict) else {}
    raw_sender = msg.get("sender")
    sender = raw_sender if isinstance(raw_sender, dict) else {}

    # Map Zernio event types to our message_type
    type_map = {
        "message.received": "DM",
        "comment.received": "COMMENT",
        "mention.received": "MENTION",
        "review.received": "REVIEW",
    }

    # Map Zernio platforms to our platform enum
    platform_map = {
        "instagram": "instagram",
        "facebook": "facebook",
        "twitter": "twitter",
        "x": "twitter",
        "telegram": "telegram",
        "whatsapp": "whatsapp",
        "bluesky": "bluesky",
        "reddit": "reddit",
        "tiktok": "tiktok",
        "linkedin": "linkedin",
        "youtube": "youtube",
        "pinterest": "pinterest",
        "threads": "threads",
        "snapchat": "snapchat",
        "googlebusiness": "googlebusiness",
    }

    return {
        "message_type": type_map.get(event_type, "DM"),
        "platform": platform_map.get(platform, platform),
        "external_id": msg.get("id", msg.get("platformMessageId", event.get("id", ""))),
        "sender_name": sender.get("name", sender.get("handle", "Unknown")),
        "sender_handle": sender.get("handle", sender.get("id", "")),
        "sender_profile_url": "",
        "content": msg.get("text", msg.get("content", "")),
        "parent_id": None,
        "status": "UNREAD",
        "sentiment": _detect_sentiment(msg.get("text", msg.get("content", ""))),
        "attachments": msg.get("attachments", []),
        "conversation_id": msg.get("conversationId", event.get("conversation_id")),
        "raw_payload": event,
        "received_at": msg.get("sentAt", event.get("timestamp", datetime.now(timezone.utc).isoformat())),
    }


def _detect_sentiment(text: str) -> Optional[str]:
    """Simple keyword-based sentiment detection (placeholder for ML model)."""
    if not text:
        return "NEUTRAL"
    text_lower = text.lower()
    positive = ["thanks", "thank you", "great", "awesome", "love", "good", "excellent", "happy", "perfect", "amazing"]
    negative = ["bad", "terrible", "worst", "hate", "angry", "frustrated", "broken", "issue", "problem", "complaint", "refund", "cancel"]

    pos_count = sum(1 for w in positive if w in text_lower)
    neg_count = sum(1 for w in negative if w in text_lower)

    if pos_count > neg_count:
        return "POSITIVE"
    elif neg_count > pos_count:
        return "NEGATIVE"
    return "NEUTRAL"


def normalize_reaction_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a Zernio reaction.received webhook payload.

    Real Zernio events nest their fields under a ``message`` object (same
    envelope as message.received), so read those first and fall back to the
    legacy flat top-level keys. Platform comes from the shared extractor so
    it resolves identically to messages (nested ``message.platform`` first).
    """
    _, platform = extract_event_meta(event)
    raw_msg = event.get("message")
    msg = raw_msg if isinstance(raw_msg, dict) else {}
    raw_sender = msg.get("sender", event.get("sender"))
    sender = raw_sender if isinstance(raw_sender, dict) else {}
    emoji = msg.get("emoji", event.get("emoji", ""))
    return {
        "event_type": "reaction.received",
        "platform": platform,
        "emoji": emoji,
        "raw_emoji": msg.get("rawEmoji", event.get("rawEmoji", emoji)),
        "added": msg.get("added", event.get("added", True)),
        "message_id": msg.get("messageId", msg.get("id", event.get("messageId", event.get("message_id", "")))),
        "conversation_id": msg.get("conversationId", event.get("conversation_id")),
        "sender": sender,
        "raw_payload": event,
    }


# ── Chat Engine ────────────────────────────────────────────────────────

class ChatEngine:
    """
    Processes incoming social messages and routes them to:
    1. Auto-reply (comment automations)
    2. Support ticket creation (escalation)
    3. Agent notification (call centre integration)
    """

    def __init__(
        self,
        db_session_factory,
        zernio_client: Optional[ZernioClient] = None,
        tenant_id: Optional[uuid.UUID] = None,
        support_url: Optional[str] = None,
        ticket_customer_id: Optional[uuid.UUID] = None,
    ):
        self.db = db_session_factory
        self.zernio = zernio_client
        # Tenant propagated from the webhook caller — never hardcoded.
        self.tenant_id = tenant_id
        self.support_url = support_url or os.getenv("SUPPORT_SERVICE_URL", "http://support:8008")
        raw_customer = os.getenv("SOCIAL_TICKET_CUSTOMER_ID", "")
        self.ticket_customer_id = ticket_customer_id
        if self.ticket_customer_id is None and raw_customer:
            try:
                self.ticket_customer_id = uuid.UUID(raw_customer)
            except ValueError:
                logger.warning("SOCIAL_TICKET_CUSTOMER_ID is not a valid UUID — ticket bridge disabled")

    async def process_inbound_message(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process an inbound message from Zernio.
        Returns action taken: "auto_replied", "ticket_created", "queued", "ignored"
        """
        normalized = normalize_webhook_event(event)
        platform = normalized["platform"]
        content = normalized["content"]
        sender = normalized["sender_name"]

        logger.info(f"Processing {platform} message from {sender}: {content[:100]}")

        # 1. Check comment automations
        auto_reply = await self._check_automations(platform, content)
        if auto_reply:
            if self.zernio:
                try:
                    await self.zernio.send_inbox_message(
                        conversation_id=normalized.get("conversation_id", ""),
                        content=auto_reply,
                    )
                    logger.info(f"Auto-replied on {platform}: {auto_reply[:50]}")
                    return {"action": "auto_replied", "message": auto_reply}
                except Exception as e:
                    logger.error(f"Auto-reply failed: {e}")

        # 2. Check if this should escalate to a ticket
        if self._should_escalate(content):
            ticket_id = await self._create_ticket(normalized)
            if ticket_id:
                return {"action": "ticket_created", "ticket_id": ticket_id}

        # 3. Queue for agent review
        return {"action": "queued", "message_id": normalized.get("external_id")}

    async def _check_automations(self, platform: str, content: str) -> Optional[str]:
        """Check if any comment automation matches this message."""
        content_lower = content.lower()

        from services.marketing.database import CommentAutomation

        async with self.db() as session:
            from sqlalchemy import select
            stmt = select(CommentAutomation).where(
                CommentAutomation.is_active == True,
            )
            if platform:
                # Filter by account platform (simplified — match all active for now)
                pass
            result = await session.execute(stmt)
            automations = result.scalars().all()

            for auto in automations:
                keywords = auto.trigger_keywords or []
                if auto.trigger_type == "ALL_COMMENTS":
                    return auto.response_template
                elif auto.trigger_type == "KEYWORD":
                    if any(kw.lower() in content_lower for kw in keywords):
                        return auto.response_template
                elif auto.trigger_type == "FIRST_COMMENT":
                    # Simplified — would check if sender has commented before
                    if any(kw.lower() in content_lower for kw in keywords):
                        return auto.response_template

        return None

    def _should_escalate(self, content: str) -> bool:
        """Determine if a message should be escalated to a support ticket."""
        escalation_keywords = [
            "complaint", "refund", "cancel", "urgent", "escalate",
            "manager", "supervisor", "break", "not working", "down",
            "outage", "billing", "overcharge", "dispute",
        ]
        content_lower = content.lower()
        return any(kw in content_lower for kw in escalation_keywords)

    async def _create_ticket(self, normalized: Dict) -> Optional[str]:
        """Create a support ticket from a social message.

        Verified contract: POST {support_url}/tickets with
        { customer_id, subject, description, category, priority }.
        Returns None (graceful skip) when tenant or customer id is unknown.
        """
        if not self.tenant_id or not self.ticket_customer_id:
            logger.info("Ticket bridge skipped: tenant or SOCIAL_TICKET_CUSTOMER_ID not set")
            return None
        sender = normalized.get("sender_name", "Unknown")
        handle = normalized.get("sender_handle", "")
        from_line = f"From: {sender} (@{handle})" if handle else f"From: {sender}"
        description_lines = [
            f"Platform: {normalized.get('platform', 'unknown')}",
            from_line,
            f"External ID: {normalized.get('external_id', '')}",
            "",
            normalized.get("content", ""),
        ]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.support_url}/tickets",
                    json={
                        "customer_id": str(self.ticket_customer_id),
                        "subject": f"Social message from {sender} on {normalized.get('platform', 'unknown')}",
                        "description": "\n".join(description_lines),
                        "category": "SOCIAL",
                        "priority": "HIGH",
                    },
                    headers={"X-Tenant-Id": str(self.tenant_id)},
                )
                if resp.status_code == 201:
                    return resp.json().get("id")
                logger.warning(f"Ticket creation returned {resp.status_code}")
        except Exception as e:
            logger.error(f"Ticket creation failed: {e}")
        return None

    async def handle_reaction(self, event):
        """Handle a reaction event."""
        normalized = normalize_reaction_event(event)
        logger.info("Reaction on %s", normalized.get("platform"))
        return {"action": "logged", "reaction": normalized}
