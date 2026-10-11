"""Server-only entitlement adapter. This adapter never calls Autumn's paid attach API."""
import os
import httpx


class AutumnError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class AutumnClient:
    def __init__(self, base_url=None, secret=None, transport=None):
        self.base_url = (base_url or os.getenv("AUTUMN_API_URL", "http://autumn:8080")).rstrip("/")
        self.secret = secret or os.getenv("AUTUMN_SECRET_KEY")
        self.transport = transport

    async def call(self, action, payload):
        allowed = {"customers.get_or_create", "features.get", "features.create", "balances.create",
                   "balances.list", "balances.delete", "check", "balances.finalize"}
        if action not in allowed:
            raise ValueError("Only entitlement operations are allowed")
        if not self.secret:
            raise AutumnError("not_configured")
        try:
            async with httpx.AsyncClient(timeout=20, transport=self.transport) as client:
                response = await client.post(self.base_url + "/v1/" + action, json=payload,
                    headers={"Authorization": "Bearer " + self.secret, "x-api-version": "2.5.0"})
        except httpx.HTTPError:
            raise AutumnError("unavailable") from None
        if response.status_code >= 400:
            raise AutumnError(f"http_{response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise AutumnError("invalid_response") from None

    async def ensure_feature(self):
        try:
            await self.call("features.get", {"feature_id": "omnidome_ai_credits"})
        except AutumnError as exc:
            if exc.code != "http_404":
                raise
            try:
                await self.call("features.create", {"feature_id": "omnidome_ai_credits", "name": "OminiDome AI credits", "type": "metered", "consumable": True})
            except AutumnError as created:
                if created.code != "http_409":
                    raise
