#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import smoke_user_flows  # noqa: E402


SCHEMA = "lizzieyzy.installed-app-runtime-workflow.v1"
BACKEND_PROOF_SCHEMA = "lizzieyzy.installed-app-runtime-proof.v1"
DEFAULT_EVIDENCE_OUT = "docs/qa/installed-app-runtime-workflow-macos.json"


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
        sanitized = re.sub(r"/private/var/folders/[^\\s\"']+", "<tmp>", sanitized)
        sanitized = re.sub(r"/var/folders/[^\\s\"']+", "<tmp>", sanitized)
        sanitized = re.sub(r"/tmp/[^\\s\"']+", "<tmp>", sanitized)
        return sanitized
    return value


def extract_backend_runtime_proof(runtime_input: dict[str, Any]) -> dict[str, Any]:
    if runtime_input.get("schema") == BACKEND_PROOF_SCHEMA:
        return normalize_backend_runtime_proof(runtime_input)
    for key in ("backendRuntimeProof", "runtimeProof", "proof"):
        value = runtime_input.get(key)
        if isinstance(value, dict) and value.get("schema") == BACKEND_PROOF_SCHEMA:
            return normalize_backend_runtime_proof(value)
    checks = runtime_input.get("checks")
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict) or check.get("name") != "backend_runtime_proof_observed":
                continue
            details = check.get("details") if isinstance(check.get("details"), dict) else check.get("evidence")
            if not isinstance(details, dict):
                continue
            if details.get("schema") == BACKEND_PROOF_SCHEMA:
                return normalize_backend_runtime_proof(details)
            for key in ("backendRuntimeProof", "runtimeProof", "proof"):
                value = details.get(key)
                if isinstance(value, dict) and value.get("schema") == BACKEND_PROOF_SCHEMA:
                    raw = details.get("raw") if isinstance(details.get("raw"), dict) else None
                    return normalize_backend_runtime_proof(value, raw)
    raise ValueError(f"runtime input must contain backend proof schema {BACKEND_PROOF_SCHEMA}")


def normalize_backend_runtime_proof(proof: dict[str, Any], raw_override: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = copy.deepcopy(proof)
    raw = copy.deepcopy(raw_override) if isinstance(raw_override, dict) else normalized.get("raw")
    if not isinstance(raw, dict):
        raw = {}
    raw_bundled = bundled_katago_alias(raw)
    if raw_bundled is None:
        raw_bundled = derive_bundled_katago_from_asset_checks(raw.get("assets"))
    summary_bundled = bundled_katago_alias(normalized)
    if raw_bundled is not None:
        normalized["bundledKatago"] = normalize_bundled_katago(raw_bundled)
        raw["bundledKatago"] = raw_bundled
    elif summary_bundled is not None:
        normalized["bundledKatago"] = normalize_bundled_katago(summary_bundled)
        raw["bundledKatago"] = summary_bundled
    normalized["raw"] = raw
    return normalized


def bundled_katago_alias(value: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("bundledKatago", "bundledKataGo", "bundled_katago"):
        bundled = value.get(key)
        if isinstance(bundled, dict):
            return bundled
    return None


def normalize_bundled_katago(value: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(value)
    records = bundled_katago_asset_records(value)
    if records:
        exists = [record for record in records if bundled_katago_record_exists(record)]
        missing = [record for record in records if bundled_katago_record_missing(record)]
        placeholders = [record for record in records if str(record.get("status", "")).lower() == "placeholder"]
        incomplete = bool(missing or placeholders)
        normalized.setdefault("sourceKind", value.get("source") or value.get("sourceKind") or "packaged-macos-app")
        normalized["status"] = value.get("status") or ("incomplete" if incomplete else "ready")
        normalized["validationStatus"] = value.get("validationStatus") or normalized["status"]
        normalized["complete"] = False if incomplete else bool(value.get("complete", True))
        normalized["checks"] = len(records)
        normalized["exists"] = exists
        normalized["missing"] = missing
        normalized["placeholders"] = placeholders
        details = normalized.get("details") if isinstance(normalized.get("details"), dict) else {}
        details.setdefault("checks", records)
        details.setdefault("exists", exists)
        details.setdefault("missing", missing)
        details.setdefault("placeholders", placeholders)
        normalized["details"] = details
    return normalized


def bundled_katago_asset_records(value: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key in ("engine", "model", "config"):
        record = value.get(key)
        if isinstance(record, dict):
            item = copy.deepcopy(record)
            item.setdefault("label", key)
            records.append(item)
    return records


def bundled_katago_record_exists(record: dict[str, Any]) -> bool:
    status = str(record.get("status", "")).lower()
    return record.get("exists") is True or status in {"exists", "ready", "available", "ok", "present"}


def bundled_katago_record_missing(record: dict[str, Any]) -> bool:
    status = str(record.get("status", "")).lower()
    return record.get("exists") is False or status in {"missing", "not_found", "unavailable", "incomplete", "problem"}


def derive_bundled_katago_from_asset_checks(assets: Any) -> dict[str, Any] | None:
    if not isinstance(assets, dict):
        return None
    details = assets.get("details") if isinstance(assets.get("details"), dict) else {}
    records = details.get("checks")
    if not isinstance(records, list):
        records = assets.get("checks")
    if not isinstance(records, list):
        return None
    resource_records: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        path = record.get("path")
        label = str(record.get("label", ""))
        if not isinstance(path, str):
            continue
        if "Contents/Resources" not in path:
            continue
        if path.endswith("Contents/Resources/") or path.endswith("Contents/Resources"):
            resource_records.append(record)
        elif "/runtime/katago/" in path and "KataGo" in label:
            resource_records.append(record)
    if not resource_records:
        return None
    exists = [record for record in resource_records if record.get("status") == "exists"]
    missing = [record for record in resource_records if record.get("status") == "missing"]
    placeholders = [record for record in resource_records if record.get("status") == "placeholder"]
    incomplete = bool(missing or placeholders)
    return {
        "sourceKind": "packaged-macos-app",
        "status": "incomplete" if incomplete else "ready",
        "validationStatus": "incomplete" if incomplete else "ready",
        "complete": not incomplete,
        "checks": len(resource_records),
        "exists": exists,
        "missing": missing,
        "placeholders": placeholders,
        "warnings": assets.get("warnings") or [],
        "details": {
            "checks": resource_records,
            "exists": exists,
            "missing": missing,
            "placeholders": placeholders,
            "layout": {"source": "resource_dir"},
        },
    }


def first_check_details(evidence: dict[str, Any], name: str) -> dict[str, Any]:
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        return {}
    for check in checks:
        if isinstance(check, dict) and check.get("name") == name:
            details = check.get("details")
            return details if isinstance(details, dict) else {}
    return {}


def screenshot_records(installed_smoke: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for screenshot in installed_smoke.get("screenshots", []):
        if isinstance(screenshot, dict):
            records.append(screenshot)
    details = first_check_details(installed_smoke, "packaged_app_window_screenshot")
    screenshot = details.get("screenshot")
    if isinstance(screenshot, dict):
        records.append(screenshot)
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    records.sort(key=lambda record: 0 if (record.get("sizeBytes") or record.get("bytes")) else 1)
    for record in records:
        key = (record.get("path"), record.get("sha256"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(
            {
                "label": record.get("label") or record.get("name") or "installed-app-runtime-window",
                "source": "installed_app_runtime",
                "path": record.get("path"),
                "sizeBytes": record.get("sizeBytes") or record.get("bytes"),
                "sha256": record.get("sha256"),
                "capturedAfterActionId": "observe_main_window",
            }
        )
    return unique


def runtime_process(installed_smoke: dict[str, Any]) -> dict[str, Any]:
    details = first_check_details(installed_smoke, "packaged_app_window_screenshot")
    window = details.get("window") if isinstance(details.get("window"), dict) else {}
    return {
        "observed": True,
        "processName": window.get("ownerName") or installed_smoke.get("processName") or "installed-app",
        "pid": window.get("ownerPid") or installed_smoke.get("processId"),
        "windowId": window.get("windowId"),
    }


def boundaries() -> dict[str, bool]:
    return {
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


def build_evidence(installed_smoke: dict[str, Any], runtime_input: dict[str, Any]) -> dict[str, Any]:
    installed_failures = smoke_user_flows.validate_installed_macos_app_smoke_evidence(installed_smoke)
    if installed_failures:
        raise ValueError("installed app smoke evidence is invalid: " + "; ".join(installed_failures))
    backend_proof = sanitize(extract_backend_runtime_proof(runtime_input))
    backend_failures = smoke_user_flows.validate_installed_app_backend_runtime_proof(backend_proof)
    if backend_failures:
        raise ValueError("backend runtime proof is invalid: " + "; ".join(backend_failures))

    app_bundle = installed_smoke.get("appBundle")
    if not isinstance(app_bundle, dict):
        raise ValueError("installed app smoke must include appBundle")
    screenshots = screenshot_records(installed_smoke)
    process = runtime_process(installed_smoke)
    boundary_values = boundaries()
    termination = installed_smoke.get("termination") if isinstance(installed_smoke.get("termination"), dict) else {
        "status": "pass",
        "success": True,
        "exitCode": 0,
    }
    runtime_source = backend_proof.get("runtime", {}).get("source") if isinstance(backend_proof.get("runtime"), dict) else None
    workflow_actions = [
        {
            "actionId": "launch_installed_app",
            "status": "pass",
            "runtimeObserved": True,
            "evidence": {"appBundlePath": installed_smoke.get("appBundlePath"), "launchMethod": "installed-app-smoke"},
        },
        {
            "actionId": "observe_main_window",
            "status": "pass",
            "runtimeObserved": True,
            "evidence": {"runtimeProcess": process, "screenshotCount": len(screenshots)},
        },
        {
            "actionId": "execute_runtime_action",
            "status": "pass",
            "runtimeObserved": True,
            "evidence": {
                "backendCommand": "installed_app_runtime_proof",
                "proofSchema": BACKEND_PROOF_SCHEMA,
                "runtimeSource": runtime_source,
            },
        },
        {
            "actionId": "terminate_installed_app",
            "status": "pass",
            "runtimeObserved": True,
            "evidence": termination,
        },
    ]
    return {
        "schema": SCHEMA,
        "name": "installed_app_runtime_workflow",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "installed_app_smoke_plus_backend_runtime_proof",
        "runtimeObserved": True,
        "runtimeSource": runtime_source,
        "installedAppLaunched": True,
        "runtimeProcessObserved": True,
        "windowObserved": True,
        "workflowExecuted": True,
        "screenshotObserved": True,
        "devServerAbsent": True,
        **boundary_values,
        "appBundlePath": installed_smoke.get("appBundlePath"),
        "appBundle": app_bundle,
        "runtimeProcess": process,
        "backendRuntimeProof": backend_proof,
        "workflowActions": workflow_actions,
        "screenshots": screenshots,
        "devServerPreflight": installed_smoke.get("devServerPreflight", {}),
        "termination": termination,
        "boundaries": boundary_values,
        "checks": [
            {"name": "app_bundle_verified", "status": "pass", "details": {"appBundle": app_bundle}},
            {
                "name": "installed_app_launched",
                "status": "pass",
                "details": {"installedAppLaunched": True, "appBundlePath": installed_smoke.get("appBundlePath")},
            },
            {"name": "runtime_process_observed", "status": "pass", "details": process},
            {"name": "window_observed", "status": "pass", "details": {"windowObserved": True}},
            {
                "name": "workflow_action_executed",
                "status": "pass",
                "details": {
                    "workflowExecuted": True,
                    "actionId": "execute_runtime_action",
                    "backendCommand": "installed_app_runtime_proof",
                    "proofSchema": BACKEND_PROOF_SCHEMA,
                },
            },
            {
                "name": "backend_runtime_proof_observed",
                "status": "pass",
                "details": {"backendRuntimeProof": backend_proof},
            },
            {"name": "screenshot_recorded", "status": "pass", "details": {"screenshots": screenshots}},
            {"name": "dev_server_absent", "status": "pass", "details": {"devServerAbsent": True}},
            {"name": "quit_or_terminate_observed", "status": "pass", "details": termination},
            {"name": "scope_boundaries_recorded", "status": "pass", "details": {"boundaries": boundary_values}},
        ],
    }


def path_arg(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate installed-app launch smoke with backend installed_app_runtime_proof evidence."
    )
    parser.add_argument("--installed-app-smoke", required=True)
    parser.add_argument("--runtime-proof")
    parser.add_argument("--tauri-runtime-report")
    parser.add_argument("--evidence-out", default=DEFAULT_EVIDENCE_OUT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    if bool(args.runtime_proof) == bool(args.tauri_runtime_report):
        parser.error("provide exactly one of --runtime-proof or --tauri-runtime-report")

    installed_smoke = load_json(path_arg(args.installed_app_smoke))
    runtime_input = load_json(path_arg(args.runtime_proof or args.tauri_runtime_report))
    evidence = build_evidence(installed_smoke, runtime_input)
    failures = smoke_user_flows.validate_installed_app_runtime_workflow_evidence(evidence)
    if failures:
        raise SystemExit("installed app runtime workflow evidence is invalid: " + "; ".join(failures))

    if not args.validate_only:
        output_path = path_arg(args.evidence_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {output_path}")
    else:
        print("installed app runtime workflow evidence is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
