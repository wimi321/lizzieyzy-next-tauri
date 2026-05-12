#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "lizzieyzy.tauri-webview-dom-click-smoke.v1"
RUNTIME_SCHEMA = "lizzieyzy.tauri-runtime-ui-smoke.v1"
PHASE = "webview-dom-click"
DEFAULT_EVIDENCE = ROOT / "docs/qa/tauri-webview-dom-click-smoke-macos.json"
SCREENSHOT_DIR = ROOT / "docs/qa/screenshots"
SMOKE_SGF = "(;FF[4]GM[1]SZ[19]C[tauri webview dom click smoke];B[dd];W[qq])\n"


class SmokeError(Exception):
    pass


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def sanitize_value(value: Any, *, temp_dir: Path) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_value(item, temp_dir=temp_dir) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_value(item, temp_dir=temp_dir) for item in value]
    if isinstance(value, str):
        replacements = [
            (str(ROOT.resolve()), "<repo>"),
            (str(ROOT), "<repo>"),
            (str(temp_dir.resolve()), "<tmp>"),
            (str(temp_dir), "<tmp>"),
        ]
        sanitized = value
        for source, target in sorted(set(replacements), key=lambda item: len(item[0]), reverse=True):
            sanitized = sanitized.replace(source, target)
            if source.startswith("/var/"):
                sanitized = sanitized.replace("/private" + source, target)
        sanitized = re.sub(r"/Users/[^\s\"'<>)]*", "<local-path>", sanitized)
        sanitized = re.sub(r"/private/var/[^\s\"'<>)]*", "<tmp>", sanitized)
        sanitized = re.sub(r"/var/folders/[^\s\"'<>)]*", "<tmp>", sanitized)
        sanitized = re.sub(r"/tmp/[^\s\"'<>)]*", "<tmp>", sanitized)
        sanitized = re.sub(r"~[/\\][^\s\"'<>)]*", "<home>", sanitized)
        return sanitized
    return value


def write_evidence(path: Path, evidence: dict[str, Any], *, temp_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = sanitize_value(evidence, temp_dir=temp_dir)
    path.write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def phase_supported() -> tuple[bool, str]:
    runtime_smoke = ROOT / "apps/desktop/src/runtimeSmoke.ts"
    if not runtime_smoke.is_file():
        return False, "apps/desktop/src/runtimeSmoke.ts is missing"
    text = runtime_smoke.read_text(encoding="utf-8")
    if PHASE not in text:
        return False, "runtimeSmoke.ts does not yet declare or handle phase webview-dom-click"
    if "webviewDomClick" not in text or "clickedControls" not in text or "visibleTargets" not in text:
        return False, "runtimeSmoke.ts phase is present but DOM/click evidence fields were not found"
    return True, "runtimeSmoke.ts declares webview-dom-click DOM/click evidence"


def write_sgf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SMOKE_SGF, encoding="utf-8")


def start_tauri(sgf_path: Path, report_path: Path, log_path: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env.update(
        {
            "VITE_LIZZIEYZY_RUNTIME_SMOKE": "1",
            "LIZZIEYZY_RUNTIME_SMOKE": "1",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_PHASE": PHASE,
            "LIZZIEYZY_RUNTIME_SMOKE_PHASE": PHASE,
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            "LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
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


def check_by_name(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks = report.get("checks")
    if not isinstance(checks, list):
        return {}
    return {
        str(check.get("name")): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }


def check_details(report: dict[str, Any], name: str) -> dict[str, Any]:
    check = check_by_name(report).get(name)
    if not isinstance(check, dict):
        return {}
    details = check.get("details")
    return details if isinstance(details, dict) else {}


def bool_from_report(report: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = report.get(key)
        if isinstance(value, bool):
            return value
    webview = report.get("webviewDomClick")
    if isinstance(webview, dict):
        for key in keys:
            value = webview.get(key)
            if isinstance(value, bool):
                return value
    for check in check_by_name(report).values():
        details = check.get("details")
        if isinstance(details, dict):
            for key in keys:
                value = details.get(key)
                if isinstance(value, bool):
                    return value
    return False


def list_from_report(report: dict[str, Any], key: str, fallback_check: str | None = None) -> list[Any]:
    value = report.get(key)
    if isinstance(value, list):
        return value
    webview = report.get("webviewDomClick")
    if isinstance(webview, dict):
        value = webview.get(key)
        if isinstance(value, list):
            return value
    if fallback_check is not None:
        details = check_details(report, fallback_check)
        value = details.get(key)
        if isinstance(value, list):
            return value
    return []


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def collect_screenshots(report: dict[str, Any], *, temp_dir: Path) -> list[dict[str, Any]]:
    screenshots: list[dict[str, Any]] = []
    raw = report.get("screenshots")
    if not isinstance(raw, list):
        return screenshots
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            continue
        source = Path(raw_path)
        if not source.is_absolute():
            source = ROOT / source
        if not source.is_file():
            continue
        suffix = source.suffix or ".png"
        dest = SCREENSHOT_DIR / f"tauri-webview-dom-{index + 1}{suffix}"
        shutil.copyfile(source, dest)
        screenshots.append(
            {
                "path": repo_relative(dest),
                "sha256": sha256_file(dest),
                "bytes": dest.stat().st_size,
                "sourcePath": sanitize_value(str(source), temp_dir=temp_dir),
            }
        )
    return screenshots


def adapt_runtime_report(
    report: Any,
    *,
    temp_dir: Path,
    temp_report_path: Path,
    log_path: Path,
    launch: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise SmokeError("runtime report root must be an object")
    screenshots = collect_screenshots(report, temp_dir=temp_dir)
    visible_assertions = list_from_report(report, "visibleAssertions", "webview_dom_assertions")
    if not visible_assertions:
        visible_assertions = list_from_report(report, "visibleTargets", "visible_targets_verified")
    clicked_controls = list_from_report(report, "clickedControls", "webview_click_actions")
    if not clicked_controls:
        clicked_controls = list_from_report(report, "clickedControls", "webview_click_observed")
    tauri_runtime_observed = bool_from_report(report, "tauriRuntimeObserved", "tauriInternals")
    webview_dom_observed = bool_from_report(report, "webviewDomObserved") or bool(visible_assertions)
    webview_click_observed = bool_from_report(report, "webviewClickObserved", "clickObserved")
    webview_click_observed = webview_click_observed or bool(clicked_controls)
    browser_fallback_used = bool_from_report(report, "browserFallbackUsed")
    failures = validate_adapted_runtime(
        report,
        tauri_runtime_observed=tauri_runtime_observed,
        webview_dom_observed=webview_dom_observed,
        webview_click_observed=webview_click_observed,
        browser_fallback_used=browser_fallback_used,
        visible_assertions=visible_assertions,
        clicked_controls=clicked_controls,
    )
    status = "pass" if not failures else "fail"
    return {
        "schema": SCHEMA,
        "name": "tauri_webview_dom_click_smoke",
        "status": status,
        "platform": "macos" if sys.platform == "darwin" else sys.platform,
        "collectionMethod": "tauri-dev-runtime-smoke-webview-dom-click",
        "phase": PHASE,
        "startedAt": launch.get("startedAt"),
        "finishedAt": utc_now(),
        "tauriRuntimeObserved": tauri_runtime_observed,
        "webviewDomObserved": webview_dom_observed,
        "webviewClickObserved": webview_click_observed,
        "browserFallbackUsed": browser_fallback_used,
        "screenshotObserved": bool(screenshots),
        "visibleAssertions": visible_assertions,
        "clickedControls": clicked_controls,
        "screenshots": screenshots,
        "sourceRuntimeReport": {
            "path": str(temp_report_path),
            "schema": report.get("schema"),
            "status": report.get("status"),
            "phase": report.get("phase"),
            "name": report.get("name"),
        },
        "runtimeReport": report,
        "launch": {
            **launch,
            "logPath": str(log_path),
        },
        "boundaries": {
            "fullLegacyParityCovered": False,
            "releasePublished": False,
            "productionSigned": False,
            "notarized": False,
            "nativeDialogClickCovered": False,
            "ocrCovered": False,
            "browserFallbackUsed": False,
        },
        "failures": failures,
    }


def validate_adapted_runtime(
    report: dict[str, Any],
    *,
    tauri_runtime_observed: bool,
    webview_dom_observed: bool,
    webview_click_observed: bool,
    browser_fallback_used: bool,
    visible_assertions: list[Any],
    clicked_controls: list[Any],
) -> list[str]:
    failures: list[str] = []
    if report.get("schema") not in (RUNTIME_SCHEMA, SCHEMA):
        failures.append(f"runtime report schema must be {RUNTIME_SCHEMA} or {SCHEMA}")
    if report.get("phase") != PHASE:
        failures.append(f"runtime report phase must be {PHASE}")
    if str(report.get("status", "")).lower() != "pass":
        failures.append("runtime report status must be pass")
    if tauri_runtime_observed is not True:
        failures.append("tauriRuntimeObserved must be true")
    if webview_dom_observed is not True:
        failures.append("webviewDomObserved must be true")
    if webview_click_observed is not True:
        failures.append("webviewClickObserved must be true")
    if browser_fallback_used is not False:
        failures.append("browserFallbackUsed must be false")
    if len(visible_assertions) < 4:
        failures.append("visibleAssertions must include at least 4 entries")
    if len(clicked_controls) < 4:
        failures.append("clickedControls must include at least 4 entries")
    return failures


def blocked_evidence(reason: str, *, temp_dir: Path) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "name": "tauri_webview_dom_click_smoke",
        "status": "blocked",
        "platform": "macos" if sys.platform == "darwin" else sys.platform,
        "collectionMethod": "tauri-dev-runtime-smoke-webview-dom-click",
        "phase": PHASE,
        "startedAt": utc_now(),
        "finishedAt": utc_now(),
        "tauriRuntimeObserved": False,
        "webviewDomObserved": False,
        "webviewClickObserved": False,
        "browserFallbackUsed": False,
        "screenshotObserved": False,
        "visibleAssertions": [],
        "clickedControls": [],
        "screenshots": [],
        "boundaries": {
            "fullLegacyParityCovered": False,
            "releasePublished": False,
            "productionSigned": False,
            "notarized": False,
            "nativeDialogClickCovered": False,
            "ocrCovered": False,
            "browserFallbackUsed": False,
        },
        "blocker": reason,
        "launch": {
            "skipped": True,
            "reason": "frontend runtime smoke phase is not ready",
            "command": "npm --prefix apps/desktop run tauri:dev",
        },
        "sourceRuntimeReport": None,
        "environment": {
            "python": sys.version.split()[0],
            "system": platform.platform(),
            "cwd": str(ROOT),
        },
    }


def run(args: argparse.Namespace) -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="lizzieyzy-tauri-webview-dom-click-"))
    evidence_path = args.evidence_out
    supported, reason = phase_supported()
    if not supported and not args.force:
        evidence = blocked_evidence(reason, temp_dir=temp_dir)
        write_evidence(evidence_path, evidence, temp_dir=temp_dir)
        print(f"BLOCKED Tauri WebView DOM/click smoke: {reason}", file=sys.stderr)
        print(f"wrote {repo_relative(evidence_path)}", file=sys.stderr)
        return 2

    sgf_path = temp_dir / "webview-dom-click.sgf"
    report_path = temp_dir / "runtime-report.json"
    log_path = temp_dir / "tauri-dev.log"
    write_sgf(sgf_path)
    launch: dict[str, Any] = {
        "command": "npm --prefix apps/desktop run tauri:dev",
        "phase": PHASE,
        "sgfPath": str(sgf_path),
        "reportPath": str(report_path),
        "pid": None,
        "startedAt": utc_now(),
        "stopped": False,
    }
    process: subprocess.Popen[bytes] | None = None
    try:
        process = start_tauri(sgf_path, report_path, log_path)
        launch["pid"] = process.pid
        report = wait_for_report(report_path, process, args.timeout)
        evidence = adapt_runtime_report(
            report,
            temp_dir=temp_dir,
            temp_report_path=report_path,
            log_path=log_path,
            launch=launch,
        )
        return_code = 0 if evidence["status"] == "pass" else 1
    except Exception as exc:
        evidence = blocked_evidence(str(exc), temp_dir=temp_dir)
        evidence["status"] = "fail"
        evidence["launch"] = launch
        evidence["launch"]["logPath"] = str(log_path)
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
    }
    write_evidence(evidence_path, evidence, temp_dir=temp_dir)
    if return_code == 0:
        print(f"PASS Tauri WebView DOM/click smoke: wrote {repo_relative(evidence_path)}")
    else:
        print(f"FAIL Tauri WebView DOM/click smoke: wrote {repo_relative(evidence_path)}", file=sys.stderr)
        for failure in evidence.get("failures", []):
            print(f"- {failure}", file=sys.stderr)
        if evidence.get("blocker"):
            print(f"- {evidence['blocker']}", file=sys.stderr)
    return return_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect scoped Tauri WebView DOM/click smoke evidence.")
    parser.add_argument("--evidence-out", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--force", action="store_true", help="launch even if local runtimeSmoke preflight cannot see the phase")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
