from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SMOKE_USER_FLOWS_SCRIPT = ROOT / "scripts" / "smoke_user_flows.py"
RUNTIME_WORKFLOW_SCRIPT = ROOT / "scripts" / "smoke_installed_app_runtime_workflow.py"

USER_FLOWS_SPEC = importlib.util.spec_from_file_location("smoke_user_flows", SMOKE_USER_FLOWS_SCRIPT)
assert USER_FLOWS_SPEC is not None and USER_FLOWS_SPEC.loader is not None
smoke_user_flows = importlib.util.module_from_spec(USER_FLOWS_SPEC)
sys.modules["smoke_user_flows"] = smoke_user_flows
USER_FLOWS_SPEC.loader.exec_module(smoke_user_flows)

WORKFLOW_SPEC = importlib.util.spec_from_file_location("smoke_installed_app_runtime_workflow", RUNTIME_WORKFLOW_SCRIPT)
assert WORKFLOW_SPEC is not None and WORKFLOW_SPEC.loader is not None
smoke_installed_app_runtime_workflow = importlib.util.module_from_spec(WORKFLOW_SPEC)
sys.modules["smoke_installed_app_runtime_workflow"] = smoke_installed_app_runtime_workflow
WORKFLOW_SPEC.loader.exec_module(smoke_installed_app_runtime_workflow)


class SmokeInstalledAppRuntimeWorkflowTests(unittest.TestCase):
    def test_aggregate_evidence_matches_user_flow_validator(self) -> None:
        evidence = smoke_installed_app_runtime_workflow.build_evidence(
            installed_smoke_fixture(),
            backend_runtime_proof_fixture(),
        )

        failures = smoke_user_flows.validate_installed_app_runtime_workflow_evidence(evidence)

        self.assertEqual([], failures)
        self.assertEqual("installed_app_smoke_plus_backend_runtime_proof", evidence["collectionMethod"])
        self.assertIn("backendRuntimeProof", evidence)

    def test_main_requires_runtime_proof_input(self) -> None:
        with TemporaryDirectory() as tmp:
            installed = Path(tmp) / "installed.json"
            installed.write_text(json.dumps(installed_smoke_fixture()), encoding="utf-8")
            old_argv = sys.argv[:]
            try:
                sys.argv = [
                    "smoke_installed_app_runtime_workflow.py",
                    "--installed-app-smoke",
                    str(installed),
                ]
                with self.assertRaises(SystemExit) as raised:
                    smoke_installed_app_runtime_workflow.main()
            finally:
                sys.argv = old_argv

            self.assertNotEqual(0, raised.exception.code)

    def test_runtime_report_details_can_be_backend_proof_summary(self) -> None:
        report = {
            "schema": "lizzieyzy.tauri-runtime-ui-smoke.v1",
            "status": "pass",
            "checks": [
                {
                    "name": "backend_runtime_proof_observed",
                    "status": "pass",
                    "details": backend_runtime_proof_fixture(),
                }
            ],
        }

        evidence = smoke_installed_app_runtime_workflow.build_evidence(installed_smoke_fixture(), report)

        self.assertEqual([], smoke_user_flows.validate_installed_app_runtime_workflow_evidence(evidence))
        self.assertEqual(smoke_user_flows.INSTALLED_APP_RUNTIME_PROOF_SCHEMA, evidence["backendRuntimeProof"]["schema"])

    def test_assets_problem_with_missing_is_allowed_as_observed_problem(self) -> None:
        proof = backend_runtime_proof_fixture()
        assets = proof["assets"]
        assert isinstance(assets, dict)
        assets["status"] = "problem"
        assets["missing"] = [{"label": "katago-model"}]

        failures = smoke_user_flows.validate_installed_app_backend_runtime_proof(proof)

        self.assertEqual([], failures)

    def test_assets_ready_with_missing_is_rejected(self) -> None:
        proof = backend_runtime_proof_fixture()
        assets = proof["assets"]
        assert isinstance(assets, dict)
        assets["status"] = "ready"
        assets["missing"] = [{"label": "katago-model"}]

        failures = smoke_user_flows.validate_installed_app_backend_runtime_proof(proof)

        self.assertIn(
            "backendRuntimeProof.assets must not be ready when missing/placeholders are present",
            "; ".join(failures),
        )

    def test_main_writes_valid_repo_safe_evidence_from_inputs(self) -> None:
        with TemporaryDirectory() as tmp:
            installed = Path(tmp) / "installed.json"
            proof = Path(tmp) / "proof.json"
            output_path = Path(tmp) / "installed-app-runtime-workflow-macos.json"
            installed.write_text(json.dumps(installed_smoke_fixture()), encoding="utf-8")
            proof.write_text(json.dumps(backend_runtime_proof_fixture()), encoding="utf-8")
            old_argv = sys.argv[:]
            try:
                sys.argv = [
                    "smoke_installed_app_runtime_workflow.py",
                    "--installed-app-smoke",
                    str(installed),
                    "--runtime-proof",
                    str(proof),
                    "--evidence-out",
                    str(output_path),
                ]
                self.assertEqual(0, smoke_installed_app_runtime_workflow.main())
            finally:
                sys.argv = old_argv

            evidence = json.loads(output_path.read_text(encoding="utf-8"))
            failures = smoke_user_flows.validate_installed_app_runtime_workflow_evidence(evidence)

            self.assertEqual([], failures)
            self.assertFalse(evidence["productionSigned"])
            self.assertFalse(evidence["notarized"])
            self.assertFalse(evidence["updaterReady"])
            self.assertFalse(evidence["windowsInstalledAppCovered"])
            self.assertFalse(evidence["linuxInstalledAppCovered"])
            self.assertFalse(evidence["fullLegacyParity"])


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
                "label": "installed-app-window",
                "path": "docs/qa/screenshots/installed-macos-app-window.png",
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
                    "window": {
                        "ownerName": "LizzieYzy Next",
                        "ownerPid": 59579,
                        "windowId": 14945,
                    },
                },
            }
        ],
    }


def backend_runtime_proof_fixture() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.INSTALLED_APP_RUNTIME_PROOF_SCHEMA,
        "status": "ok",
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
            "status": "ready",
            "checks": [{"label": "resource-dir", "status": "exists"}],
            "exists": ["resource-dir"],
            "missing": [],
            "placeholders": [],
        },
        "profileStatus": {"status": "loaded", "loaded": True, "profileCount": 1},
        "engineLaunchAttempt": {
            "attempted": True,
            "status": "unavailable",
            "success": False,
            "recoverable": True,
            "errorKind": "spawnFailed",
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


if __name__ == "__main__":
    unittest.main()
