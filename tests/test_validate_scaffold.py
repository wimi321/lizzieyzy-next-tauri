from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_scaffold.py"
SPEC = importlib.util.spec_from_file_location("validate_scaffold", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validate_scaffold = importlib.util.module_from_spec(SPEC)
sys.modules["validate_scaffold"] = validate_scaffold
SPEC.loader.exec_module(validate_scaffold)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def write_json(path: Path, content: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")


class ValidateScaffoldTests(unittest.TestCase):
    def test_reports_missing_frontend_as_single_group_failure(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "Cargo.toml",
                """
                [workspace]
                resolver = "2"
                members = []
                """,
            )

            results = validate_scaffold.Validator(root).run()

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("desktop_frontend", failures)
            self.assertIn("apps/desktop/package.json", failures["desktop_frontend"])

    def test_accepts_complete_minimal_scaffold(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_complete_scaffold(root)

            results = validate_scaffold.Validator(root).run()

            failures = [result for result in results if not result.ok]
            self.assertEqual([], failures)

    def _create_complete_scaffold(self, root: Path) -> None:
        members = validate_scaffold.WORKSPACE_MEMBERS
        write(
            root / "Cargo.toml",
            """
            [workspace]
            resolver = "2"
            members = [
              "apps/desktop/src-tauri",
              "crates/app-model",
              "crates/go-core",
              "crates/sgf",
              "crates/katago-protocol",
              "crates/analysis-core",
              "crates/engine-manager",
              "crates/storage",
            ]

            [workspace.package]
            edition = "2021"
            rust-version = "1.82"
            """,
        )
        write_json(
            root / "apps/desktop/package.json",
            {
                "scripts": {
                    "dev": "vite",
                    "build": "tsc && vite build",
                    "tauri:dev": "tauri dev",
                    "tauri:build": "tauri build",
                },
                "dependencies": {
                    "@tauri-apps/api": "latest",
                    "react": "latest",
                    "react-dom": "latest",
                },
                "devDependencies": {
                    "@tauri-apps/cli": "latest",
                    "typescript": "latest",
                    "vite": "latest",
                },
            },
        )
        for rel in [
            "apps/desktop/tsconfig.json",
            "apps/desktop/src-tauri/capabilities/default.json",
        ]:
            write_json(root / rel, {"permissions": ["core:default", "opener:default"]})
        for rel in [
            "apps/desktop/vite.config.ts",
            "apps/desktop/index.html",
            "apps/desktop/src/App.tsx",
            "apps/desktop/src/main.tsx",
            "apps/desktop/src-tauri/build.rs",
            "apps/desktop/src-tauri/src/lib.rs",
            "apps/desktop/src-tauri/src/main.rs",
        ]:
            write(root / rel, "export {}\n")
        write_json(
            root / "apps/desktop/src-tauri/tauri.conf.json",
            {
                "identifier": "org.lizzieyzy.next",
                "build": {
                    "beforeDevCommand": "npm run dev",
                    "devUrl": "http://127.0.0.1:1420",
                    "beforeBuildCommand": "npm run build",
                    "frontendDist": "../dist",
                },
            },
        )
        write(
            root / "apps/desktop/src-tauri/Cargo.toml",
            """
            [package]
            name = "desktop"
            edition.workspace = true

            [dependencies]
            tauri = "2"
            tauri-plugin-opener = "2"
            sgf = { path = "../../../crates/sgf" }
            analysis-core = { path = "../../../crates/analysis-core" }
            engine-manager = { path = "../../../crates/engine-manager" }
            """,
        )
        for member in members[1:]:
            write(
                root / member / "Cargo.toml",
                f"""
                [package]
                name = "{Path(member).name}"
                edition.workspace = true
                """,
            )
            write(root / member / "src/lib.rs", "pub fn marker() {}\n")
        doc = "Tauri Rust TypeScript production migration handoff. " * 30
        for rel in [
            "docs/ARCHITECTURE_NEXT.md",
            "docs/MIGRATION_PLAN.md",
            "docs/AGENT_EXECUTION_SUMMARY.md",
        ]:
            write(root / rel, f"# Doc\n\n{doc}\n")
        write(
            root / "tests/golden/basic_19x19.sgf",
            "(;GM[1]FF[4]SZ[19]KM[7.5];B[pd];W[dd])\n",
        )


if __name__ == "__main__":
    unittest.main()
