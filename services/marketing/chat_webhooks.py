"""
Zernio Webhook Handler + Chat Engine for OmniDome Marketing Service
------------------------------------------------------------------
Handles incoming Zernio webhooks (messages, comments, reactions),
normalizes them into our SocialInboxMessage model, and provides
auto-reply / ticket-creation / routing logic.

Webhook events handled:
  - message.received  → new DM/comment from customer
  - comment.received  → new comment on a post
  - reaction.received → emoji reaction (WhatsApp/Telegram)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.marketing.zernio_client import ZernioClient

logger = logging.getLogger(__name__)


# ── Webhook Normalizer ─────────────────────────────────────────────────

def normalize_webhook_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a Zernio webhook payload into our SocialInboxMessage schema.

    Zernio webhook payload shape (message.received):
    {
      "event_type": "message.received",
      "platform": "instagram",
      "conversation_id": "conv_abc",
      "message_id": "msg_xyz",
      "sender": {
        "name": "John Doe",
        "handle": "johndoe",
        "profile_url": "https://...",
        "phoneNumber": "+27...",       # WhatsApp only
        "instagramProfile": { ... },   # IG only
      },
      "content": "Hello, I need help",
      "attachments": [{"type": "image", "url": "https://..."}],
      "parent_id": null,  # for threaded replies
      "timestamp": "2026-07-02T10:00:00Z",
    }
    """
    event_type = event.get("event_type", "unknown")
    platform = event.get("platform", "unknown")
    sender = event.get("sender", {})

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
        "external_id": event.get("message_id", event.get("id", "")),
        "sender_name": sender.get("name", sender.get("handle", "Unknown")),
        "sender_handle": sender.get("handle", ""),
        "sender_profile_url": sender.get("profile_url", ""),
        "content": event.get("content", event.get("text", "")),
        "parent_id": event.get("parent_id"),
        "status": "UNREAD",
        "sentiment": _detect_sentiment(event.get("content", "")),
        "attachments": event.get("attachments", []),
        "conversation_id": event.get("conversation_id"),
        "raw_payload": event,
        "received_at": event.get("timestamp", datetime.utcnow().isoformat()),
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
    """Normalize a Zernio reaction.received webhook payload."""
    return {
        "event_type": "reaction.received",
        "platform": event.get("platform", "unknown"),
        "emoji": event.get("emoji", ""),
        "raw_emoji": event.get("rawEmoji", event.get("emoji", "")),
        "added": event.get("added", True),
        "message_id": event.get("messageId", event.get("message_id", "")),
        "conversation_id": event.get("conversation_id"),
        "sender": event.get("sender", {}),
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

    def __init__(self, db_session_factory, zernio_client: Optional[ZernioClient] = None):
        self.db = db_session_factory
        self.zernio = zernio_client

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
        """Create a support ticket from a social message."""
        try:
            import httpx
            support_url = "http://support:8008"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{support_url}/api/support/tickets",
                    json={
                        "subject": f"Social: {normalized['message_type']} from {normalized['sender_name']} on {normalized['platform']}",
                        "description": f"Platform: {normalized['platform']}\nFrom: {normalized['sender_name']} (@{normalized['sender_handle']})\n\n{normalized['content']}",
                        "priority": "high",
                        "source": "SOCIAL",
                        "source_id": normalized.get("external_id", ""),
                    },
                    headers={"x-tenant-id": "00000000-0000-0000-0000-000000000001"},
                )
                if resp.status_code == 201:
                    return resp.json().get("id")
        except Exception as e:
            logger.error(f"Ticket creation failed: {e}")
        return None

    async def handle_reaction(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a reaction event."""
        normalized = normalize_reaction_event(event)
        logger.info(
            f"Reaction: {normalized.get('emoji')} {'added' if normalized.get('added') else 'removed'} "
            f"on {normalized.get('platform')}"
        )
        return {"action": "logged", "reaction": normalized}
