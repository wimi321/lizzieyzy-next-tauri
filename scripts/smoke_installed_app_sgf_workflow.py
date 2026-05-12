#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


SCHEMA = "lizzieyzy.installed-app-sgf-workflow.v1"
DEFAULT_EVIDENCE_OUT = "docs/qa/installed-app-sgf-workflow-macos.json"
PHASE = "installed-app-sgf-workflow"
SMOKE_SGF = """(;FF[4]GM[1]CA[UTF-8]AP[LizzieYzyNextSmoke]SZ[9]KM[6.5]PB[Black]PW[White]C[root]
;B[dd]C[main one]LB[dd:A]
(;W[ee]C[first branch]TR[ee];B[de]C[branch child])
(;W[fd]C[second branch]SQ[fd])
(;W[]C[pass branch]))
"""


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


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
    if not isinstance(check, dict):
        return {}
    details = check.get("details") if isinstance(check.get("details"), dict) else check.get("evidence")
    return details if isinstance(details, dict) else {}


def pass_check(name: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass", "details": details}


def installed_screenshot(installed_smoke: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for screenshot in installed_smoke.get("screenshots", []):
        if isinstance(screenshot, dict):
            records.append(screenshot)
    for check in installed_smoke.get("checks", []):
        if isinstance(check, dict) and check.get("name") == "packaged_app_window_screenshot":
            details = check.get("details")
            if isinstance(details, dict) and isinstance(details.get("screenshot"), dict):
                records.insert(0, details["screenshot"])
    for record in records:
        sha = record.get("sha256")
        size = record.get("sizeBytes") or record.get("bytes")
        path = record.get("path")
        if smoke_user_flows.is_sha256_hex(sha) and smoke_user_flows.positive_number(size) and isinstance(path, str):
            return {
                "label": record.get("label") or record.get("name") or "installed-app-sgf-workflow-window",
                "source": "installed_app_sgf_workflow",
                "path": path,
                "sizeBytes": size,
                "sha256": sha,
            }
    raise ValueError("installed app smoke must include screenshot path/sha256/size metadata")


def runtime_process(installed_smoke: dict[str, Any]) -> dict[str, Any]:
    for check in installed_smoke.get("checks", []):
        if isinstance(check, dict) and check.get("name") == "packaged_app_window_screenshot":
            details = check.get("details")
            window = details.get("window") if isinstance(details, dict) and isinstance(details.get("window"), dict) else {}
            return {
                "observed": True,
                "processName": window.get("ownerName") or installed_smoke.get("processName") or "installed-app",
                "pid": window.get("ownerPid") or installed_smoke.get("processId"),
                "windowId": window.get("windowId"),
            }
    return {"observed": True, "processName": installed_smoke.get("processName") or "installed-app"}


def boundaries() -> dict[str, bool]:
    return {
        "fullSgfWorkflowParity": False,
        "nativeDialogParity": False,
        "releaseParity": False,
        "fullLegacyParity": False,
        "windowsCovered": False,
        "linuxCovered": False,
        "providerParity": False,
        "readboardParity": False,
        "ocrParity": False,
    }


def runtime_check_or_raise(report: dict[str, Any], name: str) -> dict[str, Any]:
    check = check_by_name(report).get(name)
    if not isinstance(check, dict) or str(check.get("status", "")).lower() != "pass":
        raise ValueError(f"runtime report missing PASS check {name}")
    details = check.get("details")
    return details if isinstance(details, dict) else {}


def derive_executable_path(installed_smoke: dict[str, Any], override: str | None = None) -> Path:
    if override:
        return path_arg(override)
    bundle = installed_smoke.get("bundle")
    if isinstance(bundle, dict):
        binary = bundle.get("binary")
        if isinstance(binary, dict) and isinstance(binary.get("path"), str):
            return path_arg(binary["path"])
    app_bundle = installed_smoke.get("appBundle")
    app_path = None
    executable = None
    if isinstance(app_bundle, dict):
        app_path = app_bundle.get("path") if isinstance(app_bundle.get("path"), str) else None
        executable = app_bundle.get("mainExecutable") if isinstance(app_bundle.get("mainExecutable"), str) else None
    if executable is None and isinstance(bundle, dict):
        expected = bundle.get("expected")
        if isinstance(expected, dict) and isinstance(expected.get("mainExecutable"), str):
            executable = expected["mainExecutable"]
    if app_path and executable:
        return path_arg(str(Path(app_path) / "Contents" / "MacOS" / executable))
    raise ValueError("could not derive installed app executable path from installed app smoke evidence")


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
    executable_override: str | None,
    timeout_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    executable = derive_executable_path(installed_smoke, executable_override)
    if not executable.is_file():
        raise ValueError(f"installed app executable does not exist: {executable}")
    with tempfile.TemporaryDirectory(prefix="lizzieyzy-installed-sgf-") as tmp:
        temp_dir = Path(tmp)
        sgf_path = temp_dir / "installed-app-sgf-workflow.sgf"
        report_path = temp_dir / "installed-app-sgf-workflow-report.json"
        log_path = temp_dir / "installed-app-sgf-workflow.log"
        sgf_path.write_text(SMOKE_SGF, encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "LIZZIEYZY_RUNTIME_SMOKE": "1",
                "LIZZIEYZY_RUNTIME_SMOKE_PHASE": PHASE,
                "LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
                "LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
                "VITE_LIZZIEYZY_RUNTIME_SMOKE": "1",
                "VITE_LIZZIEYZY_RUNTIME_SMOKE_PHASE": PHASE,
                "VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
                "VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            }
        )
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
                    report = load_json(report_path)
                    return report, launch
                if process.poll() is not None:
                    break
                time.sleep(0.25)
            if report_path.is_file():
                return load_json(report_path), launch
            log_tail = ""
            if log_path.is_file():
                log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            raise ValueError(f"installed app SGF workflow report was not created at {report_path}; log tail: {log_tail}")
        finally:
            log_file.close()
            stop_process(process)


def build_evidence(installed_smoke: dict[str, Any], runtime_report: dict[str, Any]) -> dict[str, Any]:
    installed_failures = smoke_user_flows.validate_installed_macos_app_smoke_evidence(installed_smoke)
    if installed_failures:
        raise ValueError("installed app smoke evidence is invalid: " + "; ".join(installed_failures))
    runtime = sanitize(runtime_report)
    runtime_failures = smoke_user_flows.validate_installed_app_sgf_runtime_report(runtime)
    if runtime_failures:
        raise ValueError("Tauri runtime report is invalid: " + "; ".join(runtime_failures))

    screenshot = installed_screenshot(installed_smoke)
    sgf_loaded = runtime_check_or_raise(runtime, "sgf_loaded")
    branch_navigation = runtime_check_or_raise(runtime, "branch_navigation")
    comment = runtime_check_or_raise(runtime, "comment_edit")
    prop = runtime_check_or_raise(runtime, "property_edit")
    annotation = runtime_check_or_raise(runtime, "annotation_edit")
    append = runtime_check_or_raise(runtime, "append_move")
    edit = runtime_check_or_raise(runtime, "edit_move")
    reorder = runtime_check_or_raise(runtime, "variation_reorder")
    delete = runtime_check_or_raise(runtime, "delete_node")
    save = runtime_check_or_raise(runtime, "save_readback_roundtrip")
    invariant = runtime_check_or_raise(runtime, "board_state_verified")
    after_reopen = save.get("afterReopen") if isinstance(save.get("afterReopen"), dict) else {}
    reopen = save.get("reopen") if isinstance(save.get("reopen"), dict) else {}
    boundary_values = boundaries()
    app_bundle = installed_smoke.get("appBundle")
    checks = [
        pass_check("installed_app_launched", {"installedAppLaunched": True, "appBundlePath": installed_smoke.get("appBundlePath")}),
        pass_check("runtime_report_observed", {"schema": runtime.get("schema"), "status": runtime.get("status"), "tauriRuntimeObserved": True}),
        pass_check("sgf_loaded", sgf_loaded),
        pass_check("sgf_reparsed", {"reparseVerified": True, "source": "save_readback_roundtrip", "readbackStatus": save.get("readbackStatus")}),
        pass_check("tree_navigation", branch_navigation),
        pass_check("comment_edit", comment),
        pass_check("property_edit", prop),
        pass_check("annotation_edit", annotation),
        pass_check("append_move", append),
        pass_check("edit_move", edit),
        pass_check("variation_reorder", reorder),
        pass_check("delete_node", delete),
        pass_check("save_readback_roundtrip", save),
        pass_check("reopen_verified", {"reopenVerified": True, "reopen": reopen, "afterReopen": after_reopen}),
        pass_check("final_invariant_verified", invariant),
        pass_check("screenshot_hash_recorded", screenshot),
        pass_check("scope_boundaries_recorded", {"boundaries": boundary_values}),
    ]
    return {
        "schema": SCHEMA,
        "name": "installed_app_sgf_workflow",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "installed_app_smoke_plus_real_tauri_runtime_sgf_report",
        "runtimePhase": PHASE,
        "installedAppLaunched": True,
        "tauriRuntimeObserved": True,
        "sgfWorkflowAutomated": True,
        "screenshotHashRecorded": True,
        "sourceStaticOnly": False,
        "devServerOnly": False,
        "browserFallbackUsed": False,
        **boundary_values,
        "appBundlePath": installed_smoke.get("appBundlePath"),
        "appBundle": app_bundle,
        "runtimeProcess": runtime_process(installed_smoke),
        "sourceRuntimeReport": runtime,
        "screenshots": [screenshot],
        "checks": checks,
        "boundaries": boundary_values,
    }


def path_arg(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launch packaged macOS app and aggregate installed-app SGF workflow runtime proof."
    )
    parser.add_argument("--installed-app-smoke", required=True)
    parser.add_argument("--app-executable")
    parser.add_argument("--evidence-out", default=DEFAULT_EVIDENCE_OUT)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    installed_smoke = load_json(path_arg(args.installed_app_smoke))
    runtime_report, launch = run_packaged_app_runtime_report(
        installed_smoke,
        executable_override=args.app_executable,
        timeout_seconds=args.timeout_seconds,
    )
    evidence = build_evidence(installed_smoke, runtime_report)
    evidence["packagedAppLaunch"] = sanitize(launch)
    failures = smoke_user_flows.validate_installed_app_sgf_workflow_evidence(evidence)
    if failures:
        raise SystemExit("installed app SGF workflow evidence is invalid: " + "; ".join(failures))

    if args.validate_only:
        print("installed app SGF workflow evidence is valid")
    else:
        output_path = path_arg(args.evidence_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
