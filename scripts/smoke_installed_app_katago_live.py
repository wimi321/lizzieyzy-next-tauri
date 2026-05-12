#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
from smoke_installed_app_sgf_workflow import derive_executable_path, installed_screenshot, runtime_process  # noqa: E402


SCHEMA = "lizzieyzy.installed-app-katago-live-workflow.v1"
DEFAULT_EVIDENCE_OUT = "docs/qa/installed-app-katago-live-workflow-macos.json"
PHASE = "installed-app-katago-live-workflow"
SMOKE_SGF = """(;FF[4]GM[1]SZ[19]PB[Black]PW[White]KM[7.5]
;B[pd];W[dd];B[qp];W[dp];B[cn];W[fq];B[fc];W[cf];B[qf];W[oc]
;B[pm];W[eq];B[jd];W[ce];B[ck];W[dc];B[qq];W[do];B[co];W[dn])
"""


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def path_arg(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        sanitized = re.sub(r"/private/var/folders/[^\s\"']+", "<tmp>", sanitized)
        sanitized = re.sub(r"/var/folders/[^\s\"']+", "<tmp>", sanitized)
        sanitized = re.sub(r"/tmp/[^\s\"']+", "<tmp>", sanitized)
        return sanitized
    return value


def find_existing(candidates: list[str]) -> Path | None:
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file():
            return path
    return None


def resolve_asset(explicit: str | None, candidates: list[str], label: str) -> Path:
    path = path_arg(explicit) if explicit else find_existing(candidates)
    if path is None or not path.is_file():
        raise ValueError(f"real KataGo {label} asset is required")
    return path


def executable_from_path_or_path_env(explicit: str | None) -> Path:
    if explicit:
        path = path_arg(explicit)
        if path.is_file():
            return path
        raise ValueError(f"KataGo engine executable does not exist: {path}")
    path_env = os.environ.get("PATH", "")
    for directory in path_env.split(os.pathsep):
        candidate = Path(directory) / "katago"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    fallback = Path("~/Developer/lizzyzy-youhua/engines/katago").expanduser()
    if fallback.is_file():
        return fallback
    raise ValueError("real KataGo engine executable is required")


def asset_metadata(path: Path, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": sanitize(str(path)),
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def pass_check(name: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass", "details": details}


def check_by_name(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks = report.get("checks")
    if not isinstance(checks, list):
        return {}
    return {
        check["name"]: check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }


def check_details(report: dict[str, Any], name: str) -> dict[str, Any]:
    check = check_by_name(report).get(name)
    if not isinstance(check, dict) or str(check.get("status", "")).lower() != "pass":
        raise ValueError(f"runtime report missing PASS check {name}")
    details = check.get("details") if isinstance(check.get("details"), dict) else check.get("evidence")
    if not isinstance(details, dict):
        raise ValueError(f"runtime report check {name} must include object details")
    return details


def boundaries() -> dict[str, bool]:
    return {
        "fullKataGoParity": False,
        "bundledLargeModelParity": False,
        "releaseParity": False,
        "signedReleaseParity": False,
        "windowsLinuxParity": False,
        "fullLegacyParity": False,
        "providerParity": False,
        "readboardParity": False,
        "ocrParity": False,
    }


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


def run_packaged_app_runtime_report(
    installed_smoke: dict[str, Any],
    *,
    app_executable: str | None,
    engine_path: Path,
    model_path: Path,
    config_path: Path,
    max_visits: int,
    timeout_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    executable = derive_executable_path(installed_smoke, app_executable)
    if not executable.is_file():
        raise ValueError(f"installed app executable does not exist: {executable}")
    with tempfile.TemporaryDirectory(prefix="lizzieyzy-installed-katago-") as tmp:
        temp_dir = Path(tmp)
        report_path = temp_dir / "installed-app-katago-live-report.json"
        log_path = temp_dir / "installed-app-katago-live.log"
        sgf_path = temp_dir / "installed-app-katago-live.sgf"
        working_dir = temp_dir / "katago-working-dir"
        sgf_path.write_text(SMOKE_SGF, encoding="utf-8")
        working_dir.mkdir(parents=True, exist_ok=True)
        cancel_max_visits = max(64, max_visits * 8)
        cancel_delay_ms = 250
        env = os.environ.copy()
        smoke_env = {
            "LIZZIEYZY_RUNTIME_SMOKE": "1",
            "LIZZIEYZY_RUNTIME_SMOKE_PHASE": PHASE,
            "LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            "LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_ENGINE_PATH": str(engine_path),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MODEL_PATH": str(model_path),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CONFIG_PATH": str(config_path),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_WORKING_DIR": str(working_dir),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MAX_VISITS": str(max_visits),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_GAME_MAX_VISITS": str(max_visits),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_MAX_VISITS": str(cancel_max_visits),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_DELAY_MS": str(cancel_delay_ms),
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_GAME": "1",
            "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_CANCEL": "1",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE": "1",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_PHASE": PHASE,
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_ENGINE_PATH": str(engine_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MODEL_PATH": str(model_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CONFIG_PATH": str(config_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_WORKING_DIR": str(working_dir),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MAX_VISITS": str(max_visits),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_GAME_MAX_VISITS": str(max_visits),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_MAX_VISITS": str(cancel_max_visits),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_DELAY_MS": str(cancel_delay_ms),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_GAME": "1",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_CANCEL": "1",
        }
        env.update(smoke_env)
        log_file = log_path.open("wb")
        process = subprocess.Popen(
            [str(executable)],
            cwd=ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        launch = {"executable": str(executable), "pid": process.pid, "phase": PHASE}
        try:
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                if report_path.is_file():
                    return load_json(report_path), launch
                if process.poll() is not None:
                    break
                time.sleep(0.25)
            log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:] if log_path.is_file() else ""
            raise ValueError(f"installed app live KataGo workflow report was not created at {report_path}; log tail: {log_tail}")
        finally:
            log_file.close()
            stop_process(process)


def build_evidence(
    installed_smoke: dict[str, Any],
    runtime_report: dict[str, Any],
    *,
    runtime_metadata: dict[str, Any],
) -> dict[str, Any]:
    installed_failures = smoke_user_flows.validate_installed_macos_app_smoke_evidence(installed_smoke)
    if installed_failures:
        raise ValueError("installed app smoke evidence is invalid: " + "; ".join(installed_failures))
    runtime = sanitize(runtime_report)
    runtime_failures = smoke_user_flows.validate_installed_app_katago_live_runtime_report(runtime)
    if runtime_failures:
        raise ValueError("installed app live KataGo runtime report is invalid: " + "; ".join(runtime_failures))
    metadata = sanitize(runtime_metadata)
    metadata_failures = smoke_user_flows.validate_installed_app_katago_live_runtime_metadata(metadata)
    if metadata_failures:
        raise ValueError("installed app live KataGo runtime metadata is invalid: " + "; ".join(metadata_failures))

    screenshot = installed_screenshot(installed_smoke)
    screenshot["source"] = "installed_app_katago_live_workflow"
    asset_details = {
        "realKataGoObserved": True,
        "observed": True,
        "engine": metadata["engine"],
        "model": metadata["model"],
        "config": metadata["config"],
        "maxVisits": metadata["maxVisits"],
        "katagoVersion": metadata["katagoVersion"],
        "missingRequired": [],
    }
    boundary_values = boundaries()
    checks = [
        pass_check("installed_app_launched", {"installedAppLaunched": True, "appBundlePath": installed_smoke.get("appBundlePath")}),
        pass_check("runtime_report_observed", {"phase": runtime.get("phase"), "status": runtime.get("status"), "liveKataGoObserved": True}),
        pass_check("runtime_started", check_details(runtime, "runtime_started")),
        pass_check("engine_assets_verified", asset_details),
        pass_check("analysis_progress_observed", check_details(runtime, "analysis_progress_observed")),
        pass_check("cancel_observed", check_details(runtime, "cancel_observed")),
        pass_check("restart_after_cancel_observed", check_details(runtime, "restart_after_cancel_observed")),
        pass_check("analysis_complete_observed", check_details(runtime, "analysis_complete_observed")),
        pass_check("cache_saved", check_details(runtime, "cache_saved")),
        pass_check("cache_hit_restored", check_details(runtime, "cache_hit_restored")),
        pass_check("stale_cache_prevented", check_details(runtime, "stale_cache_prevented")),
        pass_check("engine_failure_observed", check_details(runtime, "engine_failure_observed")),
        pass_check("browser_fallback_excluded", {"browserFallbackUsed": False}),
        pass_check("screenshot_hash_recorded", screenshot),
        pass_check("scope_boundaries_recorded", {"boundaries": boundary_values}),
    ]
    evidence = {
        "schema": SCHEMA,
        "name": "installed_app_katago_live_workflow",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "installed_packaged_app_live_katago_runtime_workflow",
        "runtimePhase": PHASE,
        "installedAppLaunched": True,
        "tauriRuntimeObserved": True,
        "liveKataGoObserved": True,
        "sourceStaticOnly": False,
        "browserFallbackUsed": False,
        "devServerOnly": False,
        **boundary_values,
        "appBundlePath": installed_smoke.get("appBundlePath"),
        "appBundle": installed_smoke.get("appBundle"),
        "runtimeProcess": runtime_process(installed_smoke),
        "runtimeMetadata": metadata,
        "sourceRuntimeReport": runtime,
        "screenshots": [screenshot],
        "checks": checks,
        "boundaries": boundary_values,
    }
    failures = smoke_user_flows.validate_installed_app_katago_live_workflow_evidence(evidence)
    if failures:
        raise ValueError("installed app live KataGo workflow evidence is invalid: " + "; ".join(failures))
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch packaged macOS app and aggregate live KataGo workflow proof.")
    parser.add_argument("--installed-app-smoke", required=True)
    parser.add_argument("--app-executable")
    parser.add_argument("--katago-engine")
    parser.add_argument("--katago-model")
    parser.add_argument("--katago-config")
    parser.add_argument("--max-visits", type=int, default=16)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--evidence-out", default=DEFAULT_EVIDENCE_OUT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    output_path = path_arg(args.evidence_out)
    if args.validate_only and output_path.is_file():
        failures = smoke_user_flows.validate_installed_app_katago_live_workflow_evidence(load_json(output_path))
        if failures:
            raise SystemExit("installed app live KataGo workflow evidence is invalid: " + "; ".join(failures))
        print("installed app live KataGo workflow evidence is valid")
        return 0

    installed_smoke = load_json(path_arg(args.installed_app_smoke))
    engine_path = executable_from_path_or_path_env(args.katago_engine)
    model_path = resolve_asset(args.katago_model, ["~/.katago/models/latest-kata1.bin.gz"], "model")
    config_path = resolve_asset(
        args.katago_config,
        ["~/.katago/configs/analysis_example.cfg", "~/.katago/configs/gtp_example.cfg"],
        "config",
    )
    metadata = {
        "engine": asset_metadata(engine_path, "katago-engine"),
        "model": asset_metadata(model_path, "katago-model"),
        "config": asset_metadata(config_path, "katago-config"),
        "maxVisits": args.max_visits,
        "katagoVersion": subprocess.run(
            [str(engine_path), "version"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
        ).stdout.strip(),
    }
    runtime_report, launch = run_packaged_app_runtime_report(
        installed_smoke,
        app_executable=args.app_executable,
        engine_path=engine_path,
        model_path=model_path,
        config_path=config_path,
        max_visits=args.max_visits,
        timeout_seconds=args.timeout_seconds,
    )
    evidence = build_evidence(installed_smoke, runtime_report, runtime_metadata=metadata)
    evidence["packagedAppLaunch"] = sanitize(launch)
    if args.validate_only:
        print("installed app live KataGo workflow evidence is valid")
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
