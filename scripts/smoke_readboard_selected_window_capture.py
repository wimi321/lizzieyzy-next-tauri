#!/usr/bin/env python3
"""Validate scoped Readboard selected-window capture evidence.

This script is intentionally standalone and does not fabricate PASS evidence.
Use it only with runtime-backed evidence that proves a selected window id was
captured, decoded, previewed, confirmed, imported, and that failed decodes did
not replace the board.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SMOKE_USER_FLOWS = ROOT / "scripts" / "smoke_user_flows.py"
SPEC = importlib.util.spec_from_file_location("smoke_user_flows", SMOKE_USER_FLOWS)
assert SPEC is not None and SPEC.loader is not None
smoke_user_flows = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_user_flows"] = smoke_user_flows
SPEC.loader.exec_module(smoke_user_flows)

DEFAULT_EVIDENCE = ROOT / "docs/qa/readboard-selected-window-capture-macos.json"
SCHEMA = "lizzieyzy.readboard-selected-window-capture.v1"
BACKEND_COMMAND = "readboard_external_capture"
RUNTIME_PHASE = "readboard-selected-window-capture"
RUNTIME_KEY = "readboardSelectedWindowCapture"
REQUIRED_FALSE_FIELDS = [
    "automaticBoardReplacement",
    "releaseParity",
    "fullReleaseParity",
    "releaseReady",
    "officialRelease",
    "realClientParity",
    "fullOcrParity",
    "fullReadboardParity",
    "targetClientDiscoveryParity",
    "foxYikeParity",
    "windowsLinuxCaptureCovered",
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def normalize_source(value: Any) -> str:
    if isinstance(value, dict):
        value = first_present(value, "sourceKind", "kind", "captureSource", "source")
    source = str(value or "").strip()
    if source in {"selected_window", "selected_window_capture", "operator_selected_window"}:
        return "selected_window"
    return source


def validate_window_metadata(value: Any, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    failures: list[str] = []
    for key in ("windowId", "title", "appName", "processName"):
        if not isinstance(value.get(key), str) or not value.get(key, "").strip():
            failures.append(f"{label}.{key} must be non-empty")
    if value.get("windowIdSanitized") is not True:
        failures.append(f"{label}.windowIdSanitized must be true")
    if not isinstance(value.get("bounds"), dict):
        failures.append(f"{label}.bounds must be an object")
    return failures


def validate_capture_artifact(value: Any, root: Path, selected_window_id: Any, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    failures: list[str] = []
    if value.get("windowId") != selected_window_id:
        failures.append(f"{label}.windowId must match selectedWindow.windowId")
    if value.get("captureTiedToSelectedWindow") is not True:
        failures.append(f"{label}.captureTiedToSelectedWindow must be true")
    if value.get("sanitized") is not True:
        failures.append(f"{label}.sanitized must be true")
    path_value = value.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        failures.append(f"{label}.path must be non-empty")
    else:
        failures.extend(smoke_user_flows.validate_repo_relative_path_artifact(root, path_value, value, label))
    return failures


def validate_raw_backend(value: Any, selected_window_id: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["rawBackendResult must be an object"]
    failures: list[str] = []
    if value.get("status") != "captured":
        failures.append("rawBackendResult.status must be captured")
    if normalize_source(first_present(value, "source", "captureSource")) != "selected_window":
        failures.append("rawBackendResult.source/captureSource must be selected_window")
    if value.get("windowId") != selected_window_id:
        failures.append("rawBackendResult.windowId must match selectedWindow.windowId")
    if value.get("captureTiedToSelectedWindow") is not True:
        failures.append("rawBackendResult.captureTiedToSelectedWindow must be true")
    if first_present(value, "boardReplacement", "board_replacement") not in (None, "none"):
        failures.append("rawBackendResult.boardReplacement must be absent or none before confirmation")
    if not is_sha256(first_present(value, "snapshotHash", "snapshot_hash", "hash")):
        failures.append("rawBackendResult.snapshotHash/hash must be a 64-character hex sha256")
    if not isinstance(value.get("position"), dict):
        failures.append("rawBackendResult.position must be an object")
    return failures


def validate_decode(value: Any, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    failures: list[str] = []
    if not isinstance(value.get("snapshotId"), str) or not value.get("snapshotId"):
        failures.append(f"{label}.snapshotId must be non-empty")
    if not is_sha256(value.get("snapshotHash")):
        failures.append(f"{label}.snapshotHash must be a 64-character hex sha256")
    if value.get("decodeSucceeded") is not True:
        failures.append(f"{label}.decodeSucceeded must be true")
    if value.get("boardSize") not in {9, 13, 19}:
        failures.append(f"{label}.boardSize must be 9, 13, or 19")
    if not isinstance(value.get("stoneCount"), (int, float)) or value.get("stoneCount") < 0:
        failures.append(f"{label}.stoneCount must be non-negative")
    return failures


def validate_preview(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["previewConfirmation must be an object"]
    failures: list[str] = []
    if value.get("previewOnlyBeforeConfirmation") is not True:
        failures.append("previewConfirmation.previewOnlyBeforeConfirmation must be true")
    if value.get("boardReplacedBeforeConfirmation") is not False:
        failures.append("previewConfirmation.boardReplacedBeforeConfirmation must be false")
    if value.get("userConfirmed") is not True:
        failures.append("previewConfirmation.userConfirmed must be true")
    if value.get("boardReplacedOnlyAfterConfirmation") is not True:
        failures.append("previewConfirmation.boardReplacedOnlyAfterConfirmation must be true")
    return failures


def validate_failed_decode(value: Any, root: Path) -> list[str]:
    if not isinstance(value, dict):
        return ["failedDecodeNoReplacement must be an object"]
    failures: list[str] = []
    path_value = value.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        failures.append("failedDecodeNoReplacement.path must be non-empty")
    else:
        failures.extend(smoke_user_flows.validate_repo_relative_path_artifact(root, path_value, value, "failedDecodeNoReplacement"))
    if value.get("decodeAttempted") is not True:
        failures.append("failedDecodeNoReplacement.decodeAttempted must be true")
    if value.get("decodeSucceeded") is not False:
        failures.append("failedDecodeNoReplacement.decodeSucceeded must be false")
    if value.get("imported") is not False:
        failures.append("failedDecodeNoReplacement.imported must be false")
    if value.get("boardReplaced") is not False:
        failures.append("failedDecodeNoReplacement.boardReplaced must be false")
    return failures


def validate_selected_window_capture_evidence(evidence: Any, root: Path = ROOT) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    failures.extend(smoke_user_flows.validate_no_readboard_target_window_local_paths(evidence))
    if evidence.get("schema") != SCHEMA:
        failures.append(f"schema must be {SCHEMA}")
    if evidence.get("name") != "readboard_selected_window_capture":
        failures.append("name must be readboard_selected_window_capture")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    if str(evidence.get("platform", "")).lower() not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    if evidence.get("collectionMethod") != "runtime_backend_selected_window_capture":
        failures.append("collectionMethod must be runtime_backend_selected_window_capture")
    if evidence.get("sourceStaticOnly") is not False:
        failures.append("sourceStaticOnly must be false")
    for key in ("runtimeObserved", "backendCommandInvoked", "selectedWindowCaptureVerified"):
        if evidence.get(key) is not True:
            failures.append(f"{key} must be true")
    if evidence.get("backendCommand") != BACKEND_COMMAND:
        failures.append(f"backendCommand must be {BACKEND_COMMAND}")
    if evidence.get("runtimeReportPhase") != RUNTIME_PHASE:
        failures.append(f"runtimeReportPhase must be {RUNTIME_PHASE}")
    if evidence.get("runtimeReportKey") != RUNTIME_KEY:
        failures.append(f"runtimeReportKey must be {RUNTIME_KEY}")
    source_report = evidence.get("sourceRuntimeReport")
    if not isinstance(source_report, dict):
        failures.append("sourceRuntimeReport must be an object")
    else:
        if source_report.get("phase") != RUNTIME_PHASE:
            failures.append(f"sourceRuntimeReport.phase must be {RUNTIME_PHASE}")
        if source_report.get("reportKey") != RUNTIME_KEY:
            failures.append(f"sourceRuntimeReport.reportKey must be {RUNTIME_KEY}")
        if source_report.get("runtimeObserved") is not True:
            failures.append("sourceRuntimeReport.runtimeObserved must be true")
        if source_report.get("backendCommandInvoked") is not True:
            failures.append("sourceRuntimeReport.backendCommandInvoked must be true")
        if source_report.get("backendCommand") != BACKEND_COMMAND:
            failures.append(f"sourceRuntimeReport.backendCommand must be {BACKEND_COMMAND}")
    for key in REQUIRED_FALSE_FIELDS:
        if evidence.get(key) is not False:
            failures.append(f"{key} must be false")
    selected = evidence.get("selectedWindow")
    failures.extend(validate_window_metadata(selected, "selectedWindow"))
    selected_window_id = selected.get("windowId") if isinstance(selected, dict) else None
    failures.extend(validate_raw_backend(evidence.get("rawBackendResult"), selected_window_id))
    failures.extend(validate_capture_artifact(evidence.get("captureArtifact"), root, selected_window_id, "captureArtifact"))
    failures.extend(validate_decode(evidence.get("decodeSnapshot"), "decodeSnapshot"))
    failures.extend(validate_preview(evidence.get("previewConfirmation")))
    failures.extend(validate_failed_decode(evidence.get("failedDecodeNoReplacement"), root))
    return failures


def validate_evidence(path: Path, *, verbose: bool = False) -> int:
    if not path.is_file():
        print(f"FAIL: evidence not found: {path}", file=sys.stderr)
        return 1
    try:
        evidence = load_json(path)
    except json.JSONDecodeError as exc:
        print(f"FAIL: invalid JSON: {exc}", file=sys.stderr)
        return 1
    failures = validate_selected_window_capture_evidence(evidence, ROOT)
    if failures:
        print("FAIL: readboard selected-window capture evidence is invalid", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    if verbose:
        print(f"PASS: validated scoped selected-window capture evidence at {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    evidence_path = args.evidence_out
    if not evidence_path.is_absolute():
        evidence_path = ROOT / evidence_path
    return validate_evidence(evidence_path, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
