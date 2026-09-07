import json
import subprocess

try:
    out = subprocess.check_output(["railway", "status", "--json"], encoding="utf-8", shell=True)
    data = json.loads(out)
    env = data["environments"]["edges"][0]["node"]
    print(f"Environment: {env['name']}")
    print("-" * 55)
    print(f"{'Service':<24} | {'Status':<12} | {'Updated'}")
    print("-" * 55)
    for edge in env["serviceInstances"]["edges"]:
        node = edge["node"]
        sname = node["serviceName"]
        latest = node.get("latestDeployment")
        status = latest.get("status", "UNKNOWN") if latest else "NO_DEPLOY"
        domains = [d["domain"] for d in node.get("domains", {}).get("serviceDomains", [])]
        custom_domains = [d["domain"] for d in node.get("domains", {}).get("customDomains", [])]
        dom_str = ", ".join(domains + custom_domains)
        print(f"{sname:<24} | {status:<12} | {dom_str}")
except Exception as e:
    print(f"Error: {e}")
