#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = (
    "docs/RELEASE_CHECKLIST.md",
    "docs/QA_REPORT.md",
    "docs/LEGACY_PARITY_MATRIX.md",
    "docs/RELEASE_PROCESS.md",
)
RELEASE_READINESS_EVIDENCE = "docs/qa/release-readiness-preflight.json"
COMPLETION_AUDIT_EVIDENCE = "docs/qa/completion-audit-gate.json"
CURRENT_CENTRAL_SMOKE_PASSED = 59
SELF_EXCLUDING_BASELINES = {
    RELEASE_READINESS_EVIDENCE: ("release_readiness_preflight", 54),
    COMPLETION_AUDIT_EVIDENCE: ("completion_audit_gate", 55),
}

POLICY_TERMS = {
    "signing": ("signing", "signed", "unsigned", "codesign", "authenticode"),
    "notarization": ("notarization", "notarized", "notarised"),
    "updater": ("updater", "update signing"),
    "rollback": ("rollback", "roll back"),
}

STALE_SMOKE_PATTERNS = (
    re.compile(r"\b44\s+passed\b", re.IGNORECASE),
    re.compile(r"\b44\s*/\s*0\s*/\s*0\b", re.IGNORECASE),
    re.compile(r"\b44\s+pass(?:ed|ing)?\s*,\s*0\s+pending\b", re.IGNORECASE),
)
SMOKE_COUNT_PATTERNS = (
    re.compile(r"\b(?P<passed>\d+)\s+passed\s*,\s*(?P<failed>\d+)\s+failed\s*,\s*(?P<pending>\d+)\s+pending\b", re.IGNORECASE),
    re.compile(r"\b(?P<passed>\d+)\s*/\s*(?P<failed>\d+)\s*/\s*(?P<pending>\d+)\b", re.IGNORECASE),
)

OVERCLAIM_PATTERNS = (
    ("fullLegacyParity true", re.compile(r"\bfullLegacyParity\b[^.\n\r]{0,40}\btrue\b", re.IGNORECASE)),
    ("full release parity true", re.compile(r"\bfullReleaseParity\b[^.\n\r]{0,40}\btrue\b", re.IGNORECASE)),
    ("production signed true", re.compile(r"\bproductionSigned\b[^.\n\r]{0,40}\btrue\b", re.IGNORECASE)),
    ("notarized true", re.compile(r"\bnotarized\b[^.\n\r]{0,40}\btrue\b", re.IGNORECASE)),
    ("updater ready true", re.compile(r"\bupdaterReady\b[^.\n\r]{0,40}\btrue\b", re.IGNORECASE)),
    ("official release published true", re.compile(r"\bofficialReleasePublished\b[^.\n\r]{0,40}\btrue\b", re.IGNORECASE)),
    ("release published true", re.compile(r"\breleasePublished\b[^.\n\r]{0,40}\btrue\b", re.IGNORECASE)),
    (
        "full legacy parity overclaim",
        re.compile(
            r"\bfull\s+legacy\s+parity\b[^.\n\r]{0,80}\b(?:achieved|complete|covered|done|met|passed|proven|ready|validated)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "full release parity overclaim",
        re.compile(
            r"\bfull\s+release\s+parity\b[^.\n\r]{0,80}\b(?:achieved|complete|covered|done|met|passed|proven|ready|validated)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "signed release overclaim",
        re.compile(
            r"\b(?:signed|notarized|notarised)\s+(?:production\s+)?release\b[^.\n\r]{0,80}\b(?:achieved|complete|covered|done|met|passed|proven|ready|validated)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "official release overclaim",
        re.compile(
            r"\bofficial\s+release\b[^.\n\r]{0,80}\b(?:published|released|ready|validated|complete)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "provider/readboard parity overclaim",
        re.compile(
            r"\bprovider/readboard(?:/OCR)?\s+parity\b[^.\n\r]{0,80}\b(?:achieved|complete|covered|done|met|passed|proven|ready|validated)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "readboard parity overclaim",
        re.compile(
            r"\bfull\s+readboard\s+parity\b[^.\n\r]{0,80}\b(?:achieved|complete|covered|done|met|passed|proven|ready|validated)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "bundled large model overclaim",
        re.compile(
            r"\bbundled\s+(?:large[-\s])?model\b[^.\n\r]{0,80}\b(?:included|ready|validated|complete|covered|proven)\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


class ReleaseReadinessValidator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.results: list[CheckResult] = []
        self.texts: dict[str, str] = {}

    def pass_(self, name: str, detail: str) -> None:
        self.results.append(CheckResult(name, True, detail))

    def fail(self, name: str, detail: str) -> None:
        self.results.append(CheckResult(name, False, detail))

    def path(self, rel: str) -> Path:
        return self.root / rel

    def load_required_docs(self) -> None:
        missing: list[str] = []
        for rel in REQUIRED_DOCS:
            path = self.path(rel)
            if not path.is_file():
                missing.append(rel)
                continue
            self.texts[rel] = path.read_text(encoding="utf-8")

        if missing:
            self.fail("required_release_docs", "missing release readiness docs: " + ", ".join(missing))
        else:
            self.pass_("required_release_docs", "release checklist, QA report, parity matrix, and release process are present")

    def check_stale_smoke_counts(self) -> None:
        hits = []
        for rel, text in self.texts.items():
            for pattern in STALE_SMOKE_PATTERNS:
                match = pattern.search(text)
                if match:
                    hits.append(f"{rel}: {match.group(0)!r}")
            for match in iter_current_central_smoke_counts(text):
                passed = int(match.group("passed"))
                failed = int(match.group("failed"))
                pending = int(match.group("pending"))
                if (passed, failed, pending) != (CURRENT_CENTRAL_SMOKE_PASSED, 0, 0):
                    hits.append(
                        f"{rel}: current central smoke count must be "
                        f"{CURRENT_CENTRAL_SMOKE_PASSED} passed, 0 failed, 0 pending, found {match.group(0)!r}"
                    )
        if hits:
            self.fail("stale_smoke_counts", "stale smoke count wording found: " + "; ".join(hits))
        else:
            self.pass_(
                "stale_smoke_counts",
                f"no stale current central smoke count found; current count is {CURRENT_CENTRAL_SMOKE_PASSED}/0/0 when stated",
            )

    def check_self_excluding_evidence_baseline(self, evidence_path: str, gate_name: str, baseline_passed: int) -> None:
        path = self.path(evidence_path)
        if not path.is_file():
            self.pass_(f"{gate_name}_baseline", f"optional {gate_name} evidence is not recorded")
            return
        try:
            evidence = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self.fail(f"{gate_name}_baseline", f"{evidence_path} invalid JSON at line {exc.lineno}: {exc.msg}")
            return

        smoke = evidence.get("smokeUserFlows")
        if not isinstance(smoke, dict):
            self.fail(f"{gate_name}_baseline", f"{evidence_path} missing smokeUserFlows object")
            return
        passed = smoke.get("passed")
        failed = smoke.get("failed")
        pending = smoke.get("pending")
        excludes = smoke.get("baselineExcludes")
        if (
            passed == baseline_passed
            and failed == 0
            and pending == 0
            and isinstance(excludes, list)
            and gate_name in excludes
        ):
            self.pass_(
                f"{gate_name}_baseline",
                f"{gate_name} evidence records self-excluding {baseline_passed}/0/0 baseline",
            )
            return
        if (passed, failed, pending) == (CURRENT_CENTRAL_SMOKE_PASSED, 0, 0):
            self.pass_(f"{gate_name}_baseline", f"{gate_name} evidence records current {CURRENT_CENTRAL_SMOKE_PASSED}/0/0 baseline")
            return

        self.fail(
            f"{gate_name}_baseline",
            f"{evidence_path} smokeUserFlows must be {CURRENT_CENTRAL_SMOKE_PASSED}/0/0 or "
            f"self-excluding {baseline_passed}/0/0 for {gate_name}; "
            f"found {passed!r}/{failed!r}/{pending!r}",
        )

    def check_self_excluding_evidence_baselines(self) -> None:
        for evidence_path, (gate_name, baseline_passed) in SELF_EXCLUDING_BASELINES.items():
            self.check_self_excluding_evidence_baseline(evidence_path, gate_name, baseline_passed)

    def check_release_overclaims(self) -> None:
        hits = []
        for rel, text in self.texts.items():
            for label, pattern in OVERCLAIM_PATTERNS:
                match = pattern.search(text)
                if match and (label.endswith(" true") or not is_negated_boundary(text, match.start(), match.end())):
                    hits.append(f"{rel}: {label}: {compact(match.group(0))!r}")
        if hits:
            self.fail("release_overclaims", "overclaim wording found: " + "; ".join(hits))
        else:
            self.pass_(
                "release_overclaims",
                "no full parity, signed/notarized/updater/official release, provider/readboard, or bundled-large-model overclaims found",
            )

    def check_policy_status(self) -> None:
        combined = "\n".join(self.texts.values()).casefold()
        release_process = self.texts.get("docs/RELEASE_PROCESS.md", "").casefold()
        checklist = self.texts.get("docs/RELEASE_CHECKLIST.md", "").casefold()

        missing_combined = [name for name, terms in POLICY_TERMS.items() if not any(term in combined for term in terms)]
        missing_process = [name for name, terms in POLICY_TERMS.items() if not any(term in release_process for term in terms)]
        missing_checklist = [name for name, terms in POLICY_TERMS.items() if not any(term in checklist for term in terms)]

        details: list[str] = []
        if missing_combined:
            details.append("missing anywhere: " + ", ".join(missing_combined))
        if missing_process:
            details.append("missing from docs/RELEASE_PROCESS.md: " + ", ".join(missing_process))
        if missing_checklist:
            details.append("missing from docs/RELEASE_CHECKLIST.md: " + ", ".join(missing_checklist))

        if details:
            self.fail("release_policy_status", "; ".join(details))
        else:
            self.pass_("release_policy_status", "signing, notarization, updater, and rollback policy states are documented")

    def check_scoped_unsigned_posture(self) -> None:
        combined = "\n".join(self.texts.values()).casefold()
        required_posture = {
            "unsigned": ("unsigned", "no-sign", "not signed"),
            "scoped": ("scoped",),
            "external gates": ("external gate", "external-validation-needed", "remain external", "outside"),
        }
        missing = [name for name, terms in required_posture.items() if not any(term in combined for term in terms)]
        if missing:
            self.fail("scoped_unsigned_posture", "missing current release posture wording: " + ", ".join(missing))
        else:
            self.pass_("scoped_unsigned_posture", "current unsigned/scoped/external-gate posture is explicit")

    def run(self) -> list[CheckResult]:
        self.load_required_docs()
        if self.texts:
            self.check_stale_smoke_counts()
            self.check_self_excluding_evidence_baselines()
            self.check_release_overclaims()
            self.check_policy_status()
            self.check_scoped_unsigned_posture()
        return self.results


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def iter_current_central_smoke_counts(text: str):
    for pattern in SMOKE_COUNT_PATTERNS:
        for match in pattern.finditer(text):
            if is_current_central_smoke_context(text, match.start(), match.end()):
                yield match


def is_current_central_smoke_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 160) : min(len(text), end + 160)].casefold()
    if "release_readiness_preflight" in window and "baseline" in window and "exclude" in window:
        return False
    central_terms = ("central smoke", "smoke_user_flows.py", "repository smoke gate", "smoke gate")
    current_terms = ("current", "currently", "reports", "reported", "passes")
    return any(term in window for term in central_terms) and any(term in window for term in current_terms)


def is_negated_boundary(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 120) : min(len(text), end + 120)].casefold()
    boundary_terms = (
        "false",
        "not ",
        "not-",
        "not_",
        "no ",
        "without",
        "outside",
        "pending",
        "remain",
        "requires",
        "required before",
        "do not claim",
        "does not claim",
        "must not claim",
        "cannot claim",
    )
    return any(term in window for term in boundary_terms)


def print_results(results: list[CheckResult], *, verbose: bool) -> None:
    failures = [result for result in results if not result.ok]
    if verbose or failures:
        for result in results:
            if verbose or not result.ok:
                prefix = "PASS" if result.ok else "FAIL"
                print(f"{prefix} {result.name}: {result.detail}")
    else:
        print("PASS release readiness: release wording, readiness policy, and scoped boundaries validated")
    print(f"Release readiness: {len(results) - len(failures)} passed, {len(failures)} failed.")


def validate(root: Path) -> list[CheckResult]:
    return ReleaseReadinessValidator(root).run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate release readiness wording and scoped release boundary policy.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    results = validate(args.root.resolve())
    print_results(results, verbose=args.verbose)
    if any(not result.ok for result in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
