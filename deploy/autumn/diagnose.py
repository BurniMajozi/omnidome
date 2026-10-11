"""Print bounded local runtime diagnostics with managed secrets redacted."""
import json
import re
import subprocess

for service in ("autumn", "balances", "workers", "kafka", "dynamodb"):
    name = "omnidome-autumn-" + service + "-1"
    inspected = subprocess.run(["docker", "inspect", name], capture_output=True, text=True)
    if inspected.returncode:
        print(service + ": absent")
        continue
    container = json.loads(inspected.stdout)[0]
    state = container["State"]
    print(json.dumps({"service": service, "status": state["Status"],
        "exit_code": state["ExitCode"], "oom": state["OOMKilled"], "restarts": container["RestartCount"]}))
    values = [item.split("=", 1)[1] for item in container["Config"]["Env"]
        if any(word in item.split("=", 1)[0] for word in ("SECRET", "KEY", "PASSWORD", "DATABASE", "IV"))]
    logs = subprocess.run(["docker", "logs", "--tail", "80", name], capture_output=True, text=True)
    output = logs.stdout + logs.stderr
    for value in values:
        if len(value) >= 12:
            output = output.replace(value, "[redacted]")
    output = re.sub(r"postgres(?:ql)?://[^\s\"']+", "[database URL redacted]", output)
    lines = [line for line in output.splitlines() if re.search(r"error|missing|fatal|segmentation|invalid|failed|ready|listening", line, re.I)]
    print("\n".join(line[:300] for line in lines[-6:]))
