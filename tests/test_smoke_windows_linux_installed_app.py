from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SCRIPT = SCRIPTS / "smoke_windows_linux_installed_app.py"
SPEC = importlib.util.spec_from_file_location("smoke_windows_linux_installed_app", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
collector = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_windows_linux_installed_app"] = collector
SPEC.loader.exec_module(collector)


class WindowsLinuxInstalledAppCollectorTests(unittest.TestCase):
    def test_write_pending_without_binary(self) -> None:
        with TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "pending.json"

            result = collector.main([
                "--platform",
                "linux",
                "--evidence-out",
                str(evidence_path),
                "--write-pending",
            ])

            self.assertEqual(0, result)
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual("pending", evidence["status"])
            self.assertEqual("linux", evidence["platform"])
            self.assertFalse(evidence["processObserved"])
            self.assertFalse(evidence["boundaries"]["fullProductionRelease"])

    def test_validate_only_accepts_pending_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "pending.json"
            collector.write_evidence(evidence_path, collector.pending_evidence("windows", "runner unavailable"))

            result = collector.main([
                "--platform",
                "windows",
                "--evidence-out",
                str(evidence_path),
                "--validate-only",
            ])

            self.assertEqual(0, result)

    def test_collect_with_python_binary_is_unavailable_not_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "linux.json"

            result = collector.main([
                "--platform",
                "linux",
                "--binary",
                sys.executable,
                "--evidence-out",
                str(evidence_path),
                "--timeout",
                "0.2",
            ])

            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            if evidence["devServerAbsent"]:
                self.assertEqual(1, result)
                self.assertEqual("unavailable", evidence["status"])
                self.assertFalse(evidence["windowObserved"])
                self.assertIn("not an installed LizzieYzy app binary", evidence["pendingReason"])
            else:
                self.assertEqual(1, result)
                self.assertIn(evidence["status"], {"fail", "unavailable"})

    def test_validate_only_rejects_artifact_only_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "bad.json"
            evidence = valid_pass_evidence("linux")
            evidence["artifactOnly"] = True
            evidence["processObserved"] = False
            evidence["windowObserved"] = False
            collector.write_evidence(evidence_path, evidence)

            result = collector.main([
                "--platform",
                "linux",
                "--evidence-out",
                str(evidence_path),
                "--validate-only",
            ])

            self.assertEqual(1, result)

    def test_validate_only_rejects_process_only_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "bad.json"
            evidence = valid_pass_evidence("linux")
            evidence["windowObserved"] = False
            collector.write_evidence(evidence_path, evidence)

            result = collector.main([
                "--platform",
                "linux",
                "--evidence-out",
                str(evidence_path),
                "--validate-only",
            ])

            self.assertEqual(1, result)

    def test_linux_wmctrl_matches_window_by_pid_and_title(self) -> None:
        with patch.object(collector.shutil, "which", side_effect=lambda name: "/usr/bin/wmctrl" if name == "wmctrl" else None):
            with patch.object(collector.subprocess, "run", return_value=Completed(stdout=b"0x04  0 4242 host LizzieYzy Next\n")) as run:
                observation = collector.observe_window("linux", "LizzieYzy", pid=4242)

        self.assertTrue(observation["observed"])
        self.assertEqual("wmctrl", observation["method"])
        self.assertEqual("wmctrl -lp", observation["source"])
        self.assertEqual("0x04", observation["windowId"])
        self.assertEqual("LizzieYzy Next", observation["title"])
        self.assertEqual("pid", observation["matchedBy"])
        self.assertEqual(["wmctrl", "-lp"], run.call_args.args[0])

    def test_linux_xdotool_gets_window_name_for_numeric_id(self) -> None:
        calls: list[list[str]] = []

        def fake_run(command: list[str], **_: object) -> Completed:
            calls.append(command)
            if command[:3] == ["xdotool", "search", "--pid"]:
                return Completed(stdout=b"123456\n")
            if command[:2] == ["xdotool", "getwindowname"]:
                return Completed(stdout=b"LizzieYzy Next\n")
            return Completed(stdout=b"")

        with patch.object(collector.shutil, "which", side_effect=lambda name: "/usr/bin/xdotool" if name == "xdotool" else None):
            with patch.object(collector.subprocess, "run", side_effect=fake_run):
                observation = collector.observe_window("linux", "LizzieYzy", pid=4242)

        self.assertTrue(observation["observed"])
        self.assertEqual("xdotool", observation["method"])
        self.assertEqual("xdotool search --pid", observation["source"])
        self.assertEqual("123456", observation["windowId"])
        self.assertEqual("LizzieYzy Next", observation["title"])
        self.assertIn(["xdotool", "getwindowname", "123456"], calls)

    def test_linux_xdotool_numeric_id_is_not_treated_as_title(self) -> None:
        calls: list[list[str]] = []

        def fake_run(command: list[str], **_: object) -> Completed:
            calls.append(command)
            if command[:3] == ["xdotool", "search", "--pid"]:
                return Completed(stdout=b"123456\n")
            if command[:3] == ["xdotool", "search", "--name"]:
                return Completed(stdout=b"789\n")
            if command[:2] == ["xdotool", "getwindowname"]:
                return Completed(stdout=b"Calculator\n")
            return Completed(stdout=b"")

        with patch.object(collector.shutil, "which", side_effect=lambda name: "/usr/bin/xdotool" if name == "xdotool" else None):
            with patch.object(collector.subprocess, "run", side_effect=fake_run):
                observation = collector.observe_window("linux", "LizzieYzy", pid=4242)

        self.assertFalse(observation["observed"])
        self.assertEqual("", observation["title"])
        self.assertIn(["xdotool", "getwindowname", "123456"], calls)
        self.assertIn(["xdotool", "getwindowname", "789"], calls)

    def test_linux_falls_back_to_xdotool_when_wmctrl_empty_or_unmatched(self) -> None:
        calls: list[list[str]] = []

        def fake_run(command: list[str], **_: object) -> Completed:
            calls.append(command)
            if command == ["wmctrl", "-lp"]:
                return Completed(stdout=b"", returncode=1)
            if command[:3] == ["xdotool", "search", "--pid"]:
                return Completed(stdout=b"123456\n")
            if command[:2] == ["xdotool", "getwindowname"]:
                return Completed(stdout=b"LizzieYzy Next\n")
            return Completed(stdout=b"")

        def fake_which(name: str) -> str | None:
            if name in {"wmctrl", "xdotool"}:
                return f"/usr/bin/{name}"
            return None

        with patch.object(collector.shutil, "which", side_effect=fake_which):
            with patch.object(collector.subprocess, "run", side_effect=fake_run):
                observation = collector.observe_window("linux", "LizzieYzy", pid=4242)

        self.assertTrue(observation["observed"])
        self.assertEqual("xdotool", observation["method"])
        self.assertEqual("xdotool search --pid", observation["source"])
        self.assertEqual("123456", observation["windowId"])
        self.assertEqual("LizzieYzy Next", observation["title"])
        self.assertEqual("wmctrl", observation["fallbackFrom"]["method"])
        self.assertFalse(observation["fallbackFrom"]["observed"])
        self.assertEqual(1, observation["fallbackFrom"]["exitCode"])
        self.assertIn(["wmctrl", "-lp"], calls)
        self.assertIn(["xdotool", "getwindowname", "123456"], calls)


def valid_pass_evidence(platform: str) -> dict[str, object]:
    return {
        "schema": collector.SCHEMA,
        "name": collector.NAME,
        "status": "pass",
        "platform": platform,
        "artifact": {
            "path": "target/release/lizzieyzy",
            "name": "lizzieyzy",
            "sha256": "a" * 64,
            "sizeBytes": 123,
        },
        "launchCommand": ["target/release/lizzieyzy"],
        "processObserved": True,
        "windowObserved": True,
        "windowObservation": {"observed": True, "method": "wmctrl"},
        "devServerAbsent": True,
        "devServerPreflight": {
            "reachableBeforeLaunch": False,
            "runnerStartedDevServer": False,
            "runnerStartedViteDevServer": False,
        },
        "exitOrTerminateSuccess": True,
        "displayMode": "xvfb",
        "staticOnly": False,
        "artifactOnly": False,
        "browserOnly": False,
        "boundaries": {
            **{key: False for key in collector.smoke_user_flows.WINDOWS_LINUX_INSTALLED_APP_SMOKE_OVERCLAIM_FIELDS},
            "viteDevServerStarted": False,
        },
    }


class Completed:
    def __init__(self, stdout: bytes, returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = b""
        self.returncode = returncode


if __name__ == "__main__":
    unittest.main()
