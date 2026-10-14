"""Build the platform UI with a private D: output mount; never alter the live container."""
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

source = Path("/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome")
stage_root = Path("/mnt/d/OminiDome-builds").resolve()
stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
stage = (stage_root / ("homedome-rooms-" + stamp)).resolve()
assert stage_root in stage.parents, "Unsafe build output path"
if os.statvfs("/mnt/c").f_bavail * os.statvfs("/mnt/c").f_frsize < 512 * 1024 * 1024:
    raise SystemExit("Keep 512 MiB free on C: before creating the small build overlay")
image = subprocess.check_output(["docker", "inspect", "--format", "{{.Image}}", "omnidome-web-1"], text=True).strip()
builder = "omnidome-room-web-build-" + stamp
target = "omnidome-homedome-web:candidate"
iid_file = stage / "web-image.iid"
output = stage / "web-next"
output.mkdir(parents=True)
log_path = stage / "web-build.log"
create = ["docker", "create", "--name", builder, "--memory", "2560m", "--cpu-period", "100000", "--cpu-quota", "100000",
    "--env", "NODE_OPTIONS=--max-old-space-size=1792", "--mount", "type=bind,src=" + str(output) + ",dst=/app/.next",
    ]
if os.getenv("HOME_DOME_WEB_CACHE_DIR"):
    cache = Path(os.environ["HOME_DOME_WEB_CACHE_DIR"]).resolve()
    assert stage_root in cache.parents and cache.name == "cache" and cache.is_dir(), "Unsafe cache path"
    create += ["--mount", "type=bind,src=" + str(cache) + ",dst=/app/.next/cache"]
create += ["--entrypoint", "sh", image, "-c", "npm run build -- --webpack"]
subprocess.run(create, check=True, stdout=subprocess.DEVNULL)
try:
    for item in ["components", "lib", "app"]:
        subprocess.run(["docker", "cp", str(source / "apps/web" / item) + "/.", builder + ":/app/" + item], check=True)
    subprocess.run(["docker", "cp", str(source / "apps/web/proxy.ts"), builder + ":/app/proxy.ts"], check=True)
    print("Platform build output: " + str(stage), flush=True)
    with log_path.open("wb") as log:
        subprocess.run(["docker", "start", "-a", builder], stdout=log, stderr=subprocess.STDOUT, check=True)
    result = subprocess.check_output(["docker", "inspect", "--format", "{{.State.ExitCode}}", builder], text=True).strip()
    if result != "0" or not (output / "BUILD_ID").is_file():
        raise SystemExit("Platform build failed; see the private staging build log")
    subprocess.run(["docker", "cp", builder + ":/app/package.json", str(stage / "package.json")], check=True)
    size = sum(p.stat().st_size for p in output.rglob("*") if p.is_file() and not {"cache", "standalone"}.intersection(p.relative_to(output).parts))
    available = os.statvfs("/mnt/c").f_bavail * os.statvfs("/mnt/c").f_frsize
    if available < 512 * 1024 * 1024 + size * 3:
        raise SystemExit("Compiled platform build is preserved on D:; more C: space is needed for its image overlay")
    with log_path.open("ab") as log:
        archive = subprocess.Popen(["tar", "-cf", "-", "--exclude=web-next/cache", "--exclude=web-next/standalone", "-C", str(source), "deploy/commercial/homedome-prebuilt-web.Dockerfile",
            "-C", str(stage), "web-next", "package.json"], stdout=subprocess.PIPE)
        built = subprocess.run(["docker", "build", "--iidfile", str(iid_file), "--build-arg", "BASE_IMAGE=" + image, "-f", "deploy/commercial/homedome-prebuilt-web.Dockerfile", "-t", target, "-"],
            stdin=archive.stdout, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "DOCKER_BUILDKIT": "0"})
        archive.stdout.close()
        archive.wait()
        if built.returncode or archive.returncode:
            raise SystemExit("Platform image overlay failed; build output remains on D:")
    current = subprocess.check_output(["docker", "inspect", "--format", "{{.Image}}", "omnidome-web-1"], text=True).strip()
    if current != image:
        raise SystemExit("The live platform changed during this build; no deployment was performed")
    print("Platform runtime image built; compiled bytes: " + str(size), flush=True)
    subprocess.run(["bash", str(source / "deploy/commercial/deploy-homedome.sh")], check=True,
        env={**os.environ, "HOME_DOME_ROOMS_ONLY": "1", "HOME_DOME_WEB_IMAGE": iid_file.read_text().strip()})
finally:
    subprocess.run(["docker", "rm", builder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

