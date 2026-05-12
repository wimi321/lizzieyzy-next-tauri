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
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "lizzieyzy.desktop-ui-click-smoke.v1"
DEFAULT_URL = "http://127.0.0.1:1420"
DEFAULT_EVIDENCE = Path("docs/qa/desktop-ui-click-smoke-macos.json")
DEFAULT_SCREENSHOT_DIR = Path("docs/qa/screenshots")
PLAYWRIGHT_VERSION = "1.60.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect browser-rendered desktop UI DOM/click smoke evidence.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--evidence-out", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--screenshot-dir", type=Path, default=DEFAULT_SCREENSHOT_DIR)
    parser.add_argument("--viewport", default="1440x1100", help="Viewport as WIDTHxHEIGHT.")
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    parser.add_argument("--no-start-server", action="store_true", help="Use an already-running Vite server.")
    parser.add_argument("--skip-playwright-install", action="store_true", help="Do not npm-install Playwright in a temp dir.")
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence_path = resolve_repo_path(args.evidence_out)
    screenshot_dir = resolve_repo_path(args.screenshot_dir)
    width, height = parse_viewport(args.viewport)
    server_process: subprocess.Popen[str] | None = None
    server_started = False
    started_at = iso_timestamp()

    try:
        if not args.no_start_server and not url_is_ready(args.url):
            server_process = start_vite_server()
            server_started = True
        wait_for_url(args.url, args.timeout_ms)

        with tempfile.TemporaryDirectory(prefix="lizzieyzy-ui-click-") as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            if not args.skip_playwright_install:
                install_playwright(temp_dir)
            result_path = temp_dir / "click-result.json"
            script_path = temp_dir / "click-runner.cjs"
            script_path.write_text(playwright_script(), encoding="utf-8")
            config = {
                "url": args.url,
                "resultPath": str(result_path),
                "screenshotDir": str(screenshot_dir),
                "viewport": {"width": width, "height": height},
                "timeoutMs": args.timeout_ms,
                "headed": args.headed,
                "serverStartedByRunner": server_started,
            }
            env = os.environ.copy()
            env["SMOKE_CLICK_CONFIG"] = json.dumps(config)
            node_result = subprocess.run(
                ["node", str(script_path)],
                cwd=temp_dir,
                env=env,
                text=True,
                capture_output=True,
                timeout=max(30, args.timeout_ms // 1000 + 20),
            )
            if node_result.returncode != 0 and not result_path.is_file():
                combined = "\n".join(part for part in [node_result.stdout.strip(), node_result.stderr.strip()] if part)
                raise RuntimeError(f"command failed ({node_result.returncode}): node {script_path}\n{combined}")
            result = load_json(result_path)

        evidence = build_evidence(result, args.url, width, height, server_started, started_at)
        write_json(evidence_path, evidence)
        print(f"wrote {evidence_path}")
        return 0 if evidence["status"] == "pass" else 1
    except Exception as exc:
        evidence = build_failure_evidence(args.url, width, height, server_started, started_at, exc)
        write_json(evidence_path, evidence)
        print(f"wrote failure evidence to {evidence_path}", file=sys.stderr)
        print(f"blocker: {exc}", file=sys.stderr)
        return 1
    finally:
        if server_process is not None:
            stop_process(server_process)


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def parse_viewport(raw: str) -> tuple[int, int]:
    try:
        width_raw, height_raw = raw.lower().split("x", 1)
        width = int(width_raw)
        height = int(height_raw)
    except ValueError as exc:
        raise RuntimeError(f"invalid --viewport {raw!r}; expected WIDTHxHEIGHT") from exc
    if width < 320 or height < 320:
        raise RuntimeError("--viewport dimensions must be at least 320")
    return width, height


def start_vite_server() -> subprocess.Popen[str]:
    log_dir = ROOT / ".tmp"
    log_dir.mkdir(exist_ok=True)
    log_file = (log_dir / "desktop-ui-click-vite.log").open("w", encoding="utf-8")
    return subprocess.Popen(
        ["npm", "--prefix", "apps/desktop", "run", "dev"],
        cwd=ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )


def wait_for_url(url: str, timeout_ms: int) -> None:
    deadline = time.time() + timeout_ms / 1000
    last_error: Exception | None = None
    while time.time() < deadline:
        if url_is_ready(url):
            return
        try:
            urllib.request.urlopen(url, timeout=1)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Vite URL was not reachable before timeout: {url}; last_error={last_error}")


def url_is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def install_playwright(temp_dir: Path) -> None:
    package_json = temp_dir / "package.json"
    package_json.write_text('{"private":true,"type":"commonjs"}\n', encoding="utf-8")
    run(["npm", "install", "--silent", f"playwright@{PLAYWRIGHT_VERSION}"], cwd=temp_dir, timeout=120)
    run([str(temp_dir / "node_modules" / ".bin" / "playwright"), "install", "chromium"], cwd=temp_dir, timeout=180)


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(cmd)}\n{combined}")
    return result


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_evidence(result: dict[str, Any], url: str, width: int, height: int, server_started: bool, started_at: str) -> dict[str, Any]:
    visible_assertions = result.get("visibleAssertions", [])
    clicked_controls = result.get("clickedControls", [])
    legacy_menu_action_smoke = result.get("legacyShellMenuActionSmoke", {})
    screenshots = normalize_screenshot_paths(result.get("screenshots", []))
    browser_dom_observed = bool(visible_assertions) and all(item.get("visible") for item in visible_assertions)
    click_observed = sum(1 for control in clicked_controls if control.get("clicked")) >= 8
    screenshot_observed = len(screenshots) >= 2 and all(item.get("sha256") for item in screenshots)
    failures = list(result.get("failures", []))
    failures.extend(
        assertion.get("name", assertion.get("selector", "unknown"))
        for assertion in visible_assertions
        if not assertion.get("visible")
    )
    if not screenshots:
        failures.append("screenshots")
    status = "pass" if not failures and result.get("status") == "pass" and browser_dom_observed and click_observed and screenshot_observed else "fail"
    return {
        "schema": SCHEMA,
        "name": "desktop_ui_click_smoke",
        "status": status,
        "platform": normalized_platform(),
        "startedAt": started_at,
        "completedAt": iso_timestamp(),
        "collectionMethod": "vite-browser-playwright-dom-click-screenshot",
        "browserDomObserved": browser_dom_observed,
        "screenshotObserved": screenshot_observed,
        "clickObserved": click_observed,
        "browserVsTauriDistinction": {
            "browserRenderedDomObserved": True,
            "viteBrowserUrl": url,
            "tauriWebviewDomObserved": False,
            "nativeFileDialogCovered": False,
            "note": "This smoke observes Chromium-rendered Vite DOM with Playwright. It is not proof of Tauri WebView DOM, OS-native file dialogs, or Tauri shell integration.",
        },
        "viewport": {"width": width, "height": height},
        "server": {"url": url, "startedByRunner": server_started},
        "screenshots": screenshots,
        "clickedControls": clicked_controls,
        "visibleAssertions": visible_assertions,
        "legacyShellMenuActionSmoke": legacy_menu_action_smoke,
        "boundaries": {
            "nativeFileDialogCovered": False,
            "tauriWebviewDomObserved": False,
            "tauriNativeDialogProof": False,
            "tauriBackendCommandProof": False,
        },
        "checks": build_checks(visible_assertions, clicked_controls, legacy_menu_action_smoke, screenshots, failures),
        "failures": failures,
    }


def build_failure_evidence(
    url: str,
    width: int,
    height: int,
    server_started: bool,
    started_at: str,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "name": "desktop_ui_click_smoke",
        "status": "fail",
        "platform": normalized_platform(),
        "startedAt": started_at,
        "completedAt": iso_timestamp(),
        "collectionMethod": "vite-browser-playwright-dom-click-screenshot",
        "browserDomObserved": False,
        "screenshotObserved": False,
        "clickObserved": False,
        "browserVsTauriDistinction": {
            "browserRenderedDomObserved": False,
            "viteBrowserUrl": url,
            "tauriWebviewDomObserved": False,
            "nativeFileDialogCovered": False,
            "note": "Runner failed before completing Chromium DOM observation.",
        },
        "viewport": {"width": width, "height": height},
        "server": {"url": url, "startedByRunner": server_started},
        "screenshots": [],
        "clickedControls": [],
        "visibleAssertions": [],
        "legacyShellMenuActionSmoke": {
            "status": "fail",
            "clickedControls": [],
            "activeTargets": [],
            "visibleAssertions": [],
            "boundaries": {
                "browserRenderedDomObserved": False,
                "nativeFileDialogCovered": False,
                "tauriWebviewDomObserved": False,
                "tauriNativeDialogProof": False,
                "fullLegacyParityCovered": False,
                "osNativeMenuCovered": False,
                "fullShortcutParityCovered": False,
                "fullLayoutParityCovered": False,
            },
            "failures": [str(exc)],
        },
        "boundaries": {
            "nativeFileDialogCovered": False,
            "tauriWebviewDomObserved": False,
            "tauriNativeDialogProof": False,
            "tauriBackendCommandProof": False,
        },
        "checks": [{"name": "runner_completed", "status": "fail", "details": {"blocker": str(exc)}}],
        "failures": [str(exc)],
    }


def normalize_screenshot_paths(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        raw_path = next_item.get("path")
        if isinstance(raw_path, str) and raw_path:
            next_item["path"] = repo_relative_path(raw_path)
        normalized.append(next_item)
    return normalized


def repo_relative_path(raw_path: str) -> str:
    path = Path(raw_path)
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def normalized_platform() -> str:
    system = platform.system().lower()
    return "macos" if system == "darwin" else system


def build_checks(
    visible_assertions: list[dict[str, Any]],
    clicked_controls: list[dict[str, Any]],
    legacy_menu_action_smoke: Any,
    screenshots: list[dict[str, Any]],
    failures: list[str],
) -> list[dict[str, Any]]:
    clicked_ok = [control for control in clicked_controls if control.get("clicked")]
    legacy_menu_failures = legacy_menu_action_smoke.get("failures", []) if isinstance(legacy_menu_action_smoke, dict) else ["legacyShellMenuActionSmoke missing"]
    return [
        {
            "name": "browser_dom_visible",
            "status": "pass" if visible_assertions and all(item.get("visible") for item in visible_assertions) else "fail",
            "details": {"assertionCount": len(visible_assertions)},
        },
        {
            "name": "real_clicks_dispatched",
            "status": "pass" if len(clicked_ok) >= 8 else "fail",
            "details": {"clickedCount": len(clicked_ok), "controls": [item.get("selector") for item in clicked_ok]},
        },
        {
            "name": "screenshots_captured",
            "status": "pass" if len(screenshots) >= 2 and all(item.get("sha256") for item in screenshots) else "fail",
            "details": {"screenshotCount": len(screenshots)},
        },
        {
            "name": "native_dialog_boundary",
            "status": "pass",
            "details": {"nativeFileDialogCovered": False, "reason": "Open/Save/Save As/import controls are selector-visible but not clicked because this browser smoke does not prove native dialogs."},
        },
        {
            "name": "legacy_shell_menu_action_smoke",
            "status": "pass" if isinstance(legacy_menu_action_smoke, dict) and legacy_menu_action_smoke.get("status") == "pass" else "fail",
            "details": {
                "clickedCount": len(legacy_menu_action_smoke.get("clickedControls", [])) if isinstance(legacy_menu_action_smoke, dict) else 0,
                "activeTargetCount": len(legacy_menu_action_smoke.get("activeTargets", [])) if isinstance(legacy_menu_action_smoke, dict) else 0,
                "failures": legacy_menu_failures,
            },
        },
        {
            "name": "runner_completed",
            "status": "pass" if not failures else "fail",
            "details": {"failures": failures},
        },
    ]


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def iso_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def playwright_script() -> str:
    return r"""
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { chromium } = require("playwright");

const config = JSON.parse(process.env.SMOKE_CLICK_CONFIG || "{}");
const timeout = config.timeoutMs || 30000;
const screenshotDir = config.screenshotDir;
fs.mkdirSync(screenshotDir, { recursive: true });

const result = {
  status: "pass",
  clickedControls: [],
  visibleAssertions: [],
  screenshots: [],
  legacyShellMenuActionSmoke: {
    status: "pass",
    clickedControls: [],
    activeTargets: [],
    visibleAssertions: [],
    boundaries: {
      browserRenderedDomObserved: true,
      nativeFileDialogCovered: false,
      tauriWebviewDomObserved: false,
      tauriNativeDialogProof: false,
      fullLegacyParityCovered: false,
      osNativeMenuCovered: false,
      fullShortcutParityCovered: false,
      fullLayoutParityCovered: false
    },
    failures: []
  },
  failures: []
};

function rel(filePath) {
  return path.relative(process.cwd(), filePath).startsWith("..") ? filePath : path.relative(process.cwd(), filePath);
}

function sha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

async function visible(page, name, selector) {
  const locator = page.locator(selector).first();
  const item = { name, selector, visible: false, text: null };
  try {
    await locator.waitFor({ state: "visible", timeout: Math.min(timeout, 8000) });
    item.visible = true;
    item.text = (await locator.innerText({ timeout: 1000 }).catch(() => "")).slice(0, 300);
  } catch (error) {
    item.error = String(error.message || error);
  }
  result.visibleAssertions.push(item);
  return item.visible;
}

async function click(page, name, selector, options = {}) {
  const locator = page.locator(selector).first();
  const item = { name, selector, clicked: false, visible: false, enabled: false };
  try {
    await locator.waitFor({ state: "visible", timeout: Math.min(timeout, 8000) });
    item.visible = true;
    item.enabled = await locator.isEnabled();
    if (item.enabled || options.force) {
      await locator.click({ timeout: Math.min(timeout, 8000), force: Boolean(options.force) });
      item.clicked = true;
      await page.waitForTimeout(options.waitAfterMs ?? 150);
    }
  } catch (error) {
    item.error = String(error.message || error);
    if (!options.optional) result.failures.push(`${name}: ${item.error}`);
  }
  result.clickedControls.push(item);
  return item.clicked;
}

async function clickMenuAction(page, group, label, target, targetSelector) {
  const action = `${group}:${label}`;
  const selector = `[data-testid="legacy-menu-${group.toLowerCase()}-${label.toLowerCase().replaceAll(" ", "-")}"]`;
  const item = { name: action, group, label, target, selector, clicked: false, visible: false, enabled: false };
  try {
    const locator = page.locator(selector).first();
    await locator.waitFor({ state: "attached", timeout: Math.min(timeout, 8000) });
    await locator.evaluate(element => element.closest("details")?.setAttribute("open", ""));
    await locator.waitFor({ state: "visible", timeout: Math.min(timeout, 8000) });
    item.visible = true;
    item.enabled = await locator.isEnabled();
    if (!item.enabled) throw new Error(`${action} menu item is disabled`);
    await locator.click({ timeout: Math.min(timeout, 8000) });
    item.clicked = true;
    await page.waitForFunction(
      ({ action, target }) => {
        const shell = document.querySelector('[data-testid="legacy-shell"]');
        return shell?.getAttribute("data-active-menu-target") === target
          && shell?.getAttribute("data-last-menu-action") === action
          && shell?.getAttribute("data-menu-action-status") === "focused";
      },
      { action, target },
      { timeout: Math.min(timeout, 8000) }
    );
    const shellAttrs = await page.locator('[data-testid="legacy-shell"]').evaluate(element => ({
      activeTarget: element.getAttribute("data-active-menu-target") || "",
      lastAction: element.getAttribute("data-last-menu-action") || "",
      status: element.getAttribute("data-menu-action-status") || ""
    }));
    const targetLocator = page.locator(targetSelector).first();
    await targetLocator.waitFor({ state: "visible", timeout: Math.min(timeout, 8000) });
    const targetText = (await targetLocator.innerText({ timeout: 1000 }).catch(() => "")).slice(0, 300);
    result.legacyShellMenuActionSmoke.activeTargets.push({
      name: action,
      target,
      selector: targetSelector,
      visible: true,
      active: shellAttrs.activeTarget === target,
      lastAction: shellAttrs.lastAction,
      status: shellAttrs.status,
      text: targetText
    });
    result.legacyShellMenuActionSmoke.visibleAssertions.push({
      name: `${action} target`,
      selector: targetSelector,
      visible: true,
      status: "pass",
      text: targetText
    });
  } catch (error) {
    item.error = String(error.message || error);
    result.legacyShellMenuActionSmoke.failures.push(`${action}: ${item.error}`);
    result.failures.push(`${action}: ${item.error}`);
  }
  result.legacyShellMenuActionSmoke.clickedControls.push(item);
  result.clickedControls.push(item);
  return item.clicked;
}

async function fill(page, name, selector, value) {
  const locator = page.locator(selector).first();
  const item = { name, selector, clicked: false, visible: false, enabled: false, valueLength: value.length };
  try {
    await locator.waitFor({ state: "visible", timeout: Math.min(timeout, 8000) });
    item.visible = true;
    item.enabled = await locator.isEnabled();
    if (item.enabled) {
      await locator.fill(value, { timeout: Math.min(timeout, 8000) });
      item.clicked = true;
      await page.waitForTimeout(100);
    }
  } catch (error) {
    item.error = String(error.message || error);
    result.failures.push(`${name}: ${item.error}`);
  }
  result.clickedControls.push(item);
  return item.clicked;
}

async function selectOption(page, name, selector, value) {
  const locator = page.locator(selector).first();
  const item = { name, selector, clicked: false, visible: false, enabled: false, value };
  try {
    await locator.waitFor({ state: "visible", timeout: Math.min(timeout, 8000) });
    item.visible = true;
    item.enabled = await locator.isEnabled();
    if (item.enabled) {
      await locator.selectOption(value, { timeout: Math.min(timeout, 8000) });
      item.clicked = true;
      await page.waitForTimeout(150);
    }
  } catch (error) {
    item.error = String(error.message || error);
    result.failures.push(`${name}: ${item.error}`);
  }
  result.clickedControls.push(item);
  return item.clicked;
}

async function screenshot(page, name) {
  const filePath = path.join(screenshotDir, `desktop-ui-click-${name}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  const stat = fs.statSync(filePath);
  result.screenshots.push({ name, path: filePath, sha256: sha256(filePath), bytes: stat.size });
}

(async () => {
  const browser = await chromium.launch({ headless: !config.headed });
  const page = await browser.newPage({ viewport: config.viewport });
  page.on("pageerror", error => result.failures.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") result.failures.push(`console error: ${message.text()}`);
  });
  try {
    await page.goto(config.url, { waitUntil: "networkidle", timeout });
    await page.locator('[data-testid="legacy-shell"]').waitFor({ state: "visible", timeout });

    for (const [name, selector] of [
      ["legacy shell", '[data-testid="legacy-shell"]'],
      ["menu bar", '[data-testid="legacy-menubar"]'],
      ["toolbar", '[data-testid="legacy-toolbar"]'],
      ["board pane", '[data-testid="legacy-board-pane"]'],
      ["analysis pane", '[data-testid="legacy-analysis-pane"]'],
      ["bottom dock", '[data-testid="legacy-bottom-dock"]'],
      ["sgf source", '[data-testid="sgf-source-textarea"]'],
      ["sgf tree", '[data-testid="sgf-tree-panel"]'],
      ["annotation editor", '[data-testid="sgf-annotation-editor"]'],
      ["move edit panel", '[data-testid="sgf-move-edit-panel"]'],
      ["provider panel", '[data-testid="provider-panel"]'],
      ["engine setup", '[data-testid="engine-setup-panel"]'],
      ["preferences", '[data-testid="preferences-panel"]'],
      ["statusbar", '[data-testid="legacy-statusbar"]']
    ]) {
      await visible(page, name, selector);
    }

    await screenshot(page, "initial");
    await click(page, "load sample", '[data-testid="toolbar-load-sample"]');
    await click(page, "parse sgf", '[data-testid="toolbar-parse-sgf"]');
    await click(page, "run review", '[data-testid="toolbar-run-review"]');
    await click(page, "select first move", '[data-testid="sgf-tree-node"][data-sgf-move-number="1"]');
    await fill(page, "edit comment draft", '[data-testid="sgf-comment-textarea"]', "Browser click smoke comment");
    await click(page, "save comment attempt", '[data-testid="sgf-comment-save"]', { optional: true });
    await fill(page, "annotation LB add input", '[data-testid="sgf-annotation-lb-add-input"]', "aa:Z");
    await click(page, "annotation LB add", '[data-testid="sgf-annotation-lb-add"]');
    await click(page, "save annotations attempt", '[data-testid="sgf-annotations-save"]', { optional: true });
    await click(page, "tree edit mode", '[data-testid="sgf-tree-mode-edit"]', { optional: true });
    await click(page, "move edit mode", '[data-testid="sgf-move-mode-edit"]');
    await click(page, "move color white", '[data-testid="sgf-move-color-white"]');
    await selectOption(page, "provider source fox", '[data-testid="provider-source-select"]', "fox");
    await fill(page, "provider source input", '[data-testid="provider-source-input"]', "chessid 123456");
	    await selectOption(page, "preferences board theme", '[data-testid="preferences-board-theme"]', "high-contrast");
	    await click(page, "preferences candidates toggle", '[data-testid="preferences-toggle-candidates"]');
	    await click(page, "runtime assets refresh", '[data-testid="engine-runtime-assets-refresh"]');
	    await clickMenuAction(page, "View", "Candidates", "candidates", "#legacy-menu-target-candidates");
	    await clickMenuAction(page, "View", "Ownership", "ownership", "#legacy-menu-target-ownership");
	    await clickMenuAction(page, "View", "Policy", "policy", "#legacy-menu-target-policy");
	    await clickMenuAction(page, "Engine", "Profiles", "profiles", "#legacy-menu-target-profiles");
	    await clickMenuAction(page, "Engine", "Assets", "assets", "#legacy-menu-target-assets");
	    await clickMenuAction(page, "Tools", "Providers", "providers", "#legacy-menu-target-providers");
	    await clickMenuAction(page, "Tools", "Preferences", "preferences", "#legacy-menu-target-preferences");
	    await clickMenuAction(page, "Help", "Backend status", "backend-status", "#legacy-menu-target-backend-status");
	    if (result.legacyShellMenuActionSmoke.failures.length) result.legacyShellMenuActionSmoke.status = "fail";
	    await screenshot(page, "after-clicks");
  } catch (error) {
    result.status = "fail";
    result.failures.push(String(error.message || error));
  } finally {
    await browser.close();
    if (result.failures.length) result.status = "fail";
    fs.writeFileSync(config.resultPath, JSON.stringify(result, null, 2));
  }
})().catch(error => {
  result.status = "fail";
  result.failures.push(String(error.message || error));
  fs.writeFileSync(config.resultPath, JSON.stringify(result, null, 2));
  process.exit(1);
});
"""


if __name__ == "__main__":
    raise SystemExit(main())
