#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
TAURI_CONFIG = "apps/desktop/src-tauri/tauri.conf.json"
DESKTOP_PACKAGE = "apps/desktop/package.json"
DESKTOP_CARGO = "apps/desktop/src-tauri/Cargo.toml"
RELEASE_WORKFLOW = ".github/workflows/release-dry-run.yml"
RELEASE_NOTES_CONFIG = ".github/release.yml"

EXPECTED_IDENTIFIER = "org.lizzieyzy.next"
EXPECTED_BINARY = "lizzieyzy-next-desktop"
EXPECTED_PRODUCT = "LizzieYzy Next"
EXPECTED_DRY_RUN_ARTIFACT = "release-dry-run-${{ runner.os }}"
EXPECTED_RELEASE_LABELS = {"release", "packaging", "desktop", "tauri"}
REQUIRED_SIGNING_SECRET_NAMES = {
    "APPLE_CERTIFICATE",
    "APPLE_CERTIFICATE_PASSWORD",
    "APPLE_ID",
    "APPLE_PASSWORD",
    "APPLE_TEAM_ID",
    "WINDOWS_CERTIFICATE",
    "WINDOWS_CERTIFICATE_PASSWORD",
    "TAURI_SIGNING_PRIVATE_KEY",
}
FORBIDDEN_RELEASE_MUTATIONS = [
    "contents: write",
    "softprops/action-gh-release",
    "actions/create-release",
    "gh release create",
    "gh release upload",
    "tauri-apps/tauri-action",
]


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


class ReleaseAssetValidator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.results: list[CheckResult] = []

    def pass_(self, name: str, detail: str) -> None:
        self.results.append(CheckResult(name, True, detail))

    def fail(self, name: str, detail: str) -> None:
        self.results.append(CheckResult(name, False, detail))

    def path(self, rel: str) -> Path:
        return self.root / rel

    def read_text(self, rel: str) -> str | None:
        try:
            return self.path(rel).read_text(encoding="utf-8")
        except FileNotFoundError:
            self.fail(f"file:{rel}", "file is missing")
        return None

    def load_json(self, rel: str) -> Any | None:
        text = self.read_text(rel)
        if text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            self.fail(f"json:{rel}", f"invalid JSON at line {exc.lineno}: {exc.msg}")
        return None

    def load_toml(self, rel: str) -> Any | None:
        text = self.read_text(rel)
        if text is None:
            return None
        try:
            if tomllib is not None:
                return tomllib.loads(text)
            return parse_minimal_toml(text)
        except ValueError as exc:
            self.fail(f"toml:{rel}", f"invalid TOML: {exc}")
        return None

    def check_tauri_metadata(self) -> None:
        conf = self.load_json(TAURI_CONFIG)
        package = self.load_json(DESKTOP_PACKAGE)
        manifest = self.load_toml(DESKTOP_CARGO)
        if not conf or not package or not manifest:
            return

        errors: list[str] = []
        bundle = conf.get("bundle", {})
        build = conf.get("build", {})
        app = conf.get("app", {})
        package_section = manifest.get("package", {})

        if conf.get("$schema") != "https://schema.tauri.app/config/2":
            errors.append("Tauri schema must be https://schema.tauri.app/config/2")
        if conf.get("identifier") != EXPECTED_IDENTIFIER:
            errors.append(f"identifier must be {EXPECTED_IDENTIFIER}")
        if conf.get("mainBinaryName") != EXPECTED_BINARY:
            errors.append(f"mainBinaryName must be {EXPECTED_BINARY}")
        if conf.get("productName") != EXPECTED_PRODUCT:
            errors.append(f"productName must be {EXPECTED_PRODUCT}")
        if package.get("name") != EXPECTED_BINARY:
            errors.append(f"desktop package name must be {EXPECTED_BINARY}")
        if package_section.get("name") != EXPECTED_BINARY:
            errors.append(f"desktop Cargo package name must be {EXPECTED_BINARY}")
        if not is_semver(str(conf.get("version", ""))):
            errors.append("Tauri version must be MAJOR.MINOR.PATCH")
        if conf.get("version") != package.get("version"):
            errors.append("Tauri and desktop package versions must match")
        if conf.get("version") != package_section.get("version"):
            errors.append("Tauri and desktop Cargo versions must match")
        if build.get("frontendDist") != "../dist":
            errors.append("build.frontendDist must be ../dist")
        if bundle.get("active") is not True:
            errors.append("bundle.active must remain true for release metadata validation")
        if bundle.get("targets") != "all":
            errors.append("bundle.targets must be all until platform artifacts are split explicitly")
        required_icons = [
            "icons/32x32.png",
            "icons/128x128.png",
            "icons/128x128@2x.png",
            "icons/icon.icns",
            "icons/icon.ico",
            "icons/icon.png",
        ]
        configured_icons = bundle.get("icon", [])
        for icon in required_icons:
            if icon not in configured_icons:
                errors.append(f"bundle.icon must include {icon}")
            elif not self.path(f"apps/desktop/src-tauri/{icon}").is_file():
                errors.append(f"configured bundle icon is missing: {icon}")
        if not bundle.get("publisher"):
            errors.append("bundle.publisher is required")
        if not bundle.get("shortDescription") or not bundle.get("longDescription"):
            errors.append("bundle descriptions are required")
        if bundle.get("macOS", {}).get("hardenedRuntime") is not True:
            errors.append("bundle.macOS.hardenedRuntime must be true")
        if not bundle.get("windows", {}).get("webviewInstallMode"):
            errors.append("bundle.windows.webviewInstallMode is required")
        if not bundle.get("linux", {}).get("deb"):
            errors.append("bundle.linux.deb metadata is required")
        windows = app.get("windows", [])
        if not windows or windows[0].get("title") != EXPECTED_PRODUCT:
            errors.append(f"main window title must be {EXPECTED_PRODUCT}")

        if errors:
            self.fail("tauri_release_metadata", "; ".join(errors))
        else:
            self.pass_(
                "tauri_release_metadata",
                f"{EXPECTED_IDENTIFIER} {conf.get('version')} with binary {EXPECTED_BINARY}",
            )

    def check_release_workflow(self) -> None:
        workflow = self.read_text(RELEASE_WORKFLOW)
        if workflow is None:
            return

        normalized = workflow.lower()
        errors: list[str] = []
        for token in FORBIDDEN_RELEASE_MUTATIONS:
            if token in normalized:
                errors.append(f"workflow must not contain release mutation token {token!r}")
        for token in [
            "permissions:",
            "contents: read",
            "workflow_dispatch:",
            'tags:',
            '"v*"',
            "python scripts/validate_release_assets.py --verbose",
            "npm run tauri:build -- --no-bundle --ci --no-sign",
        ]:
            if token not in workflow:
                errors.append(f"workflow missing {token!r}")
        if EXPECTED_DRY_RUN_ARTIFACT not in workflow:
            errors.append(f"upload artifact name must be {EXPECTED_DRY_RUN_ARTIFACT}")
        for path in [
            "release-dry-run/**",
            "apps/desktop/dist/**",
            f"target/release/{EXPECTED_BINARY}*",
            "target/release/bundle/**",
        ]:
            if path not in workflow:
                errors.append(f"upload artifact path missing {path}")
        for secret in REQUIRED_SIGNING_SECRET_NAMES:
            if f"secrets.{secret}" not in workflow:
                errors.append(f"workflow must report signing secret state for {secret}")
        for summary_token in [
            "Tauri bundle mode: compile-only dry-run",
            "no GitHub release is created",
            "Signing/notarization/publish step: skipped by design for dry-run",
        ]:
            if summary_token not in workflow:
                errors.append(f"dry-run summary missing {summary_token!r}")

        if errors:
            self.fail("release_workflow_dry_run", "; ".join(errors))
        else:
            self.pass_("release_workflow_dry_run", "workflow is read-only, unsigned, and dry-run only")

    def check_release_notes_config(self) -> None:
        config = self.read_text(RELEASE_NOTES_CONFIG)
        if config is None:
            return

        labels = set(re.findall(r"^\s*-\s+([A-Za-z0-9_*.-]+)\s*$", config, re.MULTILINE))
        missing = sorted(EXPECTED_RELEASE_LABELS - labels)
        if missing:
            self.fail("release_notes_config", "missing release note labels: " + ", ".join(missing))
        else:
            self.pass_("release_notes_config", "release note labels cover release, packaging, desktop, and tauri")

    def check_expected_artifact_contract(self) -> None:
        conf = self.load_json(TAURI_CONFIG)
        if not conf:
            return
        version = str(conf.get("version", ""))
        if not is_semver(version):
            self.fail("expected_artifact_contract", "cannot derive artifact contract from invalid version")
            return
        expected = [
            f"{EXPECTED_BINARY}-{version}-macos-dry-run",
            f"{EXPECTED_BINARY}-{version}-windows-dry-run",
            f"{EXPECTED_BINARY}-{version}-linux-dry-run",
        ]
        self.pass_(
            "expected_artifact_contract",
            "dry-run artifacts must carry binary, version, platform, commit SHA, and signing state; stems: "
            + ", ".join(expected),
        )

    def run(self) -> list[CheckResult]:
        self.check_tauri_metadata()
        self.check_release_workflow()
        self.check_release_notes_config()
        self.check_expected_artifact_contract()
        return self.results


def is_semver(value: str) -> bool:
    return re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", value) is not None


def print_results(results: list[CheckResult], *, verbose: bool) -> None:
    failures = [result for result in results if not result.ok]
    if verbose or failures:
        for result in results:
            if verbose or not result.ok:
                prefix = "PASS" if result.ok else "FAIL"
                print(f"{prefix} {result.name}: {result.detail}")
    else:
        print("PASS release preflight: Tauri release metadata and dry-run workflow validated")
    print(f"Release preflight: {len(results) - len(failures)} passed, {len(failures)} failed.")


def write_summary(results: list[CheckResult], summary_dir: Path) -> None:
    summary_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "passed": [result.__dict__ for result in results if result.ok],
        "failed": [result.__dict__ for result in results if not result.ok],
    }
    (summary_dir / "release-preflight.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = ["# Release preflight", ""]
    for result in results:
        marker = "PASS" if result.ok else "FAIL"
        lines.append(f"- {marker} `{result.name}`: {result.detail}")
    lines.append("")
    (summary_dir / "release-preflight.md").write_text("\n".join(lines), encoding="utf-8")


def parse_minimal_toml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    current = root
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = root
            for part in line[1:-1].split("."):
                current = current.setdefault(part, {})
            continue
        if "=" not in line:
            raise ValueError(f"line {lineno}: expected key/value")
        key, value = [part.strip() for part in line.split("=", 1)]
        assign_toml_key(current, key, parse_toml_scalar(value.rstrip(","), lineno))
    return root


def assign_toml_key(table: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    target = table
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def parse_toml_scalar(value: str, lineno: int) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("{") and value.endswith("}"):
        result: dict[str, Any] = {}
        inner = value[1:-1].strip()
        if not inner:
            return result
        for part in split_toml_items(inner):
            key, raw = [item.strip() for item in part.split("=", 1)]
            result[key] = parse_toml_scalar(raw, lineno)
        return result
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_toml_scalar(part.strip(), lineno) for part in split_toml_items(inner) if part.strip()]
    raise ValueError(f"line {lineno}: unsupported value {value!r}")


def split_toml_items(value: str) -> list[str]:
    items: list[str] = []
    start = 0
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(value):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(value[start:index].strip())
            start = index + 1
    items.append(value[start:].strip())
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate LizzieYzy Next release asset metadata and dry-run workflow.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to validate")
    parser.add_argument("--summary-dir", type=Path, help="optional directory for markdown/json preflight summaries")
    parser.add_argument("--verbose", action="store_true", help="print passing checks as well as failures")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"Repository root does not exist: {root}", file=sys.stderr)
        return 2

    results = ReleaseAssetValidator(root).run()
    if args.summary_dir:
        summary_dir = args.summary_dir
        if not summary_dir.is_absolute():
            summary_dir = root / summary_dir
        write_summary(results, summary_dir)
    print_results(results, verbose=args.verbose)
    return 1 if any(not result.ok for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
