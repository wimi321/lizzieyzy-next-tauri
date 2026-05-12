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
            self.assertIn("sgf_annotation_surface", pass_names)
            self.assertIn("legacy_config_migration_surface", pass_names)
            self.assertIn("runtime_asset_layout_surface", pass_names)
            for name in smoke_user_flows.TAURI_COMMAND_GROUPS:
                self.assertIn(name, pass_names)
            self.assertIn("ui_tauri_runtime_smoke", pending_names)
            self.assertIn("desktop_sgf_editing_ux_smoke", pending_names)
            self.assertIn("desktop_ui_click_smoke", pending_names)
            self.assertIn("legacy_shell_menu_action_smoke", pending_names)
            self.assertIn("native_menu_shortcut_smoke", pending_names)
            self.assertIn("tauri_window_runtime_smoke", pending_names)
            self.assertIn("tauri_webview_dom_click_smoke", pending_names)
            self.assertIn("legacy_layout_parity_smoke", pending_names)
            self.assertIn("legacy_shortcut_layout_evidence", pending_names)
            self.assertIn("installed_macos_app_smoke", pending_names)
            self.assertIn("installed_app_runtime_workflow", pending_names)
            self.assertIn("bundled_katago_installed_app_smoke", pending_names)
            self.assertIn("installed_app_sgf_workflow", pending_names)
            self.assertIn("native_desktop_sgf_workflow", pending_names)
            self.assertIn("katago_live_smoke", pending_names)
            self.assertIn("katago_review_workflow_ux_smoke", pending_names)
            self.assertIn("legacy_config_corpus_migration_smoke", pending_names)
            self.assertIn("katago_live_desktop_workflow_smoke", pending_names)
            self.assertIn("installed_app_katago_live_workflow", pending_names)
            self.assertIn("readboard_live_smoke", pending_names)
            self.assertIn("readboard_image_import_smoke", pending_names)
            self.assertIn("readboard_image_ocr_corpus_smoke", pending_names)
            self.assertIn("readboard_external_capture_mvp", pending_names)
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

    def test_valid_desktop_sgf_editing_ux_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_desktop_sgf_editing_ux_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("desktop_sgf_editing_ux_smoke", pass_names)
            self.assertNotIn("desktop_sgf_editing_ux_smoke", pending_names)

    def test_desktop_sgf_editing_ux_evidence_requires_ui_surface_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_desktop_sgf_editing_ux_evidence()
            surface = evidence["uiUxSurface"]
            assert isinstance(surface, dict)
            surface["annotationEditorVisible"] = False
            write_json(root / smoke_user_flows.DESKTOP_SGF_EDITING_UX_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("desktop_sgf_editing_ux_smoke", failures)
            self.assertIn("desktop_sgf_editing_ux_smoke", pending)
            self.assertIn("uiUxSurface.annotationEditorVisible must be true", pending["desktop_sgf_editing_ux_smoke"])

    def test_desktop_sgf_editing_ux_evidence_requires_runtime_chain_coverage(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_desktop_sgf_editing_ux_evidence()
            coverage = evidence["coverage"]
            assert isinstance(coverage, dict)
            coverage["reorderVariation"] = False
            write_json(root / smoke_user_flows.DESKTOP_SGF_EDITING_UX_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("desktop_sgf_editing_ux_smoke", failures)
            self.assertIn("desktop_sgf_editing_ux_smoke", pending)
            self.assertIn("coverage.reorderVariation must be true", pending["desktop_sgf_editing_ux_smoke"])

    def test_desktop_sgf_editing_ux_evidence_keeps_native_dialog_boundary_false(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_desktop_sgf_editing_ux_evidence()
            surface = evidence["uiUxSurface"]
            boundaries = evidence["boundaries"]
            assert isinstance(surface, dict)
            assert isinstance(boundaries, dict)
            surface["nativeDialogClickCovered"] = True
            boundaries["fullNativeDialogProof"] = True
            write_json(root / smoke_user_flows.DESKTOP_SGF_EDITING_UX_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("desktop_sgf_editing_ux_smoke", failures)
            self.assertIn("desktop_sgf_editing_ux_smoke", pending)
            self.assertIn("uiUxSurface.nativeDialogClickCovered must be false", pending["desktop_sgf_editing_ux_smoke"])
            self.assertIn("boundaries.fullNativeDialogProof must be false", pending["desktop_sgf_editing_ux_smoke"])

    def test_desktop_sgf_editing_ux_evidence_declares_static_collection_method(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_desktop_sgf_editing_ux_evidence()
            evidence["collectionMethod"] = "runtime_dom_clicks"
            evidence["runtimeDomObserved"] = True
            evidence["screenshotObserved"] = True
            write_json(root / smoke_user_flows.DESKTOP_SGF_EDITING_UX_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("desktop_sgf_editing_ux_smoke", failures)
            self.assertIn("desktop_sgf_editing_ux_smoke", pending)
            self.assertIn("collectionMethod must be source_static_plus_tauri_runtime_chain", pending["desktop_sgf_editing_ux_smoke"])
            self.assertIn("runtimeDomObserved must be false", pending["desktop_sgf_editing_ux_smoke"])
            self.assertIn("screenshotObserved must be false", pending["desktop_sgf_editing_ux_smoke"])

    def test_valid_desktop_ui_click_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_desktop_ui_click_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("desktop_ui_click_smoke", pass_names)
            self.assertNotIn("desktop_ui_click_smoke", pending_names)
            self.assertIn("legacy_shell_menu_action_smoke", pass_names)
            self.assertNotIn("legacy_shell_menu_action_smoke", pending_names)

    def test_desktop_ui_click_evidence_requires_screenshots(self) -> None:
        self.assert_invalid_desktop_ui_click_evidence_pending(
            lambda evidence: evidence.__setitem__("screenshots", []),
            "screenshots must include at least two records",
        )

    def test_desktop_ui_click_evidence_rejects_native_dialog_claim(self) -> None:
        self.assert_invalid_desktop_ui_click_evidence_pending(
            lambda evidence: evidence["boundaries"].__setitem__("nativeFileDialogCovered", True),
            "boundaries.nativeFileDialogCovered must be false",
        )

    def test_desktop_ui_click_evidence_requires_browser_dom(self) -> None:
        self.assert_invalid_desktop_ui_click_evidence_pending(
            lambda evidence: evidence.__setitem__("browserDomObserved", False),
            "browserDomObserved must be true",
        )

    def test_desktop_ui_click_evidence_requires_clicked_controls(self) -> None:
        self.assert_invalid_desktop_ui_click_evidence_pending(
            lambda evidence: evidence.__setitem__("clickedControls", []),
            "clickedControls must include at least one control",
        )

    def test_desktop_ui_click_evidence_rejects_local_absolute_screenshot_paths(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            screenshots = evidence["screenshots"]
            assert isinstance(screenshots, list)
            first = screenshots[0]
            assert isinstance(first, dict)
            first["path"] = "/Users/haoc/Documents/lizzieyzy-next/docs/qa/screenshots/local.png"

        self.assert_invalid_desktop_ui_click_evidence_pending(
            mutate,
            "screenshots[0].path must not be a local absolute path",
        )

    def test_legacy_shell_menu_action_smoke_missing_section_is_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_desktop_ui_click_evidence()
            del evidence["legacyShellMenuActionSmoke"]
            write_json(root / smoke_user_flows.DESKTOP_UI_CLICK_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("legacy_shell_menu_action_smoke", failures)
            self.assertIn("legacy_shell_menu_action_smoke", pending)
            self.assertIn("legacyShellMenuActionSmoke section", pending["legacy_shell_menu_action_smoke"])

    def test_legacy_shell_menu_action_smoke_requires_clicked_actions(self) -> None:
        self.assert_invalid_legacy_shell_menu_action_evidence_pending(
            lambda section: section.__setitem__("clickedControls", []),
            "legacyShellMenuActionSmoke.clickedControls missing View:Candidates",
        )

    def test_legacy_shell_menu_action_smoke_requires_active_targets(self) -> None:
        self.assert_invalid_legacy_shell_menu_action_evidence_pending(
            lambda section: section.__setitem__("activeTargets", []),
            "legacyShellMenuActionSmoke.activeTargets missing candidates",
        )

    def test_legacy_shell_menu_action_smoke_rejects_boundary_overclaims(self) -> None:
        def mutate(section: dict[str, object]) -> None:
            boundaries = section["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["nativeFileDialogCovered"] = True
            boundaries["tauriWebviewDomObserved"] = True
            boundaries["fullLegacyParityCovered"] = True
            boundaries["osNativeMenuCovered"] = True
            boundaries["fullShortcutParityCovered"] = True
            boundaries["fullLayoutParityCovered"] = True

        self.assert_invalid_legacy_shell_menu_action_evidence_pending(
            mutate,
            "legacyShellMenuActionSmoke.boundaries.nativeFileDialogCovered must be false",
        )

    def test_legacy_shell_menu_action_smoke_requires_explicit_optional_boundary_fields(self) -> None:
        def mutate(section: dict[str, object]) -> None:
            boundaries = section["boundaries"]
            assert isinstance(boundaries, dict)
            del boundaries["osNativeMenuCovered"]
            del boundaries["fullShortcutParityCovered"]
            del boundaries["fullLayoutParityCovered"]

        self.assert_invalid_legacy_shell_menu_action_evidence_pending(
            mutate,
            "legacyShellMenuActionSmoke.boundaries.osNativeMenuCovered must be false",
        )

    def test_legacy_shell_menu_action_smoke_rejects_shortcut_layout_boundary_claims(self) -> None:
        def mutate(section: dict[str, object]) -> None:
            boundaries = section["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["fullShortcutParityCovered"] = True
            boundaries["fullLayoutParityCovered"] = True

        self.assert_invalid_legacy_shell_menu_action_evidence_pending(
            mutate,
            "legacyShellMenuActionSmoke.boundaries.fullShortcutParityCovered must be false",
        )

    def test_legacy_shell_menu_action_smoke_rejects_missing_visible_assertions(self) -> None:
        self.assert_invalid_legacy_shell_menu_action_evidence_pending(
            lambda section: section.__setitem__("visibleAssertions", []),
            "legacyShellMenuActionSmoke.visibleAssertions missing View:Candidates target",
        )

    def assert_invalid_desktop_ui_click_evidence_pending(self, mutate_evidence, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_desktop_ui_click_evidence()
            mutate_evidence(evidence)
            write_json(root / smoke_user_flows.DESKTOP_UI_CLICK_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("desktop_ui_click_smoke", failures)
            self.assertIn("desktop_ui_click_smoke", pending)
            self.assertIn(expected_detail, pending["desktop_ui_click_smoke"])

    def assert_invalid_legacy_shell_menu_action_evidence_pending(self, mutate_section, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_desktop_ui_click_evidence()
            section = evidence["legacyShellMenuActionSmoke"]
            assert isinstance(section, dict)
            mutate_section(section)
            write_json(root / smoke_user_flows.DESKTOP_UI_CLICK_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("legacy_shell_menu_action_smoke", failures)
            self.assertIn("legacy_shell_menu_action_smoke", pending)
            self.assertIn(expected_detail, pending["legacy_shell_menu_action_smoke"])

    def test_valid_tauri_window_runtime_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_tauri_window_runtime_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("tauri_window_runtime_smoke", pass_names)
            self.assertNotIn("tauri_window_runtime_smoke", pending_names)

    def test_tauri_window_runtime_evidence_requires_screenshot(self) -> None:
        self.assert_invalid_tauri_window_runtime_evidence_pending(
            lambda evidence: evidence.__setitem__("screenshots", []),
            "screenshots must include at least one Tauri window screenshot",
        )

    def test_tauri_window_runtime_evidence_rejects_local_absolute_screenshot_path(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            screenshots = evidence["screenshots"]
            assert isinstance(screenshots, list)
            first = screenshots[0]
            assert isinstance(first, dict)
            first["path"] = "/tmp/tauri-window-runtime.png"

        self.assert_invalid_tauri_window_runtime_evidence_pending(
            mutate,
            "screenshots[0].path must not be a local absolute path",
        )

    def test_tauri_window_runtime_evidence_rejects_native_dialog_claim(self) -> None:
        self.assert_invalid_tauri_window_runtime_evidence_pending(
            lambda evidence: evidence.__setitem__("nativeDialogClickCovered", True),
            "nativeDialogClickCovered must be false",
        )

    def test_tauri_window_runtime_evidence_rejects_browser_fallback(self) -> None:
        self.assert_invalid_tauri_window_runtime_evidence_pending(
            lambda evidence: evidence.__setitem__("browserFallbackUsed", True),
            "browserFallbackUsed must be false",
        )

    def test_tauri_window_runtime_evidence_rejects_webview_dom_click_claim(self) -> None:
        self.assert_invalid_tauri_window_runtime_evidence_pending(
            lambda evidence: evidence.__setitem__("webviewDomClickCovered", True),
            "webviewDomClickCovered must be false",
        )

    def test_tauri_window_runtime_evidence_rejects_boundary_misclaims(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["browserFallbackUsed"] = True
            boundaries["webviewDomClickCovered"] = True
            boundaries["nativeDialogClickCovered"] = True

        self.assert_invalid_tauri_window_runtime_evidence_pending(
            mutate,
            "boundaries.browserFallbackUsed must be false",
        )

    def assert_invalid_tauri_window_runtime_evidence_pending(self, mutate_evidence, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_tauri_window_runtime_evidence()
            mutate_evidence(evidence)
            write_json(root / smoke_user_flows.TAURI_WINDOW_RUNTIME_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("tauri_window_runtime_smoke", failures)
        self.assertIn("tauri_window_runtime_smoke", pending)
        self.assertIn(expected_detail, pending["tauri_window_runtime_smoke"])

    def test_valid_tauri_webview_dom_click_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_tauri_webview_dom_click_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("tauri_webview_dom_click_smoke", pass_names)
            self.assertNotIn("tauri_webview_dom_click_smoke", pending_names)

    def test_tauri_webview_dom_click_evidence_requires_required_check(self) -> None:
        self.assert_invalid_tauri_webview_dom_click_evidence_pending(
            lambda evidence: evidence.__setitem__(
                "checks",
                [check for check in evidence["checks"] if check["name"] != "webview_dom_observed"],
            ),
            "missing required checks: webview_dom_observed",
        )

    def test_tauri_webview_dom_click_evidence_rejects_browser_fallback(self) -> None:
        self.assert_invalid_tauri_webview_dom_click_evidence_pending(
            lambda evidence: evidence.__setitem__("browserFallbackUsed", True),
            "browserFallbackUsed must be false",
        )

    def test_tauri_webview_dom_click_evidence_requires_at_least_four_clicks(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["clickedControls"] = evidence["clickedControls"][:3]
            click_check = find_evidence_check(evidence, "webview_click_observed")["details"]
            click_check["clickedControls"] = click_check["clickedControls"][:3]

        self.assert_invalid_tauri_webview_dom_click_evidence_pending(
            mutate,
            "clickedControls must include at least four controls",
        )

    def test_tauri_webview_dom_click_evidence_rejects_overclaim_true(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["fullLayoutParity"] = True
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["fullShortcutParity"] = True

        self.assert_invalid_tauri_webview_dom_click_evidence_pending(
            mutate,
            "fullLayoutParity must be false",
        )

    def assert_invalid_tauri_webview_dom_click_evidence_pending(self, mutate_evidence, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_tauri_webview_dom_click_evidence()
            mutate_evidence(evidence)
            write_json(root / smoke_user_flows.TAURI_WEBVIEW_DOM_CLICK_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("tauri_webview_dom_click_smoke", failures)
            self.assertIn("tauri_webview_dom_click_smoke", pending)
            self.assertIn(expected_detail, pending["tauri_webview_dom_click_smoke"])

    def test_valid_legacy_layout_parity_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_legacy_layout_parity_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("legacy_layout_parity_smoke", pass_names)
            self.assertNotIn("legacy_layout_parity_smoke", pending_names)

    def test_runner_shaped_legacy_layout_parity_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_json(
                root / smoke_user_flows.LEGACY_LAYOUT_PARITY_SMOKE_EVIDENCE,
                runner_shaped_legacy_layout_parity_evidence(),
            )

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("legacy_layout_parity_smoke", pass_names)
            self.assertNotIn("legacy_layout_parity_smoke", pending_names)

    def test_valid_legacy_shortcut_layout_evidence_passes_optional_runtime_gate(self) -> None:
        failures = smoke_user_flows.validate_legacy_shortcut_layout_evidence(valid_legacy_shortcut_layout_evidence())
        self.assertEqual([], failures)

    def test_runner_shaped_legacy_shortcut_layout_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_legacy_layout_parity_evidence(root)
            write_json(root / smoke_user_flows.LEGACY_SHORTCUT_LAYOUT_EVIDENCE, runner_shaped_legacy_shortcut_layout_evidence())

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("legacy_shortcut_layout_evidence", pass_names)
            self.assertNotIn("legacy_shortcut_layout_evidence", pending_names)

    def test_legacy_shortcut_layout_current_static_summary_shape_is_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_json(root / smoke_user_flows.LEGACY_SHORTCUT_LAYOUT_EVIDENCE, static_only_legacy_shortcut_layout_evidence())

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("legacy_shortcut_layout_evidence", failures)
            self.assertIn("legacy_shortcut_layout_evidence", pending)
            self.assertIn("runtimeObserved must be true", pending["legacy_shortcut_layout_evidence"])
            self.assertIn("evidence must not be static-source-only", pending["legacy_shortcut_layout_evidence"])

    def test_legacy_layout_parity_requires_required_screenshots(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            screenshots = evidence["screenshots"]
            assert isinstance(screenshots, list)
            evidence["screenshots"] = screenshots[:-1]

        self.assert_invalid_legacy_layout_parity_pending(
            mutate,
            "screenshots missing engine/preferences",
        )

    def test_legacy_shortcut_layout_requires_runtime_observed(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["runtimeObserved"] = False
            evidence["sourceStaticOnly"] = True
            evidence["collectionMethod"] = "source_static_only"

        self.assert_invalid_legacy_shortcut_layout_pending(
            mutate,
            "runtimeObserved must be true",
        )

    def test_legacy_shortcut_layout_requires_action_matrix_shortcuts(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["shortcutObservedCount"] = 3
            matrix = evidence["actionMatrix"]
            assert isinstance(matrix, list)
            first = matrix[0]
            assert isinstance(first, dict)
            first.pop("shortcut", None)

        self.assert_invalid_legacy_shortcut_layout_pending(
            mutate,
            "shortcutObservedCount must be at least 4",
        )

    def test_legacy_shortcut_layout_requires_input_editing_safety(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            matrix = evidence["actionMatrix"]
            assert isinstance(matrix, list)
            first = matrix[0]
            assert isinstance(first, dict)
            first["inputEditingBehavior"] = {"inputEditingSafe": False, "triggeredWhileEditing": True}

        self.assert_invalid_legacy_shortcut_layout_pending(
            mutate,
            "actionMatrix[0].inputEditingBehavior must prove input editing safety",
        )

    def test_legacy_shortcut_layout_requires_screenshot_runtime_fields(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            screenshots = evidence["screenshots"]
            assert isinstance(screenshots, list)
            first = screenshots[0]
            assert isinstance(first, dict)
            first.pop("capturedAfterActionId", None)
            first.pop("source", None)

        self.assert_invalid_legacy_shortcut_layout_pending(
            mutate,
            "screenshots[0].source must be non-empty",
        )

    def test_legacy_layout_parity_rejects_local_absolute_screenshot_path(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            screenshots = evidence["screenshots"]
            assert isinstance(screenshots, list)
            first = screenshots[0]
            assert isinstance(first, dict)
            first["path"] = "/Users/haoc/layout-default.png"

        self.assert_invalid_legacy_layout_parity_pending(
            mutate,
            "screenshots[0].path must not be a local absolute path",
        )

    def test_legacy_layout_parity_requires_three_viewports(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["viewports"] = [{"width": 1280, "height": 840}, {"width": 900, "height": 840}]
            screenshots = evidence["screenshots"]
            assert isinstance(screenshots, list)
            for screenshot in screenshots:
                assert isinstance(screenshot, dict)
                screenshot.pop("viewport", None)

        self.assert_invalid_legacy_layout_parity_pending(
            mutate,
            "viewports must include at least three sizes",
        )

    def test_legacy_layout_parity_requires_visible_targets(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            assertions = evidence["visibleAssertions"]
            assert isinstance(assertions, list)
            evidence["visibleAssertions"] = [assertion for assertion in assertions if "provider" not in str(assertion).lower()]

        self.assert_invalid_legacy_layout_parity_pending(
            mutate,
            "visibleAssertions missing provider/readboard",
        )

    def test_legacy_layout_parity_rejects_critical_overlap(self) -> None:
        self.assert_invalid_legacy_layout_parity_pending(
            lambda evidence: evidence.__setitem__("criticalOverlapDetected", True),
            "criticalOverlapDetected must not be true",
        )

    def test_legacy_layout_parity_rejects_overclaim_true(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["fullLegacyUiParity"] = True
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["pixelPerfectParity"] = True

        self.assert_invalid_legacy_layout_parity_pending(
            mutate,
            "fullLegacyUiParity must be false",
        )

    def test_legacy_shortcut_layout_rejects_overclaim_true(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["fullLegacyParity"] = True
            evidence["fullShortcutParity"] = True
            evidence["fullLayoutParity"] = True
            evidence["pixelPerfectLayoutParity"] = True
            evidence["osNativeMenuParity"] = True
            evidence["nativeDialogParity"] = True
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["fullLayoutParity"] = True
            boundaries["nativeDialogParity"] = True

        self.assert_invalid_legacy_shortcut_layout_pending(
            mutate,
            "fullLegacyParity must be false",
        )

    def assert_invalid_legacy_layout_parity_pending(self, mutate_evidence, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_legacy_layout_parity_evidence()
            mutate_evidence(evidence)
            write_json(root / smoke_user_flows.LEGACY_LAYOUT_PARITY_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("legacy_layout_parity_smoke", failures)
            self.assertIn("legacy_layout_parity_smoke", pending)
            self.assertIn(expected_detail, pending["legacy_layout_parity_smoke"])

    def assert_invalid_legacy_shortcut_layout_pending(self, mutate_evidence, expected_detail: str) -> None:
        evidence = valid_legacy_shortcut_layout_evidence()
        mutate_evidence(evidence)
        failures = smoke_user_flows.validate_legacy_shortcut_layout_evidence(evidence)
        self.assertIn(expected_detail, "; ".join(failures))

    def test_valid_installed_macos_app_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_installed_macos_app_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("installed_macos_app_smoke", pass_names)
            self.assertNotIn("installed_macos_app_smoke", pending_names)

    def test_installed_macos_app_evidence_requires_screenshot(self) -> None:
        self.assert_invalid_installed_macos_app_evidence_pending(
            lambda evidence: evidence.__setitem__("screenshots", []),
            "screenshots must include at least one installed app screenshot",
        )

    def test_installed_macos_app_evidence_rejects_local_absolute_screenshot_path(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            screenshots = evidence["screenshots"]
            assert isinstance(screenshots, list)
            first = screenshots[0]
            assert isinstance(first, dict)
            first["path"] = "/Users/haoc/Documents/lizzieyzy-next/docs/qa/screenshots/installed.png"

        self.assert_invalid_installed_macos_app_evidence_pending(
            mutate,
            "screenshots[0].path must not be a local absolute path",
        )

    def test_installed_macos_app_evidence_rejects_local_absolute_bundle_paths(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["appBundlePath"] = "/Users/haoc/Documents/lizzieyzy-next/target/release/bundle/macos/LizzieYzy.app"
            app_bundle = evidence["appBundle"]
            bundle = evidence["bundle"]
            assert isinstance(app_bundle, dict)
            assert isinstance(bundle, dict)
            app_bundle["path"] = "/tmp/LizzieYzy.app"
            for key in ("app", "binary", "dmg", "infoPlist"):
                artifact = bundle[key]
                assert isinstance(artifact, dict)
                artifact["path"] = f"/Users/haoc/{key}"
            dmgs = bundle["dmgs"]
            assert isinstance(dmgs, list)
            first_dmg = dmgs[0]
            assert isinstance(first_dmg, dict)
            first_dmg["path"] = "/private/tmp/LizzieYzy.dmg"

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_installed_macos_app_evidence()
            mutate(evidence)
            write_json(root / smoke_user_flows.INSTALLED_MACOS_APP_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("installed_macos_app_smoke", failures)
            self.assertIn("installed_macos_app_smoke", pending)
            self.assertIn("appBundlePath must not be a local absolute path", pending["installed_macos_app_smoke"])
            self.assertIn("appBundle.path must not be a local absolute path", pending["installed_macos_app_smoke"])
            self.assertIn("bundle.app.path must not be a local absolute path", pending["installed_macos_app_smoke"])
            self.assertIn("bundle.binary.path must not be a local absolute path", pending["installed_macos_app_smoke"])
            self.assertIn("bundle.dmg.path must not be a local absolute path", pending["installed_macos_app_smoke"])
            self.assertIn("bundle.infoPlist.path must not be a local absolute path", pending["installed_macos_app_smoke"])
            self.assertIn("bundle.dmgs[0].path must not be a local absolute path", pending["installed_macos_app_smoke"])

    def test_installed_macos_app_evidence_requires_dev_server_absent(self) -> None:
        self.assert_invalid_installed_macos_app_evidence_pending(
            lambda evidence: evidence.__setitem__("devServerAbsent", False),
            "devServerAbsent must be true",
        )

    def test_installed_macos_app_evidence_rejects_dev_server_preflight_contradiction(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            preflight = evidence["devServerPreflight"]
            boundaries = evidence["boundaries"]
            assert isinstance(preflight, dict)
            assert isinstance(boundaries, dict)
            preflight["reachableBeforeLaunch"] = True
            preflight["runnerStartedDevServer"] = True
            evidence["runnerStartedDevServer"] = True
            evidence["runnerStartedViteDevServer"] = True
            boundaries["viteDevServerStarted"] = True

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_installed_macos_app_evidence()
            mutate(evidence)
            write_json(root / smoke_user_flows.INSTALLED_MACOS_APP_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("installed_macos_app_smoke", failures)
            self.assertIn("installed_macos_app_smoke", pending)
            self.assertIn("devServerPreflight.reachableBeforeLaunch must be false", pending["installed_macos_app_smoke"])
            self.assertIn("devServerPreflight.runnerStartedDevServer must be false", pending["installed_macos_app_smoke"])
            self.assertIn("runnerStartedDevServer must be false", pending["installed_macos_app_smoke"])
            self.assertIn("runnerStartedViteDevServer must be false", pending["installed_macos_app_smoke"])
            self.assertIn("boundaries.viteDevServerStarted must be false", pending["installed_macos_app_smoke"])

    def test_installed_macos_app_evidence_rejects_release_claims(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["productionSigned"] = True
            evidence["notarized"] = True
            evidence["releasePublished"] = True

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_installed_macos_app_evidence()
            mutate(evidence)
            write_json(root / smoke_user_flows.INSTALLED_MACOS_APP_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("installed_macos_app_smoke", failures)
            self.assertIn("installed_macos_app_smoke", pending)
            self.assertIn("productionSigned must be false", pending["installed_macos_app_smoke"])
            self.assertIn("notarized must be false", pending["installed_macos_app_smoke"])
            self.assertIn("releasePublished must be false", pending["installed_macos_app_smoke"])

    def test_installed_macos_app_evidence_rejects_native_dialog_and_webview_boundary_claims(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["nativeDialogClickCovered"] = True
            boundaries["webviewDomClickCovered"] = True

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_installed_macos_app_evidence()
            mutate(evidence)
            write_json(root / smoke_user_flows.INSTALLED_MACOS_APP_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("installed_macos_app_smoke", failures)
            self.assertIn("installed_macos_app_smoke", pending)
            self.assertIn("boundaries.nativeDialogClickCovered must be false", pending["installed_macos_app_smoke"])
            self.assertIn("boundaries.webviewDomClickCovered must be false", pending["installed_macos_app_smoke"])

    def test_installed_macos_app_evidence_requires_launch_and_window(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["launched"] = False
            evidence["windowObserved"] = False

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_installed_macos_app_evidence()
            mutate(evidence)
            write_json(root / smoke_user_flows.INSTALLED_MACOS_APP_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("installed_macos_app_smoke", failures)
            self.assertIn("installed_macos_app_smoke", pending)
            self.assertIn("launched must be true", pending["installed_macos_app_smoke"])
            self.assertIn("windowObserved must be true", pending["installed_macos_app_smoke"])

    def test_valid_installed_app_runtime_workflow_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_installed_app_runtime_workflow_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("installed_app_runtime_workflow", pass_names)
            self.assertNotIn("installed_app_runtime_workflow", pending_names)

    def test_installed_app_runtime_workflow_rejects_static_only_or_artifact_only(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["collectionMethod"] = "static_source_only"
            evidence["sourceStaticOnly"] = True
            evidence["artifactOnly"] = True
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["sourceStaticOnly"] = True
            boundaries["artifactOnly"] = True

        self.assert_invalid_installed_app_runtime_workflow_pending(
            mutate,
            "collectionMethod must not be static-only",
        )
        evidence = valid_installed_app_runtime_workflow_evidence()
        mutate(evidence)
        failures = smoke_user_flows.validate_installed_app_runtime_workflow_evidence(evidence)
        detail = "; ".join(failures)
        self.assertIn("sourceStaticOnly must be false", detail)
        self.assertIn("artifactOnly must be false", detail)

        artifact_only = valid_installed_app_runtime_workflow_evidence()
        artifact_only["collectionMethod"] = "artifact_only"
        failures = smoke_user_flows.validate_installed_app_runtime_workflow_evidence(artifact_only)
        self.assertIn("collectionMethod must not be artifact-only", "; ".join(failures))

    def test_installed_app_runtime_workflow_requires_required_checks(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["checks"] = [
                check
                for check in evidence["checks"]
                if isinstance(check, dict) and check.get("name") != "workflow_action_executed"
            ]

        self.assert_invalid_installed_app_runtime_workflow_pending(
            mutate,
            "missing required checks: workflow_action_executed",
        )

    def test_installed_app_runtime_workflow_requires_backend_runtime_proof(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence.pop("backendRuntimeProof")

        self.assert_invalid_installed_app_runtime_workflow_pending(
            mutate,
            "backendRuntimeProof must be an object",
        )

    def test_installed_app_runtime_workflow_rejects_fake_runtime_action(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            actions = evidence["workflowActions"]
            assert isinstance(actions, list)
            action = next(item for item in actions if isinstance(item, dict) and item.get("actionId") == "execute_runtime_action")
            action["evidence"] = {"action": "focus-board-and-confirm-runtime-state", "boardVisible": True}

        self.assert_invalid_installed_app_runtime_workflow_pending(
            mutate,
            "workflowActions execute_runtime_action must cite installed_app_runtime_proof backend command",
        )

    def test_installed_app_runtime_workflow_rejects_assets_missing_marked_ready(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            proof = evidence["backendRuntimeProof"]
            assert isinstance(proof, dict)
            assets = proof["assets"]
            assert isinstance(assets, dict)
            assets["status"] = "ready"
            assets["missing"] = [{"label": "resource-dir"}]

        self.assert_invalid_installed_app_runtime_workflow_pending(
            mutate,
            "backendRuntimeProof.assets must not be ready when missing/placeholders are present",
        )

    def test_installed_app_runtime_workflow_rejects_engine_unavailable_counted_success(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            proof = evidence["backendRuntimeProof"]
            assert isinstance(proof, dict)
            launch = proof["engineLaunchAttempt"]
            assert isinstance(launch, dict)
            launch["status"] = "unavailable"
            launch["success"] = True

        self.assert_invalid_installed_app_runtime_workflow_pending(
            mutate,
            "backendRuntimeProof.engineLaunchAttempt unavailable/problem status must not be counted as success",
        )

    def test_installed_app_runtime_workflow_requires_runtime_action(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["workflowActions"] = [
                action
                for action in evidence["workflowActions"]
                if isinstance(action, dict) and action.get("actionId") != "execute_runtime_action"
            ]

        self.assert_invalid_installed_app_runtime_workflow_pending(
            mutate,
            "workflowActions missing: execute_runtime_action",
        )

    def test_installed_app_runtime_workflow_rejects_overclaim_boundaries(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            for key in (
                "productionSigned",
                "notarized",
                "updaterReady",
                "windowsInstalledAppCovered",
                "linuxInstalledAppCovered",
                "fullLegacyParity",
            ):
                evidence[key] = True
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            for key in (
                "productionSigned",
                "notarized",
                "updaterReady",
                "windowsInstalledAppCovered",
                "linuxInstalledAppCovered",
                "fullLegacyParity",
            ):
                boundaries[key] = True

        self.assert_invalid_installed_app_runtime_workflow_pending(
            mutate,
            "productionSigned must be false",
        )

    def test_installed_app_runtime_workflow_rejects_browser_fallback_and_dev_server(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["browserFallbackUsed"] = True
            evidence["runnerStartedDevServer"] = True
            preflight = evidence["devServerPreflight"]
            assert isinstance(preflight, dict)
            preflight["reachableBeforeLaunch"] = True

        self.assert_invalid_installed_app_runtime_workflow_pending(
            mutate,
            "browserFallbackUsed must be false",
        )

    def test_valid_bundled_katago_installed_app_smoke_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_json(
                root / smoke_user_flows.BUNDLED_KATAGO_INSTALLED_APP_SMOKE_EVIDENCE,
                valid_bundled_katago_installed_app_smoke_evidence(),
            )

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("bundled_katago_installed_app_smoke", pass_names)
            self.assertNotIn("bundled_katago_installed_app_smoke", pending_names)

    def test_bundled_katago_installed_app_smoke_rejects_unavailable_counted_success(self) -> None:
        self.assert_invalid_bundled_katago_installed_app_pending(
            lambda evidence: evidence["engineLaunchAttempt"].__setitem__("launchSucceeded", True),
            "engineLaunchAttempt unavailable/problem status must not be counted as success",
        )

    def test_bundled_katago_installed_app_smoke_rejects_overclaim(self) -> None:
        self.assert_invalid_bundled_katago_installed_app_pending(
            lambda evidence: evidence["boundaries"].__setitem__("fullBundledKataGoParity", True),
            "boundaries.fullBundledKataGoParity must be false",
        )

    def test_bundled_katago_installed_app_smoke_rejects_dev_server_source(self) -> None:
        self.assert_invalid_bundled_katago_installed_app_pending(
            lambda evidence: evidence["runtimeSource"].__setitem__("sourceKind", "tauri-dev"),
            "runtimeSource.sourceKind must be packaged-macos-app",
        )

    def test_bundled_katago_installed_app_smoke_rejects_ready_with_missing_assets(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            layout = evidence["bundledAssetLayout"]
            assert isinstance(layout, dict)
            layout["status"] = "ready"
            layout["missing"] = [{"label": "KataGo model"}]

        self.assert_invalid_bundled_katago_installed_app_pending(
            mutate,
            "bundledAssetLayout must not be ready when missing/placeholders are present",
        )

    def test_bundled_katago_installed_app_smoke_rejects_missing_bundled_katago_backend_proof(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence.pop("bundledKataGo")
            proof = evidence["backendRuntimeProof"]
            assert isinstance(proof, dict)
            proof.pop("bundledKataGo")
            proof.pop("bundledKatago", None)
            proof.pop("bundled_katago", None)

        self.assert_invalid_bundled_katago_installed_app_pending(
            mutate,
            "backendRuntimeProof.bundledKatago must be recorded",
        )

    def test_bundled_katago_installed_app_smoke_accepts_rust_bundled_katago_key(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_bundled_katago_installed_app_smoke_evidence()
            proof = evidence["backendRuntimeProof"]
            assert isinstance(proof, dict)
            proof["bundledKatago"] = proof.pop("bundledKataGo")
            write_json(root / smoke_user_flows.BUNDLED_KATAGO_INSTALLED_APP_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("bundled_katago_installed_app_smoke", pass_names)

    def assert_invalid_bundled_katago_installed_app_pending(self, mutate_evidence, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_bundled_katago_installed_app_smoke_evidence()
            mutate_evidence(evidence)
            write_json(root / smoke_user_flows.BUNDLED_KATAGO_INSTALLED_APP_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("bundled_katago_installed_app_smoke", failures)
            self.assertIn("bundled_katago_installed_app_smoke", pending)
            self.assertIn(expected_detail, pending["bundled_katago_installed_app_smoke"])

    def test_valid_installed_app_sgf_workflow_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_installed_app_sgf_workflow_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("installed_app_sgf_workflow", pass_names)
            self.assertNotIn("installed_app_sgf_workflow", pending_names)

    def test_installed_app_sgf_workflow_requires_runtime_report(self) -> None:
        self.assert_invalid_installed_app_sgf_workflow_pending(
            lambda evidence: evidence.pop("sourceRuntimeReport"),
            "sourceRuntimeReport must be an object",
        )

    def test_installed_app_sgf_workflow_rejects_wrong_runtime_phase(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            report = evidence["sourceRuntimeReport"]
            assert isinstance(report, dict)
            report["phase"] = "edit-save"

        self.assert_invalid_installed_app_sgf_workflow_pending(
            mutate,
            "sourceRuntimeReport.phase must be installed-app-sgf-workflow",
        )

    def test_installed_app_sgf_workflow_rejects_tauri_dev_two_launch_trace(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            report = evidence["sourceRuntimeReport"]
            assert isinstance(report, dict)
            report["firstLaunch"] = {"phase": "edit-save", "stopped": True}
            report["logPath"] = "/tmp/tauri-dev.log"

        self.assert_invalid_installed_app_sgf_workflow_pending(
            mutate,
            "sourceRuntimeReport must not include firstLaunch tauri-dev two-launch evidence",
        )

    def test_installed_app_sgf_workflow_requires_backend_runtime_proof_check(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            report = evidence["sourceRuntimeReport"]
            assert isinstance(report, dict)
            checks = report["checks"]
            assert isinstance(checks, list)
            checks[:] = [
                check
                for check in checks
                if isinstance(check, dict) and check.get("name") != "backend_runtime_proof_observed"
            ]

        self.assert_invalid_installed_app_sgf_workflow_pending(
            mutate,
            "sourceRuntimeReport missing backend_runtime_proof_observed check",
        )

    def test_installed_app_sgf_workflow_requires_screenshot_hash(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            screenshots = evidence["screenshots"]
            assert isinstance(screenshots, list)
            first = screenshots[0]
            assert isinstance(first, dict)
            first["sha256"] = "not-a-hash"

        self.assert_invalid_installed_app_sgf_workflow_pending(
            mutate,
            "screenshots[0].sha256 must be a 64-character hex sha256",
        )

    def test_installed_app_sgf_workflow_requires_installed_app_phase(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            report = evidence["sourceRuntimeReport"]
            assert isinstance(report, dict)
            report["phase"] = "edit-save"

        self.assert_invalid_installed_app_sgf_workflow_pending(
            mutate,
            "sourceRuntimeReport.phase must be installed-app-sgf-workflow",
        )

    def test_installed_app_sgf_workflow_rejects_tauri_dev_traces(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            report = evidence["sourceRuntimeReport"]
            assert isinstance(report, dict)
            report["logPath"] = "<tmp>/tauri-dev-a.log"

        self.assert_invalid_installed_app_sgf_workflow_pending(
            mutate,
            "sourceRuntimeReport must not include logPath dev-server evidence",
        )

    def test_installed_app_sgf_workflow_rejects_tauri_dev_backend_source(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            report = evidence["sourceRuntimeReport"]
            assert isinstance(report, dict)
            checks = report["checks"]
            assert isinstance(checks, list)
            backend = next(check for check in checks if isinstance(check, dict) and check.get("name") == "backend_runtime_proof_observed")
            details = backend["details"]
            assert isinstance(details, dict)
            raw = details["raw"]
            assert isinstance(raw, dict)
            runtime = raw["runtime"]
            assert isinstance(runtime, dict)
            runtime["source"] = "tauri-dev"

        self.assert_invalid_installed_app_sgf_workflow_pending(
            mutate,
            "sourceRuntimeReport.backend_runtime_proof_observed backendRuntimeProof.runtime.source must be packaged-macos-app",
        )

    def test_installed_app_sgf_workflow_rejects_overclaims(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["fullSgfWorkflowParity"] = True
            evidence["releaseParity"] = True
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["fullSgfWorkflowParity"] = True
            boundaries["releaseParity"] = True

        self.assert_invalid_installed_app_sgf_workflow_pending(
            mutate,
            "fullSgfWorkflowParity must be false",
        )

    def test_installed_app_sgf_workflow_rejects_missing_reopen_invariant(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            checks = evidence["checks"]
            assert isinstance(checks, list)
            checks[:] = [
                check
                for check in checks
                if isinstance(check, dict) and check.get("name") != "final_invariant_verified"
            ]

        self.assert_invalid_installed_app_sgf_workflow_pending(
            mutate,
            "missing required checks: final_invariant_verified",
        )

    def assert_invalid_installed_macos_app_evidence_pending(self, mutate_evidence, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_installed_macos_app_evidence()
            mutate_evidence(evidence)
            write_json(root / smoke_user_flows.INSTALLED_MACOS_APP_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("installed_macos_app_smoke", failures)
            self.assertIn("installed_macos_app_smoke", pending)
            self.assertIn(expected_detail, pending["installed_macos_app_smoke"])

    def assert_invalid_installed_app_runtime_workflow_pending(self, mutate_evidence, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_installed_app_runtime_workflow_evidence()
            mutate_evidence(evidence)
            write_json(root / smoke_user_flows.INSTALLED_APP_RUNTIME_WORKFLOW_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("installed_app_runtime_workflow", failures)
            self.assertIn("installed_app_runtime_workflow", pending)
            self.assertIn(expected_detail, pending["installed_app_runtime_workflow"])

    def assert_invalid_installed_app_sgf_workflow_pending(self, mutate_evidence, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_installed_app_sgf_workflow_evidence()
            mutate_evidence(evidence)
            write_json(root / smoke_user_flows.INSTALLED_APP_SGF_WORKFLOW_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("installed_app_sgf_workflow", failures)
            self.assertIn("installed_app_sgf_workflow", pending)
            self.assertIn(expected_detail, pending["installed_app_sgf_workflow"])

    def test_valid_native_desktop_sgf_workflow_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_native_desktop_sgf_workflow_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("native_desktop_sgf_workflow", pass_names)
            self.assertNotIn("native_desktop_sgf_workflow", pending_names)

    def test_native_desktop_sgf_workflow_accepts_string_operator_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_native_desktop_sgf_workflow_evidence()
            for check_name in ("native_open_dialog", "save_or_save_as"):
                details = find_evidence_check(evidence, check_name)["details"]
                assert isinstance(details, dict)
                details["operator"] = "qa-worker"
            write_json(root / smoke_user_flows.NATIVE_DESKTOP_SGF_WORKFLOW_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("native_desktop_sgf_workflow", pass_names)
            self.assertNotIn("native_desktop_sgf_workflow", pending_names)

    def test_native_desktop_sgf_workflow_rejects_full_automation_with_manual_steps(self) -> None:
        self.assert_invalid_native_desktop_sgf_workflow_pending(
            lambda evidence: evidence.__setitem__("fullAutomationCovered", True),
            "fullAutomationCovered must be false when manual-assisted steps are present",
        )

    def test_native_desktop_sgf_workflow_requires_native_dialog_coverage(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["nativeDialogOpenCovered"] = False
            evidence["nativeDialogSaveCovered"] = False

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_native_desktop_sgf_workflow_evidence()
            mutate(evidence)
            write_json(root / smoke_user_flows.NATIVE_DESKTOP_SGF_WORKFLOW_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("native_desktop_sgf_workflow", failures)
            self.assertIn("native_desktop_sgf_workflow", pending)
            self.assertIn("nativeDialogOpenCovered must be true", pending["native_desktop_sgf_workflow"])
            self.assertIn("nativeDialogSaveCovered must be true", pending["native_desktop_sgf_workflow"])

    def test_native_desktop_sgf_workflow_rejects_release_and_parity_claims(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["fullLegacyParityCovered"] = True
            evidence["productionSigned"] = True
            evidence["notarized"] = True
            evidence["releasePublished"] = True

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_native_desktop_sgf_workflow_evidence()
            mutate(evidence)
            write_json(root / smoke_user_flows.NATIVE_DESKTOP_SGF_WORKFLOW_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("native_desktop_sgf_workflow", failures)
            self.assertIn("native_desktop_sgf_workflow", pending)
            self.assertIn("fullLegacyParityCovered must be false", pending["native_desktop_sgf_workflow"])
            self.assertIn("productionSigned must be false", pending["native_desktop_sgf_workflow"])
            self.assertIn("notarized must be false", pending["native_desktop_sgf_workflow"])
            self.assertIn("releasePublished must be false", pending["native_desktop_sgf_workflow"])

    def test_native_desktop_sgf_workflow_rejects_native_dialog_without_metadata(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            checks = evidence["checks"]
            assert isinstance(checks, list)
            open_check = next(check for check in checks if isinstance(check, dict) and check.get("name") == "native_open_dialog")
            assert isinstance(open_check, dict)
            open_check["details"] = {"method": "", "openedSgfPath": "", "screenshotPath": ""}

        self.assert_invalid_native_desktop_sgf_workflow_pending(
            mutate,
            "native_open_dialog must include operator metadata",
        )

    def test_native_desktop_sgf_workflow_rejects_save_dialog_without_metadata(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            checks = evidence["checks"]
            assert isinstance(checks, list)
            save_check = next(check for check in checks if isinstance(check, dict) and check.get("name") == "save_or_save_as")
            assert isinstance(save_check, dict)
            save_check["details"] = {"operator": "", "method": "", "savedSgfPath": "", "screenshotPath": ""}

        self.assert_invalid_native_desktop_sgf_workflow_pending(
            mutate,
            "save_or_save_as must include SGF path metadata",
        )

    def test_native_desktop_sgf_workflow_rejects_webview_dom_claim(self) -> None:
        self.assert_invalid_native_desktop_sgf_workflow_pending(
            lambda evidence: evidence.__setitem__("webviewDomAutomationCovered", True),
            "webviewDomAutomationCovered must be false for this scoped batch",
        )

    def test_native_desktop_sgf_workflow_rejects_boundary_scope_claims(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["windowsInstalledAppCovered"] = True
            boundaries["linuxInstalledAppCovered"] = True
            boundaries["ocrCaptureCovered"] = True
            boundaries["externalClientCaptureCovered"] = True
            boundaries["providerParityCovered"] = True
            boundaries["readboardParityCovered"] = True
            boundaries["webviewDomAutomationCovered"] = True

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_native_desktop_sgf_workflow_evidence()
            mutate(evidence)
            write_json(root / smoke_user_flows.NATIVE_DESKTOP_SGF_WORKFLOW_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("native_desktop_sgf_workflow", failures)
            self.assertIn("native_desktop_sgf_workflow", pending)
            self.assertIn("boundaries.windowsInstalledAppCovered must be false", pending["native_desktop_sgf_workflow"])
            self.assertIn("boundaries.linuxInstalledAppCovered must be false", pending["native_desktop_sgf_workflow"])
            self.assertIn("boundaries.ocrCaptureCovered must be false", pending["native_desktop_sgf_workflow"])
            self.assertIn("boundaries.externalClientCaptureCovered must be false", pending["native_desktop_sgf_workflow"])
            self.assertIn("boundaries.providerParityCovered must be false", pending["native_desktop_sgf_workflow"])
            self.assertIn("boundaries.readboardParityCovered must be false", pending["native_desktop_sgf_workflow"])
            self.assertIn("boundaries.webviewDomAutomationCovered must be false", pending["native_desktop_sgf_workflow"])

    def test_native_desktop_sgf_workflow_rejects_local_absolute_paths(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["appPath"] = "/Applications/LizzieYzy.app"
            evidence["logPath"] = "/var/folders/native-workflow.log"
            screenshots = evidence["screenshots"]
            assert isinstance(screenshots, list)
            screenshot = screenshots[0]
            assert isinstance(screenshot, dict)
            screenshot["path"] = "/Users/haoc/native-workflow.png"
            checks = evidence["checks"]
            assert isinstance(checks, list)
            open_check = next(check for check in checks if isinstance(check, dict) and check.get("name") == "native_open_dialog")
            assert isinstance(open_check, dict)
            details = open_check["details"]
            assert isinstance(details, dict)
            details["openedPath"] = "C:\\Users\\haoc\\game.sgf"

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_native_desktop_sgf_workflow_evidence()
            mutate(evidence)
            write_json(root / smoke_user_flows.NATIVE_DESKTOP_SGF_WORKFLOW_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("native_desktop_sgf_workflow", failures)
            self.assertIn("native_desktop_sgf_workflow", pending)
            self.assertIn("appPath must not be a local absolute path", pending["native_desktop_sgf_workflow"])
            self.assertIn("logPath must not be a local absolute path", pending["native_desktop_sgf_workflow"])
            self.assertIn("screenshots[0].path must not be a local absolute path", pending["native_desktop_sgf_workflow"])
            self.assertIn("native_open_dialog SGF path must not be a local absolute path", pending["native_desktop_sgf_workflow"])

    def test_native_desktop_sgf_workflow_rejects_invalid_screenshots(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            screenshots = evidence["screenshots"]
            assert isinstance(screenshots, list)
            screenshot = screenshots[0]
            assert isinstance(screenshot, dict)
            screenshot["bytes"] = 0
            screenshot["sha256"] = "not-sha"

        self.assert_invalid_native_desktop_sgf_workflow_pending(
            mutate,
            "screenshots[0].bytes must be positive",
        )

    def test_native_desktop_sgf_workflow_requires_screenshot_sha(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            screenshots = evidence["screenshots"]
            assert isinstance(screenshots, list)
            screenshot = screenshots[0]
            assert isinstance(screenshot, dict)
            screenshot["sha256"] = "not-sha"

        self.assert_invalid_native_desktop_sgf_workflow_pending(
            mutate,
            "screenshots[0].sha256 must be a 64-character hex sha256",
        )

    def test_native_desktop_sgf_workflow_requires_screenshot_records(self) -> None:
        self.assert_invalid_native_desktop_sgf_workflow_pending(
            lambda evidence: evidence.__setitem__("screenshots", []),
            "screenshots must include at least one record",
        )

    def test_native_desktop_sgf_workflow_rejects_missing_reopen_invariants(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            checks = evidence["checks"]
            assert isinstance(checks, list)
            reopen = next(check for check in checks if isinstance(check, dict) and check.get("name") == "reopen_state_verified")
            assert isinstance(reopen, dict)
            details = reopen["details"]
            assert isinstance(details, dict)
            invariants = details["invariants"]
            assert isinstance(invariants, dict)
            invariants["contentHash"] = ""
            invariants["contentInvariant"] = {}
            board = invariants["boardInvariant"]
            tree = invariants["treeInvariant"]
            assert isinstance(board, dict)
            assert isinstance(tree, dict)
            board["verifiedByContent"] = False
            tree["rootPresent"] = False
            tree["moveCountAtLeast"] = 1
            tree["moveTokens"] = []

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_native_desktop_sgf_workflow_evidence()
            mutate(evidence)
            write_json(root / smoke_user_flows.NATIVE_DESKTOP_SGF_WORKFLOW_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("native_desktop_sgf_workflow", failures)
            self.assertIn("native_desktop_sgf_workflow", pending)
            self.assertIn("reopen_state_verified must include persisted edit evidence", pending["native_desktop_sgf_workflow"])
            self.assertIn("reopen_state_verified must verify board invariant", pending["native_desktop_sgf_workflow"])
            self.assertIn("reopen_state_verified must verify tree invariant", pending["native_desktop_sgf_workflow"])

    def assert_invalid_native_desktop_sgf_workflow_pending(self, mutate_evidence, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_native_desktop_sgf_workflow_evidence()
            mutate_evidence(evidence)
            write_json(root / smoke_user_flows.NATIVE_DESKTOP_SGF_WORKFLOW_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("native_desktop_sgf_workflow", failures)
            self.assertIn("native_desktop_sgf_workflow", pending)
            self.assertIn(expected_detail, pending["native_desktop_sgf_workflow"])

    def test_valid_katago_live_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_katago_live_evidence(root)
            write_valid_katago_tauri_runtime_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("katago_live_smoke", pass_names)
            self.assertNotIn("katago_live_smoke", pending_names)

    def test_invalid_katago_live_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_katago_live_evidence()
            find_evidence_check(evidence, "one_position_analysis")["details"]["moveInfoCount"] = 0
            write_json(root / smoke_user_flows.KATAGO_LIVE_SMOKE_EVIDENCE, evidence)
            write_valid_katago_tauri_runtime_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("katago_live_smoke", failures)
            self.assertIn("katago_live_smoke", pending)
            self.assertIn("CLI evidence: one_position_analysis must include positive moveInfoCount", pending["katago_live_smoke"])

    def test_katago_live_requires_tauri_runtime_evidence_too(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_katago_live_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("katago_live_smoke", failures)
            self.assertIn("katago_live_smoke", pending)
            self.assertIn("scripts/smoke_tauri_katago_live.py", pending["katago_live_smoke"])

    def test_valid_katago_review_workflow_ux_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_katago_review_workflow_ux_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("katago_review_workflow_ux_smoke", pass_names)
            self.assertNotIn("katago_review_workflow_ux_smoke", pending_names)

    def test_katago_review_workflow_ux_rejects_names_only_checks(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_katago_review_workflow_ux_evidence()
            evidence["checks"] = [
                {"name": name, "status": "pass"}
                for name in smoke_user_flows.KATAGO_REVIEW_WORKFLOW_UX_REQUIRED_CHECKS
            ]
            write_json(root / smoke_user_flows.KATAGO_REVIEW_WORKFLOW_UX_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("katago_review_workflow_ux_smoke", failures)
            self.assertIn("katago_review_workflow_ux_smoke", pending)
            self.assertIn("progress_verified.progressVerified must be true", pending["katago_review_workflow_ux_smoke"])

    def test_katago_review_workflow_ux_rejects_full_legacy_overclaim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_katago_review_workflow_ux_evidence()
            evidence["fullLegacyAnalysisParity"] = True
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["fullLegacyAnalysisParity"] = True
            write_json(root / smoke_user_flows.KATAGO_REVIEW_WORKFLOW_UX_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("katago_review_workflow_ux_smoke", failures)
            self.assertIn("katago_review_workflow_ux_smoke", pending)
            self.assertIn("fullLegacyAnalysisParity must be false", pending["katago_review_workflow_ux_smoke"])

    def test_katago_review_workflow_ux_rejects_live_claim_without_runtime_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_katago_review_workflow_ux_evidence()
            evidence["liveKataGoObserved"] = True
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["liveKataGoObserved"] = True
            write_json(root / smoke_user_flows.KATAGO_REVIEW_WORKFLOW_UX_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("katago_review_workflow_ux_smoke", failures)
            self.assertIn("katago_review_workflow_ux_smoke", pending)
            self.assertIn("liveKataGoObserved true requires runtimeMetadata", pending["katago_review_workflow_ux_smoke"])

    def test_katago_review_workflow_ux_rejects_existing_live_evidence_reuse(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_katago_review_workflow_ux_evidence()
            source_evidence = evidence["sourceEvidence"]
            assert isinstance(source_evidence, dict)
            source_evidence["existingLiveEvidenceUsedForNewLiveBehavior"] = True
            write_json(root / smoke_user_flows.KATAGO_REVIEW_WORKFLOW_UX_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("katago_review_workflow_ux_smoke", failures)
            self.assertIn("katago_review_workflow_ux_smoke", pending)
            self.assertIn(
                "existing live evidence must not be used for new live behavior claims",
                pending["katago_review_workflow_ux_smoke"],
            )

    def test_katago_review_workflow_ux_source_fact_drift_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_katago_review_workflow_ux_evidence(root)
            app_path = root / smoke_user_flows.APP_SOURCE
            app_path.write_text(
                app_path.read_text(encoding="utf-8").replace("activeJobIdRef.current === jobId", "activeJobIdRef.current === staleJobId"),
                encoding="utf-8",
            )

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("katago_review_workflow_ux_smoke", failures)
            self.assertIn("KataGo review workflow UX source facts are broken", failures["katago_review_workflow_ux_smoke"])
            self.assertIn("activeJobIdRef.current === jobId", failures["katago_review_workflow_ux_smoke"])

    def test_valid_katago_live_desktop_workflow_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_katago_live_desktop_workflow_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("katago_live_desktop_workflow_smoke", pass_names)
            self.assertNotIn("katago_live_desktop_workflow_smoke", pending_names)

    def test_katago_live_desktop_workflow_requires_required_check(self) -> None:
        self.assert_invalid_katago_live_desktop_workflow_pending(
            lambda evidence: evidence.__setitem__(
                "checks",
                [check for check in evidence["checks"] if check["name"] != "cache_hit_restored"],
            ),
            "missing required checks: cache_hit_restored",
        )

    def test_katago_live_desktop_workflow_rejects_browser_fallback(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["browserFallbackUsed"] = True
            find_evidence_check(evidence, "browser_fallback_excluded")["details"]["browserFallbackUsed"] = True

        self.assert_invalid_katago_live_desktop_workflow_pending(
            mutate,
            "browserFallbackUsed must be false",
        )

    def test_katago_live_desktop_workflow_requires_live_katago_observed(self) -> None:
        self.assert_invalid_katago_live_desktop_workflow_pending(
            lambda evidence: evidence.__setitem__("liveKataGoObserved", False),
            "liveKataGoObserved must be true",
        )

    def test_katago_live_desktop_workflow_rejects_cache_hit_without_frame_candidate_winrate(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            cache_hit = find_evidence_check(evidence, "cache_hit_restored")["details"]
            cache_hit.pop("frameCount", None)
            cache_hit.pop("candidateCount", None)
            cache_hit.pop("winrateRestored", None)

        self.assert_invalid_katago_live_desktop_workflow_pending(
            mutate,
            "cache_hit_restored must include frame evidence",
        )

    def test_katago_live_desktop_workflow_rejects_overclaim(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["fullLegacyAnalysisParity"] = True
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["releaseParity"] = True

        self.assert_invalid_katago_live_desktop_workflow_pending(
            mutate,
            "fullLegacyAnalysisParity must be false",
        )

    def assert_invalid_katago_live_desktop_workflow_pending(self, mutate_evidence, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_katago_live_desktop_workflow_evidence()
            mutate_evidence(evidence)
            write_json(root / smoke_user_flows.KATAGO_LIVE_DESKTOP_WORKFLOW_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("katago_live_desktop_workflow_smoke", failures)
            self.assertIn("katago_live_desktop_workflow_smoke", pending)
            self.assertIn(expected_detail, pending["katago_live_desktop_workflow_smoke"])

    def test_valid_installed_app_katago_live_workflow_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_installed_app_katago_live_workflow_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("installed_app_katago_live_workflow", pass_names)
            self.assertNotIn("installed_app_katago_live_workflow", pending_names)

    def test_installed_app_katago_live_workflow_rejects_static_only(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["collectionMethod"] = "source_static_only"
            evidence["sourceStaticOnly"] = True

        self.assert_invalid_installed_app_katago_live_workflow_pending(
            mutate,
            "collectionMethod must combine installed app and live KataGo runtime evidence",
        )

    def test_installed_app_katago_live_workflow_rejects_fake_assets(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            metadata = evidence["runtimeMetadata"]
            assert isinstance(metadata, dict)
            metadata["katagoVersion"] = "KataGo fake stub"

        self.assert_invalid_installed_app_katago_live_workflow_pending(
            mutate,
            "runtimeMetadata.katagoVersion must not contain fake/stub/mock/browser/dev-only claims",
        )

    def test_installed_app_katago_live_workflow_requires_real_asset_metadata(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            metadata = evidence["runtimeMetadata"]
            assert isinstance(metadata, dict)
            model = metadata["model"]
            assert isinstance(model, dict)
            model.pop("sha256")

        self.assert_invalid_installed_app_katago_live_workflow_pending(
            mutate,
            "runtimeMetadata.model.sha256 must be a 64-character hex sha256",
        )

    def test_installed_app_katago_live_workflow_rejects_tauri_dev_phase(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            report = evidence["sourceRuntimeReport"]
            assert isinstance(report, dict)
            report["phase"] = "katago-live"
            report["logPath"] = "<tmp>/tauri-dev.log"

        self.assert_invalid_installed_app_katago_live_workflow_pending(
            mutate,
            "sourceRuntimeReport.phase must be installed-app-katago-live-workflow",
        )

    def test_installed_app_katago_live_workflow_requires_backend_runtime_proof(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            report = evidence["sourceRuntimeReport"]
            assert isinstance(report, dict)
            checks = report["checks"]
            assert isinstance(checks, list)
            checks[:] = [
                check
                for check in checks
                if isinstance(check, dict) and check.get("name") != "backend_runtime_proof_observed"
            ]

        self.assert_invalid_installed_app_katago_live_workflow_pending(
            mutate,
            "sourceRuntimeReport missing required checks: backend_runtime_proof_observed",
        )

    def test_installed_app_katago_live_workflow_rejects_tauri_dev_backend_source(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            report = evidence["sourceRuntimeReport"]
            assert isinstance(report, dict)
            checks = report["checks"]
            assert isinstance(checks, list)
            backend = next(check for check in checks if isinstance(check, dict) and check.get("name") == "backend_runtime_proof_observed")
            details = backend["details"]
            assert isinstance(details, dict)
            raw = details["raw"]
            assert isinstance(raw, dict)
            runtime = raw["runtime"]
            assert isinstance(runtime, dict)
            runtime["source"] = "tauri-dev"

        self.assert_invalid_installed_app_katago_live_workflow_pending(
            mutate,
            "sourceRuntimeReport.backend_runtime_proof_observed backendRuntimeProof.runtime.source must be packaged-macos-app",
        )

    def test_installed_app_katago_live_workflow_rejects_cache_without_proof(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            cache_hit = find_evidence_check(evidence, "cache_hit_restored")["details"]
            cache_hit.pop("frameCount", None)
            cache_hit.pop("candidateCount", None)
            cache_hit.pop("winrateRestored", None)

        self.assert_invalid_installed_app_katago_live_workflow_pending(
            mutate,
            "cache_hit_restored must include frame evidence",
        )

    def test_installed_app_katago_live_workflow_rejects_overclaim(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["fullKataGoParity"] = True
            evidence["releaseParity"] = True
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["signedReleaseParity"] = True

        self.assert_invalid_installed_app_katago_live_workflow_pending(
            mutate,
            "fullKataGoParity must be false",
        )

    def assert_invalid_installed_app_katago_live_workflow_pending(self, mutate_evidence, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_installed_app_katago_live_workflow_evidence()
            mutate_evidence(evidence)
            write_json(root / smoke_user_flows.INSTALLED_APP_KATAGO_LIVE_WORKFLOW_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("installed_app_katago_live_workflow", failures)
            self.assertIn("installed_app_katago_live_workflow", pending)
            self.assertIn(expected_detail, pending["installed_app_katago_live_workflow"])

    def test_valid_readboard_tauri_runtime_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_readboard_tauri_runtime_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("readboard_live_smoke", pass_names)
            self.assertNotIn("readboard_live_smoke", pending_names)

    def test_invalid_readboard_tauri_runtime_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_readboard_tauri_runtime_evidence()
            find_evidence_check(evidence, "protocol_line_sync")["details"]["toPlay"] = "unknown"
            write_json(root / smoke_user_flows.READBOARD_TAURI_RUNTIME_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("readboard_live_smoke", failures)
            self.assertIn("readboard_live_smoke", pending)
            self.assertIn("protocol_line_sync.toPlay must be black or white", pending["readboard_live_smoke"])

    def test_readboard_tauri_runtime_evidence_requires_external_not_covered_boundaries(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_readboard_tauri_runtime_evidence()
            find_evidence_check(evidence, "external_capture_not_covered")["details"].pop("externalClientCaptureCovered")
            write_json(root / smoke_user_flows.READBOARD_TAURI_RUNTIME_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("readboard_live_smoke", failures)
            self.assertIn("readboard_live_smoke", pending)
            self.assertIn("external_capture_not_covered.externalClientCaptureCovered must be false", pending["readboard_live_smoke"])

    def test_readboard_tauri_runtime_evidence_requires_snapshot_change_semantics(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_readboard_tauri_runtime_evidence()
            target_change = find_evidence_check(evidence, "target_state_change_sync")["details"]
            target_change["afterSnapshotId"] = target_change["beforeSnapshotId"]
            target_change["afterStoneCount"] = target_change["beforeStoneCount"]
            target_change["afterMoveNumber"] = target_change["beforeMoveNumber"]
            write_json(root / smoke_user_flows.READBOARD_TAURI_RUNTIME_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("readboard_live_smoke", failures)
            self.assertIn("readboard_live_smoke", pending)
            self.assertIn("target_state_change_sync snapshot ids must differ", pending["readboard_live_smoke"])
            self.assertIn("target_state_change_sync stone count or move number must change", pending["readboard_live_smoke"])

    def test_missing_readboard_tauri_runtime_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("readboard_live_smoke", failures)
            self.assertIn("readboard_live_smoke", pending)
            self.assertIn("scripts/smoke_tauri_readboard_live.py", pending["readboard_live_smoke"])

    def test_valid_readboard_image_import_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_readboard_image_import_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("readboard_image_import_smoke", pass_names)
            self.assertNotIn("readboard_image_import_smoke", pending_names)

    def test_readboard_image_import_rejects_full_ocr_overclaim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_readboard_image_import_evidence()
            evidence["fullOcrParity"] = True
            find_evidence_check(evidence, "scope_boundaries")["details"]["fullOcrParity"] = True
            write_json(root / smoke_user_flows.READBOARD_IMAGE_IMPORT_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("readboard_image_import_smoke", failures)
            self.assertIn("readboard_image_import_smoke", pending)
            self.assertIn("fullOcrParity must be false", pending["readboard_image_import_smoke"])

    def test_readboard_image_import_rejects_external_capture_overclaim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_readboard_image_import_evidence()
            evidence["externalCaptureCovered"] = True
            find_evidence_check(evidence, "scope_boundaries")["details"]["externalCaptureCovered"] = True
            write_json(root / smoke_user_flows.READBOARD_IMAGE_IMPORT_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("readboard_image_import_smoke", failures)
            self.assertIn("readboard_image_import_smoke", pending)
            self.assertIn("externalCaptureCovered must be false", pending["readboard_image_import_smoke"])

    def test_readboard_image_import_requires_path_and_base64_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_readboard_controlled_board_fixture(root)
            evidence = valid_readboard_image_import_evidence()
            evidence["imagePathImportVerified"] = False
            evidence["imageBase64ImportVerified"] = False
            find_evidence_check(evidence, "image_path_import")["details"]["imagePathImportVerified"] = False
            find_evidence_check(evidence, "image_base64_import")["details"]["imageBase64ImportVerified"] = False
            write_json(root / smoke_user_flows.READBOARD_IMAGE_IMPORT_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("readboard_image_import_smoke", failures)
            self.assertIn("readboard_image_import_smoke", pending)
            self.assertIn("imagePathImportVerified must be true", pending["readboard_image_import_smoke"])
            self.assertIn("imageBase64ImportVerified must be true", pending["readboard_image_import_smoke"])

    def test_readboard_image_import_requires_matching_artifact_hash_and_size(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_readboard_controlled_board_fixture(root)
            evidence = valid_readboard_image_import_evidence()
            details = find_evidence_check(evidence, "image_path_import")["details"]
            details["imageSha256"] = "0" * 64
            details["imageBytes"] = 1
            write_json(root / smoke_user_flows.READBOARD_IMAGE_IMPORT_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("readboard_image_import_smoke", failures)
            self.assertIn("readboard_image_import_smoke", pending)
            self.assertIn("image_path_import.imageBytes must match artifact size", pending["readboard_image_import_smoke"])
            self.assertIn("image_path_import.imageSha256 must match artifact sha256", pending["readboard_image_import_smoke"])

    def test_readboard_image_import_requires_invalid_and_non_board_rejections(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_readboard_controlled_board_fixture(root)
            evidence = valid_readboard_image_import_evidence()
            evidence["invalidImageRejected"] = False
            evidence["nonBoardImageRejected"] = False
            find_evidence_check(evidence, "invalid_image_rejected")["details"]["invalidImageRejected"] = False
            find_evidence_check(evidence, "non_board_image_rejected")["details"]["nonBoardImageRejected"] = False
            write_json(root / smoke_user_flows.READBOARD_IMAGE_IMPORT_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("readboard_image_import_smoke", failures)
            self.assertIn("readboard_image_import_smoke", pending)
            self.assertIn("invalidImageRejected must be true", pending["readboard_image_import_smoke"])
            self.assertIn("nonBoardImageRejected must be true", pending["readboard_image_import_smoke"])

    def test_readboard_image_import_requires_snapshot_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_readboard_controlled_board_fixture(root)
            evidence = valid_readboard_image_import_evidence()
            snapshot = find_evidence_check(evidence, "snapshot_verified")["details"]
            snapshot["boardSizeVerified"] = False
            snapshot["stoneCountVerified"] = False
            snapshot["toPlay"] = "unknown"
            write_json(root / smoke_user_flows.READBOARD_IMAGE_IMPORT_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("readboard_image_import_smoke", failures)
            self.assertIn("readboard_image_import_smoke", pending)
            self.assertIn("snapshot_verified.boardSizeVerified must be true", pending["readboard_image_import_smoke"])
            self.assertIn("snapshot_verified.stoneCountVerified must be true", pending["readboard_image_import_smoke"])
            self.assertIn("snapshot_verified.toPlay must be black or white", pending["readboard_image_import_smoke"])

    def test_valid_readboard_image_ocr_corpus_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_readboard_image_ocr_corpus_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("readboard_image_ocr_corpus_smoke", pass_names)
            self.assertNotIn("readboard_image_ocr_corpus_smoke", pending_names)

    def test_readboard_image_ocr_corpus_rejects_overclaims(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_readboard_ocr_corpus_fixtures(root)
            evidence = valid_readboard_image_ocr_corpus_evidence()
            evidence["fullOcrParity"] = True
            evidence["externalWindowCaptureCovered"] = True
            evidence["realClientCaptureCovered"] = True
            evidence["fullReadboardParity"] = True
            boundary = find_evidence_check(evidence, "scope_boundaries")["details"]
            boundary["fullOcrParity"] = True
            boundary["externalWindowCaptureCovered"] = True
            boundary["realClientCaptureCovered"] = True
            boundary["fullReadboardParity"] = True
            write_json(root / smoke_user_flows.READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("readboard_image_ocr_corpus_smoke", pending)
            detail = pending["readboard_image_ocr_corpus_smoke"]
            self.assertIn("fullOcrParity must be false", detail)
            self.assertIn("externalWindowCaptureCovered must be false", detail)
            self.assertIn("realClientCaptureCovered must be false", detail)
            self.assertIn("fullReadboardParity must be false", detail)

    def test_readboard_image_ocr_corpus_requires_manifest_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_readboard_ocr_corpus_fixtures(root)
            evidence = valid_readboard_image_ocr_corpus_evidence()
            manifest = evidence["fixtureManifest"]
            manifest[0]["path"] = "/Users/example/private.png"
            manifest[1]["sha256"] = "0" * 64
            manifest[2]["sizeBytes"] = 1
            write_json(root / smoke_user_flows.READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("readboard_image_ocr_corpus_smoke", pending)
            detail = pending["readboard_image_ocr_corpus_smoke"]
            self.assertIn("fixtureManifest[0].path must be repo-relative and sanitized", detail)
            self.assertIn("fixtureManifest[1].sha256 must match artifact sha256", detail)
            self.assertIn("fixtureManifest[2].sizeBytes must match artifact size", detail)

    def test_readboard_image_ocr_corpus_rejects_happy_path_only(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_readboard_ocr_corpus_fixtures(root)
            evidence = valid_readboard_image_ocr_corpus_evidence()
            evidence["fixtureManifest"] = evidence["fixtureManifest"][:1]
            write_json(root / smoke_user_flows.READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("readboard_image_ocr_corpus_smoke", pending)
            detail = pending["readboard_image_ocr_corpus_smoke"]
            self.assertIn("fixtureManifest must include at least 4 fixtures", detail)
            self.assertIn("fixtureManifest missing outcomes:", detail)
            self.assertIn("invalid", detail)
            self.assertIn("non-board", detail)
            self.assertIn("truncated", detail)

    def test_readboard_image_ocr_corpus_requires_rejection_and_equivalence_proofs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_readboard_ocr_corpus_fixtures(root)
            evidence = valid_readboard_image_ocr_corpus_evidence()
            evidence["pathBase64EquivalenceVerified"] = False
            evidence["truncatedImageRejected"] = False
            find_evidence_check(evidence, "path_base64_equivalence")["details"]["sameHash"] = False
            find_evidence_check(evidence, "truncated_image_rejected")["details"]["truncatedImageRejected"] = False
            write_json(root / smoke_user_flows.READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("readboard_image_ocr_corpus_smoke", pending)
            detail = pending["readboard_image_ocr_corpus_smoke"]
            self.assertIn("pathBase64EquivalenceVerified must be true", detail)
            self.assertIn("path_base64_equivalence.sameHash must be true", detail)
            self.assertIn("truncatedImageRejected must be true", detail)
            self.assertIn("truncated_image_rejected.truncatedImageRejected must be true", detail)

    def test_readboard_image_ocr_corpus_requires_coverage_and_hash_invariants(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_readboard_ocr_corpus_fixtures(root)
            evidence = valid_readboard_image_ocr_corpus_evidence()
            find_evidence_check(evidence, "board_size_coverage")["details"]["boardSizes"] = [19]
            find_evidence_check(evidence, "stone_count_coverage")["details"]["stoneCounts"] = [3]
            find_evidence_check(evidence, "hash_invariants")["details"]["pathBase64Sha256Equal"] = False
            write_json(root / smoke_user_flows.READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("readboard_image_ocr_corpus_smoke", pending)
            detail = pending["readboard_image_ocr_corpus_smoke"]
            self.assertIn("board_size_coverage.boardSizes must include at least two of 9, 13, 19", detail)
            self.assertIn("stone_count_coverage.stoneCounts must include at least two non-negative counts", detail)
            self.assertIn("hash_invariants.pathBase64Sha256Equal must be true", detail)

    def test_readboard_image_ocr_corpus_requires_external_capture_unsupported_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_readboard_ocr_corpus_fixtures(root)
            evidence = valid_readboard_image_ocr_corpus_evidence()
            external = find_evidence_check(evidence, "external_capture_unsupported_contract")["details"]
            external["externalWindowCaptureCovered"] = True
            external["realClientCaptureCovered"] = True
            external["message"] = "captured"
            write_json(root / smoke_user_flows.READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("readboard_image_ocr_corpus_smoke", pending)
            detail = pending["readboard_image_ocr_corpus_smoke"]
            self.assertIn("external_capture_unsupported_contract.externalWindowCaptureCovered must be false", detail)
            self.assertIn("external_capture_unsupported_contract.realClientCaptureCovered must be false", detail)
            self.assertIn("external_capture_unsupported_contract.message must mention unsupported", detail)

    def test_readboard_image_ocr_corpus_rejects_negative_artifact_reuse(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_readboard_ocr_corpus_fixtures(root)
            evidence = valid_readboard_image_ocr_corpus_evidence()
            valid_fixture = evidence["fixtureManifest"][0]
            for fixture in evidence["fixtureManifest"]:
                if fixture["expectedOutcome"] in {"invalid", "non-board", "truncated"}:
                    fixture["path"] = valid_fixture["path"]
                    fixture["sha256"] = valid_fixture["sha256"]
                    fixture["sizeBytes"] = valid_fixture["sizeBytes"]
            write_json(root / smoke_user_flows.READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("readboard_image_ocr_corpus_smoke", pending)
            self.assertIn(
                "path must not reuse a valid fixture artifact",
                pending["readboard_image_ocr_corpus_smoke"],
            )

    def test_readboard_image_ocr_corpus_requires_negative_error_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_readboard_ocr_corpus_fixtures(root)
            evidence = valid_readboard_image_ocr_corpus_evidence()
            for fixture in evidence["fixtureManifest"]:
                if fixture["expectedOutcome"] in {"invalid", "non-board", "truncated"}:
                    fixture.pop("expectedError", None)
                    fixture["boardSize"] = 19
                    fixture["stoneCount"] = 1
            write_json(root / smoke_user_flows.READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("readboard_image_ocr_corpus_smoke", pending)
            detail = pending["readboard_image_ocr_corpus_smoke"]
            self.assertIn("expectedError must be non-empty", detail)
            self.assertIn("boardSize must be absent", detail)
            self.assertIn("stoneCount must be absent", detail)

    def test_valid_readboard_external_capture_mvp_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_readboard_external_capture_mvp_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("readboard_external_capture_mvp", pass_names)
            self.assertNotIn("readboard_external_capture_mvp", pending_names)

    def test_readboard_external_capture_mvp_rejects_static_committed_evidence(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["collectionMethod"] = "committed_external_capture_mvp_evidence"
            evidence["sourceStaticOnly"] = True
            evidence.pop("rawBackendResult", None)

        self.assert_invalid_readboard_external_capture_mvp_pending(
            mutate,
            "collectionMethod must be runtime_backend_external_capture_mvp",
        )

    def test_readboard_external_capture_mvp_unavailable_is_pending_not_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_readboard_external_capture_mvp_unavailable_evidence()
            write_json(root / smoke_user_flows.READBOARD_EXTERNAL_CAPTURE_MVP_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertNotIn("readboard_external_capture_mvp", failures)
            self.assertNotIn("readboard_external_capture_mvp", pass_names)
            self.assertIn("readboard_external_capture_mvp", pending)
            self.assertIn("permission denied by operator", pending["readboard_external_capture_mvp"])

    def test_readboard_external_capture_mvp_rejects_overclaims(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["fullOcrParity"] = True
            evidence["fullReadboardParity"] = True
            evidence["externalClientCaptureCovered"] = True
            evidence["targetClientDiscoveryCovered"] = True
            evidence["realClientParity"] = True
            evidence["windowsLinuxCaptureCovered"] = True
            evidence["releaseParity"] = True
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            for key in smoke_user_flows.READBOARD_EXTERNAL_CAPTURE_MVP_REQUIRED_FALSE_FIELDS:
                boundaries[key] = True

        self.assert_invalid_readboard_external_capture_mvp_pending(
            mutate,
            "fullOcrParity must be false",
        )

    def test_readboard_external_capture_mvp_requires_operator_selection(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["operatorInitiated"] = False
            evidence["userSelectionRequired"] = False
            source = evidence["captureSource"]
            assert isinstance(source, dict)
            source["operatorInitiated"] = False
            source["userSelectionRequired"] = False

        self.assert_invalid_readboard_external_capture_mvp_pending(
            mutate,
            "operatorInitiated must be true",
        )

    def test_readboard_external_capture_mvp_requires_artifact_hash_and_size(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            artifact = find_evidence_check(evidence, "capture_artifact_recorded")["details"]
            artifact["sha256"] = "0" * 64
            artifact["sizeBytes"] = 1

        self.assert_invalid_readboard_external_capture_mvp_pending(
            mutate,
            "capture_artifact_recorded.sizeBytes must match artifact size",
        )

    def test_readboard_external_capture_mvp_requires_preview_confirmation(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            evidence["previewOnlyBeforeConfirmation"] = False
            evidence["boardReplacedOnlyAfterConfirmation"] = False
            preview = find_evidence_check(evidence, "preview_confirmation")["details"]
            preview["previewOnlyBeforeConfirmation"] = False
            preview["boardReplacedBeforeConfirmation"] = True
            preview["boardReplacedOnlyAfterConfirmation"] = False

        self.assert_invalid_readboard_external_capture_mvp_pending(
            mutate,
            "previewOnlyBeforeConfirmation must be true",
        )

    def test_readboard_external_capture_mvp_requires_structured_result(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            result = find_evidence_check(evidence, "structured_result")["details"]
            result["toPlay"] = "unknown"
            result["boardReplaced"] = False

        self.assert_invalid_readboard_external_capture_mvp_pending(
            mutate,
            "structured_result.toPlay must be black or white",
        )

    def assert_invalid_readboard_external_capture_mvp_pending(self, mutate_evidence, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_readboard_controlled_board_fixture(root)
            evidence = valid_readboard_external_capture_mvp_evidence()
            mutate_evidence(evidence)
            write_json(root / smoke_user_flows.READBOARD_EXTERNAL_CAPTURE_MVP_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("readboard_external_capture_mvp", failures)
            self.assertIn("readboard_external_capture_mvp", pending)
            self.assertIn(expected_detail, pending["readboard_external_capture_mvp"])

    def test_valid_provider_controlled_network_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_provider_live_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("provider_live_smoke", pass_names)
            self.assertNotIn("provider_live_smoke", pending_names)

    def test_missing_provider_controlled_network_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("provider_live_smoke", failures)
            self.assertIn("provider_live_smoke", pending)
            self.assertIn("scripts/smoke_tauri_provider_live.py", pending["provider_live_smoke"])

    def test_invalid_provider_controlled_network_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_provider_live_evidence()
            find_evidence_check(evidence, "fox_controlled_fetch")["details"]["moveCount"] = 0
            write_json(root / smoke_user_flows.PROVIDER_LIVE_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("provider_live_smoke", failures)
            self.assertIn("provider_live_smoke", pending)
            self.assertIn("fox_controlled_fetch.moveCount must be positive", pending["provider_live_smoke"])

    def test_provider_evidence_claiming_external_or_fixture_only_does_not_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_provider_live_evidence()
            find_evidence_check(evidence, "yike_controlled_fetch")["details"]["fixtureParserOnly"] = True
            find_evidence_check(evidence, "offline_not_counted_as_external_live")["details"][
                "externalProviderServiceCovered"
            ] = True
            write_json(root / smoke_user_flows.PROVIDER_LIVE_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("provider_live_smoke", failures)
            self.assertIn("provider_live_smoke", pending)
            self.assertIn("yike_controlled_fetch.fixtureParserOnly must be false", pending["provider_live_smoke"])
            self.assertIn(
                "offline_not_counted_as_external_live.externalProviderServiceCovered must be false",
                pending["provider_live_smoke"],
            )

    def test_provider_evidence_rejects_legacy_runner_field_names(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_provider_live_evidence()
            fox_details = find_evidence_check(evidence, "fox_controlled_fetch")["details"]
            fox_details.pop("directHttpWarning")
            fox_details["warningIncludesDirectHttp"] = True
            failure_details = find_evidence_check(evidence, "provider_failure_modes")["details"]
            failure_details.pop("errorKind")
            failure_details["kind"] = "invalidPayload"
            network_details = find_evidence_check(evidence, "controlled_network_observed")["details"]
            network_details.pop("failureRequestObserved")
            network_details["badPayloadRequestObserved"] = True
            offline_details = find_evidence_check(evidence, "offline_not_counted_as_external_live")["details"]
            offline_details.pop("offlineParserOnly")
            offline_details["offlineFixtureOnly"] = False
            write_json(root / smoke_user_flows.PROVIDER_LIVE_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("provider_live_smoke", failures)
            self.assertIn("provider_live_smoke", pending)
            self.assertIn("fox_controlled_fetch.directHttpWarning must be true", pending["provider_live_smoke"])
            self.assertIn("provider_failure_modes.errorKind must be non-empty", pending["provider_live_smoke"])
            self.assertIn(
                "controlled_network_observed.failureRequestObserved must be true",
                pending["provider_live_smoke"],
            )
            self.assertIn(
                "offline_not_counted_as_external_live.offlineParserOnly must be false",
                pending["provider_live_smoke"],
            )

    def test_valid_multiplatform_packaging_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_multiplatform_packaging_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("multiplatform_packaging_smoke", pass_names)
            self.assertNotIn("multiplatform_packaging_smoke", pending_names)

    def test_missing_multiplatform_packaging_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("multiplatform_packaging_smoke", failures)
            self.assertIn("multiplatform_packaging_smoke", pending)
            self.assertIn("scripts/smoke_multiplatform_packaging.py", pending["multiplatform_packaging_smoke"])

    def test_partial_multiplatform_packaging_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_multiplatform_packaging_evidence()
            checks = evidence["checks"]
            assert isinstance(checks, list)
            evidence["checks"] = [check for check in checks if isinstance(check, dict) and check.get("name") != "linux_artifacts"]
            write_json(root / smoke_user_flows.MULTIPLATFORM_PACKAGING_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("multiplatform_packaging_smoke", failures)
            self.assertIn("multiplatform_packaging_smoke", pending)
            self.assertIn("missing required checks: linux_artifacts", pending["multiplatform_packaging_smoke"])

    def test_invalid_schema_multiplatform_packaging_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_multiplatform_packaging_evidence()
            evidence["schema"] = "lizzieyzy.multiplatform-packaging-smoke.v0"
            write_json(root / smoke_user_flows.MULTIPLATFORM_PACKAGING_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("multiplatform_packaging_smoke", failures)
            self.assertIn("multiplatform_packaging_smoke", pending)
            self.assertIn(smoke_user_flows.MULTIPLATFORM_PACKAGING_SMOKE_SCHEMA, pending["multiplatform_packaging_smoke"])

    def test_invalid_checksum_multiplatform_packaging_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_multiplatform_packaging_evidence()
            find_evidence_check(evidence, "checksums")["details"]["entries"][0]["value"] = "not-sha256"
            write_json(root / smoke_user_flows.MULTIPLATFORM_PACKAGING_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("multiplatform_packaging_smoke", failures)
            self.assertIn("multiplatform_packaging_smoke", pending)
            self.assertIn("checksums.entries[0].value must be a 64-character hex sha256", pending["multiplatform_packaging_smoke"])

    def test_invalid_signing_multiplatform_packaging_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_multiplatform_packaging_evidence()
            find_evidence_check(evidence, "signing_recorded")["details"]["windows"]["productionSigned"] = True
            write_json(root / smoke_user_flows.MULTIPLATFORM_PACKAGING_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("multiplatform_packaging_smoke", failures)
            self.assertIn("multiplatform_packaging_smoke", pending)
            self.assertIn("signing_recorded.windows.productionSigned must be false", pending["multiplatform_packaging_smoke"])

    def test_invalid_dev_server_absent_multiplatform_packaging_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_multiplatform_packaging_evidence()
            find_evidence_check(evidence, "dev_server_absent")["details"]["linux"] = False
            write_json(root / smoke_user_flows.MULTIPLATFORM_PACKAGING_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("multiplatform_packaging_smoke", failures)
            self.assertIn("multiplatform_packaging_smoke", pending)
            self.assertIn("dev_server_absent.linux must be true", pending["multiplatform_packaging_smoke"])

    def test_placeholder_multiplatform_packaging_artifact_does_not_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_multiplatform_packaging_evidence()
            windows_artifacts = find_evidence_check(evidence, "windows_artifacts")["details"]["artifacts"]
            assert isinstance(windows_artifacts, list)
            windows_artifacts.clear()
            windows_artifacts.append(
                {
                    "artifactPresent": False,
                    "path": "workflow-contract/windows-placeholder",
                    "sizeBytes": 0,
                    "sha256": "d" * 64,
                }
            )
            checksum_entries = find_evidence_check(evidence, "checksums")["details"]["entries"]
            assert isinstance(checksum_entries, list)
            for entry in checksum_entries:
                assert isinstance(entry, dict)
                if entry.get("platform") == "windows":
                    entry["artifactPresent"] = False
            write_json(root / smoke_user_flows.MULTIPLATFORM_PACKAGING_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("multiplatform_packaging_smoke", failures)
            self.assertIn("multiplatform_packaging_smoke", pending)
            self.assertIn(
                "windows_artifacts.artifacts must include at least one artifactPresent true entry",
                pending["multiplatform_packaging_smoke"],
            )
            self.assertIn("checksums.entries[1].artifactPresent must be true", pending["multiplatform_packaging_smoke"])
            self.assertIn("checksums missing platforms: windows", pending["multiplatform_packaging_smoke"])

    def test_valid_native_menu_shortcut_evidence_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_native_menu_shortcut_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("native_menu_shortcut_smoke", pass_names)
            self.assertNotIn("native_menu_shortcut_smoke", pending_names)

    def test_missing_native_menu_shortcut_evidence_remains_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("native_menu_shortcut_smoke", failures)
            self.assertIn("native_menu_shortcut_smoke", pending)
            self.assertIn(smoke_user_flows.NATIVE_MENU_SHORTCUT_SMOKE_EVIDENCE, pending["native_menu_shortcut_smoke"])

    def test_native_menu_shortcut_evidence_rejects_overclaims(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_native_menu_shortcut_evidence()
            evidence["fullShortcutParity"] = True
            evidence["fullLegacyMenuParity"] = True
            evidence["webviewDomProof"] = True
            evidence["releasePublished"] = True
            evidence["windowsLinuxCovered"] = True
            evidence["providerCompleted"] = True
            evidence["readboardCompleted"] = True
            evidence["ocrCompleted"] = True
            boundaries = evidence["boundaries"]
            assert isinstance(boundaries, dict)
            boundaries["productionSigned"] = True
            boundaries["notarized"] = True
            write_json(root / smoke_user_flows.NATIVE_MENU_SHORTCUT_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("native_menu_shortcut_smoke", failures)
            self.assertIn("native_menu_shortcut_smoke", pending)
            detail = pending["native_menu_shortcut_smoke"]
            self.assertIn("fullShortcutParity must be false", detail)
            self.assertIn("fullLegacyMenuParity must be false", detail)
            self.assertIn("webviewDomProof must be false", detail)
            self.assertIn("releasePublished must be false", detail)
            self.assertIn("windowsLinuxCovered must be false", detail)
            self.assertIn("providerCompleted must be false", detail)
            self.assertIn("readboardCompleted must be false", detail)
            self.assertIn("ocrCompleted must be false", detail)
            self.assertIn("productionSigned must be false", detail)
            self.assertIn("notarized must be false", detail)

    def test_native_menu_shortcut_requires_input_editing_safety(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_native_menu_shortcut_evidence()
            evidence["inputEditingSafe"] = False
            find_evidence_check(evidence, "input_editing_safe")["details"]["inputEditingSafe"] = False
            write_json(root / smoke_user_flows.NATIVE_MENU_SHORTCUT_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("native_menu_shortcut_smoke", failures)
            self.assertIn("native_menu_shortcut_smoke", pending)
            self.assertIn("inputEditingSafe must be true", pending["native_menu_shortcut_smoke"])
            self.assertIn("input_editing_safe.inputEditingSafe must be true", pending["native_menu_shortcut_smoke"])

    def test_native_menu_shortcut_helper_event_name_pattern_passes_runtime_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_native_menu_shortcut_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            passes = {result.name for result in results if result.status == "PASS"}
            self.assertNotIn("native_menu_shortcut_smoke", failures)
            self.assertNotIn("native_menu_shortcut_smoke", pending)
            self.assertIn("native_menu_shortcut_smoke", passes)

    def test_native_menu_shortcut_rejects_helper_with_wrong_event_name(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            backend_path = root / smoke_user_flows.BACKEND_SOURCE
            backend_path.write_text(
                backend_path.read_text(encoding="utf-8").replace(
                    f'const canonicalFallback = "{smoke_user_flows.NATIVE_MENU_EVENT_NAME}"',
                    'const canonicalFallback = "legacy://menu-action"',
                ),
                encoding="utf-8",
            )
            write_valid_native_menu_shortcut_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("native_menu_shortcut_smoke", pending)
            self.assertIn(f"frontend listener must include {smoke_user_flows.NATIVE_MENU_EVENT_NAME}", pending["native_menu_shortcut_smoke"])

    def test_native_menu_shortcut_rejects_snake_case_action_id_drift(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            create_legacy_actions_fixture(
                root,
                action_id_overrides={"help.backendStatus": "help.backend_status"},
            )
            write_valid_native_menu_shortcut_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("native_menu_shortcut_smoke", pending)
            self.assertIn(
                "Rust native menu action ids must exactly align with frontend legacyActionMatrix action ids",
                pending["native_menu_shortcut_smoke"],
            )

    def test_native_menu_shortcut_rejects_bogus_evidence_group(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_native_menu_shortcut_evidence()
            evidence["groups"] = ["File", "Edit", "View", "Engine", "Tools", "Help"]
            write_json(root / smoke_user_flows.NATIVE_MENU_SHORTCUT_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("native_menu_shortcut_smoke", pending)
            self.assertIn("groups must exactly equal File, Game, Analysis, View, Engine, Tools, Help", pending["native_menu_shortcut_smoke"])

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

    def test_runtime_evidence_requires_annotation_add_update_remove_semantics(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_tauri_runtime_ui_evidence()
            annotation = find_evidence_check(evidence, "annotation_edit")["evidence"]
            assert isinstance(annotation, dict)
            annotation["removed"] = []
            annotation["annotations"]["SQ"] = ["tt"]
            write_json(root / smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("ui_tauri_runtime_smoke", failures)
            self.assertIn("ui_tauri_runtime_smoke", pending)
            self.assertIn("annotation_edit annotations.SQ must equal []", pending["ui_tauri_runtime_smoke"])
            self.assertIn("annotation_edit removed must be exactly SQ", pending["ui_tauri_runtime_smoke"])

    def test_runtime_evidence_rejects_wrong_annotation_points(self) -> None:
        self.assert_invalid_annotation_evidence_pending(
            lambda annotation: annotation["annotations"].__setitem__("TR", ["ab"]),
            "annotation_edit annotations.TR must equal ['aa']",
        )

    def test_runtime_evidence_rejects_wrong_annotation_labels(self) -> None:
        self.assert_invalid_annotation_evidence_pending(
            lambda annotation: annotation["annotations"].__setitem__("LB", ["aa:B", "ee:E"]),
            "annotation_edit annotations.LB must include aa:A and ee:E",
        )

    def test_runtime_evidence_rejects_wrong_annotation_arrow_and_line(self) -> None:
        self.assert_invalid_annotation_evidence_pending(
            lambda annotation: (
                annotation["annotations"].__setitem__("AR", ["bb:aa"]),
                annotation["annotations"].__setitem__("LN", ["dd:cc"]),
            ),
            "annotation_edit annotations.AR must equal ['aa:bb']",
        )
        self.assert_invalid_annotation_evidence_pending(
            lambda annotation: annotation["annotations"].__setitem__("LN", ["dd:cc"]),
            "annotation_edit annotations.LN must equal ['cc:dd']",
        )

    def test_runtime_evidence_rejects_wrong_annotation_change_property_names(self) -> None:
        self.assert_invalid_annotation_evidence_pending(
            lambda annotation: annotation.__setitem__("added", ["TR", "CR", "MA", "SL", "LB", "LN"]),
            "annotation_edit added must be exactly AR, CR, LN, MA, SL, TR",
        )
        self.assert_invalid_annotation_evidence_pending(
            lambda annotation: annotation.__setitem__("updated", ["TR"]),
            "annotation_edit updated must be exactly LB",
        )
        self.assert_invalid_annotation_evidence_pending(
            lambda annotation: annotation.__setitem__("removed", ["CR"]),
            "annotation_edit removed must be exactly SQ",
        )

    def assert_invalid_annotation_evidence_pending(self, mutate_annotation, expected_detail: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_tauri_runtime_ui_evidence()
            annotation = find_evidence_check(evidence, "annotation_edit")["evidence"]
            assert isinstance(annotation, dict)
            mutate_annotation(annotation)
            write_json(root / smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("ui_tauri_runtime_smoke", failures)
            self.assertIn("ui_tauri_runtime_smoke", pending)
            self.assertIn(expected_detail, pending["ui_tauri_runtime_smoke"])

    def test_runtime_evidence_requires_second_launch_reopen_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_tauri_runtime_ui_evidence()
            roundtrip = find_evidence_check(evidence, "save_readback_roundtrip")["evidence"]
            assert isinstance(roundtrip, dict)
            roundtrip.pop("secondLaunch")
            roundtrip.pop("reopen")
            roundtrip.pop("afterReopen")
            write_json(root / smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertNotIn("ui_tauri_runtime_smoke", failures)
            self.assertIn("ui_tauri_runtime_smoke", pending)
            self.assertIn("secondLaunch object", pending["ui_tauri_runtime_smoke"])
            self.assertIn("reopen object", pending["ui_tauri_runtime_smoke"])
            self.assertIn("afterReopen object", pending["ui_tauri_runtime_smoke"])

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

    def test_legacy_config_migration_surface_passes_with_frontend_wiring(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            passes = {result.name for result in results if result.status == "PASS"}
            self.assertNotIn("legacy_config_migration_surface", failures)
            self.assertIn("legacy_config_migration_surface", passes)

    def test_legacy_config_migration_surface_missing_preferences_ui_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, preferences_migration_ui=False)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("legacy_config_migration_surface", failures)
            self.assertIn("PreferencesPanel missing legacyConfigPath", failures["legacy_config_migration_surface"])

    def test_legacy_config_migration_surface_missing_safety_ui_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, preferences_migration_safety_ui=False)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("legacy_config_migration_surface", failures)
            self.assertIn("PreferencesPanel missing legacy-config-safety-status", failures["legacy_config_migration_surface"])

    def test_valid_legacy_config_corpus_migration_evidence_passes_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            write_valid_legacy_config_corpus_migration_evidence(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending_names = {result.name for result in results if result.status == "PENDING"}
            pass_names = {result.name for result in results if result.status == "PASS"}
            self.assertEqual([], failures)
            self.assertIn("legacy_config_corpus_migration_smoke", pass_names)
            self.assertNotIn("legacy_config_corpus_migration_smoke", pending_names)

    def test_legacy_config_corpus_migration_evidence_requires_fixture_classes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_legacy_config_corpus_migration_evidence()
            evidence["fixtureClasses"] = [
                item
                for item in evidence["fixtureClasses"]
                if item != "unknown-deprecated"
            ]
            write_json(root / smoke_user_flows.LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("legacy_config_corpus_migration_smoke", pending)
            self.assertIn("fixtureClasses missing: unknown-deprecated", pending["legacy_config_corpus_migration_smoke"])

    def test_legacy_config_corpus_migration_evidence_rejects_low_fixture_count(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_legacy_config_corpus_migration_evidence()
            evidence["corpusFixtureCount"] = 7
            write_json(root / smoke_user_flows.LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("legacy_config_corpus_migration_smoke", pending)
            self.assertIn("corpus fixture count must be at least 8", pending["legacy_config_corpus_migration_smoke"])

    def test_legacy_config_corpus_migration_evidence_requires_no_write_proofs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_legacy_config_corpus_migration_evidence()
            evidence["previewNoWrite"] = False
            write_json(root / smoke_user_flows.LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("legacy_config_corpus_migration_smoke", pending)
            self.assertIn("previewNoWrite must be true", pending["legacy_config_corpus_migration_smoke"])

    def test_legacy_config_corpus_migration_evidence_rejects_overclaim_boundaries(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            evidence = valid_legacy_config_corpus_migration_evidence()
            evidence["fullHistoricalConfigParity"] = True
            evidence["boundaries"]["fullHistoricalConfigParity"] = True
            write_json(root / smoke_user_flows.LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_EVIDENCE, evidence)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertIn("legacy_config_corpus_migration_smoke", pending)
            self.assertIn("fullHistoricalConfigParity must be false", pending["legacy_config_corpus_migration_smoke"])
            self.assertIn("boundaries.fullHistoricalConfigParity must be false", pending["legacy_config_corpus_migration_smoke"])

    def test_sgf_annotation_surface_passes_with_frontend_wiring(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            passes = {result.name for result in results if result.status == "PASS"}
            self.assertNotIn("sgf_annotation_surface", failures)
            self.assertIn("sgf_annotation_surface", passes)

    def test_sgf_annotation_surface_missing_annotation_panel_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            (root / smoke_user_flows.SGF_ANNOTATION_PANEL_SOURCE).unlink()

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("sgf_annotation_surface", failures)
            self.assertIn("SgfAnnotationPanel source", failures["sgf_annotation_surface"])

    def test_runtime_asset_layout_surface_passes_with_frontend_wiring(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            passes = {result.name for result in results if result.status == "PASS"}
            self.assertNotIn("runtime_asset_layout_surface", failures)
            self.assertIn("runtime_asset_layout_surface", passes)

    def test_runtime_asset_layout_surface_missing_engine_setup_ui_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, runtime_asset_ui=False)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("runtime_asset_layout_surface", failures)
            self.assertIn("EngineSetupPanel missing runtimeAssetValidation", failures["runtime_asset_layout_surface"])

    def test_legacy_import_capture_helper_surface_passes_with_frontend_wiring(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            passes = {result.name for result in results if result.status == "PASS"}
            self.assertNotIn("legacy_import_capture_helper_surface", failures)
            self.assertIn("legacy_import_capture_helper_surface", passes)

    def test_legacy_import_capture_helper_surface_missing_unsupported_boundary_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, legacy_helper_ui=False)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("legacy_import_capture_helper_surface", failures)
            self.assertIn("ProviderPanel missing legacy-helper-ocr-unsupported", failures["legacy_import_capture_helper_surface"])

    def test_legacy_import_capture_helper_surface_missing_api_wrapper_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, legacy_helper_api=False)

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("legacy_import_capture_helper_surface", failures)
            self.assertIn("provider API missing previewLegacyImportCaptureHelper", failures["legacy_import_capture_helper_surface"])

    def test_legacy_import_capture_helper_surface_missing_rust_command_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, omitted_commands={smoke_user_flows.LEGACY_IMPORT_CAPTURE_HELPER_COMMAND})

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("legacy_import_capture_helper_surface", failures)
            self.assertIn("legacy_import_capture_helper function", failures["legacy_import_capture_helper_surface"])
            self.assertIn("legacy_import_capture_helper invoke handler", failures["legacy_import_capture_helper_surface"])

    def test_legacy_import_capture_helper_surface_wrong_api_invoke_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root, legacy_helper_api_command="legacy_capture_external_window")

            results = smoke_user_flows.UserFlowSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("legacy_import_capture_helper_surface", failures)
            self.assertIn(
                "provider API previewLegacyImportCaptureHelper must invoke legacy_import_capture_helper",
                failures["legacy_import_capture_helper_surface"],
            )

    def test_edit_existing_move_surface_reduced_fixture_all_frontend_sources_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_complete_smoke_fixture(root)
            for rel in (
                smoke_user_flows.BACKEND_SOURCE,
                smoke_user_flows.APP_SOURCE,
                smoke_user_flows.SGF_TREE_PANEL_SOURCE,
                smoke_user_flows.PREFERENCES_PANEL_SOURCE,
            ):
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
    preferences_migration_ui: bool = True,
    preferences_migration_safety_ui: bool = True,
    runtime_asset_ui: bool = True,
    legacy_helper_ui: bool = True,
    legacy_helper_api: bool = True,
    legacy_helper_api_command: str = smoke_user_flows.LEGACY_IMPORT_CAPTURE_HELPER_COMMAND,
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
        smoke_user_flows.LEGACY_IMPORT_CAPTURE_HELPER_COMMAND,
        "native_menu_contract",
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
        const NATIVE_MENU_EVENT_NAME: &str = "{smoke_user_flows.NATIVE_MENU_EVENT_NAME}";

        struct NativeMenuActionSpec {{
            menu_id: &'static str,
            action_id: &'static str,
            target_id: &'static str,
            label: &'static str,
            menu_path: &'static [&'static str],
            accelerator: Option<&'static str>,
        }}

        const NATIVE_MENU_ACTIONS: &[NativeMenuActionSpec] = &[
{native_menu_actions_fixture_source()}
        ];

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
    create_sgf_annotation_panel_fixture(root)
    create_runtime_smoke_fixture(root)
    create_preferences_panel_fixture(root, migration_ui=preferences_migration_ui, migration_safety_ui=preferences_migration_safety_ui)
    create_engine_setup_panel_fixture(root, runtime_asset_ui=runtime_asset_ui)
    create_provider_domain_fixture(root)
    create_provider_api_fixture(root, legacy_helper_api=legacy_helper_api, legacy_helper_api_command=legacy_helper_api_command)
    create_provider_panel_fixture(root, legacy_helper_ui=legacy_helper_ui)


def write_valid_tauri_runtime_ui_evidence(root: Path) -> None:
    write_json(root / smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_EVIDENCE, valid_tauri_runtime_ui_evidence())


def write_valid_desktop_sgf_editing_ux_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.DESKTOP_SGF_EDITING_UX_SMOKE_EVIDENCE,
        valid_desktop_sgf_editing_ux_evidence(),
    )


def write_valid_desktop_ui_click_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.DESKTOP_UI_CLICK_SMOKE_EVIDENCE,
        valid_desktop_ui_click_evidence(),
    )


def write_valid_native_menu_shortcut_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.NATIVE_MENU_SHORTCUT_SMOKE_EVIDENCE,
        valid_native_menu_shortcut_evidence(),
    )


def write_valid_tauri_window_runtime_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.TAURI_WINDOW_RUNTIME_SMOKE_EVIDENCE,
        valid_tauri_window_runtime_evidence(),
    )


def write_valid_tauri_webview_dom_click_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.TAURI_WEBVIEW_DOM_CLICK_SMOKE_EVIDENCE,
        valid_tauri_webview_dom_click_evidence(),
    )


def write_valid_legacy_layout_parity_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.LEGACY_LAYOUT_PARITY_SMOKE_EVIDENCE,
        valid_legacy_layout_parity_evidence(),
    )


def write_valid_installed_macos_app_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.INSTALLED_MACOS_APP_SMOKE_EVIDENCE,
        valid_installed_macos_app_evidence(),
    )


def write_valid_installed_app_runtime_workflow_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.INSTALLED_APP_RUNTIME_WORKFLOW_EVIDENCE,
        valid_installed_app_runtime_workflow_evidence(),
    )


def write_valid_installed_app_sgf_workflow_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.INSTALLED_APP_SGF_WORKFLOW_EVIDENCE,
        valid_installed_app_sgf_workflow_evidence(),
    )


def write_valid_native_desktop_sgf_workflow_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.NATIVE_DESKTOP_SGF_WORKFLOW_EVIDENCE,
        valid_native_desktop_sgf_workflow_evidence(),
    )


def write_valid_katago_live_evidence(root: Path) -> None:
    write_json(root / smoke_user_flows.KATAGO_LIVE_SMOKE_EVIDENCE, valid_katago_live_evidence())


def write_valid_katago_tauri_runtime_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.KATAGO_TAURI_RUNTIME_SMOKE_EVIDENCE,
        valid_katago_tauri_runtime_evidence(),
    )


def write_valid_katago_review_workflow_ux_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.KATAGO_REVIEW_WORKFLOW_UX_SMOKE_EVIDENCE,
        valid_katago_review_workflow_ux_evidence(),
    )


def write_valid_legacy_config_corpus_migration_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_EVIDENCE,
        valid_legacy_config_corpus_migration_evidence(),
    )


def write_valid_katago_live_desktop_workflow_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.KATAGO_LIVE_DESKTOP_WORKFLOW_SMOKE_EVIDENCE,
        valid_katago_live_desktop_workflow_evidence(),
    )


def write_valid_installed_app_katago_live_workflow_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.INSTALLED_APP_KATAGO_LIVE_WORKFLOW_EVIDENCE,
        valid_installed_app_katago_live_workflow_evidence(),
    )


def write_valid_readboard_tauri_runtime_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.READBOARD_TAURI_RUNTIME_SMOKE_EVIDENCE,
        valid_readboard_tauri_runtime_evidence(),
    )


def write_valid_readboard_image_import_evidence(root: Path) -> None:
    create_readboard_controlled_board_fixture(root)
    write_json(
        root / smoke_user_flows.READBOARD_IMAGE_IMPORT_SMOKE_EVIDENCE,
        valid_readboard_image_import_evidence(),
    )


def write_valid_readboard_image_ocr_corpus_evidence(root: Path) -> None:
    create_readboard_ocr_corpus_fixtures(root)
    write_json(
        root / smoke_user_flows.READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE,
        valid_readboard_image_ocr_corpus_evidence(),
    )


def write_valid_readboard_external_capture_mvp_evidence(root: Path) -> None:
    create_readboard_controlled_board_fixture(root)
    write_json(
        root / smoke_user_flows.READBOARD_EXTERNAL_CAPTURE_MVP_EVIDENCE,
        valid_readboard_external_capture_mvp_evidence(),
    )


def write_valid_provider_live_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.PROVIDER_LIVE_SMOKE_EVIDENCE,
        valid_provider_live_evidence(),
    )


def write_valid_multiplatform_packaging_evidence(root: Path) -> None:
    write_json(
        root / smoke_user_flows.MULTIPLATFORM_PACKAGING_SMOKE_EVIDENCE,
        valid_multiplatform_packaging_evidence(),
    )


def create_readboard_controlled_board_fixture(root: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "docs/qa/fixtures/readboard-controlled-board.png"
    target = root / "docs/qa/fixtures/readboard-controlled-board.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


def create_readboard_ocr_corpus_fixtures(root: Path) -> None:
    source_root = Path(__file__).resolve().parents[1] / "tests/fixtures/readboard-images"
    for filename in (
        "controlled-19-three-stones.ppm",
        "controlled-13-five-stones.ppm",
        "non-board.ppm",
        "invalid-image.bin",
        "truncated-corrupt.ppm",
    ):
        source = source_root / filename
        target = root / "tests/fixtures/readboard-images" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


def canonical_legacy_actions() -> list[dict[str, object]]:
    return [
        {"id": "file.open", "group": "File", "label": "Open", "shortcut": "Mod+O"},
        {"id": "file.save", "group": "File", "label": "Save", "shortcut": "Mod+S"},
        {"id": "file.saveAs", "group": "File", "label": "Save As", "shortcut": "Mod+Shift+S"},
        {"id": "file.importSgf", "group": "File", "label": "Import SGF", "shortcut": "Mod+I"},
        {"id": "game.loadSample", "group": "Game", "label": "Load sample", "shortcut": "Mod+Shift+L"},
        {"id": "game.parseSgf", "group": "Game", "label": "Parse SGF", "shortcut": "Mod+Enter"},
        {"id": "analysis.runReview", "group": "Analysis", "label": "Run review", "shortcut": "Mod+R"},
        {"id": "analysis.katagoPanel", "group": "Analysis", "label": "KataGo panel", "target": "profiles", "shortcut": "Mod+Shift+K"},
        {"id": "view.candidates", "group": "View", "label": "Candidates", "target": "candidates", "shortcut": "Mod+1"},
        {"id": "view.ownership", "group": "View", "label": "Ownership", "target": "ownership", "shortcut": "Mod+2"},
        {"id": "view.policy", "group": "View", "label": "Policy", "target": "policy", "shortcut": "Mod+3"},
        {"id": "engine.profiles", "group": "Engine", "label": "Profiles", "target": "profiles", "shortcut": "Mod+4"},
        {"id": "engine.assets", "group": "Engine", "label": "Assets", "target": "assets", "shortcut": "Mod+5"},
        {"id": "tools.providers", "group": "Tools", "label": "Providers", "target": "providers", "shortcut": "Mod+6"},
        {"id": "tools.preferences", "group": "Tools", "label": "Preferences", "target": "preferences", "shortcut": "Mod+7"},
        {"id": "help.backendStatus", "group": "Help", "label": "Backend status", "target": "backend-status", "shortcut": "Mod+/"},
    ]


def native_menu_actions_fixture_source() -> str:
    blocks: list[str] = []
    for action in canonical_legacy_actions():
        action_id = str(action["id"])
        group = str(action["group"])
        label = str(action["label"])
        menu_id = "legacy-menu-" + action_id.replace(".", "-").replace("Sgf", "-sgf").replace("As", "-as").replace("Sample", "-sample").replace("Review", "-review").replace("Panel", "-panel").replace("Status", "-status").lower()
        target = str(action.get("target") or action_id.split(".")[-1])
        blocks.append(
            f"""
            NativeMenuActionSpec {{
                menu_id: "{menu_id}",
                action_id: "{action_id}",
                target_id: "{target}",
                label: "{label}",
                menu_path: &["{group}", "{label}"],
                accelerator: None,
            }},
            """
        )
    return "\n".join(blocks)


def valid_katago_live_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.KATAGO_LIVE_SMOKE_SCHEMA,
        "name": "katago_live_smoke",
        "status": "pass",
        "platform": "macos",
        "engine": {
            "path": "<katago-engine>",
            "modelPath": "<katago-model>",
            "configPath": "<katago-config>",
            "maxVisits": 1,
            "timeoutSeconds": 120,
        },
        "checks": [
            {
                "name": "engine_assets",
                "status": "pass",
                "details": {
                    "engineExecutable": True,
                    "modelBytes": 12,
                    "configBytes": 10,
                },
            },
            {
                "name": "version_probe",
                "status": "pass",
                "details": {"exitCode": 0, "versionText": "KataGo fake"},
            },
            {
                "name": "one_position_analysis",
                "status": "pass",
                "details": {
                    "id": "katago-live-smoke-one",
                    "moveInfoCount": 2,
                    "hasRootInfo": True,
                    "hasOwnership": True,
                    "hasPolicy": True,
                },
            },
            {
                "name": "batch_analysis",
                "status": "pass",
                "details": {
                    "responseCount": 2,
                    "responses": [
                        {"id": "katago-live-smoke-batch-1", "moveInfoCount": 1, "hasRootInfo": True},
                        {"id": "katago-live-smoke-batch-2", "moveInfoCount": 1, "hasRootInfo": True},
                    ],
                },
            },
            {
                "name": "stderr_capture",
                "status": "pass",
                "details": {"stderrCaptured": True, "onePositionStderrBytes": 0, "batchStderrBytes": 0},
            },
        ],
    }


def valid_katago_tauri_runtime_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.KATAGO_TAURI_RUNTIME_SMOKE_SCHEMA,
        "name": "katago_tauri_runtime_smoke",
        "status": "pass",
        "platform": "macos",
        "checks": [
            {
                "name": "runtime_started",
                "status": "pass",
                "details": {"tauriInternals": True, "platform": "MacIntel"},
            },
            {
                "name": "katago_assets",
                "status": "pass",
                "details": {"engineExists": True, "modelBytes": 12, "configBytes": 10},
            },
            {
                "name": "katago_failure_mode_missing_assets",
                "status": "pass",
                "details": {"observed": True, "missingRequired": ["model", "config"]},
            },
            {
                "name": "katago_analyze_once",
                "status": "pass",
                "details": {"frameCount": 1, "candidateCount": 2, "hasRootInfo": True},
            },
            {
                "name": "katago_analyze_game",
                "status": "pass",
                "details": {"frameCount": 2, "candidateCount": 2, "hasRootInfo": True},
            },
            {
                "name": "katago_start_cancel",
                "status": "pass",
                "details": {"jobId": "job-1", "cancelRequested": True, "cancelConfirmed": True},
            },
        ],
    }


def valid_katago_review_workflow_ux_evidence() -> dict[str, object]:
    false_boundaries = {
        key: False
        for key in smoke_user_flows.KATAGO_REVIEW_WORKFLOW_UX_REQUIRED_FALSE_FIELDS
    }
    return {
        "schema": smoke_user_flows.KATAGO_REVIEW_WORKFLOW_UX_SMOKE_SCHEMA,
        "name": "scoped_katago_review_workflow_ux_resilience",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "source_static_plus_stubbed_ui_flow",
        "progressVerified": True,
        "cancelVerified": True,
        "restartAfterCancelVerified": True,
        "cacheRestoreVerified": True,
        "engineFailureVerified": True,
        "staleAnalysisPrevented": True,
        "sourceFactsValidated": True,
        **false_boundaries,
        "checks": [
            {
                "name": "progress_verified",
                "status": "pass",
                "details": {
                    "progressVerified": True,
                    "jobIdVisible": True,
                    "currentVisible": True,
                    "totalVisible": True,
                    "sessionVisible": True,
                    "stubbedProgress": "job katago-job-1, move 2, 1/3 positions",
                },
            },
            {
                "name": "cancel_verified",
                "status": "pass",
                "details": {
                    "cancelVerified": True,
                    "cancelButtonVisible": True,
                    "cancelCommandStubbed": "katago_cancel_analysis",
                },
            },
            {
                "name": "restart_after_cancel_verified",
                "status": "pass",
                "details": {
                    "restartAfterCancelVerified": True,
                    "restartAllowedAfterCancel": True,
                    "activeJobCleared": True,
                },
            },
            {
                "name": "cache_restore_verified",
                "status": "pass",
                "details": {
                    "cacheRestoreVerified": True,
                    "cacheHitRestoredFrames": True,
                    "source": "stubbed_cache_hit_restore",
                },
            },
            {
                "name": "engine_failure_verified",
                "status": "pass",
                "details": {
                    "engineFailureVerified": True,
                    "failureMessageVisible": True,
                    "message": "Full-game KataGo analysis failed: stubbed missing model",
                },
            },
            {
                "name": "stale_analysis_prevented",
                "status": "pass",
                "details": {
                    "staleAnalysisPrevented": True,
                    "jobIdGuard": True,
                    "generationGuard": False,
                    "hashGuard": True,
                },
            },
            {
                "name": "source_facts_validated",
                "status": "pass",
                "details": {
                    "sourceFactsValidated": True,
                    "frontendSources": [
                        smoke_user_flows.APP_SOURCE,
                        smoke_user_flows.ENGINE_SETUP_PANEL_SOURCE,
                        smoke_user_flows.BACKEND_SOURCE,
                    ],
                },
            },
            {
                "name": "scope_boundaries",
                "status": "pass",
                "details": {
                    **false_boundaries,
                    "boundary": "No live KataGo runtime, full legacy analysis parity, provider/readboard/OCR, release, or Windows/Linux claims.",
                },
            },
        ],
        "boundaries": false_boundaries,
        "sourceEvidence": {
            "referencedEvidence": [],
            "existingLiveEvidenceUsedForNewLiveBehavior": False,
        },
    }


def valid_legacy_config_corpus_migration_evidence() -> dict[str, object]:
    fixture_classes = list(smoke_user_flows.LEGACY_CONFIG_CORPUS_REQUIRED_FIXTURE_CLASSES)
    false_boundaries = {
        key: False
        for key in smoke_user_flows.LEGACY_CONFIG_CORPUS_REQUIRED_FALSE_FIELDS
    }
    required_true = {
        key: True
        for key in smoke_user_flows.LEGACY_CONFIG_CORPUS_REQUIRED_TRUE_FIELDS
    }
    return {
        "schema": smoke_user_flows.LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_SCHEMA,
        "name": "legacy_config_corpus_migration_smoke",
        "status": "pass",
        "collectionMethod": "source_static_plus_repository_fixture_corpus",
        "corpusFixtureCount": len(fixture_classes),
        "fixtureClasses": fixture_classes,
        **required_true,
        **false_boundaries,
        "fixtures": [
            {"name": fixture_class, "class": fixture_class, "status": "pass"}
            for fixture_class in fixture_classes
        ],
        "checks": [
            {
                "name": "fixture_corpus_covered",
                "status": "pass",
                "details": {
                    "corpusFixtureCount": len(fixture_classes),
                    "fixtureClasses": fixture_classes,
                },
            },
            {
                "name": "preview_no_write",
                "status": "pass",
                "details": {"previewNoWrite": True},
            },
            {
                "name": "apply_writes_intended_targets",
                "status": "pass",
                "details": {"applyWritesIntendedTargets": True},
            },
            {
                "name": "preserves_existing_next_settings",
                "status": "pass",
                "details": {"preservesExistingNextSettings": True},
            },
            {
                "name": "invalid_no_write",
                "status": "pass",
                "details": {"invalidNoWrite": True},
            },
            {
                "name": "unsupported_keys_warned",
                "status": "pass",
                "details": {"unsupportedKeysWarned": True},
            },
            {
                "name": "duplicate_conflict_deterministic",
                "status": "pass",
                "details": {"duplicateConflictDeterministic": True},
            },
            {
                "name": "rollback_metadata_observed",
                "status": "pass",
                "details": {"rollbackMetadataObserved": True},
            },
            {
                "name": "scope_boundaries_recorded",
                "status": "pass",
                "details": false_boundaries,
            },
        ],
        "boundaries": false_boundaries,
    }


def valid_katago_live_desktop_workflow_evidence() -> dict[str, object]:
    false_boundaries = {
        key: False
        for key in smoke_user_flows.KATAGO_LIVE_DESKTOP_WORKFLOW_REQUIRED_FALSE_FIELDS
    }
    return {
        "schema": smoke_user_flows.KATAGO_LIVE_DESKTOP_WORKFLOW_SMOKE_SCHEMA,
        "name": "katago_live_desktop_workflow_smoke",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "tauri_live_katago_desktop_workflow",
        "liveKataGoObserved": True,
        "browserFallbackUsed": False,
        **false_boundaries,
        "runtimeMetadata": {
            "enginePath": "<katago-engine>",
            "modelPath": "<katago-model>",
            "configPath": "<katago-config>",
            "katagoVersion": "KataGo fake",
        },
        "checks": [
            {
                "name": "runtime_started",
                "status": "pass",
                "details": {"tauriInternals": True, "platform": "MacIntel"},
            },
            {
                "name": "engine_assets_verified",
                "status": "pass",
                "details": {"engineExecutable": True, "modelBytes": 12, "configBytes": 10},
            },
            {
                "name": "analysis_progress_observed",
                "status": "pass",
                "details": {
                    "analysisProgressObserved": True,
                    "jobId": "katago-live-job-1",
                    "completed": 1,
                    "expected": 3,
                    "frameCount": 1,
                },
            },
            {
                "name": "cancel_observed",
                "status": "pass",
                "details": {
                    "jobId": "katago-live-job-1",
                    "cancelRequested": True,
                    "cancelObserved": True,
                },
            },
            {
                "name": "restart_after_cancel_observed",
                "status": "pass",
                "details": {
                    "restartAfterCancelObserved": True,
                    "cancelledJobId": "katago-live-job-1",
                    "restartJobId": "katago-live-job-2",
                },
            },
            {
                "name": "analysis_complete_observed",
                "status": "pass",
                "details": {
                    "analysisCompleteObserved": True,
                    "jobId": "katago-live-job-2",
                    "frameCount": 3,
                    "candidateCount": 2,
                    "winrate": 0.51,
                },
            },
            {
                "name": "cache_saved",
                "status": "pass",
                "details": {
                    "cacheSaved": True,
                    "cacheKey": "game-cache-key-1",
                    "frameCount": 3,
                },
            },
            {
                "name": "cache_hit_restored",
                "status": "pass",
                "details": {
                    "cacheHitRestored": True,
                    "cacheKey": "game-cache-key-1",
                    "frameCount": 3,
                    "candidateCount": 2,
                    "winrateRestored": 0.51,
                },
            },
            {
                "name": "stale_cache_prevented",
                "status": "pass",
                "details": {
                    "staleCachePrevented": True,
                    "jobIdGuard": True,
                    "hashGuard": True,
                },
            },
            {
                "name": "engine_failure_observed",
                "status": "pass",
                "details": {
                    "engineFailureObserved": True,
                    "message": "Live KataGo workflow smoke observed missing model failure",
                },
            },
            {
                "name": "browser_fallback_excluded",
                "status": "pass",
                "details": {"browserFallbackUsed": False},
            },
            {
                "name": "scope_boundaries_recorded",
                "status": "pass",
                "details": {
                    **false_boundaries,
                    "browserFallbackUsed": False,
                    "boundary": "Scoped live desktop workflow only; no full analysis/provider/readboard/release/OCR parity claims.",
                },
            },
        ],
        "boundaries": {**false_boundaries, "browserFallbackUsed": False},
    }


def valid_installed_app_katago_live_workflow_evidence() -> dict[str, object]:
    boundaries = {
        key: False
        for key in smoke_user_flows.INSTALLED_APP_KATAGO_LIVE_WORKFLOW_REQUIRED_FALSE_FIELDS
    }
    metadata = valid_installed_app_katago_live_metadata()
    screenshot = {
        "label": "installed-app-katago-live-window",
        "path": "docs/qa/screenshots/installed-app-katago-live-window.png",
        "sizeBytes": 23456,
        "sha256": "a" * 64,
        "source": "installed_app_katago_live_workflow",
    }
    source_report = valid_installed_app_katago_live_runtime_report()
    checks = [
        {"name": "installed_app_launched", "status": "pass", "details": {"installedAppLaunched": True}},
        {
            "name": "runtime_report_observed",
            "status": "pass",
            "details": {
                "phase": smoke_user_flows.INSTALLED_APP_KATAGO_LIVE_WORKFLOW_PHASE,
                "status": "pass",
                "liveKataGoObserved": True,
            },
        },
        *[
            {"name": name, "status": "pass", "details": find_evidence_check(source_report, name)["details"]}
            for name in [
                "runtime_started",
                "analysis_progress_observed",
                "cancel_observed",
                "restart_after_cancel_observed",
                "analysis_complete_observed",
                "cache_saved",
                "cache_hit_restored",
                "stale_cache_prevented",
                "engine_failure_observed",
                "browser_fallback_excluded",
            ]
        ],
        {
            "name": "engine_assets_verified",
            "status": "pass",
            "details": {
                "realKataGoObserved": True,
                "observed": True,
                "engine": metadata["engine"],
                "model": metadata["model"],
                "config": metadata["config"],
                "maxVisits": metadata["maxVisits"],
                "katagoVersion": metadata["katagoVersion"],
                "missingRequired": [],
            },
        },
        {"name": "screenshot_hash_recorded", "status": "pass", "details": screenshot},
        {"name": "scope_boundaries_recorded", "status": "pass", "details": {"boundaries": boundaries}},
    ]
    return {
        "schema": smoke_user_flows.INSTALLED_APP_KATAGO_LIVE_WORKFLOW_SCHEMA,
        "name": "installed_app_katago_live_workflow",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "installed_packaged_app_live_katago_runtime_workflow",
        "runtimePhase": smoke_user_flows.INSTALLED_APP_KATAGO_LIVE_WORKFLOW_PHASE,
        "installedAppLaunched": True,
        "tauriRuntimeObserved": True,
        "liveKataGoObserved": True,
        "sourceStaticOnly": False,
        "browserFallbackUsed": False,
        "devServerOnly": False,
        **boundaries,
        "appBundlePath": "target/release/bundle/macos/LizzieYzy Next.app",
        "appBundle": {
            "exists": True,
            "path": "target/release/bundle/macos/LizzieYzy Next.app",
            "sizeBytes": 123456,
            "sha256": "b" * 64,
            "mainExecutable": "lizzieyzy-next-desktop",
        },
        "runtimeProcess": {"observed": True, "processName": "LizzieYzy Next", "pid": 1234},
        "runtimeMetadata": metadata,
        "sourceRuntimeReport": source_report,
        "screenshots": [screenshot],
        "checks": checks,
        "boundaries": boundaries,
    }


def valid_installed_app_katago_live_metadata() -> dict[str, object]:
    return {
        "engine": {
            "kind": "katago-engine",
            "path": "<home>/.local/bin/katago",
            "sizeBytes": 1234567,
            "sha256": "1" * 64,
        },
        "model": {
            "kind": "katago-model",
            "path": "<home>/.katago/models/latest-kata1.bin.gz",
            "sizeBytes": 2345678,
            "sha256": "2" * 64,
        },
        "config": {
            "kind": "katago-config",
            "path": "<home>/.katago/configs/analysis_example.cfg",
            "sizeBytes": 3456,
            "sha256": "3" * 64,
        },
        "maxVisits": 16,
        "katagoVersion": "KataGo 1.15.3",
    }


def valid_installed_app_katago_live_runtime_report() -> dict[str, object]:
    checks = [
        {"name": "runtime_started", "status": "pass", "details": {"tauriInternals": True, "platform": "MacIntel"}},
        {
            "name": "backend_runtime_proof_observed",
            "status": "pass",
            "details": {"raw": valid_installed_app_backend_runtime_proof()},
        },
        {
            "name": "engine_assets_verified",
            "status": "pass",
            "details": {
                "realKataGoObserved": True,
                "observed": True,
                **valid_installed_app_katago_live_metadata(),
                "missingRequired": [],
            },
        },
        {
            "name": "analysis_progress_observed",
            "status": "pass",
            "details": {
                "analysisProgressObserved": True,
                "jobId": "installed-katago-job-1",
                "completed": 1,
                "expected": 3,
                "frameCount": 1,
            },
        },
        {
            "name": "cancel_observed",
            "status": "pass",
            "details": {"jobId": "installed-katago-job-1", "cancelRequested": True, "cancelObserved": True},
        },
        {
            "name": "restart_after_cancel_observed",
            "status": "pass",
            "details": {
                "restartAfterCancelObserved": True,
                "cancelledJobId": "installed-katago-job-1",
                "restartJobId": "installed-katago-job-2",
            },
        },
        {
            "name": "analysis_complete_observed",
            "status": "pass",
            "details": {
                "analysisCompleteObserved": True,
                "jobId": "installed-katago-job-2",
                "frameCount": 3,
                "candidateCount": 2,
                "winrate": 0.51,
            },
        },
        {
            "name": "cache_saved",
            "status": "pass",
            "details": {"cacheSaved": True, "cacheKey": "installed-katago-cache-1", "frameCount": 3},
        },
        {
            "name": "cache_hit_restored",
            "status": "pass",
            "details": {
                "cacheHitRestored": True,
                "cacheKey": "installed-katago-cache-1",
                "frameCount": 3,
                "candidateCount": 2,
                "winrateRestored": 0.51,
            },
        },
        {
            "name": "stale_cache_prevented",
            "status": "pass",
            "details": {"staleCachePrevented": True, "jobIdGuard": True, "hashGuard": True},
        },
        {
            "name": "engine_failure_observed",
            "status": "pass",
            "details": {"engineFailureObserved": True, "message": "missing model failure observed"},
        },
        {"name": "browser_fallback_excluded", "status": "pass", "details": {"browserFallbackUsed": False}},
        {
            "name": "scope_boundaries_recorded",
            "status": "pass",
            "details": {"browserFallbackUsed": False, "releaseParity": False, "fullLegacyParity": False},
        },
    ]
    return {
        "schema": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_SCHEMA,
        "status": "pass",
        "platform": "macos",
        "phase": smoke_user_flows.INSTALLED_APP_KATAGO_LIVE_WORKFLOW_PHASE,
        "liveKataGoObserved": True,
        "browserFallbackUsed": False,
        "checks": checks,
    }


def valid_readboard_tauri_runtime_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.READBOARD_TAURI_RUNTIME_SMOKE_SCHEMA,
        "name": "readboard_tauri_runtime_smoke",
        "status": "pass",
        "platform": "macos",
        "checks": [
            {
                "name": "runtime_started",
                "status": "pass",
                "details": {"tauriInternals": True, "platform": "MacIntel"},
            },
            {
                "name": "sidecar_probe_ready",
                "status": "pass",
                "details": {
                    "available": True,
                    "state": "ready",
                    "endpoint": "http://127.0.0.1:12345",
                    "version": "readboard-runtime-smoke",
                },
            },
            {
                "name": "sidecar_probe_unavailable",
                "status": "pass",
                "details": {
                    "available": False,
                    "state": "unavailable",
                    "errorKind": "unavailable",
                    "message": "readboard sidecar unavailable at probe endpoint",
                },
            },
            {
                "name": "protocol_line_sync",
                "status": "pass",
                "details": {
                    "snapshotId": "readboard-smoke-snapshot-001",
                    "boardSize": 19,
                    "moveNumber": 12,
                    "stoneCount": 12,
                    "toPlay": "black",
                    "source": "protocol_line",
                },
            },
            {
                "name": "target_state_change_sync",
                "status": "pass",
                "details": {
                    "changed": True,
                    "beforeSnapshotId": "readboard-smoke-snapshot-001",
                    "afterSnapshotId": "readboard-smoke-snapshot-002",
                    "beforeStoneCount": 12,
                    "afterStoneCount": 13,
                    "beforeMoveNumber": 12,
                    "afterMoveNumber": 13,
                    "boardSizeStable": True,
                },
            },
            {
                "name": "arbitrary_ocr_not_covered",
                "status": "pass",
                "details": {
                    "covered": False,
                    "controlledImageImportCoveredBySeparateGate": True,
                    "fullOcrParity": False,
                    "message": "Arbitrary screenshot OCR is not covered by this runtime probe/protocol smoke; controlled image import has separate evidence.",
                },
            },
            {
                "name": "external_capture_not_covered",
                "status": "pass",
                "details": {
                    "covered": False,
                    "externalWindowCaptureCovered": False,
                    "externalClientCaptureCovered": False,
                    "reason": "controlled protocol probe only; no real external client/window capture",
                },
            },
        ],
    }


def valid_readboard_image_import_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.READBOARD_IMAGE_IMPORT_SMOKE_SCHEMA,
        "name": "readboard_image_import_smoke",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "controlled_fixture_image_import",
        "imagePathImportVerified": True,
        "imageBase64ImportVerified": True,
        "invalidImageRejected": True,
        "nonBoardImageRejected": True,
        "snapshotVerified": True,
        "boardSizeVerified": True,
        "stoneCountVerified": True,
        "toPlayVerified": True,
        "protocolRegressionVerified": True,
        "fullOcrParity": False,
        "externalCaptureCovered": False,
        "checks": [
            {
                "name": "image_path_import",
                "status": "pass",
                "details": {
                    "imagePathImportVerified": True,
                    "source": "path",
                    "imagePath": "docs/qa/fixtures/readboard-controlled-board.png",
                    "imageSha256": "70cfecf5b5d5235e66a051c5208c2974fde34f0a28aaef5be33fcd8bc0f63d96",
                    "imageBytes": 522,
                    "snapshotId": "readboard-image-smoke-path-001",
                    "boardSize": 19,
                    "boardSizeVerified": True,
                    "stoneCount": 12,
                    "stoneCountVerified": True,
                    "toPlay": "black",
                    "toPlayVerified": True,
                },
            },
            {
                "name": "image_base64_import",
                "status": "pass",
                "details": {
                    "imageBase64ImportVerified": True,
                    "source": "base64",
                    "base64Bytes": 4096,
                    "snapshotId": "readboard-image-smoke-base64-001",
                    "boardSize": 19,
                    "boardSizeVerified": True,
                    "stoneCount": 12,
                    "stoneCountVerified": True,
                    "toPlay": "black",
                    "toPlayVerified": True,
                },
            },
            {
                "name": "invalid_image_rejected",
                "status": "pass",
                "details": {
                    "invalidImageRejected": True,
                    "reportedAsSuccess": False,
                    "errorKind": "invalid_image",
                    "message": "invalid image payload rejected",
                },
            },
            {
                "name": "non_board_image_rejected",
                "status": "pass",
                "details": {
                    "nonBoardImageRejected": True,
                    "reportedAsSuccess": False,
                    "errorKind": "no_board_detected",
                    "message": "controlled non-board image rejected because no board was detected",
                },
            },
            {
                "name": "snapshot_verified",
                "status": "pass",
                "details": {
                    "snapshotVerified": True,
                    "snapshotId": "readboard-image-smoke-snapshot-001",
                    "boardSize": 19,
                    "boardSizeVerified": True,
                    "stoneCount": 12,
                    "stoneCountVerified": True,
                    "toPlay": "black",
                    "toPlayVerified": True,
                },
            },
            {
                "name": "protocol_regression",
                "status": "pass",
                "details": {
                    "protocolRegressionVerified": True,
                    "protocolLineCompatible": True,
                    "snapshotMatchesProtocol": True,
                },
            },
            {
                "name": "scope_boundaries",
                "status": "pass",
                "details": {
                    "fullOcrParity": False,
                    "externalCaptureCovered": False,
                    "boundary": "Controlled fixture image import MVP only; no arbitrary OCR or external capture claim.",
                },
            },
        ],
    }


def valid_readboard_image_ocr_corpus_evidence() -> dict[str, object]:
    valid_19 = {
        "path": "tests/fixtures/readboard-images/controlled-19-three-stones.ppm",
        "sha256": "1c910bea940043ee171b36dbc9ad3d6c9365d7b317f437b563be84e8583e3f0d",
        "sizeBytes": 480015,
        "boardSize": 19,
        "stoneCount": 3,
    }
    valid_13 = {
        "path": "tests/fixtures/readboard-images/controlled-13-five-stones.ppm",
        "sha256": "e46c17570ee7debe79601b611c5f96504d7a7057677b819fe0aa88d924cc51b6",
        "sizeBytes": 480015,
        "boardSize": 13,
        "stoneCount": 5,
    }
    negative_fixtures = {
        "invalid": {
            "path": "tests/fixtures/readboard-images/invalid-image.bin",
            "sha256": "fa93dc5eb1c95fcf655bdcf745203738398b12c6915e2ae7c5b996fa31602938",
            "sizeBytes": 29,
            "expectedError": "ImageDecode",
        },
        "non-board": {
            "path": "tests/fixtures/readboard-images/non-board.ppm",
            "sha256": "c8b0b20ad8f9a7f562a77a5f26a09a215871a6a1791ce364a5375211177d4d92",
            "sizeBytes": 97215,
            "expectedError": "ImageLowConfidence",
        },
        "truncated": {
            "path": "tests/fixtures/readboard-images/truncated-corrupt.ppm",
            "sha256": "de4a4d71cf6a8fd6ce382cb16026ebf15f9e8f1b55efccb8748428f7b5295a01",
            "sizeBytes": 19443,
            "expectedError": "ImageDecode",
        },
    }

    def valid_fixture(name: str, metadata: dict[str, object]) -> dict[str, object]:
        return {
            "name": name,
            "expectedOutcome": "valid",
            **metadata,
        }

    def negative_fixture(name: str, outcome: str) -> dict[str, object]:
        return {
            "name": name,
            "expectedOutcome": outcome,
            **negative_fixtures[outcome],
        }

    return {
        "schema": smoke_user_flows.READBOARD_IMAGE_OCR_CORPUS_SMOKE_SCHEMA,
        "name": "readboard_image_ocr_corpus_smoke",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "controlled_fixture_image_ocr_corpus",
        "pathBase64EquivalenceVerified": True,
        "invalidImageRejected": True,
        "nonBoardImageRejected": True,
        "truncatedImageRejected": True,
        "boardSizeCoverageVerified": True,
        "stoneCountCoverageVerified": True,
        "hashInvariantsVerified": True,
        "externalCaptureUnsupportedContractVerified": True,
        "fullOcrParity": False,
        "externalWindowCaptureCovered": False,
        "realClientCaptureCovered": False,
        "fullReadboardParity": False,
        "fixtureManifest": [
            valid_fixture("controlled-19-three-stones", valid_19),
            valid_fixture("controlled-13-five-stones", valid_13),
            negative_fixture("invalid-image", "invalid"),
            negative_fixture("non-board", "non-board"),
            negative_fixture("truncated-corrupt", "truncated"),
        ],
        "checks": [
            {
                "name": "fixture_manifest",
                "status": "pass",
                "details": {
                    "fixtureCount": 5,
                    "outcomes": ["valid", "invalid", "non-board", "truncated"],
                },
            },
            {
                "name": "path_base64_equivalence",
                "status": "pass",
                "details": {
                    "pathBase64EquivalenceVerified": True,
                    "sameSnapshot": True,
                    "sameBoardSize": True,
                    "sameStoneCount": True,
                    "sameHash": True,
                    "pathFixture": valid_19["path"],
                    "base64Fixture": valid_19["path"],
                },
            },
            {
                "name": "invalid_image_rejected",
                "status": "pass",
                "details": {
                    "invalidImageRejected": True,
                    "reportedAsSuccess": False,
                    "errorKind": "invalid_image",
                    "message": "invalid image payload rejected",
                },
            },
            {
                "name": "non_board_image_rejected",
                "status": "pass",
                "details": {
                    "nonBoardImageRejected": True,
                    "reportedAsSuccess": False,
                    "errorKind": "no_board_detected",
                    "message": "controlled non-board image rejected because no board was detected",
                },
            },
            {
                "name": "truncated_image_rejected",
                "status": "pass",
                "details": {
                    "truncatedImageRejected": True,
                    "reportedAsSuccess": False,
                    "errorKind": "truncated_image",
                    "message": "truncated image payload rejected",
                },
            },
            {
                "name": "board_size_coverage",
                "status": "pass",
                "details": {
                    "boardSizeCoverageVerified": True,
                    "boardSizes": [13, 19],
                },
            },
            {
                "name": "stone_count_coverage",
                "status": "pass",
                "details": {
                    "stoneCountCoverageVerified": True,
                    "stoneCounts": [3, 5],
                },
            },
            {
                "name": "hash_invariants",
                "status": "pass",
                "details": {
                    "hashInvariantsVerified": True,
                    "pathSha256Stable": True,
                    "base64Sha256Stable": True,
                    "pathBase64Sha256Equal": True,
                },
            },
            {
                "name": "external_capture_unsupported_contract",
                "status": "pass",
                "details": {
                    "externalCaptureUnsupportedContractVerified": True,
                    "externalWindowCaptureCovered": False,
                    "realClientCaptureCovered": False,
                    "reportedAsSuccess": False,
                    "message": "external window and real client capture remain unsupported in this scoped corpus",
                },
            },
            {
                "name": "scope_boundaries",
                "status": "pass",
                "details": {
                    "fullOcrParity": False,
                    "externalWindowCaptureCovered": False,
                    "realClientCaptureCovered": False,
                    "fullReadboardParity": False,
                    "boundary": "Controlled image OCR corpus only; arbitrary OCR and external client/window capture remain pending.",
                },
            },
        ],
    }


def valid_readboard_external_capture_mvp_evidence() -> dict[str, object]:
    boundaries = {
        "fullOcrParity": False,
        "fullReadboardParity": False,
        "externalClientCaptureCovered": False,
        "targetClientDiscoveryCovered": False,
        "realClientParity": False,
        "windowsLinuxCaptureCovered": False,
        "releaseParity": False,
    }
    capture_source = {
        "operatorInitiated": True,
        "userSelectionRequired": True,
        "sourceKind": "external_screen_region",
        "selection": {"x": 12, "y": 18, "width": 640, "height": 640},
        "targetClientDiscoveryCovered": False,
        "externalClientCaptureCovered": False,
    }
    artifact = {
        "path": "docs/qa/fixtures/readboard-controlled-board.png",
        "sizeBytes": 522,
        "sha256": "70cfecf5b5d5235e66a051c5208c2974fde34f0a28aaef5be33fcd8bc0f63d96",
        "sanitized": True,
    }
    decode = {
        "decodeAttempted": True,
        "decodeSucceeded": True,
        "boardSize": 19,
        "stoneCount": 3,
        "confidence": 0.99,
        "structuredResultProduced": True,
    }
    preview = {
        "previewOnlyBeforeConfirmation": True,
        "boardReplacedBeforeConfirmation": False,
        "userConfirmed": True,
        "boardReplacedOnlyAfterConfirmation": True,
    }
    structured = {
        "structuredResultVerified": True,
        "snapshotId": "readboard-external-capture-mvp-001",
        "boardSize": 19,
        "stoneCount": 3,
        "toPlay": "black",
        "boardReplaced": True,
        "replacementConfirmed": True,
    }
    return {
        "schema": smoke_user_flows.READBOARD_EXTERNAL_CAPTURE_MVP_SCHEMA,
        "name": "readboard_external_capture_mvp",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "runtime_backend_external_capture_mvp",
        "runtimeObserved": True,
        "backendCommandInvoked": True,
        "backendCommand": "readboard_external_capture",
        "operatorInitiated": True,
        "userSelectionRequired": True,
        "previewOnlyBeforeConfirmation": True,
        "boardReplacedOnlyAfterConfirmation": True,
        "sourceStaticOnly": False,
        **boundaries,
        "captureSource": capture_source,
        "structuredResult": structured,
        "captureArtifact": artifact,
        "decodeSummary": decode,
        "rawBackendResult": {
            "status": "captured",
            "snapshotId": "readboard-external-capture-mvp-001",
            "position": {
                "board_size": 19,
                "move_number": 0,
                "to_play": "black",
                "stones": [
                    {"color": "black", "point": "dd"},
                    {"color": "white", "point": "pq"},
                    {"color": "black", "point": "dp"},
                ],
            },
            "decode": {
                "attempted": True,
                "status": "success",
                "board_size": 19,
                "stone_count": 3,
                "blackStones": [{"point": "dd"}, {"point": "dp"}],
                "whiteStones": [{"point": "pq"}],
            },
        },
        "checks": [
            {"name": "capture_source_selected", "status": "pass", "details": capture_source},
            {"name": "capture_artifact_recorded", "status": "pass", "details": artifact},
            {"name": "decode_summary", "status": "pass", "details": decode},
            {"name": "preview_confirmation", "status": "pass", "details": preview},
            {"name": "structured_result", "status": "pass", "details": structured},
            {"name": "scope_boundaries", "status": "pass", "details": {"boundaries": boundaries}},
        ],
        "boundaries": boundaries,
    }


def valid_readboard_external_capture_mvp_unavailable_evidence() -> dict[str, object]:
    boundaries = {
        "fullOcrParity": False,
        "fullReadboardParity": False,
        "externalClientCaptureCovered": False,
        "targetClientDiscoveryCovered": False,
        "realClientParity": False,
        "windowsLinuxCaptureCovered": False,
        "releaseParity": False,
    }
    return {
        "schema": smoke_user_flows.READBOARD_EXTERNAL_CAPTURE_MVP_SCHEMA,
        "name": "readboard_external_capture_mvp",
        "status": "unavailable",
        "platform": "macos",
        "collectionMethod": "runtime_backend_external_capture_mvp",
        "pendingReason": "permission denied by operator",
        "runtimeObserved": True,
        "backendCommandInvoked": True,
        "backendCommand": "readboard_external_capture",
        "operatorInitiated": True,
        "userSelectionRequired": True,
        "previewOnlyBeforeConfirmation": True,
        "boardReplacedOnlyAfterConfirmation": False,
        "sourceStaticOnly": False,
        **boundaries,
        "rawBackendResult": {
            "status": "permission_denied",
            "message": "permission denied by operator",
        },
        "boundaries": boundaries,
    }


def valid_provider_live_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.PROVIDER_LIVE_SMOKE_SCHEMA,
        "name": "provider_live_smoke",
        "status": "pass",
        "platform": "macos",
        "checks": [
            {
                "name": "runtime_started",
                "status": "pass",
                "details": {"tauriInternals": True, "platform": "MacIntel"},
            },
            {
                "name": "yike_controlled_fetch",
                "status": "pass",
                "details": {
                    "provider": "yike",
                    "networkMode": "controlled_network",
                    "httpStatus": 200,
                    "payloadValidated": True,
                    "resultCount": 1,
                    "fixtureParserOnly": False,
                },
            },
            {
                "name": "fox_controlled_fetch",
                "status": "pass",
                "details": {
                    "provider": "fox",
                    "networkMode": "controlled_network",
                    "httpStatus": 302,
                    "payloadImported": True,
                    "moveCount": 42,
                    "directHttpWarning": True,
                },
            },
            {
                "name": "provider_failure_modes",
                "status": "pass",
                "details": {
                    "observed": True,
                    "typedProviderError": True,
                    "errorKind": "network",
                    "message": "controlled provider failure returned typed ProviderError",
                    "reportedAsSuccess": False,
                },
            },
            {
                "name": "controlled_network_observed",
                "status": "pass",
                "details": {
                    "controlledHttpServer": True,
                    "requestCount": 3,
                    "yikeSignedHeadersObserved": True,
                    "foxRequestObserved": True,
                    "failureRequestObserved": True,
                },
            },
            {
                "name": "offline_not_counted_as_external_live",
                "status": "pass",
                "details": {
                    "offlineParserOnly": False,
                    "controlledHttpServer": True,
                    "externalProviderServiceCovered": False,
                },
            },
            {
                "name": "external_account_scope",
                "status": "pass",
                "details": {
                    "realAccountLoginStateCovered": False,
                    "antiBotStabilityCovered": False,
                    "serviceSchemaDriftCovered": False,
                },
            },
        ],
    }


def valid_multiplatform_packaging_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.MULTIPLATFORM_PACKAGING_SMOKE_SCHEMA,
        "name": "multiplatform_packaging_smoke",
        "status": "pass",
        "checks": [
            packaging_artifact_check("macos", "LizzieYzy.app.tar.gz", "ad_hoc", "a" * 64),
            packaging_artifact_check("windows", "LizzieYzy-setup.exe", "unsigned", "b" * 64),
            packaging_artifact_check("linux", "LizzieYzy.AppImage", "unsigned", "c" * 64),
            {
                "name": "signing_recorded",
                "status": "pass",
                "details": {
                    "macos": {"checked": True, "status": "ad_hoc", "productionSigned": False},
                    "windows": {"checked": True, "status": "unsigned", "productionSigned": False},
                    "linux": {"checked": True, "status": "unsigned", "productionSigned": False},
                    "officialSigningCovered": False,
                },
            },
            {
                "name": "dev_server_absent",
                "status": "pass",
                "details": {
                    "macos": True,
                    "windows": True,
                    "linux": True,
                    "viteDevServerReferenced": False,
                },
            },
            {
                "name": "checksums",
                "status": "pass",
                "details": {
                    "entries": [
                        {
                            "platform": "macos",
                            "artifact": "LizzieYzy.app.tar.gz",
                            "artifactPresent": True,
                            "algorithm": "sha256",
                            "value": "a" * 64,
                        },
                        {
                            "platform": "windows",
                            "artifact": "LizzieYzy-setup.exe",
                            "artifactPresent": True,
                            "algorithm": "sha256",
                            "value": "b" * 64,
                        },
                        {
                            "platform": "linux",
                            "artifact": "LizzieYzy.AppImage",
                            "artifactPresent": True,
                            "algorithm": "sha256",
                            "value": "c" * 64,
                        },
                    ]
                },
            },
        ],
    }


def valid_native_menu_shortcut_evidence() -> dict[str, object]:
    false_boundaries = {
        "fullShortcutParity": False,
        "fullLegacyMenuParity": False,
        "webviewDomProof": False,
        "osNativeMenuFullParity": False,
        "releasePublished": False,
        "productionSigned": False,
        "notarized": False,
        "providerParityCovered": False,
        "readboardParityCovered": False,
        "ocrExternalCaptureCovered": False,
        "windowsLinuxCovered": False,
    }
    return {
        "schema": smoke_user_flows.NATIVE_MENU_SHORTCUT_SMOKE_SCHEMA,
        "name": "native_menu_shortcut_smoke",
        "status": "pass",
        "platform": "macos",
        "eventName": smoke_user_flows.NATIVE_MENU_EVENT_NAME,
        "groups": smoke_user_flows.NATIVE_MENU_GROUPS,
        "actionIds": [str(action["id"]) for action in canonical_legacy_actions()],
        "nativeMenuSurface": True,
        "nativeMenuEventBridge": True,
        "keyboardShortcutSurface": True,
        "actionIdsAligned": True,
        "inputEditingSafe": True,
        **false_boundaries,
        "checks": [
            {
                "name": "native_menu_surface",
                "status": "pass",
                "details": {
                    "nativeMenuSurface": True,
                    "menus": smoke_user_flows.NATIVE_MENU_GROUPS,
                },
            },
            {
                "name": "native_menu_event_bridge",
                "status": "pass",
                "details": {
                    "nativeMenuEventBridge": True,
                    "eventName": smoke_user_flows.NATIVE_MENU_EVENT_NAME,
                },
            },
            {
                "name": "keyboard_shortcut_surface",
                "status": "pass",
                "details": {
                    "keyboardShortcutSurface": True,
                    "shortcutCount": 8,
                },
            },
            {
                "name": "action_ids_aligned",
                "status": "pass",
                "details": {
                    "actionIdsAligned": True,
                    "sharedActionIds": ["open-sgf", "save-sgf", "toggle-candidates"],
                },
            },
            {
                "name": "input_editing_safe",
                "status": "pass",
                "details": {
                    "inputEditingSafe": True,
                    "textInputBypass": True,
                },
            },
            {
                "name": "scope_boundaries",
                "status": "pass",
                "details": false_boundaries,
            },
        ],
        "boundaries": {
            **false_boundaries,
            "providerCompleted": False,
            "readboardCompleted": False,
            "ocrCompleted": False,
            "windowsCovered": False,
            "linuxCovered": False,
        },
    }


def packaging_artifact_check(platform: str, artifact_name: str, signing_status: str, checksum: str) -> dict[str, object]:
    return {
        "name": f"{platform}_artifacts",
        "status": "pass",
        "details": {
            "platform": platform,
            "artifacts": [
                {
                    "artifactPresent": True,
                    "path": artifact_name,
                    "kind": "installer",
                    "sizeBytes": 1024,
                    "sha256": checksum,
                }
            ],
            "signing": {"checked": True, "status": signing_status, "productionSigned": False},
        },
    }


def valid_tauri_runtime_ui_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_SCHEMA,
        "status": "pass",
        "platform": "macos",
        "firstLaunch": {"phase": "edit-save", "stopped": True, "pid": 111},
        "secondLaunch": {"phase": "reopen-verify", "stopped": True, "pid": 222, "status": "pass"},
        "saveReopenProof": {
            "sameSgfPath": True,
            "distinctProcesses": True,
            "firstStoppedBeforeSecondStarted": True,
        },
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
    if name == "annotation_edit":
        return {
            "nodeId": "branch-1",
            "added": ["TR", "CR", "MA", "SL", "AR", "LN"],
            "updated": ["LB"],
            "removed": ["SQ"],
            "annotations": {
                "TR": ["aa"],
                "SQ": [],
                "CR": ["bb"],
                "MA": ["cc"],
                "SL": ["dd"],
                "LB": ["aa:A", "ee:E"],
                "AR": ["aa:bb"],
                "LN": ["cc:dd"],
            },
        }
    if name == "delete_node":
        return {"deletedNodeId": "variation-c", "existsAfterDelete": False}
    if name == "save_readback_roundtrip":
        return {
            "savedPath": "<tmp>/runtime-smoke.sgf",
            "readbackMatchesSaved": True,
            "secondLaunch": {"launchIndex": 2, "status": "pass"},
            "reopen": {"path": "<tmp>/runtime-smoke.sgf", "status": "pass", "matchesSaved": True},
            "afterReopen": {
                "treeOrderVerified": True,
                "commentsVerified": True,
                "propertiesVerified": True,
                "annotationsVerified": True,
                "moveCountVerified": True,
                "boardStateVerified": True,
            },
        }
    if name == "board_state_verified":
        return {"invariant": "replayed position count equals parsed move count plus initial position", "verified": True}
    return {"observed": True}


def valid_desktop_sgf_editing_ux_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.DESKTOP_SGF_EDITING_UX_SMOKE_SCHEMA,
        "name": "desktop_sgf_editing_ux_smoke",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "source_static_plus_tauri_runtime_chain",
        "runtimeDomObserved": False,
        "screenshotObserved": False,
        "sourceRuntimeEvidence": {
            "path": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_EVIDENCE,
            "schema": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_SCHEMA,
            "status": "pass",
            "valid": True,
        },
        "uiUxSurface": {
            "legacyShellVisible": True,
            "toolbarMenuControls": {
                "visible": True,
                "toolbarControls": ["Open", "Save", "Save As", "Import", "Sample", "Parse", "Review"],
                "menuControls": ["File/Open", "File/Save", "File/Save As", "View/Candidates", "Engine/Profiles", "Tools/Preferences"],
            },
            "treePanelVisible": True,
            "annotationEditorVisible": True,
            "selectedNodeUxState": {
                "selectedNodeVisible": True,
                "commentEditorVisible": True,
                "moveEditModeVisible": True,
                "deleteControlVisible": True,
                "reorderControlsVisible": True,
            },
            "dirtySavedStatus": {
                "dirtyIndicatorVisible": True,
                "savedIndicatorVisible": True,
                "canSaveReflectsDirty": True,
                "dirtySetAfterEdits": True,
                "savedAfterReadback": True,
            },
            "nativeDialogClickCovered": False,
        },
        "coverage": {
            "treeNavigation": True,
            "commentEdit": True,
            "propertyEdit": True,
            "annotationEdit": True,
            "appendMove": True,
            "editMove": True,
            "reorderVariation": True,
            "deleteNode": True,
            "saveReadbackReopen": True,
        },
        "boundaries": {
            "nativeDialogClickCovered": False,
            "fullNativeDialogProof": False,
            "ocrCaptureCovered": False,
            "externalClientWindowCaptureCovered": False,
            "fullLegacyParityCovered": False,
        },
        "checks": [
            {"name": name, "status": "pass", "details": {"covered": True}}
            for name in smoke_user_flows.DESKTOP_SGF_EDITING_UX_SMOKE_REQUIRED_CHECKS
        ],
    }


def valid_desktop_ui_click_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.DESKTOP_UI_CLICK_SMOKE_SCHEMA,
        "name": "desktop_ui_click_smoke",
        "status": "pass",
        "platform": "macos",
        "browserDomObserved": True,
        "screenshotObserved": True,
        "clickObserved": True,
        "screenshots": [
            {
                "label": "initial-workspace",
                "path": "docs/qa/screenshots/desktop-ui-click-initial.png",
                "sha256": "a" * 64,
            },
            {
                "label": "after-tree-click",
                "path": "docs/qa/screenshots/desktop-ui-click-after-tree.png",
                "sha256": "b" * 64,
            },
        ],
        "clickedControls": [
            {"label": "SGF tree node", "selector": ".sgf-tree-node", "clicked": True},
            {"label": "Save Comment", "selector": "button:has-text('Save Comment')", "clicked": True},
        ],
        "visibleAssertions": [
            {"label": "LegacyShell", "selector": "[data-testid='legacy-shell']", "visible": True, "status": "pass"},
            {"label": "SGF tree", "selector": ".sgf-tree-panel", "visible": True, "status": "pass"},
            {"label": "Annotation editor", "selector": ".sgf-annotation-editor", "visible": True, "status": "pass"},
        ],
        "legacyShellMenuActionSmoke": valid_legacy_shell_menu_action_smoke_section(),
        "boundaries": {
            "nativeFileDialogCovered": False,
            "tauriWebviewDomObserved": False,
            "fullNativeDialogProof": False,
            "fullLegacyParityCovered": False,
        },
    }


def valid_legacy_shell_menu_action_smoke_section() -> dict[str, object]:
    required = smoke_user_flows.LEGACY_SHELL_MENU_ACTION_REQUIRED_TARGETS
    return {
        "status": "pass",
        "clickedControls": [
            {
                "name": action,
                "group": action.split(":", 1)[0],
                "label": action.split(":", 1)[1],
                "target": target,
                "selector": f"[data-testid='legacy-menu-{action.split(':', 1)[0].lower()}-{action.split(':', 1)[1].lower().replace(' ', '-')}']",
                "clicked": True,
                "visible": True,
                "enabled": True,
            }
            for action, target in required
        ],
        "activeTargets": [
            {
                "name": action,
                "target": target,
                "selector": f"#legacy-menu-target-{target}",
                "visible": True,
                "active": True,
                "lastAction": action,
                "status": "focused",
            }
            for action, target in required
        ],
        "visibleAssertions": [
            {
                "name": f"{action} target",
                "target": target,
                "selector": f"#legacy-menu-target-{target}",
                "visible": True,
                "status": "pass",
            }
            for action, target in required
        ],
        "boundaries": {
            "browserRenderedDomObserved": True,
            "nativeFileDialogCovered": False,
            "tauriWebviewDomObserved": False,
            "tauriNativeDialogProof": False,
            "fullLegacyParityCovered": False,
            "osNativeMenuCovered": False,
            "fullShortcutParityCovered": False,
            "fullLayoutParityCovered": False,
        },
        "failures": [],
    }


def valid_tauri_window_runtime_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.TAURI_WINDOW_RUNTIME_SMOKE_SCHEMA,
        "name": "tauri_window_runtime_smoke",
        "status": "pass",
        "platform": "macos",
        "tauriRuntimeObserved": True,
        "tauriWindowScreenshotObserved": True,
        "browserFallbackUsed": False,
        "webviewDomClickCovered": False,
        "nativeDialogClickCovered": False,
        "boundaries": {
            "browserFallbackUsed": False,
            "webviewDomClickCovered": False,
            "nativeDialogClickCovered": False,
            "nativeFileDialogCovered": False,
        },
        "screenshots": [
            {
                "label": "tauri-window-after-reopen",
                "path": "docs/qa/screenshots/tauri-window-runtime-after-reopen.png",
                "sha256": "c" * 64,
            }
        ],
        "sourceRuntimeEvidence": {
            "path": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_EVIDENCE,
            "schema": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_SCHEMA,
            "status": "pass",
            "valid": True,
        },
        "firstLaunch": {"phase": "edit-save", "stopped": True, "pid": 111},
        "secondLaunch": {"phase": "reopen-verify", "stopped": True, "pid": 222, "status": "pass"},
        "saveReopenProof": {
            "sameSgfPath": True,
            "distinctProcesses": True,
            "firstStoppedBeforeSecondStarted": True,
        },
        "reopen": {"path": "<tmp>/runtime-smoke.sgf", "status": "pass", "matchesSaved": True},
        "afterReopen": {
            "treeOrderVerified": True,
            "commentsVerified": True,
            "propertiesVerified": True,
            "annotationsVerified": True,
            "moveCountVerified": True,
            "boardStateVerified": True,
        },
    }


def valid_tauri_webview_dom_click_evidence() -> dict[str, object]:
    clicked_controls = [
        {"label": "SGF tree node", "selector": ".sgf-tree-node", "clicked": True},
        {"label": "Save Comment", "selector": "button:has-text('Save Comment')", "clicked": True},
        {"label": "Annotation tab", "selector": ".sgf-annotation-editor", "clicked": True},
        {"label": "Run review", "selector": "[data-testid='legacy-menu-analysis-run-review']", "clicked": True},
    ]
    visible_assertions = [
        {"label": "LegacyShell", "selector": "[data-testid='legacy-shell']", "visible": True, "status": "pass"},
        {"label": "SGF tree", "selector": ".sgf-tree-panel", "visible": True, "status": "pass"},
        {"label": "Annotation editor", "selector": ".sgf-annotation-editor", "visible": True, "status": "pass"},
        {"label": "Board surface", "selector": "[data-testid='go-board']", "visible": True, "status": "pass"},
    ]
    boundaries = {
        "browserFallbackUsed": False,
        "fullLayoutParity": False,
        "fullShortcutParity": False,
        "fullLegacyParity": False,
        "releaseParity": False,
        "ocrCaptureParity": False,
    }
    return {
        "schema": smoke_user_flows.TAURI_WEBVIEW_DOM_CLICK_SMOKE_SCHEMA,
        "name": "tauri_webview_dom_click_smoke",
        "status": "pass",
        "platform": "macos",
        "tauriRuntimeObserved": True,
        "webviewDomObserved": True,
        "webviewClickObserved": True,
        "browserFallbackUsed": False,
        "fullLayoutParity": False,
        "fullShortcutParity": False,
        "fullLegacyParity": False,
        "releaseParity": False,
        "ocrCaptureParity": False,
        "clickedControls": clicked_controls,
        "visibleAssertions": visible_assertions,
        "checks": [
            {"name": "tauri_runtime_started", "status": "pass", "details": {"tauriRuntimeObserved": True}},
            {"name": "webview_dom_observed", "status": "pass", "details": {"webviewDomObserved": True}},
            {
                "name": "webview_click_observed",
                "status": "pass",
                "details": {"webviewClickObserved": True, "clickedControls": clicked_controls},
            },
            {
                "name": "visible_targets_verified",
                "status": "pass",
                "details": {"visibleAssertions": visible_assertions},
            },
            {"name": "browser_fallback_excluded", "status": "pass", "details": {"browserFallbackUsed": False}},
            {"name": "scope_boundaries_recorded", "status": "pass", "details": boundaries},
        ],
        "boundaries": boundaries,
    }


def valid_legacy_action_shortcut_matrix() -> list[dict[str, object]]:
    entries = [
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
            "disabledOrAvailability": "available or safely disabled depending current document state",
            "observedBy": ["runtime-click", "runtime-shortcut", "visible-target"],
            "visibleTargetAssertion": {
                "label": menu_path,
                "selector": target_selector,
                "visible": True,
                "status": "pass",
            },
        }
        for action_id, menu_path, shortcut, target_selector in entries
    ]


def valid_legacy_shortcut_layout_evidence() -> dict[str, object]:
    evidence = valid_legacy_layout_parity_evidence()
    evidence["schema"] = smoke_user_flows.LEGACY_SHORTCUT_LAYOUT_SCHEMA
    evidence["name"] = "legacy_shortcut_layout_evidence"
    return evidence


def runner_shaped_legacy_shortcut_layout_evidence() -> dict[str, object]:
    evidence = runner_shaped_legacy_layout_parity_evidence()
    evidence["schema"] = smoke_user_flows.LEGACY_SHORTCUT_LAYOUT_SCHEMA
    evidence["name"] = "legacy_shortcut_layout_evidence"
    return evidence


def static_only_legacy_shortcut_layout_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.LEGACY_SHORTCUT_LAYOUT_SCHEMA,
        "name": "legacy_shortcut_layout_evidence",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "source_static_plus_browser_rendered_evidence_summary",
        "runtimeSource": "source_static_summary",
        "sourceFacts": {"legacyShell": True},
        "actionMatrix": [],
        "browserEvidence": {"visibleTargets": ["legacy shell"]},
        "screenshot": {"path": "docs/qa/screenshots/legacy-shortcut-layout-summary.png", "sha256": "a" * 64},
        "checks": [{"name": "summary", "status": "pass"}],
        "boundaries": {
            "fullLegacyParity": False,
            "fullShortcutParity": False,
            "fullLayoutParity": False,
            "pixelPerfectLayoutParity": False,
            "osNativeMenuParity": False,
            "nativeDialogParity": False,
        },
    }


def valid_legacy_layout_parity_evidence() -> dict[str, object]:
    viewports = [
        {"name": "default", "width": 1280, "height": 840},
        {"name": "narrow desktop", "width": 900, "height": 840},
        {"name": "short window", "width": 1280, "height": 620},
    ]
    screenshots = [
        {
            "label": "default review 1280x840",
            "path": "docs/qa/screenshots/layout-default-review.png",
            "sha256": "1" * 64,
            "source": "runtime screenshot",
            "sizeBytes": 12345,
            "capturedAfterActionId": "view.candidates",
            "viewport": {"width": 1280, "height": 840},
        },
        {
            "label": "SGF editing narrow desktop",
            "path": "docs/qa/screenshots/layout-sgf-editing.png",
            "sha256": "2" * 64,
            "source": "runtime screenshot",
            "sizeBytes": 12345,
            "capturedAfterActionId": "game.parseSgf",
            "viewport": {"width": 900, "height": 840},
        },
        {
            "label": "KataGo analysis short window",
            "path": "docs/qa/screenshots/layout-katago-analysis.png",
            "sha256": "3" * 64,
            "source": "runtime screenshot",
            "sizeBytes": 12345,
            "capturedAfterActionId": "analysis.runReview",
            "viewport": {"width": 1280, "height": 620},
        },
        {
            "label": "provider/readboard layout",
            "path": "docs/qa/screenshots/layout-provider-readboard.png",
            "sha256": "4" * 64,
            "source": "runtime screenshot",
            "sizeBytes": 12345,
            "capturedAfterActionId": "tools.providers",
            "viewport": {"width": 1280, "height": 840},
        },
        {
            "label": "engine/preferences layout",
            "path": "docs/qa/screenshots/layout-engine-preferences.png",
            "sha256": "5" * 64,
            "source": "runtime screenshot",
            "sizeBytes": 12345,
            "capturedAfterActionId": "tools.preferences",
            "viewport": {"width": 900, "height": 840},
        },
    ]
    visible_assertions = [
        {"label": "board surface", "selector": "[data-testid='go-board']", "visible": True, "status": "pass"},
        {"label": "toolbar/menu controls", "selector": "[data-testid='legacy-menubar']", "visible": True, "status": "pass"},
        {"label": "SGF tree", "selector": "[data-testid='sgf-tree-panel']", "visible": True, "status": "pass"},
        {"label": "annotation comment properties editor", "selector": ".sgf-annotation-editor", "visible": True, "status": "pass"},
        {"label": "analysis panel", "selector": "[data-testid='legacy-analysis-pane']", "visible": True, "status": "pass"},
        {"label": "winrate chart", "selector": "[data-testid='winrate-chart']", "visible": True, "status": "pass"},
        {"label": "candidates/PV list", "selector": "[data-testid='candidate-list']", "visible": True, "status": "pass"},
        {"label": "cache/status", "selector": "[data-testid='analysis-cache-status']", "visible": True, "status": "pass"},
        {"label": "provider/readboard panel", "selector": "[data-testid='provider-panel']", "visible": True, "status": "pass"},
        {"label": "engine/preferences panel", "selector": "[data-testid='engine-setup-panel']", "visible": True, "status": "pass"},
    ]
    boundaries = {
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
    return {
        "schema": smoke_user_flows.LEGACY_LAYOUT_PARITY_SMOKE_SCHEMA,
        "name": "legacy_layout_parity_smoke",
        "status": "pass",
        "platform": "macos",
        "runtimeObserved": True,
        "sourceStaticOnly": False,
        "clickedObservedCount": 5,
        "shortcutObservedCount": 5,
        "visibleTargetCount": 10,
        "actionMatrix": valid_legacy_action_shortcut_matrix(),
        "screenshots": screenshots,
        "viewports": viewports,
        "visibleAssertions": visible_assertions,
        "criticalOverlapDetected": False,
        "criticalClippingDetected": False,
        **boundaries,
        "boundaries": boundaries,
        "checks": [
            {
                "name": "overlap_clipping",
                "status": "pass",
                "details": {"criticalOverlapDetected": False, "criticalClippingDetected": False},
            }
        ],
    }


def runner_shaped_legacy_layout_parity_evidence() -> dict[str, object]:
    boundaries = {
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
    viewport_matrix = [
        {"name": "desktop-1280x840", "width": 1280, "height": 840},
        {"name": "narrow-desktop-960x840", "width": 960, "height": 840},
        {"name": "short-window-1280x620", "width": 1280, "height": 620},
    ]
    scenarios = [
        ("default_review_layout", "Default review layout", ["board surface", "toolbar/menu controls", "analysis panel", "winrate chart"]),
        ("sgf_editing_layout", "SGF editing layout", ["SGF tree", "annotation comment properties editor"]),
        ("katago_analysis_layout", "KataGo analysis layout", ["candidates/PV list", "cache/status"]),
        ("provider_readboard_layout", "Provider/readboard layout", ["provider/readboard panel"]),
        ("engine_preferences_layout", "Engine/preferences layout", ["engine/preferences panel"]),
    ]
    screenshots: list[dict[str, object]] = []
    layouts: list[dict[str, object]] = []
    visible_assertions: list[dict[str, object]] = []
    sha_counter = 1
    for viewport in viewport_matrix:
        for scenario_name, scenario_label, labels in scenarios:
            path = f"docs/qa/screenshots/legacy-layout-{viewport['name']}-{scenario_name.replace('_', '-')}.png"
            screenshot = {
                "bytes": 12345,
                "sizeBytes": 12345,
                "label": f"{scenario_label} {viewport['name']}",
                "layout": scenario_name,
                "name": scenario_name,
                "path": path,
                "source": "vite-playwright-runtime-screenshot",
                "capturedAfterActionId": {
                    "default_review_layout": "view.candidates",
                    "sgf_editing_layout": "game.parseSgf",
                    "katago_analysis_layout": "analysis.runReview",
                    "provider_readboard_layout": "tools.providers",
                    "engine_preferences_layout": "tools.preferences",
                }[scenario_name],
                "sha256": f"{sha_counter:x}" * 64,
                "viewport": viewport,
            }
            sha_counter += 1
            assertions = [
                {
                    "label": f"{scenario_label} {label}",
                    "selector": f"[data-testid='{label.replace('/', '-').replace(' ', '-')}']",
                    "visible": True,
                    "status": "pass",
                }
                for label in labels
            ]
            screenshots.append(screenshot)
            visible_assertions.extend(assertions)
            layouts.append(
                {
                    "name": scenario_name,
                    "label": scenario_label,
                    "status": "pass",
                    "failures": [],
                    "screenshot": path,
                    "viewport": viewport,
                    "visibleAssertions": assertions,
                    "overflowClippingChecks": {
                        "bodyHorizontalOverflow": False,
                        "checks": [{"selector": "[data-testid='legacy-shell']", "visible": True, "clipped": False}],
                    },
                }
            )
    return {
        "schema": smoke_user_flows.LEGACY_LAYOUT_PARITY_SMOKE_SCHEMA,
        "name": "legacy_layout_parity_smoke",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "vite_playwright_layout_screenshots",
        "runtimeObserved": True,
        "sourceStaticOnly": False,
        "browserRenderedDomObserved": True,
        "screenshotObserved": True,
        "clickedObservedCount": 5,
        "shortcutObservedCount": 5,
        "visibleTargetCount": len(visible_assertions),
        "actionMatrix": valid_legacy_action_shortcut_matrix(),
        "criticalOverlap": False,
        "criticalClipping": False,
        "viewportMatrix": viewport_matrix,
        "layouts": layouts,
        "screenshots": screenshots,
        "visibleAssertions": visible_assertions,
        "boundaries": boundaries,
        "checks": [
            {"name": scenario_name, "status": "pass", "details": {"viewportsObserved": 3}}
            for scenario_name, _, _ in scenarios
        ]
        + [
            {"name": "screenshots_recorded", "status": "pass", "details": {"count": len(screenshots)}},
            {"name": "overflow_clipping_checks_recorded", "status": "pass", "details": {"layouts": len(layouts)}},
            {"name": "scope_boundaries_recorded", "status": "pass", "details": boundaries},
        ],
        "failures": [],
    }


def valid_installed_macos_app_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.INSTALLED_MACOS_APP_SMOKE_SCHEMA,
        "name": "installed_macos_app_smoke",
        "status": "pass",
        "platform": "macos",
        "appBundlePath": "dist/macos/LizzieYzy.app",
        "appBundle": {
            "exists": True,
            "path": "dist/macos/LizzieYzy.app",
            "sizeBytes": 123456,
            "sha256": "d" * 64,
        },
        "bundle": {
            "app": {"path": "dist/macos/LizzieYzy.app", "bytes": 123456, "sha256": "d" * 64},
            "binary": {"path": "dist/macos/LizzieYzy.app/Contents/MacOS/lizzieyzy", "bytes": 120000, "sha256": "f" * 64},
            "dmg": {"path": "dist/macos/LizzieYzy.dmg", "bytes": 654321, "sha256": "a" * 64},
            "dmgs": [{"path": "dist/macos/LizzieYzy.dmg", "bytes": 654321, "sha256": "a" * 64}],
            "infoPlist": {"path": "dist/macos/LizzieYzy.app/Contents/Info.plist"},
        },
        "launched": True,
        "windowObserved": True,
        "screenshotObserved": True,
        "devServerAbsent": True,
        "devServerPreflight": {
            "reachableBeforeLaunch": False,
            "runnerStartedDevServer": False,
        },
        "runnerStartedDevServer": False,
        "runnerStartedViteDevServer": False,
        "productionSigned": False,
        "notarized": False,
        "releasePublished": False,
        "boundaries": {
            "nativeDialogClickCovered": False,
            "webviewDomClickCovered": False,
            "viteDevServerStarted": False,
        },
        "screenshots": [
            {
                "label": "installed-app-window",
                "path": "docs/qa/screenshots/installed-macos-app-window.png",
                "sha256": "e" * 64,
            }
        ],
        "termination": {
            "status": "pass",
            "exitCode": 0,
            "success": True,
        },
    }


def valid_installed_app_backend_runtime_proof() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.INSTALLED_APP_RUNTIME_PROOF_SCHEMA,
        "status": "ok",
        "platform": "macos",
        "runtime": {
            "appName": "LizzieYzy Next",
            "version": "0.1.0",
            "identifier": "org.lizzieyzy.next",
            "source": "packaged-macos-app",
            "tauriRuntimeObserved": True,
            "devServerRequired": False,
            "debugAssertions": False,
            "currentExe": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/MacOS/lizzieyzy-next-desktop",
            "resourceDir": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources",
            "appDataDir": "<home>/Library/Application Support/org.lizzieyzy.next",
        },
        "bundle": {
            "productName": "LizzieYzy Next",
            "mainBinaryName": "lizzieyzy-next-desktop",
            "appBundlePath": "target/release/bundle/macos/LizzieYzy Next.app",
            "appBundleExists": True,
            "executableExists": True,
            "resourceDirExists": True,
        },
        "assets": {
            "status": "ready",
            "checks": [
                {"label": "resource-dir", "status": "exists"},
                {"label": "app-data-dir", "status": "exists"},
            ],
            "exists": ["resource-dir", "app-data-dir"],
            "missing": [],
            "placeholders": [],
            "warnings": [],
        },
        "profileStatus": {
            "status": "loaded",
            "loaded": True,
            "selectedProfileId": "runtime-smoke",
            "profileCount": 1,
            "selectedProfileName": "Runtime Smoke KataGo",
            "maxVisits": 64,
            "errorMessage": None,
        },
        "engineLaunchAttempt": {
            "attempted": True,
            "status": "unavailable",
            "recoverable": True,
            "success": False,
            "commandSpec": None,
            "assetChecks": [],
            "processId": None,
            "exitCode": None,
            "stderrPreview": None,
            "errorKind": "spawnFailed",
            "errorMessage": "sanitized captured runtime report recorded engine unavailable; not counted as success",
        },
        "boundaries": {
            "browserFallbackUsed": False,
            "devServerStarted": False,
            "realReleasePublished": False,
            "productionSigned": False,
            "notarized": False,
            "fullLegacyParity": False,
        },
    }


def valid_installed_app_runtime_workflow_evidence() -> dict[str, object]:
    boundaries = {
        "browserFallbackUsed": False,
        "sourceStaticOnly": False,
        "artifactOnly": False,
        "runnerStartedDevServer": False,
        "runnerStartedViteDevServer": False,
        "productionSigned": False,
        "signed": False,
        "notarized": False,
        "updaterReady": False,
        "updaterCovered": False,
        "releasePublished": False,
        "windowsInstalledAppCovered": False,
        "linuxInstalledAppCovered": False,
        "windowsLinuxInstalledAppCovered": False,
        "fullInstalledAppParity": False,
        "fullLegacyParity": False,
        "fullShortcutParity": False,
        "fullLayoutParity": False,
        "providerReadboardOcrParity": False,
        "providerReadboardOCRParity": False,
    }
    app_bundle = {
        "exists": True,
        "path": "target/release/bundle/macos/LizzieYzy Next.app",
        "sizeBytes": 17399164,
        "sha256": "2530d458dd7b676911e5e36088d7a902887e9a9e9edffa1bbecada7b12bc9de6",
    }
    runtime_process = {
        "observed": True,
        "processName": "LizzieYzy Next",
        "pid": 59579,
    }
    screenshots = [
        {
            "label": "installed-app-runtime-window",
            "source": "installed_app_runtime",
            "path": "docs/qa/screenshots/installed-macos-app-window.png",
            "sizeBytes": 186268,
            "sha256": "f0731971b0dd93513a5d103e18c96aa275495d814e2ac5940c5af59481cab3ba",
            "capturedAfterActionId": "observe_main_window",
        }
    ]
    termination = {
        "status": "pass",
        "exitCode": 0,
        "success": True,
    }
    workflow_actions = [
        {
            "actionId": "launch_installed_app",
            "status": "pass",
            "runtimeObserved": True,
            "evidence": {"appBundlePath": "target/release/bundle/macos/LizzieYzy Next.app"},
        },
        {
            "actionId": "observe_main_window",
            "status": "pass",
            "runtimeObserved": True,
            "evidence": {"windowTitle": "LizzieYzy"},
        },
        {
            "actionId": "execute_runtime_action",
            "status": "pass",
            "runtimeObserved": True,
            "evidence": {
                "backendCommand": "installed_app_runtime_proof",
                "proofSchema": smoke_user_flows.INSTALLED_APP_RUNTIME_PROOF_SCHEMA,
                "runtimeSource": "packaged-macos-app",
            },
        },
        {
            "actionId": "terminate_installed_app",
            "status": "pass",
            "runtimeObserved": True,
            "evidence": {"terminated": True, "exitCode": 0},
        },
    ]
    return {
        "schema": smoke_user_flows.INSTALLED_APP_RUNTIME_WORKFLOW_SCHEMA,
        "name": "installed_app_runtime_workflow",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "installed_app_smoke_plus_backend_runtime_proof",
        "runtimeSource": "packaged-macos-app",
        "runtimeObserved": True,
        "installedAppLaunched": True,
        "runtimeProcessObserved": True,
        "windowObserved": True,
        "workflowExecuted": True,
        "screenshotObserved": True,
        "devServerAbsent": True,
        "browserFallbackUsed": False,
        "sourceStaticOnly": False,
        "artifactOnly": False,
        "runnerStartedDevServer": False,
        "runnerStartedViteDevServer": False,
        "productionSigned": False,
        "signed": False,
        "notarized": False,
        "updaterReady": False,
        "updaterCovered": False,
        "releasePublished": False,
        "windowsInstalledAppCovered": False,
        "linuxInstalledAppCovered": False,
        "windowsLinuxInstalledAppCovered": False,
        "fullInstalledAppParity": False,
        "fullLegacyParity": False,
        "fullShortcutParity": False,
        "fullLayoutParity": False,
        "providerReadboardOcrParity": False,
        "providerReadboardOCRParity": False,
        "appBundlePath": "target/release/bundle/macos/LizzieYzy Next.app",
        "appBundle": app_bundle,
        "runtimeProcess": runtime_process,
        "backendRuntimeProof": valid_installed_app_backend_runtime_proof(),
        "workflowActions": workflow_actions,
        "screenshots": screenshots,
        "devServerPreflight": {
            "reachableBeforeLaunch": False,
            "runnerStartedDevServer": False,
        },
        "termination": termination,
        "boundaries": boundaries,
        "checks": [
            {"name": "app_bundle_verified", "status": "pass", "details": {"appBundle": app_bundle}},
            {
                "name": "installed_app_launched",
                "status": "pass",
                "details": {"installedAppLaunched": True, "appBundlePath": "target/release/bundle/macos/LizzieYzy Next.app"},
            },
            {"name": "runtime_process_observed", "status": "pass", "details": runtime_process},
            {"name": "window_observed", "status": "pass", "details": {"windowObserved": True}},
            {
                "name": "workflow_action_executed",
                "status": "pass",
                "details": {
                    "workflowExecuted": True,
                    "actionId": "execute_runtime_action",
                    "backendCommand": "installed_app_runtime_proof",
                    "proofSchema": smoke_user_flows.INSTALLED_APP_RUNTIME_PROOF_SCHEMA,
                },
            },
            {
                "name": "backend_runtime_proof_observed",
                "status": "pass",
                "details": {"backendRuntimeProof": valid_installed_app_backend_runtime_proof()},
            },
            {"name": "screenshot_recorded", "status": "pass", "details": {"screenshots": screenshots}},
            {"name": "dev_server_absent", "status": "pass", "details": {"devServerAbsent": True}},
            {"name": "quit_or_terminate_observed", "status": "pass", "details": termination},
            {"name": "scope_boundaries_recorded", "status": "pass", "details": {"boundaries": boundaries}},
        ],
    }


def valid_bundled_katago_installed_app_smoke_evidence() -> dict[str, object]:
    proof = valid_installed_app_backend_runtime_proof()
    proof["bundledKataGo"] = valid_bundled_katago_backend_proof()
    proof["raw"] = {"bundledKatago": proof["bundledKataGo"]}
    assets = proof["assets"]
    assert isinstance(assets, dict)
    assets["status"] = "problem"
    assets["checks"] = 3
    assets["exists"] = [{"label": "resource root", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources"}]
    assets["missing"] = [{"label": "KataGo model", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/models"}]
    assets["placeholders"] = []
    app_bundle = {
        "exists": True,
        "path": "target/release/bundle/macos/LizzieYzy Next.app",
        "sizeBytes": 17399164,
        "sha256": "2530d458dd7b676911e5e36088d7a902887e9a9e9edffa1bbecada7b12bc9de6",
    }
    runtime_source = {
        "sourceKind": "packaged-macos-app",
        "tauriRuntimeObserved": True,
        "devServerRequired": False,
        "resourceDir": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources",
        "appDataDir": "<home>/Library/Application Support/org.lizzieyzy.next",
    }
    asset_layout = {
        "sourceKind": "packaged-macos-app",
        "status": "problem",
        "validationStatus": "problem",
        "checks": 3,
        "exists": [{"label": "resource root", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources"}],
        "missing": [{"label": "KataGo model", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/models"}],
        "placeholders": [],
        "paths": [
            "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources",
            "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/models",
        ],
    }
    engine_launch = proof["engineLaunchAttempt"]
    assert isinstance(engine_launch, dict)
    engine_launch["status"] = "unavailable"
    engine_launch["success"] = False
    engine_launch["launchSucceeded"] = False
    engine_launch["errorKind"] = "missingEnginePath"
    screenshot = {
        "label": "bundled-katago-installed-app-window",
        "source": "bundled_katago_installed_app",
        "path": "docs/qa/screenshots/installed-macos-app-window.png",
        "sizeBytes": 186268,
        "sha256": "f0731971b0dd93513a5d103e18c96aa275495d814e2ac5940c5af59481cab3ba",
    }
    boundaries = {
        "sourceStaticOnly": False,
        "artifactOnly": False,
        "browserFallbackUsed": False,
        "runnerStartedDevServer": False,
        "runnerStartedViteDevServer": False,
        "fullBundledKataGoParity": False,
        "fullKataGoParity": False,
        "bundledLargeModelParity": False,
        "releaseParity": False,
        "signedReleaseParity": False,
        "productionSigned": False,
        "notarized": False,
        "updaterReady": False,
        "windowsLinuxParity": False,
        "windowsInstalledAppCovered": False,
        "linuxInstalledAppCovered": False,
        "fullLegacyParity": False,
        "providerParity": False,
        "readboardParity": False,
        "ocrParity": False,
    }
    return {
        "schema": smoke_user_flows.BUNDLED_KATAGO_INSTALLED_APP_SMOKE_SCHEMA,
        "name": "bundled_katago_installed_app_smoke",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "installed_app_runtime_bundled_katago_layout_probe",
        "runtimeObserved": True,
        "installedAppLaunched": True,
        "backendCommandInvoked": True,
        "backendCommand": "installed_app_runtime_proof",
        "screenshotObserved": True,
        **boundaries,
        "appBundle": app_bundle,
        "runtimeSource": runtime_source,
        "backendRuntimeProof": proof,
        "bundledKataGo": proof["bundledKataGo"],
        "bundledAssetLayout": asset_layout,
        "profileStatus": proof["profileStatus"],
        "engineLaunchAttempt": engine_launch,
        "screenshots": [screenshot],
        "boundaries": boundaries,
        "checks": [
            {"name": "app_bundle_verified", "status": "pass", "details": {"appBundle": app_bundle}},
            {"name": "runtime_started", "status": "pass", "details": {"runtimeSource": runtime_source}},
            {"name": "backend_runtime_proof_observed", "status": "pass", "details": {"backendRuntimeProof": proof}},
            {"name": "bundled_asset_layout_validated", "status": "pass", "details": {"bundledAssetLayout": asset_layout}},
            {"name": "bundled_engine_launch_attempted", "status": "pass", "details": {"engineLaunchAttempt": engine_launch}},
            {"name": "screenshot_recorded", "status": "pass", "details": {"screenshots": [screenshot]}},
            {
                "name": "dev_server_excluded",
                "status": "pass",
                "details": {"devServerExcluded": True, "devServerAbsent": True, "runnerStartedDevServer": False},
            },
            {"name": "scope_boundaries_recorded", "status": "pass", "details": {"boundaries": boundaries}},
        ],
    }


def valid_bundled_katago_backend_proof() -> dict[str, object]:
    return {
        "sourceKind": "packaged-macos-app",
        "status": "incomplete",
        "validationStatus": "incomplete",
        "complete": False,
        "checks": 4,
        "exists": [{"label": "runtime root", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources"}],
        "missing": [
            {"label": "KataGo bin", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/bin"},
            {"label": "KataGo models", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/models"},
            {"label": "KataGo configs", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/configs"},
        ],
        "placeholders": [],
        "details": {
            "checks": [
                {"label": "runtime root", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources", "status": "exists"},
                {"label": "KataGo bin", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/bin", "status": "missing"},
                {"label": "KataGo models", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/models", "status": "missing"},
                {"label": "KataGo configs", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/configs", "status": "missing"},
            ],
            "exists": [{"label": "runtime root", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources"}],
            "missing": [
                {"label": "KataGo bin", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/bin"},
                {"label": "KataGo models", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/models"},
                {"label": "KataGo configs", "path": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/Resources/runtime/katago/configs"},
            ],
            "placeholders": [],
            "layout": {"source": "resource_dir"},
        },
    }


def valid_installed_app_sgf_workflow_evidence() -> dict[str, object]:
    app_bundle = {
        "exists": True,
        "path": "target/release/bundle/macos/LizzieYzy Next.app",
        "sizeBytes": 123456,
        "sha256": "8" * 64,
        "mainExecutable": "lizzieyzy-next-desktop",
    }
    screenshot = {
        "label": "installed-app-sgf-workflow-window",
        "path": "docs/qa/screenshots/installed-app-sgf-workflow-window.png",
        "sizeBytes": 23456,
        "sha256": "9" * 64,
        "source": "installed_app_sgf_workflow",
    }
    boundaries = {
        "fullSgfWorkflowParity": False,
        "nativeDialogParity": False,
        "releaseParity": False,
        "fullLegacyParity": False,
        "windowsCovered": False,
        "linuxCovered": False,
        "providerParity": False,
        "readboardParity": False,
        "ocrParity": False,
    }
    source_report = valid_installed_app_sgf_source_runtime_report()
    checks = [
        {"name": "installed_app_launched", "status": "pass", "details": {"installedAppLaunched": True}},
        {
            "name": "runtime_report_observed",
            "status": "pass",
            "details": {
                "schema": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_SCHEMA,
                "status": "pass",
                "tauriRuntimeObserved": True,
            },
        },
        {"name": "sgf_loaded", "status": "pass", "details": {"bytes": 211, "path": "<tmp>/runtime-smoke.sgf"}},
        {
            "name": "sgf_reparsed",
            "status": "pass",
            "details": {"reparseVerified": True, "readbackStatus": "matched_saved_text"},
        },
        {"name": "tree_navigation", "status": "pass", "details": {"moveNumber": 2}},
        {"name": "comment_edit", "status": "pass", "details": {"comment": "runtime smoke branch persisted"}},
        {"name": "property_edit", "status": "pass", "details": {"expectedProperties": {"N": "runtime-smoke-branch"}}},
        {"name": "annotation_edit", "status": "pass", "details": valid_runtime_check_evidence("annotation_edit")},
        {"name": "append_move", "status": "pass", "details": {"nodeId": "move-2", "vertex": "0,0"}},
        {"name": "edit_move", "status": "pass", "details": valid_runtime_check_evidence("edit_move")},
        {"name": "variation_reorder", "status": "pass", "details": valid_runtime_check_evidence("variation_reorder")},
        {"name": "delete_node", "status": "pass", "details": valid_runtime_check_evidence("delete_node")},
        {"name": "save_readback_roundtrip", "status": "pass", "details": valid_installed_app_sgf_save_details()},
        {
            "name": "reopen_verified",
            "status": "pass",
            "details": {"reopenVerified": True, "afterReopen": valid_installed_app_sgf_after_reopen()},
        },
        {
            "name": "final_invariant_verified",
            "status": "pass",
            "details": {"verified": True, "invariant": "saved_or_reopened_replay_has_no_errors"},
        },
        {"name": "screenshot_hash_recorded", "status": "pass", "details": screenshot},
        {"name": "scope_boundaries_recorded", "status": "pass", "details": {"boundaries": boundaries}},
    ]
    return {
        "schema": smoke_user_flows.INSTALLED_APP_SGF_WORKFLOW_SCHEMA,
        "name": "installed_app_sgf_workflow",
        "status": "pass",
        "platform": "macos",
        "collectionMethod": "installed_app_smoke_plus_real_tauri_runtime_sgf_report",
        "runtimePhase": "installed-app-sgf-workflow",
        "installedAppLaunched": True,
        "tauriRuntimeObserved": True,
        "sgfWorkflowAutomated": True,
        "screenshotHashRecorded": True,
        "sourceStaticOnly": False,
        "devServerOnly": False,
        "browserFallbackUsed": False,
        **boundaries,
        "appBundlePath": "target/release/bundle/macos/LizzieYzy Next.app",
        "appBundle": app_bundle,
        "runtimeProcess": {"observed": True, "processName": "LizzieYzy Next", "pid": 1234},
        "packagedAppLaunch": {
            "executable": "<repo>/target/release/bundle/macos/LizzieYzy Next.app/Contents/MacOS/lizzieyzy-next-desktop",
            "pid": 1234,
            "phase": "installed-app-sgf-workflow",
        },
        "sourceRuntimeReport": source_report,
        "screenshots": [screenshot],
        "checks": checks,
        "boundaries": boundaries,
    }


def valid_installed_app_sgf_source_runtime_report() -> dict[str, object]:
    checks = [
        {"name": "runtime_started", "status": "pass", "details": {"tauriInternals": True, "platform": "MacIntel"}},
        {
            "name": "browser_fallback_excluded",
            "status": "pass",
            "details": {"tauriRuntimeObserved": True, "browserFallbackUsed": False},
        },
        {
            "name": "backend_runtime_proof_observed",
            "status": "pass",
            "details": {"raw": valid_installed_app_backend_runtime_proof()},
        },
        {"name": "sgf_loaded", "status": "pass", "details": {"bytes": 211, "path": "<tmp>/runtime-smoke.sgf"}},
        {"name": "branch_navigation", "status": "pass", "details": {"moveNumber": 2, "stones": 2}},
        {"name": "comment_edit", "status": "pass", "details": {"comment": "runtime smoke branch persisted"}},
        {"name": "property_edit", "status": "pass", "details": {"expectedProperties": {"N": "runtime-smoke-branch"}}},
        {"name": "annotation_edit", "status": "pass", "details": valid_runtime_check_evidence("annotation_edit")},
        {"name": "append_move", "status": "pass", "details": {"nodeId": "move-2", "vertex": "0,0"}},
        {"name": "edit_move", "status": "pass", "details": valid_runtime_check_evidence("edit_move")},
        {"name": "variation_reorder", "status": "pass", "details": valid_runtime_check_evidence("variation_reorder")},
        {"name": "delete_node", "status": "pass", "details": valid_runtime_check_evidence("delete_node")},
        {"name": "save_readback_roundtrip", "status": "pass", "details": valid_installed_app_sgf_save_details()},
        {"name": "board_state_verified", "status": "pass", "details": valid_runtime_check_evidence("board_state_verified")},
        {
            "name": "reopen_state_verified",
            "status": "pass",
            "details": {"verified": True, **valid_installed_app_sgf_after_reopen()},
        },
        {"name": "save_reopen_roundtrip", "status": "pass", "details": {"verified": True, "afterReopen": valid_installed_app_sgf_after_reopen()}},
        {"name": "scope_boundaries_recorded", "status": "pass", "details": {"fullLegacyParity": False}},
    ]
    return {
        "schema": smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_SCHEMA,
        "status": "pass",
        "platform": "macos",
        "phase": "installed-app-sgf-workflow",
        "browserFallbackUsed": False,
        "checks": checks,
    }


def valid_installed_app_sgf_save_details() -> dict[str, object]:
    return {
        "savedPath": "<tmp>/runtime-smoke.sgf",
        "saveVerified": True,
        "readbackVerified": True,
        "readbackMatchesSaved": True,
        "readbackStatus": "matched_saved_text",
        "reopen": {"path": "<tmp>/runtime-smoke.sgf", "status": "pass", "matchesSaved": True},
        "afterReopen": valid_installed_app_sgf_after_reopen(),
    }


def valid_installed_app_sgf_after_reopen() -> dict[str, object]:
    return {
        "treeOrderVerified": True,
        "commentsVerified": True,
        "propertiesVerified": True,
        "annotationsVerified": True,
        "moveCountVerified": True,
        "boardStateVerified": True,
        "deletedTargetAbsent": True,
    }


def valid_native_desktop_sgf_workflow_evidence() -> dict[str, object]:
    return {
        "schema": smoke_user_flows.NATIVE_DESKTOP_SGF_WORKFLOW_SCHEMA,
        "name": "native_desktop_sgf_workflow",
        "status": "pass",
        "platform": "macos",
        "appMode": "packaged-macos-app",
        "collectionMethod": "manual_assisted_native_desktop_workflow",
        "nativeDialogOpenCovered": True,
        "nativeDialogSaveCovered": True,
        "webviewDomAutomationCovered": False,
        "fullAutomationCovered": False,
        "fullLegacyParityCovered": False,
        "releasePublished": False,
        "productionSigned": False,
        "notarized": False,
        "appPath": "dist/macos/LizzieYzy.app",
        "inputSgfPath": "<tmp>/native-desktop-sgf-workflow/input.sgf",
        "savedSgfPath": "<tmp>/native-desktop-sgf-workflow/saved.sgf",
        "logPath": "docs/qa/logs/native-desktop-sgf-workflow.log",
        "screenshots": [
            {
                "label": "native-open-dialog",
                "path": "docs/qa/screenshots/native-desktop-sgf-open-dialog.png",
                "bytes": 1234,
                "sha256": "1" * 64,
            },
            {
                "label": "native-reopened-sgf",
                "path": "docs/qa/screenshots/native-desktop-sgf-reopened.png",
                "bytes": 2345,
                "sha256": "2" * 64,
            },
        ],
        "checks": [
            {
                "name": "app_started",
                "status": "pass",
                "details": {
                    "appPath": "dist/macos/LizzieYzy.app",
                    "logPath": "docs/qa/logs/native-desktop-sgf-workflow.log",
                },
            },
            {
                "name": "native_open_dialog",
                "status": "pass",
                "details": {
                    "operator": {
                        "confirmation": "operator confirmed selected input SGF in native Open dialog",
                        "tooling": ["screencapture"],
                        "type": "manual-assisted",
                    },
                    "method": "manual_assisted_native_dialog",
                    "openedPath": "<tmp>/native-desktop-sgf-workflow/input.sgf",
                    "screenshot": {
                        "path": "docs/qa/screenshots/native-desktop-sgf-open-dialog.png",
                        "bytes": 1234,
                        "sha256": "1" * 64,
                    },
                },
            },
            {
                "name": "sgf_opened",
                "status": "pass",
                "details": {
                    "openedSgfPath": "<tmp>/native-desktop-sgf-workflow/input.sgf",
                    "boardLoaded": True,
                    "treeLoaded": True,
                },
            },
            {
                "name": "edit_operations_applied",
                "status": "pass",
                "details": {
                    "operations": [
                        "comment_edit",
                        "property_edit",
                        "annotation_edit",
                        "append_move",
                        "reorder_variation",
                        "delete_node",
                    ],
                    "editsApplied": True,
                },
            },
            {
                "name": "save_or_save_as",
                "status": "pass",
                "details": {
                    "operator": {
                        "confirmation": "operator confirmed selected output SGF in native Save dialog",
                        "tooling": ["screencapture"],
                        "type": "manual-assisted",
                    },
                    "method": "manual_assisted_native_dialog",
                    "savedPath": "<tmp>/native-desktop-sgf-workflow/saved.sgf",
                    "screenshot": {
                        "path": "docs/qa/screenshots/native-desktop-sgf-save-dialog.png",
                        "bytes": 2234,
                        "sha256": "3" * 64,
                    },
                },
            },
            {
                "name": "reopen_saved_sgf",
                "status": "pass",
                "details": {
                    "savedSgfPath": "<tmp>/native-desktop-sgf-workflow/saved.sgf",
                    "reopenedSgfPath": "<tmp>/native-desktop-sgf-workflow/saved.sgf",
                    "reopened": True,
                },
            },
            {
                "name": "reopen_state_verified",
                "status": "pass",
                "details": {
                    "method": "saved SGF content/tree/board invariant verification plus operator-confirmed reopened app state",
                    "invariants": {
                        "verified": True,
                        "contentHash": "4" * 64,
                        "contentInvariant": {
                            "boardSize9": True,
                            "sourceCommentPresent": True,
                        },
                        "boardInvariant": {
                            "verifiedByContent": True,
                            "expectedStones": [
                                {"color": "B", "point": "dd"},
                                {"color": "W", "point": "ee"},
                            ],
                        },
                        "treeInvariant": {
                            "moveCountAtLeast": 2,
                            "rootPresent": True,
                            "moveTokens": [";B[dd]", ";W[ee]"],
                        },
                    },
                },
            },
            {
                "name": "screenshots_recorded",
                "status": "pass",
                "details": {
                    "count": 2,
                    "paths": [
                        "docs/qa/screenshots/native-desktop-sgf-open-dialog.png",
                        "docs/qa/screenshots/native-desktop-sgf-reopened.png",
                    ],
                },
            },
            {
                "name": "scope_boundaries",
                "status": "pass",
                "details": {
                    "webviewDomAutomationCovered": False,
                    "fullAutomationCovered": False,
                    "fullLegacyParityCovered": False,
                    "releasePublished": False,
                    "productionSigned": False,
                    "notarized": False,
                },
            },
        ],
        "boundaries": {
            "windowsCovered": False,
            "windowsInstalledAppCovered": False,
            "linuxCovered": False,
            "linuxInstalledAppCovered": False,
            "ocrCovered": False,
            "ocrCaptureCovered": False,
            "captureCovered": False,
            "externalClientCaptureCovered": False,
            "providerCovered": False,
            "providerParityCovered": False,
            "readboardCovered": False,
            "readboardParityCovered": False,
            "webviewDomAutomationCovered": False,
            "fullLegacyParityCovered": False,
            "releasePublished": False,
            "productionSigned": False,
            "notarized": False,
        },
    }


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
    disabled = disabled_entries | disabled_entries_with_handler
    create_legacy_actions_fixture(root, disabled_entries=disabled, omitted_entries=omitted_entries)
    write(
        root / smoke_user_flows.LEGACY_SHELL_SOURCE,
        """
        import { legacyActionMatrix } from "../domain/legacyActions";

        export function LegacyShell() {{
          const isBusy = false;
          const dirty = false;
          const toolbarMenuSurfaceTokens = "Application menu Main toolbar Open SGF Save SGF Save SGF as File Open Save Save As View Candidates Engine Tools";
          const groups = new Map();
          for (const action of legacyActionMatrix) {
            const items = groups.get(action.group) ?? [];
            items.push({ action, disabled: isBusy });
            groups.set(action.group, items);
          }
          const menuGroups = Array.from(groups.entries()).map(([label, items]) => ({ label, items }));
          return <main data-testid="legacy-shell"><span hidden>{toolbarMenuSurfaceTokens}</span><nav className="legacy-menubar" aria-label="Application menu" data-testid="legacy-menubar">{menuGroups.map((group) => <details key={group.label} className="legacy-menu"><summary>{group.label}</summary>{group.items.map((item) => <button data-legacy-action={item.action.id} data-testid={`legacy-menu-${group.label.toLowerCase()}-${item.action.label.toLowerCase().replaceAll(" ", "-")}`} disabled={item.disabled}>{item.action.label}</button>)}</details>)}</nav><section className="legacy-toolbar" aria-label="Main toolbar" data-testid="legacy-toolbar"><button title="Open SGF">Open</button><button title="Save SGF">Save</button><button title="Save SGF as">Save As</button><span>{dirty ? "Unsaved" : "Saved"}</span><span>{dirty ? "Unsaved changes" : "Saved"}</span></section><footer className="legacy-statusbar" data-testid="legacy-statusbar" /></main>;
        }}
        """,
    )


def create_legacy_actions_fixture(
    root: Path,
    *,
    disabled_entries: set[tuple[str, str]] | None = None,
    omitted_entries: set[tuple[str, str]] | None = None,
    action_id_overrides: dict[str, str] | None = None,
) -> None:
    disabled_entries = disabled_entries or set()
    omitted_entries = omitted_entries or set()
    action_id_overrides = action_id_overrides or {}
    action_blocks: list[str] = []
    for action in canonical_legacy_actions():
        group = str(action["group"])
        label = str(action["label"])
        if (group, label) in omitted_entries:
            continue
        action_id = action_id_overrides.get(str(action["id"]), str(action["id"]))
        disabled = ", disabled: true" if (group, label) in disabled_entries else ""
        target = f', target: "{action["target"]}"' if action.get("target") else ""
        shortcut = f', shortcut: "{action["shortcut"]}"' if action.get("shortcut") else ""
        action_blocks.append(
            f'  {{ id: "{action_id}", group: "{group}", label: "{label}"{target}{shortcut}{disabled} }}'
        )
    write(
        root / smoke_user_flows.LEGACY_ACTIONS_SOURCE,
        "export const legacyActionMatrix = [\n" + ",\n".join(action_blocks) + "\n];\n",
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

        export async function listenToLegacyMenuActionEvents(onAction: (actionId: string) => void): Promise<() => void> {{
          const eventNames = await legacyNativeMenuEventNames();
          return () => undefined;
        }}

        async function legacyNativeMenuEventNames(): Promise<string[]> {{
          const canonicalFallback = "{smoke_user_flows.NATIVE_MENU_EVENT_NAME}";
          return uniqueStrings([canonicalFallback, "legacy://menu-action", "legacy-menu-action"]);
        }}

        function uniqueStrings(values: Array<string | null | undefined>): string[] {{
          return values.filter((value): value is string => typeof value === "string");
        }}

        export type RuntimeAssetPathDto = {{
          label: string;
          kind: string;
          source: string;
          path: string;
          required: boolean;
        }};

        export type RuntimeAssetLayoutDto = {{
          resourceDir?: string | null;
          devRoots: string[];
          resourceRoots: string[];
          releaseRoots: string[];
          candidates: RuntimeAssetPathDto[];
        }};

        export type RuntimeAssetValidationEntryDto = RuntimeAssetPathDto & {{
          status: string;
          message: string;
        }};

        export type RuntimeAssetValidationDto = {{
          layout: RuntimeAssetLayoutDto;
          checks: RuntimeAssetValidationEntryDto[];
          exists: RuntimeAssetValidationEntryDto[];
          missing: RuntimeAssetValidationEntryDto[];
          placeholders: RuntimeAssetValidationEntryDto[];
          warnings: string[];
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

        export async function startKataGoGameAnalysis(profile: EngineProfileDto, sgfText: string, maxVisits: number): Promise<string> {{
          return await invoke<string>("katago_start_analyze_game", {{ profile, sgfText, maxVisits }});
        }}

        export async function cancelKataGoAnalysis(jobId: string): Promise<void> {{
          await invoke<void>("katago_cancel_analysis", {{ jobId }});
        }}

        export async function listenToKataGoAnalysisEvents(handlers: KataGoAnalysisEventHandlers): Promise<() => void> {{
          const unlisteners = await Promise.all([
            listen("katago://analysis-progress", (event) => handlers.onProgress?.(event.payload)),
            listen("katago://analysis-complete", (event) => handlers.onComplete?.(event.payload)),
            listen("katago://analysis-error", (event) => handlers.onError?.(event.payload)),
            listen("katago://analysis-cancelled", (event) => handlers.onCancelled?.(event.payload))
          ]);
          return () => unlisteners.forEach((unlisten) => unlisten());
        }}

        export async function editSgfMove(sgfText: string, nodeId: string, point: MoveVertex | "pass") {{
          return await invoke("edit_sgf_move", {{ sgfText, nodeId, point }});
        }}

        export async function updateSgfNodeProperties(sgfText: string, nodeId: string, updates: SgfPropertyUpdate[]) {{
          return await invoke("update_sgf_node_properties", {{ sgfText, nodeId, updates }});
        }}

        export type LegacyConfigMigrationPreviewDto = {{
          sourcePath: string;
          migratedFields: string[];
          warnings: string[];
        }};

        export type LegacyConfigMigrationApplyDto = {{
          sourcePath: string;
          status: string;
          errorMessage: string | null;
          preferencesWritten: boolean;
          engineProfilesWritten: boolean;
          writtenPathLabels: string[];
          transactional: boolean;
          noWriteOnError: boolean;
          rollbackPerformed: boolean;
          rollbackSucceeded: boolean;
          rollbackPaths: string[];
          rollbackErrors: string[];
          writtenPaths: string[];
          migratedFields: string[];
          warnings: string[];
        }};

        export async function previewLegacyConfigMigration(path: string): Promise<LegacyConfigMigrationPreviewDto> {{
          return await invoke<LegacyConfigMigrationPreviewDto>("preview_legacy_config_migration", {{ path }});
        }}

        export async function applyLegacyConfigMigration(path: string): Promise<LegacyConfigMigrationApplyDto> {{
          return await invoke<LegacyConfigMigrationApplyDto>("apply_legacy_config_migration", {{ path }});
        }}

        export async function resolveRuntimeAssetLayout(): Promise<RuntimeAssetLayoutDto> {{
          return await invoke<RuntimeAssetLayoutDto>("resolve_runtime_asset_layout");
        }}

        export async function validateRuntimeAssetLayout(): Promise<RuntimeAssetValidationDto> {{
          return await invoke<RuntimeAssetValidationDto>("validate_runtime_asset_layout");
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
          const selectedNodeId = "node-1";
          const dirty = true;
          const desktopSgfEditingUxSmokeTokens = "selectedNodeId canSave={{dirty}} setDirty(true) setDirty(false)";
          const legacyConfigPath = "/tmp/legacy.properties";
          const legacyConfigStatus = "Ready to preview legacy config.";
          const legacyConfigPreview = null;
          const legacyConfigApplyResult = null;
          const annotationError = null;
          const isAnnotationSaving = false;
          const ProviderPanel = "ProviderPanel";
          const sgfTextEditVersionRef = {{ current: 0 }};
          const activeJobIdRef = {{ current: null }};
          const pendingAnalysisProgressRef = {{ current: new Map() }};
          const pendingAnalysisTerminalEventsRef = {{ current: new Map() }};
          const activeJobId = activeJobIdRef.current;
          const analysisProgress = null;
          async function handleProviderImport(result) {{
            return result;
          }}
          async function loadAppPreferences() {{
            return {{}};
          }}
          async function loadEngineProfilesSettings() {{
            return {{}};
          }}
          async function handlePreviewLegacyConfigMigration() {{
            return await previewLegacyConfigMigration(legacyConfigPath);
          }}
          async function handleApplyLegacyConfigMigration() {{
            const result = await applyLegacyConfigMigration(legacyConfigPath);
            if (result.status === "failed") {{
              const summary = legacyConfigApplyFailureSummary(result);
              return summary;
            }}
            const summary = legacyConfigApplySuccessSummary(result);
            await loadAppPreferences();
            await loadEngineProfilesSettings();
            return summary;
          }}
          function legacyConfigApplyFailureSummary(result) {{
            return `${{result.errorMessage}} ${{result.noWriteOnError}} ${{result.rollbackPerformed}} ${{result.rollbackSucceeded}}`;
          }}
          function legacyConfigApplySuccessSummary(result) {{
            return `${{result.transactional}} ${{result.writtenPathLabels.length}}`;
          }}
          async function handleSaveAnnotations(nodeId, updates) {{
            try {{
              setAnnotationError(null);
              return await updateSgfNodeProperties(sgfText, nodeId, updates);
            }} catch (error) {{
              setAnnotationError(`Save annotations failed: ${{error}}`);
              throw error;
            }}
          }}
          async function handleAnalyzeKataGoGame(profile, maxVisits) {{
            pendingAnalysisProgressRef.current.clear();
            pendingAnalysisTerminalEventsRef.current.clear();
            setAnalysisProgress(null);
            await listenToKataGoAnalysisEvents({{
              onProgress: (payload) => {{
                if (!isCurrentAnalysisJob(payload.job_id)) return;
                setAnalysisProgress({{
                  jobId: payload.job_id,
                  completed: payload.completed,
                  expected: payload.expected,
                  turn: payload.turn
                }});
              }},
              onComplete: (payload) => {{
                if (!isCurrentAnalysisJob(payload.job_id)) return;
                void finishCompletedAnalysis(payload.job_id, payload.frames, {{}}, []);
              }},
              onError: (payload) => {{
                if (!isCurrentAnalysisJob(payload.job_id)) return;
                finishStoppedAnalysis(payload.job_id);
                setMessage(`Full-game KataGo analysis failed: ${{payload.message}}`);
              }},
              onCancelled: (payload) => {{
                if (!isCurrentAnalysisJob(payload.job_id)) return;
                finishStoppedAnalysis(payload.job_id);
                setMessage(payload.message || "Full-game KataGo analysis cancelled.");
              }}
            }});
            const jobId = await startKataGoGameAnalysis(profile, sgfText, maxVisits);
            activeJobIdRef.current = jobId;
            setActiveJobId(jobId);
            setMessage(`Full-game KataGo analysis started (${{jobId}}).`);
          }}
          async function handleCancelKataGoAnalysis() {{
            const jobId = activeJobIdRef.current;
            if (!jobId) return;
            await cancelKataGoAnalysis(jobId);
            setMessage("Full-game KataGo analysis cancelled.");
          }}
          function isCurrentAnalysisJob(jobId) {{
            const currentHash = computeGameCacheKey(sgfText, currentFilePath);
            return Boolean(currentHash) && activeJobIdRef.current === jobId;
          }}
          async function finishCompletedAnalysis(jobId, result, parsed, replayed) {{
            finishStoppedAnalysis(jobId);
            await saveAnalysisCacheForGame(sgfText, currentFilePath, parsed, result, replayed, "katago");
          }}
          function finishStoppedAnalysis(jobId) {{
            if (activeJobIdRef.current !== null && activeJobIdRef.current !== jobId) return;
            activeJobIdRef.current = null;
            setActiveJobId(null);
            setAnalysisProgress(null);
          }}
          async function checkAnalysisCacheForGame(text, filePath, parsed, replayed, baseMessage) {{
            const cacheKey = await computeGameCacheKey(text, filePath);
            const lookup = await loadPreferredAnalysisCache(cacheKey.gameKey);
            if (lookup.status === "hit") {{
              setMessage(`${{baseMessage}} Restored ${{lookup.frames.length}} cached KataGo review frames.`);
            }}
            return {{ parsed, replayed }};
          }}
          async function loadPreferredAnalysisCache(gameKey) {{
            return await loadAnalysisCache(gameKey, null, "katago");
          }}
          async function handleSaveSgfDocument(saveAs = false) {{
            try {{
              {save_body}
            }} catch (error) {{
              setMessage(`Save failed: ${{error}}`);
            }}
          }}
          {edit_handler_body}
          return {{ ProviderPanel, handleProviderImport, handleSaveSgfDocument, handleSaveAnnotations, annotationError, isAnnotationSaving, handleAnalyzeKataGoGame, handleCancelKataGoAnalysis, activeJobId, analysisProgress, handlePreviewLegacyConfigMigration, handleApplyLegacyConfigMigration, legacyConfigStatus, legacyConfigPreview, legacyConfigApplyResult }};
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
          onSaveAnnotations: (nodeId: string, updates: unknown[]) => void;
          isAnnotationSaving: boolean;
          annotationError: string | null;
        };

        export function SgfTreePanel({ moveEditMode, canEditSelectedMove, onEditSelectedMovePass, onSaveAnnotations, isAnnotationSaving, annotationError }: Props) {
          return <aside className="sgf-tree-panel" aria-label="SGF tree and comments"><h2>SGF Tree</h2><button className="sgf-tree-node" onClick={() => onSelectNode("node-1")}>Node</button><section aria-label="Selected node actions"><button>Move Up</button><button>Move Down</button><button>Delete Node</button></section><div aria-label="Move edit mode"><button>Append</button><button>Edit selected</button></div><textarea aria-label="Selected SGF node comment" /><SgfAnnotationPanel onSaveAnnotations={onSaveAnnotations} isSaving={isAnnotationSaving} error={annotationError} moveEditMode={moveEditMode} canEditSelectedMove={canEditSelectedMove} onEditSelectedMovePass={onEditSelectedMovePass} /></aside>;
        }
        """,
    )


def create_sgf_annotation_panel_fixture(root: Path) -> None:
    write(
        root / smoke_user_flows.SGF_ANNOTATION_PANEL_SOURCE,
        """
        import type { SgfPropertyUpdate } from "../api/backend";

        const annotationFields = ["TR", "SQ", "CR", "MA", "SL", "LB", "AR", "LN"];

        export function SgfAnnotationPanel({ onSaveAnnotations, error }) {
          return (
            <section className="sgf-annotation-editor" aria-label="SGF node annotations">
              {annotationFields.map((key) => (
                <label key={key}>{key}<textarea aria-label={`${key} annotation values`} /></label>
              ))}
              <button>Add</button>
              <button>Remove aa</button>
              <button>Clear</button>
              {error ? <p role="alert">{error}</p> : null}
              <button onClick={() => onSaveAnnotations("node-1", [] as SgfPropertyUpdate[])}>Save Annotations</button>
            </section>
          );
        }
        """,
    )


def create_runtime_smoke_fixture(root: Path) -> None:
    write(
        root / "apps/desktop/src/runtimeSmoke.ts",
        """
        const expectedBranchAnnotations = {
          TR: ["aa"],
          SQ: [],
          CR: ["bb"],
          MA: ["cc"],
          SL: ["dd"],
          LB: ["aa:A", "ee:E"],
          AR: ["aa:bb"],
          LN: ["cc:dd"]
        };

        async function runEditSavePhase() {
          await check(report, "annotation_edit", async () => ({
            annotations: expectedBranchAnnotations,
            added: ["TR", "CR", "MA", "SL", "AR", "LN"],
            updated: ["LB"],
            removed: ["SQ"]
          }));
        }

        function verifyReopenedState() {
          const annotationsVerified = true;
          assertPropertyAbsent(node, "SQ");
          return { annotationsVerified };
        }

        function assertPropertyAbsent() {}
        """,
    )


def create_preferences_panel_fixture(root: Path, *, migration_ui: bool = True, migration_safety_ui: bool = True) -> None:
    if migration_ui:
        safety_body = """
              <strong>Migration safety</strong>
              <div data-testid="legacy-config-safety-status">{migrationSafetySummary(legacyConfigApplyResult)}</div>
              <div data-testid="legacy-config-written-path-labels">{legacyConfigApplyResult?.writtenPathLabels}</div>
              <div data-testid="legacy-config-rollback-paths">{legacyConfigApplyResult?.rollbackPaths}</div>
              <div data-testid="legacy-config-rollback-errors">{legacyConfigApplyResult?.rollbackErrors}</div>
        """ if migration_safety_ui else ""
        body = """
        type Props = {
          legacyConfigPath: string;
          legacyConfigStatus: string;
          legacyConfigPreview: { migratedFields: string[]; warnings: string[] } | null;
          legacyConfigApplyResult: { status: string; migratedFields: string[]; warnings: string[]; writtenPathLabels: string[]; transactional: boolean; noWriteOnError: boolean; rollbackPerformed: boolean; rollbackSucceeded: boolean; rollbackPaths: string[]; rollbackErrors: string[] } | null;
          onPreviewLegacyConfigMigration: () => void;
          onApplyLegacyConfigMigration: () => void;
        };

        function migrationSafetySummary(result) {
          return `${result?.status} ${result?.transactional} error protection enabled ${result?.rollbackPerformed} ${result?.rollbackSucceeded}`;
        }

        function migrationWriteStatus(result, writeTouched) {
          if (result?.status !== "failed") {
            return writeTouched ? "written" : "unchanged";
          }
          if (!writeTouched) {
            return "unchanged";
          }
          if (result.rollbackPerformed && result.rollbackSucceeded) {
            return "written then rolled back";
          }
          return result.rollbackPerformed ? "write attempted; rollback failed" : "write attempted";
        }

        export function PreferencesPanel({
          legacyConfigPath,
          legacyConfigStatus,
          legacyConfigPreview,
          legacyConfigApplyResult,
          onPreviewLegacyConfigMigration,
          onApplyLegacyConfigMigration
        }: Props) {
          return (
            <section aria-label="Legacy Java/Swing config migration">
              <label>Legacy config path<input value={legacyConfigPath} /></label>
              <span>{legacyConfigStatus}</span>
              <button onClick={onPreviewLegacyConfigMigration}>Preview</button>
              <button onClick={onApplyLegacyConfigMigration}>Apply</button>
              <strong>Migrated fields</strong>
              <strong>Warnings</strong>
              <span>{migrationWriteStatus(legacyConfigApplyResult, Boolean(legacyConfigApplyResult?.writtenPathLabels.length))}</span>
              __SAFETY_BODY__
              {legacyConfigPreview}
              {legacyConfigApplyResult}
            </section>
          );
        }
        """.replace("__SAFETY_BODY__", safety_body)
    else:
        body = """
        export function PreferencesPanel() {
          return <section aria-label="Application preferences">Preferences</section>;
        }
        """
    write(root / smoke_user_flows.PREFERENCES_PANEL_SOURCE, body)


def create_provider_domain_fixture(root: Path) -> None:
    write(
        root / smoke_user_flows.PROVIDER_DOMAIN_SOURCE,
        """
        export type ProviderKind = "yike" | "fox" | "readboard_snapshot";
        export type LegacyImportCaptureHelperKind = "sgf_payload" | "protocol_snapshot" | "image_ocr" | "external_window_capture" | "external_client_capture";
        export type LegacyImportCaptureHelperStatus = "available" | "recoverable_unsupported" | "error";
        export type LegacyImportCaptureHelperRequest = {
          kind: LegacyImportCaptureHelperKind;
          payload?: string | null;
          image_path?: string | null;
          image_base64?: string | null;
          window_title?: string | null;
          client_name?: string | null;
          process_id?: number | null;
          timeout_ms?: number | null;
          metadata: Record<string, string>;
        };
        export type LegacyImportCaptureHelperResult = {
          kind: LegacyImportCaptureHelperKind;
          status: LegacyImportCaptureHelperStatus;
          title: string;
          message: string;
          recoverable: boolean;
          imported: boolean;
          boardReplacement: "none" | "imported" | "preview_only";
          warnings: string[];
          details: Record<string, string>;
        };
        """,
    )


def create_provider_api_fixture(
    root: Path,
    *,
    legacy_helper_api: bool = True,
    legacy_helper_api_command: str = smoke_user_flows.LEGACY_IMPORT_CAPTURE_HELPER_COMMAND,
) -> None:
    legacy_helper_body = """
        export async function previewLegacyImportCaptureHelper(request: LegacyImportCaptureHelperRequest): Promise<LegacyImportCaptureHelperResult> {
          try {
            return await invoke<LegacyImportCaptureHelperResult>("__LEGACY_HELPER_API_COMMAND__", { request });
          } catch (error) {
            return legacyImportCaptureHelperFallback(request, String(error));
          }
        }

        function legacyImportCaptureHelperFallback(request: LegacyImportCaptureHelperRequest, backendMessage?: string): LegacyImportCaptureHelperResult {
          if (request.kind === "sgf_payload" || request.kind === "protocol_snapshot") {
            return { kind: request.kind, status: "available", title: "SGF/payload helper", message: "visible helper path only", recoverable: true, imported: false, boardReplacement: "none", warnings: [], details: {} };
          }
          return {
            kind: request.kind,
            status: "recoverable_unsupported",
            title: request.kind === "image_ocr" ? "OCR/image helper" : "External window/client capture",
            message: "No SGF was imported and the board was not replaced.",
            recoverable: true,
            imported: false,
            boardReplacement: "none",
            warnings: ["No stale, guessed, or partial board replacement was applied.", backendMessage ?? ""],
            details: { no_stale_board_replacement: "true" }
          };
        }
    """.replace("__LEGACY_HELPER_API_COMMAND__", legacy_helper_api_command) if legacy_helper_api else ""
    write(
        root / smoke_user_flows.PROVIDER_API_SOURCE,
        f"""
        import {{ invoke }} from "@tauri-apps/api/core";
        import type {{ LegacyImportCaptureHelperRequest, LegacyImportCaptureHelperResult }} from "../domain/providers";

        {legacy_helper_body}
        """,
    )


def create_provider_panel_fixture(root: Path, *, legacy_helper_ui: bool = True) -> None:
    legacy_helper_body = """
          <section data-testid="legacy-import-capture-helper-surface" aria-label="Legacy import and capture helpers">
            <section data-testid="legacy-helper-sgf-payload">SGF/payload helper</section>
            <section data-testid="legacy-helper-protocol-snapshot">Protocol snapshot helper</section>
            <section data-testid="legacy-helper-ocr-unsupported">OCR/image helper recoverable unsupported</section>
            <section data-testid="legacy-helper-external-capture-unsupported">External window/client capture recoverable unsupported</section>
            <p data-testid="legacy-helper-no-board-replacement">Unsupported helpers do not import SGF; board was not replaced with guessed, stale, or partial data.</p>
            <dl data-testid="legacy-helper-status"><dd>not imported</dd><dd>not replaced</dd></dl>
            <button onClick={() => handleLegacyHelperStatus("image_ocr")}>Check OCR status</button>
          </section>
    """ if legacy_helper_ui else ""
    write(
        root / smoke_user_flows.PROVIDER_PANEL_SOURCE,
        f"""
        import {{ previewLegacyImportCaptureHelper }} from "../api/providers";

        export function ProviderPanel() {{
          const legacyHelperResult = null;
          async function handleLegacyHelperStatus(kind) {{
            return await previewLegacyImportCaptureHelper({{ kind, metadata: {{}} }});
          }}
          return (
            <section data-testid="provider-panel">
              <textarea data-testid="provider-payload-textarea" aria-label="Provider payload or SGF" />
              <button data-testid="provider-import-payload">Import pasted payload</button>
              <textarea data-testid="readboard-protocol-textarea" aria-label="Readboard protocol preview line" />
              <button data-testid="readboard-preview-snapshot">Preview snapshot</button>
              <button data-testid="readboard-import-snapshot">Import snapshot</button>
              {{legacyHelperResult}}
              {legacy_helper_body}
            </section>
          );
        }}
        """,
    )


def create_engine_setup_panel_fixture(root: Path, *, runtime_asset_ui: bool = True) -> None:
    if runtime_asset_ui:
        body = """
        import { checkEngineAssets, validateRuntimeAssetLayout } from "../api/backend";

        export function EngineSetupPanel({ analysisProgress = null, activeJobId = null, onCancelAnalysis = null }) {
          const [runtimeAssetValidation, setRuntimeAssetValidation] = useState(null);
          const [runtimeAssetStatus, setRuntimeAssetStatus] = useState("Checking bundled/runtime assets...");
          const enginePath = "";
          const modelPath = "";
          const configPath = "";
          const placeholderCount = runtimeAssetValidation?.placeholders.length ?? 0;
          const progressLabel = analysisProgress
            ? `${analysisProgress.completed}/${analysisProgress.expected} positions, move ${analysisProgress.turn}`
            : "No active analysis";
          const progressPercent = analysisProgress?.expected
            ? Math.round((analysisProgress.completed / analysisProgress.expected) * 100)
            : 0;

          async function handleCheckRuntimeAssets() {
            const validation = await validateRuntimeAssetLayout();
            setRuntimeAssetValidation(validation);
            setRuntimeAssetStatus(runtimeAssetSummary(validation));
          }

          function runtimeAssetSummary(validation) {
            return `${validation.missing.length} missing, ${validation.placeholders.length} placeholder`;
          }

          function runtimeAssetMessages(validation) {
            return [...validation.warnings, ...validation.placeholders.map((placeholder) => placeholder.message)];
          }

          async function handleCheckLocalAssets() {
            await checkEngineAssets({ engine_path: enginePath, model_path: modelPath, config_path: configPath });
          }

          return (
            <section aria-label="KataGo engine setup">
              <div aria-label="Bundled runtime asset status">
                <strong>Bundled/runtime assets</strong>
                <button onClick={handleCheckRuntimeAssets}>Refresh runtime assets</button>
                <span>{runtimeAssetStatus}</span>
                <span>{runtimeAssetValidation}</span>
                <span>{placeholderCount}</span>
                <span>{runtimeAssetValidation?.checks.map((check) => check.status).join(",")}</span>
                <span>{runtimeAssetValidation ? runtimeAssetMessages(runtimeAssetValidation).join("|") : ""}</span>
              </div>
              <p>Large KataGo models are not bundled by this repository.</p>
              <div aria-label="Local asset configuration">
                <strong>Local asset configuration</strong>
                <input value={enginePath} />
                <input value={modelPath} />
                <input value={configPath} />
                <button onClick={handleCheckLocalAssets}>Check assets</button>
              </div>
              <div className="analysis-progress" aria-label="KataGo analysis progress">
                <span>{progressLabel}</span>
                <progress value={progressPercent} max={100} />
                <span>{activeJobId}</span>
              </div>
              <button>Analyze game</button>
              {activeJobId ? <button onClick={() => onCancelAnalysis?.()}>Cancel</button> : null}
            </section>
          );
        }
        """
    else:
        body = """
        import { checkEngineAssets } from "../api/backend";

        export function EngineSetupPanel({ analysisProgress = null, activeJobId = null, onCancelAnalysis = null }) {
          const enginePath = "";
          const modelPath = "";
          const configPath = "";
          const progressLabel = analysisProgress
            ? `${analysisProgress.completed}/${analysisProgress.expected} positions, move ${analysisProgress.turn}`
            : "No active analysis";
          const progressPercent = analysisProgress?.expected
            ? Math.round((analysisProgress.completed / analysisProgress.expected) * 100)
            : 0;
          return (
            <section>
              {enginePath}{modelPath}{configPath}{checkEngineAssets}
              <div className="analysis-progress">{progressLabel}{progressPercent}{activeJobId}</div>
              <button>Analyze game</button>
              {activeJobId ? <button onClick={() => onCancelAnalysis?.()}>Cancel</button> : null}
            </section>
          );
        }
        """
    write(root / smoke_user_flows.ENGINE_SETUP_PANEL_SOURCE, body)


def re_identifier_parts(value: str) -> list[str]:
    return [part[:1].upper() + part[1:] for part in value.split()]


if __name__ == "__main__":
    unittest.main()
