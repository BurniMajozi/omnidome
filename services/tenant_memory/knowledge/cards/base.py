"""Knowledge card model, markdown rendering and the PII field policy.

A card is an Obsidian-style markdown note: YAML frontmatter (provenance, as_of, tags) then a
human-readable body. Cards carry context, history and narrative; they may include figures
"as of" a date, but figures for decks/answers must still come from governed SQL.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Optional

from services.tenant_memory.knowledge.kdata import Edge

# Never indexed, whatever a builder or an env override says.
NEVER_INDEX = frozenset({
    "password", "password_hash", "hashed_password", "secret", "api_key", "token", "access_token", "refresh_token",
    "paystack_email_token", "paystack_customer_code", "paystack_subscription_code", "id_number", "passport",
    "bank_account", "account_number_bank", "card_number", "cvv", "iban", "swift", "email", "phone", "phone_normalized",
    "billing_email", "address", "street_address", "idempotency_key", "paystack_ref", "reference", "radius_password",
    "guidance_prompt",
})

# Module -> (visibility, required_roles). Admin roles always pass. Override with KNOWLEDGE_MODULE_ACCESS (JSON).
DEFAULT_MODULE_ACCESS: dict[str, tuple[str, list[str]]] = {
    "billing": ("team", ["billing", "finance", "billing_admin", "finance_manager", "accountant"]),
    "finance": ("team", ["finance", "finance_manager", "accountant"]),
    "hr": ("team", ["hr", "hr_manager", "hr_admin"]),
}


def module_access(module: str) -> tuple[str, list[str]]:
    raw = os.getenv("KNOWLEDGE_MODULE_ACCESS", "").strip()
    table = dict(DEFAULT_MODULE_ACCESS)
    if raw:
        try:
            for k, v in json.loads(raw).items():
                table[k] = (v.get("visibility", "team"), [r.lower() for r in v.get("roles", [])])
        except (ValueError, AttributeError):
            pass
    return table.get(module, ("tenant", []))


def allowed_fields(source: str, default: Iterable[str]) -> frozenset:
    """Per-builder allow-list. KNOWLEDGE_FIELDS_<SOURCE>=a,b,c can only NARROW the default."""
    fields = set(default)
    override = os.getenv(f"KNOWLEDGE_FIELDS_{source.upper()}", "").strip()
    if override:
        fields &= {f.strip() for f in override.split(",") if f.strip()}
    return frozenset(fields - NEVER_INDEX)


def pick(row: dict, allowed: frozenset) -> dict:
    return {k: v for k, v in row.items() if k in allowed}


def fmt_dt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.isoformat()
    return str(v)[:10]


def fmt_ts(v: Any) -> str:
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return fmt_dt(v)


def money(v: Any) -> str:
    try:
        return f"R{Decimal(str(v or 0)):,.2f}"
    except Exception:  # noqa: BLE001
        return "R0.00"


def initial_name(first: Any, last: Any) -> str:
    """'Thandi M.' - enough to recognise a person in a conversation, not enough to identify them alone."""
    f = (str(first or "").strip() or "Customer")
    l = str(last or "").strip()
    return f"{f} {l[0].upper()}." if l else f


def _yaml_scalar(v: Any) -> str:
    s = str(v)
    return json.dumps(s) if re.search(r"[:#\[\]{},&*!|>'\"%@`]|^\s|\s$|^$", s) else s


def frontmatter(source_type: str, source_id: str, module: str, as_of: Any, tags: list[str], extra: Optional[dict] = None) -> str:
    lines = ["---", f"source: {_yaml_scalar(source_type)}", f"source_id: {_yaml_scalar(source_id)}", f"module: {_yaml_scalar(module)}"]
    for k, v in sorted((extra or {}).items()):
        if v not in (None, ""):
            lines.append(f"{k}: {_yaml_scalar(v)}")
    lines.append(f"as_of: {fmt_ts(as_of)}")
    lines.append("tags: [" + ", ".join(_yaml_scalar(t) for t in sorted(set(tags))) + "]")
    lines.append("---")
    return "\n".join(lines) + "\n"


_VOLATILE = re.compile(r"^(as_of|generated):.*\n", re.M)


def stable_text(markdown: str) -> str:
    """Markdown minus volatile frontmatter lines: what the content hash is computed over, so a rebuild
    that changes only the timestamp never triggers a re-embedding."""
    if markdown.startswith("---\n"):
        end = markdown.find("\n---\n", 4)
        if end != -1:
            return _VOLATILE.sub("", markdown[: end + 5]) + markdown[end + 5:]
    return markdown


@dataclass
class Card:
    source_type: str
    source_id: str
    module: str
    title: str
    markdown: str
    as_of: Optional[datetime] = None
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5
    source_ref: dict = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    valid_to: Optional[datetime] = None
    owner_id: Optional[str] = None
    visibility: Optional[str] = None            # None -> module default
    required_roles: Optional[list[str]] = None

    def access(self) -> tuple[str, list[str]]:
        vis, roles = module_access(self.module)
        return (self.visibility or vis, self.required_roles if self.required_roles is not None else roles)


def link(kind: str, ident: str, label: str = "") -> str:
    """Obsidian-style wiki link used for relationships inside the body."""
    return f"[[{kind}:{ident}|{label}]]" if label else f"[[{kind}:{ident}]]"
