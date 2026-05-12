#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ACTION_MINIMUM_MAJORS = {
    "actions/checkout": 6,
    "actions/setup-node": 6,
    "actions/setup-python": 6,
    "actions/cache": 4,
    "actions/upload-artifact": 7,
    "actions/download-artifact": 8,
    "actions/github-script": 7,
}

DRY_RUN_FORBIDDEN_TOKENS = (
    "contents: write",
    "softprops/action-gh-release",
    "gh release",
    "github-script",
    "draft: false",
    "generate_release_notes:",
    "fail_on_unmatched_files:",
)


def require_file(root: Path, path: str) -> str:
    absolute = root / path
    if not absolute.is_file():
        raise AssertionError(f"Missing required release file: {path}")
    return absolute.read_text(encoding="utf-8")


def require_contains(path: str, text: str, needle: str) -> None:
    if needle not in text:
        raise AssertionError(f"{path} must contain {needle!r}")


def validate_action_runtime_hygiene(path: str, text: str) -> None:
    for line_number, action, ref in iter_action_uses(text):
        normalized_action = action.lower()
        major = action_major(ref)
        if major is None:
            continue
        minimum_major = ACTION_MINIMUM_MAJORS.get(normalized_action)
        if minimum_major is not None and major < minimum_major:
            raise AssertionError(
                f"{path}:{line_number} uses deprecated Node runtime action {action}@{ref}; "
                f"upgrade to v{minimum_major} or newer"
            )


def iter_action_uses(text: str):
    pattern = re.compile(r"^\s*(?:-\s*)?uses:\s*['\"]?([^@\s'\"]+)@([^#\s'\"]+)", re.MULTILINE)
    for match in pattern.finditer(text):
        line_number = text.count("\n", 0, match.start()) + 1
        yield line_number, match.group(1), match.group(2).rstrip("'\"")


def action_major(ref: str) -> int | None:
    match = re.match(r"v(\d+)(?:\b|[.\-])", ref)
    if not match:
        return None
    return int(match.group(1))


def workflow_paths(root: Path) -> list[Path]:
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        raise AssertionError("Missing required workflow directory: .github/workflows")
    return sorted(path for pattern in ("*.yml", "*.yaml") for path in workflows_dir.glob(pattern))


def workflow_display_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def validate_dry_run_workflow(workflow: str) -> None:
    path = ".github/workflows/release-dry-run.yml"
    lower_workflow = workflow.lower()
    for token in DRY_RUN_FORBIDDEN_TOKENS:
        if token in lower_workflow:
            raise AssertionError(f"{path} must not contain release mutation token {token!r}")

    for needle in (
        "workflow_dispatch:",
        "contents: read",
        "macos-latest",
        "windows-latest",
        "ubuntu-latest",
        "actions/checkout@",
        "actions/setup-node@",
        "actions/setup-python@",
        "actions/upload-artifact@",
        "python scripts/validate_release_assets.py --verbose --summary-dir release-dry-run",
        "npm run tauri:build -- --no-bundle --ci --no-sign",
        "xvfb",
        "xdotool",
        "wmctrl",
        "name: Linux unsigned installed-app smoke",
        "name: Windows unsigned installed-app smoke",
        "runner.os == 'Linux'",
        "runner.os == 'Windows'",
        "github.event_name != 'workflow_dispatch' || inputs.run_tauri_build",
        "shell: bash",
        "python scripts/smoke_windows_linux_installed_app.py",
        "xvfb-run -a python scripts/smoke_windows_linux_installed_app.py",
        "--platform linux",
        "--platform windows",
        "--binary target/release/lizzieyzy-next-desktop",
        "--binary target/release/lizzieyzy-next-desktop.exe",
        "--window-title \"LizzieYzy Next\"",
        "--evidence-out \"release-dry-run/${RUNNER_OS}-installed-app-smoke.json\"",
        "Tauri bundle mode: compile-only dry-run; no GitHub release is created",
        "Signing/notarization/publish step: skipped by design for dry-run",
        "release-dry-run-${{ runner.os }}",
        "release-dry-run/**",
        "target/release/bundle/**",
    ):
        require_contains(path, workflow, needle)

    for secret in (
        "secrets.APPLE_CERTIFICATE",
        "secrets.WINDOWS_CERTIFICATE",
        "secrets.TAURI_SIGNING_PRIVATE_KEY",
    ):
        require_contains(path, workflow, secret)


def validate(root: Path) -> None:
    workflow = require_file(root, ".github/workflows/release.yml")
    dry_run_workflow = require_file(root, ".github/workflows/release-dry-run.yml")
    release_config = require_file(root, ".github/release.yml")
    release_notes = require_file(root, ".github/RELEASE_NOTES_v0.1.0.md")
    collector = require_file(root, "scripts/collect_release_assets.py")

    for path in workflow_paths(root):
        validate_action_runtime_hygiene(workflow_display_path(root, path), path.read_text(encoding="utf-8"))

    if "python3 scripts/" in workflow:
        raise AssertionError(".github/workflows/release.yml must use cross-platform `python`, not `python3`, inside matrix jobs")
    if "python3 scripts/" in dry_run_workflow:
        raise AssertionError(".github/workflows/release-dry-run.yml must use cross-platform `python`, not `python3`, inside matrix jobs")

    for needle in (
        "tags:",
        '"v*"',
        "macos-latest",
        "windows-latest",
        "ubuntu-latest",
        "python scripts/validate_scaffold.py --verbose",
        "python scripts/validate_release_assets.py --verbose",
        "python scripts/validate_release_workflow.py --verbose",
        "npm run tauri:build -- --ci --no-sign",
        "python scripts/collect_release_assets.py",
        "scripts/collect_release_assets.py",
        "softprops/action-gh-release@v2",
        "SHA256SUMS.txt",
        "prerelease: true",
        "target/release/bundle",
    ):
        require_contains(".github/workflows/release.yml", workflow, needle)

    for needle in ("changelog:", "categories:", "Desktop Release Engineering", "Runtime Changes"):
        require_contains(".github/release.yml", release_config, needle)

    for needle in ("hashlib.sha256", "RELEASE_SUFFIXES", "SHA256SUMS-{platform}.txt"):
        require_contains("scripts/collect_release_assets.py", collector, needle)

    for needle in ("English", "中文", "macOS", "Windows", "Linux", "Known limitations"):
        require_contains(".github/RELEASE_NOTES_v0.1.0.md", release_notes, needle)

    validate_dry_run_workflow(dry_run_workflow)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the production release workflow contract.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    try:
        validate(root)
    except AssertionError as exc:
        print(f"FAIL release workflow: {exc}", file=sys.stderr)
        return 1

    print("PASS release workflow: action runtime hygiene, tag release publishing contract, and dry-run no-publish/no-sign contract validated")
    if args.verbose:
        print(f"Repository: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
