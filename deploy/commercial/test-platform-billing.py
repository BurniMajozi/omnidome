"""Run billing integration tests only in the explicitly named test database."""
import os
import sys
from sqlalchemy.engine import make_url

sys.path.insert(0, "/app")
url = make_url(os.environ["DATABASE_URL"]).set(database="omnidome_pricing_test")
os.environ["TEST_DATABASE_URL"] = url.render_as_string(hide_password=False)
os.environ["REQUIRE_DB_TESTS"] = "1"
import pytest
raise SystemExit(pytest.main([
    "services/admin/tests/test_platform_credits.py",
    "services/admin/tests/test_pricing_review.py",
    "services/admin/tests/test_tenant_pricing.py",
    "-q", "--tb=short",
]))
