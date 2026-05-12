from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
USER_FLOWS_SCRIPT = ROOT / "scripts" / "smoke_user_flows.py"
SGF_WORKFLOW_SCRIPT = ROOT / "scripts" / "smoke_installed_app_sgf_workflow.py"

USER_FLOWS_SPEC = importlib.util.spec_from_file_location("smoke_user_flows", USER_FLOWS_SCRIPT)
assert USER_FLOWS_SPEC is not None and USER_FLOWS_SPEC.loader is not None
smoke_user_flows = importlib.util.module_from_spec(USER_FLOWS_SPEC)
sys.modules["smoke_user_flows"] = smoke_user_flows
USER_FLOWS_SPEC.loader.exec_module(smoke_user_flows)

SGF_SPEC = importlib.util.spec_from_file_location("smoke_installed_app_sgf_workflow", SGF_WORKFLOW_SCRIPT)
assert SGF_SPEC is not None and SGF_SPEC.loader is not None
smoke_installed_app_sgf_workflow = importlib.util.module_from_spec(SGF_SPEC)
sys.modules["smoke_installed_app_sgf_workflow"] = smoke_installed_app_sgf_workflow
SGF_SPEC.loader.exec_module(smoke_installed_app_sgf_workflow)


class SmokeInstalledAppSgfWorkflowTests(unittest.TestCase):
    def test_build_evidence_requires_installed_app_phase(self) -> None:
        runtime = valid_runtime_report()
        runtime["phase"] = "edit-save"

        with self.assertRaisesRegex(ValueError, "phase must be installed-app-sgf-workflow"):
            smoke_installed_app_sgf_workflow.build_evidence(valid_installed_smoke(), runtime)

    def test_build_evidence_accepts_packaged_runtime_report(self) -> None:
        evidence = smoke_installed_app_sgf_workflow.build_evidence(valid_installed_smoke(), valid_runtime_report())

        failures = smoke_user_flows.validate_installed_app_sgf_workflow_evidence(evidence)

        self.assertEqual([], failures)
        self.assertEqual("installed-app-sgf-workflow", evidence["sourceRuntimeReport"]["phase"])

    def test_derive_executable_prefers_bundle_binary(self) -> None:
        path = smoke_installed_app_sgf_workflow.derive_executable_path(valid_installed_smoke())

        self.assertEqual(
            ROOT / "target/release/bundle/macos/LizzieYzy Next.app/Contents/MacOS/lizzieyzy-next-desktop",
            path,
        )


def valid_installed_smoke() -> dict[str, object]:
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
            "mainExecutable": "lizzieyzy-next-desktop",
        },
        "bundle": {
            "binary": {
                "path": "target/release/bundle/macos/LizzieYzy Next.app/Contents/MacOS/lizzieyzy-next-desktop",
                "bytes": 17400736,
                "sha256": "176487313acb56c5f60c4388043fad81b849e8b83a3591025754dfbd9ec5e2bd",
            }
        },
        "launched": True,
        "windowObserved": True,
        "screenshotObserved": True,
        "devServerAbsent": True,
        "productionSigned": False,
        "notarized": False,
        "releasePublished": False,
        "boundaries": {"nativeDialogClickCovered": False, "webviewDomClickCovered": False},
        "screenshots": [
            {
                "label": "installed-app-window",
                "path": "docs/qa/screenshots/installed-macos-app-window.png",
                "sha256": "f0731971b0dd93513a5d103e18c96aa275495d814e2ac5940c5af59481cab3ba",
            }
        ],
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
        "termination": {"status": "pass", "exitCode": 0, "success": True},
    }


def valid_runtime_report() -> dict[str, object]:
    checks = [
        {"name": "runtime_started", "status": "pass", "details": {"tauriInternals": True}},
        {"name": "browser_fallback_excluded", "status": "pass", "details": {"tauriRuntimeObserved": True, "browserFallbackUsed": False}},
        {"name": "backend_runtime_proof_observed", "status": "pass", "details": {"raw": backend_proof()}},
        {"name": "sgf_loaded", "status": "pass", "details": {"bytes": 211, "path": "<tmp>/runtime.sgf"}},
        {"name": "branch_navigation", "status": "pass", "details": {"nodeId": "branch", "moveNumber": 2}},
        {"name": "comment_edit", "status": "pass", "details": {"comment": "ok"}},
        {"name": "property_edit", "status": "pass", "details": {"expectedProperties": {"N": "ok"}}},
        {
            "name": "annotation_edit",
            "status": "pass",
            "details": {
                "added": ["TR", "CR", "MA", "SL", "AR", "LN"],
                "updated": ["LB"],
                "removed": ["SQ"],
                "annotations": {"TR": ["aa"], "SQ": [], "CR": ["bb"], "MA": ["cc"], "SL": ["dd"], "LB": ["aa:A", "ee:E"], "AR": ["aa:bb"], "LN": ["cc:dd"]},
            },
        },
        {"name": "append_move", "status": "pass", "details": {"nodeId": "a", "vertex": "0,0"}},
        {"name": "edit_move", "status": "pass", "details": {"targetVertex": "1,0", "confirmedVertex": "1,0"}},
        {"name": "variation_reorder", "status": "pass", "details": {"movedNodeId": "a", "targetIndex": 0, "indexAfterMove": 0, "variationIndexAfterMove": 0}},
        {"name": "delete_node", "status": "pass", "details": {"deletedNodeId": "a", "existsAfterDelete": False}},
        {
            "name": "save_readback_roundtrip",
            "status": "pass",
            "details": {
                "saveVerified": True,
                "readbackVerified": True,
                "secondLaunch": {"launchIndex": 1, "status": "pass"},
                "reopen": {"path": "<tmp>/runtime.sgf", "matchesSaved": True, "secondLaunch": True},
                "afterReopen": {
                    "boardStateVerified": True,
                    "commentsVerified": True,
                    "propertiesVerified": True,
                    "annotationsVerified": True,
                    "treeOrderVerified": True,
                    "moveCountVerified": True,
                    "deletedTargetAbsent": True,
                },
            },
        },
        {"name": "board_state_verified", "status": "pass", "details": {"invariant": "ok", "verified": True}},
        {"name": "reopen_state_verified", "status": "pass", "details": {"verified": True}},
        {"name": "save_reopen_roundtrip", "status": "pass", "details": {"verified": True}},
        {"name": "scope_boundaries_recorded", "status": "pass", "details": {"fullLegacyParity": False, "releaseParity": False}},
    ]
    return {
        "schema": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_SCHEMA,
        "status": "pass",
        "platform": "macos",
        "phase": "installed-app-sgf-workflow",
        "checks": checks,
    }


def backend_proof() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.INSTALLED_APP_RUNTIME_PROOF_SCHEMA,
        "status": "ok",
        "runtime": {
            "source": "packaged-macos-app",
            "tauriRuntimeObserved": True,
            "devServerRequired": False,
            "resourceDir": "<repo>/Resources",
            "appDataDir": "<home>/Library/Application Support/org.lizzieyzy.next",
        },
        "bundle": {"appBundleExists": True, "executableExists": True, "resourceDirExists": True},
        "assets": {"status": "observed", "checks": [{"label": "resource"}], "missing": []},
        "profileStatus": {"status": "loaded", "loaded": True, "profileCount": 1},
        "engineLaunchAttempt": {"attempted": True, "status": "unavailable", "success": False},
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
