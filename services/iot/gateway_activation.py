"""Activate the prepared home gateway from inside HomeDome, so customers never open Home Assistant.

Fresh gateway: HomeDome completes Home Assistant's onboarding itself with a generated administrator
(nobody ever sees or needs that password). Already-onboarded gateway: the operator supplies the existing
administrator login once. Either way only an encrypted long-lived access key is kept; passwords are
used for one request and discarded.
"""
import secrets
from urllib.parse import quote

import httpx

from services.iot.ha_client import HAWebSocketClient
from services.iot.managed_gateway import INTERNAL_URL, check_target

CLIENT_ID = "http://omnidome-homedome/"
REDIRECT = CLIENT_ID + "?auth_callback=1"


class GatewayUnavailable(RuntimeError):
    pass


class NeedsCredentials(RuntimeError):
    """The gateway was onboarded outside HomeDome."""


class BadCredentials(RuntimeError):
    pass


def http():
    check_target(INTERNAL_URL)
    return httpx.AsyncClient(base_url=INTERNAL_URL, timeout=httpx.Timeout(20.0, connect=5.0),
        follow_redirects=False, trust_env=False)


async def gateway_state():
    """fresh | needs_credentials | unavailable."""
    try:
        async with http() as client:
            resp = await client.get("/api/onboarding")
    except Exception:
        return "unavailable"
    if resp.status_code == 200 and any(s.get("step") == "user" and not s.get("done") for s in resp.json()):
        return "fresh"
    return "needs_credentials"


async def exchange(client, code):
    resp = await client.post("/auth/token", data={"grant_type": "authorization_code", "code": code, "client_id": CLIENT_ID})
    resp.raise_for_status()
    return resp.json()["access_token"]


async def onboard(client, name):
    resp = await client.post("/api/onboarding/users", json={"client_id": CLIENT_ID, "name": name[:60],
        "username": "homedome-" + secrets.token_hex(4), "password": secrets.token_urlsafe(24), "language": "en"})
    resp.raise_for_status()
    access = await exchange(client, resp.json()["auth_code"])
    headers = {"Authorization": f"Bearer {access}"}
    for step, body in (("core_config", {}), ("analytics", {}), ("integration", {"client_id": CLIENT_ID, "redirect_uri": REDIRECT})):
        done = await client.post(f"/api/onboarding/{step}", json=body, headers=headers)
        if done.status_code >= 500:
            done.raise_for_status()
    return access


async def login(client, username, password):
    flow = await client.post("/auth/login_flow", json={"client_id": CLIENT_ID, "handler": ["homeassistant", None], "redirect_uri": REDIRECT})
    flow.raise_for_status()
    step = await client.post(f"/auth/login_flow/{quote(flow.json()['flow_id'], safe='')}",
        json={"client_id": CLIENT_ID, "username": username, "password": password})
    data = step.json() if step.content else {}
    if step.status_code >= 400 or data.get("type") != "create_entry":
        raise BadCredentials("The gateway administrator username or password was not accepted")
    return await exchange(client, data["result"])


async def activate(home_name, username=None, password=None):
    """Return a long-lived access key for the managed gateway."""
    state = await gateway_state()
    if state == "unavailable":
        raise GatewayUnavailable("The home gateway is not reachable yet. Try again in a minute.")
    if state != "fresh" and not (username and password):
        raise NeedsCredentials("This gateway was already set up. Enter its administrator login once to link it.")
    async with http() as client:
        access = await onboard(client, home_name) if state == "fresh" else await login(client, username, password)
    ws = HAWebSocketClient(INTERNAL_URL, access, managed_gateway=True)
    try:
        await ws.connect()
        if state == "fresh":
            await ws.request("config/core/update", time_zone="Africa/Johannesburg", country="ZA", currency="ZAR",
                language="en", unit_system="metric")
        return await ws.request("auth/long_lived_access_token", client_name="HomeDome", lifespan=3650)
    finally:
        await ws.close()
