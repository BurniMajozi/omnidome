"""
AgentMail Polling Watcher for omnidome@agentmail.to
Polls the inbox until the first email arrives, then outputs and summarizes it.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

INBOX_ID = "omnidome@agentmail.to"
ENCODED_INBOX = "omnidome%40agentmail.to"
BASE_URL = "https://api.agentmail.to/v0"


def get_api_key():
    key = os.environ.get("AGENTMAIL_API_KEY")
    if key:
        return key.strip()

    # Check Windows Registry HKCU\Environment
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as rkey:
                val, _ = winreg.QueryValueEx(rkey, "AGENTMAIL_API_KEY")
                if val:
                    return str(val).strip()
        except Exception:
            pass

    # Search in .env files
    locations = [
        os.path.expanduser("~/.env"),
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.getcwd(), "apps/web/.env.local"),
        os.path.join(os.getcwd(), ".env.local"),
    ]
    for env_path in locations:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.strip().startswith("AGENTMAIL_API_KEY="):
                            val = line.split("=", 1)[1].strip().strip("\"'")
                            if val:
                                return val
            except Exception:
                pass
    return None



def fetch_threads(api_key):
    url = f"{BASE_URL}/inboxes/{ENCODED_INBOX}/threads?limit=10"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_message(api_key, message_id):
    url = f"{BASE_URL}/inboxes/{ENCODED_INBOX}/messages/{message_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    api_key = get_api_key()
    if not api_key:
        print("ERROR: AGENTMAIL_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    print(f"Polling inbox {INBOX_ID} on AgentMail API...")
    poll_count = 0
    while True:
        poll_count += 1
        try:
            data = fetch_threads(api_key)
            threads = data.get("threads", [])
            if threads:
                print(f"\n[!] INCOMING EMAIL DETECTED! Total threads: {len(threads)}")
                first_thread = threads[0]
                last_msg_id = first_thread.get("last_message_id")
                if last_msg_id:
                    msg = fetch_message(api_key, last_msg_id)
                    print("\n" + "=" * 50)
                    print("RECEIVED MESSAGE DETAILS:")
                    print("=" * 50)
                    print(f"From: {msg.get('from')}")
                    print(f"To: {', '.join(msg.get('to', []))}")
                    print(f"Subject: {msg.get('subject')}")
                    print(f"Timestamp: {msg.get('timestamp')}")
                    print("-" * 50)
                    print("Body Preview / Text:")
                    print(msg.get("text") or msg.get("preview") or "[No text body]")
                    print("=" * 50)
                else:
                    print(json.dumps(first_thread, indent=2))
                return
            else:
                print(f"[{poll_count}] Inbox {INBOX_ID} is empty. Waiting 10s...", flush=True)
        except urllib.error.HTTPError as e:
            print(f"HTTP Error {e.code}: {e.read().decode('utf-8', errors='ignore')}", file=sys.stderr)
            if e.code in (401, 403):
                print("Authentication failed. Please verify your AGENTMAIL_API_KEY.", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"Error polling AgentMail: {e}", file=sys.stderr)

        time.sleep(10)


if __name__ == "__main__":
    main()
