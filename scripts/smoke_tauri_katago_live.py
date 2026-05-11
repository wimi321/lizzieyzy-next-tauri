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
SCHEMA = "lizzieyzy.katago-tauri-runtime-smoke.v1"
REQUIRED_CHECKS = [
    "runtime_started",
    "katago_failure_mode_missing_assets",
    "katago_assets",
    "katago_analyze_once",
    "katago_analyze_game",
    "katago_start_cancel",
]
TAURI_RUNTIME_SCHEMA = "lizzieyzy.tauri-runtime-ui-smoke.v1"
SMOKE_SGF = """(;FF[4]GM[1]CA[UTF-8]AP[LizzieYzyNextKataGoSmoke]SZ[9]KM[6.5]PB[Black]PW[White]
;B[dd];W[ee];B[de])
"""


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


def first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and value > 0


def validate_report(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["report root must be an object"]
    failures: list[str] = []
    if report.get("schema") != SCHEMA:
        failures.append(f"schema must be {SCHEMA}")
    if str(report.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform_name = str(report.get("platform", "")).lower()
    if platform_name not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    checks = report.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list")
        return failures
    check_by_name = {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }
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
    failures.extend(validate_failure_mode(check_by_name.get("katago_failure_mode_missing_assets")))
    failures.extend(validate_assets(check_by_name.get("katago_assets")))
    failures.extend(validate_analysis(check_by_name.get("katago_analyze_once"), "katago_analyze_once"))
    failures.extend(validate_analysis(check_by_name.get("katago_analyze_game"), "katago_analyze_game"))
    failures.extend(validate_cancel(check_by_name.get("katago_start_cancel")))
    return failures


def validate_runtime_started(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["runtime_started evidence must be an object"]
    if evidence.get("tauriInternals") is not True:
        return ["runtime_started must confirm real Tauri runtime"]
    return []


def validate_assets(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["katago_assets evidence must be an object"]
    failures: list[str] = []
    if evidence.get("engineExists") is not True and evidence.get("engineExecutable") is not True:
        failures.append("katago_assets must confirm engine exists")
    if not positive_number(first_present(evidence, "modelBytes", "modelSizeBytes")):
        failures.append("katago_assets must include positive model bytes")
    if not positive_number(first_present(evidence, "configBytes", "configSizeBytes")):
        failures.append("katago_assets must include positive config bytes")
    return failures


def validate_failure_mode(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["katago_failure_mode_missing_assets evidence must be an object"]
    if evidence.get("observed") is not True:
        return ["katago_failure_mode_missing_assets must confirm observed failure"]
    missing_required = evidence.get("missingRequired")
    if not isinstance(missing_required, list) or not missing_required:
        structured_error = evidence.get("structuredError")
        if not isinstance(structured_error, str) or not structured_error.strip():
            return ["katago_failure_mode_missing_assets must include missing assets or structured error"]
    return []


def validate_analysis(check: Any, name: str) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return [f"{name} evidence must be an object"]
    failures: list[str] = []
    if not positive_number(first_present(evidence, "frameCount", "frames", "responseCount", "visits")):
        failures.append(f"{name} must include positive frame count")
    if not positive_number(first_present(evidence, "candidateCount", "moveInfoCount", "candidateMoveCount", "candidates")):
        failures.append(f"{name} must include positive candidate count")
    if (
        evidence.get("rootInfo") is not True
        and evidence.get("hasRootInfo") is not True
        and not positive_number(evidence.get("visits"))
    ):
        failures.append(f"{name} must confirm root info or positive visits")
    return failures


def validate_cancel(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["katago_start_cancel evidence must be an object"]
    failures: list[str] = []
    if not isinstance(first_present(evidence, "jobId", "job_id"), str):
        failures.append("katago_start_cancel must include job id")
    event = evidence.get("event")
    event_kind = event.get("kind") if isinstance(event, dict) else None
    if evidence.get("cancelRequested") is not True:
        failures.append("katago_start_cancel must confirm cancellation was requested")
    if evidence.get("cancelConfirmed") is not True and event_kind != "cancelled":
        failures.append("katago_start_cancel must confirm cancellation event")
    return failures


def validate_raw_tauri_report(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["raw Tauri report root must be an object"]
    failures: list[str] = []
    if report.get("schema") != TAURI_RUNTIME_SCHEMA:
        failures.append(f"raw Tauri report schema must be {TAURI_RUNTIME_SCHEMA}")
    if report.get("phase") != "katago-live":
        failures.append("raw Tauri report phase must be katago-live")
    if str(report.get("status", "")).lower() != "pass":
        failures.append("raw Tauri report status must be pass")
    return failures


def write_smoke_sgf(path: Path) -> None:
    path.write_text(SMOKE_SGF, encoding="utf-8")


def start_tauri(
    root: Path,
    sgf_path: Path,
    report_path: Path,
    engine: Path,
    model: Path,
    config: Path,
    log_path: Path,
    *,
    max_visits: int,
    game_max_visits: int,
    cancel_max_visits: int,
    cancel_delay_ms: int,
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env.update(
        {
            "VITE_LIZZIEYZY_RUNTIME_SMOKE": "1",
            "LIZZIEYZY_RUNTIME_SMOKE": "1",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_PHASE": "katago-live",
            "LIZZIEYZY_RUNTIME_SMOKE_PHASE": "katago-live",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            "LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_ENGINE_PATH": str(engine),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MODEL_PATH": str(model),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CONFIG_PATH": str(config),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_WORKING_DIR": str(sgf_path.parent),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MAX_VISITS": str(max_visits),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_GAME_MAX_VISITS": str(game_max_visits),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_MAX_VISITS": str(cancel_max_visits),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_DELAY_MS": str(cancel_delay_ms),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_GAME": "1",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_CANCEL": "1",
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_ENGINE_PATH": str(engine),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MODEL_PATH": str(model),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CONFIG_PATH": str(config),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_WORKING_DIR": str(sgf_path.parent),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MAX_VISITS": str(max_visits),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_GAME_MAX_VISITS": str(game_max_visits),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_MAX_VISITS": str(cancel_max_visits),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_DELAY_MS": str(cancel_delay_ms),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_GAME": "1",
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_CANCEL": "1",
        }
    )
    log_file = log_path.open("wb")
    try:
        process = subprocess.Popen(
            ["npm", "--prefix", "apps/desktop", "run", "tauri:dev"],
            cwd=root,
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
    raise SmokeError(f"timed out after {timeout_seconds:g}s waiting for Tauri KataGo runtime report")


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


def write_evidence(path: Path, report: Any, *, root: Path, temp_dir: Path, engine: Path, model: Path, config: Path) -> None:
    replacements = [
        (str(root.resolve()), "<repo>"),
        (str(temp_dir.resolve()), "<tmp>"),
        (str(engine.resolve()), "<katago-engine>"),
        (str(model.resolve()), "<katago-model>"),
        (str(config.resolve()), "<katago-config>"),
    ]
    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize_evidence(report, replacements), indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    normalized = {
        "name": name,
        "status": str(raw.get("status", "")).lower() or "fail",
        "details": details if details is not None else (check_evidence(raw) or {}),
    }
    if isinstance(raw.get("error"), str):
        normalized["error"] = raw["error"]
    return normalized


def build_evidence(raw_report: Any, *, engine: Path, model: Path, config: Path, max_visits: int, timeout_seconds: float) -> dict[str, Any]:
    if not isinstance(raw_report, dict):
        raise SmokeError("raw Tauri report root must be an object")
    raw_failures = validate_raw_tauri_report(raw_report)
    if raw_failures:
        raise SmokeError("; ".join(raw_failures))

    once = check_evidence(runtime_check(raw_report, "katago_analyze_once")) or {}
    game = check_evidence(runtime_check(raw_report, "katago_analyze_game")) or {}
    first_game_frame = game.get("firstFrame") if isinstance(game.get("firstFrame"), dict) else {}
    cancel = check_evidence(runtime_check(raw_report, "katago_start_cancel")) or {}
    failure_mode = check_evidence(runtime_check(raw_report, "katago_failure_mode_missing_assets")) or {}

    checks = [
        normalize_runtime_check(raw_report, "runtime_started"),
        normalize_runtime_check(raw_report, "katago_failure_mode_missing_assets", dict(failure_mode)),
        normalize_runtime_check(
            raw_report,
            "katago_assets",
            {
                "engineExists": engine.exists(),
                "engineExecutable": engine.is_file() and os.access(engine, os.X_OK),
                "modelBytes": model.stat().st_size,
                "configBytes": config.stat().st_size,
            },
        ),
        normalize_runtime_check(
            raw_report,
            "katago_analyze_once",
            {
                "frameCount": 1,
                "candidateCount": once.get("candidates"),
                "visits": once.get("visits"),
                "hasOwnership": once.get("hasOwnership"),
                "hasPolicy": once.get("hasPolicy"),
                "turn": once.get("turn"),
            },
        ),
        normalize_runtime_check(
            raw_report,
            "katago_analyze_game",
            {
                "frameCount": game.get("frames"),
                "candidateCount": first_game_frame.get("candidates"),
                "visits": first_game_frame.get("visits"),
                "turns": game.get("turns"),
            },
        ),
        normalize_runtime_check(
            raw_report,
            "katago_start_cancel",
            {
                "jobId": cancel.get("jobId"),
                "cancelRequested": cancel.get("cancelRequested"),
                "cancelConfirmed": cancel.get("cancelConfirmed"),
                "cancelDelayMs": cancel.get("cancelDelayMs"),
                "event": cancel.get("event"),
            },
        ),
    ]
    return {
        "schema": SCHEMA,
        "name": "katago_tauri_runtime_smoke",
        "status": "pass",
        "platform": "macos" if platform.system() == "Darwin" else platform.system().lower(),
        "phase": "katago-live",
        "engine": {
            "path": str(engine.resolve()),
            "modelPath": str(model.resolve()),
            "configPath": str(config.resolve()),
            "maxVisits": max_visits,
            "timeoutSeconds": timeout_seconds,
        },
        "runtimeReport": {
            "schema": raw_report.get("schema"),
            "phase": raw_report.get("phase"),
            "status": raw_report.get("status"),
            "startedAt": raw_report.get("startedAt"),
            "finishedAt": raw_report.get("finishedAt"),
        },
        "checks": checks,
    }


def run(
    root: Path,
    engine: Path,
    model: Path,
    config: Path,
    *,
    timeout_seconds: float,
    evidence_out: Path | None,
    max_visits: int = 8,
    game_max_visits: int = 8,
    cancel_max_visits: int = 10_000,
    cancel_delay_ms: int = 250,
) -> int:
    root = root.resolve()
    if platform.system() != "Darwin":
        print("Tauri KataGo runtime smoke is currently a macOS local evidence gate.", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"Repository root does not exist: {root}", file=sys.stderr)
        return 2
    for label, path in (("engine", engine), ("model", model), ("config", config)):
        if not path.exists():
            print(f"KataGo {label} path does not exist: {path}", file=sys.stderr)
            return 2

    temp_dir = Path(tempfile.mkdtemp(prefix="lizzieyzy-tauri-katago-smoke-"))
    keep_temp_dir = True
    try:
        sgf_path = temp_dir / "katago-smoke.sgf"
        report_path = temp_dir / "katago-tauri-runtime-report.json"
        log_path = temp_dir / "tauri-dev.log"
        write_smoke_sgf(sgf_path)
        process = start_tauri(
            root,
            sgf_path,
            report_path,
            engine,
            model,
            config,
            log_path,
            max_visits=max_visits,
            game_max_visits=game_max_visits,
            cancel_max_visits=cancel_max_visits,
            cancel_delay_ms=cancel_delay_ms,
        )
        try:
            raw_report = wait_for_report(report_path, process, timeout_seconds=timeout_seconds)
            report = build_evidence(
                raw_report,
                engine=engine,
                model=model,
                config=config,
                max_visits=max_visits,
                timeout_seconds=timeout_seconds,
            )
            failures = validate_report(report)
            if failures:
                raise SmokeError("; ".join(failures))
            if evidence_out is not None:
                write_evidence(evidence_out, report, root=root, temp_dir=temp_dir, engine=engine, model=model, config=config)
            print(f"PASS Tauri KataGo runtime smoke: {len(REQUIRED_CHECKS)} required checks passed")
            keep_temp_dir = False
            return 0
        except SmokeError as exc:
            print(f"FAIL Tauri KataGo runtime smoke: {exc}", file=sys.stderr)
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
    parser = argparse.ArgumentParser(description="Run the macOS Tauri runtime KataGo smoke and validate its JSON report.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--engine", type=Path, required=True, help="KataGo executable path")
    parser.add_argument("--model", type=Path, required=True, help="KataGo model path")
    parser.add_argument("--config", type=Path, required=True, help="KataGo analysis config path")
    parser.add_argument("--timeout", type=float, default=180.0, help="seconds to wait for the runtime report")
    parser.add_argument("--max-visits", type=int, default=8, help="maxVisits for one-position analysis")
    parser.add_argument("--game-max-visits", type=int, default=8, help="maxVisits for full-game analysis")
    parser.add_argument("--cancel-max-visits", type=int, default=10000, help="maxVisits for the cancellable analysis job")
    parser.add_argument("--cancel-delay-ms", type=int, default=250, help="milliseconds to wait before requesting cancellation")
    parser.add_argument("--evidence-out", type=Path, default=ROOT / "docs/qa/katago-tauri-runtime-smoke-macos.json")
    args = parser.parse_args(argv)
    return run(
        args.root,
        args.engine,
        args.model,
        args.config,
        timeout_seconds=args.timeout,
        evidence_out=args.evidence_out,
        max_visits=args.max_visits,
        game_max_visits=args.game_max_visits,
        cancel_max_visits=args.cancel_max_visits,
        cancel_delay_ms=args.cancel_delay_ms,
    )


if __name__ == "__main__":
    raise SystemExit(main())
