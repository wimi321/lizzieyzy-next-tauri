from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_release_readiness.py"
SPEC = importlib.util.spec_from_file_location("validate_release_readiness", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validate_release_readiness = importlib.util.module_from_spec(SPEC)
sys.modules["validate_release_readiness"] = validate_release_readiness
SPEC.loader.exec_module(validate_release_readiness)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


class ValidateReleaseReadinessTests(unittest.TestCase):
    def test_accepts_current_scoped_unsigned_policy_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_readiness_docs(root)

            results = validate_release_readiness.validate(root)

            self.assertEqual([], [result for result in results if not result.ok])

    def test_rejects_stale_smoke_count(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_readiness_docs(root, checklist_extra="Smoke gate: 44 passed, 0 pending.")

            results = validate_release_readiness.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("stale_smoke_counts", failures)
            self.assertIn("44 passed", failures["stale_smoke_counts"])

    def test_rejects_current_central_smoke_count_54(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_readiness_docs(
                root,
                checklist_extra=(
                    "python3 scripts/smoke_user_flows.py --verbose currently reports "
                    "`54 passed, 0 failed, 0 pending` for the central smoke gate."
                ),
            )

            results = validate_release_readiness.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("stale_smoke_counts", failures)
            self.assertIn("57 passed, 0 failed, 0 pending", failures["stale_smoke_counts"])
            self.assertIn("54 passed", failures["stale_smoke_counts"])

    def test_rejects_current_central_smoke_count_55(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_readiness_docs(
                root,
                qa_extra=(
                    "The central smoke gate currently reports "
                    "`55 passed, 0 failed, 0 pending`."
                ),
            )

            results = validate_release_readiness.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("stale_smoke_counts", failures)
            self.assertIn("57 passed, 0 failed, 0 pending", failures["stale_smoke_counts"])
            self.assertIn("55 passed", failures["stale_smoke_counts"])

    def test_allows_self_excluding_baseline_54_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_readiness_docs(root)
            write_release_readiness_evidence(root, passed=54, baseline_excludes=["release_readiness_preflight"])

            results = validate_release_readiness.validate(root)

            self.assertEqual([], [result for result in results if not result.ok])

    def test_rejects_baseline_54_without_self_exclusion(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_readiness_docs(root)
            write_release_readiness_evidence(root, passed=54, baseline_excludes=[])

            results = validate_release_readiness.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("release_readiness_preflight_baseline", failures)
            self.assertIn("self-excluding 54/0/0", failures["release_readiness_preflight_baseline"])

    def test_allows_completion_audit_self_excluding_baseline_55_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_readiness_docs(root)
            write_completion_audit_evidence(root, passed=55, baseline_excludes=["completion_audit_gate"])

            results = validate_release_readiness.validate(root)

            self.assertEqual([], [result for result in results if not result.ok])

    def test_rejects_completion_audit_baseline_55_without_self_exclusion(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_readiness_docs(root)
            write_completion_audit_evidence(root, passed=55, baseline_excludes=[])

            results = validate_release_readiness.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("completion_audit_gate_baseline", failures)
            self.assertIn("self-excluding 55/0/0", failures["completion_audit_gate_baseline"])

    def test_rejects_full_legacy_parity_overclaim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_readiness_docs(root, checklist_extra='Release metadata says "fullLegacyParity": true.')

            results = validate_release_readiness.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("release_overclaims", failures)
            self.assertIn("fulllegacyparity", failures["release_overclaims"].lower())

    def test_rejects_structured_true_release_boundary(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_readiness_docs(root, qa_extra='Evidence says "productionSigned": true for the release.')

            results = validate_release_readiness.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("release_overclaims", failures)
            self.assertIn("production signed", failures["release_overclaims"])

    def test_rejects_missing_rollback_policy_state(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_readiness_docs(root, omit_rollback=True)

            results = validate_release_readiness.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("release_policy_status", failures)
            self.assertIn("rollback", failures["release_policy_status"])

    def test_rejects_provider_readboard_overclaim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_readiness_docs(root, qa_extra="Provider/readboard parity validated for this release.")

            results = validate_release_readiness.validate(root)

            failures = {result.name: result.detail for result in results if not result.ok}
            self.assertIn("release_overclaims", failures)
            self.assertIn("provider/readboard", failures["release_overclaims"])


def create_readiness_docs(
    root: Path,
    *,
    checklist_extra: str = "",
    qa_extra: str = "",
    matrix_extra: str = "",
    omit_rollback: bool = False,
) -> None:
    rollback_checklist = "" if omit_rollback else "- Rollback policy state: documented and scoped.\n"
    rollback_process = "" if omit_rollback else "## Rollback\nRollback plan records affected platforms and checksums.\n"
    write(
        root / "docs/RELEASE_CHECKLIST.md",
        f"""
        # Release Checklist

        - Current posture: unsigned scoped validation with external gates.
        - Signing state: unsigned until signing secrets are configured.
        - Notarization state: not notarized until release credentials are configured.
        - Updater state: updater readiness is false and outside this scoped gate.
        {rollback_checklist}
        {checklist_extra}
        """,
    )
    write(
        root / "docs/QA_REPORT.md",
        f"""
        # QA Report

        Scoped evidence only. This does not claim full legacy parity, signed release,
        notarized release, updater readiness, provider/readboard parity, readboard parity,
        bundled large model parity, official release publication, or full release parity.

        {qa_extra}
        """,
    )
    write(
        root / "docs/LEGACY_PARITY_MATRIX.md",
        f"""
        # Legacy Parity Matrix

        Status values include partial and external-validation-needed. Do not claim full Java/Swing parity.
        Release rows are scoped and unsigned; external gates remain before production release.

        {matrix_extra}
        """,
    )
    write(
        root / "docs/RELEASE_PROCESS.md",
        f"""
        # Release Process

        Signing: release assets are unsigned until credentials are configured.
        Notarization: macOS notarization is required before a production release.
        Updater: updater signing is out of scope until update artifacts are introduced.
        {rollback_process}
        """,
    )


def write_release_readiness_evidence(root: Path, *, passed: int, baseline_excludes: list[str]) -> None:
    write_gate_evidence(
        root / "docs/qa/release-readiness-preflight.json",
        schema="lizzieyzy.release-readiness-preflight.v1",
        name="release_readiness_preflight",
        passed=passed,
        baseline_excludes=baseline_excludes,
    )


def write_completion_audit_evidence(root: Path, *, passed: int, baseline_excludes: list[str]) -> None:
    write_gate_evidence(
        root / "docs/qa/completion-audit-gate.json",
        schema="lizzieyzy.completion-audit-gate.v1",
        name="completion_audit_gate",
        passed=passed,
        baseline_excludes=baseline_excludes,
    )


def write_gate_evidence(path: Path, *, schema: str, name: str, passed: int, baseline_excludes: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": schema,
                "name": name,
                "status": "pass",
                "smokeUserFlows": {
                    "passed": passed,
                    "failed": 0,
                    "pending": 0,
                    "baselineExcludes": baseline_excludes,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
