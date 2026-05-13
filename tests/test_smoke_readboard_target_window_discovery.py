from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke_readboard_target_window_discovery.py"
SPEC = importlib.util.spec_from_file_location("smoke_readboard_target_window_discovery", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke_readboard_target_window_discovery = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_readboard_target_window_discovery"] = smoke_readboard_target_window_discovery
SPEC.loader.exec_module(smoke_readboard_target_window_discovery)


class ReadboardTargetWindowDiscoveryScriptTests(unittest.TestCase):
    def test_committed_evidence_validates(self) -> None:
        result = smoke_readboard_target_window_discovery.main(["--verbose"])

        self.assertEqual(0, result)

    def test_validate_missing_evidence_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"

            result = smoke_readboard_target_window_discovery.main(["--evidence-out", str(missing)])

            self.assertEqual(1, result)

    def test_static_only_evidence_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            source = ROOT / "docs/qa/readboard-target-window-discovery-smoke-macos.json"
            evidence = json.loads(source.read_text(encoding="utf-8"))
            evidence["runtimeObserved"] = False
            evidence["collectionMethod"] = "static_fixture_only"
            target = Path(tmp) / "evidence.json"
            target.write_text(json.dumps(evidence), encoding="utf-8")

            result = smoke_readboard_target_window_discovery.main(["--evidence-out", str(target)])

            self.assertEqual(1, result)


if __name__ == "__main__":
    unittest.main()
