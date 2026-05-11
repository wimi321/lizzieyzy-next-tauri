from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_tauri_katago_live.py"
SPEC = importlib.util.spec_from_file_location("smoke_tauri_katago_live", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke_tauri_katago_live = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_tauri_katago_live"] = smoke_tauri_katago_live
SPEC.loader.exec_module(smoke_tauri_katago_live)


class FakeProcess:
    returncode = None

    def __init__(self, pid: int = 12345) -> None:
        self.pid = pid

    def poll(self) -> int | None:
        return self.returncode


class SmokeTauriKatagoLiveTests(unittest.TestCase):
    def test_validate_report_accepts_required_pass_checks(self) -> None:
        self.assertEqual([], smoke_tauri_katago_live.validate_report(valid_report()))

    def test_validate_report_rejects_missing_cancel(self) -> None:
        report = valid_report()
        report["checks"] = [check for check in report["checks"] if check["name"] != "katago_start_cancel"]

        failures = smoke_tauri_katago_live.validate_report(report)

        self.assertIn("missing required checks: katago_start_cancel", failures)

    def test_validate_report_rejects_non_tauri_runtime(self) -> None:
        report = valid_report()
        find_check(report, "runtime_started")["details"]["tauriInternals"] = False

        failures = smoke_tauri_katago_live.validate_report(report)

        self.assertIn("runtime_started must confirm real Tauri runtime", failures)

    def test_run_writes_sanitized_evidence_after_valid_report(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            engine = root / "katago"
            model = root / "model.bin.gz"
            config = root / "analysis.cfg"
            for path in (engine, model, config):
                path.write_text("x", encoding="utf-8")
            evidence_out = Path(tmp) / "evidence.json"
            process = FakeProcess()

            with (
                patch.object(smoke_tauri_katago_live.platform, "system", return_value="Darwin"),
                patch.object(smoke_tauri_katago_live, "start_tauri", return_value=process),
                patch.object(smoke_tauri_katago_live, "wait_for_report", return_value=valid_raw_tauri_report()),
                patch.object(smoke_tauri_katago_live, "stop_process") as stop_process,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                exit_code = smoke_tauri_katago_live.run(
                    root,
                    engine,
                    model,
                    config,
                    timeout_seconds=0.1,
                    evidence_out=evidence_out,
                )

            self.assertEqual(0, exit_code)
            stop_process.assert_called_once_with(process)
            written = json.loads(evidence_out.read_text(encoding="utf-8"))
            self.assertEqual("pass", written["status"])
            self.assertIn("checks", written)


def valid_report() -> dict[str, object]:
    return {
        "schema": smoke_tauri_katago_live.SCHEMA,
        "name": "katago_tauri_runtime_smoke",
        "status": "pass",
        "platform": "macos",
        "checks": [
            {
                "name": "runtime_started",
                "status": "pass",
                "details": {"tauriInternals": True, "platform": "MacIntel"},
            },
            {
                "name": "katago_assets",
                "status": "pass",
                "details": {"engineExists": True, "modelBytes": 12, "configBytes": 10},
            },
            {
                "name": "katago_failure_mode_missing_assets",
                "status": "pass",
                "details": {"observed": True, "missingRequired": ["model", "config"]},
            },
            {
                "name": "katago_analyze_once",
                "status": "pass",
                "details": {"frameCount": 1, "candidateCount": 2, "hasRootInfo": True},
            },
            {
                "name": "katago_analyze_game",
                "status": "pass",
                "details": {"frameCount": 2, "candidateCount": 2, "hasRootInfo": True},
            },
            {
                "name": "katago_start_cancel",
                "status": "pass",
                "details": {"jobId": "job-1", "cancelRequested": True, "cancelConfirmed": True},
            },
        ],
    }


def find_check(report: dict[str, object], name: str) -> dict[str, object]:
    checks = report["checks"]
    assert isinstance(checks, list)
    for check in checks:
        assert isinstance(check, dict)
        if check.get("name") == name:
            return check
    raise AssertionError(f"missing check {name}")


def valid_raw_tauri_report() -> dict[str, object]:
    return {
        "schema": smoke_tauri_katago_live.TAURI_RUNTIME_SCHEMA,
        "name": "ui_tauri_runtime_smoke",
        "status": "pass",
        "platform": "macos",
        "phase": "katago-live",
        "startedAt": "2026-05-12T00:00:00Z",
        "finishedAt": "2026-05-12T00:00:01Z",
        "checks": [
            {
                "name": "runtime_started",
                "status": "pass",
                "details": {"tauriInternals": True, "platform": "MacIntel"},
            },
            {
                "name": "katago_assets",
                "status": "pass",
                "details": {"total": 3, "required": 3, "missingRequired": []},
            },
            {
                "name": "katago_failure_mode_missing_assets",
                "status": "pass",
                "details": {"observed": True, "missingRequired": ["model", "config"]},
            },
            {
                "name": "katago_analyze_once",
                "status": "pass",
                "details": {"visits": 8, "candidates": 2, "hasOwnership": True, "hasPolicy": True, "turn": 1},
            },
            {
                "name": "katago_analyze_game",
                "status": "pass",
                "details": {
                    "frames": 2,
                    "turns": [0, 1],
                    "firstFrame": {"visits": 8, "candidates": 2},
                    "lastFrame": {"visits": 8, "candidates": 2},
                },
            },
            {
                "name": "katago_start_cancel",
                "status": "pass",
                "details": {
                    "jobId": "job-1",
                    "cancelRequested": True,
                    "cancelConfirmed": True,
                    "event": {"kind": "cancelled", "jobId": "job-1"},
                },
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()
