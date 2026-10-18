"""Finance journals for stock movements: balanced, on the right accounts, and queued only when there is value."""
from datetime import date
from decimal import Decimal

from services.inventory import finance_outbox
from services.inventory.purchasing_helpers import dispatch_journal, return_journal, writeoff_journal

DAY = date(2026, 10, 18)


def totals(j):
    return sum(Decimal(l["debit"]) for l in j["lines"]), sum(Decimal(l["credit"]) for l in j["lines"])


def test_supplier_return_reverses_the_purchase_including_vat():
    j = return_journal("r1", Decimal("1000"), DAY, "Alpha Supply")
    assert j["source"] == "INVENTORY_RETURN" and j["source_id"] == "r1" and j["auto_post"]
    d, c = totals(j)
    assert d == c == Decimal("1150.00")
    by = {l["account_code"]: l for l in j["lines"]}
    assert by["2000"]["debit"] == "1150.00" and by["1200"]["credit"] == "1000.00" and by["2210"]["credit"] == "150.00"


def test_writeoff_and_dispatch_move_cost_out_of_inventory():
    w = writeoff_journal("w1", Decimal("612.50"), DAY)
    d = dispatch_journal("d1", Decimal("612.50"), DAY, "to customer")
    for j, expense in ((w, "6900"), (d, "5100")):
        assert totals(j) == (Decimal("612.50"), Decimal("612.50"))
        by = {l["account_code"]: l for l in j["lines"]}
        assert by[expense]["debit"] == "612.50" and by["1200"]["credit"] == "612.50"
    assert w["source"] == "INVENTORY_WRITEOFF" and d["source"] == "INVENTORY_DISPATCH"


def test_zero_value_queues_nothing_and_value_queues_one_pending_row():
    class FakeDb:
        def __init__(self):
            self.rows = []

        def add(self, row):
            self.rows.append(row)

    db = FakeDb()
    assert finance_outbox.enqueue_payload(db, "t", writeoff_journal("w0", Decimal("0"), DAY), Decimal("0")) is False and db.rows == []
    assert finance_outbox.enqueue_payload(db, "t", writeoff_journal("w2", Decimal("5"), DAY), Decimal("5")) is True
    assert db.rows[0].status == "pending" and db.rows[0].source == "INVENTORY_WRITEOFF" and db.rows[0].source_id == "w2"
