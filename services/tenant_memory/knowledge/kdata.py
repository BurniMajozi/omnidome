"""Plain data types shared by the store adapters, indexer and retrieval."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

IMPORTANCE = {"low": 0.25, "normal": 0.5, "high": 0.75, "critical": 1.0}
VISIBILITIES = ("private", "team", "tenant", "system")
ADMIN_ROLES = {"admin", "org_admin", "tenant_admin", "owner"}


def content_hash(text: str, model: str = "") -> str:
    return hashlib.sha256(f"{model}\x1f{text}".encode("utf-8")).hexdigest()


@dataclass
class AccessScope:
    """Who is asking. Applied in SQL and again in Python (defence in depth)."""
    tenant_id: str
    user_id: Optional[str] = None
    roles: frozenset = frozenset()
    permissions: frozenset = frozenset()
    is_admin: bool = False
    # Panel gate. None = not applied (admins, and trusted in-process callers such as the indexer/tests).
    # A frozenset is the exact list of modules the caller may read; request paths always build one (access.py),
    # so a missing x-modules fails closed to the always-allowed modules only.
    modules: Optional[frozenset] = None

    @classmethod
    def from_ctx(cls, ctx: Any) -> "AccessScope":
        from services.tenant_memory.knowledge.access import build_scope
        return build_scope(ctx)

    def allows(self, c: "Chunk") -> bool:
        """The single source of truth for visibility; the SQL clause mirrors it."""
        if str(c.tenant_id) != self.tenant_id:
            return False
        if c.visibility == "private" and (c.owner_id is None or c.owner_id != self.user_id):
            return False                      # private means the owner only, admins included
        if self.modules is not None and (c.module or "general").split(".")[0] not in self.modules:
            return False                      # panel gate (deny-by-default)
        if self.is_admin:
            return True
        if c.required_permission and c.required_permission.lower() not in self.permissions:
            return False
        if c.required_roles and not (self.roles & {r.lower() for r in c.required_roles}):
            return False
        return True


@dataclass
class Edge:
    src_type: str
    src_id: str
    dst_type: str
    dst_id: str
    relation: str
    weight: float = 1.0
    as_of: Optional[datetime] = None


@dataclass
class Chunk:
    tenant_id: str
    source_type: str
    source_id: str
    chunk_no: int
    module: str
    title: str
    markdown: str
    content_hash: str
    source_ref: dict = field(default_factory=dict)
    visibility: str = "tenant"
    required_roles: list = field(default_factory=list)
    required_permission: Optional[str] = None
    owner_id: Optional[str] = None
    as_of: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    importance: float = 0.5
    tags: list = field(default_factory=list)
    embedding: Optional[list] = None
    embedding_model: Optional[str] = None
    id: Optional[str] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    @property
    def key(self) -> tuple:
        return (self.tenant_id, self.source_type, self.source_id, self.chunk_no)


@dataclass
class Filters:
    modules: Optional[list] = None
    source_types: Optional[list] = None
    tags: Optional[list] = None
    since: Optional[datetime] = None      # as_of >= since
    until: Optional[datetime] = None      # as_of <= until
    min_importance: Optional[float] = None
    include_expired: bool = False         # valid_to in the past


@dataclass
class Hit:
    chunk: Chunk
    score: float = 0.0
    vector_rank: Optional[int] = None
    text_rank: Optional[int] = None
    via: str = "search"                   # search | graph
