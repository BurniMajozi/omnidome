import pytest

pytest.importorskip("mcp")

from fastapi import HTTPException

from services.agent_orchestrator.routes import mcp as mcp_route

TENANT = "00000000-0000-0000-0000-000000000001"


class FakeRequest:
    def __init__(self, headers):
        self.headers = {k.lower(): v for k, v in headers.items()}


def configure(monkeypatch, key="s3cret-key", tenant=TENANT):
    monkeypatch.setattr(mcp_route.settings, "hermes_api_key", key)
    monkeypatch.setattr(mcp_route.settings, "mcp_tenant_id", tenant)


def test_valid_bearer_passes(monkeypatch):
    configure(monkeypatch)
    mcp_route._check_auth(FakeRequest({"authorization": "Bearer s3cret-key"}))


@pytest.mark.parametrize("header", [None, "", "Bearer wrong", "bearer s3cret-key", "s3cret-key", "Bearer s3cret-key "])
def test_bad_bearer_rejected(monkeypatch, header):
    configure(monkeypatch)
    headers = {} if header is None else {"authorization": header}
    with pytest.raises(HTTPException) as exc:
        mcp_route._check_auth(FakeRequest(headers))
    assert exc.value.status_code == 401


def test_empty_key_fails_closed(monkeypatch):
    configure(monkeypatch, key="")
    with pytest.raises(HTTPException) as exc:
        mcp_route._check_auth(FakeRequest({"authorization": "Bearer "}))
    assert exc.value.status_code == 503


@pytest.mark.parametrize("tenant", ["", "not-a-uuid", "   "])
def test_unconfigured_tenant_fails_closed(monkeypatch, tenant):
    configure(monkeypatch, tenant=tenant)
    with pytest.raises(HTTPException) as exc:
        mcp_route._check_auth(FakeRequest({"authorization": "Bearer s3cret-key"}))
    assert exc.value.status_code == 503


def test_tenant_comes_from_config_not_headers(monkeypatch):
    configure(monkeypatch)
    assert mcp_route._pinned_tenant() == TENANT
