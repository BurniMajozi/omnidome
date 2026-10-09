"""Numbers-by-reference: the integrity rule of Deck Studio.

Narrative text may only carry a figure through a token such as {{q1.revenue|currency}}. Tokens are resolved
SERVER-SIDE from stored query results at render/export time. Text the AI writes is scanned: any numeric literal
that is not inside a token is replaced by the placeholder token {{?}} and reported, so the model has no path to
put an invented figure into a deck.

Token grammar:   {{ alias.path | format }}
    alias            a deck query alias (deck.queries key) or the id of a block that embeds its own query
    path             [measure.]stat   (measure defaults to the query's first measure)
    stats            total | first | last | prev | delta | delta_pct | max | min | avg | rows
                     last.label | first.label | top1.value | top1.label | top1.share | bottom1.* | row3.value | row3.label
    formats          currency currency_compact number number_compact percent percent0 duration text
                     signed_currency signed_number signed_percent
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

PLACEHOLDER = "{{?}}"
PLACEHOLDER_TEXT = "[add figure]"
TOKEN_RE = re.compile(r"\{\{\s*([^{}|]{1,120}?)\s*(?:\|\s*([a-z_0-9]{1,24})\s*)?\}\}")
FORMATS = {"currency", "currency_compact", "number", "number_compact", "percent", "percent0", "duration", "text",
           "signed_currency", "signed_number", "signed_percent"}
_MEASURE_FORMAT_DEFAULT = {"currency_zar": "currency", "number": "number", "percent": "percent", "duration": "duration"}
_STATS = {"total", "first", "last", "prev", "delta", "delta_pct", "max", "min", "avg", "rows"}
_RANK = re.compile(r"^(top|bottom)([1-9])$")
_ROW = re.compile(r"^row([1-9][0-9]?)$")


class TokenError(ValueError):
    pass


# ── formatting ────────────────────────────────────────────────────────────

def _group(v: float, dec: int) -> str:
    return f"{abs(v):,.{dec}f}".replace(",", " ")


def _compact(v: float, prefix: str = "") -> str:
    a = abs(v)
    for limit, suffix in ((1e9, "bn"), (1e6, "m"), (1e3, "k")):
        if a >= limit:
            s = f"{a / limit:.1f}".rstrip("0").rstrip(".")
            return f"{prefix}{s}{suffix}"
    s = f"{a:.2f}".rstrip("0").rstrip(".") if a % 1 else f"{a:.0f}"
    return f"{prefix}{s}"


def format_value(v: Any, fmt: str) -> str:
    if fmt not in FORMATS:
        raise TokenError(f"unknown format {fmt!r}")
    if fmt == "text":
        return str(v)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (isinstance(v, float) and not math.isfinite(v)):
        raise TokenError("value is not a number")
    signed = fmt.startswith("signed_")
    base = fmt[7:] if signed else fmt
    sign = "-" if v < 0 else ("+" if signed and v > 0 else "")
    if base == "currency":
        return f"{sign}R{_group(v, 0 if abs(v) >= 1000 or float(v).is_integer() else 2)}"
    if base == "currency_compact":
        return f"{sign}{_compact(v, 'R')}"
    if base == "number":
        return f"{sign}{_group(v, 0 if float(v).is_integer() or abs(v) >= 1000 else 2)}"
    if base == "number_compact":
        return f"{sign}{_compact(v)}"
    if base == "percent":
        return f"{sign}{abs(v) * 100:.1f}%"
    if base == "percent0":
        return f"{sign}{abs(v) * 100:.0f}%"
    if base == "duration":  # value in hours
        a = abs(v)
        if a < 1:
            return f"{sign}{a * 60:.0f} min"
        if a < 48:
            return f"{sign}{a:.1f} h"
        return f"{sign}{a / 24:.1f} days"
    raise TokenError(f"unknown format {fmt!r}")


# ── evaluation against a stored query result ─────────────────────────────

def _cols(result: dict) -> tuple[list[str], list[str], list[dict]]:
    cols = result.get("columns") or []
    measures = [c["id"] for c in cols if c.get("kind") == "measure"]
    dims = [c["id"] for c in cols if c.get("kind") != "measure"]
    return measures, dims, cols


def evaluate(body: str, results: dict[str, dict]) -> tuple[Any, str]:
    """-> (raw value, default format). Raises TokenError when the reference cannot be resolved."""
    parts = [p for p in body.strip().split(".") if p != ""]
    if len(parts) < 1:
        raise TokenError("empty token")
    alias, rest = parts[0], parts[1:]
    if alias not in results:
        raise TokenError(f"no data for query {alias!r}")
    result = results[alias]
    measures, dims, cols = _cols(result)
    rows = result.get("rows") or []
    if rest and rest[0] in measures:
        m, rest = rest[0], rest[1:]
    else:
        m = measures[0] if measures else None
    stat = rest[0] if rest else "total"
    sub = rest[1] if len(rest) > 1 else None
    if len(rest) > 2 or (stat in _STATS and stat not in ("first", "last", "prev") and sub):
        raise TokenError(f"unsupported token path {body!r}")
    mcol = next((c for c in cols if c.get("id") == m), None)
    default_fmt = _MEASURE_FORMAT_DEFAULT.get((mcol or {}).get("format") or "number", "number")
    if stat == "rows":
        return len(rows), "number"
    if m is None and stat != "rows":
        raise TokenError(f"query {alias!r} has no measure")
    mi = [c["id"] for c in cols].index(m)

    def col_vals() -> list[float]:
        return [r[mi] for r in rows if isinstance(r[mi], (int, float)) and not isinstance(r[mi], bool)]

    def label_of(row: list) -> str:
        di = [i for i, c in enumerate(cols) if c.get("kind") != "measure"]
        return " / ".join(str(row[i]) for i in di) if di else ""

    if stat == "total":
        tv = (result.get("totals") or {}).get(m)
        if tv is None:
            raise TokenError(f"no total for {m!r}")
        return tv, default_fmt
    if stat in ("first", "last", "prev"):
        if not rows or (stat == "prev" and len(rows) < 2):
            raise TokenError(f"query {alias!r} has too few rows for {stat}")
        row = rows[0] if stat == "first" else rows[-1] if stat == "last" else rows[-2]
        if sub == "label":
            return label_of(row), "text"
        if sub:
            raise TokenError(f"unsupported token path {body!r}")
        if row[mi] is None:
            raise TokenError("no value")
        return row[mi], default_fmt
    if stat in ("delta", "delta_pct"):
        if len(rows) < 2 or rows[-1][mi] is None or rows[-2][mi] is None:
            raise TokenError(f"query {alias!r} needs two periods for {stat}")
        last, prev = rows[-1][mi], rows[-2][mi]
        if stat == "delta":
            return last - prev, "signed_" + default_fmt if not default_fmt.startswith("signed_") else default_fmt
        if prev == 0:
            raise TokenError("previous period is zero; percentage change is undefined")
        return (last - prev) / abs(prev), "signed_percent"
    if stat in ("max", "min", "avg"):
        vals = col_vals()
        if not vals:
            raise TokenError("no values")
        return (max(vals) if stat == "max" else min(vals) if stat == "min" else sum(vals) / len(vals)), default_fmt
    rk, rw = _RANK.match(stat), _ROW.match(stat)
    if rk or rw:
        if rw:
            n = int(rw.group(1))
            ranked = [r for r in rows if isinstance(r[mi], (int, float))]
        else:
            n = int(rk.group(2))
            ranked = sorted((r for r in rows if isinstance(r[mi], (int, float))), key=lambda r: r[mi], reverse=rk.group(1) == "top")
        if len(ranked) < n:
            raise TokenError(f"query {alias!r} has fewer than {n} rows")
        row = ranked[n - 1]
        if sub == "label":
            return label_of(row), "text"
        if sub == "share":
            total = (result.get("totals") or {}).get(m)
            if not (mcol or {}).get("additive") or not total:
                raise TokenError("share needs an additive measure with a non-zero total")
            return row[mi] / total, "percent"
        if sub in (None, "value"):
            return row[mi], default_fmt
    raise TokenError(f"unsupported token path {body!r}")


# ── resolution ────────────────────────────────────────────────────────────

def extract_tokens(text: str) -> list[tuple[str, str, Optional[str]]]:
    return [(m.group(0), m.group(1).strip(), m.group(2)) for m in TOKEN_RE.finditer(text or "")]


def resolve_ref(ref: str, results: dict[str, dict], fmt: Optional[str] = None) -> str:
    """Resolve one bare reference such as 'q1.outstanding.delta_pct' (used by KPI blocks)."""
    raw, default = evaluate(ref, results)
    return format_value(raw, fmt or default)


def resolve_text(text: str, results: dict[str, dict]) -> tuple[str, list[dict]]:
    """Replace every token with its display string. Unresolvable tokens render as a dash and are reported."""
    unresolved: list[dict] = []

    def sub(m: re.Match) -> str:
        body, fmt = m.group(1).strip(), m.group(2)
        if body == "?":
            unresolved.append({"token": m.group(0), "reason": "placeholder: a figure still needs to be chosen"})
            return PLACEHOLDER_TEXT
        try:
            raw, default = evaluate(body, results)
            return format_value(raw, fmt or default)
        except TokenError as exc:
            unresolved.append({"token": m.group(0), "reason": str(exc)})
            return "—"

    return TOKEN_RE.sub(sub, text or ""), unresolved


def validate_token_refs(text: str, query_measures: dict[str, list[str]]) -> list[dict]:
    """Static check (no data needed): alias exists, measure (if named) exists, format known, path shape is valid."""
    bad = []
    for full, body, fmt in extract_tokens(text):
        if body == "?":
            continue
        parts = [p for p in body.split(".") if p]
        reason = None
        if not parts or parts[0] not in query_measures:
            reason = f"unknown query alias {parts[0] if parts else ''!r}"
        else:
            rest = parts[1:]
            if rest and rest[0] in query_measures[parts[0]]:
                rest = rest[1:]
            elif rest and rest[0] not in _STATS and not _RANK.match(rest[0]) and not _ROW.match(rest[0]):
                reason = f"unknown measure or statistic {rest[0]!r}"
            if reason is None:
                if not query_measures[parts[0]] and not (rest and rest[0] == "rows"):
                    reason = "that query has no measure"
                elif rest:
                    st, sub = rest[0], (rest[1] if len(rest) > 1 else None)
                    if len(rest) > 2 or (st not in _STATS and not _RANK.match(st) and not _ROW.match(st)):
                        reason = f"unsupported token path {body!r}"
                    elif sub and not ((st in ("first", "last", "prev") and sub == "label") or ((_RANK.match(st) or _ROW.match(st)) and sub in ("value", "label", "share"))):
                        reason = f"unsupported token path {body!r}"
        if reason is None and fmt and fmt not in FORMATS:
            reason = f"unknown format {fmt!r}"
        if reason:
            bad.append({"token": full, "reason": reason})
    return bad


# ── ungrounded number detection ───────────────────────────────────────────

_NUM = re.compile(
    r"(?<![\w#.])(?:[R$€£]\s?)?\d+(?:[  ,]\d{3})*(?:\.\d+)?(?:\s?%|\s?(?:bn|k|m|b)\b(?![\w]))?(?![A-Za-z])", re.I)
_YEAR = re.compile(r"^(?:19|20)\d{2}$")
_WORDS = re.compile(r"\b(?:(?:a|one|two|three|four|five|six|seven|eight|nine|ten|several|many)\s+)?"
                    r"(?:hundred|thousand|million|billion|trillion)s?\b", re.I)
_LIST_MARK = re.compile(r"^\s*\d{1,2}[.)]\s")
_ALLOWED_PHRASES = ("24/7", "24x7", "24/7/365")


def _mask_tokens(text: str) -> str:
    return TOKEN_RE.sub(lambda m: " " * len(m.group(0)), text)


def find_ungrounded(text: str) -> list[dict]:
    """Numeric literals (and big-number words) that sit outside any token."""
    out: list[dict] = []
    masked = _mask_tokens(text or "")
    for phrase in _ALLOWED_PHRASES:
        masked = masked.replace(phrase, " " * len(phrase))
    for m in _NUM.finditer(masked):
        lit = m.group(0).rstrip(" ,.")
        if not lit:
            continue
        if _YEAR.match(lit):
            continue
        line_start = masked.rfind("\n", 0, m.start()) + 1
        if _LIST_MARK.match(masked[line_start:m.end() + 2]) and m.start() - line_start <= 3 and re.match(r"^\d{1,2}$", lit):
            continue
        out.append({"literal": lit.strip(), "start": m.start(), "end": m.start() + len(m.group(0).rstrip(" ,."))})
    for m in _WORDS.finditer(masked):
        out.append({"literal": m.group(0), "start": m.start(), "end": m.end()})
    out.sort(key=lambda r: r["start"])
    return out


def sanitise_ai_text(text: str, query_measures: dict[str, list[str]]) -> tuple[str, dict]:
    """Make AI-written text safe: invalid tokens and every ungrounded figure become {{?}}."""
    report = {"ungrounded_numbers": [], "invalid_tokens": []}
    t = text or ""
    for bad in validate_token_refs(t, query_measures):
        report["invalid_tokens"].append(bad)
        t = t.replace(bad["token"], PLACEHOLDER)
    spans = find_ungrounded(t)
    spans = _merge(spans)
    for sp in reversed(spans):
        report["ungrounded_numbers"].append(sp["literal"])
        t = t[:sp["start"]] + PLACEHOLDER + t[sp["end"]:]
    report["ungrounded_numbers"].reverse()
    return t, report


def _merge(spans: list[dict]) -> list[dict]:
    out: list[dict] = []
    for sp in spans:
        if out and sp["start"] <= out[-1]["end"]:
            out[-1]["end"] = max(out[-1]["end"], sp["end"])
        else:
            out.append(dict(sp))
    return out
