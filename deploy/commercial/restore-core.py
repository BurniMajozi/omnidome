"""Restore the known local app set after a WSL interruption; retain Autumn data."""
import subprocess

autumn = ["omnidome-autumn-" + name + "-1" for name in
    ("autumn", "balances", "workers", "kafka", "dynamodb", "queue", "cache", "postgres")]
result = subprocess.run(["docker", "stop", "-t", "3", *autumn], capture_output=True)
if result.returncode:
    raise SystemExit("Could not stop isolated Autumn services; inspect locally")
core = ["omnidome-" + name + "-1" for name in (
    "db", "knowledge_db", "admin", "billing", "agent-orchestrator", "web", "fno_intelligence", "tenant_memory", "gateway",
    "journey_engine", "compliance", "iot", "network", "support", "hr", "call_center", "inventory",
    "portal-builder", "marketing", "finance", "communication", "sales", "crm", "lifecycle",
    "knowledge_indexer")]
subprocess.run(["docker", "start", *core, "ollama"], check=True)
print("Core restored and Ollama running; Autumn stopped with persistent data retained.")
