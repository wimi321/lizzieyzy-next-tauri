#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = "docs/LEGACY_PARITY_MATRIX.md"

REQUIRED_SECTIONS = [
    "UI",
    "SGF And Editing",
    "KataGo",
    "Provider And readboard",
    "Settings",
    "Packaging",
]
STATUS_TOKENS = {
    "complete",
    "partial",
    "missing",
    "external-validation-needed",
}
FORBIDDEN_CLAIMS = [
    re.compile(r"\b100\s*%\s+complete\b", re.IGNORECASE),
]


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass
class MatrixRow:
    section: str
    capability: str
    status: str
    evidence: str
    external_gate: str
    notes: str


class LegacyParityValidator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.results: list[CheckResult] = []

    def pass_(self, name: str, detail: str) -> None:
        self.results.append(CheckResult(name, True, detail))

    def fail(self, name: str, detail: str) -> None:
        self.results.append(CheckResult(name, False, detail))

    def path(self, rel: str) -> Path:
        return self.root / rel

    def read_matrix(self) -> str | None:
        try:
            return self.path(MATRIX_PATH).read_text(encoding="utf-8")
        except FileNotFoundError:
            self.fail("matrix_file", f"{MATRIX_PATH} is missing")
        return None

    def check_forbidden_claims(self, text: str) -> None:
        matches = [pattern.pattern for pattern in FORBIDDEN_CLAIMS if pattern.search(text)]
        if matches:
            self.fail("forbidden_claims", "matrix contains a forbidden completion claim")
        else:
            self.pass_("forbidden_claims", "matrix avoids forbidden completion claims")

    def check_sections(self, text: str) -> list[str]:
        headings = re.findall(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE)
        missing = [section for section in REQUIRED_SECTIONS if section not in headings]
        if missing:
            self.fail("required_sections", "missing sections: " + ", ".join(missing))
        else:
            self.pass_("required_sections", "required sections present: " + ", ".join(REQUIRED_SECTIONS))
        return headings

    def parse_rows(self, text: str) -> list[MatrixRow]:
        rows: list[MatrixRow] = []
        current_section: str | None = None
        for raw_line in text.splitlines():
            heading = re.match(r"^##\s+(.+?)\s*$", raw_line)
            if heading:
                current_section = heading.group(1)
                continue
            if current_section not in REQUIRED_SECTIONS:
                continue
            line = raw_line.strip()
            if not line.startswith("|") or "---" in line:
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells[:5] == ["Legacy Capability", "Current Status", "Acceptance Evidence", "External Gate", "Notes"]:
                continue
            if len(cells) != 5:
                self.fail("matrix_table_shape", f"{current_section}: expected 5 columns, found {len(cells)}")
                continue
            rows.append(
                MatrixRow(
                    section=current_section,
                    capability=cells[0],
                    status=cells[1].strip("`"),
                    evidence=cells[2],
                    external_gate=cells[3],
                    notes=cells[4],
                )
            )
        return rows

    def check_rows(self, rows: list[MatrixRow]) -> None:
        if not rows:
            self.fail("matrix_rows", "no machine-checkable matrix rows found")
            return

        sections_with_rows = {row.section for row in rows}
        missing_rows = [section for section in REQUIRED_SECTIONS if section not in sections_with_rows]
        invalid_statuses = [
            f"{row.section} / {row.capability}: {row.status}"
            for row in rows
            if row.status not in STATUS_TOKENS
        ]
        thin_evidence = [
            f"{row.section} / {row.capability}"
            for row in rows
            if is_placeholder(row.evidence) or is_placeholder(row.external_gate)
        ]
        observed_statuses = {row.status for row in rows}
        missing_statuses = sorted(STATUS_TOKENS - observed_statuses)

        if missing_rows:
            self.fail("matrix_rows", "sections without rows: " + ", ".join(missing_rows))
        else:
            self.pass_("matrix_rows", f"{len(rows)} parity rows found across all required sections")

        if invalid_statuses:
            self.fail("status_tokens", "invalid status values: " + "; ".join(invalid_statuses))
        elif missing_statuses:
            self.fail("status_tokens", "required status tokens not represented: " + ", ".join(missing_statuses))
        else:
            self.pass_("status_tokens", "all required status tokens are represented and valid")

        if thin_evidence:
            self.fail("acceptance_evidence", "placeholder evidence in rows: " + "; ".join(thin_evidence))
        else:
            self.pass_("acceptance_evidence", "each row has acceptance evidence and an external gate entry")

    def run(self) -> list[CheckResult]:
        text = self.read_matrix()
        if text is None:
            return self.results
        self.check_forbidden_claims(text)
        self.check_sections(text)
        rows = self.parse_rows(text)
        self.check_rows(rows)
        return self.results


def is_placeholder(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.strip()).lower()
    return normalized in {"", "tbd", "todo", "n/a", "na", "none"}


def print_results(results: list[CheckResult], *, verbose: bool) -> None:
    failures = [result for result in results if not result.ok]
    if verbose or failures:
        for result in results:
            if verbose or not result.ok:
                prefix = "PASS" if result.ok else "FAIL"
                print(f"{prefix} {result.name}: {result.detail}")
    else:
        print("PASS legacy parity matrix: required sections, statuses, and evidence validated")
    print(f"Legacy parity validation: {len(results) - len(failures)} passed, {len(failures)} failed.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the LizzieYzy Next legacy parity matrix.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to validate")
    parser.add_argument("--verbose", action="store_true", help="print passing checks as well as failures")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"Repository root does not exist: {root}", file=sys.stderr)
        return 2
    results = LegacyParityValidator(root).run()
    print_results(results, verbose=args.verbose)
    return 1 if any(not result.ok for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
