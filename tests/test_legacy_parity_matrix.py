from __future__ import annotations

import importlib.util
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_legacy_parity.py"
SPEC = importlib.util.spec_from_file_location("validate_legacy_parity", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validate_legacy_parity = importlib.util.module_from_spec(SPEC)
sys.modules["validate_legacy_parity"] = validate_legacy_parity
SPEC.loader.exec_module(validate_legacy_parity)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


class LegacyParityMatrixTests(unittest.TestCase):
    def test_repository_matrix_passes_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]

        results = validate_legacy_parity.LegacyParityValidator(root).run()

        failures = [result for result in results if not result.ok]
        self.assertEqual([], failures)

    def test_rejects_forbidden_completion_claim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_minimal_matrix(root, extra_intro="This is 100% complete.\n")

            results = validate_legacy_parity.LegacyParityValidator(root).run()

            failures = {result.name for result in results if not result.ok}
            self.assertIn("forbidden_claims", failures)

    def test_rejects_invalid_status_token(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_minimal_matrix(root, status_override="mostly done")

            results = validate_legacy_parity.LegacyParityValidator(root).run()

            failures = {result.name for result in results if not result.ok}
            self.assertIn("status_tokens", failures)

    def _write_minimal_matrix(
        self,
        root: Path,
        *,
        extra_intro: str = "",
        status_override: str | None = None,
    ) -> None:
        statuses = {
            "UI": status_override or "partial",
            "SGF And Editing": "complete",
            "KataGo": "partial",
            "Provider And readboard": "external-validation-needed",
            "Settings": "missing",
            "Packaging": "complete",
        }
        sections = []
        for section in validate_legacy_parity.REQUIRED_SECTIONS:
            sections.append(
                f"""
## {section}

| Legacy Capability | Current Status | Acceptance Evidence | External Gate | Notes |
| --- | --- | --- | --- | --- |
| {section} capability | `{statuses[section]}` | Evidence names tests and smoke checks for this area. | External gate recorded or explicitly not required. | Notes explain scope. |
"""
            )
        write(root / "docs/LEGACY_PARITY_MATRIX.md", "# Legacy Parity Matrix\n\n" + extra_intro + "\n".join(sections))


if __name__ == "__main__":
    unittest.main()
