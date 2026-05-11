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


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_tauri_readboard_live.py"
SPEC = importlib.util.spec_from_file_location("smoke_tauri_readboard_live", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke_tauri_readboard_live = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_tauri_readboard_live"] = smoke_tauri_readboard_live
SPEC.loader.exec_module(smoke_tauri_readboard_live)


class FakeProcess:
    returncode = None

    def __init__(self, pid: int = 12345) -> None:
        self.pid = pid

    def poll(self) -> int | None:
        return self.returncode


class SmokeTauriReadboardLiveTests(unittest.TestCase):
    def test_validate_report_accepts_required_pass_checks(self) -> None:
        self.assertEqual([], smoke_tauri_readboard_live.validate_report(valid_report()))

    def test_validate_report_rejects_non_tauri_runtime(self) -> None:
        report = valid_report()
        find_check(report, "runtime_started")["details"]["tauriInternals"] = False

        failures = smoke_tauri_readboard_live.validate_report(report)

        self.assertIn("runtime_started must confirm real Tauri runtime", failures)

    def test_validate_report_rejects_missing_readboard_probe(self) -> None:
        report = valid_report()
        report["checks"] = [check for check in report["checks"] if check["name"] != "sidecar_probe_ready"]

        failures = smoke_tauri_readboard_live.validate_report(report)

        self.assertIn("missing required checks: sidecar_probe_ready", failures)

    def test_validate_report_rejects_unsupported_ocr_success(self) -> None:
        report = valid_report()
        find_check(report, "unsupported_ocr_path")["details"] = {
            "observed": True,
            "unsupported": False,
            "messageIncludesBoundary": True,
            "message": "sync succeeded",
        }

        failures = smoke_tauri_readboard_live.validate_report(report)

        self.assertIn("unsupported_ocr_path must confirm unsupported true", failures)

    def test_validate_report_rejects_external_client_claim(self) -> None:
        report = valid_report()
        find_check(report, "external_client_not_covered")["details"]["externalClientCaptureCovered"] = True

        failures = smoke_tauri_readboard_live.validate_report(report)

        self.assertIn("external_client_not_covered must exclude OCR and external client capture", failures)

    def test_build_evidence_requires_readboard_live_raw_report(self) -> None:
        raw = valid_raw_tauri_report()
        raw["phase"] = "full"

        with self.assertRaises(smoke_tauri_readboard_live.SmokeError) as caught:
            smoke_tauri_readboard_live.build_evidence(raw, endpoint=None, timeout_seconds=1.0)

        self.assertIn("phase must be readboard-live", str(caught.exception))

    def test_build_evidence_preserves_sync_semantics(self) -> None:
        evidence = smoke_tauri_readboard_live.build_evidence(
            valid_raw_tauri_report(),
            endpoint="127.0.0.1:39081",
            timeout_seconds=1.5,
        )

        self.assertEqual("lizzieyzy.readboard-tauri-runtime-smoke.v1", evidence["schema"])
        self.assertEqual("readboard-live", evidence["phase"])
        self.assertEqual("127.0.0.1:39081", evidence["endpoint"])
        self.assertEqual([], smoke_tauri_readboard_live.validate_report(evidence))
        self.assertEqual(1, find_check(evidence, "protocol_line_sync")["details"]["moveNumber"])
        self.assertEqual(True, find_check(evidence, "target_state_change_sync")["details"]["changed"])
        self.assertEqual(2, find_check(evidence, "target_state_change_sync")["details"]["afterStoneCount"])

    def test_run_writes_sanitized_evidence_after_valid_report(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            readboard_home = root / "readboard"
            readboard_home.mkdir()
            evidence_out = Path(tmp) / "evidence.json"
            process = FakeProcess()

            with (
                patch.object(smoke_tauri_readboard_live.platform, "system", return_value="Darwin"),
                patch.object(smoke_tauri_readboard_live, "start_tauri", return_value=process),
                patch.object(smoke_tauri_readboard_live, "wait_for_report", return_value=valid_raw_tauri_report(str(root))),
                patch.object(smoke_tauri_readboard_live, "stop_process") as stop_process,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                exit_code = smoke_tauri_readboard_live.run(
                    root,
                    timeout_seconds=0.1,
                    evidence_out=evidence_out,
                    readboard_home=readboard_home,
                    endpoint=None,
                )

            self.assertEqual(0, exit_code)
            stop_process.assert_called_once_with(process)
            written_text = evidence_out.read_text(encoding="utf-8")
            self.assertNotIn(str(root), written_text)
            written = json.loads(written_text)
            self.assertEqual("pass", written["status"])
            self.assertEqual([], smoke_tauri_readboard_live.validate_report(written))

    def test_cleanup_removes_new_generated_readboard_artifact(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "readboard_boofcv_config.txt"
            state = smoke_tauri_readboard_live.generated_artifact_state(root)
            artifact.write_text("generated", encoding="utf-8")

            smoke_tauri_readboard_live.cleanup_new_generated_artifacts(state)

            self.assertFalse(artifact.exists())


def valid_report() -> dict[str, object]:
    return {
        "schema": smoke_tauri_readboard_live.SCHEMA,
        "name": "readboard_tauri_runtime_smoke",
        "status": "pass",
        "platform": "macos",
        "phase": "readboard-live",
        "checks": valid_checks(),
    }


def valid_raw_tauri_report(root: str = "/repo") -> dict[str, object]:
    return {
        "schema": smoke_tauri_readboard_live.TAURI_RUNTIME_SCHEMA,
        "name": "ui_tauri_runtime_smoke",
        "status": "pass",
        "platform": "macos",
        "phase": "readboard-live",
        "startedAt": "2026-05-12T00:00:00Z",
        "finishedAt": "2026-05-12T00:00:01Z",
        "checks": valid_checks(root),
    }


def valid_checks(root: str = "/repo") -> list[dict[str, object]]:
    return [
        {
            "name": "runtime_started",
            "status": "pass",
            "details": {"tauriInternals": True, "platform": "MacIntel"},
        },
        {
            "name": "sidecar_probe_ready",
            "status": "pass",
            "details": {"available": True, "endpoint": None, "version": None, "warnings": [f"{root}/readboard jar discovered"]},
        },
        {
            "name": "sidecar_probe_unavailable",
            "status": "pass",
            "details": {
                "available": False,
                "endpoint": "readboard-unavailable-endpoint",
                "warnings": ["invalid endpoint"],
                "structuredUnavailable": True,
            },
        },
        {
            "name": "protocol_line_sync",
            "status": "pass",
            "details": {
                "snapshotId": "runtime-a",
                "boardSize": 2,
                "moveNumber": 1,
                "stoneCount": 1,
                "toPlay": "white",
                "warnings": [],
            },
        },
        {
            "name": "target_state_change_sync",
            "status": "pass",
            "details": {
                "changed": True,
                "beforeSnapshotId": "runtime-a",
                "afterSnapshotId": "runtime-b",
                "beforeStoneCount": 1,
                "afterStoneCount": 2,
                "beforeMoveNumber": 1,
                "afterMoveNumber": 2,
                "boardSizeStable": True,
                "toPlay": "white",
                "warnings": [],
            },
        },
        {
            "name": "unsupported_ocr_path",
            "status": "pass",
            "details": {
                "observed": True,
                "unsupported": True,
                "boundary": "image OCR runtime unavailable",
                "messageIncludesBoundary": True,
                "message": "image OCR runtime unavailable for readboard sidecar sync",
            },
        },
        {
            "name": "external_client_not_covered",
            "status": "pass",
            "details": {
                "covered": False,
                "scope": "Tauri runtime command boundary plus protocol-line DTO sync only",
                "ocrCovered": False,
                "externalClientCaptureCovered": False,
            },
        },
    ]


def find_check(report: dict[str, object], name: str) -> dict[str, object]:
    checks = report["checks"]
    assert isinstance(checks, list)
    for check in checks:
        assert isinstance(check, dict)
        if check.get("name") == name:
            return check
    raise AssertionError(f"missing check {name}")


if __name__ == "__main__":
    unittest.main()
