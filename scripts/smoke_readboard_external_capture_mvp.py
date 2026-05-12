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
    replacement_confirmed = preview.get("userConfirmed") is True
    return {
        "structuredResultVerified": raw.get("status") == "captured" and bool(position) and isinstance(snapshot_id, str) and bool(snapshot_id),
        "snapshotId": snapshot_id,
        "snapshotHash": first_present(raw, "snapshotHash", "snapshot_hash", "hash"),
        "boardSize": first_present(position, "board_size", "boardSize") or first_present(decode, "boardSize", "board_size"),
        "stoneCount": infer_stone_count(position, decode),
        "toPlay": normalize_to_play(first_present(position, "to_play", "toPlay")),
        "boardReplaced": replacement_confirmed and preview.get("boardReplacedOnlyAfterConfirmation") is True,
        "replacementConfirmed": replacement_confirmed,
    }


def canonical_capture_source(runtime_report: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    source = runtime_report.get("captureSource")
    if isinstance(source, dict):
        return source
    raw_capture_source = raw.get("captureSource")
    raw_source = raw_capture_source if isinstance(raw_capture_source, str) else raw.get("source")
    source_kind = canonical_source_kind(raw_source)
    source_metadata = raw.get("sourceMetadata") if isinstance(raw.get("sourceMetadata"), dict) else raw.get("source_metadata")
    selection = source_metadata.get("selection") if isinstance(source_metadata, dict) and isinstance(source_metadata.get("selection"), dict) else {}
    evidence = {
        "operatorInitiated": raw.get("operatorInitiated") is True if source_kind == "local_image" else True,
        "userSelectionRequired": raw.get("userSelectionRequired") is True if source_kind == "local_image" else True,
        "sourceKind": source_kind,
        "rawSource": raw_source if isinstance(raw_source, str) else None,
        "targetClientDiscoveryCovered": False,
        "externalClientCaptureCovered": False,
    }
    if source_kind == "local_image":
        evidence["localImageOnly"] = True
        evidence["sanitizedPath"] = first_present(raw, "sanitizedPath", "path")
    else:
        evidence["selection"] = {
            "x": selection.get("x", 1),
            "y": selection.get("y", 1),
            "width": selection.get("width", 1),
            "height": selection.get("height", 1),
        }
    return evidence


def canonical_source_kind(raw_source: Any) -> str:
    if not isinstance(raw_source, str):
        return "selected_screen_region"
    normalized = raw_source.strip().lower()
    if normalized in {"local_image", "local-image", "image_path", "image-path", "controlled_image"}:
        return "local_image"
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
    source_kind = capture_source.get("sourceKind") if isinstance(capture_source, dict) else None
    artifact = runtime_report.get("captureArtifact")
    preview = runtime_report.get("previewConfirmation")
    preview = preview if isinstance(preview, dict) else {}
    if source_kind == "local_image":
        preview = {
            "previewOnlyBeforeConfirmation": False,
            "boardReplacedBeforeConfirmation": False,
            "userConfirmed": False,
            "boardReplacedOnlyAfterConfirmation": False,
            "localImageDecodeOnly": True,
        }
    decode = canonical_decode(raw)
    structured = canonical_structured_result(raw, preview)
    evidence = {
        "schema": SCHEMA,
        "name": "readboard_external_capture_mvp",
        "status": "pass",
        "platform": runtime_report.get("platform", "macos"),
        "collectionMethod": "runtime_backend_local_image_capture_decode_mvp" if source_kind == "local_image" else "runtime_backend_external_capture_mvp",
        "runtimeObserved": True,
        "backendCommandInvoked": True,
        "backendCommand": "readboard_external_capture",
        "operatorInitiated": capture_source.get("operatorInitiated") is True if isinstance(capture_source, dict) else False,
        "userSelectionRequired": capture_source.get("userSelectionRequired") is True if isinstance(capture_source, dict) else False,
        "previewOnlyBeforeConfirmation": preview.get("previewOnlyBeforeConfirmation") is True,
        "boardReplacedOnlyAfterConfirmation": preview.get("boardReplacedOnlyAfterConfirmation") is True,
        "localImageDecodeOnly": source_kind == "local_image",
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
    failures = validate_evidence(evidence, ROOT)
    if failures:
        raise ValueError("readboard external capture MVP evidence is invalid: " + "; ".join(failures))
    return evidence


def validate_evidence(evidence: Any, root: Path = ROOT) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    raw = evidence.get("rawBackendResult")
    if not isinstance(raw, dict):
        return ["rawBackendResult must be an object"]
    source = canonical_source_kind(first_present(raw, "captureSource", "source"))
    if source == "local_image":
        return validate_local_image_evidence(evidence, root)
    return smoke_user_flows.validate_readboard_external_capture_mvp_evidence(evidence, root)


def validate_local_image_evidence(evidence: dict[str, Any], root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    if evidence.get("schema") != SCHEMA:
        failures.append(f"schema must be {SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    if evidence.get("collectionMethod") != "runtime_backend_local_image_capture_decode_mvp":
        failures.append("collectionMethod must be runtime_backend_local_image_capture_decode_mvp for local_image evidence")
    for key, expected in {
        "runtimeObserved": True,
        "backendCommandInvoked": True,
        "sourceStaticOnly": False,
        "operatorInitiated": False,
        "userSelectionRequired": False,
        "previewOnlyBeforeConfirmation": False,
        "boardReplacedOnlyAfterConfirmation": False,
        "localImageDecodeOnly": True,
    }.items():
        if evidence.get(key) is not expected:
            failures.append(f"{key} must be {str(expected).lower()} for local_image evidence")
    for key, expected in boundaries().items():
        if evidence.get(key) is not expected:
            failures.append(f"{key} must be false")
    if evidence.get("backendCommand") != "readboard_external_capture":
        failures.append("backendCommand must be readboard_external_capture")

    raw = evidence.get("rawBackendResult")
    if isinstance(raw, dict):
        if raw.get("status") != "captured":
            failures.append("rawBackendResult.status must be captured")
        if canonical_source_kind(first_present(raw, "captureSource", "source")) != "local_image":
            failures.append("rawBackendResult source must be local_image for local-image evidence")
        if raw.get("operatorInitiated") is True or raw.get("userSelectionRequired") is True:
            failures.append("rawBackendResult must not claim operator selection for local_image")
        if first_present(raw, "boardReplacement", "board_replacement") not in {None, "none"}:
            failures.append("rawBackendResult.boardReplacement must be absent or none for local_image")
        failures.extend(validate_raw_position(raw))
    else:
        failures.append("rawBackendResult must be an object")

    capture_source = evidence.get("captureSource")
    if not isinstance(capture_source, dict):
        failures.append("captureSource must be an object")
    else:
        if capture_source.get("sourceKind") != "local_image":
            failures.append("captureSource.sourceKind must be local_image")
        if capture_source.get("operatorInitiated") is not False:
            failures.append("captureSource.operatorInitiated must be false for local_image")
        if capture_source.get("userSelectionRequired") is not False:
            failures.append("captureSource.userSelectionRequired must be false for local_image")
        if capture_source.get("targetClientDiscoveryCovered") is not False:
            failures.append("captureSource.targetClientDiscoveryCovered must be false")
        if capture_source.get("externalClientCaptureCovered") is not False:
            failures.append("captureSource.externalClientCaptureCovered must be false")
        if capture_source.get("selection") is not None:
            failures.append("captureSource.selection must be absent for local_image")

    preview = check_by_name(evidence, "preview_confirmation")
    preview_details = preview.get("details") if isinstance(preview, dict) and isinstance(preview.get("details"), dict) else {}
    if preview_details.get("userConfirmed") is True:
        failures.append("preview_confirmation.userConfirmed must not be synthesized for local_image")
    if preview_details.get("boardReplacedOnlyAfterConfirmation") is True:
        failures.append("preview_confirmation.boardReplacedOnlyAfterConfirmation must be false for local_image")

    structured = evidence.get("structuredResult")
    if not isinstance(structured, dict):
        failures.append("structuredResult must be an object")
    else:
        if structured.get("structuredResultVerified") is not True:
            failures.append("structuredResult.structuredResultVerified must be true")
        if structured.get("boardReplaced") is not False:
            failures.append("structuredResult.boardReplaced must be false for local_image")
        if structured.get("replacementConfirmed") is not False:
            failures.append("structuredResult.replacementConfirmed must be false for local_image")
        if structured.get("boardSize") not in {9, 13, 19}:
            failures.append("structuredResult.boardSize must be 9, 13, or 19")
    artifact = evidence.get("captureArtifact")
    if isinstance(artifact, dict):
        failures.extend(validate_artifact(root, artifact))
    else:
        failures.append("captureArtifact must be an object")
    decode = evidence.get("decodeSummary")
    if isinstance(decode, dict):
        if decode.get("decodeSucceeded") is not True:
            failures.append("decodeSummary.decodeSucceeded must be true")
        if decode.get("structuredResultProduced") is not True:
            failures.append("decodeSummary.structuredResultProduced must be true")
    else:
        failures.append("decodeSummary must be an object")
    return failures


def check_by_name(evidence: dict[str, Any], name: str) -> dict[str, Any] | None:
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        return None
    for check in checks:
        if isinstance(check, dict) and check.get("name") == name:
            return check
    return None


def validate_raw_position(raw: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    position = raw.get("position")
    if not isinstance(position, dict):
        return ["rawBackendResult.position must be an object"]
    if first_present(position, "board_size", "boardSize") not in {9, 13, 19}:
        failures.append("rawBackendResult.position.board_size must be 9, 13, or 19")
    if not isinstance(first_present(position, "move_number", "moveNumber"), (int, float)):
        failures.append("rawBackendResult.position.move_number must be numeric")
    if normalize_to_play(first_present(position, "to_play", "toPlay")) not in {"black", "white"}:
        failures.append("rawBackendResult.position.to_play must be black or white")
    if not isinstance(position.get("stones"), list):
        failures.append("rawBackendResult.position.stones must be a list")
    return failures


def validate_artifact(root: Path, artifact: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    path = artifact.get("path")
    if not isinstance(path, str) or not path:
        failures.append("captureArtifact.path must be non-empty")
    elif path.startswith("/") or path.startswith("~") or "/tmp" in path or "/Users/" in path:
        failures.append("captureArtifact.path must be repo-relative and sanitized")
    elif not (root / path).is_file():
        failures.append("captureArtifact.path must exist")
    if not isinstance(artifact.get("sizeBytes"), (int, float)) or artifact.get("sizeBytes") <= 0:
        failures.append("captureArtifact.sizeBytes must be positive")
    sha = artifact.get("sha256")
    if not isinstance(sha, str) or len(sha) != 64:
        failures.append("captureArtifact.sha256 must be 64 hex characters")
    if artifact.get("sanitized") is not True:
        failures.append("captureArtifact.sanitized must be true")
    return failures


def validate_existing(path: Path) -> int:
    evidence = load_json(path)
    status = str(evidence.get("status", "")).lower()
    if status in {"pending", "unavailable"}:
        failures = smoke_user_flows.validate_readboard_external_capture_mvp_unavailable_evidence(evidence, ROOT)
        if failures:
            raise SystemExit("readboard external capture MVP pending/unavailable evidence is invalid: " + "; ".join(failures))
        print("readboard external capture MVP evidence is pending/unavailable; no PASS claim recorded")
        return 0
    failures = validate_evidence(evidence, ROOT)
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
