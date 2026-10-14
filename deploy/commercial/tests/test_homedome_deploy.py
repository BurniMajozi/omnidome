"""Exercise the actual Bash deployment without touching services or images."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
TOOLS = Path(__file__).with_name("fake_homedome_deploy_tool.py")

@unittest.skipUnless(os.name == "posix", "Run under WSL for Bash deployment coverage")
class DeployTests(unittest.TestCase):
    def exercise(self, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            tools = workspace / "bin"
            tools.mkdir()
            for name in ["docker", "df", "du", "tar", "rsync", "systemctl", "sleep", "seq", "curl"]:
                tool = tools / name
                tool.write_text(TOOLS.read_text())
                tool.chmod(0o755)
            source = workspace / "source"
            (source / "deploy/commercial").mkdir(parents=True)
            (source / "deploy/commercial/agent-work-deploy-ready.py").write_text("pass\n")
            state_path = workspace / "state.json"
            state_path.write_text(json.dumps({"calls": [], "live": {}, "tags": {}}))
            env = {**os.environ, "PATH": str(tools) + ":" + os.environ["PATH"],
                "FAKE_DEPLOY_STATE": str(state_path), "HOME_DOME_WORKSPACE_ROOT": str(workspace),
                "HOME_DOME_SOURCE_ROOT": str(source), "HOME_DOME_BACKEND_ONLY": "1", **overrides}
            result = subprocess.run(["bash", str(ROOT / "deploy/commercial/deploy-homedome.sh")], env=env,
                text=True, capture_output=True, timeout=20)
            state = json.loads(state_path.read_text())
            metadata = workspace / "build_logs/homedome-rollback.images"
            return result, state, metadata.read_text() if metadata.exists() else ""

    def test_success_uses_only_runtime_tag_and_bounded_rollback_metadata(self):
        result, state, metadata = self.exercise()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state["live"]["iot"], "sha256:" + "b" * 64)
        self.assertEqual(len(state["tags"]), 1)
        self.assertEqual(metadata, "iot-live sha256:" + "a" * 64 + "\n")

    def test_failed_health_restores_original_sha_without_snapshot_tags(self):
        result, state, _ = self.exercise(FAKE_HEALTH_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state["live"]["iot"], "sha256:" + "a" * 64)
        self.assertIn("Rolled back to the original image IDs", result.stdout)
        self.assertEqual(len(state["tags"]), 1)

    def test_concurrent_deployment_exits_before_tagging_or_restarting(self):
        result, state, metadata = self.exercise(FAKE_CONCURRENT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Concurrent deployment detected", result.stdout)
        self.assertFalse(state["tags"])
        self.assertFalse(metadata)

    def test_prebuilt_web_only_does_not_build_other_services(self):
        result, state, _ = self.exercise(HOME_DOME_BACKEND_ONLY="", HOME_DOME_WEB_ONLY="1",
            HOME_DOME_ROOMS_ONLY="1", HOME_DOME_WEB_IMAGE="existing-candidate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(call[:2] == ["docker", "build"] for call in state["calls"]))
        self.assertEqual(state["live"]["web"], "sha256:" + "c" * 64)

if __name__ == "__main__":
    unittest.main()
