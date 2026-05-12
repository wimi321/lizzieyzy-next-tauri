from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
USER_FLOWS_SCRIPT = ROOT / "scripts" / "smoke_user_flows.py"
KATAGO_SCRIPT = ROOT / "scripts" / "smoke_installed_app_katago_live.py"

USER_FLOWS_SPEC = importlib.util.spec_from_file_location("smoke_user_flows", USER_FLOWS_SCRIPT)
assert USER_FLOWS_SPEC is not None and USER_FLOWS_SPEC.loader is not None
smoke_user_flows = importlib.util.module_from_spec(USER_FLOWS_SPEC)
sys.modules["smoke_user_flows"] = smoke_user_flows
USER_FLOWS_SPEC.loader.exec_module(smoke_user_flows)

KATAGO_SPEC = importlib.util.spec_from_file_location("smoke_installed_app_katago_live", KATAGO_SCRIPT)
assert KATAGO_SPEC is not None and KATAGO_SPEC.loader is not None
smoke_installed_app_katago_live = importlib.util.module_from_spec(KATAGO_SPEC)
sys.modules["smoke_installed_app_katago_live"] = smoke_installed_app_katago_live
KATAGO_SPEC.loader.exec_module(smoke_installed_app_katago_live)


class SmokeInstalledAppKataGoLiveTests(unittest.TestCase):
    def test_build_evidence_accepts_packaged_live_runtime_report(self) -> None:
        evidence = smoke_installed_app_katago_live.build_evidence(
            valid_installed_smoke(),
            valid_runtime_report(),
            runtime_metadata=valid_runtime_metadata(),
        )

        failures = smoke_user_flows.validate_installed_app_katago_live_workflow_evidence(evidence)

        self.assertEqual([], failures)
        self.assertEqual("installed-app-katago-live-workflow", evidence["sourceRuntimeReport"]["phase"])

    def test_build_evidence_rejects_wrong_phase(self) -> None:
        report = valid_runtime_report()
        report["phase"] = "katago-live"

        with self.assertRaisesRegex(ValueError, "phase must be installed-app-katago-live-workflow"):
            smoke_installed_app_katago_live.build_evidence(
                valid_installed_smoke(),
                report,
                runtime_metadata=valid_runtime_metadata(),
            )

    def test_build_evidence_rejects_missing_cache_hit_proof(self) -> None:
        report = valid_runtime_report()
        cache = next(check for check in report["checks"] if check["name"] == "cache_hit_restored")
        cache["details"].pop("frameCount")
        cache["details"].pop("candidateCount")
        cache["details"].pop("winrateRestored")

        with self.assertRaisesRegex(ValueError, "cache_hit_restored must include frame evidence"):
            smoke_installed_app_katago_live.build_evidence(
                valid_installed_smoke(),
                report,
                runtime_metadata=valid_runtime_metadata(),
            )

    def test_build_evidence_rejects_fake_asset_metadata(self) -> None:
        metadata = valid_runtime_metadata()
        metadata["katagoVersion"] = "KataGo stub"

        with self.assertRaisesRegex(ValueError, "fake/stub/mock"):
            smoke_installed_app_katago_live.build_evidence(
                valid_installed_smoke(),
                valid_runtime_report(),
                runtime_metadata=metadata,
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
            "sha256": "4" * 64,
            "mainExecutable": "lizzieyzy-next-desktop",
        },
        "bundle": {
            "binary": {
                "path": "target/release/bundle/macos/LizzieYzy Next.app/Contents/MacOS/lizzieyzy-next-desktop",
                "bytes": 17400736,
                "sha256": "5" * 64,
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
                "sizeBytes": 186268,
                "sha256": "6" * 64,
            }
        ],
        "checks": [
            {
                "name": "packaged_app_window_screenshot",
                "status": "pass",
                "details": {
                    "screenshot": {
                        "path": "docs/qa/screenshots/installed-macos-app-window.png",
                        "bytes": 186268,
                        "sha256": "6" * 64,
                    },
                    "window": {"ownerName": "LizzieYzy Next", "ownerPid": 59579, "windowId": 14945},
                },
            }
        ],
        "termination": {"status": "pass", "exitCode": 0, "success": True},
    }


def valid_runtime_metadata() -> dict[str, object]:
    return {
        "engine": {"kind": "katago-engine", "path": "<home>/.local/bin/katago", "sizeBytes": 10, "sha256": "1" * 64},
        "model": {"kind": "katago-model", "path": "<home>/.katago/models/latest-kata1.bin.gz", "sizeBytes": 20, "sha256": "2" * 64},
        "config": {"kind": "katago-config", "path": "<home>/.katago/configs/analysis_example.cfg", "sizeBytes": 30, "sha256": "3" * 64},
        "maxVisits": 16,
        "katagoVersion": "KataGo 1.15.3",
    }


def valid_runtime_report() -> dict[str, object]:
    metadata = valid_runtime_metadata()
    return {
        "schema": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_SCHEMA,
        "status": "pass",
        "platform": "macos",
        "phase": "installed-app-katago-live-workflow",
        "liveKataGoObserved": True,
        "browserFallbackUsed": False,
        "checks": [
            {"name": "runtime_started", "status": "pass", "details": {"tauriInternals": True, "platform": "MacIntel"}},
            {
                "name": "backend_runtime_proof_observed",
                "status": "pass",
                "details": {"raw": valid_backend_runtime_proof()},
            },
            {
                "name": "engine_assets_verified",
                "status": "pass",
                "details": {
                    "realKataGoObserved": True,
                    "observed": True,
                    "engine": metadata["engine"],
                    "model": metadata["model"],
                    "config": metadata["config"],
                    "maxVisits": metadata["maxVisits"],
                    "katagoVersion": metadata["katagoVersion"],
                    "missingRequired": [],
                },
            },
            {"name": "analysis_progress_observed", "status": "pass", "details": {"analysisProgressObserved": True, "jobId": "job-1", "completed": 1, "expected": 3, "frameCount": 1}},
            {"name": "cancel_observed", "status": "pass", "details": {"cancelRequested": True, "cancelObserved": True, "jobId": "job-1"}},
            {"name": "restart_after_cancel_observed", "status": "pass", "details": {"restartAfterCancelObserved": True, "cancelledJobId": "job-1", "restartJobId": "job-2"}},
            {"name": "analysis_complete_observed", "status": "pass", "details": {"analysisCompleteObserved": True, "frameCount": 3, "candidateCount": 2, "winrate": 0.51}},
            {"name": "cache_saved", "status": "pass", "details": {"cacheSaved": True, "cacheKey": "cache-1", "frameCount": 3}},
            {"name": "cache_hit_restored", "status": "pass", "details": {"cacheHitRestored": True, "cacheKey": "cache-1", "frameCount": 3, "candidateCount": 2, "winrateRestored": 0.51}},
            {"name": "stale_cache_prevented", "status": "pass", "details": {"staleCachePrevented": True, "jobIdGuard": True, "hashGuard": True}},
            {"name": "engine_failure_observed", "status": "pass", "details": {"engineFailureObserved": True, "message": "missing model failure observed"}},
            {"name": "browser_fallback_excluded", "status": "pass", "details": {"browserFallbackUsed": False}},
            {"name": "scope_boundaries_recorded", "status": "pass", "details": {"browserFallbackUsed": False, "releaseParity": False, "fullLegacyParity": False}},
        ],
    }


def valid_backend_runtime_proof() -> dict[str, object]:
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
