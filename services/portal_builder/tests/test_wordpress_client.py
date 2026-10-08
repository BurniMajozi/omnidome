import asyncio
import json

import httpx
import pytest

from services.portal_builder import wordpress_client as wp


def test_mcp_handshake_discovery_execute_and_close(monkeypatch):
    seen = []
    def handler(request):
        if request.method == "DELETE":
            seen.append("close")
            assert request.headers["Mcp-Session-Id"] == "session-1"
            return httpx.Response(204)
        body = json.loads(request.content)
        method = body["method"]
        seen.append(method)
        if method == "initialize":
            result = {"protocolVersion": wp.PROTOCOL}
        else:
            assert request.headers["Mcp-Session-Id"] == "session-1"
            if method == "notifications/initialized":
                return httpx.Response(202)
            name = body["params"]["name"]
            data = {"abilities": [{"name": "omnidome/site-info"}, {"name": "evil/delete"}]} if "discover" in name else {"success": True, "data": {"site_name": "Test"}}
            result = {"content": [{"type": "text", "text": json.dumps(data)}]}
        return httpx.Response(200, headers={"Mcp-Session-Id": "session-1"}, json={"jsonrpc": "2.0", "id": body["id"], "result": result})
    monkeypatch.setattr(wp, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(wp, "_resolver", lambda *args: ["93.184.216.34"])
    async def run():
        async with wp.WordPressClient("https://wordpress.example", "user", "secret") as client:
            assert await client.discover() == ["omnidome/site-info"]
            assert await client.execute("omnidome/site-info", {}) == {"site_name": "Test"}
            with pytest.raises(wp.WordPressError):
                await client.execute("evil/delete", {})
    asyncio.run(run())
    assert seen == ["initialize", "notifications/initialized", "tools/call", "tools/call", "close"]


@pytest.mark.parametrize("url", ["http://example.com", "https://127.0.0.1", "https://user:pass@example.com", "https://example.com/wp-json/mcp", "https://example.com?key=secret"])
def test_reject_unsafe_sites(url, monkeypatch):
    monkeypatch.setattr(wp, "_resolver", lambda *args: ["93.184.216.34"])
    with pytest.raises(wp.WordPressError):
        asyncio.run(wp.site_url(url))


def test_remote_errors_are_sanitized():
    with pytest.raises(wp.WordPressError) as error:
        wp.tool_data({"isError": True, "content": [{"text": "credential=secret"}]})
    assert "secret" not in str(error.value)


def test_sse_rpc_response_and_redirect_refusal(monkeypatch):
    def handler(request):
        body = json.loads(request.content)
        wire = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {"value": "fibre"}})
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=f": ping\n\nevent: message\ndata: {wire}\n\n")
    monkeypatch.setattr(wp, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(wp, "_resolver", lambda *args: ["93.184.216.34"])
    async def run():
        client = wp.WordPressClient("https://wordpress.example", "user", "secret")
        try:
            assert await client.rpc("tools/list", {}) == {"value": "fibre"}
        finally:
            await client.http.aclose()
        monkeypatch.setattr(wp, "_transport", httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "https://evil.example"})))
        client = wp.WordPressClient("https://wordpress.example", "user", "secret")
        try:
            with pytest.raises(wp.WordPressError):
                await client.rpc("initialize", {})
        finally:
            await client.http.aclose()
    asyncio.run(run())
