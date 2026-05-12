#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import smoke_installed_app_runtime_workflow  # noqa: E402
import smoke_user_flows  # noqa: E402


SCHEMA = "lizzieyzy.bundled-katago-installed-app-smoke.v1"
DEFAULT_EVIDENCE_OUT = "docs/qa/bundled-katago-installed-app-smoke-macos.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [sanitize(child) for child in value]
    if isinstance(value, str):
        sanitized = value
        root = str(ROOT)
        if root in sanitized:
            sanitized = sanitized.replace(root, "<repo>")
        home = os.path.expanduser("~")
        if home and home in sanitized:
            sanitized = sanitized.replace(home, "<home>")
        sanitized = re.sub(r"/private/var/folders/[^\s\"']+", "<tmp>", sanitized)
        sanitized = re.sub(r"/var/folders/[^\s\"']+", "<tmp>", sanitized)
        sanitized = re.sub(r"/tmp/[^\s\"']+", "<tmp>", sanitized)
        return sanitized
    return value


def pass_check(name: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass", "details": details}


def first_check_details(evidence: dict[str, Any], name: str) -> dict[str, Any]:
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        return {}
    for check in checks:
        if isinstance(check, dict) and check.get("name") == name:
            details = check.get("details")
            return details if isinstance(details, dict) else {}
    return {}


def screenshot_records(installed_smoke: dict[str, Any], runtime_workflow: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    runtime_screenshots = runtime_workflow.get("screenshots")
    if isinstance(runtime_screenshots, list):
        records.extend(record for record in runtime_screenshots if isinstance(record, dict))
    runtime_check = first_check_details(runtime_workflow, "screenshot_recorded")
    check_records = runtime_check.get("screenshots")
    if isinstance(check_records, list):
        records.extend(record for record in check_records if isinstance(record, dict))
    installed_check = first_check_details(installed_smoke, "packaged_app_window_screenshot")
    screenshot = installed_check.get("screenshot")
    if isinstance(screenshot, dict):
        records.append(screenshot)

    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for record in records:
        path = record.get("path")
        sha = record.get("sha256")
        size = record.get("sizeBytes") or record.get("bytes")
        if not isinstance(path, str) or not smoke_user_flows.is_sha256_hex(sha) or not smoke_user_flows.positive_number(size):
            continue
        key = (path, sha)
        if key in seen:
            continue
        seen.add(key)
        unique.append(
            {
                "label": record.get("label") or record.get("name") or "bundled-katago-installed-app-window",
                "source": "bundled_katago_installed_app",
                "path": path,
                "sizeBytes": size,
                "sha256": sha,
            }
        )
    if not unique:
        raise ValueError("installed/runtime evidence must include screenshot path/sha256/size metadata")
    return unique


def boundary_values() -> dict[str, bool]:
    return {
        "sourceStaticOnly": False,
        "artifactOnly": False,
        "browserFallbackUsed": False,
        "runnerStartedDevServer": False,
        "runnerStartedViteDevServer": False,
        "fullBundledKataGoParity": False,
        "fullKataGoParity": False,
        "bundledLargeModelParity": False,
        "releaseParity": False,
        "signedReleaseParity": False,
        "productionSigned": False,
        "notarized": False,
        "updaterReady": False,
        "windowsLinuxParity": False,
        "windowsInstalledAppCovered": False,
        "linuxInstalledAppCovered": False,
        "fullLegacyParity": False,
        "providerParity": False,
        "readboardParity": False,
        "ocrParity": False,
    }


def runtime_source_from_proof(proof: dict[str, Any]) -> dict[str, Any]:
    runtime = proof.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("backend runtime proof must include runtime")
    return {
        "sourceKind": runtime.get("source") or runtime.get("runtimeSource"),
        "tauriRuntimeObserved": runtime.get("tauriRuntimeObserved"),
        "devServerRequired": runtime.get("devServerRequired"),
        "resourceDir": runtime.get("resourceDir") or runtime.get("resource_dir"),
        "appDataDir": runtime.get("appDataDir") or runtime.get("app_data_dir"),
    }


def bundled_asset_layout_from_proof(proof: dict[str, Any]) -> dict[str, Any]:
    bundled = bundled_katago_from_proof(proof)
    details = bundled.get("details") if isinstance(bundled.get("details"), dict) else {}
    layout = details.get("layout") if isinstance(details.get("layout"), dict) else {}
    paths: list[str] = []
    for section in ("checks", "exists", "missing", "placeholders"):
        records = details.get(section)
        if isinstance(records, list):
            for record in records:
                if isinstance(record, dict) and isinstance(record.get("path"), str):
                    paths.append(record["path"])
    return {
        "sourceKind": "packaged-macos-app",
        "status": bundled.get("status"),
        "validationStatus": bundled.get("status"),
        "checks": bundled.get("checks"),
        "exists": bundled.get("exists"),
        "missing": bundled.get("missing"),
        "placeholders": bundled.get("placeholders"),
        "warnings": bundled.get("warnings"),
        "paths": sorted(set(paths)),
        "details": {
            "layout": layout,
            "exists": details.get("exists"),
            "missing": details.get("missing"),
            "placeholders": details.get("placeholders"),
            "checks": details.get("checks"),
        },
    }


def bundled_katago_from_proof(proof: dict[str, Any]) -> dict[str, Any]:
    bundled = proof.get("bundledKatago")
    if not isinstance(bundled, dict):
        bundled = proof.get("bundledKataGo")
    if not isinstance(bundled, dict):
        bundled = proof.get("bundled_katago")
    if not isinstance(bundled, dict):
        raise ValueError("backend runtime proof must include bundledKatago/bundledKataGo/bundled_katago")
    return bundled


def engine_launch_attempt_from_proof(proof: dict[str, Any]) -> dict[str, Any]:
    attempt = proof.get("engineLaunchAttempt")
    if not isinstance(attempt, dict):
        raise ValueError("backend runtime proof must include engineLaunchAttempt")
    return attempt


def build_evidence(installed_smoke: dict[str, Any], runtime_input: dict[str, Any]) -> dict[str, Any]:
    installed_failures = smoke_user_flows.validate_installed_macos_app_smoke_evidence(installed_smoke)
    if installed_failures:
        raise ValueError("installed app smoke evidence is invalid: " + "; ".join(installed_failures))
    runtime_failures = smoke_user_flows.validate_installed_app_runtime_workflow_evidence(runtime_input)
    if runtime_failures:
        raise ValueError("installed app runtime workflow evidence is invalid: " + "; ".join(runtime_failures))

    proof = sanitize(smoke_installed_app_runtime_workflow.extract_backend_runtime_proof(runtime_input))
    proof_failures = smoke_user_flows.validate_installed_app_backend_runtime_proof(proof)
    if proof_failures:
        raise ValueError("backend runtime proof is invalid: " + "; ".join(proof_failures))
    bundled_katago = bundled_katago_from_proof(proof)
    app_bundle = installed_smoke.get("appBundle")
    if not isinstance(app_bundle, dict):
        raise ValueError("installed app smoke must include appBundle")
    screenshots = screenshot_records(installed_smoke, runtime_input)
    runtime_source = runtime_source_from_proof(proof)
    asset_layout = bundled_asset_layout_from_proof(proof)
    launch_attempt = engine_launch_attempt_from_proof(proof)
    boundary = boundary_values()
    return {
        "schema": SCHEMA,
        "name": "bundled_katago_installed_app_smoke",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "installed_app_runtime_bundled_katago_layout_probe",
        "runtimeObserved": True,
        "installedAppLaunched": True,
        "backendCommandInvoked": True,
        "backendCommand": "installed_app_runtime_proof",
        "screenshotObserved": True,
        **boundary,
        "appBundle": sanitize(app_bundle),
        "runtimeSource": runtime_source,
        "backendRuntimeProof": proof,
        "bundledKataGo": bundled_katago,
        "bundledAssetLayout": asset_layout,
        "profileStatus": proof.get("profileStatus"),
        "engineLaunchAttempt": launch_attempt,
        "screenshots": screenshots,
        "sourceEvidence": {
            "installedAppSmoke": "docs/qa/installed-macos-app-smoke.json",
            "installedAppRuntimeWorkflow": "docs/qa/installed-app-runtime-workflow-macos.json",
            "backendProofSchema": smoke_user_flows.INSTALLED_APP_RUNTIME_PROOF_SCHEMA,
        },
        "boundaries": boundary,
        "checks": [
            pass_check("app_bundle_verified", {"appBundle": sanitize(app_bundle)}),
            pass_check("runtime_started", {"runtimeSource": runtime_source}),
            pass_check("backend_runtime_proof_observed", {"backendRuntimeProof": proof}),
            pass_check("bundled_asset_layout_validated", {"bundledAssetLayout": asset_layout}),
            pass_check("bundled_engine_launch_attempted", {"engineLaunchAttempt": launch_attempt}),
            pass_check("screenshot_recorded", {"screenshots": screenshots}),
            pass_check(
                "dev_server_excluded",
                {
                    "devServerExcluded": True,
                    "devServerAbsent": True,
                    "runnerStartedDevServer": False,
                    "runnerStartedViteDevServer": False,
                },
            ),
            pass_check("scope_boundaries_recorded", {"boundaries": boundary}),
        ],
    }


def validate_or_raise(evidence: dict[str, Any]) -> None:
    failures = smoke_user_flows.validate_bundled_katago_installed_app_smoke_evidence(evidence)
    if failures:
        raise ValueError("bundled KataGo installed-app smoke evidence is invalid: " + "; ".join(failures))


def path_arg(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or validate scoped bundled KataGo installed-app evidence.")
    parser.add_argument("--installed-app-smoke", default="docs/qa/installed-macos-app-smoke.json")
    parser.add_argument("--runtime-workflow", default="docs/qa/installed-app-runtime-workflow-macos.json")
    parser.add_argument("--evidence-out", default=DEFAULT_EVIDENCE_OUT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    output_path = path_arg(args.evidence_out)
    if args.validate_only:
        evidence = load_json(output_path)
        validate_or_raise(evidence)
        print(f"validated {output_path.relative_to(ROOT) if output_path.is_relative_to(ROOT) else output_path}")
        return 0

    installed_smoke = load_json(path_arg(args.installed_app_smoke))
    runtime_workflow = load_json(path_arg(args.runtime_workflow))
    evidence = build_evidence(installed_smoke, runtime_workflow)
    validate_or_raise(evidence)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {output_path.relative_to(ROOT) if output_path.is_relative_to(ROOT) else output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
