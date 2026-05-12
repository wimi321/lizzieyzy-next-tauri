#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "lizzieyzy.tauri-window-runtime-smoke.v1"
TAURI_RUNTIME_SCHEMA = "lizzieyzy.tauri-runtime-ui-smoke.v1"
DEFAULT_RUNTIME_EVIDENCE = Path("docs/qa/tauri-runtime-ui-smoke-macos.json")
DEFAULT_EVIDENCE = Path("docs/qa/tauri-window-runtime-smoke-macos.json")
DEFAULT_SCREENSHOT_DIR = Path("docs/qa/screenshots")
DEFAULT_SCREENSHOT_NAME = "tauri-window-runtime-smoke.png"
WINDOW_MATCHERS = ("LizzieYzy Next", "lizzieyzy-next-desktop", "LizzieYzy")


class SmokeError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect scoped Tauri desktop window/runtime screenshot smoke evidence.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--runtime-evidence", type=Path, default=DEFAULT_RUNTIME_EVIDENCE)
    parser.add_argument("--evidence-out", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--screenshot-dir", type=Path, default=DEFAULT_SCREENSHOT_DIR)
    parser.add_argument("--timeout", type=float, default=180.0, help="Seconds to wait for the Tauri window.")
    parser.add_argument("--settle-seconds", type=float, default=1.5, help="Seconds to wait after matching a window.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    evidence_path = resolve_repo_path(args.evidence_out, root)
    screenshot_dir = resolve_repo_path(args.screenshot_dir, root)
    runtime_evidence_path = resolve_repo_path(args.runtime_evidence, root)
    started_at = iso_timestamp()
    process: subprocess.Popen[str] | None = None
    log_path = root / ".tmp" / "tauri-window-runtime-smoke-tauri-dev.log"
    screenshot_path = screenshot_dir / DEFAULT_SCREENSHOT_NAME
    source_runtime: dict[str, Any] = {}
    source_summary: dict[str, Any] = {
        "path": repo_relative_path(runtime_evidence_path, root),
        "schema": None,
        "status": None,
    }

    try:
        if normalized_platform() != "macos":
            raise SmokeError("Tauri window runtime screenshot smoke is currently a macOS local evidence gate.")
        require_tool("npm")
        require_tool("screencapture")
        require_tool("swift")

        source_runtime = load_json_object(runtime_evidence_path)
        source_summary = source_runtime_summary(source_runtime, runtime_evidence_path, root)
        source_failures = validate_source_runtime(source_runtime)
        if source_failures:
            raise SmokeError("source Tauri runtime evidence invalid: " + "; ".join(source_failures))

        process = start_tauri_dev(root, log_path)
        window = wait_for_window(timeout_seconds=args.timeout)
        if args.settle_seconds > 0:
            time.sleep(args.settle_seconds)

        screenshot = capture_window_screenshot(window, screenshot_path, root)
        evidence = build_evidence(
            status="pass",
            started_at=started_at,
            source_runtime=source_runtime,
            source_summary=source_summary,
            process=process,
            window=window,
            screenshot=screenshot,
            log_path=log_path,
            blocker=None,
        )
        write_json(evidence_path, evidence)
        print(f"PASS Tauri window runtime smoke: wrote {repo_relative_path(evidence_path, root)}")
        return 0
    except Exception as exc:  # noqa: BLE001
        evidence = build_evidence(
            status="fail",
            started_at=started_at,
            source_runtime=source_runtime,
            source_summary=source_summary,
            process=process,
            window=None,
            screenshot=None,
            log_path=log_path,
            blocker=str(exc),
        )
        write_json(evidence_path, evidence)
        print(f"FAIL Tauri window runtime smoke: {exc}", file=sys.stderr)
        print(f"wrote failure evidence to {repo_relative_path(evidence_path, root)}", file=sys.stderr)
        return 1
    finally:
        if process is not None:
            stop_process(process)


def resolve_repo_path(path: Path, root: Path) -> Path:
    return path if path.is_absolute() else root / path


def normalized_platform() -> str:
    system = platform.system().lower()
    return "macos" if system == "darwin" else system


def require_tool(name: str) -> None:
    result = subprocess.run(["/usr/bin/which", name], text=True, capture_output=True)
    if result.returncode != 0:
        raise SmokeError(f"required tool not found on PATH: {name}")


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SmokeError(f"source runtime evidence not found: {repo_relative_path(path, ROOT)}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeError(f"source runtime evidence invalid JSON at line {exc.lineno}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise SmokeError("source runtime evidence root must be an object")
    return value


def source_runtime_summary(source: dict[str, Any], path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": repo_relative_path(path, root),
        "schema": source.get("schema"),
        "name": source.get("name"),
        "status": source.get("status"),
        "valid": not validate_source_runtime(source),
    }


def validate_source_runtime(source: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if source.get("schema") != TAURI_RUNTIME_SCHEMA:
        failures.append(f"schema must be {TAURI_RUNTIME_SCHEMA}")
    if str(source.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    if not source_confirms_tauri_runtime(source):
        failures.append("runtime_started evidence must confirm Tauri internals")
    if not source_confirms_save_reopen(source):
        failures.append("save/reopen semantic proof must pass")
    return failures


def source_confirms_tauri_runtime(source: dict[str, Any]) -> bool:
    runtime_started = check_by_name(source, "runtime_started")
    details = check_details(runtime_started)
    return (
        isinstance(runtime_started, dict)
        and str(runtime_started.get("status", "")).lower() == "pass"
        and isinstance(details, dict)
        and details.get("tauriInternals") is True
    )


def source_confirms_save_reopen(source: dict[str, Any]) -> bool:
    proof = source.get("saveReopenProof")
    roundtrip = check_by_name(source, "save_readback_roundtrip")
    roundtrip_details = check_details(roundtrip)
    proof_ok = (
        isinstance(proof, dict)
        and proof.get("sameSgfPath") is True
        and proof.get("distinctProcesses") is True
        and proof.get("firstStoppedBeforeSecondStarted") is True
    )
    roundtrip_ok = (
        isinstance(roundtrip, dict)
        and str(roundtrip.get("status", "")).lower() == "pass"
        and isinstance(roundtrip_details, dict)
        and (
            roundtrip_details.get("readbackVerified") is True
            or roundtrip_details.get("readbackStatus") == "matched_saved_text"
        )
    )
    return proof_ok and roundtrip_ok


def check_by_name(source: dict[str, Any], name: str) -> dict[str, Any] | None:
    checks = source.get("checks")
    if not isinstance(checks, list):
        return None
    for check in checks:
        if isinstance(check, dict) and check.get("name") == name:
            return check
    return None


def check_details(check: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(check, dict):
        return None
    for key in ("details", "evidence"):
        value = check.get(key)
        if isinstance(value, dict):
            return value
    return check


def start_tauri_dev(root: Path, log_path: Path) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("VITE_LIZZIEYZY_RUNTIME_SMOKE") or key.startswith("LIZZIEYZY_RUNTIME_SMOKE"):
            env.pop(key, None)
    log_file = log_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            ["npm", "--prefix", "apps/desktop", "run", "tauri:dev"],
            cwd=root,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        log_file.close()
        return process
    except Exception:
        log_file.close()
        raise


def stop_process(process: subprocess.Popen[str], *, grace_seconds: float = 5.0) -> None:
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


def wait_for_window(*, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_windows: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        windows = list_tauri_windows()
        if windows:
            return windows[0]
        last_windows = windows
        time.sleep(0.5)
    raise SmokeError(f"timed out after {timeout_seconds:g}s waiting for Tauri window; lastMatches={last_windows!r}")


def list_tauri_windows() -> list[dict[str, Any]]:
    script = r'''
import CoreGraphics
import Foundation

let matchers = ["LizzieYzy Next", "lizzieyzy-next-desktop", "LizzieYzy"]
let options = CGWindowListOption(arrayLiteral: .optionOnScreenOnly, .excludeDesktopElements)
let info = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] ?? []
var matches: [[String: Any]] = []

for item in info {
    let owner = item[kCGWindowOwnerName as String] as? String ?? ""
    let title = item[kCGWindowName as String] as? String ?? ""
    let haystack = owner + " " + title
    let matched = matchers.contains { haystack.localizedCaseInsensitiveContains($0) }
    let layer = item[kCGWindowLayer as String] as? Int ?? 0
    let windowId = item[kCGWindowNumber as String] as? Int ?? 0
    guard matched && layer == 0 && windowId > 0 else {
        continue
    }
    var row: [String: Any] = [
        "windowId": windowId,
        "ownerName": owner,
        "title": title,
        "layer": layer
    ]
    if let bounds = item[kCGWindowBounds as String] as? [String: Any] {
        row["bounds"] = bounds
    }
    matches.append(row)
}

let data = try! JSONSerialization.data(withJSONObject: matches, options: [.sortedKeys])
FileHandle.standardOutput.write(data)
'''
    result = subprocess.run(["swift", "-e", script], text=True, capture_output=True, timeout=20)
    if result.returncode != 0:
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        raise SmokeError(f"failed to query macOS windows via CoreGraphics: {combined}")
    try:
        value = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise SmokeError(f"window query returned invalid JSON at line {exc.lineno}: {exc.msg}") from exc
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def capture_window_screenshot(window: dict[str, Any], screenshot_path: Path, root: Path) -> dict[str, Any]:
    window_id = window.get("windowId")
    if not isinstance(window_id, int) or window_id <= 0:
        raise SmokeError("matched Tauri window is missing a valid CoreGraphics windowId")
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    if screenshot_path.exists():
        screenshot_path.unlink()
    result = subprocess.run(
        ["screencapture", "-x", "-l", str(window_id), str(screenshot_path)],
        text=True,
        capture_output=True,
        timeout=20,
    )
    if result.returncode != 0:
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        raise SmokeError(f"screencapture failed for window {window_id}: {combined}")
    if not screenshot_path.is_file():
        raise SmokeError(f"screencapture did not create screenshot: {repo_relative_path(screenshot_path, root)}")
    size = screenshot_path.stat().st_size
    if size <= 1024:
        raise SmokeError(f"screenshot is unexpectedly small ({size} bytes): {repo_relative_path(screenshot_path, root)}")
    return {
        "name": "tauri-window-runtime",
        "path": repo_relative_path(screenshot_path, root),
        "sha256": sha256_file(screenshot_path),
        "bytes": size,
        "captureTool": "screencapture",
        "captureMode": "coregraphics-window-id",
        "windowId": window_id,
    }


def build_evidence(
    *,
    status: str,
    started_at: str,
    source_runtime: dict[str, Any],
    source_summary: dict[str, Any],
    process: subprocess.Popen[str] | None,
    window: dict[str, Any] | None,
    screenshot: dict[str, Any] | None,
    log_path: Path,
    blocker: str | None,
) -> dict[str, Any]:
    tauri_runtime_observed = bool(source_runtime) and not validate_source_runtime(source_runtime)
    tauri_window_screenshot_observed = screenshot is not None and bool(screenshot.get("sha256")) and screenshot.get("bytes", 0) > 1024
    save_reopen_proof = build_save_reopen_summary(source_runtime)
    failures: list[str] = []
    if blocker:
        failures.append(blocker)
    if not tauri_runtime_observed:
        failures.append("Tauri runtime evidence was not observed as pass")
    if not tauri_window_screenshot_observed:
        failures.append("Tauri window screenshot was not captured")
    return {
        "schema": SCHEMA,
        "name": "tauri_window_runtime_smoke",
        "status": "pass" if status == "pass" and not failures else "fail",
        "platform": normalized_platform(),
        "startedAt": started_at,
        "completedAt": iso_timestamp(),
        "collectionMethod": "tauri-dev-coregraphics-window-screencapture",
        "launch": {
            "method": "npm --prefix apps/desktop run tauri:dev",
            "cwd": "<repo>",
            "pid": process.pid if process is not None else None,
            "logPath": repo_relative_path(log_path, ROOT),
            "windowMatchers": list(WINDOW_MATCHERS),
        },
        "sourceRuntimeEvidence": source_summary,
        "saveReopenSemanticProof": save_reopen_proof,
        "tauriRuntimeObserved": tauri_runtime_observed,
        "tauriWindowScreenshotObserved": tauri_window_screenshot_observed,
        "browserFallbackUsed": False,
        "webviewDomClickCovered": False,
        "nativeDialogClickCovered": False,
        "window": sanitize_window(window) if window is not None else None,
        "screenshots": [screenshot] if screenshot is not None else [],
        "boundaries": {
            "webviewDomClickCovered": False,
            "nativeDialogClickCovered": False,
            "browserFallbackUsed": False,
            "nativeFileDialogCovered": False,
            "browserDomObserved": False,
            "note": "This smoke observes a real macOS Tauri desktop window screenshot plus existing Tauri runtime semantic evidence. It does not prove WebView DOM clicks or native file dialog interaction.",
        },
        "checks": [
            {
                "name": "source_tauri_runtime_evidence",
                "status": "pass" if tauri_runtime_observed else "fail",
                "details": source_summary,
            },
            {
                "name": "save_reopen_semantic_proof",
                "status": "pass" if save_reopen_proof.get("verified") is True else "fail",
                "details": save_reopen_proof,
            },
            {
                "name": "tauri_window_screenshot",
                "status": "pass" if tauri_window_screenshot_observed else "fail",
                "details": {
                    "windowMatched": window is not None,
                    "screenshot": screenshot,
                },
            },
            {
                "name": "boundaries",
                "status": "pass",
                "details": {
                    "webviewDomClickCovered": False,
                    "nativeDialogClickCovered": False,
                    "browserFallbackUsed": False,
                },
            },
        ],
        "failures": failures,
    }


def build_save_reopen_summary(source: dict[str, Any]) -> dict[str, Any]:
    if not source:
        return {"verified": False}
    proof = source.get("saveReopenProof")
    roundtrip = check_by_name(source, "save_readback_roundtrip")
    roundtrip_details = check_details(roundtrip)
    first_launch = compact_runtime_launch(source.get("firstLaunch"), launch_index=1, status="pass")
    second_launch = compact_runtime_launch(source.get("secondLaunch"), launch_index=2, status="pass")
    reopen = (
        dict(roundtrip_details.get("reopen"))
        if isinstance(roundtrip_details, dict) and isinstance(roundtrip_details.get("reopen"), dict)
        else {}
    )
    after_reopen = (
        dict(roundtrip_details.get("afterReopen"))
        if isinstance(roundtrip_details, dict) and isinstance(roundtrip_details.get("afterReopen"), dict)
        else {}
    )
    return {
        "verified": source_confirms_save_reopen(source),
        "source": "sourceRuntimeEvidence",
        "firstLaunch": first_launch,
        "secondLaunch": second_launch,
        "saveReopenProof": dict(proof) if isinstance(proof, dict) else None,
        "reopen": reopen,
        "afterReopen": after_reopen,
        "sameSgfPath": proof.get("sameSgfPath") if isinstance(proof, dict) else None,
        "distinctProcesses": proof.get("distinctProcesses") if isinstance(proof, dict) else None,
        "firstStoppedBeforeSecondStarted": (
            proof.get("firstStoppedBeforeSecondStarted") if isinstance(proof, dict) else None
        ),
        "firstPhase": proof.get("firstPhase") if isinstance(proof, dict) else None,
        "secondPhase": proof.get("secondPhase") if isinstance(proof, dict) else None,
        "saveReadbackRoundtrip": {
            "status": roundtrip.get("status") if isinstance(roundtrip, dict) else None,
            "readbackVerified": (
                roundtrip_details.get("readbackVerified") if isinstance(roundtrip_details, dict) else None
            ),
            "readbackStatus": (
                roundtrip_details.get("readbackStatus") if isinstance(roundtrip_details, dict) else None
            ),
            "reopenSecondLaunch": (
                roundtrip_details.get("reopen", {}).get("secondLaunch")
                if isinstance(roundtrip_details, dict) and isinstance(roundtrip_details.get("reopen"), dict)
                else None
            ),
        },
    }


def compact_runtime_launch(value: Any, *, launch_index: int, status: str) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "launchIndex": launch_index,
        "status": status,
        "phase": value.get("phase"),
        "pid": value.get("pid"),
        "stopped": value.get("stopped"),
        "reportPath": value.get("reportPath"),
        "sgfPath": value.get("sgfPath"),
    }


def sanitize_window(window: dict[str, Any] | None) -> dict[str, Any] | None:
    if window is None:
        return None
    return {
        "windowId": window.get("windowId"),
        "ownerName": window.get("ownerName"),
        "title": window.get("title"),
        "layer": window.get("layer"),
        "bounds": window.get("bounds"),
    }


def repo_relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iso_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    raise SystemExit(main())
