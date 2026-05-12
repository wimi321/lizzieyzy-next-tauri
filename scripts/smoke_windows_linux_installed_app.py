#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import smoke_user_flows


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = smoke_user_flows.WINDOWS_LINUX_INSTALLED_APP_SMOKE_SCHEMA
NAME = "windows_linux_installed_app_smoke"
DEV_SERVER_PORTS = (1420, 5173, 3000)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect scoped unsigned Windows/Linux installed-app launch evidence.")
    parser.add_argument("--platform", choices=("windows", "linux"), required=True, help="platform under test")
    parser.add_argument("--binary", type=Path, help="installed app binary to launch")
    parser.add_argument("--evidence-out", type=Path, required=True, help="where to write/read evidence JSON")
    parser.add_argument("--launch-wrapper", default="", help="optional wrapper command, e.g. 'xvfb-run -a'")
    parser.add_argument("--window-title", default="", help="optional expected window title substring for platform window observation")
    parser.add_argument("--timeout", type=float, default=10.0, help="seconds to observe the launched process")
    parser.add_argument("--validate-only", action="store_true", help="validate an existing evidence file instead of launching")
    parser.add_argument("--write-pending", action="store_true", help="write pending evidence instead of failing when no binary is available")
    args = parser.parse_args(argv)

    if args.validate_only:
        return validate_existing(args.evidence_out, args.platform)

    if args.binary is None:
        evidence = pending_evidence(args.platform, "No --binary was provided.", args.launch_wrapper)
        write_evidence(args.evidence_out, evidence)
        print(f"wrote pending Windows/Linux installed-app evidence: {args.evidence_out}")
        return 0 if args.write_pending else 2

    evidence = collect_evidence(
        platform=args.platform,
        binary=args.binary,
        evidence_out=args.evidence_out,
        launch_wrapper=args.launch_wrapper,
        window_title=args.window_title,
        timeout=max(args.timeout, 0.1),
    )
    write_evidence(args.evidence_out, evidence)
    status = str(evidence.get("status", "")).lower()
    print(f"wrote {status} Windows/Linux installed-app evidence: {args.evidence_out}")
    return 0 if status == "pass" else 1


def validate_existing(path: Path, platform: str) -> int:
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"evidence file is missing: {path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"invalid JSON at line {exc.lineno}: {exc.msg}", file=sys.stderr)
        return 2
    status = str(evidence.get("status", "")).lower()
    if status == "pass":
        failures = smoke_user_flows.validate_windows_linux_installed_app_smoke_evidence(evidence, platform)
    else:
        failures = smoke_user_flows.validate_windows_linux_installed_app_pending_evidence(evidence, platform)
    if failures:
        print("invalid Windows/Linux installed-app evidence: " + "; ".join(failures), file=sys.stderr)
        return 1
    print(f"valid {status} Windows/Linux installed-app evidence: {path}")
    return 0


def collect_evidence(
    *,
    platform: str,
    binary: Path,
    evidence_out: Path,
    launch_wrapper: str,
    window_title: str,
    timeout: float,
) -> dict[str, Any]:
    resolved_binary = binary.expanduser().resolve()
    wrapper_parts = split_wrapper(launch_wrapper)
    display_mode = detect_display_mode(platform, launch_wrapper)
    dev_server_preflight = dev_server_status()
    dev_server_absent = not dev_server_preflight["reachableBeforeLaunch"]
    artifact = artifact_metadata(resolved_binary)
    if artifact is None:
        return {
            **base_evidence(platform, launch_wrapper, display_mode, dev_server_preflight, dev_server_absent),
            "status": "unavailable",
            "pendingReason": f"Binary does not exist: {stable_artifact_path(resolved_binary)}",
            "artifact": {
                "path": stable_artifact_path(resolved_binary),
                "name": resolved_binary.name,
                "sha256": None,
                "sizeBytes": 0,
            },
            "launchCommand": sanitized_command(wrapper_parts, resolved_binary),
            "processObserved": False,
            "windowObserved": False,
            "windowObservation": {"observed": False, "method": "not_attempted"},
            "exitOrTerminateSuccess": False,
        }
    identity_failures = smoke_user_flows.validate_windows_linux_installed_app_artifact(artifact)
    if identity_failures:
        return {
            **base_evidence(platform, launch_wrapper, display_mode, dev_server_preflight, dev_server_absent),
            "status": "unavailable",
            "pendingReason": "Artifact is not an installed LizzieYzy app binary: " + "; ".join(identity_failures),
            "artifact": artifact,
            "launchCommand": sanitized_command(wrapper_parts, resolved_binary),
            "processObserved": False,
            "windowObserved": False,
            "windowObservation": {"observed": False, "method": "not_attempted"},
            "exitOrTerminateSuccess": False,
        }

    command = [*wrapper_parts, str(resolved_binary)]
    started_at = time.time()
    process: subprocess.Popen[bytes] | None = None
    process_observed = False
    exit_or_terminate_success = False
    window_observed = False
    window_observation: dict[str, Any] = {"observed": False, "method": "not_attempted"}
    process_detail: dict[str, Any] = {"started": False}
    status = "pass"
    reason = ""

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process_observed = process.pid is not None
        process_detail = {
            "started": process_observed,
            "pid": process.pid,
            "observedSeconds": round(timeout, 3),
        }
        deadline = time.time() + timeout
        while time.time() < deadline:
            window_observation = observe_window(platform, window_title or resolved_binary.stem, pid=process.pid)
            window_observed = window_observation["observed"] is True
            if window_observed:
                break
            if process.poll() is not None:
                break
            time.sleep(0.25)
        process_detail["windowPollSeconds"] = round(max(0.0, timeout - max(0.0, deadline - time.time())), 3)
        try:
            stdout, stderr = process.communicate(timeout=0.1 if process.poll() is not None else 0.01)
            process_detail["exitCode"] = process.returncode
            process_detail["stdoutBytes"] = len(stdout or b"")
            process_detail["stderrBytes"] = len(stderr or b"")
            exit_or_terminate_success = process.returncode == 0
            if process.returncode != 0 and not window_observed:
                status = "fail"
                reason = f"Process exited with code {process.returncode} before observation completed."
        except subprocess.TimeoutExpired:
            process_detail["stillRunningAfterTimeout"] = True
            process.terminate()
            try:
                process.communicate(timeout=5)
                process_detail["terminated"] = True
                exit_or_terminate_success = True
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
                process_detail["terminated"] = False
                process_detail["killed"] = True
                exit_or_terminate_success = True
    except OSError as exc:
        status = "fail"
        reason = f"Launch failed: {exc}"
        process_detail = {"started": False, "error": str(exc)}

    if not dev_server_absent:
        status = "fail"
        reason = "A dev server was reachable before launch; installed-app proof must not depend on Vite/dev server."
    if status == "pass" and not process_observed:
        status = "fail"
        reason = "Process was not observed after launch."
    if status == "pass" and not window_observed:
        status = "unavailable"
        reason = "Window was not observed; process-only installed-app evidence is not accepted for PASS."
    if status == "pass" and not exit_or_terminate_success:
        status = "fail"
        reason = "Process exit/terminate success was not observed."

    evidence: dict[str, Any] = {
        **base_evidence(platform, launch_wrapper, display_mode, dev_server_preflight, dev_server_absent),
        "status": status,
        "artifact": artifact,
        "launchCommand": sanitized_command(wrapper_parts, resolved_binary),
        "processObserved": process_observed,
        "windowObserved": window_observed,
        "windowObservation": window_observation,
        "process": process_detail,
        "exitOrTerminateSuccess": exit_or_terminate_success,
        "collection": {
            "startedAtUnix": round(started_at, 3),
            "timeoutSeconds": timeout,
            "evidencePath": stable_artifact_path(evidence_out),
        },
    }
    if reason:
        evidence["reason"] = reason
    return evidence


def base_evidence(
    platform: str,
    launch_wrapper: str,
    display_mode: str,
    dev_server_preflight: dict[str, Any],
    dev_server_absent: bool,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "name": NAME,
        "platform": platform,
        "collector": "scripts/smoke_windows_linux_installed_app.py",
        "launchWrapper": launch_wrapper,
        "devServerAbsent": dev_server_absent,
        "devServerPreflight": dev_server_preflight,
        "runnerStartedDevServer": False,
        "runnerStartedViteDevServer": False,
        "displayMode": display_mode,
        "staticOnly": False,
        "artifactOnly": False,
        "browserOnly": False,
        "boundaries": {
            **{key: False for key in smoke_user_flows.WINDOWS_LINUX_INSTALLED_APP_SMOKE_OVERCLAIM_FIELDS},
            "viteDevServerStarted": False,
        },
    }


def pending_evidence(platform: str, reason: str, launch_wrapper: str = "") -> dict[str, Any]:
    return {
        **base_evidence(platform, launch_wrapper, detect_display_mode(platform, launch_wrapper), dev_server_status(), True),
        "status": "pending",
        "pendingReason": reason,
        "artifact": None,
        "launchCommand": [],
        "processObserved": False,
        "windowObserved": False,
        "windowObservation": {"observed": False, "method": "not_attempted"},
        "exitOrTerminateSuccess": False,
    }


def artifact_metadata(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return {
        "path": stable_artifact_path(path),
        "name": path.name,
        "sha256": smoke_user_flows.sha256_file(path),
        "sizeBytes": path.stat().st_size,
    }


def split_wrapper(value: str) -> list[str]:
    if not value.strip():
        return []
    return shlex.split(value, posix=os.name != "nt")


def sanitized_command(wrapper_parts: list[str], binary: Path) -> list[str]:
    return [*wrapper_parts, stable_artifact_path(binary)]


def stable_artifact_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def detect_display_mode(platform: str, launch_wrapper: str) -> str:
    if platform == "linux":
        if "xvfb" in launch_wrapper.lower():
            return "xvfb"
        return "desktop" if os.environ.get("DISPLAY") else "headless"
    return "desktop"


def observe_window(platform: str, title: str, *, pid: int | None = None) -> dict[str, Any]:
    expected = title.strip().lower()
    if platform == "linux":
        wmctrl_observation: dict[str, Any] | None = None
        if shutil.which("wmctrl"):
            wmctrl_observation = observe_linux_wmctrl_window(expected, pid)
            if wmctrl_observation.get("observed") is True:
                return wmctrl_observation
        if shutil.which("xdotool"):
            xdotool_observation = observe_linux_xdotool_window(expected, title.strip() or "Lizzie", pid)
            if wmctrl_observation is not None:
                xdotool_observation["fallbackFrom"] = {
                    "method": wmctrl_observation.get("method"),
                    "source": wmctrl_observation.get("source"),
                    "observed": wmctrl_observation.get("observed"),
                    "exitCode": wmctrl_observation.get("exitCode"),
                    "titleCount": wmctrl_observation.get("titleCount"),
                }
            return xdotool_observation
        if wmctrl_observation is not None:
            return wmctrl_observation
        return {"observed": False, "method": "unavailable", "reason": "wmctrl/xdotool unavailable"}
    if platform == "windows":
        if shutil.which("powershell"):
            script = "Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -ExpandProperty MainWindowTitle"
            return observe_window_command(["powershell", "-NoProfile", "-Command", script], expected, "powershell")
        if shutil.which("pwsh"):
            script = "Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -ExpandProperty MainWindowTitle"
            return observe_window_command(["pwsh", "-NoProfile", "-Command", script], expected, "pwsh")
        return {"observed": False, "method": "unavailable", "reason": "PowerShell unavailable"}
    return {"observed": False, "method": "unsupported_platform"}


def observe_linux_wmctrl_window(expected: str, pid: int | None) -> dict[str, Any]:
    try:
        completed = subprocess.run(["wmctrl", "-lp"], check=False, capture_output=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"observed": False, "method": "wmctrl", "source": "wmctrl -lp", "pid": pid, "error": str(exc)}
    output = (completed.stdout or b"").decode("utf-8", errors="replace")
    matches: list[dict[str, Any]] = []
    title_count = 0
    for line in output.splitlines():
        parsed = parse_wmctrl_lp_line(line)
        if parsed is None:
            continue
        title_count += 1
        title_lower = parsed["title"].lower()
        pid_matches = pid is not None and parsed["pid"] == pid
        title_matches = bool(expected) and (expected in title_lower or "lizzie" in title_lower)
        if pid_matches or title_matches:
            matches.append(parsed)
    first = matches[0] if matches else None
    return {
        "observed": first is not None,
        "method": "wmctrl",
        "source": "wmctrl -lp",
        "pid": pid,
        "windowId": first["windowId"] if first else "",
        "title": first["title"] if first else "",
        "matchedBy": "pid" if first and pid is not None and first["pid"] == pid else "title" if first else "",
        "exitCode": completed.returncode,
        "titleCount": title_count,
    }


def parse_wmctrl_lp_line(line: str) -> dict[str, Any] | None:
    parts = line.split(None, 4)
    if len(parts) < 5:
        return None
    window_id, desktop, pid_text, host, title = parts
    try:
        pid = int(pid_text)
    except ValueError:
        return None
    return {
        "windowId": window_id,
        "desktop": desktop,
        "pid": pid,
        "host": host,
        "title": title.strip(),
    }


def observe_linux_xdotool_window(expected: str, title: str, pid: int | None) -> dict[str, Any]:
    search_commands: list[tuple[str, list[str]]] = []
    if pid is not None:
        search_commands.append(("pid", ["xdotool", "search", "--pid", str(pid)]))
    search_commands.append(("name", ["xdotool", "search", "--name", title]))
    attempted: list[str] = []
    for source, command in search_commands:
        attempted.append(source)
        try:
            completed = subprocess.run(command, check=False, capture_output=True, timeout=2)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"observed": False, "method": "xdotool", "source": source, "pid": pid, "error": str(exc)}
        window_ids = parse_xdotool_window_ids((completed.stdout or b"").decode("utf-8", errors="replace"))
        for window_id in window_ids:
            name = xdotool_window_name(window_id)
            title_lower = name.lower()
            if expected and expected not in title_lower and "lizzie" not in title_lower:
                continue
            return {
                "observed": True,
                "method": "xdotool",
                "source": f"xdotool search --{source}",
                "pid": pid,
                "windowId": window_id,
                "title": name,
                "matchedBy": source,
                "exitCode": completed.returncode,
                "windowIdCount": len(window_ids),
                "attemptedSearches": attempted,
            }
    return {
        "observed": False,
        "method": "xdotool",
        "source": "xdotool search",
        "pid": pid,
        "windowId": "",
        "title": "",
        "matchedBy": "",
        "attemptedSearches": attempted,
    }


def parse_xdotool_window_ids(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip().isdigit()]


def xdotool_window_name(window_id: str) -> str:
    try:
        completed = subprocess.run(["xdotool", "getwindowname", window_id], check=False, capture_output=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (completed.stdout or b"").decode("utf-8", errors="replace").strip()


def observe_window_command(command: list[str], expected: str, method: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"observed": False, "method": method, "error": str(exc)}
    output = (completed.stdout or b"").decode("utf-8", errors="replace")
    haystack = output.lower()
    observed = bool(output.strip()) if not expected else expected in haystack or "lizzie" in haystack
    return {
        "observed": observed,
        "method": method,
        "exitCode": completed.returncode,
        "matchedTitle": expected if observed else "",
        "titleCount": len([line for line in output.splitlines() if line.strip()]),
    }


def dev_server_status() -> dict[str, Any]:
    reachable_ports = [port for port in DEV_SERVER_PORTS if port_reachable(port)]
    return {
        "checkedPorts": list(DEV_SERVER_PORTS),
        "reachablePorts": reachable_ports,
        "reachableBeforeLaunch": bool(reachable_ports),
        "runnerStartedDevServer": False,
        "runnerStartedViteDevServer": False,
    }


def port_reachable(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.15):
            return True
    except OSError:
        return False


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
