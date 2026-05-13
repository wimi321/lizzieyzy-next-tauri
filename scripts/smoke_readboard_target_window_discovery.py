#!/usr/bin/env python3
"""Validate scoped Readboard controlled target-window discovery evidence.

This helper intentionally does not fabricate PASS evidence from fixtures. A
PASS must already contain runtime/backend-backed discovery and capture facts
and is validated by the central smoke_user_flows contract.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SMOKE_USER_FLOWS = ROOT / "scripts" / "smoke_user_flows.py"
SPEC = importlib.util.spec_from_file_location("smoke_user_flows", SMOKE_USER_FLOWS)
assert SPEC is not None and SPEC.loader is not None
smoke_user_flows = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_user_flows"] = smoke_user_flows
SPEC.loader.exec_module(smoke_user_flows)

DEFAULT_EVIDENCE_OUT = ROOT / smoke_user_flows.READBOARD_TARGET_WINDOW_DISCOVERY_SMOKE_EVIDENCE


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_evidence(path: Path, *, verbose: bool = False) -> int:
    if not path.is_file():
        print(f"FAIL: evidence not found: {path}", file=sys.stderr)
        return 1
    try:
        evidence = load_json(path)
    except json.JSONDecodeError as exc:
        print(f"FAIL: invalid JSON: {exc}", file=sys.stderr)
        return 1
    failures = smoke_user_flows.validate_readboard_target_window_discovery_smoke_evidence(evidence, ROOT)
    if failures:
        print("FAIL: readboard target-window discovery evidence is invalid", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    if verbose:
        print(f"PASS: validated scoped target-window discovery evidence at {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-out",
        type=Path,
        default=DEFAULT_EVIDENCE_OUT,
        help="Path to an existing evidence JSON to validate.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    evidence_path = args.evidence_out
    if not evidence_path.is_absolute():
        evidence_path = ROOT / evidence_path
    return validate_evidence(evidence_path, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
