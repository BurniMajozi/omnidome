"""Test IoT API endpoints with real HTTP requests."""
import os
import sys
import asyncio
import json

# Load .env
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
os.environ.setdefault("AUTH_MODE", "dev")
os.environ.setdefault("AUTH_ALLOW_ANONYMOUS", "true")
os.environ.setdefault("DEFAULT_USER_ID", "00000000-0000-0000-0000-000000000001")
os.environ.setdefault("DEFAULT_TENANT_ID", "00000000-0000-0000-0000-000000000001")

sys.path.insert(0, "/opt/data/workspace/omnidome")

from services.iot.main import app
from httpx import AsyncClient, ASGITransport


async def test_all():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {
            "X-User-Id": "00000000-0000-0000-0000-000000000001",
            "X-Tenant-Id": "00000000-0000-0000-0000-000000000001",
        }

        print("=== Test: Health ===")
        r = await client.get("/health")
        print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: List Devices (empty) ===")
        r = await client.get("/api/iot/devices", headers=headers)
        print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: Create Room ===")
        r = await client.post("/api/iot/rooms", headers=headers, json={
            "name": "Living Room",
            "icon": "sofa",
            "floor": 1,
            "description": "Main living area"
        })
        print(f"  {r.status_code} {r.json()}")
        room_id = r.json().get("id") if r.status_code == 201 else None

        print("\n=== Test: List Rooms ===")
        r = await client.get("/api/iot/rooms", headers=headers)
        print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: Create Device ===")
        r = await client.post("/api/iot/devices", headers=headers, json={
            "ha_entity_id": "camera.living_room",
            "ha_domain": "camera",
            "friendly_name": "Living Room Camera",
            "device_type": "camera",
            "manufacturer": "IMOU",
            "model": "Bullet 2C",
            "status": "online",
            "is_controllable": True,
            "room_id": room_id,
        })
        print(f"  {r.status_code} {r.json()}")
        device_id = r.json().get("id") if r.status_code == 201 else None

        print("\n=== Test: List Devices (with data) ===")
        r = await client.get("/api/iot/devices", headers=headers)
        data = r.json()
        print(f"  {r.status_code} items={len(data.get('items', []))}, total={data.get('total', 0)}")

        print("\n=== Test: Get Single Device ===")
        if device_id:
            r = await client.get(f"/api/iot/devices/{device_id}", headers=headers)
            print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: Create Scene ===")
        r = await client.post("/api/iot/scenes", headers=headers, json={
            "name": "Away Mode",
            "icon": "shield",
            "description": "Activate when leaving home",
            "scene_config": {"devices": []},
            "is_favorite": True,
        })
        print(f"  {r.status_code} {r.json()}")
        scene_id = r.json().get("id") if r.status_code == 201 else None

        print("\n=== Test: List Scenes ===")
        r = await client.get("/api/iot/scenes", headers=headers)
        print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: Create Alert ===")
        r = await client.post("/api/iot/alerts", headers=headers, json={
            "name": "Motion Detected",
            "severity": "info",
            "condition_type": "state_change",
            "condition_config": {"entity_id": "binary_sensor.motion", "state": "on"},
            "notify_push": True,
        })
        print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: List Alerts ===")
        r = await client.get("/api/iot/alerts", headers=headers)
        print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: Create Event ===")
        r = await client.post("/api/iot/events", headers=headers, json={
            "event_type": "device_online",
            "source": "test",
            "message": "Device came online",
            "data": {"device_id": device_id or "test"},
        })
        print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: List Events ===")
        r = await client.get("/api/iot/events", headers=headers)
        print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: Create Automation ===")
        r = await client.post("/api/iot/automations", headers=headers, json={
            "name": "Night Mode",
            "description": "Turn off lights at midnight",
            "trigger_type": "schedule",
            "trigger_config": {"cron": "0 0 * * *"},
            "actions": [{"domain": "light", "service": "turn_off"}],
        })
        print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: List Automations ===")
        r = await client.get("/api/iot/automations", headers=headers)
        print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: Filter Devices by Type ===")
        r = await client.get("/api/iot/devices?device_type=camera", headers=headers)
        print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: Get Room Devices ===")
        if room_id:
            r = await client.get(f"/api/iot/rooms/{room_id}/devices", headers=headers)
            print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: 404 Handling ===")
        r = await client.get("/api/iot/devices/nonexistent-id", headers=headers)
        print(f"  {r.status_code} {r.json()}")

        print("\n=== Test: Delete Device ===")
        if device_id:
            r = await client.delete(f"/api/iot/devices/{device_id}", headers=headers)
            print(f"  {r.status_code}")

        print("\n=== Test: Delete Room ===")
        if room_id:
            r = await client.delete(f"/api/iot/rooms/{room_id}", headers=headers)
            print(f"  {r.status_code}")

        print("\n=== All endpoint tests complete ===")


if __name__ == "__main__":
    asyncio.run(test_all())
