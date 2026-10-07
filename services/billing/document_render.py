"""Print-ready, self-contained document rendering for invoices and quotes (no scripts, everything escaped).

Pure functions: they take plain dicts ("document views") and a template dict, so the public (token) view and
the authenticated views render identically. True PDF is not produced server-side yet: the page is styled for
browser print (``@media print``) and the CSV/JSON exports sit beside it.
"""
from __future__ import annotations

import csv
import html
import io
import re
from datetime import date
from decimal import Decimal
from typing import Any, Optional

_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
_URL = re.compile(r"^https?://[^\s<>\"']+$")

DEFAULT_TEMPLATE: dict = {
    "name": "Default", "company_name": None, "company_address": None, "vat_number": None,
    "logo_url": None, "accent_colour": "#1d4ed8", "footer": None, "payment_details": None,
    "default_terms": None, "default_due_days": 30,
    "show_columns": {"description": True, "quantity": True, "unit_price": True, "discount": True,
                     "tax": True, "line_total": True},
    "show_payment_details": True, "show_terms": True,
}

CSP = "default-src 'none'; img-src https: http: data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"


def esc(value: Any) -> str:
    """HTML-escape any value (None -> '')."""
    return "" if value is None else html.escape(str(value), quote=True)


def zar(value: Any) -> str:
    try:
        d = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return ""
    sign = "-" if d < 0 else ""
    return f"{sign}R{abs(d):,.2f}"


def _nl2br(value: Any) -> str:
    return esc(value).replace("\r\n", "\n").replace("\n", "<br>")


def safe_template(t: Optional[dict]) -> dict:
    out = {**DEFAULT_TEMPLATE, **{k: v for k, v in (t or {}).items() if v is not None or k in DEFAULT_TEMPLATE}}
    cols = dict(DEFAULT_TEMPLATE["show_columns"])
    cols.update({k: bool(v) for k, v in (out.get("show_columns") or {}).items() if k in cols})
    out["show_columns"] = cols
    if not _COLOUR.match(str(out.get("accent_colour") or "")):
        out["accent_colour"] = DEFAULT_TEMPLATE["accent_colour"]
    if out.get("logo_url") and not _URL.match(str(out["logo_url"])):
        out["logo_url"] = None
    return out


def template_to_dict(t: Any) -> dict:
    """ORM InvoiceTemplate -> template dict (or defaults when None)."""
    if t is None:
        return safe_template(None)
    return safe_template({
        "id": str(t.id), "name": t.name, "company_name": t.company_name, "company_address": t.company_address,
        "vat_number": t.vat_number, "logo_url": t.logo_url, "accent_colour": t.accent_colour, "footer": t.footer,
        "payment_details": t.payment_details, "default_terms": t.default_terms,
        "default_due_days": t.default_due_days, "show_columns": t.show_columns or {},
        "show_payment_details": t.show_payment_details, "show_terms": t.show_terms,
    })


def normalise_lines(raw_lines: list) -> list[dict]:
    """Stored lines (new shape or legacy subscription shape) -> uniform render rows."""
    rows = []
    for ln in raw_lines or []:
        if not isinstance(ln, dict):
            continue
        qty = ln.get("quantity", 1)
        unit = ln.get("unit_price_zar", ln.get("unit_price", "0"))
        net = ln.get("total_zar", ln.get("net_zar"))
        if net is None:
            try:
                net = str((Decimal(str(qty)) * Decimal(str(unit))).quantize(Decimal("0.01")))
            except Exception:  # noqa: BLE001
                net = "0.00"
        vat = ln.get("vat_zar")
        rows.append({
            "line_id": ln.get("line_id"),
            "description": ln.get("description", ""),
            "quantity": str(qty), "unit_price": str(unit),
            "discount": str(ln.get("discount_zar", "0.00")),
            "tax_rate": ln.get("tax_rate"),
            "net": str(net), "vat": None if vat is None else str(vat),
            "total": ln.get("line_total_incl_zar") or (str(Decimal(str(net)) + Decimal(str(vat))) if vat is not None else str(net)),
        })
    return rows


def invoice_view(inv: Any, meta: Any, template: dict, bill_to: Optional[dict] = None) -> dict:
    paid = Decimal(str(inv.amount_paid_zar or 0))
    total = Decimal(str(inv.total_zar))
    return {
        "kind": "invoice",
        "title": "Credit note" if inv.credit_note_of else "Tax invoice",
        "number": inv.number, "status": inv.status,
        "issue_date": (meta.issue_date if meta and meta.issue_date else (inv.created_at.date() if inv.created_at else None)),
        "due_date": inv.due_date, "valid_until": None,
        "po_number": meta.po_number if meta else None,
        "bill_to": bill_to or (meta.bill_to if meta and meta.bill_to else {}) or {},
        "lines": normalise_lines(inv.line_items or []),
        "subtotal": str(inv.subtotal_zar), "discount_total": str(meta.discount_total_zar if meta else "0.00"),
        "vat": str(inv.vat_zar), "total": str(total), "paid": str(paid), "balance": str(total - paid),
        "notes": inv.notes, "terms": (meta.terms if meta and meta.terms else template.get("default_terms")),
        "template": template,
    }


def quote_view(q: Any, template: dict, bill_to: Optional[dict] = None) -> dict:
    lines = [{
        "line_id": str(l.id), "description": l.description, "quantity": format(l.quantity.normalize(), "f"),
        "unit_price": str(l.unit_price_zar), "discount": str(l.discount_zar), "tax_rate": str(l.tax_rate),
        "net": str(l.net_zar), "vat": str(l.vat_zar), "total": str(l.total_zar + l.vat_zar),
    } for l in q.lines]
    return {
        "kind": "quote", "title": "Quote", "number": q.number, "status": q.status,
        "issue_date": q.issue_date, "due_date": None, "valid_until": q.valid_until, "po_number": q.po_number,
        "bill_to": bill_to or {"name": q.prospect_name, "email": q.prospect_email,
                               "phone": q.prospect_phone, "address": q.prospect_address},
        "lines": lines, "subtotal": str(q.subtotal_zar), "discount_total": str(q.discount_total_zar),
        "vat": str(q.vat_zar), "total": str(q.total_zar), "paid": None, "balance": None,
        "notes": q.notes, "terms": q.terms or template.get("default_terms"), "template": template,
    }


# ── HTML ─────────────────────────────────────────────────────────────────────

_CSS = """
*{box-sizing:border-box}body{font-family:Arial,Helvetica,sans-serif;color:#1f2937;margin:0;background:#f3f4f6}
.doc{max-width:820px;margin:24px auto;background:#fff;padding:40px;border-top:6px solid var(--accent)}
.hdr{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}
.hdr img{max-height:64px;max-width:220px}.title{font-size:28px;font-weight:700;color:var(--accent);margin:0}
.muted{color:#6b7280;font-size:13px}.badge{display:inline-block;border:1px solid var(--accent);color:var(--accent);
padding:2px 10px;border-radius:12px;font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.cols{display:flex;gap:32px;margin:28px 0}.cols>div{flex:1}h4{margin:0 0 6px;font-size:12px;text-transform:uppercase;color:#6b7280}
table{width:100%;border-collapse:collapse;margin-top:8px}th{background:var(--accent);color:#fff;text-align:left;font-size:12px;padding:8px}
td{padding:8px;border-bottom:1px solid #e5e7eb;font-size:13px;vertical-align:top}.num{text-align:right;white-space:nowrap}
.tot{margin:20px 0 0 auto;width:300px}.tot td{border:0;padding:4px 8px}.tot .grand td{font-weight:700;font-size:16px;border-top:2px solid var(--accent)}
.block{margin-top:24px;font-size:13px}.foot{margin-top:32px;border-top:1px solid #e5e7eb;padding-top:12px;font-size:12px;color:#6b7280}
@media print{body{background:#fff}.doc{margin:0;max-width:none;padding:0;border-top:0}.noprint{display:none}}
""".strip()


def _party_block(label: str, name: Any, lines: list) -> str:
    body = "".join(f"<div>{_nl2br(x)}</div>" for x in lines if x)
    return f"<div><h4>{esc(label)}</h4><div><strong>{esc(name)}</strong></div>{body}</div>"


def render_fragment(view: dict) -> str:
    """The document body (no <html>); also embedded in emails."""
    t = safe_template(view.get("template"))
    cols = t["show_columns"]
    accent = t["accent_colour"]
    bt = view.get("bill_to") or {}
    logo = f'<img src="{esc(t["logo_url"])}" alt="">' if t.get("logo_url") else ""
    seller_lines = [t.get("company_address"), f"VAT no. {t['vat_number']}" if t.get("vat_number") else None]
    is_invoice = view["kind"] == "invoice"
    meta_rows = [("Date", view.get("issue_date"))]
    if is_invoice:
        meta_rows.append(("Due date", view.get("due_date")))
    else:
        meta_rows.append(("Valid until", view.get("valid_until")))
    if view.get("po_number"):
        meta_rows.append(("PO number", view["po_number"]))
    meta_html = "".join(
        f'<div class="muted">{esc(k)}: <strong>{esc(v.isoformat() if isinstance(v, date) else v)}</strong></div>'
        for k, v in meta_rows if v)

    heads = [("description", "Description", ""), ("quantity", "Qty", "num"), ("unit_price", "Unit price", "num"),
             ("discount", "Discount", "num"), ("tax", "VAT %", "num"), ("line_total", "Total", "num")]
    shown = [(k, label, cls) for k, label, cls in heads if cols.get(k, True)]
    th = "".join(f'<th class="{cls}">{esc(label)}</th>' for _k, label, cls in shown)
    body_rows = []
    for ln in view.get("lines", []):
        cells = {
            "description": esc(ln["description"]),
            "quantity": esc(ln["quantity"]),
            "unit_price": esc(zar(ln["unit_price"])),
            "discount": esc(zar(ln["discount"])) if Decimal(str(ln["discount"] or 0)) else "",
            "tax": esc(f'{ln["tax_rate"]}%') if ln.get("tax_rate") not in (None, "") else "",
            "line_total": esc(zar(ln["total"])),
        }
        tds = "".join(f'<td class="{cls}">{cells[k]}</td>' for k, _l, cls in shown)
        body_rows.append(f"<tr>{tds}</tr>")

    totals = [("Subtotal", view["subtotal"])]
    if Decimal(str(view.get("discount_total") or 0)):
        totals.append(("Discounts included", view["discount_total"]))
    totals.append(("VAT", view["vat"]))
    tot_rows = "".join(f'<tr><td>{esc(k)}</td><td class="num">{esc(zar(v))}</td></tr>' for k, v in totals)
    tot_rows += f'<tr class="grand"><td>Total</td><td class="num">{esc(zar(view["total"]))}</td></tr>'
    if is_invoice and view.get("paid") is not None:
        tot_rows += (f'<tr><td>Paid</td><td class="num">{esc(zar(view["paid"]))}</td></tr>'
                     f'<tr><td><strong>Balance due</strong></td><td class="num"><strong>{esc(zar(view["balance"]))}</strong></td></tr>')

    blocks = []
    if view.get("notes"):
        blocks.append(f'<div class="block"><h4>Notes</h4>{_nl2br(view["notes"])}</div>')
    if t.get("show_payment_details") and t.get("payment_details") and is_invoice:
        blocks.append(f'<div class="block"><h4>Payment details</h4>{_nl2br(t["payment_details"])}</div>')
    if t.get("show_terms") and view.get("terms"):
        blocks.append(f'<div class="block"><h4>Terms</h4>{_nl2br(view["terms"])}</div>')
    footer = f'<div class="foot">{_nl2br(t["footer"])}</div>' if t.get("footer") else ""

    return (
        f'<div class="doc" style="--accent:{accent}">'
        f'<div class="hdr"><div>{logo}<div><strong>{esc(t.get("company_name"))}</strong></div>'
        f'{"".join(f"<div class=muted>{_nl2br(x)}</div>" for x in seller_lines if x)}</div>'
        f'<div style="text-align:right"><p class="title">{esc(view["title"])}</p>'
        f'<div class="muted">No. <strong>{esc(view["number"])}</strong></div>'
        f'<div><span class="badge">{esc(view["status"])}</span></div>{meta_html}</div></div>'
        f'<div class="cols">{_party_block("Bill to", bt.get("name"), [bt.get("email"), bt.get("phone"), bt.get("address")])}</div>'
        f'<table><thead><tr>{th}</tr></thead><tbody>{"".join(body_rows)}</tbody></table>'
        f'<table class="tot"><tbody>{tot_rows}</tbody></table>'
        f'{"".join(blocks)}{footer}</div>'
    )


def render_html(view: dict, *, pay_url: Optional[str] = None) -> str:
    """Full standalone page. ``pay_url`` (if given) adds a no-print pay/view button; it is escaped."""
    frag = render_fragment(view)
    btn = ""
    if pay_url and _URL.match(pay_url):
        btn = (f'<div class="doc noprint" style="margin-top:0;border-top:0;padding-top:0;text-align:center">'
               f'<a href="{esc(pay_url)}" style="display:inline-block;background:#1d4ed8;color:#fff;padding:10px 22px;'
               f'border-radius:6px;text-decoration:none">View online</a></div>')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="Content-Security-Policy" content="{esc(CSP)}">'
            f'<title>{esc(view["title"])} {esc(view["number"])}</title><style>{_CSS}</style></head>'
            f'<body>{frag}{btn}</body></html>')


# ── exports ──────────────────────────────────────────────────────────────────

_CSV_RISKY = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: Any) -> str:
    s = "" if value is None else str(value)
    return "'" + s if s.startswith(_CSV_RISKY) and not _is_number(s) else s


def _is_number(s: str) -> bool:
    try:
        Decimal(s)
        return True
    except Exception:  # noqa: BLE001
        return False


def render_csv(view: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["document", view["kind"], "number", _csv_safe(view["number"]), "status", view["status"]])
    w.writerow(["description", "quantity", "unit_price_zar", "discount_zar", "tax_rate", "net_zar", "vat_zar", "total_zar"])
    for ln in view.get("lines", []):
        w.writerow([_csv_safe(ln["description"]), ln["quantity"], ln["unit_price"], ln["discount"],
                    ln.get("tax_rate") or "", ln["net"], ln.get("vat") or "", ln["total"]])
    w.writerow([])
    for k in ("subtotal", "discount_total", "vat", "total", "paid", "balance"):
        if view.get(k) is not None:
            w.writerow([k, view[k]])
    return buf.getvalue()


def view_to_json(view: dict) -> dict:
    """JSON-safe copy of a view (dates -> iso strings; template reduced to public branding)."""
    t = safe_template(view.get("template"))
    out = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in view.items() if k != "template"}
    out["branding"] = {"company_name": t.get("company_name"), "logo_url": t.get("logo_url"),
                       "accent_colour": t["accent_colour"], "footer": t.get("footer"),
                       "payment_details": t.get("payment_details") if t.get("show_payment_details") else None}
    out["currency"] = "ZAR"
    return out
