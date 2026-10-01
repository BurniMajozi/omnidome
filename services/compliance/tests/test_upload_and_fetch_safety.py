"""Upload path building (traversal) and the SSRF-guarded fetch. No network: DNS and HTTP are faked."""
import os

import httpx
import pytest

from services.common.url_safety import UnsafeUrl, validate_public_url
from services.compliance import safe_fetch, upload_safety as us

TENANT = "00000000-0000-0000-0000-000000000001"
PUBLIC = lambda host, port: ["93.184.216.34"]  # noqa: E731

EVIL_NAMES = [
    "../../etc/passwd.pdf", "..\\..\\windows\\system32\\cmd.pdf", "/etc/shadow.txt", "C:\\boot.ini.txt",
    "....//....//x.pdf", "%2e%2e%2f%2e%2e%2fetc%2fpasswd.pdf", "a\x00.exe.pdf", "..", "x.php", "x.exe",
    "evil.pdf/../../../x.pdf", "name with spaces and ;rm -rf.pdf",
]


@pytest.mark.parametrize("name", EVIL_NAMES)
def test_destination_inside_root_with_generated_name(tmp_path, name):
    try:
        dest = us.build_upload_path(TENANT, name, tmp_path)
    except us.UnsafeUpload:
        return
    assert dest.is_relative_to(tmp_path.resolve())
    assert dest.parent.name == TENANT
    assert len(dest.stem) == 32 and int(dest.stem, 16) >= 0
    assert dest.suffix in us.ALLOWED_EXTENSIONS


@pytest.mark.parametrize("tenant", ["../other", "default", "", "a/b", "..", "/etc"])
def test_tenant_dir_never_from_non_uuid(tmp_path, tenant):
    with pytest.raises(us.UnsafeUpload):
        us.build_upload_path(tenant, "a.pdf", tmp_path)


def test_tenant_dir_is_canonical_uuid(tmp_path):
    assert us.build_upload_path("00000000-0000-0000-0000-00000000ABCD", "a.pdf", tmp_path).parent.name == "00000000-0000-0000-0000-00000000abcd"


@pytest.mark.parametrize("name", ["a.exe", "a.sh", "a.php", "a.svg", "a", "a.pdf.exe"])
def test_extension_allow_list(name):
    with pytest.raises(us.UnsafeUpload):
        us.safe_extension(name)


def test_extension_from_basename_only():
    assert us.safe_extension("../../x/report.PDF") == ".pdf"
    assert us.safe_extension("C:\\dir\\sheet.xlsx") == ".xlsx"


def test_magic_and_size(monkeypatch):
    with pytest.raises(us.UnsafeUpload):
        us.check_content(".pdf", b"MZ\x90\x00 not a pdf")
    with pytest.raises(us.UnsafeUpload):
        us.check_content(".txt", b"")
    us.check_content(".pdf", b"%PDF-1.7 ...")
    monkeypatch.setenv("COMPLIANCE_MAX_UPLOAD_MB", "0.001")
    with pytest.raises(us.UnsafeUpload):
        us.check_content(".txt", b"x" * 5000)


def test_write_upload_under_tenant_dir(tmp_path):
    p = us.write_upload(TENANT, "../../Quarterly Report.pdf", b"%PDF-1.4 hello", tmp_path)
    assert p.is_file() and p.is_relative_to((tmp_path / TENANT).resolve())
    if os.name == "posix":
        assert (p.stat().st_mode & 0o111) == 0


def test_symlinked_tenant_dir_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / TENANT).symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this host")
    with pytest.raises(us.UnsafeUpload):
        us.write_upload(TENANT, "a.txt", b"hello", root)
    assert not list(outside.iterdir())


def test_is_within(tmp_path):
    assert us.is_within(tmp_path / "a" / "b", tmp_path)
    assert not us.is_within(tmp_path / ".." / "x", tmp_path)
    assert not us.is_within("/etc/passwd", tmp_path)


@pytest.mark.parametrize("url", [
    "http://example.com/", "https://127.0.0.1/", "https://localhost/", "https://[::1]/", "https://169.254.169.254/latest/meta-data/",
    "https://10.0.0.5/", "https://192.168.1.1/", "https://172.16.0.1/", "https://100.64.0.1/", "https://2130706433/",
    "https://0x7f.1/", "https://127.1/", "https://user:pw@example.com/", "https://example.com:8443/", "https://intranet/",
    "https://svc.internal/", "ftp://example.com/", "file:///etc/passwd", "https://[::ffff:127.0.0.1]/", "https://[fd00::1]/",
    "https://exa mple.com/",
])
def test_validator_blocks(url):
    with pytest.raises(UnsafeUrl):
        validate_public_url(url, resolver=PUBLIC)


def test_validator_dns_and_http_flag(monkeypatch):
    with pytest.raises(UnsafeUrl):
        validate_public_url("https://example.com/", resolver=lambda h, p: ["93.184.216.34", "127.0.0.1"])
    assert validate_public_url("https://example.com/a", resolver=PUBLIC)
    with pytest.raises(UnsafeUrl):
        validate_public_url("http://example.com/", resolver=PUBLIC, allow_http_env="COMPLIANCE_ALLOW_HTTP")
    monkeypatch.setenv("COMPLIANCE_ALLOW_HTTP", "true")
    assert validate_public_url("http://example.com/", resolver=PUBLIC, allow_http_env="COMPLIANCE_ALLOW_HTTP")


def _t(handler):
    return httpx.MockTransport(handler)


@pytest.mark.anyio
async def test_fetch_public_html():
    t = _t(lambda req: httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=b"<p>hi</p>"))
    r = await safe_fetch.fetch_public("https://example.com/x", resolver=PUBLIC, transport=t)
    assert r.content == b"<p>hi</p>" and r.content_type == "text/html"


@pytest.mark.anyio
async def test_private_target_refused_before_request():
    calls = []
    t = _t(lambda req: calls.append(req) or httpx.Response(200, headers={"content-type": "text/plain"}, content=b"x"))
    with pytest.raises(safe_fetch.FetchRefused):
        await safe_fetch.fetch_public("https://169.254.169.254/", resolver=PUBLIC, transport=t)
    assert calls == []


@pytest.mark.anyio
async def test_every_redirect_hop_revalidated():
    seen = []

    def handler(req):
        seen.append(str(req.url))
        if req.url.host == "example.com":
            return httpx.Response(302, headers={"location": "https://evil.example.org/next"})
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    with pytest.raises(safe_fetch.FetchRefused):
        await safe_fetch.fetch_public("https://example.com/", resolver=PUBLIC, transport=_t(handler))
    assert all("169.254.169.254" not in u for u in seen)


@pytest.mark.anyio
async def test_redirect_to_private_resolution_refused():
    resolver = lambda host, port: ["10.0.0.9"] if host == "rebind.example.org" else ["93.184.216.34"]  # noqa: E731
    t = _t(lambda req: httpx.Response(302, headers={"location": "https://rebind.example.org/"}))
    with pytest.raises(safe_fetch.FetchRefused):
        await safe_fetch.fetch_public("https://example.com/", resolver=resolver, transport=t)


@pytest.mark.anyio
async def test_max_three_redirects():
    def handler(req):
        n = int(req.url.path.strip("/") or 0)
        return httpx.Response(302, headers={"location": f"https://example.com/{n + 1}"})

    with pytest.raises(safe_fetch.FetchRefused, match="redirect"):
        await safe_fetch.fetch_public("https://example.com/0", resolver=PUBLIC, transport=_t(handler))


@pytest.mark.anyio
async def test_size_cap():
    t = _t(lambda req: httpx.Response(200, headers={"content-type": "text/plain"}, content=b"a" * 4096))
    with pytest.raises(safe_fetch.FetchRefused, match="large"):
        await safe_fetch.fetch_public("https://example.com/", resolver=PUBLIC, transport=t, max_bytes=1000)
    t2 = _t(lambda req: httpx.Response(200, headers={"content-type": "text/plain", "content-length": "999999"}, content=b"x"))
    with pytest.raises(safe_fetch.FetchRefused, match="large"):
        await safe_fetch.fetch_public("https://example.com/", resolver=PUBLIC, transport=t2, max_bytes=1000)


@pytest.mark.anyio
async def test_content_type_and_http_error():
    t = _t(lambda req: httpx.Response(200, headers={"content-type": "application/x-msdownload"}, content=b"MZ"))
    with pytest.raises(safe_fetch.FetchRefused, match="Content type"):
        await safe_fetch.fetch_public("https://example.com/", resolver=PUBLIC, transport=t)
    with pytest.raises(safe_fetch.FetchRefused, match="HTTP 500"):
        await safe_fetch.fetch_public("https://example.com/", resolver=PUBLIC, transport=_t(lambda r: httpx.Response(500)))


def test_max_fetch_env(monkeypatch):
    assert safe_fetch.max_fetch_bytes() == 10 * 1024 * 1024
    monkeypatch.setenv("COMPLIANCE_MAX_FETCH_MB", "2")
    assert safe_fetch.max_fetch_bytes() == 2 * 1024 * 1024
