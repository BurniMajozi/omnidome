"""Pure tests for the Market Watch URL validator (SSRF guard). No network: DNS is patched.

Run with cwd = services/fno_intelligence:  python -m pytest tests/test_market_url_validation.py -q
"""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.fno_intelligence import market_routes as mr  # noqa: E402
from services.fno_intelligence.market_routes import UnsafeWatchUrl, validate_watch_url  # noqa: E402

PUBLIC = lambda host, port: ["93.184.216.34"]  # noqa: E731


def ok(url, **kw):
    return validate_watch_url(url, resolver=kw.pop("resolver", PUBLIC), **kw)


def bad(url, **kw):
    with pytest.raises(UnsafeWatchUrl):
        validate_watch_url(url, resolver=kw.pop("resolver", PUBLIC), **kw)


def test_public_https_is_accepted():
    assert ok("https://www.rival-isp.co.za/plans") == "https://www.rival-isp.co.za/plans"
    assert ok("https://rival.example:443/x")


def test_http_needs_the_env_flag(monkeypatch):
    bad("http://rival.example/plans")
    monkeypatch.setenv("MARKET_ALLOW_HTTP", "true")
    assert ok("http://rival.example/plans")
    bad("http://rival.example:8080/plans")


@pytest.mark.parametrize("url", [
    "ftp://rival.example/x", "file:///etc/passwd", "gopher://rival.example", "javascript:alert(1)",
    "//rival.example/x", "https:///path", "https://",
])
def test_bad_schemes_and_shapes(url):
    bad(url)


@pytest.mark.parametrize("url", [
    "https://127.0.0.1/", "https://10.0.0.5/", "https://172.16.0.1/", "https://172.31.255.255/",
    "https://192.168.1.1/", "https://169.254.169.254/latest/meta-data/", "https://100.64.0.1/",
    "https://100.100.100.200/", "https://0.0.0.0/", "https://224.0.0.1/", "https://255.255.255.255/",
    "https://[::1]/", "https://[::]/", "https://[fe80::1]/", "https://[fc00::1]/", "https://[fd00::1]/",
    "https://[::ffff:127.0.0.1]/", "https://[::ffff:169.254.169.254]/", "https://[64:ff9b::7f00:1]/",
    "https://[2002:7f00:1::]/",
])
def test_private_and_special_ip_literals_are_rejected(url):
    bad(url)


def test_public_ip_literal_is_accepted():
    assert ok("https://93.184.216.34/plans")
    assert ok("https://[2606:2800:220:1:248:1893:25c8:1946]/plans")


@pytest.mark.parametrize("url", [
    "https://2130706433/",          # decimal 127.0.0.1
    "https://0x7f000001/",          # hex
    "https://0x7f.0.0.1/",
    "https://0177.0.0.1/",          # octal
    "https://127.1/",               # short form
    "https://127.0.0.1.1/",
    "https://017700000001/",
    "https://１２７．０．０．１/",   # full-width digits and dots (NFKC -> 127.0.0.1)
])
def test_ip_obfuscation_tricks_are_rejected(url):
    bad(url)


@pytest.mark.parametrize("url", [
    "https://user:pass@rival.example/", "https://user@rival.example/",
    "https://rival.example@127.0.0.1/", "https://rival.example%40evil.example@127.0.0.1/",
    "https://127.0.0.1#@rival.example/", "https://evil.example\\@rival.example/",
    "https://rival.example:pass@evil.example/",
])
def test_userinfo_and_at_tricks_are_rejected(url):
    bad(url)


@pytest.mark.parametrize("url", [
    "https://localhost/", "https://LOCALHOST./", "https://app.localhost/", "https://intranet/",
    "https://db/", "https://printer.local/", "https://svc.internal/", "https://x.railway.internal/",
    "https://router.lan/", "https://nas.home.arpa/",
])
def test_internal_and_single_label_hosts_are_rejected(url):
    bad(url)


@pytest.mark.parametrize("url", [
    "https://rival.example:22/", "https://rival.example:8443/", "https://rival.example:80/",
    "https://rival.example:0/", "https://rival.example:99999/",
])
def test_non_standard_ports_are_rejected(url):
    bad(url)


@pytest.mark.parametrize("url", [
    "https://rival.example/a b", "https://rival.example/x\ny", "https://rival.exa\tmple/", "https://rival.example\\x/",
    "", "   ",
])
def test_whitespace_control_and_empty_are_rejected(url):
    bad(url)


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.1.2.3", "192.168.0.10", "169.254.169.254", "100.64.5.5", "::1", "fe80::1",
    "fd12::1", "::ffff:10.0.0.1",
])
def test_dns_names_resolving_to_private_addresses_are_rejected(ip):
    bad("https://rebind.evil.example/", resolver=lambda h, p: [ip])


def test_any_private_answer_among_public_ones_rejects():
    bad("https://mixed.example/", resolver=lambda h, p: ["93.184.216.34", "10.0.0.1"])


def test_unresolvable_or_empty_dns_is_rejected():
    def boom(h, p):
        raise OSError("nxdomain")
    bad("https://nope.example/", resolver=boom)
    bad("https://nope.example/", resolver=lambda h, p: [])


def test_unicode_hosts_are_idna_encoded_and_resolved():
    seen = []

    def resolver(host, port):
        seen.append(host)
        return ["93.184.216.34"]
    assert validate_watch_url("https://bücher.example/plans", resolver=resolver)
    assert seen == ["xn--bcher-kva.example"]
    # a unicode lookalike of a private name still hits the resolver and is judged by its address
    bad("https://ⓛⓞⓒⓐⓛⓗⓞⓢⓣ.example/", resolver=lambda h, p: ["127.0.0.1"])
    # U+3002 ideographic full stop is a dot after nameprep
    assert validate_watch_url("https://rival。example/", resolver=resolver)


def test_watch_cap_default_and_env(monkeypatch):
    monkeypatch.delenv("MARKET_MAX_WATCHES_PER_TENANT", raising=False)
    assert mr.max_watches_per_tenant() == 25
    monkeypatch.setenv("MARKET_MAX_WATCHES_PER_TENANT", "3")
    assert mr.max_watches_per_tenant() == 3
    monkeypatch.setenv("MARKET_MAX_WATCHES_PER_TENANT", "junk")
    assert mr.max_watches_per_tenant() == 25
