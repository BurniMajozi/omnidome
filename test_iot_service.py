"""Test IoT service startup and basic CRUD."""
import os
import sys
import asyncio

# Set up environment
# Load .env file
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

os.environ.setdefault("AUTH_JWT_SECRET", "test-secret")
os.environ.setdefault("LICENSE_ENFORCEMENT", "warn")
os.environ.setdefault("IOT_TOKEN_ENCRYPTION_KEY", "test-encryption-key-32bytes!")

sys.path.insert(0, "/opt/data/workspace/omnidome")

async def test_imports():
    """Test that all IoT modules import without errors."""
    print("=== Test 1: Module Imports ===")
    try:
        from services.iot.models import (
            Base, IoTDevice, IoTRoom, IoTDeviceState, IoTEvent,
            IoTAutomation, IoTScene, IoTAlert, IoTIntegration,
        )
        from services.iot.ha_client import ha_entity_to_device_type, ha_state_to_device_status
        print("  OK  models + ha_client helpers imported")
    except Exception as e:
        print(f"  FAIL models: {e}")
        return False

    try:
        from services.iot.database import get_session, init_tables, get_session_factory
        print("  OK  database imported")
    except Exception as e:
        print(f"  FAIL database: {e}")
        return False

    try:
        from services.iot.ha_client import HARestClient, HAWebSocketClient, encrypt_token, decrypt_token
        print("  OK  ha_client imported")
    except Exception as e:
        print(f"  FAIL ha_client: {e}")
        return False

    try:
        from services.iot.main import app
        print("  OK  main.py imported, app created")
    except Exception as e:
        print(f"  FAIL main.py: {e}")
        return False

    # Test route imports
    route_modules = [
        "services.iot.routes.devices",
        "services.iot.routes.rooms",
        "services.iot.routes.cameras",
        "services.iot.routes.sensors",
        "services.iot.routes.automations",
        "services.iot.routes.scenes",
        "services.iot.routes.events",
        "services.iot.routes.alerts",
        "services.iot.routes.integrations",
    ]
    for mod in route_modules:
        try:
            __import__(mod)
            print(f"  OK  {mod}")
        except Exception as e:
            print(f"  FAIL {mod}: {e}")
            return False

    return True


async def test_encryption():
    """Test token encryption/decryption."""
    print("\n=== Test 2: Token Encryption ===")
    from services.iot.ha_client import encrypt_token, decrypt_token

    test_tokens = [
        "test-token-12345",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test",
        "a" * 1000,  # long token
    ]

    for token in test_tokens:
        try:
            encrypted = encrypt_token(token)
            decrypted = decrypt_token(encrypted)
            assert decrypted == token, f"Mismatch: {decrypted[:20]}... != {token[:20]}..."
            print(f"  OK  encrypt/decrypt ({len(token)} chars)")
        except Exception as e:
            print(f"  FAIL encrypt/decrypt: {e}")
            return False

    return True


async def test_app_routes():
    """Test that the FastAPI app has all expected routes."""
    print("\n=== Test 3: App Routes ===")
    from services.iot.main import app

    routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            for method in route.methods:
                routes.append(f"{method} {route.path}")

    expected_prefixes = [
        "GET /health",
        "GET /api/iot/devices",
        "POST /api/iot/devices",
        "GET /api/iot/rooms",
        "POST /api/iot/rooms",
        "GET /api/iot/cameras",
        "GET /api/iot/sensors",
        "GET /api/iot/automations",
        "POST /api/iot/automations",
        "GET /api/iot/scenes",
        "POST /api/iot/scenes",
        "GET /api/iot/events",
        "GET /api/iot/alerts",
        "POST /api/iot/alerts",
        "GET /api/iot/integrations",
        "POST /api/iot/integrations",
    ]

    route_str = "\n".join(routes)
    all_ok = True
    for prefix in expected_prefixes:
        if any(r.startswith(prefix) for r in routes):
            print(f"  OK  {prefix}")
        else:
            print(f"  MISSING {prefix}")
            all_ok = False

    print(f"\n  Total routes: {len(routes)}")
    return all_ok


async def test_db_connection():
    """Test database connection and table creation."""
    print("\n=== Test 4: Database Connection ===")
    from services.iot.database import init_tables
    from services.common.db import get_async_engine

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url or "localhost" not in db_url:
        print(f"  SKIP (no local DB, URL: {db_url[:50]}...)")
        return True

    try:
        await init_tables()
        print("  OK  tables created")
    except Exception as e:
        print(f"  FAIL table creation: {e}")
        return False

    return True


async def test_supabase_connection():
    """Test Supabase DB connection if credentials are available."""
    print("\n=== Test 4b: Supabase Connection ===")
    import asyncpg

    db_url = os.getenv("DATABASE_URL", "")
    if "supabase" not in db_url:
        print("  SKIP (no Supabase URL)")
        return True

    try:
        conn = await asyncpg.connect(db_url)
        result = await conn.fetchval("SELECT 1")
        assert result == 1
        print("  OK  Supabase connection works")

        # Check if IoT tables exist
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name LIKE 'iot_%'
        """)
        table_names = [t["table_name"] for t in tables]
        print(f"  Found IoT tables: {table_names}")

        await conn.close()
    except Exception as e:
        print(f"  FAIL Supabase: {e}")
        return False

    return True


async def test_health_endpoint():
    """Test the health endpoint via httpx."""
    print("\n=== Test 5: Health Endpoint ===")
    from services.iot.main import app
    from httpx import AsyncClient, ASGITransport

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200, f"Status: {resp.status_code}"
            data = resp.json()
            assert data.get("status") == "ok", f"Body: {data}"
            print(f"  OK  health endpoint: {data}")
    except Exception as e:
        print(f"  FAIL health endpoint: {e}")
        return False

    return True


async def main():
    results = []
    results.append(await test_imports())
    results.append(await test_encryption())
    results.append(await test_app_routes())
    results.append(await test_db_connection())
    results.append(await test_supabase_connection())
    results.append(await test_health_endpoint())

    print("\n" + "=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    if all(results):
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
