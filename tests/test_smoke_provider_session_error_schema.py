from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke_provider_session_error_schema.py"
SPEC = importlib.util.spec_from_file_location("smoke_provider_session_error_schema", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke_provider_session_error_schema = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_provider_session_error_schema"] = smoke_provider_session_error_schema
SPEC.loader.exec_module(smoke_provider_session_error_schema)


class ProviderSessionErrorSchemaScriptTests(unittest.TestCase):
    def test_committed_evidence_validates(self) -> None:
        result = smoke_provider_session_error_schema.main(["--verbose"])

        self.assertEqual(0, result)

    def test_missing_evidence_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            result = smoke_provider_session_error_schema.main(["--evidence-out", str(Path(tmp) / "missing.json")])

            self.assertEqual(1, result)

    def test_missing_fixture_class_fails(self) -> None:
        self.assert_invalid(
            lambda evidence: self.remove_fixture_class(evidence, "auth_required"),
            "fixtureManifest missing classes: auth_required",
        )

    def test_anti_bot_challenge_fixture_class_is_required(self) -> None:
        self.assert_invalid(
            lambda evidence: self.remove_fixture_class(evidence, "blocked_or_challenged"),
            "fixtureManifest missing classes: blocked_or_challenged",
        )

    def test_empty_result_fixture_class_is_required(self) -> None:
        self.assert_invalid(
            lambda evidence: self.remove_fixture_class(evidence, "empty_result"),
            "fixtureManifest missing classes: empty_result",
        )

    def test_overclaim_fails(self) -> None:
        self.assert_invalid(lambda evidence: evidence.__setitem__("realProviderParity", True), "realProviderParity must be false")

    def test_frontend_display_must_be_typed(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            for check in evidence["checks"]:
                if isinstance(check, dict) and check.get("name") == "frontend_display":
                    details = check["details"]
                    assert isinstance(details, dict)
                    details["typedFrontendDisplay"] = False

        self.assert_invalid(mutate, "frontend_display.typedFrontendDisplay must be true")

    def test_empty_result_frontend_display_class_is_required(self) -> None:
        def mutate(evidence: dict[str, object]) -> None:
            self.remove_frontend_display_class(evidence, "empty_result")

        self.assert_invalid(mutate, "frontend_display missing classes: empty_result")

    def remove_fixture_class(self, evidence: dict[str, object], fixture_class: str) -> None:
        evidence["fixtureManifest"] = [
            item
            for item in evidence["fixtureManifest"]
            if not (isinstance(item, dict) and item.get("class") == fixture_class)
        ]

    def remove_frontend_display_class(self, evidence: dict[str, object], fixture_class: str) -> None:
        for check in evidence["checks"]:
            if isinstance(check, dict) and check.get("name") == "frontend_display":
                details = check["details"]
                assert isinstance(details, dict)
                messages = details["messages"]
                assert isinstance(messages, list)
                details["messages"] = [
                    message
                    for message in messages
                    if not (isinstance(message, dict) and message.get("class") == fixture_class)
                ]

    def assert_invalid(self, mutate, expected: str) -> None:
        with TemporaryDirectory() as tmp:
            source = ROOT / "docs/qa/provider-session-error-schema-smoke.json"
            evidence = json.loads(source.read_text(encoding="utf-8"))
            mutate(evidence)
            failures = smoke_provider_session_error_schema.smoke_user_flows.validate_provider_session_error_schema_smoke_evidence(
                evidence
            )
            self.assertIn(expected, failures)
            path = Path(tmp) / "evidence.json"
            path.write_text(json.dumps(evidence), encoding="utf-8")

            result = smoke_provider_session_error_schema.main(["--evidence-out", str(path)])

            self.assertEqual(1, result)


if __name__ == "__main__":
    unittest.main()
