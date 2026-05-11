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
            create_complete_smoke_fixture(root, include_properties_command=False)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            self.assertEqual([], failures)
            self.assertIn("tauri_sgf_properties_command", pending_names)
            self.assertIn("ui_tauri_runtime_smoke", pending_names)

    def test_properties_command_passes_when_worker_a_command_is_registered(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, include_properties_command=True)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            properties_results = [
                result for result in results if result.name == "tauri_sgf_properties_command"
            ]
            self.assertEqual(["PASS"], [result.status for result in properties_results])

    def test_missing_label_fixture_token_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, include_properties_command=False)
            (root / smoke_user_flows.COMPAT_FIXTURE).write_text(
                "(;FF[4]GM[1]SZ[9]AB[aa]AW[bb]AE[cc]PL[W]C[root](;B[dd]))\n",
                encoding="utf-8",
            )

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("sgf_compat_fixture", failures)
            self.assertIn("labels", failures["sgf_compat_fixture"])


def create_complete_smoke_fixture(root: Path, *, include_properties_command: bool) -> None:
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
    properties_command = ""
    properties_handler = ""
    if include_properties_command:
        properties_command = """
        #[tauri::command]
        fn update_sgf_node_properties() {}
        """
        properties_handler = "update_sgf_node_properties,"
    write(
        root / "apps/desktop/src-tauri/src/lib.rs",
        f"""
        #[tauri::command]
        fn update_sgf_node_comment() {{}}

        #[tauri::command]
        fn append_sgf_move() {{}}

        #[tauri::command]
        fn delete_sgf_node() {{}}

        {properties_command}

        fn run() {{
            tauri::generate_handler![
                update_sgf_node_comment,
                append_sgf_move,
                delete_sgf_node,
                {properties_handler}
            ];
        }}
        """,
    )


if __name__ == "__main__":
    unittest.main()
