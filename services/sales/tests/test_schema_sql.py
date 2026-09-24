"""The startup schema is split on ';' and run statement by statement.
A ';' inside a SQL comment once produced a comment-only fragment that asyncpg
cannot execute, which kept the service from starting. Guard both schemas.

Run with cwd = services/sales:  PYTHONPATH=../.. python -m pytest tests/ -q
"""

import os
import re
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common.event_bus import SCHEMA_SQL  # noqa: E402
from services.sales.schema import LEAD_LIFECYCLE_SQL  # noqa: E402


@pytest.mark.parametrize("sql", [LEAD_LIFECYCLE_SQL, SCHEMA_SQL], ids=["lead_lifecycle", "event_bus"])
def test_no_semicolons_inside_sql_comments(sql):
    comments = re.findall(r"--[^\n]*", sql)
    assert not [c for c in comments if ";" in c]


@pytest.mark.parametrize("sql", [LEAD_LIFECYCLE_SQL, SCHEMA_SQL], ids=["lead_lifecycle", "event_bus"])
def test_every_fragment_is_a_real_statement(sql):
    fragments = [f for f in sql.split(";") if f.strip()]
    assert all(re.sub(r"--[^\n]*", "", f).strip() for f in fragments)
