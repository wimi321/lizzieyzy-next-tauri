from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_completion_audit.py"
SPEC = importlib.util.spec_from_file_location("validate_completion_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validate_completion_audit = importlib.util.module_from_spec(SPEC)
sys.modules["validate_completion_audit"] = validate_completion_audit
SPEC.loader.exec_module(validate_completion_audit)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def write_json(path: Path, content: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")


class ValidateCompletionAuditTests(unittest.TestCase):
    def test_accepts_scoped_completion_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_completion_audit(root)

            results = validate_completion_audit.validate(root)

            self.assertEqual([], [result for result in results if not result.ok])

    def test_rejects_missing_audit_doc(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            results = validate_completion_audit.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("completion_audit_doc", failures)

    def test_rejects_missing_required_sections(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "docs/qa/basic-smoke.json", {"status": "pass"})
            write(
                root / "docs/COMPLETION_AUDIT.md",
                """
                # Completion Audit

                A scoped audit references `docs/qa/basic-smoke.json`.
                """,
            )

            results = validate_completion_audit.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("required_sections", failures)

    def test_rejects_100_percent_overclaim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_completion_audit(root, extra_criteria="The project is 100% complete.")

            results = validate_completion_audit.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("overclaims", failures)
            self.assertIn("100 percent complete", failures["overclaims"])

    def test_rejects_release_and_signing_overclaims(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_completion_audit(root, extra_criteria="Official release published. The updater is ready.")

            results = validate_completion_audit.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("overclaims", failures)
            self.assertIn("official release", failures["overclaims"])
            self.assertIn("updater", failures["overclaims"])

    def test_rejects_provider_readboard_full_parity_overclaim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_completion_audit(root, extra_criteria="Provider/readboard full parity complete for the release.")

            results = validate_completion_audit.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("overclaims", failures)
            self.assertIn("provider/readboard", failures["overclaims"])

    def test_rejects_missing_evidence_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_completion_audit(root, write_evidence=False)

            results = validate_completion_audit.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("evidence_references", failures)
            self.assertIn("is missing", failures["evidence_references"])

    def test_rejects_non_pass_evidence_status(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_completion_audit(root, evidence_status="failed")

            results = validate_completion_audit.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("evidence_references", failures)
            self.assertIn("status must be pass", failures["evidence_references"])

    def test_rejects_no_blockers_claim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_completion_audit(root, blockers="None. No blockers remain.")

            results = validate_completion_audit.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("missing_blockers", failures)
            self.assertIn("must not claim no blockers", failures["missing_blockers"])


def create_completion_audit(
    root: Path,
    *,
    extra_criteria: str = "",
    blockers: str = "- Remaining external blockers include signing, notarization, updater readiness, provider/readboard parity, and full legacy parity.",
    evidence_status: str = "pass",
    write_evidence: bool = True,
) -> None:
    if write_evidence:
        write_json(
            root / "docs/qa/basic-smoke.json",
            {
                "schema": "lizzieyzy.test-evidence.v1",
                "status": evidence_status,
                "boundaries": {
                    "fullLegacyParity": False,
                    "releasePublished": False,
                },
            },
        )
    write(
        root / "docs/COMPLETION_AUDIT.md",
        f"""
        # Completion Audit

        ## Completion Criteria

        The current scope is a scoped completion audit. It does not claim full legacy parity,
        official release publication, signed installers, notarization, updater readiness,
        bundled large model completion, or provider/readboard full parity.
        {extra_criteria}

        ## Evidence

        - Scoped evidence: `docs/qa/basic-smoke.json`

        ## Missing Blockers

        {blockers}
        """,
    )


if __name__ == "__main__":
    unittest.main()
