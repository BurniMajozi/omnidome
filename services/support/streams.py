"""In-memory SSE fan-out for technician job dispatch.

ONE bounded queue PER CONNECTION. Process-local, so this service must run a single uvicorn worker
(docker-compose.local.yml sets --workers 1; the Dockerfile default of 2 would split pushed jobs between
two processes). For several workers/instances replace this with Postgres LISTEN/NOTIFY or Redis pub/sub.
"""

from __future__ import annotations

import asyncio
from typing import Dict, List

active_streams: Dict[str, List[asyncio.Queue]] = {}


async def push(tenant_id: str, event: str, data: dict) -> None:
    for q in list(active_streams.get(tenant_id, [])):
        try:
            q.put_nowait({"event": event, "data": data})
        except asyncio.QueueFull:
            pass  # slow consumer: it re-syncs from initial_state on reconnect


async def notify_new_ticket(tenant_id: str, ticket_dict: dict) -> None:
    await push(tenant_id, "new_ticket", ticket_dict)


async def notify_ticket_update(tenant_id: str, ticket_dict: dict) -> None:
    await push(tenant_id, "ticket_update", ticket_dict)
