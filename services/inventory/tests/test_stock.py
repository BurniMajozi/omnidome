import uuid
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from services.inventory.stock import stock_delta, available, fingerprint
from services.inventory.main import StockUpdate, StockCheckoutRequest
from pydantic import ValidationError

def level(soh=10, allocated=3, reserved=2):
    return SimpleNamespace(soh=soh, allocated=allocated, reserved=reserved)

@pytest.mark.parametrize("kind", ["TRANSFER", "WRITE_OFF", "SALE"])
def test_outgoing_cannot_consume_reserved_or_allocated_stock(kind):
    row = level()
    with pytest.raises(HTTPException) as exc:
        stock_delta(row, kind, 6)
    assert exc.value.status_code == 409
    assert (row.soh, row.allocated, row.reserved) == (10, 3, 2)

def test_checkout_allocation_reduces_only_available_stock():
    row = level()
    stock_delta(row, "SALE", 5)
    assert row.soh == 10
    assert row.allocated == 8
    assert available(row) == 0

@pytest.mark.parametrize("quantity", [0, -1])
def test_reject_nonpositive_quantity_before_any_change(quantity):
    row = level()
    with pytest.raises(HTTPException):
        stock_delta(row, "PURCHASE", quantity)
    with pytest.raises(ValidationError):
        StockUpdate(product_id=uuid.uuid4(), warehouse_id=uuid.uuid4(), quantity=quantity, movement_type="TRANSFER")
    assert row.soh == 10

def test_returns_increase_stock_without_releasing_allocations():
    row = level()
    stock_delta(row, "RETURN_FROM_CUSTOMER", 4)
    assert (row.soh, row.allocated, available(row)) == (14, 3, 9)

def test_unknown_movement_and_empty_checkout_rejected():
    with pytest.raises(ValidationError):
        StockUpdate(product_id=uuid.uuid4(), warehouse_id=uuid.uuid4(), quantity=1, movement_type="FAKE")
    with pytest.raises(ValidationError):
        StockCheckoutRequest(items=[])

def test_request_identity_is_order_independent_and_changes_with_quantity():
    assert fingerprint({"quantity": 1, "sku": "X"}) == fingerprint({"sku": "X", "quantity": 1})
    assert fingerprint({"quantity": 1}) != fingerprint({"quantity": 2})
