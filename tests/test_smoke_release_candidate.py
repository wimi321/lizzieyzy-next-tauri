from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke_release_candidate.py"
SPEC = importlib.util.spec_from_file_location("smoke_release_candidate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke_release_candidate = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_release_candidate"] = smoke_release_candidate
SPEC.loader.exec_module(smoke_release_candidate)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def write_json(path: Path, content: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")


class SmokeReleaseCandidateTests(unittest.TestCase):
    def test_missing_artifact_is_pending_not_failure(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_release_candidate_fixture(root)

            results = smoke_release_candidate.ReleaseCandidateSmoke(root).run()

            failures = [result for result in results if result.status == "FAIL"]
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertEqual([], failures)
            self.assertIn("macos_build_artifact", pending)

    def test_dangerous_full_parity_claim_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_release_candidate_fixture(root)
            write(
                root / "docs/RELEASE_CHECKLIST.md",
                """
                # Release Checklist

                External pending KataGo readboard provider gates remain documented.
                Full legacy parity complete.
                """,
            )

            results = smoke_release_candidate.ReleaseCandidateSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("qa_release_guardrails", failures)
            self.assertIn("dangerous release/parity claim", failures["qa_release_guardrails"])

    def test_dangerous_one_to_one_parity_claims_fail(self) -> None:
        dangerous_claims = [
            "Legacy 1:1 parity complete.",
            "1:1 legacy parity complete.",
            "1:1 UI reconstruction complete.",
        ]
        for claim in dangerous_claims:
            with self.subTest(claim=claim), TemporaryDirectory() as tmp:
                root = Path(tmp)
                create_release_candidate_fixture(root)
                write(
                    root / "docs/RELEASE_CHECKLIST.md",
                    f"""
                    # Release Checklist

                    External pending KataGo readboard provider gates remain documented.
                    {claim}
                    """,
                )

                results = smoke_release_candidate.ReleaseCandidateSmoke(root).run()

                failures = {result.name: result.detail for result in results if result.status == "FAIL"}
                self.assertIn("qa_release_guardrails", failures)
                self.assertIn("dangerous release/parity claim", failures["qa_release_guardrails"])

    def test_non_claim_one_to_one_language_does_not_fail_guardrails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_release_candidate_fixture(root)
            write(
                root / "docs/RELEASE_CHECKLIST.md",
                """
                # Release Checklist

                Keep external pending gates for KataGo, readboard, and provider checks before release claims.
                Track 1:1 legacy parity as pending until runtime evidence exists.
                """,
            )

            results = smoke_release_candidate.ReleaseCandidateSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            pending = {result.name: result.detail for result in results if result.status == "PENDING"}
            self.assertEqual({}, failures)
            self.assertIn("macos_build_artifact", pending)

    def test_smoke_command_missing_fails_release_candidate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_release_candidate_fixture(root, omitted_commands={"validate_runtime_asset_layout"})

            results = smoke_release_candidate.ReleaseCandidateSmoke(root).run()

            failures = {result.name: result.detail for result in results if result.status == "FAIL"}
            self.assertIn("smoke_user_flows", failures)
            self.assertIn("validate_runtime_asset_layout function", failures["smoke_user_flows"])


def create_release_candidate_fixture(
    root: Path,
    *,
    omitted_commands: set[str] | None = None,
) -> None:
    omitted_commands = omitted_commands or set()
    write(root / "scripts/smoke_user_flows.py", (ROOT / "scripts/smoke_user_flows.py").read_text(encoding="utf-8"))
    for rel in smoke_release_candidate.KEY_SCRIPTS:
        if rel != "scripts/smoke_user_flows.py":
            write(root / rel, "#!/usr/bin/env python3\n")
    write(
        root / "docs/QA_REPORT.md",
        """
        # QA Report

        External gates remain pending for KataGo, readboard, and provider runtime evidence.
        """,
    )
    write(
        root / "docs/RELEASE_CHECKLIST.md",
        """
        # Release Checklist

        Keep external pending gates for KataGo, readboard, and provider checks before release claims.
        """,
    )
    create_user_flow_inputs(root, omitted_commands=omitted_commands)


def create_user_flow_inputs(root: Path, *, omitted_commands: set[str]) -> None:
    smoke_user_flows = load_current_smoke_user_flows()
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
        {command_functions}

        fn run() {{
            tauri::generate_handler![
{command_handlers}
            ];
        }}
        """,
    )


def load_current_smoke_user_flows():
    script = ROOT / "scripts" / "smoke_user_flows.py"
    spec = importlib.util.spec_from_file_location("current_smoke_user_flows", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["current_smoke_user_flows"] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
