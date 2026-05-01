from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_release_assets.py"
SPEC = importlib.util.spec_from_file_location("validate_release_assets", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validate_release_assets = importlib.util.module_from_spec(SPEC)
sys.modules["validate_release_assets"] = validate_release_assets
SPEC.loader.exec_module(validate_release_assets)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def write_json(path: Path, content: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")


class ValidateReleaseAssetsTests(unittest.TestCase):
    def test_accepts_dry_run_release_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_release_contract(root)

            results = validate_release_assets.ReleaseAssetValidator(root).run()

            failures = [result for result in results if not result.ok]
            self.assertEqual([], failures)

    def test_rejects_publish_permissions_and_missing_no_sign(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_release_contract(root)
            workflow = root / ".github/workflows/release-dry-run.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8")
                .replace("contents: read", "contents: write")
                .replace("npm run tauri:build -- --no-bundle --ci --no-sign", "npm run tauri:build"),
                encoding="utf-8",
            )

            results = validate_release_assets.ReleaseAssetValidator(root).run()

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("release_workflow_dry_run", failures)
            self.assertIn("contents: write", failures["release_workflow_dry_run"])
            self.assertIn("--no-bundle --ci --no-sign", failures["release_workflow_dry_run"])

    def test_rejects_metadata_drift(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_release_contract(root)
            tauri_config = root / "apps/desktop/src-tauri/tauri.conf.json"
            config = json.loads(tauri_config.read_text(encoding="utf-8"))
            config["identifier"] = "org.example.wrong"
            config["version"] = "0.2.0"
            write_json(tauri_config, config)

            results = validate_release_assets.ReleaseAssetValidator(root).run()

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("tauri_release_metadata", failures)
            self.assertIn("identifier must be org.lizzieyzy.next", failures["tauri_release_metadata"])
            self.assertIn("versions must match", failures["tauri_release_metadata"])

    def _create_release_contract(self, root: Path) -> None:
        write_json(
            root / "apps/desktop/src-tauri/tauri.conf.json",
            {
                "$schema": "https://schema.tauri.app/config/2",
                "productName": "LizzieYzy Next",
                "version": "0.1.0",
                "identifier": "org.lizzieyzy.next",
                "mainBinaryName": "lizzieyzy-next-desktop",
                "build": {"frontendDist": "../dist"},
                "app": {"windows": [{"title": "LizzieYzy Next"}]},
                "bundle": {
                    "active": True,
                    "targets": "all",
                    "publisher": "LizzieYzy Next contributors",
                    "shortDescription": "Desktop Go review workspace.",
                    "longDescription": "Desktop Go review workspace powered by Tauri.",
                    "icon": ["icons/icon.png"],
                    "macOS": {"hardenedRuntime": True},
                    "windows": {"webviewInstallMode": {"type": "downloadBootstrapper"}},
                    "linux": {"deb": {"section": "utils"}},
                },
            },
        )
        write_json(
            root / "apps/desktop/package.json",
            {"name": "lizzieyzy-next-desktop", "version": "0.1.0"},
        )
        write(
            root / "apps/desktop/src-tauri/Cargo.toml",
            """
            [package]
            name = "lizzieyzy-next-desktop"
            version = "0.1.0"
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
                steps:
                  - run: python scripts/validate_release_assets.py --verbose --summary-dir release-dry-run
                  - env:
                      MACOS_SIGNING_READY: ${{ secrets.APPLE_CERTIFICATE != '' && secrets.APPLE_CERTIFICATE_PASSWORD != '' && secrets.APPLE_ID != '' && secrets.APPLE_PASSWORD != '' && secrets.APPLE_TEAM_ID != '' }}
                      WINDOWS_SIGNING_READY: ${{ secrets.WINDOWS_CERTIFICATE != '' && secrets.WINDOWS_CERTIFICATE_PASSWORD != '' }}
                      TAURI_UPDATER_SIGNING_READY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY != '' }}
                    run: |
                      echo "Tauri bundle mode: compile-only dry-run; no GitHub release is created"
                      echo "Signing/notarization/publish step: skipped by design for dry-run"
                  - run: npm run tauri:build -- --no-bundle --ci --no-sign
                  - uses: actions/upload-artifact@v4
                    with:
                      name: release-dry-run-${{ runner.os }}
                      path: |
                        release-dry-run/**
                        apps/desktop/dist/**
                        target/release/lizzieyzy-next-desktop*
                        target/release/bundle/**
            """,
        )
        write(
            root / ".github/release.yml",
            """
            changelog:
              categories:
                - title: Desktop Release Engineering
                  labels:
                    - release
                    - packaging
                    - desktop
                - title: Runtime Changes
                  labels:
                    - tauri
            """,
        )


if __name__ == "__main__":
    unittest.main()
