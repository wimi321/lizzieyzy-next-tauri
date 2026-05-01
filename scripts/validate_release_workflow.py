#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require_file(root: Path, path: str) -> str:
    absolute = root / path
    if not absolute.is_file():
        raise AssertionError(f"Missing required release file: {path}")
    return absolute.read_text(encoding="utf-8")


def require_contains(path: str, text: str, needle: str) -> None:
    if needle not in text:
        raise AssertionError(f"{path} must contain {needle!r}")


def validate(root: Path) -> None:
    workflow = require_file(root, ".github/workflows/release.yml")
    release_config = require_file(root, ".github/release.yml")
    release_notes = require_file(root, ".github/RELEASE_NOTES_v0.1.0.md")
    collector = require_file(root, "scripts/collect_release_assets.py")

    if "python3 scripts/" in workflow:
        raise AssertionError(".github/workflows/release.yml must use cross-platform `python`, not `python3`, inside matrix jobs")

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

    print("PASS release workflow: tag trigger, three OS runners, Tauri bundling, checksums, and GitHub Release publishing validated")
    if args.verbose:
        print(f"Repository: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
