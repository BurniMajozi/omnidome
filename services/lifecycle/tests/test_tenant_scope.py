"""Lifecycle: the tenant comes only from the authenticated identity."""
import os
import uuid

os.environ["AUTH_MODE"] = "header"
os.environ["AUTH_ENFORCE_MODULES"] = "false"

import pytest
from fastapi.testclient import TestClient

from services.lifecycle import main
from services.lifecycle.database import get_session

TENANT_A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
TENANT_B = uuid.UUID("00000000-0000-0000-0000-00000000000b")
USER = "00000000-0000-0000-0000-0000000000f1"


class _Result:
    def scalars(self):
        return self

    def all(self):
        return []

    def scalar(self):
        return 0

    def scalar_one_or_none(self):
        return None

    def one(self):
        class Row:
            at_risk_count = 0
            avg_churn_prob = 0
            total_mrr = 0
            total_customers = 0
        return Row()


class FakeSession:
    def __init__(self):
        self.statements = []
        self.added = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _Result()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


@pytest.fixture()
def env():
    fake = FakeSession()

    async def override():
        yield fake

    main.app.dependency_overrides[get_session] = override
    yield TestClient(main.app), fake
    main.app.dependency_overrides.clear()


def hdr(tenant=TENANT_A, user=True):
    h = {"X-Tenant-Id": str(tenant)}
    if user:
        h["X-User-Id"] = USER
    return h


def _bound_tenants(fake):
    out = set()
    for stmt in fake.statements:
        out.update(v for v in stmt.compile().params.values() if isinstance(v, uuid.UUID))
    return out


READ_ROUTES = [
    "/lifecycle/stages", "/lifecycle/events", "/lifecycle/customers", "/lifecycle/dashboard",
    "/lifecycle/funnel", f"/lifecycle/customer/{uuid.uuid4()}", f"/lifecycle/context/{uuid.uuid4()}",
]


@pytest.mark.parametrize("path", READ_ROUTES)
def test_mismatching_tenant_param_is_403(env, path):
    client, fake = env
    r = client.get(path, params={"tenant_id": str(TENANT_B)}, headers=hdr(TENANT_A))
    assert r.status_code == 403
    assert fake.statements == []  # nothing was queried


@pytest.mark.parametrize("path", READ_ROUTES)
def test_tenant_comes_from_identity_with_or_without_param(env, path):
    client, fake = env
    assert client.get(path, headers=hdr(TENANT_A)).status_code == 200  # no param needed
    assert client.get(path, params={"tenant_id": str(TENANT_A)}, headers=hdr(TENANT_A)).status_code == 200
    assert TENANT_B not in _bound_tenants(fake) and TENANT_A in _bound_tenants(fake)


def test_two_tenants_each_scoped_to_own_identity(env):
    client, fake = env
    client.get("/lifecycle/stages", headers=hdr(TENANT_B))
    assert TENANT_B in _bound_tenants(fake) and TENANT_A not in _bound_tenants(fake)


def test_write_routes_refuse_other_tenant(env):
    client, fake = env
    q = {"tenant_id": str(TENANT_B)}
    assert client.post("/lifecycle/stages", params=q, headers=hdr(TENANT_A)).status_code == 403
    assert client.put(f"/lifecycle/stages/{uuid.uuid4()}", params=q, json={"name": "x"}, headers=hdr(TENANT_A)).status_code == 403
    body = {"customer_id": str(uuid.uuid4()), "to_stage": "Active"}
    assert client.post("/lifecycle/transition", params=q, json=body, headers=hdr(TENANT_A)).status_code == 403
    sale = {"tenant_id": str(TENANT_B), "customer_id": str(uuid.uuid4()), "deal_id": str(uuid.uuid4())}
    assert client.post("/lifecycle/from-sale", json=sale, headers=hdr(TENANT_A)).status_code == 403
    journey = {"tenant_id": str(TENANT_B), "customer_id": str(uuid.uuid4()), "cancel_event_id": str(uuid.uuid4()),
               "outcome": "accepted"}
    assert client.post("/lifecycle/from-journey", json=journey, headers=hdr(TENANT_A)).status_code == 403
    assert fake.statements == [] and fake.added == []


def test_bridge_with_matching_or_absent_body_tenant_works_without_user_id(env):
    """Sales' close-won / close-lost bridges sign only X-Tenant-Id (no user id)."""
    client, fake = env
    sale = {"tenant_id": str(TENANT_A), "customer_id": str(uuid.uuid4()), "deal_id": str(uuid.uuid4())}
    assert client.post("/lifecycle/from-sale", json=sale, headers=hdr(TENANT_A, user=False)).status_code == 200
    sale.pop("tenant_id")
    assert client.post("/lifecycle/from-sale", json=sale, headers=hdr(TENANT_A, user=False)).status_code == 200
    body = {"customer_id": str(uuid.uuid4()), "to_stage": "Closed Lost"}
    r = client.post("/lifecycle/transition", params={"tenant_id": str(TENANT_A)}, json=body,
                    headers=hdr(TENANT_A, user=False))
    assert r.status_code == 200 and r.json()["from_stage"] is None
    assert {getattr(o, "tenant_id", None) for o in fake.added} == {TENANT_A}


def test_reads_still_need_a_user_id_and_tenant_header(env):
    client, _ = env
    assert client.get("/lifecycle/stages", headers=hdr(TENANT_A, user=False)).status_code == 401
    assert client.get("/lifecycle/stages", params={"tenant_id": str(TENANT_A)}).status_code == 401  # param alone is not identity


def test_no_default_tenant_fallback_in_service():
    import pathlib

    src = "".join(p.read_text(encoding="utf-8") for p in pathlib.Path(main.__file__).parent.glob("*.py"))
    for needle in ("DEFAULT_TENANT_ID", "user_metadata", "00000000-0000-0000-0000-000000000001"):
        assert needle not in src
