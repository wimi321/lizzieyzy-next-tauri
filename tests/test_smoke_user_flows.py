from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_user_flows.py"
SPEC = importlib.util.spec_from_file_location("smoke_user_flows", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke_user_flows = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_user_flows"] = smoke_user_flows
SPEC.loader.exec_module(smoke_user_flows)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def write_json(path: Path, content: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")


class SmokeUserFlowsTests(unittest.TestCase):
    def test_complete_local_smoke_inputs_pass_with_pending_external_gates(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("tauri_sgf_edit_commands", pass_names)
            for name in smoke_user_flows.TAURI_COMMAND_GROUPS:
                self.assertIn(name, pass_names)
            self.assertIn("ui_tauri_runtime_smoke", pending_names)
            self.assertIn("katago_live_smoke", pending_names)
            self.assertIn("readboard_live_smoke", pending_names)
            self.assertIn("provider_live_smoke", pending_names)
            self.assertIn("multiplatform_packaging_smoke", pending_names)

    def test_missing_properties_command_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, omitted_commands={"update_sgf_node_properties"})

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("tauri_sgf_properties_command", failures)
            self.assertIn("update_sgf_node_properties function", failures["tauri_sgf_properties_command"])
            self.assertNotIn("tauri_sgf_properties_command", {result.name for result in results if result.status == "PENDING"})

    def test_missing_reorder_command_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, omitted_commands={"reorder_sgf_variation"})

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("tauri_sgf_reorder_command", failures)
            self.assertIn("reorder_sgf_variation function", failures["tauri_sgf_reorder_command"])
            self.assertNotIn("tauri_sgf_reorder_command", {result.name for result in results if result.status == "PENDING"})

    def test_missing_new_local_command_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, omitted_commands={"write_sgf_file"})

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("tauri_sgf_file_commands", failures)
            self.assertIn("write_sgf_file function", failures["tauri_sgf_file_commands"])

    def test_command_function_allows_intermediate_rust_attributes(self) -> None:
        text = """
        #[tauri::command]
        #[allow(clippy::too_many_arguments)]
        fn save_analysis_cache() {}
        """

        self.assertTrue(smoke_user_flows.has_tauri_command_function(text, "save_analysis_cache"))

    def test_missing_label_fixture_token_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            (root / smoke_user_flows.COMPAT_FIXTURE).write_text(
                "(;FF[4]GM[1]SZ[9]AB[aa]AW[bb]AE[cc]PL[W]C[root](;B[dd]))\n",
                encoding="utf-8",
            )

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("sgf_compat_fixture", failures)
            self.assertIn("labels", failures["sgf_compat_fixture"])

    def test_reorder_fixture_requires_three_sibling_variations(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            (root / smoke_user_flows.REORDER_FIXTURE).write_text(
                "(;FF[4]GM[1]SZ[9]C[root]ZZ[x];B[dd]LB[dd:A]TR[dd](;W[cf]C[one])(;W[fd]C[two]))\n",
                encoding="utf-8",
            )

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("sgf_reorder_fixture", failures)
            self.assertIn("3 sibling variations", failures["sgf_reorder_fixture"])


def create_complete_smoke_fixture(
    root: Path,
    *,
    omitted_commands: set[str] | None = None,
) -> None:
    omitted_commands = omitted_commands or set()
    write_json(
        root / "package.json",
        {
            "scripts": {
                "desktop:dev": "npm --prefix apps/desktop run tauri:dev",
                "desktop:build": "npm --prefix apps/desktop run build",
                "desktop:tauri-build": "npm --prefix apps/desktop run tauri:build",
                "validate": "python3 scripts/validate_scaffold.py",
            }
        },
    )
    write_json(
        root / "apps/desktop/package.json",
        {
            "scripts": {
                "dev": "vite",
                "build": "tsc && vite build",
                "preview": "vite preview",
                "tauri:dev": "tauri dev",
                "tauri:build": "tauri build",
            }
        },
    )
    for rel in smoke_user_flows.GOLDEN_SGF_FIXTURES:
        write(root / rel, "(;FF[4]GM[1]SZ[9];B[aa];W[bb])\n")
    write(
        root / smoke_user_flows.COMPAT_FIXTURE,
        "(;FF[4]GM[1]SZ[9]AB[aa]AW[bb]AE[cc]PL[W]LB[aa:A]C[root](;B[dd]C[branch]))\n",
    )
    write(
        root / smoke_user_flows.REORDER_FIXTURE,
        "(;FF[4]GM[1]SZ[9]C[root]ZZ[x];B[dd]LB[dd:A]TR[dd](;W[cf]C[one]ZZ[a];B[fc]C[child])(;W[fd]C[two]ZZ[b](;B[df]C[nested]))(;W[dc]C[three]ZZ[c]))\n",
    )
    commands = [
        *smoke_user_flows.TAURI_COMMANDS,
        *[
            command
            for group in smoke_user_flows.TAURI_COMMAND_GROUPS.values()
            for command in group
        ],
    ]
    command_functions = "\n".join(
        f"""
        #[tauri::command]
        fn {command}() {{}}
        """
        for command in commands
        if command not in omitted_commands
    )
    command_handlers = "\n".join(
        f"                {command},"
        for command in commands
        if command not in omitted_commands
    )
    write(
        root / "apps/desktop/src-tauri/src/lib.rs",
        f"""
        {command_functions}

        fn run() {{
            tauri::generate_handler![
{command_handlers}
            ];
        }}
        """,
    )


if __name__ == "__main__":
    unittest.main()
