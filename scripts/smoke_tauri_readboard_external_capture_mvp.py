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
PHASE = "readboard-external-capture-mvp"
TAURI_RUNTIME_SCHEMA = "lizzieyzy.tauri-runtime-ui-smoke.v1"
DEFAULT_EVIDENCE_OUT = ROOT / "docs/qa/readboard-external-capture-mvp-macos.json"
DEFAULT_IMAGE_PATH = ROOT / "tests/fixtures/readboard-images/controlled-19-three-stones.ppm"
SMOKE_SGF = "(;FF[4]GM[1]SZ[2]C[readboard external capture MVP smoke])\n"

if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import smoke_readboard_external_capture_mvp  # noqa: E402


class SmokeError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SmokeError(f"report was not created: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeError(f"report is invalid JSON at line {exc.lineno}: {exc.msg}") from exc


def validate_raw_tauri_report(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["raw Tauri report root must be an object"]
    failures: list[str] = []
    schema = report.get("schema")
    if schema is not None and schema != TAURI_RUNTIME_SCHEMA:
        failures.append(f"raw Tauri report schema must be {TAURI_RUNTIME_SCHEMA}")
    if report.get("phase") != PHASE:
        failures.append(f"raw Tauri report phase must be {PHASE}")
    return failures


def extract_runtime_capture_report(raw_report: Any) -> dict[str, Any]:
    failures = validate_raw_tauri_report(raw_report)
    if failures:
        raise SmokeError("; ".join(failures))
    assert isinstance(raw_report, dict)
    capture_report = raw_report.get("readboardExternalCaptureMvp")
    if not isinstance(capture_report, dict):
        raise SmokeError("raw Tauri report must include readboardExternalCaptureMvp object")
    raw_backend = capture_report.get("rawBackendResult")
    if not isinstance(raw_backend, dict):
        raise SmokeError("readboardExternalCaptureMvp must include rawBackendResult")
    if raw_backend.get("status") != "captured":
        raise SmokeError(
            "readboardExternalCaptureMvp rawBackendResult.status must be captured before PASS evidence can be generated"
        )
    normalized = dict(capture_report)
    normalized.setdefault("platform", raw_report.get("platform") or ("macos" if platform.system() == "Darwin" else platform.system().lower()))
    return normalized


def build_evidence_from_tauri_report(raw_report: Any) -> dict[str, Any]:
    runtime_capture_report = extract_runtime_capture_report(raw_report)
    return smoke_readboard_external_capture_mvp.build_evidence(runtime_capture_report)


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
    raise SmokeError(f"timed out after {timeout_seconds:g}s waiting for Tauri external capture MVP report")


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


def write_evidence(path: Path, report: dict[str, Any], *, root: Path, temp_dir: Path) -> None:
    replacements = [
        (str(root.resolve()), "<repo>"),
        (str(temp_dir.resolve()), "<tmp>"),
    ]
    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize_evidence(report, replacements), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(root: Path, *, timeout_seconds: float, evidence_out: Path | None, image_path: Path) -> int:
    root = root.resolve()
    image_path = image_path if image_path.is_absolute() else root / image_path
    if platform.system() != "Darwin":
        print("Tauri readboard external capture MVP smoke is currently a macOS local evidence gate.", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"Repository root does not exist: {root}", file=sys.stderr)
        return 2
    if not image_path.is_file():
        print(f"Readboard capture image fixture does not exist: {image_path}", file=sys.stderr)
        return 2

    temp_dir = Path(tempfile.mkdtemp(prefix="lizzieyzy-tauri-readboard-external-capture-"))
    keep_temp_dir = True
    try:
        sgf_path = temp_dir / "readboard-external-capture.sgf"
        report_path = temp_dir / "readboard-external-capture-runtime-report.json"
        log_path = temp_dir / "tauri-dev.log"
        work_dir = temp_dir / "work"
        work_dir.mkdir()
        write_smoke_sgf(sgf_path)
        process = start_tauri(root, sgf_path, report_path, log_path, work_dir, image_path=image_path)
        try:
            raw_report = wait_for_report(report_path, process, timeout_seconds=timeout_seconds)
            evidence = build_evidence_from_tauri_report(raw_report)
            if evidence_out is not None:
                write_evidence(evidence_out, evidence, root=root, temp_dir=temp_dir)
            print("PASS Tauri readboard external capture MVP smoke: runtime-backed captured evidence generated")
            keep_temp_dir = False
            return 0
        except SmokeError as exc:
            print(f"FAIL Tauri readboard external capture MVP smoke: {exc}", file=sys.stderr)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Tauri readboard external capture MVP phase and aggregate runtime-backed evidence."
    )
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds to wait for the runtime report")
    parser.add_argument("--runtime-report", type=Path, help="validate/aggregate an existing raw Tauri runtime report instead of launching")
    parser.add_argument("--image-path", type=Path, default=DEFAULT_IMAGE_PATH, help="controlled image path passed to the Tauri runtime phase")
    parser.add_argument("--evidence-out", type=Path, default=DEFAULT_EVIDENCE_OUT)
    args = parser.parse_args(argv)

    if args.runtime_report:
        raw_report = load_json(args.runtime_report)
        evidence = build_evidence_from_tauri_report(raw_report)
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {args.evidence_out}")
        return 0
    return run(args.root, timeout_seconds=args.timeout, evidence_out=args.evidence_out, image_path=args.image_path)


if __name__ == "__main__":
    raise SystemExit(main())
