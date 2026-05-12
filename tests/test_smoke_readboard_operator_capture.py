from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SMOKE_USER_FLOWS_SCRIPT = ROOT / "scripts" / "smoke_user_flows.py"
OPERATOR_SCRIPT = ROOT / "scripts" / "smoke_tauri_readboard_operator_capture.py"

USER_SPEC = importlib.util.spec_from_file_location("smoke_user_flows", SMOKE_USER_FLOWS_SCRIPT)
assert USER_SPEC is not None and USER_SPEC.loader is not None
smoke_user_flows = importlib.util.module_from_spec(USER_SPEC)
sys.modules["smoke_user_flows"] = smoke_user_flows
USER_SPEC.loader.exec_module(smoke_user_flows)

OPERATOR_SPEC = importlib.util.spec_from_file_location("smoke_tauri_readboard_operator_capture", OPERATOR_SCRIPT)
assert OPERATOR_SPEC is not None and OPERATOR_SPEC.loader is not None
smoke_tauri_readboard_operator_capture = importlib.util.module_from_spec(OPERATOR_SPEC)
sys.modules["smoke_tauri_readboard_operator_capture"] = smoke_tauri_readboard_operator_capture
OPERATOR_SPEC.loader.exec_module(smoke_tauri_readboard_operator_capture)


class SmokeReadboardOperatorCaptureTests(unittest.TestCase):
    def test_build_evidence_from_runtime_report_passes_validator(self) -> None:
        evidence = smoke_tauri_readboard_operator_capture.build_evidence(valid_runtime_report())

        failures = smoke_user_flows.validate_readboard_operator_capture_evidence(evidence, ROOT)

        self.assertEqual([], failures)
        self.assertTrue(evidence["operatorInitiated"])
        self.assertTrue(evidence["userConfirmed"])
        self.assertTrue(evidence["boardReplacedOnlyAfterConfirmation"])
        self.assertEqual("none", evidence["structuredImport"]["rawBackendBoardReplacement"])
        self.assertTrue(evidence["structuredImport"]["uiBoardReplacedAfterConfirmation"])

    def test_build_rejects_operator_selected_file_decode_only_without_confirmation(self) -> None:
        with self.assertRaises(ValueError) as raised:
            smoke_tauri_readboard_operator_capture.build_evidence(operator_selected_file_runtime_report())

        message = str(raised.exception)
        self.assertIn("preview_confirmation.userConfirmed must be true", message)
        self.assertIn("preview_confirmation.boardReplacedOnlyAfterConfirmation must be true", message)
        self.assertIn("structuredImport.boardReplaced must be true", message)
        self.assertIn("structuredImport.replacementConfirmed must be true", message)

    def test_runtime_env_injects_capture_image_path(self) -> None:
        env = smoke_tauri_readboard_operator_capture.runtime_env(
            Path("/tmp/smoke.sgf"),
            Path("/tmp/report.json"),
            ROOT / "tests/fixtures/readboard-images/controlled-19-three-stones.ppm",
        )

        self.assertEqual(
            str(ROOT / "tests/fixtures/readboard-images/controlled-19-three-stones.ppm"),
            env["VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH"],
        )
        self.assertEqual("readboard-operator-capture", env["VITE_LIZZIEYZY_RUNTIME_SMOKE_PHASE"])

    def test_builder_requires_independent_operator_report_key(self) -> None:
        report = valid_runtime_report()
        report["readboardExternalCaptureMvp"] = report.pop("readboardOperatorCapture")

        with self.assertRaises(smoke_tauri_readboard_operator_capture.SmokeError) as raised:
            smoke_tauri_readboard_operator_capture.build_evidence(report)

        self.assertIn("readboardOperatorCapture", str(raised.exception))

    def test_build_rejects_cancelled_or_unavailable_as_pass(self) -> None:
        report = valid_runtime_report()
        report["readboardOperatorCapture"]["rawBackendResult"]["status"] = "cancelled"

        with self.assertRaises(ValueError) as raised:
            smoke_tauri_readboard_operator_capture.build_evidence(report)

        self.assertIn("rawBackendResult.status=captured", str(raised.exception))

    def test_validator_rejects_missing_artifact_hash_size_path(self) -> None:
        evidence = smoke_tauri_readboard_operator_capture.build_evidence(valid_runtime_report())
        evidence["captureArtifact"].pop("sha256")

        failures = smoke_user_flows.validate_readboard_operator_capture_evidence(evidence, ROOT)

        self.assertIn("captureArtifact.sha256 must be a 64-character hex sha256", "; ".join(failures))

    def test_validator_rejects_replacement_before_confirmation(self) -> None:
        evidence = smoke_tauri_readboard_operator_capture.build_evidence(valid_runtime_report())
        evidence["previewConfirmation"]["boardReplacedBeforeConfirmation"] = True

        failures = smoke_user_flows.validate_readboard_operator_capture_evidence(evidence, ROOT)

        self.assertIn("preview_confirmation.boardReplacedBeforeConfirmation must be false", "; ".join(failures))

    def test_validator_rejects_missing_or_false_top_level_user_confirmed(self) -> None:
        evidence = smoke_tauri_readboard_operator_capture.build_evidence(valid_runtime_report())
        evidence.pop("userConfirmed")

        failures = smoke_user_flows.validate_readboard_operator_capture_evidence(evidence, ROOT)

        self.assertIn("userConfirmed must be true", "; ".join(failures))

        evidence = smoke_tauri_readboard_operator_capture.build_evidence(valid_runtime_report())
        evidence["userConfirmed"] = False

        failures = smoke_user_flows.validate_readboard_operator_capture_evidence(evidence, ROOT)

        self.assertIn("userConfirmed must be true", "; ".join(failures))
        self.assertIn("userConfirmed must match previewConfirmation.userConfirmed", "; ".join(failures))

    def test_validator_rejects_overclaim_boundaries(self) -> None:
        evidence = smoke_tauri_readboard_operator_capture.build_evidence(valid_runtime_report())
        evidence["fullOcrParity"] = True
        evidence["boundaries"]["fullOcrParity"] = True

        failures = smoke_user_flows.validate_readboard_operator_capture_evidence(evidence, ROOT)

        self.assertIn("fullOcrParity must be false", "; ".join(failures))

    def test_main_writes_valid_evidence_from_runtime_report(self) -> None:
        with TemporaryDirectory() as tmp:
            report = Path(tmp) / "runtime.json"
            output = Path(tmp) / "operator.json"
            report.write_text(json.dumps(valid_runtime_report()), encoding="utf-8")
            old_argv = sys.argv[:]
            try:
                sys.argv = [
                    "smoke_tauri_readboard_operator_capture.py",
                    "--runtime-report",
                    str(report),
                    "--evidence-out",
                    str(output),
                ]
                self.assertEqual(0, smoke_tauri_readboard_operator_capture.main())
            finally:
                sys.argv = old_argv

            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual([], smoke_user_flows.validate_readboard_operator_capture_evidence(evidence, ROOT))


def valid_runtime_report() -> dict[str, object]:
    return {
        "schema": "lizzieyzy.tauri-runtime-ui-smoke.v1",
        "status": "pass",
        "platform": "macos",
        "readboardOperatorCapture": {
            "platform": "macos",
            "captureArtifact": {
                "path": "docs/qa/fixtures/readboard-controlled-board.png",
                "sanitizedPath": "docs/qa/fixtures/readboard-controlled-board.png",
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
                "source": "macos_interactive_screencapture",
                "snapshotId": "operator-capture-001",
                "snapshotHash": "3" * 64,
                "boardReplacement": "none",
                "sourceMetadata": {
                    "selection": {"x": 12, "y": 18, "width": 640, "height": 640}
                },
                "position": {
                    "board_size": 19,
                    "move_number": 0,
                    "to_play": "black",
                    "stones": [
                        {"color": "black", "x": 3, "y": 3},
                        {"color": "white", "x": 15, "y": 15},
                        {"color": "black", "x": 10, "y": 10},
                    ],
                },
                "decode": {
                    "attempted": True,
                    "status": "success",
                    "boardSize": 19,
                    "stoneCount": 3,
                    "confidence": 0.99,
                },
            },
        },
    }


def operator_selected_file_runtime_report() -> dict[str, object]:
    return {
        "schema": "lizzieyzy.tauri-runtime-ui-smoke.v1",
        "status": "fail",
        "phase": "readboard-operator-capture",
        "platform": "macos",
        "readboardOperatorCapture": {
            "platform": "macos",
            "captureArtifact": {
                "path": "tests/fixtures/readboard-images/controlled-19-three-stones.ppm",
                "sanitized": True,
                "sizeBytes": 480015,
                "sha256": "1c910bea940043ee171b36dbc9ad3d6c9365d7b317f437b563be84e8583e3f0d",
            },
            "captureSource": {
                "operatorInitiated": True,
                "userSelectionRequired": True,
                "selection": None,
                "sourceKind": "operator_selected_file",
                "requestedSource": "operator_selected_file",
                "operatorSelectedFileProvided": True,
                "selectedScreenRegionCovered": False,
                "externalScreenRegionCovered": False,
                "externalWindowRegionCovered": False,
                "targetClientDiscoveryCovered": False,
                "externalClientCaptureCovered": False,
            },
            "rawBackendResult": {
                "schema": "lizzieyzy.readboard-external-capture.v1",
                "status": "captured",
                "recoverable": False,
                "operatorInitiated": True,
                "userSelectionRequired": True,
                "source": "operator_selected_file",
                "captureSource": "operator_selected_file",
                "sanitizedPath": "operator-selected-file:controlled-19-three-stones.ppm",
                "sha256": "1c910bea940043ee171b36dbc9ad3d6c9365d7b317f437b563be84e8583e3f0d",
                "hash": "1c910bea940043ee171b36dbc9ad3d6c9365d7b317f437b563be84e8583e3f0d",
                "snapshotId": "external-capture-preview",
                "snapshotHash": "41bc57f408b78d7c5f21f954e43840a2ee256007c70b30105c84b9c7447eb922",
                "size": 480015,
                "position": {
                    "board_size": 19,
                    "move_number": 3,
                    "to_play": "white",
                    "stones": [
                        {"x": 3, "y": 3, "color": "black"},
                        {"x": 10, "y": 4, "color": "black"},
                        {"x": 15, "y": 15, "color": "white"},
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
                "boardReplacement": "none",
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
