"""Skill schema, validation and text safety scan (docs/skills.md)."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from services.tenant_memory.skills import catalog

MAX_INSTRUCTIONS = 12_000
MAX_DESCRIPTION = 800
MAX_FILE_BYTES = 40_000
SEMVER = re.compile(r"^\d{1,4}\.\d{1,4}\.\d{1,4}$")
TOOL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-]{1,100}$")
AGENT_NAME = re.compile(r"^[a-z][a-z0-9_\-]{1,79}$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9\-]{1,78}[a-z0-9]$")


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:80].strip("-") or "skill"


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


# -- text safety scan ---------------------------------------------------------

_BLOCK = [
    (r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions|rules|prompts|messages)", "tries to override earlier instructions"),
    (r"disregard\s+(all\s+|any\s+|the\s+|your\s+)?(previous\s+|prior\s+|above\s+|safety\s+|system\s+)?(instructions|rules|guardrails|policies)", "tries to disregard rules"),
    (r"(reveal|print|show|output|leak|dump|repeat)\s+(me\s+)?(your\s+|the\s+)?(system\s+prompt|hidden\s+prompt|api[\s_-]?keys?|secrets?|passwords?|credentials|tokens?)", "asks to reveal secrets or the system prompt"),
    (r"(send|post|upload|forward|exfiltrate|transmit|leak)\b[^\n.]{0,80}(https?://|webhook|ftp://)", "sends data to an external address"),
    (r"!\[[^\]]*\]\(\s*https?://", "markdown image beacon (can leak data in the URL)"),
    (r"<\s*(script|iframe|object|embed|img|link|style)\b", "embedded HTML that could run or fetch content"),
    (r"(developer|jailbreak|god|dan)\s+mode|you\s+are\s+now\s+(?!a\s+helpful)", "persona or jailbreak phrasing"),
    (r"(skip|bypass|disable|ignore|circumvent)\s+(the\s+)?(approval|approvals|human\s+review|guardrails?|safety|permission|tool\s+allow)", "tries to bypass approvals or guardrails"),
    (r"(without|no)\s+(asking|human\s+approval|approval|confirmation)\s+(send|delete|refund|pay|transfer|publish)", "acts without approval"),
]
_WARN = [
    (r"https?://", "contains a URL"),
    (r"<!--", "contains an HTML comment (hidden text)"),
    (r"(api[\s_-]?key|password|secret|bearer\s+token)", "mentions credentials"),
    (r"\b(delete|drop|truncate|wipe)\b", "mentions destructive actions"),
]
_HIDDEN = re.compile("[​-‏‪-‮⁠-⁤﻿]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def scan_text(text: str) -> tuple[list[str], list[str]]:
    """(blockers, warnings) for free text that will be shown to a model."""
    blockers: list[str] = []
    warnings: list[str] = []
    t = str(text or "")
    if _HIDDEN.search(t):
        blockers.append("contains hidden or bidirectional-override characters")
    for pat, why in _BLOCK:
        if re.search(pat, t, re.IGNORECASE):
            blockers.append(why)
    for pat, why in _WARN:
        if re.search(pat, t, re.IGNORECASE):
            warnings.append(why)
    return sorted(set(blockers)), sorted(set(warnings))


def clean_text(text: str) -> str:
    return _CONTROL.sub("", str(text or "")).replace("\r\n", "\n").strip()


# -- models -------------------------------------------------------------------

class SkillInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=60, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    type: Literal["string", "number", "integer", "boolean", "date", "list"] = "string"
    description: str = Field(default="", max_length=300)
    required: bool = False


class SkillExample(BaseModel):
    title: str = Field(default="", max_length=120)
    input: str = Field(default="", max_length=600)
    output: str = Field(default="", max_length=1500)


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        v = str(v).strip()
        if v and v not in out:
            out.append(v)
    return out


class SkillSpec(BaseModel):
    """Validated, normalised skill content (everything an author controls)."""
    skill_name: str = Field(..., min_length=2, max_length=120)
    slug: Optional[str] = None
    description: str = Field(..., min_length=10, max_length=MAX_DESCRIPTION)
    instructions: str = Field(..., min_length=20, max_length=MAX_INSTRUCTIONS)
    category: str = Field(default="operational", max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=12)
    target_agent_types: list[str] = Field(default_factory=list, max_length=20)
    source_agent_type: str = Field(default="shared", max_length=80)
    tools_required: list[str] = Field(default_factory=list, max_length=20)
    tools_optional: list[str] = Field(default_factory=list, max_length=20)
    inputs: list[SkillInput] = Field(default_factory=list, max_length=12)
    triggers: list[str] = Field(default_factory=list, max_length=20)
    examples: list[SkillExample] = Field(default_factory=list, max_length=5)
    safety_class: Literal["read_only", "drafts_only", "can_act"] = "read_only"
    version: str = "1.0.0"
    changelog: str = Field(default="", max_length=600)
    visibility_roles: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("skill_name", "description", "instructions", "changelog", mode="before")
    @classmethod
    def _clean(cls, v: Any) -> Any:
        return clean_text(v) if isinstance(v, str) else v

    @field_validator("tags", "triggers", "target_agent_types", "tools_required", "tools_optional",
                     "visibility_roles", mode="before")
    @classmethod
    def _listify(cls, v: Any) -> Any:
        if v is None:
            return []
        if isinstance(v, str):
            v = re.split(r"[,\n]", v)
        if isinstance(v, (list, tuple)):
            return _dedupe([clean_text(x)[:200] for x in v])
        return v

    @field_validator("version")
    @classmethod
    def _semver(cls, v: str) -> str:
        if not SEMVER.match(v):
            raise ValueError("version must look like 1.2.0")
        return v

    @field_validator("target_agent_types")
    @classmethod
    def _agents(cls, v: list[str]) -> list[str]:
        bad = [a for a in v if not AGENT_NAME.match(a)]
        if bad:
            raise ValueError(f"invalid agent type name(s): {', '.join(bad)}")
        return v

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[a-z][a-z0-9_\-]{1,79}$", v):
            raise ValueError("category must be a short lowercase word")
        return v

    @model_validator(mode="after")
    def _check(self) -> "SkillSpec":
        self.slug = slugify(self.slug or self.skill_name)
        if not SLUG.match(self.slug):
            raise ValueError("slug must be lowercase letters, digits and dashes")
        problems: list[str] = []
        for name in self.tools_required:
            if not TOOL_NAME.match(name):
                problems.append(f"'{name}' is not a valid tool name")
            elif name in catalog.SOFT_TOOLS:
                problems.append(f"'{name}' is not in the registry yet; list it under optional tools")
            elif name not in catalog.KNOWN_TOOLS:
                problems.append(f"unknown tool '{name}'")
        for name in self.tools_optional:
            if not TOOL_NAME.match(name):
                problems.append(f"'{name}' is not a valid optional tool name")
            elif name not in catalog.KNOWN_TOOLS and name not in catalog.SOFT_TOOLS:
                problems.append(f"unknown optional tool '{name}'")
        if self.safety_class != "can_act":
            acts = [n for n in self.tools_required if catalog.KNOWN_TOOLS.get(n, (False, False))[0]]
            if acts:
                problems.append(f"requires tools that change data ({', '.join(acts)}); set safety class to can_act")
        if len({i.name for i in self.inputs}) != len(self.inputs):
            problems.append("input names must be unique")
        for label, body in (("name", self.skill_name), ("description", self.description),
                            ("instructions", self.instructions), ("triggers", " ".join(self.triggers)),
                            ("changelog", self.changelog)):
            problems += [f"{label} {x}" for x in scan_text(body)[0]]
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def warnings(self) -> list[str]:
        out: list[str] = []
        for label, body in (("instructions", self.instructions), ("description", self.description)):
            out += [f"{label} {w}" for w in scan_text(body)[1]]
        if estimate_tokens(self.instructions) > 900:
            out.append("instructions are long (over about 900 tokens) and may be trimmed at run time")
        if self.safety_class == "can_act":
            out.append("can_act skill: needs an admin to activate; actions still go through approvals")
        return out

    def content_hash(self) -> str:
        data = self.model_dump(exclude={"changelog"})
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:32]
