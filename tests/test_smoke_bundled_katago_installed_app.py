from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SMOKE_USER_FLOWS_SCRIPT = ROOT / "scripts" / "smoke_user_flows.py"
BUNDLED_SCRIPT = ROOT / "scripts" / "smoke_bundled_katago_installed_app.py"

USER_FLOWS_SPEC = importlib.util.spec_from_file_location("smoke_user_flows", SMOKE_USER_FLOWS_SCRIPT)
assert USER_FLOWS_SPEC is not None and USER_FLOWS_SPEC.loader is not None
smoke_user_flows = importlib.util.module_from_spec(USER_FLOWS_SPEC)
sys.modules["smoke_user_flows"] = smoke_user_flows
USER_FLOWS_SPEC.loader.exec_module(smoke_user_flows)

BUNDLED_SPEC = importlib.util.spec_from_file_location("smoke_bundled_katago_installed_app", BUNDLED_SCRIPT)
assert BUNDLED_SPEC is not None and BUNDLED_SPEC.loader is not None
smoke_bundled_katago_installed_app = importlib.util.module_from_spec(BUNDLED_SPEC)
sys.modules["smoke_bundled_katago_installed_app"] = smoke_bundled_katago_installed_app
BUNDLED_SPEC.loader.exec_module(smoke_bundled_katago_installed_app)


class SmokeBundledKataGoInstalledAppTests(unittest.TestCase):
    def test_build_evidence_matches_user_flow_validator_with_structured_unavailable(self) -> None:
        evidence = smoke_bundled_katago_installed_app.build_evidence(
            installed_smoke_fixture(),
            installed_runtime_workflow_fixture(),
        )

        failures = smoke_user_flows.validate_bundled_katago_installed_app_smoke_evidence(evidence)

        self.assertEqual([], failures)
        self.assertEqual("incomplete", evidence["bundledAssetLayout"]["status"])
        self.assertFalse(evidence["engineLaunchAttempt"]["launchSucceeded"])
        self.assertFalse(evidence["fullBundledKataGoParity"])

    def test_build_rejects_artifact_only_runtime_input(self) -> None:
        runtime = installed_runtime_workflow_fixture()
        runtime["artifactOnly"] = True
        runtime["boundaries"]["artifactOnly"] = True

        with self.assertRaises(ValueError) as raised:
            smoke_bundled_katago_installed_app.build_evidence(installed_smoke_fixture(), runtime)

        self.assertIn("artifactOnly must be false", str(raised.exception))

    def test_build_accepts_bundled_katago_camel_case_from_rust(self) -> None:
        runtime = installed_runtime_workflow_fixture()
        proof = runtime["backendRuntimeProof"]
        assert isinstance(proof, dict)
        proof["bundledKatago"] = proof.pop("bundledKataGo")
        for check in runtime["checks"]:
            if isinstance(check, dict) and check.get("name") == "backend_runtime_proof_observed":
                details = check["details"]
                assert isinstance(details, dict)
                details["backendRuntimeProof"] = proof

        evidence = smoke_bundled_katago_installed_app.build_evidence(installed_smoke_fixture(), runtime)

        self.assertEqual([], smoke_user_flows.validate_bundled_katago_installed_app_smoke_evidence(evidence))
        self.assertEqual("incomplete", evidence["bundledAssetLayout"]["status"])

    def test_runtime_workflow_extractor_prefers_raw_bundled_katago_runtime_report_shape(self) -> None:
        proof_summary = backend_runtime_proof_fixture()
        proof_summary.pop("bundledKataGo")
        raw_proof = backend_runtime_proof_fixture()
        raw_proof["bundledKatago"] = raw_proof.pop("bundledKataGo")
        report = {
            "schema": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_SCHEMA,
            "status": "pass",
            "checks": [
                {
                    "name": "backend_runtime_proof_observed",
                    "status": "pass",
                    "details": {
                        "backendRuntimeProof": proof_summary,
                        "raw": raw_proof,
                    },
                }
            ],
        }

        runtime_evidence = smoke_bundled_katago_installed_app.smoke_installed_app_runtime_workflow.build_evidence(
            installed_smoke_fixture(),
            report,
        )
        bundled = runtime_evidence["backendRuntimeProof"]["bundledKatago"]
        raw_bundled = runtime_evidence["backendRuntimeProof"]["raw"]["bundledKatago"]
        evidence = smoke_bundled_katago_installed_app.build_evidence(installed_smoke_fixture(), runtime_evidence)

        self.assertEqual("incomplete", bundled["status"])
        self.assertEqual("incomplete", raw_bundled["status"])
        self.assertEqual([], smoke_user_flows.validate_bundled_katago_installed_app_smoke_evidence(evidence))

    def test_runtime_workflow_extractor_normalizes_real_rust_bundled_katago_dto_shape(self) -> None:
        proof_summary = backend_runtime_proof_fixture()
        proof_summary.pop("bundledKataGo")
        raw_proof = backend_runtime_proof_fixture()
        raw_proof.pop("bundledKataGo")
        raw_proof["bundledKatago"] = rust_bundled_katago_dto_fixture()
        report = {
            "schema": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_SCHEMA,
            "status": "pass",
            "checks": [
                {
                    "name": "backend_runtime_proof_observed",
                    "status": "pass",
                    "details": {
                        "backendRuntimeProof": proof_summary,
                        "raw": raw_proof,
                    },
                }
            ],
        }

        runtime_evidence = smoke_bundled_katago_installed_app.smoke_installed_app_runtime_workflow.build_evidence(
            installed_smoke_fixture(),
            report,
        )
        bundled = runtime_evidence["backendRuntimeProof"]["bundledKatago"]
        raw_bundled = runtime_evidence["backendRuntimeProof"]["raw"]["bundledKatago"]
        evidence = smoke_bundled_katago_installed_app.build_evidence(installed_smoke_fixture(), runtime_evidence)

        self.assertEqual("bundledAsset", raw_bundled["source"])
        self.assertEqual("incomplete", bundled["status"])
        self.assertEqual(3, bundled["checks"])
        self.assertEqual(3, len(bundled["missing"]))
        self.assertEqual([], smoke_user_flows.validate_bundled_katago_installed_app_smoke_evidence(evidence))

    def test_validator_rejects_claimed_bundled_katago_without_raw_bundled_katago(self) -> None:
        evidence = smoke_bundled_katago_installed_app.build_evidence(
            installed_smoke_fixture(),
            installed_runtime_workflow_fixture(),
        )
        raw = evidence["backendRuntimeProof"]["raw"]
        assert isinstance(raw, dict)
        raw.pop("bundledKatago", None)

        failures = smoke_user_flows.validate_bundled_katago_installed_app_smoke_evidence(evidence)

        self.assertIn("backendRuntimeProof.raw.bundledKatago must be recorded", "; ".join(failures))

    def test_validator_rejects_raw_bundled_katago_ready_claim_when_assets_missing(self) -> None:
        evidence = smoke_bundled_katago_installed_app.build_evidence(
            installed_smoke_fixture(),
            installed_runtime_workflow_fixture(),
        )
        raw = evidence["backendRuntimeProof"]["raw"]
        assert isinstance(raw, dict)
        raw_bundled = raw["bundledKatago"]
        assert isinstance(raw_bundled, dict)
        raw_bundled["status"] = "ready"
        raw_bundled["validationStatus"] = "ready"
        raw_bundled["complete"] = True
        raw_bundled["success"] = True

        failures = smoke_user_flows.validate_bundled_katago_installed_app_smoke_evidence(evidence)
        detail = "; ".join(failures)

        self.assertIn(
            "backendRuntimeProof.raw.backendRuntimeProof.bundledKataGo must not be ready when missing/placeholders are present",
            detail,
        )
        self.assertIn(
            "backendRuntimeProof.raw.backendRuntimeProof.bundledKataGo missing assets must remain incomplete/unavailable",
            detail,
        )

    def test_build_rejects_backend_proof_without_bundled_katago_aliases(self) -> None:
        runtime = installed_runtime_workflow_fixture()
        proof = runtime["backendRuntimeProof"]
        assert isinstance(proof, dict)
        proof.pop("bundledKataGo")
        proof.pop("bundledKatago", None)
        proof.pop("bundled_katago", None)

        with self.assertRaises(ValueError) as raised:
            smoke_bundled_katago_installed_app.build_evidence(installed_smoke_fixture(), runtime)

        self.assertIn("backend runtime proof must include bundledKatago/bundledKataGo/bundled_katago", str(raised.exception))

    def test_validator_rejects_backend_proof_without_bundled_katago_aliases(self) -> None:
        evidence = smoke_bundled_katago_installed_app.build_evidence(
            installed_smoke_fixture(),
            installed_runtime_workflow_fixture(),
        )
        evidence["backendRuntimeProof"].pop("bundledKataGo")
        evidence["backendRuntimeProof"].pop("bundledKatago", None)
        evidence["backendRuntimeProof"].pop("bundled_katago", None)

        failures = smoke_user_flows.validate_bundled_katago_installed_app_smoke_evidence(evidence)

        self.assertIn("backendRuntimeProof.bundledKatago must be recorded", "; ".join(failures))

    def test_validator_rejects_unavailable_counted_as_launch_success(self) -> None:
        evidence = smoke_bundled_katago_installed_app.build_evidence(
            installed_smoke_fixture(),
            installed_runtime_workflow_fixture(),
        )
        evidence["engineLaunchAttempt"]["launchSucceeded"] = True

        failures = smoke_user_flows.validate_bundled_katago_installed_app_smoke_evidence(evidence)

        self.assertIn(
            "engineLaunchAttempt unavailable/problem status must not be counted as success",
            "; ".join(failures),
        )

    def test_validator_rejects_ready_layout_with_missing_assets(self) -> None:
        evidence = smoke_bundled_katago_installed_app.build_evidence(
            installed_smoke_fixture(),
            installed_runtime_workflow_fixture(),
        )
        evidence["bundledAssetLayout"]["status"] = "ready"
        evidence["bundledAssetLayout"]["missing"] = [{"label": "model"}]

        failures = smoke_user_flows.validate_bundled_katago_installed_app_smoke_evidence(evidence)

        self.assertIn(
            "bundledAssetLayout must not be ready when missing/placeholders are present",
            "; ".join(failures),
        )

    def test_validator_rejects_overclaim(self) -> None:
        evidence = smoke_bundled_katago_installed_app.build_evidence(
            installed_smoke_fixture(),
            installed_runtime_workflow_fixture(),
        )
        evidence["fullBundledKataGoParity"] = True
        evidence["boundaries"]["fullBundledKataGoParity"] = True

        failures = smoke_user_flows.validate_bundled_katago_installed_app_smoke_evidence(evidence)

        self.assertIn("fullBundledKataGoParity must be false", "; ".join(failures))

    def test_validator_rejects_dev_server_runtime_source(self) -> None:
        evidence = smoke_bundled_katago_installed_app.build_evidence(
            installed_smoke_fixture(),
            installed_runtime_workflow_fixture(),
        )
        evidence["runtimeSource"]["sourceKind"] = "tauri-dev"

        failures = smoke_user_flows.validate_bundled_katago_installed_app_smoke_evidence(evidence)

        self.assertIn("runtimeSource.sourceKind must be packaged-macos-app", "; ".join(failures))

    def test_main_writes_valid_repo_safe_evidence_from_inputs(self) -> None:
        with TemporaryDirectory() as tmp:
            installed = Path(tmp) / "installed.json"
            runtime = Path(tmp) / "runtime.json"
            output_path = Path(tmp) / "bundled-katago-installed-app-smoke-macos.json"
            installed.write_text(json.dumps(installed_smoke_fixture()), encoding="utf-8")
            runtime.write_text(json.dumps(installed_runtime_workflow_fixture()), encoding="utf-8")
            old_argv = sys.argv[:]
            try:
                sys.argv = [
                    "smoke_bundled_katago_installed_app.py",
                    "--installed-app-smoke",
                    str(installed),
                    "--runtime-workflow",
                    str(runtime),
                    "--evidence-out",
                    str(output_path),
                ]
                self.assertEqual(0, smoke_bundled_katago_installed_app.main())
            finally:
                sys.argv = old_argv

            evidence = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual([], smoke_user_flows.validate_bundled_katago_installed_app_smoke_evidence(evidence))


def installed_smoke_fixture() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.INSTALLED_MACOS_APP_SMOKE_SCHEMA,
        "name": "installed_macos_app_smoke",
        "status": "pass",
        "platform": "macos",
        "appBundlePath": "target/release/bundle/macos/LizzieYzy Next.app",
        "appBundle": {
            "exists": True,
            "path": "target/release/bundle/macos/LizzieYzy Next.app",
            "sizeBytes": 17399164,
            "sha256": "2530d458dd7b676911e5e36088d7a902887e9a9e9edffa1bbecada7b12bc9de6",
        },
        "launched": True,
        "windowObserved": True,
        "screenshotObserved": True,
        "devServerAbsent": True,
        "productionSigned": False,
        "notarized": False,
        "releasePublished": False,
        "boundaries": {
            "nativeDialogClickCovered": False,
            "webviewDomClickCovered": False,
        },
        "screenshots": [
            {
                "name": "installed-macos-app-window",
                "path": "docs/qa/screenshots/installed-macos-app-window.png",
                "bytes": 186268,
                "sha256": "f0731971b0dd93513a5d103e18c96aa275495d814e2ac5940c5af59481cab3ba",
            }
        ],
        "termination": {"status": "pass", "exitCode": 0, "success": True},
        "checks": [
            {
                "name": "packaged_app_window_screenshot",
                "status": "pass",
                "details": {
                    "screenshot": {
                        "name": "installed-macos-app-window",
                        "path": "docs/qa/screenshots/installed-macos-app-window.png",
                        "bytes": 186268,
                        "sha256": "f0731971b0dd93513a5d103e18c96aa275495d814e2ac5940c5af59481cab3ba",
                    },
                    "window": {"ownerName": "LizzieYzy Next", "ownerPid": 59579, "windowId": 14945},
                },
            }
        ],
    }


def installed_runtime_workflow_fixture() -> dict[str, object]:
    proof = backend_runtime_proof_fixture()
    app_bundle = installed_smoke_fixture()["appBundle"]
    screenshot = {
        "label": "installed-app-runtime-window",
        "source": "installed_app_runtime",
        "path": "docs/qa/screenshots/installed-macos-app-window.png",
        "sizeBytes": 186268,
        "sha256": "f0731971b0dd93513a5d103e18c96aa275495d814e2ac5940c5af59481cab3ba",
        "capturedAfterActionId": "observe_main_window",
    }
    boundaries = {
        "browserFallbackUsed": False,
        "sourceStaticOnly": False,
        "artifactOnly": False,
        "runnerStartedDevServer": False,
        "runnerStartedViteDevServer": False,
        "productionSigned": False,
        "signed": False,
        "notarized": False,
        "updaterReady": False,
        "updaterCovered": False,
        "releasePublished": False,
        "windowsInstalledAppCovered": False,
        "linuxInstalledAppCovered": False,
        "windowsLinuxInstalledAppCovered": False,
        "fullInstalledAppParity": False,
        "fullLegacyParity": False,
        "fullShortcutParity": False,
        "fullLayoutParity": False,
        "providerReadboardOcrParity": False,
        "providerReadboardOCRParity": False,
    }
    return {
        "schema": smoke_user_flows.INSTALLED_APP_RUNTIME_WORKFLOW_SCHEMA,
        "name": "installed_app_runtime_workflow",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "installed_app_smoke_plus_backend_runtime_proof",
        "runtimeSource": "packaged-macos-app",
        "runtimeObserved": True,
        "installedAppLaunched": True,
        "runtimeProcessObserved": True,
        "windowObserved": True,
        "workflowExecuted": True,
        "screenshotObserved": True,
        "devServerAbsent": True,
        **boundaries,
        "appBundle": app_bundle,
        "runtimeProcess": {"observed": True, "processName": "LizzieYzy Next", "pid": 59579},
        "backendRuntimeProof": proof,
        "workflowActions": [
            {"actionId": "launch_installed_app", "status": "pass", "runtimeObserved": True, "evidence": {"appBundlePath": "target/release/bundle/macos/LizzieYzy Next.app"}},
            {"actionId": "observe_main_window", "status": "pass", "runtimeObserved": True, "evidence": {"windowTitle": "LizzieYzy"}},
            {
                "actionId": "execute_runtime_action",
                "status": "pass",
                "runtimeObserved": True,
                "evidence": {
                    "backendCommand": "installed_app_runtime_proof",
                    "proofSchema": smoke_user_flows.INSTALLED_APP_RUNTIME_PROOF_SCHEMA,
                    "runtimeSource": "packaged-macos-app",
                },
            },
            {"actionId": "terminate_installed_app", "status": "pass", "runtimeObserved": True, "evidence": {"terminated": True, "exitCode": 0}},
        ],
        "screenshots": [screenshot],
        "devServerPreflight": {"reachableBeforeLaunch": False, "runnerStartedDevServer": False},
        "termination": {"status": "pass", "exitCode": 0, "success": True},
        "boundaries": boundaries,
        "checks": [
            {"name": "app_bundle_verified", "status": "pass", "details": {"appBundle": app_bundle}},
            {"name": "installed_app_launched", "status": "pass", "details": {"installedAppLaunched": True}},
            {"name": "runtime_process_observed", "status": "pass", "details": {"observed": True, "processName": "LizzieYzy Next", "pid": 59579}},
            {"name": "window_observed", "status": "pass", "details": {"windowObserved": True}},
            {
                "name": "workflow_action_executed",
                "status": "pass",
                "details": {
                    "workflowExecuted": True,
                    "actionId": "execute_runtime_action",
                    "backendCommand": "installed_app_runtime_proof",
                    "proofSchema": smoke_user_flows.INSTALLED_APP_RUNTIME_PROOF_SCHEMA,
                },
            },
            {"name": "backend_runtime_proof_observed", "status": "pass", "details": {"backendRuntimeProof": proof}},
            {"name": "screenshot_recorded", "status": "pass", "details": {"screenshots": [screenshot]}},
            {"name": "dev_server_absent", "status": "pass", "details": {"devServerAbsent": True}},
            {"name": "quit_or_terminate_observed", "status": "pass", "details": {"status": "pass", "exitCode": 0, "success": True}},
            {"name": "scope_boundaries_recorded", "status": "pass", "details": {"boundaries": boundaries}},
        ],
    }


def backend_runtime_proof_fixture() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.INSTALLED_APP_RUNTIME_PROOF_SCHEMA,
        "status": "observed",
        "platform": "macos",
        "runtime": {
            "source": "packaged-macos-app",
            "tauriRuntimeObserved": True,
            "devServerRequired": False,
            "resourceDir": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources",
            "appDataDir": "<home>/Library/Application Support/org.lizzieyzy.next",
        },
        "bundle": {
            "appBundlePath": "target/release/bundle/macos/LizzieYzy Next.app",
            "appBundleExists": True,
            "executableExists": True,
            "resourceDirExists": True,
        },
        "assets": {
            "status": "problem",
            "checks": 3,
            "exists": [{"label": "runtime root", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources"}],
            "missing": [{"label": "KataGo models", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/models"}],
            "placeholders": [],
            "details": {
                "checks": [
                    {"label": "runtime root", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources", "status": "exists"},
                    {"label": "KataGo models", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/models", "status": "missing"},
                ],
                "exists": [{"label": "runtime root", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources"}],
                "missing": [{"label": "KataGo models", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/models"}],
                "layout": {"source": "resource_dir"},
            },
        },
        "bundledKataGo": bundled_katago_fixture(),
        "profileStatus": {"status": "defaultMissingFile", "loaded": False, "profileCount": 1},
        "engineLaunchAttempt": {
            "attempted": True,
            "status": "unavailable",
            "availability": "unavailable",
            "success": False,
            "launchSucceeded": False,
            "recoverable": True,
            "errorKind": "missingEnginePath",
            "details": {"status": "unavailable", "errorKind": "missingEnginePath"},
        },
        "boundaries": {
            "browserFallbackUsed": False,
            "devServerStarted": False,
            "realReleasePublished": False,
            "productionSigned": False,
            "notarized": False,
            "fullLegacyParity": False,
        },
    }


def bundled_katago_fixture() -> dict[str, object]:
    return {
        "sourceKind": "packaged-macos-app",
        "status": "incomplete",
        "validationStatus": "incomplete",
        "complete": False,
        "checks": 4,
        "exists": [
            {
                "label": "runtime root",
                "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources",
                "status": "exists",
            }
        ],
        "missing": [
            {
                "label": "KataGo bin",
                "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/bin",
                "status": "missing",
            },
            {
                "label": "KataGo models",
                "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/models",
                "status": "missing",
            },
            {
                "label": "KataGo configs",
                "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/configs",
                "status": "missing",
            },
        ],
        "placeholders": [],
        "details": {
            "checks": [
                {
                    "label": "runtime root",
                    "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources",
                    "status": "exists",
                },
                {
                    "label": "KataGo bin",
                    "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/bin",
                    "status": "missing",
                },
                {
                    "label": "KataGo models",
                    "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/models",
                    "status": "missing",
                },
                {
                    "label": "KataGo configs",
                    "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/configs",
                    "status": "missing",
                },
            ],
            "exists": [
                {
                    "label": "runtime root",
                    "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources",
                    "status": "exists",
                }
            ],
            "missing": [
                {
                    "label": "KataGo bin",
                    "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/bin",
                    "status": "missing",
                },
                {
                    "label": "KataGo models",
                    "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/models",
                    "status": "missing",
                },
                {
                    "label": "KataGo configs",
                    "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/configs",
                    "status": "missing",
                },
            ],
            "placeholders": [],
            "layout": {"source": "resource_dir"},
        },
    }


def rust_bundled_katago_dto_fixture() -> dict[str, object]:
    return {
        "status": "incomplete",
        "source": "bundledAsset",
        "root": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago",
        "profile": {"status": "defaultMissingFile", "selectedProfileName": "Local KataGo"},
        "engine": {
            "status": "missing",
            "exists": False,
            "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/bin",
            "sizeBytes": 0,
            "sha256": None,
        },
        "model": {
            "status": "missing",
            "exists": False,
            "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/models",
            "sizeBytes": 0,
            "sha256": None,
        },
        "config": {
            "status": "missing",
            "exists": False,
            "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/configs",
            "sizeBytes": 0,
            "sha256": None,
        },
        "warnings": ["Bundled KataGo assets are incomplete in this local packaged app"],
    }


if __name__ == "__main__":
    unittest.main()
