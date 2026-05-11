from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_tauri_runtime_ui.py"
SPEC = importlib.util.spec_from_file_location("smoke_tauri_runtime_ui", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke_tauri_runtime_ui = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_tauri_runtime_ui"] = smoke_tauri_runtime_ui
SPEC.loader.exec_module(smoke_tauri_runtime_ui)


class FakeProcess:
    pid = 12345
    returncode = None

    def poll(self) -> int | None:
        return self.returncode


class SmokeTauriRuntimeUiTests(unittest.TestCase):
    def test_validate_report_accepts_required_pass_checks(self) -> None:
        report = valid_report()

        self.assertEqual([], smoke_tauri_runtime_ui.validate_report(report))

    def test_validate_report_rejects_missing_required_check(self) -> None:
        report = valid_report()
        report["checks"] = report["checks"][:-1]

        failures = smoke_tauri_runtime_ui.validate_report(report)

        self.assertIn("missing required checks: board_state_verified", failures)

    def test_validate_report_rejects_reorder_target_index_other_than_zero(self) -> None:
        report = valid_report()
        check = find_check(report, "variation_reorder")
        check["evidence"]["targetIndex"] = 1

        failures = smoke_tauri_runtime_ui.validate_report(report)

        self.assertIn("variation_reorder target index must be 0", failures)

    def test_validate_report_rejects_edit_move_without_confirmed_target_vertex(self) -> None:
        report = valid_report()
        check = find_check(report, "edit_move")
        check["evidence"]["confirmedVertex"] = {"point": {"x": 4, "y": 4}}

        failures = smoke_tauri_runtime_ui.validate_report(report)

        self.assertIn("edit_move confirmed vertex must match target vertex", failures)

    def test_validate_report_rejects_delete_node_without_absence_confirmation(self) -> None:
        report = valid_report()
        check = find_check(report, "delete_node")
        check["evidence"]["existsAfterDelete"] = True

        failures = smoke_tauri_runtime_ui.validate_report(report)

        self.assertIn("delete_node evidence must confirm deleted node is absent after delete", failures)

    def test_validate_report_rejects_roundtrip_without_readback_verification(self) -> None:
        report = valid_report()
        check = find_check(report, "save_readback_roundtrip")
        del check["evidence"]["readbackMatchesSaved"]

        failures = smoke_tauri_runtime_ui.validate_report(report)

        self.assertIn("save_readback_roundtrip evidence must include readback verification", failures)

    def test_validate_report_rejects_board_state_without_invariant(self) -> None:
        report = valid_report()
        check = find_check(report, "board_state_verified")
        check["evidence"]["invariant"] = ""

        failures = smoke_tauri_runtime_ui.validate_report(report)

        self.assertIn("board_state_verified evidence must include an explicit invariant", failures)

    def test_sanitize_evidence_replaces_repo_and_temp_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            temp_dir = Path(tmp) / "runtime"
            evidence = {
                "path": str(root / "apps/desktop"),
                "nested": [{"log": str(temp_dir / "tauri-dev.log")}],
            }

            sanitized = smoke_tauri_runtime_ui.sanitize_evidence(evidence, root=root, temp_dir=temp_dir)

            self.assertEqual("<repo>/apps/desktop", sanitized["path"])
            self.assertEqual("<tmp>/tauri-dev.log", sanitized["nested"][0]["log"])

    def test_run_writes_sanitized_evidence_after_valid_report(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            evidence_out = Path(tmp) / "evidence.json"
            report = valid_report()
            report["sgfPath"] = str(Path(tmp) / "repo" / "sample.sgf")
            process = FakeProcess()

            with (
                patch.object(smoke_tauri_runtime_ui.platform, "system", return_value="Darwin"),
                patch.object(smoke_tauri_runtime_ui, "start_tauri", return_value=process),
                patch.object(smoke_tauri_runtime_ui, "wait_for_report", return_value=report),
                patch.object(smoke_tauri_runtime_ui, "stop_process") as stop_process,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                exit_code = smoke_tauri_runtime_ui.run(root, timeout_seconds=0.1, evidence_out=evidence_out)

            self.assertEqual(0, exit_code)
            stop_process.assert_called_once_with(process)
            written = json.loads(evidence_out.read_text(encoding="utf-8"))
            self.assertEqual("<repo>/sample.sgf", written["sgfPath"])

    def test_run_returns_failure_for_invalid_report(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            process = FakeProcess()

            with (
                patch.object(smoke_tauri_runtime_ui.platform, "system", return_value="Darwin"),
                patch.object(smoke_tauri_runtime_ui, "start_tauri", return_value=process),
                patch.object(smoke_tauri_runtime_ui, "wait_for_report", return_value={"status": "fail"}),
                patch.object(smoke_tauri_runtime_ui, "stop_process") as stop_process,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                exit_code = smoke_tauri_runtime_ui.run(root, timeout_seconds=0.1, evidence_out=None)

            self.assertEqual(1, exit_code)
            stop_process.assert_called_once_with(process)


def valid_report() -> dict[str, object]:
    return {
        "schema": smoke_tauri_runtime_ui.SCHEMA,
        "status": "pass",
        "platform": "macos",
        "checks": [
            {"name": name, "status": "pass", "evidence": valid_evidence_for(name)}
            for name in smoke_tauri_runtime_ui.REQUIRED_CHECKS
        ],
    }


def valid_evidence_for(name: str) -> dict[str, object]:
    if name == "variation_reorder":
        return {
            "nodeId": "variation-b",
            "movedNodeId": "variation-b",
            "targetIndex": 0,
            "indexAfterMove": 0,
            "variationIndexAfterMove": 0,
            "parentNodeId": "root",
        }
    if name == "edit_move":
        vertex = {"point": {"x": 3, "y": 3}}
        return {"nodeId": "move-1", "targetVertex": vertex, "confirmedVertex": vertex}
    if name == "delete_node":
        return {"deletedNodeId": "variation-c", "existsAfterDelete": False}
    if name == "save_readback_roundtrip":
        return {"savedPath": "<tmp>/runtime-smoke.sgf", "readbackMatchesSaved": True}
    if name == "board_state_verified":
        return {"invariant": "replayed position count equals parsed move count plus initial position", "verified": True}
    return {"observed": True}


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
