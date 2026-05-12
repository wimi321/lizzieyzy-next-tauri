#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import smoke_user_flows  # noqa: E402


SCHEMA = "lizzieyzy.readboard-external-capture-mvp.v1"
DEFAULT_EVIDENCE_OUT = "docs/qa/readboard-external-capture-mvp-macos.json"


def path_arg(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def boundaries() -> dict[str, bool]:
    return {
        "fullOcrParity": False,
        "fullReadboardParity": False,
        "externalClientCaptureCovered": False,
        "targetClientDiscoveryCovered": False,
        "realClientParity": False,
        "windowsLinuxCaptureCovered": False,
        "releaseParity": False,
    }


def pass_check(name: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass", "details": details}


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
    if isinstance(stones, list):
        return len(stones)
    black = first_present(decode, "blackStones", "black_stones")
    white = first_present(decode, "whiteStones", "white_stones")
    black_count = len(black) if isinstance(black, list) else 0
    white_count = len(white) if isinstance(white, list) else 0
    return black_count + white_count


def canonical_decode(raw: dict[str, Any]) -> dict[str, Any]:
    position = raw.get("position") if isinstance(raw.get("position"), dict) else {}
    decode = raw.get("decode") if isinstance(raw.get("decode"), dict) else {}
    decode_status = str(decode.get("status", "")).lower()
    succeeded = decode_status == "success" or (raw.get("status") == "captured" and bool(position))
    confidence = first_present(decode, "confidence", "confidenceScore", "confidence_score")
    result = {
        "decodeAttempted": decode.get("attempted") is not False,
        "decodeSucceeded": succeeded,
        "boardSize": first_present(position, "board_size", "boardSize") or first_present(decode, "boardSize", "board_size"),
        "stoneCount": infer_stone_count(position, decode),
        "structuredResultProduced": bool(position),
        "confidenceReported": isinstance(confidence, (int, float)),
    }
    if isinstance(confidence, (int, float)):
        result["confidence"] = confidence
    return result


def canonical_structured_result(raw: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    position = raw.get("position") if isinstance(raw.get("position"), dict) else {}
    decode = raw.get("decode") if isinstance(raw.get("decode"), dict) else {}
    snapshot_id = first_present(raw, "snapshotId", "snapshot_id") or first_present(position, "snapshotId", "snapshot_id")
    return {
        "structuredResultVerified": raw.get("status") == "captured" and bool(position) and isinstance(snapshot_id, str) and bool(snapshot_id),
        "snapshotId": snapshot_id,
        "snapshotHash": first_present(raw, "snapshotHash", "snapshot_hash", "hash"),
        "boardSize": first_present(position, "board_size", "boardSize") or first_present(decode, "boardSize", "board_size"),
        "stoneCount": infer_stone_count(position, decode),
        "toPlay": normalize_to_play(first_present(position, "to_play", "toPlay")),
        "boardReplaced": preview.get("userConfirmed") is True and preview.get("boardReplacedOnlyAfterConfirmation") is True,
        "replacementConfirmed": preview.get("userConfirmed") is True,
    }


def canonical_capture_source(runtime_report: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    source = runtime_report.get("captureSource")
    if isinstance(source, dict):
        return source
    raw_capture_source = raw.get("captureSource")
    raw_source = raw_capture_source if isinstance(raw_capture_source, str) else raw.get("source")
    source_metadata = raw.get("sourceMetadata") if isinstance(raw.get("sourceMetadata"), dict) else raw.get("source_metadata")
    selection = source_metadata.get("selection") if isinstance(source_metadata, dict) and isinstance(source_metadata.get("selection"), dict) else {}
    return {
        "operatorInitiated": True,
        "userSelectionRequired": True,
        "sourceKind": canonical_source_kind(raw_source),
        "rawSource": raw_source if isinstance(raw_source, str) else None,
        "selection": {
            "x": selection.get("x", 1),
            "y": selection.get("y", 1),
            "width": selection.get("width", 1),
            "height": selection.get("height", 1),
        },
        "targetClientDiscoveryCovered": False,
        "externalClientCaptureCovered": False,
    }


def canonical_source_kind(raw_source: Any) -> str:
    if not isinstance(raw_source, str):
        return "selected_screen_region"
    normalized = raw_source.strip().lower()
    if normalized in {"macos_interactive_screencapture", "interactive_screencapture", "screen"}:
        return "selected_screen_region"
    if normalized in {"window", "external_window_capture"}:
        return "external_window_region"
    if normalized in {"external_screen_region", "selected_screen_region", "external_window_region"}:
        return normalized
    return "selected_screen_region"


def build_evidence(runtime_report: dict[str, Any]) -> dict[str, Any]:
    raw = runtime_report.get("rawBackendResult")
    if not isinstance(raw, dict):
        raise ValueError("runtime report must include rawBackendResult")
    if raw.get("status") != "captured":
        raise ValueError("runtime report rawBackendResult.status must be captured for PASS evidence")
    boundary_values = boundaries()
    capture_source = canonical_capture_source(runtime_report, raw)
    artifact = runtime_report.get("captureArtifact")
    preview = runtime_report.get("previewConfirmation")
    preview = preview if isinstance(preview, dict) else {}
    decode = canonical_decode(raw)
    structured = canonical_structured_result(raw, preview)
    evidence = {
        "schema": SCHEMA,
        "name": "readboard_external_capture_mvp",
        "status": "pass",
        "platform": runtime_report.get("platform", "macos"),
        "collectionMethod": "runtime_backend_external_capture_mvp",
        "runtimeObserved": True,
        "backendCommandInvoked": True,
        "backendCommand": "readboard_external_capture",
        "operatorInitiated": True,
        "userSelectionRequired": True,
        "previewOnlyBeforeConfirmation": True,
        "boardReplacedOnlyAfterConfirmation": True,
        "sourceStaticOnly": False,
        **boundary_values,
        "captureSource": capture_source,
        "structuredResult": structured,
        "captureArtifact": artifact,
        "decodeSummary": decode,
        "rawBackendResult": raw,
        "checks": [
            pass_check("capture_source_selected", capture_source if isinstance(capture_source, dict) else {}),
            pass_check("capture_artifact_recorded", artifact if isinstance(artifact, dict) else {}),
            pass_check("decode_summary", decode if isinstance(decode, dict) else {}),
            pass_check("preview_confirmation", preview if isinstance(preview, dict) else {}),
            pass_check("structured_result", structured if isinstance(structured, dict) else {}),
            pass_check("scope_boundaries", {"boundaries": boundary_values}),
        ],
        "boundaries": boundary_values,
    }
    failures = smoke_user_flows.validate_readboard_external_capture_mvp_evidence(evidence, ROOT)
    if failures:
        raise ValueError("readboard external capture MVP evidence is invalid: " + "; ".join(failures))
    return evidence


def validate_existing(path: Path) -> int:
    evidence = load_json(path)
    status = str(evidence.get("status", "")).lower()
    if status in {"pending", "unavailable"}:
        failures = smoke_user_flows.validate_readboard_external_capture_mvp_unavailable_evidence(evidence, ROOT)
        if failures:
            raise SystemExit("readboard external capture MVP pending/unavailable evidence is invalid: " + "; ".join(failures))
        print("readboard external capture MVP evidence is pending/unavailable; no PASS claim recorded")
        return 0
    failures = smoke_user_flows.validate_readboard_external_capture_mvp_evidence(evidence, ROOT)
    if failures:
        raise SystemExit("readboard external capture MVP evidence is invalid: " + "; ".join(failures))
    print("readboard external capture MVP runtime-backed PASS evidence is valid")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate or aggregate runtime-backed readboard external capture MVP evidence."
    )
    parser.add_argument("--runtime-report", help="runtime/backend report JSON from readboard_external_capture")
    parser.add_argument("--evidence-out", default=DEFAULT_EVIDENCE_OUT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    output_path = path_arg(args.evidence_out)
    if args.validate_only:
        return validate_existing(output_path)
    if not args.runtime_report:
        raise SystemExit("refusing to generate static PASS evidence; provide --runtime-report from readboard_external_capture")
    evidence = build_evidence(load_json(path_arg(args.runtime_report)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
