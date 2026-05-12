#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import plistlib
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "lizzieyzy.installed-macos-app-smoke.v1"
DEFAULT_APP_BUNDLE = Path("target/release/bundle/macos/LizzieYzy Next.app")
DEFAULT_EVIDENCE = Path("docs/qa/installed-macos-app-smoke.json")
DEFAULT_SCREENSHOT_DIR = Path("docs/qa/screenshots")
DEFAULT_SCREENSHOT_NAME = "installed-macos-app-window.png"
DEFAULT_DEV_SERVER_URL = "http://127.0.0.1:1420"
WINDOW_MATCHERS = ("LizzieYzy Next", "lizzieyzy-next-desktop", "LizzieYzy")


class SmokeError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect scoped macOS packaged .app launch smoke evidence.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--app-bundle", type=Path, default=DEFAULT_APP_BUNDLE)
    parser.add_argument("--evidence-out", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--screenshot-dir", type=Path, default=DEFAULT_SCREENSHOT_DIR)
    parser.add_argument("--dev-server-url", default=DEFAULT_DEV_SERVER_URL)
    parser.add_argument("--build", action="store_true", help="Run tauri:build if the app bundle is missing.")
    parser.add_argument("--timeout", type=float, default=60.0, help="Seconds to wait for the packaged app window.")
    parser.add_argument("--settle-seconds", type=float, default=1.5, help="Seconds to wait after matching a window.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    app_bundle = resolve_repo_path(args.app_bundle, root)
    evidence_path = resolve_repo_path(args.evidence_out, root)
    screenshot_path = resolve_repo_path(args.screenshot_dir, root) / DEFAULT_SCREENSHOT_NAME
    started_at = iso_timestamp()
    process: subprocess.Popen[str] | None = None
    window: dict[str, Any] | None = None
    screenshot: dict[str, Any] | None = None
    bundle: dict[str, Any] | None = None
    build: dict[str, Any] = {"requested": args.build, "ran": False}
    dev_server_check: dict[str, Any] = {}
    launch: dict[str, Any] = {"method": "direct-bundle-executable", "devServerStartedByRunner": False}
    blocker: str | None = None

    try:
        if normalized_platform() != "macos":
            raise SmokeError("Installed macOS app smoke is currently a macOS local evidence gate.")
        require_tool("npm")
        require_tool("swift")
        require_tool("screencapture")
        require_tool("codesign")
        require_tool("spctl")

        if not app_bundle.is_dir() and args.build:
            build = run_build(root)
            if build.get("exitCode") != 0:
                raise SmokeError("tauri:build failed; see build.stdoutTail/build.stderrTail in evidence")
        if not app_bundle.is_dir():
            raise SmokeError(f"app bundle not found: {repo_relative_path(app_bundle, root)}; rerun with --build to create it")

        dev_server_check = assert_dev_server_absent(args.dev_server_url)
        bundle = inspect_bundle(root, app_bundle)
        bundle_failures = validate_bundle(bundle)
        if bundle_failures:
            raise SmokeError("app bundle metadata invalid: " + "; ".join(bundle_failures))

        executable = root / bundle["binary"]["path"]
        process = launch_app_executable(root, executable)
        launch.update(
            {
                "pid": process.pid,
                "executablePath": bundle["binary"]["path"],
                "appBundlePath": bundle["app"]["path"],
            }
        )
        window = wait_for_window(process=process, timeout_seconds=args.timeout)
        if args.settle_seconds > 0:
            time.sleep(args.settle_seconds)
        screenshot = capture_window_screenshot(window, screenshot_path, root)
    except Exception as exc:  # noqa: BLE001
        blocker = str(exc)
    finally:
        termination = terminate_app(process)

    status = "pass" if blocker is None and bundle and window and screenshot else "fail"
    evidence = build_evidence(
        status=status,
        started_at=started_at,
        app_bundle=app_bundle,
        bundle=bundle,
        build=build,
        dev_server_check=dev_server_check,
        launch=launch,
        window=window,
        screenshot=screenshot,
        termination=termination,
        blocker=blocker,
    )
    write_json(evidence_path, evidence)
    if status == "pass":
        print(f"PASS installed macOS app smoke: wrote {repo_relative_path(evidence_path, root)}")
        return 0
    print(f"FAIL installed macOS app smoke: {blocker}", file=sys.stderr)
    print(f"wrote failure evidence to {repo_relative_path(evidence_path, root)}", file=sys.stderr)
    return 1


def resolve_repo_path(path: Path, root: Path) -> Path:
    return path if path.is_absolute() else root / path


def normalized_platform() -> str:
    system = platform.system().lower()
    return "macos" if system == "darwin" else system


def require_tool(name: str) -> None:
    result = subprocess.run(["/usr/bin/which", name], text=True, capture_output=True)
    if result.returncode != 0:
        raise SmokeError(f"required tool not found on PATH: {name}")


def run_build(root: Path) -> dict[str, Any]:
    started = iso_timestamp()
    result = subprocess.run(
        ["npm", "--prefix", "apps/desktop", "run", "tauri:build"],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=600,
    )
    return {
        "requested": True,
        "ran": True,
        "command": "npm --prefix apps/desktop run tauri:build",
        "startedAt": started,
        "completedAt": iso_timestamp(),
        "exitCode": result.returncode,
        "stdoutTail": tail_text(result.stdout),
        "stderrTail": tail_text(result.stderr),
    }


def assert_dev_server_absent(url: str) -> dict[str, Any]:
    observed_at = iso_timestamp()
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            raise SmokeError(f"dev server URL was reachable before packaged launch: {url} status={response.status}")
    except SmokeError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "url": url,
            "checkedBeforeLaunch": True,
            "reachableBeforeLaunch": False,
            "runnerStartedDevServer": False,
            "observedAt": observed_at,
            "error": f"{type(exc).__name__}: {exc}",
        }


def inspect_bundle(root: Path, app_bundle: Path) -> dict[str, Any]:
    info_path = app_bundle / "Contents" / "Info.plist"
    if not info_path.is_file():
        raise SmokeError(f"Info.plist not found: {repo_relative_path(info_path, root)}")
    with info_path.open("rb") as handle:
        info = plistlib.load(handle)
    if not isinstance(info, dict):
        raise SmokeError("Info.plist root must be a dictionary")
    executable_name = info.get("CFBundleExecutable")
    if not isinstance(executable_name, str) or not executable_name:
        raise SmokeError("Info.plist CFBundleExecutable is missing")
    binary_path = app_bundle / "Contents" / "MacOS" / executable_name
    if not binary_path.is_file():
        raise SmokeError(f"main executable not found: {repo_relative_path(binary_path, root)}")
    dmg_artifacts = find_dmg_artifacts(root)
    return {
        "app": directory_artifact(app_bundle, root),
        "binary": file_artifact(binary_path, root),
        "dmg": dmg_artifacts[0] if dmg_artifacts else None,
        "dmgs": dmg_artifacts,
        "infoPlist": {
            "path": repo_relative_path(info_path, root),
            "CFBundleName": info.get("CFBundleName"),
            "CFBundleDisplayName": info.get("CFBundleDisplayName"),
            "CFBundleShortVersionString": info.get("CFBundleShortVersionString"),
            "CFBundleVersion": info.get("CFBundleVersion"),
            "CFBundleIdentifier": info.get("CFBundleIdentifier"),
            "CFBundleExecutable": info.get("CFBundleExecutable"),
            "CFBundlePackageType": info.get("CFBundlePackageType"),
            "LSMinimumSystemVersion": info.get("LSMinimumSystemVersion"),
        },
        "expected": {
            "productName": "LizzieYzy Next",
            "version": "0.1.0",
            "identifier": "org.lizzieyzy.next",
            "mainExecutable": "lizzieyzy-next-desktop",
            "packageType": "APPL",
        },
        "signature": inspect_signature(app_bundle),
    }


def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    info = bundle.get("infoPlist")
    expected = bundle.get("expected")
    if not isinstance(info, dict) or not isinstance(expected, dict):
        return ["bundle evidence missing infoPlist/expected"]
    checks = {
        "productName": info.get("CFBundleName") == expected.get("productName")
        or info.get("CFBundleDisplayName") == expected.get("productName"),
        "version": info.get("CFBundleShortVersionString") == expected.get("version"),
        "identifier": info.get("CFBundleIdentifier") == expected.get("identifier"),
        "mainExecutable": info.get("CFBundleExecutable") == expected.get("mainExecutable"),
        "packageType": info.get("CFBundlePackageType") == expected.get("packageType"),
    }
    return [f"{name} mismatch" for name, passed in checks.items() if not passed]


def find_dmg_artifacts(root: Path) -> list[dict[str, Any]]:
    dmg_dir = root / "target" / "release" / "bundle" / "dmg"
    if not dmg_dir.is_dir():
        return []
    return [file_artifact(path, root) for path in sorted(dmg_dir.glob("*.dmg")) if path.is_file()]


def file_artifact(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": repo_relative_path(path, root),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def directory_artifact(path: Path, root: Path) -> dict[str, Any]:
    files = sorted(item for item in path.rglob("*") if item.is_file())
    digest = hashlib.sha256()
    total = 0
    for item in files:
        relative = item.relative_to(path).as_posix()
        size = item.stat().st_size
        total += size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(sha256_file(item).encode("ascii"))
        digest.update(b"\0")
    return {
        "path": repo_relative_path(path, root),
        "sha256": digest.hexdigest(),
        "bytes": total,
        "fileCount": len(files),
    }


def inspect_signature(app_bundle: Path) -> dict[str, Any]:
    display = run_status(["codesign", "-dv", "--verbose=4", str(app_bundle)])
    verify = run_status(["codesign", "--verify", "--deep", "--strict", "--verbose=4", str(app_bundle)])
    spctl = run_status(["spctl", "-a", "-vv", str(app_bundle)])
    display_text = "\n".join([display.get("stdout", ""), display.get("stderr", "")])
    spctl_text = "\n".join([spctl.get("stdout", ""), spctl.get("stderr", "")])
    return {
        "codesignDisplay": scrub_command_result(display),
        "codesignVerify": scrub_command_result(verify),
        "spctlAssess": scrub_command_result(spctl),
        "signatureKind": signature_kind(display_text),
        "spctlAccepted": spctl.get("exitCode") == 0,
        "spctlRawSummary": tail_text(scrub_paths(spctl_text), limit=2000),
        "productionSigned": False,
        "notarized": False,
        "releasePublished": False,
        "scopeNote": "This smoke records local packaged-app launchability only. It does not claim Developer ID signing, notarization, or published production release status.",
    }


def run_status(cmd: list[str]) -> dict[str, Any]:
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
    return {
        "command": " ".join(cmd[:4]),
        "exitCode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def scrub_command_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "command": scrub_paths(str(result.get("command", ""))),
        "exitCode": result.get("exitCode"),
        "stdoutTail": tail_text(scrub_paths(str(result.get("stdout", "")))),
        "stderrTail": tail_text(scrub_paths(str(result.get("stderr", "")))),
    }


def signature_kind(text: str) -> str:
    if "Signature=adhoc" in text or "flags=0x20002(adhoc" in text:
        return "adhoc"
    if "Authority=Developer ID Application" in text:
        return "developer-id"
    if "Authority=" in text:
        return "signed-other"
    return "unsigned-or-unknown"


def launch_app_executable(root: Path, executable: Path) -> subprocess.Popen[str]:
    if not executable.is_file():
        raise SmokeError(f"main executable not found: {repo_relative_path(executable, root)}")
    log_path = root / ".tmp" / "installed-macos-app-smoke.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("VITE_LIZZIEYZY_RUNTIME_SMOKE") or key.startswith("LIZZIEYZY_RUNTIME_SMOKE"):
            env.pop(key, None)
    env["LIZZIEYZY_INSTALLED_APP_SMOKE"] = "1"
    try:
        process = subprocess.Popen(
            [str(executable)],
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


def terminate_app(process: subprocess.Popen[str] | None, *, grace_seconds: float = 5.0) -> dict[str, Any]:
    if process is None:
        return {"attempted": False, "terminated": False, "exitCode": None}
    if process.poll() is not None:
        return {"attempted": False, "terminated": True, "exitCode": process.returncode, "alreadyExited": True}
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return {"attempted": True, "terminated": True, "exitCode": process.poll(), "processMissing": True}
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return {"attempted": True, "method": "SIGTERM", "terminated": True, "exitCode": process.returncode}
        time.sleep(0.1)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return {"attempted": True, "terminated": True, "exitCode": process.poll(), "processMissing": True}
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return {"attempted": True, "method": "SIGKILL", "terminated": True, "exitCode": process.returncode}
        time.sleep(0.1)
    return {"attempted": True, "method": "SIGKILL", "terminated": False, "exitCode": process.poll()}


def wait_for_window(*, process: subprocess.Popen[str], timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SmokeError(f"packaged app exited before showing a window (exit {process.returncode})")
        windows = list_installed_app_windows(owner_pid=process.pid)
        if windows:
            return windows[0]
        time.sleep(0.5)
    raise SmokeError(f"timed out after {timeout_seconds:g}s waiting for packaged app window for pid {process.pid}")


def list_installed_app_windows(*, owner_pid: int | None = None) -> list[dict[str, Any]]:
    script = r'''
import CoreGraphics
import Foundation

let matchers = ["LizzieYzy Next", "lizzieyzy-next-desktop", "LizzieYzy"]
let expectedPid = Int(CommandLine.arguments.dropFirst().first ?? "")
let options = CGWindowListOption(arrayLiteral: .optionOnScreenOnly, .excludeDesktopElements)
let info = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] ?? []
var matches: [[String: Any]] = []

for item in info {
    let owner = item[kCGWindowOwnerName as String] as? String ?? ""
    let title = item[kCGWindowName as String] as? String ?? ""
    let pid = item[kCGWindowOwnerPID as String] as? Int ?? 0
    let haystack = owner + " " + title
    let matched = matchers.contains { haystack.localizedCaseInsensitiveContains($0) }
    let layer = item[kCGWindowLayer as String] as? Int ?? 0
    let windowId = item[kCGWindowNumber as String] as? Int ?? 0
    guard matched && layer == 0 && windowId > 0 && (expectedPid == nil || pid == expectedPid!) else {
        continue
    }
    var row: [String: Any] = [
        "windowId": windowId,
        "ownerPid": pid,
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
    command = ["swift", "-e", script]
    if owner_pid is not None:
        command.append(str(owner_pid))
    result = subprocess.run(command, text=True, capture_output=True, timeout=20)
    if result.returncode != 0:
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        raise SmokeError(f"failed to query macOS windows via CoreGraphics: {combined}")
    value = json.loads(result.stdout or "[]")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def capture_window_screenshot(window: dict[str, Any], screenshot_path: Path, root: Path) -> dict[str, Any]:
    window_id = window.get("windowId")
    if not isinstance(window_id, int) or window_id <= 0:
        raise SmokeError("matched packaged app window is missing a valid CoreGraphics windowId")
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
        "name": "installed-macos-app-window",
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
    app_bundle: Path,
    bundle: dict[str, Any] | None,
    build: dict[str, Any],
    dev_server_check: dict[str, Any],
    launch: dict[str, Any],
    window: dict[str, Any] | None,
    screenshot: dict[str, Any] | None,
    termination: dict[str, Any],
    blocker: str | None,
) -> dict[str, Any]:
    bundle_observed = bundle is not None
    screenshot_observed = screenshot is not None and screenshot.get("bytes", 0) > 1024 and bool(screenshot.get("sha256"))
    launched = isinstance(launch.get("pid"), int)
    window_observed = window is not None
    dev_server_absent = dev_server_check.get("reachableBeforeLaunch") is False
    failures = [blocker] if blocker else []
    if not bundle_observed:
        failures.append("packaged app bundle was not inspected")
    if not screenshot_observed:
        failures.append("packaged app window screenshot was not captured")
    if dev_server_check and not dev_server_absent:
        failures.append("dev server absence was not confirmed before launch")
    return {
        "schema": SCHEMA,
        "name": "installed_macos_app_smoke",
        "status": "pass" if status == "pass" and not failures else "fail",
        "platform": normalized_platform(),
        "startedAt": started_at,
        "completedAt": iso_timestamp(),
        "collectionMethod": "packaged-app-executable-coregraphics-window-screencapture",
        "appBundlePath": repo_relative_path(app_bundle, ROOT),
        "appBundle": validator_app_bundle(bundle),
        "launched": launched,
        "windowObserved": window_observed,
        "screenshotObserved": screenshot_observed,
        "devServerAbsent": dev_server_absent,
        "build": build,
        "devServerPreflight": dev_server_check,
        "runnerStartedViteDevServer": False,
        "bundle": bundle,
        "launch": launch,
        "window": sanitize_window(window),
        "screenshots": [screenshot] if screenshot is not None else [],
        "codesign": bundle.get("signature") if isinstance(bundle, dict) else None,
        "productionSigned": False,
        "notarized": False,
        "releasePublished": False,
        "boundaries": {
            "productionSigned": False,
            "notarized": False,
            "releasePublished": False,
            "viteDevServerStarted": False,
            "nativeDialogClickCovered": False,
            "webviewDomClickCovered": False,
            "note": "This smoke proves a local packaged .app can launch and display a macOS window. It does not claim signing, notarization, native dialog coverage, WebView DOM coverage, or production release publication.",
        },
        "termination": termination,
        "checks": [
            {
                "name": "dev_server_absent_before_launch",
                "status": "pass" if dev_server_check.get("reachableBeforeLaunch") is False else "fail",
                "details": dev_server_check,
            },
            {
                "name": "bundle_metadata",
                "status": "pass" if bundle_observed and not validate_bundle(bundle) else "fail",
                "details": bundle,
            },
            {
                "name": "packaged_app_window_screenshot",
                "status": "pass" if screenshot_observed else "fail",
                "details": {"window": sanitize_window(window), "screenshot": screenshot},
            },
            {
                "name": "signature_boundaries",
                "status": "pass",
                "details": {
                    "productionSigned": False,
                    "notarized": False,
                    "releasePublished": False,
                },
            },
            {
                "name": "app_terminated",
                "status": "pass" if termination.get("terminated") is True else "fail",
                "details": termination,
            },
        ],
        "failures": failures,
}


def validator_app_bundle(bundle: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(bundle, dict):
        return None
    app = bundle.get("app")
    info = bundle.get("infoPlist")
    if not isinstance(app, dict):
        return None
    return {
        "exists": True,
        "path": app.get("path"),
        "sizeBytes": app.get("bytes"),
        "sha256": app.get("sha256"),
        "fileCount": app.get("fileCount"),
        "productName": info.get("CFBundleName") if isinstance(info, dict) else None,
        "version": info.get("CFBundleShortVersionString") if isinstance(info, dict) else None,
        "identifier": info.get("CFBundleIdentifier") if isinstance(info, dict) else None,
        "mainExecutable": info.get("CFBundleExecutable") if isinstance(info, dict) else None,
    }


def sanitize_window(window: dict[str, Any] | None) -> dict[str, Any] | None:
    if window is None:
        return None
    return {
        "windowId": window.get("windowId"),
        "ownerPid": window.get("ownerPid"),
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


def scrub_paths(value: str) -> str:
    return value.replace(str(ROOT.resolve()), "<repo>").replace(str(ROOT), "<repo>")


def tail_text(value: str, *, limit: int = 4000) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[-limit:]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iso_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    raise SystemExit(main())
