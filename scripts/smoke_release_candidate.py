#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ROOT = Path(__file__).resolve().parents[1]
Status = Literal["PASS", "FAIL", "PENDING"]

KEY_SCRIPTS = [
    "scripts/smoke_user_flows.py",
    "scripts/validate_scaffold.py",
    "scripts/validate_release_assets.py",
    "scripts/validate_release_workflow.py",
    "scripts/collect_release_assets.py",
]
QA_RELEASE_FILES = [
    "docs/QA_REPORT.md",
    "docs/RELEASE_CHECKLIST.md",
]
DANGEROUS_CLAIMS = [
    re.compile(r"\bfull\s+legacy\s+parity\s+(?:is\s+)?complete\b", re.IGNORECASE),
    re.compile(r"\bcomplete\s+full\s+legacy\s+parity\b", re.IGNORECASE),
    re.compile(
        r"\b(?:legacy\s+)?1\s*:\s*1\s+(?:(?:legacy|ui)\s+)?(?:parity|reconstruction)\s+(?:is\s+)?complete\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b100%\s+legacy\s+(?:parity|replacement)\b", re.IGNORECASE),
    re.compile(r"\bfully\s+live-provider-ready\b", re.IGNORECASE),
]
MACOS_ARTIFACT_GLOBS = [
    "apps/desktop/src-tauri/target/release/bundle/macos/*.app",
    "apps/desktop/src-tauri/target/release/bundle/dmg/*.dmg",
    "target/release/bundle/macos/*.app",
    "target/release/bundle/dmg/*.dmg",
]


@dataclass
class SmokeResult:
    name: str
    status: Status
    detail: str


class ReleaseCandidateSmoke:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.results: list[SmokeResult] = []

    def pass_(self, name: str, detail: str) -> None:
        self.results.append(SmokeResult(name, "PASS", detail))

    def fail(self, name: str, detail: str) -> None:
        self.results.append(SmokeResult(name, "FAIL", detail))

    def pending(self, name: str, detail: str) -> None:
        self.results.append(SmokeResult(name, "PENDING", detail))

    def path(self, rel: str) -> Path:
        return self.root / rel

    def read_text(self, rel: str) -> str | None:
        try:
            return self.path(rel).read_text(encoding="utf-8")
        except FileNotFoundError:
            self.fail(f"file:{rel}", "file is missing")
        return None

    def check_key_scripts(self) -> None:
        missing = [rel for rel in KEY_SCRIPTS if not self.path(rel).is_file()]
        if missing:
            self.fail("key_scripts", "missing: " + ", ".join(missing))
            return
        self.pass_("key_scripts", f"{len(KEY_SCRIPTS)} repository smoke/release scripts are present")

    def check_macos_artifact(self) -> None:
        artifacts = find_macos_artifacts(self.root)
        if artifacts:
            display = ", ".join(str(path.relative_to(self.root)) for path in artifacts[:3])
            suffix = "" if len(artifacts) <= 3 else f", and {len(artifacts) - 3} more"
            self.pass_("macos_build_artifact", "found local macOS build artifact: " + display + suffix)
            return
        self.pending(
            "macos_build_artifact",
            "no local macOS .app or .dmg bundle found; packaging remains an external/local build gate",
        )

    def check_user_flow_smoke(self) -> None:
        smoke_user_flows = load_smoke_user_flows(self.root)
        results = smoke_user_flows.UserFlowSmoke(self.root).run()
        failures = [result for result in results if result.status == "FAIL"]
        if failures:
            details = "; ".join(f"{result.name}: {result.detail}" for result in failures)
            self.fail("smoke_user_flows", "user-flow smoke reported FAIL: " + details)
            return
        pending = [result for result in results if result.status == "PENDING"]
        self.pass_(
            "smoke_user_flows",
            f"user-flow smoke has no FAIL results ({len(pending)} pending external/runtime gates)",
        )

    def check_qa_release_guardrails(self) -> None:
        texts: list[tuple[str, str]] = []
        for rel in QA_RELEASE_FILES:
            text = self.read_text(rel)
            if text is not None:
                texts.append((rel, text))
        if len(texts) != len(QA_RELEASE_FILES):
            return

        dangerous_hits: list[str] = []
        for rel, text in texts:
            for pattern in DANGEROUS_CLAIMS:
                if pattern.search(text):
                    dangerous_hits.append(f"{rel}: {pattern.pattern}")
        if dangerous_hits:
            self.fail("qa_release_guardrails", "dangerous release/parity claim found: " + "; ".join(dangerous_hits))
            return

        combined = "\n".join(text for _, text in texts).lower()
        required_tokens = ["external", "pending", "katago", "readboard", "provider"]
        missing = [token for token in required_tokens if token not in combined]
        if missing:
            self.fail("qa_release_guardrails", "external gate language missing tokens: " + ", ".join(missing))
            return
        self.pass_("qa_release_guardrails", "QA and release checklist retain external gates and avoid full-parity claims")

    def run(self) -> list[SmokeResult]:
        self.check_key_scripts()
        self.check_macos_artifact()
        self.check_user_flow_smoke()
        self.check_qa_release_guardrails()
        return self.results


def find_macos_artifacts(root: Path) -> list[Path]:
    artifacts: list[Path] = []
    for pattern in MACOS_ARTIFACT_GLOBS:
        artifacts.extend(path for path in root.glob(pattern) if path.exists())
    return sorted(set(artifacts))


def load_smoke_user_flows(root: Path):
    script = root / "scripts" / "smoke_user_flows.py"
    spec = importlib.util.spec_from_file_location("smoke_user_flows_for_release_smoke", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["smoke_user_flows_for_release_smoke"] = module
    spec.loader.exec_module(module)
    return module


def print_results(results: list[SmokeResult], *, verbose: bool) -> None:
    failures = [result for result in results if result.status == "FAIL"]
    pending = [result for result in results if result.status == "PENDING"]
    passes = [result for result in results if result.status == "PASS"]
    if verbose or failures:
        for result in results:
            if verbose or result.status == "FAIL":
                print(f"{result.status} {result.name}: {result.detail}")
    else:
        print("PASS release-candidate smoke: repository-local checks passed")
        if pending:
            print(f"PENDING release-candidate smoke gates: {len(pending)} deferred local/external checks")
    print(f"Release-candidate smoke: {len(passes)} passed, {len(failures)} failed, {len(pending)} pending.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local release-candidate smoke checks for LizzieYzy Next.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to validate")
    parser.add_argument("--verbose", action="store_true", help="print passing and pending checks as well as failures")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"Repository root does not exist: {root}", file=sys.stderr)
        return 2
    results = ReleaseCandidateSmoke(root).run()
    print_results(results, verbose=args.verbose)
    return 1 if any(result.status == "FAIL" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
