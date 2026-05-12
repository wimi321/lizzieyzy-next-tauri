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
    returncode = None

    def __init__(self, pid: int = 12345) -> None:
        self.pid = pid

    def poll(self) -> int | None:
        return self.returncode


class SmokeTauriRuntimeUiTests(unittest.TestCase):
    def test_validate_report_accepts_required_pass_checks(self) -> None:
        report = valid_report()

        self.assertEqual([], smoke_tauri_runtime_ui.validate_report(report))

    def test_validate_report_rejects_missing_required_check(self) -> None:
        report = valid_report()
        report["checks"] = [check for check in report["checks"] if check["name"] != "board_state_verified"]

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

    def test_validate_report_rejects_invalid_annotation_evidence(self) -> None:
        report = valid_report()
        check = find_check(report, "annotation_edit")
        check["evidence"]["annotations"]["TR"] = ["ab"]
        check["evidence"]["annotations"]["LB"] = ["aa:B", "ee:E"]
        check["evidence"]["annotations"]["AR"] = ["bb:aa"]
        check["evidence"]["annotations"]["LN"] = ["dd:cc"]
        check["evidence"]["added"] = ["TR", "CR", "MA", "SL", "LB", "LN"]
        check["evidence"]["updated"] = ["TR"]
        check["evidence"]["removed"] = ["CR"]

        failures = smoke_tauri_runtime_ui.validate_report(report)

        self.assertIn("annotation_edit annotations.TR must equal ['aa']", failures)
        self.assertIn("annotation_edit annotations.LB must include aa:A and ee:E", failures)
        self.assertIn("annotation_edit annotations.AR must equal ['aa:bb']", failures)
        self.assertIn("annotation_edit annotations.LN must equal ['cc:dd']", failures)
        self.assertIn("annotation_edit added must be exactly AR, CR, LN, MA, SL, TR", failures)
        self.assertIn("annotation_edit updated must be exactly LB", failures)
        self.assertIn("annotation_edit removed must be exactly SQ", failures)

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

    def test_run_writes_sanitized_two_launch_evidence_after_valid_reports(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            evidence_out = Path(tmp) / "evidence.json"
            first_report = valid_report()
            first_report["sgfPath"] = str(Path(tmp) / "repo" / "sample.sgf")
            second_report = valid_report()
            second_report["sgfPath"] = str(Path(tmp) / "repo" / "sample.sgf")
            first_process = FakeProcess(111)
            second_process = FakeProcess(222)

            with (
                patch.object(smoke_tauri_runtime_ui.platform, "system", return_value="Darwin"),
                patch.object(smoke_tauri_runtime_ui, "start_tauri", side_effect=[first_process, second_process]) as start_tauri,
                patch.object(smoke_tauri_runtime_ui, "wait_for_report", side_effect=[first_report, second_report]),
                patch.object(smoke_tauri_runtime_ui, "stop_process") as stop_process,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                exit_code = smoke_tauri_runtime_ui.run(root, timeout_seconds=0.1, evidence_out=evidence_out)

            self.assertEqual(0, exit_code)
            self.assertEqual(2, start_tauri.call_count)
            self.assertEqual("edit-save", start_tauri.call_args_list[0].kwargs["phase"])
            self.assertEqual("reopen-verify", start_tauri.call_args_list[1].kwargs["phase"])
            self.assertEqual(2, stop_process.call_count)
            written = json.loads(evidence_out.read_text(encoding="utf-8"))
            self.assertEqual("<repo>/sample.sgf", written["sgfPath"])
            self.assertEqual("edit-save", written["firstLaunch"]["phase"])
            self.assertEqual("reopen-verify", written["secondLaunch"]["phase"])
            self.assertTrue(written["saveReopenProof"]["distinctProcesses"])
            self.assertIn("checks", written)
            roundtrip = find_check(written, "save_readback_roundtrip")
            self.assertTrue(roundtrip["evidence"]["afterReopen"]["annotationsVerified"])

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

    def test_validate_reopen_report_requires_real_tauri_runtime_evidence(self) -> None:
        report = valid_report()
        find_check(report, "runtime_started")["evidence"] = {"tauriInternals": False}

        failures = smoke_tauri_runtime_ui.validate_reopen_report(report)

        self.assertIn("second launch runtime_started evidence must confirm real Tauri runtime", failures)

    def test_validate_save_reopen_proof_rejects_same_process(self) -> None:
        first_launch = {
            "phase": "edit-save",
            "pid": 123,
            "sgfPath": "/tmp/game.sgf",
            "reportPath": "/tmp/a.json",
            "startedAtUnix": 1.0,
            "stoppedAtUnix": 2.0,
            "stopped": True,
        }
        second_launch = {
            "phase": "reopen-verify",
            "pid": 123,
            "sgfPath": "/tmp/game.sgf",
            "reportPath": "/tmp/b.json",
            "startedAtUnix": 3.0,
            "stoppedAtUnix": 4.0,
            "stopped": True,
        }

        failures = smoke_tauri_runtime_ui.validate_save_reopen_proof(
            first_launch,
            second_launch,
            Path("/tmp/game.sgf"),
        )

        self.assertIn("second launch must use a different Tauri process id", failures)


def valid_report() -> dict[str, object]:
    return {
        "schema": smoke_tauri_runtime_ui.SCHEMA,
        "status": "pass",
        "platform": "macos",
        "checks": [
            {"name": name, "status": "pass", "evidence": valid_evidence_for(name)}
            for name in smoke_tauri_runtime_ui.REQUIRED_CHECKS
        ] + [
            {"name": "reopen_state_verified", "status": "pass", "evidence": valid_evidence_for("reopen_state_verified")},
            {"name": "save_reopen_roundtrip", "status": "pass", "evidence": valid_evidence_for("save_reopen_roundtrip")},
        ],
    }


def valid_evidence_for(name: str) -> dict[str, object]:
    if name == "runtime_started":
        return {"tauriInternals": True, "userAgent": "Tauri", "platform": "MacIntel"}
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
    if name == "annotation_edit":
        return {
            "nodeId": "branch-1",
            "added": ["TR", "CR", "MA", "SL", "AR", "LN"],
            "updated": ["LB"],
            "removed": ["SQ"],
            "annotations": {
                "TR": ["aa"],
                "SQ": [],
                "CR": ["bb"],
                "MA": ["cc"],
                "SL": ["dd"],
                "LB": ["aa:A", "ee:E"],
                "AR": ["aa:bb"],
                "LN": ["cc:dd"],
            },
        }
    if name == "delete_node":
        return {"deletedNodeId": "variation-c", "existsAfterDelete": False}
    if name == "save_readback_roundtrip":
        return {"savedPath": "<tmp>/runtime-smoke.sgf", "readbackMatchesSaved": True}
    if name == "board_state_verified":
        return {"invariant": "replayed position count equals parsed move count plus initial position", "verified": True}
    if name == "reopen_state_verified":
        return {
            "treeOrderVerified": True,
            "commentsVerified": True,
            "propertiesVerified": True,
            "annotationsVerified": True,
            "moveCountVerified": True,
            "boardStateVerified": True,
            "absentAfterReopen": True,
        }
    if name == "save_reopen_roundtrip":
        return {"reopenVerified": True, "verified": True}
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
