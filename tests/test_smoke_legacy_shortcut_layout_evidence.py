from __future__ import annotations

import importlib.util
import py_compile
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke_legacy_shortcut_layout_evidence.py"


class SmokeLegacyShortcutLayoutEvidenceTests(unittest.TestCase):
    def test_script_compiles(self) -> None:
        py_compile.compile(str(SCRIPT), doraise=True)

    def test_script_delegates_to_layout_runner(self) -> None:
        scripts_dir = ROOT / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        spec = importlib.util.spec_from_file_location("smoke_legacy_shortcut_layout_evidence", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        import smoke_legacy_layout_parity

        self.assertIs(module.main, smoke_legacy_layout_parity.main)


if __name__ == "__main__":
    unittest.main()
