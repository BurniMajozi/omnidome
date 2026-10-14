"""Package the already-compiled reporting UI after recovering disk reserve."""
import json
import os
from pathlib import Path
import subprocess

source = Path("/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome")
stage_root = Path("/mnt/d/OminiDome-builds").resolve()
stage = (stage_root / "homedome-rooms-20261014110550").resolve()
assert stage_root in stage.parents, "Unsafe saved build path"
output = stage / "web-next"
assert (output / "BUILD_ID").is_file(), "Saved build is incomplete"
image = subprocess.check_output(["docker", "inspect", "--format", "{{.Image}}", "omnidome-web-1"], text=True).strip()
expected = json.loads((stage / "package.json").read_text())["dependencies"]
actual = json.loads(subprocess.check_output(["docker", "exec", "omnidome-web-1", "node", "-e",
    "process.stdout.write(JSON.stringify(require('/app/package.json').dependencies))"], text=True))
assert expected == actual, "The live runtime dependencies changed since compilation"
size = sum(p.stat().st_size for p in output.rglob("*") if p.is_file()
    and not {"cache", "standalone"}.intersection(p.relative_to(output).parts))
available = os.statvfs("/mnt/c").f_bavail * os.statvfs("/mnt/c").f_frsize
if available < 512 * 1024 * 1024 + size * 3:
    raise SystemExit("Keep the disk reserve before packaging the saved build")
target = "omnidome-homedome-web:candidate"
iid_file = stage / ("web-image-" + str(os.getpid()) + ".iid")
with (stage / "web-package.log").open("wb") as log:
    archive = subprocess.Popen(["tar", "-cf", "-", "--exclude=web-next/cache", "--exclude=web-next/standalone",
        "-C", str(source), "deploy/commercial/homedome-prebuilt-web.Dockerfile",
        "-C", str(stage), "web-next", "package.json"], stdout=subprocess.PIPE)
    built = subprocess.run(["docker", "build", "--iidfile", str(iid_file), "--build-arg", "BASE_IMAGE=" + image,
        "-f", "deploy/commercial/homedome-prebuilt-web.Dockerfile", "-t", target, "-"],
        stdin=archive.stdout, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "DOCKER_BUILDKIT": "0"})
    archive.stdout.close()
    archive.wait()
    assert built.returncode == 0 and archive.returncode == 0, "Runtime image packaging failed"
current = subprocess.check_output(["docker", "inspect", "--format", "{{.Image}}", "omnidome-web-1"], text=True).strip()
assert current == image, "The live platform changed during packaging"
print("Saved reporting build packaged; compiled bytes: " + str(size), flush=True)
subprocess.run(["bash", str(source / "deploy/commercial/deploy-homedome.sh")], check=True,
    env={**os.environ, "HOME_DOME_ROOMS_ONLY": "1", "HOME_DOME_WEB_IMAGE": iid_file.read_text().strip()})
