from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
USER_FLOWS_SCRIPT = ROOT / "scripts" / "smoke_user_flows.py"
CAPTURE_SCRIPT = ROOT / "scripts" / "smoke_readboard_external_capture_mvp.py"

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


if __name__ == "__main__":
    unittest.main()
