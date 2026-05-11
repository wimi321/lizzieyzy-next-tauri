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
SCHEMA = "lizzieyzy.readboard-tauri-runtime-smoke.v1"
TAURI_RUNTIME_SCHEMA = "lizzieyzy.tauri-runtime-ui-smoke.v1"
REQUIRED_CHECKS = [
    "runtime_started",
    "sidecar_probe_ready",
    "sidecar_probe_unavailable",
    "protocol_line_sync",
    "target_state_change_sync",
    "unsupported_ocr_path",
    "external_client_not_covered",
]
SMOKE_SGF = "(;FF[4]GM[1]SZ[2]C[readboard runtime smoke])\n"
GENERATED_READBOARD_ARTIFACTS = ["readboard_boofcv_config.txt"]


class SmokeError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SmokeError(f"report was not created: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeError(f"report is invalid JSON at line {exc.lineno}: {exc.msg}") from exc


def check_evidence(check: Any) -> dict[str, Any] | None:
    if not isinstance(check, dict):
        return None
    for key in ("evidence", "details"):
        value = check.get(key)
        if isinstance(value, dict):
            return value
    return check


def runtime_check(raw_report: dict[str, Any], name: str) -> dict[str, Any]:
    checks = raw_report.get("checks")
    if not isinstance(checks, list):
        return {"name": name, "status": "fail", "details": {"missing": True}}
    for check in checks:
        if isinstance(check, dict) and check.get("name") == name:
            return check
    return {"name": name, "status": "fail", "details": {"missing": True}}


def normalize_runtime_check(raw_report: dict[str, Any], name: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = runtime_check(raw_report, name)
    normalized: dict[str, Any] = {
        "name": name,
        "status": str(raw.get("status", "")).lower() or "fail",
        "details": details if details is not None else (check_evidence(raw) or {}),
    }
    if isinstance(raw.get("error"), str):
        normalized["error"] = raw["error"]
    return normalized


def validate_raw_tauri_report(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["raw Tauri report root must be an object"]
    failures: list[str] = []
    if report.get("schema") != TAURI_RUNTIME_SCHEMA:
        failures.append(f"raw Tauri report schema must be {TAURI_RUNTIME_SCHEMA}")
    if report.get("phase") != "readboard-live":
        failures.append("raw Tauri report phase must be readboard-live")
    if str(report.get("status", "")).lower() != "pass":
        failures.append("raw Tauri report status must be pass")
    return failures


def validate_report(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["report root must be an object"]
    failures: list[str] = []
    if report.get("schema") != SCHEMA:
        failures.append(f"schema must be {SCHEMA}")
    if str(report.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    checks = report.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list")
        return failures
    check_by_name = {check.get("name"): check for check in checks if isinstance(check, dict)}
    missing = [name for name in REQUIRED_CHECKS if name not in check_by_name]
    not_pass = [
        name
        for name in REQUIRED_CHECKS
        if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
    ]
    if missing:
        failures.append("missing required checks: " + ", ".join(missing))
    if not_pass:
        failures.append("required checks not pass: " + ", ".join(not_pass))
    failures.extend(validate_runtime_started(check_by_name.get("runtime_started")))
    failures.extend(validate_ready_probe(check_by_name.get("sidecar_probe_ready")))
    failures.extend(validate_unavailable_probe(check_by_name.get("sidecar_probe_unavailable")))
    failures.extend(validate_protocol_line_sync(check_by_name.get("protocol_line_sync")))
    failures.extend(validate_target_state_change_sync(check_by_name.get("target_state_change_sync")))
    failures.extend(validate_unsupported_ocr(check_by_name.get("unsupported_ocr_path")))
    failures.extend(validate_external_scope(check_by_name.get("external_client_not_covered")))
    return failures


def validate_runtime_started(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["runtime_started evidence must be an object"]
    return [] if evidence.get("tauriInternals") is True else ["runtime_started must confirm real Tauri runtime"]


def validate_ready_probe(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["sidecar_probe_ready evidence must be an object"]
    return [] if evidence.get("available") is True else ["sidecar_probe_ready must report available true"]


def validate_unavailable_probe(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["sidecar_probe_unavailable evidence must be an object"]
    if evidence.get("available") is not False:
        return ["sidecar_probe_unavailable must report available false"]
    warnings = evidence.get("warnings")
    if not isinstance(warnings, list) or not warnings:
        return ["sidecar_probe_unavailable must include structured warnings"]
    return []


def validate_protocol_line_sync(check: Any) -> list[str]:
    evidence = check_evidence(check)
    name = "protocol_line_sync"
    if evidence is None:
        return [f"{name} evidence must be an object"]
    failures: list[str] = []
    if evidence.get("boardSize") != 2:
        failures.append(f"{name} must report boardSize 2")
    if evidence.get("moveNumber") != 1:
        failures.append(f"{name} must report moveNumber 1")
    if evidence.get("stoneCount") != 1:
        failures.append(f"{name} must report stoneCount 1")
    if evidence.get("snapshotId") in (None, ""):
        failures.append(f"{name} must include snapshot id")
    if evidence.get("toPlay") != "white":
        failures.append(f"{name} must report toPlay white")
    if not isinstance(evidence.get("warnings"), list):
        failures.append(f"{name} must include warnings list")
    return failures


def validate_target_state_change_sync(check: Any) -> list[str]:
    evidence = check_evidence(check)
    name = "target_state_change_sync"
    if evidence is None:
        return [f"{name} evidence must be an object"]
    failures: list[str] = []
    if evidence.get("changed") is not True:
        failures.append(f"{name} must report changed true")
    if evidence.get("beforeSnapshotId") in (None, "") or evidence.get("afterSnapshotId") in (None, ""):
        failures.append(f"{name} must include before/after snapshot ids")
    elif evidence.get("beforeSnapshotId") == evidence.get("afterSnapshotId"):
        failures.append(f"{name} must change snapshot id")
    if evidence.get("beforeStoneCount") != 1:
        failures.append(f"{name} must report beforeStoneCount 1")
    if evidence.get("afterStoneCount") != 2:
        failures.append(f"{name} must report afterStoneCount 2")
    if evidence.get("beforeMoveNumber") != 1:
        failures.append(f"{name} must report beforeMoveNumber 1")
    if evidence.get("afterMoveNumber") != 2:
        failures.append(f"{name} must report afterMoveNumber 2")
    if evidence.get("boardSizeStable") is not True:
        failures.append(f"{name} must report boardSizeStable true")
    if evidence.get("toPlay") != "white" and evidence.get("afterToPlay") != "white":
        failures.append(f"{name} must report changed toPlay white")
    if not isinstance(evidence.get("warnings"), list):
        failures.append(f"{name} must include warnings list")
    return failures


def validate_unsupported_ocr(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["unsupported_ocr_path evidence must be an object"]
    message = str(evidence.get("message", "")).lower()
    if evidence.get("observed") is not True:
        return ["unsupported_ocr_path must confirm observed true"]
    if evidence.get("unsupported") is not True:
        return ["unsupported_ocr_path must confirm unsupported true"]
    if evidence.get("messageIncludesBoundary") is not True:
        return ["unsupported_ocr_path must confirm messageIncludesBoundary true"]
    if "image" not in message and "ocr" not in message:
        return ["unsupported_ocr_path must name image/OCR boundary"]
    return []


def validate_external_scope(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["external_client_not_covered evidence must be an object"]
    if evidence.get("covered") is not False:
        return ["external_client_not_covered must explicitly mark covered false"]
    if evidence.get("ocrCovered") is not False or evidence.get("externalClientCaptureCovered") is not False:
        return ["external_client_not_covered must exclude OCR and external client capture"]
    return []


def build_evidence(raw_report: Any, *, endpoint: str | None, timeout_seconds: float) -> dict[str, Any]:
    if not isinstance(raw_report, dict):
        raise SmokeError("raw Tauri report root must be an object")
    raw_failures = validate_raw_tauri_report(raw_report)
    if raw_failures:
        raise SmokeError("; ".join(raw_failures))
    checks = [normalize_runtime_check(raw_report, name) for name in REQUIRED_CHECKS]
    return {
        "schema": SCHEMA,
        "name": "readboard_tauri_runtime_smoke",
        "status": "pass",
        "platform": "macos" if platform.system() == "Darwin" else platform.system().lower(),
        "phase": "readboard-live",
        "endpoint": endpoint,
        "timeoutSeconds": timeout_seconds,
        "runtimeReport": {
            "schema": raw_report.get("schema"),
            "phase": raw_report.get("phase"),
            "status": raw_report.get("status"),
            "startedAt": raw_report.get("startedAt"),
            "finishedAt": raw_report.get("finishedAt"),
        },
        "checks": checks,
    }


def write_smoke_sgf(path: Path) -> None:
    path.write_text(SMOKE_SGF, encoding="utf-8")


def start_tauri(
    root: Path,
    sgf_path: Path,
    report_path: Path,
    log_path: Path,
    work_dir: Path,
    *,
    readboard_home: Path | None,
    endpoint: str | None,
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env.update(
        {
            "VITE_LIZZIEYZY_RUNTIME_SMOKE": "1",
            "LIZZIEYZY_RUNTIME_SMOKE": "1",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_PHASE": "readboard-live",
            "LIZZIEYZY_RUNTIME_SMOKE_PHASE": "readboard-live",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            "LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
        }
    )
    if endpoint:
        env["VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_ENDPOINT"] = endpoint
    if readboard_home:
        env["READBOARD_HOME"] = str(readboard_home)
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


def wait_for_report(report_path: Path, process: subprocess.Popen[bytes], *, timeout_seconds: float) -> Any:
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
    raise SmokeError(f"timed out after {timeout_seconds:g}s waiting for Tauri readboard runtime report")


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


def write_evidence(path: Path, report: Any, *, root: Path, temp_dir: Path, readboard_home: Path | None) -> None:
    replacements = [
        (str(root.resolve()), "<repo>"),
        (str(temp_dir.resolve()), "<tmp>"),
    ]
    if readboard_home:
        replacements.append((str(readboard_home.resolve()), "<readboard-home>"))
    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize_evidence(report, replacements), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generated_artifact_state(root: Path) -> dict[Path, bool]:
    return {root / name: (root / name).exists() for name in GENERATED_READBOARD_ARTIFACTS}


def cleanup_new_generated_artifacts(state: dict[Path, bool]) -> None:
    for path, existed_before in state.items():
        if not existed_before and path.is_file():
            path.unlink()


def run(
    root: Path,
    *,
    timeout_seconds: float,
    evidence_out: Path | None,
    readboard_home: Path | None = None,
    endpoint: str | None = None,
) -> int:
    root = root.resolve()
    if platform.system() != "Darwin":
        print("Tauri readboard runtime smoke is currently a macOS local evidence gate.", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"Repository root does not exist: {root}", file=sys.stderr)
        return 2
    if readboard_home is not None and not readboard_home.exists():
        print(f"Readboard home does not exist: {readboard_home}", file=sys.stderr)
        return 2

    temp_dir = Path(tempfile.mkdtemp(prefix="lizzieyzy-tauri-readboard-smoke-"))
    keep_temp_dir = True
    artifact_state = generated_artifact_state(root)
    try:
        sgf_path = temp_dir / "readboard-smoke.sgf"
        report_path = temp_dir / "readboard-tauri-runtime-report.json"
        log_path = temp_dir / "tauri-dev.log"
        work_dir = temp_dir / "work"
        work_dir.mkdir()
        write_smoke_sgf(sgf_path)
        process = start_tauri(root, sgf_path, report_path, log_path, work_dir, readboard_home=readboard_home, endpoint=endpoint)
        try:
            raw_report = wait_for_report(report_path, process, timeout_seconds=timeout_seconds)
            report = build_evidence(raw_report, endpoint=endpoint, timeout_seconds=timeout_seconds)
            failures = validate_report(report)
            if failures:
                raise SmokeError("; ".join(failures))
            if evidence_out is not None:
                write_evidence(evidence_out, report, root=root, temp_dir=temp_dir, readboard_home=readboard_home)
            print(f"PASS Tauri readboard runtime smoke: {len(REQUIRED_CHECKS)} required checks passed")
            keep_temp_dir = False
            return 0
        except SmokeError as exc:
            print(f"FAIL Tauri readboard runtime smoke: {exc}", file=sys.stderr)
            print(f"failure artifacts retained in: {temp_dir}", file=sys.stderr)
            if report_path.is_file():
                print(f"runtime report: {report_path}", file=sys.stderr)
            if log_path.is_file():
                print(f"tauri:dev log: {log_path}", file=sys.stderr)
            return 1
        finally:
            stop_process(process)
            cleanup_new_generated_artifacts(artifact_state)
            if not keep_temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        cleanup_new_generated_artifacts(artifact_state)
        if not keep_temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the macOS Tauri runtime readboard smoke and validate its JSON report.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds to wait for the runtime report")
    parser.add_argument("--readboard-home", type=Path, default=Path(os.environ["READBOARD_HOME"]) if os.environ.get("READBOARD_HOME") else None)
    parser.add_argument("--endpoint", help="optional readboard endpoint for ready probe")
    parser.add_argument("--evidence-out", type=Path, default=ROOT / "docs/qa/readboard-tauri-runtime-smoke-macos.json")
    args = parser.parse_args(argv)
    return run(
        args.root,
        timeout_seconds=args.timeout,
        evidence_out=args.evidence_out,
        readboard_home=args.readboard_home,
        endpoint=args.endpoint,
    )


if __name__ == "__main__":
    raise SystemExit(main())
