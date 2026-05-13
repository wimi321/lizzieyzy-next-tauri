#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
USER_FLOWS_SCRIPT = ROOT / "scripts" / "smoke_user_flows.py"
SPEC = importlib.util.spec_from_file_location("smoke_user_flows", USER_FLOWS_SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke_user_flows = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_user_flows"] = smoke_user_flows
SPEC.loader.exec_module(smoke_user_flows)

DEFAULT_EVIDENCE_OUT = ROOT / smoke_user_flows.READBOARD_TARGET_WINDOW_SCREENSHOT_SMOKE_EVIDENCE
FIXTURE_DIR = ROOT / "tests/fixtures/readboard-screenshots"
TAURI_RUNTIME_SCHEMA = "lizzieyzy.tauri-runtime-ui-smoke.v1"
PHASE = smoke_user_flows.READBOARD_TARGET_WINDOW_SCREENSHOT_RUNTIME_PHASE
REPORT_KEY = smoke_user_flows.READBOARD_TARGET_WINDOW_SCREENSHOT_RUNTIME_KEY
MIN_DECODABLE_SIDE = 95
FIXTURE_VARIANTS = [
    ("controlled_board", "target-window-scale.ppm", "decode_success"),
    ("non_board", "target-window-non-board.ppm", "decode_error"),
]


class SmokeError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SmokeError(f"JSON file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeError(f"JSON file is invalid at line {exc.lineno}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise SmokeError(f"{path} must contain a JSON object")
    return value


def repo_rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def ppm_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    tokens: list[bytes] = []
    index = 0
    while index < len(data) and len(tokens) < 3:
        while index < len(data) and data[index] in b" \t\r\n":
            index += 1
        if index < len(data) and data[index:index + 1] == b"#":
            while index < len(data) and data[index] not in b"\r\n":
                index += 1
            continue
        start = index
        while index < len(data) and data[index] not in b" \t\r\n":
            index += 1
        if start != index:
            tokens.append(data[start:index])
    if len(tokens) < 3 or tokens[0] not in {b"P3", b"P6"}:
        return None
    try:
        return int(tokens[1]), int(tokens[2])
    except ValueError:
        return None


def artifact_record(path: Path, *, kind: str, expected_outcome: str) -> dict[str, Any]:
    data = path.read_bytes()
    dimensions = ppm_dimensions(path)
    record: dict[str, Any] = {
        "kind": kind,
        "path": repo_rel(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "sizeBytes": len(data),
        "sanitized": True,
        "expectedOutcome": expected_outcome,
    }
    if dimensions is not None:
        record.update({"width": dimensions[0], "height": dimensions[1]})
    if expected_outcome == "decode_error":
        record.update({"errorKind": "ImageLowConfidence", "boardReplaced": False, "imported": False})
    else:
        if dimensions is None:
            raise SmokeError(f"{repo_rel(path)} valid fixture must be a PPM with readable dimensions")
        width, height = dimensions
        if min(width, height) < MIN_DECODABLE_SIDE:
            raise SmokeError(
                f"{repo_rel(path)} valid fixture side must be at least {MIN_DECODABLE_SIDE}px, got {width}x{height}"
            )
        record.update({"boardSize": 19, "stoneCount": 3})
    return record


def fixture_manifest() -> list[dict[str, Any]]:
    return [
        artifact_record(FIXTURE_DIR / filename, kind=kind, expected_outcome=expected_outcome)
        for kind, filename, expected_outcome in FIXTURE_VARIANTS
    ]


def first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def normalize_to_play(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"b", "black"}:
        return "black"
    if text in {"w", "white"}:
        return "white"
    return text


def infer_stone_count(position: dict[str, Any], decode: dict[str, Any]) -> int:
    explicit = first_present(decode, "stoneCount", "stone_count")
    if isinstance(explicit, (int, float)):
        return int(explicit)
    stones = position.get("stones")
    return len(stones) if isinstance(stones, list) else 0


def validate_raw_tauri_report(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    schema = report.get("schema")
    if schema is not None and schema != TAURI_RUNTIME_SCHEMA:
        failures.append(f"runtime report schema must be {TAURI_RUNTIME_SCHEMA}")
    if report.get("phase") != PHASE:
        failures.append(f"runtime report phase must be {PHASE}")
    capture = report.get(REPORT_KEY)
    if not isinstance(capture, dict):
        failures.append(f"runtime report must include {REPORT_KEY} object")
    return failures


def extract_capture_report(runtime_report: dict[str, Any]) -> dict[str, Any]:
    failures = validate_raw_tauri_report(runtime_report)
    if failures:
        raise SmokeError("; ".join(failures))
    capture = runtime_report[REPORT_KEY]
    assert isinstance(capture, dict)
    raw = capture.get("rawBackendResult")
    if not isinstance(raw, dict):
        raise SmokeError(f"{REPORT_KEY}.rawBackendResult must be present")
    if raw.get("status") != "captured":
        raise SmokeError("rawBackendResult.status must be captured before PASS evidence can be generated")
    raw_source = smoke_user_flows.normalize_readboard_target_window_source(first_present(raw, "captureSource", "source"))
    if raw_source != "controlled_local_target_window":
        raise SmokeError("rawBackendResult.source/captureSource must be controlled_local_target_window")
    return capture


def target_metadata(report: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    metadata = report.get("targetWindowMetadata")
    if not isinstance(metadata, dict):
        metadata = first_present(raw, "sourceMetadata", "source_metadata")
    if not isinstance(metadata, dict):
        raise SmokeError("runtime report must include targetWindowMetadata or rawBackendResult.sourceMetadata")
    return dict(metadata)


def screenshot_artifacts(report: dict[str, Any]) -> list[dict[str, Any]]:
    capture_artifact = first_present(report, "captureArtifact", "rawCaptureArtifact")
    if not isinstance(capture_artifact, dict):
        raise SmokeError(f"{REPORT_KEY}.captureArtifact must be present")
    failed = report.get("failedDecodeNoReplacement")
    failed_artifact = failed.get("artifact") if isinstance(failed, dict) else None
    if not isinstance(failed_artifact, dict):
        raise SmokeError(f"{REPORT_KEY}.failedDecodeNoReplacement.artifact must be present")
    return [
        {**dict(capture_artifact), "kind": "valid_board"},
        {**dict(failed_artifact), "kind": "non_board"},
    ]


def build_decode_result(report: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    existing = report.get("decodeResult")
    if isinstance(existing, dict):
        return dict(existing)
    position = raw.get("position") if isinstance(raw.get("position"), dict) else {}
    decode = raw.get("decode") if isinstance(raw.get("decode"), dict) else {}
    snapshot_id = first_present(raw, "snapshotId", "snapshot_id") or "target-window-screenshot-001"
    snapshot_hash = first_present(raw, "snapshotHash", "snapshot_hash", "hash")
    return {
        "decodeAttempted": decode.get("attempted") is not False,
        "decodeSucceeded": str(decode.get("status", "")).lower() == "success" or bool(position),
        "structuredResultProduced": bool(position),
        "snapshotId": snapshot_id,
        "snapshotHash": snapshot_hash,
        "boardSize": first_present(position, "board_size", "boardSize") or first_present(decode, "boardSize", "board_size"),
        "stoneCount": infer_stone_count(position, decode),
        "toPlay": normalize_to_play(first_present(position, "to_play", "toPlay")),
        "previewProduced": preview_was_produced(report.get("previewConfirmation")),
        "importedAfterConfirmation": report.get("previewConfirmation", {}).get("boardReplacedOnlyAfterConfirmation") is True,
    }


def preview_was_produced(preview: Any) -> bool:
    if not isinstance(preview, dict):
        return False
    if preview.get("previewProduced") is True:
        return True
    if preview.get("previewOnlyBeforeConfirmation") is True:
        return True
    before = preview.get("beforeConfirmation")
    if isinstance(before, dict) and before.get("previewVisible") is True:
        return True
    after = preview.get("afterConfirmation")
    if isinstance(after, dict) and after.get("previewVisible") is True:
        return True
    return False


def preview_confirmation(report: dict[str, Any]) -> dict[str, Any]:
    preview = report.get("previewConfirmation")
    if isinstance(preview, dict):
        return dict(preview)
    raise SmokeError(f"{REPORT_KEY}.previewConfirmation must be present")


def failed_decode_no_replacement(report: dict[str, Any]) -> dict[str, Any]:
    failed = report.get("failedDecodeNoReplacement")
    if isinstance(failed, dict):
        return dict(failed)
    raise SmokeError(f"{REPORT_KEY}.failedDecodeNoReplacement must be present")


def build_evidence_from_runtime_report(runtime_report: dict[str, Any]) -> dict[str, Any]:
    capture = extract_capture_report(runtime_report)
    raw = capture["rawBackendResult"]
    assert isinstance(raw, dict)
    metadata = target_metadata(capture, raw)
    manifest = fixture_manifest()
    decode_result = build_decode_result(capture, raw)
    preview = preview_confirmation(capture)
    failed_decode = failed_decode_no_replacement(capture)
    artifacts = screenshot_artifacts(capture)
    false_boundaries = {
        key: False
        for key in smoke_user_flows.READBOARD_TARGET_WINDOW_SCREENSHOT_REQUIRED_FALSE_FIELDS
    }
    capture_source = {
        "sourceKind": "controlled_local_target_window",
        "controlledLocalTargetWindow": True,
        "operatorInitiated": False,
        "userSelectionRequired": False,
        "selection": None,
        "targetClientDiscoveryCovered": False,
        "rawSource": first_present(raw, "captureSource", "source"),
    }
    evidence = {
        "schema": smoke_user_flows.READBOARD_TARGET_WINDOW_SCREENSHOT_SMOKE_SCHEMA,
        "name": "readboard_target_window_screenshot_smoke",
        "status": "pass",
        "platform": runtime_report.get("platform", "macos"),
        "collectionMethod": "controlled_local_target_window_screenshot_fixture",
        "runtimeReportPhase": runtime_report.get("phase"),
        "runtimeReportKey": REPORT_KEY,
        "runtimeObserved": True,
        "backendCommandInvoked": True,
        "backendCommand": "readboard_external_capture",
        "controlledLocalTargetWindow": True,
        "previewOnlyBeforeConfirmation": preview.get("previewOnlyBeforeConfirmation") is True,
        "boardReplacedOnlyAfterConfirmation": preview.get("boardReplacedOnlyAfterConfirmation") is True,
        "nonBoardFailedDecodeNoReplacement": failed_decode.get("boardReplaced") is False and failed_decode.get("imported") is False,
        **false_boundaries,
        "captureSource": capture_source,
        "targetWindowMetadata": metadata,
        "screenshotArtifacts": artifacts,
        "decodeResult": decode_result,
        "previewConfirmation": preview,
        "failedDecodeNoReplacement": failed_decode,
        "fixtureManifest": manifest,
        "rawBackendResult": raw,
        "sourceRuntimeReport": {
            "schema": runtime_report.get("schema", TAURI_RUNTIME_SCHEMA),
            "phase": runtime_report.get("phase"),
            "reportKey": REPORT_KEY,
            "runtimeObserved": runtime_report.get("runtimeObserved", True),
        },
        "checks": [
            {
                "name": "controlled_local_target_window",
                "status": "pass",
                "details": {
                    "controlledLocalTargetWindow": True,
                    "runtimeObserved": True,
                    "backendCommandInvoked": True,
                    "sourceStaticOnly": False,
                    "realClientObserved": False,
                },
            },
            {"name": "target_window_metadata", "status": "pass", "details": metadata},
            {"name": "screenshot_artifacts", "status": "pass", "details": {"artifacts": artifacts}},
            {"name": "decode_result", "status": "pass", "details": decode_result},
            {"name": "preview_confirmation", "status": "pass", "details": preview},
            {"name": "failed_decode_no_replacement", "status": "pass", "details": failed_decode},
            {"name": "fixture_manifest", "status": "pass", "details": {"fixtures": manifest}},
            {"name": "scope_boundaries", "status": "pass", "details": {"boundaries": false_boundaries}},
        ],
        "boundaries": false_boundaries,
        "scope": {
            "realClientObserved": False,
            "targetClientDiscoveryCovered": False,
            "note": "Controlled local target-window screenshot runtime report only; not real external client discovery or full OCR/readboard parity.",
        },
    }
    failures = smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT)
    if failures:
        raise SmokeError("generated readboard target-window screenshot evidence is invalid: " + "; ".join(failures))
    return evidence


def validate_evidence_file(path: Path) -> int:
    evidence = load_json(path)
    failures = smoke_user_flows.validate_readboard_target_window_screenshot_smoke_evidence(evidence, ROOT)
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or aggregate scoped readboard controlled target-window screenshot evidence.")
    parser.add_argument("--evidence-out", type=Path, default=DEFAULT_EVIDENCE_OUT)
    parser.add_argument("--runtime-report", type=Path, help="raw Tauri runtime report to aggregate into PASS evidence")
    parser.add_argument("--check-only", action="store_true", help="validate the evidence path without rewriting it")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    if args.runtime_report is None:
        status = validate_evidence_file(args.evidence_out)
        if status == 0 and args.verbose:
            print(f"PASS readboard_target_window_screenshot_smoke: validated {args.evidence_out.relative_to(ROOT)}")
        return status

    runtime_report = load_json(args.runtime_report)
    evidence = build_evidence_from_runtime_report(runtime_report)
    args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
    args.evidence_out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.verbose:
        display_path = args.evidence_out
        if display_path.is_absolute():
            try:
                display_path = display_path.relative_to(ROOT)
            except ValueError:
                pass
        print(f"PASS readboard_target_window_screenshot_smoke: wrote {display_path} from runtime report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
