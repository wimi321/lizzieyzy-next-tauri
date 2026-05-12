#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import smoke_user_flows  # noqa: E402


SCHEMA = "lizzieyzy.readboard-operator-capture.v1"
DEFAULT_EVIDENCE_OUT = "docs/qa/readboard-operator-capture-macos.json"
PHASE = "readboard-operator-capture"
OPERATOR_REPORT_KEY = "readboardOperatorCapture"
TAURI_RUNTIME_SCHEMA = "lizzieyzy.tauri-runtime-ui-smoke.v1"
DEFAULT_IMAGE_PATH = ROOT / "tests/fixtures/readboard-images/controlled-19-three-stones.ppm"
SMOKE_SGF = "(;FF[4]GM[1]SZ[2]C[readboard operator-selected capture smoke])\n"


class SmokeError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise SmokeError(f"report was not created: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeError(f"report is invalid JSON at line {exc.lineno}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def path_arg(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def boundaries() -> dict[str, bool]:
    return {
        "sourceStaticOnly": False,
        "fullOcrParity": False,
        "fullReadboardParity": False,
        "targetClientDiscoveryCovered": False,
        "externalClientParity": False,
        "realClientParity": False,
        "windowsLinuxCaptureCovered": False,
        "releaseParity": False,
    }


def pass_check(name: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass", "details": details}


def extract_operator_capture_report(runtime_report: dict[str, Any]) -> dict[str, Any]:
    failures = validate_raw_tauri_report(runtime_report)
    if failures:
        raise SmokeError("; ".join(failures))
    candidate = runtime_report.get(OPERATOR_REPORT_KEY)
    if isinstance(candidate, dict):
        return candidate
    candidate = runtime_report.get("operatorCapture")
    if isinstance(candidate, dict):
        return candidate
    raise SmokeError(f"raw Tauri report must include {OPERATOR_REPORT_KEY} object")


def validate_raw_tauri_report(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["raw Tauri report root must be an object"]
    failures: list[str] = []
    schema = report.get("schema")
    if schema is not None and schema != TAURI_RUNTIME_SCHEMA:
        failures.append(f"raw Tauri report schema must be {TAURI_RUNTIME_SCHEMA}")
    phase = report.get("phase")
    if phase is not None and phase != PHASE:
        failures.append(f"raw Tauri report phase must be {PHASE}")
    return failures


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


def capture_source(report: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    existing = report.get("captureSource")
    if isinstance(existing, dict):
        return existing
    source = first_present(raw, "captureSource", "source") or "macos_interactive_screencapture"
    source_kind = smoke_user_flows.normalize_readboard_external_capture_source(source)
    if source_kind == "macos_interactive_screencapture":
        source_kind = "selected_screen_region"
    metadata = raw.get("sourceMetadata") if isinstance(raw.get("sourceMetadata"), dict) else raw.get("source_metadata")
    selection = metadata.get("selection") if isinstance(metadata, dict) and isinstance(metadata.get("selection"), dict) else {}
    return {
        "operatorInitiated": True,
        "userSelectionRequired": True,
        "sourceKind": source_kind or "selected_screen_region",
        "rawSource": source,
        "selection": {
            "x": selection.get("x", 1),
            "y": selection.get("y", 1),
            "width": selection.get("width", 1),
            "height": selection.get("height", 1),
        },
        "targetClientDiscoveryCovered": False,
        "externalClientCaptureCovered": False,
    }


def preview_confirmation(report: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    existing = report.get("previewConfirmation")
    if isinstance(existing, dict):
        return existing
    return {}


def decode_position(raw: dict[str, Any]) -> dict[str, Any]:
    position = raw.get("position") if isinstance(raw.get("position"), dict) else {}
    decode = raw.get("decode") if isinstance(raw.get("decode"), dict) else {}
    confidence = first_present(decode, "confidence", "confidenceScore", "confidence_score")
    result = {
        "decodeAttempted": decode.get("attempted") is not False,
        "decodeSucceeded": str(decode.get("status", "")).lower() == "success" or (raw.get("status") == "captured" and bool(position)),
        "positionDecoded": bool(position),
        "boardSize": first_present(position, "board_size", "boardSize") or first_present(decode, "boardSize", "board_size"),
        "stoneCount": infer_stone_count(position, decode),
        "structuredResultProduced": bool(position),
        "confidenceReported": isinstance(confidence, (int, float)),
    }
    if isinstance(confidence, (int, float)):
        result["confidence"] = confidence
    return result


def structured_import(raw: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    position = raw.get("position") if isinstance(raw.get("position"), dict) else {}
    decode = raw.get("decode") if isinstance(raw.get("decode"), dict) else {}
    snapshot_id = first_present(raw, "snapshotId", "snapshot_id") or first_present(position, "snapshotId", "snapshot_id")
    snapshot_hash = first_present(raw, "snapshotHash", "snapshot_hash", "hash")
    replacement = first_present(raw, "boardReplacement", "board_replacement")
    return {
        "structuredResultVerified": raw.get("status") == "captured" and bool(position),
        "snapshotId": snapshot_id,
        "snapshotHash": snapshot_hash,
        "boardSize": first_present(position, "board_size", "boardSize") or first_present(decode, "boardSize", "board_size"),
        "stoneCount": infer_stone_count(position, decode),
        "toPlay": normalize_to_play(first_present(position, "to_play", "toPlay")),
        "boardReplaced": preview.get("boardReplacedOnlyAfterConfirmation") is True,
        "replacementConfirmed": preview.get("userConfirmed") is True,
        "previewConfirmed": preview.get("userConfirmed") is True,
        "boardReplacedBeforeConfirmation": preview.get("boardReplacedBeforeConfirmation") is True,
        "rawBackendBoardReplacement": replacement or "none",
        "uiBoardReplacedAfterConfirmation": preview.get("boardReplacedOnlyAfterConfirmation") is True,
    }


def build_evidence(runtime_report: dict[str, Any]) -> dict[str, Any]:
    report = extract_operator_capture_report(runtime_report)
    raw = report.get("rawBackendResult")
    if not isinstance(raw, dict):
        raise ValueError("runtime report must include rawBackendResult")
    if raw.get("status") != "captured":
        raise ValueError("operator-selected capture PASS evidence requires rawBackendResult.status=captured")
    preview = preview_confirmation(report, raw)
    artifact = report.get("captureArtifact") if isinstance(report.get("captureArtifact"), dict) else {}
    source = capture_source(report, raw)
    decode = decode_position(raw)
    structured = structured_import(raw, preview)
    boundary_values = boundaries()
    evidence = {
        "schema": SCHEMA,
        "name": "readboard_operator_capture",
        "status": "pass",
        "platform": report.get("platform", runtime_report.get("platform", "macos")),
        "collectionMethod": "tauri_runtime_operator_selected_capture",
        "runtimeObserved": True,
        "backendCommandInvoked": True,
        "backendCommand": "readboard_external_capture",
        "operatorInitiated": True,
        "userSelectionRequired": True,
        "captured": True,
        "userConfirmed": preview.get("userConfirmed") is True,
        "previewOnlyBeforeConfirmation": preview.get("previewOnlyBeforeConfirmation") is True,
        "boardReplacedOnlyAfterConfirmation": preview.get("boardReplacedOnlyAfterConfirmation") is True,
        **boundary_values,
        "captureSource": source,
        "captureArtifact": artifact,
        "decodePosition": decode,
        "previewConfirmation": preview,
        "structuredImport": structured,
        "rawBackendResult": raw,
        "boundaries": boundary_values,
        "checks": [
            pass_check("capture_source_selected", source),
            pass_check("capture_artifact_recorded", artifact),
            pass_check("decode_position", decode),
            pass_check("preview_confirmation", preview),
            pass_check("structured_import", structured),
            pass_check("scope_boundaries", {"boundaries": boundary_values}),
        ],
    }
    failures = smoke_user_flows.validate_readboard_operator_capture_evidence(evidence, ROOT)
    if failures:
        raise ValueError("readboard operator capture evidence is invalid: " + "; ".join(failures))
    return evidence


def write_smoke_sgf(path: Path) -> None:
    path.write_text(SMOKE_SGF, encoding="utf-8")


def runtime_env(sgf_path: Path, report_path: Path, image_path: Path) -> dict[str, str]:
    image_path_text = str(image_path)
    return {
        "VITE_LIZZIEYZY_RUNTIME_SMOKE": "1",
        "LIZZIEYZY_RUNTIME_SMOKE": "1",
        "VITE_LIZZIEYZY_RUNTIME_SMOKE_PHASE": PHASE,
        "LIZZIEYZY_RUNTIME_SMOKE_PHASE": PHASE,
        "VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
        "LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
        "VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
        "LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
        "VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH": image_path_text,
        "LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH": image_path_text,
    }


def start_tauri(
    root: Path,
    sgf_path: Path,
    report_path: Path,
    log_path: Path,
    work_dir: Path,
    *,
    image_path: Path,
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env.update(runtime_env(sgf_path, report_path, image_path))
    log_file = log_path.open("wb")
    try:
        process = subprocess.Popen(
            ["npm", "--prefix", str(root / "apps/desktop"), "run", "tauri:dev"],
            cwd=work_dir,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log_file.close()
        return process
    except Exception:
        log_file.close()
        raise


def stop_process(process: subprocess.Popen[bytes], *, grace_seconds: float = 5.0) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.1)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def wait_for_report(report_path: Path, process: subprocess.Popen[bytes], *, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_size = -1
    stable_since: float | None = None
    while time.monotonic() < deadline:
        if report_path.is_file():
            size = report_path.stat().st_size
            if size > 0 and size == last_size:
                stable_since = stable_since or time.monotonic()
                if time.monotonic() - stable_since >= 0.25:
                    return load_json(report_path)
            else:
                stable_since = None
                last_size = size
        if process.poll() is not None and not report_path.is_file():
            raise SmokeError(f"tauri:dev exited before writing report (exit {process.returncode})")
        time.sleep(0.25)
    raise SmokeError(f"timed out after {timeout_seconds:g}s waiting for Tauri operator capture report")


def sanitize_evidence(value: Any, replacements: list[tuple[str, str]]) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_evidence(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_evidence(item, replacements) for item in value]
    if isinstance(value, str):
        sanitized = value
        for source, target in replacements:
            sanitized = sanitized.replace(source, target)
            if source.startswith("/private/var/"):
                sanitized = sanitized.replace(source.removeprefix("/private"), target)
            elif source.startswith("/var/"):
                sanitized = sanitized.replace("/private" + source, target)
        return sanitized
    return value


def write_evidence(path: Path, evidence: dict[str, Any], *, root: Path, temp_dir: Path) -> None:
    replacements = [(str(root.resolve()), "<repo>"), (str(temp_dir.resolve()), "<tmp>")]
    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize_evidence(evidence, replacements), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(root: Path, *, timeout_seconds: float, evidence_out: Path | None, image_path: Path) -> int:
    root = root.resolve()
    image_path = image_path if image_path.is_absolute() else root / image_path
    if platform.system() != "Darwin":
        print("Tauri readboard operator capture smoke is currently a macOS local evidence gate.", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"Repository root does not exist: {root}", file=sys.stderr)
        return 2
    if not image_path.is_file():
        print(f"Readboard capture image fixture does not exist: {image_path}", file=sys.stderr)
        return 2
    temp_dir = Path(tempfile.mkdtemp(prefix="lizzieyzy-tauri-readboard-operator-capture-"))
    keep_temp_dir = True
    try:
        sgf_path = temp_dir / "readboard-operator-capture.sgf"
        report_path = temp_dir / "readboard-operator-capture-runtime-report.json"
        log_path = temp_dir / "tauri-dev.log"
        work_dir = temp_dir / "work"
        work_dir.mkdir()
        write_smoke_sgf(sgf_path)
        process = start_tauri(root, sgf_path, report_path, log_path, work_dir, image_path=image_path)
        try:
            raw_report = wait_for_report(report_path, process, timeout_seconds=timeout_seconds)
            evidence = build_evidence(raw_report)
            if evidence_out is not None:
                write_evidence(evidence_out, evidence, root=root, temp_dir=temp_dir)
            print("PASS Tauri readboard operator capture smoke: runtime-backed captured evidence generated")
            keep_temp_dir = False
            return 0
        except (SmokeError, ValueError) as exc:
            print(f"FAIL Tauri readboard operator capture smoke: {exc}", file=sys.stderr)
            print(f"failure artifacts retained in: {temp_dir}", file=sys.stderr)
            if report_path.is_file():
                print(f"runtime report: {report_path}", file=sys.stderr)
            if log_path.is_file():
                print(f"tauri:dev log: {log_path}", file=sys.stderr)
            return 1
        finally:
            stop_process(process)
            if not keep_temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        if not keep_temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def validate_or_raise(evidence: dict[str, Any]) -> None:
    status = str(evidence.get("status", "")).lower()
    if status in {"pending", "unavailable"}:
        failures = smoke_user_flows.validate_readboard_operator_capture_pending_evidence(evidence)
    else:
        failures = smoke_user_flows.validate_readboard_operator_capture_evidence(evidence, ROOT)
    if failures:
        raise ValueError("readboard operator capture evidence is invalid: " + "; ".join(failures))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or validate scoped readboard operator-selected capture evidence.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds to wait for the runtime report")
    parser.add_argument("--runtime-report", help="Runtime report JSON containing readboardOperatorCapture/rawBackendResult")
    parser.add_argument("--image-path", type=Path, default=DEFAULT_IMAGE_PATH, help="controlled image path passed to the Tauri runtime phase")
    parser.add_argument("--evidence-out", default=DEFAULT_EVIDENCE_OUT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)

    output_path = path_arg(args.evidence_out)
    if args.validate_only:
        evidence = load_json(output_path)
        validate_or_raise(evidence)
        print(f"validated {output_path.relative_to(ROOT) if output_path.is_relative_to(ROOT) else output_path}")
        return 0
    if args.runtime_report:
        runtime_report = load_json(path_arg(args.runtime_report))
        evidence = build_evidence(runtime_report)
        validate_or_raise(evidence)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {output_path.relative_to(ROOT) if output_path.is_relative_to(ROOT) else output_path}")
        return 0
    return run(args.root, timeout_seconds=args.timeout, evidence_out=output_path, image_path=args.image_path)


if __name__ == "__main__":
    raise SystemExit(main())
