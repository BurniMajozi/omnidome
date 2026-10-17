"""Error hook: fingerprints, noise filtering, rate limiting and leak-free reports."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.common import error_reporting as ER  # noqa: E402


def _raise_in(path: str, func: str, exc: BaseException) -> BaseException:
    """An exception whose innermost frame looks like it came from `path` (an in-repo file)."""
    code = compile(f"def {func}():\n    raise exc\n", path, "exec")
    ns: dict = {"exc": exc}
    exec(code, ns)  # noqa: S102
    try:
        ns[func]()
    except BaseException as e:  # noqa: BLE001
        return e
    raise AssertionError


def test_fingerprint_is_stable_per_service_type_location():
    a = _raise_in("/app/services/billing/routes/x.py", "create_invoice", KeyError("a"))
    b = _raise_in("/app/services/billing/routes/x.py", "create_invoice", KeyError("completely different message"))
    c = _raise_in("/app/services/billing/routes/x.py", "create_invoice", ValueError("a"))
    d = _raise_in("/app/services/crm/routes/x.py", "create_invoice", KeyError("a"))
    ra, rb, rc, rd = (ER.build_report(e) for e in (a, b, c, d))
    assert ra["fingerprint"] == rb["fingerprint"]          # message does not change the identity
    assert len({ra["fingerprint"], rc["fingerprint"], rd["fingerprint"]}) == 3
    assert ra["service"] == "billing" and rd["service"] == "crm"
    assert ra["location"] == "services/billing/routes/x.py:create_invoice"


def test_report_never_leaks_secrets_or_pii():
    exc = _raise_in("/app/services/hr/main.py", "pay",
                    RuntimeError("login failed for jane@example.com password=Sup3rSecret token=abcdef1234567890zz 0821234567"))
    rep = ER.build_report(exc, method="POST", route="/payroll/{id}?token=zzzzzzzzzzzz")
    blob = repr(rep)
    for leak in ("jane@example.com", "Sup3rSecret", "abcdef1234567890zz", "0821234567", "zzzzzzzzzzzz"):
        assert leak not in blob
    assert all("exc" not in f.split(" in ")[0] for f in rep["frames"])   # file:line in function only, no locals/source


def test_http_client_errors_and_control_flow_are_ignored():
    class NotFound(Exception):
        status_code = 404

    class Boom(Exception):
        status_code = 503

    assert ER.is_ignored(NotFound()) and ER.is_ignored(asyncio.CancelledError()) and ER.is_ignored(KeyboardInterrupt())
    assert not ER.is_ignored(Boom()) and not ER.is_ignored(KeyError("x"))
    assert ER.report_exception(NotFound()) is None


def test_rate_limiter_windows_and_global_cap(monkeypatch):
    monkeypatch.setenv("ERROR_REPORT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("ERROR_REPORT_MAX_PER_MINUTE", "3")
    lim = ER.ErrorLimiter()
    assert lim.admit("a", now=1000.0) == (True, 0)
    assert lim.admit("a", now=1001.0) == (False, 0)         # same fingerprint inside the window: counted, not published
    assert lim.admit("a", now=1002.0) == (False, 0)
    assert lim.admit("a", now=1070.0) == (True, 2)          # next report carries the suppressed count
    assert lim.admit("b", now=1071.0) == (True, 0)
    assert lim.admit("c", now=1072.0) == (True, 0)
    assert lim.admit("d", now=1073.0) == (False, 0)         # global cap of 3 per minute reached
    assert lim.admit("d", now=1140.0) == (True, 1)          # new minute: the capped fingerprint gets through


def test_disabled_flag_and_missing_tenant_do_nothing(monkeypatch):
    exc = _raise_in("/app/services/hr/main.py", "pay", RuntimeError("x"))
    monkeypatch.setenv("ERROR_TICKETS_ENABLED", "false")
    assert ER.report_exception(exc) is None
    monkeypatch.setenv("ERROR_TICKETS_ENABLED", "true")
    monkeypatch.delenv("PLATFORM_OPS_TENANT_ID", raising=False)
    monkeypatch.delenv("DEFAULT_TENANT_ID", raising=False)
    monkeypatch.setattr(ER, "_limiter", ER.ErrorLimiter())
    assert ER.report_exception(exc) is None                  # no tenant to file it under


def test_platform_ops_tenant_wins_over_request_tenant(monkeypatch):
    ops = "11111111-1111-1111-1111-111111111111"
    monkeypatch.setenv("PLATFORM_OPS_TENANT_ID", ops)
    assert ER._target_tenant("22222222-2222-2222-2222-222222222222") == ops
    monkeypatch.delenv("PLATFORM_OPS_TENANT_ID")
    assert ER._target_tenant("22222222-2222-2222-2222-222222222222") == "22222222-2222-2222-2222-222222222222"


def test_report_publishes_through_the_bus(monkeypatch):
    seen = []

    async def fake_publish(report, tenant, affected, suppressed):
        seen.append((report, tenant, affected, suppressed))

    monkeypatch.setattr(ER, "_publish", fake_publish)
    monkeypatch.setenv("PLATFORM_OPS_TENANT_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(ER, "_limiter", ER.ErrorLimiter())
    exc = _raise_in("/app/services/hr/main.py", "pay", RuntimeError("boom"))

    async def run():
        assert ER.report_exception(exc, tenant_id="22222222-2222-2222-2222-222222222222") is not None
        assert ER.report_exception(exc, tenant_id="22222222-2222-2222-2222-222222222222") is None   # deduplicated in-window
        await asyncio.sleep(0.05)

    asyncio.run(run())
    assert len(seen) == 1 and seen[0][1] == "11111111-1111-1111-1111-111111111111"
    assert seen[0][2] == "22222222-2222-2222-2222-222222222222"


def test_uncaught_exception_in_a_real_app_raises_a_ticket_report(monkeypatch):
    """The shared production middleware (what every service uses) reports a crashing route once, redacted."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from services.common.middleware import configure_production

    seen = []

    async def fake_publish(report, tenant, affected, suppressed):
        seen.append((report, tenant))

    monkeypatch.setattr(ER, "_publish", fake_publish)
    monkeypatch.setenv("PLATFORM_OPS_TENANT_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(ER, "_limiter", ER.ErrorLimiter())
    app = FastAPI()
    configure_production(app)

    @app.get("/items/{item_id}")
    async def boom(item_id: str):
        raise KeyError("no currency for jane@example.com password=hunter2hunter2")

    @app.get("/missing")
    async def missing():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="nope")

    with TestClient(app, raise_server_exceptions=False) as client:
        codes = [client.get(f"/items/{i}").status_code for i in range(5)]
        assert client.get("/missing").status_code == 404
        import time
        time.sleep(0.3)
    assert codes == [500] * 5
    assert len(seen) == 1                                              # five crashes of one defect -> one report
    report = seen[0][0]
    assert report["exception_type"] == "KeyError"                      # the real error, not the middleware's ExceptionGroup
    assert report["route"] == "/items/{item_id}"                       # the route template, never the raw path
    assert "jane@example.com" not in repr(report) and "hunter2hunter2" not in repr(report)
