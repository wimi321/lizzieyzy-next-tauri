from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke_packaged_native_dialog_sgf.py"
USER_FLOWS = ROOT / "scripts" / "smoke_user_flows.py"

USER_SPEC = importlib.util.spec_from_file_location("smoke_user_flows", USER_FLOWS)
assert USER_SPEC is not None and USER_SPEC.loader is not None
smoke_user_flows = importlib.util.module_from_spec(USER_SPEC)
sys.modules["smoke_user_flows"] = smoke_user_flows
USER_SPEC.loader.exec_module(smoke_user_flows)

SPEC = importlib.util.spec_from_file_location("smoke_packaged_native_dialog_sgf", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke_packaged_native_dialog_sgf = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_packaged_native_dialog_sgf"] = smoke_packaged_native_dialog_sgf
SPEC.loader.exec_module(smoke_packaged_native_dialog_sgf)


class SmokePackagedNativeDialogSgfTests(unittest.TestCase):
    def test_pending_evidence_validates(self) -> None:
        evidence = smoke_packaged_native_dialog_sgf.pending_evidence()

        failures = smoke_user_flows.validate_packaged_native_dialog_sgf_pending_evidence(evidence)

        self.assertEqual([], failures)
        self.assertEqual("pending", evidence["status"])
        self.assertFalse(evidence["fullNativeDialogParity"])

    def test_validate_only_accepts_pending_file(self) -> None:
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "packaged-native-dialog.json"
            output.write_text(json.dumps(smoke_packaged_native_dialog_sgf.pending_evidence()), encoding="utf-8")

            result = smoke_packaged_native_dialog_sgf.main(["--validate-only", "--evidence-out", str(output)])

            self.assertEqual(0, result)

    def test_write_pending_writes_valid_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "packaged-native-dialog.json"

            result = smoke_packaged_native_dialog_sgf.main(["--write-pending", "--evidence-out", str(output)])

            self.assertEqual(0, result)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual([], smoke_user_flows.validate_packaged_native_dialog_sgf_pending_evidence(evidence))

    def test_default_run_invokes_collector(self) -> None:
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "packaged-native-dialog.json"
            with patch.object(smoke_packaged_native_dialog_sgf, "run_collector", return_value=1) as collector:
                result = smoke_packaged_native_dialog_sgf.main(["--evidence-out", str(output), "--timeout", "1"])

            self.assertEqual(1, result)
            collector.assert_called_once()


if __name__ == "__main__":
    unittest.main()
