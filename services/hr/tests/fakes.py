"""Test doubles for the HR service: a scriptable async session and request helpers.

The session answers `execute(stmt)` from an ordered list of rules (first match wins). A rule is
(matcher, rows) where matcher is a substring of str(stmt) or a callable(stmt) -> bool, and rows is a
list (or a callable(stmt) -> list). It records every statement, add(), flush() and commit() so tests
can assert that a GET never writes.
"""
from __future__ import annotations

import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

from services.common.auth import AuthContext  # noqa: E402
from services.hr.database import Employee  # noqa: E402

TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER_TENANT = uuid.UUID("00000000-0000-0000-0000-000000000002")


class Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return SimpleNamespace(first=lambda: self._rows[0] if self._rows else None, all=lambda: list(self._rows))

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)

    def scalar(self):
        if not self._rows:
            return None
        r = self._rows[0]
        return r[0] if isinstance(r, (tuple, list)) else r


class FakeDB:
    def __init__(self, rules=None):
        self.rules = list(rules or [])
        self.statements = []
        self.added = []
        self.flushes = 0
        self.commits = 0

    def when(self, matcher, rows):
        self.rules.append((matcher, rows))
        return self

    async def execute(self, stmt, params=None):
        self.statements.append(stmt)
        text = str(stmt)
        for matcher, rows in self.rules:
            ok = matcher(stmt) if callable(matcher) else (matcher in text)
            if ok:
                return Result(rows(stmt) if callable(rows) else rows)
        return Result([])

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushes += 1
        for obj in self.added:
            if hasattr(obj, "id") and getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.utcnow()

    async def refresh(self, obj):
        return None

    async def commit(self):
        self.commits += 1

    @asynccontextmanager
    async def begin_nested(self):
        yield

    def wrote(self) -> bool:
        return bool(self.added) or self.flushes > 0 or self.commits > 0


# statement matchers --------------------------------------------------------

def parent_map_query(stmt) -> bool:
    return "employees.id, employees.manager_id" in str(stmt)


def caller_lookup(stmt) -> bool:
    t = str(stmt)
    return "employees.user_id =" in t and "employees.id, employees.manager_id" not in t


def employee_by_id(stmt) -> bool:
    t = str(stmt)
    return "FROM employees" in t and "employees.id =" in t and "employees.user_id =" not in t and "employees.id, employees.manager_id" not in t


def params_of(stmt) -> list:
    return list(stmt.compile().params.values())


# builders ---------------------------------------------------------------------

def employee(emp_id=None, user_id=None, manager_id=None, title="Analyst", name="Test Person", email=None,
             status="ACTIVE", dob=None, id_number=None) -> Employee:
    return Employee(
        id=emp_id or uuid.uuid4(), tenant_id=TENANT, employee_id="E-" + uuid.uuid4().hex[:4], full_name=name,
        job_title=title, department="Ops", hire_date=date(2024, 1, 1), status=status, user_id=user_id,
        manager_id=manager_id, email=email, date_of_birth=dob, id_number=id_number,
        created_at=datetime(2026, 1, 1),
    )


def ctx(roles=(), user_id=None, tenant_id=TENANT, platform_admin=False, perms=()):
    return AuthContext(user_id=user_id or uuid.uuid4(), tenant_id=tenant_id, roles=list(roles), permissions=list(perms),
                       is_platform_admin=platform_admin, rbac_loaded=True)
