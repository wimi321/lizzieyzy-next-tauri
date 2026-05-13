from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke_readboard_selected_window_capture.py"
SPEC = importlib.util.spec_from_file_location("smoke_readboard_selected_window_capture", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke_readboard_selected_window_capture = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_readboard_selected_window_capture"] = smoke_readboard_selected_window_capture
SPEC.loader.exec_module(smoke_readboard_selected_window_capture)


class ReadboardSelectedWindowCaptureTests(unittest.TestCase):
    def test_valid_runtime_evidence_passes_validator(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = valid_evidence(root)

            failures = smoke_readboard_selected_window_capture.validate_selected_window_capture_evidence(evidence, root)

            self.assertEqual([], failures)

    def test_static_only_rejected(self) -> None:
        self.assert_invalid(lambda evidence: evidence.__setitem__("sourceStaticOnly", True), "sourceStaticOnly must be false")

    def test_capture_must_be_tied_to_selected_window(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            artifact = evidence["captureArtifact"]
            assert isinstance(artifact, dict)
            artifact["windowId"] = "different-window"

        self.assert_invalid(mutate, "captureArtifact.windowId must match selectedWindow.windowId")

    def test_missing_artifact_hash_rejected(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            artifact = evidence["captureArtifact"]
            assert isinstance(artifact, dict)
            artifact.pop("sha256", None)

        self.assert_invalid(mutate, "captureArtifact.sha256 must be a 64-character hex sha256")

    def test_failed_decode_import_rejected(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            failed = evidence["failedDecodeNoReplacement"]
            assert isinstance(failed, dict)
            failed["imported"] = True

        self.assert_invalid(mutate, "failedDecodeNoReplacement.imported must be false")

    def test_overclaims_rejected(self) -> None:
        for field in smoke_readboard_selected_window_capture.REQUIRED_FALSE_FIELDS:
            with self.subTest(field=field):
                self.assert_invalid(lambda evidence, field=field: evidence.__setitem__(field, True), f"{field} must be false")

    def test_automatic_board_replacement_overclaim_rejected(self) -> None:
        self.assert_invalid(
            lambda evidence: evidence.__setitem__("automaticBoardReplacement", True),
            "automaticBoardReplacement must be false",
        )

    def test_release_parity_overclaim_rejected(self) -> None:
        self.assert_invalid(
            lambda evidence: evidence.__setitem__("releaseParity", True),
            "releaseParity must be false",
        )

    def test_release_alias_overclaims_rejected(self) -> None:
        for field in ("fullReleaseParity", "releaseReady", "officialRelease"):
            with self.subTest(field=field):
                self.assert_invalid(
                    lambda evidence, field=field: evidence.__setitem__(field, True),
                    f"{field} must be false",
                )

    def test_wrong_source_runtime_report_rejected(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            source = evidence["sourceRuntimeReport"]
            assert isinstance(source, dict)
            source["phase"] = "readboard-target-window-discovery"
            source["reportKey"] = "readboardTargetWindowDiscovery"

        self.assert_invalid(mutate, "sourceRuntimeReport.phase must be readboard-selected-window-capture")

    def test_validate_missing_default_evidence_fails_without_fabricating_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"

            result = smoke_readboard_selected_window_capture.main(["--evidence-out", str(missing)])

            self.assertEqual(1, result)

    def assert_invalid(self, mutate, expected: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = valid_evidence(root)
            mutate(evidence)

            failures = smoke_readboard_selected_window_capture.validate_selected_window_capture_evidence(evidence, root)

            self.assertIn(expected, failures)


def write_artifact(root: Path, rel: str, content: bytes) -> dict[str, object]:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"path": rel, "sha256": hashlib.sha256(content).hexdigest(), "sizeBytes": len(content), "sanitized": True}


def valid_evidence(root: Path) -> dict[str, object]:
    capture = write_artifact(root, "artifacts/selected-window.ppm", b"P6\n1 1\n255\nabc")
    failed = write_artifact(root, "artifacts/selected-window-non-board.ppm", b"P6\n1 1\n255\nxyz")
    window = {
        "windowId": "window-001",
        "title": "Controlled Selected Window",
        "appName": "LizzieYzy Test Harness",
        "processName": "readboard-target-fixture",
        "windowIdSanitized": True,
        "bounds": {"x": 10, "y": 20, "width": 400, "height": 400},
    }
    snapshot_hash = "1c910bea940043ee171b36dbc9ad3d6c9365d7b317f437b563be84e8583e3f0d"
    raw = {
        "status": "captured",
        "source": "selected_window",
        "windowId": "window-001",
        "captureTiedToSelectedWindow": True,
        "boardReplacement": "none",
        "snapshotHash": snapshot_hash,
        "position": {"boardSize": 19, "stones": []},
    }
    artifact = {**capture, "windowId": "window-001", "captureTiedToSelectedWindow": True}
    failed_decode = {
        **failed,
        "decodeAttempted": True,
        "decodeSucceeded": False,
        "imported": False,
        "boardReplaced": False,
    }
    return {
        "schema": smoke_readboard_selected_window_capture.SCHEMA,
        "name": "readboard_selected_window_capture",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "runtime_backend_selected_window_capture",
        "sourceStaticOnly": False,
        "runtimeObserved": True,
        "backendCommandInvoked": True,
        "backendCommand": smoke_readboard_selected_window_capture.BACKEND_COMMAND,
        "runtimeReportPhase": smoke_readboard_selected_window_capture.RUNTIME_PHASE,
        "runtimeReportKey": smoke_readboard_selected_window_capture.RUNTIME_KEY,
        "selectedWindowCaptureVerified": True,
        "selectedWindow": window,
        "rawBackendResult": raw,
        "captureArtifact": artifact,
        "decodeSnapshot": {
            "snapshotId": "selected-window-snapshot-001",
            "snapshotHash": snapshot_hash,
            "decodeSucceeded": True,
            "boardSize": 19,
            "stoneCount": 0,
        },
        "previewConfirmation": {
            "previewOnlyBeforeConfirmation": True,
            "boardReplacedBeforeConfirmation": False,
            "userConfirmed": True,
            "boardReplacedOnlyAfterConfirmation": True,
        },
        "failedDecodeNoReplacement": failed_decode,
        "sourceRuntimeReport": {
            "schema": "lizzieyzy.tauri-runtime-ui-smoke.v1",
            "phase": smoke_readboard_selected_window_capture.RUNTIME_PHASE,
            "reportKey": smoke_readboard_selected_window_capture.RUNTIME_KEY,
            "runtimeObserved": True,
            "backendCommandInvoked": True,
            "backendCommand": smoke_readboard_selected_window_capture.BACKEND_COMMAND,
        },
        "automaticBoardReplacement": False,
        "releaseParity": False,
        "fullReleaseParity": False,
        "releaseReady": False,
        "officialRelease": False,
        "realClientParity": False,
        "fullOcrParity": False,
        "fullReadboardParity": False,
        "targetClientDiscoveryParity": False,
        "foxYikeParity": False,
        "windowsLinuxCaptureCovered": False,
    }


if __name__ == "__main__":
    unittest.main()
