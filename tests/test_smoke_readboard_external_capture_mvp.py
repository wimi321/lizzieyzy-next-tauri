from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
USER_FLOWS_SCRIPT = ROOT / "scripts" / "smoke_user_flows.py"
CAPTURE_SCRIPT = ROOT / "scripts" / "smoke_readboard_external_capture_mvp.py"
TAURI_CAPTURE_SCRIPT = ROOT / "scripts" / "smoke_tauri_readboard_external_capture_mvp.py"

USER_FLOWS_SPEC = importlib.util.spec_from_file_location("smoke_user_flows", USER_FLOWS_SCRIPT)
assert USER_FLOWS_SPEC is not None and USER_FLOWS_SPEC.loader is not None
smoke_user_flows = importlib.util.module_from_spec(USER_FLOWS_SPEC)
sys.modules["smoke_user_flows"] = smoke_user_flows
USER_FLOWS_SPEC.loader.exec_module(smoke_user_flows)

CAPTURE_SPEC = importlib.util.spec_from_file_location("smoke_readboard_external_capture_mvp", CAPTURE_SCRIPT)
assert CAPTURE_SPEC is not None and CAPTURE_SPEC.loader is not None
smoke_readboard_external_capture_mvp = importlib.util.module_from_spec(CAPTURE_SPEC)
sys.modules["smoke_readboard_external_capture_mvp"] = smoke_readboard_external_capture_mvp
CAPTURE_SPEC.loader.exec_module(smoke_readboard_external_capture_mvp)

TAURI_CAPTURE_SPEC = importlib.util.spec_from_file_location(
    "smoke_tauri_readboard_external_capture_mvp", TAURI_CAPTURE_SCRIPT
)
assert TAURI_CAPTURE_SPEC is not None and TAURI_CAPTURE_SPEC.loader is not None
smoke_tauri_readboard_external_capture_mvp = importlib.util.module_from_spec(TAURI_CAPTURE_SPEC)
sys.modules["smoke_tauri_readboard_external_capture_mvp"] = smoke_tauri_readboard_external_capture_mvp
TAURI_CAPTURE_SPEC.loader.exec_module(smoke_tauri_readboard_external_capture_mvp)


class SmokeReadboardExternalCaptureMvpTests(unittest.TestCase):
    def test_build_evidence_accepts_runtime_report(self) -> None:
        evidence = smoke_readboard_external_capture_mvp.build_evidence(valid_runtime_report())

        failures = smoke_user_flows.validate_readboard_external_capture_mvp_evidence(evidence, ROOT)
        self.assertEqual([], failures)
        self.assertEqual("readboard_external_capture_mvp", evidence["name"])

    def test_build_evidence_accepts_real_backend_dto_shape(self) -> None:
        evidence = smoke_readboard_external_capture_mvp.build_evidence(valid_real_backend_runtime_report())

        failures = smoke_user_flows.validate_readboard_external_capture_mvp_evidence(evidence, ROOT)

        self.assertEqual([], failures)
        self.assertEqual(19, evidence["decodeSummary"]["boardSize"])
        self.assertEqual(3, evidence["decodeSummary"]["stoneCount"])
        self.assertFalse(evidence["decodeSummary"]["confidenceReported"])
        self.assertTrue(evidence["structuredResult"]["structuredResultVerified"])
        self.assertEqual("selected_screen_region", evidence["captureSource"]["sourceKind"])
        self.assertEqual("macos_interactive_screencapture", evidence["captureSource"]["rawSource"])

    def test_build_evidence_rejects_unavailable_runtime_report(self) -> None:
        report = valid_runtime_report()
        report["rawBackendResult"]["status"] = "permission_denied"

        with self.assertRaisesRegex(ValueError, "status must be captured"):
            smoke_readboard_external_capture_mvp.build_evidence(report)

    def test_validator_rejects_absolute_artifact_path(self) -> None:
        evidence = smoke_readboard_external_capture_mvp.build_evidence(valid_runtime_report())
        artifact = next(check for check in evidence["checks"] if check["name"] == "capture_artifact_recorded")
        artifact["details"]["path"] = "/Users/example/private.png"

        failures = smoke_user_flows.validate_readboard_external_capture_mvp_evidence(evidence, ROOT)

        self.assertIn("capture_artifact_recorded.path must be repo-relative and sanitized", "; ".join(failures))

    def test_validator_rejects_overclaim(self) -> None:
        evidence = smoke_readboard_external_capture_mvp.build_evidence(valid_runtime_report())
        evidence["fullReadboardParity"] = True

        failures = smoke_user_flows.validate_readboard_external_capture_mvp_evidence(evidence, ROOT)

        self.assertIn("fullReadboardParity must be false", failures)

    def test_tauri_runner_builds_from_nested_runtime_report(self) -> None:
        raw_report = valid_tauri_runtime_report()

        evidence = smoke_tauri_readboard_external_capture_mvp.build_evidence_from_tauri_report(raw_report)
        failures = smoke_readboard_external_capture_mvp.validate_evidence(evidence, ROOT)

        self.assertEqual([], failures)
        self.assertEqual("pass", evidence["status"])
        self.assertEqual("local_image", evidence["captureSource"]["sourceKind"])
        self.assertFalse(evidence["operatorInitiated"])
        self.assertFalse(evidence["userSelectionRequired"])
        self.assertFalse(evidence["structuredResult"]["boardReplaced"])

    def test_tauri_runner_rejects_missing_nested_runtime_report(self) -> None:
        raw_report = valid_tauri_runtime_report()
        del raw_report["readboardExternalCaptureMvp"]

        with self.assertRaisesRegex(
            smoke_tauri_readboard_external_capture_mvp.SmokeError,
            "readboardExternalCaptureMvp",
        ):
            smoke_tauri_readboard_external_capture_mvp.build_evidence_from_tauri_report(raw_report)

    def test_tauri_runner_rejects_non_captured_nested_runtime_report(self) -> None:
        raw_report = valid_tauri_runtime_report()
        raw_report["readboardExternalCaptureMvp"]["rawBackendResult"]["status"] = "permission_denied"

        with self.assertRaisesRegex(
            smoke_tauri_readboard_external_capture_mvp.SmokeError,
            "status must be captured",
        ):
            smoke_tauri_readboard_external_capture_mvp.build_evidence_from_tauri_report(raw_report)

    def test_tauri_runner_env_includes_controlled_image_path(self) -> None:
        sgf_path = Path("/tmp/readboard-external-capture.sgf")
        report_path = Path("/tmp/readboard-external-capture-report.json")
        image_path = ROOT / "tests/fixtures/readboard-images/controlled-19-three-stones.ppm"

        env = smoke_tauri_readboard_external_capture_mvp.runtime_env(sgf_path, report_path, image_path)

        self.assertEqual("readboard-external-capture-mvp", env["LIZZIEYZY_RUNTIME_SMOKE_PHASE"])
        self.assertEqual(str(image_path), env["LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH"])
        self.assertEqual(str(image_path), env["VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH"])

    def test_local_image_raw_source_rejects_selected_region_overclaim(self) -> None:
        report = valid_local_image_runtime_report()
        report["captureSource"] = {
            "operatorInitiated": True,
            "userSelectionRequired": True,
            "sourceKind": "selected_screen_region",
            "selection": {"x": 1, "y": 1, "width": 1, "height": 1},
            "targetClientDiscoveryCovered": False,
            "externalClientCaptureCovered": False,
        }

        with self.assertRaisesRegex(ValueError, "captureSource.sourceKind must be local_image"):
            smoke_readboard_external_capture_mvp.build_evidence(report)

    def test_local_image_evidence_rejects_synthesized_user_confirmation(self) -> None:
        evidence = smoke_readboard_external_capture_mvp.build_evidence(valid_local_image_runtime_report())
        preview = next(check for check in evidence["checks"] if check["name"] == "preview_confirmation")
        preview["details"]["userConfirmed"] = True

        failures = smoke_readboard_external_capture_mvp.validate_evidence(evidence, ROOT)

        self.assertIn("preview_confirmation.userConfirmed must not be synthesized for local_image", failures)

    def test_local_image_raw_result_rejects_board_replacement_imported(self) -> None:
        evidence = smoke_readboard_external_capture_mvp.build_evidence(valid_local_image_runtime_report())
        evidence["rawBackendResult"]["boardReplacement"] = "imported"

        dedicated_failures = smoke_readboard_external_capture_mvp.validate_evidence(evidence, ROOT)
        central_failures = smoke_user_flows.validate_readboard_external_capture_mvp_evidence(evidence, ROOT)

        self.assertIn("rawBackendResult.boardReplacement must be absent or none for local_image", dedicated_failures)
        self.assertIn("rawBackendResult.boardReplacement must be absent or none for local_image", central_failures)


def valid_runtime_report() -> dict[str, object]:
    artifact = {
        "path": "docs/qa/fixtures/readboard-controlled-board.png",
        "sizeBytes": 522,
        "sha256": "70cfecf5b5d5235e66a051c5208c2974fde34f0a28aaef5be33fcd8bc0f63d96",
        "sanitized": True,
    }
    decode = {
        "decodeAttempted": True,
        "decodeSucceeded": True,
        "boardSize": 19,
        "stoneCount": 3,
        "confidence": 0.99,
        "structuredResultProduced": True,
    }
    raw_position = {
        "board_size": 19,
        "move_number": 0,
        "to_play": "black",
        "stones": [
            {"color": "black", "point": "dd"},
            {"color": "white", "point": "pq"},
            {"color": "black", "point": "dp"},
        ],
    }
    return {
        "platform": "macos",
        "captureSource": {
            "operatorInitiated": True,
            "userSelectionRequired": True,
            "sourceKind": "external_screen_region",
            "selection": {"x": 12, "y": 18, "width": 640, "height": 640},
            "targetClientDiscoveryCovered": False,
            "externalClientCaptureCovered": False,
        },
        "captureArtifact": artifact,
        "decodeSummary": decode,
        "previewConfirmation": {
            "previewOnlyBeforeConfirmation": True,
            "boardReplacedBeforeConfirmation": False,
            "userConfirmed": True,
            "boardReplacedOnlyAfterConfirmation": True,
        },
        "rawBackendResult": {
            "status": "captured",
            "snapshotId": "runtime-capture-001",
            "position": raw_position,
            "decode": decode,
        },
    }


def valid_real_backend_runtime_report() -> dict[str, object]:
    return {
        "platform": "macos",
        "captureArtifact": {
            "path": "docs/qa/fixtures/readboard-controlled-board.png",
            "sizeBytes": 522,
            "sha256": "70cfecf5b5d5235e66a051c5208c2974fde34f0a28aaef5be33fcd8bc0f63d96",
            "sanitized": True,
        },
        "previewConfirmation": {
            "previewOnlyBeforeConfirmation": True,
            "boardReplacedBeforeConfirmation": False,
            "userConfirmed": True,
            "boardReplacedOnlyAfterConfirmation": True,
        },
        "rawBackendResult": {
            "status": "captured",
            "position": {
                "board_size": 19,
                "move_number": 0,
                "to_play": "black",
                "stones": [
                    {"color": "black", "point": "dd"},
                    {"color": "white", "point": "pq"},
                    {"color": "black", "point": "dp"},
                ],
            },
            "decode": {
                "attempted": True,
                "status": "success",
                "board_size": 19,
                "stone_count": 3,
                "blackStones": [{"point": "dd"}, {"point": "dp"}],
                "whiteStones": [{"point": "pq"}],
            },
            "snapshot_id": "real-backend-snapshot-001",
            "snapshot_hash": "abc123",
            "source": "macos_interactive_screencapture",
            "source_metadata": {
                "selection": {"x": 12, "y": 18, "width": 640, "height": 640}
            },
            "boardReplacement": "none",
            "warnings": [],
        },
    }


def valid_tauri_runtime_report() -> dict[str, object]:
    return {
        "schema": "lizzieyzy.tauri-runtime-ui-smoke.v1",
        "phase": "readboard-external-capture-mvp",
        "status": "pass",
        "platform": "macos",
        "readboardExternalCaptureMvp": valid_local_image_runtime_report(),
    }


def valid_local_image_runtime_report() -> dict[str, object]:
    return {
        "platform": "macos",
        "captureArtifact": {
            "path": "tests/fixtures/readboard-images/controlled-19-three-stones.ppm",
            "sizeBytes": 480015,
            "sha256": "1c910bea940043ee171b36dbc9ad3d6c9365d7b317f437b563be84e8583e3f0d",
            "sanitized": True,
        },
        "rawBackendResult": {
            "status": "captured",
            "schema": "lizzieyzy.readboard-external-capture.v1",
            "captureSource": "local_image",
            "source": "local_image",
            "operatorInitiated": False,
            "userSelectionRequired": False,
            "sanitizedPath": "local-image:controlled-19-three-stones.ppm",
            "snapshotId": "external-capture-preview",
            "snapshotHash": "41bc57f408b78d7c5f21f954e43840a2ee256007c70b30105c84b9c7447eb922",
            "boardReplacement": "none",
            "position": {
                "board_size": 19,
                "move_number": 3,
                "to_play": "white",
                "stones": [
                    {"color": "black", "x": 3, "y": 3},
                    {"color": "black", "x": 10, "y": 4},
                    {"color": "white", "x": 15, "y": 15},
                ],
            },
            "decode": {
                "attempted": True,
                "status": "success",
                "boardSize": 19,
                "stoneCount": 3,
                "blackStones": 2,
                "whiteStones": 1,
            },
            "warnings": [
                "UnsupportedProvider: scoped controlled image import decoded a synthetic/controlled board image",
                "UnsupportedProvider: this is not full OCR and does not support arbitrary client screenshots",
            ],
        },
    }


if __name__ == "__main__":
    unittest.main()
