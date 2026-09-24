"""Repair malformed tool-call arguments from LLMs (spec A1 `tool-call-repair`).

Ported in spirit from Tencent/WeKnora `internal/agent/tools/json_repair.go`
(MIT License, Copyright (C) 2025 Tencent). Rewritten for Python.

Models, especially small/free ones, emit tool arguments with single quotes,
unquoted keys, Python literals, trailing commas, regex backslashes that are not
valid JSON escapes, raw newlines, extra tokens after the object, or arguments
cut off at the output-token limit. Everything but the last is repaired. Cut-off
arguments parse only after closing them, and then hold half a query or half a
body, so callers must refuse them instead of running the tool.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

_VALID_ESCAPES = set('"\\/bfnrtu')
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]*")
_PY_LITERALS = {"True": "true", "False": "false", "None": "null"}

CUT_OFF_ERROR = (
    "Tool arguments were cut off before they ended (output limit). "
    "Call the tool again with complete, shorter arguments."
)
INVALID_ERROR = "Tool arguments are not a valid JSON object. Call the tool again with a JSON object."


def _last_significant(out: list[str]) -> str:
    for piece in reversed(out):
        stripped = piece.strip()
        if stripped:
            return stripped[-1]
    return ""


def _drop_trailing_comma(out: list[str]) -> None:
    while out and not out[-1].strip():
        out.pop()
    if out and out[-1] == ",":
        out.pop()


def repair_json(raw: str) -> tuple[str, bool]:
    """Return (repaired JSON text, was_truncated). Idempotent on valid JSON."""
    s = (raw or "").strip()
    if not s:
        return "{}", False

    out: list[str] = []
    stack: list[str] = []
    in_str = False
    quote = ""
    i, n = 0, len(s)

    while i < n:
        c = s[i]
        if in_str:
            if c == "\\":
                if i + 1 >= n:                      # dangling backslash at the end
                    out.append("\\\\")
                    i += 1
                    continue
                nxt = s[i + 1]
                if quote == "'" and nxt == "'":     # \' inside a single-quoted string
                    out.append("'")
                elif nxt in _VALID_ESCAPES:
                    out.append(c + nxt)
                else:                               # e.g. \d \. \+ from an un-escaped regex
                    out.append("\\\\" + nxt)
                i += 2
                continue
            if c == quote:
                out.append('"')
                in_str = False
            elif c == '"':                          # double quote inside a single-quoted string
                out.append('\\"')
            elif c == "\n":
                out.append("\\n")
            elif c == "\r":
                out.append("\\r")
            elif c == "\t":
                out.append("\\t")
            else:
                out.append(c)
            i += 1
            continue

        if c in ('"', "'"):
            in_str, quote = True, c
            out.append('"')
            i += 1
            continue
        if c in "{[":
            stack.append("}" if c == "{" else "]")
            out.append(c)
            i += 1
            continue
        if c in "}]":
            _drop_trailing_comma(out)
            if stack:
                stack.pop()
            out.append(c)
            i += 1
            if not stack:
                break                               # drop anything after the first value
            continue
        if c.isalpha() or c == "_":
            word = _IDENT.match(s, i).group(0)
            j = i + len(word)
            k = j
            while k < n and s[k] in " \t\r\n":
                k += 1
            if k < n and s[k] == ":" and _last_significant(out) in ("{", ","):
                out.append(f'"{word}"')             # unquoted key
            else:
                out.append(_PY_LITERALS.get(word, word))
            i = j
            continue
        out.append(c)
        i += 1

    truncated = False
    if in_str:
        out.append('"')
        truncated = True
    if stack:
        _drop_trailing_comma(out)
        if _last_significant(out) == ":":
            out.append("null")
        out.extend(reversed(stack))
        truncated = True
    return "".join(out), truncated


def parse_tool_arguments(raw: Any) -> tuple[Optional[dict], Optional[str]]:
    """Arguments for a tool call → (dict, None) or (None, error for the model)."""
    if raw is None or raw == "":
        return {}, None
    if isinstance(raw, dict):
        return raw, None
    if not isinstance(raw, str):
        return None, INVALID_ERROR
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        repaired, truncated = repair_json(raw)
        if truncated:
            return None, CUT_OFF_ERROR
        try:
            value = json.loads(repaired)
        except (json.JSONDecodeError, ValueError):
            return None, INVALID_ERROR
    if not isinstance(value, dict):
        return None, INVALID_ERROR
    return value, None
