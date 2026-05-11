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
            self.assertIn("legacy_shell_menu_surface", pass_names)
            self.assertIn("native_sgf_save_readback_surface", pass_names)
            self.assertIn("sgf_existing_move_edit_surface", pass_names)
            for name in smoke_user_flows.TAURI_COMMAND_GROUPS:
                self.assertIn(name, pass_names)
            self.assertIn("ui_tauri_runtime_smoke", pending_names)
            self.assertIn("katago_live_smoke", pending_names)
            self.assertIn("readboard_live_smoke", pending_names)
            self.assertIn("provider_live_smoke", pending_names)
            self.assertIn("multiplatform_packaging_smoke", pending_names)

    def test_valid_tauri_runtime_ui_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_tauri_runtime_ui_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("ui_tauri_runtime_smoke", pass_names)
            self.assertNotIn("ui_tauri_runtime_smoke", pending_names)

    def test_invalid_tauri_runtime_ui_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_json(
                root / smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_EVIDENCE,
                {
                    "schema": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_SCHEMA,
                    "status": "pass",
                    "platform": "macos",
                    "checks": [{"name": "runtime_started", "status": "pass"}],
                },
            )

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("ui_tauri_runtime_smoke", failures)
            self.assertIn("ui_tauri_runtime_smoke", pending)
            self.assertIn("missing required checks", pending["ui_tauri_runtime_smoke"])

    def test_semantic_invalid_tauri_runtime_ui_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_tauri_runtime_ui_evidence()
            find_evidence_check(evidence, "variation_reorder")["evidence"]["targetIndex"] = 2
            write_json(root / smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("ui_tauri_runtime_smoke", failures)
            self.assertIn("ui_tauri_runtime_smoke", pending)
            self.assertIn("variation_reorder target index must be 0", pending["ui_tauri_runtime_smoke"])

    def test_runtime_evidence_uses_save_readback_roundtrip_name(self) -> None:
        self.assertIn("save_readback_roundtrip", smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_REQUIRED_CHECKS)
        self.assertNotIn("save_reopen_roundtrip", smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_REQUIRED_CHECKS)

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

    def test_missing_edit_existing_move_command_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, omitted_commands={"edit_sgf_move"})

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("sgf_existing_move_edit_surface", failures)
            self.assertIn("edit_sgf_move function", failures["sgf_existing_move_edit_surface"])

    def test_missing_edit_existing_move_app_handler_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, app_edit_handler=False)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("sgf_existing_move_edit_surface", failures)
            self.assertIn("App missing handleEditExistingMove", failures["sgf_existing_move_edit_surface"])

    def test_edit_existing_move_surface_reduced_fixture_all_frontend_sources_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            for rel in (smoke_user_flows.BACKEND_SOURCE, smoke_user_flows.APP_SOURCE, smoke_user_flows.SGF_TREE_PANEL_SOURCE):
                (root / rel).unlink()

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("sgf_existing_move_edit_surface", failures)
            self.assertIn("sgf_existing_move_edit_surface", pending)
            self.assertIn("reduced fixture", pending["sgf_existing_move_edit_surface"])

    def test_edit_existing_move_surface_partial_frontend_source_missing_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            (root / smoke_user_flows.SGF_TREE_PANEL_SOURCE).unlink()

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("sgf_existing_move_edit_surface", failures)
            self.assertIn("SgfTreePanel source", failures["sgf_existing_move_edit_surface"])

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

    def test_legacy_shell_literal_disabled_true_menu_item_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_legacy_shell_fixture(root, disabled_entries={("View", "Candidates")})

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("legacy_shell_menu_surface", failures)
            self.assertIn("View/Candidates has literal disabled: true", failures["legacy_shell_menu_surface"])

    def test_legacy_shell_literal_disabled_true_with_handler_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_legacy_shell_fixture(root, disabled_entries_with_handler={("Engine", "Profiles")})

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("legacy_shell_menu_surface", failures)
            self.assertIn("Engine/Profiles has literal disabled: true", failures["legacy_shell_menu_surface"])

    def test_legacy_shell_missing_menu_item_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_legacy_shell_fixture(root, omitted_entries={("Tools", "Providers")})

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("legacy_shell_menu_surface", failures)
            self.assertIn("Tools/Providers menu entry missing", failures["legacy_shell_menu_surface"])

    def test_native_sgf_save_readback_missing_backend_readback_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_backend_fixture(root, read_back_after_save=False)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("native_sgf_save_readback_surface", failures)
            self.assertIn("backend saveSgfDocument does not read back the saved SGF", failures["native_sgf_save_readback_surface"])

    def test_native_sgf_save_readback_missing_app_refresh_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_app_fixture(root, refresh_after_save=False)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("native_sgf_save_readback_surface", failures)
            self.assertIn("App handleSaveSgfDocument missing uses saved.sgfText/read-back text", failures["native_sgf_save_readback_surface"])


def create_complete_smoke_fixture(
    root: Path,
    *,
    omitted_commands: set[str] | None = None,
    app_edit_handler: bool = True,
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
    create_legacy_shell_fixture(root)
    create_backend_fixture(root)
    create_app_fixture(root, edit_existing_move_handler=app_edit_handler)
    create_sgf_tree_panel_fixture(root)


def write_valid_tauri_runtime_ui_evidence(root: Path) -> None:
    write_json(root / smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_EVIDENCE, valid_tauri_runtime_ui_evidence())


def valid_tauri_runtime_ui_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_SCHEMA,
        "status": "pass",
        "platform": "macos",
        "checks": [
            {"name": name, "status": "pass", "evidence": valid_runtime_check_evidence(name)}
            for name in smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_REQUIRED_CHECKS
        ],
    }


def valid_runtime_check_evidence(name: str) -> dict[str, object]:
    if name == "variation_reorder":
        return {
            "nodeId": "variation-b",
            "movedNodeId": "variation-b",
            "targetIndex": 0,
            "indexAfterMove": 0,
            "variationIndexAfterMove": 0,
            "parentNodeId": "root",
        }
    if name == "edit_move":
        vertex = {"point": {"x": 3, "y": 3}}
        return {"nodeId": "move-1", "targetVertex": vertex, "confirmedVertex": vertex}
    if name == "delete_node":
        return {"deletedNodeId": "variation-c", "existsAfterDelete": False}
    if name == "save_readback_roundtrip":
        return {"savedPath": "<tmp>/runtime-smoke.sgf", "readbackMatchesSaved": True}
    if name == "board_state_verified":
        return {"invariant": "replayed position count equals parsed move count plus initial position", "verified": True}
    return {"observed": True}


def find_evidence_check(evidence: dict[str, object], name: str) -> dict[str, object]:
    checks = evidence["checks"]
    assert isinstance(checks, list)
    for check in checks:
        assert isinstance(check, dict)
        if check.get("name") == name:
            return check
    raise AssertionError(f"missing check {name}")


def create_legacy_shell_fixture(
    root: Path,
    *,
    disabled_entries: set[tuple[str, str]] | None = None,
    disabled_entries_with_handler: set[tuple[str, str]] | None = None,
    omitted_entries: set[tuple[str, str]] | None = None,
) -> None:
    disabled_entries = disabled_entries or set()
    disabled_entries_with_handler = disabled_entries_with_handler or set()
    omitted_entries = omitted_entries or set()
    menu_blocks: list[str] = []
    for group, items in smoke_user_flows.LEGACY_SHELL_MENU_SURFACE.items():
        item_blocks: list[str] = []
        for item in items:
            if (group, item) in omitted_entries:
                continue
            if (group, item) in disabled_entries:
                item_blocks.append(f'{{ label: "{item}", disabled: true }}')
            elif (group, item) in disabled_entries_with_handler:
                handler_name = "on" + "".join(part for part in re_identifier_parts(item))
                item_blocks.append(f'{{ label: "{item}", onSelect: {handler_name}, disabled: true }}')
            else:
                handler_name = "on" + "".join(part for part in re_identifier_parts(item))
                item_blocks.append(f'{{ label: "{item}", onSelect: {handler_name}, disabled: isBusy }}')
        menu_blocks.append(
            f"""
            {{
              label: "{group}",
              items: [
                {",".join(item_blocks)}
              ]
            }}
            """
        )
    write(
        root / smoke_user_flows.LEGACY_SHELL_SOURCE,
        f"""
        export function LegacyShell() {{
          const isBusy = false;
          const onCandidates = () => undefined;
          const onOwnership = () => undefined;
          const onPolicy = () => undefined;
          const onProfiles = () => undefined;
          const onAssets = () => undefined;
          const onProviders = () => undefined;
          const onPreferences = () => undefined;
          const onBackendstatus = () => undefined;
          const menuGroups = [
            {",".join(menu_blocks)}
          ];
          return menuGroups;
        }}
        """,
    )


def create_backend_fixture(root: Path, *, read_back_after_save: bool = True) -> None:
    if read_back_after_save:
        save_body = """
        const targetPath = path ?? await save({ filters: sgfDialogFilters, defaultPath: defaultFileName });
        if (!targetPath) return null;
        await invoke<void>("write_sgf_file", { path: targetPath, sgfText });
        const savedSgfText = await invoke<string>("read_sgf_file", { path: targetPath });
        return { path: targetPath, sgfText: savedSgfText };
        """
    else:
        save_body = """
        const targetPath = path ?? await save({ filters: sgfDialogFilters, defaultPath: defaultFileName });
        if (!targetPath) return null;
        await invoke<void>("write_sgf_file", { path: targetPath, sgfText });
        return { path: targetPath, sgfText };
        """
    write(
        root / smoke_user_flows.BACKEND_SOURCE,
        f"""
        import {{ invoke }} from "@tauri-apps/api/core";
        import {{ open, save }} from "@tauri-apps/plugin-dialog";

        const sgfDialogFilters = [{{ name: "SGF files", extensions: ["sgf", "txt"] }}];

        export type SgfDocument = {{
          path: string | null;
          sgfText: string;
        }};

        export async function openSgfDocument(): Promise<SgfDocument | null> {{
          const selected = await open({{ multiple: false, directory: false, filters: sgfDialogFilters }});
          if (typeof selected !== "string") return null;
          const sgfText = await invoke<string>("read_sgf_file", {{ path: selected }});
          return {{ path: selected, sgfText }};
        }}

        export async function saveSgfDocument(path: string | null, sgfText: string, defaultFileName = "review.sgf"): Promise<SgfDocument | null> {{
          {save_body}
        }}

        export async function editSgfMove(sgfText: string, nodeId: string, point: MoveVertex | "pass") {{
          return await invoke("edit_sgf_move", {{ sgfText, nodeId, point }});
        }}
        """,
    )


def create_app_fixture(
    root: Path,
    *,
    refresh_after_save: bool = True,
    edit_existing_move_handler: bool = True,
) -> None:
    if refresh_after_save:
        save_body = """
        const saved = await saveSgfDocument(saveAs ? null : currentFilePath, sgfText, saveFileName);
        if (!saved) {
          setMessage("Save cancelled.");
          return;
        }
        setSgfText(saved.sgfText);
        sgfTextEditVersionRef.current += 1;
        const sgfTreeRequest = beginSgfTreeLoad();
        const [parsed, replayed, tree] = await Promise.all([
          parseSgfSummary(saved.sgfText),
          replaySgfPositions(saved.sgfText),
          parseSgfTree(saved.sgfText)
        ]);
        const targetMove = replayed.at(-1)?.move_number ?? parsed.moves.length;
        setCurrentFilePath(saved.path);
        setDirty(false);
        setGame(parsed);
        setPositions(replayed);
        applySgfTree(tree, targetMove, sgfTreeRequest);
        setMessage(`Saved ${saved.path ? fileNameFromPath(saved.path) : saveFileName}.`);
        await checkAnalysisCacheForGame(saved.sgfText, saved.path, parsed, replayed, "Saved.", tree);
        """
    else:
        save_body = """
        const saved = await saveSgfDocument(saveAs ? null : currentFilePath, sgfText, saveFileName);
        if (!saved) {
          setMessage("Save cancelled.");
          return;
        }
        setCurrentFilePath(saved.path);
        setDirty(false);
        setMessage(`Saved ${saved.path ? fileNameFromPath(saved.path) : saveFileName}.`);
        """
    edit_handler_body = """
      const sgfMoveEditMode = "existing";
      const normalizeEditSgfMoveResult = (result) => result;
      async function callEditSgfMove(nodeId, point) {
        return normalizeEditSgfMoveResult(await editSgfMove(sgfText, nodeId, point));
      }
      async function handleEditExistingMove(nodeId, point) {
        await callEditSgfMove(nodeId, point);
        return sgfMoveEditMode;
      }
    """ if edit_existing_move_handler else """
      const sgfMoveEditMode = "append";
    """
    write(
        root / smoke_user_flows.APP_SOURCE,
        f"""
        export function App() {{
          const currentFilePath = null;
          const sgfText = "(;GM[1])";
          const saveFileName = "review.sgf";
          const sgfTextEditVersionRef = {{ current: 0 }};
          async function handleSaveSgfDocument(saveAs = false) {{
            try {{
              {save_body}
            }} catch (error) {{
              setMessage(`Save failed: ${{error}}`);
            }}
          }}
          {edit_handler_body}
          return handleSaveSgfDocument;
        }}
        """,
    )


def create_sgf_tree_panel_fixture(root: Path) -> None:
    write(
        root / smoke_user_flows.SGF_TREE_PANEL_SOURCE,
        """
        type Props = {
          moveEditMode: "append" | "existing";
          canEditSelectedMove: boolean;
          onEditSelectedMovePass: (nodeId: string) => void;
        };

        export function SgfTreePanel({ moveEditMode, canEditSelectedMove, onEditSelectedMovePass }: Props) {
          return { moveEditMode, canEditSelectedMove, onEditSelectedMovePass };
        }
        """,
    )


def re_identifier_parts(value: str) -> list[str]:
    return [part[:1].upper() + part[1:] for part in value.split()]


if __name__ == "__main__":
    unittest.main()
