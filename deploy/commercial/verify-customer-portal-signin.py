"""Operator diagnostic: real short-lived Supabase sign-in and portal proxy checks.

No password is read or changed, no email is sent, and each probe session is signed
out locally. Credential values are never printed or saved. Existing accounts only.
"""
import json
import os
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[2]
settings = {}
for line in (root / ".env").read_text(encoding="utf-8-sig").splitlines():
    key, sep, value = line.partition("=")
    if sep and key in {"SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"}:
        settings[key] = value.strip().strip('"').strip("'")
url = settings["SUPABASE_URL"].rstrip("/") + "/auth/v1"
admin = {"apikey":settings["SUPABASE_SERVICE_ROLE_KEY"], "Authorization":"Bearer "+settings["SUPABASE_SERVICE_ROLE_KEY"]}
public = {"apikey":settings["SUPABASE_ANON_KEY"]}
with httpx.Client(timeout=40, follow_redirects=False) as client:
    prepared_home = None
    users = client.get(url+"/admin/users",headers=admin,params={"per_page":200}).json().get("users",[])
    for email in ["burnibraai@gmail.com", "test@omnidome.local"]:
        assert any((u.get("email") or "").lower()==email for u in users), "Existing account is required"
        generated = client.post(url+"/admin/generate_link", headers=admin, json={"type":"magiclink", "email":email})
        generated.raise_for_status()
        data = generated.json()
        otp = data.get("hashed_token") or data.get("properties",{}).get("hashed_token")
        assert otp, "No probe token returned"
        verified = client.post(url+"/verify",headers=public,json={"type":"magiclink","token_hash":otp})
        verified.raise_for_status()
        session = verified.json()
        token = session["access_token"]
        try:
            profile = client.get("http://127.0.0.1:3001/api/home-dome/profile",headers={"Authorization":"Bearer "+token})
            profile.raise_for_status()
            print(json.dumps({"email":email,"real_supabase_signin":verified.status_code,"portal_profile":profile.status_code,
                "account_number":profile.json()["accountNumber"]}))
            if os.getenv("CHECK_CUSTOMER_SUPPORT") == "true":
                support = client.get("http://127.0.0.1:3001/api/orchestrator/agents", headers={"Authorization":"Bearer "+token})
                support.raise_for_status()
                data=support.json()
                rows=data if isinstance(data,list) else data["agents"]
                assert len(rows)==1 and rows[0]["agent_type"]=="customer_facing"
                rejected=client.post("http://127.0.0.1:3001/api/orchestrator/agents/invoke", headers={"Authorization":"Bearer "+token},json={"agent_type":"finance","message":"Do not run"})
                assert rejected.status_code==403
                home_response=client.get("http://127.0.0.1:3001/api/home-dome",headers={"Authorization":"Bearer "+token})
                home_response.raise_for_status()
                own=any(h["is_owner"] and h["managed_gateway"] for h in home_response.json())
                if email=="burnibraai@gmail.com":
                    assert own
                print(json.dumps({"email":email,"customer_support_catalogue":support.status_code,"staff_agent_rejected":rejected.status_code,"owns_prepared_home":own}))
            if os.getenv("CHECK_HOME_FEATURES") == "true":
                headers = {"Authorization": "Bearer " + token}
                response = client.get("http://127.0.0.1:3001/api/home-dome", headers=headers)
                response.raise_for_status()
                owned = next((row for row in response.json() if row["is_owner"] and row["managed_gateway"]), None)
                if owned:
                    prepared_home = owned["id"]
                assert prepared_home, "The prepared home must exist"
                outcomes = {}
                sections = ["media", "map", "todo"] + (["rooms"] if os.getenv("CHECK_HOME_ROOMS") == "true" else [])
                for section in sections:
                    result = client.get("http://127.0.0.1:3001/api/home-dome/" + prepared_home + "/" + section, headers=headers)
                    assert result.status_code in ({200, 409} if owned else {403, 404}), section + " access regression"
                    if section == "rooms" and owned:
                        assert result.status_code == 200 and isinstance(result.json(), list)
                    outcomes[section] = result.status_code
                if owned:
                    integrations = client.get("http://127.0.0.1:3001/api/home-dome/" + prepared_home + "/integrations", headers=headers)
                    integrations.raise_for_status()
                    assert len(integrations.json()) == 21
                    assert all(row["logo_url"].startswith("https://brands.home-assistant.io/") for row in integrations.json())
                    print(json.dumps({"brand_catalogue": 21}))
                print(json.dumps({"email": email, "private_home_features": outcomes}))
            if os.getenv("CHECK_HOME_REPORTS") == "true":
                headers = {"Authorization": "Bearer " + token}
                response = client.get("http://127.0.0.1:3001/api/home-dome", headers=headers)
                response.raise_for_status()
                owned = next((row for row in response.json() if row["is_owner"] and row["managed_gateway"]), None)
                if owned:
                    prepared_home = owned["id"]
                assert prepared_home, "The prepared home must exist"
                result = client.get("http://127.0.0.1:3001/api/home-dome/" + prepared_home + "/reports", headers=headers)
                assert result.status_code == (200 if owned else 403), "Report ownership regression"
                if owned:
                    assert result.json()["plan"] == "included" and isinstance(result.json()["series"], list)
                queue = client.get("http://127.0.0.1:3001/api/home-dome/reporting/requests", headers=headers)
                assert queue.status_code == 403, "Customers cannot read the tenant request queue"
                customer_caps = client.get("http://127.0.0.1:3001/api/home-dome/capabilities", headers=headers)
                customer_caps.raise_for_status()
                assert customer_caps.json()["can_provision"] is False
                platform_caps = client.get("http://127.0.0.1:3000/api/home-dome/capabilities", headers=headers)
                platform_caps.raise_for_status()
                platform_queue = client.get("http://127.0.0.1:3000/api/home-dome/reporting/requests", headers=headers)
                assert platform_queue.status_code == (200 if platform_caps.json()["can_provision"] else 403)
                print(json.dumps({"email": email, "home_reports": result.status_code, "customer_queue_rejected": queue.status_code,
                    "tenant_queue": platform_queue.status_code, "customer_admin_controls_hidden": True}))
        finally:
            logged_out = client.post(url+"/logout",params={"scope":"local"},headers={**public,"Authorization":"Bearer "+token})
            logged_out.raise_for_status()
