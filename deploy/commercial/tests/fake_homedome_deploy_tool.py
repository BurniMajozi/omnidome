#!/usr/bin/env python3
"""Fake external commands for isolated deployment tests; never calls Docker."""
import json
import os
from pathlib import Path
import sys

command = Path(sys.argv[0]).name
args = sys.argv[1:]
state_path = Path(os.environ["FAKE_DEPLOY_STATE"])
state = json.loads(state_path.read_text())
state["calls"].append([command, *args])
original, built = "sha256:" + "a" * 64, "sha256:" + "b" * 64
code = 0
if command == "df":
    print("Avail\n21474836480")
elif command == "du":
    print("1 source")
elif command == "seq":
    print("1")
elif command == "systemctl":
    code = 1 if "is-active" in args else 0
elif command == "docker":
    if args[0] == "inspect":
        service = args[-1].removeprefix("omnidome-").removesuffix("-1")
        print(service + "-live" if "Config.Image" in args[2] else state["live"].get(service, original))
    elif args[:2] == ["image", "inspect"]:
        print("sha256:" + "c" * 64)
    elif args[0] == "build":
        sys.stdin.buffer.read()
        assert "-t" not in args, "Build must not create historical tags"
        Path(args[args.index("--iidfile") + 1]).write_text(built)
        if os.environ.get("FAKE_CONCURRENT") == "1":
            state["live"]["iot"] = "sha256:" + "d" * 64
    elif args[0] == "tag":
        assert args[2].endswith("-live"), "Only existing runtime tags may change"
        state["tags"][args[2]] = args[1]
    elif args[:2] == ["compose", "up"]:
        for service in ["iot", "web", "agent-orchestrator"]:
            if service in args:
                state["live"][service] = state["tags"].get(service + "-live", original)
    elif args[0] == "exec":
        if "-i" in args:
            sys.stdin.buffer.read()
        elif os.environ.get("FAKE_HEALTH_FAIL") == "1":
            code = 1
state_path.write_text(json.dumps(state))
raise SystemExit(code)
