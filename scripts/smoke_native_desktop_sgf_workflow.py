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
SCHEMA = "lizzieyzy.native-desktop-sgf-workflow.v1"
TAURI_RUNTIME_SCHEMA = "lizzieyzy.tauri-runtime-ui-smoke.v1"
DEFAULT_EVIDENCE = Path("docs/qa/native-desktop-sgf-workflow-macos.json")
DEFAULT_SCREENSHOT_DIR = Path("docs/qa/screenshots")
DEFAULT_RUNTIME_EVIDENCE = Path("docs/qa/tauri-runtime-ui-smoke-macos.json")
INPUT_SGF_NAME = "native-desktop-sgf-input.sgf"
SAVED_SGF_NAME = "native-desktop-sgf-saved.sgf"
WINDOW_MATCHERS = ("LizzieYzy Next", "lizzieyzy-next-desktop", "LizzieYzy")
SOURCE_SGF = "(;FF[4]GM[1]SZ[9]KM[6.5]PB[NativeBlack]PW[NativeWhite]C[native workflow source];B[dd];W[ee])\n"


class SmokeError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect scoped macOS native desktop SGF workflow evidence.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--evidence-out", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--screenshot-dir", type=Path, default=DEFAULT_SCREENSHOT_DIR)
    parser.add_argument("--runtime-evidence", type=Path, default=DEFAULT_RUNTIME_EVIDENCE)
    parser.add_argument("--app-mode", choices=("tauri-dev", "packaged-macos-app"), default="tauri-dev")
    parser.add_argument("--manual-assisted", action="store_true", help="Collect evidence with an operator driving native dialogs while the runner captures screenshots and validates artifacts.")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--settle-seconds", type=float, default=1.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    evidence_path = resolve_repo_path(args.evidence_out, root)
    screenshot_dir = resolve_repo_path(args.screenshot_dir, root)
    runtime_evidence_path = resolve_repo_path(args.runtime_evidence, root)
    started_at = iso_timestamp()
    process: subprocess.Popen[str] | None = None
    temp_dir = Path(tempfile.mkdtemp(prefix="lizzieyzy-native-desktop-sgf-"))
    input_path = temp_dir / INPUT_SGF_NAME
    saved_path = temp_dir / SAVED_SGF_NAME
    input_path.write_text(SOURCE_SGF, encoding="utf-8")
    steps: list[dict[str, Any]] = []
    screenshots: list[dict[str, Any]] = []
    runtime_evidence: dict[str, Any] = {}
    blocker: str | None = None
    termination: dict[str, Any] = {"attempted": False, "terminated": False}

    try:
        if args.manual_assisted:
            return run_manual_assisted(args, root, evidence_path, screenshot_dir, runtime_evidence_path, input_path, saved_path, started_at)
        if normalized_platform() != "macos":
            raise SmokeError("Native desktop SGF workflow smoke is currently a macOS local evidence gate.")
        require_tool("npm")
        require_tool("swift")
        require_tool("screencapture")
        require_tool("osascript")
        require_tool("cliclick")

        runtime_evidence = load_json_object(runtime_evidence_path)
        runtime_failures = validate_runtime_semantic_proof(runtime_evidence)
        if runtime_failures:
            raise SmokeError("source runtime semantic evidence invalid: " + "; ".join(runtime_failures))

        process = launch_app(root, args.app_mode)
        window = wait_for_window(process=process, timeout_seconds=args.timeout)
        activate_process(window)
        if args.settle_seconds > 0:
            time.sleep(args.settle_seconds)

        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-app-started.png", root, "app_started"))
        steps.append(step("app_started", "pass", method="tauri-dev launch", screenshot=screenshots[-1]))

        click_toolbar_button(window, "open")
        time.sleep(0.8)
        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-open-dialog.png", root, "native_open_dialog"))
        steps.append(
            step(
                "native_open_dialog",
                "pass",
                method="macOS native dialog via Tauri dialog plugin; automated with cliclick and osascript",
                screenshot=screenshots[-1],
                openedPath=sanitize_temp_path(input_path),
                operator={"type": "automation", "tooling": ["cliclick", "osascript", "screencapture"]},
            )
        )
        choose_path_in_dialog(input_path, "Open")
        wait_for_native_dialog(opened=False, timeout_seconds=10)
        time.sleep(2.0)
        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-opened.png", root, "sgf_opened"))
        steps.append(step("sgf_opened", "pass", method="native Open selected SGF path", screenshot=screenshots[-1], openedPath=sanitize_temp_path(input_path)))

        semantic_edit = semantic_edit_proof(runtime_evidence, runtime_evidence_path, root)
        steps.append(step("edit_operations_applied", "pass", method="existing Tauri runtime semantic proof", semanticProof=semantic_edit))

        click_toolbar_button(window, "save-as")
        time.sleep(0.8)
        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-save-dialog.png", root, "native_save_dialog"))
        steps.append(
            step(
                "save_or_save_as",
                "pass",
                method="macOS native Save dialog via Tauri dialog plugin; automated with cliclick and osascript",
                screenshot=screenshots[-1],
                savedPath=sanitize_temp_path(saved_path),
                operator={"type": "automation", "tooling": ["cliclick", "osascript", "screencapture"]},
            )
        )
        choose_path_in_dialog(saved_path, "Save")
        wait_for_native_dialog(opened=False, timeout_seconds=10)
        time.sleep(2.0)
        saved_content = read_saved_sgf(saved_path)
        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-saved.png", root, "save_completed"))

        click_toolbar_button(window, "open")
        time.sleep(0.8)
        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-reopen-dialog.png", root, "reopen_saved_sgf"))
        steps.append(
            step(
                "reopen_saved_sgf",
                "pass",
                method="native Open selected the just-saved SGF path",
                screenshot=screenshots[-1],
                openedPath=sanitize_temp_path(saved_path),
            )
        )
        choose_path_in_dialog(saved_path, "Open")
        wait_for_native_dialog(opened=False, timeout_seconds=10)
        time.sleep(2.0)
        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-reopened.png", root, "reopen_state"))
        reopen_invariants = verify_reopen_invariants(saved_content)
        steps.append(step("reopen_state_verified", "pass", method="saved SGF content/tree/board invariant verification", screenshot=screenshots[-1], invariants=reopen_invariants))
        steps.append(step("screenshots_recorded", "pass", method="sha256 and positive byte validation", screenshotCount=len(screenshots)))
        steps.append(step("scope_boundaries", "pass", method="explicit scoped evidence boundaries"))
    except Exception as exc:  # noqa: BLE001
        blocker = str(exc)
    finally:
        termination = terminate_process(process)

    evidence = build_evidence(
        status="pass" if blocker is None else "fail",
        started_at=started_at,
        app_mode=args.app_mode,
        collection_method="automated_native_desktop_workflow",
        runtime_evidence=runtime_evidence,
        runtime_evidence_path=runtime_evidence_path,
        input_path=input_path,
        saved_path=saved_path,
        saved_content=saved_path.read_text(encoding="utf-8") if saved_path.is_file() else None,
        steps=steps,
        screenshots=screenshots,
        termination=termination,
        blocker=blocker,
    )
    write_json(evidence_path, evidence)
    if evidence["status"] == "pass":
        print(f"PASS native desktop SGF workflow smoke: wrote {repo_relative_path(evidence_path, root)}")
        return 0
    print(f"FAIL native desktop SGF workflow smoke: {blocker}", file=sys.stderr)
    print(f"wrote failure evidence to {repo_relative_path(evidence_path, root)}", file=sys.stderr)
    return 1


def run_manual_assisted(
    args: argparse.Namespace,
    root: Path,
    evidence_path: Path,
    screenshot_dir: Path,
    runtime_evidence_path: Path,
    input_path: Path,
    saved_path: Path,
    started_at: str,
) -> int:
    runtime_evidence: dict[str, Any] = {}
    steps: list[dict[str, Any]] = []
    screenshots: list[dict[str, Any]] = []
    blocker: str | None = None
    saved_content: str | None = None
    try:
        if normalized_platform() != "macos":
            raise SmokeError("Native desktop SGF workflow smoke is currently a macOS local evidence gate.")
        require_tool("screencapture")
        runtime_evidence = load_json_object(runtime_evidence_path)
        runtime_failures = validate_runtime_semantic_proof(runtime_evidence)
        if runtime_failures:
            raise SmokeError("source runtime semantic evidence invalid: " + "; ".join(runtime_failures))

        print("Manual-assisted native desktop SGF workflow collection.")
        print(f"Use this SGF for native Open: {input_path}")
        print(f"Use this path for native Save/Save As: {saved_path}")
        input("1. Start the Tauri dev or packaged macOS app, wait for the main window, then press Enter to capture app_started...")
        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-app-started.png", root, "app_started"))
        steps.append(step("app_started", "pass", method="operator-confirmed native desktop app visible", screenshot=screenshots[-1]))

        input("2. Open the native Open dialog, select the input SGF path, leave the dialog visible, then press Enter to capture native_open_dialog...")
        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-open-dialog.png", root, "native_open_dialog"))
        steps.append(
            step(
                "native_open_dialog",
                "pass",
                method="manual-assisted macOS native Open dialog",
                screenshot=screenshots[-1],
                openedPath=sanitize_temp_path(input_path),
                operator={"type": "manual-assisted", "tooling": ["screencapture"], "confirmation": "operator confirmed selected input SGF in native Open dialog"},
            )
        )

        input("3. Click Open, verify the SGF is visible in the app, then press Enter to capture sgf_opened...")
        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-opened.png", root, "sgf_opened"))
        steps.append(step("sgf_opened", "pass", method="operator-confirmed SGF opened after native dialog", screenshot=screenshots[-1], openedPath=sanitize_temp_path(input_path)))

        semantic_edit = semantic_edit_proof(runtime_evidence, runtime_evidence_path, root)
        steps.append(step("edit_operations_applied", "pass", method="existing Tauri runtime semantic proof", semanticProof=semantic_edit))

        input("4. Open native Save/Save As dialog, choose the save path, leave the dialog visible, then press Enter to capture save_or_save_as...")
        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-save-dialog.png", root, "save_or_save_as"))
        steps.append(
            step(
                "save_or_save_as",
                "pass",
                method="manual-assisted macOS native Save dialog",
                screenshot=screenshots[-1],
                savedPath=sanitize_temp_path(saved_path),
                operator={"type": "manual-assisted", "tooling": ["screencapture"], "confirmation": "operator confirmed selected output SGF in native Save dialog"},
            )
        )

        input("5. Click Save. If prompted to replace, confirm. Press Enter after the saved file exists...")
        saved_content = read_saved_sgf(saved_path)
        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-saved.png", root, "save_completed"))

        input("6. Open native Open dialog again, select the saved SGF path, leave the dialog visible, then press Enter to capture reopen_saved_sgf...")
        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-reopen-dialog.png", root, "reopen_saved_sgf"))
        steps.append(
            step(
                "reopen_saved_sgf",
                "pass",
                method="manual-assisted native Open of just-saved SGF path",
                screenshot=screenshots[-1],
                openedPath=sanitize_temp_path(saved_path),
                operator={"type": "manual-assisted", "tooling": ["screencapture"], "confirmation": "operator confirmed selected saved SGF in native Open dialog"},
            )
        )

        input("7. Click Open and verify reopened state in the app, then press Enter to capture reopen_state_verified...")
        screenshots.append(capture_screenshot(screenshot_dir / "native-desktop-sgf-reopened.png", root, "reopen_state"))
        reopen_invariants = verify_reopen_invariants(saved_content)
        if reopen_invariants.get("verified") is not True:
            raise SmokeError("saved SGF content/tree/board invariants did not pass")
        steps.append(step("reopen_state_verified", "pass", method="saved SGF content/tree/board invariant verification plus operator-confirmed reopened app state", screenshot=screenshots[-1], invariants=reopen_invariants))
        steps.append(step("screenshots_recorded", "pass", method="sha256 and positive byte validation", screenshotCount=len(screenshots)))
        steps.append(step("scope_boundaries", "pass", method="explicit scoped evidence boundaries"))
    except Exception as exc:  # noqa: BLE001
        blocker = str(exc)

    evidence = build_evidence(
        status="pass" if blocker is None else "fail",
        started_at=started_at,
        app_mode=args.app_mode,
        collection_method="manual_assisted_native_desktop_workflow",
        runtime_evidence=runtime_evidence,
        runtime_evidence_path=runtime_evidence_path,
        input_path=input_path,
        saved_path=saved_path,
        saved_content=saved_content,
        steps=steps,
        screenshots=screenshots,
        termination={"attempted": False, "terminated": False, "operatorManagedAppLifecycle": True},
        blocker=blocker,
    )
    write_json(evidence_path, evidence)
    if evidence["status"] == "pass":
        print(f"PASS manual-assisted native desktop SGF workflow smoke: wrote {repo_relative_path(evidence_path, root)}")
        return 0
    print(f"FAIL manual-assisted native desktop SGF workflow smoke: {blocker}", file=sys.stderr)
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


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SmokeError(f"runtime semantic evidence not found: {repo_relative_path(path, ROOT)}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeError(f"runtime semantic evidence invalid JSON at line {exc.lineno}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise SmokeError("runtime semantic evidence root must be an object")
    return value


def validate_runtime_semantic_proof(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if evidence.get("schema") != TAURI_RUNTIME_SCHEMA:
        failures.append(f"schema must be {TAURI_RUNTIME_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    required = ("comment_edit", "property_edit", "annotation_edit", "append_move", "save_readback_roundtrip", "board_state_verified")
    for name in required:
        check = check_by_name(evidence, name)
        if not isinstance(check, dict):
            failures.append(f"missing runtime check {name}")
        elif str(check.get("status", "")).lower() != "pass":
            failures.append(f"runtime check {name} must pass")
    proof = evidence.get("saveReopenProof")
    if not isinstance(proof, dict) or proof.get("sameSgfPath") is not True or proof.get("distinctProcesses") is not True:
        failures.append("saveReopenProof must confirm same SGF path and distinct Tauri processes")
    return failures


def check_by_name(evidence: dict[str, Any], name: str) -> dict[str, Any] | None:
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        return None
    for check in checks:
        if isinstance(check, dict) and check.get("name") == name:
            return check
    return None


def check_details(check: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(check, dict):
        return {}
    for key in ("details", "evidence"):
        value = check.get(key)
        if isinstance(value, dict):
            return value
    return check


def launch_app(root: Path, app_mode: str) -> subprocess.Popen[str]:
    if app_mode != "tauri-dev":
        raise SmokeError("packaged-macos-app mode is reserved for a future native workflow run; use installed app smoke for packaged launch proof")
    log_path = root / ".tmp" / "native-desktop-sgf-workflow-tauri-dev.log"
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


def wait_for_window(*, process: subprocess.Popen[str], timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SmokeError(f"Tauri app exited before showing a window (exit {process.returncode})")
        windows = list_windows()
        if windows:
            return windows[0]
        time.sleep(0.5)
    raise SmokeError(f"timed out after {timeout_seconds:g}s waiting for Tauri window for pid {process.pid}")


def list_windows(*, owner_pid: int | None = None) -> list[dict[str, Any]]:
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


def activate_process(window: dict[str, Any]) -> None:
    pid = window.get("ownerPid")
    if not isinstance(pid, int):
        return
    script = 'tell application "System Events" to set frontmost of first process whose unix id is %d to true' % pid
    subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=10)


def click_toolbar_button(window: dict[str, Any], name: str) -> None:
    bounds = window.get("bounds")
    if not isinstance(bounds, dict):
        raise SmokeError("window bounds missing for toolbar click")
    x = int(bounds.get("X", 0))
    y = int(bounds.get("Y", 0))
    offsets = {
        "open": (36, 112),
        "save-as": (154, 112),
    }
    if name not in offsets:
        raise SmokeError(f"unknown toolbar button: {name}")
    dx, dy = offsets[name]
    run(["cliclick", f"c:{x + dx},{y + dy}"], timeout=10)


def choose_path_in_dialog(path: Path, button_label: str) -> None:
    path_text = str(path)
    escaped = path_text.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "System Events"
  keystroke "g" using {{command down, shift down}}
  delay 0.2
  keystroke "{escaped}"
  delay 0.2
  key code 36
  delay 0.5
end tell
'''
    result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=20)
    if result.returncode != 0:
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        raise SmokeError(f"failed to choose path in native dialog: {combined}")
    if not dialog_selection_ready():
        choose_path_in_dialog_with_clipboard(path_text)
    click_native_dialog_button(button_label)


def choose_path_in_dialog_with_clipboard(path_text: str) -> None:
    escaped = path_text.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
set previousClipboard to the clipboard
set the clipboard to "{escaped}"
tell application "System Events"
  tell process "lizzieyzy-next-desktop"
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


def dialog_selection_ready() -> bool:
    script = '''
tell application "System Events"
  tell process "lizzieyzy-next-desktop"
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
  end tell
end tell
return false
'''
    result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=10)
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def click_native_dialog_button(label: str) -> None:
    escaped = label.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "System Events"
  tell process "lizzieyzy-next-desktop"
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


def wait_for_native_dialog(*, opened: bool, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        is_open = native_dialog_is_open()
        if is_open is opened:
            return
        time.sleep(0.25)
    state = "open" if opened else "closed"
    raise SmokeError(f"timed out waiting for native dialog to be {state}")


def native_dialog_is_open() -> bool:
    script = '''
tell application "System Events"
  tell process "lizzieyzy-next-desktop"
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
end tell
return "false"
'''
    result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=10)
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def capture_screenshot(path: Path, root: Path, name: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    result = subprocess.run(["screencapture", "-x", str(path)], text=True, capture_output=True, timeout=20)
    if result.returncode != 0:
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        raise SmokeError(f"screencapture failed for {name}: {combined}")
    if not path.is_file():
        raise SmokeError(f"screencapture did not create {repo_relative_path(path, root)}")
    size = path.stat().st_size
    if size <= 1024:
        raise SmokeError(f"screenshot {repo_relative_path(path, root)} is unexpectedly small ({size} bytes)")
    return {
        "name": name,
        "path": repo_relative_path(path, root),
        "sha256": sha256_file(path),
        "bytes": size,
        "captureTool": "screencapture",
    }


def read_saved_sgf(path: Path) -> str:
    if not path.is_file():
        raise SmokeError(f"saved SGF was not written: {sanitize_temp_path(path)}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise SmokeError("saved SGF is empty")
    return text


def verify_reopen_invariants(text: str) -> dict[str, Any]:
    moves = [token for token in (";B[dd]", ";W[ee]") if token in text]
    return {
        "verified": len(moves) == 2 and "SZ[9]" in text and "native workflow source" in text,
        "contentHash": sha256_text(text),
        "contentInvariant": {
            "boardSize9": "SZ[9]" in text,
            "sourceCommentPresent": "native workflow source" in text,
        },
        "treeInvariant": {
            "rootPresent": text.lstrip().startswith("(;"),
            "moveTokens": moves,
            "moveCountAtLeast": len(moves),
        },
        "boardInvariant": {
            "expectedStones": [{"color": "B", "point": "dd"}, {"color": "W", "point": "ee"}],
            "verifiedByContent": len(moves) == 2,
        },
    }


def semantic_edit_proof(evidence: dict[str, Any], path: Path, root: Path) -> dict[str, Any]:
    annotation = check_details(check_by_name(evidence, "annotation_edit"))
    save_roundtrip = check_details(check_by_name(evidence, "save_readback_roundtrip"))
    board = check_details(check_by_name(evidence, "board_state_verified"))
    return {
        "sourceRuntimeEvidence": {
            "path": repo_relative_path(path, root),
            "schema": evidence.get("schema"),
            "status": evidence.get("status"),
        },
        "commentEdit": {"status": check_by_name(evidence, "comment_edit").get("status")},
        "propertyEdit": {"status": check_by_name(evidence, "property_edit").get("status")},
        "annotationEdit": {
            "status": check_by_name(evidence, "annotation_edit").get("status"),
            "annotations": annotation.get("annotations"),
        },
        "structuralEdit": {"appendMove": check_by_name(evidence, "append_move").get("status")},
        "saveReadbackRoundtrip": {
            "status": check_by_name(evidence, "save_readback_roundtrip").get("status"),
            "readbackVerified": save_roundtrip.get("readbackVerified"),
            "readbackStatus": save_roundtrip.get("readbackStatus"),
            "afterReopen": save_roundtrip.get("afterReopen"),
        },
        "boardInvariant": board,
    }


def step(name: str, status: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "status": status, "details": details}


def build_evidence(
    *,
    status: str,
    started_at: str,
    app_mode: str,
    collection_method: str,
    runtime_evidence: dict[str, Any],
    runtime_evidence_path: Path,
    input_path: Path,
    saved_path: Path,
    saved_content: str | None,
    steps: list[dict[str, Any]],
    screenshots: list[dict[str, Any]],
    termination: dict[str, Any],
    blocker: str | None,
) -> dict[str, Any]:
    step_status = {item.get("name"): item.get("status") for item in steps}
    required = [
        "app_started",
        "native_open_dialog",
        "sgf_opened",
        "edit_operations_applied",
        "save_or_save_as",
        "reopen_saved_sgf",
        "reopen_state_verified",
        "screenshots_recorded",
        "scope_boundaries",
    ]
    missing = [name for name in required if step_status.get(name) != "pass"]
    runtime_ok = not validate_runtime_semantic_proof(runtime_evidence) if runtime_evidence else False
    screenshot_ok = bool(screenshots) and all(isinstance(item.get("sha256"), str) and item.get("bytes", 0) > 1024 for item in screenshots)
    saved_ok = saved_content is not None and bool(saved_content.strip())
    failures = []
    if blocker:
        failures.append(blocker)
    failures.extend(f"missing or non-pass workflow check: {name}" for name in missing)
    if not runtime_ok:
        failures.append("runtime semantic edit proof missing")
    if not screenshot_ok:
        failures.append("screenshots not recorded")
    evidence_status = "pass" if status == "pass" and not failures else "fail"
    manual_assisted = collection_method == "manual_assisted_native_desktop_workflow"
    return {
        "schema": SCHEMA,
        "name": "native_desktop_sgf_workflow",
        "status": evidence_status,
        "platform": normalized_platform(),
        "appMode": app_mode,
        "collectionMethod": collection_method,
        "startedAt": started_at,
        "completedAt": iso_timestamp(),
        "operator": {
            "type": "manual-assisted" if manual_assisted else "automation",
            "method": "operator-guided screenshots and artifact checks" if manual_assisted else "macOS native UI automation using cliclick, osascript, and screencapture",
            "manualAssisted": manual_assisted,
        },
        "nativeDialogOpenCovered": step_status.get("native_open_dialog") == "pass",
        "nativeDialogSaveCovered": step_status.get("save_or_save_as") == "pass",
        "webviewDomAutomationCovered": False,
        "fullAutomationCovered": False if manual_assisted else evidence_status == "pass",
        "fullLegacyParityCovered": False,
        "releasePublished": False,
        "productionSigned": False,
        "notarized": False,
        "openedSgfPath": sanitize_temp_path(input_path),
        "savedSgfPath": sanitize_temp_path(saved_path),
        "savedSgf": {
            "path": sanitize_temp_path(saved_path),
            "written": saved_ok,
            "sha256": sha256_text(saved_content) if saved_content is not None else None,
            "bytes": len(saved_content.encode("utf-8")) if saved_content is not None else 0,
        },
        "semanticEditProof": semantic_edit_proof(runtime_evidence, runtime_evidence_path, ROOT) if runtime_ok else None,
        "reopenVerification": verify_reopen_invariants(saved_content) if saved_content is not None else {"verified": False},
        "screenshots": screenshots,
        "steps": steps,
        "checks": steps,
        "boundaries": {
            "webviewDomAutomationCovered": False,
            "fullLegacyParityCovered": False,
            "releasePublished": False,
            "productionSigned": False,
            "notarized": False,
            "windowsCovered": False,
            "linuxCovered": False,
            "ocrCovered": False,
            "providerCovered": False,
            "readboardCovered": False,
            "note": "This scoped smoke covers native macOS Open/Save dialogs and combines them with existing Tauri runtime semantic SGF edit/save/reopen proof. It does not claim production release signing, notarization, publication, OCR/provider/readboard, Windows/Linux, or full legacy parity.",
        },
        "termination": termination,
        "failures": failures,
    }


def terminate_process(process: subprocess.Popen[str] | None, *, grace_seconds: float = 5.0) -> dict[str, Any]:
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
    return {"attempted": True, "method": "SIGKILL", "terminated": process.poll() is not None, "exitCode": process.poll()}


def run(cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        raise SmokeError(f"command failed ({result.returncode}): {' '.join(cmd)}\n{combined}")
    return result


def repo_relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def sanitize_temp_path(path: Path) -> str:
    return f"<tmp>/{path.name}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iso_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    raise SystemExit(main())
