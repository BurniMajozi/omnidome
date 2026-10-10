"""SKILL.md-style import/export: YAML-subset frontmatter + markdown instructions.

No YAML dependency: the emitted subset (JSON-quoted scalars, inline lists, inline maps) is also valid YAML, and the parser
accepts only that subset plus plain scalars and '- item' block lists. Anything else is rejected with a clear message.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from services.tenant_memory.skills.spec import MAX_FILE_BYTES, SkillSpec, clean_text


def _q(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def to_markdown(s: dict) -> str:
    lines = ["---", f"name: {_q(s.get('skill_name'))}", f"slug: {_q(s.get('slug'))}",
             f"description: {_q(s.get('description'))}", f"version: {_q(s.get('version') or '1.0.0')}",
             f"category: {_q(s.get('category') or 'operational')}", f"scope: {_q(s.get('scope') or 'tenant')}",
             f"safety_class: {_q(s.get('safety_class') or 'read_only')}",
             f"agents: {_q(list(s.get('target_agent_types') or []))}", f"tools: {_q(list(s.get('tools_required') or []))}",
             f"optional_tools: {_q(list(s.get('tools_optional') or []))}", f"triggers: {_q(list(s.get('triggers') or []))}",
             f"tags: {_q(list(s.get('tags') or []))}", f"roles: {_q(list(s.get('visibility_roles') or []))}"]
    if s.get("changelog"):
        lines.append(f"changelog: {_q(s['changelog'])}")
    if s.get("inputs"):
        lines.append("inputs:")
        lines += [f"  - {_q(i)}" for i in s["inputs"]]
    if s.get("examples"):
        lines.append("examples:")
        lines += [f"  - {_q(e)}" for e in s["examples"]]
    lines += ["---", "", (s.get("instructions") or s.get("guidance_prompt") or "").strip(), ""]
    return "\n".join(lines)


def _scalar(raw: str) -> Any:
    raw = raw.strip()
    if raw == "":
        return ""
    if raw[0] in "[{\"":
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        if raw[0] == "[" and raw[-1] == "]":          # plain-word list: [a, b, c]
            return [p.strip().strip("'\"") for p in raw[1:-1].split(",") if p.strip()]
        if raw[0] == "{" and raw[-1] == "}":          # {name: x, type: string}
            out = {}
            for part in re.split(r",\s*(?=[A-Za-z_]+\s*:)", raw[1:-1]):
                k, _, v = part.partition(":")
                out[k.strip()] = _scalar(v)
            return out
        raise ValueError(f"cannot read value: {raw[:60]}")
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    if raw[0] == "'" and raw[-1] == "'" and len(raw) >= 2:
        return raw[1:-1]
    return raw


def parse_markdown(text: str) -> dict:
    """Parse into a SkillSpec-shaped dict (not yet validated). Raises ValueError on malformed files."""
    if len(text.encode("utf-8", "ignore")) > MAX_FILE_BYTES:
        raise ValueError(f"file is larger than {MAX_FILE_BYTES // 1000} KB")
    text = text.lstrip("﻿").replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not m:
        raise ValueError("missing '---' frontmatter block at the top of the file")
    front, body = m.group(1), m.group(2)
    meta: dict[str, Any] = {}
    key = None
    for line in front.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) or line.lstrip().startswith("- "):
            if key is None or not line.strip().startswith("- "):
                raise ValueError(f"unexpected indented line: {line.strip()[:60]}")
            if not isinstance(meta.get(key), list):
                raise ValueError(f"'{key}' mixes a value and a list")
            meta[key].append(_scalar(line.strip()[2:]))
            continue
        k, sep, v = line.partition(":")
        if not sep:
            raise ValueError(f"cannot read frontmatter line: {line[:60]}")
        key = k.strip().lower()
        meta[key] = _scalar(v) if v.strip() else []
    return {
        "skill_name": meta.get("name"), "slug": meta.get("slug"), "description": meta.get("description"),
        "instructions": clean_text(body), "version": str(meta.get("version") or "1.0.0"),
        "category": meta.get("category") or "operational", "safety_class": meta.get("safety_class") or "read_only",
        "target_agent_types": meta.get("agents") or [], "tools_required": meta.get("tools") or [],
        "tools_optional": meta.get("optional_tools") or [], "triggers": meta.get("triggers") or [],
        "tags": meta.get("tags") or [], "visibility_roles": meta.get("roles") or [],
        "inputs": meta.get("inputs") or [], "examples": meta.get("examples") or [],
        "changelog": meta.get("changelog") or "",
    }


def preview(text: str) -> dict:
    """Parse + validate. {ok, skill, errors[], warnings[]}. Never raises."""
    try:
        raw = parse_markdown(text)
    except ValueError as exc:
        return {"ok": False, "skill": None, "errors": [str(exc)], "warnings": []}
    try:
        spec = SkillSpec.model_validate(raw)
    except ValidationError as exc:
        errs = []
        for e in exc.errors():
            loc = ".".join(str(p) for p in e.get("loc", ()) if p != "__root__")
            msg = str(e.get("msg", "")).removeprefix("Value error, ")
            errs.append(f"{loc}: {msg}" if loc else msg)
        return {"ok": False, "skill": raw, "errors": errs, "warnings": []}
    return {"ok": True, "skill": spec.model_dump(), "errors": [],
            "warnings": spec.warnings() + ["imported skills are created as drafts and must be activated by an admin"]}
