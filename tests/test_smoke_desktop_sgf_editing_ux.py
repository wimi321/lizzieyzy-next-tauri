from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke_desktop_sgf_editing_ux.py"
SPEC = importlib.util.spec_from_file_location("smoke_desktop_sgf_editing_ux", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke_desktop_sgf_editing_ux = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_desktop_sgf_editing_ux"] = smoke_desktop_sgf_editing_ux
SPEC.loader.exec_module(smoke_desktop_sgf_editing_ux)

USER_FLOWS_TEST = ROOT / "tests" / "test_smoke_user_flows.py"
USER_FLOWS_SPEC = importlib.util.spec_from_file_location("test_smoke_user_flows_helpers", USER_FLOWS_TEST)
assert USER_FLOWS_SPEC is not None and USER_FLOWS_SPEC.loader is not None
test_smoke_user_flows = importlib.util.module_from_spec(USER_FLOWS_SPEC)
sys.modules["test_smoke_user_flows_helpers"] = test_smoke_user_flows
USER_FLOWS_SPEC.loader.exec_module(test_smoke_user_flows)


class DesktopSgfEditingUxSmokeTests(unittest.TestCase):
    def test_build_evidence_from_runtime_and_ui_surface(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            test_smoke_user_flows.create_complete_smoke_fixture(root)
            test_smoke_user_flows.write_valid_tauri_runtime_ui_evidence(root)

            evidence = smoke_desktop_sgf_editing_ux.build_evidence(
                root,
                Path(test_smoke_user_flows.smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_EVIDENCE),
            )

            self.assertEqual("pass", evidence["status"])
            self.assertEqual([], smoke_desktop_sgf_editing_ux.validate_evidence(evidence))
            self.assertEqual("source_static_plus_tauri_runtime_chain", evidence["collectionMethod"])
            self.assertIs(evidence["runtimeDomObserved"], False)
            self.assertIs(evidence["screenshotObserved"], False)
            surface = evidence["uiUxSurface"]
            self.assertIsInstance(surface, dict)
            self.assertIs(surface["legacyShellVisible"], True)
            self.assertIs(surface["treePanelVisible"], True)
            self.assertIs(surface["annotationEditorVisible"], True)
            self.assertIs(surface["nativeDialogClickCovered"], False)

    def test_build_evidence_fails_when_annotation_editor_surface_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            test_smoke_user_flows.create_complete_smoke_fixture(root)
            test_smoke_user_flows.write_valid_tauri_runtime_ui_evidence(root)
            annotation_path = root / test_smoke_user_flows.smoke_user_flows.SGF_ANNOTATION_PANEL_SOURCE
            annotation_path.write_text("export function SgfAnnotationPanel() { return null; }\n", encoding="utf-8")

            evidence = smoke_desktop_sgf_editing_ux.build_evidence(
                root,
                Path(test_smoke_user_flows.smoke_user_flows.TAURI_RUNTIME_UI_SMOKE_EVIDENCE),
            )

            self.assertEqual("fail", evidence["status"])
            failures = smoke_desktop_sgf_editing_ux.validate_evidence(evidence)
            self.assertIn("status must be pass", failures)
            self.assertIn("required checks not pass: annotation_editor_visible", failures)
            self.assertIn("uiUxSurface.annotationEditorVisible must be true", failures)

    def test_validator_rejects_claimed_native_dialog_click_coverage(self) -> None:
        evidence = test_smoke_user_flows.valid_desktop_sgf_editing_ux_evidence()
        surface = evidence["uiUxSurface"]
        boundaries = evidence["boundaries"]
        assert isinstance(surface, dict)
        assert isinstance(boundaries, dict)
        surface["nativeDialogClickCovered"] = True
        boundaries["nativeDialogClickCovered"] = True

        failures = smoke_desktop_sgf_editing_ux.validate_evidence(evidence)

        self.assertIn("uiUxSurface.nativeDialogClickCovered must be false", failures)
        self.assertIn("boundaries.nativeDialogClickCovered must be false", failures)


if __name__ == "__main__":
    unittest.main()
