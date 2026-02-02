from fastapi import FastAPI

from services.common.entitlements import EntitlementGuard

app = FastAPI(title="CoreConnect Gateway", version="0.1.0")

guard = EntitlementGuard(module_id="")


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/entitlements")
async def entitlements():
    state = guard.state()
    payload = state.payload or {}
    return {
        "valid": state.valid,
        "customer_id": payload.get("customer_id"),
        "plan": payload.get("plan"),
        "modules": payload.get("modules", []),
        "limits": payload.get("limits", {}),
        "issued_at": payload.get("issued_at"),
        "expires_at": payload.get("expires_at"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
