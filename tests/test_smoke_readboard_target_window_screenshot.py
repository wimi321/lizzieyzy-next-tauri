from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
USER_FLOWS_SCRIPT = ROOT / "scripts" / "smoke_user_flows.py"
USER_SPEC = importlib.util.spec_from_file_location("smoke_user_flows", USER_FLOWS_SCRIPT)
assert USER_SPEC is not None and USER_SPEC.loader is not None
smoke_user_flows = importlib.util.module_from_spec(USER_SPEC)
sys.modules["smoke_user_flows"] = smoke_user_flows
USER_SPEC.loader.exec_module(smoke_user_flows)

SCRIPT = ROOT / "scripts" / "smoke_readboard_target_window_screenshot.py"
SPEC = importlib.util.spec_from_file_location("smoke_readboard_target_window_screenshot", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
collector = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_readboard_target_window_screenshot"] = collector
SPEC.loader.exec_module(collector)


class ReadboardTargetWindowScreenshotSmokeTests(unittest.TestCase):
    def test_builds_evidence_from_runtime_report(self) -> None:
        evidence = collector.build_evidence_from_runtime_report(fake_runtime_report())

        self.assertEqual([], smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT))
        self.assertIn("rawBackendResult", evidence)
        self.assertEqual("readboard-controlled-target-proof", evidence["runtimeReportPhase"])
        valid_fixture = next(item for item in evidence["fixtureManifest"] if item["kind"] == "controlled_board")
        self.assertGreaterEqual(min(valid_fixture["width"], valid_fixture["height"]), 95)
        self.assertEqual({"controlled_board", "non_board"}, {item["kind"] for item in evidence["fixtureManifest"]})

    def test_validate_only_rejects_static_evidence_without_raw_backend(self) -> None:
        evidence = collector.build_evidence_from_runtime_report(fake_runtime_report())
        evidence.pop("rawBackendResult")

        failures = smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT)

        self.assertIn("rawBackendResult must be an object", "; ".join(failures))

    def test_rejects_source_mismatch(self) -> None:
        report = fake_runtime_report()
        report["readboardTargetWindowScreenshot"]["rawBackendResult"]["source"] = "operator_selected_file"
        report["readboardTargetWindowScreenshot"]["rawBackendResult"]["captureSource"] = "operator_selected_file"

        with self.assertRaisesRegex(collector.SmokeError, "controlled_local_target_window"):
            collector.build_evidence_from_runtime_report(report)

    def test_rejects_operator_selection_fabricated(self) -> None:
        evidence = collector.build_evidence_from_runtime_report(fake_runtime_report())
        source = evidence["captureSource"]
        assert isinstance(source, dict)
        source["operatorInitiated"] = True
        source["selection"] = {"x": 1, "y": 1, "width": 12, "height": 12}

        failures = smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT)

        detail = "; ".join(failures)
        self.assertIn("captureSource.operatorInitiated must be false", detail)
        self.assertIn("captureSource.selection must be absent", detail)

    def test_rejects_static_only_overclaim(self) -> None:
        evidence = collector.build_evidence_from_runtime_report(fake_runtime_report())
        evidence["sourceStaticOnly"] = True
        evidence["checks"][0]["details"]["sourceStaticOnly"] = True

        failures = smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT)

        self.assertIn("sourceStaticOnly must be false", "; ".join(failures))

    def test_rejects_missing_artifact_hash(self) -> None:
        evidence = collector.build_evidence_from_runtime_report(fake_runtime_report())
        evidence["screenshotArtifacts"][0].pop("sha256")

        failures = smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT)

        self.assertIn("sha256 must be a 64-character hex sha256", "; ".join(failures))

    def test_rejects_missing_target_metadata(self) -> None:
        report = fake_runtime_report()
        report["readboardTargetWindowScreenshot"]["targetWindowMetadata"].pop("title")

        with self.assertRaisesRegex(collector.SmokeError, "title must be non-empty"):
            collector.build_evidence_from_runtime_report(report)

    def test_rejects_backend_only_report_without_preview_confirmation(self) -> None:
        report = fake_runtime_report()
        report["readboardTargetWindowScreenshot"].pop("previewConfirmation")

        with self.assertRaisesRegex(collector.SmokeError, "previewConfirmation"):
            collector.build_evidence_from_runtime_report(report)

    def test_rejects_report_without_failed_decode_evidence(self) -> None:
        report = fake_runtime_report()
        report["readboardTargetWindowScreenshot"].pop("failedDecodeNoReplacement")

        with self.assertRaisesRegex(collector.SmokeError, "failedDecodeNoReplacement"):
            collector.build_evidence_from_runtime_report(report)

    def test_rejects_report_without_runtime_capture_artifact(self) -> None:
        report = fake_runtime_report()
        report["readboardTargetWindowScreenshot"].pop("captureArtifact")

        with self.assertRaisesRegex(collector.SmokeError, "captureArtifact"):
            collector.build_evidence_from_runtime_report(report)

    def test_rejects_absolute_path_in_target_metadata(self) -> None:
        evidence = collector.build_evidence_from_runtime_report(fake_runtime_report())
        evidence["targetWindowMetadata"]["imagePath"] = "/Users/haoc/private-target-window.ppm"
        evidence["rawBackendResult"]["sourceMetadata"]["imagePath"] = "/private/var/folders/runtime.ppm"

        failures = smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT)

        detail = "; ".join(failures)
        self.assertIn("targetWindowMetadata.imagePath must not contain a local absolute path", detail)
        self.assertIn("rawBackendResult.sourceMetadata.imagePath must not contain a local absolute path", detail)

    def test_rejects_confirmed_preview_with_nested_false_after_state(self) -> None:
        evidence = collector.build_evidence_from_runtime_report(fake_runtime_report())
        evidence["previewConfirmation"]["afterConfirmation"] = {"boardReplacedOnlyAfterConfirmation": False}
        evidence["checks"][4]["details"] = evidence["previewConfirmation"]

        failures = smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT)

        self.assertIn("contradicts confirmed preview/import state", "; ".join(failures))

    def test_rejects_confirmed_preview_with_false_dom_attributes(self) -> None:
        evidence = collector.build_evidence_from_runtime_report(fake_runtime_report())
        evidence["previewConfirmation"]["confirmationControl"] = {
            "attributes": {
                "data-user-confirmed": "false",
                "data-can-import-preview": "false",
            }
        }
        evidence["checks"][4]["details"] = evidence["previewConfirmation"]

        failures = smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT)

        detail = "; ".join(failures)
        self.assertIn("previewConfirmation.confirmationControl.attributes.data-user-confirmed", detail)
        self.assertIn("previewConfirmation.confirmationControl.attributes.data-can-import-preview", detail)

    def test_accepts_runtime_preview_before_confirmation_false_state(self) -> None:
        report = fake_runtime_report()
        preview = report["readboardTargetWindowScreenshot"]["previewConfirmation"]
        assert isinstance(preview, dict)
        preview.pop("previewProduced")
        preview["beforeConfirmation"] = {
            "previewVisible": True,
            "userConfirmed": False,
            "boardReplacedOnlyAfterConfirmation": False,
            "confirmationControl": {
                "attributes": {
                    "data-user-confirmed": "false",
                    "data-can-import-preview": "false",
                }
            },
        }
        preview["afterConfirmation"] = {
            "previewVisible": True,
            "userConfirmed": True,
            "boardReplacedOnlyAfterConfirmation": True,
        }

        evidence = collector.build_evidence_from_runtime_report(report)

        self.assertTrue(evidence["decodeResult"]["previewProduced"])
        self.assertEqual([], smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT))

    def test_rejects_failed_decode_import(self) -> None:
        evidence = collector.build_evidence_from_runtime_report(fake_runtime_report())
        evidence["failedDecodeNoReplacement"]["imported"] = True
        evidence["checks"][5]["details"]["imported"] = True

        failures = smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT)

        self.assertIn("failedDecodeNoReplacement.imported must be false", "; ".join(failures))

    def test_rejects_fixture_manifest_missing_required_shape(self) -> None:
        evidence = collector.build_evidence_from_runtime_report(fake_runtime_report())
        evidence["fixtureManifest"] = [item for item in evidence["fixtureManifest"] if item["kind"] != "controlled_board"]
        evidence["checks"][6]["details"]["fixtures"] = evidence["fixtureManifest"]

        failures = smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT)

        self.assertIn("missing fixture kinds: controlled_board", "; ".join(failures))

    def test_rejects_valid_fixture_too_small(self) -> None:
        too_small = ROOT / "tests/fixtures/readboard-screenshots/target-window-too-small.ppm"
        with self.assertRaisesRegex(collector.SmokeError, "at least 95"):
            collector.artifact_record(too_small, kind="scale", expected_outcome="decode_success")

        evidence = collector.build_evidence_from_runtime_report(fake_runtime_report())
        data = too_small.read_bytes()
        small_record = {
            "kind": "controlled_board",
            "path": too_small.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(data).hexdigest(),
            "sizeBytes": len(data),
            "sanitized": True,
            "expectedOutcome": "decode_success",
            "width": 4,
            "height": 4,
            "boardSize": 19,
            "stoneCount": 3,
        }
        evidence["fixtureManifest"][0] = small_record
        evidence["checks"][6]["details"]["fixtures"] = evidence["fixtureManifest"]

        failures = smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT)

        self.assertIn("fixture side must be at least 95px", "; ".join(failures))

    def test_runtime_report_cli_writes_valid_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_path = tmp_path / "runtime-report.json"
            evidence_path = tmp_path / "evidence.json"
            report_path.write_text(json.dumps(fake_runtime_report()), encoding="utf-8")

            self.assertEqual(0, collector.main(["--runtime-report", str(report_path), "--evidence-out", str(evidence_path)]))
            self.assertEqual(0, collector.main(["--check-only", "--evidence-out", str(evidence_path)]))


def fake_runtime_report() -> dict[str, object]:
    snapshot_hash = "c8102fb47a1ee533c7762741774b805877994c9ae13b6d77c36290bff988fe87"
    capture_artifact = collector.artifact_record(
        ROOT / "tests/fixtures/readboard-screenshots/target-window-scale.ppm",
        kind="controlled_board",
        expected_outcome="decode_success",
    )
    failed_artifact = collector.artifact_record(
        ROOT / "tests/fixtures/readboard-screenshots/target-window-non-board.ppm",
        kind="non_board",
        expected_outcome="decode_error",
    )
    return {
        "schema": "lizzieyzy.tauri-runtime-ui-smoke.v1",
        "phase": "readboard-controlled-target-proof",
        "platform": "macos",
        "runtimeObserved": True,
        "readboardTargetWindowScreenshot": {
            "targetWindowMetadata": {
                "controlledFixture": True,
                "targetClientDiscovery": False,
                "windowIdSanitized": True,
                "title": "Controlled Readboard Target Window",
                "appName": "LizzieYzy Next Fixture Host",
                "processName": "readboard-fixture-host",
                "captureSource": "controlled_local_target_window",
                "fixtureSize": "640x480",
                "bounds": {"x": 16, "y": 24, "width": 640, "height": 480},
            },
            "captureArtifact": capture_artifact,
            "previewConfirmation": {
                "previewProduced": True,
                "previewOnlyBeforeConfirmation": True,
                "boardReplacedBeforeConfirmation": False,
                "userConfirmed": True,
                "boardReplacedOnlyAfterConfirmation": True,
            },
            "failedDecodeNoReplacement": {
                "fixtureKind": "non_board",
                "decodeAttempted": True,
                "decodeSucceeded": False,
                "previewProduced": False,
                "imported": False,
                "boardReplaced": False,
                "errorKind": "ImageLowConfidence",
                "artifact": failed_artifact,
            },
            "rawBackendResult": {
                "status": "captured",
                "source": "controlled_local_target_window",
                "captureSource": "controlled_local_target_window",
                "snapshotId": "target-window-screenshot-001",
                "snapshotHash": snapshot_hash,
                "boardReplacement": "none",
                "sourceMetadata": {
                    "controlledFixture": True,
                    "targetClientDiscovery": False,
                    "windowIdSanitized": True,
                    "title": "Controlled Readboard Target Window",
                    "appName": "LizzieYzy Next Fixture Host",
                    "processName": "readboard-fixture-host",
                    "captureSource": "controlled_local_target_window",
                    "fixtureSize": "640x480",
                    "bounds": {"x": 16, "y": 24, "width": 640, "height": 480},
                },
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
                    "boardSize": 19,
                    "stoneCount": 3,
                },
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
