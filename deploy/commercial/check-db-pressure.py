"""Read-only local pool diagnosis. Never prints credentials or SQL query text."""
import json
import subprocess

ids = subprocess.check_output(["docker", "ps", "-q"], text=True).split()
containers = json.loads(subprocess.check_output(["docker", "inspect", *ids], text=True))
addresses = {network.get("IPAddress"): item["Name"].lstrip("/") for item in containers
    for network in item["NetworkSettings"]["Networks"].values()}
sql = "SELECT coalesce(client_addr::text,'local'),coalesce(state,'background'),count(*) FROM pg_stat_activity GROUP BY client_addr,state ORDER BY count(*) DESC; SELECT count(*) FROM agent_jobs WHERE status IN ('running','pause_requested','queued');"
result = subprocess.run(["docker", "exec", "-i", "omnidome-db-1", "psql", "-U", "admin", "-d", "coreconnect", "-At"],
    input=sql, text=True, capture_output=True, check=True)
for line in result.stdout.splitlines():
    columns = line.split("|")
    if len(columns) == 3:
        print(json.dumps({"service": addresses.get(columns[0].split("/")[0], columns[0]), "state": columns[1], "connections": int(columns[2])}))
    else:
        print("Active managed tasks:", line)
