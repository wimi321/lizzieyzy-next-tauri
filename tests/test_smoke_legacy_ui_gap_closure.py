from __future__ import annotations

import importlib.util
import json
import py_compile
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke_legacy_ui_gap_closure.py"


def load_module():
    scripts_dir = ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location("smoke_legacy_ui_gap_closure", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SmokeLegacyUiGapClosureTests(unittest.TestCase):
    def test_script_compiles(self) -> None:
        py_compile.compile(str(SCRIPT), doraise=True)

    def test_build_evidence_from_runtime_shortcut_layout_source(self) -> None:
        module = load_module()
        import test_smoke_user_flows

        evidence = module.build_evidence(test_smoke_user_flows.valid_legacy_shortcut_layout_evidence())

        self.assertEqual("lizzieyzy.legacy-ui-gap-closure.v1", evidence["schema"])
        self.assertEqual("pass", evidence["status"])
        self.assertTrue(evidence["runtimeObserved"])
        self.assertFalse(evidence["fullLegacyParity"])
        self.assertGreaterEqual(len(evidence["unsupportedExternalOnlyActions"]), 1)
        module.validate_or_raise(evidence)

    def test_static_shortcut_layout_source_is_rejected(self) -> None:
        module = load_module()
        import test_smoke_user_flows

        with self.assertRaises(ValueError) as context:
            module.build_evidence(test_smoke_user_flows.static_only_legacy_shortcut_layout_evidence())

        self.assertIn("not valid runtime evidence", str(context.exception))

    def test_cli_writes_pending_and_validates_pass(self) -> None:
        module = load_module()
        import test_smoke_user_flows

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            output = root / "gap.json"
            source.write_text(json.dumps(test_smoke_user_flows.valid_legacy_shortcut_layout_evidence()), encoding="utf-8")

            self.assertEqual(0, module.main(["--source-evidence", str(source), "--evidence-out", str(output)]))
            self.assertEqual(0, module.main(["--validate-only", "--evidence-out", str(output)]))

            pending = root / "pending.json"
            self.assertEqual(0, module.main(["--write-pending", "--evidence-out", str(pending)]))
            written = json.loads(pending.read_text(encoding="utf-8"))
            self.assertEqual("pending", written["status"])


if __name__ == "__main__":
    unittest.main()
