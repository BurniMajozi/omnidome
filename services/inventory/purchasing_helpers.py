"""Pure purchasing rules shared by routes and behavioral tests."""
import base64
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

from fastapi import HTTPException

VAT_RATE = Decimal("0.15")


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def approval_hash(po, items):
    """Canonical snapshot, independent of relationship/query order."""
    snapshot = {
        "po_id": str(po.id), "supplier_id": str(po.supplier_id),
        "warehouse_id": str(po.warehouse_id), "currency": po.currency,
        "subtotal": str(money(po.subtotal_zar)), "vat": str(money(po.tax_zar)),
        "total": str(money(po.total_zar)),
        "lines": sorted([
            {"id": str(i.id), "product": str(i.product_id), "quantity": i.quantity_ordered,
             "unit_cost": str(money(i.unit_cost_zar)), "total": str(money(i.total_cost_zar))}
            for i in items
        ], key=lambda i: i["id"]),
    }
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_signature(signature):
    """Accept bounded PNG data, never arbitrary HTML/SVG or remote URLs."""
    prefix = "data:image/png;base64,"
    if not signature.startswith(prefix) or len(signature) > 350_000:
        raise ValueError("A PNG signature is required (maximum 256 KB)")
    try:
        data = base64.b64decode(signature[len(prefix):], validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("Invalid signature encoding") from exc
    if len(data) > 256_000 or not data.startswith(b"\x89PNG\r\n\x1a\n") or b"IEND" not in data[-12:]:
        raise ValueError("Invalid PNG signature")
    return signature


def require_state(po, allowed, action):
    if po.status not in allowed:
        raise HTTPException(409, f"Cannot {action} a PO in '{po.status}' status")


def validate_receipt(items, po_items):
    seen = set()
    for item in items:
        if item.po_item_id in seen:
            raise HTTPException(422, "Duplicate PO line in receipt")
        seen.add(item.po_item_id)
        line = po_items.get(str(item.po_item_id))
        if line is None:
            raise HTTPException(422, "Receipt line does not belong to this purchase order")
        if item.quantity_rejected > item.quantity_received:
            raise HTTPException(422, "quantity_rejected cannot exceed quantity_received")
        if item.quantity_received > line.quantity_ordered - line.quantity_received:
            raise HTTPException(409, "Receipt exceeds outstanding PO quantity")
        if item.quantity_rejected and not (item.rejection_reason or "").strip():
            raise HTTPException(422, "Rejected goods require a reason")
        accepted = item.quantity_received - item.quantity_rejected
        if item.serial_numbers and (len(item.serial_numbers) != accepted or len(set(item.serial_numbers)) != accepted):
            raise HTTPException(422, "Serial numbers must uniquely identify each accepted unit")


def matches_receipt(gr, body, po_items):
    """A reference may replay the same delivery, never a changed payload."""
    def key(product, ordered, received, rejected, cost, serials, reason):
        return (str(product), ordered, received, rejected, str(money(cost)),
                tuple(sorted(serials or [])), reason or "")
    requested = []
    for item in body.items:
        line = po_items.get(str(item.po_item_id))
        if line is None:
            return False
        requested.append(key(line.product_id, line.quantity_ordered, item.quantity_received,
                             item.quantity_rejected, line.unit_cost_zar, item.serial_numbers, item.rejection_reason))
    saved = [key(i.product_id, i.quantity_ordered, i.quantity_received, i.quantity_rejected,
                 i.unit_cost_zar, i.serial_numbers, i.rejection_reason) for i in gr.items]
    return sorted(requested) == sorted(saved) and all(
        getattr(gr, name) == getattr(body, name)
        for name in ("supplier_delivery_note", "supplier_invoice_number", "notes")
    )


def journal_payload(gr, accepted_value):
    value = money(accepted_value)
    vat = money(value * VAT_RATE)
    return {
        "entry_date": gr.received_at.date().isoformat(),
        "description": f"Goods receipt {gr.gr_number}",
        "source": "INVENTORY", "source_id": str(gr.id), "auto_post": True,
        "lines": [line for line in [
            {"account_code": "1200", "account_name": "Inventory", "debit": str(value), "credit": "0.00"},
            {"account_code": "2210", "account_name": "VAT Input", "debit": str(vat), "credit": "0.00"},
            {"account_code": "2000", "account_name": "Accounts Payable", "debit": "0.00", "credit": str(value + vat)},
        ] if Decimal(line["debit"]) or Decimal(line["credit"])],
    }


def render_purchase_order_pdf(po, items, supplier_name):
    """Real PDF bytes when ReportLab is installed in the service runtime."""
    try:
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise HTTPException(503, "PDF renderer unavailable: install ReportLab in the inventory service runtime") from exc
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(595, 842))
    pdf.setTitle(po.po_number)
    y = 790
    rows = [f"Purchase order {po.po_number}", f"Supplier: {supplier_name}",
            f"Currency: {po.currency}", f"Warehouse: {po.warehouse_id}"]
    rows += [f"{i.product_id} | {i.quantity_ordered} x {money(i.unit_cost_zar)} = {money(i.total_cost_zar)}" for i in items]
    rows += [f"Subtotal: {money(po.subtotal_zar)}", f"VAT: {money(po.tax_zar)}", f"Total: {money(po.total_zar)}"]
    for row in rows:
        if y < 55:
            pdf.showPage()
            y = 790
        pdf.drawString(40, y, row)
        y -= 24
    pdf.save()
    return output.getvalue()
