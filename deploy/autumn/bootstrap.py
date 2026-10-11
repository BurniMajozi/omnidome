"""Local-only Docker bootstrap. Secrets persist in managed container environments.

Run with Linux Python from the repository's deploy/autumn directory in WSL.
No plaintext secret file is produced. Back up managed volumes and secret storage
before removing containers. Existing credentials are reused, never regenerated.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PROJECT = "omnidome-autumn"


def run(args, *, env=None, stdin=None, required=True):
    result = subprocess.run(args, cwd=HERE, env=env, input=stdin,
                            text=True, capture_output=True)
    if required and result.returncode:
        # Upstream startup errors can include connection strings. Keep raw output
        # out of the caller's transcript; inspect the service locally if needed.
        output = result.stderr + "\n" + result.stdout
        for key, value in (env or {}).items():
            if key.startswith("AUTUMN_") and len(value) >= 16:
                output = output.replace(value, "[redacted]")
        import re
        output = re.sub(r"postgres(?:ql)?://[^\s\"']+", "[database URL redacted]", output)
        lines = [line for line in output.splitlines() if any(word in line.lower()
                 for word in ("error", "failed", "cannot", "not found", "permission", "exception", "invalid"))]
        details = "\n".join(lines[-8:]) if lines else output[-1200:]
        raise RuntimeError("Command failed (exit " + str(result.returncode) + "): " + args[0] + " " + args[1] + "\n" + details[:1600])
    return result


def container_env(service):
    result = run(["docker", "inspect", f"{PROJECT}-{service}-1"], required=False)
    if result.returncode:
        return None
    return dict(entry.split("=", 1) for entry in json.loads(result.stdout)[0]["Config"]["Env"])


def environment():
    env = os.environ.copy()
    existing = container_env("autumn")
    postgres = container_env("postgres")
    if existing:
        env.update({"AUTUMN_DB_PASSWORD": postgres["POSTGRES_PASSWORD"],
                    "AUTUMN_ENCRYPTION_PASSWORD": existing["ENCRYPTION_PASSWORD"],
                    "AUTUMN_ENCRYPTION_IV": existing["ENCRYPTION_IV"],
                    "AUTUMN_AUTH_SECRET": existing["BETTER_AUTH_SECRET"],
                    "AUTUMN_BRIDGE_KEY": existing["OMNIDOME_BRIDGE_KEY"]})
    else:
        volume = run(["docker", "volume", "inspect", PROJECT + "_postgres"], required=False)
        if postgres or volume.returncode == 0:
            raise RuntimeError("Existing Autumn storage requires its original managed credentials")
        env.update({"AUTUMN_DB_PASSWORD": secrets.token_hex(32),
                    "AUTUMN_ENCRYPTION_PASSWORD": secrets.token_hex(32),
                    "AUTUMN_ENCRYPTION_IV": secrets.token_hex(16),
                    "AUTUMN_AUTH_SECRET": secrets.token_hex(32),
                    "AUTUMN_BRIDGE_KEY": "am_sk_live_" + secrets.token_hex(24)})
    return env


def main():
    env = environment()
    def compose(*args):
        return run(["docker", "compose", "-f", str(HERE / "compose.yml"), *args], env=env)
    compose("config", "--quiet")
    print("Configuration validated; preparing isolated containers.", flush=True)
    # Persist generated credentials in managed environments before migrations.
    compose("create")
    print("Containers prepared; waiting for storage and queue readiness.", flush=True)
    compose("up", "-d", "--wait", "--wait-timeout", "180", "postgres", "cache", "kafka", "dynamodb", "queue")
    topics = compose("exec", "-T", "kafka", "/opt/kafka/bin/kafka-topics.sh",
                     "--bootstrap-server", "localhost:9092", "--list").stdout.splitlines()
    for topic in ("events", "ownership", "commands", "catalog-invalidations-v1"):
        if "omnidome-" + topic not in topics:
            compose("exec", "-T", "kafka", "/opt/kafka/bin/kafka-topics.sh",
                    "--bootstrap-server", "localhost:9092", "--create", "--if-not-exists",
                    "--topic", "omnidome-" + topic, "--partitions", "1" if topic == "catalog-invalidations-v1" else "4", "--replication-factor", "1")
    compose("exec", "-T", "postgres", "psql", "-U", "autumn", "-d", "autumn", "-v", "ON_ERROR_STOP=1",
            "-c", "CREATE EXTENSION IF NOT EXISTS pg_trgm")
    exists = compose("exec", "-T", "postgres", "psql", "-U", "autumn", "-d", "autumn", "-Atc",
                     "SELECT to_regclass('public.organizations') IS NOT NULL").stdout.strip()
    if exists != "t":
        print("Initializing the isolated Autumn schema.", flush=True)
        compose("run", "--rm", "--no-deps", "--workdir", "/app/shared", "autumn",
                "bun", "/app/shared/node_modules/drizzle-kit/bin.cjs", "push", "--force")
    hashed = hashlib.sha256(env["AUTUMN_BRIDGE_KEY"].encode()).hexdigest()
    sql = f"""
      INSERT INTO organizations(id,slug,name,"createdAt",default_currency,config)
      VALUES('org_omnidome','omnidome','OminiDome',now(),'zar','{{}}')
      ON CONFLICT(id) DO NOTHING;
      INSERT INTO api_keys(id,name,prefix,org_id,env,hashed_key)
      VALUES('key_omnidome_bridge','OminiDome server bridge','am_sk_live_',
             'org_omnidome','live','{hashed}') ON CONFLICT(id) DO NOTHING;
    """
    run(["docker", "compose", "-f", str(HERE / "compose.yml"), "exec", "-T", "postgres",
         "psql", "-U", "autumn", "-d", "autumn", "-v", "ON_ERROR_STOP=1"], env=env, stdin=sql)
    compose("up", "-d", "autumn", "balances", "workers")
    print("Autumn isolated services started; API probe required before bridge activation.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error) if isinstance(error, RuntimeError) else "Bootstrap failed; no secrets printed", file=sys.stderr)
        sys.exit(1)
