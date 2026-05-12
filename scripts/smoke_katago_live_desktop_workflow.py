#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "lizzieyzy.katago-live-desktop-workflow-smoke.v1"
TAURI_RUNTIME_SCHEMA = "lizzieyzy.tauri-runtime-ui-smoke.v1"
DEFAULT_PHASE = "katago-live-workflow-cache"
DEFAULT_EVIDENCE = ROOT / "docs/qa/katago-live-desktop-workflow-smoke-macos.json"
HOMEBREW_KATAGO = Path("/opt/homebrew/bin/katago")
SMOKE_SGF = """(;FF[4]GM[1]CA[UTF-8]AP[LizzieYzyNextKataGoWorkflowSmoke]SZ[9]KM[6.5]PB[Black]PW[White]
;B[dd];W[ee];B[de];W[ed])
"""


REQUIRED_PROOFS = [
    "tauriRuntimeObserved",
    "realKataGoAssetsObserved",
    "analysisProgressObserved",
    "cancelObserved",
    "restartAfterCancelObserved",
    "analysisCompleteObserved",
    "cacheSaved",
    "cacheHitRestored",
    "staleCachePrevented",
    "engineFailureObserved",
]


class SmokeError(RuntimeError):
    pass


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SmokeError(f"runtime report was not created: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeError(f"runtime report is invalid JSON at line {exc.lineno}: {exc.msg}") from exc


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def safe_label(path: Path, marker: str) -> str:
    try:
        resolved = path.resolve()
    except FileNotFoundError:
        resolved = path.absolute()
    suffix = resolved.suffix
    if suffix == ".gz" and resolved.name.endswith(".bin.gz"):
        suffix = ".bin.gz"
    return f"{marker}{suffix}"


def sanitize_value(value: Any, *, temp_dir: Path, engine: Path, model: Path, config: Path) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_value(item, temp_dir=temp_dir, engine=engine, model=model, config=config) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_value(item, temp_dir=temp_dir, engine=engine, model=model, config=config) for item in value]
    if isinstance(value, str):
        replacements = [
            (str(ROOT.resolve()), "<repo>"),
            (str(ROOT), "<repo>"),
            (str(temp_dir.resolve()), "<tmp>"),
            (str(temp_dir), "<tmp>"),
            (str(engine.resolve()), "<katago-engine>") if engine.exists() else (str(engine), "<katago-engine>"),
            (str(model.resolve()), "<katago-model>") if model.exists() else (str(model), "<katago-model>"),
            (str(config.resolve()), "<katago-config>") if config.exists() else (str(config), "<katago-config>"),
        ]
        sanitized = value
        for source, target in sorted(set(replacements), key=lambda item: len(item[0]), reverse=True):
            sanitized = sanitized.replace(source, target)
            if source.startswith("/var/"):
                sanitized = sanitized.replace("/private" + source, target)
        sanitized = re.sub(r"/Users/[^\s\"'<>)]*", "<local-path>", sanitized)
        sanitized = re.sub(r"/opt/homebrew/[^\s\"'<>)]*", "<homebrew-path>", sanitized)
        sanitized = re.sub(r"/private/var/[^\s\"'<>)]*", "<tmp>", sanitized)
        sanitized = re.sub(r"/var/folders/[^\s\"'<>)]*", "<tmp>", sanitized)
        sanitized = re.sub(r"/tmp/[^\s\"'<>)]*", "<tmp>", sanitized)
        sanitized = re.sub(r"~[/\\][^\s\"'<>)]*", "<home>", sanitized)
        return sanitized
    return value


def write_evidence(path: Path, evidence: dict[str, Any], *, temp_dir: Path, engine: Path, model: Path, config: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = sanitize_value(evidence, temp_dir=temp_dir, engine=engine, model=model, config=config)
    path.write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def env_path(*names: str) -> Path | None:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return Path(value).expanduser()
    return None


def find_default_engine() -> Path:
    env = env_path("KATAGO_ENGINE_PATH", "LIZZIEYZY_KATAGO_ENGINE_PATH")
    if env is not None:
        return env
    located = shutil.which("katago")
    if located:
        return Path(located)
    return HOMEBREW_KATAGO


def find_default_model() -> Path:
    env = env_path("KATAGO_MODEL_PATH", "LIZZIEYZY_KATAGO_MODEL_PATH")
    if env is not None:
        return env
    model_dir = Path.home() / ".katago/models"
    models = sorted(model_dir.glob("*.bin.gz")) if model_dir.is_dir() else []
    return models[0] if models else model_dir / "model.bin.gz"


def find_default_config() -> Path:
    env = env_path("KATAGO_CONFIG_PATH", "LIZZIEYZY_KATAGO_CONFIG_PATH")
    if env is not None:
        return env
    config_dir = Path.home() / ".katago/configs"
    preferred = config_dir / "analysis_example.cfg"
    if preferred.is_file():
        return preferred
    configs = sorted(config_dir.glob("*.cfg")) if config_dir.is_dir() else []
    return configs[0] if configs else preferred


def phase_supported(phase: str) -> tuple[bool, str]:
    runtime_smoke = ROOT / "apps/desktop/src/runtimeSmoke.ts"
    if not runtime_smoke.is_file():
        return False, "apps/desktop/src/runtimeSmoke.ts is missing"
    text = runtime_smoke.read_text(encoding="utf-8")
    if phase not in text:
        return False, f"runtimeSmoke.ts does not yet declare or handle phase {phase}"
    expected_tokens = [
        "cache",
        "restart",
        "stale",
        "engine",
        "progress",
    ]
    missing = [token for token in expected_tokens if token.lower() not in text.lower()]
    if missing:
        return False, "runtimeSmoke.ts phase appears incomplete for workflow/cache proof tokens: " + ", ".join(missing)
    return True, f"runtimeSmoke.ts declares {phase}"


def write_smoke_sgf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SMOKE_SGF, encoding="utf-8")


def start_tauri(
    *,
    phase: str,
    sgf_path: Path,
    report_path: Path,
    cache_dir: Path,
    engine: Path,
    model: Path,
    config: Path,
    log_path: Path,
    max_visits: int,
    cancel_max_visits: int,
    cancel_delay_ms: int,
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env.update(
        {
            "VITE_LIZZIEYZY_RUNTIME_SMOKE": "1",
            "LIZZIEYZY_RUNTIME_SMOKE": "1",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_PHASE": phase,
            "LIZZIEYZY_RUNTIME_SMOKE_PHASE": phase,
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            "LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_ENGINE_PATH": str(engine),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_ENGINE_PATH": str(engine),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MODEL_PATH": str(model),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MODEL_PATH": str(model),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CONFIG_PATH": str(config),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CONFIG_PATH": str(config),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_WORKING_DIR": str(sgf_path.parent),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_WORKING_DIR": str(sgf_path.parent),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MAX_VISITS": str(max_visits),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MAX_VISITS": str(max_visits),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_GAME_MAX_VISITS": str(max_visits),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_GAME_MAX_VISITS": str(max_visits),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_MAX_VISITS": str(cancel_max_visits),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_MAX_VISITS": str(cancel_max_visits),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_DELAY_MS": str(cancel_delay_ms),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_DELAY_MS": str(cancel_delay_ms),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_GAME": "1",
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_GAME": "1",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_CANCEL": "1",
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_CANCEL": "1",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CACHE_DIR": str(cache_dir),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CACHE_DIR": str(cache_dir),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_WORKFLOW_CACHE_DIR": str(cache_dir),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_WORKFLOW_CACHE_DIR": str(cache_dir),
        }
    )
    log_file = log_path.open("wb")
    try:
        process = subprocess.Popen(
            ["npm", "--prefix", "apps/desktop", "run", "tauri:dev"],
            cwd=ROOT,
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


def wait_for_report(report_path: Path, process: subprocess.Popen[bytes], timeout_seconds: float) -> Any:
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
    raise SmokeError(f"timed out after {timeout_seconds:g}s waiting for runtime smoke report")


def positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and value > 0


def check_by_name(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks = report.get("checks")
    if not isinstance(checks, list):
        return {}
    return {
        str(check.get("name")): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }


def check_details(report: dict[str, Any], *names: str) -> dict[str, Any]:
    checks = check_by_name(report)
    for name in names:
        check = checks.get(name)
        if isinstance(check, dict):
            details = check.get("details")
            if isinstance(details, dict):
                return details
            evidence = check.get("evidence")
            if isinstance(evidence, dict):
                return evidence
    return {}


def check_passed(report: dict[str, Any], *names: str) -> bool:
    checks = check_by_name(report)
    for name in names:
        check = checks.get(name)
        if isinstance(check, dict) and str(check.get("status", "")).lower() == "pass":
            return True
    return False


def workflow_sections(report: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = [report]
    for key in (
        "katagoLiveWorkflow",
        "katagoLiveWorkflowCache",
        "katagoWorkflow",
        "katagoWorkflowCache",
        "katagoCacheWorkflow",
        "katago",
    ):
        value = report.get(key)
        if isinstance(value, dict):
            sections.append(value)
    return sections


def find_bool(report: dict[str, Any], keys: tuple[str, ...], checks: tuple[str, ...] = ()) -> bool:
    for section in workflow_sections(report):
        for key in keys:
            if section.get(key) is True:
                return True
    for name in checks:
        details = check_details(report, name)
        if details:
            for key in keys:
                if details.get(key) is True:
                    return True
            if str(check_by_name(report).get(name, {}).get("status", "")).lower() == "pass":
                return True
    return False


def proof_booleans(report: dict[str, Any], *, engine: Path, model: Path, config: Path) -> dict[str, bool]:
    asset_details = check_details(report, "katago_assets", "katago_live_assets", "katago_real_assets", "engine_assets_verified")
    local_assets = engine.exists() and model.is_file() and config.is_file() and os.access(engine, os.X_OK)
    assets_from_report = (
        (
            asset_details.get("engineExecutable") is True
            and positive_number(asset_details.get("modelBytes") or asset_details.get("modelSizeBytes"))
            and positive_number(asset_details.get("configBytes") or asset_details.get("configSizeBytes"))
        )
        or (
            asset_details.get("missingRequired") == []
            and positive_number(asset_details.get("required"))
            and positive_number(asset_details.get("total"))
        )
    )
    return {
        "tauriRuntimeObserved": find_bool(report, ("tauriRuntimeObserved", "tauriInternals"), ("runtime_started",)),
        "realKataGoAssetsObserved": assets_from_report and local_assets,
        "analysisProgressObserved": find_bool(
            report,
            ("analysisProgressObserved", "progressObserved", "progressEventObserved"),
            ("analysis_progress_observed", "katago_analysis_progress", "katago_analysis_progress_observed", "katago_progress_observed"),
        ),
        "cancelObserved": find_bool(
            report,
            ("cancelObserved", "cancelConfirmed", "analysisCancelObserved"),
            ("cancel_observed", "katago_cancel_observed", "katago_start_cancel", "katago_analysis_cancelled"),
        ),
        "restartAfterCancelObserved": find_bool(
            report,
            ("restartAfterCancelObserved", "restartObserved", "restartedAfterCancel"),
            ("restart_after_cancel_observed", "katago_restart_after_cancel", "katago_restart_after_cancel_observed"),
        ),
        "analysisCompleteObserved": find_bool(
            report,
            ("analysisCompleteObserved", "completeObserved", "analysisCompleted"),
            ("analysis_complete_observed", "katago_analysis_complete", "katago_analysis_complete_observed"),
        ),
        "cacheSaved": find_bool(report, ("cacheSaved", "analysisCacheSaved"), ("cache_saved", "katago_cache_saved", "analysis_cache_saved")),
        "cacheHitRestored": find_bool(
            report,
            ("cacheHitRestored", "cacheRestored", "analysisCacheHitRestored"),
            ("cache_hit_restored", "katago_cache_hit_restored", "analysis_cache_hit_restored"),
        ),
        "staleCachePrevented": find_bool(
            report,
            ("staleCachePrevented", "staleCacheRejected", "staleCacheNotRestored"),
            ("stale_cache_prevented", "katago_stale_cache_prevented", "analysis_stale_cache_prevented"),
        ),
        "engineFailureObserved": find_bool(
            report,
            ("engineFailureObserved", "structuredEngineFailureObserved", "missingAssetFailureObserved"),
            ("engine_failure_observed", "katago_engine_failure_observed", "katago_failure_mode_missing_assets", "katago_missing_asset_failure"),
        ),
        "browserFallbackUsed": any(section.get("browserFallbackUsed") is True for section in workflow_sections(report)),
    }


def asset_evidence(engine: Path, model: Path, config: Path) -> dict[str, Any]:
    return {
        "engine": {
            "path": safe_label(engine, "<katago-engine>"),
            "exists": engine.exists(),
            "executable": engine.exists() and os.access(engine, os.X_OK),
            "sha256": sha256_file(engine) if engine.is_file() else None,
            "bytes": engine.stat().st_size if engine.is_file() else None,
        },
        "model": {
            "path": safe_label(model, "<katago-model>"),
            "exists": model.is_file(),
            "sha256": sha256_file(model) if model.is_file() else None,
            "bytes": model.stat().st_size if model.is_file() else None,
        },
        "config": {
            "path": safe_label(config, "<katago-config>"),
            "exists": config.is_file(),
            "sha256": sha256_file(config) if config.is_file() else None,
            "bytes": config.stat().st_size if config.is_file() else None,
        },
    }


def validate_final(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if evidence.get("schema") != SCHEMA:
        failures.append(f"schema must be {SCHEMA}")
    if evidence.get("status") != "pass":
        failures.append("status must be pass")
    if evidence.get("platform") not in ("macos", "darwin"):
        failures.append("platform must be macos/darwin")
    if evidence.get("sourceRuntimeReport", {}).get("schema") != TAURI_RUNTIME_SCHEMA:
        failures.append(f"sourceRuntimeReport.schema must be {TAURI_RUNTIME_SCHEMA}")
    if evidence.get("sourceRuntimeReport", {}).get("phase") != evidence.get("phase"):
        failures.append("sourceRuntimeReport.phase must match phase")
    if evidence.get("sourceRuntimeReport", {}).get("status") != "pass":
        failures.append("sourceRuntimeReport.status must be pass")
    proofs = evidence.get("proofs")
    if not isinstance(proofs, dict):
        return failures + ["proofs must be an object"]
    for key in REQUIRED_PROOFS:
        if proofs.get(key) is not True:
            failures.append(f"{key} must be true")
    if proofs.get("browserFallbackUsed") is not False:
        failures.append("browserFallbackUsed must be false")
    boundaries = evidence.get("boundaries")
    if not isinstance(boundaries, dict):
        failures.append("boundaries must be an object")
    else:
        for key in ("fullLegacyAnalysisParity", "providerReadboardParity", "releaseParity", "arbitraryOcrParity"):
            if boundaries.get(key) is not False:
                failures.append(f"boundaries.{key} must be false")
    return failures


def build_evidence(
    *,
    raw_report: dict[str, Any],
    phase: str,
    temp_dir: Path,
    report_path: Path,
    log_path: Path,
    launch: dict[str, Any],
    engine: Path,
    model: Path,
    config: Path,
    started_at: str,
) -> dict[str, Any]:
    proofs = proof_booleans(raw_report, engine=engine, model=model, config=config)
    failures: list[str] = []
    if raw_report.get("schema") != TAURI_RUNTIME_SCHEMA:
        failures.append(f"raw runtime schema must be {TAURI_RUNTIME_SCHEMA}")
    if raw_report.get("phase") != phase:
        failures.append(f"raw runtime phase must be {phase}")
    if str(raw_report.get("status", "")).lower() != "pass":
        failures.append("raw runtime status must be pass")
    missing = [key for key in REQUIRED_PROOFS if proofs.get(key) is not True]
    if missing:
        failures.append("missing required workflow proofs: " + ", ".join(missing))
    if proofs.get("browserFallbackUsed") is not False:
        failures.append("browserFallbackUsed must be false")
    status = "pass" if not failures else "fail"
    evidence = {
        "schema": SCHEMA,
        "name": "katago_live_desktop_workflow_smoke",
        "status": status,
        "platform": "macos" if platform.system() == "Darwin" else platform.system().lower(),
        "phase": phase,
        "collectionMethod": "tauri-dev-runtime-smoke-katago-live-workflow-cache",
        "startedAt": started_at,
        "finishedAt": utc_now(),
        "assets": asset_evidence(engine, model, config),
        "proofs": proofs,
        "checks": [
            {"name": key, "status": "pass" if proofs.get(key) is True else "fail", "details": {"observed": proofs.get(key)}}
            for key in REQUIRED_PROOFS
        ] + [{"name": "browser_fallback_excluded", "status": "pass" if proofs.get("browserFallbackUsed") is False else "fail", "details": {"browserFallbackUsed": proofs.get("browserFallbackUsed")}}],
        "sourceRuntimeReport": {
            "path": str(report_path),
            "schema": raw_report.get("schema"),
            "status": raw_report.get("status"),
            "phase": raw_report.get("phase"),
            "name": raw_report.get("name"),
            "startedAt": raw_report.get("startedAt"),
            "finishedAt": raw_report.get("finishedAt"),
        },
        "runtimeReport": raw_report,
        "launch": {
            **launch,
            "logPath": str(log_path),
            "reportPath": str(report_path),
            "cacheDir": str(temp_dir / "katago-cache"),
        },
        "boundaries": {
            "fullLegacyAnalysisParity": False,
            "providerReadboardParity": False,
            "releaseParity": False,
            "arbitraryOcrParity": False,
            "browserFallbackUsed": False,
        },
        "failures": failures,
    }
    final_failures = validate_final(evidence) if status == "pass" else []
    if final_failures:
        evidence["status"] = "fail"
        evidence["failures"] = failures + final_failures
    return evidence


def blocked_evidence(reason: str, *, phase: str, temp_dir: Path, engine: Path, model: Path, config: Path) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "name": "katago_live_desktop_workflow_smoke",
        "status": "blocked",
        "platform": "macos" if platform.system() == "Darwin" else platform.system().lower(),
        "phase": phase,
        "collectionMethod": "tauri-dev-runtime-smoke-katago-live-workflow-cache",
        "startedAt": utc_now(),
        "finishedAt": utc_now(),
        "assets": asset_evidence(engine, model, config),
        "proofs": {key: False for key in REQUIRED_PROOFS} | {"browserFallbackUsed": False},
        "checks": [],
        "sourceRuntimeReport": None,
        "runtimeReport": None,
        "launch": {
            "skipped": True,
            "stopped": True,
            "command": "npm --prefix apps/desktop run tauri:dev",
            "reason": reason,
        },
        "boundaries": {
            "fullLegacyAnalysisParity": False,
            "providerReadboardParity": False,
            "releaseParity": False,
            "arbitraryOcrParity": False,
            "browserFallbackUsed": False,
        },
        "blocker": reason,
        "failures": [reason],
    }


def run(args: argparse.Namespace) -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="lizzieyzy-katago-live-desktop-workflow-"))
    engine = args.engine if args.engine is not None else find_default_engine()
    model = args.model if args.model is not None else find_default_model()
    config = args.config if args.config is not None else find_default_config()
    evidence_path = args.evidence_out
    phase = args.phase

    asset_blockers = []
    if not engine.exists() or not os.access(engine, os.X_OK):
        asset_blockers.append(f"KataGo engine is missing or not executable: {engine}")
    if not model.is_file():
        asset_blockers.append(f"KataGo model is missing: {model}")
    if not config.is_file():
        asset_blockers.append(f"KataGo config is missing: {config}")
    supported, reason = phase_supported(phase)
    if asset_blockers or (not supported and not args.force):
        blocker = "; ".join(asset_blockers) if asset_blockers else reason
        evidence = blocked_evidence(blocker, phase=phase, temp_dir=temp_dir, engine=engine, model=model, config=config)
        write_evidence(evidence_path, evidence, temp_dir=temp_dir, engine=engine, model=model, config=config)
        print(f"BLOCKED KataGo live desktop workflow smoke: {blocker}", file=sys.stderr)
        print(f"wrote {repo_relative(evidence_path)}", file=sys.stderr)
        return 2

    sgf_path = temp_dir / "katago-live-workflow.sgf"
    report_path = temp_dir / "runtime-report.json"
    log_path = temp_dir / "tauri-dev.log"
    cache_dir = temp_dir / "katago-cache"
    write_smoke_sgf(sgf_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    launch: dict[str, Any] = {
        "command": "npm --prefix apps/desktop run tauri:dev",
        "phase": phase,
        "pid": None,
        "startedAt": started_at,
        "stopped": False,
        "sgfPath": str(sgf_path),
    }
    process: subprocess.Popen[bytes] | None = None
    try:
        process = start_tauri(
            phase=phase,
            sgf_path=sgf_path,
            report_path=report_path,
            cache_dir=cache_dir,
            engine=engine,
            model=model,
            config=config,
            log_path=log_path,
            max_visits=args.max_visits,
            cancel_max_visits=args.cancel_max_visits,
            cancel_delay_ms=args.cancel_delay_ms,
        )
        launch["pid"] = process.pid
        raw_report = wait_for_report(report_path, process, args.timeout)
        evidence = build_evidence(
            raw_report=raw_report,
            phase=phase,
            temp_dir=temp_dir,
            report_path=report_path,
            log_path=log_path,
            launch=launch,
            engine=engine,
            model=model,
            config=config,
            started_at=started_at,
        )
        return_code = 0 if evidence["status"] == "pass" else 1
    except Exception as exc:
        evidence = blocked_evidence(str(exc), phase=phase, temp_dir=temp_dir, engine=engine, model=model, config=config)
        evidence["status"] = "fail"
        evidence["launch"] = {
            **launch,
            "logPath": str(log_path),
            "reportPath": str(report_path),
            "cacheDir": str(cache_dir),
        }
        return_code = 1
    finally:
        if process is not None:
            stop_process(process)
            launch["stopped"] = True
            launch["exitCode"] = process.poll()
            launch["stoppedAt"] = utc_now()
            evidence["launch"] = {
                **(evidence.get("launch") if isinstance(evidence.get("launch"), dict) else {}),
                **launch,
                "logPath": str(log_path),
                "reportPath": str(report_path),
                "cacheDir": str(cache_dir),
            }
    write_evidence(evidence_path, evidence, temp_dir=temp_dir, engine=engine, model=model, config=config)
    if return_code == 0:
        print(f"PASS KataGo live desktop workflow smoke: wrote {repo_relative(evidence_path)}")
    else:
        prefix = "BLOCKED" if evidence.get("status") == "blocked" else "FAIL"
        print(f"{prefix} KataGo live desktop workflow smoke: wrote {repo_relative(evidence_path)}", file=sys.stderr)
        for failure in evidence.get("failures", []):
            print(f"- {failure}", file=sys.stderr)
    return return_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the scoped macOS Tauri KataGo live workflow/cache smoke.")
    parser.add_argument("--phase", default=DEFAULT_PHASE, help="runtime smoke phase to request")
    parser.add_argument("--engine", type=Path, default=None, help="KataGo executable path; defaults to env or PATH")
    parser.add_argument("--model", type=Path, default=None, help="KataGo model path; defaults to env or ~/.katago/models/*.bin.gz")
    parser.add_argument("--config", type=Path, default=None, help="KataGo analysis config path; defaults to env or ~/.katago/configs/*.cfg")
    parser.add_argument("--timeout", type=float, default=360.0, help="seconds to wait for the runtime report")
    parser.add_argument("--max-visits", type=int, default=8, help="max visits for short workflow analysis")
    parser.add_argument("--cancel-max-visits", type=int, default=160, help="max visits for cancellable analysis")
    parser.add_argument("--cancel-delay-ms", type=int, default=250, help="milliseconds before requesting cancellation")
    parser.add_argument("--evidence-out", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--force", action="store_true", help="launch even if runtimeSmoke.ts preflight cannot see the phase")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
