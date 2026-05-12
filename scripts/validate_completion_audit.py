#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DOC = "docs/COMPLETION_AUDIT.md"

REQUIRED_SECTION_PATTERNS = {
    "completion criteria": re.compile(r"^#{1,3}\s+.*\b(?:completion\s+criteria|criteria)\b", re.IGNORECASE | re.MULTILINE),
    "evidence": re.compile(r"^#{1,3}\s+.*\bevidence\b", re.IGNORECASE | re.MULTILINE),
    "missing blockers": re.compile(r"^#{1,3}\s+.*\b(?:missing\s+blockers|blockers|remaining\s+blockers|gaps)\b", re.IGNORECASE | re.MULTILINE),
}

OVERCLAIM_PATTERNS = (
    ("100 percent complete", re.compile(r"\b100\s*%\s+complete\b", re.IGNORECASE)),
    ("full legacy parity complete", re.compile(r"\bfull\s+legacy\s+parity\b[^.\n\r]{0,80}\b(?:complete|done|achieved|proven|validated|ready)\b", re.IGNORECASE)),
    ("official release published", re.compile(r"\bofficial\s+release\b[^.\n\r]{0,80}\b(?:published|released|complete|ready|validated)\b", re.IGNORECASE)),
    ("signed release ready", re.compile(r"\bsigned\b[^.\n\r]{0,40}\b(?:release|installer|build)\b[^.\n\r]{0,80}\b(?:ready|complete|validated|published)\b", re.IGNORECASE)),
    ("notarized release ready", re.compile(r"\bnotari[sz]ed\b[^.\n\r]{0,80}\b(?:ready|complete|validated|published)\b", re.IGNORECASE)),
    ("updater ready", re.compile(r"\bupdater\b[^.\n\r]{0,80}\b(?:ready|complete|validated|published)\b", re.IGNORECASE)),
    ("bundled large model complete", re.compile(r"\bbundled\s+(?:large[-\s])?model\b[^.\n\r]{0,80}\b(?:complete|included|ready|validated|proven)\b", re.IGNORECASE)),
    (
        "provider/readboard full parity complete",
        re.compile(
            r"\b(?:provider/readboard|provider\s+and\s+readboard|provider\s*/\s*readboard)\b[^.\n\r]{0,80}\bfull\s+parity\b[^.\n\r]{0,80}\b(?:complete|done|achieved|proven|validated|ready)\b",
            re.IGNORECASE,
        ),
    ),
)

EVIDENCE_PATH_RE = re.compile(r"docs/qa/[A-Za-z0-9_.@/+~-]+\.json")
BLOCKER_TERMS = (
    "blocker",
    "external",
    "missing",
    "not covered",
    "pending",
    "remain",
    "remaining",
    "required before",
    "unresolved",
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


class CompletionAuditValidator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.results: list[CheckResult] = []
        self.audit_text = ""

    def pass_(self, name: str, detail: str) -> None:
        self.results.append(CheckResult(name, True, detail))

    def fail(self, name: str, detail: str) -> None:
        self.results.append(CheckResult(name, False, detail))

    def path(self, rel: str) -> Path:
        return self.root / rel

    def load_audit_doc(self) -> None:
        path = self.path(AUDIT_DOC)
        if not path.is_file():
            self.fail("completion_audit_doc", f"missing required completion audit document: {AUDIT_DOC}")
            return
        self.audit_text = path.read_text(encoding="utf-8")
        self.pass_("completion_audit_doc", f"{AUDIT_DOC} is present")

    def check_required_sections(self) -> None:
        missing = [name for name, pattern in REQUIRED_SECTION_PATTERNS.items() if not pattern.search(self.audit_text)]
        if missing:
            self.fail("required_sections", "missing required completion audit sections: " + ", ".join(missing))
        else:
            self.pass_("required_sections", "completion criteria, evidence, and missing blockers sections are present")

    def check_overclaims(self) -> None:
        hits: list[str] = []
        for label, pattern in OVERCLAIM_PATTERNS:
            for match in pattern.finditer(self.audit_text):
                if label == "100 percent complete" or not is_negated_boundary(self.audit_text, match.start(), match.end()):
                    hits.append(f"{label}: {compact(match.group(0))!r}")
        if hits:
            self.fail("overclaims", "completion audit overclaim wording found: " + "; ".join(hits))
        else:
            self.pass_("overclaims", "no 100%, full parity, official release, signing/notarization/updater, bundled-large-model, or provider/readboard overclaims found")

    def check_evidence_references(self) -> None:
        evidence_paths = sorted(set(EVIDENCE_PATH_RE.findall(self.audit_text)))
        if not evidence_paths:
            self.fail("evidence_references", "completion audit must reference at least one docs/qa/*.json evidence file")
            return

        errors: list[str] = []
        passed = 0
        for rel in evidence_paths:
            path = self.path(rel)
            if not path.is_file():
                errors.append(f"{rel} is missing")
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{rel} invalid JSON at line {exc.lineno}: {exc.msg}")
                continue
            status = extract_status(payload)
            if status != "pass":
                errors.append(f"{rel} status must be pass, found {status!r}")
                continue
            passed += 1

        if errors:
            self.fail("evidence_references", "; ".join(errors))
        else:
            self.pass_("evidence_references", f"{passed} referenced docs/qa evidence files are present with status=pass")

    def check_missing_blockers(self) -> None:
        section = section_text(self.audit_text, "missing")
        if section is None:
            section = section_text(self.audit_text, "blocker")
        if section is None:
            section = section_text(self.audit_text, "gap")
        if section is None:
            self.fail("missing_blockers", "missing blockers section could not be located")
            return

        normalized = section.casefold()
        if re.search(r"\b(?:none|no\s+blockers?|nothing\s+remaining|0\s+blockers?)\b", normalized):
            self.fail("missing_blockers", "missing blockers section must not claim no blockers or nothing remaining")
            return
        if not any(term in normalized for term in BLOCKER_TERMS):
            self.fail("missing_blockers", "missing blockers section must identify pending/external/missing/unresolved blockers")
            return
        self.pass_("missing_blockers", "missing blockers section records remaining or external blockers")

    def run(self) -> list[CheckResult]:
        self.load_audit_doc()
        if self.audit_text:
            self.check_required_sections()
            self.check_overclaims()
            self.check_evidence_references()
            self.check_missing_blockers()
        return self.results


def extract_status(payload: Any) -> str | None:
    if isinstance(payload, dict):
        value = payload.get("status")
        if isinstance(value, str):
            return value.strip().lower()
    return None


def section_text(text: str, keyword: str) -> str | None:
    heading = re.search(rf"^#{{1,3}}\s+.*\b{re.escape(keyword)}\w*\b.*$", text, re.IGNORECASE | re.MULTILINE)
    if not heading:
        return None
    next_heading = re.search(r"^#{1,3}\s+", text[heading.end() :], re.MULTILINE)
    end = heading.end() + next_heading.start() if next_heading else len(text)
    return text[heading.end() : end]


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def is_negated_boundary(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 80) : min(len(text), end + 40)].casefold()
    negation_terms = (
        "false",
        "not ",
        "not-",
        "not_",
        "no ",
        "cannot",
        "do not claim",
        "does not claim",
        "must not claim",
        "outside",
        "pending",
        "remain",
        "requires",
        "unresolved",
        "without",
    )
    return any(term in window for term in negation_terms)


def print_results(results: list[CheckResult], *, verbose: bool) -> None:
    failures = [result for result in results if not result.ok]
    if verbose or failures:
        for result in results:
            if verbose or not result.ok:
                prefix = "PASS" if result.ok else "FAIL"
                print(f"{prefix} {result.name}: {result.detail}")
    else:
        print("PASS completion audit: sections, evidence status, blockers, and overclaim boundaries validated")
    print(f"Completion audit: {len(results) - len(failures)} passed, {len(failures)} failed.")


def validate(root: Path) -> list[CheckResult]:
    return CompletionAuditValidator(root).run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate docs/COMPLETION_AUDIT.md completion boundaries and evidence references.")
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
