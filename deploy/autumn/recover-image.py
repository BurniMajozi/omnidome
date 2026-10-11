"""Recover a completed dependency-install container without another download.

Only use for the exact upstream checkout and successful install described in
README. Stream filesystem data, omit disposable cache/Git metadata, and import
the final runtime image. Never touches OminiDome's data volumes.
"""
import subprocess
import sys
import tarfile

container = sys.argv[1]
check = subprocess.run(["docker", "inspect", "--format", "{{.State.ExitCode}} {{.State.Status}}", container], capture_output=True, text=True, check=True)
if check.stdout.strip() != "0 exited":
    raise SystemExit("Recovery requires a completed successful install container")
export = subprocess.Popen(["docker", "export", container], stdout=subprocess.PIPE)
importer = subprocess.Popen(["docker", "import", "--change", "ENV NODE_ENV=production",
    "--change", "WORKDIR /app/server", "--change", "EXPOSE 8080",
    "--change", 'CMD ["bun", "start"]', "-", "omnidome-autumn:89b5b6dc"], stdin=subprocess.PIPE)
try:
    with tarfile.open(fileobj=export.stdout, mode="r|") as source:
        with tarfile.open(fileobj=importer.stdin, mode="w|") as target:
            for member in source:
                name = member.name.removeprefix("./").rstrip("/")
                excluded = ("root/.bun/install/cache", "app/.git")
                if name.startswith("tmp/") or any(name == path or name.startswith(path+"/") for path in excluded):
                    continue
                if member.islnk() and any(member.linkname.startswith(path+"/") for path in excluded):
                    raise RuntimeError("Excluded cache is referenced by runtime; refuse incomplete image")
                target.addfile(member, source.extractfile(member) if member.isfile() else None)
    importer.stdin.close()
    if export.wait() or importer.wait():
        raise RuntimeError("Image stream failed")
    print("Recovered pinned Autumn image; runtime probe is still required.")
except Exception:
    export.terminate()
    importer.terminate()
    raise
