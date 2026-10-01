"""Manager-chain helpers, redaction and text scrubbing (no database)."""
import uuid

from services.hr import access
from services.hr.access import (
    manager_chain, would_create_cycle, reports_of, redact_employee, redact_payslip, scrub_text, mask_tail,
)

A, B, C, D = (uuid.uuid4() for _ in range(4))


def test_chain_nearest_first():
    pm = {A: None, B: A, C: B}
    assert manager_chain(C, pm) == ([B, A], False)
    assert manager_chain(A, pm) == ([], False)


def test_chain_detects_loop():
    pm = {A: C, B: A, C: B}
    chain, cyclic = manager_chain(A, pm)
    assert cyclic is True


def test_would_create_cycle():
    pm = {A: None, B: A, C: B}
    assert would_create_cycle(A, C, pm) is True      # A reports to C who reports (via B) to A
    assert would_create_cycle(A, A, pm) is True      # own manager
    assert would_create_cycle(C, A, pm) is False
    assert would_create_cycle(D, C, {**pm, D: None}) is False
    assert would_create_cycle(A, None, pm) is False


def test_reports_are_direct_and_indirect():
    pm = {A: None, B: A, C: B, D: A}
    assert reports_of(A, pm) == {B, C, D}
    assert reports_of(B, pm) == {C}
    assert reports_of(C, pm) == set()


def test_reports_of_loop_terminates():
    pm = {A: B, B: A}
    assert reports_of(A, pm) == {B}


def test_mask_tail_and_scrub():
    assert mask_tail("1234567890") == "••••7890"
    assert mask_tail(None) is None
    assert "1234567890" not in scrub_text("account 1234567890 failed")
    assert scrub_text("account 1234567890 failed").endswith("failed") and "7890" in scrub_text("account 1234567890 failed")
    assert scrub_text("order 12345 ok") == "order 12345 ok"          # short numbers untouched
    assert scrub_text(None) is None


def test_redact_employee_for_non_admin():
    row = {"id": 1, "full_name": "X", "base_salary": 50000.0, "gross": 1, "net": 2, "account_number": "62001234567",
           "id_number": "8001015009087", "tax_number": "9876543210", "bank_code": "632005", "department": "Ops"}
    out = redact_employee(row, is_admin=False)
    assert "base_salary" not in out and "gross" not in out and "net" not in out and "bank_code" not in out
    assert out["account_number"].endswith("4567") and "6200" not in out["account_number"]
    assert out["id_number"].endswith("87") and "80010150" not in out["id_number"]
    assert out["tax_number"].endswith("10") and "98765432" not in out["tax_number"]
    assert out["department"] == "Ops" and out["full_name"] == "X"
    assert redact_employee(row, is_admin=True) is row


def test_redact_payslip_keeps_pay_masks_identifiers():
    row = {"gross": 100.0, "net": 80.0, "account_number": "62001234567", "id_number": "8001015009087",
           "paystack_transfer_code": "TRF_x", "paystack_recipient_code": "RCP_x", "account_name": "A B"}
    out = redact_payslip(row, is_admin=False)
    assert out["gross"] == 100.0 and out["net"] == 80.0 and out["account_name"] == "A B"
    assert out["account_number"].endswith("4567") and "6200" not in out["account_number"]
    assert "paystack_transfer_code" not in out and "paystack_recipient_code" not in out


def test_org_admin_is_not_hr_admin_by_default(monkeypatch):
    assert "org_admin" not in access.HR_ADMIN_ROLES
    monkeypatch.setenv("HR_ADMIN_EXTRA_ROLES", "org_admin")
    assert "org_admin" in access._admin_roles()


def test_roles_enforced_flag(monkeypatch):
    monkeypatch.delenv("HR_ENFORCE_ROLES", raising=False)
    assert access.roles_enforced() is True
    monkeypatch.setenv("HR_ENFORCE_ROLES", "false")
    assert access.roles_enforced() is False
