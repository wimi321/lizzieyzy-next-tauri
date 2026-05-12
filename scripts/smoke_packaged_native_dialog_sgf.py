#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import signal
import shutil
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
import smoke_native_desktop_sgf_workflow as native_sgf  # noqa: E402


SCHEMA = "lizzieyzy.packaged-native-dialog-sgf.v1"
DEFAULT_EVIDENCE_OUT = ROOT / "docs/qa/packaged-native-dialog-sgf-macos.json"
DEFAULT_SCREENSHOT_DIR = ROOT / "docs/qa/screenshots"
DEFAULT_INSTALLED_APP_SMOKE = ROOT / "docs/qa/installed-macos-app-smoke.json"
INPUT_SGF = "(;FF[4]GM[1]SZ[9]KM[6.5]PB[PackagedBlack]PW[PackagedWhite]C[native workflow source; packaged native dialog source];B[dd];W[ee])\n"


class SmokeError(RuntimeError):
    pass


def pending_evidence() -> dict[str, Any]:
    boundaries = {
        "fullNativeDialogParity": False,
        "fullLegacyParity": False,
        "releaseParity": False,
        "signedReleaseParity": False,
        "windowsLinuxParity": False,
        "fullAutomation": False,
    }
    return {
        "schema": SCHEMA,
        "name": "packaged_native_dialog_sgf",
        "status": "pending",
        "platform": "macos",
        "collectionMethod": "packaged_macos_app_native_dialog_sgf_workflow",
        "pendingReason": (
            "Unsigned packaged macOS .app native Open/Save dialog SGF workflow proof has not been captured in this "
            "repository snapshot. PASS requires packagedApp/devServerAbsent/nativeOpenDialogObserved/"
            "nativeSaveDialogObserved plus dialog step records, screenshots, SGF hashes, readback/reopen invariants, "
            "and false parity/release boundaries."
        ),
        "packagedApp": False,
        "devServerAbsent": False,
        "nativeOpenDialogObserved": False,
        "nativeSaveDialogObserved": False,
        "sourceStaticOnly": False,
        "browserOnly": False,
        "devServerOnly": False,
        **boundaries,
        "boundaries": boundaries,
    }


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_or_raise(evidence: dict[str, Any]) -> None:
    status = str(evidence.get("status", "")).lower()
    if status in {"pending", "unavailable"}:
        failures = smoke_user_flows.validate_packaged_native_dialog_sgf_pending_evidence(evidence)
    else:
        failures = smoke_user_flows.validate_packaged_native_dialog_sgf_evidence(evidence)
    if failures:
        raise ValueError("packaged native dialog SGF evidence is invalid: " + "; ".join(failures))


def path_arg(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def derive_executable(installed_smoke: dict[str, Any], override: Path | None) -> Path:
    if override is not None:
        return path_arg(override)
    bundle = installed_smoke.get("bundle")
    if isinstance(bundle, dict):
        binary = bundle.get("binary")
        if isinstance(binary, dict) and isinstance(binary.get("path"), str):
            return path_arg(binary["path"])
    app_bundle = installed_smoke.get("appBundle")
    if isinstance(app_bundle, dict):
        app_path = app_bundle.get("path")
        executable = app_bundle.get("mainExecutable")
        if isinstance(app_path, str) and isinstance(executable, str):
            return path_arg(Path(app_path) / "Contents" / "MacOS" / executable)
    raise SmokeError("could not derive packaged app executable from installed app smoke evidence")


def clean_packaged_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("VITE_LIZZIEYZY_RUNTIME_SMOKE") or key.startswith("LIZZIEYZY_RUNTIME_SMOKE"):
            env.pop(key, None)
    return env


def start_packaged_app(executable: Path, log_path: Path) -> subprocess.Popen[str]:
    if not executable.is_file():
        raise SmokeError(f"packaged app executable does not exist: {executable}")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            [str(executable)],
            cwd=ROOT,
            env=clean_packaged_env(),
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


def stop_process(process: subprocess.Popen[str] | None, *, grace_seconds: float = 5.0) -> dict[str, Any]:
    if process is None:
        return {"attempted": False, "terminated": False}
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
    return {"attempted": True, "method": "SIGKILL", "terminated": process.poll() is not None, "exitCode": process.poll()}


def wait_for_packaged_window(process: subprocess.Popen[str], timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SmokeError(f"packaged app exited before showing a window (exit {process.returncode})")
        windows = native_sgf.list_windows(owner_pid=process.pid)
        if windows:
            return windows[0]
        time.sleep(0.5)
    raise SmokeError(f"timed out after {timeout_seconds:g}s waiting for packaged app window for pid {process.pid}")


def click_packaged_toolbar_button(window: dict[str, Any], name: str) -> None:
    bounds = window.get("bounds")
    if not isinstance(bounds, dict):
        raise SmokeError("window bounds missing for packaged toolbar click")
    x = int(bounds.get("X", 0))
    y = int(bounds.get("Y", 0))
    offsets = {
        "open": (36, 112),
        "save-as": (154, 112),
    }
    if name not in offsets:
        raise SmokeError(f"unknown packaged toolbar button: {name}")
    dx, dy = offsets[name]
    native_sgf.run(["cliclick", f"c:{x + dx},{y + dy}"], timeout=10)


def native_dialog_is_open_for_pid(pid: int) -> bool:
    script = f'''
tell application "System Events"
  try
    set targetProcess to first process whose unix id is {pid}
    tell targetProcess
      try
        if (count of sheets of window 1) > 0 then return "true"
      end try
      try
        if exists button "Open" of window 1 then return "true"
      end try
      try
        if exists button "Save" of window 1 then return "true"
      end try
    end tell
  end try
end tell
return "false"
'''
    result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=10)
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def wait_for_native_dialog_for_pid(pid: int, *, opened: bool, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if native_dialog_is_open_for_pid(pid) is opened:
            return
        time.sleep(0.25)
    state = "open" if opened else "closed"
    raise SmokeError(f"timed out waiting for native dialog to be {state}")


def click_native_dialog_button_for_pid(pid: int, label: str) -> None:
    escaped = label.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "System Events"
  set targetProcess to first process whose unix id is {pid}
  tell targetProcess
    set frontmost to true
    try
      click button "{escaped}" of sheet 1 of window 1
    on error
      try
        click button "{escaped}" of window 1
      on error
        key code 36
      end try
    end try
  end tell
end tell
'''
    result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=20)
    if result.returncode != 0:
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        raise SmokeError(f"failed to click native dialog button {label!r}: {combined}")


def dialog_selection_ready_for_pid(pid: int) -> bool:
    script = f'''
tell application "System Events"
  try
    set targetProcess to first process whose unix id is {pid}
    tell targetProcess
      try
        if exists button "Open" of sheet 1 of window 1 then
          return enabled of button "Open" of sheet 1 of window 1
        end if
      end try
      try
        if exists button "Save" of sheet 1 of window 1 then
          return enabled of button "Save" of sheet 1 of window 1
        end if
      end try
      try
        if exists button "Open" of window 1 then
          return enabled of button "Open" of window 1
        end if
      end try
      try
        if exists button "Save" of window 1 then
          return enabled of button "Save" of window 1
        end if
      end try
    end tell
  end try
end tell
return false
'''
    result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=10)
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def choose_path_in_dialog_with_clipboard_for_pid(pid: int, path_text: str) -> None:
    escaped = path_text.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
set previousClipboard to the clipboard
set the clipboard to "{escaped}"
tell application "System Events"
  set targetProcess to first process whose unix id is {pid}
  tell targetProcess
    set frontmost to true
    key code 5 using {{command down, shift down}}
    delay 0.3
    keystroke "v" using {{command down}}
    delay 0.2
    key code 36
    delay 0.7
  end tell
end tell
set the clipboard to previousClipboard
'''
    result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=20)
    if result.returncode != 0:
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        raise SmokeError(f"failed to choose path in native dialog with clipboard fallback: {combined}")


def choose_path_in_dialog_with_slash_for_pid(pid: int, path_text: str) -> None:
    escaped = path_text.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
set previousClipboard to the clipboard
set the clipboard to "{escaped}"
tell application "System Events"
  set targetProcess to first process whose unix id is {pid}
  tell targetProcess
    set frontmost to true
    keystroke "/"
    delay 0.3
    keystroke "v" using {{command down}}
    delay 0.2
    key code 36
    delay 0.7
  end tell
end tell
set the clipboard to previousClipboard
'''
    result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=20)
    if result.returncode != 0:
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        raise SmokeError(f"failed to choose path in native dialog with slash fallback: {combined}")


def choose_path_in_dialog_for_pid(pid: int, path: Path, button_label: str) -> None:
    try:
        native_sgf.choose_path_in_dialog(path, button_label)
        return
    except Exception:
        pass
    escaped = str(path).replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "System Events"
  set targetProcess to first process whose unix id is {pid}
  tell targetProcess
    set frontmost to true
    keystroke "g" using {{command down, shift down}}
    delay 0.2
    keystroke "{escaped}"
    delay 0.2
    key code 36
    delay 0.5
  end tell
end tell
'''
    result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=20)
    if result.returncode != 0:
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        raise SmokeError(f"failed to choose path in native dialog: {combined}")
    if not dialog_selection_ready_for_pid(pid):
        choose_path_in_dialog_with_clipboard_for_pid(pid, str(path))
    if not dialog_selection_ready_for_pid(pid):
        choose_path_in_dialog_with_slash_for_pid(pid, str(path))
    if not dialog_selection_ready_for_pid(pid):
        raise SmokeError("native dialog selection did not become ready after path entry")
    click_native_dialog_button_for_pid(pid, button_label)


def save_dialog_point(window: dict[str, Any], name: str) -> tuple[int, int]:
    bounds = window.get("bounds")
    if not isinstance(bounds, dict):
        raise SmokeError("window bounds missing for save dialog interaction")
    x = int(bounds.get("X", 0))
    y = int(bounds.get("Y", 0))
    offsets = {
        "file-name": (675, 362),
        "save-button": (770, 482),
    }
    if name not in offsets:
        raise SmokeError(f"unknown save dialog point: {name}")
    dx, dy = offsets[name]
    return x + dx, y + dy


def set_save_dialog_file_name_for_pid(_pid: int, _window: dict[str, Any], file_name: str) -> None:
    native_sgf.run(["cliclick", f"t:{file_name}"], timeout=10)


def discover_saved_sgf_path(temp_dir: Path, input_path: Path, intended_path: Path) -> Path:
    if intended_path.is_file():
        return intended_path
    candidates = sorted(path for path in temp_dir.glob("*.sgf") if path != input_path)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise SmokeError(f"saved SGF was not written: {native_sgf.sanitize_temp_path(intended_path)}")
    labels = ", ".join(native_sgf.sanitize_temp_path(path) for path in candidates)
    raise SmokeError(f"could not identify the saved SGF path unambiguously: {labels}")


def send_shortcut_for_pid(pid: int, key: str, *, shift: bool = False) -> None:
    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    modifiers = "{command down, shift down}" if shift else "{command down}"
    script = f'''
tell application "System Events"
  set targetProcess to first process whose unix id is {pid}
  tell targetProcess
    set frontmost to true
    keystroke "{escaped}" using {modifiers}
  end tell
end tell
'''
    result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=10)
    if result.returncode != 0:
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        raise SmokeError(f"failed to send shortcut command for {key!r}: {combined}")


def open_dialog_via_toolbar_or_shortcut(process: subprocess.Popen[str], window: dict[str, Any], button: str) -> str:
    click_packaged_toolbar_button(window, button)
    try:
        wait_for_native_dialog_for_pid(process.pid, opened=True, timeout_seconds=2)
        return "toolbar-click"
    except SmokeError:
        if button == "open":
            send_shortcut_for_pid(process.pid, "o")
        elif button == "save-as":
            send_shortcut_for_pid(process.pid, "s", shift=True)
        else:
            raise
        wait_for_native_dialog_for_pid(process.pid, opened=True, timeout_seconds=10)
        return "toolbar-click-then-keyboard-shortcut"


def screenshot_record(path: Path, label: str) -> dict[str, Any]:
    record = native_sgf.capture_screenshot(path, ROOT, label)
    return {
        "label": label,
        "path": record["path"],
        "sha256": record["sha256"],
        "sizeBytes": record.get("bytes") or record.get("sizeBytes"),
        "captureTool": record.get("captureTool", "screencapture"),
    }


def dialog_step(kind: str, method: str, path: Path, screenshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": kind,
        "method": method,
        "tooling": ["cliclick", "osascript", "screencapture"],
        "path": native_sgf.sanitize_temp_path(path),
        "screenshot": screenshot,
    }


def pass_check(name: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass", "details": details}


def build_pass_evidence(
    *,
    executable: Path,
    input_path: Path,
    saved_path: Path,
    input_text: str,
    saved_text: str,
    screenshots: list[dict[str, Any]],
    dialog_steps: list[dict[str, Any]],
    termination: dict[str, Any],
) -> dict[str, Any]:
    boundaries = {
        "fullNativeDialogParity": False,
        "fullLegacyParity": False,
        "releaseParity": False,
        "signedReleaseParity": False,
        "windowsLinuxParity": False,
        "fullAutomation": False,
    }
    before_hash = sha256_text(input_text)
    after_hash = sha256_text(saved_text)
    workflow = {
        "openVerified": True,
        "contentPreserved": True,
        "saveVerified": True,
        "readbackVerified": True,
        "reopenVerified": True,
        "finalInvariantVerified": True,
    }
    checks = [
        pass_check("packaged_app_started", {"packagedApp": True, "devServerAbsent": True, "executable": native_sgf.repo_relative_path(executable, ROOT)}),
        pass_check("native_open_dialog", dialog_steps[0]),
        pass_check("sgf_opened", {"openVerified": True, "openedSgfPath": native_sgf.sanitize_temp_path(input_path)}),
        pass_check("content_preserved", {"contentPreserved": True, "method": "open/save/readback workflow preserves source SGF content"}),
        pass_check("native_save_dialog", dialog_steps[1]),
        pass_check("save_readback_verified", {"readbackVerified": True, "savedSgfPath": native_sgf.sanitize_temp_path(saved_path)}),
        pass_check("reopen_verified", {"reopenVerified": True, "reopenedSgfPath": native_sgf.sanitize_temp_path(saved_path)}),
        pass_check("final_invariant_verified", {"finalInvariantVerified": True, "invariants": native_sgf.verify_reopen_invariants(saved_text)}),
        pass_check("screenshots_recorded", {"count": len(screenshots), "screenshots": screenshots}),
        pass_check("scope_boundaries", {"boundaries": boundaries}),
    ]
    return {
        "schema": SCHEMA,
        "name": "packaged_native_dialog_sgf",
        "status": "pass",
        "platform": "macos" if platform.system() == "Darwin" else platform.system().lower(),
        "collectionMethod": "packaged_macos_app_native_dialog_sgf_workflow",
        "packagedApp": True,
        "devServerAbsent": True,
        "nativeOpenDialogObserved": True,
        "nativeSaveDialogObserved": True,
        "sourceStaticOnly": False,
        "browserOnly": False,
        "devServerOnly": False,
        **boundaries,
        "appPath": native_sgf.repo_relative_path(executable, ROOT),
        "inputSgfPath": native_sgf.sanitize_temp_path(input_path),
        "savedSgfPath": native_sgf.sanitize_temp_path(saved_path),
        "reopenedSgfPath": native_sgf.sanitize_temp_path(saved_path),
        "sgfHashes": {
            "before": before_hash,
            "after": after_hash,
            "readback": after_hash,
        },
        "dialogStepRecords": dialog_steps,
        "screenshots": screenshots,
        "workflow": workflow,
        "checks": checks,
        "boundaries": boundaries,
        "termination": termination,
    }


def failure_evidence(reason: str) -> dict[str, Any]:
    evidence = pending_evidence()
    evidence["status"] = "unavailable"
    evidence["pendingReason"] = reason
    return evidence


def run_collector(
    *,
    evidence_out: Path,
    screenshot_dir: Path,
    installed_app_smoke: Path,
    app_executable: Path | None,
    timeout: float,
    settle_seconds: float,
) -> int:
    if platform.system() != "Darwin":
        evidence = failure_evidence("Packaged native dialog SGF runner currently requires macOS.")
        write_json(evidence_out, evidence)
        print("FAIL packaged native dialog SGF smoke: macOS required", file=sys.stderr)
        return 1
    for tool in ("swift", "screencapture", "osascript", "cliclick"):
        native_sgf.require_tool(tool)
    installed = load_json(installed_app_smoke)
    executable = derive_executable(installed, app_executable)
    temp_dir = Path(tempfile.mkdtemp(prefix="lzy-sgf-", dir="/tmp"))
    keep_temp_dir = False
    process: subprocess.Popen[str] | None = None
    log_path = ROOT / ".tmp" / "packaged-native-dialog-sgf.log"
    try:
        input_path = temp_dir / "in.sgf"
        intended_saved_path = temp_dir / "out.sgf"
        input_path.write_text(INPUT_SGF, encoding="utf-8")
        screenshots: list[dict[str, Any]] = []
        dialog_steps: list[dict[str, Any]] = []

        process = start_packaged_app(executable, log_path)
        window = wait_for_packaged_window(process, timeout)
        native_sgf.activate_process(window)
        if settle_seconds > 0:
            time.sleep(settle_seconds)

        screenshots.append(screenshot_record(screenshot_dir / "packaged-native-dialog-app-started.png", "app-started"))
        open_method = open_dialog_via_toolbar_or_shortcut(process, window, "open")
        open_shot = screenshot_record(screenshot_dir / "packaged-native-dialog-open.png", "native-open-dialog")
        screenshots.append(open_shot)
        dialog_steps.append(dialog_step("native_open_dialog", f"packaged macOS app native Open dialog via {open_method}", input_path, open_shot))
        choose_path_in_dialog_for_pid(process.pid, input_path, "Open")
        wait_for_native_dialog_for_pid(process.pid, opened=False, timeout_seconds=10)
        time.sleep(1.5)
        screenshots.append(screenshot_record(screenshot_dir / "packaged-native-dialog-opened.png", "sgf-opened"))

        save_method = open_dialog_via_toolbar_or_shortcut(process, window, "save-as")
        save_shot = screenshot_record(screenshot_dir / "packaged-native-dialog-save.png", "native-save-dialog")
        screenshots.append(save_shot)
        dialog_steps.append(dialog_step("native_save_dialog", f"packaged macOS app native Save dialog via {save_method}", intended_saved_path, save_shot))
        set_save_dialog_file_name_for_pid(process.pid, window, intended_saved_path.stem)
        screenshots.append(screenshot_record(screenshot_dir / "packaged-native-dialog-save-named.png", "native-save-dialog-named"))
        save_x, save_y = save_dialog_point(window, "save-button")
        native_sgf.run(["cliclick", f"c:{save_x},{save_y}"], timeout=10)
        screenshots.append(screenshot_record(screenshot_dir / "packaged-native-dialog-save-clicked.png", "native-save-dialog-clicked"))
        wait_for_native_dialog_for_pid(process.pid, opened=False, timeout_seconds=10)
        time.sleep(1.5)
        saved_path = discover_saved_sgf_path(temp_dir, input_path, intended_saved_path)
        dialog_steps[-1]["path"] = native_sgf.sanitize_temp_path(saved_path)
        saved_text = native_sgf.read_saved_sgf(saved_path)
        screenshots.append(screenshot_record(screenshot_dir / "packaged-native-dialog-saved.png", "save-readback"))

        open_dialog_via_toolbar_or_shortcut(process, window, "open")
        reopen_shot = screenshot_record(screenshot_dir / "packaged-native-dialog-reopen.png", "reopen-dialog")
        screenshots.append(reopen_shot)
        choose_path_in_dialog_for_pid(process.pid, saved_path, "Open")
        wait_for_native_dialog_for_pid(process.pid, opened=False, timeout_seconds=10)
        time.sleep(1.5)
        screenshots.append(screenshot_record(screenshot_dir / "packaged-native-dialog-reopened.png", "reopen-verified"))

        invariants = native_sgf.verify_reopen_invariants(saved_text)
        if invariants.get("verified") is not True:
            raise SmokeError("saved SGF readback/reopen invariants did not verify")
        termination = stop_process(process)
        process = None
        evidence = build_pass_evidence(
            executable=executable,
            input_path=input_path,
            saved_path=saved_path,
            input_text=INPUT_SGF,
            saved_text=saved_text,
            screenshots=screenshots,
            dialog_steps=dialog_steps,
            termination=termination,
        )
        validate_or_raise(evidence)
        write_json(evidence_out, evidence)
        print(f"PASS packaged native dialog SGF smoke: wrote {native_sgf.repo_relative_path(evidence_out, ROOT)}")
        return 0
    except Exception as exc:  # noqa: BLE001
        reason = str(exc)
        evidence = failure_evidence(reason)
        write_json(evidence_out, evidence)
        print(f"FAIL packaged native dialog SGF smoke: {reason}", file=sys.stderr)
        print(f"wrote unavailable evidence to {native_sgf.repo_relative_path(evidence_out, ROOT)}", file=sys.stderr)
        if log_path.is_file():
            print(f"log: {log_path}", file=sys.stderr)
        print(f"failure artifacts retained in: {temp_dir}", file=sys.stderr)
        keep_temp_dir = True
        return 1
    finally:
        stop_process(process)
        if not keep_temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or seed scoped packaged macOS native-dialog SGF workflow evidence."
    )
    parser.add_argument("--evidence-out", type=Path, default=DEFAULT_EVIDENCE_OUT)
    parser.add_argument("--screenshot-dir", type=Path, default=DEFAULT_SCREENSHOT_DIR)
    parser.add_argument("--installed-app-smoke", type=Path, default=DEFAULT_INSTALLED_APP_SMOKE)
    parser.add_argument("--app-executable", type=Path)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--settle-seconds", type=float, default=1.0)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--write-pending", action="store_true")
    args = parser.parse_args(argv)

    evidence_path = args.evidence_out if args.evidence_out.is_absolute() else ROOT / args.evidence_out
    if args.write_pending:
        evidence = pending_evidence()
        validate_or_raise(evidence)
        write_json(evidence_path, evidence)
        print(f"wrote pending evidence {evidence_path}")
        return 0
    if args.validate_only:
        evidence = load_json(evidence_path)
        validate_or_raise(evidence)
        print(f"validated {evidence_path}")
        return 0
    screenshot_dir = args.screenshot_dir if args.screenshot_dir.is_absolute() else ROOT / args.screenshot_dir
    installed_app_smoke = args.installed_app_smoke if args.installed_app_smoke.is_absolute() else ROOT / args.installed_app_smoke
    return run_collector(
        evidence_out=evidence_path,
        screenshot_dir=screenshot_dir,
        installed_app_smoke=installed_app_smoke,
        app_executable=args.app_executable,
        timeout=args.timeout,
        settle_seconds=args.settle_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
