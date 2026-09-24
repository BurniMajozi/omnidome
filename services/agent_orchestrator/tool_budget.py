"""Cap tool output before it goes back to the model (spec A3 `tool-output-budget`).

Patterns from Tencent/WeKnora `internal/agent/tools/output_budget.go`
(MIT License, Copyright (C) 2025 Tencent), rewritten for Python.

A single tool result (500 CRM rows, a scraped page) can fill the model's context.
Results over the budget are trimmed: list-shaped results keep every record and
trim the largest ones (max-min fair allocation), anything else keeps its head and
tail. The untrimmed result is still returned to callers and stored in the log.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Optional

DEFAULT_MAX_OUTPUT_CHARS = 8000
_PLACEHOLDER = "__OMNIDOME_RECORDS__"
_MARK = "…[trimmed]"
_MIN_RECORD_CHARS = 60


def split_budget_fairly(total: int, sizes: list[int]) -> list[int]:
    """Water-filling: entries smaller than an equal share keep their full size and
    donate the slack; the rest split what remains evenly. Caps never exceed their
    size and never sum past `total`."""
    caps = [0] * len(sizes)
    remaining = max(total, 0)
    unsettled = set(range(len(sizes)))
    while unsettled:
        share = remaining // len(unsettled)
        settled = [i for i in unsettled if sizes[i] <= share]
        if not settled:
            for i in unsettled:
                caps[i] = share
            break
        for i in settled:
            caps[i] = sizes[i]
            remaining -= sizes[i]
            unsettled.discard(i)
    return caps


def _find_records(result: Any) -> tuple[Optional[list], Optional[list]]:
    """(records, path) for the largest list inside the result, if any."""
    if isinstance(result, list):
        return result, []
    if not isinstance(result, dict):
        return None, None
    data = result.get("data")
    if isinstance(data, list):
        return data, ["data"]
    if isinstance(data, dict):
        lists = [(k, v) for k, v in data.items() if isinstance(v, list) and v]
        if lists:
            key, value = max(lists, key=lambda kv: len(json.dumps(kv[1], default=str)))
            return value, ["data", key]
    return None, None


def _set_path(obj: Any, path: list, value: Any) -> Any:
    if not path:
        return value
    target = obj
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return obj


def budget_tool_result(result: Any, max_chars: int = DEFAULT_MAX_OUTPUT_CHARS) -> str:
    """The text sent to the model for this tool result, at most ~max_chars."""
    full = json.dumps(result, default=str)
    if len(full) <= max_chars:
        return full

    records, path = _find_records(result)
    if records:
        max_records = max(1, max_chars // _MIN_RECORD_CHARS)
        shown = records[:max_records]
        shell = json.dumps(_set_path(copy.deepcopy(result), path, _PLACEHOLDER), default=str)
        header = (
            f"[Tool output trimmed to fit: {len(full)} -> about {max_chars} chars. "
            + (f"All {len(records)} records kept; the largest were trimmed.]\n"
               if len(shown) == len(records)
               else f"Showing the first {len(shown)} of {len(records)} records, the largest trimmed.]\n")
        )
        pieces = [json.dumps(r, default=str) for r in shown]
        budget = max(max_chars - len(shell) - len(header) - 2 * len(pieces), len(pieces) * _MIN_RECORD_CHARS // 2)
        caps = split_budget_fairly(budget, [len(p) for p in pieces])
        trimmed = [
            p if len(p) <= cap else p[: max(cap - len(_MARK), 8)] + _MARK
            for p, cap in zip(pieces, caps)
        ]
        body = shell.replace(json.dumps(_PLACEHOLDER), "[\n" + ",\n".join(trimmed) + "\n]")
        return header + body

    head = int(max_chars * 0.7)
    tail = int(max_chars * 0.25)
    return f"{full[:head]}\n…[trimmed {len(full) - head - tail} chars]…\n{full[-tail:]}"
