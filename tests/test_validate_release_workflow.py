from __future__ import annotations

import importlib.util
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_release_workflow.py"
SPEC = importlib.util.spec_from_file_location("validate_release_workflow", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validate_release_workflow = importlib.util.module_from_spec(SPEC)
sys.modules["validate_release_workflow"] = validate_release_workflow
SPEC.loader.exec_module(validate_release_workflow)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


class ValidateReleaseWorkflowTests(unittest.TestCase):
    def test_accepts_current_release_and_dry_run_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_release_workflow_contract(root)

            validate_release_workflow.validate(root)

    def test_rejects_deprecated_action_majors_in_release_workflow(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_release_workflow_contract(root)
            release = root / ".github/workflows/release.yml"
            release.write_text(
                release.read_text(encoding="utf-8")
                .replace("actions/checkout@v6", "actions/checkout@v3", 1)
                .replace("actions/setup-node@v6", "actions/setup-node@v3", 1),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(AssertionError, "deprecated Node runtime action actions/checkout@v3"):
                validate_release_workflow.validate(root)

    def test_rejects_deprecated_action_majors_in_dry_run_workflow(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_release_workflow_contract(root)
            dry_run = root / ".github/workflows/release-dry-run.yml"
            dry_run.write_text(
                dry_run.read_text(encoding="utf-8")
                .replace("actions/upload-artifact@v7", "actions/upload-artifact@v3", 1),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(AssertionError, "deprecated Node runtime action actions/upload-artifact@v3"):
                validate_release_workflow.validate(root)

    def test_rejects_old_setup_python_and_github_script(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_release_workflow_contract(root)
            release = root / ".github/workflows/release.yml"
            release.write_text(
                release.read_text(encoding="utf-8")
                .replace("actions/setup-python@v6", "actions/setup-python@v4", 1)
                + "\n      - uses: actions/github-script@v6\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(AssertionError, "deprecated Node runtime action actions/setup-python@v4"):
                validate_release_workflow.validate(root)

    def test_rejects_node20_majors_in_tauri_next_ci(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_release_workflow_contract(root)
            write(
                root / ".github/workflows/tauri-next-ci.yml",
                """
                name: tauri-next-ci
                on:
                  pull_request:
                jobs:
                  ci:
                    steps:
                      - uses: actions/checkout@v4
                      - uses: actions/setup-node@v4
                      - uses: actions/setup-python@v5
                      - run: python --version
                """,
            )

            with self.assertRaisesRegex(AssertionError, "tauri-next-ci.yml:.*actions/checkout@v4"):
                validate_release_workflow.validate(root)

    def test_rejects_dry_run_over_publish_behavior(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_release_workflow_contract(root)
            dry_run = root / ".github/workflows/release-dry-run.yml"
            dry_run.write_text(
                dry_run.read_text(encoding="utf-8")
                .replace("contents: read", "contents: write", 1)
                + "\n      - uses: softprops/action-gh-release@v2\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(AssertionError, "must not contain release mutation token 'contents: write'"):
                validate_release_workflow.validate(root)

    def test_rejects_dry_run_signing_or_bundle_drift(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_release_workflow_contract(root)
            dry_run = root / ".github/workflows/release-dry-run.yml"
            dry_run.write_text(
                dry_run.read_text(encoding="utf-8")
                .replace("npm run tauri:build -- --no-bundle --ci --no-sign", "npm run tauri:build -- --ci", 1),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(AssertionError, r"--no-bundle --ci --no-sign"):
                validate_release_workflow.validate(root)


def create_release_workflow_contract(root: Path) -> None:
    write(
        root / ".github/workflows/release.yml",
        """
        name: release
        on:
          push:
            tags:
              - "v*"
        permissions:
          contents: write
        jobs:
          build:
            strategy:
              matrix:
                include:
                  - platform: linux-x64
                    runner: ubuntu-latest
                  - platform: macos
                    runner: macos-latest
                  - platform: windows-x64
                    runner: windows-latest
            steps:
              - uses: actions/checkout@v6
              - uses: actions/setup-node@v6
              - uses: actions/setup-python@v6
              - run: |
                  python scripts/validate_scaffold.py --verbose
                  python scripts/validate_release_assets.py --verbose
                  python scripts/validate_release_workflow.py --verbose
              - run: npm run tauri:build -- --ci --no-sign
              - run: |
                  python scripts/collect_release_assets.py \\
                    --bundle-dir target/release/bundle \\
                    --out-dir release-assets/${{ matrix.platform }} \\
                    --platform ${{ matrix.platform }}
                  echo scripts/collect_release_assets.py
              - uses: actions/upload-artifact@v7
          publish:
            steps:
              - uses: actions/checkout@v6
              - uses: actions/download-artifact@v8
              - run: |
                  sha256sum * > SHA256SUMS.txt
                  echo target/release/bundle
              - uses: softprops/action-gh-release@v2
                with:
                  prerelease: true
        """,
    )
    write(
        root / ".github/workflows/release-dry-run.yml",
        """
        name: release-dry-run
        on:
          workflow_dispatch:
          push:
            tags:
              - "v*"
        permissions:
          contents: read
        jobs:
          preflight:
            strategy:
              matrix:
                include:
                  - label: macOS
                    os: macos-latest
                  - label: Linux
                    os: ubuntu-latest
                  - label: Windows
                    os: windows-latest
            steps:
              - uses: actions/checkout@v6
              - uses: actions/setup-node@v6
              - uses: actions/setup-python@v6
              - run: python scripts/validate_release_assets.py --verbose --summary-dir release-dry-run
              - env:
                  MACOS_SIGNING_READY: ${{ secrets.APPLE_CERTIFICATE != '' }}
                  WINDOWS_SIGNING_READY: ${{ secrets.WINDOWS_CERTIFICATE != '' }}
                  TAURI_UPDATER_SIGNING_READY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY != '' }}
                run: |
                  echo "Tauri bundle mode: compile-only dry-run; no GitHub release is created"
                  echo "Signing/notarization/publish step: skipped by design for dry-run"
              - run: npm run tauri:build -- --no-bundle --ci --no-sign
              - uses: actions/upload-artifact@v7
                with:
                  name: release-dry-run-${{ runner.os }}
                  path: |
                    release-dry-run/**
                    target/release/bundle/**
        """,
    )
    write(
        root / ".github/release.yml",
        """
        changelog:
          categories:
            - title: Desktop Release Engineering
            - title: Runtime Changes
        """,
    )
    write(
        root / ".github/RELEASE_NOTES_v0.1.0.md",
        """
        # Release Notes
        English
        中文
        macOS
        Windows
        Linux
        Known limitations
        """,
    )
    write(
        root / "scripts/collect_release_assets.py",
        """
        import hashlib
        hashlib.sha256(b"")
        RELEASE_SUFFIXES = {}
        pattern = "SHA256SUMS-{platform}.txt"
        """,
    )


if __name__ == "__main__":
    unittest.main()
