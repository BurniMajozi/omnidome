"""Local isolated entitlement probe. No payments or real tenant mutations."""
import json
import subprocess
import sys
import time
import uuid
import urllib.request
import urllib.error


def main():
    raw = subprocess.check_output(["docker", "inspect", "omnidome-autumn-autumn-1"], text=True)
    env = dict(item.split("=", 1) for item in json.loads(raw)[0]["Config"]["Env"])
    key = env["OMNIDOME_BRIDGE_KEY"]
    customer = "omnidome_probe_" + uuid.uuid4().hex
    balance = customer + ":grant"
    lock = customer + ":lock"
    feature = "omnidome_ai_credits"
    base = "http://127.0.0.1:8188/v1/"

    def call(action, payload, expected=(200, 201)):
        req = urllib.request.Request(base + action, data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "x-api-version": "2.5.0"})
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                status, data = response.status, json.load(response)
        except urllib.error.HTTPError as error:
            status = error.code
            try:
                data = json.load(error)
            except ValueError:
                data = {}
        if status not in ((expected,) if isinstance(expected, int) else expected):
            # Never print raw upstream errors or authentication headers.
            print(json.dumps({"action": action, "status": status,
                "error_code": str(data.get("code", "unknown"))[:80]}), flush=True)
            raise RuntimeError("Entitlement probe failed")
        print(json.dumps({"action": action, "status": status}), flush=True)
        if status == 404:
            data["_probe_not_found"] = True
        return data

    existing = call("features.get", {"feature_id": feature}, expected=(200, 404))
    if existing.get("_probe_not_found"):
        call("features.create", {"feature_id": feature, "name": "OminiDome AI credits", "type": "metered", "consumable": True})
    call("customers.get_or_create", {"customer_id": customer})
    payload = {"customer_id": customer, "feature_id": feature, "balance_id": balance,
        "included_grant": 100, "expires_at": int((time.time() + 3600) * 1000)}
    created = False
    try:
        call("balances.create", payload)
        created = True
        call("balances.create", payload, expected=409)
        receipt = call("balances.list", {"customer_id": customer, "feature_id": feature})
        matches = [row for row in receipt.get("list", []) if row.get("id") == balance]
        assert len(matches) == 1 and matches[0]["included_grant"] == 100
        result = call("check", {"customer_id": customer, "feature_id": feature,
            "required_balance": 10, "lock": {"enabled": True, "lock_id": lock,
                "expires_at": int((time.time() + 300) * 1000), "overage_behavior": "reject"}})
        assert result.get("allowed") is True
        call("balances.finalize", {"lock_id": lock, "action": "release"})
        result = call("check", {"customer_id": customer, "feature_id": feature, "required_balance": 100})
        assert result.get("allowed") is True
        print("Stripe-free grant, duplicate receipt, reservation and release verified.", flush=True)
    finally:
        if created:
            call("balances.delete", {"customer_id": customer, "balance_id": balance})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Probe incomplete; no bridge activation or customer charges.", file=sys.stderr)
        sys.exit(1)
