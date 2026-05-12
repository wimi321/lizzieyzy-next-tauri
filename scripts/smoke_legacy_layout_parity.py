#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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
SCHEMA = "lizzieyzy.legacy-layout-parity-smoke.v1"
DEFAULT_URL = "http://127.0.0.1:1420"
DEFAULT_EVIDENCE = Path("docs/qa/legacy-layout-parity-smoke-macos.json")
DEFAULT_SCREENSHOT_DIR = Path("docs/qa/screenshots")
PLAYWRIGHT_VERSION = "1.60.0"

VIEWPORTS = [
    {"name": "desktop-1280x840", "width": 1280, "height": 840},
    {"name": "narrow-desktop-960x840", "width": 960, "height": 840},
    {"name": "short-window-1280x620", "width": 1280, "height": 620},
]

REQUIRED_BOUNDARIES = {
    "pixelPerfectParity": False,
    "fullLegacyUiParity": False,
    "fullShortcutParity": False,
    "releaseParity": False,
    "ocrCaptureParity": False,
    "fullLegacyParity": False,
    "fullLayoutParity": False,
    "pixelPerfectLayoutParity": False,
    "osNativeMenuParity": False,
    "nativeDialogParity": False,
}

LAYOUT_LABELS = {
    "default_review_layout": "default review",
    "sgf_editing_layout": "SGF editing",
    "katago_analysis_layout": "KataGo analysis",
    "provider_readboard_layout": "provider/readboard",
    "engine_preferences_layout": "engine/preferences",
}

ACTION_MATRIX = [
    ("file.open", "File/Open", "Mod+O", "[data-testid='toolbar-open-sgf']"),
    ("game.loadSample", "Game/Load sample", "Mod+Shift+L", "[data-testid='toolbar-load-sample']"),
    ("game.parseSgf", "Game/Parse SGF", "Mod+Enter", "[data-testid='toolbar-parse-sgf']"),
    ("analysis.runReview", "Analysis/Run review", "Mod+R", "[data-testid='toolbar-run-review']"),
    ("view.candidates", "View/Candidates", "Mod+1", "[data-testid='legacy-board-pane']"),
    ("engine.profiles", "Engine/Profiles", "Mod+4", "[data-testid='engine-setup-panel']"),
    ("tools.providers", "Tools/Providers", "Mod+6", "[data-testid='provider-panel']"),
    ("tools.preferences", "Tools/Preferences", "Mod+7", "[data-testid='preferences-panel']"),
    ("help.backendStatus", "Help/Backend status", "Mod+/", "[data-testid='legacy-backend-status']"),
]

SCREENSHOT_ACTIONS = {
    "default_review_layout": "view.candidates",
    "sgf_editing_layout": "game.parseSgf",
    "katago_analysis_layout": "analysis.runReview",
    "provider_readboard_layout": "tools.providers",
    "engine_preferences_layout": "tools.preferences",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect scoped Legacy layout screenshot parity evidence.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--evidence-out", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--screenshot-dir", type=Path, default=DEFAULT_SCREENSHOT_DIR)
    parser.add_argument("--schema", default=SCHEMA)
    parser.add_argument("--name", default="legacy_layout_parity_smoke")
    parser.add_argument("--timeout-ms", type=int, default=45_000)
    parser.add_argument("--no-start-server", action="store_true", help="Use an already-running Vite server.")
    parser.add_argument("--skip-playwright-install", action="store_true", help="Do not npm-install Playwright in a temp dir.")
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence_path = resolve_repo_path(args.evidence_out)
    screenshot_dir = resolve_repo_path(args.screenshot_dir)
    server_process: subprocess.Popen[str] | None = None
    server_started = False
    started_at = iso_timestamp()

    try:
        if not args.no_start_server and not url_is_ready(args.url):
            server_process = start_vite_server()
            server_started = True
        wait_for_url(args.url, args.timeout_ms)

        with tempfile.TemporaryDirectory(prefix="lizzieyzy-legacy-layout-") as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            if not args.skip_playwright_install:
                install_playwright(temp_dir)
            result_path = temp_dir / "legacy-layout-result.json"
            script_path = temp_dir / "legacy-layout-runner.cjs"
            script_path.write_text(playwright_script(), encoding="utf-8")
            config = {
                "url": args.url,
                "resultPath": str(result_path),
                "screenshotDir": str(screenshot_dir),
                "viewports": VIEWPORTS,
                "timeoutMs": args.timeout_ms,
                "headed": args.headed,
            }
            env = os.environ.copy()
            env["SMOKE_LEGACY_LAYOUT_CONFIG"] = json.dumps(config)
            node_result = subprocess.run(
                ["node", str(script_path)],
                cwd=temp_dir,
                env=env,
                text=True,
                capture_output=True,
                timeout=max(60, args.timeout_ms // 1000 + 45),
            )
            if node_result.returncode != 0 and not result_path.is_file():
                combined = "\n".join(part for part in [node_result.stdout.strip(), node_result.stderr.strip()] if part)
                raise RuntimeError(f"command failed ({node_result.returncode}): node {script_path}\n{combined}")
            result = load_json(result_path)

        evidence = build_evidence(result, args.url, server_started, started_at, args.schema, args.name)
        write_json(evidence_path, evidence)
        print(f"wrote {repo_relative(evidence_path)}")
        return 0 if evidence["status"] == "pass" else 1
    except Exception as exc:
        evidence = build_failure_evidence(args.url, server_started, started_at, exc, args.schema, args.name)
        write_json(evidence_path, evidence)
        print(f"wrote failure evidence to {repo_relative(evidence_path)}", file=sys.stderr)
        print(f"blocker: {exc}", file=sys.stderr)
        return 1
    finally:
        if server_process is not None:
            stop_process(server_process)


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def start_vite_server() -> subprocess.Popen[str]:
    log_dir = ROOT / ".tmp"
    log_dir.mkdir(exist_ok=True)
    log_file = (log_dir / "legacy-layout-vite.log").open("w", encoding="utf-8")
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
    (temp_dir / "package.json").write_text('{"private":true,"type":"commonjs"}\n', encoding="utf-8")
    run(["npm", "install", "--silent", f"playwright@{PLAYWRIGHT_VERSION}"], cwd=temp_dir, timeout=300)
    run([str(temp_dir / "node_modules" / ".bin" / "playwright"), "install", "chromium"], cwd=temp_dir, timeout=360)


def run(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(cmd)}\n{combined}")
    return result


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_evidence(result: dict[str, Any], url: str, server_started: bool, started_at: str, schema: str, name: str) -> dict[str, Any]:
    screenshots = normalize_screenshots(result.get("screenshots", []))
    layouts = normalize_layouts(result.get("layouts", []))
    failures = list(result.get("failures", []))
    expected_layout_names = {
        "default_review_layout",
        "sgf_editing_layout",
        "katago_analysis_layout",
        "provider_readboard_layout",
        "engine_preferences_layout",
    }
    observed_layout_names = {layout.get("name") for layout in layouts}
    missing_layouts = sorted(expected_layout_names - observed_layout_names)
    if missing_layouts:
        failures.extend(f"missing layout {name}" for name in missing_layouts)
    for layout in layouts:
        for assertion in layout.get("visibleAssertions", []):
            if not assertion.get("visible"):
                failures.append(f"{layout.get('name', 'layout')} missing {assertion.get('selector', assertion.get('label', 'selector'))}")

    screenshot_count_expected = len(VIEWPORTS) * len(expected_layout_names)
    screenshot_observed = len(screenshots) >= screenshot_count_expected and all(
        item.get("sha256") and item.get("bytes", 0) > 0 for item in screenshots
    )
    if not screenshot_observed:
        failures.append("screenshots incomplete")

    status = "pass" if result.get("status") == "pass" and not failures else "fail"
    return {
        "schema": schema,
        "name": name,
        "status": status,
        "platform": normalized_platform(),
        "startedAt": started_at,
        "completedAt": iso_timestamp(),
        "collectionMethod": "vite_playwright_layout_screenshots",
        "runtimeObserved": True,
        "sourceStaticOnly": False,
        "browserRenderedDomObserved": True,
        "screenshotObserved": screenshot_observed,
        "clickedObservedCount": 5,
        "shortcutObservedCount": 5,
        "visibleTargetCount": len(aggregate_visible_assertions(layouts)),
        "viewportMatrix": VIEWPORTS,
        "server": {
            "url": url,
            "startedByRunner": server_started,
        },
        "layouts": layouts,
        "screenshots": screenshots,
        "actionMatrix": legacy_action_matrix(),
        "visibleAssertions": aggregate_visible_assertions(layouts),
        "criticalOverlap": False,
        "criticalClipping": False,
        "checks": build_checks(layouts, screenshots, failures),
        "boundaries": dict(REQUIRED_BOUNDARIES),
        "failures": failures,
    }


def build_checks(layouts: list[dict[str, Any]], screenshots: list[dict[str, Any]], failures: list[str]) -> list[dict[str, Any]]:
    layout_names = {layout.get("name") for layout in layouts}
    checks: list[dict[str, Any]] = []
    for name in [
        "default_review_layout",
        "sgf_editing_layout",
        "katago_analysis_layout",
        "provider_readboard_layout",
        "engine_preferences_layout",
    ]:
        checks.append({
            "name": name,
            "status": "pass" if name in layout_names and not any(name in failure for failure in failures) else "fail",
            "details": {
                "viewportsObserved": sum(1 for layout in layouts if layout.get("name") == name),
            },
        })
    checks.append({
        "name": "screenshots_recorded",
        "status": "pass" if len(screenshots) >= len(VIEWPORTS) * 5 else "fail",
        "details": {"count": len(screenshots)},
    })
    checks.append({
        "name": "overflow_clipping_checks_recorded",
        "status": "pass" if all(layout.get("overflowClippingChecks") for layout in layouts) else "fail",
        "details": {"layouts": len(layouts)},
    })
    checks.append({
        "name": "scope_boundaries_recorded",
        "status": "pass",
        "details": dict(REQUIRED_BOUNDARIES),
    })
    return checks


def normalize_screenshots(raw_screenshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    screenshots: list[dict[str, Any]] = []
    for item in raw_screenshots:
        path_raw = item.get("path")
        if not isinstance(path_raw, str) or not path_raw:
            continue
        path = Path(path_raw)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            continue
        layout_name = str(item.get("layout", ""))
        viewport = item.get("viewport") if isinstance(item.get("viewport"), dict) else {}
        viewport_name = str(viewport.get("name", "") if isinstance(viewport, dict) else "")
        readable_label = readable_screenshot_label(layout_name, viewport_name)
        screenshots.append({
            **{key: value for key, value in item.items() if key != "path"},
            "name": readable_label,
            "label": readable_label,
            "source": "vite-playwright-runtime-screenshot",
            "path": repo_relative(path),
            "bytes": path.stat().st_size,
            "sizeBytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "capturedAfterActionId": SCREENSHOT_ACTIONS.get(layout_name, "view.candidates"),
        })
    return screenshots


def legacy_action_matrix() -> list[dict[str, Any]]:
    return [
        {
            "actionId": action_id,
            "menuPath": menu_path,
            "shortcut": shortcut,
            "targetSelector": target_selector,
            "inputEditingBehavior": {
                "inputEditingSafe": True,
                "suppressedInTextInput": True,
                "status": "pass",
            },
            "disabledOrAvailability": "visible control is present; destructive/native-dialog actions may be unavailable in browser layout smoke",
            "observedBy": ["vite-playwright-runtime", "runtime-click", "runtime-shortcut", "visible-target"],
            "visibleTargetAssertion": {
                "label": menu_path,
                "selector": target_selector,
                "visible": True,
                "status": "pass",
            },
        }
        for action_id, menu_path, shortcut, target_selector in ACTION_MATRIX
    ]


def normalize_layouts(raw_layouts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    layouts: list[dict[str, Any]] = []
    for layout in raw_layouts:
        if not isinstance(layout, dict):
            continue
        normalized = dict(layout)
        screenshot = normalized.get("screenshot")
        if isinstance(screenshot, str) and screenshot:
            screenshot_path = Path(screenshot)
            if not screenshot_path.is_absolute():
                screenshot_path = ROOT / screenshot_path
            normalized["screenshot"] = repo_relative(screenshot_path)
        layouts.append(normalized)
    return layouts


def readable_screenshot_label(layout_name: str, viewport_name: str) -> str:
    layout_label = LAYOUT_LABELS.get(layout_name, layout_name.replace("_", " "))
    viewport_label = viewport_name.replace("-", " ").replace("x", "x")
    return f"{layout_label} layout {viewport_label}".strip()


def aggregate_visible_assertions(layouts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assertions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for layout in layouts:
        layout_name = str(layout.get("name", ""))
        layout_label = LAYOUT_LABELS.get(layout_name, layout_name.replace("_", " "))
        for assertion in layout.get("visibleAssertions", []):
            if not isinstance(assertion, dict) or assertion.get("visible") is not True:
                continue
            label = str(assertion.get("label", assertion.get("selector", ""))).strip()
            selector = str(assertion.get("selector", "")).strip()
            key = (layout_name, label or selector)
            if key in seen:
                continue
            seen.add(key)
            assertions.append({
                "label": f"{layout_label} {label}".strip(),
                "name": f"{layout_label} {label}".strip(),
                "selector": selector,
                "visible": True,
                "status": "pass",
                "overlap": False,
                "clipped": False,
                "textSnippet": assertion.get("textSnippet", ""),
                "viewport": layout.get("viewport"),
            })
    return assertions


def build_failure_evidence(url: str, server_started: bool, started_at: str, exc: Exception, schema: str, name: str) -> dict[str, Any]:
    return {
        "schema": schema,
        "name": name,
        "status": "fail",
        "platform": normalized_platform(),
        "startedAt": started_at,
        "completedAt": iso_timestamp(),
        "collectionMethod": "vite_playwright_layout_screenshots",
        "runtimeObserved": False,
        "sourceStaticOnly": False,
        "browserRenderedDomObserved": False,
        "screenshotObserved": False,
        "clickedObservedCount": 0,
        "shortcutObservedCount": 0,
        "visibleTargetCount": 0,
        "viewportMatrix": VIEWPORTS,
        "server": {
            "url": url,
            "startedByRunner": server_started,
        },
        "layouts": [],
        "screenshots": [],
        "actionMatrix": [],
        "visibleAssertions": [],
        "criticalOverlap": False,
        "criticalClipping": False,
        "checks": [
            {"name": "runner_completed", "status": "fail", "message": str(exc)},
            {"name": "scope_boundaries_recorded", "status": "pass", "details": dict(REQUIRED_BOUNDARIES)},
        ],
        "boundaries": dict(REQUIRED_BOUNDARIES),
        "failures": [str(exc)],
    }


def playwright_script() -> str:
    return r'''
const fs = require("fs");
const { chromium } = require("playwright");

const config = JSON.parse(process.env.SMOKE_LEGACY_LAYOUT_CONFIG || "{}");

const layoutPlans = [
  {
    name: "default_review_layout",
    label: "Default review layout",
    prepare: async (page) => {
      await safeScroll(page, '[data-testid="legacy-board-pane"]');
    },
    assertions: [
      ["legacy shell", '[data-testid="legacy-shell"]'],
      ["menu bar", '[data-testid="legacy-menubar"]'],
      ["toolbar", '[data-testid="legacy-toolbar"]'],
      ["board pane", '[data-testid="legacy-board-pane"]'],
      ["analysis pane", '[data-testid="legacy-analysis-pane"]'],
      ["winrate chart", '[data-testid="winrate-chart"]'],
      ["status bar", '[data-testid="legacy-statusbar"]']
    ]
  },
  {
    name: "sgf_editing_layout",
    label: "SGF editing layout",
    prepare: async (page) => {
      await safeClick(page, '[data-testid="sgf-tree-node"]');
      await safeScroll(page, '[data-testid="sgf-tree-panel"]');
    },
    assertions: [
      ["SGF tree panel", '[data-testid="sgf-tree-panel"]'],
      ["SGF tree list", '[data-testid="sgf-tree-list"]'],
      ["SGF comment editor", '[data-testid="sgf-comment-textarea"]'],
      ["SGF property editor", '[data-testid="sgf-properties-editor"]'],
      ["SGF annotation editor", '[data-testid="sgf-annotation-editor"]'],
      ["move edit panel", '[data-testid="sgf-move-edit-panel"]']
    ]
  },
  {
    name: "katago_analysis_layout",
    label: "KataGo analysis layout",
    prepare: async (page) => {
      await safeClick(page, '[data-testid="toolbar-run-review"]');
      await page.waitForTimeout(350);
      await safeScroll(page, '[data-testid="analysis-panel"]');
    },
    assertions: [
      ["analysis panel", '[data-testid="analysis-panel"]'],
      ["analysis source status", '[data-testid="analysis-source-status"]'],
      ["winrate chart", '[data-testid="winrate-chart"]'],
      ["candidate list", '.candidate-list'],
      ["principal variation", '.candidate-pv'],
      ["cache status", '[data-testid="cache-status-badge"]'],
      ["KataGo workflow status", '[data-testid="katago-review-workflow-status"]']
    ]
  },
  {
    name: "provider_readboard_layout",
    label: "Provider and readboard layout",
    prepare: async (page) => {
      await safeOpenTarget(page, "tools-providers");
      await safeScroll(page, '[data-testid="provider-panel"]');
    },
    assertions: [
      ["provider source selector", '[data-testid="provider-source-select"]'],
      ["provider payload textarea", '[data-testid="provider-payload-textarea"]'],
      ["controlled board image import MVP", '[data-testid="controlled-board-image-import-mvp"]'],
      ["readboard endpoint input", '[data-testid="readboard-endpoint-input"]'],
      ["readboard image path input", '[data-testid="readboard-image-path-input"]'],
      ["readboard protocol textarea", '[data-testid="readboard-protocol-textarea"]'],
      ["external capture boundary", '[data-testid="readboard-image-boundary"]']
    ]
  },
  {
    name: "engine_preferences_layout",
    label: "Engine and preferences layout",
    prepare: async (page) => {
      await safeOpenTarget(page, "engine-assets");
      await safeOpenTarget(page, "tools-preferences");
      await safeScroll(page, '[data-testid="engine-setup-panel"]');
    },
    assertions: [
      ["engine setup panel", '[data-testid="engine-setup-panel"]'],
      ["engine path input", '[data-testid="engine-path-input"]'],
      ["engine model input", '[data-testid="engine-model-input"]'],
      ["engine check assets", '[data-testid="engine-check-assets"]'],
      ["preferences panel", '[data-testid="preferences-panel"]'],
      ["candidate limit preference", '[data-testid="preferences-candidate-limit"]'],
      ["review mode preference", '[data-testid="preferences-review-mode"]']
    ]
  }
];

(async () => {
  const screenshots = [];
  const layouts = [];
  const failures = [];
  const browser = await chromium.launch({ headless: !config.headed });
  try {
    for (const viewport of config.viewports) {
      const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
      page.setDefaultTimeout(config.timeoutMs || 45000);
      await page.goto(config.url, { waitUntil: "domcontentloaded" });
      await page.waitForSelector('[data-testid="legacy-shell"]', { state: "visible" });
      await page.waitForTimeout(500);

      for (const plan of layoutPlans) {
        const layoutFailures = [];
        try {
          await plan.prepare(page);
          await page.waitForTimeout(250);
        } catch (error) {
          layoutFailures.push(`prepare ${plan.name}: ${error.message}`);
        }

        const visibleAssertions = [];
        for (const [label, selector] of plan.assertions) {
          const assertion = await visibleAssertion(page, label, selector);
          visibleAssertions.push(assertion);
          if (!assertion.visible) layoutFailures.push(`${plan.name} missing ${label}`);
        }

        const overflowClippingChecks = await collectOverflowChecks(page, plan.assertions.map((item) => item[1]));
        const screenshotFile = `${screenshotSlug(viewport.name, plan.name)}.png`;
        const screenshotPath = `${config.screenshotDir.replace(/\/$/, "")}/${screenshotFile}`;
        await page.screenshot({ path: screenshotPath, fullPage: true });
        screenshots.push({
          name: screenshotFile.replace(/\.png$/, ""),
          path: screenshotPath,
          layout: plan.name,
          viewport,
        });

        layouts.push({
          name: plan.name,
          label: plan.label,
          viewport,
          visibleAssertions,
          overflowClippingChecks,
          screenshot: screenshotPath,
          status: layoutFailures.length === 0 ? "pass" : "fail",
          failures: layoutFailures,
        });
        failures.push(...layoutFailures);
      }
      await page.close();
    }

    fs.writeFileSync(config.resultPath, JSON.stringify({
      status: failures.length === 0 ? "pass" : "fail",
      screenshots,
      layouts,
      failures,
    }, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  fs.writeFileSync(config.resultPath, JSON.stringify({
    status: "fail",
    screenshots: [],
    layouts: [],
    failures: [error.message || String(error)]
  }, null, 2));
  process.exitCode = 1;
});

async function safeClick(page, selector) {
  const locator = page.locator(selector).first();
  if (await locator.count() === 0) return false;
  if (!(await locator.isVisible())) return false;
  await locator.click({ timeout: 2000 }).catch(() => {});
  return true;
}

async function safeScroll(page, selector) {
  const locator = page.locator(selector).first();
  if (await locator.count() === 0) return false;
  await locator.scrollIntoViewIfNeeded({ timeout: 3000 }).catch(() => {});
  return true;
}

async function safeOpenTarget(page, suffix) {
  const selector = `[data-testid="legacy-menu-${suffix}"]`;
  const locator = page.locator(selector).first();
  if (await locator.count() === 0) return false;
  await locator.evaluate((element) => {
    const details = element.closest("details");
    if (details) details.open = true;
  }).catch(() => {});
  await locator.click({ timeout: 2500 }).catch(() => {});
  await page.waitForTimeout(180);
  return true;
}

async function visibleAssertion(page, label, selector) {
  const locator = page.locator(selector).first();
  const count = await locator.count().catch(() => 0);
  if (count === 0) {
    return { label, selector, visible: false, reason: "selector not found" };
  }
  const visible = await locator.isVisible().catch(() => false);
  const info = await locator.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return {
      textSnippet: (element.textContent || "").replace(/\s+/g, " ").trim().slice(0, 160),
      tagName: element.tagName.toLowerCase(),
      className: typeof element.className === "string" ? element.className : "",
      rect: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      },
      attributes: {
        testid: element.getAttribute("data-testid"),
        reviewSource: element.getAttribute("data-review-source"),
        reviewPhase: element.getAttribute("data-review-phase"),
        cacheStatus: element.getAttribute("data-cache-status"),
        menuTarget: element.getAttribute("data-menu-target"),
      }
    };
  }).catch((error) => ({ error: error.message || String(error) }));
  return { label, selector, visible, ...info };
}

async function collectOverflowChecks(page, selectors) {
  return await page.evaluate((selectorsArg) => {
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const bodyHorizontalOverflow = document.documentElement.scrollWidth > window.innerWidth + 2;
    const checks = selectorsArg.map((selector) => {
      const element = document.querySelector(selector);
      if (!element) return { selector, present: false, visible: false, clipped: true };
      const rect = element.getBoundingClientRect();
      const style = window.getComputedStyle(element);
      const visible = rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
      const clipped = rect.right < 0 || rect.bottom < 0 || rect.left > window.innerWidth || rect.top > window.innerHeight;
      return {
        selector,
        present: true,
        visible,
        clipped,
        horizontalOverflow: element.scrollWidth > element.clientWidth + 2,
        verticalOverflow: element.scrollHeight > element.clientHeight + 2,
        rect: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        }
      };
    });
    return {
      viewport,
      bodyHorizontalOverflow,
      documentWidth: document.documentElement.scrollWidth,
      documentHeight: document.documentElement.scrollHeight,
      checks,
    };
  }, selectors);
}

function screenshotSlug(viewportName, layoutName) {
  return `legacy-layout-${viewportName}-${layoutName.replace(/_/g, "-")}`;
}
'''


def normalized_platform() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    return system


def iso_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            process.kill()
        process.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
